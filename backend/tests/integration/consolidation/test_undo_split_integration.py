"""
Integration tests for Undo/Split operations.

Tests the undo and split functionality against a real database, including:
- Undo merge with real database state
- Entity restoration from aliases
- Relationship restoration
- Split entity with relationship redistribution
- Split with alias redistribution
- Time-window validation for undo
- Projection handler updates
"""

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

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
    MergeUndoError,
    EntitySplitError,
    UndoResult,
    SplitResult,
)


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def merged_entities_for_undo(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraped_page_acme,
):
    """
    Create and merge entities, ready for undo testing.

    Creates:
    - canonical: John Smith (original canonical entity)
    - merged: Jon Smith (merged into canonical)
    - related: ACME Corp (has relationship to Jon Smith)

    After fixture completes, Jon Smith is merged into John Smith.
    """
    from tests.integration.consolidation.conftest import create_entity

    # Create entities
    canonical = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "John Smith",
        EntityType.PERSON,
        properties={"role": "Engineer", "department": "R&D"},
        confidence_score=0.95,
    )
    canonical.description = "Senior engineer"
    canonical.external_ids = {"linkedin": "john-smith"}

    merged = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "Jon Smith",
        EntityType.PERSON,
        properties={"role": "Developer", "skills": ["Python"]},
        confidence_score=0.88,
    )
    merged.description = "Software developer"
    merged.external_ids = {"github": "jonsmith"}

    related = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "ACME Corp",
        EntityType.ORGANIZATION,
        properties={"industry": "Technology"},
    )

    db_session.add_all([canonical, merged, related])
    await db_session.flush()

    # Create relationship: ACME Corp -> Jon Smith
    relationship = EntityRelationship(
        tenant_id=tenant_acme.id,
        source_entity_id=related.id,
        target_entity_id=merged.id,
        relationship_type="EMPLOYS",
        properties={"since": "2020"},
        confidence_score=0.9,
    )
    db_session.add(relationship)
    await db_session.commit()

    # Perform the merge
    service = MergeService(db_session)

    merge_result = await service.merge_entities(
        canonical_entity=canonical,
        merged_entities=[merged],
        tenant_id=tenant_acme.id,
        merge_reason="auto_high_confidence",
        similarity_scores={"combined": 0.92},
        # Not passing user_id to avoid foreign key constraint on users table
    )

    await db_session.commit()

    # Refresh all entities
    await db_session.refresh(canonical)
    await db_session.refresh(merged)
    await db_session.refresh(related)

    return {
        "canonical": canonical,
        "merged": merged,
        "related": related,
        "merge_result": merge_result,
    }


@pytest.fixture
async def multi_merged_for_undo(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraped_page_acme,
):
    """
    Create and merge multiple entities, ready for partial undo testing.
    """
    from tests.integration.consolidation.conftest import create_entity

    canonical = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "Event Sourcing",
        EntityType.CONCEPT,
        properties={"category": "architecture"},
    )

    merged_1 = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "event sourcing",
        EntityType.CONCEPT,
        properties={"category": "pattern"},
    )

    merged_2 = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "EventSourcing",
        EntityType.CONCEPT,
        properties={"category": "design"},
    )

    db_session.add_all([canonical, merged_1, merged_2])
    await db_session.commit()

    # Perform the merge
    service = MergeService(db_session)

    merge_result = await service.merge_entities(
        canonical_entity=canonical,
        merged_entities=[merged_1, merged_2],
        tenant_id=tenant_acme.id,
        merge_reason="batch",
        # Not passing user_id to avoid foreign key constraint
    )

    await db_session.commit()

    for entity in [canonical, merged_1, merged_2]:
        await db_session.refresh(entity)

    return {
        "canonical": canonical,
        "merged_1": merged_1,
        "merged_2": merged_2,
        "merge_result": merge_result,
    }


