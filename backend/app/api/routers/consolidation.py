"""
Entity Consolidation API endpoints.

This router provides endpoints for:
- Listing and computing merge candidates
- Executing merge operations (merge, undo, split)
- Managing the review queue
- Viewing merge history
- Managing consolidation configuration

Authorization is enforced using consolidation scopes:
- consolidation/read: View candidates, queue, history
- consolidation/write: Execute merges, review decisions
- consolidation/admin: Configuration changes, batch operations
"""

import logging
import math
import uuid as uuid_module
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import CurrentUserWithTenant
from app.api.dependencies.scopes import require_scopes, require_any_scope
from app.api.dependencies.tenant import TenantSession
from app.models.extracted_entity import ExtractedEntity
from app.models.merge_review_queue import MergeReviewItem, MergeReviewStatus
from app.models.merge_history import MergeHistory, MergeEventType as MergeEventTypeModel
from app.models.consolidation_config import ConsolidationConfig
from app.schemas.auth import (
    SCOPE_CONSOLIDATION_READ,
    SCOPE_CONSOLIDATION_WRITE,
    SCOPE_CONSOLIDATION_ADMIN,
)
from app.schemas.consolidation import (
    # Enums
    MergeDecision,
    ReviewDecision,
    ReviewStatus,
    MergeEventType,
    # Entity Summary
    EntitySummary,
    # Merge Candidates
    SimilarityBreakdown,
    MergeCandidateResponse,
    MergeCandidateListResponse,
    ComputeCandidatesRequest,
    ComputeCandidatesResponse,
    # Merge Operations
    MergeRequest,
    MergeResponse,
    UndoMergeRequest,
    UndoMergeResponse,
    SplitEntityRequest,
    SplitEntityResponse,
    # Review Queue
    ReviewQueueItemResponse,
    ReviewQueueListResponse,
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewQueueStatsResponse,
    # Merge History
    MergeHistoryItemResponse,
    MergeHistoryListResponse,
    # Configuration
    ConsolidationConfigResponse,
    ConsolidationConfigRequest,
    # Batch Operations
    BatchConsolidationRequest,
    BatchConsolidationResponse,
)
from app.services.consolidation import (
    MergeService,
    MergeError,
    MergeValidationError,
    MergeUndoError,
    EntitySplitError,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/consolidation", tags=["consolidation"])

# Type alias for tenant-aware database session dependency
DbSession = TenantSession


def _build_paginated_response(
    items: list,
    total: int,
    page: int,
    page_size: int,
    response_class,
):
    """Build a paginated response with metadata."""
    pages = max(1, math.ceil(total / page_size))
    return response_class(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )


def _entity_to_summary(entity: ExtractedEntity) -> EntitySummary:
    """Convert ExtractedEntity to EntitySummary response."""
    return EntitySummary(
        id=entity.id,
        name=entity.name,
        normalized_name=entity.normalized_name,
        entity_type=entity.entity_type.value if hasattr(entity.entity_type, "value") else str(entity.entity_type),
        description=entity.description,
        is_canonical=entity.is_canonical,
    )


# =============================================================================
# Merge Candidate Endpoints (P4-003)
# =============================================================================


@router.get(
    "/candidates",
    response_model=MergeCandidateListResponse,
    summary="List merge candidates",
    description="Get a paginated list of identified merge candidates.",
    dependencies=[Depends(require_scopes(SCOPE_CONSOLIDATION_READ))],
)
async def list_merge_candidates(
    user: CurrentUserWithTenant,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0, description="Minimum confidence filter"),
    max_confidence: float = Query(1.0, ge=0.0, le=1.0, description="Maximum confidence filter"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    status_filter: Optional[str] = Query(None, description="Filter by review status (pending, approved, rejected)"),
) -> MergeCandidateListResponse:
    """
    List merge candidates identified by the consolidation system.

    Returns candidates from the review queue with their similarity scores
    and recommendations.
    """
    tenant_id = UUID(user.tenant_id)

    # Build query
    query = select(MergeReviewItem).where(
        MergeReviewItem.tenant_id == tenant_id,
        MergeReviewItem.confidence >= min_confidence,
        MergeReviewItem.confidence <= max_confidence,
    )

    # Filter by status
    if status_filter:
        try:
            status_enum = MergeReviewStatus(status_filter)
            query = query.where(MergeReviewItem.status == status_enum)
        except ValueError:
            pass  # Ignore invalid status

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    query = query.order_by(MergeReviewItem.review_priority.desc(), MergeReviewItem.created_at.desc())
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    review_items = result.scalars().all()

    # Load related entities
    entity_ids = set()
    for item in review_items:
        entity_ids.add(item.entity_a_id)
        entity_ids.add(item.entity_b_id)

    entities_result = await db.execute(
        select(ExtractedEntity).where(ExtractedEntity.id.in_(entity_ids))
    )
    entities_map = {e.id: e for e in entities_result.scalars().all()}

    # Filter by entity type if specified
    items = []
    for item in review_items:
        entity_a = entities_map.get(item.entity_a_id)
        entity_b = entities_map.get(item.entity_b_id)

        if not entity_a or not entity_b:
            continue

        # Filter by entity type
        if entity_type:
            a_type = entity_a.entity_type.value if hasattr(entity_a.entity_type, "value") else str(entity_a.entity_type)
            b_type = entity_b.entity_type.value if hasattr(entity_b.entity_type, "value") else str(entity_b.entity_type)
            if a_type != entity_type and b_type != entity_type:
                continue

        # Determine decision based on confidence
        decision = _get_decision_for_confidence(item.confidence)

        # Build similarity breakdown from stored scores
        breakdown = _build_similarity_breakdown(item.similarity_scores)

        items.append(
            MergeCandidateResponse(
                entity_a=_entity_to_summary(entity_a),
                entity_b=_entity_to_summary(entity_b),
                combined_score=item.confidence,
                confidence=item.confidence,
                decision=decision,
                similarity_breakdown=breakdown,
                blocking_keys=item.similarity_scores.get("blocking_keys", []),
                review_item_id=item.id,
                computed_at=item.created_at,
            )
        )

    return _build_paginated_response(items, total, page, page_size, MergeCandidateListResponse)


@router.get(
    "/candidates/{entity_id}",
    response_model=MergeCandidateListResponse,
    summary="Get candidates for specific entity",
    description="Get merge candidates involving a specific entity.",
    dependencies=[Depends(require_scopes(SCOPE_CONSOLIDATION_READ))],
)
async def get_entity_candidates(
    entity_id: UUID,
    user: CurrentUserWithTenant,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> MergeCandidateListResponse:
    """
    Get merge candidates for a specific entity.

    Returns all candidate pairs where the entity appears as either entity_a or entity_b.
    """
    tenant_id = UUID(user.tenant_id)

    # Verify entity exists
    entity_result = await db.execute(
        select(ExtractedEntity).where(
            ExtractedEntity.id == entity_id,
            ExtractedEntity.tenant_id == tenant_id,
        )
    )
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    # Build query for candidates involving this entity
    query = select(MergeReviewItem).where(
        MergeReviewItem.tenant_id == tenant_id,
        or_(
            MergeReviewItem.entity_a_id == entity_id,
            MergeReviewItem.entity_b_id == entity_id,
        ),
    )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(MergeReviewItem.confidence.desc())
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    review_items = result.scalars().all()

    # Load related entities
    entity_ids = set()
    for item in review_items:
        entity_ids.add(item.entity_a_id)
        entity_ids.add(item.entity_b_id)

    entities_result = await db.execute(
        select(ExtractedEntity).where(ExtractedEntity.id.in_(entity_ids))
    )
    entities_map = {e.id: e for e in entities_result.scalars().all()}

    items = []
    for item in review_items:
        entity_a = entities_map.get(item.entity_a_id)
        entity_b = entities_map.get(item.entity_b_id)

        if not entity_a or not entity_b:
            continue

        decision = _get_decision_for_confidence(item.confidence)
        breakdown = _build_similarity_breakdown(item.similarity_scores)

        items.append(
            MergeCandidateResponse(
                entity_a=_entity_to_summary(entity_a),
                entity_b=_entity_to_summary(entity_b),
                combined_score=item.confidence,
                confidence=item.confidence,
                decision=decision,
                similarity_breakdown=breakdown,
                blocking_keys=item.similarity_scores.get("blocking_keys", []),
                review_item_id=item.id,
                computed_at=item.created_at,
            )
        )

    return _build_paginated_response(items, total, page, page_size, MergeCandidateListResponse)


@router.post(
    "/candidates/compute",
    response_model=ComputeCandidatesResponse,
    summary="Trigger candidate computation",
    description="Start a background job to compute merge candidates.",
    dependencies=[Depends(require_scopes(SCOPE_CONSOLIDATION_WRITE))],
)
async def compute_candidates(
    request: ComputeCandidatesRequest,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> ComputeCandidatesResponse:
    """
    Trigger computation of merge candidates.

    This starts a background job that:
    1. Runs blocking to find candidate pairs
    2. Computes string similarity
    3. Optionally computes embedding and graph similarity
    4. Queues medium-confidence candidates for review
    5. Auto-merges high-confidence candidates (if enabled)

    Returns a job ID for tracking progress.
    """
    from app.tasks.consolidation import run_consolidation_manual

    tenant_id = user.tenant_id

    # Convert entity IDs to strings for Celery serialization
    entity_ids_str = None
    if request.entity_ids:
        entity_ids_str = [str(eid) for eid in request.entity_ids]

    # Queue the consolidation task
    task = run_consolidation_manual.delay(tenant_id, entity_ids_str)

    logger.info(
        "Candidate computation job queued",
        extra={
            "tenant_id": tenant_id,
            "user_id": user.user_id,
            "task_id": task.id,
            "entity_ids_count": len(entity_ids_str) if entity_ids_str else "all",
        },
    )

    return ComputeCandidatesResponse(
        job_id=UUID(task.id),
        status="queued",
        entities_processed=0,
        candidates_found=0,
        message="Consolidation job has been queued. Poll for progress or check review queue when complete.",
    )


# =============================================================================
# Merge Operation Endpoints (P4-004)
# =============================================================================


@router.post(
    "/merge",
    response_model=MergeResponse,
    summary="Execute entity merge",
    description="Merge one or more entities into a canonical entity.",
    dependencies=[Depends(require_scopes(SCOPE_CONSOLIDATION_WRITE))],
)
async def execute_merge(
    request: MergeRequest,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> MergeResponse:
    """
    Execute an entity merge operation.

    Merges the specified entities into the canonical entity, creating
    alias records, transferring relationships, and recording history.
    """
    tenant_id = UUID(user.tenant_id)

    # Load canonical entity
    canonical_result = await db.execute(
        select(ExtractedEntity).where(
            ExtractedEntity.id == request.canonical_entity_id,
            ExtractedEntity.tenant_id == tenant_id,
        )
    )
    canonical_entity = canonical_result.scalar_one_or_none()
    if not canonical_entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canonical entity not found",
        )

    # Load entities to merge
    merged_result = await db.execute(
        select(ExtractedEntity).where(
            ExtractedEntity.id.in_(request.merged_entity_ids),
            ExtractedEntity.tenant_id == tenant_id,
        )
    )
    merged_entities = list(merged_result.scalars().all())

    if len(merged_entities) != len(request.merged_entity_ids):
        found_ids = {e.id for e in merged_entities}
        missing = [str(eid) for eid in request.merged_entity_ids if eid not in found_ids]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Some entities to merge were not found: {', '.join(missing)}",
        )

    # Prevent merging canonical into itself
    if request.canonical_entity_id in request.merged_entity_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot merge entity into itself",
        )

    # Execute merge
    try:
        merge_service = MergeService(db)
        result = await merge_service.merge_entities(
            canonical_entity=canonical_entity,
            merged_entities=merged_entities,
            tenant_id=tenant_id,
            merge_reason=request.merge_reason,
            similarity_scores=request.similarity_scores,
            merged_by_user_id=UUID(user.user_id) if user.user_id else None,
        )

        await db.commit()

        logger.info(
            "Merge executed successfully",
            extra={
                "tenant_id": str(tenant_id),
                "user_id": user.user_id,
                "canonical_id": str(request.canonical_entity_id),
                "merged_ids": [str(eid) for eid in request.merged_entity_ids],
            },
        )

        return MergeResponse(
            success=True,
            canonical_entity_id=result.canonical_entity_id,
            merged_entity_ids=result.merged_entity_ids,
            aliases_created=len(result.aliases_created),
            relationships_transferred=result.relationships_transferred,
            merge_history_id=result.merge_history_id,
            event_id=result.event_id,
            message="Entities merged successfully",
        )

    except MergeValidationError as e:
        logger.warning(
            "Merge validation failed",
            extra={"error": str(e), "tenant_id": str(tenant_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except MergeError as e:
        logger.error(
            "Merge operation failed",
            extra={"error": str(e), "tenant_id": str(tenant_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Merge operation failed: {str(e)}",
        )


@router.post(
    "/undo/{merge_event_id}",
    response_model=UndoMergeResponse,
    summary="Undo a merge",
    description="Undo a previous merge operation.",
    dependencies=[Depends(require_scopes(SCOPE_CONSOLIDATION_WRITE))],
)
async def undo_merge(
    merge_event_id: UUID,
    request: UndoMergeRequest,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> UndoMergeResponse:
    """
    Undo a previous merge operation.

    Restores the merged entities as separate canonical entities,
    removes alias records, and restores original relationships.
    """
    tenant_id = UUID(user.tenant_id)

    # Verify merge history exists and belongs to tenant
    history_result = await db.execute(
        select(MergeHistory).where(
            MergeHistory.event_id == merge_event_id,
            MergeHistory.tenant_id == tenant_id,
        )
    )
    history = history_result.scalar_one_or_none()

    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merge history not found",
        )

    if not history.can_undo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This merge operation cannot be undone (already undone or not a merge event)",
        )

    try:
        merge_service = MergeService(db)
        result = await merge_service.undo_merge(
            merge_event_id=merge_event_id,
            user_id=UUID(user.user_id) if user.user_id else None,
            reason=request.reason,
            restore_entity_ids=request.restore_entity_ids,
        )

        await db.commit()

        logger.info(
            "Merge undo executed successfully",
            extra={
                "tenant_id": str(tenant_id),
                "user_id": user.user_id,
                "original_merge_id": str(merge_event_id),
            },
        )

        return UndoMergeResponse(
            success=True,
            original_merge_event_id=result.original_merge_event_id,
            restored_entity_ids=result.restored_entity_ids,
            aliases_removed=result.aliases_removed,
            relationships_restored=result.relationships_restored,
            undo_history_id=result.undo_history_id,
            message="Merge undone successfully",
        )

    except MergeUndoError as e:
        logger.warning(
            "Merge undo failed",
            extra={"error": str(e), "tenant_id": str(tenant_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/split/{entity_id}",
    response_model=SplitEntityResponse,
    summary="Split an entity",
    description="Split an entity into multiple new entities.",
    dependencies=[Depends(require_scopes(SCOPE_CONSOLIDATION_WRITE))],
)
async def split_entity(
    entity_id: UUID,
    request: SplitEntityRequest,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> SplitEntityResponse:
    """
    Split an entity into multiple new entities.

    Creates new entities from the split definitions, redistributes
    relationships and aliases according to assignments, and marks
    the original entity as non-canonical.
    """
    tenant_id = UUID(user.tenant_id)

    # Verify entity exists
    entity_result = await db.execute(
        select(ExtractedEntity).where(
            ExtractedEntity.id == entity_id,
            ExtractedEntity.tenant_id == tenant_id,
        )
    )
    entity = entity_result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    try:
        merge_service = MergeService(db)

        # Convert relationship_assignments keys from string to UUID
        rel_assignments = None
        if request.relationship_assignments:
            rel_assignments = {
                UUID(k): v for k, v in request.relationship_assignments.items()
            }

        # Convert alias_assignments keys from string to UUID
        alias_assignments = None
        if request.alias_assignments:
            alias_assignments = {
                UUID(k): v for k, v in request.alias_assignments.items()
            }

        result = await merge_service.split_entity(
            entity_id=entity_id,
            split_definitions=request.split_definitions,
            relationship_assignments=rel_assignments,
            alias_assignments=alias_assignments,
            user_id=UUID(user.user_id) if user.user_id else None,
            reason=request.reason,
        )

        await db.commit()

        logger.info(
            "Entity split executed successfully",
            extra={
                "tenant_id": str(tenant_id),
                "user_id": user.user_id,
                "original_entity_id": str(entity_id),
                "new_entity_count": len(result.new_entity_ids),
            },
        )

        return SplitEntityResponse(
            success=True,
            original_entity_id=result.original_entity_id,
            new_entity_ids=result.new_entity_ids,
            relationships_redistributed=result.relationships_redistributed,
            aliases_redistributed=result.aliases_redistributed,
            split_history_id=result.split_history_id,
            message="Entity split successfully",
        )

    except EntitySplitError as e:
        logger.warning(
            "Entity split failed",
            extra={"error": str(e), "tenant_id": str(tenant_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =============================================================================
# Review Queue Endpoints (P4-005)
# =============================================================================


@router.get(
    "/review-queue",
    response_model=ReviewQueueListResponse,
    summary="List review queue items",
    description="Get a paginated list of items pending human review.",
    dependencies=[Depends(require_scopes(SCOPE_CONSOLIDATION_READ))],
)
async def list_review_queue(
    user: CurrentUserWithTenant,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query("pending", description="Filter by status"),
    sort_by: str = Query("priority", description="Sort by: priority, confidence, created_at"),
) -> ReviewQueueListResponse:
    """
    List items in the review queue.

    By default returns pending items sorted by review priority (highest uncertainty first).
    """
    tenant_id = UUID(user.tenant_id)

    # Build query
    query = select(MergeReviewItem).where(MergeReviewItem.tenant_id == tenant_id)

    # Apply status filter
    if status_filter:
        try:
            status_enum = MergeReviewStatus(status_filter)
            query = query.where(MergeReviewItem.status == status_enum)
        except ValueError:
            pass  # Ignore invalid status

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply sorting
    if sort_by == "priority":
        query = query.order_by(MergeReviewItem.review_priority.desc())
    elif sort_by == "confidence":
        query = query.order_by(MergeReviewItem.confidence.desc())
    else:
        query = query.order_by(MergeReviewItem.created_at.desc())

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    review_items = result.scalars().all()

    # Load related entities
    entity_ids = set()
    for item in review_items:
        entity_ids.add(item.entity_a_id)
        entity_ids.add(item.entity_b_id)

    entities_result = await db.execute(
        select(ExtractedEntity).where(ExtractedEntity.id.in_(entity_ids))
    )
    entities_map = {e.id: e for e in entities_result.scalars().all()}

    items = []
    for item in review_items:
        entity_a = entities_map.get(item.entity_a_id)
        entity_b = entities_map.get(item.entity_b_id)

        if not entity_a or not entity_b:
            continue

        items.append(
            ReviewQueueItemResponse(
                id=item.id,
                entity_a=_entity_to_summary(entity_a),
                entity_b=_entity_to_summary(entity_b),
                confidence=item.confidence,
                review_priority=item.review_priority,
                similarity_scores=item.similarity_scores,
                status=ReviewStatus(item.status.value),
                reviewed_by_name=None,  # Would need to load user
                reviewed_at=item.reviewed_at,
                reviewer_notes=item.reviewer_notes,
                created_at=item.created_at,
            )
        )

    return _build_paginated_response(items, total, page, page_size, ReviewQueueListResponse)


@router.post(
    "/review-queue/{item_id}/decide",
    response_model=ReviewDecisionResponse,
    summary="Submit review decision",
    description="Approve, reject, or defer a merge candidate.",
    dependencies=[Depends(require_scopes(SCOPE_CONSOLIDATION_WRITE))],
)
async def submit_review_decision(
    item_id: UUID,
    request: ReviewDecisionRequest,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> ReviewDecisionResponse:
    """
    Submit a review decision for a merge candidate.

    If approved, can optionally execute the merge immediately.
    """
    tenant_id = UUID(user.tenant_id)

    # Load review item
    item_result = await db.execute(
        select(MergeReviewItem).where(
            MergeReviewItem.id == item_id,
            MergeReviewItem.tenant_id == tenant_id,
        )
    )
    item = item_result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review queue item not found",
        )

    if item.status != MergeReviewStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Item has already been reviewed (status: {item.status.value})",
        )

    # Update review item
    now = datetime.now(timezone.utc)
    if request.decision == ReviewDecision.APPROVE:
        item.status = MergeReviewStatus.APPROVED
    elif request.decision == ReviewDecision.REJECT:
        item.status = MergeReviewStatus.REJECTED
    else:
        item.status = MergeReviewStatus.DEFERRED

    item.reviewed_at = now
    item.reviewed_by = UUID(user.user_id) if user.user_id else None
    item.reviewer_notes = request.notes

    merge_result = None
    merge_executed = False

    # If approved, execute merge
    if request.decision == ReviewDecision.APPROVE:
        try:
            # Determine canonical entity
            if request.select_canonical:
                canonical_id = request.select_canonical
                if canonical_id == item.entity_a_id:
                    merged_id = item.entity_b_id
                elif canonical_id == item.entity_b_id:
                    merged_id = item.entity_a_id
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="select_canonical must be one of the entities in the pair",
                    )
            else:
                # Default: entity_a is canonical
                canonical_id = item.entity_a_id
                merged_id = item.entity_b_id

            # Load entities
            entities_result = await db.execute(
                select(ExtractedEntity).where(
                    ExtractedEntity.id.in_([canonical_id, merged_id])
                )
            )
            entities = {e.id: e for e in entities_result.scalars().all()}

            canonical_entity = entities.get(canonical_id)
            merged_entity = entities.get(merged_id)

            if not canonical_entity or not merged_entity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One or both entities no longer exist",
                )

            merge_service = MergeService(db)
            result = await merge_service.merge_entities(
                canonical_entity=canonical_entity,
                merged_entities=[merged_entity],
                tenant_id=tenant_id,
                merge_reason="user_approved",
                similarity_scores=item.similarity_scores,
                merged_by_user_id=UUID(user.user_id) if user.user_id else None,
            )

            merge_executed = True
            merge_result = MergeResponse(
                success=True,
                canonical_entity_id=result.canonical_entity_id,
                merged_entity_ids=result.merged_entity_ids,
                aliases_created=len(result.aliases_created),
                relationships_transferred=result.relationships_transferred,
                merge_history_id=result.merge_history_id,
                event_id=result.event_id,
            )

        except MergeError as e:
            logger.warning(
                "Merge after approval failed",
                extra={"error": str(e), "item_id": str(item_id)},
            )
            # Still record the approval, but note the merge failed
            item.reviewer_notes = (item.reviewer_notes or "") + f"\n[Merge failed: {str(e)}]"

    await db.commit()

    logger.info(
        "Review decision submitted",
        extra={
            "tenant_id": str(tenant_id),
            "user_id": user.user_id,
            "item_id": str(item_id),
            "decision": request.decision.value,
            "merge_executed": merge_executed,
        },
    )

    return ReviewDecisionResponse(
        success=True,
        review_item_id=item_id,
        decision=request.decision,
        merge_executed=merge_executed,
        merge_result=merge_result,
        message=f"Decision recorded: {request.decision.value}",
    )


@router.get(
    "/review-queue/stats",
    response_model=ReviewQueueStatsResponse,
    summary="Get review queue statistics",
    description="Get statistics about the review queue.",
    dependencies=[Depends(require_scopes(SCOPE_CONSOLIDATION_READ))],
)
async def get_review_queue_stats(
    user: CurrentUserWithTenant,
    db: DbSession,
) -> ReviewQueueStatsResponse:
    """
    Get statistics about the review queue.

    Returns counts by status, average confidence, and entity type breakdown.
    """
    tenant_id = UUID(user.tenant_id)

    # Get counts by status
    status_counts = {}
    for status_value in MergeReviewStatus:
        count_result = await db.execute(
            select(func.count()).where(
                MergeReviewItem.tenant_id == tenant_id,
                MergeReviewItem.status == status_value,
            )
        )
        status_counts[status_value.value] = count_result.scalar() or 0

    # Get average confidence for pending items
    avg_result = await db.execute(
        select(func.avg(MergeReviewItem.confidence)).where(
            MergeReviewItem.tenant_id == tenant_id,
            MergeReviewItem.status == MergeReviewStatus.PENDING,
        )
    )
    avg_confidence = avg_result.scalar() or 0.0

    # Get oldest pending item age
    oldest_result = await db.execute(
        select(func.min(MergeReviewItem.created_at)).where(
            MergeReviewItem.tenant_id == tenant_id,
            MergeReviewItem.status == MergeReviewStatus.PENDING,
        )
    )
    oldest_created = oldest_result.scalar()
    oldest_age_hours = None
    if oldest_created:
        age = datetime.now(timezone.utc) - oldest_created.replace(tzinfo=timezone.utc)
        oldest_age_hours = age.total_seconds() / 3600

    # Get counts by entity type (would need to join with entities)
    # For now, return empty dict
    by_entity_type: dict[str, int] = {}

    return ReviewQueueStatsResponse(
        total_pending=status_counts.get("pending", 0),
        total_approved=status_counts.get("approved", 0),
        total_rejected=status_counts.get("rejected", 0),
        total_deferred=status_counts.get("deferred", 0),
        total_expired=status_counts.get("expired", 0),
        avg_confidence=float(avg_confidence),
        oldest_pending_age_hours=oldest_age_hours,
        by_entity_type=by_entity_type,
    )


# =============================================================================
# Merge History Endpoints
# =============================================================================


@router.get(
    "/history",
    response_model=MergeHistoryListResponse,
    summary="List merge history",
    description="Get a paginated list of merge operations.",
    dependencies=[Depends(require_scopes(SCOPE_CONSOLIDATION_READ))],
)
async def list_merge_history(
    user: CurrentUserWithTenant,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    entity_id: Optional[UUID] = Query(None, description="Filter by entity involvement"),
) -> MergeHistoryListResponse:
    """
    Get merge operation history.

    Shows all merge, undo, and split operations with their details.
    """
    tenant_id = UUID(user.tenant_id)

    # Build query
    query = select(MergeHistory).where(MergeHistory.tenant_id == tenant_id)

    # Filter by event type
    if event_type:
        try:
            type_enum = MergeEventTypeModel(event_type)
            query = query.where(MergeHistory.event_type == type_enum)
        except ValueError:
            pass

    # Filter by entity involvement
    if entity_id:
        query = query.where(MergeHistory.affected_entity_ids.any(entity_id))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(MergeHistory.performed_at.desc())
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    history_items = result.scalars().all()

    # Load canonical entities
    canonical_ids = [h.canonical_entity_id for h in history_items if h.canonical_entity_id]
    entities_map = {}
    if canonical_ids:
        entities_result = await db.execute(
            select(ExtractedEntity).where(ExtractedEntity.id.in_(canonical_ids))
        )
        entities_map = {e.id: e for e in entities_result.scalars().all()}

    items = []
    for history in history_items:
        canonical_entity = None
        if history.canonical_entity_id and history.canonical_entity_id in entities_map:
            canonical_entity = _entity_to_summary(entities_map[history.canonical_entity_id])

        items.append(
            MergeHistoryItemResponse(
                id=history.id,
                event_id=history.event_id,
                event_type=MergeEventType(history.event_type.value),
                canonical_entity=canonical_entity,
                affected_entity_ids=history.affected_entity_ids,
                merge_reason=history.merge_reason,
                similarity_scores=history.similarity_scores,
                performed_by_name=None,  # Would need to load user
                performed_at=history.performed_at,
                undone=history.undone,
                undone_at=history.undone_at,
                undone_by_name=None,  # Would need to load user
                undo_reason=history.undo_reason,
                can_undo=history.can_undo,
            )
        )

    return _build_paginated_response(items, total, page, page_size, MergeHistoryListResponse)


# =============================================================================
# Configuration Endpoints (P4-006)
# =============================================================================


@router.get(
    "/config",
    response_model=ConsolidationConfigResponse,
    summary="Get consolidation config",
    description="Get the tenant's consolidation configuration.",
    dependencies=[Depends(require_scopes(SCOPE_CONSOLIDATION_READ))],
)
async def get_consolidation_config(
    user: CurrentUserWithTenant,
    db: DbSession,
) -> ConsolidationConfigResponse:
    """
    Get the tenant's consolidation configuration.

    Returns current thresholds, feature toggles, and weights.
    If no config exists, returns default values.
    """
    tenant_id = UUID(user.tenant_id)

    config_result = await db.execute(
        select(ConsolidationConfig).where(ConsolidationConfig.tenant_id == tenant_id)
    )
    config = config_result.scalar_one_or_none()

    if not config:
        # Return defaults
        defaults = ConsolidationConfig.get_defaults()
        return ConsolidationConfigResponse(
            tenant_id=tenant_id,
            auto_merge_threshold=defaults["auto_merge_threshold"],
            review_threshold=defaults["review_threshold"],
            max_block_size=defaults["max_block_size"],
            enable_embedding_similarity=defaults["enable_embedding_similarity"],
            enable_graph_similarity=defaults["enable_graph_similarity"],
            enable_auto_consolidation=defaults["enable_auto_consolidation"],
            embedding_model=defaults["embedding_model"],
            feature_weights=defaults["feature_weights"],
            created_at=datetime.now(timezone.utc),
            updated_at=None,
        )

    return ConsolidationConfigResponse.model_validate(config)


@router.put(
    "/config",
    response_model=ConsolidationConfigResponse,
    summary="Update consolidation config",
    description="Update the tenant's consolidation configuration.",
    dependencies=[Depends(require_scopes(SCOPE_CONSOLIDATION_ADMIN))],
)
async def update_consolidation_config(
    request: ConsolidationConfigRequest,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> ConsolidationConfigResponse:
    """
    Update the tenant's consolidation configuration.

    Only updates fields that are provided in the request.
    Requires consolidation/admin scope.
    """
    tenant_id = UUID(user.tenant_id)

    # Load or create config
    config_result = await db.execute(
        select(ConsolidationConfig).where(ConsolidationConfig.tenant_id == tenant_id)
    )
    config = config_result.scalar_one_or_none()

    if not config:
        # Create new config with defaults
        config = ConsolidationConfig(tenant_id=tenant_id)
        db.add(config)

    # Update provided fields
    update_fields = request.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        if value is not None:
            setattr(config, field, value)

    # Validate thresholds
    if config.review_threshold >= config.auto_merge_threshold:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="review_threshold must be less than auto_merge_threshold",
        )

    config.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(config)

    logger.info(
        "Consolidation config updated",
        extra={
            "tenant_id": str(tenant_id),
            "user_id": user.user_id,
            "updated_fields": list(update_fields.keys()),
        },
    )

    return ConsolidationConfigResponse.model_validate(config)


# =============================================================================
# Batch Operations Endpoints
# =============================================================================


@router.post(
    "/batch",
    response_model=BatchConsolidationResponse,
    summary="Run batch consolidation",
    description="Start a batch consolidation job.",
    dependencies=[Depends(require_scopes(SCOPE_CONSOLIDATION_ADMIN))],
)
async def run_batch_consolidation(
    request: BatchConsolidationRequest,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> BatchConsolidationResponse:
    """
    Start a batch consolidation job.

    Processes all entities (or filtered by type), finds candidates,
    and auto-merges high-confidence matches.

    Requires consolidation/admin scope.
    """
    from app.tasks.consolidation import run_consolidation_manual

    tenant_id = UUID(user.tenant_id)
    job_id = uuid_module.uuid4()

    logger.info(
        "Batch consolidation requested",
        extra={
            "tenant_id": str(tenant_id),
            "user_id": user.user_id,
            "job_id": str(job_id),
            "entity_type": request.entity_type,
            "dry_run": request.dry_run,
        },
    )

    # Queue the Celery task
    task = run_consolidation_manual.delay(
        tenant_id=str(tenant_id),
        entity_ids=None,  # Process all entities
    )

    return BatchConsolidationResponse(
        job_id=UUID(task.id) if task.id else job_id,
        status="queued",
        dry_run=request.dry_run,
        merges_executed=0,
        merges_skipped=0,
        errors=[],
        message=f"Batch consolidation job queued. Task ID: {task.id}",
    )


# =============================================================================
# Helper Functions
# =============================================================================


def _get_decision_for_confidence(confidence: float) -> MergeDecision:
    """Determine merge decision based on confidence score."""
    if confidence >= 0.90:
        return MergeDecision.AUTO_MERGE
    elif confidence >= 0.50:
        return MergeDecision.REVIEW
    else:
        return MergeDecision.REJECT


def _build_similarity_breakdown(scores: dict) -> SimilarityBreakdown:
    """Build similarity breakdown from stored scores dict."""
    return SimilarityBreakdown(
        jaro_winkler=scores.get("jaro_winkler"),
        levenshtein=scores.get("levenshtein"),
        trigram=scores.get("trigram"),
        soundex_match=scores.get("soundex") == 1.0 if "soundex" in scores else None,
        metaphone_match=scores.get("metaphone") == 1.0 if "metaphone" in scores else None,
        embedding_cosine=scores.get("embedding_cosine"),
        graph_neighborhood=scores.get("graph_neighborhood"),
        type_match=scores.get("type_match") == 1.0 if "type_match" in scores else None,
        same_page=scores.get("same_page") == 1.0 if "same_page" in scores else None,
    )
