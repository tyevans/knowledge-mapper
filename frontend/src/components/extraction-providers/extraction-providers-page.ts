import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { apiClient } from '../../api/client'
import type {
  ExtractionProviderResponse,
  CreateExtractionProviderRequest,
  UpdateExtractionProviderRequest,
  TestConnectionResponse,
  ExtractionProviderType,
} from '../../api/extraction-provider-types'
import {
  PROVIDER_TYPE_LABELS,
  PROVIDER_TYPE_COLORS,
  STATUS_COLORS,
  DEFAULT_MODELS,
  DEFAULT_EMBEDDING_MODELS,
  requiresApiKey,
} from '../../api/extraction-provider-types'

type ModalMode = 'create' | 'edit' | null

/**
 * Extraction Providers Management Page
 *
 * Allows users to manage their extraction providers (OpenAI, Ollama, etc.)
 */
@customElement('extraction-providers-page')
export class ExtractionProvidersPage extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1.5rem;
    }

    .header h2 {
      margin: 0;
      color: #111827;
      font-size: 1.25rem;
    }

    .btn {
      padding: 0.5rem 1rem;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
    }

    .btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .btn-primary {
      background: #1e3a8a;
      border: 1px solid #1e3a8a;
      color: white;
    }

    .btn-primary:hover:not(:disabled) {
      background: #1e40af;
    }

    .btn-secondary {
      background: white;
      border: 1px solid #d1d5db;
      color: #374151;
    }

    .btn-secondary:hover:not(:disabled) {
      background: #f9fafb;
    }

    .btn-danger {
      background: #dc2626;
      border: 1px solid #dc2626;
      color: white;
    }

    .btn-danger:hover:not(:disabled) {
      background: #b91c1c;
    }

    .btn-sm {
      padding: 0.25rem 0.5rem;
      font-size: 0.75rem;
    }

    /* Provider List */
    .providers-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 1rem;
    }

    .provider-card {
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 0.5rem;
      padding: 1rem;
      transition: box-shadow 0.2s;
    }

    .provider-card:hover {
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    .provider-card.default {
      border-color: #fcd34d;
      background: #fffbeb;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 0.75rem;
    }

    .provider-name {
      font-weight: 600;
      color: #111827;
      font-size: 1rem;
      margin: 0;
    }

    .badges {
      display: flex;
      gap: 0.25rem;
      flex-wrap: wrap;
    }

    .badge {
      padding: 0.125rem 0.5rem;
      border-radius: 9999px;
      font-size: 0.625rem;
      font-weight: 500;
      text-transform: uppercase;
    }

    .card-body {
      margin-bottom: 0.75rem;
    }

    .info-row {
      display: flex;
      justify-content: space-between;
      font-size: 0.75rem;
      color: #6b7280;
      margin-bottom: 0.25rem;
    }

    .info-label {
      color: #9ca3af;
    }

    .card-actions {
      display: flex;
      gap: 0.5rem;
      border-top: 1px solid #e5e7eb;
      padding-top: 0.75rem;
    }

    /* Empty State */
    .empty-state {
      text-align: center;
      padding: 3rem 1rem;
      background: white;
      border: 2px dashed #e5e7eb;
      border-radius: 0.5rem;
    }

    .empty-state h3 {
      margin: 0 0 0.5rem;
      color: #374151;
    }

    .empty-state p {
      margin: 0 0 1rem;
      color: #6b7280;
      font-size: 0.875rem;
    }

    /* Loading State */
    .loading {
      text-align: center;
      padding: 2rem;
      color: #6b7280;
    }

    /* Error State */
    .error {
      background: #fef2f2;
      color: #991b1b;
      padding: 1rem;
      border-radius: 0.5rem;
      margin-bottom: 1rem;
    }

    /* Modal */
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

    .modal-header h3 {
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

    .form-input,
    .form-select {
      width: 100%;
      padding: 0.5rem 0.75rem;
      border: 1px solid #d1d5db;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      box-sizing: border-box;
      transition: border-color 0.2s, box-shadow 0.2s;
    }

    .form-input:focus,
    .form-select:focus {
      outline: none;
      border-color: #1e3a8a;
      box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
    }

    .form-input.error,
    .form-select.error {
      border-color: #ef4444;
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

    /* Test Connection Result */
    .test-result {
      padding: 0.75rem;
      border-radius: 0.375rem;
      margin-top: 1rem;
      font-size: 0.875rem;
    }

    .test-result.success {
      background: #d1fae5;
      color: #065f46;
    }

    .test-result.error {
      background: #fee2e2;
      color: #991b1b;
    }

    /* Delete Confirmation */
    .delete-confirm {
      text-align: center;
      padding: 1rem 0;
    }

    .delete-confirm p {
      margin: 0 0 1rem;
      color: #6b7280;
    }

    .delete-confirm .provider-name {
      color: #111827;
      font-weight: 600;
    }
  `

  @state()
  private providers: ExtractionProviderResponse[] = []

  @state()
  private isLoading = true

  @state()
  private error: string | null = null

  @state()
  private modalMode: ModalMode = null

  @state()
  private editingProvider: ExtractionProviderResponse | null = null

  @state()
  private formData: Partial<CreateExtractionProviderRequest> = {}

  @state()
  private formErrors: Record<string, string> = {}

  @state()
  private isSubmitting = false

  @state()
  private testResult: TestConnectionResponse | null = null

  @state()
  private isTesting = false

  @state()
  private deleteConfirmProvider: ExtractionProviderResponse | null = null

  @state()
  private isDeleting = false

  connectedCallback(): void {
    super.connectedCallback()
    this.loadProviders()
  }

  private async loadProviders(): Promise<void> {
    this.isLoading = true
    this.error = null

    try {
      const response = await apiClient.get<ExtractionProviderResponse[]>(
        '/api/v1/extraction-providers'
      )

      if (response.success) {
        this.providers = response.data
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to load providers'
    } finally {
      this.isLoading = false
    }
  }

  private openCreateModal(): void {
    this.modalMode = 'create'
    this.editingProvider = null
    this.formData = {
      name: '',
      provider_type: 'openai',
      config: {},
      default_model: DEFAULT_MODELS.openai,
      embedding_model: DEFAULT_EMBEDDING_MODELS.openai,
      is_active: true,
      is_default: false,
      rate_limit_rpm: 30,
      max_context_length: 8000,
      timeout_seconds: 300,
    }
    this.formErrors = {}
    this.testResult = null
  }

  private openEditModal(provider: ExtractionProviderResponse): void {
    this.modalMode = 'edit'
    this.editingProvider = provider
    this.formData = {
      name: provider.name,
      provider_type: provider.provider_type,
      config: { ...provider.config },
      default_model: provider.default_model || undefined,
      embedding_model: provider.embedding_model || undefined,
      is_active: provider.is_active,
      is_default: provider.is_default,
      rate_limit_rpm: provider.rate_limit_rpm,
      max_context_length: provider.max_context_length,
      timeout_seconds: provider.timeout_seconds,
    }
    this.formErrors = {}
    this.testResult = null
  }

  private closeModal(): void {
    this.modalMode = null
    this.editingProvider = null
    this.formData = {}
    this.formErrors = {}
    this.testResult = null
  }

  private handleProviderTypeChange(type: ExtractionProviderType): void {
    this.formData = {
      ...this.formData,
      provider_type: type,
      default_model: DEFAULT_MODELS[type],
      embedding_model: DEFAULT_EMBEDDING_MODELS[type],
      config: {},
    }
    this.testResult = null
  }

  private handleInputChange(field: string, value: unknown): void {
    if (field.startsWith('config.')) {
      const configField = field.replace('config.', '')
      this.formData = {
        ...this.formData,
        config: { ...this.formData.config, [configField]: value },
      }
    } else {
      this.formData = { ...this.formData, [field]: value }
    }

    if (this.formErrors[field]) {
      const newErrors = { ...this.formErrors }
      delete newErrors[field]
      this.formErrors = newErrors
    }
  }

  private validateForm(): boolean {
    const errors: Record<string, string> = {}

    if (!this.formData.name?.trim()) {
      errors.name = 'Name is required'
    }

    if (!this.formData.provider_type) {
      errors.provider_type = 'Provider type is required'
    }

    if (
      this.formData.provider_type &&
      requiresApiKey(this.formData.provider_type) &&
      !this.formData.config?.api_key
    ) {
      errors['config.api_key'] = 'API key is required for this provider'
    }

    this.formErrors = errors
    return Object.keys(errors).length === 0
  }

  private async handleSubmit(e: Event): Promise<void> {
    e.preventDefault()

    if (!this.validateForm()) {
      return
    }

    this.isSubmitting = true

    try {
      if (this.modalMode === 'create') {
        const response = await apiClient.post<ExtractionProviderResponse>(
          '/api/v1/extraction-providers',
          this.formData
        )

        if (response.success) {
          this.providers = [...this.providers, response.data]
          this.closeModal()
        } else {
          this.formErrors.submit = response.error.message
        }
      } else if (this.modalMode === 'edit' && this.editingProvider) {
        const updateData: UpdateExtractionProviderRequest = { ...this.formData }
        delete (updateData as Record<string, unknown>).provider_type // Can't change type

        const response = await apiClient.patch<ExtractionProviderResponse>(
          `/api/v1/extraction-providers/${this.editingProvider.id}`,
          updateData
        )

        if (response.success) {
          this.providers = this.providers.map((p) =>
            p.id === this.editingProvider!.id ? response.data : p
          )
          this.closeModal()
        } else {
          this.formErrors.submit = response.error.message
        }
      }
    } catch (err) {
      this.formErrors.submit = err instanceof Error ? err.message : 'Failed to save provider'
    } finally {
      this.isSubmitting = false
    }
  }

  private async testConnection(): Promise<void> {
    if (!this.editingProvider) return

    this.isTesting = true
    this.testResult = null

    try {
      const response = await apiClient.post<TestConnectionResponse>(
        `/api/v1/extraction-providers/${this.editingProvider.id}/test`,
        {}
      )

      if (response.success) {
        this.testResult = response.data
      } else {
        this.testResult = {
          success: false,
          message: response.error.message,
          provider: this.editingProvider.provider_type,
          error: response.error.message,
        }
      }
    } catch (err) {
      this.testResult = {
        success: false,
        message: err instanceof Error ? err.message : 'Connection test failed',
        provider: this.editingProvider?.provider_type || 'unknown',
        error: err instanceof Error ? err.message : 'Unknown error',
      }
    } finally {
      this.isTesting = false
    }
  }

  private openDeleteConfirm(provider: ExtractionProviderResponse): void {
    this.deleteConfirmProvider = provider
  }

  private closeDeleteConfirm(): void {
    this.deleteConfirmProvider = null
  }

  private async deleteProvider(): Promise<void> {
    if (!this.deleteConfirmProvider) return

    this.isDeleting = true

    try {
      const response = await apiClient.delete(
        `/api/v1/extraction-providers/${this.deleteConfirmProvider.id}`
      )

      if (response.success) {
        this.providers = this.providers.filter((p) => p.id !== this.deleteConfirmProvider!.id)
        this.closeDeleteConfirm()
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to delete provider'
    } finally {
      this.isDeleting = false
    }
  }

  private renderProviderCard(provider: ExtractionProviderResponse) {
    const typeColor = PROVIDER_TYPE_COLORS[provider.provider_type]
    const statusColor = provider.is_active ? STATUS_COLORS.active : STATUS_COLORS.inactive

    return html`
      <div class="provider-card ${provider.is_default ? 'default' : ''}">
        <div class="card-header">
          <h4 class="provider-name">${provider.name}</h4>
          <div class="badges">
            <span
              class="badge"
              style="background: ${typeColor.background}; color: ${typeColor.color}"
            >
              ${PROVIDER_TYPE_LABELS[provider.provider_type]}
            </span>
            <span
              class="badge"
              style="background: ${statusColor.background}; color: ${statusColor.color}"
            >
              ${provider.is_active ? 'Active' : 'Inactive'}
            </span>
            ${provider.is_default
              ? html`
                  <span
                    class="badge"
                    style="background: ${STATUS_COLORS.default.background}; color: ${STATUS_COLORS
                      .default.color}"
                  >
                    Default
                  </span>
                `
              : null}
          </div>
        </div>

        <div class="card-body">
          <div class="info-row">
            <span class="info-label">Model:</span>
            <span>${provider.default_model || 'Default'}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Rate Limit:</span>
            <span>${provider.rate_limit_rpm} req/min</span>
          </div>
          <div class="info-row">
            <span class="info-label">Timeout:</span>
            <span>${provider.timeout_seconds}s</span>
          </div>
        </div>

        <div class="card-actions">
          <button class="btn btn-secondary btn-sm" @click=${() => this.openEditModal(provider)}>
            Edit
          </button>
          <button class="btn btn-danger btn-sm" @click=${() => this.openDeleteConfirm(provider)}>
            Delete
          </button>
        </div>
      </div>
    `
  }

  private renderModal() {
    if (!this.modalMode) return null

    const isEdit = this.modalMode === 'edit'
    const providerType = this.formData.provider_type as ExtractionProviderType
    const needsApiKey = providerType && requiresApiKey(providerType)

    return html`
      <div class="modal-backdrop" @click=${(e: Event) => e.target === e.currentTarget && this.closeModal()}>
        <div class="modal">
          <div class="modal-header">
            <h3>${isEdit ? 'Edit Provider' : 'Add Extraction Provider'}</h3>
            <button class="close-btn" @click=${this.closeModal}>&times;</button>
          </div>

          <form @submit=${this.handleSubmit}>
            <div class="modal-body">
              ${this.formErrors.submit
                ? html`<div class="error">${this.formErrors.submit}</div>`
                : null}

              <div class="form-group">
                <label class="form-label">
                  Name <span class="required">*</span>
                </label>
                <input
                  type="text"
                  class="form-input ${this.formErrors.name ? 'error' : ''}"
                  .value=${this.formData.name || ''}
                  @input=${(e: Event) =>
                    this.handleInputChange('name', (e.target as HTMLInputElement).value)}
                  placeholder="My OpenAI Provider"
                  ?disabled=${this.isSubmitting}
                />
                ${this.formErrors.name
                  ? html`<div class="form-error">${this.formErrors.name}</div>`
                  : null}
              </div>

              <div class="form-group">
                <label class="form-label">
                  Provider Type <span class="required">*</span>
                </label>
                <select
                  class="form-select ${this.formErrors.provider_type ? 'error' : ''}"
                  .value=${this.formData.provider_type || 'openai'}
                  @change=${(e: Event) =>
                    this.handleProviderTypeChange(
                      (e.target as HTMLSelectElement).value as ExtractionProviderType
                    )}
                  ?disabled=${this.isSubmitting || isEdit}
                >
                  <option value="openai">OpenAI</option>
                  <option value="ollama">Ollama (Local)</option>
                  <option value="anthropic" disabled>Anthropic (Coming Soon)</option>
                </select>
                ${isEdit
                  ? html`<div class="form-hint">Provider type cannot be changed after creation</div>`
                  : null}
              </div>

              ${needsApiKey
                ? html`
                    <div class="form-group">
                      <label class="form-label">
                        API Key <span class="required">*</span>
                      </label>
                      <input
                        type="password"
                        class="form-input ${this.formErrors['config.api_key'] ? 'error' : ''}"
                        .value=${(this.formData.config?.api_key as string) || ''}
                        @input=${(e: Event) =>
                          this.handleInputChange(
                            'config.api_key',
                            (e.target as HTMLInputElement).value
                          )}
                        placeholder="sk-..."
                        ?disabled=${this.isSubmitting}
                      />
                      ${this.formErrors['config.api_key']
                        ? html`<div class="form-error">${this.formErrors['config.api_key']}</div>`
                        : null}
                      <div class="form-hint">
                        Your API key is encrypted at rest and never exposed in responses
                      </div>
                    </div>
                  `
                : html`
                    <div class="form-group">
                      <label class="form-label">Base URL</label>
                      <input
                        type="url"
                        class="form-input"
                        .value=${(this.formData.config?.base_url as string) || ''}
                        @input=${(e: Event) =>
                          this.handleInputChange(
                            'config.base_url',
                            (e.target as HTMLInputElement).value
                          )}
                        placeholder="http://localhost:11434"
                        ?disabled=${this.isSubmitting}
                      />
                      <div class="form-hint">Leave empty to use default Ollama URL</div>
                    </div>
                  `}

              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">Default Model</label>
                  <input
                    type="text"
                    class="form-input"
                    .value=${this.formData.default_model || ''}
                    @input=${(e: Event) =>
                      this.handleInputChange('default_model', (e.target as HTMLInputElement).value)}
                    placeholder=${DEFAULT_MODELS[providerType] || 'gpt-4o'}
                    ?disabled=${this.isSubmitting}
                  />
                </div>

                <div class="form-group">
                  <label class="form-label">Embedding Model</label>
                  <input
                    type="text"
                    class="form-input"
                    .value=${this.formData.embedding_model || ''}
                    @input=${(e: Event) =>
                      this.handleInputChange(
                        'embedding_model',
                        (e.target as HTMLInputElement).value
                      )}
                    placeholder=${DEFAULT_EMBEDDING_MODELS[providerType] || ''}
                    ?disabled=${this.isSubmitting}
                  />
                </div>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">Rate Limit (req/min)</label>
                  <input
                    type="number"
                    class="form-input"
                    .value=${this.formData.rate_limit_rpm?.toString() || '30'}
                    @input=${(e: Event) =>
                      this.handleInputChange(
                        'rate_limit_rpm',
                        parseInt((e.target as HTMLInputElement).value, 10)
                      )}
                    min="1"
                    max="1000"
                    ?disabled=${this.isSubmitting}
                  />
                </div>

                <div class="form-group">
                  <label class="form-label">Timeout (seconds)</label>
                  <input
                    type="number"
                    class="form-input"
                    .value=${this.formData.timeout_seconds?.toString() || '300'}
                    @input=${(e: Event) =>
                      this.handleInputChange(
                        'timeout_seconds',
                        parseInt((e.target as HTMLInputElement).value, 10)
                      )}
                    min="30"
                    max="600"
                    ?disabled=${this.isSubmitting}
                  />
                </div>
              </div>

              <div class="form-group">
                <div class="form-checkbox">
                  <input
                    type="checkbox"
                    id="is_active"
                    .checked=${this.formData.is_active !== false}
                    @change=${(e: Event) =>
                      this.handleInputChange('is_active', (e.target as HTMLInputElement).checked)}
                    ?disabled=${this.isSubmitting}
                  />
                  <label for="is_active">Active</label>
                </div>
              </div>

              <div class="form-group">
                <div class="form-checkbox">
                  <input
                    type="checkbox"
                    id="is_default"
                    .checked=${this.formData.is_default === true}
                    @change=${(e: Event) =>
                      this.handleInputChange('is_default', (e.target as HTMLInputElement).checked)}
                    ?disabled=${this.isSubmitting}
                  />
                  <label for="is_default">Set as default provider</label>
                </div>
                <div class="form-hint" style="margin-left: 1.5rem;">
                  Default provider is used when no provider is specified for a job
                </div>
              </div>

              ${isEdit && this.editingProvider
                ? html`
                    <div style="margin-top: 1rem;">
                      <button
                        type="button"
                        class="btn btn-secondary"
                        @click=${this.testConnection}
                        ?disabled=${this.isTesting}
                      >
                        ${this.isTesting ? 'Testing...' : 'Test Connection'}
                      </button>

                      ${this.testResult
                        ? html`
                            <div class="test-result ${this.testResult.success ? 'success' : 'error'}">
                              ${this.testResult.success
                                ? html`Connection successful! Model available: ${this.testResult.model_available ? 'Yes' : 'No'}`
                                : html`Connection failed: ${this.testResult.error || this.testResult.message}`}
                            </div>
                          `
                        : null}
                    </div>
                  `
                : null}
            </div>

            <div class="modal-footer">
              <button
                type="button"
                class="btn btn-secondary"
                @click=${this.closeModal}
                ?disabled=${this.isSubmitting}
              >
                Cancel
              </button>
              <button type="submit" class="btn btn-primary" ?disabled=${this.isSubmitting}>
                ${this.isSubmitting ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Provider'}
              </button>
            </div>
          </form>
        </div>
      </div>
    `
  }

  private renderDeleteConfirm() {
    if (!this.deleteConfirmProvider) return null

    return html`
      <div class="modal-backdrop" @click=${(e: Event) => e.target === e.currentTarget && this.closeDeleteConfirm()}>
        <div class="modal" style="max-width: 24rem;">
          <div class="modal-header" style="background: #dc2626;">
            <h3>Delete Provider</h3>
            <button class="close-btn" @click=${this.closeDeleteConfirm}>&times;</button>
          </div>

          <div class="modal-body">
            <div class="delete-confirm">
              <p>
                Are you sure you want to delete
                <span class="provider-name">${this.deleteConfirmProvider.name}</span>?
              </p>
              <p>Jobs using this provider will fall back to the default provider.</p>
            </div>
          </div>

          <div class="modal-footer">
            <button
              class="btn btn-secondary"
              @click=${this.closeDeleteConfirm}
              ?disabled=${this.isDeleting}
            >
              Cancel
            </button>
            <button
              class="btn btn-danger"
              @click=${this.deleteProvider}
              ?disabled=${this.isDeleting}
            >
              ${this.isDeleting ? 'Deleting...' : 'Delete'}
            </button>
          </div>
        </div>
      </div>
    `
  }

  render() {
    return html`
      <div class="header">
        <h2>Extraction Providers</h2>
        <button class="btn btn-primary" @click=${this.openCreateModal}>
          + Add Provider
        </button>
      </div>

      ${this.error ? html`<div class="error">${this.error}</div>` : null}

      ${this.isLoading
        ? html`<div class="loading">Loading providers...</div>`
        : this.providers.length === 0
          ? html`
              <div class="empty-state">
                <h3>No Extraction Providers</h3>
                <p>
                  Add an extraction provider to use custom LLM configurations for entity extraction.
                </p>
                <button class="btn btn-primary" @click=${this.openCreateModal}>
                  + Add Your First Provider
                </button>
              </div>
            `
          : html`
              <div class="providers-grid">
                ${this.providers.map((p) => this.renderProviderCard(p))}
              </div>
            `}

      ${this.renderModal()} ${this.renderDeleteConfirm()}
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'extraction-providers-page': ExtractionProvidersPage
  }
}