@pytest.fixture
async def entity_for_split(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraped_page_acme,
):
    """
    Create an entity with relationships and aliases for split testing.
    """
    from tests.integration.consolidation.conftest import create_entity

    # Create the entity that will be split
    entity = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "John Smith (Developer, Manager)",
        EntityType.PERSON,
        properties={
            "roles": ["developer", "manager"],
            "skills": ["Python", "Leadership"],
        },
    )
    entity.description = "Combined profile that should be split"

    # Create related entities
    team = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "Engineering Team",
        EntityType.ORGANIZATION,
    )

    project = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "Knowledge Mapper Project",
        EntityType.CONCEPT,
    )

    db_session.add_all([entity, team, project])
    await db_session.flush()

    # Create relationships
    # entity -> team (MEMBER_OF)
    rel_to_team = EntityRelationship(
        tenant_id=tenant_acme.id,
        source_entity_id=entity.id,
        target_entity_id=team.id,
        relationship_type="MEMBER_OF",
        properties={"role": "developer"},
    )

    # entity -> project (LEADS)
    rel_to_project = EntityRelationship(
        tenant_id=tenant_acme.id,
        source_entity_id=entity.id,
        target_entity_id=project.id,
        relationship_type="LEADS",
        properties={"role": "manager"},
    )

    db_session.add_all([rel_to_team, rel_to_project])
    await db_session.commit()

    for e in [entity, team, project]:
        await db_session.refresh(e)

    return {
        "entity": entity,
        "team": team,
        "project": project,
        "rel_to_team": rel_to_team,
        "rel_to_project": rel_to_project,
    }


@pytest.fixture
async def entity_with_aliases_for_split(
    db_session: AsyncSession,
    tenant_acme: Tenant,
    scraped_page_acme,
):
    """
    Create an entity with existing aliases for split testing.
    """
    from tests.integration.consolidation.conftest import create_entity

    # Create canonical entity
    entity = create_entity(
        tenant_acme.id,
        scraped_page_acme.id,
        "Combined Entity",
        EntityType.CONCEPT,
        properties={"source": "merged"},
    )

    db_session.add(entity)
    await db_session.flush()

    # Create aliases (simulating previous merges)
    alias_1 = EntityAlias(
        tenant_id=tenant_acme.id,
        canonical_entity_id=entity.id,
        alias_name="Original Entity A",
        original_entity_id=uuid.uuid4(),
        merged_at=datetime.now(UTC),
        merge_reason="batch",
        original_entity_type="concept",
    )

    alias_2 = EntityAlias(
        tenant_id=tenant_acme.id,
        canonical_entity_id=entity.id,
        alias_name="Original Entity B",
        original_entity_id=uuid.uuid4(),
        merged_at=datetime.now(UTC),
        merge_reason="batch",
        original_entity_type="concept",
    )

    db_session.add_all([alias_1, alias_2])
    await db_session.commit()

    await db_session.refresh(entity)
    await db_session.refresh(alias_1)
    await db_session.refresh(alias_2)

    return {
        "entity": entity,
        "alias_1": alias_1,
        "alias_2": alias_2,
    }


# ---------------------------------------------------------------------------
# Undo Merge Tests
# ---------------------------------------------------------------------------


