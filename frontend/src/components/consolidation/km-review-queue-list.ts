import { LitElement, html, css } from 'lit'
import { customElement, state, property } from 'lit/decorators.js'
import { apiClient } from '../../api/client'
import type {
  ReviewQueueItem,
  ReviewQueueListResponse,
  ReviewQueueStats,
  ReviewStatus,
  ReviewDecisionRequest,
  ReviewDecisionResponse,
} from '../../api/types'
import '../shared/km-pagination'
import '../shared/km-status-badge'
import '../shared/km-empty-state'
import './km-confidence-score'
import './km-merge-candidate-card'

/** Status labels for display */
const STATUS_LABELS: Record<ReviewStatus, string> = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
  deferred: 'Deferred',
  expired: 'Expired',
}

/** Status colors for badges */
const STATUS_COLORS: Record<ReviewStatus, 'gray' | 'blue' | 'green' | 'yellow' | 'red' | 'purple'> = {
  pending: 'yellow',
  approved: 'green',
  rejected: 'red',
  deferred: 'purple',
  expired: 'gray',
}

/**
 * Review queue list component
 *
 * List of pending merge reviews with:
 * - Filtering by status, entity type, confidence
 * - Sorting and pagination
 * - Quick actions for review decisions
 *
 * @element km-review-queue-list
 * @fires view-entity - When user wants to view entity details
 */
