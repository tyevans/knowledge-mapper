"""
Pytest configuration and fixtures for integration tests.

Provides fixtures for:
- Keycloak token acquisition
- FastAPI test client for integration tests
- Redis client for integration tests
- Real service interactions
"""

import os
import asyncio
import httpx
import pytest
import redis.asyncio as redis
from httpx import AsyncClient
from typing import Dict, Any

# Configure settings for integration tests (only if not already set by .env.test)
# Tests/conftest.py loads .env.test which takes precedence
# These tests run INSIDE Docker containers, so use internal container ports and service names
if "DATABASE_URL" not in os.environ:
    # Use knowledge_mapper_migration_user for tests since tests need full permissions
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://knowledge_mapper_migration_user:migration_password_dev@postgres:5432/knowledge_mapper_db"
if "OAUTH_ISSUER_URL" not in os.environ:
    os.environ["OAUTH_ISSUER_URL"] = "http://keycloak:8080/realms/knowledge-mapper-dev"
if "REDIS_URL" not in os.environ:
    os.environ["REDIS_URL"] = "redis://default:knowledge_mapper_redis_pass@redis:6379/0"
if "OAUTH_AUDIENCE" not in os.environ:
    # Keycloak default client uses 'account' as audience, not 'knowledge-mapper-backend'
    os.environ["OAUTH_AUDIENCE"] = "account"

from app.core.config import settings
from app.main import app


# Keycloak configuration
# Use keycloak service name for internal Docker network communication
KEYCLOAK_BASE_URL = "http://keycloak:8080"
KEYCLOAK_REALM = "knowledge-mapper-dev"
KEYCLOAK_CLIENT_ID = "knowledge-mapper-backend"
KEYCLOAK_CLIENT_SECRET = "knowledge-mapper-backend-secret"
KEYCLOAK_TOKEN_URL = f"{KEYCLOAK_BASE_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"


# Test users (from TASK-007)
TEST_USERS = {
    "acme_alice": {
        "username": "alice@acme-corp.example",
        "password": "password123",
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "user_id": "cbd0900c-44b3-4e75-b093-0b6c2282183f",
    },
    "acme_bob": {
        "username": "bob@acme-corp.example",
        "password": "password123",
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "user_id": "59be274d-c55a-4945-a420-8c49ced43d86",
    },
    "globex_charlie": {
        "username": "charlie@globex-inc.example",
        "password": "password123",
        "tenant_id": "22222222-2222-2222-2222-222222222222",
        "user_id": "50b5edc2-6740-47f3-9d0f-eafbb7c1652a",
    },
    "globex_diana": {
        "username": "diana@globex-inc.example",
        "password": "password123",
        "tenant_id": "22222222-2222-2222-2222-222222222222",
        "user_id": "7c53def1-64b4-4190-964d-a0e0ac258f85",
    },
}


async def get_keycloak_token(
    username: str,
    password: str,
    client_id: str = KEYCLOAK_CLIENT_ID,
    client_secret: str = KEYCLOAK_CLIENT_SECRET,
) -> Dict[str, Any]:
    """
    Fetch real access token from Keycloak using password grant.

    Args:
        username: User's email address
        password: User's password
        client_id: OAuth client ID (default: knowledge-mapper-backend)
        client_secret: OAuth client secret

    Returns:
        Token response dictionary with:
        - access_token: JWT access token
        - expires_in: Token lifetime in seconds
        - refresh_token: Refresh token
        - token_type: "Bearer"

    Raises:
        httpx.HTTPStatusError: If token request fails
    """
    data = {
        "grant_type": "password",
        "client_id": client_id,
        "client_secret": client_secret,
        "username": username,
        "password": password,
        "scope": "openid profile email",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(KEYCLOAK_TOKEN_URL, data=data)
        response.raise_for_status()
        return response.json()


@pytest.fixture
async def get_keycloak_token_helper():
    """
    Fixture providing helper function to get Keycloak tokens.

    Usage:
        async def test_something(get_keycloak_token_helper):
            token_data = await get_keycloak_token_helper("alice@acme-corp.example", "password123")
            access_token = token_data["access_token"]
    """
    return get_keycloak_token


@pytest.fixture
async def keycloak_token_acme_alice():
    """
    Fixture providing access token for alice@acme-corp.example.

    Returns:
        str: JWT access token for Alice (ACME Corp tenant)
    """
    token_data = await get_keycloak_token(
        username=TEST_USERS["acme_alice"]["username"],
        password=TEST_USERS["acme_alice"]["password"],
    )
    return token_data["access_token"]


@pytest.fixture
async def keycloak_token_acme_bob():
    """
    Fixture providing access token for bob@acme-corp.example.

    Returns:
        str: JWT access token for Bob (ACME Corp tenant)
    """
    token_data = await get_keycloak_token(
        username=TEST_USERS["acme_bob"]["username"],
        password=TEST_USERS["acme_bob"]["password"],
    )
    return token_data["access_token"]


@pytest.fixture
async def keycloak_token_globex_charlie():
    """
    Fixture providing access token for charlie@globex-inc.example.

    Returns:
        str: JWT access token for Charlie (Globex Inc tenant)
    """
    token_data = await get_keycloak_token(
        username=TEST_USERS["globex_charlie"]["username"],
        password=TEST_USERS["globex_charlie"]["password"],
    )
    return token_data["access_token"]


@pytest.fixture
async def keycloak_token_globex_diana():
    """
    Fixture providing access token for diana@globex-inc.example.

    Returns:
        str: JWT access token for Diana (Globex Inc tenant)
    """
    token_data = await get_keycloak_token(
        username=TEST_USERS["globex_diana"]["username"],
        password=TEST_USERS["globex_diana"]["password"],
    )
    return token_data["access_token"]


@pytest.fixture
def integration_test_client():
    """
    Fixture providing test client for integration tests.

    Uses Starlette TestClient which manages its own event loop properly.
    This client makes synchronous-looking calls but internally handles async.

    Returns:
        TestClient: Synchronous test client for FastAPI app
    """
    from starlette.testclient import TestClient

    with TestClient(app) as client:
        yield client


@pytest.fixture
async def redis_client_integration():
    """
    Fixture providing Redis client for integration tests.

    This connects to the real Redis instance configured in settings.
    Automatically cleans up test data after each test.

    Returns:
        redis.Redis: Async Redis client
    """
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    # Yield client for test
    yield client

    # Cleanup: Remove test keys only (revoked_token:* from tests)
    # Note: In production, use separate Redis DB for testing
    cursor = 0
    while True:
        cursor, keys = await client.scan(
            cursor=cursor, match="revoked_token:*", count=100
        )
        if keys:
            await client.delete(*keys)
        if cursor == 0:
            break

    await client.close()


@pytest.fixture
def check_keycloak_available():
    """
    Fixture to check if Keycloak is available before running tests.

    Raises:
        pytest.skip: If Keycloak is not reachable
    """
    try:
        import requests

        response = requests.get(
            f"{KEYCLOAK_BASE_URL}/realms/{KEYCLOAK_REALM}/.well-known/openid-configuration",
            timeout=2,
        )
        if response.status_code != 200:
            pytest.skip("Keycloak not available")
    except Exception:
        pytest.skip("Keycloak not available")


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for async tests."""
    return "asyncio"
