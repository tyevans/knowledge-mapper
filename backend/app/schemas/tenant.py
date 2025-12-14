"""
Pydantic schemas for tenant data.

This module provides Pydantic models for tenant information used in API
responses and caching. The TenantInfo schema can be serialized to JSON for
Redis caching and is used by the tenant resolver service.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TenantInfo(BaseModel):
    """
    Tenant information schema for API responses and caching.

    This schema is used by the tenant resolver service and can be
    serialized to JSON for Redis caching. It provides a lightweight
    representation of tenant data optimized for caching and API responses.

    Attributes:
        id: Tenant UUID (primary key)
        slug: Tenant slug (URL-safe identifier)
        name: Tenant display name
        is_active: Whether tenant is active (soft delete flag)
        created_at: Tenant creation timestamp (UTC)
        updated_at: Tenant last update timestamp (UTC)
        settings: Tenant-specific settings (JSONB)
    """

    id: UUID = Field(..., description="Tenant UUID")
    slug: str = Field(..., description="Tenant slug (URL-safe identifier)")
    name: str = Field(..., description="Tenant display name")
    is_active: bool = Field(..., description="Whether tenant is active")
    created_at: datetime = Field(..., description="Tenant creation timestamp")
    updated_at: datetime = Field(..., description="Tenant last update timestamp")
    settings: Optional[dict] = Field(
        None, description="Tenant-specific settings (JSONB)"
    )

    class Config:
        """Pydantic model configuration."""

        from_attributes = True  # Enables ORM mode for SQLAlchemy models


class TenantNotFoundError(Exception):
    """
    Raised when tenant cannot be found.

    This exception is raised by the tenant resolver when a tenant with the
    specified ID, slug, or subdomain does not exist in the database.
    """

    pass


class TenantInactiveError(Exception):
    """
    Raised when tenant is not active.

    This exception is raised by the tenant resolver when a tenant exists but
    is marked as inactive (soft deleted) and require_active=True is specified.
    """

    pass


# =============================================================================
# Tenant Management Schemas (for platform admins)
# =============================================================================


class TenantCreate(BaseModel):
    """Schema for creating a new tenant."""

    slug: str = Field(
        ...,
        min_length=2,
        max_length=255,
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$",
        description="URL-safe tenant identifier (lowercase, hyphens allowed)",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable tenant name",
    )
    settings: Optional[dict] = Field(
        default_factory=dict,
        description="Tenant-specific settings",
    )
    is_active: bool = Field(
        default=True,
        description="Whether tenant is active",
    )


class TenantUpdate(BaseModel):
    """Schema for updating an existing tenant."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Human-readable tenant name",
    )
    settings: Optional[dict] = Field(
        None,
        description="Tenant-specific settings",
    )
    is_active: Optional[bool] = Field(
        None,
        description="Whether tenant is active",
    )


class TenantStoreMapping(BaseModel):
    """Schema for tenant-to-event-store mapping."""

    tenant_id: UUID = Field(..., description="Tenant UUID")
    store_id: str = Field(..., description="Event store identifier")
    migration_state: str = Field(
        default="NORMAL",
        description="Migration state: NORMAL, BULK_COPY, DUAL_WRITE, CUTOVER_PAUSED, MIGRATED",
    )
    target_store_id: Optional[str] = Field(
        None,
        description="Target store ID during migration",
    )
    active_migration_id: Optional[UUID] = Field(
        None,
        description="Active migration ID if migrating",
    )


class TenantWithStoreMapping(TenantInfo):
    """Tenant info with event store mapping details."""

    store_mapping: Optional[TenantStoreMapping] = Field(
        None,
        description="Event store mapping for this tenant",
    )
    user_count: int = Field(
        default=0,
        description="Number of users in this tenant",
    )
    event_count: int = Field(
        default=0,
        description="Number of events for this tenant",
    )


class TenantListResponse(BaseModel):
    """Paginated list of tenants."""

    items: list[TenantWithStoreMapping] = Field(
        ...,
        description="List of tenants",
    )
    total: int = Field(..., description="Total number of tenants")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    pages: int = Field(..., description="Total number of pages")
