# tests/trading/test_idempotency.py
"""
Unit tests for SignalIdempotencyManager:
- Duplicate suppression by deterministic event key
- Cooldown timer enforcement
- Single-execution semantics per confirmed brick
"""

import time
import pytest
from plugins.trading_signals.models.chart_state import OptionType
from plugins.trading_signals.models.signal_types import (
    CandidateSignal,
    SignalType,
    StrategyTriggerMode
)
from plugins.trading_signals.state.idempotency import SignalIdempotencyManager


@pytest.fixture
def idempotency_mgr():
    return SignalIdempotencyManager(cooldown_seconds=2.0)


@pytest.fixture
def sample_candidate():
    return CandidateSignal(
        signal_type=SignalType.BUY,
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        price=150.0,
        brick_sequence_id=5,
        strategy_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
        reason="Test breakout"
    )


def test_first_candidate_can_dispatch(idempotency_mgr, sample_candidate):
    """First candidate signal on a brick can be dispatched."""
    assert idempotency_mgr.can_dispatch(sample_candidate) is True


def test_duplicate_signal_on_same_brick_suppressed(idempotency_mgr, sample_candidate):
    """Identical signal on the same confirmed brick is strictly suppressed."""
    assert idempotency_mgr.can_dispatch(sample_candidate) is True
    idempotency_mgr.record_dispatch(sample_candidate)

    # Immediate second check on identical brick
    assert idempotency_mgr.can_dispatch(sample_candidate) is False


def test_cooldown_suppression_on_same_contract_next_brick(idempotency_mgr, sample_candidate):
    """Signals on new brick but within cooldown window are suppressed."""
    idempotency_mgr.record_dispatch(sample_candidate)

    # Next brick appears immediately (brick 6 instead of 5)
    next_brick_candidate = CandidateSignal(
        signal_type=SignalType.BUY,
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        price=155.0,
        brick_sequence_id=6,
        strategy_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
        reason="Next brick breakout"
    )

    # Within 2.0s cooldown -> False
    assert idempotency_mgr.can_dispatch(next_brick_candidate) is False

    # Sleep past cooldown
    time.sleep(2.1)
    assert idempotency_mgr.can_dispatch(next_brick_candidate) is True


def test_different_contract_independent_cooldown(idempotency_mgr, sample_candidate):
    """Different contract (e.g. PE or different strike) has independent dispatch."""
    idempotency_mgr.record_dispatch(sample_candidate)

    pe_candidate = CandidateSignal(
        signal_type=SignalType.BUY,
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.PE,
        price=140.0,
        brick_sequence_id=5,
        strategy_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
        reason="PE breakout"
    )

    assert idempotency_mgr.can_dispatch(pe_candidate) is True
