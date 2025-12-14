"""
Unit tests for extraction health check endpoints.

Tests all extraction health endpoints with mocked services:
- /health/extraction (aggregated health)
- /health/ollama (Ollama connectivity)
- /health/neo4j (Neo4j connectivity)
- /health/circuit-breaker (circuit breaker status)
- /health/rate-limiter (rate limiter status)
- /health/subscriptions (subscription manager status)
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Pre-create mock modules before importing the router
# This allows us to patch the imports that happen inside the endpoint functions

# Mock settings
_mock_settings = MagicMock()
_mock_settings.REDIS_URL = "redis://localhost:6379/0"
_mock_settings.OLLAMA_BASE_URL = "http://localhost:11434"
_mock_settings.OLLAMA_MODEL = "gemma3:12b"
_mock_settings.OLLAMA_TIMEOUT = 60
_mock_settings.OLLAMA_MAX_CONTEXT_LENGTH = 10000
_mock_settings.OLLAMA_RATE_LIMIT_RPM = 60
_mock_settings.NEO4J_URI = "bolt://localhost:7687"
_mock_settings.NEO4J_USER = "neo4j"
_mock_settings.NEO4J_PASSWORD = "password"
_mock_settings.NEO4J_DATABASE = "neo4j"
_mock_settings.NEO4J_MAX_CONNECTION_POOL_SIZE = 50
_mock_settings.NEO4J_CONNECTION_TIMEOUT = 30.0

# Create mock config module
_mock_config_module = MagicMock()
_mock_config_module.settings = _mock_settings

# Insert mock config into sys.modules
sys.modules.setdefault("app.core.config", _mock_config_module)

# Mock the extraction modules
_mock_ollama_extractor = MagicMock()
sys.modules.setdefault("app.extraction.ollama_extractor", _mock_ollama_extractor)

_mock_circuit_breaker = MagicMock()
sys.modules.setdefault("app.extraction.circuit_breaker", _mock_circuit_breaker)

_mock_rate_limiter = MagicMock()
sys.modules.setdefault("app.extraction.rate_limiter", _mock_rate_limiter)

# Mock the services module
_mock_neo4j_service = MagicMock()
sys.modules.setdefault("app.services.neo4j", _mock_neo4j_service)

# Mock eventsourcing subscriptions
_mock_subscriptions = MagicMock()
sys.modules.setdefault("app.eventsourcing.subscriptions", _mock_subscriptions)

# Now import the router - the imports inside the functions will use our mocks
from app.api.routers.health_extraction import router


@pytest.fixture
def test_app():
    """Create a minimal test app with just the health_extraction router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def test_client(test_app):
    """FastAPI test client."""
    return TestClient(test_app)


# ==============================================================================
# Ollama Health Tests
# ==============================================================================


class TestOllamaHealth:
    """Tests for /health/ollama endpoint."""

    def test_ollama_healthy(self, test_client):
        """Test /health/ollama returns 200 when Ollama is healthy."""
        mock_service = MagicMock()
        mock_service.health_check = AsyncMock(
            return_value={
                "status": "healthy",
                "base_url": "http://localhost:11434",
                "model": "gemma3:12b",
                "available_models": ["gemma3:12b", "llama2:7b"],
                "model_available": True,
            }
        )

        _mock_ollama_extractor.get_ollama_extraction_service = MagicMock(return_value=mock_service)

        response = test_client.get("/api/v1/health/ollama")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "healthy"
        assert json_data["base_url"] == "http://localhost:11434"
        assert json_data["model"] == "gemma3:12b"
        assert json_data["model_available"] is True
        assert "gemma3:12b" in json_data["available_models"]

    def test_ollama_unhealthy_connection_error(self, test_client):
        """Test /health/ollama returns 503 when Ollama connection fails."""
        mock_service = MagicMock()
        mock_service.health_check = AsyncMock(
            return_value={
                "status": "unhealthy",
                "base_url": "http://localhost:11434",
                "model": "gemma3:12b",
                "error": "Connection failed: Connection refused",
            }
        )

        _mock_ollama_extractor.get_ollama_extraction_service = MagicMock(return_value=mock_service)

        response = test_client.get("/api/v1/health/ollama")

        assert response.status_code == 503
        json_data = response.json()
        assert json_data["detail"]["status"] == "unhealthy"
        assert "Connection failed" in json_data["detail"]["error"]

    def test_ollama_health_exception(self, test_client):
        """Test /health/ollama returns 503 on unexpected exception."""
        _mock_ollama_extractor.get_ollama_extraction_service = MagicMock(
            side_effect=Exception("Service initialization failed")
        )

        response = test_client.get("/api/v1/health/ollama")

        assert response.status_code == 503
        json_data = response.json()
        assert json_data["detail"]["status"] == "unhealthy"
        assert "Service initialization failed" in json_data["detail"]["error"]


