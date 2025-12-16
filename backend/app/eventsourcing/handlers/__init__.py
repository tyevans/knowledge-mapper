"""
Event handlers for domain events.

This module provides handlers that react to domain events
to perform side effects like syncing to external systems.
"""

from app.eventsourcing.handlers.consolidation_neo4j import ConsolidationNeo4jSyncHandler

__all__ = [
    "ConsolidationNeo4jSyncHandler",
]
