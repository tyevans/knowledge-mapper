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
import './graph-search'
import './graph-minimap'

interface SimulationNode extends d3.SimulationNodeDatum {
  id: string
  entity_type: EntityType
  name: string
  properties: Record<string, unknown>
  degree?: number // Connection count for sizing
}

interface SimulationLink extends d3.SimulationLinkDatum<SimulationNode> {
  source: SimulationNode | string
  target: SimulationNode | string
  relationship_type: string
  confidence: number
  linkIndex?: number // Index within edge group for curve offset
  linkTotal?: number // Total edges in this group
}

/**
 * Calculate a point on a quadratic Bezier curve at parameter t (0-1).
 * Used for positioning labels along curved edges.
 */
function getPointOnQuadraticBezier(
  sx: number, sy: number,  // start point
  cx: number, cy: number,  // control point
  ex: number, ey: number,  // end point
  t: number               // parameter 0-1
): { x: number; y: number } {
  const x = (1 - t) * (1 - t) * sx + 2 * (1 - t) * t * cx + t * t * ex
  const y = (1 - t) * (1 - t) * sy + 2 * (1 - t) * t * cy + t * t * ey
  return { x, y }
}

// --- Relationship Color Palette ---
// Metro-style distinct colors for different relationship types
const RELATIONSHIP_COLORS = [
  '#e11d48', // rose-600
  '#0891b2', // cyan-600
  '#7c3aed', // violet-600
  '#059669', // emerald-600
  '#d97706', // amber-600
  '#2563eb', // blue-600
  '#c026d3', // fuchsia-600
  '#16a34a', // green-600
  '#dc2626', // red-600
  '#0d9488', // teal-600
  '#9333ea', // purple-600
  '#ea580c', // orange-600
]

/**
 * Get a consistent color for a relationship type.
 * Uses a hash to ensure the same relationship always gets the same color.
 */
function getRelationshipColor(relationshipType: string, colorMap: Map<string, string>): string {
  if (colorMap.has(relationshipType)) {
    return colorMap.get(relationshipType)!
  }
  // Assign next available color
  const colorIndex = colorMap.size % RELATIONSHIP_COLORS.length
  const color = RELATIONSHIP_COLORS[colorIndex]
  colorMap.set(relationshipType, color)
  return color
}

// --- Edge Routing Utilities ---
// Video game-inspired pathfinding: detect obstacles and route edges around them

interface Point {
  x: number
  y: number
}

/**
 * Check if a line segment intersects a circle (node).
 * Uses parametric line-circle intersection formula.
 */
function lineIntersectsCircle(
  x1: number, y1: number, x2: number, y2: number,  // Line segment
  cx: number, cy: number, r: number               // Circle center and radius
): boolean {
  const dx = x2 - x1
  const dy = y2 - y1
  const fx = x1 - cx
  const fy = y1 - cy

  const a = dx * dx + dy * dy
  if (a === 0) return false // Zero-length segment

  const b = 2 * (fx * dx + fy * dy)
  const c = fx * fx + fy * fy - r * r

  const discriminant = b * b - 4 * a * c
  if (discriminant < 0) return false

  const sqrtD = Math.sqrt(discriminant)
  const t1 = (-b - sqrtD) / (2 * a)
  const t2 = (-b + sqrtD) / (2 * a)

  // Check if intersection is within segment (0 <= t <= 1)
  return (t1 >= 0 && t1 <= 1) || (t2 >= 0 && t2 <= 1)
}

/**
 * Find all nodes that an edge would pass through if drawn straight.
 */
function findObstacles(
  source: SimulationNode,
  target: SimulationNode,
  allNodes: SimulationNode[],
  getNodeRadius: (node: SimulationNode) => number,
  padding = 20
): SimulationNode[] {
  return allNodes.filter(node =>
    node.id !== source.id &&
    node.id !== target.id &&
    node.x !== undefined && node.y !== undefined &&
    source.x !== undefined && source.y !== undefined &&
    target.x !== undefined && target.y !== undefined &&
    lineIntersectsCircle(
      source.x, source.y,
      target.x, target.y,
      node.x, node.y,
      getNodeRadius(node) + padding
    )
  )
}

/**
 * Generate a smooth path through waypoints using Catmull-Rom to Bezier conversion.
 */
function generateSmoothPath(points: Point[]): string {
  if (points.length === 2) {
    return `M${points[0].x},${points[0].y}L${points[1].x},${points[1].y}`
  }

  // Catmull-Rom to Bezier conversion for smooth curves
  let path = `M${points[0].x},${points[0].y}`

  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[Math.min(points.length - 1, i + 2)]

    // Control points (tension = 0.5, divided by 6 for smooth curves)
    const cp1x = p1.x + (p2.x - p0.x) / 6
    const cp1y = p1.y + (p2.y - p0.y) / 6
    const cp2x = p2.x - (p3.x - p1.x) / 6
    const cp2y = p2.y - (p3.y - p1.y) / 6

    path += `C${cp1x},${cp1y},${cp2x},${cp2y},${p2.x},${p2.y}`
  }

  return path
}

/**
 * Route an edge around obstacles using multi-waypoint pathfinding.
 */
function routeAroundObstacles(
  source: Point,
  target: Point,
  obstacles: SimulationNode[],
  getNodeRadius: (node: SimulationNode) => number
): string {
  if (obstacles.length === 0) {
    return `M${source.x},${source.y}L${target.x},${target.y}`
  }

  // Sort obstacles by distance from source
  const sorted = [...obstacles].sort((a, b) =>
    Math.hypot(a.x! - source.x, a.y! - source.y) -
    Math.hypot(b.x! - source.x, b.y! - source.y)
  )

  // Build waypoints around each obstacle
  const waypoints: Point[] = [source]

  for (const obs of sorted) {
    const prev = waypoints[waypoints.length - 1]

    // Calculate direction to target from current position
    const dx = target.x - prev.x
    const dy = target.y - prev.y
    const len = Math.hypot(dx, dy) || 1
    const perpX = -dy / len
    const perpY = dx / len

    // Determine which side to route (away from obstacle center relative to line)
    const toObsX = obs.x! - prev.x
    const toObsY = obs.y! - prev.y
    const side = (toObsX * perpX + toObsY * perpY) > 0 ? -1 : 1

    // Create waypoint offset from obstacle
    const clearance = getNodeRadius(obs) + 25
    waypoints.push({
      x: obs.x! + perpX * clearance * side,
      y: obs.y! + perpY * clearance * side
    })
  }

  waypoints.push(target)

  // Generate smooth path through waypoints
  return generateSmoothPath(waypoints)
}

// --- Octilinear (Metro-style) Routing ---
// Constrains edges to 8 directions: horizontal, vertical, and 45° diagonals

// Allowed angles in radians (0°, 45°, 90°, 135°, 180°, 225°, 270°, 315°)
const OCTILINEAR_ANGLES = [0, Math.PI / 4, Math.PI / 2, (3 * Math.PI) / 4, Math.PI, (5 * Math.PI) / 4, (3 * Math.PI) / 2, (7 * Math.PI) / 4]

// Lane spacing for parallel edge separation (pixels between parallel edges)
const LANE_SPACING = 8

/**
 * Simple hash function for strings - returns a number.
 * Used to assign edges to consistent lanes.
 */
