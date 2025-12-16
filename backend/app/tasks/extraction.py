"""
Celery tasks for entity extraction.

This module provides Celery task wrappers for extraction operations.
Business logic is delegated to ExtractionOrchestrator service,
following the Single Responsibility Principle.

Tasks handle:
- Celery task lifecycle (retries, acks, etc.)
- Database context and transactions
- Event emission
- Job status updates
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from celery import shared_task
from sqlalchemy import func, select

from app.eventsourcing.events.scraping import (
    EntitiesExtractedBatch,
    ExtractionFailed,
)
from app.models.extracted_entity import EntityRelationship, ExtractedEntity
from app.models.scraped_page import ScrapedPage
from app.models.scraping_job import JobStage, ScrapingJob
from app.services.extraction import ExtractionOrchestrator
from app.worker.context import TenantWorkerContext

logger = logging.getLogger(__name__)

# Shared orchestrator instance (stateless)
_orchestrator = ExtractionOrchestrator()


@shared_task(
    bind=True,
    name="app.tasks.extraction.extract_entities",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def extract_entities(self, page_id: str, tenant_id: str) -> dict:
    """
    Extract entities from a single scraped page.

    This task:
    1. Loads page content from the database
    2. Delegates extraction to ExtractionOrchestrator
    3. Stores extracted entities and relationships
    4. Emits domain events

    Args:
        page_id: UUID of the scraped page
        tenant_id: UUID of the tenant

    Returns:
        dict: Extraction summary
    """
    logger.info(
        "Starting entity extraction",
        extra={"page_id": page_id, "tenant_id": tenant_id},
    )

    with TenantWorkerContext(tenant_id) as ctx:
        # Load page
        result = ctx.db.execute(
            select(ScrapedPage).where(ScrapedPage.id == UUID(page_id))
        )
        page = result.scalar_one_or_none()

        if not page:
            logger.error(f"Page not found: {page_id}")
            return {"status": "error", "message": "Page not found"}

        # Check if already processed
        if page.extraction_status == "completed":
            logger.info(f"Page already processed: {page_id}")
            return {"status": "skipped", "message": "Already processed"}

        try:
            # Update status to processing
            page.extraction_status = "processing"
            page.updated_at = datetime.now(UTC)
            ctx.db.commit()

            # Load job to get extraction settings
            from sqlalchemy.orm import selectinload

            job_result = ctx.db.execute(
                select(ScrapingJob)
                .options(selectinload(ScrapingJob.extraction_provider))
                .where(ScrapingJob.id == page.job_id)
            )
            job = job_result.scalar_one_or_none()

            # Run extraction via orchestrator
            extraction_result = _orchestrator.extract_from_page(
                page=page,
                tenant_id=tenant_id,
                extraction_provider=job.extraction_provider if job else None,
                use_llm_extraction=job.use_llm_extraction if job else False,
            )

            # Save entities and build name->id mapping for relationships
            entity_name_to_id: dict[str, UUID] = {}
            for entity_data in extraction_result.entities:
                entity = ExtractedEntity(
                    tenant_id=UUID(tenant_id),
                    source_page_id=page.id,
                    entity_type=entity_data["type"],
                    name=entity_data["name"],
                    normalized_name=_orchestrator.normalize_name(entity_data["name"]),
                    description=entity_data.get("description"),
                    properties=entity_data.get("properties", {}),
                    extraction_method=entity_data["method"],
                    confidence_score=entity_data.get("confidence", 1.0),
                    source_text=entity_data.get("source_text"),
                )
                ctx.db.add(entity)
                # Track entity name to ID for relationship resolution
                entity_name_to_id[
                    _orchestrator.normalize_name(entity_data["name"])
                ] = entity.id

            # Flush to ensure entities have IDs before creating relationships
            ctx.db.flush()

            # Save relationships
            relationship_count = 0
            for rel_data in extraction_result.relationships:
                source_name = _orchestrator.normalize_name(rel_data["source_name"])
                target_name = _orchestrator.normalize_name(rel_data["target_name"])

                source_id = entity_name_to_id.get(source_name)
                target_id = entity_name_to_id.get(target_name)

                if source_id and target_id:
                    relationship = EntityRelationship(
                        tenant_id=UUID(tenant_id),
                        source_entity_id=source_id,
                        target_entity_id=target_id,
                        relationship_type=rel_data["relationship_type"].upper(),
                        properties=rel_data.get("properties", {}),
                        confidence_score=rel_data.get("confidence", 1.0),
                    )
                    ctx.db.add(relationship)
                    relationship_count += 1
                else:
                    logger.warning(
                        f"Could not resolve relationship: "
                        f"{rel_data['source_name']} -> {rel_data['target_name']}"
                    )

            # Update page status
            page.extraction_status = "completed"
            page.extracted_at = datetime.now(UTC)
            page.updated_at = datetime.now(UTC)
            ctx.db.commit()

            # Update job entity count
            _update_job_entity_count(
                ctx.db, page.job_id, extraction_result.total_entities
            )

            # Emit batch event
            _emit_batch_extracted_event(
                page,
                tenant_id,
                extraction_result.total_entities,
                extraction_result.schema_org_count,
                extraction_result.llm_count,
            )

            logger.info(
                "Entity extraction completed",
                extra={
                    "page_id": page_id,
                    "entities_count": extraction_result.total_entities,
                    "relationships_count": relationship_count,
                    "schema_org_count": extraction_result.schema_org_count,
                    "llm_count": extraction_result.llm_count,
                },
            )

            return {
                "status": "completed",
                "page_id": page_id,
                "entities_count": extraction_result.total_entities,
                "relationships_count": relationship_count,
                "schema_org_count": extraction_result.schema_org_count,
                "llm_count": extraction_result.llm_count,
            }

        except Exception as e:
            logger.exception(
                "Entity extraction failed",
                extra={"page_id": page_id, "error": str(e)},
            )

            # Update page status
            page.extraction_status = "failed"
            page.extraction_error = str(e)
            page.updated_at = datetime.now(UTC)
            ctx.db.commit()

            # Emit failed event
            _emit_extraction_failed_event(page, tenant_id, e)

            # Retry if appropriate
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e) from e

            return {"status": "failed", "error": str(e)}


def _update_job_entity_count(db, job_id: UUID, count: int) -> None:
    """Update job's entity count."""
    from sqlalchemy import update

    db.execute(
        update(ScrapingJob)
        .where(ScrapingJob.id == job_id)
        .values(
            entities_extracted=ScrapingJob.entities_extracted + count,
            updated_at=datetime.now(UTC),
        )
    )
    db.commit()


