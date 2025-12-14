"""
Unit tests for tenant-aware database dependencies.

Tests the FastAPI dependencies that provide tenant-aware database sessions:
- get_tenant_db() - Requires tenant context
- get_optional_tenant_db() - Optional tenant context
- get_superuser_db() - Bypasses RLS for admin operations
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.tenant import (
    _extract_tenant_id,
    get_optional_tenant_db,
    get_superuser_db,
    get_tenant_db,
)
from app.services.tenant_context import TenantContextError


class TestGetTenantDb:
    """Tests for get_tenant_db() dependency."""

    @pytest.mark.asyncio
    async def test_get_tenant_db_with_request_state(self):
        """Test that get_tenant_db() works with tenant_id in request.state."""
        # Arrange
        tenant_id = uuid4()
        mock_request = MagicMock(spec=Request)
        mock_request.state.tenant_id = tenant_id
        mock_request.url.path = "/api/v1/statements"
        mock_request.method = "GET"

        # Mock the session and set_tenant_context
        with patch(
            "app.api.dependencies.tenant.AsyncSessionLocal"
        ) as mock_session_factory:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_session_factory.return_value.__aexit__.return_value = None

            with patch(
                "app.api.dependencies.tenant.set_tenant_context"
            ) as mock_set_context:
                # Act
                async for session in get_tenant_db(mock_request):
                    # Assert - session is returned
                    assert session == mock_session

                    # Assert - set_tenant_context was called with correct params
                    mock_set_context.assert_called_once_with(
                        mock_session, tenant_id, validate=True
                    )

                # Assert - session was committed and closed
                mock_session.commit.assert_called_once()
                mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tenant_db_with_contextvars_fallback(self):
        """Test that get_tenant_db() falls back to contextvars."""
        # Arrange
        tenant_id = uuid4()
        mock_request = MagicMock(spec=Request)
        # No tenant_id in request.state
        delattr(mock_request.state, "tenant_id")
        mock_request.url.path = "/api/v1/statements"
        mock_request.method = "GET"

        # Mock get_current_tenant to return tenant_id from contextvars
        with patch(
            "app.api.dependencies.tenant.get_current_tenant", return_value=tenant_id
        ):
            with patch(
                "app.api.dependencies.tenant.AsyncSessionLocal"
            ) as mock_session_factory:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_session_factory.return_value.__aenter__.return_value = mock_session
                mock_session_factory.return_value.__aexit__.return_value = None

                with patch(
                    "app.api.dependencies.tenant.set_tenant_context"
                ) as mock_set_context:
                    # Act
                    async for session in get_tenant_db(mock_request):
                        # Assert
                        assert session == mock_session
                        mock_set_context.assert_called_once_with(
                            mock_session, tenant_id, validate=True
                        )

    @pytest.mark.asyncio
    async def test_get_tenant_db_missing_tenant_raises_500(self):
        """Test that get_tenant_db() raises 500 if tenant context is missing."""
        # Arrange
        mock_request = MagicMock(spec=Request)
        # No tenant_id in request.state
        delattr(mock_request.state, "tenant_id")
        mock_request.url.path = "/api/v1/statements"
        mock_request.method = "GET"

        # Mock get_current_tenant to return None
        with patch("app.api.dependencies.tenant.get_current_tenant", return_value=None):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                async for _ in get_tenant_db(mock_request):
                    pass

            # Assert error details
            assert exc_info.value.status_code == 500
            assert "tenant_context_missing" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_tenant_db_tenant_validation_failure_raises_403(self):
        """Test that get_tenant_db() raises 403 if tenant validation fails."""
        # Arrange
        tenant_id = uuid4()
        mock_request = MagicMock(spec=Request)
        mock_request.state.tenant_id = tenant_id
        mock_request.url.path = "/api/v1/statements"
        mock_request.method = "GET"

        with patch(
            "app.api.dependencies.tenant.AsyncSessionLocal"
        ) as mock_session_factory:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_session_factory.return_value.__aexit__.return_value = None

            # Mock set_tenant_context to raise TenantContextError
            with patch(
                "app.api.dependencies.tenant.set_tenant_context",
                side_effect=TenantContextError("Tenant is not active"),
            ):
                # Act & Assert
                with pytest.raises(HTTPException) as exc_info:
                    async for _ in get_tenant_db(mock_request):
                        pass

                # Assert error details
                assert exc_info.value.status_code == 403
                assert "tenant_validation_failed" in str(exc_info.value.detail)

                # Assert rollback was called
                mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tenant_db_propagates_exceptions(self):
        """Test that get_tenant_db() propagates exceptions from route handlers."""
        # Arrange
        tenant_id = uuid4()
        mock_request = MagicMock(spec=Request)
        mock_request.state.tenant_id = tenant_id
        mock_request.url.path = "/api/v1/statements"
        mock_request.method = "GET"

        with patch(
            "app.api.dependencies.tenant.AsyncSessionLocal"
        ) as mock_session_factory:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_session_factory.return_value.__aexit__.return_value = None

            with patch("app.api.dependencies.tenant.set_tenant_context"):
                # Act & Assert - exception should be propagated
                with pytest.raises(RuntimeError, match="Database error"):
                    async for session in get_tenant_db(mock_request):
                        # Simulate exception in route handler
                        raise RuntimeError("Database error")

    @pytest.mark.asyncio
    async def test_get_tenant_db_logs_tenant_context_set(self, caplog):
        """Test that get_tenant_db() logs when tenant context is set."""
        # Arrange
        tenant_id = uuid4()
        mock_request = MagicMock(spec=Request)
        mock_request.state.tenant_id = tenant_id
        mock_request.url.path = "/api/v1/statements"
        mock_request.method = "GET"

        with patch(
            "app.api.dependencies.tenant.AsyncSessionLocal"
        ) as mock_session_factory:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_session_factory.return_value.__aexit__.return_value = None

            with patch("app.api.dependencies.tenant.set_tenant_context"):
                with caplog.at_level(logging.INFO):
                    # Act
                    async for _ in get_tenant_db(mock_request):
                        pass

                    # Assert logging
                    assert any(
                        "Tenant context set for database session" in record.message
                        for record in caplog.records
                    )


class TestGetOptionalTenantDb:
    """Tests for get_optional_tenant_db() dependency."""

    @pytest.mark.asyncio
    async def test_get_optional_tenant_db_with_tenant(self):
        """Test that get_optional_tenant_db() sets context when tenant is available."""
        # Arrange
        tenant_id = uuid4()
        mock_request = MagicMock(spec=Request)
        mock_request.state.tenant_id = tenant_id
        mock_request.url.path = "/api/v1/public-data"
        mock_request.method = "GET"

        with patch(
            "app.api.dependencies.tenant.AsyncSessionLocal"
        ) as mock_session_factory:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_session_factory.return_value.__aexit__.return_value = None

            with patch(
                "app.api.dependencies.tenant.set_tenant_context"
            ) as mock_set_context:
                # Act
                async for session in get_optional_tenant_db(mock_request):
                    # Assert
                    assert session == mock_session
                    mock_set_context.assert_called_once_with(
                        mock_session, tenant_id, validate=True
                    )

    @pytest.mark.asyncio
    async def test_get_optional_tenant_db_without_tenant(self):
        """Test that get_optional_tenant_db() works without tenant context."""
        # Arrange
        mock_request = MagicMock(spec=Request)
        # No tenant_id in request.state
        delattr(mock_request.state, "tenant_id")
        mock_request.url.path = "/api/v1/public-data"
        mock_request.method = "GET"

        with patch("app.api.dependencies.tenant.get_current_tenant", return_value=None):
            with patch(
                "app.api.dependencies.tenant.AsyncSessionLocal"
            ) as mock_session_factory:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_session_factory.return_value.__aenter__.return_value = mock_session
                mock_session_factory.return_value.__aexit__.return_value = None

                with patch(
                    "app.api.dependencies.tenant.set_tenant_context"
                ) as mock_set_context:
                    # Act
                    async for session in get_optional_tenant_db(mock_request):
                        # Assert - session is returned without tenant context
                        assert session == mock_session
                        mock_set_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_optional_tenant_db_continues_on_validation_failure(self):
        """Test that get_optional_tenant_db() continues if tenant validation fails."""
        # Arrange
        tenant_id = uuid4()
        mock_request = MagicMock(spec=Request)
        mock_request.state.tenant_id = tenant_id
        mock_request.url.path = "/api/v1/public-data"
        mock_request.method = "GET"

        with patch(
            "app.api.dependencies.tenant.AsyncSessionLocal"
        ) as mock_session_factory:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_session_factory.return_value.__aexit__.return_value = None

            # Mock set_tenant_context to raise TenantContextError
            with patch(
                "app.api.dependencies.tenant.set_tenant_context",
                side_effect=TenantContextError("Tenant is not active"),
            ):
                # Act - should not raise exception
                async for session in get_optional_tenant_db(mock_request):
                    # Assert - session is returned without tenant context
                    assert session == mock_session

                # Assert - session was committed (not rolled back)
                mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_optional_tenant_db_logs_optional_context(self, caplog):
        """Test that get_optional_tenant_db() logs appropriately."""
        # Arrange
        mock_request = MagicMock(spec=Request)
        delattr(mock_request.state, "tenant_id")
        mock_request.url.path = "/api/v1/public-data"
        mock_request.method = "GET"

        with patch("app.api.dependencies.tenant.get_current_tenant", return_value=None):
            with patch(
                "app.api.dependencies.tenant.AsyncSessionLocal"
            ) as mock_session_factory:
                mock_session = AsyncMock(spec=AsyncSession)
                mock_session_factory.return_value.__aenter__.return_value = mock_session
                mock_session_factory.return_value.__aexit__.return_value = None

                with caplog.at_level(logging.DEBUG):
                    # Act
                    async for _ in get_optional_tenant_db(mock_request):
                        pass

                    # Assert logging
                    assert any(
                        "Optional tenant context not available" in record.message
                        for record in caplog.records
                    )


class TestGetSuperuserDb:
    """Tests for get_superuser_db() dependency."""

    @pytest.mark.asyncio
    async def test_get_superuser_db_bypasses_rls(self):
        """Test that get_superuser_db() calls bypass_rls()."""
        # Arrange
        mock_request = MagicMock(spec=Request)
        mock_request.state.user_id = "admin-user-123"
        mock_request.url.path = "/api/v1/admin/tenants"
        mock_request.method = "GET"

        with patch(
            "app.api.dependencies.tenant.AsyncSessionLocal"
        ) as mock_session_factory:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_session_factory.return_value.__aexit__.return_value = None

            with patch("app.api.dependencies.tenant.bypass_rls") as mock_bypass:
                # Act
                async for session in get_superuser_db(mock_request):
                    # Assert
                    assert session == mock_session
                    mock_bypass.assert_called_once_with(mock_session)

    @pytest.mark.asyncio
    async def test_get_superuser_db_logs_at_warning_level(self, caplog):
        """Test that get_superuser_db() logs RLS bypass at WARNING level."""
        # Arrange
        mock_request = MagicMock(spec=Request)
        mock_request.state.user_id = "admin-user-123"
        mock_request.url.path = "/api/v1/admin/tenants"
        mock_request.method = "GET"

        with patch(
            "app.api.dependencies.tenant.AsyncSessionLocal"
        ) as mock_session_factory:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_session_factory.return_value.__aexit__.return_value = None

            with patch("app.api.dependencies.tenant.bypass_rls"):
                with caplog.at_level(logging.WARNING):
                    # Act
                    async for _ in get_superuser_db(mock_request):
                        pass

                    # Assert - multiple WARNING logs for security audit
                    warning_logs = [
                        record
                        for record in caplog.records
                        if record.levelname == "WARNING"
                    ]
                    assert len(warning_logs) >= 2

                    # Check log messages
                    log_messages = [record.message for record in warning_logs]
                    assert any("RLS bypass requested" in msg for msg in log_messages)
                    assert any("RLS bypass active" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_get_superuser_db_logs_user_id(self, caplog):
        """Test that get_superuser_db() logs user_id for audit trail."""
        # Arrange
        user_id = "admin-user-123"
        mock_request = MagicMock(spec=Request)
        mock_request.state.user_id = user_id
        mock_request.url.path = "/api/v1/admin/tenants"
        mock_request.method = "GET"

        with patch(
            "app.api.dependencies.tenant.AsyncSessionLocal"
        ) as mock_session_factory:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_session_factory.return_value.__aexit__.return_value = None

            with patch("app.api.dependencies.tenant.bypass_rls"):
                with caplog.at_level(logging.WARNING):
                    # Act
                    async for _ in get_superuser_db(mock_request):
                        pass

                    # Assert - user_id is in log records
                    assert any(
                        user_id in str(record.__dict__.get("user_id", ""))
                        for record in caplog.records
                    )

    @pytest.mark.asyncio
    async def test_get_superuser_db_propagates_exceptions(self):
        """Test that get_superuser_db() propagates exceptions from route handlers."""
        # Arrange
        mock_request = MagicMock(spec=Request)
        mock_request.state.user_id = "admin-user-123"
        mock_request.url.path = "/api/v1/admin/tenants"
        mock_request.method = "GET"

        with patch(
            "app.api.dependencies.tenant.AsyncSessionLocal"
        ) as mock_session_factory:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            mock_session_factory.return_value.__aexit__.return_value = None

            with patch("app.api.dependencies.tenant.bypass_rls"):
                # Act & Assert - exception should be propagated
                with pytest.raises(RuntimeError, match="Database error"):
                    async for session in get_superuser_db(mock_request):
                        raise RuntimeError("Database error")


class TestExtractTenantId:
    """Tests for _extract_tenant_id() helper function."""

    def test_extract_tenant_id_from_request_state(self):
        """Test extracting tenant_id from request.state."""
        # Arrange
        tenant_id = uuid4()
        mock_request = MagicMock(spec=Request)
        mock_request.state.tenant_id = tenant_id

        # Act
        result = _extract_tenant_id(mock_request)

        # Assert
        assert result == tenant_id

    def test_extract_tenant_id_from_contextvars(self):
        """Test extracting tenant_id from contextvars as fallback."""
        # Arrange
        tenant_id = uuid4()
        mock_request = MagicMock(spec=Request)
        delattr(mock_request.state, "tenant_id")

        with patch(
            "app.api.dependencies.tenant.get_current_tenant", return_value=tenant_id
        ):
            # Act
            result = _extract_tenant_id(mock_request)

            # Assert
            assert result == tenant_id

    def test_extract_tenant_id_returns_none_if_not_available(self):
        """Test that _extract_tenant_id() returns None if tenant_id is not available."""
        # Arrange
        mock_request = MagicMock(spec=Request)
        delattr(mock_request.state, "tenant_id")

        with patch("app.api.dependencies.tenant.get_current_tenant", return_value=None):
            # Act
            result = _extract_tenant_id(mock_request)

            # Assert
            assert result is None

    def test_extract_tenant_id_prefers_request_state_over_contextvars(self):
        """Test that request.state is preferred over contextvars."""
        # Arrange
        request_tenant_id = uuid4()
        contextvar_tenant_id = uuid4()
        mock_request = MagicMock(spec=Request)
        mock_request.state.tenant_id = request_tenant_id

        with patch(
            "app.api.dependencies.tenant.get_current_tenant",
            return_value=contextvar_tenant_id,
        ):
            # Act
            result = _extract_tenant_id(mock_request)

            # Assert - should return request state value
            assert result == request_tenant_id
            assert result != contextvar_tenant_id
