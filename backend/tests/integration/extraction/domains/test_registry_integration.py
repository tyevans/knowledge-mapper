"""Integration tests for DomainSchemaRegistry with real schema files.

These tests verify that the registry works correctly with the actual
production schema files, ensuring all schemas load and validate properly.
"""

from __future__ import annotations

import pytest

from app.extraction.domains.models import DomainSchema, DomainSummary
from app.extraction.domains.registry import (
    DEFAULT_SCHEMA_DIR,
    DomainSchemaRegistry,
    reset_registry_cache,
)


@pytest.mark.integration
class TestRegistryWithRealSchemas:
    """Integration tests using the actual schema files."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before and after each test."""
        reset_registry_cache()
        yield
        reset_registry_cache()

    @pytest.fixture
    def registry(self) -> DomainSchemaRegistry:
        """Create registry with real schema directory."""
        return DomainSchemaRegistry.get_instance(
            schema_dir=DEFAULT_SCHEMA_DIR,
            force_new=True,
        )

    def test_schema_directory_exists(self):
        """Verify the default schema directory exists."""
        assert DEFAULT_SCHEMA_DIR.exists(), (
            f"Schema directory not found: {DEFAULT_SCHEMA_DIR}"
        )
        assert DEFAULT_SCHEMA_DIR.is_dir()

    def test_all_schemas_load_successfully(self, registry: DomainSchemaRegistry):
        """Test that all production schemas load without errors."""
        count = registry.load_schemas()
        assert count >= 6, f"Expected at least 6 schemas, got {count}"

    def test_can_get_each_expected_domain(self, registry: DomainSchemaRegistry):
        """Test that each expected domain is available."""
        registry.load_schemas()

        expected_domains = [
            "technical_documentation",
            "literature_fiction",
            "news_journalism",
            "academic_research",
            "encyclopedia_wiki",
            "business_corporate",
        ]

        for domain_id in expected_domains:
            schema = registry.get_schema(domain_id)
            assert schema is not None, f"Domain {domain_id} not found"
            assert schema.domain_id == domain_id
            assert isinstance(schema, DomainSchema)

    def test_each_schema_has_minimum_entity_types(
        self, registry: DomainSchemaRegistry
    ):
        """Test that each schema has at least 5 entity types."""
        registry.load_schemas()

        for schema in registry:
            assert len(schema.entity_types) >= 5, (
                f"Schema {schema.domain_id} has only "
                f"{len(schema.entity_types)} entity types (minimum 5)"
            )

    def test_each_schema_has_minimum_relationship_types(
        self, registry: DomainSchemaRegistry
    ):
        """Test that each schema has at least 5 relationship types."""
        registry.load_schemas()

        for schema in registry:
            assert len(schema.relationship_types) >= 5, (
                f"Schema {schema.domain_id} has only "
                f"{len(schema.relationship_types)} relationship types (minimum 5)"
            )

    def test_each_schema_has_extraction_prompt(
        self, registry: DomainSchemaRegistry
    ):
        """Test that each schema has an extraction prompt template."""
        registry.load_schemas()

        for schema in registry:
            assert schema.extraction_prompt_template, (
                f"Schema {schema.domain_id} has empty extraction_prompt_template"
            )
            assert len(schema.extraction_prompt_template) > 50, (
                f"Schema {schema.domain_id} has short extraction_prompt_template "
                f"({len(schema.extraction_prompt_template)} chars)"
            )

    def test_list_domains_returns_all_domains(
        self, registry: DomainSchemaRegistry
    ):
        """Test that list_domains returns summaries for all domains."""
        registry.load_schemas()

        domains = registry.list_domains()
        assert len(domains) >= 6

        for summary in domains:
            assert isinstance(summary, DomainSummary)
            assert summary.domain_id
            assert summary.display_name
            assert summary.description
            assert summary.entity_type_count >= 5
            assert summary.relationship_type_count >= 5

    def test_default_schema_is_encyclopedia(
        self, registry: DomainSchemaRegistry
    ):
        """Test that the default schema is encyclopedia_wiki."""
        registry.load_schemas()

        default = registry.get_default_schema()
        assert default is not None
        assert default.domain_id == "encyclopedia_wiki"

    def test_schema_versions_are_valid(self, registry: DomainSchemaRegistry):
        """Test that all schemas have valid semver versions."""
        import re

        registry.load_schemas()

        semver_pattern = re.compile(r"^\d+\.\d+\.\d+$")

        for schema in registry:
            assert semver_pattern.match(schema.version), (
                f"Schema {schema.domain_id} has invalid version: {schema.version}"
            )

    def test_no_duplicate_entity_types_within_schema(
        self, registry: DomainSchemaRegistry
    ):
        """Test that no schema has duplicate entity type IDs."""
        registry.load_schemas()

        for schema in registry:
            entity_ids = schema.get_entity_type_ids()
            assert len(entity_ids) == len(set(entity_ids)), (
                f"Schema {schema.domain_id} has duplicate entity type IDs"
            )

    def test_no_duplicate_relationship_types_within_schema(
        self, registry: DomainSchemaRegistry
    ):
        """Test that no schema has duplicate relationship type IDs."""
        registry.load_schemas()

        for schema in registry:
            rel_ids = schema.get_relationship_type_ids()
            assert len(rel_ids) == len(set(rel_ids)), (
                f"Schema {schema.domain_id} has duplicate relationship type IDs"
            )

    def test_relationship_type_references_valid(
        self, registry: DomainSchemaRegistry
    ):
        """Test that relationship source/target types reference valid entity types."""
        registry.load_schemas()

        for schema in registry:
            entity_ids = set(schema.get_entity_type_ids())

            for rel in schema.relationship_types:
                for source_type in rel.valid_source_types:
                    assert source_type in entity_ids, (
                        f"Schema {schema.domain_id}: relationship '{rel.id}' "
                        f"references unknown source type '{source_type}'"
                    )
                for target_type in rel.valid_target_types:
                    assert target_type in entity_ids, (
                        f"Schema {schema.domain_id}: relationship '{rel.id}' "
                        f"references unknown target type '{target_type}'"
                    )


