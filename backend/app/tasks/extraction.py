"""
Celery tasks for entity extraction.

This module provides tasks for:
- Extracting entities from scraped pages
- Processing extraction batches
- Managing extraction queue
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from celery import shared_task
from sqlalchemy import select

from app.worker.context import TenantWorkerContext
from app.models.scraped_page import ScrapedPage
from app.models.extracted_entity import ExtractedEntity, EntityRelationship, ExtractionMethod
from app.models.scraping_job import ScrapingJob
from app.eventsourcing.events.scraping import (
    EntityExtracted,
    EntitiesExtractedBatch,
    ExtractionFailed,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


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
    2. Runs Schema.org extraction
    3. Optionally runs LLM extraction
    4. Stores extracted entities
    5. Emits domain events

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
            page.updated_at = datetime.now(timezone.utc)
            ctx.db.commit()

            # Run extraction pipeline
            entities, relationships = _extract_from_page(page, ctx, tenant_id)

            # Save entities and build name->id mapping for relationships
            schema_org_count = 0
            llm_count = 0
            entity_name_to_id: dict[str, UUID] = {}
            for entity_data in entities:
                entity = ExtractedEntity(
                    tenant_id=UUID(tenant_id),
                    source_page_id=page.id,
                    entity_type=entity_data["type"],
                    name=entity_data["name"],
                    normalized_name=_normalize_name(entity_data["name"]),
                    description=entity_data.get("description"),
                    properties=entity_data.get("properties", {}),
                    extraction_method=entity_data["method"],
                    confidence_score=entity_data.get("confidence", 1.0),
                    source_text=entity_data.get("source_text"),
                )
                ctx.db.add(entity)
                # Track entity name to ID for relationship resolution
                entity_name_to_id[_normalize_name(entity_data["name"])] = entity.id

                if entity_data["method"] == ExtractionMethod.SCHEMA_ORG:
                    schema_org_count += 1
                else:
                    llm_count += 1

            # Flush to ensure entities have IDs before creating relationships
            ctx.db.flush()

            # Save relationships
            relationship_count = 0
            for rel_data in relationships:
                source_name = _normalize_name(rel_data["source_name"])
                target_name = _normalize_name(rel_data["target_name"])

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
                        f"Could not resolve relationship: {rel_data['source_name']} -> {rel_data['target_name']}"
                    )

            # Update page status
            page.extraction_status = "completed"
            page.extracted_at = datetime.now(timezone.utc)
            page.updated_at = datetime.now(timezone.utc)
            ctx.db.commit()

            # Update job entity count
            _update_job_entity_count(ctx.db, page.job_id, len(entities))

            # Emit batch event
            _emit_batch_extracted_event(
                page,
                tenant_id,
                len(entities),
                schema_org_count,
                llm_count,
            )

            logger.info(
                "Entity extraction completed",
                extra={
                    "page_id": page_id,
                    "entities_count": len(entities),
                    "relationships_count": relationship_count,
                    "schema_org_count": schema_org_count,
                    "llm_count": llm_count,
                },
            )

            return {
                "status": "completed",
                "page_id": page_id,
                "entities_count": len(entities),
                "relationships_count": relationship_count,
                "schema_org_count": schema_org_count,
                "llm_count": llm_count,
            }

        except Exception as e:
            logger.exception(
                "Entity extraction failed",
                extra={"page_id": page_id, "error": str(e)},
            )

            # Update page status
            page.extraction_status = "failed"
            page.extraction_error = str(e)
            page.updated_at = datetime.now(timezone.utc)
            ctx.db.commit()

            # Emit failed event
            _emit_extraction_failed_event(page, tenant_id, e)

            # Retry if appropriate
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)

            return {"status": "failed", "error": str(e)}


def _extract_from_page(
    page: ScrapedPage,
    ctx: TenantWorkerContext,
    tenant_id: str,
) -> tuple[list[dict], list[dict]]:
    """
    Run extraction pipeline on a page.

    Args:
        page: Scraped page
        ctx: Worker context
        tenant_id: Tenant ID

    Returns:
        Tuple of (entities, relationships)
    """
    entities = []
    relationships = []

    # 1. Extract from Schema.org/JSON-LD
    if page.schema_org_data:
        schema_entities = _extract_schema_org(page.schema_org_data)
        entities.extend(schema_entities)

    # 2. Extract from Open Graph
    if page.open_graph_data:
        og_entities = _extract_open_graph(page.open_graph_data)
        entities.extend(og_entities)

    # 3. LLM extraction (if enabled for the job)
    result = ctx.db.execute(
        select(ScrapingJob).where(ScrapingJob.id == page.job_id)
    )
    job = result.scalar_one_or_none()

    if job and job.use_llm_extraction and page.text_content:
        llm_entities, llm_relationships = _extract_with_llm(page.text_content, tenant_id, page.url)
        entities.extend(llm_entities)
        relationships.extend(llm_relationships)

    # Deduplicate entities by name
    return _deduplicate_entities(entities), relationships


def _extract_schema_org(data: list) -> list[dict]:
    """Extract entities from Schema.org JSON-LD data."""
    from app.extraction.schema_org import extract_entities_from_schema_org
    return extract_entities_from_schema_org(data)


def _extract_open_graph(data: dict) -> list[dict]:
    """Extract entities from Open Graph data."""
    from app.extraction.schema_org import extract_entities_from_open_graph
    return extract_entities_from_open_graph(data)


def _extract_with_llm(text: str, tenant_id: str, page_url: str = "") -> tuple[list[dict], list[dict]]:
    """Extract entities and relationships using Ollama LLM.

    Returns:
        Tuple of (entities, relationships)
    """
    import asyncio
    from app.extraction.ollama_extractor import get_ollama_extraction_service
    from app.core.config import settings

    # Check if Ollama is configured
    if not settings.OLLAMA_BASE_URL:
        logger.warning("OLLAMA_BASE_URL not configured, skipping LLM extraction")
        return [], []

    try:
        service = get_ollama_extraction_service()
        # Run async extraction in sync context
        result = asyncio.run(service.extract(content=text, page_url=page_url))

        # Convert ExtractionResult to list of entity dicts
        entities = []
        for entity in result.entities:
            # entity_type may be string or enum depending on pydantic-ai parsing
            entity_type = entity.entity_type
            if hasattr(entity_type, 'value'):
                entity_type = entity_type.value
            entities.append({
                "name": entity.name,
                "type": entity_type,
                "description": entity.description,
                "confidence": entity.confidence,
                "properties": entity.properties or {},
                "method": ExtractionMethod.LLM_OLLAMA,
            })

        # Convert relationships to list of dicts
        relationships = []
        for rel in result.relationships:
            rel_type = rel.relationship_type
            if hasattr(rel_type, 'value'):
                rel_type = rel_type.value
            relationships.append({
                "source_name": rel.source_name,
                "target_name": rel.target_name,
                "relationship_type": rel_type,
                "confidence": rel.confidence,
                "context": rel.context,
                "properties": rel.properties or {},
            })

        logger.info(f"LLM extracted {len(entities)} entities and {len(relationships)} relationships")
        return entities, relationships
    except Exception as e:
        logger.warning(f"Ollama extraction failed: {e}")
        return [], []


def _deduplicate_entities(entities: list[dict]) -> list[dict]:
    """Deduplicate entities by normalized name and type."""
    seen = set()
    unique = []
    for entity in entities:
        key = (_normalize_name(entity["name"]), entity["type"])
        if key not in seen:
            seen.add(key)
            unique.append(entity)
    return unique


def _normalize_name(name: str) -> str:
    """Normalize entity name for deduplication."""
    return name.lower().strip()


def _update_job_entity_count(db, job_id: UUID, count: int) -> None:
    """Update job's entity count."""
    from sqlalchemy import update
    db.execute(
        update(ScrapingJob)
        .where(ScrapingJob.id == job_id)
        .values(
            entities_extracted=ScrapingJob.entities_extracted + count,
            updated_at=datetime.now(timezone.utc),
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
            extracted_at=datetime.now(timezone.utc),
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
            failed_at=datetime.now(timezone.utc),
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
