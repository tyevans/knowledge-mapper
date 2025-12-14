"""
Pytest configuration and fixtures for E2E tests.

Provides combined fixtures for:
- Database session with tenant context
- Neo4j service connection
- Ollama availability checking
- Sample page content
- Cleanup utilities

All fixtures are designed to skip gracefully if external services
are unavailable, allowing tests to run in environments without
full infrastructure.
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Configure environment variables for tests
# Tests may run inside Docker containers, use internal service names
if "NEO4J_URI" not in os.environ:
    os.environ["NEO4J_URI"] = "bolt://neo4j:7687"
if "NEO4J_USER" not in os.environ:
    os.environ["NEO4J_USER"] = "neo4j"
if "NEO4J_PASSWORD" not in os.environ:
    os.environ["NEO4J_PASSWORD"] = "knowledge_mapper_neo4j_pass"
if "NEO4J_DATABASE" not in os.environ:
    os.environ["NEO4J_DATABASE"] = "neo4j"


def pytest_configure(config):
    """Register custom markers for E2E tests."""
    config.addinivalue_line(
        "markers",
        "e2e: marks tests as end-to-end tests (require database/services)",
    )
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow running",
    )


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for async tests."""
    return "asyncio"


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Database Fixtures
# =============================================================================


async def _check_database_available() -> bool:
    """Check if PostgreSQL is available and connectable.

    Returns:
        True if database is available, False otherwise.
    """
    try:
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
async def db_available() -> bool:
    """Check if PostgreSQL is available for the test module.

    Returns:
        True if database is available, False otherwise.
    """
    return await _check_database_available()


@pytest.fixture
async def db_session(db_available: bool) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session with tenant context for tests.

    This fixture:
    1. Checks if database is available (skips test if not)
    2. Creates a new async session
    3. Yields the session for test use
    4. Rolls back and closes the session after the test

    Args:
        db_available: Module-scoped fixture indicating database availability.

    Yields:
        AsyncSession: Database session for test use.

    Raises:
        pytest.skip: If database is not available.
    """
    if not db_available:
        pytest.skip("PostgreSQL is not available")

    from app.core.database import AsyncSessionLocal

    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


@pytest.fixture
async def db_session_with_tenant(
    db_session: AsyncSession,
    test_tenant_id: UUID,
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session with RLS tenant context set.

    Sets the PostgreSQL session variable for RLS enforcement.

    Args:
        db_session: Base database session.
        test_tenant_id: Tenant ID for RLS context.

    Yields:
        AsyncSession with tenant context set.
    """
    # Set PostgreSQL session variable for RLS
    await db_session.execute(
        text("SET app.current_tenant_id = :tenant_id"),
        {"tenant_id": str(test_tenant_id)},
    )
    yield db_session


# =============================================================================
# Neo4j Fixtures
# =============================================================================


async def _check_neo4j_available() -> bool:
    """Check if Neo4j is available and connectable.

    Returns:
        True if Neo4j is available, False otherwise.
    """
    try:
        from app.services.neo4j import Neo4jService

        service = Neo4jService()
        await service.connect()
        health = await service.health_check()
        await service.close()
        return health.get("status") == "healthy"
    except Exception:
        return False


@pytest.fixture(scope="module")
async def neo4j_available() -> bool:
    """Check if Neo4j is available for the test module.

    This fixture is evaluated once per module and can be used
    to skip tests when Neo4j is not available.

    Returns:
        True if Neo4j is available, False otherwise.
    """
    return await _check_neo4j_available()


@pytest.fixture
async def neo4j_service(neo4j_available: bool):
    """Provide a connected Neo4j service instance for tests.

    This fixture:
    1. Checks if Neo4j is available (skips test if not)
    2. Creates and connects a new Neo4jService instance
    3. Yields the service for test use
    4. Closes the connection after the test

    Args:
        neo4j_available: Module-scoped fixture indicating Neo4j availability.

    Yields:
        Connected Neo4jService instance.

    Raises:
        pytest.skip: If Neo4j is not available.
    """
    if not neo4j_available:
        pytest.skip("Neo4j is not available")

    from app.services.neo4j import Neo4jService

    service = Neo4jService()
    await service.connect()

    yield service

    await service.close()


# =============================================================================
# Ollama Fixtures
# =============================================================================


async def _check_ollama_available() -> bool:
    """Check if Ollama is available and has the configured model.

    Returns:
        True if Ollama is available with the model, False otherwise.
    """
    try:
        from app.core.config import settings

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


