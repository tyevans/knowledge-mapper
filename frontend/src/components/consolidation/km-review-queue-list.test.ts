import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fixture, html } from '@open-wc/testing'
import './km-review-queue-list'
import type { KmReviewQueueList } from './km-review-queue-list'
import { apiClient } from '../../api/client'
import type { ReviewQueueItem, ReviewQueueListResponse, ReviewQueueStats } from '../../api/types'

// Mock the API client
vi.mock('../../api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

describe('KmReviewQueueList Component', () => {
  const mockStats: ReviewQueueStats = {
    total_pending: 15,
    total_approved: 50,
    total_rejected: 10,
    total_deferred: 5,
    total_expired: 2,
    avg_confidence: 0.72,
    oldest_pending_age_hours: 24,
    by_entity_type: { person: 10, organization: 5 },
  }

  const mockItems: ReviewQueueItem[] = [
    {
      id: 'item-1',
      entity_a: {
        id: 'entity-a-1',
        name: 'John Smith',
        normalized_name: 'john smith',
        entity_type: 'person',
        description: null,
        is_canonical: true,
      },
      entity_b: {
        id: 'entity-b-1',
        name: 'John D. Smith',
        normalized_name: 'john d smith',
        entity_type: 'person',
        description: null,
        is_canonical: false,
      },
      confidence: 0.85,
      review_priority: 0.9,
      similarity_scores: { jaro_winkler: 0.85 },
      status: 'pending',
      reviewed_by_name: null,
      reviewed_at: null,
      reviewer_notes: null,
      created_at: '2024-01-15T10:00:00Z',
    },
  ]

  const mockResponse: ReviewQueueListResponse = {
    items: mockItems,
    total: 1,
    page: 1,
    page_size: 20,
    pages: 1,
    has_next: false,
    has_prev: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()

    // Default mocks
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('/stats')) {
        return { success: true, data: mockStats }
      }
      return { success: true, data: mockResponse }
    })
  })

  it('should render the component', async () => {
    const el = await fixture<KmReviewQueueList>(
      html`<km-review-queue-list></km-review-queue-list>`
    )

    expect(el).toBeDefined()
    expect(el.shadowRoot).toBeDefined()
  })

  it('should load queue data on connect', async () => {
    await fixture<KmReviewQueueList>(
      html`<km-review-queue-list></km-review-queue-list>`
    )

    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(apiClient.get).toHaveBeenCalled()
  })

  it('should display queue items', async () => {
    const el = await fixture<KmReviewQueueList>(
      html`<km-review-queue-list></km-review-queue-list>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const items = el.shadowRoot?.querySelectorAll('.queue-item')
    expect(items?.length).toBe(1)
  })

  it('should display entity names in queue items', async () => {
    const el = await fixture<KmReviewQueueList>(
      html`<km-review-queue-list></km-review-queue-list>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const entityLinks = el.shadowRoot?.querySelectorAll('.entity-link')
    expect(entityLinks?.[0]?.textContent).toBe('John Smith')
    expect(entityLinks?.[1]?.textContent).toBe('John D. Smith')
  })

  it('should display stats in header', async () => {
    const el = await fixture<KmReviewQueueList>(
      html`<km-review-queue-list></km-review-queue-list>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const stats = el.shadowRoot?.querySelectorAll('.stat-item')
    expect(stats?.length).toBe(3)
  })

  it('should have action buttons for pending items', async () => {
    const el = await fixture<KmReviewQueueList>(
      html`<km-review-queue-list></km-review-queue-list>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const approveBtn = el.shadowRoot?.querySelector('.action-btn.approve')
    const rejectBtn = el.shadowRoot?.querySelector('.action-btn.reject')
    const deferBtn = el.shadowRoot?.querySelector('.action-btn.defer')

    expect(approveBtn).toBeDefined()
    expect(rejectBtn).toBeDefined()
    expect(deferBtn).toBeDefined()
  })

  it('should have status filter dropdown', async () => {
    const el = await fixture<KmReviewQueueList>(
      html`<km-review-queue-list></km-review-queue-list>`
    )

    await el.updateComplete

    const filterSelect = el.shadowRoot?.querySelector('.filter-select')
    expect(filterSelect).toBeDefined()
  })

  it('should have sort dropdown', async () => {
    const el = await fixture<KmReviewQueueList>(
      html`<km-review-queue-list></km-review-queue-list>`
    )

    await el.updateComplete

    const selects = el.shadowRoot?.querySelectorAll('.filter-select')
    // Should have status filter and sort select
    expect(selects?.length).toBe(2)
  })

  it('should show empty state when no items', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('/stats')) {
        return { success: true, data: mockStats }
      }
      return { success: true, data: { ...mockResponse, items: [], total: 0 } }
    })

    const el = await fixture<KmReviewQueueList>(
      html`<km-review-queue-list></km-review-queue-list>`
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

    const el = await fixture<KmReviewQueueList>(
      html`<km-review-queue-list></km-review-queue-list>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const error = el.shadowRoot?.querySelector('.error')
    expect(error).toBeDefined()
    expect(error?.textContent).toContain('Failed to load')
  })

  it('should submit approve decision when approve is clicked', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      success: true,
      data: { success: true, review_item_id: 'item-1', decision: 'approve', merge_executed: true },
    })

    const el = await fixture<KmReviewQueueList>(
      html`<km-review-queue-list></km-review-queue-list>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const approveBtn = el.shadowRoot?.querySelector('.action-btn.approve') as HTMLButtonElement
    approveBtn?.click()

    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(apiClient.post).toHaveBeenCalledWith(
      expect.stringContaining('/decide'),
      expect.objectContaining({ decision: 'approve' })
    )
  })

  it('should fire view-entity event when entity link is clicked', async () => {
    const viewHandler = vi.fn()

    const el = await fixture<KmReviewQueueList>(
      html`<km-review-queue-list @view-entity=${viewHandler}></km-review-queue-list>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const entityLink = el.shadowRoot?.querySelector('.entity-link') as HTMLElement
    entityLink?.click()

    expect(viewHandler).toHaveBeenCalled()
    expect(viewHandler.mock.calls[0][0].detail.entityId).toBe('entity-a-1')
  })

  it('should display priority badge for high priority items', async () => {
    const el = await fixture<KmReviewQueueList>(
      html`<km-review-queue-list></km-review-queue-list>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const priorityBadge = el.shadowRoot?.querySelector('.priority-badge')
    expect(priorityBadge).toBeDefined()
    expect(priorityBadge?.classList.contains('high')).toBe(true)
  })
})
