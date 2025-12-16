"""Unit tests for consolidation domain events."""

from uuid import uuid4

import pytest

from app.eventsourcing.events.consolidation import (
    AliasCreated,
    BatchConsolidationCompleted,
    BatchConsolidationFailed,
    BatchConsolidationProgress,
    BatchConsolidationStarted,
    ConsolidationConfigUpdated,
    EntitiesMerged,
    EntitySplit,
    MergeCandidateIdentified,
    MergeQueuedForReview,
    MergeReviewDecision,
    MergeUndone,
)


class TestMergeCandidateIdentifiedEvent:
    """Tests for MergeCandidateIdentified event."""

    def test_creation_with_required_fields(self):
        """Test event creation with required fields."""
        event = MergeCandidateIdentified(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            entity_a_id=uuid4(),
            entity_b_id=uuid4(),
            combined_confidence=0.85,
        )
        assert event.event_type == "MergeCandidateIdentified"
        assert event.aggregate_type == "ConsolidationProcess"
        assert event.combined_confidence == 0.85

    def test_default_values(self):
        """Test default values for optional fields."""
        event = MergeCandidateIdentified(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            entity_a_id=uuid4(),
            entity_b_id=uuid4(),
            combined_confidence=0.75,
        )
        assert event.similarity_scores == {}
        assert event.blocking_keys_matched == []
        assert event.identified_by == "extraction"

    def test_confidence_validation_valid(self):
        """Test valid confidence values."""
        for confidence in [0.0, 0.5, 1.0]:
            event = MergeCandidateIdentified(
                aggregate_id=uuid4(),
                tenant_id=uuid4(),
                entity_a_id=uuid4(),
                entity_b_id=uuid4(),
                combined_confidence=confidence,
            )
            assert event.combined_confidence == confidence

    def test_confidence_validation_invalid_high(self):
        """Test invalid confidence > 1.0."""
        with pytest.raises(ValueError):
            MergeCandidateIdentified(
                aggregate_id=uuid4(),
                tenant_id=uuid4(),
                entity_a_id=uuid4(),
                entity_b_id=uuid4(),
                combined_confidence=1.5,
            )

    def test_confidence_validation_invalid_negative(self):
        """Test invalid negative confidence."""
        with pytest.raises(ValueError):
            MergeCandidateIdentified(
                aggregate_id=uuid4(),
                tenant_id=uuid4(),
                entity_a_id=uuid4(),
                entity_b_id=uuid4(),
                combined_confidence=-0.1,
            )


class TestEntitiesMergedEvent:
    """Tests for EntitiesMerged event."""

    def test_creation_with_required_fields(self):
        """Test event creation with required fields."""
        event = EntitiesMerged(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            canonical_entity_id=uuid4(),
            merged_entity_ids=[uuid4()],
            merge_reason="auto_high_confidence",
        )
        assert event.event_type == "EntitiesMerged"
        assert event.aggregate_type == "ConsolidationProcess"
        assert event.merge_reason == "auto_high_confidence"

    def test_default_values(self):
        """Test default values for optional fields."""
        event = EntitiesMerged(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            canonical_entity_id=uuid4(),
            merged_entity_ids=[uuid4()],
            merge_reason="user_approved",
        )
        assert event.similarity_scores == {}
        assert event.property_merge_details == {}
        assert event.relationship_transfer_count == 0
        assert event.merged_by_user_id is None

    def test_merged_entity_ids_required(self):
        """Test that merged_entity_ids must have at least one ID."""
        with pytest.raises(ValueError):
            EntitiesMerged(
                aggregate_id=uuid4(),
                tenant_id=uuid4(),
                canonical_entity_id=uuid4(),
                merged_entity_ids=[],
                merge_reason="test",
            )

    def test_with_multiple_merged_entities(self):
        """Test with multiple merged entities."""
        event = EntitiesMerged(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            canonical_entity_id=uuid4(),
            merged_entity_ids=[uuid4(), uuid4(), uuid4()],
            merge_reason="batch",
        )
        assert len(event.merged_entity_ids) == 3

    def test_with_user_id(self):
        """Test with merged_by_user_id."""
        user_id = uuid4()
        event = EntitiesMerged(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            canonical_entity_id=uuid4(),
            merged_entity_ids=[uuid4()],
            merge_reason="user_approved",
            merged_by_user_id=user_id,
        )
        assert event.merged_by_user_id == user_id


