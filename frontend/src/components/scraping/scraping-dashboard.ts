import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { authStore, type AuthState } from '../../auth'
import { apiClient } from '../../api/client'
import type {
  ScrapingJobSummary,
  JobStatus,
  PaginatedResponse,
} from '../../api/scraping-types'
import { JOB_STATUS_LABELS } from '../../api/scraping-types'
import '../shared/km-pagination'
import '../shared/km-status-badge'
import '../shared/km-empty-state'
import './scraping-job-create-modal'

/**
 * Scraping Dashboard Component
 *
 * Displays list of scraping jobs with filtering, pagination, and quick actions.
 *
 * @fires view-job - When user clicks to view a job detail
 */
@customElement('scraping-dashboard')
export class ScrapingDashboard extends LitElement {
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

    .filters {
      display: flex;
      gap: 0.5rem;
      align-items: center;
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

    .job-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }

    .job-table th,
    .job-table td {
      padding: 0.75rem 1rem;
      text-align: left;
      border-bottom: 1px solid #e5e7eb;
    }

    .job-table th {
      background: #f9fafb;
      font-weight: 600;
      color: #374151;
    }

    .job-table tr:hover {
      background: #f9fafb;
    }

    .job-name {
      font-weight: 500;
      color: #1e3a8a;
      cursor: pointer;
    }

    .job-name:hover {
      text-decoration: underline;
    }

