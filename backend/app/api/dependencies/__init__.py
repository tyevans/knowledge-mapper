"""
FastAPI dependency injection modules.

This package contains dependency injection functions for FastAPI routes,
including database session management, authentication, and tenant context.
"""

from app.api.dependencies.database import get_db
from app.api.dependencies.tenant import (
    get_db_for_tenant,
    get_optional_tenant_db,
    get_superuser_db,
    get_tenant_db,
    TenantSession,
)

__all__ = [
    "get_db",
    "get_db_for_tenant",
    "get_tenant_db",
    "get_optional_tenant_db",
    "get_superuser_db",
    "TenantSession",
]
