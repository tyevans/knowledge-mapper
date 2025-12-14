"""
Unit tests for Neo4j sync handlers.

Tests the projection handlers that sync EntityExtracted and RelationshipDiscovered
events to Neo4j graph database and update PostgreSQL sync status.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.eventsourcing.events.extraction import RelationshipDiscovered
from app.eventsourcing.events.scraping import EntityExtracted
from app.eventsourcing.projections.neo4j_sync import (
    Neo4jEntitySyncHandler,
    Neo4jRelationshipSyncHandler,
)


class TestNeo4jEntitySyncHandlerInit:
    """Test suite for Neo4jEntitySyncHandler initialization."""

    def test_handler_can_be_instantiated(self):
        """Test that Neo4jEntitySyncHandler can be instantiated with session factory."""
        mock_session_factory = MagicMock()

        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        assert handler is not None

    def test_handler_has_projection_name(self):
        """Test that handler has a projection name set."""
        mock_session_factory = MagicMock()

        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        # DatabaseProjection uses _projection_name attribute
        assert hasattr(handler, "_projection_name")

    def test_handler_accepts_optional_repos(self):
        """Test that handler accepts optional checkpoint and DLQ repositories."""
        mock_session_factory = MagicMock()
        mock_checkpoint_repo = MagicMock()
        mock_dlq_repo = MagicMock()

        handler = Neo4jEntitySyncHandler(
            session_factory=mock_session_factory,
            checkpoint_repo=mock_checkpoint_repo,
            dlq_repo=mock_dlq_repo,
            enable_tracing=True,
        )

        assert handler is not None

    def test_handler_logs_initialization(self):
        """Test that handler logs initialization message."""
        mock_session_factory = MagicMock()

        with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
            Neo4jEntitySyncHandler(session_factory=mock_session_factory)

            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert "Neo4jEntitySyncHandler initialized" in call_args[0][0]


class TestHandleEntityExtracted:
    """Test suite for _handle_entity_extracted event handler."""

    def _create_entity_event(
        self,
        tenant_id=None,
        entity_id=None,
        page_id=None,
        job_id=None,
        entity_type="FUNCTION",
        name="test_entity",
        normalized_name="test_entity",
        description="Test description",
        properties=None,
        extraction_method="llm_ollama",
        confidence_score=0.95,
        source_text=None,
    ):
        """Helper to create EntityExtracted event."""
        return EntityExtracted(
            aggregate_id=uuid4(),
            tenant_id=tenant_id or uuid4(),
            entity_id=entity_id or uuid4(),
            page_id=page_id or uuid4(),
            job_id=job_id or uuid4(),
            entity_type=entity_type,
            name=name,
            normalized_name=normalized_name,
            description=description,
            properties=properties or {},
            extraction_method=extraction_method,
            confidence_score=confidence_score,
            source_text=source_text,
        )

    @pytest.mark.asyncio
    async def test_successful_neo4j_sync(self):
        """Test successful entity sync to Neo4j and PostgreSQL update."""
        mock_session_factory = MagicMock()
        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        entity_id = uuid4()
        tenant_id = uuid4()
        neo4j_node_id = "4:abc123:456"

        event = self._create_entity_event(
            entity_id=entity_id,
            tenant_id=tenant_id,
            entity_type="CLASS",
            name="TestClass",
            description="A test class",
            properties={"methods": ["run", "stop"]},
        )

        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_entity_node.return_value = neo4j_node_id

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            await handler._handle_entity_extracted(mock_conn, event)

        # Verify Neo4j service was called with correct parameters
        mock_neo4j_service.create_entity_node.assert_called_once_with(
            entity_id=entity_id,
            tenant_id=tenant_id,
            entity_type="CLASS",
            name="TestClass",
            properties={"methods": ["run", "stop"]},
            description="A test class",
        )

        # Verify PostgreSQL update was called
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        params = call_args[0][1]
        assert params["node_id"] == neo4j_node_id
        assert params["entity_id"] == entity_id
        assert params["tenant_id"] == tenant_id

    @pytest.mark.asyncio
    async def test_entity_type_uppercase_conversion(self):
        """Test that entity_type is converted to uppercase for Neo4j."""
        mock_session_factory = MagicMock()
        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        event = self._create_entity_event(
            entity_type="function",  # lowercase
        )

        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_entity_node.return_value = "4:abc:123"

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            await handler._handle_entity_extracted(mock_conn, event)

        # Verify entity_type was uppercased
        call_args = mock_neo4j_service.create_entity_node.call_args
        assert call_args.kwargs["entity_type"] == "FUNCTION"

    @pytest.mark.asyncio
    async def test_empty_properties_handled(self):
        """Test that None properties are converted to empty dict."""
        mock_session_factory = MagicMock()
        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        event = self._create_entity_event(
            properties=None,  # None properties
        )

        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_entity_node.return_value = "4:abc:123"

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            await handler._handle_entity_extracted(mock_conn, event)

        # Verify empty dict was passed
        call_args = mock_neo4j_service.create_entity_node.call_args
        assert call_args.kwargs["properties"] == {}

    @pytest.mark.asyncio
    async def test_postgresql_update_with_sync_timestamp(self):
        """Test that PostgreSQL update includes synced_at timestamp."""
        mock_session_factory = MagicMock()
        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        event = self._create_entity_event()

        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_entity_node.return_value = "4:abc:123"

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            await handler._handle_entity_extracted(mock_conn, event)

        # Verify synced_at timestamp was included
        call_args = mock_conn.execute.call_args
        params = call_args[0][1]
        assert "synced_at" in params
        assert isinstance(params["synced_at"], datetime)
        assert params["synced_at"].tzinfo is not None  # Should be timezone-aware


class TestErrorHandling:
    """Test suite for error handling behavior."""

    def _create_entity_event(
        self,
        tenant_id=None,
        entity_id=None,
    ):
        """Helper to create EntityExtracted event."""
        return EntityExtracted(
            aggregate_id=uuid4(),
            tenant_id=tenant_id or uuid4(),
            entity_id=entity_id or uuid4(),
            page_id=uuid4(),
            job_id=uuid4(),
            entity_type="FUNCTION",
            name="test_entity",
            normalized_name="test_entity",
            extraction_method="llm_ollama",
            confidence_score=0.95,
        )

    @pytest.mark.asyncio
    async def test_neo4j_connection_error_logged_not_raised(self):
        """Test that Neo4j connection errors are logged but not raised."""
        mock_session_factory = MagicMock()
        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        event = self._create_entity_event()
        mock_conn = AsyncMock()

        # Simulate Neo4j connection failure
        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_entity_node.side_effect = ConnectionError("Neo4j unavailable")

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
                # Should not raise
                await handler._handle_entity_extracted(mock_conn, event)

                # Should log the error
                mock_logger.error.assert_called_once()
                call_args = mock_logger.error.call_args
                assert "Failed to sync entity to Neo4j" in call_args[0][0]

        # PostgreSQL should NOT be updated on failure
        mock_conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_neo4j_timeout_error_logged_not_raised(self):
        """Test that Neo4j timeout errors are logged but not raised."""
        mock_session_factory = MagicMock()
        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        event = self._create_entity_event()
        mock_conn = AsyncMock()

        # Simulate Neo4j timeout
        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_entity_node.side_effect = TimeoutError("Neo4j request timed out")

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
                # Should not raise
                await handler._handle_entity_extracted(mock_conn, event)

                # Should log the error with extra context
                mock_logger.error.assert_called_once()
                call_extra = mock_logger.error.call_args.kwargs.get("extra", {})
                assert "error_type" in call_extra
                assert call_extra["error_type"] == "TimeoutError"

    @pytest.mark.asyncio
    async def test_generic_exception_logged_not_raised(self):
        """Test that generic exceptions are logged but not raised."""
        mock_session_factory = MagicMock()
        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        event = self._create_entity_event()
        mock_conn = AsyncMock()

        # Simulate unexpected error
        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_entity_node.side_effect = RuntimeError("Unexpected error")

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            # Should not raise
            await handler._handle_entity_extracted(mock_conn, event)

        # PostgreSQL should NOT be updated on failure
        mock_conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_includes_entity_context(self):
        """Test that error logs include entity context for debugging."""
        mock_session_factory = MagicMock()
        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        entity_id = uuid4()
        tenant_id = uuid4()
        event = self._create_entity_event(
            entity_id=entity_id,
            tenant_id=tenant_id,
        )
        mock_conn = AsyncMock()

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_entity_node.side_effect = Exception("Test error")

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
                await handler._handle_entity_extracted(mock_conn, event)

                call_extra = mock_logger.error.call_args.kwargs.get("extra", {})
                assert call_extra["entity_id"] == str(entity_id)
                assert call_extra["tenant_id"] == str(tenant_id)
                assert call_extra["entity_type"] == "FUNCTION"


class TestPostgreSQLUpdateBehavior:
    """Test suite for PostgreSQL update behavior."""

    def _create_entity_event(
        self,
        tenant_id=None,
        entity_id=None,
    ):
        """Helper to create EntityExtracted event."""
        return EntityExtracted(
            aggregate_id=uuid4(),
            tenant_id=tenant_id or uuid4(),
            entity_id=entity_id or uuid4(),
            page_id=uuid4(),
            job_id=uuid4(),
            entity_type="FUNCTION",
            name="test_entity",
            normalized_name="test_entity",
            extraction_method="llm_ollama",
            confidence_score=0.95,
        )

    @pytest.mark.asyncio
    async def test_postgresql_update_sql_format(self):
        """Test that PostgreSQL update SQL is correct."""
        mock_session_factory = MagicMock()
        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        event = self._create_entity_event()

        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_entity_node.return_value = "4:abc:123"

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            await handler._handle_entity_extracted(mock_conn, event)

        # Verify SQL structure
        call_args = mock_conn.execute.call_args
        sql_text = str(call_args[0][0])
        assert "UPDATE extracted_entities" in sql_text
        assert "neo4j_node_id" in sql_text
        assert "synced_to_neo4j" in sql_text
        assert "synced_at" in sql_text
        assert "WHERE id = :entity_id" in sql_text
        assert "AND tenant_id = :tenant_id" in sql_text

    @pytest.mark.asyncio
    async def test_warning_logged_when_no_rows_updated(self):
        """Test that warning is logged when PostgreSQL update affects no rows."""
        mock_session_factory = MagicMock()
        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        event = self._create_entity_event()

        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0  # No rows updated
        mock_conn.execute.return_value = mock_result

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_entity_node.return_value = "4:abc:123"

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
                await handler._handle_entity_extracted(mock_conn, event)

                mock_logger.warning.assert_called_once()
                call_args = mock_logger.warning.call_args
                assert "No entity found to update" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_debug_logged_on_successful_sync(self):
        """Test that debug log is written on successful sync."""
        mock_session_factory = MagicMock()
        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        neo4j_node_id = "4:abc:123"
        event = self._create_entity_event()

        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_entity_node.return_value = neo4j_node_id

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
                await handler._handle_entity_extracted(mock_conn, event)

                mock_logger.debug.assert_called_once()
                call_args = mock_logger.debug.call_args
                assert "Synced entity to Neo4j" in call_args[0][0]
                call_extra = call_args.kwargs.get("extra", {})
                assert call_extra["neo4j_node_id"] == neo4j_node_id


class TestIdempotency:
    """Test suite for idempotent behavior."""

    def _create_entity_event(
        self,
        tenant_id=None,
        entity_id=None,
    ):
        """Helper to create EntityExtracted event."""
        return EntityExtracted(
            aggregate_id=uuid4(),
            tenant_id=tenant_id or uuid4(),
            entity_id=entity_id or uuid4(),
            page_id=uuid4(),
            job_id=uuid4(),
            entity_type="FUNCTION",
            name="test_entity",
            normalized_name="test_entity",
            extraction_method="llm_ollama",
            confidence_score=0.95,
        )

    @pytest.mark.asyncio
    async def test_same_entity_synced_twice_uses_merge(self):
        """Test that syncing same entity twice is handled by Neo4j MERGE."""
        mock_session_factory = MagicMock()
        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        entity_id = uuid4()
        tenant_id = uuid4()
        event = self._create_entity_event(
            entity_id=entity_id,
            tenant_id=tenant_id,
        )

        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result

        mock_neo4j_service = AsyncMock()
        # Same node ID returned both times (MERGE behavior)
        mock_neo4j_service.create_entity_node.return_value = "4:same:123"

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            # Process same event twice
            await handler._handle_entity_extracted(mock_conn, event)
            await handler._handle_entity_extracted(mock_conn, event)

        # Neo4j should be called twice with same parameters
        assert mock_neo4j_service.create_entity_node.call_count == 2

        # Both calls should have same entity_id
        for call in mock_neo4j_service.create_entity_node.call_args_list:
            assert call.kwargs["entity_id"] == entity_id


class TestTruncateReadModels:
    """Test suite for _truncate_read_models method."""

    @pytest.mark.asyncio
    async def test_truncate_logs_warning(self):
        """Test that truncate method logs a warning."""
        mock_session_factory = MagicMock()
        handler = Neo4jEntitySyncHandler(session_factory=mock_session_factory)

        with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
            await handler._truncate_read_models()

            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "Truncating Neo4j sync status" in call_args[0][0]


# =============================================================================
# Neo4jRelationshipSyncHandler Tests
# =============================================================================


class TestNeo4jRelationshipSyncHandlerInit:
    """Test suite for Neo4jRelationshipSyncHandler initialization."""

    def test_handler_can_be_instantiated(self):
        """Test that Neo4jRelationshipSyncHandler can be instantiated with session factory."""
        mock_session_factory = MagicMock()

        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        assert handler is not None

    def test_handler_has_projection_name(self):
        """Test that handler has a projection name set."""
        mock_session_factory = MagicMock()

        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        # DatabaseProjection uses _projection_name attribute
        assert hasattr(handler, "_projection_name")

    def test_handler_accepts_optional_repos(self):
        """Test that handler accepts optional checkpoint and DLQ repositories."""
        mock_session_factory = MagicMock()
        mock_checkpoint_repo = MagicMock()
        mock_dlq_repo = MagicMock()

        handler = Neo4jRelationshipSyncHandler(
            session_factory=mock_session_factory,
            checkpoint_repo=mock_checkpoint_repo,
            dlq_repo=mock_dlq_repo,
            enable_tracing=True,
        )

        assert handler is not None

    def test_handler_logs_initialization(self):
        """Test that handler logs initialization message."""
        mock_session_factory = MagicMock()

        with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
            Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

            # Should log initialization
            assert mock_logger.info.called
            # Find the call for relationship handler
            for call in mock_logger.info.call_args_list:
                if "Neo4jRelationshipSyncHandler initialized" in call[0][0]:
                    break
            else:
                pytest.fail("Expected initialization log message not found")


class TestHandleRelationshipDiscovered:
    """Test suite for _handle_relationship_discovered event handler."""

    def _create_relationship_event(
        self,
        tenant_id=None,
        relationship_id=None,
        page_id=None,
        source_entity_name="SourceEntity",
        target_entity_name="TargetEntity",
        relationship_type="USES",
        confidence_score=0.95,
        context=None,
    ):
        """Helper to create RelationshipDiscovered event."""
        return RelationshipDiscovered(
            aggregate_id=uuid4(),
            tenant_id=tenant_id or uuid4(),
            relationship_id=relationship_id or uuid4(),
            page_id=page_id or uuid4(),
            source_entity_name=source_entity_name,
            target_entity_name=target_entity_name,
            relationship_type=relationship_type,
            confidence_score=confidence_score,
            context=context,
        )

    @pytest.mark.asyncio
    async def test_successful_relationship_sync(self):
        """Test successful relationship sync to Neo4j and PostgreSQL update."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        relationship_id = uuid4()
        tenant_id = uuid4()
        page_id = uuid4()
        source_entity_id = uuid4()
        target_entity_id = uuid4()
        neo4j_rel_id = "5:abc123:789"

        event = self._create_relationship_event(
            relationship_id=relationship_id,
            tenant_id=tenant_id,
            page_id=page_id,
            source_entity_name="ClassA",
            target_entity_name="ClassB",
            relationship_type="IMPLEMENTS",
            confidence_score=0.9,
            context="ClassA implements ClassB interface",
        )

        mock_conn = AsyncMock()

        # Mock entity lookup results
        def mock_execute(sql, params=None):
            result = MagicMock()
            if "SELECT id, neo4j_node_id" in str(sql):
                if params and params.get("name") == "ClassA":
                    row = MagicMock()
                    row.id = source_entity_id
                    row.neo4j_node_id = "4:src:123"
                    result.fetchone.return_value = row
                elif params and params.get("name") == "ClassB":
                    row = MagicMock()
                    row.id = target_entity_id
                    row.neo4j_node_id = "4:tgt:456"
                    result.fetchone.return_value = row
                else:
                    result.fetchone.return_value = None
            else:
                # UPDATE query
                result.rowcount = 1
            return result

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_relationship.return_value = neo4j_rel_id

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            await handler._handle_relationship_discovered(mock_conn, event)

        # Verify Neo4j service was called with correct parameters
        mock_neo4j_service.create_relationship.assert_called_once_with(
            relationship_id=relationship_id,
            tenant_id=tenant_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relationship_type="IMPLEMENTS",
            properties={"context": "ClassA implements ClassB interface"},
            confidence_score=0.9,
        )

    @pytest.mark.asyncio
    async def test_missing_source_entity_logs_warning(self):
        """Test that missing source entity logs warning and returns early."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        event = self._create_relationship_event(
            source_entity_name="NonExistentSource",
            target_entity_name="ExistingTarget",
        )

        mock_conn = AsyncMock()

        def mock_execute(sql, params=None):
            result = MagicMock()
            if "SELECT id, neo4j_node_id" in str(sql):
                if params and params.get("name") == "ExistingTarget":
                    row = MagicMock()
                    row.id = uuid4()
                    row.neo4j_node_id = "4:tgt:456"
                    result.fetchone.return_value = row
                else:
                    result.fetchone.return_value = None
            return result

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
            await handler._handle_relationship_discovered(mock_conn, event)

            # Should log warning about missing entity
            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args
            assert "Cannot sync relationship" in call_args[0][0]
            call_extra = call_args.kwargs.get("extra", {})
            assert call_extra["source_found"] is False
            assert call_extra["target_found"] is True

    @pytest.mark.asyncio
    async def test_missing_target_entity_logs_warning(self):
        """Test that missing target entity logs warning and returns early."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        event = self._create_relationship_event(
            source_entity_name="ExistingSource",
            target_entity_name="NonExistentTarget",
        )

        mock_conn = AsyncMock()

        def mock_execute(sql, params=None):
            result = MagicMock()
            if "SELECT id, neo4j_node_id" in str(sql):
                if params and params.get("name") == "ExistingSource":
                    row = MagicMock()
                    row.id = uuid4()
                    row.neo4j_node_id = "4:src:123"
                    result.fetchone.return_value = row
                else:
                    result.fetchone.return_value = None
            return result

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
            await handler._handle_relationship_discovered(mock_conn, event)

            # Should log warning about missing entity
            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args
            assert "Cannot sync relationship" in call_args[0][0]
            call_extra = call_args.kwargs.get("extra", {})
            assert call_extra["source_found"] is True
            assert call_extra["target_found"] is False

    @pytest.mark.asyncio
    async def test_missing_both_entities_logs_warning(self):
        """Test that missing both entities logs warning and returns early."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        event = self._create_relationship_event()

        mock_conn = AsyncMock()
        # No entities found
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_conn.execute.return_value = mock_result

        with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
            await handler._handle_relationship_discovered(mock_conn, event)

            # Should log warning about missing entities
            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args
            assert "Cannot sync relationship" in call_args[0][0]
            call_extra = call_args.kwargs.get("extra", {})
            assert call_extra["source_found"] is False
            assert call_extra["target_found"] is False

    @pytest.mark.asyncio
    async def test_neo4j_returns_none_logs_warning(self):
        """Test that Neo4j returning None logs warning about missing entities in Neo4j."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        source_entity_id = uuid4()
        target_entity_id = uuid4()
        event = self._create_relationship_event()

        mock_conn = AsyncMock()

        def mock_execute(sql, params=None):
            result = MagicMock()
            if "SELECT id, neo4j_node_id" in str(sql):
                row = MagicMock()
                row.id = source_entity_id if params.get("name") == event.source_entity_name else target_entity_id
                row.neo4j_node_id = "4:node:123"
                result.fetchone.return_value = row
            return result

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_relationship.return_value = None  # Entities not found in Neo4j

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
                await handler._handle_relationship_discovered(mock_conn, event)

                # Should log warning about Neo4j returning None
                warning_calls = [c for c in mock_logger.warning.call_args_list
                                if "Neo4j create_relationship returned None" in c[0][0]]
                assert len(warning_calls) == 1

    @pytest.mark.asyncio
    async def test_empty_context_not_included_in_properties(self):
        """Test that empty context is not included in properties dict."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        event = self._create_relationship_event(context=None)

        mock_conn = AsyncMock()

        def mock_execute(sql, params=None):
            result = MagicMock()
            if "SELECT id, neo4j_node_id" in str(sql):
                row = MagicMock()
                row.id = uuid4()
                row.neo4j_node_id = "4:node:123"
                result.fetchone.return_value = row
            else:
                result.rowcount = 1
            return result

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_relationship.return_value = "5:rel:789"

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            await handler._handle_relationship_discovered(mock_conn, event)

        # Verify properties is empty dict when context is None
        call_args = mock_neo4j_service.create_relationship.call_args
        assert call_args.kwargs["properties"] == {}

    @pytest.mark.asyncio
    async def test_context_included_in_properties(self):
        """Test that context is included in properties dict when provided."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        event = self._create_relationship_event(context="Important relationship context")

        mock_conn = AsyncMock()

        def mock_execute(sql, params=None):
            result = MagicMock()
            if "SELECT id, neo4j_node_id" in str(sql):
                row = MagicMock()
                row.id = uuid4()
                row.neo4j_node_id = "4:node:123"
                result.fetchone.return_value = row
            else:
                result.rowcount = 1
            return result

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_relationship.return_value = "5:rel:789"

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            await handler._handle_relationship_discovered(mock_conn, event)

        # Verify properties includes context
        call_args = mock_neo4j_service.create_relationship.call_args
        assert call_args.kwargs["properties"] == {"context": "Important relationship context"}


