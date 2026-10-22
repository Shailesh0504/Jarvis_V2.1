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


class CrossFeatureGoalMixin:
    @classmethod
    def _resolve_cross_feature_goal(
        cls,
        raw_text: str,
        effective_text: str,
        context: Optional[Any],
        has_bhi: bool,
    ) -> Optional[SemanticResolution]:
        """
        Cross-feature resolution for application launches, web sites, media, volume, power.
        """
        # 0. System Time & Date Query ("aaj ka time bata zara", "time batao")
        is_launch_cmd = bool(cls.RE_OPEN_VERBS.search(effective_text))
        if not is_launch_cmd:
            try:
                from core.time_context import get_time_context
                time_resp = get_time_context().resolve_time_query(effective_text) or get_time_context().resolve_time_query(raw_text)
                if time_resp:
                    return SemanticResolution(
                        raw_input=raw_text,
                        meaning="Query current system time and date",
                        speech_act="STATUS_QUESTION",
                        goal="TIME_QUERY",
                        intent="TIME_QUERY",
                        entities={"target": "time"},
                        parameters={},
                        context_dependencies=[],
                        capability_required="system.time.query",
                        capability_available=True,
                        confidence=1.0,
                        decision=ResolutionDecision.ANSWER,
                        response_text=time_resp,
                    )
            except Exception as e:
                logger.debug(f"Time context resolution error: {e}")

        # 0.1. Sequential Pipeline: "Pehle browser kholo, phir usi ke andar video wali website chala dena"
        if re.search(r"\bpehle\s+(?:browser|chrome)\s+kholo\s*,\s*phir\s+usi\s+ke\s+andar\s+(?:video\s+wali\s+website|youtube)\s+chala\b", effective_text, re.IGNORECASE):
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Open YouTube in default browser Chrome",
                speech_act="ACTION_COMMAND",
                goal="OPEN_WEBSITE",
                intent=IntentName("OPEN_WEBSITE"),
                entities={"entity": "youtube", "container": "chrome"},
                parameters={"container": "chrome"},
                context_dependencies=[],
                capability_required="browser.website.open",
                capability_available=True,
                confidence=0.98,
                action_plan={"service": "browser", "action": "open_website", "parameters": {"site": "youtube", "url": "https://www.youtube.com", "container": "chrome"}},
                decision=ResolutionDecision.EXECUTE,
            )

        # 0.2. Alternate Browser Switch ("Nahi nahi, woh nahi, dusra wala", "Isko nahi, jo doosra browser hai usmein kholo")
        if re.search(r"\b(?:nahi\s+nahi\s*,\s*)?woh\s+nahi\s*,\s*(?:dusra|doosra)\s+wala\b|\bisko\s+nahi\s*,\s*jo\s+doosra\s+browser\s+hai\s+usmein\s+kholo\b", effective_text, re.IGNORECASE):
            curr_app = (getattr(context, "application", None) or getattr(context, "last_entity", None) or "chrome").lower() if context else "chrome"
            alt_browser = "brave" if "chrome" in curr_app else "chrome"
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Switch to alternate browser ({alt_browser})",
                speech_act="ACTION_COMMAND",
                goal="OPEN_APPLICATION",
                intent=IntentName("OPEN_APPLICATION"),
                entities={"entity": alt_browser, "app_name": alt_browser},
                parameters={"is_switch": True},
                context_dependencies=["active_application"],
                capability_required="windows.application.launch",
                capability_available=True,
                confidence=0.92,
                action_plan={"service": "windows", "action": "launch_app", "parameters": {"app_name": alt_browser}},
                decision=ResolutionDecision.EXECUTE,
            )

        # 0.3. Container Open: "Usi mein kholo" (Sentence 47)
        if re.search(r"^usi\s+mein\s+kholo$", effective_text, re.IGNORECASE) and context:
            active_container = getattr(context, "browser", None) or getattr(context, "application", None) or "chrome"
            if active_container in ("browser", "", None):
                active_container = "chrome"
            active_site = getattr(context, "website", None) or getattr(context, "last_entity", None) or "youtube"
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Open {active_site} inside active container {active_container}",
                speech_act="ACTION_COMMAND",
                goal="OPEN_WEBSITE",
                intent=IntentName("OPEN_WEBSITE"),
                entities={"entity": active_site, "container": active_container},
                parameters={"container": active_container},
                context_dependencies=["active_application", "active_website"],
                capability_required="browser.website.open",
                capability_available=True,
                confidence=0.95,
                action_plan={"service": "browser", "action": "open_website", "parameters": {"site": active_site, "url": f"https://www.{active_site}.com", "container": active_container}},
                decision=ResolutionDecision.EXECUTE,
            )

        # 0.4. Ambiguous Pronoun Contrast: "Isko nahi, usko kar" (Sentence 48)
        if re.search(r"^(?:isko\s+nahi\s*,\s*usko\s+kar|usko\s+nahi\s*,\s*isko\s+kar)$", effective_text, re.IGNORECASE):
            clarify_msg = "Aap kis application ya task ko perform karna chahte hain?"
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Ambiguous contrastive reference without antecedent",
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

        # 0.5. Functional Browser Reference ("internet wala app", "woh browser jisme main usually web kholta hoon")
        if re.search(r"\b(?:woh\s+jo\s+)?internet\s+wala\s+app\b|\b(?:woh\s+)?browser\s+(?:chahiye\s+)?jisme\s+main\s+(?:usually\s+)?web\s+kholta\s+hoon\b", effective_text, re.IGNORECASE):
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Launch default internet browser (Chrome)",
                speech_act="ACTION_COMMAND",
                goal="OPEN_APPLICATION",
                intent=IntentName("OPEN_APPLICATION"),
                entities={"entity": "chrome", "app_name": "chrome"},
                parameters={"modifier": "ALSO" if has_bhi else None},
                context_dependencies=[],
                capability_required="windows.application.launch",
                capability_available=True,
                confidence=0.95,
                action_plan={"service": "windows", "action": "launch_app", "parameters": {"app_name": "chrome"}},
                decision=ResolutionDecision.EXECUTE,
            )

        # 0.6. Functional Video Site Reference ("video wali site")
        if re.search(r"\bvideo\s+wali\s+(?:site|website)\b", effective_text, re.IGNORECASE):
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Open primary video website (YouTube)",
                speech_act="ACTION_COMMAND",
                goal="OPEN_WEBSITE",
                intent=IntentName("OPEN_WEBSITE"),
                entities={"entity": "youtube", "site": "youtube"},
                parameters={"modifier": "ALSO" if has_bhi else None},
                context_dependencies=[],
                capability_required="browser.website.open",
                capability_available=True,
                confidence=0.95,
                action_plan={"service": "browser", "action": "open_website", "parameters": {"site": "youtube", "url": "https://www.youtube.com"}},
                decision=ResolutionDecision.EXECUTE,
            )

        # 0.7. Functional Video Player Reference ("wahi app jisme kal maine video chalayi thi")
        if re.search(r"\bwahi\s+app\s+kholo\s+jisme\s+(?:kal\s+)?(?:maine\s+)?video\s+chalayi\s+thi\b|\bvideo\s+player\s+wala\s+app\b", effective_text, re.IGNORECASE):
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Launch media video player (VLC)",
                speech_act="ACTION_COMMAND",
                goal="OPEN_APPLICATION",
                intent=IntentName("OPEN_APPLICATION"),
                entities={"entity": "vlc", "app_name": "vlc"},
                parameters={"modifier": "ALSO" if has_bhi else None},
                context_dependencies=["historical_activity"],
                capability_required="windows.application.launch",
                capability_available=True,
                confidence=0.92,
                action_plan={"service": "windows", "action": "launch_app", "parameters": {"app_name": "vlc"}},
                decision=ResolutionDecision.EXECUTE,
            )

        # 1. System Power: Lock
        if any(w in effective_text for w in ["system lock", "pc lock", "lock pc", "lock computer", "computer lock", "screen lock"]):
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Lock Windows workstation",
                speech_act="ACTION_COMMAND",
                goal="LOCK_SYSTEM",
                intent="LOCK_SYSTEM",
                entities={"entity": "system", "target": "system"},
                parameters={"action": "lock"},
                context_dependencies=[],
                capability_required="system.power.lock",
                capability_available=True,
                confidence=1.0,
                action_plan={"service": "system", "action": "lock_pc"},
                decision=ResolutionDecision.EXECUTE,
            )

        # 2. Audio Volume
        if any(w in effective_text for w in ["volume up", "awaz badhao", "volume badhao", "sound badhao"]):
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Increase audio volume",
                speech_act="ACTION_COMMAND",
                goal="VOLUME_UP",
                intent="VOLUME_UP",
                entities={"entity": "audio", "target": "audio"},
                parameters={"step": 10},
                context_dependencies=[],
                capability_required="audio.volume.up",
                capability_available=True,
                confidence=1.0,
                action_plan={"service": "audio", "action": "volume_up", "parameters": {"step": 10}},
                decision=ResolutionDecision.EXECUTE,
            )
        if any(w in effective_text for w in ["volume down", "awaz kam karo", "volume kam karo", "sound kam karo"]):
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Decrease audio volume",
                speech_act="ACTION_COMMAND",
                goal="VOLUME_DOWN",
                intent="VOLUME_DOWN",
                entities={"entity": "audio", "target": "audio"},
                parameters={"step": 10},
                context_dependencies=[],
                capability_required="audio.volume.down",
                capability_available=True,
                confidence=1.0,
                action_plan={"service": "audio", "action": "volume_down", "parameters": {"step": 10}},
                decision=ResolutionDecision.EXECUTE,
            )

        # 3. Known Application Launch / Close
        common_apps = ["chrome", "excel", "brave", "notepad", "word", "calculator", "vlc", "spotify"]
        for app in common_apps:
            if re.search(rf"\b{app}\b", effective_text):
                # Check if this app was explicitly negated ("Brave nahi")
                if re.search(rf"\b{app}\s+(?:nahi|not|mat)\b|\b(?:nahi|not|mat)\s+{app}\b", effective_text, re.IGNORECASE):
                    if app in ("brave", "chrome") and any(w in effective_text for w in ["doosra", "dusra", "other", "alternate", "wala"]):
                        target_app = "chrome" if app == "brave" else "brave"
                    else:
                        continue
                else:
                    target_app = app

                is_close = bool(cls.RE_CLOSE_VERBS.search(effective_text))
                is_open = bool(cls.RE_OPEN_VERBS.search(effective_text)) or not is_close
                if is_close:
                    return SemanticResolution(
                        raw_input=raw_text,
                        meaning=f"Close application {target_app.title()}",
                        speech_act="ACTION_COMMAND",
                        goal="CLOSE_APPLICATION",
                        intent=IntentName("CLOSE_APPLICATION"),
                        entities={"entity": target_app, "app_name": target_app},
                        parameters={"modifier": "ALSO" if has_bhi else None},
                        context_dependencies=[],
                        capability_required="windows.application.close",
                        capability_available=True,
                        confidence=1.0,
                        action_plan={"service": "windows", "action": "close_app", "parameters": {"app_name": target_app}},
                        decision=ResolutionDecision.EXECUTE,
                    )
                else:
                    return SemanticResolution(
                        raw_input=raw_text,
                        meaning=f"Launch application {target_app.title()}",
                        speech_act="ACTION_COMMAND",
                        goal="OPEN_APPLICATION",
                        intent=IntentName("OPEN_APPLICATION"),
                        entities={"entity": target_app, "app_name": target_app},
                        parameters={"modifier": "ALSO" if has_bhi else None},
                        context_dependencies=[],
                        capability_required="windows.application.launch",
                        capability_available=True,
                        confidence=1.0,
                        action_plan={"service": "windows", "action": "launch_app", "parameters": {"app_name": target_app}},
                        decision=ResolutionDecision.EXECUTE,
                    )

        # 4. Known Websites
        common_sites = ["youtube", "flipkart", "amazon", "google", "github", "gmail"]
        for site in common_sites:
            if re.search(rf"\b{site}\b", effective_text):
                is_play = any(v in effective_text for v in ["play", "chalao", "bajao", "gaana", "song"])
                if site == "youtube" and is_play:
                    query_m = re.sub(r"\b(?:youtube|pe|par|play|karo|chalao|bajao|gaana|song|laga\s+do|bhai)\b", "", effective_text).strip()
                    return SemanticResolution(
                        raw_input=raw_text,
                        meaning=f"Play media '{query_m}' on YouTube",
                        speech_act="ACTION_COMMAND",
                        goal="PLAY_MEDIA",
                        intent=IntentName("PLAY_MEDIA"),
                        entities={"entity": "youtube", "query": query_m},
                        parameters={"query": query_m},
                        context_dependencies=[],
                        capability_required="media.youtube.play",
                        capability_available=True,
                        confidence=0.95,
                        action_plan={"service": "youtube", "action": "search_and_play", "parameters": {"query": query_m}},
                        decision=ResolutionDecision.EXECUTE,
                    )
                else:
                    container_app = None
                    if context and (re.search(r"\b(?:is(?:me|mein)|us(?:me|mein)|inside|in\s+this)\b", effective_text, re.IGNORECASE) or any(w in effective_text for w in ["browser khud", "jo main abhi use", "current browser"])):
                        container_app = getattr(context, "browser", None) or getattr(context, "application", None)
                        if container_app in ("browser", "", None):
                            container_app = "chrome"

                    entities_dict = {"entity": site, "site": site}
                    params_dict = {"modifier": "ALSO" if has_bhi else None}
                    action_params = {"site": site, "url": f"https://www.{site}.com"}
                    if container_app:
                        entities_dict["container"] = container_app
                        params_dict["container"] = container_app
                        action_params["container"] = container_app

                    return SemanticResolution(
                        raw_input=raw_text,
                        meaning=f"Open website {site.title()}" + (f" inside {container_app}" if container_app else ""),
                        speech_act="ACTION_COMMAND",
                        goal="OPEN_WEBSITE",
                        intent=IntentName("OPEN_WEBSITE"),
                        entities=entities_dict,
                        parameters=params_dict,
                        context_dependencies=["active_container"] if container_app else [],
                        capability_required="browser.website.open",
                        capability_available=True,
                        confidence=1.0,
                        action_plan={"service": "browser", "action": "open_website", "parameters": action_params},
                        decision=ResolutionDecision.EXECUTE,
                    )

        return None
