import { LitElement, html, css } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import type { MergeCandidate, ReviewDecision } from '../../api/types'
import './km-confidence-score'
import './km-entity-comparison'

/**
 * Merge candidate card component
 *
 * Card showing two entities as merge candidates with:
 * - Display similarity scores and confidence
 * - Entity comparison view
 * - Action buttons (merge, reject, defer)
 *
 * @element km-merge-candidate-card
 * @fires merge - When user approves merge
 * @fires reject - When user rejects merge
 * @fires defer - When user defers decision
 * @fires view-entity - When user wants to view entity details
 */
@customElement('km-merge-candidate-card')
export class KmMergeCandidateCard extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .card {
      background: white;
      border-radius: 0.75rem;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
      overflow: hidden;
      transition: box-shadow 0.2s;
    }

    .card:hover {
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }

    .card-header {
      padding: 1rem 1.5rem;
      background: #f9fafb;
      border-bottom: 1px solid #e5e7eb;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
    }

    .header-left {
      display: flex;
      align-items: center;
      gap: 1rem;
    }

    .header-title {
      font-size: 0.875rem;
      font-weight: 500;
      color: #374151;
    }

    .decision-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      padding: 0.25rem 0.5rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
    }

    .decision-badge.auto_merge {
      background: #d1fae5;
      color: #065f46;
    }

    .decision-badge.review {
      background: #fef3c7;
      color: #92400e;
    }

    .decision-badge.reject {
      background: #fee2e2;
      color: #991b1b;
    }

    .blocking-keys {
      display: flex;
      gap: 0.25rem;
      flex-wrap: wrap;
    }

    .blocking-key {
      font-size: 0.625rem;
      padding: 0.125rem 0.375rem;
      background: #e5e7eb;
      color: #4b5563;
      border-radius: 0.25rem;
      font-family: monospace;
    }

    .card-body {
      padding: 1.5rem;
    }

    .entity-names {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 1rem;
      margin-bottom: 1.5rem;
      flex-wrap: wrap;
    }

    .entity-name {
      font-size: 1.125rem;
      font-weight: 600;
      color: #1f2937;
      cursor: pointer;
      transition: color 0.2s;
    }

    .entity-name:hover {
      color: #1e3a8a;
      text-decoration: underline;
    }

    .merge-arrow {
      font-size: 1.5rem;
      color: #9ca3af;
    }

    .similarity-section {
      background: #f9fafb;
      border-radius: 0.5rem;
      padding: 1rem;
      margin-bottom: 1.5rem;
    }

    .similarity-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.75rem;
    }

    .similarity-title {
      font-size: 0.875rem;
      font-weight: 500;
      color: #374151;
    }

    .similarity-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 0.75rem;
    }

    .similarity-item {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
    }

    .similarity-label {
      font-size: 0.75rem;
      color: #6b7280;
    }

    .similarity-value {
      font-size: 0.875rem;
      font-weight: 500;
      color: #374151;
    }

    .similarity-value.high {
      color: #059669;
    }

    .similarity-value.medium {
      color: #d97706;
    }

    .similarity-value.low {
      color: #dc2626;
    }

    .similarity-value.boolean-true {
      color: #059669;
    }

    .similarity-value.boolean-false {
      color: #dc2626;
    }

    .card-footer {
      padding: 1rem 1.5rem;
      background: #f9fafb;
      border-top: 1px solid #e5e7eb;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
    }

    .footer-info {
      font-size: 0.75rem;
      color: #6b7280;
    }

    .action-buttons {
      display: flex;
      gap: 0.5rem;
    }

    .action-btn {
      padding: 0.5rem 1rem;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
      border: 1px solid;
    }

    .action-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .action-btn.merge {
      background: #1e3a8a;
      border-color: #1e3a8a;
      color: white;
    }

    .action-btn.merge:hover:not(:disabled) {
      background: #1e40af;
    }

    .action-btn.reject {
      background: white;
      border-color: #ef4444;
      color: #ef4444;
    }

    .action-btn.reject:hover:not(:disabled) {
      background: #fee2e2;
    }

    .action-btn.defer {
      background: white;
      border-color: #e5e7eb;
      color: #374151;
    }

    .action-btn.defer:hover:not(:disabled) {
      background: #f9fafb;
      border-color: #d1d5db;
    }

    /* Expanded view toggle */
    .expand-toggle {
      padding: 0.5rem;
      background: transparent;
      border: none;
      color: #6b7280;
      cursor: pointer;
      font-size: 0.875rem;
      display: flex;
      align-items: center;
      gap: 0.25rem;
    }

    .expand-toggle:hover {
      color: #374151;
    }

    .expanded-content {
      padding: 1.5rem;
      border-top: 1px solid #e5e7eb;
    }

    /* Loading state */
    .loading-overlay {
      position: absolute;
      inset: 0;
      background: rgba(255, 255, 255, 0.8);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10;
    }

    .card-wrapper {
      position: relative;
    }
  `

  /** The merge candidate data */
  @property({ type: Object })
  candidate: MergeCandidate | null = null

  /** Whether to show expanded comparison view */
  @property({ type: Boolean })
  expanded = false

  /** Whether the card is in loading state */
  @property({ type: Boolean })
  loading = false

  /** Whether actions are disabled */
  @property({ type: Boolean })
  disabled = false

  /** Selected canonical entity ID for merge */
  @state()
  private selectedCanonical: string | null = null

  private handleMerge() {
    if (!this.candidate || this.disabled) return

    const canonicalId = this.selectedCanonical || this.candidate.entity_a.id
    const mergedId =
      canonicalId === this.candidate.entity_a.id
        ? this.candidate.entity_b.id
        : this.candidate.entity_a.id

    this.dispatchEvent(
      new CustomEvent('merge', {
        detail: {
          canonical_entity_id: canonicalId,
          merged_entity_ids: [mergedId],
          review_item_id: this.candidate.review_item_id,
          similarity_scores: this.candidate.similarity_breakdown,
        },
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleReject() {
    if (!this.candidate || this.disabled) return

    this.dispatchEvent(
      new CustomEvent('reject', {
        detail: {
          review_item_id: this.candidate.review_item_id,
          entity_a_id: this.candidate.entity_a.id,
          entity_b_id: this.candidate.entity_b.id,
        },
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleDefer() {
    if (!this.candidate || this.disabled) return

    this.dispatchEvent(
      new CustomEvent('defer', {
        detail: {
          review_item_id: this.candidate.review_item_id,
          entity_a_id: this.candidate.entity_a.id,
          entity_b_id: this.candidate.entity_b.id,
        },
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleViewEntity(entityId: string) {
    this.dispatchEvent(
      new CustomEvent('view-entity', {
        detail: { entityId },
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleSelectCanonical(e: CustomEvent) {
    this.selectedCanonical = e.detail.entityId
  }

  private toggleExpanded() {
    this.expanded = !this.expanded
  }

  private formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  private getDecisionLabel(decision: string): string {
    switch (decision) {
      case 'auto_merge':
        return 'Auto Merge'
      case 'review':
        return 'Needs Review'
      case 'reject':
        return 'Unlikely Match'
      default:
        return decision
    }
  }

  private renderSimilarityValue(value: number | boolean | null, label: string) {
    if (value === null || value === undefined) return null

    if (typeof value === 'boolean') {
      return html`
        <div class="similarity-item">
          <span class="similarity-label">${label}</span>
          <span class="similarity-value ${value ? 'boolean-true' : 'boolean-false'}">
            ${value ? 'Yes' : 'No'}
          </span>
        </div>
      `
    }

    const level = value >= 0.7 ? 'high' : value >= 0.5 ? 'medium' : 'low'

    return html`
      <div class="similarity-item">
        <span class="similarity-label">${label}</span>
        <span class="similarity-value ${level}">${Math.round(value * 100)}%</span>
      </div>
    `
  }

  render() {
    if (!this.candidate) {
      return html`<div class="card"><p style="padding: 1.5rem; color: #6b7280;">No candidate data</p></div>`
    }

    const { entity_a, entity_b, confidence, decision, similarity_breakdown, blocking_keys, computed_at } =
      this.candidate

    return html`
      <div class="card-wrapper">
        ${this.loading
          ? html`
              <div class="loading-overlay">
                <span>Processing...</span>
              </div>
            `
          : null}

        <div class="card">
          <div class="card-header">
            <div class="header-left">
              <span class="header-title">Merge Candidate</span>
              <span class="decision-badge ${decision}">${this.getDecisionLabel(decision)}</span>
              <km-confidence-score
                .score=${confidence}
                .breakdown=${similarity_breakdown}
                show-bar
                show-tooltip
              ></km-confidence-score>
            </div>
            <div class="blocking-keys">
              ${blocking_keys.map(
                (key) => html`<span class="blocking-key">${key}</span>`
              )}
            </div>
          </div>

          <div class="card-body">
            <div class="entity-names">
              <span
                class="entity-name"
                @click=${() => this.handleViewEntity(entity_a.id)}
                @keydown=${(e: KeyboardEvent) => e.key === 'Enter' && this.handleViewEntity(entity_a.id)}
                tabindex="0"
                role="button"
              >
                ${entity_a.name}
              </span>
              <span class="merge-arrow" aria-hidden="true">\u{2194}</span>
              <span
                class="entity-name"
                @click=${() => this.handleViewEntity(entity_b.id)}
                @keydown=${(e: KeyboardEvent) => e.key === 'Enter' && this.handleViewEntity(entity_b.id)}
                tabindex="0"
                role="button"
              >
                ${entity_b.name}
              </span>
            </div>

            <div class="similarity-section">
              <div class="similarity-header">
                <span class="similarity-title">Similarity Scores</span>
                <button
                  class="expand-toggle"
                  @click=${this.toggleExpanded}
                  aria-expanded=${this.expanded}
                >
                  ${this.expanded ? 'Hide Details' : 'Show Details'}
                  <span aria-hidden="true">${this.expanded ? '\u25B2' : '\u25BC'}</span>
                </button>
              </div>
              <div class="similarity-grid">
                ${this.renderSimilarityValue(similarity_breakdown.jaro_winkler, 'Jaro-Winkler')}
                ${this.renderSimilarityValue(similarity_breakdown.levenshtein, 'Levenshtein')}
                ${this.renderSimilarityValue(similarity_breakdown.trigram, 'Trigram')}
                ${this.renderSimilarityValue(similarity_breakdown.embedding_cosine, 'Embedding')}
                ${this.renderSimilarityValue(similarity_breakdown.graph_neighborhood, 'Graph')}
                ${this.renderSimilarityValue(similarity_breakdown.type_match, 'Type Match')}
                ${this.renderSimilarityValue(similarity_breakdown.soundex_match, 'Soundex')}
                ${this.renderSimilarityValue(similarity_breakdown.same_page, 'Same Page')}
              </div>
            </div>
          </div>

          ${this.expanded
            ? html`
                <div class="expanded-content">
                  <km-entity-comparison
                    .entityA=${entity_a}
                    .entityB=${entity_b}
                    .breakdown=${similarity_breakdown}
                    .selectedCanonical=${this.selectedCanonical}
                    selectable
                    show-comparison
                    @select-canonical=${this.handleSelectCanonical}
                  ></km-entity-comparison>
                </div>
              `
            : null}

          <div class="card-footer">
            <span class="footer-info">Computed: ${this.formatDate(computed_at)}</span>
            <div class="action-buttons">
              <button
                class="action-btn defer"
                @click=${this.handleDefer}
                ?disabled=${this.disabled || this.loading}
              >
                Defer
              </button>
              <button
                class="action-btn reject"
                @click=${this.handleReject}
                ?disabled=${this.disabled || this.loading}
              >
                Reject
              </button>
              <button
                class="action-btn merge"
                @click=${this.handleMerge}
                ?disabled=${this.disabled || this.loading}
              >
                Merge
              </button>
            </div>
          </div>
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'km-merge-candidate-card': KmMergeCandidateCard
  }
}
