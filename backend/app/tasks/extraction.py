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

from sqlalchemy import func

from app.worker.context import TenantWorkerContext
from app.models.scraped_page import ScrapedPage
from app.models.extracted_entity import ExtractedEntity, EntityRelationship, ExtractionMethod
from app.models.scraping_job import ScrapingJob, JobStatus, JobStage
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
    from sqlalchemy.orm import selectinload

    result = ctx.db.execute(
        select(ScrapingJob)
        .options(selectinload(ScrapingJob.extraction_provider))
        .where(ScrapingJob.id == page.job_id)
    )
    job = result.scalar_one_or_none()

    if job and job.use_llm_extraction and page.html_content:
        # Pass html_content to the preprocessing pipeline - trafilatura needs HTML
        # Pass the extraction provider if configured for per-job provider selection
        llm_entities, llm_relationships = _extract_with_llm(
            page.html_content,
            tenant_id,
            page.url,
            extraction_provider=job.extraction_provider,
        )
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


def _extract_with_llm(
    text: str,
    tenant_id: str,
    page_url: str = "",
    extraction_provider=None,
) -> tuple[list[dict], list[dict]]:
    """Extract entities and relationships using LLM with optional provider.

    When extraction_provider is specified, uses the factory to create the
    appropriate extraction service. Otherwise falls back to global Ollama.

    When PREPROCESSING_ENABLED is True, uses the full pipeline:
    1. Preprocess: Clean HTML, remove boilerplate (trafilatura)
    2. Chunk: Split into overlapping chunks
    3. Extract: Run LLM on each chunk
    4. Merge: Combine entities across chunks (with LLM assistance)

    When PREPROCESSING_ENABLED is False, falls back to legacy behavior.

    Args:
        text: HTML content to extract from
        tenant_id: Tenant ID
        page_url: URL of the page
        extraction_provider: Optional ExtractionProvider model instance

    Returns:
        Tuple of (entities, relationships)
    """
    # If a provider is specified, use it
    if extraction_provider is not None:
        return _extract_with_provider(text, tenant_id, page_url, extraction_provider)

    # Check if Ollama is configured for fallback
    if not settings.OLLAMA_BASE_URL:
        logger.warning("OLLAMA_BASE_URL not configured and no provider specified, skipping LLM extraction")
        return [], []

    # Use preprocessing pipeline if enabled
    if settings.PREPROCESSING_ENABLED:
        return _extract_with_preprocessing_pipeline(text, tenant_id, page_url)
    else:
        return _extract_with_llm_legacy(text, tenant_id, page_url)


def _extract_with_provider(
    text: str,
    tenant_id: str,
    page_url: str,
    extraction_provider,
) -> tuple[list[dict], list[dict]]:
    """Extract using a specific configured provider.

    Uses the ExtractionProviderFactory to create the appropriate service
    and run extraction.

    Args:
        text: HTML content to extract from
        tenant_id: Tenant ID
        page_url: URL of the page
        extraction_provider: ExtractionProvider model instance

    Returns:
        Tuple of (entities, relationships)
    """
    import asyncio
    import time
    from uuid import UUID

    from app.extraction.factory import ExtractionProviderFactory, ProviderConfigError
    from app.extraction.base import ExtractionError
    from app.models.extraction_provider import ExtractionProviderType

    logger.info(
        "Starting provider-based extraction",
        extra={
            "page_url": page_url,
            "text_length": len(text),
            "provider_id": str(extraction_provider.id),
            "provider_type": extraction_provider.provider_type.value,
            "provider_name": extraction_provider.name,
        },
    )

    start_time = time.time()

    try:
        # Create service from provider config
        service = ExtractionProviderFactory.create_service(
            extraction_provider,
            UUID(tenant_id),
        )

        # Run async extraction in sync context
        result = asyncio.run(service.extract(content=text, page_url=page_url))

        elapsed = time.time() - start_time

        # Determine extraction method based on provider type
        if extraction_provider.provider_type == ExtractionProviderType.OPENAI:
            method = ExtractionMethod.LLM_OPENAI
        elif extraction_provider.provider_type == ExtractionProviderType.ANTHROPIC:
            method = ExtractionMethod.LLM_CLAUDE
        else:
            method = ExtractionMethod.LLM_OLLAMA

        # Convert ExtractionResult to list of entity dicts
        entities = []
        for entity in result.entities:
            entity_type = entity.entity_type
            if hasattr(entity_type, "value"):
                entity_type = entity_type.value
            entities.append(
                {
                    "name": entity.name,
                    "type": entity_type,
                    "description": entity.description,
                    "confidence": entity.confidence,
                    "properties": entity.properties or {},
                    "method": method,
                }
            )

        # Convert relationships to list of dicts
        relationships = []
        for rel in result.relationships:
            rel_type = rel.relationship_type
            if hasattr(rel_type, "value"):
                rel_type = rel_type.value
            relationships.append(
                {
                    "source_name": rel.source_name,
                    "target_name": rel.target_name,
                    "relationship_type": rel_type,
                    "confidence": rel.confidence,
                    "context": rel.context,
                    "properties": rel.properties or {},
                }
            )

        logger.info(
            "Provider-based extraction completed",
            extra={
                "page_url": page_url,
                "entities_count": len(entities),
                "relationships_count": len(relationships),
                "elapsed_seconds": round(elapsed, 2),
                "provider_type": extraction_provider.provider_type.value,
            },
        )

        return entities, relationships

    except ProviderConfigError as e:
        elapsed = time.time() - start_time
        logger.error(
            "Provider configuration error",
            extra={
                "page_url": page_url,
                "error": str(e),
                "provider_id": str(extraction_provider.id),
                "elapsed_seconds": round(elapsed, 2),
            },
        )
        return [], []

    except ExtractionError as e:
        elapsed = time.time() - start_time
        logger.warning(
            f"Provider extraction failed for {page_url} "
            f"(provider={extraction_provider.id}, elapsed={round(elapsed, 2)}s): {e}"
        )
        return [], []

    except Exception as e:
        elapsed = time.time() - start_time
        logger.warning(
            f"Provider extraction failed with unexpected error: {type(e).__name__}: {e}",
            extra={
                "page_url": page_url,
                "error": str(e),
                "error_type": type(e).__name__,
                "provider_id": str(extraction_provider.id),
                "elapsed_seconds": round(elapsed, 2),
            },
        )
        return [], []


