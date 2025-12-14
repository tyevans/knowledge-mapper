"""
Unit tests for ExtractionProcess aggregate.

Tests cover the aggregate lifecycle, command methods, event handlers,
state transitions, and invariant enforcement.
"""

from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

from app.eventsourcing.aggregates.extraction import (
    ExtractionProcess,
    ExtractionProcessState,
    ExtractionStatus,
    ExtractedEntityRecord,
    ExtractedRelationshipRecord,
    create_extraction_process_repository,
)
from app.eventsourcing.events.extraction import (
    ExtractionCompleted,
    ExtractionProcessFailed,
    ExtractionRequested,
    ExtractionRetryScheduled,
    ExtractionStarted,
    RelationshipDiscovered,
)
from app.eventsourcing.events.scraping import EntityExtracted


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def aggregate_id():
    """Create a unique aggregate ID for each test."""
    return uuid4()


@pytest.fixture
def tenant_id():
    """Create a unique tenant ID for each test."""
    return uuid4()


@pytest.fixture
def page_id():
    """Create a unique page ID for each test."""
    return uuid4()


@pytest.fixture
def extraction_process(aggregate_id):
    """Create a fresh ExtractionProcess aggregate."""
    return ExtractionProcess(aggregate_id)


@pytest.fixture
def requested_process(extraction_process, tenant_id, page_id):
    """Create an ExtractionProcess in PENDING state."""
    extraction_process.request_extraction(
        page_id=page_id,
        tenant_id=tenant_id,
        page_url="https://docs.example.com/api",
        content_hash="hash123abc",
        config={"model": "llama3.2"},
    )
    return extraction_process


@pytest.fixture
def started_process(requested_process):
    """Create an ExtractionProcess in IN_PROGRESS state."""
    requested_process.start(worker_id="worker-test-1")
    return requested_process


# =============================================================================
# ExtractionProcess Lifecycle Tests
# =============================================================================


class TestExtractionProcessCreation:
    """Tests for ExtractionProcess aggregate creation."""

    def test_create_with_aggregate_id(self, aggregate_id):
        """Test creating aggregate with specific ID."""
        process = ExtractionProcess(aggregate_id)

        assert process.aggregate_id == aggregate_id
        assert process.version == 0
        assert process._state is None

    def test_initial_state_raises_error(self, extraction_process):
        """Test that _get_initial_state raises error before request."""
        with pytest.raises(RuntimeError, match="requires request_extraction"):
            extraction_process._get_initial_state()


class TestRequestExtraction:
    """Tests for request_extraction command method."""

    def test_request_extraction_creates_pending_state(
        self, extraction_process, tenant_id, page_id
    ):
        """Test requesting extraction creates pending state."""
        extraction_process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com/page",
            content_hash="contenthash123",
        )

        assert extraction_process._state is not None
        assert extraction_process._state.status == ExtractionStatus.PENDING
        assert extraction_process._state.page_id == page_id
        assert extraction_process._state.tenant_id == tenant_id
        assert extraction_process._state.page_url == "https://example.com/page"
        assert extraction_process._state.content_hash == "contenthash123"

    def test_request_extraction_sets_extraction_id(
        self, extraction_process, aggregate_id, tenant_id, page_id
    ):
        """Test that extraction_id matches aggregate_id."""
        extraction_process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )

        assert extraction_process._state.extraction_id == aggregate_id

    def test_request_extraction_captures_config(
        self, extraction_process, tenant_id, page_id
    ):
        """Test that extraction config is captured."""
        config = {"model": "codellama", "max_tokens": 4096}

        extraction_process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
            config=config,
        )

        assert extraction_process._state.extraction_config == config

    def test_request_extraction_default_config_empty(
        self, extraction_process, tenant_id, page_id
    ):
        """Test default extraction config is empty dict."""
        extraction_process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )

        assert extraction_process._state.extraction_config == {}

    def test_request_extraction_sets_requested_at(
        self, extraction_process, tenant_id, page_id
    ):
        """Test that requested_at timestamp is set."""
        extraction_process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )

        assert extraction_process._state.requested_at is not None
        assert isinstance(extraction_process._state.requested_at, datetime)

    def test_request_extraction_emits_event(
        self, extraction_process, tenant_id, page_id
    ):
        """Test that ExtractionRequested event is emitted."""
        extraction_process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )

        assert len(extraction_process.uncommitted_events) == 1
        event = extraction_process.uncommitted_events[0]
        assert isinstance(event, ExtractionRequested)
        assert event.page_id == page_id
        assert event.tenant_id == tenant_id

    def test_request_extraction_increments_version(
        self, extraction_process, tenant_id, page_id
    ):
        """Test that version is incremented after request."""
        assert extraction_process.version == 0

        extraction_process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )

        assert extraction_process.version == 1


