"""Unit tests for OAuth client."""
import hashlib
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.oauth_client import OAuthClient
from app.schemas.oauth import TokenResponse, OIDCDiscovery, UserInfo, PKCEChallenge


@pytest.fixture
def oauth_client():
    """Create OAuth client instance for testing."""
    return OAuthClient(
        client_id="test-client",
        client_secret="test-secret",
        redirect_uri="http://localhost:8000/callback",
        issuer_url="http://keycloak:8080/realms/knowledge-mapper-dev",
        scopes=["openid", "profile", "email"],
        use_pkce=True,
        http_timeout=10,
    )


@pytest.fixture
def mock_oidc_discovery():
    """Mock OIDC discovery response."""
    return {
        "issuer": "http://keycloak:8080/realms/knowledge-mapper-dev",
        "authorization_endpoint": "http://keycloak:8080/realms/knowledge-mapper-dev/protocol/openid-connect/auth",
        "token_endpoint": "http://keycloak:8080/realms/knowledge-mapper-dev/protocol/openid-connect/token",
        "jwks_uri": "http://keycloak:8080/realms/knowledge-mapper-dev/protocol/openid-connect/certs",
        "userinfo_endpoint": "http://keycloak:8080/realms/knowledge-mapper-dev/protocol/openid-connect/userinfo",
        "end_session_endpoint": "http://keycloak:8080/realms/knowledge-mapper-dev/protocol/openid-connect/logout",
    }


@pytest.mark.asyncio
class TestPKCEGeneration:
    """Test PKCE code verifier and challenge generation."""

    async def test_pkce_challenge_generation(self, oauth_client):
        """Test PKCE code verifier and challenge are generated correctly."""
        challenge = oauth_client.generate_pkce_challenge()

        # Verify structure
        assert isinstance(challenge, PKCEChallenge)
        assert challenge.code_challenge_method == "S256"

        # Verifier should be 43 characters (base64url of 32 bytes)
        assert len(challenge.code_verifier) == 43
        # Only base64url characters (A-Z, a-z, 0-9, -, _)
        assert all(
            c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            for c in challenge.code_verifier
        )

        # Challenge should be 43 characters (base64url of SHA256 hash)
        assert len(challenge.code_challenge) == 43

    async def test_pkce_challenge_is_valid_sha256(self, oauth_client):
        """Test that code_challenge is valid SHA256 hash of code_verifier."""
        challenge = oauth_client.generate_pkce_challenge()

        # Manually compute expected challenge
        expected_hash = hashlib.sha256(challenge.code_verifier.encode("utf-8")).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_hash).decode("utf-8").rstrip("=")

        assert challenge.code_challenge == expected_challenge

    async def test_pkce_challenge_is_unique(self, oauth_client):
        """Test that each PKCE challenge is unique."""
        challenge1 = oauth_client.generate_pkce_challenge()
        challenge2 = oauth_client.generate_pkce_challenge()

        assert challenge1.code_verifier != challenge2.code_verifier
        assert challenge1.code_challenge != challenge2.code_challenge


@pytest.mark.asyncio
class TestStateGeneration:
    """Test state parameter generation for CSRF protection."""

    async def test_state_generation(self, oauth_client):
        """Test state parameter is generated correctly."""
        state = oauth_client.generate_state()

        # State should be sufficiently long for security
        assert len(state) >= 32
        # Should be URL-safe
        assert all(c.isalnum() or c in "-_" for c in state)

    async def test_state_is_unique(self, oauth_client):
        """Test that each state parameter is unique."""
        state1 = oauth_client.generate_state()
        state2 = oauth_client.generate_state()

        assert state1 != state2