def _emit_batch_extracted_event(
    page: ScrapedPage,
    tenant_id: str,
    total: int,
    schema_org: int,
    llm: int,
) -> None:
    """Emit EntitiesExtractedBatch event."""
    try:
        from app.eventsourcing.stores.factory import get_event_store_sync

        event_store = get_event_store_sync()
        event = EntitiesExtractedBatch(
            aggregate_id=str(page.id),
            tenant_id=tenant_id,
            page_id=page.id,
            job_id=page.job_id,
            entity_count=total,
            schema_org_count=schema_org,
            llm_extracted_count=llm,
            extracted_at=datetime.now(UTC),
        )
        event_store.append_sync(event)
    except Exception as e:
        logger.warning(f"Failed to emit EntitiesExtractedBatch event: {e}")


def _emit_extraction_failed_event(
    page: ScrapedPage,
    tenant_id: str,
    error: Exception,
) -> None:
    """Emit ExtractionFailed event."""
    try:
        from app.eventsourcing.stores.factory import get_event_store_sync

        event_store = get_event_store_sync()
        event = ExtractionFailed(
            aggregate_id=str(page.id),
            tenant_id=tenant_id,
            page_id=page.id,
            job_id=page.job_id,
            error_message=str(error),
            failed_at=datetime.now(UTC),
        )
        event_store.append_sync(event)
    except Exception as e:
        logger.warning(f"Failed to emit ExtractionFailed event: {e}")


@shared_task(
    name="app.tasks.extraction.extract_entities_batch",
    acks_late=True,
)
def extract_entities_batch(page_ids: list[str], tenant_id: str) -> dict:
    """
    Extract entities from multiple pages in batch.

    Args:
        page_ids: List of page UUIDs
        tenant_id: UUID of the tenant

    Returns:
        dict: Batch extraction summary
    """
    logger.info(
        "Starting batch entity extraction",
        extra={"page_count": len(page_ids), "tenant_id": tenant_id},
    )

    results = {
        "total": len(page_ids),
        "completed": 0,
        "failed": 0,
        "entities_extracted": 0,
    }

    for page_id in page_ids:
        try:
            result = extract_entities(page_id, tenant_id)
            if result.get("status") == "completed":
                results["completed"] += 1
                results["entities_extracted"] += result.get("entities_count", 0)
            elif result.get("status") == "failed":
                results["failed"] += 1
        except Exception as e:
            logger.error(f"Batch extraction failed for page {page_id}: {e}")
            results["failed"] += 1

    logger.info(
        "Batch entity extraction completed",
        extra=results,
    )

    return results


