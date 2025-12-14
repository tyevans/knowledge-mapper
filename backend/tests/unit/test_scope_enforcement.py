"""Unit tests for OAuth scope enforcement."""
import pytest
from fastapi import HTTPException

from app.api.dependencies.scopes import (
    require_scopes,
    require_any_scope,
    has_scope,
    has_any_scope,
    has_all_scopes,
)
from app.schemas.auth import (
    AuthenticatedUser,
    SCOPE_STATEMENTS_READ,
    SCOPE_STATEMENTS_WRITE,
    SCOPE_STATEMENTS_READ_MINE,
    SCOPE_STATE_READ,
    SCOPE_STATE_WRITE,
    SCOPE_ADMIN,
    SCOPE_TENANT_ADMIN,
)


# Fixtures for different user scope combinations


@pytest.fixture
def user_with_read_scope():
    """Mock user with read scope only."""
    return AuthenticatedUser(
        user_id="test-user-123",
        tenant_id="550e8400-e29b-41d4-a716-446655440000",
        jti="jwt-id-123",
        exp=9999999999,
        scopes=[SCOPE_STATEMENTS_READ],
        issuer="http://keycloak:8080/realms/knowledge-mapper-dev",
    )


@pytest.fixture
def user_with_write_scope():
    """Mock user with write scope only."""
    return AuthenticatedUser(
        user_id="test-user-456",
        tenant_id="550e8400-e29b-41d4-a716-446655440000",
        jti="jwt-id-456",
        exp=9999999999,
        scopes=[SCOPE_STATEMENTS_WRITE],
        issuer="http://keycloak:8080/realms/knowledge-mapper-dev",
    )


@pytest.fixture
def user_with_multiple_scopes():
    """Mock user with multiple scopes."""
    return AuthenticatedUser(
        user_id="test-user-789",
        tenant_id="550e8400-e29b-41d4-a716-446655440000",
        jti="jwt-id-789",
        exp=9999999999,
        scopes=[SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_WRITE, SCOPE_STATE_READ],
        issuer="http://keycloak:8080/realms/knowledge-mapper-dev",
    )


@pytest.fixture
def user_with_no_scopes():
    """Mock user with no scopes."""
    return AuthenticatedUser(
        user_id="test-user-000",
        tenant_id="550e8400-e29b-41d4-a716-446655440000",
        jti="jwt-id-000",
        exp=9999999999,
        scopes=[],
        issuer="http://keycloak:8080/realms/knowledge-mapper-dev",
    )


@pytest.fixture
def user_with_admin_scopes():
    """Mock user with admin scopes."""
    return AuthenticatedUser(
        user_id="test-admin-999",
        tenant_id="550e8400-e29b-41d4-a716-446655440000",
        jti="jwt-id-999",
        exp=9999999999,
        scopes=[SCOPE_ADMIN, SCOPE_TENANT_ADMIN],
        issuer="http://keycloak:8080/realms/knowledge-mapper-dev",
    )


@pytest.fixture
def user_with_read_mine_scope():
    """Mock user with read/mine scope only."""
    return AuthenticatedUser(
        user_id="test-user-111",
        tenant_id="550e8400-e29b-41d4-a716-446655440000",
        jti="jwt-id-111",
        exp=9999999999,
        scopes=[SCOPE_STATEMENTS_READ_MINE],
        issuer="http://keycloak:8080/realms/knowledge-mapper-dev",
    )


# Tests for require_scopes() - AND logic


@pytest.mark.asyncio
async def test_require_scopes_success_single_scope(user_with_read_scope):
    """Test that user with required scope passes."""
    checker = require_scopes(SCOPE_STATEMENTS_READ)

    # Should not raise exception
    await checker(user_with_read_scope)


@pytest.mark.asyncio
async def test_require_scopes_failure_missing_scope(user_with_read_scope):
    """Test that user without required scope fails with 403."""
    checker = require_scopes(SCOPE_STATEMENTS_WRITE)

    # Should raise 403
    with pytest.raises(HTTPException) as exc_info:
        await checker(user_with_read_scope)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "insufficient_scope"
    assert SCOPE_STATEMENTS_WRITE in exc_info.value.detail["missing_scopes"]
    assert "required_scopes" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_multiple_scopes_success(user_with_multiple_scopes):
    """Test that user with all required scopes passes (AND logic)."""
    checker = require_scopes(SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_WRITE)

    # Should not raise exception
    await checker(user_with_multiple_scopes)


@pytest.mark.asyncio
async def test_require_multiple_scopes_failure_missing_one(user_with_read_scope):
    """Test that user missing one of multiple scopes fails (AND logic)."""
    checker = require_scopes(SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_WRITE)

    # Should raise 403 (missing write scope)
    with pytest.raises(HTTPException) as exc_info:
        await checker(user_with_read_scope)

    assert exc_info.value.status_code == 403
    assert SCOPE_STATEMENTS_WRITE in exc_info.value.detail["missing_scopes"]
    assert SCOPE_STATEMENTS_READ not in exc_info.value.detail["missing_scopes"]


