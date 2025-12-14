"""
Pytest configuration and fixtures for eventsourcing integration tests.

Provides fixtures for:
- Database session management
- Event store access
- Test data cleanup
"""

import pytest


# Register markers for integration tests
def pytest_configure(config):
    """Register custom markers for eventsourcing integration tests."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require database/services)"
    )


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for async tests."""
    return "asyncio"