@shared_task(
    name="app.tasks.extraction.process_pending_pages",
    acks_late=True,
)
def process_pending_pages(job_id: str, tenant_id: str, batch_size: int = 10) -> dict:
    """
    Process pending pages for a job.

    Finds pages with pending extraction status and queues them
    for extraction.

    Args:
        job_id: UUID of the job
        tenant_id: UUID of the tenant
        batch_size: Number of pages to process per batch

    Returns:
        dict: Processing summary
    """
    with TenantWorkerContext(tenant_id) as ctx:
        result = ctx.db.execute(
            select(ScrapedPage)
            .where(
                ScrapedPage.job_id == UUID(job_id),
                ScrapedPage.extraction_status == "pending",
            )
            .limit(batch_size)
        )
        pages = result.scalars().all()

        queued = 0
        for page in pages:
            extract_entities.delay(str(page.id), tenant_id)
            queued += 1

        logger.info(
            "Queued pages for extraction",
            extra={"job_id": job_id, "queued": queued},
        )

        return {"queued": queued}


@shared_task(
    bind=True,
    name="app.tasks.extraction.monitor_extraction_completion",
    max_retries=None,  # Keep checking until complete
    default_retry_delay=5,
    acks_late=True,
)
def monitor_extraction_completion(self, job_id: str, tenant_id: str) -> dict:
    """
    Monitor extraction progress and trigger consolidation when complete.

    This task polls for pending/processing pages and transitions the job
    stage when all extractions are complete.

    Args:
        job_id: UUID of the scraping job
        tenant_id: UUID of the tenant

    Returns:
        dict: Monitoring summary
    """
    logger.info(
        "Monitoring extraction completion",
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

        # Only proceed if job is in EXTRACTING stage
        if job.stage != JobStage.EXTRACTING:
            logger.info(
                f"Job {job_id} not in EXTRACTING stage, skipping",
                extra={"job_id": job_id, "stage": job.stage.value},
            )
            return {"status": "skipped", "reason": f"Job in {job.stage.value} stage"}

        # Count pages by extraction status
        total_pages = (
            ctx.db.execute(
                select(func.count())
                .select_from(ScrapedPage)
                .where(ScrapedPage.job_id == UUID(job_id))
            ).scalar()
            or 0
        )

        completed_pages = (
            ctx.db.execute(
                select(func.count())
                .select_from(ScrapedPage)
                .where(
                    ScrapedPage.job_id == UUID(job_id),
                    ScrapedPage.extraction_status == "completed",
                )
            ).scalar()
            or 0
        )

        pending_pages = (
            ctx.db.execute(
                select(func.count())
                .select_from(ScrapedPage)
                .where(
                    ScrapedPage.job_id == UUID(job_id),
                    ScrapedPage.extraction_status.in_(["pending", "processing"]),
                )
            ).scalar()
            or 0
        )

        failed_pages = (
            ctx.db.execute(
                select(func.count())
                .select_from(ScrapedPage)
                .where(
                    ScrapedPage.job_id == UUID(job_id),
                    ScrapedPage.extraction_status == "failed",
                )
            ).scalar()
            or 0
        )

        # Update progress
        if total_pages > 0:
            job.extraction_progress = completed_pages / total_pages
        job.pages_pending_extraction = pending_pages
        job.updated_at = datetime.now(UTC)
        ctx.db.commit()

        logger.info(
            "Extraction progress",
            extra={
                "job_id": job_id,
                "total_pages": total_pages,
                "completed_pages": completed_pages,
                "pending_pages": pending_pages,
                "failed_pages": failed_pages,
                "extraction_progress": job.extraction_progress,
            },
        )

        # If there are still pending pages, retry in 5 seconds
        if pending_pages > 0:
            raise self.retry(countdown=5)

        # All extractions complete - transition to consolidation
        job.stage = JobStage.CONSOLIDATING
        job.extraction_progress = 1.0
        job.pages_pending_extraction = 0
        job.updated_at = datetime.now(UTC)
        ctx.db.commit()

        # Queue consolidation task
        from app.tasks.consolidation import run_consolidation_for_job

        task = run_consolidation_for_job.delay(job_id, tenant_id)
        job.consolidation_task_id = task.id
        ctx.db.commit()

        logger.info(
            "Extraction complete, transitioning to consolidation",
            extra={
                "job_id": job_id,
                "consolidation_task_id": task.id,
                "total_pages": total_pages,
                "completed_pages": completed_pages,
                "failed_pages": failed_pages,
            },
        )

        return {
            "status": "complete",
            "total_pages": total_pages,
            "completed_pages": completed_pages,
            "failed_pages": failed_pages,
            "consolidation_task_id": task.id,
        }