class TestStartExtraction:
    """Tests for start command method."""

    def test_start_transitions_to_in_progress(self, requested_process):
        """Test starting moves to IN_PROGRESS status."""
        requested_process.start(worker_id="worker-1")

        assert requested_process._state.status == ExtractionStatus.IN_PROGRESS

    def test_start_captures_worker_id(self, requested_process):
        """Test that worker_id is captured."""
        requested_process.start(worker_id="celery-worker-abc123")

        assert requested_process._state.worker_id == "celery-worker-abc123"

    def test_start_sets_started_at(self, requested_process):
        """Test that started_at timestamp is set."""
        requested_process.start(worker_id="worker-1")

        assert requested_process._state.started_at is not None
        assert isinstance(requested_process._state.started_at, datetime)

    def test_start_emits_event(self, requested_process):
        """Test that ExtractionStarted event is emitted."""
        initial_event_count = len(requested_process.uncommitted_events)

        requested_process.start(worker_id="worker-1")

        assert len(requested_process.uncommitted_events) == initial_event_count + 1
        event = requested_process.uncommitted_events[-1]
        assert isinstance(event, ExtractionStarted)
        assert event.worker_id == "worker-1"


class TestRecordEntity:
    """Tests for record_entity command method."""

    def test_record_entity_returns_entity_id(self, started_process):
        """Test that record_entity returns a UUID."""
        entity_id = started_process.record_entity(
            entity_type="FUNCTION",
            name="test_function",
            normalized_name="test_function",
            confidence_score=0.95,
        )

        assert entity_id is not None
        from uuid import UUID
        assert isinstance(entity_id, UUID)

    def test_record_entity_adds_to_state(self, started_process):
        """Test that recorded entity is added to state."""
        assert len(started_process._state.entities) == 0

        started_process.record_entity(
            entity_type="CLASS",
            name="MyClass",
            normalized_name="myclass",
            properties={"methods": ["__init__", "process"]},
            confidence_score=0.9,
            source_text="class MyClass:",
        )

        assert len(started_process._state.entities) == 1
        entity = started_process._state.entities[0]
        assert entity.entity_type == "CLASS"
        assert entity.name == "MyClass"
        assert entity.normalized_name == "myclass"
        assert entity.properties == {"methods": ["__init__", "process"]}
        assert entity.confidence_score == 0.9
        assert entity.source_text == "class MyClass:"

    def test_record_multiple_entities(self, started_process):
        """Test recording multiple entities."""
        started_process.record_entity(
            entity_type="FUNCTION",
            name="func1",
            normalized_name="func1",
            confidence_score=0.9,
        )
        started_process.record_entity(
            entity_type="FUNCTION",
            name="func2",
            normalized_name="func2",
            confidence_score=0.85,
        )
        started_process.record_entity(
            entity_type="CLASS",
            name="MyClass",
            normalized_name="myclass",
            confidence_score=0.95,
        )

        assert len(started_process._state.entities) == 3

    def test_record_entity_emits_event(self, started_process):
        """Test that EntityExtracted event is emitted."""
        initial_event_count = len(started_process.uncommitted_events)

        started_process.record_entity(
            entity_type="FUNCTION",
            name="test_func",
            normalized_name="test_func",
            confidence_score=0.9,
        )

        assert len(started_process.uncommitted_events) == initial_event_count + 1
        event = started_process.uncommitted_events[-1]
        assert isinstance(event, EntityExtracted)
        assert event.name == "test_func"
        assert event.entity_type == "FUNCTION"

    def test_record_entity_default_properties(self, started_process):
        """Test default properties is empty dict."""
        started_process.record_entity(
            entity_type="CONCEPT",
            name="TestConcept",
            normalized_name="testconcept",
            confidence_score=0.8,
        )

        entity = started_process._state.entities[0]
        assert entity.properties == {}

    def test_record_entity_default_confidence(self, started_process):
        """Test default confidence_score is 1.0."""
        started_process.record_entity(
            entity_type="FUNCTION",
            name="func",
            normalized_name="func",
        )

        entity = started_process._state.entities[0]
        assert entity.confidence_score == 1.0


