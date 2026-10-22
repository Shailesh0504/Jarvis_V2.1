# tests/trading/test_renko_lifecycle.py
"""
Unit tests for Renko brick lifecycle:
- Closed vs forming brick determination (never price rounding or arbitrary timers)
- Structural column spawn and stabilization
- Forming brick rejection for BUY and EXIT signals
- Multi-brick jump detection and signal rejection
- Calibrated HSV color classification
"""

import numpy as np
import pytest
from plugins.trading_signals.vision.color_classifier import CalibratedColorClassifier
from plugins.trading_signals.vision.renko_detector import RenkoVisualDetector
from plugins.trading_signals.models.chart_state import (
    IndexChartState,
    OptionChartState,
    RenkoColor,
    BrickStatus,
    RenkoTransition,
    SuperTrendBias,
    SuperTrendFlip,
    OptionType
)
from plugins.trading_signals.models.signal_types import (
    StrategyTriggerMode,
    SignalType,
    PositionState
)
from plugins.trading_signals.strategy.confluence_engine import ConfluenceSignalEngine
from plugins.trading_signals.strategy.exit_evaluator import ExitEvaluator


def test_color_classifier_calibrated_hsv():
    """Verify calibrated HSV color classifier correctly classifies green and red bricks."""
    classifier = CalibratedColorClassifier()

    # Create solid green block (BGR: (35, 180, 45) -> HSV: H~62, S~205, V~180)
    green_crop = np.full((20, 20, 3), (35, 180, 45), dtype=np.uint8)
    color, conf = classifier.classify_brick_color(green_crop)
    assert color == RenkoColor.GREEN
    assert conf > 0.85

    # Create solid red block (BGR: (40, 40, 210) -> HSV: H~0, S~206, V~210)
    red_crop = np.full((20, 20, 3), (40, 40, 210), dtype=np.uint8)
    color, conf = classifier.classify_brick_color(red_crop)
    assert color == RenkoColor.RED
    assert conf > 0.85

    # Black / empty block
    empty_crop = np.zeros((20, 20, 3), dtype=np.uint8)
    color, conf = classifier.classify_brick_color(empty_crop)
    assert color == RenkoColor.UNKNOWN


def test_renko_detector_forming_to_closed_transition():
    """Verify detector requires multi-frame stabilization before confirming closed brick."""
    detector = RenkoVisualDetector(min_brick_width=10, min_brick_height=10)

    # Canvas 1: Baseline single green brick at x=50, y=100, w=15, h=15
    canvas1 = np.zeros((300, 300, 3), dtype=np.uint8)
    canvas1[100:115, 50:65] = [35, 180, 45]  # Green

    res1 = detector.evaluate_canvas(canvas1)
    assert res1.brick_status == BrickStatus.CLOSED
    assert res1.active_color == RenkoColor.GREEN
    assert res1.brick_sequence_id == 1

    # Canvas 2: A new brick starts appearing at x=66 (step = 16 px > 12 px)
    canvas2 = np.zeros((300, 300, 3), dtype=np.uint8)
    canvas2[100:115, 50:65] = [35, 180, 45]
    canvas2[85:100, 66:81] = [35, 180, 45]  # Higher green brick

    # Frame 1: First observation of new brick -> FORMING
    res2 = detector.evaluate_canvas(canvas2)
    assert res2.brick_status == BrickStatus.FORMING

    # Frame 2: Second consecutive observation of stable new brick -> CONFIRMED CLOSED
    res3 = detector.evaluate_canvas(canvas2)
    assert res3.brick_status == BrickStatus.CLOSED
    assert res3.brick_sequence_id == 2


def test_renko_detector_multi_brick_jump_detection():
    """Verify that a visual jump > 2.5x brick width flags multi_brick_jump=True."""
    detector = RenkoVisualDetector(min_brick_width=10, min_brick_height=10)

    # Baseline brick at x=50
    canvas1 = np.zeros((300, 300, 3), dtype=np.uint8)
    canvas1[100:115, 50:65] = [35, 180, 45]
    detector.evaluate_canvas(canvas1)

    # Next canvas has brick at x=120 (step = 70 px > 2.5 * 15 = 37.5 px)
    canvas_jump = np.zeros((300, 300, 3), dtype=np.uint8)
    canvas_jump[100:115, 50:65] = [35, 180, 45]
    canvas_jump[50:65, 120:135] = [35, 180, 45]

    res_jump = detector.evaluate_canvas(canvas_jump)
    assert res_jump.multi_brick_jump is True


def test_strategy_engine_rejects_multi_brick_jump():
    """ConfluenceSignalEngine must strictly reject signal on multi-brick jump."""
    bullish_index = IndexChartState(
        underlying="NIFTY",
        current_price=24500.0,
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        ema_bias=SuperTrendBias.BULLISH,
        brick_sequence_id=1,
        last_trigger_brick_id=1,
        is_valid=True
    )
    option_with_jump = OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=150.0,
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        donchian_upper=145.0,
        donchian_basis=135.0,
        donchian_lower=125.0,
        previous_price=140.0,
        previous_donchian_upper=145.0,
        donchian_breakout_event=True,
        brick_sequence_id=3,
        multi_brick_jump=True,  # JUMP DETECTED
        is_valid=True
    )

    engine = ConfluenceSignalEngine(mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD)
    signal = engine.evaluate_entry(bullish_index, option_with_jump)
    assert signal is None, "Multi-brick jump must reject candidate signal generation"


def test_exit_evaluator_ignores_forming_brick():
    """ExitEvaluator must ignore forming opposite bricks and not trigger warning or exit."""
    active_position = OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=140.0,
        renko_color=RenkoColor.RED,
        brick_status=BrickStatus.FORMING,  # Opposite color but still FORMING!
        renko_transition=RenkoTransition.NO_TRANSITION,
        consecutive_opposite_bricks=1,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        donchian_upper=150.0,
        donchian_basis=130.0,
        donchian_lower=110.0,
        previous_price=145.0,
        previous_donchian_upper=150.0,
        donchian_breakout_event=False,
        brick_sequence_id=5,
        is_valid=True
    )
    index_state = IndexChartState(
        underlying="NIFTY",
        current_price=24500.0,
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        ema_bias=SuperTrendBias.BULLISH,
        brick_sequence_id=5,
        last_trigger_brick_id=4,
        is_valid=True
    )

    evaluator = ExitEvaluator()
    eval_res = evaluator.evaluate_exit(
        current_position_state=PositionState.JARVIS_SIGNAL_ACTIVE,
        active_option_type=OptionType.CE,
        option_state=active_position,
        index_state=index_state
    )

    assert eval_res.should_exit is False
    assert eval_res.is_warning is False
    assert "Forming brick" in eval_res.reason or "FORMING" in eval_res.reason
