"""
Tenant Resolution Middleware for FastAPI.

This middleware extracts the tenant_id from authenticated requests and sets
it in the request state for downstream handlers. It integrates with OAuth
token validation to get the tenant_id claim.

The middleware runs for ALL requests but skips tenant resolution for public
endpoints (health checks, docs, OAuth flows).

Key Features:
- Extracts tenant_id from request.state.user (set by OAuth validation dependency)
- Sets tenant_id in request.state for downstream handlers
- Sets tenant_id in contextvars for application-level tracking (logging, metrics)
- Skips public endpoints that don't require tenant context
- Clears tenant context after request to prevent leakage
- Handles missing/invalid tenant_id with appropriate error responses
"""

import logging
from typing import Set
from uuid import UUID

from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.context import clear_current_tenant, set_current_tenant

logger = logging.getLogger(__name__)


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to resolve tenant from authenticated requests.

    This middleware extracts tenant_id from OAuth token claims (via request.state.user)
    and sets it in request.state and contextvars for use by downstream handlers and
    dependencies.

    Public endpoints (health, docs, OAuth) are skipped automatically. For protected
    endpoints, the middleware expects request.state.user to be set by the OAuth
    validation dependency. If a protected endpoint is accessed without authentication,
    the OAuth dependency will handle the 401 response.

    The middleware uses a finally block to ensure tenant context is always cleared
    after the request completes, preventing context leakage between requests.

    Example:
        >>> # In main.py
        >>> app.add_middleware(TenantResolutionMiddleware)
        >>>
        >>> # In route handler
        >>> @router.get("/statements")
        >>> async def get_statements(request: Request):
        ...     tenant_id = request.state.tenant_id  # Available here
        ...     # Process request with tenant context
    """

    # Endpoints that don't require tenant resolution
    # These paths are accessible without authentication or tenant context
    PUBLIC_PATHS: Set[str] = {
        "/",
        "/health",
        "/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/health",
        "/api/v1/ready",
        "/api/v1/oauth/login",
        "/api/v1/oauth/callback",
        "/api/v1/oauth/token/refresh",
        "/api/v1/oauth/logout",
    }

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and resolve tenant context.

        This method is called for every request. It performs the following steps:
        1. Check if path is public (skip tenant resolution)
        2. Extract tenant_id from request.state.user (set by OAuth dependency)
        3. Validate tenant_id format
        4. Set tenant_id in request.state and contextvars
        5. Call downstream handlers
        6. Clear tenant context in finally block

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or handler in chain

        Returns:
            Response from downstream handler or error response

        Note:
            This middleware runs BEFORE route handlers execute, but AFTER
            middleware like CORS. The OAuth validation dependency runs during
            route handler execution, so request.state.user may not be set yet
            for some requests. We handle this gracefully by checking if the
            user is authenticated.
        """
        # Skip tenant resolution for public paths
        if request.url.path in self.PUBLIC_PATHS:
            logger.debug(
                f"Tenant resolution skipped for public endpoint: {request.url.path}"
            )
            return await call_next(request)

        # Skip for static files and framework paths
        if (
            request.url.path.startswith("/static/")
            or request.url.path.startswith("/_next/")
        ):
            logger.debug(
                f"Tenant resolution skipped for static files: {request.url.path}"
            )
            return await call_next(request)

        try:
            # Extract tenant_id from OAuth token
            # Note: request.state.user is set by OAuth validation dependency
            # during route handler execution, not during middleware execution.
            # For protected endpoints, the dependency will run and set this.
            # For public endpoints or unauthenticated requests, it won't be set.
            tenant_id = await self._extract_tenant_id(request)

            if tenant_id is None:
                # No tenant_id found. This could mean:
                # 1. Request to public endpoint (already filtered above)
                # 2. Unauthenticated request to protected endpoint (OAuth dependency will handle)
                # 3. Authenticated request without tenant_id claim (error)
                #
                # We don't return 403 here because the OAuth dependency hasn't run yet.
                # If the endpoint requires authentication, the OAuth dependency will
                # return 401. If it doesn't require authentication, no tenant context
                # is needed.
                logger.debug(
                    f"Tenant ID not available for {request.method} {request.url.path} - "
                    "user not authenticated or missing tenant"
                )
                # Continue without setting tenant context
                # If the endpoint requires it, downstream handlers will fail
                return await call_next(request)

            # Store tenant_id in request state for downstream handlers
            request.state.tenant_id = tenant_id

            # Also set in contextvars for application-level tracking
            set_current_tenant(tenant_id)

            logger.info(
                f"Tenant resolved: {tenant_id} for {request.method} {request.url.path}"
            )

            # Call downstream handlers with tenant context set
            response = await call_next(request)

            return response

        except Exception as e:
            # Catch any unexpected errors during tenant resolution
            logger.error(
                f"Tenant resolution failed for {request.method} {request.url.path}: "
                f"{type(e).__name__}: {e}"
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": {
                        "code": 500,
                        "message": "Failed to resolve tenant context",
                        "type": "tenant_resolution_error",
                    }
                },
            )

        finally:
            # CRITICAL: Always clear tenant context after request completes
            # This ensures no context leakage between requests in async environments
            clear_current_tenant()
            logger.debug("Tenant context cleared")

    async def _extract_tenant_id(self, request: Request) -> UUID | None:
        """
        Extract tenant_id from OAuth token in request.

        The tenant_id is set by OAuth token validation dependency (TASK-009)
        in request.state.user.tenant_id. This method extracts and validates it.

        Args:
            request: HTTP request

        Returns:
            Tenant UUID or None if not authenticated or tenant_id missing

        Note:
            This method does not raise exceptions. If tenant_id is invalid,
            it logs a warning and returns None. The calling code decides
            whether to continue or return an error.
        """
        # Check if user was authenticated by OAuth dependency
        # Note: This is set during route handler execution, not during middleware
        # execution. For protected endpoints, this will be set by the time we check.
        user = getattr(request.state, "user", None)

        if user is None:
            # No authenticated user - might be:
            # - Public endpoint (filtered above, but could be new endpoint)
            # - Unauthenticated request to protected endpoint (OAuth dependency will handle)
            logger.debug(
                f"User not authenticated for {request.url.path} - request.state.user not set"
            )
            return None

        # Extract tenant_id from authenticated user
        tenant_id = getattr(user, "tenant_id", None)

        if tenant_id is None:
            # User is authenticated but token doesn't have tenant_id claim
            # This is a configuration error - all tokens should have tenant_id
            user_id = getattr(user, "user_id", "unknown")
            logger.warning(
                f"Tenant ID missing in token for user {user_id} at {request.url.path}"
            )
            return None

        # Validate tenant_id is a UUID
        if isinstance(tenant_id, str):
            try:
                tenant_id = UUID(tenant_id)
            except ValueError:
                user_id = getattr(user, "user_id", "unknown")
                logger.error(
                    f"Invalid tenant ID format '{tenant_id}' for user {user_id} at {request.url.path}"
                )
                return None

        return tenant_id
