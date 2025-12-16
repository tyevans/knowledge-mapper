"""
Projection handlers for entity consolidation events.

This module provides handlers that update PostgreSQL read models
in response to consolidation events (merge, undo, split).
These projections maintain denormalized views for efficient querying.

Handlers update:
- extracted_entities: Entity status, canonical flags
- entity_aliases: Alias records
- merge_review_queue: Review item status
- Denormalized views for entity counts and relationships
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, UTC
from typing import TYPE_CHECKING
from uuid import UUID

from eventsource import DatabaseProjection, handles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.eventsourcing.events.consolidation import (
    EntitiesMerged,
    EntitySplit,
    MergeQueuedForReview,
    MergeReviewDecision,
    MergeUndone,
)

if TYPE_CHECKING:
    from eventsource.repositories import CheckpointRepository, DLQRepository

logger = logging.getLogger(__name__)


class ConsolidationProjectionHandler(DatabaseProjection):
    """
    Projection handler for consolidation events.

    Updates PostgreSQL read models when entities are merged, split,
    or when merge operations are undone. This keeps denormalized
    views in sync with the event stream.

    Handles:
    - EntitiesMerged: Updates entity canonical status, creates summary views
    - MergeUndone: Reverses denormalized updates
    - EntitySplit: Creates entries for new split entities
    - MergeQueuedForReview: Creates review queue entries
    - MergeReviewDecision: Updates review item status

    Example:
        >>> from sqlalchemy.ext.asyncio import async_sessionmaker
        >>> session_factory = async_sessionmaker(engine, expire_on_commit=False)
        >>> handler = ConsolidationProjectionHandler(session_factory=session_factory)
        >>> await handler.handle(entities_merged_event)
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        checkpoint_repo: "CheckpointRepository | None" = None,
        dlq_repo: "DLQRepository | None" = None,
        enable_tracing: bool = False,
    ) -> None:
        """
        Initialize the consolidation projection handler.

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
            "ConsolidationProjectionHandler initialized",
            extra={"projection": self._projection_name},
        )

    @handles(EntitiesMerged)
    async def _handle_entities_merged(
        self, conn: AsyncConnection, event: EntitiesMerged
    ) -> None:
        """
        Handle EntitiesMerged event by updating read models.

        Updates:
        - Merged entities: is_canonical=False, is_alias_of=canonical_id
        - Canonical entity: Updated merge count in properties
        - Any pending review items for these entities: status=expired

        Args:
            conn: Database connection from DatabaseProjection
            event: EntitiesMerged event to process
        """
        canonical_id = event.canonical_entity_id
        merged_ids = event.merged_entity_ids
        tenant_id = event.tenant_id

        try:
            # Update merged entities to point to canonical
            update_merged_sql = text("""
                UPDATE extracted_entities
                SET is_canonical = FALSE,
                    is_alias_of = :canonical_id,
                    updated_at = NOW()
                WHERE id = ANY(:merged_ids)
                  AND tenant_id = :tenant_id
            """)

            await conn.execute(
                update_merged_sql,
                {
                    "canonical_id": canonical_id,
                    "merged_ids": [str(mid) for mid in merged_ids],
                    "tenant_id": tenant_id,
                },
            )

            # Update canonical entity properties with merge info
            merge_details = event.property_merge_details or {}
            update_canonical_sql = text("""
                UPDATE extracted_entities
                SET properties = properties || :merge_properties,
                    updated_at = NOW()
                WHERE id = :canonical_id
                  AND tenant_id = :tenant_id
            """)

            await conn.execute(
                update_canonical_sql,
                {
                    "canonical_id": canonical_id,
                    "tenant_id": tenant_id,
                    "merge_properties": json.dumps({
                        "_merged_count": len(merged_ids),
                        "_last_merged_at": datetime.now(UTC).isoformat(),
                        "_merge_event_id": str(event.aggregate_id),
                    }),
                },
            )

            # Expire any pending review items involving merged entities
            expire_reviews_sql = text("""
                UPDATE merge_review_queue
                SET status = 'expired',
                    updated_at = NOW()
                WHERE tenant_id = :tenant_id
                  AND status = 'pending'
                  AND (entity_a_id = ANY(:all_entity_ids) OR entity_b_id = ANY(:all_entity_ids))
            """)

            all_entity_ids = [str(canonical_id)] + [str(mid) for mid in merged_ids]
            await conn.execute(
                expire_reviews_sql,
                {
                    "tenant_id": tenant_id,
                    "all_entity_ids": all_entity_ids,
                },
            )

            logger.debug(
                "Updated read models for EntitiesMerged",
                extra={
                    "projection": self._projection_name,
                    "canonical_entity_id": str(canonical_id),
                    "merged_count": len(merged_ids),
                    "tenant_id": str(tenant_id),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to update read models for EntitiesMerged: %s",
                str(e),
                extra={
                    "projection": self._projection_name,
                    "event_id": str(event.aggregate_id),
                    "canonical_entity_id": str(canonical_id),
                    "tenant_id": str(tenant_id),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise

    @handles(MergeUndone)
    async def _handle_merge_undone(
        self, conn: AsyncConnection, event: MergeUndone
    ) -> None:
        """
        Handle MergeUndone event by reversing denormalized updates.

        Updates:
        - Restored entities: Created as new entities (handled by service)
        - Canonical entity: Updated undo count in properties

        Note: The actual entity restoration is done by MergeService.
        This projection only updates metadata on the canonical entity.

        Args:
            conn: Database connection from DatabaseProjection
            event: MergeUndone event to process
        """
        canonical_id = event.canonical_entity_id
        restored_ids = event.restored_entity_ids
        tenant_id = event.tenant_id

        try:
            # Update canonical entity properties with undo info
            update_canonical_sql = text("""
                UPDATE extracted_entities
                SET properties = properties || :undo_properties,
                    updated_at = NOW()
                WHERE id = :canonical_id
                  AND tenant_id = :tenant_id
            """)

            await conn.execute(
                update_canonical_sql,
                {
                    "canonical_id": canonical_id,
                    "tenant_id": tenant_id,
                    "undo_properties": json.dumps({
                        "_last_undo_at": datetime.now(UTC).isoformat(),
                        "_undo_event_id": str(event.aggregate_id),
                        "_last_restored_ids": [str(rid) for rid in restored_ids],
                    }),
                },
            )

            logger.debug(
                "Updated read models for MergeUndone",
                extra={
                    "projection": self._projection_name,
                    "canonical_entity_id": str(canonical_id),
                    "restored_count": len(restored_ids),
                    "tenant_id": str(tenant_id),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to update read models for MergeUndone: %s",
                str(e),
                extra={
                    "projection": self._projection_name,
                    "event_id": str(event.aggregate_id),
                    "canonical_entity_id": str(canonical_id),
                    "tenant_id": str(tenant_id),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise

    @handles(EntitySplit)
    async def _handle_entity_split(
        self, conn: AsyncConnection, event: EntitySplit
    ) -> None:
        """
        Handle EntitySplit event by creating entries for new entities.

        Updates:
        - Original entity: is_canonical=False, split metadata in properties
        - New entities: Created by service, marked as canonical

        Note: The actual entity creation is done by MergeService.
        This projection updates the original entity's metadata.

        Args:
            conn: Database connection from DatabaseProjection
            event: EntitySplit event to process
        """
        original_id = event.original_entity_id
        new_ids = event.new_entity_ids
        tenant_id = event.tenant_id

        try:
            # Update original entity with split info
            update_original_sql = text("""
                UPDATE extracted_entities
                SET is_canonical = FALSE,
                    properties = properties || :split_properties,
                    updated_at = NOW()
                WHERE id = :original_id
                  AND tenant_id = :tenant_id
            """)

            await conn.execute(
                update_original_sql,
                {
                    "original_id": original_id,
                    "tenant_id": tenant_id,
                    "split_properties": json.dumps({
                        "_split_into": [str(nid) for nid in new_ids],
                        "_split_at": datetime.now(UTC).isoformat(),
                        "_split_event_id": str(event.aggregate_id),
                        "_split_reason": event.split_reason,
                    }),
                },
            )

            # Expire any pending review items involving the original entity
            expire_reviews_sql = text("""
                UPDATE merge_review_queue
                SET status = 'expired',
                    updated_at = NOW()
                WHERE tenant_id = :tenant_id
                  AND status = 'pending'
                  AND (entity_a_id = :original_id OR entity_b_id = :original_id)
            """)

            await conn.execute(
                expire_reviews_sql,
                {
                    "tenant_id": tenant_id,
                    "original_id": original_id,
                },
            )

            logger.debug(
                "Updated read models for EntitySplit",
                extra={
                    "projection": self._projection_name,
                    "original_entity_id": str(original_id),
                    "new_entity_count": len(new_ids),
                    "tenant_id": str(tenant_id),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to update read models for EntitySplit: %s",
                str(e),
                extra={
                    "projection": self._projection_name,
                    "event_id": str(event.aggregate_id),
                    "original_entity_id": str(original_id),
                    "tenant_id": str(tenant_id),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise

    @handles(MergeQueuedForReview)
    async def _handle_merge_queued_for_review(
        self, conn: AsyncConnection, event: MergeQueuedForReview
    ) -> None:
        """
        Handle MergeQueuedForReview by creating review queue entry.

        Creates or updates a merge_review_queue entry for human review.
        Uses upsert semantics to handle replay scenarios.

        Args:
            conn: Database connection from DatabaseProjection
            event: MergeQueuedForReview event to process
        """
        tenant_id = event.tenant_id
        entity_a_id = event.entity_a_id
        entity_b_id = event.entity_b_id

        try:
            # Normalize entity order (smaller UUID first) for consistent uniqueness
            if str(entity_a_id) > str(entity_b_id):
                entity_a_id, entity_b_id = entity_b_id, entity_a_id

            upsert_sql = text("""
                INSERT INTO merge_review_queue (
                    id,
                    tenant_id,
                    entity_a_id,
                    entity_b_id,
                    confidence,
                    review_priority,
                    similarity_scores,
                    status,
                    created_at
                ) VALUES (
                    :id,
                    :tenant_id,
                    :entity_a_id,
                    :entity_b_id,
                    :confidence,
                    :review_priority,
                    :similarity_scores,
                    'pending',
                    NOW()
                )
                ON CONFLICT (tenant_id, entity_a_id, entity_b_id) DO UPDATE SET
                    confidence = EXCLUDED.confidence,
                    review_priority = EXCLUDED.review_priority,
                    similarity_scores = EXCLUDED.similarity_scores,
                    status = 'pending',
                    updated_at = NOW()
            """)

            await conn.execute(
                upsert_sql,
                {
                    "id": event.aggregate_id,
                    "tenant_id": tenant_id,
                    "entity_a_id": entity_a_id,
                    "entity_b_id": entity_b_id,
                    "confidence": event.confidence,
                    "review_priority": event.review_priority,
                    "similarity_scores": json.dumps(event.similarity_scores),
                },
            )

            logger.debug(
                "Created/updated merge review queue entry",
                extra={
                    "projection": self._projection_name,
                    "review_id": str(event.aggregate_id),
                    "entity_a_id": str(entity_a_id),
                    "entity_b_id": str(entity_b_id),
                    "confidence": event.confidence,
                    "tenant_id": str(tenant_id),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to create review queue entry: %s",
                str(e),
                extra={
                    "projection": self._projection_name,
                    "event_id": str(event.aggregate_id),
                    "tenant_id": str(tenant_id),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise

    @handles(MergeReviewDecision)
    async def _handle_merge_review_decision(
        self, conn: AsyncConnection, event: MergeReviewDecision
    ) -> None:
        """
        Handle MergeReviewDecision by updating review item status.

        Updates the merge_review_queue entry with the review decision
        and reviewer information.

        Args:
            conn: Database connection from DatabaseProjection
            event: MergeReviewDecision event to process
        """
        review_item_id = event.review_item_id
        tenant_id = event.tenant_id

        try:
            # Map decision to status
            status_map = {
                "approve": "approved",
                "reject": "rejected",
                "defer": "deferred",
                "mark_different": "rejected",
            }
            status = status_map.get(event.decision, "rejected")

            update_sql = text("""
                UPDATE merge_review_queue
                SET status = :status,
                    reviewed_by = :reviewer_user_id,
                    reviewed_at = NOW(),
                    reviewer_notes = :reviewer_notes,
                    updated_at = NOW()
                WHERE id = :review_item_id
                  AND tenant_id = :tenant_id
            """)

            result = await conn.execute(
                update_sql,
                {
                    "status": status,
                    "reviewer_user_id": event.reviewer_user_id,
                    "reviewer_notes": event.reviewer_notes,
                    "review_item_id": review_item_id,
                    "tenant_id": tenant_id,
                },
            )

            if result.rowcount == 0:
                logger.warning(
                    "No review item found to update",
                    extra={
                        "projection": self._projection_name,
                        "review_item_id": str(review_item_id),
                        "tenant_id": str(tenant_id),
                    },
                )
            else:
                logger.debug(
                    "Updated merge review item status",
                    extra={
                        "projection": self._projection_name,
                        "review_item_id": str(review_item_id),
                        "decision": event.decision,
                        "status": status,
                        "reviewer_user_id": str(event.reviewer_user_id),
                        "tenant_id": str(tenant_id),
                    },
                )

        except Exception as e:
            logger.error(
                "Failed to update review item status: %s",
                str(e),
                extra={
                    "projection": self._projection_name,
                    "review_item_id": str(review_item_id),
                    "tenant_id": str(tenant_id),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise

    async def _truncate_read_models(self) -> None:
        """
        Truncate consolidation-related read model data for projection reset.

        Warning: This resets denormalized data. Use with caution.
        """
        logger.warning(
            "Truncating consolidation read models",
            extra={"projection": self._projection_name},
        )
        # Note: Actual truncation would need to be done within a session context
        # This is called during reset() which happens outside handle()


__all__ = ["ConsolidationProjectionHandler"]
