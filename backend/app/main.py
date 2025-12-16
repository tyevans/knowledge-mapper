"""
Main FastAPI application.

This module initializes the FastAPI application with middleware,
routers, and error handlers.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.api.routers import health, test_auth, auth, oauth, todos, tenants, well_known, scraping, health_extraction, graph, entities, audit, consolidation, extraction_providers
from app.middleware.tenant import TenantResolutionMiddleware

from app.observability import setup_observability

# Event sourcing imports
from app.eventsourcing.stores.factory import get_event_store, close_event_store
from app.eventsourcing.bus.factory import get_kafka_bus, close_kafka_bus
from app.eventsourcing.outbox.publisher import OutboxPublisher
from app.eventsourcing.subscriptions import get_subscription_manager, close_subscription_manager

# Neo4j service
from app.services.neo4j import close_neo4j_service



from app.middleware.security import SecurityHeadersMiddleware, SecurityHeadersConfig



# Global outbox publisher instance
_outbox_publisher: OutboxPublisher | None = None

# Global subscription manager instance (managed by get_subscription_manager)
_subscription_manager_started: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager for startup and shutdown events.

    Args:
        app: FastAPI application instance

    Yields:
        None
    """
    global _outbox_publisher, _subscription_manager_started

    # Startup
    print(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"Debug mode: {settings.DEBUG}")
    print(f"API prefix: {settings.API_V1_PREFIX}")

    # Initialize event sourcing components
    if settings.EVENT_STORE_ENABLED:
        print("Initializing event store...")
        await get_event_store()
        print("Event store: initialized")

    if settings.KAFKA_ENABLED:
        try:
            print("Connecting to Kafka...")
            kafka_bus = await get_kafka_bus()
            print(f"Kafka: connected to {settings.KAFKA_BOOTSTRAP_SERVERS}")

            # Start outbox publisher if outbox is enabled
            if settings.EVENT_STORE_OUTBOX_ENABLED:
                print("Starting outbox publisher...")
                _outbox_publisher = OutboxPublisher(kafka_bus)
                await _outbox_publisher.start()
                print("Outbox publisher: started")

            # Start subscription manager for projection handlers
            if settings.EVENT_STORE_ENABLED:
                try:
                    print("Starting subscription manager...")
                    subscription_manager = await get_subscription_manager()
                    await subscription_manager.start()
                    _subscription_manager_started = True
                    print("Subscription manager: started")
                except Exception as e:
                    print(f"Subscription manager start failed (non-fatal): {e}")
                    print("Continuing without subscriptions - projections will not update")
        except Exception as e:
            print(f"Kafka connection failed (non-fatal): {e}")
            print("Continuing without Kafka - events will not be published")

    yield

    # Shutdown
    print(f"Shutting down {settings.APP_NAME}")

    # Stop subscription manager first (before other cleanup)
    if _subscription_manager_started:
        print("Stopping subscription manager...")
        await close_subscription_manager()
        print("Subscription manager: stopped")

    # Stop outbox publisher
    if _outbox_publisher is not None:
        print("Stopping outbox publisher...")
        await _outbox_publisher.stop()
        print("Outbox publisher: stopped")

    # Close Kafka connection
    if settings.KAFKA_ENABLED:
        print("Disconnecting from Kafka...")
        await close_kafka_bus()
        print("Kafka: disconnected")

    # Close Neo4j connection
    print("Closing Neo4j connection...")
    await close_neo4j_service()
    print("Neo4j: closed")

    # Close event store
    if settings.EVENT_STORE_ENABLED:
        print("Closing event store...")
        await close_event_store()
        print("Event store: closed")


# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""A knowledge scraping and mapping tool""",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    debug=settings.DEBUG
)




# Setup observability (tracing, metrics, logging)
# Must be called before other middleware to ensure all requests are instrumented
setup_observability(app)



