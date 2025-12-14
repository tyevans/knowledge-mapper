"""
Handler to trigger extraction on page scrape.

This module implements the ExtractionTriggerHandler, which listens for
PageScraped events and creates ExtractionProcess aggregates to initiate
entity extraction from newly scraped pages.

The handler:
- Creates a new ExtractionProcess aggregate for each PageScraped event
- Includes idempotency checks to prevent duplicate extractions
- Uses error handling that logs but doesn't raise to avoid blocking scraping
"""

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from eventsource import DeclarativeProjection, handles

from app.eventsourcing.aggregates.extraction import (
    ExtractionProcess,
    create_extraction_process_repository,
)
from app.eventsourcing.events.scraping import PageScraped

if TYPE_CHECKING:
    from eventsource import EventStore
    from eventsource.repositories import CheckpointRepository, DLQRepository

logger = logging.getLogger(__name__)


class ExtractionTriggerHandler(DeclarativeProjection):
    """
    Triggers extraction when a page is scraped.

    Listens for PageScraped events and creates ExtractionProcess
    aggregates to initiate entity extraction.

    This handler ensures:
    - Automatic triggering of extraction on page scrape
    - Idempotent behavior (same content_hash doesn't create duplicate processes)
    - Failure isolation (extraction failures don't block page scraping)
    - Full logging for debugging and monitoring

    Example:
        >>> from eventsource import InMemoryEventStore
        >>> event_store = InMemoryEventStore()
        >>> handler = ExtractionTriggerHandler(event_store=event_store)
        >>> await handler.handle(page_scraped_event)
    """

    projection_name = "extraction_trigger"

    def __init__(
        self,
        event_store: "EventStore",
        checkpoint_repo: "CheckpointRepository | None" = None,
        dlq_repo: "DLQRepository | None" = None,
        enable_tracing: bool = False,
        processed_content_hashes: set[str] | None = None,
    ) -> None:
        """
        Initialize the extraction trigger handler.

        Args:
            event_store: Event store for persisting extraction process events
            checkpoint_repo: Optional checkpoint repository for tracking position
            dlq_repo: Optional DLQ repository for failed events
            enable_tracing: Enable OpenTelemetry tracing (default: False)
            processed_content_hashes: Optional set for tracking processed hashes
                                     (used for testing/dependency injection)
        """
        super().__init__(
            checkpoint_repo=checkpoint_repo,
            dlq_repo=dlq_repo,
            enable_tracing=enable_tracing,
        )
        self._event_store = event_store
        # Track processed content hashes for idempotency
        # In production, this would typically be backed by a database lookup
        self._processed_content_hashes: set[str] = processed_content_hashes or set()
        logger.info(
            "ExtractionTriggerHandler initialized",
            extra={"projection": self.projection_name},
        )

    def _is_content_already_processed(self, content_hash: str) -> bool:
        """
        Check if content has already been processed for extraction.

        This provides idempotency - the same page content won't trigger
        multiple extraction processes.

        Args:
            content_hash: Hash of the page content

        Returns:
            True if content has already been processed, False otherwise
        """
        return content_hash in self._processed_content_hashes

    def _mark_content_processed(self, content_hash: str) -> None:
        """
        Mark content as processed to prevent duplicate extractions.

        Args:
            content_hash: Hash of the page content
        """
        self._processed_content_hashes.add(content_hash)

    @handles(PageScraped)
    async def handle_page_scraped(self, event: PageScraped) -> None:
        """
        Create extraction process for scraped page.

        This handler:
        1. Checks idempotency (skips if content already processed)
        2. Creates a new ExtractionProcess aggregate
        3. Requests extraction with page details
        4. Saves the process via repository
        5. Logs success or failure appropriately

        Args:
            event: PageScraped event containing page details

        Note:
            Errors are logged but not raised to avoid blocking page processing.
        """
        try:
            # Idempotency check
            if self._is_content_already_processed(event.content_hash):
                logger.debug(
                    "Skipping extraction for already processed content",
                    extra={
                        "projection": self.projection_name,
                        "page_id": str(event.page_id),
                        "content_hash": event.content_hash,
                        "tenant_id": str(event.tenant_id),
                    },
                )
                return

            # Create repository from event store
            repo = create_extraction_process_repository(self._event_store)

            # Create new extraction process
            process_id = uuid4()
            process = ExtractionProcess(process_id)

            # Request extraction with page details
            process.request_extraction(
                page_id=event.page_id,
                tenant_id=event.tenant_id,
                page_url=event.url,
                content_hash=event.content_hash,
            )

            # Save the process (persists ExtractionRequested event)
            await repo.save(process)

            # Mark content as processed for idempotency
            self._mark_content_processed(event.content_hash)

            logger.info(
                "Created extraction process for page",
                extra={
                    "projection": self.projection_name,
                    "process_id": str(process_id),
                    "page_id": str(event.page_id),
                    "page_url": event.url,
                    "content_hash": event.content_hash,
                    "tenant_id": str(event.tenant_id),
                },
            )

        except Exception as e:
            # Log error but don't raise - we don't want to block page processing
            logger.error(
                "Failed to trigger extraction for page",
                extra={
                    "projection": self.projection_name,
                    "page_id": str(event.page_id),
                    "page_url": event.url,
                    "content_hash": event.content_hash,
                    "tenant_id": str(event.tenant_id),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
                exc_info=True,
            )

    async def reset(self) -> None:
        """
        Reset the projection state.

        Clears the set of processed content hashes and calls parent reset.
        """
        self._processed_content_hashes.clear()
        await super().reset()
        logger.info(
            "ExtractionTriggerHandler reset",
            extra={"projection": self.projection_name},
        )


__all__ = ["ExtractionTriggerHandler"]
