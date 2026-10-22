# learning/suggestions.py
"""Proactive contextual suggestions engine."""

import logging
from typing import Any, Dict, List

from .patterns import PatternLearner

logger = logging.getLogger("jarvis.learning.suggestions")


class SuggestionEngine:
    """Generates intelligent recommendations based on habits and frequent actions."""

    def __init__(self, pattern_learner: PatternLearner):
        self.patterns = pattern_learner

    def get_proactive_suggestions(self) -> List[str]:
        frequent = self.patterns.get_frequent_patterns(min_count=3, limit=3)
        suggestions = []
        for p in frequent:
            suggestions.append(f"You often run '{p['pattern_signature']}'. Would you like me to execute it?")
        return suggestions
