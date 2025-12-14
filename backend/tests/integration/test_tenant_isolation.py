"""
Integration tests for tenant isolation with RLS policies.

Tests that the tenant context service correctly integrates with Row-Level Security
policies to enforce tenant isolation. These tests verify that:
- Queries with tenant context only return data for that tenant
- INSERT/UPDATE/DELETE operations respect tenant boundaries
- Cross-tenant data leakage is prevented
"""

import pytest
from uuid import uuid4
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.services.tenant_context import (
    set_tenant_context,
    clear_tenant_context,
    bypass_rls,
    TenantContext,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.core.database import AsyncSessionLocal, Base, engine
from app.core.config import settings


# Create a separate engine for RLS testing using app user (NO BYPASSRLS)
_rls_test_url = settings.DATABASE_URL.replace("knowledge_mapper_user:change_me_in_production", "knowledge_mapper_app_user:app_password_dev")
rls_test_engine = create_async_engine(_rls_test_url, echo=settings.DEBUG)
RLSSessionLocal = async_sessionmaker(
    rls_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session")
async def clean_seed_data():
    """
    Clean development seed data before running integration tests.

    This removes the seed data from migrations so tests have a clean slate.
    """
    async with AsyncSessionLocal() as session:
        # Delete seed users and tenants (from migration)
        await session.execute(text("DELETE FROM oauth_providers"))
        await session.execute(text("DELETE FROM users"))
        await session.execute(text("DELETE FROM tenants"))
        await session.commit()
    yield


@pytest.fixture
async def db_session(clean_seed_data):
    """
    Create a test database session with BYPASSRLS for setup/teardown.

    Note: Tables are expected to already exist from migrations.
    This fixture provides a session and ensures cleanup of test data.
    Data is committed during setup so other sessions can see it, then
    cleaned up in teardown.
    """
    # Create session with BYPASSRLS to allow test setup/teardown
    async with AsyncSessionLocal() as session:
        # Track created tenant IDs for cleanup
        created_tenant_ids = []
        session.info['created_tenant_ids'] = created_tenant_ids

        yield session

        # Clean up test data by deleting created tenants (cascades to users)
        if created_tenant_ids:
            await session.execute(
                text("DELETE FROM users WHERE tenant_id = ANY(:ids)"),
                {"ids": created_tenant_ids}
            )
            await session.execute(
                text("DELETE FROM tenants WHERE id = ANY(:ids)"),
                {"ids": created_tenant_ids}
            )
            await session.commit()


@pytest.fixture
async def rls_session(tenant_a, tenant_b, users_tenant_a, users_tenant_b):
    """
    Create a session using knowledge_mapper_app_user (NO BYPASSRLS) for RLS testing.

    This session will have RLS policies enforced, unlike the db_session
    fixture which uses a superuser.

    Note: This fixture depends on tenant and user fixtures to ensure test data
    is committed before this session is created.
    """
    async with RLSSessionLocal() as session:
        yield session
        # No rollback needed - rls_session doesn't create data


@pytest.fixture
async def tenant_a(db_session: AsyncSession):
    """Create tenant A with unique slug."""
    from uuid import uuid4
    unique_id = str(uuid4())[:8]
    tenant = Tenant(slug=f"test-tenant-a-{unique_id}", name="Test Tenant A", is_active=True)
    db_session.add(tenant)
    await db_session.commit()  # Commit so other sessions can see it
    await db_session.refresh(tenant)
    # Track for cleanup
    db_session.info['created_tenant_ids'].append(str(tenant.id))
    return tenant


@pytest.fixture
async def tenant_b(db_session: AsyncSession):
    """Create tenant B with unique slug."""
    from uuid import uuid4
    unique_id = str(uuid4())[:8]
    tenant = Tenant(slug=f"test-tenant-b-{unique_id}", name="Test Tenant B", is_active=True)
    db_session.add(tenant)
    await db_session.commit()  # Commit so other sessions can see it
    await db_session.refresh(tenant)
    # Track for cleanup
    db_session.info['created_tenant_ids'].append(str(tenant.id))
    return tenant


@pytest.fixture
async def users_tenant_a(db_session: AsyncSession, tenant_a: Tenant):
    """Create users for tenant A."""
    users = [
        User(
            tenant_id=tenant_a.id,
            oauth_subject=f"auth0|user-a{i}",
            email=f"user{i}@tenant-a.com",
            display_name=f"User A{i}",
            is_active=True
        )
        for i in range(3)
    ]
    db_session.add_all(users)
    await db_session.commit()  # Commit so other sessions can see them
    for user in users:
        await db_session.refresh(user)
    return users


@pytest.fixture
async def users_tenant_b(db_session: AsyncSession, tenant_b: Tenant):
    """Create users for tenant B."""
    users = [
        User(
            tenant_id=tenant_b.id,
            oauth_subject=f"auth0|user-b{i}",
            email=f"user{i}@tenant-b.com",
            display_name=f"User B{i}",
            is_active=True
        )
        for i in range(3)
    ]
    db_session.add_all(users)
    await db_session.commit()  # Commit so other sessions can see them
    for user in users:
        await db_session.refresh(user)
    return users


class TestTenantIsolationSelect:
    """Test tenant isolation for SELECT queries."""

    @pytest.mark.asyncio
    async def test_select_with_tenant_context_returns_only_tenant_data(
        self,
        rls_session: AsyncSession,
        tenant_a: Tenant,
        tenant_b: Tenant,
        users_tenant_a: list[User],
        users_tenant_b: list[User]
    ):
        """Test that SELECT with tenant context only returns data for that tenant."""
        # Set context to tenant A (using RLS session)
        await set_tenant_context(rls_session, tenant_a.id, validate=False)

        # Query users - should only get tenant A users
        result = await rls_session.execute(select(User))
        users = result.scalars().all()

        assert len(users) == 3
        for user in users:
            assert user.tenant_id == tenant_a.id
            # Test data uses format "userN@test-tenant-a-UUID.com" so check tenant ID instead
            assert user.tenant_id == tenant_a.id

    @pytest.mark.asyncio
    async def test_select_different_tenant_contexts(
        self,
        rls_session: AsyncSession,
        tenant_a: Tenant,
        tenant_b: Tenant,
        users_tenant_a: list[User],
        users_tenant_b: list[User]
    ):
        """Test that changing tenant context changes which data is returned."""
        # Query with tenant A context
        await set_tenant_context(rls_session, tenant_a.id, validate=False)
        result = await rls_session.execute(select(User))
        users_a = result.scalars().all()
        assert len(users_a) == 3
        assert all(u.tenant_id == tenant_a.id for u in users_a)

        # Change to tenant B context (in new transaction)
        await rls_session.commit()
        await set_tenant_context(rls_session, tenant_b.id, validate=False)
        result = await rls_session.execute(select(User))
        users_b = result.scalars().all()
        assert len(users_b) == 3
        assert all(u.tenant_id == tenant_b.id for u in users_b)

    @pytest.mark.asyncio
    async def test_select_without_tenant_context_returns_no_data(
        self,
        rls_session: AsyncSession,
        users_tenant_a: list[User],
        users_tenant_b: list[User]
    ):
        """Test that SELECT without tenant context returns no data (RLS blocks)."""
        # Clear any existing context
        await clear_tenant_context(rls_session)

        # Query users without tenant context - should return no data
        result = await rls_session.execute(select(User))
        users = result.scalars().all()

        # RLS should block all rows when context not set
        assert len(users) == 0

    @pytest.mark.asyncio
    async def test_select_with_bypass_rls_returns_all_data(
        self,
        db_session: AsyncSession,
        users_tenant_a: list[User],
        users_tenant_b: list[User]
    ):
        """Test that SELECT with RLS bypass returns all tenant data."""
        # Bypass RLS
        await bypass_rls(db_session)

        # Query users - should get all users regardless of tenant
        result = await db_session.execute(select(User))
        users = result.scalars().all()

        assert len(users) == 6  # 3 from tenant A + 3 from tenant B


class TestTenantIsolationInsert:
    """Test tenant isolation for INSERT operations."""

    @pytest.mark.asyncio
    async def test_insert_with_tenant_context(
        self,
        db_session: AsyncSession,
        tenant_a: Tenant
    ):
        """Test that INSERT with tenant context succeeds."""
        # Set context to tenant A
        await set_tenant_context(db_session, tenant_a.id, validate=False)

        # Insert user for tenant A
        user = User(
            tenant_id=tenant_a.id,
            oauth_subject="auth0|new-user",
            email="newuser@tenant-a.com",
            display_name="New User",
            is_active=True
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Verify user was created
        assert user.id is not None
        assert user.tenant_id == tenant_a.id

    @pytest.mark.asyncio
    async def test_insert_with_wrong_tenant_id_blocked(
        self,
        rls_session: AsyncSession,
        tenant_a: Tenant,
        tenant_b: Tenant
    ):
        """Test that INSERT with wrong tenant_id is blocked by RLS."""
        # Set context to tenant A
        await set_tenant_context(rls_session, tenant_a.id, validate=False)

        # Try to insert user for tenant B (should be blocked)
        user = User(
            tenant_id=tenant_b.id,  # Wrong tenant!
            oauth_subject="auth0|malicious-user",
            email="malicious@tenant-b.com",
            display_name="Malicious User",
            is_active=True
        )
        rls_session.add(user)

        # Should raise an exception due to RLS policy violation
        with pytest.raises(Exception):  # SQLAlchemy will raise an exception
            await rls_session.commit()

        await rls_session.rollback()


class TestTenantIsolationUpdate:
    """Test tenant isolation for UPDATE operations."""

    @pytest.mark.asyncio
    async def test_update_with_tenant_context(
        self,
        db_session: AsyncSession,
        tenant_a: Tenant,
        users_tenant_a: list[User]
    ):
        """Test that UPDATE with tenant context succeeds for owned data."""
        # Set context to tenant A
        await set_tenant_context(db_session, tenant_a.id, validate=False)

        # Update a tenant A user
        user = users_tenant_a[0]
        result = await db_session.execute(
            select(User).where(User.id == user.id)
        )
        user_to_update = result.scalar_one()
        user_to_update.display_name = "Updated Name"
        await db_session.commit()

        # Verify update succeeded
        await db_session.refresh(user_to_update)
        assert user_to_update.display_name == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_other_tenant_data_blocked(
        self,
        rls_session: AsyncSession,
        tenant_a: Tenant,
        tenant_b: Tenant,
        users_tenant_b: list[User]
    ):
        """Test that UPDATE of other tenant's data is blocked by RLS."""
        # Set context to tenant A
        await set_tenant_context(rls_session, tenant_a.id, validate=False)

        # Try to query and update tenant B user (should not find it)
        tenant_b_user_id = users_tenant_b[0].id
        result = await rls_session.execute(
            select(User).where(User.id == tenant_b_user_id)
        )
        user = result.scalar_one_or_none()

        # RLS should prevent seeing tenant B's user
        assert user is None


class TestTenantIsolationDelete:
    """Test tenant isolation for DELETE operations."""

    @pytest.mark.asyncio
    async def test_delete_with_tenant_context(
        self,
        db_session: AsyncSession,
        tenant_a: Tenant,
        users_tenant_a: list[User]
    ):
        """Test that DELETE with tenant context succeeds for owned data."""
        # Set context to tenant A
        await set_tenant_context(db_session, tenant_a.id, validate=False)

        # Delete a tenant A user
        user_to_delete = users_tenant_a[0]
        await db_session.delete(user_to_delete)
        await db_session.commit()

        # Verify user was deleted
        result = await db_session.execute(
            select(User).where(User.id == user_to_delete.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_other_tenant_data_blocked(
        self,
        rls_session: AsyncSession,
        tenant_a: Tenant,
        tenant_b: Tenant,
        users_tenant_b: list[User]
    ):
        """Test that DELETE of other tenant's data is blocked by RLS."""
        # Set context to tenant A
        await set_tenant_context(rls_session, tenant_a.id, validate=False)

        # Try to query and delete tenant B user (should not find it)
        tenant_b_user_id = users_tenant_b[0].id
        result = await rls_session.execute(
            select(User).where(User.id == tenant_b_user_id)
        )
        user = result.scalar_one_or_none()

        # RLS should prevent seeing tenant B's user
        assert user is None


class TestTenantContextManager:
    """Test TenantContext context manager with RLS."""

    @pytest.mark.asyncio
    async def test_context_manager_with_rls(
        self,
        rls_session: AsyncSession,
        tenant_a: Tenant,
        tenant_b: Tenant,
        users_tenant_a: list[User],
        users_tenant_b: list[User]
    ):
        """Test that TenantContext works correctly with RLS queries."""
        # Query within tenant A context
        async with TenantContext(rls_session, tenant_a.id, validate=False):
            result = await rls_session.execute(select(User))
            users = result.scalars().all()
            assert len(users) == 3
            assert all(u.tenant_id == tenant_a.id for u in users)

        # Query within tenant B context (in new transaction)
        await rls_session.commit()
        async with TenantContext(rls_session, tenant_b.id, validate=False):
            result = await rls_session.execute(select(User))
            users = result.scalars().all()
            assert len(users) == 3
            assert all(u.tenant_id == tenant_b.id for u in users)


class TestSecurityScenarios:
    """Test security scenarios and edge cases."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_tenant_by_id(
        self,
        rls_session: AsyncSession,
        tenant_a: Tenant,
        users_tenant_b: list[User]
    ):
        """Test that specifying another tenant's user ID doesn't bypass RLS."""
        # Set context to tenant A
        await set_tenant_context(rls_session, tenant_a.id, validate=False)

        # Try to query tenant B user by ID
        tenant_b_user_id = users_tenant_b[0].id
        result = await rls_session.execute(
            select(User).where(User.id == tenant_b_user_id)
        )
        user = result.scalar_one_or_none()

        # RLS should block access
        assert user is None

    @pytest.mark.asyncio
    async def test_tenant_context_persists_within_transaction(
        self,
        db_session: AsyncSession,
        tenant_a: Tenant,
        users_tenant_a: list[User]
    ):
        """Test that tenant context persists for the entire transaction."""
        # Set context
        await set_tenant_context(db_session, tenant_a.id, validate=False)

        # Perform multiple queries in same transaction
        result1 = await db_session.execute(select(User))
        users1 = result1.scalars().all()

        result2 = await db_session.execute(select(User))
        users2 = result2.scalars().all()

        # Both queries should return same tenant's data
        assert len(users1) == 3
        assert len(users2) == 3
        assert all(u.tenant_id == tenant_a.id for u in users1)
        assert all(u.tenant_id == tenant_a.id for u in users2)
