"""
ExtractionProcess Aggregate for knowledge graph extraction pipeline.

This aggregate manages the lifecycle of an extraction process, from initial
request through completion or failure. It enforces business invariants and
tracks all entities and relationships discovered during extraction.

The aggregate uses eventsource-py's DeclarativeAggregate pattern with
@handles decorators for clean event handler registration.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from eventsource import DeclarativeAggregate, handles
from pydantic import BaseModel, Field

from app.eventsourcing.events.extraction import (
    ExtractionCompleted,
    ExtractionProcessFailed,
    ExtractionRequested,
    ExtractionRetryScheduled,
    ExtractionStarted,
    RelationshipDiscovered,
)
from app.eventsourcing.events.scraping import EntityExtracted

if TYPE_CHECKING:
    from eventsource import AggregateRepository, EventStore


# =============================================================================
# Enums
# =============================================================================


class ExtractionStatus(str, Enum):
    """Status of an extraction process."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# =============================================================================
# State Model
# =============================================================================


class ExtractedEntityRecord(BaseModel):
    """Record of an entity extracted during the process."""

    entity_id: UUID
    entity_type: str
    name: str
    normalized_name: str
    properties: dict = Field(default_factory=dict)
    confidence_score: float
    source_text: str | None = None


class ExtractedRelationshipRecord(BaseModel):
    """Record of a relationship discovered during the process."""

    relationship_id: UUID
    source_entity_name: str
    target_entity_name: str
    relationship_type: str
    confidence_score: float
    context: str | None = None


class ExtractionProcessState(BaseModel):
    """
    State model for ExtractionProcess aggregate.

    Tracks all information about an extraction process including:
    - Configuration and request details
    - Processing status and worker assignment
    - Extracted entities and relationships
    - Error information for failed extractions
    - Retry tracking for resilience
    """

    # Identity
    extraction_id: UUID
    tenant_id: UUID

    # Request details
    page_id: UUID
    page_url: str
    content_hash: str
    extraction_config: dict = Field(default_factory=dict)
    requested_at: datetime

    # Processing status
    status: ExtractionStatus = ExtractionStatus.PENDING
    worker_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None

    # Results
    entities: list[ExtractedEntityRecord] = Field(default_factory=list)
    relationships: list[ExtractedRelationshipRecord] = Field(default_factory=list)
    duration_ms: int | None = None
    extraction_method: str | None = None

    # Error tracking
    error_message: str | None = None
    error_type: str | None = None
    retryable: bool = True
    retry_count: int = 0
    next_retry_at: datetime | None = None


# =============================================================================
# Aggregate
# =============================================================================