class TestRecordRelationship:
    """Tests for record_relationship command method."""

    def test_record_relationship_returns_relationship_id(self, started_process):
        """Test that record_relationship returns a UUID."""
        relationship_id = started_process.record_relationship(
            source_entity_name="ClassA",
            target_entity_name="ClassB",
            relationship_type="EXTENDS",
            confidence_score=0.95,
        )

        assert relationship_id is not None
        from uuid import UUID
        assert isinstance(relationship_id, UUID)

    def test_record_relationship_adds_to_state(self, started_process):
        """Test that recorded relationship is added to state."""
        assert len(started_process._state.relationships) == 0

        started_process.record_relationship(
            source_entity_name="FunctionA",
            target_entity_name="FunctionB",
            relationship_type="CALLS",
            confidence_score=0.88,
            context="FunctionA calls FunctionB",
        )

        assert len(started_process._state.relationships) == 1
        rel = started_process._state.relationships[0]
        assert rel.source_entity_name == "FunctionA"
        assert rel.target_entity_name == "FunctionB"
        assert rel.relationship_type == "CALLS"
        assert rel.confidence_score == 0.88
        assert rel.context == "FunctionA calls FunctionB"

    def test_record_multiple_relationships(self, started_process):
        """Test recording multiple relationships."""
        started_process.record_relationship(
            source_entity_name="A",
            target_entity_name="B",
            relationship_type="CALLS",
        )
        started_process.record_relationship(
            source_entity_name="B",
            target_entity_name="C",
            relationship_type="EXTENDS",
        )

        assert len(started_process._state.relationships) == 2

    def test_record_relationship_emits_event(self, started_process):
        """Test that RelationshipDiscovered event is emitted."""
        initial_event_count = len(started_process.uncommitted_events)

        started_process.record_relationship(
            source_entity_name="Source",
            target_entity_name="Target",
            relationship_type="USES",
        )

        assert len(started_process.uncommitted_events) == initial_event_count + 1
        event = started_process.uncommitted_events[-1]
        assert isinstance(event, RelationshipDiscovered)
        assert event.source_entity_name == "Source"
        assert event.target_entity_name == "Target"

    def test_record_relationship_default_confidence(self, started_process):
        """Test default confidence_score is 1.0."""
        started_process.record_relationship(
            source_entity_name="A",
            target_entity_name="B",
            relationship_type="RELATES",
        )

        rel = started_process._state.relationships[0]
        assert rel.confidence_score == 1.0

    def test_record_relationship_optional_context(self, started_process):
        """Test context is optional and defaults to None."""
        started_process.record_relationship(
            source_entity_name="A",
            target_entity_name="B",
            relationship_type="RELATES",
        )

        rel = started_process._state.relationships[0]
        assert rel.context is None


class TestCompleteExtraction:
    """Tests for complete command method."""

    def test_complete_transitions_to_completed(self, started_process):
        """Test completing moves to COMPLETED status."""
        started_process.complete(duration_ms=1500, extraction_method="llm_ollama")

        assert started_process._state.status == ExtractionStatus.COMPLETED

    def test_complete_captures_duration(self, started_process):
        """Test that duration_ms is captured."""
        started_process.complete(duration_ms=2500, extraction_method="llm")

        assert started_process._state.duration_ms == 2500

    def test_complete_captures_extraction_method(self, started_process):
        """Test that extraction_method is captured."""
        started_process.complete(duration_ms=1000, extraction_method="hybrid_regex_llm")

        assert started_process._state.extraction_method == "hybrid_regex_llm"

    def test_complete_sets_completed_at(self, started_process):
        """Test that completed_at timestamp is set."""
        started_process.complete(duration_ms=1000, extraction_method="llm")

        assert started_process._state.completed_at is not None
        assert isinstance(started_process._state.completed_at, datetime)

    def test_complete_emits_event(self, started_process):
        """Test that ExtractionCompleted event is emitted."""
        initial_event_count = len(started_process.uncommitted_events)

        started_process.complete(duration_ms=1000, extraction_method="llm")

        assert len(started_process.uncommitted_events) == initial_event_count + 1
        event = started_process.uncommitted_events[-1]
        assert isinstance(event, ExtractionCompleted)
        assert event.duration_ms == 1000
        assert event.extraction_method == "llm"

    def test_complete_includes_entity_count(self, started_process):
        """Test that completed event includes entity count."""
        started_process.record_entity(
            entity_type="FUNCTION",
            name="func1",
            normalized_name="func1",
        )
        started_process.record_entity(
            entity_type="CLASS",
            name="cls1",
            normalized_name="cls1",
        )

        started_process.complete(duration_ms=1000, extraction_method="llm")

        event = started_process.uncommitted_events[-1]
        assert event.entity_count == 2

    def test_complete_includes_relationship_count(self, started_process):
        """Test that completed event includes relationship count."""
        started_process.record_relationship(
            source_entity_name="A",
            target_entity_name="B",
            relationship_type="CALLS",
        )

        started_process.complete(duration_ms=1000, extraction_method="llm")

        event = started_process.uncommitted_events[-1]
        assert event.relationship_count == 1


