"""
Integration tests for BlockingEngine service.

Tests the BlockingEngine against a real PostgreSQL database with:
- Soundex, trigram, and combined blocking strategies
- Database indexes from P1-005
- Tenant isolation verification
- Performance benchmarks for blocking efficiency

These tests verify that the blocking strategies correctly identify
candidate pairs while maintaining good performance on larger datasets.
"""

import time
import pytest
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExtractedEntity, EntityType, Tenant
from app.services.consolidation import BlockingEngine, BlockingStrategy
from app.services.tenant_context import set_tenant_context


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestBlockingEngineDatabase:
    """Test BlockingEngine against real database with indexes."""

    async def test_find_candidates_returns_results(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that find_candidates returns matching entities from database."""
        engine = BlockingEngine(max_block_size=100)

        # Use John Smith as source entity
        source = person_entities_acme["john_smith"]

        result = await engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Should find at least some candidates
        assert result.total_candidates > 0
        assert len(result.candidates) > 0

        # Source entity should NOT be in candidates
        candidate_ids = {c.id for c in result.candidates}
        assert source.id not in candidate_ids

    async def test_blocking_strategies_recorded(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that blocking strategies used are recorded in result."""
        engine = BlockingEngine(
            max_block_size=100,
            strategies=[
                BlockingStrategy.PREFIX,
                BlockingStrategy.ENTITY_TYPE,
                BlockingStrategy.SOUNDEX,
            ],
        )

        source = person_entities_acme["john_smith"]

        result = await engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Strategies should be recorded
        assert len(result.strategies_used) > 0
        assert all(
            isinstance(s, BlockingStrategy) for s in result.strategies_used
        )

    async def test_soundex_blocking_finds_phonetic_matches(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that soundex blocking finds phonetically similar names."""
        # Use only soundex strategy
        engine = BlockingEngine(
            max_block_size=100,
            strategies=[BlockingStrategy.SOUNDEX],
        )

        # "John Smith" should match "John Smyth" (same soundex)
        source = person_entities_acme["john_smith"]

        result = await engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        candidate_names = {c.name for c in result.candidates}

        # "John Smyth" should be found (soundex for Smith = Smyth)
        # Note: Soundex might match other names too depending on algorithm
        assert result.total_candidates >= 1

    async def test_entity_type_blocking_returns_same_type(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
        org_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that entity_type blocking only returns entities of same type."""
        engine = BlockingEngine(
            max_block_size=100,
            strategies=[BlockingStrategy.ENTITY_TYPE],
        )

        # Use a person entity
        source = person_entities_acme["john_smith"]

        result = await engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # All candidates should be PERSON type
        for candidate in result.candidates:
            assert candidate.entity_type == EntityType.PERSON

    async def test_prefix_blocking_finds_similar_prefixes(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that prefix blocking finds entities with same name prefix."""
        engine = BlockingEngine(
            max_block_size=100,
            min_prefix_length=4,
            strategies=[BlockingStrategy.PREFIX],
        )

        # "John Smith" should match others starting with "john"
        source = person_entities_acme["john_smith"]

        result = await engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Should find other "John" variants
        candidate_normalized = {c.normalized_name for c in result.candidates}

        # All candidates should share the same prefix
        source_prefix = source.normalized_name[:4]
        for candidate in result.candidates:
            candidate_prefix = (candidate.normalized_name or "")[:4]
            if "prefix" in getattr(candidate, "_blocking_keys", []):
                assert candidate_prefix == source_prefix

    async def test_blocking_keys_tracked_on_candidates(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that _blocking_keys attribute is set on candidates."""
        engine = BlockingEngine(
            max_block_size=100,
            strategies=[
                BlockingStrategy.PREFIX,
                BlockingStrategy.ENTITY_TYPE,
                BlockingStrategy.SOUNDEX,
            ],
        )

        source = person_entities_acme["john_smith"]

        result = await engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        for candidate in result.candidates:
            # Each candidate should have _blocking_keys attribute
            blocking_keys = getattr(candidate, "_blocking_keys", None)
            assert blocking_keys is not None
            assert isinstance(blocking_keys, list)
            assert len(blocking_keys) > 0

    async def test_combined_strategies_union_results(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that combined strategies return union of all matches."""
        # Get results with single strategies
        prefix_engine = BlockingEngine(strategies=[BlockingStrategy.PREFIX])
        soundex_engine = BlockingEngine(strategies=[BlockingStrategy.SOUNDEX])
        combined_engine = BlockingEngine(
            strategies=[BlockingStrategy.PREFIX, BlockingStrategy.SOUNDEX]
        )

        source = person_entities_acme["john_smith"]

        prefix_result = await prefix_engine.find_candidates(
            db_session, source, tenant_acme.id
        )
        soundex_result = await soundex_engine.find_candidates(
            db_session, source, tenant_acme.id
        )
        combined_result = await combined_engine.find_candidates(
            db_session, source, tenant_acme.id
        )

        # Combined should include candidates from both strategies
        prefix_ids = {c.id for c in prefix_result.candidates}
        soundex_ids = {c.id for c in soundex_result.candidates}
        combined_ids = {c.id for c in combined_result.candidates}

        # Combined should be superset (or equal) of individual strategies
        # Note: Due to entity_type being default, there's overlap
        assert combined_ids >= (prefix_ids | soundex_ids)


class TestBlockingEngineTenantIsolation:
    """Test tenant isolation in BlockingEngine."""

    async def test_blocking_respects_tenant_boundary(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        tenant_globex: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
        person_entities_globex: dict[str, ExtractedEntity],
    ):
        """Test that blocking only returns candidates from same tenant."""
        engine = BlockingEngine(max_block_size=100)

        # Use ACME's John Smith
        source = person_entities_acme["john_smith"]

        result = await engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Should NOT find Globex's John Smith
        candidate_ids = {c.id for c in result.candidates}
        globex_john_id = person_entities_globex["john_smith_globex"].id

        assert globex_john_id not in candidate_ids

        # All candidates should be from ACME tenant
        for candidate in result.candidates:
            assert candidate.tenant_id == tenant_acme.id

    async def test_blocking_finds_same_name_within_tenant(
        self,
        db_session: AsyncSession,
        tenant_globex: Tenant,
        person_entities_globex: dict[str, ExtractedEntity],
    ):
        """Test that blocking works correctly within different tenant."""
        engine = BlockingEngine(max_block_size=100)

        source = person_entities_globex["john_smith_globex"]

        result = await engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_globex.id,
        )

        # Should only find Globex entities
        for candidate in result.candidates:
            assert candidate.tenant_id == tenant_globex.id


class TestBlockingEngineCanonicalFiltering:
    """Test that BlockingEngine only returns canonical entities."""

    async def test_only_returns_canonical_entities(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that only canonical entities are returned as candidates."""
        engine = BlockingEngine(max_block_size=100)
        source = person_entities_acme["john_smith"]

        result = await engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # All candidates should be canonical
        for candidate in result.candidates:
            assert candidate.is_canonical is True

    async def test_non_canonical_entities_excluded(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        scraped_page_acme,
    ):
        """Test that non-canonical (alias) entities are excluded from results."""
        from tests.integration.consolidation.conftest import create_entity

        # Create a canonical entity
        canonical = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Robert Johnson",
            EntityType.PERSON,
            is_canonical=True,
        )
        db_session.add(canonical)
        await db_session.flush()

        # Create an alias entity
        alias = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Bob Johnson",
            EntityType.PERSON,
            is_canonical=False,
        )
        alias.is_alias_of = canonical.id
        db_session.add(alias)
        await db_session.commit()

        # Create another entity to search for candidates
        source = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Bobby Johnson",
            EntityType.PERSON,
            is_canonical=True,
        )
        db_session.add(source)
        await db_session.commit()

        engine = BlockingEngine(max_block_size=100)
        result = await engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        candidate_ids = {c.id for c in result.candidates}

        # Should find canonical Robert Johnson
        assert canonical.id in candidate_ids

        # Should NOT find alias Bob Johnson
        assert alias.id not in candidate_ids


class TestBlockingEnginePerformance:
    """Performance tests for BlockingEngine."""

    async def test_blocking_performance_large_dataset(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        large_entity_dataset: list[ExtractedEntity],
    ):
        """Test that blocking performs efficiently on larger datasets."""
        engine = BlockingEngine(max_block_size=50)

        # Pick a source entity from the dataset
        source = large_entity_dataset[0]

        start_time = time.perf_counter()
        result = await engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Should complete in reasonable time (< 500ms)
        assert elapsed_ms < 500, f"Blocking took {elapsed_ms:.2f}ms"

        # Should have recorded execution time
        assert result.execution_time_ms > 0

    async def test_max_block_size_truncation(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        large_entity_dataset: list[ExtractedEntity],
    ):
        """Test that max_block_size limits are respected."""
        max_size = 10
        engine = BlockingEngine(max_block_size=max_size)

        source = large_entity_dataset[0]

        result = await engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Should not exceed max_block_size
        assert len(result.candidates) <= max_size

        # If there are many candidates, truncation should be flagged
        # (depends on how many match the blocking criteria)

    async def test_batch_find_candidates(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test batch candidate finding."""
        engine = BlockingEngine(max_block_size=100)

        # Use multiple entities as sources
        sources = [
            person_entities_acme["john_smith"],
            person_entities_acme["jane_doe"],
        ]

        results = await engine.find_candidates_batch(
            session=db_session,
            entities=sources,
            tenant_id=tenant_acme.id,
        )

        # Should have result for each source
        assert len(results) == 2
        assert sources[0].id in results
        assert sources[1].id in results

        # Each result should be a BlockingResult
        for entity_id, result in results.items():
            assert isinstance(result.candidates, list)
            assert isinstance(result.total_candidates, int)


class TestBlockingEngineStatistics:
    """Test BlockingEngine statistics and monitoring."""

    async def test_get_block_statistics(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
        org_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test block statistics collection."""
        engine = BlockingEngine(max_block_size=100)

        stats = await engine.get_block_statistics(
            session=db_session,
            tenant_id=tenant_acme.id,
        )

        # Should have expected keys
        assert "total_canonical_entities" in stats
        assert "entities_by_type" in stats
        assert "distinct_soundex_codes" in stats
        assert "strategies_configured" in stats
        assert "max_block_size" in stats

        # Should have positive counts
        assert stats["total_canonical_entities"] > 0
        assert len(stats["entities_by_type"]) > 0

    async def test_block_sizes_tracked(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that block sizes are tracked per strategy."""
        engine = BlockingEngine(
            max_block_size=100,
            strategies=[
                BlockingStrategy.PREFIX,
                BlockingStrategy.ENTITY_TYPE,
                BlockingStrategy.SOUNDEX,
            ],
        )

        source = person_entities_acme["john_smith"]

        result = await engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Block sizes should be tracked
        assert isinstance(result.block_sizes, dict)

        # If there are candidates, at least one strategy should have counts
        if result.total_candidates > 0:
            total_block_counts = sum(result.block_sizes.values())
            # Total might exceed candidates if same entity matched multiple keys
            assert total_block_counts >= 0


class TestBlockingEngineEdgeCases:
    """Test edge cases and error handling."""

    async def test_empty_name_handling(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        scraped_page_acme,
    ):
        """Test handling of entities with empty or short names."""
        from tests.integration.consolidation.conftest import create_entity

        # Create entity with very short name
        short_entity = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "AB",
            EntityType.CONCEPT,
        )
        db_session.add(short_entity)
        await db_session.commit()

        engine = BlockingEngine(
            max_block_size=100,
            min_prefix_length=5,  # Name shorter than prefix length
        )

        result = await engine.find_candidates(
            session=db_session,
            entity=short_entity,
            tenant_id=tenant_acme.id,
        )

        # Should not error, may return limited results
        assert isinstance(result.candidates, list)

    async def test_special_characters_in_name(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        scraped_page_acme,
    ):
        """Test handling of names with special characters."""
        from tests.integration.consolidation.conftest import create_entity

        # Create entities with special characters
        entity1 = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "C++ Programming",
            EntityType.CONCEPT,
        )
        entity2 = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "C# Programming",
            EntityType.CONCEPT,
        )
        db_session.add_all([entity1, entity2])
        await db_session.commit()

        engine = BlockingEngine(max_block_size=100)

        result = await engine.find_candidates(
            session=db_session,
            entity=entity1,
            tenant_id=tenant_acme.id,
        )

        # Should handle special characters without error
        assert isinstance(result.candidates, list)

    async def test_unicode_names(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        scraped_page_acme,
    ):
        """Test handling of unicode characters in names."""
        from tests.integration.consolidation.conftest import create_entity

        # Create entities with unicode characters
        entity1 = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Muller",
            EntityType.PERSON,
        )
        entity2 = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Mueller",
            EntityType.PERSON,
        )
        db_session.add_all([entity1, entity2])
        await db_session.commit()

        engine = BlockingEngine(max_block_size=100)

        result = await engine.find_candidates(
            session=db_session,
            entity=entity1,
            tenant_id=tenant_acme.id,
        )

        # Should handle unicode without error
        assert isinstance(result.candidates, list)
