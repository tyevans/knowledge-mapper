"""Event store factory and configuration."""

from app.eventsourcing.stores.factory import (
    get_event_store,
    get_event_store_sync,
    create_event_store,
    create_sync_event_store,
    close_event_store,
)

__all__ = [
    "get_event_store",
    "get_event_store_sync",
    "create_event_store",
    "create_sync_event_store",
    "close_event_store",
]
