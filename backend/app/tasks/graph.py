"""
Celery tasks for Neo4j knowledge graph operations.

This module provides tasks for:
- Syncing entities to Neo4j
- Syncing relationships to Neo4j
- Batch synchronization
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from celery import shared_task
from sqlalchemy import select, update

from app.worker.context import TenantWorkerContext
from app.models.extracted_entity import ExtractedEntity, EntityRelationship
from app.eventsourcing.events.scraping import (
    EntitySyncedToNeo4j,
    RelationshipSyncedToNeo4j,
    Neo4jSyncFailed,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="app.tasks.graph.sync_entity_to_neo4j",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def sync_entity_to_neo4j(self, entity_id: str, tenant_id: str) -> dict:
    """
    Sync a single entity to Neo4j.

    This task:
    1. Loads entity from the database
    2. Creates/updates node in Neo4j
    3. Updates sync status in PostgreSQL
    4. Emits domain events

    Args:
        entity_id: UUID of the entity
        tenant_id: UUID of the tenant

    Returns:
        dict: Sync summary
    """
    logger.info(
        "Syncing entity to Neo4j",
        extra={"entity_id": entity_id, "tenant_id": tenant_id},
    )

    with TenantWorkerContext(tenant_id) as ctx:
        # Load entity
        result = ctx.db.execute(
            select(ExtractedEntity).where(ExtractedEntity.id == UUID(entity_id))
        )
        entity = result.scalar_one_or_none()

        if not entity:
            logger.error(f"Entity not found: {entity_id}")
            return {"status": "error", "message": "Entity not found"}

        # Check if already synced
        if entity.synced_to_neo4j:
            logger.info(f"Entity already synced: {entity_id}")
            return {"status": "skipped", "message": "Already synced"}

        try:
            # Import graph client
            from app.graph.client import get_neo4j_client

            neo4j_client = get_neo4j_client()

            # Create/update node in Neo4j
            neo4j_node_id = neo4j_client.sync_entity(entity)

            # Update entity with Neo4j node ID
            entity.neo4j_node_id = neo4j_node_id
            entity.synced_to_neo4j = True
            entity.synced_at = datetime.now(timezone.utc)
            entity.updated_at = datetime.now(timezone.utc)
            ctx.db.commit()

            # Emit success event
            _emit_entity_synced_event(entity, tenant_id, neo4j_node_id)

            logger.info(
                "Entity synced to Neo4j",
                extra={
                    "entity_id": entity_id,
                    "neo4j_node_id": neo4j_node_id,
                },
            )

            return {
                "status": "completed",
                "entity_id": entity_id,
                "neo4j_node_id": neo4j_node_id,
            }

        except Exception as e:
            logger.exception(
                "Failed to sync entity to Neo4j",
                extra={"entity_id": entity_id, "error": str(e)},
            )

            # Emit failed event
            _emit_sync_failed_event(
                tenant_id,
                entity_id=UUID(entity_id),
                relationship_id=None,
                error=e,
            )

            # Retry if appropriate
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)

            return {"status": "failed", "error": str(e)}


@shared_task(
    bind=True,
    name="app.tasks.graph.sync_relationship_to_neo4j",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def sync_relationship_to_neo4j(self, relationship_id: str, tenant_id: str) -> dict:
    """
    Sync a single relationship to Neo4j.

    Args:
        relationship_id: UUID of the relationship
        tenant_id: UUID of the tenant

    Returns:
        dict: Sync summary
    """
    logger.info(
        "Syncing relationship to Neo4j",
        extra={"relationship_id": relationship_id, "tenant_id": tenant_id},
    )

    with TenantWorkerContext(tenant_id) as ctx:
        # Load relationship
        result = ctx.db.execute(
            select(EntityRelationship).where(
                EntityRelationship.id == UUID(relationship_id)
            )
        )
        relationship = result.scalar_one_or_none()

        if not relationship:
            logger.error(f"Relationship not found: {relationship_id}")
            return {"status": "error", "message": "Relationship not found"}

        # Check if already synced
        if relationship.synced_to_neo4j:
            logger.info(f"Relationship already synced: {relationship_id}")
            return {"status": "skipped", "message": "Already synced"}

        # Ensure both entities are synced first
        source_result = ctx.db.execute(
            select(ExtractedEntity).where(
                ExtractedEntity.id == relationship.source_entity_id
            )
        )
        source_entity = source_result.scalar_one_or_none()

        target_result = ctx.db.execute(
            select(ExtractedEntity).where(
                ExtractedEntity.id == relationship.target_entity_id
            )
        )
        target_entity = target_result.scalar_one_or_none()

        if not source_entity or not target_entity:
            logger.error(
                "Source or target entity not found for relationship",
                extra={
                    "relationship_id": relationship_id,
                    "source_id": str(relationship.source_entity_id),
                    "target_id": str(relationship.target_entity_id),
                },
            )
            return {"status": "error", "message": "Entity not found"}

        # Sync entities first if needed
        if not source_entity.synced_to_neo4j:
            sync_entity_to_neo4j.delay(str(source_entity.id), tenant_id)
            return {"status": "pending", "message": "Source entity sync queued"}

        if not target_entity.synced_to_neo4j:
            sync_entity_to_neo4j.delay(str(target_entity.id), tenant_id)
            return {"status": "pending", "message": "Target entity sync queued"}

        try:
            # Import graph client
            from app.graph.client import get_neo4j_client

            neo4j_client = get_neo4j_client()

            # Create relationship in Neo4j
            neo4j_rel_id = neo4j_client.sync_relationship(
                relationship,
                source_entity.neo4j_node_id,
                target_entity.neo4j_node_id,
            )

            # Update relationship
            relationship.neo4j_relationship_id = neo4j_rel_id
            relationship.synced_to_neo4j = True
            relationship.updated_at = datetime.now(timezone.utc)
            ctx.db.commit()

            # Emit success event
            _emit_relationship_synced_event(relationship, tenant_id, neo4j_rel_id)

            logger.info(
                "Relationship synced to Neo4j",
                extra={
                    "relationship_id": relationship_id,
                    "neo4j_rel_id": neo4j_rel_id,
                },
            )

            return {
                "status": "completed",
                "relationship_id": relationship_id,
                "neo4j_rel_id": neo4j_rel_id,
            }

        except Exception as e:
            logger.exception(
                "Failed to sync relationship to Neo4j",
                extra={"relationship_id": relationship_id, "error": str(e)},
            )

            # Emit failed event
            _emit_sync_failed_event(
                tenant_id,
                entity_id=None,
                relationship_id=UUID(relationship_id),
                error=e,
            )

            # Retry if appropriate
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)

            return {"status": "failed", "error": str(e)}


@shared_task(
    name="app.tasks.graph.sync_pending_entities",
    acks_late=True,
)
def sync_pending_entities(batch_size: int = 100) -> dict:
    """
    Sync all pending entities to Neo4j.

    This periodic task finds entities that haven't been synced
    to Neo4j and queues them for synchronization.

    Args:
        batch_size: Maximum entities to process per run

    Returns:
        dict: Sync summary
    """
    from app.core.database import SyncSessionLocal

    logger.info("Starting pending entity sync")

    queued = 0

    with SyncSessionLocal() as db:
        try:
            # Find entities not yet synced
            result = db.execute(
                select(ExtractedEntity)
                .where(ExtractedEntity.synced_to_neo4j == False)  # noqa: E712
                .limit(batch_size)
            )
            entities = result.scalars().all()

            for entity in entities:
                sync_entity_to_neo4j.delay(
                    str(entity.id),
                    str(entity.tenant_id),
                )
                queued += 1

        except Exception as e:
            logger.exception("Failed to queue pending entities")
            raise

    logger.info(f"Queued {queued} entities for Neo4j sync")
    return {"queued": queued}


@shared_task(
    name="app.tasks.graph.sync_pending_relationships",
    acks_late=True,
)
def sync_pending_relationships(batch_size: int = 100) -> dict:
    """
    Sync all pending relationships to Neo4j.

    Args:
        batch_size: Maximum relationships to process per run

    Returns:
        dict: Sync summary
    """
    from app.core.database import SyncSessionLocal

    logger.info("Starting pending relationship sync")

    queued = 0

    with SyncSessionLocal() as db:
        try:
            # Find relationships not yet synced
            result = db.execute(
                select(EntityRelationship)
                .where(EntityRelationship.synced_to_neo4j == False)  # noqa: E712
                .limit(batch_size)
            )
            relationships = result.scalars().all()

            for rel in relationships:
                sync_relationship_to_neo4j.delay(
                    str(rel.id),
                    str(rel.tenant_id),
                )
                queued += 1

        except Exception as e:
            logger.exception("Failed to queue pending relationships")
            raise

    logger.info(f"Queued {queued} relationships for Neo4j sync")
    return {"queued": queued}


def _emit_entity_synced_event(
    entity: ExtractedEntity,
    tenant_id: str,
    neo4j_node_id: str,
) -> None:
    """Emit EntitySyncedToNeo4j event."""
    try:
        from app.eventsourcing.stores.factory import get_event_store_sync
        event_store = get_event_store_sync()
        event = EntitySyncedToNeo4j(
            aggregate_id=str(entity.id),
            tenant_id=tenant_id,
            entity_id=entity.id,
            neo4j_node_id=neo4j_node_id,
            synced_at=datetime.now(timezone.utc),
        )
        event_store.append_sync(event)
    except Exception as e:
        logger.warning(f"Failed to emit EntitySyncedToNeo4j event: {e}")


def _emit_relationship_synced_event(
    relationship: EntityRelationship,
    tenant_id: str,
    neo4j_rel_id: str,
) -> None:
    """Emit RelationshipSyncedToNeo4j event."""
    try:
        from app.eventsourcing.stores.factory import get_event_store_sync
        event_store = get_event_store_sync()
        event = RelationshipSyncedToNeo4j(
            aggregate_id=str(relationship.id),
            tenant_id=tenant_id,
            relationship_id=relationship.id,
            neo4j_relationship_id=neo4j_rel_id,
            synced_at=datetime.now(timezone.utc),
        )
        event_store.append_sync(event)
    except Exception as e:
        logger.warning(f"Failed to emit RelationshipSyncedToNeo4j event: {e}")


def _emit_sync_failed_event(
    tenant_id: str,
    entity_id: UUID | None,
    relationship_id: UUID | None,
    error: Exception,
) -> None:
    """Emit Neo4jSyncFailed event."""
    try:
        from app.eventsourcing.stores.factory import get_event_store_sync
        event_store = get_event_store_sync()
        aggregate_id = str(entity_id or relationship_id or "unknown")
        event = Neo4jSyncFailed(
            aggregate_id=aggregate_id,
            tenant_id=tenant_id,
            entity_id=entity_id,
            relationship_id=relationship_id,
            error_message=str(error),
            failed_at=datetime.now(timezone.utc),
        )
        event_store.append_sync(event)
    except Exception as e:
        logger.warning(f"Failed to emit Neo4jSyncFailed event: {e}")
