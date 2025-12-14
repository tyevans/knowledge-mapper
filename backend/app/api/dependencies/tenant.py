"""
Tenant-Aware Database Dependencies for FastAPI.

This module provides tenant-aware database session dependencies that automatically
set the PostgreSQL tenant context (via `app.current_tenant_id` session variable)
for Row-Level Security (RLS) enforcement.

These dependencies integrate with:
- TASK-015: Tenant Resolution Middleware (reads request.state.tenant_id)
- TASK-014: Tenant Context Service (calls set_tenant_context())
- TASK-001: Database Infrastructure (returns AsyncSession)

Key Features:
- Automatic RLS enforcement via session variable
- Multiple variants for different use cases (required, optional, superuser)
- Request state as primary source, contextvars as fallback
- Clear error messages when tenant context is missing
- Comprehensive logging for debugging and security auditing

Usage Examples:
    # Protected endpoint (requires tenant context) - RECOMMENDED
    @router.get("/statements")
    async def get_statements(
        user: CurrentUserWithTenant,
        db: Annotated[AsyncSession, Depends(get_tenant_session)]
    ):
        # All queries automatically filtered by tenant via RLS
        result = await db.execute(select(Statement))
        return result.scalars().all()

    # Flexible endpoint (optional tenant context)
    @router.get("/public-data")
    async def get_public_data(db: AsyncSession = Depends(get_optional_tenant_db)):
        # Tenant context set if available, skipped if not
        result = await db.execute(select(PublicData))
        return result.scalars().all()

    # Admin endpoint (bypasses RLS)
    @router.get("/admin/all-tenants")
    async def list_all_tenants(
        db: AsyncSession = Depends(get_superuser_db),
        _: None = Depends(require_admin_scope)
    ):
        # Bypasses RLS to see all tenants
        result = await db.execute(select(Tenant))
        return result.scalars().all()
"""

import logging
from typing import Annotated, AsyncGenerator, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_current_tenant
from app.core.database import AsyncSessionLocal
from app.schemas.auth import AuthenticatedUser
from app.services.tenant_context import (
    TenantContextError,
    bypass_rls,
    set_tenant_context,
)

# Import for dependency chaining (no circular import - auth.py doesn't import tenant.py)
from app.api.dependencies.auth import require_tenant_context

logger = logging.getLogger(__name__)


