# ADR-024: Sentry Error Tracking Integration

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2025-12-06 |
| **Decision Makers** | Project Team |

## Context

{{ cookiecutter.project_name }} needs a production-grade error tracking solution to:

1. **Capture unhandled exceptions** with full stack traces and context
2. **Correlate errors** with user sessions and tenant IDs for multi-tenant support
3. **Track releases** to identify regressions introduced by deployments
4. **Filter sensitive data** (PII) before transmission
5. **Integrate seamlessly** with the existing FastAPI/SQLAlchemy stack

### Requirements

| Requirement | Description |
|-------------|-------------|
| Exception capture | Automatic capture of unhandled exceptions |
| Stack traces | Full Python stack traces with local variables |
| User context | Attach user_id and tenant_id to errors |
| Release tracking | Correlate errors with deployment versions |
| PII filtering | Remove passwords, tokens, and sensitive data |
| Performance tracing | Optional request performance monitoring |
| Fail-open | Application works if error tracking unavailable |

### Constraints

- Must be optional (not all deployments need error tracking)
- Must follow existing cookiecutter conditional pattern
- Must not impact application performance significantly
- Must handle multi-tenant context properly
- SaaS or self-hosted deployment options required

## Decision

We implement **optional Sentry integration** as the error tracking solution, following these principles:

### 1. Error Tracking Platform: Sentry

**Choice**: Sentry SDK with FastAPI and SQLAlchemy integrations

**Rationale**:
- Industry-standard error tracking platform
- Excellent Python SDK with automatic framework detection
- First-party FastAPI and SQLAlchemy integrations
- Supports both SaaS and self-hosted deployment
- Free tier suitable for development and small projects
- Comprehensive context capture (request, user, breadcrumbs)

### 2. Integration Pattern: Optional via Cookiecutter

**Choice**: Use `include_sentry` cookiecutter variable following ADR-017 pattern

**Implementation**:
```python
{% raw %}{% if cookiecutter.include_sentry == "yes" %}{% endraw %}
from app.sentry import init_sentry
init_sentry(settings)
{% raw %}{% endif %}{% endraw %}
```

**Rationale**:
- Consistent with existing observability stack optional pattern
- No runtime overhead when disabled
- Clean codebase without error tracking when not needed
- Easy to enable/disable at project generation time

### 3. Initialization Pattern: Fail-Open

**Choice**: Application starts normally if Sentry is misconfigured or unavailable

**Implementation**:
```python
def init_sentry(settings: Settings) -> bool:
    if not settings.SENTRY_DSN:
        logger.info("SENTRY_DSN not configured - error tracking disabled")
        return False
    try:
        sentry_sdk.init(...)
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")
        return False  # Continue without error tracking
```

**Rationale**:
- Error tracking should never block application startup
- Development environments work without Sentry configuration
- Graceful degradation on network issues or misconfiguration
- Clear logging indicates Sentry status

### 4. Multi-Tenant Context: User and Tenant Tags

**Choice**: Attach tenant_id as both user context and tag

**Implementation**:
```python
def set_user_context(user_id: str, tenant_id: str, email: str = None):
    sentry_sdk.set_user({
        "id": user_id,
        "email": email,
    })
    sentry_sdk.set_tag("tenant_id", tenant_id)
    sentry_sdk.set_context("tenant", {"tenant_id": tenant_id})
```

**Rationale**:
- Enables filtering errors by tenant in Sentry UI
- Supports multi-tenant debugging and impact analysis
- User context provides authentication correlation
- Tags are indexed for fast dashboard filtering

### 5. PII Filtering: Before-Send Hook

**Choice**: Filter sensitive data using before_send hook

**Implementation**:
```python
PII_FIELDS = {"password", "secret", "api_key", "access_token", "token", ...}
SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key", ...}

def _before_send(event, hint):
    # Filter request body
    if "request" in event and "data" in event["request"]:
        _filter_dict(event["request"]["data"], PII_FIELDS)
    # Filter headers
    if "request" in event and "headers" in event["request"]:
        _filter_dict(event["request"]["headers"], SENSITIVE_HEADERS)
    return event
```

