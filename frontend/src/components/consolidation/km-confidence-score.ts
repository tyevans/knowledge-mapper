import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'
import type { SimilarityBreakdown } from '../../api/types'

/**
 * Confidence score display component
 *
 * Visual confidence score display (0-1 scale) with:
 * - Color coding (green high, yellow medium, red low)
 * - Progress bar visualization
 * - Tooltip with score breakdown
 *
 * @element km-confidence-score
 */
@customElement('km-confidence-score')
export class KmConfidenceScore extends LitElement {
  static styles = css`
    :host {
      display: inline-block;
    }

    .confidence-container {
      position: relative;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
    }

    .confidence-bar {
      width: 60px;
      height: 8px;
      background: #e5e7eb;
      border-radius: 4px;
      overflow: hidden;
    }

    .confidence-fill {
      height: 100%;
      border-radius: 4px;
      transition: width 0.3s ease, background-color 0.3s ease;
    }

    .confidence-value {
      font-size: 0.875rem;
      font-weight: 600;
      min-width: 3.5rem;
      text-align: right;
    }

    /* Color variants based on confidence level */
    .confidence-high .confidence-fill {
      background: linear-gradient(90deg, #10b981, #059669);
    }
    .confidence-high .confidence-value {
      color: #059669;
    }

    .confidence-medium .confidence-fill {
      background: linear-gradient(90deg, #f59e0b, #d97706);
    }
    .confidence-medium .confidence-value {
      color: #d97706;
    }

    .confidence-low .confidence-fill {
      background: linear-gradient(90deg, #ef4444, #dc2626);
    }
    .confidence-low .confidence-value {
      color: #dc2626;
    }

    /* Tooltip styles */
    .tooltip-trigger {
      cursor: help;
      position: relative;
    }

    .tooltip {
      position: absolute;
      bottom: calc(100% + 8px);
      left: 50%;
      transform: translateX(-50%);
      background: #1f2937;
      color: white;
      padding: 0.75rem;
      border-radius: 0.5rem;
      font-size: 0.75rem;
      white-space: nowrap;
      z-index: 1000;
      opacity: 0;
      visibility: hidden;
      transition: opacity 0.2s, visibility 0.2s;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }

    .tooltip::after {
      content: '';
      position: absolute;
      top: 100%;
      left: 50%;
      transform: translateX(-50%);
      border: 6px solid transparent;
      border-top-color: #1f2937;
    }

    .tooltip-trigger:hover .tooltip,
    .tooltip-trigger:focus .tooltip {
      opacity: 1;
      visibility: visible;
    }

    .tooltip-title {
      font-weight: 600;
      margin-bottom: 0.5rem;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid #374151;
    }

    .tooltip-row {
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      padding: 0.25rem 0;
    }

    .tooltip-label {
      color: #9ca3af;
    }

    .tooltip-value {
      font-weight: 500;
    }

    .tooltip-value.positive {
      color: #10b981;
    }

    .tooltip-value.negative {
      color: #ef4444;
    }

    /* Size variants */
    :host([size='small']) .confidence-bar {
      width: 40px;
      height: 6px;
    }
    :host([size='small']) .confidence-value {
      font-size: 0.75rem;
      min-width: 2.5rem;
    }

    :host([size='large']) .confidence-bar {
      width: 100px;
      height: 12px;
    }
    :host([size='large']) .confidence-value {
      font-size: 1rem;
      min-width: 4rem;
    }

    /* Badge variant */
    :host([variant='badge']) .confidence-container {
      padding: 0.25rem 0.5rem;
      border-radius: 9999px;
      gap: 0.25rem;
    }
    :host([variant='badge']) .confidence-bar {
      display: none;
    }
    :host([variant='badge'].confidence-high) .confidence-container {
      background: #d1fae5;
    }
    :host([variant='badge'].confidence-medium) .confidence-container {
      background: #fef3c7;
    }
    :host([variant='badge'].confidence-low) .confidence-container {
      background: #fee2e2;
    }
  `