# Security Headers Middleware (P2-02)
# Adds security-related HTTP headers to all responses
# Must be added before CORS middleware to ensure headers are present on all responses
if settings.SECURITY_HEADERS_ENABLED:
    # Build connect-src with frontend URL
    connect_src = settings.CSP_CONNECT_SRC
    if settings.FRONTEND_URL and settings.FRONTEND_URL not in connect_src:
        connect_src = f"{connect_src} {settings.FRONTEND_URL}"

    security_config = SecurityHeadersConfig(
        # CSP Configuration
        csp_enabled=settings.CSP_ENABLED,
        csp_default_src=settings.CSP_DEFAULT_SRC,
        csp_script_src=settings.CSP_SCRIPT_SRC,
        csp_style_src=settings.CSP_STYLE_SRC,
        csp_img_src=settings.CSP_IMG_SRC,
        csp_font_src=settings.CSP_FONT_SRC,
        csp_connect_src=connect_src,
        csp_frame_ancestors=settings.CSP_FRAME_ANCESTORS,
        csp_base_uri=settings.CSP_BASE_URI,
        csp_form_action=settings.CSP_FORM_ACTION,
        csp_report_uri=settings.CSP_REPORT_URI or None,

        # HSTS Configuration
        hsts_enabled=settings.HSTS_ENABLED,
        hsts_max_age=settings.HSTS_MAX_AGE,
        hsts_include_subdomains=settings.HSTS_INCLUDE_SUBDOMAINS,
        hsts_preload=settings.HSTS_PRELOAD,

        # Other Headers
        x_frame_options=settings.X_FRAME_OPTIONS or None,
        x_content_type_options=settings.X_CONTENT_TYPE_OPTIONS or None,
        referrer_policy=settings.REFERRER_POLICY or None,
        permissions_policy=settings.PERMISSIONS_POLICY or None,
        x_xss_protection=settings.X_XSS_PROTECTION or None,
    )
    app.add_middleware(SecurityHeadersMiddleware, config=security_config)
    print(f"Security headers: enabled (CSP={settings.CSP_ENABLED}, HSTS={settings.HSTS_ENABLED})")
else:
    print("Security headers: disabled via SECURITY_HEADERS_ENABLED=false")


# Configure CORS middleware
# Runs after observability middleware to ensure CORS-rejected requests are also instrumented
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Tenant Resolution Middleware
# Runs after CORS, before route handlers
# Extracts tenant_id from authenticated requests and sets context
app.add_middleware(TenantResolutionMiddleware)


# Exception handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Handle HTTP exceptions with structured JSON responses.

    Args:
        request: The incoming request
        exc: The HTTP exception

    Returns:
        JSONResponse: Structured error response
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "type": "http_exception"
            }
        },
        headers=exc.headers  # Preserve headers (e.g., Retry-After for rate limiting)
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handle request validation errors with detailed field-level errors.

    Args:
        request: The incoming request
        exc: The validation exception

    Returns:
        JSONResponse: Structured validation error response
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": 422,
                "message": "Validation error",
                "type": "validation_error",
                "details": exc.errors()
            }
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unexpected exceptions with generic error response.

    Args:
        request: The incoming request
        exc: The exception

    Returns:
        JSONResponse: Generic error response
    """
    # In production, log the full exception details
    print(f"Unhandled exception: {exc}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": 500,
                "message": "Internal server error",
                "type": "internal_error"
            }
        }
    )


# Include routers
app.include_router(health.router, prefix=settings.API_V1_PREFIX)
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(oauth.router, prefix=settings.API_V1_PREFIX)
app.include_router(todos.router, prefix=settings.API_V1_PREFIX)
app.include_router(test_auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(tenants.router, prefix=settings.API_V1_PREFIX)
app.include_router(scraping.router, prefix=settings.API_V1_PREFIX)
app.include_router(health_extraction.router, prefix=settings.API_V1_PREFIX)
app.include_router(graph.router, prefix=settings.API_V1_PREFIX)
app.include_router(entities.router, prefix=settings.API_V1_PREFIX)
app.include_router(audit.router, prefix=settings.API_V1_PREFIX)
app.include_router(consolidation.router, prefix=settings.API_V1_PREFIX)
app.include_router(extraction_providers.router, prefix=settings.API_V1_PREFIX)

# Well-known endpoints (no API prefix - root level)
app.include_router(well_known.router)


# Root endpoint
@app.get(
    "/",
    tags=["root"],
    summary="Root endpoint",
    description="Returns basic information about the API"
)
async def root() -> dict[str, str]:
    """
    Root endpoint providing basic API information.

    Returns:
        dict: Basic API information
    """
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": f"{settings.API_V1_PREFIX}/health"
    }
