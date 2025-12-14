"""
Unit tests for Sentry integration module.

Tests cover:
- PII filtering in before_send hook
- Initialization logic (fail-open pattern)
- User context setting
- Helper functions (capture_message, capture_exception, etc.)
"""

import pytest
from unittest.mock import MagicMock, patch, ANY


class TestBeforeSend:
    """Tests for PII filtering in before_send hook."""

    def test_filters_password_from_request_data(self):
        """Password fields should be filtered from request data."""
        from app.sentry import _before_send

        event = {
            "request": {
                "data": {"username": "alice", "password": "secret123"}
            }
        }
        result = _before_send(event, {})

        assert result is not None
        assert result["request"]["data"]["password"] == "[Filtered]"
        assert result["request"]["data"]["username"] == "alice"

    def test_filters_multiple_pii_fields(self):
        """Multiple PII fields should all be filtered."""
        from app.sentry import _before_send

        event = {
            "request": {
                "data": {
                    "username": "alice",
                    "password": "secret123",
                    "api_key": "key-abc123",
                    "access_token": "token-xyz",
                    "credit_card": "4111111111111111",
                }
            }
        }
        result = _before_send(event, {})

        assert result is not None
        assert result["request"]["data"]["username"] == "alice"
        assert result["request"]["data"]["password"] == "[Filtered]"
        assert result["request"]["data"]["api_key"] == "[Filtered]"
        assert result["request"]["data"]["access_token"] == "[Filtered]"
        assert result["request"]["data"]["credit_card"] == "[Filtered]"

    def test_filters_authorization_header(self):
        """Authorization headers should be filtered."""
        from app.sentry import _before_send

        event = {
            "request": {
                "headers": {
                    "Authorization": "Bearer token123",
                    "Content-Type": "application/json",
                    "X-Request-ID": "req-123",
                }
            }
        }
        result = _before_send(event, {})

        assert result is not None
        assert result["request"]["headers"]["Authorization"] == "[Filtered]"
        assert result["request"]["headers"]["Content-Type"] == "application/json"
        assert result["request"]["headers"]["X-Request-ID"] == "req-123"

    def test_filters_cookie_header(self):
        """Cookie headers should be filtered."""
        from app.sentry import _before_send

        event = {
            "request": {
                "headers": {
                    "Cookie": "session=abc123; other=value",
                    "Accept": "application/json",
                }
            }
        }
        result = _before_send(event, {})

        assert result is not None
        assert result["request"]["headers"]["Cookie"] == "[Filtered]"
        assert result["request"]["headers"]["Accept"] == "application/json"

    def test_filters_x_api_key_header(self):
        """X-API-Key headers should be filtered."""
        from app.sentry import _before_send

        event = {
            "request": {
                "headers": {
                    "X-API-Key": "my-secret-key",
                    "Content-Type": "application/json",
                }
            }
        }
        result = _before_send(event, {})

        assert result is not None
        assert result["request"]["headers"]["X-API-Key"] == "[Filtered]"

    def test_filters_breadcrumb_data(self):
        """PII in breadcrumb data should be filtered."""
        from app.sentry import _before_send

        event = {
            "breadcrumbs": {
                "values": [
                    {
                        "category": "http",
                        "message": "POST /login",
                        "data": {"password": "secret", "username": "alice"},
                    },
                    {
                        "category": "ui",
                        "message": "Button clicked",
                        "data": {"button_id": "submit"},
                    },
                ]
            }
        }
        result = _before_send(event, {})

        assert result is not None
        breadcrumbs = result["breadcrumbs"]["values"]
        assert breadcrumbs[0]["data"]["password"] == "[Filtered]"
        assert breadcrumbs[0]["data"]["username"] == "alice"
        assert breadcrumbs[1]["data"]["button_id"] == "submit"

    def test_filters_extra_data(self):
        """PII in extra data should be filtered."""
        from app.sentry import _before_send

        event = {
            "extra": {
                "password": "secret",
                "user_action": "login",
                "api_key": "key-123",
            }
        }
        result = _before_send(event, {})

        assert result is not None
        assert result["extra"]["password"] == "[Filtered]"
        assert result["extra"]["api_key"] == "[Filtered]"
        assert result["extra"]["user_action"] == "login"

    def test_filters_context_data(self):
        """PII in contexts should be filtered."""
        from app.sentry import _before_send

        event = {
            "contexts": {
                "user": {"secret": "hidden"},
                "request": {"method": "POST"},
            }
        }
        result = _before_send(event, {})

        assert result is not None
        assert result["contexts"]["user"]["secret"] == "[Filtered]"
        assert result["contexts"]["request"]["method"] == "POST"

    def test_filters_query_string_with_password(self):
        """Query strings containing PII patterns should be filtered."""
        from app.sentry import _before_send

        event = {
            "request": {
                "query_string": "username=alice&password=secret123"
            }
        }
        result = _before_send(event, {})

        assert result is not None
        assert result["request"]["query_string"] == "[Filtered]"

    def test_preserves_safe_query_string(self):
        """Query strings without PII should be preserved."""
        from app.sentry import _before_send

        event = {
            "request": {
                "query_string": "page=1&limit=10&sort=name"
            }
        }
        result = _before_send(event, {})

        assert result is not None
        assert result["request"]["query_string"] == "page=1&limit=10&sort=name"

    def test_handles_missing_request(self):
        """Events without request data should pass through."""
        from app.sentry import _before_send

        event = {"message": "Test message", "level": "info"}
        result = _before_send(event, {})

        assert result is not None
        assert result["message"] == "Test message"

    def test_handles_non_dict_data(self):
        """Non-dict data should not cause errors."""
        from app.sentry import _before_send

        event = {
            "request": {
                "data": "plain text body",
                "headers": ["not", "a", "dict"],
            }
        }
        result = _before_send(event, {})

        assert result is not None
        # Should not modify non-dict data
        assert result["request"]["data"] == "plain text body"

    def test_case_insensitive_filtering(self):
        """PII filtering should be case-insensitive."""
        from app.sentry import _before_send

        event = {
            "request": {
                "data": {
                    "PASSWORD": "secret1",
                    "Password": "secret2",
                    "API_KEY": "key1",
                    "Api_Key": "key2",
                }
            }
        }
        result = _before_send(event, {})

        assert result is not None
        # All variations should be filtered
        for key in result["request"]["data"]:
            assert result["request"]["data"][key] == "[Filtered]"