function simpleHash(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash = hash & hash // Convert to 32-bit integer
  }
  return Math.abs(hash)
}

/**
 * Compute a lane offset for an edge based on its identity.
 * This ensures edges with different source/target/relationship get different lanes.
 */
function computeLaneOffset(sourceId: string, targetId: string, relationshipType: string): number {
  // Create a unique key for this edge
  const edgeKey = `${sourceId}|${targetId}|${relationshipType}`
  const hash = simpleHash(edgeKey)

  // Map hash to lane offset (-2, -1, 0, 1, 2) * LANE_SPACING
  const laneIndex = (hash % 5) - 2  // Results in -2 to 2
  return laneIndex * LANE_SPACING
}

/**
 * Snap an angle to the nearest octilinear direction.
 */
function snapToOctilinear(angle: number): number {
  // Normalize angle to [0, 2π)
  let normalized = angle % (2 * Math.PI)
  if (normalized < 0) normalized += 2 * Math.PI

  // Find closest allowed angle
  let minDiff = Infinity
  let closestAngle = 0

  for (const allowed of OCTILINEAR_ANGLES) {
    let diff = Math.abs(normalized - allowed)
    // Handle wraparound
    if (diff > Math.PI) diff = 2 * Math.PI - diff
    if (diff < minDiff) {
      minDiff = diff
      closestAngle = allowed
    }
  }

  return closestAngle
}

/**
 * Get the two octilinear directions that best approximate moving from p1 to p2.
 * Returns them in order of preference (primary first).
 */
function getOctilinearDirections(p1: Point, p2: Point): [number, number] {
  const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x)
  const primary = snapToOctilinear(angle)

  // Find the next best direction (the other side of the actual angle)
  let secondary = primary + Math.PI / 4
  if (secondary >= 2 * Math.PI) secondary -= 2 * Math.PI

  // Check if secondary is on the right side of the actual angle
  const angleDiff = angle - primary
  if (angleDiff < 0) {
    secondary = primary - Math.PI / 4
    if (secondary < 0) secondary += 2 * Math.PI
  }

  return [primary, secondary]
}

/**
 * Generate octilinear metro-style path from source to target.
 * Uses at most two direction changes (like a metro line).
 * Optional laneOffset shifts the entire path perpendicular to the edge direction
 * to prevent parallel edges from overlapping.
 */
function generateOctilinearPath(
  source: Point,
  target: Point,
  obstacles: SimulationNode[],
  getNodeRadius: (node: SimulationNode) => number,
  laneOffset: number = 0
): string {
  let dx = target.x - source.x
  let dy = target.y - source.y
  const len = Math.hypot(dx, dy)

  // If very close, just draw a line
  if (len < 20) {
    return `M${source.x},${source.y}L${target.x},${target.y}`
  }

  // Apply lane offset perpendicular to edge direction
  let effectiveSource = source
  let effectiveTarget = target

  if (laneOffset !== 0) {
    const perpX = -dy / len
    const perpY = dx / len
    effectiveSource = {
      x: source.x + perpX * laneOffset,
      y: source.y + perpY * laneOffset
    }
    effectiveTarget = {
      x: target.x + perpX * laneOffset,
      y: target.y + perpY * laneOffset
    }
    // Recalculate dx/dy for the offset path
    dx = effectiveTarget.x - effectiveSource.x
    dy = effectiveTarget.y - effectiveSource.y
  }

  // Get primary octilinear direction
  const angle = Math.atan2(dy, dx)
  const snappedAngle = snapToOctilinear(angle)

  // Unit vector in snapped direction
  const ux = Math.cos(snappedAngle)
  const uy = Math.sin(snappedAngle)

  // Check if we can go directly (angle is exactly octilinear or close enough)
  const angleDiff = Math.abs(angle - snappedAngle)
  if (angleDiff < 0.01 || Math.abs(angleDiff - 2 * Math.PI) < 0.01) {
    // Direct path works
    return `M${effectiveSource.x},${effectiveSource.y}L${effectiveTarget.x},${effectiveTarget.y}`
  }

  // Need to create a two-segment path with one bend
  // Strategy: go in primary direction until aligned, then go perpendicular

  // Calculate how far to go in primary direction
  // Project target onto primary direction line
  const projLength = dx * ux + dy * uy

  // First waypoint: move in primary direction
  const wp1: Point = {
    x: effectiveSource.x + ux * projLength,
    y: effectiveSource.y + uy * projLength
  }

  // But this might not reach target, so we need a second segment
  // The second segment should be perpendicular (45° different)

  // Actually, for a true metro look, use horizontal/vertical priority
  // If mostly horizontal, go horizontal first then vertical
  // If mostly vertical, go vertical first then horizontal

  const absX = Math.abs(dx)
  const absY = Math.abs(dy)

  let midPoint: Point

  if (absX > absY) {
    // Horizontal dominant - go horizontal first, then vertical
    // But snap to 45° if the vertical component is significant
    if (absY > absX * 0.4) {
      // Use diagonal + straight approach
      const diag = Math.min(absX, absY)
      const diagDx = Math.sign(dx) * diag
      const diagDy = Math.sign(dy) * diag
      midPoint = { x: effectiveSource.x + diagDx, y: effectiveSource.y + diagDy }
    } else {
      // Horizontal then vertical
      midPoint = { x: effectiveTarget.x, y: effectiveSource.y }
    }
  } else {
    // Vertical dominant - go vertical first, then horizontal
    if (absX > absY * 0.4) {
      // Use diagonal + straight approach
      const diag = Math.min(absX, absY)
      const diagDx = Math.sign(dx) * diag
      const diagDy = Math.sign(dy) * diag
      midPoint = { x: effectiveSource.x + diagDx, y: effectiveSource.y + diagDy }
    } else {
      // Vertical then horizontal
      midPoint = { x: effectiveSource.x, y: effectiveTarget.y }
    }
  }

  // Check if midpoint intersects any obstacles
  const midpointHitsObstacle = obstacles.some(obs => {
    const radius = getNodeRadius(obs) + 15
    return Math.hypot(midPoint.x - obs.x!, midPoint.y - obs.y!) < radius
  })

  if (midpointHitsObstacle) {
    // Try the alternative bend direction
    if (absX > absY) {
      midPoint = { x: effectiveSource.x, y: effectiveTarget.y }
    } else {
      midPoint = { x: effectiveTarget.x, y: effectiveSource.y }
    }
  }

  // Generate path with rounded corner at bend
  const cornerRadius = 8

  // Calculate corner points
  const d1x = midPoint.x - effectiveSource.x
  const d1y = midPoint.y - effectiveSource.y
  const d1Len = Math.hypot(d1x, d1y)

  const d2x = effectiveTarget.x - midPoint.x
  const d2y = effectiveTarget.y - midPoint.y
  const d2Len = Math.hypot(d2x, d2y)

  if (d1Len < cornerRadius * 2 || d2Len < cornerRadius * 2) {
    // Too short for rounded corner, just use sharp bend
    return `M${effectiveSource.x},${effectiveSource.y}L${midPoint.x},${midPoint.y}L${effectiveTarget.x},${effectiveTarget.y}`
  }

  // Points where the curve starts and ends
  const corner1: Point = {
    x: midPoint.x - (d1x / d1Len) * cornerRadius,
    y: midPoint.y - (d1y / d1Len) * cornerRadius
  }
  const corner2: Point = {
    x: midPoint.x + (d2x / d2Len) * cornerRadius,
    y: midPoint.y + (d2y / d2Len) * cornerRadius
  }

  // Use quadratic bezier for smooth corner
  return `M${effectiveSource.x},${effectiveSource.y}L${corner1.x},${corner1.y}Q${midPoint.x},${midPoint.y},${corner2.x},${corner2.y}L${effectiveTarget.x},${effectiveTarget.y}`
}

