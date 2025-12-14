"""
Pytest configuration and fixtures for Neo4j integration tests.

Provides fixtures for:
- Neo4j service connection and availability checking
- Test data cleanup after each test
- Tenant isolation testing utilities
"""

import os
from typing import AsyncGenerator
from uuid import UUID, uuid4

import pytest

# Configure Neo4j settings for integration tests
# Tests run inside Docker containers, use internal service names
if "NEO4J_URI" not in os.environ:
    os.environ["NEO4J_URI"] = "bolt://neo4j:7687"
if "NEO4J_USER" not in os.environ:
    os.environ["NEO4J_USER"] = "neo4j"
if "NEO4J_PASSWORD" not in os.environ:
    os.environ["NEO4J_PASSWORD"] = "knowledge_mapper_neo4j_pass"
if "NEO4J_DATABASE" not in os.environ:
    os.environ["NEO4J_DATABASE"] = "neo4j"


def pytest_configure(config):
    """Register custom markers for Neo4j integration tests."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require Neo4j service)",
    )


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for async tests."""
    return "asyncio"


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
async def cleanup_tenant_data(neo4j_service) -> AsyncGenerator[list[UUID], None]:
    """Fixture to track and cleanup test tenant data.

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
    """Fixture providing a single test tenant ID with automatic cleanup.

    This is a convenience fixture for tests that only need one tenant.
    The tenant data is automatically deleted after the test completes.

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
    """Fixture providing two test tenant IDs with automatic cleanup.

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