class TestUndoMergeBasic:
    """Test basic undo merge operations."""

    async def test_undo_merge_success(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merged_entities_for_undo: dict,
    ):
        """Test successful undo of a merge."""
        data = merged_entities_for_undo
        merge_result = data["merge_result"]

        service = MergeService(db_session)

        result = await service.undo_merge(
            merge_event_id=merge_result.event_id,
            reason="Entities are different people",
        )

        await db_session.commit()

        # Verify result structure
        assert isinstance(result, UndoResult)
        assert result.original_merge_event_id == merge_result.event_id
        assert len(result.restored_entity_ids) == 1
        assert result.aliases_removed == 1
        assert result.undo_history_id is not None
        assert result.event_id is not None

    async def test_undo_creates_new_entity(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merged_entities_for_undo: dict,
    ):
        """Test that undo creates a new entity with original properties."""
        data = merged_entities_for_undo
        merge_result = data["merge_result"]
        original_merged = data["merged"]

        service = MergeService(db_session)

        result = await service.undo_merge(
            merge_event_id=merge_result.event_id,
            reason="Incorrect merge",
        )

        await db_session.commit()

        # Query for the restored entity
        restored_id = result.restored_entity_ids[0]
        entity_query = select(ExtractedEntity).where(
            ExtractedEntity.id == restored_id
        )
        entity_result = await db_session.execute(entity_query)
        restored_entity = entity_result.scalar_one_or_none()

        # Verify restored entity
        assert restored_entity is not None
        assert restored_entity.name == "Jon Smith"
        assert restored_entity.is_canonical is True
        assert restored_entity.is_alias_of is None
        assert restored_entity.entity_type == EntityType.PERSON

    async def test_undo_removes_aliases(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merged_entities_for_undo: dict,
    ):
        """Test that undo removes the alias records."""
        data = merged_entities_for_undo
        merge_result = data["merge_result"]
        canonical = data["canonical"]

        # Verify alias exists before undo
        alias_query = select(EntityAlias).where(
            EntityAlias.canonical_entity_id == canonical.id
        )
        alias_result = await db_session.execute(alias_query)
        aliases_before = alias_result.scalars().all()
        assert len(aliases_before) == 1

        service = MergeService(db_session)

        await service.undo_merge(
            merge_event_id=merge_result.event_id,
            reason="Test undo",
        )

        await db_session.commit()

        # Verify aliases removed
        alias_result = await db_session.execute(alias_query)
        aliases_after = alias_result.scalars().all()
        assert len(aliases_after) == 0

    async def test_undo_marks_original_merge_as_undone(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merged_entities_for_undo: dict,
    ):
        """Test that undo marks the original merge history as undone."""
        data = merged_entities_for_undo
        merge_result = data["merge_result"]

        service = MergeService(db_session)

        await service.undo_merge(
            merge_event_id=merge_result.event_id,
            reason="Test undo",
        )

        await db_session.commit()

        # Query original merge history
        history_query = select(MergeHistory).where(
            MergeHistory.event_id == merge_result.event_id
        )
        history_result = await db_session.execute(history_query)
        history = history_result.scalar_one_or_none()

        # Verify marked as undone
        assert history is not None
        assert history.undone is True
        assert history.undone_at is not None
        assert history.undone_by == undo_user_id
        assert history.undo_reason == "Test undo"

    async def test_undo_creates_undo_history_record(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merged_entities_for_undo: dict,
    ):
        """Test that undo creates a MergeHistory record for the undo operation."""
        data = merged_entities_for_undo
        merge_result = data["merge_result"]

        service = MergeService(db_session)

        result = await service.undo_merge(
            merge_event_id=merge_result.event_id,
            reason="Test undo",
        )

        await db_session.commit()

        # Query for undo history record
        history_query = select(MergeHistory).where(
            MergeHistory.id == result.undo_history_id
        )
        history_result = await db_session.execute(history_query)
        undo_history = history_result.scalar_one_or_none()

        # Verify undo history
        assert undo_history is not None
        assert undo_history.event_type == MergeEventType.MERGE_UNDONE
        assert undo_history.performed_by == undo_user_id
        assert undo_history.merge_reason == "Test undo"


class TestUndoMergeValidation:
    """Test undo merge validation."""

    async def test_cannot_undo_nonexistent_merge(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
    ):
        """Test that undoing a nonexistent merge raises an error."""
        service = MergeService(db_session)
        fake_event_id = uuid.uuid4()

        with pytest.raises(MergeUndoError, match="not found"):
            await service.undo_merge(
                merge_event_id=fake_event_id,
                reason="Test",
            )

    async def test_cannot_undo_already_undone_merge(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        merged_entities_for_undo: dict,
    ):
        """Test that undoing an already-undone merge raises an error."""
        data = merged_entities_for_undo
        merge_result = data["merge_result"]

        service = MergeService(db_session)

        # First undo
        await service.undo_merge(
            merge_event_id=merge_result.event_id,
            reason="First undo",
        )
        await db_session.commit()

        # Try second undo
        with pytest.raises(MergeUndoError, match="already undone"):
            await service.undo_merge(
                merge_event_id=merge_result.event_id,
                reason="Second undo attempt",
            )