# ==============================================================================
# Neo4j Health Tests
# ==============================================================================


class TestNeo4jHealth:
    """Tests for /health/neo4j endpoint."""

    def test_neo4j_healthy(self, test_client):
        """Test /health/neo4j returns 200 when Neo4j is healthy."""
        mock_service = MagicMock()
        mock_service.health_check = AsyncMock(
            return_value={
                "status": "healthy",
                "uri": "bolt://localhost:7687",
                "database": "neo4j",
                "latency_ms": 5.23,
            }
        )

        async def mock_get_neo4j_service():
            return mock_service

        _mock_neo4j_service.get_neo4j_service = mock_get_neo4j_service

        response = test_client.get("/api/v1/health/neo4j")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "healthy"
        assert json_data["uri"] == "bolt://localhost:7687"
        assert json_data["database"] == "neo4j"
        assert json_data["latency_ms"] == 5.23

    def test_neo4j_unhealthy(self, test_client):
        """Test /health/neo4j returns 503 when Neo4j is unhealthy."""
        mock_service = MagicMock()
        mock_service.health_check = AsyncMock(
            return_value={
                "status": "unhealthy",
                "uri": "bolt://localhost:7687",
                "database": "neo4j",
                "error": "Connection refused",
            }
        )

        async def mock_get_neo4j_service():
            return mock_service

        _mock_neo4j_service.get_neo4j_service = mock_get_neo4j_service

        response = test_client.get("/api/v1/health/neo4j")

        assert response.status_code == 503
        json_data = response.json()
        assert json_data["detail"]["status"] == "unhealthy"
        assert "Connection refused" in json_data["detail"]["error"]

    def test_neo4j_health_exception(self, test_client):
        """Test /health/neo4j returns 503 on unexpected exception."""

        async def mock_get_neo4j_service():
            raise Exception("Driver not connected")

        _mock_neo4j_service.get_neo4j_service = mock_get_neo4j_service

        response = test_client.get("/api/v1/health/neo4j")

        assert response.status_code == 503
        json_data = response.json()
        assert json_data["detail"]["status"] == "unhealthy"
        assert "Driver not connected" in json_data["detail"]["error"]


# ==============================================================================
# Circuit Breaker Health Tests
# ==============================================================================


class TestCircuitBreakerHealth:
    """Tests for /health/circuit-breaker endpoint."""

    def test_circuit_breaker_closed(self, test_client):
        """Test /health/circuit-breaker returns 200 with closed state."""
        mock_breaker = MagicMock()
        mock_breaker.failure_threshold = 5
        mock_breaker.recovery_timeout = 60

        mock_state = MagicMock()
        mock_state.value = "closed"
        mock_breaker.get_state = AsyncMock(return_value=mock_state)
        mock_breaker.get_retry_after = AsyncMock(return_value=0.0)

        _mock_circuit_breaker.get_circuit_breaker = MagicMock(return_value=mock_breaker)

        response = test_client.get("/api/v1/health/circuit-breaker")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "healthy"
        assert json_data["state"] == "closed"
        assert json_data["failure_threshold"] == 5
        assert json_data["recovery_timeout"] == 60
        assert json_data["retry_after"] is None

    def test_circuit_breaker_open(self, test_client):
        """Test /health/circuit-breaker returns 200 with open state and retry_after."""
        mock_breaker = MagicMock()
        mock_breaker.failure_threshold = 5
        mock_breaker.recovery_timeout = 60

        mock_state = MagicMock()
        mock_state.value = "open"
        mock_breaker.get_state = AsyncMock(return_value=mock_state)
        mock_breaker.get_retry_after = AsyncMock(return_value=45.5)

        _mock_circuit_breaker.get_circuit_breaker = MagicMock(return_value=mock_breaker)

        response = test_client.get("/api/v1/health/circuit-breaker")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "healthy"
        assert json_data["state"] == "open"
        assert json_data["retry_after"] == 45.5

    def test_circuit_breaker_half_open(self, test_client):
        """Test /health/circuit-breaker returns 200 with half_open state."""
        mock_breaker = MagicMock()
        mock_breaker.failure_threshold = 5
        mock_breaker.recovery_timeout = 60

        mock_state = MagicMock()
        mock_state.value = "half_open"
        mock_breaker.get_state = AsyncMock(return_value=mock_state)
        mock_breaker.get_retry_after = AsyncMock(return_value=0.0)

        _mock_circuit_breaker.get_circuit_breaker = MagicMock(return_value=mock_breaker)

        response = test_client.get("/api/v1/health/circuit-breaker")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "healthy"
        assert json_data["state"] == "half_open"

    def test_circuit_breaker_exception(self, test_client):
        """Test /health/circuit-breaker returns 503 on exception."""
        _mock_circuit_breaker.get_circuit_breaker = MagicMock(
            side_effect=Exception("Redis connection failed")
        )

        response = test_client.get("/api/v1/health/circuit-breaker")

        assert response.status_code == 503
        json_data = response.json()
        assert json_data["detail"]["status"] == "unhealthy"
        assert "Redis connection failed" in json_data["detail"]["error"]


