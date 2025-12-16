"""
Celery tasks for entity consolidation.

This module provides tasks for:
- Running consolidation pipeline for scraping jobs
- Computing merge candidates
- Auto-merging high-confidence pairs
- Queueing medium-confidence pairs for review
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from celery import shared_task
from sqlalchemy import select, func

from app.worker.context import TenantWorkerContext
from app.models.scraping_job import JobStatus, JobStage, ScrapingJob
from app.models.scraped_page import ScrapedPage
from app.models.extracted_entity import ExtractedEntity
from app.models.merge_review_queue import MergeReviewItem, MergeReviewStatus
from app.models.consolidation_config import ConsolidationConfig

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="app.tasks.consolidation.run_consolidation_for_job",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def run_consolidation_for_job(self, job_id: str, tenant_id: str) -> dict:
    """
    Run entity consolidation pipeline for entities from a scraping job.

    This task:
    1. Loads entities extracted from the job's pages
    2. Runs blocking to find candidate pairs
    3. Computes string similarity (Stage 2)
    4. Auto-merges high-confidence pairs
    5. Queues medium-confidence pairs for review
    6. Updates job to DONE stage

    Args:
        job_id: UUID of the scraping job
        tenant_id: UUID of the tenant

    Returns:
        dict: Consolidation summary
    """
    logger.info(
        "Starting consolidation for job",
        extra={"job_id": job_id, "tenant_id": tenant_id},
    )

    with TenantWorkerContext(tenant_id) as ctx:
        # Load job
        result = ctx.db.execute(
            select(ScrapingJob).where(ScrapingJob.id == UUID(job_id))
        )
        job = result.scalar_one_or_none()

        if not job:
            logger.error(f"Job not found: {job_id}")
            return {"status": "error", "message": "Job not found"}

        if job.stage != JobStage.CONSOLIDATING:
            logger.info(
                f"Job {job_id} not in CONSOLIDATING stage, skipping",
                extra={"job_id": job_id, "stage": job.stage.value},
            )
            return {"status": "skipped", "reason": f"Job in {job.stage.value} stage"}

        try:
            # Load tenant config
            config_result = ctx.db.execute(
                select(ConsolidationConfig).where(
                    ConsolidationConfig.tenant_id == UUID(tenant_id)
                )
            )
            config = config_result.scalar_one_or_none()

            if not config:
                # Use defaults
                config = ConsolidationConfig(tenant_id=UUID(tenant_id))

            # Get entities from this job's pages
            page_ids_subquery = (
                select(ScrapedPage.id)
                .where(ScrapedPage.job_id == UUID(job_id))
                .subquery()
            )

            entities_result = ctx.db.execute(
                select(ExtractedEntity).where(
                    ExtractedEntity.source_page_id.in_(select(page_ids_subquery)),
                    ExtractedEntity.tenant_id == UUID(tenant_id),
                    ExtractedEntity.is_canonical == True,  # noqa: E712
                )
            )
            entities = list(entities_result.scalars().all())

            total_entities = len(entities)
            if total_entities == 0:
                # No entities to consolidate - mark job complete
                _complete_job(job, ctx.db, 0, 0, 0)
                return {
                    "status": "complete",
                    "entities_processed": 0,
                    "candidates_found": 0,
                    "auto_merged": 0,
                }

            logger.info(
                f"Found {total_entities} entities to consolidate",
                extra={"job_id": job_id, "total_entities": total_entities},
            )

            # Initialize services
            from app.services.consolidation import (
                BlockingEngine,
                StringSimilarityService,
            )

            blocking_engine = BlockingEngine(
                max_block_size=config.max_block_size or 500
            )
            string_similarity = StringSimilarityService()

            # Process each entity
            candidates_found = 0
            auto_merged = 0
            review_queued = 0
            processed = 0
            processed_pairs = set()  # Avoid duplicate processing

            for entity in entities:
                # Find blocking candidates
                blocking_result = blocking_engine.find_candidates_sync(
                    ctx.db, entity, UUID(tenant_id), config
                )

                if not blocking_result.candidates:
                    processed += 1
                    _update_progress(job, ctx.db, processed, total_entities, candidates_found, auto_merged)
                    continue

                # Compute string similarity and filter using threshold
                filtered_candidates = string_similarity.filter_candidates(
                    entity,
                    blocking_result.candidates,
                    threshold=(config.review_threshold or 0.50),
                )

                for candidate, scores in filtered_candidates:
                    # Skip self-comparison (shouldn't happen, but be safe)
                    if candidate.id == entity.id:
                        continue

                    # Skip already processed pairs
                    pair_key = tuple(sorted([str(entity.id), str(candidate.id)]))
                    if pair_key in processed_pairs:
                        continue
                    processed_pairs.add(pair_key)

                    candidates_found += 1
                    combined_score = scores.combined_score
                    scores_dict = scores.to_dict() if hasattr(scores, 'to_dict') else {}

                    # Determine action based on score
                    if combined_score >= (config.auto_merge_threshold or 0.90):
                        # Auto-merge high confidence pairs
                        merged = _auto_merge_pair(
                            ctx.db, entity, candidate, combined_score,
                            scores_dict, UUID(tenant_id)
                        )
                        if merged:
                            auto_merged += 1
                        else:
                            # If merge failed, queue for review
                            _queue_for_review(
                                ctx.db, entity, candidate, combined_score,
                                scores_dict, UUID(tenant_id), priority=50
                            )
                            review_queued += 1
                    else:
                        # Queue medium confidence for review
                        _queue_for_review(
                            ctx.db, entity, candidate, combined_score,
                            scores_dict, UUID(tenant_id),
                            priority=_compute_review_priority(combined_score)
                        )
                        review_queued += 1

                processed += 1
                _update_progress(job, ctx.db, processed, total_entities, candidates_found, auto_merged)

                # Update task state for monitoring
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "entities_processed": processed,
                        "total_entities": total_entities,
                        "candidates_found": candidates_found,
                        "auto_merged": auto_merged,
                        "review_queued": review_queued,
                    },
                )

            # Mark job as complete
            _complete_job(job, ctx.db, total_entities, candidates_found, auto_merged)

            # Emit completion event
            _emit_consolidation_completed_event(
                job, tenant_id, total_entities, candidates_found, auto_merged
            )

            logger.info(
                "Consolidation completed",
                extra={
                    "job_id": job_id,
                    "entities_processed": total_entities,
                    "candidates_found": candidates_found,
                    "auto_merged": auto_merged,
                    "review_queued": review_queued,
                },
            )

            return {
                "status": "complete",
                "entities_processed": total_entities,
                "candidates_found": candidates_found,
                "auto_merged": auto_merged,
                "review_queued": review_queued,
            }

        except Exception as e:
            logger.exception(
                "Consolidation failed",
                extra={"job_id": job_id, "error": str(e)},
            )

            # Mark job as failed
            job.status = JobStatus.FAILED
            job.error_message = f"Consolidation failed: {str(e)}"
            job.updated_at = datetime.now(timezone.utc)
            ctx.db.commit()

            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)

            return {"status": "failed", "error": str(e)}


@shared_task(
    bind=True,
    name="app.tasks.consolidation.run_consolidation_manual",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def run_consolidation_manual(
    self,
    tenant_id: str,
    entity_ids: list[str] | None = None,
) -> dict:
    """
    Manually trigger consolidation for a tenant.

    Can optionally specify subset of entity IDs to process.

    Args:
        tenant_id: UUID of the tenant
        entity_ids: Optional list of entity UUIDs to process

    Returns:
        dict: Consolidation summary
    """
    logger.info(
        "Starting manual consolidation",
        extra={
            "tenant_id": tenant_id,
            "entity_ids_count": len(entity_ids) if entity_ids else "all",
        },
    )

    with TenantWorkerContext(tenant_id) as ctx:
        try:
            # Load tenant config
            config_result = ctx.db.execute(
                select(ConsolidationConfig).where(
                    ConsolidationConfig.tenant_id == UUID(tenant_id)
                )
            )
            config = config_result.scalar_one_or_none()

            if not config:
                config = ConsolidationConfig(tenant_id=UUID(tenant_id))

            # Get entities to process
            if entity_ids:
                entity_uuids = [UUID(eid) for eid in entity_ids]
                entities_result = ctx.db.execute(
                    select(ExtractedEntity).where(
                        ExtractedEntity.id.in_(entity_uuids),
                        ExtractedEntity.tenant_id == UUID(tenant_id),
                        ExtractedEntity.is_canonical == True,  # noqa: E712
                    )
                )
            else:
                entities_result = ctx.db.execute(
                    select(ExtractedEntity).where(
                        ExtractedEntity.tenant_id == UUID(tenant_id),
                        ExtractedEntity.is_canonical == True,  # noqa: E712
                    )
                )
            entities = list(entities_result.scalars().all())

            total_entities = len(entities)
            if total_entities == 0:
                return {
                    "status": "complete",
                    "entities_processed": 0,
                    "candidates_found": 0,
                    "auto_merged": 0,
                }

            # Initialize services
            from app.services.consolidation import (
                BlockingEngine,
                StringSimilarityService,
            )

            blocking_engine = BlockingEngine(
                max_block_size=config.max_block_size or 500
            )
            string_similarity = StringSimilarityService()

            # Process entities
            candidates_found = 0
            auto_merged = 0
            review_queued = 0
            processed = 0
            processed_pairs = set()

            for entity in entities:
                blocking_result = blocking_engine.find_candidates_sync(
                    ctx.db, entity, UUID(tenant_id), config
                )

                if not blocking_result.candidates:
                    processed += 1
                    continue

                # Compute string similarity and filter
                filtered_candidates = string_similarity.filter_candidates(
                    entity,
                    blocking_result.candidates,
                    threshold=(config.review_threshold or 0.50),
                )

                for candidate, scores in filtered_candidates:
                    if candidate.id == entity.id:
                        continue

                    pair_key = tuple(sorted([str(entity.id), str(candidate.id)]))
                    if pair_key in processed_pairs:
                        continue
                    processed_pairs.add(pair_key)

                    candidates_found += 1
                    combined_score = scores.combined_score
                    scores_dict = scores.to_dict() if hasattr(scores, 'to_dict') else {}

                    # Determine action based on score
                    if combined_score >= (config.auto_merge_threshold or 0.90):
                        # Auto-merge high confidence pairs
                        merged = _auto_merge_pair(
                            ctx.db, entity, candidate, combined_score,
                            scores_dict, UUID(tenant_id)
                        )
                        if merged:
                            auto_merged += 1
                        else:
                            # If merge failed, queue for review
                            _queue_for_review(
                                ctx.db, entity, candidate, combined_score,
                                scores_dict, UUID(tenant_id), priority=50
                            )
                            review_queued += 1
                    else:
                        # Queue medium confidence for review
                        _queue_for_review(
                            ctx.db, entity, candidate, combined_score,
                            scores_dict, UUID(tenant_id),
                            priority=_compute_review_priority(combined_score)
                        )
                        review_queued += 1

                processed += 1

                self.update_state(
                    state="PROGRESS",
                    meta={
                        "entities_processed": processed,
                        "total_entities": total_entities,
                        "candidates_found": candidates_found,
                        "review_queued": review_queued,
                    },
                )

            logger.info(
                "Manual consolidation completed",
                extra={
                    "tenant_id": tenant_id,
                    "entities_processed": total_entities,
                    "candidates_found": candidates_found,
                    "review_queued": review_queued,
                },
            )

            return {
                "status": "complete",
                "entities_processed": total_entities,
                "candidates_found": candidates_found,
                "auto_merged": auto_merged,
                "review_queued": review_queued,
            }

        except Exception as e:
            logger.exception(
                "Manual consolidation failed",
                extra={"tenant_id": tenant_id, "error": str(e)},
            )

            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)

            return {"status": "failed", "error": str(e)}


def _update_progress(
    job: ScrapingJob,
    db,
    processed: int,
    total: int,
    candidates: int,
    merged: int,
) -> None:
    """Update job consolidation progress."""
    if total > 0:
        job.consolidation_progress = processed / total
    job.consolidation_candidates_found = candidates
    job.consolidation_auto_merged = merged
    job.updated_at = datetime.now(timezone.utc)
    db.commit()


def _complete_job(
    job: ScrapingJob,
    db,
    entities_processed: int,
    candidates_found: int,
    auto_merged: int,
) -> None:
    """Mark job as complete."""
    job.stage = JobStage.DONE
    job.status = JobStatus.COMPLETED
    job.consolidation_progress = 1.0
    job.consolidation_candidates_found = candidates_found
    job.consolidation_auto_merged = auto_merged
    job.completed_at = datetime.now(timezone.utc)
    job.updated_at = datetime.now(timezone.utc)
    db.commit()


def _auto_merge_pair(
    db,
    entity_a: ExtractedEntity,
    entity_b: ExtractedEntity,
    confidence: float,
    similarity_scores: dict,
    tenant_id: UUID,
) -> bool:
    """
    Auto-merge two entities with high confidence.

    Performs a simplified sync merge:
    1. Determines canonical entity
    2. Creates alias for merged entity
    3. Marks merged entity as non-canonical
    4. Commits changes

    Returns True if merge succeeded, False otherwise.
    """
    import uuid as uuid_module
    from app.models.entity_alias import EntityAlias

    try:
        # Determine canonical entity (prefer higher confidence or older entity)
        if (entity_a.confidence_score or 0) >= (entity_b.confidence_score or 0):
            canonical = entity_a
            merged = entity_b
        else:
            canonical = entity_b
            merged = entity_a

        # Skip if already merged
        if not merged.is_canonical:
            logger.debug(f"Entity {merged.id} already merged, skipping")
            return True

        now = datetime.now(timezone.utc)

        # Create alias for the merged entity
        alias = EntityAlias(
            id=uuid_module.uuid4(),
            tenant_id=tenant_id,
            canonical_entity_id=canonical.id,
            alias_name=merged.name,
            alias_normalized_name=merged.normalized_name or merged.name.lower(),
            original_entity_id=merged.id,
            source_page_id=merged.source_page_id,
            merged_at=now,
            merge_reason="auto_high_confidence",
            original_entity_type=merged.entity_type,
            original_normalized_name=merged.normalized_name,
            original_description=merged.description,
            original_properties=merged.properties or {},
            original_external_ids=merged.external_ids or {},
            original_confidence_score=merged.confidence_score,
        )
        db.add(alias)

        # Mark merged entity as non-canonical and link to canonical
        merged.is_canonical = False
        merged.is_alias_of = canonical.id

        # Optionally merge properties (simple strategy: keep canonical's values)
        # For auto-merge, we keep it simple

        db.commit()

        logger.info(
            "Auto-merged entities",
            extra={
                "canonical_id": str(canonical.id),
                "merged_id": str(merged.id),
                "confidence": confidence,
            },
        )
        return True

    except Exception as e:
        db.rollback()
        logger.warning(
            "Auto-merge failed, will queue for review",
            extra={
                "entity_a_id": str(entity_a.id),
                "entity_b_id": str(entity_b.id),
                "error": str(e),
            },
        )
        return False


def _queue_for_review(
    db,
    entity_a: ExtractedEntity,
    entity_b: ExtractedEntity,
    confidence: float,
    similarity_scores: dict,
    tenant_id: UUID,
    priority: int = 50,
) -> None:
    """Queue a candidate pair for human review."""
    # Check if already queued
    existing = db.execute(
        select(MergeReviewItem).where(
            MergeReviewItem.tenant_id == tenant_id,
            MergeReviewItem.entity_a_id == entity_a.id,
            MergeReviewItem.entity_b_id == entity_b.id,
            MergeReviewItem.status == MergeReviewStatus.PENDING,
        )
    ).scalar_one_or_none()

    if existing:
        return

    # Also check reverse order
    existing_reverse = db.execute(
        select(MergeReviewItem).where(
            MergeReviewItem.tenant_id == tenant_id,
            MergeReviewItem.entity_a_id == entity_b.id,
            MergeReviewItem.entity_b_id == entity_a.id,
            MergeReviewItem.status == MergeReviewStatus.PENDING,
        )
    ).scalar_one_or_none()

    if existing_reverse:
        return

    review_item = MergeReviewItem(
        tenant_id=tenant_id,
        entity_a_id=entity_a.id,
        entity_b_id=entity_b.id,
        confidence=confidence,
        similarity_scores=similarity_scores,
        status=MergeReviewStatus.PENDING,
        review_priority=priority,
    )
    db.add(review_item)


def _compute_review_priority(confidence: float) -> int:
    """
    Compute review priority (higher = more urgent).

    Borderline cases (near 0.7-0.8) get highest priority since
    they are most likely to benefit from human judgment.
    """
    if 0.65 <= confidence <= 0.85:
        return 100  # Borderline - highest priority
    elif 0.5 <= confidence < 0.65:
        return 75  # Lower confidence
    elif 0.85 < confidence < 0.90:
        return 50  # Nearly auto-merge threshold
    else:
        return 25  # Other cases


def _emit_consolidation_completed_event(
    job: ScrapingJob,
    tenant_id: str,
    entities_processed: int,
    candidates_found: int,
    auto_merged: int,
) -> None:
    """Emit ConsolidationCompleted event."""
    try:
        from app.eventsourcing.stores.factory import get_event_store_sync
        from app.eventsourcing.events.consolidation import ConsolidationCompleted

        event_store = get_event_store_sync()
        event = ConsolidationCompleted(
            aggregate_id=str(job.id),
            tenant_id=tenant_id,
            job_id=job.id,
            entities_processed=entities_processed,
            candidates_found=candidates_found,
            auto_merged=auto_merged,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        event_store.append_sync(event)
    except Exception as e:
        logger.warning(f"Failed to emit ConsolidationCompleted event: {e}")
