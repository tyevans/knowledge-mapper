/**
 * TypeScript interfaces for web scraping API.
 *
 * These types match the backend Pydantic schemas in app/schemas/scraping.py
 */

// =============================================================================
// Enums
// =============================================================================

/**
 * Job status enum matching backend JobStatus.
 */
export type JobStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled'

/**
 * Job stage enum matching backend JobStage.
 * Represents the current phase of the scraping pipeline.
 */
export type JobStage = 'crawling' | 'extracting' | 'consolidating' | 'done'

/**
 * Entity type enum matching backend EntityType.
 */
export type EntityType =
  | 'person'
  | 'organization'
  | 'location'
  | 'event'
  | 'product'
  | 'concept'
  | 'document'
  | 'date'
  | 'custom'

/**
 * Extraction method enum matching backend ExtractionMethod.
 */
export type ExtractionMethod =
  | 'schema_org'
  | 'open_graph'
  | 'llm_claude'
  | 'pattern'
  | 'spacy'
  | 'hybrid'

// =============================================================================
// Scraping Job Interfaces
// =============================================================================

/**
 * Request schema for creating a new scraping job.
 */
export interface CreateScrapingJobRequest {
  /** Human-readable job name (1-255 chars) */
  name: string
  /** URL to begin crawling from */
  start_url: string
  /** List of domains to stay within (empty = derived from start_url) */
  allowed_domains?: string[]
  /** Regex patterns for URLs to include */
  url_patterns?: string[]
  /** Regex patterns for URLs to exclude */
  excluded_patterns?: string[]
  /** Maximum link depth to follow (1-10, default: 2) */
  crawl_depth?: number
  /** Maximum number of pages to scrape (1-10000, default: 100) */
  max_pages?: number
  /** Requests per second limit (0.1-10.0, default: 1.0) */
  crawl_speed?: number
  /** Honor robots.txt rules (default: true) */
  respect_robots_txt?: boolean
  /** Use LLM for semantic entity extraction (default: true) */
  use_llm_extraction?: boolean
  /** Extraction provider ID (null = use tenant default or global) */
  extraction_provider_id?: string | null
  /** Additional Scrapy settings */
  custom_settings?: Record<string, unknown>
}

/**
 * Request schema for updating a scraping job (before it starts).
 */
export interface UpdateScrapingJobRequest {
  /** Human-readable job name */
  name?: string
  /** Maximum link depth to follow */
  crawl_depth?: number
  /** Maximum number of pages to scrape */
  max_pages?: number
  /** Requests per second limit */
  crawl_speed?: number
  /** Use LLM for semantic entity extraction */
  use_llm_extraction?: boolean
}

/**
 * Summary view of a scraping job (for list views).
 */
export interface ScrapingJobSummary {
  /** Job ID */
  id: string
  /** Job name */
  name: string
  /** Starting URL */
  start_url: string
  /** Current status */
  status: JobStatus
  /** Current pipeline stage */
  stage: JobStage | null
  /** Pages scraped so far */
  pages_crawled: number
  /** Entities found so far */
  entities_extracted: number
  /** Creation timestamp */
  created_at: string
}

/**
 * Full scraping job response.
 */
export interface ScrapingJobResponse {
  /** Job ID */
  id: string
  /** Tenant ID */
  tenant_id: string
  /** Creator user ID */
  created_by_user_id: string
  /** Job name */
  name: string
  /** Starting URL */
  start_url: string
  /** Allowed domains */
  allowed_domains: string[]
  /** URL include patterns */
  url_patterns: string[] | null
  /** URL exclude patterns */
  excluded_patterns: string[] | null
  /** Max crawl depth */
  crawl_depth: number
  /** Max pages to scrape */
  max_pages: number
  /** Requests per second */
  crawl_speed: number
  /** Honor robots.txt */
  respect_robots_txt: boolean
  /** Use LLM extraction */
  use_llm_extraction: boolean
  /** Extraction provider ID */
  extraction_provider_id: string | null
  /** Custom Scrapy settings */
  custom_settings: Record<string, unknown>
  /** Current status */
  status: JobStatus
  /** Current pipeline stage */
  stage: JobStage | null
  /** Celery task ID */
  celery_task_id: string | null
  /** Pages scraped */
  pages_crawled: number
  /** Entities extracted */
  entities_extracted: number
  /** Error count */
  errors_count: number
  /** Extraction progress (0.0-1.0) */
  extraction_progress: number
  /** Pages pending extraction */
  pages_pending_extraction: number
  /** Consolidation progress (0.0-1.0) */
  consolidation_progress: number
  /** Candidates found during consolidation */
  consolidation_candidates_found: number
  /** Auto-merged entities */
  consolidation_auto_merged: number
  /** Start time */
  started_at: string | null
  /** Completion time */
  completed_at: string | null
  /** Error message */
  error_message: string | null
  /** Creation timestamp */
  created_at: string
  /** Last update timestamp */
  updated_at: string
}

/**
 * Job status and progress response.
 */
