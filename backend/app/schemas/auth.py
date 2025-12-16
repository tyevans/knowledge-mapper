"""Authentication schemas for OAuth token validation."""
from typing import List, Optional, Union

from pydantic import BaseModel, Field


# OAuth Scope Constants for xAPI Endpoints
# These constants define the available OAuth 2.0 scopes for the API.
# Scopes control fine-grained access to xAPI resources following the principle
# of least privilege. These scope names MUST match the scopes configured in
# Keycloak (TASK-007) for token validation to work correctly.

# xAPI Statement Scopes
SCOPE_STATEMENTS_READ = "statements/read"
"""Read access to all xAPI statements in the tenant."""

SCOPE_STATEMENTS_WRITE = "statements/write"
"""Write access to create/update xAPI statements."""

SCOPE_STATEMENTS_READ_MINE = "statements/read/mine"
"""Read access to only the user's own xAPI statements."""

# xAPI State Scopes
SCOPE_STATE_READ = "state/read"
"""Read access to xAPI state resources."""

SCOPE_STATE_WRITE = "state/write"
"""Write access to xAPI state resources."""

# Admin Scopes
SCOPE_ADMIN = "admin"
"""System-wide administrative access."""

SCOPE_TENANT_ADMIN = "tenant/admin"
"""Tenant-level administrative access (within user's own tenant)."""

# Tenant Management Scopes (cross-tenant access for platform admins)
SCOPE_TENANTS_READ = "tenants/read"
"""Read access to all tenants in the system (platform admin)."""

SCOPE_TENANTS_MANAGE = "tenants/manage"
"""Full tenant management: create, update, delete tenants (platform admin)."""

SCOPE_TENANTS_STORES = "tenants/stores"
"""Manage tenant-to-event-store mappings (platform admin)."""

# Entity Scopes (for knowledge graph entities)
SCOPE_ENTITIES_READ = "entities/read"
"""Read access to entities in the tenant's knowledge graph."""

SCOPE_ENTITIES_WRITE = "entities/write"
"""Write access to create, update, and delete entities."""

# Entity Consolidation Scopes (for merge/deduplication operations)
SCOPE_CONSOLIDATION_READ = "consolidation/read"
"""Read access to consolidation review queue and merge history."""

SCOPE_CONSOLIDATION_WRITE = "consolidation/write"
"""Write access to approve/reject merges and perform manual consolidation."""

SCOPE_CONSOLIDATION_ADMIN = "consolidation/admin"
"""Administrative access for batch consolidation and configuration changes."""

# All defined scopes (for validation and documentation)
ALL_SCOPES = {
    SCOPE_STATEMENTS_READ,
    SCOPE_STATEMENTS_WRITE,
    SCOPE_STATEMENTS_READ_MINE,
    SCOPE_STATE_READ,
    SCOPE_STATE_WRITE,
    SCOPE_ADMIN,
    SCOPE_TENANT_ADMIN,
    SCOPE_TENANTS_READ,
    SCOPE_TENANTS_MANAGE,
    SCOPE_TENANTS_STORES,
    SCOPE_ENTITIES_READ,
    SCOPE_ENTITIES_WRITE,
    SCOPE_CONSOLIDATION_READ,
    SCOPE_CONSOLIDATION_WRITE,
    SCOPE_CONSOLIDATION_ADMIN,
}


class RealmAccess(BaseModel):
    """Keycloak realm_access claim containing user roles."""

    roles: List[str] = Field(default_factory=list, description="User's realm roles")


class TokenPayload(BaseModel):
    """
    JWT token payload with standard and custom claims.

    This model validates the structure of decoded JWT tokens before
    extracting user context. It includes both standard OAuth claims
    (sub, iss, aud, exp, iat, jti) and custom claims (tenant_id).

    The jti (JWT ID) claim is required for token revocation support.
    """

    sub: str = Field(..., description="Subject (user ID from OAuth provider)")
    iss: str = Field(..., description="Issuer (OAuth provider URL)")
    aud: Union[str, List[str]] = Field(
        ..., description="Audience (client ID or API identifier)"
    )
    exp: int = Field(..., description="Expiration time (Unix timestamp)")
    iat: int = Field(..., description="Issued at time (Unix timestamp)")
    jti: str = Field(..., description="JWT ID (unique token identifier for revocation)")
    tenant_id: Optional[str] = Field(None, description="Tenant ID (custom claim)")
    scope: Optional[str] = Field(
        None, description="OAuth scopes (space-separated)"
    )
    custom_scopes: Optional[str] = Field(
        None, description="Custom scopes from Keycloak user attribute (space-separated)"
    )
    realm_access: Optional[RealmAccess] = Field(
        None, description="Keycloak realm access with roles"
    )
    email: Optional[str] = Field(None, description="User email address")
    name: Optional[str] = Field(None, description="User full name")
    preferred_username: Optional[str] = Field(
        None, description="Preferred username"
    )