@pytest.mark.asyncio
async def test_require_multiple_scopes_failure_missing_all(user_with_no_scopes):
    """Test that user with no scopes fails when multiple scopes required."""
    checker = require_scopes(SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_WRITE)

    # Should raise 403 (missing all scopes)
    with pytest.raises(HTTPException) as exc_info:
        await checker(user_with_no_scopes)

    assert exc_info.value.status_code == 403
    missing = exc_info.value.detail["missing_scopes"]
    assert SCOPE_STATEMENTS_READ in missing
    assert SCOPE_STATEMENTS_WRITE in missing


@pytest.mark.asyncio
async def test_require_scopes_failure_with_no_scopes(user_with_no_scopes):
    """Test that user with no scopes fails."""
    checker = require_scopes(SCOPE_STATEMENTS_READ)

    with pytest.raises(HTTPException) as exc_info:
        await checker(user_with_no_scopes)

    assert exc_info.value.status_code == 403
    assert "insufficient_scope" in exc_info.value.detail["error"]


# Tests for require_any_scope() - OR logic


@pytest.mark.asyncio
async def test_require_any_scope_success_has_one(user_with_read_scope):
    """Test that user with any allowed scope passes (OR logic)."""
    checker = require_any_scope(SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_WRITE)

    # Should not raise exception (has read scope)
    await checker(user_with_read_scope)


@pytest.mark.asyncio
async def test_require_any_scope_success_has_multiple(user_with_multiple_scopes):
    """Test that user with multiple allowed scopes passes."""
    checker = require_any_scope(SCOPE_STATEMENTS_READ, SCOPE_STATE_WRITE)

    # Should not raise exception (has read scope)
    await checker(user_with_multiple_scopes)


@pytest.mark.asyncio
async def test_require_any_scope_failure_has_none(user_with_no_scopes):
    """Test that user with no allowed scopes fails."""
    checker = require_any_scope(SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_WRITE)

    # Should raise 403
    with pytest.raises(HTTPException) as exc_info:
        await checker(user_with_no_scopes)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "insufficient_scope"
    assert "allowed_scopes" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_any_scope_failure_wrong_scope(user_with_read_scope):
    """Test that user with wrong scope fails."""
    checker = require_any_scope(SCOPE_STATEMENTS_WRITE, SCOPE_STATE_WRITE)

    # Should raise 403 (has read, but needs write or state/write)
    with pytest.raises(HTTPException) as exc_info:
        await checker(user_with_read_scope)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_any_scope_success_with_read_mine(user_with_read_mine_scope):
    """Test that user with read/mine scope passes when it's an allowed scope."""
    checker = require_any_scope(SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_READ_MINE)

    # Should not raise exception
    await checker(user_with_read_mine_scope)


# Tests for has_scope() helper


def test_has_scope_true(user_with_read_scope):
    """Test has_scope returns True when user has scope."""
    assert has_scope(user_with_read_scope, SCOPE_STATEMENTS_READ) is True


def test_has_scope_false(user_with_read_scope):
    """Test has_scope returns False when user lacks scope."""
    assert has_scope(user_with_read_scope, SCOPE_STATEMENTS_WRITE) is False


def test_has_scope_with_no_scopes(user_with_no_scopes):
    """Test has_scope returns False when user has no scopes."""
    assert has_scope(user_with_no_scopes, SCOPE_STATEMENTS_READ) is False


def test_has_scope_with_multiple_scopes(user_with_multiple_scopes):
    """Test has_scope with user having multiple scopes."""
    assert has_scope(user_with_multiple_scopes, SCOPE_STATEMENTS_READ) is True
    assert has_scope(user_with_multiple_scopes, SCOPE_STATEMENTS_WRITE) is True
    assert has_scope(user_with_multiple_scopes, SCOPE_ADMIN) is False


# Tests for has_any_scope() helper


def test_has_any_scope_true_one_match(user_with_read_scope):
    """Test has_any_scope returns True when user has at least one scope."""
    assert (
        has_any_scope(
            user_with_read_scope, SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_WRITE
        )
        is True
    )


def test_has_any_scope_true_multiple_matches(user_with_multiple_scopes):
    """Test has_any_scope returns True when user has multiple matching scopes."""
    assert (
        has_any_scope(
            user_with_multiple_scopes, SCOPE_STATEMENTS_READ, SCOPE_STATE_READ
        )
        is True
    )


