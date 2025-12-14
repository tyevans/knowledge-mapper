"""
OAuth 2.0 endpoints for user authentication.

Handles Authorization Code flow with PKCE for interactive user login.
This router provides web-facing API endpoints for:
- Login initiation (redirect to OAuth provider)
- OAuth callback handling (token exchange)
- Token refresh
- Logout (session cleanup)

Security features:
- PKCE (Proof Key for Code Exchange) for authorization code protection
- State parameter for CSRF protection
- HTTP-only cookies for token storage (XSS protection)
- Secure flag for HTTPS-only cookies (production)
- SameSite=lax for CSRF protection
"""

import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.services.oauth_client import OAuthClient, get_oauth_client
from app.schemas.oauth import (
    LoginResponse,
    TokenRefreshResponse,
    ErrorResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])


@router.get(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate OAuth login",
    description="Redirects user to OAuth provider for authentication. Returns authorization URL.",
    responses={
        200: {"description": "Authorization URL generated successfully"},
        503: {"description": "OAuth provider unavailable", "model": ErrorResponse},
    },
)
async def login(
    request: Request,
    response: Response,
    redirect_uri: Optional[str] = None,
    oauth_client: OAuthClient = Depends(get_oauth_client),
) -> LoginResponse:
    """
    Initiate OAuth Authorization Code flow with PKCE.

    Generates authorization URL with state parameter for CSRF protection and
    PKCE challenge for authorization code protection. State and code verifier
    are stored in HTTP-only session cookies.

    Args:
        request: FastAPI request object
        response: FastAPI response object for setting cookies
        redirect_uri: Optional redirect URI after successful auth (defaults to FRONTEND_URL)
        oauth_client: OAuth client dependency

    Returns:
        LoginResponse: Authorization URL and state parameter

    Raises:
        HTTPException 503: If OAuth provider is unavailable
    """
    try:
        # Generate authorization URL with state and PKCE
        authorization_url, state, pkce_challenge = await oauth_client.get_authorization_url()

        # Store state and code_verifier in HTTP-only cookies for callback validation
        response.set_cookie(
            key="oauth_state",
            value=state,
            httponly=True,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite="lax",
            max_age=600,  # 10 minutes (short-lived for security)
        )

        if pkce_challenge:
            response.set_cookie(
                key="code_verifier",
                value=pkce_challenge.code_verifier,
                httponly=True,
                secure=settings.SESSION_COOKIE_SECURE,
                samesite="lax",
                max_age=600,  # 10 minutes
            )

        # Optionally store post-auth redirect URI
        if redirect_uri:
            response.set_cookie(
                key="post_auth_redirect",
                value=redirect_uri,
                httponly=True,
                secure=settings.SESSION_COOKIE_SECURE,
                samesite="lax",
                max_age=600,
            )

        logger.info(
            "OAuth login initiated",
            extra={
                "state": state,
                "redirect_uri": redirect_uri,
                "pkce_enabled": pkce_challenge is not None,
            },
        )

        return LoginResponse(
            authorization_url=authorization_url,
            state=state,
        )

    except Exception as e:
        logger.error(
            "OAuth login failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth provider unavailable",
        )


