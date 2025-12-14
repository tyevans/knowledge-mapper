"""
Tenant-aware repository for event-sourced aggregates.

Wraps the eventsource-py AggregateRepository to enforce tenant context
and provide multi-tenancy support.
"""

import logging
from typing import Generic, TypeVar, Optional
from uuid import UUID

from eventsource import AggregateRepository, AggregateRoot
from eventsource.stores import EventStore
from eventsource.bus import EventBus
from eventsource.snapshots import SnapshotStore

from app.core.config import settings
from app.core.context import get_current_tenant

logger = logging.getLogger(__name__)

TAggregate = TypeVar("TAggregate", bound=AggregateRoot)


class TenantAwareRepository(Generic[TAggregate]):
    """
    Repository wrapper that enforces tenant context for all operations.

    This repository ensures that:
    1. All operations have a valid tenant context
    2. Events are tagged with the correct tenant_id
    3. Aggregates can only be loaded within the correct tenant context

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
        self._event_store = event_store
        self._aggregate_factory = aggregate_factory
        self._aggregate_type = aggregate_type
        self._event_publisher = event_publisher
        self._snapshot_store = snapshot_store
        self._snapshot_threshold = snapshot_threshold or (
            settings.SNAPSHOT_THRESHOLD if settings.SNAPSHOT_ENABLED else None
        )

    def _get_repo(self) -> AggregateRepository[TAggregate]:
        """
        Get the underlying AggregateRepository.

        Creates a new repository instance each time to ensure clean state.
        """
        return AggregateRepository(
            event_store=self._event_store,
            aggregate_factory=self._aggregate_factory,
            aggregate_type=self._aggregate_type,
            event_publisher=self._event_publisher,
            snapshot_store=self._snapshot_store,
            snapshot_threshold=self._snapshot_threshold,
            enable_tracing=True,
        )

    def _get_tenant_id(self) -> UUID:
        """
        Get the current tenant ID from context.

        Raises:
            ValueError: If no tenant context is available
        """
        tenant_id = get_current_tenant()
        if tenant_id is None:
            raise ValueError(
                "Cannot access aggregate: no tenant context available. "
                "Ensure this is called within a request with tenant middleware."
            )
        return tenant_id

    def create_new(self, aggregate_id: UUID) -> TAggregate:
        """
        Create a new aggregate instance.

        The aggregate is not persisted until save() is called.
        Tenant context is validated but not applied yet - events
        created on the aggregate should use TenantDomainEvent.with_tenant_context().

        Args:
            aggregate_id: Unique ID for the new aggregate

        Returns:
            New aggregate instance

        Raises:
            ValueError: If no tenant context is available
        """
        # Validate tenant context exists
        self._get_tenant_id()
        return self._get_repo().create_new(aggregate_id)

    async def save(self, aggregate: TAggregate) -> None:
        """
        Save the aggregate's uncommitted events.

        Validates tenant context and persists all uncommitted events
        to the event store. If an event publisher is configured,
        events are also published.

        Args:
            aggregate: The aggregate to save

        Raises:
            ValueError: If no tenant context is available
            OptimisticLockError: If version conflict detected
        """
        tenant_id = self._get_tenant_id()

        # Validate all uncommitted events have the correct tenant_id
        for event in aggregate.uncommitted_events:
            if hasattr(event, "tenant_id") and event.tenant_id != tenant_id:
                raise ValueError(
                    f"Event tenant_id mismatch: expected {tenant_id}, "
                    f"got {event.tenant_id}"
                )

        await self._get_repo().save(aggregate)
        logger.debug(
            "Aggregate saved",
            extra={
                "aggregate_type": self._aggregate_type,
                "aggregate_id": str(aggregate.aggregate_id),
                "tenant_id": str(tenant_id),
                "version": aggregate.version,
            },
        )

    async def load(self, aggregate_id: UUID) -> TAggregate:
        """
        Load an aggregate by replaying its event history.

        Validates tenant context before loading. Note that this does NOT
        currently filter events by tenant_id - the assumption is that
        aggregate IDs are globally unique. For additional security,
        consider validating the loaded aggregate's events match the
        current tenant.

        Args:
            aggregate_id: ID of the aggregate to load

        Returns:
            Reconstituted aggregate

        Raises:
            ValueError: If no tenant context is available
            AggregateNotFoundError: If aggregate has no events
        """
        tenant_id = self._get_tenant_id()
        aggregate = await self._get_repo().load(aggregate_id)

        # Optional: Validate loaded aggregate belongs to current tenant
        # This provides defense-in-depth if aggregate IDs are guessable
        if aggregate.uncommitted_events:
            # Check the first event's tenant_id (all should match)
            first_event = aggregate.uncommitted_events[0]
            if hasattr(first_event, "tenant_id") and first_event.tenant_id != tenant_id:
                logger.warning(
                    "Tenant mismatch on aggregate load",
                    extra={
                        "aggregate_id": str(aggregate_id),
                        "expected_tenant": str(tenant_id),
                        "actual_tenant": str(first_event.tenant_id),
                    },
                )
                raise ValueError("Aggregate not found")

        logger.debug(
            "Aggregate loaded",
            extra={
                "aggregate_type": self._aggregate_type,
                "aggregate_id": str(aggregate_id),
                "tenant_id": str(tenant_id),
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
        self._get_tenant_id()  # Validate context
        try:
            await self.load(aggregate_id)
            return True
        except Exception:
            return False
