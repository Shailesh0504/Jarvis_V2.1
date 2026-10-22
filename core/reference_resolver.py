# core/reference_resolver.py
"""
Deictic Reference Resolution Engine for Jarvis V2.
Resolves ambiguous pronouns and markers:
'ye', 'yeh', 'is', 'ise', 'isko', 'isse', 'woh', 'usko', 'usse',
'ye wala', 'wahi', 'same', 'ab', 'phir', 'fir', 'dobara', 'doosra', 'pehla', 'usi', 'iska', 'ismein'
across conversation history, active desktop/browser target, and visual screen targets.
"""

from dataclasses import dataclass
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from core.visual_reference import VisualReferenceManager, VisualSearchSession
from core.context import ActiveTargetContext
from core.conversation_state import ConversationState

logger = logging.getLogger("jarvis.core.reference_resolver")


class ReferenceTargetType(str, Enum):
    VISUAL_MATCH = "VISUAL_MATCH"
    ORDINAL_SELECTION = "ORDINAL_SELECTION"
    ACTIVE_TAB = "ACTIVE_TAB"
    ACTIVE_BROWSER = "ACTIVE_BROWSER"
    ACTIVE_APPLICATION = "ACTIVE_APPLICATION"
    THREAD_ENTITY = "THREAD_ENTITY"
    NONE = "NONE"


@dataclass
class ResolvedReference:
    target_type: ReferenceTargetType
    action: str  # "click", "close", "inspect_browser", "open", "select_ordinal", "none"
    target_value: Any = None
    target_name: str = ""
    container: str = ""
    ordinal_index: Optional[int] = None
    resolved: bool = False
    confidence: float = 0.90
    explanation: str = ""


