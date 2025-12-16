"""
Unit tests for the map_entity_type function after enum to string migration.

These tests verify that:
1. Known entity types are preserved
2. Domain-specific types pass through correctly
3. Normalization (lowercase, underscore) works
4. Empty/None values fallback to 'custom'
"""

import pytest

from app.eventsourcing.projections.extraction import map_entity_type


class TestMapEntityTypeLegacyTypes:
    """Test that legacy EntityType enum values work correctly."""

    def test_lowercase_legacy_types(self):
        """Test lowercase legacy types pass through unchanged."""
        legacy_types = [
            "person", "organization", "location", "event", "product",
            "concept", "document", "date", "custom",
            "function", "class", "module", "pattern", "example",
            "parameter", "return_type", "exception"
        ]

        for legacy_type in legacy_types:
            assert map_entity_type(legacy_type) == legacy_type

    def test_uppercase_legacy_types(self):
        """Test uppercase legacy types are normalized to lowercase."""
        assert map_entity_type("PERSON") == "person"
        assert map_entity_type("ORGANIZATION") == "organization"
        assert map_entity_type("FUNCTION") == "function"
        assert map_entity_type("CLASS") == "class"

    def test_mixed_case_legacy_types(self):
        """Test mixed case legacy types are normalized."""
        assert map_entity_type("Person") == "person"
        assert map_entity_type("Organization") == "organization"
        assert map_entity_type("Function") == "function"


class TestMapEntityTypeDomainSpecific:
    """Test domain-specific entity types pass through correctly."""

    def test_domain_specific_types_pass_through(self):
        """Test domain-specific types are accepted and normalized."""
        domain_types = {
            "character": "character",
            "theme": "theme",
            "plot_point": "plot_point",
            "setting": "setting",
            "motif": "motif",
            "symbol": "symbol",
        }

        for input_type, expected in domain_types.items():
            assert map_entity_type(input_type) == expected

    def test_uppercase_domain_types(self):
        """Test uppercase domain-specific types are lowercased."""
        assert map_entity_type("CHARACTER") == "character"
        assert map_entity_type("THEME") == "theme"
        assert map_entity_type("PLOT_POINT") == "plot_point"

    def test_mixed_case_domain_types(self):
        """Test mixed case domain-specific types."""
        assert map_entity_type("Character") == "character"
        assert map_entity_type("PlotPoint") == "plotpoint"  # No camelCase conversion


class TestMapEntityTypeNormalization:
    """Test normalization of entity type strings."""

    def test_space_to_underscore(self):
        """Test spaces are converted to underscores."""
        assert map_entity_type("plot point") == "plot_point"
        assert map_entity_type("main character") == "main_character"

    def test_hyphen_to_underscore(self):
        """Test hyphens are converted to underscores."""
        assert map_entity_type("plot-point") == "plot_point"
        assert map_entity_type("main-character") == "main_character"

    def test_whitespace_stripped(self):
        """Test leading/trailing whitespace is stripped."""
        assert map_entity_type("  person  ") == "person"
        assert map_entity_type("\tcharacter\n") == "character"

    def test_double_underscore_collapsed(self):
        """Test double underscores are collapsed to single."""
        assert map_entity_type("plot__point") == "plot_point"
        assert map_entity_type("main___character") == "main_character"

    def test_leading_trailing_underscore_stripped(self):
        """Test leading/trailing underscores are stripped."""
        assert map_entity_type("_person_") == "person"
        assert map_entity_type("__character__") == "character"


class TestMapEntityTypeFallback:
    """Test fallback behavior for edge cases."""

    def test_empty_string_fallback(self):
        """Test empty string falls back to 'custom'."""
        assert map_entity_type("") == "custom"

    def test_whitespace_only_fallback(self):
        """Test whitespace-only string falls back to 'custom'."""
        assert map_entity_type("   ") == "custom"
        assert map_entity_type("\t\n") == "custom"

    def test_underscore_only_fallback(self):
        """Test underscore-only string falls back to 'custom'."""
        assert map_entity_type("_") == "custom"
        assert map_entity_type("___") == "custom"


class TestMapEntityTypeArbitraryStrings:
    """Test that arbitrary strings are accepted (for future flexibility)."""

    def test_arbitrary_strings_accepted(self):
        """Test that arbitrary entity types are accepted."""
        arbitrary_types = [
            "protagonist",
            "antagonist",
            "literary_device",
            "historical_figure",
            "scientific_concept",
            "api_endpoint",
        ]

        for arbitrary_type in arbitrary_types:
            result = map_entity_type(arbitrary_type)
            assert result == arbitrary_type.lower()
            assert isinstance(result, str)

    def test_long_entity_type(self):
        """Test that long entity types are accepted."""
        long_type = "very_long_domain_specific_entity_type_name"
        assert map_entity_type(long_type) == long_type

    def test_numeric_suffix(self):
        """Test entity types with numeric suffixes."""
        assert map_entity_type("character_v2") == "character_v2"
        assert map_entity_type("entity_123") == "entity_123"
