"""
Event-sourced aggregates for Knowledge Mapper.

This module provides aggregate implementations using eventsource-py's
DeclarativeAggregate pattern for managing domain state through events.

Aggregates:
- ExtractionProcess: Manages the lifecycle of knowledge extraction from pages

Example:
    >>> from uuid import uuid4
    >>> from eventsource import InMemoryEventStore
    >>> from app.eventsourcing.aggregates import (
    ...     ExtractionProcess,
    ...     ExtractionStatus,
    ...     create_extraction_process_repository,
    ... )
    >>>
    >>> # Create a repository
    >>> store = InMemoryEventStore()
    >>> repo = create_extraction_process_repository(store)
    >>>
    >>> # Create and use an aggregate
    >>> process = repo.create_new(uuid4())
    >>> process.request_extraction(
    ...     page_id=uuid4(),
    ...     tenant_id=uuid4(),
    ...     page_url="https://example.com",
    ...     content_hash="abc123",
    ... )
"""

from app.eventsourcing.aggregates.extraction import (
    ExtractedEntityRecord,
    ExtractedRelationshipRecord,
    ExtractionProcess,
    ExtractionProcessState,
    ExtractionStatus,
    create_extraction_process_repository,
)

__all__ = [
    # Extraction Process Aggregate
    "ExtractionProcess",
    "ExtractionProcessState",
    "ExtractionStatus",
    "ExtractedEntityRecord",
    "ExtractedRelationshipRecord",
    "create_extraction_process_repository",
]
