"""
Unit tests for extraction domain events.

Tests cover event creation, field initialization, defaults, validation,
and serialization/deserialization roundtrip for all extraction events.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.eventsourcing.events.extraction import (
    ExtractionBatchCompleted,
    ExtractionBatchStarted,
    ExtractionCompleted,
    ExtractionProcessFailed,
    ExtractionRequested,
    ExtractionRetryScheduled,
    ExtractionStarted,
    RelationshipDiscovered,
)


# =============================================================================
# Helper Functions
# =============================================================================


def make_base_event_kwargs() -> dict:
    """Create base kwargs required for all events."""
    return {
        "aggregate_id": uuid4(),
        "tenant_id": uuid4(),
    }


# =============================================================================
# ExtractionRequested Tests
# =============================================================================


class TestExtractionRequested:
    """Tests for ExtractionRequested event."""

    def test_create_with_all_fields(self):
        """Test creating event with all fields populated."""
        base_kwargs = make_base_event_kwargs()
        page_id = uuid4()
        requested_at = datetime.now(timezone.utc)
        config = {"max_entities": 100, "model": "llama3.2"}

        event = ExtractionRequested(
            **base_kwargs,
            page_id=page_id,
            page_url="https://docs.example.com/page",
            content_hash="abc123def456",
            extraction_config=config,
            requested_at=requested_at,
        )

        assert event.event_type == "ExtractionRequested"
        assert event.aggregate_type == "ExtractionProcess"
        assert event.page_id == page_id
        assert event.page_url == "https://docs.example.com/page"
        assert event.content_hash == "abc123def456"
        assert event.extraction_config == config
        assert event.requested_at == requested_at
        assert event.tenant_id == base_kwargs["tenant_id"]

    def test_create_with_default_extraction_config(self):
        """Test creating event with default empty extraction config."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionRequested(
            **base_kwargs,
            page_id=uuid4(),
            page_url="https://docs.example.com",
            content_hash="hash123",
            requested_at=datetime.now(timezone.utc),
        )

        assert event.extraction_config == {}

    def test_event_type_is_correct(self):
        """Test that event_type class attribute is correctly set."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionRequested(
            **base_kwargs,
            page_id=uuid4(),
            page_url="https://example.com",
            content_hash="hash",
            requested_at=datetime.now(timezone.utc),
        )

        assert event.event_type == "ExtractionRequested"

    def test_aggregate_type_is_extraction_process(self):
        """Test that aggregate_type is ExtractionProcess."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionRequested(
            **base_kwargs,
            page_id=uuid4(),
            page_url="https://example.com",
            content_hash="hash",
            requested_at=datetime.now(timezone.utc),
        )

        assert event.aggregate_type == "ExtractionProcess"

    def test_serialization_roundtrip(self):
        """Test event serializes and deserializes correctly."""
        base_kwargs = make_base_event_kwargs()
        page_id = uuid4()
        requested_at = datetime.now(timezone.utc)
        config = {"llm_model": "codellama"}

        original = ExtractionRequested(
            **base_kwargs,
            page_id=page_id,
            page_url="https://docs.example.com/api",
            content_hash="contenthash123",
            extraction_config=config,
            requested_at=requested_at,
        )

        # Serialize to dict and back
        data = original.model_dump()
        restored = ExtractionRequested(**data)

        assert restored.event_id == original.event_id
        assert restored.aggregate_id == original.aggregate_id
        assert restored.tenant_id == original.tenant_id
        assert restored.page_id == original.page_id
        assert restored.page_url == original.page_url
        assert restored.content_hash == original.content_hash
        assert restored.extraction_config == original.extraction_config
        assert restored.requested_at == original.requested_at

    def test_json_serialization_roundtrip(self):
        """Test event serializes to JSON and back correctly."""
        base_kwargs = make_base_event_kwargs()

        original = ExtractionRequested(
            **base_kwargs,
            page_id=uuid4(),
            page_url="https://example.com/page",
            content_hash="abc",
            requested_at=datetime.now(timezone.utc),
        )

        # Use to_dict for JSON-compatible serialization
        json_data = original.to_dict()

        # Verify UUIDs are strings
        assert isinstance(json_data["event_id"], str)
        assert isinstance(json_data["aggregate_id"], str)
        assert isinstance(json_data["page_id"], str)

        # Verify we can restore
        restored = ExtractionRequested.from_dict(json_data)
        assert restored.page_id == original.page_id

    def test_tenant_id_is_required(self):
        """Test that tenant_id is required (from TenantDomainEvent)."""
        with pytest.raises(Exception):  # ValidationError
            ExtractionRequested(
                aggregate_id=uuid4(),
                # Missing tenant_id
                page_id=uuid4(),
                page_url="https://example.com",
                content_hash="hash",
                requested_at=datetime.now(timezone.utc),
            )