class ReferenceResolver:
    """Authoritative multi-source deictic reference resolution engine."""

    # Ordinals
    ORDINAL_MAP = {
        "pehla": 0, "pehle": 0, "pehli": 0, "first": 0, "1st": 0, "ek": 0, "pehla wala": 0, "upar wala": 0, "top": 0,
        "doosra": 1, "doosre": 1, "doosri": 1, "dusra": 1, "dusre": 1, "second": 1, "2nd": 1, "do": 1, "doosra wala": 1,
        "teesra": 2, "teesre": 2, "teesri": 2, "tisra": 2, "third": 2, "3rd": 2, "teen": 2, "teesra wala": 2,
        "chautha": 3, "chauthe": 3, "fourth": 3, "4th": 3, "chaar": 3, "chautha wala": 3,
        "paanchva": 4, "paanchve": 4, "fifth": 4, "5th": 4, "paanch": 4,
        "aakhiri": -1, "antim": -1, "last": -1, "last wala": -1, "neeche wala": -1, "bottom": -1,
    }

    # Reference indicators
    PRONOUNS_RE = re.compile(
        r"\b(?:ye|yeh|is|ise|isko|isse|ispe|ispar|us|use|usko|usko\s+hi|usse|uspe|uspar|ye\s+wala|woh|wahi|same|aisi|usi|iska|ismein|isme|usme|yahan|wahan|jo\s+abhi\s+khula\s+tha|jo\s+maine\s+pehle\s+bola\s+tha|last\s+wala|upar\s+wala|neeche\s+wala)\b",
        re.IGNORECASE
    )

    @classmethod
    def has_reference(cls, text: str) -> bool:
        """Returns True if the utterance contains deictic pronouns or reference words."""
        t = text.lower()
        if cls.PRONOUNS_RE.search(t):
            return True
        if any(w in t for w in ["doosra", "doosre", "pehla", "pehle", "teesra", "aakhiri", "wahi", "upar", "neeche", "last"]):
            return True
        return False

    @classmethod
    def resolve(
        cls,
        text: str,
        active_context: Optional[ActiveTargetContext] = None,
        visual_manager: Optional[VisualReferenceManager] = None,
        conversation_state: Optional[ConversationState] = None
    ) -> ResolvedReference:
        """
        Resolves reference in text against Visual Memory, Active Target, and Conversation Threads.
        """
        raw = text.strip()
        low = raw.lower()

        vis_mgr = visual_manager or VisualReferenceManager()
        last_search = vis_mgr.get_last_search()

        # 1. Inquiries about browser/container
        # Matches: "ye kaun se browser mein hai?", "konse browser me hai?",
        #          "youtube kahan open hai?", "kis browser mein open hai?", "kidhar open hai?"
        BROWSER_LOCATION_WORDS = (
            "kaun se browser", "kaun si browser", "kaunse browser", "kaunsi browser",
            "konse browser", "konsi browser", "kis browser", "which browser",
            "kahan open hai", "kahan hai", "kidhar open hai", "kidhar hai",
            "kahan khula hai", "kahan chal raha hai",
        )
        if any(w in low for w in BROWSER_LOCATION_WORDS):
            browser = getattr(active_context, "browser", "") or getattr(active_context, "application", "") or "Chrome"
            # Prefer website from context; fall back to extracting it from the query
            website = getattr(active_context, "website", "") or getattr(active_context, "last_entity", "")
            if not website:
                # Extract first word before the location phrase as the website name
                import re as _re
                m_site = _re.match(r"^([a-z0-9]+(?:\.[a-z]+)?)\s+", low)
                website = m_site.group(1).strip() if m_site else "Website"
            website_display = website.capitalize()
            browser_display = browser.capitalize()
            return ResolvedReference(
                target_type=ReferenceTargetType.ACTIVE_BROWSER,
                action="inspect_browser",
                target_name=website_display,
                container=browser_display,
                resolved=True,
                confidence=0.98,
                explanation=f"{website_display} {browser_display} mein open hai."
            )

        # 2. Ordinal selection in visual search ("doosre wale pe jao", "ye doosra wala hai", "pehle wale pe jao")
        ordinal_idx = cls._extract_ordinal(low)
        if ordinal_idx is not None and ("wale" in low or "wala" in low or "pe jao" in low):
            if last_search and last_search.matches:
                idx = ordinal_idx
                if idx == -1:
                    idx = len(last_search.matches) - 1
                if 0 <= idx < len(last_search.matches):
                    vis_mgr.set_selected_index(idx)
                    match_item = last_search.matches[idx]
                    return ResolvedReference(
                        target_type=ReferenceTargetType.ORDINAL_SELECTION,
                        action="select_ordinal",
                        target_value=match_item,
                        target_name=getattr(match_item, "text", "match"),
                        ordinal_index=idx,
                        resolved=True,
                        confidence=0.95,
                        explanation=f"Selected ordinal match {idx + 1} for '{getattr(match_item, 'text', '')}'"
                    )

        # 3. Action click on deictic target ("ab is par click karo", "haan, is par click karo", "ispe click karo")
        if "click" in low and cls.has_reference(low):
            # Check visual search session first
            if last_search and last_search.selected_match:
                sel = last_search.selected_match
                return ResolvedReference(
                    target_type=ReferenceTargetType.VISUAL_MATCH,
                    action="click",
                    target_value=sel,
                    target_name=getattr(sel, "text", "target"),
                    resolved=True,
                    confidence=0.96,
                    explanation=f"Click on visual target '{getattr(sel, 'text', '')}'"
                )

        # 4. Action close on deictic target or ellipsis ("ab band karo", "isko band karo", "ye tab band karo", "ise close karo")
        is_ellipsis_close = bool(re.search(r"^(?:ab\s+)?(?:band\s+karo|close|exit)$", low))
        if cls.has_reference(low) or is_ellipsis_close:
            if any(w in low for w in ["band karo", "close karo", "close", "exit", "band"]):
                tab = getattr(active_context, "tab", "")
                website = getattr(active_context, "website", "")
                app = getattr(active_context, "application", "")
                target_name = website or tab or app or "current target"
                return ResolvedReference(
                    target_type=ReferenceTargetType.ACTIVE_TAB if (website or tab) else ReferenceTargetType.ACTIVE_APPLICATION,
                    action="close",
                    target_name=target_name,
                    container=getattr(active_context, "browser", "") or app,
                    resolved=True,
                    confidence=0.94,
                    explanation=f"Close target '{target_name}'"
                )

        # 4.5. Reference to "jo abhi khula tha" / "jo maine pehle bola tha" / "wahi" / "same" / "usko hi"
        if re.search(r"\b(?:jo\s+abhi\s+khula\s+tha|jo\s+maine\s+pehle\s+bola\s+tha|wahi|same|usko\s+hi)\b", low):
            app = getattr(active_context, "application", "") or getattr(active_context, "last_entity", "") or getattr(active_context, "website", "") or "current target"
            return ResolvedReference(
                target_type=ReferenceTargetType.ACTIVE_APPLICATION,
                action="focus",
                target_name=app,
                resolved=True,
                confidence=0.95,
                explanation=f"Resolved antecedent '{app}' for '{raw}'"
            )

        # 4.6. Action focus/foreground on deictic target ("usko foreground mein lao", "isko saamne lao", "use foreground me lao", "foreground mein lao")
        FOREGROUND_WORDS = ("foreground", "saamne", "focus", "aage")
        if any(w in low for w in FOREGROUND_WORDS) and (cls.has_reference(low) or any(w in low for w in ("foreground", "saamne"))):
            app = (
                getattr(active_context, "application", "")
                or getattr(active_context, "last_entity", "")
                or getattr(active_context, "current_app", "")
                or getattr(active_context, "website", "")
                or "current target"
            )
            app_title = app.title() if app and app != "current target" else "Application"
            return ResolvedReference(
                target_type=ReferenceTargetType.ACTIVE_APPLICATION,
                action="foreground",
                target_name=app,
                container=app,
                resolved=True,
                confidence=0.96,
                explanation=f"{app_title} foreground mein le aaya."
            )

        # 5. Reference to an earlier thread entity ("ab woh YouTube wala kholo", "woh chrome wala")
        # Guard: explicit browser-container actions ("chrome wala youtube band kar do",
        # "brave me netflix band karo") own TWO entities (container + target) and must
        # fall through to the universal-target pipeline (target_engine tab close),
        # not a canned reference reply that never executes.
        try:
            from core.semantic.parsers.windows import parse_universal_target_action as _parse_uta
            if _parse_uta(raw, low) is not None:
                return ResolvedReference(
                    target_type=ReferenceTargetType.NONE,
                    action="none",
                    resolved=False,
                    confidence=0.20,
                    explanation="Explicit container action; defer to universal-target pipeline."
                )
        except Exception:
            pass
        m_thread = re.search(r"(?:ab\s+)?(?:woh\s+)?([a-zA-Z0-9_\-\.]+)\s+wala(?:\s+(?:kholo|open(?:\s+karo)?|band(?:\s+karo)?|chalao))?", low)
        if m_thread:
            entity_name = m_thread.group(1).strip()
            # Grounding guard: only resolve when the entity was actually mentioned
            # (active context slots or recent conversation). Otherwise a qualifier
            # like "Thoda slow wala" would hijack as a fake thread entity.
            _known: List[str] = []
            try:
                for _attr in ("application", "website", "browser", "last_entity", "tab"):
                    _v = getattr(active_context, _attr, "") if active_context is not None else ""
                    if _v:
                        _known.append(str(_v).lower())
                _rel = getattr(active_context, "relevant_entities", {}) if active_context is not None else {}
                if isinstance(_rel, dict):
                    _known.extend(str(v).lower() for v in _rel.values() if v)
            except Exception:
                pass
            try:
                _cs = conversation_state
                _turns = []
                if _cs is not None:
                    _turns = getattr(_cs, "history", None) or getattr(_cs, "turns", None) or []
                    if callable(_turns):
                        _turns = []
                for _t in list(_turns)[-6:]:
                    for _f in ("user_text", "raw_input", "text", "utterance"):
                        _v = getattr(_t, _f, "") if not isinstance(_t, dict) else _t.get(_f, "")
                        if _v:
                            _known.append(str(_v).lower())
            except Exception:
                pass
            _grounded = any(entity_name.lower() in k for k in _known) if _known else False
            if not _grounded:
                return ResolvedReference(
                    target_type=ReferenceTargetType.NONE,
                    action="none",
                    resolved=False,
                    confidence=0.20,
                    explanation="Thread entity not grounded in context; defer to pipeline."
                )
            act = "close" if "band" in low else "open"
            return ResolvedReference(
                target_type=ReferenceTargetType.THREAD_ENTITY,
                action=act,
                target_name=entity_name,
                resolved=True,
                confidence=0.92,
                explanation=f"Resume/Open entity '{entity_name}' from thread"
            )

        # Fallback
        return ResolvedReference(
            target_type=ReferenceTargetType.NONE,
            action="none",
            resolved=False,
            confidence=0.20,
            explanation="No clear reference target could be resolved."
        )

    @classmethod
    def _extract_ordinal(cls, text: str) -> Optional[int]:
        for word, idx in cls.ORDINAL_MAP.items():
            if re.search(rf"\b{re.escape(word)}\b", text):
                return idx
        return None
