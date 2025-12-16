import { LitElement, html, css } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import type { GraphNode } from '../../api/scraping-types'
import { ENTITY_TYPE_COLORS } from '../../api/scraping-types'
import './floating-panel'

/**
 * Map icon SVG for collapsed panel state.
 */
const MAP_ICON = html`
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
    <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"></polygon>
    <line x1="9" y1="3" x2="9" y2="18"></line>
    <line x1="15" y1="6" x2="15" y2="21"></line>
  </svg>
`

interface NodePosition {
  id: string
  x: number
  y: number
  entityType: string
}

interface ViewportBounds {
  x: number
  y: number
  width: number
  height: number
}

/**
 * Graph Minimap Component
 *
 * Shows a bird's eye view of the entire graph with the current viewport highlighted.
 * Allows clicking to navigate to different areas.
 *
 * @fires navigate - When user clicks on the minimap to navigate
 */
@customElement('graph-minimap')
export class GraphMinimap extends LitElement {
  static styles = css`
    :host {
      display: contents;
    }

    .minimap-content {
      padding: 0.5rem;
    }

    .minimap-canvas {
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 0.25rem;
      cursor: crosshair;
      display: block;
    }

    .minimap-canvas:hover {
      border-color: #1e3a8a;
    }
  `

  @property({ type: Array })
  nodePositions: NodePosition[] = []

  @property({ type: Object })
  viewport: ViewportBounds | null = null

  @property({ type: Object })
  graphBounds: { minX: number; minY: number; maxX: number; maxY: number } | null = null

  @state()
  private minimapWidth = 160

  @state()
  private minimapHeight = 100

  private canvasRef: HTMLCanvasElement | null = null

  updated(changedProperties: Map<string, unknown>): void {
    if (
      changedProperties.has('nodePositions') ||
      changedProperties.has('viewport') ||
      changedProperties.has('graphBounds')
    ) {
      this.drawMinimap()
    }
  }

  private drawMinimap(): void {
    const canvas = this.shadowRoot?.querySelector('.minimap-canvas') as HTMLCanvasElement
    if (!canvas) return

    this.canvasRef = canvas
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Clear canvas
    ctx.clearRect(0, 0, this.minimapWidth, this.minimapHeight)

    if (!this.graphBounds || this.nodePositions.length === 0) {
      // Draw empty state
      ctx.fillStyle = '#e5e7eb'
      ctx.fillRect(0, 0, this.minimapWidth, this.minimapHeight)
      ctx.fillStyle = '#9ca3af'
      ctx.font = '10px system-ui'
      ctx.textAlign = 'center'
      ctx.fillText('No data', this.minimapWidth / 2, this.minimapHeight / 2)
      return
    }

    const { minX, minY, maxX, maxY } = this.graphBounds
    const graphWidth = maxX - minX || 1
    const graphHeight = maxY - minY || 1

    // Calculate scale to fit graph in minimap with padding
    const padding = 10
    const scaleX = (this.minimapWidth - padding * 2) / graphWidth
    const scaleY = (this.minimapHeight - padding * 2) / graphHeight
    const scale = Math.min(scaleX, scaleY)

    // Calculate offset to center the graph
    const offsetX = padding + (this.minimapWidth - padding * 2 - graphWidth * scale) / 2
    const offsetY = padding + (this.minimapHeight - padding * 2 - graphHeight * scale) / 2

    // Draw nodes as small dots
    this.nodePositions.forEach((node) => {
      const x = (node.x - minX) * scale + offsetX
      const y = (node.y - minY) * scale + offsetY

      ctx.beginPath()
      ctx.arc(x, y, 2, 0, Math.PI * 2)
      ctx.fillStyle = ENTITY_TYPE_COLORS[node.entityType as keyof typeof ENTITY_TYPE_COLORS] || '#6b7280'
      ctx.fill()
    })

    // Draw viewport rectangle if available
    if (this.viewport) {
      const vpX = (this.viewport.x - minX) * scale + offsetX
      const vpY = (this.viewport.y - minY) * scale + offsetY
      const vpWidth = this.viewport.width * scale
      const vpHeight = this.viewport.height * scale

      ctx.strokeStyle = '#1e3a8a'
      ctx.lineWidth = 2
      ctx.strokeRect(vpX, vpY, vpWidth, vpHeight)

      ctx.fillStyle = 'rgba(30, 58, 138, 0.1)'
      ctx.fillRect(vpX, vpY, vpWidth, vpHeight)
    }
  }

  private handleMinimapClick(event: MouseEvent): void {
    if (!this.graphBounds || !this.canvasRef) return

    const rect = this.canvasRef.getBoundingClientRect()
    const clickX = event.clientX - rect.left
    const clickY = event.clientY - rect.top

    const { minX, minY, maxX, maxY } = this.graphBounds
    const graphWidth = maxX - minX || 1
    const graphHeight = maxY - minY || 1

    const padding = 10
    const scaleX = (this.minimapWidth - padding * 2) / graphWidth
    const scaleY = (this.minimapHeight - padding * 2) / graphHeight
    const scale = Math.min(scaleX, scaleY)

    const offsetX = padding + (this.minimapWidth - padding * 2 - graphWidth * scale) / 2
    const offsetY = padding + (this.minimapHeight - padding * 2 - graphHeight * scale) / 2

    // Convert click position to graph coordinates
    const graphX = (clickX - offsetX) / scale + minX
    const graphY = (clickY - offsetY) / scale + minY

    this.dispatchEvent(
      new CustomEvent('navigate', {
        detail: { x: graphX, y: graphY },
        bubbles: true,
        composed: true,
      })
    )
  }

  render() {
    return html`
      <floating-panel
        panel-title="Minimap"
        position="bottom-right"
        .collapsedIcon=${MAP_ICON}
        .collapsed=${true}
        collapsible
      >
        <div class="minimap-content">
          <canvas
            class="minimap-canvas"
            width="${this.minimapWidth}"
            height="${this.minimapHeight}"
            @click=${this.handleMinimapClick}
            title="Click to navigate"
          ></canvas>
        </div>
      </floating-panel>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'graph-minimap': GraphMinimap
  }
}
