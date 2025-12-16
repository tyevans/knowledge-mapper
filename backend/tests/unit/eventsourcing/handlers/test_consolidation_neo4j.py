"""
Unit tests for Neo4j consolidation sync handler.

Tests the ConsolidationNeo4jSyncHandler for syncing merge, undo,
and split operations to Neo4j.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.eventsourcing.events.consolidation import (
    EntitiesMerged,
    EntitySplit,
    MergeUndone,
)
from app.eventsourcing.handlers.consolidation_neo4j import ConsolidationNeo4jSyncHandler


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_driver():
    """Create a mock Neo4j async driver."""
    driver = MagicMock()

    # Create mock session that can be used as async context manager
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    driver.session.return_value = mock_session
    return driver


@pytest.fixture
def mock_session(mock_driver):
    """Get the mock session from the driver."""
    return mock_driver.session.return_value


@pytest.fixture
def tenant_id():
    """Create a test tenant ID."""
    return uuid.uuid4()


@pytest.fixture
def canonical_entity_id():
    """Create a canonical entity ID."""
    return uuid.uuid4()


@pytest.fixture
def merged_entity_ids():
    """Create merged entity IDs."""
    return [uuid.uuid4(), uuid.uuid4()]


@pytest.fixture
def user_id():
    """Create a test user ID."""
    return uuid.uuid4()


# =============================================================================
# Test Handler Routing
# =============================================================================


class TestHandlerRouting:
    """Tests for event routing in the handler."""

    @pytest.mark.asyncio
    async def test_handle_routes_to_entities_merged(
        self, mock_driver, mock_session, tenant_id, canonical_entity_id, merged_entity_ids
    ):
        """Test that EntitiesMerged event is routed correctly."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        event = EntitiesMerged(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            canonical_entity_id=canonical_entity_id,
            merged_entity_ids=merged_entity_ids,
            merge_reason="auto_high_confidence",
            similarity_scores={},
        )

        await handler.handle(event)

        # Verify session.run was called multiple times for the merge
        assert mock_session.run.call_count >= 4

    @pytest.mark.asyncio
    async def test_handle_routes_to_merge_undone(
        self, mock_driver, mock_session, tenant_id, canonical_entity_id, user_id
    ):
        """Test that MergeUndone event is routed correctly."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        event = MergeUndone(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            original_merge_event_id=uuid.uuid4(),
            canonical_entity_id=canonical_entity_id,
            restored_entity_ids=[uuid.uuid4()],
            original_entity_ids=[uuid.uuid4()],
            undo_reason="Testing",
            undone_by_user_id=user_id,
        )

        await handler.handle(event)

        # Verify session.run was called for undo operations
        assert mock_session.run.call_count >= 2

    @pytest.mark.asyncio
    async def test_handle_routes_to_entity_split(
        self, mock_driver, mock_session, tenant_id, user_id
    ):
        """Test that EntitySplit event is routed correctly."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        event = EntitySplit(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            original_entity_id=uuid.uuid4(),
            new_entity_ids=[uuid.uuid4(), uuid.uuid4()],
            new_entity_names=["Entity A", "Entity B"],
            property_assignments={},
            relationship_assignments={},
            split_reason="Testing",
            split_by_user_id=user_id,
        )

        await handler.handle(event)

        # Verify session.run was called for split operations
        assert mock_session.run.call_count >= 3

    @pytest.mark.asyncio
    async def test_handle_skips_unknown_event_type(self, mock_driver, mock_session):
        """Test that unknown event types are skipped."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        # Create event-like object with unknown type
        event = MagicMock()
        event.event_type = "UnknownEventType"
        event.aggregate_id = uuid.uuid4()

        await handler.handle(event)

        # Session should not be opened
        mock_session.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_skips_event_without_type(self, mock_driver, mock_session):
        """Test that events without event_type are skipped."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        event = MagicMock(spec=[])  # No attributes

        await handler.handle(event)

        mock_session.run.assert_not_called()


# =============================================================================
# Test EntitiesMerged Handler
# =============================================================================


