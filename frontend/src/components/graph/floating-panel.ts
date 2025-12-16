import { LitElement, html, css, PropertyValues } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'

/**
 * Position options for the floating panel.
 */
export type FloatingPanelPosition = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'

/**
 * Event detail for toggle events.
 */
export interface FloatingPanelToggleEventDetail {
  collapsed: boolean
}

/**
 * Event detail for position change events (from dragging).
 */
export interface FloatingPanelPositionChangeEventDetail {
  x: number
  y: number
}

/**
 * Floating Panel Component
 *
 * A reusable floating panel container for controls, legends, and other
 * floating UI elements over the graph visualization.
 *
 * @fires toggle - Dispatched when the panel is expanded or collapsed
 * @fires position-change - Dispatched when the panel is dragged to a new position
 *
 * @slot - Default slot for panel content
 *
 * @example
 * ```html
 * <floating-panel
 *   panel-title="Controls"
 *   position="top-left"
 *   collapsible
 * >
 *   <graph-controls></graph-controls>
 * </floating-panel>
 * ```
 */
@customElement('floating-panel')
export class FloatingPanel extends LitElement {
  static styles = css`
    :host {
      display: block;
      position: absolute;
      z-index: 100;
      pointer-events: auto;
    }

    /* Position variants */
    :host([position='top-left']) {
      top: 1rem;
      left: 1rem;
    }

    :host([position='top-right']) {
      top: 1rem;
      right: 1rem;
    }

    :host([position='bottom-left']) {
      bottom: 1rem;
      left: 1rem;
    }

    :host([position='bottom-right']) {
      bottom: 1rem;
      right: 1rem;
    }

    /* Custom position (when dragged) */
    :host([data-custom-position]) {
      top: auto !important;
      left: auto !important;
      right: auto !important;
      bottom: auto !important;
    }

    .panel {
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      border-radius: 0.5rem;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      overflow: hidden;
      min-width: 200px;
      max-width: 320px;
      transition:
        min-width 0.2s ease-in-out,
        max-width 0.2s ease-in-out,
        box-shadow 0.2s ease-in-out;
    }

    .panel.collapsed {
      min-width: auto;
      max-width: none;
    }

    .panel.dragging {
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
      cursor: grabbing;
    }

    .panel-header {
      background: #1f2937;
      color: white;
      padding: 0.75rem 1rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.5rem;
      user-select: none;
      transition: padding 0.2s ease-in-out;
    }

    .panel-header.draggable {
      cursor: grab;
    }

    .panel-header.draggable:active {
      cursor: grabbing;
    }

    .panel.collapsed .panel-header {
      padding: 0.5rem 0.75rem;
    }

    .header-content {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex: 1;
      min-width: 0;
    }

    .collapsed-icon {
      display: none;
      font-size: 1.25rem;
      line-height: 1;
      flex-shrink: 0;
    }

    .panel.collapsed .collapsed-icon {
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .panel-title {
      font-size: 0.875rem;
      font-weight: 600;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .panel.collapsed .panel-title {
      display: none;
    }

    .collapse-button {
      background: none;
      border: none;
      color: white;
      cursor: pointer;
      padding: 0.25rem;
      border-radius: 0.25rem;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      transition: background 0.15s ease-in-out;
    }

    .collapse-button:hover {
      background: rgba(255, 255, 255, 0.1);
    }

    .collapse-button:focus {
      outline: 2px solid rgba(255, 255, 255, 0.5);
      outline-offset: 2px;
    }

    .collapse-button:focus:not(:focus-visible) {
      outline: none;
    }

    .collapse-button svg {
      transition: transform 0.2s ease-in-out;
    }

    .panel.collapsed .collapse-button svg {
      transform: rotate(180deg);
    }

    .panel-content {
      max-height: 400px;
      overflow-y: auto;
      overflow-x: hidden;
      transition:
        max-height 0.2s ease-in-out,
        opacity 0.2s ease-in-out;
    }

    .panel.collapsed .panel-content {
      max-height: 0;
      opacity: 0;
      overflow: hidden;
    }

    /* Scrollbar styling */
    .panel-content::-webkit-scrollbar {
      width: 6px;
    }

    .panel-content::-webkit-scrollbar-track {
      background: #f1f5f9;
    }

    .panel-content::-webkit-scrollbar-thumb {
      background: #cbd5e1;
      border-radius: 3px;
    }

    .panel-content::-webkit-scrollbar-thumb:hover {
      background: #94a3b8;
    }

    /* High contrast mode support */
    @media (prefers-contrast: high) {
      .panel {
        border: 2px solid #000;
      }

      .panel-header {
        background: #000;
      }

      .collapse-button:focus {
        outline: 3px solid #fff;
      }
    }

    /* Reduced motion support */
    @media (prefers-reduced-motion: reduce) {
      .panel,
      .panel-header,
      .collapse-button svg,
      .panel-content {
        transition: none;
      }
    }
  `

