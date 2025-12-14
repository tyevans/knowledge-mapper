import { LitElement, html, css } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import { authStore, type AuthState } from '../../auth'
import { apiClient } from '../../api/client'
import type {
  ExtractedEntityDetail,
  EntityRelationshipResponse,
  PaginatedResponse,
} from '../../api/scraping-types'
import { EXTRACTION_METHOD_LABELS } from '../../api/scraping-types'
import '../shared/km-status-badge'
import '../shared/km-pagination'
import '../shared/km-empty-state'

/**
 * Entity Detail Component
 *
 * Displays detailed information about an extracted entity including relationships.
 *
 * @fires back - When user clicks back button
 * @fires view-entity - When user clicks to view a related entity
 * @fires view-graph - When user clicks to view the knowledge graph
 */
@customElement('entity-detail')
export class EntityDetail extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .back-link {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      color: #4b5563;
      text-decoration: none;
      font-size: 0.875rem;
      margin-bottom: 1rem;
      cursor: pointer;
    }

    .back-link:hover {
      color: #111827;
      text-decoration: underline;
    }

    .card {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
      overflow: hidden;
      margin-bottom: 1.5rem;
    }

    .card-header {
      background: #1f2937;
      color: white;
      padding: 1.5rem;
    }

    .header-content {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
    }

    .entity-name {
      margin: 0 0 0.5rem 0;
      font-size: 1.5rem;
    }

    .entity-meta {
      display: flex;
      align-items: center;
      gap: 1rem;
      flex-wrap: wrap;
    }

    .header-actions {
      display: flex;
      gap: 0.5rem;
    }

    .graph-btn {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 1rem;
      background: rgba(255, 255, 255, 0.1);
      border: none;
      border-radius: 0.375rem;
      color: white;
      font-size: 0.875rem;
      cursor: pointer;
      transition: background 0.2s;
    }

    .graph-btn:hover {
      background: rgba(255, 255, 255, 0.2);
    }

    .confidence-display {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.875rem;
      opacity: 0.9;
    }

    .confidence-bar {
      width: 80px;
      height: 6px;
      background: rgba(255, 255, 255, 0.2);
      border-radius: 3px;
      overflow: hidden;
    }

    .confidence-fill {
      height: 100%;
      background: #10b981;
    }

    .card-body {
      padding: 1.5rem;
    }

    .section-title {
      font-size: 1rem;
      font-weight: 600;
      color: #374151;
      margin: 0 0 1rem 0;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid #e5e7eb;
    }

    .info-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 1rem;
    }

    .info-item {
      font-size: 0.875rem;
    }

    .info-label {
      color: #6b7280;
      margin-bottom: 0.25rem;
    }

    .info-value {
      color: #1f2937;
      font-weight: 500;
    }

    .description {
      font-size: 0.875rem;
      color: #4b5563;
      line-height: 1.5;
      margin-bottom: 1.5rem;
    }

    .properties-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }

    .properties-table th,
    .properties-table td {
      padding: 0.75rem 1rem;
      text-align: left;
      border-bottom: 1px solid #e5e7eb;
    }

    .properties-table th {
      background: #f9fafb;
      font-weight: 600;
      color: #374151;
      width: 200px;
    }

    .properties-table td {
      color: #4b5563;
    }

    .source-link {
      color: #1e3a8a;
      text-decoration: none;
      font-size: 0.875rem;
    }

    .source-link:hover {
      text-decoration: underline;
    }

    .relationship-card {
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 0.75rem 1rem;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      margin-bottom: 0.5rem;
      transition: all 0.2s;
    }

    .relationship-card:hover {
      border-color: #1e3a8a;
      background: #f9fafb;
    }

    .relationship-type {
      font-size: 0.75rem;
      background: #e5e7eb;
      padding: 0.25rem 0.5rem;
      border-radius: 0.25rem;
      color: #374151;
      white-space: nowrap;
    }

    .relationship-entity {
      flex: 1;
      min-width: 0;
    }

    .relationship-entity-name {
      font-weight: 500;
      color: #1e3a8a;
      cursor: pointer;
    }

    .relationship-entity-name:hover {
      text-decoration: underline;
    }

    .relationship-entity-type {
      font-size: 0.75rem;
      color: #6b7280;
    }

    .relationship-direction {
      font-size: 1.25rem;
      color: #9ca3af;
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

    .source-text {
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      padding: 1rem;
      font-size: 0.875rem;
      color: #4b5563;
      line-height: 1.6;
      font-style: italic;
    }

    .external-ids {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }

    .external-id {
      background: #dbeafe;
      color: #1e40af;
      padding: 0.25rem 0.5rem;
      border-radius: 0.25rem;
      font-size: 0.75rem;
    }
  `

  @property({ type: String })
  entityId = ''

  @state()
  private authState: AuthState | null = null

  @state()
  private entity: ExtractedEntityDetail | null = null

  @state()
  private relationships: EntityRelationshipResponse[] = []

  @state()
  private isLoading = true

  @state()
  private error: string | null = null

  @state()
  private relationshipsPage = 1

  @state()
  private relationshipsTotal = 0

  @state()
  private relationshipsPages = 1

  private unsubscribe?: () => void
  private readonly pageSize = 10

  connectedCallback(): void {
    super.connectedCallback()
    this.unsubscribe = authStore.subscribe((state) => {
      const wasAuthenticated = this.authState?.isAuthenticated
      this.authState = state

      if (state.isAuthenticated && !wasAuthenticated) {
        this.loadEntity()
      }
    })

    if (this.authState?.isAuthenticated) {
      this.loadEntity()
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.unsubscribe?.()
  }

  updated(changedProperties: Map<string, unknown>): void {
    if (changedProperties.has('entityId') && this.entityId && this.authState?.isAuthenticated) {
      this.loadEntity()
    }
  }

  private async loadEntity(): Promise<void> {
    if (!this.entityId) return

    this.isLoading = true
    this.error = null

    try {
      const response = await apiClient.get<ExtractedEntityDetail>(
        `/api/v1/entities/${this.entityId}`
      )

      if (response.success) {
        this.entity = response.data
        await this.loadRelationships()
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to load entity'
    } finally {
      this.isLoading = false
    }
  }

  private async loadRelationships(): Promise<void> {
    if (!this.entityId) return

    try {
      const params = new URLSearchParams({
        page: this.relationshipsPage.toString(),
        page_size: this.pageSize.toString(),
      })

      const response = await apiClient.get<PaginatedResponse<EntityRelationshipResponse>>(
        `/api/v1/entities/${this.entityId}/relationships?${params.toString()}`
      )

      if (response.success) {
        this.relationships = response.data.items
        this.relationshipsTotal = response.data.total
        this.relationshipsPages = response.data.pages
      }
    } catch {
      // Silent fail for relationships
    }
  }

  private handleRelationshipsPageChange(e: CustomEvent): void {
    this.relationshipsPage = e.detail.page
    this.loadRelationships()
  }

  private handleBack(): void {
    this.dispatchEvent(new CustomEvent('back', { bubbles: true, composed: true }))
  }

  private handleViewGraph(): void {
    this.dispatchEvent(
      new CustomEvent('view-graph', {
        detail: { entityId: this.entityId },
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleViewEntity(entityId: string): void {
    this.dispatchEvent(
      new CustomEvent('view-entity', {
        detail: { entityId },
        bubbles: true,
        composed: true,
      })
    )
  }

  private formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleString()
  }

  private getMethodLabel(method: string): string {
    return EXTRACTION_METHOD_LABELS[method as keyof typeof EXTRACTION_METHOD_LABELS] || method
  }

  private renderProperties() {
    if (!this.entity?.properties || Object.keys(this.entity.properties).length === 0) {
      return null
    }

    return html`
      <div class="card">
        <div class="card-body">
          <h3 class="section-title">Properties</h3>
          <table class="properties-table">
            <tbody>
              ${Object.entries(this.entity.properties).map(
                ([key, value]) => html`
                  <tr>
                    <th>${key}</th>
                    <td>${typeof value === 'object' ? JSON.stringify(value) : String(value)}</td>
                  </tr>
                `
              )}
            </tbody>
          </table>
        </div>
      </div>
    `
  }

  private renderRelationships() {
    const relationships = this.relationships ?? []
    return html`
      <div class="card">
        <div class="card-body">
          <h3 class="section-title">Relationships (${this.relationshipsTotal})</h3>

          ${relationships.length === 0
            ? html`
                <km-empty-state
                  icon="🔗"
                  title="No relationships found"
                  message="This entity has no known relationships with other entities."
                ></km-empty-state>
              `
            : html`
                ${relationships.map((rel) => {
                  const isSource = rel.source_entity_id === this.entityId
                  const relatedEntityId = isSource ? rel.target_entity_id : rel.source_entity_id
                  const relatedEntityName = isSource
                    ? rel.target_entity_name
                    : rel.source_entity_name
                  const relatedEntityType = isSource
                    ? rel.target_entity_type
                    : rel.source_entity_type

                  return html`
                    <div class="relationship-card">
                      <span class="relationship-direction">${isSource ? '→' : '←'}</span>
                      <span class="relationship-type">${rel.relationship_type}</span>
                      <div class="relationship-entity">
                        <span
                          class="relationship-entity-name"
                          @click=${() => this.handleViewEntity(relatedEntityId)}
                        >
                          ${relatedEntityName || relatedEntityId}
                        </span>
                        ${relatedEntityType
                          ? html`
                              <div class="relationship-entity-type">
                                <km-status-badge
                                  type="entity-type"
                                  status=${relatedEntityType}
                                ></km-status-badge>
                              </div>
                            `
                          : null}
                      </div>
                      <div class="confidence-display">
                        ${(rel.confidence_score * 100).toFixed(0)}%
                      </div>
                    </div>
                  `
                })}

                ${this.relationshipsTotal > this.pageSize
                  ? html`
                      <km-pagination
                        .page=${this.relationshipsPage}
                        .total=${this.relationshipsTotal}
                        .pageSize=${this.pageSize}
                        .pages=${this.relationshipsPages}
                        @page-change=${this.handleRelationshipsPageChange}
                      ></km-pagination>
                    `
                  : null}
              `}
        </div>
      </div>
    `
  }

  render() {
    if (!this.authState?.isAuthenticated) {
      return html`
        <div class="card">
          <div class="loading">Please log in to view entity details.</div>
        </div>
      `
    }

    if (this.isLoading) {
      return html`
        <span class="back-link" @click=${this.handleBack}>&larr; Back to Entities</span>
        <div class="card">
          <div class="loading">Loading entity details...</div>
        </div>
      `
    }

    if (!this.entity) {
      return html`
        <span class="back-link" @click=${this.handleBack}>&larr; Back to Entities</span>
        <div class="card">
          <div class="error">Entity not found</div>
        </div>
      `
    }

    return html`
      <span class="back-link" @click=${this.handleBack}>&larr; Back to Entities</span>

      <div class="card">
        <div class="card-header">
          ${this.error ? html`<div class="error">${this.error}</div>` : null}

          <div class="header-content">
            <div>
              <h1 class="entity-name">${this.entity.name}</h1>
              <div class="entity-meta">
                <km-status-badge
                  type="entity-type"
                  status=${this.entity.entity_type}
                ></km-status-badge>
                <div class="confidence-display">
                  <span>Confidence:</span>
                  <div class="confidence-bar">
                    <div
                      class="confidence-fill"
                      style="width: ${this.entity.confidence_score * 100}%"
                    ></div>
                  </div>
                  <span>${(this.entity.confidence_score * 100).toFixed(0)}%</span>
                </div>
              </div>
            </div>
            <div class="header-actions">
              <button class="graph-btn" @click=${this.handleViewGraph}>
                View in Graph
              </button>
            </div>
          </div>
        </div>

        <div class="card-body">
          ${this.entity.description
            ? html`<p class="description">${this.entity.description}</p>`
            : null}

          <div class="info-grid">
            <div class="info-item">
              <div class="info-label">Extraction Method</div>
              <div class="info-value">${this.getMethodLabel(this.entity.extraction_method)}</div>
            </div>
            <div class="info-item">
              <div class="info-label">Normalized Name</div>
              <div class="info-value">${this.entity.normalized_name}</div>
            </div>
            <div class="info-item">
              <div class="info-label">Created</div>
              <div class="info-value">${this.formatDate(this.entity.created_at)}</div>
            </div>
            <div class="info-item">
              <div class="info-label">Graph Status</div>
              <div class="info-value">
                ${this.entity.synced_to_neo4j ? 'Synced to Neo4j' : 'Pending sync'}
              </div>
            </div>
          </div>

          ${Object.keys(this.entity.external_ids).length > 0
            ? html`
                <div style="margin-top: 1rem;">
                  <div class="info-label">External IDs</div>
                  <div class="external-ids">
                    ${Object.entries(this.entity.external_ids).map(
                      ([key, value]) =>
                        html`<span class="external-id">${key}: ${value}</span>`
                    )}
                  </div>
                </div>
              `
            : null}

          ${this.entity.source_text
            ? html`
                <div style="margin-top: 1.5rem;">
                  <div class="info-label" style="margin-bottom: 0.5rem;">Source Text</div>
                  <div class="source-text">"${this.entity.source_text}"</div>
                </div>
              `
            : null}
        </div>
      </div>

      ${this.renderProperties()}
      ${this.renderRelationships()}
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'entity-detail': EntityDetail
  }
}
