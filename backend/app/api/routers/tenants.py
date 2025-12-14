"""
Tenant management API router.

Provides endpoints for platform administrators to manage tenants
and their event store mappings. Requires elevated permissions
(tenants/read, tenants/manage, tenants/stores scopes).
"""

import logging
import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_db
from app.api.dependencies.scopes import require_scopes, require_any_scope
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    AuthenticatedUser,
    SCOPE_TENANTS_READ,
    SCOPE_TENANTS_MANAGE,
    SCOPE_TENANTS_STORES,
    SCOPE_ADMIN,
)
from app.schemas.tenant import (
    TenantInfo,
    TenantCreate,
    TenantUpdate,
    TenantListResponse,
    TenantWithStoreMapping,
    TenantStoreMapping,
)
from app.services.tenant_resolver import TenantResolver

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/tenants",
    tags=["Tenant Management"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
    },
)

# Dependency for tenant management access
require_tenant_read = require_any_scope(SCOPE_TENANTS_READ, SCOPE_ADMIN)
require_tenant_manage = require_any_scope(SCOPE_TENANTS_MANAGE, SCOPE_ADMIN)
require_tenant_stores = require_any_scope(SCOPE_TENANTS_STORES, SCOPE_ADMIN)


@router.get(
    "",
    response_model=TenantListResponse,
    summary="List all tenants",
    description="Get a paginated list of all tenants in the system. Requires tenants/read or admin scope.",
)
async def list_tenants(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    include_inactive: bool = Query(False, description="Include inactive tenants"),
    search: Optional[str] = Query(None, description="Search by name or slug"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
    _: None = Depends(require_tenant_read),
) -> TenantListResponse:
    """
    List all tenants with pagination and optional filtering.

    This endpoint bypasses normal RLS to allow platform admins
    to see all tenants in the system.
    """
    logger.info(
        "Listing tenants",
        extra={
            "user_id": current_user.user_id,
            "page": page,
            "page_size": page_size,
        },
    )

    # Build query
    query = select(Tenant)

    if not include_inactive:
        query = query.where(Tenant.is_active == True)

    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (Tenant.name.ilike(search_pattern)) | (Tenant.slug.ilike(search_pattern))
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.order_by(Tenant.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    # Execute query
    result = await db.execute(query)
    tenants = result.scalars().all()

    # Get user counts for each tenant
    tenant_ids = [t.id for t in tenants]
    user_counts = {}
    if tenant_ids:
        user_count_query = (
            select(User.tenant_id, func.count(User.id))
            .where(User.tenant_id.in_(tenant_ids))
            .group_by(User.tenant_id)
        )
        user_count_result = await db.execute(user_count_query)
        user_counts = dict(user_count_result.all())

    # Build response items
    items = []
    for tenant in tenants:
        tenant_info = TenantWithStoreMapping(
            id=tenant.id,
            slug=tenant.slug,
            name=tenant.name,
            is_active=tenant.is_active,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
            settings=tenant.settings,
            user_count=user_counts.get(tenant.id, 0),
            event_count=0,  # TODO: Get from event store
            store_mapping=TenantStoreMapping(
                tenant_id=tenant.id,
                store_id="default",  # TODO: Get from TenantRoutingRepository
                migration_state="NORMAL",
            ),
        )
        items.append(tenant_info)

    pages = math.ceil(total / page_size) if total > 0 else 1

    return TenantListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/{tenant_id}",
    response_model=TenantWithStoreMapping,
    summary="Get tenant details",
    description="Get detailed information about a specific tenant.",
)
async def get_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
    _: None = Depends(require_tenant_read),
) -> TenantWithStoreMapping:
    """Get a specific tenant by ID."""
    logger.info(
        "Getting tenant",
        extra={
            "user_id": current_user.user_id,
            "tenant_id": str(tenant_id),
        },
    )

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )

    # Get user count
    user_count_result = await db.execute(
        select(func.count(User.id)).where(User.tenant_id == tenant_id)
    )
    user_count = user_count_result.scalar() or 0

    return TenantWithStoreMapping(
        id=tenant.id,
        slug=tenant.slug,
        name=tenant.name,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        settings=tenant.settings,
        user_count=user_count,
        event_count=0,  # TODO: Get from event store
        store_mapping=TenantStoreMapping(
            tenant_id=tenant.id,
            store_id="default",  # TODO: Get from TenantRoutingRepository
            migration_state="NORMAL",
        ),
    )


