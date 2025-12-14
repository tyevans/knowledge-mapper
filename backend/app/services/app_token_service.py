"""App token service for issuing backend JWTs with tenant context."""

import base64
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import settings

logger = logging.getLogger(__name__)


class AppTokenService:
    """
    Service for issuing and validating backend-signed JWT tokens.

    This service creates JWT tokens after a user has authenticated via Keycloak
    and selected a specific tenant. The app token includes the tenant context
    and is used for all subsequent API calls.

    Key Features:
    - RSA-based JWT signing (RS256)
    - Tenant-scoped access tokens
    - JWKS endpoint support for external validation
    - Key rotation support via key ID (kid)

    Token Flow:
    1. User authenticates via Keycloak (gets Keycloak token)
    2. User calls /auth/tenants to list available tenants
    3. User calls /auth/select-tenant/{tenant_id} to get app token
    4. App token is used for all subsequent API calls

    Usage:
        >>> service = AppTokenService()
        >>> token = service.create_access_token(
        ...     user_id="user-123",
        ...     tenant_id="tenant-456",
        ...     scopes=["statements/read", "statements/write"],
        ...     email="user@example.com"
        ... )
    """

    def __init__(
        self,
        private_key: str | None = None,
        public_key: str | None = None,
        key_id: str | None = None,
    ):
        """
        Initialize the app token service.

        Args:
            private_key: RSA private key in PEM format (uses config if not provided)
            public_key: RSA public key in PEM format (uses config if not provided)
            key_id: Key ID for JWKS rotation support
        """
        self.key_id = key_id or settings.APP_JWT_KEY_ID
        self._private_key_pem = private_key or settings.APP_JWT_PRIVATE_KEY
        self._public_key_pem = public_key or settings.APP_JWT_PUBLIC_KEY

        # Generate keys if not provided (development mode)
        if not self._private_key_pem or not self._public_key_pem:
            logger.warning(
                "No RSA keys configured for app tokens. Generating temporary keys. "
                "Set APP_JWT_PRIVATE_KEY and APP_JWT_PUBLIC_KEY in production."
            )
            self._generate_keys()

        # Load keys
        self._private_key = serialization.load_pem_private_key(
            self._private_key_pem.encode(),
            password=None,
            backend=default_backend(),
        )
        self._public_key = serialization.load_pem_public_key(
            self._public_key_pem.encode(),
            backend=default_backend(),
        )

    def _generate_keys(self) -> None:
        """Generate RSA key pair for development/testing."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )

        self._private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        self._public_key_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    def create_access_token(
        self,
        user_id: str,
        tenant_id: str,
        scopes: list[str],
        email: str | None = None,
        name: str | None = None,
        oauth_subject: str | None = None,
    ) -> str:
        """
        Create a signed JWT access token with tenant context.

        Args:
            user_id: User's internal ID (UUID)
            tenant_id: Selected tenant ID (UUID)
            scopes: List of granted scopes
            email: User's email address (optional)
            name: User's display name (optional)
            oauth_subject: Original OAuth subject claim (optional)

        Returns:
            Signed JWT token string

        Example:
            >>> token = service.create_access_token(
            ...     user_id="123e4567-e89b-12d3-a456-426614174000",
            ...     tenant_id="987fcdeb-51a2-3bc4-d567-890123456789",
            ...     scopes=["statements/read"],
            ...     email="user@example.com"
            ... )
        """
        now = datetime.now(timezone.utc)
        jti = str(uuid.uuid4())
        exp = now + timedelta(minutes=settings.APP_JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

        claims = {
            # Standard JWT claims
            "sub": user_id,
            "iss": settings.APP_JWT_ISSUER,
            "aud": settings.OAUTH_AUDIENCE,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "jti": jti,
            # App-specific claims
            "tenant_id": tenant_id,
            "scopes": scopes,
            "token_type": "access",
        }

        # Add optional claims
        if email:
            claims["email"] = email
        if name:
            claims["name"] = name
        if oauth_subject:
            claims["oauth_subject"] = oauth_subject

        headers = {
            "kid": self.key_id,
            "alg": settings.APP_JWT_ALGORITHM,
        }

        token = jwt.encode(
            payload=claims,
            key=self._private_key_pem,
            algorithm=settings.APP_JWT_ALGORITHM,
            headers=headers,
        )

        logger.info(
            "App token created",
            extra={
                "user_id": user_id,
                "tenant_id": tenant_id,
                "scopes": scopes,
                "jti": jti,
                "exp": int(exp.timestamp()),
            },
        )

        return token

    def validate_token(self, token: str) -> dict[str, Any]:
        """
        Validate and decode an app token.

        Args:
            token: JWT token string

        Returns:
            Decoded token claims

        Raises:
            jwt.ExpiredSignatureError: If token is expired
            jwt.InvalidSignatureError: If signature is invalid
            jwt.InvalidTokenError: For other validation errors
        """
        claims = jwt.decode(
            jwt=token,
            key=self._public_key_pem,
            algorithms=[settings.APP_JWT_ALGORITHM],
            issuer=settings.APP_JWT_ISSUER,
            audience=settings.OAUTH_AUDIENCE,
        )

        return claims

    def get_public_key_pem(self) -> str:
        """Get the public key in PEM format."""
        return self._public_key_pem

    def get_jwks(self) -> dict[str, Any]:
        """
        Get public key in JWKS format for external validation.

        Returns a JSON Web Key Set (JWKS) containing the public key used
        to sign app tokens. This allows external services to validate
        tokens issued by this backend.

        Returns:
            JWKS dictionary with keys array

        Example response:
            {
                "keys": [{
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "app-key-1",
                    "alg": "RS256",
                    "n": "...",
                    "e": "..."
                }]
            }
        """
        # Get public key numbers
        public_numbers = self._public_key.public_numbers()

        # Convert to base64url encoding (no padding)
        def _int_to_base64url(value: int, length: int | None = None) -> str:
            """Convert integer to base64url-encoded string."""
            if length is None:
                # Calculate minimum bytes needed
                length = (value.bit_length() + 7) // 8
            value_bytes = value.to_bytes(length, byteorder="big")
            return base64.urlsafe_b64encode(value_bytes).rstrip(b"=").decode("ascii")

        # RSA modulus and exponent
        n = _int_to_base64url(public_numbers.n, 256)  # 2048 bits = 256 bytes
        e = _int_to_base64url(public_numbers.e)

        jwk = {
            "kty": "RSA",
            "use": "sig",
            "kid": self.key_id,
            "alg": settings.APP_JWT_ALGORITHM,
            "n": n,
            "e": e,
        }

        return {"keys": [jwk]}


# Module-level singleton (lazy initialization)
_app_token_service: AppTokenService | None = None


def get_app_token_service() -> AppTokenService:
    """
    Get the singleton AppTokenService instance.

    This function implements lazy initialization to avoid loading
    keys until the service is actually needed.

    Returns:
        Singleton AppTokenService instance
    """
    global _app_token_service
    if _app_token_service is None:
        _app_token_service = AppTokenService()
    return _app_token_service
