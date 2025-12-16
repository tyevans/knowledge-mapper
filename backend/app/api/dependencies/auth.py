"""Authentication dependencies for OAuth token validation.

This module supports dual token validation:
- Keycloak tokens: Validated via JWKS from OAuth provider
- App tokens: Validated via backend-issued RSA keys

Token flow:
1. User authenticates via Keycloak -> Gets Keycloak token
2. User calls /auth/tenants -> Lists available tenants (using Keycloak token)
3. User calls /auth/select-tenant -> Gets app token with tenant context
4. User calls API endpoints -> Uses app token for all subsequent requests

Architecture:
- RateLimitValidator: Handles rate limiting (SRP)
- TokenValidatorRouter: Routes to AppTokenValidator or KeycloakTokenValidator (SRP/Strategy)
- get_current_user: Orchestrates the authentication flow
"""
import logging
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.rate_limit import get_rate_limiter, RateLimiter
from app.schemas.auth import AuthenticatedUser
from app.services.jwks_client import get_jwks_client, JWKSClient
from app.services.token_revocation import (
    get_token_revocation_service,
    TokenRevocationService,
)
from app.api.dependencies.auth_validators import (
    RateLimitValidator,
    TokenValidatorRouter,
    create_token_validator_router,
)


logger = logging.getLogger(__name__)

# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(security)
    ],
    jwks_client: Annotated[JWKSClient, Depends(get_jwks_client)],
    rate_limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    token_revocation_service: Annotated[
        TokenRevocationService, Depends(get_token_revocation_service)
    ],
) -> AuthenticatedUser:
    """
    FastAPI dependency to validate OAuth token and extract user context.

    This dependency orchestrates the authentication flow using specialized validators:
    - RateLimitValidator: Enforces rate limits
    - TokenValidatorRouter: Routes to appropriate token validator

    The flow:
    1. Rate limiting check (prevents brute force/DoS attacks)
    2. Extracts Bearer token from Authorization header
    3. Routes to appropriate validator (App or Keycloak)
    4. Validates JWT and checks revocation
    5. Returns AuthenticatedUser for use in route handlers

    Args:
        request: FastAPI Request object (for extracting client IP)
        credentials: HTTP Bearer credentials from Authorization header
        jwks_client: JWKS client for fetching OAuth provider public keys
        rate_limiter: Rate limiter for distributed rate limiting
        token_revocation_service: Token revocation service for blacklist checking

    Returns:
        AuthenticatedUser: Authenticated user context with user_id, tenant_id, and scopes

    Raises:
        HTTPException: 401 Unauthorized if token is invalid, expired, revoked, or missing
        HTTPException: 429 Too Many Requests if rate limit exceeded
        HTTPException: 503 Service Unavailable if JWKS fetch or revocation check fails

    Example:
        >>> from app.api.dependencies.auth import get_current_user
        >>>
        >>> @router.get("/protected")
        >>> async def protected_route(user: Annotated[AuthenticatedUser, Depends(get_current_user)]):
        ...     return {"user_id": user.user_id, "tenant_id": user.tenant_id}
    """
    # Create validators
    rate_limit_validator = RateLimitValidator(rate_limiter)
    token_validator = create_token_validator_router(jwks_client)

    # Extract client IP for rate limiting
    client_ip = request.client.host if request.client else "unknown"

    # Step 1: Check general rate limit
    await rate_limit_validator.check_general_limit(client_ip)

    # Step 2: Validate credentials presence
    if credentials is None:
        logger.warning("Missing Authorization header")
        await rate_limit_validator.record_failed_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "missing_token",
                "error_description": "Authorization header with Bearer token is required",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Step 3: Validate token
    try:
        return await token_validator.validate(
            credentials.credentials,
            token_revocation_service,
        )
    except HTTPException as e:
        # Record failed auth attempt for 401 errors
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            await rate_limit_validator.record_failed_attempt(client_ip)
        raise


# Type alias for dependency injection
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


async def require_tenant_context(user: CurrentUser) -> AuthenticatedUser:
    """
    Dependency that requires tenant context in the authenticated user.

    Use this for routes that need multi-tenant isolation. Routes like
    /auth/tenants and /auth/select-tenant don't need this since they
    operate before tenant selection.

    Args:
        user: Authenticated user from get_current_user

    Returns:
        AuthenticatedUser with guaranteed tenant_id

    Raises:
        HTTPException: 403 Forbidden if no tenant context
    """
    if not user.has_tenant:
        logger.warning(
            "Tenant context required but not present",
            extra={"user_id": user.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "tenant_required",
                "error_description": "This endpoint requires tenant selection. "
                "Please call /api/v1/auth/select-tenant/{tenant_id} first.",
            },
        )
    return user


# Type alias for routes requiring tenant context
CurrentUserWithTenant = Annotated[AuthenticatedUser, Depends(require_tenant_context)]
