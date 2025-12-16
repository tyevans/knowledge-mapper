"""
API endpoints for managing extraction providers.

Provides CRUD operations for tenant-scoped extraction provider
configurations, including connection testing.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.dependencies.auth import CurrentUser
from app.api.dependencies.tenant import TenantSession
from app.core.encryption import get_encryption_service
from app.extraction.factory import ExtractionProviderFactory, ProviderConfigError
from app.models.extraction_provider import ExtractionProvider
from app.schemas.extraction_provider import (
    PROVIDER_TYPE_INFO,
    CreateExtractionProviderRequest,
    ExtractionProviderResponse,
    ProviderTypeInfo,
    TestConnectionResponse,
    UpdateExtractionProviderRequest,
)

router = APIRouter(prefix="/extraction-providers", tags=["extraction-providers"])


@router.post(
    "",
    response_model=ExtractionProviderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create extraction provider",
    description="Create a new extraction provider for the tenant. API keys are encrypted at rest.",
)
async def create_extraction_provider(
    request: CreateExtractionProviderRequest,
    user: CurrentUser,
    db: TenantSession,
) -> ExtractionProviderResponse:
    """Create a new extraction provider for the tenant."""
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )

    tenant_id = UUID(user.tenant_id)

    # Validate configuration for provider type
    validation_errors = ExtractionProviderFactory.validate_config(
        request.provider_type,
        request.config,
    )
    if validation_errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": validation_errors},
        )

    # Encrypt API key if provided
    config = dict(request.config)
    if "api_key" in config and config["api_key"]:
        encryption = get_encryption_service()
        config["api_key"] = encryption.encrypt(
            config["api_key"],
            tenant_id,
            field_name="api_key",
        )

    # If setting as default, unset other defaults
    if request.is_default:
        await db.execute(
            select(ExtractionProvider)
            .where(
                ExtractionProvider.tenant_id == tenant_id,
                ExtractionProvider.is_default.is_(True),
            )
        )
        result = await db.execute(
            select(ExtractionProvider).where(
                ExtractionProvider.tenant_id == tenant_id,
                ExtractionProvider.is_default.is_(True),
            )
        )
        for existing in result.scalars():
            existing.is_default = False

    provider = ExtractionProvider(
        tenant_id=tenant_id,
        name=request.name,
        provider_type=request.provider_type,
        config=config,
        default_model=request.default_model,
        embedding_model=request.embedding_model,
        is_active=request.is_active,
        is_default=request.is_default,
        rate_limit_rpm=request.rate_limit_rpm,
        max_context_length=request.max_context_length,
        timeout_seconds=request.timeout_seconds,
    )

    db.add(provider)
    await db.flush()
    await db.refresh(provider)

    return ExtractionProviderResponse.from_orm_masked(provider)


@router.get(
    "",
    response_model=list[ExtractionProviderResponse],
    summary="List extraction providers",
    description="List all extraction providers for the tenant.",
)
async def list_extraction_providers(
    user: CurrentUser,
    db: TenantSession,
    active_only: bool = True,
) -> list[ExtractionProviderResponse]:
    """List all extraction providers for the tenant."""
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )

    query = select(ExtractionProvider).where(
        ExtractionProvider.tenant_id == UUID(user.tenant_id)
    )

    if active_only:
        query = query.where(ExtractionProvider.is_active.is_(True))

    query = query.order_by(ExtractionProvider.name)

    result = await db.execute(query)
    providers = result.scalars().all()

    return [ExtractionProviderResponse.from_orm_masked(p) for p in providers]


@router.get(
    "/types",
    response_model=list[ProviderTypeInfo],
    summary="List provider types",
    description="List available extraction provider types with metadata.",
)
async def list_provider_types() -> list[ProviderTypeInfo]:
    """List available provider types with metadata."""
    return list(PROVIDER_TYPE_INFO.values())


@router.get(
    "/{provider_id}",
    response_model=ExtractionProviderResponse,
    summary="Get extraction provider",
    description="Get a specific extraction provider by ID.",
)
async def get_extraction_provider(
    provider_id: UUID,
    user: CurrentUser,
    db: TenantSession,
) -> ExtractionProviderResponse:
    """Get a specific extraction provider."""
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )

    result = await db.execute(
        select(ExtractionProvider).where(
            ExtractionProvider.id == provider_id,
            ExtractionProvider.tenant_id == UUID(user.tenant_id),
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )

    return ExtractionProviderResponse.from_orm_masked(provider)


@router.patch(
    "/{provider_id}",
    response_model=ExtractionProviderResponse,
    summary="Update extraction provider",
    description="Update an extraction provider. Only provided fields are updated.",
)
async def update_extraction_provider(
    provider_id: UUID,
    request: UpdateExtractionProviderRequest,
    user: CurrentUser,
    db: TenantSession,
) -> ExtractionProviderResponse:
    """Update an extraction provider."""
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )

    tenant_id = UUID(user.tenant_id)

    result = await db.execute(
        select(ExtractionProvider).where(
            ExtractionProvider.id == provider_id,
            ExtractionProvider.tenant_id == tenant_id,
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )

    # Update fields if provided
    if request.name is not None:
        provider.name = request.name

    if request.default_model is not None:
        provider.default_model = request.default_model

    if request.embedding_model is not None:
        provider.embedding_model = request.embedding_model

    if request.is_active is not None:
        provider.is_active = request.is_active

    if request.is_default is not None:
        if request.is_default:
            # Unset other defaults
            other_result = await db.execute(
                select(ExtractionProvider).where(
                    ExtractionProvider.tenant_id == tenant_id,
                    ExtractionProvider.is_default.is_(True),
                    ExtractionProvider.id != provider_id,
                )
            )
            for other in other_result.scalars():
                other.is_default = False
        provider.is_default = request.is_default

    if request.rate_limit_rpm is not None:
        provider.rate_limit_rpm = request.rate_limit_rpm

    if request.max_context_length is not None:
        provider.max_context_length = request.max_context_length

    if request.timeout_seconds is not None:
        provider.timeout_seconds = request.timeout_seconds

    if request.config is not None:
        # Encrypt API key if being updated
        config = dict(request.config)
        if "api_key" in config and config["api_key"]:
            encryption = get_encryption_service()
            config["api_key"] = encryption.encrypt(
                config["api_key"],
                tenant_id,
                field_name="api_key",
            )
        provider.config = config

    provider.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(provider)

    return ExtractionProviderResponse.from_orm_masked(provider)


@router.delete(
    "/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete extraction provider",
    description="Delete an extraction provider. Jobs using this provider will fall back to defaults.",
)
async def delete_extraction_provider(
    provider_id: UUID,
    user: CurrentUser,
    db: TenantSession,
) -> None:
    """Delete an extraction provider."""
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )

    result = await db.execute(
        select(ExtractionProvider).where(
            ExtractionProvider.id == provider_id,
            ExtractionProvider.tenant_id == UUID(user.tenant_id),
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )

    await db.delete(provider)


@router.post(
    "/{provider_id}/test",
    response_model=TestConnectionResponse,
    summary="Test provider connection",
    description="Test connectivity to an extraction provider.",
)
async def test_provider_connection(
    provider_id: UUID,
    user: CurrentUser,
    db: TenantSession,
) -> TestConnectionResponse:
    """Test connectivity to an extraction provider."""
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )

    tenant_id = UUID(user.tenant_id)

    result = await db.execute(
        select(ExtractionProvider).where(
            ExtractionProvider.id == provider_id,
            ExtractionProvider.tenant_id == tenant_id,
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )

    try:
        service = ExtractionProviderFactory.create_service(provider, tenant_id)
        health = await service.health_check()

        return TestConnectionResponse(
            success=health.get("status") == "healthy",
            details=health,
        )

    except ProviderConfigError as e:
        return TestConnectionResponse(
            success=False,
            details={
                "status": "unhealthy",
                "error": str(e),
                "error_type": "configuration",
            },
        )

    except NotImplementedError as e:
        return TestConnectionResponse(
            success=False,
            details={
                "status": "unhealthy",
                "error": str(e),
                "error_type": "not_implemented",
            },
        )

    except Exception as e:
        return TestConnectionResponse(
            success=False,
            details={
                "status": "unhealthy",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