    .job-url {
      font-size: 0.75rem;
      color: #6b7280;
      max-width: 200px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .stats {
      font-size: 0.75rem;
      color: #6b7280;
    }

    .stats-value {
      font-weight: 500;
      color: #374151;
    }

    .date {
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

    .action-btn:hover:not(:disabled) {
      background: #f9fafb;
      border-color: #1e3a8a;
      color: #1e3a8a;
    }

    .action-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .action-btn.start {
      color: #065f46;
      border-color: #10b981;
    }

    .action-btn.start:hover:not(:disabled) {
      background: #d1fae5;
    }

    .action-btn.stop {
      color: #991b1b;
      border-color: #ef4444;
    }

    .action-btn.stop:hover:not(:disabled) {
      background: #fee2e2;
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
  private jobs: ScrapingJobSummary[] = []

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
  private statusFilter: JobStatus | '' = ''

  @state()
  private showCreateModal = false

  private unsubscribe?: () => void

  connectedCallback(): void {
    super.connectedCallback()
    this.unsubscribe = authStore.subscribe((state) => {
      const wasAuthenticated = this.authState?.isAuthenticated
      this.authState = state

      if (state.isAuthenticated && !wasAuthenticated) {
        this.loadJobs()
      }
    })

    if (this.authState?.isAuthenticated) {
      this.loadJobs()
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.unsubscribe?.()
  }

  private async loadJobs(): Promise<void> {
    this.isLoading = true
    this.error = null

    try {
      const params = new URLSearchParams({
        page: this.page.toString(),
        page_size: this.pageSize.toString(),
      })

      if (this.statusFilter) {
        params.set('status', this.statusFilter)
      }

      const response = await apiClient.get<PaginatedResponse<ScrapingJobSummary>>(
        `/api/v1/scraping/jobs?${params.toString()}`
      )

      if (response.success) {
        this.jobs = response.data.items
        this.total = response.data.total
        this.pages = response.data.pages
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to load jobs'
    } finally {
      this.isLoading = false
    }
  }

  private handlePageChange(e: CustomEvent): void {
    this.page = e.detail.page
    this.loadJobs()
  }

  private handleStatusFilterChange(e: Event): void {
    const select = e.target as HTMLSelectElement
    this.statusFilter = select.value as JobStatus | ''
    this.page = 1
    this.loadJobs()
  }

  private handleViewJob(job: ScrapingJobSummary): void {
    this.dispatchEvent(
      new CustomEvent('view-job', {
        detail: { jobId: job.id },
        bubbles: true,
        composed: true,
      })
    )
  }

  private async handleStartJob(job: ScrapingJobSummary): Promise<void> {
    try {
      const response = await apiClient.post(`/api/v1/scraping/jobs/${job.id}/start`)

      if (response.success) {
        this.loadJobs()
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to start job'
    }
  }

  private async handleStopJob(job: ScrapingJobSummary): Promise<void> {
    try {
      const response = await apiClient.post(`/api/v1/scraping/jobs/${job.id}/stop`)

      if (response.success) {
        this.loadJobs()
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to stop job'
    }
  }

  private async handleDeleteJob(job: ScrapingJobSummary): Promise<void> {
    if (!confirm(`Are you sure you want to delete "${job.name}"?`)) {
      return
    }

    try {
      const response = await apiClient.delete(`/api/v1/scraping/jobs/${job.id}`)

      if (response.success) {
        this.loadJobs()
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to delete job'
    }
  }

  private handleJobCreated(): void {
    this.showCreateModal = false
    this.loadJobs()
  }

  private canStart(status: JobStatus): boolean {
    return status === 'pending' || status === 'paused'
  }

  private canStop(status: JobStatus): boolean {
    return status === 'running' || status === 'queued' || status === 'paused'
  }

  private canDelete(status: JobStatus): boolean {
    return (
      status === 'pending' ||
      status === 'completed' ||
      status === 'failed' ||
      status === 'cancelled'
    )
  }

  private formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleString()
  }

  private renderJobTable() {
    if (this.jobs.length === 0) {
      return html`
        <km-empty-state
          icon="🕷️"
          title="No scraping jobs"
          message="Create your first scraping job to start extracting knowledge from websites."
        >
          <button
            slot="action"
            class="create-btn"
            @click=${() => (this.showCreateModal = true)}
          >
            Create Job
          </button>
        </km-empty-state>
      `
    }

    return html`
      <table class="job-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Status</th>
            <th>Progress</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${this.jobs.map(
            (job) => html`
              <tr>
                <td>
                  <div class="job-name" @click=${() => this.handleViewJob(job)}>
                    ${job.name}
                  </div>
                  <div class="job-url" title=${job.start_url}>${job.start_url}</div>
                </td>
                <td>
                  <km-status-badge
                    type="job-status"
                    status=${job.status}
                  ></km-status-badge>
                </td>
                <td>
                  <div class="stats">
                    <span class="stats-value">${job.pages_crawled}</span> pages,
                    <span class="stats-value">${job.entities_extracted}</span> entities
                  </div>
                </td>
                <td>
                  <div class="date">${this.formatDate(job.created_at)}</div>
                </td>
                <td>
                  <div class="actions">
                    <button
                      class="action-btn"
                      @click=${() => this.handleViewJob(job)}
                      title="View details"
                    >
                      View
                    </button>
                    ${this.canStart(job.status)
                      ? html`
                          <button
                            class="action-btn start"
                            @click=${() => this.handleStartJob(job)}
                            title="Start job"
                          >
                            Start
                          </button>
                        `
                      : null}
                    ${this.canStop(job.status)
                      ? html`
                          <button
                            class="action-btn stop"
                            @click=${() => this.handleStopJob(job)}
                            title="Stop job"
                          >
                            Stop
                          </button>
                        `
                      : null}
                    ${this.canDelete(job.status)
                      ? html`
                          <button
                            class="action-btn"
                            @click=${() => this.handleDeleteJob(job)}
                            title="Delete job"
                          >
                            Delete
                          </button>
                        `
                      : null}
                  </div>
                </td>
              </tr>
            `
          )}
        </tbody>
      </table>

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
              <p>Please log in to manage scraping jobs.</p>
            </div>
          </div>
        </div>
      `
    }

    return html`
      <div class="card">
        <div class="card-header">
          <h2>Scraping Jobs</h2>
          <span class="badge">${this.total} total</span>
        </div>
        <div class="card-body">
          ${this.error ? html`<div class="error">${this.error}</div>` : null}

          <div class="toolbar">
            <div class="filters">
              <select
                class="filter-select"
                .value=${this.statusFilter}
                @change=${this.handleStatusFilterChange}
              >
                <option value="">All Statuses</option>
                ${Object.entries(JOB_STATUS_LABELS).map(
                  ([value, label]) =>
                    html`<option value=${value}>${label}</option>`
                )}
              </select>
            </div>
            <button
              class="create-btn"
              @click=${() => (this.showCreateModal = true)}
            >
              + Create Job
            </button>
          </div>

          ${this.isLoading
            ? html`<div class="loading">Loading jobs...</div>`
            : this.renderJobTable()}
        </div>
      </div>

      <scraping-job-create-modal
        .open=${this.showCreateModal}
        @close=${() => (this.showCreateModal = false)}
        @job-created=${this.handleJobCreated}
      ></scraping-job-create-modal>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'scraping-dashboard': ScrapingDashboard
  }
}
