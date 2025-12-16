import { LitElement, html, css } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import type { GraphNode } from '../../api/scraping-types'
import { ENTITY_TYPE_COLORS } from '../../api/scraping-types'
import './floating-panel'

/**
 * Search icon SVG for collapsed panel state.
 */
const SEARCH_ICON = html`
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <circle cx="11" cy="11" r="8"></circle>
    <path d="m21 21-4.35-4.35"></path>
  </svg>
`

/**
 * Graph Search Component
 *
 * Search and filter nodes in the knowledge graph visualization.
 *
 * @fires focus-node - When user selects a node from search results
 * @fires search-highlight - When search query changes (for highlighting matches)
 */
@customElement('graph-search')
export class GraphSearch extends LitElement {
  static styles = css`
    :host {
      display: contents;
    }

    .search-content {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      padding: 0.75rem;
      min-width: 220px;
    }

    .search-input-wrapper {
      position: relative;
      display: flex;
      align-items: center;
    }

    .search-icon {
      position: absolute;
      left: 0.625rem;
      color: #9ca3af;
      pointer-events: none;
    }

    .search-input {
      width: 100%;
      padding: 0.5rem 0.75rem 0.5rem 2rem;
      font-size: 0.8125rem;
      border: 1px solid #d1d5db;
      border-radius: 0.375rem;
      background: white;
      color: #374151;
    }

    .search-input:focus {
      outline: none;
      border-color: #1e3a8a;
      box-shadow: 0 0 0 2px rgba(30, 58, 138, 0.1);
    }

    .search-input::placeholder {
      color: #9ca3af;
    }

    .clear-btn {
      position: absolute;
      right: 0.5rem;
      background: none;
      border: none;
      color: #9ca3af;
      cursor: pointer;
      padding: 0.25rem;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 0.25rem;
    }

    .clear-btn:hover {
      color: #6b7280;
      background: #f3f4f6;
    }

    .results-list {
      max-height: 200px;
      overflow-y: auto;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .results-list::-webkit-scrollbar {
      width: 4px;
    }

    .results-list::-webkit-scrollbar-track {
      background: #f1f5f9;
      border-radius: 2px;
    }

    .results-list::-webkit-scrollbar-thumb {
      background: #cbd5e1;
      border-radius: 2px;
    }

    .result-item {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 0.625rem;
      cursor: pointer;
      border-radius: 0.25rem;
      font-size: 0.8125rem;
    }

    .result-item:hover {
      background: #f0f5ff;
    }

    .result-item:focus {
      outline: 2px solid #1e3a8a;
      outline-offset: -2px;
    }

    .result-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .result-name {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #374151;
    }

    .result-type {
      font-size: 0.6875rem;
      color: #6b7280;
      flex-shrink: 0;
    }

    .no-results {
      padding: 0.75rem;
      text-align: center;
      color: #6b7280;
      font-size: 0.8125rem;
    }

    .result-count {
      font-size: 0.6875rem;
      color: #6b7280;
      padding: 0.25rem 0;
    }
  `

  @property({ type: Array })
  nodes: GraphNode[] = []

  @state()
  private searchQuery = ''

  @state()
  private filteredNodes: GraphNode[] = []

  private handleSearchInput(e: InputEvent): void {
    this.searchQuery = (e.target as HTMLInputElement).value.toLowerCase()

    if (this.searchQuery.length === 0) {
      this.filteredNodes = []
      this.dispatchSearchHighlight([])
      return
    }

    // Filter nodes matching the query
    this.filteredNodes = this.nodes
      .filter((n) => n.name.toLowerCase().includes(this.searchQuery))
      .slice(0, 20) // Limit to 20 results

    // Emit highlight event for matching nodes
    this.dispatchSearchHighlight(this.filteredNodes.map((n) => n.id))
  }

  private handleClear(): void {
    this.searchQuery = ''
    this.filteredNodes = []
    this.dispatchSearchHighlight([])
  }

  private dispatchSearchHighlight(nodeIds: string[]): void {
    this.dispatchEvent(
      new CustomEvent('search-highlight', {
        detail: { nodeIds },
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleSelectNode(node: GraphNode): void {
    this.dispatchEvent(
      new CustomEvent('focus-node', {
        detail: { nodeId: node.id, nodeName: node.name },
        bubbles: true,
        composed: true,
      })
    )
  }

  private handleKeyDown(e: KeyboardEvent, node: GraphNode): void {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      this.handleSelectNode(node)
    }
  }

  render() {
    return html`
      <floating-panel
        panel-title="Search"
        position="top-right"
        .collapsedIcon=${SEARCH_ICON}
        .collapsed=${true}
        collapsible
      >
        <div class="search-content">
          <div class="search-input-wrapper">
            <svg
              class="search-icon"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="11" cy="11" r="8"></circle>
              <path d="m21 21-4.35-4.35"></path>
            </svg>
            <input
              type="text"
              class="search-input"
              placeholder="Search nodes..."
              .value=${this.searchQuery}
              @input=${this.handleSearchInput}
              aria-label="Search for nodes by name"
            />
            ${this.searchQuery
              ? html`
                  <button
                    type="button"
                    class="clear-btn"
                    @click=${this.handleClear}
                    title="Clear search"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M18 6L6 18M6 6l12 12"></path>
                    </svg>
                  </button>
                `
              : null}
          </div>

          ${this.searchQuery
            ? this.filteredNodes.length > 0
              ? html`
                  <div class="result-count">
                    ${this.filteredNodes.length} result${this.filteredNodes.length !== 1 ? 's' : ''}
                  </div>
                  <ul class="results-list" role="listbox">
                    ${this.filteredNodes.map(
                      (node) => html`
                        <li
                          class="result-item"
                          role="option"
                          tabindex="0"
                          @click=${() => this.handleSelectNode(node)}
                          @keydown=${(e: KeyboardEvent) => this.handleKeyDown(e, node)}
                        >
                          <span
                            class="result-dot"
                            style="background-color: ${ENTITY_TYPE_COLORS[node.entity_type] || '#6b7280'}"
                          ></span>
                          <span class="result-name">${node.name}</span>
                          <span class="result-type">${node.entity_type}</span>
                        </li>
                      `
                    )}
                  </ul>
                `
              : html`<div class="no-results">No matching nodes found</div>`
            : null}
        </div>
      </floating-panel>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'graph-search': GraphSearch
  }
}
