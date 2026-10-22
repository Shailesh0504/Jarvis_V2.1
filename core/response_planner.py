# core/response_planner.py
"""
Context-Aware Response Planner for Jarvis V2.1.

Determines:
1. Interaction Category (Greeting, Small-Talk, Thanks, Ack, Command, Visual, Failure, etc.)
2. Strategic Delivery Mode (Direct concise, Direct with detail, Acknowledge first, Explain, Chat)
3. Conversational Language & Continuity (Hinglish, English, Hindi)
4. Time-of-Day Context (Morning, Afternoon, Evening, Night)
5. Structured Execution Awareness (Success, Failure, Verified, Found state)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.core.response_planner")


class ResponseCategory(str, Enum):
    """Authoritative response categories."""
    GREETING = "GREETING"
    GREETING_TIME_AWARE = "GREETING_TIME_AWARE"
    SMALL_TALK = "SMALL_TALK"
    THANKS = "THANKS"
    ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"
    QUESTION_ANSWER = "QUESTION_ANSWER"
    COMMAND_SUCCESS = "COMMAND_SUCCESS"
    COMMAND_FAILURE = "COMMAND_FAILURE"
    TARGET_FOUND = "TARGET_FOUND"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    CLICK_SUCCESS = "CLICK_SUCCESS"
    CLICK_FAILURE = "CLICK_FAILURE"
    WINDOW_FOCUS = "WINDOW_FOCUS"
    BROWSER_TAB_ACTION = "BROWSER_TAB_ACTION"
    VISUAL_FIND = "VISUAL_FIND"
    VISUAL_CLICK = "VISUAL_CLICK"
    CLARIFICATION = "CLARIFICATION"
    RECOVERY = "RECOVERY"
    UNKNOWN = "UNKNOWN"
    GOODBYE = "GOODBYE"
    CONVERSATION_STATE = "CONVERSATION_STATE"


class DeliveryMode(str, Enum):
    """Response delivery length and style."""
    DIRECT_CONCISE = "direct_concise"       # E.g. "Theek hai.", "Chrome khol diya, Sir."
    DIRECT_WITH_DETAIL = "direct_with_detail" # E.g. "Sir, YouTube Chrome mein open hai. Focus mein la diya."
    ACKNOWLEDGE_AND_ACT = "acknowledge_and_act" # E.g. "Mil gaya. Maine mouse pehle wale par le gaya hai."
    EXPLAIN_DIAGNOSTIC = "explain_diagnostic"  # E.g. "Sir, window band nahi ho payi."
    NATURAL_CHAT = "natural_chat"             # Conversational small-talk


@dataclass
class ResponseContext:
    """Complete situational context for generating user-facing feedback."""
    user_text: str = ""
    previous_user_text: Optional[str] = None
    previous_response: Optional[str] = None
    intent: str = ""
    speech_act: str = ""
    target: str = ""
    action_performed: str = ""
    action_status: str = "success"        # success, failure, partial, none
    verification_status: str = "verified" # verified, unverified, failed
    found: Optional[bool] = None
    match_count: int = 1
    mouse_moved: bool = False
    focused_app: str = ""
    active_tab: str = ""
    language: str = "hinglish"            # hinglish, hindi, english
    time_of_day: str = ""                 # morning, afternoon, evening, night
    is_follow_up: bool = False
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannedResponse:
    """Strategic plan formulated by the ResponsePlanner."""
    category: ResponseCategory
    delivery_mode: DeliveryMode
    language: str
    time_of_day: str
    target_clean: str
    allow_sir: bool = True
    prefix_ack: Optional[str] = None
    detail_requested: bool = False


class ResponsePlanner:
    """Plans response category, delivery mode, language, and acknowledgements."""

    GREETINGS_TIME_PATTERNS = {
        "morning": re.compile(r"\b(good\s+morning|gud\s+morning|good\s+moring|gud\s+moring|good\s+mornig|good\s+mornin|good\s+mrng|gud\s+mrng|gm|morning|shubh\s+prabhat|suprabhat|subah\s+bakhair)\b", re.IGNORECASE),
        "afternoon": re.compile(r"\b(good\s+afternoon|gud\s+afternoon|afternoon|shubh\s+dopahar)\b", re.IGNORECASE),
        "evening": re.compile(r"\b(good\s+evening|gud\s+evening|evening|shubh\s+sandhya)\b", re.IGNORECASE),
        "night": re.compile(r"\b(good\s+night|gud\s+night|gn|shubh\s+ratri)\b", re.IGNORECASE),
    }

    GENERIC_GREETINGS = re.compile(r"^(hi|hello|hey|helo|hallo|helllo|hii+|hie|namaste|pranam|namaskar|hola|yo)\b", re.IGNORECASE)
    THANKS_PATTERNS = re.compile(r"\b(thanks|thank\s+you|shukriya|dhanyawad|thx)\b", re.IGNORECASE)
    ACKS_PATTERNS = re.compile(r"^(okay|ok|theek\s+hai|thik\s+hai|achha|achha\s+theek\s+hai|got\s+it|great|nice|perfect|bilkul|sahi\s+hai|chalo\s+theek\s+hai)\b", re.IGNORECASE)
    HOW_ARE_YOU_PATTERNS = re.compile(r"\b(kaise\s+ho|kya\s+haal|how\s+are\s+you|kaisa\s+chal\s+raha|sab\s+theek)\b", re.IGNORECASE)
    GOODBYE_PATTERNS = re.compile(r"\b(bye|goodbye|alvida|see\s+you|exit|quit)\b", re.IGNORECASE)

    @classmethod
    def get_current_time_of_day(cls) -> str:
        """Determines the current day part from local clock."""
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 22:
            return "evening"
        else:
            return "night"

    @classmethod
    def detect_language(cls, text: str, previous_lang: str = "hinglish") -> str:
        """
        Detects language from user text while honoring continuity for short acknowledgements.
        """
        if not text or not text.strip():
            return previous_lang or "hinglish"

        # Check for Devanagari script
        if re.search(r"[\u0900-\u097F]", text):
            return "hindi"

        lower = text.lower().strip()

        # Pure English markers
        english_markers = {"what", "which", "where", "how", "who", "when", "open", "close", "please", "thank", "thanks"}
        # Hinglish markers
        hinglish_markers = {
            "karo", "kholo", "chalao", "band", "batao", "dikhao", "hai", "hain", "kya",
            "ka", "ki", "ke", "ko", "se", "aur", "ye", "yeh", "woh", "usko", "isko",
            "nahi", "nahin", "haan", "dono", "sab", "yaar", "kardo", "kar", "do",
            "kaise", "kahan", "kitna", "wala", "wali", "ji", "ek", "theek", "achha"
        }

        words = set(re.findall(r"[a-z]+", lower))
        if words.intersection(hinglish_markers):
            return "hinglish"

        # If it is a very short token like "ok", "great", "thanks", maintain continuity if previous was hinglish
        if len(words) <= 2 and previous_lang == "hinglish" and not words.intersection(english_markers):
            return "hinglish"

        if words.intersection(english_markers):
            return "english"

        return previous_lang or "hinglish"

    @classmethod
    def plan(cls, ctx: ResponseContext) -> PlannedResponse:
        """Plans category and delivery parameters based on the incoming context."""
        text = (ctx.user_text or "").strip()
        lower = text.lower()
        intent_raw = ctx.intent
        if hasattr(intent_raw, "name"):
            intent = (intent_raw.name or "").upper()
        elif isinstance(intent_raw, str):
            intent = intent_raw.upper()
        else:
            intent = str(intent_raw or "").upper()
        act = (ctx.speech_act or "").upper()

        time_of_day = ctx.time_of_day or cls.get_current_time_of_day()
        language = ctx.language or cls.detect_language(text)

        # 1. Check for Goodbye / Exit
        if cls.GOODBYE_PATTERNS.search(lower) or intent in ("EXIT", "QUIT", "SHUTDOWN"):
            return PlannedResponse(
                category=ResponseCategory.GOODBYE,
                delivery_mode=DeliveryMode.DIRECT_CONCISE,
                language=language,
                time_of_day=time_of_day,
                target_clean="",
                allow_sir=True
            )

        # Guard: Utterances with query/action markers or non-greeting intents must NOT become greetings
        is_query_or_command = bool(re.search(
            r"\b(?:meaning|matlab|kya\s+hai|kya\s+hota\s+hai|what\s+(?:is|does)|explain|likho|likh\s+do|type|send|bhejo|batao|kya\s+tum|can\s+you|could\s+you|say|bolo)\b",
            lower
        ))
        is_non_greeting_intent = intent in (
            "CAPABILITY_QUESTION", "CAPABILITY_INQUIRY", "INFORMATION_QUESTION",
            "KNOWLEDGE", "ACTION_COMMAND", "STATUS_QUESTION", "TROUBLESHOOTING"
        )

        if not is_query_or_command and not is_non_greeting_intent and len(lower.split()) <= 5:
            # 2. Check for Time-Aware Greeting in user utterance or intent
            for tod, pat in cls.GREETINGS_TIME_PATTERNS.items():
                if pat.search(lower):
                    return PlannedResponse(
                        category=ResponseCategory.GREETING_TIME_AWARE,
                        delivery_mode=DeliveryMode.DIRECT_CONCISE,
                        language=language,
                        time_of_day=tod,
                        target_clean="",
                        allow_sir=True
                    )

            # 3. Check for Generic Greetings ("hi", "hello", "namaste") or GREETING intent/act
            if cls.GENERIC_GREETINGS.search(lower) or intent == "GREETING" or act == "GREETING":
                return PlannedResponse(
                    category=ResponseCategory.GREETING,
                    delivery_mode=DeliveryMode.DIRECT_CONCISE,
                    language=language,
                    time_of_day=time_of_day,
                    target_clean="",
                    allow_sir=True
                )

        # 4. Check for Thanks ("thank you", "thanks")
        if cls.THANKS_PATTERNS.search(lower) and len(lower.split()) <= 4:
            return PlannedResponse(
                category=ResponseCategory.THANKS,
                delivery_mode=DeliveryMode.DIRECT_CONCISE,
                language=language,
                time_of_day=time_of_day,
                target_clean="",
                allow_sir=True
            )

        # 5. Check for Short Acknowledgements ("okay", "achha", "theek hai").
        # Guard: "Achha weather batao" / "Theek hai, Chrome kholo" are COMMANDS with a
        # discourse lead — never ACK (which would discard the real pipeline answer).
        if cls.ACKS_PATTERNS.search(lower) and len(lower.split()) <= 3:
            _after_ack = cls.ACKS_PATTERNS.sub("", lower, count=1).strip(" ,.")
            _has_command = bool(re.search(
                r"\b(?:batao|kholo|khol|chalao|chala|open|close|band|weather|mausam|forecast|"
                r"music|gaana|gana|reminder|alarm|mail|message|bhejo|send|volume|karo|kar\s+do|"
                r"dikhao|sunao|play|lagao|kya|kaise|kab|kitna)\b",
                _after_ack or lower))
            if not _has_command:
                return PlannedResponse(
                    category=ResponseCategory.ACKNOWLEDGEMENT,
                    delivery_mode=DeliveryMode.DIRECT_CONCISE,
                    language=language,
                    time_of_day=time_of_day,
                    target_clean="",
                    allow_sir=False
                )

        # 5.5 Check for Food State / Conversational Continuation
        if any(w in lower for w in ["khana", "lunch", "dinner", "breakfast", "bhookh"]):
            return PlannedResponse(
                category=ResponseCategory.CONVERSATION_STATE,
                delivery_mode=DeliveryMode.NATURAL_CHAT,
                language=language,
                time_of_day=time_of_day,
                target_clean="",
                allow_sir=False
            )

        # 6. Check for Small Talk ("kaise ho?", "how are you?")
        if (cls.HOW_ARE_YOU_PATTERNS.search(lower) or act == "SMALL_TALK" or "kya kar rahe ho" in lower) and not any(w in lower for w in ["mic", "microphone", "headset", "earbuds", "earphone", "audio device"]):
            return PlannedResponse(
                category=ResponseCategory.SMALL_TALK,
                delivery_mode=DeliveryMode.NATURAL_CHAT,
                language=language,
                time_of_day=time_of_day,
                target_clean="",
                allow_sir=True
            )

        # 7. Check for Visual Text Actions (Find / Point / Click Text)
        if intent in ("FIND_TEXT", "POINT_TO_TEXT", "VISUAL_FIND"):
            return PlannedResponse(
                category=ResponseCategory.VISUAL_FIND,
                delivery_mode=DeliveryMode.DIRECT_WITH_DETAIL,
                language=language,
                time_of_day=time_of_day,
                target_clean=ctx.target.strip(),
                allow_sir=True
            )
        elif intent in ("CLICK_TEXT", "DOUBLE_CLICK_TEXT", "SELECT_TEXT", "VISUAL_CLICK"):
            return PlannedResponse(
                category=ResponseCategory.VISUAL_CLICK,
                delivery_mode=DeliveryMode.DIRECT_CONCISE,
                language=language,
                time_of_day=time_of_day,
                target_clean=ctx.target.strip(),
                allow_sir=True
            )

        # 8. Check for Browser / Tab queries & Focus
        if "browser" in intent.lower() or "tab" in intent.lower() or "focus" in intent.lower():
            if ctx.action_status == "failure" or ctx.found is False:
                return PlannedResponse(
                    category=ResponseCategory.TARGET_NOT_FOUND,
                    delivery_mode=DeliveryMode.DIRECT_CONCISE,
                    language=language,
                    time_of_day=time_of_day,
                    target_clean=ctx.target.strip(),
                    allow_sir=True
                )
            return PlannedResponse(
                category=ResponseCategory.BROWSER_TAB_ACTION,
                delivery_mode=DeliveryMode.DIRECT_WITH_DETAIL,
                language=language,
                time_of_day=time_of_day,
                target_clean=ctx.target.strip(),
                allow_sir=True
            )

        # 9. Execution Command Success vs Failure
        if ctx.action_status == "failure" or ctx.verification_status == "failed":
            return PlannedResponse(
                category=ResponseCategory.COMMAND_FAILURE,
                delivery_mode=DeliveryMode.EXPLAIN_DIAGNOSTIC,
                language=language,
                time_of_day=time_of_day,
                target_clean=ctx.target.strip(),
                allow_sir=True
            )

        if ctx.action_performed or intent.endswith("_COMMAND") or intent in ("OPEN_APP", "CLOSE_APP", "SYSTEM_SETTING"):
            return PlannedResponse(
                category=ResponseCategory.COMMAND_SUCCESS,
                delivery_mode=DeliveryMode.DIRECT_CONCISE,
                language=language,
                time_of_day=time_of_day,
                target_clean=ctx.target.strip(),
                allow_sir=True
            )

        # 10. Default / General Questions or Clarifications
        if act == "CLARIFICATION" or "clarif" in intent.lower():
            return PlannedResponse(
                category=ResponseCategory.CLARIFICATION,
                delivery_mode=DeliveryMode.DIRECT_CONCISE,
                language=language,
                time_of_day=time_of_day,
                target_clean=ctx.target.strip(),
                allow_sir=True
            )

        return PlannedResponse(
            category=ResponseCategory.QUESTION_ANSWER,
            delivery_mode=DeliveryMode.DIRECT_CONCISE,
            language=language,
            time_of_day=time_of_day,
            target_clean=ctx.target.strip(),
            allow_sir=True
        )
