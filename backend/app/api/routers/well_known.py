"""
Well-known endpoints for service discovery.

This module provides standard well-known endpoints that allow external
services to discover and validate tokens issued by this backend.

Endpoints:
- /.well-known/jwks.json: JSON Web Key Set for app token validation
"""

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from app.services.app_token_service import get_app_token_service

router = APIRouter(prefix="/.well-known", tags=["well-known"])


@router.get(
    "/jwks.json",
    response_class=JSONResponse,
    summary="Get JSON Web Key Set",
    description="""
    Returns the public keys used to sign app tokens in JWKS format.

    External services can use this endpoint to validate JWT tokens
    issued by this backend. The response follows the JWKS specification
    (RFC 7517).

    Response format:
    ```json
    {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "kid": "app-key-1",
                "alg": "RS256",
                "n": "...",
                "e": "..."
            }
        ]
    }
    ```

    Note: This endpoint is public and does not require authentication.
    """,
    responses={
        200: {
            "description": "JSON Web Key Set",
            "content": {
                "application/json": {
                    "example": {
                        "keys": [
                            {
                                "kty": "RSA",
                                "use": "sig",
                                "kid": "app-key-1",
                                "alg": "RS256",
                                "n": "0vx7agoebGcQSuuPiLJXZpt...",
                                "e": "AQAB",
                            }
                        ]
                    }
                }
            },
        }
    },
)
async def get_jwks() -> JSONResponse:
    """
    Return JSON Web Key Set for app token validation.

    This endpoint allows external services to fetch the public key(s)
    used to sign JWT tokens issued by this backend. The keys are returned
    in standard JWKS format (RFC 7517).

    Returns:
        JSONResponse: JWKS containing the public key(s)
    """
    app_token_service = get_app_token_service()
    jwks = app_token_service.get_jwks()

    return JSONResponse(
        content=jwks,
        headers={
            # Allow caching for 1 hour (keys rarely change)
            "Cache-Control": "public, max-age=3600",
            "Content-Type": "application/json",
        },
    )
