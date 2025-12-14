"""
Test settings override for integration tests.

Integration tests run INSIDE Docker containers and connect to services
via Docker service names and internal container ports.
"""

import os
from app.core.config import Settings


def get_integration_test_settings() -> Settings:
    """
    Get settings configured for integration tests.

    Uses Docker service names and internal container ports for Docker network access.
    """
    # Override environment for integration tests running inside Docker
    os.environ["OAUTH_ISSUER_URL"] = "http://keycloak:8080/realms/knowledge-mapper-dev"
    os.environ["REDIS_URL"] = "redis://default:knowledge_mapper_redis_pass@redis:6379/0"
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://knowledge_mapper_app_user:app_password_dev@postgres:5432/knowledge_mapper_db"

    return Settings()
