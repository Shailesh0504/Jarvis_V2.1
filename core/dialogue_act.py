# core/dialogue_act.py
"""
Dialogue Act Classification Layer for Jarvis V2.
Classifies utterances into speech acts / dialogue acts BEFORE intent classification.
Prevents non-command conversational statements from triggering unknown command errors.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.core.dialogue_act")


class DialogueAct(str, Enum):
    GREETING = "GREETING"
    FAREWELL = "FAREWELL"
    THANKS = "THANKS"
    ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"
    CASUAL_STATEMENT = "CASUAL_STATEMENT"
    SMALL_TALK = "SMALL_TALK"
    QUESTION = "QUESTION"
    COMMAND = "COMMAND"
    REQUEST = "REQUEST"
    FOLLOW_UP = "FOLLOW_UP"
    CORRECTION = "CORRECTION"
    CLARIFICATION = "CLARIFICATION"
    OPINION = "OPINION"
    REACTION = "REACTION"
    EMOTION = "EMOTION"
    STATUS_UPDATE = "STATUS_UPDATE"
    CONTEXT_UPDATE = "CONTEXT_UPDATE"
    REFERENCE = "REFERENCE"
    JOKE = "JOKE"
    CONVERSATIONAL_CONTINUATION = "CONVERSATIONAL_CONTINUATION"
    UNKNOWN = "UNKNOWN"


@dataclass
class DialogueActResult:
    act: DialogueAct
    confidence: float = 0.90
    topic_hint: Optional[str] = None
    subtopic_hint: Optional[str] = None
    entities: Dict[str, Any] = field(default_factory=dict)
    is_executable_command: bool = False
    raw_text: str = ""
    normalized_text: str = ""
    suggested_state_update: Optional[Dict[str, Any]] = None


class DialogueActClassifier:
    """Authoritative dialogue act classification before command/intent processing."""

    # 1. Greetings
    _GREETING_PATTERNS = [
        re.compile(
            r"^(?:hi|hello|hey|helo|hallo|helllo|hii+|hie|namaste|pranam|ram\s+ram|radhe\s+radhe|salaam|salam|sat\s+sri\s+akal|shubh\s+prabhat|suprabhat|subah\s+bakhair|gm|morning|evening|afternoon|good\s+(?:morning|afternoon|evening|day)|gud\s+(?:morning|afternoon|evening|day)|good\s+(?:moring|mornig|mornin|mrng)|gud\s+(?:moring|mornig|mornin|mrng))"
            r"(?:\s+(?:jarvis|sir|boss|bhai|dost|bro|buddy|yaar|friend|dear|ji|madam|mam|to\s+you|everyone|all))?[\.!\?]?$",
            re.IGNORECASE
        ),
        re.compile(
            r"^(?:hey\s+(?:there|good\s+morning|morning|dear)|hello\s+(?:there|good\s+morning|morning|dear)|hi\s+dear|hello\s+dear|gm\s+dear|morning\s+dear|kya\s+hal\s+hai|kaise\s+ho)[\.!\?]?$",
            re.IGNORECASE
        ),
    ]

    # 2. Farewells
    _FAREWELL_PATTERNS = [
        re.compile(r"^(?:bye|goodbye|bye\s+bye|see\s+you|alvida|shubhratri|good\s+night|tata)(?:\s+(?:jarvis|sir|boss))?[\.!\?]?$", re.IGNORECASE),
    ]

    # 3. Thanks
    _THANKS_PATTERNS = [
        re.compile(r"^(?:thanks|thank\s+you|shukriya|dhanyawad|bahut\s+shukriya|thank\s+u|many\s+thanks)(?:\s+(?:jarvis|sir|boss))?[\.!\?]?$", re.IGNORECASE),
    ]

    # 4. Acknowledgements / Conversational Fillers
    _ACK_PATTERNS = [
        re.compile(r"^(?:achha(?:\s+hai)?|theek\s+hai|thik\s+hai|sahi\s+hai|badhiya|haan(?:\s+(?:yehi|yahi|wahi|sahi))?|ha|yes(?:\s+(?:this|that))?|yep|yeah|hmm|hmmm|ok|okay|k|accha|chalo|done|samajh\s+gaya|wow|great|awesome|nice)[\.!\?]?$", re.IGNORECASE),
    ]

    # 4.5. User Wellbeing / Greeting Responses ("main achha hun", "theek hun", "badhiya", "sab sahi hai", "mast", "i am good", "fine")
    _WELLBEING_PATTERNS = [
        re.compile(r"^(?:main\s+)?(?:achha|accha|theek|thik|badhiya|badiya|mast|sahi|fine|good|well)\s+(?:hun|hoon|hu|h)[\.!\?]?$", re.IGNORECASE),
        re.compile(r"^(?:main\s+)?(?:ekdam\s+|bilkul\s+)?(?:achha|accha|theek|thik|badhiya|badiya|mast|fine|good|fit|changa)[\.!\?]?$", re.IGNORECASE),
        re.compile(r"^(?:sab\s+)?(?:theek|thik|badhiya|badiya|mast|sahi|all\s+good|all\s+set|all\s+well)(?:\s+hai)?[\.!\?]?$", re.IGNORECASE),
        re.compile(r"^(?:i'?m|i\s+am)\s+(?:good|fine|doing\s+well|doing\s+good|great|okay|alright)[\.!\?]?$", re.IGNORECASE),
        re.compile(r"(?:main\s+)?(?:achha|accha|theek|thik|badhiya|mast)\s+(?:hun|hoon|hu|h)[,\s]+(?:tum|aap)\s+(?:batao|sunao|bataiye)", re.IGNORECASE),
        re.compile(r"(?:i'?m|i\s+am)\s+(?:good|fine)[,\s]+(?:how\s+are\s+you|and\s+you|what\s+about\s+you)", re.IGNORECASE),
    ]

    # 4.6. Reciprocal Questions & Conversational Continuation ("tum batao", "aur batao", "kya chal raha hai")
    _RECIPROCAL_CHAT_PATTERNS = [
        re.compile(r"^(?:aur\s+)?(?:tum|aap)\s+(?:batao|sunao|bataiye)[\.!\?]?$", re.IGNORECASE),
        re.compile(r"^(?:aur\s+)?(?:tumhara|aapka)\s+din\s+kaisa\s+(?:raha|ja\s+raha\s+hai)[\.!\?]?$", re.IGNORECASE),
        re.compile(r"^(?:and\s+you|what\s+about\s+you|how\s+about\s+you)[\.!\?]?$", re.IGNORECASE),
        re.compile(r"^(?:aur\s+batao|aur\s+sunao|kya\s+chal\s+raha\s+hai|kya\s+chal\s+raha\s+h|kya\s+naya\s+hai|kya\s+ho\s+raha\s+hai)[\.!\?]?$", re.IGNORECASE),
        re.compile(r"^(?:what'?s\s+up|sup|what'?s\s+new|how'?s\s+it\s+going)[\.!\?]?$", re.IGNORECASE),
    ]

    # 4.7. Neutral / Idle / Boredom ("kuch khas nahi", "bas aise hi", "bore ho raha hoon")
    _IDLE_OR_BORED_PATTERNS = [
        re.compile(r"^(?:kuch\s+khas\s+nahi|kuch\s+nahi|bas\s+aise\s+hi|nothing\s+much|not\s+much|just\s+chilling)[\.!\?]?$", re.IGNORECASE),
        re.compile(r"^(?:theek\s+thaak|so\s+so|chal\s+raha\s+hai|bas\s+kat\s+rahi\s+hai)[\.!\?]?$", re.IGNORECASE),
        re.compile(r"^(?:main\s+)?(?:bore\s+ho\s+raha\s+hoon|boring\s+lag\s+raha\s+hai|i'?m\s+bored|kuch\s+interesting\s+batao)[\.!\?]?$", re.IGNORECASE),
    ]

    # 5. Small Talk
    _SMALL_TALK_PATTERNS = [
        re.compile(r"(?:tum|aap)\s+(?:kya\s+kar\s+rahe\s+ho|kaise\s+ho|kya\s+hal\s+hai)", re.IGNORECASE),
        re.compile(r"^what\s+(?:are\s+you\s+doing|is\s+up|sup)\b", re.IGNORECASE),
        re.compile(r"^(?:aur\s+batao|kya\s+chal\s+raha\s+hai|kya\s+ho\s+raha\s+hai)[\.!\?]?$", re.IGNORECASE),
        re.compile(r"(?:who\s+are\s+you|tum\s+kaun\s+ho)", re.IGNORECASE),
    ]

    # 6. Casual Food Statements
    _FOOD_NOT_EATEN_PATTERNS = [
        re.compile(r"(?:abhi\s+tak\s+(?:khana|lunch|dinner|breakfast|food)\s+nahi\s+khaya|khana\s+nahi\s+khaya|lunch\s+nahi\s+kiya|kuch\s+nahi\s+khaya|bhookh\s+lagi\s+hai|haven'?t\s+eaten)", re.IGNORECASE),
    ]

    # 7. Food State Updates (Continuation / Resumption)
    _FOOD_EATEN_PATTERNS = [
        re.compile(r"(?:main\s+)?(?:kha\s+ke\s+aa(?:ya|yi|gaya)|khana\s+kha\s+liya|lunch\s+ho\s+gaya|pet\s+bhar\s+gaya|ate\s+food|done\s+with\s+lunch|lunch\s+kar\s+liya)", re.IGNORECASE),
        re.compile(r"(?:main\s+)?(?:lunch|khana|dinner)\s+karne\s+ja\s+raha\s+hoon", re.IGNORECASE),
    ]

    # 8. Casual Life Statements (Fatigue, Weather, Mood)
    _CASUAL_STATEMENT_PATTERNS = [
        re.compile(r"(?:main\s+thak\s+gaya\s+hoon|bahut\s+thaka\s+hoon|exhausted|tired)", re.IGNORECASE),
        re.compile(r"(?:aaj\s+bahut\s+garmi\s+hai|bahut\s+thand\s+hai|mausam\s+achha\s+hai|it'?s\s+hot|it'?s\s+cold)", re.IGNORECASE),
        re.compile(r"(?:bahut\s+late\s+ho\s+gaya|aaj\s+kaafi\s+busy\s+raha|busy\s+day)", re.IGNORECASE),
        re.compile(r"^(?:are\s+yaar|yaar|suno|sun|waise\s+ek\s+baat\s+batao|ek\s+baat\s+batao|kya\s+baat\s+hai)[\.!\?]?$", re.IGNORECASE),
    ]

    # 9. Movement / Presence Updates
    _PRESENCE_UPDATE_PATTERNS = [
        re.compile(r"(?:main\s+aa\s+gaya|i\s+am\s+back|main\s+ja\s+raha\s+hoon|abhi\s+aaya|be\s+right\s+back)", re.IGNORECASE),
    ]

    # 10. Visual Text Query ("Paramhans Aashram kahan likha hai?")
    _VISUAL_FIND_PATTERNS = [
        re.compile(r"^(?:(?:sir\s+)?['\"]?(.+?)['\"]?\s+kahan\s+(?:par\s+)?likha\s+hai[\?]?)$", re.IGNORECASE),
        re.compile(r"^(?:where\s+is\s+['\"]?(.+?)['\"]?\s+written[\?]?)$", re.IGNORECASE),
        re.compile(r"^find\s+text\s+['\"]?(.+?)['\"]?$", re.IGNORECASE),
    ]

    # 11. Context Inquiries / Questions about State ("ye kaun se browser mein hai?")
    _CONTEXT_INQUIRY_PATTERNS = [
        re.compile(r"(?:ye|yeh|ye\s+wala|is)\s+(?:kaun\s+se|kis)\s+(?:browser|app|window)\s+mein\s+hai", re.IGNORECASE),
        re.compile(r"which\s+browser\s+is\s+(?:this|it)\s+in", re.IGNORECASE),
    ]

    # 12. Deictic / Reference Commands ("ab is par click karo", "isko band karo", "doosre wale pe jao")
    _DEICTIC_COMMAND_PATTERNS = [
        re.compile(r"^(?:ab\s+)?(?:is|iss|ise|isko|ispe|us|use|usko|ye|yeh)\s+(?:par\s+|pe\s+)?click\s+karo", re.IGNORECASE),
        re.compile(r"^(?:ab\s+)?(?:is|iss|ise|isko|us|use|usko|ye|yeh|same|wahi)\s+(?:ko\s+)?band\s+karo", re.IGNORECASE),
        re.compile(r"^(?:doosre|dusre|pehle|pehla|teesre|aakhiri|next)\s+wale\s+(?:pe|par)\s+(?:jao|click\s+karo|move\s+karo)", re.IGNORECASE),
        re.compile(r"^(?:haan,?\s*)?(?:ab\s+)?is\s+par\s+click\s+karo", re.IGNORECASE),
        re.compile(r"^(?:ab\s+)?woh\s+([a-zA-Z0-9_\-\.]+)\s+wala\s+kholo", re.IGNORECASE),
    ]

    # 13. Reference Corrections ("ye doosra wala hai", "nahi, chrome nahi edge kholo", "ruko, woh nahi doosra", "chrome nahi edge")
    _CORRECTION_PATTERNS = [
        re.compile(r"^(?:ye|yeh)\s+(?:doosra|dusra|pehla|teesra|next)\s+wala\s+hai", re.IGNORECASE),
        re.compile(r"^(?:nahi,?\s*)?([a-zA-Z0-9_\-\.]+)\s+nahi[,\s]+([a-zA-Z0-9_\-\.]+)(?:\s+(?:kholo|chalao|karo))?", re.IGNORECASE),
        re.compile(r"^(?:nahi|nahi\s+nahi|arre\s+nahi|arrey\s+nahi|ruko|wait)[,\s]+woh\s+nahi[,\s]+(doosra(?:\s+wala)?|[a-zA-Z0-9_\-\.]+)", re.IGNORECASE),
        re.compile(r"^(?:woh\s+nahi[,\s]+doosra(?:\s+wala)?|usko\s+nahi[,\s]+isko)$", re.IGNORECASE),
        re.compile(r"^(?:mera\s+matlab|actually)[,\s]+([a-zA-Z0-9_\-\.]+)(?:\s+(?:kholo|tha))?", re.IGNORECASE),
    ]

    # 14. Explicit & Indirect App / Web Launch Command Patterns
    _EXPLICIT_COMMAND_PATTERNS = [
        re.compile(r"^([a-zA-Z0-9_\-\.]+)\s+(?:kholo|open\s+karo|chalao|launch\s+karo|khol\s+do|start\s+kar|on\s+kar)$", re.IGNORECASE),
        re.compile(r"^([a-zA-Z0-9_\-\.]+)\s+(?:khol\s+doge|chala\s+doge|kar\s+do|laga\s+do)\??$", re.IGNORECASE),
        re.compile(r"^(?:mujhe\s+)?([a-zA-Z0-9_\-\.]+)\s+chahiye\??$", re.IGNORECASE),
        re.compile(r"^chalo\s+([a-zA-Z0-9_\-\.]+)$", re.IGNORECASE),
        re.compile(r"^([a-zA-Z0-9_\-\.]+)\s+pe\s+chalte\s+hain$", re.IGNORECASE),
        re.compile(r"^(?:open|launch|please\s+open|would\s+you\s+open)\s+([a-zA-Z0-9_\-\.]+)\??$", re.IGNORECASE),
    ]

    @classmethod
    def classify(
        cls,
        text: str,
        active_topic: Optional[str] = None,
        conversation_state: Optional[Any] = None,
        has_pending_context: bool = False
    ) -> DialogueActResult:
        raw = text.strip()
        cleaned = re.sub(r"[,!?.]+$", "", raw).strip().lower()
        try:
            from core.semantic.normalizer import HinglishNormalizer
            norm = HinglishNormalizer.normalize_text(cleaned)
        except Exception:
            norm = cleaned

        # Check 1: Greetings
        for pat in cls._GREETING_PATTERNS:
            if pat.search(raw) or pat.search(cleaned) or pat.search(norm):
                return DialogueActResult(
                    act=DialogueAct.GREETING,
                    confidence=0.98,
                    topic_hint="greeting",
                    is_executable_command=False,
                    raw_text=raw,
                    normalized_text=norm or cleaned
                )

        # Check 2: Farewells
        for pat in cls._FAREWELL_PATTERNS:
            if pat.search(raw):
                return DialogueActResult(
                    act=DialogueAct.FAREWELL,
                    confidence=0.98,
                    topic_hint="farewell",
                    is_executable_command=False,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 3: Thanks
        for pat in cls._THANKS_PATTERNS:
            if pat.search(raw):
                return DialogueActResult(
                    act=DialogueAct.THANKS,
                    confidence=0.95,
                    is_executable_command=False,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 3.5: User Wellbeing / State ("main achha hun", "theek hun", "sab badhiya", "i'm good")
        for pat in cls._WELLBEING_PATTERNS:
            if pat.search(raw) or pat.search(cleaned):
                has_reciprocal = bool(re.search(r"(?:tum|aap)\s+(?:batao|sunao|bataiye)|how\s+are\s+you|and\s+you|what\s+about\s+you", raw, re.I))
                return DialogueActResult(
                    act=DialogueAct.STATUS_UPDATE,
                    confidence=0.96,
                    topic_hint="wellbeing",
                    subtopic_hint="reciprocal" if has_reciprocal else "positive",
                    is_executable_command=False,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 3.6: Reciprocal Questions / Small Talk Continuations ("tum batao", "aur batao", "kya chal raha hai")
        for pat in cls._RECIPROCAL_CHAT_PATTERNS:
            if pat.search(raw) or pat.search(cleaned):
                return DialogueActResult(
                    act=DialogueAct.SMALL_TALK,
                    confidence=0.95,
                    topic_hint="reciprocal_chat",
                    is_executable_command=False,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 3.7: Idle / Boredom / Casual Chat Starters ("kuch khas nahi", "bore ho raha hoon")
        for pat in cls._IDLE_OR_BORED_PATTERNS:
            if pat.search(raw) or pat.search(cleaned):
                return DialogueActResult(
                    act=DialogueAct.CASUAL_STATEMENT,
                    confidence=0.92,
                    topic_hint="idle_chat",
                    is_executable_command=False,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 4: Context Inquiry ("ye kaun se browser mein hai?")
        for pat in cls._CONTEXT_INQUIRY_PATTERNS:
            if pat.search(raw):
                return DialogueActResult(
                    act=DialogueAct.QUESTION,
                    confidence=0.95,
                    topic_hint="context_inquiry",
                    subtopic_hint="browser_state",
                    is_executable_command=False,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 5: Visual Search Query ("Paramhans Aashram kahan likha hai?")
        for pat in cls._VISUAL_FIND_PATTERNS:
            m = pat.search(raw)
            if m:
                target_text = m.group(1).strip().strip("'\"") if m.groups() else ""
                return DialogueActResult(
                    act=DialogueAct.QUESTION,
                    confidence=0.95,
                    topic_hint="visual_search",
                    entities={"visual_target": target_text},
                    is_executable_command=True,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 6: Corrections ("ye doosra wala hai", "nahi, chrome nahi edge kholo", "chrome nahi edge")
        for pat in cls._CORRECTION_PATTERNS:
            m = pat.search(raw) or pat.search(cleaned)
            if m:
                groups = m.groups()
                new_ent = groups[-1] if groups else None
                has_cmd_verb = bool(re.search(r"\b(?:kholo|karo|band|chalao|open|close|start|launch)\b", raw, re.I))
                return DialogueActResult(
                    act=DialogueAct.CORRECTION,
                    confidence=0.95,
                    topic_hint="correction",
                    entities={"correction_match": groups, "new_entity": new_ent},
                    is_executable_command=has_cmd_verb,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 7: Deictic / Reference Commands ("ab is par click karo", "isko band karo", "doosre wale pe jao")
        for pat in cls._DEICTIC_COMMAND_PATTERNS:
            m = pat.search(raw)
            if m:
                # Capture possible entity like "youtube" in "ab woh youtube wala kholo"
                entity_val = m.group(1).strip() if (m.groups() and m.group(1)) else ""
                return DialogueActResult(
                    act=DialogueAct.COMMAND,
                    confidence=0.95,
                    topic_hint="reference_command",
                    entities={"reference_target": entity_val} if entity_val else {},
                    is_executable_command=True,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 8: Food State Updates ("chalo main kha ke aaya", "main lunch karne ja raha hoon")
        for pat in cls._FOOD_EATEN_PATTERNS:
            if pat.search(raw):
                is_leaving_for_food = "ja raha" in raw.lower()
                state_update = {"has_eaten": not is_leaving_for_food, "is_eating": is_leaving_for_food}
                return DialogueActResult(
                    act=DialogueAct.CONTEXT_UPDATE if not is_leaving_for_food else DialogueAct.STATUS_UPDATE,
                    confidence=0.95,
                    topic_hint="food",
                    subtopic_hint="lunch",
                    suggested_state_update=state_update,
                    is_executable_command=False,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 9: Casual Food Statements ("are yaar main ne abhi tak khana nahi khaya")
        for pat in cls._FOOD_NOT_EATEN_PATTERNS:
            if pat.search(raw):
                return DialogueActResult(
                    act=DialogueAct.CASUAL_STATEMENT,
                    confidence=0.95,
                    topic_hint="food",
                    subtopic_hint="lunch",
                    suggested_state_update={"has_eaten": False},
                    is_executable_command=False,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 10: Small Talk ("tum kya kar rahe ho")
        for pat in cls._SMALL_TALK_PATTERNS:
            if pat.search(raw):
                return DialogueActResult(
                    act=DialogueAct.SMALL_TALK,
                    confidence=0.95,
                    topic_hint="small_talk",
                    is_executable_command=False,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 11: Acknowledgements ("achha hai", "theek hai", "hmm", "haan", "chalo")
        for pat in cls._ACK_PATTERNS:
            if pat.search(raw):
                return DialogueActResult(
                    act=DialogueAct.ACKNOWLEDGEMENT,
                    confidence=0.92,
                    topic_hint=active_topic or "general",
                    is_executable_command=False,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 12: Casual Life Statements
        for pat in cls._CASUAL_STATEMENT_PATTERNS:
            if pat.search(raw):
                return DialogueActResult(
                    act=DialogueAct.CASUAL_STATEMENT,
                    confidence=0.90,
                    topic_hint="casual",
                    is_executable_command=False,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 13: Movement / Presence Updates
        for pat in cls._PRESENCE_UPDATE_PATTERNS:
            if pat.search(raw):
                is_back = any(w in raw.lower() for w in ["aa gaya", "back"])
                return DialogueActResult(
                    act=DialogueAct.STATUS_UPDATE,
                    confidence=0.92,
                    topic_hint="presence",
                    suggested_state_update={"is_away": not is_back},
                    is_executable_command=False,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 14: Explicit App / Web Launch Command ("Chrome kholo", "YouTube kholo")
        for pat in cls._EXPLICIT_COMMAND_PATTERNS:
            m = pat.search(raw)
            if m:
                target_app = m.group(1).strip().lower()
                topic_h = "browser" if target_app in ("chrome", "youtube", "browser", "firefox", "edge", "brave") else "app_control"
                return DialogueActResult(
                    act=DialogueAct.COMMAND,
                    confidence=0.95,
                    topic_hint=topic_h,
                    entities={"target": target_app, "action": "open"},
                    is_executable_command=True,
                    raw_text=raw,
                    normalized_text=cleaned
                )

        # Check 15: General question check
        if any(w in cleaned for w in ["kya", "kyun", "kaise", "kab", "kahan", "kitna", "what", "why", "how", "when", "where", "who"]):
            return DialogueActResult(
                act=DialogueAct.QUESTION,
                confidence=0.85,
                topic_hint="inquiry",
                is_executable_command=False,
                raw_text=raw,
                normalized_text=cleaned
            )

        # Default fallback
        return DialogueActResult(
            act=DialogueAct.UNKNOWN,
            confidence=0.40,
            is_executable_command=False,
            raw_text=raw,
            normalized_text=cleaned
        )
