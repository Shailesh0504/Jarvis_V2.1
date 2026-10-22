# core/handlers/learning_handler.py
"""
Learning & Correction Handler for Jarvis V2.1.
Handles:
- Explicit verbal corrections
- Spelling feedback and auto-vocabulary learning
- Browser preference corrections
- Learning inspection, forget, and metrics commands
- Self-improvement feedback bridges
"""

import logging
from typing import Any, Optional

from core.intent import Intent

logger = logging.getLogger("jarvis.handlers.learning")


class LearningHandler:
    """Manages continuous self-improvement, user corrections, and vocabulary learning."""

    def __init__(self, core: Any):
        self.core = core

    def handle_learning_command(self, intent: Intent) -> str:
        """Processes learning-specific intents (corrections, vocabulary staging)."""
        core = self.core
        if not getattr(core, "learning_manager", None):
            return "Learning system is currently disabled."

        if intent.name == "user_correction":
            concept = intent.entities.get("concept", "setting")
            old_val = intent.entities.get("old_value", "previous")
            new_val = intent.entities.get("new_value", "new")
            expl = intent.entities.get("explanation", "")

            # Stage in ApprovalManager for user confirmation
            candidate = core.learning_manager.approval.stage_learning(
                layer=2,
                pattern_type="vocabulary",
                original_key=concept,
                proposed_val=new_val,
                confidence=0.91,
                prompt_text="Kya main ise future ke liye yaad rakhu?"
            )
            if getattr(core, "dialog_manager", None):
                core.dialog_manager.set_pending_learning(candidate)

            header = expl if expl else f"Previous assumption:\n{concept} → {old_val}\n\nCorrection:\n{concept} → {new_val}"
            return f"{header}\n\nKya main ise future ke liye yaad rakhu?"

        original = intent.entities.get("original", "")
        correction = intent.entities.get("correction", "")
        if original and correction:
            candidate = core.learning_manager.approval.stage_learning(
                layer=2,
                pattern_type="vocabulary",
                original_key=original,
                proposed_val=correction,
                confidence=0.95
            )
            if getattr(core, "dialog_manager", None):
                core.dialog_manager.set_pending_learning(candidate)
            return f"Understood: mapping '{original}' to '{correction}'. Kya main ise future ke liye yaad rakhu?"

        return "Learning update processed."
