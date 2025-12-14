"""
Extracted entity models for knowledge graph construction.

This module defines the ExtractedEntity and EntityRelationship models,
which represent entities extracted from scraped pages and their relationships.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.scraped_page import ScrapedPage
    from app.models.tenant import Tenant


class EntityType(str, enum.Enum):
    """Types of entities that can be extracted."""

    # General entity types
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    EVENT = "event"
    PRODUCT = "product"
    CONCEPT = "concept"
    DOCUMENT = "document"
    DATE = "date"
    CUSTOM = "custom"

    # Documentation-specific types (for technical documentation extraction)
    FUNCTION = "function"  # Callable functions with signatures
    CLASS = "class"  # OOP classes with methods/attributes
    MODULE = "module"  # Python modules and packages
    PATTERN = "pattern"  # Design patterns, architectural patterns
    EXAMPLE = "example"  # Code examples and usage demonstrations
    PARAMETER = "parameter"  # Function/method parameters
    RETURN_TYPE = "return_type"  # Function return types
    EXCEPTION = "exception"  # Exception classes


class ExtractionMethod(str, enum.Enum):
    """How the entity was extracted."""

    SCHEMA_ORG = "schema_org"  # From JSON-LD/Schema.org markup
    OPEN_GRAPH = "open_graph"  # From Open Graph meta tags
    LLM_CLAUDE = "llm_claude"  # Via Claude semantic extraction
    LLM_OLLAMA = "llm_ollama"  # Via local Ollama LLM extraction
    PATTERN = "pattern"  # Via regex/pattern matching
    SPACY = "spacy"  # Via spaCy NER fallback
    HYBRID = "hybrid"  # Combination of methods


class ExtractedEntity(Base):
    """
    Represents an entity extracted from a scraped page.

    Entities are the building blocks of the knowledge graph. They can be
    people, organizations, locations, events, etc., extracted via Schema.org
    markup or LLM analysis.

    Attributes:
        id: UUID primary key for security
        tenant_id: Foreign key to tenant (RLS enforced)
        source_page_id: Foreign key to source page
        entity_type: Type of entity (person, org, location, etc.)
        name: Entity name as extracted
        normalized_name: Normalized name for deduplication
        description: Optional description of the entity
        external_ids: External identifiers (wikidata, etc.)
        properties: Entity-specific attributes as JSON
        extraction_method: How the entity was extracted
        confidence_score: Confidence in extraction (0.0-1.0)
        source_text: Text snippet where entity was found
        neo4j_node_id: Neo4j node ID for sync tracking
        synced_to_neo4j: Whether entity is synced to Neo4j
        synced_at: When entity was synced to Neo4j
        created_at: Timestamp of creation (inherited)
        updated_at: Timestamp of last update (inherited)
    """

    __tablename__ = "extracted_entities"

    # Primary key - UUID for security
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        insert_default=uuid.uuid4,
        index=True,
        comment="UUID primary key for security",
    )

    # Tenant isolation (RLS enforced)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tenant this entity belongs to (RLS enforced)",
    )

    # Source reference
    source_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scraped_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Page this entity was extracted from",
    )

    # Entity identification
    entity_type: Mapped[EntityType] = mapped_column(
        SQLEnum(
            EntityType,
            name="entity_type",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        index=True,
        comment="Type of entity",
    )

    name: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        index=True,
        comment="Entity name as extracted",
    )

    normalized_name: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        index=True,
        comment="Normalized name for deduplication",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional description of the entity",
    )

    # External identifiers for linking
    external_ids: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        insert_default=dict,
        comment="External identifiers (wikidata, schema_org_id, etc.)",
    )

    # Entity properties
    properties: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        insert_default=dict,
        comment="Entity-specific attributes as JSON",
    )

    # Extraction metadata
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        SQLEnum(
            ExtractionMethod,
            name="extraction_method",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        index=True,
        comment="How the entity was extracted",
    )

    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        insert_default=1.0,
        comment="Confidence in extraction (0.0-1.0)",
    )

    source_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Text snippet where entity was found",
    )

    # Neo4j sync status
    neo4j_node_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Neo4j node element ID for sync tracking",
    )

    synced_to_neo4j: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        insert_default=False,
        index=True,
        comment="Whether entity is synced to Neo4j",
    )

    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When entity was synced to Neo4j",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        doc="Tenant this entity belongs to",
    )

    source_page: Mapped["ScrapedPage"] = relationship(
        "ScrapedPage",
        back_populates="entities",
        doc="Page this entity was extracted from",
    )

    # Relationships where this entity is the source
    outgoing_relationships: Mapped[list["EntityRelationship"]] = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.source_entity_id",
        back_populates="source_entity",
        cascade="all, delete-orphan",
        doc="Relationships where this entity is the source",
    )

    # Relationships where this entity is the target
    incoming_relationships: Mapped[list["EntityRelationship"]] = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.target_entity_id",
        back_populates="target_entity",
        cascade="all, delete-orphan",
        doc="Relationships where this entity is the target",
    )

    def __init__(self, **kwargs):
        """Initialize entity with default values for optional fields."""
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "external_ids" not in kwargs:
            kwargs["external_ids"] = {}
        if "properties" not in kwargs:
            kwargs["properties"] = {}
        # Auto-normalize name if not provided
        if "normalized_name" not in kwargs and "name" in kwargs:
            kwargs["normalized_name"] = self._normalize_name(kwargs["name"])
        super().__init__(**kwargs)

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize entity name for deduplication."""
        import unicodedata

        # Lowercase and strip whitespace
        normalized = name.lower().strip()
        # Remove accents
        normalized = unicodedata.normalize("NFKD", normalized)
        normalized = "".join(c for c in normalized if not unicodedata.combining(c))
        # Collapse multiple spaces
        normalized = " ".join(normalized.split())
        return normalized

    def __repr__(self) -> str:
        """Return string representation of the entity."""
        return f"<ExtractedEntity {self.id} '{self.name}' ({self.entity_type.value})>"


