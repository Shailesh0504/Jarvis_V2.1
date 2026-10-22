# tests/trading/test_pair_validation.py
"""
Unit tests for PairValidator:
- Verifies NIFTY underlying
- Verifies option strike (positive int)
- Verifies CE/PE derivative type
- Verifies directional pairing (Bullish NIFTY -> CE; Bearish NIFTY -> PE)
- Rejects BANKNIFTY, FINNIFTY, zero strike, or misaligned contract
"""

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
from plugins.trading_signals.validation.pair_validator import PairValidator


@pytest.fixture
def validator():
    return PairValidator()


@pytest.fixture
def base_bullish_index():
    return IndexChartState(
        underlying="NIFTY 50",
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
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        donchian_upper=145.0,
        donchian_basis=135.0,
        donchian_lower=125.0,
        previous_price=140.0,
        previous_donchian_upper=145.0,
        donchian_breakout_event=True,
        brick_sequence_id=1,
        is_valid=True
    )


def test_valid_bullish_nifty_ce_pair(validator, base_bullish_index, base_ce_option):
    """Valid NIFTY index and NIFTY CE option passes validation."""
    result = validator.validate(base_bullish_index, base_ce_option)
    assert result.is_valid is True
    assert "aligned" in result.reason.lower()


def test_rejects_non_nifty_index(validator, base_bullish_index, base_ce_option):
    """Rejects non-NIFTY index like BANKNIFTY or SENSEX."""
    base_bullish_index.underlying = "BANKNIFTY"
    result = validator.validate(base_bullish_index, base_ce_option)
    assert result.is_valid is False
    assert "not recognized as NIFTY" in result.reason


def test_rejects_non_nifty_option_underlying(validator, base_bullish_index, base_ce_option):
    """Rejects option underlying not matching NIFTY."""
    base_ce_option.underlying = "FINNIFTY"
    result = validator.validate(base_bullish_index, base_ce_option)
    assert result.is_valid is False
    assert "does not match NIFTY" in result.reason


def test_rejects_invalid_strike(validator, base_bullish_index, base_ce_option):
    """Rejects strike <= 0."""
    base_ce_option.strike = 0
    result = validator.validate(base_bullish_index, base_ce_option)
    assert result.is_valid is False
    assert "strike" in result.reason.lower()


def test_directional_mismatch_bullish_index_with_pe(validator, base_bullish_index, base_ce_option):
    """Rejects PE option when Index is Bullish."""
    base_ce_option.option_type = OptionType.PE
    result = validator.validate(base_bullish_index, base_ce_option)
    assert result.is_valid is False
    assert "Expected CE" in result.reason


def test_directional_mismatch_bearish_index_with_ce(validator, base_bullish_index, base_ce_option):
    """Rejects CE option when Index is Bearish."""
    base_bullish_index.supertrend_bias = SuperTrendBias.BEARISH
    base_ce_option.option_type = OptionType.CE
    result = validator.validate(base_bullish_index, base_ce_option)
    assert result.is_valid is False
    assert "Expected PE" in result.reason


def test_valid_bearish_nifty_pe_pair(validator, base_bullish_index, base_ce_option):
    """Valid Bearish NIFTY Index with PE option passes validation."""
    base_bullish_index.supertrend_bias = SuperTrendBias.BEARISH
    base_bullish_index.renko_color = RenkoColor.RED
    base_ce_option.option_type = OptionType.PE
    result = validator.validate(base_bullish_index, base_ce_option)
    assert result.is_valid is True
