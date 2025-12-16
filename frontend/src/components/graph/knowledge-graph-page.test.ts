import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fixture, html } from '@open-wc/testing'
import './knowledge-graph-page'
import type { KnowledgeGraphPage } from './knowledge-graph-page'

// Mock the auth store to avoid authentication issues in tests
vi.mock('../../auth', () => ({
  authStore: {
    subscribe: vi.fn((callback) => {
      // Simulate authenticated state
      callback({
        isAuthenticated: true,
        user: { id: 'test-user' },
      })
      return () => {}
    }),
    getState: vi.fn(() => ({
      isAuthenticated: true,
      user: { id: 'test-user' },
    })),
  },
}))

// Mock the API client
vi.mock('../../api/client', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({
      success: true,
      data: {
        nodes: [],
        edges: [],
        total_nodes: 0,
        total_edges: 0,
        truncated: false,
      },
    }),
  },
}))

describe('KnowledgeGraphPage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render the component', async () => {
    const el = await fixture<KnowledgeGraphPage>(
      html`<knowledge-graph-page></knowledge-graph-page>`
    )

    expect(el).toBeDefined()
    expect(el.shadowRoot).toBeDefined()
  })

  it('should render the header with back button', async () => {
    const el = await fixture<KnowledgeGraphPage>(
      html`<knowledge-graph-page></knowledge-graph-page>`
    )

    const header = el.shadowRoot?.querySelector('.header')
    expect(header).toBeDefined()

    const backButton = el.shadowRoot?.querySelector('.back-button')
    expect(backButton).toBeDefined()
    expect(backButton?.textContent?.trim()).toContain('Back')
  })

  it('should render the title', async () => {
    const el = await fixture<KnowledgeGraphPage>(
      html`<knowledge-graph-page></knowledge-graph-page>`
    )

    const title = el.shadowRoot?.querySelector('.title')
    expect(title).toBeDefined()
    expect(title?.textContent?.trim()).toBe('Knowledge Graph')
  })

  it('should dispatch back event when back button is clicked', async () => {
    const el = await fixture<KnowledgeGraphPage>(
      html`<knowledge-graph-page></knowledge-graph-page>`
    )

    const backHandler = vi.fn()
    el.addEventListener('back', backHandler)

    const backButton = el.shadowRoot?.querySelector('.back-button') as HTMLButtonElement
    backButton?.click()

    expect(backHandler).toHaveBeenCalledTimes(1)
    expect(backHandler.mock.calls[0][0]).toBeInstanceOf(CustomEvent)
  })

  it('should pass centerId to knowledge-graph-viewer', async () => {
    const testEntityId = 'test-entity-123'
    const el = await fixture<KnowledgeGraphPage>(
      html`<knowledge-graph-page .centerId=${testEntityId}></knowledge-graph-page>`
    )

    const viewer = el.shadowRoot?.querySelector('knowledge-graph-viewer') as any
    expect(viewer).toBeDefined()
    expect(viewer?.centerId).toBe(testEntityId)
  })

  it('should forward view-entity events from knowledge-graph-viewer', async () => {
    const el = await fixture<KnowledgeGraphPage>(
      html`<knowledge-graph-page></knowledge-graph-page>`
    )

    const viewEntityHandler = vi.fn()
    el.addEventListener('view-entity', viewEntityHandler)

    // Get the viewer and dispatch a view-entity event from it
    const viewer = el.shadowRoot?.querySelector('knowledge-graph-viewer')
    expect(viewer).toBeDefined()

    const testEvent = new CustomEvent('view-entity', {
      detail: { entityId: 'test-entity-456' },
      bubbles: true,
      composed: true,
    })
    viewer?.dispatchEvent(testEvent)

    expect(viewEntityHandler).toHaveBeenCalledTimes(1)
    expect(viewEntityHandler.mock.calls[0][0].detail).toEqual({ entityId: 'test-entity-456' })
  })

  it('should have proper ARIA attributes', async () => {
    const el = await fixture<KnowledgeGraphPage>(
      html`<knowledge-graph-page></knowledge-graph-page>`
    )

    const header = el.shadowRoot?.querySelector('.header')
    expect(header?.getAttribute('role')).toBe('banner')

    const backButton = el.shadowRoot?.querySelector('.back-button')
    expect(backButton?.getAttribute('aria-label')).toBe('Go back to previous page')
  })

  it('should have full viewport dimensions via CSS', async () => {
    const el = await fixture<KnowledgeGraphPage>(
      html`<knowledge-graph-page></knowledge-graph-page>`
    )

    // Verify the component has the expected CSS applied
    const computedStyle = getComputedStyle(el)
    expect(computedStyle.display).toBe('block')
    expect(computedStyle.position).toBe('relative')
  })

  it('should render slot for header actions', async () => {
    const el = await fixture<KnowledgeGraphPage>(
      html`<knowledge-graph-page>
        <button slot="header-actions">Custom Action</button>
      </knowledge-graph-page>`
    )

    const headerActions = el.shadowRoot?.querySelector('.header-actions')
    expect(headerActions).toBeDefined()

    const slot = headerActions?.querySelector('slot[name="header-actions"]')
    expect(slot).toBeDefined()
  })

  it('should render slot for floating panels', async () => {
    const el = await fixture<KnowledgeGraphPage>(
      html`<knowledge-graph-page>
        <div slot="floating-panels">Custom Panel</div>
      </knowledge-graph-page>`
    )

    const viewport = el.shadowRoot?.querySelector('.graph-viewport')
    expect(viewport).toBeDefined()

    const slot = viewport?.querySelector('slot[name="floating-panels"]')
    expect(slot).toBeDefined()
  })

  it('should contain the knowledge-graph-viewer component', async () => {
    const el = await fixture<KnowledgeGraphPage>(
      html`<knowledge-graph-page></knowledge-graph-page>`
    )

    const viewer = el.shadowRoot?.querySelector('knowledge-graph-viewer')
    expect(viewer).toBeDefined()
  })
})