class TestRelationshipSyncErrorHandling:
    """Test suite for relationship sync error handling behavior."""

    def _create_relationship_event(
        self,
        tenant_id=None,
        relationship_id=None,
    ):
        """Helper to create RelationshipDiscovered event."""
        return RelationshipDiscovered(
            aggregate_id=uuid4(),
            tenant_id=tenant_id or uuid4(),
            relationship_id=relationship_id or uuid4(),
            page_id=uuid4(),
            source_entity_name="SourceEntity",
            target_entity_name="TargetEntity",
            relationship_type="USES",
            confidence_score=0.95,
        )

    @pytest.mark.asyncio
    async def test_neo4j_connection_error_logged_not_raised(self):
        """Test that Neo4j connection errors are logged but not raised."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        event = self._create_relationship_event()
        mock_conn = AsyncMock()

        def mock_execute(sql, params=None):
            result = MagicMock()
            if "SELECT id, neo4j_node_id" in str(sql):
                row = MagicMock()
                row.id = uuid4()
                row.neo4j_node_id = "4:node:123"
                result.fetchone.return_value = row
            return result

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        # Simulate Neo4j connection failure
        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_relationship.side_effect = ConnectionError("Neo4j unavailable")

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
                # Should not raise
                await handler._handle_relationship_discovered(mock_conn, event)

                # Should log the error
                mock_logger.error.assert_called_once()
                call_args = mock_logger.error.call_args
                assert "Failed to sync relationship to Neo4j" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_error_includes_relationship_context(self):
        """Test that error logs include relationship context for debugging."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        relationship_id = uuid4()
        tenant_id = uuid4()
        event = self._create_relationship_event(
            relationship_id=relationship_id,
            tenant_id=tenant_id,
        )
        mock_conn = AsyncMock()

        def mock_execute(sql, params=None):
            result = MagicMock()
            if "SELECT id, neo4j_node_id" in str(sql):
                row = MagicMock()
                row.id = uuid4()
                row.neo4j_node_id = "4:node:123"
                result.fetchone.return_value = row
            return result

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_relationship.side_effect = Exception("Test error")

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
                await handler._handle_relationship_discovered(mock_conn, event)

                call_extra = mock_logger.error.call_args.kwargs.get("extra", {})
                assert call_extra["relationship_id"] == str(relationship_id)
                assert call_extra["tenant_id"] == str(tenant_id)
                assert call_extra["relationship_type"] == "USES"
                assert call_extra["error_type"] == "Exception"