def _extract_with_preprocessing_pipeline(
    text: str, tenant_id: str, page_url: str = ""
) -> tuple[list[dict], list[dict]]:
    """Extract using the full preprocessing pipeline.

    Pipeline stages:
    1. Preprocess (trafilatura): Clean HTML, remove boilerplate
    2. Chunk (sliding window): Split into overlapping chunks
    3. Extract (Ollama): Run LLM on each chunk
    4. Merge (LLM-assisted): Combine entities across chunks

    Returns:
        Tuple of (entities, relationships)
    """
    import asyncio
    import time
    from uuid import UUID

    from app.extraction.ollama_extractor import get_ollama_extraction_service
    from app.preprocessing.factory import (
        ChunkerType,
        EntityMergerType,
        PreprocessorType,
    )
    from app.preprocessing.pipeline import PipelineConfig, PreprocessingPipeline

    logger.info(
        "Starting preprocessing pipeline extraction",
        extra={
            "page_url": page_url,
            "text_length": len(text),
            "preprocessor": settings.PREPROCESSOR_TYPE,
            "chunker": settings.CHUNKER_TYPE,
            "merger": settings.MERGER_TYPE,
            "chunk_size": settings.CHUNK_SIZE,
        },
    )

    start_time = time.time()

    try:
        # Build pipeline configuration from settings
        config = PipelineConfig(
            preprocessor_type=PreprocessorType(settings.PREPROCESSOR_TYPE),
            preprocessor_config={
                "favor_recall": settings.PREPROCESSOR_FAVOR_RECALL,
                "include_tables": settings.PREPROCESSOR_INCLUDE_TABLES,
            },
            chunker_type=ChunkerType(settings.CHUNKER_TYPE),
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            merger_type=EntityMergerType(settings.MERGER_TYPE),
            use_llm_merging=settings.MERGER_USE_LLM,
            merger_config={
                "high_threshold": settings.MERGER_HIGH_SIMILARITY_THRESHOLD,
                "low_threshold": settings.MERGER_LOW_SIMILARITY_THRESHOLD,
                "batch_size": settings.MERGER_LLM_BATCH_SIZE,
            },
            skip_preprocessing=not settings.PREPROCESSING_ENABLED,
            skip_chunking=not settings.CHUNKING_ENABLED,
            max_chunks=settings.MAX_CHUNKS_PER_DOCUMENT,
        )

        # Create pipeline and extractor
        pipeline = PreprocessingPipeline(config)
        extractor = get_ollama_extraction_service()

        # Run pipeline (async in sync context)
        result = asyncio.run(
            pipeline.process(
                content=text,
                extractor=extractor,
                content_type="text/html",
                url=page_url,
                tenant_id=UUID(tenant_id) if tenant_id else None,
            )
        )

        elapsed = time.time() - start_time

        # Add extraction method to entities
        entities = []
        for entity in result.entities:
            entity_copy = entity.copy()
            entity_copy["method"] = ExtractionMethod.LLM_OLLAMA
            entities.append(entity_copy)

        logger.info(
            "Preprocessing pipeline extraction completed",
            extra={
                "page_url": page_url,
                "entities_count": len(entities),
                "relationships_count": len(result.relationships),
                "elapsed_seconds": round(elapsed, 2),
                "original_length": result.original_length,
                "preprocessed_length": result.preprocessed_length,
                "num_chunks": result.num_chunks,
                "preprocessing_method": result.preprocessing_method,
                "chunking_method": result.chunking_method,
                "merging_method": result.merging_method,
                "entities_per_chunk": result.entities_per_chunk,
            },
        )

        return entities, result.relationships

    except Exception as e:
        elapsed = time.time() - start_time
        logger.warning(
            "Preprocessing pipeline extraction failed, falling back to legacy",
            extra={
                "page_url": page_url,
                "error": str(e),
                "error_type": type(e).__name__,
                "elapsed_seconds": round(elapsed, 2),
            },
        )
        # Fall back to legacy extraction on pipeline failure
        return _extract_with_llm_legacy(text, tenant_id, page_url)