@pytest.mark.asyncio
class TestOIDCDiscovery:
    """Test OIDC discovery endpoint fetching."""

    async def test_discover_endpoints_success(self, oauth_client, mock_oidc_discovery):
        """Test successful OIDC discovery."""
        with patch.object(oauth_client._http_client, "get") as mock_get:
            # Mock successful discovery response
            mock_response = MagicMock()
            mock_response.json.return_value = mock_oidc_discovery
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # Discover endpoints
            config = await oauth_client.discover_endpoints()

            # Verify discovery was called
            mock_get.assert_called_once()
            call_url = mock_get.call_args[0][0]
            assert call_url.endswith("/.well-known/openid-configuration")

            # Verify parsed config
            assert isinstance(config, OIDCDiscovery)
            assert config.issuer == "http://keycloak:8080/realms/knowledge-mapper-dev"
            assert config.authorization_endpoint.endswith("/auth")
            assert config.token_endpoint.endswith("/token")
            assert config.jwks_uri.endswith("/certs")

    async def test_discover_endpoints_caching(self, oauth_client, mock_oidc_discovery):
        """Test that OIDC discovery is cached after first call."""
        with patch.object(oauth_client._http_client, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_oidc_discovery
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # First call - should fetch
            config1 = await oauth_client.discover_endpoints()
            assert mock_get.call_count == 1

            # Second call - should use cache
            config2 = await oauth_client.discover_endpoints()
            assert mock_get.call_count == 1  # No additional call

            # Should return same config
            assert config1 == config2

    async def test_discover_endpoints_http_error(self, oauth_client):
        """Test OIDC discovery handles HTTP errors."""
        with patch.object(oauth_client._http_client, "get") as mock_get:
            import httpx
            mock_get.side_effect = httpx.HTTPError("Network error")

            with pytest.raises(httpx.HTTPError):
                await oauth_client.discover_endpoints()


@pytest.mark.asyncio
class TestAuthorizationURL:
    """Test authorization URL generation."""

    async def test_authorization_url_generation(self, oauth_client, mock_oidc_discovery):
        """Test authorization URL generation with PKCE."""
        with patch.object(oauth_client._http_client, "get") as mock_get:
            # Mock OIDC discovery
            mock_response = MagicMock()
            mock_response.json.return_value = mock_oidc_discovery
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # Generate authorization URL
            url, state, challenge = await oauth_client.get_authorization_url()

            # Verify URL structure
            assert url.startswith("http://keycloak:8080/realms/knowledge-mapper-dev/protocol/openid-connect/auth")
            assert "response_type=code" in url
            assert f"client_id={oauth_client.client_id}" in url
            # redirect_uri is URL-encoded in the URL
            assert "redirect_uri=" in url
            assert f"state={state}" in url
            assert "code_challenge=" in url
            assert "code_challenge_method=S256" in url

            # Verify state
            assert len(state) >= 32

            # Verify PKCE challenge
            assert challenge is not None
            assert isinstance(challenge, PKCEChallenge)
            assert len(challenge.code_verifier) == 43
            assert challenge.code_challenge in url

    async def test_authorization_url_with_custom_state(self, oauth_client, mock_oidc_discovery):
        """Test authorization URL generation with custom state parameter."""
        with patch.object(oauth_client._http_client, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_oidc_discovery
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            custom_state = "my-custom-state-12345"
            url, state, challenge = await oauth_client.get_authorization_url(state=custom_state)

            assert state == custom_state
            assert f"state={custom_state}" in url

    async def test_authorization_url_without_pkce(self, mock_oidc_discovery):
        """Test authorization URL generation without PKCE."""
        client = OAuthClient(
            client_id="test-client",
            client_secret="test-secret",
            redirect_uri="http://localhost:8000/callback",
            issuer_url="http://keycloak:8080/realms/knowledge-mapper-dev",
            use_pkce=False,
        )

        with patch.object(client._http_client, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_oidc_discovery
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            url, state, challenge = await client.get_authorization_url()

            # PKCE parameters should not be in URL
            assert "code_challenge=" not in url
            assert "code_challenge_method=" not in url
            assert challenge is None


@pytest.mark.asyncio
class TestTokenExchange:
    """Test authorization code exchange for tokens."""

    async def test_exchange_code_for_token_success(self, oauth_client, mock_oidc_discovery):
        """Test successful authorization code exchange."""
        with patch.object(oauth_client._http_client, "get") as mock_get, \
             patch.object(oauth_client._http_client, "post") as mock_post:

            # Mock OIDC discovery
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_oidc_discovery
            mock_discovery_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_discovery_response

            # Mock token response
            mock_token_response = MagicMock()
            mock_token_response.json.return_value = {
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
                "expires_in": 3600,
                "token_type": "Bearer",
                "scope": "openid profile email",
            }
            mock_token_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_token_response

            # Exchange code for token
            verifier = "test-code-verifier-123456789012345678901234"
            token = await oauth_client.exchange_code_for_token("test-auth-code", verifier)

            # Verify token response
            assert isinstance(token, TokenResponse)
            assert token.access_token == "test-access-token"
            assert token.refresh_token == "test-refresh-token"
            assert token.expires_in == 3600
            assert token.token_type == "Bearer"

            # Verify POST request was made with correct data
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["data"]["grant_type"] == "authorization_code"
            assert call_kwargs["data"]["code"] == "test-auth-code"
            assert call_kwargs["data"]["code_verifier"] == verifier

    async def test_exchange_code_without_verifier_fails(self, oauth_client, mock_oidc_discovery):
        """Test that PKCE code_verifier is required when PKCE enabled."""
        with patch.object(oauth_client._http_client, "get") as mock_get:
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_oidc_discovery
            mock_get.return_value = mock_discovery_response

            # Should raise ValueError if code_verifier not provided
            with pytest.raises(ValueError, match="PKCE enabled but code_verifier not provided"):
                await oauth_client.exchange_code_for_token("test-code", code_verifier=None)

    async def test_exchange_code_invalid_code(self, oauth_client, mock_oidc_discovery):
        """Test token exchange with invalid authorization code."""
        with patch.object(oauth_client._http_client, "get") as mock_get, \
             patch.object(oauth_client._http_client, "post") as mock_post:

            # Mock OIDC discovery
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_oidc_discovery
            mock_discovery_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_discovery_response

            # Mock token error response
            import httpx
            mock_token_response = MagicMock()
            mock_token_response.status_code = 400
            mock_token_response.json.return_value = {
                "error": "invalid_grant",
                "error_description": "Invalid authorization code",
            }
            mock_post.side_effect = httpx.HTTPStatusError(
                "Bad Request",
                request=MagicMock(),
                response=mock_token_response,
            )

            with pytest.raises(httpx.HTTPStatusError):
                await oauth_client.exchange_code_for_token("invalid-code", "verifier")


@pytest.mark.asyncio
class TestTokenRefresh:
    """Test token refresh functionality."""

    async def test_refresh_token_success(self, oauth_client, mock_oidc_discovery):
        """Test successful token refresh."""
        with patch.object(oauth_client._http_client, "get") as mock_get, \
             patch.object(oauth_client._http_client, "post") as mock_post:

            # Mock OIDC discovery
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_oidc_discovery
            mock_discovery_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_discovery_response

            # Mock token refresh response
            mock_token_response = MagicMock()
            mock_token_response.json.return_value = {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 3600,
                "token_type": "Bearer",
            }
            mock_token_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_token_response

            # Refresh token
            token = await oauth_client.refresh_token("old-refresh-token")

            # Verify token response
            assert isinstance(token, TokenResponse)
            assert token.access_token == "new-access-token"
            assert token.refresh_token == "new-refresh-token"

            # Verify POST request
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["data"]["grant_type"] == "refresh_token"
            assert call_kwargs["data"]["refresh_token"] == "old-refresh-token"

    async def test_refresh_token_expired(self, oauth_client, mock_oidc_discovery):
        """Test token refresh with expired refresh token."""
        with patch.object(oauth_client._http_client, "get") as mock_get, \
             patch.object(oauth_client._http_client, "post") as mock_post:

            # Mock OIDC discovery
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_oidc_discovery
            mock_discovery_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_discovery_response

            # Mock token error response
            import httpx
            mock_token_response = MagicMock()
            mock_token_response.status_code = 400
            mock_token_response.json.return_value = {
                "error": "invalid_grant",
                "error_description": "Refresh token expired",
            }
            mock_post.side_effect = httpx.HTTPStatusError(
                "Bad Request",
                request=MagicMock(),
                response=mock_token_response,
            )

            with pytest.raises(httpx.HTTPStatusError):
                await oauth_client.refresh_token("expired-refresh-token")


@pytest.mark.asyncio
class TestUserInfo:
    """Test user info fetching."""

    async def test_get_user_info_success(self, oauth_client, mock_oidc_discovery):
        """Test successful user info fetch."""
        with patch.object(oauth_client._http_client, "get") as mock_get:
            # Mock OIDC discovery
            mock_discovery_response = MagicMock()
            mock_discovery_response.json.return_value = mock_oidc_discovery
            mock_discovery_response.raise_for_status = MagicMock()

            # Mock user info response
            mock_userinfo_response = MagicMock()
            mock_userinfo_response.json.return_value = {
                "sub": "user-123",
                "email": "user@example.com",
                "email_verified": True,
                "name": "Test User",
                "given_name": "Test",
                "family_name": "User",
                "preferred_username": "testuser",
            }
            mock_userinfo_response.raise_for_status = MagicMock()

            # Return different mocks for different URLs
            def get_side_effect(url, **kwargs):
                if "openid-configuration" in url:
                    return mock_discovery_response
                else:
                    return mock_userinfo_response

            mock_get.side_effect = get_side_effect

            # Get user info
            user_info = await oauth_client.get_user_info("test-access-token")

            # Verify user info
            assert isinstance(user_info, UserInfo)
            assert user_info.sub == "user-123"
            assert user_info.email == "user@example.com"
            assert user_info.name == "Test User"

            # Verify Bearer token was sent
            userinfo_call = [call for call in mock_get.call_args_list if "userinfo" in str(call)]
            assert len(userinfo_call) == 1
            assert userinfo_call[0][1]["headers"]["Authorization"] == "Bearer test-access-token"

    async def test_get_user_info_no_endpoint(self, oauth_client):
        """Test user info fetch when endpoint is not available."""
        # Create discovery without userinfo_endpoint
        mock_discovery = {
            "issuer": "http://keycloak:8080/realms/knowledge-mapper-dev",
            "authorization_endpoint": "http://keycloak:8080/realms/knowledge-mapper-dev/protocol/openid-connect/auth",
            "token_endpoint": "http://keycloak:8080/realms/knowledge-mapper-dev/protocol/openid-connect/token",
            "jwks_uri": "http://keycloak:8080/realms/knowledge-mapper-dev/protocol/openid-connect/certs",
        }

        with patch.object(oauth_client._http_client, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_discovery
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with pytest.raises(ValueError, match="No userinfo_endpoint"):
                await oauth_client.get_user_info("test-token")


@pytest.mark.asyncio
class TestClientLifecycle:
    """Test OAuth client lifecycle management."""

    async def test_client_close(self, oauth_client):
        """Test that client closes HTTP connection properly."""
        with patch.object(oauth_client._http_client, "aclose") as mock_close:
            await oauth_client.close()
            mock_close.assert_called_once()
