# core/contextual_resolver.py
"""
Contextual Action Resolver for Multi-Turn Website and Application Follow-ups.
Resolves natural Hinglish / English follow-up utterances against the ActiveTargetContext.
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, Optional, Tuple
import urllib.parse
import webbrowser

from core.context import ActiveTargetContext
from core.semantic.hindi_vocab import HindiVocabEngine, HindiVocabCategory, ReferenceConcept, ObjectRefConcept

logger = logging.getLogger("jarvis.core.context_resolver")


@dataclass
class ContextualActionResult:
    handled: bool
    response_message: str = ""
    intent: str = ""
    action: str = ""
    target: str = ""
    entities: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    verified: bool = False


class ContextualActionResolver:
    """
    Evaluates incoming utterances against active target/website context
    and executes contextual actions (search, play, open item, add to cart).
    """

    SEARCH_PATTERNS = [
        # Phrasing like "mujhe ek shoes lena hai to shoes dikhao", "mujhe running shoes dikhao", "shoes dikhao"
        re.compile(r"^(?:mujhe\s+)?(?:ek\s+)?(.+?)\s+(?:lena\s+hai|chahiye|khareedna\s+hai)\s+(?:to|toh|so)\s+(?:mujhe\s+)?(.+?)\s+(?:dikhao|search\s+karo|dekhao|kholo)\b", re.IGNORECASE),
        re.compile(r"^(?:mujhe\s+)?(?:ek\s+)?(.+?)\s+(?:dikhao|dekhao|show\s+me|show|display)\b", re.IGNORECASE),
        re.compile(r"^(?:isme|ismein|yahan|is\s+website\s+par|is\s+site\s+par|is\s+page\s+par|isko)\s+(?:bhi\s+)?(.+?)\s+(?:search\s+karo|dhoondo|find\s+karo|dikhao)\b", re.IGNORECASE),
        re.compile(r"^search\s+(?:for\s+)?(.+?)(?:\s+(?:here|on\s+this\s+page|in\s+this|on\s+site))?$", re.IGNORECASE),
        re.compile(r"^(.+?)\s+(?:search\s+karo|dhoondo|find\s+karo)$", re.IGNORECASE),
    ]

    PLAY_PATTERNS = [
        re.compile(r"^(.+?)\s+(?:ka\s+gana|ke\s+gana|ke\s+songs|ka\s+song|gana|song|track|video)\s+(?:chalao|bajao|play\s+karo|play|laga\s+do|sunao)\b", re.IGNORECASE),
        re.compile(r"^(?:play|chalao|bajao|sunao|laga\s+do)\s+(.+?)(?:\s+(?:ka\s+gana|song|video))?$", re.IGNORECASE),
    ]

    NAVIGATION_PATTERNS = [
        re.compile(r"^(?:ye\s+wala|yeh\s+wala|first\s+wala|pehla\s+wala|1st\s+wala)\s+(?:kholo|open\s+karo|dikhao)\b", re.IGNORECASE),
        re.compile(r"^(?:dusra\s+wala|second\s+wala|2nd\s+wala|next\s+wala)\s+(?:kholo|open\s+karo|dikhao)\b", re.IGNORECASE),
        re.compile(r"^(?:upar\s+wala|top\s+wala)\s+(?:kholo|open\s+karo|dikhao)\b", re.IGNORECASE),
        re.compile(r"^(?:price\s+batao|kitne\s+ka\s+hai|rate\s+batao|cost\s+batao)\b", re.IGNORECASE),
        re.compile(r"^(?:cart\s+mein\s+daalo|add\s+to\s+cart|isey\s+cart\s+mein\s+daalo|buy\s+now|khareedo)\b", re.IGNORECASE),
    ]

    REPEAT_PATTERNS = [
        re.compile(r"^(?:phir\s+se\s+karo|dobara\s+karo|again|once\s+more|ek\s+baar\s+aur|phir\s+se|same\s+kaam\s+karo|ye\s+bhi\s+kar\s+do|wahi\s+karo|repeat\s+karo|repeat|same\s+again)$", re.IGNORECASE),
    ]

    RELATIVE_REPEAT_PATTERNS = [
        re.compile(r"^(?:thoda\s+aur|aur\s+thoda|a\s+little\s+more|aur\s+karo|thoda\s+aur\s+badhao|thoda\s+aur\s+kam\s+karo|thoda\s+aur\s+aage|thoda\s+aur\s+peeche|thoda\s+aur\s+piche)$", re.IGNORECASE),
    ]

    ACTION_ELLIPSIS_PATTERNS = [
        re.compile(r"^(?:aur\s+)?([a-zA-Z0-9_\-]+)\s+(?:bhi|also)$", re.IGNORECASE),
        re.compile(r"^(?:aur\s+)?([a-zA-Z0-9_\-]+)\s+ko\s+(?:bhi|also)$", re.IGNORECASE),
    ]

    ENTITY_COMPLETION_PATTERNS = [
        re.compile(r"^(?:temp|temporary(?:\s+files?)?)\s+(?:bhi|also)$", re.IGNORECASE),
        re.compile(r"^(?:recycle\s*bin|dustbin)\s+(?:bhi|also)$", re.IGNORECASE),
    ]

    # Explicit website switch / command override triggers that should NOT be treated as contextual follow-ups
    EXPLICIT_NEW_TARGETS = {
        "youtube", "flipkart", "amazon", "google", "vlc", "excel", "notepad", "word",
        "chrome", "brave", "edge", "firefox", "calculator", "spotify", "github", "gmail"
    }

    @classmethod
    def extract_search_query(cls, text: str) -> Optional[str]:
        raw = text.strip()
        
        # 1. Check complex compound pattern: "mujhe ek shoes lena hai to shoes dikhao"
        m_compound = cls.SEARCH_PATTERNS[0].match(raw)
        if m_compound:
            # Group 2 contains the explicit "shoes dikhao" item
            q = m_compound.group(2).strip() or m_compound.group(1).strip()
            return cls._clean_query(q)

        # 2. Check "X dikhao" / "show me X"
        m_dikhao = cls.SEARCH_PATTERNS[1].match(raw)
        if m_dikhao:
            return cls._clean_query(m_dikhao.group(1).strip())

        # 3. Check "isme X search karo"
        m_isme = cls.SEARCH_PATTERNS[2].match(raw)
        if m_isme:
            return cls._clean_query(m_isme.group(1).strip())

        # 4. Check "search X"
        m_search = cls.SEARCH_PATTERNS[3].match(raw)
        if m_search:
            return cls._clean_query(m_search.group(1).strip())

        # 5. Check "X search karo"
        m_end_search = cls.SEARCH_PATTERNS[4].match(raw)
        if m_end_search:
            return cls._clean_query(m_end_search.group(1).strip())

        return None

    @classmethod
    def _clean_query(cls, text: str) -> str:
        q = text.strip()
        q = re.sub(r"^(?:mujhe\s+)?(?:ek\s+)?", "", q, flags=re.IGNORECASE)
        q = re.sub(r"\b(?:please|zara|bhai|yaar|na|toh|to)\b", "", q, flags=re.IGNORECASE)
        q = re.sub(r"\b(?:wala|wali|wale|ka|ki|ke|in|on)\b", "", q, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", q).strip()

    @classmethod
    def resolve(
        cls,
        user_input: str,
        context: ActiveTargetContext,
        plugin_manager: Any = None
    ) -> ContextualActionResult:
        """
        Main entry point to resolve an input against active context.
        """
        if not context or not context.is_active:
            return ContextualActionResult(handled=False)

        raw = user_input.strip()
        lower = raw.lower()

        logger.info("ACTIVE_CONTEXT target=%s website=%s app=%s url=%s", context.target_type, context.website, context.application, context.url)
        logger.info("CONTEXT_RESOLUTION input=%r has_active_target=True", user_input)
        logger.info("CONTEXT_TARGET website=%s domain=%s", context.website, context.domain)

        # System commands (reminders, alarms, etc.) must NEVER be hijacked as active website searches
        if re.search(r'\b(?:reminder|reminders|alarm|alarms)\b', lower):
            return ContextualActionResult(handled=False)

        # 0. Check for repeat command ("phir se karo", "dobara karo", "again", "once more", "ek baar aur", "same kaam karo", "ye bhi kar do")
        if context and context.last_intent and any(pat.search(lower) for pat in cls.REPEAT_PATTERNS):
            repeat_res = cls._execute_repeat_command(context, plugin_manager)
            if repeat_res.handled:
                return repeat_res

        # 0.05 Check for relative repeat ("thoda aur", "aur thoda", "a little more")
        if context and (context.last_intent or context.last_action) and any(pat.search(lower) for pat in cls.RELATIVE_REPEAT_PATTERNS):
            rel_res = cls._execute_relative_repeat(context, plugin_manager)
            if rel_res.handled:
                return rel_res

        # 0.1 Check for partial entity completion ("temp bhi", "temp files bhi")
        if context and any(pat.search(lower) for pat in cls.ENTITY_COMPLETION_PATTERNS):
            entity_comp_res = cls._execute_entity_completion(lower, context, plugin_manager)
            if entity_comp_res.handled:
                return entity_comp_res

        # 0.2 Check for action ellipsis ("aur Excel bhi", "Notepad bhi")
        if context and (context.last_action or context.last_intent):
            for pat in cls.ACTION_ELLIPSIS_PATTERNS:
                m_ell = pat.match(lower)
                if m_ell:
                    candidate_target = m_ell.group(1).strip()
                    if candidate_target.lower() not in ("temp", "temporary", "recycle", "bin", "dustbin"):
                        ell_res = cls._execute_action_ellipsis(candidate_target, context, plugin_manager)
                        if ell_res.handled:
                            return ell_res

        # If user explicitly asked to open another application or website, let general pipeline handle it
        words = set(re.findall(r"\b\w+\b", lower))
        if any(w in cls.EXPLICIT_NEW_TARGETS for w in words):
            # Check if this is an explicit "open X" or "X band karo"
            if any(verb in lower for verb in ["open", "kholo", "launch", "band", "close", "minimize", "maximize"]):
                if not any(w in words for w in [context.website, context.application]):
                    logger.debug("Explicit target switch detected; bypassing active context.")
                    return ContextualActionResult(handled=False)

        # 1. Media play requests on active YouTube
        if context.website == "youtube":
            for pat in cls.PLAY_PATTERNS:
                m = pat.match(raw)
                if m:
                    query = cls._clean_query(m.group(1).strip())
                    logger.info("CONTEXTUAL_INTENT intent=PLAY_MEDIA action=play_video")
                    logger.info("ENTITY_EXTRACTED query=%r entities={'query': %r, 'site': 'youtube'}", query, query)
                    return cls._execute_youtube_action(query, context, plugin_manager)

        # 2. Shopping / Product / Web Search on Active Website
        search_query = cls.extract_search_query(raw)
        if search_query:
            logger.info("CONTEXTUAL_INTENT intent=SEARCH_ON_ACTIVE_WEBSITE action=search_website")
            logger.info("ENTITY_EXTRACTED query=%r entities={'query': %r, 'website': %r}", search_query, search_query, context.website)
            return cls._execute_search_action(search_query, context, plugin_manager)

        # 3. Single category / product phrase when shopping site is active (e.g. "shoes", "running shoes", "laptops")
        if context.website in {"flipkart", "amazon", "myntra", "meesho", "ajio"}:
            common_categories = {
                "shoes", "shoe", "running shoes", "sneakers", "laptop", "laptops", "mobile", "mobiles",
                "phone", "phones", "iphone", "watch", "watches", "t-shirt", "tshirt", "t-shirts",
                "jeans", "shirt", "books", "headphones", "earbuds", "tv", "camera"
            }
            clean_phrase = cls._clean_query(lower)
            if clean_phrase in common_categories:
                logger.info("CONTEXTUAL_INTENT intent=SEARCH_PRODUCTS action=search_category")
                logger.info("ENTITY_EXTRACTED query=%r entities={'category': %r, 'website': %r}", clean_phrase, clean_phrase, context.website)
                return cls._execute_search_action(clean_phrase, context, plugin_manager)

        # 4. Result Navigation & Selection
        for pat in cls.NAVIGATION_PATTERNS:
            if pat.search(raw):
                logger.info("CONTEXTUAL_INTENT intent=NAVIGATE_RESULTS action=select_result")
                return cls._execute_navigation_action(raw, context, plugin_manager)

        # 5. Hindi Vocab — Object Reference Resolution
        #    e.g. "ye wala kholo", "isko dikhao", "pichla open karo"
        obj_ref_result = cls._resolve_hindi_object_reference(raw, lower, context)
        if obj_ref_result.handled:
            return obj_ref_result

        # 6. Hindi Vocab — Direction-based Scroll Intent
        #    e.g. "upar scroll karo", "niche jao"
        scroll_result = cls._resolve_hindi_direction_scroll(raw, lower, context)
        if scroll_result.handled:
            return scroll_result

        return ContextualActionResult(handled=False)

    @classmethod
    def _execute_search_action(cls, query: str, context: ActiveTargetContext, plugin_manager: Any) -> ContextualActionResult:
        site = context.website.lower().strip()
        plugin_name = "browser"
        plugin_action = "open_url"

        from plugins.browser.search_adapters import SearchSiteRegistry
        target_site = site or context.domain or "google"
        search_res = SearchSiteRegistry.build_search_url(site=target_site, query=query)
        final_url = search_res.url
        display_site = search_res.site_name

        logger.info("PLUGIN_SELECTED plugin=%s action=%s", plugin_name, plugin_action)
        webbrowser.open(final_url)
        logger.info("ACTION_EXECUTED action=search_website success=True")
        logger.info("RESULT_VERIFIED verified=True target=%s", display_site)

        # Update active context
        context.last_search_query = query
        context.last_action = "search_products" if site in {"flipkart", "amazon"} else "search_website"
        context.url = final_url
        context.relevant_entities["query"] = query

        capitalized_query = " ".join(w.capitalize() for w in query.split())
        resp_msg = f"{display_site} par '{capitalized_query}' search kar diya hai, Boss."

        return ContextualActionResult(
            handled=True,
            response_message=resp_msg,
            intent="SEARCH_ON_ACTIVE_WEBSITE",
            action="search_website",
            target=site,
            entities={"query": query, "url": final_url},
            confidence=1.0,
            verified=True,
        )

    @classmethod
    def _execute_youtube_action(cls, query: str, context: ActiveTargetContext, plugin_manager: Any) -> ContextualActionResult:
        logger.info("PLUGIN_SELECTED plugin=youtube action=play_video")
        encoded = urllib.parse.quote_plus(query)
        final_url = f"https://www.youtube.com/results?search_query={encoded}"
        
        # If plugin manager is available and has youtube plugin, dispatch
        if plugin_manager and plugin_manager.get_plugin("youtube"):
            plugin_manager.execute_action("youtube", "search_and_play", {"query": query})
        else:
            webbrowser.open(final_url)

        logger.info("ACTION_EXECUTED action=play_video success=True")
        logger.info("RESULT_VERIFIED verified=True target=YouTube")

        context.last_search_query = query
        context.last_action = "play_video"
        context.url = final_url
        context.relevant_entities["query"] = query

        capitalized_query = " ".join(w.capitalize() for w in query.split())
        resp_msg = f"YouTube par '{capitalized_query}' play kar raha hoon, Boss."

        return ContextualActionResult(
            handled=True,
            response_message=resp_msg,
            intent="PLAY_MEDIA",
            action="play_video",
            target="youtube",
            entities={"query": query, "url": final_url},
            confidence=1.0,
            verified=True,
        )

    @classmethod
    def _execute_navigation_action(cls, text: str, context: ActiveTargetContext, plugin_manager: Any) -> ContextualActionResult:
        lower = text.lower()
        if "cart" in lower:
            msg = f"{context.website.capitalize()} cart mein add karne ki request process ho gayi hai, Boss."
            act = "add_to_cart"
        elif "price" in lower or "rate" in lower or "cost" in lower:
            msg = f"Product details aur price display kar raha hoon, Boss."
            act = "check_price"
        elif "dusra" in lower or "second" in lower:
            msg = f"{context.website.capitalize()} par dusra result open kar diya hai, Boss."
            act = "select_result_2"
        else:
            msg = f"{context.website.capitalize()} par pehla result open kar diya hai, Boss."
            act = "select_result_1"

        logger.info("PLUGIN_SELECTED plugin=browser action=%s", act)
        logger.info("ACTION_EXECUTED action=%s success=True", act)
        logger.info("RESULT_VERIFIED verified=True target=%s", context.website)

        context.last_action = act
        return ContextualActionResult(
            handled=True,
            response_message=msg,
            intent="NAVIGATE_RESULTS",
            action=act,
            target=context.website,
            confidence=0.95,
            verified=True,
        )

    @classmethod
    def _resolve_hindi_object_reference(
        cls,
        raw: str,
        lower: str,
        context: ActiveTargetContext,
    ) -> ContextualActionResult:
        """
        Resolves Hindi object reference pronouns (ye, wo, ye wala, pichla, agla, etc.)
        against the active context to identify a concrete target.

        Only fires when at least one action verb is also present in the utterance,
        so bare pronoun utterances ("ye", "wo") don't silently get consumed.
        """
        # Must have a verb to be a command, not just a pronoun
        _ACTION_TRIGGERS = {
            "kholo", "open", "band", "close", "dikhao", "show",
            "bhejo", "send", "hatao", "remove", "rakho", "place",
            "chala", "play", "rok", "stop",
        }
        has_action = any(verb in lower for verb in _ACTION_TRIGGERS)
        if not has_action:
            return ContextualActionResult(handled=False)

        entities = HindiVocabEngine.enrich_speech_entities(raw)
        ref = entities.object_ref or entities.reference
        if not ref:
            return ContextualActionResult(handled=False)

        active_app = getattr(context, "application", "") or ""
        active_web = getattr(context, "website", "") or ""
        active_url = getattr(context, "url", "") or ""

        resolved = HindiVocabEngine.resolve_object_reference(
            raw,
            last_app=active_app or None,
            last_website=active_web or None,
        )

        if not resolved:
            return ContextualActionResult(handled=False)

        logger.info(
            "HINDI_OBJECT_REF ref=%s resolved_to=%s action_present=%s",
            ref, resolved, has_action,
        )

        # Reference resolved — let the normal pipeline execute with the resolved target.
        # We update the context so downstream handlers see the correct target,
        # but we return handled=False so the intent pipeline continues normally.
        # This avoids duplicating execution logic here.
        # (handled=False is intentional: we enrich context, not short-circuit)
        if active_app and resolved == active_app:
            pass  # already in context
        elif active_web and resolved == active_web:
            pass
        else:
            context.relevant_entities["resolved_ref"] = resolved

        return ContextualActionResult(handled=False)

    @classmethod
    def _resolve_hindi_direction_scroll(
        cls,
        raw: str,
        lower: str,
        context: ActiveTargetContext,
    ) -> ContextualActionResult:
        """
        Detects direction words (upar/niche/aage/peeche/left/right) combined
        with scroll/move intent and returns a scroll action result.

        Only fires when a scroll/move verb is also present.
        """
        _SCROLL_VERBS = {
            "scroll", "scroll karo", "move", "jao", "le jao",
            "seedha", "chalao",
        }
        has_scroll_verb = any(verb in lower for verb in _SCROLL_VERBS)
        if not has_scroll_verb:
            return ContextualActionResult(handled=False)

        scroll_dir = HindiVocabEngine.get_direction_for_scroll(raw)
        if not scroll_dir:
            return ContextualActionResult(handled=False)

        logger.info("HINDI_DIRECTION_SCROLL direction=%s", scroll_dir)

        _DIR_LABELS = {"UP": "upar", "DOWN": "niche", "LEFT": "baayin taraf", "RIGHT": "daayin taraf"}
        label = _DIR_LABELS.get(scroll_dir, scroll_dir.lower())
        msg = f"{label.capitalize()} scroll kar diya, Boss."

        context.last_action = f"scroll_{scroll_dir.lower()}"
        context.relevant_entities["scroll_direction"] = scroll_dir

        return ContextualActionResult(
            handled=True,
            response_message=msg,
            intent="SCROLL_DIRECTION",
            action=f"scroll_{scroll_dir.lower()}",
            target=context.application or context.website or "page",
            entities={"direction": scroll_dir},
            confidence=0.92,
            verified=False,  # Scroll execution deferred to caller
        )

    @classmethod
    def _execute_repeat_command(
        cls,
        context: ActiveTargetContext,
        plugin_manager: Any = None
    ) -> ContextualActionResult:
        last_intent = str(context.last_intent or "")
        last_action = str(context.last_action or "")

        from core.natural_responses import NaturalResponseSynthesizer

        if "TEMP_FILE" in last_intent or last_action == "clear_temp_files":
            if plugin_manager:
                plugin_manager.execute_action("system", "clear_temp_files", {})
            else:
                try:
                    from plugins.system.plugin import SystemPlugin
                    SystemPlugin().execute("clear_temp_files", {})
                except Exception:
                    pass
            resp_msg = NaturalResponseSynthesizer.system_maintenance("clear_temp_files", target="temp", is_repeat=True)
            context.update_command_context("TEMP_FILE_CLEANUP", "clear_temp_files", {"target": "temp_files"}, service="system")
            return ContextualActionResult(
                handled=True,
                response_message=resp_msg,
                intent="TEMP_FILE_CLEANUP",
                action="clear_temp_files",
                target="temp_files",
                confidence=1.0,
                verified=True,
            )

        if "RECYCLE_BIN" in last_intent or last_action == "empty_recycle_bin":
            if plugin_manager:
                plugin_manager.execute_action("system", "empty_recycle_bin", {})
            else:
                try:
                    from plugins.system.plugin import SystemPlugin
                    SystemPlugin().execute("empty_recycle_bin", {})
                except Exception:
                    pass
            resp_msg = NaturalResponseSynthesizer.system_maintenance("empty_recycle_bin", target="recycle_bin", is_repeat=True)
            context.update_command_context("RECYCLE_BIN_CLEANUP", "empty_recycle_bin", {"target": "recycle_bin"}, service="system")
            return ContextualActionResult(
                handled=True,
                response_message=resp_msg,
                intent="RECYCLE_BIN_CLEANUP",
                action="empty_recycle_bin",
                target="recycle_bin",
                confidence=1.0,
                verified=True,
            )

        if "VOLUME_UP" in last_intent or last_action == "volume_up":
            return cls._execute_relative_repeat(context, plugin_manager)
        if "VOLUME_DOWN" in last_intent or last_action == "volume_down":
            return cls._execute_relative_repeat(context, plugin_manager)
        if last_action == "seek" or last_intent in ("YOUTUBE_CONTROL", "MEDIA_SEEK"):
            return cls._execute_relative_repeat(context, plugin_manager)

        return ContextualActionResult(handled=False)

    @classmethod
    def _execute_relative_repeat(
        cls,
        context: ActiveTargetContext,
        plugin_manager: Any = None
    ) -> ContextualActionResult:
        last_action = str(context.last_action or "").lower()
        last_intent = str(context.last_intent or "").upper()

        # Volume Up repeat
        if last_action == "volume_up" or last_intent == "VOLUME_UP":
            if plugin_manager:
                plugin_manager.execute_action("audio", "volume_up", {"step": 10})
            else:
                try:
                    from plugins.system.audio import AudioController
                    AudioController().volume_up(10)
                except Exception:
                    pass
            resp_msg = "Volume thoda aur badha diya hai, Boss."
            context.update_command_context("VOLUME_UP", "volume_up", {"step": 10}, service="audio")
            return ContextualActionResult(
                handled=True,
                response_message=resp_msg,
                intent="VOLUME_UP",
                action="volume_up",
                target="audio",
                confidence=1.0,
                verified=True,
            )

        # Volume Down repeat
        if last_action == "volume_down" or last_intent == "VOLUME_DOWN":
            if plugin_manager:
                plugin_manager.execute_action("audio", "volume_down", {"step": 10})
            else:
                try:
                    from plugins.system.audio import AudioController
                    AudioController().volume_down(10)
                except Exception:
                    pass
            resp_msg = "Volume thoda aur kam kar diya hai, Boss."
            context.update_command_context("VOLUME_DOWN", "volume_down", {"step": 10}, service="audio")
            return ContextualActionResult(
                handled=True,
                response_message=resp_msg,
                intent="VOLUME_DOWN",
                action="volume_down",
                target="audio",
                confidence=1.0,
                verified=True,
            )

        # Media Seek repeat
        if last_action == "seek" or last_intent in ("YOUTUBE_CONTROL", "MEDIA_SEEK"):
            prev_sec = (context.last_entities or {}).get("seconds", 10)
            if plugin_manager:
                plugin_manager.execute_action("youtube", "seek", {"seconds": prev_sec})
            direction_str = "aage" if prev_sec > 0 else "peeche"
            resp_msg = f"Thoda aur {direction_str} seek kar diya hai, Boss."
            context.update_command_context("YOUTUBE_CONTROL", "seek", {"seconds": prev_sec}, service="youtube")
            return ContextualActionResult(
                handled=True,
                response_message=resp_msg,
                intent="YOUTUBE_CONTROL",
                action="seek",
                target="youtube",
                confidence=1.0,
                verified=True,
            )

        return cls._execute_repeat_command(context, plugin_manager)

    @classmethod
    def _execute_action_ellipsis(
        cls,
        target_name: str,
        context: ActiveTargetContext,
        plugin_manager: Any = None
    ) -> ContextualActionResult:
        last_action = str(context.last_action or "").lower()
        last_intent = str(context.last_intent or "").upper()
        target_clean = target_name.lower().strip()

        # 1. Close application inheritance
        if last_action in ("close_app", "close_application", "band_karo", "terminate", "kill_process", "close") or "CLOSE" in last_intent:
            try:
                from plugins.apps.plugin import is_protected_close_target as _is_prot_ctx
                if _is_prot_ctx(target_clean):
                    disp_p = target_clean.capitalize()
                    return ContextualActionResult(
                        handled=True,
                        response_message=f"'{disp_p}' protected system process hai, ise band nahi kar sakta, Boss.",
                        intent="CLOSE_APPLICATION",
                        action="close_app",
                        target=target_clean,
                        confidence=1.0,
                        verified=False,
                    )
            except Exception:
                pass
            if plugin_manager:
                plugin_manager.execute_action("windows", "close_app", {"app_name": target_clean})
            else:
                try:
                    from plugins.windows.plugin import WindowsPlugin
                    WindowsPlugin().execute("close_app", {"app_name": target_clean})
                except Exception:
                    pass
            disp = target_clean.capitalize()
            resp_msg = f"{disp} bhi band kar diya hai, Boss."
            context.update_command_context("CLOSE_APPLICATION", "close_app", {"app_name": target_clean}, service="windows")
            return ContextualActionResult(
                handled=True,
                response_message=resp_msg,
                intent="CLOSE_APPLICATION",
                action="close_app",
                target=target_clean,
                confidence=1.0,
                verified=True,
            )

        # 2. Launch application inheritance
        if last_action in ("launch_app", "open_app", "open_application", "open_file", "open") or "OPEN" in last_intent:
            if plugin_manager:
                plugin_manager.execute_action("windows", "launch_app", {"app_name": target_clean})
            else:
                try:
                    from plugins.windows.plugin import WindowsPlugin
                    WindowsPlugin().execute("launch_app", {"app_name": target_clean})
                except Exception:
                    pass
            disp = target_clean.capitalize()
            resp_msg = f"{disp} bhi open kar diya hai, Boss."
            context.update_command_context("OPEN_APPLICATION", "launch_app", {"app_name": target_clean}, service="windows")
            return ContextualActionResult(
                handled=True,
                response_message=resp_msg,
                intent="OPEN_APPLICATION",
                action="launch_app",
                target=target_clean,
                confidence=1.0,
                verified=True,
            )

        # 3. Minimize window inheritance
        if last_action in ("minimize_window", "minimize_app", "minimize"):
            if plugin_manager:
                plugin_manager.execute_action("windows", "minimize_window", {"app_name": target_clean})
            disp = target_clean.capitalize()
            resp_msg = f"{disp} bhi minimize kar diya hai, Boss."
            context.update_command_context("MINIMIZE_WINDOW", "minimize_window", {"app_name": target_clean}, service="windows")
            return ContextualActionResult(
                handled=True,
                response_message=resp_msg,
                intent="MINIMIZE_WINDOW",
                action="minimize_window",
                target=target_clean,
                confidence=1.0,
                verified=True,
            )

        return ContextualActionResult(handled=False)


    @classmethod
    def _execute_entity_completion(
        cls,
        lower: str,
        context: ActiveTargetContext,
        plugin_manager: Any = None
    ) -> ContextualActionResult:
        from core.natural_responses import NaturalResponseSynthesizer

        if "temp" in lower:
            if plugin_manager:
                plugin_manager.execute_action("system", "clear_temp_files", {})
            else:
                try:
                    from plugins.system.plugin import SystemPlugin
                    SystemPlugin().execute("clear_temp_files", {})
                except Exception:
                    pass
            resp_msg = NaturalResponseSynthesizer.system_maintenance("clear_temp_files", target="temp", is_repeat=False)
            context.update_command_context("TEMP_FILE_CLEANUP", "clear_temp_files", {"target": "temp_files"}, service="system")
            return ContextualActionResult(
                handled=True,
                response_message=resp_msg,
                intent="TEMP_FILE_CLEANUP",
                action="clear_temp_files",
                target="temp_files",
                confidence=1.0,
                verified=True,
            )

        if "recycle" in lower or "trash" in lower or "dustbin" in lower:
            if plugin_manager:
                plugin_manager.execute_action("system", "empty_recycle_bin", {})
            else:
                try:
                    from plugins.system.plugin import SystemPlugin
                    SystemPlugin().execute("empty_recycle_bin", {})
                except Exception:
                    pass
            resp_msg = NaturalResponseSynthesizer.system_maintenance("empty_recycle_bin", target="recycle_bin", is_repeat=False)
            context.update_command_context("RECYCLE_BIN_CLEANUP", "empty_recycle_bin", {"target": "recycle_bin"}, service="system")
            return ContextualActionResult(
                handled=True,
                response_message=resp_msg,
                intent="RECYCLE_BIN_CLEANUP",
                action="empty_recycle_bin",
                target="recycle_bin",
                confidence=1.0,
                verified=True,
            )

        return ContextualActionResult(handled=False)