# =============================================================================
# ExtractionStarted Tests
# =============================================================================


class TestExtractionStarted:
    """Tests for ExtractionStarted event."""

    def test_create_with_all_fields(self):
        """Test creating event with all fields populated."""
        from app.eventsourcing.events.extraction import ExtractionStarted

        base_kwargs = make_base_event_kwargs()
        page_id = uuid4()
        started_at = datetime.now(timezone.utc)

        event = ExtractionStarted(
            **base_kwargs,
            page_id=page_id,
            worker_id="worker-node-1",
            started_at=started_at,
        )

        assert event.event_type == "ExtractionStarted"
        assert event.aggregate_type == "ExtractionProcess"
        assert event.page_id == page_id
        assert event.worker_id == "worker-node-1"
        assert event.started_at == started_at

    def test_worker_id_captured(self):
        """Test that worker_id is properly captured."""
        from app.eventsourcing.events.extraction import ExtractionStarted

        base_kwargs = make_base_event_kwargs()

        event = ExtractionStarted(
            **base_kwargs,
            page_id=uuid4(),
            worker_id="celery-worker-abc123",
            started_at=datetime.now(timezone.utc),
        )

        assert event.worker_id == "celery-worker-abc123"

    def test_serialization_roundtrip(self):
        """Test event serializes and deserializes correctly."""
        from app.eventsourcing.events.extraction import ExtractionStarted

        base_kwargs = make_base_event_kwargs()

        original = ExtractionStarted(
            **base_kwargs,
            page_id=uuid4(),
            worker_id="worker-2",
            started_at=datetime.now(timezone.utc),
        )

        data = original.model_dump()
        restored = ExtractionStarted(**data)

        assert restored.page_id == original.page_id
        assert restored.worker_id == original.worker_id
        assert restored.started_at == original.started_at


# =============================================================================
# ExtractionCompleted Tests
# =============================================================================


class TestExtractionCompleted:
    """Tests for ExtractionCompleted event."""

    def test_create_with_all_fields(self):
        """Test creating event with all fields populated."""
        base_kwargs = make_base_event_kwargs()
        page_id = uuid4()
        completed_at = datetime.now(timezone.utc)

        event = ExtractionCompleted(
            **base_kwargs,
            page_id=page_id,
            entity_count=25,
            relationship_count=12,
            duration_ms=3500,
            extraction_method="llm_ollama",
            completed_at=completed_at,
        )

        assert event.event_type == "ExtractionCompleted"
        assert event.aggregate_type == "ExtractionProcess"
        assert event.page_id == page_id
        assert event.entity_count == 25
        assert event.relationship_count == 12
        assert event.duration_ms == 3500
        assert event.extraction_method == "llm_ollama"
        assert event.completed_at == completed_at

    def test_includes_extraction_statistics(self):
        """Test event includes all extraction statistics."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionCompleted(
            **base_kwargs,
            page_id=uuid4(),
            entity_count=100,
            relationship_count=50,
            duration_ms=5000,
            extraction_method="hybrid",
            completed_at=datetime.now(timezone.utc),
        )

        assert event.entity_count == 100
        assert event.relationship_count == 50
        assert event.duration_ms == 5000
        assert event.extraction_method == "hybrid"

    def test_zero_counts_allowed(self):
        """Test that zero entity/relationship counts are valid."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionCompleted(
            **base_kwargs,
            page_id=uuid4(),
            entity_count=0,
            relationship_count=0,
            duration_ms=100,
            extraction_method="llm",
            completed_at=datetime.now(timezone.utc),
        )

        assert event.entity_count == 0
        assert event.relationship_count == 0

    def test_serialization_roundtrip(self):
        """Test event serializes and deserializes correctly."""
        base_kwargs = make_base_event_kwargs()

        original = ExtractionCompleted(
            **base_kwargs,
            page_id=uuid4(),
            entity_count=15,
            relationship_count=8,
            duration_ms=2500,
            extraction_method="regex",
            completed_at=datetime.now(timezone.utc),
        )

        data = original.model_dump()
        restored = ExtractionCompleted(**data)

        assert restored.entity_count == original.entity_count
        assert restored.relationship_count == original.relationship_count
        assert restored.duration_ms == original.duration_ms
        assert restored.extraction_method == original.extraction_method


