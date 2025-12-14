# Knowledge Mapper - Frontend

Modern, lightweight frontend application built with Vite, Lit, and Tailwind CSS.

## Technology Stack

- **Build Tool**: Vite 5.x - Fast, modern build tool with instant HMR
- **Framework**: Lit 3.x - Lightweight web components library
- **Styling**: Tailwind CSS - Utility-first CSS framework
- **Language**: TypeScript - Type-safe development
- **API Client**: Native fetch with typed wrapper

## Architecture

```
frontend/
├── src/
│   ├── api/              # API client layer
│   │   ├── client.ts     # Base API client
│   │   ├── health.ts     # Health API endpoints
│   │   ├── types.ts      # API type definitions
│   │   └── index.ts      # API exports
│   ├── components/       # Lit web components
│   │   └── health-check.ts
│   ├── main.ts          # Application entry point
│   ├── style.css        # Global styles
│   └── vite-env.d.ts    # Vite type definitions
├── index.html           # HTML entry point
├── Dockerfile           # Multi-stage Docker build
├── nginx.conf           # Production nginx config
└── package.json         # Dependencies and scripts
```

## Features

- **Health Check Component**: Displays backend API health status
- **API Client**: Type-safe API communication with error handling
- **Responsive Design**: Mobile-first, accessible UI
- **Hot Module Replacement**: Instant updates during development
- **Docker Support**: Development and production builds
- **CORS Handling**: Configured for backend communication
- **Environment Configuration**: API URL configuration via environment variables

## Getting Started

### Local Development

1. Install dependencies:
```bash
npm install
```

2. Configure environment (optional):
```bash
cp .env.example .env
# Edit .env to set VITE_API_URL
```

3. Start development server:
```bash
npm run dev
```

The application will be available at `http://localhost:5173`

### Docker Development

```bash
docker build --target development -t knowledge-mapper-frontend:dev .
docker run -p 5173:5173 \
  -e VITE_API_URL=http://localhost:8000 \
  -v $(pwd):/app \
  -v /app/node_modules \
  knowledge-mapper-frontend:dev
```

### Production Build

```bash
npm run build
```

Build output will be in `dist/` directory.

### Docker Production

```bash
docker build --target production -t knowledge-mapper-frontend:prod .
docker run -p 80:80 knowledge-mapper-frontend:prod
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_URL` | Backend API base URL | `http://localhost:8000` |

## Available Scripts

- `npm run dev` - Start development server with HMR
- `npm run build` - Build for production
- `npm run preview` - Preview production build locally
- `npm run lint` - Run ESLint
- `npm run format` - Format code with Prettier
- `npm run test` - Run unit/component tests with Vitest
- `npm run test:ui` - Run tests with Vitest UI
- `npm run test:coverage` - Run tests with coverage report
- `npm run test:e2e` - Run E2E tests with Playwright
- `npm run test:e2e:ui` - Run E2E tests with Playwright UI
- `npm run test:e2e:debug` - Run E2E tests in debug mode

## Testing

The frontend uses a two-tier testing strategy for comprehensive coverage:

### Unit/Component Testing (Vitest)

Fast, isolated tests for components and utilities using Vitest and @open-wc/testing.

**Run tests:**
```bash
npm run test              # Run tests in watch mode
npm run test:ui           # Run with interactive UI
npm run test:coverage     # Run with coverage report
```

**Writing component tests:**
```typescript
import { describe, it, expect, vi } from 'vitest'
import { fixture, html } from '@open-wc/testing'
import './my-component'
import type { MyComponent } from './my-component'

describe('MyComponent', () => {
  it('should render', async () => {
    const el = await fixture<MyComponent>(html`<my-component></my-component>`)
    expect(el).toBeDefined()
    expect(el.shadowRoot).toBeDefined()
  })
})
```

**Test file naming:**
- Place tests next to components: `my-component.test.ts`
- Use `.spec.ts` or `.test.ts` extension

