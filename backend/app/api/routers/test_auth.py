"""
Test authentication endpoints for manual rate limiting and RBAC validation.

These endpoints are used for testing rate limiting, authentication flow,
and role-based access control. They should be removed or disabled in production.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies.auth import CurrentUser
from app.schemas.auth import AuthenticatedUser

router = APIRouter(tags=["test"], prefix="/test")


class TestAuthResponse(BaseModel):
    """Test authentication response model."""

    message: str
    user_id: str
    tenant_id: str
    email: str | None = None


class TestUserInfo(BaseModel):
    """User information returned in test responses for RBAC testing."""

    username: str
    roles: list[str]
    tenant_id: str


class TestAdminResponse(BaseModel):
    """Response model for admin test endpoint."""

    message: str
    user: TestUserInfo


def require_admin(user: CurrentUser) -> AuthenticatedUser:
    """
    Dependency that requires the user to have the 'admin' role/scope.

    Raises 403 Forbidden if the user lacks the admin role.

    The admin role can be represented as either:
    - A scope named 'admin' in the token's scope claim
    - A role named 'admin' (mapped to scope during token processing)

    Args:
        user: The authenticated user from the CurrentUser dependency

    Returns:
        AuthenticatedUser: The validated user if they have admin role

    Raises:
        HTTPException: 403 Forbidden if user lacks admin role
    """
    if "admin" not in user.scopes:
        raise HTTPException(
            status_code=403,
            detail="Role 'admin' required. User roles: " + ", ".join(user.scopes),
        )
    return user


@router.get(
    "/protected",
    response_model=TestAuthResponse,
    summary="Protected test endpoint",
    description="Test endpoint that requires authentication. Used for testing rate limiting.",
)
async def protected_endpoint(user: CurrentUser) -> TestAuthResponse:
    """
    Protected endpoint requiring OAuth authentication.

    This endpoint is used to test:
    - Rate limiting on authentication
    - Failed auth rate limiting
    - Token validation

    Args:
        user: Authenticated user from OAuth token

    Returns:
        TestAuthResponse: User information from token
    """
    return TestAuthResponse(
        message="Authentication successful",
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        email=user.email,
    )


@router.get(
    "/admin",
    response_model=TestAdminResponse,
    summary="Admin-only test endpoint",
    description="Requires 'admin' role. Used for testing role-based access control.",
)
async def admin_endpoint(
    user: AuthenticatedUser = Depends(require_admin),
) -> TestAdminResponse:
    """
    Admin-only endpoint for testing RBAC.

    Returns 403 Forbidden if the authenticated user does not have the 'admin' role.

    This endpoint is used to test:
    - Role-based access control (RBAC)
    - Admin privilege verification
    - Proper 403 responses for unauthorized users

    Args:
        user: Authenticated user with admin role verification

    Returns:
        TestAdminResponse: Admin-specific response with user info
    """
    # Use email or name as username fallback, or user_id if neither available
    username = user.name or user.email or user.user_id

    return TestAdminResponse(
        message="This is an admin route",
        user=TestUserInfo(
            username=username,
            roles=user.scopes,  # Scopes serve as roles in this system
            tenant_id=user.tenant_id,
        ),
    )
