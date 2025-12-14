import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { authStore, type AuthState } from '../auth'
import type { TenantMembership } from '../api/types'

/**
 * Tenant Selector Component
 *
 * Full page component for selecting a tenant after Keycloak authentication.
 * Displays all available tenants as cards with role information.
 *
 * Usage:
 * ```html
 * <tenant-selector return-url="/"></tenant-selector>
 * ```
 */
@customElement('tenant-selector')
export class TenantSelector extends LitElement {
  static styles = css`
    :host {
      display: block;
      min-height: 100vh;
      background: #f3f4f6;
      padding: 2rem;
    }

    .container {
      max-width: 800px;
      margin: 0 auto;
    }

    .header {
      text-align: center;
      color: #111827;
      margin-bottom: 2rem;
    }

    .header h1 {
      margin: 0 0 0.5rem 0;
      font-size: 2rem;
      font-weight: 700;
    }

    .header p {
      margin: 0;
      color: #6b7280;
      font-size: 1.1rem;
    }

    .tenants-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 1.5rem;
    }

    .tenant-card {
      background: white;
      border-radius: 0.75rem;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
      overflow: hidden;
      cursor: pointer;
      transition: transform 0.2s, box-shadow 0.2s;
      border: 2px solid transparent;
    }

    .tenant-card:hover {
      transform: translateY(-4px);
      box-shadow: 0 8px 25px rgba(0, 0, 0, 0.2);
    }

    .tenant-card:focus {
      outline: none;
      border-color: #1f2937;
    }

    .tenant-card.selected {
      border-color: #1f2937;
      background: #f9fafb;
    }

    .tenant-card.loading {
      opacity: 0.7;
      pointer-events: none;
    }

    .card-header {
      padding: 1.25rem;
      background: #f9fafb;
      border-bottom: 1px solid #e5e7eb;
    }

    .tenant-name {
      margin: 0;
      font-size: 1.25rem;
      font-weight: 600;
      color: #1f2937;
    }

    .tenant-slug {
      margin: 0.25rem 0 0 0;
      font-size: 0.875rem;
      color: #6b7280;
      font-family: monospace;
    }

    .card-body {
      padding: 1.25rem;
    }

    .role-badge {
      display: inline-flex;
      align-items: center;
      padding: 0.25rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
      text-transform: capitalize;
    }

    .role-badge.owner {
      background: #fef3c7;
      color: #92400e;
    }

    .role-badge.admin {
      background: #dbeafe;
      color: #1e40af;
    }

    .role-badge.member {
      background: #e5e7eb;
      color: #374151;
    }

    .default-badge {
      display: inline-flex;
      align-items: center;
      margin-left: 0.5rem;
      padding: 0.25rem 0.5rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
      background: #ecfdf5;
      color: #065f46;
    }

    .card-footer {
      padding: 1rem 1.25rem;
      background: #f9fafb;
      border-top: 1px solid #e5e7eb;
      text-align: center;
    }

    .select-btn {
      padding: 0.625rem 1.5rem;
      background: #1f2937;
      color: white;
      border: none;
      border-radius: 0.375rem;
      cursor: pointer;
      font-size: 0.875rem;
      font-weight: 500;
      transition: background 0.2s;
      width: 100%;
    }

    .select-btn:hover {
      background: #374151;
    }

    .select-btn:disabled {
      background: #9ca3af;
      cursor: not-allowed;
    }

    .loading-state {
      text-align: center;
      color: #374151;
      padding: 4rem 2rem;
    }

    .loading-spinner {
      display: inline-block;
      width: 3rem;
      height: 3rem;
      border: 3px solid #e5e7eb;
      border-radius: 50%;
      border-top-color: #1f2937;
      animation: spin 1s ease-in-out infinite;
    }

    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }

    .loading-text {
      margin-top: 1rem;
      font-size: 1.1rem;
    }

    .error-state {
      text-align: center;
      padding: 4rem 2rem;
    }

    .error-card {
      background: white;
      border-radius: 0.75rem;
      padding: 2rem;
      max-width: 400px;
      margin: 0 auto;
    }

    .error-title {
      color: #991b1b;
      margin: 0 0 1rem 0;
      font-size: 1.25rem;
    }

    .error-message {
      color: #6b7280;
      margin: 0 0 1.5rem 0;
    }

    .retry-btn {
      padding: 0.625rem 1.5rem;
      background: #1f2937;
      color: white;
      border: none;
      border-radius: 0.375rem;
      cursor: pointer;
      font-size: 0.875rem;
      font-weight: 500;
    }

    .retry-btn:hover {
      background: #374151;
    }

    .no-tenants {
      text-align: center;
      padding: 4rem 2rem;
    }

    .no-tenants-card {
      background: white;
      border-radius: 0.75rem;
      padding: 2rem;
      max-width: 400px;
      margin: 0 auto;
    }

    .no-tenants-title {
      color: #374151;
      margin: 0 0 1rem 0;
      font-size: 1.25rem;
    }

    .no-tenants-message {
      color: #6b7280;
      margin: 0 0 1.5rem 0;
    }

    .logout-btn {
      padding: 0.625rem 1.5rem;
      background: #ef4444;
      color: white;
      border: none;
      border-radius: 0.375rem;
      cursor: pointer;
      font-size: 0.875rem;
      font-weight: 500;
    }

    .logout-btn:hover {
      background: #dc2626;
    }
  `

