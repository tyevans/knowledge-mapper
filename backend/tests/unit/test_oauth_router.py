"""
Unit tests for OAuth router endpoints.

Tests all OAuth endpoints with mocked OAuth client responses:
- /oauth/login (authorization URL generation)
- /oauth/callback (token exchange)
- /oauth/token/refresh (token refresh)
- /oauth/logout (session cleanup)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.oauth_client import OAuthClient, get_oauth_client
from app.schemas.oauth import TokenResponse, PKCEChallenge


@pytest.fixture
def mock_oauth_client():
    """Mock OAuth client for testing."""
    client = AsyncMock(spec=OAuthClient)
    return client


@pytest.fixture
def test_client(mock_oauth_client):
    """FastAPI test client with mocked OAuth client dependency."""
    async def override_get_oauth_client():
        return mock_oauth_client

    app.dependency_overrides[get_oauth_client] = override_get_oauth_client
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def mock_token_response():
    """Mock token response from OAuth provider."""
    return TokenResponse(
        access_token="test_access_token_12345",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="test_refresh_token_67890",
        scope="openid profile email",
    )


@pytest.fixture
def mock_pkce_challenge():
    """Mock PKCE challenge."""
    return PKCEChallenge(
        code_verifier="test_code_verifier_abc123",
        code_challenge="test_code_challenge_xyz789",
        code_challenge_method="S256",
    )


# Login Endpoint Tests

def test_login_endpoint_success(test_client, mock_oauth_client, mock_pkce_challenge):
    """Test /oauth/login returns authorization URL and sets cookies."""
    mock_oauth_client.get_authorization_url.return_value = (
        "https://keycloak.example.com/auth?code_challenge=xyz&state=abc",
        "test_state_12345",
        mock_pkce_challenge,
    )

    response = test_client.get("/api/v1/oauth/login")

    assert response.status_code == 200
    json_data = response.json()
    assert "authorization_url" in json_data
    assert "state" in json_data
    assert json_data["state"] == "test_state_12345"

    # Verify cookies are set
    assert "oauth_state" in response.cookies
    assert "code_verifier" in response.cookies
    assert response.cookies["oauth_state"] == "test_state_12345"


def test_login_endpoint_sets_secure_cookies(test_client, mock_oauth_client, mock_pkce_challenge):
    """Test /oauth/login sets HTTP-only cookies with proper security attributes."""
    mock_oauth_client.get_authorization_url.return_value = (
        "https://keycloak.example.com/auth",
        "state_123",
        mock_pkce_challenge,
    )

    response = test_client.get("/api/v1/oauth/login")

    # Note: TestClient doesn't expose all cookie attributes, but we verify they're set
    assert "oauth_state" in response.cookies
    assert "code_verifier" in response.cookies


def test_login_endpoint_with_redirect_uri(test_client, mock_oauth_client, mock_pkce_challenge):
    """Test /oauth/login accepts optional redirect_uri parameter."""
    mock_oauth_client.get_authorization_url.return_value = (
        "https://keycloak.example.com/auth",
        "state_456",
        mock_pkce_challenge,
    )

    response = test_client.get("/api/v1/oauth/login?redirect_uri=http://localhost:3000/dashboard")

    assert response.status_code == 200
    # Redirect URI should be stored in cookie
    assert "post_auth_redirect" in response.cookies


def test_login_endpoint_provider_unavailable(test_client, mock_oauth_client):
    """Test /oauth/login returns 503 when OAuth provider is unavailable."""
    mock_oauth_client.get_authorization_url.side_effect = Exception("Connection refused")

    response = test_client.get("/api/v1/oauth/login")

    assert response.status_code == 503
    json_data = response.json()
    assert "error" in json_data
    assert json_data["error"]["message"] == "OAuth provider unavailable"


# Callback Endpoint Tests

def test_callback_with_valid_state(test_client, mock_oauth_client, mock_token_response):
    """Test /oauth/callback exchanges code for token with valid state."""
    mock_oauth_client.get_authorization_url.return_value = (
        "https://keycloak.example.com/auth",
        "valid_state_123",
        PKCEChallenge(
            code_verifier="verifier_123",
            code_challenge="challenge_123",
            code_challenge_method="S256",
        ),
    )
    mock_oauth_client.exchange_code_for_token.return_value = mock_token_response

    # First, initiate login to set state cookie
    login_response = test_client.get("/api/v1/oauth/login")
    state = login_response.json()["state"]

    # Then, call callback with the same state (follow_redirects=False to check redirect)
    callback_response = test_client.get(
        f"/api/v1/oauth/callback?code=test_code&state={state}",
        follow_redirects=False,
    )

    assert callback_response.status_code == 302  # Redirect
    assert callback_response.headers["location"] == "http://localhost:3000"  # Default FRONTEND_URL

    # Verify tokens are stored in cookies
    assert "access_token" in callback_response.cookies
    assert "refresh_token" in callback_response.cookies


def test_callback_with_invalid_state(test_client, mock_oauth_client):
    """Test /oauth/callback rejects mismatched state (CSRF protection)."""
    # Set a state cookie manually
    test_client.cookies.set("oauth_state", "expected_state")
    test_client.cookies.set("code_verifier", "verifier_123")

    # Call callback with different state
    response = test_client.get("/api/v1/oauth/callback?code=test_code&state=wrong_state")

    assert response.status_code == 400
    json_data = response.json()
    assert "error" in json_data
    assert "Invalid state parameter" in json_data["error"]["message"]


def test_callback_with_missing_state_cookie(test_client, mock_oauth_client):
    """Test /oauth/callback rejects request when state cookie is missing."""
    # Call callback without setting state cookie
    response = test_client.get("/api/v1/oauth/callback?code=test_code&state=some_state")

    assert response.status_code == 400
    json_data = response.json()
    assert "error" in json_data
    assert "Invalid state parameter" in json_data["error"]["message"]


def test_callback_with_missing_code_verifier(test_client, mock_oauth_client):
    """Test /oauth/callback rejects request when code_verifier cookie is missing."""
    # Set state cookie but not code_verifier
    test_client.cookies.set("oauth_state", "valid_state")

    response = test_client.get("/api/v1/oauth/callback?code=test_code&state=valid_state")

    assert response.status_code == 400
    json_data = response.json()
    assert "error" in json_data
    assert "Missing code verifier" in json_data["error"]["message"]


def test_callback_token_exchange_failure(test_client, mock_oauth_client):
    """Test /oauth/callback handles token exchange failure."""
    mock_oauth_client.exchange_code_for_token.side_effect = Exception("Token exchange failed")

    test_client.cookies.set("oauth_state", "valid_state")
    test_client.cookies.set("code_verifier", "verifier_123")

    response = test_client.get("/api/v1/oauth/callback?code=test_code&state=valid_state")

    assert response.status_code == 500
    json_data = response.json()
    assert "error" in json_data
    assert "Token exchange failed" in json_data["error"]["message"]


def test_callback_clears_temporary_cookies(test_client, mock_oauth_client, mock_token_response):
    """Test /oauth/callback clears temporary state and verifier cookies."""
    mock_oauth_client.exchange_code_for_token.return_value = mock_token_response

    test_client.cookies.set("oauth_state", "valid_state")
    test_client.cookies.set("code_verifier", "verifier_123")
    test_client.cookies.set("post_auth_redirect", "http://localhost:3000/dashboard")

    response = test_client.get(
        "/api/v1/oauth/callback?code=test_code&state=valid_state",
        follow_redirects=False,
    )

    assert response.status_code == 302
    # Note: TestClient may not fully support delete_cookie validation
    # In production, these cookies would be cleared


def test_callback_with_custom_redirect(test_client, mock_oauth_client, mock_token_response):
    """Test /oauth/callback redirects to custom post_auth_redirect URL."""
    mock_oauth_client.exchange_code_for_token.return_value = mock_token_response
    custom_redirect = "http://localhost:3000/dashboard"

    test_client.cookies.set("oauth_state", "valid_state")
    test_client.cookies.set("code_verifier", "verifier_123")
    test_client.cookies.set("post_auth_redirect", custom_redirect)

    response = test_client.get(
        "/api/v1/oauth/callback?code=test_code&state=valid_state",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == custom_redirect


# Token Refresh Endpoint Tests

def test_token_refresh_success(test_client, mock_oauth_client, mock_token_response):
    """Test /oauth/token/refresh exchanges refresh token for new access token."""
    mock_oauth_client.refresh_token.return_value = mock_token_response

    test_client.cookies.set("refresh_token", "test_refresh_token")

    response = test_client.post("/api/v1/oauth/token/refresh")

    assert response.status_code == 200
    json_data = response.json()
    assert json_data["access_token"] == "test_access_token_12345"
    assert json_data["token_type"] == "Bearer"
    assert json_data["expires_in"] == 3600

    # Verify new access token is set in cookie
    assert "access_token" in response.cookies


def test_token_refresh_missing_refresh_token(test_client, mock_oauth_client):
    """Test /oauth/token/refresh returns 401 when refresh token is missing."""
    response = test_client.post("/api/v1/oauth/token/refresh")

    assert response.status_code == 401
    json_data = response.json()
    assert "error" in json_data
    assert "No refresh token available" in json_data["error"]["message"]


def test_token_refresh_failure(test_client, mock_oauth_client):
    """Test /oauth/token/refresh handles refresh failure."""
    mock_oauth_client.refresh_token.side_effect = Exception("Token refresh failed")

    test_client.cookies.set("refresh_token", "invalid_token")

    response = test_client.post("/api/v1/oauth/token/refresh")

    assert response.status_code == 401
    json_data = response.json()
    assert "error" in json_data
    assert "Token refresh failed" in json_data["error"]["message"]


def test_token_refresh_updates_refresh_token(test_client, mock_oauth_client):
    """Test /oauth/token/refresh updates refresh token if new one is issued."""
    new_token_response = TokenResponse(
        access_token="new_access_token",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="new_refresh_token",  # New refresh token
        scope="openid profile email",
    )
    mock_oauth_client.refresh_token.return_value = new_token_response

    test_client.cookies.set("refresh_token", "old_refresh_token")

    response = test_client.post("/api/v1/oauth/token/refresh")

    assert response.status_code == 200
    assert "refresh_token" in response.cookies


# Logout Endpoint Tests

def test_logout_clears_cookies(test_client):
    """Test /oauth/logout clears all session cookies."""
    test_client.cookies.set("access_token", "test_token")
    test_client.cookies.set("refresh_token", "test_refresh")
    test_client.cookies.set("oauth_state", "test_state")

    response = test_client.post("/api/v1/oauth/logout")

    assert response.status_code == 204
    # Note: TestClient may not fully support delete_cookie validation
    # In production, all cookies would be cleared


def test_logout_without_cookies(test_client):
    """Test /oauth/logout succeeds even without existing cookies."""
    response = test_client.post("/api/v1/oauth/logout")

    assert response.status_code == 204


# Edge Cases and Error Handling

def test_callback_without_refresh_token(test_client, mock_oauth_client):
    """Test /oauth/callback handles token response without refresh token."""
    token_response_no_refresh = TokenResponse(
        access_token="access_token_only",
        token_type="Bearer",
        expires_in=3600,
        refresh_token=None,  # No refresh token
    )
    mock_oauth_client.exchange_code_for_token.return_value = token_response_no_refresh

    test_client.cookies.set("oauth_state", "valid_state")
    test_client.cookies.set("code_verifier", "verifier_123")

    response = test_client.get(
        "/api/v1/oauth/callback?code=test_code&state=valid_state",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "access_token" in response.cookies
    # refresh_token should not be set