@pytest.fixture(scope="module")
async def ollama_available() -> bool:
    """Check if Ollama is available for the test module.

    Returns:
        True if Ollama is available with the configured model, False otherwise.
    """
    return await _check_ollama_available()


@pytest.fixture
def ollama_service(ollama_available: bool):
    """Provide an Ollama extraction service instance.

    Args:
        ollama_available: Module-scoped fixture indicating Ollama availability.

    Yields:
        OllamaExtractionService instance.

    Raises:
        pytest.skip: If Ollama is not available.
    """
    if not ollama_available:
        pytest.skip("Ollama is not available")

    from app.extraction.ollama_extractor import get_ollama_extraction_service

    return get_ollama_extraction_service()


# =============================================================================
# Tenant and ID Fixtures
# =============================================================================


@pytest.fixture
def test_tenant_id() -> UUID:
    """Generate a unique tenant ID for test isolation.

    Each test gets a unique tenant ID to ensure complete
    isolation from other tests running in parallel.

    Returns:
        A new UUID for the test tenant.
    """
    return uuid4()


@pytest.fixture
def test_tenant_id_a() -> UUID:
    """Generate first unique tenant ID for multi-tenant tests.

    Returns:
        A new UUID for tenant A.
    """
    return uuid4()


@pytest.fixture
def test_tenant_id_b() -> UUID:
    """Generate second unique tenant ID for multi-tenant tests.

    Returns:
        A new UUID for tenant B.
    """
    return uuid4()


@pytest.fixture
def test_page_id() -> UUID:
    """Generate a unique page ID for test use.

    Returns:
        A new UUID for the test page.
    """
    return uuid4()


@pytest.fixture
def test_job_id() -> UUID:
    """Generate a unique job ID for test use.

    Returns:
        A new UUID for the test job.
    """
    return uuid4()


@pytest.fixture
def test_process_id() -> UUID:
    """Generate a unique process ID for test use.

    Returns:
        A new UUID for the extraction process.
    """
    return uuid4()


# =============================================================================
# Sample Content Fixtures
# =============================================================================


@pytest.fixture
def sample_page_content() -> str:
    """Provide sample page content for extraction testing.

    Contains Python class and function definitions that should
    be extracted as entities with relationships.

    Returns:
        Sample documentation content string.
    """
    return '''
## DomainEvent

Base class for all domain events in the system.

```python
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class DomainEvent(BaseModel):
    """Base event class for event sourcing.

    All domain events should inherit from this class to ensure
    consistent serialization and event metadata.
    """

    event_type: str
    aggregate_id: UUID
    aggregate_version: int
    occurred_at: datetime

    def to_dict(self) -> dict:
        """Convert event to dictionary for serialization."""
        return self.model_dump()
```

### Inheritance

All domain events should inherit from `DomainEvent`:

```python
from eventsource import register_event

@register_event
class UserCreated(DomainEvent):
    """Emitted when a new user is created."""

    event_type: str = "UserCreated"
    user_id: UUID
    email: str
    name: str
```

The `@register_event` decorator registers the event with the event registry
for automatic serialization and deserialization.

### Event Store

Events are stored in the EventStore which provides append and read operations:

```python
class EventStore:
    """Stores and retrieves domain events."""

    async def append(self, event: DomainEvent) -> None:
        """Append an event to the store."""
        pass

    async def get_events(self, aggregate_id: UUID) -> list[DomainEvent]:
        """Get all events for an aggregate."""
        pass
```
'''


@pytest.fixture
def sample_api_doc() -> str:
    """Sample API documentation content for testing extraction.

    Contains class definitions, inheritance, methods, and decorators
    that should be extracted as entities and relationships.

    Returns:
        API documentation string with DomainEvent and UserCreated classes.
    """
    return '''
## DomainEvent

Base class for all domain events in the system.

```python
from pydantic import BaseModel

class DomainEvent(BaseModel):
    """Base event class."""

    event_type: str
    aggregate_id: UUID
    aggregate_version: int
    occurred_at: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return self.model_dump()
```

### Inheritance

All domain events should inherit from `DomainEvent`:

```python
@register_event
class UserCreated(DomainEvent):
    event_type: str = "UserCreated"
    user_id: UUID
    email: str
```

The `@register_event` decorator registers the event with the event registry.
'''


