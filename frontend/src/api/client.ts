import type { ApiResponse, ApiError } from './types'
import { authService } from '../auth'
import { authStore } from '../auth/store'

/**
 * API Client Configuration
 */
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/**
 * Custom error class for API errors
 */
export class ApiClientError extends Error {
  constructor(
    message: string,
    public status: number,
    public timestamp: string
  ) {
    super(message)
    this.name = 'ApiClientError'
  }
}

/**
 * Request options for API calls
 */
export interface RequestOptions {
  /**
   * Whether to include auth token (default: true)
   */
  authenticated?: boolean
  /**
   * Use Keycloak token instead of app token.
   * Use this for endpoints that work before tenant selection
   * (e.g., /auth/tenants, /auth/select-tenant).
   */
  useKeycloakToken?: boolean
}

/**
 * API Client for backend communication
 *
 * Token Strategy:
 * - By default, uses app token (after tenant selection)
 * - Falls back to Keycloak token if app token not available
 * - Use `useKeycloakToken: true` for endpoints that need Keycloak token
 *   (e.g., /auth/tenants before tenant selection)
 */
class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl
  }

  /**
   * Get the appropriate access token for API calls
   *
   * Priority:
   * 1. If useKeycloakToken is true, always use Keycloak token
   * 2. Otherwise, prefer app token (for tenant-isolated requests)
   * 3. Fall back to Keycloak token if app token not available
   */
  private async getAccessToken(useKeycloakToken: boolean = false): Promise<string | null> {
    if (useKeycloakToken) {
      return authService.getAccessToken()
    }

    // Prefer app token
    const appToken = authStore.getAppToken()
    if (appToken) {
      return appToken
    }

    // Fall back to Keycloak token
    return authService.getAccessToken()
  }

  /**
   * Get headers for requests, including auth token if available
   */
  private async getHeaders(options: RequestOptions = {}): Promise<HeadersInit> {
    const { authenticated = true, useKeycloakToken = false } = options

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }

    if (authenticated) {
      const token = await this.getAccessToken(useKeycloakToken)
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }
    }

    return headers
  }

  /**
   * Handle API response errors
   *
   * Detects tenant_required errors and clears tenant state to trigger re-selection.
   */
  private handleErrorResponse(response: Response, data: unknown): ApiError {
    const errorData = data as {
      error?: string
      error_description?: string
      detail?: string | { error?: string; error_description?: string }
      message?: string
    }

    let message = 'An error occurred'
    let errorCode: string | undefined

    // Extract error message from various formats
    if (typeof errorData.detail === 'object' && errorData.detail !== null) {
      message = errorData.detail.error_description || errorData.detail.error || message
      errorCode = errorData.detail.error
    } else if (typeof errorData.detail === 'string') {
      message = errorData.detail
    } else if (errorData.error_description) {
      message = errorData.error_description
      errorCode = errorData.error
    } else if (errorData.message) {
      message = errorData.message
    }

    // Handle tenant_required error - clear tenant state to trigger re-selection
    if (response.status === 403 && errorCode === 'tenant_required') {
      console.warn('Tenant selection required - clearing tenant state')
      authStore.clearTenantState()
    }

    // Handle expired/invalid token - might need to re-authenticate
    if (response.status === 401) {
      const currentAppToken = authStore.getAppToken()
      if (currentAppToken) {
        console.warn('App token rejected - clearing tenant state')
        authStore.clearTenantState()
      }
    }

    return {
      message,
      status: response.status,
      timestamp: new Date().toISOString(),
    }
  }

  /**
   * Make a GET request to the API
   * @param endpoint - API endpoint
   * @param options - Request options
   */
  async get<T>(endpoint: string, options: RequestOptions = {}): Promise<ApiResponse<T>> {
    try {
      const headers = await this.getHeaders(options)
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        method: 'GET',
        headers,
      })

      const data = await response.json()

      if (!response.ok) {
        const error = this.handleErrorResponse(response, data)
        return { success: false, error }
      }

      return { success: true, data }
    } catch (error) {
      const apiError: ApiError = {
        message: error instanceof Error ? error.message : 'Network error occurred',
        status: 0,
        timestamp: new Date().toISOString(),
      }
      return { success: false, error: apiError }
    }
  }

  /**
   * Make a POST request to the API
   * @param endpoint - API endpoint
   * @param body - Request body
   * @param options - Request options
   */
  async post<T, B = unknown>(
    endpoint: string,
    body?: B,
    options: RequestOptions = {}
  ): Promise<ApiResponse<T>> {
    try {
      const headers = await this.getHeaders(options)
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        method: 'POST',
        headers,
        body: body ? JSON.stringify(body) : undefined,
      })

      const data = await response.json()

      if (!response.ok) {
        const error = this.handleErrorResponse(response, data)
        return { success: false, error }
      }

      return { success: true, data }
    } catch (error) {
      const apiError: ApiError = {
        message: error instanceof Error ? error.message : 'Network error occurred',
        status: 0,
        timestamp: new Date().toISOString(),
      }
      return { success: false, error: apiError }
    }
  }

  /**
   * Make a PUT request to the API
   */
  async put<T, B = unknown>(
    endpoint: string,
    body?: B,
    options: RequestOptions = {}
  ): Promise<ApiResponse<T>> {
    try {
      const headers = await this.getHeaders(options)
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        method: 'PUT',
        headers,
        body: body ? JSON.stringify(body) : undefined,
      })

      const data = await response.json()

      if (!response.ok) {
        const error = this.handleErrorResponse(response, data)
        return { success: false, error }
      }

      return { success: true, data }
    } catch (error) {
      const apiError: ApiError = {
        message: error instanceof Error ? error.message : 'Network error occurred',
        status: 0,
        timestamp: new Date().toISOString(),
      }
      return { success: false, error: apiError }
    }
  }

  /**
   * Make a PATCH request to the API
   */
  async patch<T, B = unknown>(
    endpoint: string,
    body?: B,
    options: RequestOptions = {}
  ): Promise<ApiResponse<T>> {
    try {
      const headers = await this.getHeaders(options)
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        method: 'PATCH',
        headers,
        body: body ? JSON.stringify(body) : undefined,
      })

      const data = await response.json()

      if (!response.ok) {
        const error = this.handleErrorResponse(response, data)
        return { success: false, error }
      }

      return { success: true, data }
    } catch (error) {
      const apiError: ApiError = {
        message: error instanceof Error ? error.message : 'Network error occurred',
        status: 0,
        timestamp: new Date().toISOString(),
      }
      return { success: false, error: apiError }
    }
  }

  /**
   * Make a DELETE request to the API
   */
  async delete<T>(endpoint: string, options: RequestOptions = {}): Promise<ApiResponse<T>> {
    try {
      const headers = await this.getHeaders(options)
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        method: 'DELETE',
        headers,
      })

      // Handle 204 No Content
      if (response.status === 204) {
        return { success: true, data: undefined as T }
      }

      const data = await response.json()

      if (!response.ok) {
        const error = this.handleErrorResponse(response, data)
        return { success: false, error }
      }

      return { success: true, data }
    } catch (error) {
      const apiError: ApiError = {
        message: error instanceof Error ? error.message : 'Network error occurred',
        status: 0,
        timestamp: new Date().toISOString(),
      }
      return { success: false, error: apiError }
    }
  }

  /**
   * Get the base URL
   */
  getBaseUrl(): string {
    return this.baseUrl
  }
}

// Export singleton instance
export const apiClient = new ApiClient()
