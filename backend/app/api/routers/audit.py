"""
Audit log endpoint for viewing recent domain events.

Provides read-only access to the event store for audit and monitoring purposes.
"""

from datetime import datetime
from typing import Annotated

from eventsource.stores import ReadDirection, ReadOptions
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.dependencies.eventsourcing import EventStoreDep


class AuditEventResponse(BaseModel):
    """Single audit event response."""

    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    global_position: int
    stream_position: int
    occurred_at: datetime
    stored_at: datetime
    actor_id: str | None = None
    summary: str = Field(description="Human-readable summary of the event")


class AuditLogResponse(BaseModel):
    """Paginated audit log response."""

    events: list[AuditEventResponse]
    total_position: int = Field(description="Maximum global position in the event store")
    has_more: bool


class AuditStatsResponse(BaseModel):
    """Statistics about the event store."""

    total_events: int
    event_type_counts: dict[str, int]
    aggregate_type_counts: dict[str, int]


router = APIRouter(prefix="/audit", tags=["audit"])


def _create_event_summary(event_type: str, event_data: dict) -> str:
    """Create a human-readable summary for an event."""
    summaries = {
        "ScrapingJobCreated": lambda d: f"Created scraping job '{d.get('name', 'Unknown')}'",
        "ScrapingJobStarted": lambda d: "Started scraping job",
        "ScrapingJobCompleted": lambda d: f"Completed scraping job ({d.get('total_pages', 0)} pages, {d.get('total_entities', 0)} entities)",
        "ScrapingJobFailed": lambda d: f"Scraping job failed: {d.get('error_message', 'Unknown error')[:50]}",
        "ScrapingJobCancelled": lambda d: "Scraping job cancelled",
        "ScrapingJobPaused": lambda d: "Scraping job paused",
        "ScrapingJobResumed": lambda d: "Scraping job resumed",
        "PageScraped": lambda d: f"Scraped page: {d.get('url', 'Unknown')[:50]}",
        "PageScrapingFailed": lambda d: f"Failed to scrape page: {d.get('url', 'Unknown')[:40]}",
        "EntityExtracted": lambda d: f"Extracted {d.get('entity_type', 'Unknown')} entity: {d.get('name', 'Unknown')[:30]}",
        "EntitiesExtractedBatch": lambda d: f"Extracted batch of {d.get('entity_count', 0)} entities",
        "EntityRelationshipCreated": lambda d: f"Created {d.get('relationship_type', 'Unknown')} relationship",
        "ExtractionFailed": lambda d: f"Extraction failed: {d.get('error_message', 'Unknown')[:50]}",
        "EntitySyncedToNeo4j": lambda d: "Synced entity to Neo4j",
        "RelationshipSyncedToNeo4j": lambda d: "Synced relationship to Neo4j",
        "Neo4jSyncFailed": lambda d: f"Neo4j sync failed: {d.get('error_message', 'Unknown')[:50]}",
    }

    generator = summaries.get(event_type)
    if generator:
        try:
            return generator(event_data)
        except Exception:
            pass

    return f"{event_type} event occurred"


@router.get(
    "/events",
    response_model=AuditLogResponse,
    summary="Get recent audit events",
    description="Retrieves recent domain events from the event store for audit purposes."
)
async def get_audit_events(
    event_store: EventStoreDep,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    limit: int = Query(default=50, ge=1, le=200, description="Number of events to return"),
    from_position: int = Query(default=0, ge=0, description="Start from this global position"),
    direction: str = Query(default="backward", pattern="^(forward|backward)$", description="Read direction"),
) -> AuditLogResponse:
    """
    Get recent audit events.

    Returns the most recent domain events by default (backward direction).
    Events are filtered by the user's tenant_id for multi-tenant isolation.
    """
    options = ReadOptions(
        direction=ReadDirection.BACKWARD if direction == "backward" else ReadDirection.FORWARD,
        from_position=from_position,
        limit=limit,
        tenant_id=user.tenant_id,
    )

    events: list[AuditEventResponse] = []
    async for stored_event in event_store.read_all(options):
        event = stored_event.event
        event_data = event.model_dump() if hasattr(event, "model_dump") else {}

        events.append(
            AuditEventResponse(
                event_id=str(event.event_id),
                event_type=event.event_type,
                aggregate_type=event.aggregate_type,
                aggregate_id=str(event.aggregate_id),
                global_position=stored_event.global_position,
                stream_position=stored_event.stream_position,
                occurred_at=event.occurred_at,
                stored_at=stored_event.stored_at,
                actor_id=event.actor_id if hasattr(event, "actor_id") else None,
                summary=_create_event_summary(event.event_type, event_data),
            )
        )

    # Get total position for pagination
    total_position = await event_store.get_global_position()

    # Determine if there are more events
    has_more = len(events) == limit

    return AuditLogResponse(
        events=events,
        total_position=total_position,
        has_more=has_more,
    )


@router.get(
    "/stats",
    response_model=AuditStatsResponse,
    summary="Get audit statistics",
    description="Returns aggregate statistics about events in the store."
)
async def get_audit_stats(
    event_store: EventStoreDep,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuditStatsResponse:
    """
    Get audit statistics.

    Returns counts of events by type and aggregate type for the user's tenant.
    """
    options = ReadOptions(
        tenant_id=user.tenant_id,
        limit=1000,  # Cap at 1000 for performance
    )

    event_type_counts: dict[str, int] = {}
    aggregate_type_counts: dict[str, int] = {}
    total_events = 0

    async for stored_event in event_store.read_all(options):
        event = stored_event.event
        total_events += 1

        # Count by event type
        event_type = event.event_type
        event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1

        # Count by aggregate type
        aggregate_type = event.aggregate_type
        aggregate_type_counts[aggregate_type] = aggregate_type_counts.get(aggregate_type, 0) + 1

    return AuditStatsResponse(
        total_events=total_events,
        event_type_counts=event_type_counts,
        aggregate_type_counts=aggregate_type_counts,
    )