# =============================================================================
# ExtractionProcessFailed Tests
# =============================================================================


class TestExtractionProcessFailed:
    """Tests for ExtractionProcessFailed event."""

    def test_create_with_all_fields(self):
        """Test creating event with all fields populated."""
        base_kwargs = make_base_event_kwargs()
        page_id = uuid4()
        failed_at = datetime.now(timezone.utc)

        event = ExtractionProcessFailed(
            **base_kwargs,
            page_id=page_id,
            error_message="LLM timeout after 30s",
            error_type="LLM_TIMEOUT",
            retry_count=2,
            retryable=True,
            failed_at=failed_at,
        )

        assert event.event_type == "ExtractionProcessFailed"
        assert event.aggregate_type == "ExtractionProcess"
        assert event.page_id == page_id
        assert event.error_message == "LLM timeout after 30s"
        assert event.error_type == "LLM_TIMEOUT"
        assert event.retry_count == 2
        assert event.retryable is True
        assert event.failed_at == failed_at

    def test_default_retry_count_is_zero(self):
        """Test default retry_count is 0."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionProcessFailed(
            **base_kwargs,
            page_id=uuid4(),
            error_message="Some error",
            error_type="UNKNOWN",
            failed_at=datetime.now(timezone.utc),
        )

        assert event.retry_count == 0

    def test_default_retryable_is_true(self):
        """Test default retryable is True."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionProcessFailed(
            **base_kwargs,
            page_id=uuid4(),
            error_message="Temporary failure",
            error_type="NETWORK_ERROR",
            failed_at=datetime.now(timezone.utc),
        )

        assert event.retryable is True

    def test_non_retryable_error(self):
        """Test marking error as non-retryable."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionProcessFailed(
            **base_kwargs,
            page_id=uuid4(),
            error_message="Invalid content format - cannot parse",
            error_type="PARSE_ERROR",
            retryable=False,
            failed_at=datetime.now(timezone.utc),
        )

        assert event.retryable is False

    def test_serialization_roundtrip(self):
        """Test event serializes and deserializes correctly."""
        base_kwargs = make_base_event_kwargs()

        original = ExtractionProcessFailed(
            **base_kwargs,
            page_id=uuid4(),
            error_message="Connection refused",
            error_type="CONNECTION_ERROR",
            retry_count=3,
            retryable=True,
            failed_at=datetime.now(timezone.utc),
        )

        data = original.model_dump()
        restored = ExtractionProcessFailed(**data)

        assert restored.error_message == original.error_message
        assert restored.error_type == original.error_type
        assert restored.retry_count == original.retry_count
        assert restored.retryable == original.retryable


# =============================================================================
# ExtractionRetryScheduled Tests
# =============================================================================


class TestExtractionRetryScheduled:
    """Tests for ExtractionRetryScheduled event."""

    def test_create_with_all_fields(self):
        """Test creating event with all fields populated."""
        base_kwargs = make_base_event_kwargs()
        page_id = uuid4()
        scheduled_for = datetime.now(timezone.utc)

        event = ExtractionRetryScheduled(
            **base_kwargs,
            page_id=page_id,
            retry_number=1,
            scheduled_for=scheduled_for,
            backoff_seconds=30.0,
        )

        assert event.event_type == "ExtractionRetryScheduled"
        assert event.aggregate_type == "ExtractionProcess"
        assert event.page_id == page_id
        assert event.retry_number == 1
        assert event.scheduled_for == scheduled_for
        assert event.backoff_seconds == 30.0

    def test_retry_number_increments(self):
        """Test that retry_number properly tracks attempt count."""
        base_kwargs = make_base_event_kwargs()

        # First retry
        event1 = ExtractionRetryScheduled(
            **base_kwargs,
            page_id=uuid4(),
            retry_number=1,
            scheduled_for=datetime.now(timezone.utc),
            backoff_seconds=30.0,
        )
        assert event1.retry_number == 1

        # Second retry
        event2 = ExtractionRetryScheduled(
            **base_kwargs,
            page_id=uuid4(),
            retry_number=2,
            scheduled_for=datetime.now(timezone.utc),
            backoff_seconds=60.0,
        )
        assert event2.retry_number == 2

    def test_backoff_seconds_is_float(self):
        """Test that backoff_seconds accepts float values."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionRetryScheduled(
            **base_kwargs,
            page_id=uuid4(),
            retry_number=1,
            scheduled_for=datetime.now(timezone.utc),
            backoff_seconds=45.5,
        )

        assert event.backoff_seconds == 45.5

    def test_serialization_roundtrip(self):
        """Test event serializes and deserializes correctly."""
        base_kwargs = make_base_event_kwargs()

        original = ExtractionRetryScheduled(
            **base_kwargs,
            page_id=uuid4(),
            retry_number=3,
            scheduled_for=datetime.now(timezone.utc),
            backoff_seconds=120.0,
        )

        data = original.model_dump()
        restored = ExtractionRetryScheduled(**data)

        assert restored.retry_number == original.retry_number
        assert restored.scheduled_for == original.scheduled_for
        assert restored.backoff_seconds == original.backoff_seconds


