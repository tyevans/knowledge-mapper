"""
Health check endpoints for extraction pipeline components.

Provides health status for:
- Ollama LLM service
- Neo4j graph database
- Circuit breaker state
- Rate limiter status
- Subscription manager (event processing)

These endpoints are designed for Kubernetes health probes and operational monitoring.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ComponentHealth(BaseModel):
    """Health status for a single component."""

    status: str
    error: str | None = None


class OllamaHealth(BaseModel):
    """Health status for Ollama service."""

    status: str
    base_url: str
    model: str
    available_models: list[str] | None = None
    model_available: bool | None = None
    error: str | None = None


class Neo4jHealth(BaseModel):
    """Health status for Neo4j service."""

    status: str
    uri: str
    database: str
    latency_ms: float | None = None
    error: str | None = None


class CircuitBreakerHealth(BaseModel):
    """Health status for circuit breaker."""

    status: str
    state: str
    failure_threshold: int
    recovery_timeout: int
    retry_after: float | None = None
    error: str | None = None


class RateLimiterHealth(BaseModel):
    """Health status for rate limiter."""

    status: str
    requests_per_minute: int
    window_seconds: int
    error: str | None = None


class SubscriptionHealth(BaseModel):
    """Health status for subscription manager."""

    status: str
    running: bool
    subscription_count: int | None = None
    subscriptions: list[str] | None = None
    error: str | None = None


class ExtractionHealthResponse(BaseModel):
    """Aggregated health status for all extraction components."""

    status: str
    components: dict[str, Any]


router = APIRouter(prefix="/health", tags=["extraction-health"])


@router.get(
    "/extraction",
    response_model=ExtractionHealthResponse,
    summary="Extraction pipeline health",
    description="Check health of all extraction pipeline components.",
)
async def extraction_health() -> ExtractionHealthResponse:
    """
    Check extraction pipeline health.

    Returns aggregated health status for:
    - Ollama LLM service
    - Neo4j graph database
    - Circuit breaker
    - Rate limiter
    - Subscription manager

    Returns:
        ExtractionHealthResponse with status and component details
    """
    results: dict[str, Any] = {}

    # Check Ollama
    try:
        from app.extraction.ollama_extractor import get_ollama_extraction_service

        service = get_ollama_extraction_service()
        ollama_result = await service.health_check()
        results["ollama"] = ollama_result
    except Exception as e:
        logger.exception("Ollama health check failed")
        results["ollama"] = {"status": "unhealthy", "error": str(e)}

    # Check Neo4j
    try:
        from app.services.neo4j import get_neo4j_service

        neo4j = await get_neo4j_service()
        neo4j_result = await neo4j.health_check()
        results["neo4j"] = neo4j_result
    except Exception as e:
        logger.exception("Neo4j health check failed")
        results["neo4j"] = {"status": "unhealthy", "error": str(e)}

    # Check Circuit Breaker
    try:
        from app.extraction.circuit_breaker import get_circuit_breaker

        breaker = get_circuit_breaker()
        state = await breaker.get_state()
        retry_after = await breaker.get_retry_after() if state.value == "open" else None

        results["circuit_breaker"] = {
            "status": "healthy",
            "state": state.value,
            "failure_threshold": breaker.failure_threshold,
            "recovery_timeout": breaker.recovery_timeout,
            "retry_after": retry_after,
        }
    except Exception as e:
        logger.exception("Circuit breaker health check failed")
        results["circuit_breaker"] = {"status": "unhealthy", "error": str(e)}

    # Check Rate Limiter
    try:
        from app.extraction.rate_limiter import get_rate_limiter

        limiter = get_rate_limiter()
        results["rate_limiter"] = {
            "status": "healthy",
            "requests_per_minute": limiter._rpm,
            "window_seconds": limiter._window,
        }
    except Exception as e:
        logger.exception("Rate limiter health check failed")
        results["rate_limiter"] = {"status": "unhealthy", "error": str(e)}

    # Check Subscription Manager
    try:
        from app.eventsourcing.subscriptions import get_subscription_manager

        manager = await get_subscription_manager()
        health = manager.get_health()
        results["subscriptions"] = {
            "status": "healthy" if manager.is_running else "stopped",
            "running": manager.is_running,
            "subscription_count": health.get("subscription_count"),
            "subscriptions": health.get("subscriptions", []),
        }
    except Exception as e:
        logger.exception("Subscription manager health check failed")
        results["subscriptions"] = {"status": "unhealthy", "error": str(e)}

    # Calculate overall status
    all_healthy = all(
        r.get("status") in ("healthy", "stopped") for r in results.values()
    )

    return ExtractionHealthResponse(
        status="healthy" if all_healthy else "degraded",
        components=results,
    )


@router.get(
    "/ollama",
    response_model=OllamaHealth,
    responses={503: {"description": "Ollama unhealthy"}},
    summary="Ollama health check",
    description="Check Ollama LLM service connectivity and model availability.",
)
async def ollama_health() -> OllamaHealth:
    """
    Check Ollama specifically.

    Returns 200 if Ollama is healthy, 503 if unhealthy.

    Returns:
        OllamaHealth with status and details

    Raises:
        HTTPException: 503 if Ollama is unhealthy
    """
    try:
        from app.extraction.ollama_extractor import get_ollama_extraction_service

        service = get_ollama_extraction_service()
        result = await service.health_check()

        if result.get("status") != "healthy":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result,
            )

        return OllamaHealth(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ollama health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "error": str(e)},
        ) from e


@router.get(
    "/neo4j",
    response_model=Neo4jHealth,
    responses={503: {"description": "Neo4j unhealthy"}},
    summary="Neo4j health check",
    description="Check Neo4j graph database connectivity.",
)
async def neo4j_health() -> Neo4jHealth:
    """
    Check Neo4j specifically.

    Returns 200 if Neo4j is healthy, 503 if unhealthy.

    Returns:
        Neo4jHealth with status and connection details

    Raises:
        HTTPException: 503 if Neo4j is unhealthy
    """
    try:
        from app.services.neo4j import get_neo4j_service

        service = await get_neo4j_service()
        result = await service.health_check()

        if result.get("status") != "healthy":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result,
            )

        return Neo4jHealth(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Neo4j health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "error": str(e)},
        ) from e


@router.get(
    "/circuit-breaker",
    response_model=CircuitBreakerHealth,
    responses={503: {"description": "Circuit breaker unhealthy"}},
    summary="Circuit breaker status",
    description="Check circuit breaker state for the Ollama service.",
)
async def circuit_breaker_health() -> CircuitBreakerHealth:
    """
    Check circuit breaker status.

    Returns 200 with circuit breaker state information.

    Returns:
        CircuitBreakerHealth with state and configuration details

    Raises:
        HTTPException: 503 if circuit breaker check fails
    """
    try:
        from app.extraction.circuit_breaker import get_circuit_breaker

        breaker = get_circuit_breaker()
        state = await breaker.get_state()
        retry_after = await breaker.get_retry_after() if state.value == "open" else None

        return CircuitBreakerHealth(
            status="healthy",
            state=state.value,
            failure_threshold=breaker.failure_threshold,
            recovery_timeout=breaker.recovery_timeout,
            retry_after=retry_after,
        )
    except Exception as e:
        logger.exception("Circuit breaker health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "error": str(e)},
        ) from e


@router.get(
    "/rate-limiter",
    response_model=RateLimiterHealth,
    responses={503: {"description": "Rate limiter unhealthy"}},
    summary="Rate limiter status",
    description="Check rate limiter configuration and status.",
)
async def rate_limiter_health() -> RateLimiterHealth:
    """
    Check rate limiter status.

    Returns 200 with rate limiter configuration information.

    Returns:
        RateLimiterHealth with configuration details

    Raises:
        HTTPException: 503 if rate limiter check fails
    """
    try:
        from app.extraction.rate_limiter import get_rate_limiter

        limiter = get_rate_limiter()

        return RateLimiterHealth(
            status="healthy",
            requests_per_minute=limiter._rpm,
            window_seconds=limiter._window,
        )
    except Exception as e:
        logger.exception("Rate limiter health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "error": str(e)},
        ) from e


@router.get(
    "/subscriptions",
    response_model=SubscriptionHealth,
    responses={503: {"description": "Subscription manager unhealthy"}},
    summary="Subscription manager status",
    description="Check event subscription manager status.",
)
async def subscriptions_health() -> SubscriptionHealth:
    """
    Check subscription manager status.

    Returns 200 with subscription manager state. Status will be
    'stopped' if manager is not running but check succeeded.

    Returns:
        SubscriptionHealth with running state and subscription details

    Raises:
        HTTPException: 503 if subscription manager check fails
    """
    try:
        from app.eventsourcing.subscriptions import get_subscription_manager

        manager = await get_subscription_manager()
        health = manager.get_health()

        return SubscriptionHealth(
            status="healthy" if manager.is_running else "stopped",
            running=manager.is_running,
            subscription_count=health.get("subscription_count"),
            subscriptions=health.get("subscriptions", []),
        )
    except Exception as e:
        logger.exception("Subscription manager health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "error": str(e)},
        ) from e
