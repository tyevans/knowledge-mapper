"""
Pydantic schemas for web scraping API.

This module provides Pydantic models for scraping job management,
including request validation and response serialization.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from app.models.scraping_job import JobStatus, JobStage
from app.models.extracted_entity import ExtractionMethod

# Note: EntityType enum is no longer used in schemas since entity_type is now
# stored as a string to support dynamic domain-specific types.


# =============================================================================
# Scraping Job Schemas
# =============================================================================


class CreateScrapingJobRequest(BaseModel):
    """Request schema for creating a new scraping job."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable job name",
    )
    start_url: HttpUrl = Field(
        ...,
        description="URL to begin crawling from",
    )
    allowed_domains: list[str] = Field(
        default_factory=list,
        description="List of domains to stay within (empty = derived from start_url)",
    )
    url_patterns: Optional[list[str]] = Field(
        None,
        description="Regex patterns for URLs to include",
    )
    excluded_patterns: Optional[list[str]] = Field(
        None,
        description="Regex patterns for URLs to exclude",
    )
    crawl_depth: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Maximum link depth to follow",
    )
    max_pages: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Maximum number of pages to scrape",
    )
    crawl_speed: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Requests per second limit",
    )
    respect_robots_txt: bool = Field(
        default=True,
        description="Honor robots.txt rules",
    )
    use_llm_extraction: bool = Field(
        default=True,
        description="Use LLM for semantic entity extraction",
    )
    extraction_provider_id: Optional[UUID] = Field(
        None,
        description="Extraction provider to use (null = use tenant default or global)",
    )
    custom_settings: dict = Field(
        default_factory=dict,
        description="Additional Scrapy settings",
    )


