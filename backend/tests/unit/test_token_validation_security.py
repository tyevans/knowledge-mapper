"""Unit tests for OAuth token validation security hardening (TASK-009B)."""
import base64
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

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


# ============================================================================
# SECURITY TEST 1: Algorithm Confusion Attack Prevention
# ============================================================================

@pytest.mark.asyncio
async def test_algorithm_none_rejected(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service):
    """
    SECURITY: Test that tokens with alg: 'none' are rejected.

    Attack scenario: Attacker creates token with alg: "none" to bypass signature verification.
    Expected behavior: Token rejected before signature check with "Unsupported JWT algorithm" error.
    """
    # Create token payload
    payload = {
        "sub": "test-user-123",
        "iss": settings.OAUTH_ISSUER_URL,
        "aud": settings.OAUTH_AUDIENCE,
        "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
        "iat": int(datetime.utcnow().timestamp()),
        "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "jti": "test-jti-12345",
    }

    # Create token with alg: none (no signature)
    header_data = json.dumps({"alg": "none", "typ": "JWT"}).encode()
    header = base64.urlsafe_b64encode(header_data).decode().rstrip("=")

    payload_data = json.dumps(payload).encode()
    payload_encoded = base64.urlsafe_b64encode(payload_data).decode().rstrip("=")

    token = f"{header}.{payload_encoded}."
    mock_credentials.credentials = token

    # Mock get_unverified_jwt_header to return the actual header with alg: none
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"alg": "none", "typ": "JWT"}  # No kid since alg is none

        # Should raise HTTPException before signature verification
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

        # Verify error response
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"] == "invalid_token"
        assert "algorithm" in exc_info.value.detail["error_description"].lower()


@pytest.mark.asyncio
async def test_hmac_algorithm_rejected(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service):
    """
    SECURITY: Test that HMAC algorithms (HS256, HS384, HS512) are rejected.

    Attack scenario: Attacker obtains RSA public key from JWKS, creates HMAC token using
    public key as symmetric secret. If server accepts HS256, token validates successfully.
    Expected behavior: Symmetric algorithms rejected with error.
    """
    # Generate token with HS256 algorithm
    token = jwt.encode(
        {
            "sub": "test-user-123",
            "iss": settings.OAUTH_ISSUER_URL,
            "aud": settings.OAUTH_AUDIENCE,
            "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.utcnow().timestamp()),
            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "jti": "test-jti-12345",
        },
        "public-key-as-secret",
        algorithm="HS256",
        headers={"kid": "test-key-1"}
    )
    mock_credentials.credentials = token

    # Mock get_unverified_jwt_header to return HS256 algorithm
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"alg": "HS256", "typ": "JWT", "kid": "test-key-1"}

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"] == "invalid_token"
        # HS256 will be caught by either "not in OAUTH_ALGORITHMS" or "asymmetric" check
        error_desc = exc_info.value.detail["error_description"].lower()
        assert "algorithm" in error_desc  # Generic check that algorithm validation failed


@pytest.mark.asyncio
async def test_unsupported_algorithm_rejected(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service):
    """
    SECURITY: Test that algorithms not in OAUTH_ALGORITHMS config are rejected.

    Expected behavior: Only algorithms specified in settings.OAUTH_ALGORITHMS are accepted.
    """
    token = "mock-token"
    mock_credentials.credentials = token

    # Mock get_unverified_jwt_header to return ES512 (not in default config)
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"alg": "ES512", "typ": "JWT", "kid": "test-key-1"}

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"] == "invalid_token"
        assert "algorithm" in exc_info.value.detail["error_description"].lower()


# ============================================================================
# SECURITY TEST 2: Information Disclosure Prevention
# ============================================================================

