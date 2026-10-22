# Auto-extracted domain goal mixin
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from core.capabilities import CapabilityDescriptor, get_capability_registry
from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from core.semantic.hindi_vocab import HindiVocabEngine
from core.semantic.models import IntentName
from core.semantic.normalizer import HinglishNormalizer
from core.semantic.resolution import (
    MultiDimensionalConfidence,
    ResolutionDecision,
    SemanticResolution,
)

logger = logging.getLogger("jarvis.semantic.goal_resolver")


class SoftwareUpdateGoalMixin:
    RE_UPDATE_CHECK = re.compile(
        r"\b(?:check\s+karo\s+(?:koi\s+)?(?:software\s+|windows\s+|system\s+)?updates?(?:\s+hai)?|"
        r"(?:kya\s+)?(?:koi\s+)?(?:software\s+|windows\s+|system\s+)?updates?\s+available\s+hai(?:\s+kya)?|"
        r"check\s+(?:for\s+)?(?:software\s+|windows\s+|system\s+)?updates?|"
        r"(?:software|windows|apps|system)\s+updates?\s+(?:check\s+karo|check\s+kar\s+do|dekho)|"
        r"(?:koi\s+)?updates?\s+(?:hai[n]?\s+kya|check\s+karo)|"
        r"software\s+aur\s+windows\s+dono\s+update\s+check\s+karo)\b",
        re.IGNORECASE,
    )
    RE_UPDATE_WINDOWS = re.compile(
        r"\b(?:windows\s+(?:bhi\s+)?update\s*(?:karo|kar\s+do|kardo)?|"
        r"update\s+(?:the\s+)?windows(?:\s+os)?|"
        r"os\s+update\s*(?:karo|kar\s+do|kardo)?)\b",
        re.IGNORECASE,
    )
    RE_UPDATE_ALL = re.compile(
        r"\b(?:(?:saare|sare|all|mere|sab|sab\s+kuch)\s+(?:software|apps|applications|programs)?\s*(?:update|latest)\s*(?:karo|kar\s+do|kardo)|"
        r"(?:software|apps|applications)\s+update\s*(?:kar\s+do|karo|kardo)|"
        r"jo\s+updates?\s+available\s+hai[n]?\s+(?:sab\s+)?install\s*(?:kar\s+do|karo|kardo)|"
        r"available\s+updates?\s+install\s*(?:kar\s+do|karo|kardo)|"
        r"sab\s+kuch\s+latest\s*(?:kar\s+do|karo|kardo)|"
        r"update\s+(?:all\s+)?(?:software|apps|applications|everything)|"
        r"(?:software\s+aur\s+windows|windows\s+aur\s+(?:software|apps))\s+(?:dono\s+)?update\s*(?:karo|kar\s+do|kardo))\b",
        re.IGNORECASE,
    )
    RE_UPDATE_CONFIRM_EXECUTE = re.compile(
        r"^(?:haan\s*,?\s*)?(?:sab\s+update\s*(?:kar\s+do|karo|kardo)|update\s*(?:kar\s+do|karo|kardo)|install\s*(?:kar\s+do|karo|kardo)|haan\s+kar\s+do|haan\s+sab\s+update\s+kar\s+do)$",
        re.IGNORECASE,
    )
    RE_UPDATE_CANCEL = re.compile(
        r"\b(?:update\s+band\s+karo|update\s+band\s+kar\s+do|cancel\s+update|stop\s+update|update\s+roko)\b",
        re.IGNORECASE,
    )
    @classmethod
    def _has_pending_update_plan(cls) -> bool:
        try:
            from core.software_update.manager import SoftwareUpdateManager
            mgr = SoftwareUpdateManager.get_instance()
            return mgr.pending_plan is not None
        except Exception:
            return False
    @classmethod
    def _resolve_software_update_goal(
        cls,
        raw_text: str,
        effective_text: str,
        context: Optional[Any],
        has_bhi: bool = False,
    ) -> SemanticResolution:
        """Resolves software and OS update goals respecting domain separation and multi-turn flow."""
        # 1. Cooperative Cancellation
        if cls.RE_UPDATE_CANCEL.search(effective_text):
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Cancel running software update",
                speech_act="ACTION_COMMAND",
                goal="CANCEL_UPDATE",
                intent="CANCEL_UPDATE",
                entities={"target": "software_update"},
                parameters={},
                context_dependencies=[],
                capability_required="software.update.winget",
                capability_available=True,
                confidence=0.98,
                action_plan={
                    "service": "software_update",
                    "action": "cancel_update",
                    "parameters": {},
                },
                decision=ResolutionDecision.EXECUTE,
            )

        # 2. Multi-turn execution of pending update plan
        if cls.RE_UPDATE_CONFIRM_EXECUTE.search(effective_text) and cls._has_pending_update_plan():
            from core.software_update.manager import SoftwareUpdateManager
            mgr = SoftwareUpdateManager.get_instance()
            scope = mgr.pending_plan.requested_scope.value if mgr.pending_plan else "ALL_SUPPORTED"
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Execute discovered software update plan",
                speech_act="ACTION_COMMAND",
                goal="EXECUTE_UPDATE_PLAN",
                intent="EXECUTE_UPDATE_PLAN",
                entities={"target": "software_update", "scope": scope},
                parameters={"scope": scope},
                context_dependencies=["pending_update_plan"],
                capability_required="software.update.winget",
                capability_available=True,
                confidence=1.0,
                action_plan={
                    "service": "software_update",
                    "action": "install_updates",
                    "parameters": {"scope": scope},
                },
                decision=ResolutionDecision.EXECUTE,
            )

        # 3. Check for updates only
        is_check = bool(
            cls.RE_UPDATE_CHECK.search(effective_text)
            or any(w in effective_text for w in ["check karo", "check kar do", "check updates", "updates hain kya", "updates available"])
        )
        if is_check and not any(w in effective_text for w in ["install", "sab update kar do", "update kar do", "latest kar do"]):
            scope = "ALL_SUPPORTED" if any(w in effective_text for w in ["dono", "windows", "system", "all"]) else "APPLICATIONS"
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Check for {scope.lower()} updates",
                speech_act="ACTION_COMMAND",
                goal="CHECK_FOR_UPDATES",
                intent="CHECK_FOR_UPDATES",
                entities={"target": "software_update", "scope": scope},
                parameters={"scope": scope},
                context_dependencies=[],
                capability_required="software.update.winget",
                capability_available=True,
                confidence=0.98,
                action_plan={
                    "service": "software_update",
                    "action": "check_updates",
                    "parameters": {"scope": scope},
                },
                decision=ResolutionDecision.EXECUTE,
            )

        # 4. Windows update specifically
        if cls.RE_UPDATE_WINDOWS.search(effective_text) and not any(w in effective_text for w in ["software", "apps", "application"]):
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Update Windows Operating System",
                speech_act="ACTION_COMMAND",
                goal="UPDATE_WINDOWS",
                intent="WINDOWS_UPDATE",
                entities={"target": "windows_os", "scope": "OS"},
                parameters={"scope": "OS", "action_mode": "install"},
                context_dependencies=[],
                capability_required="software.update.windows",
                capability_available=True,
                confidence=0.98,
                action_plan={
                    "service": "software_update",
                    "action": "windows_update",
                    "parameters": {"action_mode": "install"},
                },
                decision=ResolutionDecision.EXECUTE,
            )

        # 5. Broad / Application software update
        scope = "ALL_SUPPORTED" if any(w in effective_text for w in ["dono", "sab kuch", "windows", "everything"]) else "APPLICATIONS"
        return SemanticResolution(
            raw_input=raw_text,
            meaning="Update installed software applications",
            speech_act="ACTION_COMMAND",
            goal="UPDATE_INSTALLED_SOFTWARE",
            intent="SOFTWARE_UPDATE_ALL",
            entities={"target": "installed_software", "scope": scope},
            parameters={"scope": scope},
            context_dependencies=[],
            capability_required="software.update.winget",
            capability_available=True,
            confidence=0.98,
            action_plan={
                "service": "software_update",
                "action": "install_updates",
                "parameters": {"scope": scope},
            },
            decision=ResolutionDecision.EXECUTE,
        )
