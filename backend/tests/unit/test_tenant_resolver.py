"""
Unit tests for tenant resolver service.

Tests tenant resolution by ID, slug, and subdomain with cache hit/miss scenarios,
error handling, and cache invalidation.
"""

import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.schemas.tenant import TenantInfo, TenantInactiveError, TenantNotFoundError
from app.services.tenant_resolver import TenantResolver


class TestTenantResolver:
    """Test suite for TenantResolver service."""

    @pytest.fixture
    def tenant_resolver(self):
        """Create a TenantResolver instance for testing."""
        return TenantResolver(cache_ttl=60)

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def sample_tenant_dict(self):
        """Sample tenant data as dictionary."""
        tenant_id = uuid4()
        now = datetime.utcnow()
        return {
            "id": tenant_id,
            "slug": "acme-corp",
            "name": "ACME Corporation",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "settings": {"feature_flags": {"advanced_mode": True}},
        }

    @pytest.fixture
    def sample_tenant_info(self, sample_tenant_dict):
        """Sample TenantInfo object."""
        return TenantInfo(**sample_tenant_dict)

    @pytest.fixture
    def mock_tenant_model(self, sample_tenant_dict):
        """Mock SQLAlchemy Tenant model."""
        tenant = Mock()
        tenant.id = sample_tenant_dict["id"]
        tenant.slug = sample_tenant_dict["slug"]
        tenant.name = sample_tenant_dict["name"]
        tenant.is_active = sample_tenant_dict["is_active"]
        tenant.created_at = sample_tenant_dict["created_at"]
        tenant.updated_at = sample_tenant_dict["updated_at"]
        tenant.settings = sample_tenant_dict["settings"]
        return tenant


class TestResolveById(TestTenantResolver):
    """Tests for resolve_by_id method."""

    @pytest.mark.asyncio
    async def test_resolve_by_id_cache_miss(
        self, tenant_resolver, mock_session, mock_tenant_model, sample_tenant_info
    ):
        """Test resolving tenant by ID with cache miss (database query)."""
        tenant_id = mock_tenant_model.id

        # Mock database query
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_tenant_model
        mock_session.execute.return_value = mock_result

        # Mock cache (cache miss)
        with patch.object(
            tenant_resolver, "_get_from_cache", new_callable=AsyncMock, return_value=None
        ):
            with patch.object(
                tenant_resolver, "_set_in_cache", new_callable=AsyncMock
            ) as mock_set_cache:
                tenant_info = await tenant_resolver.resolve_by_id(
                    mock_session, tenant_id
                )

                # Verify result
                assert tenant_info.id == tenant_id
                assert tenant_info.slug == "acme-corp"
                assert tenant_info.name == "ACME Corporation"
                assert tenant_info.is_active is True

                # Verify database was queried
                mock_session.execute.assert_called_once()

                # Verify cache was set
                mock_set_cache.assert_called_once()
                cache_key = f"tenant:id:{tenant_id}"
                assert mock_set_cache.call_args[0][0] == cache_key

    @pytest.mark.asyncio
    async def test_resolve_by_id_cache_hit(
        self, tenant_resolver, mock_session, sample_tenant_info
    ):
        """Test resolving tenant by ID with cache hit (no database query)."""
        tenant_id = sample_tenant_info.id

        # Mock cache (cache hit)
        with patch.object(
            tenant_resolver,
            "_get_from_cache",
            new_callable=AsyncMock,
            return_value=sample_tenant_info,
        ):
            tenant_info = await tenant_resolver.resolve_by_id(mock_session, tenant_id)

            # Verify result
            assert tenant_info.id == tenant_id
            assert tenant_info.slug == "acme-corp"

            # Verify database was NOT queried (cache hit)
            mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_by_id_not_found(self, tenant_resolver, mock_session):
        """Test resolving non-existent tenant raises TenantNotFoundError."""
        fake_id = uuid4()

        # Mock database query (not found)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Mock cache (cache miss)
        with patch.object(
            tenant_resolver, "_get_from_cache", new_callable=AsyncMock, return_value=None
        ):
            with pytest.raises(TenantNotFoundError, match=f"Tenant {fake_id} not found"):
                await tenant_resolver.resolve_by_id(mock_session, fake_id)

    @pytest.mark.asyncio
    async def test_resolve_by_id_inactive_tenant_requires_active(
        self, tenant_resolver, mock_session
    ):
        """Test resolving inactive tenant with require_active=True raises error."""
        tenant_id = uuid4()
        now = datetime.utcnow()

        # Create inactive tenant
        inactive_tenant = Mock()
        inactive_tenant.id = tenant_id
        inactive_tenant.slug = "inactive-corp"
        inactive_tenant.name = "Inactive Corp"
        inactive_tenant.is_active = False
        inactive_tenant.created_at = now
        inactive_tenant.updated_at = now
        inactive_tenant.settings = {}

        # Mock database query
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = inactive_tenant
        mock_session.execute.return_value = mock_result

        # Mock cache (cache miss)
        with patch.object(
            tenant_resolver, "_get_from_cache", new_callable=AsyncMock, return_value=None
        ):
            with pytest.raises(TenantInactiveError, match="not active"):
                await tenant_resolver.resolve_by_id(
                    mock_session, tenant_id, require_active=True
                )

    @pytest.mark.asyncio
    async def test_resolve_by_id_inactive_tenant_allow_inactive(
        self, tenant_resolver, mock_session
    ):
        """Test resolving inactive tenant with require_active=False succeeds."""
        tenant_id = uuid4()
        now = datetime.utcnow()

        # Create inactive tenant
        inactive_tenant = Mock()
        inactive_tenant.id = tenant_id
        inactive_tenant.slug = "inactive-corp"
        inactive_tenant.name = "Inactive Corp"
        inactive_tenant.is_active = False
        inactive_tenant.created_at = now
        inactive_tenant.updated_at = now
        inactive_tenant.settings = {}

        # Mock database query
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = inactive_tenant
        mock_session.execute.return_value = mock_result

        # Mock cache
        with patch.object(
            tenant_resolver, "_get_from_cache", new_callable=AsyncMock, return_value=None
        ):
            with patch.object(
                tenant_resolver, "_set_in_cache", new_callable=AsyncMock
            ):
                tenant_info = await tenant_resolver.resolve_by_id(
                    mock_session, tenant_id, require_active=False
                )

                # Should succeed
                assert tenant_info.id == tenant_id
                assert tenant_info.is_active is False

    @pytest.mark.asyncio
    async def test_resolve_by_id_inactive_from_cache_raises_error(
        self, tenant_resolver, mock_session
    ):
        """Test cached inactive tenant raises error when require_active=True."""
        tenant_id = uuid4()
        now = datetime.utcnow()

        # Create cached inactive tenant info
        cached_tenant = TenantInfo(
            id=tenant_id,
            slug="inactive-corp",
            name="Inactive Corp",
            is_active=False,
            created_at=now,
            updated_at=now,
            settings={},
        )

        # Mock cache (cache hit with inactive tenant)
        with patch.object(
            tenant_resolver,
            "_get_from_cache",
            new_callable=AsyncMock,
            return_value=cached_tenant,
        ):
            with pytest.raises(TenantInactiveError, match="not active"):
                await tenant_resolver.resolve_by_id(
                    mock_session, tenant_id, require_active=True
                )


