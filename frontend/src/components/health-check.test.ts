import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fixture, html } from '@open-wc/testing'
import './health-check'
import type { HealthCheck } from './health-check'
import { healthApi } from '../api'

// Mock the health API
vi.mock('../api', () => ({
  healthApi: {
    checkHealth: vi.fn(),
  },
}))

describe('HealthCheck Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render the component', async () => {
    vi.mocked(healthApi.checkHealth).mockResolvedValue({
      success: true,
      data: {
        status: 'healthy',
        version: '1.0.0',
        timestamp: '2025-11-10T12:00:00Z',
      },
    })

    const el = await fixture<HealthCheck>(html`<health-check></health-check>`)

    expect(el).toBeDefined()
    expect(el.shadowRoot).toBeDefined()
  })

  it('should display health status after successful check', async () => {
    vi.mocked(healthApi.checkHealth).mockResolvedValue({
      success: true,
      data: {
        status: 'healthy',
        version: '1.0.0',
        timestamp: '2025-11-10T12:00:00Z',
      },
    })

    const el = await fixture<HealthCheck>(html`<health-check></health-check>`)

    // Wait for the component to finish loading
    await new Promise(resolve => setTimeout(resolve, 100))
    await el.updateComplete

    const statusText = el.shadowRoot?.querySelector('.status-text')
    expect(statusText?.textContent?.trim()).toBe('healthy')
  })

  it('should display error message when health check fails', async () => {
    vi.mocked(healthApi.checkHealth).mockResolvedValue({
      success: false,
      error: {
        message: 'Connection failed',
        status: 500,
      },
    })

    const el = await fixture<HealthCheck>(html`<health-check></health-check>`)

    // Wait for the component to finish loading
    await new Promise(resolve => setTimeout(resolve, 100))
    await el.updateComplete

    const errorMessage = el.shadowRoot?.querySelector('.error-message')
    expect(errorMessage).toBeDefined()
    expect(errorMessage?.textContent).toContain('Connection failed')
  })

  it('should display loading state during health check', async () => {
    // Create a promise that we can control
    let resolveHealthCheck: (value: any) => void
    const healthCheckPromise = new Promise(resolve => {
      resolveHealthCheck = resolve
    })

    vi.mocked(healthApi.checkHealth).mockReturnValue(healthCheckPromise as any)

    const el = await fixture<HealthCheck>(html`<health-check></health-check>`)

    // Component should be in loading state
    const statusIndicator = el.shadowRoot?.querySelector('.status-indicator')
    expect(statusIndicator?.classList.contains('loading')).toBe(true)

    // Resolve the promise
    resolveHealthCheck!({
      success: true,
      data: {
        status: 'healthy',
        version: '1.0.0',
        timestamp: '2025-11-10T12:00:00Z',
      },
    })

    await el.updateComplete
  })

  it('should have a check health button', async () => {
    vi.mocked(healthApi.checkHealth).mockResolvedValue({
      success: true,
      data: {
        status: 'healthy',
        version: '1.0.0',
        timestamp: '2025-11-10T12:00:00Z',
      },
    })

    const el = await fixture<HealthCheck>(html`<health-check></health-check>`)
    await el.updateComplete

    const button = el.shadowRoot?.querySelector('button')
    expect(button).toBeDefined()
    expect(button?.textContent?.trim()).toBe('Check Health')
  })

  it('should call checkHealth when button is clicked', async () => {
    vi.mocked(healthApi.checkHealth).mockResolvedValue({
      success: true,
      data: {
        status: 'healthy',
        version: '1.0.0',
        timestamp: '2025-11-10T12:00:00Z',
      },
    })

    const el = await fixture<HealthCheck>(html`<health-check></health-check>`)
    await el.updateComplete

    // Clear the initial call from connectedCallback
    vi.clearAllMocks()

    const button = el.shadowRoot?.querySelector('button') as HTMLButtonElement
    button?.click()

    await new Promise(resolve => setTimeout(resolve, 100))

    expect(healthApi.checkHealth).toHaveBeenCalledTimes(1)
  })
})
