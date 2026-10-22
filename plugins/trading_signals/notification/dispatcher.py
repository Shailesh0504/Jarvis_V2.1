# plugins/trading_signals/notification/dispatcher.py
"""
Signal Notification Dispatcher.
Formats exact concise user notifications and emits canonical domain events onto the EventBus.
Strictly zero commentary, zero confidence metrics in user channels, zero profit guarantees.
"""

from dataclasses import dataclass
import logging
from typing import Any, Callable, Dict, Optional

from ..models.signal_types import CandidateSignal, SignalType

logger = logging.getLogger("jarvis.trading.notification")


class SignalNotificationDispatcher:
    """
    Emits verified trading recommendations across EventBus, GUI, and TTS.
    """

    def __init__(
        self,
        event_bus: Optional[Any] = None,
        tts_speaker: Optional[Callable[[str], None]] = None
    ):
        self.event_bus = event_bus
        self.tts_speaker = tts_speaker

    def format_user_message(self, candidate: CandidateSignal) -> str:
        """
        Produces the exact concise user-visible string:
        BUY <strike> CE
        BUY <strike> PE
        EXIT <strike> CE
        EXIT <strike> PE
        """
        action = candidate.signal_type.value
        strike = candidate.strike
        opt_type = candidate.option_type.upper()
        return f"{action} {strike} {opt_type}"

    def dispatch(self, candidate: CandidateSignal) -> str:
        """
        Dispatches the verified candidate signal to registered notification channels.
        Returns the exact concise notification string.
        """
        msg = self.format_user_message(candidate)

        # 1. Emit onto EventBus
        if self.event_bus and hasattr(self.event_bus, "emit"):
            payload = {
                "signal": msg,
                "signal_type": candidate.signal_type.value,
                "underlying": candidate.underlying,
                "strike": candidate.strike,
                "option_type": candidate.option_type,
                "price": candidate.price,
                "timestamp": candidate.timestamp,
                "trigger_mode": candidate.trigger_mode.value,
                "exit_reason": candidate.exit_reason.value,
                "brick_sequence_id": candidate.brick_sequence_id
            }
            try:
                self.event_bus.emit("trading.signal.generated", payload)
                logger.info("[EVENTBUS_EMIT] Emitted 'trading.signal.generated': %s", msg)
            except Exception as e:
                logger.error("[EVENTBUS_EMIT_FAIL] Failed to emit trading signal: %s", e)

        # 2. Audible notification (TTS)
        if self.tts_speaker:
            try:
                self.tts_speaker(msg)
            except Exception as e:
                logger.debug("[TTS_NOTIFY_FAIL] %s", e)

        logger.info("[USER_NOTIFICATION_DISPATCHED] '%s'", msg)
        return msg
