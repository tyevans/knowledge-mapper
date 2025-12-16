"""Domains API router for adaptive extraction.

Provides endpoints for listing available domains and their schemas,
enabling the frontend to display domain options and schema details.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies.auth import CurrentUser
from app.extraction.domains import (
    DomainSchema,
    DomainSchemaRegistry,
    DomainSummary,
    get_registry_dependency,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/domains", tags=["domains"])


# ==============================================================================
# Response Models
# ==============================================================================


class DomainsListResponse(BaseModel):
    """Response for listing all available domains."""

    domains: list[DomainSummary] = Field(
        ...,
        description="List of available domain summaries",
    )
    count: int = Field(
        ...,
        ge=0,
        description="Total number of available domains",
    )


class EntityTypeDetail(BaseModel):
    """Detailed entity type information for API responses."""

    id: str = Field(..., description="Entity type identifier")
    description: str = Field(..., description="Human-readable description")
    properties: list[dict] = Field(
        default_factory=list,
        description="Entity properties with name, type, description, required",
    )
    examples: list[str] = Field(
        default_factory=list,
        description="Example entity names for this type",
    )


class RelationshipTypeDetail(BaseModel):
    """Detailed relationship type information for API responses."""

    id: str = Field(..., description="Relationship type identifier")
    description: str = Field(..., description="Human-readable description")
    valid_source_types: list[str] = Field(
        default_factory=list,
        description="Valid source entity types (empty means any)",
    )
    valid_target_types: list[str] = Field(
        default_factory=list,
        description="Valid target entity types (empty means any)",
    )
    bidirectional: bool = Field(
        default=False,
        description="Whether the relationship is bidirectional",
    )


class DomainDetailResponse(BaseModel):
    """Response for domain detail with full schema information."""

    domain_id: str = Field(..., description="Unique domain identifier")
    display_name: str = Field(..., description="Human-readable domain name")
    description: str = Field(..., description="Domain description")
    entity_types: list[EntityTypeDetail] = Field(
        ...,
        description="Entity type definitions for this domain",
    )
    relationship_types: list[RelationshipTypeDetail] = Field(
        ...,
        description="Relationship type definitions for this domain",
    )
    version: str = Field(..., description="Schema version (semver format)")

    @classmethod
    def from_schema(cls, schema: DomainSchema) -> "DomainDetailResponse":
        """Create response from DomainSchema.

        Args:
            schema: The full DomainSchema to convert

        Returns:
            DomainDetailResponse with all schema details
        """
        return cls(
            domain_id=schema.domain_id,
            display_name=schema.display_name,
            description=schema.description,
            entity_types=[
                EntityTypeDetail(
                    id=et.id,
                    description=et.description,
                    properties=[p.model_dump() for p in et.properties],
                    examples=et.examples,
                )
                for et in schema.entity_types
            ],
            relationship_types=[
                RelationshipTypeDetail(
                    id=rt.id,
                    description=rt.description,
                    valid_source_types=rt.valid_source_types,
                    valid_target_types=rt.valid_target_types,
                    bidirectional=rt.bidirectional,
                )
                for rt in schema.relationship_types
            ],
            version=schema.version,
        )


# ==============================================================================
# Dependencies
# ==============================================================================


# Type alias for injecting the domain registry
DomainRegistry = Annotated[DomainSchemaRegistry, Depends(get_registry_dependency)]


# ==============================================================================
# Endpoints
# ==============================================================================


@router.get(
    "",
    response_model=DomainsListResponse,
    summary="List available domains",
    description="Get a list of all available content domains with summary information.",
)
async def list_domains(
    _user: CurrentUser,
    registry: DomainRegistry,
) -> DomainsListResponse:
    """List all available content domains.

    Returns a summary of each domain including entity and relationship
    type counts, suitable for dropdown/selection UI components.

    Requires authentication.
    """
    logger.debug("Listing available domains")

    domains = registry.list_domains()

    logger.info(
        "Listed domains",
        extra={
            "domain_count": len(domains),
            "user_id": _user.user_id,
        },
    )

    return DomainsListResponse(
        domains=domains,
        count=len(domains),
    )


@router.get(
    "/{domain_id}",
    response_model=DomainDetailResponse,
    summary="Get domain details",
    description="Get detailed schema information for a specific domain.",
    responses={
        404: {
            "description": "Domain not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Domain not found: unknown_domain"
                    }
                }
            },
        },
    },
)
async def get_domain(
    domain_id: str,
    _user: CurrentUser,
    registry: DomainRegistry,
) -> DomainDetailResponse:
    """Get detailed information about a specific domain.

    Returns full entity type and relationship type definitions,
    suitable for domain preview and schema inspection.

    Requires authentication.

    Args:
        domain_id: The domain identifier to look up

    Raises:
        HTTPException: 404 if domain is not found
    """
    logger.debug("Getting domain detail", extra={"domain_id": domain_id})

    try:
        schema = registry.get_schema(domain_id)
    except KeyError as e:
        logger.warning(
            "Domain not found",
            extra={
                "domain_id": domain_id,
                "user_id": _user.user_id,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain not found: {domain_id}",
        )

    logger.info(
        "Retrieved domain detail",
        extra={
            "domain_id": domain_id,
            "user_id": _user.user_id,
            "entity_type_count": len(schema.entity_types),
            "relationship_type_count": len(schema.relationship_types),
        },
    )

    return DomainDetailResponse.from_schema(schema)
