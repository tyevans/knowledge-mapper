import { LitElement, html, css } from 'lit'
import { customElement, state, property } from 'lit/decorators.js'
import { apiClient } from '../../api/client'
import type {
  MergeHistoryItem,
  MergeHistoryListResponse,
  MergeEventType,
  UndoMergeRequest,
  UndoMergeResponse,
} from '../../api/types'
import '../shared/km-pagination'
import '../shared/km-status-badge'
import '../shared/km-empty-state'

/** Event type labels */
const EVENT_TYPE_LABELS: Record<MergeEventType, string> = {
  entities_merged: 'Entities Merged',
  merge_undone: 'Merge Undone',
  entity_split: 'Entity Split',
}

/** Event type colors */
const EVENT_TYPE_COLORS: Record<MergeEventType, 'green' | 'yellow' | 'blue'> = {
  entities_merged: 'green',
  merge_undone: 'yellow',
  entity_split: 'blue',
}

/** Event type icons */
const EVENT_TYPE_ICONS: Record<MergeEventType, string> = {
  entities_merged: '\u{1F517}',
  merge_undone: '\u{21A9}',
  entity_split: '\u{2702}',
}

/**
 * Merge history component
 *
 * Timeline of merge operations with:
 * - Filter by entity, date range, event type
 * - Undo capability for recent merges
 * - Visual timeline representation
 *
 * @element km-merge-history
 * @fires view-entity - When user wants to view entity details
 * @fires undo-complete - When undo operation completes
 */