class TestUndoMergePartial:
    """Test partial undo operations."""

    async def test_partial_undo_restores_subset(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        multi_merged_for_undo: dict,
    ):
        """Test partial undo restores only specified entities."""
        data = multi_merged_for_undo
        merge_result = data["merge_result"]
        merged_1_id = data["merged_1"].id

        service = MergeService(db_session)

        result = await service.undo_merge(
            merge_event_id=merge_result.event_id,
            reason="Partial undo",
            restore_entity_ids=[merged_1_id],  # Only restore merged_1
        )

        await db_session.commit()

        # Should only restore one entity
        assert len(result.restored_entity_ids) == 1

        # Verify one alias removed
        assert result.aliases_removed == 1

        # Query remaining aliases
        alias_query = select(EntityAlias).where(
            EntityAlias.canonical_entity_id == data["canonical"].id
        )
        alias_result = await db_session.execute(alias_query)
        remaining_aliases = alias_result.scalars().all()

        # One alias should remain (for merged_2)
        assert len(remaining_aliases) == 1


# ---------------------------------------------------------------------------
# Split Entity Tests
# ---------------------------------------------------------------------------


class TestSplitEntityBasic:
    """Test basic split entity operations."""

    async def test_split_entity_success(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        entity_for_split: dict,
    ):
        """Test successful split of an entity."""
        data = entity_for_split
        entity = data["entity"]

        service = MergeService(db_session)

        split_definitions = [
            {
                "name": "John Smith (Developer)",
                "entity_type": "person",
                "properties": {"role": "developer"},
            },
            {
                "name": "John Smith (Manager)",
                "entity_type": "person",
                "properties": {"role": "manager"},
            },
        ]

        result = await service.split_entity(
            entity_id=entity.id,
            split_definitions=split_definitions,
            relationship_assignments={},
            alias_assignments=None,
            reason="Entity represents two different roles",
        )

        await db_session.commit()

        # Verify result structure
        assert isinstance(result, SplitResult)
        assert result.original_entity_id == entity.id
        assert len(result.new_entity_ids) == 2
        assert len(result.new_entities) == 2
        assert result.split_history_id is not None
        assert result.event_id is not None

    async def test_split_creates_new_entities(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        entity_for_split: dict,
    ):
        """Test that split creates new entities with correct properties."""
        data = entity_for_split
        entity = data["entity"]

        service = MergeService(db_session)

        split_definitions = [
            {
                "name": "Developer John",
                "entity_type": "person",
                "properties": {"specialty": "backend"},
                "description": "Backend developer",
            },
            {
                "name": "Manager John",
                "entity_type": "person",
                "properties": {"specialty": "team_lead"},
                "description": "Team lead",
            },
        ]

        result = await service.split_entity(
            entity_id=entity.id,
            split_definitions=split_definitions,
            relationship_assignments={},
            alias_assignments=None,
            reason="Split roles",
        )

        await db_session.commit()

        # Query for new entities
        for new_entity in result.new_entities:
            entity_query = select(ExtractedEntity).where(
                ExtractedEntity.id == new_entity.id
            )
            entity_result = await db_session.execute(entity_query)
            queried_entity = entity_result.scalar_one_or_none()

            assert queried_entity is not None
            assert queried_entity.is_canonical is True
            assert queried_entity.tenant_id == tenant_acme.id

    async def test_split_marks_original_non_canonical(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        entity_for_split: dict,
    ):
        """Test that split marks the original entity as non-canonical."""
        data = entity_for_split
        entity = data["entity"]

        service = MergeService(db_session)

        split_definitions = [
            {"name": "Part A"},
            {"name": "Part B"},
        ]

        result = await service.split_entity(
            entity_id=entity.id,
            split_definitions=split_definitions,
            relationship_assignments={},
            alias_assignments=None,
            reason="Split",
        )

        await db_session.commit()
        await db_session.refresh(entity)

        # Original should be non-canonical
        assert entity.is_canonical is False

        # Should have split metadata
        assert "_split_into" in entity.properties
        assert len(entity.properties["_split_into"]) == 2