def _extract_with_llm_legacy(
    text: str, tenant_id: str, page_url: str = ""
) -> tuple[list[dict], list[dict]]:
    """Legacy extraction without preprocessing pipeline.

    Simple truncation-based extraction for backward compatibility.

    Returns:
        Tuple of (entities, relationships)
    """
    import asyncio
    import time

    from app.extraction.ollama_extractor import ExtractionError, get_ollama_extraction_service

    logger.info(
        "Starting legacy LLM extraction",
        extra={
            "page_url": page_url,
            "text_length": len(text),
            "ollama_url": settings.OLLAMA_BASE_URL,
            "model": settings.OLLAMA_MODEL,
        },
    )

    start_time = time.time()

    try:
        service = get_ollama_extraction_service()
        # Run async extraction in sync context
        result = asyncio.run(service.extract(content=text, page_url=page_url))

        elapsed = time.time() - start_time

        # Convert ExtractionResult to list of entity dicts
        entities = []
        for entity in result.entities:
            # entity_type may be string or enum depending on pydantic-ai parsing
            entity_type = entity.entity_type
            if hasattr(entity_type, "value"):
                entity_type = entity_type.value
            entities.append(
                {
                    "name": entity.name,
                    "type": entity_type,
                    "description": entity.description,
                    "confidence": entity.confidence,
                    "properties": entity.properties or {},
                    "method": ExtractionMethod.LLM_OLLAMA,
                }
            )

        # Convert relationships to list of dicts
        relationships = []
        for rel in result.relationships:
            rel_type = rel.relationship_type
            if hasattr(rel_type, "value"):
                rel_type = rel_type.value
            relationships.append(
                {
                    "source_name": rel.source_name,
                    "target_name": rel.target_name,
                    "relationship_type": rel_type,
                    "confidence": rel.confidence,
                    "context": rel.context,
                    "properties": rel.properties or {},
                }
            )

        logger.info(
            "Legacy LLM extraction completed",
            extra={
                "page_url": page_url,
                "entities_count": len(entities),
                "relationships_count": len(relationships),
                "elapsed_seconds": round(elapsed, 2),
                "text_length": len(text),
            },
        )
        return entities, relationships

    except ExtractionError as e:
        elapsed = time.time() - start_time
        logger.warning(
            "Legacy LLM extraction failed with ExtractionError",
            extra={
                "page_url": page_url,
                "error": str(e),
                "cause": str(e.cause) if e.cause else None,
                "cause_type": type(e.cause).__name__ if e.cause else None,
                "elapsed_seconds": round(elapsed, 2),
                "text_length": len(text),
            },
        )
        return [], []

    except Exception as e:
        elapsed = time.time() - start_time
        logger.warning(
            "Legacy LLM extraction failed with unexpected error",
            extra={
                "page_url": page_url,
                "error": str(e),
                "error_type": type(e).__name__,
                "elapsed_seconds": round(elapsed, 2),
                "text_length": len(text),
            },
        )
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
        total_pages = ctx.db.execute(
            select(func.count())
            .select_from(ScrapedPage)
            .where(ScrapedPage.job_id == UUID(job_id))
        ).scalar() or 0

        completed_pages = ctx.db.execute(
            select(func.count())
            .select_from(ScrapedPage)
            .where(
                ScrapedPage.job_id == UUID(job_id),
                ScrapedPage.extraction_status == "completed",
            )
        ).scalar() or 0

        pending_pages = ctx.db.execute(
            select(func.count())
            .select_from(ScrapedPage)
            .where(
                ScrapedPage.job_id == UUID(job_id),
                ScrapedPage.extraction_status.in_(["pending", "processing"]),
            )
        ).scalar() or 0

        failed_pages = ctx.db.execute(
            select(func.count())
            .select_from(ScrapedPage)
            .where(
                ScrapedPage.job_id == UUID(job_id),
                ScrapedPage.extraction_status == "failed",
            )
        ).scalar() or 0

        # Update progress
        if total_pages > 0:
            job.extraction_progress = completed_pages / total_pages
        job.pages_pending_extraction = pending_pages
        job.updated_at = datetime.now(timezone.utc)
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
        job.updated_at = datetime.now(timezone.utc)
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
