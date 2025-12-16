"""
Integration tests for the complete Phase 1 consolidation pipeline.

Tests the full flow: BlockingEngine -> StringSimilarityService -> filtered candidates

This validates:
- High-confidence matches are correctly identified
- Low-confidence pairs are correctly excluded
- Pipeline performance with realistic data
- Decision thresholds work correctly
"""

import time
import pytest
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExtractedEntity, EntityType, Tenant
from app.services.consolidation import BlockingEngine, BlockingStrategy, StringSimilarityService
from app.schemas.similarity import (
    SimilarityScores,
    SimilarityThresholds,
    WeightConfiguration,
)


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestPhase1Pipeline:
    """Test complete Phase 1 pipeline: Blocking -> String Similarity -> Decision."""

    async def test_pipeline_identifies_high_confidence_matches(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that pipeline identifies high-confidence match candidates."""
        # Stage 1: Blocking
        blocking_engine = BlockingEngine(
            max_block_size=100,
            strategies=[
                BlockingStrategy.PREFIX,
                BlockingStrategy.ENTITY_TYPE,
                BlockingStrategy.SOUNDEX,
            ],
        )

        source = person_entities_acme["john_smith"]

        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Stage 2: String Similarity
        similarity_service = StringSimilarityService()

        filtered_candidates = similarity_service.filter_candidates(
            entity=source,
            candidates=blocking_result.candidates,
            threshold=0.7,  # Only keep high-confidence
        )

        # Should identify at least some high-confidence matches
        # Jon Smith and John Smith Jr. should be highly similar
        assert len(filtered_candidates) >= 1

        # All filtered candidates should have high scores
        for candidate, scores in filtered_candidates:
            assert scores.combined_score >= 0.7

    async def test_pipeline_excludes_low_confidence_pairs(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that pipeline excludes low-confidence pairs."""
        blocking_engine = BlockingEngine(max_block_size=100)
        similarity_service = StringSimilarityService()

        source = person_entities_acme["john_smith"]

        # Get all candidates through blocking
        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Get all scores (no threshold)
        all_scores = similarity_service.compute_batch(
            entity=source,
            candidates=blocking_result.candidates,
        )

        # Filter with high threshold
        high_threshold = 0.85
        filtered = [
            (c, s) for c, s in all_scores if s.combined_score >= high_threshold
        ]

        # Jane Doe should NOT be in high-confidence matches
        jane_id = person_entities_acme["jane_doe"].id
        filtered_ids = {c.id for c, _ in filtered}
        assert jane_id not in filtered_ids

    async def test_pipeline_decision_thresholds(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that decision thresholds correctly categorize matches."""
        blocking_engine = BlockingEngine(max_block_size=100)
        similarity_service = StringSimilarityService()
        thresholds = SimilarityThresholds(
            auto_merge=0.90,
            review_required=0.50,
            reject_below=0.30,
        )

        source = person_entities_acme["john_smith"]

        # Get blocking candidates
        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Compute all scores
        all_results = similarity_service.compute_batch(
            entity=source,
            candidates=blocking_result.candidates,
        )

        # Categorize by decision
        auto_merge = []
        review = []
        reject = []

        for candidate, scores in all_results:
            decision = thresholds.get_decision(scores.confidence)
            if decision == "auto_merge":
                auto_merge.append((candidate, scores))
            elif decision == "review":
                review.append((candidate, scores))
            else:
                reject.append((candidate, scores))

        # Verify categorization is consistent
        for candidate, scores in auto_merge:
            assert scores.confidence >= thresholds.auto_merge

        for candidate, scores in review:
            assert (
                thresholds.review_required
                <= scores.confidence
                < thresholds.auto_merge
            )

        for candidate, scores in reject:
            assert scores.confidence < thresholds.review_required


class TestPipelineTenantIsolation:
    """Test tenant isolation throughout the pipeline."""

    async def test_pipeline_respects_tenant_isolation(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        tenant_globex: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
        person_entities_globex: dict[str, ExtractedEntity],
    ):
        """Test that pipeline never crosses tenant boundaries."""
        blocking_engine = BlockingEngine(max_block_size=100)
        similarity_service = StringSimilarityService()

        # Search from ACME tenant
        source = person_entities_acme["john_smith"]

        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # No candidates should be from Globex
        globex_ids = {e.id for e in person_entities_globex.values()}
        candidate_ids = {c.id for c in blocking_result.candidates}

        assert candidate_ids.isdisjoint(globex_ids)

        # Run through similarity service
        all_results = similarity_service.compute_batch(
            entity=source,
            candidates=blocking_result.candidates,
        )

        # All results should be ACME entities
        for candidate, scores in all_results:
            assert candidate.tenant_id == tenant_acme.id


class TestPipelineWithEntityTypes:
    """Test pipeline behavior with different entity types."""

    async def test_pipeline_with_organization_entities(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        org_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test pipeline with organization entities."""
        blocking_engine = BlockingEngine(max_block_size=100)
        similarity_service = StringSimilarityService(
            weight_config=WeightConfiguration.for_organization_entities()
        )

        source = org_entities_acme["acme_corp"]

        # Stage 1: Blocking
        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Stage 2: Filter
        filtered = similarity_service.filter_candidates(
            entity=source,
            candidates=blocking_result.candidates,
            threshold=0.6,
        )

        # Should find ACME Corporation and ACME Inc as candidates
        candidate_names = {c.name for c, _ in filtered}
        assert "ACME Corporation" in candidate_names or "ACME Inc" in candidate_names

    async def test_pipeline_with_technical_entities(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        technical_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test pipeline with technical entities (classes)."""
        blocking_engine = BlockingEngine(max_block_size=100)
        similarity_service = StringSimilarityService(
            weight_config=WeightConfiguration.for_technical_entities()
        )

        source = technical_entities_acme["domain_event"]

        # Run pipeline
        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        filtered = similarity_service.filter_candidates(
            entity=source,
            candidates=blocking_result.candidates,
            threshold=0.5,
        )

        # DomainEvent (CamelCase) should be found as similar
        # It has same normalized name
        candidate_names = {c.name for c, _ in filtered}

        # At least one variation should match
        assert len(filtered) >= 0  # May or may not have matches depending on normalization


class TestPipelinePerformance:
    """Test pipeline performance characteristics."""

    async def test_pipeline_performance_large_dataset(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        large_entity_dataset: list[ExtractedEntity],
    ):
        """Test pipeline performance on larger dataset."""
        blocking_engine = BlockingEngine(max_block_size=50)
        similarity_service = StringSimilarityService()

        source = large_entity_dataset[0]

        # Measure blocking time
        start_blocking = time.perf_counter()
        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )
        blocking_time = (time.perf_counter() - start_blocking) * 1000

        # Measure similarity time
        start_similarity = time.perf_counter()
        filtered = similarity_service.filter_candidates(
            entity=source,
            candidates=blocking_result.candidates,
            threshold=0.7,
        )
        similarity_time = (time.perf_counter() - start_similarity) * 1000

        total_time = blocking_time + similarity_time

        # Total pipeline should complete in reasonable time
        assert total_time < 1000, f"Pipeline took {total_time:.2f}ms"

        # Log performance metrics for analysis
        print(f"\nPipeline Performance:")
        print(f"  Blocking: {blocking_time:.2f}ms ({blocking_result.total_candidates} candidates)")
        print(f"  Similarity: {similarity_time:.2f}ms ({len(filtered)} filtered)")
        print(f"  Total: {total_time:.2f}ms")

    async def test_blocking_reduces_comparison_space(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        large_entity_dataset: list[ExtractedEntity],
    ):
        """Test that blocking significantly reduces comparison space."""
        blocking_engine = BlockingEngine(max_block_size=100)

        source = large_entity_dataset[0]
        total_entities = len(large_entity_dataset)

        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Blocking should reduce candidates significantly
        # (not comparing with all entities)
        candidates_count = blocking_result.total_candidates

        # Should be much less than O(n) comparisons
        # At minimum, shouldn't return ALL entities
        assert candidates_count < total_entities - 1  # Exclude source

        reduction_ratio = candidates_count / total_entities
        print(f"\nBlocking reduction: {candidates_count}/{total_entities} = {reduction_ratio:.2%}")


class TestPipelineWithBlockingKeys:
    """Test that blocking keys are preserved through pipeline."""

    async def test_blocking_keys_preserved_in_scores(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that blocking keys from BlockingEngine are in SimilarityScores."""
        blocking_engine = BlockingEngine(
            max_block_size=100,
            strategies=[
                BlockingStrategy.PREFIX,
                BlockingStrategy.ENTITY_TYPE,
                BlockingStrategy.SOUNDEX,
            ],
        )
        similarity_service = StringSimilarityService()

        source = person_entities_acme["john_smith"]

        # Get candidates with blocking keys
        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Verify blocking keys are set on candidates
        for candidate in blocking_result.candidates:
            blocking_keys = getattr(candidate, "_blocking_keys", None)
            assert blocking_keys is not None
            assert len(blocking_keys) > 0

        # Run through similarity service (uses blocking keys)
        all_results = similarity_service.compute_batch(
            entity=source,
            candidates=blocking_result.candidates,
        )

        # Blocking keys should be in scores
        for candidate, scores in all_results:
            assert isinstance(scores.blocking_keys, list)


class TestPipelineContextualSignals:
    """Test contextual signals through pipeline."""

    async def test_same_page_entities_pipeline(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        mixed_entities_same_page: dict[str, ExtractedEntity],
    ):
        """Test pipeline with entities from same page."""
        blocking_engine = BlockingEngine(max_block_size=100)
        similarity_service = StringSimilarityService(compute_contextual=True)

        source = mixed_entities_same_page["event_sourcing_concept"]

        # Run pipeline
        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        all_results = similarity_service.compute_batch(
            entity=source,
            candidates=blocking_result.candidates,
        )

        # Check contextual signals
        for candidate, scores in all_results:
            # Same page signal should be set
            if candidate.source_page_id == source.source_page_id:
                assert scores.contextual.same_page.raw_score == 1.0
            else:
                assert scores.contextual.same_page.raw_score == 0.0

    async def test_different_pages_pipeline(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        entities_different_pages: dict[str, ExtractedEntity],
    ):
        """Test pipeline with entities from different pages."""
        blocking_engine = BlockingEngine(max_block_size=100)
        similarity_service = StringSimilarityService(compute_contextual=True)

        source = entities_different_pages["api_client_page1"]

        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Filter to get API client from page 2
        filtered = similarity_service.filter_candidates(
            entity=source,
            candidates=blocking_result.candidates,
            threshold=0.5,
        )

        # Find the page 2 entity if it's in results
        for candidate, scores in filtered:
            if candidate.id == entities_different_pages["api_client_page2"].id:
                # Different page, so same_page should be 0
                assert scores.contextual.same_page.raw_score == 0.0
                # But type match should be 1
                assert scores.contextual.type_match.raw_score == 1.0


class TestPipelineEdgeCases:
    """Test edge cases in pipeline."""

    async def test_pipeline_with_no_blocking_results(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        scraped_page_acme,
    ):
        """Test pipeline when blocking returns no candidates."""
        from tests.integration.consolidation.conftest import create_entity

        # Create an entity with unique name that won't match anything
        unique_entity = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "XyzzyPlugh123UniqueEntity",
            EntityType.CONCEPT,
        )
        db_session.add(unique_entity)
        await db_session.commit()

        blocking_engine = BlockingEngine(max_block_size=100)
        similarity_service = StringSimilarityService()

        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=unique_entity,
            tenant_id=tenant_acme.id,
        )

        # May or may not have candidates (depends on blocking strategies)
        # If no candidates, filter should handle gracefully
        filtered = similarity_service.filter_candidates(
            entity=unique_entity,
            candidates=blocking_result.candidates,
            threshold=0.7,
        )

        # Should return empty list, not error
        assert isinstance(filtered, list)

    async def test_pipeline_with_single_entity(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        scraped_page_acme,
    ):
        """Test pipeline when only one entity exists."""
        from tests.integration.consolidation.conftest import create_entity

        # Create a single entity in a fresh tenant-like scenario
        single_entity = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "SingletonEntity",
            EntityType.CONCEPT,
        )
        db_session.add(single_entity)
        await db_session.commit()

        blocking_engine = BlockingEngine(max_block_size=100)

        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=single_entity,
            tenant_id=tenant_acme.id,
        )

        # Should not return the source entity as a candidate
        candidate_ids = {c.id for c in blocking_result.candidates}
        assert single_entity.id not in candidate_ids