class ExtractionProcess(DeclarativeAggregate[ExtractionProcessState]):
    """
    Aggregate for managing an extraction process lifecycle.

    This aggregate tracks the complete extraction lifecycle:
    1. Request: A page is queued for extraction
    2. Start: A worker picks up the extraction
    3. Entity Recording: Entities are discovered and recorded
    4. Relationship Recording: Relationships between entities are discovered
    5. Completion/Failure: Extraction finishes successfully or fails

    Business Invariants:
    - Cannot start an already started/completed/failed extraction
    - Cannot record entities/relationships before extraction starts
    - Cannot complete/fail an extraction that hasn't started
    - Cannot retry a non-retryable failure

    Example:
        >>> from uuid import uuid4
        >>> process = ExtractionProcess(uuid4())
        >>> process.request_extraction(
        ...     page_id=uuid4(),
        ...     tenant_id=uuid4(),
        ...     page_url="https://example.com/page",
        ...     content_hash="abc123",
        ...     config={"model": "llama3.2"}
        ... )
        >>> process.start(worker_id="worker-1")
        >>> process.record_entity(
        ...     entity_type="FUNCTION",
        ...     name="process_data",
        ...     normalized_name="process_data",
        ...     properties={"signature": "def process_data(x: int) -> str"},
        ...     confidence_score=0.95
        ... )
        >>> process.complete(duration_ms=1500, extraction_method="llm_ollama")
    """

    aggregate_type = "ExtractionProcess"

    def _get_initial_state(self) -> ExtractionProcessState:
        """Return the initial state for a new extraction process."""
        # Initial state is populated by ExtractionRequested event
        # This should never be called directly as first event sets full state
        raise RuntimeError("ExtractionProcess requires request_extraction() to initialize state")

    # =========================================================================
    # Command Methods
    # =========================================================================

    def request_extraction(
        self,
        page_id: UUID,
        tenant_id: UUID,
        page_url: str,
        content_hash: str,
        config: dict | None = None,
    ) -> None:
        """
        Request extraction for a scraped page.

        This initializes the extraction process and queues it for processing.

        Args:
            page_id: ID of the scraped page
            tenant_id: Tenant owning the page
            page_url: URL of the page
            content_hash: Hash of page content for change detection
            config: Optional extraction configuration (model, prompts, etc.)

        Raises:
            ValueError: If extraction has already been requested
        """
        if self.version > 0:
            raise ValueError("Extraction has already been requested for this process")

        self.create_event(
            ExtractionRequested,
            tenant_id=tenant_id,
            page_id=page_id,
            page_url=page_url,
            content_hash=content_hash,
            extraction_config=config or {},
            requested_at=datetime.now(UTC),
        )

    def start(self, worker_id: str) -> None:
        """
        Start processing the extraction.

        Called when a worker picks up the extraction task.

        Args:
            worker_id: ID of the worker processing the extraction

        Raises:
            ValueError: If extraction is not in PENDING status
        """
        if self._state is None:
            raise ValueError("Cannot start extraction: not yet requested")

        if self._state.status != ExtractionStatus.PENDING:
            raise ValueError(
                f"Cannot start extraction in {self._state.status.value} status. "
                f"Only PENDING extractions can be started."
            )

        self.create_event(
            ExtractionStarted,
            tenant_id=self._state.tenant_id,
            page_id=self._state.page_id,
            worker_id=worker_id,
            started_at=datetime.now(UTC),
        )

    def record_entity(
        self,
        entity_type: str,
        name: str,
        normalized_name: str,
        properties: dict | None = None,
        confidence_score: float = 1.0,
        description: str | None = None,
        source_text: str | None = None,
        job_id: UUID | None = None,
        extraction_method: str = "llm",
    ) -> UUID:
        """
        Record an extracted entity.

        Args:
            entity_type: Type of entity (FUNCTION, CLASS, CONCEPT, etc.)
            name: Entity name as extracted
            normalized_name: Normalized name for deduplication
            properties: Type-specific properties
            confidence_score: Confidence in extraction (0.0-1.0)
            description: Optional entity description
            source_text: Text snippet where entity was found
            job_id: Optional job ID for tracking
            extraction_method: How entity was extracted

        Returns:
            UUID of the created entity

        Raises:
            ValueError: If extraction is not IN_PROGRESS
        """
        if self._state is None:
            raise ValueError("Cannot record entity: extraction not yet requested")

        if self._state.status != ExtractionStatus.IN_PROGRESS:
            raise ValueError(
                f"Cannot record entity in {self._state.status.value} status. "
                f"Extraction must be IN_PROGRESS."
            )

        from uuid import uuid4

        entity_id = uuid4()

        self.create_event(
            EntityExtracted,
            tenant_id=self._state.tenant_id,
            entity_id=entity_id,
            page_id=self._state.page_id,
            job_id=job_id or self._state.page_id,  # Fallback to page_id if no job
            entity_type=entity_type,
            name=name,
            normalized_name=normalized_name,
            description=description,
            properties=properties or {},
            extraction_method=extraction_method,
            confidence_score=confidence_score,
            source_text=source_text,
        )
        return entity_id

    def record_relationship(
        self,
        source_entity_name: str,
        target_entity_name: str,
        relationship_type: str,
        confidence_score: float = 1.0,
        context: str | None = None,
    ) -> UUID:
        """
        Record a discovered relationship between entities.

        Args:
            source_entity_name: Name of the source entity
            target_entity_name: Name of the target entity
            relationship_type: Type of relationship (CALLS, EXTENDS, etc.)
            confidence_score: Confidence in the relationship (0.0-1.0)
            context: Optional context where relationship was found

        Returns:
            UUID of the created relationship

        Raises:
            ValueError: If extraction is not IN_PROGRESS
        """
        if self._state is None:
            raise ValueError("Cannot record relationship: extraction not yet requested")

        if self._state.status != ExtractionStatus.IN_PROGRESS:
            raise ValueError(
                f"Cannot record relationship in {self._state.status.value} status. "
                f"Extraction must be IN_PROGRESS."
            )

        from uuid import uuid4

        relationship_id = uuid4()

        self.create_event(
            RelationshipDiscovered,
            tenant_id=self._state.tenant_id,
            relationship_id=relationship_id,
            page_id=self._state.page_id,
            source_entity_name=source_entity_name,
            target_entity_name=target_entity_name,
            relationship_type=relationship_type,
            confidence_score=confidence_score,
            context=context,
        )
        return relationship_id

    def complete(self, duration_ms: int, extraction_method: str) -> None:
        """
        Mark extraction as complete.

        Args:
            duration_ms: Total extraction duration in milliseconds
            extraction_method: Method used for extraction (e.g., "llm_ollama")

        Raises:
            ValueError: If extraction is not IN_PROGRESS
        """
        if self._state is None:
            raise ValueError("Cannot complete extraction: not yet requested")

        if self._state.status != ExtractionStatus.IN_PROGRESS:
            raise ValueError(
                f"Cannot complete extraction in {self._state.status.value} status. "
                f"Extraction must be IN_PROGRESS."
            )

        self.create_event(
            ExtractionCompleted,
            tenant_id=self._state.tenant_id,
            page_id=self._state.page_id,
            entity_count=len(self._state.entities),
            relationship_count=len(self._state.relationships),
            duration_ms=duration_ms,
            extraction_method=extraction_method,
            completed_at=datetime.now(UTC),
        )

    def fail(
        self,
        error_message: str,
        error_type: str,
        retryable: bool = True,
    ) -> None:
        """
        Mark extraction as failed.

        Args:
            error_message: Human-readable error message
            error_type: Classification of error (e.g., "LLM_TIMEOUT", "PARSE_ERROR")
            retryable: Whether this failure can be retried

        Raises:
            ValueError: If extraction is not IN_PROGRESS
        """
        if self._state is None:
            raise ValueError("Cannot fail extraction: not yet requested")

        if self._state.status != ExtractionStatus.IN_PROGRESS:
            raise ValueError(
                f"Cannot fail extraction in {self._state.status.value} status. "
                f"Extraction must be IN_PROGRESS."
            )

        self.create_event(
            ExtractionProcessFailed,
            tenant_id=self._state.tenant_id,
            page_id=self._state.page_id,
            error_message=error_message,
            error_type=error_type,
            retry_count=self._state.retry_count,
            retryable=retryable,
            failed_at=datetime.now(UTC),
        )

    def schedule_retry(self, scheduled_for: datetime, backoff_seconds: float) -> None:
        """
        Schedule a retry for a failed extraction.

        Args:
            scheduled_for: When the retry should be attempted
            backoff_seconds: Backoff duration before retry

        Raises:
            ValueError: If extraction is not FAILED or not retryable
        """
        if self._state is None:
            raise ValueError("Cannot schedule retry: extraction not yet requested")

        if self._state.status != ExtractionStatus.FAILED:
            raise ValueError(
                f"Cannot schedule retry in {self._state.status.value} status. "
                f"Only FAILED extractions can be retried."
            )

        if not self._state.retryable:
            raise ValueError("Cannot retry: extraction is marked as non-retryable")

        self.create_event(
            ExtractionRetryScheduled,
            tenant_id=self._state.tenant_id,
            page_id=self._state.page_id,
            retry_number=self._state.retry_count + 1,
            scheduled_for=scheduled_for,
            backoff_seconds=backoff_seconds,
        )

    # =========================================================================
    # Event Handlers
    # =========================================================================

    @handles(ExtractionRequested)
    def _on_extraction_requested(self, event: ExtractionRequested) -> None:
        """Handle ExtractionRequested event - initialize state."""
        self._state = ExtractionProcessState(
            extraction_id=self.aggregate_id,
            tenant_id=event.tenant_id,
            page_id=event.page_id,
            page_url=event.page_url,
            content_hash=event.content_hash,
            extraction_config=event.extraction_config,
            requested_at=event.requested_at,
            status=ExtractionStatus.PENDING,
        )

    @handles(ExtractionStarted)
    def _on_extraction_started(self, event: ExtractionStarted) -> None:
        """Handle ExtractionStarted event - mark as in progress."""
        if self._state is None:
            return

        self._state = self._state.model_copy(
            update={
                "status": ExtractionStatus.IN_PROGRESS,
                "worker_id": event.worker_id,
                "started_at": event.started_at,
            }
        )

    @handles(EntityExtracted)
    def _on_entity_extracted(self, event: EntityExtracted) -> None:
        """Handle EntityExtracted event - record extracted entity."""
        if self._state is None:
            return

        entity_record = ExtractedEntityRecord(
            entity_id=event.entity_id,
            entity_type=event.entity_type,
            name=event.name,
            normalized_name=event.normalized_name,
            properties=event.properties,
            confidence_score=event.confidence_score,
            source_text=event.source_text,
        )

        self._state = self._state.model_copy(
            update={"entities": [*self._state.entities, entity_record]}
        )

    @handles(RelationshipDiscovered)
    def _on_relationship_discovered(self, event: RelationshipDiscovered) -> None:
        """Handle RelationshipDiscovered event - record relationship."""
        if self._state is None:
            return

        relationship_record = ExtractedRelationshipRecord(
            relationship_id=event.relationship_id,
            source_entity_name=event.source_entity_name,
            target_entity_name=event.target_entity_name,
            relationship_type=event.relationship_type,
            confidence_score=event.confidence_score,
            context=event.context,
        )

        self._state = self._state.model_copy(
            update={"relationships": [*self._state.relationships, relationship_record]}
        )

    @handles(ExtractionCompleted)
    def _on_extraction_completed(self, event: ExtractionCompleted) -> None:
        """Handle ExtractionCompleted event - mark as complete."""
        if self._state is None:
            return

        self._state = self._state.model_copy(
            update={
                "status": ExtractionStatus.COMPLETED,
                "completed_at": event.completed_at,
                "duration_ms": event.duration_ms,
                "extraction_method": event.extraction_method,
            }
        )

    @handles(ExtractionProcessFailed)
    def _on_extraction_failed(self, event: ExtractionProcessFailed) -> None:
        """Handle ExtractionProcessFailed event - mark as failed."""
        if self._state is None:
            return

        self._state = self._state.model_copy(
            update={
                "status": ExtractionStatus.FAILED,
                "failed_at": event.failed_at,
                "error_message": event.error_message,
                "error_type": event.error_type,
                "retryable": event.retryable,
                "retry_count": event.retry_count,
            }
        )

    @handles(ExtractionRetryScheduled)
    def _on_retry_scheduled(self, event: ExtractionRetryScheduled) -> None:
        """Handle ExtractionRetryScheduled event - reset to pending for retry."""
        if self._state is None:
            return

        self._state = self._state.model_copy(
            update={
                "status": ExtractionStatus.PENDING,
                "retry_count": event.retry_number,
                "next_retry_at": event.scheduled_for,
                # Clear error state for retry
                "error_message": None,
                "error_type": None,
                "failed_at": None,
            }
        )


# =============================================================================
# Repository Factory
# =============================================================================


def create_extraction_process_repository(
    event_store: "EventStore",
) -> "AggregateRepository[ExtractionProcess]":
    """
    Create a repository for ExtractionProcess aggregates.

    This factory function provides a convenient way to create properly
    configured repositories for extraction process management.

    Args:
        event_store: The event store for persistence

    Returns:
        Configured AggregateRepository for ExtractionProcess

    Example:
        >>> from eventsource import InMemoryEventStore
        >>> store = InMemoryEventStore()
        >>> repo = create_extraction_process_repository(store)
        >>> process = repo.create_new(uuid4())
    """
    from eventsource import AggregateRepository

    return AggregateRepository(
        event_store=event_store,
        aggregate_factory=ExtractionProcess,
        aggregate_type="ExtractionProcess",
    )


__all__ = [
    "ExtractionProcess",
    "ExtractionProcessState",
    "ExtractionStatus",
    "ExtractedEntityRecord",
    "ExtractedRelationshipRecord",
    "create_extraction_process_repository",
]
