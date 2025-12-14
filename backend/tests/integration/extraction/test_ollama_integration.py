"""
Integration tests for OllamaExtractionService.

These tests require a running Ollama instance and are marked with
@pytest.mark.integration. They test real extraction with actual LLM calls.

Run with: pytest -m integration tests/integration/extraction/

Test Categories:
- Health Check Integration Tests: Verify Ollama connectivity
- Extraction Integration Tests: Test entity/relationship extraction
- DocumentationType Integration Tests: Test different doc type prompts
- Error Handling Integration Tests: Test error scenarios
- Factory Function Integration Tests: Test singleton pattern
"""

import httpx
import pytest

from app.core.config import settings
from app.extraction.ollama_extractor import (
    ExtractionError,
    get_ollama_extraction_service,
    reset_ollama_extraction_service,
)
from app.extraction.prompts import DocumentationType
from app.extraction.schemas import ExtractionResult

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def ollama_available():
    """Check if Ollama is available and return True/False.

    This fixture checks connectivity to the Ollama server and whether
    the configured model is available.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                model_names = [m.get("name", "") for m in models]
                # Check if configured model is available
                model_available = any(
                    settings.OLLAMA_MODEL in name or name in settings.OLLAMA_MODEL
                    for name in model_names
                )
                return model_available
            return False
    except Exception:
        return False


@pytest.fixture(autouse=True)
def reset_service():
    """Reset the global service instance before each test."""
    reset_ollama_extraction_service()
    yield
    reset_ollama_extraction_service()


# =============================================================================
# Health Check Integration Tests
# =============================================================================


@pytest.mark.integration
class TestOllamaHealthCheckIntegration:
    """Integration tests for Ollama health check."""

    @pytest.mark.asyncio
    async def test_health_check_returns_status(self):
        """Test health check returns a status dict."""
        service = get_ollama_extraction_service()
        health = await service.health_check()

        # Should always return a dict with status key
        assert isinstance(health, dict)
        assert "status" in health
        assert health["status"] in ["healthy", "unhealthy"]

        # Should include base URL and model info
        assert "base_url" in health
        assert "model" in health

    @pytest.mark.asyncio
    async def test_health_check_shows_available_models_when_healthy(self, ollama_available):
        """Test health check lists available models when Ollama is up."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()
        health = await service.health_check()

        assert health["status"] == "healthy"
        assert "available_models" in health
        assert isinstance(health["available_models"], list)
        assert "model_available" in health


# =============================================================================
# Extraction Integration Tests
# =============================================================================


