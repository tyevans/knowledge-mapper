/**
 * Auth Store - Reactive authentication state management
 *
 * Provides a reactive store for auth state with multi-tenant support.
 *
 * Token Flow:
 * 1. User authenticates via Keycloak -> Gets Keycloak token
 * 2. fetchUserTenants() called with Keycloak token
 * 3. If multiple tenants, user selects one via selectTenant()
 * 4. App token is stored and used for all subsequent API calls
 */

import { authService, type AuthUser } from './service'
import type {
  TenantMembership,
  AppToken,
  UserTenantsResponse,
  TokenExchangeResponse,
} from '../api/types'

// Storage keys
const STORAGE_KEYS = {
  APP_TOKEN: 'km_app_token',
  SELECTED_TENANT: 'km_selected_tenant',
  AVAILABLE_TENANTS: 'km_available_tenants',
} as const

export interface AuthState {
  // Keycloak auth state
  user: AuthUser | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  // Multi-tenant state
  availableTenants: TenantMembership[]
  selectedTenant: TenantMembership | null
  appToken: AppToken | null
  needsTenantSelection: boolean
}

type AuthStateListener = (state: AuthState) => void

class AuthStore {
  private state: AuthState = {
    user: null,
    isAuthenticated: false,
    isLoading: true,
    error: null,
    availableTenants: [],
    selectedTenant: null,
    appToken: null,
    needsTenantSelection: false,
  }

  private listeners: Set<AuthStateListener> = new Set()

  constructor() {
    // Subscribe to auth service events
    authService.subscribe(() => this.refreshState())

    // Load persisted tenant state from localStorage
    this.loadPersistedState()

    // Initialize state
    this.refreshState()
  }

  /**
   * Load persisted state from localStorage
   */
  private loadPersistedState(): void {
    try {
      const appTokenJson = localStorage.getItem(STORAGE_KEYS.APP_TOKEN)
      const selectedTenantJson = localStorage.getItem(STORAGE_KEYS.SELECTED_TENANT)
      const availableTenantsJson = localStorage.getItem(STORAGE_KEYS.AVAILABLE_TENANTS)

      if (appTokenJson) {
        const appToken = JSON.parse(appTokenJson) as AppToken
        // Check if token is expired
        if (appToken.expires_at > Date.now() / 1000) {
          this.state.appToken = appToken
        } else {
          // Clear expired token
          localStorage.removeItem(STORAGE_KEYS.APP_TOKEN)
        }
      }

      if (selectedTenantJson) {
        this.state.selectedTenant = JSON.parse(selectedTenantJson) as TenantMembership
      }

      if (availableTenantsJson) {
        this.state.availableTenants = JSON.parse(availableTenantsJson) as TenantMembership[]
      }
    } catch (error) {
      console.error('Failed to load persisted auth state:', error)
      this.clearPersistedState()
    }
  }

  /**
   * Clear all persisted state
   */
  private clearPersistedState(): void {
    localStorage.removeItem(STORAGE_KEYS.APP_TOKEN)
    localStorage.removeItem(STORAGE_KEYS.SELECTED_TENANT)
    localStorage.removeItem(STORAGE_KEYS.AVAILABLE_TENANTS)
  }

  /**
   * Persist app token to localStorage
   */
  private persistAppToken(token: AppToken): void {
    localStorage.setItem(STORAGE_KEYS.APP_TOKEN, JSON.stringify(token))
  }

  /**
   * Persist selected tenant to localStorage
   */
  private persistSelectedTenant(tenant: TenantMembership): void {
    localStorage.setItem(STORAGE_KEYS.SELECTED_TENANT, JSON.stringify(tenant))
  }

  /**
   * Persist available tenants to localStorage
   */
  private persistAvailableTenants(tenants: TenantMembership[]): void {
    localStorage.setItem(STORAGE_KEYS.AVAILABLE_TENANTS, JSON.stringify(tenants))
  }

  /**
   * Get current auth state
   */
  getState(): AuthState {
    return { ...this.state }
  }

  /**
   * Subscribe to state changes
   */
  subscribe(listener: AuthStateListener): () => void {
    this.listeners.add(listener)
    // Immediately notify with current state
    listener(this.getState())
    return () => this.listeners.delete(listener)
  }

