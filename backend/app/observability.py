"""
Observability instrumentation for Knowledge Mapper.

This module configures comprehensive observability for the FastAPI application:

1. **OpenTelemetry Distributed Tracing**
   - Automatic request tracing with span context
   - Export to Tempo via OTLP gRPC protocol
   - Service graph support via OpenTelemetry metrics

2. **Prometheus Metrics**
   - HTTP request counters (method, endpoint, status)
   - Request duration histograms
   - Active request gauges
   - Exposed at /metrics endpoint for Prometheus scraping

3. **Structured Logging**
   - Trace context correlation (trace_id, span_id)
   - Test mode support for clean pytest output

Environment Variables:
    OTEL_SERVICE_NAME: Service name for traces (default: "backend")
    OTEL_EXPORTER_OTLP_ENDPOINT: Tempo OTLP endpoint (default: "http://tempo:4317")
    TESTING: Set to "true" to disable trace context in logs

Usage:
    from app.observability import setup_observability

    app = FastAPI()
    setup_observability(app)

Architecture Notes:
    - Uses fail-open pattern: If Tempo is unavailable, traces are dropped silently
      without affecting application availability (NFR-RL-001)
    - Health endpoint (/api/v1/health) is excluded from tracing to reduce noise (OQ-005)
    - Metrics middleware runs on every request for accurate instrumentation
    - BatchSpanProcessor handles export asynchronously to avoid blocking requests
"""

import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pythonjsonlogger import jsonlogger

# =============================================================================
# Configuration
# =============================================================================

# Service identification for distributed tracing
# This name appears in Tempo and Grafana service graphs
SERVICE_NAME_VAL = os.getenv("OTEL_SERVICE_NAME", "backend")

# OTLP endpoint for trace and metric export
# Default points to Tempo service in Docker Compose network
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://tempo:4317")

# Endpoints to exclude from tracing (OQ-005)
# Health checks are frequent and add noise without value
EXCLUDED_TRACE_ENDPOINTS = frozenset({
    "/api/v1/health",
    "/api/v1/ready",
    "/metrics",
    "/health",
    "/ready",
})


# =============================================================================
# Logging Configuration
# =============================================================================

# Reserved log record attributes that should not be treated as extra fields
# These are standard Python logging attributes plus our custom trace fields
RESERVED_LOG_ATTRS = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
    # Our custom trace context fields
    "trace_id", "span_id", "service",
})