class TestResolveBySlug(TestTenantResolver):
    """Tests for resolve_by_slug method."""

    @pytest.mark.asyncio
    async def test_resolve_by_slug_cache_miss(
        self, tenant_resolver, mock_session, mock_tenant_model
    ):
        """Test resolving tenant by slug with cache miss."""
        slug = "acme-corp"

        # Mock database query
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_tenant_model
        mock_session.execute.return_value = mock_result

        # Mock cache (cache miss)
        with patch.object(
            tenant_resolver, "_get_from_cache", new_callable=AsyncMock, return_value=None
        ):
            with patch.object(
                tenant_resolver, "_set_in_cache", new_callable=AsyncMock
            ) as mock_set_cache:
                tenant_info = await tenant_resolver.resolve_by_slug(mock_session, slug)

                # Verify result
                assert tenant_info.slug == slug
                assert tenant_info.is_active is True

                # Verify database was queried
                mock_session.execute.assert_called_once()

                # Verify cache was set for BOTH slug and ID
                assert mock_set_cache.call_count == 2
                call_args_list = [call[0][0] for call in mock_set_cache.call_args_list]
                assert f"tenant:slug:{slug}" in call_args_list
                assert f"tenant:id:{mock_tenant_model.id}" in call_args_list

    @pytest.mark.asyncio
    async def test_resolve_by_slug_cache_hit(
        self, tenant_resolver, mock_session, sample_tenant_info
    ):
        """Test resolving tenant by slug with cache hit."""
        slug = "acme-corp"

        # Mock cache (cache hit)
        with patch.object(
            tenant_resolver,
            "_get_from_cache",
            new_callable=AsyncMock,
            return_value=sample_tenant_info,
        ):
            tenant_info = await tenant_resolver.resolve_by_slug(mock_session, slug)

            # Verify result
            assert tenant_info.slug == slug

            # Verify database was NOT queried
            mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_by_slug_not_found(self, tenant_resolver, mock_session):
        """Test resolving non-existent slug raises TenantNotFoundError."""
        slug = "nonexistent-slug"

        # Mock database query (not found)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Mock cache (cache miss)
        with patch.object(
            tenant_resolver, "_get_from_cache", new_callable=AsyncMock, return_value=None
        ):
            with pytest.raises(
                TenantNotFoundError, match=f"Tenant '{slug}' not found"
            ):
                await tenant_resolver.resolve_by_slug(mock_session, slug)

    @pytest.mark.asyncio
    async def test_resolve_by_slug_inactive_tenant(
        self, tenant_resolver, mock_session
    ):
        """Test resolving inactive tenant by slug with require_active=True."""
        slug = "inactive-corp"
        now = datetime.utcnow()

        # Create inactive tenant
        inactive_tenant = Mock()
        inactive_tenant.id = uuid4()
        inactive_tenant.slug = slug
        inactive_tenant.name = "Inactive Corp"
        inactive_tenant.is_active = False
        inactive_tenant.created_at = now
        inactive_tenant.updated_at = now
        inactive_tenant.settings = {}

        # Mock database query
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = inactive_tenant
        mock_session.execute.return_value = mock_result

        # Mock cache (cache miss)
        with patch.object(
            tenant_resolver, "_get_from_cache", new_callable=AsyncMock, return_value=None
        ):
            with pytest.raises(TenantInactiveError, match="not active"):
                await tenant_resolver.resolve_by_slug(
                    mock_session, slug, require_active=True
                )