**Rationale**:
- GDPR and privacy compliance
- Prevents credential exposure in error reports
- Consistent filtering across all events
- Extensible for application-specific fields

### 6. Configuration: Environment Variables

**Choice**: All Sentry configuration via environment variables

**Variables**:
| Variable | Default | Description |
|----------|---------|-------------|
| `SENTRY_DSN` | "" | Sentry project DSN (empty = disabled) |
| `SENTRY_ENVIRONMENT` | development | Environment tag |
| `SENTRY_RELEASE` | APP_VERSION | Release version for tracking |
| `SENTRY_TRACES_SAMPLE_RATE` | 0.1 | Performance trace sampling (10%) |
| `SENTRY_PROFILES_SAMPLE_RATE` | 0.1 | Profiling sample rate (10%) |

**Rationale**:
- Follows 12-factor app configuration
- Easy to configure per environment
- DSN as secret - not committed to repository
- Sensible defaults for development

## Consequences

### Positive

1. **Proactive Error Detection**: Errors captured before users report them
2. **Context-Rich Debugging**: Full stack traces with request and user context
3. **Multi-Tenant Visibility**: Filter and analyze errors by tenant
4. **Release Correlation**: Identify regressions from deployments
5. **Minimal Code Impact**: Single initialization point, automatic capture
6. **Privacy Compliant**: PII filtered before transmission

### Negative

1. **External Dependency**: Requires Sentry account or self-hosted instance
2. **Network Overhead**: Events sent to external service (async, minimal impact)
3. **Learning Curve**: Team needs familiarity with Sentry UI
4. **Cost at Scale**: High error volumes may require paid tier

### Neutral

1. **Complementary to Logging**: Sentry captures structured errors; Loki captures all logs. Both are valuable and serve different purposes
2. **SDK Availability**: If `sentry-sdk` is not installed, the module gracefully degrades with no functionality

## Architecture

### Integration Points

```
                                    +---------------------+
                                    |   Sentry Cloud      |
                                    |   (or self-hosted)  |
                                    +----------^----------+
                                               |
                                               | HTTPS (async)
                                               |
+----------------------------------------------+---------------+
|                        Backend Service                        |
|  +-------------+     +-------------+     +-------------+     |
|  |   FastAPI   |---->|  sentry.py  |---->|  Sentry SDK |     |
|  |  Middleware |     | init/hooks  |     |  (async)    |     |
|  +-------------+     +-------------+     +-------------+     |
|         |                   |                                 |
|         |            +------+------+                          |
|         |            | before_send |                          |
|         |            | (PII filter)|                          |
|         |            +-------------+                          |
|         |                                                     |
|  +------v------+     +-------------+                          |
|  |    Auth     |---->|set_user_ctx |                          |
|  | Dependency  |     |(tenant_id)  |                          |
|  +-------------+     +-------------+                          |
|                                                               |
+---------------------------------------------------------------+
```

### Data Flow

1. **Exception Occurs**: Unhandled exception in request handler
2. **SDK Captures**: Sentry SDK intercepts and enriches with context
3. **PII Filtering**: before_send hook removes sensitive data
4. **Async Transmission**: Event queued and sent asynchronously
5. **Sentry Processing**: Deduplication, grouping, alerting
6. **Developer Review**: Error appears in Sentry dashboard

### SDK Integrations

The Sentry module configures the following SDK integrations:

| Integration | Purpose |
|-------------|---------|
| `FastApiIntegration` | Automatic request/response capture, URL-based transaction naming |
| `SqlalchemyIntegration` | Database query tracking and error context |
| `AsyncioIntegration` | Proper async context tracking |
| `LoggingIntegration` | Log messages as breadcrumbs, ERROR+ as events |

## Alternatives Considered

### Alternative 1: Rollbar

**Approach**: Use Rollbar for error tracking.

**Strengths**:
- Good Python support
- Simpler pricing model
- Decent feature set

**Why Not Chosen**:
- Smaller community and ecosystem
- Fewer integrations
- No self-hosted option for sensitive deployments

### Alternative 2: Bugsnag

