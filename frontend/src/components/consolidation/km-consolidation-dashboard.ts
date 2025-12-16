import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { apiClient } from '../../api/client'
import type {
  ReviewQueueStats,
  MergeCandidateListResponse,
  MergeCandidate,
  BatchConsolidationRequest,
  BatchConsolidationResponse,
} from '../../api/types'
import './km-review-queue-list'
import './km-merge-history'
import './km-merge-candidate-card'
import './km-consolidation-config'

type Tab = 'overview' | 'queue' | 'history' | 'settings'

/**
 * Consolidation dashboard component
 *
 * Overview dashboard with:
 * - Statistics cards
 * - Quick access to review queue
 * - Recent merge activity
 * - Configuration access
 *
 * @element km-consolidation-dashboard
 * @fires view-entity - When user wants to view entity details
 */
@customElement('km-consolidation-dashboard')
export class KmConsolidationDashboard extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .dashboard {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }

    .dashboard-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
    }

    .dashboard-title {
      font-size: 1.5rem;
      font-weight: 600;
      color: #1f2937;
      margin: 0;
    }

    .dashboard-subtitle {
      font-size: 0.875rem;
      color: #6b7280;
      margin-top: 0.25rem;
    }

    .header-actions {
      display: flex;
      gap: 0.5rem;
    }

    .action-btn {
      padding: 0.5rem 1rem;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
    }

    .action-btn.primary {
      background: #1e3a8a;
      border: 1px solid #1e3a8a;
      color: white;
    }

    .action-btn.primary:hover:not(:disabled) {
      background: #1e40af;
    }

    .action-btn.secondary {
      background: white;
      border: 1px solid #e5e7eb;
      color: #374151;
    }

    .action-btn.secondary:hover:not(:disabled) {
      background: #f9fafb;
      border-color: #d1d5db;
    }

    .action-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .tabs {
      display: flex;
      gap: 0.25rem;
      background: #f3f4f6;
      padding: 0.25rem;
      border-radius: 0.5rem;
    }

    .tab {
      padding: 0.5rem 1rem;
      border: none;
      background: transparent;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      font-weight: 500;
      color: #6b7280;
      cursor: pointer;
      transition: all 0.2s;
    }

    .tab:hover:not(.active) {
      color: #374151;
      background: white;
    }

    .tab.active {
      background: white;
      color: #1f2937;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    }

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
    }

    .stat-card {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
      padding: 1.25rem;
      transition: transform 0.2s, box-shadow 0.2s;
    }

    .stat-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }

    .stat-card.clickable {
      cursor: pointer;
    }

    .stat-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 0.75rem;
    }

    .stat-icon {
      font-size: 1.5rem;
      opacity: 0.7;
    }

    .stat-badge {
      font-size: 0.625rem;
      padding: 0.125rem 0.375rem;
      border-radius: 9999px;
      font-weight: 500;
    }

    .stat-badge.pending {
      background: #fef3c7;
      color: #92400e;
    }

    .stat-badge.urgent {
      background: #fee2e2;
      color: #991b1b;
    }

    .stat-label {
      font-size: 0.75rem;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.25rem;
    }

    .stat-value {
      font-size: 1.75rem;
      font-weight: 700;
      color: #1f2937;
    }

    .stat-change {
      font-size: 0.75rem;
      margin-top: 0.25rem;
    }

    .stat-change.positive {
      color: #059669;
    }

    .stat-change.negative {
      color: #dc2626;
    }

    .main-content {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 1.5rem;
    }

    @media (max-width: 1024px) {
      .main-content {
        grid-template-columns: 1fr;
      }
    }

    .section-card {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
      overflow: hidden;
    }

    .section-header {
      padding: 1rem 1.5rem;
      background: #f9fafb;
      border-bottom: 1px solid #e5e7eb;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .section-title {
      font-size: 1rem;
      font-weight: 600;
      color: #1f2937;
      margin: 0;
    }

    .section-link {
      font-size: 0.875rem;
      color: #1e3a8a;
      cursor: pointer;
      text-decoration: none;
    }

    .section-link:hover {
      text-decoration: underline;
    }

    .section-body {
      padding: 1.5rem;
    }

    .candidate-list {
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }

    .empty-state {
      text-align: center;
      padding: 2rem;
      color: #6b7280;
    }

    .empty-icon {
      font-size: 2rem;
      margin-bottom: 0.5rem;
    }

    .quick-stats {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }

    .quick-stat {
      display: flex;
      justify-content: space-between;
      padding: 0.75rem;
      background: #f9fafb;
      border-radius: 0.375rem;
    }

    .quick-stat-label {
      font-size: 0.875rem;
      color: #6b7280;
    }

    .quick-stat-value {
      font-size: 0.875rem;
      font-weight: 600;
      color: #374151;
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

    .success {
      background: #d1fae5;
      color: #065f46;
      padding: 0.75rem;
      border-radius: 0.375rem;
      margin-bottom: 1rem;
      font-size: 0.875rem;
    }

    .tab-content {
      animation: fadeIn 0.2s ease-in-out;
    }

    @keyframes fadeIn {
      from {
        opacity: 0;
      }
      to {
        opacity: 1;
      }
    }
  `

  @state()
  private activeTab: Tab = 'overview'

  @state()
  private stats: ReviewQueueStats | null = null

  @state()
  private topCandidates: MergeCandidate[] = []

  @state()
  private isLoading = true

  @state()
  private error: string | null = null

  @state()
  private success: string | null = null

  @state()
  private isRunningBatch = false

  connectedCallback(): void {
    super.connectedCallback()
    this.loadDashboardData()
  }

  private async loadDashboardData(): Promise<void> {
    this.isLoading = true
    this.error = null

    try {
      // Load stats and top candidates in parallel
      const [statsResponse, candidatesResponse] = await Promise.all([
        apiClient.get<ReviewQueueStats>('/api/v1/consolidation/review-queue/stats'),
        apiClient.get<MergeCandidateListResponse>(
          '/api/v1/consolidation/candidates?page=1&page_size=3&min_confidence=0.5'
        ),
      ])

      if (statsResponse.success) {
        this.stats = statsResponse.data
      }

      if (candidatesResponse.success) {
        this.topCandidates = candidatesResponse.data.items
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to load dashboard data'
    } finally {
      this.isLoading = false
    }
  }

  private handleTabChange(tab: Tab): void {
    this.activeTab = tab
  }

  private handleViewEntity(e: CustomEvent): void {
    this.dispatchEvent(
      new CustomEvent('view-entity', {
        detail: e.detail,
        bubbles: true,
        composed: true,
      })
    )
  }

  private async runBatchConsolidation(): Promise<void> {
    if (!confirm('This will run batch consolidation to find and merge high-confidence duplicates. Continue?')) {
      return
    }

    this.isRunningBatch = true
    this.error = null
    this.success = null

    try {
      const request: BatchConsolidationRequest = {
        min_confidence: 0.9,
        dry_run: false,
        max_merges: 100,
      }

      const response = await apiClient.post<BatchConsolidationResponse>(
        '/api/v1/consolidation/batch',
        request
      )

      if (response.success) {
        this.success = `Batch consolidation started. Job ID: ${response.data.job_id}`
        setTimeout(() => (this.success = null), 5000)
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to start batch consolidation'
    } finally {
      this.isRunningBatch = false
    }
  }

  private renderStats() {
    if (!this.stats) return null

    const hasUrgent = this.stats.oldest_pending_age_hours && this.stats.oldest_pending_age_hours > 24

    return html`
      <div class="stats-grid">
        <div
          class="stat-card clickable"
          @click=${() => this.handleTabChange('queue')}
          role="button"
          tabindex="0"
          @keydown=${(e: KeyboardEvent) => e.key === 'Enter' && this.handleTabChange('queue')}
        >
          <div class="stat-header">
            <span class="stat-icon">\u{1F4CB}</span>
            ${this.stats.total_pending > 10
              ? html`<span class="stat-badge pending">Needs attention</span>`
              : null}
          </div>
          <div class="stat-label">Pending Reviews</div>
          <div class="stat-value">${this.stats.total_pending}</div>
        </div>

        <div class="stat-card">
          <div class="stat-header">
            <span class="stat-icon">\u{2705}</span>
          </div>
          <div class="stat-label">Approved</div>
          <div class="stat-value">${this.stats.total_approved}</div>
        </div>

        <div class="stat-card">
          <div class="stat-header">
            <span class="stat-icon">\u{274C}</span>
          </div>
          <div class="stat-label">Rejected</div>
          <div class="stat-value">${this.stats.total_rejected}</div>
        </div>

        <div class="stat-card">
          <div class="stat-header">
            <span class="stat-icon">\u{1F4CA}</span>
            ${hasUrgent
              ? html`<span class="stat-badge urgent">Overdue</span>`
              : null}
          </div>
          <div class="stat-label">Avg. Confidence</div>
          <div class="stat-value">${Math.round(this.stats.avg_confidence * 100)}%</div>
          ${this.stats.oldest_pending_age_hours
            ? html`
                <div class="stat-change ${hasUrgent ? 'negative' : ''}">
                  Oldest: ${Math.round(this.stats.oldest_pending_age_hours)}h ago
                </div>
              `
            : null}
        </div>
      </div>
    `
  }

  private renderOverview() {
    return html`
      <div class="tab-content">
        ${this.renderStats()}

        <div class="main-content">
          <div class="section-card">
            <div class="section-header">
              <h3 class="section-title">Top Merge Candidates</h3>
              <span class="section-link" @click=${() => this.handleTabChange('queue')}>
                View All \u{2192}
              </span>
            </div>
            <div class="section-body">
              ${this.topCandidates.length > 0
                ? html`
                    <div class="candidate-list">
                      ${this.topCandidates.map(
                        (candidate) => html`
                          <km-merge-candidate-card
                            .candidate=${candidate}
                            @view-entity=${this.handleViewEntity}
                          ></km-merge-candidate-card>
                        `
                      )}
                    </div>
                  `
                : html`
                    <div class="empty-state">
                      <div class="empty-icon">\u{1F50D}</div>
                      <p>No merge candidates found</p>
                    </div>
                  `}
            </div>
          </div>

          <div>
            <div class="section-card" style="margin-bottom: 1rem;">
              <div class="section-header">
                <h3 class="section-title">Quick Stats</h3>
              </div>
              <div class="section-body">
                <div class="quick-stats">
                  <div class="quick-stat">
                    <span class="quick-stat-label">Deferred</span>
                    <span class="quick-stat-value">${this.stats?.total_deferred ?? 0}</span>
                  </div>
                  <div class="quick-stat">
                    <span class="quick-stat-label">Expired</span>
                    <span class="quick-stat-value">${this.stats?.total_expired ?? 0}</span>
                  </div>
                  <div class="quick-stat">
                    <span class="quick-stat-label">Total Reviewed</span>
                    <span class="quick-stat-value">
                      ${(this.stats?.total_approved ?? 0) +
                      (this.stats?.total_rejected ?? 0) +
                      (this.stats?.total_deferred ?? 0)}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div class="section-card">
              <div class="section-header">
                <h3 class="section-title">Quick Actions</h3>
              </div>
              <div class="section-body">
                <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                  <button
                    class="action-btn primary"
                    style="width: 100%;"
                    @click=${() => this.handleTabChange('queue')}
                  >
                    Review Queue
                  </button>
                  <button
                    class="action-btn secondary"
                    style="width: 100%;"
                    @click=${() => this.handleTabChange('history')}
                  >
                    View History
                  </button>
                  <button
                    class="action-btn secondary"
                    style="width: 100%;"
                    @click=${() => this.handleTabChange('settings')}
                  >
                    Settings
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `
  }

  private renderQueue() {
    return html`
      <div class="tab-content">
        <km-review-queue-list
          @view-entity=${this.handleViewEntity}
        ></km-review-queue-list>
      </div>
    `
  }

  private renderHistory() {
    return html`
      <div class="tab-content">
        <km-merge-history
          @view-entity=${this.handleViewEntity}
        ></km-merge-history>
      </div>
    `
  }

  private renderSettings() {
    return html`
      <div class="tab-content">
        <km-consolidation-config></km-consolidation-config>
      </div>
    `
  }

  render() {
    return html`
      <div class="dashboard">
        <div class="dashboard-header">
          <div>
            <h1 class="dashboard-title">Entity Consolidation</h1>
            <p class="dashboard-subtitle">
              Identify and merge duplicate entities across your knowledge graph
            </p>
          </div>
          <div class="header-actions">
            <button
              class="action-btn secondary"
              @click=${this.loadDashboardData}
              ?disabled=${this.isLoading}
            >
              Refresh
            </button>
            <button
              class="action-btn primary"
              @click=${this.runBatchConsolidation}
              ?disabled=${this.isRunningBatch}
            >
              ${this.isRunningBatch ? 'Running...' : 'Run Batch Consolidation'}
            </button>
          </div>
        </div>

        ${this.error ? html`<div class="error">${this.error}</div>` : null}
        ${this.success ? html`<div class="success">${this.success}</div>` : null}

        <div class="tabs" role="tablist">
          <button
            class="tab ${this.activeTab === 'overview' ? 'active' : ''}"
            @click=${() => this.handleTabChange('overview')}
            role="tab"
            aria-selected=${this.activeTab === 'overview'}
          >
            Overview
          </button>
          <button
            class="tab ${this.activeTab === 'queue' ? 'active' : ''}"
            @click=${() => this.handleTabChange('queue')}
            role="tab"
            aria-selected=${this.activeTab === 'queue'}
          >
            Review Queue
            ${this.stats && this.stats.total_pending > 0
              ? html`<span style="margin-left: 0.25rem; font-size: 0.75rem; opacity: 0.7;">(${this.stats.total_pending})</span>`
              : null}
          </button>
          <button
            class="tab ${this.activeTab === 'history' ? 'active' : ''}"
            @click=${() => this.handleTabChange('history')}
            role="tab"
            aria-selected=${this.activeTab === 'history'}
          >
            History
          </button>
          <button
            class="tab ${this.activeTab === 'settings' ? 'active' : ''}"
            @click=${() => this.handleTabChange('settings')}
            role="tab"
            aria-selected=${this.activeTab === 'settings'}
          >
            Settings
          </button>
        </div>

        ${this.isLoading && this.activeTab === 'overview'
          ? html`<div class="loading">Loading dashboard...</div>`
          : this.activeTab === 'overview'
            ? this.renderOverview()
            : this.activeTab === 'queue'
              ? this.renderQueue()
              : this.activeTab === 'history'
                ? this.renderHistory()
                : this.renderSettings()}
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'km-consolidation-dashboard': KmConsolidationDashboard
  }
}
