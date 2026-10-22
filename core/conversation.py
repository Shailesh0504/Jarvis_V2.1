# core/conversation.py
"""Conversation management, text normalization, and wake-word stripping."""

import re
from typing import List, Optional, Tuple

from .context import SessionContext, TurnContext


class TextNormalizer:
    """Sanitizes, normalizes and cleans user input."""

    @staticmethod
    def normalize(text: str) -> str:
        if not text:
            return ""
        # 1. Trim leading/trailing whitespace
        cleaned = text.strip()
        # 2. Normalize whitespace sequences
        cleaned = re.sub(r"\s+", " ", cleaned)
        # 3. Strip surrounding quotation marks
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
            cleaned = cleaned[1:-1].strip()
        try:
            from core.semantic.normalizer import HinglishNormalizer
            cleaned = HinglishNormalizer.normalize_text(cleaned)
        except Exception:
            pass
        return cleaned

    @staticmethod
    def strip_punctuation(text: str) -> str:
        return re.sub(r"[^\w\s]", "", text)


class WakeWordDetector:
    """Checks for wake-word triggers and extracts clean command payload using the authoritative voice engine."""

    def __init__(self, wake_words: Optional[List[str]] = None):
        from voice.wake_word import WakeWordDetector as UniversalDetector
        self._detector = UniversalDetector(wake_words=wake_words)
        self.wake_words = self._detector.wake_words

    def detect_and_strip(self, text: str) -> Tuple[bool, str]:
        """
        Returns (is_wake_word_detected, payload_text).
        Detects wake word anywhere in the utterance (beginning, middle, end, or standalone)
        and extracts the clean command payload.
        """
        if not text:
            return False, ""

        res = self._detector.detect(text)
        if res.detected:
            return True, res.cleaned_command

        # Direct mode or no wake word
        normalized = TextNormalizer.normalize(text)
        return False, normalized


class ConversationManager:
    """Manages active conversation session, turns, context history, and generation-based barge-in invalidation."""

    def __init__(self, wake_words: Optional[List[str]] = None, history_limit: int = 10):
        self.normalizer = TextNormalizer()
        self.wake_detector = WakeWordDetector(wake_words=wake_words)
        self.session = SessionContext()
        self.history_limit = history_limit
        self.current_generation_id: int = 0

    def process_incoming_input(self, raw_text: str, source: str = "cli", repaired_text: Optional[str] = None) -> TurnContext:
        """Takes raw input, normalizes it, checks wake word, and creates an active TurnContext with a new generation ID."""
        text_to_process = repaired_text if repaired_text is not None else raw_text
        cleaned = self.normalizer.normalize(text_to_process)
        is_wake, payload = self.wake_detector.detect_and_strip(cleaned)

        # If source is cli or gui, consider wake word implicitly triggered even if omitted
        effective_payload = payload if payload else (cleaned if not is_wake else "")

        self.current_generation_id += 1

        turn = self.session.start_new_turn(raw_input=raw_text, source=source)
        turn.repaired_input = text_to_process
        turn.normalized_input = effective_payload if effective_payload else cleaned
        turn.wake_word_detected = is_wake
        turn.status = "ACTIVE"
        turn.generation_id = self.current_generation_id
        return turn

    def complete_turn(self, turn: TurnContext, response_text: str) -> None:
        """Finalizes the turn with the assistant's generated response if not already interrupted."""
        if turn.status == "INTERRUPTED":
            return
        turn.status = "COMPLETED"
        turn.response_text = response_text

    def interrupt_active_turn(self, reason: str = "user_barge_in") -> Optional[TurnContext]:
        """
        Immediately invalidates and marks the current active conversation turn as INTERRUPTED.
        Increments current_generation_id so any queued TTS chunks or stale background workers are permanently dropped.
        """
        import time
        self.current_generation_id += 1

        turn = self.session.get_current_turn()
        if turn and turn.status == "ACTIVE":
            turn.status = "INTERRUPTED"
            turn.interrupted_at = time.time()
            turn.metadata["interrupted"] = True
            turn.metadata["interruption_reason"] = reason
            return turn
        return None

    def is_current_generation(self, generation_id: int) -> bool:
        """Checks whether the specified generation ID matches the active conversation generation."""
        return generation_id == self.current_generation_id

    def get_history(self, limit: int = 5) -> List[TurnContext]:
        """Returns the most recent completed turns."""
        if hasattr(self.session, "turns") and self.session.turns:
            return self.session.turns[-limit:]
        return []