class TestFailExtraction:
    """Tests for fail command method."""

    def test_fail_transitions_to_failed(self, started_process):
        """Test failing moves to FAILED status."""
        started_process.fail(
            error_message="LLM timeout",
            error_type="TIMEOUT",
        )

        assert started_process._state.status == ExtractionStatus.FAILED

    def test_fail_captures_error_message(self, started_process):
        """Test that error_message is captured."""
        started_process.fail(
            error_message="Connection refused to Ollama server",
            error_type="CONNECTION_ERROR",
        )

        assert started_process._state.error_message == "Connection refused to Ollama server"

    def test_fail_captures_error_type(self, started_process):
        """Test that error_type is captured."""
        started_process.fail(
            error_message="Parse error",
            error_type="PARSE_ERROR",
        )

        assert started_process._state.error_type == "PARSE_ERROR"

    def test_fail_default_retryable_true(self, started_process):
        """Test that retryable defaults to True."""
        started_process.fail(
            error_message="Temporary failure",
            error_type="TEMP_ERROR",
        )

        assert started_process._state.retryable is True

    def test_fail_non_retryable_error(self, started_process):
        """Test marking error as non-retryable."""
        started_process.fail(
            error_message="Invalid content format",
            error_type="INVALID_CONTENT",
            retryable=False,
        )

        assert started_process._state.retryable is False

    def test_fail_sets_failed_at(self, started_process):
        """Test that failed_at timestamp is set."""
        started_process.fail(
            error_message="Error",
            error_type="ERROR",
        )

        assert started_process._state.failed_at is not None
        assert isinstance(started_process._state.failed_at, datetime)

    def test_fail_emits_event(self, started_process):
        """Test that ExtractionProcessFailed event is emitted."""
        initial_event_count = len(started_process.uncommitted_events)

        started_process.fail(
            error_message="Test error",
            error_type="TEST",
        )

        assert len(started_process.uncommitted_events) == initial_event_count + 1
        event = started_process.uncommitted_events[-1]
        assert isinstance(event, ExtractionProcessFailed)
        assert event.error_message == "Test error"
        assert event.error_type == "TEST"


class TestScheduleRetry:
    """Tests for schedule_retry command method."""

    @pytest.fixture
    def failed_process(self, started_process):
        """Create an ExtractionProcess in FAILED state."""
        started_process.fail(
            error_message="Temporary error",
            error_type="TEMP",
            retryable=True,
        )
        return started_process

    def test_schedule_retry_transitions_to_pending(self, failed_process):
        """Test scheduling retry moves back to PENDING status."""
        scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=5)

        failed_process.schedule_retry(
            scheduled_for=scheduled_for,
            backoff_seconds=300.0,
        )

        assert failed_process._state.status == ExtractionStatus.PENDING

    def test_schedule_retry_increments_retry_count(self, failed_process):
        """Test that retry_count is incremented."""
        initial_retry_count = failed_process._state.retry_count

        failed_process.schedule_retry(
            scheduled_for=datetime.now(timezone.utc),
            backoff_seconds=30.0,
        )

        assert failed_process._state.retry_count == initial_retry_count + 1

    def test_schedule_retry_sets_next_retry_at(self, failed_process):
        """Test that next_retry_at is set."""
        scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=10)

        failed_process.schedule_retry(
            scheduled_for=scheduled_for,
            backoff_seconds=600.0,
        )

        assert failed_process._state.next_retry_at == scheduled_for

    def test_schedule_retry_clears_error_state(self, failed_process):
        """Test that error state is cleared on retry."""
        assert failed_process._state.error_message is not None
        assert failed_process._state.error_type is not None
        assert failed_process._state.failed_at is not None

        failed_process.schedule_retry(
            scheduled_for=datetime.now(timezone.utc),
            backoff_seconds=30.0,
        )

        assert failed_process._state.error_message is None
        assert failed_process._state.error_type is None
        assert failed_process._state.failed_at is None

    def test_schedule_retry_emits_event(self, failed_process):
        """Test that ExtractionRetryScheduled event is emitted."""
        initial_event_count = len(failed_process.uncommitted_events)
        scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=5)

        failed_process.schedule_retry(
            scheduled_for=scheduled_for,
            backoff_seconds=300.0,
        )

        assert len(failed_process.uncommitted_events) == initial_event_count + 1
        event = failed_process.uncommitted_events[-1]
        assert isinstance(event, ExtractionRetryScheduled)
        assert event.scheduled_for == scheduled_for
        assert event.backoff_seconds == 300.0


