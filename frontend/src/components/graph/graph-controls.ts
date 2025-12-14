import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { EntityType } from '../../api/scraping-types'
import { ENTITY_TYPE_LABELS } from '../../api/scraping-types'

/**
 * Graph Controls Component
 *
 * Controls for the knowledge graph visualization.
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
      display: block;
    }

    .controls-section {
      padding: 1rem;
      border-bottom: 1px solid #e5e7eb;
    }

    .section-title {
      font-size: 0.75rem;
      font-weight: 600;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.75rem;
    }

    .control-group {
      margin-bottom: 1rem;
    }

    .control-group:last-child {
      margin-bottom: 0;
    }

    .control-label {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.875rem;
      color: #374151;
      margin-bottom: 0.5rem;
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
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: #1e3a8a;
      cursor: pointer;
    }

    .depth-slider::-moz-range-thumb {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: #1e3a8a;
      cursor: pointer;
      border: none;
    }

    .type-filter-list {
      display: flex;
      flex-direction: column;
      gap: 0.375rem;
    }

    .type-filter-item {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.875rem;
    }

    .type-filter-item input {
      width: 1rem;
      height: 1rem;
      accent-color: #1e3a8a;
      cursor: pointer;
    }

    .type-filter-item label {
      cursor: pointer;
      color: #374151;
    }

    .btn-group {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }

    .control-btn {
      padding: 0.5rem 1rem;
      font-size: 0.875rem;
      font-weight: 500;
      border-radius: 0.375rem;
      cursor: pointer;
      transition: all 0.2s;
      text-align: center;
    }

    .control-btn-primary {
      background: #1e3a8a;
      color: white;
      border: none;
    }

    .control-btn-primary:hover {
      background: #1e40af;
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

    .select-all-link {
      font-size: 0.75rem;
      color: #1e3a8a;
      cursor: pointer;
      text-decoration: none;
    }

    .select-all-link:hover {
      text-decoration: underline;
    }

    .filter-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.5rem;
    }
  `

  @property({ type: Number })
  depth = 2

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
      <div class="controls-section">
        <div class="section-title">Graph Settings</div>

        <div class="control-group">
          <div class="control-label">
            <span>Relationship Depth</span>
            <span class="control-value">${this.depth}</span>
          </div>
          <input
            type="range"
            class="depth-slider"
            min="1"
            max="5"
            .value=${this.depth.toString()}
            @change=${this.handleDepthChange}
          />
        </div>

        <div class="control-group">
          <div class="filter-header">
            <span class="control-label" style="margin-bottom: 0;">Entity Types</span>
            ${this.selectedTypes.length > 0
              ? html`
                  <span class="select-all-link" @click=${this.handleSelectAll}>
                    Show All
                  </span>
                `
              : null}
          </div>
          <div class="type-filter-list">
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
      </div>

      <div class="controls-section">
        <div class="section-title">View Controls</div>
        <div class="btn-group">
          <button class="control-btn control-btn-secondary" @click=${this.handleResetLayout}>
            Reset Layout
          </button>
          <button class="control-btn control-btn-secondary" @click=${this.handleFitView}>
            Fit to View
          </button>
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'graph-controls': GraphControls
  }
}
