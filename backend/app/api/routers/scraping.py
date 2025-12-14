"""
Web scraping API endpoints for job management and entity extraction.

This router provides endpoints for:
- Creating and managing scraping jobs
- Controlling job execution (start, stop, pause, resume)
- Retrieving scraped pages and extracted entities
- Querying the knowledge graph
"""

import logging
import math
from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import CurrentUserWithTenant
from app.api.dependencies.tenant import TenantSession
from app.celery_app import celery_app
from app.models.scraping_job import JobStatus, ScrapingJob
from app.tasks.scraping import run_scraping_job
from app.models.scraped_page import ScrapedPage
from app.models.extracted_entity import (
    EntityRelationship,
    EntityType,
    ExtractedEntity,
)
from app.schemas.scraping import (
    CreateScrapingJobRequest,
    ExtractedEntityDetail,
    ExtractedEntitySummary,
    EntityRelationshipResponse,
    GraphQueryRequest,
    GraphQueryResponse,
    GraphNode,
    GraphEdge,
    JobStatusResponse,
    PaginatedResponse,
    ScrapedPageContent,
    ScrapedPageDetail,
    ScrapedPageSummary,
    ScrapingJobResponse,
    ScrapingJobSummary,
    UpdateScrapingJobRequest,
)
from eventsource.stores import ExpectedVersion

from app.eventsourcing.events.scraping import (
    ScrapingJobCreated,
    ScrapingJobCancelled,
)
from app.eventsourcing.stores.factory import get_event_store


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scraping", tags=["scraping"])


# Type alias for tenant-aware database session dependency
# TenantSession handles both authentication and RLS context
DbSession = TenantSession


# =============================================================================
# Helper Functions
# =============================================================================


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


