"""
Celery application configuration for background task processing.

This module configures Celery for handling asynchronous tasks such as:
- Web scraping jobs
- Entity extraction
- Knowledge graph synchronization

All tasks are tenant-aware and maintain proper isolation.
"""

import logging
import os

from celery import Celery
from celery.signals import after_setup_logger, after_setup_task_logger
from kombu import Exchange, Queue

from app.core.config import settings
from app.observability import StructuredJsonFormatter

# Create Celery app
celery_app = Celery(
    "knowledge_mapper",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Configure Celery
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_acks_late=True,  # Tasks acknowledged after execution
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    task_track_started=True,  # Track when tasks start

    # Result backend settings
    result_expires=86400,  # Results expire after 24 hours
    result_extended=True,  # Store additional task metadata

    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time per worker
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks

    # Broker connection settings
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,

    # Task routes - direct tasks to appropriate queues
    task_routes={
        "app.tasks.scraping.*": {"queue": "scraping"},
        "app.tasks.extraction.*": {"queue": "extraction"},
        "app.tasks.graph.*": {"queue": "graph"},
        "app.tasks.consolidation.*": {"queue": "consolidation"},
    },

    # Beat schedule for periodic tasks
    beat_schedule={
        "cleanup-stale-jobs": {
            "task": "app.tasks.scraping.cleanup_stale_jobs",
            "schedule": 3600.0,  # Every hour
        },
        "sync-entities-to-neo4j": {
            "task": "app.tasks.graph.sync_pending_entities",
            "schedule": 300.0,  # Every 5 minutes
        },
    },

    # Task annotations for rate limiting
    task_annotations={
        "app.tasks.extraction.extract_entities_llm": {
            "rate_limit": f"{settings.LLM_RATE_LIMIT_RPM}/m",
        },
    },
)

# Define queues
celery_app.conf.task_queues = (
    Queue(
        "scraping",
        Exchange("scraping"),
        routing_key="scraping",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "extraction",
        Exchange("extraction"),
        routing_key="extraction",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "graph",
        Exchange("graph"),
        routing_key="graph",
        queue_arguments={"x-max-priority": 5},
    ),
    Queue(
        "consolidation",
        Exchange("consolidation"),
        routing_key="consolidation",
        queue_arguments={"x-max-priority": 5},
    ),
)

# Default queue
celery_app.conf.task_default_queue = "scraping"

# Autodiscover tasks from these modules
celery_app.autodiscover_tasks([
    "app.tasks.scraping",
    "app.tasks.extraction",
    "app.tasks.graph",
    "app.tasks.consolidation",
])


# =============================================================================
# Celery Logging Configuration
# =============================================================================

def _setup_celery_json_logging(logger: logging.Logger, **kwargs) -> None:
    """
    Configure Celery logger to use JSON formatting with extra fields.

    This replaces Celery's default handlers with our StructuredJsonFormatter,
    ensuring consistent JSON logging across both FastAPI and Celery workers.
    """
    is_testing = os.getenv("TESTING", "false").lower() == "true"

    if is_testing:
        # Keep simple format for tests
        return

    # Remove all existing handlers
    logger.handlers.clear()

    # Add our JSON handler
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(StructuredJsonFormatter())
    logger.addHandler(handler)


@after_setup_logger.connect
def setup_celery_logger(logger: logging.Logger, **kwargs) -> None:
    """Configure the main Celery logger."""
    _setup_celery_json_logging(logger, **kwargs)


@after_setup_task_logger.connect
def setup_celery_task_logger(logger: logging.Logger, **kwargs) -> None:
    """Configure the Celery task logger."""
    _setup_celery_json_logging(logger, **kwargs)


# Task base class with common functionality
class TenantAwareTask(celery_app.Task):
    """
    Base task class with tenant context support.

    All scraping-related tasks should inherit from this class
    to ensure proper tenant isolation.
    """

    abstract = True

    def before_start(self, task_id, args, kwargs):
        """Called before task execution."""
        tenant_id = kwargs.get("tenant_id")
        if tenant_id:
            from app.worker.context import set_current_tenant
            set_current_tenant(tenant_id)

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """Called after task completes."""
        from app.worker.context import clear_current_tenant
        clear_current_tenant()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called on task failure."""
        import logging
        logger = logging.getLogger(__name__)
        logger.error(
            f"Task {self.name} failed",
            extra={
                "task_id": task_id,
                "tenant_id": kwargs.get("tenant_id"),
                "error": str(exc),
            },
            exc_info=True,
        )


# Register the base task
celery_app.Task = TenantAwareTask
