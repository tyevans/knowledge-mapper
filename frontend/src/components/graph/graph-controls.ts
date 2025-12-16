import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { EntityType } from '../../api/scraping-types'
import { ENTITY_TYPE_LABELS } from '../../api/scraping-types'
import './floating-panel'

/**
 * Settings/Cog icon SVG for collapsed panel state.
 */
const SETTINGS_ICON = html`
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="3"></circle>
    <path
      d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"
    ></path>
  </svg>
`

/**
 * Graph Controls Component
 *
 * Controls for the knowledge graph visualization, wrapped in a floating panel
 * for overlay display over the graph canvas.
 *
 * @fires depth-change - When depth slider changes
 * @fires type-filter-change - When entity type filter changes
 * @fires reset-layout - When reset layout button is clicked
 * @fires fit-view - When fit view button is clicked
 */
@customElement('graph-controls')
export class GraphControls extends LitElement {
  static styles = css`
    :host {
      display: contents; /* Let floating-panel handle positioning */
    }

    .controls-content {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      padding: 0.75rem;
    }

    .section {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }

    .section-title {
      font-size: 0.6875rem;
      font-weight: 600;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin: 0;
    }

    .control-group {
      display: flex;
      flex-direction: column;
      gap: 0.375rem;
    }

    .control-label {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.8125rem;
      color: #374151;
    }

    .control-value {
      font-weight: 500;
      color: #1e3a8a;
    }

    .depth-slider {
      width: 100%;
      height: 6px;
      border-radius: 3px;
      background: #e5e7eb;
      outline: none;
      -webkit-appearance: none;
      cursor: pointer;
    }

    .depth-slider::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: #1e3a8a;
      cursor: pointer;
    }

    .depth-slider::-moz-range-thumb {
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: #1e3a8a;
      cursor: pointer;
      border: none;
    }

    .depth-slider:focus {
      outline: 2px solid #1e3a8a;
      outline-offset: 2px;
    }

    .depth-slider:focus:not(:focus-visible) {
      outline: none;
    }

    .type-filter-list {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      max-height: 160px;
      overflow-y: auto;
      padding-right: 0.25rem;
    }

    /* Scrollbar styling for filter list */
    .type-filter-list::-webkit-scrollbar {
      width: 4px;
    }

    .type-filter-list::-webkit-scrollbar-track {
      background: #f1f5f9;
      border-radius: 2px;
    }

    .type-filter-list::-webkit-scrollbar-thumb {
      background: #cbd5e1;
      border-radius: 2px;
    }

    .type-filter-list::-webkit-scrollbar-thumb:hover {
      background: #94a3b8;
    }

    .type-filter-item {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.8125rem;
    }

    .type-filter-item input {
      width: 0.875rem;
      height: 0.875rem;
      accent-color: #1e3a8a;
      cursor: pointer;
      flex-shrink: 0;
    }

    .type-filter-item label {
      cursor: pointer;
      color: #374151;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .filter-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .select-all-link {
      font-size: 0.6875rem;
      color: #1e3a8a;
      cursor: pointer;
      text-decoration: none;
      padding: 0.125rem 0.25rem;
      border-radius: 0.25rem;
    }

    .select-all-link:hover {
      text-decoration: underline;
      background: #f0f5ff;
    }

    .select-all-link:focus {
      outline: 2px solid #1e3a8a;
      outline-offset: 1px;
    }

    .select-all-link:focus:not(:focus-visible) {
      outline: none;
    }

    .section-divider {
      border: none;
      border-top: 1px solid #e5e7eb;
      margin: 0.25rem 0;
    }

    .btn-group {
      display: flex;
      gap: 0.5rem;
    }

    .control-btn {
      flex: 1;
      padding: 0.375rem 0.5rem;
      font-size: 0.75rem;
      font-weight: 500;
      border-radius: 0.375rem;
      cursor: pointer;
      transition: all 0.15s;
      text-align: center;
      white-space: nowrap;
    }

    .control-btn-secondary {
      background: white;
      color: #374151;
      border: 1px solid #d1d5db;
    }

    .control-btn-secondary:hover {
      background: #f9fafb;
      border-color: #1e3a8a;
      color: #1e3a8a;
    }

    .control-btn-secondary:focus {
      outline: 2px solid #1e3a8a;
      outline-offset: 1px;
    }

    .control-btn-secondary:focus:not(:focus-visible) {
      outline: none;
    }

    /* High contrast mode support */
    @media (prefers-contrast: high) {
      .control-btn-secondary {
        border-width: 2px;
      }

      .depth-slider:focus,
      .control-btn-secondary:focus,
      .select-all-link:focus {
        outline-width: 3px;
      }
    }

    /* Reduced motion support */
    @media (prefers-reduced-motion: reduce) {
      .control-btn {
        transition: none;
      }
    }
  `

