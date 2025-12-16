"""Domain schema models and registry for adaptive extraction.

This package provides infrastructure for domain-specific extraction:
- Domain schemas defining entity types, relationship types, and prompts
- Registry for loading and managing domain schemas
- Models for classification results and extraction strategies

Example usage:
    from app.extraction.domains import (
        DomainSchema,
        EntityTypeSchema,
        RelationshipTypeSchema,
        ClassificationResult,
        ExtractionStrategy,
    )

    # Create a domain schema programmatically
    schema = DomainSchema(
        domain_id="literature_fiction",
        display_name="Literature & Fiction",
        description="Novels, plays, and narrative works",
        entity_types=[
            EntityTypeSchema(id="character", description="A person in the narrative"),
        ],
        relationship_types=[
            RelationshipTypeSchema(id="loves", description="Romantic love between characters"),
        ],
        extraction_prompt_template="Extract entities from: {content}",
    )
"""

from app.extraction.domains.models import (
    ClassificationResult,
    ConfidenceThresholds,
    DomainSchema,
    DomainSummary,
    EntityTypeSchema,
    ExtractionStrategy,
    PropertySchema,
    RelationshipTypeSchema,
)

__all__ = [
    "ClassificationResult",
    "ConfidenceThresholds",
    "DomainSchema",
    "DomainSummary",
    "EntityTypeSchema",
    "ExtractionStrategy",
    "PropertySchema",
    "RelationshipTypeSchema",
]