# ==============================================================================
# Rate Limiter Health Tests
# ==============================================================================


class TestRateLimiterHealth:
    """Tests for /health/rate-limiter endpoint."""

    def test_rate_limiter_healthy(self, test_client):
        """Test /health/rate-limiter returns 200 with configuration."""
        mock_limiter = MagicMock()
        mock_limiter._rpm = 60
        mock_limiter._window = 60

        _mock_rate_limiter.get_rate_limiter = MagicMock(return_value=mock_limiter)

        response = test_client.get("/api/v1/health/rate-limiter")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "healthy"
        assert json_data["requests_per_minute"] == 60
        assert json_data["window_seconds"] == 60

    def test_rate_limiter_exception(self, test_client):
        """Test /health/rate-limiter returns 503 on exception."""
        _mock_rate_limiter.get_rate_limiter = MagicMock(
            side_effect=Exception("Redis connection failed")
        )

        response = test_client.get("/api/v1/health/rate-limiter")

        assert response.status_code == 503
        json_data = response.json()
        assert json_data["detail"]["status"] == "unhealthy"
        assert "Redis connection failed" in json_data["detail"]["error"]


# ==============================================================================
# Subscription Manager Health Tests
# ==============================================================================


class TestSubscriptionsHealth:
    """Tests for /health/subscriptions endpoint."""

    def test_subscriptions_running(self, test_client):
        """Test /health/subscriptions returns 200 when running."""
        mock_manager = MagicMock()
        mock_manager.is_running = True
        mock_manager.get_health.return_value = {
            "status": "healthy",
            "subscription_count": 3,
            "subscriptions": [
                "EntityProjection",
                "RelationshipProjection",
                "ExtractionProcessProjection",
            ],
        }

        async def mock_get_subscription_manager():
            return mock_manager

        _mock_subscriptions.get_subscription_manager = mock_get_subscription_manager

        response = test_client.get("/api/v1/health/subscriptions")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "healthy"
        assert json_data["running"] is True
        assert json_data["subscription_count"] == 3
        assert "EntityProjection" in json_data["subscriptions"]

    def test_subscriptions_stopped(self, test_client):
        """Test /health/subscriptions returns 200 with 'stopped' status when not running."""
        mock_manager = MagicMock()
        mock_manager.is_running = False
        mock_manager.get_health.return_value = {
            "status": "stopped",
            "subscription_count": 0,
            "subscriptions": [],
        }

        async def mock_get_subscription_manager():
            return mock_manager

        _mock_subscriptions.get_subscription_manager = mock_get_subscription_manager

        response = test_client.get("/api/v1/health/subscriptions")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "stopped"
        assert json_data["running"] is False

    def test_subscriptions_exception(self, test_client):
        """Test /health/subscriptions returns 503 on exception."""

        async def mock_get_subscription_manager():
            raise Exception("Kafka connection failed")

        _mock_subscriptions.get_subscription_manager = mock_get_subscription_manager

        response = test_client.get("/api/v1/health/subscriptions")

        assert response.status_code == 503
        json_data = response.json()
        assert json_data["detail"]["status"] == "unhealthy"
        assert "Kafka connection failed" in json_data["detail"]["error"]


# ==============================================================================
# Aggregated Extraction Health Tests
# ==============================================================================


