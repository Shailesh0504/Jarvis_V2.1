# plugins/trading_signals/strategy/__init__.py
"""Trading strategy components for confluence and exit evaluation."""

from .confluence_engine import ConfluenceSignalEngine, ConfluenceEvaluationResult
from .exit_evaluator import ExitEvaluator, ExitEvaluationResult

__all__ = [
    "ConfluenceSignalEngine",
    "ConfluenceEvaluationResult",
    "ExitEvaluator",
    "ExitEvaluationResult",
]
