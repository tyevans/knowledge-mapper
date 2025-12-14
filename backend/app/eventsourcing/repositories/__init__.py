"""Tenant-aware repositories for event-sourced aggregates."""

from app.eventsourcing.repositories.base import TenantAwareRepository

__all__ = ["TenantAwareRepository"]
