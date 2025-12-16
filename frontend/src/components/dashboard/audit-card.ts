import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { apiClient } from '../../api/client'
import type { AuditLogResponse, AuditEvent, ApiError } from '../../api/types'

/**
 * Event type to color/icon mapping
 */
const EVENT_TYPE_CONFIG: Record<string, { color: string; icon: string }> = {
  ScrapingJobCreated: { color: '#10b981', icon: '+' },
  ScrapingJobStarted: { color: '#3b82f6', icon: '\u25B6' },
  ScrapingJobCompleted: { color: '#10b981', icon: '\u2713' },
  ScrapingJobFailed: { color: '#ef4444', icon: '\u2717' },
  ScrapingJobCancelled: { color: '#f59e0b', icon: '\u2718' },
  ScrapingJobPaused: { color: '#8b5cf6', icon: '\u275A\u275A' },
  ScrapingJobResumed: { color: '#3b82f6', icon: '\u25B6' },
  PageScraped: { color: '#06b6d4', icon: '\u25CF' },
  PageScrapingFailed: { color: '#ef4444', icon: '\u2717' },
  EntityExtracted: { color: '#8b5cf6', icon: '\u25C6' },
  EntitiesExtractedBatch: { color: '#8b5cf6', icon: '\u25C6\u25C6' },
  EntityRelationshipCreated: { color: '#ec4899', icon: '\u2194' },
  ExtractionFailed: { color: '#ef4444', icon: '\u2717' },
  EntitySyncedToNeo4j: { color: '#22c55e', icon: '\u21D2' },
  RelationshipSyncedToNeo4j: { color: '#22c55e', icon: '\u21D2' },
  Neo4jSyncFailed: { color: '#ef4444', icon: '\u2717' },
}

/**
 * Audit Card Component
 *
 * Displays recent domain events from the event store as an audit log.
 */
