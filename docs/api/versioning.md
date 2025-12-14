# API Versioning Strategy

This document defines the API versioning strategy for Knowledge Mapper.

## Overview

Knowledge Mapper uses **URL path-based versioning** for its REST API. All API endpoints include a version prefix in the URL path.

**Current Version:** v1
**Base URL:** `/api/v1`
**Full Example:** `https://api.example.com/api/v1/health`

## Table of Contents

- [Versioning Approach](#versioning-approach)
- [Version Format](#version-format)
- [Versioning Policy](#versioning-policy)
- [Breaking Changes](#breaking-changes)
- [Version Negotiation](#version-negotiation)
- [Client Migration](#client-migration)
- [Implementation Guidelines](#implementation-guidelines)
- [Documentation](#documentation)
- [Related Documentation](#related-documentation)

## Versioning Approach

### Why URL Path Versioning?

We chose URL path versioning over alternatives for these reasons:

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **URL Path** (`/api/v1/`) | Simple, visible, cacheable | URL changes between versions | **Selected** |
| Header (`Accept-Version`) | Clean URLs | Hidden, harder to test | Not selected |
| Query param (`?version=1`) | Flexible | Easy to forget, caching issues | Not selected |
| Content negotiation | RESTful | Complex, tooling issues | Not selected |

**Key benefits of URL path versioning:**

- **Visibility**: Immediately visible in logs, documentation, and debugging
- **Routing**: Easy to route at load balancer level
- **Testing**: Simple to test with curl/browser
- **Separation**: Clear separation of version-specific code
- **Caching**: CDN/cache friendly (different URLs = different cache entries)

## Version Format

Versions follow this format:

```
/api/v{MAJOR}/
```

- **MAJOR**: Incremented for breaking changes only
- Minor and patch changes do not create new versions

Examples:
- `/api/v1/users` - Version 1
- `/api/v2/users` - Version 2 (breaking changes)

### Rationale

Major-only versioning in URLs keeps the version scheme simple while aligning with the purpose of API versioning: managing breaking changes. Non-breaking enhancements and bug fixes can be released without version changes.

## Versioning Policy

### Supported Versions

| Version | Status | Release Date | End of Support |
|---------|--------|--------------|----------------|
| v1 | **Current** | Initial Release | - |

### Support Timeline

- **Current version (N)**: Fully supported with new features and bug fixes
- **Previous version (N-1)**: Bug fixes and security patches only, deprecated
- **Older versions (N-2+)**: Unsupported, may be removed

**Minimum support period**: Each version is supported for at least **12 months** after the next major version is released.

### Deprecation Process

```
Timeline (from new version release):

Month 0     │ New version released, previous version marked deprecated
            │ Deprecation notice in response headers and documentation
            ▼
Months 1-6  │ Migration Period
            │ Both versions fully functional
            │ Migration encouraged via documentation and notifications
            ▼
Months 7-12 │ Reduced Support
            │ Bug fixes only for deprecated version
            │ Warning headers on deprecated endpoint responses
            ▼
Month 12+   │ End of Life
            │ Deprecated version may be removed
            │ Requests return 410 Gone with migration instructions
```

### Deprecation Headers

When an endpoint is deprecated, responses include:

```http
Deprecation: true
Sunset: Sat, 01 Jan 2026 00:00:00 GMT
Link: </api/v2/resource>; rel="successor-version"
```

## Breaking Changes

### What Constitutes a Breaking Change

The following changes **require a new major version**:

#### Request Breaking Changes

| Change Type | Example | Why Breaking |
|------------|---------|--------------|
| Removing an endpoint | `DELETE /api/v1/legacy` removed | Clients get 404 |
| Renaming an endpoint path | `/users` to `/accounts` | Hardcoded URLs break |
| Removing a required request field | `name` no longer accepted | Clients send unused data |
| Making an optional field required | `email` now required | Requests fail validation |
| Changing a field's data type | `count: "5"` to `count: 5` | Type parsing fails |
| Restricting validation | Max length 100 to 50 | Valid data rejected |
| Removing request format support | Query params to body only | Existing requests fail |

#### Response Breaking Changes

| Change Type | Example | Why Breaking |
|------------|---------|--------------|
| Removing a response field | `created_at` removed | Missing expected data |
| Renaming a response field | `name` to `full_name` | Field access fails |
| Changing a field's data type | `id: 1` to `id: "uuid"` | Type coercion fails |
| Changing nested structure | `user.name` to `user.profile.name` | Path traversal fails |
| Changing enum values | `status: "active"` to `status: "enabled"` | Comparison logic fails |
| Changing error format | Different error structure | Error handling breaks |

#### Behavioral Breaking Changes

| Change Type | Example | Why Breaking |
|------------|---------|--------------|
| Authentication requirements | Public to authenticated | 401 for existing clients |
| Authorization requirements | New permission required | 403 for existing clients |
| Rate limit changes | 1000/hour to 100/hour | Clients throttled |
| Semantic changes | Sort order reversed | UI/logic depends on order |

### What Is NOT a Breaking Change

The following changes are **backward compatible** and do not require a new version:

| Change Type | Example | Why Compatible |
|------------|---------|----------------|
| Adding new endpoints | `GET /api/v1/analytics` | New functionality |
| Adding optional request fields | `metadata` field optional | Existing requests work |
| Adding new response fields | `updated_at` added | Extra data ignored |
| Adding new enum values | New `status: "archived"` | Existing values work |
| Relaxing validation | Max length 50 to 100 | Previously valid data still valid |
| Adding new error codes | New 422 reason | Existing errors unchanged |
| Performance improvements | Faster queries | Transparent to clients |
| Bug fixes | Correct calculation | Unless clients depend on bug |

### Examples

**Non-breaking change (v1 remains v1):**

```python
# Before: GET /api/v1/users/{id} returns
{
    "id": 1,
    "name": "John Doe"
}

# After: Adding a new field is non-breaking
{
    "id": 1,
    "name": "John Doe",
    "email": "john@example.com"  # New field - clients ignore if not expected
}
```

**Breaking change (requires v2):**

```python
# Before: GET /api/v1/users/{id} returns
{
    "id": 1,
    "name": "John Doe"
}

# After: Renaming a field is breaking
{
    "id": 1,
    "full_name": "John Doe"  # 'name' -> 'full_name' breaks clients expecting 'name'
}
```

## Version Negotiation

### Default Behavior

- Requests to `/api/v1/*` always use v1 behavior
- Requests to `/api/v2/*` always use v2 behavior (when available)
- No automatic version negotiation or fallback

### Explicit Version Required

Clients must explicitly specify the API version in the URL. There is no "latest" alias to prevent accidental breaking changes during version transitions.

**Correct:**
```bash
curl https://api.example.com/api/v1/users
```

**Incorrect (no version):**
```bash
curl https://api.example.com/api/users  # 404 Not Found
```

### Version Discovery

Clients can discover available versions via:

```bash
# OpenAPI specification lists available versions
curl https://api.example.com/openapi.json

# Health endpoint returns API version
curl https://api.example.com/api/v1/health
```

## Client Migration

### Migration Guide Template

When releasing a new major version, provide:

1. **Migration Guide**: Step-by-step instructions (see [Migration Guide Template](./migration-guide-template.md))
2. **Changelog**: Complete list of changes (see [API Changelog](./changelog.md))
3. **Compatibility Matrix**: What works, what doesn't
4. **Timeline**: Deprecation and EOL dates

### Recommended Migration Process

```
Step 1: Review
├── Read migration guide and changelog
├── Identify affected code in your application
└── Estimate migration effort

Step 2: Update
├── Update API client SDK (if using official SDK)
├── Update base URLs from v{OLD} to v{NEW}
├── Modify request/response handling for changes
└── Update any hardcoded field names or structures

Step 3: Test
├── Run unit tests with mocked responses
├── Run integration tests against staging
├── Verify all API interactions work correctly
└── Test error handling for new error formats

Step 4: Deploy
├── Deploy to staging environment
├── Monitor for errors and unexpected behavior
├── Deploy to production during low-traffic period
└── Have rollback plan ready

Step 5: Complete
├── Remove old version references
├── Update internal documentation
└── Communicate completion to team
```

### Handling Multiple Versions During Migration

During migration periods, clients may need to support multiple versions:

```typescript
// API client configuration
const API_VERSION = process.env.API_VERSION || 'v1';
const BASE_URL = `https://api.example.com/api/${API_VERSION}`;

// Feature flags for version-specific behavior
function parseUserResponse(response: UserResponse): User {
  if (API_VERSION === 'v2') {
    return {
      id: response.id,
      name: response.full_name,  // v2 field name
      displayName: response.display_name,
    };
  } else {
    return {
      id: response.id,
      name: response.name,  // v1 field name
      displayName: response.name,  // v1 doesn't have display_name
    };
  }
}
```

## Implementation Guidelines

### Backend: Version-Specific Routers

```python
# app/api/v1/router.py
from fastapi import APIRouter

v1_router = APIRouter(prefix="/api/v1")

@v1_router.get("/users/{user_id}")
async def get_user_v1(user_id: int):
    user = await fetch_user(user_id)
    return {"id": user.id, "name": user.name}  # v1 schema


# app/api/v2/router.py
from fastapi import APIRouter

v2_router = APIRouter(prefix="/api/v2")

@v2_router.get("/users/{user_id}")
async def get_user_v2(user_id: int):
    user = await fetch_user(user_id)
    return {
        "id": user.id,
        "full_name": user.name,  # v2 renamed field
        "display_name": user.display_name,  # v2 new field
    }


# app/main.py
from fastapi import FastAPI
from app.api.v1.router import v1_router
from app.api.v2.router import v2_router

app = FastAPI()
app.include_router(v1_router)
app.include_router(v2_router)  # When v2 is released
```

### Shared vs Version-Specific Logic

```
app/
├── core/           # Shared business logic (version-independent)
│   ├── services/   # Business operations
│   └── database.py # Database connections
├── models/         # Shared database models (version-independent)
├── api/
│   ├── v1/         # Version 1 specific
│   │   ├── routers/
│   │   └── schemas/    # v1 request/response Pydantic models
│   └── v2/         # Version 2 specific
│       ├── routers/
│       └── schemas/    # v2 request/response Pydantic models
└── main.py
```

**Guideline**: Keep business logic version-independent. Only request/response schemas, serialization, and routers should be version-specific.

### Testing Multiple Versions

```python
# tests/api/test_users_v1.py
def test_get_user_v1(client):
    response = client.get("/api/v1/users/1")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data  # v1 field
    assert "full_name" not in data  # v2 field shouldn't exist


# tests/api/test_users_v2.py
def test_get_user_v2(client):
    response = client.get("/api/v2/users/1")
    assert response.status_code == 200
    data = response.json()
    assert "full_name" in data  # v2 field
    assert "name" not in data  # v1 field shouldn't exist
```

### Configuration

The API version prefix is configured in `backend/app/core/config.py`:

```python
# API Configuration
API_V1_PREFIX: str = "/api/v1"
```

## Documentation

### OpenAPI Specification

Each version has its own OpenAPI spec:

| Version | OpenAPI URL | Swagger UI |
|---------|-------------|------------|
| Current (v1) | `/openapi.json` | `/docs` |
| v1 | `/api/v1/openapi.json` | `/api/v1/docs` |
| v2 | `/api/v2/openapi.json` | `/api/v2/docs` |

### Swagger UI Access

Interactive API documentation is available at:

- **Current version**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Related Documentation

- [API Changelog](./changelog.md) - Version history and changes
- [Migration Guide Template](./migration-guide-template.md) - Template for version migrations
- [Environment Configuration](../operations/environment-configuration.md) - API configuration options

## References

- [Stripe API Versioning](https://stripe.com/docs/api/versioning) - Industry best practice
- [GitHub API Versioning](https://docs.github.com/en/rest/overview/api-versions) - URL path versioning example
- [Zalando RESTful API Guidelines](https://opensource.zalando.com/restful-api-guidelines/#108) - Comprehensive API design guidance
