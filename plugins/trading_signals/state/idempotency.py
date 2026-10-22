# plugins/trading_signals/state/idempotency.py
"""
Signal Idempotency, Deduplication, and Cooldown Governance.
Prevents duplicate BUY recommendations from the same breakout event or closed brick.
"""

from dataclasses import dataclass
import logging
import time
from typing import Dict, Set

from ..models.signal_types import CandidateSignal, SignalType

logger = logging.getLogger("jarvis.trading.state.idempotency")


class SignalIdempotencyManager:
    """
    Tracks dispatched signal keys and ensures single-execution semantics per confirmed brick.
    """

    def __init__(self, cooldown_seconds: float = 30.0):
        self.cooldown_seconds = max(1.0, float(cooldown_seconds))
        self._dispatched_keys: Set[str] = set()
        self._last_signal_time_by_contract: Dict[str, float] = {}

    def build_event_key(self, candidate: CandidateSignal) -> str:
        """
        Creates a deterministic unique identity for a candidate signal.
        Key structure: <underlying>:<strike>:<option_type>:<brick_seq_id>:<signal_type>
        """
        return (
            f"{candidate.underlying.strip().lower()}:"
            f"{candidate.strike}:"
            f"{candidate.option_type.strip().lower()}:"
            f"{candidate.brick_sequence_id}:"
            f"{candidate.signal_type.value}"
        )

    def can_dispatch(self, candidate: CandidateSignal) -> bool:
        """
        Checks if candidate signal is novel (not a duplicate) and outside the cooldown window.
        """
        key = self.build_event_key(candidate)
        contract_key = f"{candidate.underlying}:{candidate.strike}:{candidate.option_type}"

        # 1. Exact brick deduplication check
        if key in self._dispatched_keys:
            logger.debug("[IDEMPOTENCY_REJECT] Signal key '%s' has already been dispatched.", key)
            return False

        # 2. Time-based cooldown check for BUY signals on the same contract
        if candidate.signal_type == SignalType.BUY:
            last_time = self._last_signal_time_by_contract.get(contract_key, 0.0)
            elapsed = time.time() - last_time
            if elapsed < self.cooldown_seconds:
                logger.debug(
                    "[COOLDOWN_REJECT] Contract '%s' in cooldown (%.1fs elapsed < %.1fs threshold).",
                    contract_key,
                    elapsed,
                    self.cooldown_seconds
                )
                return False

        return True

    def record_dispatch(self, candidate: CandidateSignal) -> None:
        """
        Records that a signal has been successfully dispatched to prevent duplicates.
        """
        key = self.build_event_key(candidate)
        contract_key = f"{candidate.underlying}:{candidate.strike}:{candidate.option_type}"
        self._dispatched_keys.add(key)
        self._last_signal_time_by_contract[contract_key] = time.time()
        logger.debug("[IDEMPOTENCY_RECORDED] Dispatched key '%s' recorded.", key)

    def clear(self) -> None:
        """Clears idempotency cache for testing or reset."""
        self._dispatched_keys.clear()
        self._last_signal_time_by_contract.clear()
