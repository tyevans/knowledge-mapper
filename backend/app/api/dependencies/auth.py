"""Authentication dependencies for OAuth token validation.

This module supports dual token validation:
- Keycloak tokens: Validated via JWKS from OAuth provider
- App tokens: Validated via backend-issued RSA keys

Token flow:
1. User authenticates via Keycloak -> Gets Keycloak token
2. User calls /auth/tenants -> Lists available tenants (using Keycloak token)
3. User calls /auth/select-tenant -> Gets app token with tenant context
4. User calls API endpoints -> Uses app token for all subsequent requests
"""
import logging
import uuid
from typing import Annotated, Optional

import httpx
import jwt
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidSignatureError,
    InvalidTokenError,
)
from pydantic import ValidationError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings
from app.core.security import get_unverified_jwt_header
from app.core.rate_limit import get_rate_limiter, RateLimiter, RateLimitExceeded
from app.schemas.auth import AuthenticatedUser, TokenPayload
from app.services.jwks_client import get_jwks_client, JWKSClient
from app.services.token_revocation import (
    get_token_revocation_service,
    TokenRevocationService,
)
from app.services.app_token_service import get_app_token_service


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

    This dependency implements the complete OAuth 2.0 Bearer token validation flow:
    1. Rate limiting check (prevents brute force/DoS attacks)
    2. Extracts Bearer token from Authorization header
    3. Validates JWT signature using JWKS public keys
    4. Validates standard JWT claims (exp, iss, aud, jti)
    5. Checks if token has been revoked (supports logout and security incidents)
    6. Extracts user context (user_id, tenant_id, scopes)
    7. Returns AuthenticatedUser for use in route handlers

    The dependency handles key rotation by attempting to refresh JWKS when a
    signing key is not found in the cache. It also enforces multi-tenant
    architecture by requiring a tenant_id claim in all tokens.

    Rate limiting prevents:
    - Brute force authentication attacks
    - Denial of service attacks
    - Token enumeration attacks

    Token revocation enables:
    - Secure logout (invalidate access tokens immediately)
    - Compromised token invalidation
    - Forced logout for security incidents

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
    # Extract client IP for rate limiting
    client_ip = request.client.host if request.client else "unknown"

    # SECURITY: Rate limiting - Check general auth rate limit
    # This prevents brute force attacks and DoS by limiting requests per IP
    try:
        await rate_limiter.check_rate_limit(client_ip, is_failed_auth=False)
    except RateLimitExceeded as e:
        logger.warning(
            "Rate limit exceeded for authentication",
            extra={
                "client_ip": client_ip,
                "limit_type": e.limit_type,
                "retry_after": e.retry_after,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "error_description": "Too many authentication attempts. Please try again later.",
            },
            headers={"Retry-After": str(e.retry_after)},
        )

    # Check if Authorization header is present
    if credentials is None:
        logger.warning("Missing Authorization header")
        # Track failed auth attempt before raising
        try:
            await rate_limiter.check_rate_limit(client_ip, is_failed_auth=True)
        except RateLimitExceeded as e:
            logger.warning(
                "Failed auth rate limit exceeded",
                extra={
                    "client_ip": client_ip,
                    "retry_after": e.retry_after,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "error_description": "Too many failed authentication attempts. Please try again later.",
                },
                headers={"Retry-After": str(e.retry_after)},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "missing_token",
                "error_description": "Authorization header with Bearer token is required",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Wrap entire validation in try-except to track failed auth attempts
    try:
        # Extract header to get key ID (kid) before validation
        return await _validate_token_and_get_user(token, jwks_client, token_revocation_service)
    except HTTPException as e:
        # Check if this is an auth failure (401) that should count toward failed auth rate limit
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            # Track failed auth attempt
            try:
                await rate_limiter.check_rate_limit(client_ip, is_failed_auth=True)
            except RateLimitExceeded as rate_limit_err:
                logger.warning(
                    "Failed auth rate limit exceeded",
                    extra={
                        "client_ip": client_ip,
                        "retry_after": rate_limit_err.retry_after,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "rate_limit_exceeded",
                        "error_description": "Too many failed authentication attempts. Please try again later.",
                    },
                    headers={"Retry-After": str(rate_limit_err.retry_after)},
                )
        # Re-raise the original HTTPException (auth failure or other error)
        raise


def _get_issuer_from_token(token: str) -> str | None:
    """
    Extract issuer claim from token without verification.

    Used to determine which validation path to take (app token vs Keycloak token).

    Args:
        token: JWT token string

    Returns:
        Issuer claim value or None if not present
    """
    try:
        # Decode without verification to peek at claims
        unverified = jwt.decode(token, options={"verify_signature": False})
        return unverified.get("iss")
    except Exception:
        return None


async def _validate_app_token(
    token: str,
    token_revocation_service: TokenRevocationService,
) -> AuthenticatedUser:
    """
    Validate an app-issued JWT token.

    App tokens are issued by this backend after tenant selection.
    They are signed with the backend's RSA private key.

    Args:
        token: JWT token string
        token_revocation_service: Token revocation service for blacklist checking

    Returns:
        AuthenticatedUser: Authenticated user context

    Raises:
        HTTPException: 401 Unauthorized if token is invalid or revoked
    """
    app_token_service = get_app_token_service()

    try:
        # Validate and decode using app token service
        claims = app_token_service.validate_token(token)

    except ExpiredSignatureError:
        logger.warning("App token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "expired_token",
                "error_description": "App token has expired",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    except InvalidSignatureError as e:
        logger.warning(f"App token signature validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "error_description": "App token signature validation failed",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    except InvalidTokenError as e:
        logger.warning(f"App token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "error_description": "App token validation failed",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract required claims
    jti = claims.get("jti")
    if not jti:
        logger.error("App token missing 'jti' claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "error_description": "App token missing required claims",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if token has been revoked
    try:
        is_revoked = await token_revocation_service.is_token_revoked(jti)
        if is_revoked:
            logger.warning(
                "App token has been revoked",
                extra={"jti": jti, "sub": claims.get("sub")},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_token",
                    "error_description": "Token has been revoked",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Token revocation check failed - rejecting app token",
            extra={"jti": jti, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "service_unavailable",
                "error_description": "Unable to verify token revocation status",
            },
        )

    # App tokens always have tenant_id
    tenant_id = claims.get("tenant_id")
    if not tenant_id:
        logger.error("App token missing 'tenant_id' claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "error_description": "App token missing required 'tenant_id' claim",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate tenant_id format
    try:
        uuid_obj = uuid.UUID(tenant_id)
        tenant_id = str(uuid_obj).lower()
    except (ValueError, AttributeError) as e:
        logger.error(f"Invalid tenant_id format in app token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "error_description": "Invalid tenant_id format",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # App tokens store scopes as a list (not space-separated)
    scopes = claims.get("scopes", [])
    if isinstance(scopes, str):
        scopes = scopes.split()

    logger.info(
        "User authenticated via app token",
        extra={
            "user_id": claims.get("sub"),
            "tenant_id": tenant_id,
            "scopes": scopes,
        },
    )

    return AuthenticatedUser(
        user_id=claims.get("sub"),
        tenant_id=tenant_id,
        jti=jti,
        exp=claims.get("exp"),
        email=claims.get("email"),
        name=claims.get("name"),
        scopes=scopes,
        issuer=claims.get("iss"),
    )


async def _validate_keycloak_token(
    token: str,
    jwks_client: JWKSClient,
    token_revocation_service: TokenRevocationService,
) -> AuthenticatedUser:
    """
    Validate a Keycloak-issued JWT token.

    Keycloak tokens are validated using JWKS (public keys fetched from Keycloak).
    These tokens may or may not have tenant_id (depends on user attribute).

    Args:
        token: JWT token string
        jwks_client: JWKS client for fetching OAuth provider public keys
        token_revocation_service: Token revocation service for blacklist checking

    Returns:
        AuthenticatedUser: Authenticated user context

    Raises:
        HTTPException: 401 Unauthorized if token is invalid or revoked
        HTTPException: 503 Service Unavailable if JWKS fetch fails
    """
    # Extract header to get key ID (kid) before validation
    try:
        header = get_unverified_jwt_header(token)
        key_id = header.get("kid")
        alg = header.get("alg")

        # SECURITY: Prevent algorithm confusion attacks
        if not alg or alg not in settings.OAUTH_ALGORITHMS:
            logger.warning(
                "Unsupported or missing JWT algorithm",
                extra={"algorithm": alg, "expected": settings.OAUTH_ALGORITHMS}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_token",
                    "error_description": "Unsupported JWT algorithm",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # SECURITY: Reject symmetric algorithms
        if alg.startswith("HS"):
            logger.warning("Symmetric algorithm rejected", extra={"algorithm": alg})
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_token",
                    "error_description": "Only asymmetric algorithms supported",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not key_id:
            logger.warning("JWT header missing 'kid' claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_token",
                    "error_description": "JWT header missing 'kid' (key ID) claim",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

    except DecodeError as e:
        logger.warning(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "error_description": "Malformed JWT token",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch signing key from JWKS
    try:
        signing_key = await jwks_client.get_signing_key(
            settings.OAUTH_ISSUER_URL, key_id, force_refresh=False
        )

        if signing_key is None:
            logger.info(f"Signing key not found, refreshing JWKS (kid: {key_id})")
            signing_key = await jwks_client.get_signing_key(
                settings.OAUTH_ISSUER_URL, key_id, force_refresh=True
            )

            if signing_key is None:
                logger.error(f"Signing key not found after refresh (kid: {key_id})")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "error": "invalid_token",
                        "error_description": "Signing key not found in JWKS",
                    },
                    headers={"WWW-Authenticate": "Bearer"},
                )

    except httpx.HTTPError as e:
        logger.error(f"JWKS fetch failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "service_unavailable",
                "error_description": "Unable to fetch signing keys from OAuth provider",
            },
        )

    # Validate and decode JWT
    try:
        payload = jwt.decode(
            token,
            key=jwt.PyJWK(signing_key).key,
            algorithms=settings.OAUTH_ALGORITHMS,
            issuer=settings.OAUTH_ISSUER_URL,
            audience=settings.OAUTH_AUDIENCE,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
                "verify_iat": True,
            },
        )

        token_payload = TokenPayload(**payload)

    except ExpiredSignatureError:
        logger.warning("JWT token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "expired_token",
                "error_description": "JWT token has expired",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    except InvalidSignatureError as e:
        logger.warning(f"JWT signature validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "error_description": "JWT signature validation failed",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    except InvalidTokenError as e:
        logger.warning(
            "JWT validation failed",
            extra={"error_type": type(e).__name__, "error_details": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "error_description": "JWT validation failed",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    except ValidationError as e:
        logger.warning(
            "JWT payload validation failed",
            extra={"error_type": "ValidationError", "error_details": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "error_description": "JWT validation failed",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check token revocation
    try:
        is_revoked = await token_revocation_service.is_token_revoked(token_payload.jti)
        if is_revoked:
            logger.warning(
                "Token has been revoked",
                extra={"jti": token_payload.jti, "sub": token_payload.sub},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_token",
                    "error_description": "Token has been revoked",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Token revocation check failed - rejecting token",
            extra={"jti": token_payload.jti, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "service_unavailable",
                "error_description": "Unable to verify token revocation status",
            },
        )

    # Extract tenant_id (optional for Keycloak tokens - user may not have selected tenant yet)
    tenant_id = token_payload.tenant_id
    if tenant_id:
        # Validate format if present
        try:
            uuid_obj = uuid.UUID(tenant_id)
            tenant_id = str(uuid_obj).lower()
        except (ValueError, AttributeError) as e:
            logger.error(f"Invalid tenant_id format in JWT token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_token",
                    "error_description": "Invalid tenant_id format",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Parse scopes
    scopes = token_payload.scope.split() if token_payload.scope else []

    if token_payload.realm_access and token_payload.realm_access.roles:
        scopes.extend(token_payload.realm_access.roles)

    if token_payload.custom_scopes:
        scopes.extend(token_payload.custom_scopes.split())

    logger.info(
        "User authenticated via Keycloak token",
        extra={
            "user_id": token_payload.sub,
            "tenant_id": tenant_id,
            "has_tenant": tenant_id is not None,
            "scopes": scopes,
        },
    )

    return AuthenticatedUser(
        user_id=token_payload.sub,
        tenant_id=tenant_id,
        jti=token_payload.jti,
        exp=token_payload.exp,
        email=token_payload.email,
        name=token_payload.name,
        scopes=scopes,
        issuer=token_payload.iss,
    )


async def _validate_token_and_get_user(
    token: str,
    jwks_client: JWKSClient,
    token_revocation_service: TokenRevocationService,
) -> AuthenticatedUser:
    """
    Internal helper to validate token and extract user context.

    Supports dual token validation:
    - App tokens (issuer = APP_JWT_ISSUER): Validated with backend RSA key
    - Keycloak tokens (issuer = OAUTH_ISSUER_URL): Validated with JWKS

    Args:
        token: JWT token string
        jwks_client: JWKS client for fetching OAuth provider public keys
        token_revocation_service: Token revocation service for blacklist checking

    Returns:
        AuthenticatedUser: Authenticated user context

    Raises:
        HTTPException: 401 Unauthorized if token is invalid or revoked
        HTTPException: 503 Service Unavailable if validation service fails
    """
    # Determine token type by peeking at issuer
    issuer = _get_issuer_from_token(token)

    if issuer == settings.APP_JWT_ISSUER:
        # App token - validate with backend RSA key
        return await _validate_app_token(token, token_revocation_service)
    elif issuer == settings.OAUTH_ISSUER_URL:
        # Keycloak token - validate with JWKS
        return await _validate_keycloak_token(token, jwks_client, token_revocation_service)
    else:
        # Unknown issuer
        logger.warning(
            "Unknown token issuer",
            extra={
                "issuer": issuer,
                "expected_app": settings.APP_JWT_ISSUER,
                "expected_oauth": settings.OAUTH_ISSUER_URL,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "error_description": "Unknown token issuer",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )


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