/**
 * Generate octilinear path with parallel offset for bundled/bidirectional edges.
 * The offset shifts the entire path perpendicular to create parallel "lanes".
 */
function generateOctilinearPathWithOffset(
  source: Point,
  target: Point,
  offset: number,  // Perpendicular offset (positive = right side, negative = left)
  obstacles: SimulationNode[],
  getNodeRadius: (node: SimulationNode) => number
): string {
  const dx = target.x - source.x
  const dy = target.y - source.y
  const len = Math.hypot(dx, dy)

  if (len < 20) {
    return `M${source.x},${source.y}L${target.x},${target.y}`
  }

  // Calculate perpendicular offset direction
  const perpX = -dy / len
  const perpY = dx / len

  // Apply offset to source and target
  const offsetSource: Point = {
    x: source.x + perpX * offset,
    y: source.y + perpY * offset
  }
  const offsetTarget: Point = {
    x: target.x + perpX * offset,
    y: target.y + perpY * offset
  }

  // Now generate octilinear path for the offset line
  const odx = offsetTarget.x - offsetSource.x
  const ody = offsetTarget.y - offsetSource.y
  const absX = Math.abs(odx)
  const absY = Math.abs(ody)

  let midPoint: Point

  // Determine bend strategy based on dominant direction
  if (absX > absY) {
    if (absY > absX * 0.4) {
      // Use diagonal + straight
      const diag = Math.min(absX, absY)
      midPoint = {
        x: offsetSource.x + Math.sign(odx) * diag,
        y: offsetSource.y + Math.sign(ody) * diag
      }
    } else {
      // Horizontal then vertical
      midPoint = { x: offsetTarget.x, y: offsetSource.y }
    }
  } else {
    if (absX > absY * 0.4) {
      // Use diagonal + straight
      const diag = Math.min(absX, absY)
      midPoint = {
        x: offsetSource.x + Math.sign(odx) * diag,
        y: offsetSource.y + Math.sign(ody) * diag
      }
    } else {
      // Vertical then horizontal
      midPoint = { x: offsetSource.x, y: offsetTarget.y }
    }
  }

  // Check for obstacle collision at midpoint
  const midpointHitsObstacle = obstacles.some(obs => {
    const radius = getNodeRadius(obs) + 15
    return Math.hypot(midPoint.x - obs.x!, midPoint.y - obs.y!) < radius
  })

  if (midpointHitsObstacle) {
    // Try alternative bend
    if (absX > absY) {
      midPoint = { x: offsetSource.x, y: offsetTarget.y }
    } else {
      midPoint = { x: offsetTarget.x, y: offsetSource.y }
    }
  }

  // Generate path with rounded corner
  const cornerRadius = 6

  const d1x = midPoint.x - offsetSource.x
  const d1y = midPoint.y - offsetSource.y
  const d1Len = Math.hypot(d1x, d1y)

  const d2x = offsetTarget.x - midPoint.x
  const d2y = offsetTarget.y - midPoint.y
  const d2Len = Math.hypot(d2x, d2y)

  // If segments too short, use sharp corner
  if (d1Len < cornerRadius * 2 || d2Len < cornerRadius * 2) {
    return `M${offsetSource.x},${offsetSource.y}L${midPoint.x},${midPoint.y}L${offsetTarget.x},${offsetTarget.y}`
  }

  const corner1: Point = {
    x: midPoint.x - (d1x / d1Len) * cornerRadius,
    y: midPoint.y - (d1y / d1Len) * cornerRadius
  }
  const corner2: Point = {
    x: midPoint.x + (d2x / d2Len) * cornerRadius,
    y: midPoint.y + (d2y / d2Len) * cornerRadius
  }

  return `M${offsetSource.x},${offsetSource.y}L${corner1.x},${corner1.y}Q${midPoint.x},${midPoint.y},${corner2.x},${corner2.y}L${offsetTarget.x},${offsetTarget.y}`
}

/**
 * Knowledge Graph Viewer Component
 *
 * Interactive D3.js visualization of the knowledge graph with floating
 * controls and legend panels overlaid on the graph canvas.
 *
 * @fires view-entity - When user clicks to view an entity detail
 */