class TestAliasCreatedEvent:
    """Tests for AliasCreated event."""

    def test_creation(self):
        """Test event creation."""
        event = AliasCreated(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            alias_id=uuid4(),
            canonical_entity_id=uuid4(),
            alias_name="Domain Event",
            original_entity_id=uuid4(),
        )
        assert event.event_type == "AliasCreated"
        assert event.alias_name == "Domain Event"

    def test_with_merge_event_id(self):
        """Test with merge_event_id for provenance."""
        merge_event_id = uuid4()
        event = AliasCreated(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            alias_id=uuid4(),
            canonical_entity_id=uuid4(),
            alias_name="Test",
            original_entity_id=uuid4(),
            merge_event_id=merge_event_id,
        )
        assert event.merge_event_id == merge_event_id


class TestMergeQueuedForReviewEvent:
    """Tests for MergeQueuedForReview event."""

    def test_creation(self):
        """Test event creation."""
        event = MergeQueuedForReview(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            entity_a_id=uuid4(),
            entity_b_id=uuid4(),
            confidence=0.65,
            review_priority=0.7,
        )
        assert event.event_type == "MergeQueuedForReview"
        assert event.confidence == 0.65
        assert event.review_priority == 0.7

    def test_default_queue_reason(self):
        """Test default queue_reason."""
        event = MergeQueuedForReview(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            entity_a_id=uuid4(),
            entity_b_id=uuid4(),
            confidence=0.65,
            review_priority=0.7,
        )
        assert event.queue_reason == "medium_confidence"


class TestMergeReviewDecisionEvent:
    """Tests for MergeReviewDecision event."""

    def test_creation_approve(self):
        """Test event creation with approve decision."""
        event = MergeReviewDecision(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            review_item_id=uuid4(),
            entity_a_id=uuid4(),
            entity_b_id=uuid4(),
            decision="approve",
            reviewer_user_id=uuid4(),
            original_confidence=0.75,
        )
        assert event.event_type == "MergeReviewDecision"
        assert event.decision == "approve"

    def test_creation_reject(self):
        """Test event creation with reject decision."""
        event = MergeReviewDecision(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            review_item_id=uuid4(),
            entity_a_id=uuid4(),
            entity_b_id=uuid4(),
            decision="reject",
            reviewer_user_id=uuid4(),
            original_confidence=0.65,
        )
        assert event.decision == "reject"

    def test_with_reviewer_notes(self):
        """Test with reviewer notes."""
        event = MergeReviewDecision(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            review_item_id=uuid4(),
            entity_a_id=uuid4(),
            entity_b_id=uuid4(),
            decision="approve",
            reviewer_user_id=uuid4(),
            reviewer_notes="These are clearly the same entity",
            original_confidence=0.70,
        )
        assert event.reviewer_notes == "These are clearly the same entity"

    def test_serialization(self):
        """Test event serializes correctly."""
        event = MergeReviewDecision(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            review_item_id=uuid4(),
            entity_a_id=uuid4(),
            entity_b_id=uuid4(),
            decision="approve",
            reviewer_user_id=uuid4(),
            original_confidence=0.75,
        )
        data = event.model_dump()
        assert data["decision"] == "approve"
        assert data["original_confidence"] == 0.75


class TestMergeUndoneEvent:
    """Tests for MergeUndone event."""

    def test_creation(self):
        """Test event creation."""
        event = MergeUndone(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            original_merge_event_id=uuid4(),
            canonical_entity_id=uuid4(),
            restored_entity_ids=[uuid4()],
            original_entity_ids=[uuid4()],
            undo_reason="Entities are different concepts",
            undone_by_user_id=uuid4(),
        )
        assert event.event_type == "MergeUndone"
        assert event.undo_reason == "Entities are different concepts"


