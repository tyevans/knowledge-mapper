"""
Sentry error tracking integration for Knowledge Mapper.

This module provides optional Sentry SDK integration for production
error tracking. It follows a fail-open pattern where the application
continues functioning normally if Sentry is misconfigured or unavailable.

Features:
- Automatic exception capture with stack traces
- Tenant and user context attachment (multi-tenancy aware)
- PII filtering via before_send hook
- Release tracking for deployment correlation
- FastAPI and SQLAlchemy integrations

Environment Variables:
    SENTRY_DSN: Sentry Data Source Name (required to enable)
    SENTRY_ENVIRONMENT: Environment tag (default: "development")
    SENTRY_TRACES_SAMPLE_RATE: Trace sampling rate (default: 0.1)
    SENTRY_RELEASE: Release version (default: APP_VERSION from settings)

Usage:
    from app.sentry import init_sentry
    from app.core.config import settings

    init_sentry(settings)

Architecture Notes:
    - Follows fail-open pattern: If Sentry DSN is not configured or invalid,
      the application starts normally without error tracking
    - Integrates with existing tenant context middleware for multi-tenant
      error correlation
    - PII filtering removes sensitive data before transmission
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Sentry SDK imports wrapped in try-except for graceful degradation
# when sentry-sdk is not installed
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False
    sentry_sdk = None  # type: ignore[assignment]
    logger.info("sentry-sdk not installed - error tracking disabled")


# PII fields to filter from Sentry events
# These field names (case-insensitive) will have their values replaced with "[Filtered]"
PII_FIELDS = frozenset({
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "auth_token",
    "refresh_token",
    "credentials",
    "credit_card",
    "card_number",
    "cvv",
    "ssn",
    "social_security",
    "token",
    "private_key",
    "secret_key",
})

# Headers to filter from Sentry events (contain auth tokens)
SENSITIVE_HEADERS = frozenset({
    "authorization",
    "x-api-key",
    "x-auth-token",
    "cookie",
    "set-cookie",
})


def _filter_dict(data: dict[str, Any], sensitive_keys: frozenset[str]) -> None:
    """
    Filter sensitive keys from a dictionary in-place.

    Args:
        data: Dictionary to filter
        sensitive_keys: Set of key names to filter (case-insensitive matching)
    """
    for key in list(data.keys()):
        if key.lower() in sensitive_keys:
            data[key] = "[Filtered]"


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Sentry before_send hook for PII filtering and event enrichment.

    This function runs before every event is sent to Sentry, allowing:
    - Filtering of sensitive data (passwords, tokens, etc.)
    - Event modification or enrichment
    - Conditional event dropping (return None)

    Args:
        event: The Sentry event dictionary
        hint: Additional context (exception info, etc.)

    Returns:
        Modified event dict, or None to drop the event
    """
    # Filter request body data for PII
    if "request" in event:
        request_data = event["request"]

        # Filter request body data
        if "data" in request_data and isinstance(request_data["data"], dict):
            _filter_dict(request_data["data"], PII_FIELDS)

        # Filter headers for sensitive tokens
        if "headers" in request_data and isinstance(request_data["headers"], dict):
            _filter_dict(request_data["headers"], SENSITIVE_HEADERS)

        # Filter query string parameters
        if "query_string" in request_data and isinstance(request_data["query_string"], str):
            # For query strings, we can't easily filter in-place, so just check for sensitive params
            qs = request_data["query_string"].lower()
            for field in PII_FIELDS:
                if field in qs:
                    request_data["query_string"] = "[Filtered]"
                    break

    # Filter breadcrumb data
    if "breadcrumbs" in event:
        breadcrumbs = event.get("breadcrumbs", {})
        if isinstance(breadcrumbs, dict):
            for breadcrumb in breadcrumbs.get("values", []):
                if "data" in breadcrumb and isinstance(breadcrumb["data"], dict):
                    _filter_dict(breadcrumb["data"], PII_FIELDS)

    # Filter extra data
    if "extra" in event and isinstance(event["extra"], dict):
        _filter_dict(event["extra"], PII_FIELDS)

    # Filter contexts for sensitive data
    if "contexts" in event and isinstance(event["contexts"], dict):
        for context_name, context_data in event["contexts"].items():
            if isinstance(context_data, dict):
                _filter_dict(context_data, PII_FIELDS)

    return event


