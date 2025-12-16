"""
Job-specific entity endpoints.

This router handles entity operations scoped to a specific job:
- Listing entities for a job
- Getting entity details
- Getting entity relationships

Note: General entity endpoints are in the separate entities.py router.
Follows Single Responsibility Principle by focusing only on job-scoped entities.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.dependencies.auth import CurrentUserWithTenant
from app.api.dependencies.tenant import TenantSession
from app.api.routers.scraping.helpers import (
    build_paginated_response,
    get_entity_or_404,
    get_job_or_404,
)
from app.models.extracted_entity import (
    EntityRelationship,
    ExtractedEntity,
)
from app.models.scraped_page import ScrapedPage
from app.schemas.scraping import (
    EntityRelationshipResponse,
    ExtractedEntityDetail,
    ExtractedEntitySummary,
    PaginatedResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scraping"])

# Type alias for tenant-aware database session dependency
DbSession = TenantSession


@router.get(
    "/jobs/{job_id}/entities",
    response_model=PaginatedResponse,
    summary="List extracted entities",
    description="Returns a paginated list of entities extracted from a job.",
)
async def list_job_entities(
    job_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    entity_type: str | None = Query(
        None,
        description="Filter by entity type (e.g., 'person', 'organization', 'character')",
    ),
) -> PaginatedResponse:
    """List all entities extracted from a job."""
    # Verify job exists and belongs to tenant
    await get_job_or_404(db, job_id, user.tenant_id)

    # Build query - join with pages to filter by job
    query = (
        select(ExtractedEntity)
        .join(ScrapedPage, ExtractedEntity.source_page_id == ScrapedPage.id)
        .where(
            ScrapedPage.job_id == job_id,
            ExtractedEntity.tenant_id == UUID(user.tenant_id),
        )
    )

    if entity_type:
        # entity_type is now a string column
        query = query.where(ExtractedEntity.entity_type == entity_type.lower())

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get paginated results
    offset = (page - 1) * page_size
    query = query.order_by(ExtractedEntity.created_at.desc())
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    entities = result.scalars().all()

    # Convert to summary format
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

    return build_paginated_response(items, total, page, page_size)


@router.get(
    "/entities",
    response_model=PaginatedResponse,
    summary="List all entities",
    description="Returns a paginated list of all extracted entities for the tenant.",
)
async def list_entities(
    user: CurrentUserWithTenant,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    entity_type: str | None = Query(
        None,
        description="Filter by entity type (e.g., 'person', 'organization', 'character')",
    ),
    search: str | None = Query(
        None,
        min_length=1,
        max_length=100,
        description="Search by entity name",
    ),
) -> PaginatedResponse:
    """List all extracted entities for the tenant."""
    query = select(ExtractedEntity).where(
        ExtractedEntity.tenant_id == UUID(user.tenant_id)
    )

    if entity_type:
        # entity_type is now a string column
        query = query.where(ExtractedEntity.entity_type == entity_type.lower())

    if search:
        query = query.where(ExtractedEntity.name.ilike(f"%{search}%"))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get paginated results
    offset = (page - 1) * page_size
    query = query.order_by(ExtractedEntity.created_at.desc())
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    entities = result.scalars().all()

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

    return build_paginated_response(items, total, page, page_size)


@router.get(
    "/entities/{entity_id}",
    response_model=ExtractedEntityDetail,
    summary="Get entity details",
    description="Returns detailed information about a specific entity.",
)
async def get_entity(
    entity_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> ExtractedEntity:
    """Get detailed information about an entity."""
    return await get_entity_or_404(db, entity_id, user.tenant_id)


@router.get(
    "/entities/{entity_id}/relationships",
    response_model=list[EntityRelationshipResponse],
    summary="Get entity relationships",
    description="Returns all relationships for a specific entity.",
)
async def get_entity_relationships(
    entity_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> list[EntityRelationshipResponse]:
    """Get all relationships for an entity."""
    # Verify entity exists
    await get_entity_or_404(db, entity_id, user.tenant_id)

    # Get relationships where entity is source or target
    result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.tenant_id == UUID(user.tenant_id),
            (
                (EntityRelationship.source_entity_id == entity_id)
                | (EntityRelationship.target_entity_id == entity_id)
            ),
        )
    )
    relationships = result.scalars().all()

    # Expand with entity names
    responses = []
    for rel in relationships:
        # Get source entity
        source_result = await db.execute(
            select(ExtractedEntity).where(ExtractedEntity.id == rel.source_entity_id)
        )
        source = source_result.scalar_one_or_none()

        # Get target entity
        target_result = await db.execute(
            select(ExtractedEntity).where(ExtractedEntity.id == rel.target_entity_id)
        )
        target = target_result.scalar_one_or_none()

        responses.append(
            EntityRelationshipResponse(
                id=rel.id,
                source_entity_id=rel.source_entity_id,
                target_entity_id=rel.target_entity_id,
                relationship_type=rel.relationship_type,
                properties=rel.properties,
                confidence_score=rel.confidence_score,
                synced_to_neo4j=rel.synced_to_neo4j,
                created_at=rel.created_at,
                source_entity_name=source.name if source else None,
                source_entity_type=source.entity_type if source else None,
                target_entity_name=target.name if target else None,
                target_entity_type=target.entity_type if target else None,
            )
        )

    return responses
