"""
Security Headers Middleware for FastAPI.

Adds security-related HTTP headers to all responses to mitigate common
web vulnerabilities. Headers are configurable via environment variables.

Key Features:
- Content-Security-Policy (CSP) for XSS mitigation
- Strict-Transport-Security (HSTS) for transport security
- X-Frame-Options for clickjacking protection
- X-Content-Type-Options for MIME sniffing prevention
- Referrer-Policy for privacy protection
- Permissions-Policy for feature restrictions
- X-XSS-Protection for legacy browser protection

References:
- OWASP Secure Headers: https://owasp.org/www-project-secure-headers/
- MDN Security Headers: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers
- Lit and CSP: https://lit.dev/docs/security/trusted-types/
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


@dataclass
class SecurityHeadersConfig:
    """
    Configuration for security headers.

    All values are optional and can be disabled by setting to None or False.
    Default values are secure and compatible with Lit web components.

    Attributes:
        csp_enabled: Whether to enable Content-Security-Policy header.
        csp_default_src: Default source directive for CSP.
        csp_script_src: Script source directive (includes 'unsafe-inline' for Lit).
        csp_style_src: Style source directive (includes 'unsafe-inline' for Lit).
        csp_img_src: Image source directive.
        csp_font_src: Font source directive.
        csp_connect_src: Connect source directive for API calls.
        csp_frame_ancestors: Frame ancestors directive.
        csp_base_uri: Base URI directive.
        csp_form_action: Form action directive.
        csp_report_uri: Optional CSP report URI.
        hsts_enabled: Whether to enable HSTS header.
        hsts_max_age: Max age for HSTS in seconds (default 1 year).
        hsts_include_subdomains: Include subdomains in HSTS.
        hsts_preload: Enable HSTS preload (use with caution).
        x_frame_options: X-Frame-Options value (DENY, SAMEORIGIN, or None).
        x_content_type_options: X-Content-Type-Options value.
        referrer_policy: Referrer-Policy value.
        permissions_policy: Permissions-Policy directives.
        x_xss_protection: Legacy X-XSS-Protection header value.
    """

    # Content-Security-Policy settings
    csp_enabled: bool = True
    csp_default_src: str = "'self'"
    csp_script_src: str = "'self' 'unsafe-inline'"  # Required for Lit components
    csp_style_src: str = "'self' 'unsafe-inline'"  # Required for Lit components
    csp_img_src: str = "'self' data: https:"
    csp_font_src: str = "'self'"
    csp_connect_src: str = "'self'"
    csp_frame_ancestors: str = "'none'"
    csp_base_uri: str = "'self'"
    csp_form_action: str = "'self'"
    csp_report_uri: Optional[str] = None

    # Strict-Transport-Security (HSTS) settings
    hsts_enabled: bool = True
    hsts_max_age: int = 31536000  # 1 year in seconds
    hsts_include_subdomains: bool = True
    hsts_preload: bool = False  # Disabled by default - requires careful consideration

    # X-Frame-Options (DENY, SAMEORIGIN, or None to disable)
    x_frame_options: Optional[str] = "DENY"

    # X-Content-Type-Options
    x_content_type_options: Optional[str] = "nosniff"

    # Referrer-Policy
    referrer_policy: Optional[str] = "strict-origin-when-cross-origin"

    # Permissions-Policy (formerly Feature-Policy)
    permissions_policy: Optional[str] = field(
        default_factory=lambda: (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(), "
            "payment=(), "
            "usb=()"
        )
    )

    # X-XSS-Protection (legacy, but still useful for older browsers)
    x_xss_protection: Optional[str] = "1; mode=block"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all HTTP responses.

    This middleware adds a comprehensive set of security headers designed to
    mitigate common web vulnerabilities including XSS, clickjacking, and
    MIME sniffing attacks.

    The middleware pre-computes static headers at initialization time to
    minimize per-request overhead. Only HSTS requires per-request evaluation
    to check if the request is over HTTPS.

    Example:
        >>> from app.middleware.security import SecurityHeadersMiddleware, SecurityHeadersConfig
        >>>
        >>> # Use default configuration
        >>> app.add_middleware(SecurityHeadersMiddleware)
        >>>
        >>> # Or with custom configuration
        >>> config = SecurityHeadersConfig(
        ...     csp_script_src="'self' 'unsafe-inline' https://cdn.example.com",
        ...     x_frame_options="SAMEORIGIN",
        ...     hsts_preload=True,
        ... )
        >>> app.add_middleware(SecurityHeadersMiddleware, config=config)

    Note:
        HSTS header is only added for HTTPS requests to avoid browser issues
        when accessing the site over HTTP during development.

    Attributes:
        config: The security headers configuration.
    """

    def __init__(self, app, config: Optional[SecurityHeadersConfig] = None) -> None:
        """
        Initialize the security headers middleware.

        Args:
            app: The ASGI application.
            config: Security headers configuration. If None, uses defaults.
        """
        super().__init__(app)
        self.config = config or SecurityHeadersConfig()

        # Pre-compute headers at initialization for performance
        self._csp_header = self._build_csp_header()
        self._hsts_header = self._build_hsts_header()

        logger.info(
            "SecurityHeadersMiddleware initialized with CSP=%s, HSTS=%s",
            "enabled" if self.config.csp_enabled else "disabled",
            "enabled" if self.config.hsts_enabled else "disabled",
        )

    def _build_csp_header(self) -> Optional[str]:
        """
        Build the Content-Security-Policy header value.

        Constructs the CSP header from configured directives. Only includes
        directives that have non-empty values.

        Returns:
            CSP header string or None if CSP is disabled.
        """
        if not self.config.csp_enabled:
            return None

        directives = []

        # Add each directive if configured
        if self.config.csp_default_src:
            directives.append(f"default-src {self.config.csp_default_src}")
        if self.config.csp_script_src:
            directives.append(f"script-src {self.config.csp_script_src}")
        if self.config.csp_style_src:
            directives.append(f"style-src {self.config.csp_style_src}")
        if self.config.csp_img_src:
            directives.append(f"img-src {self.config.csp_img_src}")
        if self.config.csp_font_src:
            directives.append(f"font-src {self.config.csp_font_src}")
        if self.config.csp_connect_src:
            directives.append(f"connect-src {self.config.csp_connect_src}")
        if self.config.csp_frame_ancestors:
            directives.append(f"frame-ancestors {self.config.csp_frame_ancestors}")
        if self.config.csp_base_uri:
            directives.append(f"base-uri {self.config.csp_base_uri}")
        if self.config.csp_form_action:
            directives.append(f"form-action {self.config.csp_form_action}")
        if self.config.csp_report_uri:
            directives.append(f"report-uri {self.config.csp_report_uri}")

        if not directives:
            return None

        return "; ".join(directives)

    def _build_hsts_header(self) -> Optional[str]:
        """
        Build the Strict-Transport-Security header value.

        Constructs the HSTS header with max-age and optional directives
        for subdomains and preload.

        Returns:
            HSTS header string or None if HSTS is disabled.
        """
        if not self.config.hsts_enabled:
            return None

        parts = [f"max-age={self.config.hsts_max_age}"]

        if self.config.hsts_include_subdomains:
            parts.append("includeSubDomains")
        if self.config.hsts_preload:
            parts.append("preload")

        return "; ".join(parts)

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and add security headers to response.

        This method is called for every request. It processes the request
        through the application and then adds security headers to the
        response before returning it.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or handler in chain.

        Returns:
            Response with security headers added.
        """
        # Process the request first
        response = await call_next(request)

        # Add Content-Security-Policy
        if self._csp_header:
            response.headers["Content-Security-Policy"] = self._csp_header

        # Add Strict-Transport-Security (only for HTTPS requests)
        if self._hsts_header and self._is_https_request(request):
            response.headers["Strict-Transport-Security"] = self._hsts_header

        # Add X-Frame-Options
        if self.config.x_frame_options:
            response.headers["X-Frame-Options"] = self.config.x_frame_options

        # Add X-Content-Type-Options
        if self.config.x_content_type_options:
            response.headers["X-Content-Type-Options"] = self.config.x_content_type_options

        # Add Referrer-Policy
        if self.config.referrer_policy:
            response.headers["Referrer-Policy"] = self.config.referrer_policy

        # Add Permissions-Policy
        if self.config.permissions_policy:
            response.headers["Permissions-Policy"] = self.config.permissions_policy

        # Add X-XSS-Protection (legacy)
        if self.config.x_xss_protection:
            response.headers["X-XSS-Protection"] = self.config.x_xss_protection

        logger.debug(
            "Security headers added to response for %s %s",
            request.method,
            request.url.path,
        )

        return response

    def _is_https_request(self, request: Request) -> bool:
        """
        Determine if request was made over HTTPS.

        Checks both the URL scheme and common proxy headers to determine
        if the original request was made over HTTPS. This is important
        for proper HSTS handling behind reverse proxies.

        Args:
            request: HTTP request.

        Returns:
            True if request is HTTPS, False otherwise.
        """
        # Check URL scheme directly
        if request.url.scheme == "https":
            return True

        # Check X-Forwarded-Proto header (set by reverse proxies like nginx, traefik)
        forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
        if forwarded_proto.lower() == "https":
            return True

        # Check Forwarded header (standard RFC 7239)
        forwarded = request.headers.get("Forwarded", "")
        if "proto=https" in forwarded.lower():
            return True

        return False