**Approach**: Use Bugsnag for error and stability monitoring.

**Strengths**:
- Good stability monitoring
- Release health tracking
- Solid Python SDK

**Why Not Chosen**:
- Less comprehensive than Sentry
- Fewer framework integrations
- Higher pricing for comparable features

### Alternative 3: Application Insights (Azure)

**Approach**: Use Azure Application Insights for APM and error tracking.

**Strengths**:
- Deep Azure integration
- Comprehensive APM features
- Log correlation

**Why Not Chosen**:
- Azure-specific, reduces portability
- More complex setup
- Python SDK less mature than Sentry
- Template aims for cloud-agnostic deployment

### Alternative 4: Self-Built Error Tracking

**Approach**: Build custom error tracking with structured logging to Loki.

**Strengths**:
- Full control
- No external dependencies
- No cost

**Why Not Chosen**:
- Significant development effort
- Maintenance burden
- Missing advanced features (deduplication, trends, issue grouping)
- Building error tracking is not a differentiating feature

### Alternative 5: Logs Only (No Error Tracking)

**Approach**: Rely solely on structured logging captured by Loki.

**Strengths**:
- No additional dependencies
- Existing Loki stack captures logs
- Simpler architecture

**Why Not Chosen**:
- No aggregation or deduplication
- Harder to identify error trends
- No user impact analysis
- Missing stack trace correlation and grouping
- Sentry complements logging, not replaces it

## Implementation

### File Structure

```
backend/
  app/
    sentry.py           # Sentry initialization and helpers
    core/
      config.py         # Sentry configuration settings
    api/
      dependencies/
        auth.py         # User context attachment point

.env.example            # SENTRY_DSN placeholder
```

### Configuration

```python
# config.py
class Settings(BaseSettings):
    # Sentry Configuration
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_RELEASE: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    SENTRY_PROFILES_SAMPLE_RATE: float = 0.1
```

### API Functions

The sentry module exposes these functions:

| Function | Purpose |
|----------|---------|
| `init_sentry(settings)` | Initialize Sentry SDK (returns True if successful) |
| `set_user_context(user_id, tenant_id, email)` | Attach user context to current scope |
| `clear_user_context()` | Clear user context (logout) |
| `capture_message(message, level, **extra)` | Manually capture a message |
| `capture_exception(exception, **extra)` | Manually capture an exception |
| `add_breadcrumb(message, category, level, data)` | Add breadcrumb trail |
| `set_tag(key, value)` | Set indexed tag |
| `set_context(name, context)` | Set structured context |

### Cookiecutter Variable

```json
// cookiecutter.json
{
  "include_sentry": ["no", "yes"]
}
```

## Complementary Stack

Sentry complements the existing observability stack:

| Tool | Purpose | Overlap |
|------|---------|---------|
| Prometheus | Metrics | None - different data types |
| Loki | Logs | Breadcrumbs capture some log data |
| Tempo | Traces | Sentry has separate trace sampling |
| Grafana | Visualization | Sentry has own dashboard |
| Sentry | Error Tracking | Primary error management |

## Related ADRs

- [ADR-017: Optional Observability Stack](./ADR-017-optional-observability-stack.md) - Follows optional feature pattern
- [ADR-019: GitHub Actions CI/CD](./ADR-019-github-actions-cicd.md) - Release tracking integration via CI
- [ADR-023: Database Backup Strategy](./ADR-023-database-backup-strategy.md) - Same fail-open pattern

## Implementation References

- `backend/app/sentry.py` - Sentry initialization and helper functions
- `backend/app/core/config.py` - Sentry configuration settings
- `.env.example` - SENTRY_DSN placeholder

## External References

- [Sentry Python SDK](https://docs.sentry.io/platforms/python/)
- [Sentry FastAPI Integration](https://docs.sentry.io/platforms/python/integrations/fastapi/)
- [Sentry SQLAlchemy Integration](https://docs.sentry.io/platforms/python/integrations/sqlalchemy/)
- [Sentry Self-Hosted](https://develop.sentry.dev/self-hosted/)
- [GDPR and Sentry](https://sentry.io/security/#gdpr)
