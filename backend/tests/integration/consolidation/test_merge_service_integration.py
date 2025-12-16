"""
Integration tests for MergeService.

Tests the full merge workflow against a real database, including:
- Complete merge execution with real entities
- Property merging with different strategies
- Relationship transfer with real entity relationships
- EntityAlias creation and querying
- MergeHistory record creation
- Domain event emission
- Tenant isolation during merges
- Merge validation edge cases
"""

import uuid
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.eventsourcing.events.consolidation import AliasCreated, EntitiesMerged
from app.models import (
    EntityType,
    ExtractionMethod,
    ExtractedEntity,
    EntityRelationship,
    Tenant,
)
from app.models.entity_alias import EntityAlias
from app.models.merge_history import MergeEventType, MergeHistory
from app.services.consolidation import (
    MergeService,
    MergeResult,
    MergeError,
    MergeValidationError,
    PropertyMergeStrategy,
)


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def merge_entities_with_relationships(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraped_page_acme,
):
    """
    Create entities with relationships for merge testing.

    Creates:
    - entity_a: John Smith (PERSON) with properties
    - entity_b: Jon Smith (PERSON) - duplicate to merge
    - entity_c: External entity with relationship to entity_b
    - entity_d: External entity with relationship from entity_b
    """
    from tests.integration.consolidation.conftest import create_entity

    entity_a = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "John Smith",
        EntityType.PERSON,
        properties={
            "role": "Engineer",
            "department": "R&D",
            "tags": ["tech", "lead"],
        },
        confidence_score=0.95,
    )
    entity_a.description = "Senior engineer at ACME Corp"
    entity_a.external_ids = {"linkedin": "john-smith-123"}

    entity_b = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "Jon Smith",
        EntityType.PERSON,
        properties={
            "role": "Developer",
            "skills": ["Python", "JavaScript"],
            "tags": ["developer", "backend"],
        },
        confidence_score=0.88,
    )
    entity_b.description = "Software developer"
    entity_b.external_ids = {"github": "jonsmith"}

    entity_c = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "ACME Corp",
        EntityType.ORGANIZATION,
        properties={"industry": "Technology"},
    )

    entity_d = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "Python Programming",
        EntityType.CONCEPT,
        properties={"category": "skill"},
    )

    db_session.add_all([entity_a, entity_b, entity_c, entity_d])
    await db_session.flush()

    # Create relationships
    # entity_c (ACME Corp) -> entity_b (Jon Smith): EMPLOYS
    rel_c_to_b = EntityRelationship(
        tenant_id=tenant_acme.id,
        source_entity_id=entity_c.id,
        target_entity_id=entity_b.id,
        relationship_type="EMPLOYS",
        properties={"since": "2020"},
        confidence_score=0.9,
    )

    # entity_b (Jon Smith) -> entity_d (Python): KNOWS
    rel_b_to_d = EntityRelationship(
        tenant_id=tenant_acme.id,
        source_entity_id=entity_b.id,
        target_entity_id=entity_d.id,
        relationship_type="KNOWS",
        properties={"level": "expert"},
        confidence_score=0.85,
    )

    db_session.add_all([rel_c_to_b, rel_b_to_d])
    await db_session.commit()

    # Refresh to get all attributes
    for entity in [entity_a, entity_b, entity_c, entity_d]:
        await db_session.refresh(entity)

    return {
        "entity_a": entity_a,
        "entity_b": entity_b,
        "entity_c": entity_c,
        "entity_d": entity_d,
        "rel_c_to_b": rel_c_to_b,
        "rel_b_to_d": rel_b_to_d,
    }


@pytest.fixture
async def multi_merge_entities(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraped_page_acme,
):
    """Create multiple entities for batch merge testing."""
    from tests.integration.consolidation.conftest import create_entity

    canonical = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "Event Sourcing",
        EntityType.CONCEPT,
        properties={"category": "architecture"},
    )

    duplicate_1 = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "event sourcing",
        EntityType.CONCEPT,
        properties={"category": "pattern"},
    )

    duplicate_2 = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "EventSourcing",
        EntityType.CONCEPT,
        properties={"category": "design_pattern"},
    )

    db_session.add_all([canonical, duplicate_1, duplicate_2])
    await db_session.commit()

    for entity in [canonical, duplicate_1, duplicate_2]:
        await db_session.refresh(entity)

    return {
        "canonical": canonical,
        "duplicate_1": duplicate_1,
        "duplicate_2": duplicate_2,
    }


