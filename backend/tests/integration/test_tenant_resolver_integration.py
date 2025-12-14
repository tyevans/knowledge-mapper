"""
Integration tests for tenant resolver service.

Tests tenant resolution with real database and Redis connections, including:
- End-to-end tenant resolution
- Cache hit/miss scenarios with real Redis
- Graceful degradation when Redis is unavailable
- Cache invalidation
"""

import pytest
from uuid import UUID

from app.core.database import AsyncSessionLocal, Base, engine
from app.models.tenant import Tenant
from app.schemas.tenant import TenantInfo, TenantInactiveError, TenantNotFoundError
from app.services.tenant_resolver import TenantResolver, get_tenant_resolver
from app.core.cache import get_redis_client, close_redis_client


class TestTenantResolverIntegration:
    """Integration tests for TenantResolver with real database and Redis."""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        """Setup and teardown for each test."""
        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield

        # Clean up
        # Close Redis connection
        await close_redis_client()

        # Drop tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.fixture
    async def test_tenant(self):
        """Create a test tenant in the database."""
        async with AsyncSessionLocal() as session:
            tenant = Tenant(
                slug="acme-corp", name="ACME Corporation", is_active=True
            )
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)
            return tenant

    @pytest.fixture
    async def inactive_tenant(self):
        """Create an inactive test tenant in the database."""
        async with AsyncSessionLocal() as session:
            tenant = Tenant(
                slug="inactive-corp",
                name="Inactive Corporation",
                is_active=False,
            )
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)
            return tenant

    @pytest.mark.asyncio
    async def test_resolve_by_id_from_database(self, test_tenant):
        """Test resolving tenant by ID from database (cache miss)."""
        resolver = TenantResolver(cache_ttl=60)

        async with AsyncSessionLocal() as session:
            tenant_info = await resolver.resolve_by_id(session, test_tenant.id)

            # Verify result
            assert tenant_info.id == test_tenant.id
            assert tenant_info.slug == "acme-corp"
            assert tenant_info.name == "ACME Corporation"
            assert tenant_info.is_active is True

    @pytest.mark.asyncio
    async def test_resolve_by_id_from_cache(self, test_tenant):
        """Test resolving tenant by ID from cache (cache hit)."""
        resolver = TenantResolver(cache_ttl=60)

        async with AsyncSessionLocal() as session:
            # First call - database query, populates cache
            tenant_info_1 = await resolver.resolve_by_id(session, test_tenant.id)

            # Second call - should hit cache
            tenant_info_2 = await resolver.resolve_by_id(session, test_tenant.id)

            # Verify both results are identical
            assert tenant_info_1.id == tenant_info_2.id
            assert tenant_info_1.slug == tenant_info_2.slug

    @pytest.mark.asyncio
    async def test_resolve_by_slug_from_database(self, test_tenant):
        """Test resolving tenant by slug from database."""
        resolver = TenantResolver(cache_ttl=60)

        async with AsyncSessionLocal() as session:
            tenant_info = await resolver.resolve_by_slug(session, "acme-corp")

            # Verify result
            assert tenant_info.id == test_tenant.id
            assert tenant_info.slug == "acme-corp"
            assert tenant_info.name == "ACME Corporation"

    @pytest.mark.asyncio
    async def test_resolve_by_slug_caches_both_keys(self, test_tenant):
        """Test that resolve_by_slug caches by both slug and ID."""
        resolver = TenantResolver(cache_ttl=60)

        async with AsyncSessionLocal() as session:
            # First call - resolve by slug (cache miss)
            await resolver.resolve_by_slug(session, "acme-corp")

            # Verify cache was populated for both slug and ID
            slug_cache_key = f"tenant:slug:acme-corp"
            id_cache_key = f"tenant:id:{test_tenant.id}"

            cached_by_slug = await resolver._get_from_cache(slug_cache_key)
            cached_by_id = await resolver._get_from_cache(id_cache_key)

            assert cached_by_slug is not None
            assert cached_by_id is not None
            assert cached_by_slug.id == cached_by_id.id

    @pytest.mark.asyncio
    async def test_resolve_by_slug_from_cache(self, test_tenant):
        """Test resolving tenant by slug from cache."""
        resolver = TenantResolver(cache_ttl=60)

        async with AsyncSessionLocal() as session:
            # First call - database query
            tenant_info_1 = await resolver.resolve_by_slug(session, "acme-corp")

            # Second call - should hit cache
            tenant_info_2 = await resolver.resolve_by_slug(session, "acme-corp")

            # Verify both results are identical
            assert tenant_info_1.id == tenant_info_2.id
            assert tenant_info_1.slug == tenant_info_2.slug

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_tenant_by_id(self):
        """Test resolving non-existent tenant by ID raises error."""
        resolver = TenantResolver(cache_ttl=60)
        fake_id = UUID("12345678-1234-1234-1234-123456789012")

        async with AsyncSessionLocal() as session:
            with pytest.raises(TenantNotFoundError, match=f"Tenant {fake_id} not found"):
                await resolver.resolve_by_id(session, fake_id)

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_tenant_by_slug(self):
        """Test resolving non-existent tenant by slug raises error."""
        resolver = TenantResolver(cache_ttl=60)

        async with AsyncSessionLocal() as session:
            with pytest.raises(
                TenantNotFoundError, match="Tenant 'nonexistent-slug' not found"
            ):
                await resolver.resolve_by_slug(session, "nonexistent-slug")

    @pytest.mark.asyncio
    async def test_resolve_inactive_tenant_requires_active(self, inactive_tenant):
        """Test resolving inactive tenant with require_active=True raises error."""
        resolver = TenantResolver(cache_ttl=60)

        async with AsyncSessionLocal() as session:
            with pytest.raises(TenantInactiveError, match="not active"):
                await resolver.resolve_by_id(
                    session, inactive_tenant.id, require_active=True
                )

    @pytest.mark.asyncio
    async def test_resolve_inactive_tenant_allow_inactive(self, inactive_tenant):
        """Test resolving inactive tenant with require_active=False succeeds."""
        resolver = TenantResolver(cache_ttl=60)

        async with AsyncSessionLocal() as session:
            tenant_info = await resolver.resolve_by_id(
                session, inactive_tenant.id, require_active=False
            )

            # Verify result
            assert tenant_info.id == inactive_tenant.id
            assert tenant_info.is_active is False

    @pytest.mark.asyncio
    async def test_resolve_by_subdomain_uses_slug(self, test_tenant):
        """Test subdomain resolution uses slug lookup."""
        resolver = TenantResolver(cache_ttl=60)

        async with AsyncSessionLocal() as session:
            # Subdomain resolution should use slug lookup
            tenant_info = await resolver.resolve_by_subdomain(session, "acme-corp")

            # Verify result
            assert tenant_info.id == test_tenant.id
            assert tenant_info.slug == "acme-corp"

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, test_tenant):
        """Test cache invalidation removes cached data."""
        resolver = TenantResolver(cache_ttl=60)

        async with AsyncSessionLocal() as session:
            # First call - populates cache
            await resolver.resolve_by_slug(session, "acme-corp")

            # Verify cache is populated
            slug_cache_key = f"tenant:slug:acme-corp"
            id_cache_key = f"tenant:id:{test_tenant.id}"

            cached_by_slug = await resolver._get_from_cache(slug_cache_key)
            cached_by_id = await resolver._get_from_cache(id_cache_key)

            assert cached_by_slug is not None
            assert cached_by_id is not None

            # Invalidate cache
            await resolver.invalidate_cache(test_tenant.id, "acme-corp")

            # Verify cache is cleared
            cached_by_slug_after = await resolver._get_from_cache(slug_cache_key)
            cached_by_id_after = await resolver._get_from_cache(id_cache_key)

            assert cached_by_slug_after is None
            assert cached_by_id_after is None

    @pytest.mark.asyncio
    async def test_cache_invalidation_partial(self, test_tenant):
        """Test cache invalidation with only tenant ID (no slug)."""
        resolver = TenantResolver(cache_ttl=60)

        async with AsyncSessionLocal() as session:
            # Populate cache by ID
            await resolver.resolve_by_id(session, test_tenant.id)

            # Verify cache is populated
            id_cache_key = f"tenant:id:{test_tenant.id}"
            cached_by_id = await resolver._get_from_cache(id_cache_key)
            assert cached_by_id is not None

            # Invalidate cache with only ID (no slug)
            await resolver.invalidate_cache(test_tenant.id)

            # Verify cache is cleared
            cached_by_id_after = await resolver._get_from_cache(id_cache_key)
            assert cached_by_id_after is None

    @pytest.mark.asyncio
    async def test_get_tenant_resolver_singleton(self, test_tenant):
        """Test get_tenant_resolver returns singleton instance."""
        # Reset global instance
        import app.services.tenant_resolver as resolver_module

        resolver_module._tenant_resolver = None

        # Get resolver instances
        resolver1 = get_tenant_resolver()
        resolver2 = get_tenant_resolver()

        # Verify singleton
        assert resolver1 is resolver2

        # Verify it works
        async with AsyncSessionLocal() as session:
            tenant_info = await resolver1.resolve_by_id(session, test_tenant.id)
            assert tenant_info.id == test_tenant.id

    @pytest.mark.asyncio
    async def test_multiple_tenants(self):
        """Test resolving multiple tenants."""
        resolver = TenantResolver(cache_ttl=60)

        # Create multiple tenants
        async with AsyncSessionLocal() as session:
            tenant1 = Tenant(
                slug="tenant1", name="Tenant 1", is_active=True
            )
            tenant2 = Tenant(
                slug="tenant2", name="Tenant 2", is_active=True
            )
            session.add(tenant1)
            session.add(tenant2)
            await session.commit()
            await session.refresh(tenant1)
            await session.refresh(tenant2)

            # Resolve both tenants
            tenant1_info = await resolver.resolve_by_slug(session, "tenant1")
            tenant2_info = await resolver.resolve_by_slug(session, "tenant2")

            # Verify results
            assert tenant1_info.slug == "tenant1"
            assert tenant2_info.slug == "tenant2"
            assert tenant1_info.id != tenant2_info.id

    @pytest.mark.asyncio
    async def test_cache_expiration_behavior(self, test_tenant):
        """Test cache behavior with very short TTL (simulates expiration)."""
        # Use very short TTL (1 second)
        resolver = TenantResolver(cache_ttl=1)

        async with AsyncSessionLocal() as session:
            # First call - populate cache
            tenant_info_1 = await resolver.resolve_by_id(session, test_tenant.id)

            # Immediately call again - should hit cache
            tenant_info_2 = await resolver.resolve_by_id(session, test_tenant.id)

            # Verify both results are identical
            assert tenant_info_1.id == tenant_info_2.id

            # Wait for cache to expire (1 second + buffer)
            import asyncio

            await asyncio.sleep(1.5)

            # Call again - cache should be expired, queries database
            tenant_info_3 = await resolver.resolve_by_id(session, test_tenant.id)

            # Result should still be correct
            assert tenant_info_3.id == test_tenant.id

    @pytest.mark.asyncio
    async def test_redis_graceful_degradation(self, test_tenant):
        """Test graceful degradation when Redis is unavailable."""
        # Create resolver
        resolver = TenantResolver(cache_ttl=60)

        # Close Redis connection to simulate unavailability
        await close_redis_client()

        # Reset resolver's Redis client
        resolver.redis = None

        async with AsyncSessionLocal() as session:
            # Should still work by querying database
            tenant_info = await resolver.resolve_by_id(session, test_tenant.id)

            # Verify result
            assert tenant_info.id == test_tenant.id
            assert tenant_info.slug == "acme-corp"