@pytest.mark.asyncio
async def test_error_messages_no_information_disclosure(
    mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_jwk
):
    """
    SECURITY: Test that error messages don't leak sensitive information.

    Attack scenario: Attacker sends malformed tokens and analyzes error messages to learn
    about expected audience, issuer, claim requirements, etc.
    Expected behavior: Generic error messages returned to client, detailed logs server-side only.
    """
    token = "mock-token"
    mock_credentials.credentials = token

    mock_jwks_client.get_signing_key.return_value = mock_jwk

    # Test various JWT validation errors
    test_cases = [
        (
            jwt.exceptions.InvalidAudienceError("Audience doesn't match"),
            "invalid_token",
            "JWT validation failed"
        ),
        (
            jwt.exceptions.InvalidIssuerError("Invalid issuer"),
            "invalid_token",
            "JWT validation failed"
        ),
        (
            jwt.exceptions.ImmatureSignatureError("Token used before issued"),
            "invalid_token",
            "JWT validation failed"
        ),
    ]

    for exception, expected_error, expected_description in test_cases:
        with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
            mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

            with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
                mock_decode.side_effect = exception

                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

                error_desc = exc_info.value.detail["error_description"]

                # Error message should be generic
                assert error_desc == expected_description

                # Should NOT contain specific details that could help attackers
                assert "audience" not in error_desc.lower() or error_desc == expected_description
                assert "issuer" not in error_desc.lower() or error_desc == expected_description
                assert "expected" not in error_desc.lower()
                assert "got" not in error_desc.lower()


# ============================================================================
# SECURITY TEST 3: Tenant ID Validation
# ============================================================================

@pytest.mark.asyncio
async def test_tenant_id_must_be_valid_uuid(
    mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service, mock_jwk
):
    """
    SECURITY: Test that tenant_id must be a valid UUID format.

    Attack scenarios: SQL injection, path traversal, XSS, NoSQL injection through tenant_id.
    Expected behavior: Non-UUID tenant_id values rejected.
    """
    invalid_tenant_ids = [
        "not-a-uuid",  # Invalid format
        "123",  # Too short
        "../../etc/passwd",  # Path traversal attempt
        "' OR '1'='1",  # SQL injection attempt
        "<script>alert('xss')</script>",  # XSS attempt
        "550e8400-INVALID-UUID",  # Malformed UUID
        "{'$ne': null}",  # NoSQL injection attempt
        "550e8400-e29b-41d4-a716-446655440000'; DROP TABLE users; --",  # SQL injection with UUID prefix
    ]

    for invalid_tenant_id in invalid_tenant_ids:
        token = "mock-token"
        mock_credentials.credentials = token

        mock_jwks_client.get_signing_key.return_value = mock_jwk

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
                    "tenant_id": invalid_tenant_id,
                }

                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

                assert exc_info.value.status_code == 401
                assert exc_info.value.detail["error"] == "invalid_token"
                assert "tenant_id" in exc_info.value.detail["error_description"].lower()


@pytest.mark.asyncio
async def test_tenant_id_uuid_normalization(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service, mock_jwk):
    """
    SECURITY: Test that tenant_id UUID is normalized to lowercase.

    This prevents case-based attacks and ensures consistent database queries.
    """
    token = "mock-token"
    mock_credentials.credentials = token

    mock_jwks_client.get_signing_key.return_value = mock_jwk

    # UUID with mixed case
    mixed_case_uuid = "550E8400-E29B-41D4-A716-446655440000"

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
                "tenant_id": mixed_case_uuid,
                "scope": "read",
            }

            user = await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

            # Tenant ID should be normalized to lowercase
            assert user.tenant_id == mixed_case_uuid.lower()
            assert user.tenant_id == "550e8400-e29b-41d4-a716-446655440000"


# ============================================================================
# SECURITY TEST 4: Claims Validation (iat check)
# ============================================================================

@pytest.mark.asyncio
async def test_future_iat_rejected(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_jwk):
    """
    SECURITY: Test that tokens with iat (issued-at) in the future are rejected.

    Attack scenario: Attacker creates token with future iat to bypass rate limiting
    or access controls based on token age.
    Expected behavior: Token with future iat rejected by PyJWT.
    """
    token = "mock-token"
    mock_credentials.credentials = token

    mock_jwks_client.get_signing_key.return_value = mock_jwk

    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            # Simulate PyJWT rejecting future iat
            mock_decode.side_effect = jwt.exceptions.ImmatureSignatureError(
                "The token is not yet valid (iat)"
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

            assert exc_info.value.status_code == 401
            assert exc_info.value.detail["error"] == "invalid_token"
            # Error message should be generic (no information disclosure)
            assert exc_info.value.detail["error_description"] == "JWT validation failed"


# ============================================================================
# SECURITY TEST 5: Valid Security Scenarios (Positive Tests)
# ============================================================================

@pytest.mark.asyncio
async def test_valid_token_with_all_security_checks(
    mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service, mock_jwk
):
    """
    SECURITY: Test that valid token passes all security checks.

    This verifies that security hardening doesn't break legitimate authentication.
    """
    token = "mock-token"
    mock_credentials.credentials = token

    mock_jwks_client.get_signing_key.return_value = mock_jwk

    # Valid UUID tenant_id (lowercase)
    valid_tenant_id = "550e8400-e29b-41d4-a716-446655440000"

    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        # Valid RS256 algorithm
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "test-user-123",
                "iss": settings.OAUTH_ISSUER_URL,
                "aud": settings.OAUTH_AUDIENCE,
                "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                "iat": int(datetime.utcnow().timestamp()),
                "jti": "test-jti-12345",
                "tenant_id": valid_tenant_id,
                "scope": "read write",
                "email": "test@example.com",
                "name": "Test User",
            }

            user = await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)

            # All validations passed
            assert isinstance(user, AuthenticatedUser)
            assert user.user_id == "test-user-123"
            assert user.tenant_id == valid_tenant_id
            assert user.scopes == ["read", "write"]
            assert user.email == "test@example.com"
            assert user.name == "Test User"


