# API Changelog

All notable changes to the Knowledge Mapper API are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) for API versions.

## How to Read This Changelog

- **Added**: New endpoints, fields, or capabilities
- **Changed**: Modifications to existing functionality (backward-compatible)
- **Deprecated**: Features that will be removed in future versions
- **Removed**: Features removed (only in major versions)
- **Fixed**: Bug fixes
- **Security**: Security-related changes

## Version Compatibility

| Version | Status | Supported Until |
|---------|--------|-----------------|
| v1 | **Current** | - |

---

## [Unreleased]

### Added
- _List new endpoints, fields, or features pending release_

### Changed
- _List modifications to existing functionality_

### Deprecated
- _List features that will be removed in future versions_

### Fixed
- _List bug fixes_

---

## [v1] - Initial Release

### Added

#### Health Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/health` | Application health check with service status |
| `GET /api/v1/health/ready` | Kubernetes readiness probe |
| `GET /api/v1/health/live` | Kubernetes liveness probe |

#### Authentication Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/auth/token` | Exchange authorization code for access/refresh tokens |
| `POST /api/v1/auth/refresh` | Refresh expired access token |
| `GET /api/v1/auth/me` | Get current authenticated user information |
| `POST /api/v1/auth/logout` | Revoke tokens and end session |

#### OAuth Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/oauth/authorize` | Initiate OAuth 2.0 authorization flow |
| `GET /api/v1/oauth/callback` | OAuth callback handler |

#### Todo Endpoints (Demo Resource)

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/todos` | List todos for current tenant (paginated) |
| `POST /api/v1/todos` | Create a new todo |
| `GET /api/v1/todos/{id}` | Get todo by ID |
| `PUT /api/v1/todos/{id}` | Update a todo |
| `DELETE /api/v1/todos/{id}` | Delete a todo |

### Features

- **OAuth 2.0 / OIDC Authentication**: PKCE-enhanced authorization code flow via Keycloak
- **Multi-tenant Architecture**: Row-Level Security (RLS) enforced data isolation
- **Rate Limiting**: Redis-backed request throttling (100 req/min default)
- **Security Headers**: OWASP-compliant HTTP security headers
- **Structured Logging**: JSON-formatted logs with correlation IDs
- **Observability**: Prometheus metrics, Loki logging, Tempo tracing

### Request/Response Formats

#### Standard Error Response

```json
{
    "detail": "Human-readable error message",
    "status_code": 400,
    "error_code": "VALIDATION_ERROR",
    "timestamp": "2024-01-15T10:30:00Z"
}
```

#### Pagination Response

```json
{
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20,
    "pages": 5
}
```

### Notes

- Initial release targeting MVP functionality
- All endpoints require authentication unless explicitly documented as public
- Tenant isolation enforced at database level via RLS policies

---

## Changelog Entry Template

When adding new entries, use this template:

```markdown
## [vX] - YYYY-MM-DD

### Added
- `METHOD /api/vX/endpoint` - Description of new endpoint
  - Request: `{ field: type }` (optional fields marked with `?`)
  - Response: `{ field: type }`
- New field `field_name` added to `EndpointResponse`

### Changed
- `METHOD /api/vX/endpoint` - Description of change
- Field `old_name` renamed to `new_name` in `SchemaName` (backward-compatible via alias)

### Deprecated
- `METHOD /api/vX/endpoint` - Will be removed in vY. Use `/api/vX/new-endpoint` instead.
- Field `field_name` in `SchemaName` - Will be removed in vY. Use `new_field_name` instead.

### Removed
- `METHOD /api/vX-1/endpoint` - Removed, use vX equivalent
- Field `field_name` removed from `SchemaName`

### Fixed
- Fixed issue where `endpoint` returned incorrect data when [condition]
- Fixed validation for `field_name` to properly reject [invalid input]

### Security
- Fixed authentication bypass in `endpoint` (CVE-XXXX-XXXX if applicable)
- Added rate limiting to `endpoint` to prevent abuse
```

---

## Version Comparison

This table summarizes feature availability across versions:

| Feature | v1 | v2 (Future) |
|---------|-----|-------------|
| Authentication | OAuth 2.0 / OIDC | OAuth 2.0 / OIDC |
| Multi-tenancy | Yes (RLS) | Yes (RLS) |
| Rate Limiting | Yes (Redis) | Yes (Redis) |
| Pagination | Offset-based | Offset + Cursor |
| Filtering | Basic | Advanced |
| Sorting | Single field | Multi-field |
| Batch Operations | No | Planned |

---

## Migration Guides

When breaking changes require migration, guides are published here:

- _No migrations required yet - v1 is the initial release_

Future migration guides will be linked here:
- `v1 to v2`: [Migration Guide: v1 to v2](./migration-guide-v1-to-v2.md) _(when available)_

---

## API Deprecation Schedule

Active deprecations and their timeline:

| Deprecated Item | Deprecated In | Removal In | Replacement |
|-----------------|---------------|------------|-------------|
| _None currently_ | - | - | - |

---

## Related Documentation

- [API Versioning Strategy](./versioning.md) - Versioning policy and guidelines
- [Migration Guide Template](./migration-guide-template.md) - Template for version migrations
- [OpenAPI Specification](/openapi.json) - Machine-readable API definition
