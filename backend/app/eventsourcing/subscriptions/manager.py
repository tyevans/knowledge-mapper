"""
Subscription manager for coordinating projection handlers and event processing.

Provides a wrapper around eventsource-py's SubscriptionManager with pre-configured
projection handlers for the Knowledge Mapper application. Enables resumable event
processing with checkpoint tracking.

This module integrates:
- EntityProjectionHandler: Projects EntityExtracted events to extracted_entities table
- RelationshipProjectionHandler: Projects RelationshipDiscovered events
- ExtractionProcessProjectionHandler: Projects extraction lifecycle events

Example:
    >>> from app.eventsourcing.subscriptions import get_subscription_manager
    >>> manager = await get_subscription_manager()
    >>> await manager.start()
    >>> # ... projection handlers now receiving events ...
    >>> await manager.stop()
"""

import logging
from typing import TYPE_CHECKING

from eventsource.repositories.checkpoint import PostgreSQLCheckpointRepository
from eventsource.subscriptions import SubscriptionManager, SubscriptionConfig

from app.core.config import settings
from app.core.database import engine, AsyncSessionLocal
from app.eventsourcing.stores.factory import get_event_store
from app.eventsourcing.bus.factory import get_kafka_bus
from app.eventsourcing.projections.extraction import (
    EntityProjectionHandler,
    RelationshipProjectionHandler,
    ExtractionProcessProjectionHandler,
)

if TYPE_CHECKING:
    from eventsource.stores import EventStore
    from eventsource.bus import EventBus

logger = logging.getLogger(__name__)

# Global singleton instance
_subscription_manager: "ExtractionSubscriptionManager | None" = None


