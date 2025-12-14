"""
Integration tests for backend.

These tests validate the system works correctly with real external services:
- Keycloak (OAuth provider)
- Redis (caching and token blacklist)
- PostgreSQL (data persistence)

Run with: pytest backend/tests/integration/ -v
"""
