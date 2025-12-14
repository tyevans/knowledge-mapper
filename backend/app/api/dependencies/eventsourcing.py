"""
FastAPI dependencies for event sourcing.

Provides dependency injection for event store and event bus
instances within request handlers.
"""

from typing import Annotated, AsyncGenerator

from fastapi import Depends

from eventsource.stores import EventStore
from eventsource.bus import EventBus

from app.api.dependencies.auth import get_current_user, AuthenticatedUser
from app.eventsourcing.stores.factory import get_event_store as _get_event_store
from app.eventsourcing.bus.factory import (
    get_kafka_bus as _get_kafka_bus,
    create_tenant_kafka_bus,
)


async def get_event_store() -> EventStore:
    """
    Dependency to get the event store.

    Returns the singleton event store instance.

    Example:
        @router.post("/statements")
        async def create_statement(
            statement: StatementCreate,
            store: EventStoreDep,
        ):
            # Use store to append events
            ...
    """
    return await _get_event_store()


async def get_kafka_bus() -> EventBus:
    """
    Dependency to get the main Kafka bus (without tenant prefix).

    Used primarily for internal operations like outbox publishing.

    Example:
        @router.post("/admin/replay")
        async def replay_events(
            bus: KafkaBusDep,
        ):
            # Use bus to publish events
            ...
    """
    return await _get_kafka_bus()


async def get_tenant_kafka_bus(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)]
) -> AsyncGenerator[EventBus, None]:
    """
    Dependency to get a tenant-specific Kafka bus.

    Creates a Kafka bus with tenant-prefixed topics based on the
    authenticated user's tenant_id. This ensures events are published
    to the correct tenant-specific topics.

    Example:
        @router.post("/statements")
        async def create_statement(
            statement: StatementCreate,
            bus: TenantKafkaBusDep,
        ):
            # Events go to events.tenant-{tenant_id}.Statement
            await bus.publish([event])
    """
    bus = await create_tenant_kafka_bus(user.tenant_id)
    try:
        yield bus
    finally:
        # Tenant-specific buses should be closed after request
        if hasattr(bus, "disconnect"):
            await bus.disconnect()


# Type aliases for cleaner dependency injection
EventStoreDep = Annotated[EventStore, Depends(get_event_store)]
KafkaBusDep = Annotated[EventBus, Depends(get_kafka_bus)]
TenantKafkaBusDep = Annotated[EventBus, Depends(get_tenant_kafka_bus)]
