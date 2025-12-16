"""
Projection handlers for extraction events.

These projections update PostgreSQL read models in response to extraction events,
providing query-optimized views of entity and extraction process data.

Handlers use:
- DatabaseProjection from eventsource-py for transaction management
- @handles decorator for declarative event routing
- Upsert (INSERT ... ON CONFLICT) for idempotent event handling
"""

import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from eventsource import DatabaseProjection, handles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker, AsyncSession

from app.eventsourcing.events.extraction import (
    ExtractionCompleted,
    ExtractionProcessFailed,
    ExtractionRequested,
    ExtractionStarted,
    RelationshipDiscovered,
)
from app.eventsourcing.events.scraping import EntityExtracted
from app.models.extracted_entity import EntityType, ExtractionMethod

if TYPE_CHECKING:
    from eventsource.repositories import CheckpointRepository, DLQRepository

logger = logging.getLogger(__name__)


# =============================================================================
# Type Mapping Utilities
# =============================================================================


def map_entity_type(entity_type_str: str) -> str:
    """
    Map entity type string to storage format.

    Changed from enum mapping to string pass-through for dynamic domain support.
    Normalizes to lowercase and handles formatting for consistency.

    As of the Adaptive Extraction Strategy feature, the database stores
    entity_type as a String(100) to support domain-specific types like
    'character', 'theme', 'plot_point' that aren't in the EntityType enum.

    Args:
        entity_type_str: Entity type string from extraction (e.g., "FUNCTION", "character")

    Returns:
        Normalized entity type string (lowercase, underscores for separators)
    """
    if not entity_type_str:
        return "custom"

    # Normalize to lowercase and strip whitespace
    normalized = entity_type_str.lower().strip()

    # Replace spaces and hyphens with underscores for consistency
    normalized = normalized.replace(" ", "_").replace("-", "_")

    # Remove any double underscores that might result
    while "__" in normalized:
        normalized = normalized.replace("__", "_")

    # Strip leading/trailing underscores
    normalized = normalized.strip("_")

    # Log if this is an unknown type (for observability, not an error)
    if not EntityType.is_valid(normalized):
        logger.debug(
            "Domain-specific entity type '%s' (not in EntityType enum)",
            normalized,
            extra={"entity_type": normalized, "original": entity_type_str},
        )

    return normalized if normalized else "custom"


def map_extraction_method(method_str: str) -> str:
    """
    Map event extraction_method string to ExtractionMethod enum value.

    Handles case-insensitive matching and provides fallback for unknown methods.

    Args:
        method_str: Extraction method string from event (e.g., "llm_ollama", "LLM")

    Returns:
        Valid ExtractionMethod enum value string (e.g., "llm_ollama")
    """
    # Normalize to lowercase for comparison
    normalized = method_str.lower().strip()

    # Check against valid ExtractionMethod values
    valid_values = {e.value for e in ExtractionMethod}

    if normalized in valid_values:
        return normalized

    # Handle uppercase enum names
    for method in ExtractionMethod:
        if method.name.lower() == normalized:
            return method.value

    # Common aliases
    aliases = {
        "llm": ExtractionMethod.LLM_OLLAMA.value,
        "ollama": ExtractionMethod.LLM_OLLAMA.value,
        "claude": ExtractionMethod.LLM_CLAUDE.value,
        "anthropic": ExtractionMethod.LLM_CLAUDE.value,
        "schema": ExtractionMethod.SCHEMA_ORG.value,
        "schemaorg": ExtractionMethod.SCHEMA_ORG.value,
        "regex": ExtractionMethod.PATTERN.value,
    }

    if normalized in aliases:
        return aliases[normalized]

    # Fallback to HYBRID for unknown methods
    logger.warning(
        "Unknown extraction method '%s', falling back to HYBRID",
        method_str,
        extra={"extraction_method": method_str},
    )
    return ExtractionMethod.HYBRID.value


# =============================================================================
# Entity Projection Handler
# =============================================================================