class TestInitSentry:
    """Tests for Sentry initialization."""

    def test_returns_false_when_sdk_not_available(self):
        """Should return False when sentry-sdk is not installed."""
        from app.sentry import init_sentry

        settings = MagicMock()
        settings.SENTRY_DSN = "https://xxx@sentry.io/123"

        with patch("app.sentry.SENTRY_AVAILABLE", False):
            result = init_sentry(settings)
            assert result is False

    def test_returns_false_when_dsn_empty(self):
        """Should return False when SENTRY_DSN is empty."""
        from app.sentry import init_sentry

        settings = MagicMock()
        settings.SENTRY_DSN = ""

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            result = init_sentry(settings)
            assert result is False

    def test_returns_false_when_dsn_not_set(self):
        """Should return False when SENTRY_DSN attribute doesn't exist."""
        from app.sentry import init_sentry

        settings = MagicMock(spec=[])  # No attributes

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            result = init_sentry(settings)
            assert result is False

    @patch("app.sentry.sentry_sdk")
    def test_returns_true_on_successful_init(self, mock_sentry):
        """Should return True when Sentry initializes successfully."""
        from app.sentry import init_sentry

        settings = MagicMock()
        settings.SENTRY_DSN = "https://xxx@sentry.io/123"
        settings.SENTRY_ENVIRONMENT = "test"
        settings.SENTRY_RELEASE = "1.0.0"
        settings.SENTRY_TRACES_SAMPLE_RATE = 0.1
        settings.SENTRY_PROFILES_SAMPLE_RATE = 0.1
        settings.APP_VERSION = "1.0.0"

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            result = init_sentry(settings)

        assert result is True
        mock_sentry.init.assert_called_once()

    @patch("app.sentry.sentry_sdk")
    def test_uses_app_version_when_release_not_set(self, mock_sentry):
        """Should fall back to APP_VERSION when SENTRY_RELEASE is empty."""
        from app.sentry import init_sentry

        settings = MagicMock()
        settings.SENTRY_DSN = "https://xxx@sentry.io/123"
        settings.SENTRY_ENVIRONMENT = "test"
        settings.SENTRY_RELEASE = ""  # Empty
        settings.SENTRY_TRACES_SAMPLE_RATE = 0.1
        settings.SENTRY_PROFILES_SAMPLE_RATE = 0.1
        settings.APP_VERSION = "2.0.0"

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            init_sentry(settings)

        # Verify release uses APP_VERSION
        call_kwargs = mock_sentry.init.call_args[1]
        assert call_kwargs["release"] == "2.0.0"

    @patch("app.sentry.sentry_sdk")
    def test_handles_init_exception(self, mock_sentry):
        """Should return False and not crash on init exception."""
        from app.sentry import init_sentry

        mock_sentry.init.side_effect = Exception("Init failed")

        settings = MagicMock()
        settings.SENTRY_DSN = "https://xxx@sentry.io/123"
        settings.SENTRY_ENVIRONMENT = "test"
        settings.SENTRY_RELEASE = "1.0.0"
        settings.SENTRY_TRACES_SAMPLE_RATE = 0.1
        settings.SENTRY_PROFILES_SAMPLE_RATE = 0.1
        settings.APP_VERSION = "1.0.0"

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            result = init_sentry(settings)

        assert result is False

    @patch("app.sentry.sentry_sdk")
    def test_configures_integrations(self, mock_sentry):
        """Should configure FastAPI, SQLAlchemy, Asyncio, and Logging integrations."""
        from app.sentry import init_sentry

        settings = MagicMock()
        settings.SENTRY_DSN = "https://xxx@sentry.io/123"
        settings.SENTRY_ENVIRONMENT = "production"
        settings.SENTRY_RELEASE = "1.0.0"
        settings.SENTRY_TRACES_SAMPLE_RATE = 0.5
        settings.SENTRY_PROFILES_SAMPLE_RATE = 0.5
        settings.APP_VERSION = "1.0.0"

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            init_sentry(settings)

        call_kwargs = mock_sentry.init.call_args[1]
        integrations = call_kwargs["integrations"]

        # Should have 4 integrations
        assert len(integrations) == 4

    @patch("app.sentry.sentry_sdk")
    def test_sets_before_send_hooks(self, mock_sentry):
        """Should configure before_send and before_send_transaction hooks."""
        from app.sentry import init_sentry, _before_send, _before_send_transaction

        settings = MagicMock()
        settings.SENTRY_DSN = "https://xxx@sentry.io/123"
        settings.SENTRY_ENVIRONMENT = "test"
        settings.SENTRY_RELEASE = "1.0.0"
        settings.SENTRY_TRACES_SAMPLE_RATE = 0.1
        settings.SENTRY_PROFILES_SAMPLE_RATE = 0.1
        settings.APP_VERSION = "1.0.0"

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            init_sentry(settings)

        call_kwargs = mock_sentry.init.call_args[1]
        assert call_kwargs["before_send"] == _before_send
        assert call_kwargs["before_send_transaction"] == _before_send_transaction