class TestExtractionHealth:
    """Tests for /health/extraction aggregated endpoint."""

    def _setup_all_healthy_mocks(self):
        """Setup all mocks for healthy components."""
        # Mock Ollama service
        mock_ollama = MagicMock()
        mock_ollama.health_check = AsyncMock(
            return_value={
                "status": "healthy",
                "base_url": "http://localhost:11434",
                "model": "gemma3:12b",
                "model_available": True,
            }
        )
        _mock_ollama_extractor.get_ollama_extraction_service = MagicMock(return_value=mock_ollama)

        # Mock Neo4j service
        mock_neo4j = MagicMock()
        mock_neo4j.health_check = AsyncMock(
            return_value={
                "status": "healthy",
                "uri": "bolt://localhost:7687",
                "database": "neo4j",
                "latency_ms": 5.0,
            }
        )

        async def mock_get_neo4j():
            return mock_neo4j

        _mock_neo4j_service.get_neo4j_service = mock_get_neo4j

        # Mock Circuit Breaker
        mock_breaker = MagicMock()
        mock_breaker.failure_threshold = 5
        mock_breaker.recovery_timeout = 60
        mock_state = MagicMock()
        mock_state.value = "closed"
        mock_breaker.get_state = AsyncMock(return_value=mock_state)
        mock_breaker.get_retry_after = AsyncMock(return_value=0.0)
        _mock_circuit_breaker.get_circuit_breaker = MagicMock(return_value=mock_breaker)

        # Mock Rate Limiter
        mock_limiter = MagicMock()
        mock_limiter._rpm = 60
        mock_limiter._window = 60
        _mock_rate_limiter.get_rate_limiter = MagicMock(return_value=mock_limiter)

        # Mock Subscription Manager
        mock_sub_manager = MagicMock()
        mock_sub_manager.is_running = True
        mock_sub_manager.get_health.return_value = {
            "subscription_count": 3,
            "subscriptions": ["EntityProjection"],
        }

        async def mock_get_subscription_manager():
            return mock_sub_manager

        _mock_subscriptions.get_subscription_manager = mock_get_subscription_manager

    def test_extraction_all_healthy(self, test_client):
        """Test /health/extraction returns 'healthy' when all components are healthy."""
        self._setup_all_healthy_mocks()

        response = test_client.get("/api/v1/health/extraction")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "healthy"
        assert "ollama" in json_data["components"]
        assert "neo4j" in json_data["components"]
        assert "circuit_breaker" in json_data["components"]
        assert "rate_limiter" in json_data["components"]
        assert "subscriptions" in json_data["components"]
        assert json_data["components"]["ollama"]["status"] == "healthy"
        assert json_data["components"]["neo4j"]["status"] == "healthy"
        assert json_data["components"]["circuit_breaker"]["status"] == "healthy"
        assert json_data["components"]["rate_limiter"]["status"] == "healthy"
        assert json_data["components"]["subscriptions"]["status"] == "healthy"

    def test_extraction_degraded_when_ollama_unhealthy(self, test_client):
        """Test /health/extraction returns 'degraded' when Ollama is unhealthy."""
        # Setup most mocks as healthy
        self._setup_all_healthy_mocks()

        # Override Ollama to be unhealthy
        mock_ollama = MagicMock()
        mock_ollama.health_check = AsyncMock(
            return_value={
                "status": "unhealthy",
                "base_url": "http://localhost:11434",
                "model": "gemma3:12b",
                "error": "Connection refused",
            }
        )
        _mock_ollama_extractor.get_ollama_extraction_service = MagicMock(return_value=mock_ollama)

        response = test_client.get("/api/v1/health/extraction")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "degraded"
        assert json_data["components"]["ollama"]["status"] == "unhealthy"
        assert json_data["components"]["neo4j"]["status"] == "healthy"

    def test_extraction_handles_component_exceptions(self, test_client):
        """Test /health/extraction handles exceptions from individual components."""
        # Setup most mocks as healthy
        self._setup_all_healthy_mocks()

        # Override Ollama to raise exception
        _mock_ollama_extractor.get_ollama_extraction_service = MagicMock(
            side_effect=Exception("Ollama initialization failed")
        )

        response = test_client.get("/api/v1/health/extraction")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "degraded"
        assert json_data["components"]["ollama"]["status"] == "unhealthy"
        assert "Ollama initialization failed" in json_data["components"]["ollama"]["error"]
        # Other components should still report their status
        assert json_data["components"]["neo4j"]["status"] == "healthy"

    def test_extraction_stopped_subscriptions_not_degraded(self, test_client):
        """Test /health/extraction treats 'stopped' subscriptions as acceptable."""
        # Setup all mocks as healthy
        self._setup_all_healthy_mocks()

        # Override subscriptions to be stopped
        mock_sub_manager = MagicMock()
        mock_sub_manager.is_running = False
        mock_sub_manager.get_health.return_value = {"subscription_count": 0, "subscriptions": []}

        async def mock_get_subscription_manager():
            return mock_sub_manager

        _mock_subscriptions.get_subscription_manager = mock_get_subscription_manager

        response = test_client.get("/api/v1/health/extraction")

        assert response.status_code == 200
        json_data = response.json()
        # Stopped is acceptable - not degraded
        assert json_data["status"] == "healthy"
        assert json_data["components"]["subscriptions"]["status"] == "stopped"
