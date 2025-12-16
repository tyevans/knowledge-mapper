/**
 * API Response Types
 */

export interface HealthResponse {
  status: string
  timestamp: string
  version?: string
}

export interface ApiError {
  message: string
  status: number
  timestamp: string
}

export type ApiResponse<T> = {
  success: true
  data: T
} | {
  success: false
  error: ApiError
}

/**
 * Todo Types
 */
export interface PublicTodo {
  id: string
  title: string
  description: string | null
  completed: boolean
  created_at: string
}

export interface UserTodo extends PublicTodo {
  user_id: string
  tenant_id: string
  updated_at: string
}

export interface CreateTodoRequest {
  title: string
  description?: string
  completed?: boolean
}

export interface UpdateTodoRequest {
  title?: string
  description?: string
  completed?: boolean
}

/**
 * Auth Types
 */
export interface ProtectedResponse {
  message: string
  user_id: string
  tenant_id: string
  email: string | null
}

/**
 * Tenant Types
 */
export interface TenantStoreMapping {
  tenant_id: string
  store_id: string
  migration_state: string
  target_store_id?: string | null
  active_migration_id?: string | null
}

export interface TenantInfo {
  id: string
  slug: string
  name: string
  is_active: boolean
  created_at: string
  updated_at: string
  settings: Record<string, unknown>
}

export interface TenantWithStoreMapping extends TenantInfo {
  store_mapping?: TenantStoreMapping | null
  user_count: number
  event_count: number
}