class TestResolveBySubdomain(TestTenantResolver):
    """Tests for resolve_by_subdomain method."""

    @pytest.mark.asyncio
    async def test_resolve_by_subdomain_uses_slug_lookup(
        self, tenant_resolver, mock_session, sample_tenant_info
    ):
        """Test subdomain resolution uses slug lookup (future enhancement)."""
        subdomain = "acme"

        # Mock resolve_by_slug to verify it's called
        with patch.object(
            tenant_resolver,
            "resolve_by_slug",
            new_callable=AsyncMock,
            return_value=sample_tenant_info,
        ) as mock_resolve_by_slug:
            tenant_info = await tenant_resolver.resolve_by_subdomain(
                mock_session, subdomain
            )

            # Verify resolve_by_slug was called with subdomain
            mock_resolve_by_slug.assert_called_once_with(
                mock_session, subdomain, True
            )

            # Verify result
            assert tenant_info == sample_tenant_info


class TestCacheInvalidation(TestTenantResolver):
    """Tests for cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_cache_with_slug(self, tenant_resolver):
        """Test cache invalidation removes both ID and slug keys."""
        tenant_id = uuid4()
        slug = "acme-corp"

        # Mock Redis
        mock_redis = AsyncMock()
        with patch.object(
            tenant_resolver, "_get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            await tenant_resolver.invalidate_cache(tenant_id, slug)

            # Verify Redis delete was called with both keys
            mock_redis.delete.assert_called_once()
            call_args = mock_redis.delete.call_args[0]
            assert f"tenant:id:{tenant_id}" in call_args
            assert f"tenant:slug:{slug}" in call_args

    @pytest.mark.asyncio
    async def test_invalidate_cache_without_slug(self, tenant_resolver):
        """Test cache invalidation with only tenant ID."""
        tenant_id = uuid4()

        # Mock Redis
        mock_redis = AsyncMock()
        with patch.object(
            tenant_resolver, "_get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            await tenant_resolver.invalidate_cache(tenant_id)

            # Verify Redis delete was called with only ID key
            mock_redis.delete.assert_called_once()
            call_args = mock_redis.delete.call_args[0]
            assert f"tenant:id:{tenant_id}" in call_args
            assert len(call_args) == 1

    @pytest.mark.asyncio
    async def test_invalidate_cache_redis_unavailable(self, tenant_resolver):
        """Test cache invalidation handles Redis unavailable gracefully."""
        tenant_id = uuid4()
        slug = "acme-corp"

        # Mock Redis unavailable (returns None)
        with patch.object(
            tenant_resolver, "_get_redis", new_callable=AsyncMock, return_value=None
        ):
            # Should not raise exception
            await tenant_resolver.invalidate_cache(tenant_id, slug)

    @pytest.mark.asyncio
    async def test_invalidate_cache_redis_error(self, tenant_resolver):
        """Test cache invalidation handles Redis errors gracefully."""
        tenant_id = uuid4()
        slug = "acme-corp"

        # Mock Redis that raises exception on delete
        mock_redis = AsyncMock()
        mock_redis.delete.side_effect = Exception("Redis error")

        with patch.object(
            tenant_resolver, "_get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            # Should not raise exception (logs warning instead)
            await tenant_resolver.invalidate_cache(tenant_id, slug)


class TestCacheOperations(TestTenantResolver):
    """Tests for internal cache operations."""

    @pytest.mark.asyncio
    async def test_get_from_cache_success(self, tenant_resolver, sample_tenant_info):
        """Test successful cache retrieval."""
        cache_key = "tenant:id:12345"

        # Mock Redis
        mock_redis = AsyncMock()
        tenant_json = sample_tenant_info.model_dump_json()
        mock_redis.get.return_value = tenant_json

        with patch.object(
            tenant_resolver, "_get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            result = await tenant_resolver._get_from_cache(cache_key)

            # Verify result
            assert result is not None
            assert result.id == sample_tenant_info.id
            assert result.slug == sample_tenant_info.slug

    @pytest.mark.asyncio
    async def test_get_from_cache_miss(self, tenant_resolver):
        """Test cache miss returns None."""
        cache_key = "tenant:id:12345"

        # Mock Redis (cache miss)
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch.object(
            tenant_resolver, "_get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            result = await tenant_resolver._get_from_cache(cache_key)

            # Verify result is None
            assert result is None

    @pytest.mark.asyncio
    async def test_get_from_cache_redis_unavailable(self, tenant_resolver):
        """Test cache get when Redis unavailable returns None."""
        cache_key = "tenant:id:12345"

        # Mock Redis unavailable
        with patch.object(
            tenant_resolver, "_get_redis", new_callable=AsyncMock, return_value=None
        ):
            result = await tenant_resolver._get_from_cache(cache_key)

            # Verify result is None (graceful degradation)
            assert result is None

    @pytest.mark.asyncio
    async def test_get_from_cache_invalid_json(self, tenant_resolver):
        """Test cache get with invalid JSON returns None."""
        cache_key = "tenant:id:12345"

        # Mock Redis with invalid JSON
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "invalid json"

        with patch.object(
            tenant_resolver, "_get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            result = await tenant_resolver._get_from_cache(cache_key)

            # Verify result is None (graceful degradation)
            assert result is None

    @pytest.mark.asyncio
    async def test_set_in_cache_success(self, tenant_resolver, sample_tenant_info):
        """Test successful cache set."""
        cache_key = "tenant:id:12345"

        # Mock Redis
        mock_redis = AsyncMock()

        with patch.object(
            tenant_resolver, "_get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            await tenant_resolver._set_in_cache(cache_key, sample_tenant_info)

            # Verify Redis setex was called
            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args[0]
            assert call_args[0] == cache_key
            assert call_args[1] == tenant_resolver.cache_ttl
            # Verify JSON is valid
            cached_json = call_args[2]
            tenant_dict = json.loads(cached_json)
            assert tenant_dict["slug"] == sample_tenant_info.slug

    @pytest.mark.asyncio
    async def test_set_in_cache_redis_unavailable(
        self, tenant_resolver, sample_tenant_info
    ):
        """Test cache set when Redis unavailable does not raise error."""
        cache_key = "tenant:id:12345"

        # Mock Redis unavailable
        with patch.object(
            tenant_resolver, "_get_redis", new_callable=AsyncMock, return_value=None
        ):
            # Should not raise exception
            await tenant_resolver._set_in_cache(cache_key, sample_tenant_info)

    @pytest.mark.asyncio
    async def test_set_in_cache_redis_error(self, tenant_resolver, sample_tenant_info):
        """Test cache set handles Redis errors gracefully."""
        cache_key = "tenant:id:12345"

        # Mock Redis that raises exception
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = Exception("Redis error")

        with patch.object(
            tenant_resolver, "_get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            # Should not raise exception (logs warning instead)
            await tenant_resolver._set_in_cache(cache_key, sample_tenant_info)


class TestGetTenantResolver:
    """Tests for get_tenant_resolver singleton factory."""

    def test_get_tenant_resolver_returns_singleton(self):
        """Test that get_tenant_resolver returns the same instance."""
        from app.services.tenant_resolver import (
            get_tenant_resolver,
            _tenant_resolver,
        )

        # Reset global instance
        import app.services.tenant_resolver as resolver_module

        resolver_module._tenant_resolver = None

        # Get first instance
        resolver1 = get_tenant_resolver()

        # Get second instance
        resolver2 = get_tenant_resolver()

        # Verify they are the same instance
        assert resolver1 is resolver2

    def test_get_tenant_resolver_uses_config(self):
        """Test that get_tenant_resolver uses configuration."""
        from app.services.tenant_resolver import get_tenant_resolver
        from app.core.config import settings

        # Reset global instance
        import app.services.tenant_resolver as resolver_module

        resolver_module._tenant_resolver = None

        # Mock settings.TENANT_CACHE_TTL
        with patch.object(settings, "TENANT_CACHE_TTL", 7200):
            resolver = get_tenant_resolver()

            # Verify cache_ttl from config
            assert resolver.cache_ttl == 7200
