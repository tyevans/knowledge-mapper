"""
Celery tasks for background processing.

This package contains task modules for:
- scraping: Web scraping job execution
- extraction: Entity extraction from scraped content
- graph: Neo4j knowledge graph synchronization
"""

from app.tasks.scraping import run_scraping_job, cleanup_stale_jobs
from app.tasks.extraction import extract_entities, extract_entities_batch
from app.tasks.graph import sync_entity_to_neo4j, sync_pending_entities

__all__ = [
    # Scraping tasks
    "run_scraping_job",
    "cleanup_stale_jobs",
    # Extraction tasks
    "extract_entities",
    "extract_entities_batch",
    # Graph tasks
    "sync_entity_to_neo4j",
    "sync_pending_entities",
]