### End-to-End Testing (Playwright)

Integration tests that verify complete user workflows across the application.

**Run tests:**
```bash
npm run test:e2e          # Run E2E tests headless
npm run test:e2e:ui       # Run with Playwright UI
npm run test:e2e:debug    # Debug tests with browser
```

**Writing E2E tests:**
```typescript
import { test, expect } from '@playwright/test'

test.describe('Feature Name', () => {
  test('should do something', async ({ page }) => {
    await page.goto('/')
    const element = page.locator('my-component')
    await expect(element).toBeVisible()
  })
})
```

**Test file location:**
- Place E2E tests in `e2e/` directory
- Use `.spec.ts` extension

### Test Organization

```
frontend/
├── src/
│   ├── components/
│   │   ├── health-check.ts
│   │   └── health-check.test.ts      # Component tests
│   └── test-setup.ts                  # Vitest setup
├── e2e/
│   └── health-check.spec.ts           # E2E tests
├── vite.config.ts                     # Vitest configuration
└── playwright.config.ts               # Playwright configuration
```

### Coverage Goals

- **Components**: 80%+ line coverage
- **Utilities**: 90%+ line coverage
- **Integration**: All critical user paths tested

## Component Development

### Creating a New Component

```typescript
import { LitElement, html, css } from 'lit'
import { customElement, state } from 'lit/decorators.js'

@customElement('my-component')
export class MyComponent extends LitElement {
  static styles = css`
    :host {
      display: block;
    }
  `

  @state()
  private myState = ''

  render() {
    return html`
      <div>My Component</div>
    `
  }
}
```

### Using the API Client

```typescript
import { apiClient } from './api'
import type { ApiResponse } from './api'

// GET request
const response = await apiClient.get<MyDataType>('/endpoint')
if (response.success) {
  console.log(response.data)
} else {
  console.error(response.error)
}

// POST request
const response = await apiClient.post<ResponseType, BodyType>(
  '/endpoint',
  { key: 'value' }
)
```

## API Integration

The frontend communicates with the FastAPI backend through a type-safe API client:

- **Base URL**: Configured via `VITE_API_URL` environment variable
- **CORS**: Handled by backend configuration
- **Error Handling**: All API calls return typed success/error responses
- **Type Safety**: Full TypeScript support for API contracts

### Current Endpoints

- `GET /health` - Backend health check

## Browser Support

- Modern browsers with ES2020 support
- Chrome 80+
- Firefox 75+
- Safari 13.1+
- Edge 80+

## Accessibility

All components follow WCAG 2.1 AA guidelines:

- Semantic HTML
- Keyboard navigation
- ARIA labels and roles
- Focus management
- Color contrast compliance

## Docker Configuration

### Development Stage
- Uses Node 20 Alpine
- Installs dependencies with `npm ci`
- Runs Vite dev server on port 5173
- Supports hot module replacement
- Volume mounting for live code updates

### Production Stage
- Multi-stage build for optimized size
- Builds application with `npm run build`
- Serves static files with nginx
- Optimized caching headers
- Health check endpoint at `/health`

## Next Steps

- Add authentication components
- Implement routing (e.g., using Lit Router)
- Add state management if needed
- Create additional API endpoints
- Implement error boundaries
- Add loading states and skeletons
- Expand test coverage for new components

## Troubleshooting

### Port Already in Use
```bash
# Change port in vite.config.ts or set via CLI
vite --port 3000
```

### Cannot Connect to Backend
- Verify backend is running
- Check `VITE_API_URL` environment variable
- Verify CORS configuration on backend
- Check Docker network configuration

### Hot Reload Not Working in Docker
- Ensure volume mounting is correct
- Verify `usePolling: true` in vite.config.ts
- Check file permissions

## Contributing

1. Follow TypeScript strict mode
2. Use Prettier for code formatting
3. Follow Lit component best practices
4. Keep components small and focused
5. Write accessible, semantic HTML
6. Test across browsers