class UpdateScrapingJobRequest(BaseModel):
    """Request schema for updating a scraping job (before it starts)."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Human-readable job name",
    )
    crawl_depth: Optional[int] = Field(
        None,
        ge=1,
        le=10,
        description="Maximum link depth to follow",
    )
    max_pages: Optional[int] = Field(
        None,
        ge=1,
        le=10000,
        description="Maximum number of pages to scrape",
    )
    crawl_speed: Optional[float] = Field(
        None,
        ge=0.1,
        le=10.0,
        description="Requests per second limit",
    )
    use_llm_extraction: Optional[bool] = Field(
        None,
        description="Use LLM for semantic entity extraction",
    )


class ScrapingJobSummary(BaseModel):
    """Summary view of a scraping job."""

    id: UUID = Field(..., description="Job ID")
    name: str = Field(..., description="Job name")
    start_url: str = Field(..., description="Starting URL")
    status: JobStatus = Field(..., description="Current status")
    stage: JobStage | None = Field(None, description="Current pipeline stage")
    pages_crawled: int = Field(..., description="Pages scraped so far")
    entities_extracted: int = Field(..., description="Entities found so far")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        from_attributes = True


class ScrapingJobResponse(BaseModel):
    """Full scraping job response."""

    id: UUID = Field(..., description="Job ID")
    tenant_id: UUID = Field(..., description="Tenant ID")
    created_by_user_id: str = Field(..., description="Creator user ID")
    name: str = Field(..., description="Job name")
    start_url: str = Field(..., description="Starting URL")
    allowed_domains: list[str] = Field(..., description="Allowed domains")
    url_patterns: Optional[list[str]] = Field(None, description="URL include patterns")
    excluded_patterns: Optional[list[str]] = Field(None, description="URL exclude patterns")
    crawl_depth: int = Field(..., description="Max crawl depth")
    max_pages: int = Field(..., description="Max pages to scrape")
    crawl_speed: float = Field(..., description="Requests per second")
    respect_robots_txt: bool = Field(..., description="Honor robots.txt")
    use_llm_extraction: bool = Field(..., description="Use LLM extraction")
    extraction_provider_id: Optional[UUID] = Field(None, description="Extraction provider ID")
    custom_settings: dict = Field(..., description="Custom Scrapy settings")
    status: JobStatus = Field(..., description="Current status")
    stage: JobStage | None = Field(None, description="Current pipeline stage")
    celery_task_id: Optional[str] = Field(None, description="Celery task ID")
    consolidation_task_id: Optional[str] = Field(None, description="Consolidation task ID")
    pages_crawled: int = Field(..., description="Pages scraped")
    entities_extracted: int = Field(..., description="Entities extracted")
    errors_count: int = Field(..., description="Error count")
    extraction_progress: float = Field(0.0, description="Extraction progress (0.0-1.0)")
    consolidation_progress: float = Field(0.0, description="Consolidation progress (0.0-1.0)")
    pages_pending_extraction: int = Field(0, description="Pages pending extraction")
    consolidation_candidates_found: int = Field(0, description="Merge candidates found")
    consolidation_auto_merged: int = Field(0, description="Auto-merged entity pairs")
    started_at: Optional[datetime] = Field(None, description="Start time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")
    error_message: Optional[str] = Field(None, description="Error message")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


class JobStatusResponse(BaseModel):
    """Job status and progress response."""

    job_id: UUID = Field(..., description="Job ID")
    status: JobStatus = Field(..., description="Current status")
    stage: JobStage | None = Field(None, description="Current pipeline stage")
    pages_crawled: int = Field(..., description="Pages scraped")
    entities_extracted: int = Field(..., description="Entities extracted")
    errors_count: int = Field(..., description="Error count")
    started_at: Optional[datetime] = Field(None, description="Start time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    estimated_progress: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Estimated overall progress (0.0-1.0)",
    )
    # Stage-specific progress
    crawl_progress: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Crawling progress (0.0-1.0)",
    )
    extraction_progress: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Extraction progress (0.0-1.0)",
    )
    consolidation_progress: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Consolidation progress (0.0-1.0)",
    )
    # Consolidation metrics
    consolidation_candidates_found: int = Field(0, description="Merge candidates found")
    consolidation_auto_merged: int = Field(0, description="Auto-merged entity pairs")
    pages_pending_extraction: int = Field(0, description="Pages pending extraction")


# =============================================================================
# Scraped Page Schemas
# =============================================================================


class ScrapedPageSummary(BaseModel):
    """Summary view of a scraped page."""

    id: UUID = Field(..., description="Page ID")
    url: str = Field(..., description="Page URL")
    title: Optional[str] = Field(None, description="Page title")
    http_status: int = Field(..., description="HTTP status code")
    depth: int = Field(..., description="Link depth")
    extraction_status: str = Field(..., description="Extraction status")
    crawled_at: datetime = Field(..., description="Crawl timestamp")

    class Config:
        from_attributes = True


class ScrapedPageDetail(BaseModel):
    """Detailed view of a scraped page."""

    id: UUID = Field(..., description="Page ID")
    job_id: UUID = Field(..., description="Parent job ID")
    url: str = Field(..., description="Page URL")
    canonical_url: Optional[str] = Field(None, description="Canonical URL")
    title: Optional[str] = Field(None, description="Page title")
    meta_description: Optional[str] = Field(None, description="Meta description")
    meta_keywords: Optional[str] = Field(None, description="Meta keywords")
    http_status: int = Field(..., description="HTTP status code")
    content_type: str = Field(..., description="Content-Type")
    depth: int = Field(..., description="Link depth")
    crawled_at: datetime = Field(..., description="Crawl timestamp")
    extraction_status: str = Field(..., description="Extraction status")
    extracted_at: Optional[datetime] = Field(None, description="Extraction timestamp")
    extraction_error: Optional[str] = Field(None, description="Extraction error")
    schema_org_count: int = Field(
        default=0,
        description="Number of Schema.org items found",
    )
    entity_count: int = Field(
        default=0,
        description="Number of entities extracted",
    )
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        from_attributes = True


class ScrapedPageContent(BaseModel):
    """Full content of a scraped page."""

    id: UUID = Field(..., description="Page ID")
    url: str = Field(..., description="Page URL")
    html_content: str = Field(..., description="Raw HTML content")
    text_content: str = Field(..., description="Extracted text content")
    schema_org_data: list = Field(..., description="Schema.org JSON-LD data")
    open_graph_data: dict = Field(..., description="Open Graph metadata")
    response_headers: dict = Field(..., description="HTTP response headers")

    class Config:
        from_attributes = True


# =============================================================================
# Extracted Entity Schemas
# =============================================================================


class ExtractedEntitySummary(BaseModel):
    """Summary view of an extracted entity."""

    id: UUID = Field(..., description="Entity ID")
    entity_type: str = Field(..., description="Entity type (e.g., 'person', 'organization', 'character')")
    name: str = Field(..., description="Entity name")
    extraction_method: ExtractionMethod = Field(..., description="Extraction method")
    confidence_score: float = Field(..., description="Confidence score")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        from_attributes = True


class ExtractedEntityDetail(BaseModel):
    """Detailed view of an extracted entity."""

    id: UUID = Field(..., description="Entity ID")
    tenant_id: UUID = Field(..., description="Tenant ID")
    source_page_id: UUID = Field(..., description="Source page ID")
    entity_type: str = Field(..., description="Entity type (e.g., 'person', 'organization', 'character')")
    original_entity_type: Optional[str] = Field(None, description="Original entity type from LLM before normalization")
    name: str = Field(..., description="Entity name")
    normalized_name: str = Field(..., description="Normalized name")
    description: Optional[str] = Field(None, description="Entity description")
    external_ids: dict = Field(..., description="External identifiers")
    properties: dict = Field(..., description="Entity properties")
    extraction_method: ExtractionMethod = Field(..., description="Extraction method")
    confidence_score: float = Field(..., description="Confidence score")
    source_text: Optional[str] = Field(None, description="Source text snippet")
    neo4j_node_id: Optional[str] = Field(None, description="Neo4j node ID")
    synced_to_neo4j: bool = Field(..., description="Neo4j sync status")
    synced_at: Optional[datetime] = Field(None, description="Neo4j sync timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


class EntityRelationshipResponse(BaseModel):
    """Response for an entity relationship."""

    id: UUID = Field(..., description="Relationship ID")
    source_entity_id: UUID = Field(..., description="Source entity ID")
    target_entity_id: UUID = Field(..., description="Target entity ID")
    relationship_type: str = Field(..., description="Relationship type")
    properties: dict = Field(..., description="Relationship properties")
    confidence_score: float = Field(..., description="Confidence score")
    synced_to_neo4j: bool = Field(..., description="Neo4j sync status")
    created_at: datetime = Field(..., description="Creation timestamp")

    # Expanded entity info (optional)
    source_entity_name: Optional[str] = Field(None, description="Source entity name")
    source_entity_type: Optional[str] = Field(None, description="Source entity type")
    target_entity_name: Optional[str] = Field(None, description="Target entity name")
    target_entity_type: Optional[str] = Field(None, description="Target entity type")

    class Config:
        from_attributes = True


# =============================================================================
# Paginated Response Schema
# =============================================================================


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper."""

    items: list = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page (1-indexed)")
    page_size: int = Field(..., description="Items per page")
    pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there's a next page")
    has_prev: bool = Field(..., description="Whether there's a previous page")