async def get_tenant_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a tenant-aware database session.

    This dependency REQUIRES tenant context and will raise HTTP 500 if the tenant
    context is not available. It automatically sets the PostgreSQL session variable
    `app.current_tenant_id` to enforce Row-Level Security (RLS) policies.

    The tenant_id is read from:
    1. request.state.tenant_id (set by TenantResolutionMiddleware from TASK-015)
    2. Contextvars as fallback (set by middleware or previous context)

    Use this dependency for protected endpoints that require tenant isolation.

    Args:
        request: FastAPI request object (automatically injected)

    Yields:
        AsyncSession: Database session with tenant context set and RLS enforced

    Raises:
        HTTPException: 500 Internal Server Error if tenant context is missing or invalid

    Example:
        @router.get("/statements")
        async def get_statements(db: AsyncSession = Depends(get_tenant_db)):
            # All queries automatically filtered by tenant via RLS
            result = await db.execute(select(Statement))
            return result.scalars().all()

    Security:
        This dependency ensures that all database queries are automatically filtered
        by tenant via RLS policies. Queries will only return data for the authenticated
        user's tenant. This is the PRIMARY security mechanism for tenant isolation.

    Note:
        If you're implementing a public endpoint that doesn't require tenant context,
        use get_db() from app.api.dependencies.database instead.
    """
    # Extract tenant_id from request state (set by middleware)
    tenant_id = _extract_tenant_id(request)

    if tenant_id is None:
        # Tenant context is required but missing - this is a server error
        # The middleware should have set this for all protected endpoints
        logger.error(
            "Tenant context required but missing",
            extra={
                "endpoint": request.url.path,
                "method": request.method,
                "has_user": hasattr(request.state, "user"),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": 500,
                    "message": "Tenant context is required but not available",
                    "type": "tenant_context_missing",
                }
            },
        )

    # Create database session and set tenant context
    async with AsyncSessionLocal() as session:
        try:
            # Set PostgreSQL session variable for RLS enforcement
            await set_tenant_context(session, tenant_id, validate=True)

            logger.info(
                "Tenant context set for database session",
                extra={
                    "tenant_id": str(tenant_id),
                    "endpoint": request.url.path,
                    "method": request.method,
                    "session_id": id(session),
                },
            )

            # Yield session with tenant context set
            yield session

            # Commit on success
            await session.commit()
            logger.debug(
                "Tenant-aware database session committed",
                extra={"tenant_id": str(tenant_id)},
            )

        except TenantContextError as e:
            # Tenant validation failed (tenant doesn't exist or is inactive)
            await session.rollback()
            logger.error(
                "Tenant context validation failed",
                extra={
                    "tenant_id": str(tenant_id),
                    "endpoint": request.url.path,
                    "error": str(e),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": 403,
                        "message": "Tenant is not active or does not exist",
                        "type": "tenant_validation_failed",
                    }
                },
            ) from e

        except Exception as e:
            # Rollback on any other error
            await session.rollback()
            logger.warning(
                "Tenant-aware database session rolled back",
                extra={
                    "tenant_id": str(tenant_id),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise

        finally:
            await session.close()
            logger.debug("Tenant-aware database session closed")


async def get_optional_tenant_db(
    request: Request,
) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session with optional tenant context.

    This variant sets tenant context if available but continues without it if not.
    Use this for endpoints that can work with or without tenant context (e.g.,
    endpoints that show public data but filter by tenant if user is authenticated).

    If tenant_id is available, RLS is enforced. If not, queries are not filtered
    by tenant (but may still be filtered by other RLS policies or app logic).

    Args:
        request: FastAPI request object (automatically injected)

    Yields:
        AsyncSession: Database session (with or without tenant context)

    Example:
        @router.get("/public-resources")
        async def get_public_resources(
            db: AsyncSession = Depends(get_optional_tenant_db)
        ):
            # If user is authenticated, data is filtered by tenant
            # If not authenticated, shows all public data
            result = await db.execute(select(PublicResource))
            return result.scalars().all()

    Note:
        This dependency does not raise errors if tenant context is missing.
        Use this only for endpoints where tenant context is truly optional.
        For most protected endpoints, use get_tenant_db() instead.
    """
    # Extract tenant_id (may be None for unauthenticated requests)
    tenant_id = _extract_tenant_id(request)

    async with AsyncSessionLocal() as session:
        try:
            if tenant_id is not None:
                # Set tenant context if available
                try:
                    await set_tenant_context(session, tenant_id, validate=True)
                    logger.info(
                        "Optional tenant context set",
                        extra={
                            "tenant_id": str(tenant_id),
                            "endpoint": request.url.path,
                        },
                    )
                except TenantContextError as e:
                    # Tenant validation failed - continue without context
                    logger.warning(
                        "Optional tenant context validation failed, continuing without tenant",
                        extra={
                            "tenant_id": str(tenant_id),
                            "endpoint": request.url.path,
                            "error": str(e),
                        },
                    )
            else:
                logger.debug(
                    "Optional tenant context not available",
                    extra={"endpoint": request.url.path},
                )

            # Yield session (with or without tenant context)
            yield session

            # Commit on success
            await session.commit()
            logger.debug("Optional tenant-aware database session committed")

        except Exception as e:
            await session.rollback()
            logger.warning(
                "Optional tenant-aware database session rolled back",
                extra={"error": str(e), "error_type": type(e).__name__},
                exc_info=True,
            )
            raise

        finally:
            await session.close()
            logger.debug("Optional tenant-aware database session closed")


