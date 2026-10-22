# tests/trading/test_donchian_breakout.py
"""
Unit tests for strict Donchian Upper-Band breakout transition event detection.
Verifies that only a true transition (prev <= upper and curr > upper) triggers a signal,
and sustained state or basis-line crosses are strictly rejected.
"""

import pytest
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
    SignalType
)
from plugins.trading_signals.strategy.confluence_engine import ConfluenceSignalEngine


@pytest.fixture
def bullish_index():
    return IndexChartState(
        underlying="NIFTY",
        current_price=24500.0,
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        ema_bias=SuperTrendBias.BULLISH,
        brick_sequence_id=12,
        last_trigger_brick_id=11,
        is_valid=True
    )


def test_valid_breakout_transition_triggers_signal(bullish_index):
    """Test prev <= upper and curr > upper triggers signal."""
    option = OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=105.0,
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        donchian_upper=100.0,
        donchian_basis=90.0,
        donchian_lower=80.0,
        previous_price=98.0,
        previous_donchian_upper=100.0,
        donchian_breakout_event=True,
        brick_sequence_id=1,
        is_valid=True
    )

    engine = ConfluenceSignalEngine(mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD)
    signal = engine.evaluate_entry(bullish_index, option)
    assert signal is not None
    assert signal.signal_type == SignalType.BUY


def test_sustained_price_above_band_is_rejected(bullish_index):
    """Test that price remaining above upper band (already crossed in previous brick) is rejected."""
    option = OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=110.0,
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        donchian_upper=100.0,
        donchian_basis=90.0,
        donchian_lower=80.0,
        previous_price=105.0,  # Already above 100 in previous brick!
        previous_donchian_upper=100.0,
        donchian_breakout_event=False,  # Not a fresh transition
        brick_sequence_id=2,
        is_valid=True
    )

    engine = ConfluenceSignalEngine(mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD)
    signal = engine.evaluate_entry(bullish_index, option)
    assert signal is None, "Sustained price above band must not trigger repeated breakout signal"


def test_basis_cross_only_is_rejected(bullish_index):
    """Test that crossing Donchian basis (middle line) but not upper band is rejected."""
    option = OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=95.0,  # Above basis 90, but below upper 100
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        donchian_upper=100.0,
        donchian_basis=90.0,
        donchian_lower=80.0,
        previous_price=88.0,
        previous_donchian_upper=100.0,
        donchian_breakout_event=False,
        brick_sequence_id=3,
        is_valid=True
    )

    engine = ConfluenceSignalEngine(mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD)
    signal = engine.evaluate_entry(bullish_index, option)
    assert signal is None, "Basis-line cross alone must be strictly rejected"


def test_price_at_upper_band_exact_boundary(bullish_index):
    """Test price exactly equal to upper band (not strictly greater) does not trigger breakout."""
    option = OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=100.0,  # Exactly at upper, not strictly greater
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        donchian_upper=100.0,
        donchian_basis=90.0,
        donchian_lower=80.0,
        previous_price=95.0,
        previous_donchian_upper=100.0,
        donchian_breakout_event=False,
        brick_sequence_id=4,
        is_valid=True
    )

    engine = ConfluenceSignalEngine(mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD)
    signal = engine.evaluate_entry(bullish_index, option)
    assert signal is None
