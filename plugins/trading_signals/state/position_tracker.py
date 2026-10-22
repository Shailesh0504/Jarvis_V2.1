# plugins/trading_signals/state/position_tracker.py
"""
Position-Aware Recommendation Lifecycle State Tracker.
Maintains the binding invariant: JARVIS_SIGNAL_ACTIVE != ACTUAL_BROKER_POSITION.
Inhibits EXIT signals when FLAT.
"""

from dataclasses import dataclass, field
import logging
import time
from typing import Optional

from ..models.signal_types import PositionState, SignalType, CandidateSignal, ExitReason

logger = logging.getLogger("jarvis.trading.state.position")


@dataclass
class ActiveSignalRecord:
    """Snapshot of the active recommendation currently tracked."""
    signal_id: str
    underlying: str
    strike: int
    option_type: str
    entry_price: float
    entry_timestamp: float
    last_confirmed_brick_id: int
    exit_warning_count: int = 0


class PositionStateTracker:
    """
    State machine governing the recommendation lifecycle.
    Decoupled strictly from broker fills or financial balance.
    """

    def __init__(self, cooldown_seconds: float = 30.0):
        self.state: PositionState = PositionState.FLAT
        self.cooldown_seconds = max(5.0, float(cooldown_seconds))
        self.active_signal: Optional[ActiveSignalRecord] = None
        self._last_exit_time: float = 0.0

    @property
    def is_flat(self) -> bool:
        """True if no Jarvis recommendation is actively tracked."""
        return self.state in (PositionState.FLAT, PositionState.COOLDOWN)

    @property
    def is_active(self) -> bool:
        """True if an active recommendation is undergoing lifecycle monitoring."""
        return self.state in (
            PositionState.BUY_SIGNAL_DISPATCHED,
            PositionState.JARVIS_SIGNAL_ACTIVE,
            PositionState.EXIT_WARNING_1_BRICK
        )

    def can_evaluate_buy(self) -> bool:
        """BUY evaluation is allowed only when FLAT and not in cooldown."""
        if self.state == PositionState.COOLDOWN:
            if time.time() - self._last_exit_time >= self.cooldown_seconds:
                logger.info("[STATE_TRANSITION] Cooldown elapsed. Transitioning from COOLDOWN -> FLAT.")
                self.state = PositionState.FLAT
                return True
            return False
        return self.state == PositionState.FLAT

    def can_evaluate_exit(self) -> bool:
        """EXIT evaluation is strictly prohibited while FLAT or UNKNOWN."""
        return self.is_active

    def on_buy_signal_dispatched(self, candidate: CandidateSignal) -> None:
        """
        Transitions state to JARVIS_SIGNAL_ACTIVE upon successful pre-dispatch revalidation.
        """
        self.state = PositionState.JARVIS_SIGNAL_ACTIVE
        self.active_signal = ActiveSignalRecord(
            signal_id=f"{candidate.underlying}_{candidate.strike}_{candidate.option_type}_{int(candidate.timestamp)}",
            underlying=candidate.underlying,
            strike=candidate.strike,
            option_type=candidate.option_type,
            entry_price=candidate.price,
            entry_timestamp=candidate.timestamp,
            last_confirmed_brick_id=candidate.brick_sequence_id,
            exit_warning_count=0
        )
        logger.info(
            "[STATE_TRANSITION] Signal state -> JARVIS_SIGNAL_ACTIVE (%s %s %s @ %.2f, brick=%d). Note: Does NOT imply broker fill.",
            candidate.underlying,
            candidate.strike,
            candidate.option_type,
            candidate.price,
            candidate.brick_sequence_id
        )

    def on_exit_warning(self, brick_id: int) -> None:
        """
        Records an internal single opposite brick warning without alerting the user.
        """
        if self.is_active and self.active_signal:
            self.state = PositionState.EXIT_WARNING_1_BRICK
            self.active_signal.exit_warning_count = 1
            self.active_signal.last_confirmed_brick_id = brick_id
            logger.info(
                "[STATE_TRANSITION] Signal state -> EXIT_WARNING_1_BRICK (Single opposite brick at #%d). User alert inhibited.",
                brick_id
            )

    def on_exit_signal_dispatched(self, exit_reason: ExitReason) -> None:
        """
        Transitions state to COOLDOWN upon confirmed EXIT dispatch.
        """
        prev_sig = self.active_signal
        self.state = PositionState.COOLDOWN
        self._last_exit_time = time.time()
        self.active_signal = None
        logger.info(
            "[STATE_TRANSITION] Signal state -> COOLDOWN (Exit confirmed: %s for %s %s). Tracking terminated.",
            exit_reason.value,
            prev_sig.strike if prev_sig else "",
            prev_sig.option_type if prev_sig else ""
        )

    def on_data_feed_loss(self, reason: str = "window_occluded") -> None:
        """
        Handles loss of visible chart window without corrupting state or assuming broker action.
        """
        if self.is_active:
            logger.warning("[DATA_FEED_LOSS] %s while JARVIS_SIGNAL_ACTIVE. State -> POSITION_STATE_UNKNOWN.", reason)
            self.state = PositionState.POSITION_STATE_UNKNOWN
        elif self.state != PositionState.POSITION_STATE_UNKNOWN:
            logger.debug("[DATA_FEED_LOSS] %s while %s.", reason, self.state.value)

    def on_data_feed_restored(self) -> None:
        """
        Restores tracking state when chart visibility is regained.
        """
        if self.state == PositionState.POSITION_STATE_UNKNOWN:
            if self.active_signal:
                logger.info("[DATA_FEED_RESTORED] Visibility restored. Resuming JARVIS_SIGNAL_ACTIVE tracking.")
                self.state = PositionState.JARVIS_SIGNAL_ACTIVE
            else:
                logger.info("[DATA_FEED_RESTORED] Visibility restored with no active signal. State -> FLAT.")
                self.state = PositionState.FLAT

    def reset_to_flat(self, reason: str = "manual_reset") -> None:
        """Safely resets state to FLAT."""
        logger.info("[STATE_RESET] Resetting signal state to FLAT (Reason: %s).", reason)
        self.state = PositionState.FLAT
        self.active_signal = None
        self._last_exit_time = 0.0
