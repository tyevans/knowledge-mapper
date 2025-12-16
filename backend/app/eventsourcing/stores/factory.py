"""
Event store factory for Knowledge Mapper.

Provides singleton access to the PostgreSQL event store with proper
configuration and connection management.

Factory Functions:
    - get_event_store(): Async factory for FastAPI endpoints (preferred)
    - get_event_store_sync(): Sync factory for Celery tasks
    - close_event_store(): Cleanup for application shutdown
"""

import logging
from collections.abc import Sequence
from typing import Optional

from eventsource import PostgreSQLEventStore, InMemoryEventStore
from eventsource.events import DomainEvent, default_registry
from eventsource.stores import EventStore
from eventsource.sync import SyncEventStoreAdapter
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


def _create_worker_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Create an isolated async session factory for Celery workers.

    This factory uses NullPool (no connection pooling) to avoid asyncpg
    connection state conflicts when using asyncio.run() multiple times.

    The issue: asyncpg connections are bound to the event loop they were
    created in. When asyncio.run() closes its loop, those connections become
    invalid but would remain in a pool. Using NullPool ensures fresh
    connections for each operation, avoiding "another operation is in progress"
    errors when event emission follows LLM extraction.
    """
    from sqlalchemy.pool import NullPool

    database_url = settings.DATABASE_URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Use NullPool - creates fresh connections each time, avoiding event loop conflicts
    worker_engine = create_async_engine(
        database_url,
        poolclass=NullPool,  # No pooling - fresh connection per operation
        echo=settings.DB_ECHO,
        future=True,
    )

    return async_sessionmaker(
        worker_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


# Lazily-created worker session factory
_worker_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _get_worker_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the worker async session factory."""
    global _worker_async_session_factory
    if _worker_async_session_factory is None:
        _worker_async_session_factory = _create_worker_async_session_factory()
    return _worker_async_session_factory


class SyncEventStoreWrapper:
    """
    Thin wrapper over eventsource.sync.SyncEventStoreAdapter.

    Provides backward-compatible convenience methods for Celery tasks:
    - append_sync(event): Append a single event
    - append_events_sync(events): Append multiple events

    Uses the library's SyncEventStoreAdapter for proper async/sync bridging
    with timeout handling and thread safety.
    """

    def __init__(self, event_store: EventStore, timeout: float = 30.0):
        self._store = event_store
        self._adapter = SyncEventStoreAdapter(event_store, timeout=timeout)

    def append_sync(self, event: DomainEvent) -> None:
        """
        Append a single event synchronously.

        Args:
            event: The event to append
        """
        self.append_events_sync([event])

    def append_events_sync(self, events: Sequence[DomainEvent]) -> None:
        """
        Append multiple events synchronously.

        Events must have aggregate_id and aggregate_type attributes.
        Uses version 0 (no optimistic locking) for notification events.

        Args:
            events: Sequence of events to append
        """
        if not events:
            return

        # Extract aggregate info from first event
        first_event = events[0]
        aggregate_id = first_event.aggregate_id
        aggregate_type = getattr(first_event, "aggregate_type", "Unknown")

        # For notification events outside aggregate context, use version 0
        # (no optimistic locking needed)
        self._adapter.append_events_sync(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            events=list(events),
            expected_version=0,
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

    IMPORTANT: Uses an isolated session factory to avoid asyncpg connection
    state conflicts when multiple asyncio.run() calls are made in the same
    Celery worker (e.g., LLM extraction followed by event emission).

    Returns:
        SyncEventStoreWrapper: Wrapped event store with sync methods
    """
    if not settings.EVENT_STORE_ENABLED:
        logger.info("Event store disabled, using InMemoryEventStore (sync wrapper)")
        store = InMemoryEventStore(enable_tracing=True)
        return SyncEventStoreWrapper(store)

    logger.info(
        "Creating PostgreSQL event store (sync wrapper with isolated pool)",
        extra={
            "outbox_enabled": settings.EVENT_STORE_OUTBOX_ENABLED,
        },
    )

    # Use isolated worker session factory to avoid connection conflicts
    # with other async operations (like LLM extraction) in Celery workers
    worker_session_factory = _get_worker_async_session_factory()
    store = PostgreSQLEventStore(
        session_factory=worker_session_factory,
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
