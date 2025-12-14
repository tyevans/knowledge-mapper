import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { authStore, type AuthState } from '../auth'

/**
 * Login/Logout Button Component
 *
 * Shows login button when unauthenticated, user info and logout when authenticated.
 */
@customElement('login-button')
export class LoginButton extends LitElement {
  static styles = css`
    :host {
      display: inline-flex;
      align-items: center;
      gap: 0.75rem;
    }

    .user-info {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      color: white;
      font-size: 0.875rem;
    }

    .user-email {
      opacity: 0.9;
    }

    button {
      padding: 0.5rem 1rem;
      border: none;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
    }

    .login-btn {
      background: white;
      color: #667eea;
    }

    .login-btn:hover {
      background: #f0f0f0;
      transform: translateY(-1px);
    }

    .logout-btn {
      background: rgba(255, 255, 255, 0.2);
      color: white;
      border: 1px solid rgba(255, 255, 255, 0.3);
    }

    .logout-btn:hover {
      background: rgba(255, 255, 255, 0.3);
    }

    button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    .loading {
      display: inline-block;
      width: 1rem;
      height: 1rem;
      border: 2px solid transparent;
      border-top-color: currentColor;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }
  `

  @state()
  private authState: AuthState = {
    user: null,
    isAuthenticated: false,
    isLoading: true,
    error: null,
  }

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

  private async handleLogin(): Promise<void> {
    await authStore.login()
  }

  private async handleLogout(): Promise<void> {
    await authStore.logout()
  }

  render() {
    const { user, isAuthenticated, isLoading } = this.authState

    if (isLoading) {
      return html`<span class="loading"></span>`
    }

    if (isAuthenticated && user) {
      return html`
        <div class="user-info">
          <span class="user-email">${user.profile.email}</span>
        </div>
        <button class="logout-btn" @click=${this.handleLogout}>Logout</button>
      `
    }

    return html`
      <button class="login-btn" @click=${this.handleLogin}>Login</button>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'login-button': LoginButton
  }
}