class AuthenticatedUser(BaseModel):
    """
    Authenticated user context extracted from validated JWT token.

    This model represents the user identity after successful token validation.
    It's injected into route handlers via the get_current_user() dependency.

    Token Types:
    - Keycloak tokens: May not have tenant_id (before tenant selection)
    - App tokens: Always have tenant_id (after tenant selection)

    Most endpoints require tenant_id for multi-tenant isolation, but some
    endpoints (like /auth/tenants) work without tenant context.

    The jti and exp fields are included to support token revocation.
    """

    user_id: str = Field(..., description="User ID (OAuth subject claim)")
    tenant_id: Optional[str] = Field(
        None, description="Tenant ID (required for multi-tenancy, optional for pre-tenant-selection)"
    )
    jti: str = Field(..., description="JWT ID (unique token identifier)")
    exp: int = Field(..., description="Token expiration time (Unix timestamp)")
    email: Optional[str] = Field(None, description="User email address")
    name: Optional[str] = Field(None, description="User display name")
    scopes: List[str] = Field(
        default_factory=list, description="OAuth scopes granted"
    )
    issuer: str = Field(..., description="OAuth issuer URL")

    def has_scope(self, scope: str) -> bool:
        """
        Check if user has a specific scope.

        Args:
            scope: OAuth scope to check (e.g., "statements/write")

        Returns:
            True if user has the scope, False otherwise

        Example:
            >>> user.has_scope("statements/write")
            True
        """
        return scope in self.scopes

    @property
    def has_tenant(self) -> bool:
        """
        Check if user has tenant context.

        Returns:
            True if tenant_id is set, False otherwise

        Example:
            >>> if not user.has_tenant:
            ...     raise HTTPException(403, "Tenant selection required")
        """
        return self.tenant_id is not None


class AuthError(BaseModel):
    """
    Authentication error response following OAuth 2.0 error format.

    Used to return structured error responses for authentication failures.
    Follows RFC 6750 (Bearer Token Usage) error response format.
    """

    error: str = Field(
        ...,
        description="Error type (e.g., 'invalid_token', 'expired_token', 'missing_token')",
    )
    error_description: str = Field(
        ..., description="Human-readable error description"
    )


# =============================================================================
# Tenant Membership Schemas (Multi-Tenant User Support)
# =============================================================================


class TenantMembershipResponse(BaseModel):
    """
    Tenant membership information for the current user.

    Returned when listing user's available tenants for tenant selection.
    """

    tenant_id: str = Field(..., description="Tenant UUID")
    tenant_slug: str = Field(..., description="URL-safe tenant identifier")
    tenant_name: str = Field(..., description="Human-readable tenant name")
    role: str = Field(..., description="User's role in this tenant (owner, admin, member)")
    is_default: bool = Field(..., description="Whether this is the user's default tenant")


class UserTenantsResponse(BaseModel):
    """
    List of tenants the current user belongs to.

    Returned by GET /auth/tenants endpoint after Keycloak authentication.
    Used by frontend to determine if tenant selection is needed.
    """

    user_id: str = Field(..., description="User ID (OAuth subject)")
    email: Optional[str] = Field(None, description="User's email address")
    tenants: List[TenantMembershipResponse] = Field(
        default_factory=list, description="List of tenant memberships"
    )


class TokenExchangeRequest(BaseModel):
    """
    Optional parameters for tenant token exchange.

    Allows requesting a subset of available scopes for the app token.
    """

    requested_scopes: Optional[List[str]] = Field(
        None, description="Request specific scopes (subset of available scopes)"
    )


class TokenExchangeResponse(BaseModel):
    """
    Response containing the app-issued token after tenant selection.

    This token should be used for all subsequent API calls instead of
    the Keycloak token.
    """

    access_token: str = Field(..., description="App-issued JWT token")
    token_type: str = Field(default="Bearer", description="Token type (always Bearer)")
    expires_in: int = Field(..., description="Token lifetime in seconds")
    scope: str = Field(..., description="Granted scopes (space-separated)")
    tenant_id: str = Field(..., description="Selected tenant ID")
    tenant_slug: str = Field(..., description="Selected tenant slug")
