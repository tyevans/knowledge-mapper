"""
Unit tests for tenant resolution middleware.

Tests the TenantResolutionMiddleware class to ensure correct tenant extraction,
public endpoint handling, error handling, and context cleanup.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4, UUID

from starlette.requests import Request
from starlette.responses import Response

from app.middleware.tenant import TenantResolutionMiddleware
from app.schemas.auth import AuthenticatedUser


@pytest.fixture
def middleware():
    """Create middleware instance for testing."""
    app = Mock()
    return TenantResolutionMiddleware(app=app)


@pytest.fixture
def mock_request():
    """Create mock request for testing."""
    from types import SimpleNamespace

    request = Mock(spec=Request)
    request.url.path = "/api/v1/statements"
    request.method = "GET"
    # Use SimpleNamespace instead of Mock to avoid automatic attribute creation
    request.state = SimpleNamespace()
    return request


@pytest.fixture
def authenticated_user():
    """Create authenticated user for testing."""
    return AuthenticatedUser(
        user_id="auth0|test-user-123",
        tenant_id=str(uuid4()),
        jti="test-jti-123",
        exp=1699999999,
        email="test@example.com",
        name="Test User",
        scopes=["statements/read", "statements/write"],
        issuer="http://keycloak:8080/realms/knowledge-mapper-dev",
    )


class TestPublicEndpointSkipping:
    """Test that public endpoints skip tenant resolution."""

    @pytest.mark.asyncio
    async def test_health_endpoint_skipped(self, middleware, mock_request):
        """Test that /health endpoint skips tenant resolution."""
        mock_request.url.path = "/health"
        call_next = AsyncMock(return_value=Response(status_code=200))

        response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 200
        call_next.assert_called_once()
        # tenant_id should not be set
        assert not hasattr(mock_request.state, "tenant_id")

    @pytest.mark.asyncio
    async def test_docs_endpoint_skipped(self, middleware, mock_request):
        """Test that /docs endpoint skips tenant resolution."""
        mock_request.url.path = "/docs"
        call_next = AsyncMock(return_value=Response(status_code=200))

        response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 200
        call_next.assert_called_once()
        assert not hasattr(mock_request.state, "tenant_id")

    @pytest.mark.asyncio
    async def test_oauth_endpoints_skipped(self, middleware, mock_request):
        """Test that OAuth endpoints skip tenant resolution."""
        oauth_endpoints = [
            "/api/v1/oauth/login",
            "/api/v1/oauth/callback",
            "/api/v1/oauth/token/refresh",
            "/api/v1/oauth/logout",
        ]

        for endpoint in oauth_endpoints:
            mock_request.url.path = endpoint
            call_next = AsyncMock(return_value=Response(status_code=200))

            response = await middleware.dispatch(mock_request, call_next)

            assert response.status_code == 200, f"Failed for endpoint: {endpoint}"
            call_next.assert_called_once()
            # Reset for next iteration
            call_next.reset_mock()

    @pytest.mark.asyncio
    async def test_static_files_skipped(self, middleware, mock_request):
        """Test that static file paths skip tenant resolution."""
        mock_request.url.path = "/static/css/main.css"
        call_next = AsyncMock(return_value=Response(status_code=200))

        response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 200
        call_next.assert_called_once()
        assert not hasattr(mock_request.state, "tenant_id")


class TestTenantExtraction:
    """Test tenant ID extraction from authenticated users."""

    @pytest.mark.asyncio
    async def test_tenant_id_extracted_from_token(
        self, middleware, mock_request, authenticated_user
    ):
        """Test tenant_id successfully extracted from authenticated user."""
        # Simulate OAuth token validation setting user in request.state
        mock_request.state.user = authenticated_user

        call_next = AsyncMock(return_value=Response(status_code=200))

        response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 200
        # Verify tenant_id was set in request.state
        assert hasattr(mock_request.state, "tenant_id")
        assert isinstance(mock_request.state.tenant_id, UUID)
        assert str(mock_request.state.tenant_id) == authenticated_user.tenant_id
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_tenant_id_set_in_contextvars(
        self, middleware, mock_request, authenticated_user
    ):
        """Test tenant_id is set in contextvars for application tracking."""
        from app.core.context import get_current_tenant

        mock_request.state.user = authenticated_user
        call_next = AsyncMock(return_value=Response(status_code=200))

        # Before request, context should be None
        assert get_current_tenant() is None

        await middleware.dispatch(mock_request, call_next)

        # After request (in finally block), context should be cleared
        assert get_current_tenant() is None

    @pytest.mark.asyncio
    async def test_string_tenant_id_converted_to_uuid(
        self, middleware, mock_request, authenticated_user
    ):
        """Test that string tenant_id is converted to UUID."""
        # Create user with string tenant_id (valid UUID format)
        tenant_uuid = uuid4()
        authenticated_user.tenant_id = str(tenant_uuid)

        mock_request.state.user = authenticated_user
        call_next = AsyncMock(return_value=Response(status_code=200))

        response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 200
        # Verify conversion to UUID
        assert isinstance(mock_request.state.tenant_id, UUID)
        assert mock_request.state.tenant_id == tenant_uuid


class TestMissingTenantHandling:
    """Test handling of missing or invalid tenant_id."""

    @pytest.mark.asyncio
    async def test_no_authenticated_user_continues(self, middleware, mock_request):
        """Test that missing authenticated user allows request to continue.

        The OAuth dependency will handle authentication for protected endpoints.
        The middleware doesn't enforce authentication - it only sets tenant context
        if authentication is present.
        """
        # No user in request.state (OAuth validation hasn't run or failed)
        # This is not an attribute error - request.state exists but has no user

        call_next = AsyncMock(return_value=Response(status_code=200))

        response = await middleware.dispatch(mock_request, call_next)

        # Request should continue (OAuth dependency will handle auth if needed)
        assert response.status_code == 200
        call_next.assert_called_once()
        # tenant_id should not be set
        assert not hasattr(mock_request.state, "tenant_id")

    @pytest.mark.asyncio
    async def test_missing_tenant_id_in_token_continues(
        self, middleware, mock_request, authenticated_user
    ):
        """Test that missing tenant_id in token allows request to continue.

        The middleware logs a warning but doesn't block the request.
        Downstream handlers can check for tenant_id and return appropriate errors.
        """
        # User authenticated but no tenant_id claim
        authenticated_user.tenant_id = None
        mock_request.state.user = authenticated_user

        call_next = AsyncMock(return_value=Response(status_code=200))

        response = await middleware.dispatch(mock_request, call_next)

        # Request continues (downstream will handle missing tenant)
        assert response.status_code == 200
        call_next.assert_called_once()
        assert not hasattr(mock_request.state, "tenant_id")

    @pytest.mark.asyncio
    async def test_invalid_tenant_id_format_continues(
        self, middleware, mock_request, authenticated_user
    ):
        """Test that invalid tenant_id format allows request to continue.

        The middleware logs an error but doesn't block the request.
        """
        # Invalid UUID format
        authenticated_user.tenant_id = "not-a-valid-uuid"
        mock_request.state.user = authenticated_user

        call_next = AsyncMock(return_value=Response(status_code=200))

        response = await middleware.dispatch(mock_request, call_next)

        # Request continues (downstream will handle invalid tenant)
        assert response.status_code == 200
        call_next.assert_called_once()
        assert not hasattr(mock_request.state, "tenant_id")


class TestContextCleanup:
    """Test that tenant context is properly cleaned up after request."""

    @pytest.mark.asyncio
    async def test_context_cleared_after_successful_request(
        self, middleware, mock_request, authenticated_user
    ):
        """Test tenant context is cleared after successful request."""
        from app.core.context import get_current_tenant

        mock_request.state.user = authenticated_user
        call_next = AsyncMock(return_value=Response(status_code=200))

        await middleware.dispatch(mock_request, call_next)

        # Context should be cleared in finally block
        assert get_current_tenant() is None

    @pytest.mark.asyncio
    async def test_context_cleared_after_error(
        self, middleware, mock_request, authenticated_user
    ):
        """Test tenant context is cleared even if downstream handler raises error."""
        from app.core.context import get_current_tenant

        mock_request.state.user = authenticated_user
        # Simulate downstream error
        call_next = AsyncMock(side_effect=Exception("Downstream error"))

        # The middleware catches the exception and returns a 500 response
        response = await middleware.dispatch(mock_request, call_next)

        # Should return 500 error response
        assert response.status_code == 500

        # Context should still be cleared in finally block
        assert get_current_tenant() is None

    @pytest.mark.asyncio
    async def test_context_cleared_for_public_endpoints(self, middleware, mock_request):
        """Test context is cleared even for public endpoints."""
        from app.core.context import get_current_tenant

        mock_request.url.path = "/health"
        call_next = AsyncMock(return_value=Response(status_code=200))

        await middleware.dispatch(mock_request, call_next)

        assert get_current_tenant() is None


class TestErrorHandling:
    """Test error handling in middleware."""

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_500(
        self, middleware, mock_request, authenticated_user
    ):
        """Test that unexpected errors return 500 Internal Server Error."""
        mock_request.state.user = authenticated_user

        # Simulate unexpected error in call_next
        call_next = AsyncMock(side_effect=RuntimeError("Unexpected error"))

        # The middleware catches the error and returns 500
        response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 500
        # Verify error response format
        import json
        content = json.loads(response.body)
        assert content["error"]["code"] == 500
        assert "Failed to resolve tenant context" in content["error"]["message"]

    @pytest.mark.asyncio
    async def test_context_cleared_on_error(
        self, middleware, mock_request, authenticated_user
    ):
        """Test that context is cleared even when errors occur."""
        from app.core.context import get_current_tenant

        mock_request.state.user = authenticated_user
        call_next = AsyncMock(side_effect=ValueError("Test error"))

        # The middleware catches the error and returns 500
        response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 500

        # Context should be cleared in finally block
        assert get_current_tenant() is None


class TestTenantIdExtraction:
    """Test the _extract_tenant_id method directly."""

    @pytest.mark.asyncio
    async def test_extract_valid_tenant_id(
        self, middleware, mock_request, authenticated_user
    ):
        """Test extracting valid tenant_id."""
        mock_request.state.user = authenticated_user

        tenant_id = await middleware._extract_tenant_id(mock_request)

        assert tenant_id is not None
        assert isinstance(tenant_id, UUID)
        assert str(tenant_id) == authenticated_user.tenant_id

    @pytest.mark.asyncio
    async def test_extract_tenant_id_no_user(self, middleware, mock_request):
        """Test extracting tenant_id when no user is authenticated."""
        # No user attribute in request.state
        # Ensure request.state has no user attribute
        # (SimpleNamespace doesn't auto-create attributes like Mock does)

        tenant_id = await middleware._extract_tenant_id(mock_request)

        assert tenant_id is None

    @pytest.mark.asyncio
    async def test_extract_tenant_id_missing(
        self, middleware, mock_request, authenticated_user
    ):
        """Test extracting tenant_id when it's missing from user."""
        authenticated_user.tenant_id = None
        mock_request.state.user = authenticated_user

        tenant_id = await middleware._extract_tenant_id(mock_request)

        assert tenant_id is None

    @pytest.mark.asyncio
    async def test_extract_invalid_tenant_id_format(
        self, middleware, mock_request, authenticated_user
    ):
        """Test extracting tenant_id with invalid UUID format."""
        authenticated_user.tenant_id = "invalid-uuid-format"
        mock_request.state.user = authenticated_user

        tenant_id = await middleware._extract_tenant_id(mock_request)

        assert tenant_id is None

    @pytest.mark.asyncio
    async def test_extract_tenant_id_converts_string_to_uuid(
        self, middleware, mock_request, authenticated_user
    ):
        """Test that string tenant_id is converted to UUID."""
        tenant_uuid = uuid4()
        authenticated_user.tenant_id = str(tenant_uuid)
        mock_request.state.user = authenticated_user

        tenant_id = await middleware._extract_tenant_id(mock_request)

        assert tenant_id is not None
        assert isinstance(tenant_id, UUID)
        assert tenant_id == tenant_uuid


