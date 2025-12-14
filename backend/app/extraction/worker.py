"""
Extraction worker task for processing knowledge graph extraction.

This module provides an async task function that coordinates the extraction
process, integrating with the Ollama extraction service, rate limiting,
circuit breaker, and event sourcing infrastructure.

The worker is designed to be called from various contexts:
- Background task queue processing
- Direct invocation from API endpoints
- Scheduled extraction jobs
"""

import logging
import time
from uuid import UUID

from sqlalchemy import select

from app.core.context import set_current_tenant, clear_current_tenant
from app.core.database import AsyncSessionLocal
from app.eventsourcing.aggregates.extraction import (
    ExtractionProcess,
    create_extraction_process_repository,
)
from app.eventsourcing.stores.factory import get_event_store
from app.extraction.circuit_breaker import (
    CircuitOpen,
    get_circuit_breaker,
)
from app.extraction.ollama_extractor import (
    ExtractionError,
    get_ollama_extraction_service,
)
from app.extraction.rate_limiter import (
    RateLimitExceeded,
    get_rate_limiter,
)
from app.models.scraped_page import ScrapedPage

logger = logging.getLogger(__name__)


class ExtractionWorkerError(Exception):
    """Base exception for extraction worker errors.

    Attributes:
        message: Human-readable error message
        process_id: The extraction process ID
        retryable: Whether the error is retryable
    """

    def __init__(
        self,
        message: str,
        process_id: UUID | None = None,
        retryable: bool = True,
    ):
        super().__init__(message)
        self.message = message
        self.process_id = process_id
        self.retryable = retryable


class ProcessNotFoundError(ExtractionWorkerError):
    """Raised when the extraction process cannot be found."""

    def __init__(self, process_id: UUID):
        super().__init__(
            f"ExtractionProcess {process_id} not found",
            process_id=process_id,
            retryable=False,
        )


class PageContentNotFoundError(ExtractionWorkerError):
    """Raised when the page content cannot be retrieved."""

    def __init__(self, page_id: UUID, process_id: UUID | None = None):
        super().__init__(
            f"Page content not found for page {page_id}",
            process_id=process_id,
            retryable=False,
        )
        self.page_id = page_id


