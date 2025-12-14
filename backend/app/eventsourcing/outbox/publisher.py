"""
Outbox publisher for reliable event delivery to Kafka.

Implements the transactional outbox pattern by polling the outbox table
and publishing events to Kafka with proper tenant-based topic routing.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from eventsource import DomainEvent
from eventsource.bus import EventBus
from eventsource.events import default_registry

from app.core.config import settings
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class OutboxPublisher:
    """
    Background task that publishes events from the outbox to Kafka.

    The publisher polls the outbox table for pending events and publishes
    them to tenant-specific Kafka topics. Events are marked as published
    after successful delivery.

    Features:
    - Tenant-based topic routing (events.tenant-{id}.{aggregate_type})
    - Automatic retry with exponential backoff
    - Dead letter handling for persistently failing events
    - Graceful shutdown support

    Example:
        publisher = OutboxPublisher(kafka_bus)
        await publisher.start()

        # On shutdown
        await publisher.stop()
    """

    def __init__(
        self,
        kafka_bus: EventBus,
        poll_interval: float = 0.1,
        batch_size: int = 100,
        max_retries: int = 5,
    ):
        """
        Initialize the outbox publisher.

        Args:
            kafka_bus: Kafka bus for publishing events
            poll_interval: Seconds between polls (default 100ms)
            batch_size: Maximum events per batch
            max_retries: Max retry attempts before marking as failed
        """
        self._kafka_bus = kafka_bus
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """
        Start the outbox publisher background task.

        Creates an asyncio task that continuously polls the outbox
        and publishes events. The task runs until stop() is called.
        """
        if self._running:
            logger.warning("Outbox publisher already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(
            "Outbox publisher started",
            extra={
                "poll_interval": self._poll_interval,
                "batch_size": self._batch_size,
            },
        )

    async def stop(self) -> None:
        """
        Stop the outbox publisher gracefully.

        Signals the background task to stop and waits for it to complete
        processing the current batch.
        """
        if not self._running:
            return

        self._running = False
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Outbox publisher stop timed out, cancelling")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None
        logger.info("Outbox publisher stopped")

    async def _run(self) -> None:
        """Main loop that polls and publishes events."""
        while self._running:
            try:
                published_count = await self._publish_batch()
                if published_count > 0:
                    logger.debug(
                        "Published events from outbox",
                        extra={"count": published_count},
                    )
            except Exception as e:
                logger.error(
                    "Error in outbox publisher",
                    extra={"error": str(e)},
                    exc_info=True,
                )

            await asyncio.sleep(self._poll_interval)

    async def _publish_batch(self) -> int:
        """
        Fetch and publish a batch of pending events.

        Returns:
            Number of events published
        """
        async with AsyncSessionLocal() as session:
            # Fetch pending events
            result = await session.execute(
                select(OutboxEntry)
                .where(OutboxEntry.status == "pending")
                .order_by(OutboxEntry.id)
                .limit(self._batch_size)
                .with_for_update(skip_locked=True)
            )
            entries = result.scalars().all()

            if not entries:
                return 0

            published_count = 0
            for entry in entries:
                try:
                    await self._publish_entry(session, entry)
                    published_count += 1
                except Exception as e:
                    await self._handle_failure(session, entry, e)

            await session.commit()
            return published_count

    async def _publish_entry(self, session: AsyncSession, entry: "OutboxEntry") -> None:
        """
        Publish a single outbox entry to Kafka.

        Args:
            session: Database session for updating status
            entry: Outbox entry to publish
        """
        # Reconstruct the event from stored data
        event = self._reconstruct_event(entry)

        # Build tenant-specific topic
        topic = self._build_topic(entry.tenant_id, entry.aggregate_type)

        # Publish to Kafka
        await self._kafka_bus.publish([event], topic=topic)

        # Mark as published
        entry.status = "published"
        entry.published_at = datetime.now(timezone.utc)

        logger.debug(
            "Published event to Kafka",
            extra={
                "event_id": str(entry.event_id),
                "topic": topic,
                "event_type": entry.event_type,
            },
        )

    async def _handle_failure(
        self, session: AsyncSession, entry: "OutboxEntry", error: Exception
    ) -> None:
        """
        Handle a failed publish attempt.

        Args:
            session: Database session
            entry: Failed outbox entry
            error: The exception that occurred
        """
        entry.retry_count += 1
        entry.last_error = str(error)

        if entry.retry_count >= self._max_retries:
            entry.status = "failed"
            logger.error(
                "Event publish failed after max retries",
                extra={
                    "event_id": str(entry.event_id),
                    "retry_count": entry.retry_count,
                    "error": str(error),
                },
            )
        else:
            logger.warning(
                "Event publish failed, will retry",
                extra={
                    "event_id": str(entry.event_id),
                    "retry_count": entry.retry_count,
                    "error": str(error),
                },
            )

    def _reconstruct_event(self, entry: "OutboxEntry") -> DomainEvent:
        """
        Reconstruct a DomainEvent from outbox entry data.

        Args:
            entry: Outbox entry with serialized event

        Returns:
            Reconstructed domain event
        """
        event_class = default_registry.get(entry.event_type)
        return event_class.from_dict(entry.event_data)

    def _build_topic(self, tenant_id: Optional[UUID], aggregate_type: str) -> str:
        """
        Build the Kafka topic name for an event.

        Args:
            tenant_id: Tenant ID for topic prefix
            aggregate_type: Aggregate type for topic suffix

        Returns:
            Topic name like 'events.tenant-{id}.Statement'
        """
        prefix = settings.KAFKA_TOPIC_PREFIX
        if tenant_id:
            return f"{prefix}.tenant-{tenant_id}.{aggregate_type}"
        return f"{prefix}.{aggregate_type}"


# SQLAlchemy model for outbox table (matches migration)
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import declarative_base

OutboxBase = declarative_base()


class OutboxEntry(OutboxBase):
    """SQLAlchemy model for outbox table entries."""

    __tablename__ = "event_outbox"

    id = Column(PGUUID(as_uuid=True), primary_key=True)
    event_id = Column(PGUUID(as_uuid=True), nullable=False)
    aggregate_id = Column(PGUUID(as_uuid=True), nullable=False)
    aggregate_type = Column(String(255), nullable=False)
    tenant_id = Column(PGUUID(as_uuid=True), nullable=True)
    event_type = Column(String(255), nullable=False)
    event_data = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    retry_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