  /**
   * Panel title shown in header.
   */
  @property({ type: String, attribute: 'panel-title' })
  panelTitle = ''

  /**
   * Position in viewport (top-left, top-right, bottom-left, bottom-right).
   * This is reflected to an attribute for CSS styling.
   */
  @property({ type: String, reflect: true })
  position: FloatingPanelPosition = 'top-left'

  /**
   * Initial collapsed state. When true, panel starts collapsed.
   */
  @property({ type: Boolean })
  collapsed = false

  /**
   * Icon to display when panel is collapsed (optional).
   * Can be an emoji, text, or unicode character.
   */
  @property({ type: String, attribute: 'collapsed-icon' })
  collapsedIcon = ''

  /**
   * Whether the panel can be collapsed. When false, the collapse
   * button is hidden and header clicks don't toggle state.
   */
  @property({ type: Boolean })
  collapsible = true

  /**
   * Whether the panel can be dragged to reposition.
   */
  @property({ type: Boolean })
  draggable = false

  /**
   * Internal collapsed state.
   */
  @state()
  private isCollapsed = false

  /**
   * Whether the panel is currently being dragged.
   */
  @state()
  private isDragging = false

  /**
   * Offset for drag positioning.
   */
  private dragOffset = { x: 0, y: 0 }

  /**
   * Bound event handlers for proper cleanup.
   */
  private boundHandleMouseMove: ((e: MouseEvent) => void) | null = null
  private boundHandleMouseUp: (() => void) | null = null

  connectedCallback(): void {
    super.connectedCallback()
    this.isCollapsed = this.collapsed
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.cleanupDragListeners()
  }

  updated(changedProperties: PropertyValues): void {
    super.updated(changedProperties)

    // Sync isCollapsed when collapsed prop changes externally
    if (changedProperties.has('collapsed') && changedProperties.get('collapsed') !== undefined) {
      this.isCollapsed = this.collapsed
    }
  }

  /**
   * Toggle the collapsed state of the panel.
   */
  toggle(): void {
    if (!this.collapsible) return
    this.isCollapsed = !this.isCollapsed
    this.dispatchToggleEvent()
  }

  /**
   * Expand the panel (if collapsible).
   */
  expand(): void {
    if (!this.collapsible || !this.isCollapsed) return
    this.isCollapsed = false
    this.dispatchToggleEvent()
  }

  /**
   * Collapse the panel (if collapsible).
   */
  collapse(): void {
    if (!this.collapsible || this.isCollapsed) return
    this.isCollapsed = true
    this.dispatchToggleEvent()
  }

