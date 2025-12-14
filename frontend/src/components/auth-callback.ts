import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { authStore } from '../auth'

/**
 * Auth Callback Handler Component
 *
 * Handles the OAuth callback after Keycloak redirects back.
 * After successful Keycloak auth, fetches user tenants and:
 * - If 0 tenants: Shows error (user not in any tenant)
 * - If 1 tenant: Auto-selects tenant and redirects to app
 * - If >1 tenants: Redirects to tenant selection page
 */
@customElement('auth-callback')
export class AuthCallback extends LitElement {
  static styles = css`
    :host {
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      background: #f3f4f6;
    }

    .container {
      background: white;
      padding: 2rem;
      border-radius: 0.5rem;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
      text-align: center;
      max-width: 400px;
    }

    .loading {
      display: inline-block;
      width: 3rem;
      height: 3rem;
      border: 3px solid #e5e7eb;
      border-top-color: #1f2937;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin-bottom: 1rem;
    }

    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }

    h2 {
      color: #374151;
      margin: 0 0 0.5rem 0;
      font-size: 1.25rem;
    }

    p {
      color: #6b7280;
      margin: 0;
      font-size: 0.875rem;
    }

    .status-text {
      margin-top: 0.5rem;
      font-size: 0.8rem;
      color: #9ca3af;
    }

    .error {
      color: #dc2626;
      background: #fef2f2;
      padding: 1rem;
      border-radius: 0.375rem;
      margin-top: 1rem;
    }

    .error-title {
      font-weight: 600;
      margin-bottom: 0.5rem;
    }

    .retry-btn {
      margin-top: 1rem;
      padding: 0.5rem 1rem;
      background: #1f2937;
      color: white;
      border: none;
      border-radius: 0.375rem;
      cursor: pointer;
      font-size: 0.875rem;
    }

    .retry-btn:hover {
      background: #374151;
    }

    .logout-btn {
      margin-top: 0.5rem;
      padding: 0.5rem 1rem;
      background: #ef4444;
      color: white;
      border: none;
      border-radius: 0.375rem;
      cursor: pointer;
      font-size: 0.875rem;
    }

    .logout-btn:hover {
      background: #dc2626;
    }
  `

  @state()
  private status: 'processing' | 'fetching-tenants' | 'selecting-tenant' | 'done' | 'error' = 'processing'

  @state()
  private statusMessage = 'Processing authentication...'

  @state()
  private error: string | null = null

  @state()
  private returnUrl = '/'

  async connectedCallback(): Promise<void> {
    super.connectedCallback()
    await this.handleCallback()
  }

  private async handleCallback(): Promise<void> {
    try {
      this.status = 'processing'
      this.statusMessage = 'Processing authentication...'
      this.error = null

      // Step 1: Handle the Keycloak callback
      const user = await authStore.handleCallback()

      if (!user) {
        this.error = 'Authentication failed. Please try again.'
        this.status = 'error'
        return
      }

      // Store the return URL from state
      this.returnUrl = (user.state as string) || '/'

      // Step 2: Fetch user's available tenants
      this.status = 'fetching-tenants'
      this.statusMessage = 'Loading your tenants...'

      const tenantsResponse = await authStore.fetchUserTenants()

      if (!tenantsResponse) {
        this.error = authStore.getState().error || 'Failed to fetch tenants. Please try again.'
        this.status = 'error'
        return
      }

      const { tenants } = tenantsResponse

      // Step 3: Handle based on number of tenants
      if (tenants.length === 0) {
        // No tenants - show error
        this.error = 'You do not have access to any tenants. Please contact an administrator.'
        this.status = 'error'
        return
      }

      if (tenants.length === 1) {
        // Single tenant - auto-select
        this.status = 'selecting-tenant'
        this.statusMessage = `Selecting ${tenants[0].tenant_name}...`

        const appToken = await authStore.selectTenant(tenants[0].tenant_id)

        if (!appToken) {
          this.error = authStore.getState().error || 'Failed to select tenant. Please try again.'
          this.status = 'error'
          return
        }

        // Success - redirect to app
        this.status = 'done'
        this.statusMessage = 'Redirecting...'
        setTimeout(() => {
          window.location.href = this.returnUrl
        }, 300)
        return
      }

      // Multiple tenants - redirect to tenant selection
      this.status = 'done'
      this.statusMessage = 'Redirecting to tenant selection...'

      // Encode the return URL for the tenant selector
      const selectTenantUrl = `/select-tenant?returnUrl=${encodeURIComponent(this.returnUrl)}`
      setTimeout(() => {
        window.location.href = selectTenantUrl
      }, 300)

    } catch (err) {
      console.error('Callback error:', err)
      this.error = err instanceof Error ? err.message : 'An unexpected error occurred'
      this.status = 'error'
    }
  }

  private handleRetry(): void {
    window.location.href = '/'
  }

  private handleLogout(): void {
    authStore.logout()
  }

  render() {
    if (this.status === 'error') {
      return html`
        <div class="container">
          <div class="error">
            <div class="error-title">Authentication Error</div>
            <p>${this.error}</p>
          </div>
          <button class="retry-btn" @click=${this.handleRetry}>Return to Home</button>
          <button class="logout-btn" @click=${this.handleLogout}>Logout</button>
        </div>
      `
    }

    return html`
      <div class="container">
        <div class="loading"></div>
        <h2>Signing you in...</h2>
        <p>Please wait while we complete the authentication.</p>
        <p class="status-text">${this.statusMessage}</p>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'auth-callback': AuthCallback
  }
}
