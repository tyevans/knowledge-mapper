"""
Unit tests for ExtractionTriggerHandler.

Tests cover:
- Handler initialization
- PageScraped event handling
- ExtractionProcess creation
- Idempotency behavior
- Error handling without raising
- Logging behavior
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.eventsourcing.events.scraping import PageScraped
from app.eventsourcing.projections.extraction_trigger import ExtractionTriggerHandler


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_event_store():
    """Create a mock event store."""
    return MagicMock()


@pytest.fixture
def handler(mock_event_store):
    """Create a handler instance with mock dependencies."""
    return ExtractionTriggerHandler(event_store=mock_event_store)


@pytest.fixture
def page_scraped_event():
    """Create a sample PageScraped event."""
    return PageScraped(
        aggregate_id=uuid4(),
        tenant_id=uuid4(),
        page_id=uuid4(),
        job_id=uuid4(),
        url="https://docs.example.com/api/reference",
        content_hash="abc123def456",
        http_status=200,
        depth=1,
        scraped_at=datetime.now(timezone.utc),
    )


def create_page_scraped_event(
    tenant_id=None,
    page_id=None,
    job_id=None,
    url="https://example.com/page",
    content_hash=None,
    http_status=200,
    depth=0,
):
    """Helper to create PageScraped events with custom values."""
    return PageScraped(
        aggregate_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        page_id=page_id or uuid4(),
        job_id=job_id or uuid4(),
        url=url,
        content_hash=content_hash or f"hash_{uuid4().hex[:8]}",
        http_status=http_status,
        depth=depth,
        scraped_at=datetime.now(timezone.utc),
    )


# =============================================================================
# Initialization Tests
# =============================================================================


class TestExtractionTriggerHandlerInit:
    """Test suite for ExtractionTriggerHandler initialization."""

    def test_handler_can_be_instantiated(self, mock_event_store):
        """Test that handler can be instantiated with event store."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        assert handler is not None

    def test_handler_has_projection_name(self, mock_event_store):
        """Test that handler has projection_name set."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        assert handler.projection_name == "extraction_trigger"

    def test_handler_stores_event_store(self, mock_event_store):
        """Test that handler stores event store reference."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        assert handler._event_store is mock_event_store

    def test_handler_initializes_empty_processed_hashes(self, mock_event_store):
        """Test that handler initializes with empty processed hashes set."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        assert handler._processed_content_hashes == set()

    def test_handler_accepts_optional_repos(self, mock_event_store):
        """Test that handler accepts optional checkpoint and DLQ repositories."""
        mock_checkpoint_repo = MagicMock()
        mock_dlq_repo = MagicMock()

        handler = ExtractionTriggerHandler(
            event_store=mock_event_store,
            checkpoint_repo=mock_checkpoint_repo,
            dlq_repo=mock_dlq_repo,
            enable_tracing=True,
        )

        assert handler is not None

    def test_handler_accepts_custom_processed_hashes(self, mock_event_store):
        """Test that handler accepts custom processed hashes set."""
        custom_hashes = {"hash1", "hash2"}

        handler = ExtractionTriggerHandler(
            event_store=mock_event_store,
            processed_content_hashes=custom_hashes,
        )

        assert handler._processed_content_hashes == custom_hashes

    def test_handler_logs_initialization(self, mock_event_store):
        """Test that handler logs initialization message."""
        with patch(
            "app.eventsourcing.projections.extraction_trigger.logger"
        ) as mock_logger:
            ExtractionTriggerHandler(event_store=mock_event_store)

            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert "ExtractionTriggerHandler initialized" in call_args[0][0]


# =============================================================================
# Handle PageScraped Tests
# =============================================================================


class TestHandlePageScraped:
    """Test suite for handle_page_scraped event handler."""

    @pytest.mark.asyncio
    async def test_creates_extraction_process(self, mock_event_store, page_scraped_event):
        """Test that handler creates ExtractionProcess for PageScraped event."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        # Mock the repository save method
        mock_repo = MagicMock()
        mock_repo.save = AsyncMock()

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            await handler.handle_page_scraped(page_scraped_event)

        # Verify save was called
        mock_repo.save.assert_called_once()

        # Verify the process has correct attributes
        saved_process = mock_repo.save.call_args[0][0]
        assert saved_process._state is not None
        assert saved_process._state.page_id == page_scraped_event.page_id
        assert saved_process._state.tenant_id == page_scraped_event.tenant_id
        assert saved_process._state.page_url == page_scraped_event.url
        assert saved_process._state.content_hash == page_scraped_event.content_hash

    @pytest.mark.asyncio
    async def test_marks_content_as_processed(self, mock_event_store, page_scraped_event):
        """Test that handler marks content hash as processed."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock()

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            await handler.handle_page_scraped(page_scraped_event)

        assert page_scraped_event.content_hash in handler._processed_content_hashes

    @pytest.mark.asyncio
    async def test_logs_success_on_creation(self, mock_event_store, page_scraped_event):
        """Test that handler logs info message on successful creation."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock()

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            with patch(
                "app.eventsourcing.projections.extraction_trigger.logger"
            ) as mock_logger:
                # Reset mock to clear initialization log
                mock_logger.info.reset_mock()

                await handler.handle_page_scraped(page_scraped_event)

                # Find the creation log call
                creation_calls = [
                    c for c in mock_logger.info.call_args_list
                    if "Created extraction process for page" in c[0][0]
                ]
                assert len(creation_calls) == 1

                call_extra = creation_calls[0].kwargs.get("extra", {})
                assert "process_id" in call_extra
                assert call_extra["page_id"] == str(page_scraped_event.page_id)
                assert call_extra["page_url"] == page_scraped_event.url

    @pytest.mark.asyncio
    async def test_creates_unique_process_id(self, mock_event_store, page_scraped_event):
        """Test that handler creates unique process ID for each event."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        saved_processes = []
        mock_repo = MagicMock()

        async def capture_save(process):
            saved_processes.append(process)

        mock_repo.save = AsyncMock(side_effect=capture_save)

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            # Process first event
            event1 = create_page_scraped_event(content_hash="hash1")
            await handler.handle_page_scraped(event1)

            # Process second event with different content hash
            event2 = create_page_scraped_event(content_hash="hash2")
            await handler.handle_page_scraped(event2)

        # Verify two different processes were created
        assert len(saved_processes) == 2
        assert saved_processes[0].aggregate_id != saved_processes[1].aggregate_id


# =============================================================================
# Idempotency Tests
# =============================================================================


class TestIdempotency:
    """Test suite for idempotent behavior."""

    @pytest.mark.asyncio
    async def test_skips_duplicate_content_hash(self, mock_event_store):
        """Test that handler skips events with already processed content hash."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock()

        content_hash = "duplicate_hash_123"
        event1 = create_page_scraped_event(content_hash=content_hash)
        event2 = create_page_scraped_event(content_hash=content_hash)

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            # Process first event
            await handler.handle_page_scraped(event1)
            # Process second event with same hash
            await handler.handle_page_scraped(event2)

        # Save should only be called once
        assert mock_repo.save.call_count == 1

    @pytest.mark.asyncio
    async def test_logs_skip_for_duplicate(self, mock_event_store):
        """Test that handler logs debug message when skipping duplicate."""
        # Pre-populate with processed hash
        content_hash = "already_processed"
        handler = ExtractionTriggerHandler(
            event_store=mock_event_store,
            processed_content_hashes={content_hash},
        )

        event = create_page_scraped_event(content_hash=content_hash)

        with patch(
            "app.eventsourcing.projections.extraction_trigger.logger"
        ) as mock_logger:
            # Reset mock to clear initialization log
            mock_logger.debug.reset_mock()

            await handler.handle_page_scraped(event)

            # Should log debug message about skipping
            skip_calls = [
                c for c in mock_logger.debug.call_args_list
                if "Skipping extraction for already processed content" in c[0][0]
            ]
            assert len(skip_calls) == 1

            call_extra = skip_calls[0].kwargs.get("extra", {})
            assert call_extra["content_hash"] == content_hash

    @pytest.mark.asyncio
    async def test_processes_different_content_hashes(self, mock_event_store):
        """Test that handler processes events with different content hashes."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock()

        event1 = create_page_scraped_event(content_hash="unique_hash_1")
        event2 = create_page_scraped_event(content_hash="unique_hash_2")
        event3 = create_page_scraped_event(content_hash="unique_hash_3")

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            await handler.handle_page_scraped(event1)
            await handler.handle_page_scraped(event2)
            await handler.handle_page_scraped(event3)

        # All three should be processed
        assert mock_repo.save.call_count == 3

    def test_is_content_already_processed_returns_true(self, mock_event_store):
        """Test _is_content_already_processed returns True for known hash."""
        handler = ExtractionTriggerHandler(
            event_store=mock_event_store,
            processed_content_hashes={"known_hash"},
        )

        assert handler._is_content_already_processed("known_hash") is True

    def test_is_content_already_processed_returns_false(self, mock_event_store):
        """Test _is_content_already_processed returns False for unknown hash."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        assert handler._is_content_already_processed("unknown_hash") is False

    def test_mark_content_processed_adds_hash(self, mock_event_store):
        """Test _mark_content_processed adds hash to set."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        handler._mark_content_processed("new_hash")

        assert "new_hash" in handler._processed_content_hashes


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Test suite for error handling behavior."""

    @pytest.mark.asyncio
    async def test_error_logged_not_raised(self, mock_event_store, page_scraped_event):
        """Test that errors are logged but not raised."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        # Make repository save raise an exception
        mock_repo = MagicMock()
        mock_repo.save = AsyncMock(side_effect=Exception("Database connection failed"))

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            with patch(
                "app.eventsourcing.projections.extraction_trigger.logger"
            ) as mock_logger:
                # Should not raise
                await handler.handle_page_scraped(page_scraped_event)

                # Should log error
                mock_logger.error.assert_called_once()
                call_args = mock_logger.error.call_args
                assert "Failed to trigger extraction for page" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_error_includes_context(self, mock_event_store, page_scraped_event):
        """Test that error logs include event context."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock(side_effect=RuntimeError("Test error"))

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            with patch(
                "app.eventsourcing.projections.extraction_trigger.logger"
            ) as mock_logger:
                await handler.handle_page_scraped(page_scraped_event)

                call_extra = mock_logger.error.call_args.kwargs.get("extra", {})
                assert call_extra["page_id"] == str(page_scraped_event.page_id)
                assert call_extra["page_url"] == page_scraped_event.url
                assert call_extra["content_hash"] == page_scraped_event.content_hash
                assert call_extra["tenant_id"] == str(page_scraped_event.tenant_id)
                assert call_extra["error_type"] == "RuntimeError"
                assert call_extra["error_message"] == "Test error"

    @pytest.mark.asyncio
    async def test_error_includes_exc_info(self, mock_event_store, page_scraped_event):
        """Test that error logs include exception info for debugging."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock(side_effect=Exception("Test exception"))

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            with patch(
                "app.eventsourcing.projections.extraction_trigger.logger"
            ) as mock_logger:
                await handler.handle_page_scraped(page_scraped_event)

                # Verify exc_info=True was passed
                call_kwargs = mock_logger.error.call_args.kwargs
                assert call_kwargs.get("exc_info") is True

    @pytest.mark.asyncio
    async def test_content_not_marked_on_error(self, mock_event_store, page_scraped_event):
        """Test that content hash is not marked as processed on error."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock(side_effect=Exception("Save failed"))

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            await handler.handle_page_scraped(page_scraped_event)

        # Content should NOT be marked as processed since save failed
        assert page_scraped_event.content_hash not in handler._processed_content_hashes

    @pytest.mark.asyncio
    async def test_repository_creation_error_handled(
        self, mock_event_store, page_scraped_event
    ):
        """Test that repository creation errors are handled."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            side_effect=Exception("Failed to create repository"),
        ):
            with patch(
                "app.eventsourcing.projections.extraction_trigger.logger"
            ) as mock_logger:
                # Should not raise
                await handler.handle_page_scraped(page_scraped_event)

                mock_logger.error.assert_called_once()


# =============================================================================
# Reset Tests
# =============================================================================


class TestReset:
    """Test suite for reset method."""

    @pytest.mark.asyncio
    async def test_reset_clears_processed_hashes(self, mock_event_store):
        """Test that reset clears processed content hashes."""
        handler = ExtractionTriggerHandler(
            event_store=mock_event_store,
            processed_content_hashes={"hash1", "hash2", "hash3"},
        )

        assert len(handler._processed_content_hashes) == 3

        await handler.reset()

        assert len(handler._processed_content_hashes) == 0

    @pytest.mark.asyncio
    async def test_reset_logs_message(self, mock_event_store):
        """Test that reset logs info message."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        with patch(
            "app.eventsourcing.projections.extraction_trigger.logger"
        ) as mock_logger:
            mock_logger.info.reset_mock()

            await handler.reset()

            reset_calls = [
                c for c in mock_logger.info.call_args_list
                if "ExtractionTriggerHandler reset" in c[0][0]
            ]
            assert len(reset_calls) == 1


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestExtractionProcessCreation:
    """Tests verifying correct ExtractionProcess creation."""

    @pytest.mark.asyncio
    async def test_process_has_pending_status(self, mock_event_store, page_scraped_event):
        """Test that created process has PENDING status."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        saved_process = None
        mock_repo = MagicMock()

        async def capture_save(process):
            nonlocal saved_process
            saved_process = process

        mock_repo.save = AsyncMock(side_effect=capture_save)

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            await handler.handle_page_scraped(page_scraped_event)

        from app.eventsourcing.aggregates.extraction import ExtractionStatus
        assert saved_process._state.status == ExtractionStatus.PENDING

    @pytest.mark.asyncio
    async def test_process_has_uncommitted_events(
        self, mock_event_store, page_scraped_event
    ):
        """Test that created process has ExtractionRequested event."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        saved_process = None
        mock_repo = MagicMock()

        async def capture_save(process):
            nonlocal saved_process
            saved_process = process

        mock_repo.save = AsyncMock(side_effect=capture_save)

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            await handler.handle_page_scraped(page_scraped_event)

        # Process should have one uncommitted event
        assert len(saved_process.uncommitted_events) == 1

        from app.eventsourcing.events.extraction import ExtractionRequested
        event = saved_process.uncommitted_events[0]
        assert isinstance(event, ExtractionRequested)
        assert event.page_id == page_scraped_event.page_id
        assert event.tenant_id == page_scraped_event.tenant_id
        assert event.page_url == page_scraped_event.url
        assert event.content_hash == page_scraped_event.content_hash

    @pytest.mark.asyncio
    async def test_repository_created_with_event_store(
        self, mock_event_store, page_scraped_event
    ):
        """Test that repository is created with the handler's event store."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock()

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ) as mock_create_repo:
            await handler.handle_page_scraped(page_scraped_event)

            mock_create_repo.assert_called_once_with(mock_event_store)


# =============================================================================
# Full Lifecycle Tests
# =============================================================================


class TestFullLifecycle:
    """Tests for complete handler lifecycle scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_pages_same_job(self, mock_event_store):
        """Test processing multiple pages from same scraping job."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        job_id = uuid4()
        tenant_id = uuid4()

        events = [
            create_page_scraped_event(
                job_id=job_id,
                tenant_id=tenant_id,
                url=f"https://example.com/page{i}",
                content_hash=f"hash_{i}",
            )
            for i in range(5)
        ]

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock()

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            for event in events:
                await handler.handle_page_scraped(event)

        # All 5 pages should be processed
        assert mock_repo.save.call_count == 5
        assert len(handler._processed_content_hashes) == 5

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(self, mock_event_store):
        """Test processing with some successes and some failures."""
        handler = ExtractionTriggerHandler(event_store=mock_event_store)

        events = [create_page_scraped_event(content_hash=f"hash_{i}") for i in range(3)]

        call_count = 0

        async def save_with_failures(process):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Second save fails
                raise Exception("Save failed")

        mock_repo = MagicMock()
        mock_repo.save = AsyncMock(side_effect=save_with_failures)

        with patch(
            "app.eventsourcing.projections.extraction_trigger.create_extraction_process_repository",
            return_value=mock_repo,
        ):
            for event in events:
                await handler.handle_page_scraped(event)

        # All 3 were attempted
        assert mock_repo.save.call_count == 3
        # Only 2 were marked as processed (first and third succeeded)
        assert len(handler._processed_content_hashes) == 2
        assert "hash_0" in handler._processed_content_hashes
        assert "hash_1" not in handler._processed_content_hashes  # Failed
        assert "hash_2" in handler._processed_content_hashes