@customElement('audit-card')
export class AuditCard extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .card {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
      overflow: hidden;
    }

    .header {
      padding: 1rem 1.5rem;
      border-bottom: 1px solid #e5e7eb;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .title {
      font-size: 1.125rem;
      font-weight: 600;
      color: #1f2937;
      margin: 0;
    }

    .subtitle {
      font-size: 0.75rem;
      color: #6b7280;
      margin-top: 0.25rem;
    }

    .refresh-btn {
      background: none;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      padding: 0.5rem;
      cursor: pointer;
      color: #6b7280;
      transition: all 0.2s;
    }

    .refresh-btn:hover {
      background: #f3f4f6;
      color: #374151;
    }

    .refresh-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .refresh-btn.spinning {
      animation: spin 1s linear infinite;
    }

    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }

    .content {
      padding: 0;
      max-height: 400px;
      overflow-y: auto;
    }

    .event-list {
      list-style: none;
      margin: 0;
      padding: 0;
    }

    .event-item {
      display: flex;
      align-items: flex-start;
      gap: 0.75rem;
      padding: 0.75rem 1.5rem;
      border-bottom: 1px solid #f3f4f6;
      transition: background 0.2s;
    }

    .event-item:hover {
      background: #f9fafb;
    }

    .event-item:last-child {
      border-bottom: none;
    }

    .event-icon {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.75rem;
      font-weight: bold;
      flex-shrink: 0;
      color: white;
    }

    .event-content {
      flex: 1;
      min-width: 0;
    }

    .event-summary {
      font-size: 0.875rem;
      color: #374151;
      margin: 0;
      line-height: 1.4;
    }

    .event-meta {
      display: flex;
      gap: 0.75rem;
      margin-top: 0.25rem;
      font-size: 0.75rem;
      color: #9ca3af;
    }

    .event-type {
      font-family: ui-monospace, monospace;
      background: #f3f4f6;
      padding: 0.125rem 0.375rem;
      border-radius: 0.25rem;
    }

    .empty-state {
      padding: 2rem;
      text-align: center;
      color: #6b7280;
    }

    .empty-icon {
      font-size: 2rem;
      margin-bottom: 0.5rem;
    }

    .error-state {
      padding: 1.5rem;
      background: #fef2f2;
      color: #991b1b;
      text-align: center;
    }

    .loading-state {
      padding: 2rem;
      text-align: center;
      color: #6b7280;
    }

    .loading-spinner {
      width: 24px;
      height: 24px;
      border: 2px solid #e5e7eb;
      border-top-color: #3b82f6;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin: 0 auto 0.5rem;
    }

    .footer {
      padding: 0.75rem 1.5rem;
      border-top: 1px solid #e5e7eb;
      background: #f9fafb;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .footer-text {
      font-size: 0.75rem;
      color: #6b7280;
    }

    .view-all-link {
      font-size: 0.75rem;
      color: #3b82f6;
      text-decoration: none;
      cursor: pointer;
    }

    .view-all-link:hover {
      text-decoration: underline;
    }
  `

  @state()
  private loading = true

  @state()
  private error: ApiError | null = null

  @state()
  private auditLog: AuditLogResponse | null = null

  connectedCallback() {
    super.connectedCallback()
    this.fetchAuditEvents()
  }

  private async fetchAuditEvents() {
    this.loading = true
    this.error = null

    const response = await apiClient.get<AuditLogResponse>('/api/v1/audit/events?limit=15')

    if (response.success) {
      this.auditLog = response.data
    } else {
      this.error = response.error
    }

    this.loading = false
  }

  private handleRefresh() {
    this.fetchAuditEvents()
  }

  private getEventConfig(eventType: string) {
    return EVENT_TYPE_CONFIG[eventType] || { color: '#6b7280', icon: '\u25CF' }
  }

  private formatTime(timestamp: string): string {
    const date = new Date(timestamp)
    const now = new Date()
    const diff = now.getTime() - date.getTime()

    // Less than 1 minute
    if (diff < 60000) {
      return 'just now'
    }

    // Less than 1 hour
    if (diff < 3600000) {
      const mins = Math.floor(diff / 60000)
      return `${mins}m ago`
    }

    // Less than 24 hours
    if (diff < 86400000) {
      const hours = Math.floor(diff / 3600000)
      return `${hours}h ago`
    }

    // Show date
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    })
  }

  private renderEvent(event: AuditEvent) {
    const config = this.getEventConfig(event.event_type)

    return html`
      <li class="event-item">
        <div class="event-icon" style="background-color: ${config.color}">
          ${config.icon}
        </div>
        <div class="event-content">
          <p class="event-summary">${event.summary}</p>
          <div class="event-meta">
            <span class="event-type">${event.event_type}</span>
            <span>${this.formatTime(event.occurred_at)}</span>
          </div>
        </div>
      </li>
    `
  }

  render() {
    return html`
      <div class="card">
        <div class="header">
          <div>
            <h2 class="title">Audit Log</h2>
            <p class="subtitle">Recent domain events</p>
          </div>
          <button
            class="refresh-btn ${this.loading ? 'spinning' : ''}"
            @click=${this.handleRefresh}
            ?disabled=${this.loading}
            title="Refresh"
          >
            \u21BB
          </button>
        </div>

        <div class="content">
          ${this.loading
            ? html`
                <div class="loading-state">
                  <div class="loading-spinner"></div>
                  <div>Loading events...</div>
                </div>
              `
            : this.error
              ? html`
                  <div class="error-state">
                    <strong>Error:</strong> ${this.error.message}
                  </div>
                `
              : this.auditLog && this.auditLog.events.length > 0
                ? html`
                    <ul class="event-list">
                      ${this.auditLog.events.map((event) => this.renderEvent(event))}
                    </ul>
                  `
                : html`
                    <div class="empty-state">
                      <div class="empty-icon">\u{1F4DC}</div>
                      <div>No events recorded yet</div>
                      <div style="font-size: 0.75rem; margin-top: 0.25rem;">
                        Events will appear here as you use the system
                      </div>
                    </div>
                  `}
        </div>

        ${this.auditLog
          ? html`
              <div class="footer">
                <span class="footer-text">
                  ${this.auditLog.total_position.toLocaleString()} total events
                </span>
                ${this.auditLog.has_more
                  ? html`<span class="view-all-link">View all \u2192</span>`
                  : ''}
              </div>
            `
          : ''}
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'audit-card': AuditCard
  }
}