@customElement('knowledge-graph-viewer')
export class KnowledgeGraphViewer extends LitElement {
  static styles = css`
    :host {
      display: block;
      height: 100%;
    }

    .card {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
      overflow: hidden;
      height: 100%;
      display: flex;
      flex-direction: column;
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
      flex: 1;
      min-height: 0; /* Allow flex shrinking */
      background: #f9fafb;
      overflow: hidden;
    }

    .graph-svg {
      width: 100%;
      height: 100%;
    }

    /* Floating panels container - positioned over the graph */
    .floating-panels {
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      pointer-events: none;
      z-index: 10;
    }

    /* Allow pointer events only on the actual panels */
    .floating-panels > * {
      pointer-events: auto;
    }

    .node {
      cursor: pointer;
      transition: opacity 150ms ease;
    }

    .node circle {
      transition: stroke 150ms ease, stroke-width 150ms ease;
    }

    .node:hover circle {
      stroke-width: 3px;
    }

    .link {
      /* stroke color set dynamically per relationship type */
      stroke-opacity: 0.6;  /* Slightly higher for colored edges */
      fill: none;
      transition: stroke-opacity 150ms ease, opacity 150ms ease, stroke 150ms ease;
    }

    .link-label {
      font-size: 9px;
      fill: #475569;
      font-weight: 500;
      pointer-events: none;
      text-anchor: middle;
      transition: opacity 150ms ease;
    }

    .link-label-bg {
      fill: rgba(255, 255, 255, 0.92);
      stroke: rgba(0, 0, 0, 0.06);
      stroke-width: 0.5;
      transition: opacity 150ms ease;
    }

    .node-label {
      font-size: 11px;
      fill: #1f2937;
      transition: display 150ms ease;
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
      height: 100%;
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
      height: 100%;
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
  private confidenceThreshold = 0

  @state()
  private tooltipData: { node: SimulationNode; x: number; y: number } | null = null

  @state()
  private pinnedNodeId: string | null = null

  @query('.graph-svg')
  private svgElement!: SVGSVGElement

  @query('.graph-container')
  private containerElement!: HTMLDivElement

  private simulation: d3.Simulation<SimulationNode, SimulationLink> | null = null
  private unsubscribe?: () => void
  private resizeObserver?: ResizeObserver

  // D3 selections for hover highlighting
  private linkSelection: d3.Selection<SVGPathElement, SimulationLink, SVGGElement, unknown> | null = null
  private nodeSelection: d3.Selection<SVGGElement, SimulationNode, SVGGElement, unknown> | null = null
  private linkLabelSelection: d3.Selection<SVGTextElement, SimulationLink, SVGGElement, unknown> | null = null
  private linkLabelBackgroundSelection: d3.Selection<SVGRectElement, SimulationLink, SVGGElement, unknown> | null = null
  private currentSimLinks: SimulationLink[] = []
  private edgeGroups: Map<string, number> = new Map() // Maps edge pair key to total count
  private relationshipColorMap: Map<string, string> = new Map() // Maps relationship type to color

  // Zoom state for LOD labels
  private currentZoomScale = 1
  private currentZoom: d3.ZoomBehavior<SVGSVGElement, unknown> | null = null

  // Search highlight state
  private highlightedNodeIds: Set<string> = new Set()

  // Focus mode state
  private focusedNodeId: string | null = null
  private focusDepth = 2

  // Path highlighting state
  private pathStartNodeId: string | null = null
  private pathEndNodeId: string | null = null
  private pathNodeIds: Set<string> = new Set()
  private pathEdgeKeys: Set<string> = new Set()

  // Minimap state
  @state()
  private minimapNodePositions: Array<{ id: string; x: number; y: number; entityType: string }> = []

  @state()
  private minimapViewport: { x: number; y: number; width: number; height: number } | null = null

  @state()
  private minimapGraphBounds: { minX: number; minY: number; maxX: number; maxY: number } | null = null

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

    // Add keyboard listener for Escape to clear pinned highlighting
    document.addEventListener('keydown', this.handleKeyDown)
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.unsubscribe?.()
    this.simulation?.stop()
    this.resizeObserver?.disconnect()
    document.removeEventListener('keydown', this.handleKeyDown)
  }

  protected firstUpdated(): void {
    // Set up resize observer to handle dynamic sizing
    if (this.containerElement) {
      this.resizeObserver = new ResizeObserver(this.handleResize.bind(this))
      this.resizeObserver.observe(this.containerElement)
    }
  }

  /**
   * Handle container resize events.
   * Updates D3 simulation center force and optionally re-centers the view.
   */
  private handleResize(entries: ResizeObserverEntry[]): void {
    const entry = entries[0]
    if (!entry || !this.simulation || !this.graphData) return

    const { width, height } = entry.contentRect

    // Update the center force to the new center
    this.simulation
      .force('center', d3.forceCenter(width / 2, height / 2))
      .alpha(0.3)
      .restart()
  }

  updated(changedProperties: Map<string, unknown>): void {
    if (changedProperties.has('centerId') && this.authState?.isAuthenticated) {
      this.loadGraph()
    }
  }

  private async loadGraph(): Promise<void> {
    // Only show loading spinner on initial load, not on settings changes
    // This prevents the graph from disappearing when changing depth/filters
    const isInitialLoad = !this.graphData
    if (isInitialLoad) {
      this.isLoading = true
    }
    this.error = null

    try {
      const params = new URLSearchParams({
        depth: this.depth.toString(),
        limit: '1000',
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

    // Create zoom behavior with LOD label updates and minimap viewport tracking
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        container.attr('transform', event.transform)
        this.currentZoomScale = event.transform.k
        this.updateLabelVisibility()
        this.updateMinimapViewport(event.transform)
      })

    svg.call(zoom)

    // Store zoom for minimap navigation
    this.currentZoom = zoom

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

    // Calculate adaptive force parameters based on graph density
    const nodeCount = simNodes.length
    const edgeCount = simLinks.length

    // Scale parameters to prevent clustering in dense graphs
    const linkDistance = Math.max(60, 100 + nodeCount * 0.5)
    const chargeStrength = Math.min(-100, -300 + nodeCount * 0.8)
    const collisionRadius = Math.max(30, 40 + Math.log10(Math.max(nodeCount, 1)) * 10)
    const linkStrength = 1 / Math.min(nodeCount, 100)

    // Create force simulation with adaptive parameters
    this.simulation = d3.forceSimulation<SimulationNode>(simNodes)
      .force('link', d3.forceLink<SimulationNode, SimulationLink>(simLinks)
        .id((d) => d.id)
        .distance(linkDistance)
        .strength(linkStrength))
      .force('charge', d3.forceManyBody()
        .strength(chargeStrength)
        .distanceMax(400)) // Limit charge calculation range for performance
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(collisionRadius))

    // Group edges by source-target pair for curve calculation
    this.edgeGroups = new Map()
    simLinks.forEach((link) => {
      const sourceId = typeof link.source === 'string' ? link.source : link.source.id
      const targetId = typeof link.target === 'string' ? link.target : link.target.id
      // Canonical key (always smaller id first) to group edges in both directions
      const key = sourceId < targetId ? `${sourceId}-${targetId}` : `${targetId}-${sourceId}`

      const currentCount = this.edgeGroups.get(key) || 0
      link.linkIndex = currentCount
      this.edgeGroups.set(key, currentCount + 1)
    })

    // Set total count for each link
    simLinks.forEach((link) => {
      const sourceId = typeof link.source === 'string' ? link.source : link.source.id
      const targetId = typeof link.target === 'string' ? link.target : link.target.id
      const key = sourceId < targetId ? `${sourceId}-${targetId}` : `${targetId}-${sourceId}`
      link.linkTotal = this.edgeGroups.get(key) || 1
    })

    // Calculate node degrees for sizing
    const nodeDegrees = new Map<string, number>()
    simLinks.forEach((link) => {
      const sourceId = typeof link.source === 'string' ? link.source : link.source.id
      const targetId = typeof link.target === 'string' ? link.target : link.target.id
      nodeDegrees.set(sourceId, (nodeDegrees.get(sourceId) || 0) + 1)
      nodeDegrees.set(targetId, (nodeDegrees.get(targetId) || 0) + 1)
    })
    simNodes.forEach((node) => {
      node.degree = nodeDegrees.get(node.id) || 0
    })

    // Store links for hover highlighting
    this.currentSimLinks = simLinks

    // Reset relationship color map for fresh assignment
    this.relationshipColorMap = new Map()

    // Create links as paths for curved edges with relationship-based colors
    this.linkSelection = container.append('g')
      .selectAll('path')
      .data(simLinks)
      .join('path')
      .attr('class', 'link')
      .attr('stroke', (d) => getRelationshipColor(d.relationship_type, this.relationshipColorMap))
      .attr('stroke-width', 2)
      .attr('marker-end', 'url(#arrowhead)')

    const link = this.linkSelection

    // Create link label backgrounds (rendered before text so they appear behind)
    this.linkLabelBackgroundSelection = container.append('g')
      .selectAll('rect')
      .data(simLinks)
      .join('rect')
      .attr('class', 'link-label-bg')
      .attr('rx', 2)
      .attr('ry', 2)

    const linkLabelBg = this.linkLabelBackgroundSelection

    // Create link labels
    this.linkLabelSelection = container.append('g')
      .selectAll('text')
      .data(simLinks)
      .join('text')
      .attr('class', 'link-label')
      .text((d) => d.relationship_type)

    const linkLabel = this.linkLabelSelection

    // Create nodes
    this.nodeSelection = container.append('g')
      .selectAll('g')
      .data(simNodes)
      .join('g')
      .attr('class', 'node')
      .call(this.createDragBehavior())
      .on('click', (event, d) => {
        // Ctrl+click (or Cmd+click on Mac) to pin/unpin highlighting
        if (event.ctrlKey || event.metaKey) {
          event.stopPropagation()
          event.preventDefault()
          if (this.pinnedNodeId === d.id) {
            // Clicking pinned node unpins it
            this.pinnedNodeId = null
            this.resetHighlighting()
          } else {
            // Pin new node
            this.pinnedNodeId = d.id
            this.highlightConnections(d)
            this.updatePinnedNodeVisual()
          }
        } else {
          // Normal click - open detail view
          this.handleNodeClick(d)
        }
      })
      .on('contextmenu', (event, d) => this.handleNodeRightClick(event, d))
      .on('mouseenter', (event, d) => {
        this.showTooltip(event, d)
        // Only highlight on hover if no node is pinned
        if (!this.pinnedNodeId) {
          this.highlightConnections(d)
        }
      })
      .on('mouseleave', () => {
        this.hideTooltip()
        // Only reset highlighting if no node is pinned
        if (!this.pinnedNodeId) {
          this.resetHighlighting()
        }
      })

    const node = this.nodeSelection

    node.append('circle')
      .attr('r', (d) => {
        // Center node is always larger
        if (d.id === this.centerId) return 20
        // Scale by degree: base 10 + degree contribution, capped at 24
        const degreeBonus = Math.min((d.degree || 0) * 1.5, 14)
        return 10 + degreeBonus
      })
      .attr('fill', (d) => ENTITY_TYPE_COLORS[d.entity_type] || '#6b7280')
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)

    node.append('text')
      .attr('class', 'node-label')
      .attr('dy', (d) => {
        // Position label below node, accounting for varying radius
        if (d.id === this.centerId) return 32
        const degreeBonus = Math.min((d.degree || 0) * 1.5, 14)
        return 10 + degreeBonus + 12
      })
      .text((d) => this.truncateLabel(d.name))

    // Helper to get node radius (same logic as circle rendering)
    const getNodeRadius = (node: SimulationNode): number => {
      if (node.id === this.centerId) return 20
      const degreeBonus = Math.min((node.degree || 0) * 1.5, 14)
      return 10 + degreeBonus
    }

    // Update positions on tick
    this.simulation.on('tick', () => {
      // Get current simulation alpha for performance optimization
      const alpha = this.simulation!.alpha()

      // Calculate curved paths for edges with smart routing
      link.attr('d', (d) => {
        const source = d.source as SimulationNode
        const target = d.target as SimulationNode
        const linkIndex = d.linkIndex || 0
        const linkTotal = d.linkTotal || 1

        // Safety check
        if (source.x === undefined || source.y === undefined ||
            target.x === undefined || target.y === undefined) {
          return ''
        }

        // Multiple edges (bidirectional) - use octilinear paths with parallel offsets
        if (linkTotal > 1) {
          // During fast animation, use simple offset lines for performance
          if (alpha > 0.3) {
            const dx = target.x - source.x
            const dy = target.y - source.y
            const dr = Math.sqrt(dx * dx + dy * dy) || 1
            const offset = (linkIndex - (linkTotal - 1) / 2) * 12
            const perpX = -dy / dr
            const perpY = dx / dr
            return `M${source.x + perpX * offset},${source.y + perpY * offset}L${target.x + perpX * offset},${target.y + perpY * offset}`
          }

          // Calculate parallel offset for this edge in the bundle
          const offset = (linkIndex - (linkTotal - 1) / 2) * 12
          const obstacles = findObstacles(source, target, simNodes, getNodeRadius)

          return generateOctilinearPathWithOffset(
            { x: source.x, y: source.y },
            { x: target.x, y: target.y },
            offset,
            obstacles,
            getNodeRadius
          )
        }

        // Single edge - apply octilinear metro-style routing when simulation is settling
        // During fast animation (high alpha), use straight lines for performance

        // Compute lane offset based on edge identity to prevent parallel edges from overlapping
        const sourceId = typeof source === 'string' ? source : source.id
        const targetId = typeof target === 'string' ? target : target.id
        const laneOffset = computeLaneOffset(sourceId, targetId, d.relationship_type)

        if (alpha > 0.3) {
          // Apply lane offset even during animation for consistency
          const dx = target.x - source.x
          const dy = target.y - source.y
          const len = Math.hypot(dx, dy) || 1
          const perpX = -dy / len
          const perpY = dx / len
          return `M${source.x + perpX * laneOffset},${source.y + perpY * laneOffset}L${target.x + perpX * laneOffset},${target.y + perpY * laneOffset}`
        }

        // Find obstacles for this edge
        const obstacles = findObstacles(source, target, simNodes, getNodeRadius)

        // Generate octilinear metro-style path with lane offset
        return generateOctilinearPath(
          { x: source.x, y: source.y },
          { x: target.x, y: target.y },
          obstacles,
          getNodeRadius,
          laneOffset
        )
      })

      // Position link labels along the curve with staggered positions for bidirectional edges
      // This prevents label overlap when two nodes connect in both directions
      const getLabelPosition = (d: SimulationLink) => {
        const source = d.source as SimulationNode
        const target = d.target as SimulationNode
        const linkIndex = d.linkIndex || 0
        const linkTotal = d.linkTotal || 1

        // For single edge, position at midpoint
        if (linkTotal === 1) {
          return { x: (source.x! + target.x!) / 2, y: (source.y! + target.y!) / 2 }
        }

        // Calculate the control point for the quadratic curve
        const dx = target.x! - source.x!
        const dy = target.y! - source.y!
        const dr = Math.sqrt(dx * dx + dy * dy) || 1
        const offset = (linkIndex - (linkTotal - 1) / 2) * 30
        const ctrlX = (source.x! + target.x!) / 2 + offset * (dy / dr)
        const ctrlY = (source.y! + target.y!) / 2 - offset * (dx / dr)

        // Stagger labels along the curve: "forward" edges at t=0.35, "backward" at t=0.65
        // This separates labels for bidirectional connections
        const sourceId = typeof source === 'string' ? source : source.id
        const targetId = typeof target === 'string' ? target : target.id
        const isForward = sourceId < targetId
        const t = isForward ? 0.35 : 0.65

        return getPointOnQuadraticBezier(source.x!, source.y!, ctrlX, ctrlY, target.x!, target.y!, t)
      }

      linkLabel
        .attr('x', (d) => getLabelPosition(d).x)
        .attr('y', (d) => getLabelPosition(d).y)

      // Update background rectangles to match label positions
      // We need to measure text bounds after positioning
      linkLabelBg.each(function(d, i) {
        const textElement = linkLabel.nodes()[i] as SVGTextElement
        if (textElement) {
          const bbox = textElement.getBBox()
          const padding = 3
          d3.select(this)
            .attr('x', bbox.x - padding)
            .attr('y', bbox.y - padding)
            .attr('width', bbox.width + padding * 2)
            .attr('height', bbox.height + padding * 2)
        }
      })

      node.attr('transform', (d) => `translate(${d.x},${d.y})`)

      // Update minimap with current positions (throttled)
      this.updateMinimapNodePositions(simNodes)
    })

    // Initialize minimap viewport
    this.updateMinimapViewport(d3.zoomIdentity)

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

    // Apply initial LOD label visibility
    this.updateLabelVisibility()
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
    // Toggle focus mode
    if (this.focusedNodeId === node.id) {
      // Exit focus mode
      this.focusedNodeId = null
      this.resetFocusMode()
    } else {
      // Enter focus mode on this node
      this.focusedNodeId = node.id
      this.applyFocusMode(node.id)
    }

    this.dispatchEvent(
      new CustomEvent('view-entity', {
        detail: { entityId: node.id },
        bubbles: true,
        composed: true,
      })
    )
  }

  /**
   * Apply focus mode - dim nodes/edges outside N hops from focused node.
   */
  private applyFocusMode(centerId: string): void {
    if (!this.linkSelection || !this.nodeSelection || !this.linkLabelSelection) return

    // BFS to find nodes within focusDepth hops
    const visibleIds = new Set<string>()
    const queue: Array<{ id: string; depth: number }> = [{ id: centerId, depth: 0 }]

    while (queue.length > 0) {
      const { id, depth } = queue.shift()!
      if (visibleIds.has(id) || depth > this.focusDepth) continue
      visibleIds.add(id)

      // Find neighbors
      this.currentSimLinks.forEach((link) => {
        const sourceId = typeof link.source === 'string' ? link.source : link.source.id
        const targetId = typeof link.target === 'string' ? link.target : link.target.id

        if (sourceId === id && !visibleIds.has(targetId)) {
          queue.push({ id: targetId, depth: depth + 1 })
        }
        if (targetId === id && !visibleIds.has(sourceId)) {
          queue.push({ id: sourceId, depth: depth + 1 })
        }
      })
    }

    // Apply visual styling - dim nodes outside focus
    this.nodeSelection.style('opacity', (d) => (visibleIds.has(d.id) ? 1 : 0.1))

    // Dim edges outside focus
    this.linkSelection
      .style('stroke-opacity', (d) => {
        const sourceId = typeof d.source === 'string' ? d.source : d.source.id
        const targetId = typeof d.target === 'string' ? d.target : d.target.id
        return visibleIds.has(sourceId) && visibleIds.has(targetId) ? 0.6 : 0.02
      })
      .style('opacity', (d) => {
        const sourceId = typeof d.source === 'string' ? d.source : d.source.id
        const targetId = typeof d.target === 'string' ? d.target : d.target.id
        return visibleIds.has(sourceId) && visibleIds.has(targetId) ? 1 : 0.02
      })

    // Dim edge labels outside focus
    this.linkLabelSelection.style('opacity', (d) => {
      const sourceId = typeof d.source === 'string' ? d.source : d.source.id
      const targetId = typeof d.target === 'string' ? d.target : d.target.id
      return visibleIds.has(sourceId) && visibleIds.has(targetId) ? 1 : 0
    })
    this.linkLabelBackgroundSelection?.style('opacity', (d) => {
      const sourceId = typeof d.source === 'string' ? d.source : d.source.id
      const targetId = typeof d.target === 'string' ? d.target : d.target.id
      return visibleIds.has(sourceId) && visibleIds.has(targetId) ? 1 : 0
    })

    // Highlight the focused node
    this.nodeSelection.select('circle')
      .attr('stroke', (d) => (d.id === centerId ? '#ef4444' : '#fff'))
      .attr('stroke-width', (d) => (d.id === centerId ? 4 : 2))
  }

  /**
   * Exit focus mode - restore all nodes/edges to normal visibility.
   */
  private resetFocusMode(): void {
    if (!this.linkSelection || !this.nodeSelection || !this.linkLabelSelection) return

    this.nodeSelection.style('opacity', 1)
    this.linkSelection
      .style('stroke-opacity', 0.6)
      .style('opacity', 1)
    this.linkLabelSelection.style('opacity', 1)
    this.linkLabelBackgroundSelection?.style('opacity', 1)

    // Reset node strokes
    this.nodeSelection.select('circle')
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
  }

  /**
   * Handle right-click on node for path selection.
   */
  private handleNodeRightClick(event: MouseEvent, node: SimulationNode): void {
    event.preventDefault()

    if (!this.pathStartNodeId) {
      // First node selected - start of path
      this.pathStartNodeId = node.id
      this.pathEndNodeId = null
      this.highlightPathStart(node.id)
    } else if (this.pathStartNodeId !== node.id && !this.pathEndNodeId) {
      // Second node selected - end of path
      this.pathEndNodeId = node.id
      this.highlightPath(this.pathStartNodeId, this.pathEndNodeId)
    } else {
      // Third click - clear path selection
      this.clearPathHighlight()
    }
  }

  /**
   * Highlight the start node for path selection.
   */
  private highlightPathStart(nodeId: string): void {
    if (!this.nodeSelection) return

    this.nodeSelection.select('circle')
      .attr('stroke', (d) => (d.id === nodeId ? '#10b981' : '#fff'))
      .attr('stroke-width', (d) => (d.id === nodeId ? 4 : 2))
  }

  /**
   * Find and highlight shortest path between two nodes using BFS.
   */
  private highlightPath(startId: string, endId: string): void {
    if (!this.linkSelection || !this.nodeSelection) return

    // BFS to find shortest path
    const parent = new Map<string, string>()
    const queue = [startId]
    parent.set(startId, startId)

    while (queue.length > 0) {
      const current = queue.shift()!
      if (current === endId) break

      this.currentSimLinks.forEach((link) => {
        const sourceId = typeof link.source === 'string' ? link.source : link.source.id
        const targetId = typeof link.target === 'string' ? link.target : link.target.id

        // Check both directions
        if (sourceId === current && !parent.has(targetId)) {
          parent.set(targetId, current)
          queue.push(targetId)
        }
        if (targetId === current && !parent.has(sourceId)) {
          parent.set(sourceId, current)
          queue.push(sourceId)
        }
      })
    }

    // Check if path exists
    if (!parent.has(endId)) {
      // No path found - just highlight both endpoints
      this.pathNodeIds = new Set([startId, endId])
      this.pathEdgeKeys = new Set()
    } else {
      // Reconstruct path
      this.pathNodeIds = new Set<string>()
      this.pathEdgeKeys = new Set<string>()

      let current = endId
      while (current !== startId) {
        this.pathNodeIds.add(current)
        const prev = parent.get(current)!

        // Create edge key for highlighting
        const edgeKey = current < prev ? `${current}-${prev}` : `${prev}-${current}`
        this.pathEdgeKeys.add(edgeKey)

        current = prev
      }
      this.pathNodeIds.add(startId)
    }

    // Apply visual highlighting
    this.nodeSelection
      .style('opacity', (d) => (this.pathNodeIds.has(d.id) ? 1 : 0.2))

    this.nodeSelection.select('circle')
      .attr('stroke', (d) => {
        if (d.id === startId) return '#10b981' // Green for start
        if (d.id === endId) return '#ef4444' // Red for end
        if (this.pathNodeIds.has(d.id)) return '#f59e0b' // Orange for path
        return '#fff'
      })
      .attr('stroke-width', (d) => (this.pathNodeIds.has(d.id) ? 4 : 2))

    this.linkSelection
      .style('stroke', (d) => {
        const sourceId = typeof d.source === 'string' ? d.source : d.source.id
        const targetId = typeof d.target === 'string' ? d.target : d.target.id
        const edgeKey = sourceId < targetId ? `${sourceId}-${targetId}` : `${targetId}-${sourceId}`
        // Highlight path in red, otherwise use relationship color
        return this.pathEdgeKeys.has(edgeKey) ? '#ef4444' : getRelationshipColor(d.relationship_type, this.relationshipColorMap)
      })
      .style('stroke-opacity', (d) => {
        const sourceId = typeof d.source === 'string' ? d.source : d.source.id
        const targetId = typeof d.target === 'string' ? d.target : d.target.id
        const edgeKey = sourceId < targetId ? `${sourceId}-${targetId}` : `${targetId}-${sourceId}`
        return this.pathEdgeKeys.has(edgeKey) ? 1 : 0.1
      })
      .style('stroke-width', (d) => {
        const sourceId = typeof d.source === 'string' ? d.source : d.source.id
        const targetId = typeof d.target === 'string' ? d.target : d.target.id
        const edgeKey = sourceId < targetId ? `${sourceId}-${targetId}` : `${targetId}-${sourceId}`
        return this.pathEdgeKeys.has(edgeKey) ? 4 : 2
      })
      .style('opacity', (d) => {
        const sourceId = typeof d.source === 'string' ? d.source : d.source.id
        const targetId = typeof d.target === 'string' ? d.target : d.target.id
        const edgeKey = sourceId < targetId ? `${sourceId}-${targetId}` : `${targetId}-${sourceId}`
        return this.pathEdgeKeys.has(edgeKey) ? 1 : 0.1
      })

    if (this.linkLabelSelection) {
      this.linkLabelSelection.style('opacity', (d) => {
        const sourceId = typeof d.source === 'string' ? d.source : d.source.id
        const targetId = typeof d.target === 'string' ? d.target : d.target.id
        const edgeKey = sourceId < targetId ? `${sourceId}-${targetId}` : `${targetId}-${sourceId}`
        return this.pathEdgeKeys.has(edgeKey) ? 1 : 0
      })
    }
    if (this.linkLabelBackgroundSelection) {
      this.linkLabelBackgroundSelection.style('opacity', (d) => {
        const sourceId = typeof d.source === 'string' ? d.source : d.source.id
        const targetId = typeof d.target === 'string' ? d.target : d.target.id
        const edgeKey = sourceId < targetId ? `${sourceId}-${targetId}` : `${targetId}-${sourceId}`
        return this.pathEdgeKeys.has(edgeKey) ? 1 : 0
      })
    }
  }

  /**
   * Clear path highlighting and reset to normal state.
   */
  private clearPathHighlight(): void {
    this.pathStartNodeId = null
    this.pathEndNodeId = null
    this.pathNodeIds = new Set()
    this.pathEdgeKeys = new Set()

    if (!this.linkSelection || !this.nodeSelection) return

    this.nodeSelection.style('opacity', 1)
    this.nodeSelection.select('circle')
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)

    this.linkSelection
      .style('stroke', (d) => getRelationshipColor(d.relationship_type, this.relationshipColorMap))
      .style('stroke-opacity', 0.6)
      .style('stroke-width', 2)
      .style('opacity', 1)

    if (this.linkLabelSelection) {
      this.linkLabelSelection.style('opacity', 1)
    }
    if (this.linkLabelBackgroundSelection) {
      this.linkLabelBackgroundSelection.style('opacity', 1)
    }
  }

  /**
   * Update minimap node positions from simulation data.
   */
  private updateMinimapNodePositions(nodes: SimulationNode[]): void {
    // Update node positions
    this.minimapNodePositions = nodes.map((n) => ({
      id: n.id,
      x: n.x || 0,
      y: n.y || 0,
      entityType: n.entity_type,
    }))

    // Calculate graph bounds
    if (nodes.length > 0) {
      const xs = nodes.map((n) => n.x || 0)
      const ys = nodes.map((n) => n.y || 0)
      this.minimapGraphBounds = {
        minX: Math.min(...xs) - 50,
        minY: Math.min(...ys) - 50,
        maxX: Math.max(...xs) + 50,
        maxY: Math.max(...ys) + 50,
      }
    }
  }

  /**
   * Update minimap viewport based on current zoom transform.
   */
  private updateMinimapViewport(transform: d3.ZoomTransform): void {
    if (!this.containerElement) return

    const width = this.containerElement.clientWidth
    const height = this.containerElement.clientHeight

    // Calculate visible viewport in graph coordinates
    this.minimapViewport = {
      x: -transform.x / transform.k,
      y: -transform.y / transform.k,
      width: width / transform.k,
      height: height / transform.k,
    }
  }

  /**
   * Handle minimap navigation click.
   */
  private handleMinimapNavigate(e: CustomEvent): void {
    const { x, y } = e.detail

    if (!this.svgElement || !this.currentZoom) return

    const svg = d3.select(this.svgElement)
    const width = this.containerElement.clientWidth
    const height = this.containerElement.clientHeight

    // Calculate transform to center on clicked position
    const scale = this.currentZoomScale
    const translateX = width / 2 - x * scale
    const translateY = height / 2 - y * scale

    svg.transition()
      .duration(500)
      .call(
        this.currentZoom.transform as (
          selection: d3.Transition<SVGSVGElement, unknown, null, undefined>,
          transform: d3.ZoomTransform
        ) => void,
        d3.zoomIdentity.translate(translateX, translateY).scale(scale)
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

  /**
   * Highlight connections for a hovered node.
   * Dims unconnected nodes and edges to make the neighborhood visible.
   */
  private highlightConnections(hoveredNode: SimulationNode): void {
    if (!this.linkSelection || !this.nodeSelection || !this.linkLabelSelection) return

    // Find all connected node IDs
    const connectedIds = new Set<string>()
    connectedIds.add(hoveredNode.id)

    this.currentSimLinks.forEach((link) => {
      const sourceId = typeof link.source === 'string' ? link.source : link.source.id
      const targetId = typeof link.target === 'string' ? link.target : link.target.id

      if (sourceId === hoveredNode.id) {
        connectedIds.add(targetId)
      } else if (targetId === hoveredNode.id) {
        connectedIds.add(sourceId)
      }
    })

    // Dim unconnected nodes
    this.nodeSelection.style('opacity', (d) => connectedIds.has(d.id) ? 1 : 0.15)

    // Dim unconnected edges (including opacity for both stroke and marker)
    this.linkSelection
      .style('stroke-opacity', (d) => {
        const sourceId = typeof d.source === 'string' ? d.source : d.source.id
        const targetId = typeof d.target === 'string' ? d.target : d.target.id
        return (sourceId === hoveredNode.id || targetId === hoveredNode.id) ? 0.8 : 0.05
      })
      .style('opacity', (d) => {
        const sourceId = typeof d.source === 'string' ? d.source : d.source.id
        const targetId = typeof d.target === 'string' ? d.target : d.target.id
        return (sourceId === hoveredNode.id || targetId === hoveredNode.id) ? 1 : 0.05
      })

    // Hide unconnected edge labels (and their backgrounds)
    this.linkLabelSelection.style('opacity', (d) => {
      const sourceId = typeof d.source === 'string' ? d.source : d.source.id
      const targetId = typeof d.target === 'string' ? d.target : d.target.id
      return (sourceId === hoveredNode.id || targetId === hoveredNode.id) ? 1 : 0
    })
    this.linkLabelBackgroundSelection?.style('opacity', (d) => {
      const sourceId = typeof d.source === 'string' ? d.source : d.source.id
      const targetId = typeof d.target === 'string' ? d.target : d.target.id
      return (sourceId === hoveredNode.id || targetId === hoveredNode.id) ? 1 : 0
    })
  }

  /**
   * Reset highlighting after mouse leaves a node.
   */
  private resetHighlighting(): void {
    if (!this.linkSelection || !this.nodeSelection || !this.linkLabelSelection) return

    this.nodeSelection.style('opacity', 1)
    this.linkSelection
      .style('stroke-opacity', 0.6)
      .style('opacity', 1)
    this.linkLabelSelection.style('opacity', 1)
    this.linkLabelBackgroundSelection?.style('opacity', 1)

    // Reset pinned node visual
    this.nodeSelection.select('circle')
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
  }

  /**
   * Update visual indicator for the pinned node (orange border).
   */
  private updatePinnedNodeVisual(): void {
    if (!this.nodeSelection) return

    this.nodeSelection.select('circle')
      .attr('stroke', (d) => d.id === this.pinnedNodeId ? '#f97316' : '#fff')
      .attr('stroke-width', (d) => d.id === this.pinnedNodeId ? 4 : 2)
  }

  /**
   * Handle keyboard events for graph interactions.
   */
  private handleKeyDown = (e: KeyboardEvent): void => {
    // Escape key clears pinned highlighting
    if (e.key === 'Escape' && this.pinnedNodeId) {
      this.pinnedNodeId = null
      this.resetHighlighting()
    }
  }

  /**
   * Update label visibility based on zoom level (Level of Detail).
   * - Zoom < 0.5: No labels
   * - Zoom 0.5-1.5: Center node label only
   * - Zoom 1.5-2.0: All node labels visible
   * - Zoom > 2.0: Node and edge labels visible (if above confidence threshold)
   */
  private updateLabelVisibility(): void {
    if (!this.svgElement) return

    const svg = d3.select(this.svgElement)
    const scale = this.currentZoomScale
    const threshold = this.confidenceThreshold

    // Update node labels
    svg.selectAll('.node-label').style('display', (d) => {
      const node = d as SimulationNode
      if (scale > 1.5) return 'block'
      if (scale > 0.5 && node.id === this.centerId) return 'block'
      if (scale > 0.5) return 'none'
      return 'none'
    })

    // Update edge labels - only visible at high zoom and above confidence threshold
    svg.selectAll('.link-label').style('display', (d) => {
      const link = d as SimulationLink
      return scale > 2 && link.confidence >= threshold ? 'block' : 'none'
    })

    // Update edge label backgrounds to match
    svg.selectAll('.link-label-bg').style('display', (d) => {
      const link = d as SimulationLink
      return scale > 2 && link.confidence >= threshold ? 'block' : 'none'
    })
  }

  private handleDepthChange(e: CustomEvent): void {
    this.depth = e.detail.depth
    this.loadGraph()
  }

  private handleTypeFilterChange(e: CustomEvent): void {
    this.selectedTypes = e.detail.types
    this.loadGraph()
  }

  private handleConfidenceChange(e: CustomEvent): void {
    this.confidenceThreshold = e.detail.threshold
    this.applyConfidenceFilter()
  }

  /**
   * Apply confidence filter to show/hide edges based on threshold.
   */
  private applyConfidenceFilter(): void {
    if (!this.linkSelection || !this.linkLabelSelection) return

    const threshold = this.confidenceThreshold

    this.linkSelection.style('display', (d) =>
      d.confidence >= threshold ? 'block' : 'none'
    )

    this.linkLabelSelection.style('display', (d) =>
      d.confidence >= threshold && this.currentZoomScale > 2 ? 'block' : 'none'
    )

    this.linkLabelBackgroundSelection?.style('display', (d) =>
      d.confidence >= threshold && this.currentZoomScale > 2 ? 'block' : 'none'
    )
  }

  private handleResetLayout(): void {
    if (this.simulation) {
      this.simulation.alpha(1).restart()
    }
  }

  /**
   * Handle search highlight event - highlight matching nodes.
   */
  private handleSearchHighlight(e: CustomEvent): void {
    const nodeIds = e.detail.nodeIds as string[]
    this.highlightedNodeIds = new Set(nodeIds)

    if (!this.nodeSelection) return

    if (nodeIds.length === 0) {
      // Clear highlights
      this.nodeSelection.select('circle').attr('stroke', '#fff').attr('stroke-width', 2)
    } else {
      // Highlight matching nodes
      this.nodeSelection.select('circle')
        .attr('stroke', (d) => this.highlightedNodeIds.has(d.id) ? '#f59e0b' : '#fff')
        .attr('stroke-width', (d) => this.highlightedNodeIds.has(d.id) ? 4 : 2)
    }
  }

  /**
   * Handle focus node event - zoom to and select a specific node.
   */
  private handleFocusNode(e: CustomEvent): void {
    const nodeId = e.detail.nodeId as string

    if (!this.svgElement || !this.nodeSelection) return

    // Find the node
    const targetNode = this.nodeSelection.data().find((d) => d.id === nodeId)
    if (!targetNode || targetNode.x === undefined || targetNode.y === undefined) return

    // Zoom to the node
    const svg = d3.select(this.svgElement)
    const width = this.containerElement.clientWidth
    const height = this.containerElement.clientHeight

    const scale = 2 // Zoom level when focusing
    const translateX = width / 2 - targetNode.x * scale
    const translateY = height / 2 - targetNode.y * scale

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

    // Update zoom scale for LOD
    this.currentZoomScale = scale
    this.updateLabelVisibility()

    // Highlight the focused node
    this.highlightedNodeIds = new Set([nodeId])
    this.nodeSelection.select('circle')
      .attr('stroke', (d) => d.id === nodeId ? '#f59e0b' : '#fff')
      .attr('stroke-width', (d) => d.id === nodeId ? 4 : 2)
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
              <div style="font-size: 3rem; margin-bottom: 1rem;"></div>
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
          ${this.isLoading
            ? html`<div class="loading">Loading graph...</div>`
            : this.graphData?.nodes.length === 0
            ? html`
                <div class="empty-state">
                  <div class="empty-state-icon"></div>
                  <div class="empty-state-title">No graph data available</div>
                  <div class="empty-state-message">
                    Extract entities from web pages to build your knowledge graph.
                  </div>
                </div>
              `
            : html`
                <svg class="graph-svg"></svg>
                ${this.renderTooltip()}

                <!-- Floating panels overlay -->
                <div class="floating-panels">
                  <graph-controls
                    .depth=${this.depth}
                    .confidenceThreshold=${this.confidenceThreshold}
                    .selectedTypes=${this.selectedTypes}
                    @depth-change=${this.handleDepthChange}
                    @confidence-change=${this.handleConfidenceChange}
                    @type-filter-change=${this.handleTypeFilterChange}
                    @reset-layout=${this.handleResetLayout}
                    @fit-view=${this.handleFitView}
                  ></graph-controls>

                  <graph-search
                    .nodes=${this.graphData?.nodes || []}
                    @search-highlight=${this.handleSearchHighlight}
                    @focus-node=${this.handleFocusNode}
                  ></graph-search>

                  <graph-minimap
                    .nodePositions=${this.minimapNodePositions}
                    .viewport=${this.minimapViewport}
                    .graphBounds=${this.minimapGraphBounds}
                    @navigate=${this.handleMinimapNavigate}
                  ></graph-minimap>

                  <graph-legend></graph-legend>
                </div>
              `}
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
