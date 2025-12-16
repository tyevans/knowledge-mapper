"""
Unit tests for consolidation scopes.

Tests that consolidation scopes are properly defined and work with
the require_scopes dependency.
"""

import pytest

from app.schemas.auth import (
    ALL_SCOPES,
    SCOPE_ENTITIES_READ,
    SCOPE_ENTITIES_WRITE,
    SCOPE_CONSOLIDATION_READ,
    SCOPE_CONSOLIDATION_WRITE,
    SCOPE_CONSOLIDATION_ADMIN,
)
from app.api.dependencies.scopes import require_scopes, require_any_scope


@pytest.mark.unit
def test_entities_read_scope_defined():
    """Verify entities/read scope is defined."""
    assert SCOPE_ENTITIES_READ == "entities/read"
    assert SCOPE_ENTITIES_READ in ALL_SCOPES


@pytest.mark.unit
def test_entities_write_scope_defined():
    """Verify entities/write scope is defined."""
    assert SCOPE_ENTITIES_WRITE == "entities/write"
    assert SCOPE_ENTITIES_WRITE in ALL_SCOPES


@pytest.mark.unit
def test_consolidation_read_scope_defined():
    """Verify consolidation/read scope is defined."""
    assert SCOPE_CONSOLIDATION_READ == "consolidation/read"
    assert SCOPE_CONSOLIDATION_READ in ALL_SCOPES


@pytest.mark.unit
def test_consolidation_write_scope_defined():
    """Verify consolidation/write scope is defined."""
    assert SCOPE_CONSOLIDATION_WRITE == "consolidation/write"
    assert SCOPE_CONSOLIDATION_WRITE in ALL_SCOPES


@pytest.mark.unit
def test_consolidation_admin_scope_defined():
    """Verify consolidation/admin scope is defined."""
    assert SCOPE_CONSOLIDATION_ADMIN == "consolidation/admin"
    assert SCOPE_CONSOLIDATION_ADMIN in ALL_SCOPES


@pytest.mark.unit
def test_require_entities_read_scope():
    """Verify entities/read scope check works."""
    checker = require_scopes(SCOPE_ENTITIES_READ)
    assert checker is not None
    assert callable(checker)


@pytest.mark.unit
def test_require_entities_write_scope():
    """Verify entities/write scope check works."""
    checker = require_scopes(SCOPE_ENTITIES_WRITE)
    assert checker is not None
    assert callable(checker)


@pytest.mark.unit
def test_require_consolidation_read_scope():
    """Verify consolidation/read scope check works."""
    checker = require_scopes(SCOPE_CONSOLIDATION_READ)
    assert checker is not None
    assert callable(checker)


@pytest.mark.unit
def test_require_consolidation_write_scope():
    """Verify consolidation/write scope check works."""
    checker = require_scopes(SCOPE_CONSOLIDATION_WRITE)
    assert checker is not None
    assert callable(checker)


@pytest.mark.unit
def test_require_consolidation_admin_scope():
    """Verify consolidation/admin scope check works."""
    checker = require_scopes(SCOPE_CONSOLIDATION_ADMIN)
    assert checker is not None
    assert callable(checker)


@pytest.mark.unit
def test_require_any_consolidation_scope():
    """Verify OR logic with consolidation scopes."""
    checker = require_any_scope(
        SCOPE_CONSOLIDATION_READ,
        SCOPE_CONSOLIDATION_WRITE,
        SCOPE_CONSOLIDATION_ADMIN,
    )
    assert checker is not None
    assert callable(checker)


@pytest.mark.unit
def test_all_consolidation_scopes_in_all_scopes():
    """Verify all consolidation scopes are registered in ALL_SCOPES."""
    consolidation_scopes = {
        SCOPE_ENTITIES_READ,
        SCOPE_ENTITIES_WRITE,
        SCOPE_CONSOLIDATION_READ,
        SCOPE_CONSOLIDATION_WRITE,
        SCOPE_CONSOLIDATION_ADMIN,
    }
    assert consolidation_scopes.issubset(ALL_SCOPES)
