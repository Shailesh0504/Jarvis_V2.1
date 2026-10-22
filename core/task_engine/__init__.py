# core/task_engine/__init__.py
"""
Task Continuity Engine package for Jarvis V2.
Exposes models, persistence, verifier, watchdog, diagnostics, experience, and engine.
"""

from .models import TaskState, TaskStep, TaskStatus, StepExecutionReport
from .persistence import TaskPersistenceManager
from .verifier import TaskVerifier
from .watchdog import TaskWatchdog
from .diagnostics import FailureDiagnoser, FailureDiagnosis
from .experience import ExperienceLearner
from .engine import TaskContinuityEngine

__all__ = [
    "TaskState",
    "TaskStep",
    "TaskStatus",
    "StepExecutionReport",
    "TaskPersistenceManager",
    "TaskVerifier",
    "TaskWatchdog",
    "FailureDiagnoser",
    "FailureDiagnosis",
    "ExperienceLearner",
    "TaskContinuityEngine",
]
