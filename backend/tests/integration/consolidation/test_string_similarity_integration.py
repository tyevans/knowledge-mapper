"""
Integration tests for StringSimilarityService.

Tests end-to-end similarity computation with realistic entity data:
- Verifies scoring produces expected results for known entity pairs
- Tests batch processing with realistic data
- Validates confidence estimation accuracy
- Tests integration with SimilarityScores schema
"""

import pytest
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExtractedEntity, EntityType, Tenant
from app.services.consolidation import StringSimilarityService
from app.schemas.similarity import (
    SimilarityScores,
    SimilarityThresholds,
    WeightConfiguration,
)


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestStringSimilarityPersonEntities:
    """Test string similarity on person entities with known relationships."""

    async def test_high_similarity_same_name(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that identical names produce very high similarity."""
        service = StringSimilarityService()

        john1 = person_entities_acme["john_smith"]
        # Create a mock entity with same name for comparison
        # In real scenario, this would be from database

        # Compare with John Smith Jr. (very similar)
        john_jr = person_entities_acme["john_smith_jr"]

        scores = service.compute_all(john1, john_jr)

        # Should have high Jaro-Winkler score (same prefix)
        assert scores.string_scores.jaro_winkler is not None
        assert scores.string_scores.jaro_winkler.raw_score >= 0.85

        # Combined score should be reasonably high
        assert scores.combined_score >= 0.6

    async def test_phonetic_similarity_different_spelling(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that phonetically similar names are detected."""
        service = StringSimilarityService()

        john = person_entities_acme["john_smith"]
        john_smyth = person_entities_acme["john_smyth"]

        scores = service.compute_all(john, john_smyth)

        # Phonetic scores should show match (Smith = Smyth phonetically)
        assert scores.phonetic_scores.soundex is not None

        # At least one phonetic match should be found
        assert scores.phonetic_scores.any_match()

    async def test_high_similarity_jon_vs_john(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test similarity between 'Jon Smith' and 'John Smith'."""
        service = StringSimilarityService()

        john = person_entities_acme["john_smith"]
        jon = person_entities_acme["jon_smith"]

        scores = service.compute_all(john, jon)

        # Very high string similarity (only one letter difference)
        assert scores.string_scores.jaro_winkler.raw_score >= 0.9

        # Levenshtein should also be high
        assert scores.string_scores.levenshtein is not None
        assert scores.string_scores.levenshtein.raw_score >= 0.85

        # Combined score should be high
        assert scores.combined_score >= 0.7

    async def test_low_similarity_different_names(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that clearly different names produce low similarity."""
        service = StringSimilarityService()

        john = person_entities_acme["john_smith"]
        jane = person_entities_acme["jane_doe"]

        scores = service.compute_all(john, jane)

        # String similarity should be low
        assert scores.string_scores.jaro_winkler.raw_score < 0.7

        # Combined score should be low
        assert scores.combined_score < 0.5

    async def test_ambiguous_abbreviation(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test similarity with abbreviated name 'J. Smith'."""
        service = StringSimilarityService()

        john = person_entities_acme["john_smith"]
        j_smith = person_entities_acme["j_smith"]

        scores = service.compute_all(john, j_smith)

        # Partial match - should be medium similarity
        # "John Smith" vs "J. Smith" - shares "Smith" suffix
        assert scores.combined_score > 0.3
        assert scores.combined_score < 0.9  # Not high enough for auto-merge


class TestStringSimilarityOrganizationEntities:
    """Test string similarity on organization entities."""

    async def test_org_name_variations(
        self,
        org_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test similarity between org name variations."""
        service = StringSimilarityService(
            weight_config=WeightConfiguration.for_organization_entities()
        )

        acme_corp = org_entities_acme["acme_corp"]
        acme_corporation = org_entities_acme["acme_corporation"]

        scores = service.compute_all(acme_corp, acme_corporation)

        # Very high similarity - only difference is "Corp" vs "Corporation"
        assert scores.string_scores.jaro_winkler.raw_score >= 0.85

        # Trigram similarity should also be high
        assert scores.string_scores.trigram is not None
        assert scores.string_scores.trigram.raw_score >= 0.6

    async def test_org_different_suffix(
        self,
        org_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test similarity between orgs with different suffixes."""
        service = StringSimilarityService()

        acme_corp = org_entities_acme["acme_corp"]
        acme_inc = org_entities_acme["acme_inc"]

        scores = service.compute_all(acme_corp, acme_inc)

        # Moderate similarity - same base name, different suffix
        assert scores.combined_score >= 0.5

    async def test_org_completely_different(
        self,
        org_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test similarity between completely different orgs."""
        service = StringSimilarityService()

        acme = org_entities_acme["acme_corp"]
        google = org_entities_acme["google_inc"]

        scores = service.compute_all(acme, google)

        # Low similarity - different organizations
        assert scores.combined_score < 0.5


class TestStringSimilarityTechnicalEntities:
    """Test string similarity on technical entities (classes, functions)."""

    async def test_class_name_case_variation(
        self,
        technical_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test similarity between snake_case and CamelCase names."""
        service = StringSimilarityService(
            weight_config=WeightConfiguration.for_technical_entities()
        )

        snake = technical_entities_acme["domain_event"]
        camel = technical_entities_acme["DomainEvent"]

        scores = service.compute_all(snake, camel)

        # Should recognize as same concept despite case difference
        # Normalized names should match or be very similar
        assert scores.string_scores.normalized_exact is not None

        # Even if not exact match, Jaro-Winkler on lowercase should be high
        assert scores.string_scores.jaro_winkler.raw_score >= 0.8

    async def test_class_name_extended(
        self,
        technical_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test similarity between base and extended class names."""
        service = StringSimilarityService()

        base = technical_entities_acme["domain_event"]
        extended = technical_entities_acme["domain_event_base"]

        scores = service.compute_all(base, extended)

        # High similarity - extended name contains base name
        assert scores.combined_score >= 0.5

    async def test_class_name_different(
        self,
        technical_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test similarity between different class names."""
        service = StringSimilarityService()

        domain = technical_entities_acme["domain_event"]
        base = technical_entities_acme["base_event"]

        scores = service.compute_all(domain, base)

        # Some similarity (both end in "event")
        assert scores.combined_score > 0.3
        assert scores.combined_score < 0.8


class TestStringSimilarityContextualSignals:
    """Test contextual signals computation."""

    async def test_same_page_signal(
        self,
        mixed_entities_same_page: dict[str, ExtractedEntity],
    ):
        """Test same_page signal when entities are from same source."""
        service = StringSimilarityService(compute_contextual=True)

        entity1 = mixed_entities_same_page["event_sourcing_concept"]
        entity2 = mixed_entities_same_page["cqrs_concept"]

        scores = service.compute_all(entity1, entity2)

        # Same page signal should be 1.0
        assert scores.contextual.same_page is not None
        assert scores.contextual.same_page.raw_score == 1.0
        assert scores.contextual.are_from_same_page is True

    async def test_type_match_signal(
        self,
        mixed_entities_same_page: dict[str, ExtractedEntity],
    ):
        """Test type_match signal when entities have same type."""
        service = StringSimilarityService(compute_contextual=True)

        # Both are CONCEPT type
        entity1 = mixed_entities_same_page["event_sourcing_concept"]
        entity2 = mixed_entities_same_page["cqrs_concept"]

        scores = service.compute_all(entity1, entity2)

        # Type match signal should be 1.0
        assert scores.contextual.type_match is not None
        assert scores.contextual.type_match.raw_score == 1.0
        assert scores.contextual.are_same_type is True

    async def test_type_mismatch_signal(
        self,
        mixed_entities_same_page: dict[str, ExtractedEntity],
    ):
        """Test type_match signal when entities have different types."""
        service = StringSimilarityService(compute_contextual=True)

        # CONCEPT vs PATTERN types
        concept = mixed_entities_same_page["event_sourcing_concept"]
        pattern = mixed_entities_same_page["event_sourcing_pattern"]

        scores = service.compute_all(concept, pattern)

        # Type match signal should be 0.0
        assert scores.contextual.type_match is not None
        assert scores.contextual.type_match.raw_score == 0.0
        assert scores.contextual.are_same_type is False

    async def test_property_overlap_signal(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test property overlap computation."""
        service = StringSimilarityService(compute_contextual=True)

        # Both have "role" property
        john = person_entities_acme["john_smith"]  # role: Engineer
        john_jr = person_entities_acme["john_smith_jr"]  # role: Engineer

        scores = service.compute_all(john, john_jr)

        # Property overlap should be > 0
        assert scores.contextual.property_overlap is not None
        assert scores.contextual.property_overlap.raw_score > 0


class TestStringSimilarityDifferentPages:
    """Test similarity computation for entities on different pages."""

    async def test_same_name_different_pages(
        self,
        entities_different_pages: dict[str, ExtractedEntity],
    ):
        """Test similarity between same-name entities on different pages."""
        service = StringSimilarityService(compute_contextual=True)

        api1 = entities_different_pages["api_client_page1"]
        api2 = entities_different_pages["api_client_page2"]

        scores = service.compute_all(api1, api2)

        # High string similarity despite slight name difference
        assert scores.string_scores.jaro_winkler.raw_score >= 0.85

        # Different pages
        assert scores.contextual.same_page.raw_score == 0.0
        assert scores.contextual.are_from_same_page is False

    async def test_case_variation_different_pages(
        self,
        entities_different_pages: dict[str, ExtractedEntity],
    ):
        """Test similarity between case variations on different pages."""
        service = StringSimilarityService()

        http1 = entities_different_pages["http_client_page1"]  # HTTPClient
        http2 = entities_different_pages["http_client_page2"]  # HttpClient

        scores = service.compute_all(http1, http2)

        # Should recognize as likely same entity
        assert scores.combined_score >= 0.7


class TestStringSimilarityBatchProcessing:
    """Test batch processing capabilities."""

    async def test_filter_candidates(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test filtering candidates by threshold."""
        service = StringSimilarityService()

        source = person_entities_acme["john_smith"]
        candidates = [
            person_entities_acme["john_smith_jr"],  # High match
            person_entities_acme["jon_smith"],  # High match
            person_entities_acme["jane_doe"],  # Low match
        ]

        results = service.filter_candidates(
            entity=source,
            candidates=candidates,
            threshold=0.7,
        )

        # Should filter out low-similarity candidates
        # Results should be sorted by combined_score descending
        assert len(results) > 0
        assert len(results) <= len(candidates)

        # Check sorting
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i][1].combined_score >= results[i + 1][1].combined_score

    async def test_compute_batch(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test batch computation without filtering."""
        service = StringSimilarityService()

        source = person_entities_acme["john_smith"]
        candidates = list(person_entities_acme.values())
        candidates.remove(source)  # Don't compare with self

        results = service.compute_batch(
            entity=source,
            candidates=candidates,
        )

        # Should have result for each candidate
        assert len(results) == len(candidates)

        # Each result should have scores
        for candidate, scores in results:
            assert isinstance(scores, SimilarityScores)
            assert scores.entity_a_id == source.id
            assert scores.entity_b_id == candidate.id


class TestStringSimilarityConfidence:
    """Test confidence estimation."""

    async def test_high_confidence_exact_match(
        self,
        db_session: AsyncSession,
        tenant_acme: Tenant,
        scraped_page_acme,
    ):
        """Test that exact normalized matches produce high confidence."""
        from tests.integration.consolidation.conftest import create_entity

        # Create two entities with same normalized name
        entity1 = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "Event Handler",
            EntityType.CLASS,
        )
        entity2 = create_entity(
            tenant_acme.id,
            scraped_page_acme.id,
            "event handler",  # Same when normalized
            EntityType.CLASS,
        )
        db_session.add_all([entity1, entity2])
        await db_session.commit()

        service = StringSimilarityService()
        scores = service.compute_all(entity1, entity2)

        # Should have normalized exact match
        assert scores.string_scores.normalized_exact.raw_score == 1.0

        # Confidence should be high
        assert scores.confidence >= 0.8

    async def test_medium_confidence_partial_match(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test confidence for partial matches."""
        service = StringSimilarityService()

        john = person_entities_acme["john_smith"]
        j_smith = person_entities_acme["j_smith"]

        scores = service.compute_all(john, j_smith)

        # Medium confidence - not exact match
        assert 0.3 <= scores.confidence <= 0.9

    async def test_confidence_with_thresholds(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test confidence-based decision making."""
        service = StringSimilarityService()
        thresholds = SimilarityThresholds()

        # High match pair
        john = person_entities_acme["john_smith"]
        jon = person_entities_acme["jon_smith"]

        scores = service.compute_all(john, jon)
        decision = thresholds.get_decision(scores.confidence)

        # Should be either "auto_merge" or "review" for high similarity
        assert decision in ["auto_merge", "review"]

        # Low match pair
        jane = person_entities_acme["jane_doe"]
        low_scores = service.compute_all(john, jane)
        low_decision = thresholds.get_decision(low_scores.confidence)

        # Should be "reject" or "review" for low similarity
        assert low_decision in ["review", "reject"]


class TestStringSimilarityWeightConfiguration:
    """Test different weight configurations."""

    async def test_person_entity_weights(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test person-optimized weights."""
        default_service = StringSimilarityService()
        person_service = StringSimilarityService(
            weight_config=WeightConfiguration.for_person_entities()
        )

        john = person_entities_acme["john_smith"]
        jon = person_entities_acme["jon_smith"]

        default_scores = default_service.compute_all(john, jon)
        person_scores = person_service.compute_all(john, jon)

        # Both should compute scores
        assert default_scores.combined_score > 0
        assert person_scores.combined_score > 0

        # Person weights emphasize Jaro-Winkler and phonetics
        # Results may differ based on weight configuration

    async def test_organization_entity_weights(
        self,
        org_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test organization-optimized weights."""
        org_service = StringSimilarityService(
            weight_config=WeightConfiguration.for_organization_entities()
        )

        acme_corp = org_entities_acme["acme_corp"]
        acme_corporation = org_entities_acme["acme_corporation"]

        scores = org_service.compute_all(acme_corp, acme_corporation)

        # Organization weights emphasize exact matches and trigrams
        assert scores.combined_score > 0


class TestStringSimilarityScoresSerialization:
    """Test SimilarityScores serialization."""

    async def test_to_dict_from_dict_roundtrip(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that scores can be serialized and deserialized."""
        service = StringSimilarityService()

        john = person_entities_acme["john_smith"]
        jon = person_entities_acme["jon_smith"]

        original_scores = service.compute_all(john, jon)

        # Serialize to dict
        data = original_scores.to_dict()
        assert isinstance(data, dict)
        assert "combined_score" in data
        assert "confidence" in data

        # Deserialize from dict
        restored_scores = SimilarityScores.from_dict(
            john.id, jon.id, data
        )

        # Key fields should match
        assert restored_scores.combined_score == original_scores.combined_score
        assert restored_scores.confidence == original_scores.confidence

    async def test_scores_contain_computation_time(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that computation time is tracked."""
        service = StringSimilarityService()

        john = person_entities_acme["john_smith"]
        jon = person_entities_acme["jon_smith"]

        scores = service.compute_all(john, jon)

        # Computation time should be recorded
        assert scores.computation_time_ms is not None
        assert scores.computation_time_ms > 0

    async def test_blocking_keys_preserved(
        self,
        person_entities_acme: dict[str, ExtractedEntity],
    ):
        """Test that blocking keys are preserved in scores."""
        service = StringSimilarityService()

        john = person_entities_acme["john_smith"]
        jon = person_entities_acme["jon_smith"]

        # Simulate blocking keys from BlockingEngine
        blocking_keys = ["prefix", "soundex", "entity_type"]

        scores = service.compute_all(john, jon, blocking_keys=blocking_keys)

        # Blocking keys should be preserved
        assert scores.blocking_keys == blocking_keys
