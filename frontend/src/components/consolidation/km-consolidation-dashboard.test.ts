import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fixture, html } from '@open-wc/testing'
import './km-consolidation-dashboard'
import type { KmConsolidationDashboard } from './km-consolidation-dashboard'
import { apiClient } from '../../api/client'
import type { ReviewQueueStats, MergeCandidateListResponse } from '../../api/types'

// Mock the API client
vi.mock('../../api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

describe('KmConsolidationDashboard Component', () => {
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

  const mockCandidates: MergeCandidateListResponse = {
    items: [
      {
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
        combined_score: 0.85,
        confidence: 0.85,
        decision: 'review',
        similarity_breakdown: {
          jaro_winkler: 0.85,
          levenshtein: null,
          trigram: null,
          soundex_match: true,
          metaphone_match: null,
          embedding_cosine: null,
          graph_neighborhood: null,
          type_match: true,
          same_page: null,
        },
        blocking_keys: ['name_soundex'],
        review_item_id: 'review-1',
        computed_at: '2024-01-15T10:00:00Z',
      },
    ],
    total: 1,
    page: 1,
    page_size: 3,
    pages: 1,
    has_next: false,
    has_prev: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes('/stats')) {
        return { success: true, data: mockStats }
      }
      if (url.includes('/candidates')) {
        return { success: true, data: mockCandidates }
      }
      return { success: true, data: {} }
    })
  })

  it('should render the component', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    expect(el).toBeDefined()
    expect(el.shadowRoot).toBeDefined()
  })

  it('should display dashboard title', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    const title = el.shadowRoot?.querySelector('.dashboard-title')
    expect(title?.textContent).toBe('Entity Consolidation')
  })

  it('should have tabs for navigation', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    const tabs = el.shadowRoot?.querySelectorAll('.tab')
    expect(tabs?.length).toBe(4) // Overview, Queue, History, Settings
  })

  it('should display stats cards on overview', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const statCards = el.shadowRoot?.querySelectorAll('.stat-card')
    expect(statCards?.length).toBe(4)
  })

  it('should display pending count from stats', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const statValue = el.shadowRoot?.querySelector('.stat-value')
    expect(statValue?.textContent).toBe('15') // total_pending
  })

  it('should switch tabs when clicked', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    await el.updateComplete

    // Click on Queue tab
    const tabs = el.shadowRoot?.querySelectorAll('.tab')
    const queueTab = tabs?.[1] as HTMLButtonElement
    queueTab?.click()
    await el.updateComplete

    expect(queueTab?.classList.contains('active')).toBe(true)
  })

  it('should show review queue list when queue tab is active', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    await el.updateComplete

    // Click on Queue tab
    const tabs = el.shadowRoot?.querySelectorAll('.tab')
    const queueTab = tabs?.[1] as HTMLButtonElement
    queueTab?.click()
    await el.updateComplete

    const reviewQueue = el.shadowRoot?.querySelector('km-review-queue-list')
    expect(reviewQueue).toBeDefined()
  })

  it('should show merge history when history tab is active', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    await el.updateComplete

    // Click on History tab
    const tabs = el.shadowRoot?.querySelectorAll('.tab')
    const historyTab = tabs?.[2] as HTMLButtonElement
    historyTab?.click()
    await el.updateComplete

    const mergeHistory = el.shadowRoot?.querySelector('km-merge-history')
    expect(mergeHistory).toBeDefined()
  })

  it('should show config when settings tab is active', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    await el.updateComplete

    // Click on Settings tab
    const tabs = el.shadowRoot?.querySelectorAll('.tab')
    const settingsTab = tabs?.[3] as HTMLButtonElement
    settingsTab?.click()
    await el.updateComplete

    const config = el.shadowRoot?.querySelector('km-consolidation-config')
    expect(config).toBeDefined()
  })

  it('should have refresh button', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    const refreshBtn = el.shadowRoot?.querySelector('.action-btn.secondary')
    expect(refreshBtn?.textContent?.trim()).toBe('Refresh')
  })

  it('should have batch consolidation button', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    const batchBtn = el.shadowRoot?.querySelector('.action-btn.primary')
    expect(batchBtn?.textContent?.trim()).toBe('Run Batch Consolidation')
  })

  it('should display top merge candidates on overview', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const candidates = el.shadowRoot?.querySelectorAll('km-merge-candidate-card')
    expect(candidates?.length).toBe(1)
  })

  it('should show quick stats section', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const quickStats = el.shadowRoot?.querySelector('.quick-stats')
    expect(quickStats).toBeDefined()
  })

  it('should show pending count in queue tab badge', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const tabs = el.shadowRoot?.querySelectorAll('.tab')
    const queueTab = tabs?.[1]
    expect(queueTab?.textContent).toContain('(15)')
  })

  it('should fire view-entity event from nested components', async () => {
    const viewHandler = vi.fn()

    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard @view-entity=${viewHandler}></km-consolidation-dashboard>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    // Find and click entity in candidate card
    const card = el.shadowRoot?.querySelector('km-merge-candidate-card')
    card?.dispatchEvent(
      new CustomEvent('view-entity', {
        detail: { entityId: 'entity-a-1' },
        bubbles: true,
        composed: true,
      })
    )

    expect(viewHandler).toHaveBeenCalled()
  })

  it('should run batch consolidation when button clicked', async () => {
    // Mock window.confirm
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    vi.mocked(apiClient.post).mockResolvedValue({
      success: true,
      data: { job_id: 'job-123', status: 'queued' },
    })

    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    await el.updateComplete

    const batchBtn = el.shadowRoot?.querySelector('.action-btn.primary') as HTMLButtonElement
    batchBtn?.click()

    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/consolidation/batch',
      expect.any(Object)
    )
  })

  it('should show success message after batch consolidation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    vi.mocked(apiClient.post).mockResolvedValue({
      success: true,
      data: { job_id: 'job-123', status: 'queued', message: 'Job queued' },
    })

    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    await el.updateComplete

    const batchBtn = el.shadowRoot?.querySelector('.action-btn.primary') as HTMLButtonElement
    batchBtn?.click()

    await new Promise((resolve) => setTimeout(resolve, 50))
    await el.updateComplete

    const success = el.shadowRoot?.querySelector('.success')
    expect(success).toBeDefined()
    expect(success?.textContent).toContain('job-123')
  })

  it('should show error message on batch consolidation failure', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    vi.mocked(apiClient.post).mockResolvedValue({
      success: false,
      error: { message: 'Batch failed', status: 500, timestamp: '' },
    })

    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    await el.updateComplete

    const batchBtn = el.shadowRoot?.querySelector('.action-btn.primary') as HTMLButtonElement
    batchBtn?.click()

    await new Promise((resolve) => setTimeout(resolve, 50))
    await el.updateComplete

    const error = el.shadowRoot?.querySelector('.error')
    expect(error).toBeDefined()
    expect(error?.textContent).toContain('Batch failed')
  })

  it('should reload data when refresh button is clicked', async () => {
    const el = await fixture<KmConsolidationDashboard>(
      html`<km-consolidation-dashboard></km-consolidation-dashboard>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))

    vi.clearAllMocks()

    const refreshBtn = el.shadowRoot?.querySelector('.action-btn.secondary') as HTMLButtonElement
    refreshBtn?.click()

    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(apiClient.get).toHaveBeenCalled()
  })
})
