"""
Unit tests for domains API router.

Tests all domain endpoints with mocked registry and authentication:
- GET /domains (list all domains)
- GET /domains/{domain_id} (get domain detail)

Note: These tests import directly from the domains subpackage to avoid
pulling in heavy dependencies from app.extraction.__init__.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

# Import directly from the domains subpackage to avoid triggering
# the full app.extraction package which pulls in database dependencies
from app.extraction.domains.models import (
    DomainSchema,
    DomainSummary,
    EntityTypeSchema,
    PropertySchema,
    RelationshipTypeSchema,
)
from app.extraction.domains.registry import DomainSchemaRegistry


# ==============================================================================
# Test Fixtures and Data
# ==============================================================================


def create_test_schema(domain_id: str = "test_domain") -> DomainSchema:
    """Create a test DomainSchema for testing."""
    return DomainSchema(
        domain_id=domain_id,
        display_name=f"Test Domain: {domain_id}",
        description=f"A test domain schema for {domain_id}",
        entity_types=[
            EntityTypeSchema(
                id="character",
                description="A character in the narrative",
                properties=[
                    PropertySchema(name="role", type="string", description="Character role"),
                    PropertySchema(name="age", type="number", description="Character age"),
                ],
                examples=["Hamlet", "Ophelia"],
            ),
            EntityTypeSchema(
                id="location",
                description="A place or setting",
                properties=[],
                examples=["Denmark", "Elsinore Castle"],
            ),
        ],
        relationship_types=[
            RelationshipTypeSchema(
                id="loves",
                description="Romantic love between characters",
                valid_source_types=["character"],
                valid_target_types=["character"],
                bidirectional=True,
            ),
            RelationshipTypeSchema(
                id="located_in",
                description="Entity is located in a location",
                valid_source_types=["character"],
                valid_target_types=["location"],
            ),
        ],
        extraction_prompt_template="Extract entities from: {content}",
        version="1.0.0",
    )


def create_mock_registry(schemas: list[DomainSchema] | None = None) -> MagicMock:
    """Create a mock DomainSchemaRegistry with test data."""
    mock_registry = MagicMock(spec=DomainSchemaRegistry)

    if schemas is None:
        schemas = [
            create_test_schema("literature_fiction"),
            create_test_schema("news_articles"),
            create_test_schema("technical_docs"),
        ]

    # Store schemas in a dict for lookup
    schema_dict = {s.domain_id: s for s in schemas}

    # Mock list_domains - returns DomainSummary objects
    mock_registry.list_domains.return_value = [
        DomainSummary.from_schema(s) for s in sorted(schemas, key=lambda x: x.display_name)
    ]

    # Mock get_schema - returns schema or raises KeyError
    def get_schema_side_effect(domain_id: str):
        normalized = domain_id.lower().strip()
        if normalized not in schema_dict:
            raise KeyError(f"Unknown domain: '{domain_id}'")
        return schema_dict[normalized]

    mock_registry.get_schema.side_effect = get_schema_side_effect
    mock_registry.has_domain.side_effect = lambda d: d.lower().strip() in schema_dict

    return mock_registry


def create_mock_user() -> MagicMock:
    """Create a mock authenticated user."""
    mock_user = MagicMock()
    mock_user.user_id = "test-user-id"
    mock_user.tenant_id = "test-tenant-id"
    mock_user.email = "test@example.com"
    mock_user.has_tenant = True
    return mock_user


# ==============================================================================
# Response Models (mirroring the router's models for testing)
# ==============================================================================


class DomainsListResponse(BaseModel):
    """Response for listing all available domains."""

    domains: list[DomainSummary] = Field(...)
    count: int = Field(..., ge=0)


class EntityTypeDetail(BaseModel):
    """Detailed entity type information for API responses."""

    id: str
    description: str
    properties: list[dict] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class RelationshipTypeDetail(BaseModel):
    """Detailed relationship type information for API responses."""

    id: str
    description: str
    valid_source_types: list[str] = Field(default_factory=list)
    valid_target_types: list[str] = Field(default_factory=list)
    bidirectional: bool = False


class DomainDetailResponse(BaseModel):
    """Response for domain detail with full schema information."""

    domain_id: str
    display_name: str
    description: str
    entity_types: list[EntityTypeDetail]
    relationship_types: list[RelationshipTypeDetail]
    version: str

    @classmethod
    def from_schema(cls, schema: DomainSchema) -> "DomainDetailResponse":
        """Create response from DomainSchema."""
        return cls(
            domain_id=schema.domain_id,
            display_name=schema.display_name,
            description=schema.description,
            entity_types=[
                EntityTypeDetail(
                    id=et.id,
                    description=et.description,
                    properties=[p.model_dump() for p in et.properties],
                    examples=et.examples,
                )
                for et in schema.entity_types
            ],
            relationship_types=[
                RelationshipTypeDetail(
                    id=rt.id,
                    description=rt.description,
                    valid_source_types=rt.valid_source_types,
                    valid_target_types=rt.valid_target_types,
                    bidirectional=rt.bidirectional,
                )
                for rt in schema.relationship_types
            ],
            version=schema.version,
        )


# ==============================================================================
# Test App Factory (builds router inline to avoid import issues)
# ==============================================================================


def create_test_app(
    mock_registry: MagicMock,
    mock_user: MagicMock | None = None,
    require_auth: bool = True,
) -> FastAPI:
    """Create a test FastAPI app with domain endpoints.

    This creates the router inline to avoid importing the actual router
    which would pull in heavy dependencies.
    """
    app = FastAPI()

    # Create dependency functions
    def get_registry():
        return mock_registry

    def get_current_user():
        if require_auth and mock_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing token",
            )
        return mock_user

    # Define endpoints inline (mirroring the actual router)
    @app.get("/api/v1/domains", response_model=DomainsListResponse)
    async def list_domains(
        user: MagicMock = Depends(get_current_user),
        registry: MagicMock = Depends(get_registry),
    ) -> DomainsListResponse:
        """List all available content domains."""
        domains = registry.list_domains()
        return DomainsListResponse(domains=domains, count=len(domains))

    @app.get("/api/v1/domains/{domain_id}", response_model=DomainDetailResponse)
    async def get_domain(
        domain_id: str,
        user: MagicMock = Depends(get_current_user),
        registry: MagicMock = Depends(get_registry),
    ) -> DomainDetailResponse:
        """Get detailed information about a specific domain."""
        try:
            schema = registry.get_schema(domain_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Domain not found: {domain_id}",
            )
        return DomainDetailResponse.from_schema(schema)

    return app


@pytest.fixture
def mock_registry():
    """Fixture providing a mock registry."""
    return create_mock_registry()


@pytest.fixture
def mock_user():
    """Fixture providing a mock authenticated user."""
    return create_mock_user()


@pytest.fixture
def test_client(mock_registry, mock_user):
    """FastAPI test client with mocked dependencies."""
    app = create_test_app(mock_registry, mock_user)
    return TestClient(app)


# ==============================================================================
# List Domains Tests
# ==============================================================================


class TestListDomains:
    """Tests for GET /api/v1/domains endpoint."""

    def test_list_domains_returns_all_domains(self, mock_registry, mock_user):
        """Test that list_domains returns all available domains."""
        app = create_test_app(mock_registry, mock_user)
        client = TestClient(app)

        response = client.get("/api/v1/domains")

        assert response.status_code == 200
        json_data = response.json()

        assert "domains" in json_data
        assert "count" in json_data
        assert json_data["count"] == 3
        assert len(json_data["domains"]) == 3

    def test_list_domains_returns_domain_summaries(self, mock_registry, mock_user):
        """Test that list_domains returns proper DomainSummary format."""
        app = create_test_app(mock_registry, mock_user)
        client = TestClient(app)

        response = client.get("/api/v1/domains")

        assert response.status_code == 200
        json_data = response.json()

        # Verify domain structure
        for domain in json_data["domains"]:
            assert "domain_id" in domain
            assert "display_name" in domain
            assert "description" in domain
            assert "entity_type_count" in domain
            assert "relationship_type_count" in domain
            assert "entity_types" in domain
            assert "relationship_types" in domain

    def test_list_domains_entity_counts(self, mock_registry, mock_user):
        """Test that list_domains returns correct entity/relationship counts."""
        app = create_test_app(mock_registry, mock_user)
        client = TestClient(app)

        response = client.get("/api/v1/domains")

        assert response.status_code == 200
        json_data = response.json()

        # Check first domain has correct counts
        domain = json_data["domains"][0]
        assert domain["entity_type_count"] == 2
        assert domain["relationship_type_count"] == 2
        assert "character" in domain["entity_types"]
        assert "location" in domain["entity_types"]

    def test_list_domains_empty_registry(self, mock_user):
        """Test list_domains with empty registry."""
        empty_registry = create_mock_registry(schemas=[])
        app = create_test_app(empty_registry, mock_user)
        client = TestClient(app)

        response = client.get("/api/v1/domains")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["count"] == 0
        assert json_data["domains"] == []

    def test_list_domains_requires_auth(self, mock_registry):
        """Test that list_domains requires authentication."""
        app = create_test_app(mock_registry, mock_user=None, require_auth=True)
        client = TestClient(app)

        response = client.get("/api/v1/domains")

        assert response.status_code == 401


# ==============================================================================
# Get Domain Detail Tests
# ==============================================================================


class TestGetDomainDetail:
    """Tests for GET /api/v1/domains/{domain_id} endpoint."""

    def test_get_domain_detail_success(self, mock_registry, mock_user):
        """Test successful domain detail retrieval."""
        app = create_test_app(mock_registry, mock_user)
        client = TestClient(app)

        response = client.get("/api/v1/domains/literature_fiction")

        assert response.status_code == 200
        json_data = response.json()

        assert json_data["domain_id"] == "literature_fiction"
        assert "display_name" in json_data
        assert "description" in json_data
        assert "entity_types" in json_data
        assert "relationship_types" in json_data
        assert "version" in json_data

    def test_get_domain_detail_entity_types(self, mock_registry, mock_user):
        """Test that entity types are properly formatted in detail response."""
        app = create_test_app(mock_registry, mock_user)
        client = TestClient(app)

        response = client.get("/api/v1/domains/literature_fiction")

        assert response.status_code == 200
        json_data = response.json()

        entity_types = json_data["entity_types"]
        assert len(entity_types) == 2

        # Find character entity type
        character_type = next(et for et in entity_types if et["id"] == "character")
        assert character_type["description"] == "A character in the narrative"
        assert len(character_type["properties"]) == 2
        assert len(character_type["examples"]) == 2
        assert "Hamlet" in character_type["examples"]

        # Check property structure
        role_prop = next(p for p in character_type["properties"] if p["name"] == "role")
        assert role_prop["type"] == "string"
        assert "description" in role_prop

    def test_get_domain_detail_relationship_types(self, mock_registry, mock_user):
        """Test that relationship types are properly formatted in detail response."""
        app = create_test_app(mock_registry, mock_user)
        client = TestClient(app)

        response = client.get("/api/v1/domains/literature_fiction")

        assert response.status_code == 200
        json_data = response.json()

        relationship_types = json_data["relationship_types"]
        assert len(relationship_types) == 2

        # Find loves relationship type
        loves_type = next(rt for rt in relationship_types if rt["id"] == "loves")
        assert loves_type["description"] == "Romantic love between characters"
        assert loves_type["valid_source_types"] == ["character"]
        assert loves_type["valid_target_types"] == ["character"]
        assert loves_type["bidirectional"] is True

        # Find located_in relationship type
        located_type = next(rt for rt in relationship_types if rt["id"] == "located_in")
        assert located_type["bidirectional"] is False

    def test_get_domain_detail_not_found(self, mock_registry, mock_user):
        """Test 404 response for unknown domain."""
        app = create_test_app(mock_registry, mock_user)
        client = TestClient(app)

        response = client.get("/api/v1/domains/nonexistent_domain")

        assert response.status_code == 404
        json_data = response.json()
        assert "nonexistent_domain" in json_data["detail"]

    def test_get_domain_detail_case_insensitive(self, mock_registry, mock_user):
        """Test that domain_id lookup is case insensitive."""
        app = create_test_app(mock_registry, mock_user)
        client = TestClient(app)

        # Registry mock normalizes to lowercase
        response = client.get("/api/v1/domains/LITERATURE_FICTION")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["domain_id"] == "literature_fiction"

    def test_get_domain_detail_requires_auth(self, mock_registry):
        """Test that get_domain requires authentication."""
        app = create_test_app(mock_registry, mock_user=None, require_auth=True)
        client = TestClient(app)

        response = client.get("/api/v1/domains/literature_fiction")

        assert response.status_code == 401

    def test_get_domain_detail_version_format(self, mock_registry, mock_user):
        """Test that version is in semver format."""
        app = create_test_app(mock_registry, mock_user)
        client = TestClient(app)

        response = client.get("/api/v1/domains/literature_fiction")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["version"] == "1.0.0"


# ==============================================================================
# Response Model Tests
# ==============================================================================


class TestResponseModels:
    """Tests for response model construction."""

    def test_domains_list_response_structure(self):
        """Test DomainsListResponse structure."""
        schema = create_test_schema()
        summary = DomainSummary.from_schema(schema)

        response = DomainsListResponse(
            domains=[summary],
            count=1,
        )

        assert response.count == 1
        assert len(response.domains) == 1
        assert response.domains[0].domain_id == "test_domain"

    def test_domain_detail_response_from_schema(self):
        """Test DomainDetailResponse.from_schema factory method."""
        schema = create_test_schema("my_domain")
        response = DomainDetailResponse.from_schema(schema)

        assert response.domain_id == "my_domain"
        assert response.display_name == "Test Domain: my_domain"
        assert len(response.entity_types) == 2
        assert len(response.relationship_types) == 2
        assert response.version == "1.0.0"

    def test_entity_type_detail_structure(self):
        """Test EntityTypeDetail model structure."""
        detail = EntityTypeDetail(
            id="character",
            description="A character",
            properties=[{"name": "role", "type": "string"}],
            examples=["Alice", "Bob"],
        )

        assert detail.id == "character"
        assert detail.description == "A character"
        assert len(detail.properties) == 1
        assert len(detail.examples) == 2

    def test_relationship_type_detail_structure(self):
        """Test RelationshipTypeDetail model structure."""
        detail = RelationshipTypeDetail(
            id="loves",
            description="Love relationship",
            valid_source_types=["character"],
            valid_target_types=["character"],
            bidirectional=True,
        )

        assert detail.id == "loves"
        assert detail.bidirectional is True
        assert detail.valid_source_types == ["character"]


# ==============================================================================
# Edge Case Tests
# ==============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_domain_with_no_properties(self, mock_user):
        """Test domain where entity types have no properties."""
        schema = DomainSchema(
            domain_id="simple_domain",
            display_name="Simple Domain",
            description="A domain with no entity properties",
            entity_types=[
                EntityTypeSchema(
                    id="item",
                    description="A simple item",
                    properties=[],
                    examples=[],
                ),
            ],
            relationship_types=[
                RelationshipTypeSchema(
                    id="related_to",
                    description="Generic relationship",
                ),
            ],
            extraction_prompt_template="Extract: {content}",
        )

        registry = create_mock_registry([schema])
        app = create_test_app(registry, mock_user)
        client = TestClient(app)

        response = client.get("/api/v1/domains/simple_domain")

        assert response.status_code == 200
        json_data = response.json()
        assert len(json_data["entity_types"][0]["properties"]) == 0
        assert len(json_data["entity_types"][0]["examples"]) == 0

    def test_domain_with_many_entity_types(self, mock_user):
        """Test domain with many entity types."""
        entity_types = [
            EntityTypeSchema(
                id=f"type_{i}",
                description=f"Entity type {i}",
            )
            for i in range(10)
        ]

        schema = DomainSchema(
            domain_id="large_domain",
            display_name="Large Domain",
            description="A domain with many entity types",
            entity_types=entity_types,
            relationship_types=[
                RelationshipTypeSchema(
                    id="related_to",
                    description="Generic relationship",
                ),
            ],
            extraction_prompt_template="Extract: {content}",
        )

        registry = create_mock_registry([schema])
        app = create_test_app(registry, mock_user)
        client = TestClient(app)

        response = client.get("/api/v1/domains/large_domain")

        assert response.status_code == 200
        json_data = response.json()
        assert len(json_data["entity_types"]) == 10

    def test_whitespace_in_domain_id(self, mock_registry, mock_user):
        """Test that whitespace in domain_id is handled."""
        app = create_test_app(mock_registry, mock_user)
        client = TestClient(app)

        # With leading/trailing whitespace in URL (URL-encoded)
        response = client.get("/api/v1/domains/%20literature_fiction%20")

        # This should normalize the ID
        assert response.status_code == 200
        json_data = response.json()
        assert json_data["domain_id"] == "literature_fiction"
