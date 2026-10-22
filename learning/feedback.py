# learning/feedback.py
"""User satisfaction and explicit feedback tracking."""

import logging
import time
from typing import Any, Dict, List, Optional

from memory.database import DatabaseManager

logger = logging.getLogger("jarvis.learning.feedback")


class FeedbackManager:
    """Records thumbs up/down and numeric score evaluations."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def record_feedback(self, turn_id: str, score: int, comment: Optional[str] = None) -> None:
        """Score: +1 (positive), -1 (negative), 0 (neutral)."""
        logger.info(f"Feedback recorded for turn {turn_id}: score={score}, comment={comment}")
