import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'
import { authStore, type AuthState } from '../auth'
import { apiClient } from '../api/client'

interface PublicTodo {
  id: string
  title: string
  description: string | null
  completed: boolean
  created_at: string
}

interface UserTodo extends PublicTodo {
  user_id: string
  tenant_id: string
  updated_at: string
}

/**
 * Todo List Component
 *
 * Shows public todos for unauthenticated users,
 * and personal todos for authenticated users with CRUD functionality.
 */
@customElement('todo-list')
export class TodoList extends LitElement {
  static styles = css`
    :host {
      display: block;
    }

    .card {
      background: white;
      border-radius: 0.5rem;
      box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
      overflow: hidden;
    }

    .card-header {
      background: #1f2937;
      color: white;
      padding: 1rem 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .card-header h2 {
      margin: 0;
      font-size: 1.125rem;
    }

    .badge {
      background: rgba(255, 255, 255, 0.2);
      padding: 0.25rem 0.5rem;
      border-radius: 0.25rem;
      font-size: 0.75rem;
    }

    .card-body {
      padding: 1.5rem;
    }

    .todo-form {
      display: flex;
      gap: 0.5rem;
      margin-bottom: 1rem;
    }

    .todo-form input {
      flex: 1;
      padding: 0.5rem;
      border: 1px solid #e5e7eb;
      border-radius: 0.375rem;
      font-size: 0.875rem;
    }

    .todo-form input:focus {
      outline: none;
      border-color: #667eea;
      box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }

    .todo-form button {
      padding: 0.5rem 1rem;
      background: #667eea;
      color: white;
      border: none;
      border-radius: 0.375rem;
      cursor: pointer;
      font-size: 0.875rem;
    }

    .todo-form button:hover {
      background: #5a67d8;
    }

    .todo-form button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    .todo-list {
      list-style: none;
      padding: 0;
      margin: 0;
    }

    .todo-item {
      display: flex;
      align-items: flex-start;
      gap: 0.75rem;
      padding: 0.75rem 0;
      border-bottom: 1px solid #e5e7eb;
    }

    .todo-item:last-child {
      border-bottom: none;
    }

    .todo-checkbox {
      margin-top: 0.125rem;
      width: 1.25rem;
      height: 1.25rem;
      cursor: pointer;
    }

    .todo-content {
      flex: 1;
    }

    .todo-title {
      font-weight: 500;
      color: #374151;
    }

    .todo-title.completed {
      text-decoration: line-through;
      color: #9ca3af;
    }

    .todo-description {
      font-size: 0.75rem;
      color: #6b7280;
      margin-top: 0.25rem;
    }

    .todo-actions {
      display: flex;
      gap: 0.5rem;
    }

    .delete-btn {
      padding: 0.25rem 0.5rem;
      background: transparent;
      color: #dc2626;
      border: 1px solid #dc2626;
      border-radius: 0.25rem;
      cursor: pointer;
      font-size: 0.75rem;
    }

    .delete-btn:hover {
      background: #dc2626;
      color: white;
    }

    .empty-state {
      text-align: center;
      padding: 2rem;
      color: #6b7280;
    }

    .loading {
      text-align: center;
      padding: 2rem;
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

    .auth-hint {
      text-align: center;
      padding: 1rem;
      background: #f3f4f6;
      border-radius: 0.375rem;
      color: #6b7280;
      font-size: 0.875rem;
      margin-top: 1rem;
    }
  `

  @state()
  private authState: AuthState = {
    user: null,
    isAuthenticated: false,
    isLoading: true,
    error: null,
  }

  @state()
  private publicTodos: PublicTodo[] = []

  @state()
  private userTodos: UserTodo[] = []

  @state()
  private isLoading = true

  @state()
  private error: string | null = null

  @state()
  private newTodoTitle = ''

  @state()
  private isCreating = false

  private unsubscribe?: () => void

  connectedCallback(): void {
    super.connectedCallback()
    this.unsubscribe = authStore.subscribe((state) => {
      const wasAuthenticated = this.authState.isAuthenticated
      this.authState = state

      // Reload todos when auth state changes
      if (!state.isLoading && state.isAuthenticated !== wasAuthenticated) {
        this.loadTodos()
      }
    })
    this.loadTodos()
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.unsubscribe?.()
  }

