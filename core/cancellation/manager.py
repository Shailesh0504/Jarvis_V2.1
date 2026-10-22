# core/cancellation/manager.py
"""
Cancellation Manager for Jarvis V2.1.
Supports voice barge-in, explicit user stop commands, task cancellation,
and graceful cancellation propagation across pipeline steps.
"""

from dataclasses import dataclass, field
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("jarvis.core.cancellation")


@dataclass
class CancellationToken:
    """Thread-safe cancellation token with listener callbacks."""
    token_id: str
    is_cancelled: bool = False
    reason: str = ""
    cancelled_at: Optional[float] = None
    _callbacks: List[Callable[[str], None]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def cancel(self, reason: str = "User interrupted") -> None:
        with self._lock:
            if self.is_cancelled:
                return
            self.is_cancelled = True
            self.reason = reason
            self.cancelled_at = time.time()
            callbacks = list(self._callbacks)

        logger.info(f"[Cancellation] Token '{self.token_id}' cancelled: {reason}")
        for cb in callbacks:
            try:
                cb(reason)
            except Exception as e:
                logger.error(f"Error in cancellation callback for token '{self.token_id}': {e}")

    def register_callback(self, callback: Callable[[str], None]) -> None:
        with self._lock:
            if self.is_cancelled:
                # Fire immediately if already cancelled
                reason = self.reason
                do_call = True
            else:
                self._callbacks.append(callback)
                do_call = False

        if do_call:
            try:
                callback(reason)
            except Exception as e:
                logger.error(f"Error running immediate cancellation callback: {e}")


class CancellationManager:
    """
    Central registry for tracking, coordinating, and executing cancellations.
    Safely integrates with speech interruption (barge-in), active workflow stop,
    and long-running task termination.
    """

    _STOP_KEYWORDS = {
        "cancel", "stop", "ruk jao", "ruko", "band karo", "abort",
        "chup", "shant", "quiet", "silence", "pause"
    }

    def __init__(self):
        self._tokens: Dict[str, CancellationToken] = {}
        self._active_token_id: Optional[str] = None
        self._lock = threading.Lock()

    def create_token(self, identifier: str) -> CancellationToken:
        """Creates or retrieves an active cancellation token for a request/workflow."""
        with self._lock:
            token = CancellationToken(token_id=identifier)
            self._tokens[identifier] = token
            self._active_token_id = identifier
            return token

    def get_token(self, identifier: str) -> Optional[CancellationToken]:
        with self._lock:
            return self._tokens.get(identifier)

    def is_cancelled(self, identifier: Optional[str] = None) -> bool:
        with self._lock:
            target_id = identifier or self._active_token_id
            if not target_id or target_id not in self._tokens:
                return False
            return self._tokens[target_id].is_cancelled

    def cancel(self, identifier: Optional[str] = None, reason: str = "User interrupted") -> bool:
        """Cancels a specific or currently active operation."""
        with self._lock:
            target_id = identifier or self._active_token_id
            if not target_id or target_id not in self._tokens:
                logger.debug(f"[Cancellation] No active token found for ID '{target_id}'")
                return False
            token = self._tokens[target_id]

        token.cancel(reason=reason)
        return True

    def is_cancellation_intent(self, text: str) -> bool:
        """Detects whether a short utterance is an explicit cancellation / interruption request."""
        clean = (text or "").strip().lower()
        if clean in self._STOP_KEYWORDS:
            return True
        for kw in self._STOP_KEYWORDS:
            if clean == f"jarvis {kw}" or clean == f"{kw} jarvis":
                return True
        return False

    def cleanup(self, identifier: str) -> None:
        with self._lock:
            self._tokens.pop(identifier, None)
            if self._active_token_id == identifier:
                self._active_token_id = None