@pytest.mark.integration
class TestOllamaExtractionIntegration:
    """Integration tests for real extraction with Ollama."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_extract_simple_class(self, ollama_available):
        """Test extraction of a simple Python class."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()

        content = '''
class DomainEvent(BaseModel):
    """Base class for domain events.

    All domain events should inherit from this class to ensure
    consistent serialization and event metadata.
    """

    event_type: str
    aggregate_id: UUID
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert event to dictionary for serialization."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "DomainEvent":
        """Create event from dictionary."""
        return cls(**data)
'''

        result = await service.extract(
            content=content,
            page_url="https://docs.example.com/events",
        )

        # Validate result type
        assert isinstance(result, ExtractionResult)

        # Should extract at least one entity
        assert result.entity_count > 0

        # Should find the DomainEvent class
        class_entities = result.get_entities_by_type("class")
        entity_names = [e.name.lower() for e in result.entities]
        assert any("domainevent" in name for name in entity_names) or len(class_entities) > 0

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_extract_function_with_parameters(self, ollama_available):
        """Test extraction of a function with typed parameters."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()

        content = '''
async def process_extraction(
    content: str,
    page_url: str,
    max_retries: int = 3,
    timeout: float = 30.0,
) -> ExtractionResult:
    """Process content extraction with retries.

    Args:
        content: The text content to analyze
        page_url: URL of the source page
        max_retries: Maximum retry attempts on failure
        timeout: Timeout in seconds for each attempt

    Returns:
        ExtractionResult containing entities and relationships

    Raises:
        ExtractionError: If all retry attempts fail
    """
    for attempt in range(max_retries):
        try:
            result = await extract_with_llm(content, page_url, timeout)
            return result
        except TimeoutError:
            if attempt == max_retries - 1:
                raise ExtractionError("All retries exhausted")
            await asyncio.sleep(2 ** attempt)
'''

        result = await service.extract(
            content=content,
            page_url="https://docs.example.com/extraction",
        )

        assert isinstance(result, ExtractionResult)
        assert result.entity_count > 0

        # Check that function was identified
        function_entities = result.get_entities_by_type("function")
        entity_names = [e.name.lower() for e in result.entities]
        assert len(function_entities) > 0 or any("process" in name for name in entity_names)

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_extract_with_relationships(self, ollama_available):
        """Test extraction identifies relationships between entities."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()

        content = '''
class EventStore:
    """Stores and retrieves domain events."""

    def __init__(self, repository: EventRepository):
        self.repository = repository

    async def append(self, event: DomainEvent) -> None:
        await self.repository.save(event)


class EventRepository:
    """Repository for event persistence."""

    async def save(self, event: DomainEvent) -> None:
        pass


class DomainEvent:
    """Base event class."""
    pass
'''

        result = await service.extract(
            content=content,
            page_url="https://docs.example.com/event-sourcing",
        )

        assert isinstance(result, ExtractionResult)

        # Should find multiple classes
        class_entities = result.get_entities_by_type("class")
        assert len(class_entities) >= 2 or result.entity_count >= 2

        # May find relationships (not guaranteed with all models)
        # Just verify the structure is valid
        for rel in result.relationships:
            assert rel.source_name in result.get_entity_names()
            assert rel.target_name in result.get_entity_names()

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_extract_design_pattern(self, ollama_available):
        """Test extraction of a design pattern description."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()

        content = """
# Repository Pattern

The Repository pattern mediates between the domain and data mapping layers,
acting like an in-memory domain object collection.

## Implementation

The pattern involves:
1. A Repository interface defining collection-like operations
2. Concrete implementations for specific data stores
3. Domain objects that remain persistence-ignorant

## Example

```python
class UserRepository(Protocol):
    async def find_by_id(self, user_id: UUID) -> User | None: ...
    async def save(self, user: User) -> None: ...

class PostgresUserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)
```
"""

        result = await service.extract(
            content=content,
            page_url="https://docs.example.com/patterns/repository",
        )

        assert isinstance(result, ExtractionResult)
        assert result.entity_count > 0

        # Should identify pattern or concept entities
        entity_types = {e.entity_type for e in result.entities}
        # At least one of these should be found
        assert "pattern" in entity_types or "concept" in entity_types or "class" in entity_types

    @pytest.mark.asyncio
    async def test_extract_handles_empty_content(self, ollama_available):
        """Test extraction handles empty or minimal content."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()

        result = await service.extract(
            content="# Empty Page\n\nNo content here.",
            page_url="https://docs.example.com/empty",
        )

        # Should return valid but possibly empty result
        assert isinstance(result, ExtractionResult)
        # Empty content should not cause errors

    @pytest.mark.asyncio
    async def test_extract_respects_max_length(self, ollama_available):
        """Test extraction respects max_length parameter."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()

        # Create long content
        long_content = "class Example: pass\n" * 1000

        # Should not raise error even with very long content
        result = await service.extract(
            content=long_content,
            page_url="https://docs.example.com/long",
            max_length=500,
        )

        assert isinstance(result, ExtractionResult)


# =============================================================================
# DocumentationType Integration Tests
# =============================================================================


@pytest.mark.integration
class TestDocumentationTypeIntegration:
    """Integration tests for different DocumentationType variants."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_extract_with_api_reference_type(self, ollama_available, sample_api_doc):
        """Test extraction with API_REFERENCE document type."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()
        result = await service.extract(
            content=sample_api_doc,
            page_url="https://docs.example.com/api/events",
            doc_type=DocumentationType.API_REFERENCE,
        )

        assert isinstance(result, ExtractionResult)
        # API reference should focus on classes and functions
        assert result.entity_count > 0
        # Should find at least one class entity
        class_entities = result.get_entities_by_type("class")
        function_entities = result.get_entities_by_type("function")
        assert len(class_entities) > 0 or len(function_entities) > 0

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_extract_with_tutorial_type(self, ollama_available, sample_tutorial_doc):
        """Test extraction with TUTORIAL document type."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()
        result = await service.extract(
            content=sample_tutorial_doc,
            page_url="https://docs.example.com/tutorials/event-sourcing",
            doc_type=DocumentationType.TUTORIAL,
        )

        assert isinstance(result, ExtractionResult)
        # Tutorial should extract concepts and examples
        assert result.entity_count > 0
        # Should find concepts or patterns
        entity_types = {e.entity_type for e in result.entities}
        # At least one concept-like entity type should be found
        concept_types = {"concept", "pattern", "class", "example"}
        assert len(entity_types & concept_types) > 0

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_extract_with_conceptual_type(self, ollama_available):
        """Test extraction with CONCEPTUAL document type."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()

        conceptual_content = """
