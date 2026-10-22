# core/decision_core.py
"""
Central Decision Core for Jarvis V2.1.
Authoritative component separating Intent Detection ("What does user mean?")
from Decision Making ("What should Jarvis do about it?").
Translates semantic actions, intents, and suggestions into validated ActionPlan objects.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from core.confirmation import classify_confirmation, ConfirmationType
from core.context import RuntimeContext
from core.execution.models import ActionPlan
from core.permissions import ActionRiskLevel, PermissionGuard, PermissionLevel

logger = logging.getLogger("jarvis.core.decision")


class DecisionCategory(str, Enum):
    """Categorization of decided operations."""
    ACTION = "ACTION"
    CONVERSATION = "CONVERSATION"
    WORKFLOW = "WORKFLOW"
    CONFIRMATION = "CONFIRMATION"
    CLARIFICATION = "CLARIFICATION"
    REJECTED = "REJECTED"


@dataclass
class DecisionResult:
    """Outcome of Decision Core evaluation."""
    category: DecisionCategory
    action_plan: Optional[ActionPlan] = None
    response_message: str = ""
    handled: bool = True
    needs_confirmation: bool = False
    confirmation_prompt: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class DecisionCore:
    """
    Central Decision Core for Jarvis V2.1.
    Translates intents, semantic actions, and proactive suggestions into
    validated ActionPlan instances, checking policy, resolving targets,
    and enforcing confirmation gating.
    """

    def __init__(
        self,
        permission_guard: Optional[PermissionGuard] = None,
        target_engine: Optional[Any] = None,
        runtime_context: Optional[RuntimeContext] = None,
    ):
        self.permission_guard = permission_guard or PermissionGuard()
        self.target_engine = target_engine
        self.runtime_context = runtime_context

    def plan_action(
        self,
        action: str,
        target: str = "",
        target_type: str = "general",
        parameters: Optional[Dict[str, Any]] = None,
        source: str = "user",
        confidence: float = 1.0,
        resolver: str = "auto",
        required_permission: str = "EXECUTE",
    ) -> ActionPlan:
        """
        Creates and validates a normalized ActionPlan, determining
        risk level, confirmation requirement, and verification strategy.
        """
        params = dict(parameters or {})
        risk_level, confirm_req = self.permission_guard.evaluate_action_risk(
            action=action, target=target, parameters=params
        )

        # Infer verification strategy
        verif_strat = "unverifiable"
        act_clean = (action or "").strip().lower()
        type_clean = (target_type or "").strip().lower()

        if type_clean in ("application", "app") or act_clean in ("launch_app", "open_app"):
            verif_strat = "process_running"
        elif type_clean == "window" or act_clean in ("focus", "maximize", "minimize", "restore"):
            verif_strat = "window_exists"
        elif type_clean == "folder" or act_clean in ("open_folder", "close_folder"):
            verif_strat = "folder_window_open"
        elif type_clean == "file" or act_clean in ("open_file", "write_file"):
            verif_strat = "file_exists"
        elif type_clean == "system_setting" or act_clean in ("set_volume", "adjust_volume"):
            verif_strat = "system_state"
        elif type_clean == "media" or act_clean in ("play_music", "media_play"):
            verif_strat = "system_state"

        ctx_key = (
            self.runtime_context.desktop.get_context_key()
            if self.runtime_context and hasattr(self.runtime_context, "desktop")
            else "global"
        )

        plan = ActionPlan(
            action=action,
            target=target,
            target_type=target_type,
            resolver=resolver,
            parameters=params,
            source=source,
            confidence=confidence,
            context_key=ctx_key,
            required_permission=required_permission,
            risk_level=risk_level.value,
            confirmation_required=confirm_req,
            confirmation_prompt=(
                f"Kya aap sach mein '{target or action}' execute karna chahte hain, Boss?"
                if confirm_req else None
            ),
            verification_strategy=verif_strat,
        )

        logger.info(
            "ACTION_PLANNED: id=%s action=%s target=%r type=%s risk=%s confirm=%s verif=%s",
            plan.plan_id, plan.action, plan.target, plan.target_type,
            plan.risk_level, plan.confirmation_required, plan.verification_strategy
        )
        return plan

    def evaluate_confirmation(self, user_input: str) -> Tuple[ConfirmationType, bool]:
        """
        Evaluates whether an utterance is affirmative, cancellation, or unrelated.
        Returns: (ConfirmationType, is_decided)
        """
        conf_type = classify_confirmation(user_input)
        is_decided = conf_type != ConfirmationType.UNSPECIFIED
        return conf_type, is_decided