# ---------------------------------------------------------------------------
# Test Classes
# ---------------------------------------------------------------------------


class TestMergeServiceBasicMerge:
    """Test basic merge operations."""

    async def test_merge_two_entities_success(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test successful merge of two entities."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]
        to_merge = entities["entity_b"]

        service = MergeService(db_session)

        result = await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="auto_high_confidence",
            similarity_scores={"combined": 0.92},
        )

        await db_session.commit()

        # Verify result structure
        assert isinstance(result, MergeResult)
        assert result.canonical_entity_id == canonical.id
        assert to_merge.id in result.merged_entity_ids
        assert len(result.aliases_created) == 1
        assert result.merge_history_id is not None
        assert result.event_id is not None

    async def test_merged_entity_marked_as_alias(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test that merged entity is marked as non-canonical."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]
        to_merge = entities["entity_b"]

        service = MergeService(db_session)

        await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="user_approved",
        )

        await db_session.commit()

        # Refresh merged entity
        await db_session.refresh(to_merge)

        # Verify merged entity is marked as alias
        assert to_merge.is_canonical is False
        assert to_merge.is_alias_of == canonical.id

    async def test_entity_alias_created_with_correct_data(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test that EntityAlias record is created correctly."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]
        to_merge = entities["entity_b"]

        service = MergeService(db_session)

        result = await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="batch",
        )

        await db_session.commit()

        # Query for alias record
        alias_query = select(EntityAlias).where(
            EntityAlias.canonical_entity_id == canonical.id,
            EntityAlias.original_entity_id == to_merge.id,
        )
        alias_result = await db_session.execute(alias_query)
        alias = alias_result.scalar_one_or_none()

        # Verify alias
        assert alias is not None
        assert alias.alias_name == "Jon Smith"
        assert alias.tenant_id == tenant_acme.id
        assert alias.merge_reason == "batch"
        assert alias.merge_event_id == result.event_id

        # Verify original properties stored for undo
        assert alias.original_entity_type == "person"
        assert alias.original_properties == to_merge.properties


class TestMergeServicePropertyMerging:
    """Test property merging with different strategies."""

    async def test_properties_deep_merged(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test that properties are deep merged."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]
        to_merge = entities["entity_b"]

        service = MergeService(db_session)

        await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="manual",
        )

        await db_session.commit()
        await db_session.refresh(canonical)

        # Properties should be deep merged
        # canonical had: role, department, tags
        # to_merge had: role, skills, tags
        assert canonical.properties.get("department") == "R&D"  # From canonical
        assert "skills" in canonical.properties  # Added from merged
        assert canonical.properties["skills"] == ["Python", "JavaScript"]

    async def test_external_ids_merged(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test that external IDs are merged."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]
        to_merge = entities["entity_b"]

        service = MergeService(db_session)

        await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="manual",
        )

        await db_session.commit()
        await db_session.refresh(canonical)

        # Both external IDs should be present
        assert canonical.external_ids.get("linkedin") == "john-smith-123"
        assert canonical.external_ids.get("github") == "jonsmith"

    async def test_higher_confidence_score_adopted(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test that higher confidence score is adopted."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]  # confidence=0.95
        to_merge = entities["entity_b"]  # confidence=0.88

        original_confidence = canonical.confidence_score

        service = MergeService(db_session)

        await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="manual",
        )

        await db_session.commit()
        await db_session.refresh(canonical)

        # Canonical had higher confidence, should keep it
        assert canonical.confidence_score == original_confidence