def _before_send_transaction(
    event: dict[str, Any], hint: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """
    Sentry before_send_transaction hook for filtering performance transactions.

    This applies the same PII filtering to performance monitoring data.

    Args:
        event: The Sentry transaction event dictionary
        hint: Additional context

    Returns:
        Modified event dict, or None to drop the transaction
    """
    # Apply same filtering as regular events
    return _before_send(event, hint)


def init_sentry(settings: Any) -> bool:
    """
    Initialize Sentry SDK with FastAPI integration.

    This function configures the Sentry SDK for error tracking in production.
    It follows a fail-open pattern - if Sentry DSN is not configured or
    initialization fails, the application continues without error tracking.

    Args:
        settings: Application settings instance with Sentry configuration.
                  Expected attributes:
                  - SENTRY_DSN: str
                  - SENTRY_ENVIRONMENT: str
                  - SENTRY_RELEASE: str (optional)
                  - SENTRY_TRACES_SAMPLE_RATE: float
                  - SENTRY_PROFILES_SAMPLE_RATE: float
                  - APP_VERSION: str

    Returns:
        True if Sentry was successfully initialized, False otherwise

    Example:
        from app.sentry import init_sentry
        from app.core.config import settings

        if init_sentry(settings):
            print("Sentry error tracking enabled")
    """
    # Check if sentry-sdk is available
    if not SENTRY_AVAILABLE:
        logger.info("Sentry SDK not installed - skipping initialization")
        return False

    # Check if Sentry is configured
    sentry_dsn = getattr(settings, "SENTRY_DSN", "")
    if not sentry_dsn:
        logger.info("SENTRY_DSN not configured - error tracking disabled")
        return False

    try:
        # Get configuration values with safe defaults
        environment = getattr(settings, "SENTRY_ENVIRONMENT", "development")
        release = getattr(settings, "SENTRY_RELEASE", "") or getattr(
            settings, "APP_VERSION", "unknown"
        )
        traces_sample_rate = getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.1)
        profiles_sample_rate = getattr(settings, "SENTRY_PROFILES_SAMPLE_RATE", 0.1)

        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=environment,
            release=release,
            # Enable performance monitoring (traces)
            traces_sample_rate=traces_sample_rate,
            # Profile configuration (if available in plan)
            profiles_sample_rate=profiles_sample_rate,
            # Integrations
            integrations=[
                # FastAPI integration with URL-based transaction naming
                # Groups errors by endpoint pattern rather than full URL
                FastApiIntegration(transaction_style="url"),
                # SQLAlchemy integration for database query tracking
                SqlalchemyIntegration(),
                # Asyncio integration for proper async context tracking
                AsyncioIntegration(),
                # Logging integration - captures log messages as breadcrumbs
                LoggingIntegration(
                    level=logging.INFO,  # Capture INFO and above as breadcrumbs
                    event_level=logging.ERROR,  # Create events for ERROR and above
                ),
            ],
            # PII filtering hooks
            before_send=_before_send,
            before_send_transaction=_before_send_transaction,
            # Don't send default PII (email, username in user context)
            # We control this manually via set_user_context
            send_default_pii=False,
            # Attach stack traces to captured messages
            attach_stacktrace=True,
            # Max breadcrumbs to capture
            max_breadcrumbs=50,
            # Include local variables in stack traces (helpful for debugging)
            # Set to False in highly sensitive environments
            include_local_variables=True,
            # Enable source context for better stack traces
            include_source_context=True,
        )

        # Log successful initialization (truncate DSN for security)
        dsn_preview = sentry_dsn[:20] + "..." if len(sentry_dsn) > 20 else sentry_dsn
        logger.info(
            f"Sentry initialized - DSN: {dsn_preview}, "
            f"environment: {environment}, "
            f"release: {release}"
        )
        return True

    except Exception as e:
        # Fail-open: Log error but don't crash the application
        logger.error(f"Failed to initialize Sentry: {e}")
        return False


def set_user_context(
    user_id: str,
    tenant_id: str,
    email: Optional[str] = None,
    username: Optional[str] = None,
) -> None:
    """
    Set Sentry user context for error correlation.

    This function should be called after successful authentication to
    attach user information to all subsequent Sentry events. It enables
    filtering and searching errors by user or tenant in the Sentry UI.

    The user context persists for the duration of the request/scope and
    is automatically cleared at the end.

    Args:
        user_id: Unique user identifier (from JWT sub claim)
        tenant_id: Tenant identifier (from JWT tenant_id claim)
        email: Optional user email
        username: Optional username

    Example:
        from app.sentry import set_user_context

        # In authentication dependency or middleware
        set_user_context(
            user_id=token_data.sub,
            tenant_id=token_data.tenant_id,
            email=token_data.email
        )
    """
    if not SENTRY_AVAILABLE or sentry_sdk is None:
        return

    try:
        # Set user context - this attaches to all events in the current scope
        user_context: dict[str, Any] = {
            "id": user_id,
        }

        # Only include email/username if provided (PII consideration)
        if email:
            user_context["email"] = email
        if username:
            user_context["username"] = username

        sentry_sdk.set_user(user_context)

        # Set tenant_id as a tag for easier filtering in Sentry dashboard
        # Tags are indexed and searchable, making tenant-based queries fast
        sentry_sdk.set_tag("tenant_id", tenant_id)

        # Also set tenant_id in context for additional visibility
        sentry_sdk.set_context("tenant", {"tenant_id": tenant_id})

    except Exception as e:
        # Fail silently - don't break the request for Sentry issues
        logger.debug(f"Failed to set Sentry user context: {e}")


