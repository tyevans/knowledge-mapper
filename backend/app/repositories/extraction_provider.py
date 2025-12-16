"""
Repository for ExtractionProvider operations.

This module implements the Repository pattern for ExtractionProvider entities,
following the Dependency Inversion Principle (DIP). Routers depend on this
abstraction rather than directly querying the database.

Benefits:
- Decouples business logic from data access
- Makes routers easier to test (can mock the repository)
- Centralizes query logic for extraction providers
- Follows Single Responsibility Principle

Usage in routers:
    from app.repositories.extraction_provider import (
        ExtractionProviderRepository,
        get_extraction_provider_repository,
    )

    @router.post("/jobs")
    async def create_job(
        repo: ExtractionProviderRepository = Depends(get_extraction_provider_repository),
    ):
        provider = await repo.get_active_by_id(provider_id, tenant_id)
"""

import logging
from abc import ABC, abstractmethod
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.tenant import TenantSession
from app.models.extraction_provider import ExtractionProvider, ExtractionProviderType

logger = logging.getLogger(__name__)


class ExtractionProviderNotFoundError(Exception):
    """Raised when an extraction provider is not found."""

    def __init__(self, provider_id: UUID, tenant_id: UUID):
        self.provider_id = provider_id
        self.tenant_id = tenant_id
        super().__init__(f"Extraction provider {provider_id} not found for tenant {tenant_id}")


class ExtractionProviderInactiveError(Exception):
    """Raised when an extraction provider is inactive."""

    def __init__(self, provider_id: UUID):
        self.provider_id = provider_id
        super().__init__(f"Extraction provider {provider_id} is inactive")


class ExtractionProviderRepositoryProtocol(ABC):
    """Abstract interface for ExtractionProvider repository.

    This protocol defines the contract that any implementation must follow.
    This allows for easy mocking in tests and potential future implementations
    (e.g., caching repository, remote repository).
    """

    @abstractmethod
    async def get_by_id(
        self,
        provider_id: UUID,
        tenant_id: UUID,
    ) -> ExtractionProvider | None:
        """Get an extraction provider by ID.

        Args:
            provider_id: Provider UUID
            tenant_id: Tenant UUID for isolation

        Returns:
            ExtractionProvider or None if not found
        """
        pass

    @abstractmethod
    async def get_active_by_id(
        self,
        provider_id: UUID,
        tenant_id: UUID,
    ) -> ExtractionProvider | None:
        """Get an active extraction provider by ID.

        Args:
            provider_id: Provider UUID
            tenant_id: Tenant UUID for isolation

        Returns:
            ExtractionProvider or None if not found or inactive
        """
        pass

    @abstractmethod
    async def get_default_for_tenant(
        self,
        tenant_id: UUID,
    ) -> ExtractionProvider | None:
        """Get the default extraction provider for a tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Default ExtractionProvider or None if no default set
        """
        pass

    @abstractmethod
    async def list_active_for_tenant(
        self,
        tenant_id: UUID,
        provider_type: ExtractionProviderType | None = None,
    ) -> list[ExtractionProvider]:
        """List all active extraction providers for a tenant.

        Args:
            tenant_id: Tenant UUID
            provider_type: Optional filter by provider type

        Returns:
            List of active ExtractionProvider instances
        """
        pass

    @abstractmethod
    async def require_active_by_id(
        self,
        provider_id: UUID,
        tenant_id: UUID,
    ) -> ExtractionProvider:
        """Get an active extraction provider by ID, raising if not found.

        Args:
            provider_id: Provider UUID
            tenant_id: Tenant UUID for isolation

        Returns:
            ExtractionProvider instance

        Raises:
            ExtractionProviderNotFoundError: If provider not found
            ExtractionProviderInactiveError: If provider is inactive
        """
        pass


class ExtractionProviderRepository(ExtractionProviderRepositoryProtocol):
    """SQLAlchemy implementation of ExtractionProvider repository.

    This repository handles all database operations for ExtractionProvider
    entities. It uses the tenant-aware session which has RLS policies
    automatically applied.
    """

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session (should be tenant-aware)
        """
        self._session = session

    async def get_by_id(
        self,
        provider_id: UUID,
        tenant_id: UUID,
    ) -> ExtractionProvider | None:
        """Get an extraction provider by ID."""
        result = await self._session.execute(
            select(ExtractionProvider).where(
                ExtractionProvider.id == provider_id,
                ExtractionProvider.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_id(
        self,
        provider_id: UUID,
        tenant_id: UUID,
    ) -> ExtractionProvider | None:
        """Get an active extraction provider by ID."""
        result = await self._session.execute(
            select(ExtractionProvider).where(
                ExtractionProvider.id == provider_id,
                ExtractionProvider.tenant_id == tenant_id,
                ExtractionProvider.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_default_for_tenant(
        self,
        tenant_id: UUID,
    ) -> ExtractionProvider | None:
        """Get the default extraction provider for a tenant."""
        result = await self._session.execute(
            select(ExtractionProvider).where(
                ExtractionProvider.tenant_id == tenant_id,
                ExtractionProvider.is_default.is_(True),
                ExtractionProvider.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_active_for_tenant(
        self,
        tenant_id: UUID,
        provider_type: ExtractionProviderType | None = None,
    ) -> list[ExtractionProvider]:
        """List all active extraction providers for a tenant."""
        query = select(ExtractionProvider).where(
            ExtractionProvider.tenant_id == tenant_id,
            ExtractionProvider.is_active.is_(True),
        )

        if provider_type is not None:
            query = query.where(ExtractionProvider.provider_type == provider_type)

        query = query.order_by(
            ExtractionProvider.is_default.desc(),
            ExtractionProvider.name,
        )

        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def require_active_by_id(
        self,
        provider_id: UUID,
        tenant_id: UUID,
    ) -> ExtractionProvider:
        """Get an active extraction provider by ID, raising if not found."""
        # First check if provider exists at all
        provider = await self.get_by_id(provider_id, tenant_id)

        if provider is None:
            logger.warning(
                "Extraction provider not found",
                extra={"provider_id": str(provider_id), "tenant_id": str(tenant_id)},
            )
            raise ExtractionProviderNotFoundError(provider_id, tenant_id)

        if not provider.is_active:
            logger.warning(
                "Extraction provider is inactive",
                extra={"provider_id": str(provider_id), "tenant_id": str(tenant_id)},
            )
            raise ExtractionProviderInactiveError(provider_id)

        return provider


# Dependency injection


async def get_extraction_provider_repository(
    db: TenantSession,
) -> ExtractionProviderRepository:
    """FastAPI dependency for ExtractionProviderRepository.

    Args:
        db: Tenant-aware database session from dependency injection

    Returns:
        ExtractionProviderRepository instance
    """
    return ExtractionProviderRepository(db)


# Type alias for cleaner dependency injection
ExtractionProviderRepo = Annotated[
    ExtractionProviderRepository,
    Depends(get_extraction_provider_repository),
]