class TestMergeServiceRelationshipTransfer:
    """Test relationship transfer during merge."""

    async def test_incoming_relationships_transferred(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test that incoming relationships are transferred to canonical."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]
        to_merge = entities["entity_b"]
        entity_c = entities["entity_c"]  # Has EMPLOYS -> entity_b

        service = MergeService(db_session)

        result = await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="auto_high_confidence",
        )

        await db_session.commit()

        # Query for relationships now pointing to canonical
        rel_query = select(EntityRelationship).where(
            EntityRelationship.source_entity_id == entity_c.id,
            EntityRelationship.target_entity_id == canonical.id,
        )
        rel_result = await db_session.execute(rel_query)
        relationship = rel_result.scalar_one_or_none()

        assert relationship is not None
        assert relationship.relationship_type == "EMPLOYS"
        assert result.relationships_transferred >= 1

    async def test_outgoing_relationships_transferred(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test that outgoing relationships are transferred to canonical."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]
        to_merge = entities["entity_b"]
        entity_d = entities["entity_d"]  # entity_b -> entity_d (KNOWS)

        service = MergeService(db_session)

        await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="auto_high_confidence",
        )

        await db_session.commit()

        # Query for relationships now from canonical
        rel_query = select(EntityRelationship).where(
            EntityRelationship.source_entity_id == canonical.id,
            EntityRelationship.target_entity_id == entity_d.id,
        )
        rel_result = await db_session.execute(rel_query)
        relationship = rel_result.scalar_one_or_none()

        assert relationship is not None
        assert relationship.relationship_type == "KNOWS"

    async def test_no_duplicate_relationships_created(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        scraped_page_acme,
    ):
        """Test that duplicate relationships are not created during transfer."""
        from tests.integration.consolidation.conftest import create_entity

        # Create entities
        canonical = create_entity(
            tenant_acme.id, scraped_page_acme.id, "Entity A", EntityType.CONCEPT
        )
        to_merge = create_entity(
            tenant_acme.id, scraped_page_acme.id, "Entity B", EntityType.CONCEPT
        )
        target = create_entity(
            tenant_acme.id, scraped_page_acme.id, "Target", EntityType.CONCEPT
        )

        db_session.add_all([canonical, to_merge, target])
        await db_session.flush()

        # Both entities have RELATED_TO -> target
        rel_from_canonical = EntityRelationship(
            tenant_id=tenant_acme.id,
            source_entity_id=canonical.id,
            target_entity_id=target.id,
            relationship_type="RELATED_TO",
        )
        rel_from_merged = EntityRelationship(
            tenant_id=tenant_acme.id,
            source_entity_id=to_merge.id,
            target_entity_id=target.id,
            relationship_type="RELATED_TO",
        )

        db_session.add_all([rel_from_canonical, rel_from_merged])
        await db_session.commit()

        service = MergeService(db_session)

        await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="manual",
        )

        await db_session.commit()

        # Query for all RELATED_TO relationships from canonical to target
        rel_query = select(EntityRelationship).where(
            EntityRelationship.source_entity_id == canonical.id,
            EntityRelationship.target_entity_id == target.id,
            EntityRelationship.relationship_type == "RELATED_TO",
        )
        rel_result = await db_session.execute(rel_query)
        relationships = rel_result.scalars().all()

        # Should only have one relationship, not duplicated
        assert len(relationships) == 1


class TestMergeServiceMergeHistory:
    """Test MergeHistory record creation."""

    async def test_merge_history_created(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test that MergeHistory record is created."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]
        to_merge = entities["entity_b"]

        service = MergeService(db_session)

        result = await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="user_approved",
            similarity_scores={"combined": 0.88, "jaro_winkler": 0.91},
            # Note: Not passing merged_by_user_id as it requires an existing user
        )

        await db_session.commit()

        # Query for history record
        history_query = select(MergeHistory).where(
            MergeHistory.id == result.merge_history_id
        )
        history_result = await db_session.execute(history_query)
        history = history_result.scalar_one_or_none()

        # Verify history
        assert history is not None
        assert history.event_type == MergeEventType.ENTITIES_MERGED
        assert history.canonical_entity_id == canonical.id
        assert canonical.id in history.affected_entity_ids
        assert to_merge.id in history.affected_entity_ids
        assert history.merge_reason == "user_approved"
        assert history.similarity_scores["combined"] == 0.88
        assert history.undone is False

    async def test_merge_history_can_undo_property(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test that merge history can_undo property works."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]
        to_merge = entities["entity_b"]

        service = MergeService(db_session)

        result = await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="manual",
        )

        await db_session.commit()

        # Query for history record
        history_query = select(MergeHistory).where(
            MergeHistory.id == result.merge_history_id
        )
        history_result = await db_session.execute(history_query)
        history = history_result.scalar_one_or_none()

        # Can undo a fresh merge
        assert history.can_undo is True