@pytest.mark.asyncio
async def test_multiple_asymmetric_algorithms_accepted(mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service, mock_jwk):
    """
    SECURITY: Test that various asymmetric algorithms (RS256, RS384, RS512, ES256) are accepted.

    This ensures we don't block legitimate algorithms while preventing HMAC attacks.
    """
    asymmetric_algorithms = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]

    for algorithm in asymmetric_algorithms:
        # Only test algorithms that are in the configured list
        if algorithm not in settings.OAUTH_ALGORITHMS:
            continue

        token = "mock-token"
        mock_credentials.credentials = token

        mock_jwks_client.get_signing_key.return_value = mock_jwk

        with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
            mock_header.return_value = {"kid": "test-key-1", "alg": algorithm, "typ": "JWT"}

            with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
                mock_decode.return_value = {
                    "sub": "test-user-123",
                    "iss": settings.OAUTH_ISSUER_URL,
                    "aud": settings.OAUTH_AUDIENCE,
                    "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                    "iat": int(datetime.utcnow().timestamp()),
                    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "jti": "test-jti-12345",
                }

                # Should not raise exception for asymmetric algorithms
                user = await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)
                assert user.user_id == "test-user-123"


# ============================================================================
# SECURITY TEST 7: Rate Limiting for OAuth Token Validation (TASK-009B Session 2A)
# ============================================================================

@pytest.mark.asyncio
async def test_rate_limit_general_auth_exceeded(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service):
    """
    SECURITY: Test that general auth rate limit is enforced.

    When an IP exceeds 100 requests/minute, should return 429 with Retry-After header.
    """
    from app.core.rate_limit import RateLimitExceeded

    # Simulate rate limit exceeded for general auth
    mock_rate_limiter.check_rate_limit.side_effect = RateLimitExceeded(
        retry_after=42, limit_type="auth"
    )

    # Attempt authentication
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter
        , mock_token_revocation_service)

    # Verify 429 response
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error"] == "rate_limit_exceeded"
    assert "Too many authentication attempts" in exc_info.value.detail["error_description"]
    assert exc_info.value.headers["Retry-After"] == "42"

    # Verify rate limiter was called with correct parameters
    mock_rate_limiter.check_rate_limit.assert_called_once_with(
        "192.168.1.100", is_failed_auth=False
    )


@pytest.mark.asyncio
async def test_rate_limit_failed_auth_exceeded(
    mock_request, mock_jwks_client, mock_rate_limiter
):
    """
    SECURITY: Test that failed auth rate limit is enforced (stricter limit).

    When an IP exceeds 10 failed auth attempts/minute, should return 429.
    """
    from app.core.rate_limit import RateLimitExceeded

    # First call: general rate limit passes
    # Second call: failed auth rate limit exceeded
    call_count = 0

    def side_effect(ip, is_failed_auth):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call (general auth) - passes
            return None
        else:
            # Second call (failed auth) - exceeded
            raise RateLimitExceeded(retry_after=30, limit_type="failed_auth")

    mock_rate_limiter.check_rate_limit.side_effect = side_effect

    # Missing Authorization header triggers failed auth
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            mock_request, None, mock_jwks_client, mock_rate_limiter
        , mock_token_revocation_service)

    # Verify 429 response for failed auth rate limit
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error"] == "rate_limit_exceeded"
    assert "Too many failed authentication attempts" in exc_info.value.detail["error_description"]
    assert exc_info.value.headers["Retry-After"] == "30"

    # Verify rate limiter was called twice: general + failed
    assert mock_rate_limiter.check_rate_limit.call_count == 2


