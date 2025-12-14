"""OAuth scope enforcement dependencies."""
import logging
from typing import Callable

from fastapi import HTTPException, status, Depends

from app.api.dependencies.auth import get_current_user
from app.schemas.auth import AuthenticatedUser

logger = logging.getLogger(__name__)


def require_scopes(*required_scopes: str) -> Callable:
    """
    Create a FastAPI dependency that requires ALL specified scopes.

    This implements AND logic: user must have every scope in the list.
    Use this when an operation requires multiple permissions to be present.

    Args:
        *required_scopes: Variable number of scope strings required (all must be present)

    Returns:
        Dependency function that validates scopes

    Raises:
        HTTPException: 403 Forbidden if user lacks any required scope

    Example:
        >>> from app.api.dependencies.scopes import require_scopes
        >>> from app.schemas.auth import SCOPE_STATEMENTS_WRITE
        >>>
        >>> @router.post("/statements")
        >>> async def post_statement(
        ...     statement: dict,
        ...     current_user: CurrentUser,
        ...     _: None = Depends(require_scopes(SCOPE_STATEMENTS_WRITE))
        ... ):
        ...     # User has statements/write scope
        ...     return {"status": "created"}

        Multiple scopes (AND logic):
        >>> @router.delete("/admin/tenants/{tenant_id}")
        >>> async def delete_tenant(
        ...     tenant_id: str,
        ...     _: None = Depends(require_scopes(SCOPE_ADMIN, SCOPE_TENANT_ADMIN))
        ... ):
        ...     # User must have BOTH admin AND tenant/admin scopes
        ...     return {"status": "deleted"}
    """
    async def scope_checker(
        current_user: AuthenticatedUser = Depends(get_current_user)
    ) -> None:
        """
        Check if user has all required scopes.

        Args:
            current_user: Authenticated user from token validation

        Raises:
            HTTPException: 403 Forbidden if user lacks required scopes
        """
        user_scopes = set(current_user.scopes)
        missing_scopes = set(required_scopes) - user_scopes

        if missing_scopes:
            logger.warning(
                "Scope enforcement failed: missing required scopes",
                extra={
                    "user_id": current_user.user_id,
                    "tenant_id": current_user.tenant_id,
                    "required_scopes": list(required_scopes),
                    "user_scopes": list(user_scopes),
                    "missing_scopes": sorted(missing_scopes),
                },
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "insufficient_scope",
                    "error_description": f"Missing required scopes: {', '.join(sorted(missing_scopes))}",
                    "required_scopes": sorted(required_scopes),
                    "missing_scopes": sorted(missing_scopes),
                },
            )

        logger.debug(
            "Scope enforcement passed",
            extra={
                "user_id": current_user.user_id,
                "required_scopes": list(required_scopes),
            },
        )

    return scope_checker