class TestMergeServiceMultipleMerge:
    """Test merging multiple entities at once."""

    async def test_merge_multiple_entities(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        multi_merge_entities: dict,
    ):
        """Test merging multiple entities into one canonical."""
        entities = multi_merge_entities
        canonical = entities["canonical"]
        dup1 = entities["duplicate_1"]
        dup2 = entities["duplicate_2"]

        service = MergeService(db_session)

        result = await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[dup1, dup2],
            tenant_id=tenant_acme.id,
            merge_reason="batch",
        )

        await db_session.commit()

        # Verify all merged
        assert len(result.merged_entity_ids) == 2
        assert dup1.id in result.merged_entity_ids
        assert dup2.id in result.merged_entity_ids

        # Verify aliases created for both
        assert len(result.aliases_created) == 2

    async def test_all_duplicates_marked_non_canonical(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        multi_merge_entities: dict,
    ):
        """Test that all merged entities are marked non-canonical."""
        entities = multi_merge_entities
        canonical = entities["canonical"]
        dup1 = entities["duplicate_1"]
        dup2 = entities["duplicate_2"]

        service = MergeService(db_session)

        await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[dup1, dup2],
            tenant_id=tenant_acme.id,
            merge_reason="batch",
        )

        await db_session.commit()

        # Refresh entities
        await db_session.refresh(dup1)
        await db_session.refresh(dup2)

        # Both should be non-canonical
        assert dup1.is_canonical is False
        assert dup1.is_alias_of == canonical.id
        assert dup2.is_canonical is False
        assert dup2.is_alias_of == canonical.id


class TestMergeServiceValidation:
    """Test merge validation."""

    async def test_cannot_merge_entity_with_itself(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict,
    ):
        """Test that an entity cannot be merged with itself."""
        entity = person_entities_acme["john_smith"]

        service = MergeService(db_session)

        with pytest.raises(MergeValidationError, match="Cannot merge an entity with itself"):
            await service.merge_entities(
                canonical_entity=entity,
                merged_entities=[entity],
                tenant_id=tenant_acme.id,
                merge_reason="manual",
            )

    async def test_cannot_merge_already_aliased_entity(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test that already-aliased entities cannot be merged again."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]
        to_merge = entities["entity_b"]

        service = MergeService(db_session)

        # First merge
        await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="manual",
        )
        await db_session.commit()
        await db_session.refresh(to_merge)

        # Try to merge the already-aliased entity again
        another_entity = entities["entity_c"]

        with pytest.raises(MergeValidationError, match="already an alias"):
            await service.merge_entities(
                canonical_entity=another_entity,
                merged_entities=[to_merge],
                tenant_id=tenant_acme.id,
                merge_reason="manual",
            )

    async def test_cannot_merge_cross_tenant(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        tenant_globex: Tenant,
        person_entities_acme: dict,
        person_entities_globex: dict,
    ):
        """Test that entities from different tenants cannot be merged."""
        acme_entity = person_entities_acme["john_smith"]
        globex_entity = person_entities_globex["john_smith_globex"]

        service = MergeService(db_session)

        with pytest.raises(MergeValidationError, match="does not belong to tenant"):
            await service.merge_entities(
                canonical_entity=acme_entity,
                merged_entities=[globex_entity],
                tenant_id=tenant_acme.id,
                merge_reason="manual",
            )

    async def test_validate_merge_returns_issues(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict,
    ):
        """Test that validate_merge returns validation issues."""
        entity = person_entities_acme["john_smith"]

        service = MergeService(db_session)

        # Try to validate merging with itself
        issues = await service.validate_merge(
            canonical_entity=entity,
            merged_entities=[entity],
            tenant_id=tenant_acme.id,
        )

        assert len(issues) > 0
        assert any("itself" in issue for issue in issues)

    async def test_is_mergeable_returns_false_for_invalid(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict,
    ):
        """Test that is_mergeable returns False for invalid merge."""
        entity = person_entities_acme["john_smith"]

        service = MergeService(db_session)

        # Same entity should not be mergeable
        result = await service.is_mergeable(
            entity_a=entity,
            entity_b=entity,
            tenant_id=tenant_acme.id,
        )

        assert result is False


