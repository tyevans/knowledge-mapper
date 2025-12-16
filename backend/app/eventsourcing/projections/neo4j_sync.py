"""
Neo4j sync handlers for graph database synchronization.

This module provides projection handlers that sync extracted entities
to Neo4j for knowledge graph construction. Handlers listen to domain
events and create corresponding nodes in the graph database.

The sync is designed to be resilient:
- Errors are logged but don't block event processing
- Failed syncs can be retried later via compensation processes
- PostgreSQL tracks sync status for monitoring and retry logic
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from eventsource import DatabaseProjection, handles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.eventsourcing.events.extraction import RelationshipDiscovered
from app.eventsourcing.events.scraping import EntityExtracted
from app.services.neo4j import get_neo4j_service

if TYPE_CHECKING:
    from eventsource.repositories import CheckpointRepository, DLQRepository

logger = logging.getLogger(__name__)


class Neo4jEntitySyncHandler(DatabaseProjection):
    """
    Syncs EntityExtracted events to Neo4j graph database.

    Creates or updates entity nodes in Neo4j when entities are extracted.
    After successful sync, updates the PostgreSQL record with the Neo4j
    node ID for tracking and future reference.

    The handler is designed to be resilient:
    - Neo4j failures are logged but don't raise exceptions
    - PostgreSQL updates only happen on successful Neo4j sync
    - Failed syncs can be identified via synced_to_neo4j=False

    Example:
        >>> from sqlalchemy.ext.asyncio import async_sessionmaker
        >>> session_factory = async_sessionmaker(engine, expire_on_commit=False)
        >>> handler = Neo4jEntitySyncHandler(session_factory=session_factory)
        >>> await handler.handle(entity_extracted_event)
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        checkpoint_repo: "CheckpointRepository | None" = None,
        dlq_repo: "DLQRepository | None" = None,
        enable_tracing: bool = False,
    ) -> None:
        """
        Initialize the Neo4j entity sync handler.

        Args:
            session_factory: SQLAlchemy async session factory for PostgreSQL updates
            checkpoint_repo: Optional checkpoint repository for tracking position
            dlq_repo: Optional DLQ repository for failed events
            enable_tracing: Enable OpenTelemetry tracing (default: False)
        """
        super().__init__(
            session_factory=session_factory,
            checkpoint_repo=checkpoint_repo,
            dlq_repo=dlq_repo,
            enable_tracing=enable_tracing,
        )
        logger.info(
            "Neo4jEntitySyncHandler initialized",
            extra={"projection": self._projection_name},
        )

    @handles(EntityExtracted)
    async def _handle_entity_extracted(self, conn: AsyncConnection, event: EntityExtracted) -> None:
        """
        Sync extracted entity to Neo4j graph database.

        Creates or merges a node in Neo4j for the entity, then updates
        the PostgreSQL record with the Neo4j node ID for tracking.

        Error handling:
        - Neo4j errors are caught and logged, not raised
        - PostgreSQL update only happens on successful Neo4j sync
        - This allows event processing to continue even if Neo4j is unavailable

        Args:
            conn: Database connection from DatabaseProjection
            event: EntityExtracted event to process
        """
        try:
            # Get Neo4j service (connects lazily if needed)
            neo4j = await get_neo4j_service()

            # Create or merge entity node in Neo4j
            # Uses MERGE for idempotency - same entity creates same node
            node_id = await neo4j.create_entity_node(
                entity_id=event.entity_id,
                tenant_id=event.tenant_id,
                entity_type=event.entity_type.upper(),
                name=event.name,
                properties=event.properties or {},
                description=event.description,
            )

            # Update PostgreSQL with Neo4j node ID and sync status
            sync_time = datetime.now(UTC)
            sql = text("""
                UPDATE extracted_entities
                SET neo4j_node_id = :node_id,
                    synced_to_neo4j = TRUE,
                    synced_at = :synced_at,
                    updated_at = NOW()
                WHERE id = :entity_id
                  AND tenant_id = :tenant_id
            """)

            result = await conn.execute(
                sql,
                {
                    "node_id": node_id,
                    "synced_at": sync_time,
                    "entity_id": event.entity_id,
                    "tenant_id": event.tenant_id,
                },
            )

            if result.rowcount == 0:
                logger.warning(
                    "No entity found to update after Neo4j sync",
                    extra={
                        "projection": self._projection_name,
                        "entity_id": str(event.entity_id),
                        "tenant_id": str(event.tenant_id),
                        "neo4j_node_id": node_id,
                    },
                )
            else:
                logger.debug(
                    "Synced entity to Neo4j",
                    extra={
                        "projection": self._projection_name,
                        "entity_id": str(event.entity_id),
                        "entity_type": event.entity_type,
                        "entity_name": event.name,
                        "neo4j_node_id": node_id,
                        "tenant_id": str(event.tenant_id),
                    },
                )

        except Exception as e:
            # Log error but don't raise - allow event processing to continue
            # Failed syncs can be identified via synced_to_neo4j=False
            # and retried later via a compensation process
            logger.error(
                "Failed to sync entity to Neo4j: %s",
                str(e),
                extra={
                    "projection": self._projection_name,
                    "entity_id": str(event.entity_id),
                    "entity_type": event.entity_type,
                    "entity_name": event.name,
                    "tenant_id": str(event.tenant_id),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )

    async def _truncate_read_models(self) -> None:
        """
        Truncate sync-related data for projection reset.

        Note: This resets the PostgreSQL sync status flags but does NOT
        delete Neo4j nodes. Neo4j cleanup should be handled separately
        if a full reset is needed.
        """
        logger.warning(
            "Truncating Neo4j sync status in PostgreSQL",
            extra={"projection": self._projection_name},
        )
        # Note: Actual truncation would need to be done within a session context
        # This is called during reset() which happens outside handle()


class Neo4jRelationshipSyncHandler(DatabaseProjection):
    """
    Syncs RelationshipDiscovered events to Neo4j graph database.

    Creates relationships between entity nodes in Neo4j when relationships
    are discovered during extraction. After successful sync, updates the
    PostgreSQL record with the Neo4j relationship ID for tracking.

    The handler resolves entity names to entity IDs before creating the
    relationship in Neo4j, as the RelationshipDiscovered event contains
    entity names rather than IDs.

    The handler is designed to be resilient:
    - Neo4j failures are logged but don't raise exceptions
    - PostgreSQL updates only happen on successful Neo4j sync
    - Failed syncs can be identified via synced_to_neo4j=False
    - Missing source/target entities are logged as warnings

    Example:
        >>> from sqlalchemy.ext.asyncio import async_sessionmaker
        >>> session_factory = async_sessionmaker(engine, expire_on_commit=False)
        >>> handler = Neo4jRelationshipSyncHandler(session_factory=session_factory)
        >>> await handler.handle(relationship_discovered_event)
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        checkpoint_repo: "CheckpointRepository | None" = None,
        dlq_repo: "DLQRepository | None" = None,
        enable_tracing: bool = False,
    ) -> None:
        """
        Initialize the Neo4j relationship sync handler.

        Args:
            session_factory: SQLAlchemy async session factory for PostgreSQL updates
            checkpoint_repo: Optional checkpoint repository for tracking position
            dlq_repo: Optional DLQ repository for failed events
            enable_tracing: Enable OpenTelemetry tracing (default: False)
        """
        super().__init__(
            session_factory=session_factory,
            checkpoint_repo=checkpoint_repo,
            dlq_repo=dlq_repo,
            enable_tracing=enable_tracing,
        )
        logger.info(
            "Neo4jRelationshipSyncHandler initialized",
            extra={"projection": self._projection_name},
        )

    async def _find_entity(
        self,
        conn: AsyncConnection,
        tenant_id: UUID,
        page_id: UUID,
        name: str,
    ) -> dict | None:
        """
        Find entity by name within a page.

        Looks up an entity in the extracted_entities table by tenant, page,
        and name. Returns entity id and neo4j_node_id if found.

        Args:
            conn: Database connection
            tenant_id: Tenant identifier
            page_id: Source page identifier
            name: Entity name to find

        Returns:
            Dict with 'id' and 'neo4j_node_id' if found, None otherwise
        """
        sql = text("""
            SELECT id, neo4j_node_id
            FROM extracted_entities
            WHERE tenant_id = :tenant_id
              AND source_page_id = :page_id
              AND name = :name
            LIMIT 1
        """)

        result = await conn.execute(
            sql,
            {
                "tenant_id": tenant_id,
                "page_id": page_id,
                "name": name,
            },
        )
        row = result.fetchone()
        if row:
            return {"id": row.id, "neo4j_node_id": row.neo4j_node_id}
        return None

    @handles(RelationshipDiscovered)
    async def _handle_relationship_discovered(
        self, conn: AsyncConnection, event: RelationshipDiscovered
    ) -> None:
        """
        Sync discovered relationship to Neo4j graph database.

        Resolves entity names to IDs, creates the relationship in Neo4j,
        then updates the PostgreSQL record with the Neo4j relationship ID.

        Error handling:
        - Missing entities are logged as warnings, not errors
        - Neo4j errors are caught and logged, not raised
        - PostgreSQL update only happens on successful Neo4j sync
        - This allows event processing to continue even if Neo4j is unavailable

        Args:
            conn: Database connection from DatabaseProjection
            event: RelationshipDiscovered event to process
        """
        try:
            # Find source and target entities by name
            source = await self._find_entity(
                conn, event.tenant_id, event.page_id, event.source_entity_name
            )
            target = await self._find_entity(
                conn, event.tenant_id, event.page_id, event.target_entity_name
            )

            if not source or not target:
                logger.warning(
                    "Cannot sync relationship: missing entity",
                    extra={
                        "projection": self._projection_name,
                        "relationship_id": str(event.relationship_id),
                        "tenant_id": str(event.tenant_id),
                        "page_id": str(event.page_id),
                        "source_entity_name": event.source_entity_name,
                        "target_entity_name": event.target_entity_name,
                        "source_found": source is not None,
                        "target_found": target is not None,
                    },
                )
                return

            # Get Neo4j service (connects lazily if needed)
            neo4j = await get_neo4j_service()

            # Build properties dict
            properties = {}
            if event.context:
                properties["context"] = event.context

            # Create relationship in Neo4j
            rel_id = await neo4j.create_relationship(
                relationship_id=event.relationship_id,
                tenant_id=event.tenant_id,
                source_entity_id=source["id"],
                target_entity_id=target["id"],
                relationship_type=event.relationship_type,
                properties=properties,
                confidence_score=event.confidence_score,
            )

            if rel_id:
                # Update PostgreSQL with Neo4j relationship ID and sync status
                sync_time = datetime.now(UTC)
                sql = text("""
                    UPDATE entity_relationships
                    SET neo4j_relationship_id = :rel_id,
                        synced_to_neo4j = TRUE,
                        updated_at = NOW()
                    WHERE id = :relationship_id
                      AND tenant_id = :tenant_id
                """)

                result = await conn.execute(
                    sql,
                    {
                        "rel_id": rel_id,
                        "relationship_id": event.relationship_id,
                        "tenant_id": event.tenant_id,
                    },
                )

                if result.rowcount == 0:
                    logger.warning(
                        "No relationship found to update after Neo4j sync",
                        extra={
                            "projection": self._projection_name,
                            "relationship_id": str(event.relationship_id),
                            "tenant_id": str(event.tenant_id),
                            "neo4j_relationship_id": rel_id,
                        },
                    )
                else:
                    logger.debug(
                        "Synced relationship to Neo4j",
                        extra={
                            "projection": self._projection_name,
                            "relationship_id": str(event.relationship_id),
                            "relationship_type": event.relationship_type,
                            "source_entity": event.source_entity_name,
                            "target_entity": event.target_entity_name,
                            "neo4j_relationship_id": rel_id,
                            "tenant_id": str(event.tenant_id),
                        },
                    )
            else:
                logger.warning(
                    "Neo4j create_relationship returned None - entities may not exist in Neo4j",
                    extra={
                        "projection": self._projection_name,
                        "relationship_id": str(event.relationship_id),
                        "tenant_id": str(event.tenant_id),
                        "source_entity_id": str(source["id"]),
                        "target_entity_id": str(target["id"]),
                    },
                )

        except Exception as e:
            # Log error but don't raise - allow event processing to continue
            # Failed syncs can be identified via synced_to_neo4j=False
            # and retried later via a compensation process
            logger.error(
                "Failed to sync relationship to Neo4j: %s",
                str(e),
                extra={
                    "projection": self._projection_name,
                    "relationship_id": str(event.relationship_id),
                    "relationship_type": event.relationship_type,
                    "source_entity_name": event.source_entity_name,
                    "target_entity_name": event.target_entity_name,
                    "tenant_id": str(event.tenant_id),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )

    async def _truncate_read_models(self) -> None:
        """
        Truncate sync-related data for projection reset.

        Note: This resets the PostgreSQL sync status flags but does NOT
        delete Neo4j relationships. Neo4j cleanup should be handled separately
        if a full reset is needed.
        """
        logger.warning(
            "Truncating Neo4j relationship sync status in PostgreSQL",
            extra={"projection": self._projection_name},
        )
        # Note: Actual truncation would need to be done within a session context
        # This is called during reset() which happens outside handle()


__all__ = ["Neo4jEntitySyncHandler", "Neo4jRelationshipSyncHandler"]
