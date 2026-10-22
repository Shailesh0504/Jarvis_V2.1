# plugins/trading_signals/models/session_types.py
"""
Session Lifecycle and Browser State Models for Automatic Trading Discovery.
Kept strictly orthogonal to DataFeedState and SignalState.
"""

from enum import Enum


class BrowserState(str, Enum):
    """Foreground / background presence of a supported browser."""
    BROWSER_FOREGROUND = "BROWSER_FOREGROUND"
    BROWSER_BACKGROUND = "BROWSER_BACKGROUND"
    BROWSER_NOT_SUPPORTED = "BROWSER_NOT_SUPPORTED"


class TradingSessionState(str, Enum):
    """
    Deterministic lifecycle state for automated trading chart sessions.
    Transitions happen silently without speaking every state change.
    """
    NO_SESSION = "NO_SESSION"                          # No trading chart present
    TRADING_PAGE_DETECTED = "TRADING_PAGE_DETECTED"    # Candidate URL or window title observed
    VALIDATING = "VALIDATING"                          # Visual layout and indicators undergoing inspection
    ACTIVE = "ACTIVE"                                  # Confirmed chart active; strategy evaluating
    PAUSED = "PAUSED"                                  # Minimized, alt-tabbed, or tab switched away
    INVALID = "INVALID"                                # Incompatible layout or missing required indicators
