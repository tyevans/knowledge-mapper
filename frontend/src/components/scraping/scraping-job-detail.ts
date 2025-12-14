import { LitElement, html, css } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import { authStore, type AuthState } from '../../auth'
import { apiClient } from '../../api/client'
import type {
  ScrapingJobResponse,
  JobStatusResponse,
  ScrapedPageSummary,
  ExtractedEntitySummary,
  PaginatedResponse,
  JobStatus,
} from '../../api/scraping-types'
import '../shared/km-pagination'
import '../shared/km-status-badge'
import '../shared/km-empty-state'

type Tab = 'pages' | 'entities'

/**
 * Scraping Job Detail Component
 *
 * Displays detailed information about a scraping job with real-time status updates.
 *
 * @fires back - When user clicks back button
 * @fires view-entity - When user clicks to view an entity
 * @fires view-graph - When user clicks to view knowledge graph
 */
@customElement('scraping-job-detail')
export class ScrapingJobDetail extends LitElement {
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
    }

    .card-header {
      background: #1f2937;
      color: white;
      padding: 1.5rem;
    }

    .header-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
      margin-bottom: 1rem;
    }

    .job-title {
      margin: 0;
      font-size: 1.25rem;
    }

    .job-url {
      font-size: 0.875rem;
      opacity: 0.8;
      margin-top: 0.25rem;
      word-break: break-all;
    }

    .controls {
      display: flex;
      gap: 0.5rem;
      flex-shrink: 0;
    }

    .control-btn {
      padding: 0.5rem 1rem;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
      border: none;
    }

    .control-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .control-btn.start {
      background: #10b981;
      color: white;
    }

    .control-btn.start:hover:not(:disabled) {
      background: #059669;
    }

    .control-btn.pause {
      background: #f59e0b;
      color: white;
    }

    .control-btn.pause:hover:not(:disabled) {
      background: #d97706;
    }

    .control-btn.stop {
      background: #ef4444;
      color: white;
    }

    .control-btn.stop:hover:not(:disabled) {
      background: #dc2626;
    }

    .stats-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 1rem;
      margin-top: 1rem;
    }

    .stat-card {
      background: rgba(255, 255, 255, 0.1);
      padding: 0.75rem;
      border-radius: 0.375rem;
      text-align: center;
    }

    .stat-value {
      font-size: 1.5rem;
      font-weight: 600;
    }

    .stat-label {
      font-size: 0.75rem;
      opacity: 0.8;
      margin-top: 0.25rem;
    }

    .progress-section {
      margin-top: 1rem;
    }

    .progress-bar {
      height: 0.5rem;
      background: rgba(255, 255, 255, 0.2);
      border-radius: 0.25rem;
      overflow: hidden;
    }

    .progress-fill {
      height: 100%;
      background: #10b981;
      transition: width 0.3s ease;
    }

    .progress-text {
      font-size: 0.75rem;
      margin-top: 0.25rem;
      opacity: 0.8;
    }

    .tabs {
      display: flex;
      border-bottom: 1px solid #e5e7eb;
    }

    .tab {
      padding: 1rem 1.5rem;
      font-size: 0.875rem;
      font-weight: 500;
      color: #6b7280;
      cursor: pointer;
      border: none;
      background: none;
      border-bottom: 2px solid transparent;
      transition: all 0.2s;
    }

    .tab:hover {
      color: #1e3a8a;
    }

    .tab.active {
      color: #1e3a8a;
      border-bottom-color: #1e3a8a;
    }

    .tab-content {
      padding: 1.5rem;
    }

    .item-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }

    .item-table th,
    .item-table td {
      padding: 0.75rem 1rem;
      text-align: left;
      border-bottom: 1px solid #e5e7eb;
    }

    .item-table th {
      background: #f9fafb;
      font-weight: 600;
      color: #374151;
    }

    .item-table tr:hover {
      background: #f9fafb;
    }

    .page-url {
      max-width: 300px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #1e3a8a;
      cursor: pointer;
    }

    .page-url:hover {
      text-decoration: underline;
    }

    .entity-name {
      font-weight: 500;
      color: #1e3a8a;
      cursor: pointer;
    }

    .entity-name:hover {
      text-decoration: underline;
    }

    .confidence {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .confidence-bar {
      width: 60px;
      height: 6px;
      background: #e5e7eb;
      border-radius: 3px;
      overflow: hidden;
    }

    .confidence-fill {
      height: 100%;
      background: #10b981;
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

    .error-message {
      background: #fef2f2;
      color: #991b1b;
      padding: 1rem;
      border-radius: 0.375rem;
      margin: 1rem;
    }

    .graph-link {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 1rem;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 0.375rem;
      color: white;
      font-size: 0.875rem;
      cursor: pointer;
      transition: background 0.2s;
      border: none;
    }

    .graph-link:hover {
      background: rgba(255, 255, 255, 0.2);
    }

    .header-actions {
      display: flex;
      gap: 0.5rem;
      align-items: center;
    }
  `

  @property({ type: String })
  jobId = ''

  @state()
  private authState: AuthState | null = null

  @state()
  private job: ScrapingJobResponse | null = null

  @state()
  private isLoading = true

  @state()
  private error: string | null = null

  @state()
  private activeTab: Tab = 'pages'

  @state()
  private pages: ScrapedPageSummary[] = []

  @state()
  private pagesPage = 1

  @state()
  private pagesTotal = 0

  @state()
  private pagesPages = 1

  @state()
  private entities: ExtractedEntitySummary[] = []

  @state()
  private entitiesPage = 1

  @state()
  private entitiesTotal = 0

  @state()
  private entitiesPages = 1

  private unsubscribe?: () => void
  private pollInterval: number | null = null
  private readonly pageSize = 20

  connectedCallback(): void {
    super.connectedCallback()
    this.unsubscribe = authStore.subscribe((state) => {
      const wasAuthenticated = this.authState?.isAuthenticated
      this.authState = state

      if (state.isAuthenticated && !wasAuthenticated) {
        this.loadJob()
      }
    })

    if (this.authState?.isAuthenticated) {
      this.loadJob()
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.unsubscribe?.()
    this.stopPolling()
  }

  updated(changedProperties: Map<string, unknown>): void {
    if (changedProperties.has('jobId') && this.jobId && this.authState?.isAuthenticated) {
      this.loadJob()
    }
  }

  private async loadJob(): Promise<void> {
    if (!this.jobId) return

    this.isLoading = true
    this.error = null

    try {
      const response = await apiClient.get<ScrapingJobResponse>(
        `/api/v1/scraping/jobs/${this.jobId}`
      )

      if (response.success) {
        this.job = response.data
        this.startPollingIfNeeded()
        await this.loadTabContent()
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to load job'
    } finally {
      this.isLoading = false
    }
  }

  private startPollingIfNeeded(): void {
    this.stopPolling()

    if (this.job && ['running', 'queued'].includes(this.job.status)) {
      this.pollInterval = window.setInterval(() => this.pollStatus(), 3000)
    }
  }

  private stopPolling(): void {
    if (this.pollInterval) {
      clearInterval(this.pollInterval)
      this.pollInterval = null
    }
  }

  private async pollStatus(): Promise<void> {
    if (!this.jobId) return

    try {
      const response = await apiClient.get<JobStatusResponse>(
        `/api/v1/scraping/jobs/${this.jobId}/status`
      )

      if (response.success && this.job) {
        this.job = {
          ...this.job,
          status: response.data.status,
          pages_crawled: response.data.pages_crawled,
          entities_extracted: response.data.entities_extracted,
          errors_count: response.data.errors_count,
          started_at: response.data.started_at,
          completed_at: response.data.completed_at,
          error_message: response.data.error_message,
        }

        // Stop polling if job is no longer running
        if (!['running', 'queued'].includes(response.data.status)) {
          this.stopPolling()
          await this.loadTabContent()
        }
      }
    } catch {
      // Silent fail on poll errors
    }
  }

  private async loadTabContent(): Promise<void> {
    if (this.activeTab === 'pages') {
      await this.loadPages()
    } else {
      await this.loadEntities()
    }
  }

  private async loadPages(): Promise<void> {
    if (!this.jobId) return

    try {
      const params = new URLSearchParams({
        page: this.pagesPage.toString(),
        page_size: this.pageSize.toString(),
      })

      const response = await apiClient.get<PaginatedResponse<ScrapedPageSummary>>(
        `/api/v1/scraping/jobs/${this.jobId}/pages?${params.toString()}`
      )

      if (response.success) {
        this.pages = response.data.items
        this.pagesTotal = response.data.total
        this.pagesPages = response.data.pages
      }
    } catch {
      // Silent fail
    }
  }

  private async loadEntities(): Promise<void> {
    if (!this.jobId) return

    try {
      const params = new URLSearchParams({
        page: this.entitiesPage.toString(),
        page_size: this.pageSize.toString(),
      })

      const response = await apiClient.get<PaginatedResponse<ExtractedEntitySummary>>(
        `/api/v1/scraping/jobs/${this.jobId}/entities?${params.toString()}`
      )

      if (response.success) {
        this.entities = response.data.items
        this.entitiesTotal = response.data.total
        this.entitiesPages = response.data.pages
      }
    } catch {
      // Silent fail
    }
  }

  private handleTabChange(tab: Tab): void {
    this.activeTab = tab
    this.loadTabContent()
  }

  private handlePagesPageChange(e: CustomEvent): void {
    this.pagesPage = e.detail.page
    this.loadPages()
  }

  private handleEntitiesPageChange(e: CustomEvent): void {
    this.entitiesPage = e.detail.page
    this.loadEntities()
  }

  private handleBack(): void {
    this.dispatchEvent(new CustomEvent('back', { bubbles: true, composed: true }))
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

  private handleViewGraph(): void {
    this.dispatchEvent(
      new CustomEvent('view-graph', {
        detail: {},
        bubbles: true,
        composed: true,
      })
    )
  }

  private async handleStart(): Promise<void> {
    try {
      const response = await apiClient.post(`/api/v1/scraping/jobs/${this.jobId}/start`)
      if (response.success) {
        await this.loadJob()
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to start job'
    }
  }

  private async handlePause(): Promise<void> {
    try {
      const response = await apiClient.post(`/api/v1/scraping/jobs/${this.jobId}/pause`)
      if (response.success) {
        await this.loadJob()
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to pause job'
    }
  }

  private async handleStop(): Promise<void> {
    try {
      const response = await apiClient.post(`/api/v1/scraping/jobs/${this.jobId}/stop`)
      if (response.success) {
        await this.loadJob()
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to stop job'
    }
  }

  private canStart(status: JobStatus): boolean {
    return status === 'pending' || status === 'paused'
  }

  private canPause(status: JobStatus): boolean {
    return status === 'running'
  }

  private canStop(status: JobStatus): boolean {
    return status === 'running' || status === 'queued' || status === 'paused'
  }

  private getProgress(): number {
    if (!this.job) return 0
    if (this.job.max_pages === 0) return 0
    return Math.min(100, (this.job.pages_crawled / this.job.max_pages) * 100)
  }

  private formatDate(dateStr: string | null): string {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleString()
  }

  private renderControls() {
    if (!this.job) return null

    return html`
      <div class="controls">
        ${this.canStart(this.job.status)
          ? html`
              <button class="control-btn start" @click=${this.handleStart}>
                Start
              </button>
            `
          : null}
        ${this.canPause(this.job.status)
          ? html`
              <button class="control-btn pause" @click=${this.handlePause}>
                Pause
              </button>
            `
          : null}
        ${this.canStop(this.job.status)
          ? html`
              <button class="control-btn stop" @click=${this.handleStop}>
                Stop
              </button>
            `
          : null}
      </div>
    `
  }

  private renderPagesTable() {
    if (this.pages.length === 0) {
      return html`
        <km-empty-state
          icon="📄"
          title="No pages scraped yet"
          message="Pages will appear here once the job starts crawling."
        ></km-empty-state>
      `
    }

    return html`
      <table class="item-table">
        <thead>
          <tr>
            <th>URL</th>
            <th>Title</th>
            <th>Status</th>
            <th>Depth</th>
            <th>Crawled</th>
          </tr>
        </thead>
        <tbody>
          ${this.pages.map(
            (page) => html`
              <tr>
                <td>
                  <div
                    class="page-url"
                    title=${page.url}
                    @click=${() => window.open(page.url, '_blank')}
                  >
                    ${page.url}
                  </div>
                </td>
                <td>${page.title || '-'}</td>
                <td>
                  <km-status-badge
                    type="extraction-status"
                    status=${page.extraction_status}
                  ></km-status-badge>
                </td>
                <td>${page.depth}</td>
                <td>${this.formatDate(page.crawled_at)}</td>
              </tr>
            `
          )}
        </tbody>
      </table>

      <km-pagination
        .page=${this.pagesPage}
        .total=${this.pagesTotal}
        .pageSize=${this.pageSize}
        .pages=${this.pagesPages}
        @page-change=${this.handlePagesPageChange}
      ></km-pagination>
    `
  }

  private renderEntitiesTable() {
    if (this.entities.length === 0) {
      return html`
        <km-empty-state
          icon="🔗"
          title="No entities extracted yet"
          message="Entities will appear here once extraction is complete."
        ></km-empty-state>
      `
    }

    return html`
      <table class="item-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Method</th>
            <th>Confidence</th>
          </tr>
        </thead>
        <tbody>
          ${this.entities.map(
            (entity) => html`
              <tr>
                <td>
                  <span
                    class="entity-name"
                    @click=${() => this.handleViewEntity(entity.id)}
                  >
                    ${entity.name}
                  </span>
                </td>
                <td>
                  <km-status-badge
                    type="entity-type"
                    status=${entity.entity_type}
                  ></km-status-badge>
                </td>
                <td>${entity.extraction_method}</td>
                <td>
                  <div class="confidence">
                    <div class="confidence-bar">
                      <div
                        class="confidence-fill"
                        style="width: ${entity.confidence_score * 100}%"
                      ></div>
                    </div>
                    <span>${(entity.confidence_score * 100).toFixed(0)}%</span>
                  </div>
                </td>
              </tr>
            `
          )}
        </tbody>
      </table>

      <km-pagination
        .page=${this.entitiesPage}
        .total=${this.entitiesTotal}
        .pageSize=${this.pageSize}
        .pages=${this.entitiesPages}
        @page-change=${this.handleEntitiesPageChange}
      ></km-pagination>
    `
  }

  render() {
    if (!this.authState?.isAuthenticated) {
      return html`
        <div class="card">
          <div class="loading">Please log in to view job details.</div>
        </div>
      `
    }

    if (this.isLoading) {
      return html`
        <span class="back-link" @click=${this.handleBack}>&larr; Back to Jobs</span>
        <div class="card">
          <div class="loading">Loading job details...</div>
        </div>
      `
    }

    if (!this.job) {
      return html`
        <span class="back-link" @click=${this.handleBack}>&larr; Back to Jobs</span>
        <div class="card">
          <div class="error-message">Job not found</div>
        </div>
      `
    }

    const progress = this.getProgress()

    return html`
      <span class="back-link" @click=${this.handleBack}>&larr; Back to Jobs</span>

      <div class="card">
        <div class="card-header">
          ${this.error ? html`<div class="error">${this.error}</div>` : null}

          <div class="header-top">
            <div>
              <h1 class="job-title">${this.job.name}</h1>
              <div class="job-url">${this.job.start_url}</div>
            </div>
            <div class="header-actions">
              <km-status-badge
                type="job-status"
                status=${this.job.status}
              ></km-status-badge>
              ${this.renderControls()}
            </div>
          </div>

          <div class="stats-row">
            <div class="stat-card">
              <div class="stat-value">${this.job.pages_crawled}</div>
              <div class="stat-label">Pages Crawled</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">${this.job.entities_extracted}</div>
              <div class="stat-label">Entities Found</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">${this.job.errors_count}</div>
              <div class="stat-label">Errors</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">${this.job.crawl_depth}</div>
              <div class="stat-label">Max Depth</div>
            </div>
          </div>

          <div class="progress-section">
            <div class="progress-bar">
              <div class="progress-fill" style="width: ${progress}%"></div>
            </div>
            <div class="progress-text">
              ${this.job.pages_crawled} / ${this.job.max_pages} pages (${progress.toFixed(1)}%)
            </div>
          </div>

          ${this.job.entities_extracted > 0
            ? html`
                <button
                  class="graph-link"
                  @click=${this.handleViewGraph}
                  style="margin-top: 1rem;"
                >
                  View Knowledge Graph
                </button>
              `
            : null}
        </div>

        <div class="tabs">
          <button
            class="tab ${this.activeTab === 'pages' ? 'active' : ''}"
            @click=${() => this.handleTabChange('pages')}
          >
            Pages (${this.pagesTotal})
          </button>
          <button
            class="tab ${this.activeTab === 'entities' ? 'active' : ''}"
            @click=${() => this.handleTabChange('entities')}
          >
            Entities (${this.entitiesTotal})
          </button>
        </div>

        <div class="tab-content">
          ${this.activeTab === 'pages'
            ? this.renderPagesTable()
            : this.renderEntitiesTable()}
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'scraping-job-detail': ScrapingJobDetail
  }
}
