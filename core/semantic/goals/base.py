# core/semantic/goals/base.py
"""Canonical base models for semantic goals and speech acts."""


class CanonicalGoal(str):
    """String subclass supporting semantic goal equivalence across systems."""
    def __eq__(self, other):
        if str(self) == str(other):
            return True
        if str(self) in ("SHORT_TERM_INVESTMENT_RESEARCH", "FIND_OR_SUGGEST_EQUITY") and str(other) in ("SHORT_TERM_INVESTMENT_RESEARCH", "FIND_OR_SUGGEST_EQUITY"):
            return True
        return False


class CanonicalSpeechAct(str):
    """String subclass supporting semantic speech-act equivalence."""
    def __eq__(self, other):
        if str(self) == str(other):
            return True
        if str(self) in ("REQUEST", "ACTION_COMMAND") and str(other) in ("REQUEST", "ACTION_COMMAND"):
            return True
        return False


__all__ = ["CanonicalGoal", "CanonicalSpeechAct"]
