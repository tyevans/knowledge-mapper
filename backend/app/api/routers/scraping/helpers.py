"""
Shared helpers for scraping routers.

This module provides common utilities used across scraping router modules,
following the DRY (Don't Repeat Yourself) principle.
"""

import math
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extracted_entity import ExtractedEntity
from app.models.scraped_page import ScrapedPage
from app.models.scraping_job import ScrapingJob
from app.schemas.scraping import PaginatedResponse


def build_paginated_response(
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


async def get_job_or_404(
    db: AsyncSession,
    job_id: UUID,
    tenant_id: str,
) -> ScrapingJob:
    """Get a scraping job by ID or raise 404."""
    result = await db.execute(
        select(ScrapingJob).where(
            ScrapingJob.id == job_id,
            ScrapingJob.tenant_id == UUID(tenant_id),
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scraping job not found",
        )
    return job


async def get_page_or_404(
    db: AsyncSession,
    page_id: UUID,
    tenant_id: str,
) -> ScrapedPage:
    """Get a scraped page by ID or raise 404."""
    result = await db.execute(
        select(ScrapedPage).where(
            ScrapedPage.id == page_id,
            ScrapedPage.tenant_id == UUID(tenant_id),
        )
    )
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scraped page not found",
        )
    return page


async def get_entity_or_404(
    db: AsyncSession,
    entity_id: UUID,
    tenant_id: str,
) -> ExtractedEntity:
    """Get an extracted entity by ID or raise 404."""
    result = await db.execute(
        select(ExtractedEntity).where(
            ExtractedEntity.id == entity_id,
            ExtractedEntity.tenant_id == UUID(tenant_id),
        )
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )
    return entity