  private dispatchToggleEvent(): void {
    this.dispatchEvent(
      new CustomEvent<FloatingPanelToggleEventDetail>('toggle', {
        detail: { collapsed: this.isCollapsed },
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleHeaderClick(e: MouseEvent): void {
    // Don't toggle if clicking the collapse button (it has its own handler)
    // or if we're dragging
    if ((e.target as HTMLElement).closest('.collapse-button') || this.isDragging) {
      return
    }

    if (this.collapsible) {
      this.toggle()
    }
  }

  private handleHeaderKeydown(e: KeyboardEvent): void {
    if (!this.collapsible) return

    // Don't handle if focused on the collapse button
    if ((e.target as HTMLElement).closest('.collapse-button')) {
      return
    }

    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      this.toggle()
    }
  }

  private handleCollapseButtonClick(e: MouseEvent): void {
    e.stopPropagation()
    if (this.collapsible) {
      this.toggle()
    }
  }

  private handleCollapseButtonKeydown(e: KeyboardEvent): void {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      e.stopPropagation()
      if (this.collapsible) {
        this.toggle()
      }
    }
  }

  // Drag functionality
  private handleDragStart(e: MouseEvent): void {
    if (!this.draggable || (e.target as HTMLElement).closest('.collapse-button')) {
      return
    }

    // Only respond to left mouse button
    if (e.button !== 0) return

    e.preventDefault()

    const rect = this.getBoundingClientRect()
    this.dragOffset = {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    }

    this.isDragging = true

    // Set up document-level listeners for drag
    this.boundHandleMouseMove = this.handleMouseMove.bind(this)
    this.boundHandleMouseUp = this.handleMouseUp.bind(this)

    document.addEventListener('mousemove', this.boundHandleMouseMove)
    document.addEventListener('mouseup', this.boundHandleMouseUp)
  }

  private handleMouseMove(e: MouseEvent): void {
    if (!this.isDragging) return

    const newX = e.clientX - this.dragOffset.x
    const newY = e.clientY - this.dragOffset.y

    // Apply custom positioning
    this.setAttribute('data-custom-position', '')
    this.style.left = `${newX}px`
    this.style.top = `${newY}px`

    this.dispatchEvent(
      new CustomEvent<FloatingPanelPositionChangeEventDetail>('position-change', {
        detail: { x: newX, y: newY },
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleMouseUp(): void {
    this.isDragging = false
    this.cleanupDragListeners()
  }

  private cleanupDragListeners(): void {
    if (this.boundHandleMouseMove) {
      document.removeEventListener('mousemove', this.boundHandleMouseMove)
      this.boundHandleMouseMove = null
    }
    if (this.boundHandleMouseUp) {
      document.removeEventListener('mouseup', this.boundHandleMouseUp)
      this.boundHandleMouseUp = null
    }
  }

  /**
   * Reset the panel position to its original position attribute.
   */
  resetPosition(): void {
    this.removeAttribute('data-custom-position')
    this.style.left = ''
    this.style.top = ''
  }

  private renderCollapseIcon() {
    return html`
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <polyline points="18 15 12 9 6 15"></polyline>
      </svg>
    `
  }

  render() {
    const panelClasses = [
      'panel',
      this.isCollapsed ? 'collapsed' : '',
      this.isDragging ? 'dragging' : '',
    ]
      .filter(Boolean)
      .join(' ')

    const headerClasses = ['panel-header', this.draggable ? 'draggable' : ''].filter(Boolean).join(' ')

    return html`
      <div class=${panelClasses} role="region" aria-label=${this.panelTitle || 'Panel'}>
        <div
          class=${headerClasses}
          @click=${this.handleHeaderClick}
          @keydown=${this.handleHeaderKeydown}
          @mousedown=${this.handleDragStart}
          role=${this.collapsible ? 'button' : 'heading'}
          tabindex=${this.collapsible ? '0' : '-1'}
          aria-expanded=${this.collapsible ? String(!this.isCollapsed) : undefined}
          aria-controls=${this.collapsible ? 'panel-content' : undefined}
        >
          <div class="header-content">
            ${this.collapsedIcon
              ? html` <span class="collapsed-icon" aria-hidden="true">${this.collapsedIcon}</span> `
              : null}
            <span class="panel-title">${this.panelTitle}</span>
          </div>

          ${this.collapsible
            ? html`
                <button
                  class="collapse-button"
                  @click=${this.handleCollapseButtonClick}
                  @keydown=${this.handleCollapseButtonKeydown}
                  aria-label=${this.isCollapsed ? 'Expand panel' : 'Collapse panel'}
                  type="button"
                >
                  ${this.renderCollapseIcon()}
                </button>
              `
            : null}
        </div>

        <div
          id="panel-content"
          class="panel-content"
          aria-hidden=${this.isCollapsed ? 'true' : 'false'}
        >
          <slot></slot>
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'floating-panel': FloatingPanel
  }
}