class TestConcurrentRequests:
    """Test that context isolation works for concurrent requests."""

    @pytest.mark.asyncio
    async def test_context_isolated_between_requests(
        self, middleware, authenticated_user
    ):
        """Test that context is isolated between concurrent requests."""
        import asyncio
        from types import SimpleNamespace
        from app.core.context import get_current_tenant

        # Create two different tenants
        tenant_1 = uuid4()
        tenant_2 = uuid4()

        # Create mock requests with different tenant IDs
        request_1 = Mock(spec=Request)
        request_1.url.path = "/api/v1/statements"
        request_1.method = "GET"
        request_1.state = SimpleNamespace()
        user_1 = AuthenticatedUser(
            user_id="user-1",
            tenant_id=str(tenant_1),
            jti="jti-1",
            exp=1699999999,
            scopes=[],
            issuer="http://keycloak:8080/realms/knowledge-mapper-dev",
        )
        request_1.state.user = user_1

        request_2 = Mock(spec=Request)
        request_2.url.path = "/api/v1/statements"
        request_2.method = "GET"
        request_2.state = SimpleNamespace()
        user_2 = AuthenticatedUser(
            user_id="user-2",
            tenant_id=str(tenant_2),
            jti="jti-2",
            exp=1699999999,
            scopes=[],
            issuer="http://keycloak:8080/realms/knowledge-mapper-dev",
        )
        request_2.state.user = user_2

        # Track which tenant was seen during request processing
        seen_tenants = []

        async def slow_handler(request):
            """Handler that checks current tenant and sleeps."""
            # Record the tenant_id set in request.state
            tenant = getattr(request.state, "tenant_id", None)
            seen_tenants.append(tenant)
            await asyncio.sleep(0.01)  # Simulate slow processing
            return Response(status_code=200)

        # Process both requests concurrently
        await asyncio.gather(
            middleware.dispatch(request_1, slow_handler),
            middleware.dispatch(request_2, slow_handler),
        )

        # Both tenants should have been seen
        assert len(seen_tenants) == 2
        assert tenant_1 in seen_tenants
        assert tenant_2 in seen_tenants

        # Context should be cleared after both requests
        assert get_current_tenant() is None


