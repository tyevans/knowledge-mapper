"""
Integration tests for event store operations.

Tests event store append and retrieval against real PostgreSQL database.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.eventsourcing.events.extraction import (
    ExtractionCompleted,
    ExtractionRequested,
    ExtractionStarted,
)
from app.eventsourcing.stores.factory import get_event_store


@pytest.mark.integration
@pytest.mark.asyncio
class TestEventStoreAppendAndRetrieve:
    """Tests for appending and retrieving events from the event store."""

    async def test_append_and_retrieve_single_event(self):
        """Test appending and retrieving a single event."""
        event_store = await get_event_store()
        aggregate_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        event = ExtractionRequested(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=tenant_id,
            page_id=page_id,
            page_url="https://docs.example.com/api",
            content_hash="hash123abc",
            extraction_config={"model": "llama3.2"},
            requested_at=datetime.now(timezone.utc),
        )

        # Append the event
        result = await event_store.append_events(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            events=[event],
            expected_version=0,
        )

        assert result.success is True
        assert result.new_version == 1

        # Retrieve the events
        stream = await event_store.get_events(aggregate_id, "ExtractionProcess")

        assert len(stream.events) == 1
        assert stream.version == 1
        retrieved_event = stream.events[0]
        assert retrieved_event.aggregate_id == aggregate_id
        assert retrieved_event.page_url == "https://docs.example.com/api"
        assert retrieved_event.tenant_id == tenant_id

    async def test_append_multiple_events_in_sequence(self):
        """Test appending multiple events in sequence."""
        event_store = await get_event_store()
        aggregate_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        # First event - ExtractionRequested
        event1 = ExtractionRequested(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=tenant_id,
            page_id=page_id,
            page_url="https://example.com/page",
            content_hash="hash123",
            extraction_config={},
            requested_at=datetime.now(timezone.utc),
        )

        result1 = await event_store.append_events(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            events=[event1],
            expected_version=0,
        )
        assert result1.success is True

        # Second event - ExtractionStarted
        event2 = ExtractionStarted(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=2,
            tenant_id=tenant_id,
            page_id=page_id,
            worker_id="worker-1",
            started_at=datetime.now(timezone.utc),
        )

        result2 = await event_store.append_events(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            events=[event2],
            expected_version=1,
        )
        assert result2.success is True

        # Third event - ExtractionCompleted
        event3 = ExtractionCompleted(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=3,
            tenant_id=tenant_id,
            page_id=page_id,
            entity_count=5,
            relationship_count=3,
            duration_ms=1500,
            extraction_method="llm_ollama",
            completed_at=datetime.now(timezone.utc),
        )

        result3 = await event_store.append_events(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            events=[event3],
            expected_version=2,
        )
        assert result3.success is True

        # Retrieve all events
        stream = await event_store.get_events(aggregate_id, "ExtractionProcess")

        assert len(stream.events) == 3
        assert stream.version == 3
        assert stream.events[0].event_type == "ExtractionRequested"
        assert stream.events[1].event_type == "ExtractionStarted"
        assert stream.events[2].event_type == "ExtractionCompleted"

    async def test_append_batch_of_events(self):
        """Test appending multiple events in a single batch."""
        event_store = await get_event_store()
        aggregate_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        events = [
            ExtractionRequested(
                aggregate_id=aggregate_id,
                aggregate_type="ExtractionProcess",
                aggregate_version=1,
                tenant_id=tenant_id,
                page_id=page_id,
                page_url="https://example.com",
                content_hash="hash",
                extraction_config={},
                requested_at=datetime.now(timezone.utc),
            ),
            ExtractionStarted(
                aggregate_id=aggregate_id,
                aggregate_type="ExtractionProcess",
                aggregate_version=2,
                tenant_id=tenant_id,
                page_id=page_id,
                worker_id="worker-batch-1",
                started_at=datetime.now(timezone.utc),
            ),
            ExtractionCompleted(
                aggregate_id=aggregate_id,
                aggregate_type="ExtractionProcess",
                aggregate_version=3,
                tenant_id=tenant_id,
                page_id=page_id,
                entity_count=10,
                relationship_count=5,
                duration_ms=2000,
                extraction_method="llm_ollama",
                completed_at=datetime.now(timezone.utc),
            ),
        ]

        # Append all events in one batch
        result = await event_store.append_events(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            events=events,
            expected_version=0,
        )

        assert result.success is True
        assert result.new_version == 3

        # Verify retrieval
        stream = await event_store.get_events(aggregate_id, "ExtractionProcess")
        assert len(stream.events) == 3


@pytest.mark.integration
@pytest.mark.asyncio
class TestEventStoreOrdering:
    """Tests for event ordering and versioning."""

    async def test_events_ordered_by_version(self):
        """Test events are returned in version order."""
        event_store = await get_event_store()
        aggregate_id = uuid4()
        tenant_id = uuid4()

        # Append 5 events one at a time
        for i in range(5):
            event = ExtractionRequested(
                aggregate_id=aggregate_id,
                aggregate_type="ExtractionProcess",
                aggregate_version=i + 1,
                tenant_id=tenant_id,
                page_id=uuid4(),
                page_url=f"https://example.com/page{i}",
                content_hash=f"hash{i}",
                extraction_config={"index": i},
                requested_at=datetime.now(timezone.utc),
            )
            await event_store.append_events(
                aggregate_id=aggregate_id,
                aggregate_type="ExtractionProcess",
                events=[event],
                expected_version=i,
            )

        stream = await event_store.get_events(aggregate_id, "ExtractionProcess")

        assert len(stream.events) == 5
        assert stream.version == 5

        # Verify ordering by version
        for i, event in enumerate(stream.events):
            assert event.aggregate_version == i + 1
            assert event.page_url == f"https://example.com/page{i}"

    async def test_stream_version_matches_event_count(self):
        """Test that stream version matches number of events."""
        event_store = await get_event_store()
        aggregate_id = uuid4()
        tenant_id = uuid4()

        # Append 3 events
        for i in range(3):
            event = ExtractionRequested(
                aggregate_id=aggregate_id,
                aggregate_type="ExtractionProcess",
                aggregate_version=i + 1,
                tenant_id=tenant_id,
                page_id=uuid4(),
                page_url=f"https://example.com/{i}",
                content_hash=f"hash{i}",
                extraction_config={},
                requested_at=datetime.now(timezone.utc),
            )
            await event_store.append_events(
                aggregate_id=aggregate_id,
                aggregate_type="ExtractionProcess",
                events=[event],
                expected_version=i,
            )

        stream = await event_store.get_events(aggregate_id, "ExtractionProcess")

        assert stream.version == len(stream.events)
        assert stream.version == 3


@pytest.mark.integration
@pytest.mark.asyncio
class TestEventStoreIsolation:
    """Tests for stream isolation between different aggregates."""

    async def test_stream_isolation_by_aggregate_id(self):
        """Test that different aggregate IDs have separate event streams."""
        event_store = await get_event_store()
        tenant_id = uuid4()

        # Create events for first aggregate
        aggregate_id_1 = uuid4()
        event_1 = ExtractionRequested(
            aggregate_id=aggregate_id_1,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=tenant_id,
            page_id=uuid4(),
            page_url="https://example.com/aggregate-1",
            content_hash="hash1",
            extraction_config={},
            requested_at=datetime.now(timezone.utc),
        )
        await event_store.append_events(
            aggregate_id=aggregate_id_1,
            aggregate_type="ExtractionProcess",
            events=[event_1],
            expected_version=0,
        )

        # Create events for second aggregate
        aggregate_id_2 = uuid4()
        event_2 = ExtractionRequested(
            aggregate_id=aggregate_id_2,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=tenant_id,
            page_id=uuid4(),
            page_url="https://example.com/aggregate-2",
            content_hash="hash2",
            extraction_config={},
            requested_at=datetime.now(timezone.utc),
        )
        await event_store.append_events(
            aggregate_id=aggregate_id_2,
            aggregate_type="ExtractionProcess",
            events=[event_2],
            expected_version=0,
        )

        # Verify streams are isolated
        stream_1 = await event_store.get_events(aggregate_id_1, "ExtractionProcess")
        stream_2 = await event_store.get_events(aggregate_id_2, "ExtractionProcess")

        assert len(stream_1.events) == 1
        assert len(stream_2.events) == 1

        assert stream_1.events[0].page_url == "https://example.com/aggregate-1"
        assert stream_2.events[0].page_url == "https://example.com/aggregate-2"

        assert stream_1.aggregate_id == aggregate_id_1
        assert stream_2.aggregate_id == aggregate_id_2

    async def test_stream_isolation_by_tenant(self):
        """Test that different tenants have isolated events with same aggregate type."""
        event_store = await get_event_store()

        tenant_id_1 = uuid4()
        tenant_id_2 = uuid4()

        # Create aggregate for tenant 1
        aggregate_id_1 = uuid4()
        event_1 = ExtractionRequested(
            aggregate_id=aggregate_id_1,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=tenant_id_1,
            page_id=uuid4(),
            page_url="https://tenant1.example.com",
            content_hash="tenant1hash",
            extraction_config={},
            requested_at=datetime.now(timezone.utc),
        )
        await event_store.append_events(
            aggregate_id=aggregate_id_1,
            aggregate_type="ExtractionProcess",
            events=[event_1],
            expected_version=0,
        )

        # Create aggregate for tenant 2
        aggregate_id_2 = uuid4()
        event_2 = ExtractionRequested(
            aggregate_id=aggregate_id_2,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=tenant_id_2,
            page_id=uuid4(),
            page_url="https://tenant2.example.com",
            content_hash="tenant2hash",
            extraction_config={},
            requested_at=datetime.now(timezone.utc),
        )
        await event_store.append_events(
            aggregate_id=aggregate_id_2,
            aggregate_type="ExtractionProcess",
            events=[event_2],
            expected_version=0,
        )

        # Verify isolation
        stream_1 = await event_store.get_events(aggregate_id_1, "ExtractionProcess")
        stream_2 = await event_store.get_events(aggregate_id_2, "ExtractionProcess")

        assert stream_1.events[0].tenant_id == tenant_id_1
        assert stream_2.events[0].tenant_id == tenant_id_2


@pytest.mark.integration
@pytest.mark.asyncio
class TestEventStoreOptimisticLocking:
    """Tests for optimistic locking behavior."""

    async def test_append_with_correct_expected_version(self):
        """Test that append succeeds with correct expected version."""
        event_store = await get_event_store()
        aggregate_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        # First event
        event_1 = ExtractionRequested(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=tenant_id,
            page_id=page_id,
            page_url="https://example.com",
            content_hash="hash",
            extraction_config={},
            requested_at=datetime.now(timezone.utc),
        )
        result_1 = await event_store.append_events(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            events=[event_1],
            expected_version=0,
        )
        assert result_1.success is True

        # Second event with correct version
        event_2 = ExtractionStarted(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=2,
            tenant_id=tenant_id,
            page_id=page_id,
            worker_id="worker-1",
            started_at=datetime.now(timezone.utc),
        )
        result_2 = await event_store.append_events(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            events=[event_2],
            expected_version=1,  # Correct - current version is 1
        )
        assert result_2.success is True
        assert result_2.new_version == 2

    async def test_append_with_wrong_expected_version_raises_error(self):
        """Test that append raises OptimisticLockError with wrong expected version."""
        from eventsource.exceptions import OptimisticLockError

        event_store = await get_event_store()
        aggregate_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()

        # First event
        event_1 = ExtractionRequested(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=tenant_id,
            page_id=page_id,
            page_url="https://example.com",
            content_hash="hash",
            extraction_config={},
            requested_at=datetime.now(timezone.utc),
        )
        await event_store.append_events(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            events=[event_1],
            expected_version=0,
        )

        # Second event with wrong version - should raise OptimisticLockError
        event_2 = ExtractionStarted(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=2,
            tenant_id=tenant_id,
            page_id=page_id,
            worker_id="worker-1",
            started_at=datetime.now(timezone.utc),
        )

        with pytest.raises(OptimisticLockError) as exc_info:
            await event_store.append_events(
                aggregate_id=aggregate_id,
                aggregate_type="ExtractionProcess",
                events=[event_2],
                expected_version=0,  # Wrong - current version is 1
            )

        assert exc_info.value.aggregate_id == aggregate_id
        assert exc_info.value.expected_version == 0
        assert exc_info.value.actual_version == 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestEventStoreEmptyStream:
    """Tests for empty stream handling."""

    async def test_get_events_for_nonexistent_aggregate(self):
        """Test getting events for an aggregate that doesn't exist."""
        event_store = await get_event_store()
        nonexistent_id = uuid4()

        stream = await event_store.get_events(nonexistent_id, "ExtractionProcess")

        assert stream.is_empty is True
        assert len(stream.events) == 0
        assert stream.version == 0

    async def test_event_exists_returns_false_for_nonexistent(self):
        """Test event_exists returns False for nonexistent event."""
        event_store = await get_event_store()
        nonexistent_event_id = uuid4()

        exists = await event_store.event_exists(nonexistent_event_id)

        assert exists is False

    async def test_event_exists_returns_true_for_existing(self):
        """Test event_exists returns True for an existing event."""
        event_store = await get_event_store()
        aggregate_id = uuid4()
        tenant_id = uuid4()

        event = ExtractionRequested(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            aggregate_version=1,
            tenant_id=tenant_id,
            page_id=uuid4(),
            page_url="https://example.com",
            content_hash="hash",
            extraction_config={},
            requested_at=datetime.now(timezone.utc),
        )

        await event_store.append_events(
            aggregate_id=aggregate_id,
            aggregate_type="ExtractionProcess",
            events=[event],
            expected_version=0,
        )

        exists = await event_store.event_exists(event.event_id)

        assert exists is True