# =============================================================================
# Knowledge Graph Query Schemas
# =============================================================================


class GraphQueryRequest(BaseModel):
    """Request for querying the knowledge graph."""

    entity_id: UUID = Field(..., description="Central entity ID")
    depth: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Relationship depth to traverse",
    )
    relationship_types: Optional[list[str]] = Field(
        None,
        description="Filter by relationship types",
    )
    entity_types: Optional[list[str]] = Field(
        None,
        description="Filter by entity types (e.g., ['person', 'organization', 'character'])",
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum nodes to return",
    )


class GraphNode(BaseModel):
    """A node in the knowledge graph response."""

    id: UUID = Field(..., description="Entity ID")
    entity_type: str = Field(..., description="Entity type (e.g., 'person', 'organization', 'character')")
    name: str = Field(..., description="Entity name")
    properties: dict = Field(default_factory=dict, description="Entity properties")


class GraphEdge(BaseModel):
    """An edge in the knowledge graph response."""

    source: UUID = Field(..., description="Source entity ID")
    target: UUID = Field(..., description="Target entity ID")
    relationship_type: str = Field(..., description="Relationship type")
    confidence: float = Field(..., description="Confidence score")


class GraphQueryResponse(BaseModel):
    """Response from a knowledge graph query."""

    nodes: list[GraphNode] = Field(..., description="Graph nodes")
    edges: list[GraphEdge] = Field(..., description="Graph edges")
    total_nodes: int = Field(..., description="Total nodes found")
    total_edges: int = Field(..., description="Total edges found")
    truncated: bool = Field(
        default=False,
        description="Whether results were truncated",
    )