async def _get_job_or_404(
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


async def _get_page_or_404(
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


async def _get_entity_or_404(
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


# =============================================================================
# Job Management Endpoints
# =============================================================================


@router.post(
    "/jobs",
    response_model=ScrapingJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a scraping job",
    description="Creates a new web scraping job with the specified configuration.",
)
async def create_scraping_job(
    request: CreateScrapingJobRequest,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> ScrapingJob:
    """
    Create a new scraping job.

    The job is created in 'pending' status and must be started explicitly
    using the start endpoint.
    """
    # Extract domain from start_url if allowed_domains is empty
    allowed_domains = request.allowed_domains
    if not allowed_domains:
        from urllib.parse import urlparse
        parsed = urlparse(str(request.start_url))
        if parsed.netloc:
            allowed_domains = [parsed.netloc]

    # Create the job
    job = ScrapingJob(
        tenant_id=UUID(user.tenant_id),
        created_by_user_id=user.user_id,
        name=request.name,
        start_url=str(request.start_url),
        allowed_domains=allowed_domains,
        url_patterns=request.url_patterns,
        excluded_patterns=request.excluded_patterns,
        crawl_depth=request.crawl_depth,
        max_pages=request.max_pages,
        crawl_speed=request.crawl_speed,
        respect_robots_txt=request.respect_robots_txt,
        use_llm_extraction=request.use_llm_extraction,
        custom_settings=request.custom_settings,
        status=JobStatus.PENDING,
    )

    db.add(job)
    await db.flush()  # Get the ID

    # Emit domain event
    try:
        event_store = await get_event_store()
        event = ScrapingJobCreated(
            aggregate_id=str(job.id),
            tenant_id=UUID(user.tenant_id),
            job_id=job.id,
            name=job.name,
            start_url=job.start_url,
            created_by=user.user_id,
            config={
                "allowed_domains": allowed_domains,
                "url_patterns": request.url_patterns,
                "excluded_patterns": request.excluded_patterns,
                "crawl_depth": request.crawl_depth,
                "max_pages": request.max_pages,
                "crawl_speed": request.crawl_speed,
                "respect_robots_txt": request.respect_robots_txt,
                "use_llm_extraction": request.use_llm_extraction,
            },
        )
        await event_store.append_events(
            aggregate_id=job.id,
            aggregate_type="ScrapingJob",
            events=[event],
            expected_version=ExpectedVersion.NO_STREAM,
        )
    except Exception as e:
        logger.warning(f"Failed to emit ScrapingJobCreated event: {e}")

    logger.info(
        "Scraping job created",
        extra={
            "job_id": str(job.id),
            "tenant_id": user.tenant_id,
            "start_url": job.start_url,
        },
    )

    return job


@router.get(
    "/jobs",
    response_model=PaginatedResponse,
    summary="List scraping jobs",
    description="Returns a paginated list of scraping jobs for the tenant.",
)
async def list_scraping_jobs(
    user: CurrentUserWithTenant,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[JobStatus] = Query(
        None,
        alias="status",
        description="Filter by job status",
    ),
) -> PaginatedResponse:
    """
    List all scraping jobs for the authenticated tenant.

    Results are paginated and can be filtered by status.
    """
    # Build query
    query = select(ScrapingJob).where(
        ScrapingJob.tenant_id == UUID(user.tenant_id)
    )

    if status_filter:
        query = query.where(ScrapingJob.status == status_filter)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get paginated results
    offset = (page - 1) * page_size
    query = query.order_by(ScrapingJob.created_at.desc())
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    jobs = result.scalars().all()

    # Convert to summary format
    items = [
        ScrapingJobSummary(
            id=job.id,
            name=job.name,
            start_url=job.start_url,
            status=job.status,
            pages_crawled=job.pages_crawled,
            entities_extracted=job.entities_extracted,
            created_at=job.created_at,
        )
        for job in jobs
    ]

    return _build_paginated_response(items, total, page, page_size)


@router.get(
    "/jobs/{job_id}",
    response_model=ScrapingJobResponse,
    summary="Get a scraping job",
    description="Returns the full details of a specific scraping job.",
)
async def get_scraping_job(
    job_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> ScrapingJob:
    """Get a specific scraping job by ID."""
    return await _get_job_or_404(db, job_id, user.tenant_id)


@router.patch(
    "/jobs/{job_id}",
    response_model=ScrapingJobResponse,
    summary="Update a scraping job",
    description="Updates a scraping job configuration. Only allowed for pending jobs.",
)
async def update_scraping_job(
    job_id: UUID,
    request: UpdateScrapingJobRequest,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> ScrapingJob:
    """
    Update a scraping job.

    Only jobs in 'pending' status can be updated.
    """
    job = await _get_job_or_404(db, job_id, user.tenant_id)

    if job.status != JobStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot update job in '{job.status.value}' status. Only pending jobs can be updated.",
        )

    # Update fields if provided
    if request.name is not None:
        job.name = request.name
    if request.crawl_depth is not None:
        job.crawl_depth = request.crawl_depth
    if request.max_pages is not None:
        job.max_pages = request.max_pages
    if request.crawl_speed is not None:
        job.crawl_speed = request.crawl_speed
    if request.use_llm_extraction is not None:
        job.use_llm_extraction = request.use_llm_extraction

    job.updated_at = datetime.now(timezone.utc)

    logger.info(
        "Scraping job updated",
        extra={"job_id": str(job_id), "tenant_id": user.tenant_id},
    )

    return job


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a scraping job",
    description="Deletes a scraping job and all associated data.",
)
async def delete_scraping_job(
    job_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> None:
    """
    Delete a scraping job.

    Running jobs will be cancelled before deletion.
    All associated scraped pages and extracted entities will also be deleted.
    """
    job = await _get_job_or_404(db, job_id, user.tenant_id)

    # Cancel Celery task if running or queued
    if job.status in (JobStatus.RUNNING, JobStatus.QUEUED) and job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True)
        logger.info(
            "Celery task revoked before job deletion",
            extra={
                "job_id": str(job_id),
                "celery_task_id": job.celery_task_id,
            },
        )

    await db.delete(job)

    logger.info(
        "Scraping job deleted",
        extra={"job_id": str(job_id), "tenant_id": user.tenant_id},
    )


@router.get(
    "/jobs/{job_id}/status",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Returns the current status and progress of a scraping job.",
)
async def get_job_status(
    job_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> JobStatusResponse:
    """Get the current status and progress of a scraping job."""
    job = await _get_job_or_404(db, job_id, user.tenant_id)

    # Calculate estimated progress
    estimated_progress = None
    if job.status == JobStatus.RUNNING and job.max_pages > 0:
        estimated_progress = min(1.0, job.pages_crawled / job.max_pages)
    elif job.status == JobStatus.COMPLETED:
        estimated_progress = 1.0

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        pages_crawled=job.pages_crawled,
        entities_extracted=job.entities_extracted,
        errors_count=job.errors_count,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        estimated_progress=estimated_progress,
    )


# =============================================================================
# Job Control Endpoints
# =============================================================================


@router.post(
    "/jobs/{job_id}/start",
    response_model=JobStatusResponse,
    summary="Start a scraping job",
    description="Starts or resumes a scraping job.",
)
async def start_scraping_job(
    job_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> JobStatusResponse:
    """
    Start a scraping job.

    Jobs in 'pending' or 'paused' status can be started.
    """
    job = await _get_job_or_404(db, job_id, user.tenant_id)

    if job.status not in (JobStatus.PENDING, JobStatus.PAUSED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start job in '{job.status.value}' status. Only pending or paused jobs can be started.",
        )

    # Queue the job for execution
    job.status = JobStatus.QUEUED
    job.updated_at = datetime.now(timezone.utc)

    # Submit to Celery for background processing
    task = run_scraping_job.delay(str(job.id), user.tenant_id)
    job.celery_task_id = task.id

    logger.info(
        "Scraping job queued",
        extra={
            "job_id": str(job_id),
            "tenant_id": user.tenant_id,
            "celery_task_id": task.id,
        },
    )

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        pages_crawled=job.pages_crawled,
        entities_extracted=job.entities_extracted,
        errors_count=job.errors_count,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        estimated_progress=0.0,
    )


@router.post(
    "/jobs/{job_id}/stop",
    response_model=JobStatusResponse,
    summary="Stop a scraping job",
    description="Stops a running scraping job.",
)
async def stop_scraping_job(
    job_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> JobStatusResponse:
    """
    Stop a running scraping job.

    The job will be cancelled and cannot be resumed.
    """
    job = await _get_job_or_404(db, job_id, user.tenant_id)

    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot stop job in '{job.status.value}' status. Only queued or running jobs can be stopped.",
        )

    # Cancel the Celery task if running
    if job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True)
        logger.info(
            "Celery task revoked",
            extra={
                "job_id": str(job_id),
                "celery_task_id": job.celery_task_id,
            },
        )

    job.status = JobStatus.CANCELLED
    job.updated_at = datetime.now(timezone.utc)

    # Emit domain event
    try:
        event_store = await get_event_store()
        event = ScrapingJobCancelled(
            aggregate_id=str(job.id),
            tenant_id=UUID(user.tenant_id),
            job_id=job.id,
            cancelled_by=user.user_id,
            cancelled_at=datetime.now(timezone.utc),
        )
        await event_store.append_events(
            aggregate_id=job.id,
            aggregate_type="ScrapingJob",
            events=[event],
            expected_version=ExpectedVersion.ANY,
        )
    except Exception as e:
        logger.warning(f"Failed to emit ScrapingJobCancelled event: {e}")

    logger.info(
        "Scraping job cancelled",
        extra={"job_id": str(job_id), "tenant_id": user.tenant_id},
    )

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        pages_crawled=job.pages_crawled,
        entities_extracted=job.entities_extracted,
        errors_count=job.errors_count,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        estimated_progress=None,
    )


@router.post(
    "/jobs/{job_id}/pause",
    response_model=JobStatusResponse,
    summary="Pause a scraping job",
    description="Pauses a running scraping job. Can be resumed later.",
)
async def pause_scraping_job(
    job_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> JobStatusResponse:
    """
    Pause a running scraping job.

    The job can be resumed later using the start endpoint.
    """
    job = await _get_job_or_404(db, job_id, user.tenant_id)

    if job.status != JobStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot pause job in '{job.status.value}' status. Only running jobs can be paused.",
        )

    # Revoke the Celery task to pause execution
    # Note: This is a hard pause - the task is terminated and can be resumed later
    # by calling the start endpoint, which will submit a new Celery task.
    # A graceful pause (checkpointing mid-crawl) would require the spider to
    # periodically check a "pause requested" flag and save its state.
    if job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True)
        logger.info(
            "Celery task revoked for pause",
            extra={
                "job_id": str(job_id),
                "celery_task_id": job.celery_task_id,
            },
        )

    job.status = JobStatus.PAUSED
    job.celery_task_id = None  # Clear task ID since it's been revoked
    job.updated_at = datetime.now(timezone.utc)

    logger.info(
        "Scraping job paused",
        extra={"job_id": str(job_id), "tenant_id": user.tenant_id},
    )

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        pages_crawled=job.pages_crawled,
        entities_extracted=job.entities_extracted,
        errors_count=job.errors_count,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        estimated_progress=None,
    )


