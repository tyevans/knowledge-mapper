"""
Unit tests for RelationshipProjectionHandler.

Tests the projection handler that processes RelationshipDiscovered events
to create EntityRelationship records in the database.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.eventsourcing.events.extraction import RelationshipDiscovered
from app.eventsourcing.projections.extraction import RelationshipProjectionHandler


class TestRelationshipProjectionHandlerInit:
    """Test suite for RelationshipProjectionHandler initialization."""

    def test_handler_can_be_instantiated(self):
        """Test that RelationshipProjectionHandler can be instantiated with session factory."""
        mock_session_factory = MagicMock()

        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        assert handler is not None

    def test_handler_has_projection_name(self):
        """Test that handler has a projection name set."""
        mock_session_factory = MagicMock()

        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        # DatabaseProjection uses _projection_name attribute
        assert hasattr(handler, "_projection_name")

    def test_handler_accepts_optional_repos(self):
        """Test that handler accepts optional checkpoint and DLQ repositories."""
        mock_session_factory = MagicMock()
        mock_checkpoint_repo = MagicMock()
        mock_dlq_repo = MagicMock()

        handler = RelationshipProjectionHandler(
            session_factory=mock_session_factory,
            checkpoint_repo=mock_checkpoint_repo,
            dlq_repo=mock_dlq_repo,
            enable_tracing=True,
        )

        assert handler is not None


class TestFindEntityByName:
    """Test suite for _find_entity_by_name helper method."""

    @pytest.mark.asyncio
    async def test_find_entity_exact_match(self):
        """Test finding entity by exact name match."""
        mock_session_factory = MagicMock()
        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        tenant_id = uuid4()
        page_id = uuid4()
        entity_id = uuid4()
        entity_name = "TestEntity"

        # Mock connection and query result
        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (entity_id,)
        mock_conn.execute.return_value = mock_result

        result = await handler._find_entity_by_name(
            mock_conn, tenant_id, page_id, entity_name
        )

        assert result == entity_id
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_entity_normalized_match(self):
        """Test finding entity by normalized name when exact match fails."""
        mock_session_factory = MagicMock()
        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        tenant_id = uuid4()
        page_id = uuid4()
        entity_id = uuid4()
        entity_name = "TestEntity"

        # Mock connection - first query returns None, second returns entity
        mock_conn = AsyncMock()
        mock_result_none = MagicMock()
        mock_result_none.fetchone.return_value = None
        mock_result_found = MagicMock()
        mock_result_found.fetchone.return_value = (entity_id,)

        mock_conn.execute.side_effect = [mock_result_none, mock_result_found]

        result = await handler._find_entity_by_name(
            mock_conn, tenant_id, page_id, entity_name
        )

        assert result == entity_id
        assert mock_conn.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_find_entity_not_found(self):
        """Test returns None when entity not found."""
        mock_session_factory = MagicMock()
        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        tenant_id = uuid4()
        page_id = uuid4()
        entity_name = "NonExistentEntity"

        # Mock connection - both queries return None
        mock_conn = AsyncMock()
        mock_result_none = MagicMock()
        mock_result_none.fetchone.return_value = None
        mock_conn.execute.return_value = mock_result_none

        result = await handler._find_entity_by_name(
            mock_conn, tenant_id, page_id, entity_name
        )

        assert result is None


class TestHandleRelationshipDiscovered:
    """Test suite for _handle_relationship_discovered event handler."""

    def _create_relationship_event(
        self,
        tenant_id=None,
        page_id=None,
        relationship_id=None,
        source_name="SourceEntity",
        target_name="TargetEntity",
        relationship_type="RELATED_TO",
        confidence=0.95,
        context=None,
    ):
        """Helper to create RelationshipDiscovered event."""
        return RelationshipDiscovered(
            aggregate_id=uuid4(),
            tenant_id=tenant_id or uuid4(),
            page_id=page_id or uuid4(),
            relationship_id=relationship_id or uuid4(),
            source_entity_name=source_name,
            target_entity_name=target_name,
            relationship_type=relationship_type,
            confidence_score=confidence,
            context=context,
        )

    @pytest.mark.asyncio
    async def test_successful_relationship_creation(self):
        """Test successful relationship creation when both entities exist."""
        mock_session_factory = MagicMock()
        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        tenant_id = uuid4()
        page_id = uuid4()
        source_entity_id = uuid4()
        target_entity_id = uuid4()

        event = self._create_relationship_event(
            tenant_id=tenant_id,
            page_id=page_id,
            source_name="PersonA",
            target_name="CompanyB",
            relationship_type="works_for",
            confidence=0.9,
            context="PersonA works at CompanyB",
        )

        mock_conn = AsyncMock()

        # Mock entity lookups and insert
        with patch.object(
            handler,
            "_find_entity_by_name",
            side_effect=[source_entity_id, target_entity_id],
        ):
            await handler._handle_relationship_discovered(mock_conn, event)

        # Verify insert was called
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args

        # Check parameters
        params = call_args[0][1]
        assert params["relationship_id"] == event.relationship_id
        assert params["tenant_id"] == tenant_id
        assert params["source_entity_id"] == source_entity_id
        assert params["target_entity_id"] == target_entity_id
        assert params["relationship_type"] == "WORKS_FOR"  # Uppercase
        assert params["confidence_score"] == 0.9
        assert params["properties"] == '{"context": "PersonA works at CompanyB"}'

    @pytest.mark.asyncio
    async def test_skips_when_source_entity_missing(self):
        """Test that handler skips when source entity not found."""
        mock_session_factory = MagicMock()
        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        event = self._create_relationship_event()
        mock_conn = AsyncMock()

        # Mock source entity not found
        with patch.object(
            handler,
            "_find_entity_by_name",
            side_effect=[None, uuid4()],  # source not found
        ):
            await handler._handle_relationship_discovered(mock_conn, event)

        # Verify no insert was attempted
        mock_conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_target_entity_missing(self):
        """Test that handler skips when target entity not found."""
        mock_session_factory = MagicMock()
        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        event = self._create_relationship_event()
        mock_conn = AsyncMock()

        # Mock target entity not found
        with patch.object(
            handler,
            "_find_entity_by_name",
            side_effect=[uuid4(), None],  # target not found
        ):
            await handler._handle_relationship_discovered(mock_conn, event)

        # Verify no insert was attempted
        mock_conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_relationship_type_normalized_to_uppercase(self):
        """Test that relationship type is normalized to uppercase."""
        mock_session_factory = MagicMock()
        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        event = self._create_relationship_event(
            relationship_type="related_to",  # lowercase
        )
        mock_conn = AsyncMock()

        with patch.object(
            handler,
            "_find_entity_by_name",
            side_effect=[uuid4(), uuid4()],
        ):
            await handler._handle_relationship_discovered(mock_conn, event)

        call_args = mock_conn.execute.call_args
        params = call_args[0][1]
        assert params["relationship_type"] == "RELATED_TO"

    @pytest.mark.asyncio
    async def test_empty_properties_when_no_context(self):
        """Test that properties is empty dict when no context provided."""
        mock_session_factory = MagicMock()
        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        event = self._create_relationship_event(context=None)
        mock_conn = AsyncMock()

        with patch.object(
            handler,
            "_find_entity_by_name",
            side_effect=[uuid4(), uuid4()],
        ):
            await handler._handle_relationship_discovered(mock_conn, event)

        call_args = mock_conn.execute.call_args
        params = call_args[0][1]
        assert params["properties"] == '{}'


class TestRelationshipProjectionIdempotency:
    """Test suite for idempotent behavior."""

    @pytest.mark.asyncio
    async def test_upsert_sql_contains_on_conflict(self):
        """Test that SQL uses ON CONFLICT for idempotency."""
        mock_session_factory = MagicMock()
        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        event = RelationshipDiscovered(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            page_id=uuid4(),
            relationship_id=uuid4(),
            source_entity_name="A",
            target_entity_name="B",
            relationship_type="CONNECTS",
            confidence_score=1.0,
        )
        mock_conn = AsyncMock()

        with patch.object(
            handler,
            "_find_entity_by_name",
            side_effect=[uuid4(), uuid4()],
        ):
            await handler._handle_relationship_discovered(mock_conn, event)

        # Verify SQL includes ON CONFLICT
        call_args = mock_conn.execute.call_args
        sql_text = str(call_args[0][0])
        assert "ON CONFLICT" in sql_text
        assert "DO UPDATE" in sql_text


class TestRelationshipProjectionLogging:
    """Test suite for logging behavior."""

    @pytest.mark.asyncio
    async def test_logs_warning_on_missing_source_entity(self):
        """Test that warning is logged when source entity not found."""
        mock_session_factory = MagicMock()
        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        event = RelationshipDiscovered(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            page_id=uuid4(),
            relationship_id=uuid4(),
            source_entity_name="MissingSource",
            target_entity_name="Target",
            relationship_type="RELATES",
            confidence_score=0.8,
        )
        mock_conn = AsyncMock()

        with patch.object(handler, "_find_entity_by_name", return_value=None):
            with patch(
                "app.eventsourcing.projections.extraction.logger"
            ) as mock_logger:
                await handler._handle_relationship_discovered(mock_conn, event)

                mock_logger.warning.assert_called_once()
                call_args = mock_logger.warning.call_args
                assert "Source entity not found" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_logs_warning_on_missing_target_entity(self):
        """Test that warning is logged when target entity not found."""
        mock_session_factory = MagicMock()
        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        event = RelationshipDiscovered(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            page_id=uuid4(),
            relationship_id=uuid4(),
            source_entity_name="Source",
            target_entity_name="MissingTarget",
            relationship_type="RELATES",
            confidence_score=0.8,
        )
        mock_conn = AsyncMock()

        with patch.object(
            handler,
            "_find_entity_by_name",
            side_effect=[uuid4(), None],  # source found, target not
        ):
            with patch(
                "app.eventsourcing.projections.extraction.logger"
            ) as mock_logger:
                await handler._handle_relationship_discovered(mock_conn, event)

                mock_logger.warning.assert_called_once()
                call_args = mock_logger.warning.call_args
                assert "Target entity not found" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_logs_debug_on_successful_upsert(self):
        """Test that debug log is written on successful relationship upsert."""
        mock_session_factory = MagicMock()
        handler = RelationshipProjectionHandler(session_factory=mock_session_factory)

        event = RelationshipDiscovered(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            page_id=uuid4(),
            relationship_id=uuid4(),
            source_entity_name="Source",
            target_entity_name="Target",
            relationship_type="CONNECTS",
            confidence_score=1.0,
        )
        mock_conn = AsyncMock()

        with patch.object(
            handler,
            "_find_entity_by_name",
            side_effect=[uuid4(), uuid4()],
        ):
            with patch(
                "app.eventsourcing.projections.extraction.logger"
            ) as mock_logger:
                await handler._handle_relationship_discovered(mock_conn, event)

                mock_logger.debug.assert_called_once()
                call_args = mock_logger.debug.call_args
                assert "Upserted entity relationship" in call_args[0][0]