class EntityProjectionHandler(DatabaseProjection):
    """
    Projection handler for EntityExtracted events.

    Updates the extracted_entities table in PostgreSQL, creating or updating
    entity records for each EntityExtracted event. Uses upsert semantics for
    idempotent event handling.

    The handler maps event data to the database schema, including:
    - Converting entity_type strings to valid EntityType enum values
    - Converting extraction_method strings to valid ExtractionMethod enum values
    - Handling unknown types gracefully with fallback values

    Example:
        >>> from sqlalchemy.ext.asyncio import async_sessionmaker
        >>> session_factory = async_sessionmaker(engine, expire_on_commit=False)
        >>> handler = EntityProjectionHandler(session_factory=session_factory)
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
        Initialize the entity projection handler.

        Args:
            session_factory: SQLAlchemy async session factory
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
            "EntityProjectionHandler initialized",
            extra={"projection": self._projection_name},
        )

    @handles(EntityExtracted)
    async def _handle_entity_extracted(
        self, conn: AsyncConnection, event: EntityExtracted
    ) -> None:
        """
        Handle EntityExtracted event by upserting entity record.

        Uses INSERT ... ON CONFLICT DO UPDATE for idempotent handling.
        On conflict (same entity_id), updates all fields to latest values.

        Args:
            conn: Database connection from DatabaseProjection
            event: EntityExtracted event to process
        """
        # Map string values to valid enum values
        entity_type = map_entity_type(event.entity_type)
        extraction_method = map_extraction_method(event.extraction_method)

        # Prepare normalized name (fallback to event value or derive from name)
        normalized_name = event.normalized_name
        if not normalized_name:
            # Simple normalization: lowercase and strip
            normalized_name = event.name.lower().strip()

        # Upsert SQL using INSERT ... ON CONFLICT DO UPDATE
        # This ensures idempotent handling - replaying the same event
        # will update to the same values
        sql = text("""
            INSERT INTO extracted_entities (
                id,
                tenant_id,
                source_page_id,
                entity_type,
                name,
                normalized_name,
                description,
                properties,
                extraction_method,
                confidence_score,
                source_text,
                external_ids,
                created_at,
                updated_at
            ) VALUES (
                :entity_id,
                :tenant_id,
                :page_id,
                :entity_type,
                :name,
                :normalized_name,
                :description,
                :properties,
                :extraction_method,
                :confidence_score,
                :source_text,
                :external_ids,
                NOW(),
                NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                entity_type = EXCLUDED.entity_type,
                name = EXCLUDED.name,
                normalized_name = EXCLUDED.normalized_name,
                description = EXCLUDED.description,
                properties = EXCLUDED.properties,
                extraction_method = EXCLUDED.extraction_method,
                confidence_score = EXCLUDED.confidence_score,
                source_text = EXCLUDED.source_text,
                updated_at = NOW()
        """)

        await conn.execute(
            sql,
            {
                "entity_id": event.entity_id,
                "tenant_id": event.tenant_id,
                "page_id": event.page_id,
                "entity_type": entity_type,
                "name": event.name,
                "normalized_name": normalized_name,
                "description": event.description,
                "properties": json.dumps(event.properties or {}),
                "extraction_method": extraction_method,
                "confidence_score": event.confidence_score,
                "source_text": event.source_text,
                "external_ids": json.dumps({}),  # Default empty, can be populated later
            },
        )

        logger.debug(
            "Upserted extracted entity",
            extra={
                "projection": self._projection_name,
                "entity_id": str(event.entity_id),
                "entity_type": entity_type,
                "name": event.name,
                "tenant_id": str(event.tenant_id),
            },
        )

    async def _truncate_read_models(self) -> None:
        """
        Truncate the extracted_entities table for projection reset.

        Warning: This deletes all entity data. Use with caution.
        """
        logger.warning(
            "Truncating extracted_entities table",
            extra={"projection": self._projection_name},
        )
        # Note: Actual truncation would need to be done within a session context
        # This is called during reset() which happens outside handle()


# =============================================================================
# Extraction Process Projection Handler
# =============================================================================


class ExtractionProcessProjectionHandler(DatabaseProjection):
    """
    Projection handler for extraction process lifecycle events.

    Updates the extraction_processes table in PostgreSQL, tracking the status
    of extraction processes from request through completion or failure.

    Handles events:
    - ExtractionRequested: Creates new process record (status: pending)
    - ExtractionStarted: Updates to processing status
    - ExtractionCompleted: Updates to completed status with results
    - ExtractionProcessFailed: Updates to failed status with error info

    Uses upsert semantics based on page_id for idempotent handling.

    Example:
        >>> from sqlalchemy.ext.asyncio import async_sessionmaker
        >>> session_factory = async_sessionmaker(engine, expire_on_commit=False)
        >>> handler = ExtractionProcessProjectionHandler(session_factory=session_factory)
        >>> await handler.handle(extraction_requested_event)
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        checkpoint_repo: "CheckpointRepository | None" = None,
        dlq_repo: "DLQRepository | None" = None,
        enable_tracing: bool = False,
    ) -> None:
        """
        Initialize the extraction process projection handler.

        Args:
            session_factory: SQLAlchemy async session factory
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
            "ExtractionProcessProjectionHandler initialized",
            extra={"projection": self._projection_name},
        )

    @handles(ExtractionRequested)
    async def _handle_extraction_requested(
        self, conn: AsyncConnection, event: ExtractionRequested
    ) -> None:
        """
        Handle ExtractionRequested event by creating/updating process record.

        Uses upsert to handle replay scenarios where the same extraction
        might be requested multiple times.

        Args:
            conn: Database connection from DatabaseProjection
            event: ExtractionRequested event to process
        """
        sql = text("""
            INSERT INTO extraction_processes (
                id,
                tenant_id,
                page_id,
                status,
                page_url,
                content_hash,
                extraction_config,
                requested_at,
                created_at
            ) VALUES (
                :process_id,
                :tenant_id,
                :page_id,
                'pending',
                :page_url,
                :content_hash,
                :extraction_config,
                :requested_at,
                NOW()
            )
            ON CONFLICT (page_id) DO UPDATE SET
                status = 'pending',
                page_url = EXCLUDED.page_url,
                content_hash = EXCLUDED.content_hash,
                extraction_config = EXCLUDED.extraction_config,
                requested_at = EXCLUDED.requested_at,
                updated_at = NOW(),
                -- Reset processing fields on re-request
                started_at = NULL,
                completed_at = NULL,
                failed_at = NULL,
                worker_id = NULL,
                entity_count = 0,
                relationship_count = 0,
                duration_ms = NULL,
                last_error = NULL,
                last_error_type = NULL
        """)

        await conn.execute(
            sql,
            {
                "process_id": event.aggregate_id,
                "tenant_id": event.tenant_id,
                "page_id": event.page_id,
                "page_url": event.page_url,
                "content_hash": event.content_hash,
                "extraction_config": json.dumps(event.extraction_config or {}),
                "requested_at": event.requested_at,
            },
        )

        logger.debug(
            "Created/updated extraction process record",
            extra={
                "projection": self._projection_name,
                "process_id": str(event.aggregate_id),
                "page_id": str(event.page_id),
                "status": "pending",
                "tenant_id": str(event.tenant_id),
            },
        )

    @handles(ExtractionStarted)
    async def _handle_extraction_started(
        self, conn: AsyncConnection, event: ExtractionStarted
    ) -> None:
        """
        Handle ExtractionStarted event by updating process to processing status.

        Args:
            conn: Database connection from DatabaseProjection
            event: ExtractionStarted event to process
        """
        sql = text("""
            UPDATE extraction_processes
            SET
                status = 'processing',
                worker_id = :worker_id,
                started_at = :started_at,
                updated_at = NOW()
            WHERE page_id = :page_id AND tenant_id = :tenant_id
        """)

        result = await conn.execute(
            sql,
            {
                "page_id": event.page_id,
                "tenant_id": event.tenant_id,
                "worker_id": event.worker_id,
                "started_at": event.started_at,
            },
        )

        if result.rowcount == 0:
            logger.warning(
                "No extraction process found to update for ExtractionStarted",
                extra={
                    "projection": self._projection_name,
                    "page_id": str(event.page_id),
                    "tenant_id": str(event.tenant_id),
                },
            )
        else:
            logger.debug(
                "Updated extraction process to processing",
                extra={
                    "projection": self._projection_name,
                    "page_id": str(event.page_id),
                    "worker_id": event.worker_id,
                    "tenant_id": str(event.tenant_id),
                },
            )

    @handles(ExtractionCompleted)
    async def _handle_extraction_completed(
        self, conn: AsyncConnection, event: ExtractionCompleted
    ) -> None:
        """
        Handle ExtractionCompleted event by updating process to completed status.

        Args:
            conn: Database connection from DatabaseProjection
            event: ExtractionCompleted event to process
        """
        # Map extraction method to valid enum value
        extraction_method = map_extraction_method(event.extraction_method)

        sql = text("""
            UPDATE extraction_processes
            SET
                status = 'completed',
                entity_count = :entity_count,
                relationship_count = :relationship_count,
                duration_ms = :duration_ms,
                extraction_method = :extraction_method,
                completed_at = :completed_at,
                updated_at = NOW()
            WHERE page_id = :page_id AND tenant_id = :tenant_id
        """)

        result = await conn.execute(
            sql,
            {
                "page_id": event.page_id,
                "tenant_id": event.tenant_id,
                "entity_count": event.entity_count,
                "relationship_count": event.relationship_count,
                "duration_ms": event.duration_ms,
                "extraction_method": extraction_method,
                "completed_at": event.completed_at,
            },
        )

        if result.rowcount == 0:
            logger.warning(
                "No extraction process found to update for ExtractionCompleted",
                extra={
                    "projection": self._projection_name,
                    "page_id": str(event.page_id),
                    "tenant_id": str(event.tenant_id),
                },
            )
        else:
            logger.debug(
                "Updated extraction process to completed",
                extra={
                    "projection": self._projection_name,
                    "page_id": str(event.page_id),
                    "entity_count": event.entity_count,
                    "relationship_count": event.relationship_count,
                    "duration_ms": event.duration_ms,
                    "tenant_id": str(event.tenant_id),
                },
            )

    @handles(ExtractionProcessFailed)
    async def _handle_extraction_failed(
        self, conn: AsyncConnection, event: ExtractionProcessFailed
    ) -> None:
        """
        Handle ExtractionProcessFailed event by updating process to failed status.

        Args:
            conn: Database connection from DatabaseProjection
            event: ExtractionProcessFailed event to process
        """
        # Determine final status based on retryable flag
        status = "retrying" if event.retryable else "failed"

        sql = text("""
            UPDATE extraction_processes
            SET
                status = :status,
                retry_count = :retry_count,
                last_error = :error_message,
                last_error_type = :error_type,
                failed_at = :failed_at,
                updated_at = NOW()
            WHERE page_id = :page_id AND tenant_id = :tenant_id
        """)

        result = await conn.execute(
            sql,
            {
                "page_id": event.page_id,
                "tenant_id": event.tenant_id,
                "status": status,
                "retry_count": event.retry_count,
                "error_message": event.error_message,
                "error_type": event.error_type,
                "failed_at": event.failed_at,
            },
        )

        if result.rowcount == 0:
            logger.warning(
                "No extraction process found to update for ExtractionProcessFailed",
                extra={
                    "projection": self._projection_name,
                    "page_id": str(event.page_id),
                    "tenant_id": str(event.tenant_id),
                },
            )
        else:
            logger.debug(
                "Updated extraction process to %s",
                status,
                extra={
                    "projection": self._projection_name,
                    "page_id": str(event.page_id),
                    "error_type": event.error_type,
                    "retry_count": event.retry_count,
                    "retryable": event.retryable,
                    "tenant_id": str(event.tenant_id),
                },
            )

    async def _truncate_read_models(self) -> None:
        """
        Truncate the extraction_processes table for projection reset.

        Warning: This deletes all extraction process data. Use with caution.
        """
        logger.warning(
            "Truncating extraction_processes table",
            extra={"projection": self._projection_name},
        )
        # Note: Actual truncation would need to be done within a session context
        # This is called during reset() which happens outside handle()


# =============================================================================
# Relationship Projection Handler
# =============================================================================


class RelationshipProjectionHandler(DatabaseProjection):
    """
    Projection handler for RelationshipDiscovered events.

    Creates EntityRelationship records by resolving entity names to entity IDs
    within the same page/tenant context. Uses upsert semantics for idempotent
    event handling.

    The handler:
    - Resolves source and target entity names to entity IDs
    - Creates relationships with proper tenant isolation
    - Handles missing entities gracefully with logging (no exceptions)
    - Uses INSERT ... ON CONFLICT for idempotency

    Example:
        >>> from sqlalchemy.ext.asyncio import async_sessionmaker
        >>> session_factory = async_sessionmaker(engine, expire_on_commit=False)
        >>> handler = RelationshipProjectionHandler(session_factory=session_factory)
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
        Initialize the relationship projection handler.

        Args:
            session_factory: SQLAlchemy async session factory
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
            "RelationshipProjectionHandler initialized",
            extra={"projection": self._projection_name},
        )

    async def _find_entity_by_name(
        self,
        conn: AsyncConnection,
        tenant_id: UUID,
        page_id: UUID,
        name: str,
    ) -> UUID | None:
        """
        Find entity ID by name within tenant and page context.

        Attempts exact name match first, then falls back to normalized name match.

        Args:
            conn: Database connection
            tenant_id: Tenant ID for isolation
            page_id: Source page ID for scoping
            name: Entity name to search for

        Returns:
            Entity UUID if found, None otherwise
        """
        # Try exact name match first
        exact_match_sql = text("""
            SELECT id FROM extracted_entities
            WHERE tenant_id = :tenant_id
              AND source_page_id = :page_id
              AND name = :name
            LIMIT 1
        """)

        result = await conn.execute(
            exact_match_sql,
            {"tenant_id": tenant_id, "page_id": page_id, "name": name},
        )
        row = result.fetchone()

        if row:
            return row[0]

        # Fall back to normalized name match
        normalized_name = name.lower().strip()
        normalized_match_sql = text("""
            SELECT id FROM extracted_entities
            WHERE tenant_id = :tenant_id
              AND source_page_id = :page_id
              AND normalized_name = :normalized_name
            LIMIT 1
        """)

        result = await conn.execute(
            normalized_match_sql,
            {
                "tenant_id": tenant_id,
                "page_id": page_id,
                "normalized_name": normalized_name,
            },
        )
        row = result.fetchone()

        return row[0] if row else None

    @handles(RelationshipDiscovered)
    async def _handle_relationship_discovered(
        self, conn: AsyncConnection, event: RelationshipDiscovered
    ) -> None:
        """
        Handle RelationshipDiscovered event by creating/updating relationship record.

        Resolves source and target entity names to IDs, then creates an
        EntityRelationship record. Uses upsert for idempotent handling.

        If either source or target entity is not found, logs a warning and
        skips the event without raising an exception.

        Args:
            conn: Database connection from DatabaseProjection
            event: RelationshipDiscovered event to process
        """
        # Resolve source entity
        source_entity_id = await self._find_entity_by_name(
            conn,
            event.tenant_id,
            event.page_id,
            event.source_entity_name,
        )

        if source_entity_id is None:
            logger.warning(
                "Source entity not found for relationship",
                extra={
                    "projection": self._projection_name,
                    "relationship_id": str(event.relationship_id),
                    "source_entity_name": event.source_entity_name,
                    "page_id": str(event.page_id),
                    "tenant_id": str(event.tenant_id),
                },
            )
            return

        # Resolve target entity
        target_entity_id = await self._find_entity_by_name(
            conn,
            event.tenant_id,
            event.page_id,
            event.target_entity_name,
        )

        if target_entity_id is None:
            logger.warning(
                "Target entity not found for relationship",
                extra={
                    "projection": self._projection_name,
                    "relationship_id": str(event.relationship_id),
                    "target_entity_name": event.target_entity_name,
                    "page_id": str(event.page_id),
                    "tenant_id": str(event.tenant_id),
                },
            )
            return

        # Normalize relationship type to uppercase
        relationship_type = event.relationship_type.upper()

        # Build properties dict and serialize to JSON for asyncpg
        properties = {}
        if event.context:
            properties["context"] = event.context
        properties = json.dumps(properties)

        # Upsert SQL using INSERT ... ON CONFLICT DO UPDATE
        # This ensures idempotent handling - replaying the same event
        # will update to the same values
        sql = text("""
            INSERT INTO entity_relationships (
                id,
                tenant_id,
                source_entity_id,
                target_entity_id,
                relationship_type,
                properties,
                confidence_score,
                synced_to_neo4j,
                created_at,
                updated_at
            ) VALUES (
                :relationship_id,
                :tenant_id,
                :source_entity_id,
                :target_entity_id,
                :relationship_type,
                :properties,
                :confidence_score,
                FALSE,
                NOW(),
                NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                source_entity_id = EXCLUDED.source_entity_id,
                target_entity_id = EXCLUDED.target_entity_id,
                relationship_type = EXCLUDED.relationship_type,
                properties = EXCLUDED.properties,
                confidence_score = EXCLUDED.confidence_score,
                updated_at = NOW()
        """)

        await conn.execute(
            sql,
            {
                "relationship_id": event.relationship_id,
                "tenant_id": event.tenant_id,
                "source_entity_id": source_entity_id,
                "target_entity_id": target_entity_id,
                "relationship_type": relationship_type,
                "properties": properties,
                "confidence_score": event.confidence_score,
            },
        )

        logger.debug(
            "Upserted entity relationship",
            extra={
                "projection": self._projection_name,
                "relationship_id": str(event.relationship_id),
                "source_entity_name": event.source_entity_name,
                "target_entity_name": event.target_entity_name,
                "relationship_type": relationship_type,
                "tenant_id": str(event.tenant_id),
            },
        )

    async def _truncate_read_models(self) -> None:
        """
        Truncate the entity_relationships table for projection reset.

        Warning: This deletes all relationship data. Use with caution.
        """
        logger.warning(
            "Truncating entity_relationships table",
            extra={"projection": self._projection_name},
        )
        # Note: Actual truncation would need to be done within a session context
        # This is called during reset() which happens outside handle()


__all__ = [
    "EntityProjectionHandler",
    "ExtractionProcessProjectionHandler",
    "RelationshipProjectionHandler",
    "map_entity_type",
    "map_extraction_method",
]
