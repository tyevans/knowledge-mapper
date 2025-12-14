"""
Tenant Resolver Service with Redis caching.

Provides tenant information lookup by ID, slug, or subdomain with intelligent
caching to reduce database load. Uses cache-aside pattern where cache is checked
first, and database is queried on cache miss.

This service is the central authority for tenant information retrieval and is
used by middleware, dependencies, and other services to validate tenant existence
and activity status.
"""

import json
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis_client
from app.models.tenant import Tenant
from app.schemas.tenant import TenantInfo, TenantInactiveError, TenantNotFoundError

logger = logging.getLogger(__name__)


class TenantResolver:
    """
    Service for resolving tenant information with caching.

    Provides multiple resolution strategies (by ID, slug, subdomain) and caches
    results in Redis to minimize database queries. Implements cache-aside pattern
    with graceful degradation if Redis is unavailable.

    The resolver caches tenant data for a configurable TTL (default 1 hour) and
    provides cache invalidation for tenant updates.

    Attributes:
        cache_ttl: Cache time-to-live in seconds (default: 3600)
        redis: Redis client (lazy-loaded on first use)

    Example:
        >>> resolver = TenantResolver(cache_ttl=3600)
        >>> tenant = await resolver.resolve_by_slug(session, "acme-corp")
        >>> print(f"Found tenant: {tenant.name}")
    """

    def __init__(self, cache_ttl: int = 3600):
        """
        Initialize tenant resolver.

        Args:
            cache_ttl: Cache time-to-live in seconds (default: 1 hour)
        """
        self.cache_ttl = cache_ttl
        self.redis = None  # Lazy-loaded on first use

    async def _get_redis(self):
        """
        Get Redis client with lazy initialization.

        Returns:
            Redis client or None if Redis unavailable
        """
        if self.redis is None:
            self.redis = await get_redis_client()
        return self.redis

    async def resolve_by_id(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        require_active: bool = True,
    ) -> TenantInfo:
        """
        Resolve tenant by UUID with caching.

        This is the primary resolution method when you have a tenant ID from a JWT
        token or database foreign key. It checks the cache first and falls back to
        database query on cache miss.

        Args:
            session: Database session
            tenant_id: Tenant UUID
            require_active: If True, raise error if tenant is inactive

        Returns:
            TenantInfo object with tenant details

        Raises:
            TenantNotFoundError: If tenant does not exist
            TenantInactiveError: If tenant is not active (when require_active=True)

        Example:
            >>> tenant_id = UUID("...")
            >>> tenant = await resolver.resolve_by_id(session, tenant_id)
            >>> print(f"Tenant: {tenant.name} ({tenant.slug})")
        """
        cache_key = f"tenant:id:{tenant_id}"

        # Try cache first
        tenant_info = await self._get_from_cache(cache_key)
        if tenant_info:
            logger.debug(
                f"Tenant resolved from cache: tenant_id={tenant_id}, cache_key={cache_key}"
            )
            if require_active and not tenant_info.is_active:
                raise TenantInactiveError(f"Tenant {tenant_id} is not active")
            return tenant_info

        # Cache miss - query database
        result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()

        if tenant is None:
            logger.error(f"Tenant not found: tenant_id={tenant_id}")
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")

        tenant_info = TenantInfo.model_validate(tenant)

        # Cache the result
        await self._set_in_cache(cache_key, tenant_info)

        logger.info(
            f"Tenant resolved from DB: tenant_id={tenant_id}, "
            f"tenant_slug={tenant_info.slug}, is_active={tenant_info.is_active}"
        )

        if require_active and not tenant_info.is_active:
            raise TenantInactiveError(f"Tenant {tenant_id} is not active")

        return tenant_info

    async def resolve_by_slug(
        self,
        session: AsyncSession,
        slug: str,
        require_active: bool = True,
    ) -> TenantInfo:
        """
        Resolve tenant by slug with caching.

        This method is used for slug-based tenant resolution, such as from URLs
        or API requests that use the tenant slug as an identifier. It caches by
        both slug and ID to optimize future lookups.

        Args:
            session: Database session
            slug: Tenant slug (e.g., "acme-corp")
            require_active: If True, raise error if tenant is inactive

        Returns:
            TenantInfo object with tenant details

        Raises:
            TenantNotFoundError: If tenant does not exist
            TenantInactiveError: If tenant is not active (when require_active=True)

        Example:
            >>> tenant = await resolver.resolve_by_slug(session, "acme-corp")
            >>> print(f"Tenant ID: {tenant.id}")
        """
        cache_key = f"tenant:slug:{slug}"

        # Try cache first
        tenant_info = await self._get_from_cache(cache_key)
        if tenant_info:
            logger.debug(
                f"Tenant resolved from cache: tenant_slug={slug}, cache_key={cache_key}"
            )
            if require_active and not tenant_info.is_active:
                raise TenantInactiveError(f"Tenant '{slug}' is not active")
            return tenant_info

        # Cache miss - query database
        result = await session.execute(select(Tenant).where(Tenant.slug == slug))
        tenant = result.scalar_one_or_none()

        if tenant is None:
            logger.error(f"Tenant not found: tenant_slug={slug}")
            raise TenantNotFoundError(f"Tenant '{slug}' not found")

        tenant_info = TenantInfo.model_validate(tenant)

        # Cache by both slug and ID for optimal lookups
        await self._set_in_cache(cache_key, tenant_info)
        await self._set_in_cache(f"tenant:id:{tenant_info.id}", tenant_info)

        logger.info(
            f"Tenant resolved from DB: tenant_id={tenant_info.id}, "
            f"tenant_slug={slug}, is_active={tenant_info.is_active}"
        )

        if require_active and not tenant_info.is_active:
            raise TenantInactiveError(f"Tenant '{slug}' is not active")

        return tenant_info

    async def resolve_by_subdomain(
        self,
        session: AsyncSession,
        subdomain: str,
        require_active: bool = True,
    ) -> TenantInfo:
        """
        Resolve tenant by subdomain (future enhancement).

        For custom domain support: acme.knowledge-mapper.example.com -> acme-corp tenant.
        Currently, this is a simple wrapper that uses slug lookup, but can be
        enhanced to support custom domain mapping in the future.

        Args:
            session: Database session
            subdomain: Subdomain (e.g., "acme")
            require_active: If True, raise error if tenant is inactive

        Returns:
            TenantInfo object with tenant details

        Raises:
            TenantNotFoundError: If tenant does not exist
            TenantInactiveError: If tenant is not active

        Note:
            Future enhancement: Map subdomain to tenant slug or custom domain table.
            For now, assume subdomain == slug.

        Example:
            >>> tenant = await resolver.resolve_by_subdomain(session, "acme")
            >>> print(f"Subdomain 'acme' maps to: {tenant.slug}")
        """
        logger.warning(
            f"Subdomain resolution not fully implemented, using slug lookup: subdomain={subdomain}"
        )
        return await self.resolve_by_slug(session, subdomain, require_active)

    async def invalidate_cache(self, tenant_id: UUID, slug: Optional[str] = None):
        """
        Invalidate cached tenant data.

        Call this when tenant data changes (update, deactivation, etc.) to ensure
        the cache stays consistent with the database. This removes cache entries
        for both the tenant ID and slug (if provided).

        Args:
            tenant_id: Tenant UUID to invalidate
            slug: Tenant slug to invalidate (optional)

        Example:
            >>> # After updating tenant in database
            >>> await resolver.invalidate_cache(tenant_id, slug="acme-corp")
        """
        redis = await self._get_redis()
        if redis is None:
            return

        keys_to_delete = [f"tenant:id:{tenant_id}"]
        if slug:
            keys_to_delete.append(f"tenant:slug:{slug}")

        try:
            await redis.delete(*keys_to_delete)
            logger.info(
                f"Tenant cache invalidated: tenant_id={tenant_id}, slug={slug}, "
                f"keys_deleted={len(keys_to_delete)}"
            )
        except Exception as e:
            logger.warning(
                f"Cache invalidation failed: tenant_id={tenant_id}, slug={slug}, "
                f"error={str(e)}, error_type={type(e).__name__}"
            )

    async def _get_from_cache(self, cache_key: str) -> Optional[TenantInfo]:
        """
        Get tenant info from Redis cache.

        Args:
            cache_key: Redis key (format: tenant:id:{uuid} or tenant:slug:{slug})

        Returns:
            TenantInfo or None if cache miss or Redis error

        Note:
            Redis failures are logged but don't raise exceptions - we gracefully
            fall back to database queries.
        """
        redis = await self._get_redis()
        if redis is None:
            return None

        try:
            cached_data = await redis.get(cache_key)
            if cached_data:
                tenant_dict = json.loads(cached_data)
                return TenantInfo(**tenant_dict)
        except Exception as e:
            logger.warning(
                f"Cache get failed: cache_key={cache_key}, "
                f"error={str(e)}, error_type={type(e).__name__}"
            )
        return None

    async def _set_in_cache(self, cache_key: str, tenant_info: TenantInfo):
        """
        Set tenant info in Redis cache with TTL.

        Args:
            cache_key: Redis key
            tenant_info: Tenant information to cache

        Note:
            Redis failures are logged but don't raise exceptions - caching is
            a performance optimization, not a critical operation.
        """
        redis = await self._get_redis()
        if redis is None:
            return

        try:
            # Serialize TenantInfo to JSON
            tenant_json = tenant_info.model_dump_json()
            await redis.setex(cache_key, self.cache_ttl, tenant_json)
            logger.debug(
                f"Tenant cached: cache_key={cache_key}, ttl={self.cache_ttl}"
            )
        except Exception as e:
            logger.warning(
                f"Cache set failed: cache_key={cache_key}, "
                f"error={str(e)}, error_type={type(e).__name__}"
            )


# Global resolver instance (singleton pattern)
_tenant_resolver: Optional[TenantResolver] = None


def get_tenant_resolver() -> TenantResolver:
    """
    Get global tenant resolver instance.

    Creates a singleton TenantResolver on first call and reuses it for subsequent
    calls. This ensures consistent configuration and avoids creating multiple
    Redis connections.

    Returns:
        TenantResolver singleton

    Example:
        >>> resolver = get_tenant_resolver()
        >>> tenant = await resolver.resolve_by_id(session, tenant_id)
    """
    global _tenant_resolver
    if _tenant_resolver is None:
        from app.core.config import settings

        cache_ttl = getattr(settings, "TENANT_CACHE_TTL", 3600)
        _tenant_resolver = TenantResolver(cache_ttl=cache_ttl)
    return _tenant_resolver
