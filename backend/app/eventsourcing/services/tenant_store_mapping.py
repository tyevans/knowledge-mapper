"""
Tenant-to-event-store mapping service.

Provides a high-level interface for managing tenant routing to event stores,
wrapping the eventsource-py migration.TenantRoutingRepository.
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from eventsource.migration import TenantRouting, TenantMigrationState
from eventsource.migration.repositories import PostgreSQLTenantRoutingRepository

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.schemas.tenant import TenantStoreMapping

logger = logging.getLogger(__name__)

# Default store ID for new tenants
DEFAULT_STORE_ID = "default"


class TenantStoreMappingService:
    """
    Service for managing tenant-to-event-store mappings.

    This service wraps the eventsource-py TenantRoutingRepository to provide
    a simpler interface for the tenant management API. It handles:

    - Getting current store mapping for a tenant
    - Setting store mapping for a tenant
    - Listing all mappings
    - Integration with the migration system

    Example:
        service = TenantStoreMappingService()

        # Get mapping for a tenant
        mapping = await service.get_mapping(tenant_id)

        # Set mapping for a tenant
        await service.set_mapping(tenant_id, "dedicated-store-1")
    """

    def __init__(self, session: Optional[AsyncSession] = None):
        """
        Initialize the service.

        Args:
            session: Optional database session. If not provided,
                    will create one per operation.
        """
        self._session = session
        self._routing_repo: Optional[PostgreSQLTenantRoutingRepository] = None

    async def _get_repo(
        self, session: Optional[AsyncSession] = None
    ) -> PostgreSQLTenantRoutingRepository:
        """Get or create the routing repository."""
        if self._routing_repo is None:
            self._routing_repo = PostgreSQLTenantRoutingRepository(
                session_factory=AsyncSessionLocal,
            )
        return self._routing_repo

    async def get_mapping(self, tenant_id: UUID) -> TenantStoreMapping:
        """
        Get the event store mapping for a tenant.

        If no mapping exists, returns a default mapping pointing
        to the default store.

        Args:
            tenant_id: Tenant UUID

        Returns:
            TenantStoreMapping with current routing state
        """
        try:
            repo = await self._get_repo()
            routing = await repo.get_routing(tenant_id)

            if routing is None:
                # No mapping exists, return default
                return TenantStoreMapping(
                    tenant_id=tenant_id,
                    store_id=DEFAULT_STORE_ID,
                    migration_state="NORMAL",
                )

            return TenantStoreMapping(
                tenant_id=routing.tenant_id,
                store_id=routing.store_id,
                migration_state=routing.migration_state.value,
                target_store_id=routing.target_store_id,
                active_migration_id=routing.active_migration_id,
            )
        except Exception as e:
            logger.error(
                "Failed to get tenant mapping",
                extra={"tenant_id": str(tenant_id), "error": str(e)},
                exc_info=True,
            )
            # Return default on error
            return TenantStoreMapping(
                tenant_id=tenant_id,
                store_id=DEFAULT_STORE_ID,
                migration_state="NORMAL",
            )

    async def set_mapping(
        self,
        tenant_id: UUID,
        store_id: str,
    ) -> TenantStoreMapping:
        """
        Set the event store mapping for a tenant.

        This sets the primary store for the tenant. If the tenant
        already has a mapping, this will update it (only if not
        currently migrating).

        Args:
            tenant_id: Tenant UUID
            store_id: Target store ID

        Returns:
            Updated TenantStoreMapping

        Raises:
            ValueError: If tenant is currently migrating
        """
        repo = await self._get_repo()

        # Check current state
        current = await repo.get_routing(tenant_id)
        if current and current.is_migrating:
            raise ValueError(
                f"Cannot change store mapping for tenant {tenant_id}: "
                f"migration in progress (state: {current.migration_state.value})"
            )

        # Set the new mapping
        await repo.set_routing(tenant_id, store_id)

        logger.info(
            "Tenant store mapping updated",
            extra={
                "tenant_id": str(tenant_id),
                "store_id": store_id,
            },
        )

        return TenantStoreMapping(
            tenant_id=tenant_id,
            store_id=store_id,
            migration_state="NORMAL",
        )

    async def get_or_create_mapping(
        self,
        tenant_id: UUID,
    ) -> TenantStoreMapping:
        """
        Get mapping for tenant, creating default if none exists.

        This is useful during tenant creation to ensure a mapping
        always exists.

        Args:
            tenant_id: Tenant UUID

        Returns:
            TenantStoreMapping (existing or newly created)
        """
        repo = await self._get_repo()

        # Use get_or_default which handles upsert
        routing = await repo.get_or_default(tenant_id, DEFAULT_STORE_ID)

        return TenantStoreMapping(
            tenant_id=routing.tenant_id,
            store_id=routing.store_id,
            migration_state=routing.migration_state.value,
            target_store_id=routing.target_store_id,
            active_migration_id=routing.active_migration_id,
        )

    async def list_mappings(
        self,
        tenant_ids: Optional[list[UUID]] = None,
    ) -> dict[UUID, TenantStoreMapping]:
        """
        Get mappings for multiple tenants.

        Args:
            tenant_ids: Optional list of tenant IDs. If None, returns empty dict.

        Returns:
            Dict mapping tenant_id to TenantStoreMapping
        """
        if not tenant_ids:
            return {}

        result = {}
        repo = await self._get_repo()

        for tenant_id in tenant_ids:
            routing = await repo.get_routing(tenant_id)
            if routing:
                result[tenant_id] = TenantStoreMapping(
                    tenant_id=routing.tenant_id,
                    store_id=routing.store_id,
                    migration_state=routing.migration_state.value,
                    target_store_id=routing.target_store_id,
                    active_migration_id=routing.active_migration_id,
                )
            else:
                result[tenant_id] = TenantStoreMapping(
                    tenant_id=tenant_id,
                    store_id=DEFAULT_STORE_ID,
                    migration_state="NORMAL",
                )

        return result

    async def get_tenants_by_store(
        self,
        store_id: str,
    ) -> list[UUID]:
        """
        Get all tenant IDs mapped to a specific store.

        Args:
            store_id: Store ID to query

        Returns:
            List of tenant UUIDs
        """
        # TODO: This requires a new method in TenantRoutingRepository
        # For now, return empty list
        logger.warning(
            "get_tenants_by_store not yet implemented",
            extra={"store_id": store_id},
        )
        return []

    async def get_migrating_tenants(self) -> list[TenantStoreMapping]:
        """
        Get all tenants currently undergoing migration.

        Returns:
            List of TenantStoreMapping for migrating tenants
        """
        # TODO: This requires a new method in TenantRoutingRepository
        # For now, return empty list
        logger.warning("get_migrating_tenants not yet implemented")
        return []