def test_has_any_scope_false(user_with_no_scopes):
    """Test has_any_scope returns False when user has no scopes."""
    assert (
        has_any_scope(
            user_with_no_scopes, SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_WRITE
        )
        is False
    )


def test_has_any_scope_false_wrong_scopes(user_with_read_scope):
    """Test has_any_scope returns False when user has wrong scopes."""
    assert (
        has_any_scope(user_with_read_scope, SCOPE_STATEMENTS_WRITE, SCOPE_ADMIN)
        is False
    )


def test_has_any_scope_single_scope(user_with_read_scope):
    """Test has_any_scope with single scope check."""
    assert has_any_scope(user_with_read_scope, SCOPE_STATEMENTS_READ) is True
    assert has_any_scope(user_with_read_scope, SCOPE_STATEMENTS_WRITE) is False


# Tests for has_all_scopes() helper


def test_has_all_scopes_true(user_with_multiple_scopes):
    """Test has_all_scopes returns True when user has all scopes."""
    assert (
        has_all_scopes(
            user_with_multiple_scopes, SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_WRITE
        )
        is True
    )


def test_has_all_scopes_false_missing_one(user_with_read_scope):
    """Test has_all_scopes returns False when user lacks any scope."""
    assert (
        has_all_scopes(
            user_with_read_scope, SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_WRITE
        )
        is False
    )


def test_has_all_scopes_false_missing_all(user_with_no_scopes):
    """Test has_all_scopes returns False when user has no scopes."""
    assert (
        has_all_scopes(
            user_with_no_scopes, SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_WRITE
        )
        is False
    )


def test_has_all_scopes_true_single_scope(user_with_read_scope):
    """Test has_all_scopes with single scope."""
    assert has_all_scopes(user_with_read_scope, SCOPE_STATEMENTS_READ) is True


def test_has_all_scopes_false_wrong_scope(user_with_read_scope):
    """Test has_all_scopes with wrong scope."""
    assert has_all_scopes(user_with_read_scope, SCOPE_STATEMENTS_WRITE) is False


def test_has_all_scopes_true_admin(user_with_admin_scopes):
    """Test has_all_scopes with admin scopes."""
    assert has_all_scopes(user_with_admin_scopes, SCOPE_ADMIN, SCOPE_TENANT_ADMIN) is True
    assert (
        has_all_scopes(user_with_admin_scopes, SCOPE_ADMIN, SCOPE_STATEMENTS_READ)
        is False
    )


# Tests for error message format


@pytest.mark.asyncio
async def test_error_message_includes_missing_scopes(user_with_read_scope):
    """Test that 403 error includes missing scopes in response."""
    checker = require_scopes(SCOPE_STATEMENTS_WRITE, SCOPE_STATE_WRITE)

    with pytest.raises(HTTPException) as exc_info:
        await checker(user_with_read_scope)

    detail = exc_info.value.detail
    assert "error" in detail
    assert detail["error"] == "insufficient_scope"
    assert "error_description" in detail
    assert "missing_scopes" in detail or "required_scopes" in detail
    # Check that error description mentions missing scopes
    assert "write" in detail["error_description"].lower()


@pytest.mark.asyncio
async def test_error_message_sorted_scopes(user_with_no_scopes):
    """Test that error message scopes are sorted for consistency."""
    checker = require_scopes(SCOPE_STATEMENTS_WRITE, SCOPE_STATEMENTS_READ)

    with pytest.raises(HTTPException) as exc_info:
        await checker(user_with_no_scopes)

    detail = exc_info.value.detail
    # Scopes should be sorted alphabetically
    required = detail.get("required_scopes", [])
    assert required == sorted(required)


@pytest.mark.asyncio
async def test_require_any_scope_error_message(user_with_no_scopes):
    """Test that require_any_scope error message is clear."""
    checker = require_any_scope(SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_WRITE)

    with pytest.raises(HTTPException) as exc_info:
        await checker(user_with_no_scopes)

    detail = exc_info.value.detail
    assert detail["error"] == "insufficient_scope"
    assert "Requires one of" in detail["error_description"]
    assert "allowed_scopes" in detail


# Edge cases


def test_has_scope_case_sensitive(user_with_read_scope):
    """Test that scope checking is case-sensitive."""
    # Scopes should be case-sensitive
    assert has_scope(user_with_read_scope, "statements/READ") is False
    assert has_scope(user_with_read_scope, "STATEMENTS/read") is False


def test_has_any_scope_empty_check(user_with_read_scope):
    """Test has_any_scope with no scopes to check."""
    # Edge case: no scopes to check should return False
    assert has_any_scope(user_with_read_scope) is False


def test_has_all_scopes_empty_check(user_with_read_scope):
    """Test has_all_scopes with no scopes to check."""
    # Edge case: no scopes to check should return True (vacuous truth)
    assert has_all_scopes(user_with_read_scope) is True
