# plugins/code_assistant/analyzers/__init__.py
"""Modular analyzers for Code Assistant & Code Intelligence."""

from .architecture import ArchitectureAnalyzer
from .circular import CircularDependencyDetector
from .complexity import ComplexityAnalyzer
from .coverage import CoverageAnalyzer
from .dead_code import DeadCodeAnalyzer
from .dependency import DependencyAnalyzer
from .duplication import DuplicateCodeDetector
from .health_audit import HealthAuditEngine
from .imports import ImportAnalyzer
from .performance import PerformanceAnalyzer
from .security import SecurityScanner

__all__ = [
    "ArchitectureAnalyzer",
    "CircularDependencyDetector",
    "ComplexityAnalyzer",
    "CoverageAnalyzer",
    "DeadCodeAnalyzer",
    "DependencyAnalyzer",
    "DuplicateCodeDetector",
    "HealthAuditEngine",
    "ImportAnalyzer",
    "PerformanceAnalyzer",
    "SecurityScanner",
]