class TestSetUserContext:
    """Tests for user context setting."""

    @patch("app.sentry.sentry_sdk")
    def test_sets_user_and_tenant_tag(self, mock_sentry):
        """Should set user context and tenant tag."""
        from app.sentry import set_user_context

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            set_user_context(
                user_id="user-123",
                tenant_id="tenant-456",
                email="user@example.com",
            )

        mock_sentry.set_user.assert_called_once_with({
            "id": "user-123",
            "email": "user@example.com",
        })
        mock_sentry.set_tag.assert_called_once_with("tenant_id", "tenant-456")
        mock_sentry.set_context.assert_called_once_with(
            "tenant", {"tenant_id": "tenant-456"}
        )

    @patch("app.sentry.sentry_sdk")
    def test_sets_user_without_email(self, mock_sentry):
        """Should set user context without email if not provided."""
        from app.sentry import set_user_context

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            set_user_context(
                user_id="user-123",
                tenant_id="tenant-456",
            )

        mock_sentry.set_user.assert_called_once_with({
            "id": "user-123",
        })

    @patch("app.sentry.sentry_sdk")
    def test_sets_user_with_username(self, mock_sentry):
        """Should include username in user context if provided."""
        from app.sentry import set_user_context

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            set_user_context(
                user_id="user-123",
                tenant_id="tenant-456",
                username="alice",
            )

        mock_sentry.set_user.assert_called_once_with({
            "id": "user-123",
            "username": "alice",
        })

    def test_does_nothing_when_sdk_not_available(self):
        """Should not raise errors when SDK is not available."""
        from app.sentry import set_user_context

        with patch("app.sentry.SENTRY_AVAILABLE", False):
            # Should not raise
            set_user_context(
                user_id="user-123",
                tenant_id="tenant-456",
            )

    @patch("app.sentry.sentry_sdk")
    def test_handles_exception_gracefully(self, mock_sentry):
        """Should not raise on exception during context setting."""
        from app.sentry import set_user_context

        mock_sentry.set_user.side_effect = Exception("Sentry error")

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            # Should not raise
            set_user_context(
                user_id="user-123",
                tenant_id="tenant-456",
            )


