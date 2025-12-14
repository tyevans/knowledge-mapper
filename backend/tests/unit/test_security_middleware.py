"""
Unit tests for SecurityHeadersMiddleware.

Tests the SecurityHeadersMiddleware class to ensure correct security header
injection, configuration handling, HTTPS detection, and header disabling.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import Mock

from starlette.requests import Request
from starlette.responses import Response

from app.middleware.security import SecurityHeadersConfig, SecurityHeadersMiddleware


@pytest.fixture
def app_with_default_security():
    """Create a FastAPI app with default security headers middleware."""
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    return app


@pytest.fixture
def client(app_with_default_security):
    """Create test client with default security headers."""
    return TestClient(app_with_default_security)


class TestDefaultSecurityHeaders:
    """Tests for default security headers configuration."""

    def test_adds_csp_header(self, client):
        """CSP header should be present with default configuration."""
        response = client.get("/test")

        assert "Content-Security-Policy" in response.headers
        csp = response.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "script-src 'self' 'unsafe-inline'" in csp
        assert "style-src 'self' 'unsafe-inline'" in csp

    def test_adds_x_frame_options_header(self, client):
        """X-Frame-Options header should be DENY by default."""
        response = client.get("/test")

        assert response.headers["X-Frame-Options"] == "DENY"

    def test_adds_x_content_type_options_header(self, client):
        """X-Content-Type-Options header should be nosniff."""
        response = client.get("/test")

        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_adds_referrer_policy_header(self, client):
        """Referrer-Policy header should be present with default value."""
        response = client.get("/test")

        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_adds_permissions_policy_header(self, client):
        """Permissions-Policy header should be present with restrictive defaults."""
        response = client.get("/test")

        assert "Permissions-Policy" in response.headers
        policy = response.headers["Permissions-Policy"]
        assert "camera=()" in policy
        assert "microphone=()" in policy
        assert "geolocation=()" in policy

    def test_adds_x_xss_protection_header(self, client):
        """X-XSS-Protection header should be present for legacy browser support."""
        response = client.get("/test")

        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    def test_hsts_not_added_for_http(self, client):
        """HSTS should not be added for HTTP requests."""
        response = client.get("/test")

        # TestClient uses HTTP by default
        assert "Strict-Transport-Security" not in response.headers


class TestHSTSHeader:
    """Tests for Strict-Transport-Security header handling."""

    def test_hsts_added_for_https_forwarded_proto(self, client):
        """HSTS should be added when X-Forwarded-Proto is https."""
        response = client.get("/test", headers={"X-Forwarded-Proto": "https"})

        assert "Strict-Transport-Security" in response.headers
        hsts = response.headers["Strict-Transport-Security"]
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts

    def test_hsts_respects_forwarded_header(self):
        """HSTS should be added when Forwarded header indicates https."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test", headers={"Forwarded": "proto=https"})

        assert "Strict-Transport-Security" in response.headers

    def test_hsts_preload_disabled_by_default(self, client):
        """HSTS preload should be disabled by default."""
        response = client.get("/test", headers={"X-Forwarded-Proto": "https"})

        hsts = response.headers["Strict-Transport-Security"]
        assert "preload" not in hsts

    def test_hsts_with_preload_enabled(self):
        """HSTS preload can be enabled via configuration."""
        app = FastAPI()
        config = SecurityHeadersConfig(hsts_preload=True)
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test", headers={"X-Forwarded-Proto": "https"})

        hsts = response.headers["Strict-Transport-Security"]
        assert "preload" in hsts

    def test_hsts_custom_max_age(self):
        """HSTS max-age can be customized."""
        app = FastAPI()
        config = SecurityHeadersConfig(hsts_max_age=86400)  # 1 day
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test", headers={"X-Forwarded-Proto": "https"})

        hsts = response.headers["Strict-Transport-Security"]
        assert "max-age=86400" in hsts