# =============================================================================
# RelationshipDiscovered Tests
# =============================================================================


class TestRelationshipDiscovered:
    """Tests for RelationshipDiscovered event."""

    def test_create_with_all_fields(self):
        """Test creating event with all fields populated."""
        base_kwargs = make_base_event_kwargs()
        relationship_id = uuid4()
        page_id = uuid4()

        event = RelationshipDiscovered(
            **base_kwargs,
            relationship_id=relationship_id,
            page_id=page_id,
            source_entity_name="DomainEvent",
            target_entity_name="BaseModel",
            relationship_type="EXTENDS",
            confidence_score=0.95,
            context="class DomainEvent(BaseModel):",
        )

        assert event.event_type == "RelationshipDiscovered"
        assert event.aggregate_type == "ExtractionProcess"
        assert event.relationship_id == relationship_id
        assert event.page_id == page_id
        assert event.source_entity_name == "DomainEvent"
        assert event.target_entity_name == "BaseModel"
        assert event.relationship_type == "EXTENDS"
        assert event.confidence_score == 0.95
        assert event.context == "class DomainEvent(BaseModel):"

    def test_create_without_optional_context(self):
        """Test creating event without optional context field."""
        base_kwargs = make_base_event_kwargs()

        event = RelationshipDiscovered(
            **base_kwargs,
            relationship_id=uuid4(),
            page_id=uuid4(),
            source_entity_name="FunctionA",
            target_entity_name="FunctionB",
            relationship_type="CALLS",
            confidence_score=0.8,
        )

        assert event.context is None

    def test_context_default_is_none(self):
        """Test that context defaults to None."""
        base_kwargs = make_base_event_kwargs()

        event = RelationshipDiscovered(
            **base_kwargs,
            relationship_id=uuid4(),
            page_id=uuid4(),
            source_entity_name="A",
            target_entity_name="B",
            relationship_type="RELATED_TO",
            confidence_score=0.5,
        )

        assert event.context is None

    def test_confidence_score_range(self):
        """Test confidence score accepts values in valid range."""
        base_kwargs = make_base_event_kwargs()

        # Test minimum
        event_min = RelationshipDiscovered(
            **base_kwargs,
            relationship_id=uuid4(),
            page_id=uuid4(),
            source_entity_name="A",
            target_entity_name="B",
            relationship_type="RELATED",
            confidence_score=0.0,
        )
        assert event_min.confidence_score == 0.0

        # Test maximum
        event_max = RelationshipDiscovered(
            **base_kwargs,
            relationship_id=uuid4(),
            page_id=uuid4(),
            source_entity_name="A",
            target_entity_name="B",
            relationship_type="RELATED",
            confidence_score=1.0,
        )
        assert event_max.confidence_score == 1.0

    def test_relationship_types(self):
        """Test various relationship types are accepted."""
        base_kwargs = make_base_event_kwargs()
        relationship_types = ["CALLS", "EXTENDS", "IMPLEMENTS", "USES", "DEPENDS_ON"]

        for rel_type in relationship_types:
            event = RelationshipDiscovered(
                **base_kwargs,
                relationship_id=uuid4(),
                page_id=uuid4(),
                source_entity_name="Source",
                target_entity_name="Target",
                relationship_type=rel_type,
                confidence_score=0.9,
            )
            assert event.relationship_type == rel_type

    def test_serialization_roundtrip(self):
        """Test event serializes and deserializes correctly."""
        base_kwargs = make_base_event_kwargs()

        original = RelationshipDiscovered(
            **base_kwargs,
            relationship_id=uuid4(),
            page_id=uuid4(),
            source_entity_name="ClassA",
            target_entity_name="ClassB",
            relationship_type="INHERITS",
            confidence_score=0.88,
            context="class ClassA(ClassB):",
        )

        data = original.model_dump()
        restored = RelationshipDiscovered(**data)

        assert restored.relationship_id == original.relationship_id
        assert restored.source_entity_name == original.source_entity_name
        assert restored.target_entity_name == original.target_entity_name
        assert restored.relationship_type == original.relationship_type
        assert restored.confidence_score == original.confidence_score
        assert restored.context == original.context


