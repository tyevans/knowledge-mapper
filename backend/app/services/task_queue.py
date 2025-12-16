"""
Task queue abstraction layer.

This module provides an abstract interface for task queue operations,
enabling the application to be decoupled from specific task queue
implementations (e.g., Celery).

Follows the Dependency Inversion Principle: high-level modules (routers)
depend on abstractions (TaskQueueService), not on concrete implementations
(Celery).

Benefits:
- Testable without running Celery
- Swappable task queue backends
- Cleaner separation of concerns
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    """Task execution states."""

    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    REVOKED = "REVOKED"
    RETRY = "RETRY"


@dataclass
class TaskInfo:
    """Information about a submitted task."""

    task_id: str
    name: str
    state: TaskState = TaskState.PENDING


class TaskQueueService(ABC):
    """
    Abstract interface for task queue operations.

    This interface defines the contract that any task queue implementation
    must follow. It enables dependency injection and testability.

    Example usage with FastAPI dependency injection:
        @router.post("/jobs/{job_id}/stop")
        async def stop_job(
            job_id: UUID,
            task_queue: TaskQueueService = Depends(get_task_queue),
        ):
            task_queue.cancel_task(job.celery_task_id)
    """

    @abstractmethod
    def submit_task(
        self,
        task_name: str,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> TaskInfo:
        """
        Submit a task for async execution.

        Args:
            task_name: Fully qualified task name (e.g., "app.tasks.scraping.run_job")
            args: Positional arguments for the task
            kwargs: Keyword arguments for the task

        Returns:
            TaskInfo with the task ID
        """
        ...

    @abstractmethod
    def cancel_task(self, task_id: str, terminate: bool = True) -> bool:
        """
        Cancel a running or queued task.

        Args:
            task_id: ID of the task to cancel
            terminate: If True, forcefully terminate (SIGTERM)

        Returns:
            True if cancellation was requested successfully
        """
        ...

    @abstractmethod
    def get_task_state(self, task_id: str) -> TaskState:
        """
        Get the current state of a task.

        Args:
            task_id: ID of the task

        Returns:
            Current TaskState
        """
        ...


class CeleryTaskQueue(TaskQueueService):
    """
    Celery implementation of TaskQueueService.

    This implementation wraps the Celery app to provide task queue
    operations while maintaining the abstract interface.
    """

    def __init__(self):
        """Initialize with lazy Celery app loading."""
        self._app = None

    @property
    def app(self):
        """Lazy load Celery app to avoid import cycles."""
        if self._app is None:
            from app.celery_app import celery_app

            self._app = celery_app
        return self._app

    def submit_task(
        self,
        task_name: str,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> TaskInfo:
        """Submit a task to Celery for async execution."""
        task = self.app.send_task(
            task_name,
            args=args or (),
            kwargs=kwargs or {},
        )
        logger.info(
            "Task submitted",
            extra={"task_id": task.id, "task_name": task_name},
        )
        return TaskInfo(task_id=task.id, name=task_name)

    def cancel_task(self, task_id: str, terminate: bool = True) -> bool:
        """Cancel a Celery task by revoking it."""
        try:
            self.app.control.revoke(task_id, terminate=terminate)
            logger.info(
                "Task revoked",
                extra={"task_id": task_id, "terminate": terminate},
            )
            return True
        except Exception as e:
            logger.warning(
                f"Failed to revoke task {task_id}: {e}",
                extra={"task_id": task_id, "error": str(e)},
            )
            return False

    def get_task_state(self, task_id: str) -> TaskState:
        """Get task state from Celery."""
        try:
            result = self.app.AsyncResult(task_id)
            state_map = {
                "PENDING": TaskState.PENDING,
                "STARTED": TaskState.STARTED,
                "SUCCESS": TaskState.SUCCESS,
                "FAILURE": TaskState.FAILURE,
                "REVOKED": TaskState.REVOKED,
                "RETRY": TaskState.RETRY,
            }
            return state_map.get(result.state, TaskState.PENDING)
        except Exception as e:
            logger.warning(
                f"Failed to get task state for {task_id}: {e}",
                extra={"task_id": task_id, "error": str(e)},
            )
            return TaskState.PENDING


class InMemoryTaskQueue(TaskQueueService):
    """
    In-memory implementation for testing.

    This implementation stores tasks in memory and can be used
    in unit tests without requiring a running Celery broker.
    """

    def __init__(self):
        """Initialize with empty task storage."""
        self._tasks: dict[str, TaskInfo] = {}
        self._next_id = 1

    def submit_task(
        self,
        task_name: str,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> TaskInfo:
        """Submit a task to in-memory storage."""
        task_id = f"test-task-{self._next_id}"
        self._next_id += 1
        task_info = TaskInfo(task_id=task_id, name=task_name)
        self._tasks[task_id] = task_info
        return task_info

    def cancel_task(self, task_id: str, terminate: bool = True) -> bool:
        """Cancel a task in memory."""
        if task_id in self._tasks:
            self._tasks[task_id].state = TaskState.REVOKED
            return True
        return False

    def get_task_state(self, task_id: str) -> TaskState:
        """Get task state from memory."""
        task = self._tasks.get(task_id)
        return task.state if task else TaskState.PENDING

    def clear(self) -> None:
        """Clear all tasks (useful in tests)."""
        self._tasks.clear()
        self._next_id = 1


# Singleton instance for dependency injection
_task_queue: TaskQueueService | None = None


def get_task_queue() -> TaskQueueService:
    """
    Get the task queue service instance.

    This function is designed for use with FastAPI's Depends():
        task_queue: TaskQueueService = Depends(get_task_queue)

    Returns:
        TaskQueueService implementation
    """
    global _task_queue
    if _task_queue is None:
        _task_queue = CeleryTaskQueue()
    return _task_queue


def set_task_queue(queue: TaskQueueService) -> None:
    """
    Set the task queue service instance.

    Useful for testing to inject a mock implementation:
        set_task_queue(InMemoryTaskQueue())

    Args:
        queue: TaskQueueService implementation to use
    """
    global _task_queue
    _task_queue = queue


def reset_task_queue() -> None:
    """Reset the task queue to default (Celery)."""
    global _task_queue
    _task_queue = None
