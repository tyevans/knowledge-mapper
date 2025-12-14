"""
Security utilities for JWT validation and cryptographic operations.

This module provides helper functions for JWT token parsing and validation,
focusing on extracting headers and claims for signature verification.
"""

from typing import Dict, Any, Optional
import jwt


def get_unverified_jwt_header(token: str) -> Dict[str, Any]:
    """
    Extract JWT header without verification.

    Used to get 'kid' (key ID) and 'alg' (algorithm) for signature verification.
    This is safe to use before verification to determine which key to use.

    Args:
        token: JWT token string (format: header.payload.signature)

    Returns:
        Decoded JWT header dictionary containing fields like 'kid', 'alg', 'typ'

    Raises:
        jwt.DecodeError: If token format is invalid or cannot be decoded

    Example:
        >>> header = get_unverified_jwt_header(token)
        >>> key_id = header['kid']
        >>> algorithm = header['alg']
    """
    return jwt.get_unverified_header(token)


def get_unverified_jwt_claims(token: str) -> Dict[str, Any]:
    """
    Extract JWT claims (payload) without verification.

    Useful for debugging and logging, but NEVER trust these claims for authorization
    until the token signature has been verified. This is intended for inspection only.

    Args:
        token: JWT token string

    Returns:
        Decoded JWT payload dictionary containing claims like 'sub', 'iss', 'exp', 'aud'

    Raises:
        jwt.DecodeError: If token format is invalid or cannot be decoded

    Example:
        >>> claims = get_unverified_jwt_claims(token)
        >>> issuer = claims.get('iss')
        >>> subject = claims.get('sub')

    Warning:
        Do NOT use these claims for access control decisions. Always verify the
        signature first using a proper JWT validation function.
    """
    return jwt.decode(token, options={"verify_signature": False})
