import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fixture, html, oneEvent } from '@open-wc/testing'
import './graph-controls'
import type { GraphControls } from './graph-controls'
import type { FloatingPanel } from './floating-panel'
import type { EntityType } from '../../api/scraping-types'

describe('GraphControls', () => {
  let element: GraphControls

  beforeEach(async () => {
    element = await fixture<GraphControls>(html`
      <graph-controls .depth=${2} .selectedTypes=${[]}></graph-controls>
    `)
  })

  describe('rendering', () => {
    it('should render inside a floating-panel', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel')
      expect(floatingPanel).toBeDefined()
      expect(floatingPanel).not.toBeNull()
    })

    it('should have "Controls" as panel title', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel') as FloatingPanel
      expect(floatingPanel.panelTitle).toBe('Controls')
    })

    it('should be positioned at top-left', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel') as FloatingPanel
      expect(floatingPanel.position).toBe('top-left')
    })

    it('should be collapsible', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel') as FloatingPanel
      expect(floatingPanel.collapsible).toBe(true)
    })

    it('should start expanded', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel') as FloatingPanel
      expect(floatingPanel.collapsed).toBe(false)
    })

    it('should have a settings icon for collapsed state', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel') as FloatingPanel
      // Check that collapsedIcon is set (it's an SVG TemplateResult)
      expect(floatingPanel.collapsedIcon).toBeDefined()
    })

    it('should render depth slider', async () => {
      const slider = element.shadowRoot?.querySelector('.depth-slider') as HTMLInputElement
      expect(slider).toBeDefined()
      expect(slider).not.toBeNull()
      expect(slider.type).toBe('range')
      expect(slider.min).toBe('1')
      expect(slider.max).toBe('5')
    })

    it('should render entity type checkboxes', async () => {
      const checkboxes = element.shadowRoot?.querySelectorAll('.type-filter-item input[type="checkbox"]')
      expect(checkboxes).toBeDefined()
      expect(checkboxes?.length).toBeGreaterThan(0)
    })

    it('should render Reset Layout button', async () => {
      const buttons = element.shadowRoot?.querySelectorAll('.control-btn')
      const resetButton = Array.from(buttons || []).find(
        (btn) => btn.textContent?.trim() === 'Reset Layout'
      )
      expect(resetButton).toBeDefined()
    })

    it('should render Fit to View button', async () => {
      const buttons = element.shadowRoot?.querySelectorAll('.control-btn')
      const fitViewButton = Array.from(buttons || []).find(
        (btn) => btn.textContent?.trim() === 'Fit to View'
      )
      expect(fitViewButton).toBeDefined()
    })
  })

  describe('depth slider', () => {
    it('should display current depth value', async () => {
      const el = await fixture<GraphControls>(html`
        <graph-controls .depth=${3} .selectedTypes=${[]}></graph-controls>
      `)

      const valueDisplay = el.shadowRoot?.querySelector('.control-value')
      expect(valueDisplay?.textContent).toBe('3')
    })

    it('should dispatch depth-change event on slider change', async () => {
      const slider = element.shadowRoot?.querySelector('.depth-slider') as HTMLInputElement

      const handler = vi.fn()
      element.addEventListener('depth-change', handler)

      slider.value = '4'
      slider.dispatchEvent(new Event('change', { bubbles: true }))

      expect(handler).toHaveBeenCalledTimes(1)
      expect(handler.mock.calls[0][0].detail).toEqual({ depth: 4 })
    })

    it('should have bubbles and composed set to true on depth-change event', async () => {
      const slider = element.shadowRoot?.querySelector('.depth-slider') as HTMLInputElement

      setTimeout(() => {
        slider.value = '3'
        slider.dispatchEvent(new Event('change', { bubbles: true }))
      })

      const event = await oneEvent(element, 'depth-change')
      expect(event.bubbles).toBe(true)
      expect(event.composed).toBe(true)
    })

    it('should have proper accessibility attributes on slider', async () => {
      const slider = element.shadowRoot?.querySelector('.depth-slider') as HTMLInputElement
      expect(slider.getAttribute('aria-label')).toBe('Relationship depth from 1 to 5')
      expect(slider.id).toBe('depth-slider')

      const label = element.shadowRoot?.querySelector('label[for="depth-slider"]')
      expect(label).toBeDefined()
    })
  })

  describe('entity type filters', () => {
    it('should check all types when selectedTypes is empty', async () => {
      const checkboxes = element.shadowRoot?.querySelectorAll(
        '.type-filter-item input[type="checkbox"]'
      ) as NodeListOf<HTMLInputElement>

      checkboxes.forEach((checkbox) => {
        expect(checkbox.checked).toBe(true)
      })
    })

    it('should only check selected types when selectedTypes has values', async () => {
      const el = await fixture<GraphControls>(html`
        <graph-controls .depth=${2} .selectedTypes=${['person' as EntityType]}></graph-controls>
      `)

      const personCheckbox = el.shadowRoot?.querySelector('#type-person') as HTMLInputElement
      expect(personCheckbox.checked).toBe(true)

      // Other checkboxes should be unchecked
      const orgCheckbox = el.shadowRoot?.querySelector('#type-organization') as HTMLInputElement
      if (orgCheckbox) {
        expect(orgCheckbox.checked).toBe(false)
      }
    })

    it('should dispatch type-filter-change event when checkbox is toggled', async () => {
      const checkbox = element.shadowRoot?.querySelector(
        '.type-filter-item input[type="checkbox"]'
      ) as HTMLInputElement

      const handler = vi.fn()
      element.addEventListener('type-filter-change', handler)

      checkbox.checked = false
      checkbox.dispatchEvent(new Event('change', { bubbles: true }))

      expect(handler).toHaveBeenCalledTimes(1)
      expect(handler.mock.calls[0][0].detail.types).toBeDefined()
    })

    it('should show "Show All" link when types are filtered', async () => {
      const el = await fixture<GraphControls>(html`
        <graph-controls .depth=${2} .selectedTypes=${['person' as EntityType]}></graph-controls>
      `)

      const showAllLink = el.shadowRoot?.querySelector('.select-all-link')
      expect(showAllLink).toBeDefined()
      expect(showAllLink?.textContent?.trim()).toBe('Show All')
    })

    it('should not show "Show All" link when no types are filtered', async () => {
      const showAllLink = element.shadowRoot?.querySelector('.select-all-link')
      expect(showAllLink).toBeNull()
    })

    it('should dispatch type-filter-change with empty array when Show All is clicked', async () => {
      const el = await fixture<GraphControls>(html`
        <graph-controls .depth=${2} .selectedTypes=${['person' as EntityType]}></graph-controls>
      `)

      const handler = vi.fn()
      el.addEventListener('type-filter-change', handler)

      const showAllLink = el.shadowRoot?.querySelector('.select-all-link') as HTMLButtonElement
      showAllLink.click()

      expect(handler).toHaveBeenCalledTimes(1)
      expect(handler.mock.calls[0][0].detail).toEqual({ types: [] })
    })

    it('should have proper role and aria-label on filter group', async () => {
      const filterGroup = element.shadowRoot?.querySelector('.type-filter-list')
      expect(filterGroup?.getAttribute('role')).toBe('group')
      expect(filterGroup?.getAttribute('aria-label')).toBe('Entity type filters')
    })
  })

  describe('view controls', () => {
    it('should dispatch reset-layout event when Reset Layout button is clicked', async () => {
      const buttons = element.shadowRoot?.querySelectorAll('.control-btn')
      const resetButton = Array.from(buttons || []).find(
        (btn) => btn.textContent?.trim() === 'Reset Layout'
      ) as HTMLButtonElement

      const handler = vi.fn()
      element.addEventListener('reset-layout', handler)

      resetButton.click()

      expect(handler).toHaveBeenCalledTimes(1)
    })

    it('should dispatch fit-view event when Fit to View button is clicked', async () => {
      const buttons = element.shadowRoot?.querySelectorAll('.control-btn')
      const fitViewButton = Array.from(buttons || []).find(
        (btn) => btn.textContent?.trim() === 'Fit to View'
      ) as HTMLButtonElement

      const handler = vi.fn()
      element.addEventListener('fit-view', handler)

      fitViewButton.click()

      expect(handler).toHaveBeenCalledTimes(1)
    })

    it('should have bubbles and composed on reset-layout event', async () => {
      const buttons = element.shadowRoot?.querySelectorAll('.control-btn')
      const resetButton = Array.from(buttons || []).find(
        (btn) => btn.textContent?.trim() === 'Reset Layout'
      ) as HTMLButtonElement

      setTimeout(() => resetButton.click())

      const event = await oneEvent(element, 'reset-layout')
      expect(event.bubbles).toBe(true)
      expect(event.composed).toBe(true)
    })

    it('should have bubbles and composed on fit-view event', async () => {
      const buttons = element.shadowRoot?.querySelectorAll('.control-btn')
      const fitViewButton = Array.from(buttons || []).find(
        (btn) => btn.textContent?.trim() === 'Fit to View'
      ) as HTMLButtonElement

      setTimeout(() => fitViewButton.click())

      const event = await oneEvent(element, 'fit-view')
      expect(event.bubbles).toBe(true)
      expect(event.composed).toBe(true)
    })

    it('should have title attributes on buttons for tooltips', async () => {
      const buttons = element.shadowRoot?.querySelectorAll('.control-btn')
      const resetButton = Array.from(buttons || []).find(
        (btn) => btn.textContent?.trim() === 'Reset Layout'
      ) as HTMLButtonElement
      const fitViewButton = Array.from(buttons || []).find(
        (btn) => btn.textContent?.trim() === 'Fit to View'
      ) as HTMLButtonElement

      expect(resetButton.title).toBe('Reset the graph layout simulation')
      expect(fitViewButton.title).toBe('Fit all nodes in view')
    })
  })

  describe('accessibility', () => {
    it('should have display: contents on host to let floating-panel position', async () => {
      const hostStyles = getComputedStyle(element)
      expect(hostStyles.display).toBe('contents')
    })

    it('should have associated labels for all inputs', async () => {
      const slider = element.shadowRoot?.querySelector('#depth-slider')
      expect(slider).toBeDefined()

      const checkboxes = element.shadowRoot?.querySelectorAll('.type-filter-item')
      checkboxes?.forEach((item) => {
        const checkbox = item.querySelector('input[type="checkbox"]') as HTMLInputElement
        const label = item.querySelector('label')
        expect(checkbox.id).toBeDefined()
        expect(label?.getAttribute('for')).toBe(checkbox.id)
      })
    })

    it('should have proper button types to prevent form submission', async () => {
      const buttons = element.shadowRoot?.querySelectorAll('button')
      buttons?.forEach((button) => {
        expect(button.type).toBe('button')
      })
    })

    it('should support keyboard interaction on Show All link', async () => {
      const el = await fixture<GraphControls>(html`
        <graph-controls .depth=${2} .selectedTypes=${['person' as EntityType]}></graph-controls>
      `)

      const handler = vi.fn()
      el.addEventListener('type-filter-change', handler)

      const showAllLink = el.shadowRoot?.querySelector('.select-all-link') as HTMLButtonElement

      // Test Enter key
      showAllLink.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })
      )
      expect(handler).toHaveBeenCalledTimes(1)

      // Test Space key
      showAllLink.dispatchEvent(
        new KeyboardEvent('keydown', { key: ' ', bubbles: true })
      )
      expect(handler).toHaveBeenCalledTimes(2)
    })
  })

  describe('floating panel integration', () => {
    it('should collapse and expand via floating-panel', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel') as FloatingPanel
      const panelContent = floatingPanel.shadowRoot?.querySelector('.panel-content')

      // Initially expanded
      expect(panelContent?.getAttribute('aria-hidden')).toBe('false')

      // Collapse via floating-panel
      floatingPanel.collapse()
      await floatingPanel.updateComplete

      expect(panelContent?.getAttribute('aria-hidden')).toBe('true')

      // Expand via floating-panel
      floatingPanel.expand()
      await floatingPanel.updateComplete

      expect(panelContent?.getAttribute('aria-hidden')).toBe('false')
    })

    it('should allow events to bubble through shadow DOM', async () => {
      // Test that events properly compose through the floating-panel boundary
      const depthChangeHandler = vi.fn()
      const typeFilterHandler = vi.fn()
      const resetHandler = vi.fn()
      const fitViewHandler = vi.fn()

      element.addEventListener('depth-change', depthChangeHandler)
      element.addEventListener('type-filter-change', typeFilterHandler)
      element.addEventListener('reset-layout', resetHandler)
      element.addEventListener('fit-view', fitViewHandler)

      // Trigger events
      const slider = element.shadowRoot?.querySelector('.depth-slider') as HTMLInputElement
      slider.value = '3'
      slider.dispatchEvent(new Event('change', { bubbles: true }))

      const checkbox = element.shadowRoot?.querySelector(
        '.type-filter-item input'
      ) as HTMLInputElement
      checkbox.checked = false
      checkbox.dispatchEvent(new Event('change', { bubbles: true }))

      const buttons = element.shadowRoot?.querySelectorAll('.control-btn')
      const resetButton = Array.from(buttons || []).find(
        (btn) => btn.textContent?.trim() === 'Reset Layout'
      ) as HTMLButtonElement
      const fitViewButton = Array.from(buttons || []).find(
        (btn) => btn.textContent?.trim() === 'Fit to View'
      ) as HTMLButtonElement

      resetButton.click()
      fitViewButton.click()

      expect(depthChangeHandler).toHaveBeenCalled()
      expect(typeFilterHandler).toHaveBeenCalled()
      expect(resetHandler).toHaveBeenCalled()
      expect(fitViewHandler).toHaveBeenCalled()
    })
  })

  describe('section structure', () => {
    it('should have Graph Settings section', async () => {
      const sections = element.shadowRoot?.querySelectorAll('.section')
      const titles = element.shadowRoot?.querySelectorAll('.section-title')

      const graphSettingsTitle = Array.from(titles || []).find(
        (t) => t.textContent?.trim() === 'Graph Settings'
      )
      expect(graphSettingsTitle).toBeDefined()
    })

    it('should have Entity Types section', async () => {
      const titles = element.shadowRoot?.querySelectorAll('.section-title')

      const entityTypesTitle = Array.from(titles || []).find(
        (t) => t.textContent?.trim() === 'Entity Types'
      )
      expect(entityTypesTitle).toBeDefined()
    })

    it('should have View Controls section', async () => {
      const titles = element.shadowRoot?.querySelectorAll('.section-title')

      const viewControlsTitle = Array.from(titles || []).find(
        (t) => t.textContent?.trim() === 'View Controls'
      )
      expect(viewControlsTitle).toBeDefined()
    })

    it('should have section dividers between sections', async () => {
      const dividers = element.shadowRoot?.querySelectorAll('.section-divider')
      expect(dividers?.length).toBe(2) // Two dividers between three sections
    })
  })
})
