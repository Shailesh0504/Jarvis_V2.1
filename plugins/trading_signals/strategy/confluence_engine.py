# plugins/trading_signals/strategy/confluence_engine.py
"""
Deterministic Multi-Chart Confluence Evaluation Engine.
Evaluates normalized IndexChartState and OptionChartState inputs.
Strictly decoupled from screen capture, OCR, and order execution.
"""

from dataclasses import dataclass
import logging
from typing import List, Optional

from ..models.chart_state import (
    BrickStatus,
    IndexChartState,
    OptionChartState,
    OptionType,
    RenkoColor,
    RenkoTransition,
    SuperTrendBias,
    SuperTrendFlip
)
from ..models.signal_types import (
    CandidateSignal,
    SignalType,
    StrategyTriggerMode
)

logger = logging.getLogger("jarvis.trading.strategy.confluence")


@dataclass
class ConfluenceEvaluationResult:
    """Detailed result of confluence evaluation for internal telemetry."""
    signal_generated: bool
    candidate: Optional[CandidateSignal]
    rejection_reason: str
    trigger_mode_used: StrategyTriggerMode


class ConfluenceSignalEngine:
    """
    Evaluates Index and Option chart states to generate deterministic BUY candidate signals.
    """

    def __init__(
        self,
        trigger_mode: Optional[StrategyTriggerMode] = None,
        dual_fresh_window_bricks: Optional[int] = None,
        mode: Optional[StrategyTriggerMode] = None,
        fresh_window_n: Optional[int] = None
    ):
        self.trigger_mode = trigger_mode or mode or StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD
        val_n = dual_fresh_window_bricks if dual_fresh_window_bricks is not None else fresh_window_n
        self.dual_fresh_window_bricks = max(1, int(val_n)) if val_n is not None else 2
        self._recent_index_flips: List[int] = []  # History of brick_sequence_ids where flip occurred

    def record_index_transition(self, index_state: IndexChartState) -> None:
        """Tracks Index flip events for DUAL_FRESH_TRIGGER window matching."""
        if index_state.supertrend_flip in (SuperTrendFlip.BULLISH_FLIP, SuperTrendFlip.BEARISH_FLIP) or \
           index_state.renko_transition in (RenkoTransition.RED_TO_GREEN, RenkoTransition.GREEN_TO_RED):
            self._recent_index_flips.append(index_state.brick_sequence_id)
            # Keep history bounded
            if len(self._recent_index_flips) > 20:
                self._recent_index_flips.pop(0)

    def is_index_fresh_trigger_within_window(self, current_brick_id: int) -> bool:
        """
        Checks if a fresh Index flip occurred within the last N confirmed bricks
        (inclusive of the current newly confirmed brick).
        """
        for flip_id in reversed(self._recent_index_flips):
            if 0 <= (current_brick_id - flip_id) <= self.dual_fresh_window_bricks:
                return True
        return False

    def evaluate_entry(
        self,
        index_state: IndexChartState,
        option_state: OptionChartState,
        previous_option_state: Optional[OptionChartState] = None
    ) -> Optional[CandidateSignal]:
        """Convenience method returning CandidateSignal if triggered."""
        res = self.evaluate_buy_confluence(index_state, option_state, previous_option_state)
        return res.candidate if res.signal_generated else None

    def evaluate_buy_confluence(
        self,
        index_state: IndexChartState,
        option_state: OptionChartState,
        previous_option_state: Optional[OptionChartState] = None
    ) -> ConfluenceEvaluationResult:
        """
        Evaluates confluence on newly confirmed closed bricks.
        Returns ConfluenceEvaluationResult containing CandidateSignal if triggered.
        """
        # 1. Closed Brick Invariant
        if index_state.brick_status != BrickStatus.CLOSED:
            return ConfluenceEvaluationResult(
                signal_generated=False,
                candidate=None,
                rejection_reason="Index brick is FORMING (closed brick required).",
                trigger_mode_used=self.trigger_mode
            )

        if option_state.brick_status != BrickStatus.CLOSED:
            return ConfluenceEvaluationResult(
                signal_generated=False,
                candidate=None,
                rejection_reason="Option brick is FORMING (closed brick required).",
                trigger_mode_used=self.trigger_mode
            )

        # 2. Validity & Discrepancy Invariants
        if getattr(option_state, "is_valid", True) is False:
            return ConfluenceEvaluationResult(
                signal_generated=False,
                candidate=None,
                rejection_reason="Option chart state is marked invalid (indicator discrepancy or low confidence).",
                trigger_mode_used=self.trigger_mode
            )

        if getattr(option_state, "multi_brick_jump", False):
            return ConfluenceEvaluationResult(
                signal_generated=False,
                candidate=None,
                rejection_reason="Option chart flagged multi-brick jump.",
                trigger_mode_used=self.trigger_mode
            )

        # Multi-Brick Jump check from sequence id
        if previous_option_state:
            jump = option_state.brick_sequence_id - previous_option_state.brick_sequence_id
            if jump > 1:
                msg = f"Multi-brick jump detected ({jump} bricks spawned at once without sequence reconstruction)."
                logger.warning("[CONFLUENCE_REJECT] %s Inhabiting candidate signal.", msg)
                return ConfluenceEvaluationResult(
                    signal_generated=False,
                    candidate=None,
                    rejection_reason=msg,
                    trigger_mode_used=self.trigger_mode
                )

        # 3. Update Index Transition History
        self.record_index_transition(index_state)

        # 4. Mode-Specific Index Checks
        if self.trigger_mode == StrategyTriggerMode.DUAL_FRESH_TRIGGER:
            last_trig = getattr(index_state, "last_trigger_brick_id", None)
            is_fresh = False
            if last_trig is not None and last_trig > 0:
                diff = index_state.brick_sequence_id - last_trig
                if 0 <= diff <= self.dual_fresh_window_bricks:
                    is_fresh = True

            if not is_fresh and self.is_index_fresh_trigger_within_window(index_state.brick_sequence_id):
                is_fresh = True

            if not is_fresh:
                return ConfluenceEvaluationResult(
                    signal_generated=False,
                    candidate=None,
                    rejection_reason=f"Dual-fresh mode required Index flip within last {self.dual_fresh_window_bricks} bricks.",
                    trigger_mode_used=self.trigger_mode
                )

        # 5. Evaluate Put (PE) Confluence
        if option_state.option_type == OptionType.PE:
            # Index must be Bearish: Price <= SuperTrend (or ST bias Bearish), Price <= EMA(20) (or EMA bias Bearish), Red Renko
            idx_bearish = (
                option_state.renko_color == RenkoColor.GREEN and
                (index_state.supertrend_bias == SuperTrendBias.BEARISH or (index_state.supertrend_val > 0 and index_state.current_price <= index_state.supertrend_val)) and
                index_state.renko_color == RenkoColor.RED
            )
            if not idx_bearish:
                return ConfluenceEvaluationResult(
                    signal_generated=False,
                    candidate=None,
                    rejection_reason="Index is not in confirmed Bearish regime for PE trade.",
                    trigger_mode_used=self.trigger_mode
                )

            # Option must be Bullish: Green Renko, SuperTrend Bullish, and Fresh Donchian Upper Breakout
            opt_bullish = (
                option_state.renko_color == RenkoColor.GREEN
                and option_state.supertrend_bias == SuperTrendBias.BULLISH
            )
            if not opt_bullish:
                return ConfluenceEvaluationResult(
                    signal_generated=False,
                    candidate=None,
                    rejection_reason="Option PE premium is not in confirmed Bullish state.",
                    trigger_mode_used=self.trigger_mode
                )

            # Strict Donchian Upper Breakout Event:
            # Must be a discrete breakout transition on this closed brick
            if not option_state.donchian_breakout_event:
                return ConfluenceEvaluationResult(
                    signal_generated=False,
                    candidate=None,
                    rejection_reason="Option PE price did not produce a fresh Donchian upper breakout event on this brick.",
                    trigger_mode_used=self.trigger_mode
                )

            # Confluence Confirmed for PUT BUY
            candidate = CandidateSignal(
                signal_type=SignalType.BUY,
                underlying=option_state.underlying,
                strike=option_state.strike,
                option_type=option_state.option_type.value if hasattr(option_state.option_type, "value") else str(option_state.option_type),
                price=option_state.current_price,
                timestamp=option_state.timestamp,
                trigger_mode=self.trigger_mode,
                confidence=min(index_state.confidence, option_state.confidence),
                brick_sequence_id=option_state.brick_sequence_id,
                reason=f"{self.trigger_mode.value} BUY triggered",
                metadata={
                    "index_price": index_state.current_price,
                    "index_st": index_state.supertrend_val,
                    "option_st": option_state.supertrend_val,
                    "donchian_upper": option_state.donchian_upper
                }
            )
            logger.info(
                "[CONFLUENCE_TRIGGER] BUY %d PE triggered under %s (Price: %.2f, ST: %.2f, DC_Upper: %.2f).",
                candidate.strike,
                self.trigger_mode.value,
                candidate.price,
                option_state.supertrend_val,
                option_state.donchian_upper
            )
            return ConfluenceEvaluationResult(
                signal_generated=True,
                candidate=candidate,
                rejection_reason="",
                trigger_mode_used=self.trigger_mode
            )

        # 6. Evaluate Call (CE) Confluence
        elif option_state.option_type == OptionType.CE:
            # Index must be Bullish: SuperTrend bias Bullish, Green Renko
            idx_bullish = (
                index_state.supertrend_bias == SuperTrendBias.BULLISH
                and index_state.renko_color == RenkoColor.GREEN
            )
            if not idx_bullish:
                return ConfluenceEvaluationResult(
                    signal_generated=False,
                    candidate=None,
                    rejection_reason="Index is not in confirmed Bullish regime for CE trade.",
                    trigger_mode_used=self.trigger_mode
                )

            # Option must be Bullish: Green Renko, SuperTrend bias Bullish
            opt_bullish = (
                option_state.renko_color == RenkoColor.GREEN
                and option_state.supertrend_bias == SuperTrendBias.BULLISH
            )
            if not opt_bullish:
                return ConfluenceEvaluationResult(
                    signal_generated=False,
                    candidate=None,
                    rejection_reason="Option CE premium is not in confirmed Bullish state.",
                    trigger_mode_used=self.trigger_mode
                )

            # Strict Donchian Upper Breakout Event
            if not option_state.donchian_breakout_event:
                return ConfluenceEvaluationResult(
                    signal_generated=False,
                    candidate=None,
                    rejection_reason="Option CE price did not produce a fresh Donchian upper breakout event on this brick.",
                    trigger_mode_used=self.trigger_mode
                )

            # Confluence Confirmed for CALL BUY
            candidate = CandidateSignal(
                signal_type=SignalType.BUY,
                underlying=option_state.underlying,
                strike=option_state.strike,
                option_type=option_state.option_type.value if hasattr(option_state.option_type, "value") else str(option_state.option_type),
                price=option_state.current_price,
                timestamp=option_state.timestamp,
                trigger_mode=self.trigger_mode,
                confidence=min(index_state.confidence, option_state.confidence),
                brick_sequence_id=option_state.brick_sequence_id,
                reason=f"{self.trigger_mode.value} BUY triggered",
                metadata={
                    "index_price": index_state.current_price,
                    "index_st": index_state.supertrend_val,
                    "option_st": option_state.supertrend_val,
                    "donchian_upper": option_state.donchian_upper
                }
            )
            logger.info(
                "[CONFLUENCE_TRIGGER] BUY %d CE triggered under %s (Price: %.2f, ST: %.2f, DC_Upper: %.2f).",
                candidate.strike,
                self.trigger_mode.value,
                candidate.price,
                option_state.supertrend_val,
                option_state.donchian_upper
            )
            return ConfluenceEvaluationResult(
                signal_generated=True,
                candidate=candidate,
                rejection_reason="",
                trigger_mode_used=self.trigger_mode
            )

        return ConfluenceEvaluationResult(
            signal_generated=False,
            candidate=None,
            rejection_reason=f"Unsupported option type '{option_state.option_type}'.",
            trigger_mode_used=self.trigger_mode
        )
