"""
Unit tests for JWKS client.

Tests the JWKS client's ability to fetch, cache, and retrieve OAuth provider
public keys with proper error handling and multi-issuer support.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from app.services.jwks_client import JWKSClient


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock()
    return redis_mock


@pytest.fixture
def mock_jwks():
    """Sample JWKS response with multiple keys."""
    return {
        "keys": [
            {
                "kid": "test-key-1",
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "n": "test-modulus-1",
                "e": "AQAB",
            },
            {
                "kid": "test-key-2",
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "n": "test-modulus-2",
                "e": "AQAB",
            },
        ]
    }


@pytest.fixture
def mock_oidc_discovery():
    """Sample OIDC discovery response."""
    return {
        "issuer": "http://keycloak:8080/realms/knowledge-mapper-dev",
        "authorization_endpoint": "http://keycloak:8080/realms/knowledge-mapper-dev/protocol/openid-connect/auth",
        "token_endpoint": "http://keycloak:8080/realms/knowledge-mapper-dev/protocol/openid-connect/token",
        "jwks_uri": "http://keycloak:8080/realms/knowledge-mapper-dev/protocol/openid-connect/certs",
    }


@pytest.mark.asyncio
async def test_fetch_jwks_success(mock_redis, mock_jwks, mock_oidc_discovery):
    """Test successful JWKS fetch from provider."""
    client = JWKSClient(redis_client=mock_redis, cache_ttl=3600)

    with patch.object(client._http_client, "get") as mock_get:
        # Mock OIDC discovery response
        discovery_response = MagicMock()
        discovery_response.json.return_value = mock_oidc_discovery
        discovery_response.raise_for_status = MagicMock()

        # Mock JWKS response
        jwks_response = MagicMock()
        jwks_response.json.return_value = mock_jwks
        jwks_response.raise_for_status = MagicMock()

        mock_get.side_effect = [discovery_response, jwks_response]

        # Fetch JWKS
        result = await client.get_jwks("http://keycloak:8080/realms/knowledge-mapper-dev")

        # Assertions
        assert result == mock_jwks
        assert len(result["keys"]) == 2
        assert result["keys"][0]["kid"] == "test-key-1"
        assert result["keys"][1]["kid"] == "test-key-2"

        # Verify HTTP calls
        assert mock_get.call_count == 2
        mock_get.assert_any_call(
            "http://keycloak:8080/realms/knowledge-mapper-dev/.well-known/openid-configuration"
        )
        mock_get.assert_any_call(
            "http://keycloak:8080/realms/knowledge-mapper-dev/protocol/openid-connect/certs"
        )

        # Verify caching was attempted
        mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_jwks_cache_hit(mock_redis, mock_jwks):
    """Test JWKS cache hit - should not make HTTP request."""
    # Mock cache hit
    mock_redis.get = AsyncMock(return_value=json.dumps(mock_jwks))

    client = JWKSClient(redis_client=mock_redis, cache_ttl=3600)

    with patch.object(client._http_client, "get") as mock_get:
        # Fetch JWKS (should hit cache)
        result = await client.get_jwks("http://keycloak:8080/realms/knowledge-mapper-dev")

        # Assertions
        assert result == mock_jwks
        mock_get.assert_not_called()  # Should not make HTTP request
        mock_redis.get.assert_called_once_with("jwks:http://keycloak:8080/realms/knowledge-mapper-dev")


@pytest.mark.asyncio
async def test_jwks_cache_miss(mock_redis, mock_jwks, mock_oidc_discovery):
    """Test JWKS cache miss - should fetch from provider and cache result."""
    # Mock cache miss
    mock_redis.get = AsyncMock(return_value=None)

    client = JWKSClient(redis_client=mock_redis, cache_ttl=3600)

    with patch.object(client._http_client, "get") as mock_get:
        discovery_response = MagicMock()
        discovery_response.json.return_value = mock_oidc_discovery
        discovery_response.raise_for_status = MagicMock()

        jwks_response = MagicMock()
        jwks_response.json.return_value = mock_jwks
        jwks_response.raise_for_status = MagicMock()

        mock_get.side_effect = [discovery_response, jwks_response]

        # Fetch JWKS
        result = await client.get_jwks("http://keycloak:8080/realms/knowledge-mapper-dev")

        # Assertions
        assert result == mock_jwks
        mock_redis.get.assert_called_once()
        mock_get.assert_called()  # Should make HTTP request
        mock_redis.setex.assert_called_once_with(
            "jwks:http://keycloak:8080/realms/knowledge-mapper-dev",
            3600,
            json.dumps(mock_jwks),
        )


@pytest.mark.asyncio
async def test_force_refresh_bypasses_cache(mock_redis, mock_jwks, mock_oidc_discovery):
    """Test force_refresh=True bypasses cache even if cached value exists."""
    # Mock cache hit (but should be bypassed)
    mock_redis.get = AsyncMock(return_value=json.dumps(mock_jwks))

    client = JWKSClient(redis_client=mock_redis, cache_ttl=3600)

    with patch.object(client._http_client, "get") as mock_get:
        discovery_response = MagicMock()
        discovery_response.json.return_value = mock_oidc_discovery
        discovery_response.raise_for_status = MagicMock()

        jwks_response = MagicMock()
        jwks_response.json.return_value = mock_jwks
        jwks_response.raise_for_status = MagicMock()

        mock_get.side_effect = [discovery_response, jwks_response]

        # Fetch JWKS with force_refresh
        result = await client.get_jwks(
            "http://keycloak:8080/realms/knowledge-mapper-dev", force_refresh=True
        )

        # Assertions
        assert result == mock_jwks
        mock_redis.get.assert_not_called()  # Should NOT check cache
        mock_get.assert_called()  # Should make HTTP request
        mock_redis.setex.assert_called_once()  # Should cache the fresh result


@pytest.mark.asyncio
async def test_get_signing_key_found(mock_redis, mock_jwks):
    """Test getting a specific signing key by kid - key exists."""
    mock_redis.get = AsyncMock(return_value=json.dumps(mock_jwks))

    client = JWKSClient(redis_client=mock_redis, cache_ttl=3600)

    # Get first key
    key = await client.get_signing_key(
        "http://keycloak:8080/realms/knowledge-mapper-dev", "test-key-1"
    )

    assert key is not None
    assert key["kid"] == "test-key-1"
    assert key["alg"] == "RS256"
    assert key["kty"] == "RSA"

    # Get second key
    key2 = await client.get_signing_key(
        "http://keycloak:8080/realms/knowledge-mapper-dev", "test-key-2"
    )

    assert key2 is not None
    assert key2["kid"] == "test-key-2"


@pytest.mark.asyncio
async def test_get_signing_key_not_found(mock_redis, mock_jwks):
    """Test getting a signing key that doesn't exist - should return None."""
    mock_redis.get = AsyncMock(return_value=json.dumps(mock_jwks))

    client = JWKSClient(redis_client=mock_redis, cache_ttl=3600)

    key = await client.get_signing_key(
        "http://keycloak:8080/realms/knowledge-mapper-dev", "nonexistent-key"
    )

    assert key is None