@pytest.mark.asyncio
async def test_rate_limit_invalid_token_tracked_as_failed(
    mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_jwk
):
    """
    SECURITY: Test that invalid tokens are tracked as failed auth attempts.

    Invalid token should:
    1. Pass general rate limit check
    2. Fail validation (401)
    3. Trigger failed auth rate limit check
    """
    from app.core.rate_limit import RateLimitExceeded

    # General rate limit passes, failed auth passes initially
    mock_rate_limiter.check_rate_limit.return_value = None

    token = "mock-invalid-token"
    mock_credentials.credentials = token
    mock_jwks_client.get_signing_key.return_value = mock_jwk

    # Mock invalid token (expired)
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}

        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            mock_decode.side_effect = ExpiredSignatureError("Token expired")

            # Attempt authentication with expired token
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter
                , mock_token_revocation_service)

            # Verify 401 response (not 429 - failed auth limit not exceeded yet)
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail["error"] == "expired_token"

    # Verify rate limiter was called twice: general auth + failed auth
    assert mock_rate_limiter.check_rate_limit.call_count == 2
    calls = mock_rate_limiter.check_rate_limit.call_args_list
    assert calls[0][0] == ("192.168.1.100",)
    assert calls[0][1] == {"is_failed_auth": False}
    assert calls[1][0] == ("192.168.1.100",)
    assert calls[1][1] == {"is_failed_auth": True}


@pytest.mark.asyncio
async def test_rate_limit_graceful_degradation():
    """
    SECURITY: Test graceful degradation when Redis is unavailable.

    If Redis fails, rate limiting should:
    1. Log a warning
    2. Allow the request to proceed
    3. Not block authentication
    """
    from app.core.rate_limit import RateLimiter
    import redis.asyncio as redis_async

    # Create mock Redis client that fails
    mock_redis = AsyncMock()
    mock_redis.incr.side_effect = redis_async.RedisError("Connection failed")

    # Create rate limiter with failing Redis
    limiter = RateLimiter(
        redis_client=mock_redis,
        general_limit=100,
        failed_limit=10,
        window_seconds=60,
        enabled=True,
    )

    # Should not raise exception - graceful degradation
    await limiter.check_rate_limit("192.168.1.100", is_failed_auth=False)

    # Verify Redis was attempted
    mock_redis.incr.assert_called_once()


@pytest.mark.asyncio
async def test_rate_limit_retry_after_calculation():
    """
    SECURITY: Test that Retry-After header is calculated correctly.

    The retry_after value should represent seconds until the current window ends.
    """
    from app.core.rate_limit import RateLimiter, RateLimitExceeded
    import time

    # Create mock Redis client
    mock_redis = AsyncMock()

    # Simulate exceeding limit (count > limit)
    mock_redis.incr.return_value = 101  # Exceeds limit of 100

    limiter = RateLimiter(
        redis_client=mock_redis,
        general_limit=100,
        failed_limit=10,
        window_seconds=60,
        enabled=True,
    )

    # Check rate limit
    with pytest.raises(RateLimitExceeded) as exc_info:
        await limiter.check_rate_limit("192.168.1.100", is_failed_auth=False)

    # Verify retry_after is reasonable (between 1 and 60 seconds)
    retry_after = exc_info.value.retry_after
    assert 1 <= retry_after <= 60
    assert isinstance(retry_after, int)


@pytest.mark.asyncio
async def test_rate_limit_disabled():
    """
    SECURITY: Test that rate limiting can be disabled via configuration.

    When RATE_LIMIT_ENABLED=False, no rate limiting should occur.
    """
    from app.core.rate_limit import RateLimiter

    mock_redis = AsyncMock()

    # Create disabled rate limiter
    limiter = RateLimiter(
        redis_client=mock_redis,
        general_limit=100,
        failed_limit=10,
        window_seconds=60,
        enabled=False,  # Disabled
    )

    # Should not interact with Redis at all
    await limiter.check_rate_limit("192.168.1.100", is_failed_auth=False)

    # Verify Redis was not called
    mock_redis.incr.assert_not_called()
    mock_redis.expire.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limit_separate_windows_for_general_and_failed():
    """
    SECURITY: Test that general and failed auth have separate rate limit windows.

    General auth limit (100/min) and failed auth limit (10/min) should be tracked separately.
    """
    from app.core.rate_limit import RateLimiter

    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 5  # Within both limits

    limiter = RateLimiter(
        redis_client=mock_redis,
        general_limit=100,
        failed_limit=10,
        window_seconds=60,
        enabled=True,
    )

    # Check general auth
    await limiter.check_rate_limit("192.168.1.100", is_failed_auth=False)

    # Check failed auth
    await limiter.check_rate_limit("192.168.1.100", is_failed_auth=True)

    # Verify different Redis keys were used
    calls = mock_redis.incr.call_args_list
    assert len(calls) == 2

    general_key = calls[0][0][0]
    failed_key = calls[1][0][0]

    assert "rate_limit:auth:" in general_key
    assert "rate_limit:failed_auth:" in failed_key
    assert general_key != failed_key

