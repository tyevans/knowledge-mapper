"""
Tenant-aware projection base class for read models.

Provides a base class for projections that need to handle
multi-tenant event streams.
"""

import logging
from typing import Optional
from uuid import UUID

from eventsource import DomainEvent
from eventsource.projections import DeclarativeProjection
from eventsource.repositories import CheckpointRepository, DLQRepository

from app.core.context import get_current_tenant

logger = logging.getLogger(__name__)


class TenantAwareProjection(DeclarativeProjection):
    """
    Base class for tenant-aware projections.

    Extends DeclarativeProjection to filter events by tenant_id,
    ensuring projections only process events for the current tenant
    or a specified tenant filter.

    Example:
        class OrderSummaryProjection(TenantAwareProjection):
            def __init__(self, checkpoint_repo, tenant_id: UUID):
                super().__init__(
                    name="OrderSummary",
                    checkpoint_repo=checkpoint_repo,
                    tenant_filter=tenant_id,
                )
                self.orders: dict[UUID, dict] = {}

            @handles(OrderCreated)
            async def on_order_created(self, event: OrderCreated) -> None:
                self.orders[event.aggregate_id] = {
                    "status": "created",
                    "customer_id": event.customer_id,
                }

            async def reset(self) -> None:
                self.orders.clear()
    """

    def __init__(
        self,
        name: str,
        checkpoint_repo: Optional[CheckpointRepository] = None,
        dlq_repo: Optional[DLQRepository] = None,
        tenant_filter: Optional[UUID] = None,
        enable_tracing: bool = True,
    ):
        """
        Initialize the tenant-aware projection.

        Args:
            name: Unique name for checkpoint tracking
            checkpoint_repo: Repository for tracking position
            dlq_repo: Repository for failed events
            tenant_filter: If set, only process events for this tenant.
                          If None, uses current tenant context.
            enable_tracing: Enable OpenTelemetry tracing
        """
        super().__init__(
            name=name,
            checkpoint_repo=checkpoint_repo,
            dlq_repo=dlq_repo,
            enable_tracing=enable_tracing,
        )
        self._tenant_filter = tenant_filter

    def _get_tenant_filter(self) -> Optional[UUID]:
        """
        Get the tenant ID to filter events by.

        Returns the explicit tenant_filter if set, otherwise
        attempts to get the current tenant from context.
        """
        if self._tenant_filter is not None:
            return self._tenant_filter
        return get_current_tenant()

    async def handle(self, event: DomainEvent) -> None:
        """
        Process an event if it matches the tenant filter.

        Events without a tenant_id are processed by all projections.
        Events with a tenant_id are only processed if they match
        the tenant filter.

        Args:
            event: The domain event to process
        """
        # Check tenant filter
        tenant_filter = self._get_tenant_filter()
        if tenant_filter is not None:
            event_tenant_id = getattr(event, "tenant_id", None)
            if event_tenant_id is not None and event_tenant_id != tenant_filter:
                # Skip events for other tenants
                logger.debug(
                    "Skipping event for different tenant",
                    extra={
                        "projection": self.name,
                        "event_type": event.event_type,
                        "event_tenant": str(event_tenant_id),
                        "filter_tenant": str(tenant_filter),
                    },
                )
                return

        # Process the event
        await super().handle(event)