async def get_superuser_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session with RLS bypassed.

    SECURITY WARNING: This dependency bypasses Row-Level Security, allowing queries
    to access ALL tenant data. Only use this for:
    - System administration endpoints
    - Cross-tenant analytics (with proper authorization)
    - Operations that truly need access to all tenants

    This dependency logs all usage at WARNING level for security auditing.

    Args:
        request: FastAPI request object (automatically injected)

    Yields:
        AsyncSession: Database session with RLS disabled

    Raises:
        HTTPException: If authorization fails (should be paired with scope check)

    Example:
        @router.get("/admin/all-tenants")
        async def list_all_tenants(
            db: AsyncSession = Depends(get_superuser_db),
            _: None = Depends(require_scope("admin:all"))
        ):
            # Bypasses RLS to see all tenants
            result = await db.execute(select(Tenant))
            return result.scalars().all()

    Security:
        ALWAYS pair this dependency with proper authorization checks:
        - Require admin scope (admin:all or similar)
        - Validate user has permission for cross-tenant operations
        - Log all operations for security audit trail

        This dependency automatically logs at WARNING level to ensure all
        RLS bypass operations are visible in logs for security review.
    """
    # Log RLS bypass for security auditing
    user_id = getattr(request.state, "user_id", "unknown")
    logger.warning(
        "RLS bypass requested - database session will access ALL tenant data",
        extra={
            "endpoint": request.url.path,
            "method": request.method,
            "user_id": user_id,
            "reason": "superuser_operation",
        },
    )

    async with AsyncSessionLocal() as session:
        try:
            # Bypass RLS policies for system operations
            await bypass_rls(session)

            logger.warning(
                "RLS bypass active - session can access all tenant data",
                extra={
                    "endpoint": request.url.path,
                    "user_id": user_id,
                    "session_id": id(session),
                },
            )

            # Yield session with RLS bypassed
            yield session

            # Commit on success
            await session.commit()
            logger.warning(
                "Superuser database session committed - RLS was bypassed",
                extra={"endpoint": request.url.path, "user_id": user_id},
            )

        except Exception as e:
            await session.rollback()
            logger.error(
                "Superuser database session rolled back",
                extra={
                    "endpoint": request.url.path,
                    "user_id": user_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise

        finally:
            await session.close()
            logger.debug("Superuser database session closed")


def _extract_tenant_id(request: Request) -> Optional[UUID]:
    """
    Extract tenant_id from request state or contextvars.

    This is an internal helper function that reads tenant_id from:
    1. request.state.tenant_id (set by TenantResolutionMiddleware)
    2. contextvars as fallback (set by middleware or previous context)

    Args:
        request: FastAPI request object

    Returns:
        Tenant UUID or None if not available

    Note:
        This function does not raise exceptions. It returns None if tenant_id
        is not available, and the calling dependency decides how to handle it.
    """
    # Primary source: request state (set by middleware)
    tenant_id = getattr(request.state, "tenant_id", None)

    if tenant_id is not None:
        logger.debug(
            "Tenant ID extracted from request state",
            extra={"tenant_id": str(tenant_id)},
        )
        return tenant_id

    # Fallback: contextvars (for edge cases)
    tenant_id = get_current_tenant()

    if tenant_id is not None:
        logger.debug(
            "Tenant ID extracted from contextvars (fallback)",
            extra={"tenant_id": str(tenant_id)},
        )
        return tenant_id

    # No tenant context available
    logger.debug("Tenant ID not available in request state or contextvars")
    return None


async def get_session_with_tenant(
    tenant_id: UUID,
    request: Request,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Create a database session with tenant context set.

    This is a helper function (not a FastAPI dependency) that creates a session
    with the PostgreSQL session variable `app.current_tenant_id` set for RLS.

    Args:
        tenant_id: UUID of the tenant
        request: FastAPI request object for logging

    Yields:
        AsyncSession: Database session with tenant context set

    Example:
        async for db in get_session_with_tenant(UUID(user.tenant_id), request):
            result = await db.execute(select(Item))
    """
    async with AsyncSessionLocal() as session:
        try:
            await set_tenant_context(session, tenant_id, validate=True)
            logger.info(
                "Tenant session context set",
                extra={
                    "tenant_id": str(tenant_id),
                    "endpoint": request.url.path,
                    "session_id": id(session),
                },
            )
            yield session
            await session.commit()
        except TenantContextError as e:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": 403, "message": str(e)}},
            ) from e
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class TenantSessionDep:
    """
    Dependency class that provides a tenant-aware database session.

    This class-based dependency allows passing the user's tenant_id to create
    a database session with proper RLS context.

    Example:
        @router.get("/items")
        async def get_items(
            user: CurrentUserWithTenant,
            db: AsyncSession = Depends(TenantSessionDep())
        ):
            # Note: Use get_db_for_tenant helper instead for simpler usage
            pass
    """

    async def __call__(
        self,
        request: Request,
    ) -> AsyncGenerator[AsyncSession, None]:
        # Try to get tenant from request.state (set by other dependencies)
        user = getattr(request.state, "user", None)
        tenant_id: Optional[UUID] = None

        if user is not None and getattr(user, "tenant_id", None):
            tenant_id_str = user.tenant_id
            try:
                tenant_id = UUID(tenant_id_str) if isinstance(tenant_id_str, str) else tenant_id_str
            except (ValueError, TypeError):
                pass

        # Fallback to request.state.tenant_id or contextvars
        if tenant_id is None:
            tenant_id = _extract_tenant_id(request)

        if tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": {
                        "code": 500,
                        "message": "Tenant context required but not available",
                        "type": "tenant_context_missing",
                    }
                },
            )

        async for session in get_session_with_tenant(tenant_id, request):
            yield session