@pytest.mark.integration
class TestRegistryPerformance:
    """Performance tests for the registry."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before and after each test."""
        reset_registry_cache()
        yield
        reset_registry_cache()

    def test_schema_loading_performance(self):
        """Test that schema loading is reasonably fast."""
        import time

        registry = DomainSchemaRegistry.get_instance(
            schema_dir=DEFAULT_SCHEMA_DIR,
            force_new=True,
        )

        start = time.time()
        registry.load_schemas()
        elapsed = time.time() - start

        # Loading should complete in under 1 second
        assert elapsed < 1.0, f"Schema loading took {elapsed:.2f}s (expected <1s)"

    def test_schema_access_performance(self):
        """Test that schema access is fast after loading."""
        import time

        registry = DomainSchemaRegistry.get_instance(
            schema_dir=DEFAULT_SCHEMA_DIR,
            force_new=True,
        )
        registry.load_schemas()

        start = time.time()
        for _ in range(1000):
            registry.get_schema("literature_fiction")
        elapsed = time.time() - start

        # 1000 accesses should complete in under 100ms
        assert elapsed < 0.1, (
            f"1000 schema accesses took {elapsed:.2f}s (expected <0.1s)"
        )


@pytest.mark.integration
class TestRegistryConcurrency:
    """Concurrency tests for the registry."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before and after each test."""
        reset_registry_cache()
        yield
        reset_registry_cache()

    def test_concurrent_schema_access(self):
        """Test that concurrent access works correctly."""
        import threading

        registry = DomainSchemaRegistry.get_instance(
            schema_dir=DEFAULT_SCHEMA_DIR,
            force_new=True,
        )
        registry.load_schemas()

        results = []
        errors = []

        def access_schema():
            try:
                for _ in range(100):
                    schema = registry.get_schema("literature_fiction")
                    results.append(schema.domain_id)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=access_schema) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"
        assert len(results) == 1000
        assert all(r == "literature_fiction" for r in results)

    def test_concurrent_lazy_loading(self):
        """Test that concurrent lazy loading works correctly."""
        import threading

        # Create new registry without loading
        registry = DomainSchemaRegistry.get_instance(
            schema_dir=DEFAULT_SCHEMA_DIR,
            force_new=True,
        )

        results = []
        errors = []

        def trigger_lazy_load():
            try:
                # This should trigger lazy loading
                schema = registry.get_schema("literature_fiction")
                results.append(schema.domain_id)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=trigger_lazy_load) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"
        assert len(results) == 10
        assert all(r == "literature_fiction" for r in results)
