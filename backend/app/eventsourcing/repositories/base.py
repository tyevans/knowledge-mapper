"""
Tenant-aware repository for event-sourced aggregates.

Provides a backward-compatible facade over eventsource.multitenancy.TenantAwareRepository.
"""

import logging
from typing import Generic, TypeVar, Optional
from uuid import UUID

from eventsource import AggregateRepository, AggregateRoot
from eventsource.stores import EventStore
from eventsource.bus import EventBus
from eventsource.snapshots import SnapshotStore
from eventsource.multitenancy import TenantAwareRepository as BaseTenantAwareRepository

from app.core.config import settings

logger = logging.getLogger(__name__)

TAggregate = TypeVar("TAggregate", bound=AggregateRoot)


class TenantAwareRepository(Generic[TAggregate]):
    """
    Backward-compatible facade over eventsource.multitenancy.TenantAwareRepository.

    Maintains the same constructor signature as before while delegating to
    the library's implementation for tenant validation. This ensures existing
    code continues to work without modification.

    Example:
        # Create repository for Statement aggregates
        repo = TenantAwareRepository(
            event_store=event_store,
            aggregate_factory=StatementAggregate,
            aggregate_type="Statement",
        )

        # Within a request handler (tenant context set by middleware)
        statement = repo.create_new(statement_id)
        statement.create(content="Hello world")
        await repo.save(statement)

        # Later, load the statement
        loaded = await repo.load(statement_id)
    """

    def __init__(
        self,
        event_store: EventStore,
        aggregate_factory: type[TAggregate],
        aggregate_type: str,
        event_publisher: Optional[EventBus] = None,
        snapshot_store: Optional[SnapshotStore] = None,
        snapshot_threshold: Optional[int] = None,
    ):
        """
        Initialize the tenant-aware repository.

        Args:
            event_store: Event store for persistence
            aggregate_factory: Class to instantiate when loading aggregates
            aggregate_type: Type name for the aggregate (e.g., "Statement")
            event_publisher: Optional event bus for publishing events
            snapshot_store: Optional snapshot store for performance
            snapshot_threshold: Events between automatic snapshots
        """
        # Resolve snapshot threshold from settings if enabled
        resolved_threshold = snapshot_threshold or (
            settings.SNAPSHOT_THRESHOLD if settings.SNAPSHOT_ENABLED else None
        )

        # Create the underlying AggregateRepository
        underlying_repo = AggregateRepository(
            event_store=event_store,
            aggregate_factory=aggregate_factory,
            aggregate_type=aggregate_type,
            event_publisher=event_publisher,
            snapshot_store=snapshot_store,
            snapshot_threshold=resolved_threshold,
            enable_tracing=True,
        )

        # Wrap with library's TenantAwareRepository
        # enforce_on_load=False because knowledge-mapper uses PostgreSQL RLS for isolation
        # validate_on_save=True to ensure events have correct tenant_id
        self._wrapper = BaseTenantAwareRepository(
            underlying_repo,
            enforce_on_load=False,
            validate_on_save=True,
        )

        # Store for property access
        self._aggregate_type = aggregate_type

    @property
    def aggregate_type(self) -> str:
        """Get the aggregate type name."""
        return self._aggregate_type

    def create_new(self, aggregate_id: UUID) -> TAggregate:
        """
        Create a new aggregate instance.

        The aggregate is not persisted until save() is called.
        Events created on the aggregate should use TenantDomainEvent.with_tenant_context().

        Args:
            aggregate_id: Unique ID for the new aggregate

        Returns:
            New aggregate instance
        """
        return self._wrapper.create_new(aggregate_id)

    async def save(self, aggregate: TAggregate) -> None:
        """
        Save the aggregate's uncommitted events.

        Validates tenant context and persists all uncommitted events
        to the event store. If an event publisher is configured,
        events are also published.

        Args:
            aggregate: The aggregate to save

        Raises:
            TenantContextNotSetError: If no tenant context is available
            TenantMismatchError: If any event has wrong tenant_id
            OptimisticLockError: If version conflict detected
        """
        await self._wrapper.save(aggregate)
        logger.debug(
            "Aggregate saved",
            extra={
                "aggregate_type": self._aggregate_type,
                "aggregate_id": str(aggregate.aggregate_id),
                "version": aggregate.version,
            },
        )

    async def load(self, aggregate_id: UUID) -> TAggregate:
        """
        Load an aggregate by replaying its event history.

        Args:
            aggregate_id: ID of the aggregate to load

        Returns:
            Reconstituted aggregate

        Raises:
            AggregateNotFoundError: If aggregate has no events
        """
        aggregate = await self._wrapper.load(aggregate_id)
        logger.debug(
            "Aggregate loaded",
            extra={
                "aggregate_type": self._aggregate_type,
                "aggregate_id": str(aggregate_id),
                "version": aggregate.version,
            },
        )
        return aggregate

    async def exists(self, aggregate_id: UUID) -> bool:
        """
        Check if an aggregate exists.

        Args:
            aggregate_id: ID of the aggregate to check

        Returns:
            True if aggregate exists, False otherwise
        """
        return await self._wrapper.exists(aggregate_id)

    async def load_or_create(self, aggregate_id: UUID) -> TAggregate:
        """
        Load an existing aggregate or create a new one.

        Args:
            aggregate_id: ID of the aggregate

        Returns:
            Existing aggregate if found, or new empty aggregate
        """
        return await self._wrapper.load_or_create(aggregate_id)
