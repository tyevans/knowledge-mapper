"""
JWKS client for fetching and caching OAuth provider public keys.

This module provides an async JWKS (JSON Web Key Set) client that:
- Fetches public keys from OAuth providers via OIDC discovery
- Caches keys in Redis for performance
- Supports multiple OAuth providers (multi-tenant)
- Handles key rotation gracefully
- Provides structured logging for all operations
"""

import json
import logging
from typing import Dict, List, Optional, Any

import httpx
import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class JWKSClient:
    """
    Async JWKS client with Redis caching.

    Fetches and caches JSON Web Key Sets from OAuth providers for JWT signature
    validation. Supports multiple issuers (multi-provider) and implements graceful
    error handling with fallback to direct provider fetching if Redis is unavailable.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        cache_ttl: int = 3600,
        http_timeout: int = 10,
    ):
        """
        Initialize JWKS client.

        Args:
            redis_client: Async Redis client for caching JWKS
            cache_ttl: Cache TTL in seconds (default 1 hour)
            http_timeout: HTTP request timeout in seconds (default 10s)
        """
        self.redis_client = redis_client
        self.cache_ttl = cache_ttl
        self.http_timeout = http_timeout
        self._http_client = httpx.AsyncClient(timeout=http_timeout)

    async def get_jwks(self, issuer_url: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get JWKS for an issuer, using cache when available.

        This is the primary method for retrieving JWKS. It checks the cache first
        (unless force_refresh is True), and fetches from the provider on cache miss.

        Args:
            issuer_url: OAuth issuer URL (e.g., http://keycloak:8080/realms/knowledge-mapper-dev)
            force_refresh: Bypass cache and fetch fresh JWKS (useful for key rotation)

        Returns:
            JWKS dictionary with 'keys' array containing JWK objects

        Raises:
            httpx.HTTPError: If JWKS fetch fails (network error, 4xx/5xx response)
            ValueError: If JWKS format is invalid (missing 'keys' field)

        Example:
            >>> client = JWKSClient(redis_client)
            >>> jwks = await client.get_jwks("http://keycloak:8080/realms/knowledge-mapper-dev")
            >>> print(f"Found {len(jwks['keys'])} keys")
        """
        cache_key = f"jwks:{issuer_url}"

        # Check cache first (unless force refresh requested)
        if not force_refresh:
            cached_jwks = await self._get_from_cache(cache_key)
            if cached_jwks:
                logger.debug(
                    "JWKS cache hit",
                    extra={"issuer": issuer_url, "cache_key": cache_key},
                )
                return cached_jwks

        # Cache miss or force refresh - fetch from provider
        logger.info(
            "Fetching JWKS from provider",
            extra={"issuer": issuer_url, "force_refresh": force_refresh},
        )
        jwks = await self._fetch_jwks(issuer_url)

        # Cache the result
        await self._set_in_cache(cache_key, jwks)

        return jwks

    async def get_signing_key(
        self, issuer_url: str, key_id: str, force_refresh: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific signing key by key ID (kid).

        Convenience method that fetches JWKS and extracts a specific key by its
        key ID. This is the typical flow when validating a JWT: extract the 'kid'
        from the JWT header, then fetch that specific key.

        Args:
            issuer_url: OAuth issuer URL
            key_id: JWK key ID (kid claim from JWT header)
            force_refresh: Bypass cache and fetch fresh JWKS

        Returns:
            JWK dictionary for the specified key ID, or None if not found

        Raises:
            httpx.HTTPError: If JWKS fetch fails

        Example:
            >>> # Extract kid from JWT header
            >>> header = jwt.get_unverified_header(token)
            >>> kid = header['kid']
            >>> # Fetch the specific key
            >>> key = await client.get_signing_key(issuer_url, kid)
            >>> if key:
            ...     # Verify JWT signature with this key
            ...     pass
        """
        jwks = await self.get_jwks(issuer_url, force_refresh=force_refresh)

        # Find key by kid
        for key in jwks.get("keys", []):
            if key.get("kid") == key_id:
                logger.debug(
                    "Signing key found",
                    extra={"issuer": issuer_url, "kid": key_id},
                )
                return key

        # Key not found - log warning with available keys for debugging
        available_kids = [k.get("kid") for k in jwks.get("keys", [])]
        logger.warning(
            "Signing key not found in JWKS",
            extra={
                "issuer": issuer_url,
                "requested_kid": key_id,
                "available_kids": available_kids,
            },
        )
        return None

    async def _fetch_jwks(self, issuer_url: str) -> Dict[str, Any]:
        """
        Fetch JWKS from OAuth provider via OIDC discovery.

        Implements the OIDC discovery flow:
        1. Fetch .well-known/openid-configuration from issuer
        2. Extract jwks_uri from discovery document
        3. Fetch JWKS from jwks_uri endpoint

        Args:
            issuer_url: OAuth issuer URL

        Returns:
            JWKS dictionary with 'keys' array

        Raises:
            httpx.HTTPError: If discovery or JWKS fetch fails
            ValueError: If JWKS format is invalid
        """
        # Step 1: Discover JWKS endpoint via OIDC discovery
        discovery_url = f"{issuer_url}/.well-known/openid-configuration"

        try:
            logger.debug(
                "Fetching OIDC discovery document",
                extra={"discovery_url": discovery_url},
            )
            discovery_response = await self._http_client.get(discovery_url)
            discovery_response.raise_for_status()
            discovery_data = discovery_response.json()
            jwks_uri = discovery_data.get("jwks_uri")

            if not jwks_uri:
                raise ValueError(
                    f"No jwks_uri in OIDC discovery document: {discovery_url}"
                )

            logger.debug(
                "OIDC discovery successful",
                extra={"issuer": issuer_url, "jwks_uri": jwks_uri},
            )

        except httpx.HTTPError as e:
            logger.error(
                "OIDC discovery failed",
                extra={
                    "issuer": issuer_url,
                    "discovery_url": discovery_url,
                    "error": str(e),
                },
            )
            raise

        # Step 2: Fetch JWKS from jwks_uri
        try:
            logger.debug("Fetching JWKS", extra={"jwks_uri": jwks_uri})
            jwks_response = await self._http_client.get(jwks_uri)
            jwks_response.raise_for_status()
            jwks = jwks_response.json()

            # Validate JWKS structure
            if "keys" not in jwks or not isinstance(jwks["keys"], list):
                raise ValueError(f"Invalid JWKS format from {jwks_uri}")

            key_count = len(jwks["keys"])
            logger.info(
                "JWKS fetched successfully",
                extra={
                    "issuer": issuer_url,
                    "jwks_uri": jwks_uri,
                    "key_count": key_count,
                },
            )

            return jwks

        except httpx.HTTPError as e:
            logger.error(
                "JWKS fetch failed",
                extra={
                    "issuer": issuer_url,
                    "jwks_uri": jwks_uri,
                    "error": str(e),
                },
            )
            raise

    async def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Get JWKS from Redis cache.

        Args:
            cache_key: Redis cache key (format: jwks:{issuer_url})

        Returns:
            Cached JWKS dictionary, or None if not found or Redis error

        Note:
            Redis failures are logged but don't raise exceptions - we gracefully
            fall back to fetching from the provider.
        """
        try:
            cached_data = await self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
            return None
        except redis.RedisError as e:
            logger.warning(
                "Redis cache read failed",
                extra={"cache_key": cache_key, "error": str(e)},
            )
            return None  # Fail gracefully, fetch from provider
        except json.JSONDecodeError as e:
            logger.warning(
                "Invalid JSON in Redis cache",
                extra={"cache_key": cache_key, "error": str(e)},
            )
            return None

    async def _set_in_cache(self, cache_key: str, jwks: Dict[str, Any]) -> None:
        """
        Set JWKS in Redis cache with TTL.

        Args:
            cache_key: Redis cache key
            jwks: JWKS dictionary to cache

        Note:
            Redis failures are logged but don't raise exceptions - caching is
            a performance optimization, not a critical operation.
        """
        try:
            await self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(jwks),
            )
            logger.debug(
                "JWKS cached successfully",
                extra={"cache_key": cache_key, "ttl": self.cache_ttl},
            )
        except redis.RedisError as e:
            logger.warning(
                "Redis cache write failed",
                extra={"cache_key": cache_key, "error": str(e)},
            )
            # Continue without caching - not a critical failure

    async def close(self) -> None:
        """
        Close HTTP client and cleanup resources.

        Should be called when the application shuts down to properly close
        the HTTP client connection pool.
        """
        await self._http_client.aclose()
        logger.debug("JWKS client closed")


# Singleton instance for application-wide use
_jwks_client: Optional[JWKSClient] = None


async def get_jwks_client() -> JWKSClient:
    """
    Get singleton JWKS client instance.

    Creates a singleton JWKS client on first call and reuses it for subsequent
    calls. This ensures we have a single Redis connection pool and HTTP client
    pool across the application.

    Returns:
        Initialized JWKSClient instance

    Example:
        >>> client = await get_jwks_client()
        >>> jwks = await client.get_jwks(issuer_url)
    """
    global _jwks_client

    if _jwks_client is None:
        # Initialize Redis client
        redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )

        _jwks_client = JWKSClient(
            redis_client=redis_client,
            cache_ttl=settings.JWKS_CACHE_TTL,
            http_timeout=settings.JWKS_HTTP_TIMEOUT,
        )

        logger.info(
            "JWKS client initialized",
            extra={
                "cache_ttl": settings.JWKS_CACHE_TTL,
                "http_timeout": settings.JWKS_HTTP_TIMEOUT,
                "redis_url": settings.REDIS_URL,
            },
        )

    return _jwks_client
