"""
Authentication validators extracted for Single Responsibility Principle.

This module contains specialized validators for the authentication flow:
- RateLimitValidator: Handles rate limiting checks
- AppTokenValidator: Validates backend-issued JWT tokens
- KeycloakTokenValidator: Validates Keycloak OAuth tokens
- TokenValidatorRouter: Routes to appropriate validator based on token issuer

Each validator has a single responsibility and can be tested independently.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Protocol

import httpx
import jwt
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidSignatureError,
    InvalidTokenError,
)
from pydantic import ValidationError
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import get_unverified_jwt_header
from app.schemas.auth import AuthenticatedUser, TokenPayload
from app.services.jwks_client import JWKSClient
from app.services.token_revocation import TokenRevocationService
from app.services.app_token_service import get_app_token_service
from app.core.rate_limit import RateLimiter, RateLimitExceeded


logger = logging.getLogger(__name__)


class AuthenticationError(HTTPException):
    """Standard authentication error with OAuth-compliant error response."""

    def __init__(
        self,
        error: str,
        error_description: str,
        status_code: int = status.HTTP_401_UNAUTHORIZED,
        headers: dict | None = None,
    ):
        default_headers = {"WWW-Authenticate": "Bearer"}
        if headers:
            default_headers.update(headers)

        super().__init__(
            status_code=status_code,
            detail={
                "error": error,
                "error_description": error_description,
            },
            headers=default_headers,
        )
        self.error = error
        self.error_description = error_description


class RateLimitValidator:
    """Validates rate limits for authentication requests.

    Responsibility: Check and enforce rate limits, nothing else.
    """

    def __init__(self, rate_limiter: RateLimiter):
        self._rate_limiter = rate_limiter

    async def check_general_limit(self, client_ip: str) -> None:
        """Check general authentication rate limit.

        Args:
            client_ip: Client IP address for rate limiting

        Raises:
            HTTPException: 429 if rate limit exceeded
        """
        try:
            await self._rate_limiter.check_rate_limit(client_ip, is_failed_auth=False)
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

    async def record_failed_attempt(self, client_ip: str) -> None:
        """Record a failed authentication attempt.

        Args:
            client_ip: Client IP address

        Raises:
            HTTPException: 429 if failed auth rate limit exceeded
        """
        try:
            await self._rate_limiter.check_rate_limit(client_ip, is_failed_auth=True)
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


class TokenValidator(ABC):
    """Abstract base class for token validators."""

    @abstractmethod
    async def validate(
        self,
        token: str,
        token_revocation_service: TokenRevocationService,
    ) -> AuthenticatedUser:
        """Validate a token and return the authenticated user.

        Args:
            token: JWT token string
            token_revocation_service: Service for checking token revocation

        Returns:
            AuthenticatedUser with user context

        Raises:
            AuthenticationError: If validation fails
        """
        pass


class AppTokenValidator(TokenValidator):
    """Validates backend-issued JWT tokens.

    Responsibility: Validate app tokens signed with backend RSA key.
    """

    async def validate(
        self,
        token: str,
        token_revocation_service: TokenRevocationService,
    ) -> AuthenticatedUser:
        """Validate an app-issued JWT token."""
        app_token_service = get_app_token_service()

        try:
            claims = app_token_service.validate_token(token)
        except ExpiredSignatureError:
            logger.warning("App token expired")
            raise AuthenticationError(
                error="expired_token",
                error_description="App token has expired",
            )
        except InvalidSignatureError as e:
            logger.warning(f"App token signature validation failed: {e}")
            raise AuthenticationError(
                error="invalid_token",
                error_description="App token signature validation failed",
            )
        except InvalidTokenError as e:
            logger.warning(f"App token validation failed: {e}")
            raise AuthenticationError(
                error="invalid_token",
                error_description="App token validation failed",
            )

        # Validate required claims
        jti = claims.get("jti")
        if not jti:
            logger.error("App token missing 'jti' claim")
            raise AuthenticationError(
                error="invalid_token",
                error_description="App token missing required claims",
            )

        # Check revocation
        await self._check_revocation(jti, claims.get("sub"), token_revocation_service)

        # Validate tenant_id
        tenant_id = self._validate_tenant_id(claims.get("tenant_id"))

        # Parse scopes
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

    async def _check_revocation(
        self,
        jti: str,
        sub: str | None,
        token_revocation_service: TokenRevocationService,
    ) -> None:
        """Check if token has been revoked."""
        try:
            is_revoked = await token_revocation_service.is_token_revoked(jti)
            if is_revoked:
                logger.warning(
                    "App token has been revoked",
                    extra={"jti": jti, "sub": sub},
                )
                raise AuthenticationError(
                    error="invalid_token",
                    error_description="Token has been revoked",
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

    def _validate_tenant_id(self, tenant_id: str | None) -> str:
        """Validate and normalize tenant_id."""
        if not tenant_id:
            logger.error("App token missing 'tenant_id' claim")
            raise AuthenticationError(
                error="invalid_token",
                error_description="App token missing required 'tenant_id' claim",
            )

        try:
            uuid_obj = uuid.UUID(tenant_id)
            return str(uuid_obj).lower()
        except (ValueError, AttributeError) as e:
            logger.error(f"Invalid tenant_id format in app token: {e}")
            raise AuthenticationError(
                error="invalid_token",
                error_description="Invalid tenant_id format",
            )


class KeycloakTokenValidator(TokenValidator):
    """Validates Keycloak OAuth tokens via JWKS.

    Responsibility: Validate Keycloak tokens using JWKS public keys.
    """

    def __init__(self, jwks_client: JWKSClient):
        self._jwks_client = jwks_client

    async def validate(
        self,
        token: str,
        token_revocation_service: TokenRevocationService,
    ) -> AuthenticatedUser:
        """Validate a Keycloak-issued JWT token."""
        # Extract and validate header
        key_id, alg = self._extract_and_validate_header(token)

        # Get signing key
        signing_key = await self._get_signing_key(key_id)

        # Decode and validate token
        token_payload = self._decode_token(token, signing_key)

        # Check revocation
        await self._check_revocation(token_payload, token_revocation_service)

        # Extract tenant_id (optional for Keycloak tokens)
        tenant_id = self._extract_tenant_id(token_payload.tenant_id)

        # Parse scopes
        scopes = self._extract_scopes(token_payload)

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

    def _extract_and_validate_header(self, token: str) -> tuple[str, str]:
        """Extract and validate JWT header."""
        try:
            header = get_unverified_jwt_header(token)
            key_id = header.get("kid")
            alg = header.get("alg")

            # Security: Prevent algorithm confusion attacks
            if not alg or alg not in settings.OAUTH_ALGORITHMS:
                logger.warning(
                    "Unsupported or missing JWT algorithm",
                    extra={"algorithm": alg, "expected": settings.OAUTH_ALGORITHMS}
                )
                raise AuthenticationError(
                    error="invalid_token",
                    error_description="Unsupported JWT algorithm",
                )

            # Security: Reject symmetric algorithms
            if alg.startswith("HS"):
                logger.warning("Symmetric algorithm rejected", extra={"algorithm": alg})
                raise AuthenticationError(
                    error="invalid_token",
                    error_description="Only asymmetric algorithms supported",
                )

            if not key_id:
                logger.warning("JWT header missing 'kid' claim")
                raise AuthenticationError(
                    error="invalid_token",
                    error_description="JWT header missing 'kid' (key ID) claim",
                )

            return key_id, alg

        except DecodeError as e:
            logger.warning(f"JWT decode error: {e}")
            raise AuthenticationError(
                error="invalid_token",
                error_description="Malformed JWT token",
            )

    async def _get_signing_key(self, key_id: str) -> dict:
        """Fetch signing key from JWKS."""
        try:
            signing_key = await self._jwks_client.get_signing_key(
                settings.OAUTH_ISSUER_URL, key_id, force_refresh=False
            )

            if signing_key is None:
                logger.info(f"Signing key not found, refreshing JWKS (kid: {key_id})")
                signing_key = await self._jwks_client.get_signing_key(
                    settings.OAUTH_ISSUER_URL, key_id, force_refresh=True
                )

                if signing_key is None:
                    logger.error(f"Signing key not found after refresh (kid: {key_id})")
                    raise AuthenticationError(
                        error="invalid_token",
                        error_description="Signing key not found in JWKS",
                    )

            return signing_key

        except httpx.HTTPError as e:
            logger.error(f"JWKS fetch failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "service_unavailable",
                    "error_description": "Unable to fetch signing keys from OAuth provider",
                },
            )

    def _decode_token(self, token: str, signing_key: dict) -> TokenPayload:
        """Decode and validate JWT token."""
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
            return TokenPayload(**payload)

        except ExpiredSignatureError:
            logger.warning("JWT token expired")
            raise AuthenticationError(
                error="expired_token",
                error_description="JWT token has expired",
            )
        except InvalidSignatureError as e:
            logger.warning(f"JWT signature validation failed: {e}")
            raise AuthenticationError(
                error="invalid_token",
                error_description="JWT signature validation failed",
            )
        except InvalidTokenError as e:
            logger.warning(
                "JWT validation failed",
                extra={"error_type": type(e).__name__, "error_details": str(e)}
            )
            raise AuthenticationError(
                error="invalid_token",
                error_description="JWT validation failed",
            )
        except ValidationError as e:
            logger.warning(
                "JWT payload validation failed",
                extra={"error_type": "ValidationError", "error_details": str(e)}
            )
            raise AuthenticationError(
                error="invalid_token",
                error_description="JWT validation failed",
            )

    async def _check_revocation(
        self,
        token_payload: TokenPayload,
        token_revocation_service: TokenRevocationService,
    ) -> None:
        """Check if token has been revoked."""
        try:
            is_revoked = await token_revocation_service.is_token_revoked(token_payload.jti)
            if is_revoked:
                logger.warning(
                    "Token has been revoked",
                    extra={"jti": token_payload.jti, "sub": token_payload.sub},
                )
                raise AuthenticationError(
                    error="invalid_token",
                    error_description="Token has been revoked",
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

    def _extract_tenant_id(self, tenant_id: str | None) -> str | None:
        """Extract and validate tenant_id if present."""
        if not tenant_id:
            return None

        try:
            uuid_obj = uuid.UUID(tenant_id)
            return str(uuid_obj).lower()
        except (ValueError, AttributeError) as e:
            logger.error(f"Invalid tenant_id format in JWT token: {e}")
            raise AuthenticationError(
                error="invalid_token",
                error_description="Invalid tenant_id format",
            )

    def _extract_scopes(self, token_payload: TokenPayload) -> list[str]:
        """Extract scopes from token payload."""
        scopes = token_payload.scope.split() if token_payload.scope else []

        if token_payload.realm_access and token_payload.realm_access.roles:
            scopes.extend(token_payload.realm_access.roles)

        if token_payload.custom_scopes:
            scopes.extend(token_payload.custom_scopes.split())

        return scopes


class TokenValidatorRouter:
    """Routes token validation to the appropriate validator based on issuer.

    This implements the Strategy pattern - selecting the correct validator
    based on the token's issuer claim.
    """

    def __init__(
        self,
        app_token_validator: AppTokenValidator,
        keycloak_token_validator: KeycloakTokenValidator,
    ):
        self._app_validator = app_token_validator
        self._keycloak_validator = keycloak_token_validator

    async def validate(
        self,
        token: str,
        token_revocation_service: TokenRevocationService,
    ) -> AuthenticatedUser:
        """Validate token by routing to appropriate validator.

        Args:
            token: JWT token string
            token_revocation_service: Service for checking revocation

        Returns:
            AuthenticatedUser with user context

        Raises:
            AuthenticationError: If validation fails
        """
        issuer = self._get_issuer(token)

        if issuer == settings.APP_JWT_ISSUER:
            return await self._app_validator.validate(token, token_revocation_service)
        elif issuer == settings.OAUTH_ISSUER_URL:
            return await self._keycloak_validator.validate(token, token_revocation_service)
        else:
            logger.warning(
                "Unknown token issuer",
                extra={
                    "issuer": issuer,
                    "expected_app": settings.APP_JWT_ISSUER,
                    "expected_oauth": settings.OAUTH_ISSUER_URL,
                },
            )
            raise AuthenticationError(
                error="invalid_token",
                error_description="Unknown token issuer",
            )

    def _get_issuer(self, token: str) -> str | None:
        """Extract issuer claim from token without verification."""
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
            return unverified.get("iss")
        except Exception:
            return None


def create_token_validator_router(jwks_client: JWKSClient) -> TokenValidatorRouter:
    """Factory function to create a TokenValidatorRouter with all validators.

    Args:
        jwks_client: JWKS client for Keycloak token validation

    Returns:
        Configured TokenValidatorRouter
    """
    return TokenValidatorRouter(
        app_token_validator=AppTokenValidator(),
        keycloak_token_validator=KeycloakTokenValidator(jwks_client),
    )
