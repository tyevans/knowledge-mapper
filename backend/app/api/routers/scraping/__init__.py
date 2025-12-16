"""
Scraping routers package.

This package contains focused routers for scraping functionality,
following the Single Responsibility Principle:

- jobs.py: Job CRUD operations (create, list, get, update, delete)
- job_control.py: Job execution control (start, stop, pause, status)
- pages.py: Scraped pages retrieval
- job_entities.py: Entity operations (job-scoped and global)
- graph_query.py: Knowledge graph queries

Each router handles a single cohesive set of responsibilities.
"""

from fastapi import APIRouter

from app.api.routers.scraping.graph_query import router as graph_query_router
from app.api.routers.scraping.job_control import router as job_control_router
from app.api.routers.scraping.job_entities import router as job_entities_router
from app.api.routers.scraping.jobs import router as jobs_router
from app.api.routers.scraping.pages import router as pages_router

# Combined router with /scraping prefix
router = APIRouter(prefix="/scraping", tags=["scraping"])

# Include all sub-routers
router.include_router(jobs_router)
router.include_router(job_control_router)
router.include_router(pages_router)
router.include_router(job_entities_router)
router.include_router(graph_query_router)

__all__ = ["router"]
