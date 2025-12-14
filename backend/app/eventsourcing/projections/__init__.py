"""Projection base classes and handlers for read models."""

from app.eventsourcing.projections.base import TenantAwareProjection
from app.eventsourcing.projections.extraction import (
    EntityProjectionHandler,
    ExtractionProcessProjectionHandler,
    RelationshipProjectionHandler,
    map_entity_type,
    map_extraction_method,
)
from app.eventsourcing.projections.extraction_trigger import ExtractionTriggerHandler
from app.eventsourcing.projections.neo4j_sync import (
    Neo4jEntitySyncHandler,
    Neo4jRelationshipSyncHandler,
)

__all__ = [
    # Base classes
    "TenantAwareProjection",
    # Extraction projections
    "EntityProjectionHandler",
    "ExtractionProcessProjectionHandler",
    "ExtractionTriggerHandler",
    "RelationshipProjectionHandler",
    # Neo4j sync projections
    "Neo4jEntitySyncHandler",
    "Neo4jRelationshipSyncHandler",
    # Utilities
    "map_entity_type",
    "map_extraction_method",
]