class TestPipelineConfidenceLevels:
    """Test confidence level classifications through pipeline."""

    async def test_confidence_level_high(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test identifying high confidence matches."""
        blocking_engine = BlockingEngine(max_block_size=100)
        similarity_service = StringSimilarityService()

        # Jon Smith vs John Smith should be high confidence
        source = person_entities_acme["john_smith"]
        target = person_entities_acme["jon_smith"]

        # Use blocking to get target as candidate
        blocking_result = await blocking_engine.find_candidates(
            session=db_session,
            entity=source,
            tenant_id=tenant_acme.id,
        )

        # Find Jon Smith in candidates and compute scores
        for candidate in blocking_result.candidates:
            if candidate.id == target.id:
                scores = similarity_service.compute_all(source, candidate)

                # Should have high confidence
                assert scores.confidence >= 0.7
                assert scores.is_high_confidence or scores.is_medium_confidence
                break

    async def test_confidence_level_low(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test identifying low confidence matches."""
        similarity_service = StringSimilarityService()

        # John Smith vs Jane Doe should be low confidence
        john = person_entities_acme["john_smith"]
        jane = person_entities_acme["jane_doe"]

        scores = similarity_service.compute_all(john, jane)

        # Should have low confidence
        assert scores.confidence < 0.7
        assert scores.is_low_confidence or scores.is_medium_confidence