  /**
   * Refresh state from auth service
   */
  async refreshState(): Promise<void> {
    try {
      const user = await authService.getUser()
      const isAuthenticated = user !== null && !user.expired

      // Determine if tenant selection is needed
      const needsTenantSelection =
        isAuthenticated &&
        !this.state.appToken &&
        this.state.availableTenants.length > 1

      this.state = {
        ...this.state,
        user,
        isAuthenticated,
        isLoading: false,
        error: null,
        needsTenantSelection,
      }
    } catch (error) {
      this.state = {
        ...this.state,
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      }
    }

    this.notifyListeners()
  }

  private notifyListeners(): void {
    const state = this.getState()
    this.listeners.forEach((listener) => listener(state))
  }

  /**
   * Login action
   */
  async login(returnUrl?: string): Promise<void> {
    this.state = { ...this.state, isLoading: true, error: null }
    this.notifyListeners()

    try {
      await authService.login(returnUrl)
    } catch (error) {
      this.state = {
        ...this.state,
        isLoading: false,
        error: error instanceof Error ? error.message : 'Login failed',
      }
      this.notifyListeners()
    }
  }

  /**
   * Handle OAuth callback
   */
  async handleCallback(): Promise<AuthUser | null> {
    this.state = { ...this.state, isLoading: true, error: null }
    this.notifyListeners()

    try {
      const user = await authService.handleCallback()
      this.state = {
        ...this.state,
        user,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      }
      this.notifyListeners()
      return user
    } catch (error) {
      this.state = {
        ...this.state,
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: error instanceof Error ? error.message : 'Callback failed',
      }
      this.notifyListeners()
      return null
    }
  }

  /**
   * Logout action - clears all auth state including tenant data
   */
  async logout(): Promise<void> {
    this.state = { ...this.state, isLoading: true, error: null }
    this.notifyListeners()

    // Clear persisted tenant state
    this.clearPersistedState()

    try {
      await authService.logout()
    } catch (error) {
      // Even if logout fails at Keycloak, clear local state
      await authService.removeUser()
      this.state = {
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
        availableTenants: [],
        selectedTenant: null,
        appToken: null,
        needsTenantSelection: false,
      }
      this.notifyListeners()
    }
  }

  // ==========================================================================
  // Multi-Tenant Methods
  // ==========================================================================

