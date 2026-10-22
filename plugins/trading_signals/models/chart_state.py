# plugins/trading_signals/models/chart_state.py
"""
Normalized Immutable Chart State Models for NIFTY Index and Option Contracts.
Decoupled strictly from vision capture and strategy logic.
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Optional, Tuple


class RenkoColor(str, Enum):
    """Calibrated color classification for Renko bricks."""
    GREEN = "GREEN"
    RED = "RED"
    UNKNOWN = "UNKNOWN"


class BrickStatus(str, Enum):
    """Discrete lifecycle state of a Renko brick."""
    CLOSED = "CLOSED"      # Solidified contour, fixed geometry across observation frames
    FORMING = "FORMING"    # In-progress column or price within box height, never eligible for signals
    UNKNOWN = "UNKNOWN"


class RenkoTransition(str, Enum):
    """Transition between consecutive closed Renko bricks."""
    RED_TO_GREEN = "RED_TO_GREEN"    # Fresh Bullish transition
    GREEN_TO_RED = "GREEN_TO_RED"    # Fresh Bearish transition
    NO_TRANSITION = "NO_TRANSITION"  # Same color as previous closed brick
    UNKNOWN = "UNKNOWN"


class SuperTrendBias(str, Enum):
    """Persistent trend bias relative to SuperTrend line."""
    BULLISH = "BULLISH"  # Price currently above SuperTrend line
    BEARISH = "BEARISH"  # Price currently below SuperTrend line
    UNKNOWN = "UNKNOWN"


class SuperTrendFlip(str, Enum):
    """Discrete transition event occurring on the current closed brick."""
    BULLISH_FLIP = "BULLISH_FLIP"    # Transitioned from Bearish to Bullish on current brick
    BEARISH_FLIP = "BEARISH_FLIP"    # Transitioned from Bullish to Bearish on current brick
    NO_FLIP = "NO_FLIP"              # Continued prior bias without crossover
    UNKNOWN = "UNKNOWN"


class OptionType(str, Enum):
    """Option contract derivative type."""
    CE = "CE"
    PE = "PE"
    UNKNOWN = "UNKNOWN"


@dataclass
class IndexChartState:
    """
    Representation of the visible NIFTY Index chart state.
    """
    timestamp: float = field(default_factory=time.time)
    underlying: str = "NIFTY"                          # Expected: "NIFTY" or "NIFTY 50"
    current_price: float = 0.0
    brick_size: int = 10                              # Expected: 10
    renko_color: RenkoColor = RenkoColor.UNKNOWN
    renko_transition: RenkoTransition = RenkoTransition.NO_TRANSITION
    brick_status: BrickStatus = BrickStatus.UNKNOWN
    supertrend_val: float = 0.0                       # Visible SuperTrend level
    supertrend_bias: SuperTrendBias = SuperTrendBias.UNKNOWN  # Persistent bias
    supertrend_flip: SuperTrendFlip = SuperTrendFlip.NO_FLIP  # Discrete flip event
    ema_20_val: float = 0.0                           # Visible EMA (20) level
    ema_bias: Any = "NEUTRAL"                         # "ABOVE" / "BELOW" or SuperTrendBias
    confidence: float = 1.0                           # Visual confidence score [0.0, 1.0]
    brick_sequence_id: int = 0                        # Sequential counter of confirmed closed bricks
    last_trigger_brick_id: int = 0                    # Brick ID of last ST flip or Renko transition
    is_valid: bool = True


@dataclass
class OptionChartState:
    """
    Representation of the visible NIFTY Option contract chart state.
    """
    timestamp: float = field(default_factory=time.time)
    underlying: str = "NIFTY"                          # Expected: "NIFTY"
    expiry: str = ""                                  # e.g., "08 SEP"
    strike: int = 0                                   # e.g., 23900
    option_type: OptionType = OptionType.UNKNOWN      # CE / PE
    current_price: float = 0.0
    brick_size: int = 3                               # Expected: 3
    renko_color: RenkoColor = RenkoColor.UNKNOWN
    renko_transition: RenkoTransition = RenkoTransition.NO_TRANSITION
    brick_status: BrickStatus = BrickStatus.UNKNOWN
    consecutive_opposite_bricks: int = 0             # Count of consecutive confirmed opposite bricks
    supertrend_val: float = 0.0                       # Visible SuperTrend level
    supertrend_bias: SuperTrendBias = SuperTrendBias.UNKNOWN  # Persistent bias
    supertrend_flip: SuperTrendFlip = SuperTrendFlip.NO_FLIP  # Discrete flip event
    donchian_upper: float = 0.0                       # Verified upper channel level
    donchian_basis: float = 0.0                       # Verified middle basis level
    donchian_lower: float = 0.0                       # Verified lower channel level
    donchian_breakout_event: bool = False             # True ONLY if (P_prev <= Upper_prev and P_curr > Upper_curr)
    confidence: float = 1.0                           # Visual confidence score [0.0, 1.0]
    brick_sequence_id: int = 0                        # Sequential counter of confirmed closed bricks
    previous_price: float = 0.0
    previous_donchian_upper: float = 0.0
    multi_brick_jump: bool = False
    is_valid: bool = True
    data_feed_state: Any = None

    @property
    def donchian_breakout(self) -> bool:
        return self.donchian_breakout_event

    @donchian_breakout.setter
    def donchian_breakout(self, value: bool) -> None:
        self.donchian_breakout_event = value
