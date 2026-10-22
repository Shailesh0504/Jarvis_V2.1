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


class ContextualGoalMixin:
    RE_MODIFIER_BHI = re.compile(r"\b(?:bhi|also|as\s+well|too)\b", re.IGNORECASE)
    RE_MODIFIER_REPEAT = re.compile(
        r"^(?:haan\s*,?\s*)?(?:(?:phir\s+se|dobara|again|once\s+more|ek\s+baar\s+aur|same\s+kaam|wahi\s+kaam|wohi\s+wala\s+kaam|wahi\s+wala|wahi|wohi|woh\s+hi|ye\s+bhi|same\s+again|repeat)\s*)+(?:karo|kar\s+do|kardo|chalao|kar|de)?$|"
        r"\b(?:ek\s+baar\s+aur\s+)?(?:wahi|wohi|same|woh\s+hi)\s*(?:cleanup|kaam|cheez|process|wala)?\s*(?:bhi\s+)?(?:ek\s+baar\s+aur|phir\s+se|dobara|repeat)?(?:\s+(?:karo|kar\s+do|kardo|kar\s+dena|kar|de))?\b|"
        r"\bjo\s+(?:abhi|pichhli\s+baar|last\s+time)\s+kiya\s+tha(?:\s+na)?(?:\s*,\s*|\s+)(?:same\s+cheez\s+)?(?:phir\s+se|dobara|repeat)\b|"
        r"\bmaine\s+jo\s+abhi\s+bola\s+tha\s+(?:usi\s+ko\s+)?repeat\b|"
        r"\bpichhle\s+command\s+ka\s+(?:jo\s+)?(?:second\s+part\s+tha|wahi)\s*(?:,\s*|\s+)(?:bas\s+)?(?:wahi\s+)?repeat\b|"
        r"\b(?:pehle\s+wala\s+kaam\s+rehne\s+de\s*,\s*)?baad\s+mein\s+jo\s+kiya\s+tha\s+woh\s+kar\b",
        re.IGNORECASE,
    )
    RE_INVERSE_ACTION = re.compile(
        r"\b(?:jo\s+pichhli\s+baar\s+kiya\s+tha\s*,\s*)?(?:uska\s+)?(?:ulta|opposite|reverse)\s+(?:kar|karo|kardo|kar\s+do|karna)\b",
        re.IGNORECASE,
    )
    RE_META_CONTEXT = re.compile(
        r"\b(?:main\s+(?:command\s+exact\s+nahi\s+bolunga|kaise\s+bolun\s+ye\s+mat\s+dekho)|mujhe\s+exact\s+command\s+yaad\s+nahi\s+hai)\b|"
        r"\b(?:tum\s+)?context\s+se\s+samajh(?:ne\s+ki\s+koshish\s+karo|lo)\b|"
        r"\bsamjho\s+main\s+karna\s+kya\s+chahta\s+hoon\b",
        re.IGNORECASE,
    )
    RE_MODIFIER_CONTAINER = re.compile(
        r"\b(?:is(?:me|mein)|us(?:me|mein)|yahan|in\s+this|inside)\b",
        re.IGNORECASE,
    )
    RE_MODIFIER_PRONOUN = re.compile(
        r"\b(?:is(?:ko|ey)|us(?:ko|ey)|yeh|woh|ye\s+wala|woh\s+wala)\b",
        re.IGNORECASE,
    )
    RE_CORRECTION = re.compile(
        r"^(?:nahi|nah|no|instead|wait|matlab),?\s+(.+)$",
        re.IGNORECASE,
    )
    RE_ISOLATED_PRONOUN_CMD = re.compile(
        r"^(?:woh|yeh|ye|isko|usko|wahi)\s+(?:kar\s+do|karo|kardo|chalao|khol\s+do|kholna)$",
        re.IGNORECASE,
    )
    RE_OPEN_VERBS = re.compile(
        r"\b(?:open|launch|start|kholo|khol\s+de|kholna|chalao|chala\s+do|le\s+aao|run)\b",
        re.IGNORECASE,
    )
    RE_CLOSE_VERBS = re.compile(
        r"\b(?:close|band|exit|terminate|kill|hatao|hata|remove|shut)\b",
        re.IGNORECASE,
    )
    @classmethod
    def _resolve_capability_question(
        cls,
        raw_text: str,
        effective_text: str,
        conv_res: Any,
    ) -> SemanticResolution:
        """Capability questions are answered conversationally; NEVER executed."""
        target = conv_res.target or "system"
        if "temp" in effective_text or "garbage" in effective_text or "kachra" in effective_text:
            ans = "Haan, main computer ki temporary files aur garbage saaf kar sakta hoon."
            cap = "system.maintenance.temp_cleanup"
            goal = "TEMP_FILE_CLEANUP"
        elif "recycle" in effective_text:
            ans = "Haan, main Recycle Bin khali kar sakta hoon."
            cap = "system.maintenance.recycle_bin"
            goal = "RECYCLE_BIN_CLEANUP"
        elif "lock" in effective_text:
            ans = "Haan, main system lock kar sakta hoon."
            cap = "system.power.lock"
            goal = "LOCK_SYSTEM"
        elif "chrome" in effective_text:
            ans = "Haan, main Chrome open kar sakta hoon."
            cap = "windows.application.launch"
            goal = "OPEN_APPLICATION"
        elif "update" in effective_text or "upgrade" in effective_text:
            ans = "Haan, main aapke installed software aur Windows OS ke updates check aur install kar sakta hoon."
            cap = "software.update.winget"
            goal = "UPDATE_INSTALLED_SOFTWARE"
        else:
            ans = conv_res.natural_response or f"Haan, main {target} manage kar sakta hoon."
            cap = f"system.{target}"
            goal = "CAPABILITY_INQUIRY"

        return SemanticResolution(
            raw_input=raw_text,
            meaning=f"Inquire capability to perform {goal}",
            speech_act="CAPABILITY_QUESTION",
            goal=goal,
            intent="CAPABILITY_INQUIRY",
            entities={"target": target},
            parameters={},
            context_dependencies=[],
            capability_required=cap,
            capability_available=True,
            confidence=conv_res.confidence,
            decision=ResolutionDecision.ANSWER,
            response_text=ans,
        )
    @classmethod
    def _resolve_status_question(
        cls,
        raw_text: str,
        effective_text: str,
        conv_res: Any,
    ) -> SemanticResolution:
        """Status questions inspect state; NEVER alter state."""
        target = conv_res.target or "system"
        if "update" in effective_text:
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Check if software or Windows updates are available",
                speech_act="STATUS_QUESTION",
                goal="CHECK_FOR_UPDATES",
                intent="CHECK_FOR_UPDATES",
                entities={"target": "software_update"},
                parameters={"scope": "ALL_SUPPORTED"},
                context_dependencies=[],
                capability_required="software.update.winget",
                capability_available=True,
                confidence=conv_res.confidence,
                action_plan={
                    "service": "software_update",
                    "action": "check_updates",
                    "parameters": {"scope": "ALL_SUPPORTED"},
                },
                decision=ResolutionDecision.EXECUTE,
                response_text="Updates status check kar raha hoon, Boss.",
            )

        return SemanticResolution(
            raw_input=raw_text,
            meaning=f"Query current status of {target}",
            speech_act="STATUS_QUESTION",
            goal="QUERY_STATUS",
            intent="STATUS_QUERY",
            entities={"target": target},
            parameters={},
            context_dependencies=[],
            capability_required="system.status",
            capability_available=True,
            confidence=conv_res.confidence,
            decision=ResolutionDecision.ANSWER,
            response_text=f"{target.capitalize()} status checked.",
        )
    @classmethod
    def _resolve_generic_repeat(
        cls,
        raw_text: str,
        effective_text: str,
        context: Any,
    ) -> SemanticResolution:
        """Repeats the last recorded actionable goal from context."""
        prev_intent = str(getattr(context, "last_intent", "") or "")
        prev_action = str(getattr(context, "last_action", "") or "")
        prev_entities = getattr(context, "last_entities", {}) or {}
        prev_service = getattr(context, "last_service", "system") or "system"

        return SemanticResolution(
            raw_input=raw_text,
            meaning=f"Repeat previous operation ({prev_action})",
            speech_act="ACTION_COMMAND",
            goal=prev_intent or "REPEAT_ACTION",
            intent=IntentName(prev_intent) if prev_intent else "REPEAT_ACTION",
            entities=prev_entities,
            parameters={"modifier": "REPEAT"},
            context_dependencies=["last_intent", "last_action", "last_entities"],
            capability_required=f"{prev_service}.{prev_action}",
            capability_available=True,
            confidence=0.95,
            action_plan={
                "service": prev_service,
                "action": prev_action,
                "parameters": prev_entities,
            },
            decision=ResolutionDecision.EXECUTE,
        )
    @classmethod
    def _resolve_container_followup(
        cls,
        raw_text: str,
        effective_text: str,
        container_app: str,
        has_bhi: bool,
    ) -> Optional[SemanticResolution]:
        """
        Resolves container follow-ups such as 'isme YouTube kholo' or 'isme Gmail bhi kholo'.
        Inherits container from active context.
        """
        # Browser switch commands should not be treated as container followups
        if re.search(r"\b(?:doosra|dusra)\s+browser\b", effective_text, re.IGNORECASE):
            return None

        # Normalize container
        if container_app in ("browser", "", None):
            container_app = "chrome"

        # Strip container markers ("isme", "usme", "in this")
        cleaned = re.sub(r"\b(?:is(?:me|mein)|us(?:me|mein)|yahan|in\s+this)\b", "", effective_text).strip()
        cleaned = re.sub(r"\b(?:bhi|also|please|zara|kholo|open|karo|kar\s+do|chalao|le\s+aao|run)\b", "", cleaned).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if cleaned:
            target_entity = cleaned
            known_sites = ["youtube", "gmail", "google", "flipkart", "amazon", "github"]
            for s in known_sites:
                if s in cleaned.lower():
                    target_entity = s
                    break

            is_web = any(w in target_entity for w in known_sites)
            action_name = "open_website" if is_web else "launch_app"
            goal_name = "OPEN_WEBSITE" if is_web else "OPEN_APPLICATION"
            service_name = "browser" if is_web else "windows"

            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Open {target_entity} inside {container_app}",
                speech_act="ACTION_COMMAND",
                goal=goal_name,
                intent=IntentName(goal_name),
                entities={"entity": target_entity, "container": container_app},
                parameters={"modifier": "ALSO" if has_bhi else None, "container": container_app},
                context_dependencies=["active_container"],
                capability_required=f"{service_name}.{action_name}",
                capability_available=True,
                confidence=0.92,
                action_plan={
                    "service": service_name,
                    "action": action_name,
                    "parameters": {"site": target_entity, "url": f"https://www.{target_entity}.com", "container": container_app},
                },
                decision=ResolutionDecision.EXECUTE,
            )
        return None
    @classmethod
    def _resolve_pronoun_action(
        cls,
        raw_text: str,
        effective_text: str,
        context: Any,
    ) -> Optional[SemanticResolution]:
        """
        Resolves pronoun commands such as 'isko band karo', 'isko minimize karo'.
        Extracts active entity from context.
        """
        active_target = getattr(context, "application", None) or getattr(context, "website", None) or getattr(context, "target", None)
        if not active_target:
            return None

        has_close = bool(cls.RE_CLOSE_VERBS.search(effective_text))
        has_min = "minimize" in effective_text or "chhota" in effective_text
        has_max = "maximize" in effective_text or "bada" in effective_text

        if has_close:
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Close active entity ({active_target})",
                speech_act="ACTION_COMMAND",
                goal="CLOSE_APPLICATION",
                intent=IntentName("CLOSE_APPLICATION"),
                entities={"entity": active_target, "app_name": active_target},
                parameters={"action": "close"},
                context_dependencies=["active_target"],
                capability_required="windows.application.close",
                capability_available=True,
                confidence=0.92,
                action_plan={
                    "service": "windows",
                    "action": "close_app",
                    "parameters": {"app_name": active_target},
                },
                decision=ResolutionDecision.EXECUTE,
            )
        elif has_min:
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Minimize active window ({active_target})",
                speech_act="ACTION_COMMAND",
                goal="MINIMIZE_WINDOW",
                intent=IntentName("MINIMIZE_WINDOW"),
                entities={"entity": active_target, "app_name": active_target},
                parameters={"action": "minimize"},
                context_dependencies=["active_target"],
                capability_required="windows.window.minimize",
                capability_available=True,
                confidence=0.92,
                action_plan={
                    "service": "windows",
                    "action": "minimize_window",
                    "parameters": {"app_name": active_target},
                },
                decision=ResolutionDecision.EXECUTE,
            )
        elif has_max:
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Maximize active window ({active_target})",
                speech_act="ACTION_COMMAND",
                goal="MAXIMIZE_WINDOW",
                intent=IntentName("MAXIMIZE_WINDOW"),
                entities={"entity": active_target, "app_name": active_target},
                parameters={"action": "maximize"},
                context_dependencies=["active_target"],
                capability_required="windows.window.maximize",
                capability_available=True,
                confidence=0.92,
                action_plan={
                    "service": "windows",
                    "action": "maximize_window",
                    "parameters": {"app_name": active_target},
                },
                decision=ResolutionDecision.EXECUTE,
            )
        return None
    @classmethod
    def _resolve_inverse_action(
        cls,
        raw_text: str,
        effective_text: str,
        context: Optional[Any],
    ) -> SemanticResolution:
        """
        Resolves inverse / opposite requests such as 'jo pichhli baar kiya tha, uska ulta kar'.
        """
        prev_intent = str(getattr(context, "last_intent", "") or "") if context else ""
        prev_action = str(getattr(context, "last_action", "") or "") if context else ""
        prev_app = getattr(context, "application", None) or getattr(context, "last_entity", None) or "chrome"

        if "OPEN" in prev_intent or "launch" in prev_action:
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Invert launch by closing {prev_app}",
                speech_act="ACTION_COMMAND",
                goal="CLOSE_APPLICATION",
                intent=IntentName("CLOSE_APPLICATION"),
                entities={"entity": prev_app, "app_name": prev_app},
                parameters={"action": "close", "inverse_of": prev_action or prev_intent},
                context_dependencies=["last_intent", "last_action"],
                capability_required="windows.application.close",
                capability_available=True,
                confidence=0.92,
                action_plan={"service": "windows", "action": "close_app", "parameters": {"app_name": prev_app}},
                decision=ResolutionDecision.EXECUTE,
            )
        elif "CLOSE" in prev_intent or "close" in prev_action:
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Invert close by opening {prev_app}",
                speech_act="ACTION_COMMAND",
                goal="OPEN_APPLICATION",
                intent=IntentName("OPEN_APPLICATION"),
                entities={"entity": prev_app, "app_name": prev_app},
                parameters={"action": "open", "inverse_of": prev_action or prev_intent},
                context_dependencies=["last_intent", "last_action"],
                capability_required="windows.application.launch",
                capability_available=True,
                confidence=0.92,
                action_plan={"service": "windows", "action": "launch_app", "parameters": {"app_name": prev_app}},
                decision=ResolutionDecision.EXECUTE,
            )
        elif "MUTE" in prev_intent:
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Invert mute by unmuting audio",
                speech_act="ACTION_COMMAND",
                goal="UNMUTE",
                intent="UNMUTE",
                entities={"entity": "audio"},
                parameters={},
                context_dependencies=["last_intent"],
                capability_required="audio.volume.unmute",
                capability_available=True,
                confidence=0.95,
                action_plan={"service": "audio", "action": "unmute"},
                decision=ResolutionDecision.EXECUTE,
            )
        elif "UNMUTE" in prev_intent:
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Invert unmute by muting audio",
                speech_act="ACTION_COMMAND",
                goal="MUTE",
                intent="MUTE",
                entities={"entity": "audio"},
                parameters={},
                context_dependencies=["last_intent"],
                capability_required="audio.volume.mute",
                capability_available=True,
                confidence=0.95,
                action_plan={"service": "audio", "action": "mute"},
                decision=ResolutionDecision.EXECUTE,
            )
        elif "VOLUME_UP" in prev_intent:
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Invert volume up by decreasing volume",
                speech_act="ACTION_COMMAND",
                goal="VOLUME_DOWN",
                intent="VOLUME_DOWN",
                entities={"entity": "audio"},
                parameters={"step": 10},
                context_dependencies=["last_intent"],
                capability_required="audio.volume.down",
                capability_available=True,
                confidence=0.95,
                action_plan={"service": "audio", "action": "volume_down", "parameters": {"step": 10}},
                decision=ResolutionDecision.EXECUTE,
            )
        elif "VOLUME_DOWN" in prev_intent:
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Invert volume down by increasing volume",
                speech_act="ACTION_COMMAND",
                goal="VOLUME_UP",
                intent="VOLUME_UP",
                entities={"entity": "audio"},
                parameters={"step": 10},
                context_dependencies=["last_intent"],
                capability_required="audio.volume.up",
                capability_available=True,
                confidence=0.95,
                action_plan={"service": "audio", "action": "volume_up", "parameters": {"step": 10}},
                decision=ResolutionDecision.EXECUTE,
            )

        # Fallback clarification if no reversible previous action exists
        clarify_msg = "Pichla koi reversible action detect nahi hua, aap kya perform karna chahte hain?"
        return SemanticResolution(
            raw_input=raw_text,
            meaning="Inverse action requested without reversible antecedent",
            speech_act="ACTION_COMMAND",
            goal="AMBIGUOUS_COMMAND",
            intent="UNKNOWN",
            entities={},
            parameters={},
            context_dependencies=[],
            capability_required="",
            capability_available=False,
            confidence=0.30,
            decision=ResolutionDecision.ASK_PRECISE_CLARIFICATION,
            clarification_prompt=clarify_msg,
            response_text=clarify_msg,
        )
    @classmethod
    def _resolve_meta_contextual(
        cls,
        raw_text: str,
        effective_text: str,
        context: Optional[Any],
    ) -> SemanticResolution:
        """
        Resolves meta-contextual requests where the user explicitly tells Jarvis
        to infer intent from active context ('tum context se samajhne ki koshish karo', 'samjho main kya chahta hoon').
        """
        active_app = getattr(context, "application", None) if context else None
        active_site = getattr(context, "website", None) if context else None
        last_intent = getattr(context, "last_intent", None) if context else None

        if active_app or active_site:
            target = active_site or active_app
            ans = f"Samajh gaya Boss. Abhi {target.capitalize()} active hai. Kya aap isme navigation, search, ya window control chahte hain?"
        elif last_intent:
            ans = f"Samajh gaya Boss. Pichla action {last_intent} tha. Batayein isey repeat karun ya koi naya task shuru karun?"
        else:
            ans = "Main context samajhne ke liye ready hoon Boss. Abhi koi application ya task active nahi hai — batayein browser, media playback, ya system cleanup mein se kya start karun?"

        return SemanticResolution(
            raw_input=raw_text,
            meaning="Meta-contextual intent inference request",
            speech_act="CONVERSATIONAL_GUIDANCE",
            goal="META_CONTEXTUAL_ASSISTANCE",
            intent="META_ASSISTANCE",
            entities={"active_target": active_site or active_app},
            parameters={},
            context_dependencies=["active_context"],
            capability_required="core.conversational_guidance",
            capability_available=True,
            confidence=0.90,
            decision=ResolutionDecision.ANSWER,
            response_text=ans,
        )