@pytest.mark.asyncio
async def test_redis_failure_graceful(mock_redis, mock_jwks, mock_oidc_discovery):
    """Test JWKS client works even when Redis fails - should fetch from provider."""
    # Simulate Redis failure
    import redis as redis_module

    mock_redis.get = AsyncMock(side_effect=redis_module.RedisError("Redis connection failed"))
    mock_redis.setex = AsyncMock(side_effect=redis_module.RedisError("Redis connection failed"))

    client = JWKSClient(redis_client=mock_redis, cache_ttl=3600)

    with patch.object(client._http_client, "get") as mock_get:
        discovery_response = MagicMock()
        discovery_response.json.return_value = mock_oidc_discovery
        discovery_response.raise_for_status = MagicMock()

        jwks_response = MagicMock()
        jwks_response.json.return_value = mock_jwks
        jwks_response.raise_for_status = MagicMock()

        mock_get.side_effect = [discovery_response, jwks_response]

        # Should still fetch JWKS despite Redis failure
        result = await client.get_jwks("http://keycloak:8080/realms/knowledge-mapper-dev")

        assert result == mock_jwks
        mock_get.assert_called()  # Should make HTTP request


@pytest.mark.asyncio
async def test_oidc_discovery_failure(mock_redis):
    """Test handling of OIDC discovery endpoint failure."""
    import httpx

    client = JWKSClient(redis_client=mock_redis, cache_ttl=3600)

    with patch.object(client._http_client, "get") as mock_get:
        # Simulate discovery endpoint failure
        mock_get.side_effect = httpx.HTTPStatusError(
            "404 Not Found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )

        # Should raise HTTPError
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_jwks("http://invalid-issuer.example.com")


@pytest.mark.asyncio
async def test_invalid_jwks_format(mock_redis, mock_oidc_discovery):
    """Test handling of invalid JWKS format (missing 'keys' field)."""
    client = JWKSClient(redis_client=mock_redis, cache_ttl=3600)

    with patch.object(client._http_client, "get") as mock_get:
        discovery_response = MagicMock()
        discovery_response.json.return_value = mock_oidc_discovery
        discovery_response.raise_for_status = MagicMock()

        # Invalid JWKS (missing 'keys' field)
        jwks_response = MagicMock()
        jwks_response.json.return_value = {"invalid": "format"}
        jwks_response.raise_for_status = MagicMock()

        mock_get.side_effect = [discovery_response, jwks_response]

        # Should raise ValueError
        with pytest.raises(ValueError, match="Invalid JWKS format"):
            await client.get_jwks("http://keycloak:8080/realms/knowledge-mapper-dev")


@pytest.mark.asyncio
async def test_missing_jwks_uri_in_discovery(mock_redis):
    """Test handling of missing jwks_uri in OIDC discovery response."""
    client = JWKSClient(redis_client=mock_redis, cache_ttl=3600)

    with patch.object(client._http_client, "get") as mock_get:
        # Discovery response missing jwks_uri
        discovery_response = MagicMock()
        discovery_response.json.return_value = {"issuer": "http://example.com"}
        discovery_response.raise_for_status = MagicMock()

        mock_get.return_value = discovery_response

        # Should raise ValueError
        with pytest.raises(ValueError, match="No jwks_uri in OIDC discovery"):
            await client.get_jwks("http://example.com")


@pytest.mark.asyncio
async def test_multi_issuer_support(mock_redis, mock_jwks, mock_oidc_discovery):
    """Test that different issuers are cached separately."""
    client = JWKSClient(redis_client=mock_redis, cache_ttl=3600)

    issuer1 = "http://keycloak:8080/realms/knowledge-mapper-dev"
    issuer2 = "http://keycloak:8080/realms/other-tenant"

    jwks1 = {"keys": [{"kid": "key-issuer1", "kty": "RSA"}]}
    jwks2 = {"keys": [{"kid": "key-issuer2", "kty": "RSA"}]}

    with patch.object(client._http_client, "get") as mock_get:
        # Mock responses for issuer1
        discovery1 = MagicMock()
        discovery1.json.return_value = {
            **mock_oidc_discovery,
            "issuer": issuer1,
            "jwks_uri": f"{issuer1}/protocol/openid-connect/certs",
        }
        discovery1.raise_for_status = MagicMock()

        jwks_response1 = MagicMock()
        jwks_response1.json.return_value = jwks1
        jwks_response1.raise_for_status = MagicMock()

        # Mock responses for issuer2
        discovery2 = MagicMock()
        discovery2.json.return_value = {
            **mock_oidc_discovery,
            "issuer": issuer2,
            "jwks_uri": f"{issuer2}/protocol/openid-connect/certs",
        }
        discovery2.raise_for_status = MagicMock()

        jwks_response2 = MagicMock()
        jwks_response2.json.return_value = jwks2
        jwks_response2.raise_for_status = MagicMock()

        # Fetch from both issuers
        mock_get.side_effect = [discovery1, jwks_response1]
        result1 = await client.get_jwks(issuer1)

        mock_get.side_effect = [discovery2, jwks_response2]
        result2 = await client.get_jwks(issuer2)

        # Assertions
        assert result1 != result2
        assert result1["keys"][0]["kid"] == "key-issuer1"
        assert result2["keys"][0]["kid"] == "key-issuer2"

        # Verify both were cached with different keys
        assert mock_redis.setex.call_count == 2
        call_args_list = [call[0] for call in mock_redis.setex.call_args_list]
        assert any(f"jwks:{issuer1}" in str(args) for args in call_args_list)
        assert any(f"jwks:{issuer2}" in str(args) for args in call_args_list)


@pytest.mark.asyncio
async def test_invalid_json_in_cache(mock_redis, mock_jwks, mock_oidc_discovery):
    """Test handling of corrupted JSON in Redis cache."""
    # Mock cache returning invalid JSON
    mock_redis.get = AsyncMock(return_value="invalid json {{{")

    client = JWKSClient(redis_client=mock_redis, cache_ttl=3600)

    with patch.object(client._http_client, "get") as mock_get:
        discovery_response = MagicMock()
        discovery_response.json.return_value = mock_oidc_discovery
        discovery_response.raise_for_status = MagicMock()

        jwks_response = MagicMock()
        jwks_response.json.return_value = mock_jwks
        jwks_response.raise_for_status = MagicMock()

        mock_get.side_effect = [discovery_response, jwks_response]

        # Should gracefully fall back to fetching from provider
        result = await client.get_jwks("http://keycloak:8080/realms/knowledge-mapper-dev")

        assert result == mock_jwks
        mock_get.assert_called()  # Should make HTTP request


@pytest.mark.asyncio
async def test_close_cleanup(mock_redis):
    """Test that close() properly cleans up HTTP client."""
    client = JWKSClient(redis_client=mock_redis, cache_ttl=3600)

    with patch.object(client._http_client, "aclose") as mock_close:
        await client.close()
        mock_close.assert_called_once()
