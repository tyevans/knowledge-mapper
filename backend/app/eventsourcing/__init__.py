"""
Event Sourcing module for Knowledge Mapper.

Integrates eventsource-py library with multi-tenant support and Kafka event bus.

Usage:
    from app.eventsourcing import (
        TenantDomainEvent,
        get_event_store,
        get_event_store_sync,
        get_kafka_bus,
        TenantAwareRepository,
    )
"""

from app.eventsourcing.events.base import TenantDomainEvent
from app.eventsourcing.stores.factory import get_event_store, get_event_store_sync
from app.eventsourcing.bus.factory import get_kafka_bus, create_tenant_kafka_bus
from app.eventsourcing.repositories.base import TenantAwareRepository

__all__ = [
    "TenantDomainEvent",
    "get_event_store",
    "get_event_store_sync",
    "get_kafka_bus",
    "create_tenant_kafka_bus",
    "TenantAwareRepository",
]
