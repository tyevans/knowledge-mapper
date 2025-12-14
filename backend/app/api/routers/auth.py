"""
Authentication endpoints for OAuth token management.

This module provides endpoints for token management operations:
- Token revocation (logout)
- Tenant membership listing (multi-tenant support)
- Token exchange for tenant selection (multi-tenant support)
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies.auth import CurrentUser
from app.api.dependencies.database import get_db
from app.core.config import settings
from app.models import User, Tenant, UserTenantMembership, MembershipRole
from app.schemas.auth import (
    TenantMembershipResponse,
    UserTenantsResponse,
    TokenExchangeRequest,
    TokenExchangeResponse,
)
from app.services.app_token_service import get_app_token_service
from app.services.token_revocation import (
    get_token_revocation_service,
    TokenRevocationService,
)

router = APIRouter(tags=["auth"], prefix="/auth")


class RevokeTokenRequest(BaseModel):
    """Request model for token revocation (optional, for future extensions)."""

    # Future: Allow revoking specific tokens by jti
    # For now, we revoke the current token from the Authorization header
    pass


class RevokeTokenResponse(BaseModel):
    """Response model for successful token revocation."""

    message: str = Field(..., description="Success message")
    jti: str = Field(..., description="JWT ID of the revoked token")


@router.post(
    "/revoke",
    response_model=RevokeTokenResponse,
    summary="Revoke current access token",
    description="Revoke the current access token to implement secure logout. "
    "The token will be added to a blacklist and rejected for all future requests. "
    "This is useful for logout flows, compromised token invalidation, and forced logout.",
    responses={
        200: {
            "description": "Token revoked successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Token revoked successfully",
                        "jti": "cca5f515-b48f-4307-8152-ad3a031d832d",
                    }
                }
            },
        },
        401: {
            "description": "Unauthorized - Invalid or missing token",
            "content": {
                "application/json": {
                    "example": {
                        "error": "invalid_token",
                        "error_description": "Authorization header with Bearer token is required",
                    }
                }
            },
        },
        503: {
            "description": "Service Unavailable - Token revocation service unavailable",
            "content": {
                "application/json": {
                    "example": {
                        "error": "service_unavailable",
                        "error_description": "Unable to revoke token at this time",
                    }
                }
            },
        },
    },
)
async def revoke_token(
    user: CurrentUser,
    token_revocation_service: Annotated[
        TokenRevocationService, Depends(get_token_revocation_service)
    ],
) -> RevokeTokenResponse:
    """
    Revoke the current access token (logout).

    This endpoint adds the current access token to a blacklist, preventing it from
    being used for authentication in future requests. This is the primary mechanism
    for implementing secure logout.

    The token is identified by its jti (JWT ID) claim, which is extracted from the
    authenticated user context. The token is added to Redis with a TTL matching the
    token's expiration time, ensuring automatic cleanup of expired tokens.

    Use Cases:
    - User logout: User explicitly logs out from the application
    - Security incident: Admin force-logs out a compromised account
    - Token rotation: Old token is revoked when new token is issued

    Security Notes:
    - The token must be valid and not already revoked to call this endpoint
    - After revocation, the token cannot be used again (401 Unauthorized)
    - Revocation is immediate and distributed across all backend instances
    - If Redis is unavailable, returns 503 Service Unavailable

    Args:
        user: Authenticated user context (from get_current_user dependency)
        token_revocation_service: Token revocation service for blacklist management

    Returns:
        RevokeTokenResponse: Success message with revoked token jti

    Raises:
        HTTPException: 401 Unauthorized if token is invalid
        HTTPException: 503 Service Unavailable if revocation service unavailable

    Example:
        >>> # curl -X POST http://localhost:8000/api/v1/auth/revoke \
        >>> #   -H "Authorization: Bearer <access_token>"
        >>> {
        ...   "message": "Token revoked successfully",
        ...   "jti": "cca5f515-b48f-4307-8152-ad3a031d832d"
        ... }
    """
    # Extract jti and exp from authenticated user context
    jti = user.jti
    exp = user.exp

    try:
        # Add token to revocation blacklist
        await token_revocation_service.revoke_token(jti=jti, exp=exp)

        return RevokeTokenResponse(
            message="Token revoked successfully",
            jti=jti,
        )

    except Exception as e:
        # If Redis is unavailable or revocation fails, return 503
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "service_unavailable",
                "error_description": "Unable to revoke token at this time",
            },
        )


# =============================================================================
# Multi-Tenant User Support Endpoints
# =============================================================================


def _get_scopes_for_role(role: MembershipRole) -> list[str]:
    """
    Get default scopes based on membership role.

    Args:
        role: Membership role (owner, admin, member)

    Returns:
        List of scope strings
    """
    base_scopes = ["statements/read", "statements/write", "state/read", "state/write"]

    if role == MembershipRole.OWNER:
        return base_scopes + ["tenant/admin", "admin"]
    elif role == MembershipRole.ADMIN:
        return base_scopes + ["tenant/admin"]
    else:
        return base_scopes


@router.get(
    "/tenants",
    response_model=UserTenantsResponse,
    summary="List user's tenant memberships",
    description="""
    Returns all tenants the authenticated user belongs to.

    This endpoint is called after Keycloak authentication to determine which
    tenants the user has access to. If the user has multiple tenants, the
    frontend should display a tenant selector.

    Note: This endpoint works with both Keycloak tokens (before tenant selection)
    and app tokens (after tenant selection).
    """,
    responses={
        200: {
            "description": "List of user's tenant memberships",
            "content": {
                "application/json": {
                    "example": {
                        "user_id": "google|12345",
                        "email": "user@example.com",
                        "tenants": [
                            {
                                "tenant_id": "11111111-1111-1111-1111-111111111111",
                                "tenant_slug": "acme-corp",
                                "tenant_name": "Acme Corporation",
                                "role": "member",
                                "is_default": True,
                            },
                            {
                                "tenant_id": "22222222-2222-2222-2222-222222222222",
                                "tenant_slug": "demo-org",
                                "tenant_name": "Demo Organization",
                                "role": "admin",
                                "is_default": False,
                            },
                        ],
                    }
                }
            },
        },
        401: {"description": "Unauthorized - Invalid or missing token"},
    },
)
async def list_user_tenants(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserTenantsResponse:
    """
    List all tenants the current user has access to.

    This endpoint queries the user_tenant_memberships table to find all
    tenants where the user has an active membership. The user is identified
    by their OAuth subject claim (user_id from the token).

    Args:
        user: Authenticated user context
        db: Database session

    Returns:
        UserTenantsResponse: User info with list of tenant memberships
    """
    # Query memberships for this user by oauth_subject
    # We need to find the User record first, then get memberships
    user_query = (
        select(User)
        .where(User.oauth_subject == user.user_id)
        .where(User.is_active == True)
        .options(
            selectinload(User.memberships).selectinload(UserTenantMembership.tenant)
        )
    )

    result = await db.execute(user_query)
    db_user = result.scalar_one_or_none()

    memberships = []

    if db_user:
        # Get memberships from the user's memberships relationship
        for membership in db_user.memberships:
            if membership.is_active and membership.tenant.is_active:
                memberships.append(
                    TenantMembershipResponse(
                        tenant_id=str(membership.tenant_id),
                        tenant_slug=membership.tenant.slug,
                        tenant_name=membership.tenant.name,
                        role=membership.role.value,
                        is_default=membership.is_default,
                    )
                )
    else:
        # User doesn't exist in our database yet
        # This could happen if they're a new user from Keycloak
        # In this case, we return empty memberships
        pass

    return UserTenantsResponse(
        user_id=user.user_id,
        email=user.email,
        tenants=memberships,
    )


@router.post(
    "/select-tenant/{tenant_id}",
    response_model=TokenExchangeResponse,
    summary="Exchange token for tenant-scoped app token",
    description="""
    Select a tenant and receive an app-issued JWT with tenant context.

    After authenticating via Keycloak and listing available tenants, the user
    selects a tenant. This endpoint verifies the user has access to the
    requested tenant and issues a new JWT token with:
    - tenant_id claim set to the selected tenant
    - scopes based on the user's role in that tenant
    - signed by the backend's RSA key (not Keycloak)

    The returned app token should be used for all subsequent API calls.
    """,
    responses={
        200: {
            "description": "App token issued successfully",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                        "scope": "statements/read statements/write",
                        "tenant_id": "11111111-1111-1111-1111-111111111111",
                        "tenant_slug": "acme-corp",
                    }
                }
            },
        },
        401: {"description": "Unauthorized - Invalid or missing token"},
        403: {"description": "Forbidden - User does not have access to this tenant"},
        404: {"description": "Not Found - Tenant does not exist"},
    },
)
async def select_tenant(
    tenant_id: UUID,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: TokenExchangeRequest | None = None,
) -> TokenExchangeResponse:
    """
    Exchange Keycloak token for tenant-scoped app token.

    Args:
        tenant_id: UUID of the tenant to select
        user: Authenticated user context (from Keycloak or existing app token)
        db: Database session
        request: Optional request body to specify scopes

    Returns:
        TokenExchangeResponse: App token with tenant context

    Raises:
        HTTPException: 403 if user doesn't have access to tenant
        HTTPException: 404 if tenant doesn't exist
    """
    # Find the user in our database
    user_query = (
        select(User)
        .where(User.oauth_subject == user.user_id)
        .where(User.is_active == True)
    )
    result = await db.execute(user_query)
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found in system",
        )

    # Check membership in requested tenant
    membership_query = (
        select(UserTenantMembership)
        .where(UserTenantMembership.user_id == db_user.id)
        .where(UserTenantMembership.tenant_id == tenant_id)
        .where(UserTenantMembership.is_active == True)
        .options(selectinload(UserTenantMembership.tenant))
    )
    result = await db.execute(membership_query)
    membership = result.scalar_one_or_none()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this tenant",
        )

    if not membership.tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found or inactive",
        )

    # Determine scopes based on role
    available_scopes = _get_scopes_for_role(membership.role)

    # Filter to requested scopes if specified
    if request and request.requested_scopes:
        granted_scopes = [s for s in request.requested_scopes if s in available_scopes]
    else:
        granted_scopes = available_scopes

    # Create app token
    app_token_service = get_app_token_service()
    access_token = app_token_service.create_access_token(
        user_id=user.user_id,
        tenant_id=str(tenant_id),
        scopes=granted_scopes,
        email=user.email,
        name=user.name,
        oauth_subject=user.user_id,
    )

    return TokenExchangeResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=settings.APP_JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        scope=" ".join(granted_scopes),
        tenant_id=str(tenant_id),
        tenant_slug=membership.tenant.slug,
    )
