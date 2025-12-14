"""
Pytest configuration and fixtures for testing.

Provides common fixtures for database testing and other shared test utilities.
"""

import asyncio
from pathlib import Path

import pytest


def pytest_configure(config):
    """
    Pytest hook that runs before test collection.

    This is the earliest point we can modify the environment.
    We load .env.test here to ensure it's available before any
    app modules are imported.
    """
    from dotenv import load_dotenv

    test_env_path = Path(__file__).parent.parent / ".env.test"
    if test_env_path.exists():
        load_dotenv(test_env_path, override=True)
        print(f"Loaded test environment from {test_env_path}")


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for async tests."""
    return "asyncio"


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Extraction Test Fixtures
# =============================================================================


@pytest.fixture
def sample_api_doc() -> str:
    """Sample API documentation content for testing extraction.

    Contains class definitions, inheritance, methods, and decorators
    that should be extracted as entities and relationships.

    Returns:
        API documentation string with DomainEvent and UserCreated classes.
    """
    return '''
## DomainEvent

Base class for all domain events in the system.

```python
from pydantic import BaseModel

class DomainEvent(BaseModel):
    """Base event class."""

    event_type: str
    aggregate_id: UUID
    aggregate_version: int
    occurred_at: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return self.model_dump()
```

### Inheritance

All domain events should inherit from `DomainEvent`:

```python
@register_event
class UserCreated(DomainEvent):
    event_type: str = "UserCreated"
    user_id: UUID
    email: str
```

The `@register_event` decorator registers the event with the event registry.
'''


@pytest.fixture
def sample_tutorial_doc() -> str:
    """Sample tutorial documentation content for testing extraction.

    Contains concepts, step-by-step patterns, and best practices
    that should be extracted as conceptual entities.

    Returns:
        Tutorial documentation string about event sourcing.
    """
    return '''
# Getting Started with Event Sourcing

Event sourcing is a pattern where application state changes are stored
as a sequence of events rather than mutating a current state.

## Core Concepts

### Events
Events represent facts that have happened in the system. They are immutable
and contain all information needed to reconstruct state.

### Aggregates
An aggregate is a cluster of domain objects that can be treated as a single
unit for data changes. Each aggregate has a root entity.

### Event Store
The event store is responsible for persisting and retrieving events.
It acts as the source of truth for the application.

## Basic Example

Here's how to create your first event:

```python
from eventsource import DomainEvent

class OrderCreated(DomainEvent):
    order_id: UUID
    customer_id: UUID
    total_amount: Decimal
```

## Best Practices

1. Events should be past-tense named (e.g., `OrderCreated` not `CreateOrder`)
2. Events should be immutable once created
3. Events should contain all data needed to apply the change

## Related Concepts

Event sourcing is often used together with:
- CQRS (Command Query Responsibility Segregation)
- Domain-Driven Design (DDD)
- Message Queuing
'''
