"""
Scraping job control endpoints.

This router handles job execution control:
- Starting jobs
- Stopping jobs
- Pausing jobs
- Getting job status

Follows Single Responsibility Principle by focusing only on job state transitions.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from eventsource.stores import ExpectedVersion
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update

from app.api.dependencies.auth import CurrentUserWithTenant
from app.api.dependencies.tenant import TenantSession
from app.api.routers.scraping.helpers import get_job_or_404
from app.eventsourcing.events.scraping import ScrapingJobCancelled
from app.eventsourcing.stores.factory import get_event_store
from app.models.scraping_job import JobStage, JobStatus, ScrapingJob
from app.schemas.scraping import JobStatusResponse
from app.services.task_queue import TaskQueueService, get_task_queue
from app.tasks.scraping import run_scraping_job

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scraping"])

# Type alias for tenant-aware database session dependency
DbSession = TenantSession


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
    job = await get_job_or_404(db, job_id, user.tenant_id)

    # Calculate crawl progress
    crawl_progress = None
    if job.max_pages > 0:
        crawl_progress = min(1.0, job.pages_crawled / job.max_pages)

    # Calculate overall estimated progress based on stage
    # Weights: Crawling=40%, Extracting=30%, Consolidating=30%
    if job.stage == JobStage.CRAWLING:
        estimated_progress = (crawl_progress or 0.0) * 0.4
    elif job.stage == JobStage.EXTRACTING:
        estimated_progress = 0.4 + (job.extraction_progress * 0.3)
    elif job.stage == JobStage.CONSOLIDATING:
        estimated_progress = 0.7 + (job.consolidation_progress * 0.3)
    elif job.stage == JobStage.DONE:
        estimated_progress = 1.0
    else:
        estimated_progress = 0.0

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        stage=job.stage,
        pages_crawled=job.pages_crawled,
        entities_extracted=job.entities_extracted,
        errors_count=job.errors_count,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        estimated_progress=estimated_progress,
        crawl_progress=crawl_progress,
        extraction_progress=job.extraction_progress,
        consolidation_progress=job.consolidation_progress,
        consolidation_candidates_found=job.consolidation_candidates_found,
        consolidation_auto_merged=job.consolidation_auto_merged,
        pages_pending_extraction=job.pages_pending_extraction,
    )


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
    job = await get_job_or_404(db, job_id, user.tenant_id)

    if job.status not in (JobStatus.PENDING, JobStatus.PAUSED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start job in '{job.status.value}' status. "
            "Only pending or paused jobs can be started.",
        )

    # Queue the job for execution
    job.status = JobStatus.QUEUED
    job.updated_at = datetime.now(UTC)

    # Commit status change BEFORE queueing Celery task so the worker can see
    # the QUEUED status when it queries the database
    await db.commit()

    # Submit to Celery for background processing
    task = run_scraping_job.delay(str(job.id), user.tenant_id)

    # Use a raw UPDATE to save the celery_task_id - this avoids StaleDataError
    # if the Celery worker has already modified the row (which sets its own task ID).
    await db.execute(
        update(ScrapingJob)
        .where(ScrapingJob.id == job.id)
        .values(celery_task_id=task.id)
    )
    await db.commit()

    # Refresh job to get latest state for response
    await db.refresh(job)

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
    task_queue: TaskQueueService = Depends(get_task_queue),
) -> JobStatusResponse:
    """
    Stop a running scraping job.

    The job will be cancelled and cannot be resumed.
    """
    job = await get_job_or_404(db, job_id, user.tenant_id)

    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot stop job in '{job.status.value}' status. "
            "Only queued or running jobs can be stopped.",
        )

    # Cancel the task if running
    if job.celery_task_id:
        task_queue.cancel_task(job.celery_task_id, terminate=True)
        logger.info(
            "Task revoked",
            extra={
                "job_id": str(job_id),
                "task_id": job.celery_task_id,
            },
        )

    job.status = JobStatus.CANCELLED
    job.updated_at = datetime.now(UTC)

    # Emit domain event
    try:
        event_store = await get_event_store()
        event = ScrapingJobCancelled(
            aggregate_id=str(job.id),
            tenant_id=UUID(user.tenant_id),
            job_id=job.id,
            cancelled_by=user.user_id,
            cancelled_at=datetime.now(UTC),
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
    task_queue: TaskQueueService = Depends(get_task_queue),
) -> JobStatusResponse:
    """
    Pause a running scraping job.

    The job can be resumed later using the start endpoint.
    """
    job = await get_job_or_404(db, job_id, user.tenant_id)

    if job.status != JobStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot pause job in '{job.status.value}' status. "
            "Only running jobs can be paused.",
        )

    # Revoke the task to pause execution
    # Note: This is a hard pause - the task is terminated and can be resumed later
    # by calling the start endpoint, which will submit a new task.
    if job.celery_task_id:
        task_queue.cancel_task(job.celery_task_id, terminate=True)
        logger.info(
            "Task revoked for pause",
            extra={
                "job_id": str(job_id),
                "task_id": job.celery_task_id,
            },
        )

    job.status = JobStatus.PAUSED
    job.celery_task_id = None  # Clear task ID since it's been revoked
    job.updated_at = datetime.now(UTC)

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