# =============================================================================
# Invariant Tests
# =============================================================================


class TestExtractionProcessInvariants:
    """Tests for aggregate business invariants."""

    def test_cannot_start_without_request(self, extraction_process):
        """Test cannot start extraction without request."""
        with pytest.raises(ValueError, match="Cannot start.*not yet requested"):
            extraction_process.start(worker_id="worker-1")

    def test_cannot_start_completed_extraction(self, started_process):
        """Test cannot start already completed extraction."""
        started_process.complete(duration_ms=1000, extraction_method="llm")

        with pytest.raises(ValueError, match="(?i)Cannot start.*completed"):
            started_process.start(worker_id="worker-2")

    def test_cannot_start_failed_extraction(self, started_process):
        """Test cannot start failed extraction directly."""
        started_process.fail(error_message="Error", error_type="ERROR")

        with pytest.raises(ValueError, match="(?i)Cannot start.*failed"):
            started_process.start(worker_id="worker-2")

    def test_cannot_start_in_progress_extraction(self, started_process):
        """Test cannot start already in-progress extraction."""
        with pytest.raises(ValueError, match="(?i)Cannot start.*in_progress"):
            started_process.start(worker_id="worker-2")

    def test_cannot_request_twice(self, requested_process, tenant_id, page_id):
        """Test cannot request extraction twice."""
        with pytest.raises(ValueError, match="already been requested"):
            requested_process.request_extraction(
                page_id=page_id,
                tenant_id=tenant_id,
                page_url="https://example.com",
                content_hash="hash2",
            )

    def test_cannot_record_entity_before_start(self, requested_process):
        """Test cannot record entity when not in progress."""
        with pytest.raises(ValueError, match="(?i)Cannot record entity.*pending"):
            requested_process.record_entity(
                entity_type="FUNCTION",
                name="test",
                normalized_name="test",
            )

    def test_cannot_record_entity_after_complete(self, started_process):
        """Test cannot record entity after completion."""
        started_process.complete(duration_ms=1000, extraction_method="llm")

        with pytest.raises(ValueError, match="(?i)Cannot record entity.*completed"):
            started_process.record_entity(
                entity_type="FUNCTION",
                name="test",
                normalized_name="test",
            )

    def test_cannot_record_entity_after_fail(self, started_process):
        """Test cannot record entity after failure."""
        started_process.fail(error_message="Error", error_type="ERROR")

        with pytest.raises(ValueError, match="(?i)Cannot record entity.*failed"):
            started_process.record_entity(
                entity_type="FUNCTION",
                name="test",
                normalized_name="test",
            )

    def test_cannot_record_entity_without_request(self, extraction_process):
        """Test cannot record entity without request."""
        with pytest.raises(ValueError, match="not yet requested"):
            extraction_process.record_entity(
                entity_type="FUNCTION",
                name="test",
                normalized_name="test",
            )

    def test_cannot_record_relationship_before_start(self, requested_process):
        """Test cannot record relationship when not in progress."""
        with pytest.raises(ValueError, match="(?i)Cannot record relationship.*pending"):
            requested_process.record_relationship(
                source_entity_name="A",
                target_entity_name="B",
                relationship_type="CALLS",
            )

    def test_cannot_record_relationship_after_complete(self, started_process):
        """Test cannot record relationship after completion."""
        started_process.complete(duration_ms=1000, extraction_method="llm")

        with pytest.raises(ValueError, match="(?i)Cannot record relationship.*completed"):
            started_process.record_relationship(
                source_entity_name="A",
                target_entity_name="B",
                relationship_type="CALLS",
            )

    def test_cannot_complete_before_start(self, requested_process):
        """Test cannot complete when not in progress."""
        with pytest.raises(ValueError, match="(?i)Cannot complete.*pending"):
            requested_process.complete(duration_ms=1000, extraction_method="llm")

    def test_cannot_complete_without_request(self, extraction_process):
        """Test cannot complete without request."""
        with pytest.raises(ValueError, match="not yet requested"):
            extraction_process.complete(duration_ms=1000, extraction_method="llm")

    def test_cannot_fail_before_start(self, requested_process):
        """Test cannot fail when not in progress."""
        with pytest.raises(ValueError, match="(?i)Cannot fail.*pending"):
            requested_process.fail(error_message="Error", error_type="ERROR")

    def test_cannot_fail_without_request(self, extraction_process):
        """Test cannot fail without request."""
        with pytest.raises(ValueError, match="not yet requested"):
            extraction_process.fail(error_message="Error", error_type="ERROR")

    def test_cannot_retry_pending_extraction(self, requested_process):
        """Test cannot schedule retry for pending extraction."""
        with pytest.raises(ValueError, match="(?i)Cannot schedule retry.*pending"):
            requested_process.schedule_retry(
                scheduled_for=datetime.now(timezone.utc),
                backoff_seconds=30.0,
            )

    def test_cannot_retry_in_progress_extraction(self, started_process):
        """Test cannot schedule retry for in-progress extraction."""
        with pytest.raises(ValueError, match="(?i)Cannot schedule retry.*in_progress"):
            started_process.schedule_retry(
                scheduled_for=datetime.now(timezone.utc),
                backoff_seconds=30.0,
            )

    def test_cannot_retry_completed_extraction(self, started_process):
        """Test cannot schedule retry for completed extraction."""
        started_process.complete(duration_ms=1000, extraction_method="llm")

        with pytest.raises(ValueError, match="(?i)Cannot schedule retry.*completed"):
            started_process.schedule_retry(
                scheduled_for=datetime.now(timezone.utc),
                backoff_seconds=30.0,
            )

    def test_cannot_retry_non_retryable_failure(self, started_process):
        """Test cannot retry non-retryable failure."""
        started_process.fail(
            error_message="Permanent error",
            error_type="PERMANENT",
            retryable=False,
        )

        with pytest.raises(ValueError, match="non-retryable"):
            started_process.schedule_retry(
                scheduled_for=datetime.now(timezone.utc),
                backoff_seconds=30.0,
            )

    def test_cannot_retry_without_request(self, extraction_process):
        """Test cannot retry without request."""
        with pytest.raises(ValueError, match="not yet requested"):
            extraction_process.schedule_retry(
                scheduled_for=datetime.now(timezone.utc),
                backoff_seconds=30.0,
            )