export interface TenantListResponse {
  items: TenantWithStoreMapping[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface TenantCreate {
  slug: string
  name: string
  settings?: Record<string, unknown>
  is_active?: boolean
}

/**
 * Multi-Tenant User Types
 *
 * Types for the multi-tenant user flow where a user can belong to multiple tenants
 * and must select one after authentication to receive a tenant-scoped app token.
 */

/** Role a user has within a tenant */
export type MembershipRole = 'owner' | 'admin' | 'member'

/** A user's membership in a specific tenant */
export interface TenantMembership {
  tenant_id: string
  tenant_slug: string
  tenant_name: string
  role: MembershipRole
  is_default: boolean
}

/** Response from GET /auth/tenants */
export interface UserTenantsResponse {
  user_id: string
  email: string | null
  tenants: TenantMembership[]
}

/** Request body for POST /auth/select-tenant */
export interface TokenExchangeRequest {
  requested_scopes?: string[]
}

/** Response from POST /auth/select-tenant */
export interface TokenExchangeResponse {
  access_token: string
  token_type: 'Bearer'
  expires_in: number
  scope: string
  tenant_id: string
  tenant_slug: string
}

/**
 * App Token
 *
 * Represents a backend-issued JWT token with tenant context.
 * This token is used for all API calls after tenant selection.
 */
export interface AppToken {
  access_token: string
  token_type: 'Bearer'
  expires_in: number
  /** Unix timestamp when token expires */
  expires_at: number
  tenant_id: string
  tenant_slug: string
  /** Space-separated scopes */
  scope: string
}

/**
 * Audit Types
 */

/** Single audit event from the event store */
export interface AuditEvent {
  event_id: string
  event_type: string
  aggregate_type: string
  aggregate_id: string
  global_position: number
  stream_position: number
  occurred_at: string
  stored_at: string
  actor_id: string | null
  summary: string
}

/** Response from GET /audit/events */
export interface AuditLogResponse {
  events: AuditEvent[]
  total_position: number
  has_more: boolean
}

/** Response from GET /audit/stats */
export interface AuditStatsResponse {
  total_events: number
  event_type_counts: Record<string, number>
  aggregate_type_counts: Record<string, number>
}

/**
 * Consolidation Types
 *
 * Types for the entity consolidation feature, including merge candidates,
 * review queue, merge history, and configuration.
 */

/** Possible decisions for merge candidates */
export type MergeDecision = 'auto_merge' | 'review' | 'reject'

/** Human reviewer decisions for merge candidates */
export type ReviewDecision = 'approve' | 'reject' | 'defer'

/** Status values for merge review items */
export type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'deferred' | 'expired'

/** Types of merge-related events in history */
export type MergeEventType = 'entities_merged' | 'merge_undone' | 'entity_split'

/** Summary information about an entity for display purposes */
export interface EntitySummary {
  id: string
  name: string
  normalized_name: string | null
  entity_type: string
  description: string | null
  is_canonical: boolean
}

/** Breakdown of similarity scores for transparency */
export interface SimilarityBreakdown {
  jaro_winkler: number | null
  levenshtein: number | null
  trigram: number | null
  soundex_match: boolean | null
  metaphone_match: boolean | null
  embedding_cosine: number | null
  graph_neighborhood: number | null
  type_match: boolean | null
  same_page: boolean | null
}

/** Response model for a single merge candidate pair */
export interface MergeCandidate {
  entity_a: EntitySummary
  entity_b: EntitySummary
  combined_score: number
  confidence: number
  decision: MergeDecision
  similarity_breakdown: SimilarityBreakdown
  blocking_keys: string[]
  review_item_id: string | null
  computed_at: string
}

/** Paginated list of merge candidates */
export interface MergeCandidateListResponse {
  items: MergeCandidate[]
  total: number
  page: number
  page_size: number
  pages: number
  has_next: boolean
  has_prev: boolean
}

/** Request to compute merge candidates */
export interface ComputeCandidatesRequest {
  entity_ids?: string[]
  min_confidence?: number
  include_embedding?: boolean
  include_graph?: boolean
  max_candidates_per_entity?: number
}

/** Response from candidate computation */
export interface ComputeCandidatesResponse {
  job_id: string
  status: string
  entities_processed: number
  candidates_found: number
  message: string | null
}

/** Request to execute a merge operation */
export interface MergeRequest {
  canonical_entity_id: string
  merged_entity_ids: string[]
  merge_reason?: string
  similarity_scores?: Record<string, number>
}

/** Response from a merge operation */
export interface MergeResponse {
  success: boolean
  canonical_entity_id: string
  merged_entity_ids: string[]
  aliases_created: number
  relationships_transferred: number
  merge_history_id: string
  event_id: string
  message: string | null
}

/** Request to undo a previous merge operation */
export interface UndoMergeRequest {
  reason: string
  restore_entity_ids?: string[]
}

/** Response from an undo merge operation */
export interface UndoMergeResponse {
  success: boolean
  original_merge_event_id: string
  restored_entity_ids: string[]
  aliases_removed: number
  relationships_restored: number
  undo_history_id: string
  message: string | null
}

/** Split definition for creating new entities */
export interface SplitDefinition {
  name: string
  entity_type?: string
  description?: string
}

/** Request to split an entity into multiple new entities */
export interface SplitEntityRequest {
  split_definitions: SplitDefinition[]
  relationship_assignments?: Record<string, number>
  alias_assignments?: Record<string, number>
  reason: string
}

/** Response from an entity split operation */
export interface SplitEntityResponse {
  success: boolean
  original_entity_id: string
  new_entity_ids: string[]
  relationships_redistributed: number
  aliases_redistributed: number
  split_history_id: string
  message: string | null
}

/** Response model for a review queue item */
export interface ReviewQueueItem {
  id: string
  entity_a: EntitySummary
  entity_b: EntitySummary
  confidence: number
  review_priority: number
  similarity_scores: Record<string, number | boolean | null>
  status: ReviewStatus
  reviewed_by_name: string | null
  reviewed_at: string | null
  reviewer_notes: string | null
  created_at: string
}

/** Paginated list of review queue items */
export interface ReviewQueueListResponse {
  items: ReviewQueueItem[]
  total: number
  page: number
  page_size: number
  pages: number
  has_next: boolean
  has_prev: boolean
}

/** Request to submit a review decision */
export interface ReviewDecisionRequest {
  decision: ReviewDecision
  notes?: string
  select_canonical?: string
}

/** Response from submitting a review decision */
export interface ReviewDecisionResponse {
  success: boolean
  review_item_id: string
  decision: ReviewDecision
  merge_executed: boolean
  merge_result: MergeResponse | null
  message: string | null
}

/** Statistics about the review queue */
export interface ReviewQueueStats {
  total_pending: number
  total_approved: number
  total_rejected: number
  total_deferred: number
  total_expired: number
  avg_confidence: number
  oldest_pending_age_hours: number | null
  by_entity_type: Record<string, number>
}

/** Response model for a merge history item */
export interface MergeHistoryItem {
  id: string
  event_id: string
  event_type: MergeEventType
  canonical_entity: EntitySummary | null
  affected_entity_ids: string[]
  merge_reason: string | null
  similarity_scores: Record<string, number | boolean | null> | null
  performed_by_name: string | null
  performed_at: string
  undone: boolean
  undone_at: string | null
  undone_by_name: string | null
  undo_reason: string | null
  can_undo: boolean
}

/** Paginated list of merge history items */
export interface MergeHistoryListResponse {
  items: MergeHistoryItem[]
  total: number
  page: number
  page_size: number
  pages: number
  has_next: boolean
  has_prev: boolean
}

/** Feature weight configuration */
export interface FeatureWeightConfig {
  jaro_winkler: number
  normalized_exact: number
  type_match: number
  same_page_bonus: number
  embedding_cosine: number
  graph_neighborhood: number
}

/** Tenant consolidation configuration */
export interface ConsolidationConfig {
  tenant_id: string
  auto_merge_threshold: number
  review_threshold: number
  max_block_size: number
  enable_embedding_similarity: boolean
  enable_graph_similarity: boolean
  enable_auto_consolidation: boolean
  embedding_model: string
  feature_weights: FeatureWeightConfig
  created_at: string
  updated_at: string | null
}

/** Request to update consolidation configuration */
export interface ConsolidationConfigUpdate {
  auto_merge_threshold?: number
  review_threshold?: number
  max_block_size?: number
  enable_embedding_similarity?: boolean
  enable_graph_similarity?: boolean
  enable_auto_consolidation?: boolean
  embedding_model?: string
  feature_weights?: Partial<FeatureWeightConfig>
}

/** Request to run batch consolidation */
export interface BatchConsolidationRequest {
  entity_type?: string
  min_confidence?: number
  dry_run?: boolean
  max_merges?: number
}

/** Response from batch consolidation */
export interface BatchConsolidationResponse {
  job_id: string
  status: string
  dry_run: boolean
  merges_executed: number
  merges_skipped: number
  errors: string[]
  message: string | null
}
