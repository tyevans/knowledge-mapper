import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { apiClient } from '../../api/client'
import type { HealthResponse, AuditStatsResponse } from '../../api/types'

// Import sub-components
import './audit-card'
import '../health-check'

/**
 * Dashboard Home Component
 *
 * Main dashboard view showing system overview, audit log, and quick stats.
 */
@customElement('dashboard-home')
export class DashboardHome extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .dashboard {
      display: grid;
      gap: 1.5rem;
    }

    .dashboard-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .welcome {
      font-size: 1.5rem;
      font-weight: 600;
      color: #1f2937;
      margin: 0;
    }

    .welcome-sub {
      font-size: 0.875rem;
      color: #6b7280;
      margin-top: 0.25rem;
    }

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
    }

    .stat-card {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
      padding: 1.25rem;
    }

    .stat-label {
      font-size: 0.75rem;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.5rem;
    }

    .stat-value {
      font-size: 1.75rem;
      font-weight: 700;
      color: #1f2937;
    }

    .stat-icon {
      float: right;
      font-size: 1.5rem;
      opacity: 0.3;
    }

    .main-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.5rem;
    }

    @media (max-width: 900px) {
      .main-grid {
        grid-template-columns: 1fr;
      }
    }

    .quick-links {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
      padding: 1.5rem;
    }

    .quick-links-title {
      font-size: 1.125rem;
      font-weight: 600;
      color: #1f2937;
      margin: 0 0 1rem 0;
    }

    .link-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 0.75rem;
    }

    .quick-link {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 1rem;
      background: #f9fafb;
      border-radius: 0.5rem;
      text-decoration: none;
      color: #374151;
      transition: all 0.2s;
      cursor: pointer;
      border: 1px solid transparent;
    }

    .quick-link:hover {
      background: #f3f4f6;
      border-color: #e5e7eb;
    }

    .quick-link-icon {
      font-size: 1.5rem;
    }

    .quick-link-text {
      font-weight: 500;
    }

    .quick-link-desc {
      font-size: 0.75rem;
      color: #6b7280;
    }

    .loading-shimmer {
      background: linear-gradient(90deg, #f3f4f6 25%, #e5e7eb 50%, #f3f4f6 75%);
      background-size: 200% 100%;
      animation: shimmer 1.5s infinite;
      border-radius: 0.25rem;
    }

    @keyframes shimmer {
      0% {
        background-position: 200% 0;
      }
      100% {
        background-position: -200% 0;
      }
    }
  `

  @state()
  private healthStatus: 'healthy' | 'error' | 'loading' = 'loading'

  @state()
  private stats: AuditStatsResponse | null = null

  @state()
  private statsLoading = true

  connectedCallback() {
    super.connectedCallback()
    this.fetchHealth()
    this.fetchStats()
  }

  private async fetchHealth() {
    const response = await apiClient.get<HealthResponse>('/api/v1/health', {
      authenticated: false,
    })

    this.healthStatus = response.success ? 'healthy' : 'error'
  }

  private async fetchStats() {
    this.statsLoading = true

    const response = await apiClient.get<AuditStatsResponse>('/api/v1/audit/stats')

    if (response.success) {
      this.stats = response.data
    }

    this.statsLoading = false
  }

  private handleNavigation(path: string) {
    window.history.pushState({}, '', path)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }

  private getTopEventTypes(): Array<{ name: string; count: number }> {
    if (!this.stats) return []

    return Object.entries(this.stats.event_type_counts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 3)
      .map(([name, count]) => ({ name, count }))
  }

  render() {
    const topEvents = this.getTopEventTypes()

    return html`
      <div class="dashboard">
        <div class="dashboard-header">
          <div>
            <h1 class="welcome">Dashboard</h1>
            <p class="welcome-sub">System overview and recent activity</p>
          </div>
        </div>

        <div class="stats-grid">
          <div class="stat-card">
            <span class="stat-icon">\u{1F4CA}</span>
            <div class="stat-label">Total Events</div>
            <div class="stat-value">
              ${this.statsLoading
                ? html`<span class="loading-shimmer" style="display: inline-block; width: 60px; height: 28px;"></span>`
                : (this.stats?.total_events ?? 0).toLocaleString()}
            </div>
          </div>

          <div class="stat-card">
            <span class="stat-icon">\u{1F3F7}</span>
            <div class="stat-label">Event Types</div>
            <div class="stat-value">
              ${this.statsLoading
                ? html`<span class="loading-shimmer" style="display: inline-block; width: 40px; height: 28px;"></span>`
                : Object.keys(this.stats?.event_type_counts ?? {}).length}
            </div>
          </div>

          <div class="stat-card">
            <span class="stat-icon">\u{1F4E6}</span>
            <div class="stat-label">Aggregates</div>
            <div class="stat-value">
              ${this.statsLoading
                ? html`<span class="loading-shimmer" style="display: inline-block; width: 40px; height: 28px;"></span>`
                : Object.keys(this.stats?.aggregate_type_counts ?? {}).length}
            </div>
          </div>

          <div class="stat-card">
            <span class="stat-icon">${this.healthStatus === 'healthy' ? '\u2705' : this.healthStatus === 'error' ? '\u274C' : '\u23F3'}</span>
            <div class="stat-label">System Status</div>
            <div class="stat-value" style="font-size: 1.25rem; color: ${this.healthStatus === 'healthy' ? '#10b981' : this.healthStatus === 'error' ? '#ef4444' : '#6b7280'}">
              ${this.healthStatus === 'healthy' ? 'Healthy' : this.healthStatus === 'error' ? 'Error' : 'Checking...'}
            </div>
          </div>
        </div>

        <div class="main-grid">
          <audit-card></audit-card>

          <div class="quick-links">
            <h2 class="quick-links-title">Quick Actions</h2>
            <div class="link-grid">
              <div class="quick-link" @click=${() => this.handleNavigation('/scraping')}>
                <span class="quick-link-icon">\u{1F578}</span>
                <div>
                  <div class="quick-link-text">Scraping Jobs</div>
                  <div class="quick-link-desc">Manage web scraping</div>
                </div>
              </div>

              <div class="quick-link" @click=${() => this.handleNavigation('/entities')}>
                <span class="quick-link-icon">\u{1F4C1}</span>
                <div>
                  <div class="quick-link-text">Entities</div>
                  <div class="quick-link-desc">Browse extracted data</div>
                </div>
              </div>

              <div class="quick-link" @click=${() => this.handleNavigation('/knowledge-graph')}>
                <span class="quick-link-icon">\u{1F310}</span>
                <div>
                  <div class="quick-link-text">Knowledge Graph</div>
                  <div class="quick-link-desc">Visualize connections</div>
                </div>
              </div>

              <div class="quick-link" @click=${() => this.handleNavigation('/tenants')}>
                <span class="quick-link-icon">\u{1F3E2}</span>
                <div>
                  <div class="quick-link-text">Tenants</div>
                  <div class="quick-link-desc">Manage workspaces</div>
                </div>
              </div>

              <div class="quick-link" @click=${() => this.handleNavigation('/consolidation')}>
                <span class="quick-link-icon">\u{1F517}</span>
                <div>
                  <div class="quick-link-text">Consolidation</div>
                  <div class="quick-link-desc">Merge duplicate entities</div>
                </div>
              </div>
            </div>

            ${topEvents.length > 0
              ? html`
                  <h3 style="font-size: 0.875rem; color: #6b7280; margin: 1.5rem 0 0.75rem 0;">Top Event Types</h3>
                  <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                    ${topEvents.map(
                      (event) => html`
                        <div style="display: flex; justify-content: space-between; font-size: 0.875rem; padding: 0.5rem; background: #f9fafb; border-radius: 0.25rem;">
                          <span style="font-family: monospace; color: #374151;">${event.name}</span>
                          <span style="color: #6b7280; font-weight: 500;">${event.count.toLocaleString()}</span>
                        </div>
                      `
                    )}
                  </div>
                `
              : ''}
          </div>
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'dashboard-home': DashboardHome
  }
}