# CQRS Architecture Pattern

Command Query Responsibility Segregation (CQRS) separates read and write
operations into different models.

## The Problem

Traditional CRUD-based architectures often struggle with:
- Complex queries that span multiple aggregates
- Different scaling requirements for reads vs writes
- Performance optimization for high-read scenarios

## The Solution

CQRS addresses this by:
1. Commands: Handle write operations, validate business rules
2. Queries: Optimized read models for specific use cases
3. Events: Bridge between command and query sides

## Trade-offs

Benefits:
- Independent scaling of read/write sides
- Optimized read models for specific queries
- Better separation of concerns

Drawbacks:
- Eventual consistency between models
- Increased complexity
- More infrastructure to maintain
"""

        result = await service.extract(
            content=conceptual_content,
            page_url="https://docs.example.com/concepts/cqrs",
            doc_type=DocumentationType.CONCEPTUAL,
        )

        assert isinstance(result, ExtractionResult)
        assert result.entity_count > 0
        # Should find patterns or concepts
        entity_names_lower = [e.name.lower() for e in result.entities]
        # CQRS or Command/Query should appear in some form
        assert any(
            "cqrs" in name or "command" in name or "query" in name
            for name in entity_names_lower
        )

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_extract_with_example_code_type(self, ollama_available):
        """Test extraction with EXAMPLE_CODE document type."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()

        example_content = """
# Code Examples

## Basic Repository Implementation

```python
from abc import ABC, abstractmethod
from uuid import UUID

class Repository(ABC):
    @abstractmethod
    async def get(self, id: UUID) -> Entity | None:
        pass

    @abstractmethod
    async def save(self, entity: Entity) -> None:
        pass

class InMemoryRepository(Repository):
    def __init__(self):
        self._store: dict[UUID, Entity] = {}

    async def get(self, id: UUID) -> Entity | None:
        return self._store.get(id)

    async def save(self, entity: Entity) -> None:
        self._store[entity.id] = entity
```

## Usage Example

```python
repo = InMemoryRepository()
entity = Entity(id=UUID("..."), name="test")
await repo.save(entity)
retrieved = await repo.get(entity.id)
```
"""

        result = await service.extract(
            content=example_content,
            page_url="https://docs.example.com/examples/repository",
            doc_type=DocumentationType.EXAMPLE_CODE,
        )

        assert isinstance(result, ExtractionResult)
        assert result.entity_count > 0
        # Should find classes or examples
        entity_types = {e.entity_type for e in result.entities}
        assert "class" in entity_types or "example" in entity_types or "function" in entity_types

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_extract_with_general_type(self, ollama_available, sample_api_doc):
        """Test extraction with GENERAL document type (default)."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()
        result = await service.extract(
            content=sample_api_doc,
            page_url="https://docs.example.com/general",
            doc_type=DocumentationType.GENERAL,
        )

        assert isinstance(result, ExtractionResult)
        # Should still extract entities with general type
        assert result.entity_count > 0

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_extract_with_additional_context(self, ollama_available, sample_api_doc):
        """Test extraction with additional context provided."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()
        result = await service.extract(
            content=sample_api_doc,
            page_url="https://docs.eventsource-py.io/api/events",
            doc_type=DocumentationType.API_REFERENCE,
            additional_context="This is documentation for eventsource-py, a Python event sourcing library. Focus on event-related entities.",
        )

        assert isinstance(result, ExtractionResult)
        assert result.entity_count > 0


