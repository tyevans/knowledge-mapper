"""
Celery tasks for web scraping operations.

This module provides tasks for:
- Running scraping jobs using Scrapy
- Cleaning up stale or abandoned jobs
- Progress tracking and status updates
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from celery import shared_task
from sqlalchemy import select, update

from app.worker.context import TenantWorkerContext
from app.models.scraping_job import JobStatus, ScrapingJob
from app.eventsourcing.events.scraping import (
    ScrapingJobStarted,
    ScrapingJobCompleted,
    ScrapingJobFailed,
    ScrapingJobProgressUpdated,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="app.tasks.scraping.run_scraping_job",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def run_scraping_job(self, job_id: str, tenant_id: str) -> dict:
    """
    Execute a Scrapy spider for a scraping job.

    This task:
    1. Loads job configuration from the database
    2. Configures and runs the Scrapy spider
    3. Updates job status and progress
    4. Emits domain events

    Args:
        job_id: UUID of the scraping job
        tenant_id: UUID of the tenant

    Returns:
        dict: Job execution summary

    Raises:
        Retry: If task should be retried
    """
    logger.info(
        "Starting scraping job",
        extra={"job_id": job_id, "tenant_id": tenant_id},
    )

    with TenantWorkerContext(tenant_id) as ctx:
        # Load job
        result = ctx.db.execute(
            select(ScrapingJob).where(ScrapingJob.id == UUID(job_id))
        )
        job = result.scalar_one_or_none()

        if not job:
            logger.error(f"Job not found: {job_id}")
            return {"status": "error", "message": "Job not found"}

        # Verify job is in correct state
        if job.status not in (JobStatus.QUEUED, JobStatus.PAUSED):
            logger.warning(
                f"Job {job_id} in unexpected status: {job.status}",
                extra={"job_id": job_id, "status": job.status.value},
            )
            return {"status": "skipped", "message": f"Job in {job.status.value} status"}

        try:
            # Update job to running
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            job.celery_task_id = self.request.id
            job.updated_at = datetime.now(timezone.utc)
            ctx.db.commit()

            # Emit started event
            _emit_job_started_event(job, tenant_id)

            # Run the spider
            summary = _run_spider(job, ctx, self)

            # Update job as completed
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            ctx.db.commit()

            # Emit completed event
            _emit_job_completed_event(job, tenant_id, summary)

            logger.info(
                "Scraping job completed",
                extra={
                    "job_id": job_id,
                    "pages_crawled": job.pages_crawled,
                    "entities_extracted": job.entities_extracted,
                },
            )

            return {
                "status": "completed",
                "job_id": job_id,
                "pages_crawled": job.pages_crawled,
                "entities_extracted": job.entities_extracted,
            }

        except Exception as e:
            logger.exception(
                "Scraping job failed",
                extra={"job_id": job_id, "error": str(e)},
            )

            # Update job as failed
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.updated_at = datetime.now(timezone.utc)
            ctx.db.commit()

            # Emit failed event
            _emit_job_failed_event(job, tenant_id, e)

            # Retry if appropriate
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)

            return {"status": "failed", "error": str(e)}


def _run_spider(job: ScrapingJob, ctx: TenantWorkerContext, task) -> dict:
    """
    Run the Scrapy spider for a job.

    Args:
        job: The scraping job
        ctx: Tenant worker context
        task: Celery task for progress updates

    Returns:
        dict: Spider execution summary
    """
    from app.scraping.runner import run_spider_for_job

    # Run the spider with progress callback
    def on_progress(pages: int, entities: int, errors: int):
        """Update job progress."""
        job.pages_crawled = pages
        job.entities_extracted = entities
        job.errors_count = errors
        job.updated_at = datetime.now(timezone.utc)
        ctx.db.commit()

        # Update task state for monitoring
        task.update_state(
            state="PROGRESS",
            meta={
                "pages_crawled": pages,
                "entities_extracted": entities,
                "errors_count": errors,
            },
        )

    return run_spider_for_job(job, str(ctx.tenant_id), on_progress)


def _emit_job_started_event(job: ScrapingJob, tenant_id: str) -> None:
    """Emit ScrapingJobStarted event."""
    try:
        from app.eventsourcing.stores.factory import get_event_store_sync
        event_store = get_event_store_sync()
        event = ScrapingJobStarted(
            aggregate_id=str(job.id),
            tenant_id=tenant_id,
            job_id=job.id,
            celery_task_id=job.celery_task_id or "",
            started_at=job.started_at,
        )
        event_store.append_sync(event)
    except Exception as e:
        logger.warning(f"Failed to emit ScrapingJobStarted event: {e}")


def _emit_job_completed_event(
    job: ScrapingJob,
    tenant_id: str,
    summary: dict,
) -> None:
    """Emit ScrapingJobCompleted event."""
    try:
        from app.eventsourcing.stores.factory import get_event_store_sync
        event_store = get_event_store_sync()

        duration = 0.0
        if job.started_at and job.completed_at:
            duration = (job.completed_at - job.started_at).total_seconds()

        event = ScrapingJobCompleted(
            aggregate_id=str(job.id),
            tenant_id=tenant_id,
            job_id=job.id,
            total_pages=job.pages_crawled,
            total_entities=job.entities_extracted,
            duration_seconds=duration,
            completed_at=job.completed_at,
        )
        event_store.append_sync(event)
    except Exception as e:
        logger.warning(f"Failed to emit ScrapingJobCompleted event: {e}")


def _emit_job_failed_event(job: ScrapingJob, tenant_id: str, error: Exception) -> None:
    """Emit ScrapingJobFailed event."""
    try:
        from app.eventsourcing.stores.factory import get_event_store_sync
        event_store = get_event_store_sync()
        event = ScrapingJobFailed(
            aggregate_id=str(job.id),
            tenant_id=tenant_id,
            job_id=job.id,
            error_message=str(error),
            error_type=type(error).__name__,
            failed_at=datetime.now(timezone.utc),
        )
        event_store.append_sync(event)
    except Exception as e:
        logger.warning(f"Failed to emit ScrapingJobFailed event: {e}")


@shared_task(
    name="app.tasks.scraping.cleanup_stale_jobs",
    acks_late=True,
)
def cleanup_stale_jobs() -> dict:
    """
    Clean up stale or abandoned scraping jobs.

    Finds jobs that have been running for too long or are in an
    inconsistent state and marks them as failed.

    Returns:
        dict: Cleanup summary
    """
    from app.core.database import SyncSessionLocal

    logger.info("Starting stale job cleanup")

    cleaned = 0
    stale_threshold = datetime.now(timezone.utc) - timedelta(hours=24)

    with SyncSessionLocal() as db:
        try:
            # Find stale running jobs (running for more than 24 hours)
            result = db.execute(
                select(ScrapingJob).where(
                    ScrapingJob.status == JobStatus.RUNNING,
                    ScrapingJob.started_at < stale_threshold,
                )
            )
            stale_jobs = result.scalars().all()

            for job in stale_jobs:
                job.status = JobStatus.FAILED
                job.error_message = "Job timed out after 24 hours"
                job.updated_at = datetime.now(timezone.utc)
                cleaned += 1

                logger.warning(
                    "Marked stale job as failed",
                    extra={
                        "job_id": str(job.id),
                        "tenant_id": str(job.tenant_id),
                        "started_at": job.started_at.isoformat(),
                    },
                )

            # Find queued jobs that never started (queued for more than 1 hour)
            queued_threshold = datetime.now(timezone.utc) - timedelta(hours=1)
            result = db.execute(
                select(ScrapingJob).where(
                    ScrapingJob.status == JobStatus.QUEUED,
                    ScrapingJob.updated_at < queued_threshold,
                )
            )
            stuck_jobs = result.scalars().all()

            for job in stuck_jobs:
                # Reset to pending so they can be retried
                job.status = JobStatus.PENDING
                job.celery_task_id = None
                job.updated_at = datetime.now(timezone.utc)
                cleaned += 1

                logger.warning(
                    "Reset stuck queued job to pending",
                    extra={
                        "job_id": str(job.id),
                        "tenant_id": str(job.tenant_id),
                    },
                )

            db.commit()

        except Exception as e:
            logger.exception("Failed to cleanup stale jobs")
            db.rollback()
            raise

    logger.info(f"Stale job cleanup completed: {cleaned} jobs cleaned")
    return {"cleaned": cleaned}


@shared_task(
    name="app.tasks.scraping.update_job_progress",
    acks_late=True,
)
def update_job_progress(
    job_id: str,
    tenant_id: str,
    pages_crawled: int,
    entities_extracted: int,
    errors_count: int,
) -> None:
    """
    Update job progress from spider callback.

    This task is called by the spider to update job progress
    during execution.

    Args:
        job_id: UUID of the job
        tenant_id: UUID of the tenant
        pages_crawled: Number of pages crawled
        entities_extracted: Number of entities extracted
        errors_count: Number of errors encountered
    """
    with TenantWorkerContext(tenant_id) as ctx:
        result = ctx.db.execute(
            update(ScrapingJob)
            .where(ScrapingJob.id == UUID(job_id))
            .values(
                pages_crawled=pages_crawled,
                entities_extracted=entities_extracted,
                errors_count=errors_count,
                updated_at=datetime.now(timezone.utc),
            )
        )
        ctx.db.commit()

        # Emit progress event
        try:
            from app.eventsourcing.stores.factory import get_event_store_sync
            event_store = get_event_store_sync()
            event = ScrapingJobProgressUpdated(
                aggregate_id=job_id,
                tenant_id=tenant_id,
                job_id=UUID(job_id),
                pages_crawled=pages_crawled,
                entities_extracted=entities_extracted,
                errors_count=errors_count,
            )
            event_store.append_sync(event)
        except Exception as e:
            logger.warning(f"Failed to emit progress event: {e}")
