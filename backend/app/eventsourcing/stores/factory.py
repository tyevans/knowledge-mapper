"""
Event store factory for Knowledge Mapper.

Provides singleton access to the PostgreSQL event store with proper
configuration and connection management.

Factory Functions:
    - get_event_store(): Async factory for FastAPI endpoints (preferred)
    - get_event_store_sync(): Sync factory for Celery tasks
    - close_event_store(): Cleanup for application shutdown
"""

import asyncio
import logging
from typing import Optional, Sequence

from eventsource import PostgreSQLEventStore, InMemoryEventStore
from eventsource.events import DomainEvent, default_registry
from eventsource.stores import EventStore

from app.core.config import settings
from app.core.database import AsyncSessionLocal, SyncSessionLocal

logger = logging.getLogger(__name__)


class SyncEventStoreWrapper:
    """
    Wrapper that provides sync methods for async event stores.

    Used by Celery tasks which run in a synchronous context but need
    to interact with the async PostgreSQLEventStore.
    """

    def __init__(self, event_store: EventStore):
        self._store = event_store

    def append_sync(self, event: DomainEvent) -> None:
        """
        Append a single event synchronously.

        Creates a new event loop to run the async append_events method.
        """
        self.append_events_sync([event])

    def append_events_sync(self, events: Sequence[DomainEvent]) -> None:
        """
        Append multiple events synchronously.

        Creates a new event loop to run the async append_events method.
        Events must have aggregate_id and aggregate_type attributes.
        """
        if not events:
            return

        # Extract aggregate info from first event
        first_event = events[0]
        aggregate_id = first_event.aggregate_id
        aggregate_type = getattr(first_event, "aggregate_type", "Unknown")

        # For notification events outside aggregate context, use version 0
        # (no optimistic locking needed)
        expected_version = 0

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, need to use run_coroutine_threadsafe
                import concurrent.futures

                future = asyncio.run_coroutine_threadsafe(
                    self._store.append_events(
                        aggregate_id, aggregate_type, list(events), expected_version
                    ),
                    loop,
                )
                future.result(timeout=30)
            else:
                loop.run_until_complete(
                    self._store.append_events(
                        aggregate_id, aggregate_type, list(events), expected_version
                    )
                )
        except RuntimeError:
            # No event loop exists, create one
            asyncio.run(
                self._store.append_events(
                    aggregate_id, aggregate_type, list(events), expected_version
                )
            )

    @property
    def outbox_enabled(self) -> bool:
        """Check if outbox is enabled on underlying store."""
        return getattr(self._store, "outbox_enabled", False)

# Singleton instances
_event_store: Optional[EventStore] = None
_sync_event_store: Optional[SyncEventStoreWrapper] = None


def create_event_store() -> EventStore:
    """
    Create a new event store instance.

    Uses PostgreSQLEventStore for production with transactional outbox support.
    Falls back to InMemoryEventStore if event sourcing is disabled.

    Returns:
        EventStore: Configured event store instance
    """
    if not settings.EVENT_STORE_ENABLED:
        logger.info("Event store disabled, using InMemoryEventStore")
        return InMemoryEventStore(enable_tracing=True)

    logger.info(
        "Creating PostgreSQL event store",
        extra={
            "outbox_enabled": settings.EVENT_STORE_OUTBOX_ENABLED,
        },
    )

    return PostgreSQLEventStore(
        session_factory=AsyncSessionLocal,
        event_registry=default_registry,
        outbox_enabled=settings.EVENT_STORE_OUTBOX_ENABLED,
        enable_tracing=True,
        # Auto-detect UUID fields (tenant_id, aggregate_id, etc.)
        auto_detect_uuid=True,
    )


async def get_event_store() -> EventStore:
    """
    Get the singleton event store instance.

    Creates the instance on first call, then returns the cached instance.
    This ensures all parts of the application share the same event store.

    Returns:
        EventStore: The application's event store
    """
    global _event_store
    if _event_store is None:
        _event_store = create_event_store()
    return _event_store


async def close_event_store() -> None:
    """
    Clean up event store resources.

    Should be called during application shutdown to ensure proper cleanup.
    """
    global _event_store, _sync_event_store
    if _event_store is not None:
        # PostgreSQLEventStore doesn't need explicit cleanup
        # (uses shared session factory)
        _event_store = None
        logger.info("Event store closed")
    if _sync_event_store is not None:
        _sync_event_store = None
        logger.info("Sync event store closed")


def create_sync_event_store() -> SyncEventStoreWrapper:
    """
    Create a new synchronous event store wrapper instance.

    Wraps the async PostgreSQLEventStore to provide synchronous methods
    for use in Celery task workers.

    Returns:
        SyncEventStoreWrapper: Wrapped event store with sync methods
    """
    if not settings.EVENT_STORE_ENABLED:
        logger.info("Event store disabled, using InMemoryEventStore (sync wrapper)")
        store = InMemoryEventStore(enable_tracing=True)
        return SyncEventStoreWrapper(store)

    logger.info(
        "Creating PostgreSQL event store (sync wrapper)",
        extra={
            "outbox_enabled": settings.EVENT_STORE_OUTBOX_ENABLED,
        },
    )

    # Use AsyncSessionLocal since PostgreSQLEventStore is async internally
    store = PostgreSQLEventStore(
        session_factory=AsyncSessionLocal,
        event_registry=default_registry,
        outbox_enabled=settings.EVENT_STORE_OUTBOX_ENABLED,
        enable_tracing=True,
        auto_detect_uuid=True,
    )
    return SyncEventStoreWrapper(store)


def get_event_store_sync() -> SyncEventStoreWrapper:
    """
    Get the singleton sync event store wrapper instance.

    Creates the instance on first call, then returns the cached instance.
    Use this for Celery tasks and other synchronous contexts.

    Returns:
        SyncEventStoreWrapper: The application's sync event store wrapper
    """
    global _sync_event_store
    if _sync_event_store is None:
        _sync_event_store = create_sync_event_store()
    return _sync_event_store
