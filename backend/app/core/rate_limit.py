"""
Rate limiting module for OAuth token validation.

Implements distributed rate limiting using Redis with a sliding window algorithm
to prevent:
- Brute force authentication attacks
- Denial of service attacks
- Token enumeration attacks

The rate limiter maintains two separate limits:
1. General auth requests: Limits all authentication attempts per IP
2. Failed auth attempts: Stricter limit for failed authentication

Gracefully degrades if Redis is unavailable (logs warning and allows request).
"""

import logging
import time
from typing import Optional, Tuple

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """
    Exception raised when rate limit is exceeded.

    Attributes:
        retry_after: Seconds until the rate limit window resets
        limit_type: Type of limit exceeded ("auth" or "failed_auth")
    """

    def __init__(self, retry_after: int, limit_type: str):
        self.retry_after = retry_after
        self.limit_type = limit_type
        super().__init__(
            f"Rate limit exceeded for {limit_type}. Retry after {retry_after} seconds."
        )


class RateLimiter:
    """
    Distributed rate limiter using Redis with sliding window algorithm.

    Implements two tiers of rate limiting:
    - General authentication: Limits all auth requests per IP
    - Failed authentication: Stricter limit for failed auth attempts

    The sliding window algorithm provides accurate rate limiting by:
    1. Using time-based Redis keys (rate_limit:{type}:{identifier}:{window_start})
    2. Incrementing counter for each request
    3. Setting TTL on first request in window
    4. Checking counter against limit

    Graceful degradation: If Redis is unavailable, logs warning and allows request.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        general_limit: int = 100,
        failed_limit: int = 10,
        window_seconds: int = 60,
        enabled: bool = True,
    ):
        """
        Initialize rate limiter.

        Args:
            redis_client: Async Redis client for distributed rate limiting
            general_limit: Max requests per window for general auth (default: 100)
            failed_limit: Max requests per window for failed auth (default: 10)
            window_seconds: Time window in seconds (default: 60)
            enabled: Whether rate limiting is enabled (default: True)
        """
        self.redis_client = redis_client
        self.general_limit = general_limit
        self.failed_limit = failed_limit
        self.window_seconds = window_seconds
        self.enabled = enabled

        logger.info(
            "Rate limiter initialized",
            extra={
                "enabled": enabled,
                "general_limit": general_limit,
                "failed_limit": failed_limit,
                "window_seconds": window_seconds,
            },
        )

    async def check_rate_limit(
        self, identifier: str, is_failed_auth: bool = False
    ) -> None:
        """
        Check if request is within rate limits.

        Uses sliding window algorithm with Redis:
        1. Calculate current window start time
        2. Build Redis key: rate_limit:{type}:{identifier}:{window_start}
        3. Increment counter and get current count
        4. Set TTL on first request
        5. Check if count exceeds limit

        Args:
            identifier: Client identifier (typically IP address)
            is_failed_auth: Whether this is a failed auth attempt (stricter limit)

        Raises:
            RateLimitExceeded: If rate limit is exceeded, includes retry_after seconds

        Note:
            Gracefully degrades if Redis is unavailable - logs warning and allows request.
        """
        # Skip if rate limiting is disabled
        if not self.enabled:
            return

        # Determine limit type and threshold
        limit_type = "failed_auth" if is_failed_auth else "auth"
        limit = self.failed_limit if is_failed_auth else self.general_limit

        # Calculate window start time (aligned to window_seconds boundary)
        current_time = int(time.time())
        window_start = current_time - (current_time % self.window_seconds)

        # Build Redis key: rate_limit:{type}:{identifier}:{window_start}
        # This creates a new key for each time window
        redis_key = f"rate_limit:{limit_type}:{identifier}:{window_start}"

        try:
            # Increment counter and get current count
            count = await self.redis_client.incr(redis_key)

            # Set TTL on first request (count == 1)
            # TTL is 2x window to handle edge cases near window boundaries
            if count == 1:
                await self.redis_client.expire(redis_key, self.window_seconds * 2)

            # Check if limit exceeded
            if count > limit:
                # Calculate retry_after: time until current window ends
                window_end = window_start + self.window_seconds
                retry_after = window_end - current_time

                logger.warning(
                    "Rate limit exceeded",
                    extra={
                        "identifier": identifier,
                        "limit_type": limit_type,
                        "count": count,
                        "limit": limit,
                        "retry_after": retry_after,
                        "window_start": window_start,
                    },
                )

                raise RateLimitExceeded(retry_after=retry_after, limit_type=limit_type)

            # Log successful check (debug level)
            logger.debug(
                "Rate limit check passed",
                extra={
                    "identifier": identifier,
                    "limit_type": limit_type,
                    "count": count,
                    "limit": limit,
                },
            )

        except redis.RedisError as e:
            # Graceful degradation: Log warning and allow request
            # Don't block authentication if rate limiting infrastructure fails
            logger.warning(
                "Redis error during rate limit check - allowing request",
                extra={
                    "identifier": identifier,
                    "limit_type": limit_type,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            # Allow request to proceed
            return

    async def get_current_usage(
        self, identifier: str, is_failed_auth: bool = False
    ) -> Tuple[int, int]:
        """
        Get current usage for an identifier.

        Useful for monitoring and debugging rate limit status.

        Args:
            identifier: Client identifier (typically IP address)
            is_failed_auth: Whether to check failed auth limit

        Returns:
            Tuple of (current_count, limit)

        Note:
            Returns (0, limit) if Redis is unavailable or key doesn't exist.
        """
        if not self.enabled:
            return (0, 0)

        limit_type = "failed_auth" if is_failed_auth else "auth"
        limit = self.failed_limit if is_failed_auth else self.general_limit

        # Calculate current window
        current_time = int(time.time())
        window_start = current_time - (current_time % self.window_seconds)
        redis_key = f"rate_limit:{limit_type}:{identifier}:{window_start}"

        try:
            count_str = await self.redis_client.get(redis_key)
            count = int(count_str) if count_str else 0
            return (count, limit)
        except redis.RedisError as e:
            logger.warning(
                "Redis error getting rate limit usage",
                extra={
                    "identifier": identifier,
                    "limit_type": limit_type,
                    "error": str(e),
                },
            )
            return (0, limit)


# Singleton instance for application-wide use
_rate_limiter: Optional[RateLimiter] = None


async def get_rate_limiter() -> RateLimiter:
    """
    Get singleton rate limiter instance.

    Creates a singleton rate limiter on first call and reuses it for subsequent
    calls. This ensures we have a single Redis connection pool across the application.

    Returns:
        Initialized RateLimiter instance

    Example:
        >>> limiter = await get_rate_limiter()
        >>> await limiter.check_rate_limit("192.168.1.100")
    """
    global _rate_limiter

    if _rate_limiter is None:
        # Initialize Redis client
        redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )

        _rate_limiter = RateLimiter(
            redis_client=redis_client,
            general_limit=settings.RATE_LIMIT_REQUESTS_PER_MINUTE,
            failed_limit=settings.RATE_LIMIT_FAILED_AUTH_PER_MINUTE,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
            enabled=settings.RATE_LIMIT_ENABLED,
        )

        logger.info(
            "Rate limiter singleton initialized",
            extra={
                "redis_url": settings.REDIS_URL,
                "enabled": settings.RATE_LIMIT_ENABLED,
            },
        )

    return _rate_limiter
