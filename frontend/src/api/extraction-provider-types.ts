/**
 * TypeScript interfaces for extraction provider API.
 *
 * These types match the backend Pydantic schemas in app/schemas/extraction_provider.py
 */

// =============================================================================
// Enums
// =============================================================================

/**
 * Extraction provider type enum matching backend ExtractionProviderType.
 */
export type ExtractionProviderType = 'ollama' | 'openai' | 'anthropic'

// =============================================================================
// Request/Response Interfaces
// =============================================================================

/**
 * Request schema for creating an extraction provider.
 */
export interface CreateExtractionProviderRequest {
  /** Provider display name (1-255 chars) */
  name: string
  /** Provider type */
  provider_type: ExtractionProviderType
  /** Provider configuration (api_key, base_url, etc.) */
  config: Record<string, unknown>
  /** Default model for extraction */
  default_model?: string
  /** Model for embeddings (entity matching) */
  embedding_model?: string
  /** Whether provider is active */
  is_active?: boolean
  /** Whether this is the default provider for the tenant */
  is_default?: boolean
  /** Rate limit (requests per minute) */
  rate_limit_rpm?: number
  /** Maximum context length */
  max_context_length?: number
  /** Request timeout in seconds */
  timeout_seconds?: number
}

/**
 * Request schema for updating an extraction provider.
 */
export interface UpdateExtractionProviderRequest {
  /** Provider display name */
  name?: string
  /** Provider configuration */
  config?: Record<string, unknown>
  /** Default model for extraction */
  default_model?: string
  /** Model for embeddings */
  embedding_model?: string
  /** Whether provider is active */
  is_active?: boolean
  /** Whether this is the default provider */
  is_default?: boolean
  /** Rate limit (requests per minute) */
  rate_limit_rpm?: number
  /** Maximum context length */
  max_context_length?: number
  /** Request timeout in seconds */
  timeout_seconds?: number
}

/**
 * Response schema for an extraction provider.
 */
export interface ExtractionProviderResponse {
  /** Provider ID */
  id: string
  /** Tenant ID */
  tenant_id: string
  /** Provider display name */
  name: string
  /** Provider type */
  provider_type: ExtractionProviderType
  /** Provider configuration (API key masked) */
  config: Record<string, unknown>
  /** Default model for extraction */
  default_model: string | null
  /** Model for embeddings */
  embedding_model: string | null
  /** Whether provider is active */
  is_active: boolean
  /** Whether this is the default provider */
  is_default: boolean
  /** Rate limit (requests per minute) */
  rate_limit_rpm: number
  /** Maximum context length */
  max_context_length: number
  /** Request timeout in seconds */
  timeout_seconds: number
  /** Creation timestamp */
  created_at: string
  /** Last update timestamp */
  updated_at: string
}

/**
 * Response from testing provider connection.
 */
export interface TestConnectionResponse {
  /** Whether connection succeeded */
  success: boolean
  /** Connection status message */
  message: string
  /** Provider name */
  provider: string
  /** Model availability (if applicable) */
  model_available?: boolean
  /** Error details (if failed) */
  error?: string
}

/**
 * Information about a provider type.
 */
export interface ProviderTypeInfo {
  /** Provider type value */
  type: ExtractionProviderType
  /** Human-readable name */
  name: string
  /** Description */
  description: string
  /** Required config fields */
  required_fields: string[]
  /** Optional config fields */
  optional_fields: string[]
}

// =============================================================================
// Utility Types and Constants
// =============================================================================

/**
 * Human-readable labels for provider types.
 */
export const PROVIDER_TYPE_LABELS: Record<ExtractionProviderType, string> = {
  ollama: 'Ollama (Local)',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
}

/**
 * Provider type descriptions.
 */
export const PROVIDER_TYPE_DESCRIPTIONS: Record<ExtractionProviderType, string> = {
  ollama: 'Local LLM inference using Ollama. No API key required.',
  openai: 'OpenAI GPT models with structured outputs. Requires API key.',
  anthropic: 'Anthropic Claude models. Requires API key. (Coming soon)',
}

/**
 * Default models for each provider type.
 */
export const DEFAULT_MODELS: Record<ExtractionProviderType, string> = {
  ollama: 'llama2',
  openai: 'gpt-4o',
  anthropic: 'claude-3-5-sonnet-20241022',
}

/**
 * Default embedding models for each provider type.
 */
export const DEFAULT_EMBEDDING_MODELS: Record<ExtractionProviderType, string> = {
  ollama: 'bge-m3',
  openai: 'text-embedding-3-small',
  anthropic: '',
}

/**
 * Required config fields for each provider type.
 */
export const REQUIRED_CONFIG_FIELDS: Record<ExtractionProviderType, string[]> = {
  ollama: [],
  openai: ['api_key'],
  anthropic: ['api_key'],
}

/**
 * Check if a provider type requires an API key.
 */
export function requiresApiKey(providerType: ExtractionProviderType): boolean {
  return REQUIRED_CONFIG_FIELDS[providerType].includes('api_key')
}

/**
 * Badge colors for provider types.
 */
export const PROVIDER_TYPE_COLORS: Record<
  ExtractionProviderType,
  { background: string; color: string }
> = {
  ollama: { background: '#dbeafe', color: '#1e40af' },
  openai: { background: '#d1fae5', color: '#065f46' },
  anthropic: { background: '#fce7f3', color: '#9d174d' },
}

/**
 * Status badge colors.
 */
export const STATUS_COLORS = {
  active: { background: '#d1fae5', color: '#065f46' },
  inactive: { background: '#fee2e2', color: '#991b1b' },
  default: { background: '#fef3c7', color: '#92400e' },
}
