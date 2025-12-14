"""
Extracted entities API endpoints.

This router provides endpoints for:
- Listing extracted entities with pagination
- Retrieving entity details
- Searching entities
"""

import logging
import math
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import CurrentUserWithTenant
from app.api.dependencies.tenant import TenantSession
from app.models.extracted_entity import (
    EntityRelationship,
    EntityType,
    ExtractionMethod,
    ExtractedEntity,
)
from app.schemas.scraping import (
    ExtractedEntityDetail,
    ExtractedEntitySummary,
    EntityRelationshipResponse,
    PaginatedResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/entities", tags=["entities"])


# Type alias for tenant-aware database session dependency
DbSession = TenantSession


def _build_paginated_response(
    items: list,
    total: int,
    page: int,
    page_size: int,
) -> PaginatedResponse:
    """Build a paginated response with metadata."""
    pages = max(1, math.ceil(total / page_size))
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )


@router.get(
    "",
    response_model=PaginatedResponse,
    summary="List extracted entities",
    description="Get a paginated list of extracted entities for the tenant.",
)
async def list_entities(
    user: CurrentUserWithTenant,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    extraction_method: Optional[str] = Query(None, description="Filter by extraction method"),
    search: Optional[str] = Query(None, description="Search by name"),
    job_id: Optional[UUID] = Query(None, description="Filter by scraping job ID"),
) -> PaginatedResponse:
    """
    Get a paginated list of extracted entities.

    Entities are filtered by tenant automatically via RLS.
    """
    tenant_id = UUID(user.tenant_id)

    # Build base query
    query = select(ExtractedEntity).where(
        ExtractedEntity.tenant_id == tenant_id
    )

    # Apply filters
    if entity_type:
        try:
            type_enum = EntityType(entity_type)
            query = query.where(ExtractedEntity.entity_type == type_enum)
        except ValueError:
            pass  # Ignore invalid types

    if extraction_method:
        try:
            method_enum = ExtractionMethod(extraction_method)
            query = query.where(ExtractedEntity.extraction_method == method_enum)
        except ValueError:
            pass  # Ignore invalid methods

    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            ExtractedEntity.name.ilike(search_pattern) |
            ExtractedEntity.normalized_name.ilike(search_pattern)
        )

    if job_id:
        # Need to join with scraped_pages to filter by job
        from app.models.scraped_page import ScrapedPage
        query = query.join(
            ScrapedPage,
            ExtractedEntity.source_page_id == ScrapedPage.id,
        ).where(ScrapedPage.job_id == job_id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(ExtractedEntity.created_at.desc())
    query = query.offset(offset).limit(page_size)

    # Execute query
    result = await db.execute(query)
    entities = result.scalars().all()

    # Convert to response format
    items = [
        ExtractedEntitySummary(
            id=e.id,
            entity_type=e.entity_type,
            name=e.name,
            extraction_method=e.extraction_method,
            confidence_score=e.confidence_score,
            created_at=e.created_at,
        )
        for e in entities
    ]

    return _build_paginated_response(items, total, page, page_size)


@router.get(
    "/{entity_id}",
    response_model=ExtractedEntityDetail,
    summary="Get entity details",
    description="Get detailed information about a specific entity.",
)
async def get_entity(
    entity_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> ExtractedEntityDetail:
    """Get detailed information about a specific entity."""
    tenant_id = UUID(user.tenant_id)

    result = await db.execute(
        select(ExtractedEntity).where(
            ExtractedEntity.id == entity_id,
            ExtractedEntity.tenant_id == tenant_id,
        )
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    return ExtractedEntityDetail.model_validate(entity)


@router.get(
    "/{entity_id}/relationships",
    response_model=PaginatedResponse,
    summary="Get entity relationships",
    description="Get all relationships for a specific entity.",
)
async def get_entity_relationships(
    entity_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    direction: str = Query(
        "both",
        description="Relationship direction: 'outgoing', 'incoming', or 'both'",
    ),
) -> PaginatedResponse:
    """Get all relationships for a specific entity."""
    tenant_id = UUID(user.tenant_id)

    # Verify entity exists
    entity_result = await db.execute(
        select(ExtractedEntity).where(
            ExtractedEntity.id == entity_id,
            ExtractedEntity.tenant_id == tenant_id,
        )
    )
    if not entity_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    # Build relationship query based on direction
    base_query = select(EntityRelationship).where(
        EntityRelationship.tenant_id == tenant_id
    )

    if direction == "outgoing":
        base_query = base_query.where(EntityRelationship.source_entity_id == entity_id)
    elif direction == "incoming":
        base_query = base_query.where(EntityRelationship.target_entity_id == entity_id)
    else:  # both
        base_query = base_query.where(
            (EntityRelationship.source_entity_id == entity_id) |
            (EntityRelationship.target_entity_id == entity_id)
        )

    # Get total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = base_query.order_by(EntityRelationship.created_at.desc())
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    relationships = result.scalars().all()

    # Get related entity names for enrichment
    entity_ids = set()
    for rel in relationships:
        entity_ids.add(rel.source_entity_id)
        entity_ids.add(rel.target_entity_id)

    entities_result = await db.execute(
        select(ExtractedEntity).where(ExtractedEntity.id.in_(entity_ids))
    )
    entities_map = {e.id: e for e in entities_result.scalars().all()}

    # Convert to response format
    items = []
    for rel in relationships:
        source = entities_map.get(rel.source_entity_id)
        target = entities_map.get(rel.target_entity_id)

        items.append(
            EntityRelationshipResponse(
                id=rel.id,
                source_entity_id=rel.source_entity_id,
                target_entity_id=rel.target_entity_id,
                relationship_type=rel.relationship_type,
                properties=rel.properties or {},
                confidence_score=rel.confidence_score,
                synced_to_neo4j=rel.synced_to_neo4j,
                created_at=rel.created_at,
                source_entity_name=source.name if source else None,
                source_entity_type=source.entity_type if source else None,
                target_entity_name=target.name if target else None,
                target_entity_type=target.entity_type if target else None,
            )
        )

    return _build_paginated_response(items, total, page, page_size)
