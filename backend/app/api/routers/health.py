"""
Health check endpoints for monitoring and orchestration.

Provides basic health status and readiness checks for the application.
"""

from datetime import datetime
from fastapi import APIRouter, status
from pydantic import BaseModel

from app.core.config import settings


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    service: str
    version: str
    timestamp: datetime


router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
    description="Returns the health status of the service for monitoring and orchestration."
)
async def health_check() -> HealthResponse:
    """
    Perform a basic health check.

    Returns:
        HealthResponse: Current health status of the service
    """
    return HealthResponse(
        status="healthy",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        timestamp=datetime.utcnow()
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness check endpoint",
    description="Returns readiness status indicating if the service can accept requests."
)
async def readiness_check() -> HealthResponse:
    """
    Perform a readiness check.

    In a full implementation, this would check database connectivity,
    external service availability, etc.

    Returns:
        HealthResponse: Current readiness status of the service
    """
    return HealthResponse(
        status="ready",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        timestamp=datetime.utcnow()
    )
