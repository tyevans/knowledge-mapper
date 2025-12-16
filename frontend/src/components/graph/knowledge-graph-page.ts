import { LitElement, html, css } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import './knowledge-graph-viewer'

/**
 * Knowledge Graph Page Component
 *
 * Full-viewport container for the knowledge graph viewer.
 * Provides a minimal header with navigation and hosts the graph visualization.
 *
 * @fires view-entity - When user clicks to view an entity detail
 * @fires back - When user clicks the back button
 *
 * @slot header-actions - Slot for additional header actions (e.g., fullscreen button)
 * @slot floating-panels - Slot for floating panels (controls, legend, minimap)
 */
@customElement('knowledge-graph-page')
export class KnowledgeGraphPage extends LitElement {
  static styles = css`
    :host {
      display: block;
      height: 100vh;
      width: 100vw;
      overflow: hidden;
      position: relative;
      background: var(--km-graph-page-bg, #f3f4f6);
    }

    .header {
      height: var(--km-graph-header-height, 48px);
      background: var(--km-graph-header-bg, #1f2937);
      display: flex;
      align-items: center;
      padding: 0 1rem;
      gap: 1rem;
      box-sizing: border-box;
    }

    .back-button {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 0.75rem;
      background: transparent;
      border: 1px solid var(--km-graph-header-border, #374151);
      border-radius: 0.375rem;
      color: var(--km-graph-header-text, #d1d5db);
      font-size: 0.875rem;
      cursor: pointer;
      transition: background 0.2s, color 0.2s, border-color 0.2s;
    }

    .back-button:hover {
      background: var(--km-graph-header-hover-bg, #374151);
      color: var(--km-graph-header-hover-text, #ffffff);
      border-color: var(--km-graph-header-hover-border, #4b5563);
    }

    .back-button:focus {
      outline: 2px solid var(--km-focus-ring, #3b82f6);
      outline-offset: 2px;
    }

    .back-button:focus:not(:focus-visible) {
      outline: none;
    }

    .back-button:focus-visible {
      outline: 2px solid var(--km-focus-ring, #3b82f6);
      outline-offset: 2px;
    }

    .back-icon {
      width: 1rem;
      height: 1rem;
      flex-shrink: 0;
    }

    .title {
      margin: 0;
      font-size: 1rem;
      font-weight: 600;
      color: var(--km-graph-header-title, #ffffff);
      flex: 1;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .fullscreen-button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 2rem;
      height: 2rem;
      padding: 0;
      background: transparent;
      border: 1px solid var(--km-graph-header-border, #374151);
      border-radius: 0.375rem;
      color: var(--km-graph-header-text, #d1d5db);
      cursor: pointer;
      transition: background 0.2s, color 0.2s, border-color 0.2s;
    }

    .fullscreen-button:hover {
      background: var(--km-graph-header-hover-bg, #374151);
      color: var(--km-graph-header-hover-text, #ffffff);
      border-color: var(--km-graph-header-hover-border, #4b5563);
    }

    .fullscreen-button:focus {
      outline: 2px solid var(--km-focus-ring, #3b82f6);
      outline-offset: 2px;
    }

    .fullscreen-button:focus:not(:focus-visible) {
      outline: none;
    }

    .fullscreen-button:focus-visible {
      outline: 2px solid var(--km-focus-ring, #3b82f6);
      outline-offset: 2px;
    }

    .fullscreen-icon {
      width: 1rem;
      height: 1rem;
    }

    /* Fullscreen mode styles */
    :host(.fullscreen) .header {
      background: rgba(31, 41, 55, 0.9);
      backdrop-filter: blur(8px);
    }

    .graph-viewport {
      height: calc(100vh - var(--km-graph-header-height, 48px));
      width: 100%;
      position: relative;
      overflow: hidden;
    }

    .graph-viewport knowledge-graph-viewer {
      width: 100%;
      height: 100%;
    }

    /* Style the embedded viewer to fill the viewport */
    .graph-viewport knowledge-graph-viewer::part(card) {
      height: 100%;
      border-radius: 0;
    }
  `

  /**
   * Entity ID to center the graph on.
   * Passed to the knowledge-graph-viewer component.
   */
  @property({ type: String })
  centerId = ''

  /**
   * Whether the component is currently in fullscreen mode.
   */
  @state()
  private isFullscreen = false

  private boundHandleFullscreenChange = this.handleFullscreenChange.bind(this)

  connectedCallback(): void {
    super.connectedCallback()
    document.addEventListener('fullscreenchange', this.boundHandleFullscreenChange)
    // Check if already in fullscreen (e.g., on reconnect)
    this.isFullscreen = !!document.fullscreenElement
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    document.removeEventListener('fullscreenchange', this.boundHandleFullscreenChange)
  }

  /**
   * Handle fullscreen change events from the document.
   * Updates state when fullscreen is entered/exited via browser controls or Escape.
   */
  private handleFullscreenChange(): void {
    this.isFullscreen = !!document.fullscreenElement
    if (this.isFullscreen) {
      this.classList.add('fullscreen')
    } else {
      this.classList.remove('fullscreen')
    }
  }

  /**
   * Toggle fullscreen mode for this component.
   */
  private async toggleFullscreen(): Promise<void> {
    try {
      if (this.isFullscreen) {
        await document.exitFullscreen()
      } else {
        await this.requestFullscreen()
      }
    } catch (error) {
      console.error('Fullscreen toggle failed:', error)
    }
  }

  /**
   * Handle back button click.
   * Dispatches a 'back' event for parent navigation.
   */
  private handleBack(): void {
    this.dispatchEvent(
      new CustomEvent('back', {
        bubbles: true,
        composed: true,
      })
    )
  }

  /**
   * Forward view-entity events from the knowledge-graph-viewer.
   */
  private handleViewEntity(e: CustomEvent<{ entityId: string }>): void {
    this.dispatchEvent(
      new CustomEvent('view-entity', {
        detail: e.detail,
        bubbles: true,
        composed: true,
      })
    )
  }

  render() {
    return html`
      <div class="header" role="banner">
        <button
          class="back-button"
          @click=${this.handleBack}
          aria-label="Go back to previous page"
        >
          <svg
            class="back-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          <span>Back</span>
        </button>
        <h1 class="title">Knowledge Graph</h1>
        <div class="header-actions">
          <button
            class="fullscreen-button"
            @click=${this.toggleFullscreen}
            aria-label=${this.isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
            title=${this.isFullscreen ? 'Exit fullscreen (Esc)' : 'Enter fullscreen'}
          >
            ${this.isFullscreen
              ? html`
                  <svg
                    class="fullscreen-icon"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3" />
                  </svg>
                `
              : html`
                  <svg
                    class="fullscreen-icon"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
                  </svg>
                `}
          </button>
          <slot name="header-actions"></slot>
        </div>
      </div>

      <div class="graph-viewport">
        <knowledge-graph-viewer
          .centerId=${this.centerId}
          @view-entity=${this.handleViewEntity}
        ></knowledge-graph-viewer>

        <slot name="floating-panels"></slot>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'knowledge-graph-page': KnowledgeGraphPage
  }
}