class TestSplitEntityRelationshipRedistribution:
    """Test relationship redistribution during split."""

    async def test_default_relationship_redistribution(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        entity_for_split: dict,
    ):
        """Test default redistribution assigns all relationships to first entity."""
        data = entity_for_split
        entity = data["entity"]
        team = data["team"]
        project = data["project"]

        service = MergeService(db_session)

        split_definitions = [
            {"name": "First Entity"},
            {"name": "Second Entity"},
        ]

        result = await service.split_entity(
            entity_id=entity.id,
            split_definitions=split_definitions,
            relationship_assignments={},  # Empty = default to first
            alias_assignments=None,
            reason="Split",
        )

        await db_session.commit()

        first_entity_id = result.new_entity_ids[0]

        # Query relationships from first entity
        rel_query = select(EntityRelationship).where(
            EntityRelationship.source_entity_id == first_entity_id
        )
        rel_result = await db_session.execute(rel_query)
        relationships = rel_result.scalars().all()

        # All relationships should be assigned to first entity
        assert len(relationships) == 2

    async def test_explicit_relationship_redistribution(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        entity_for_split: dict,
    ):
        """Test explicit redistribution assigns relationships to specified entities."""
        data = entity_for_split
        entity = data["entity"]
        rel_to_team = data["rel_to_team"]
        rel_to_project = data["rel_to_project"]

        service = MergeService(db_session)

        split_definitions = [
            {"name": "Developer John", "properties": {"role": "developer"}},
            {"name": "Manager John", "properties": {"role": "manager"}},
        ]

        # Assign MEMBER_OF to developer (index 0)
        # Assign LEADS to manager (index 1)
        relationship_assignments = {
            rel_to_team.id: 0,
            rel_to_project.id: 1,
        }

        result = await service.split_entity(
            entity_id=entity.id,
            split_definitions=split_definitions,
            relationship_assignments=relationship_assignments,
            alias_assignments=None,
            reason="Split roles",
        )

        await db_session.commit()

        developer_id = result.new_entity_ids[0]
        manager_id = result.new_entity_ids[1]

        # Query developer's relationships
        dev_rel_query = select(EntityRelationship).where(
            EntityRelationship.source_entity_id == developer_id
        )
        dev_rel_result = await db_session.execute(dev_rel_query)
        dev_rels = dev_rel_result.scalars().all()

        assert len(dev_rels) == 1
        assert dev_rels[0].relationship_type == "MEMBER_OF"

        # Query manager's relationships
        mgr_rel_query = select(EntityRelationship).where(
            EntityRelationship.source_entity_id == manager_id
        )
        mgr_rel_result = await db_session.execute(mgr_rel_query)
        mgr_rels = mgr_rel_result.scalars().all()

        assert len(mgr_rels) == 1
        assert mgr_rels[0].relationship_type == "LEADS"


class TestSplitEntityAliasRedistribution:
    """Test alias redistribution during split."""

    async def test_alias_redistribution(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        entity_with_aliases_for_split: dict,
    ):
        """Test that aliases are redistributed during split."""
        data = entity_with_aliases_for_split
        entity = data["entity"]
        alias_1 = data["alias_1"]
        alias_2 = data["alias_2"]

        service = MergeService(db_session)

        split_definitions = [
            {"name": "New Entity A"},
            {"name": "New Entity B"},
        ]

        alias_assignments = {
            alias_1.id: 0,  # Alias 1 goes to first entity
            alias_2.id: 1,  # Alias 2 goes to second entity
        }

        result = await service.split_entity(
            entity_id=entity.id,
            split_definitions=split_definitions,
            relationship_assignments={},
            alias_assignments=alias_assignments,
            reason="Split",
        )

        await db_session.commit()

        # Query aliases
        await db_session.refresh(alias_1)
        await db_session.refresh(alias_2)

        # Aliases should point to new entities
        assert alias_1.canonical_entity_id == result.new_entity_ids[0]
        assert alias_2.canonical_entity_id == result.new_entity_ids[1]