@customElement('km-merge-history')
export class KmMergeHistory extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .history-container {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
      overflow: hidden;
    }

    .history-header {
      padding: 1rem 1.5rem;
      background: #1f2937;
      color: white;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .history-title {
      font-size: 1.125rem;
      font-weight: 600;
      margin: 0;
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

    .filter-select,
    .filter-input {
      padding: 0.5rem;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      background: white;
    }

    .filter-select:focus,
    .filter-input:focus {
      outline: none;
      border-color: #1e3a8a;
      box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
    }

    .history-body {
      padding: 1.5rem;
    }

    .timeline {
      position: relative;
      padding-left: 2rem;
    }

    .timeline::before {
      content: '';
      position: absolute;
      left: 0.75rem;
      top: 0;
      bottom: 0;
      width: 2px;
      background: #e5e7eb;
    }

    .timeline-item {
      position: relative;
      padding-bottom: 1.5rem;
    }

    .timeline-item:last-child {
      padding-bottom: 0;
    }

    .timeline-icon {
      position: absolute;
      left: -1.75rem;
      top: 0;
      width: 1.5rem;
      height: 1.5rem;
      background: white;
      border: 2px solid #e5e7eb;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.75rem;
      z-index: 1;
    }

    .timeline-icon.merged {
      border-color: #10b981;
      color: #10b981;
    }

    .timeline-icon.undone {
      border-color: #f59e0b;
      color: #f59e0b;
    }

    .timeline-icon.split {
      border-color: #3b82f6;
      color: #3b82f6;
    }

    .timeline-content {
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 0.5rem;
      overflow: hidden;
    }

    .timeline-header {
      padding: 0.75rem 1rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      border-bottom: 1px solid #e5e7eb;
    }

    .timeline-header-left {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .event-type-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      padding: 0.25rem 0.5rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
    }

    .event-type-badge.green {
      background: #d1fae5;
      color: #065f46;
    }

    .event-type-badge.yellow {
      background: #fef3c7;
      color: #92400e;
    }

    .event-type-badge.blue {
      background: #dbeafe;
      color: #1e40af;
    }

    .timeline-date {
      font-size: 0.75rem;
      color: #6b7280;
    }

    .timeline-body {
      padding: 1rem;
    }

    .entity-info {
      margin-bottom: 0.75rem;
    }

    .entity-label {
      font-size: 0.75rem;
      color: #6b7280;
      margin-bottom: 0.25rem;
    }

    .entity-name {
      font-weight: 500;
      color: #1e3a8a;
      cursor: pointer;
    }

    .entity-name:hover {
      text-decoration: underline;
    }

    .affected-entities {
      font-size: 0.875rem;
      color: #374151;
    }

    .affected-entities-list {
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem;
      margin-top: 0.25rem;
    }

    .affected-entity-badge {
      font-size: 0.75rem;
      padding: 0.125rem 0.375rem;
      background: #e5e7eb;
      border-radius: 0.25rem;
      color: #374151;
      cursor: pointer;
    }

    .affected-entity-badge:hover {
      background: #d1d5db;
    }

    .merge-reason {
      font-size: 0.75rem;
      color: #6b7280;
      margin-top: 0.5rem;
    }

    .timeline-footer {
      padding: 0.75rem 1rem;
      background: white;
      border-top: 1px solid #e5e7eb;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .performer {
      font-size: 0.75rem;
      color: #6b7280;
    }

    .undo-btn {
      padding: 0.375rem 0.75rem;
      background: white;
      border: 1px solid #f59e0b;
      border-radius: 0.375rem;
      color: #f59e0b;
      font-size: 0.75rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
    }

    .undo-btn:hover:not(:disabled) {
      background: #fef3c7;
    }

    .undo-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .undone-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      font-size: 0.75rem;
      color: #6b7280;
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

    .history-footer {
      padding: 1rem 1.5rem;
      border-top: 1px solid #e5e7eb;
    }

    /* Undo modal */
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }

    .modal {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
      max-width: 400px;
      width: 90%;
    }

    .modal-header {
      padding: 1rem 1.5rem;
      border-bottom: 1px solid #e5e7eb;
    }

    .modal-title {
      font-size: 1rem;
      font-weight: 600;
      margin: 0;
    }

    .modal-body {
      padding: 1.5rem;
    }

    .modal-label {
      font-size: 0.875rem;
      font-weight: 500;
      color: #374151;
      margin-bottom: 0.5rem;
      display: block;
    }

    .modal-textarea {
      width: 100%;
      padding: 0.5rem;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      resize: vertical;
      min-height: 80px;
    }

    .modal-textarea:focus {
      outline: none;
      border-color: #1e3a8a;
      box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
    }

    .modal-footer {
      padding: 1rem 1.5rem;
      border-top: 1px solid #e5e7eb;
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
    }

    .modal-btn {
      padding: 0.5rem 1rem;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
    }

    .modal-btn.cancel {
      background: white;
      border: 1px solid #e5e7eb;
      color: #374151;
    }

    .modal-btn.cancel:hover {
      background: #f9fafb;
    }

    .modal-btn.confirm {
      background: #f59e0b;
      border: 1px solid #f59e0b;
      color: white;
    }

    .modal-btn.confirm:hover:not(:disabled) {
      background: #d97706;
    }

    .modal-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  `

  /** API endpoint for merge history */
  @property({ type: String })
  endpoint = '/api/v1/consolidation/history'

  /** Optional entity ID to filter by */
  @property({ type: String, attribute: 'entity-id' })
  entityId: string | null = null

  @state()
  private items: MergeHistoryItem[] = []

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
  private eventTypeFilter: MergeEventType | '' = ''

  @state()
  private undoModalOpen = false

  @state()
  private selectedUndoItem: MergeHistoryItem | null = null

  @state()
  private undoReason = ''

  @state()
  private isUndoing = false

  connectedCallback(): void {
    super.connectedCallback()
    this.loadHistory()
  }

  private async loadHistory(): Promise<void> {
    this.isLoading = true
    this.error = null

    try {
      const params = new URLSearchParams({
        page: this.page.toString(),
        page_size: this.pageSize.toString(),
      })

      if (this.eventTypeFilter) {
        params.set('event_type', this.eventTypeFilter)
      }

      if (this.entityId) {
        params.set('entity_id', this.entityId)
      }

      const response = await apiClient.get<MergeHistoryListResponse>(
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
      this.error = err instanceof Error ? err.message : 'Failed to load merge history'
    } finally {
      this.isLoading = false
    }
  }

  private handlePageChange(e: CustomEvent): void {
    this.page = e.detail.page
    this.loadHistory()
  }

  private handleEventTypeFilterChange(e: Event): void {
    const select = e.target as HTMLSelectElement
    this.eventTypeFilter = select.value as MergeEventType | ''
    this.page = 1
    this.loadHistory()
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

  private openUndoModal(item: MergeHistoryItem): void {
    this.selectedUndoItem = item
    this.undoReason = ''
    this.undoModalOpen = true
  }

  private closeUndoModal(): void {
    this.undoModalOpen = false
    this.selectedUndoItem = null
    this.undoReason = ''
  }

  private async submitUndo(): Promise<void> {
    if (!this.selectedUndoItem || this.undoReason.length < 5) return

    this.isUndoing = true

    try {
      const request: UndoMergeRequest = {
        reason: this.undoReason,
      }

      const response = await apiClient.post<UndoMergeResponse>(
        `/api/v1/consolidation/undo/${this.selectedUndoItem.event_id}`,
        request
      )

      if (response.success) {
        this.closeUndoModal()
        this.loadHistory()
        this.dispatchEvent(
          new CustomEvent('undo-complete', {
            detail: { undoResponse: response.data },
            bubbles: true,
            composed: true,
          })
        )
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to undo merge'
    } finally {
      this.isUndoing = false
    }
  }

  private formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  private renderTimelineItem(item: MergeHistoryItem) {
    const iconClass =
      item.event_type === 'entities_merged'
        ? 'merged'
        : item.event_type === 'merge_undone'
          ? 'undone'
          : 'split'

    return html`
      <div class="timeline-item">
        <div class="timeline-icon ${iconClass}">
          ${EVENT_TYPE_ICONS[item.event_type]}
        </div>
        <div class="timeline-content">
          <div class="timeline-header">
            <div class="timeline-header-left">
              <span class="event-type-badge ${EVENT_TYPE_COLORS[item.event_type]}">
                ${EVENT_TYPE_LABELS[item.event_type]}
              </span>
              ${item.undone
                ? html`<span class="undone-badge">\u{21A9} Undone</span>`
                : null}
            </div>
            <span class="timeline-date">${this.formatDate(item.performed_at)}</span>
          </div>

          <div class="timeline-body">
            ${item.canonical_entity
              ? html`
                  <div class="entity-info">
                    <div class="entity-label">Canonical Entity</div>
                    <span
                      class="entity-name"
                      @click=${() => this.handleViewEntity(item.canonical_entity!.id)}
                      @keydown=${(e: KeyboardEvent) =>
                        e.key === 'Enter' && this.handleViewEntity(item.canonical_entity!.id)}
                      tabindex="0"
                      role="button"
                    >
                      ${item.canonical_entity.name}
                    </span>
                  </div>
                `
              : null}

            <div class="affected-entities">
              <span>Affected entities (${item.affected_entity_ids.length}):</span>
              <div class="affected-entities-list">
                ${item.affected_entity_ids.slice(0, 5).map(
                  (id) => html`
                    <span
                      class="affected-entity-badge"
                      @click=${() => this.handleViewEntity(id)}
                      title=${id}
                    >
                      ${id.slice(0, 8)}...
                    </span>
                  `
                )}
                ${item.affected_entity_ids.length > 5
                  ? html`<span class="affected-entity-badge">+${item.affected_entity_ids.length - 5} more</span>`
                  : null}
              </div>
            </div>

            ${item.merge_reason
              ? html`<div class="merge-reason">Reason: ${item.merge_reason}</div>`
              : null}
          </div>

          <div class="timeline-footer">
            <span class="performer">
              ${item.performed_by_name || 'System'}
            </span>
            ${item.can_undo && !item.undone
              ? html`
                  <button
                    class="undo-btn"
                    @click=${() => this.openUndoModal(item)}
                  >
                    Undo Merge
                  </button>
                `
              : item.undone && item.undone_at
                ? html`
                    <span class="timeline-date">
                      Undone: ${this.formatDate(item.undone_at)}
                      ${item.undo_reason ? `(${item.undo_reason})` : ''}
                    </span>
                  `
                : null}
          </div>
        </div>
      </div>
    `
  }

  private renderUndoModal() {
    if (!this.undoModalOpen || !this.selectedUndoItem) return null

    return html`
      <div
        class="modal-overlay"
        @click=${(e: Event) => e.target === e.currentTarget && this.closeUndoModal()}
      >
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="undo-modal-title">
          <div class="modal-header">
            <h3 class="modal-title" id="undo-modal-title">Undo Merge</h3>
          </div>
          <div class="modal-body">
            <p style="margin-bottom: 1rem; color: #374151; font-size: 0.875rem;">
              Are you sure you want to undo this merge? This will restore the merged entities
              as separate canonical entities.
            </p>
            <label class="modal-label" for="undo-reason">Reason for undoing (min 5 characters)</label>
            <textarea
              id="undo-reason"
              class="modal-textarea"
              .value=${this.undoReason}
              @input=${(e: Event) => (this.undoReason = (e.target as HTMLTextAreaElement).value)}
              placeholder="Explain why you are undoing this merge..."
            ></textarea>
          </div>
          <div class="modal-footer">
            <button class="modal-btn cancel" @click=${this.closeUndoModal}>Cancel</button>
            <button
              class="modal-btn confirm"
              @click=${this.submitUndo}
              ?disabled=${this.undoReason.length < 5 || this.isUndoing}
            >
              ${this.isUndoing ? 'Undoing...' : 'Confirm Undo'}
            </button>
          </div>
        </div>
      </div>
    `
  }

  render() {
    return html`
      <div class="history-container">
        <div class="history-header">
          <h2 class="history-title">Merge History</h2>
        </div>

        <div class="toolbar">
          <div class="filters">
            <select
              class="filter-select"
              .value=${this.eventTypeFilter}
              @change=${this.handleEventTypeFilterChange}
              aria-label="Filter by event type"
            >
              <option value="">All Event Types</option>
              ${Object.entries(EVENT_TYPE_LABELS).map(
                ([value, label]) =>
                  html`<option value=${value}>${label}</option>`
              )}
            </select>
          </div>
        </div>

        <div class="history-body">
          ${this.error ? html`<div class="error">${this.error}</div>` : null}

          ${this.isLoading
            ? html`<div class="loading">Loading merge history...</div>`
            : this.items.length === 0
              ? html`
                  <km-empty-state
                    icon="\u{1F4DC}"
                    title="No merge history"
                    message="No merge operations have been performed yet."
                  ></km-empty-state>
                `
              : html`
                  <div class="timeline" role="list">
                    ${this.items.map((item) => this.renderTimelineItem(item))}
                  </div>
                `}
        </div>

        ${this.total > this.pageSize
          ? html`
              <div class="history-footer">
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

      ${this.renderUndoModal()}
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'km-merge-history': KmMergeHistory
  }
}