class TestClearUserContext:
    """Tests for clearing user context."""

    @patch("app.sentry.sentry_sdk")
    def test_clears_user_context(self, mock_sentry):
        """Should clear user context."""
        from app.sentry import clear_user_context

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            clear_user_context()

        mock_sentry.set_user.assert_called_once_with(None)

    def test_does_nothing_when_sdk_not_available(self):
        """Should not raise when SDK is not available."""
        from app.sentry import clear_user_context

        with patch("app.sentry.SENTRY_AVAILABLE", False):
            # Should not raise
            clear_user_context()


class TestCaptureMessage:
    """Tests for manual message capture."""

    @patch("app.sentry.sentry_sdk")
    def test_captures_message_with_extras(self, mock_sentry):
        """Should capture message with extra context."""
        from app.sentry import capture_message

        mock_sentry.capture_message.return_value = "event-id-123"

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            result = capture_message(
                "Test message",
                level="warning",
                custom_field="value",
            )

        assert result == "event-id-123"
        mock_sentry.capture_message.assert_called_once()

    def test_returns_none_when_sdk_not_available(self):
        """Should return None when SDK is not available."""
        from app.sentry import capture_message

        with patch("app.sentry.SENTRY_AVAILABLE", False):
            result = capture_message("Test message")

        assert result is None

    @patch("app.sentry.sentry_sdk")
    def test_returns_none_on_exception(self, mock_sentry):
        """Should return None on capture exception."""
        from app.sentry import capture_message

        mock_sentry.push_scope.side_effect = Exception("Sentry error")

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            result = capture_message("Test message")

        assert result is None


class TestCaptureException:
    """Tests for manual exception capture."""

    @patch("app.sentry.sentry_sdk")
    def test_captures_exception_with_extras(self, mock_sentry):
        """Should capture exception with extra context."""
        from app.sentry import capture_exception

        mock_sentry.capture_exception.return_value = "event-id-456"

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            exc = ValueError("Test error")
            result = capture_exception(exc, operation="test_op")

        assert result == "event-id-456"
        mock_sentry.capture_exception.assert_called_once()

    def test_returns_none_when_sdk_not_available(self):
        """Should return None when SDK is not available."""
        from app.sentry import capture_exception

        with patch("app.sentry.SENTRY_AVAILABLE", False):
            result = capture_exception(ValueError("Test"))

        assert result is None


class TestAddBreadcrumb:
    """Tests for breadcrumb adding."""

    @patch("app.sentry.sentry_sdk")
    def test_adds_breadcrumb(self, mock_sentry):
        """Should add breadcrumb with all parameters."""
        from app.sentry import add_breadcrumb

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            add_breadcrumb(
                message="User logged in",
                category="auth",
                level="info",
                data={"method": "oauth2"},
            )

        mock_sentry.add_breadcrumb.assert_called_once_with(
            message="User logged in",
            category="auth",
            level="info",
            data={"method": "oauth2"},
        )

    def test_does_nothing_when_sdk_not_available(self):
        """Should not raise when SDK is not available."""
        from app.sentry import add_breadcrumb

        with patch("app.sentry.SENTRY_AVAILABLE", False):
            # Should not raise
            add_breadcrumb("Test message")


class TestSetTag:
    """Tests for tag setting."""

    @patch("app.sentry.sentry_sdk")
    def test_sets_tag(self, mock_sentry):
        """Should set a tag."""
        from app.sentry import set_tag

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            set_tag("feature", "checkout")

        mock_sentry.set_tag.assert_called_once_with("feature", "checkout")

    def test_does_nothing_when_sdk_not_available(self):
        """Should not raise when SDK is not available."""
        from app.sentry import set_tag

        with patch("app.sentry.SENTRY_AVAILABLE", False):
            # Should not raise
            set_tag("key", "value")


class TestSetContext:
    """Tests for context setting."""

    @patch("app.sentry.sentry_sdk")
    def test_sets_context(self, mock_sentry):
        """Should set a context."""
        from app.sentry import set_context

        with patch("app.sentry.SENTRY_AVAILABLE", True):
            set_context("order", {"order_id": "123", "total": 99.99})

        mock_sentry.set_context.assert_called_once_with(
            "order", {"order_id": "123", "total": 99.99}
        )

    def test_does_nothing_when_sdk_not_available(self):
        """Should not raise when SDK is not available."""
        from app.sentry import set_context

        with patch("app.sentry.SENTRY_AVAILABLE", False):
            # Should not raise
            set_context("name", {"key": "value"})
