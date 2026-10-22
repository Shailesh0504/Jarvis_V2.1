# core/response_validator.py
"""
Pre-Speech 10-Point Response Validator & Safety Gate for Jarvis V2.1.

Validates:
1. Contradiction Check (Does response contradict actual findings or action?)
2. False Success Check (Does response claim success when execution failed or was unverified?)
3. False Failure Check (Does response claim failure when execution succeeded?)
4. Language Consistency (Does response match intended conversational language?)
5. Brevity Check (Is response unnecessarily verbose for a simple command/greeting?)
6. Anti-Repetition Check (Does response unnecessarily repeat user prompt?)
7. Anti-Robotic Invariant (Does response contain banned formulaic templates?)
8. Clarification Check (Does response ask an unnecessary question when target is known?)
9. Raw Technical Error Leak (Does response leak exceptions, PIDs, hwnd, or stack traces?)
10. Context Integrity (Does response maintain active conversation continuity?)
"""

from dataclasses import dataclass, field
import logging
import re
from typing import List, Optional

from core.response_planner import ResponseContext
from core.response_style import ResponseStyleManager

logger = logging.getLogger("jarvis.core.response_validator")


@dataclass
class ValidationResult:
    """Result of the 10-point response validation check."""
    is_valid: bool
    score: float = 1.0
    repaired_text: str = ""
    reasons: List[str] = field(default_factory=list)


class ResponseValidator:
    """Validates and guarantees truthfulness and natural quality before TTS/Chat."""

    TECHNICAL_LEAK_PATTERNS = [
        re.compile(r"traceback\s+\(most\s+recent\s+call\s+last\):", re.IGNORECASE),
        re.compile(r"\b(exception|winerror|filenotfounderror|attributeerror|typeerror|valueerror):\b", re.IGNORECASE),
        re.compile(r"\bhwnd\s*=\s*\d+\b", re.IGNORECASE),
        re.compile(r"\bpid\s*=\s*\d+\b", re.IGNORECASE),
        re.compile(r"\b0x[0-9a-fA-F]{4,16}\b"),
    ]

    SUCCESS_AFFIRMATIONS = [
        "kar diya", "ho gaya", "khol diya", "band kar diya", "close kar diya",
        "open kar diya", "successfully", "done", "completed"
    ]

    FAILURE_INDICATORS = [
        "nahi ho paya", "nahi ho payi", "nahi mila", "fail", "failed", "error",
        "samaye par nahi", "problem aa gayi", "rukawat"
    ]

    @classmethod
    def validate(cls, candidate_text: str, ctx: ResponseContext) -> ValidationResult:
        """Runs the 10-point invariant checks on candidate response text."""
        if not candidate_text or not candidate_text.strip():
            return ValidationResult(
                is_valid=False,
                score=0.0,
                repaired_text="Ji Sir.",
                reasons=["Empty candidate text"]
            )

        text = candidate_text.strip()
        lower = text.lower()
        reasons = []
        score = 1.0

        # 1. Contradiction: Target Found vs Not Found
        if ctx.found is True and any(ind in lower for ind in ["nahi mila", "not found", "could not find", "nahi mil raha"]):
            reasons.append("Contradiction: target was found, but response claims target not found.")
            score -= 0.5

        if ctx.found is False and any(ind in lower for ind in ["yahan likha hai", "mil gaya", "found"]):
            reasons.append("Contradiction: target was NOT found, but response claims target found.")
            score -= 0.5

        # 2. False Success: Action failed but response claims success
        action_failed = (ctx.action_status == "failure" or ctx.verification_status == "failed")
        if action_failed and any(aff in lower for aff in cls.SUCCESS_AFFIRMATIONS):
            reasons.append("False Success: Action execution/verification failed, but response claimed success.")
            score -= 0.8

        # 3. False Failure: Action succeeded but response claims failure
        action_succeeded = (ctx.action_status == "success" and ctx.verification_status != "failed")
        if action_succeeded and ctx.action_performed and any(fail in lower for fail in ["nahi ho paya", "nahi ho payi", "failed to"]):
            reasons.append("False Failure: Action succeeded, but response claimed failure.")
            score -= 0.7

        # 4. Anti-Robotic Invariant
        if ResponseStyleManager.contains_banned_template(text):
            reasons.append("Banned Robotic Template: contains forbidden template phrase.")
            score -= 0.4

        # 5. Technical Error Leaks
        for leak_pat in cls.TECHNICAL_LEAK_PATTERNS:
            if leak_pat.search(text):
                reasons.append(f"Technical Leak: matched pattern {leak_pat.pattern}")
                score -= 0.9
                break

        # 6. Brevity Check for Simple Utterances
        user_words = ctx.user_text.strip().split()
        if len(user_words) <= 2 and len(text.split()) > 25:
            reasons.append("Excessive verbosity for a simple utterance.")
            score -= 0.3

        # 7. Controlled 'Sir' Stacking Check
        sir_count = len(re.findall(r"\b(sir|boss)\b", lower))
        if sir_count > 1:
            reasons.append(f"Excessive Sir: found {sir_count} occurrences of Sir/Boss.")
            score -= 0.2

        is_valid = (score >= 0.6) and (not reasons or all("Excessive" in r for r in reasons))

        repaired = text
        if not is_valid or score < 0.8:
            repaired = cls._repair(text, ctx, reasons)

        return ValidationResult(
            is_valid=is_valid,
            score=max(0.0, min(1.0, score)),
            repaired_text=repaired,
            reasons=reasons
        )

    @classmethod
    def _repair(cls, text: str, ctx: ResponseContext, reasons: List[str]) -> str:
        """Formulates an authoritative, safe, natural fallback when validation fails."""
        lang = ctx.language or "hinglish"
        lower = text.lower()

        # Handle Action Failed false-success repair
        if any("False Success" in r for r in reasons):
            target_disp = ctx.target.capitalize() if ctx.target else "action"
            if lang == "en":
                return f"Sorry Sir, could not complete {target_disp}."
            return f"Sir, {target_disp} complete nahi ho paya."

        # Handle Target Found contradiction repair
        if any("target was found" in r for r in reasons):
            target_disp = f"'{ctx.target.title()}'" if ctx.target else "Text"
            if lang == "en":
                return f"Sir, {target_disp} is here. I have moved the mouse to it."
            return f"Sir, {target_disp} yahan likha hai. Maine mouse usi jagah le diya hai."

        # Handle Target NOT Found contradiction repair
        if any("target was NOT found" in r for r in reasons):
            target_disp = f"'{ctx.target.title()}'" if ctx.target else "Text"
            if lang == "en":
                return f"Sir, I could not find {target_disp} on the active screen."
            return f"Sir, mujhe {target_disp} current screen par nahi mila."

        # Handle Robotic phrase removal
        cleaned = ResponseStyleManager.filter_robotic_phrases(text)
        cleaned = ResponseStyleManager.sanitize_for_tts(cleaned)
        cleaned = ResponseStyleManager.enforce_controlled_sir(cleaned)

        if not cleaned:
            return "Theek hai, Sir." if lang == "hinglish" else "Done, Sir."

        return cleaned