class TestTenantInfoSerialization:
    """Test TenantInfo serialization for caching."""

    @pytest.mark.asyncio
    async def test_tenant_info_json_serialization(self):
        """Test TenantInfo can be serialized to/from JSON."""
        from datetime import datetime
        from uuid import uuid4

        tenant_id = uuid4()
        now = datetime.utcnow()

        # Create TenantInfo
        tenant_info = TenantInfo(
            id=tenant_id,
            slug="test-tenant",
            name="Test Tenant",
            is_active=True,
            created_at=now,
            updated_at=now,
            settings={"key": "value"},
        )

        # Serialize to JSON
        tenant_json = tenant_info.model_dump_json()

        # Deserialize from JSON
        import json

        tenant_dict = json.loads(tenant_json)
        tenant_info_2 = TenantInfo(**tenant_dict)

        # Verify roundtrip
        assert tenant_info_2.id == tenant_id
        assert tenant_info_2.slug == "test-tenant"
        assert tenant_info_2.name == "Test Tenant"
        assert tenant_info_2.is_active is True
        assert tenant_info_2.settings == {"key": "value"}

    @pytest.mark.asyncio
    async def test_tenant_info_from_orm_model(self):
        """Test TenantInfo can be created from SQLAlchemy Tenant model."""
        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        try:
            async with AsyncSessionLocal() as session:
                # Create Tenant model
                tenant = Tenant(
                    slug="orm-tenant",
                    name="ORM Tenant",
                    is_active=True,
                    settings={"feature": "enabled"},
                )
                session.add(tenant)
                await session.commit()
                await session.refresh(tenant)

                # Convert to TenantInfo using model_validate
                tenant_info = TenantInfo.model_validate(tenant)

                # Verify conversion
                assert tenant_info.id == tenant.id
                assert tenant_info.slug == "orm-tenant"
                assert tenant_info.name == "ORM Tenant"
                assert tenant_info.is_active is True
                assert tenant_info.settings == {"feature": "enabled"}

        finally:
            # Clean up
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
