# plugins/trading_signals/gate/__init__.py
"""Pre-dispatch validation gate components."""

from .pre_dispatch_gate import PreDispatchRevalidationGate, PreDispatchValidationResult

__all__ = [
    "PreDispatchRevalidationGate",
    "PreDispatchValidationResult",
]