class TestCSPConfiguration:
    """Tests for Content-Security-Policy configuration."""

    def test_csp_contains_all_default_directives(self, client):
        """CSP should contain all default directives."""
        response = client.get("/test")

        csp = response.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "script-src 'self' 'unsafe-inline'" in csp
        assert "style-src 'self' 'unsafe-inline'" in csp
        assert "img-src 'self' data: https:" in csp
        assert "font-src 'self'" in csp
        assert "connect-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "base-uri 'self'" in csp
        assert "form-action 'self'" in csp

    def test_csp_can_be_disabled(self):
        """CSP can be disabled via configuration."""
        app = FastAPI()
        config = SecurityHeadersConfig(csp_enabled=False)
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert "Content-Security-Policy" not in response.headers

    def test_csp_custom_script_src(self):
        """CSP script-src can be customized for CDN usage."""
        app = FastAPI()
        config = SecurityHeadersConfig(
            csp_script_src="'self' 'unsafe-inline' https://cdn.example.com"
        )
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        csp = response.headers["Content-Security-Policy"]
        assert "script-src 'self' 'unsafe-inline' https://cdn.example.com" in csp

    def test_csp_custom_connect_src_for_api(self):
        """CSP connect-src can include API URLs."""
        app = FastAPI()
        config = SecurityHeadersConfig(
            csp_connect_src="'self' https://api.example.com wss://ws.example.com"
        )
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        csp = response.headers["Content-Security-Policy"]
        assert "connect-src 'self' https://api.example.com wss://ws.example.com" in csp

    def test_csp_report_uri(self):
        """CSP can include report-uri directive."""
        app = FastAPI()
        config = SecurityHeadersConfig(
            csp_report_uri="/api/csp-report"
        )
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        csp = response.headers["Content-Security-Policy"]
        assert "report-uri /api/csp-report" in csp


class TestCustomConfiguration:
    """Tests for custom configuration options."""

    def test_x_frame_options_sameorigin(self):
        """X-Frame-Options can be set to SAMEORIGIN."""
        app = FastAPI()
        config = SecurityHeadersConfig(x_frame_options="SAMEORIGIN")
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"

    def test_x_frame_options_disabled(self):
        """X-Frame-Options can be disabled."""
        app = FastAPI()
        config = SecurityHeadersConfig(x_frame_options=None)
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert "X-Frame-Options" not in response.headers

    def test_referrer_policy_custom_value(self):
        """Referrer-Policy can be customized."""
        app = FastAPI()
        config = SecurityHeadersConfig(referrer_policy="no-referrer")
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.headers["Referrer-Policy"] == "no-referrer"

    def test_referrer_policy_disabled(self):
        """Referrer-Policy can be disabled."""
        app = FastAPI()
        config = SecurityHeadersConfig(referrer_policy=None)
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert "Referrer-Policy" not in response.headers

    def test_permissions_policy_custom(self):
        """Permissions-Policy can be customized."""
        app = FastAPI()
        config = SecurityHeadersConfig(
            permissions_policy="camera=self, microphone=()"
        )
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.headers["Permissions-Policy"] == "camera=self, microphone=()"

    def test_permissions_policy_disabled(self):
        """Permissions-Policy can be disabled."""
        app = FastAPI()
        config = SecurityHeadersConfig(permissions_policy=None)
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert "Permissions-Policy" not in response.headers

    def test_x_xss_protection_disabled(self):
        """X-XSS-Protection can be disabled."""
        app = FastAPI()
        config = SecurityHeadersConfig(x_xss_protection=None)
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert "X-XSS-Protection" not in response.headers

    def test_hsts_disabled(self):
        """HSTS can be disabled via configuration."""
        app = FastAPI()
        config = SecurityHeadersConfig(hsts_enabled=False)
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test", headers={"X-Forwarded-Proto": "https"})

        assert "Strict-Transport-Security" not in response.headers

    def test_hsts_without_subdomains(self):
        """HSTS can exclude subdomains."""
        app = FastAPI()
        config = SecurityHeadersConfig(hsts_include_subdomains=False)
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test", headers={"X-Forwarded-Proto": "https"})

        hsts = response.headers["Strict-Transport-Security"]
        assert "includeSubDomains" not in hsts