class TestEntitiesMergedHandler:
    """Tests for EntitiesMerged event handling."""

    @pytest.mark.asyncio
    async def test_handle_entities_merged_transfers_relationships(
        self, mock_driver, mock_session, tenant_id, canonical_entity_id, merged_entity_ids
    ):
        """Test that relationships are transferred from merged to canonical."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        event = EntitiesMerged(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            canonical_entity_id=canonical_entity_id,
            merged_entity_ids=merged_entity_ids,
            merge_reason="auto_high_confidence",
            similarity_scores={"string_similarity": 0.95},
            property_merge_details={"merged_names": ["Entity A", "Entity B"]},
            relationship_transfer_count=5,
        )

        await handler._handle_EntitiesMerged(event)

        # Should execute queries for:
        # 1. Transfer outgoing relationships
        # 2. Transfer incoming relationships
        # 3. Remove self-refs
        # 4. Deduplicate
        # 5. Delete merged nodes
        # 6. Update canonical
        assert mock_session.run.call_count >= 5

    @pytest.mark.asyncio
    async def test_handle_entities_merged_deletes_merged_nodes(
        self, mock_driver, mock_session, tenant_id, canonical_entity_id, merged_entity_ids
    ):
        """Test that merged nodes are deleted from Neo4j."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        event = EntitiesMerged(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            canonical_entity_id=canonical_entity_id,
            merged_entity_ids=merged_entity_ids,
            merge_reason="user_approved",
            similarity_scores={},
        )

        await handler._handle_EntitiesMerged(event)

        # Check that delete query was executed
        calls = mock_session.run.call_args_list
        delete_calls = [c for c in calls if "DELETE merged" in str(c) or "DETACH DELETE" in str(c)]
        assert len(delete_calls) >= 1

    @pytest.mark.asyncio
    async def test_handle_entities_merged_updates_canonical_properties(
        self, mock_driver, mock_session, tenant_id, canonical_entity_id, merged_entity_ids
    ):
        """Test that canonical node properties are updated."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        event = EntitiesMerged(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            canonical_entity_id=canonical_entity_id,
            merged_entity_ids=merged_entity_ids,
            merge_reason="auto_high_confidence",
            similarity_scores={},
            property_merge_details={"merged_names": ["Alias 1", "Alias 2"]},
        )

        await handler._handle_EntitiesMerged(event)

        # Check that update canonical query was executed
        calls = mock_session.run.call_args_list
        update_calls = [c for c in calls if "merged_count" in str(c) or "aliases" in str(c)]
        assert len(update_calls) >= 1


# =============================================================================
# Test MergeUndone Handler
# =============================================================================


class TestMergeUndoneHandler:
    """Tests for MergeUndone event handling."""

    @pytest.mark.asyncio
    async def test_handle_merge_undone_creates_restored_nodes(
        self, mock_driver, mock_session, tenant_id, canonical_entity_id, user_id
    ):
        """Test that placeholder nodes are created for restored entities."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        restored_ids = [uuid.uuid4(), uuid.uuid4()]

        event = MergeUndone(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            original_merge_event_id=uuid.uuid4(),
            canonical_entity_id=canonical_entity_id,
            restored_entity_ids=restored_ids,
            original_entity_ids=[uuid.uuid4(), uuid.uuid4()],
            undo_reason="Incorrect merge",
            undone_by_user_id=user_id,
        )

        await handler._handle_MergeUndone(event)

        # Check that create query was executed for restored nodes
        calls = mock_session.run.call_args_list
        merge_calls = [c for c in calls if "MERGE" in str(c)]
        assert len(merge_calls) >= 1

    @pytest.mark.asyncio
    async def test_handle_merge_undone_updates_canonical_node(
        self, mock_driver, mock_session, tenant_id, canonical_entity_id, user_id
    ):
        """Test that canonical node is updated with undo metadata."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        event = MergeUndone(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            original_merge_event_id=uuid.uuid4(),
            canonical_entity_id=canonical_entity_id,
            restored_entity_ids=[uuid.uuid4()],
            original_entity_ids=[uuid.uuid4()],
            undo_reason="Testing",
            undone_by_user_id=user_id,
        )

        await handler._handle_MergeUndone(event)

        # Check that update canonical query was executed
        calls = mock_session.run.call_args_list
        update_calls = [c for c in calls if "undo_count" in str(c)]
        assert len(update_calls) >= 1


# =============================================================================
# Test EntitySplit Handler
# =============================================================================


class TestEntitySplitHandler:
    """Tests for EntitySplit event handling."""

    @pytest.mark.asyncio
    async def test_handle_entity_split_creates_new_nodes(
        self, mock_driver, mock_session, tenant_id, user_id
    ):
        """Test that new nodes are created for split entities."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        new_entity_ids = [uuid.uuid4(), uuid.uuid4()]

        event = EntitySplit(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            original_entity_id=uuid.uuid4(),
            new_entity_ids=new_entity_ids,
            new_entity_names=["Entity A", "Entity B"],
            property_assignments={},
            relationship_assignments={},
            split_reason="Contains multiple concepts",
            split_by_user_id=user_id,
        )

        await handler._handle_EntitySplit(event)

        # Check that create queries were executed for new nodes
        calls = mock_session.run.call_args_list
        merge_calls = [c for c in calls if "MERGE" in str(c) and "Entity" in str(c)]
        assert len(merge_calls) >= 2

    @pytest.mark.asyncio
    async def test_handle_entity_split_transfers_unassigned_to_first(
        self, mock_driver, mock_session, tenant_id, user_id
    ):
        """Test that unassigned relationships go to first new entity."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        new_entity_ids = [uuid.uuid4(), uuid.uuid4()]

        event = EntitySplit(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            original_entity_id=uuid.uuid4(),
            new_entity_ids=new_entity_ids,
            new_entity_names=["Entity A", "Entity B"],
            property_assignments={},
            relationship_assignments={},  # No explicit assignments
            split_reason="Testing",
            split_by_user_id=user_id,
        )

        await handler._handle_EntitySplit(event)

        # Check that transfer queries were executed
        # Should transfer remaining relationships to first new entity
        calls = mock_session.run.call_args_list
        assert len(calls) >= 3

    @pytest.mark.asyncio
    async def test_handle_entity_split_marks_original_as_split(
        self, mock_driver, mock_session, tenant_id, user_id
    ):
        """Test that original node is marked as split."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        original_entity_id = uuid.uuid4()

        event = EntitySplit(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            original_entity_id=original_entity_id,
            new_entity_ids=[uuid.uuid4(), uuid.uuid4()],
            new_entity_names=["Entity A", "Entity B"],
            property_assignments={},
            relationship_assignments={},
            split_reason="Testing",
            split_by_user_id=user_id,
        )

        await handler._handle_EntitySplit(event)

        # Check that mark split query was executed
        calls = mock_session.run.call_args_list
        mark_split_calls = [c for c in calls if "is_split" in str(c)]
        assert len(mark_split_calls) >= 1

    @pytest.mark.asyncio
    async def test_handle_entity_split_with_relationship_assignments(
        self, mock_driver, mock_session, tenant_id, user_id
    ):
        """Test split with explicit relationship assignments."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        new_entity_ids = [uuid.uuid4(), uuid.uuid4()]
        rel_id_1 = str(uuid.uuid4())
        rel_id_2 = str(uuid.uuid4())

        event = EntitySplit(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            original_entity_id=uuid.uuid4(),
            new_entity_ids=new_entity_ids,
            new_entity_names=["Entity A", "Entity B"],
            property_assignments={},
            relationship_assignments={
                rel_id_1: str(new_entity_ids[0]),
                rel_id_2: str(new_entity_ids[1]),
            },
            split_reason="Testing",
            split_by_user_id=user_id,
        )

        await handler._handle_EntitySplit(event)

        # Should have calls for each relationship assignment
        assert mock_session.run.call_count >= 6


# =============================================================================
# Test Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in the handler."""

    @pytest.mark.asyncio
    async def test_handle_error_is_raised(
        self, mock_driver, mock_session, tenant_id, canonical_entity_id, merged_entity_ids
    ):
        """Test that errors are raised for retry handling."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        # Make session.run raise an error
        mock_session.run.side_effect = Exception("Neo4j connection error")

        event = EntitiesMerged(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            canonical_entity_id=canonical_entity_id,
            merged_entity_ids=merged_entity_ids,
            merge_reason="auto_high_confidence",
            similarity_scores={},
        )

        with pytest.raises(Exception, match="Neo4j connection error"):
            await handler.handle(event)

    @pytest.mark.asyncio
    async def test_transfer_outgoing_continues_on_failure(
        self, mock_driver, mock_session, tenant_id, canonical_entity_id, merged_entity_ids
    ):
        """Test that transfer outgoing failure is logged but doesn't stop processing."""
        handler = ConsolidationNeo4jSyncHandler(mock_driver)

        # Make first run fail, then succeed for subsequent calls
        call_count = [0]

        async def mock_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Transfer failed")
            return MagicMock()

        mock_session.run = mock_run

        event = EntitiesMerged(
            aggregate_id=uuid.uuid4(),
            tenant_id=tenant_id,
            canonical_entity_id=canonical_entity_id,
            merged_entity_ids=merged_entity_ids,
            merge_reason="auto_high_confidence",
            similarity_scores={},
        )

        # Should not raise - continues with other operations
        await handler._handle_EntitiesMerged(event)

        # Verify we continued to call other operations
        assert call_count[0] > 1