def require_any_scope(*allowed_scopes: str) -> Callable:
    """
    Create a FastAPI dependency that requires ANY of the specified scopes.

    This implements OR logic: user must have at least one scope from the list.
    Use this when an operation can be authorized by multiple different permissions.

    Args:
        *allowed_scopes: Variable number of scope strings (user needs at least one)

    Returns:
        Dependency function that validates scopes

    Raises:
        HTTPException: 403 Forbidden if user has none of the allowed scopes

    Example:
        >>> from app.api.dependencies.scopes import require_any_scope
        >>> from app.schemas.auth import SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_READ_MINE
        >>>
        >>> @router.get("/statements")
        >>> async def get_statements(
        ...     current_user: CurrentUser,
        ...     _: None = Depends(require_any_scope(SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_READ_MINE))
        ... ):
        ...     # User has either statements/read OR statements/read/mine
        ...     # Can use has_scope() to differentiate behavior
        ...     if current_user.has_scope(SCOPE_STATEMENTS_READ):
        ...         return all_statements
        ...     else:
        ...         return user_statements
    """
    async def scope_checker(
        current_user: AuthenticatedUser = Depends(get_current_user)
    ) -> None:
        """
        Check if user has at least one of the allowed scopes.

        Args:
            current_user: Authenticated user from token validation

        Raises:
            HTTPException: 403 Forbidden if user has none of the allowed scopes
        """
        user_scopes = set(current_user.scopes)
        has_any_scope = bool(user_scopes & set(allowed_scopes))

        if not has_any_scope:
            logger.warning(
                "Scope enforcement failed: no allowed scopes",
                extra={
                    "user_id": current_user.user_id,
                    "tenant_id": current_user.tenant_id,
                    "allowed_scopes": list(allowed_scopes),
                    "user_scopes": list(user_scopes),
                },
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "insufficient_scope",
                    "error_description": f"Requires one of: {', '.join(sorted(allowed_scopes))}",
                    "allowed_scopes": sorted(allowed_scopes),
                },
            )

        logger.debug(
            "Scope enforcement passed (any scope)",
            extra={
                "user_id": current_user.user_id,
                "allowed_scopes": list(allowed_scopes),
                "matched_scopes": sorted(user_scopes & set(allowed_scopes)),
            },
        )

    return scope_checker


def has_scope(user: AuthenticatedUser, scope: str) -> bool:
    """
    Helper function to check if user has a specific scope.

    Useful for conditional logic within route handlers where you need to
    differentiate behavior based on scope level (e.g., read-only vs read-write).

    This is a convenience wrapper around AuthenticatedUser.has_scope() for
    better discoverability and consistency with other scope utilities.

    Args:
        user: Authenticated user
        scope: Scope to check

    Returns:
        True if user has the scope, False otherwise

    Example:
        >>> from app.api.dependencies.scopes import has_scope
        >>> from app.schemas.auth import SCOPE_STATEMENTS_WRITE
        >>>
        >>> @router.get("/statements/{statement_id}")
        >>> async def get_statement(
        ...     statement_id: str,
        ...     current_user: CurrentUser,
        ... ):
        ...     # Conditional logic based on scope
        ...     if has_scope(current_user, SCOPE_STATEMENTS_WRITE):
        ...         # Allow edit operations
        ...         return {"statement": statement, "editable": True}
        ...     else:
        ...         # Read-only
        ...         return {"statement": statement, "editable": False}
    """
    return scope in user.scopes


def has_any_scope(user: AuthenticatedUser, *scopes: str) -> bool:
    """
    Helper function to check if user has any of the specified scopes.

    Useful for conditional authorization within route handlers.

    Args:
        user: Authenticated user
        *scopes: Variable number of scopes to check

    Returns:
        True if user has at least one scope, False otherwise

    Example:
        >>> from app.api.dependencies.scopes import has_any_scope
        >>> from app.schemas.auth import SCOPE_ADMIN, SCOPE_TENANT_ADMIN
        >>>
        >>> if has_any_scope(current_user, SCOPE_ADMIN, SCOPE_TENANT_ADMIN):
        ...     # User has admin privileges
        ...     show_admin_controls = True
    """
    return bool(set(user.scopes) & set(scopes))


def has_all_scopes(user: AuthenticatedUser, *scopes: str) -> bool:
    """
    Helper function to check if user has all specified scopes.

    Useful for conditional authorization within route handlers when you need
    to verify multiple permissions are present.

    Args:
        user: Authenticated user
        *scopes: Variable number of scopes to check

    Returns:
        True if user has all scopes, False otherwise

    Example:
        >>> from app.api.dependencies.scopes import has_all_scopes
        >>> from app.schemas.auth import SCOPE_STATEMENTS_WRITE, SCOPE_STATE_WRITE
        >>>
        >>> if has_all_scopes(current_user, SCOPE_STATEMENTS_WRITE, SCOPE_STATE_WRITE):
        ...     # User can write both statements and state
        ...     enable_full_edit = True
    """
    return set(scopes).issubset(set(user.scopes))