@customElement('km-review-queue-list')
export class KmReviewQueueList extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .queue-container {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
      overflow: hidden;
    }

    .queue-header {
      padding: 1rem 1.5rem;
      background: #1f2937;
      color: white;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .queue-title {
      font-size: 1.125rem;
      font-weight: 600;
      margin: 0;
    }

    .queue-stats {
      display: flex;
      gap: 1rem;
    }

    .stat-item {
      text-align: center;
    }

    .stat-value {
      font-size: 1.25rem;
      font-weight: 700;
    }

    .stat-label {
      font-size: 0.75rem;
      opacity: 0.8;
    }

    .toolbar {
      padding: 1rem 1.5rem;
      background: #f9fafb;
      border-bottom: 1px solid #e5e7eb;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
    }

    .filters {
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
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

    .refresh-btn {
      padding: 0.5rem 1rem;
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      cursor: pointer;
      transition: all 0.2s;
    }

    .refresh-btn:hover {
      background: #f9fafb;
      border-color: #d1d5db;
    }

    .queue-body {
      padding: 1.5rem;
    }

    .queue-list {
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }

    .queue-item {
      border: 1px solid #e5e7eb;
      border-radius: 0.5rem;
      overflow: hidden;
      transition: box-shadow 0.2s;
    }

    .queue-item:hover {
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }

    .item-header {
      padding: 0.75rem 1rem;
      background: #f9fafb;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      border-bottom: 1px solid #e5e7eb;
    }

    .item-entities {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex-wrap: wrap;
    }

    .entity-link {
      font-weight: 500;
      color: #1e3a8a;
      cursor: pointer;
      transition: color 0.2s;
    }

    .entity-link:hover {
      text-decoration: underline;
    }

    .merge-arrow {
      color: #9ca3af;
    }

    .item-meta {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .item-body {
      padding: 1rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
    }

    .item-scores {
      display: flex;
      gap: 1rem;
      flex-wrap: wrap;
    }

    .score-item {
      display: flex;
      flex-direction: column;
      gap: 0.125rem;
    }

    .score-label {
      font-size: 0.625rem;
      color: #6b7280;
      text-transform: uppercase;
    }

    .score-value {
      font-size: 0.875rem;
      font-weight: 500;
    }

    .item-actions {
      display: flex;
      gap: 0.5rem;
    }

    .action-btn {
      padding: 0.375rem 0.75rem;
      border-radius: 0.25rem;
      font-size: 0.75rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
      border: 1px solid;
    }

    .action-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .action-btn.approve {
      background: #1e3a8a;
      border-color: #1e3a8a;
      color: white;
    }

    .action-btn.approve:hover:not(:disabled) {
      background: #1e40af;
    }

    .action-btn.reject {
      background: white;
      border-color: #ef4444;
      color: #ef4444;
    }

    .action-btn.reject:hover:not(:disabled) {
      background: #fee2e2;
    }

    .action-btn.defer {
      background: white;
      border-color: #e5e7eb;
      color: #374151;
    }

    .action-btn.defer:hover:not(:disabled) {
      background: #f9fafb;
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

    .item-date {
      font-size: 0.75rem;
      color: #6b7280;
    }

    .priority-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      padding: 0.125rem 0.375rem;
      background: #fef3c7;
      color: #92400e;
      border-radius: 0.25rem;
      font-size: 0.625rem;
      font-weight: 500;
    }

    .priority-badge.high {
      background: #fee2e2;
      color: #991b1b;
    }

    .queue-footer {
      padding: 1rem 1.5rem;
      border-top: 1px solid #e5e7eb;
    }
  `

  /** API endpoint for the review queue */
  @property({ type: String })
  endpoint = '/api/v1/consolidation/review-queue'

  @state()
  private items: ReviewQueueItem[] = []

  @state()
  private stats: ReviewQueueStats | null = null

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
  private statusFilter: ReviewStatus | '' = 'pending'

  @state()
  private sortBy: 'priority' | 'confidence' | 'created_at' = 'priority'

  @state()
  private processingItems: Set<string> = new Set()

  connectedCallback(): void {
    super.connectedCallback()
    this.loadQueue()
    this.loadStats()
  }

  private async loadQueue(): Promise<void> {
    this.isLoading = true
    this.error = null

    try {
      const params = new URLSearchParams({
        page: this.page.toString(),
        page_size: this.pageSize.toString(),
        sort_by: this.sortBy,
      })

      if (this.statusFilter) {
        params.set('status_filter', this.statusFilter)
      }

      const response = await apiClient.get<ReviewQueueListResponse>(
        `${this.endpoint}?${params.toString()}`
      )

      if (response.success) {
        this.items = response.data.items
        this.total = response.data.total
        this.pages = response.data.pages
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to load review queue'
    } finally {
      this.isLoading = false
    }
  }

  private async loadStats(): Promise<void> {
    try {
      const response = await apiClient.get<ReviewQueueStats>(`${this.endpoint}/stats`)

      if (response.success) {
        this.stats = response.data
      }
    } catch (err) {
      console.error('Failed to load stats:', err)
    }
  }

  private async submitDecision(
    itemId: string,
    decision: 'approve' | 'reject' | 'defer',
    selectCanonical?: string
  ): Promise<void> {
    this.processingItems.add(itemId)
    this.requestUpdate()

    try {
      const request: ReviewDecisionRequest = {
        decision,
        select_canonical: selectCanonical,
      }

      const response = await apiClient.post<ReviewDecisionResponse>(
        `${this.endpoint}/${itemId}/decide`,
        request
      )

      if (response.success) {
        // Remove item from list or reload
        this.loadQueue()
        this.loadStats()
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to submit decision'
    } finally {
      this.processingItems.delete(itemId)
      this.requestUpdate()
    }
  }

  private handlePageChange(e: CustomEvent): void {
    this.page = e.detail.page
    this.loadQueue()
  }

  private handleStatusFilterChange(e: Event): void {
    const select = e.target as HTMLSelectElement
    this.statusFilter = select.value as ReviewStatus | ''
    this.page = 1
    this.loadQueue()
  }

  private handleSortChange(e: Event): void {
    const select = e.target as HTMLSelectElement
    this.sortBy = select.value as 'priority' | 'confidence' | 'created_at'
    this.page = 1
    this.loadQueue()
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
    return new Date(dateStr).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  private renderStats() {
    if (!this.stats) return null

    return html`
      <div class="queue-stats">
        <div class="stat-item">
          <div class="stat-value">${this.stats.total_pending}</div>
          <div class="stat-label">Pending</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">${this.stats.total_approved}</div>
          <div class="stat-label">Approved</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">${this.stats.total_rejected}</div>
          <div class="stat-label">Rejected</div>
        </div>
      </div>
    `
  }

  private renderQueueItem(item: ReviewQueueItem) {
    const isProcessing = this.processingItems.has(item.id)
    const isPending = item.status === 'pending'

    return html`
      <div class="queue-item" role="article">
        <div class="item-header">
          <div class="item-entities">
            <span
              class="entity-link"
              @click=${() => this.handleViewEntity(item.entity_a.id)}
              @keydown=${(e: KeyboardEvent) => e.key === 'Enter' && this.handleViewEntity(item.entity_a.id)}
              tabindex="0"
              role="button"
            >
              ${item.entity_a.name}
            </span>
            <span class="merge-arrow" aria-hidden="true">\u{2194}</span>
            <span
              class="entity-link"
              @click=${() => this.handleViewEntity(item.entity_b.id)}
              @keydown=${(e: KeyboardEvent) => e.key === 'Enter' && this.handleViewEntity(item.entity_b.id)}
              tabindex="0"
              role="button"
            >
              ${item.entity_b.name}
            </span>
          </div>
          <div class="item-meta">
            ${item.review_priority >= 0.8
              ? html`<span class="priority-badge high">High Priority</span>`
              : item.review_priority >= 0.5
                ? html`<span class="priority-badge">Priority</span>`
                : null}
            <km-status-badge
              type="custom"
              status=${item.status}
              variant=${STATUS_COLORS[item.status]}
              label=${STATUS_LABELS[item.status]}
            ></km-status-badge>
          </div>
        </div>

        <div class="item-body">
          <div class="item-scores">
            <div class="score-item">
              <span class="score-label">Confidence</span>
              <km-confidence-score
                .score=${item.confidence}
                size="small"
              ></km-confidence-score>
            </div>
            <div class="score-item">
              <span class="score-label">Type</span>
              <span class="score-value">${item.entity_a.entity_type}</span>
            </div>
            <div class="score-item">
              <span class="score-label">Created</span>
              <span class="item-date">${this.formatDate(item.created_at)}</span>
            </div>
          </div>

          ${isPending
            ? html`
                <div class="item-actions">
                  <button
                    class="action-btn defer"
                    @click=${() => this.submitDecision(item.id, 'defer')}
                    ?disabled=${isProcessing}
                    aria-busy=${isProcessing}
                  >
                    Defer
                  </button>
                  <button
                    class="action-btn reject"
                    @click=${() => this.submitDecision(item.id, 'reject')}
                    ?disabled=${isProcessing}
                    aria-busy=${isProcessing}
                  >
                    Reject
                  </button>
                  <button
                    class="action-btn approve"
                    @click=${() => this.submitDecision(item.id, 'approve', item.entity_a.id)}
                    ?disabled=${isProcessing}
                    aria-busy=${isProcessing}
                  >
                    Approve
                  </button>
                </div>
              `
            : html`
                <div class="item-actions">
                  ${item.reviewed_at
                    ? html`<span class="item-date">Reviewed: ${this.formatDate(item.reviewed_at)}</span>`
                    : null}
                </div>
              `}
        </div>
      </div>
    `
  }

  render() {
    return html`
      <div class="queue-container">
        <div class="queue-header">
          <h2 class="queue-title">Review Queue</h2>
          ${this.renderStats()}
        </div>

        <div class="toolbar">
          <div class="filters">
            <select
              class="filter-select"
              .value=${this.statusFilter}
              @change=${this.handleStatusFilterChange}
              aria-label="Filter by status"
            >
              <option value="">All Statuses</option>
              ${Object.entries(STATUS_LABELS).map(
                ([value, label]) =>
                  html`<option value=${value}>${label}</option>`
              )}
            </select>

            <select
              class="filter-select"
              .value=${this.sortBy}
              @change=${this.handleSortChange}
              aria-label="Sort by"
            >
              <option value="priority">Sort by Priority</option>
              <option value="confidence">Sort by Confidence</option>
              <option value="created_at">Sort by Date</option>
            </select>
          </div>

          <button class="refresh-btn" @click=${() => this.loadQueue()}>
            Refresh
          </button>
        </div>

        <div class="queue-body">
          ${this.error ? html`<div class="error">${this.error}</div>` : null}

          ${this.isLoading
            ? html`<div class="loading">Loading review queue...</div>`
            : this.items.length === 0
              ? html`
                  <km-empty-state
                    icon="\u{2705}"
                    title="No items in queue"
                    message=${this.statusFilter === 'pending'
                      ? 'Great job! All merge candidates have been reviewed.'
                      : `No ${this.statusFilter || ''} items found.`}
                  ></km-empty-state>
                `
              : html`
                  <div class="queue-list" role="list">
                    ${this.items.map((item) => this.renderQueueItem(item))}
                  </div>
                `}
        </div>

        ${this.total > this.pageSize
          ? html`
              <div class="queue-footer">
                <km-pagination
                  .page=${this.page}
                  .total=${this.total}
                  .pageSize=${this.pageSize}
                  .pages=${this.pages}
                  @page-change=${this.handlePageChange}
                ></km-pagination>
              </div>
            `
          : null}
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'km-review-queue-list': KmReviewQueueList
  }
}
