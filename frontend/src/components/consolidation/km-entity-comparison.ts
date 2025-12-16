import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { EntitySummary, SimilarityBreakdown } from '../../api/types'

/**
 * Entity comparison component
 *
 * Side-by-side entity comparison view with:
 * - Highlight similarities and differences
 * - Property comparison table
 * - Visual indicators for matching/differing fields
 *
 * @element km-entity-comparison
 * @fires select-canonical - When user selects an entity as canonical
 */
@customElement('km-entity-comparison')
export class KmEntityComparison extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .comparison-container {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      gap: 1rem;
      align-items: start;
    }

    @media (max-width: 768px) {
      .comparison-container {
        grid-template-columns: 1fr;
      }
    }

    .entity-panel {
      background: white;
      border-radius: 0.5rem;
      border: 2px solid #e5e7eb;
      overflow: hidden;
      transition: border-color 0.2s;
    }

    .entity-panel:hover {
      border-color: #d1d5db;
    }

    .entity-panel.selected {
      border-color: #1e3a8a;
      box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
    }

    .entity-panel.canonical {
      border-color: #10b981;
    }

    .entity-header {
      padding: 1rem;
      background: #f9fafb;
      border-bottom: 1px solid #e5e7eb;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
    }

    .entity-name {
      font-size: 1rem;
      font-weight: 600;
      color: #1f2937;
      margin: 0;
      word-break: break-word;
    }

    .entity-type-badge {
      display: inline-flex;
      align-items: center;
      padding: 0.25rem 0.5rem;
      background: #dbeafe;
      color: #1e40af;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
      white-space: nowrap;
    }

    .canonical-badge {
      background: #d1fae5;
      color: #065f46;
    }

    .entity-body {
      padding: 1rem;
    }

    .property-row {
      display: flex;
      padding: 0.5rem 0;
      border-bottom: 1px solid #f3f4f6;
    }

    .property-row:last-child {
      border-bottom: none;
    }

    .property-label {
      flex: 0 0 120px;
      font-size: 0.75rem;
      font-weight: 500;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .property-value {
      flex: 1;
      font-size: 0.875rem;
      color: #374151;
      word-break: break-word;
    }

    .property-value.match {
      background: #d1fae5;
      padding: 0.125rem 0.25rem;
      border-radius: 0.25rem;
      color: #065f46;
    }

    .property-value.different {
      background: #fef3c7;
      padding: 0.125rem 0.25rem;
      border-radius: 0.25rem;
      color: #92400e;
    }

    .property-value.empty {
      color: #9ca3af;
      font-style: italic;
    }

    .select-btn {
      padding: 0.5rem 1rem;
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      cursor: pointer;
      transition: all 0.2s;
    }

    .select-btn:hover:not(:disabled) {
      background: #f9fafb;
      border-color: #1e3a8a;
      color: #1e3a8a;
    }

    .select-btn.selected {
      background: #1e3a8a;
      border-color: #1e3a8a;
      color: white;
    }

    .select-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    /* Comparison column */
    .comparison-column {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 1rem 0.5rem;
      min-width: 100px;
    }

    @media (max-width: 768px) {
      .comparison-column {
        flex-direction: row;
        justify-content: center;
        padding: 0.5rem;
        gap: 1rem;
      }
    }

    .comparison-icon {
      font-size: 1.5rem;
      margin-bottom: 0.5rem;
    }

    .similarity-label {
      font-size: 0.75rem;
      color: #6b7280;
      text-align: center;
      margin-bottom: 0.5rem;
    }

    .similarity-indicators {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      width: 100%;
    }

    @media (max-width: 768px) {
      .similarity-indicators {
        flex-direction: row;
        flex-wrap: wrap;
        justify-content: center;
      }
    }

    .indicator {
      display: flex;
      align-items: center;
      gap: 0.25rem;
      font-size: 0.625rem;
      padding: 0.125rem 0.25rem;
      border-radius: 0.25rem;
      background: #f3f4f6;
    }

    .indicator.match {
      background: #d1fae5;
      color: #065f46;
    }

    .indicator-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: currentColor;
    }

    /* Entity footer */
    .entity-footer {
      padding: 0.75rem 1rem;
      background: #f9fafb;
      border-top: 1px solid #e5e7eb;
      display: flex;
      justify-content: center;
    }
  `

  /** First entity to compare */
  @property({ type: Object })
  entityA: EntitySummary | null = null

  /** Second entity to compare */
  @property({ type: Object })
  entityB: EntitySummary | null = null

  /** Similarity breakdown for comparison */
  @property({ type: Object })
  breakdown: SimilarityBreakdown | null = null

  /** Currently selected canonical entity ID */
  @property({ type: String })
  selectedCanonical: string | null = null

  /** Whether selection is enabled */
  @property({ type: Boolean })
  selectable = false

  /** Whether to show the comparison column */
  @property({ type: Boolean, attribute: 'show-comparison' })
  showComparison = true

  private handleSelectCanonical(entityId: string) {
    if (!this.selectable) return

    this.selectedCanonical = entityId
    this.dispatchEvent(
      new CustomEvent('select-canonical', {
        detail: { entityId },
        bubbles: true,
        composed: true,
      })
    )
  }

  private compareNames(): 'match' | 'similar' | 'different' {
    if (!this.entityA || !this.entityB) return 'different'

    // Exact match
    if (this.entityA.name === this.entityB.name) return 'match'

    // Check normalized names
    if (
      this.entityA.normalized_name &&
      this.entityB.normalized_name &&
      this.entityA.normalized_name === this.entityB.normalized_name
    ) {
      return 'match'
    }

    // Check case-insensitive
    if (this.entityA.name.toLowerCase() === this.entityB.name.toLowerCase()) {
      return 'similar'
    }

    return 'different'
  }

  private compareTypes(): boolean {
    return this.entityA?.entity_type === this.entityB?.entity_type
  }

  private renderEntityPanel(entity: EntitySummary, position: 'a' | 'b') {
    const isSelected = this.selectedCanonical === entity.id
    const otherEntity = position === 'a' ? this.entityB : this.entityA

    const nameComparison = this.compareNames()
    const typeMatch = this.compareTypes()

    return html`
      <div
        class="entity-panel ${isSelected ? 'selected' : ''} ${entity.is_canonical ? 'canonical' : ''}"
        role="article"
        aria-label="Entity ${position.toUpperCase()}: ${entity.name}"
      >
        <div class="entity-header">
          <div>
            <h3 class="entity-name">${entity.name}</h3>
          </div>
          <div style="display: flex; gap: 0.25rem; align-items: center;">
            ${entity.is_canonical
              ? html`<span class="entity-type-badge canonical">Canonical</span>`
              : null}
            <span class="entity-type-badge">${entity.entity_type}</span>
          </div>
        </div>

        <div class="entity-body">
          <div class="property-row">
            <span class="property-label">Name</span>
            <span
              class="property-value ${nameComparison === 'match' ? 'match' : nameComparison === 'similar' ? 'different' : ''}"
            >
              ${entity.name}
            </span>
          </div>

          <div class="property-row">
            <span class="property-label">Normalized</span>
            <span class="property-value ${entity.normalized_name ? '' : 'empty'}">
              ${entity.normalized_name || 'Not normalized'}
            </span>
          </div>

          <div class="property-row">
            <span class="property-label">Type</span>
            <span class="property-value ${typeMatch ? 'match' : 'different'}">
              ${entity.entity_type}
            </span>
          </div>

          <div class="property-row">
            <span class="property-label">Description</span>
            <span class="property-value ${entity.description ? '' : 'empty'}">
              ${entity.description || 'No description'}
            </span>
          </div>

          <div class="property-row">
            <span class="property-label">ID</span>
            <span class="property-value" style="font-family: monospace; font-size: 0.75rem;">
              ${entity.id}
            </span>
          </div>
        </div>

        ${this.selectable
          ? html`
              <div class="entity-footer">
                <button
                  class="select-btn ${isSelected ? 'selected' : ''}"
                  @click=${() => this.handleSelectCanonical(entity.id)}
                  aria-pressed=${isSelected}
                >
                  ${isSelected ? 'Selected as Canonical' : 'Select as Canonical'}
                </button>
              </div>
            `
          : null}
      </div>
    `
  }

  private renderComparisonColumn() {
    if (!this.showComparison || !this.entityA || !this.entityB) return null

    const nameMatch = this.compareNames()
    const typeMatch = this.compareTypes()

    const indicators = []

    // Add similarity indicators from breakdown
    if (this.breakdown) {
      if (this.breakdown.type_match !== null) {
        indicators.push({
          label: 'Type',
          match: this.breakdown.type_match,
        })
      }
      if (this.breakdown.soundex_match !== null) {
        indicators.push({
          label: 'Soundex',
          match: this.breakdown.soundex_match,
        })
      }
      if (this.breakdown.metaphone_match !== null) {
        indicators.push({
          label: 'Metaphone',
          match: this.breakdown.metaphone_match,
        })
      }
      if (this.breakdown.same_page !== null) {
        indicators.push({
          label: 'Same Page',
          match: this.breakdown.same_page,
        })
      }
    } else {
      // Fallback indicators
      indicators.push({
        label: 'Name',
        match: nameMatch === 'match',
      })
      indicators.push({
        label: 'Type',
        match: typeMatch,
      })
    }

    return html`
      <div class="comparison-column" role="presentation">
        <div class="comparison-icon" aria-hidden="true">
          ${nameMatch === 'match' && typeMatch ? '\u{2194}\u{FE0F}' : '\u{1F504}'}
        </div>
        <div class="similarity-label">Comparison</div>
        <div class="similarity-indicators">
          ${indicators.map(
            (ind) => html`
              <div class="indicator ${ind.match ? 'match' : ''}">
                <span class="indicator-dot"></span>
                <span>${ind.label}</span>
              </div>
            `
          )}
        </div>
      </div>
    `
  }

  render() {
    if (!this.entityA || !this.entityB) {
      return html`
        <div class="comparison-container">
          <p style="color: #6b7280; text-align: center; grid-column: 1 / -1;">
            No entities to compare
          </p>
        </div>
      `
    }

    return html`
      <div class="comparison-container">
        ${this.renderEntityPanel(this.entityA, 'a')}
        ${this.renderComparisonColumn()}
        ${this.renderEntityPanel(this.entityB, 'b')}
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'km-entity-comparison': KmEntityComparison
  }
}