async def _get_page_content(page_id: UUID, tenant_id: UUID) -> str | None:
    """Retrieve page content from the database.

    Fetches the text content of a scraped page for extraction processing.

    Args:
        page_id: UUID of the scraped page
        tenant_id: UUID of the tenant owning the page

    Returns:
        The text content of the page, or None if not found
    """
    async with AsyncSessionLocal() as session:
        stmt = select(ScrapedPage.text_content).where(
            ScrapedPage.id == page_id,
            ScrapedPage.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def process_extraction(
    process_id: UUID,
    tenant_id: UUID,
    worker_id: str = "async-worker",
) -> dict:
    """Process an extraction request.

    Loads the extraction process aggregate, extracts entities using Ollama,
    and updates the aggregate with results. Handles rate limiting, circuit
    breaker, and error scenarios gracefully.

    Args:
        process_id: UUID of the ExtractionProcess aggregate
        tenant_id: Tenant identifier
        worker_id: Identifier for the worker processing this extraction

    Returns:
        dict with extraction results:
            - status: "completed", "rate_limited", "circuit_open", or "failed"
            - process_id: The process ID (as string)
            - entities: Number of entities extracted (if completed)
            - relationships: Number of relationships extracted (if completed)
            - duration_ms: Processing duration in milliseconds (if completed)
            - retry_after: Seconds until retry (if rate limited)
            - error: Error message (if failed)

    Raises:
        ProcessNotFoundError: If the extraction process cannot be found
        PageContentNotFoundError: If the page content cannot be retrieved
        ExtractionWorkerError: For other unrecoverable errors
    """
    logger.info(
        "Starting extraction processing",
        extra={
            "process_id": str(process_id),
            "tenant_id": str(tenant_id),
            "worker_id": worker_id,
        },
    )

    # Set tenant context for repository operations
    set_current_tenant(tenant_id)

    try:
        # Check circuit breaker first
        circuit = get_circuit_breaker()
        if not await circuit.allow_request():
            retry_after = await circuit.get_retry_after()
            logger.warning(
                "Circuit breaker is open, skipping extraction",
                extra={
                    "process_id": str(process_id),
                    "tenant_id": str(tenant_id),
                    "retry_after": retry_after,
                },
            )
            return {
                "status": "circuit_open",
                "process_id": str(process_id),
                "retry_after": retry_after,
            }

        # Check rate limit
        rate_limiter = get_rate_limiter()
        try:
            await rate_limiter.acquire(tenant_id)
        except RateLimitExceeded as e:
            logger.warning(
                "Rate limit exceeded, extraction deferred",
                extra={
                    "process_id": str(process_id),
                    "tenant_id": str(tenant_id),
                    "retry_after": e.retry_after,
                },
            )
            return {
                "status": "rate_limited",
                "process_id": str(process_id),
                "retry_after": e.retry_after,
            }

        # Get event store and create repository
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        # Load the extraction process aggregate
        try:
            process = await repo.load(process_id)
        except Exception as e:
            logger.error(
                "Failed to load extraction process",
                extra={
                    "process_id": str(process_id),
                    "error": str(e),
                },
            )
            raise ProcessNotFoundError(process_id) from e

        if process.state is None:
            raise ProcessNotFoundError(process_id)

        # Get page content from database
        content = await _get_page_content(process.state.page_id, tenant_id)
        if not content:
            logger.error(
                "Page content not found",
                extra={
                    "process_id": str(process_id),
                    "page_id": str(process.state.page_id),
                    "tenant_id": str(tenant_id),
                },
            )
            raise PageContentNotFoundError(process.state.page_id, process_id)

        # Start the extraction process
        process.start(worker_id=worker_id)

        start_time = time.time()

        try:
            # Extract using Ollama service
            service = get_ollama_extraction_service()
            extraction_result = await service.extract(
                content=content,
                page_url=process.state.page_url,
            )
            duration_ms = int((time.time() - start_time) * 1000)

            # Record entities
            for entity in extraction_result.entities:
                process.record_entity(
                    entity_type=entity.entity_type,
                    name=entity.name,
                    normalized_name=entity.name.lower().strip(),
                    properties=entity.properties,
                    confidence_score=entity.confidence,
                    description=entity.description,
                    source_text=entity.source_text,
                )

            # Record relationships
            for rel in extraction_result.relationships:
                process.record_relationship(
                    source_entity_name=rel.source_name,
                    target_entity_name=rel.target_name,
                    relationship_type=rel.relationship_type,
                    confidence_score=rel.confidence,
                    context=rel.context,
                )

            # Complete extraction
            process.complete(duration_ms=duration_ms, extraction_method="llm_ollama")
            await circuit.record_success()

            # Save the aggregate
            await repo.save(process)

            logger.info(
                "Extraction completed successfully",
                extra={
                    "process_id": str(process_id),
                    "tenant_id": str(tenant_id),
                    "entity_count": extraction_result.entity_count,
                    "relationship_count": extraction_result.relationship_count,
                    "duration_ms": duration_ms,
                },
            )

            return {
                "status": "completed",
                "process_id": str(process_id),
                "entities": extraction_result.entity_count,
                "relationships": extraction_result.relationship_count,
                "duration_ms": duration_ms,
            }

        except ExtractionError as e:
            # Extraction failed - record failure and circuit breaker
            duration_ms = int((time.time() - start_time) * 1000)
            await circuit.record_failure()

            process.fail(
                error_message=str(e),
                error_type=type(e).__name__,
                retryable=True,  # Extraction errors are usually retryable
            )
            await repo.save(process)

            logger.error(
                "Extraction failed",
                extra={
                    "process_id": str(process_id),
                    "tenant_id": str(tenant_id),
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": duration_ms,
                },
            )

            return {
                "status": "failed",
                "process_id": str(process_id),
                "error": str(e),
                "error_type": type(e).__name__,
                "retryable": True,
            }

        except Exception as e:
            # Unexpected error during extraction
            duration_ms = int((time.time() - start_time) * 1000)
            await circuit.record_failure()

            process.fail(
                error_message=str(e),
                error_type=type(e).__name__,
                retryable=False,  # Unknown errors may not be retryable
            )
            await repo.save(process)

            logger.error(
                "Unexpected error during extraction",
                extra={
                    "process_id": str(process_id),
                    "tenant_id": str(tenant_id),
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": duration_ms,
                },
                exc_info=True,
            )

            return {
                "status": "failed",
                "process_id": str(process_id),
                "error": str(e),
                "error_type": type(e).__name__,
                "retryable": False,
            }

    finally:
        # Always clear tenant context
        clear_current_tenant()


__all__ = [
    "process_extraction",
    "ExtractionWorkerError",
    "ProcessNotFoundError",
    "PageContentNotFoundError",
]
