"""
Application context variables for async-safe state management.

Uses Python contextvars to track tenant context across async operations.
This complements PostgreSQL session variables for application-level tracking.
"""

from contextvars import ContextVar
from uuid import UUID
from typing import Optional

# Context variable for current tenant ID
current_tenant_id: ContextVar[Optional[UUID]] = ContextVar(
    "current_tenant_id",
    default=None
)


def get_current_tenant() -> Optional[UUID]:
    """
    Get current tenant ID from context.

    Returns:
        Current tenant UUID or None if not set

    Example:
        tenant_id = get_current_tenant()
        if tenant_id:
            logger.info("operation", tenant_id=str(tenant_id))
    """
    return current_tenant_id.get()


def set_current_tenant(tenant_id: UUID) -> None:
    """
    Set current tenant ID in context.

    Args:
        tenant_id: UUID of tenant to set as current

    Example:
        set_current_tenant(tenant_id)
        # All logging/tracing will now include tenant_id
    """
    current_tenant_id.set(tenant_id)


def clear_current_tenant() -> None:
    """
    Clear current tenant ID from context.

    Example:
        clear_current_tenant()
        # Tenant context removed
    """
    current_tenant_id.set(None)
