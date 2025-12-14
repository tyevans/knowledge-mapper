import { LitElement, html, css } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import { apiClient } from '../../api/client'
import type { CreateScrapingJobRequest, ScrapingJobResponse } from '../../api/scraping-types'

/**
 * Modal for creating a new scraping job.
 *
 * @fires close - When modal is closed
 * @fires job-created - When a job is successfully created
 */
@customElement('scraping-job-create-modal')
export class ScrapingJobCreateModal extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .modal-backdrop {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      padding: 1rem;
    }

    .modal {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
      width: 100%;
      max-width: 32rem;
      max-height: 90vh;
      overflow-y: auto;
    }

    .modal-header {
      background: #1f2937;
      color: white;
      padding: 1rem 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-radius: 0.5rem 0.5rem 0 0;
    }

    .modal-header h2 {
      margin: 0;
      font-size: 1.125rem;
    }

    .close-btn {
      background: transparent;
      border: none;
      color: white;
      font-size: 1.5rem;
      cursor: pointer;
      padding: 0;
      line-height: 1;
      opacity: 0.8;
    }

    .close-btn:hover {
      opacity: 1;
    }

    .modal-body {
      padding: 1.5rem;
    }

    .form-group {
      margin-bottom: 1rem;
    }

    .form-label {
      display: block;
      font-size: 0.875rem;
      font-weight: 500;
      color: #374151;
      margin-bottom: 0.375rem;
    }

    .form-label .required {
      color: #ef4444;
    }

    .form-hint {
      font-size: 0.75rem;
      color: #6b7280;
      margin-top: 0.25rem;
    }

    .form-input {
      width: 100%;
      padding: 0.5rem 0.75rem;
      border: 1px solid #d1d5db;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      box-sizing: border-box;
      transition: border-color 0.2s, box-shadow 0.2s;
    }

    .form-input:focus {
      outline: none;
      border-color: #1e3a8a;
      box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
    }

    .form-input.error {
      border-color: #ef4444;
    }

    .form-input:disabled {
      background: #f9fafb;
      cursor: not-allowed;
    }

    .form-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }

    .form-checkbox {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .form-checkbox input {
      width: 1rem;
      height: 1rem;
      accent-color: #1e3a8a;
    }

    .form-checkbox label {
      font-size: 0.875rem;
      color: #374151;
    }

    .form-error {
      color: #ef4444;
      font-size: 0.75rem;
      margin-top: 0.25rem;
    }

    .modal-footer {
      padding: 1rem 1.5rem;
      border-top: 1px solid #e5e7eb;
      display: flex;
      justify-content: flex-end;
      gap: 0.75rem;
    }

    .btn {
      padding: 0.5rem 1rem;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
    }

    .btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .btn-secondary {
      background: white;
      border: 1px solid #d1d5db;
      color: #374151;
    }

    .btn-secondary:hover:not(:disabled) {
      background: #f9fafb;
    }

    .btn-primary {
      background: #1e3a8a;
      border: 1px solid #1e3a8a;
      color: white;
    }

    .btn-primary:hover:not(:disabled) {
      background: #1e40af;
    }

    .global-error {
      background: #fef2f2;
      color: #991b1b;
      padding: 0.75rem;
      border-radius: 0.375rem;
      margin-bottom: 1rem;
      font-size: 0.875rem;
    }

    .advanced-toggle {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 0;
      font-size: 0.875rem;
      color: #1e3a8a;
      cursor: pointer;
      border: none;
      background: none;
    }

    .advanced-toggle:hover {
      text-decoration: underline;
    }

    .advanced-section {
      border-top: 1px solid #e5e7eb;
      padding-top: 1rem;
      margin-top: 0.5rem;
    }
  `

  @property({ type: Boolean })
  open = false

  @state()
  private formData: CreateScrapingJobRequest = {
    name: '',
    start_url: '',
    allowed_domains: [],
    crawl_depth: 2,
    max_pages: 100,
    crawl_speed: 1.0,
    respect_robots_txt: true,
    use_llm_extraction: true,
  }

  @state()
  private errors: Partial<Record<keyof CreateScrapingJobRequest, string>> = {}

  @state()
  private globalError: string | null = null

  @state()
  private isSubmitting = false

  @state()
  private showAdvanced = false

  private handleClose(): void {
    this.resetForm()
    this.dispatchEvent(new CustomEvent('close'))
  }

  private resetForm(): void {
    this.formData = {
      name: '',
      start_url: '',
      allowed_domains: [],
      crawl_depth: 2,
      max_pages: 100,
      crawl_speed: 1.0,
      respect_robots_txt: true,
      use_llm_extraction: true,
    }
    this.errors = {}
    this.globalError = null
    this.showAdvanced = false
  }

  private handleInputChange(field: keyof CreateScrapingJobRequest, value: unknown): void {
    this.formData = { ...this.formData, [field]: value }
    if (this.errors[field]) {
      this.errors = { ...this.errors, [field]: undefined }
    }

    // Auto-populate allowed domains when URL changes
    if (field === 'start_url' && typeof value === 'string') {
      this.autoPopulateDomains(value)
    }
  }

  private autoPopulateDomains(url: string): void {
    try {
      const parsedUrl = new URL(url)
      this.formData = {
        ...this.formData,
        allowed_domains: [parsedUrl.hostname],
      }
    } catch {
      // Invalid URL, don't auto-populate
    }
  }

  private validateForm(): boolean {
    const errors: Partial<Record<keyof CreateScrapingJobRequest, string>> = {}

    // Name validation
    if (!this.formData.name.trim()) {
      errors.name = 'Name is required'
    } else if (this.formData.name.length > 255) {
      errors.name = 'Name must be 255 characters or less'
    }

    // URL validation
    if (!this.formData.start_url.trim()) {
      errors.start_url = 'Start URL is required'
    } else {
      try {
        const url = new URL(this.formData.start_url)
        if (!['http:', 'https:'].includes(url.protocol)) {
          errors.start_url = 'URL must use HTTP or HTTPS protocol'
        }
      } catch {
        errors.start_url = 'Please enter a valid URL'
      }
    }

    // Crawl depth validation
    if (
      this.formData.crawl_depth !== undefined &&
      (this.formData.crawl_depth < 1 || this.formData.crawl_depth > 10)
    ) {
      errors.crawl_depth = 'Depth must be between 1 and 10'
    }

    // Max pages validation
    if (
      this.formData.max_pages !== undefined &&
      (this.formData.max_pages < 1 || this.formData.max_pages > 10000)
    ) {
      errors.max_pages = 'Max pages must be between 1 and 10,000'
    }

    // Crawl speed validation
    if (
      this.formData.crawl_speed !== undefined &&
      (this.formData.crawl_speed < 0.1 || this.formData.crawl_speed > 10)
    ) {
      errors.crawl_speed = 'Speed must be between 0.1 and 10 req/sec'
    }

    this.errors = errors
    return Object.keys(errors).length === 0
  }

  private async handleSubmit(e: Event): Promise<void> {
    e.preventDefault()

    if (!this.validateForm()) {
      return
    }

    this.isSubmitting = true
    this.globalError = null

    try {
      const response = await apiClient.post<ScrapingJobResponse>(
        '/api/v1/scraping/jobs',
        this.formData
      )

      if (response.success) {
        this.dispatchEvent(
          new CustomEvent('job-created', {
            detail: { job: response.data },
            bubbles: true,
            composed: true,
          })
        )
        this.handleClose()
      } else {
        this.globalError = response.error.message
      }
    } catch (err) {
      this.globalError = err instanceof Error ? err.message : 'Failed to create job'
    } finally {
      this.isSubmitting = false
    }
  }

  private handleBackdropClick(e: Event): void {
    if (e.target === e.currentTarget) {
      this.handleClose()
    }
  }

  render() {
    if (!this.open) {
      return null
    }

    return html`
      <div class="modal-backdrop" @click=${this.handleBackdropClick}>
        <div class="modal" role="dialog" aria-labelledby="modal-title" aria-modal="true">
          <div class="modal-header">
            <h2 id="modal-title">Create Scraping Job</h2>
            <button
              class="close-btn"
              @click=${this.handleClose}
              aria-label="Close modal"
            >
              &times;
            </button>
          </div>

          <form @submit=${this.handleSubmit}>
            <div class="modal-body">
              ${this.globalError
                ? html`<div class="global-error">${this.globalError}</div>`
                : null}

              <div class="form-group">
                <label class="form-label">
                  Job Name <span class="required">*</span>
                </label>
                <input
                  type="text"
                  class="form-input ${this.errors.name ? 'error' : ''}"
                  .value=${this.formData.name}
                  @input=${(e: Event) =>
                    this.handleInputChange('name', (e.target as HTMLInputElement).value)}
                  placeholder="e.g., Documentation Site Scrape"
                  ?disabled=${this.isSubmitting}
                />
                ${this.errors.name
                  ? html`<div class="form-error">${this.errors.name}</div>`
                  : null}
              </div>

              <div class="form-group">
                <label class="form-label">
                  Start URL <span class="required">*</span>
                </label>
                <input
                  type="url"
                  class="form-input ${this.errors.start_url ? 'error' : ''}"
                  .value=${this.formData.start_url}
                  @input=${(e: Event) =>
                    this.handleInputChange('start_url', (e.target as HTMLInputElement).value)}
                  placeholder="https://example.com/docs"
                  ?disabled=${this.isSubmitting}
                />
                <div class="form-hint">The URL where the crawler will begin</div>
                ${this.errors.start_url
                  ? html`<div class="form-error">${this.errors.start_url}</div>`
                  : null}
              </div>

              <div class="form-group">
                <label class="form-label">Allowed Domains</label>
                <input
                  type="text"
                  class="form-input"
                  .value=${this.formData.allowed_domains?.join(', ') || ''}
                  @input=${(e: Event) => {
                    const value = (e.target as HTMLInputElement).value
                    const domains = value
                      .split(',')
                      .map((d) => d.trim())
                      .filter((d) => d)
                    this.handleInputChange('allowed_domains', domains)
                  }}
                  placeholder="example.com, docs.example.com"
                  ?disabled=${this.isSubmitting}
                />
                <div class="form-hint">
                  Comma-separated list. Auto-populated from Start URL.
                </div>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">Crawl Depth</label>
                  <input
                    type="number"
                    class="form-input ${this.errors.crawl_depth ? 'error' : ''}"
                    .value=${this.formData.crawl_depth?.toString() || '2'}
                    @input=${(e: Event) =>
                      this.handleInputChange(
                        'crawl_depth',
                        parseInt((e.target as HTMLInputElement).value, 10)
                      )}
                    min="1"
                    max="10"
                    ?disabled=${this.isSubmitting}
                  />
                  <div class="form-hint">Link levels to follow (1-10)</div>
                  ${this.errors.crawl_depth
                    ? html`<div class="form-error">${this.errors.crawl_depth}</div>`
                    : null}
                </div>

                <div class="form-group">
                  <label class="form-label">Max Pages</label>
                  <input
                    type="number"
                    class="form-input ${this.errors.max_pages ? 'error' : ''}"
                    .value=${this.formData.max_pages?.toString() || '100'}
                    @input=${(e: Event) =>
                      this.handleInputChange(
                        'max_pages',
                        parseInt((e.target as HTMLInputElement).value, 10)
                      )}
                    min="1"
                    max="10000"
                    ?disabled=${this.isSubmitting}
                  />
                  <div class="form-hint">Maximum pages (1-10,000)</div>
                  ${this.errors.max_pages
                    ? html`<div class="form-error">${this.errors.max_pages}</div>`
                    : null}
                </div>
              </div>

              <button
                type="button"
                class="advanced-toggle"
                @click=${() => (this.showAdvanced = !this.showAdvanced)}
              >
                ${this.showAdvanced ? '- Hide' : '+ Show'} Advanced Options
              </button>

              ${this.showAdvanced
                ? html`
                    <div class="advanced-section">
                      <div class="form-group">
                        <label class="form-label">Crawl Speed (req/sec)</label>
                        <input
                          type="number"
                          class="form-input ${this.errors.crawl_speed ? 'error' : ''}"
                          .value=${this.formData.crawl_speed?.toString() || '1.0'}
                          @input=${(e: Event) =>
                            this.handleInputChange(
                              'crawl_speed',
                              parseFloat((e.target as HTMLInputElement).value)
                            )}
                          min="0.1"
                          max="10"
                          step="0.1"
                          ?disabled=${this.isSubmitting}
                        />
                        <div class="form-hint">
                          Requests per second limit (0.1-10). Lower values are more polite.
                        </div>
                        ${this.errors.crawl_speed
                          ? html`<div class="form-error">${this.errors.crawl_speed}</div>`
                          : null}
                      </div>

                      <div class="form-group">
                        <div class="form-checkbox">
                          <input
                            type="checkbox"
                            id="respect_robots"
                            .checked=${this.formData.respect_robots_txt}
                            @change=${(e: Event) =>
                              this.handleInputChange(
                                'respect_robots_txt',
                                (e.target as HTMLInputElement).checked
                              )}
                            ?disabled=${this.isSubmitting}
                          />
                          <label for="respect_robots">Respect robots.txt</label>
                        </div>
                        <div class="form-hint" style="margin-left: 1.5rem;">
                          Honor the site's crawling rules
                        </div>
                      </div>

                      <div class="form-group">
                        <div class="form-checkbox">
                          <input
                            type="checkbox"
                            id="use_llm"
                            .checked=${this.formData.use_llm_extraction}
                            @change=${(e: Event) =>
                              this.handleInputChange(
                                'use_llm_extraction',
                                (e.target as HTMLInputElement).checked
                              )}
                            ?disabled=${this.isSubmitting}
                          />
                          <label for="use_llm">Use LLM Extraction</label>
                        </div>
                        <div class="form-hint" style="margin-left: 1.5rem;">
                          Enable AI-powered entity extraction (uses Claude API)
                        </div>
                      </div>
                    </div>
                  `
                : null}
            </div>

            <div class="modal-footer">
              <button
                type="button"
                class="btn btn-secondary"
                @click=${this.handleClose}
                ?disabled=${this.isSubmitting}
              >
                Cancel
              </button>
              <button type="submit" class="btn btn-primary" ?disabled=${this.isSubmitting}>
                ${this.isSubmitting ? 'Creating...' : 'Create Job'}
              </button>
            </div>
          </form>
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'scraping-job-create-modal': ScrapingJobCreateModal
  }
}
