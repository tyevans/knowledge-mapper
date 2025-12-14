"""OAuth 2.0 client schemas for Authorization Code flow and OAuth router."""
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field, HttpUrl


class TokenResponse(BaseModel):
    """
    OAuth 2.0 token response.

    Returned by the token endpoint after successful authorization code
    exchange or token refresh. Contains access token, refresh token,
    and token metadata.
    """

    access_token: str = Field(..., description="OAuth access token (JWT)")
    token_type: str = Field(default="Bearer", description="Token type (always 'Bearer')")
    expires_in: int = Field(..., description="Token lifetime in seconds")
    refresh_token: Optional[str] = Field(None, description="Refresh token for obtaining new access tokens")
    scope: Optional[str] = Field(None, description="Granted scopes (space-separated)")
    id_token: Optional[str] = Field(None, description="OpenID Connect ID token (JWT)")


class OIDCDiscovery(BaseModel):
    """
    OpenID Connect Discovery document.

    Retrieved from .well-known/openid-configuration endpoint.
    Contains OAuth provider metadata and endpoint URLs.
    """

    issuer: str = Field(..., description="OAuth issuer URL")
    authorization_endpoint: str = Field(..., description="Authorization endpoint URL")
    token_endpoint: str = Field(..., description="Token endpoint URL")
    jwks_uri: str = Field(..., description="JWKS endpoint URL")
    userinfo_endpoint: Optional[str] = Field(None, description="UserInfo endpoint URL")
    end_session_endpoint: Optional[str] = Field(None, description="Logout endpoint URL")
    revocation_endpoint: Optional[str] = Field(None, description="Token revocation endpoint URL")
    introspection_endpoint: Optional[str] = Field(None, description="Token introspection endpoint URL")
    scopes_supported: Optional[List[str]] = Field(None, description="Supported OAuth scopes")
    response_types_supported: Optional[List[str]] = Field(None, description="Supported response types")
    grant_types_supported: Optional[List[str]] = Field(None, description="Supported grant types")
    code_challenge_methods_supported: Optional[List[str]] = Field(None, description="Supported PKCE challenge methods")


class UserInfo(BaseModel):
    """
    OAuth UserInfo response.

    Retrieved from the userinfo endpoint after successful authentication.
    Contains user profile information from the OAuth provider.
    """

    sub: str = Field(..., description="Subject (user ID)")
    email: Optional[str] = Field(None, description="User email address")
    email_verified: Optional[bool] = Field(None, description="Email verification status")
    name: Optional[str] = Field(None, description="User full name")
    given_name: Optional[str] = Field(None, description="User first name")
    family_name: Optional[str] = Field(None, description="User last name")
    preferred_username: Optional[str] = Field(None, description="Preferred username")
    picture: Optional[str] = Field(None, description="Profile picture URL")
    tenant_id: Optional[str] = Field(None, description="Tenant ID (custom claim)")


class AuthorizationRequest(BaseModel):
    """
    OAuth authorization request parameters.

    Parameters used to generate the authorization URL that the user
    is redirected to for authentication.
    """

    response_type: str = Field(default="code", description="OAuth response type")
    client_id: str = Field(..., description="OAuth client ID")
    redirect_uri: str = Field(..., description="Callback URL after authentication")
    scope: str = Field(..., description="Requested OAuth scopes (space-separated)")
    state: str = Field(..., description="CSRF protection state parameter")
    code_challenge: Optional[str] = Field(None, description="PKCE code challenge")
    code_challenge_method: Optional[str] = Field(None, description="PKCE challenge method (S256)")


class TokenExchangeRequest(BaseModel):
    """
    OAuth token exchange request.

    Parameters sent to the token endpoint to exchange an authorization
    code for access and refresh tokens.
    """

    grant_type: str = Field(default="authorization_code", description="OAuth grant type")
    code: str = Field(..., description="Authorization code from callback")
    redirect_uri: str = Field(..., description="Redirect URI (must match authorization request)")
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str = Field(..., description="OAuth client secret")
    code_verifier: Optional[str] = Field(None, description="PKCE code verifier")


class TokenRefreshRequest(BaseModel):
    """
    OAuth token refresh request.

    Parameters sent to the token endpoint to refresh an expired
    access token using a refresh token.
    """

    grant_type: str = Field(default="refresh_token", description="OAuth grant type")
    refresh_token: str = Field(..., description="Refresh token from previous token response")
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str = Field(..., description="OAuth client secret")
    scope: Optional[str] = Field(None, description="Requested scopes (optional)")


class PKCEChallenge(BaseModel):
    """
    PKCE code challenge and verifier.

    Used in Authorization Code flow with PKCE for enhanced security.
    The code_verifier is stored in the session and sent during token
    exchange. The code_challenge is sent during authorization.
    """

    code_verifier: str = Field(..., description="PKCE code verifier (43 chars, base64url)")
    code_challenge: str = Field(..., description="PKCE code challenge (SHA256 of verifier)")
    code_challenge_method: str = Field(default="S256", description="PKCE challenge method")


# OAuth Router Response Schemas (TASK-012)

class LoginResponse(BaseModel):
    """Response from /oauth/login endpoint."""

    authorization_url: HttpUrl = Field(
        ...,
        description="URL to redirect user to for OAuth authentication",
    )
    state: str = Field(
        ...,
        description="State parameter for CSRF protection (also stored in cookie)",
    )


class CallbackResponse(BaseModel):
    """Response model for OAuth callback (not directly returned, used for typing)."""

    access_token: str = Field(..., description="OAuth access token")
    refresh_token: Optional[str] = Field(None, description="OAuth refresh token")
    expires_in: int = Field(..., description="Token expiry in seconds")


class TokenRefreshResponse(BaseModel):
    """Response from /oauth/token/refresh endpoint."""

    access_token: str = Field(..., description="OAuth access token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiry in seconds")
    refresh_token: Optional[str] = Field(None, description="New refresh token if issued")


class ErrorResponse(BaseModel):
    """OAuth error response."""

    error: str = Field(..., description="OAuth error code")
    error_description: Optional[str] = Field(None, description="Human-readable error description")