class TestSplitEntityValidation:
    """Test split entity validation."""

    async def test_cannot_split_nonexistent_entity(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
    ):
        """Test that splitting a nonexistent entity raises an error."""
        service = MergeService(db_session)
        fake_entity_id = uuid.uuid4()

        split_definitions = [
            {"name": "Part A"},
            {"name": "Part B"},
        ]

        with pytest.raises(EntitySplitError, match="not found"):
            await service.split_entity(
                entity_id=fake_entity_id,
                split_definitions=split_definitions,
                relationship_assignments={},
                alias_assignments=None,
                reason="Test",
            )

    async def test_cannot_split_into_one_entity(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        entity_for_split: dict,
    ):
        """Test that split requires at least 2 new entities."""
        data = entity_for_split
        entity = data["entity"]

        service = MergeService(db_session)

        split_definitions = [
            {"name": "Single Entity"},  # Only one definition
        ]

        with pytest.raises(EntitySplitError, match="at least 2"):
            await service.split_entity(
                entity_id=entity.id,
                split_definitions=split_definitions,
                relationship_assignments={},
                alias_assignments=None,
                reason="Invalid split",
            )

    async def test_cannot_split_without_name(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        entity_for_split: dict,
    ):
        """Test that split definitions must have names."""
        data = entity_for_split
        entity = data["entity"]

        service = MergeService(db_session)

        split_definitions = [
            {"name": "Valid Entity"},
            {"properties": {"missing": "name"}},  # Missing name
        ]

        with pytest.raises(EntitySplitError, match="missing required 'name'"):
            await service.split_entity(
                entity_id=entity.id,
                split_definitions=split_definitions,
                relationship_assignments={},
                alias_assignments=None,
                reason="Invalid split",
            )


class TestSplitEntityHistory:
    """Test split history creation."""

    async def test_split_creates_history_record(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        entity_for_split: dict,
    ):
        """Test that split creates a MergeHistory record."""
        data = entity_for_split
        entity = data["entity"]

        service = MergeService(db_session)

        split_definitions = [
            {"name": "Part A"},
            {"name": "Part B"},
        ]

        result = await service.split_entity(
            entity_id=entity.id,
            split_definitions=split_definitions,
            relationship_assignments={},
            alias_assignments=None,
            reason="Split reason",
        )

        await db_session.commit()

        # Query history record
        history_query = select(MergeHistory).where(
            MergeHistory.id == result.split_history_id
        )
        history_result = await db_session.execute(history_query)
        history = history_result.scalar_one_or_none()

        # Verify history
        assert history is not None
        assert history.event_type == MergeEventType.ENTITY_SPLIT
        assert history.canonical_entity_id == entity.id  # Original entity
        assert history.performed_by == user_id
        assert history.merge_reason == "Split reason"
        assert len(history.affected_entity_ids) == 2


class TestSplitEntityTenantIsolation:
    """Test tenant isolation during split operations."""

    async def test_split_preserves_tenant(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        entity_for_split: dict,
    ):
        """Test that split preserves tenant ID on new entities."""
        data = entity_for_split
        entity = data["entity"]

        service = MergeService(db_session)

        split_definitions = [
            {"name": "Part A"},
            {"name": "Part B"},
        ]

        result = await service.split_entity(
            entity_id=entity.id,
            split_definitions=split_definitions,
            relationship_assignments={},
            alias_assignments=None,
            reason="Split",
        )

        await db_session.commit()

        # All new entities should have correct tenant
        for new_entity in result.new_entities:
            assert new_entity.tenant_id == tenant_acme.id


