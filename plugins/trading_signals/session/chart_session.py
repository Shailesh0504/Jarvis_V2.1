# plugins/trading_signals/session/chart_session.py
"""
Authoritative TradingChartSession Context Object.
Sole authoritative owner of active trading window, instrument identity,
bounding regions, and session lifecycle status.
"""

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, Optional, Tuple

from ..models.data_feed_types import DataFeedState
from ..models.session_types import TradingSessionState

logger = logging.getLogger("jarvis.trading.session.context")


@dataclass
class TradingChartSession:
    """
    Authoritative context representation of an observed trading chart session.
    Decoupled strictly from OCR, vision, strategy, GUI, and TTS.
    """
    session_id: str
    browser_type: str = "unknown"
    hwnd: int = 0
    window_title: str = ""
    chart_roi: Optional[Any] = None
    instrument_identity: str = "NIFTY"
    index_chart_identity: str = "NIFTY 50"
    option_chart_identity: str = ""
    strike: int = 0
    expiry: str = ""
    option_type: str = "CE"
    ce_strike: int = 0
    ce_expiry: str = ""
    pe_strike: int = 0
    pe_expiry: str = ""
    discovered_panels: Dict[str, Any] = field(default_factory=dict)
    session_status: TradingSessionState = TradingSessionState.NO_SESSION
    last_validated_observation: Optional[Any] = None
    data_freshness_state: DataFeedState = DataFeedState.LIVE_AND_VALID
    created_timestamp: float = field(default_factory=time.time)
    last_active_timestamp: float = field(default_factory=time.time)
    paused_timestamp: Optional[float] = None
    pause_reason: str = ""
    invalid_reason: str = ""

    @property
    def state(self) -> TradingSessionState:
        """Alias for session_status."""
        return self.session_status

    @state.setter
    def state(self, value: TradingSessionState) -> None:
        self.session_status = value

    @property
    def activated_at(self) -> float:
        """Alias for created_timestamp."""
        return self.created_timestamp

    @property
    def last_seen_at(self) -> float:
        """Alias for last_active_timestamp."""
        return self.last_active_timestamp

    @property
    def underlying(self) -> str:
        """Alias for instrument_identity."""
        return self.instrument_identity

    @property
    def browser_title(self) -> str:
        """Alias for window_title."""
        return self.window_title

    @property
    def is_active(self) -> bool:
        """True only if session is confirmed ACTIVE."""
        return self.session_status == TradingSessionState.ACTIVE

    @property
    def is_paused(self) -> bool:
        """True if session is currently PAUSED."""
        return self.session_status == TradingSessionState.PAUSED

    def matches_window(self, hwnd: int, title: str) -> bool:
        """Checks whether the given HWND and title match this session."""
        if self.hwnd and hwnd and self.hwnd != hwnd:
            return False
        if not title:
            return False
        # Case-insensitive title match
        return "dhan" in title.lower() or (self.window_title and self.window_title.lower() in title.lower())

    def has_instrument_changed(
        self,
        strike: int,
        expiry: str,
        option_type: str,
        underlying: str = "NIFTY"
    ) -> bool:
        """
        Determines whether the visible chart instrument has switched
        (e.g., strike change, CE -> PE, PE -> CE, expiry change).
        """
        if self.strike > 0 and strike > 0 and self.strike != strike:
            return True
        if self.option_type and option_type and self.option_type.upper() != option_type.upper():
            return True
        if self.expiry and expiry and self.expiry.strip().lower() != expiry.strip().lower():
            return True
        if self.instrument_identity and underlying and self.instrument_identity.strip().lower() != underlying.strip().lower():
            return True
        return False

    def reset_instrument(
        self,
        strike: int,
        expiry: str,
        option_type: str,
        underlying: str = "NIFTY"
    ) -> None:
        """
        Updates session identity to the new contract and invalidates all stale instrument state.
        Guarantees zero stale breakout or Renko events leak across contract changes.
        """
        old_desc = f"{self.instrument_identity} {self.strike} {self.option_type}"
        self.instrument_identity = underlying
        self.strike = strike
        self.expiry = expiry
        self.option_type = option_type.upper()
        if self.option_type == "CE":
            self.ce_strike = strike
            self.ce_expiry = expiry
        elif self.option_type == "PE":
            self.pe_strike = strike
            self.pe_expiry = expiry
        self.last_validated_observation = None
        self.last_active_timestamp = time.time()
        logger.info(
            "[SESSION_INSTRUMENT_SWITCH] Session %s switched: %s -> %s %d %s (Stale state purged).",
            self.session_id,
            old_desc,
            underlying,
            strike,
            self.option_type
        )

    def has_panel_changed(
        self,
        panel_id: str,
        symbol: str,
        strike: int,
        option_type: str,
        expiry: str
    ) -> bool:
        """
        Determines if a tracked panel has changed its identity or contract.
        """
        if panel_id not in self.discovered_panels:
            return False
        prev = self.discovered_panels[panel_id]
        if prev.get("strike", 0) > 0 and strike > 0 and prev.get("strike") != strike:
            return True
        if prev.get("option_type") and option_type and prev.get("option_type").upper() != option_type.upper():
            return True
        if prev.get("expiry") and expiry and prev.get("expiry").strip().lower() != expiry.strip().lower():
            return True
        if prev.get("symbol") and symbol and prev.get("symbol").strip().lower() != symbol.strip().lower():
            return True
        return False

    def update_panel_contract(
        self,
        panel_id: str,
        symbol: str,
        strike: int,
        option_type: str,
        expiry: str
    ) -> None:
        """
        Updates tracked panel contract identity.
        """
        self.discovered_panels[panel_id] = {
            "symbol": symbol,
            "strike": strike,
            "option_type": option_type.upper() if option_type else "",
            "expiry": expiry,
            "updated_at": time.time()
        }
        if option_type.upper() == "CE":
            self.ce_strike = strike
            self.ce_expiry = expiry
        elif option_type.upper() == "PE":
            self.pe_strike = strike
            self.pe_expiry = expiry

    def pause(self, reason: str = "window_unfocused") -> None:
        """Transitions session to PAUSED."""
        if self.session_status != TradingSessionState.PAUSED:
            self.session_status = TradingSessionState.PAUSED
            self.paused_timestamp = time.time()
            self.pause_reason = reason
            logger.info("[SESSION_PAUSED] Session %s paused: %s", self.session_id, reason)

    def resume(self) -> None:
        """Transitions session back to ACTIVE."""
        self.session_status = TradingSessionState.ACTIVE
        self.paused_timestamp = None
        self.pause_reason = ""
        self.last_active_timestamp = time.time()
        logger.info("[SESSION_RESUMED] Session %s resumed to ACTIVE.", self.session_id)

    def invalidate(self, reason: str) -> None:
        """Transitions session to INVALID."""
        self.session_status = TradingSessionState.INVALID
        self.invalid_reason = reason
        self.last_validated_observation = None
        logger.warning("[SESSION_INVALID] Session %s marked INVALID: %s", self.session_id, reason)
