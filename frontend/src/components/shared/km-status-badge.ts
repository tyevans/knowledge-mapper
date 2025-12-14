import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { JobStatus, EntityType } from '../../api/scraping-types'
import {
  JOB_STATUS_COLORS,
  ENTITY_TYPE_COLORS,
  JOB_STATUS_LABELS,
  ENTITY_TYPE_LABELS,
} from '../../api/scraping-types'

/**
 * Badge type determines which color scheme to use.
 */
export type BadgeType = 'job-status' | 'entity-type' | 'extraction-status' | 'custom'

/**
 * Reusable status badge component with color-coded variants.
 */
@customElement('km-status-badge')
export class KmStatusBadge extends LitElement {
  static styles = css`
    :host {
      display: inline-block;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      padding: 0.125rem 0.5rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
      white-space: nowrap;
    }

    .badge-dot {
      width: 0.375rem;
      height: 0.375rem;
      border-radius: 50%;
      background: currentColor;
    }

    /* Extraction status badges */
    .extraction-pending {
      background: #e5e7eb;
      color: #374151;
    }

    .extraction-completed {
      background: #d1fae5;
      color: #065f46;
    }

    .extraction-failed {
      background: #fee2e2;
      color: #991b1b;
    }

    /* Custom/generic badges */
    .badge-gray {
      background: #f3f4f6;
      color: #6b7280;
    }

    .badge-blue {
      background: #dbeafe;
      color: #1e40af;
    }

    .badge-green {
      background: #d1fae5;
      color: #065f46;
    }

    .badge-yellow {
      background: #fef3c7;
      color: #92400e;
    }

    .badge-red {
      background: #fee2e2;
      color: #991b1b;
    }

    .badge-purple {
      background: #ede9fe;
      color: #5b21b6;
    }
  `

  /** The status value to display */
  @property({ type: String })
  status: string = ''

  /** Badge type for color scheme selection */
  @property({ type: String })
  type: BadgeType = 'custom'

  /** Custom label override (defaults to formatted status) */
  @property({ type: String })
  label?: string

  /** Whether to show a dot indicator */
  @property({ type: Boolean, attribute: 'show-dot' })
  showDot = false

  /** Custom color variant for 'custom' type */
  @property({ type: String })
  variant: 'gray' | 'blue' | 'green' | 'yellow' | 'red' | 'purple' = 'gray'

  private getStyles(): { background: string; color: string } | null {
    switch (this.type) {
      case 'job-status':
        return JOB_STATUS_COLORS[this.status as JobStatus] || null

      case 'entity-type':
        const entityColor = ENTITY_TYPE_COLORS[this.status as EntityType]
        if (entityColor) {
          return {
            background: `${entityColor}20`,
            color: entityColor,
          }
        }
        return null

      case 'extraction-status':
        // Handled via CSS classes
        return null

      default:
        return null
    }
  }

  private getLabel(): string {
    if (this.label) {
      return this.label
    }

    switch (this.type) {
      case 'job-status':
        return JOB_STATUS_LABELS[this.status as JobStatus] || this.status

      case 'entity-type':
        return ENTITY_TYPE_LABELS[this.status as EntityType] || this.status

      default:
        // Capitalize first letter
        return this.status.charAt(0).toUpperCase() + this.status.slice(1).replace(/_/g, ' ')
    }
  }

  private getCssClass(): string {
    switch (this.type) {
      case 'extraction-status':
        return `extraction-${this.status}`

      case 'custom':
        return `badge-${this.variant}`

      default:
        return ''
    }
  }

  render() {
    const customStyles = this.getStyles()
    const label = this.getLabel()
    const cssClass = this.getCssClass()

    return html`
      <span
        class="badge ${cssClass}"
        style=${customStyles
          ? `background: ${customStyles.background}; color: ${customStyles.color};`
          : ''}
        role="status"
        aria-label="${this.type}: ${label}"
      >
        ${this.showDot ? html`<span class="badge-dot"></span>` : null}
        ${label}
      </span>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'km-status-badge': KmStatusBadge
  }
}
