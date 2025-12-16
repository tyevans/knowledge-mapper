"""
Pytest configuration and fixtures for scraping integration tests.

Provides fixtures for:
- Database session management with BYPASSRLS
- Tenant fixtures for testing
"""

import os
import pytest
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models import Tenant


# Create async engine using migration user (BYPASSRLS)
_MIGRATION_USER_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://knowledge_mapper_migration_user:migration_password_dev@postgres:5432/knowledge_mapper_db"
)

_test_engine = create_async_engine(
    _MIGRATION_USER_DB_URL,
    pool_size=5,
    max_overflow=5,
    echo=False,
)

TestAsyncSessionLocal = async_sessionmaker(
    _test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for async tests."""
    return "asyncio"


@pytest.fixture
async def db_session():
    """
    Create a test database session with BYPASSRLS for setup/teardown.
    """
    async with TestAsyncSessionLocal() as session:
        created_tenant_ids = []
        session.info["created_tenant_ids"] = created_tenant_ids

        yield session

        # Clean up test data
        if created_tenant_ids:
            await session.execute(
                text("DELETE FROM scraping_jobs WHERE tenant_id = ANY(:ids)"),
                {"ids": created_tenant_ids},
            )
            await session.execute(
                text("DELETE FROM tenants WHERE id = ANY(:ids)"),
                {"ids": created_tenant_ids},
            )
            await session.commit()


@pytest.fixture
async def test_tenant(db_session: AsyncSession):
    """Create a test tenant."""
    unique_id = str(uuid4())[:8]
    tenant = Tenant(
        slug=f"test-tenant-{unique_id}",
        name="Test Tenant",
        is_active=True,
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    db_session.info["created_tenant_ids"].append(str(tenant.id))
    return tenant