# ============================================================================
# SECURITY TEST 8: Token Revocation (TASK-009B Session 2B)
# ============================================================================

@pytest.mark.asyncio
async def test_jti_claim_required(
    mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service, mock_jwk
):
    """
    SECURITY: Test that tokens without jti claim are rejected.
    
    The jti (JWT ID) claim is required for token revocation support.
    Tokens without jti cannot be revoked and should be rejected.
    """
    # Mock JWKS response
    mock_jwks_client.get_signing_key.return_value = mock_jwk
    
    token = "mock-token"
    mock_credentials.credentials = token
    
    # Mock get_unverified_jwt_header
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}
        
        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            # Return payload WITHOUT jti
            mock_decode.return_value = {
                "sub": "test-user-123",
                "iss": settings.OAUTH_ISSUER_URL,
                "aud": settings.OAUTH_AUDIENCE,
                "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                "iat": int(datetime.utcnow().timestamp()),
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                # jti is MISSING
            }
            
            # Should raise validation error (Pydantic will catch missing jti)
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)
            
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail["error"] == "invalid_token"


@pytest.mark.asyncio
async def test_revoked_token_rejected(
    mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service, mock_jwk
):
    """
    SECURITY: Test that revoked tokens are rejected with 401 Unauthorized.
    
    After a token is revoked (e.g., during logout), subsequent requests with that
    token should return 401 Unauthorized with "Token has been revoked" error.
    """
    # Mock JWKS response
    mock_jwks_client.get_signing_key.return_value = mock_jwk
    
    # Mock token revocation service to return token as revoked
    mock_token_revocation_service.is_token_revoked.return_value = True
    
    token = "mock-token"
    mock_credentials.credentials = token
    
    # Mock get_unverified_jwt_header
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}
        
        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            # Return valid payload
            mock_decode.return_value = {
                "sub": "test-user-123",
                "iss": settings.OAUTH_ISSUER_URL,
                "aud": settings.OAUTH_AUDIENCE,
                "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                "iat": int(datetime.utcnow().timestamp()),
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "jti": "revoked-jti-12345",
            }
            
            # Should raise HTTPException because token is revoked
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)
            
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail["error"] == "invalid_token"
            assert "revoked" in exc_info.value.detail["error_description"].lower()
            
            # Verify revocation check was called with correct jti
            mock_token_revocation_service.is_token_revoked.assert_called_once_with("revoked-jti-12345")


@pytest.mark.asyncio
async def test_token_revocation_service_blacklist():
    """
    Test TokenRevocationService add and check token in blacklist.
    
    Verifies that:
    1. Tokens can be added to blacklist with correct TTL
    2. is_token_revoked returns True for blacklisted tokens
    3. is_token_revoked returns False for non-blacklisted tokens
    """
    from app.services.token_revocation import TokenRevocationService
    import time
    
    # Mock Redis client
    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=1)  # Token exists in blacklist
    
    service = TokenRevocationService(mock_redis)
    
    # Test revoking a token
    jti = "test-jti-12345"
    exp = int(time.time()) + 3600  # Expires in 1 hour
    
    await service.revoke_token(jti=jti, exp=exp)
    
    # Verify Redis setex was called with correct parameters
    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args
    assert call_args[1]["name"] == f"revoked_token:{jti}"
    assert call_args[1]["value"] == "revoked"
    assert call_args[1]["time"] > 0  # TTL should be positive
    assert call_args[1]["time"] <= 3600  # TTL should not exceed token expiration
    
    # Test checking if token is revoked
    is_revoked = await service.is_token_revoked(jti=jti)
    assert is_revoked is True
    
    # Verify Redis exists was called with correct key
    mock_redis.exists.assert_called_once_with(f"revoked_token:{jti}")


