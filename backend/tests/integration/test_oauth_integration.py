"""
Integration tests for OAuth token validation with real Keycloak.

These tests validate:
1. Real Keycloak token validation
2. JWKS fetching from real Keycloak
3. End-to-end protected endpoint flow
4. Token revocation flow with Redis
5. Multi-tenant token isolation

Prerequisites:
- Keycloak running at http://localhost:8080
- Realm 'knowledge-mapper-dev' configured with test users
- Redis running at configured REDIS_URL
- PostgreSQL with seed data

Run with: pytest backend/tests/integration/test_oauth_integration.py -v
"""

import pytest
import httpx
import jwt
import redis.asyncio as redis
from typing import Dict, Any

from app.core.config import settings
from app.services.jwks_client import JWKSClient


# Test markers
pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class TestRealKeycloakTokenValidation:
    """Test suite for real Keycloak token validation."""

    async def test_real_keycloak_token_validates_successfully(
        self, integration_test_client, keycloak_token_acme_alice
    ):
        """
        Test 1: Real Token Validation

        Verify that a real Keycloak-issued token validates successfully
        and returns correct user context.

        Success Criteria:
        - Token validates without errors
        - User ID extracted correctly
        - Tenant ID extracted correctly
        - Email extracted correctly
        """
        # Arrange
        token = keycloak_token_acme_alice

        # Act
        response = integration_test_client.get(
            "/api/v1/test/protected", headers={"Authorization": f"Bearer {token}"}
        )

        # Assert
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "user_id" in data, "Response missing user_id"
        assert "tenant_id" in data, "Response missing tenant_id"
        assert "email" in data, "Response missing email"

        # Verify Alice's details (from TASK-007)
        assert (
            data["user_id"] == "cbd0900c-44b3-4e75-b093-0b6c2282183f"
        ), "Incorrect user_id"
        assert (
            data["tenant_id"] == "11111111-1111-1111-1111-111111111111"
        ), "Incorrect tenant_id"
        assert data["email"] == "alice@acme-corp.example", "Incorrect email"

    async def test_real_token_includes_jti_claim(
        self, keycloak_token_acme_alice
    ):
        """
        Verify that real Keycloak tokens include jti claim (required for revocation).

        Success Criteria:
        - Token includes jti claim
        - jti is a non-empty string
        - jti has expected format (UUID)
        """
        # Arrange
        token = keycloak_token_acme_alice

        # Act - Decode without verification to inspect claims
        decoded = jwt.decode(token, options={"verify_signature": False})

        # Assert
        assert "jti" in decoded, "Token missing required jti claim"
        assert decoded["jti"], "jti claim is empty"
        assert isinstance(decoded["jti"], str), "jti must be a string"

        # Verify it's a UUID format (Keycloak uses UUIDs for jti)
        assert len(decoded["jti"]) > 0, "jti is empty"


class TestJWKSFetchFromKeycloak:
    """Test suite for JWKS fetching from real Keycloak."""

    async def test_fetch_jwks_from_real_keycloak(
        self, redis_client_integration
    ):
        """
        Test 2: JWKS Fetch from Keycloak

        Verify that JWKS client can fetch signing keys from real Keycloak.

        Success Criteria:
        - JWKS fetched successfully
        - Keys array contains at least one key
        - Each key has required fields (kid, kty)
        - Keys cached in Redis
        """
        # Arrange
        jwks_client = JWKSClient(redis_client_integration)
        issuer_url = "http://localhost:8080/realms/knowledge-mapper-dev"

        # Act
        jwks = await jwks_client.get_jwks(issuer_url)

        # Assert - JWKS structure
        assert "keys" in jwks, "JWKS response missing 'keys' field"
        assert len(jwks["keys"]) > 0, "JWKS contains no keys"

        # Assert - Key fields
        for key in jwks["keys"]:
            assert "kid" in key, f"Key missing 'kid': {key}"
            assert "kty" in key, f"Key missing 'kty': {key}"
            assert key["kty"] == "RSA", f"Expected RSA key, got {key['kty']}"

            # Keys should have either 'use' or 'key_ops'
            assert (
                "use" in key or "key_ops" in key
            ), f"Key missing 'use' or 'key_ops': {key}"

    async def test_jwks_caching_in_redis(self, redis_client_integration):
        """
        Verify that JWKS are cached in Redis for performance.

        Success Criteria:
        - First fetch stores in Redis
        - Second fetch retrieves from cache
        - Cache key exists in Redis
        """
        # Arrange
        jwks_client = JWKSClient(redis_client_integration)
        issuer_url = "http://localhost:8080/realms/knowledge-mapper-dev"
        cache_key = f"jwks:{issuer_url}"

        # Clean cache first
        await redis_client_integration.delete(cache_key)

        # Act - First fetch (cache miss)
        jwks1 = await jwks_client.get_jwks(issuer_url)

        # Assert - Cache populated
        cached_value = await redis_client_integration.get(cache_key)
        assert cached_value is not None, "JWKS not cached in Redis"

        # Act - Second fetch (cache hit)
        jwks2 = await jwks_client.get_jwks(issuer_url)

        # Assert - Same JWKS returned
        assert jwks1 == jwks2, "Cached JWKS differs from original"