  @state()
  private authState: AuthState = authStore.getState()

  @state()
  private selectingTenantId: string | null = null

  @state()
  private error: string | null = null

  private unsubscribe?: () => void

  connectedCallback(): void {
    super.connectedCallback()
    this.unsubscribe = authStore.subscribe((state) => {
      this.authState = state
      this.error = state.error
    })
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.unsubscribe?.()
  }

  private async handleSelectTenant(tenant: TenantMembership): Promise<void> {
    this.selectingTenantId = tenant.tenant_id
    this.error = null

    const appToken = await authStore.selectTenant(tenant.tenant_id)

    if (appToken) {
      // Success - redirect to return URL or home
      const returnUrl = new URLSearchParams(window.location.search).get('returnUrl') || '/'
      window.location.href = returnUrl
    } else {
      this.selectingTenantId = null
    }
  }

  private handleLogout(): void {
    authStore.logout()
  }

  private renderTenantCard(tenant: TenantMembership) {
    const isSelecting = this.selectingTenantId === tenant.tenant_id
    const isDisabled = this.selectingTenantId !== null

    return html`
      <div
        class="tenant-card ${isSelecting ? 'selected loading' : ''}"
        tabindex="0"
        @click=${() => !isDisabled && this.handleSelectTenant(tenant)}
        @keypress=${(e: KeyboardEvent) =>
          e.key === 'Enter' && !isDisabled && this.handleSelectTenant(tenant)}
      >
        <div class="card-header">
          <h3 class="tenant-name">${tenant.tenant_name}</h3>
          <p class="tenant-slug">${tenant.tenant_slug}</p>
        </div>
        <div class="card-body">
          <span class="role-badge ${tenant.role}">${tenant.role}</span>
          ${tenant.is_default ? html`<span class="default-badge">Default</span>` : null}
        </div>
        <div class="card-footer">
          <button class="select-btn" ?disabled=${isDisabled}>
            ${isSelecting ? 'Selecting...' : 'Select Tenant'}
          </button>
        </div>
      </div>
    `
  }

  render() {
    const { isLoading, availableTenants, user } = this.authState

    // Loading state
    if (isLoading) {
      return html`
        <div class="container">
          <div class="loading-state">
            <div class="loading-spinner"></div>
            <p class="loading-text">Loading your tenants...</p>
          </div>
        </div>
      `
    }

    // Error state
    if (this.error) {
      return html`
        <div class="container">
          <div class="error-state">
            <div class="error-card">
              <h2 class="error-title">Something went wrong</h2>
              <p class="error-message">${this.error}</p>
              <button class="retry-btn" @click=${() => authStore.fetchUserTenants()}>
                Try Again
              </button>
            </div>
          </div>
        </div>
      `
    }

    // No tenants state
    if (availableTenants.length === 0) {
      return html`
        <div class="container">
          <div class="no-tenants">
            <div class="no-tenants-card">
              <h2 class="no-tenants-title">No Tenants Available</h2>
              <p class="no-tenants-message">
                You don't have access to any tenants yet. Please contact an administrator.
              </p>
              <button class="logout-btn" @click=${this.handleLogout}>Logout</button>
            </div>
          </div>
        </div>
      `
    }

    // Tenant selection
    return html`
      <div class="container">
        <div class="header">
          <h1>Select a Tenant</h1>
          <p>Welcome back${user?.profile?.name ? `, ${user.profile.name}` : ''}! Choose a tenant to continue.</p>
        </div>
        <div class="tenants-grid">${availableTenants.map((t) => this.renderTenantCard(t))}</div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'tenant-selector': TenantSelector
  }
}