@pytest.mark.asyncio
async def test_token_revocation_ttl_calculation():
    """
    Test that revoked tokens have TTL matching token expiration.
    
    The TTL should equal (exp - current_time) so that revoked tokens
    automatically expire from Redis when the token naturally expires.
    """
    from app.services.token_revocation import TokenRevocationService
    import time
    
    # Mock Redis client
    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock()
    
    service = TokenRevocationService(mock_redis)
    
    # Test with token expiring in 1 hour
    jti = "test-jti-12345"
    current_time = int(time.time())
    exp = current_time + 3600  # 1 hour from now
    
    await service.revoke_token(jti=jti, exp=exp)
    
    # Verify TTL is approximately 3600 seconds (allow for small time differences)
    call_args = mock_redis.setex.call_args
    ttl = call_args[1]["time"]
    assert 3595 <= ttl <= 3600, f"TTL should be ~3600, got {ttl}"
    
    # Test with already expired token (TTL should be 0 or negative, so no blacklist entry)
    expired_jti = "expired-jti-67890"
    expired_exp = current_time - 100  # Expired 100 seconds ago
    
    mock_redis.setex.reset_mock()
    await service.revoke_token(jti=expired_jti, exp=expired_exp)
    
    # Should not call setex for already expired token
    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_token_revocation_redis_failure_fail_closed():
    """
    SECURITY: Test that Redis failures during revocation check result in fail-closed behavior.
    
    If Redis is unavailable during token validation, the system should:
    - Reject the token (fail closed)
    - Return 503 Service Unavailable
    - Log the error
    
    Rationale: It's safer to temporarily block legitimate users than to potentially
    allow a revoked (compromised) token.
    """
    from app.services.token_revocation import TokenRevocationService
    import redis.asyncio as redis
    
    # Mock Redis client that raises error
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(side_effect=redis.RedisError("Connection failed"))
    
    service = TokenRevocationService(mock_redis)
    
    # Check if token is revoked (should fail closed and return True)
    is_revoked = await service.is_token_revoked(jti="test-jti-12345")
    
    # Should return True (reject token) even though we don't know if it's actually revoked
    assert is_revoked is True, "Should fail closed (reject token) when Redis is unavailable"


@pytest.mark.asyncio
async def test_token_revocation_valid_token_not_revoked(
    mock_request, mock_jwks_client, mock_credentials, mock_rate_limiter, mock_token_revocation_service, mock_jwk
):
    """
    Test that valid (non-revoked) tokens are accepted.
    
    Verifies that token revocation check allows valid tokens through.
    """
    # Mock JWKS response
    mock_jwks_client.get_signing_key.return_value = mock_jwk
    
    # Mock token revocation service to return token as NOT revoked
    mock_token_revocation_service.is_token_revoked.return_value = False
    
    token = "mock-token"
    mock_credentials.credentials = token
    
    valid_tenant_id = "550e8400-e29b-41d4-a716-446655440000"
    
    # Mock get_unverified_jwt_header
    with patch("app.api.dependencies.auth.get_unverified_jwt_header") as mock_header:
        mock_header.return_value = {"kid": "test-key-1", "alg": "RS256", "typ": "JWT"}
        
        with patch("app.api.dependencies.auth.jwt.decode") as mock_decode:
            # Return valid payload with jti
            mock_decode.return_value = {
                "sub": "test-user-123",
                "iss": settings.OAUTH_ISSUER_URL,
                "aud": settings.OAUTH_AUDIENCE,
                "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                "iat": int(datetime.utcnow().timestamp()),
                "tenant_id": valid_tenant_id,
                "jti": "valid-jti-12345",
                "scope": "read",
            }
            
            # Should successfully authenticate
            user = await get_current_user(mock_request, mock_credentials, mock_jwks_client, mock_rate_limiter, mock_token_revocation_service)
            
            # Verify user was authenticated
            assert isinstance(user, AuthenticatedUser)
            assert user.user_id == "test-user-123"
            assert user.tenant_id == valid_tenant_id
            assert user.jti == "valid-jti-12345"
            
            # Verify revocation check was called
            mock_token_revocation_service.is_token_revoked.assert_called_once_with("valid-jti-12345")
