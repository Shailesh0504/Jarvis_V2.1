# brain/conversation/classifier.py
"""
High-Precision Conversational Intent & Command Boundary Classifier.
Strictly separates executable tool/plugin commands from natural conversational dialogue,
and supports compound request extraction (conversational preamble + actionable command).
"""

from dataclasses import dataclass
import logging
import re
from typing import List, Optional, Tuple

from .intents import ConversationalIntent
from .normalizer import ConversationNormalizer
from .registry import ConversationIntentRegistry

logger = logging.getLogger("jarvis.brain.conversation.classifier")


@dataclass
class ClassificationResult:
    """Detailed classification output with confidence, ambiguity, and compound command split."""
    intent: ConversationalIntent
    confidence: float
    is_command: bool
    is_ambiguous: bool = False
    clarification_prompt: Optional[str] = None
    matched_pattern: Optional[str] = None
    actionable_command: Optional[str] = None
    conversational_prefix: Optional[str] = None


class ConversationClassifier:
    """
    Semantic Intent Classifier for Jarvis V2.
    Integrates the Intent Registry, semantic parser checks, command boundaries,
    and compound utterance splitting.
    """

    _registry = ConversationIntentRegistry()

    # Explicit command triggers that represent actual tool actions
    COMMAND_ACTION_TRIGGERS = [
        r'\bkholo\b', r'\bopen\b', r'\blaunch\b', r'\bstart\b',
        r'\bchalao\b', r'\bplay\b', r'\bbajao\b', r'\bstream\b',
        r'\bband\s+karo\b', r'\bclose\b', r'\bkill\b', r'\bterminate\b',
        r'\bsearch\s+karo\b', r'\bdhoondo\b',
        r'\bvolume\b', r'\bawaz\b', r'\bbrightness\b',
        r'\bscreenshot\b', r'\brecord\b', r'\bmute\b', r'\bunmute\b',
        r'\bshutdown\b', r'\brestart\b', r'\block\s+pc\b', r'\bsystem\s+lock\b',
        r'\bsuggest\b', r'\brecommend\b', r'\bshortlist\b', r'\banalyze\b', r'\bscan\b',
        r'\bbatao\b', r'\bbata\b', r'\bbataiye\b', r'\bbuy\b', r'\bkharid\b'
    ]

    # Explicit system entities that represent tools/apps/domains
    COMMAND_ENTITIES = [
        "excel", "chrome", "brave", "firefox", "edge", "vlc", "notepad", "calculator",
        "calc", "spotify", "vscode", "vs code", "terminal", "powershell", "cmd",
        "camera", "paint", "whatsapp", "control panel", "task manager", "taskmgr",
        "stock", "stocks", "share", "shares", "equity", "equities", "nifty", "sensex"
    ]

    @classmethod
    def get_registry(cls) -> ConversationIntentRegistry:
        return cls._registry

    @classmethod
    def extract_compound_command(cls, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Splits compound statements like 'achha weather to theek hai par Chrome khol do'
        into (chat_prefix, actionable_command).
        """
        match = re.search(
            r'^(.*?)(?:,\s*|\s+par\s+|\s+lekin\s+|\s+aur\s+saath\s+me\s+|\s+but\s+|\s+and\s+also\s+)([a-zA-Z0-9_\s]+(?:khol\s+do|kholo|open|launch|chalao|play|band\s+karo|close|dhoondo|calculate).*)$',
            text,
            re.IGNORECASE
        )
        if match:
            prefix = match.group(1).strip()
            command = match.group(2).strip()
            if prefix and command:
                return prefix, command
        return None, None

    @classmethod
    def classify(cls, text: str, has_active_dialogue: bool = False) -> ConversationalIntent:
        """
        Backward-compatible classification method returning ConversationalIntent.
        """
        res = cls.classify_detailed(text, has_active_dialogue=has_active_dialogue)
        return res.intent

    @classmethod
    def classify_detailed(cls, text: str, has_active_dialogue: bool = False) -> ClassificationResult:
        """
        Full semantic classification distinguishing Commands vs Conversational Intents vs Ambiguity.
        """
        if not text or not text.strip():
            return ClassificationResult(
                intent=ConversationalIntent.GENERAL_CHAT,
                confidence=0.0,
                is_command=False
            )

        raw_text = text.strip()
        cleaned = ConversationNormalizer.clean(raw_text)

        # 0. Check for Compound Conversational + Actionable Command
        chat_pre, act_cmd = cls.extract_compound_command(raw_text)
        if act_cmd:
            return ClassificationResult(
                intent=ConversationalIntent.COMMAND,
                confidence=0.95,
                is_command=True,
                actionable_command=act_cmd,
                conversational_prefix=chat_pre
            )

        # 1. Corrections & Complaints take highest conversational precedence (e.g. "Nahi, mera matlab...", "Pehle kyon nahi listen kar rahi thi?")
        corr_match = cls._registry.match(cleaned)
        if corr_match.intent in (
            ConversationalIntent.CORRECTION,
            ConversationalIntent.USER_COMPLAINT_FEEDBACK,
            ConversationalIntent.CRITICISM_LISTENING,
            ConversationalIntent.COMPLAINT,
        ) and corr_match.confidence >= 0.75:
            return ClassificationResult(
                intent=corr_match.intent,
                confidence=corr_match.confidence,
                is_command=False,
                matched_pattern=corr_match.matched_pattern
            )

        # 2. Interruption / Dismissal checks
        if corr_match.intent in (ConversationalIntent.INTERRUPTION_WAIT, ConversationalIntent.DISMISSAL_CANCEL) and corr_match.confidence >= 0.8:
            return ClassificationResult(
                intent=corr_match.intent,
                confidence=corr_match.confidence,
                is_command=False,
                matched_pattern=corr_match.matched_pattern
            )

        # 3. Check for specific everyday conversational patterns first before command parsing:
        # e.g. "main abhi khana khane ja raha hoon", "kya tum meri baat sun rahe ho?", "kaise ho", "kya kar rahe ho"
        if corr_match.intent in (
            ConversationalIntent.ACTIVITY_UPDATE,
            ConversationalIntent.LISTENING_CHECK,
            ConversationalIntent.GREETING,
            ConversationalIntent.FAREWELL,
            ConversationalIntent.HOW_ARE_YOU,
            ConversationalIntent.USER_STATE_UPDATE,
            ConversationalIntent.STATUS_CHECK,
            ConversationalIntent.HELP_INQUIRY,
            ConversationalIntent.GRATITUDE,
            ConversationalIntent.APOLOGY,
            ConversationalIntent.WELCOME_NO_PROBLEM,
            ConversationalIntent.JOKE,
            ConversationalIntent.STORY,
            ConversationalIntent.EMOTIONAL_MOOD,
            ConversationalIntent.OPINION_REQUEST,
            ConversationalIntent.EXPLANATION_REQUEST,
            ConversationalIntent.CONVERSATION_START,
            ConversationalIntent.UNCERTAINTY_CONFUSION,
            ConversationalIntent.USER_COMPLAINT_FEEDBACK,
            ConversationalIntent.CRITICISM_LISTENING,
            ConversationalIntent.COMPLAINT,
        ) and corr_match.confidence >= 0.7:
            return ClassificationResult(
                intent=corr_match.intent,
                confidence=corr_match.confidence,
                is_command=False,
                matched_pattern=corr_match.matched_pattern
            )

        # 4. Check for explicit system/tool commands keywords
        for kw in [
            "status", "plugin", "plugins", "remember", "favorite", "favourite", "screenshot",
            "screen", "window", "windows", "display",
            "calculate", "average", "organize", "duplicate", "report", "clean", "workflow",
            "excel", "chrome", "brave", "firefox", "edge", "vlc", "notepad", "calc",
            "calculator", "spotify", "code", "system", "cpu", "ram", "battery",
            "shutdown", "restart", "reboot", "mute", "unmute", "volume", "brightness",
            "record", "search", "dhoondo", "list", "sales report", "sheet", "time", "date",
            "stock", "stocks", "share", "shares", "equity", "equities", "nifty", "sensex"
        ]:
            if re.search(r'\b' + re.escape(kw) + r'\b', cleaned):
                # Disambiguate casual chit-chat
                if not any(w in cleaned for w in ["kaise ho", "kya haal", "joke", "mood", "sun rahe ho"]):
                    return ClassificationResult(
                        intent=ConversationalIntent.COMMAND,
                        confidence=0.95,
                        is_command=True
                    )

        # 5. Check Core Brain Semantic Parser (Media, Math, Location, Window Management, App Launch)
        from brain.semantic_parser import HinglishNLUParser
        semantic_act = HinglishNLUParser.parse(raw_text)
        if semantic_act:
            return ClassificationResult(
                intent=ConversationalIntent.COMMAND,
                confidence=1.0,
                is_command=True,
                matched_pattern=semantic_act.intent
            )

        # 6. Check if user sentence is an explicit tool command via action verbs + entities
        has_action = any(re.search(pat, cleaned) for pat in cls.COMMAND_ACTION_TRIGGERS)
        has_entity = any(re.search(r'\b' + re.escape(ent) + r'\b', cleaned) for ent in cls.COMMAND_ENTITIES)
        if has_action and has_entity:
            return ClassificationResult(
                intent=ConversationalIntent.COMMAND,
                confidence=0.9,
                is_command=True
            )

        # 7. Check Continuation / Wh-questions / Acknowledgements in Registry
        if corr_match.confidence >= 0.5:
            return ClassificationResult(
                intent=corr_match.intent,
                confidence=corr_match.confidence,
                is_command=False,
                matched_pattern=corr_match.matched_pattern
            )

        # 8. Check if user is asking a natural question
        if ConversationNormalizer.is_question(raw_text):
            return ClassificationResult(
                intent=ConversationalIntent.EXPLANATION_REQUEST,
                confidence=0.7,
                is_command=False
            )

        # 9. Ambiguity & Clarification
        words = cleaned.split()
        if len(words) >= 1 and corr_match.confidence < 0.4:
            if has_active_dialogue:
                return ClassificationResult(
                    intent=ConversationalIntent.GENERAL_CHAT,
                    confidence=0.5,
                    is_command=False
                )
            return ClassificationResult(
                intent=ConversationalIntent.GENERAL_CHAT,
                confidence=0.3,
                is_command=False,
                is_ambiguous=True,
                clarification_prompt="Aap kis baare mein baat kar rahe hain, Boss?"
            )

        # 10. Fallback General Conversation
        return ClassificationResult(
            intent=ConversationalIntent.GENERAL_CHAT,
            confidence=0.6,
            is_command=False
        )
