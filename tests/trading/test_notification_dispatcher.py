# tests/trading/test_notification_dispatcher.py
"""
Unit tests for SignalNotificationDispatcher:
- Concise formatting:
  BUY <strike> CE
  BUY <strike> PE
  EXIT <strike> CE
  EXIT <strike> PE
- Zero commentary, no confidence numbers, no profit guarantees
- EventBus emission of 'trading.signal.generated'
- TTS delivery
"""

import pytest
from plugins.trading_signals.models.chart_state import OptionType
from plugins.trading_signals.models.signal_types import (
    CandidateSignal,
    ExitReason,
    SignalType,
    StrategyTriggerMode
)
from plugins.trading_signals.notification.dispatcher import SignalNotificationDispatcher


class MockEventBus:
    def __init__(self):
        self.emitted = []

    def emit(self, event_name, payload):
        self.emitted.append((event_name, payload))


def test_concise_buy_ce_formatting():
    """Verify exact concise format for BUY CE."""
    dispatcher = SignalNotificationDispatcher()
    candidate = CandidateSignal(
        signal_type=SignalType.BUY,
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        price=150.0,
        brick_sequence_id=1,
        strategy_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
        reason="Breakout"
    )
    msg = dispatcher.format_user_message(candidate)
    assert msg == "BUY 24500 CE"


def test_concise_buy_pe_formatting():
    """Verify exact concise format for BUY PE."""
    dispatcher = SignalNotificationDispatcher()
    candidate = CandidateSignal(
        signal_type=SignalType.BUY,
        underlying="NIFTY",
        strike=24400,
        option_type=OptionType.PE,
        price=165.0,
        brick_sequence_id=2,
        strategy_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
        reason="Breakout"
    )
    msg = dispatcher.format_user_message(candidate)
    assert msg == "BUY 24400 PE"


def test_concise_exit_ce_formatting():
    """Verify exact concise format for EXIT CE."""
    dispatcher = SignalNotificationDispatcher()
    candidate = CandidateSignal(
        signal_type=SignalType.EXIT,
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        price=140.0,
        brick_sequence_id=3,
        strategy_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
        exit_reason=ExitReason.TWO_CONSECUTIVE_OPPOSITE_BRICKS,
        reason="Reversal"
    )
    msg = dispatcher.format_user_message(candidate)
    assert msg == "EXIT 24500 CE"


def test_concise_exit_pe_formatting():
    """Verify exact concise format for EXIT PE."""
    dispatcher = SignalNotificationDispatcher()
    candidate = CandidateSignal(
        signal_type=SignalType.EXIT,
        underlying="NIFTY",
        strike=24400,
        option_type=OptionType.PE,
        price=155.0,
        brick_sequence_id=4,
        strategy_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
        exit_reason=ExitReason.OPTION_SUPERTREND_REVERSAL,
        reason="Reversal"
    )
    msg = dispatcher.format_user_message(candidate)
    assert msg == "EXIT 24400 PE"


def test_eventbus_dispatch_and_tts():
    """Verify EventBus emission and TTS invocation."""
    bus = MockEventBus()
    spoken = []
    dispatcher = SignalNotificationDispatcher(
        event_bus=bus,
        tts_speaker=lambda text: spoken.append(text)
    )

    candidate = CandidateSignal(
        signal_type=SignalType.BUY,
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        price=150.0,
        brick_sequence_id=1,
        strategy_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD,
        reason="Breakout"
    )

    result_msg = dispatcher.dispatch(candidate)
    assert result_msg == "BUY 24500 CE"
    assert len(bus.emitted) == 1
    assert bus.emitted[0][0] == "trading.signal.generated"
    assert bus.emitted[0][1]["signal"] == "BUY 24500 CE"
    assert spoken == ["BUY 24500 CE"]
