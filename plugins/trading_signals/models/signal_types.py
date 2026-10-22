# plugins/trading_signals/models/signal_types.py
"""
Signal Types, Strategy Trigger Modes, Exit Reasons, and Candidate Signal Models.
Strictly decoupled from execution mechanisms.
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, Optional


class StrategyTriggerMode(str, Enum):
    """
    Evaluation mode for multi-chart confluence.
    """
    # Index must be in confirmed persistent regime; Option generates the fresh trigger
    REGIME_CONFIRMED_OPTION_LEAD = "REGIME_CONFIRMED_OPTION_LEAD"

    # Both Index AND Option must have generated a fresh trigger within alignment window N
    DUAL_FRESH_TRIGGER = "DUAL_FRESH_TRIGGER"


class SignalType(str, Enum):
    """Signal direction for recommendation output."""
    BUY = "BUY"
    EXIT = "EXIT"
    NO_SIGNAL = "NO_SIGNAL"


class ExitReason(str, Enum):
    """Deterministic reason for generating an EXIT recommendation."""
    NONE = "NONE"
    TWO_CONSECUTIVE_OPPOSITE_BRICKS = "TWO_CONSECUTIVE_OPPOSITE_BRICKS"
    OPTION_SUPERTREND_REVERSAL = "OPTION_SUPERTREND_REVERSAL"
    DONCHIAN_MIDDLE_BAND_BREACH = "DONCHIAN_MIDDLE_BAND_BREACH"
    INDEX_SUPERTREND_REVERSAL = "INDEX_SUPERTREND_REVERSAL"


class PositionState(str, Enum):
    """
    Position-aware signal lifecycle tracking state.
    Binding invariant: JARVIS_SIGNAL_ACTIVE != ACTUAL_BROKER_POSITION.
    Jarvis holds zero knowledge of external broker orders.
    """
    FLAT = "FLAT"                                    # No active recommendation
    ARMED_AWAITING_FRESH_TRIGGER = "ARMED_AWAITING_FRESH_TRIGGER"  # Regime valid, waiting for fresh breakout
    BUY_SIGNAL_DISPATCHED = "BUY_SIGNAL_DISPATCHED"  # Fresh signal validated and dispatched
    JARVIS_SIGNAL_ACTIVE = "JARVIS_SIGNAL_ACTIVE"    # Tracking active recommendation lifecycle
    EXIT_WARNING_1_BRICK = "EXIT_WARNING_1_BRICK"    # Internal warning: 1 opposite brick closed (logged only)
    EXIT_SIGNAL_DISPATCHED = "EXIT_SIGNAL_DISPATCHED"# Confirmed exit dispatched
    COOLDOWN = "COOLDOWN"                            # Post-trade temporary observation cooldown
    POSITION_STATE_UNKNOWN = "POSITION_STATE_UNKNOWN"# Window minimized or chart occluded; tracking paused


@dataclass
class CandidateSignal:
    """
    Internal signal proposal emitted by the Strategy Engine.
    Must pass Pre-Dispatch Revalidation before reaching user notification channels.
    """
    signal_type: SignalType
    underlying: str
    strike: int
    option_type: Any                            # "CE" / "PE" or OptionType
    price: float
    timestamp: float = field(default_factory=time.time)
    trigger_mode: StrategyTriggerMode = StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD
    exit_reason: ExitReason = ExitReason.NONE
    confidence: float = 1.0
    brick_sequence_id: int = 0
    reason: str = ""
    strategy_mode: Optional[StrategyTriggerMode] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if hasattr(self.option_type, "value"):
            self.option_type = str(self.option_type.value)
        else:
            self.option_type = str(self.option_type)
        if self.strategy_mode is None:
            self.strategy_mode = self.trigger_mode
        else:
            self.trigger_mode = self.strategy_mode

    def to_concise_string(self) -> str:
        """User-visible notification string: exact concise format."""
        if self.signal_type in (SignalType.BUY, SignalType.EXIT):
            return f"{self.signal_type.value} {self.strike} {self.option_type.upper()}"
        return "NO_SIGNAL"