class TestMergeServiceTenantIsolation:
    """Test tenant isolation during merge operations."""

    async def test_merge_history_tenant_isolated(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        tenant_globex: Tenant,
        person_entities_acme: dict,
        person_entities_globex: dict,
    ):
        """Test that merge history is properly tenant-isolated."""
        acme_entities = person_entities_acme
        globex_entities = person_entities_globex

        service = MergeService(db_session)

        # Merge in ACME tenant
        await service.merge_entities(
            canonical_entity=acme_entities["john_smith"],
            merged_entities=[acme_entities["jon_smith"]],
            tenant_id=tenant_acme.id,
            merge_reason="auto_high_confidence",
        )
        await db_session.commit()

        # Query merge history for Globex tenant
        history_query = select(MergeHistory).where(
            MergeHistory.tenant_id == tenant_globex.id
        )
        history_result = await db_session.execute(history_query)
        globex_history = history_result.scalars().all()

        # Globex should have no merge history
        assert len(globex_history) == 0

        # Query for ACME tenant
        history_query = select(MergeHistory).where(
            MergeHistory.tenant_id == tenant_acme.id
        )
        history_result = await db_session.execute(history_query)
        acme_history = history_result.scalars().all()

        # ACME should have the merge history
        assert len(acme_history) == 1

    async def test_entity_alias_tenant_isolated(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        tenant_globex: Tenant,
        person_entities_acme: dict,
    ):
        """Test that entity aliases are properly tenant-isolated."""
        service = MergeService(db_session)

        # Merge in ACME tenant
        await service.merge_entities(
            canonical_entity=person_entities_acme["john_smith"],
            merged_entities=[person_entities_acme["jon_smith"]],
            tenant_id=tenant_acme.id,
            merge_reason="manual",
        )
        await db_session.commit()

        # Query aliases for Globex tenant
        alias_query = select(EntityAlias).where(
            EntityAlias.tenant_id == tenant_globex.id
        )
        alias_result = await db_session.execute(alias_query)
        globex_aliases = alias_result.scalars().all()

        # Globex should have no aliases
        assert len(globex_aliases) == 0


class TestMergeServiceDomainEvents:
    """Test domain event emission during merge."""

    async def test_merge_events_collected_without_bus(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test that events are collected when no event bus is provided."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]
        to_merge = entities["entity_b"]

        # Service without event bus
        service = MergeService(db_session, event_bus=None)

        result = await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="manual",
        )

        await db_session.commit()

        # Merge should succeed even without event bus
        assert result.event_id is not None


class TestMergeServiceEdgeCases:
    """Test edge cases in merge operations."""

    async def test_merge_with_empty_properties(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        scraped_page_acme,
    ):
        """Test merging entities with empty properties."""
        from tests.integration.consolidation.conftest import create_entity

        canonical = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Empty Canonical",
            EntityType.CONCEPT,
            properties={},
        )

        to_merge = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Empty Merged",
            EntityType.CONCEPT,
            properties={},
        )

        db_session.add_all([canonical, to_merge])
        await db_session.commit()

        service = MergeService(db_session)

        result = await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="manual",
        )

        await db_session.commit()

        # Should succeed without error
        assert result.canonical_entity_id == canonical.id

    async def test_merge_with_null_description(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        scraped_page_acme,
    ):
        """Test merging where merged entity has description and canonical doesn't."""
        from tests.integration.consolidation.conftest import create_entity

        canonical = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "No Description",
            EntityType.CONCEPT,
        )
        canonical.description = None

        to_merge = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Has Description",
            EntityType.CONCEPT,
        )
        to_merge.description = "This is a description"

        db_session.add_all([canonical, to_merge])
        await db_session.commit()

        service = MergeService(db_session)

        await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="manual",
        )

        await db_session.commit()
        await db_session.refresh(canonical)

        # Canonical should adopt description from merged
        assert canonical.description == "This is a description"


class TestMergeServiceQueryAliases:
    """Test querying entities via their aliases."""

    async def test_query_alias_by_name(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test that aliases can be queried by original name."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]
        to_merge = entities["entity_b"]

        service = MergeService(db_session)

        await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="manual",
        )

        await db_session.commit()

        # Query alias by original name
        alias_query = select(EntityAlias).where(
            EntityAlias.alias_name == "Jon Smith"
        )
        alias_result = await db_session.execute(alias_query)
        alias = alias_result.scalar_one_or_none()

        assert alias is not None
        assert alias.canonical_entity_id == canonical.id

    async def test_query_alias_by_normalized_name(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merge_entities_with_relationships: dict,
    ):
        """Test that aliases can be queried by normalized name."""
        entities = merge_entities_with_relationships
        canonical = entities["entity_a"]
        to_merge = entities["entity_b"]

        service = MergeService(db_session)

        await service.merge_entities(
            canonical_entity=canonical,
            merged_entities=[to_merge],
            tenant_id=tenant_acme.id,
            merge_reason="manual",
        )

        await db_session.commit()

        # Query alias by normalized name (lowercase)
        alias_query = select(EntityAlias).where(
            EntityAlias.alias_normalized_name == "jon smith"
        )
        alias_result = await db_session.execute(alias_query)
        alias = alias_result.scalar_one_or_none()

        assert alias is not None