# =============================================================================
# Event Handler Tests
# =============================================================================


class TestEventHandlers:
    """Tests for @handles decorators and state application."""

    def test_extraction_requested_handler_initializes_state(
        self, extraction_process, tenant_id, page_id
    ):
        """Test ExtractionRequested handler initializes state correctly."""
        extraction_process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash123",
            config={"model": "llama3.2"},
        )

        state = extraction_process._state
        assert isinstance(state, ExtractionProcessState)
        assert state.status == ExtractionStatus.PENDING
        assert state.entities == []
        assert state.relationships == []
        assert state.worker_id is None
        assert state.started_at is None
        assert state.completed_at is None
        assert state.failed_at is None

    def test_extraction_started_handler_updates_state(self, requested_process):
        """Test ExtractionStarted handler updates state correctly."""
        requested_process.start(worker_id="worker-abc")

        state = requested_process._state
        assert state.status == ExtractionStatus.IN_PROGRESS
        assert state.worker_id == "worker-abc"
        assert state.started_at is not None

    def test_entity_extracted_handler_adds_entity(self, started_process):
        """Test EntityExtracted handler adds entity to state."""
        started_process.record_entity(
            entity_type="FUNCTION",
            name="my_func",
            normalized_name="my_func",
            properties={"params": ["x", "y"]},
            confidence_score=0.85,
            source_text="def my_func(x, y):",
        )

        entities = started_process._state.entities
        assert len(entities) == 1
        assert isinstance(entities[0], ExtractedEntityRecord)
        assert entities[0].name == "my_func"

    def test_relationship_discovered_handler_adds_relationship(self, started_process):
        """Test RelationshipDiscovered handler adds relationship to state."""
        started_process.record_relationship(
            source_entity_name="ClassA",
            target_entity_name="ClassB",
            relationship_type="EXTENDS",
            confidence_score=0.9,
            context="class ClassA(ClassB):",
        )

        relationships = started_process._state.relationships
        assert len(relationships) == 1
        assert isinstance(relationships[0], ExtractedRelationshipRecord)
        assert relationships[0].source_entity_name == "ClassA"

    def test_extraction_completed_handler_finalizes_state(self, started_process):
        """Test ExtractionCompleted handler finalizes state."""
        started_process.complete(duration_ms=2500, extraction_method="llm_ollama")

        state = started_process._state
        assert state.status == ExtractionStatus.COMPLETED
        assert state.duration_ms == 2500
        assert state.extraction_method == "llm_ollama"
        assert state.completed_at is not None

    def test_extraction_failed_handler_captures_error(self, started_process):
        """Test ExtractionProcessFailed handler captures error details."""
        started_process.fail(
            error_message="Connection timeout",
            error_type="TIMEOUT",
            retryable=True,
        )

        state = started_process._state
        assert state.status == ExtractionStatus.FAILED
        assert state.error_message == "Connection timeout"
        assert state.error_type == "TIMEOUT"
        assert state.retryable is True
        assert state.failed_at is not None

    def test_retry_scheduled_handler_resets_state(self, started_process):
        """Test ExtractionRetryScheduled handler resets state for retry."""
        started_process.fail(
            error_message="Error",
            error_type="ERROR",
            retryable=True,
        )

        scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=5)
        started_process.schedule_retry(
            scheduled_for=scheduled_for,
            backoff_seconds=300.0,
        )

        state = started_process._state
        assert state.status == ExtractionStatus.PENDING
        assert state.retry_count == 1
        assert state.next_retry_at == scheduled_for
        assert state.error_message is None
        assert state.error_type is None
        assert state.failed_at is None