class StructuredJsonFormatter(jsonlogger.JsonFormatter):
    """
    JSON formatter that includes OpenTelemetry trace context and extra fields.

    This formatter outputs structured JSON logs that include:
    - Standard log fields (timestamp, level, logger name, message)
    - OpenTelemetry trace context (trace_id, span_id)
    - Service name for multi-service environments
    - All extra fields passed via logger.info("msg", extra={...})

    The JSON output is easy to parse in Loki/Grafana and other log aggregators.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Define the base format with standard fields
        # Additional fields from extra={} are automatically added
        super().__init__(
            *args,
            **kwargs,
            timestamp=True,
        )
        self.service_name = os.getenv("OTEL_SERVICE_NAME", "backend")

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        """Add custom fields to the JSON log record."""
        super().add_fields(log_record, record, message_dict)

        # Add standard fields
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["service"] = self.service_name

        # Add OpenTelemetry trace context
        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            log_record["trace_id"] = format(ctx.trace_id, '032x')
            log_record["span_id"] = format(ctx.span_id, '016x')

        # Add all extra fields that aren't reserved attributes
        # This captures everything passed via extra={...}
        for key, value in record.__dict__.items():
            if key not in RESERVED_LOG_ATTRS and not key.startswith('_'):
                # Skip if already in log_record (avoid duplicates)
                if key not in log_record:
                    log_record[key] = value


def _configure_logging() -> None:
    """
    Configure structured JSON logging with trace context.

    In production mode, outputs JSON logs with:
    - Timestamp, level, logger name, message
    - OpenTelemetry trace_id and span_id for correlation
    - All extra fields from logger calls

    In test mode (TESTING=true), uses simplified text format to avoid
    noise during pytest.

    Example JSON output:
        {"timestamp": "2025-01-15T10:30:00Z", "level": "INFO",
         "logger": "app.tasks.extraction", "message": "Extraction progress",
         "service": "backend", "trace_id": "abc123...", "span_id": "def456...",
         "job_id": "uuid-here", "pages_completed": 5, "total_pages": 10}
    """
    is_testing = os.getenv("TESTING", "false").lower() == "true"

    if is_testing:
        # Simplified format for test environments
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            force=True
        )
    else:
        # JSON format for production - includes all extra fields
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        handler.setFormatter(StructuredJsonFormatter())

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        # Remove any existing handlers and add our configured one
        root_logger.handlers.clear()
        root_logger.addHandler(handler)


# Initialize logging configuration at module load
_configure_logging()


# =============================================================================
# OpenTelemetry Tracing Setup
# =============================================================================

def _create_trace_provider() -> TracerProvider:
    """
    Create and configure the OpenTelemetry TracerProvider.

    Returns:
        TracerProvider: Configured tracer provider with OTLP exporter

    Architecture:
        - Resource: Identifies this service in distributed traces
        - TracerProvider: Central manager for trace creation
        - OTLPSpanExporter: Sends spans to Tempo via gRPC
        - BatchSpanProcessor: Batches spans for efficient export

    Fail-Open Pattern (NFR-RL-001):
        The BatchSpanProcessor handles export failures gracefully:
        - If Tempo is unavailable, spans are queued in memory
        - If queue fills, oldest spans are dropped (no exceptions)
        - Application continues operating normally
        - insecure=True allows non-TLS connections for development
    """
    # Resource attributes identify this service in traces
    resource = Resource(attributes={
        SERVICE_NAME: SERVICE_NAME_VAL
    })

    # Create the tracer provider
    provider = TracerProvider(resource=resource)

    # Configure OTLP exporter for Tempo
    # insecure=True: Use plain gRPC (no TLS) - appropriate for internal networks
    trace_exporter = OTLPSpanExporter(
        endpoint=OTLP_ENDPOINT,
        insecure=True
    )

    # BatchSpanProcessor configuration:
    # - Batches spans to reduce network overhead
    # - Exports asynchronously (doesn't block request handling)
    # - Handles Tempo unavailability gracefully (drops spans if buffer full)
    provider.add_span_processor(BatchSpanProcessor(trace_exporter))

    return provider


# Initialize OpenTelemetry tracer provider at module load
# This ensures tracing is ready before any requests arrive
_trace_provider = _create_trace_provider()
trace.set_tracer_provider(_trace_provider)

# Configure W3C TraceContext propagation for distributed tracing
# This extracts trace context from incoming requests (traceparent header)
# and injects it into outgoing requests, enabling end-to-end trace correlation
set_global_textmap(CompositePropagator([
    TraceContextTextMapPropagator(),  # W3C Trace Context (traceparent, tracestate)
    W3CBaggagePropagator(),           # W3C Baggage (baggage header)
]))


# =============================================================================
# Prometheus Metrics Definitions
# =============================================================================

# Counter: Total HTTP requests processed
# Labels allow filtering/grouping in Grafana dashboards
# - method: HTTP method (GET, POST, PUT, DELETE, etc.)
# - endpoint: Request path (/api/v1/todos, /api/v1/health, etc.)
# - status: HTTP status code (200, 404, 500, etc.)
http_requests_total = Counter(
    name="http_requests_total",
    documentation="Total number of HTTP requests processed",
    labelnames=["method", "endpoint", "status"]
)

# Histogram: Request duration in seconds
# Default buckets optimized for web API latencies:
# .005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, 7.5, 10.0
# Labels: method, endpoint (status excluded to reduce cardinality)
http_request_duration_seconds = Histogram(
    name="http_request_duration_seconds",
    documentation="HTTP request duration in seconds",
    labelnames=["method", "endpoint"]
)

# Gauge: Current number of in-flight requests
# Useful for detecting request queuing and concurrency issues
# No labels to keep this metric simple and fast
active_requests = Gauge(
    name="active_requests",
    documentation="Number of HTTP requests currently being processed"
)


# =============================================================================
# Tracer for Custom Instrumentation
# =============================================================================

# Application code can import this for custom spans:
#
# from app.observability import tracer
#
# with tracer.start_as_current_span("custom_operation") as span:
#     span.set_attribute("custom.attribute", "value")
#     # ... operation code ...

tracer = trace.get_tracer(__name__)


# =============================================================================
# Health Check Filter for Tracing
# =============================================================================

def _should_exclude_from_trace(path: str) -> bool:
    """
    Determine if a request path should be excluded from tracing.

    Per OQ-005, health check endpoints are excluded to reduce trace noise.
    These endpoints are called frequently by load balancers and monitoring
    systems, creating many low-value traces.

    Args:
        path: The request URL path

    Returns:
        True if the path should be excluded from tracing, False otherwise
    """
    return path in EXCLUDED_TRACE_ENDPOINTS


# =============================================================================
# Setup Function
# =============================================================================

def setup_observability(app: FastAPI) -> FastAPI:
    """
    Setup observability instrumentation for a FastAPI application.

    This function performs three main tasks:
    1. Instruments FastAPI with OpenTelemetry for automatic request tracing
    2. Adds HTTP middleware for Prometheus metrics collection
    3. Registers the /metrics endpoint for Prometheus scraping

    Args:
        app: FastAPI application instance to instrument

    Returns:
        The instrumented FastAPI application (same instance, for chaining)

    Example:
        app = FastAPI()
        setup_observability(app)

    Integration:
        Call this function after creating the FastAPI app but before
        adding routes or starting the server. The middleware will
        automatically instrument all subsequent routes.

    Metrics Collected:
        - http_requests_total: Counter with method, endpoint, status labels
        - http_request_duration_seconds: Histogram with method, endpoint labels
        - active_requests: Gauge of concurrent requests

    Tracing:
        - Automatic span creation for all HTTP requests
        - Health endpoints excluded per OQ-005
        - Trace context propagation for distributed tracing
    """
    logger = logging.getLogger(__name__)

    # -------------------------------------------------------------------------
    # 1. Instrument FastAPI with OpenTelemetry
    # -------------------------------------------------------------------------
    # This automatically creates spans for all HTTP requests including:
    # - Request method, URL, headers
    # - Response status code
    # - Exception information if request fails
    #
    # excluded_urls parameter implements OQ-005:
    # Health endpoints are excluded to reduce trace noise
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls=",".join(EXCLUDED_TRACE_ENDPOINTS)
    )

    # -------------------------------------------------------------------------
    # 2. Add Prometheus Metrics Middleware
    # -------------------------------------------------------------------------
    @app.middleware("http")
    async def metrics_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """
        Middleware that collects HTTP metrics for every request.

        This middleware wraps every HTTP request to collect:
        - Active request count (gauge)
        - Request duration (histogram)
        - Request count by method, endpoint, status (counter)

        Args:
            request: The incoming HTTP request
            call_next: Function to call the next middleware/handler

        Returns:
            The HTTP response from downstream handlers

        Performance:
            - Minimal overhead (<1ms per request)
            - Labels are low-cardinality for efficient storage
            - Context manager ensures accurate timing even on errors
        """
        # Increment active requests gauge
        active_requests.inc()

        # Extract request metadata for labels
        method = request.method
        path = request.url.path

        try:
            # Time the request processing and record in histogram
            # The context manager ensures timing is accurate even if
            # an exception occurs during request processing
            with http_request_duration_seconds.labels(
                method=method,
                endpoint=path
            ).time():
                response = await call_next(request)

            # Record request in counter with status
            http_requests_total.labels(
                method=method,
                endpoint=path,
                status=response.status_code
            ).inc()

            return response
        finally:
            # Always decrement active requests, even on error
            active_requests.dec()

    # -------------------------------------------------------------------------
    # 3. Register /metrics Endpoint
    # -------------------------------------------------------------------------
    @app.get(
        "/metrics",
        include_in_schema=False,  # Hide from OpenAPI docs
        tags=["monitoring"]
    )
    async def get_metrics() -> Response:
        """
        Prometheus metrics endpoint.

        Returns all registered metrics in Prometheus exposition format.
        This endpoint is scraped by Prometheus at regular intervals.

        Returns:
            Response: Metrics in text/plain Prometheus format

        Endpoint Details:
            - Path: /metrics
            - Method: GET
            - Auth: None (should be network-restricted in production)
            - Content-Type: text/plain; version=0.0.4; charset=utf-8
        """
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )

    # Log successful initialization
    logger.info(
        f"Observability configured for service '{SERVICE_NAME_VAL}' "
        f"(OTLP endpoint: {OTLP_ENDPOINT})"
    )

    return app
