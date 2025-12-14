import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { healthApi } from '../api'
import type { HealthResponse, ApiError } from '../api'

/**
 * Health Check Component
 * Displays backend health status and allows manual health checks
 */
@customElement('health-check')
export class HealthCheck extends LitElement {
  static styles = css`
    :host {
      display: block;
      font-family: system-ui, -apple-system, sans-serif;
    }

    .container {
      max-width: 600px;
      margin: 0 auto;
      padding: 2rem;
    }

    .card {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
      padding: 1.5rem;
    }

    .title {
      font-size: 1.5rem;
      font-weight: bold;
      color: #1f2937;
      margin-bottom: 1rem;
    }

    .status {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 1rem;
    }

    .status-indicator {
      width: 12px;
      height: 12px;
      border-radius: 50%;
    }

    .status-indicator.healthy {
      background-color: #10b981;
    }

    .status-indicator.error {
      background-color: #ef4444;
    }

    .status-indicator.loading {
      background-color: #6b7280;
      animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }

    @keyframes pulse {
      0%, 100% {
        opacity: 1;
      }
      50% {
        opacity: 0.5;
      }
    }

    .status-text {
      font-weight: 500;
      color: #374151;
    }

    .info {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      margin-bottom: 1.5rem;
      padding: 1rem;
      background: #f9fafb;
      border-radius: 0.375rem;
    }

    .info-row {
      display: flex;
      justify-content: space-between;
      font-size: 0.875rem;
    }

    .info-label {
      color: #6b7280;
    }

    .info-value {
      color: #1f2937;
      font-weight: 500;
    }

    .error-message {
      background: #fef2f2;
      border: 1px solid #fecaca;
      border-radius: 0.375rem;
      padding: 1rem;
      color: #991b1b;
      margin-bottom: 1rem;
    }

    .button {
      background-color: #0ea5e9;
      color: white;
      padding: 0.5rem 1rem;
      border-radius: 0.375rem;
      border: none;
      font-weight: 500;
      cursor: pointer;
      transition: background-color 0.2s;
    }

    .button:hover:not(:disabled) {
      background-color: #0284c7;
    }

    .button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .loading {
      display: inline-block;
      width: 1rem;
      height: 1rem;
      border: 2px solid #ffffff;
      border-right-color: transparent;
      border-radius: 50%;
      animation: spin 0.75s linear infinite;
    }

    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }
  `

  @state()
  private loading = false

  @state()
  private healthData: HealthResponse | null = null

  @state()
  private error: ApiError | null = null

  @state()
  private lastChecked: Date | null = null

  connectedCallback() {
    super.connectedCallback()
    this.checkHealth()
  }

  private async checkHealth() {
    this.loading = true
    this.error = null

    const response = await healthApi.checkHealth()

    if (response.success) {
      this.healthData = response.data
      this.lastChecked = new Date()
    } else {
      this.error = response.error
    }

    this.loading = false
  }

  private handleCheckHealth() {
    this.checkHealth()
  }

  private formatTimestamp(date: Date): string {
    return date.toLocaleString()
  }

  render() {
    return html`
      <div class="container">
        <div class="card">
          <h1 class="title">Backend Health Check</h1>

          <div class="status">
            <span
              class="status-indicator ${this.loading
                ? 'loading'
                : this.error
                  ? 'error'
                  : 'healthy'}"
            ></span>
            <span class="status-text">
              ${this.loading
                ? 'Checking...'
                : this.error
                  ? 'Error'
                  : this.healthData?.status || 'Unknown'}
            </span>
          </div>

          ${this.error
            ? html`
                <div class="error-message">
                  <strong>Error:</strong> ${this.error.message}
                  ${this.error.status
                    ? html`<br /><small>Status Code: ${this.error.status}</small>`
                    : ''}
                </div>
              `
            : ''}
          ${this.healthData
            ? html`
                <div class="info">
                  <div class="info-row">
                    <span class="info-label">Status:</span>
                    <span class="info-value">${this.healthData.status}</span>
                  </div>
                  ${this.healthData.version
                    ? html`
                        <div class="info-row">
                          <span class="info-label">Version:</span>
                          <span class="info-value">${this.healthData.version}</span>
                        </div>
                      `
                    : ''}
                  ${this.healthData.timestamp
                    ? html`
                        <div class="info-row">
                          <span class="info-label">Server Time:</span>
                          <span class="info-value">${this.healthData.timestamp}</span>
                        </div>
                      `
                    : ''}
                  ${this.lastChecked
                    ? html`
                        <div class="info-row">
                          <span class="info-label">Last Checked:</span>
                          <span class="info-value">${this.formatTimestamp(this.lastChecked)}</span>
                        </div>
                      `
                    : ''}
                </div>
              `
            : ''}

          <button
            class="button"
            @click=${this.handleCheckHealth}
            ?disabled=${this.loading}
            aria-label="Check health status"
          >
            ${this.loading ? html`<span class="loading"></span>` : 'Check Health'}
          </button>
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'health-check': HealthCheck
  }
}
