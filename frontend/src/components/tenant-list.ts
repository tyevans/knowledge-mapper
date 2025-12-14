import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { authStore, type AuthState } from '../auth'
import { apiClient } from '../api/client'
import type { TenantWithStoreMapping, TenantListResponse, TenantCreate, TenantInfo } from '../api/types'

/**
 * Tenant List Component
 *
 * Displays a list of tenants for platform administrators.
 * Requires tenants/read, tenants/manage, or admin scope.
 */
@customElement('tenant-list')
export class TenantList extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .card {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
      overflow: hidden;
    }

    .card-header {
      background: #1f2937;
      color: white;
      padding: 1rem 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .card-header h2 {
      margin: 0;
      font-size: 1.125rem;
    }

    .badge {
      background: rgba(255, 255, 255, 0.2);
      padding: 0.25rem 0.5rem;
      border-radius: 0.25rem;
      font-size: 0.75rem;
    }

    .card-body {
      padding: 1.5rem;
    }

    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
      flex-wrap: wrap;
      gap: 0.5rem;
    }

    .search-box {
      display: flex;
      gap: 0.5rem;
      flex: 1;
      max-width: 300px;
    }

    .search-box input {
      flex: 1;
      padding: 0.5rem;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      font-size: 0.875rem;
    }

    .search-box input:focus {
      outline: none;
      border-color: #1e3a8a;
      box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
    }

    .filters {
      display: flex;
      gap: 0.5rem;
      align-items: center;
    }

    .checkbox-label {
      display: flex;
      align-items: center;
      gap: 0.25rem;
      font-size: 0.875rem;
      color: #374151;
      cursor: pointer;
    }

    .tenant-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }

    .tenant-table th,
    .tenant-table td {
      padding: 0.75rem 1rem;
      text-align: left;
      border-bottom: 1px solid #e5e7eb;
    }

    .tenant-table th {
      background: #f9fafb;
      font-weight: 600;
      color: #374151;
    }

    .tenant-table tr:hover {
      background: #f9fafb;
    }

    .tenant-name {
      font-weight: 500;
      color: #1e3a8a;
    }

    .tenant-slug {
      font-size: 0.75rem;
      color: #6b7280;
      font-family: monospace;
    }

    .status-badge {
      display: inline-block;
      padding: 0.125rem 0.5rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
    }

    .status-active {
      background: #d1fae5;
      color: #065f46;
    }

    .status-inactive {
      background: #fee2e2;
      color: #991b1b;
    }

    .migration-badge {
      display: inline-block;
      padding: 0.125rem 0.5rem;
      border-radius: 0.25rem;
      font-size: 0.75rem;
      font-family: monospace;
    }

    .migration-normal {
      background: #e5e7eb;
      color: #374151;
    }

    .migration-active {
      background: #fef3c7;
      color: #92400e;
    }

    .store-id {
      font-family: monospace;
      font-size: 0.75rem;
      color: #6b7280;
    }

    .stats {
      font-size: 0.75rem;
      color: #6b7280;
    }

    .actions {
      display: flex;
      gap: 0.5rem;
    }

    .action-btn {
      padding: 0.25rem 0.5rem;
      border: 1px solid #e5e7eb;
      border-radius: 0.25rem;
      background: white;
      font-size: 0.75rem;
      cursor: pointer;
      transition: all 0.2s;
    }

    .action-btn:hover {
      background: #f9fafb;
      border-color: #1e3a8a;
      color: #1e3a8a;
    }

    .pagination {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 1rem;
      padding-top: 1rem;
      border-top: 1px solid #e5e7eb;
    }

    .pagination-info {
      font-size: 0.875rem;
      color: #6b7280;
    }

    .pagination-controls {
      display: flex;
      gap: 0.25rem;
    }

    .page-btn {
      padding: 0.375rem 0.75rem;
      border: 1px solid #e5e7eb;
      border-radius: 0.25rem;
      background: white;
      font-size: 0.875rem;
      cursor: pointer;
      transition: all 0.2s;
    }

    .page-btn:hover:not(:disabled) {
      background: #f9fafb;
      border-color: #1e3a8a;
    }

    .page-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .page-btn.active {
      background: #1e3a8a;
      color: white;
      border-color: #1e3a8a;
    }

    .empty-state {
      text-align: center;
      padding: 3rem;
      color: #6b7280;
    }

    .empty-state-icon {
      font-size: 3rem;
      margin-bottom: 1rem;
    }

    .loading {
      text-align: center;
      padding: 3rem;
      color: #6b7280;
    }

    .error {
      background: #fef2f2;
      color: #991b1b;
      padding: 0.75rem;
      border-radius: 0.375rem;
      margin-bottom: 1rem;
      font-size: 0.875rem;
    }

    .unauthorized {
      text-align: center;
      padding: 3rem;
      color: #6b7280;
    }

    .unauthorized-icon {
      font-size: 3rem;
      margin-bottom: 1rem;
    }

    .date {
      font-size: 0.75rem;
      color: #6b7280;
    }

    .create-btn {
      padding: 0.5rem 1rem;
      background: #1e3a8a;
      color: white;
      border: none;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }

    .create-btn:hover {
      background: #1e40af;
    }

    .create-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }

    .modal {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 25px 50px rgba(0, 0, 0, 0.25);
      width: 100%;
      max-width: 28rem;
      max-height: 90vh;
      overflow-y: auto;
    }

    .modal-header {
      padding: 1rem 1.5rem;
      border-bottom: 1px solid #e5e7eb;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .modal-header h3 {
      margin: 0;
      font-size: 1.125rem;
      font-weight: 600;
      color: #111827;
    }

    .modal-close {
      background: none;
      border: none;
      font-size: 1.5rem;
      color: #6b7280;
      cursor: pointer;
      padding: 0;
      line-height: 1;
    }

    .modal-close:hover {
      color: #374151;
    }

    .modal-body {
      padding: 1.5rem;
    }

    .form-group {
      margin-bottom: 1rem;
    }

    .form-group:last-child {
      margin-bottom: 0;
    }

    .form-label {
      display: block;
      font-size: 0.875rem;
      font-weight: 500;
      color: #374151;
      margin-bottom: 0.375rem;
    }

    .form-input {
      width: 100%;
      padding: 0.5rem 0.75rem;
      border: 1px solid #d1d5db;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      box-sizing: border-box;
      transition: border-color 0.2s, box-shadow 0.2s;
    }

    .form-input:focus {
      outline: none;
      border-color: #1e3a8a;
      box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
    }

    .form-input.error {
      border-color: #dc2626;
    }

    .form-hint {
      font-size: 0.75rem;
      color: #6b7280;
      margin-top: 0.25rem;
    }

    .form-error {
      font-size: 0.75rem;
      color: #dc2626;
      margin-top: 0.25rem;
    }

    .modal-footer {
      padding: 1rem 1.5rem;
      border-top: 1px solid #e5e7eb;
      display: flex;
      justify-content: flex-end;
      gap: 0.75rem;
    }

    .btn-cancel {
      padding: 0.5rem 1rem;
      background: white;
      color: #374151;
      border: 1px solid #d1d5db;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      cursor: pointer;
      transition: background 0.2s;
    }

    .btn-cancel:hover {
      background: #f9fafb;
    }

    .btn-submit {
      padding: 0.5rem 1rem;
      background: #1e3a8a;
      color: white;
      border: none;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }

    .btn-submit:hover:not(:disabled) {
      background: #1e40af;
    }

    .btn-submit:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  `

  @state()
  private authState: AuthState = {
    user: null,
    isAuthenticated: false,
    isLoading: true,
    error: null,
  }

  @state()
  private tenants: TenantWithStoreMapping[] = []

  @state()
  private isLoading = true

  @state()
  private error: string | null = null

  @state()
  private page = 1

  @state()
  private pageSize = 20

  @state()
  private total = 0

  @state()
  private pages = 1

  @state()
  private searchQuery = ''

  @state()
  private includeInactive = false

  @state()
  private showCreateModal = false

  @state()
  private createForm: TenantCreate = { name: '', slug: '' }

  @state()
  private createFormErrors: { name?: string; slug?: string } = {}

  @state()
  private isCreating = false

  @state()
  private createError: string | null = null

  private unsubscribe?: () => void
  private searchTimeout?: number

  connectedCallback(): void {
    super.connectedCallback()
    this.unsubscribe = authStore.subscribe((state) => {
      const wasAuthenticated = this.authState.isAuthenticated
      this.authState = state

      if (!state.isLoading && state.isAuthenticated && !wasAuthenticated) {
        this.loadTenants()
      }
    })

    if (this.authState.isAuthenticated) {
      this.loadTenants()
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.unsubscribe?.()
    if (this.searchTimeout) {
      clearTimeout(this.searchTimeout)
    }
  }

  private hasRequiredScope(): boolean {
    const user = this.authState.user
    if (!user?.profile) return false

    // Check for tenant management or admin scopes
    // Scopes can come from standard scope claim or custom_scopes claim
    const standardScopes = user.scope?.split(' ') || []
    const customScopes = (user.profile.custom_scopes as string)?.split(' ') || []
    const allScopes = [...standardScopes, ...customScopes]
    const requiredScopes = ['tenants/read', 'tenants/manage', 'admin']

    return requiredScopes.some((scope) => allScopes.includes(scope))
  }

  private async loadTenants(): Promise<void> {
    this.isLoading = true
    this.error = null

    try {
      const params = new URLSearchParams({
        page: this.page.toString(),
        page_size: this.pageSize.toString(),
        include_inactive: this.includeInactive.toString(),
      })

      if (this.searchQuery.trim()) {
        params.set('search', this.searchQuery.trim())
      }

      const response = await apiClient.get<TenantListResponse>(
        `/api/v1/tenants?${params.toString()}`
      )

      if (response.success) {
        this.tenants = response.data.items
        this.total = response.data.total
        this.pages = response.data.pages
      } else {
        if (response.error.status === 403) {
          this.error = 'You do not have permission to view tenants'
        } else {
          this.error = response.error.message
        }
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to load tenants'
    } finally {
      this.isLoading = false
    }
  }

  private handleSearch(e: Event): void {
    const input = e.target as HTMLInputElement
    this.searchQuery = input.value

    // Debounce search
    if (this.searchTimeout) {
      clearTimeout(this.searchTimeout)
    }
    this.searchTimeout = window.setTimeout(() => {
      this.page = 1
      this.loadTenants()
    }, 300)
  }

  private handleIncludeInactiveChange(e: Event): void {
    const input = e.target as HTMLInputElement
    this.includeInactive = input.checked
    this.page = 1
    this.loadTenants()
  }

  private goToPage(newPage: number): void {
    if (newPage >= 1 && newPage <= this.pages) {
      this.page = newPage
      this.loadTenants()
    }
  }

  private formatDate(dateString: string): string {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  }

  private getMigrationStateClass(state: string): string {
    return state === 'NORMAL' ? 'migration-normal' : 'migration-active'
  }

  private hasManageScope(): boolean {
    const user = this.authState.user
    if (!user?.profile) return false

    const standardScopes = user.scope?.split(' ') || []
    const customScopes = (user.profile.custom_scopes as string)?.split(' ') || []
    const allScopes = [...standardScopes, ...customScopes]
    const manageScopes = ['tenants/manage', 'admin']

    return manageScopes.some((scope) => allScopes.includes(scope))
  }

  private generateSlug(name: string): string {
    return name
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .substring(0, 255)
  }

  private openCreateModal(): void {
    this.createForm = { name: '', slug: '' }
    this.createFormErrors = {}
    this.createError = null
    this.showCreateModal = true
  }

  private closeCreateModal(): void {
    this.showCreateModal = false
    this.createForm = { name: '', slug: '' }
    this.createFormErrors = {}
    this.createError = null
  }

  private handleNameChange(e: Event): void {
    const input = e.target as HTMLInputElement
    const name = input.value
    this.createForm = {
      ...this.createForm,
      name,
      slug: this.generateSlug(name),
    }
    this.createFormErrors = { ...this.createFormErrors, name: undefined }
  }

  private handleSlugChange(e: Event): void {
    const input = e.target as HTMLInputElement
    this.createForm = { ...this.createForm, slug: input.value }
    this.createFormErrors = { ...this.createFormErrors, slug: undefined }
  }

  private validateForm(): boolean {
    const errors: { name?: string; slug?: string } = {}

    if (!this.createForm.name.trim()) {
      errors.name = 'Name is required'
    } else if (this.createForm.name.length > 255) {
      errors.name = 'Name must be 255 characters or less'
    }

    if (!this.createForm.slug.trim()) {
      errors.slug = 'Slug is required'
    } else if (this.createForm.slug.length < 2) {
      errors.slug = 'Slug must be at least 2 characters'
    } else if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(this.createForm.slug)) {
      errors.slug = 'Slug must start and end with lowercase letter or number, and contain only lowercase letters, numbers, and hyphens'
    }

    this.createFormErrors = errors
    return Object.keys(errors).length === 0
  }

  private async handleCreateSubmit(e: Event): Promise<void> {
    e.preventDefault()

    if (!this.validateForm()) {
      return
    }

    this.isCreating = true
    this.createError = null

    try {
      const response = await apiClient.post<TenantInfo>('/api/v1/tenants', this.createForm)

      if (response.success) {
        this.closeCreateModal()
        this.loadTenants()
        this.dispatchEvent(
          new CustomEvent('tenant-created', {
            detail: { tenant: response.data },
            bubbles: true,
            composed: true,
          })
        )
      } else {
        if (response.error.status === 409) {
          this.createFormErrors = { slug: 'A tenant with this slug already exists' }
        } else if (response.error.status === 403) {
          this.createError = 'You do not have permission to create tenants'
        } else {
          this.createError = response.error.message
        }
      }
    } catch (err) {
      this.createError = err instanceof Error ? err.message : 'Failed to create tenant'
    } finally {
      this.isCreating = false
    }
  }

  private renderUnauthorized() {
    return html`
      <div class="unauthorized">
        <div class="unauthorized-icon">&#128274;</div>
        <h3>Access Restricted</h3>
        <p>You need tenant management permissions to view this page.</p>
        <p>Required scopes: tenants/read, tenants/manage, or admin</p>
      </div>
    `
  }

  private renderToolbar() {
    return html`
      <div class="toolbar">
        <div class="search-box">
          <input
            type="text"
            placeholder="Search tenants..."
            .value=${this.searchQuery}
            @input=${this.handleSearch}
          />
        </div>
        <div class="filters">
          <label class="checkbox-label">
            <input
              type="checkbox"
              .checked=${this.includeInactive}
              @change=${this.handleIncludeInactiveChange}
            />
            Show inactive
          </label>
          ${this.hasManageScope()
            ? html`
                <button class="create-btn" @click=${this.openCreateModal}>
                  + Create Tenant
                </button>
              `
            : null}
        </div>
      </div>
    `
  }

  private renderTenantTable() {
    if (this.tenants.length === 0) {
      return html`
        <div class="empty-state">
          <div class="empty-state-icon">&#128450;</div>
          <h3>No tenants found</h3>
          <p>
            ${this.searchQuery
              ? 'Try adjusting your search criteria'
              : 'No tenants have been created yet'}
          </p>
        </div>
      `
    }

    return html`
      <table class="tenant-table">
        <thead>
          <tr>
            <th>Tenant</th>
            <th>Status</th>
            <th>Store</th>
            <th>Migration</th>
            <th>Users</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${this.tenants.map(
            (tenant) => html`
              <tr>
                <td>
                  <div class="tenant-name">${tenant.name}</div>
                  <div class="tenant-slug">${tenant.slug}</div>
                </td>
                <td>
                  <span
                    class="status-badge ${tenant.is_active
                      ? 'status-active'
                      : 'status-inactive'}"
                  >
                    ${tenant.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td>
                  <span class="store-id">
                    ${tenant.store_mapping?.store_id || 'default'}
                  </span>
                </td>
                <td>
                  <span
                    class="migration-badge ${this.getMigrationStateClass(
                      tenant.store_mapping?.migration_state || 'NORMAL'
                    )}"
                  >
                    ${tenant.store_mapping?.migration_state || 'NORMAL'}
                  </span>
                </td>
                <td>
                  <span class="stats">${tenant.user_count}</span>
                </td>
                <td>
                  <span class="date">${this.formatDate(tenant.created_at)}</span>
                </td>
                <td>
                  <div class="actions">
                    <button
                      class="action-btn"
                      @click=${() => this.viewTenant(tenant)}
                    >
                      View
                    </button>
                  </div>
                </td>
              </tr>
            `
          )}
        </tbody>
      </table>
    `
  }

  private renderPagination() {
    if (this.pages <= 1) return null

    const pageNumbers: number[] = []
    const maxVisible = 5
    let start = Math.max(1, this.page - Math.floor(maxVisible / 2))
    const end = Math.min(this.pages, start + maxVisible - 1)

    if (end - start + 1 < maxVisible) {
      start = Math.max(1, end - maxVisible + 1)
    }

    for (let i = start; i <= end; i++) {
      pageNumbers.push(i)
    }

    return html`
      <div class="pagination">
        <div class="pagination-info">
          Showing ${(this.page - 1) * this.pageSize + 1} -
          ${Math.min(this.page * this.pageSize, this.total)} of ${this.total}
        </div>
        <div class="pagination-controls">
          <button
            class="page-btn"
            ?disabled=${this.page === 1}
            @click=${() => this.goToPage(1)}
          >
            First
          </button>
          <button
            class="page-btn"
            ?disabled=${this.page === 1}
            @click=${() => this.goToPage(this.page - 1)}
          >
            Prev
          </button>
          ${pageNumbers.map(
            (num) => html`
              <button
                class="page-btn ${num === this.page ? 'active' : ''}"
                @click=${() => this.goToPage(num)}
              >
                ${num}
              </button>
            `
          )}
          <button
            class="page-btn"
            ?disabled=${this.page === this.pages}
            @click=${() => this.goToPage(this.page + 1)}
          >
            Next
          </button>
          <button
            class="page-btn"
            ?disabled=${this.page === this.pages}
            @click=${() => this.goToPage(this.pages)}
          >
            Last
          </button>
        </div>
      </div>
    `
  }

  private viewTenant(tenant: TenantWithStoreMapping): void {
    // Dispatch custom event for parent to handle navigation
    this.dispatchEvent(
      new CustomEvent('tenant-selected', {
        detail: { tenant },
        bubbles: true,
        composed: true,
      })
    )
  }

  private renderCreateModal() {
    if (!this.showCreateModal) return null

    return html`
      <div class="modal-overlay" @click=${(e: Event) => {
        if (e.target === e.currentTarget) this.closeCreateModal()
      }}>
        <div class="modal">
          <div class="modal-header">
            <h3>Create New Tenant</h3>
            <button class="modal-close" @click=${this.closeCreateModal}>&times;</button>
          </div>
          <form @submit=${this.handleCreateSubmit}>
            <div class="modal-body">
              ${this.createError
                ? html`<div class="error">${this.createError}</div>`
                : null}
              <div class="form-group">
                <label class="form-label" for="tenant-name">Name *</label>
                <input
                  type="text"
                  id="tenant-name"
                  class="form-input ${this.createFormErrors.name ? 'error' : ''}"
                  .value=${this.createForm.name}
                  @input=${this.handleNameChange}
                  placeholder="Acme Corporation"
                  ?disabled=${this.isCreating}
                />
                ${this.createFormErrors.name
                  ? html`<div class="form-error">${this.createFormErrors.name}</div>`
                  : html`<div class="form-hint">The display name for this tenant</div>`}
              </div>
              <div class="form-group">
                <label class="form-label" for="tenant-slug">Slug *</label>
                <input
                  type="text"
                  id="tenant-slug"
                  class="form-input ${this.createFormErrors.slug ? 'error' : ''}"
                  .value=${this.createForm.slug}
                  @input=${this.handleSlugChange}
                  placeholder="acme-corporation"
                  ?disabled=${this.isCreating}
                />
                ${this.createFormErrors.slug
                  ? html`<div class="form-error">${this.createFormErrors.slug}</div>`
                  : html`<div class="form-hint">URL-safe identifier (auto-generated from name)</div>`}
              </div>
            </div>
            <div class="modal-footer">
              <button
                type="button"
                class="btn-cancel"
                @click=${this.closeCreateModal}
                ?disabled=${this.isCreating}
              >
                Cancel
              </button>
              <button
                type="submit"
                class="btn-submit"
                ?disabled=${this.isCreating}
              >
                ${this.isCreating ? 'Creating...' : 'Create Tenant'}
              </button>
            </div>
          </form>
        </div>
      </div>
    `
  }

  render() {
    const { isAuthenticated, isLoading: authLoading } = this.authState

    return html`
      <div class="card">
        <div class="card-header">
          <h2>Tenant Management</h2>
          <span class="badge">
            ${isAuthenticated ? 'Platform Admin' : 'Not Authenticated'}
          </span>
        </div>
        <div class="card-body">
          ${this.error ? html`<div class="error">${this.error}</div>` : null}

          ${authLoading
            ? html`<div class="loading">Checking authentication...</div>`
            : !isAuthenticated
              ? html`
                  <div class="unauthorized">
                    <div class="unauthorized-icon">&#128274;</div>
                    <h3>Authentication Required</h3>
                    <p>Please log in to access tenant management.</p>
                  </div>
                `
              : !this.hasRequiredScope()
                ? this.renderUnauthorized()
                : this.isLoading
                  ? html`<div class="loading">Loading tenants...</div>`
                  : html`
                      ${this.renderToolbar()} ${this.renderTenantTable()}
                      ${this.renderPagination()}
                    `}
        </div>
      </div>
      ${this.renderCreateModal()}
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'tenant-list': TenantList
  }
}
