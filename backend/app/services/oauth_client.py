"""
OAuth 2.0 client for Authorization Code flow with PKCE.

This module provides an async OAuth client that implements the Authorization
Code flow with PKCE (Proof Key for Code Exchange) for enhanced security. It
supports OIDC discovery for dynamic endpoint configuration and handles token
exchange, refresh, and user info fetching.
"""

import logging
import secrets
import hashlib
import base64
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.schemas.oauth import OIDCDiscovery, TokenResponse, UserInfo, PKCEChallenge

logger = logging.getLogger(__name__)


class OAuthClient:
    """
    OAuth 2.0 client for Authorization Code flow with PKCE.

    Implements:
    - Authorization URL generation with PKCE (Proof Key for Code Exchange)
    - Authorization code exchange for tokens
    - Token refresh
    - OIDC discovery for dynamic endpoint configuration
    - State parameter generation for CSRF protection
    - Structured logging for all operations

    PKCE enhances OAuth security by:
    - Protecting against authorization code interception attacks
    - Enabling secure OAuth for public clients (SPAs, mobile apps)
    - Preventing CSRF attacks via state parameter

    Example:
        >>> client = OAuthClient(
        ...     client_id="knowledge-mapper-backend",
        ...     client_secret="secret",
        ...     redirect_uri="http://localhost:8000/callback",
        ...     issuer_url="http://keycloak:8080/realms/knowledge-mapper-dev"
        ... )
        >>> # Generate authorization URL
        >>> url, state, verifier = await client.get_authorization_url()
        >>> # Exchange code for tokens
        >>> token = await client.exchange_code_for_token(code, verifier)
        >>> # Refresh token
        >>> new_token = await client.refresh_token(token.refresh_token)
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        issuer_url: str,
        scopes: Optional[List[str]] = None,
        use_pkce: bool = True,
        http_timeout: int = 10,
    ):
        """
        Initialize OAuth client.

        Args:
            client_id: OAuth client ID (from Keycloak)
            client_secret: OAuth client secret (from Keycloak)
            redirect_uri: OAuth redirect URI (callback URL)
            issuer_url: OAuth issuer URL (e.g., http://keycloak:8080/realms/knowledge-mapper-dev)
            scopes: OAuth scopes to request (default: ["openid", "profile", "email"])
            use_pkce: Enable PKCE for enhanced security (default: True)
            http_timeout: HTTP request timeout in seconds (default: 10)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.issuer_url = issuer_url
        self.scopes = scopes or ["openid", "profile", "email"]
        self.use_pkce = use_pkce
        self.http_timeout = http_timeout

        self._http_client = httpx.AsyncClient(timeout=http_timeout)
        self._oidc_config: Optional[OIDCDiscovery] = None

    async def discover_endpoints(self) -> OIDCDiscovery:
        """
        Discover OAuth endpoints via OIDC discovery.

        Fetches the OpenID Connect discovery document from the provider's
        .well-known/openid-configuration endpoint. The discovery document
        contains all OAuth endpoint URLs (authorization, token, jwks, etc.).

        The discovery result is cached after the first successful fetch to
        avoid repeated network requests.

        Returns:
            OIDCDiscovery: OIDC configuration with endpoint URLs

        Raises:
            httpx.HTTPError: If discovery fails (network error, 4xx/5xx response)
            ValueError: If discovery document is missing required fields

        Example:
            >>> config = await client.discover_endpoints()
            >>> print(f"Token endpoint: {config.token_endpoint}")
        """
        if self._oidc_config is not None:
            return self._oidc_config

        discovery_url = f"{self.issuer_url}/.well-known/openid-configuration"

        try:
            logger.debug(
                "Fetching OIDC discovery document",
                extra={"discovery_url": discovery_url},
            )
            response = await self._http_client.get(discovery_url)
            response.raise_for_status()
            discovery_data = response.json()

            # Validate and parse discovery document
            self._oidc_config = OIDCDiscovery(**discovery_data)

            logger.info(
                "OIDC discovery successful",
                extra={
                    "issuer": self.issuer_url,
                    "authorization_endpoint": self._oidc_config.authorization_endpoint,
                    "token_endpoint": self._oidc_config.token_endpoint,
                },
            )

            return self._oidc_config

        except httpx.HTTPError as e:
            logger.error(
                "OIDC discovery failed",
                extra={"issuer": self.issuer_url, "error": str(e)},
            )
            raise
        except Exception as e:
            logger.error(
                "OIDC discovery parsing failed",
                extra={"issuer": self.issuer_url, "error": str(e)},
            )
            raise ValueError(f"Invalid OIDC discovery document: {e}")

    def generate_pkce_challenge(self) -> PKCEChallenge:
        """
        Generate PKCE code verifier and challenge.

        PKCE (Proof Key for Code Exchange) enhances OAuth security by:
        - Protecting against authorization code interception
        - Enabling secure OAuth for public clients (SPAs, mobile apps)

        The code_verifier is a random 43-character string (base64url of 32 bytes).
        The code_challenge is the SHA256 hash of the verifier (base64url encoded).

        The verifier is stored in the session and sent during token exchange.
        The challenge is sent during authorization.

        Returns:
            PKCEChallenge: Code verifier, challenge, and challenge method

        Example:
            >>> challenge = client.generate_pkce_challenge()
            >>> print(f"Verifier: {challenge.code_verifier}")
            >>> print(f"Challenge: {challenge.code_challenge}")
        """
        # Generate random code verifier (43-128 characters, base64url)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")

        # Generate code challenge (SHA256 hash of verifier, base64url)
        challenge_bytes = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")

        logger.debug(
            "PKCE challenge generated",
            extra={"code_challenge": code_challenge, "verifier_length": len(code_verifier)},
        )

        return PKCEChallenge(
            code_verifier=code_verifier,
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )

    def generate_state(self) -> str:
        """
        Generate random state parameter for CSRF protection.

        The state parameter is a random string sent during authorization
        and validated in the callback to prevent CSRF attacks.

        Returns:
            str: Random state string (URL-safe, 32+ characters)

        Example:
            >>> state = client.generate_state()
            >>> # Store state in session
            >>> # Validate state in callback
        """
        return secrets.token_urlsafe(32)

    async def get_authorization_url(
        self, state: Optional[str] = None, pkce_challenge: Optional[PKCEChallenge] = None
    ) -> tuple[str, str, Optional[PKCEChallenge]]:
        """
        Generate OAuth authorization URL.

        Creates the URL that users are redirected to for authentication.
        The URL includes client_id, redirect_uri, scope, state, and PKCE
        challenge (if enabled).

        Args:
            state: CSRF protection state (generated if not provided)
            pkce_challenge: PKCE challenge (generated if not provided and PKCE enabled)

        Returns:
            Tuple of (authorization_url, state, pkce_challenge)
            pkce_challenge is None if PKCE is disabled

        Example:
            >>> url, state, challenge = await client.get_authorization_url()
            >>> # Store state and challenge.code_verifier in session
            >>> # Redirect user to authorization_url
        """
        oidc_config = await self.discover_endpoints()
        authorization_endpoint = oidc_config.authorization_endpoint

        # Generate state for CSRF protection
        if state is None:
            state = self.generate_state()

        # Build authorization parameters
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
        }

        # Add PKCE if enabled
        challenge = None
        if self.use_pkce:
            if pkce_challenge is None:
                pkce_challenge = self.generate_pkce_challenge()
            challenge = pkce_challenge

            params["code_challenge"] = pkce_challenge.code_challenge
            params["code_challenge_method"] = pkce_challenge.code_challenge_method

        authorization_url = f"{authorization_endpoint}?{urlencode(params)}"

        logger.info(
            "Authorization URL generated",
            extra={
                "state": state,
                "pkce_enabled": self.use_pkce,
                "scopes": self.scopes,
            },
        )

        return authorization_url, state, challenge

    async def exchange_code_for_token(
        self, code: str, code_verifier: Optional[str] = None
    ) -> TokenResponse:
        """
        Exchange authorization code for access token.

        Sends a POST request to the token endpoint with the authorization
        code and client credentials. If PKCE is enabled, the code_verifier
        must be provided (it should match the verifier used to generate
        the code_challenge in the authorization request).

        Args:
            code: Authorization code from OAuth callback
            code_verifier: PKCE code verifier (required if PKCE enabled)

        Returns:
            TokenResponse: Access token, refresh token, and metadata

        Raises:
            httpx.HTTPError: If token exchange fails
            ValueError: If PKCE is enabled but code_verifier is missing

        Example:
            >>> token = await client.exchange_code_for_token(code, verifier)
            >>> print(f"Access token: {token.access_token}")
            >>> print(f"Expires in: {token.expires_in} seconds")
        """
        if self.use_pkce and code_verifier is None:
            raise ValueError("PKCE enabled but code_verifier not provided")

        oidc_config = await self.discover_endpoints()
        token_endpoint = oidc_config.token_endpoint

        # Build token request
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        # Add PKCE verifier if enabled
        if self.use_pkce and code_verifier:
            data["code_verifier"] = code_verifier

        try:
            response = await self._http_client.post(
                token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            token_data = response.json()

            # Parse into TokenResponse model
            token_response = TokenResponse(**token_data)

            logger.info(
                "Token exchange successful",
                extra={
                    "expires_in": token_response.expires_in,
                    "token_type": token_response.token_type,
                    "has_refresh_token": token_response.refresh_token is not None,
                },
            )

            return token_response

        except httpx.HTTPStatusError as e:
            # Log OAuth error details if available
            error_data = {}
            try:
                error_data = e.response.json()
            except Exception:
                pass

            logger.error(
                "Token exchange failed",
                extra={
                    "token_endpoint": token_endpoint,
                    "status_code": e.response.status_code,
                    "error": error_data.get("error", str(e)),
                    "error_description": error_data.get("error_description", ""),
                },
            )
            raise

        except httpx.HTTPError as e:
            logger.error(
                "Token exchange failed",
                extra={"token_endpoint": token_endpoint, "error": str(e)},
            )
            raise

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """
        Refresh access token using refresh token.

        Sends a POST request to the token endpoint with the refresh token
        and client credentials. Returns a new access token and optionally
        a new refresh token.

        Args:
            refresh_token: Refresh token from previous token exchange

        Returns:
            TokenResponse: New access token, refresh token, and metadata

        Raises:
            httpx.HTTPError: If token refresh fails

        Example:
            >>> new_token = await client.refresh_token(old_token.refresh_token)
            >>> print(f"New access token: {new_token.access_token}")
        """
        oidc_config = await self.discover_endpoints()
        token_endpoint = oidc_config.token_endpoint

        # Build refresh request
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = await self._http_client.post(
                token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            token_data = response.json()

            # Parse into TokenResponse model
            token_response = TokenResponse(**token_data)

            logger.info(
                "Token refresh successful",
                extra={
                    "expires_in": token_response.expires_in,
                    "has_new_refresh_token": token_response.refresh_token is not None,
                },
            )

            return token_response

        except httpx.HTTPStatusError as e:
            # Log OAuth error details if available
            error_data = {}
            try:
                error_data = e.response.json()
            except Exception:
                pass

            logger.error(
                "Token refresh failed",
                extra={
                    "token_endpoint": token_endpoint,
                    "status_code": e.response.status_code,
                    "error": error_data.get("error", str(e)),
                    "error_description": error_data.get("error_description", ""),
                },
            )
            raise

        except httpx.HTTPError as e:
            logger.error(
                "Token refresh failed",
                extra={"token_endpoint": token_endpoint, "error": str(e)},
            )
            raise

    async def get_user_info(self, access_token: str) -> UserInfo:
        """
        Fetch user info from OAuth provider.

        Sends a GET request to the userinfo endpoint with the access token.
        Returns user profile information including email, name, etc.

        Args:
            access_token: Valid OAuth access token

        Returns:
            UserInfo: User profile information

        Raises:
            httpx.HTTPError: If userinfo fetch fails
            ValueError: If OIDC discovery doesn't include userinfo_endpoint

        Example:
            >>> user_info = await client.get_user_info(token.access_token)
            >>> print(f"User email: {user_info.email}")
        """
        oidc_config = await self.discover_endpoints()

        if not oidc_config.userinfo_endpoint:
            raise ValueError("No userinfo_endpoint in OIDC discovery")

        try:
            response = await self._http_client.get(
                oidc_config.userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            user_data = response.json()

            # Parse into UserInfo model
            user_info = UserInfo(**user_data)

            logger.info(
                "User info fetch successful",
                extra={"user_id": user_info.sub, "has_email": user_info.email is not None},
            )

            return user_info

        except httpx.HTTPError as e:
            logger.error(
                "User info fetch failed",
                extra={"userinfo_endpoint": oidc_config.userinfo_endpoint, "error": str(e)},
            )
            raise

    async def close(self) -> None:
        """
        Close HTTP client and cleanup resources.

        Should be called when the application shuts down to properly close
        the HTTP client connection pool.
        """
        await self._http_client.aclose()
        logger.debug("OAuth client closed")


# Singleton instance factory
_oauth_client: Optional[OAuthClient] = None


async def get_oauth_client() -> OAuthClient:
    """
    Get singleton OAuth client instance.

    Creates a singleton OAuth client on first call and reuses it for subsequent
    calls. This ensures we have a single HTTP client pool across the application.

    Returns:
        Initialized OAuthClient instance

    Example:
        >>> client = await get_oauth_client()
        >>> url, state, challenge = await client.get_authorization_url()
    """
    global _oauth_client

    if _oauth_client is None:
        _oauth_client = OAuthClient(
            client_id=settings.OAUTH_CLIENT_ID,
            client_secret=settings.OAUTH_CLIENT_SECRET,
            redirect_uri=settings.OAUTH_REDIRECT_URI,
            issuer_url=settings.OAUTH_ISSUER_URL,
            scopes=settings.OAUTH_SCOPES,
            use_pkce=settings.OAUTH_USE_PKCE,
            http_timeout=settings.JWKS_HTTP_TIMEOUT,
        )

        logger.info(
            "OAuth client initialized",
            extra={
                "client_id": settings.OAUTH_CLIENT_ID,
                "redirect_uri": settings.OAUTH_REDIRECT_URI,
                "issuer_url": settings.OAUTH_ISSUER_URL,
                "scopes": settings.OAUTH_SCOPES,
                "pkce_enabled": settings.OAUTH_USE_PKCE,
            },
        )

    return _oauth_client
