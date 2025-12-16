import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fixture, html } from '@open-wc/testing'
import './km-consolidation-config'
import type { KmConsolidationConfig } from './km-consolidation-config'
import { apiClient } from '../../api/client'
import type { ConsolidationConfig } from '../../api/types'

// Mock the API client
vi.mock('../../api/client', () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
  },
}))

describe('KmConsolidationConfig Component', () => {
  const mockConfig: ConsolidationConfig = {
    tenant_id: 'tenant-123',
    auto_merge_threshold: 0.9,
    review_threshold: 0.5,
    max_block_size: 1000,
    enable_embedding_similarity: true,
    enable_graph_similarity: true,
    enable_auto_consolidation: false,
    embedding_model: 'text-embedding-3-small',
    feature_weights: {
      jaro_winkler: 0.3,
      normalized_exact: 0.4,
      type_match: 0.2,
      same_page_bonus: 0.1,
      embedding_cosine: 0.5,
      graph_neighborhood: 0.3,
    },
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-10T00:00:00Z',
  }

  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(apiClient.get).mockResolvedValue({
      success: true,
      data: mockConfig,
    })
  })

  it('should render the component', async () => {
    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    expect(el).toBeDefined()
    expect(el.shadowRoot).toBeDefined()
  })

  it('should load config on connect', async () => {
    await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/consolidation/config')
  })

  it('should display threshold sliders', async () => {
    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const sliders = el.shadowRoot?.querySelectorAll('.slider')
    expect(sliders?.length).toBeGreaterThan(0)
  })

  it('should display feature toggles', async () => {
    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const toggles = el.shadowRoot?.querySelectorAll('.toggle input[type="checkbox"]')
    expect(toggles?.length).toBe(3) // embedding, graph, auto-consolidation
  })

  it('should display feature weights section', async () => {
    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const weightsGrid = el.shadowRoot?.querySelector('.weights-grid')
    expect(weightsGrid).toBeDefined()

    const weightItems = el.shadowRoot?.querySelectorAll('.weight-item')
    expect(weightItems?.length).toBe(6)
  })

  it('should have save button', async () => {
    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    await el.updateComplete

    const saveBtn = el.shadowRoot?.querySelector('.save-btn')
    expect(saveBtn).toBeDefined()
    expect(saveBtn?.textContent?.trim()).toBe('Save Changes')
  })

  it('should have reset button', async () => {
    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    await el.updateComplete

    const resetBtn = el.shadowRoot?.querySelector('.reset-btn')
    expect(resetBtn).toBeDefined()
    expect(resetBtn?.textContent?.trim()).toBe('Reset to Defaults')
  })

  it('should show validation error when review threshold >= auto-merge threshold', async () => {
    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    // Change review threshold slider to be higher than auto-merge
    const sliders = el.shadowRoot?.querySelectorAll('.slider') as NodeListOf<HTMLInputElement>
    const reviewSlider = sliders?.[1] // Second slider is review threshold
    if (reviewSlider) {
      reviewSlider.value = '0.95'
      reviewSlider.dispatchEvent(new Event('input'))
    }
    await el.updateComplete

    const validationError = el.shadowRoot?.querySelector('.validation-error')
    expect(validationError).toBeDefined()
    expect(validationError?.textContent).toContain('less than auto-merge')
  })

  it('should disable save button when validation fails', async () => {
    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    // Make validation fail
    const sliders = el.shadowRoot?.querySelectorAll('.slider') as NodeListOf<HTMLInputElement>
    const reviewSlider = sliders?.[1]
    if (reviewSlider) {
      reviewSlider.value = '0.95'
      reviewSlider.dispatchEvent(new Event('input'))
    }
    await el.updateComplete

    const saveBtn = el.shadowRoot?.querySelector('.save-btn') as HTMLButtonElement
    expect(saveBtn?.disabled).toBe(true)
  })

  it('should save config when save button is clicked', async () => {
    vi.mocked(apiClient.put).mockResolvedValue({
      success: true,
      data: mockConfig,
    })

    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const saveBtn = el.shadowRoot?.querySelector('.save-btn') as HTMLButtonElement
    saveBtn?.click()

    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(apiClient.put).toHaveBeenCalledWith(
      '/api/v1/consolidation/config',
      expect.any(Object)
    )
  })

  it('should fire config-saved event on successful save', async () => {
    vi.mocked(apiClient.put).mockResolvedValue({
      success: true,
      data: mockConfig,
    })

    const savedHandler = vi.fn()

    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config @config-saved=${savedHandler}></km-consolidation-config>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const saveBtn = el.shadowRoot?.querySelector('.save-btn') as HTMLButtonElement
    saveBtn?.click()

    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(savedHandler).toHaveBeenCalled()
  })

  it('should show error message on save failure', async () => {
    vi.mocked(apiClient.put).mockResolvedValue({
      success: false,
      error: { message: 'Save failed', status: 500, timestamp: '' },
    })

    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const saveBtn = el.shadowRoot?.querySelector('.save-btn') as HTMLButtonElement
    saveBtn?.click()

    await new Promise((resolve) => setTimeout(resolve, 50))
    await el.updateComplete

    const error = el.shadowRoot?.querySelector('.error')
    expect(error).toBeDefined()
    expect(error?.textContent).toContain('Save failed')
  })

  it('should show success message on save success', async () => {
    vi.mocked(apiClient.put).mockResolvedValue({
      success: true,
      data: mockConfig,
    })

    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const saveBtn = el.shadowRoot?.querySelector('.save-btn') as HTMLButtonElement
    saveBtn?.click()

    await new Promise((resolve) => setTimeout(resolve, 50))
    await el.updateComplete

    const success = el.shadowRoot?.querySelector('.success')
    expect(success).toBeDefined()
    expect(success?.textContent).toContain('successfully')
  })

  it('should reset to defaults when reset button is clicked', async () => {
    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    // Change a value first
    const sliders = el.shadowRoot?.querySelectorAll('.slider') as NodeListOf<HTMLInputElement>
    const autoMergeSlider = sliders?.[0]
    if (autoMergeSlider) {
      autoMergeSlider.value = '0.75'
      autoMergeSlider.dispatchEvent(new Event('input'))
    }
    await el.updateComplete

    // Reset
    const resetBtn = el.shadowRoot?.querySelector('.reset-btn') as HTMLButtonElement
    resetBtn?.click()
    await el.updateComplete

    // Check that auto-merge threshold is back to default (0.9)
    const valueEl = el.shadowRoot?.querySelector('.slider-value')
    expect(valueEl?.textContent).toBe('90%')
  })

  it('should display last updated date', async () => {
    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    await new Promise((resolve) => setTimeout(resolve, 100))
    await el.updateComplete

    const lastUpdated = el.shadowRoot?.querySelector('.last-updated')
    expect(lastUpdated).toBeDefined()
    expect(lastUpdated?.textContent).toContain('Last updated')
  })

  it('should show loading state initially', async () => {
    // Delay the API response
    vi.mocked(apiClient.get).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve({ success: true, data: mockConfig }), 500))
    )

    const el = await fixture<KmConsolidationConfig>(
      html`<km-consolidation-config></km-consolidation-config>`
    )

    const loading = el.shadowRoot?.querySelector('.loading')
    expect(loading).toBeDefined()
    expect(loading?.textContent).toContain('Loading')
  })
})