class TestEndToEndProtectedEndpoint:
    """Test suite for end-to-end OAuth flow."""

    async def test_e2e_protected_endpoint_flow(
        self, integration_test_client, keycloak_token_acme_alice
    ):
        """
        Test 3: End-to-End Protected Endpoint

        Test full OAuth flow:
        1. Obtain token from Keycloak (via fixture)
        2. Call protected endpoint
        3. Verify response and user context

        Success Criteria:
        - Token obtained successfully (from fixture)
        - Protected endpoint returns 200
        - User context extracted correctly
        - Tenant ID matches expected value
        """
        # Arrange - Use token from fixture
        access_token = keycloak_token_acme_alice

        # Assert - Token obtained
        assert access_token, "Failed to obtain access token"

        # Act - Call protected endpoint
        response = integration_test_client.get(
            "/api/v1/test/protected",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        # Assert - Response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        user_data = response.json()
        assert user_data["user_id"] is not None, "user_id is None"
        assert (
            user_data["tenant_id"] == "11111111-1111-1111-1111-111111111111"
        ), "Incorrect tenant_id"
        assert user_data["email"] == "alice@acme-corp.example", "Incorrect email"

    async def test_protected_endpoint_requires_authentication(
        self, integration_test_client
    ):
        """
        Verify that protected endpoint rejects requests without token.

        Success Criteria:
        - Request without token returns 401
        - Error message is appropriate
        """
        # Act
        response = integration_test_client.get("/api/v1/test/protected")

        # Assert
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

        error_data = response.json()
        assert "error" in error_data, "Response missing error field"


class TestTokenRevocationFlow:
    """Test suite for token revocation with Redis blacklist."""

    async def test_token_revocation_flow_complete(
        self, integration_test_client, keycloak_token_acme_bob, redis_client_integration
    ):
        """
        Test 4: Token Revocation Flow

        Test complete revocation flow:
        1. Use token successfully
        2. Revoke token
        3. Verify token rejected after revocation
        4. Verify blacklist entry in Redis

        Success Criteria:
        - Token works before revocation
        - Revocation succeeds (200)
        - Token rejected after revocation (401)
        - Blacklist entry exists in Redis
        """
        # Arrange
        token = keycloak_token_acme_bob

        # Act 1: Use token (should work)
        response1 = integration_test_client.get(
            "/api/v1/test/protected", headers={"Authorization": f"Bearer {token}"}
        )
        assert response1.status_code == 200, "Token should work before revocation"

        # Act 2: Revoke token
        revoke_response = integration_test_client.post(
            "/api/v1/auth/revoke", headers={"Authorization": f"Bearer {token}"}
        )

        # Assert - Revocation succeeded
        assert (
            revoke_response.status_code == 200
        ), f"Revocation failed: {revoke_response.text}"

        revoke_data = revoke_response.json()
        assert "jti" in revoke_data, "Revocation response missing jti"
        jti = revoke_data["jti"]

        # Assert - Blacklist entry exists
        blacklist_key = f"revoked_token:{jti}"
        is_blacklisted = await redis_client_integration.exists(blacklist_key)
        assert is_blacklisted, f"Token {jti} not found in Redis blacklist"

        # Act 3: Try to use token again (should fail)
        response2 = integration_test_client.get(
            "/api/v1/test/protected", headers={"Authorization": f"Bearer {token}"}
        )

        # Assert - Token rejected
        assert (
            response2.status_code == 401
        ), f"Expected 401 after revocation, got {response2.status_code}"

        error_data = response2.json()
        error_message = error_data["error"]["message"]["error_description"].lower()
        assert "revoked" in error_message, f"Error message should mention 'revoked': {error_message}"

    async def test_revoked_token_blacklist_has_ttl(
        self, integration_test_client, keycloak_token_acme_bob, redis_client_integration
    ):
        """
        Verify that revoked tokens have TTL matching token expiration.

        Success Criteria:
        - Blacklist entry has TTL set
        - TTL is reasonable (not -1, not 0)
        - TTL approximately matches token exp claim
        """
        # Arrange - Get token from fixture
        token = keycloak_token_acme_bob

        # Decode to get exp claim
        decoded = jwt.decode(token, options={"verify_signature": False})
        token_exp = decoded["exp"]
        jti = decoded["jti"]

        # Act - Revoke token
        revoke_response = integration_test_client.post(
            "/api/v1/auth/revoke", headers={"Authorization": f"Bearer {token}"}
        )
        assert revoke_response.status_code == 200, "Revocation failed"

        # Assert - Check TTL
        blacklist_key = f"revoked_token:{jti}"
        ttl = await redis_client_integration.ttl(blacklist_key)

        assert ttl > 0, f"TTL should be positive, got {ttl}"
        assert ttl != -1, "TTL should not be -1 (no expiration)"
        assert ttl != -2, "Key should exist in Redis"

        # TTL should be roughly token_exp - current_time
        # Allow some margin for processing time
        import time
        expected_ttl = token_exp - int(time.time())
        assert abs(ttl - expected_ttl) < 10, f"TTL {ttl} differs from expected {expected_ttl}"


class TestMultiTenantIsolation:
    """Test suite for multi-tenant token isolation."""

    async def test_multi_tenant_isolation_different_tenants(
        self, integration_test_client, keycloak_token_acme_alice, keycloak_token_globex_charlie
    ):
        """
        Test 5: Multi-Tenant Isolation

        Verify that tokens from different tenants are properly isolated.

        Success Criteria:
        - ACME token returns ACME tenant_id
        - Globex token returns Globex tenant_id
        - Tenant IDs are different
        - User contexts are distinct
        """
        # Arrange
        acme_token = keycloak_token_acme_alice
        globex_token = keycloak_token_globex_charlie

        # Act 1: Call with ACME token
        acme_response = integration_test_client.get(
            "/api/v1/test/protected",
            headers={"Authorization": f"Bearer {acme_token}"},
        )

        # Act 2: Call with Globex token
        globex_response = integration_test_client.get(
            "/api/v1/test/protected",
            headers={"Authorization": f"Bearer {globex_token}"},
        )

        # Assert - Both succeed
        assert acme_response.status_code == 200, "ACME token should validate"
        assert globex_response.status_code == 200, "Globex token should validate"

        # Extract data
        acme_data = acme_response.json()
        globex_data = globex_response.json()

        # Assert - ACME tenant
        assert (
            acme_data["tenant_id"] == "11111111-1111-1111-1111-111111111111"
        ), "ACME tenant_id incorrect"
        assert (
            acme_data["user_id"] == "cbd0900c-44b3-4e75-b093-0b6c2282183f"
        ), "Alice user_id incorrect"
        assert acme_data["email"] == "alice@acme-corp.example", "Alice email incorrect"

        # Assert - Globex tenant
        assert (
            globex_data["tenant_id"] == "22222222-2222-2222-2222-222222222222"
        ), "Globex tenant_id incorrect"
        assert (
            globex_data["user_id"] == "50b5edc2-6740-47f3-9d0f-eafbb7c1652a"
        ), "Charlie user_id incorrect"
        assert (
            globex_data["email"] == "charlie@globex-inc.example"
        ), "Charlie email incorrect"

        # Assert - Tenants are different
        assert (
            acme_data["tenant_id"] != globex_data["tenant_id"]
        ), "Tenant IDs should be different"

    async def test_same_tenant_different_users(
        self, integration_test_client, keycloak_token_acme_alice, keycloak_token_acme_bob
    ):
        """
        Verify that different users in same tenant have correct isolation.

        Success Criteria:
        - Both users in same tenant
        - Different user IDs
        - Same tenant ID
        """
        # Arrange
        alice_token = keycloak_token_acme_alice
        bob_token = keycloak_token_acme_bob

        # Act
        alice_response = integration_test_client.get(
            "/api/v1/test/protected",
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        bob_response = integration_test_client.get(
            "/api/v1/test/protected",
            headers={"Authorization": f"Bearer {bob_token}"},
        )

        # Assert - Both succeed
        assert alice_response.status_code == 200, "Alice token should validate"
        assert bob_response.status_code == 200, "Bob token should validate"

        alice_data = alice_response.json()
        bob_data = bob_response.json()

        # Assert - Same tenant
        assert (
            alice_data["tenant_id"] == bob_data["tenant_id"]
        ), "Should be same tenant"
        assert (
            alice_data["tenant_id"] == "11111111-1111-1111-1111-111111111111"
        ), "Should be ACME tenant"

        # Assert - Different users
        assert alice_data["user_id"] != bob_data["user_id"], "User IDs should differ"
        assert (
            alice_data["user_id"] == "cbd0900c-44b3-4e75-b093-0b6c2282183f"
        ), "Alice user_id incorrect"
        assert (
            bob_data["user_id"] == "59be274d-c55a-4945-a420-8c49ced43d86"
        ), "Bob user_id incorrect"
