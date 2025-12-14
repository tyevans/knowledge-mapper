"""
Unit tests for health check endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI application."""
    return TestClient(app)


class TestHealthEndpoint:
    """Test suite for the health check endpoint."""

    def test_health_check_returns_200(self, client: TestClient) -> None:
        """Test that health check returns 200 OK status."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_check_returns_correct_structure(self, client: TestClient) -> None:
        """Test that health check returns expected JSON structure."""
        response = client.get("/api/v1/health")
        data = response.json()

        assert "status" in data
        assert "service" in data
        assert "version" in data
        assert "timestamp" in data

    def test_health_check_status_is_healthy(self, client: TestClient) -> None:
        """Test that health check status is 'healthy'."""
        response = client.get("/api/v1/health")
        data = response.json()

        assert data["status"] == "healthy"

    def test_health_check_service_name(self, client: TestClient) -> None:
        """Test that health check returns correct service name."""
        response = client.get("/api/v1/health")
        data = response.json()

        assert data["service"] == settings.APP_NAME

    def test_health_check_timestamp_is_valid(self, client: TestClient) -> None:
        """Test that health check timestamp is valid ISO format."""
        response = client.get("/api/v1/health")
        data = response.json()

        # Should be able to parse as ISO datetime
        timestamp = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        assert isinstance(timestamp, datetime)


class TestReadinessEndpoint:
    """Test suite for the readiness check endpoint."""

    def test_readiness_check_returns_200(self, client: TestClient) -> None:
        """Test that readiness check returns 200 OK status."""
        response = client.get("/api/v1/ready")
        assert response.status_code == 200

    def test_readiness_check_returns_correct_structure(self, client: TestClient) -> None:
        """Test that readiness check returns expected JSON structure."""
        response = client.get("/api/v1/ready")
        data = response.json()

        assert "status" in data
        assert "service" in data
        assert "version" in data
        assert "timestamp" in data

    def test_readiness_check_status_is_ready(self, client: TestClient) -> None:
        """Test that readiness check status is 'ready'."""
        response = client.get("/api/v1/ready")
        data = response.json()

        assert data["status"] == "ready"


class TestRootEndpoint:
    """Test suite for the root endpoint."""

    def test_root_endpoint_returns_200(self, client: TestClient) -> None:
        """Test that root endpoint returns 200 OK status."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_endpoint_returns_api_info(self, client: TestClient) -> None:
        """Test that root endpoint returns API information."""
        response = client.get("/")
        data = response.json()

        assert "service" in data
        assert "version" in data
        assert "docs" in data
        assert "health" in data

    def test_root_endpoint_docs_url(self, client: TestClient) -> None:
        """Test that root endpoint provides correct docs URL."""
        response = client.get("/")
        data = response.json()

        assert data["docs"] == "/docs"

    def test_root_endpoint_health_url(self, client: TestClient) -> None:
        """Test that root endpoint provides correct health URL."""
        response = client.get("/")
        data = response.json()

        assert data["health"] == "/api/v1/health"