export interface JobStatusResponse {
  /** Job ID */
  job_id: string
  /** Current status */
  status: JobStatus
  /** Current pipeline stage */
  stage: JobStage | null
  /** Pages scraped */
  pages_crawled: number
  /** Entities extracted */
  entities_extracted: number
  /** Error count */
  errors_count: number
  /** Crawl progress (0.0-1.0) */
  crawl_progress: number | null
  /** Extraction progress (0.0-1.0) */
  extraction_progress: number | null
  /** Consolidation progress (0.0-1.0) */
  consolidation_progress: number | null
  /** Candidates found during consolidation */
  consolidation_candidates_found: number
  /** Auto-merged entities */
  consolidation_auto_merged: number
  /** Start time */
  started_at: string | null
  /** Completion time */
  completed_at: string | null
  /** Error message if failed */
  error_message: string | null
  /** Estimated progress (0.0-1.0) */
  estimated_progress: number | null
}

// =============================================================================
// Scraped Page Interfaces
// =============================================================================

/**
 * Summary view of a scraped page.
 */
export interface ScrapedPageSummary {
  /** Page ID */
  id: string
  /** Page URL */
  url: string
  /** Page title */
  title: string | null
  /** HTTP status code */
  http_status: number
  /** Link depth */
  depth: number
  /** Extraction status */
  extraction_status: string
  /** Crawl timestamp */
  crawled_at: string
}

/**
 * Detailed view of a scraped page.
 */
export interface ScrapedPageDetail {
  /** Page ID */
  id: string
  /** Parent job ID */
  job_id: string
  /** Page URL */
  url: string
  /** Canonical URL */
  canonical_url: string | null
  /** Page title */
  title: string | null
  /** Meta description */
  meta_description: string | null
  /** Meta keywords */
  meta_keywords: string | null
  /** HTTP status code */
  http_status: number
  /** Content-Type */
  content_type: string
  /** Link depth */
  depth: number
  /** Crawl timestamp */
  crawled_at: string
  /** Extraction status */
  extraction_status: string
  /** Extraction timestamp */
  extracted_at: string | null
  /** Extraction error */
  extraction_error: string | null
  /** Number of Schema.org items found */
  schema_org_count: number
  /** Number of entities extracted */
  entity_count: number
  /** Creation timestamp */
  created_at: string
}

/**
 * Full content of a scraped page.
 */
export interface ScrapedPageContent {
  /** Page ID */
  id: string
  /** Page URL */
  url: string
  /** Raw HTML content */
  html_content: string
  /** Extracted text content */
  text_content: string
  /** Schema.org JSON-LD data */
  schema_org_data: unknown[]
  /** Open Graph metadata */
  open_graph_data: Record<string, unknown>
  /** HTTP response headers */
  response_headers: Record<string, string>
}

// =============================================================================
// Extracted Entity Interfaces
// =============================================================================

/**
 * Summary view of an extracted entity.
 */
export interface ExtractedEntitySummary {
  /** Entity ID */
  id: string
  /** Entity type */
  entity_type: EntityType
  /** Entity name */
  name: string
  /** Extraction method */
  extraction_method: ExtractionMethod
  /** Confidence score */
  confidence_score: number
  /** Creation timestamp */
  created_at: string
}

/**
 * Detailed view of an extracted entity.
 */
export interface ExtractedEntityDetail {
  /** Entity ID */
  id: string
  /** Tenant ID */
  tenant_id: string
  /** Source page ID */
  source_page_id: string
  /** Entity type */
  entity_type: EntityType
  /** Entity name */
  name: string
  /** Normalized name */
  normalized_name: string
  /** Entity description */
  description: string | null
  /** External identifiers */
  external_ids: Record<string, string>
  /** Entity properties */
  properties: Record<string, unknown>
  /** Extraction method */
  extraction_method: ExtractionMethod
  /** Confidence score */
  confidence_score: number
  /** Source text snippet */
  source_text: string | null
  /** Neo4j node ID */
  neo4j_node_id: string | null
  /** Neo4j sync status */
  synced_to_neo4j: boolean
  /** Neo4j sync timestamp */
  synced_at: string | null
  /** Creation timestamp */
  created_at: string
  /** Last update timestamp */
  updated_at: string
}

/**
 * Response for an entity relationship.
 */
export interface EntityRelationshipResponse {
  /** Relationship ID */
  id: string
  /** Source entity ID */
  source_entity_id: string
  /** Target entity ID */
  target_entity_id: string
  /** Relationship type */
  relationship_type: string
  /** Relationship properties */
  properties: Record<string, unknown>
  /** Confidence score */
  confidence_score: number
  /** Neo4j sync status */
  synced_to_neo4j: boolean
  /** Creation timestamp */
  created_at: string
  /** Source entity name (optional) */
  source_entity_name?: string
  /** Source entity type (optional) */
  source_entity_type?: EntityType
  /** Target entity name (optional) */
  target_entity_name?: string
  /** Target entity type (optional) */
  target_entity_type?: EntityType
}

// =============================================================================
// Paginated Response Interface
// =============================================================================

/**
 * Generic paginated response wrapper.
 */
