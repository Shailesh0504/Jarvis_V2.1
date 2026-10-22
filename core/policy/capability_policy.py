# core/policy/capability_policy.py
"""
Capability & Permission Policy Layer for Jarvis V2.1.
Enforces explicit risk classification (LOW / MEDIUM / HIGH / CRITICAL)
and execution decisions (ALLOW / CONFIRM / DENY) prior to planning or execution.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from core.permissions import ActionRiskLevel, PermissionGuard, PermissionLevel

logger = logging.getLogger("jarvis.core.policy")


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    CONFIRM = "CONFIRM"
    DENY = "DENY"


@dataclass
class PolicyEvaluationResult:
    decision: PolicyDecision
    risk_tier: ActionRiskLevel
    reason: str
    confirmation_prompt: Optional[str] = None
    required_role: str = "USER"
    audit_metadata: Dict[str, Any] = field(default_factory=dict)


class CapabilityPolicy:
    """
    Authoritative boundary for validating execution requests against system security,
    user privilege, and destructive operation guardrails.
    """

    # Critical destructive actions requiring explicit confirmation or admin escalation
    _CRITICAL_PATTERNS = [
        r"\b(?:format|wipe|destroy|erase_disk|drop_database|purge_all)\b",
        r"\b(?:shutdown|reboot|restart\s+system|power\s+off)\b",
    ]

    _HIGH_RISK_PATTERNS = [
        r"\b(?:delete|remove|unlink|rmdir|kill|terminate|drop)\b",
        r"\b(?:send_email|send_message|post_tweet|transfer_funds)\b",
        r"\b(?:modify_registry|disable_firewall|edit_hosts)\b",
    ]

    _MEDIUM_RISK_PATTERNS = [
        r"\b(?:write_file|edit_file|append_file|save_file|overwrite)\b",
        r"\b(?:change_setting|toggle_bluetooth|modify_config|uninstall)\b",
    ]

    def __init__(self, permission_guard: Optional[PermissionGuard] = None, enforce: bool = True):
        self.permission_guard = permission_guard or PermissionGuard(enforce=enforce)
        self.enforce = enforce

    def evaluate(
        self,
        action: str,
        target: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        user_role: str = "ADMIN"
    ) -> PolicyEvaluationResult:
        """
        Evaluates the requested action and target against security rules.
        Returns PolicyEvaluationResult with ALLOW, CONFIRM, or DENY.
        """
        if not self.enforce:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                risk_tier=ActionRiskLevel.LOW,
                reason="Policy enforcement disabled"
            )

        act = (action or "").strip().lower()
        tgt = (target or "").strip().lower()
        query = f"{act} {tgt}".strip()
        params = parameters or {}

        # 1. Critical Actions
        for pattern in self._CRITICAL_PATTERNS:
            if re.search(pattern, query):
                logger.warning(f"[CapabilityPolicy] CRITICAL action detected: '{query}'")
                prompt = f"Caution: '{action}' on '{target}' is a critical system operation. Are you sure you want to proceed?"
                return PolicyEvaluationResult(
                    decision=PolicyDecision.CONFIRM,
                    risk_tier=ActionRiskLevel.CRITICAL,
                    reason="Critical system operation requires explicit confirmation",
                    confirmation_prompt=prompt,
                    required_role="ADMIN"
                )

        # 2. High Risk Actions
        for pattern in self._HIGH_RISK_PATTERNS:
            if re.search(pattern, query):
                # Check for explicit safety override in parameters if pre-confirmed
                if params.get("confirmed", False):
                    return PolicyEvaluationResult(
                        decision=PolicyDecision.ALLOW,
                        risk_tier=ActionRiskLevel.HIGH,
                        reason="High risk action confirmed by user"
                    )
                prompt = f"'{action.capitalize()}' operation on '{target}' will permanently modify or delete data. Should I proceed?"
                return PolicyEvaluationResult(
                    decision=PolicyDecision.CONFIRM,
                    risk_tier=ActionRiskLevel.HIGH,
                    reason="Destructive operation requires confirmation",
                    confirmation_prompt=prompt,
                    required_role="USER"
                )

        # 3. Medium Risk Actions
        for pattern in self._MEDIUM_RISK_PATTERNS:
            if re.search(pattern, query):
                return PolicyEvaluationResult(
                    decision=PolicyDecision.ALLOW,
                    risk_tier=ActionRiskLevel.MEDIUM,
                    reason="Medium risk configuration or file update permitted"
                )

        # 4. Low Risk Actions (Default)
        return PolicyEvaluationResult(
            decision=PolicyDecision.ALLOW,
            risk_tier=ActionRiskLevel.LOW,
            reason="Standard benign operation permitted"
        )