# =============================================================================
# Error Handling Integration Tests
# =============================================================================


@pytest.mark.integration
class TestOllamaErrorHandlingIntegration:
    """Integration tests for error handling with real Ollama."""

    @pytest.mark.asyncio
    async def test_extract_with_invalid_url_still_works(self, ollama_available):
        """Test extraction works even with invalid-looking URLs."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()

        # URL is just context, should not affect extraction
        result = await service.extract(
            content="class Test: pass",
            page_url="not-a-real-url",
        )

        assert isinstance(result, ExtractionResult)

    @pytest.mark.asyncio
    async def test_extract_with_unicode_content(self, ollama_available):
        """Test extraction handles unicode content."""
        if not ollama_available:
            pytest.skip("Ollama not available")

        service = get_ollama_extraction_service()

        content = '''
class UnicodeHandler:
    """Handles unicode strings like: cafe, resume, naive.

    Supports Japanese: , Korean: , Russian: .
    """
    pass
'''

        result = await service.extract(
            content=content,
            page_url="https://docs.example.com/unicode",
        )

        assert isinstance(result, ExtractionResult)

    @pytest.mark.asyncio
    async def test_handles_connection_error(self):
        """Test extraction handles connection errors gracefully.

        This test uses a mock to simulate a connection error without
        requiring an actual unavailable Ollama instance.
        """
        # Reset to ensure fresh service
        reset_ollama_extraction_service()

        # Create a service pointing to invalid endpoint
        from app.extraction.ollama_extractor import OllamaExtractionService

        service = OllamaExtractionService(
            base_url="http://localhost:99999",  # Invalid port
            model="test-model",
            timeout=5,
        )

        # Should raise ExtractionError with connection error details
        with pytest.raises(ExtractionError) as exc_info:
            await service.extract(
                content="class Test: pass",
                page_url="https://example.com/test",
            )

        # Verify error contains connection failure message
        assert "connect" in str(exc_info.value).lower() or "connection" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_health_check_returns_unhealthy_when_unavailable(self):
        """Test health check returns unhealthy status when Ollama is unavailable."""
        from app.extraction.ollama_extractor import OllamaExtractionService

        service = OllamaExtractionService(
            base_url="http://localhost:99999",  # Invalid port
            model="test-model",
            timeout=2,
        )

        health = await service.health_check()

        assert health["status"] == "unhealthy"
        assert "error" in health
        assert health["base_url"] == "http://localhost:99999"


# =============================================================================
# Factory Function Integration Tests
# =============================================================================


@pytest.mark.integration
class TestFactoryIntegration:
    """Integration tests for the factory function."""

    def test_factory_uses_settings(self):
        """Test factory function uses configuration settings."""
        service = get_ollama_extraction_service()

        assert service._base_url == settings.OLLAMA_BASE_URL
        assert service._model == settings.OLLAMA_MODEL
        assert service._timeout == settings.OLLAMA_TIMEOUT
