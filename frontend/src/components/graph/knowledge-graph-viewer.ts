import { LitElement, html, css } from 'lit'
import { customElement, property, state, query } from 'lit/decorators.js'
import { authStore, type AuthState } from '../../auth'
import { apiClient } from '../../api/client'
import type {
  GraphQueryResponse,
  GraphNode,
  GraphEdge,
  EntityType,
} from '../../api/scraping-types'
import { ENTITY_TYPE_COLORS, ENTITY_TYPE_LABELS } from '../../api/scraping-types'
import * as d3 from 'd3'
import './graph-controls'
import './graph-legend'

interface SimulationNode extends d3.SimulationNodeDatum {
  id: string
  entity_type: EntityType
  name: string
  properties: Record<string, unknown>
}

interface SimulationLink extends d3.SimulationLinkDatum<SimulationNode> {
  source: SimulationNode | string
  target: SimulationNode | string
  relationship_type: string
  confidence: number
}

/**
 * Knowledge Graph Viewer Component
 *
 * Interactive D3.js visualization of the knowledge graph.
 *
 * @fires view-entity - When user clicks to view an entity detail
 */
@customElement('knowledge-graph-viewer')
export class KnowledgeGraphViewer extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .card {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
      overflow: hidden;
    }

    .card-header {
      background: #1f2937;
      color: white;
      padding: 1rem 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .card-header h2 {
      margin: 0;
      font-size: 1.125rem;
    }

    .stats {
      display: flex;
      gap: 1rem;
      font-size: 0.875rem;
    }

    .stat {
      background: rgba(255, 255, 255, 0.2);
      padding: 0.25rem 0.5rem;
      border-radius: 0.25rem;
    }

    .graph-container {
      position: relative;
      display: flex;
    }

    .graph-svg-container {
      flex: 1;
      height: 600px;
      background: #f9fafb;
      overflow: hidden;
    }

    .graph-svg {
      width: 100%;
      height: 100%;
    }

    .sidebar {
      width: 280px;
      border-left: 1px solid #e5e7eb;
      background: white;
      overflow-y: auto;
      max-height: 600px;
    }

    .node {
      cursor: pointer;
    }

    .node:hover circle {
      stroke-width: 3px;
    }

    .link {
      stroke: #94a3b8;
      stroke-opacity: 0.6;
      fill: none;
    }

    .link-label {
      font-size: 10px;
      fill: #64748b;
      pointer-events: none;
    }

    .node-label {
      font-size: 11px;
      fill: #1f2937;
      pointer-events: none;
      text-anchor: middle;
    }

    .tooltip {
      position: absolute;
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      padding: 0.75rem;
      font-size: 0.75rem;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      pointer-events: none;
      z-index: 1000;
      max-width: 200px;
    }

    .tooltip-title {
      font-weight: 600;
      color: #1f2937;
      margin-bottom: 0.25rem;
    }

    .tooltip-type {
      color: #6b7280;
      margin-bottom: 0.5rem;
    }

    .tooltip-props {
      font-size: 0.6875rem;
      color: #4b5563;
    }

    .loading {
      display: flex;
      align-items: center;
      justify-content: center;
      height: 400px;
      color: #6b7280;
    }

    .error {
      background: #fef2f2;
      color: #991b1b;
      padding: 0.75rem;
      margin: 1rem;
      border-radius: 0.375rem;
      font-size: 0.875rem;
    }

    .empty-state {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 400px;
      color: #6b7280;
      text-align: center;
    }

    .empty-state-icon {
      font-size: 3rem;
      margin-bottom: 1rem;
    }

    .empty-state-title {
      font-size: 1rem;
      font-weight: 500;
      color: #374151;
      margin-bottom: 0.5rem;
    }

    .empty-state-message {
      font-size: 0.875rem;
    }

    .unauthorized {
      text-align: center;
      padding: 3rem;
      color: #6b7280;
    }
  `

  @property({ type: String })
  centerId = ''

  @state()
  private authState: AuthState | null = null

  @state()
  private graphData: GraphQueryResponse | null = null

  @state()
  private isLoading = true

  @state()
  private error: string | null = null

  @state()
  private depth = 2

  @state()
  private selectedTypes: EntityType[] = []

  @state()
  private tooltipData: { node: SimulationNode; x: number; y: number } | null = null

  @query('.graph-svg')
  private svgElement!: SVGSVGElement

  @query('.graph-svg-container')
  private containerElement!: HTMLDivElement

  private simulation: d3.Simulation<SimulationNode, SimulationLink> | null = null
  private unsubscribe?: () => void

  connectedCallback(): void {
    super.connectedCallback()
    this.unsubscribe = authStore.subscribe((state) => {
      const wasAuthenticated = this.authState?.isAuthenticated
      this.authState = state

      if (state.isAuthenticated && !wasAuthenticated) {
        this.loadGraph()
      }
    })

    if (this.authState?.isAuthenticated) {
      this.loadGraph()
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.unsubscribe?.()
    this.simulation?.stop()
  }

  updated(changedProperties: Map<string, unknown>): void {
    if (changedProperties.has('centerId') && this.authState?.isAuthenticated) {
      this.loadGraph()
    }
  }

  private async loadGraph(): Promise<void> {
    this.isLoading = true
    this.error = null

    try {
      const params = new URLSearchParams({
        depth: this.depth.toString(),
        limit: '100',
      })

      if (this.centerId) {
        params.set('entity_id', this.centerId)
      }

      if (this.selectedTypes.length > 0) {
        this.selectedTypes.forEach((t) => params.append('entity_types', t))
      }

      const response = await apiClient.get<GraphQueryResponse>(
        `/api/v1/graph/query?${params.toString()}`
      )

      if (response.success) {
        this.graphData = response.data
        // Wait for render then init graph
        await this.updateComplete
        this.initGraph()
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to load graph'
    } finally {
      this.isLoading = false
    }
  }

  private initGraph(): void {
    if (!this.graphData || !this.svgElement || !this.containerElement) return

    // Clear previous graph
    d3.select(this.svgElement).selectAll('*').remove()
    this.simulation?.stop()

    const { nodes, edges } = this.graphData

    if (nodes.length === 0) return

    const width = this.containerElement.clientWidth
    const height = this.containerElement.clientHeight

    const svg = d3.select(this.svgElement)

    // Create zoom behavior
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        container.attr('transform', event.transform)
      })

    svg.call(zoom)

    const container = svg.append('g')

    // Arrow marker for directed edges
    svg.append('defs').append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .append('path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', '#94a3b8')

    // Convert data to simulation format
    const simNodes: SimulationNode[] = nodes.map((n) => ({
      ...n,
      x: width / 2 + (Math.random() - 0.5) * 100,
      y: height / 2 + (Math.random() - 0.5) * 100,
    }))

    const nodeMap = new Map(simNodes.map((n) => [n.id, n]))

    const simLinks: SimulationLink[] = edges
      .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e) => ({
        source: e.source,
        target: e.target,
        relationship_type: e.relationship_type,
        confidence: e.confidence,
      }))

    // Create force simulation
    this.simulation = d3.forceSimulation<SimulationNode>(simNodes)
      .force('link', d3.forceLink<SimulationNode, SimulationLink>(simLinks)
        .id((d) => d.id)
        .distance(100))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(40))

    // Create links
    const link = container.append('g')
      .selectAll('line')
      .data(simLinks)
      .join('line')
      .attr('class', 'link')
      .attr('stroke-width', (d) => Math.max(1, d.confidence * 3))
      .attr('marker-end', 'url(#arrowhead)')

    // Create link labels
    const linkLabel = container.append('g')
      .selectAll('text')
      .data(simLinks)
      .join('text')
      .attr('class', 'link-label')
      .text((d) => d.relationship_type)

    // Create nodes
    const node = container.append('g')
      .selectAll('g')
      .data(simNodes)
      .join('g')
      .attr('class', 'node')
      .call(this.createDragBehavior())
      .on('click', (_event, d) => this.handleNodeClick(d))
      .on('mouseenter', (event, d) => this.showTooltip(event, d))
      .on('mouseleave', () => this.hideTooltip())

    node.append('circle')
      .attr('r', (d) => d.id === this.centerId ? 18 : 14)
      .attr('fill', (d) => ENTITY_TYPE_COLORS[d.entity_type] || '#6b7280')
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)

    node.append('text')
      .attr('class', 'node-label')
      .attr('dy', 28)
      .text((d) => this.truncateLabel(d.name))

    // Update positions on tick
    this.simulation.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as SimulationNode).x!)
        .attr('y1', (d) => (d.source as SimulationNode).y!)
        .attr('x2', (d) => (d.target as SimulationNode).x!)
        .attr('y2', (d) => (d.target as SimulationNode).y!)

      linkLabel
        .attr('x', (d) =>
          ((d.source as SimulationNode).x! + (d.target as SimulationNode).x!) / 2
        )
        .attr('y', (d) =>
          ((d.source as SimulationNode).y! + (d.target as SimulationNode).y!) / 2
        )

      node.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })

    // Center on initial node if provided
    if (this.centerId) {
      const centerNode = nodeMap.get(this.centerId)
      if (centerNode) {
        centerNode.fx = width / 2
        centerNode.fy = height / 2
        setTimeout(() => {
          centerNode.fx = null
          centerNode.fy = null
        }, 2000)
      }
    }
  }

  private createDragBehavior() {
    return d3.drag<SVGGElement, SimulationNode>()
      .on('start', (event, d) => {
        if (!event.active) this.simulation?.alphaTarget(0.3).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x
        d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) this.simulation?.alphaTarget(0)
        d.fx = null
        d.fy = null
      })
  }

  private truncateLabel(label: string): string {
    return label.length > 20 ? label.substring(0, 18) + '...' : label
  }

  private handleNodeClick(node: SimulationNode): void {
    this.dispatchEvent(
      new CustomEvent('view-entity', {
        detail: { entityId: node.id },
        bubbles: true,
        composed: true,
      })
    )
  }

  private showTooltip(event: MouseEvent, node: SimulationNode): void {
    const rect = this.containerElement.getBoundingClientRect()
    this.tooltipData = {
      node,
      x: event.clientX - rect.left + 10,
      y: event.clientY - rect.top + 10,
    }
  }

  private hideTooltip(): void {
    this.tooltipData = null
  }

  private handleDepthChange(e: CustomEvent): void {
    this.depth = e.detail.depth
    this.loadGraph()
  }

  private handleTypeFilterChange(e: CustomEvent): void {
    this.selectedTypes = e.detail.types
    this.loadGraph()
  }

  private handleResetLayout(): void {
    if (this.simulation) {
      this.simulation.alpha(1).restart()
    }
  }

  private handleFitView(): void {
    if (!this.svgElement || !this.graphData?.nodes.length) return

    const svg = d3.select(this.svgElement)
    const container = svg.select('g')
    const bounds = (container.node() as SVGGElement)?.getBBox()

    if (!bounds) return

    const width = this.containerElement.clientWidth
    const height = this.containerElement.clientHeight

    const scale = Math.min(
      0.9 * width / bounds.width,
      0.9 * height / bounds.height,
      1
    )

    const translateX = (width - bounds.width * scale) / 2 - bounds.x * scale
    const translateY = (height - bounds.height * scale) / 2 - bounds.y * scale

    svg.transition()
      .duration(750)
      .call(
        (d3.zoom<SVGSVGElement, unknown>() as d3.ZoomBehavior<SVGSVGElement, unknown>)
          .transform as (
            selection: d3.Transition<SVGSVGElement, unknown, null, undefined>,
            transform: d3.ZoomTransform
          ) => void,
        d3.zoomIdentity.translate(translateX, translateY).scale(scale)
      )
  }

  private renderTooltip() {
    if (!this.tooltipData) return null

    const { node, x, y } = this.tooltipData
    const props = Object.entries(node.properties).slice(0, 3)

    return html`
      <div class="tooltip" style="left: ${x}px; top: ${y}px;">
        <div class="tooltip-title">${node.name}</div>
        <div class="tooltip-type">${ENTITY_TYPE_LABELS[node.entity_type]}</div>
        ${props.length > 0
          ? html`
              <div class="tooltip-props">
                ${props.map(
                  ([key, value]) =>
                    html`<div>${key}: ${String(value).substring(0, 30)}</div>`
                )}
              </div>
            `
          : null}
      </div>
    `
  }

  render() {
    if (!this.authState?.isAuthenticated) {
      return html`
        <div class="card">
          <div class="card-body">
            <div class="unauthorized">
              <div style="font-size: 3rem; margin-bottom: 1rem;">🔒</div>
              <p>Please log in to view the knowledge graph.</p>
            </div>
          </div>
        </div>
      `
    }

    return html`
      <div class="card">
        <div class="card-header">
          <h2>Knowledge Graph</h2>
          ${this.graphData
            ? html`
                <div class="stats">
                  <span class="stat">${this.graphData.total_nodes} nodes</span>
                  <span class="stat">${this.graphData.total_edges} edges</span>
                  ${this.graphData.truncated
                    ? html`<span class="stat">truncated</span>`
                    : null}
                </div>
              `
            : null}
        </div>

        ${this.error ? html`<div class="error">${this.error}</div>` : null}

        <div class="graph-container">
          <div class="graph-svg-container">
            ${this.isLoading
              ? html`<div class="loading">Loading graph...</div>`
              : this.graphData?.nodes.length === 0
              ? html`
                  <div class="empty-state">
                    <div class="empty-state-icon">🕸️</div>
                    <div class="empty-state-title">No graph data available</div>
                    <div class="empty-state-message">
                      Extract entities from web pages to build your knowledge graph.
                    </div>
                  </div>
                `
              : html`
                  <svg class="graph-svg"></svg>
                  ${this.renderTooltip()}
                `}
          </div>

          <div class="sidebar">
            <graph-controls
              .depth=${this.depth}
              .selectedTypes=${this.selectedTypes}
              @depth-change=${this.handleDepthChange}
              @type-filter-change=${this.handleTypeFilterChange}
              @reset-layout=${this.handleResetLayout}
              @fit-view=${this.handleFitView}
            ></graph-controls>

            <graph-legend></graph-legend>
          </div>
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'knowledge-graph-viewer': KnowledgeGraphViewer
  }
}
