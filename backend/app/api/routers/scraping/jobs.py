"""
Scraping job CRUD endpoints.

This router handles job management operations:
- Creating scraping jobs
- Listing jobs with pagination
- Retrieving job details
- Updating job configuration
- Deleting jobs

Follows Single Responsibility Principle by focusing only on job lifecycle.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from eventsource.stores import ExpectedVersion
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.dependencies.auth import CurrentUserWithTenant
from app.api.dependencies.tenant import TenantSession
from app.api.routers.scraping.helpers import (
    build_paginated_response,
    get_job_or_404,
)
from app.eventsourcing.events.scraping import ScrapingJobCreated
from app.eventsourcing.stores.factory import get_event_store
from app.models.scraping_job import JobStatus, ScrapingJob
from app.schemas.scraping import (
    CreateScrapingJobRequest,
    PaginatedResponse,
    ScrapingJobResponse,
    ScrapingJobSummary,
    UpdateScrapingJobRequest,
)
from app.services.task_queue import TaskQueueService, get_task_queue

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scraping"])

# Type alias for tenant-aware database session dependency
DbSession = TenantSession


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
    tenant_id = UUID(user.tenant_id)

    # Validate extraction provider if specified
    extraction_provider_id = None
    if request.extraction_provider_id:
        from app.models.extraction_provider import ExtractionProvider

        result = await db.execute(
            select(ExtractionProvider).where(
                ExtractionProvider.id == request.extraction_provider_id,
                ExtractionProvider.tenant_id == tenant_id,
                ExtractionProvider.is_active.is_(True),
            )
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or inactive extraction provider",
            )
        extraction_provider_id = provider.id

    # Extract domain from start_url if allowed_domains is empty
    allowed_domains = request.allowed_domains
    if not allowed_domains:
        from urllib.parse import urlparse

        parsed = urlparse(str(request.start_url))
        if parsed.netloc:
            allowed_domains = [parsed.netloc]

    # Create the job
    job = ScrapingJob(
        tenant_id=tenant_id,
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
        extraction_provider_id=extraction_provider_id,
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
    status_filter: JobStatus | None = Query(
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

    return build_paginated_response(items, total, page, page_size)


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
    return await get_job_or_404(db, job_id, user.tenant_id)


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
    job = await get_job_or_404(db, job_id, user.tenant_id)

    if job.status != JobStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot update job in '{job.status.value}' status. "
            "Only pending jobs can be updated.",
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

    job.updated_at = datetime.now(UTC)

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
    task_queue: TaskQueueService = Depends(get_task_queue),
) -> None:
    """
    Delete a scraping job.

    Running jobs will be cancelled before deletion.
    All associated scraped pages and extracted entities will also be deleted.
    """
    job = await get_job_or_404(db, job_id, user.tenant_id)

    # Cancel task if running or queued
    if job.status in (JobStatus.RUNNING, JobStatus.QUEUED) and job.celery_task_id:
        task_queue.cancel_task(job.celery_task_id, terminate=True)
        logger.info(
            "Task revoked before job deletion",
            extra={
                "job_id": str(job_id),
                "task_id": job.celery_task_id,
            },
        )

    await db.delete(job)

    logger.info(
        "Scraping job deleted",
        extra={"job_id": str(job_id), "tenant_id": user.tenant_id},
    )
