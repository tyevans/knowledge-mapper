"""Integration tests for OAuth client with real Keycloak."""
import pytest
import httpx

from app.services.oauth_client import OAuthClient
from app.schemas.oauth import OIDCDiscovery


@pytest.fixture
def keycloak_oauth_client():
    """Create OAuth client for Keycloak integration."""
    return OAuthClient(
        client_id="knowledge-mapper-backend",
        client_secret="your-client-secret",  # Would need real secret for full flow
        redirect_uri="http://localhost:8000/api/v1/auth/callback",
        issuer_url="http://localhost:8080/realms/knowledge-mapper-dev",
        scopes=["openid", "profile", "email"],
        use_pkce=True,
        http_timeout=10,
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestOAuthClientIntegration:
    """Integration tests with real Keycloak instance."""

    async def test_oidc_discovery_real_keycloak(self, keycloak_oauth_client):
        """Test OIDC discovery with real Keycloak instance."""
        try:
            # Discover endpoints
            config = await keycloak_oauth_client.discover_endpoints()

            # Verify discovered config
            assert isinstance(config, OIDCDiscovery)
            assert config.issuer == "http://localhost:8080/realms/knowledge-mapper-dev"
            assert "authorization_endpoint" in config.model_dump()
            assert "token_endpoint" in config.model_dump()
            assert "jwks_uri" in config.model_dump()

            # Verify endpoints are valid URLs
            assert config.authorization_endpoint.startswith("http://localhost:8080")
            assert config.token_endpoint.startswith("http://localhost:8080")
            assert config.jwks_uri.startswith("http://localhost:8080")

            print(f"\nOIDC Discovery successful!")
            print(f"Issuer: {config.issuer}")
            print(f"Authorization endpoint: {config.authorization_endpoint}")
            print(f"Token endpoint: {config.token_endpoint}")
            print(f"JWKS URI: {config.jwks_uri}")

        except httpx.HTTPError as e:
            pytest.skip(f"Keycloak not available: {e}")

    async def test_authorization_url_generation_real_keycloak(self, keycloak_oauth_client):
        """Test authorization URL generation with real Keycloak."""
        try:
            # Generate authorization URL
            url, state, challenge = await keycloak_oauth_client.get_authorization_url()

            # Verify URL structure
            assert url.startswith("http://localhost:8080/realms/knowledge-mapper-dev/protocol/openid-connect/auth")
            assert "response_type=code" in url
            assert "client_id=knowledge-mapper-backend" in url
            assert "redirect_uri=" in url
            assert f"state={state}" in url
            assert "code_challenge=" in url
            assert "code_challenge_method=S256" in url

            # Verify state and PKCE
            assert len(state) >= 32
            assert challenge is not None
            assert len(challenge.code_verifier) == 43
            assert len(challenge.code_challenge) == 43

            print(f"\nAuthorization URL generated successfully!")
            print(f"URL: {url[:100]}...")
            print(f"State: {state}")
            print(f"PKCE Challenge: {challenge.code_challenge}")

        except httpx.HTTPError as e:
            pytest.skip(f"Keycloak not available: {e}")

    async def test_pkce_challenge_validation(self, keycloak_oauth_client):
        """Test that PKCE challenge and verifier are correctly formatted."""
        challenge = keycloak_oauth_client.generate_pkce_challenge()

        # Verify PKCE structure
        assert len(challenge.code_verifier) == 43
        assert len(challenge.code_challenge) == 43
        assert challenge.code_challenge_method == "S256"

        # Verify it's URL-safe base64
        import base64
        try:
            # Should be decodable as base64url (with padding added)
            padded_verifier = challenge.code_verifier + "=" * (4 - len(challenge.code_verifier) % 4)
            base64.urlsafe_b64decode(padded_verifier)

            padded_challenge = challenge.code_challenge + "=" * (4 - len(challenge.code_challenge) % 4)
            base64.urlsafe_b64decode(padded_challenge)

            print(f"\nPKCE validation successful!")
            print(f"Verifier length: {len(challenge.code_verifier)}")
            print(f"Challenge length: {len(challenge.code_challenge)}")

        except Exception as e:
            pytest.fail(f"PKCE challenge not valid base64url: {e}")


@pytest.mark.asyncio
async def test_oauth_client_singleton():
    """Test that get_oauth_client returns singleton instance."""
    from app.services.oauth_client import get_oauth_client

    client1 = await get_oauth_client()
    client2 = await get_oauth_client()

    assert client1 is client2
    print("\nSingleton pattern working correctly!")
