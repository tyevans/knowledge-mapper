"""
Base event classes for Knowledge Mapper.

All domain events in the application should inherit from TenantDomainEvent
to ensure proper multi-tenancy support.
"""

from uuid import UUID

from eventsource import DomainEvent

from app.core.context import get_current_tenant


class TenantDomainEvent(DomainEvent):
    """
    Base event class with required tenant_id for multi-tenancy.

    All domain events in Knowledge Mapper must include a tenant_id
    to ensure proper data isolation. This class makes tenant_id
    a required field (not optional as in the base DomainEvent).

    The tenant_id can be automatically populated from the current
    request context using the with_tenant_context() class method.

    Example:
        @register_event
        class StatementCreated(TenantDomainEvent):
            event_type: str = "StatementCreated"
            aggregate_type: str = "Statement"
            content: str
            author_id: UUID

        # Create with explicit tenant_id
        event = StatementCreated(
            aggregate_id=statement_id,
            tenant_id=tenant_id,
            content="Hello world",
            author_id=user_id,
        )

        # Or use context (within a request)
        event = StatementCreated.with_tenant_context(
            aggregate_id=statement_id,
            content="Hello world",
            author_id=user_id,
        )
    """

    # Override to make tenant_id required
    tenant_id: UUID

    @classmethod
    def with_tenant_context(cls, **kwargs) -> "TenantDomainEvent":
        """
        Create an event with tenant_id populated from the current request context.

        This is a convenience method for creating events within a request handler
        where the tenant context has been set by middleware.

        Args:
            **kwargs: Event field values (excluding tenant_id)

        Returns:
            Event instance with tenant_id from context

        Raises:
            ValueError: If no tenant context is available
        """
        tenant_id = get_current_tenant()
        if tenant_id is None:
            raise ValueError(
                "Cannot create event: no tenant context available. "
                "Ensure this is called within a request with tenant middleware."
            )
        return cls(tenant_id=tenant_id, **kwargs)