export interface PaginatedResponse<T> {
  /** List of items */
  items: T[]
  /** Total number of items */
  total: number
  /** Current page (1-indexed) */
  page: number
  /** Items per page */
  page_size: number
  /** Total number of pages */
  pages: number
  /** Whether there's a next page */
  has_next: boolean
  /** Whether there's a previous page */
  has_prev: boolean
}

// =============================================================================
// Knowledge Graph Query Interfaces
// =============================================================================

/**
 * Request for querying the knowledge graph.
 */
export interface GraphQueryRequest {
  /** Central entity ID */
  entity_id: string
  /** Relationship depth to traverse (1-5, default: 2) */
  depth?: number
  /** Filter by relationship types */
  relationship_types?: string[]
  /** Filter by entity types */
  entity_types?: EntityType[]
  /** Maximum nodes to return (1-1000, default: 100) */
  limit?: number
}

/**
 * A node in the knowledge graph response.
 */
export interface GraphNode {
  /** Entity ID */
  id: string
  /** Entity type */
  entity_type: EntityType
  /** Entity name */
  name: string
  /** Entity properties */
  properties: Record<string, unknown>
}

/**
 * An edge in the knowledge graph response.
 */
export interface GraphEdge {
  /** Source entity ID */
  source: string
  /** Target entity ID */
  target: string
  /** Relationship type */
  relationship_type: string
  /** Confidence score */
  confidence: number
}

/**
 * Response from a knowledge graph query.
 */
export interface GraphQueryResponse {
  /** Graph nodes */
  nodes: GraphNode[]
  /** Graph edges */
  edges: GraphEdge[]
  /** Total nodes found */
  total_nodes: number
  /** Total edges found */
  total_edges: number
  /** Whether results were truncated */
  truncated: boolean
}

// =============================================================================
// Utility Types
// =============================================================================

/**
 * Color mapping for entity types (for UI).
 */
export const ENTITY_TYPE_COLORS: Record<EntityType, string> = {
  person: '#3b82f6', // blue
  organization: '#10b981', // green
  location: '#f59e0b', // amber
  event: '#8b5cf6', // purple
  product: '#ef4444', // red
  concept: '#6366f1', // indigo
  document: '#64748b', // slate
  date: '#14b8a6', // teal
  custom: '#6b7280', // gray
}

/**
 * Status badge colors for job status.
 */
export const JOB_STATUS_COLORS: Record<
  JobStatus,
  { background: string; color: string }
> = {
  pending: { background: '#e5e7eb', color: '#374151' },
  queued: { background: '#dbeafe', color: '#1e40af' },
  running: { background: '#fef3c7', color: '#92400e' },
  paused: { background: '#fce7f3', color: '#9d174d' },
  completed: { background: '#d1fae5', color: '#065f46' },
  failed: { background: '#fee2e2', color: '#991b1b' },
  cancelled: { background: '#f3f4f6', color: '#6b7280' },
}

/**
 * Human-readable labels for entity types.
 */
export const ENTITY_TYPE_LABELS: Record<EntityType, string> = {
  person: 'Person',
  organization: 'Organization',
  location: 'Location',
  event: 'Event',
  product: 'Product',
  concept: 'Concept',
  document: 'Document',
  date: 'Date',
  custom: 'Custom',
}

/**
 * Human-readable labels for job statuses.
 */
export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  pending: 'Pending',
  queued: 'Queued',
  running: 'Running',
  paused: 'Paused',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

/**
 * Human-readable labels for extraction methods.
 */
export const EXTRACTION_METHOD_LABELS: Record<ExtractionMethod, string> = {
  schema_org: 'Schema.org',
  open_graph: 'Open Graph',
  llm_claude: 'Claude LLM',
  pattern: 'Pattern Match',
  spacy: 'spaCy NLP',
  hybrid: 'Hybrid',
}

/**
 * Human-readable labels for job stages.
 */
export const JOB_STAGE_LABELS: Record<JobStage, string> = {
  crawling: 'Crawling',
  extracting: 'Extracting',
  consolidating: 'Consolidating',
  done: 'Done',
}

/**
 * Icons/emojis for job stages (for stepper UI).
 */
export const JOB_STAGE_ICONS: Record<JobStage, string> = {
  crawling: '🕷️',
  extracting: '🔍',
  consolidating: '🔗',
  done: '✓',
}

/**
 * Stage badge colors for job stage.
 */
export const JOB_STAGE_COLORS: Record<
  JobStage,
  { background: string; color: string; border: string }
> = {
  crawling: { background: '#dbeafe', color: '#1e40af', border: '#93c5fd' },
  extracting: { background: '#fef3c7', color: '#92400e', border: '#fcd34d' },
  consolidating: { background: '#e0e7ff', color: '#4338ca', border: '#a5b4fc' },
  done: { background: '#d1fae5', color: '#065f46', border: '#6ee7b7' },
}

/**
 * Order of job stages for stepper UI.
 */
export const JOB_STAGE_ORDER: JobStage[] = [
  'crawling',
  'extracting',
  'consolidating',
  'done',
]