@router.get(
    "/callback",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    summary="OAuth callback endpoint",
    description="Handles redirect from OAuth provider after user authentication.",
    responses={
        302: {"description": "Redirect to frontend after successful authentication"},
        400: {"description": "Invalid state or missing code verifier", "model": ErrorResponse},
        500: {"description": "Token exchange failed", "model": ErrorResponse},
    },
)
async def callback(
    request: Request,
    code: str,
    state: str,
    oauth_client: OAuthClient = Depends(get_oauth_client),
) -> RedirectResponse:
    """
    Handle OAuth provider callback after user authentication.

    Validates state parameter (CSRF protection), exchanges authorization code
    for tokens using PKCE verifier, stores tokens in HTTP-only cookies, and
    redirects user to application.

    Args:
        request: FastAPI request object
        code: Authorization code from provider
        state: State parameter from provider (for CSRF validation)
        oauth_client: OAuth client dependency

    Returns:
        RedirectResponse: Redirect to frontend or specified redirect_uri

    Raises:
        HTTPException 400: If state validation fails or code verifier missing
        HTTPException 500: If token exchange fails
    """
    try:
        # Validate state parameter (CSRF protection)
        stored_state = request.cookies.get("oauth_state")
        if not stored_state or stored_state != state:
            logger.warning(
                "OAuth state mismatch",
                extra={
                    "stored_state": stored_state,
                    "received_state": state,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid state parameter",
            )

        # Get code_verifier from cookie (for PKCE)
        code_verifier = request.cookies.get("code_verifier")
        if not code_verifier:
            logger.warning("OAuth code verifier missing")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing code verifier",
            )

        # Exchange authorization code for tokens
        token_response = await oauth_client.exchange_code_for_token(
            code=code,
            code_verifier=code_verifier,
        )

        # Create redirect response
        redirect_uri = request.cookies.get("post_auth_redirect", settings.FRONTEND_URL)
        response = RedirectResponse(url=redirect_uri, status_code=status.HTTP_302_FOUND)

        # Store tokens in HTTP-only session cookies
        # Access token: short-lived (from token response)
        response.set_cookie(
            key="access_token",
            value=token_response.access_token,
            httponly=True,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite="lax",
            max_age=token_response.expires_in,
        )

        # Refresh token: long-lived (7 days)
        if token_response.refresh_token:
            response.set_cookie(
                key="refresh_token",
                value=token_response.refresh_token,
                httponly=True,
                secure=settings.SESSION_COOKIE_SECURE,
                samesite="lax",
                max_age=settings.SESSION_COOKIE_MAX_AGE,
            )

        # Clear temporary cookies
        response.delete_cookie("oauth_state")
        response.delete_cookie("code_verifier")
        response.delete_cookie("post_auth_redirect")

        logger.info(
            "OAuth callback success",
            extra={
                "redirect_uri": redirect_uri,
                "has_refresh_token": token_response.refresh_token is not None,
                "expires_in": token_response.expires_in,
            },
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "OAuth callback failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token exchange failed",
        )


@router.post(
    "/token/refresh",
    response_model=TokenRefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Exchanges refresh token for a new access token.",
    responses={
        200: {"description": "Token refreshed successfully"},
        401: {"description": "Refresh token missing or invalid", "model": ErrorResponse},
    },
)
async def refresh_token(
    request: Request,
    response: Response,
    oauth_client: OAuthClient = Depends(get_oauth_client),
) -> TokenRefreshResponse:
    """
    Refresh access token using refresh token.

    Reads refresh token from cookie, exchanges it for new access token,
    updates cookies with new tokens.

    Args:
        request: FastAPI request object
        response: FastAPI response object
        oauth_client: OAuth client dependency

    Returns:
        TokenRefreshResponse: New access token and optional new refresh token

    Raises:
        HTTPException 401: If refresh token is missing or refresh fails
    """
    try:
        # Get refresh token from cookie
        refresh_token_value = request.cookies.get("refresh_token")
        if not refresh_token_value:
            logger.warning("Refresh token missing")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No refresh token available",
            )

        # Exchange refresh token for new access token
        token_response = await oauth_client.refresh_token(
            refresh_token=refresh_token_value
        )

        # Update access token cookie
        response.set_cookie(
            key="access_token",
            value=token_response.access_token,
            httponly=True,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite="lax",
            max_age=token_response.expires_in,
        )

        # Update refresh token if a new one was issued
        if token_response.refresh_token:
            response.set_cookie(
                key="refresh_token",
                value=token_response.refresh_token,
                httponly=True,
                secure=settings.SESSION_COOKIE_SECURE,
                samesite="lax",
                max_age=settings.SESSION_COOKIE_MAX_AGE,
            )

        logger.info(
            "Token refresh success",
            extra={
                "expires_in": token_response.expires_in,
                "new_refresh_token": token_response.refresh_token is not None,
            },
        )

        return TokenRefreshResponse(
            access_token=token_response.access_token,
            token_type=token_response.token_type,
            expires_in=token_response.expires_in,
            refresh_token=token_response.refresh_token,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Token refresh failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token refresh failed",
        )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout user",
    description="Clears user session and tokens.",
    responses={
        204: {"description": "Logout successful, session cleared"},
    },
)
async def logout(response: Response) -> None:
    """
    Logout user by clearing session cookies.

    Clears all OAuth-related cookies including access token, refresh token,
    and any temporary authentication state cookies.

    Note: This only clears local session. For complete logout, clients should
    also call the provider's end_session_endpoint to revoke tokens at the OAuth
    provider (future enhancement).

    Args:
        response: FastAPI response object
    """
    # Clear all OAuth-related cookies
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    response.delete_cookie("oauth_state")
    response.delete_cookie("code_verifier")
    response.delete_cookie("post_auth_redirect")

    logger.info("User logged out")
