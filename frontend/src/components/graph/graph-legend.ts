import { LitElement, html, css } from 'lit'
import { customElement } from 'lit/decorators.js'
import type { EntityType } from '../../api/scraping-types'
import { ENTITY_TYPE_COLORS, ENTITY_TYPE_LABELS } from '../../api/scraping-types'

/**
 * Graph Legend Component
 *
 * Displays a color legend for entity types in the knowledge graph.
 */
@customElement('graph-legend')
export class GraphLegend extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .legend-section {
      padding: 1rem;
    }

    .section-title {
      font-size: 0.75rem;
      font-weight: 600;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.75rem;
    }

    .legend-list {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }

    .legend-item {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.875rem;
      color: #374151;
    }

    .legend-color {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .legend-label {
      flex: 1;
    }

    .interaction-hints {
      margin-top: 1.5rem;
      padding-top: 1rem;
      border-top: 1px solid #e5e7eb;
    }

    .hint {
      font-size: 0.75rem;
      color: #6b7280;
      margin-bottom: 0.375rem;
      display: flex;
      align-items: flex-start;
      gap: 0.375rem;
    }

    .hint-icon {
      flex-shrink: 0;
      width: 14px;
      text-align: center;
    }
  `

  render() {
    const entityTypes = Object.entries(ENTITY_TYPE_LABELS) as [EntityType, string][]

    return html`
      <div class="legend-section">
        <div class="section-title">Entity Types</div>
        <div class="legend-list">
          ${entityTypes.map(
            ([type, label]) => html`
              <div class="legend-item">
                <div
                  class="legend-color"
                  style="background-color: ${ENTITY_TYPE_COLORS[type]}"
                ></div>
                <span class="legend-label">${label}</span>
              </div>
            `
          )}
        </div>

        <div class="interaction-hints">
          <div class="section-title">Interactions</div>
          <div class="hint">
            <span class="hint-icon">🖱️</span>
            <span>Click node to view entity details</span>
          </div>
          <div class="hint">
            <span class="hint-icon">✋</span>
            <span>Drag nodes to rearrange</span>
          </div>
          <div class="hint">
            <span class="hint-icon">🔍</span>
            <span>Scroll to zoom in/out</span>
          </div>
          <div class="hint">
            <span class="hint-icon">↔️</span>
            <span>Drag background to pan</span>
          </div>
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'graph-legend': GraphLegend
  }
}
