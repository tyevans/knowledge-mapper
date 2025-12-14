"""
Kafka event bus factory for Knowledge Mapper.

Provides Kafka bus instances with tenant-aware topic prefixing for
proper event isolation in multi-tenant deployments.
"""

import logging
from typing import Optional
from uuid import UUID

from eventsource import KafkaEventBus, InMemoryEventBus
from eventsource.bus import EventBus
from eventsource.bus.kafka import KafkaEventBusConfig
from eventsource.events import default_registry

from app.core.config import settings

logger = logging.getLogger(__name__)

# Singleton instance for the main bus (used for outbox publishing)
_kafka_bus: Optional[EventBus] = None


def create_kafka_config(tenant_id: Optional[UUID] = None) -> KafkaEventBusConfig:
    """
    Create Kafka configuration with optional tenant-specific topic prefix.

    When tenant_id is provided, topics will be prefixed with the tenant ID
    to ensure event isolation: events.tenant-{tenant_id}.{aggregate_type}

    Args:
        tenant_id: Optional tenant ID for topic prefixing

    Returns:
        KafkaEventBusConfig: Configuration for KafkaEventBus
    """
    topic_prefix = settings.KAFKA_TOPIC_PREFIX
    if tenant_id:
        topic_prefix = f"{topic_prefix}.tenant-{tenant_id}"

    return KafkaEventBusConfig(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic_prefix=topic_prefix,
        consumer_group=settings.KAFKA_CONSUMER_GROUP,
        # Producer settings
        acks=settings.KAFKA_ACKS,
        compression_type=settings.KAFKA_COMPRESSION_TYPE,
        batch_size=settings.KAFKA_BATCH_SIZE,
        linger_ms=settings.KAFKA_LINGER_MS,
        # Consumer settings
        auto_offset_reset=settings.KAFKA_AUTO_OFFSET_RESET,
        session_timeout_ms=settings.KAFKA_SESSION_TIMEOUT_MS,
        heartbeat_interval_ms=settings.KAFKA_HEARTBEAT_INTERVAL_MS,
        # Observability
        enable_tracing=True,
        enable_metrics=True,
    )


async def create_kafka_bus(tenant_id: Optional[UUID] = None) -> EventBus:
    """
    Create a new Kafka bus instance.

    Falls back to InMemoryEventBus if Kafka is disabled.

    Args:
        tenant_id: Optional tenant ID for topic prefixing

    Returns:
        EventBus: Connected Kafka or in-memory bus
    """
    if not settings.KAFKA_ENABLED:
        logger.info("Kafka disabled, using InMemoryEventBus")
        return InMemoryEventBus(enable_tracing=True)

    config = create_kafka_config(tenant_id)
    bus = KafkaEventBus(config=config, event_registry=default_registry)

    try:
        await bus.connect()
        logger.info(
            "Kafka bus connected",
            extra={
                "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "topic_prefix": config.topic_prefix,
                "consumer_group": config.consumer_group,
            },
        )
    except Exception as e:
        logger.error(
            "Failed to connect to Kafka",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise

    return bus


async def create_tenant_kafka_bus(tenant_id: UUID) -> EventBus:
    """
    Create a Kafka bus instance for a specific tenant.

    Topics will be prefixed with the tenant ID for isolation.

    Args:
        tenant_id: Tenant ID for topic prefixing

    Returns:
        EventBus: Connected Kafka bus with tenant-specific topics
    """
    return await create_kafka_bus(tenant_id=tenant_id)


async def get_kafka_bus() -> EventBus:
    """
    Get the singleton Kafka bus instance (without tenant prefix).

    Used by the outbox publisher to send events to tenant-specific topics.
    The publisher routes events to the correct topic based on event.tenant_id.

    Returns:
        EventBus: The application's main Kafka bus
    """
    global _kafka_bus
    if _kafka_bus is None:
        _kafka_bus = await create_kafka_bus()
    return _kafka_bus


async def close_kafka_bus() -> None:
    """
    Close the Kafka bus and release resources.

    Should be called during application shutdown.
    """
    global _kafka_bus
    if _kafka_bus is not None:
        try:
            if isinstance(_kafka_bus, KafkaEventBus):
                await _kafka_bus.disconnect()
            logger.info("Kafka bus disconnected")
        except Exception as e:
            logger.warning(
                "Error disconnecting Kafka bus",
                extra={"error": str(e)},
            )
        finally:
            _kafka_bus = None