  /**
   * Fetch user's available tenants from the backend
   *
   * Call this after Keycloak authentication to determine which tenants
   * the user has access to.
   *
   * @returns UserTenantsResponse or null if failed
   */
  async fetchUserTenants(): Promise<UserTenantsResponse | null> {
    this.state = { ...this.state, isLoading: true, error: null }
    this.notifyListeners()

    try {
      // Get Keycloak token for the API call
      const keycloakToken = await authService.getAccessToken()
      if (!keycloakToken) {
        throw new Error('No Keycloak token available')
      }

      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/api/v1/auth/tenants`,
        {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${keycloakToken}`,
            'Content-Type': 'application/json',
          },
        }
      )

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(
          errorData.error_description || errorData.detail || `HTTP ${response.status}`
        )
      }

      const data = (await response.json()) as UserTenantsResponse

      // Update state with available tenants
      this.state = {
        ...this.state,
        availableTenants: data.tenants,
        isLoading: false,
        error: null,
        needsTenantSelection: data.tenants.length > 1,
      }

      // Persist available tenants
      this.persistAvailableTenants(data.tenants)

      this.notifyListeners()
      return data
    } catch (error) {
      this.state = {
        ...this.state,
        isLoading: false,
        error: error instanceof Error ? error.message : 'Failed to fetch tenants',
      }
      this.notifyListeners()
      return null
    }
  }

  /**
   * Select a tenant and exchange Keycloak token for app token
   *
   * @param tenantId - UUID of the tenant to select
   * @param requestedScopes - Optional specific scopes to request
   * @returns AppToken or null if failed
   */
  async selectTenant(
    tenantId: string,
    requestedScopes?: string[]
  ): Promise<AppToken | null> {
    this.state = { ...this.state, isLoading: true, error: null }
    this.notifyListeners()

    try {
      // Get Keycloak token for the API call
      const keycloakToken = await authService.getAccessToken()
      if (!keycloakToken) {
        throw new Error('No Keycloak token available')
      }

      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/api/v1/auth/select-tenant/${tenantId}`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${keycloakToken}`,
            'Content-Type': 'application/json',
          },
          body: requestedScopes
            ? JSON.stringify({ requested_scopes: requestedScopes })
            : undefined,
        }
      )

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(
          errorData.error_description || errorData.detail || `HTTP ${response.status}`
        )
      }

      const data = (await response.json()) as TokenExchangeResponse

      // Create AppToken with computed expiry
      const appToken: AppToken = {
        access_token: data.access_token,
        token_type: data.token_type,
        expires_in: data.expires_in,
        expires_at: Math.floor(Date.now() / 1000) + data.expires_in,
        tenant_id: data.tenant_id,
        tenant_slug: data.tenant_slug,
        scope: data.scope,
      }

      // Find the selected tenant in available tenants
      const selectedTenant = this.state.availableTenants.find(
        (t) => t.tenant_id === tenantId
      )

      if (!selectedTenant) {
        throw new Error('Selected tenant not found in available tenants')
      }

      // Update state
      this.state = {
        ...this.state,
        appToken,
        selectedTenant,
        isLoading: false,
        error: null,
        needsTenantSelection: false,
      }

      // Persist token and selection
      this.persistAppToken(appToken)
      this.persistSelectedTenant(selectedTenant)

      this.notifyListeners()
      return appToken
    } catch (error) {
      this.state = {
        ...this.state,
        isLoading: false,
        error: error instanceof Error ? error.message : 'Failed to select tenant',
      }
      this.notifyListeners()
      return null
    }
  }

  /**
   * Switch to a different tenant
   *
   * This clears the current app token and triggers a new tenant selection.
   * After switching, the page should be reloaded to clear any tenant-specific state.
   *
   * @param tenantId - UUID of the tenant to switch to
   * @param reload - Whether to reload the page after switching (default: true)
   */
  async switchTenant(tenantId: string, reload = true): Promise<AppToken | null> {
    // Clear current app token
    this.state = {
      ...this.state,
      appToken: null,
      selectedTenant: null,
    }
    localStorage.removeItem(STORAGE_KEYS.APP_TOKEN)
    localStorage.removeItem(STORAGE_KEYS.SELECTED_TENANT)

    // Select the new tenant
    const appToken = await this.selectTenant(tenantId)

    if (appToken && reload) {
      // Reload to clear any tenant-specific cached data
      window.location.reload()
    }

    return appToken
  }

  /**
   * Get the current app token for API calls
   *
   * Returns the app token if available and not expired.
   * If expired, returns null (caller should handle re-authentication).
   *
   * @returns Access token string or null
   */
  getAppToken(): string | null {
    const { appToken } = this.state

    if (!appToken) {
      return null
    }

    // Check if token is expired (with 60 second buffer)
    const now = Math.floor(Date.now() / 1000)
    if (appToken.expires_at <= now + 60) {
      console.warn('App token expired or expiring soon')
      return null
    }

    return appToken.access_token
  }

  /**
   * Check if user has a valid app token (has completed tenant selection)
   */
  hasValidAppToken(): boolean {
    return this.getAppToken() !== null
  }

  /**
   * Check if user needs to select a tenant
   */
  needsTenantSelectionCheck(): boolean {
    const { isAuthenticated, appToken, availableTenants } = this.state
    return isAuthenticated && !appToken && availableTenants.length > 1
  }

  /**
   * Get the currently selected tenant
   */
  getSelectedTenant(): TenantMembership | null {
    return this.state.selectedTenant
  }

  /**
   * Get all available tenants
   */
  getAvailableTenants(): TenantMembership[] {
    return this.state.availableTenants
  }

  /**
   * Clear tenant-specific state (but keep Keycloak auth)
   *
   * Use this when the app token expires or becomes invalid.
   */
  clearTenantState(): void {
    this.state = {
      ...this.state,
      appToken: null,
      selectedTenant: null,
      needsTenantSelection: this.state.availableTenants.length > 1,
    }
    localStorage.removeItem(STORAGE_KEYS.APP_TOKEN)
    localStorage.removeItem(STORAGE_KEYS.SELECTED_TENANT)
    this.notifyListeners()
  }
}

// Singleton instance
export const authStore = new AuthStore()
