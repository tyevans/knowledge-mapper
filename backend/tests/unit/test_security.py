"""
Unit tests for security utility functions.

Tests the JWT parsing and validation helper functions in app.core.security.
These are thin wrappers around PyJWT but need coverage for reliability.
"""

import pytest
import jwt as pyjwt
from app.core.security import (
    get_unverified_jwt_header,
    get_unverified_jwt_claims,
)


# Helper Functions
def create_test_jwt() -> str:
    """Create a test JWT for testing unverified parsing."""
    payload = {
        "sub": "user123",
        "iss": "http://test-issuer",
        "exp": 9999999999,
        "aud": "test-audience",
    }
    return pyjwt.encode(
        payload, "test-secret", algorithm="HS256", headers={"kid": "test-key-id"}
    )


# Tests for get_unverified_jwt_header()
def test_get_unverified_jwt_header_valid():
    """Test extracting header from valid JWT."""
    token = create_test_jwt()
    header = get_unverified_jwt_header(token)

    assert header["kid"] == "test-key-id"
    assert header["alg"] == "HS256"
    assert header["typ"] == "JWT"


def test_get_unverified_jwt_header_invalid_format():
    """Test handling of malformed JWT with invalid format."""
    with pytest.raises(pyjwt.DecodeError):
        get_unverified_jwt_header("invalid.token.format")


def test_get_unverified_jwt_header_missing_parts():
    """Test handling of JWT with missing parts."""
    with pytest.raises(pyjwt.DecodeError):
        get_unverified_jwt_header("invalid-single-part")


def test_get_unverified_jwt_header_empty_string():
    """Test handling of empty string."""
    with pytest.raises(pyjwt.DecodeError):
        get_unverified_jwt_header("")


# Tests for get_unverified_jwt_claims()
def test_get_unverified_jwt_claims_valid():
    """Test extracting claims from valid JWT."""
    token = create_test_jwt()
    claims = get_unverified_jwt_claims(token)

    assert claims["sub"] == "user123"
    assert claims["iss"] == "http://test-issuer"
    assert claims["aud"] == "test-audience"
    assert claims["exp"] == 9999999999


def test_get_unverified_jwt_claims_invalid_format():
    """Test handling of malformed JWT claims."""
    with pytest.raises(pyjwt.DecodeError):
        get_unverified_jwt_claims("not.a.jwt")


def test_get_unverified_jwt_claims_expired_token():
    """Test that expired tokens can still be parsed unverified."""
    # Create an expired token
    payload = {
        "sub": "user123",
        "iss": "http://test-issuer",
        "exp": 1000000000,  # Expired timestamp
    }
    expired_token = pyjwt.encode(payload, "test-secret", algorithm="HS256")

    # Should successfully parse even though expired (signature verification disabled)
    claims = get_unverified_jwt_claims(expired_token)

    assert claims["sub"] == "user123"
    assert claims["exp"] == 1000000000


def test_get_unverified_jwt_claims_missing_parts():
    """Test handling of JWT with missing parts."""
    with pytest.raises(pyjwt.DecodeError):
        get_unverified_jwt_claims("only-one-part")


def test_get_unverified_jwt_claims_empty_string():
    """Test handling of empty string."""
    with pytest.raises(pyjwt.DecodeError):
        get_unverified_jwt_claims("")


def test_get_unverified_jwt_claims_custom_claims():
    """Test extracting custom claims from JWT."""
    payload = {
        "sub": "user123",
        "iss": "http://test-issuer",
        "exp": 9999999999,
        "custom_field": "custom_value",
        "roles": ["admin", "user"],
    }
    token = pyjwt.encode(payload, "test-secret", algorithm="HS256")

    claims = get_unverified_jwt_claims(token)

    assert claims["custom_field"] == "custom_value"
    assert claims["roles"] == ["admin", "user"]
