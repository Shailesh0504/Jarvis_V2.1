# plugins/trading_signals/session/__init__.py
"""Session management and automatic discovery subsystem."""

from .chart_session import TradingChartSession
from .session_detector import SessionClassificationResult, TradingSessionDetector
from .panel_classifier import PanelRoleClassifier
from .session_coordinator import SessionCoordinator

__all__ = [
    "TradingChartSession",
    "SessionClassificationResult",
    "TradingSessionDetector",
    "SessionCoordinator",
    "PanelRoleClassifier"
]
