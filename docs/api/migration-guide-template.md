# API Migration Guide Template

> **Instructions**: Copy this template when creating a migration guide for a new API version.
> Replace all placeholders (marked with `{PLACEHOLDER}`) with actual values.
> Delete this instruction block and any sections not applicable to your migration.

---

# API Migration Guide: v{OLD_VERSION} to v{NEW_VERSION}

This guide helps you migrate from API v{OLD_VERSION} to v{NEW_VERSION}.

## Migration Timeline

| Milestone | Date | Description |
|-----------|------|-------------|
| v{NEW_VERSION} Released | YYYY-MM-DD | New version available |
| v{OLD_VERSION} Deprecated | YYYY-MM-DD | Deprecation warnings added |
| v{OLD_VERSION} End of Life | YYYY-MM-DD | Version removed |

**Time to migrate**: {N} months from deprecation to EOL

## Quick Start

### 1. Update Base URL

```diff
- https://api.example.com/api/v{OLD_VERSION}/
+ https://api.example.com/api/v{NEW_VERSION}/
```

### 2. Update Affected Endpoints

Review the [Breaking Changes Summary](#breaking-changes-summary) below.

### 3. Test in Staging

```bash
# Set API version to test
export API_VERSION=v{NEW_VERSION}

# Run your test suite
npm test
# or
pytest
```

### 4. Deploy to Production

Deploy during low-traffic period with rollback plan ready.

---

## Breaking Changes Summary

| Category | Change | v{OLD_VERSION} | v{NEW_VERSION} | Action Required |
|----------|--------|----------------|----------------|-----------------|
| Endpoint | Renamed | `/old-path` | `/new-path` | Update URL |
| Field | Renamed | `old_name` | `new_name` | Update references |
| Field | Removed | `deprecated_field` | - | Remove usage |
| Type | Changed | `id: number` | `id: string` | Update type handling |
| Required | Added | `field?` optional | `field` required | Add field to requests |

---

## Detailed Changes

### Endpoint Changes

#### {ENDPOINT_NAME}: `{HTTP_METHOD} /path`

**Summary**: {Brief description of the change}

**Request Changes**:

```diff
{
- "old_field": "value",
+ "new_field": "value",
+ "new_required_field": "value"  // Now required
}
```

**Response Changes**:

```diff
{
  "id": 1,
- "name": "John Doe",
+ "full_name": "John Doe",
+ "display_name": "John"  // New field
}
```

**Migration Steps**:

1. Update request body to use `new_field` instead of `old_field`
2. Add `new_required_field` to all requests
3. Update response parsing to use `full_name` instead of `name`
4. Optionally use new `display_name` field

**Code Example**:

```typescript
// Before (v{OLD_VERSION})
const response = await api.get('/api/v{OLD_VERSION}/endpoint');
const name = response.data.name;

// After (v{NEW_VERSION})
const response = await api.get('/api/v{NEW_VERSION}/endpoint');
const name = response.data.full_name;
const displayName = response.data.display_name;
```

```python
# Before (v{OLD_VERSION})
response = client.get('/api/v{OLD_VERSION}/endpoint')
name = response.json()['name']

# After (v{NEW_VERSION})
response = client.get('/api/v{NEW_VERSION}/endpoint')
name = response.json()['full_name']
display_name = response.json()['display_name']
```

---

### Authentication Changes

_{Delete this section if no authentication changes}_

**Summary**: {Description of authentication changes}

**Changes**:

| Aspect | v{OLD_VERSION} | v{NEW_VERSION} |
|--------|----------------|----------------|
| Token format | JWT | JWT |
| Required scopes | `read` | `resource:read` |
| Token header | `Authorization: Bearer` | `Authorization: Bearer` |

**Migration Steps**:

1. Request new scopes during OAuth flow
2. Update scope validation in your application

---

### Error Response Changes

_{Delete this section if no error format changes}_

**v{OLD_VERSION} Error Format**:

```json
{
    "error": "Error message"
}
```

**v{NEW_VERSION} Error Format**:

```json
{
    "detail": "Error message",
    "status_code": 400,
    "error_code": "VALIDATION_ERROR",
    "timestamp": "2024-01-15T10:30:00Z"
}
```

**Migration Steps**:

1. Update error handling to parse new format
2. Use `detail` field instead of `error`
3. Optionally log `error_code` for debugging

---

### Pagination Changes

_{Delete this section if no pagination changes}_

**v{OLD_VERSION}**:

```
GET /api/v{OLD_VERSION}/resources?page=1&limit=20
```

**v{NEW_VERSION}**:

```
GET /api/v{NEW_VERSION}/resources?page=1&page_size=20
```

**Response Format Changes**:

```diff
{
  "items": [...],
  "total": 100,
  "page": 1,
- "limit": 20,
+ "page_size": 20,
+ "pages": 5
}
```

---

## New Features in v{NEW_VERSION}

### New Endpoints

| Endpoint | Description | Documentation |
|----------|-------------|---------------|
| `GET /api/v{NEW_VERSION}/new-endpoint` | Description | [Link](#) |
| `POST /api/v{NEW_VERSION}/another-endpoint` | Description | [Link](#) |

### New Response Fields

| Endpoint | New Field | Type | Description |
|----------|-----------|------|-------------|
| `GET /users` | `display_name` | string | Short name for display |
| `GET /resources` | `metadata` | object | Extended resource info |

### New Request Options

| Endpoint | New Parameter | Type | Description |
|----------|---------------|------|-------------|
| `GET /resources` | `include` | string[] | Related resources to include |
| `GET /resources` | `sort` | string | Multi-field sorting |

---

## Compatibility Matrix

### SDK Compatibility

| SDK | v{OLD_VERSION} Support | v{NEW_VERSION} Support | Upgrade To |
|-----|------------------------|------------------------|------------|
| JavaScript SDK | Yes | >= 2.0.0 | `npm install @project/sdk@2` |
| Python SDK | Yes | >= 2.0.0 | `pip install project-sdk>=2.0.0` |
| Go SDK | Yes | >= 2.0.0 | Update `go.mod` |
| OpenAPI Generated | Yes | Regenerate | Regenerate client |

### Feature Compatibility

| Feature | v{OLD_VERSION} | v{NEW_VERSION} |
|---------|----------------|----------------|
| CRUD Operations | Full | Full |
| Pagination | Offset-based | Offset + Cursor |
| Filtering | Basic | Advanced |
| Webhooks | Not available | Available |

---

## Testing Checklist

Use this checklist to verify your migration is complete:

### Request Changes
- [ ] All API calls updated to v{NEW_VERSION} URLs
- [ ] Request bodies updated with new/renamed fields
- [ ] Removed references to deprecated fields
- [ ] Added new required fields to all requests

### Response Handling
- [ ] Response parsing updated for changed field names
- [ ] Type handling updated for changed field types
- [ ] Error handling updated for new error format
- [ ] Pagination handling updated

### Authentication
- [ ] OAuth scopes updated if required
- [ ] Token handling verified
- [ ] Refresh token flow tested

### Testing
- [ ] Unit tests updated and passing
- [ ] Integration tests passing against v{NEW_VERSION}
- [ ] End-to-end tests verified
- [ ] Error scenarios tested

### Deployment
- [ ] Staging environment validated
- [ ] Monitoring configured for new endpoints
- [ ] Rollback plan documented
- [ ] Production deployment completed

---

## Rollback Plan

If issues occur after migration to v{NEW_VERSION}:

### Immediate Rollback

1. **Revert code changes** to use v{OLD_VERSION} URLs
2. **Deploy reverted code** to affected environments
3. **Verify functionality** with v{OLD_VERSION} API

### Rollback Script

```bash
# Option 1: Git revert
git revert HEAD  # Reverts migration commit
git push

# Option 2: Environment variable (if supported)
export API_VERSION=v{OLD_VERSION}
```

### Important Notes

- v{OLD_VERSION} remains functional until EOL date: YYYY-MM-DD
- Report issues to: {support contact}
- Track migration issues: {issue tracker URL}

---

## Frequently Asked Questions

### General

**Q: Can I use both versions simultaneously?**

A: Yes, during the migration period both versions are available. However, we recommend completing migration as soon as possible to avoid maintaining two code paths.

**Q: Will my API keys work with v{NEW_VERSION}?**

A: Yes, authentication is version-independent. Your existing API keys and OAuth tokens work with both versions.

**Q: What happens after the EOL date?**

A: After YYYY-MM-DD, v{OLD_VERSION} endpoints will return `410 Gone` status with a message directing to v{NEW_VERSION}.

### Technical

**Q: Do I need to update my OAuth scopes?**

A: {Yes/No}. {Explanation if yes}

**Q: Are webhooks affected by this migration?**

A: {Answer based on actual changes}

**Q: How do I test against v{NEW_VERSION} without affecting production?**

A: Use our staging environment or run the API locally:
```bash
# Point to staging
export API_BASE_URL=https://staging-api.example.com/api/v{NEW_VERSION}

# Or run locally
docker compose up
```

---

## Support

If you encounter issues during migration:

- **Documentation**: https://docs.example.com/api/v{NEW_VERSION}
- **API Status**: https://status.example.com
- **GitHub Issues**: https://github.com/org/project/issues
- **Support Email**: api-support@example.com

### Reporting Migration Issues

When reporting issues, include:

1. API version you're migrating from/to
2. Endpoint(s) affected
3. Request/response examples
4. Error messages
5. Your SDK version (if applicable)

---

## Changelog

| Date | Change |
|------|--------|
| YYYY-MM-DD | Initial migration guide published |
| YYYY-MM-DD | Added FAQ section |
| YYYY-MM-DD | Updated rollback instructions |

---

_Last updated: YYYY-MM-DD_