class TestRelationshipPostgreSQLUpdateBehavior:
    """Test suite for relationship PostgreSQL update behavior."""

    def _create_relationship_event(
        self,
        tenant_id=None,
        relationship_id=None,
    ):
        """Helper to create RelationshipDiscovered event."""
        return RelationshipDiscovered(
            aggregate_id=uuid4(),
            tenant_id=tenant_id or uuid4(),
            relationship_id=relationship_id or uuid4(),
            page_id=uuid4(),
            source_entity_name="SourceEntity",
            target_entity_name="TargetEntity",
            relationship_type="USES",
            confidence_score=0.95,
        )

    @pytest.mark.asyncio
    async def test_postgresql_update_sql_format(self):
        """Test that PostgreSQL update SQL is correct for relationships."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        event = self._create_relationship_event()

        mock_conn = AsyncMock()
        execute_calls = []

        def mock_execute(sql, params=None):
            execute_calls.append((str(sql), params))
            result = MagicMock()
            if "SELECT id, neo4j_node_id" in str(sql):
                row = MagicMock()
                row.id = uuid4()
                row.neo4j_node_id = "4:node:123"
                result.fetchone.return_value = row
            else:
                result.rowcount = 1
            return result

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_relationship.return_value = "5:rel:789"

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            await handler._handle_relationship_discovered(mock_conn, event)

        # Find the UPDATE query
        update_query = None
        for sql_text, params in execute_calls:
            if "UPDATE entity_relationships" in sql_text:
                update_query = sql_text
                break

        assert update_query is not None
        assert "neo4j_relationship_id" in update_query
        assert "synced_to_neo4j" in update_query
        assert "WHERE id = :relationship_id" in update_query
        assert "AND tenant_id = :tenant_id" in update_query

    @pytest.mark.asyncio
    async def test_warning_logged_when_no_rows_updated(self):
        """Test that warning is logged when PostgreSQL update affects no rows."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        event = self._create_relationship_event()

        mock_conn = AsyncMock()

        def mock_execute(sql, params=None):
            result = MagicMock()
            if "SELECT id, neo4j_node_id" in str(sql):
                row = MagicMock()
                row.id = uuid4()
                row.neo4j_node_id = "4:node:123"
                result.fetchone.return_value = row
            else:
                result.rowcount = 0  # No rows updated
            return result

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_relationship.return_value = "5:rel:789"

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
                await handler._handle_relationship_discovered(mock_conn, event)

                # Should log warning about no rows updated
                warning_calls = [c for c in mock_logger.warning.call_args_list
                                if "No relationship found to update" in c[0][0]]
                assert len(warning_calls) == 1

    @pytest.mark.asyncio
    async def test_debug_logged_on_successful_sync(self):
        """Test that debug log is written on successful sync."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        neo4j_rel_id = "5:rel:789"
        event = self._create_relationship_event()

        mock_conn = AsyncMock()

        def mock_execute(sql, params=None):
            result = MagicMock()
            if "SELECT id, neo4j_node_id" in str(sql):
                row = MagicMock()
                row.id = uuid4()
                row.neo4j_node_id = "4:node:123"
                result.fetchone.return_value = row
            else:
                result.rowcount = 1
            return result

        mock_conn.execute = AsyncMock(side_effect=mock_execute)

        mock_neo4j_service = AsyncMock()
        mock_neo4j_service.create_relationship.return_value = neo4j_rel_id

        with patch(
            "app.eventsourcing.projections.neo4j_sync.get_neo4j_service",
            return_value=mock_neo4j_service,
        ):
            with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
                await handler._handle_relationship_discovered(mock_conn, event)

                # Should log debug message
                debug_calls = [c for c in mock_logger.debug.call_args_list
                              if "Synced relationship to Neo4j" in c[0][0]]
                assert len(debug_calls) == 1
                call_extra = debug_calls[0].kwargs.get("extra", {})
                assert call_extra["neo4j_relationship_id"] == neo4j_rel_id


class TestRelationshipFindEntity:
    """Test suite for _find_entity helper method."""

    @pytest.mark.asyncio
    async def test_find_entity_returns_dict_when_found(self):
        """Test that _find_entity returns dict with id and neo4j_node_id."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        entity_id = uuid4()
        neo4j_node_id = "4:abc:123"
        tenant_id = uuid4()
        page_id = uuid4()

        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = entity_id
        mock_row.neo4j_node_id = neo4j_node_id
        mock_result.fetchone.return_value = mock_row
        mock_conn.execute.return_value = mock_result

        result = await handler._find_entity(mock_conn, tenant_id, page_id, "TestEntity")

        assert result is not None
        assert result["id"] == entity_id
        assert result["neo4j_node_id"] == neo4j_node_id

    @pytest.mark.asyncio
    async def test_find_entity_returns_none_when_not_found(self):
        """Test that _find_entity returns None when entity not found."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        tenant_id = uuid4()
        page_id = uuid4()

        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_conn.execute.return_value = mock_result

        result = await handler._find_entity(mock_conn, tenant_id, page_id, "NonExistentEntity")

        assert result is None

    @pytest.mark.asyncio
    async def test_find_entity_queries_correct_table(self):
        """Test that _find_entity queries extracted_entities table."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        tenant_id = uuid4()
        page_id = uuid4()

        mock_conn = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_conn.execute.return_value = mock_result

        await handler._find_entity(mock_conn, tenant_id, page_id, "TestEntity")

        # Verify the SQL query
        call_args = mock_conn.execute.call_args
        sql_text = str(call_args[0][0])
        assert "extracted_entities" in sql_text
        assert "tenant_id" in sql_text
        assert "source_page_id" in sql_text
        assert "name" in sql_text


class TestRelationshipTruncateReadModels:
    """Test suite for relationship handler _truncate_read_models method."""

    @pytest.mark.asyncio
    async def test_truncate_logs_warning(self):
        """Test that truncate method logs a warning."""
        mock_session_factory = MagicMock()
        handler = Neo4jRelationshipSyncHandler(session_factory=mock_session_factory)

        with patch("app.eventsourcing.projections.neo4j_sync.logger") as mock_logger:
            await handler._truncate_read_models()

            # Should log warning about truncation
            warning_calls = [c for c in mock_logger.warning.call_args_list
                            if "Truncating Neo4j relationship sync status" in c[0][0]]
            assert len(warning_calls) == 1
