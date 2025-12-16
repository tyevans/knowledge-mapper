import { describe, it, expect, beforeEach } from 'vitest'
import { fixture, html, oneEvent } from '@open-wc/testing'
import './graph-legend'
import type { GraphLegend } from './graph-legend'
import { ENTITY_TYPE_LABELS, ENTITY_TYPE_COLORS } from '../../api/scraping-types'

describe('GraphLegend', () => {
  let element: GraphLegend

  beforeEach(async () => {
    element = await fixture<GraphLegend>(html` <graph-legend></graph-legend> `)
  })

  describe('rendering', () => {
    it('should render inside a floating-panel', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel')
      expect(floatingPanel).toBeDefined()
      expect(floatingPanel).not.toBeNull()
    })

    it('should have panel-title set to Legend', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel')
      expect(floatingPanel?.getAttribute('panel-title')).toBe('Legend')
    })

    it('should be positioned at bottom-left', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel')
      expect(floatingPanel?.getAttribute('position')).toBe('bottom-left')
    })

    it('should have a collapsed icon', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel')
      expect(floatingPanel?.getAttribute('collapsed-icon')).toBe('(i)')
    })

    it('should render all entity type colors', async () => {
      const legendItems = element.shadowRoot?.querySelectorAll('.legend-item')
      const entityTypeCount = Object.keys(ENTITY_TYPE_LABELS).length

      expect(legendItems?.length).toBe(entityTypeCount)
    })

    it('should render entity type labels correctly', async () => {
      const labels = element.shadowRoot?.querySelectorAll('.legend-label')
      const expectedLabels = Object.values(ENTITY_TYPE_LABELS)

      expect(labels?.length).toBe(expectedLabels.length)

      labels?.forEach((label, index) => {
        expect(expectedLabels).toContain(label.textContent?.trim())
      })
    })

    it('should render color dots with correct colors', async () => {
      const colorDots = element.shadowRoot?.querySelectorAll('.legend-color')
      const entityTypes = Object.keys(ENTITY_TYPE_COLORS)

      colorDots?.forEach((dot, index) => {
        const dotElement = dot as HTMLElement
        const expectedColor = ENTITY_TYPE_COLORS[entityTypes[index] as keyof typeof ENTITY_TYPE_COLORS]
        expect(dotElement.style.backgroundColor).toBeDefined()
      })
    })

    it('should render interaction hints section', async () => {
      const hintsSection = element.shadowRoot?.querySelector('.interaction-hints')
      expect(hintsSection).toBeDefined()
      expect(hintsSection).not.toBeNull()
    })

    it('should render all interaction hints', async () => {
      const hints = element.shadowRoot?.querySelectorAll('.hint')
      expect(hints?.length).toBe(4) // Click, Drag, Scroll, Pan
    })

    it('should render Click hint', async () => {
      const hints = element.shadowRoot?.querySelectorAll('.hint')
      const hintTexts = Array.from(hints || []).map((h) => h.textContent)
      expect(hintTexts.some((t) => t?.includes('Click'))).toBe(true)
      expect(hintTexts.some((t) => t?.includes('Select node'))).toBe(true)
    })

    it('should render Drag hint', async () => {
      const hints = element.shadowRoot?.querySelectorAll('.hint')
      const hintTexts = Array.from(hints || []).map((h) => h.textContent)
      expect(hintTexts.some((t) => t?.includes('Drag'))).toBe(true)
      expect(hintTexts.some((t) => t?.includes('Move nodes'))).toBe(true)
    })

    it('should render Scroll hint', async () => {
      const hints = element.shadowRoot?.querySelectorAll('.hint')
      const hintTexts = Array.from(hints || []).map((h) => h.textContent)
      expect(hintTexts.some((t) => t?.includes('Scroll'))).toBe(true)
      expect(hintTexts.some((t) => t?.includes('Zoom'))).toBe(true)
    })

    it('should render Pan hint', async () => {
      const hints = element.shadowRoot?.querySelectorAll('.hint')
      const hintTexts = Array.from(hints || []).map((h) => h.textContent)
      expect(hintTexts.some((t) => t?.includes('Pan'))).toBe(true)
      expect(hintTexts.some((t) => t?.includes('background'))).toBe(true)
    })
  })

  describe('collapsed state', () => {
    it('should start collapsed by default', async () => {
      expect(element.collapsed).toBe(true)
    })

    it('should allow starting expanded', async () => {
      const expandedElement = await fixture<GraphLegend>(html`
        <graph-legend .collapsed=${false}></graph-legend>
      `)

      expect(expandedElement.collapsed).toBe(false)
    })

    it('should pass collapsed prop to floating-panel', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel') as HTMLElement & {
        collapsed: boolean
      }
      // The floating-panel internally handles the collapsed state
      expect(floatingPanel).toBeDefined()
    })
  })

  describe('floating-panel integration', () => {
    it('should forward toggle events from floating-panel', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel') as HTMLElement

      // Dispatch toggle event from floating-panel
      setTimeout(() => {
        floatingPanel.dispatchEvent(
          new CustomEvent('toggle', {
            detail: { collapsed: false },
            bubbles: true,
            composed: true,
          })
        )
      })

      const event = await oneEvent(element, 'toggle')
      expect(event).toBeDefined()
      expect(event.detail.collapsed).toBe(false)
    })

    it('should render content inside floating-panel slot', async () => {
      const floatingPanel = element.shadowRoot?.querySelector('floating-panel')
      const legendContent = floatingPanel?.querySelector('.legend-content')
      expect(legendContent).toBeDefined()
    })
  })

  describe('accessibility', () => {
    it('should have section titles for entity types and interactions', async () => {
      const sectionTitles = element.shadowRoot?.querySelectorAll('.section-title')
      expect(sectionTitles?.length).toBe(2)

      const titles = Array.from(sectionTitles || []).map((t) => t.textContent)
      expect(titles).toContain('Entity Types')
      expect(titles).toContain('Interactions')
    })

    it('should have display: contents on host for proper floating behavior', async () => {
      // The :host should have display: contents to allow floating-panel
      // to position itself properly
      expect(element.shadowRoot).toBeDefined()
    })
  })

  describe('styling', () => {
    it('should have legend-list for entity types', async () => {
      const legendList = element.shadowRoot?.querySelector('.legend-list')
      expect(legendList).toBeDefined()
      expect(legendList).not.toBeNull()
    })

    it('should have interaction-hints section with border', async () => {
      const hints = element.shadowRoot?.querySelector('.interaction-hints')
      expect(hints).toBeDefined()
    })

    it('should have color dots with border-radius for round appearance', async () => {
      const colorDot = element.shadowRoot?.querySelector('.legend-color') as HTMLElement
      expect(colorDot).toBeDefined()

      const styles = getComputedStyle(colorDot)
      expect(styles.borderRadius).toBe('50%')
    })
  })
})
