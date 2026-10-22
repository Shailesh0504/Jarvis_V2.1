# core/desktop_task/__init__.py
"""Desktop task planning, context resolution, and verified execution package."""

from .action_registry import FilesystemActionRegistry, TaskActionResult
from .context import DesktopExecutionContext, TaskExecutionContext
from .executor import DesktopExecutionReport, DesktopTaskExecutor
from .planner import AtomicTaskStep, DesktopTaskPlan, DesktopTaskPlanner

__all__ = [
    "FilesystemActionRegistry",
    "TaskActionResult",
    "DesktopExecutionContext",
    "TaskExecutionContext",
    "DesktopTaskPlanner",
    "DesktopTaskPlan",
    "AtomicTaskStep",
    "DesktopTaskExecutor",
    "DesktopExecutionReport",
]
