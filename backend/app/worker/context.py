"""
Tenant context management for Celery workers.

This module provides utilities for managing tenant isolation in background tasks.
It ensures that all database operations within a task respect RLS policies
by setting the appropriate session variable.
"""

import logging
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.context import (
    clear_current_tenant as _clear_context_tenant,
    get_current_tenant as _get_context_tenant,
    set_current_tenant as _set_context_tenant,
)
from app.core.database import AsyncSessionLocal, SyncSessionLocal

logger = logging.getLogger(__name__)


# Re-export context functions for convenience
def get_current_tenant() -> Optional[UUID]:
    """Get current tenant ID from context."""
    return _get_context_tenant()


def set_current_tenant(tenant_id: str | UUID) -> None:
    """Set current tenant ID in context."""
    if isinstance(tenant_id, str):
        tenant_id = UUID(tenant_id)
    _set_context_tenant(tenant_id)


def clear_current_tenant() -> None:
    """Clear current tenant ID from context."""
    _clear_context_tenant()


class TenantWorkerContext:
    """
    Context manager for Celery tasks with tenant isolation.

    Provides a database session with RLS context set for the specified tenant.
    This ensures all database operations within the context respect tenant
    isolation policies.

    Example:
        @celery_app.task
        def process_job(job_id: str, tenant_id: str):
            with TenantWorkerContext(tenant_id) as ctx:
                job = ctx.db.query(ScrapingJob).get(job_id)
                # All queries are automatically filtered by tenant_id
                process(job)

    The context manager:
    1. Creates a new database session
    2. Sets the PostgreSQL session variable for RLS
    3. Sets the application context variable
    4. Provides the session for use
    5. Commits changes on success
    6. Rolls back on exception
    7. Clears context on exit
    """

    def __init__(self, tenant_id: str | UUID):
        """
        Initialize tenant worker context.

        Args:
            tenant_id: UUID of the tenant (string or UUID object)
        """
        if isinstance(tenant_id, str):
            tenant_id = UUID(tenant_id)
        self.tenant_id = tenant_id
        self._db: Optional[Session] = None

    def __enter__(self) -> "TenantWorkerContext":
        """Enter context and set up tenant isolation."""
        # Create synchronous database session
        self._db = SyncSessionLocal()

        try:
            # Set PostgreSQL session variable for RLS
            self._db.execute(
                text("SET app.current_tenant_id = :tenant_id"),
                {"tenant_id": str(self.tenant_id)}
            )

            # Set application context
            set_current_tenant(self.tenant_id)

            logger.debug(
                "Tenant worker context entered",
                extra={"tenant_id": str(self.tenant_id)},
            )

            return self

        except Exception as e:
            self._db.close()
            self._db = None
            raise

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and clean up."""
        try:
            if self._db is not None:
                if exc_type is not None:
                    # Rollback on exception
                    self._db.rollback()
                    logger.warning(
                        "Tenant worker context rolled back",
                        extra={
                            "tenant_id": str(self.tenant_id),
                            "error": str(exc_val),
                        },
                    )
                else:
                    # Commit on success
                    self._db.commit()
                    logger.debug(
                        "Tenant worker context committed",
                        extra={"tenant_id": str(self.tenant_id)},
                    )
        finally:
            # Always clean up
            if self._db is not None:
                self._db.close()
                self._db = None

            clear_current_tenant()
            logger.debug("Tenant worker context cleared")

    @property
    def db(self) -> Session:
        """Get the database session."""
        if self._db is None:
            raise RuntimeError("Context not entered - use 'with' statement")
        return self._db


class AsyncTenantWorkerContext:
    """
    Async context manager for Celery tasks with tenant isolation.

    Same as TenantWorkerContext but for async operations.

    Example:
        async with AsyncTenantWorkerContext(tenant_id) as ctx:
            result = await ctx.db.execute(select(ScrapingJob).where(...))
            job = result.scalar_one()
            await process(job)
    """

    def __init__(self, tenant_id: str | UUID):
        """
        Initialize async tenant worker context.

        Args:
            tenant_id: UUID of the tenant (string or UUID object)
        """
        if isinstance(tenant_id, str):
            tenant_id = UUID(tenant_id)
        self.tenant_id = tenant_id
        self._db: Optional[AsyncSession] = None

    async def __aenter__(self) -> "AsyncTenantWorkerContext":
        """Enter async context and set up tenant isolation."""
        # Create async database session
        self._db = AsyncSessionLocal()

        try:
            # Set PostgreSQL session variable for RLS
            await self._db.execute(
                text("SET app.current_tenant_id = :tenant_id"),
                {"tenant_id": str(self.tenant_id)}
            )

            # Set application context
            set_current_tenant(self.tenant_id)

            logger.debug(
                "Async tenant worker context entered",
                extra={"tenant_id": str(self.tenant_id)},
            )

            return self

        except Exception as e:
            await self._db.close()
            self._db = None
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context and clean up."""
        try:
            if self._db is not None:
                if exc_type is not None:
                    # Rollback on exception
                    await self._db.rollback()
                    logger.warning(
                        "Async tenant worker context rolled back",
                        extra={
                            "tenant_id": str(self.tenant_id),
                            "error": str(exc_val),
                        },
                    )
                else:
                    # Commit on success
                    await self._db.commit()
                    logger.debug(
                        "Async tenant worker context committed",
                        extra={"tenant_id": str(self.tenant_id)},
                    )
        finally:
            # Always clean up
            if self._db is not None:
                await self._db.close()
                self._db = None

            clear_current_tenant()
            logger.debug("Async tenant worker context cleared")

    @property
    def db(self) -> AsyncSession:
        """Get the async database session."""
        if self._db is None:
            raise RuntimeError("Context not entered - use 'async with' statement")
        return self._db


@contextmanager
def tenant_context(tenant_id: str | UUID) -> Generator[Session, None, None]:
    """
    Convenience context manager for tenant-aware database operations.

    Args:
        tenant_id: UUID of the tenant

    Yields:
        Database session with tenant context set

    Example:
        with tenant_context(tenant_id) as db:
            job = db.query(ScrapingJob).get(job_id)
    """
    with TenantWorkerContext(tenant_id) as ctx:
        yield ctx.db


@asynccontextmanager
async def async_tenant_context(
    tenant_id: str | UUID,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Convenience async context manager for tenant-aware database operations.

    Args:
        tenant_id: UUID of the tenant

    Yields:
        Async database session with tenant context set

    Example:
        async with async_tenant_context(tenant_id) as db:
            result = await db.execute(select(ScrapingJob).where(...))
    """
    async with AsyncTenantWorkerContext(tenant_id) as ctx:
        yield ctx.db
