"""
Integration tests for aggregate repository operations.

Tests saving and loading aggregates through the repository abstraction
against real PostgreSQL database.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.eventsourcing.aggregates.extraction import (
    ExtractionProcess,
    ExtractionStatus,
    create_extraction_process_repository,
)
from app.eventsourcing.stores.factory import get_event_store


@pytest.mark.integration
@pytest.mark.asyncio
class TestAggregateRepositorySaveAndLoad:
    """Tests for saving and loading aggregates via repository."""

    async def test_save_and_load_new_aggregate(self):
        """Test saving and loading a newly created aggregate."""
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        process_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        # Create new aggregate
        process = repo.create_new(process_id)
        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://docs.example.com/api",
            content_hash="hash123abc",
            config={"model": "llama3.2"},
        )

        # Save aggregate
        await repo.save(process)

        # Load aggregate
        loaded = await repo.load(process_id)

        assert loaded is not None
        assert loaded.aggregate_id == process_id
        assert loaded._state is not None
        assert loaded._state.page_id == page_id
        assert loaded._state.tenant_id == tenant_id
        assert loaded._state.status == ExtractionStatus.PENDING
        assert loaded._state.page_url == "https://docs.example.com/api"

    async def test_save_aggregate_with_multiple_events(self):
        """Test saving an aggregate that has emitted multiple events."""
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        process_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        # Create and progress aggregate through multiple states
        process = repo.create_new(process_id)
        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com/page",
            content_hash="contenthash",
        )
        process.start(worker_id="worker-integration-1")

        # Record some entities
        process.record_entity(
            entity_type="FUNCTION",
            name="process_data",
            normalized_name="process_data",
            properties={"signature": "def process_data(x: int) -> str"},
            confidence_score=0.95,
        )
        process.record_entity(
            entity_type="CLASS",
            name="DataProcessor",
            normalized_name="dataprocessor",
            properties={"methods": ["__init__", "process"]},
            confidence_score=0.92,
        )

        # Record relationship
        process.record_relationship(
            source_entity_name="DataProcessor",
            target_entity_name="process_data",
            relationship_type="CALLS",
            confidence_score=0.88,
        )

        # Save aggregate
        await repo.save(process)

        # Load and verify
        loaded = await repo.load(process_id)

        assert loaded.version == 5  # request + start + 2 entities + 1 relationship
        assert loaded._state.status == ExtractionStatus.IN_PROGRESS
        assert len(loaded._state.entities) == 2
        assert len(loaded._state.relationships) == 1

    async def test_load_aggregate_rebuilds_state_from_events(self):
        """Test that aggregate state is fully rebuilt from events on load."""
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        process_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        # Create aggregate with complete lifecycle
        process = repo.create_new(process_id)
        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://docs.python.org/api",
            content_hash="pythondocshash",
            config={"model": "codellama"},
        )
        process.start(worker_id="extraction-worker-1")

        # Record entities
        entity_id_1 = process.record_entity(
            entity_type="FUNCTION",
            name="asyncio.run",
            normalized_name="asyncio_run",
            properties={"module": "asyncio", "params": ["coro"]},
            confidence_score=0.96,
            source_text="asyncio.run(main())",
        )
        entity_id_2 = process.record_entity(
            entity_type="CLASS",
            name="asyncio.Task",
            normalized_name="asyncio_task",
            properties={"module": "asyncio"},
            confidence_score=0.94,
        )

        # Complete extraction
        process.complete(duration_ms=2500, extraction_method="llm_ollama")

        await repo.save(process)

        # Load fresh from store
        loaded = await repo.load(process_id)

        # Verify full state reconstruction
        assert loaded._state.extraction_id == process_id
        assert loaded._state.tenant_id == tenant_id
        assert loaded._state.page_id == page_id
        assert loaded._state.page_url == "https://docs.python.org/api"
        assert loaded._state.status == ExtractionStatus.COMPLETED
        assert loaded._state.worker_id == "extraction-worker-1"
        assert loaded._state.duration_ms == 2500
        assert loaded._state.extraction_method == "llm_ollama"

        # Verify entities were reconstructed
        assert len(loaded._state.entities) == 2
        entity_names = {e.name for e in loaded._state.entities}
        assert "asyncio.run" in entity_names
        assert "asyncio.Task" in entity_names


@pytest.mark.integration
@pytest.mark.asyncio
class TestAggregateRepositoryVersionTracking:
    """Tests for version tracking across save/load cycles."""

    async def test_version_increments_correctly(self):
        """Test that version increments correctly with each event."""
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        process_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        # Create aggregate
        process = repo.create_new(process_id)
        assert process.version == 0

        # Request extraction (v1)
        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )
        assert process.version == 1

        # Start (v2)
        process.start(worker_id="worker-1")
        assert process.version == 2

        # Save and reload
        await repo.save(process)

        loaded = await repo.load(process_id)
        assert loaded.version == 2

    async def test_version_persists_across_save_load_cycles(self):
        """Test that version is correctly persisted and loaded."""
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        process_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        # First save
        process = repo.create_new(process_id)
        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )
        await repo.save(process)

        # Load and continue
        loaded = await repo.load(process_id)
        assert loaded.version == 1

        loaded.start(worker_id="worker-1")
        await repo.save(loaded)

        # Load again
        loaded_2 = await repo.load(process_id)
        assert loaded_2.version == 2

        loaded_2.complete(duration_ms=1000, extraction_method="llm")
        await repo.save(loaded_2)

        # Final load
        final = await repo.load(process_id)
        assert final.version == 3

    async def test_uncommitted_events_cleared_after_save(self):
        """Test that uncommitted events are cleared after successful save."""
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        process_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        process = repo.create_new(process_id)
        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )
        process.start(worker_id="worker-1")

        # Verify uncommitted events exist before save
        assert len(process.uncommitted_events) == 2

        await repo.save(process)

        # Verify uncommitted events cleared after save
        assert len(process.uncommitted_events) == 0


@pytest.mark.integration
@pytest.mark.asyncio
class TestAggregateRepositoryExistence:
    """Tests for aggregate existence checks."""

    async def test_exists_returns_true_for_existing_aggregate(self):
        """Test exists() returns True for saved aggregate."""
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        process_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        process = repo.create_new(process_id)
        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )
        await repo.save(process)

        exists = await repo.exists(process_id)
        assert exists is True

    async def test_exists_returns_false_for_nonexistent_aggregate(self):
        """Test exists() returns False for nonexistent aggregate."""
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        nonexistent_id = uuid4()

        exists = await repo.exists(nonexistent_id)
        assert exists is False

    async def test_load_nonexistent_aggregate_raises_error(self):
        """Test that loading nonexistent aggregate raises AggregateNotFoundError."""
        from eventsource.exceptions import AggregateNotFoundError

        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        nonexistent_id = uuid4()

        with pytest.raises(AggregateNotFoundError):
            await repo.load(nonexistent_id)

    async def test_load_or_create_returns_new_for_nonexistent(self):
        """Test load_or_create returns new aggregate if not found."""
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        new_id = uuid4()

        process = await repo.load_or_create(new_id)

        assert process is not None
        assert process.aggregate_id == new_id
        assert process.version == 0
        assert process._state is None  # No state until first event

    async def test_load_or_create_returns_existing_for_saved(self):
        """Test load_or_create returns existing aggregate if found."""
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        process_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        # Create and save
        process = repo.create_new(process_id)
        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )
        await repo.save(process)

        # Load or create
        loaded = await repo.load_or_create(process_id)

        assert loaded.aggregate_id == process_id
        assert loaded.version == 1
        assert loaded._state is not None
        assert loaded._state.page_url == "https://example.com"


@pytest.mark.integration
@pytest.mark.asyncio
class TestAggregateRepositoryFullLifecycle:
    """Tests for complete aggregate lifecycles."""

    async def test_successful_extraction_lifecycle(self):
        """Test complete successful extraction lifecycle through repository."""
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        process_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        # Phase 1: Request
        process = repo.create_new(process_id)
        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://docs.python.org/api",
            content_hash="python_docs_hash",
            config={"model": "codellama"},
        )
        await repo.save(process)

        # Phase 2: Start (simulating worker pickup)
        loaded = await repo.load(process_id)
        loaded.start(worker_id="celery-worker-123")
        await repo.save(loaded)

        # Phase 3: Extract entities (simulating LLM extraction)
        worker_process = await repo.load(process_id)
        worker_process.record_entity(
            entity_type="FUNCTION",
            name="main",
            normalized_name="main",
            properties={"async": True},
            confidence_score=0.97,
        )
        worker_process.record_entity(
            entity_type="CLASS",
            name="Application",
            normalized_name="application",
            properties={"base_class": "BaseApp"},
            confidence_score=0.95,
        )
        worker_process.record_relationship(
            source_entity_name="Application",
            target_entity_name="main",
            relationship_type="DEFINES",
            confidence_score=0.93,
        )
        await repo.save(worker_process)

        # Phase 4: Complete
        completing_process = await repo.load(process_id)
        completing_process.complete(duration_ms=3500, extraction_method="llm_codellama")
        await repo.save(completing_process)

        # Verify final state
        final = await repo.load(process_id)
        assert final._state.status == ExtractionStatus.COMPLETED
        assert len(final._state.entities) == 2
        assert len(final._state.relationships) == 1
        assert final._state.duration_ms == 3500
        assert final.version == 6  # request + start + 2 entities + 1 rel + complete

    async def test_failed_and_retry_lifecycle(self):
        """Test extraction with failure and retry through repository."""
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        process_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        # Request and start
        process = repo.create_new(process_id)
        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )
        process.start(worker_id="worker-1")
        await repo.save(process)

        # First failure
        loaded = await repo.load(process_id)
        loaded.fail(
            error_message="LLM timeout after 30s",
            error_type="TIMEOUT",
            retryable=True,
        )
        await repo.save(loaded)

        # Schedule retry
        failed_process = await repo.load(process_id)
        assert failed_process._state.status == ExtractionStatus.FAILED

        retry_time = datetime.now(timezone.utc) + timedelta(minutes=1)
        failed_process.schedule_retry(scheduled_for=retry_time, backoff_seconds=60.0)
        await repo.save(failed_process)

        # Verify retry scheduled
        retry_scheduled = await repo.load(process_id)
        assert retry_scheduled._state.status == ExtractionStatus.PENDING
        assert retry_scheduled._state.retry_count == 1

        # Second attempt succeeds
        retry_scheduled.start(worker_id="worker-2")
        retry_scheduled.complete(duration_ms=2000, extraction_method="llm")
        await repo.save(retry_scheduled)

        # Verify final state
        final = await repo.load(process_id)
        assert final._state.status == ExtractionStatus.COMPLETED
        assert final._state.retry_count == 1

    async def test_get_version_returns_correct_value(self):
        """Test get_version returns correct aggregate version."""
        event_store = await get_event_store()
        repo = create_extraction_process_repository(event_store)

        process_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        # Initially no version
        version_before = await repo.get_version(process_id)
        assert version_before == 0

        # After first save
        process = repo.create_new(process_id)
        process.request_extraction(
            page_id=page_id,
            tenant_id=tenant_id,
            page_url="https://example.com",
            content_hash="hash",
        )
        await repo.save(process)

        version_after = await repo.get_version(process_id)
        assert version_after == 1
