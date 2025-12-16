import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fixture, html, oneEvent } from '@open-wc/testing'
import './floating-panel'
import type { FloatingPanel } from './floating-panel'

describe('FloatingPanel', () => {
  let element: FloatingPanel

  beforeEach(async () => {
    element = await fixture<FloatingPanel>(html`
      <floating-panel panel-title="Test Panel">
        <div class="test-content">Content here</div>
      </floating-panel>
    `)
  })

  describe('rendering', () => {
    it('should render with title', async () => {
      expect(element).toBeDefined()
      expect(element.shadowRoot).toBeDefined()

      const title = element.shadowRoot?.querySelector('.panel-title')
      expect(title?.textContent).toBe('Test Panel')
    })

    it('should render slot content', async () => {
      const slot = element.shadowRoot?.querySelector('slot')
      expect(slot).toBeDefined()

      // Check that slot content is properly projected
      const assignedNodes = slot?.assignedNodes() || []
      const contentNode = assignedNodes.find(
        (node) => node instanceof HTMLElement && node.classList.contains('test-content')
      )
      expect(contentNode).toBeDefined()
    })

    it('should render collapse button when collapsible is true', async () => {
      const button = element.shadowRoot?.querySelector('.collapse-button')
      expect(button).toBeDefined()
      expect(button?.getAttribute('aria-label')).toBe('Collapse panel')
    })

    it('should not render collapse button when collapsible is false', async () => {
      const el = await fixture<FloatingPanel>(html`
        <floating-panel panel-title="Non-collapsible" .collapsible=${false}>
          Content
        </floating-panel>
      `)

      const button = el.shadowRoot?.querySelector('.collapse-button')
      expect(button).toBeNull()
    })

    it('should render collapsed icon when provided', async () => {
      const el = await fixture<FloatingPanel>(html`
        <floating-panel panel-title="With Icon" collapsed-icon="settings">
          Content
        </floating-panel>
      `)

      const icon = el.shadowRoot?.querySelector('.collapsed-icon')
      expect(icon).toBeDefined()
      expect(icon?.textContent?.trim()).toBe('settings')
    })
  })

  describe('positioning', () => {
    it('should have position attribute reflected for top-left', async () => {
      const el = await fixture<FloatingPanel>(html`
        <floating-panel position="top-left" panel-title="Test"> Content </floating-panel>
      `)

      expect(el.getAttribute('position')).toBe('top-left')
    })

    it('should have position attribute reflected for top-right', async () => {
      const el = await fixture<FloatingPanel>(html`
        <floating-panel position="top-right" panel-title="Test"> Content </floating-panel>
      `)

      expect(el.getAttribute('position')).toBe('top-right')
    })

    it('should have position attribute reflected for bottom-left', async () => {
      const el = await fixture<FloatingPanel>(html`
        <floating-panel position="bottom-left" panel-title="Test"> Content </floating-panel>
      `)

      expect(el.getAttribute('position')).toBe('bottom-left')
    })

    it('should have position attribute reflected for bottom-right', async () => {
      const el = await fixture<FloatingPanel>(html`
        <floating-panel position="bottom-right" panel-title="Test"> Content </floating-panel>
      `)

      expect(el.getAttribute('position')).toBe('bottom-right')
    })

    it('should default to top-left position', async () => {
      expect(element.position).toBe('top-left')
      expect(element.getAttribute('position')).toBe('top-left')
    })
  })

  describe('collapse/expand behavior', () => {
    it('should toggle collapsed state on header click', async () => {
      const header = element.shadowRoot?.querySelector('.panel-header') as HTMLElement
      expect(header).toBeDefined()

      // Initially not collapsed
      const panel = element.shadowRoot?.querySelector('.panel')
      expect(panel?.classList.contains('collapsed')).toBe(false)

      // Click header to collapse
      header.click()
      await element.updateComplete

      expect(panel?.classList.contains('collapsed')).toBe(true)

      // Click again to expand
      header.click()
      await element.updateComplete

      expect(panel?.classList.contains('collapsed')).toBe(false)
    })

    it('should dispatch toggle event with collapsed state', async () => {
      const header = element.shadowRoot?.querySelector('.panel-header') as HTMLElement

      setTimeout(() => header.click())
      const event = await oneEvent(element, 'toggle')

      expect(event).toBeDefined()
      expect(event.detail).toEqual({ collapsed: true })
    })

    it('should dispatch toggle event when expanding', async () => {
      // Start collapsed
      const el = await fixture<FloatingPanel>(html`
        <floating-panel panel-title="Test" collapsed> Content </floating-panel>
      `)

      const header = el.shadowRoot?.querySelector('.panel-header') as HTMLElement

      setTimeout(() => header.click())
      const event = await oneEvent(el, 'toggle')

      expect(event.detail).toEqual({ collapsed: false })
    })

    it('should toggle on collapse button click', async () => {
      const button = element.shadowRoot?.querySelector('.collapse-button') as HTMLButtonElement

      button.click()
      await element.updateComplete

      const panel = element.shadowRoot?.querySelector('.panel')
      expect(panel?.classList.contains('collapsed')).toBe(true)
    })

    it('should hide content when collapsed', async () => {
      const header = element.shadowRoot?.querySelector('.panel-header') as HTMLElement
      header.click()
      await element.updateComplete

      const content = element.shadowRoot?.querySelector('.panel-content')
      expect(content?.getAttribute('aria-hidden')).toBe('true')
    })

    it('should show collapsed icon when collapsed', async () => {
      const el = await fixture<FloatingPanel>(html`
        <floating-panel panel-title="Test" collapsed-icon="X"> Content </floating-panel>
      `)

      const icon = el.shadowRoot?.querySelector('.collapsed-icon') as HTMLElement

      // Initially expanded, icon should be hidden via CSS (display: none)
      const computedStyle = getComputedStyle(icon)
      expect(computedStyle.display).toBe('none')

      // Collapse the panel
      const header = el.shadowRoot?.querySelector('.panel-header') as HTMLElement
      header.click()
      await el.updateComplete

      // When collapsed, icon should be visible
      const collapsedStyle = getComputedStyle(icon)
      expect(collapsedStyle.display).not.toBe('none')
    })

    it('should respect collapsible=false', async () => {
      const el = await fixture<FloatingPanel>(html`
        <floating-panel panel-title="Test" .collapsible=${false}> Content </floating-panel>
      `)

      const header = el.shadowRoot?.querySelector('.panel-header') as HTMLElement
      header.click()
      await el.updateComplete

      const panel = el.shadowRoot?.querySelector('.panel')
      // Should NOT be collapsed
      expect(panel?.classList.contains('collapsed')).toBe(false)
    })

    it('should start collapsed when collapsed prop is true', async () => {
      const el = await fixture<FloatingPanel>(html`
        <floating-panel panel-title="Test" collapsed> Content </floating-panel>
      `)

      const panel = el.shadowRoot?.querySelector('.panel')
      expect(panel?.classList.contains('collapsed')).toBe(true)
    })
  })

  describe('programmatic API', () => {
    it('should toggle via toggle() method', async () => {
      element.toggle()
      await element.updateComplete

      const panel = element.shadowRoot?.querySelector('.panel')
      expect(panel?.classList.contains('collapsed')).toBe(true)

      element.toggle()
      await element.updateComplete
      expect(panel?.classList.contains('collapsed')).toBe(false)
    })

    it('should expand via expand() method', async () => {
      // Start collapsed
      const el = await fixture<FloatingPanel>(html`
        <floating-panel panel-title="Test" collapsed> Content </floating-panel>
      `)

      el.expand()
      await el.updateComplete

      const panel = el.shadowRoot?.querySelector('.panel')
      expect(panel?.classList.contains('collapsed')).toBe(false)
    })

    it('should collapse via collapse() method', async () => {
      element.collapse()
      await element.updateComplete

      const panel = element.shadowRoot?.querySelector('.panel')
      expect(panel?.classList.contains('collapsed')).toBe(true)
    })

    it('should not dispatch event if already in target state', async () => {
      const toggleHandler = vi.fn()
      element.addEventListener('toggle', toggleHandler)

      // Already expanded, expand should do nothing
      element.expand()
      await element.updateComplete

      expect(toggleHandler).not.toHaveBeenCalled()

      // Collapse
      element.collapse()
      await element.updateComplete
      expect(toggleHandler).toHaveBeenCalledTimes(1)

      // Already collapsed, collapse should do nothing
      element.collapse()
      await element.updateComplete
      expect(toggleHandler).toHaveBeenCalledTimes(1)
    })
  })

  describe('accessibility', () => {
    it('should have aria-label on panel region', async () => {
      const panel = element.shadowRoot?.querySelector('.panel')
      expect(panel?.getAttribute('role')).toBe('region')
      expect(panel?.getAttribute('aria-label')).toBe('Test Panel')
    })

    it('should have proper aria attributes on header when collapsible', async () => {
      const header = element.shadowRoot?.querySelector('.panel-header')
      expect(header?.getAttribute('role')).toBe('button')
      expect(header?.getAttribute('tabindex')).toBe('0')
      expect(header?.getAttribute('aria-expanded')).toBe('true')
      expect(header?.getAttribute('aria-controls')).toBe('panel-content')
    })

    it('should update aria-expanded when toggled', async () => {
      const header = element.shadowRoot?.querySelector('.panel-header') as HTMLElement

      header.click()
      await element.updateComplete

      expect(header?.getAttribute('aria-expanded')).toBe('false')
    })

    it('should have aria-label on collapse button', async () => {
      const button = element.shadowRoot?.querySelector('.collapse-button')
      expect(button?.getAttribute('aria-label')).toBe('Collapse panel')

      // Collapse and check label changes
      button?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await element.updateComplete

      expect(button?.getAttribute('aria-label')).toBe('Expand panel')
    })

    it('should toggle on Enter key press on header', async () => {
      const header = element.shadowRoot?.querySelector('.panel-header') as HTMLElement

      header.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
      await element.updateComplete

      const panel = element.shadowRoot?.querySelector('.panel')
      expect(panel?.classList.contains('collapsed')).toBe(true)
    })

    it('should toggle on Space key press on header', async () => {
      const header = element.shadowRoot?.querySelector('.panel-header') as HTMLElement

      header.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }))
      await element.updateComplete

      const panel = element.shadowRoot?.querySelector('.panel')
      expect(panel?.classList.contains('collapsed')).toBe(true)
    })

    it('should toggle on Enter key press on collapse button', async () => {
      const button = element.shadowRoot?.querySelector('.collapse-button') as HTMLButtonElement

      button.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
      await element.updateComplete

      const panel = element.shadowRoot?.querySelector('.panel')
      expect(panel?.classList.contains('collapsed')).toBe(true)
    })

    it('should have heading role when not collapsible', async () => {
      const el = await fixture<FloatingPanel>(html`
        <floating-panel panel-title="Test" .collapsible=${false}> Content </floating-panel>
      `)

      const header = el.shadowRoot?.querySelector('.panel-header')
      expect(header?.getAttribute('role')).toBe('heading')
      expect(header?.getAttribute('tabindex')).toBe('-1')
    })

    it('should have aria-hidden on content when collapsed', async () => {
      const content = element.shadowRoot?.querySelector('.panel-content')
      expect(content?.getAttribute('aria-hidden')).toBe('false')

      element.collapse()
      await element.updateComplete

      expect(content?.getAttribute('aria-hidden')).toBe('true')
    })
  })

  describe('draggable behavior', () => {
    let draggableElement: FloatingPanel

    beforeEach(async () => {
      draggableElement = await fixture<FloatingPanel>(html`
        <floating-panel panel-title="Draggable" draggable> Content </floating-panel>
      `)
    })

    afterEach(() => {
      // Clean up any document event listeners
      document.removeEventListener('mousemove', () => {})
      document.removeEventListener('mouseup', () => {})
    })

    it('should have draggable class on header when draggable is true', async () => {
      const header = draggableElement.shadowRoot?.querySelector('.panel-header')
      expect(header?.classList.contains('draggable')).toBe(true)
    })

    it('should not have draggable class when draggable is false', async () => {
      const header = element.shadowRoot?.querySelector('.panel-header')
      expect(header?.classList.contains('draggable')).toBe(false)
    })

    it('should dispatch position-change event on drag', async () => {
      const header = draggableElement.shadowRoot?.querySelector('.panel-header') as HTMLElement

      // Mock getBoundingClientRect
      vi.spyOn(draggableElement, 'getBoundingClientRect').mockReturnValue({
        left: 100,
        top: 100,
        right: 300,
        bottom: 200,
        width: 200,
        height: 100,
        x: 100,
        y: 100,
        toJSON: () => ({}),
      })

      // Start drag
      header.dispatchEvent(
        new MouseEvent('mousedown', {
          clientX: 150,
          clientY: 120,
          button: 0,
          bubbles: true,
        })
      )

      // Move mouse - should trigger position-change
      const moveHandler = vi.fn()
      draggableElement.addEventListener('position-change', moveHandler)

      document.dispatchEvent(
        new MouseEvent('mousemove', {
          clientX: 200,
          clientY: 170,
        })
      )

      expect(moveHandler).toHaveBeenCalled()
      expect(moveHandler.mock.calls[0][0].detail.x).toBe(150) // 200 - 50 (offset)
      expect(moveHandler.mock.calls[0][0].detail.y).toBe(150) // 170 - 20 (offset)

      // End drag
      document.dispatchEvent(new MouseEvent('mouseup'))
    })

    it('should set custom position attribute when dragged', async () => {
      const header = draggableElement.shadowRoot?.querySelector('.panel-header') as HTMLElement

      vi.spyOn(draggableElement, 'getBoundingClientRect').mockReturnValue({
        left: 100,
        top: 100,
        right: 300,
        bottom: 200,
        width: 200,
        height: 100,
        x: 100,
        y: 100,
        toJSON: () => ({}),
      })

      header.dispatchEvent(
        new MouseEvent('mousedown', {
          clientX: 150,
          clientY: 120,
          button: 0,
          bubbles: true,
        })
      )

      document.dispatchEvent(
        new MouseEvent('mousemove', {
          clientX: 200,
          clientY: 170,
        })
      )

      expect(draggableElement.hasAttribute('data-custom-position')).toBe(true)

      document.dispatchEvent(new MouseEvent('mouseup'))
    })

    it('should reset position via resetPosition() method', async () => {
      // Simulate that the panel was dragged
      draggableElement.setAttribute('data-custom-position', '')
      draggableElement.style.left = '200px'
      draggableElement.style.top = '150px'

      draggableElement.resetPosition()

      expect(draggableElement.hasAttribute('data-custom-position')).toBe(false)
      expect(draggableElement.style.left).toBe('')
      expect(draggableElement.style.top).toBe('')
    })

    it('should not start drag on right click', async () => {
      const header = draggableElement.shadowRoot?.querySelector('.panel-header') as HTMLElement

      header.dispatchEvent(
        new MouseEvent('mousedown', {
          clientX: 150,
          clientY: 120,
          button: 2, // Right click
          bubbles: true,
        })
      )

      const panel = draggableElement.shadowRoot?.querySelector('.panel')
      expect(panel?.classList.contains('dragging')).toBe(false)
    })

    it('should add dragging class during drag', async () => {
      const header = draggableElement.shadowRoot?.querySelector('.panel-header') as HTMLElement

      vi.spyOn(draggableElement, 'getBoundingClientRect').mockReturnValue({
        left: 100,
        top: 100,
        right: 300,
        bottom: 200,
        width: 200,
        height: 100,
        x: 100,
        y: 100,
        toJSON: () => ({}),
      })

      header.dispatchEvent(
        new MouseEvent('mousedown', {
          clientX: 150,
          clientY: 120,
          button: 0,
          bubbles: true,
        })
      )

      await draggableElement.updateComplete

      const panel = draggableElement.shadowRoot?.querySelector('.panel')
      expect(panel?.classList.contains('dragging')).toBe(true)

      // End drag
      document.dispatchEvent(new MouseEvent('mouseup'))
      await draggableElement.updateComplete

      expect(panel?.classList.contains('dragging')).toBe(false)
    })
  })

  describe('varying content sizes', () => {
    it('should handle long titles with ellipsis', async () => {
      const el = await fixture<FloatingPanel>(html`
        <floating-panel
          panel-title="This is a very long title that should be truncated with ellipsis"
        >
          Content
        </floating-panel>
      `)

      const title = el.shadowRoot?.querySelector('.panel-title') as HTMLElement
      expect(title).toBeDefined()

      // Check CSS properties for text overflow
      const styles = getComputedStyle(title)
      expect(styles.overflow).toBe('hidden')
      expect(styles.textOverflow).toBe('ellipsis')
      expect(styles.whiteSpace).toBe('nowrap')
    })

    it('should handle empty content', async () => {
      const el = await fixture<FloatingPanel>(html`
        <floating-panel panel-title="Empty Panel"></floating-panel>
      `)

      expect(el).toBeDefined()
      const content = el.shadowRoot?.querySelector('.panel-content')
      expect(content).toBeDefined()
    })

    it('should handle large content with scrolling', async () => {
      const el = await fixture<FloatingPanel>(html`
        <floating-panel panel-title="Scrollable">
          <div style="height: 500px;">Large content</div>
        </floating-panel>
      `)

      const content = el.shadowRoot?.querySelector('.panel-content') as HTMLElement
      const styles = getComputedStyle(content)
      expect(styles.overflowY).toBe('auto')
      expect(styles.maxHeight).toBe('400px')
    })
  })

  describe('external prop sync', () => {
    it('should sync isCollapsed when collapsed prop changes', async () => {
      // Start expanded
      expect(element.collapsed).toBe(false)

      // Change prop
      element.collapsed = true
      await element.updateComplete

      const panel = element.shadowRoot?.querySelector('.panel')
      expect(panel?.classList.contains('collapsed')).toBe(true)
    })
  })
})
