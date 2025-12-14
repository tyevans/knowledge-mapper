/**
 * OIDC Authentication Service
 *
 * Manages the OIDC flow using oidc-client-ts with Keycloak.
 * Uses PKCE for secure authorization code flow.
 */

import { UserManager, User, WebStorageStateStore } from 'oidc-client-ts'
import { OIDC_CONFIG } from './config'

export type AuthUser = User

class AuthService {
  private userManager: UserManager

  constructor() {
    this.userManager = new UserManager({
      ...OIDC_CONFIG,
      userStore: new WebStorageStateStore({ store: window.localStorage }),
    })

    // Handle silent renew errors
    this.userManager.events.addSilentRenewError((error) => {
      console.error('Silent renew error:', error)
    })

    // Handle user loaded (after login or silent renew)
    this.userManager.events.addUserLoaded((user) => {
      console.log('User loaded:', user.profile.email)
      this.notifyListeners()
    })

    // Handle user unloaded (logout)
    this.userManager.events.addUserUnloaded(() => {
      console.log('User unloaded')
      this.notifyListeners()
    })

    // Handle access token expiring
    this.userManager.events.addAccessTokenExpiring(() => {
      console.log('Access token expiring, attempting silent renew...')
    })

    // Handle access token expired
    this.userManager.events.addAccessTokenExpired(() => {
      console.log('Access token expired')
      this.notifyListeners()
    })
  }

  // Event listeners for auth state changes
  private listeners: Set<() => void> = new Set()

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private notifyListeners(): void {
    this.listeners.forEach((listener) => listener())
  }

  /**
   * Get the current authenticated user
   */
  async getUser(): Promise<User | null> {
    return this.userManager.getUser()
  }

  /**
   * Check if user is authenticated (has valid, non-expired token)
   */
  async isAuthenticated(): Promise<boolean> {
    const user = await this.getUser()
    return user !== null && !user.expired
  }

  /**
   * Get the access token for API calls
   */
  async getAccessToken(): Promise<string | null> {
    const user = await this.getUser()
    return user?.access_token ?? null
  }

  /**
   * Initiate login - redirects to Keycloak
   */
  async login(returnUrl?: string): Promise<void> {
    await this.userManager.signinRedirect({
      state: returnUrl || window.location.pathname,
    })
  }

  /**
   * Handle the callback after Keycloak redirects back
   */
  async handleCallback(): Promise<User> {
    const user = await this.userManager.signinRedirectCallback()
    this.notifyListeners()
    return user
  }

  /**
   * Logout - redirects to Keycloak logout
   */
  async logout(): Promise<void> {
    await this.userManager.signoutRedirect()
  }

  /**
   * Silent token renewal
   */
  async silentRenew(): Promise<User | null> {
    try {
      return await this.userManager.signinSilent()
    } catch (error) {
      console.error('Silent renew failed:', error)
      return null
    }
  }

  /**
   * Remove user from local storage (local logout without Keycloak redirect)
   */
  async removeUser(): Promise<void> {
    await this.userManager.removeUser()
    this.notifyListeners()
  }
}

// Singleton instance
export const authService = new AuthService()