class TestSplitEntitySourcePage:
    """Test source page preservation during split."""

    async def test_split_preserves_source_page(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        entity_for_split: dict,
    ):
        """Test that split preserves source page on new entities."""
        data = entity_for_split
        entity = data["entity"]
        original_page_id = entity.source_page_id

        service = MergeService(db_session)

        split_definitions = [
            {"name": "Part A"},
            {"name": "Part B"},
        ]

        result = await service.split_entity(
            entity_id=entity.id,
            split_definitions=split_definitions,
            relationship_assignments={},
            alias_assignments=None,
            reason="Split",
        )

        await db_session.commit()

        # All new entities should have original source page
        for new_entity in result.new_entities:
            assert new_entity.source_page_id == original_page_id


class TestIntegrationMergeUndoSplitCycle:
    """Test complete merge -> undo -> split cycles."""

    async def test_merge_then_split_workflow(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        scraped_page_acme,
    ):
        """Test workflow: merge entities, then split the result."""
        from tests.integration.consolidation.conftest import create_entity

        # Create entities
        entity_a = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Entity A",
            EntityType.CONCEPT,
            properties={"source": "a"},
        )
        entity_b = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Entity B",
            EntityType.CONCEPT,
            properties={"source": "b"},
        )

        db_session.add_all([entity_a, entity_b])
        await db_session.commit()

        service = MergeService(db_session)

        # Step 1: Merge
        merge_result = await service.merge_entities(
            canonical_entity=entity_a,
            merged_entities=[entity_b],
            tenant_id=tenant_acme.id,
            merge_reason="auto_high_confidence",
        )
        await db_session.commit()

        # Verify merge
        await db_session.refresh(entity_b)
        assert entity_b.is_canonical is False

        # Step 2: Split the merged entity into 3 parts
        split_definitions = [
            {"name": "Part 1"},
            {"name": "Part 2"},
            {"name": "Part 3"},
        ]

        split_result = await service.split_entity(
            entity_id=entity_a.id,
            split_definitions=split_definitions,
            relationship_assignments={},
            alias_assignments=None,
            reason="Need more granularity",
        )
        await db_session.commit()

        # Verify split
        assert len(split_result.new_entity_ids) == 3

        await db_session.refresh(entity_a)
        assert entity_a.is_canonical is False

    async def test_merge_undo_remerge_workflow(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        scraped_page_acme,
    ):
        """Test workflow: merge entities, undo, then merge differently."""
        from tests.integration.consolidation.conftest import create_entity

        # Create entities
        entity_a = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Entity Alpha",
            EntityType.CONCEPT,
        )
        entity_b = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Entity Beta",
            EntityType.CONCEPT,
        )
        entity_c = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Entity Gamma",
            EntityType.CONCEPT,
        )

        db_session.add_all([entity_a, entity_b, entity_c])
        await db_session.commit()

        service = MergeService(db_session)

        # Step 1: Merge A <- B
        merge_result_1 = await service.merge_entities(
            canonical_entity=entity_a,
            merged_entities=[entity_b],
            tenant_id=tenant_acme.id,
            merge_reason="auto",
        )
        await db_session.commit()

        # Step 2: Undo the merge
        undo_result = await service.undo_merge(
            merge_event_id=merge_result_1.event_id,
            reason="Wrong merge",
        )
        await db_session.commit()

        # Step 3: Get the restored entity
        restored_entity_id = undo_result.restored_entity_ids[0]
        entity_query = select(ExtractedEntity).where(
            ExtractedEntity.id == restored_entity_id
        )
        entity_result = await db_session.execute(entity_query)
        restored_entity = entity_result.scalar_one()

        # Step 4: Merge C <- restored (different merge)
        merge_result_2 = await service.merge_entities(
            canonical_entity=entity_c,
            merged_entities=[restored_entity],
            tenant_id=tenant_acme.id,
            merge_reason="correct_merge",
        )
        await db_session.commit()

        # Verify final state
        await db_session.refresh(restored_entity)
        assert restored_entity.is_canonical is False
        assert restored_entity.is_alias_of == entity_c.id
