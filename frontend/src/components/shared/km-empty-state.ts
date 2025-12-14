import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'

/**
 * Reusable empty state component for lists and tables.
 *
 * @slot action - Optional slot for action buttons
 */
@customElement('km-empty-state')
export class KmEmptyState extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .empty-state {
      text-align: center;
      padding: 3rem 1.5rem;
      color: #6b7280;
    }

    .empty-state-icon {
      font-size: 3rem;
      margin-bottom: 1rem;
      opacity: 0.8;
    }

    .empty-state-title {
      font-size: 1rem;
      font-weight: 500;
      color: #374151;
      margin: 0 0 0.5rem 0;
    }

    .empty-state-message {
      font-size: 0.875rem;
      color: #6b7280;
      margin: 0 0 1.5rem 0;
      max-width: 24rem;
      margin-left: auto;
      margin-right: auto;
    }

    .empty-state-action {
      display: flex;
      justify-content: center;
      gap: 0.5rem;
    }
  `

  /** Icon to display (emoji or symbol) */
  @property({ type: String })
  icon = '📋'

  /** Title text */
  @property({ type: String })
  title = 'No items found'

  /** Description message */
  @property({ type: String })
  message = ''

  render() {
    return html`
      <div class="empty-state" role="status">
        <div class="empty-state-icon" aria-hidden="true">${this.icon}</div>
        <h3 class="empty-state-title">${this.title}</h3>
        ${this.message
          ? html`<p class="empty-state-message">${this.message}</p>`
          : null}
        <div class="empty-state-action">
          <slot name="action"></slot>
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'km-empty-state': KmEmptyState
  }
}