# =============================================================================
# Full Lifecycle Tests
# =============================================================================


class TestExtractionProcessFullLifecycle:
    """Tests for complete extraction process lifecycles."""

    def test_successful_extraction_lifecycle(self, aggregate_id, tenant_id, page_id):
        """Test complete successful extraction lifecycle."""
        process = ExtractionProcess(aggregate_id)

        # Request
        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://docs.python.org/api",
            content_hash="python_docs_hash",
            config={"model": "codellama"},
        )
        assert process._state.status == ExtractionStatus.PENDING

        # Start
        process.start(worker_id="extraction-worker-1")
        assert process._state.status == ExtractionStatus.IN_PROGRESS

        # Record entities
        process.record_entity(
            entity_type="FUNCTION",
            name="asyncio.run",
            normalized_name="asyncio_run",
            properties={"module": "asyncio"},
            confidence_score=0.95,
        )
        process.record_entity(
            entity_type="CLASS",
            name="asyncio.Task",
            normalized_name="asyncio_task",
            properties={"module": "asyncio"},
            confidence_score=0.92,
        )

        # Record relationships
        process.record_relationship(
            source_entity_name="asyncio.run",
            target_entity_name="asyncio.Task",
            relationship_type="CREATES",
            confidence_score=0.88,
        )

        # Complete
        process.complete(duration_ms=3500, extraction_method="llm_codellama")
        assert process._state.status == ExtractionStatus.COMPLETED
        assert len(process._state.entities) == 2
        assert len(process._state.relationships) == 1

        # Verify all events emitted
        assert len(process.uncommitted_events) == 6  # request, start, 2 entities, 1 rel, complete

    def test_failed_and_retry_lifecycle(self, aggregate_id, tenant_id, page_id):
        """Test extraction with failure and retry lifecycle."""
        process = ExtractionProcess(aggregate_id)

        # Request and start
        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )
        process.start(worker_id="worker-1")

        # First failure
        process.fail(
            error_message="LLM timeout after 30s",
            error_type="TIMEOUT",
            retryable=True,
        )
        assert process._state.status == ExtractionStatus.FAILED
        assert process._state.retry_count == 0

        # Schedule retry
        retry_time = datetime.now(timezone.utc) + timedelta(minutes=1)
        process.schedule_retry(scheduled_for=retry_time, backoff_seconds=60.0)
        assert process._state.status == ExtractionStatus.PENDING
        assert process._state.retry_count == 1

        # Retry - start again
        process.start(worker_id="worker-2")
        assert process._state.status == ExtractionStatus.IN_PROGRESS

        # Complete on retry
        process.complete(duration_ms=2000, extraction_method="llm")
        assert process._state.status == ExtractionStatus.COMPLETED
        assert process._state.retry_count == 1

    def test_multiple_retries_lifecycle(self, aggregate_id, tenant_id, page_id):
        """Test extraction with multiple retries."""
        process = ExtractionProcess(aggregate_id)

        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )

        # First attempt - fail
        process.start(worker_id="worker-1")
        process.fail(error_message="Error 1", error_type="ERROR", retryable=True)
        process.schedule_retry(
            scheduled_for=datetime.now(timezone.utc),
            backoff_seconds=30.0,
        )
        assert process._state.retry_count == 1

        # Second attempt - fail
        process.start(worker_id="worker-2")
        process.fail(error_message="Error 2", error_type="ERROR", retryable=True)
        process.schedule_retry(
            scheduled_for=datetime.now(timezone.utc),
            backoff_seconds=60.0,
        )
        assert process._state.retry_count == 2

        # Third attempt - success
        process.start(worker_id="worker-3")
        process.complete(duration_ms=1000, extraction_method="llm")
        assert process._state.status == ExtractionStatus.COMPLETED
        assert process._state.retry_count == 2

    def test_permanent_failure_lifecycle(self, aggregate_id, tenant_id, page_id):
        """Test extraction with permanent (non-retryable) failure."""
        process = ExtractionProcess(aggregate_id)

        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )
        process.start(worker_id="worker-1")

        # Permanent failure
        process.fail(
            error_message="Invalid content - cannot be processed",
            error_type="INVALID_CONTENT",
            retryable=False,
        )

        assert process._state.status == ExtractionStatus.FAILED
        assert process._state.retryable is False

        # Verify cannot retry
        with pytest.raises(ValueError, match="non-retryable"):
            process.schedule_retry(
                scheduled_for=datetime.now(timezone.utc),
                backoff_seconds=30.0,
            )


