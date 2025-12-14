import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { authStore, type AuthState } from '../auth'
import { apiClient } from '../api/client'

interface ProtectedResponse {
  message: string
  user_id: string
  tenant_id: string
  email: string | null
}

/**
 * User Profile Component
 *
 * Displays user profile information when authenticated.
 * Demonstrates making authenticated API calls.
 */
@customElement('user-profile')
export class UserProfile extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .card {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
      overflow: hidden;
      max-width: 500px;
      margin: 0 auto;
    }

    .card-header {
      background: #1f2937;
      color: white;
      padding: 1.5rem;
    }

    .card-header h2 {
      margin: 0;
      font-size: 1.25rem;
    }

    .card-body {
      padding: 1.5rem;
    }

    .profile-item {
      display: flex;
      margin-bottom: 1rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid #e5e7eb;
    }

    .profile-item:last-child {
      margin-bottom: 0;
      padding-bottom: 0;
      border-bottom: none;
    }

    .profile-label {
      font-weight: 600;
      color: #374151;
      width: 120px;
      flex-shrink: 0;
    }

    .profile-value {
      color: #6b7280;
      word-break: break-all;
    }

    .api-test {
      margin-top: 1.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid #e5e7eb;
    }

    .api-test h3 {
      margin: 0 0 1rem 0;
      font-size: 1rem;
      color: #374151;
    }

    .test-btn {
      padding: 0.5rem 1rem;
      background: #667eea;
      color: white;
      border: none;
      border-radius: 0.375rem;
      cursor: pointer;
      font-size: 0.875rem;
      margin-right: 0.5rem;
    }

    .test-btn:hover {
      background: #5a67d8;
    }

    .test-btn:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    .api-result {
      margin-top: 1rem;
      padding: 1rem;
      border-radius: 0.375rem;
      font-family: monospace;
      font-size: 0.75rem;
      white-space: pre-wrap;
      word-break: break-all;
    }

    .api-result.success {
      background: #ecfdf5;
      color: #065f46;
      border: 1px solid #a7f3d0;
    }

    .api-result.error {
      background: #fef2f2;
      color: #991b1b;
      border: 1px solid #fecaca;
    }

    .not-authenticated {
      text-align: center;
      padding: 2rem;
      color: #6b7280;
    }

    .not-authenticated p {
      margin: 0 0 1rem 0;
    }
  `

  @state()
  private authState: AuthState = {
    user: null,
    isAuthenticated: false,
    isLoading: true,
    error: null,
  }

  @state()
  private apiResult: { success: boolean; data: string } | null = null

  @state()
  private isTestingApi = false

  private unsubscribe?: () => void

  connectedCallback(): void {
    super.connectedCallback()
    this.unsubscribe = authStore.subscribe((state) => {
      this.authState = state
    })
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.unsubscribe?.()
  }

  private async testProtectedEndpoint(): Promise<void> {
    this.isTestingApi = true
    this.apiResult = null

    try {
      const response = await apiClient.get<ProtectedResponse>('/api/v1/test/protected')

      if (response.success) {
        this.apiResult = {
          success: true,
          data: JSON.stringify(response.data, null, 2),
        }
      } else {
        this.apiResult = {
          success: false,
          data: `Error ${response.error.status}: ${response.error.message}`,
        }
      }
    } catch (err) {
      this.apiResult = {
        success: false,
        data: err instanceof Error ? err.message : 'Unknown error',
      }
    } finally {
      this.isTestingApi = false
    }
  }

  private async testPublicEndpoint(): Promise<void> {
    this.isTestingApi = true
    this.apiResult = null

    try {
      const response = await apiClient.get<unknown>('/api/v1/health', { authenticated: false })

      if (response.success) {
        this.apiResult = {
          success: true,
          data: JSON.stringify(response.data, null, 2),
        }
      } else {
        this.apiResult = {
          success: false,
          data: `Error ${response.error.status}: ${response.error.message}`,
        }
      }
    } catch (err) {
      this.apiResult = {
        success: false,
        data: err instanceof Error ? err.message : 'Unknown error',
      }
    } finally {
      this.isTestingApi = false
    }
  }

  render() {
    const { user, isAuthenticated, isLoading } = this.authState

    if (isLoading) {
      return html`<div class="card"><div class="card-body">Loading...</div></div>`
    }

    if (!isAuthenticated || !user) {
      return html`
        <div class="card">
          <div class="card-body not-authenticated">
            <p>Please log in to view your profile.</p>
            <div class="api-test">
              <h3>Test Public API</h3>
              <button
                class="test-btn"
                @click=${this.testPublicEndpoint}
                ?disabled=${this.isTestingApi}
              >
                ${this.isTestingApi ? 'Testing...' : 'Test /api/v1/health'}
              </button>
              ${this.apiResult
                ? html`
                    <div class="api-result ${this.apiResult.success ? 'success' : 'error'}">
                      ${this.apiResult.data}
                    </div>
                  `
                : null}
            </div>
          </div>
        </div>
      `
    }

    const { profile } = user

    return html`
      <div class="card">
        <div class="card-header">
          <h2>User Profile</h2>
        </div>
        <div class="card-body">
          <div class="profile-item">
            <span class="profile-label">Email</span>
            <span class="profile-value">${profile.email || 'N/A'}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">Name</span>
            <span class="profile-value">${profile.name || 'N/A'}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">User ID</span>
            <span class="profile-value">${profile.sub}</span>
          </div>
          <div class="profile-item">
            <span class="profile-label">Tenant ID</span>
            <span class="profile-value">${(profile as Record<string, unknown>).tenant_id || 'N/A'}</span>
          </div>

          <div class="api-test">
            <h3>Test API Endpoints</h3>
            <button
              class="test-btn"
              @click=${this.testProtectedEndpoint}
              ?disabled=${this.isTestingApi}
            >
              ${this.isTestingApi ? 'Testing...' : 'Test Protected API'}
            </button>
            <button
              class="test-btn"
              @click=${this.testPublicEndpoint}
              ?disabled=${this.isTestingApi}
            >
              ${this.isTestingApi ? 'Testing...' : 'Test Public API'}
            </button>
            ${this.apiResult
              ? html`
                  <div class="api-result ${this.apiResult.success ? 'success' : 'error'}">
                    ${this.apiResult.data}
                  </div>
                `
              : null}
          </div>
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'user-profile': UserProfile
  }
}