class ExtractionSubscriptionManager:
    """
    Manages event subscriptions for extraction projections.

    Wraps eventsource-py's SubscriptionManager with Knowledge Mapper-specific
    projection handlers and configuration. Provides:

    - Automatic registration of extraction projection handlers
    - PostgreSQL checkpoint repository for resumable processing
    - Integration with the application's event store and event bus
    - Graceful startup and shutdown

    The manager coordinates three projection handlers:
    1. EntityProjectionHandler: Updates extracted_entities table
    2. RelationshipProjectionHandler: Updates entity_relationships table
    3. ExtractionProcessProjectionHandler: Updates extraction_processes table

    All handlers use checkpoint tracking for resumable processing, so events
    are not reprocessed after restarts.

    Example:
        >>> manager = await ExtractionSubscriptionManager.create()
        >>> await manager.start()
        >>> # Projections now processing events
        >>> health = manager.get_health()
        >>> await manager.stop()
    """

    def __init__(
        self,
        event_store: "EventStore",
        event_bus: "EventBus",
        checkpoint_repo: PostgreSQLCheckpointRepository,
        entity_handler: EntityProjectionHandler,
        relationship_handler: RelationshipProjectionHandler,
        process_handler: ExtractionProcessProjectionHandler,
    ) -> None:
        """
        Initialize the extraction subscription manager.

        Note: Use the create() factory method for normal instantiation.
        This constructor is for advanced use cases and testing.

        Args:
            event_store: Event store for historical event retrieval
            event_bus: Event bus for live event streaming
            checkpoint_repo: Repository for checkpoint persistence
            entity_handler: Handler for EntityExtracted events
            relationship_handler: Handler for RelationshipDiscovered events
            process_handler: Handler for extraction process lifecycle events
        """
        self._event_store = event_store
        self._event_bus = event_bus
        self._checkpoint_repo = checkpoint_repo
        self._entity_handler = entity_handler
        self._relationship_handler = relationship_handler
        self._process_handler = process_handler
        self._manager: SubscriptionManager | None = None
        self._running = False

    @classmethod
    async def create(
        cls,
        event_store: "EventStore | None" = None,
        event_bus: "EventBus | None" = None,
        enable_tracing: bool = True,
    ) -> "ExtractionSubscriptionManager":
        """
        Factory method to create and configure the subscription manager.

        Creates all required components:
        - Connects to the event store and event bus
        - Creates PostgreSQL checkpoint repository
        - Initializes projection handlers with session factory

        Args:
            event_store: Optional event store (uses global instance if not provided)
            event_bus: Optional event bus (uses global instance if not provided)
            enable_tracing: Enable OpenTelemetry tracing for handlers

        Returns:
            Configured ExtractionSubscriptionManager instance

        Example:
            >>> manager = await ExtractionSubscriptionManager.create()
            >>> await manager.start()
        """
        # Get or create event store and bus
        store = event_store or await get_event_store()
        bus = event_bus or await get_kafka_bus()

        # Create checkpoint repository using database engine
        checkpoint_repo = PostgreSQLCheckpointRepository(
            conn=engine,
            enable_tracing=enable_tracing,
        )

        # Create projection handlers with shared session factory
        entity_handler = EntityProjectionHandler(
            session_factory=AsyncSessionLocal,
            checkpoint_repo=checkpoint_repo,
            enable_tracing=enable_tracing,
        )

        relationship_handler = RelationshipProjectionHandler(
            session_factory=AsyncSessionLocal,
            checkpoint_repo=checkpoint_repo,
            enable_tracing=enable_tracing,
        )

        process_handler = ExtractionProcessProjectionHandler(
            session_factory=AsyncSessionLocal,
            checkpoint_repo=checkpoint_repo,
            enable_tracing=enable_tracing,
        )

        logger.info(
            "Created extraction subscription manager",
            extra={
                "event_store_type": type(store).__name__,
                "event_bus_type": type(bus).__name__,
                "tracing_enabled": enable_tracing,
            },
        )

        return cls(
            event_store=store,
            event_bus=bus,
            checkpoint_repo=checkpoint_repo,
            entity_handler=entity_handler,
            relationship_handler=relationship_handler,
            process_handler=process_handler,
        )

    async def _initialize_manager(self) -> SubscriptionManager:
        """
        Initialize the eventsource-py SubscriptionManager with handlers.

        Creates the manager and registers all projection handlers as subscribers.

        Returns:
            Configured SubscriptionManager instance
        """
        manager = SubscriptionManager(
            event_store=self._event_store,
            event_bus=self._event_bus,
            checkpoint_repo=self._checkpoint_repo,
            shutdown_timeout=30.0,
            drain_timeout=10.0,
            enable_tracing=True,
        )

        # Configure subscriptions to start from last checkpoint
        config = SubscriptionConfig(
            start_from="checkpoint",  # Resume from last position
            batch_size=100,  # Process events in batches of 100
        )

        # Register projection handlers
        await manager.subscribe(
            self._entity_handler,
            config=config,
            name="EntityProjection",
        )
        await manager.subscribe(
            self._relationship_handler,
            config=config,
            name="RelationshipProjection",
        )
        await manager.subscribe(
            self._process_handler,
            config=config,
            name="ExtractionProcessProjection",
        )

        logger.info(
            "Registered projection handlers",
            extra={
                "handlers": [
                    "EntityProjection",
                    "RelationshipProjection",
                    "ExtractionProcessProjection",
                ],
            },
        )

        return manager

    async def start(self) -> None:
        """
        Start the subscription manager and begin processing events.

        Initializes the SubscriptionManager, registers all handlers, and
        starts event processing. Each handler will:
        1. Load its last checkpoint position
        2. Catch up from that position (if events are pending)
        3. Transition to live event processing

        Raises:
            RuntimeError: If manager is already running
        """
        if self._running:
            logger.warning("Subscription manager already running")
            return

        logger.info("Starting extraction subscription manager")

        # Initialize and start the manager
        self._manager = await self._initialize_manager()
        await self._manager.start()
        self._running = True

        logger.info(
            "Extraction subscription manager started",
            extra={
                "subscription_count": self._manager.subscription_count,
                "subscriptions": self._manager.subscription_names,
            },
        )

    async def stop(self) -> None:
        """
        Stop the subscription manager gracefully.

        Stops event processing, saves final checkpoints, and cleans up
        resources. In-flight events will be allowed to complete within
        the configured drain timeout.
        """
        if not self._running or self._manager is None:
            return

        logger.info("Stopping extraction subscription manager")

        try:
            await self._manager.stop(timeout=30.0)
            logger.info("Extraction subscription manager stopped")
        except Exception as e:
            logger.error(
                "Error stopping subscription manager",
                extra={"error": str(e)},
                exc_info=True,
            )
        finally:
            self._running = False
            self._manager = None

    @property
    def is_running(self) -> bool:
        """Check if the subscription manager is running."""
        return self._running

    def get_health(self) -> dict:
        """
        Get health status of all subscriptions.

        Returns:
            Dictionary with subscription health information including:
            - status: Overall health status
            - running: Whether manager is running
            - subscription_count: Number of registered subscriptions
            - subscriptions: Per-subscription status details
        """
        if self._manager is None:
            return {
                "status": "stopped",
                "running": False,
                "subscription_count": 0,
                "subscriptions": [],
            }

        return self._manager.get_health()

    async def health_check(self):
        """
        Get comprehensive health status for Kubernetes probes.

        Returns:
            ManagerHealth object with detailed health information
        """
        if self._manager is None:
            return None
        return await self._manager.health_check()

    async def readiness_check(self):
        """
        Check if the manager is ready to accept work.

        Returns:
            ReadinessStatus indicating readiness state
        """
        if self._manager is None:
            return None
        return await self._manager.readiness_check()

    async def liveness_check(self):
        """
        Check if the manager is alive and responsive.

        Returns:
            LivenessStatus indicating liveness state
        """
        if self._manager is None:
            return None
        return await self._manager.liveness_check()


async def get_subscription_manager() -> ExtractionSubscriptionManager:
    """
    Get or create the global subscription manager instance.

    Returns the singleton ExtractionSubscriptionManager, creating it if
    necessary. The manager is not started automatically - call start()
    after obtaining the instance.

    Returns:
        ExtractionSubscriptionManager: The global subscription manager

    Example:
        >>> manager = await get_subscription_manager()
        >>> await manager.start()
    """
    global _subscription_manager

    if _subscription_manager is None:
        _subscription_manager = await ExtractionSubscriptionManager.create()

    return _subscription_manager


async def close_subscription_manager() -> None:
    """
    Stop and clean up the global subscription manager.

    Should be called during application shutdown to ensure proper cleanup.
    Stops all subscriptions, saves checkpoints, and releases resources.
    """
    global _subscription_manager

    if _subscription_manager is not None:
        await _subscription_manager.stop()
        _subscription_manager = None
        logger.info("Subscription manager closed")


__all__ = [
    "ExtractionSubscriptionManager",
    "get_subscription_manager",
    "close_subscription_manager",
]
