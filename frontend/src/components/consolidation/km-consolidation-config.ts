import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { apiClient } from '../../api/client'
import type { ConsolidationConfig, ConsolidationConfigUpdate, FeatureWeightConfig } from '../../api/types'

/**
 * Consolidation configuration component
 *
 * Form for editing consolidation settings with:
 * - Threshold sliders for auto-merge and review
 * - Feature weight configuration
 * - Toggle switches for features
 *
 * @element km-consolidation-config
 * @fires config-saved - When configuration is successfully saved
 */
@customElement('km-consolidation-config')
export class KmConsolidationConfig extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .config-container {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
      overflow: hidden;
    }

    .config-header {
      padding: 1rem 1.5rem;
      background: #1f2937;
      color: white;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .config-title {
      font-size: 1.125rem;
      font-weight: 600;
      margin: 0;
    }

    .config-body {
      padding: 1.5rem;
    }

    .section {
      margin-bottom: 2rem;
    }

    .section:last-child {
      margin-bottom: 0;
    }

    .section-title {
      font-size: 1rem;
      font-weight: 600;
      color: #1f2937;
      margin: 0 0 1rem 0;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid #e5e7eb;
    }

    .form-group {
      margin-bottom: 1.25rem;
    }

    .form-group:last-child {
      margin-bottom: 0;
    }

    .form-label {
      display: block;
      font-size: 0.875rem;
      font-weight: 500;
      color: #374151;
      margin-bottom: 0.5rem;
    }

    .form-hint {
      font-size: 0.75rem;
      color: #6b7280;
      margin-top: 0.25rem;
    }

    .slider-container {
      display: flex;
      align-items: center;
      gap: 1rem;
    }

    .slider {
      flex: 1;
      -webkit-appearance: none;
      appearance: none;
      height: 8px;
      background: #e5e7eb;
      border-radius: 4px;
      outline: none;
    }

    .slider::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: 20px;
      height: 20px;
      background: #1e3a8a;
      border-radius: 50%;
      cursor: pointer;
      transition: background 0.2s;
    }

    .slider::-webkit-slider-thumb:hover {
      background: #1e40af;
    }

    .slider::-moz-range-thumb {
      width: 20px;
      height: 20px;
      background: #1e3a8a;
      border: none;
      border-radius: 50%;
      cursor: pointer;
    }

    .slider-value {
      min-width: 3.5rem;
      text-align: right;
      font-weight: 600;
      color: #374151;
    }

    .toggle-group {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.75rem;
      background: #f9fafb;
      border-radius: 0.375rem;
      margin-bottom: 0.75rem;
    }

    .toggle-group:last-child {
      margin-bottom: 0;
    }

    .toggle-label {
      font-size: 0.875rem;
      color: #374151;
    }

    .toggle {
      position: relative;
      width: 44px;
      height: 24px;
    }

    .toggle input {
      opacity: 0;
      width: 0;
      height: 0;
    }

    .toggle-slider {
      position: absolute;
      cursor: pointer;
      inset: 0;
      background: #d1d5db;
      border-radius: 24px;
      transition: 0.3s;
    }

    .toggle-slider::before {
      position: absolute;
      content: '';
      height: 18px;
      width: 18px;
      left: 3px;
      bottom: 3px;
      background: white;
      border-radius: 50%;
      transition: 0.3s;
    }

    .toggle input:checked + .toggle-slider {
      background: #1e3a8a;
    }

    .toggle input:checked + .toggle-slider::before {
      transform: translateX(20px);
    }

    .toggle input:focus + .toggle-slider {
      box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.2);
    }

    .weights-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
    }

    .weight-item {
      padding: 0.75rem;
      background: #f9fafb;
      border-radius: 0.375rem;
    }

    .weight-label {
      font-size: 0.75rem;
      color: #6b7280;
      margin-bottom: 0.5rem;
    }

    .text-input {
      width: 100%;
      padding: 0.5rem;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      font-size: 0.875rem;
    }

    .text-input:focus {
      outline: none;
      border-color: #1e3a8a;
      box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
    }

    .number-input {
      width: 100%;
      padding: 0.5rem;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      font-size: 0.875rem;
    }

    .number-input:focus {
      outline: none;
      border-color: #1e3a8a;
      box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
    }

    .config-footer {
      padding: 1rem 1.5rem;
      background: #f9fafb;
      border-top: 1px solid #e5e7eb;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .save-btn {
      padding: 0.5rem 1.5rem;
      background: #1e3a8a;
      color: white;
      border: none;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }

    .save-btn:hover:not(:disabled) {
      background: #1e40af;
    }

    .save-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .reset-btn {
      padding: 0.5rem 1rem;
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      color: #374151;
      cursor: pointer;
      transition: all 0.2s;
    }

    .reset-btn:hover {
      background: #f9fafb;
      border-color: #d1d5db;
    }

    .loading {
      text-align: center;
      padding: 3rem;
      color: #6b7280;
    }

    .error {
      background: #fef2f2;
      color: #991b1b;
      padding: 0.75rem;
      border-radius: 0.375rem;
      margin-bottom: 1rem;
      font-size: 0.875rem;
    }

    .success {
      background: #d1fae5;
      color: #065f46;
      padding: 0.75rem;
      border-radius: 0.375rem;
      margin-bottom: 1rem;
      font-size: 0.875rem;
    }

    .last-updated {
      font-size: 0.75rem;
      color: #6b7280;
    }

    .validation-error {
      color: #dc2626;
      font-size: 0.75rem;
      margin-top: 0.25rem;
    }
  `

  @state()
  private config: ConsolidationConfig | null = null

  @state()
  private isLoading = true

  @state()
  private isSaving = false

  @state()
  private error: string | null = null

  @state()
  private success: string | null = null

  // Form state
  @state()
  private autoMergeThreshold = 0.9

  @state()
  private reviewThreshold = 0.5

  @state()
  private maxBlockSize = 1000

  @state()
  private enableEmbeddingSimilarity = true

  @state()
  private enableGraphSimilarity = true

  @state()
  private enableAutoConsolidation = false

  @state()
  private embeddingModel = 'text-embedding-3-small'

  @state()
  private featureWeights: FeatureWeightConfig = {
    jaro_winkler: 0.3,
    normalized_exact: 0.4,
    type_match: 0.2,
    same_page_bonus: 0.1,
    embedding_cosine: 0.5,
    graph_neighborhood: 0.3,
  }

  connectedCallback(): void {
    super.connectedCallback()
    this.loadConfig()
  }

  private async loadConfig(): Promise<void> {
    this.isLoading = true
    this.error = null

    try {
      const response = await apiClient.get<ConsolidationConfig>('/api/v1/consolidation/config')

      if (response.success) {
        this.config = response.data
        this.populateForm(response.data)
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to load configuration'
    } finally {
      this.isLoading = false
    }
  }

  private populateForm(config: ConsolidationConfig): void {
    this.autoMergeThreshold = config.auto_merge_threshold
    this.reviewThreshold = config.review_threshold
    this.maxBlockSize = config.max_block_size
    this.enableEmbeddingSimilarity = config.enable_embedding_similarity
    this.enableGraphSimilarity = config.enable_graph_similarity
    this.enableAutoConsolidation = config.enable_auto_consolidation
    this.embeddingModel = config.embedding_model
    this.featureWeights = { ...config.feature_weights }
  }

  private validateForm(): string | null {
    if (this.reviewThreshold >= this.autoMergeThreshold) {
      return 'Review threshold must be less than auto-merge threshold'
    }
    if (this.maxBlockSize < 10 || this.maxBlockSize > 10000) {
      return 'Max block size must be between 10 and 10,000'
    }
    return null
  }

  private async saveConfig(): Promise<void> {
    const validationError = this.validateForm()
    if (validationError) {
      this.error = validationError
      return
    }

    this.isSaving = true
    this.error = null
    this.success = null

    try {
      const update: ConsolidationConfigUpdate = {
        auto_merge_threshold: this.autoMergeThreshold,
        review_threshold: this.reviewThreshold,
        max_block_size: this.maxBlockSize,
        enable_embedding_similarity: this.enableEmbeddingSimilarity,
        enable_graph_similarity: this.enableGraphSimilarity,
        enable_auto_consolidation: this.enableAutoConsolidation,
        embedding_model: this.embeddingModel,
        feature_weights: this.featureWeights,
      }

      const response = await apiClient.put<ConsolidationConfig>(
        '/api/v1/consolidation/config',
        update
      )

      if (response.success) {
        this.config = response.data
        this.success = 'Configuration saved successfully'
        this.dispatchEvent(
          new CustomEvent('config-saved', {
            detail: { config: response.data },
            bubbles: true,
            composed: true,
          })
        )
        // Clear success message after 3 seconds
        setTimeout(() => (this.success = null), 3000)
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to save configuration'
    } finally {
      this.isSaving = false
    }
  }

  private resetToDefaults(): void {
    this.autoMergeThreshold = 0.9
    this.reviewThreshold = 0.5
    this.maxBlockSize = 1000
    this.enableEmbeddingSimilarity = true
    this.enableGraphSimilarity = true
    this.enableAutoConsolidation = false
    this.embeddingModel = 'text-embedding-3-small'
    this.featureWeights = {
      jaro_winkler: 0.3,
      normalized_exact: 0.4,
      type_match: 0.2,
      same_page_bonus: 0.1,
      embedding_cosine: 0.5,
      graph_neighborhood: 0.3,
    }
  }

  private handleWeightChange(key: keyof FeatureWeightConfig, value: number): void {
    this.featureWeights = { ...this.featureWeights, [key]: value }
  }

  private formatDate(dateStr: string | null): string {
    if (!dateStr) return 'Never'
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  render() {
    if (this.isLoading) {
      return html`
        <div class="config-container">
          <div class="config-header">
            <h2 class="config-title">Consolidation Settings</h2>
          </div>
          <div class="loading">Loading configuration...</div>
        </div>
      `
    }

    return html`
      <div class="config-container">
        <div class="config-header">
          <h2 class="config-title">Consolidation Settings</h2>
        </div>

        <div class="config-body">
          ${this.error ? html`<div class="error">${this.error}</div>` : null}
          ${this.success ? html`<div class="success">${this.success}</div>` : null}

          <!-- Thresholds Section -->
          <div class="section">
            <h3 class="section-title">Thresholds</h3>

            <div class="form-group">
              <label class="form-label">Auto-Merge Threshold</label>
              <div class="slider-container">
                <input
                  type="range"
                  class="slider"
                  min="0"
                  max="1"
                  step="0.05"
                  .value=${String(this.autoMergeThreshold)}
                  @input=${(e: Event) =>
                    (this.autoMergeThreshold = parseFloat((e.target as HTMLInputElement).value))}
                  aria-label="Auto-merge threshold"
                />
                <span class="slider-value">${Math.round(this.autoMergeThreshold * 100)}%</span>
              </div>
              <p class="form-hint">
                Candidates above this threshold will be automatically merged
              </p>
            </div>

            <div class="form-group">
              <label class="form-label">Review Threshold</label>
              <div class="slider-container">
                <input
                  type="range"
                  class="slider"
                  min="0"
                  max="1"
                  step="0.05"
                  .value=${String(this.reviewThreshold)}
                  @input=${(e: Event) =>
                    (this.reviewThreshold = parseFloat((e.target as HTMLInputElement).value))}
                  aria-label="Review threshold"
                />
                <span class="slider-value">${Math.round(this.reviewThreshold * 100)}%</span>
              </div>
              <p class="form-hint">
                Candidates above this threshold will be queued for human review
              </p>
              ${this.reviewThreshold >= this.autoMergeThreshold
                ? html`<p class="validation-error">Must be less than auto-merge threshold</p>`
                : null}
            </div>

            <div class="form-group">
              <label class="form-label">Max Block Size</label>
              <input
                type="number"
                class="number-input"
                min="10"
                max="10000"
                .value=${String(this.maxBlockSize)}
                @input=${(e: Event) =>
                  (this.maxBlockSize = parseInt((e.target as HTMLInputElement).value) || 1000)}
                aria-label="Maximum block size"
              />
              <p class="form-hint">
                Maximum number of entities in a blocking group
              </p>
            </div>
          </div>

          <!-- Features Section -->
          <div class="section">
            <h3 class="section-title">Features</h3>

            <div class="toggle-group">
              <span class="toggle-label">Enable Embedding Similarity</span>
              <label class="toggle">
                <input
                  type="checkbox"
                  .checked=${this.enableEmbeddingSimilarity}
                  @change=${(e: Event) =>
                    (this.enableEmbeddingSimilarity = (e.target as HTMLInputElement).checked)}
                />
                <span class="toggle-slider"></span>
              </label>
            </div>

            <div class="toggle-group">
              <span class="toggle-label">Enable Graph Neighborhood Similarity</span>
              <label class="toggle">
                <input
                  type="checkbox"
                  .checked=${this.enableGraphSimilarity}
                  @change=${(e: Event) =>
                    (this.enableGraphSimilarity = (e.target as HTMLInputElement).checked)}
                />
                <span class="toggle-slider"></span>
              </label>
            </div>

            <div class="toggle-group">
              <span class="toggle-label">Enable Auto-Consolidation on Extraction</span>
              <label class="toggle">
                <input
                  type="checkbox"
                  .checked=${this.enableAutoConsolidation}
                  @change=${(e: Event) =>
                    (this.enableAutoConsolidation = (e.target as HTMLInputElement).checked)}
                />
                <span class="toggle-slider"></span>
              </label>
            </div>

            <div class="form-group" style="margin-top: 1rem;">
              <label class="form-label">Embedding Model</label>
              <input
                type="text"
                class="text-input"
                .value=${this.embeddingModel}
                @input=${(e: Event) =>
                  (this.embeddingModel = (e.target as HTMLInputElement).value)}
                placeholder="text-embedding-3-small"
              />
            </div>
          </div>

          <!-- Feature Weights Section -->
          <div class="section">
            <h3 class="section-title">Feature Weights</h3>
            <p class="form-hint" style="margin-bottom: 1rem;">
              Adjust the weight of each feature in the combined similarity score (0-1)
            </p>

            <div class="weights-grid">
              <div class="weight-item">
                <div class="weight-label">Jaro-Winkler</div>
                <div class="slider-container">
                  <input
                    type="range"
                    class="slider"
                    min="0"
                    max="1"
                    step="0.05"
                    .value=${String(this.featureWeights.jaro_winkler)}
                    @input=${(e: Event) =>
                      this.handleWeightChange(
                        'jaro_winkler',
                        parseFloat((e.target as HTMLInputElement).value)
                      )}
                  />
                  <span class="slider-value">${this.featureWeights.jaro_winkler.toFixed(2)}</span>
                </div>
              </div>

              <div class="weight-item">
                <div class="weight-label">Normalized Exact</div>
                <div class="slider-container">
                  <input
                    type="range"
                    class="slider"
                    min="0"
                    max="1"
                    step="0.05"
                    .value=${String(this.featureWeights.normalized_exact)}
                    @input=${(e: Event) =>
                      this.handleWeightChange(
                        'normalized_exact',
                        parseFloat((e.target as HTMLInputElement).value)
                      )}
                  />
                  <span class="slider-value">${this.featureWeights.normalized_exact.toFixed(2)}</span>
                </div>
              </div>

              <div class="weight-item">
                <div class="weight-label">Type Match</div>
                <div class="slider-container">
                  <input
                    type="range"
                    class="slider"
                    min="0"
                    max="1"
                    step="0.05"
                    .value=${String(this.featureWeights.type_match)}
                    @input=${(e: Event) =>
                      this.handleWeightChange(
                        'type_match',
                        parseFloat((e.target as HTMLInputElement).value)
                      )}
                  />
                  <span class="slider-value">${this.featureWeights.type_match.toFixed(2)}</span>
                </div>
              </div>

              <div class="weight-item">
                <div class="weight-label">Same Page Bonus</div>
                <div class="slider-container">
                  <input
                    type="range"
                    class="slider"
                    min="0"
                    max="1"
                    step="0.05"
                    .value=${String(this.featureWeights.same_page_bonus)}
                    @input=${(e: Event) =>
                      this.handleWeightChange(
                        'same_page_bonus',
                        parseFloat((e.target as HTMLInputElement).value)
                      )}
                  />
                  <span class="slider-value">${this.featureWeights.same_page_bonus.toFixed(2)}</span>
                </div>
              </div>

              <div class="weight-item">
                <div class="weight-label">Embedding Cosine</div>
                <div class="slider-container">
                  <input
                    type="range"
                    class="slider"
                    min="0"
                    max="1"
                    step="0.05"
                    .value=${String(this.featureWeights.embedding_cosine)}
                    @input=${(e: Event) =>
                      this.handleWeightChange(
                        'embedding_cosine',
                        parseFloat((e.target as HTMLInputElement).value)
                      )}
                  />
                  <span class="slider-value">${this.featureWeights.embedding_cosine.toFixed(2)}</span>
                </div>
              </div>

              <div class="weight-item">
                <div class="weight-label">Graph Neighborhood</div>
                <div class="slider-container">
                  <input
                    type="range"
                    class="slider"
                    min="0"
                    max="1"
                    step="0.05"
                    .value=${String(this.featureWeights.graph_neighborhood)}
                    @input=${(e: Event) =>
                      this.handleWeightChange(
                        'graph_neighborhood',
                        parseFloat((e.target as HTMLInputElement).value)
                      )}
                  />
                  <span class="slider-value">${this.featureWeights.graph_neighborhood.toFixed(2)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="config-footer">
          <div>
            <button class="reset-btn" @click=${this.resetToDefaults}>
              Reset to Defaults
            </button>
            <span class="last-updated">
              Last updated: ${this.formatDate(this.config?.updated_at ?? null)}
            </span>
          </div>
          <button
            class="save-btn"
            @click=${this.saveConfig}
            ?disabled=${this.isSaving || this.reviewThreshold >= this.autoMergeThreshold}
          >
            ${this.isSaving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'km-consolidation-config': KmConsolidationConfig
  }
}
