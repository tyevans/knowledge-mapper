"""Unit tests for OAuth token validation dependency."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidSignatureError

from fastapi import HTTPException
from app.api.dependencies.auth import get_current_user
from app.schemas.auth import AuthenticatedUser
from app.core.config import settings


@pytest.fixture
def mock_jwks_client():
    """Mock JWKS client for testing."""
    client = AsyncMock()
    client.get_signing_key = AsyncMock()
    return client


@pytest.fixture
def mock_credentials():
    """Mock HTTP Bearer credentials."""
    credentials = MagicMock()
    credentials.credentials = "mock-token"
    return credentials


@pytest.fixture
def mock_request():
    """Mock FastAPI Request with client IP."""
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = "192.168.1.100"
    return request


@pytest.fixture
def mock_rate_limiter():
    """Mock rate limiter for testing."""
    limiter = AsyncMock()
    limiter.check_rate_limit = AsyncMock()
    return limiter


@pytest.fixture
def mock_token_revocation_service():
    """Mock token revocation service for testing."""
    service = AsyncMock()
    service.is_token_revoked = AsyncMock(return_value=False)
    service.revoke_token = AsyncMock()
    return service


@pytest.fixture
def mock_jwk():
    """Sample JWK for testing."""
    return {
        "kid": "test-key-1",
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": "test-modulus",
        "e": "AQAB",
    }


def generate_test_token(
    sub: str = "test-user-123",
    tenant_id: str = "550e8400-e29b-41d4-a716-446655440000",
    scopes: str = "statements/read statements/write",
    expired: bool = False,
    secret: str = "test-secret",
    include_kid: bool = True,
) -> str:
    """Generate a test JWT token."""
    exp_time = (
        datetime.utcnow() - timedelta(hours=1)
        if expired
        else datetime.utcnow() + timedelta(hours=1)
    )

    payload = {
        "sub": sub,
        "iss": settings.OAUTH_ISSUER_URL,
        "aud": settings.OAUTH_AUDIENCE,
        "exp": int(exp_time.timestamp()),
        "iat": int(datetime.utcnow().timestamp()),
        "jti": "test-jti-12345",
        "tenant_id": tenant_id,
        "scope": scopes,
        "email": "test@example.com",
        "name": "Test User",
    }

    headers = {"kid": "test-key-1"} if include_kid else {}

    return jwt.encode(payload, secret, algorithm="HS256", headers=headers)


@pytest.mark.asyncio
async def test_valid_token_success(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_jwk, mock_token_revocation_service):
    """Test successful token validation with all required claims."""
    # Generate valid token
    token = generate_test_token()
    mock_credentials.credentials = token

    # Mock JWKS client to return signing key
    mock_jwks_client.get_signing_key.return_value = mock_jwk

    # Mock get_unverified_jwt_header to return RS256 algorithm
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        # Mock jwt.decode to return valid payload
        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "test-user-123",
                "iss": settings.OAUTH_ISSUER_URL,
                "aud": settings.OAUTH_AUDIENCE,
                "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                "iat": int(datetime.utcnow().timestamp()),
                "jti": "test-jti-12345",
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "scope": "statements/read statements/write",
                "email": "test@example.com",
                "name": "Test User",
            }

            # Call dependency
            user = await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

        # Assertions
        assert isinstance(user, AuthenticatedUser)
        assert user.user_id == "test-user-123"
        assert user.tenant_id == "550e8400-e29b-41d4-a716-446655440000"
        assert user.scopes == ["statements/read", "statements/write"]
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.issuer == settings.OAUTH_ISSUER_URL


@pytest.mark.asyncio
async def test_missing_token_fails(mock_request, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service):
    """Test that missing Authorization header raises 401."""
    # No credentials provided
    credentials = None

    # Should raise HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(mock_request, credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["error"] == "missing_token"
    assert "Authorization header" in exc_info.value.detail["error_description"]


@pytest.mark.asyncio
async def test_expired_token_fails(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_jwk, mock_token_revocation_service):
    """Test that expired token raises 401 with expired_token error."""
    # Generate expired token
    token = generate_test_token(expired=True)
    mock_credentials.credentials = token

    mock_jwks_client.get_signing_key.return_value = mock_jwk

    # Mock get_unverified_jwt_header to return RS256 algorithm
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        # Mock jwt.decode to raise ExpiredSignatureError
        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            mock_decode.side_effect = ExpiredSignatureError("Token expired")

            # Should raise HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

            assert exc_info.value.status_code == 401
            assert exc_info.value.detail["error"] == "expired_token"
            assert "expired" in exc_info.value.detail["error_description"].lower()


@pytest.mark.asyncio
async def test_missing_tenant_id_fails(
    mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service, mock_jwk
):
    """Test that token without tenant_id raises 401."""
    token = generate_test_token(tenant_id=None)
    mock_credentials.credentials = token

    mock_jwks_client.get_signing_key.return_value = mock_jwk

    # Mock get_unverified_jwt_header to return RS256 algorithm
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        # Mock jwt.decode to return payload without tenant_id
        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "test-user-123",
                "iss": settings.OAUTH_ISSUER_URL,
                "aud": settings.OAUTH_AUDIENCE,
                "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                "iat": int(datetime.utcnow().timestamp()),
                "jti": "test-jti-12345",
                "tenant_id": None,  # Missing tenant_id
                "scope": "statements/read",
            }

            # Should raise HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

            assert exc_info.value.status_code == 401
            assert exc_info.value.detail["error"] == "invalid_token"
            assert "tenant_id" in exc_info.value.detail["error_description"]


@pytest.mark.asyncio
async def test_key_rotation_refresh(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_jwk, mock_token_revocation_service):
    """Test that missing signing key triggers JWKS refresh."""
    token = generate_test_token()
    mock_credentials.credentials = token

    # First call returns None (key not found), second call returns key (after refresh)
    mock_jwks_client.get_signing_key.side_effect = [None, mock_jwk]

    # Mock get_unverified_jwt_header to return RS256 algorithm
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "test-user-123",
                "iss": settings.OAUTH_ISSUER_URL,
                "aud": settings.OAUTH_AUDIENCE,
                "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                "iat": int(datetime.utcnow().timestamp()),
                "jti": "test-jti-12345",
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "scope": "statements/read",
            }

            # Call dependency
            user = await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

            # Should have called get_signing_key twice (once normal, once with force_refresh=True)
            assert mock_jwks_client.get_signing_key.call_count == 2

            # First call should be with force_refresh=False
            first_call = mock_jwks_client.get_signing_key.call_args_list[0]
            assert first_call[1]["force_refresh"] is False

            # Second call should be with force_refresh=True
            second_call = mock_jwks_client.get_signing_key.call_args_list[1]
            assert second_call[1]["force_refresh"] is True

            assert user.user_id == "test-user-123"


@pytest.mark.asyncio
async def test_invalid_signature_fails(
    mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_jwk
):
    """Test that invalid signature raises 401."""
    token = generate_test_token()
    mock_credentials.credentials = token

    mock_jwks_client.get_signing_key.return_value = mock_jwk

    # Mock get_unverified_jwt_header to return RS256 algorithm
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        # Mock jwt.decode to raise InvalidSignatureError
        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            mock_decode.side_effect = InvalidSignatureError(
                "Signature verification failed"
            )

            # Should raise HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

            assert exc_info.value.status_code == 401
            assert exc_info.value.detail["error"] == "invalid_token"
            assert "signature" in exc_info.value.detail["error_description"].lower()


@pytest.mark.asyncio
async def test_malformed_jwt_fails(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service):
    """Test that malformed JWT raises 401."""
    # Malformed token (not a valid JWT)
    mock_credentials.credentials = "not-a-valid-jwt-token"

    # Should raise HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["error"] == "invalid_token"
    assert "Malformed" in exc_info.value.detail["error_description"]


@pytest.mark.asyncio
async def test_missing_kid_in_header_fails(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service):
    """Test that JWT without kid in header raises 401."""
    # Generate token without kid in header
    token = generate_test_token(include_kid=False)
    mock_credentials.credentials = token

    # Mock get_unverified_jwt_header to return RS256 algorithm but no kid
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"alg": "RS256", "typ": "JWT"}  # No kid

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"] == "invalid_token"
        assert "kid" in exc_info.value.detail["error_description"]


@pytest.mark.asyncio
async def test_signing_key_not_found_after_refresh_fails(
    mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter
):
    """Test that signing key not found after refresh raises 401."""
    token = generate_test_token()
    mock_credentials.credentials = token

    # Both calls return None (key not found even after refresh)
    mock_jwks_client.get_signing_key.return_value = None

    # Mock get_unverified_jwt_header to return RS256 algorithm
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"] == "invalid_token"
        assert "Signing key not found" in exc_info.value.detail["error_description"]


@pytest.mark.asyncio
async def test_jwks_fetch_error_returns_503(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service):
    """Test that JWKS fetch failure raises 503."""
    token = generate_test_token()
    mock_credentials.credentials = token

    # Mock JWKS client to raise httpx.HTTPError
    import httpx

    mock_jwks_client.get_signing_key.side_effect = httpx.HTTPError(
        "Connection refused"
    )

    # Mock get_unverified_jwt_header to return RS256 algorithm
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        # Should raise HTTPException with 503
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["error"] == "service_unavailable"
        assert (
            "signing keys" in exc_info.value.detail["error_description"].lower()
        )


@pytest.mark.asyncio
async def test_scopes_parsing(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_jwk, mock_token_revocation_service):
    """Test that space-separated scopes are correctly parsed."""
    token = generate_test_token(scopes="read write admin")
    mock_credentials.credentials = token

    mock_jwks_client.get_signing_key.return_value = mock_jwk

    # Mock get_unverified_jwt_header to return RS256 algorithm
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "test-user-123",
                "iss": settings.OAUTH_ISSUER_URL,
                "aud": settings.OAUTH_AUDIENCE,
                "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                "iat": int(datetime.utcnow().timestamp()),
                "jti": "test-jti-12345",
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "scope": "read write admin",
            }

            user = await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

            assert user.scopes == ["read", "write", "admin"]
            assert user.has_scope("read")
            assert user.has_scope("write")
            assert user.has_scope("admin")
            assert not user.has_scope("delete")


@pytest.mark.asyncio
async def test_empty_scopes(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_jwk, mock_token_revocation_service):
    """Test that empty scopes are handled correctly."""
    token = generate_test_token(scopes="")
    mock_credentials.credentials = token

    mock_jwks_client.get_signing_key.return_value = mock_jwk

    # Mock get_unverified_jwt_header to return RS256 algorithm
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "test-user-123",
                "iss": settings.OAUTH_ISSUER_URL,
                "aud": settings.OAUTH_AUDIENCE,
                "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                "iat": int(datetime.utcnow().timestamp()),
                "jti": "test-jti-12345",
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "scope": "",
            }

            user = await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

            assert user.scopes == []
            assert not user.has_scope("read")


@pytest.mark.asyncio
async def test_no_scopes_claim(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_jwk, mock_token_revocation_service):
    """Test that missing scope claim defaults to empty list."""
    token = generate_test_token()
    mock_credentials.credentials = token

    mock_jwks_client.get_signing_key.return_value = mock_jwk

    # Mock get_unverified_jwt_header to return RS256 algorithm
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "test-user-123",
                "iss": settings.OAUTH_ISSUER_URL,
                "aud": settings.OAUTH_AUDIENCE,
                "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                "iat": int(datetime.utcnow().timestamp()),
                "jti": "test-jti-12345",
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                # No scope claim
            }

            user = await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

            assert user.scopes == []


@pytest.mark.asyncio
async def test_multiple_audiences(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_jwk, mock_token_revocation_service):
    """Test that tokens with multiple audiences are validated correctly."""
    token = generate_test_token()
    mock_credentials.credentials = token

    mock_jwks_client.get_signing_key.return_value = mock_jwk

    # Mock get_unverified_jwt_header to return RS256 algorithm
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "test-user-123",
                "iss": settings.OAUTH_ISSUER_URL,
                "aud": [
                    settings.OAUTH_AUDIENCE,
                    "another-audience",
                ],  # Multiple audiences
                "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                "iat": int(datetime.utcnow().timestamp()),
                "jti": "test-jti-12345",
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "scope": "read",
            }

            user = await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

            assert user.user_id == "test-user-123"