# =============================================================================
# ExtractionBatchStarted Tests
# =============================================================================


class TestExtractionBatchStarted:
    """Tests for ExtractionBatchStarted event."""

    def test_create_with_all_fields(self):
        """Test creating event with all fields populated."""
        base_kwargs = make_base_event_kwargs()
        batch_id = uuid4()
        page_ids = [uuid4() for _ in range(5)]
        started_at = datetime.now(timezone.utc)

        event = ExtractionBatchStarted(
            **base_kwargs,
            batch_id=batch_id,
            page_ids=page_ids,
            total_pages=5,
            started_at=started_at,
        )

        assert event.event_type == "ExtractionBatchStarted"
        assert event.aggregate_type == "ExtractionBatch"
        assert event.batch_id == batch_id
        assert event.page_ids == page_ids
        assert event.total_pages == 5
        assert event.started_at == started_at

    def test_empty_page_ids_list(self):
        """Test batch with empty page_ids list."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionBatchStarted(
            **base_kwargs,
            batch_id=uuid4(),
            page_ids=[],
            total_pages=0,
            started_at=datetime.now(timezone.utc),
        )

        assert event.page_ids == []
        assert event.total_pages == 0

    def test_large_batch(self):
        """Test batch with many pages."""
        base_kwargs = make_base_event_kwargs()
        page_ids = [uuid4() for _ in range(100)]

        event = ExtractionBatchStarted(
            **base_kwargs,
            batch_id=uuid4(),
            page_ids=page_ids,
            total_pages=100,
            started_at=datetime.now(timezone.utc),
        )

        assert len(event.page_ids) == 100
        assert event.total_pages == 100

    def test_serialization_roundtrip(self):
        """Test event serializes and deserializes correctly."""
        base_kwargs = make_base_event_kwargs()
        page_ids = [uuid4() for _ in range(3)]

        original = ExtractionBatchStarted(
            **base_kwargs,
            batch_id=uuid4(),
            page_ids=page_ids,
            total_pages=3,
            started_at=datetime.now(timezone.utc),
        )

        data = original.model_dump()
        restored = ExtractionBatchStarted(**data)

        assert restored.batch_id == original.batch_id
        assert restored.page_ids == original.page_ids
        assert restored.total_pages == original.total_pages


# =============================================================================
# ExtractionBatchCompleted Tests
# =============================================================================


class TestExtractionBatchCompleted:
    """Tests for ExtractionBatchCompleted event."""

    def test_create_with_all_fields(self):
        """Test creating event with all fields populated."""
        base_kwargs = make_base_event_kwargs()
        batch_id = uuid4()
        completed_at = datetime.now(timezone.utc)

        event = ExtractionBatchCompleted(
            **base_kwargs,
            batch_id=batch_id,
            successful_count=8,
            failed_count=2,
            total_entities=150,
            total_relationships=75,
            duration_ms=60000,
            completed_at=completed_at,
        )

        assert event.event_type == "ExtractionBatchCompleted"
        assert event.aggregate_type == "ExtractionBatch"
        assert event.batch_id == batch_id
        assert event.successful_count == 8
        assert event.failed_count == 2
        assert event.total_entities == 150
        assert event.total_relationships == 75
        assert event.duration_ms == 60000
        assert event.completed_at == completed_at

    def test_all_successful_batch(self):
        """Test batch where all extractions succeeded."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionBatchCompleted(
            **base_kwargs,
            batch_id=uuid4(),
            successful_count=10,
            failed_count=0,
            total_entities=200,
            total_relationships=100,
            duration_ms=30000,
            completed_at=datetime.now(timezone.utc),
        )

        assert event.successful_count == 10
        assert event.failed_count == 0

    def test_all_failed_batch(self):
        """Test batch where all extractions failed."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionBatchCompleted(
            **base_kwargs,
            batch_id=uuid4(),
            successful_count=0,
            failed_count=5,
            total_entities=0,
            total_relationships=0,
            duration_ms=5000,
            completed_at=datetime.now(timezone.utc),
        )

        assert event.successful_count == 0
        assert event.failed_count == 5
        assert event.total_entities == 0
        assert event.total_relationships == 0

    def test_serialization_roundtrip(self):
        """Test event serializes and deserializes correctly."""
        base_kwargs = make_base_event_kwargs()

        original = ExtractionBatchCompleted(
            **base_kwargs,
            batch_id=uuid4(),
            successful_count=7,
            failed_count=3,
            total_entities=100,
            total_relationships=50,
            duration_ms=45000,
            completed_at=datetime.now(timezone.utc),
        )

        data = original.model_dump()
        restored = ExtractionBatchCompleted(**data)

        assert restored.successful_count == original.successful_count
        assert restored.failed_count == original.failed_count
        assert restored.total_entities == original.total_entities
        assert restored.total_relationships == original.total_relationships
        assert restored.duration_ms == original.duration_ms


# =============================================================================
# Cross-Event Tests
# =============================================================================


class TestEventRegistration:
    """Tests for event registration with eventsource registry."""

    def test_all_events_are_registered(self):
        """Test all extraction events are properly registered."""
        from eventsource import is_event_registered, get_event_class

        # Verify all event types are registered
        registered_types = [
            "ExtractionRequested",
            "ExtractionStarted",
            "ExtractionCompleted",
            "ExtractionProcessFailed",
            "ExtractionRetryScheduled",
            "RelationshipDiscovered",
            "ExtractionBatchStarted",
            "ExtractionBatchCompleted",
        ]

        for event_type in registered_types:
            assert is_event_registered(event_type), f"Event {event_type} not registered"
            event_class = get_event_class(event_type)
            assert event_class is not None, f"Event {event_type} class not found"


class TestEventImmutability:
    """Tests for event immutability (frozen models)."""

    def test_events_are_immutable(self):
        """Test that events cannot be modified after creation."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionRequested(
            **base_kwargs,
            page_id=uuid4(),
            page_url="https://example.com",
            content_hash="hash",
            requested_at=datetime.now(timezone.utc),
        )

        with pytest.raises(Exception):  # ValidationError for frozen model
            event.page_url = "https://changed.com"


