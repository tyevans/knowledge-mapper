"""
Subscription management for event processing.

This module provides the subscription infrastructure for coordinating
projection handlers and managing event processing lifecycles.

Components:
    - ExtractionSubscriptionManager: Main manager wrapping eventsource-py
    - get_subscription_manager: Factory function for singleton instance
    - close_subscription_manager: Cleanup function for shutdown

Usage:
    >>> from app.eventsourcing.subscriptions import get_subscription_manager
    >>> manager = await get_subscription_manager()
    >>> await manager.start()
    >>> # ... events are now being processed ...
    >>> await manager.stop()
"""

from app.eventsourcing.subscriptions.manager import (
    ExtractionSubscriptionManager,
    get_subscription_manager,
    close_subscription_manager,
)

__all__ = [
    "ExtractionSubscriptionManager",
    "get_subscription_manager",
    "close_subscription_manager",
]