class TestSecurityHeadersConfig:
    """Tests for SecurityHeadersConfig dataclass."""

    def test_default_values(self):
        """Config should have secure default values."""
        config = SecurityHeadersConfig()

        assert config.csp_enabled is True
        assert config.csp_default_src == "'self'"
        assert "'unsafe-inline'" in config.csp_script_src
        assert "'unsafe-inline'" in config.csp_style_src
        assert config.hsts_enabled is True
        assert config.hsts_max_age == 31536000
        assert config.hsts_include_subdomains is True
        assert config.hsts_preload is False
        assert config.x_frame_options == "DENY"
        assert config.x_content_type_options == "nosniff"
        assert config.referrer_policy == "strict-origin-when-cross-origin"
        assert config.x_xss_protection == "1; mode=block"

    def test_permissions_policy_default(self):
        """Permissions-Policy should have restrictive defaults."""
        config = SecurityHeadersConfig()

        assert "camera=()" in config.permissions_policy
        assert "microphone=()" in config.permissions_policy
        assert "geolocation=()" in config.permissions_policy
        assert "payment=()" in config.permissions_policy

    def test_custom_values_override_defaults(self):
        """Custom values should override defaults."""
        config = SecurityHeadersConfig(
            csp_enabled=False,
            x_frame_options="SAMEORIGIN",
            hsts_max_age=3600,
        )

        assert config.csp_enabled is False
        assert config.x_frame_options == "SAMEORIGIN"
        assert config.hsts_max_age == 3600


class TestHTTPSDetection:
    """Tests for HTTPS request detection logic."""

    def test_detects_https_from_url_scheme(self):
        """Should detect HTTPS from URL scheme."""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        request.url.scheme = "https"
        request.headers = {}

        assert middleware._is_https_request(request) is True

    def test_detects_https_from_x_forwarded_proto(self):
        """Should detect HTTPS from X-Forwarded-Proto header."""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        request.url.scheme = "http"
        request.headers = {"X-Forwarded-Proto": "https"}

        assert middleware._is_https_request(request) is True

    def test_detects_https_from_x_forwarded_proto_case_insensitive(self):
        """X-Forwarded-Proto detection should be case insensitive."""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        request.url.scheme = "http"
        request.headers = {"X-Forwarded-Proto": "HTTPS"}

        assert middleware._is_https_request(request) is True

    def test_detects_https_from_forwarded_header(self):
        """Should detect HTTPS from standard Forwarded header."""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        request.url.scheme = "http"
        request.headers = {"Forwarded": "for=192.0.2.60;proto=https;by=203.0.113.43"}

        assert middleware._is_https_request(request) is True

    def test_detects_http_correctly(self):
        """Should correctly identify HTTP requests."""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        request.url.scheme = "http"
        request.headers = {}

        assert middleware._is_https_request(request) is False

    def test_detects_http_with_explicit_proto(self):
        """Should detect HTTP when X-Forwarded-Proto is http."""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        request.url.scheme = "http"
        request.headers = {"X-Forwarded-Proto": "http"}

        assert middleware._is_https_request(request) is False