# =============================================================================
# Repository Factory Tests
# =============================================================================


class TestExtractionProcessRepository:
    """Tests for create_extraction_process_repository factory."""

    def test_create_repository(self):
        """Test repository factory creates valid repository."""
        from eventsource import InMemoryEventStore

        event_store = InMemoryEventStore()
        repo = create_extraction_process_repository(event_store)

        assert repo is not None
        assert repo.aggregate_type == "ExtractionProcess"

    def test_repository_creates_new_aggregate(self):
        """Test repository can create new aggregates."""
        from eventsource import InMemoryEventStore

        event_store = InMemoryEventStore()
        repo = create_extraction_process_repository(event_store)

        aggregate_id = uuid4()
        process = repo.create_new(aggregate_id)

        assert process is not None
        assert process.aggregate_id == aggregate_id
        assert isinstance(process, ExtractionProcess)


# =============================================================================
# State Model Tests
# =============================================================================


class TestExtractionProcessState:
    """Tests for ExtractionProcessState model."""

    def test_state_model_fields(self):
        """Test state model has all required fields."""
        state = ExtractionProcessState(
            extraction_id=uuid4(),
            tenant_id=uuid4(),
            page_id=uuid4(),
            page_url="https://example.com",
            content_hash="hash",
            requested_at=datetime.now(timezone.utc),
        )

        assert state.status == ExtractionStatus.PENDING
        assert state.entities == []
        assert state.relationships == []
        assert state.worker_id is None
        assert state.started_at is None
        assert state.completed_at is None
        assert state.failed_at is None
        assert state.duration_ms is None
        assert state.extraction_method is None
        assert state.error_message is None
        assert state.error_type is None
        assert state.retryable is True
        assert state.retry_count == 0
        assert state.next_retry_at is None


class TestExtractedEntityRecord:
    """Tests for ExtractedEntityRecord model."""

    def test_entity_record_fields(self):
        """Test entity record has all required fields."""
        entity_id = uuid4()
        record = ExtractedEntityRecord(
            entity_id=entity_id,
            entity_type="FUNCTION",
            name="test_func",
            normalized_name="test_func",
            confidence_score=0.95,
        )

        assert record.entity_id == entity_id
        assert record.entity_type == "FUNCTION"
        assert record.name == "test_func"
        assert record.normalized_name == "test_func"
        assert record.confidence_score == 0.95
        assert record.properties == {}
        assert record.source_text is None


class TestExtractedRelationshipRecord:
    """Tests for ExtractedRelationshipRecord model."""

    def test_relationship_record_fields(self):
        """Test relationship record has all required fields."""
        relationship_id = uuid4()
        record = ExtractedRelationshipRecord(
            relationship_id=relationship_id,
            source_entity_name="ClassA",
            target_entity_name="ClassB",
            relationship_type="EXTENDS",
            confidence_score=0.9,
        )

        assert record.relationship_id == relationship_id
        assert record.source_entity_name == "ClassA"
        assert record.target_entity_name == "ClassB"
        assert record.relationship_type == "EXTENDS"
        assert record.confidence_score == 0.9
        assert record.context is None


class TestExtractionStatus:
    """Tests for ExtractionStatus enum."""

    def test_all_status_values(self):
        """Test all expected status values exist."""
        assert ExtractionStatus.PENDING == "pending"
        assert ExtractionStatus.IN_PROGRESS == "in_progress"
        assert ExtractionStatus.COMPLETED == "completed"
        assert ExtractionStatus.FAILED == "failed"
        assert ExtractionStatus.CANCELLED == "cancelled"

    def test_status_is_string_enum(self):
        """Test that status values are strings."""
        assert isinstance(ExtractionStatus.PENDING.value, str)
        assert ExtractionStatus.PENDING.value == "pending"