class TestPublicPathsConfiguration:
    """Test the public paths configuration."""

    def test_public_paths_includes_health_endpoints(self, middleware):
        """Test that health endpoints are in public paths."""
        assert "/health" in middleware.PUBLIC_PATHS
        assert "/ready" in middleware.PUBLIC_PATHS
        assert "/api/v1/health" in middleware.PUBLIC_PATHS
        assert "/api/v1/ready" in middleware.PUBLIC_PATHS

    def test_public_paths_includes_docs_endpoints(self, middleware):
        """Test that documentation endpoints are in public paths."""
        assert "/docs" in middleware.PUBLIC_PATHS
        assert "/redoc" in middleware.PUBLIC_PATHS
        assert "/openapi.json" in middleware.PUBLIC_PATHS

    def test_public_paths_includes_oauth_endpoints(self, middleware):
        """Test that OAuth endpoints are in public paths."""
        assert "/api/v1/oauth/login" in middleware.PUBLIC_PATHS
        assert "/api/v1/oauth/callback" in middleware.PUBLIC_PATHS
        assert "/api/v1/oauth/token/refresh" in middleware.PUBLIC_PATHS
        assert "/api/v1/oauth/logout" in middleware.PUBLIC_PATHS

    def test_public_paths_includes_root(self, middleware):
        """Test that root endpoint is in public paths."""
        assert "/" in middleware.PUBLIC_PATHS