async def get_db_for_tenant(
    request: Request,
    user: AuthenticatedUser = Depends(require_tenant_context),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Create a tenant-aware database session from an authenticated user.

    This is the recommended way to get a database session with tenant context
    in route handlers. It ensures RLS is enforced based on the user's tenant.

    This dependency automatically chains with authentication - you don't need
    to separately inject CurrentUserWithTenant.

    Example:
        @router.post("/items")
        async def create_item(
            db: TenantSession,  # Includes auth + tenant-aware DB
        ):
            # RLS is now enforced
            item = Item(...)
            db.add(item)
            return item

        # Or if you need the user object too:
        @router.post("/items")
        async def create_item(
            user: CurrentUserWithTenant,
            db: TenantSession,
        ):
            # Both are available
            item = Item(tenant_id=UUID(user.tenant_id), ...)
            db.add(item)
            return item

    Args:
        request: FastAPI request object
        user: Authenticated user with tenant context (auto-injected)

    Yields:
        AsyncSession: Database session with tenant context set

    Raises:
        HTTPException: 401 if not authenticated
        HTTPException: 403 if no tenant context or tenant validation fails
        HTTPException: 500 if tenant_id is invalid
    """
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": 500,
                    "message": "Tenant context required but user has no tenant_id",
                    "type": "tenant_context_missing",
                }
            },
        )

    try:
        tenant_id = UUID(user.tenant_id) if isinstance(user.tenant_id, str) else user.tenant_id
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": 500,
                    "message": f"Invalid tenant_id format: {user.tenant_id}",
                    "type": "tenant_context_invalid",
                }
            },
        ) from e

    async for session in get_session_with_tenant(tenant_id, request):
        yield session


# Type alias for tenant-aware database session (uses get_db_for_tenant)
TenantSession = Annotated[AsyncSession, Depends(get_db_for_tenant)]
