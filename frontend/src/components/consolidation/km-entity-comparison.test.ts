import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fixture, html } from '@open-wc/testing'
import './km-entity-comparison'
import type { KmEntityComparison } from './km-entity-comparison'
import type { EntitySummary } from '../../api/types'

describe('KmEntityComparison Component', () => {
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

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render the component', async () => {
    const el = await fixture<KmEntityComparison>(
      html`<km-entity-comparison
        .entityA=${entityA}
        .entityB=${entityB}
      ></km-entity-comparison>`
    )

    expect(el).toBeDefined()
    expect(el.shadowRoot).toBeDefined()
  })

  it('should display both entity names', async () => {
    const el = await fixture<KmEntityComparison>(
      html`<km-entity-comparison
        .entityA=${entityA}
        .entityB=${entityB}
      ></km-entity-comparison>`
    )

    const names = el.shadowRoot?.querySelectorAll('.entity-name')
    expect(names?.length).toBe(2)
    expect(names?.[0]?.textContent?.trim()).toBe('John Smith')
    expect(names?.[1]?.textContent?.trim()).toBe('John D. Smith')
  })

  it('should show entity types', async () => {
    const el = await fixture<KmEntityComparison>(
      html`<km-entity-comparison
        .entityA=${entityA}
        .entityB=${entityB}
      ></km-entity-comparison>`
    )

    const badges = el.shadowRoot?.querySelectorAll('.entity-type-badge')
    // At least 2 type badges (one for each entity, possibly canonical badge too)
    expect(badges?.length).toBeGreaterThanOrEqual(2)
  })

  it('should show empty state when entities are missing', async () => {
    const el = await fixture<KmEntityComparison>(
      html`<km-entity-comparison></km-entity-comparison>`
    )

    const container = el.shadowRoot?.querySelector('.comparison-container')
    expect(container?.textContent).toContain('No entities to compare')
  })

  it('should show canonical badge for canonical entities', async () => {
    const el = await fixture<KmEntityComparison>(
      html`<km-entity-comparison
        .entityA=${entityA}
        .entityB=${entityB}
      ></km-entity-comparison>`
    )

    const canonicalBadge = el.shadowRoot?.querySelector('.canonical-badge')
    expect(canonicalBadge).toBeDefined()
    expect(canonicalBadge?.textContent?.trim()).toBe('Canonical')
  })

  it('should enable selection when selectable is true', async () => {
    const el = await fixture<KmEntityComparison>(
      html`<km-entity-comparison
        .entityA=${entityA}
        .entityB=${entityB}
        selectable
      ></km-entity-comparison>`
    )

    const selectButtons = el.shadowRoot?.querySelectorAll('.select-btn')
    expect(selectButtons?.length).toBe(2)
  })

  it('should fire select-canonical event when entity is selected', async () => {
    const selectHandler = vi.fn()

    const el = await fixture<KmEntityComparison>(
      html`<km-entity-comparison
        .entityA=${entityA}
        .entityB=${entityB}
        selectable
        @select-canonical=${selectHandler}
      ></km-entity-comparison>`
    )

    const selectButton = el.shadowRoot?.querySelector('.select-btn') as HTMLButtonElement
    selectButton?.click()

    expect(selectHandler).toHaveBeenCalled()
    expect(selectHandler.mock.calls[0][0].detail.entityId).toBe(entityA.id)
  })

  it('should highlight matching types', async () => {
    const el = await fixture<KmEntityComparison>(
      html`<km-entity-comparison
        .entityA=${entityA}
        .entityB=${entityB}
      ></km-entity-comparison>`
    )

    // Both have type 'person', so should show match class
    const typeValues = el.shadowRoot?.querySelectorAll('.property-row')
    const typeRow = Array.from(typeValues || []).find(
      (row) => row.querySelector('.property-label')?.textContent?.includes('Type')
    )
    const typeValue = typeRow?.querySelector('.property-value')
    expect(typeValue?.classList.contains('match')).toBe(true)
  })

  it('should show comparison column when show-comparison is true', async () => {
    const el = await fixture<KmEntityComparison>(
      html`<km-entity-comparison
        .entityA=${entityA}
        .entityB=${entityB}
        show-comparison
      ></km-entity-comparison>`
    )

    const comparisonColumn = el.shadowRoot?.querySelector('.comparison-column')
    expect(comparisonColumn).toBeDefined()
  })

  it('should apply selected class to selected entity panel', async () => {
    const el = await fixture<KmEntityComparison>(
      html`<km-entity-comparison
        .entityA=${entityA}
        .entityB=${entityB}
        .selectedCanonical=${entityA.id}
        selectable
      ></km-entity-comparison>`
    )

    const panels = el.shadowRoot?.querySelectorAll('.entity-panel')
    expect(panels?.[0]?.classList.contains('selected')).toBe(true)
    expect(panels?.[1]?.classList.contains('selected')).toBe(false)
  })
})
