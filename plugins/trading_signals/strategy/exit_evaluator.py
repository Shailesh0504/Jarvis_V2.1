# plugins/trading_signals/strategy/exit_evaluator.py
"""
Position-Aware Exit Evaluation Engine.
Evaluates multi-tiered exit conditions strictly while an active recommendation is tracked.
Inhibits exit signals when FLAT or POSITION_STATE_UNKNOWN.
"""

from dataclasses import dataclass
import logging
from typing import Any, Optional

from ..models.chart_state import (
    BrickStatus,
    IndexChartState,
    OptionChartState,
    OptionType,
    RenkoColor,
    SuperTrendBias
)
from ..models.signal_types import (
    CandidateSignal,
    ExitReason,
    PositionState,
    SignalType,
    StrategyTriggerMode
)
from ..state.position_tracker import ActiveSignalRecord, PositionStateTracker

logger = logging.getLogger("jarvis.trading.strategy.exit")


@dataclass
class ExitEvaluationResult:
    """Detailed result of exit evaluation."""
    is_exit: bool
    is_warning: bool
    exit_reason: ExitReason
    candidate: Optional[CandidateSignal]
    details: str

    @property
    def should_exit(self) -> bool:
        return self.is_exit

    @property
    def reason(self) -> str:
        return self.details


