import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fixture, html } from '@open-wc/testing'
import './km-merge-candidate-card'
import type { KmMergeCandidateCard } from './km-merge-candidate-card'
import type { MergeCandidate, EntitySummary, SimilarityBreakdown } from '../../api/types'

describe('KmMergeCandidateCard Component', () => {
  const entityA: EntitySummary = {
    id: 'entity-a-123',
    name: 'John Smith',
    normalized_name: 'john smith',
    entity_type: 'person',
    description: 'A software engineer',
    is_canonical: true,
  }

  const entityB: EntitySummary = {
    id: 'entity-b-456',
    name: 'John D. Smith',
    normalized_name: 'john d smith',
    entity_type: 'person',
    description: 'Senior software engineer',
    is_canonical: false,
  }

  const breakdown: SimilarityBreakdown = {
    jaro_winkler: 0.85,
    levenshtein: 0.9,
    trigram: 0.75,
    soundex_match: true,
    metaphone_match: true,
    embedding_cosine: 0.82,
    graph_neighborhood: 0.7,
    type_match: true,
    same_page: false,
  }

  const mockCandidate: MergeCandidate = {
    entity_a: entityA,
    entity_b: entityB,
    combined_score: 0.85,
    confidence: 0.85,
    decision: 'review',
    similarity_breakdown: breakdown,
    blocking_keys: ['name_soundex', 'type_person'],
    review_item_id: 'review-123',
    computed_at: '2024-01-15T10:30:00Z',
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render the component', async () => {
    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card .candidate=${mockCandidate}></km-merge-candidate-card>`
    )

    expect(el).toBeDefined()
    expect(el.shadowRoot).toBeDefined()
  })

  it('should display entity names', async () => {
    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card .candidate=${mockCandidate}></km-merge-candidate-card>`
    )

    const names = el.shadowRoot?.querySelectorAll('.entity-name')
    expect(names?.length).toBe(2)
    expect(names?.[0]?.textContent?.trim()).toBe('John Smith')
    expect(names?.[1]?.textContent?.trim()).toBe('John D. Smith')
  })

  it('should display decision badge', async () => {
    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card .candidate=${mockCandidate}></km-merge-candidate-card>`
    )

    const badge = el.shadowRoot?.querySelector('.decision-badge')
    expect(badge).toBeDefined()
    expect(badge?.textContent?.trim()).toBe('Needs Review')
    expect(badge?.classList.contains('review')).toBe(true)
  })

  it('should display blocking keys', async () => {
    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card .candidate=${mockCandidate}></km-merge-candidate-card>`
    )

    const keys = el.shadowRoot?.querySelectorAll('.blocking-key')
    expect(keys?.length).toBe(2)
    expect(keys?.[0]?.textContent).toBe('name_soundex')
    expect(keys?.[1]?.textContent).toBe('type_person')
  })

  it('should display similarity scores', async () => {
    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card .candidate=${mockCandidate}></km-merge-candidate-card>`
    )

    const scores = el.shadowRoot?.querySelectorAll('.similarity-item')
    expect(scores?.length).toBeGreaterThan(0)
  })

  it('should have merge, reject, and defer buttons', async () => {
    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card .candidate=${mockCandidate}></km-merge-candidate-card>`
    )

    const mergeBtn = el.shadowRoot?.querySelector('.action-btn.merge')
    const rejectBtn = el.shadowRoot?.querySelector('.action-btn.reject')
    const deferBtn = el.shadowRoot?.querySelector('.action-btn.defer')

    expect(mergeBtn).toBeDefined()
    expect(rejectBtn).toBeDefined()
    expect(deferBtn).toBeDefined()
  })

  it('should fire merge event when merge button is clicked', async () => {
    const mergeHandler = vi.fn()

    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card
        .candidate=${mockCandidate}
        @merge=${mergeHandler}
      ></km-merge-candidate-card>`
    )

    const mergeBtn = el.shadowRoot?.querySelector('.action-btn.merge') as HTMLButtonElement
    mergeBtn?.click()

    expect(mergeHandler).toHaveBeenCalled()
    expect(mergeHandler.mock.calls[0][0].detail.canonical_entity_id).toBe(entityA.id)
  })

  it('should fire reject event when reject button is clicked', async () => {
    const rejectHandler = vi.fn()

    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card
        .candidate=${mockCandidate}
        @reject=${rejectHandler}
      ></km-merge-candidate-card>`
    )

    const rejectBtn = el.shadowRoot?.querySelector('.action-btn.reject') as HTMLButtonElement
    rejectBtn?.click()

    expect(rejectHandler).toHaveBeenCalled()
  })

  it('should fire defer event when defer button is clicked', async () => {
    const deferHandler = vi.fn()

    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card
        .candidate=${mockCandidate}
        @defer=${deferHandler}
      ></km-merge-candidate-card>`
    )

    const deferBtn = el.shadowRoot?.querySelector('.action-btn.defer') as HTMLButtonElement
    deferBtn?.click()

    expect(deferHandler).toHaveBeenCalled()
  })

  it('should disable buttons when disabled prop is true', async () => {
    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card
        .candidate=${mockCandidate}
        disabled
      ></km-merge-candidate-card>`
    )

    const mergeBtn = el.shadowRoot?.querySelector('.action-btn.merge') as HTMLButtonElement
    expect(mergeBtn?.disabled).toBe(true)
  })

  it('should show loading overlay when loading', async () => {
    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card
        .candidate=${mockCandidate}
        loading
      ></km-merge-candidate-card>`
    )

    const overlay = el.shadowRoot?.querySelector('.loading-overlay')
    expect(overlay).toBeDefined()
  })

  it('should toggle expanded view', async () => {
    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card .candidate=${mockCandidate}></km-merge-candidate-card>`
    )

    // Initially not expanded
    let expandedContent = el.shadowRoot?.querySelector('.expanded-content')
    expect(expandedContent).toBeNull()

    // Click to expand
    const expandToggle = el.shadowRoot?.querySelector('.expand-toggle') as HTMLButtonElement
    expandToggle?.click()
    await el.updateComplete

    expandedContent = el.shadowRoot?.querySelector('.expanded-content')
    expect(expandedContent).toBeDefined()
  })

  it('should fire view-entity event when entity name is clicked', async () => {
    const viewHandler = vi.fn()

    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card
        .candidate=${mockCandidate}
        @view-entity=${viewHandler}
      ></km-merge-candidate-card>`
    )

    const entityName = el.shadowRoot?.querySelector('.entity-name') as HTMLElement
    entityName?.click()

    expect(viewHandler).toHaveBeenCalled()
    expect(viewHandler.mock.calls[0][0].detail.entityId).toBe(entityA.id)
  })

  it('should show empty state when candidate is null', async () => {
    const el = await fixture<KmMergeCandidateCard>(
      html`<km-merge-candidate-card></km-merge-candidate-card>`
    )

    const content = el.shadowRoot?.querySelector('.card')?.textContent
    expect(content).toContain('No candidate data')
  })
})
