import { describe, it, expect, beforeEach } from 'vitest'
import { fixture, html } from '@open-wc/testing'
import './km-confidence-score'
import type { KmConfidenceScore } from './km-confidence-score'
import type { SimilarityBreakdown } from '../../api/types'

describe('KmConfidenceScore Component', () => {
  beforeEach(() => {
    // Clean up any existing elements
  })

  it('should render the component', async () => {
    const el = await fixture<KmConfidenceScore>(
      html`<km-confidence-score .score=${0.75}></km-confidence-score>`
    )

    expect(el).toBeDefined()
    expect(el.shadowRoot).toBeDefined()
  })

  it('should display score as percentage by default', async () => {
    const el = await fixture<KmConfidenceScore>(
      html`<km-confidence-score .score=${0.75}></km-confidence-score>`
    )

    const valueEl = el.shadowRoot?.querySelector('.confidence-value')
    expect(valueEl?.textContent?.trim()).toBe('75%')
  })

  it('should display score as decimal when format is decimal', async () => {
    const el = await fixture<KmConfidenceScore>(
      html`<km-confidence-score .score=${0.75} format="decimal"></km-confidence-score>`
    )

    const valueEl = el.shadowRoot?.querySelector('.confidence-value')
    expect(valueEl?.textContent?.trim()).toBe('0.75')
  })

  it('should apply high confidence styling for scores >= 0.7', async () => {
    const el = await fixture<KmConfidenceScore>(
      html`<km-confidence-score .score=${0.85}></km-confidence-score>`
    )

    const container = el.shadowRoot?.querySelector('.confidence-container')
    expect(container?.classList.contains('confidence-high')).toBe(true)
  })

  it('should apply medium confidence styling for scores between 0.5 and 0.7', async () => {
    const el = await fixture<KmConfidenceScore>(
      html`<km-confidence-score .score=${0.55}></km-confidence-score>`
    )

    const container = el.shadowRoot?.querySelector('.confidence-container')
    expect(container?.classList.contains('confidence-medium')).toBe(true)
  })

  it('should apply low confidence styling for scores < 0.5', async () => {
    const el = await fixture<KmConfidenceScore>(
      html`<km-confidence-score .score=${0.3}></km-confidence-score>`
    )

    const container = el.shadowRoot?.querySelector('.confidence-container')
    expect(container?.classList.contains('confidence-low')).toBe(true)
  })

  it('should show progress bar when showBar is true', async () => {
    const el = await fixture<KmConfidenceScore>(
      html`<km-confidence-score .score=${0.75} show-bar></km-confidence-score>`
    )

    const bar = el.shadowRoot?.querySelector('.confidence-bar')
    expect(bar).toBeDefined()
  })

  it('should set correct fill width on progress bar', async () => {
    const el = await fixture<KmConfidenceScore>(
      html`<km-confidence-score .score=${0.65} show-bar></km-confidence-score>`
    )

    const fill = el.shadowRoot?.querySelector('.confidence-fill') as HTMLElement
    expect(fill?.style.width).toBe('65%')
  })

  it('should render tooltip when breakdown is provided', async () => {
    const breakdown: SimilarityBreakdown = {
      jaro_winkler: 0.85,
      levenshtein: 0.9,
      trigram: 0.75,
      soundex_match: true,
      metaphone_match: false,
      embedding_cosine: null,
      graph_neighborhood: null,
      type_match: true,
      same_page: false,
    }

    const el = await fixture<KmConfidenceScore>(
      html`<km-confidence-score
        .score=${0.75}
        .breakdown=${breakdown}
        show-tooltip
      ></km-confidence-score>`
    )

    const tooltip = el.shadowRoot?.querySelector('.tooltip')
    expect(tooltip).toBeDefined()
  })

  it('should have proper ARIA attributes', async () => {
    const el = await fixture<KmConfidenceScore>(
      html`<km-confidence-score .score=${0.75}></km-confidence-score>`
    )

    const container = el.shadowRoot?.querySelector('.confidence-container')
    expect(container?.getAttribute('role')).toBe('meter')
    expect(container?.getAttribute('aria-valuenow')).toBe('0.75')
    expect(container?.getAttribute('aria-valuemin')).toBe('0')
    expect(container?.getAttribute('aria-valuemax')).toBe('1')
  })
})
