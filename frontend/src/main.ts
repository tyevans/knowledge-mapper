import { initObservability } from './observability'
import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import './components/health-check'
import './components/login-button'
import './components/auth-callback'
import './components/user-profile'
import './components/todo-list'
import './components/tenant-list'
import './components/tenant-selector'
import './components/tenant-switcher'
// Scraping components
import './components/scraping/scraping-dashboard'
import './components/scraping/scraping-job-detail'
// Entity components
import './components/entities/entity-explorer'
import './components/entities/entity-detail'
// Graph components
import './components/graph/knowledge-graph-viewer'
import './style.css'

// Initialize observability before any other code runs
initObservability()

type Route =
  | 'home'
  | 'callback'
  | 'profile'
  | 'tenants'
  | 'select-tenant'
  | 'scraping'
  | 'scraping-job-detail'
  | 'entities'
  | 'entity-detail'
  | 'knowledge-graph'

interface RouteParams {
  jobId?: string
  entityId?: string
}

/**
 * Main Application Component
 *
 * Handles routing and authentication state.
 */
@customElement('app-root')
export class AppRoot extends LitElement {
  static styles = css`
    :host {
      display: block;
      min-height: 100vh;
      background: #f3f4f6;
    }

    .header {
      background: #1f2937;
      padding: 1.5rem;
      border-bottom: 1px solid #374151;
    }

    .header-content {
      max-width: 1200px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
    }

    .logo-section {
      display: flex;
      flex-direction: column;
    }

    .logo {
      font-size: 1.5rem;
      font-weight: bold;
      color: white;
    }

    .subtitle {
      color: #9ca3af;
      font-size: 0.875rem;
    }

    .nav {
      display: flex;
      align-items: center;
      gap: 1rem;
    }

    .nav-link {
      color: #d1d5db;
      text-decoration: none;
      padding: 0.5rem 1rem;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      cursor: pointer;
      transition: background 0.2s, color 0.2s;
    }

    .nav-link:hover {
      background: #374151;
      color: white;
    }

    .nav-link.active {
      background: #374151;
      color: white;
    }

    .nav-separator {
      width: 1px;
      height: 24px;
      background: #374151;
    }

    .content {
      padding: 2rem 1rem;
      max-width: 1200px;
      margin: 0 auto;
    }

    .page-title {
      color: #111827;
      font-size: 1.5rem;
      margin-bottom: 1.5rem;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 1.5rem;
    }
  `

  @state()
  private currentRoute: Route = 'home'

  @state()
  private routeParams: RouteParams = {}

  connectedCallback(): void {
    super.connectedCallback()
    this.handleRoute()
    window.addEventListener('popstate', () => this.handleRoute())
  }

  private handleRoute(): void {
    const path = window.location.pathname
    this.routeParams = {}

    if (path === '/auth/callback') {
      this.currentRoute = 'callback'
    } else if (path === '/profile') {
      this.currentRoute = 'profile'
    } else if (path === '/tenants') {
      this.currentRoute = 'tenants'
    } else if (path === '/select-tenant') {
      this.currentRoute = 'select-tenant'
    } else if (path === '/scraping') {
      this.currentRoute = 'scraping'
    } else if (path.match(/^\/scraping\/jobs\/[0-9a-f-]+$/i)) {
      this.currentRoute = 'scraping-job-detail'
      this.routeParams.jobId = path.split('/')[3]
    } else if (path === '/entities') {
      this.currentRoute = 'entities'
    } else if (path.match(/^\/entities\/[0-9a-f-]+$/i)) {
      this.currentRoute = 'entity-detail'
      this.routeParams.entityId = path.split('/')[2]
    } else if (path === '/knowledge-graph') {
      this.currentRoute = 'knowledge-graph'
    } else if (path.match(/^\/knowledge-graph\/[0-9a-f-]+$/i)) {
      this.currentRoute = 'knowledge-graph'
      this.routeParams.entityId = path.split('/')[2]
    } else {
      this.currentRoute = 'home'
    }
  }

  private navigate(route: Route, params?: RouteParams): void {
    let path: string

    switch (route) {
      case 'home':
        path = '/'
        break
      case 'scraping-job-detail':
        path = `/scraping/jobs/${params?.jobId}`
        break
      case 'entity-detail':
        path = `/entities/${params?.entityId}`
        break
      case 'knowledge-graph':
        path = params?.entityId ? `/knowledge-graph/${params.entityId}` : '/knowledge-graph'
        break
      default:
        path = `/${route}`
    }

    window.history.pushState({}, '', path)
    this.currentRoute = route
    this.routeParams = params || {}
  }

