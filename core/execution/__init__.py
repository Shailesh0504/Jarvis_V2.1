# core/execution/__init__.py
"""
Execution Verification Layer package for Jarvis V2.
Decouples command execution completion from task success and enforces
observable system state verification before claiming success.
"""

from .models import ActionPlan, ExecutionResult, ExecutionState, VerificationResult
from .verifier import ExecutionVerificationLayer, get_execution_verifier
from .diagnostics import ExecutionDiagnosticEngine
from .strategies import ExecutionStrategyEngine
from .feedback import ExecutionFeedbackHandler
from .fast_path import FastPathEngine
from .semantic_executor import SemanticActionExecutor
from .plugin_verifier import PluginVerificationBridge

__all__ = [
    "ActionPlan",
    "ExecutionState",
    "VerificationResult",
    "ExecutionResult",
    "ExecutionVerificationLayer",
    "get_execution_verifier",
    "ExecutionDiagnosticEngine",
    "ExecutionStrategyEngine",
    "ExecutionFeedbackHandler",
    "FastPathEngine",
    "SemanticActionExecutor",
    "PluginVerificationBridge",
]
