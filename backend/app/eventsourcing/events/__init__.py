"""Event definitions for Knowledge Mapper."""

from app.eventsourcing.events.base import TenantDomainEvent
from app.eventsourcing.events.extraction import (
    ExtractionBatchCompleted,
    ExtractionBatchStarted,
    ExtractionCompleted,
    ExtractionProcessFailed,
    ExtractionRequested,
    ExtractionRetryScheduled,
    ExtractionStarted,
    RelationshipDiscovered,
)
from app.eventsourcing.events.inference import (
    InferenceCancelled,
    InferenceCompleted,
    InferenceFailed,
    InferenceRequested,
    InferenceStarted,
    ProviderCreated,
    ProviderDeleted,
    ProviderTestFailed,
    ProviderTestSucceeded,
    ProviderUpdated,
)
from app.eventsourcing.events.scraping import (
    EntitiesExtractedBatch,
    EntityExtracted,
    EntityRelationshipCreated,
    EntitySyncedToNeo4j,
    ExtractionFailed,
    Neo4jSyncFailed,
    PageScraped,
    PageScrapingFailed,
    RelationshipSyncedToNeo4j,
    ScrapingJobCancelled,
    ScrapingJobCompleted,
    ScrapingJobCreated,
    ScrapingJobFailed,
    ScrapingJobPaused,
    ScrapingJobProgressUpdated,
    ScrapingJobResumed,
    ScrapingJobStarted,
)

__all__ = [
    # Base event
    "TenantDomainEvent",
    # Scraping job events
    "ScrapingJobCreated",
    "ScrapingJobStarted",
    "ScrapingJobProgressUpdated",
    "ScrapingJobCompleted",
    "ScrapingJobFailed",
    "ScrapingJobCancelled",
    "ScrapingJobPaused",
    "ScrapingJobResumed",
    # Page events
    "PageScraped",
    "PageScrapingFailed",
    # Entity extraction events (scraping module)
    "EntityExtracted",
    "EntitiesExtractedBatch",
    "EntityRelationshipCreated",
    "ExtractionFailed",
    # Extraction pipeline events (extraction module)
    "ExtractionRequested",
    "ExtractionStarted",
    "ExtractionCompleted",
    "ExtractionProcessFailed",
    "ExtractionRetryScheduled",
    "RelationshipDiscovered",
    "ExtractionBatchStarted",
    "ExtractionBatchCompleted",
    # Neo4j sync events
    "EntitySyncedToNeo4j",
    "RelationshipSyncedToNeo4j",
    "Neo4jSyncFailed",
    # Inference provider events
    "ProviderCreated",
    "ProviderUpdated",
    "ProviderDeleted",
    "ProviderTestSucceeded",
    "ProviderTestFailed",
    # Inference request events
    "InferenceRequested",
    "InferenceStarted",
    "InferenceCompleted",
    "InferenceFailed",
    "InferenceCancelled",
]
