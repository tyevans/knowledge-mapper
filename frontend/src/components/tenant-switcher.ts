import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { authStore, type AuthState } from '../auth'
import type { TenantMembership } from '../api/types'

/**
 * Tenant Switcher Component
 *
 * Header dropdown component for viewing and switching between tenants.
 * Shows current tenant name and provides a dropdown to switch to other tenants.
 *
 * Usage:
 * ```html
 * <tenant-switcher></tenant-switcher>
 * ```
 */
@customElement('tenant-switcher')
export class TenantSwitcher extends LitElement {
  static styles = css`
    :host {
      display: inline-block;
      position: relative;
    }

    .switcher-button {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 0.75rem;
      background: rgba(255, 255, 255, 0.1);
      color: white;
      border: 1px solid rgba(255, 255, 255, 0.2);
      border-radius: 0.375rem;
      cursor: pointer;
      font-size: 0.875rem;
      font-weight: 500;
      transition: background 0.2s, border-color 0.2s;
    }

    .switcher-button:hover {
      background: rgba(255, 255, 255, 0.2);
      border-color: rgba(255, 255, 255, 0.3);
    }

    .switcher-button:focus {
      outline: none;
      box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.5);
    }

    .tenant-name {
      max-width: 150px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .chevron {
      width: 12px;
      height: 12px;
      transition: transform 0.2s;
    }

    .chevron.open {
      transform: rotate(180deg);
    }

    .dropdown {
      position: absolute;
      top: calc(100% + 0.5rem);
      right: 0;
      min-width: 220px;
      max-width: 300px;
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
      z-index: 1000;
      overflow: hidden;
    }

    .dropdown-header {
      padding: 0.75rem 1rem;
      background: #f9fafb;
      border-bottom: 1px solid #e5e7eb;
    }

    .dropdown-header-label {
      font-size: 0.75rem;
      font-weight: 500;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .tenant-list {
      max-height: 300px;
      overflow-y: auto;
    }

    .tenant-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.75rem 1rem;
      cursor: pointer;
      transition: background 0.2s;
      border: none;
      background: none;
      width: 100%;
      text-align: left;
    }

    .tenant-item:hover {
      background: #f3f4f6;
    }

    .tenant-item:focus {
      outline: none;
      background: #f3f4f6;
    }

    .tenant-item.current {
      background: #f5f3ff;
    }

    .tenant-item.current:hover {
      background: #ede9fe;
    }

    .tenant-item-info {
      flex: 1;
      min-width: 0;
    }

    .tenant-item-name {
      font-size: 0.875rem;
      font-weight: 500;
      color: #1f2937;
      margin: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .tenant-item-role {
      font-size: 0.75rem;
      color: #6b7280;
      margin: 0.125rem 0 0 0;
    }

    .current-badge {
      flex-shrink: 0;
      padding: 0.125rem 0.5rem;
      background: #667eea;
      color: white;
      border-radius: 9999px;
      font-size: 0.625rem;
      font-weight: 600;
      text-transform: uppercase;
    }

    .switching-badge {
      flex-shrink: 0;
      padding: 0.125rem 0.5rem;
      background: #9ca3af;
      color: white;
      border-radius: 9999px;
      font-size: 0.625rem;
      font-weight: 600;
    }

    .backdrop {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      z-index: 999;
    }

    .no-tenants {
      padding: 1rem;
      text-align: center;
      color: #6b7280;
      font-size: 0.875rem;
    }

    /* Hide when not authenticated or no tenant selected */
    :host([hidden]) {
      display: none;
    }
  `

  @state()
  private authState: AuthState = authStore.getState()

  @state()
  private isOpen = false

  @state()
  private switchingToId: string | null = null

  private unsubscribe?: () => void

  connectedCallback(): void {
    super.connectedCallback()
    this.unsubscribe = authStore.subscribe((state) => {
      this.authState = state
    })
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.unsubscribe?.()
  }

  private toggleDropdown(): void {
    this.isOpen = !this.isOpen
  }

  private closeDropdown(): void {
    this.isOpen = false
  }

  private async handleSwitchTenant(tenant: TenantMembership): Promise<void> {
    const { selectedTenant } = this.authState

    // Don't switch to current tenant
    if (selectedTenant?.tenant_id === tenant.tenant_id) {
      this.closeDropdown()
      return
    }

    this.switchingToId = tenant.tenant_id

    // switchTenant will reload the page on success
    await authStore.switchTenant(tenant.tenant_id)

    // If we get here, something went wrong (page should have reloaded)
    this.switchingToId = null
  }

  private renderTenantItem(tenant: TenantMembership) {
    const { selectedTenant } = this.authState
    const isCurrent = selectedTenant?.tenant_id === tenant.tenant_id
    const isSwitching = this.switchingToId === tenant.tenant_id

    return html`
      <button
        class="tenant-item ${isCurrent ? 'current' : ''}"
        @click=${() => this.handleSwitchTenant(tenant)}
        ?disabled=${isSwitching}
      >
        <div class="tenant-item-info">
          <p class="tenant-item-name">${tenant.tenant_name}</p>
          <p class="tenant-item-role">${tenant.role}${tenant.is_default ? ' (default)' : ''}</p>
        </div>
        ${isSwitching
          ? html`<span class="switching-badge">Switching...</span>`
          : isCurrent
            ? html`<span class="current-badge">Current</span>`
            : null}
      </button>
    `
  }

  render() {
    const { selectedTenant, availableTenants, isAuthenticated, appToken } = this.authState

    // Don't show if not authenticated or no app token
    if (!isAuthenticated || !appToken || !selectedTenant) {
      return null
    }

    // Don't show if only one tenant
    if (availableTenants.length <= 1) {
      return html`
        <div class="switcher-button" style="cursor: default;">
          <span class="tenant-name">${selectedTenant.tenant_name}</span>
        </div>
      `
    }

    return html`
      ${this.isOpen
        ? html`<div class="backdrop" @click=${this.closeDropdown}></div>`
        : null}

      <button class="switcher-button" @click=${this.toggleDropdown}>
        <span class="tenant-name">${selectedTenant.tenant_name}</span>
        <svg
          class="chevron ${this.isOpen ? 'open' : ''}"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </button>

      ${this.isOpen
        ? html`
            <div class="dropdown">
              <div class="dropdown-header">
                <span class="dropdown-header-label">Switch Tenant</span>
              </div>
              <div class="tenant-list">
                ${availableTenants.length > 0
                  ? availableTenants.map((t) => this.renderTenantItem(t))
                  : html`<div class="no-tenants">No tenants available</div>`}
              </div>
            </div>
          `
        : null}
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'tenant-switcher': TenantSwitcher
  }
}
