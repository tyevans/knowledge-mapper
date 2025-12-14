import { LitElement, html, css } from 'lit'
import { customElement, property } from 'lit/decorators.js'

/**
 * Reusable pagination component.
 *
 * @fires page-change - Dispatched when user navigates to a different page
 */
@customElement('km-pagination')
export class KmPagination extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .pagination {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 1rem;
      border-top: 1px solid #e5e7eb;
    }

    .pagination-info {
      font-size: 0.875rem;
      color: #6b7280;
    }

    .pagination-controls {
      display: flex;
      gap: 0.25rem;
    }

    .page-btn {
      padding: 0.375rem 0.75rem;
      border: 1px solid #e5e7eb;
      border-radius: 0.25rem;
      background: white;
      font-size: 0.875rem;
      cursor: pointer;
      transition: all 0.2s;
    }

    .page-btn:hover:not(:disabled) {
      background: #f9fafb;
      border-color: #1e3a8a;
    }

    .page-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .page-btn.active {
      background: #1e3a8a;
      color: white;
      border-color: #1e3a8a;
    }

    .ellipsis {
      padding: 0.375rem 0.5rem;
      color: #6b7280;
    }
  `

  /** Current page number (1-indexed) */
  @property({ type: Number })
  page = 1

  /** Total number of items */
  @property({ type: Number })
  total = 0

  /** Items per page */
  @property({ type: Number, attribute: 'page-size' })
  pageSize = 20

  /** Total number of pages */
  @property({ type: Number })
  pages = 1

  /** Maximum visible page buttons */
  @property({ type: Number, attribute: 'max-visible' })
  maxVisible = 5

  private goToPage(newPage: number): void {
    if (newPage < 1 || newPage > this.pages || newPage === this.page) {
      return
    }

    this.dispatchEvent(
      new CustomEvent('page-change', {
        detail: { page: newPage },
        bubbles: true,
        composed: true,
      })
    )
  }

  private getVisiblePages(): (number | 'ellipsis')[] {
    const pages: (number | 'ellipsis')[] = []

    if (this.pages <= this.maxVisible) {
      // Show all pages if total is small
      for (let i = 1; i <= this.pages; i++) {
        pages.push(i)
      }
    } else {
      // Always show first page
      pages.push(1)

      // Calculate range around current page
      const halfVisible = Math.floor((this.maxVisible - 2) / 2)
      let start = Math.max(2, this.page - halfVisible)
      let end = Math.min(this.pages - 1, this.page + halfVisible)

      // Adjust if at edges
      if (this.page <= halfVisible + 1) {
        end = this.maxVisible - 1
      }
      if (this.page >= this.pages - halfVisible) {
        start = this.pages - this.maxVisible + 2
      }

      // Add ellipsis before if needed
      if (start > 2) {
        pages.push('ellipsis')
      }

      // Add middle pages
      for (let i = start; i <= end; i++) {
        pages.push(i)
      }

      // Add ellipsis after if needed
      if (end < this.pages - 1) {
        pages.push('ellipsis')
      }

      // Always show last page
      pages.push(this.pages)
    }

    return pages
  }

  render() {
    const startItem = (this.page - 1) * this.pageSize + 1
    const endItem = Math.min(this.page * this.pageSize, this.total)
    const visiblePages = this.getVisiblePages()

    return html`
      <div class="pagination">
        <div class="pagination-info">
          Showing ${startItem}-${endItem} of ${this.total}
        </div>
        <div class="pagination-controls">
          <button
            class="page-btn"
            ?disabled=${this.page === 1}
            @click=${() => this.goToPage(this.page - 1)}
            aria-label="Previous page"
          >
            &laquo;
          </button>

          ${visiblePages.map((p) =>
            p === 'ellipsis'
              ? html`<span class="ellipsis">...</span>`
              : html`
                  <button
                    class="page-btn ${p === this.page ? 'active' : ''}"
                    @click=${() => this.goToPage(p as number)}
                    aria-label="Page ${p}"
                    aria-current=${p === this.page ? 'page' : 'false'}
                  >
                    ${p}
                  </button>
                `
          )}

          <button
            class="page-btn"
            ?disabled=${this.page === this.pages}
            @click=${() => this.goToPage(this.page + 1)}
            aria-label="Next page"
          >
            &raquo;
          </button>
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'km-pagination': KmPagination
  }
}