  /** The confidence score value (0-1) */
  @property({ type: Number })
  score = 0

  /** Optional similarity breakdown for tooltip */
  @property({ type: Object })
  breakdown: SimilarityBreakdown | null = null

  /** Whether to show the progress bar */
  @property({ type: Boolean, attribute: 'show-bar' })
  showBar = true

  /** Whether to show the tooltip on hover */
  @property({ type: Boolean, attribute: 'show-tooltip' })
  showTooltip = true

  /** Display format: 'percent' or 'decimal' */
  @property({ type: String })
  format: 'percent' | 'decimal' = 'percent'

  /** Size variant */
  @property({ type: String, reflect: true })
  size: 'small' | 'medium' | 'large' = 'medium'

  /** Display variant */
  @property({ type: String, reflect: true })
  variant: 'default' | 'badge' = 'default'

  private getConfidenceLevel(): 'high' | 'medium' | 'low' {
    if (this.score >= 0.7) return 'high'
    if (this.score >= 0.5) return 'medium'
    return 'low'
  }

  private getFormattedScore(): string {
    if (this.format === 'percent') {
      return `${Math.round(this.score * 100)}%`
    }
    return this.score.toFixed(2)
  }

  private renderTooltip() {
    if (!this.showTooltip || !this.breakdown) return null

    const scores = [
      { label: 'Jaro-Winkler', value: this.breakdown.jaro_winkler },
      { label: 'Levenshtein', value: this.breakdown.levenshtein },
      { label: 'Trigram', value: this.breakdown.trigram },
      { label: 'Soundex Match', value: this.breakdown.soundex_match },
      { label: 'Metaphone Match', value: this.breakdown.metaphone_match },
      { label: 'Embedding Cosine', value: this.breakdown.embedding_cosine },
      { label: 'Graph Neighborhood', value: this.breakdown.graph_neighborhood },
      { label: 'Type Match', value: this.breakdown.type_match },
      { label: 'Same Page', value: this.breakdown.same_page },
    ].filter((s) => s.value !== null && s.value !== undefined)

    if (scores.length === 0) return null

    return html`
      <div class="tooltip" role="tooltip">
        <div class="tooltip-title">Similarity Breakdown</div>
        ${scores.map((s) => {
          const isBoolean = typeof s.value === 'boolean'
          const displayValue = isBoolean
            ? s.value
              ? 'Yes'
              : 'No'
            : `${Math.round((s.value as number) * 100)}%`
          const valueClass = isBoolean
            ? s.value
              ? 'positive'
              : 'negative'
            : (s.value as number) >= 0.7
              ? 'positive'
              : ''

          return html`
            <div class="tooltip-row">
              <span class="tooltip-label">${s.label}</span>
              <span class="tooltip-value ${valueClass}">${displayValue}</span>
            </div>
          `
        })}
      </div>
    `
  }

  render() {
    const level = this.getConfidenceLevel()
    const formattedScore = this.getFormattedScore()
    const fillWidth = `${Math.round(this.score * 100)}%`

    return html`
      <div
        class="confidence-container confidence-${level} ${this.showTooltip && this.breakdown ? 'tooltip-trigger' : ''}"
        role="meter"
        aria-valuenow=${this.score}
        aria-valuemin="0"
        aria-valuemax="1"
        aria-label="Confidence score: ${formattedScore}"
        tabindex=${this.showTooltip && this.breakdown ? '0' : '-1'}
      >
        ${this.showBar
          ? html`
              <div class="confidence-bar">
                <div class="confidence-fill" style="width: ${fillWidth}"></div>
              </div>
            `
          : null}
        <span class="confidence-value">${formattedScore}</span>
        ${this.renderTooltip()}
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'km-confidence-score': KmConfidenceScore
  }
}
