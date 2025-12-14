"""
Tenant Context Service for PostgreSQL Row-Level Security (RLS).

This service manages the `app.current_tenant_id` session variable that RLS policies
use to filter queries by tenant. This is the PRIMARY security mechanism for tenant
isolation in the multi-tenant architecture.

Security Critical: All queries MUST have tenant context set before execution to
prevent cross-tenant data leakage.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from uuid import UUID
from typing import Optional
import logging

from app.models.tenant import Tenant
from app.core.context import set_current_tenant, clear_current_tenant

logger = logging.getLogger(__name__)


class TenantContextError(Exception):
    """Raised when tenant context operations fail."""
    pass


async def set_tenant_context(
    session: AsyncSession,
    tenant_id: UUID,
    validate: bool = True
) -> None:
    """
    Set PostgreSQL session variable for RLS tenant filtering.

    This function MUST be called before executing any queries that access
    tenant-scoped tables (users, statements, activities, etc.). It sets the
    `app.current_tenant_id` session variable that RLS policies use for filtering.

    Args:
        session: SQLAlchemy async session
        tenant_id: UUID of the tenant to set as current context
        validate: If True, validates tenant exists and is active (default: True)

    Raises:
        TenantContextError: If tenant validation fails or session variable cannot be set

    Example:
        async with get_db() as session:
            await set_tenant_context(session, tenant_id)
            # All subsequent queries filtered by tenant_id via RLS
            result = await session.execute(select(User))
    """
    try:
        # Validate tenant exists and is active
        if validate:
            await validate_tenant_active(session, tenant_id)

        # Set PostgreSQL session variable for RLS policies
        # TRUE parameter makes this transaction-scoped (LOCAL)
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, TRUE)"),
            {"tenant_id": str(tenant_id)}
        )

        # Also set in contextvars for application-level tracking
        set_current_tenant(tenant_id)

        logger.info(
            "Tenant context set: tenant_id=%s, validated=%s",
            str(tenant_id),
            validate
        )

    except TenantContextError:
        # Re-raise TenantContextError without wrapping
        raise
    except Exception as e:
        logger.error(
            "Failed to set tenant context: tenant_id=%s, error=%s, error_type=%s",
            str(tenant_id),
            str(e),
            type(e).__name__
        )
        raise TenantContextError(f"Failed to set tenant context: {e}") from e


async def clear_tenant_context(session: AsyncSession) -> None:
    """
    Clear tenant context from PostgreSQL session.

    Sets the `app.current_tenant_id` session variable to a nil UUID. After calling this,
    queries will return no rows from RLS-protected tables (unless RLS is bypassed).

    Note: We use '00000000-0000-0000-0000-000000000000' instead of NULL because
    current_setting() returns an empty string for NULL, which fails UUID casting
    in RLS policies.

    Args:
        session: SQLAlchemy async session

    Example:
        await clear_tenant_context(session)
        # Queries to tenant-scoped tables will now return no rows
    """
    try:
        # Set to nil UUID instead of NULL to avoid UUID casting errors
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', '00000000-0000-0000-0000-000000000000', TRUE)")
        )
        clear_current_tenant()

        logger.info("Tenant context cleared")

    except Exception as e:
        logger.error(
            "Failed to clear tenant context: error=%s, error_type=%s",
            str(e),
            type(e).__name__
        )
        raise TenantContextError(f"Failed to clear tenant context: {e}") from e


async def bypass_rls(session: AsyncSession) -> None:
    """
    Bypass Row-Level Security for system operations.

    SECURITY WARNING: This disables RLS policies, allowing queries to access ALL
    tenant data. Only use for:
    - Database migrations (Alembic)
    - System administration tasks
    - Cross-tenant analytics (with proper authorization)

    Args:
        session: SQLAlchemy async session

    Example:
        # In migration script
        async with get_db() as session:
            await bypass_rls(session)
            # Migration can now modify all tenant data
            await session.execute(...)
    """
    try:
        await session.execute(text("SET LOCAL row_security = off"))

        logger.warning("Row-Level Security bypassed for system operation")

    except Exception as e:
        logger.error(
            "Failed to bypass RLS: error=%s, error_type=%s",
            str(e),
            type(e).__name__
        )
        raise TenantContextError(f"Failed to bypass RLS: {e}") from e


async def validate_tenant_active(session: AsyncSession, tenant_id: UUID) -> None:
    """
    Validate that tenant exists and is active.

    Args:
        session: SQLAlchemy async session
        tenant_id: UUID of tenant to validate

    Raises:
        TenantContextError: If tenant does not exist or is not active
    """
    # Query without RLS (tenants table may not have RLS in all configurations)
    result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()

    if tenant is None:
        logger.error("Tenant not found: tenant_id=%s", str(tenant_id))
        raise TenantContextError(f"Tenant {tenant_id} does not exist")

    if not tenant.is_active:
        logger.error("Tenant inactive: tenant_id=%s", str(tenant_id))
        raise TenantContextError(f"Tenant {tenant_id} is not active")

    logger.debug(
        "Tenant validated: tenant_id=%s, tenant_slug=%s",
        str(tenant_id),
        tenant.slug
    )


class TenantContext:
    """
    Async context manager for tenant context operations.

    Ensures tenant context is set for the duration of the context and
    optionally cleared afterwards.

    Example:
        async with TenantContext(session, tenant_id):
            # Tenant context active here
            result = await session.execute(select(User))
        # Tenant context cleared (if clear_on_exit=True)
    """

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        validate: bool = True,
        clear_on_exit: bool = False
    ):
        self.session = session
        self.tenant_id = tenant_id
        self.validate = validate
        self.clear_on_exit = clear_on_exit

    async def __aenter__(self):
        await set_tenant_context(self.session, self.tenant_id, self.validate)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.clear_on_exit:
            await clear_tenant_context(self.session)
        # Don't suppress exceptions
        return False
