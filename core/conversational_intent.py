# core/conversational_intent.py
"""
Human-Like Conversational Intent & Speech-Act Classification Layer.

Determines the user's conversational intent/speech-act BEFORE command execution:
1. CAPABILITY_QUESTION: User asks if Jarvis can do something ("kya tum system lock kar sakte ho?")
   -> Answer capability directly; NEVER execute.
2. ACTION_COMMAND: User gives an explicit imperative instruction ("system lock karo")
   -> Execute the command; confirm completion.
3. STATUS_QUESTION: User asks about current state ("Chrome open hai kya?", "system lock hai kya?")
   -> Answer current state; do NOT alter state.
4. STATUS_AFTER_ACTION: User asks if past action occurred ("system lock hua?", "Chrome open hua?")
   -> Answer verification of actual state.
5. INFORMATION_QUESTION: User asks for how-to, explanation, or definition ("system lock kaise hota hai?")
   -> Explain; do NOT execute.
6. CONFIRMATION: User is approving a previously discussed action ("haan karo", "yes", "proceed")
   -> Only execute if an active pending operation exists.
7. CANCELLATION: User is rejecting/cancelling ("nahi", "mat karo", "cancel")
   -> Cancel pending operation.
8. CLARIFICATION: Asking for missing details ("kaunsa Chrome?", "kis file ko?")
   -> Ask for missing info; do not guess.
9. TROUBLESHOOTING: Asking why an action failed ("system lock kyun nahi ho raha?")
   -> Explain problem; do NOT re-attempt blindly.
10. GREETING: Salutations ("hello", "namaste", "good morning")
11. CONVERSATION: Small talk, banter, empathy, casual chat
12. FOLLOW_UP: Contextual continuation of dialogue

CRITICAL RULE:
Only ACTION_COMMAND (or active CONFIRMATION) reaches the command executor.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from core.intent import UniversalCategoryRegistry, UniversalIntentCategory

logger = logging.getLogger("jarvis.core.conversational_intent")


class ConversationalIntentType(str, Enum):
    CAPABILITY_QUESTION = "CAPABILITY_QUESTION"
    ACTION_COMMAND = "ACTION_COMMAND"
    STATUS_QUESTION = "STATUS_QUESTION"
    STATUS_AFTER_ACTION = "STATUS_AFTER_ACTION"
    INFORMATION_QUESTION = "INFORMATION_QUESTION"
    CONFIRMATION = "CONFIRMATION"
    CANCELLATION = "CANCELLATION"
    CLARIFICATION = "CLARIFICATION"
    TROUBLESHOOTING = "TROUBLESHOOTING"
    GREETING = "GREETING"
    CONVERSATION = "CONVERSATION"
    EXPRESSED_DESIRE = "EXPRESSED_DESIRE"
    FOLLOW_UP = "FOLLOW_UP"
    FUTURE_INTENTION = "FUTURE_INTENTION"
    FUTURE_EVENT = "FUTURE_EVENT"
    STATEMENT = "STATEMENT"
    # Extended 15 Universal Categories
    COMMAND = "COMMAND"
    QUESTION = "QUESTION"
    INFORMATION_REQUEST = "INFORMATION_REQUEST"
    GENERAL_CONVERSATION = "GENERAL_CONVERSATION"
    CORRECTION = "CORRECTION"
    REJECTION = "REJECTION"
    REQUEST_FOR_CLARIFICATION = "REQUEST_FOR_CLARIFICATION"
    SYSTEM_INFORMATION = "SYSTEM_INFORMATION"
    ACTION_RESULT = "ACTION_RESULT"
    COMPLAINT = "COMPLAINT"
    SMALL_TALK = "SMALL_TALK"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"
    UNINTELLIGIBLE = "UNINTELLIGIBLE"


CONVERSATIONAL_TO_UNIVERSAL: Dict[ConversationalIntentType, UniversalIntentCategory] = {
    ConversationalIntentType.ACTION_COMMAND: UniversalIntentCategory.COMMAND,
    ConversationalIntentType.COMMAND: UniversalIntentCategory.COMMAND,
    ConversationalIntentType.CAPABILITY_QUESTION: UniversalIntentCategory.QUESTION,
    ConversationalIntentType.QUESTION: UniversalIntentCategory.QUESTION,
    ConversationalIntentType.INFORMATION_QUESTION: UniversalIntentCategory.INFORMATION_REQUEST,
    ConversationalIntentType.INFORMATION_REQUEST: UniversalIntentCategory.INFORMATION_REQUEST,
    ConversationalIntentType.CONVERSATION: UniversalIntentCategory.GENERAL_CONVERSATION,
    ConversationalIntentType.EXPRESSED_DESIRE: UniversalIntentCategory.GENERAL_CONVERSATION,
    ConversationalIntentType.FUTURE_INTENTION: UniversalIntentCategory.GENERAL_CONVERSATION,
    ConversationalIntentType.FUTURE_EVENT: UniversalIntentCategory.GENERAL_CONVERSATION,
    ConversationalIntentType.STATEMENT: UniversalIntentCategory.GENERAL_CONVERSATION,
    ConversationalIntentType.GENERAL_CONVERSATION: UniversalIntentCategory.GENERAL_CONVERSATION,
    ConversationalIntentType.FOLLOW_UP: UniversalIntentCategory.FOLLOW_UP,
    ConversationalIntentType.CORRECTION: UniversalIntentCategory.CORRECTION,
    ConversationalIntentType.CONFIRMATION: UniversalIntentCategory.CONFIRMATION,
    ConversationalIntentType.REJECTION: UniversalIntentCategory.REJECTION,
    ConversationalIntentType.CANCELLATION: UniversalIntentCategory.CANCELLATION,
    ConversationalIntentType.TROUBLESHOOTING: UniversalIntentCategory.TROUBLESHOOTING,
    ConversationalIntentType.CLARIFICATION: UniversalIntentCategory.REQUEST_FOR_CLARIFICATION,
    ConversationalIntentType.REQUEST_FOR_CLARIFICATION: UniversalIntentCategory.REQUEST_FOR_CLARIFICATION,
    ConversationalIntentType.STATUS_QUESTION: UniversalIntentCategory.SYSTEM_INFORMATION,
    ConversationalIntentType.SYSTEM_INFORMATION: UniversalIntentCategory.SYSTEM_INFORMATION,
    ConversationalIntentType.STATUS_AFTER_ACTION: UniversalIntentCategory.ACTION_RESULT,
    ConversationalIntentType.ACTION_RESULT: UniversalIntentCategory.ACTION_RESULT,
    ConversationalIntentType.COMPLAINT: UniversalIntentCategory.COMPLAINT,
    ConversationalIntentType.GREETING: UniversalIntentCategory.SMALL_TALK,
    ConversationalIntentType.SMALL_TALK: UniversalIntentCategory.SMALL_TALK,
    ConversationalIntentType.UNKNOWN: UniversalIntentCategory.UNKNOWN,
    ConversationalIntentType.UNINTELLIGIBLE: UniversalIntentCategory.UNKNOWN,
    ConversationalIntentType.AMBIGUOUS: UniversalIntentCategory.AMBIGUOUS,
}


@dataclass
class ConversationalIntentResult:
    intent_type: ConversationalIntentType
    confidence: float
    is_executable: bool
    target: Optional[str] = None
    action_type: Optional[str] = None
    natural_response: Optional[str] = None
    matched_pattern: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    raw_input: str = ""
    normalized_input: str = ""
    universal_category: Optional[UniversalIntentCategory] = None

    def __post_init__(self):
        if self.universal_category is None:
            self.universal_category = CONVERSATIONAL_TO_UNIVERSAL.get(
                self.intent_type, UniversalIntentCategory.GENERAL_CONVERSATION
            )


class ConversationalIntentClassifier:
    """
    Authoritative Conversational Intent & Speech-Act Classifier.
    Acts as a gating layer prior to fast-path and semantic parser execution.
    """

    # Supported capabilities and their natural Hinglish descriptions
    KNOWN_CAPABILITIES: Dict[str, Dict[str, Any]] = {
        "lock_system": {
            "keywords": ["system lock", "pc lock", "screen lock", "lock pc", "lock computer", "computer lock", "laptop lock", "lock system", "lock"],
            "target": "system",
            "action": "lock_system",
            "response_hi": "Haan, main system lock kar sakta hoon.",
            "response_en": "Yes, I can lock the system."
        },
        "restart_system": {
            "keywords": ["restart computer", "computer restart", "pc restart", "system restart", "reboot", "restart the computer", "restart"],
            "target": "system",
            "action": "restart_system",
            "response_hi": "Haan, main computer restart kar sakta hoon.",
            "response_en": "Yes, I can restart the computer."
        },
        "shutdown_system": {
            "keywords": ["shutdown", "system shutdown", "pc shutdown", "computer shutdown", "turn off"],
            "target": "system",
            "action": "shutdown_system",
            "response_hi": "Haan, main system shutdown kar sakta hoon.",
            "response_en": "Yes, I can shut down the computer."
        },
        "open_chrome": {
            "keywords": ["chrome", "google chrome"],
            "target": "chrome",
            "action": "open_app",
            "response_hi": "Haan, main Chrome open kar sakta hoon.",
            "response_en": "Yes, I can open Chrome."
        },
        "open_excel": {
            "keywords": ["excel", "microsoft excel"],
            "target": "excel",
            "action": "open_app",
            "response_hi": "Haan, main Excel chala sakta hoon.",
            "response_en": "Yes, I can open Excel."
        },
        "open_notepad": {
            "keywords": ["notepad"],
            "target": "notepad",
            "action": "open_app",
            "response_hi": "Haan, main Notepad open kar sakta hoon.",
            "response_en": "Yes, I can open Notepad."
        },
        "open_calculator": {
            "keywords": ["calculator", "calc"],
            "target": "calculator",
            "action": "open_app",
            "response_hi": "Haan, main Calculator open kar sakta hoon.",
            "response_en": "Yes, I can open Calculator."
        },
        "open_brave": {
            "keywords": ["brave", "brave browser"],
            "target": "brave",
            "action": "open_app",
            "response_hi": "Haan, main Brave browser open kar sakta hoon.",
            "response_en": "Yes, I can open Brave."
        },
        "open_spotify": {
            "keywords": ["spotify"],
            "target": "spotify",
            "action": "open_app",
            "response_hi": "Haan, main Spotify open kar sakta hoon.",
            "response_en": "Yes, I can open Spotify."
        },
        "open_youtube": {
            "keywords": ["youtube", "yt"],
            "target": "youtube",
            "action": "open_website",
            "response_hi": "Haan, main YouTube chala sakta hoon.",
            "response_en": "Yes, I can open and play YouTube."
        },
        "volume_control": {
            "keywords": ["volume", "awaz", "aawaz", "sound"],
            "target": "audio",
            "action": "volume_control",
            "response_hi": "Haan, main system volume adjust kar sakta hoon.",
            "response_en": "Yes, I can control system volume."
        },
        "screen_awareness": {
            "keywords": ["screen dekh", "screenshot", "screen inspect", "screen reading"],
            "target": "screen",
            "action": "screen_inspect",
            "response_hi": "Haan, main screen dekh sakta hoon aur screen content inspect kar sakta hoon.",
            "response_en": "Yes, I can inspect your screen."
        },
        "reminders": {
            "keywords": ["reminder", "alarm"],
            "target": "reminder",
            "action": "set_reminder",
            "response_hi": "Haan, main aapke liye reminders set kar sakta hoon.",
            "response_en": "Yes, I can set reminders for you."
        },
        "draw_bappa": {
            "keywords": [
                "bappa", "draw bappa", "drawing bappa", "bappa drawing", "bappa ki drawing",
                "bappa draw", "ganpati drawing", "ganesha drawing"
            ],
            "target": "bappa",
            "action": "draw",
            "response_hi": "Haan, main Bappa ki drawing bana sakta hoon.",
            "response_en": "Yes, I can draw Bappa for you."
        },
        "system_cleanup": {
            "keywords": [
                "clean temp", "clear temp", "temp cleanup", "temporary files",
                "clean temporary files", "recycle bin", "empty recycle bin", "trash"
            ],
            "target": "system",
            "action": "system_maintenance",
            "response_hi": "Haan, main temporary files aur recycle bin clear kar sakta hoon.",
            "response_en": "Yes, I can clean temporary files and empty the recycle bin."
        },
        "wallpaper": {
            "keywords": [
                "wallpaper", "desktop wallpaper", "background", "wallpaper change",
                "wallpaper badal", "wallpaper lagao", "wallpaper set"
            ],
            "target": "wallpaper",
            "action": "change_wallpaper",
            "response_hi": "Haan, main desktop wallpaper change kar sakta hoon.",
            "response_en": "Yes, I can change your desktop wallpaper."
        },
        "weather": {
            "keywords": [
                "weather", "mausam", "baarish", "rain", "temperature", "forecast", "garmi", "sardi", "thand"
            ],
            "target": "weather",
            "action": "check_weather",
            "response_hi": "Haan, main live weather conditions aur forecast check karke bata sakta hoon.",
            "response_en": "Yes, I can check live weather conditions and forecasts for you."
        },
        "open_vlc": {
            "keywords": ["vlc", "vlc player", "vlc media player", "media player"],
            "target": "vlc",
            "action": "open_app",
            "response_hi": "Haan, main VLC open kar sakta hoon.",
            "response_en": "Yes, I can open VLC."
        }
    }

    # Precompiled regex patterns for speech-act determination
    CAPABILITY_PATTERNS = [
        # Hindi/Hinglish capability question forms
        re.compile(r"^(?:kya\s+)?(?:tum|aap)\s+(.+?)\s*(?:kar\s+)?(?:sakte\s*y?\s*ho|sakti\s*ho|sakte\s*hain|kar\s+paoge|kar\s+sakte\s+ho)\b(?:\s+kya)?\??$", re.IGNORECASE),
        re.compile(r"^kya\s+(?:tum|aap)\s+(.+?)\??$", re.IGNORECASE),
        re.compile(r"^(.+?)\s+(?:kar\s+)?(?:sakte\s*y?\s*ho|sakti\s*ho|sakte\s*hain|kar\s+paoge)(?:\s+kya)?\??$", re.IGNORECASE),
        re.compile(r"^tumse\s+(.+?)\s+(?:ho\s+paega|ho\s+sakta\s+hai|ho\s+payega)\s*(?:kya)?\??$", re.IGNORECASE),
        re.compile(r"^kya\s+(?:tumse|aapse)\s+(.+?)\s+(?:ho\s+paega|ho\s+sakta\s+hai|ho\s+payega)\??$", re.IGNORECASE),
        re.compile(r"^kya\s+ye\s+(.+?)\s+(?:ho\s+sakta\s+hai|kar\s+sakte\s+ho)\??$", re.IGNORECASE),
        # English capability question forms
        re.compile(r"^(?:can\s+you|could\s+you|are\s+you\s+able\s+to|do\s+you\s+know\s+how\s+to|can\s+jarvis)\s+(.+?)\??$", re.IGNORECASE),
        re.compile(r"^(?:is\s+it\s+possible\s+for\s+you\s+to)\s+(.+?)\??$", re.IGNORECASE),
    ]

    TROUBLESHOOTING_PATTERNS = [
        re.compile(r"\b(?:kyun|kyu|why)\s+(?:nahi|not)\b", re.IGNORECASE),
        re.compile(r"\bwhy\s+(?:isn't|is\s+not|won't|can't)\b", re.IGNORECASE),
        re.compile(r"\b(?:problem|error|issue)\s+kya\s+hai\b", re.IGNORECASE),
        re.compile(r"\bwhy\s+did\s+(.+?)\s+fail\b", re.IGNORECASE),
        re.compile(r"\b(.+?)\s+(?:kyun|kyu)\s+fail\s+hua\b", re.IGNORECASE),
    ]

    STATUS_AFTER_ACTION_PATTERNS = [
        re.compile(r"^(?:kya\s+)?(?:(.+?)\s+)?(?:lock\s+hua|open\s+hua|chalu\s+hua|band\s+hua|restart\s+hua|start\s+hua|clean\s+hua|clear\s+hua|saaf\s+hua|delete\s+hua|empty\s+hua)(?:\s+kya)?\??$", re.IGNORECASE),
        re.compile(r"^(?:kya\s+)?(?:(.+?)\s+)?(?:lock\s+ho\s+gaya|open\s+ho\s+gaya|chalu\s+ho\s+gaya|band\s+ho\s+gaya|restart\s+ho\s+gaya|clean\s+ho\s+gaya|clear\s+ho\s+gaya|saaf\s+ho\s+gaya|empty\s+ho\s+gaya|ho\s+gaya)(?:\s+kya|hai)?\??$", re.IGNORECASE),
        re.compile(r"^(?:did|has)\s+(.+?)\s+(?:lock|open|start|close|restart|clean|clear|empty)(?:\s+yet)?\??$", re.IGNORECASE),
        re.compile(r"^is\s+(.+?)\s+(?:done|finished|completed|cleaned|emptied)\??$", re.IGNORECASE),
    ]

    STATUS_QUESTION_PATTERNS = [
        re.compile(r"^(?:kya\s+)?(.+?)\s+(?:open|chalu|running|active|lock|locked|chal\s+raha|chal\s+rahi|on|khula|khuli|band)\s+hai(?:\s+kya)?\??$", re.IGNORECASE),
        re.compile(r"^(?:kya\s+)?(.+?)\s+(?:open|chalu|running|active|khula|khuli)\s+nahi\s+hai(?:\s+na)?\??$", re.IGNORECASE),
        re.compile(r"^(?:is|check\s+if)\s+(.+?)\s+(?:open|running|active|locked|lock|on)\??$", re.IGNORECASE),
        re.compile(r"^(?:kaunsa|kaunsi|which)\s+(.+?)\s+(?:window|tab)?\s*(?:open|active|chal\s+raha)\s+hai(?:\s+kya)?\??$", re.IGNORECASE),
        re.compile(r"^status\s+of\s+(.+?)\??$", re.IGNORECASE),
        re.compile(r"^(?:is\s+)?(.+?)\s+(?:locked|unlocked)\??$", re.IGNORECASE),
    ]

    # Browser-location queries: "youtube konse browser me hai?", "flipkart kahan open hai?", "youtube kaun se brouser mein open hai"
    # These must fire BEFORE STATUS_QUESTION_PATTERNS to prevent capturing the full
    # noise phrase ("youtube konse browser me") as the status target.
    # Group(1) or (?P<site>) extracts ONLY the website/app name.
    BROWSER_LOCATION_PATTERNS = [
        re.compile(
            r"^(?P<site>[a-z0-9]+(?:\.[a-z]+)?)\s+"
            r"(?:konse|kis|kaun\s+se|kaun\s+si|kaunse|kaunsi|which|kahan|kidhar)"
            r"\s+(?:browser|brouser|browzer|broser|tab|window)(?:\s+me(?:in)?|\s+mein|\s+par|\s+pe)?(?:\s+(?:open\s+hai|khula\s+hai|chal\s+raha\s+hai|open|hai|khula))?\s*\??$",
            re.IGNORECASE
        ),
        re.compile(
            r"^(?P<site>[a-z0-9]+(?:\.[a-z]+)?)\s+kahan\s+(?:open\s+hai|hai|khula\s+hai|chal\s+raha\s+hai)\s*\??$",
            re.IGNORECASE
        ),
        re.compile(
            r"^(?P<site>[a-z0-9]+(?:\.[a-z]+)?)\s+"
            r"(?:konse|kis|kaun\s+se|kaunse|which)\s+(?:browser|brouser|browzer|broser|tab|window)(?:\s+me(?:in)?|\s+mein)?\s+(?:open\s+hai|hai|khula\s+hai|chal\s+raha\s+hai)\s*\??$",
            re.IGNORECASE
        ),
        re.compile(
            r"^(?:konse|kis|kaun\s+se|kaun\s+si|kaunse|kaunsi|which)"
            r"\s+(?:browser|brouser|browzer|broser|tab|window)(?:\s+me(?:in)?|\s+mein|\s+par|\s+pe)?\s+"
            r"(?P<site>[a-z0-9]+(?:\.[a-z]+)?)(?:\s+(?:open\s+hai|khula\s+hai|chal\s+raha\s+hai|open|hai|khula))?\s*\??$",
            re.IGNORECASE
        ),
        re.compile(
            r"^(?:which|what)\s+(?:browser|brouser|browzer|broser)\s+(?:is\s+)?(?P<site>[a-z0-9]+(?:\.[a-z]+)?)\s+(?:open|running)(?:\s+in)?\s*\??$",
            re.IGNORECASE
        ),
        re.compile(
            r"^(?P<site>[a-z0-9]+(?:\.[a-z]+)?)\s+(?:is\s+)?in\s+which\s+(?:browser|brouser|browzer|broser)\s*\??$",
            re.IGNORECASE
        ),
    ]

    CONFIRMATION_PATTERNS = [
        re.compile(r"^(?:haan(?:\s+(?:karo|kar\s+do|kardo|open\s+kar\s+do|open\s+kardo|open\s+karo|khol\s+do|chala\s+do|chalao|proceed|bhai|ji))?|yes(?:\s+(?:please|proceed|do\s+it|open\s+it))?|yep|yeah|kar\s+do|karo|open\s+kar\s+do|open\s+kardo|open\s+karo|khol\s+do|theek\s+hai(?:\s+(?:karo|kar\s+do|kardo|open\s+kar\s+do))?|bilkul|sure|proceed|okay\s+proceed|kardo|okay\s+karo|ok\s+karo)$", re.IGNORECASE),
    ]

    CANCELLATION_PATTERNS = [
        re.compile(r"^(?:nahi|cancel|cancel\s+karo|mat\s+karo|mat\s+karo\s+yeh|rehne\s+do|stop|abort|ruk\s+jao|ruko|stop\s+it|terminate\s+task)$", re.IGNORECASE),
    ]

    REJECTION_PATTERNS = [
        re.compile(r"^(?:nahi\s+rehne\s+do|nahi\s+chahiye|no\s+don'?t\s+do\s+that|bilkul\s+nahi|no\s+thanks|na\s+re|nahi\s+karna|i\s+don'?t\s+want\s+this|not\s+now|nah|nope)$", re.IGNORECASE),
    ]

    COMPLAINT_PATTERNS = [
        re.compile(r"(?:tum\s+sun\s+nahi\s+rahe|galat\s+kar\s+diya|you\s+made\s+a\s+mistake|bahut\s+slow\s+ho|tumne\s+galat\s+kiya|kya\s+bakwaas\s+hai|hamesha\s+galat\s+karte\s+ho|not\s+listening|you\s+are\s+useless|stupid\s+assistant)", re.IGNORECASE),
    ]

    CLARIFICATION_PATTERNS = [
        re.compile(r"^(?:kya\s+matlab|what\s+do\s+you\s+mean|samjha\s+nahi|samajh\s+nahi\s+aaya|kaun\s+sa\s+file|kaunsa\s+app|can\s+you\s+clarify|kya\s+kehna\s+chahte\s+ho|phir\s+se\s+batao|pardon|what)(?:\??)$", re.IGNORECASE),
    ]

    FOLLOW_UP_PATTERNS = [
        re.compile(r"^(?:aur\s+uske\s+baad\??|what\s+about\s+tomorrow\??|and\s+chrome\s+also\??|ab\s+next\s+kya\s+karein\??|next\s+step\s+kya\s+hai\??|aur\s+bhi\s+kuch\??|uske\s+baad\s+kya)$", re.IGNORECASE),
    ]

    CORRECTION_PATTERNS = [
        re.compile(r"^(?:nahi[,\s]+.+?\s+nahi\s+.+?|no[,\s]+i\s+meant\s+.+?|maine\s+\d+\s+bola\s+tha|correction[,\s]+.+?)$", re.IGNORECASE),
    ]

    SMALL_TALK_PATTERNS = [
        re.compile(r"^(?:shukriya|dhanyawad|thank\s+you|thanks|nice\s+job|great\s+job|well\s+done|good\s+work|you\s+are\s+awesome|tum\s+bahut\s+acche\s+ho|bye|goodbye|alvida|good\s+night|shubh\s+ratri|tell\s+me\s+a\s+joke|koi\s+joke\s+sunao)\b", re.IGNORECASE),
    ]

    SYSTEM_INFO_PATTERNS = [
        re.compile(r"(?:cpu\s+usage|battery\s+percentage|ram\s+status|memory\s+kitni|system\s+status|ip\s+address|hardware\s+info|disk\s+space)", re.IGNORECASE),
    ]

    INFORMATION_PATTERNS = [
        re.compile(r"^(?:what\s+is|who\s+is|explain|kaise\s+karein|kaise\s+hota\s+hai|kaise\s+karte\s+hain|batao\s+ki)\s+(.+)$", re.IGNORECASE),
        re.compile(r"^(.+?)\s+(?:kya\s+hai|kya\s+hota\s+hai|kya\s+hoti\s+hai|kya\s+the|kya\s+thi|kaise\s+karte\s+hain|kaise\s+hota\s+hai|kaise\s+karein)\??$", re.IGNORECASE),
        re.compile(r"^(?:capital\s+of|currency\s+of)\s+(.+)$", re.IGNORECASE),
    ]

    _GREETING_QUESTION_OR_ACTION_RE = re.compile(
        r"(?:\bka\s+meaning\b|\bmeaning\s+kya\b|\bmatlab\s+kya\b|\bkya\s+meaning\b|"
        r"\bwhat\s+(?:does|is)\b|\bmeaning\s+of\b|\bexplain\b|\bdefine\b|"
        r"\bmessage\s+likho\b|\blikh\s+do\b|\blikho\b|\btype\s+karo\b|\bsend\s+karo\b|"
        r"\bbolo\b|\bsay\b|\bbol\s+do\b|\bkaho\b|\bbatana\b)",
        re.IGNORECASE
    )
    _SOCIAL_FILLERS_RE = re.compile(
        r"\b(?:jarvis|sir|boss|bhai|dost|bro|buddy|yaar|friend|dear|ji|madam|mam|please|zara)\b",
        re.IGNORECASE
    )

    GREETING_PATTERNS = [
        re.compile(
            r"^(?:hi|hello|hey|helo|hallo|helllo|hii+|hie|namaste|namaskar|pranam|ram\s+ram|radhe\s+radhe|salaam|salam|sat\s+sri\s+akal|shubh\s+prabhat|suprabhat|subah\s+bakhair|gm|morning|evening|afternoon|good\s+(?:morning|afternoon|evening|day)|gud\s+(?:morning|afternoon|evening|day)|good\s+(?:moring|mornig|mornin|mrng)|gud\s+(?:moring|mornig|mornin|mrng))"
            r"(?:\s+(?:jarvis|sir|boss|bhai|dost|bro|buddy|yaar|friend|dear|ji|madam|mam|to\s+you|everyone|all))?$",
            re.IGNORECASE
        ),
        re.compile(
            r"^(?:hey\s+(?:there|good\s+morning|morning|dear)|hello\s+(?:there|good\s+morning|morning|dear)|hi\s+dear|hello\s+dear|gm\s+dear|morning\s+dear)$",
            re.IGNORECASE
        ),
        re.compile(
            r"^(?:good|gud)\s+(?:morning|afternoon|evening|night|moring|mornig|mornin|mrng|day)\b",
            re.IGNORECASE
        ),
    ]

    IMPERATIVE_VERBS = [
        "bhej do", "bhej de", "bhej dijiye", "bhejo", "bhej", "send kar do", "send karo", "send kar",
        "chala do", "chala de", "khol do", "khol de", "kar do", "kar de", "band kar do", "band karo",
        "play kar do", "play karo", "restart karo", "lock karo", "kam karo", "delete karo", "create karo", "mute karo",
        "clear kar do", "clear karo", "clean kar do", "clean karo", "saaf kar do", "saaf karo",
        "khali kar do", "khali karo", "hata do", "hatao", "cleanup kar do", "cleanup karo",
        "dikha do", "dikha de", "dikhai de", "dikhao", "dikhe", "show", "display", "visualize", "view",
        "yaad dila dena", "yaad dila do", "yaad dilana", "yaad dilao", "remind me", "reminder lagao", "reminder set karo",
        "suggest kar do", "suggest karo", "suggest kar", "recommend kar do", "recommend karo", "shortlist kar do", "shortlist karo",
        "bata do", "bata de", "batao", "bata", "bataiye", "batana", "suggest", "recommend", "shortlist", "dhoondo", "scan", "analyze",
        "karo", "kholo", "kholna", "khol", "chalao", "chalana", "chala", "open", "launch", "close", "start", "stop", "restart", "reboot", "lock",
        "kill", "terminate", "badhao", "ghatao", "banao", "play", "draw", "drawing", "sketch",
        "clear", "clean", "cleanup", "saaf", "khali", "hata"
    ]

    _IMPERATIVE_VERBS_RE = re.compile(
        r'\b(' + '|'.join(re.escape(v) for v in sorted(IMPERATIVE_VERBS, key=len, reverse=True)) + r')\b',
        re.IGNORECASE
    )
    _FILLERS_RE = re.compile(r'\b(?:jarvis|please|bhai|yaar|zara|ko|mein|par|bhi|ab|abhi)\b', re.IGNORECASE)
    _WHITESPACE_RE = re.compile(r'\s+')

    _COMPILED_DIRECT_CMDS = [
        (re.compile(r"^lock\s+(?:the\s+)?(?:pc|system|screen|computer)$", re.IGNORECASE), "lock", "system"),
        (re.compile(r"^system\s+lock$", re.IGNORECASE), "lock", "system"),
        (re.compile(r"^pc\s+lock$", re.IGNORECASE), "lock", "system"),
        (re.compile(r"^(?:exit|quit|shutdown|bye\s+bye|bye-bye|bye|goodbye|alvida|terminate)(?:\s+jarvis)?$", re.IGNORECASE), "shutdown", "jarvis"),
        (re.compile(r"^(?:jarvis\s+)?(?:exit|quit|shutdown|bye\s+bye|bye-bye|bye|goodbye|alvida|terminate)$", re.IGNORECASE), "shutdown", "jarvis"),
        (re.compile(r"^(?:jarvis\s+(?:ko\s+)?band\s+karo|band\s+karo\s+jarvis|jarvis\s+close\s+karo|close\s+jarvis)$", re.IGNORECASE), "shutdown", "jarvis"),
        (re.compile(r"^(?:drawing|draw)\s+(?:bappa|ganpati(?:\s+bappa)?|ganesh(?:a)?)(?:\s+(?:banao|karo|dikhao))?$", re.IGNORECASE), "draw", "bappa"),
        (re.compile(r"^(?:bappa|ganpati(?:\s+bappa)?|ganesh(?:a)?)\s+(?:ki\s+)?(?:drawing|sketch)(?:\s+(?:banao|karo|dikhao))?$", re.IGNORECASE), "draw", "bappa"),
        (re.compile(r"^(?:bappa|ganpati(?:\s+bappa)?|ganesh(?:a)?)\s+(?:draw\s+karo|banao)$", re.IGNORECASE), "draw", "bappa"),
        (re.compile(r"^(?:clear|clean|empty|saaf|khali)\s+(?:the\s+)?recycle\s*bin(?:\s+(?:karo|kar\s+do))?$", re.IGNORECASE), "empty", "recycle_bin"),
        (re.compile(r"^(?:recycle\s*bin)\s+(?:saaf|clean|clear|khali|empty)(?:\s+(?:karo|kar\s+do))?$", re.IGNORECASE), "empty", "recycle_bin"),
        (re.compile(r"^(?:clear|clean|remove|delete|empty|saaf|khali)\s+(?:the\s+)?(?:temp|temporary)(?:\s+files?)?(?:\s+(?:karo|kar\s+do|saaf\s+karo))?$", re.IGNORECASE), "clean", "temp_files"),
        (re.compile(r"^(?:temp|temporary)(?:\s+files?)?\s+(?:saaf|clean|clear|khali|delete|hatao)(?:\s+(?:karo|kar\s+do))?$", re.IGNORECASE), "clean", "temp_files"),
        (re.compile(r"^(.+?)\s+(?:yaad\s+dilana|yaad\s+dila\s+do|yaad\s+dila\s+dena|yaad\s+dilao)$", re.IGNORECASE), "create_reminder", "reminder"),
        (re.compile(r"^(?:remind\s+me|yaad\s+dilana|yaad\s+dila\s+do)\s+(?:to\s+|ki\s+|ke\s+liye\s+)?(.+)$", re.IGNORECASE), "create_reminder", "reminder"),
        (re.compile(r"^(?:open|launch)\s+([a-z0-9\s]+)$", re.IGNORECASE), "open", None),
        (re.compile(r"^(?:close|quit|exit)\s+([a-z0-9\s]+)$", re.IGNORECASE), "close", None),
        (re.compile(r"^.*(?:archify|architecture).*(?:dikhao|dikhai\s+de|dikhe|show|open|display|kholo|viewer|view|visualize).*$", re.IGNORECASE), "show_architecture", "archify"),
        (re.compile(r"^(?:archify(?:\s+(?:dikhao|open\s+karo|kholo|show|display))?|(?:show|open|display)\s+archify|complete\s+archify(?:\s+dikhao)?)$", re.IGNORECASE), "show_architecture", "archify"),
        (re.compile(r"^(?:jarvis\s+)?architecture\s+(?:dikhao|show|open(?:\s+karo)?|display)$", re.IGNORECASE), "show_architecture", "archify"),
        (re.compile(r"^(?:restart|reboot)\s+(?:the\s+)?(?:pc|computer|system)$", re.IGNORECASE), "restart", "system"),
        (re.compile(r"^(?:shutdown|power\s+off)\s+(?:the\s+)?(?:pc|computer|system)$", re.IGNORECASE), "shutdown", "system"),
    ]

    @classmethod
    def classify(
        cls,
        raw_text: str,
        has_pending_confirmation: bool = False,
        active_context: Optional[Any] = None
    ) -> ConversationalIntentResult:
        """
        Main classification entrypoint.
        Evaluates speech-act and conversational intent.
        """
        text = raw_text.strip()
        lowered = text.lower()
        cleaned = re.sub(r"\s+", " ", lowered).strip()
        cleaned_no_punct = re.sub(r"[?!.,]", "", cleaned).strip()

        logger.debug("[CONVERSATIONAL_INTENT_RAW] text=%r pending_conf=%s", text, has_pending_confirmation)

        # 0. Check for Unintelligible / Corrupted / Random Keyboard Input
        from core.speech_understanding import InputQuality, InputQualityEvaluator, ContextualRecoveryEngine, NaturalUncertaintyResponder
        quality, _, _ = InputQualityEvaluator.evaluate_quality(raw_text, cleaned)

        if quality == InputQuality.UNINTELLIGIBLE:
            resp_prompt = NaturalUncertaintyResponder.get_unintelligible_response()
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.UNKNOWN,
                confidence=0.05,
                is_executable=False,
                natural_response=resp_prompt,
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s response=%r", res.intent_type.value, res.confidence, res.is_executable, resp_prompt)
            return res

        if quality == InputQuality.INCOMPLETE_FRAGMENT:
            is_rec, rec_text, ctx_desc, rec_conf = ContextualRecoveryEngine.attempt_recovery(
                text=cleaned, quality=quality, active_context=active_context
            )
            if not is_rec:
                resp_prompt = NaturalUncertaintyResponder.get_incomplete_response()
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.UNKNOWN,
                    confidence=0.15,
                    is_executable=False,
                    natural_response=resp_prompt,
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s response=%r", res.intent_type.value, res.confidence, res.is_executable, resp_prompt)
                return res

        if quality == InputQuality.AMBIGUOUS:
            is_rec, rec_text, ctx_desc, rec_conf = ContextualRecoveryEngine.attempt_recovery(
                text=cleaned, quality=quality, active_context=active_context
            )
            if not is_rec:
                resp_prompt = NaturalUncertaintyResponder.get_ambiguous_response()
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.AMBIGUOUS,
                    confidence=0.45,
                    is_executable=False,
                    natural_response=resp_prompt,
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s response=%r", res.intent_type.value, res.confidence, res.is_executable, resp_prompt)
                return res

        # 0.5 Deterministic math gate: "2+2=?", "2+2 kitna hota hai" are ACTION_COMMAND,
        # never CONVERSATION chitchat. Single owner: plugins.math.calculator.
        try:
            from plugins.math.calculator import SpokenMathNormalizer as _MathGate
            if _MathGate.is_math_query(text) or _MathGate.is_math_query(cleaned):
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.ACTION_COMMAND,
                    confidence=0.97,
                    is_executable=True,
                    action_type="calculate",
                    target="math",
                    parameters={"expression": text.strip()},
                    raw_input=raw_text,
                    normalized_input=cleaned,
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s (math gate)", res.intent_type.value, res.confidence, res.is_executable)
                return res
        except Exception:
            pass

        # 1. Check for Cancellation / Abort
        for pat in cls.CANCELLATION_PATTERNS:
            if pat.fullmatch(cleaned_no_punct):
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.CANCELLATION,
                    confidence=0.98,
                    is_executable=False,
                    natural_response="Theek hai, cancel kar diya hai.",
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s", res.intent_type.value, res.confidence, res.is_executable)
                return res

        # 1.5. Check for Rejection / Refusal
        for pat in cls.REJECTION_PATTERNS:
            if pat.fullmatch(cleaned_no_punct):
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.REJECTION,
                    confidence=0.98,
                    is_executable=False,
                    natural_response="Theek hai, jaisa aap chahein.",
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s", res.intent_type.value, res.confidence, res.is_executable)
                return res

        # 1.55. Explicit Negation Invariant Gating ("Chrome mat kholo", "Usko band mat karo", "Maine Chrome nahi bola")
        is_neg, neg_act, neg_tgt = cls._detect_explicit_negation(cleaned)
        if is_neg:
            if neg_tgt:
                resp = f"Theek hai, main {neg_tgt} {'close' if neg_act == 'close' else 'open'} nahi kar raha."
            else:
                resp = "Theek hai, main yeh action perform nahi kar raha."
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.REJECTION,
                confidence=0.98,
                is_executable=False,
                target=neg_tgt,
                action_type=neg_act,
                natural_response=resp,
                parameters={"is_negated": True, "negated_action": neg_act},
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] NEGATION INVARIANT: target=%r act=%r exec=%s", neg_tgt, neg_act, False)
            return res

        # 1.56. State Contradiction & Dispute Invariant Gating ("lekin Chrome mein to open YouTube Nahin Hai", "par YouTube open nahi hai")
        is_dispute, d_target, d_container, d_cond = cls._detect_state_dispute_or_contradiction(
            cleaned, raw_text, active_context=active_context
        )
        if is_dispute:
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.CORRECTION,
                confidence=0.96,
                is_executable=False,
                target=d_target,
                natural_response="Maafi chahta hoon, maine check kiya — yeh open nahi hai.",
                parameters={
                    "state_dispute": True,
                    "disputed_condition": d_cond,
                    "target": d_target,
                    "container": d_container,
                },
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] STATE DISPUTE INVARIANT: target=%r container=%r cond=%r exec=%s", d_target, d_container, d_cond, False)
            return res

        # 1.58. Pragmatic Situational Remarks ("Yaar bahut garmi hai", "Bahut thand hai")
        is_prag, p_goal, p_prompt, p_fact = cls._detect_pragmatic_statement(cleaned, raw_text)
        if is_prag:
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.EXPRESSED_DESIRE,
                confidence=0.58,  # Calibrated uncertainty: clarification required, never execute prematurely!
                is_executable=False,
                target=p_goal,
                natural_response=p_prompt,
                parameters={
                    "pragmatic_goal": p_goal,
                    "clarification_prompt": p_prompt,
                    "stated_condition": p_fact,
                    "decision": "ASK_CLARIFICATION"
                },
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] PRAGMATIC STATEMENT: goal=%s conf=0.58 prompt=%r", p_goal, p_prompt)
            return res

        # 1.59. Social Inquiries & Conversational Starters ("Ek baat batao", "Mujhe ek cheez poochni hai", "Suno")
        if re.search(r"^(?:ek\s+baat\s+batao|mujhe\s+ek\s+cheez\s+poochni\s+hai|suno|sun)(?:\s+na)?\??$", cleaned):
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.INFORMATION_QUESTION,
                confidence=0.92,
                is_executable=False,
                natural_response="Haan boliye, main sun raha hoon.",
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s", res.intent_type.value, res.confidence, res.is_executable)
            return res

        # 1.6. Check for User Complaint
        for pat in cls.COMPLAINT_PATTERNS:
            if pat.search(cleaned):
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.COMPLAINT,
                    confidence=0.95,
                    is_executable=False,
                    natural_response="Maafi chahta hoon, main turant ise theek karne ki koshish karta hoon.",
                    matched_pattern=pat.pattern,
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s", res.intent_type.value, res.confidence, res.is_executable)
                return res

        # 1.7. Check for Request for Clarification
        for pat in cls.CLARIFICATION_PATTERNS:
            if pat.search(cleaned) or pat.search(cleaned_no_punct):
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.REQUEST_FOR_CLARIFICATION,
                    confidence=0.92,
                    is_executable=False,
                    natural_response="Mera matlab tha ki kya main action proceed karun ya koi specific setting chahte hain?",
                    matched_pattern=pat.pattern,
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s", res.intent_type.value, res.confidence, res.is_executable)
                return res

        # 1.8. Check for Follow-Up Continues
        for pat in cls.FOLLOW_UP_PATTERNS:
            if pat.search(cleaned):
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.FOLLOW_UP,
                    confidence=0.90,
                    is_executable=False,
                    natural_response="Ji, batayein next kya karna hai?",
                    matched_pattern=pat.pattern,
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s", res.intent_type.value, res.confidence, res.is_executable)
                return res

        # 1.9. Check for Conversational Correction
        for pat in cls.CORRECTION_PATTERNS:
            if pat.search(cleaned):
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.CORRECTION,
                    confidence=0.95,
                    is_executable=False,
                    natural_response="Theek hai, correction note kar liya hai.",
                    matched_pattern=pat.pattern,
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s", res.intent_type.value, res.confidence, res.is_executable)
                return res

        # 2. Check for Confirmation / Permission
        for pat in cls.CONFIRMATION_PATTERNS:
            if pat.fullmatch(cleaned_no_punct):
                if has_pending_confirmation:
                    res = ConversationalIntentResult(
                        intent_type=ConversationalIntentType.CONFIRMATION,
                        confidence=0.98,
                        is_executable=True,
                        raw_input=raw_text,
                        normalized_input=cleaned
                    )
                else:
                    res = ConversationalIntentResult(
                        intent_type=ConversationalIntentType.CONFIRMATION,
                        confidence=0.75,
                        is_executable=False,
                        natural_response="Ji, batayein kya karna hai?",
                        raw_input=raw_text,
                        normalized_input=cleaned
                    )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s (pending_conf=%s)", res.intent_type.value, res.confidence, res.is_executable, has_pending_confirmation)
                return res

        # 2.5. Complaint about prior promise + implicit command
        # ("abhi tum ne bola tha ki vlc open kar sakte ho to open kyun nahi kartey")
        # Human-like: apologize + EXECUTE the wanted action, not generic troubleshooting.
        promise_cmd = cls._detect_complaint_with_action(cleaned, raw_text)
        if promise_cmd is not None:
            act_verb_p, act_target_p = promise_cmd
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.ACTION_COMMAND,
                confidence=0.95,
                is_executable=True,
                target=act_target_p,
                action_type=act_verb_p,
                parameters={"apology_needed": True, "complaint_recovery": True},
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f target=%r action=%r exec=%s (complaint-recovery)", res.intent_type.value, res.confidence, act_target_p, act_verb_p, res.is_executable)
            return res

        # 3. Check for Troubleshooting Queries ("system lock kyun nahi ho raha?")
        for pat in cls.TROUBLESHOOTING_PATTERNS:
            if pat.search(cleaned):
                trouble_resp = cls._resolve_troubleshooting_response(cleaned)
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.TROUBLESHOOTING,
                    confidence=0.95,
                    is_executable=False,
                    natural_response=trouble_resp,
                    matched_pattern=pat.pattern,
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s", res.intent_type.value, res.confidence, res.is_executable)
                return res

        # 3.5. Bare task-done marker ("Ho gaya", "Done ho gaya") — acknowledgement,
        # never a status query. Caller may offer a suspended-workflow resume.
        if re.fullmatch(r"(?:ho\s+gaya(?:\s+hai)?|done(?:\s+ho\s+gaya)?|kaam\s+ho\s+gaya|ho\s+gaya\s+na)\s*[.!?]?", cleaned):
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.STATEMENT,
                confidence=0.93,
                is_executable=False,
                natural_response=None,
                parameters={"task_done": True},
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s (task-done)", res.intent_type.value, res.confidence, res.is_executable)
            return res

        # 4. Check for Status After Action ("system lock hua?", "Chrome open hua?")
        for pat in cls.STATUS_AFTER_ACTION_PATTERNS:
            m = pat.search(cleaned)
            if m:
                target = ((m.group(1) or "").strip() if m.groups() else "")
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.STATUS_AFTER_ACTION,
                    confidence=0.92,
                    is_executable=False,
                    target=target,
                    matched_pattern=pat.pattern,
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f target=%r exec=%s", res.intent_type.value, res.confidence, target, res.is_executable)
                return res

        # 5. Check for Capability Questions ("kya tum system lock kar sakte ho?", "can you open Chrome?")
        # This MUST take priority over raw command keyword matching.
        is_capability, cap_target, cap_resp, cap_action = cls._detect_capability_question(cleaned, raw_text)
        if is_capability:
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.CAPABILITY_QUESTION,
                confidence=0.95,
                is_executable=False,
                target=cap_target,
                action_type=cap_action,
                natural_response=cap_resp,
                parameters={"proposed_target": cap_target, "proposed_action": cap_action or "open_app"},
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f target=%r exec=%s response=%r", res.intent_type.value, res.confidence, cap_target, res.is_executable, cap_resp)
            return res

        # 5.5. Check for Real-Time Screen Inspection Queries ("screen par kya open hai", "what is on screen", "what is open on my screen")
        if re.search(r"\b(?:screen|desktop|laptop\s+screen)\s+par\s+kya\b|\bwhat(?:\s+is|\s*'s)?\s+(?:(?:open\s+)?on\s+(?:my\s+|the\s+)?screen|on\s+screen)\b", cleaned):
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.ACTION_COMMAND,
                confidence=0.95,
                is_executable=True,
                target="screen",
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f target=%r exec=%s", res.intent_type.value, res.confidence, "screen", res.is_executable)
            return res

        # 5.6. Activity and Past Media Queries ("main ne abhi konsi video dekhi", "maine abhi kya dekha", "abhi konsi video chal rahi thi", "what video was i watching")
        if re.search(
            r"\b(?:main(?:\s*ne)?|maine|humne|i)?\s*(?:abhi|just\s+now|haali\s+mein|last|previous|pichl[aie])?\s*"
            r"(?:kons[ia]|kauns[ia]|kaun\s*s[ia]|which|what)\s+(?:video|gaana|gana|song|movie|track|clip|media)s?\s*"
            r"(?:dekh[aie]?|sun[aie]?|play\s+kar|chal|dekha|suna|dekhi|suni|dekh\s+rah[aie]\s+th[aie]|chal\s+rah[aie]\s+th[aie]|was\s+playing|did\s+i\s+(?:watch|see|listen))\b|"
            r"\b(?:what\s+was\s+i\s+(?:watching|listening\s+to|playing|doing)|what\s+(?:video|song|movie|media)\s+(?:was\s+(?:i\s+)?(?:watching|playing)|was\s+playing|did\s+i\s+(?:watch|see|listen)))\b|"
            r"\b(?:main(?:\s*ne)?|maine)?\s*(?:abhi\s+)?(?:kya\s+(?:dekh[aie]?|dekha|suna|sun[aie]?|kar\s+raha\s+tha)|what\s+did\s+i\s+(?:watch|see))\b|"
            r"\b(?:pichl[aie]|last)\s+(?:video|gaana|gana|song|movie|media)\s+(?:kons[ia]|kauns[ia]|kya\s+(?:tha|thi)|batao|dikhao)\b|"
            r"\b(?:youtube|browser|screen)\s+(?:pe|par|me|mein)\s+(?:abhi\s+)?kya\s+(?:video\s+)?(?:chal|play\s+ho|dekh)\s+rah[aie]\s+th[aie]\b",
            cleaned,
            re.IGNORECASE
        ):
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.ACTION_COMMAND,
                confidence=0.96,
                is_executable=True,
                target="activity",
                action_type="query_media",
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f target=%r exec=%s", res.intent_type.value, res.confidence, "activity", res.is_executable)
            return res

        # 5.8. Browser-Location Queries ("youtube konse browser me hai?", "flipkart kahan open hai?")
        # Must fire BEFORE STATUS_QUESTION_PATTERNS to avoid extracting garbled target strings.
        for pat in cls.BROWSER_LOCATION_PATTERNS:
            m = pat.search(cleaned)
            if m:
                try:
                    site = m.group("site").strip()
                except IndexError:
                    site = m.group(1).strip() if m.groups() else ""
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.STATUS_QUESTION,
                    confidence=0.96,
                    is_executable=False,
                    target=site,
                    parameters={"browser_location_query": True},
                    matched_pattern=pat.pattern,
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=BROWSER_LOCATION conf=%.2f site=%r exec=%s", 0.96, site, False)
                return res

        # 6. Check for Status Questions ("Chrome open hai kya?", "system lock hai kya?")
        for pat in cls.STATUS_QUESTION_PATTERNS:
            m = pat.search(cleaned)
            if m:
                target = m.group(1).strip() if m.groups() else ""
                # Exclude conversational idioms ("kya chal raha hai", "aur batao kya chal raha hai")
                if target.lower() in ("kya", "aur batao kya", "aur batao", "sab", "kuch", "idhar") or "kya chal raha" in cleaned.lower() or "aur batao" in cleaned.lower():
                    continue

                # If target contains browser location noise phrases that slipped through, clean it and mark browser_location_query
                is_loc_q = bool(re.search(r"\b(?:konse|kaun\s+se|kaunse|kis|which|kahan|kidhar)\b", target, re.IGNORECASE)) or bool(re.search(r"\b(?:browser|brouser|browzer|broser)\b", target, re.IGNORECASE))
                params: Dict[str, Any] = {}
                if is_loc_q:
                    clean_t = re.sub(r"\b(?:konse|kaun\s+se|kaunse|kis|which|kahan|kidhar|browser|brouser|browzer|broser|mein|me|par|pe|open|hai|khula)\b", "", target, flags=re.IGNORECASE).strip()
                    if clean_t:
                        target = clean_t
                    params["browser_location_query"] = True

                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.STATUS_QUESTION,
                    confidence=0.93,
                    is_executable=False,
                    target=target,
                    parameters=params,
                    matched_pattern=pat.pattern,
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f target=%r exec=%s", res.intent_type.value, res.confidence, target, res.is_executable)
                return res

        # 6.5. Check for System Information Queries ("cpu usage", "battery percentage", "ram status")
        for pat in cls.SYSTEM_INFO_PATTERNS:
            if pat.search(cleaned):
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.SYSTEM_INFORMATION,
                    confidence=0.93,
                    is_executable=False,
                    target="system",
                    matched_pattern=pat.pattern,
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f target=%r exec=%s", res.intent_type.value, res.confidence, "system", res.is_executable)
                return res

        # 7. Check for Information Questions ("what is Chrome?", "lock kaise karein?")
        for pat in cls.INFORMATION_PATTERNS:
            if pat.search(cleaned):
                # Exclude local Wi-Fi / network password queries from being treated as generic information questions
                is_wifi_pwd_query = bool(re.search(r"\b(?:wifi|wi-fi|network)\s+(?:ka\s+)?password\b", cleaned)) or (
                    bool(re.search(r"\b(?:password|passcode)\b", cleaned)) and bool(re.search(r"\b(?:wifi|wi-fi)\b", cleaned))
                )
                if is_wifi_pwd_query:
                    break
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.INFORMATION_QUESTION,
                    confidence=0.85,
                    is_executable=False,
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s", res.intent_type.value, res.confidence, res.is_executable)
                return res

        # 8. Check for Greetings & Small Talk
        for pat in cls.SMALL_TALK_PATTERNS:
            if pat.search(cleaned):
                from core.response_engine import ResponseEngine, ResponseContext
                resp = ResponseEngine.get_instance().render_response(
                    ResponseContext(user_text=raw_text, intent="SMALL_TALK", speech_act="SMALL_TALK")
                )
                res = ConversationalIntentResult(
                    intent_type=ConversationalIntentType.SMALL_TALK,
                    confidence=0.90,
                    is_executable=False,
                    natural_response=resp,
                    matched_pattern=pat.pattern,
                    raw_input=raw_text,
                    normalized_input=cleaned
                )
                logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s", res.intent_type.value, res.confidence, res.is_executable)
                return res

        # 8.35 Check for Greetings (typo-tolerant, filler-tolerant, speech-act safe)
        is_greet, greet_conf = cls._detect_greeting(cleaned, raw_text)
        if is_greet:
            from core.response_engine import ResponseEngine, ResponseContext
            resp = ResponseEngine.get_instance().render_response(
                ResponseContext(user_text=raw_text, intent="GREETING", speech_act="GREETING")
            )
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.GREETING,
                confidence=greet_conf,
                is_executable=False,
                natural_response=resp,
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s", res.intent_type.value, res.confidence, res.is_executable)
            return res

        # 8.4. Check for Expressed Desires (watching video, listening to music, games, relaxation)
        is_desire, desire_goal, desire_act, desire_resp = cls._detect_expressed_desire(cleaned, raw_text)
        if is_desire:
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.EXPRESSED_DESIRE,
                confidence=0.96,
                is_executable=False,
                target=desire_goal,
                action_type=desire_act,
                natural_response=desire_resp,
                parameters={"goal": desire_goal, "possible_next_action": desire_act},
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f goal=%r response=%r", res.intent_type.value, res.confidence, desire_goal, desire_resp)
            return res

        # 8.45. Check for Future Intention, Scheduled Plan, Future Event, or Temporal Statement
        is_future, f_type, f_goal, f_dt, f_time_disp, f_desc, is_rem_cand, f_resp = cls._detect_future_plan_or_event(cleaned, raw_text)
        if is_future:
            is_exec = (f_type == ConversationalIntentType.ACTION_COMMAND)
            res = ConversationalIntentResult(
                intent_type=f_type,
                confidence=0.95,
                is_executable=is_exec,
                target="reminder" if (is_rem_cand or is_exec) else None,
                action_type="create_reminder" if is_exec else ("offer_reminder" if is_rem_cand else None),
                natural_response=f_resp,
                parameters={
                    "speech_act": f_type.value,
                    "goal": f_goal,
                    "datetime": f_dt,
                    "iso_time": f_dt.astimezone().isoformat() if f_dt else None,
                    "time_display": f_time_disp,
                    "description": f_desc,
                    "reminder_candidate": is_rem_cand,
                    "actionability": "REMINDER_CANDIDATE" if is_rem_cand else "NONE"
                },
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f goal=%r time=%r exec=%s response=%r", res.intent_type.value, res.confidence, f_goal, f_time_disp, res.is_executable, f_resp)
            return res

        # 8.5. Check for Conversational / Body State / Empathy Turns (fatigue, sleep, hunger, small talk)
        is_conv, conv_resp = cls._detect_conversational_turn(cleaned, raw_text)
        if is_conv:
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.CONVERSATION,
                confidence=0.95,
                is_executable=False,
                natural_response=conv_resp,
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s response=%r", res.intent_type.value, res.confidence, res.is_executable, conv_resp)
            return res

        # 9. Check for Action Commands
        # To be an ACTION_COMMAND, the user utterance must contain an actionable directive or imperative verb,
        # and NOT be phrased as a hypothetical, capability, or status inquiry.
        is_action_cmd, act_verb, act_target = cls._detect_action_command(cleaned)
        if is_action_cmd:
            is_indir, _, _, indir_speech_act = cls._detect_indirect_request(cleaned)
            cmd_params = {}
            if is_indir:
                cmd_params["speech_act"] = indir_speech_act
                cmd_params["is_indirect_request"] = True
            res = ConversationalIntentResult(
                intent_type=ConversationalIntentType.ACTION_COMMAND,
                confidence=0.95,
                is_executable=True,
                target=act_target,
                action_type=act_verb,
                parameters=cmd_params,
                raw_input=raw_text,
                normalized_input=cleaned
            )
            logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f target=%r action=%r exec=%s indir=%s", res.intent_type.value, res.confidence, act_target, act_verb, res.is_executable, is_indir)
            return res

        # 10. Default / General Conversation Fallback
        res = ConversationalIntentResult(
            intent_type=ConversationalIntentType.CONVERSATION,
            confidence=0.60,
            is_executable=False,
            natural_response=conv_resp,
            raw_input=raw_text,
            normalized_input=cleaned
        )
        logger.info("[CONVERSATIONAL_INTENT] type=%s conf=%.2f exec=%s", res.intent_type.value, res.confidence, res.is_executable)
        return res

    @classmethod
    def _detect_greeting(cls, cleaned: str, raw_text: str) -> Tuple[bool, float]:
        """
        Robust, typo-tolerant, filler-tolerant greeting detector.
        Follows Section 1-6 safety invariants:
        - Rejects questions, meaning inquiries, capability questions, and content generation.
        - Strips social vocatives / fillers (dear, sir, bro, ji, etc.).
        - Normalizes common greeting typos (moring -> morning, gud -> good, gm -> good morning).
        - Applies fuzzy edit-distance matching for salutation terms.
        """
        # 1. Negative intent safety check (questions, action commands, content generation)
        if cls._GREETING_QUESTION_OR_ACTION_RE.search(cleaned):
            return False, 0.0

        # Also ensure it's not a capability question ("kya tum good morning bol sakte ho", etc.)
        if re.search(r"\b(?:kya\s+tum|can\s+you|could\s+you|are\s+you\s+able)\b", cleaned, re.IGNORECASE):
            return False, 0.0

        # 2. Early normalization
        try:
            from core.semantic.normalizer import HinglishNormalizer
            norm = HinglishNormalizer.normalize_text(cleaned)
        except Exception:
            norm = cleaned

        clean_text = re.sub(r"[?!.,;]+", "", cleaned).strip().lower()
        norm_text = re.sub(r"[?!.,;]+", "", norm).strip().lower()

        words = clean_text.split()
        if len(words) > 5:
            return False, 0.0

        # 3. Direct pattern match against anchor patterns
        for pat in cls.GREETING_PATTERNS:
            if pat.search(clean_text) or pat.search(norm_text):
                return True, 0.95

        # 4. Strip social/filler vocatives and re-check core greeting
        stripped_clean = cls._SOCIAL_FILLERS_RE.sub("", clean_text).strip()
        stripped_clean = re.sub(r"\s+", " ", stripped_clean)
        stripped_norm = cls._SOCIAL_FILLERS_RE.sub("", norm_text).strip()
        stripped_norm = re.sub(r"\s+", " ", stripped_norm)

        for pat in cls.GREETING_PATTERNS:
            if stripped_clean and pat.search(stripped_clean):
                return True, 0.95
            if stripped_norm and pat.search(stripped_norm):
                return True, 0.95

        # 5. Fuzzy matching for greeting tokens (Levenshtein edit distance <= 2)
        check_words = stripped_clean.split() if stripped_clean else words
        if len(check_words) in (1, 2, 3):
            try:
                from brain.spelling_resolver import _levenshtein
                if len(check_words) >= 2 and check_words[0] in ("good", "gud", "gd"):
                    w2 = check_words[1]
                    for anchor in ("morning", "evening", "afternoon", "night"):
                        if abs(len(w2) - len(anchor)) <= 2:
                            if _levenshtein(w2, anchor) <= 2:
                                return True, 0.90
                elif len(check_words) == 1:
                    w1 = check_words[0]
                    for anchor in ("morning", "evening", "afternoon", "hello", "namaste", "pranam"):
                        if abs(len(w1) - len(anchor)) <= 2:
                            if _levenshtein(w1, anchor) <= 1:
                                return True, 0.90
            except Exception:
                pass

        return False, 0.0

    CAPABILITY_GENERAL_RESP_HI = "Ji, bilkul! Main applications open/close kar sakta hoon, reminders set kar sakta hoon, audio/system control, web search aur normal conversations handle kar sakta hoon, Boss."
    CAPABILITY_GENERAL_RESP_EN = "Yes! I can open/close applications, set reminders, control audio/system, web search and handle normal conversations, Boss."

    @classmethod
    def _detect_capability_question(cls, cleaned: str, raw_text: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Detects if the utterance is inquiring about Jarvis's capabilities.
        Returns (is_capability, target, natural_response, action).
        Human-like: bare 'tum kya kar sakte/sakti ho' returns overview;
        'kya tum mere liye vlc open kar sakti ho' returns clean 'VLC'.
        """
        matched = False
        captured_action = ""

        # Check regex capability patterns
        for pat in cls.CAPABILITY_PATTERNS:
            m = pat.search(cleaned)
            if m:
                # Polite stock/share suggestion requests (e.g. "koi share suggest kar sakte ho", "koi achha share bata sakte ho")
                # are direct equity research requests, not abstract capability questions.
                if re.search(r"\b(?:stocks?|shares?|equit(?:y|ies))\b", cleaned, re.I) and any(w in cleaned.lower() for w in ["suggest", "bata", "recommend", "shortlist", "analyze"]):
                    return False, None, None, None
                matched = True
                captured_action = m.group(1).strip() if m.groups() else cleaned
                break

        # Also check common modal phrases (incl. feminine sakti/sakti ho)
        modal_tokens = ["sakte ho", "sakti ho", "sakte hain", "sakti hain", "saktay ho", "kar paoge", "kar paogi", "can you", "could you", "able to"]
        if not matched and any(tok in cleaned for tok in modal_tokens):
            # Check if it starts with kya or can
            if cleaned.startswith("kya ") or cleaned.startswith("can ") or cleaned.startswith("could ") or "kya" in cleaned.split():
                matched = True
                captured_action = cleaned

        if not matched:
            return False, None, None, None

        # Bare general capability inquiry: "tum kya kar sakte ho?", "tum kya kar sakti ho?"
        # -> overview response, never generic "yeh action perform".
        bare_core = re.sub(r"[?!.,]+$", "", cleaned).strip().lower()
        bare_core = re.sub(r"^(?:kya\s+)?(?:tum|aap|jarvis)\s+", "", bare_core).strip()
        bare_core = re.sub(r"^(?:bhai\s+|please\s+|zara\s+)", "", bare_core).strip()
        if bare_core in (
            "kya kar sakte ho", "kya kar sakti ho", "kya kar sakte hain", "kya kar sakti hain",
            "kya kya kar sakte ho", "kya kya kar sakti ho", "kya kar paoge", "kya kar paogi",
            "kar sakte ho", "kar sakti ho",
        ):
            is_en = cleaned.startswith("can you") or cleaned.startswith("could you") or cleaned.startswith("are you able to") or cleaned.startswith("what can you")
            resp = cls.CAPABILITY_GENERAL_RESP_EN if is_en else cls.CAPABILITY_GENERAL_RESP_HI
            return True, "general", resp, "list_capabilities"

        # Resolve which known capability is being asked about
        target_found = None
        action_found = None
        response_text = None

        # Clean captured action from filler words, benefactive phrases and articles.
        # "mere liye vlc open kar sakti ho" -> "vlc open"
        clean_cap = captured_action.lower()
        clean_cap = re.sub(r"\b(?:kya|tum|aap|jarvis|please|zara|bhai|boss|yaar|ji)\b", " ", clean_cap)
        clean_cap = re.sub(r"\b(?:mere\s+liye|mere\s+liy|meri\s+liye|mujhe|mujhko|meri|mera|mere|liye|ke\s+liye|k\s+liye)\b", " ", clean_cap)
        clean_cap = re.sub(r"\b(?:the|a|an)\b", " ", clean_cap)
        clean_cap = re.sub(r"\s+", " ", clean_cap).strip()
        clean_cap_no_art = clean_cap

        for cap_key, cap_data in cls.KNOWN_CAPABILITIES.items():
            for kw in cap_data["keywords"]:
                if kw in clean_cap or kw in clean_cap_no_art or kw in cleaned:
                    target_found = cap_data["target"]
                    action_found = cap_data["action"]
                    # Choose Hindi/English response matching user language
                    is_english = cleaned.startswith("can you") or cleaned.startswith("could you") or cleaned.startswith("are you able to")
                    response_text = cap_data["response_en"] if is_english else cap_data["response_hi"]
                    break
            if target_found:
                break

        if not response_text:
            # Generic capability affirmative if recognizable action verb present
            if any(v in clean_cap for v in ["open", "close", "kholo", "khol", "chalao", "chala", "band", "lock", "play", "set"]):
                # Strip modal/verb noise to isolate clean entity: "vlc open kar sakti ho" -> "vlc"
                noise = {"kar", "karo", "kar sakte", "kholo", "khol", "kholna", "chalao", "chala", "chalana",
                         "sakte", "sakti", "saktey", "ho", "hain", "hai", "open", "close", "kardo", "karke",
                         "sakta", "sakti", "sakto", "sako", "paoge", "paogi", "do", "de", "lijiye"}
                tokens = [t for t in clean_cap.split() if t not in noise and len(t) > 1]
                # Drop stray single letters left from cleaning
                tokens = [t for t in tokens if t not in ("e", "ye", "yh", "mere")]
                if tokens:
                    raw_entity = " ".join(tokens).strip()
                    # Proper display: VLC uppercase, else title-case
                    if raw_entity.lower() in ("vlc", "vlc player"):
                        entity = "VLC"
                    else:
                        entity = raw_entity.title()
                    target_found = raw_entity.lower()
                    action_found = "open_app" if any(v in clean_cap for v in ["open", "kholo", "khol", "chalao", "chala"]) else "handle"
                    response_text = f"Haan, main {entity} open kar sakta hoon."
                else:
                    response_text = "Haan, main yeh kaam kar sakta hoon. Bataiye, kya karna hai?"
            else:
                response_text = cls.CAPABILITY_GENERAL_RESP_HI

        return True, target_found, response_text, action_found

    @classmethod
    def _detect_conversational_turn(cls, cleaned: str, raw_text: str) -> Tuple[bool, Optional[str]]:
        """
        Detects if the utterance is casual conversation, body/emotional state,
        fatigue, empathy, or small talk.
        Returns (is_conversational, natural_response).
        """
        lowered = cleaned.lower()

        # 1. Fatigue / Tiredness ("Today bahut thak gaya hoon", "aaj bahut thak gaya", "tired")
        if any(w in lowered for w in [
            "thak gaya", "thak gayi", "thak gaye", "thakan", "bahut thak",
            "tired", "exhausted", "tiring day", "so tired", "too tired"
        ]):
            return True, "Kaafi tiring day raha lagta hai. Thoda rest kar lijiye."

        # 2. Sleepiness
        if any(w in lowered for w in ["neend aa rahi", "neend aayi", "so raha hoon", "sleepy", "drowsy"]):
            return True, "Aap thak gaye lagte hain, thoda aaram kar lijiye."

        # 3. Hunger / Food
        if any(w in lowered for w in ["bhookh lag", "bhookh lagi", "hungry", "starving"]):
            return True, "Lagta hai aapko bhookh lagi hai, kuch accha kha lijiye."

        # 4. Illness / Pain
        if any(w in lowered for w in ["sir dard", "sar dard", "tabiyat kharab", "headache", "not feeling well", "dard ho raha"]):
            return True, "Apna khayal rakhiye Boss, thoda aaram karein."

        # 5. Stress / Anxiety
        if any(w in lowered for w in ["tension ho rahi", "tension hai", "stress", "mood kharab", "sad hoon", "pareshan hoon"]):
            return True, "Kya hua? Tension mat lijiye, sab theek ho jayega. Thoda relax kijiye."

        # 6. Small Talk / Inquiries (How are you / Kya chal raha hai)
        weather_words = ["weather", "mausam", "baarish", "rain", "temperature", "forecast", "temp", "garmi", "sardi", "thand", "chhatri", "umbrella"]
        is_weather = any(w in lowered for w in weather_words)

        # 6a. User Wellbeing / State Answers ("main achha hun", "theek hun", "sab badhiya", "i'm good")
        wellbeing_positive = [
            "main achha", "main accha", "main theek", "main thik", "main badhiya", "main badiya",
            "ekdam badhiya", "ekdam theek", "ekdam mast", "sab badhiya", "sab theek", "sab thik",
            "sab thik hai", "sab theek hai", "sab sahi",
            "achha hun", "accha hun", "achha hoon", "accha hoon", "theek hun", "theek hoon",
            "thik hun", "thik hoon", "badhiya hoon", "badhiya hun", "mast hoon", "mast hun",
            "i'm good", "i am good", "i'm fine", "i am fine", "doing well", "all good", "all well"
        ]
        is_wellbeing = any(w in lowered for w in wellbeing_positive) or lowered in ("achha", "accha", "theek", "thik", "badhiya", "mast", "fine", "good")
        if is_wellbeing and not is_weather:
            has_reciprocal = bool(re.search(r"(?:tum|aap)\s+(?:batao|sunao|bataiye)|how\s+are\s+you|and\s+you|what\s+about\s+you", raw_text, re.I))
            if has_reciprocal:
                return True, "Yeh sunkar achha laga! Main bhi ekdam badhiya hoon, Sir. Bataiye, aaj kya plan hai?"
            return True, "Yeh sunkar achha laga, Sir! Aur bataiye, aaj kya chal raha hai?"

        # 6b. Reciprocal Questions / Small Talk Continuations ("tum batao", "aur batao", "kya chal raha hai")
        if not is_weather and any(w in lowered for w in [
            "tum batao", "aap batao", "aap bataiye", "tum sunao", "aap sunao", "aur batao", "aur sunao", "what about you", "and you"
        ]):
            return True, "Bas sab badhiya chal raha hai, Sir! Aapki commands ka wait kar raha tha. Bataiye kya karein?"

        # 6c. Boredom / Idle State ("bore ho raha hoon", "kuch khas nahi", "bas aise hi")
        if any(w in lowered for w in ["bore ho raha", "boring lag raha", "i'm bored", "kuch interesting batao"]):
            return True, "Koi baat nahi Sir, thoda refresh ho lijiye! Koi accha music chalaun ya YouTube par kuch interesting dekhna chahenge?"
        if any(w in lowered for w in ["kuch khas nahi", "kuch nahi", "bas aise hi", "nothing much", "not much", "just chilling", "chal raha hai"]):
            return True, "Theek hai Sir, aaram se chill kijiye. Jab bhi meri zaroorat ho, bas batayein!"

        # 6d. General How are you from user to Jarvis
        if not is_weather and (
            any(w in lowered for w in [
                "kaise ho", "how are you", "kya chal raha hai", "kya chal raha",
                "what's up", "whats up", "sab kaisa hai"
            ])
            or bool(re.search(r"\b(?:tu|tum|aap|bhai|jarvis)?\s*kaisa\s+hai\b", lowered))
            or lowered == "kaisa hai"
        ):
            return True, "Main bilkul theek hoon, Boss! Aap batayein, sab kaisa chal raha hai?"

        # 6e. Humorous Banter / Rhetorical Skepticism / Frustration ("tum pagal ho kya?", "pagal ho kya?", "are you crazy?")
        if any(w in lowered for w in [
            "tum pagal ho kya", "pagal ho kya", "pagal ho gaye", "pagal ho gaya", "are you crazy",
            "are you nuts", "dimag kharab hai kya", "bavle ho kya", "satak gaya hai kya",
            "are you out of your mind", "pagal hai kya"
        ]) or bool(re.search(r"\b(?:tum|tu|aap)?\s*(?:pagal|crazy|mental|nuts)\s*(?:ho|hai)?\s*kya\b", lowered)):
            return True, "Nahi Sir, mere circuits bilkul theek chal rahe hain! Bas thoda extra creative ho gaya tha. Bataiye, kya karna hai?"

        # 7. Day Reflection
        if any(w in lowered for w in ["long day", "bada lamba din", "kaafi kaam tha", "busy day", "aaj ka din"]):
            return True, "Samajh sakta hoon Boss, kaafi busy day raha. Ab thoda relax karein."

        # 8. Check HindiVocabEngine for any other body/emotion states
        try:
            from core.semantic.hindi_vocab import HindiVocabEngine
            empathy_resp = HindiVocabEngine.get_empathetic_response(raw_text) or HindiVocabEngine.get_empathetic_response(cleaned)
            if empathy_resp:
                return True, empathy_resp
        except Exception:
            pass

        return False, None

    RE_DESIRE_VIDEO = re.compile(
        r"\b(?:mera\s+)?(?:video|videos|movie|movies|film|filme|youtube|yt|series|show|episode)\s+(?:dekhne|chalaane|chalaney|play\s+karne)\s+ka\s+(?:man|mann|mood)\s*(?:kar\s+raha\s+hai|ho\s+raha\s+hai|hai|tha)?\b|"
        r"\b(?:man|mann|mood)\s+(?:kar\s+raha\s+hai|ho\s+raha\s+hai|hai)\s+(?:ki\s+)?(?:koi\s+)?(?:video|videos|movie|movies|film|youtube)\s+dekh(?:un|oon|ne)?\b|"
        r"\b(?:mujhe\s+)?(?:video|videos|movie|youtube)\s+dekhne\s+ka\s+(?:man|mann|mood)\b|"
        r"\bfeel(?:s)?\s+like\s+watching\s+(?:a\s+)?(?:video|movie|film|youtube)\b|"
        r"\bin\s+(?:the\s+)?mood\s+(?:to\s+|for\s+)(?:watch|see)\s+(?:a\s+)?(?:video|movie|film|youtube)\b",
        re.IGNORECASE
    )
    RE_DESIRE_MUSIC = re.compile(
        r"\b(?:mera\s+)?(?:gaana|gana|gaane|gane|song|songs|music|sangeet)\s+(?:sunne|chalaane|play\s+karne)\s+ka\s+(?:man|mann|mood)\s*(?:kar\s+raha\s+hai|ho\s+raha\s+hai|hai|tha)?\b|"
        r"\b(?:man|mann|mood)\s+(?:kar\s+raha\s+hai|ho\s+raha\s+hai|hai)\s+(?:ki\s+)?(?:koi\s+)?(?:gaana|gana|song|music)\s+sun(?:un|oon|ne)?\b|"
        r"\b(?:kuch\s+)?(?:bajane|bajane\s+ka)\s+man\b|"
        r"\bfeel(?:s)?\s+like\s+listening\s+to\s+(?:some\s+)?(?:music|songs?|audio)\b|"
        r"\bin\s+(?:the\s+)?mood\s+(?:to\s+listen\s+to|for)\s+(?:some\s+)?(?:music|songs?)\b",
        re.IGNORECASE
    )
    RE_DESIRE_GAME = re.compile(
        r"\b(?:mera\s+)?(?:koi\s+)?(?:game|games)\s+(?:khelne|play\s+karne)\s+ka\s+(?:man|mann|mood)\s*(?:kar\s+raha\s+hai|ho\s+raha\s+hai|hai|tha)?\b|"
        r"\b(?:man|mann|mood)\s+(?:kar\s+raha\s+hai|ho\s+raha\s+hai|hai)\s+(?:ki\s+)?(?:koi\s+)?(?:game)\s+khel(?:un|oon|ne)?\b|"
        r"\bfeel(?:s)?\s+like\s+playing\s+(?:a\s+)?game\b",
        re.IGNORECASE
    )
    RE_DESIRE_RELAX = re.compile(
        r"\b(?:thoda\s+)?(?:relax|aaram|chill|rest)\s+karne\s+ka\s+(?:man|mann|mood)\s*(?:kar\s+raha\s+hai|ho\s+raha\s+hai|hai|tha)?\b|"
        r"\bfeel(?:s)?\s+like\s+(?:relaxing|taking\s+a\s+break|resting)\b",
        re.IGNORECASE
    )

    @classmethod
    def _detect_expressed_desire(cls, cleaned: str, raw_text: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Detects user conversational desires and personal intent.
        Returns (is_desire, goal, possible_action, natural_response).
        """
        # 1. Video / YouTube / Movies
        if cls.RE_DESIRE_VIDEO.search(cleaned):
            return True, "WATCH_VIDEO", "OFFER_VIDEO/YOUTUBE", "Bataiye kya dekhna chahte hain? Main YouTube open kar doon ya koi specific video chalaun?"

        # 2. Music / Songs
        if cls.RE_DESIRE_MUSIC.search(cleaned):
            return True, "LISTEN_MUSIC", "OFFER_MUSIC/SPOTIFY", "Kaunsa gaana sunna chahenge? Main Spotify ya YouTube Music open kar doon?"

        # 3. Games
        if cls.RE_DESIRE_GAME.search(cleaned):
            return True, "PLAY_GAME", "OFFER_GAME", "Kaunsa game khelna chahenge? Batayein main launch kar doon."

        # 4. Relaxation / Rest
        if cls.RE_DESIRE_RELAX.search(cleaned):
            return True, "RELAX", "OFFER_RELAXATION", "Bilkul, thoda aaram kar lijiye. Main koi soothing music chalaun ya system quiet mode mein daal doon?"

        return False, None, None, None

    @classmethod
    def _detect_explicit_negation(cls, cleaned: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Enforces the Negation Invariant:
        Identifies explicitly negated user desires and instructions.
        Examples:
        - "Chrome mat kholo" -> (True, "open", "chrome")
        - "Chrome nahi kholna" -> (True, "open", "chrome")
        - "Maine Chrome nahi bola" -> (True, "statement", "chrome")
        - "Usko band mat karo" -> (True, "close", "usko")
        - "Nahi, mujhe woh nahi chahiye" -> (True, "request", "woh")
        - "Don't open Chrome" -> (True, "open", "chrome")
        """
        # Pattern 1: <target> mat/nahi <verb> or mat/nahi <verb> <target>
        m1 = re.search(r"^(?:(.+?)\s+)?(?:mat|nahi)\s+(kholo|chalao|karo|open|close|band\s+karo)(?:\s+(.+?))?$", cleaned)
        if m1:
            target = (m1.group(1) or m1.group(3) or "").strip()
            verb = m1.group(2).strip()
            target = re.sub(r"\b(?:ko|par|pe|bhai|please|yaar)\b", "", target).strip()
            return True, verb, target or None

        # Pattern 2: <target> nahi/mat <verb>na (e.g. "Chrome nahi kholna", "abhi nahi karna")
        m2 = re.search(r"^(?:(.+?)\s+)?(?:nahi|mat)\s+(kholna|chalana|karna|open\s+karna|band\s+karna)(?:\s+(.+?))?$", cleaned)
        if m2:
            target = (m2.group(1) or m2.group(3) or "").strip()
            verb = m2.group(2).strip()
            target = re.sub(r"\b(?:ko|par|pe|bhai|please|yaar)\b", "", target).strip()
            return True, verb, target or None

        # Pattern 3: band mat/nahi karo / close mat/nahi karo
        m3 = re.search(r"^(?:(.+?)\s+)?(?:band|close)\s+(?:mat|nahi)\s+karo(?:\s+(.+?))?$", cleaned)
        if m3:
            target = (m3.group(1) or m3.group(2) or "").strip()
            target = re.sub(r"\b(?:ko|par|pe|bhai|please|yaar)\b", "", target).strip()
            return True, "close", target or None

        # Pattern 3b: mat/nahi band karo
        m3b = re.search(r"^(?:(.+?)\s+)?(?:mat|nahi)\s+(?:band\s+karo|close\s+karo|band|close)(?:\s+(.+?))?$", cleaned)
        if m3b:
            target = (m3b.group(1) or m3b.group(2) or "").strip()
            target = re.sub(r"\b(?:ko|par|pe|bhai|please|yaar)\b", "", target).strip()
            return True, "close", target or None

        # Pattern 4: English don't / do not <verb> <target>
        m4 = re.search(r"^(?:don'?t|do\s+not|never)\s+(open|close|launch|start|stop|lock)\s+(.+)$", cleaned)
        if m4:
            verb = m4.group(1).strip()
            target = m4.group(2).strip()
            return True, verb, target

        # Pattern 5: "maine <target> nahi bola" / "maine chrome nahi bola tha"
        m5 = re.search(r"^maine\s+(.+?)\s+nahi\s+bola(?:tha)?$", cleaned)
        if m5:
            target = m5.group(1).strip()
            return True, "statement", target

        # Pattern 6: "nahi mujhe woh nahi chahiye" / "nahi chahiye"
        if re.search(r"\b(?:nahi\s+chahiye|woh\s+nahi\s+chahiye|mujhe\s+(?:woh\s+)?nahi\s+chahiye)\b", cleaned):
            return True, "request", "target"

        return False, None, None

    @classmethod
    def _detect_state_dispute_or_contradiction(
        cls, cleaned: str, raw_text: str, active_context: Optional[Any] = None
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Detects user contradictions, state disputes, and negations regarding open status.
        Examples:
        - "lekin Chrome mein to open YouTube Nahin Hai" -> (True, "youtube", "chrome", "NOT_OPEN")
        - "par Chrome mein to YouTube open nahi hai" -> (True, "youtube", "chrome", "NOT_OPEN")
        - "par Chrome mein to open nahi hai YouTube" -> (True, "youtube", "chrome", "NOT_OPEN")
        - "lekin YouTube to open nahi hai" -> (True, "youtube", None, "NOT_OPEN")
        - "par YouTube open nahi hai" -> (True, "youtube", None, "NOT_OPEN")
        - "lekin open to nahi hai" -> (True, None, None, "NOT_OPEN")
        - "par open nahi hai" -> (True, None, None, "NOT_OPEN")
        - "par khula nahi hai" -> (True, None, None, "NOT_OPEN")
        - "but YouTube is not open in Chrome" -> (True, "youtube", "chrome", "NOT_OPEN")
        - "but it is not open" -> (True, None, None, "NOT_OPEN")

        Returns: (is_dispute, target, container, condition)
        """
        # Exclude questions asking whether something is open ("open nahi hai kya?", "open hai ya nahi?")
        if cleaned.endswith("?") or "kya" in cleaned.split() or "ya nahi" in cleaned:
            return False, None, None, None

        # Pattern 1b: [Container] mein [to]? [open]? nahi hai [Target]
        # Catches: "par Chrome mein to open nahi hai YouTube", "Chrome mein nahi hai YouTube"
        m1b = re.search(
            r"\b(?:lekin|magar|kintu|parantu|par|arre\s+lekin|but|however)?\s*"
            r"(?:(?:in|mein|me)\s+)?(?P<container>[a-zA-Z0-9_\-\.]+)\s+(?:mein|me|pe|par)\s+"
            r"(?:to\s+)?(?:open\s+|khula\s+|running\s+|chalu\s+)?"
            r"(?:nahi|nahin|nhi|not)\s+hai\s+"
            r"(?P<target>[a-zA-Z0-9_\-\.]+)\b",
            cleaned,
            re.IGNORECASE
        )
        if m1b:
            container = m1b.group("container").strip().lower()
            target = m1b.group("target").strip().lower()
            return True, target, container, "NOT_OPEN"

        # Pattern 1: [Discourse Marker]? [Container] mein to [open]? [Target] [to]? [open]? nahi/not hai
        # Catches: "lekin Chrome mein to open YouTube Nahin Hai", "Chrome mein to YouTube open nahi hai",
        #          "par chrome mein to open youtube nahi hai"
        m1 = re.search(
            r"\b(?:lekin|magar|kintu|parantu|par|arre\s+lekin|but|however)?\s*"
            r"(?:(?:in|mein|me)\s+)?(?P<container>[a-zA-Z0-9_\-\.]+)\s+(?:mein|me|pe|par)\s+"
            r"(?:to\s+)?(?:open\s+|khula\s+|running\s+|chalu\s+)?"
            r"(?P<target>[a-zA-Z0-9_\-\.]+)\s+"
            r"(?:to\s+)?(?:open\s+|khula\s+|running\s+|chalu\s+)?"
            r"(?:nahi|nahin|nhi|not)\s+hai\b",
            cleaned,
            re.IGNORECASE
        )
        if m1:
            container = m1.group("container").strip().lower()
            target = m1.group("target").strip().lower()
            if target in ("open", "khula", "running", "chalu", "to", "bhi", "yeh", "ye"):
                target = None
            if container in ("open", "khula", "running", "chalu", "to", "bhi"):
                container = None
            return True, target, container, "NOT_OPEN"

        # Pattern 2: [Discourse Marker]? [Target] [to]? [Container] mein [open]? nahi/not hai
        # Catches: "YouTube Chrome mein open nahi hai", "YouTube to Chrome mein open nahi hai",
        #          "par YouTube Chrome mein nahi hai"
        m2 = re.search(
            r"\b(?:lekin|magar|kintu|parantu|par|arre\s+lekin|but|however)?\s*"
            r"(?P<target>[a-zA-Z0-9_\-\.]+)\s+(?:to\s+)?"
            r"(?P<container>[a-zA-Z0-9_\-\.]+)\s+(?:mein|me|pe|par)\s+"
            r"(?:to\s+)?(?:open\s+|khula\s+|running\s+|chalu\s+)?"
            r"(?:nahi|nahin|nhi|not)\s+hai\b",
            cleaned,
            re.IGNORECASE
        )
        if m2:
            target = m2.group("target").strip().lower()
            container = m2.group("container").strip().lower()
            if target not in ("ye", "yeh", "this", "it", "to", "bhi"):
                return True, target, container, "NOT_OPEN"

        # Pattern 3: [Discourse Marker] [Target] [to]? [open]? nahi/not hai
        # Catches: "lekin YouTube to open nahi hai", "par YouTube open nahi hai", "lekin Chrome nahi khula hai"
        m3 = re.search(
            r"\b(?:lekin|magar|kintu|parantu|par|arre\s+lekin|but|however)\s+"
            r"(?:bhai\s+)?(?:to\s+)?"
            r"(?P<target>[a-zA-Z0-9_\-\.]+)\s+"
            r"(?:to\s+)?(?:open\s+|khula\s+|running\s+|chalu\s+)?"
            r"(?:to\s+)?(?:nahi|nahin|nhi|not)\s+hai\b",
            cleaned,
            re.IGNORECASE
        )
        if m3:
            target = m3.group("target").strip().lower()
            if target not in ("open", "khula", "running", "chalu", "ye", "yeh", "this", "it", "to", "bhi"):
                return True, target, None, "NOT_OPEN"

        # Pattern 4: [Discourse Marker] [to]? [open/khula/running] [to]? [nahi/not hai] (anaphoric dispute)
        # Catches: "lekin open to nahi hai", "par open nahi hai", "par khula to nahi hai", "lekin chalu nahi hai"
        m4 = re.search(
            r"\b(?:lekin|magar|kintu|parantu|par|arre\s+lekin|but|however)\s+"
            r"(?:to\s+)?(?:open|khula|running|chalu)\s+(?:to\s+)?(?:nahi|nahin|nhi|not)\s+hai\b",
            cleaned,
            re.IGNORECASE
        )
        if m4:
            ctx_target = getattr(active_context, "website", None) or getattr(active_context, "application", None)
            return True, ctx_target, None, "NOT_OPEN"

        # Pattern 5: English: "but [target] is not open [in container]" / "but it is not open"
        m5 = re.search(
            r"\b(?:but|however)\s+(?:(?:(?:it|this|that)\s+is\s+not\s+(?:open|running))|"
            r"(?:(?P<target>[a-zA-Z0-9_\-\.]+)\s+is\s+not\s+(?:open|running)(?:\s+in\s+(?P<container>[a-zA-Z0-9_\-\.]+))?))\b",
            cleaned,
            re.IGNORECASE
        )
        if m5:
            target = m5.group("target").strip().lower() if m5.group("target") else None
            container = m5.group("container").strip().lower() if m5.group("container") else None
            return True, target, container, "NOT_OPEN"

        # Pattern 6: Direct user objection / contradiction marker with negation:
        # e.g. "lekin open kahan hai", "par khula kidhar hai"
        if re.search(r"\b(?:lekin|magar|kintu|parantu|par|arre\s+lekin|but|however)\b", cleaned, re.IGNORECASE):
            if re.search(r"\b(?:open\s+kahan|open\s+kidhar|khula\s+kahan|khula\s+kidhar|kahan\s+open|kidhar\s+open)\b", cleaned, re.IGNORECASE):
                ctx_target = getattr(active_context, "website", None) or getattr(active_context, "application", None)
                return True, ctx_target, None, "NOT_OPEN"

        return False, None, None, None

    @classmethod
    def _detect_pragmatic_statement(cls, cleaned: str, raw_text: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Detects pragmatic human statements (e.g. "Yaar bahut garmi hai")
        where the user may be expressing a situational state that warrants
        clarification rather than premature execution.
        Returns: (is_pragmatic, goal, clarification_prompt, stated_condition)
        """
        # Exclude direct questions ("garmi hai kya?", "aaj garmi kyu hai?")
        if cleaned.endswith("?") or "kya" in cleaned.split() or "kyun" in cleaned.split():
            return False, None, None, None

        if re.search(r"\b(?:bahut\s+garmi\s+hai|bohot\s+garmi|garmi\s+lag\s+rahi|it'?s\s+(?:so\s+)?hot)\b", cleaned):
            return True, "COOL_ENVIRONMENT", "AC chala doon?", "USER_STATED = HOT"

        if re.search(r"\b(?:bahut\s+thand\s+hai|bohot\s+thand|thand\s+lag\s+rahi|it'?s\s+(?:so\s+)?cold)\b", cleaned):
            return True, "WARM_ENVIRONMENT", "Heater chala doon?", "USER_STATED = COLD"

        if re.search(r"\b(?:bahut\s+andhera\s+hai|andhera\s+hai|kuch\s+dikh\s+nahi\s+raha|it'?s\s+(?:too\s+)?dark)\b", cleaned):
            return True, "INCREASE_LIGHT", "Lights on kar doon?", "USER_STATED = DARK"

        return False, None, None, None

    @classmethod
    def _detect_indirect_request(cls, cleaned: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Detects polite indirect requests and suggestions for application/action control:
        - "Chrome khol doge?" -> (True, "open", "chrome", "REQUEST")
        - "Mujhe Chrome chahiye" -> (True, "open", "chrome", "REQUEST")
        - "Chrome mil sakta hai?" -> (True, "open", "chrome", "REQUEST")
        - "Chalo Chrome" / "Chrome pe chalte hain" -> (True, "open", "chrome", "SUGGESTION")
        - "Zara Chrome laga do" / "Chrome kar do" -> (True, "open", "chrome", "COMMAND")
        - "Please open Chrome" / "Would you open Chrome?" -> (True, "open", "chrome", "REQUEST")
        """
        low = cleaned.strip()

        # 1. "Chrome khol doge?" / "<app> khol doge" / "<app> open kar doge"
        m_doge = re.search(r"^(?:zara\s+|bhai\s+|please\s+)?([a-zA-Z0-9_\-\.]+)\s+(?:khol\s+doge|open\s+kar\s+doge|chala\s+doge|laga\s+doge)\??$", low)
        if m_doge:
            return True, "open", m_doge.group(1).strip(), "REQUEST"

        # 2. "Mujhe <app> chahiye" / "<app> chahiye"
        m_chahiye = re.search(r"^(?:mujhe\s+|humein\s+)?([a-zA-Z0-9_\-\.]+)\s+chahiye\??$", low)
        if m_chahiye:
            target = m_chahiye.group(1).strip()
            if target not in ("kuch", "help", "madad", "waqt", "time"):
                return True, "open", target, "REQUEST"

        # 3. "<app> mil sakta hai?" / "kya <app> mil sakta hai?"
        m_mil = re.search(r"^(?:kya\s+)?([a-zA-Z0-9_\-\.]+)\s+mil\s+sakta\s+hai\??$", low)
        if m_mil:
            target = m_mil.group(1).strip()
            if target not in ("kuch", "help", "madad"):
                return True, "open", target, "REQUEST"

        # 4. "Chalo <app>" / "chalo <app> pe" / "<app> pe chalte hain"
        m_chalo = re.search(r"^chalo\s+([a-zA-Z0-9_\-\.]+)(?:\s+pe|\s+par)?$", low)
        if m_chalo:
            return True, "open", m_chalo.group(1).strip(), "SUGGESTION"
        m_chalte = re.search(r"^([a-zA-Z0-9_\-\.]+)\s+pe\s+chalte\s+hain$", low)
        if m_chalte:
            return True, "open", m_chalte.group(1).strip(), "SUGGESTION"

        # 5. "Zara <app> laga do" / "<app> laga do"
        m_laga = re.search(r"^(?:zara\s+|bhai\s+)?([a-zA-Z0-9_\-\.]+)\s+laga\s+do$", low)
        if m_laga:
            return True, "open", m_laga.group(1).strip(), "COMMAND"

        # 6. "<app> kar do" (e.g. "Chrome kar do")
        m_kardo = re.search(r"^(?:zara\s+|bhai\s+)?([a-zA-Z0-9_\-\.]+)\s+kar\s+do$", low)
        if m_kardo:
            target = m_kardo.group(1).strip()
            if target in ("chrome", "excel", "notepad", "brave", "edge", "spotify", "calculator"):
                return True, "open", target, "COMMAND"

        # 7. "Would you open <app>?" / "Please open <app>"
        m_would = re.search(r"^(?:would\s+you\s+(?:please\s+)?open|please\s+open)\s+([a-zA-Z0-9_\-\.]+)\??$", low)
        if m_would:
            return True, "open", m_would.group(1).strip(), "REQUEST"

        return False, None, None, None

    # Leading Hindi discourse markers: "to open karo" (= then open it), "toh khol do", "tab band karo".
    # NOTE: "phir/fir" deliberately NOT stripped — bare "phir se karo" means REPEAT
    # (handled by contextual repeat), not discourse ellipsis.
    _LEADING_DISCOURSE_RE = re.compile(
        r"^(?:(?:toh|to|tu|tab|achha|acha|accha|theek\s+hai|thik\s+hai|haan\s+to|chalo)\s*[,]*\s*)+",
        re.IGNORECASE,
    )
    _ELLIPSIS_ONLY_TARGETS = frozenset({
        "", "to", "toh", "tu", "tab", "phir", "fir", "ye", "yeh", "woh", "vo",
        "usko", "isko", "isse", "usse", "it", "that", "this", "karo",
    })
    # Praise preamble: "ye to bahut achhi baat hai, to open kar ke dikhao" -> command part only.
    _PRAISE_PREAMBLE_RE = re.compile(
        r"^(?:ye|yeh)\s+(?:(?:to|toh)\s+)?(?:(?:bahut|bohot)\s+)?(?:achhi|acchi|acha|achha|badhiya|sahi)\s+(?:baat\s+hai|bat\s+hai)\s*[,]*\s*",
        re.IGNORECASE,
    )
    # Demonstration suffix: "open kar ke dikhao" / "khol kar dikhao" / "khol karke dikha"
    # -> base command (execute + show). Strict: only with dikhao-family verb.
    _DEMO_SUFFIX_RE = re.compile(
        r"\s*\b(?:kar\s+ke|karke|kar|ke)\s+(?:dikhao|dikha\s+do|dikha|dikhaiye|dikhai)\s*\??$",
        re.IGNORECASE,
    )

    @classmethod
    def _detect_action_command(cls, cleaned: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Determines if the utterance is an imperative action directive.
        Returns (is_action_command, action_verb, target).
        Human-like: strips leading Hindi discourse ('to open karo' -> 'open karo'
        with ellipsis target None so caller inherits last discussed target e.g. VLC).
        """
        # Capability inquiries are always handled separately (incl. feminine + colloquial saktey)
        if any(m in cleaned for m in ["sakte ho", "sakti ho", "saktey ho", "sakte hain", "sakti hain", "saktay ho", "kar paoge", "kar paogi", "can you", "could you", "able to"]):
            return False, None, None

        # Strip praise preamble ("ye to bahut achhi baat hai, ...") and demonstration
        # suffix ("... open kar ke dikhao" -> "... open") before verb detection.
        tmp = cls._PRAISE_PREAMBLE_RE.sub("", cleaned.strip()).strip()
        tmp = cls._DEMO_SUFFIX_RE.sub("", tmp).strip()
        # Strip leading Hindi discourse markers for ellipsis commands ("to open karo")
        working = cls._LEADING_DISCOURSE_RE.sub("", tmp).strip()
        if not working:
            working = cleaned.strip()
        discourse_stripped = working != cleaned.strip()

        # Expressed desires (man kar raha hai, mood hai) are conversational, NOT imperative commands
        if any(w in cleaned for w in ["man kar raha", "mann kar raha", "mood hai", "man hai", "mann hai", "man ho raha", "feel like", "mann ho raha"]):
            return False, None, None

        # Social conversation lead-ins (e.g. "ek baat batao", "mujhe ek cheez poochni hai", "suno")
        if re.search(r"^(?:ek\s+baat\s+batao|mujhe\s+ek\s+cheez\s+poochni\s+hai|suno|sun)(?:\s+na)?\??$", cleaned):
            return False, None, None

        # Check for Wi-Fi and network credential retrieval commands
        is_wifi_pwd = bool(re.search(r"\b(?:wifi|wi-fi|network)\s+(?:ka\s+)?password\b", cleaned)) or (
            bool(re.search(r"\b(?:password|passcode)\b", cleaned)) and bool(re.search(r"\b(?:wifi|wi-fi)\b", cleaned))
        )
        if is_wifi_pwd:
            return True, "copy_wifi_password", "network"

        # Ellipsis Volume check: "volume 50", "50 volume"
        m_vol = re.search(r"^(?:ab\s+)?(?:set\s+)?volume\s+(\d+)$", cleaned)
        if m_vol:
            return True, "set_volume", f"volume {m_vol.group(1)}"
        m_vol2 = re.search(r"^(\d+)\s+volume$", cleaned)
        if m_vol2:
            return True, "set_volume", f"volume {m_vol2.group(1)}"

        # Ellipsis Close check: "ab band karo"
        m_close_el = re.search(r"^(?:ab\s+)?band\s+karo$", working)
        if m_close_el:
            return True, "close", "current"

        # Ellipsis Open check after discourse stripping: "to open karo" / "toh khol do"
        # Return target None so the caller inherits last discussed target (e.g. VLC).
        m_open_el = re.search(r"^(?:open|khol|kholo|chala|chalao|chala\s+do|open\s+kar|khol\s+do)\s*(?:karo|kar\s+do|do|de)?$", working, re.IGNORECASE)
        if m_open_el and discourse_stripped:
            verb_el = m_open_el.group(0).split()[0].lower()
            return True, verb_el, None

        # Check for Indirect Requests & Polite Commands
        is_indir, ind_verb, ind_target, _ = cls._detect_indirect_request(working)
        if is_indir:
            return True, ind_verb, ind_target

        # Exclude questions and status inquiries explicitly
        if (
            cleaned.endswith("?")
            or "hai kya" in cleaned
            or "kya tum" in cleaned
            or "kya aap" in cleaned
        ):
            return False, None, None

        # Negation Invariant: Imperative action commands NEVER contain negation particles.
        # ("Chrome mat kholo", "open nahi hai", "lekin Chrome mein to open YouTube Nahin Hai")
        if re.search(r"\b(?:nahi|nahin|nhi|mat|not|never|don'?t)\b", cleaned, re.IGNORECASE):
            return False, None, None

        # Contradiction / Dispute Invariant: Utterances with contradiction markers
        # disputing prior assertions or asking why/where/how cannot be action commands.
        if re.search(r"\b(?:lekin|magar|kintu|parantu|par\s+bhai|lekin\s+bhai|arre\s+lekin|but|however)\b", cleaned, re.IGNORECASE):
            if re.search(r"\b(?:nahi|nahin|nhi|mat|not|kahan|kidhar|galat|kaise|kyun|kyu|why)\b", cleaned, re.IGNORECASE):
                return False, None, None

        # Check for direct commands using precompiled patterns first
        for pat, act, def_tgt in cls._COMPILED_DIRECT_CMDS:
            m = pat.match(working)
            if m:
                tgt = m.group(1).strip() if (m.groups() and m.group(1)) else def_tgt
                if tgt is not None and tgt.strip().lower() in cls._ELLIPSIS_ONLY_TARGETS:
                    return True, act, None
                return True, act, tgt

        # Check for direct imperative verbs using unified precompiled regex
        m_verb = cls._IMPERATIVE_VERBS_RE.search(working)
        if m_verb:
            verb = m_verb.group(1).lower()
            target = cls._IMPERATIVE_VERBS_RE.sub('', working).strip()
            target = cls._FILLERS_RE.sub('', target).strip()
            target = cls._WHITESPACE_RE.sub(' ', target)
            # Strip residual leading discourse inside target ("to" leftovers)
            target = cls._LEADING_DISCOURSE_RE.sub("", target).strip()
            target = re.sub(r"\s+", " ", target).strip(" ,.")
            if not target or target.lower() in cls._ELLIPSIS_ONLY_TARGETS:
                return True, verb, None
            return True, verb, target or None

        return False, None, None

    @classmethod
    def _detect_complaint_with_action(cls, cleaned: str, raw_text: str) -> Optional[Tuple[str, str]]:
        """
        Detects complaint-about-prior-promise carrying an implicit action:
        'abhi tum ne bola tha ki vlc open kar sakte ho to open kyun nahi kartey'
        -> ('open', 'vlc'). Returns None when no actionable target found.
        """
        low = cleaned.lower()
        has_promise_marker = any(m in low for m in ["bola tha", "bole the", "kaha tha", "kahi thi", "kaha ti", "bolatha", "ne bola", "tum ne"])
        if not has_promise_marker:
            return None
        has_open_verb = any(v in low for v in ["open", "khol", "kholo", "chala", "chalao", "start", "launch"])
        if not has_open_verb:
            return None
        # Extract app target: prefer known apps, else generic noun before open verb
        known_apps = ["vlc", "chrome", "brave", "edge", "firefox", "excel", "word", "notepad",
                      "calculator", "spotify", "youtube", "whatsapp", "camera", "settings", "paint"]
        for app in known_apps:
            if re.search(rf"\b{re.escape(app)}\b", low):
                verb = "open"
                if re.search(r"\b(?:band|close)\b", low):
                    verb = "close"
                return verb, app
        m_app = re.search(r"\bki\s+([a-z]{2,20})\s+(?:open|khol|chala)", low)
        if m_app:
            cand = m_app.group(1).strip()
            if cand not in ("to", "ye", "woh", "tum", "main"):
                return "open", cand
        return None

    @classmethod
    def _resolve_troubleshooting_response(cls, cleaned: str) -> str:
        """
        Provides helpful diagnostic troubleshooting response without re-executing action.
        """
        try:
            from core.knowledge.it import get_it_knowledge_engine
            it_eng = get_it_knowledge_engine()
            guide = it_eng.troubleshooting_store.match_guide(cleaned)
            if guide:
                is_hi = it_eng._is_hindi_or_hinglish(cleaned)
                return it_eng._format_troubleshooting_response(guide, is_hi)
        except Exception:
            pass

        if "lock" in cleaned:
            return "System lock na hone ke kuch reasons ho sakte hain: shayad Windows workstation lock policy disabled hai, ya koi process foreground input lock kar rahi hai."
        elif "chrome" in cleaned or "browser" in cleaned:
            return "Chrome open na hone ke reasons ho sakte hain: background mein koi crashed chrome process pehle se chal rahi ho, ya installation path accessible na ho."
        elif "volume" in cleaned or "awaz" in cleaned:
            return "Audio volume adjust na hone ka kaaran audio driver busy hona ya correct playback device select na hona ho sakta hai."
        return "Lagta hai is command mein koi rukawat aa rahi hai. Aap ek baar manually check kar sakte hain ya exact error dekh sakte hain."

    RE_EXPLICIT_REMINDER = re.compile(
        r"\b(?:yaad\s+dilana|yaad\s+dila\s+do|yaad\s+dila\s+dena|yaad\s+dilao|yaad\s+rakhna|remind\s+me|reminder\s+set|reminder\s+lagao|reminder\s+laga\s+do|set\s+(?:a\s+)?reminder)\b",
        re.IGNORECASE
    )

    RE_QUESTION_MARKERS = re.compile(
        r"\b(?:kya\s+mujhe|kya\s+main|kya\s+meri|do\s+i|should\s+i|is\s+there)\b|\b(?:hai\s+kya|hogi\s+kya|hoga\s+kya)\b|\?$",
        re.IGNORECASE
    )

    RE_PAST_MARKERS = re.compile(
        r"\b(?:tha|thi|gaya\s+tha|gayi\s+thi|gaye\s+the|kiya\s+tha|ki\s+thi|kiye\s+the|raha\s+tha|rahi\s+thi|rahe\s+the|yesterday|last\s+(?:week|month|year|night)|already)\b|(?:\b(?:ho|gaye|kiye|rahe|chuke)\s+the\b)",
        re.IGNORECASE
    )

    RE_FUTURE_INTENTION = re.compile(
        r"\b(?:mujhe|humein|mera|mere|main|hum)\b.*?\b(?:j[a]+na\s+hai|nikalna\s+hai|kar(?:na|ni|ne)\s+hai|a[a]+na\s+hai|pahunchna\s+hai|kholna\s+hai|dekhna\s+hai|lena\s+hai|dena\s+hai|milna\s+hai)\b|"
        r"\b(?:j[a]+na\s+hai|nikalna\s+hai|kar(?:na|ni|ne)\s+hai|attend\s+kar(?:na|ni|ne)\s+hai|submit\s+kar(?:na|ni|ne)\s+hai|a[a]+na\s+hai|pahunchna\s+hai)\b|"
        r"\b(?:main|hum)\b.*?\b(?:j[a]+unga|j[a]+ungi|jaenge|karunga|karungi|karenge|niklunga|niklenge|khaaunga|khaunga|khaaungi|khaungi|dekhunga|milunga|aunga|aaunga)\b|"
        r"\b(?:i\s+have\s+to|i\s+need\s+to|i\s+will|i'm\s+going\s+to|i\s+am\s+going\s+to|i\s+plan\s+to|gotta|have\s+to\s+leave|have\s+to\s+go)\b",
        re.IGNORECASE
    )

    RE_FUTURE_EVENT = re.compile(
        r"\b(?:\w+\s+)?(?:meeting|call|webinar|class|session|appointment|interview|flight|train|match|event|exam|demo|presentation|review)\s+(?:hai|honi\s+hai|hoga|hogi|scheduled\s+hai)\b|"
        r"\b(?:is\s+(?:the|a)?\s*(?:\w+\s+)?(?:meeting|call|webinar|class|session|appointment|interview|flight|train|match|event|exam|demo|presentation|review))\b|"
        r"\b(?:there\s+is|there's|have)\s+(?:a\s+)?(?:\w+\s+)?(?:meeting|call|webinar|class|session|appointment|interview|flight|train|match|event|exam|demo|presentation|review)\b",
        re.IGNORECASE
    )

    @classmethod
    def _extract_temporal_anchor(cls, text: str) -> Tuple[Optional[datetime], Optional[str]]:
        """
        Extracts temporal anchor (datetime and clean display string) from utterance.
        Supports both absolute clock times and relative durations ('5 minut baad', '10 minute baad').
        Reuses TimeContext for local timezone resolution.
        """
        from core.time_context import get_time_context
        tc = get_time_context()
        now = tc.now()

        low = text.lower().strip()

        # 0. Check for relative deltas ("5 minut baad", "10 minute baad", "in 5 minutes", "aadhe ghante baad", "1 ghanta baad")
        HINDI_NUMS = {
            "ek": 1, "do": 2, "teen": 3, "chaar": 4, "char": 4, "paanch": 5, "panch": 5,
            "chhe": 6, "che": 6, "chhah": 6, "saat": 7, "aath": 8, "ath": 8, "nau": 9,
            "das": 10, "dus": 10, "gyarah": 11, "barah": 12, "terah": 13, "chaudah": 14,
            "pandrah": 15, "solah": 16, "satrah": 17, "atharah": 18, "unnees": 19, "bees": 20,
            "pachees": 25, "pachchis": 25, "tees": 30, "paintees": 35, "chaalis": 40,
            "paintaalis": 45, "pachaas": 50
        }

        rel_delta = None
        rel_display = None
        if re.search(r'\b(?:aadha\s+ghanta|aadhe\s+ghante|half\s+an\s+hour|half\s+hour)\b', low):
            rel_delta = timedelta(minutes=30)
            rel_display = "30 minute baad"
        elif re.search(r'\b(?:dedh\s+ghanta|dedh\s+ghante)\b', low):
            rel_delta = timedelta(minutes=90)
            rel_display = "1 ghanta 30 minute baad"
        elif re.search(r'\b(?:paun\s+ghanta|paun\s+ghante)\b', low):
            rel_delta = timedelta(minutes=45)
            rel_display = "45 minute baad"
        elif re.search(r'\b(?:sawa\s+ghanta|sawa\s+ghante)\b', low):
            rel_delta = timedelta(minutes=75)
            rel_display = "1 ghanta 15 minute baad"
        elif re.search(r'\b(?:thodi\s+der\s+baad|thoda\s+time\s+baad)\b', low):
            rel_delta = timedelta(minutes=10)
            rel_display = "10 minute baad"
        elif re.search(r'\b(?:ek\s+do\s+minute|couple\s+of\s+minutes)\b', low):
            rel_delta = timedelta(minutes=2)
            rel_display = "2 minute baad"
        else:
            num_pattern = r'(?:\d+|' + '|'.join(HINDI_NUMS.keys()) + r')'
            m_rel = re.search(
                rf'\b(?:(?:in|after)\s+)?({num_pattern})\s*'
                r'(minute|minutes|minut|minuts|mint|mints|min|mins|second|seconds|sec|secs|ghante|ghanta|ghanto|hour|hours|hr|hrs|din|days?)\b'
                r'(?:\s*(?:baad|ke\s+baad|later|mein|me))?',
                low
            )
            if m_rel:
                matched_str = m_rel.group(0)
                is_explicit_rel = bool(re.search(r'\b(?:baad|later|in|after|mein|me)\b', matched_str))
                has_rel_context = is_explicit_rel or any(w in low for w in ["yaad", "remind", "reminder", "baad", "after", "later"])
                if has_rel_context:
                    val_str = m_rel.group(1).lower()
                    qty = int(val_str) if val_str.isdigit() else HINDI_NUMS.get(val_str, 0)
                    unit = m_rel.group(2).lower()
                    if qty > 0:
                        if unit.startswith("sec"):
                            rel_delta = timedelta(seconds=qty)
                            rel_display = f"{qty} second baad"
                        elif unit.startswith("din") or unit.startswith("day"):
                            rel_delta = timedelta(days=qty)
                            rel_display = f"{qty} din baad"
                        elif unit.startswith("ghant") or unit.startswith("hour") or unit.startswith("hr"):
                            rel_delta = timedelta(hours=qty)
                            rel_display = f"{qty} ghante baad"
                        else:
                            rel_delta = timedelta(minutes=qty)
                            rel_display = f"{qty} minute baad"

        if rel_delta is not None:
            target_dt = now + rel_delta
            disp_clock = target_dt.strftime("%I:%M %p").lstrip("0")
            full_display = f"{rel_display} ({disp_clock})"
            return target_dt, full_display

        is_kal = bool(re.search(r'\b(?:kal|tomorrow)\b', low))
        is_parso = bool(re.search(r'\b(?:parso|day\s+after\s+tomorrow)\b', low))
        day_prefix = "Kal " if is_kal else ("Parso " if is_parso else "")
        day_prefix_en = "tomorrow at " if is_kal else ""

        target_hour = None
        target_minute = 0
        time_display = None

        # 1. Check for 12h time with AM/PM (e.g. "1:30 PM", "1.30 PM", "1 30 pm", "4:00 PM", "10 am")
        # Handle cases where colon was removed by normalizer: "1 30 pm"
        m_ampm = re.search(r'\b(\d{1,2})(?:[:\.](\d{2})|\s+(\d{2}))?\s*(am|pm)\b', low)
        if m_ampm:
            orig_h = int(m_ampm.group(1))
            min_str = m_ampm.group(2) or m_ampm.group(3)
            min_val = int(min_str) if min_str else 0
            if 1 <= orig_h <= 12 and 0 <= min_val <= 59:
                target_hour = orig_h
                target_minute = min_val
                period = m_ampm.group(4).upper()
                if period == "PM" and target_hour < 12:
                    target_hour += 12
                elif period == "AM" and target_hour == 12:
                    target_hour = 0
                fmt_min = f":{target_minute:02d}" if (target_minute or min_str) else ""
                time_display = f"{day_prefix}{orig_h}{fmt_min} {period}".strip()

        # 2. Check for period + time (e.g. "shaam 6 baje", "dopahar 1:30", "dopahar 1 30", "subah 8 baje")
        if not time_display:
            m_period = re.search(r'\b(subah|dopahar|shaam|raat)\s*(?:ke\s*)?(\d{1,2})(?:[:\.](\d{2})|\s+(\d{2}))?\s*(?:baje)?\b', low)
            if m_period:
                part = m_period.group(1).lower()
                orig_h = int(m_period.group(2))
                min_str = m_period.group(3) or m_period.group(4)
                min_val = int(min_str) if min_str else 0
                if 1 <= orig_h <= 12 and 0 <= min_val <= 59:
                    target_minute = min_val
                    if part in ("shaam", "raat", "dopahar") and orig_h < 12:
                        target_hour = orig_h + 12
                    elif part == "subah" and orig_h == 12:
                        target_hour = 0
                    else:
                        target_hour = orig_h
                    fmt_min = f":{target_minute:02d}" if target_minute else ""
                    time_display = f"{day_prefix}{part} {orig_h}{fmt_min} baje".strip()

        # 3. Check for standalone "baje" (e.g. "1:30 baje", "1 30 baje", "2 baje")
        if not time_display:
            m_baje = re.search(r'\b(\d{1,2})(?:[:\.](\d{2})|\s+(\d{2}))?\s*baje\b', low)
            if m_baje:
                orig_h = int(m_baje.group(1))
                min_str = m_baje.group(2) or m_baje.group(3)
                min_val = int(min_str) if min_str else 0
                if 1 <= orig_h <= 12 and 0 <= min_val <= 59:
                    target_minute = min_val
                    if orig_h <= 6:
                        target_hour = orig_h + 12
                    else:
                        target_hour = orig_h
                    fmt_min = f":{target_minute:02d}" if target_minute else ""
                    time_display = f"{day_prefix}{orig_h}{fmt_min} baje".strip()

        # 4. Check for English "at <time>" (e.g. "at 4:00", "at 4 PM", "at 1 30 pm")
        if not time_display:
            m_at = re.search(r'\bat\s*(\d{1,2})(?:[:\.](\d{2})|\s+(\d{2}))?\s*(am|pm)?\b', low)
            if m_at:
                orig_h = int(m_at.group(1))
                min_str = m_at.group(2) or m_at.group(3)
                min_val = int(min_str) if min_str else 0
                if 1 <= orig_h <= 12 and 0 <= min_val <= 59:
                    target_minute = min_val
                    p_str = m_at.group(4).upper() if m_at.group(4) else ""
                    if p_str == "PM" and orig_h < 12:
                        target_hour = orig_h + 12
                    elif p_str == "AM" and orig_h == 12:
                        target_hour = 0
                    else:
                        target_hour = orig_h + 12 if orig_h <= 6 else orig_h
                    fmt_p = f" {p_str}" if p_str else ""
                    fmt_min = f":{target_minute:02d}" if (target_minute or min_str) else ""
                    time_display = f"{day_prefix_en}{orig_h}{fmt_min}{fmt_p}".strip()

        if target_hour is None or not (0 <= target_hour <= 23) or not (0 <= target_minute <= 59):
            return None, None

        target_date = now.date()
        if is_kal:
            target_date += timedelta(days=1)
        elif is_parso:
            target_date += timedelta(days=2)
        else:
            cand = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            if cand <= now:
                target_date += timedelta(days=1)

        dt_obj = now.replace(
            year=target_date.year,
            month=target_date.month,
            day=target_date.day,
            hour=target_hour,
            minute=target_minute,
            second=0,
            microsecond=0
        )
        return dt_obj, time_display

    @classmethod
    def _extract_task_description(cls, text: str) -> Optional[str]:
        """
        Extracts a clean, human-readable task description from a natural reminder / plan utterance.
        e.g. "mujhe 7 PM pe ghar jaana hai" -> "Ghar jaana"
             "kal 10 baje rohit se milna hai" -> "Rohit se milna"
             "5 minut baad mujhe yaad dilana ki mujhe paani pina hai" -> "paani peene"
             "remind me at 5 pm to call mom" -> "Call mom"
        """
        raw = text.strip()
        cleaned = re.sub(r"[?!.,]+$", "", raw).strip()
        low = cleaned.lower()

        # 1. Check explicit "to <task>" or "ki <task>"
        m_explicit = re.search(r'\b(?:ki|to|for|about)\s+(.+)$', low)
        if m_explicit and any(w in low[:m_explicit.start()] for w in ["remind", "yaad", "reminder"]):
            cand = cleaned[m_explicit.start():].strip()
            cand = re.sub(r'^(?:ki|to|for|about)\s+', '', cand, flags=re.I).strip()
            # Strip leading subject / pronoun / modal phrases from task clause
            cand = re.sub(r'^(?:mujhe|humein|main|hum|mera|mere|meri|i\s+have\s+to|i\s+need\s+to|i\s+want\s+to|i\s+must|i\s+should|i\'m\s+going\s+to|i\s+am\s+going\s+to)\s+', '', cand, flags=re.I).strip()
            cand = re.sub(r'\s+(?:hai|hoga|hogi|tha|thi|the)$', '', cand, flags=re.I).strip()
            # Normalize natural activity phrasings
            if re.match(r'^(?:paani|pani)\s+pina$', cand, re.I):
                cand = "paani peene"
            if cand and len(cand) >= 2:
                return cand

        # 2. Strip temporal phrases (e.g. "7 pm", "7:00 pm", "7 baje", "10 minute baad", "kal", "aaj", "parso")
        pattern_time = (
            r'\b(?:\d+|ek|do|teen|chaar|char|paanch|panch|chhe|che|saat|aath|nau|das|dus|pandrah|bees|tees|aadha|aadhe|dedh)\s*'
            r'(?:minute|minutes|minut|minuts|mint|mints|min|mins|second|seconds|sec|secs|ghante|ghanta|ghanto|hour|hours?|hrs|din|days?)\s*'
            r'(?:baad|ke\s+baad|mein|me|later|after)?\b|'
            r'\b(?:kal|aaj|parso|today|tomorrow|yesterday|day\s+after\s+tomorrow)\b|'
            r'\b(?:subah|shaam|dopahar|raat|morning|evening|afternoon|night)\b|'
            r'\b(?:\d{1,2}(?:[:\.]\d{2})?\s*(?:am|pm)|\d{1,2}\s*baje)\b|'
            r'\b(?:pe|par|ko|ke\s+liye|at|around|sharp|on)\b'
        )
        task_str = re.sub(pattern_time, ' ', cleaned, flags=re.I)

        # 3. Strip subject / intent preamble phrases
        pattern_prefix = (
            r'^\s*(?:mujhe|humein|main|hum|mera|mere|meri|i\s+have\s+to|i\s+need\s+to|i\s+want\s+to|'
            r"i'm\s+going\s+to|i\s+am\s+going\s+to|i\s+will|i\s+plan\s+to|gotta|have\s+to|"
            r'remind\s+me|reminder\s+lagao|reminder\s+laga\s+do|reminder\s+set\s+karo|set\s+a\s+reminder|'
            r'yaad\s+dilana|yaad\s+dila\s+dena|yaad\s+dila\s+do|yaad\s+rakhna|'
            r'kripya|please|bhai|boss)\b'
        )
        task_str = re.sub(pattern_prefix, ' ', task_str, flags=re.I).strip()

        # 4. Strip trailing reminder markers and auxiliary verbs
        task_str = re.sub(
            r'\s+(?:yaad\s+dilana|yaad\s+dila\s+dena|yaad\s+dila\s+do|yaad\s+dilao|yaad\s+rakhna|'
            r'ka\s+reminder\s+lagao|ka\s+reminder\s+laga\s+do|ka\s+reminder\s+set\s+karo|'
            r'reminder\s+lagao|reminder\s+laga\s+do|reminder\s+set\s+karo|remind\s+me)\b',
            '', task_str, flags=re.I
        ).strip()
        task_str = re.sub(r'\s+(?:hai|hogi|hoga|tha|thi|the)$', '', task_str, flags=re.I).strip()
        task_str = re.sub(r'\s+', ' ', task_str).strip()

        if re.match(r'^(?:paani|pani)\s+pina$', task_str, re.I):
            task_str = "paani peene"

        if task_str and len(task_str) >= 3 and not task_str.isdigit():
            return task_str
        return None

    @classmethod
    def _classify_plan_goal(cls, text: str) -> Tuple[str, str]:
        """
        Derives canonical goal and task description from natural utterance.
        """
        low = text.lower()
        extracted_desc = cls._extract_task_description(text)
        if extracted_desc:
            extracted_desc = extracted_desc[0].upper() + extracted_desc[1:]

        if any(w in low for w in ["paani", "pani", "water"]):
            goal = "DRINK_WATER"
            desc = extracted_desc or "Paani peene"
        elif any(w in low for w in ["ghar", "home"]):
            goal = "GO_HOME"
            desc = extracted_desc or "Ghar jaana"
        elif any(w in low for w in ["khana", "lunch", "dinner", "breakfast", "nashta", "food", "eat"]):
            goal = "GO_TO_EAT"
            default_desc = "Khana khane jaana" if any(w in low for w in ["khana", "eat", "food"]) else ("Lunch" if "lunch" in low else "Dinner")
            desc = default_desc
        elif any(w in low for w in ["meeting", "call", "zoom", "client", "sync"]):
            goal = "ATTEND_MEETING"
            desc = extracted_desc or "Meeting"
        elif any(w in low for w in ["doctor", "clinic", "hospital", "checkup", "medicine", "dawa"]):
            goal = "DOCTOR_APPOINTMENT"
            desc = extracted_desc or "Doctor appointment"
        elif any(w in low for w in ["gym", "workout", "exercise", "kasrat", "running", "run"]):
            goal = "GYM_WORKOUT"
            desc = extracted_desc or "Gym jaana"
        elif any(w in low for w in ["office", "work", "dukan", "shop"]):
            goal = "GO_TO_WORK"
            desc = extracted_desc or "Office nikalna"
        elif any(w in low for w in ["flight", "train", "station", "airport", "bus"]):
            goal = "TRAVEL_LEAVE"
            desc = extracted_desc or "Travel"
        elif any(w in low for w in ["sleep", "sona", "rest", "aaram"]):
            goal = "REST_SLEEP"
            desc = extracted_desc or "Rest"
        else:
            goal = "SCHEDULED_PLAN"
            desc = extracted_desc or "Scheduled task"
        return goal, desc

    @classmethod
    def _detect_future_plan_or_event(
        cls, cleaned: str, raw_text: str
    ) -> Tuple[bool, Optional[ConversationalIntentType], Optional[str], Optional[datetime], Optional[str], Optional[str], bool, Optional[str]]:
        """
        Discovers future personal intentions, scheduled events, explicit reminder commands,
        information questions about schedules, and temporal statements.
        Returns:
            (matched, intent_type, goal, datetime, time_display, description, reminder_candidate, natural_response)
        """
        low = cleaned.lower()

        # 1. Check for explicit reminder directive
        if cls.RE_EXPLICIT_REMINDER.search(low):
            dt_obj, time_display = cls._extract_temporal_anchor(cleaned)
            goal, desc = cls._classify_plan_goal(cleaned)
            return True, ConversationalIntentType.ACTION_COMMAND, "CREATE_REMINDER", dt_obj, time_display, desc or "Reminder", True, None

        # 2. Check for question asking about scheduled status / obligation
        if cls.RE_QUESTION_MARKERS.search(cleaned) or (low.endswith("?") and any(w in low for w in ["jaana", "karna", "meeting", "plan", "hai"])):
            dt_obj, time_display = cls._extract_temporal_anchor(cleaned)
            if time_display or any(w in low for w in ["jaana", "nikalna", "meeting"]):
                time_part = f"{time_display} par " if time_display else ""
                resp = f"Maine check kiya, {time_part}aapka koi scheduled task ya reminder set nahi hai."
                return True, ConversationalIntentType.STATUS_QUESTION, "STATUS_INQUIRY", dt_obj, time_display, "Schedule inquiry", False, resp

        # 3. Check for past statement
        if cls.RE_PAST_MARKERS.search(low):
            dt_obj, time_display = cls._extract_temporal_anchor(cleaned)
            if time_display:
                return True, ConversationalIntentType.STATEMENT, "PAST_RECORD", dt_obj, time_display, "Past statement", False, "Theek hai Boss, note kar liya."

        # 3.5. Indirect wake-up intent ("mujhe kal subah jaldi uthna hai" -> alarm offer)
        if re.search(r"\b(?:jaldi\s+)?uthna\s+hai\b|\buth\s+jana\s+hai\b|\bwake\s+me\s+up\b", low) and "?" not in cleaned:
            dt_obj, time_display = cls._extract_temporal_anchor(cleaned)
            if time_display:
                return True, ConversationalIntentType.FUTURE_INTENTION, "WAKE_UP", dt_obj, time_display, "Subah uthna (alarm)", True, None
            return True, ConversationalIntentType.FUTURE_INTENTION, "WAKE_UP", None, None, "Subah uthna (alarm)", False, None

        # 4. Check for personal future intention
        m_intent = cls.RE_FUTURE_INTENTION.search(low)
        if m_intent:
            dt_obj, time_display = cls._extract_temporal_anchor(cleaned)
            goal, desc = cls._classify_plan_goal(cleaned)
            if time_display:
                is_en = any(low.startswith(w) for w in ["i have to", "i will", "i need to", "i'm going to", "there is", "tomorrow"])
                resp = f"Alright. Should I set a reminder for {time_display}?" if is_en else f"Theek hai. {time_display} par yaad dila du?"
                return True, ConversationalIntentType.FUTURE_INTENTION, goal, dt_obj, time_display, desc, True, resp
            else:
                # Future intention without specific time
                resp = "Theek hai Boss! Agar kisi specific time par yaad dilana ho toh batayein."
                return True, ConversationalIntentType.FUTURE_INTENTION, goal, None, None, desc, False, resp

        # 5. Check for future external/scheduled event
        m_event = cls.RE_FUTURE_EVENT.search(low)
        if m_event:
            dt_obj, time_display = cls._extract_temporal_anchor(cleaned)
            goal, desc = cls._classify_plan_goal(cleaned)
            if time_display:
                is_en = any(low.startswith(w) for w in ["there is", "there's", "tomorrow", "have a"])
                resp = f"Alright. Should I set a reminder for {time_display}?" if is_en else f"Theek hai. {time_display} par yaad dila du?"
                return True, ConversationalIntentType.FUTURE_EVENT, goal, dt_obj, time_display, desc, True, resp
            else:
                resp = "Theek hai Boss, event note kar liya."
                return True, ConversationalIntentType.FUTURE_EVENT, goal, None, None, desc, False, resp

        return False, None, None, None, None, None, False, None
