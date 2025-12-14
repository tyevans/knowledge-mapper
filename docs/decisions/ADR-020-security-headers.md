# ADR-020: Security Headers Middleware

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2025-12-06 |
| **Decision Makers** | Project Team |

## Context

The project-starter template generates FastAPI applications that may be deployed in production environments facing the public internet. Modern web applications require security headers to mitigate common vulnerabilities including:

- **Cross-Site Scripting (XSS)**: Malicious scripts injected into web pages
- **Clickjacking**: UI redressing attacks via iframe embedding
- **MIME Type Sniffing**: Browser misinterpretation of content types
- **Man-in-the-Middle Attacks**: Interception of insecure connections
- **Information Leakage**: Sensitive data exposure via referrer headers
- **Feature Abuse**: Unauthorized access to browser APIs (camera, microphone, etc.)

While the frontend nginx configuration includes some security headers (X-Frame-Options, X-Content-Type-Options, X-XSS-Protection), the backend API needs equivalent protection for:

1. Direct API access that bypasses the frontend proxy
2. Defense in depth against proxy misconfiguration
3. API responses that may be rendered in browsers (error pages, redirects)

### Constraints

1. **Lit Component Compatibility**: The frontend uses Lit web components that require `'unsafe-inline'` in CSP for both `script-src` and `style-src` directives. Lit's reactive updates and CSS-in-JS patterns cannot work with strict CSP without significant architectural changes.

2. **Development vs Production**: HSTS must only be added for HTTPS connections to avoid browser caching issues during HTTP development.

3. **Configurability**: Different deployments have varying security requirements (internal tools vs public APIs).

4. **Performance**: Headers must not add measurable latency to request processing.

## Decision

We implement a `SecurityHeadersMiddleware` for FastAPI that adds comprehensive security headers to all responses.

### Headers Implemented

| Header | Default Value | Purpose |
|--------|--------------|---------|
| **Content-Security-Policy** | See below | XSS mitigation with Lit compatibility |
| **Strict-Transport-Security** | `max-age=31536000; includeSubDomains` | HTTPS enforcement (conditional) |
| **X-Frame-Options** | `DENY` | Clickjacking protection |
| **X-Content-Type-Options** | `nosniff` | MIME sniffing prevention |
| **Referrer-Policy** | `strict-origin-when-cross-origin` | Privacy protection |
| **Permissions-Policy** | See below | Browser feature restrictions |
| **X-XSS-Protection** | `1; mode=block` | Legacy browser XSS filter |

### Content-Security-Policy Details

```
default-src 'self';
script-src 'self' 'unsafe-inline';
style-src 'self' 'unsafe-inline';
img-src 'self' data: https:;
font-src 'self';
connect-src 'self';
frame-ancestors 'none';
base-uri 'self';
form-action 'self'
```

**Directive Rationale**:

| Directive | Value | Rationale |
|-----------|-------|-----------|
| `default-src` | `'self'` | Restrict all resources to same origin by default |
| `script-src` | `'self' 'unsafe-inline'` | Required for Lit component reactive updates |
| `style-src` | `'self' 'unsafe-inline'` | Required for Lit CSS-in-JS patterns |
| `img-src` | `'self' data: https:` | Allow same-origin, data URIs, and HTTPS images |
| `font-src` | `'self'` | Fonts from same origin only |
| `connect-src` | `'self'` | API calls to same origin only |
| `frame-ancestors` | `'none'` | Prevent embedding in iframes (clickjacking) |
| `base-uri` | `'self'` | Prevent base tag hijacking |
| `form-action` | `'self'` | Prevent form submission to external origins |

**Note on `'unsafe-inline'`**: While `'unsafe-inline'` reduces XSS protection, it is required for Lit compatibility. Future enhancement could implement CSP nonces for stricter security, but this adds significant complexity to the middleware and template rendering pipeline.

### Permissions-Policy Details

```
accelerometer=(),
camera=(),
geolocation=(),
gyroscope=(),
magnetometer=(),
microphone=(),
payment=(),
usb=()
```

All sensitive browser APIs are disabled by default. Applications requiring these features can override via environment configuration.

### Implementation Approach

1. **Middleware Pattern**: Follows existing `TenantResolutionMiddleware` pattern for consistency

2. **Dataclass Configuration**: `SecurityHeadersConfig` dataclass provides type-safe configuration with sensible defaults:

```python
@dataclass
class SecurityHeadersConfig:
    csp_enabled: bool = True
    csp_default_src: str = "'self'"
    csp_script_src: str = "'self' 'unsafe-inline'"
    hsts_enabled: bool = True
    hsts_max_age: int = 31536000
    x_frame_options: Optional[str] = "DENY"
    # ... additional fields
```

3. **Header Pre-computation**: CSP and HSTS headers are built once at middleware initialization to minimize per-request overhead

4. **HTTPS Detection**: Checks URL scheme and `X-Forwarded-Proto` header for proper HSTS handling behind reverse proxies:

