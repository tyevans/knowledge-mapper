import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { authStore, type AuthState } from '../../auth'
import { apiClient } from '../../api/client'
import type {
  ExtractedEntitySummary,
  EntityType,
  PaginatedResponse,
} from '../../api/scraping-types'
import { ENTITY_TYPE_LABELS } from '../../api/scraping-types'
import '../shared/km-pagination'
import '../shared/km-status-badge'
import '../shared/km-empty-state'

/**
 * Entity Explorer Component
 *
 * Browse and search extracted entities across all scraping jobs.
 *
 * @fires view-entity - When user clicks to view an entity detail
 */
@customElement('entity-explorer')
export class EntityExplorer extends LitElement {
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
      gap: 1rem;
      margin-bottom: 1rem;
      flex-wrap: wrap;
    }

    .search-input {
      flex: 1;
      min-width: 200px;
      padding: 0.5rem 0.75rem;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      font-size: 0.875rem;
    }

    .search-input:focus {
      outline: none;
      border-color: #1e3a8a;
      box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
    }

    .filter-select {
      padding: 0.5rem;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      background: white;
    }

    .filter-select:focus {
      outline: none;
      border-color: #1e3a8a;
      box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
    }

    .entity-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 1rem;
    }

    .entity-card {
      border: 1px solid #e5e7eb;
      border-radius: 0.5rem;
      padding: 1rem;
      cursor: pointer;
      transition: all 0.2s;
    }

    .entity-card:hover {
      border-color: #1e3a8a;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }

    .entity-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 0.5rem;
      margin-bottom: 0.5rem;
    }

    .entity-name {
      font-weight: 500;
      color: #1e3a8a;
      font-size: 0.9375rem;
      word-break: break-word;
    }

    .entity-method {
      font-size: 0.75rem;
      color: #6b7280;
      margin-top: 0.25rem;
    }

    .entity-confidence {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-top: 0.75rem;
      font-size: 0.75rem;
      color: #6b7280;
    }

    .confidence-bar {
      flex: 1;
      height: 4px;
      background: #e5e7eb;
      border-radius: 2px;
      overflow: hidden;
    }

    .confidence-fill {
      height: 100%;
      background: #10b981;
    }

    .entity-date {
      font-size: 0.75rem;
      color: #9ca3af;
      margin-top: 0.5rem;
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
  `

  @state()
  private authState: AuthState | null = null

  @state()
  private entities: ExtractedEntitySummary[] = []

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
  private typeFilter: EntityType | '' = ''

  private unsubscribe?: () => void
  private searchTimeout: number | null = null

  connectedCallback(): void {
    super.connectedCallback()
    this.unsubscribe = authStore.subscribe((state) => {
      const wasAuthenticated = this.authState?.isAuthenticated
      this.authState = state

      if (state.isAuthenticated && !wasAuthenticated) {
        this.loadEntities()
      }
    })

    if (this.authState?.isAuthenticated) {
      this.loadEntities()
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.unsubscribe?.()
    if (this.searchTimeout) {
      clearTimeout(this.searchTimeout)
    }
  }

  private async loadEntities(): Promise<void> {
    this.isLoading = true
    this.error = null

    try {
      const params = new URLSearchParams({
        page: this.page.toString(),
        page_size: this.pageSize.toString(),
      })

      if (this.searchQuery.trim()) {
        params.set('search', this.searchQuery.trim())
      }

      if (this.typeFilter) {
        params.set('entity_type', this.typeFilter)
      }

      const response = await apiClient.get<PaginatedResponse<ExtractedEntitySummary>>(
        `/api/v1/entities?${params.toString()}`
      )

      if (response.success) {
        this.entities = response.data.items
        this.total = response.data.total
        this.pages = response.data.pages
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to load entities'
    } finally {
      this.isLoading = false
    }
  }

  private handlePageChange(e: CustomEvent): void {
    this.page = e.detail.page
    this.loadEntities()
  }

  private handleSearchInput(e: Event): void {
    const value = (e.target as HTMLInputElement).value
    this.searchQuery = value

    // Debounce search
    if (this.searchTimeout) {
      clearTimeout(this.searchTimeout)
    }

    this.searchTimeout = window.setTimeout(() => {
      this.page = 1
      this.loadEntities()
    }, 300)
  }

  private handleTypeFilterChange(e: Event): void {
    const select = e.target as HTMLSelectElement
    this.typeFilter = select.value as EntityType | ''
    this.page = 1
    this.loadEntities()
  }

  private handleViewEntity(entity: ExtractedEntitySummary): void {
    this.dispatchEvent(
      new CustomEvent('view-entity', {
        detail: { entityId: entity.id },
        bubbles: true,
        composed: true,
      })
    )
  }

  private formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString()
  }

  private renderEntityGrid() {
    if (this.entities.length === 0) {
      const message = this.searchQuery || this.typeFilter
        ? 'No entities match your search criteria.'
        : 'Entities will appear here after scraping jobs extract them.'

      return html`
        <km-empty-state
          icon="🔗"
          title="No entities found"
          message=${message}
        ></km-empty-state>
      `
    }

    return html`
      <div class="entity-grid">
        ${this.entities.map(
          (entity) => html`
            <div class="entity-card" @click=${() => this.handleViewEntity(entity)}>
              <div class="entity-header">
                <div>
                  <div class="entity-name">${entity.name}</div>
                  <div class="entity-method">${entity.extraction_method}</div>
                </div>
                <km-status-badge
                  type="entity-type"
                  status=${entity.entity_type}
                ></km-status-badge>
              </div>
              <div class="entity-confidence">
                <span>Confidence:</span>
                <div class="confidence-bar">
                  <div
                    class="confidence-fill"
                    style="width: ${entity.confidence_score * 100}%"
                  ></div>
                </div>
                <span>${(entity.confidence_score * 100).toFixed(0)}%</span>
              </div>
              <div class="entity-date">
                Found on ${this.formatDate(entity.created_at)}
              </div>
            </div>
          `
        )}
      </div>

      <km-pagination
        .page=${this.page}
        .total=${this.total}
        .pageSize=${this.pageSize}
        .pages=${this.pages}
        @page-change=${this.handlePageChange}
      ></km-pagination>
    `
  }

  render() {
    if (!this.authState?.isAuthenticated) {
      return html`
        <div class="card">
          <div class="card-body">
            <div class="unauthorized">
              <div style="font-size: 3rem; margin-bottom: 1rem;">🔒</div>
              <p>Please log in to browse entities.</p>
            </div>
          </div>
        </div>
      `
    }

    return html`
      <div class="card">
        <div class="card-header">
          <h2>Extracted Entities</h2>
          <span class="badge">${this.total} total</span>
        </div>
        <div class="card-body">
          ${this.error ? html`<div class="error">${this.error}</div>` : null}

          <div class="toolbar">
            <input
              type="text"
              class="search-input"
              placeholder="Search entities by name..."
              .value=${this.searchQuery}
              @input=${this.handleSearchInput}
            />
            <select
              class="filter-select"
              .value=${this.typeFilter}
              @change=${this.handleTypeFilterChange}
            >
              <option value="">All Types</option>
              ${Object.entries(ENTITY_TYPE_LABELS).map(
                ([value, label]) =>
                  html`<option value=${value}>${label}</option>`
              )}
            </select>
          </div>

          ${this.isLoading
            ? html`<div class="loading">Loading entities...</div>`
            : this.renderEntityGrid()}
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'entity-explorer': EntityExplorer
  }
}
