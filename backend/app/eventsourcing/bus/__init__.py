"""Event bus factory and configuration."""

from app.eventsourcing.bus.factory import get_kafka_bus, create_tenant_kafka_bus

__all__ = ["get_kafka_bus", "create_tenant_kafka_bus"]
