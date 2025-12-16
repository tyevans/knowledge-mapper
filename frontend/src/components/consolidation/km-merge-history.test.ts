import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fixture, html } from '@open-wc/testing'
import './km-merge-history'
import type { KmMergeHistory } from './km-merge-history'
import { apiClient } from '../../api/client'
import type { MergeHistoryItem, MergeHistoryListResponse } from '../../api/types'

// Mock the API client
vi.mock('../../api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

describe('KmMergeHistory Component', () => {
  const mockItems: MergeHistoryItem[] = [
    {
      id: 'history-1',
      event_id: 'event-1',
      event_type: 'entities_merged',
      canonical_entity: {
        id: 'entity-canonical',
        name: 'John Smith',
        normalized_name: 'john smith',
        entity_type: 'person',
        description: null,
        is_canonical: true,
      },
      affected_entity_ids: ['entity-a', 'entity-b'],
      merge_reason: 'user_approved',
      similarity_scores: { jaro_winkler: 0.9 },
      performed_by_name: 'Admin User',
      performed_at: '2024-01-15T10:00:00Z',
      undone: false,
      undone_at: null,
      undone_by_name: null,
      undo_reason: null,
      can_undo: true,
    },
    {
      id: 'history-2',
      event_id: 'event-2',
      event_type: 'merge_undone',
      canonical_entity: null,
      affected_entity_ids: ['entity-c', 'entity-d'],
      merge_reason: null,
      similarity_scores: null,
      performed_by_name: 'Admin User',
      performed_at: '2024-01-14T09:00:00Z',
      undone: true,
      undone_at: '2024-01-14T10:00:00Z',
      undone_by_name: 'Admin User',
      undo_reason: 'Merged by mistake',
      can_undo: false,
    },
  ]

  const mockResponse: MergeHistoryListResponse = {
    items: mockItems,
    total: 2,
    page: 1,
    page_size: 20,
    pages: 1,
    has_next: false,
    has_prev: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(apiClient.get).mockResolvedValue({
      success: true,
      data: mockResponse,
    })
  })

  it('should render the component', async () => {
    const el = await fixture<KmMergeHistory>(
      html`<km-merge-history></km-merge-history>`
    )

    expect(el).toBeDefined()
    expect(el.shadowRoot).toBeDefined()
  })

  it('should load history data on connect', async () => {
    await fixture<KmMergeHistory>(
      html`<km-merge-history></km-merge-history>`
    )

    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(apiClient.get).toHaveBeenCalledWith(expect.stringContaining('/history'))
  })

  it('should display timeline items', async () => {
    const el = await fixture<KmMergeHistory>(
      html`<km-merge-history></km-merge-history>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const items = el.shadowRoot?.querySelectorAll('.timeline-item')
    expect(items?.length).toBe(2)
  })

  it('should display correct event type badges', async () => {
    const el = await fixture<KmMergeHistory>(
      html`<km-merge-history></km-merge-history>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const badges = el.shadowRoot?.querySelectorAll('.event-type-badge')
    expect(badges?.[0]?.textContent?.trim()).toBe('Entities Merged')
    expect(badges?.[1]?.textContent?.trim()).toBe('Merge Undone')
  })

  it('should show undo button for undoable items', async () => {
    const el = await fixture<KmMergeHistory>(
      html`<km-merge-history></km-merge-history>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const undoButtons = el.shadowRoot?.querySelectorAll('.undo-btn')
    // Only the first item can be undone
    expect(undoButtons?.length).toBe(1)
  })

  it('should display canonical entity when present', async () => {
    const el = await fixture<KmMergeHistory>(
      html`<km-merge-history></km-merge-history>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const entityName = el.shadowRoot?.querySelector('.entity-name')
    expect(entityName?.textContent?.trim()).toBe('John Smith')
  })

  it('should display affected entity count', async () => {
    const el = await fixture<KmMergeHistory>(
      html`<km-merge-history></km-merge-history>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const affectedEntities = el.shadowRoot?.querySelector('.affected-entities')
    expect(affectedEntities?.textContent).toContain('(2)')
  })

  it('should have event type filter dropdown', async () => {
    const el = await fixture<KmMergeHistory>(
      html`<km-merge-history></km-merge-history>`
    )

    await el.updateComplete

    const filterSelect = el.shadowRoot?.querySelector('.filter-select')
    expect(filterSelect).toBeDefined()
  })

  it('should show empty state when no items', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      success: true,
      data: { ...mockResponse, items: [], total: 0 },
    })

    const el = await fixture<KmMergeHistory>(
      html`<km-merge-history></km-merge-history>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const emptyState = el.shadowRoot?.querySelector('km-empty-state')
    expect(emptyState).toBeDefined()
  })

  it('should show error state on API failure', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      success: false,
      error: { message: 'Failed to load', status: 500, timestamp: '' },
    })

    const el = await fixture<KmMergeHistory>(
      html`<km-merge-history></km-merge-history>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const error = el.shadowRoot?.querySelector('.error')
    expect(error).toBeDefined()
  })

  it('should open undo modal when undo button is clicked', async () => {
    const el = await fixture<KmMergeHistory>(
      html`<km-merge-history></km-merge-history>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const undoBtn = el.shadowRoot?.querySelector('.undo-btn') as HTMLButtonElement
    undoBtn?.click()
    await el.updateComplete

    const modal = el.shadowRoot?.querySelector('.modal-overlay')
    expect(modal).toBeDefined()
  })

  it('should submit undo request when confirmed', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      success: true,
      data: { success: true, original_merge_event_id: 'event-1' },
    })

    const el = await fixture<KmMergeHistory>(
      html`<km-merge-history></km-merge-history>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    // Open modal
    const undoBtn = el.shadowRoot?.querySelector('.undo-btn') as HTMLButtonElement
    undoBtn?.click()
    await el.updateComplete

    // Fill reason
    const textarea = el.shadowRoot?.querySelector('.modal-textarea') as HTMLTextAreaElement
    textarea.value = 'Merged by mistake'
    textarea.dispatchEvent(new Event('input'))
    await el.updateComplete

    // Confirm
    const confirmBtn = el.shadowRoot?.querySelector('.modal-btn.confirm') as HTMLButtonElement
    confirmBtn?.click()

    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(apiClient.post).toHaveBeenCalledWith(
      expect.stringContaining('/undo/event-1'),
      expect.objectContaining({ reason: 'Merged by mistake' })
    )
  })

  it('should fire view-entity event when entity name is clicked', async () => {
    const viewHandler = vi.fn()

    const el = await fixture<KmMergeHistory>(
      html`<km-merge-history @view-entity=${viewHandler}></km-merge-history>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const entityName = el.shadowRoot?.querySelector('.entity-name') as HTMLElement
    entityName?.click()

    expect(viewHandler).toHaveBeenCalled()
    expect(viewHandler.mock.calls[0][0].detail.entityId).toBe('entity-canonical')
  })

  it('should filter by entity-id when provided', async () => {
    await fixture<KmMergeHistory>(
      html`<km-merge-history entity-id="entity-123"></km-merge-history>`
    )

    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(apiClient.get).toHaveBeenCalledWith(
      expect.stringContaining('entity_id=entity-123')
    )
  })

  it('should display undone badge for undone merges', async () => {
    const el = await fixture<KmMergeHistory>(
      html`<km-merge-history></km-merge-history>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const undoneBadge = el.shadowRoot?.querySelector('.undone-badge')
    expect(undoneBadge).toBeDefined()
  })
})