class EntityRelationship(Base):
    """
    Represents a relationship between two extracted entities.

    Relationships form the edges of the knowledge graph, connecting
    entities with typed, directed relationships.

    Attributes:
        id: UUID primary key for security
        tenant_id: Foreign key to tenant (RLS enforced)
        source_entity_id: Source entity of the relationship
        target_entity_id: Target entity of the relationship
        relationship_type: Type of relationship (e.g., WORKS_FOR, LOCATED_IN)
        properties: Additional relationship properties
        confidence_score: Confidence in the relationship (0.0-1.0)
        neo4j_relationship_id: Neo4j relationship ID for sync tracking
        synced_to_neo4j: Whether relationship is synced to Neo4j
        created_at: Timestamp of creation (inherited)
        updated_at: Timestamp of last update (inherited)
    """

    __tablename__ = "entity_relationships"

    # Primary key - UUID for security
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        insert_default=uuid.uuid4,
        index=True,
        comment="UUID primary key for security",
    )

    # Tenant isolation (RLS enforced)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Tenant this relationship belongs to (RLS enforced)",
    )

    # Relationship endpoints
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extracted_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Source entity of the relationship",
    )

    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extracted_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Target entity of the relationship",
    )

    # Relationship metadata
    relationship_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Type of relationship (e.g., WORKS_FOR, LOCATED_IN)",
    )

    properties: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        insert_default=dict,
        comment="Additional relationship properties",
    )

    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        insert_default=1.0,
        comment="Confidence in the relationship (0.0-1.0)",
    )

    # Neo4j sync status
    neo4j_relationship_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Neo4j relationship element ID for sync tracking",
    )

    synced_to_neo4j: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        insert_default=False,
        index=True,
        comment="Whether relationship is synced to Neo4j",
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        doc="Tenant this relationship belongs to",
    )

    source_entity: Mapped["ExtractedEntity"] = relationship(
        "ExtractedEntity",
        foreign_keys=[source_entity_id],
        back_populates="outgoing_relationships",
        doc="Source entity of the relationship",
    )

    target_entity: Mapped["ExtractedEntity"] = relationship(
        "ExtractedEntity",
        foreign_keys=[target_entity_id],
        back_populates="incoming_relationships",
        doc="Target entity of the relationship",
    )

    def __init__(self, **kwargs):
        """Initialize relationship with default values for optional fields."""
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "properties" not in kwargs:
            kwargs["properties"] = {}
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        """Return string representation of the relationship."""
        return f"<EntityRelationship {self.id} ({self.relationship_type})>"