def clear_user_context() -> None:
    """
    Clear Sentry user context.

    This is typically called on logout or at the end of request processing
    to ensure user context doesn't leak between requests in edge cases.
    """
    if not SENTRY_AVAILABLE or sentry_sdk is None:
        return

    try:
        sentry_sdk.set_user(None)
    except Exception:
        # Fail silently
        pass


def capture_message(
    message: str,
    level: str = "info",
    **extra: Any,
) -> Optional[str]:
    """
    Manually capture a message to Sentry.

    Use this for important business events or warnings that should be
    tracked even if they're not exceptions.

    Args:
        message: The message to capture
        level: Severity level (debug, info, warning, error, fatal)
        **extra: Additional context data to attach to the event

    Returns:
        Sentry event ID if captured, None otherwise

    Example:
        from app.sentry import capture_message

        event_id = capture_message(
            "High-value transaction completed",
            level="info",
            transaction_id="txn-123",
            amount=10000
        )
    """
    if not SENTRY_AVAILABLE or sentry_sdk is None:
        return None

    try:
        with sentry_sdk.push_scope() as scope:
            for key, value in extra.items():
                scope.set_extra(key, value)
            return sentry_sdk.capture_message(message, level=level)
    except Exception:
        return None


def capture_exception(
    exception: Optional[BaseException] = None,
    **extra: Any,
) -> Optional[str]:
    """
    Manually capture an exception to Sentry.

    Use this when you catch an exception but still want to track it in Sentry
    without re-raising it.

    Args:
        exception: The exception to capture (uses current exception if None)
        **extra: Additional context data to attach to the event

    Returns:
        Sentry event ID if captured, None otherwise

    Example:
        from app.sentry import capture_exception

        try:
            risky_operation()
        except Exception as e:
            capture_exception(e, operation="risky_operation", retry_count=3)
            # Handle gracefully without re-raising
    """
    if not SENTRY_AVAILABLE or sentry_sdk is None:
        return None

    try:
        with sentry_sdk.push_scope() as scope:
            for key, value in extra.items():
                scope.set_extra(key, value)
            return sentry_sdk.capture_exception(exception)
    except Exception:
        return None


def add_breadcrumb(
    message: str,
    category: str = "custom",
    level: str = "info",
    data: Optional[dict[str, Any]] = None,
) -> None:
    """
    Add a breadcrumb to the current Sentry scope.

    Breadcrumbs are a trail of events that led up to an error.
    They help understand the sequence of actions before a crash.

    Args:
        message: Descriptive message for the breadcrumb
        category: Category for grouping (e.g., "auth", "database", "http")
        level: Severity level (debug, info, warning, error, fatal)
        data: Optional additional data

    Example:
        from app.sentry import add_breadcrumb

        add_breadcrumb(
            message="User logged in",
            category="auth",
            level="info",
            data={"method": "oauth2"}
        )
    """
    if not SENTRY_AVAILABLE or sentry_sdk is None:
        return

    try:
        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            data=data or {},
        )
    except Exception:
        # Fail silently
        pass


def set_tag(key: str, value: str) -> None:
    """
    Set a tag on the current Sentry scope.

    Tags are indexed key-value pairs that can be used for filtering
    and searching in the Sentry dashboard.

    Args:
        key: Tag name
        value: Tag value

    Example:
        from app.sentry import set_tag

        set_tag("feature", "checkout")
        set_tag("payment_provider", "stripe")
    """
    if not SENTRY_AVAILABLE or sentry_sdk is None:
        return

    try:
        sentry_sdk.set_tag(key, value)
    except Exception:
        # Fail silently
        pass


def set_context(name: str, context: dict[str, Any]) -> None:
    """
    Set a context on the current Sentry scope.

    Contexts are additional structured data attached to events.
    Unlike tags, contexts are not indexed but can contain more complex data.

    Args:
        name: Context name (e.g., "order", "request")
        context: Dictionary of context data

    Example:
        from app.sentry import set_context

        set_context("order", {
            "order_id": "order-123",
            "total": 99.99,
            "items_count": 3
        })
    """
    if not SENTRY_AVAILABLE or sentry_sdk is None:
        return

    try:
        sentry_sdk.set_context(name, context)
    except Exception:
        # Fail silently
        pass
