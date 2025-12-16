"""
Scraped pages endpoints.

This router handles scraped page operations:
- Listing pages for a job
- Retrieving page details
- Getting page content

Follows Single Responsibility Principle by focusing only on page retrieval.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.dependencies.auth import CurrentUserWithTenant
from app.api.dependencies.tenant import TenantSession
from app.api.routers.scraping.helpers import (
    build_paginated_response,
    get_job_or_404,
    get_page_or_404,
)
from app.models.extracted_entity import ExtractedEntity
from app.models.scraped_page import ScrapedPage
from app.schemas.scraping import (
    PaginatedResponse,
    ScrapedPageContent,
    ScrapedPageDetail,
    ScrapedPageSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scraping"])

# Type alias for tenant-aware database session dependency
DbSession = TenantSession


@router.get(
    "/jobs/{job_id}/pages",
    response_model=PaginatedResponse,
    summary="List scraped pages",
    description="Returns a paginated list of pages scraped by a job.",
)
async def list_scraped_pages(
    job_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    extraction_status: str | None = Query(
        None,
        description="Filter by extraction status (pending, completed, failed)",
    ),
) -> PaginatedResponse:
    """List all pages scraped by a job."""
    # Verify job exists and belongs to tenant
    await get_job_or_404(db, job_id, user.tenant_id)

    # Build query
    query = select(ScrapedPage).where(
        ScrapedPage.job_id == job_id,
        ScrapedPage.tenant_id == UUID(user.tenant_id),
    )

    if extraction_status:
        query = query.where(ScrapedPage.extraction_status == extraction_status)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get paginated results
    offset = (page - 1) * page_size
    query = query.order_by(ScrapedPage.crawled_at.desc())
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    pages = result.scalars().all()

    # Convert to summary format
    items = [
        ScrapedPageSummary(
            id=p.id,
            url=p.url,
            title=p.title,
            http_status=p.http_status,
            depth=p.depth,
            extraction_status=p.extraction_status,
            crawled_at=p.crawled_at,
        )
        for p in pages
    ]

    return build_paginated_response(items, total, page, page_size)


@router.get(
    "/jobs/{job_id}/pages/{page_id}",
    response_model=ScrapedPageDetail,
    summary="Get scraped page details",
    description="Returns detailed information about a specific scraped page.",
)
async def get_scraped_page(
    job_id: UUID,
    page_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> ScrapedPage:
    """Get detailed information about a scraped page."""
    # Verify job exists and belongs to tenant
    await get_job_or_404(db, job_id, user.tenant_id)

    page = await get_page_or_404(db, page_id, user.tenant_id)

    # Verify page belongs to job
    if page.job_id != job_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found in this job",
        )

    # Count schema.org items and entities
    entity_count_result = await db.execute(
        select(func.count()).where(
            ExtractedEntity.source_page_id == page_id,
            ExtractedEntity.tenant_id == UUID(user.tenant_id),
        )
    )
    entity_count = entity_count_result.scalar() or 0

    # Add computed fields
    page.schema_org_count = len(page.schema_org_data) if page.schema_org_data else 0
    page.entity_count = entity_count

    return page


@router.get(
    "/jobs/{job_id}/pages/{page_id}/content",
    response_model=ScrapedPageContent,
    summary="Get scraped page content",
    description="Returns the full content of a scraped page including HTML.",
)
async def get_scraped_page_content(
    job_id: UUID,
    page_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> ScrapedPage:
    """Get the full content of a scraped page."""
    # Verify job exists and belongs to tenant
    await get_job_or_404(db, job_id, user.tenant_id)

    page = await get_page_or_404(db, page_id, user.tenant_id)

    # Verify page belongs to job
    if page.job_id != job_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found in this job",
        )

    return page
