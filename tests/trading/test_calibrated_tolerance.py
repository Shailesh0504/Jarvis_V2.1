# tests/trading/test_calibrated_tolerance.py
"""
Unit tests for calibrated Donchian tolerance and discrepancy gating:
- R = (P_top - P_bottom) / (Y_bottom - Y_top)
- Tolerance_calibrated = max(TickSize, c_scale * R * (StrokeWidth + AntialiasingMargin))
- Discrepancy rejection -> DataFeedState.INDICATOR_DISCREPANCY
"""

import numpy as np
import pytest
from plugins.trading_signals.vision.donchian_verifier import DonchianChannelVerifier
from plugins.trading_signals.models.data_feed_types import DataFeedState
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
from plugins.trading_signals.strategy.confluence_engine import ConfluenceSignalEngine
from plugins.trading_signals.models.signal_types import StrategyTriggerMode


def test_calibrated_tolerance_exact_calculation():
    """Verify calibrated tolerance calculation against expected formula values."""
    verifier = DonchianChannelVerifier()
    p_top = 200.0
    p_bottom = 100.0
    y_top = 50
    y_bottom = 450
    stroke_width = 1.5

    # R = 100 / 400 = 0.25
    # tolerance = max(0.05, 1.25 * 0.25 * (1.5 + 1.5)) = 0.9375
    r, tolerance = verifier.compute_calibrated_tolerance(
        p_top=p_top,
        p_bottom=p_bottom,
        y_top=y_top,
        y_bottom=y_bottom,
        stroke_width_pixels=stroke_width
    )

    assert pytest.approx(r, 0.0001) == 0.25
    assert pytest.approx(tolerance, 0.0001) == 0.9375


def test_calibrated_tolerance_tick_size_floor():
    """Verify tick size floor applies when chart is very zoomed in."""
    verifier = DonchianChannelVerifier()
    p_top = 100.10
    p_bottom = 100.00
    y_top = 0
    y_bottom = 1000
    r, tolerance = verifier.compute_calibrated_tolerance(
        p_top=p_top,
        p_bottom=p_bottom,
        y_top=y_top,
        y_bottom=y_bottom
    )
    assert tolerance == verifier.TICK_SIZE == 0.05


def test_rejects_calibration_when_y_range_invalid():
    """Rejects calibration when Y scale cannot be established (y_bottom <= y_top)."""
    verifier = DonchianChannelVerifier()
    r, tolerance = verifier.compute_calibrated_tolerance(
        p_top=200.0,
        p_bottom=100.0,
        y_top=100,
        y_bottom=100
    )
    assert r == 0.0
    assert tolerance == 0.0


def test_discrepancy_between_ocr_and_geometry_fails_verification():
    """When OCR and geometry differ by more than calibrated tolerance, verification fails."""
    verifier = DonchianChannelVerifier()

    canvas = np.zeros((500, 400, 3), dtype=np.uint8)
    canvas[150:152, 50:350] = [255, 0, 0]  # Blue

    result = verifier.verify_donchian_levels(
        ocr_upper=185.0,
        ocr_basis=150.0,
        ocr_lower=120.0,
        canvas_bgr=canvas,
        p_top=200.0,
        p_bottom=100.0,
        y_top=50,
        y_bottom=450
    )

    assert result.is_verified is False
    assert result.ocr_geometry_delta > result.calibrated_tolerance
    assert "disagree" in result.reason


def test_agreement_between_ocr_and_geometry_passes():
    """When OCR and geometry agree within calibrated tolerance, verification succeeds."""
    verifier = DonchianChannelVerifier()

    canvas = np.zeros((500, 400, 3), dtype=np.uint8)
    canvas[150:152, 50:350] = [255, 0, 0]

    result = verifier.verify_donchian_levels(
        ocr_upper=175.2,
        ocr_basis=150.0,
        ocr_lower=120.0,
        canvas_bgr=canvas,
        p_top=200.0,
        p_bottom=100.0,
        y_top=50,
        y_bottom=450
    )

    assert result.is_verified is True
    assert result.ocr_geometry_delta <= result.calibrated_tolerance


def test_signal_inhibited_on_indicator_discrepancy():
    """ConfluenceSignalEngine must inhibit signal if option chart state has indicator discrepancy."""
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
    # Option chart marked invalid due to INDICATOR_DISCREPANCY
    invalid_option = OptionChartState(
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
        brick_sequence_id=1,
        is_valid=False,  # Flagged false by extractor due to discrepancy!
        data_feed_state=DataFeedState.INDICATOR_DISCREPANCY
    )

    engine = ConfluenceSignalEngine(mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD)
    signal = engine.evaluate_entry(bullish_index, invalid_option)
    assert signal is None, "Signal must be strictly inhibited when DataFeedState is INDICATOR_DISCREPANCY"
