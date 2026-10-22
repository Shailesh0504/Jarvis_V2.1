# plugins/trading_signals/gate/pre_dispatch_gate.py
"""
Synchronous Visual Pre-Dispatch Revalidation Gate.
Every candidate signal must pass an immediate fresh visual revalidation before user notification.
Rejects signals if window shifted, chart repainted, boundary lost, or confidence fell.
"""

from dataclasses import dataclass
import logging
from typing import Callable, Optional

from ..models.chart_state import BrickStatus, IndexChartState, OptionChartState
from ..models.data_feed_types import FrameConfidence
from ..models.signal_types import CandidateSignal, SignalType

logger = logging.getLogger("jarvis.trading.gate.pre_dispatch")


@dataclass(frozen=True)
class PreDispatchValidationResult:
    """Outcome of synchronous pre-dispatch revalidation pass."""
    passed: bool
    window_invariant_passed: bool
    brick_invariant_passed: bool
    boundary_invariant_passed: bool
    confidence_invariant_passed: bool
    reason: str


class PreDispatchRevalidationGate:
    """
    Final defense line before dispatching any trading signal to the user.
    Executes an immediate fresh visual snapshot and revalidates 4 strict invariants.
    """

    def __init__(
        self,
        min_confidence: float = 0.85,
        window_verifier: Optional[Callable[[], bool]] = None
    ):
        self.min_confidence = min_confidence
        self.window_verifier = window_verifier

    def validate_candidate(
        self,
        candidate: CandidateSignal,
        fresh_index_state: IndexChartState,
        fresh_option_state: OptionChartState,
        fresh_confidence: FrameConfidence
    ) -> PreDispatchValidationResult:
        """
        Synchronously validates the candidate signal against fresh revalidation frame data.
        """
        # 1. Window Invariance Check
        window_ok = True
        if self.window_verifier is not None:
            try:
                window_ok = bool(self.window_verifier())
            except Exception as e:
                logger.debug("[PRE_DISPATCH_CHECK] Window verification exception: %s", e)
                window_ok = False

        if not window_ok:
            msg = "Trading window lost focus, was minimized, or changed before dispatch."
            logger.warning("[PRE_DISPATCH_REVALIDATION_FAILED] Window Invariance failed: %s", msg)
            return PreDispatchValidationResult(
                passed=False,
                window_invariant_passed=False,
                brick_invariant_passed=False,
                boundary_invariant_passed=False,
                confidence_invariant_passed=False,
                reason=msg
            )

        # 2. Brick Invariance Check
        # The newly closed brick must STILL be confirmed closed and not repainting
        brick_ok = (
            fresh_option_state.brick_status == BrickStatus.CLOSED and
            fresh_index_state.brick_status == BrickStatus.CLOSED
        )
        if not brick_ok:
            msg = "Option or Index brick returned to FORMING or repainting state in fresh snapshot."
            logger.warning("[PRE_DISPATCH_REVALIDATION_FAILED] Brick Invariance failed: %s", msg)
            return PreDispatchValidationResult(
                passed=False,
                window_invariant_passed=True,
                brick_invariant_passed=False,
                boundary_invariant_passed=False,
                confidence_invariant_passed=False,
                reason=msg
            )

        # 3. Boundary Invariance Check
        # For BUY: active price must still be strictly above Donchian Upper Band
        boundary_ok = True
        if candidate.signal_type == SignalType.BUY:
            if fresh_option_state.current_price <= fresh_option_state.donchian_upper:
                boundary_ok = False
                msg = (
                    f"Option price ({fresh_option_state.current_price:.2f}) slipped below "
                    f"Donchian upper boundary ({fresh_option_state.donchian_upper:.2f}) during revalidation."
                )
                logger.warning("[PRE_DISPATCH_REVALIDATION_FAILED] Boundary Invariance failed: %s", msg)
                return PreDispatchValidationResult(
                    passed=False,
                    window_invariant_passed=True,
                    brick_invariant_passed=True,
                    boundary_invariant_passed=False,
                    confidence_invariant_passed=False,
                    reason=msg
                )

        # 4. Confidence Invariance Check
        conf_ok = fresh_confidence.is_acceptable(self.min_confidence)
        if not conf_ok:
            msg = f"Fresh visual confidence {fresh_confidence.composite_confidence:.2f} < {self.min_confidence:.2f} threshold."
            logger.warning("[PRE_DISPATCH_REVALIDATION_FAILED] Confidence Invariance failed: %s", msg)
            return PreDispatchValidationResult(
                passed=False,
                window_invariant_passed=True,
                brick_invariant_passed=True,
                boundary_invariant_passed=True,
                confidence_invariant_passed=False,
                reason=msg
            )

        logger.info(
            "[PRE_DISPATCH_PASSED] All 4 invariants verified for %s %d %s @ %.2f.",
            candidate.signal_type.value,
            candidate.strike,
            candidate.option_type,
            fresh_option_state.current_price
        )
        return PreDispatchValidationResult(
            passed=True,
            window_invariant_passed=True,
            brick_invariant_passed=True,
            boundary_invariant_passed=True,
            confidence_invariant_passed=True,
            reason="All 4 pre-dispatch invariants successfully verified."
        )
