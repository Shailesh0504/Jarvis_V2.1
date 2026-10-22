# tests/trading/test_pre_dispatch_gate.py
"""
Unit tests for synchronous visual PreDispatchRevalidationGate:
1. Window Invariance
2. Brick Invariance
3. Boundary Invariance
4. Confidence Invariance (>= 0.85)
"""

import pytest
from plugins.trading_signals.gate.pre_dispatch_gate import PreDispatchRevalidationGate
from plugins.trading_signals.models.chart_state import (
    BrickStatus,
    IndexChartState,
    OptionChartState,
    OptionType,
    RenkoColor,
    RenkoTransition,
    SuperTrendBias,
    SuperTrendFlip
)
from plugins.trading_signals.models.data_feed_types import FrameConfidence
from plugins.trading_signals.models.signal_types import (
    CandidateSignal,
    SignalType,
    StrategyTriggerMode
)


@pytest.fixture
def candidate_buy_signal():
    return CandidateSignal(
        signal_type=SignalType.BUY,
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        price=152.0,
        brick_sequence_id=10,
        strategy_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
        reason="Test candidate"
    )


@pytest.fixture
def fresh_valid_index():
    return IndexChartState(
        underlying="NIFTY",
        current_price=24500.0,
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        ema_bias=SuperTrendBias.BULLISH,
        brick_sequence_id=10,
        last_trigger_brick_id=9,
        is_valid=True
    )


@pytest.fixture
def fresh_valid_option():
    return OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=152.0,
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        donchian_upper=150.0,
        donchian_basis=140.0,
        donchian_lower=130.0,
        previous_price=149.0,
        previous_donchian_upper=150.0,
        donchian_breakout_event=True,
        brick_sequence_id=25,
        is_valid=True
    )


@pytest.fixture
def high_confidence():
    return FrameConfidence(
        ocr_confidence=0.95,
        color_segmentation_confidence=0.92,
        contour_confidence=0.90,
        scale_calibration_confidence=0.94,
        window_visibility_confidence=1.0
    )


def test_all_invariants_pass_enables_dispatch(
    candidate_buy_signal,
    fresh_valid_index,
    fresh_valid_option,
    high_confidence
):
    """When all 4 invariants hold, candidate passes pre-dispatch revalidation."""
    gate = PreDispatchRevalidationGate(
        min_confidence=0.85,
        window_verifier=lambda: True  # Window matches
    )

    result = gate.validate_candidate(
        candidate=candidate_buy_signal,
        fresh_index_state=fresh_valid_index,
        fresh_option_state=fresh_valid_option,
        fresh_confidence=high_confidence
    )

    assert result.passed is True
    assert result.window_invariant_passed is True
    assert result.brick_invariant_passed is True
    assert result.boundary_invariant_passed is True
    assert result.confidence_invariant_passed is True


def test_window_invariant_failure_rejects_candidate(
    candidate_buy_signal,
    fresh_valid_index,
    fresh_valid_option,
    high_confidence
):
    """When window focus is lost or changed, candidate is immediately rejected."""
    gate = PreDispatchRevalidationGate(
        min_confidence=0.85,
        window_verifier=lambda: False  # Focus lost
    )

    result = gate.validate_candidate(
        candidate=candidate_buy_signal,
        fresh_index_state=fresh_valid_index,
        fresh_option_state=fresh_valid_option,
        fresh_confidence=high_confidence
    )

    assert result.passed is False
    assert result.window_invariant_passed is False
    assert "lost focus" in result.reason


def test_brick_invariant_failure_rejects_repainting_brick(
    candidate_buy_signal,
    fresh_valid_index,
    fresh_valid_option,
    high_confidence
):
    """When option brick returns to FORMING in fresh frame, candidate is rejected."""
    fresh_valid_option.brick_status = BrickStatus.FORMING

    gate = PreDispatchRevalidationGate(
        min_confidence=0.85,
        window_verifier=lambda: True
    )

    result = gate.validate_candidate(
        candidate=candidate_buy_signal,
        fresh_index_state=fresh_valid_index,
        fresh_option_state=fresh_valid_option,
        fresh_confidence=high_confidence
    )

    assert result.passed is False
    assert result.brick_invariant_passed is False
    assert "FORMING" in result.reason


def test_boundary_invariant_failure_rejects_slipped_price(
    candidate_buy_signal,
    fresh_valid_index,
    fresh_valid_option,
    high_confidence
):
    """When option price slips back to or below Donchian upper, candidate is rejected."""
    fresh_valid_option.current_price = 149.5

    gate = PreDispatchRevalidationGate(
        min_confidence=0.85,
        window_verifier=lambda: True
    )

    result = gate.validate_candidate(
        candidate=candidate_buy_signal,
        fresh_index_state=fresh_valid_index,
        fresh_option_state=fresh_valid_option,
        fresh_confidence=high_confidence
    )

    assert result.passed is False
    assert result.boundary_invariant_passed is False
    assert "slipped below" in result.reason


def test_confidence_invariant_failure_rejects_low_confidence_frame(
    candidate_buy_signal,
    fresh_valid_index,
    fresh_valid_option
):
    """When composite frame confidence drops below 0.85, candidate is rejected."""
    low_confidence = FrameConfidence(
        ocr_confidence=0.60,
        color_segmentation_confidence=0.70,
        contour_confidence=0.65,
        scale_calibration_confidence=0.80,
        window_visibility_confidence=1.0
    )

    gate = PreDispatchRevalidationGate(
        min_confidence=0.85,
        window_verifier=lambda: True
    )

    result = gate.validate_candidate(
        candidate=candidate_buy_signal,
        fresh_index_state=fresh_valid_index,
        fresh_option_state=fresh_valid_option,
        fresh_confidence=low_confidence
    )

    assert result.passed is False
    assert result.confidence_invariant_passed is False
    assert "threshold" in result.reason