  private renderNav() {
    const isScrapingActive = this.currentRoute === 'scraping' || this.currentRoute === 'scraping-job-detail'
    const isEntitiesActive = this.currentRoute === 'entities' || this.currentRoute === 'entity-detail'

    return html`
      <nav class="nav">
        <span
          class="nav-link ${this.currentRoute === 'home' ? 'active' : ''}"
          @click=${() => this.navigate('home')}
        >
          Home
        </span>
        <span
          class="nav-link ${isScrapingActive ? 'active' : ''}"
          @click=${() => this.navigate('scraping')}
        >
          Scraping
        </span>
        <span
          class="nav-link ${isEntitiesActive ? 'active' : ''}"
          @click=${() => this.navigate('entities')}
        >
          Entities
        </span>
        <span
          class="nav-link ${this.currentRoute === 'knowledge-graph' ? 'active' : ''}"
          @click=${() => this.navigate('knowledge-graph')}
        >
          Graph
        </span>
        <div class="nav-separator"></div>
        <span
          class="nav-link ${this.currentRoute === 'profile' ? 'active' : ''}"
          @click=${() => this.navigate('profile')}
        >
          Profile
        </span>
        <span
          class="nav-link ${this.currentRoute === 'tenants' ? 'active' : ''}"
          @click=${() => this.navigate('tenants')}
        >
          Tenants
        </span>
        <div class="nav-separator"></div>
        <tenant-switcher></tenant-switcher>
        <login-button></login-button>
      </nav>
    `
  }

  private renderPage() {
    switch (this.currentRoute) {
      case 'callback':
        return html`<auth-callback></auth-callback>`

      case 'select-tenant':
        return html`<tenant-selector></tenant-selector>`

      case 'profile':
        return html`
          <h1 class="page-title">Your Profile</h1>
          <user-profile></user-profile>
        `

      case 'tenants':
        return html`
          <h1 class="page-title">Tenant Management</h1>
          <tenant-list></tenant-list>
        `

      case 'scraping':
        return html`
          <h1 class="page-title">Web Scraping Jobs</h1>
          <scraping-dashboard
            @view-job=${(e: CustomEvent) => this.navigate('scraping-job-detail', { jobId: e.detail.jobId })}
          ></scraping-dashboard>
        `

      case 'scraping-job-detail':
        return html`
          <scraping-job-detail
            .jobId=${this.routeParams.jobId || ''}
            @back=${() => this.navigate('scraping')}
            @view-entity=${(e: CustomEvent) => this.navigate('entity-detail', { entityId: e.detail.entityId })}
            @view-graph=${(e: CustomEvent) => this.navigate('knowledge-graph', { entityId: e.detail.entityId })}
          ></scraping-job-detail>
        `

      case 'entities':
        return html`
          <h1 class="page-title">Entity Explorer</h1>
          <entity-explorer
            @view-entity=${(e: CustomEvent) => this.navigate('entity-detail', { entityId: e.detail.entityId })}
          ></entity-explorer>
        `

      case 'entity-detail':
        return html`
          <entity-detail
            .entityId=${this.routeParams.entityId || ''}
            @back=${() => this.navigate('entities')}
            @view-graph=${(e: CustomEvent) => this.navigate('knowledge-graph', { entityId: e.detail.entityId })}
            @view-entity=${(e: CustomEvent) => this.navigate('entity-detail', { entityId: e.detail.entityId })}
          ></entity-detail>
        `

      case 'knowledge-graph':
        return html`
          <h1 class="page-title">Knowledge Graph</h1>
          <knowledge-graph-viewer
            .centerId=${this.routeParams.entityId || ''}
            @view-entity=${(e: CustomEvent) => this.navigate('entity-detail', { entityId: e.detail.entityId })}
          ></knowledge-graph-viewer>
        `

      case 'home':
      default:
        return html`
          <h1 class="page-title">Todo Application</h1>
          <div class="grid">
            <health-check></health-check>
            <todo-list></todo-list>
          </div>
        `
    }
  }

  render() {
    // Auth callback and tenant selector pages have their own full-screen layout
    if (this.currentRoute === 'callback') {
      return html`<auth-callback></auth-callback>`
    }

    if (this.currentRoute === 'select-tenant') {
      return html`<tenant-selector></tenant-selector>`
    }

    return html`
      <div class="header">
        <div class="header-content">
          <div class="logo-section">
            <div class="logo">Knowledge Mapper</div>
            <div class="subtitle">Frontend Application</div>
          </div>
          ${this.renderNav()}
        </div>
      </div>
      <div class="content">
        ${this.renderPage()}
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'app-root': AppRoot
  }
}