  @property({ type: Number })
  depth = 2

  @property({ type: Number })
  confidenceThreshold = 0

  @property({ type: Array })
  selectedTypes: EntityType[] = []

  private handleDepthChange(e: Event): void {
    const value = parseInt((e.target as HTMLInputElement).value, 10)
    this.dispatchEvent(
      new CustomEvent('depth-change', {
        detail: { depth: value },
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleConfidenceChange(e: Event): void {
    const value = parseFloat((e.target as HTMLInputElement).value)
    this.dispatchEvent(
      new CustomEvent('confidence-change', {
        detail: { threshold: value },
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleTypeToggle(type: EntityType, checked: boolean): void {
    let newTypes: EntityType[]

    if (checked) {
      newTypes = [...this.selectedTypes, type]
    } else {
      newTypes = this.selectedTypes.filter((t) => t !== type)
    }

    this.dispatchEvent(
      new CustomEvent('type-filter-change', {
        detail: { types: newTypes },
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleSelectAll(): void {
    this.dispatchEvent(
      new CustomEvent('type-filter-change', {
        detail: { types: [] },
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleResetLayout(): void {
    this.dispatchEvent(
      new CustomEvent('reset-layout', {
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleFitView(): void {
    this.dispatchEvent(
      new CustomEvent('fit-view', {
        bubbles: true,
        composed: true,
      })
    )
  }

  render() {
    const entityTypes = Object.entries(ENTITY_TYPE_LABELS) as [EntityType, string][]

    return html`
      <floating-panel
        panel-title="Controls"
        position="top-left"
        .collapsedIcon=${SETTINGS_ICON}
        .collapsed=${false}
        collapsible
      >
        <div class="controls-content">
          <!-- Graph Settings Section -->
          <div class="section">
            <h4 class="section-title">Graph Settings</h4>

            <div class="control-group">
              <div class="control-label">
                <label for="depth-slider">Relationship Depth</label>
                <span class="control-value">${this.depth}</span>
              </div>
              <input
                id="depth-slider"
                type="range"
                class="depth-slider"
                min="1"
                max="5"
                .value=${this.depth.toString()}
                @change=${this.handleDepthChange}
                aria-label="Relationship depth from 1 to 5"
              />
            </div>

            <div class="control-group">
              <div class="control-label">
                <label for="confidence-slider">Min Confidence</label>
                <span class="control-value">${Math.round(this.confidenceThreshold * 100)}%</span>
              </div>
              <input
                id="confidence-slider"
                type="range"
                class="depth-slider"
                min="0"
                max="1"
                step="0.1"
                .value=${this.confidenceThreshold.toString()}
                @input=${this.handleConfidenceChange}
                aria-label="Minimum confidence threshold from 0 to 100 percent"
              />
            </div>
          </div>

          <hr class="section-divider" />

          <!-- Entity Types Section -->
          <div class="section">
            <div class="filter-header">
              <h4 class="section-title">Entity Types</h4>
              ${this.selectedTypes.length > 0
                ? html`
                    <button
                      type="button"
                      class="select-all-link"
                      @click=${this.handleSelectAll}
                      @keydown=${(e: KeyboardEvent) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          this.handleSelectAll()
                        }
                      }}
                    >
                      Show All
                    </button>
                  `
                : null}
            </div>
            <div class="type-filter-list" role="group" aria-label="Entity type filters">
              ${entityTypes.map(
                ([type, label]) => html`
                  <div class="type-filter-item">
                    <input
                      type="checkbox"
                      id="type-${type}"
                      .checked=${this.selectedTypes.length === 0 ||
                      this.selectedTypes.includes(type)}
                      @change=${(e: Event) =>
                        this.handleTypeToggle(type, (e.target as HTMLInputElement).checked)}
                    />
                    <label for="type-${type}">${label}</label>
                  </div>
                `
              )}
            </div>
          </div>

          <hr class="section-divider" />

          <!-- View Controls Section -->
          <div class="section">
            <h4 class="section-title">View Controls</h4>
            <div class="btn-group">
              <button
                type="button"
                class="control-btn control-btn-secondary"
                @click=${this.handleResetLayout}
                title="Reset the graph layout simulation"
              >
                Reset Layout
              </button>
              <button
                type="button"
                class="control-btn control-btn-secondary"
                @click=${this.handleFitView}
                title="Fit all nodes in view"
              >
                Fit to View
              </button>
            </div>
          </div>
        </div>
      </floating-panel>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'graph-controls': GraphControls
  }
}
