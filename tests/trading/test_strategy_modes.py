# tests/trading/test_strategy_modes.py
"""
Unit tests for strategy mode selection:
- REGIME_CONFIRMED_OPTION_LEAD (default)
- DUAL_FRESH_TRIGGER (N=2 window)
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
def base_bullish_index():
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
        last_trigger_brick_id=5,  # 5 bricks ago (stale for dual fresh, ok for persistent regime)
        is_valid=True
    )


@pytest.fixture
def base_ce_option():
    return OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=150.0,
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.BULLISH_FLIP,
        donchian_upper=148.0,
        donchian_basis=140.0,
        donchian_lower=130.0,
        previous_price=147.0,
        previous_donchian_upper=148.0,
        donchian_breakout_event=True,
        brick_sequence_id=25,
        is_valid=True
    )


def test_regime_confirmed_option_lead_buy_ce(base_bullish_index, base_ce_option):
    """Test CE buy under REGIME_CONFIRMED_OPTION_LEAD mode."""
    engine = ConfluenceSignalEngine(mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD)
    signal = engine.evaluate_entry(base_bullish_index, base_ce_option)

    assert signal is not None
    assert signal.signal_type == SignalType.BUY
    assert signal.option_type == "CE"
    assert signal.strike == 24500
    assert signal.strategy_mode == StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD
    assert "REGIME_CONFIRMED_OPTION_LEAD" in signal.reason


def test_regime_confirmed_option_lead_rejects_forming_index_brick(base_bullish_index, base_ce_option):
    """Forming index brick must reject candidate signal."""
    base_bullish_index.brick_status = BrickStatus.FORMING
    engine = ConfluenceSignalEngine(mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD)
    signal = engine.evaluate_entry(base_bullish_index, base_ce_option)
    assert signal is None


def test_regime_confirmed_option_lead_rejects_forming_option_brick(base_bullish_index, base_ce_option):
    """Forming option brick must reject candidate signal."""
    base_ce_option.brick_status = BrickStatus.FORMING
    engine = ConfluenceSignalEngine(mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD)
    signal = engine.evaluate_entry(base_bullish_index, base_ce_option)
    assert signal is None


def test_regime_confirmed_option_lead_rejects_unaligned_supertrend(base_bullish_index, base_ce_option):
    """Option SuperTrend must be bullish for CE buy."""
    base_ce_option.supertrend_bias = SuperTrendBias.BEARISH
    engine = ConfluenceSignalEngine(mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD)
    signal = engine.evaluate_entry(base_bullish_index, base_ce_option)
    assert signal is None


def test_dual_fresh_trigger_rejects_stale_index_event(base_bullish_index, base_ce_option):
    """DUAL_FRESH_TRIGGER rejects if last index trigger is older than N=2 bricks."""
    engine = ConfluenceSignalEngine(
        mode=StrategyTriggerMode.DUAL_FRESH_TRIGGER,
        fresh_window_n=2
    )
    # base_bullish_index brick_sequence_id=10, last_trigger_brick_id=5 -> diff = 5 > 2
    signal = engine.evaluate_entry(base_bullish_index, base_ce_option)
    assert signal is None


def test_dual_fresh_trigger_accepts_fresh_index_trigger_current_brick(base_bullish_index, base_ce_option):
    """DUAL_FRESH_TRIGGER accepts if index trigger occurred on current brick (diff=0)."""
    base_bullish_index.brick_sequence_id = 10
    base_bullish_index.last_trigger_brick_id = 10
    base_bullish_index.renko_transition = RenkoTransition.RED_TO_GREEN

    engine = ConfluenceSignalEngine(
        mode=StrategyTriggerMode.DUAL_FRESH_TRIGGER,
        fresh_window_n=2
    )
    signal = engine.evaluate_entry(base_bullish_index, base_ce_option)
    assert signal is not None
    assert signal.strategy_mode == StrategyTriggerMode.DUAL_FRESH_TRIGGER
    assert signal.signal_type == SignalType.BUY


def test_dual_fresh_trigger_accepts_fresh_index_trigger_n_minus_one_brick(base_bullish_index, base_ce_option):
    """DUAL_FRESH_TRIGGER accepts if index trigger occurred 1 brick ago (diff=1 <= 2)."""
    base_bullish_index.brick_sequence_id = 10
    base_bullish_index.last_trigger_brick_id = 9

    engine = ConfluenceSignalEngine(
        mode=StrategyTriggerMode.DUAL_FRESH_TRIGGER,
        fresh_window_n=2
    )
    signal = engine.evaluate_entry(base_bullish_index, base_ce_option)
    assert signal is not None
    assert signal.strategy_mode == StrategyTriggerMode.DUAL_FRESH_TRIGGER


def test_dual_fresh_trigger_rejects_when_diff_greater_than_n(base_bullish_index, base_ce_option):
    """DUAL_FRESH_TRIGGER rejects if diff > N."""
    base_bullish_index.brick_sequence_id = 10
    base_bullish_index.last_trigger_brick_id = 7  # diff = 3 > 2

    engine = ConfluenceSignalEngine(
        mode=StrategyTriggerMode.DUAL_FRESH_TRIGGER,
        fresh_window_n=2
    )
    signal = engine.evaluate_entry(base_bullish_index, base_ce_option)
    assert signal is None


def test_pe_signal_bearish_regime_confluence():
    """PE signal requires bearish index regime + bullish option premium breakout."""
    bearish_index = IndexChartState(
        underlying="NIFTY",
        current_price=24300.0,
        renko_color=RenkoColor.RED,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BEARISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        ema_bias=SuperTrendBias.BEARISH,
        brick_sequence_id=15,
        last_trigger_brick_id=14,
        is_valid=True
    )
    pe_option = OptionChartState(
        underlying="NIFTY",
        strike=24300,
        option_type=OptionType.PE,
        current_price=165.0,
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        donchian_upper=160.0,
        donchian_basis=150.0,
        donchian_lower=140.0,
        previous_price=159.0,
        previous_donchian_upper=160.0,
        donchian_breakout_event=True,
        brick_sequence_id=30,
        is_valid=True
    )

    engine = ConfluenceSignalEngine(mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD)
    signal = engine.evaluate_entry(bearish_index, pe_option)
    assert signal is not None
    assert signal.signal_type == SignalType.BUY
    assert signal.option_type == "PE"
    assert signal.strike == 24300
