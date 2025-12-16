import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { EntityType } from '../../api/scraping-types'
import { ENTITY_TYPE_COLORS, ENTITY_TYPE_LABELS } from '../../api/scraping-types'
import './floating-panel'

/**
 * Graph Legend Component
 *
 * Displays a color legend for entity types in the knowledge graph
 * as a floating panel positioned in the bottom-left corner.
 *
 * @fires toggle - Forwarded from floating-panel when expanded/collapsed
 */
@customElement('graph-legend')
export class GraphLegend extends LitElement {
  static styles = css`
    :host {
      display: contents;
    }

    .legend-content {
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
      margin-top: 1rem;
      padding-top: 0.75rem;
      border-top: 1px solid #e5e7eb;
    }

    .hint {
      font-size: 0.6875rem;
      color: #6b7280;
      margin-bottom: 0.25rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .hint-icon {
      flex-shrink: 0;
      width: 14px;
      text-align: center;
      font-size: 0.875rem;
    }
  `

  /**
   * Initial collapsed state. When true, legend starts collapsed.
   * Defaults to true since legend is less critical than controls.
   */
  @property({ type: Boolean })
  collapsed = true

  render() {
    const entityTypes = Object.entries(ENTITY_TYPE_LABELS) as [EntityType, string][]

    return html`
      <floating-panel
        panel-title="Legend"
        position="bottom-left"
        collapsed-icon="(i)"
        .collapsed=${this.collapsed}
      >
        <div class="legend-content">
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
              <span class="hint-icon">Click</span>
              <span>Select node to view details</span>
            </div>
            <div class="hint">
              <span class="hint-icon">Drag</span>
              <span>Move nodes to rearrange</span>
            </div>
            <div class="hint">
              <span class="hint-icon">Scroll</span>
              <span>Zoom in/out</span>
            </div>
            <div class="hint">
              <span class="hint-icon">Pan</span>
              <span>Drag background to move view</span>
            </div>
          </div>
        </div>
      </floating-panel>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'graph-legend': GraphLegend
  }
}
