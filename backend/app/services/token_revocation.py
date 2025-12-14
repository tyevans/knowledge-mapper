"""Token revocation service for OAuth token blacklisting."""
import logging
import time
from typing import Optional

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class TokenRevocationService:
    """
    Redis-based token revocation service for blacklisting JWT tokens.

    This service implements a token blacklist using Redis for distributed token
    revocation across multiple backend instances. When a token is revoked (e.g.,
    during logout or security incident), its jti (JWT ID) is added to the blacklist
    with a TTL matching the token's expiration time.

    Key Features:
    - Distributed blacklist across multiple backend instances
    - Automatic expiration via Redis TTL (no need to store expired tokens)
    - Graceful degradation if Redis is unavailable
    - Fail-closed security model (reject token if Redis check fails)

    Security Model:
    - Fail closed: If Redis is unavailable during revocation check, reject the token
    - Fail open for revocation: If Redis is unavailable during revocation, return 503
    - Rationale: Prioritize security over availability for authentication

    Usage:
        >>> service = TokenRevocationService(redis_client)
        >>> await service.revoke_token(jti="abc-123", exp=1762903147)
        >>> is_revoked = await service.is_token_revoked(jti="abc-123")
        >>> # is_revoked == True
    """

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize the token revocation service.

        Args:
            redis_client: Redis client instance for storing blacklist
        """
        self.redis_client = redis_client

    async def revoke_token(self, jti: str, exp: int) -> None:
        """
        Add a token to the revocation blacklist.

        The token is stored in Redis with a TTL matching the token's expiration time.
        Once the token naturally expires, Redis automatically removes it from the blacklist.

        Args:
            jti: JWT ID (unique token identifier)
            exp: Token expiration time (Unix timestamp)

        Raises:
            redis.RedisError: If Redis is unavailable or operation fails

        Example:
            >>> await service.revoke_token(jti="abc-123", exp=1762903147)
        """
        current_time = int(time.time())
        ttl = exp - current_time

        # If token is already expired, no need to blacklist it
        if ttl <= 0:
            logger.info(
                "Token already expired, skipping revocation",
                extra={"jti": jti, "exp": exp, "current_time": current_time},
            )
            return

        redis_key = f"revoked_token:{jti}"

        try:
            # Add token to blacklist with TTL
            await self.redis_client.setex(
                name=redis_key,
                time=ttl,
                value="revoked",
            )

            logger.info(
                "Token revoked successfully",
                extra={
                    "jti": jti,
                    "exp": exp,
                    "ttl": ttl,
                    "redis_key": redis_key,
                },
            )

        except redis.RedisError as e:
            logger.error(
                "Redis error during token revocation",
                extra={
                    "jti": jti,
                    "error_type": type(e).__name__,
                    "error_details": str(e),
                },
            )
            # Re-raise to let caller handle with 503 Service Unavailable
            raise

    async def is_token_revoked(self, jti: str) -> bool:
        """
        Check if a token has been revoked.

        This method implements the security-critical check during authentication.
        If Redis is unavailable, the method returns True (fail closed) to reject
        the token rather than potentially allowing a revoked token.

        Args:
            jti: JWT ID (unique token identifier)

        Returns:
            True if token is revoked or Redis check fails, False if token is valid

        Example:
            >>> is_revoked = await service.is_token_revoked(jti="abc-123")
            >>> if is_revoked:
            ...     raise HTTPException(401, "Token has been revoked")
        """
        redis_key = f"revoked_token:{jti}"

        try:
            # Check if token exists in blacklist
            exists = await self.redis_client.exists(redis_key)

            if exists:
                logger.info(
                    "Token revocation check: Token is revoked",
                    extra={"jti": jti, "redis_key": redis_key},
                )
                return True

            logger.debug(
                "Token revocation check: Token is valid",
                extra={"jti": jti, "redis_key": redis_key},
            )
            return False

        except redis.RedisError as e:
            # SECURITY: Fail closed - if Redis is unavailable, reject the token
            # Rationale: It's safer to temporarily block legitimate users than to
            # potentially allow a revoked (compromised) token
            logger.error(
                "Redis error during revocation check - rejecting token (fail closed)",
                extra={
                    "jti": jti,
                    "error_type": type(e).__name__,
                    "error_details": str(e),
                },
            )
            # Return True to indicate token should be rejected
            return True

    async def get_revoked_count(self) -> Optional[int]:
        """
        Get the count of currently revoked tokens (for monitoring/debugging).

        Returns:
            Number of revoked tokens in Redis, or None if Redis unavailable

        Example:
            >>> count = await service.get_revoked_count()
            >>> print(f"Currently revoked tokens: {count}")
        """
        try:
            # Scan for all revoked_token:* keys
            pattern = "revoked_token:*"
            cursor = 0
            count = 0

            # Use SCAN instead of KEYS for production safety
            while True:
                cursor, keys = await self.redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                count += len(keys)
                if cursor == 0:
                    break

            logger.debug(
                "Revoked token count retrieved",
                extra={"count": count, "pattern": pattern},
            )
            return count

        except redis.RedisError as e:
            logger.warning(
                "Redis error during revoked token count",
                extra={
                    "error_type": type(e).__name__,
                    "error_details": str(e),
                },
            )
            return None


# Singleton instance
_token_revocation_service: Optional[TokenRevocationService] = None


async def get_token_revocation_service() -> TokenRevocationService:
    """
    Get the singleton TokenRevocationService instance.

    This function returns the application-wide token revocation service instance.
    It creates the Redis client and service on first call, then returns the same
    instance for all subsequent calls.

    Returns:
        TokenRevocationService instance

    Example:
        >>> from fastapi import Depends
        >>> from app.services.token_revocation import get_token_revocation_service
        >>>
        >>> @router.post("/revoke")
        >>> async def revoke_token(
        ...     service: TokenRevocationService = Depends(get_token_revocation_service)
        ... ):
        ...     await service.revoke_token(jti="abc-123", exp=1762903147)
    """
    global _token_revocation_service

    if _token_revocation_service is None:
        # Create Redis client
        redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )

        _token_revocation_service = TokenRevocationService(redis_client)

        logger.info(
            "Token revocation service initialized",
            extra={"redis_url": settings.REDIS_URL},
        )

    return _token_revocation_service