@router.post(
    "",
    response_model=TenantInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new tenant",
    description="Create a new tenant in the system. Requires tenants/manage or admin scope.",
)
async def create_tenant(
    tenant_data: TenantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
    _: None = Depends(require_tenant_manage),
) -> TenantInfo:
    """Create a new tenant."""
    logger.info(
        "Creating tenant",
        extra={
            "user_id": current_user.user_id,
            "slug": tenant_data.slug,
        },
    )

    # Check if slug already exists
    existing = await db.execute(
        select(Tenant).where(Tenant.slug == tenant_data.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with slug '{tenant_data.slug}' already exists",
        )

    # Create tenant
    tenant = Tenant(
        slug=tenant_data.slug,
        name=tenant_data.name,
        settings=tenant_data.settings or {},
        is_active=tenant_data.is_active,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    logger.info(
        "Tenant created",
        extra={
            "tenant_id": str(tenant.id),
            "slug": tenant.slug,
        },
    )

    return TenantInfo.model_validate(tenant)


@router.patch(
    "/{tenant_id}",
    response_model=TenantInfo,
    summary="Update a tenant",
    description="Update an existing tenant. Requires tenants/manage or admin scope.",
)
async def update_tenant(
    tenant_id: UUID,
    tenant_data: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
    _: None = Depends(require_tenant_manage),
) -> TenantInfo:
    """Update an existing tenant."""
    logger.info(
        "Updating tenant",
        extra={
            "user_id": current_user.user_id,
            "tenant_id": str(tenant_id),
        },
    )

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )

    # Update fields
    update_data = tenant_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)

    await db.commit()
    await db.refresh(tenant)

    # Invalidate cache
    resolver = TenantResolver()
    await resolver.invalidate_cache(tenant.id, tenant.slug)

    logger.info(
        "Tenant updated",
        extra={
            "tenant_id": str(tenant.id),
            "updated_fields": list(update_data.keys()),
        },
    )

    return TenantInfo.model_validate(tenant)


@router.delete(
    "/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tenant",
    description="Soft-delete a tenant (marks as inactive). Requires tenants/manage or admin scope.",
)
async def delete_tenant(
    tenant_id: UUID,
    hard_delete: bool = Query(False, description="Permanently delete (dangerous)"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
    _: None = Depends(require_tenant_manage),
) -> None:
    """Delete a tenant (soft delete by default)."""
    logger.info(
        "Deleting tenant",
        extra={
            "user_id": current_user.user_id,
            "tenant_id": str(tenant_id),
            "hard_delete": hard_delete,
        },
    )

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )

    if hard_delete:
        # Permanent deletion - requires admin scope
        if SCOPE_ADMIN not in current_user.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Hard delete requires admin scope",
            )
        await db.delete(tenant)
        logger.warning(
            "Tenant permanently deleted",
            extra={"tenant_id": str(tenant_id)},
        )
    else:
        # Soft delete
        tenant.is_active = False
        logger.info(
            "Tenant soft-deleted",
            extra={"tenant_id": str(tenant_id)},
        )

    await db.commit()

    # Invalidate cache
    resolver = TenantResolver()
    await resolver.invalidate_cache(tenant_id, tenant.slug)


@router.get(
    "/{tenant_id}/store-mapping",
    response_model=TenantStoreMapping,
    summary="Get tenant store mapping",
    description="Get the event store mapping for a tenant. Requires tenants/stores or admin scope.",
)
async def get_tenant_store_mapping(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
    _: None = Depends(require_tenant_stores),
) -> TenantStoreMapping:
    """Get the event store mapping for a tenant."""
    logger.info(
        "Getting tenant store mapping",
        extra={
            "user_id": current_user.user_id,
            "tenant_id": str(tenant_id),
        },
    )

    # Verify tenant exists
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )

    # TODO: Get from TenantRoutingRepository when integrated
    # For now, return default mapping
    return TenantStoreMapping(
        tenant_id=tenant_id,
        store_id="default",
        migration_state="NORMAL",
    )


@router.put(
    "/{tenant_id}/store-mapping",
    response_model=TenantStoreMapping,
    summary="Update tenant store mapping",
    description="Update the event store mapping for a tenant. Requires tenants/stores or admin scope.",
)
async def update_tenant_store_mapping(
    tenant_id: UUID,
    store_id: str = Query(..., description="Target store ID"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
    _: None = Depends(require_tenant_stores),
) -> TenantStoreMapping:
    """Update the event store mapping for a tenant."""
    logger.info(
        "Updating tenant store mapping",
        extra={
            "user_id": current_user.user_id,
            "tenant_id": str(tenant_id),
            "store_id": store_id,
        },
    )

    # Verify tenant exists
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )

    # TODO: Update TenantRoutingRepository when integrated
    # For now, just return the requested mapping
    return TenantStoreMapping(
        tenant_id=tenant_id,
        store_id=store_id,
        migration_state="NORMAL",
    )