class ExitEvaluator:
    """
    Evaluates reversal and risk criteria to generate deterministic EXIT recommendations.
    """

    def __init__(self, position_tracker: Optional[PositionStateTracker] = None):
        self.tracker = position_tracker or PositionStateTracker()

    def evaluate_exit(
        self,
        index_state: Optional[IndexChartState] = None,
        option_state: Optional[OptionChartState] = None,
        current_position_state: Optional[PositionState] = None,
        active_option_type: Optional[Any] = None,
        **kwargs
    ) -> ExitEvaluationResult:
        """
        Evaluates exit conditions on confirmed closed bricks.
        Returns ExitEvaluationResult with CandidateSignal if confirmed exit occurs.
        """
        # Allow test overrides of tracker state
        if current_position_state is not None:
            self.tracker.state = current_position_state
            if self.tracker.active_signal is None and current_position_state != PositionState.FLAT:
                opt_t = active_option_type.value if hasattr(active_option_type, "value") else str(active_option_type or "CE")
                self.tracker.active_signal = ActiveSignalRecord(
                    signal_id="temp_signal",
                    underlying=option_state.underlying if option_state else "NIFTY",
                    strike=option_state.strike if option_state else 24500,
                    option_type=opt_t,
                    entry_price=option_state.current_price if option_state else 100.0,
                    entry_timestamp=0.0,
                    last_confirmed_brick_id=0
                )

        # 1. Position-Aware Guard: Do NOT evaluate if FLAT or UNKNOWN
        if not self.tracker.can_evaluate_exit():
            return ExitEvaluationResult(
                is_exit=False,
                is_warning=False,
                exit_reason=ExitReason.NONE,
                candidate=None,
                details="Exit evaluation inhibited: No active Jarvis recommendation tracked (FLAT or UNKNOWN)."
            )

        active = self.tracker.active_signal
        if not active:
            return ExitEvaluationResult(
                is_exit=False,
                is_warning=False,
                exit_reason=ExitReason.NONE,
                candidate=None,
                details="Active signal record missing."
            )

        if option_state is None:
            return ExitEvaluationResult(
                is_exit=False,
                is_warning=False,
                exit_reason=ExitReason.NONE,
                candidate=None,
                details="Missing option state."
            )

        # 2. Closed Brick Invariant
        if option_state.brick_status != BrickStatus.CLOSED:
            return ExitEvaluationResult(
                is_exit=False,
                is_warning=False,
                exit_reason=ExitReason.NONE,
                candidate=None,
                details="Option brick is FORMING; exit evaluation requires confirmed closed brick."
            )

        # 3. Check Condition: Two Consecutive Opposite Confirmed Bricks
        if option_state.consecutive_opposite_bricks >= 2 or (
            option_state.renko_color == RenkoColor.RED and self.tracker.state == PositionState.EXIT_WARNING_1_BRICK
        ):
            candidate = CandidateSignal(
                signal_type=SignalType.EXIT,
                underlying=option_state.underlying,
                strike=option_state.strike,
                option_type=option_state.option_type.value if hasattr(option_state.option_type, "value") else str(option_state.option_type),
                price=option_state.current_price,
                timestamp=option_state.timestamp,
                trigger_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
                exit_reason=ExitReason.TWO_CONSECUTIVE_OPPOSITE_BRICKS,
                confidence=option_state.confidence,
                brick_sequence_id=option_state.brick_sequence_id,
                reason="Two consecutive opposite confirmed Renko bricks closed."
            )
            logger.info(
                "[EXIT_TRIGGER] EXIT %d %s triggered: 2 consecutive opposite bricks confirmed closed at %.2f.",
                candidate.strike,
                candidate.option_type,
                candidate.price
            )
            return ExitEvaluationResult(
                is_exit=True,
                is_warning=False,
                exit_reason=ExitReason.TWO_CONSECUTIVE_OPPOSITE_BRICKS,
                candidate=candidate,
                details="Two consecutive opposite confirmed Renko bricks closed."
            )

        # 4. Check Condition: Option SuperTrend Reversal
        if (option_state.current_price < option_state.supertrend_val and option_state.supertrend_val > 0) or option_state.supertrend_bias == SuperTrendBias.BEARISH:
            candidate = CandidateSignal(
                signal_type=SignalType.EXIT,
                underlying=option_state.underlying,
                strike=option_state.strike,
                option_type=option_state.option_type.value if hasattr(option_state.option_type, "value") else str(option_state.option_type),
                price=option_state.current_price,
                timestamp=option_state.timestamp,
                trigger_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
                exit_reason=ExitReason.OPTION_SUPERTREND_REVERSAL,
                confidence=option_state.confidence,
                brick_sequence_id=option_state.brick_sequence_id,
                reason="Option SuperTrend reversal"
            )
            logger.info(
                "[EXIT_TRIGGER] EXIT %d %s triggered: Option SuperTrend breached (Price: %.2f < ST: %.2f).",
                candidate.strike,
                candidate.option_type,
                candidate.price,
                option_state.supertrend_val
            )
            return ExitEvaluationResult(
                is_exit=True,
                is_warning=False,
                exit_reason=ExitReason.OPTION_SUPERTREND_REVERSAL,
                candidate=candidate,
                details=f"Option closed below SuperTrend ({option_state.current_price:.2f} < {option_state.supertrend_val:.2f})."
            )

        # 5. Check Condition: Donchian Middle Band (Basis) Breach
        if option_state.donchian_basis > 0 and option_state.current_price < option_state.donchian_basis:
            candidate = CandidateSignal(
                signal_type=SignalType.EXIT,
                underlying=option_state.underlying,
                strike=option_state.strike,
                option_type=option_state.option_type.value if hasattr(option_state.option_type, "value") else str(option_state.option_type),
                price=option_state.current_price,
                timestamp=option_state.timestamp,
                trigger_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
                exit_reason=ExitReason.DONCHIAN_MIDDLE_BAND_BREACH,
                confidence=option_state.confidence,
                brick_sequence_id=option_state.brick_sequence_id,
                reason="Donchian basis breached"
            )
            logger.info(
                "[EXIT_TRIGGER] EXIT %d %s triggered: Donchian middle band breached (Price: %.2f < Basis: %.2f).",
                candidate.strike,
                candidate.option_type,
                candidate.price,
                option_state.donchian_basis
            )
            return ExitEvaluationResult(
                is_exit=True,
                is_warning=False,
                exit_reason=ExitReason.DONCHIAN_MIDDLE_BAND_BREACH,
                candidate=candidate,
                details=f"Option closed below Donchian Basis ({option_state.current_price:.2f} < {option_state.donchian_basis:.2f})."
            )

        # 6. Check Condition: Index SuperTrend Invalidation
        if index_state is not None:
            if str(active.option_type).upper() == "PE":
                # For a Put trade, Index flipping Bullish above SuperTrend invalidates the trade
                if (index_state.current_price > index_state.supertrend_val and index_state.supertrend_val > 0) or index_state.supertrend_bias == SuperTrendBias.BULLISH:
                    candidate = CandidateSignal(
                        signal_type=SignalType.EXIT,
                        underlying=option_state.underlying,
                        strike=option_state.strike,
                        option_type=option_state.option_type.value if hasattr(option_state.option_type, "value") else str(option_state.option_type),
                        price=option_state.current_price,
                        timestamp=option_state.timestamp,
                        trigger_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
                        exit_reason=ExitReason.INDEX_SUPERTREND_REVERSAL,
                        confidence=min(index_state.confidence, option_state.confidence),
                        brick_sequence_id=option_state.brick_sequence_id,
                        reason="Index SuperTrend flipped Bullish against PE"
                    )
                    return ExitEvaluationResult(
                        is_exit=True,
                        is_warning=False,
                        exit_reason=ExitReason.INDEX_SUPERTREND_REVERSAL,
                        candidate=candidate,
                        details="Index SuperTrend flipped Bullish against active PE trade."
                    )

            elif str(active.option_type).upper() == "CE":
                # For a Call trade, Index flipping Bearish below SuperTrend invalidates the trade
                if (index_state.current_price < index_state.supertrend_val and index_state.supertrend_val > 0) or index_state.supertrend_bias == SuperTrendBias.BEARISH:
                    candidate = CandidateSignal(
                        signal_type=SignalType.EXIT,
                        underlying=option_state.underlying,
                        strike=option_state.strike,
                        option_type=option_state.option_type.value if hasattr(option_state.option_type, "value") else str(option_state.option_type),
                        price=option_state.current_price,
                        timestamp=option_state.timestamp,
                        trigger_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
                        exit_reason=ExitReason.INDEX_SUPERTREND_REVERSAL,
                        confidence=min(index_state.confidence, option_state.confidence),
                        brick_sequence_id=option_state.brick_sequence_id,
                        reason="Index SuperTrend flipped Bearish against CE"
                    )
                    return ExitEvaluationResult(
                        is_exit=True,
                        is_warning=False,
                        exit_reason=ExitReason.INDEX_SUPERTREND_REVERSAL,
                        candidate=candidate,
                        details="Index SuperTrend flipped Bearish against active CE trade."
                    )

        # 7. Check Condition: First Single Opposite Confirmed Brick (Internal Warning Only)
        if option_state.renko_color == RenkoColor.RED and self.tracker.state != PositionState.EXIT_WARNING_1_BRICK:
            self.tracker.on_exit_warning(option_state.brick_sequence_id)
            return ExitEvaluationResult(
                is_exit=False,
                is_warning=True,
                exit_reason=ExitReason.NONE,
                candidate=None,
                details=f"Single opposite red brick confirmed closed at {option_state.current_price:.2f}. Logged internal warning."
            )

        return ExitEvaluationResult(
            is_exit=False,
            is_warning=False,
            exit_reason=ExitReason.NONE,
            candidate=None,
            details="Active recommendation remains valid; no exit conditions met."
        )