# =============================================================================
# Scraped Pages Endpoints
# =============================================================================


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
    extraction_status: Optional[str] = Query(
        None,
        description="Filter by extraction status (pending, completed, failed)",
    ),
) -> PaginatedResponse:
    """List all pages scraped by a job."""
    # Verify job exists and belongs to tenant
    await _get_job_or_404(db, job_id, user.tenant_id)

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

    return _build_paginated_response(items, total, page, page_size)


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
    await _get_job_or_404(db, job_id, user.tenant_id)

    page = await _get_page_or_404(db, page_id, user.tenant_id)

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
    await _get_job_or_404(db, job_id, user.tenant_id)

    page = await _get_page_or_404(db, page_id, user.tenant_id)

    # Verify page belongs to job
    if page.job_id != job_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found in this job",
        )

    return page


# =============================================================================
# Extracted Entities Endpoints
# =============================================================================


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
    entity_type: Optional[EntityType] = Query(
        None,
        description="Filter by entity type",
    ),
) -> PaginatedResponse:
    """List all entities extracted from a job."""
    # Verify job exists and belongs to tenant
    await _get_job_or_404(db, job_id, user.tenant_id)

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
        query = query.where(ExtractedEntity.entity_type == entity_type)

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

    return _build_paginated_response(items, total, page, page_size)


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
    entity_type: Optional[EntityType] = Query(
        None,
        description="Filter by entity type",
    ),
    search: Optional[str] = Query(
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
        query = query.where(ExtractedEntity.entity_type == entity_type)

    if search:
        query = query.where(
            ExtractedEntity.name.ilike(f"%{search}%")
        )

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

    return _build_paginated_response(items, total, page, page_size)


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
    return await _get_entity_or_404(db, entity_id, user.tenant_id)


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
    await _get_entity_or_404(db, entity_id, user.tenant_id)

    # Get relationships where entity is source or target
    result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.tenant_id == UUID(user.tenant_id),
            (
                (EntityRelationship.source_entity_id == entity_id) |
                (EntityRelationship.target_entity_id == entity_id)
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


# =============================================================================
# Knowledge Graph Query Endpoints
# =============================================================================


@router.post(
    "/graph/query",
    response_model=GraphQueryResponse,
    summary="Query knowledge graph",
    description="Query the knowledge graph starting from an entity.",
)
async def query_graph(
    request: GraphQueryRequest,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> GraphQueryResponse:
    """
    Query the knowledge graph.

    Returns nodes and edges starting from the specified entity,
    traversing up to the specified depth.
    """
    # Verify starting entity exists
    start_entity = await _get_entity_or_404(db, request.entity_id, user.tenant_id)

    # For now, query from PostgreSQL
    # TODO: Query from Neo4j when available
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    visited: set[UUID] = set()

    async def traverse(entity_id: UUID, current_depth: int) -> None:
        if entity_id in visited or current_depth > request.depth:
            return
        if len(nodes) >= request.limit:
            return

        visited.add(entity_id)

        # Get entity
        result = await db.execute(
            select(ExtractedEntity).where(
                ExtractedEntity.id == entity_id,
                ExtractedEntity.tenant_id == UUID(user.tenant_id),
            )
        )
        entity = result.scalar_one_or_none()
        if not entity:
            return

        # Filter by entity type if specified
        if request.entity_types and entity.entity_type not in request.entity_types:
            return

        nodes.append(
            GraphNode(
                id=entity.id,
                entity_type=entity.entity_type,
                name=entity.name,
                properties=entity.properties,
            )
        )

        # Get relationships
        rel_query = select(EntityRelationship).where(
            EntityRelationship.tenant_id == UUID(user.tenant_id),
            (
                (EntityRelationship.source_entity_id == entity_id) |
                (EntityRelationship.target_entity_id == entity_id)
            ),
        )

        if request.relationship_types:
            rel_query = rel_query.where(
                EntityRelationship.relationship_type.in_(request.relationship_types)
            )

        rel_result = await db.execute(rel_query)
        relationships = rel_result.scalars().all()

        for rel in relationships:
            # Add edge
            edges.append(
                GraphEdge(
                    source=rel.source_entity_id,
                    target=rel.target_entity_id,
                    relationship_type=rel.relationship_type,
                    confidence=rel.confidence_score,
                )
            )

            # Traverse connected entity
            next_id = (
                rel.target_entity_id
                if rel.source_entity_id == entity_id
                else rel.source_entity_id
            )
            await traverse(next_id, current_depth + 1)

    await traverse(request.entity_id, 0)

    return GraphQueryResponse(
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
        truncated=len(nodes) >= request.limit,
    )