class TestEventMetadata:
    """Tests for common event metadata fields."""

    def test_event_id_is_auto_generated(self):
        """Test that event_id is automatically generated."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionRequested(
            **base_kwargs,
            page_id=uuid4(),
            page_url="https://example.com",
            content_hash="hash",
            requested_at=datetime.now(timezone.utc),
        )

        assert event.event_id is not None
        assert isinstance(event.event_id, UUID)

    def test_occurred_at_is_auto_set(self):
        """Test that occurred_at is automatically set."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionRequested(
            **base_kwargs,
            page_id=uuid4(),
            page_url="https://example.com",
            content_hash="hash",
            requested_at=datetime.now(timezone.utc),
        )

        assert event.occurred_at is not None
        assert isinstance(event.occurred_at, datetime)

    def test_aggregate_version_defaults_to_one(self):
        """Test that aggregate_version defaults to 1."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionRequested(
            **base_kwargs,
            page_id=uuid4(),
            page_url="https://example.com",
            content_hash="hash",
            requested_at=datetime.now(timezone.utc),
        )

        assert event.aggregate_version == 1

    def test_correlation_id_is_auto_generated(self):
        """Test that correlation_id is automatically generated."""
        base_kwargs = make_base_event_kwargs()

        event = ExtractionRequested(
            **base_kwargs,
            page_id=uuid4(),
            page_url="https://example.com",
            content_hash="hash",
            requested_at=datetime.now(timezone.utc),
        )

        assert event.correlation_id is not None
        assert isinstance(event.correlation_id, UUID)

    def test_with_causation_sets_causation_id(self):
        """Test that with_causation properly sets causation tracking."""
        base_kwargs = make_base_event_kwargs()

        event1 = ExtractionRequested(
            **base_kwargs,
            page_id=uuid4(),
            page_url="https://example.com",
            content_hash="hash1",
            requested_at=datetime.now(timezone.utc),
        )

        event2 = ExtractionStarted(
            **base_kwargs,
            page_id=uuid4(),
            worker_id="worker-1",
            started_at=datetime.now(timezone.utc),
        )

        caused_event = event2.with_causation(event1)

        assert caused_event.causation_id == event1.event_id
        assert caused_event.correlation_id == event1.correlation_id