```python
def _is_https_request(self, request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
    return forwarded_proto.lower() == "https"
```

5. **Individual Header Control**: Any header can be disabled by setting to `None` or `False`

### Configuration via Environment Variables

All headers are configurable via `config.py`:

```python
class Settings(BaseSettings):
    # Security Headers
    SECURITY_HEADERS_ENABLED: bool = True
    CSP_DEFAULT_SRC: str = "'self'"
    CSP_SCRIPT_SRC: str = "'self' 'unsafe-inline'"
    CSP_STYLE_SRC: str = "'self' 'unsafe-inline'"
    CSP_IMG_SRC: str = "'self' data: https:"
    HSTS_MAX_AGE: int = 31536000
    HSTS_INCLUDE_SUBDOMAINS: bool = True
    HSTS_PRELOAD: bool = False
    X_FRAME_OPTIONS: str = "DENY"
    REFERRER_POLICY: str = "strict-origin-when-cross-origin"
```

## Consequences

### Positive

1. **Defense in Depth**: Backend adds headers regardless of frontend proxy configuration, protecting against proxy misconfiguration

2. **OWASP Compliance**: Addresses security header recommendations from OWASP Secure Headers Project

3. **Flexibility**: All headers are configurable for different deployment requirements (internal tools may need relaxed CSP)

4. **Developer Experience**: Sensible defaults work out of the box without configuration

5. **Lit Compatibility**: CSP configuration tested with Lit web components, ensuring frontend functionality

6. **Performance**: Header pre-computation at initialization adds negligible overhead to request processing

7. **Observability**: Debug logging tracks header application for troubleshooting

### Negative

1. **CSP Limitations**: `'unsafe-inline'` requirement for Lit reduces XSS protection. Script injection attacks are partially mitigated but not fully prevented

2. **Configuration Complexity**: Many environment variables to manage for full customization

3. **Header Duplication**: Some headers (X-Frame-Options, X-Content-Type-Options) may be set by both nginx and backend. While browsers use the most restrictive value, this creates maintenance overhead

4. **No CSP Reporting**: Default configuration lacks `report-uri` for CSP violation monitoring. Adding this requires external reporting infrastructure

### Neutral

1. **Future CSP Nonces**: A future enhancement could implement CSP nonces (`'nonce-<base64>'`) for stricter security, but this requires template integration to inject nonces into HTML responses

2. **CSP Reporting Endpoint**: A future enhancement could add a CSP violation reporting endpoint for security monitoring

3. **Permissions-Policy Evolution**: The Permissions-Policy header replaces the deprecated Feature-Policy. The implementation uses the modern format

## Alternatives Considered

### Nginx-Only Headers

**Approach**: Configure all security headers in nginx frontend proxy only.

**Strengths**:
- Single configuration location
- Simpler backend (no security middleware)
- Well-documented nginx security patterns

**Why Not Chosen**:
- Doesn't protect direct API access (load balancers, service mesh)
- Less flexible for per-route customization
- Violates defense-in-depth principle

### Third-Party Library (secure / starlette-helmet)

**Approach**: Use established security header libraries like `secure` or `starlette-helmet`.

**Strengths**:
- Mature and well-tested implementations
- Community maintenance and security updates
- Comprehensive header coverage

**Why Not Chosen**:
- Additional dependency for relatively simple functionality
- Less control over implementation details
- May include unnecessary features
- Custom middleware aligns better with existing project patterns

### FastAPI Dependency Injection

**Approach**: Add security headers via FastAPI dependencies on each route.

**Strengths**:
- Per-route control over headers
- Explicit header application
- Type-safe dependency injection

**Why Not Chosen**:
- Must be added to every route manually
- Easy to forget on new endpoints
- Higher maintenance burden
- Middleware ensures consistent coverage

### Response Callbacks / Event Handlers

**Approach**: Use Starlette's response callbacks or event handlers to add headers.

**Strengths**:
- Lighter weight than full middleware
- Starlette-native approach

**Why Not Chosen**:
- Less clear separation of concerns
- Harder to configure per-environment
- Middleware pattern is more conventional for this use case

---

## Related ADRs

- [ADR-017: Optional Observability Stack](./ADR-017-optional-observability-stack.md) - Pattern for optional cookiecutter features

## Implementation References

- `backend/app/middleware/security.py` - SecurityHeadersMiddleware implementation
- `backend/app/core/config.py` - Security header configuration settings
- `backend/app/main.py` - Middleware registration
- `backend/tests/unit/middleware/test_security.py` - Middleware tests
- `frontend/nginx.conf` - Complementary frontend security headers

## External References

- [OWASP Secure Headers Project](https://owasp.org/www-project-secure-headers/)
- [MDN Content-Security-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
- [MDN Permissions-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Permissions-Policy)
- [Lit and Content Security Policy](https://lit.dev/docs/security/trusted-types/)
- [Content-Security-Policy.com Reference](https://content-security-policy.com/)