@pytest.fixture
def sample_tutorial_doc() -> str:
    """Sample tutorial documentation content for testing extraction.

    Contains concepts, step-by-step patterns, and best practices
    that should be extracted as conceptual entities.

    Returns:
        Tutorial documentation string about event sourcing.
    """
    return '''
# Getting Started with Event Sourcing

Event sourcing is a pattern where application state changes are stored
as a sequence of events rather than mutating a current state.

## Core Concepts

### Events
Events represent facts that have happened in the system. They are immutable
and contain all information needed to reconstruct state.

### Aggregates
An aggregate is a cluster of domain objects that can be treated as a single
unit for data changes. Each aggregate has a root entity.

### Event Store
The event store is responsible for persisting and retrieving events.
It acts as the source of truth for the application.

## Basic Example

Here's how to create your first event:

```python
from eventsource import DomainEvent

class OrderCreated(DomainEvent):
    order_id: UUID
    customer_id: UUID
    total_amount: Decimal
```

## Best Practices

1. Events should be past-tense named (e.g., `OrderCreated` not `CreateOrder`)
2. Events should be immutable once created
3. Events should contain all data needed to apply the change

## Related Concepts

Event sourcing is often used together with:
- CQRS (Command Query Responsibility Segregation)
- Domain-Driven Design (DDD)
- Message Queuing
'''


# =============================================================================
# Cleanup Fixtures
# =============================================================================


@pytest.fixture
async def cleanup_tenant_data(neo4j_service) -> AsyncGenerator[list[UUID], None]:
    """Fixture to track and cleanup test tenant data in Neo4j.

    Usage:
        async def test_something(cleanup_tenant_data, neo4j_service):
            tenant_id = uuid4()
            cleanup_tenant_data.append(tenant_id)
            # ... create test data for tenant_id ...
            # Data will be automatically cleaned up after test

    Yields:
        List to collect tenant IDs that need cleanup.
    """
    tenant_ids: list[UUID] = []

    yield tenant_ids

    # Cleanup all tenant data after the test
    for tenant_id in tenant_ids:
        try:
            await neo4j_service.delete_tenant_data(tenant_id)
        except Exception:
            # Ignore cleanup errors
            pass


@pytest.fixture
async def cleanup_single_tenant(
    neo4j_service,
    test_tenant_id: UUID,
) -> AsyncGenerator[UUID, None]:
    """Fixture providing a single test tenant ID with automatic Neo4j cleanup.

    This is a convenience fixture for tests that only need one tenant.
    The tenant data is automatically deleted from Neo4j after the test completes.

    Yields:
        The test tenant ID.
    """
    yield test_tenant_id

    try:
        await neo4j_service.delete_tenant_data(test_tenant_id)
    except Exception:
        # Ignore cleanup errors
        pass


@pytest.fixture
async def two_tenants_cleanup(
    neo4j_service,
    test_tenant_id_a: UUID,
    test_tenant_id_b: UUID,
) -> AsyncGenerator[tuple[UUID, UUID], None]:
    """Fixture providing two test tenant IDs with automatic Neo4j cleanup.

    Useful for tenant isolation tests that need two separate tenants.
    Both tenants' data is automatically deleted after the test.

    Yields:
        Tuple of (tenant_a_id, tenant_b_id).
    """
    yield (test_tenant_id_a, test_tenant_id_b)

    for tenant_id in [test_tenant_id_a, test_tenant_id_b]:
        try:
            await neo4j_service.delete_tenant_data(tenant_id)
        except Exception:
            # Ignore cleanup errors
            pass


# =============================================================================
# Event Sourcing Fixtures
# =============================================================================


@pytest.fixture
async def event_store(db_available: bool):
    """Provide an event store instance for tests.

    Args:
        db_available: Module-scoped fixture indicating database availability.

    Yields:
        Event store instance.

    Raises:
        pytest.skip: If database is not available.
    """
    if not db_available:
        pytest.skip("PostgreSQL is not available")

    from app.eventsourcing.stores.factory import get_event_store

    return await get_event_store()


# =============================================================================
# Sample Entity Properties
# =============================================================================


@pytest.fixture
def sample_entity_properties() -> dict:
    """Provide sample entity properties for testing.

    Returns:
        Dict with typical entity properties.
    """
    return {
        "docstring": "A sample entity for testing.",
        "signature": "def sample_function(arg1, arg2):",
        "methods": ["method1", "method2"],
        "attributes": {"attr1": "value1"},
    }


@pytest.fixture
def sample_relationship_properties() -> dict:
    """Provide sample relationship properties for testing.

    Returns:
        Dict with typical relationship properties.
    """
    return {
        "context": "The source entity uses the target entity for processing.",
        "line_number": 42,
    }
