"""
Neo4j consolidation sync handler.

This module handles synchronizing consolidation operations
(merge, undo, split) to the Neo4j graph database.

The handler maintains consistency between PostgreSQL and Neo4j
for entity merge, undo, and split operations by:
- Transferring relationships when entities are merged
- Deleting merged nodes from the graph
- Creating restored nodes when merges are undone
- Creating split entities and redistributing relationships
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.eventsourcing.events.consolidation import (
    EntitiesMerged,
    EntitySplit,
    MergeUndone,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


class ConsolidationNeo4jSyncHandler:
    """
    Handles Neo4j synchronization for consolidation events.

    This handler maintains consistency between PostgreSQL and Neo4j
    for entity merge, undo, and split operations.

    The handler is designed to be resilient:
    - Errors are logged with full context
    - Re-raises exceptions for retry handling by caller
    - Handles missing nodes gracefully

    Example:
        >>> from neo4j import AsyncGraphDatabase
        >>> driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        >>> handler = ConsolidationNeo4jSyncHandler(driver)
        >>> await handler.handle(entities_merged_event)
    """

    def __init__(self, driver: "AsyncDriver"):
        """
        Initialize the Neo4j consolidation sync handler.

        Args:
            driver: Neo4j async driver instance
        """
        self._driver = driver

    async def handle(self, event: Any) -> None:
        """
        Route event to appropriate handler method.

        Args:
            event: Domain event to process
        """
        event_type = getattr(event, "event_type", None)
        if not event_type:
            logger.debug("Event has no event_type, skipping")
            return

        handler_name = f"_handle_{event_type}"
        handler = getattr(self, handler_name, None)

        if handler:
            try:
                await handler(event)
                logger.debug(
                    "Neo4j consolidation sync completed",
                    extra={
                        "event_type": event_type,
                        "event_id": str(getattr(event, "aggregate_id", "unknown")),
                    },
                )
            except Exception as e:
                logger.error(
                    "Neo4j consolidation sync failed: %s",
                    str(e),
                    extra={
                        "event_type": event_type,
                        "event_id": str(getattr(event, "aggregate_id", "unknown")),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )
                raise
        else:
            logger.debug(
                "No Neo4j handler for event type: %s",
                event_type,
            )

    async def _handle_EntitiesMerged(self, event: EntitiesMerged) -> None:
        """
        Sync merge operation to Neo4j.

        Operations:
        1. Transfer outgoing relationships from merged nodes to canonical
        2. Transfer incoming relationships from merged nodes to canonical
        3. Remove self-referential relationships
        4. Deduplicate relationships
        5. Delete merged nodes
        6. Update canonical node properties

        Args:
            event: EntitiesMerged event to process
        """
        canonical_id = str(event.canonical_entity_id)
        merged_ids = [str(eid) for eid in event.merged_entity_ids]
        tenant_id = str(event.tenant_id)

        async with self._driver.session() as session:
            # Step 1: Transfer outgoing relationships from merged to canonical
            # Using APOC for dynamic relationship type creation
            transfer_outgoing_query = """
            UNWIND $merged_ids AS merged_id
            MATCH (merged:Entity {id: merged_id, tenant_id: $tenant_id})-[r]->(target)
            WHERE target.id <> $canonical_id
            WITH merged, r, target, type(r) AS rel_type, properties(r) AS rel_props
            MATCH (canonical:Entity {id: $canonical_id, tenant_id: $tenant_id})

            // Create new relationship (using generic RELATED_TO as fallback)
            CREATE (canonical)-[new_r:RELATED_TO]->(target)
            SET new_r = rel_props
            SET new_r.original_type = rel_type
            SET new_r.transferred_from = merged.id
            SET new_r.transferred_at = datetime()

            DELETE r
            RETURN count(new_r) AS transferred
            """

            try:
                await session.run(
                    transfer_outgoing_query,
                    canonical_id=canonical_id,
                    merged_ids=merged_ids,
                    tenant_id=tenant_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to transfer outgoing relationships: %s",
                    str(e),
                    extra={"canonical_id": canonical_id},
                )

            # Step 2: Transfer incoming relationships
            transfer_incoming_query = """
            UNWIND $merged_ids AS merged_id
            MATCH (source)-[r]->(merged:Entity {id: merged_id, tenant_id: $tenant_id})
            WHERE source.id <> $canonical_id
            WITH source, r, merged, type(r) AS rel_type, properties(r) AS rel_props
            MATCH (canonical:Entity {id: $canonical_id, tenant_id: $tenant_id})

            CREATE (source)-[new_r:RELATED_TO]->(canonical)
            SET new_r = rel_props
            SET new_r.original_type = rel_type
            SET new_r.transferred_from = merged.id
            SET new_r.transferred_at = datetime()

            DELETE r
            RETURN count(new_r) AS transferred
            """

            try:
                await session.run(
                    transfer_incoming_query,
                    canonical_id=canonical_id,
                    merged_ids=merged_ids,
                    tenant_id=tenant_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to transfer incoming relationships: %s",
                    str(e),
                    extra={"canonical_id": canonical_id},
                )

            # Step 3: Remove self-referential relationships
            remove_self_refs_query = """
            MATCH (e:Entity {id: $canonical_id, tenant_id: $tenant_id})-[r]->(e)
            DELETE r
            RETURN count(r) AS deleted
            """

            await session.run(
                remove_self_refs_query,
                canonical_id=canonical_id,
                tenant_id=tenant_id,
            )

            # Step 4: Deduplicate relationships (keep highest confidence)
            dedup_query = """
            MATCH (canonical:Entity {id: $canonical_id, tenant_id: $tenant_id})-[r]->(target)
            WITH canonical, target, type(r) AS rel_type, collect(r) AS rels
            WHERE size(rels) > 1
            WITH rels, reduce(best = head(rels), r IN tail(rels) |
                CASE WHEN coalesce(r.confidence_score, 0) > coalesce(best.confidence_score, 0)
                THEN r ELSE best END
            ) AS keeper
            FOREACH (r IN [rel IN rels WHERE rel <> keeper] | DELETE r)
            RETURN count(*) AS deduplicated
            """

            await session.run(
                dedup_query,
                canonical_id=canonical_id,
                tenant_id=tenant_id,
            )

            # Step 5: Delete merged nodes
            delete_merged_query = """
            UNWIND $merged_ids AS merged_id
            MATCH (merged:Entity {id: merged_id, tenant_id: $tenant_id})
            DETACH DELETE merged
            RETURN count(merged) AS deleted
            """

            await session.run(
                delete_merged_query,
                merged_ids=merged_ids,
                tenant_id=tenant_id,
            )

            # Step 6: Update canonical node properties
            property_merge_details = event.property_merge_details or {}
            merged_names = property_merge_details.get("merged_names", [])

            update_canonical_query = """
            MATCH (e:Entity {id: $canonical_id, tenant_id: $tenant_id})
            SET e.aliases = coalesce(e.aliases, []) + $merged_names
            SET e.merged_count = coalesce(e.merged_count, 0) + $merge_count
            SET e.last_merged_at = datetime()
            SET e.merge_event_id = $merge_event_id
            RETURN e.id AS updated
            """

            await session.run(
                update_canonical_query,
                canonical_id=canonical_id,
                tenant_id=tenant_id,
                merged_names=merged_names,
                merge_count=len(merged_ids),
                merge_event_id=str(event.aggregate_id),
            )

        logger.info(
            "Neo4j sync completed for EntitiesMerged",
            extra={
                "canonical_id": canonical_id,
                "merged_count": len(merged_ids),
                "tenant_id": tenant_id,
            },
        )

    async def _handle_MergeUndone(self, event: MergeUndone) -> None:
        """
        Sync undo operation to Neo4j.

        Operations:
        1. Create placeholder nodes for restored entities
        2. Update canonical node with undo metadata

        Note: Full node properties should be synced via the regular
        entity sync handler when the restored entities are created
        in PostgreSQL.

        Args:
            event: MergeUndone event to process
        """
        canonical_id = str(event.canonical_entity_id)
        restored_ids = [str(eid) for eid in event.restored_entity_ids]
        tenant_id = str(event.tenant_id)

        async with self._driver.session() as session:
            # Step 1: Create placeholder nodes for restored entities
            # These will be fully populated by the entity sync handler
            create_restored_query = """
            UNWIND $restored_ids AS restored_id
            MERGE (e:Entity {id: restored_id, tenant_id: $tenant_id})
            ON CREATE SET
                e.created_at = datetime(),
                e.restored_from_merge = true,
                e.restored_at = datetime(),
                e.undo_event_id = $undo_event_id
            RETURN count(e) AS created
            """

            await session.run(
                create_restored_query,
                restored_ids=restored_ids,
                tenant_id=tenant_id,
                undo_event_id=str(event.aggregate_id),
            )

            # Step 2: Update canonical node with undo metadata
            update_canonical_query = """
            MATCH (e:Entity {id: $canonical_id, tenant_id: $tenant_id})
            SET e.undo_count = coalesce(e.undo_count, 0) + 1
            SET e.last_undo_at = datetime()
            SET e.last_undo_event_id = $undo_event_id
            RETURN e.id AS updated
            """

            await session.run(
                update_canonical_query,
                canonical_id=canonical_id,
                tenant_id=tenant_id,
                undo_event_id=str(event.aggregate_id),
            )

        logger.info(
            "Neo4j sync completed for MergeUndone",
            extra={
                "canonical_id": canonical_id,
                "restored_count": len(restored_ids),
                "tenant_id": tenant_id,
            },
        )

    async def _handle_EntitySplit(self, event: EntitySplit) -> None:
        """
        Sync split operation to Neo4j.

        Operations:
        1. Create nodes for new split entities
        2. Transfer relationships based on assignments
        3. Mark original node as split

        Note: Relationship redistribution follows the assignments
        from the event. Relationships not explicitly assigned go
        to the first new entity.

        Args:
            event: EntitySplit event to process
        """
        original_id = str(event.original_entity_id)
        new_ids = [str(eid) for eid in event.new_entity_ids]
        new_names = event.new_entity_names
        tenant_id = str(event.tenant_id)
        relationship_assignments = event.relationship_assignments or {}

        async with self._driver.session() as session:
            # Step 1: Create new entity nodes
            for i, (new_id, new_name) in enumerate(zip(new_ids, new_names, strict=False)):
                create_node_query = """
                MERGE (e:Entity {id: $new_id, tenant_id: $tenant_id})
                ON CREATE SET
                    e.name = $name,
                    e.created_at = datetime(),
                    e.split_from = $original_id,
                    e.split_index = $index,
                    e.split_event_id = $split_event_id
                RETURN e.id AS created
                """

                await session.run(
                    create_node_query,
                    new_id=new_id,
                    tenant_id=tenant_id,
                    name=new_name,
                    original_id=original_id,
                    index=i,
                    split_event_id=str(event.aggregate_id),
                )

            # Step 2: Transfer relationships based on assignments
            # For relationships with explicit assignments
            if relationship_assignments:
                for rel_id_str, target_entity_id_str in relationship_assignments.items():
                    # Transfer outgoing relationships
                    transfer_out_query = """
                    MATCH (original:Entity {id: $original_id, tenant_id: $tenant_id})-[r]->(target)
                    WHERE r.pg_id = $rel_id OR toString(id(r)) = $rel_id
                    MATCH (new_entity:Entity {id: $new_entity_id, tenant_id: $tenant_id})
                    WITH r, target, new_entity, type(r) AS rel_type, properties(r) AS props
                    CREATE (new_entity)-[new_r:RELATED_TO]->(target)
                    SET new_r = props
                    SET new_r.original_type = rel_type
                    SET new_r.split_from = $original_id
                    DELETE r
                    RETURN count(new_r) AS transferred
                    """

                    await session.run(
                        transfer_out_query,
                        original_id=original_id,
                        tenant_id=tenant_id,
                        rel_id=rel_id_str,
                        new_entity_id=target_entity_id_str,
                    )

                    # Transfer incoming relationships
                    transfer_in_query = """
                    MATCH (source)-[r]->(original:Entity {id: $original_id, tenant_id: $tenant_id})
                    WHERE r.pg_id = $rel_id OR toString(id(r)) = $rel_id
                    MATCH (new_entity:Entity {id: $new_entity_id, tenant_id: $tenant_id})
                    WITH source, r, new_entity, type(r) AS rel_type, properties(r) AS props
                    CREATE (source)-[new_r:RELATED_TO]->(new_entity)
                    SET new_r = props
                    SET new_r.original_type = rel_type
                    SET new_r.split_from = $original_id
                    DELETE r
                    RETURN count(new_r) AS transferred
                    """

                    await session.run(
                        transfer_in_query,
                        original_id=original_id,
                        tenant_id=tenant_id,
                        rel_id=rel_id_str,
                        new_entity_id=target_entity_id_str,
                    )

            # Transfer any remaining unassigned relationships to first new entity
            if new_ids:
                first_new_id = new_ids[0]

                # Remaining outgoing
                transfer_remaining_out_query = """
                MATCH (original:Entity {id: $original_id, tenant_id: $tenant_id})-[r]->(target)
                MATCH (new_entity:Entity {id: $first_new_id, tenant_id: $tenant_id})
                WITH r, target, new_entity, type(r) AS rel_type, properties(r) AS props
                CREATE (new_entity)-[new_r:RELATED_TO]->(target)
                SET new_r = props
                SET new_r.original_type = rel_type
                SET new_r.split_from = $original_id
                DELETE r
                RETURN count(new_r) AS transferred
                """

                await session.run(
                    transfer_remaining_out_query,
                    original_id=original_id,
                    tenant_id=tenant_id,
                    first_new_id=first_new_id,
                )

                # Remaining incoming
                transfer_remaining_in_query = """
                MATCH (source)-[r]->(original:Entity {id: $original_id, tenant_id: $tenant_id})
                MATCH (new_entity:Entity {id: $first_new_id, tenant_id: $tenant_id})
                WITH source, r, new_entity, type(r) AS rel_type, properties(r) AS props
                CREATE (source)-[new_r:RELATED_TO]->(new_entity)
                SET new_r = props
                SET new_r.original_type = rel_type
                SET new_r.split_from = $original_id
                DELETE r
                RETURN count(new_r) AS transferred
                """

                await session.run(
                    transfer_remaining_in_query,
                    original_id=original_id,
                    tenant_id=tenant_id,
                    first_new_id=first_new_id,
                )

            # Step 3: Mark original node as split
            mark_split_query = """
            MATCH (e:Entity {id: $original_id, tenant_id: $tenant_id})
            SET e.is_split = true
            SET e.split_into = $new_ids
            SET e.split_at = datetime()
            SET e.split_event_id = $split_event_id
            SET e.split_reason = $split_reason
            RETURN e.id AS updated
            """

            await session.run(
                mark_split_query,
                original_id=original_id,
                tenant_id=tenant_id,
                new_ids=new_ids,
                split_event_id=str(event.aggregate_id),
                split_reason=event.split_reason,
            )

        logger.info(
            "Neo4j sync completed for EntitySplit",
            extra={
                "original_id": original_id,
                "new_entity_count": len(new_ids),
                "tenant_id": tenant_id,
            },
        )


__all__ = ["ConsolidationNeo4jSyncHandler"]
