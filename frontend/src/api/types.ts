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