class TestMiddlewareIntegration:
    """Integration tests for middleware with various response types."""

    def test_headers_added_to_json_response(self, client):
        """Security headers should be added to JSON responses."""
        response = client.get("/test")

        assert response.status_code == 200
        assert "Content-Security-Policy" in response.headers
        assert "X-Frame-Options" in response.headers

    def test_headers_added_to_error_responses(self):
        """Security headers should be added to error responses."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/error")
        async def error_endpoint():
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")

        client = TestClient(app)
        response = client.get("/error")

        assert response.status_code == 404
        assert "Content-Security-Policy" in response.headers
        assert "X-Frame-Options" in response.headers

    def test_headers_added_to_all_http_methods(self):
        """Security headers should be added for all HTTP methods."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def get_endpoint():
            return {"method": "GET"}

        @app.post("/test")
        async def post_endpoint():
            return {"method": "POST"}

        @app.put("/test")
        async def put_endpoint():
            return {"method": "PUT"}

        @app.delete("/test")
        async def delete_endpoint():
            return {"method": "DELETE"}

        client = TestClient(app)

        for method in ["get", "post", "put", "delete"]:
            response = getattr(client, method)("/test")
            assert "Content-Security-Policy" in response.headers
            assert "X-Frame-Options" in response.headers

    def test_multiple_endpoints(self):
        """Security headers should be added to all endpoints."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/api/users")
        async def users_endpoint():
            return {"users": []}

        @app.get("/api/items")
        async def items_endpoint():
            return {"items": []}

        client = TestClient(app)

        for path in ["/api/users", "/api/items"]:
            response = client.get(path)
            assert "Content-Security-Policy" in response.headers


class TestLitComponentsCompatibility:
    """Tests ensuring CSP is compatible with Lit web components."""

    def test_default_csp_allows_unsafe_inline_scripts(self, client):
        """Default CSP should allow unsafe-inline for Lit components."""
        response = client.get("/test")

        csp = response.headers["Content-Security-Policy"]
        # Lit requires unsafe-inline for scripts
        assert "'unsafe-inline'" in csp
        assert "script-src" in csp

    def test_default_csp_allows_unsafe_inline_styles(self, client):
        """Default CSP should allow unsafe-inline styles for Lit shadow DOM."""
        response = client.get("/test")

        csp = response.headers["Content-Security-Policy"]
        # Lit requires unsafe-inline for styles
        assert "'unsafe-inline'" in csp
        assert "style-src" in csp

    def test_default_csp_allows_data_urls_for_images(self, client):
        """Default CSP should allow data: URLs for images."""
        response = client.get("/test")

        csp = response.headers["Content-Security-Policy"]
        assert "img-src" in csp
        assert "data:" in csp


class TestHeaderPrecomputation:
    """Tests ensuring headers are precomputed for performance."""

    def test_csp_header_precomputed(self):
        """CSP header should be precomputed at initialization."""
        config = SecurityHeadersConfig()
        middleware = SecurityHeadersMiddleware(app=Mock(), config=config)

        assert middleware._csp_header is not None
        assert isinstance(middleware._csp_header, str)
        assert "default-src" in middleware._csp_header

    def test_hsts_header_precomputed(self):
        """HSTS header should be precomputed at initialization."""
        config = SecurityHeadersConfig()
        middleware = SecurityHeadersMiddleware(app=Mock(), config=config)

        assert middleware._hsts_header is not None
        assert isinstance(middleware._hsts_header, str)
        assert "max-age" in middleware._hsts_header

    def test_disabled_csp_returns_none(self):
        """Disabled CSP should result in None precomputed header."""
        config = SecurityHeadersConfig(csp_enabled=False)
        middleware = SecurityHeadersMiddleware(app=Mock(), config=config)

        assert middleware._csp_header is None

    def test_disabled_hsts_returns_none(self):
        """Disabled HSTS should result in None precomputed header."""
        config = SecurityHeadersConfig(hsts_enabled=False)
        middleware = SecurityHeadersMiddleware(app=Mock(), config=config)

        assert middleware._hsts_header is None


class TestAllHeadersDisabled:
    """Tests for fully disabled security headers."""

    def test_all_headers_can_be_disabled(self):
        """All security headers can be disabled if needed."""
        app = FastAPI()
        config = SecurityHeadersConfig(
            csp_enabled=False,
            hsts_enabled=False,
            x_frame_options=None,
            x_content_type_options=None,
            referrer_policy=None,
            permissions_policy=None,
            x_xss_protection=None,
        )
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        # None of the security headers should be present
        assert "Content-Security-Policy" not in response.headers
        assert "Strict-Transport-Security" not in response.headers
        assert "X-Frame-Options" not in response.headers
        assert "X-Content-Type-Options" not in response.headers
        assert "Referrer-Policy" not in response.headers
        assert "Permissions-Policy" not in response.headers
        assert "X-XSS-Protection" not in response.headers