class TestEntitySplitEvent:
    """Tests for EntitySplit event."""

    def test_creation(self):
        """Test event creation."""
        new_id_1 = uuid4()
        new_id_2 = uuid4()
        event = EntitySplit(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            original_entity_id=uuid4(),
            new_entity_ids=[new_id_1, new_id_2],
            new_entity_names=["Entity A", "Entity B"],
            split_reason="Entity combines two distinct concepts",
            split_by_user_id=uuid4(),
        )
        assert event.event_type == "EntitySplit"
        assert len(event.new_entity_ids) == 2
        assert len(event.new_entity_names) == 2

    def test_new_entity_ids_min_length(self):
        """Test that new_entity_ids must have at least 2 items."""
        with pytest.raises(ValueError):
            EntitySplit(
                aggregate_id=uuid4(),
                tenant_id=uuid4(),
                original_entity_id=uuid4(),
                new_entity_ids=[uuid4()],  # Only 1
                new_entity_names=["Entity A", "Entity B"],
                split_reason="test",
                split_by_user_id=uuid4(),
            )

    def test_with_property_assignments(self):
        """Test with property assignments."""
        new_id_1 = uuid4()
        new_id_2 = uuid4()
        event = EntitySplit(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            original_entity_id=uuid4(),
            new_entity_ids=[new_id_1, new_id_2],
            new_entity_names=["Entity A", "Entity B"],
            property_assignments={
                "name": str(new_id_1),
                "description": str(new_id_2),
            },
            split_reason="test",
            split_by_user_id=uuid4(),
        )
        assert len(event.property_assignments) == 2


class TestBatchConsolidationEvents:
    """Tests for batch consolidation events."""

    def test_batch_started(self):
        """Test BatchConsolidationStarted event."""
        event = BatchConsolidationStarted(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            job_id=uuid4(),
            entity_count=1000,
            started_by_user_id=uuid4(),
        )
        assert event.event_type == "BatchConsolidationStarted"
        assert event.entity_count == 1000

    def test_batch_progress(self):
        """Test BatchConsolidationProgress event."""
        event = BatchConsolidationProgress(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            job_id=uuid4(),
            entities_processed=500,
            candidates_found=50,
            merges_performed=25,
            reviews_queued=25,
        )
        assert event.event_type == "BatchConsolidationProgress"
        assert event.entities_processed == 500

    def test_batch_completed(self):
        """Test BatchConsolidationCompleted event."""
        event = BatchConsolidationCompleted(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            job_id=uuid4(),
            entities_processed=1000,
            candidates_found=100,
            merges_performed=45,
            reviews_queued=55,
            duration_seconds=3600,
        )
        assert event.event_type == "BatchConsolidationCompleted"
        assert event.duration_seconds == 3600
        assert event.errors == []

    def test_batch_failed(self):
        """Test BatchConsolidationFailed event."""
        event = BatchConsolidationFailed(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            job_id=uuid4(),
            error_message="Database connection lost",
            entities_processed=500,
        )
        assert event.event_type == "BatchConsolidationFailed"
        assert event.error_message == "Database connection lost"


class TestConsolidationConfigUpdatedEvent:
    """Tests for ConsolidationConfigUpdated event."""

    def test_creation(self):
        """Test event creation."""
        event = ConsolidationConfigUpdated(
            aggregate_id=uuid4(),
            tenant_id=uuid4(),
            updated_fields=["auto_merge_threshold", "review_threshold"],
            old_values={"auto_merge_threshold": 0.90, "review_threshold": 0.50},
            new_values={"auto_merge_threshold": 0.85, "review_threshold": 0.45},
            updated_by_user_id=uuid4(),
        )
        assert event.event_type == "ConsolidationConfigUpdated"
        assert len(event.updated_fields) == 2
        assert event.old_values["auto_merge_threshold"] == 0.90
        assert event.new_values["auto_merge_threshold"] == 0.85
