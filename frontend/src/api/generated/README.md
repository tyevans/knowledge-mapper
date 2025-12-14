# Generated API Client

This directory contains TypeScript API client code auto-generated from the backend OpenAPI specification using [OpenAPI Generator](https://openapi-generator.tech/).

## Quick Start

```bash
# From project root (requires backend running)
./scripts/generate-api-client.sh

# From frontend directory
npm run generate:api:fetch
```

## Regeneration

To regenerate the client after backend API changes:

```bash
# Option 1: From project root (recommended)
# Fetches spec from running backend and generates client
./scripts/generate-api-client.sh

# Option 2: From frontend directory
# Uses existing spec file (backend/openapi.json)
npm run generate:api

# Option 3: From frontend directory
# Fetches spec from running backend via shell script
npm run generate:api:fetch

# Validate spec only (no generation)
npm run generate:api:validate
```

## Usage

### Basic Setup

```typescript
import { Configuration, DefaultApi } from './generated'

const config = new Configuration({
  basePath: import.meta.env.VITE_API_URL || 'http://localhost:8000',
})

const api = new DefaultApi(config)

// Make API calls
const healthResponse = await api.healthCheck()
```

### With Authentication

The Configuration class supports an `accessToken` callback for automatic authentication:

```typescript
import { Configuration, DefaultApi } from './generated'
import { authService } from '../auth'

const config = new Configuration({
  basePath: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  accessToken: async () => {
    const token = await authService.getAccessToken()
    return token || ''
  },
})

const api = new DefaultApi(config)

// All requests automatically include Authorization header
const user = await api.getMe()
```

### Type-Safe Responses

```typescript
// Types are automatically generated from OpenAPI schemas
import type { HealthCheckResponse, UserResponse } from './generated'

const health: HealthCheckResponse = await api.healthCheck()
const user: UserResponse = await api.getMe()
```

### Error Handling

```typescript
import { ResponseError } from './generated'

try {
  const result = await api.createResource({ body: data })
  console.log('Created:', result)
} catch (error) {
  if (error instanceof ResponseError) {
    console.error(`API Error: ${error.response.status}`)
    const body = await error.response.json()
    console.error('Details:', body.detail)
  } else {
    console.error('Network error:', error)
  }
}
```

### Using with Data Providers

Example data provider pattern for Lit components:

```typescript
import { Configuration, DefaultApi, type Todo } from './generated'

export class TodoDataProvider {
  private api: DefaultApi

  constructor(config: Configuration) {
    this.api = new DefaultApi(config)
  }

  async fetchTodos(): Promise<Todo[]> {
    return this.api.listTodos()
  }

  async createTodo(title: string, description?: string): Promise<Todo> {
    return this.api.createTodo({
      createTodoRequest: { title, description },
    })
  }

  async updateTodo(id: string, updates: Partial<Todo>): Promise<Todo> {
    return this.api.updateTodo({
      todoId: id,
      updateTodoRequest: updates,
    })
  }

  async deleteTodo(id: string): Promise<void> {
    await this.api.deleteTodo({ todoId: id })
  }
}
```

## Coexistence with Hand-Written Client

The generated client can coexist with the hand-written `client.ts`:

| Client | Use Case |
|--------|----------|
| **Generated** (`./generated`) | Type-safe API calls with full IDE support, automatic type generation |
| **Hand-written** (`./client.ts`) | Custom logic, error handling patterns, simplified response types |

### Migration Strategy

1. **Phase 1**: Use both clients side-by-side
   ```typescript
   // Old code continues to work
   import { apiClient } from './api/client'
   const response = await apiClient.get<Todo[]>('/api/v1/todos')

   // New code uses generated client
   import { DefaultApi, Configuration } from './api/generated'
   const api = new DefaultApi(config)
   const todos = await api.listTodos()
   ```

2. **Phase 2**: Gradually migrate endpoints to generated client
3. **Phase 3**: Deprecate hand-written client (optional)

### Choosing Between Clients

Use the **generated client** when:
- You want full type safety from OpenAPI schemas
- You're implementing new features
- You want IDE autocompletion for API methods

Use the **hand-written client** when:
- You need custom error handling wrappers
- You have specific retry/caching logic
- You're working with legacy code

## Customization

### Preserving Custom Files

Files listed in `.openapi-generator-ignore` are preserved during regeneration.

To customize generated code:
1. Add the file path to `.openapi-generator-ignore`
2. Modify the file as needed
3. Re-run generation (your changes are preserved)

Example `.openapi-generator-ignore`:
```
# Preserve custom runtime modifications
runtime.ts

# Preserve custom model extensions
models/UserExtensions.ts
```

### Configuration Options

Edit `frontend/openapitools.json` to customize generation:

```json
{
  "generator-cli": {
    "generators": {
      "typescript-fetch": {
        "additionalProperties": {
          "supportsES6": true,           // Use ES6+ features
          "typescriptThreePlus": true,   // TypeScript 3+ features
          "withInterfaces": true,        // Generate interfaces
          "useSingleRequestParameter": true,  // Single param object
          "enumPropertyNaming": "original"    // Preserve enum names
        }
      }
    }
  }
}
```

## Directory Structure

After generation, this directory contains:

```
generated/
  apis/             # API classes grouped by OpenAPI tags
    DefaultApi.ts   # Default API operations
    AuthApi.ts      # Authentication operations (if tagged)
    TodosApi.ts     # Todo operations (if tagged)
  models/           # TypeScript interfaces from OpenAPI schemas
    HealthCheckResponse.ts
    Todo.ts
    CreateTodoRequest.ts
    ...
  runtime.ts        # Fetch configuration and helpers
  index.ts          # Re-exports all APIs and models
  README.md         # This file (preserved during regeneration)
```

## Troubleshooting

### Backend not running

```
Error: Backend is not running at http://localhost:8000
```

Start backend:
```bash
./scripts/docker-dev.sh up
```

### Java not found

OpenAPI Generator requires Java 11+:

```bash
# macOS
brew install openjdk@11

# Ubuntu
sudo apt-get install openjdk-11-jdk

# Verify installation
java -version
```

### Validation errors

```bash
# Validate OpenAPI spec
npm run generate:api:validate

# Or from project root
./scripts/generate-api-client.sh --validate
```

### TypeScript errors in generated code

If generated code has TypeScript errors:

1. Check that the OpenAPI spec is valid
2. Ensure backend schemas are properly defined
3. Try regenerating with a clean slate:
   ```bash
   rm -rf src/api/generated/*
   npm run generate:api:fetch
   ```

### CORS issues

If you see CORS errors when calling the API:

1. Ensure the backend CORS configuration includes your frontend origin
2. Check that cookies/credentials are properly configured
3. Verify the `basePath` in Configuration matches the backend URL

## Related Files

- `frontend/openapitools.json` - Generator configuration
- `frontend/.openapi-generator-ignore` - Files to preserve
- `scripts/generate-api-client.sh` - Generation script
- `backend/openapi.json` - OpenAPI specification (generated)
- `frontend/src/api/client.ts` - Hand-written API client

## Further Reading

- [OpenAPI Generator Documentation](https://openapi-generator.tech/docs/generators/typescript-fetch)
- [OpenAPI Specification](https://swagger.io/specification/)
- [TypeScript Fetch Generator Options](https://openapi-generator.tech/docs/generators/typescript-fetch#config-options)
