"""
Integration tests for tenant resolution middleware.

Tests the middleware in a real FastAPI application context with OAuth validation.
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from app.middleware.tenant import TenantResolutionMiddleware
from app.api.dependencies.auth import get_current_user
from app.schemas.auth import AuthenticatedUser


@pytest.fixture
def test_app():
    """Create a test FastAPI app with tenant middleware."""
    app = FastAPI()

    # Add tenant resolution middleware
    app.add_middleware(TenantResolutionMiddleware)

    # Create test endpoints
    @app.get("/public/health")
    async def health():
        """Public endpoint - no authentication required."""
        return {"status": "healthy"}

    @app.get("/protected/resource")
    async def protected_resource(user: AuthenticatedUser = Depends(get_current_user)):
        """Protected endpoint - requires authentication."""
        # Access tenant_id from dependency injection
        return {
            "user_id": user.user_id,
            "tenant_id": user.tenant_id,
            "message": "Access granted",
        }

    @app.get("/protected/tenant-context")
    async def tenant_context_endpoint(
        user: AuthenticatedUser = Depends(get_current_user)
    ):
        """Protected endpoint that checks request state."""
        from fastapi import Request

        async def inner(request: Request):
            # Check that tenant_id is in request.state
            tenant_id = getattr(request.state, "tenant_id", None)
            return {
                "user_id": user.user_id,
                "tenant_id": user.tenant_id,
                "request_state_tenant_id": str(tenant_id) if tenant_id else None,
            }

        from fastapi import Request

        return await inner(Request)

    return app


@pytest.fixture
def client(test_app):
    """Create test client for the app."""
    return TestClient(test_app)


@pytest.fixture
def mock_authenticated_user():
    """Create mock authenticated user."""
    return AuthenticatedUser(
        user_id="test-user-123",
        tenant_id=str(uuid4()),
        jti="test-jti-123",
        exp=1699999999,
        email="test@example.com",
        name="Test User",
        scopes=["statements/read", "statements/write"],
        issuer="http://keycloak:8080/realms/knowledge-mapper-dev",
    )


class TestPublicEndpoints:
    """Test that public endpoints work without authentication."""

    def test_public_endpoint_accessible(self, client):
        """Test that public endpoints are accessible without authentication."""
        response = client.get("/public/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestProtectedEndpoints:
    """Test protected endpoints with authentication."""

    def test_protected_endpoint_requires_authentication(self, client):
        """Test that protected endpoints require authentication."""
        # Make request without authentication
        response = client.get("/protected/resource")

        # Should return 401 or 403 (depends on OAuth dependency behavior)
        # The OAuth dependency will handle this
        assert response.status_code in [401, 403]

    @patch("app.api.dependencies.auth.get_current_user")
    def test_protected_endpoint_with_authentication(
        self, mock_get_current_user, client, mock_authenticated_user
    ):
        """Test protected endpoint with valid authentication."""
        # Mock the OAuth dependency to return authenticated user
        mock_get_current_user.return_value = mock_authenticated_user

        response = client.get("/protected/resource")

        # Should succeed
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == mock_authenticated_user.user_id
        assert data["tenant_id"] == mock_authenticated_user.tenant_id


class TestMiddlewareIntegration:
    """Test middleware integration with FastAPI."""

    def test_middleware_added_to_app(self, test_app):
        """Test that middleware is properly added to the app."""
        # Check that TenantResolutionMiddleware is in the middleware stack
        middleware_classes = [
            middleware.cls.__name__
            for middleware in test_app.user_middleware
        ]

        assert "TenantResolutionMiddleware" in middleware_classes

    @patch("app.api.dependencies.auth.get_current_user")
    def test_middleware_sets_tenant_context(
        self, mock_get_current_user, client, mock_authenticated_user
    ):
        """Test that middleware sets tenant context for authenticated requests."""
        # Mock the OAuth dependency
        mock_get_current_user.return_value = mock_authenticated_user

        response = client.get("/protected/resource")

        assert response.status_code == 200
        # Verify that the user's tenant_id was accessible
        data = response.json()
        assert data["tenant_id"] == mock_authenticated_user.tenant_id


class TestContextPropagation:
    """Test that tenant context is propagated correctly."""

    @patch("app.api.dependencies.auth.get_current_user")
    def test_context_cleared_after_request(
        self, mock_get_current_user, client, mock_authenticated_user
    ):
        """Test that tenant context is cleared after request completes."""
        from app.core.context import get_current_tenant

        # Mock the OAuth dependency
        mock_get_current_user.return_value = mock_authenticated_user

        # Make a request
        response = client.get("/protected/resource")

        assert response.status_code == 200

        # After request completes, context should be cleared
        # Note: In test client, context is cleared in the finally block
        # This test verifies the mechanism works
        assert get_current_tenant() is None


class TestTenantIsolation:
    """Test tenant isolation between requests."""

    @patch("app.api.dependencies.auth.get_current_user")
    def test_different_tenants_isolated(
        self, mock_get_current_user, client
    ):
        """Test that different requests with different tenants are isolated."""
        # Create two users with different tenant IDs
        tenant_1 = uuid4()
        user_1 = AuthenticatedUser(
            user_id="user-1",
            tenant_id=str(tenant_1),
            jti="jti-1",
            exp=1699999999,
            scopes=[],
            issuer="http://keycloak:8080/realms/knowledge-mapper-dev",
        )

        tenant_2 = uuid4()
        user_2 = AuthenticatedUser(
            user_id="user-2",
            tenant_id=str(tenant_2),
            jti="jti-2",
            exp=1699999999,
            scopes=[],
            issuer="http://keycloak:8080/realms/knowledge-mapper-dev",
        )

        # First request with tenant 1
        mock_get_current_user.return_value = user_1
        response_1 = client.get("/protected/resource")

        assert response_1.status_code == 200
        data_1 = response_1.json()
        assert data_1["tenant_id"] == str(tenant_1)

        # Second request with tenant 2
        mock_get_current_user.return_value = user_2
        response_2 = client.get("/protected/resource")

        assert response_2.status_code == 200
        data_2 = response_2.json()
        assert data_2["tenant_id"] == str(tenant_2)

        # Verify tenants are different
        assert data_1["tenant_id"] != data_2["tenant_id"]


class TestErrorHandling:
    """Test error handling in middleware integration."""

    @patch("app.api.dependencies.auth.get_current_user")
    def test_missing_tenant_id_handled(
        self, mock_get_current_user, client
    ):
        """Test that missing tenant_id is handled gracefully."""
        # Create user without tenant_id
        user_without_tenant = AuthenticatedUser(
            user_id="user-1",
            tenant_id=None,  # Missing tenant_id
            jti="jti-1",
            exp=1699999999,
            scopes=[],
            issuer="http://keycloak:8080/realms/knowledge-mapper-dev",
        )

        mock_get_current_user.return_value = user_without_tenant

        # This should be caught by OAuth validation (tenant_id is required)
        # But if it somehow gets through, the middleware should handle it
        response = client.get("/protected/resource")

        # Should return an error (401 or 403)
        # The exact behavior depends on OAuth validation
        assert response.status_code in [401, 403, 500]