  private async loadTodos(): Promise<void> {
    this.isLoading = true
    this.error = null

    try {
      // Always load public todos
      const publicResponse = await apiClient.get<PublicTodo[]>('/api/v1/todos/public', {
        authenticated: false,
      })

      if (publicResponse.success) {
        this.publicTodos = publicResponse.data
      } else {
        this.error = publicResponse.error.message
      }

      // Load user todos if authenticated
      if (this.authState.isAuthenticated) {
        const userResponse = await apiClient.get<UserTodo[]>('/api/v1/todos/')

        if (userResponse.success) {
          this.userTodos = userResponse.data
        } else if (userResponse.error.status !== 401) {
          this.error = userResponse.error.message
        }
      } else {
        this.userTodos = []
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to load todos'
    } finally {
      this.isLoading = false
    }
  }

  private async createTodo(): Promise<void> {
    if (!this.newTodoTitle.trim()) return

    this.isCreating = true
    this.error = null

    try {
      const response = await apiClient.post<UserTodo>('/api/v1/todos/', {
        title: this.newTodoTitle.trim(),
        completed: false,
      })

      if (response.success) {
        this.userTodos = [...this.userTodos, response.data]
        this.newTodoTitle = ''
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to create todo'
    } finally {
      this.isCreating = false
    }
  }

  private async toggleTodo(todo: UserTodo): Promise<void> {
    try {
      const response = await apiClient.put<UserTodo>(`/api/v1/todos/${todo.id}`, {
        completed: !todo.completed,
      })

      if (response.success) {
        this.userTodos = this.userTodos.map((t) =>
          t.id === todo.id ? response.data : t
        )
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to update todo'
    }
  }

  private async deleteTodo(todo: UserTodo): Promise<void> {
    try {
      const response = await apiClient.delete(`/api/v1/todos/${todo.id}`)

      if (response.success) {
        this.userTodos = this.userTodos.filter((t) => t.id !== todo.id)
      } else {
        this.error = response.error.message
      }
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to delete todo'
    }
  }

  private handleKeyDown(e: KeyboardEvent): void {
    if (e.key === 'Enter') {
      this.createTodo()
    }
  }

  private renderTodoForm() {
    if (!this.authState.isAuthenticated) {
      return null
    }

    return html`
      <div class="todo-form">
        <input
          type="text"
          placeholder="Add a new todo..."
          .value=${this.newTodoTitle}
          @input=${(e: Event) =>
            (this.newTodoTitle = (e.target as HTMLInputElement).value)}
          @keydown=${this.handleKeyDown}
          ?disabled=${this.isCreating}
        />
        <button @click=${this.createTodo} ?disabled=${this.isCreating || !this.newTodoTitle.trim()}>
          ${this.isCreating ? 'Adding...' : 'Add'}
        </button>
      </div>
    `
  }

  private renderPublicTodos() {
    return html`
      <ul class="todo-list">
        ${this.publicTodos.map(
          (todo) => html`
            <li class="todo-item">
              <input
                type="checkbox"
                class="todo-checkbox"
                .checked=${todo.completed}
                disabled
              />
              <div class="todo-content">
                <div class="todo-title ${todo.completed ? 'completed' : ''}">
                  ${todo.title}
                </div>
                ${todo.description
                  ? html`<div class="todo-description">${todo.description}</div>`
                  : null}
              </div>
            </li>
          `
        )}
      </ul>
      <div class="auth-hint">
        Log in to create your own todos
      </div>
    `
  }

  private renderUserTodos() {
    if (this.userTodos.length === 0) {
      return html`
        <div class="empty-state">
          No todos yet. Add your first one above!
        </div>
      `
    }

    return html`
      <ul class="todo-list">
        ${this.userTodos.map(
          (todo) => html`
            <li class="todo-item">
              <input
                type="checkbox"
                class="todo-checkbox"
                .checked=${todo.completed}
                @change=${() => this.toggleTodo(todo)}
              />
              <div class="todo-content">
                <div class="todo-title ${todo.completed ? 'completed' : ''}">
                  ${todo.title}
                </div>
                ${todo.description
                  ? html`<div class="todo-description">${todo.description}</div>`
                  : null}
              </div>
              <div class="todo-actions">
                <button class="delete-btn" @click=${() => this.deleteTodo(todo)}>
                  Delete
                </button>
              </div>
            </li>
          `
        )}
      </ul>
    `
  }

  render() {
    const { isAuthenticated, isLoading: authLoading } = this.authState

    return html`
      <div class="card">
        <div class="card-header">
          <h2>${isAuthenticated ? 'Your Todos' : 'Example Todos'}</h2>
          <span class="badge">
            ${isAuthenticated ? 'Authenticated' : 'Public'}
          </span>
        </div>
        <div class="card-body">
          ${this.error ? html`<div class="error">${this.error}</div>` : null}

          ${this.renderTodoForm()}

          ${this.isLoading || authLoading
            ? html`<div class="loading">Loading todos...</div>`
            : isAuthenticated
              ? this.renderUserTodos()
              : this.renderPublicTodos()}
        </div>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'todo-list': TodoList
  }
}
