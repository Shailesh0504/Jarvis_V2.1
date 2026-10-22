# tests/trading/test_position_lifecycle.py
"""
Unit tests for PositionStateTracker and ExitEvaluator:
- Enforces invariant: JARVIS_SIGNAL_ACTIVE != ACTUAL_BROKER_POSITION
- Never claims broker filled/order executed
- Position-aware EXIT (never emit EXIT while FLAT)
- 1st opposite brick: warning only
- 2nd consecutive opposite brick: EXIT
- Other exit triggers: Option ST breach, DC basis breach, Index reversal
- Window loss -> POSITION_STATE_UNKNOWN
- Cooldown period gating
"""

import time
import pytest
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
from plugins.trading_signals.models.signal_types import (
    CandidateSignal,
    ExitReason,
    PositionState,
    SignalType,
    StrategyTriggerMode
)
from plugins.trading_signals.state.position_tracker import PositionStateTracker
from plugins.trading_signals.strategy.exit_evaluator import ExitEvaluator


@pytest.fixture
def tracker():
    return PositionStateTracker(cooldown_seconds=10.0)


@pytest.fixture
def exit_evaluator(tracker):
    return ExitEvaluator(position_tracker=tracker)


@pytest.fixture
def active_ce_candidate():
    return CandidateSignal(
        signal_type=SignalType.BUY,
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        price=150.0,
        brick_sequence_id=1,
        strategy_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
        reason="Entry test"
    )


@pytest.fixture
def base_index_state():
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


def test_exit_inhibited_while_flat(exit_evaluator, base_index_state):
    """ExitEvaluator must inhibit exit signals when tracker is FLAT."""
    option_state = OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=130.0,
        renko_color=RenkoColor.RED,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.GREEN_TO_RED,
        consecutive_opposite_bricks=2,
        supertrend_bias=SuperTrendBias.BEARISH,
        supertrend_flip=SuperTrendFlip.BEARISH_FLIP,
        donchian_upper=150.0,
        donchian_basis=140.0,
        donchian_lower=120.0,
        previous_price=140.0,
        previous_donchian_upper=150.0,
        donchian_breakout_event=False,
        brick_sequence_id=15,
        is_valid=True
    )

    result = exit_evaluator.evaluate_exit(base_index_state, option_state)
    assert result.is_exit is False
    assert result.is_warning is False
    assert result.candidate is None
    assert "inhibited" in result.details.lower()


def test_buy_transitions_to_jarvis_signal_active(tracker, active_ce_candidate):
    """Dispatching BUY signal transitions state to JARVIS_SIGNAL_ACTIVE."""
    assert tracker.state == PositionState.FLAT
    tracker.on_buy_signal_dispatched(active_ce_candidate)
    assert tracker.state == PositionState.JARVIS_SIGNAL_ACTIVE
    assert tracker.is_active is True
    assert tracker.active_signal is not None
    assert tracker.active_signal.strike == 24500
    assert tracker.active_signal.option_type == "CE"


def test_first_opposite_brick_gives_warning_only(tracker, exit_evaluator, active_ce_candidate, base_index_state):
    """First confirmed opposite brick gives warning only, does not emit exit signal."""
    tracker.on_buy_signal_dispatched(active_ce_candidate)

    # First red brick appears
    red_brick_1 = OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=145.0,
        renko_color=RenkoColor.RED,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.GREEN_TO_RED,
        consecutive_opposite_bricks=1,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        donchian_upper=150.0,
        donchian_basis=140.0,
        donchian_lower=120.0,
        previous_price=150.0,
        previous_donchian_upper=150.0,
        donchian_breakout_event=False,
        brick_sequence_id=2,
        is_valid=True
    )

    result = exit_evaluator.evaluate_exit(base_index_state, red_brick_1)
    assert result.is_exit is False
    assert result.is_warning is True
    assert result.candidate is None

    tracker.on_exit_warning(2)
    assert tracker.state == PositionState.EXIT_WARNING_1_BRICK


def test_second_opposite_brick_triggers_exit(tracker, exit_evaluator, active_ce_candidate, base_index_state):
    """Second consecutive opposite brick triggers confirmed EXIT signal."""
    tracker.on_buy_signal_dispatched(active_ce_candidate)
    tracker.on_exit_warning(2)

    # Second red brick appears
    red_brick_2 = OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=140.0,
        renko_color=RenkoColor.RED,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        consecutive_opposite_bricks=2,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        donchian_upper=150.0,
        donchian_basis=135.0,
        donchian_lower=120.0,
        previous_price=145.0,
        previous_donchian_upper=150.0,
        donchian_breakout_event=False,
        brick_sequence_id=3,
        is_valid=True
    )

    result = exit_evaluator.evaluate_exit(base_index_state, red_brick_2)
    assert result.is_exit is True
    assert result.candidate is not None
    assert result.candidate.signal_type == SignalType.EXIT
    assert result.exit_reason == ExitReason.TWO_CONSECUTIVE_OPPOSITE_BRICKS

    tracker.on_exit_signal_dispatched(result.exit_reason)
    assert tracker.state == PositionState.COOLDOWN
    assert tracker.active_signal is None


def test_option_supertrend_breach_triggers_exit(tracker, exit_evaluator, active_ce_candidate, base_index_state):
    """Option SuperTrend flip to BEARISH triggers immediate EXIT."""
    tracker.on_buy_signal_dispatched(active_ce_candidate)

    st_flip_option = OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=142.0,
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        consecutive_opposite_bricks=0,
        supertrend_bias=SuperTrendBias.BEARISH,  # Flipped!
        supertrend_flip=SuperTrendFlip.BEARISH_FLIP,
        donchian_upper=150.0,
        donchian_basis=140.0,
        donchian_lower=120.0,
        previous_price=145.0,
        previous_donchian_upper=150.0,
        donchian_breakout_event=False,
        brick_sequence_id=4,
        is_valid=True
    )

    result = exit_evaluator.evaluate_exit(base_index_state, st_flip_option)
    assert result.is_exit is True
    assert result.exit_reason == ExitReason.OPTION_SUPERTREND_REVERSAL


def test_donchian_basis_breach_triggers_exit(tracker, exit_evaluator, active_ce_candidate, base_index_state):
    """Option price breaching below Donchian basis triggers EXIT."""
    tracker.on_buy_signal_dispatched(active_ce_candidate)

    basis_breach_option = OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=138.0,  # Below basis 140.0
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        consecutive_opposite_bricks=0,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        donchian_upper=150.0,
        donchian_basis=140.0,
        donchian_lower=120.0,
        previous_price=142.0,
        previous_donchian_upper=150.0,
        donchian_breakout_event=False,
        brick_sequence_id=5,
        is_valid=True
    )

    result = exit_evaluator.evaluate_exit(base_index_state, basis_breach_option)
    assert result.is_exit is True
    assert result.exit_reason == ExitReason.DONCHIAN_MIDDLE_BAND_BREACH


def test_window_loss_transitions_to_position_state_unknown(tracker, active_ce_candidate):
    """When chart window is lost during active signal, state becomes POSITION_STATE_UNKNOWN without external broker inference."""
    tracker.on_buy_signal_dispatched(active_ce_candidate)
    tracker.on_data_feed_loss("window_occluded")

    assert tracker.state == PositionState.POSITION_STATE_UNKNOWN
    # Must not evaluate buys or exits while UNKNOWN
    assert tracker.can_evaluate_buy() is False
    assert tracker.can_evaluate_exit() is False

    # When restored:
    tracker.on_data_feed_restored()
    assert tracker.state == PositionState.JARVIS_SIGNAL_ACTIVE
