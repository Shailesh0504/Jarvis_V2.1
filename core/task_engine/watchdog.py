# core/task_engine/watchdog.py
"""
Watchdog and circuit breaker for long-horizon task execution.
Guards against infinite retry loops, deadlocks, hanging actions,
and runaway executions with configurable thresholds.
"""

import logging
import time
from typing import Optional, Tuple

from .models import TaskState, TaskStep

logger = logging.getLogger("jarvis.task_engine.watchdog")


class TaskWatchdog:
    """Monitors step execution, enforces retry limits, and prevents infinite loops."""

    def __init__(
        self,
        default_max_retries_per_step: int = 3,
        default_max_total_retries: int = 10,
        default_step_timeout_seconds: float = 30.0,
        task_timeout_seconds: float = 600.0,
        default_timeout: Optional[float] = None,
        max_retries_per_step: Optional[int] = None,
    ):
        self.max_retries_per_step = max_retries_per_step if max_retries_per_step is not None else default_max_retries_per_step
        self.max_total_retries = default_max_total_retries
        self.default_step_timeout = default_timeout if default_timeout is not None else default_step_timeout_seconds
        self.task_timeout = task_timeout_seconds
        self._step_start_times = {}

    def start_step_timer(self, step_id: str) -> None:
        self._step_start_times[step_id] = time.time()

    def check_step_timeout(self, step: TaskStep) -> Tuple[bool, float]:
        """Returns (has_timed_out, elapsed_seconds)."""
        started = self._step_start_times.get(step.step_id, time.time())
        elapsed = time.time() - started
        limit = step.timeout_seconds or self.default_step_timeout
        return (elapsed > limit), elapsed

    def can_retry_step(self, task: TaskState, step: TaskStep) -> Tuple[bool, str]:
        """
        Determines whether the step may be retried or if limits have been exceeded.
        Returns: (allowed: bool, reason: str)
        """
        step_attempts = task.step_retry_counts.get(step.step_id, 0)
        step_limit = step.max_retries or self.max_retries_per_step

        if step_attempts >= step_limit:
            msg = f"Step retry limit reached ({step_attempts}/{step_limit}) for step '{step.name or step.step_id}'"
            logger.warning("Watchdog: %s", msg)
            return False, msg

        if task.retry_count >= self.max_total_retries:
            msg = f"Task total retry limit reached ({task.retry_count}/{self.max_total_retries}) across all steps"
            logger.warning("Watchdog: %s", msg)
            return False, msg

        # Check total task duration
        task_elapsed = time.time() - task.created_at
        if task_elapsed > self.task_timeout:
            msg = f"Task overall execution deadline exceeded ({task_elapsed:.1f}s > {self.task_timeout:.1f}s)"
            logger.warning("Watchdog: %s", msg)
            return False, msg

        return True, "Retry permitted"

    def clear_step(self, step_id: str) -> None:
        self._step_start_times.pop(step_id, None)
