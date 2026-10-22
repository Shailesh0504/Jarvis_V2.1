# core/semantic/lexicon.py
"""
Local Vocabulary & Dictionary Intelligence Layer for Jarvis V2.1.

Understands common English words, Hindi/Hinglish words, synonyms, phrases,
abbreviations, and variations without relying on rigid keyword matching.

Core Invariant:
The vocabulary layer provides semantic understanding (ActionConcept, TargetDomain,
Extracted Entities, Normalized Concepts) but does NOT itself decide the final intent
without context.

Examples:
- "restart", "reboot", "restart the PC", "reboot my computer", "system ko restart karo", "PC dobara start karo"
  all provide ActionConcept.SYSTEM_RESTART on TargetDomain.SYSTEM -> resolves to SYSTEM_RESTART in context.
- "open", "launch", "start", "chalao", "khol do"
  all provide ActionConcept.OPEN_APPLICATION / OPEN_TARGET -> maps to OPEN_APP in context when target is an app.
"""

import functools
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class ActionConcept(str, Enum):
    """Normalized action concept across English and Hindi/Hinglish."""
    OPEN_APPLICATION   = "OPEN_APPLICATION"
    OPEN_TARGET        = "OPEN_TARGET"
    CLOSE_TARGET       = "CLOSE_TARGET"
    SYSTEM_RESTART     = "SYSTEM_RESTART"
    SYSTEM_SHUTDOWN    = "SYSTEM_SHUTDOWN"
    SYSTEM_LOCK        = "SYSTEM_LOCK"
    SYSTEM_SLEEP       = "SYSTEM_SLEEP"
    SYSTEM_MAINTENANCE = "SYSTEM_MAINTENANCE"
    PLAY_MEDIA         = "PLAY_MEDIA"
    SEARCH_TARGET      = "SEARCH_TARGET"
    STATUS_QUERY       = "STATUS_QUERY"
    UNKNOWN            = "UNKNOWN"


class TargetDomain(str, Enum):
    """Domain category of the entity being acted upon."""
    SYSTEM      = "SYSTEM"       # PC, computer, laptop, machine, Windows
    APPLICATION = "APPLICATION"  # Installed software, tools, apps
    WEBSITE     = "WEBSITE"      # Domains, URLs, web portals
    FILE        = "FILE"         # Files, documents, spreadsheets
    FOLDER      = "FOLDER"       # Directories, folders
    MEDIA       = "MEDIA"        # Songs, music, video, movies
    WINDOW      = "WINDOW"       # Windows, tabs
    UNKNOWN     = "UNKNOWN"


@dataclass
class LexicalAnalysis:
    """Detailed linguistic and semantic breakdown of an utterance."""
    raw_text: str
    normalized_text: str
    action_concept: ActionConcept
    target_domain: TargetDomain
    target_candidate: Optional[str] = None
    action_phrase: Optional[str] = None
    target_phrase: Optional[str] = None
    is_restart: bool = False
    is_open: bool = False
    is_close: bool = False
    is_shutdown: bool = False
    is_system_target: bool = False
    confidence: float = 1.0
    synonyms_used: Dict[str, str] = field(default_factory=dict)


class LexiconEngine:
    """
    Local vocabulary and lexicon intelligence engine.
    High performance, deterministic O(1) hash lookups with multi-word phrase matching.
    """

    # -----------------------------------------------------------------------
    # 1. Abbreviations & Jargon Mapping
    # -----------------------------------------------------------------------
    ABBREVIATIONS: Dict[str, str] = {
        "pc": "computer",
        "calc": "calculator",
        "ppt": "powerpoint",
        "doc": "word",
        "docs": "word",
        "xls": "excel",
        "xlsx": "excel",
        "yt": "youtube",
        "wa": "whatsapp",
        "bt": "bluetooth",
        "wifi": "wi-fi",
        "cmd": "command prompt",
        "ps": "powershell",
        "vol": "volume",
        "mic": "microphone",
        "cam": "camera",
        "msg": "message",
        "msgs": "messages",
        "app": "application",
        "apps": "applications",
        "microsft": "microsoft",
    }

    # -----------------------------------------------------------------------
    # 2. System Target Terminology (English + Hindi/Hinglish)
    # -----------------------------------------------------------------------
    SYSTEM_TERMS: Set[str] = {
        "pc", "computer", "system", "laptop", "machine", "workstation",
        "desktop", "device", "windows", "my pc", "my computer", "the pc",
        "the computer", "apna computer", "mera pc", "apna pc", "apna system",
        "mera computer", "is computer", "is pc", "ye pc", "ye computer",
    }

    # -----------------------------------------------------------------------
    # 3. Action Synonyms & Multi-word Phrases
    # -----------------------------------------------------------------------
    # Restart phrases across English, Hindi, Hinglish
    RESTART_PHRASES: List[str] = [
        "dobara start karo", "dobara start kar do", "dobara start kardo",
        "dobara start", "dobara shuru karo", "dobara shuru kar do",
        "phir se start karo", "phir se start kar do", "phir se start",
        "phir se shuru karo", "phir se shuru", "phir start karo",
        "wapas start karo", "wapas start kar do", "wapas start",
        "wapas shuru karo", "restart karo", "restart kar do", "restart kardo",
        "restart kijiye", "reboot karo", "reboot kar do", "reboot kardo",
        "reboot kijiye", "restart the pc", "restart the computer",
        "reboot the pc", "reboot the computer", "restart my pc",
        "restart my computer", "reboot my pc", "reboot my computer",
        "start again", "re-start", "re-boot", "restart", "reboot",
    ]

    # Open / Launch phrases across English, Hindi, Hinglish
    OPEN_PHRASES: List[str] = [
        "khol do", "khol de", "kholiye", "khol dena", "kholo",
        "open karo", "open kar do", "open kardo", "open kijiye",
        "launch karo", "launch kar do", "launch kardo", "launch kijiye",
        "start karo", "start kar do", "start kardo", "start kijiye",
        "chalao", "chala do", "chala de", "chala dena",
        "chalu karo", "chalu kar do", "chalu kardo", "chalu kijiye",
        "shuru karo", "shuru kar do", "shuru kardo", "shuru kijiye",
        "run karo", "run kar do", "run kardo",
        "open", "launch", "start", "run", "access",
    ]

    # Close / Terminate phrases
    CLOSE_PHRASES: List[str] = [
        "band karo", "band kar do", "band kardo", "band kijiye",
        "band kar", "hatao", "hata do", "hata kijiye",
        "close karo", "close kar do", "close kardo", "close kijiye",
        "exit karo", "exit kar do", "kill karo", "kill kar do",
        "rok do", "rokna", "khatam karo",
        "close", "exit", "quit", "terminate", "kill", "shut", "stop",
    ]

    # Shutdown phrases
    SHUTDOWN_PHRASES: List[str] = [
        "shutdown karo", "shutdown kar do", "shutdown kardo",
        "power off karo", "power off kar do", "turn off karo", "turn off kar do",
        "shut down the computer", "shutdown the computer", "shut down the pc",
        "shutdown the pc", "turn off the computer", "turn off the pc",
        "power off the computer", "power off the pc", "power off",
        "shut down", "shutdown", "turn off",
    ]

    # Maintenance / Cleanup phrases across English, Hindi, Hinglish
    CLEAN_PHRASES: List[str] = [
        "clear karo", "clear kar do", "clear kardo", "clear kijiye", "clear kar de", "clear",
        "clean karo", "clean kar do", "clean kardo", "clean kijiye", "clean kar de", "clean",
        "cleanup karo", "cleanup kar do", "cleanup kardo", "cleanup",
        "saaf karo", "saaf kar do", "saaf kardo", "saaf kijiye", "saaf kar de", "saaf",
        "khali karo", "khali kar do", "khali kardo", "khali kijiye", "khali kar de", "khali",
        "delete karo", "delete kar do", "delete kardo", "delete kijiye", "delete kar de", "delete",
        "remove karo", "remove kar do", "remove kardo", "remove kijiye", "remove kar de", "remove",
        "erase karo", "erase kar do", "erase",
        "hata do", "hatao", "hata de", "hata kijiye", "hata",
    ]

    TEMP_TERMS: Set[str] = {
        "temp", "temp file", "temp files", "temporary file", "temporary files",
        "temp data", "temporary data", "temp folder", "temporary folder",
        "temporary", "temp dir", "temp directory"
    }

    RECYCLE_TERMS: Set[str] = {
        "recycle bin", "recyclebin", "trash", "trash can", "dustbin", "kachra dabba", "kachra dibba"
    }

    # Fillers and grammatical particles to strip safely during extraction
    GRAMMATICAL_PARTICLES: Set[str] = {
        "ko", "ka", "ki", "ke", "par", "pe", "me", "mein", "se", "ne",
        "mera", "meri", "mere", "apna", "apni", "apne", "the", "a", "an",
        "my", "please", "zara", "bhai", "yaar", "dost", "boss", "jarvis", "bhi",
    }

    _COMPILED_RESTART: List[Tuple[re.Pattern, str]] = []
    _COMPILED_OPEN: List[Tuple[re.Pattern, str]] = []
    _COMPILED_CLOSE: List[Tuple[re.Pattern, str]] = []
    _COMPILED_SHUTDOWN: List[Tuple[re.Pattern, str]] = []
    _SYS_TERMS_RE: Optional[re.Pattern] = None
    _APP_TARGETS_RE: Optional[re.Pattern] = None

    _NORM_CLEAN_RE = re.compile(r"[^\w\s.-]")
    _NORM_PUNCT_RE = re.compile(r"[^\w\s]")
    _WHITESPACE_RE = re.compile(r"\s+")

    @classmethod
    def _init_patterns(cls) -> None:
        if cls._COMPILED_RESTART:
            return

        # Sort phrases by length descending to ensure greedy matching
        def _compile_list(phrases: List[str]) -> List[Tuple[re.Pattern, str]]:
            sorted_phrases = sorted(phrases, key=len, reverse=True)
            compiled = []
            for p in sorted_phrases:
                pattern = re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE)
                compiled.append((pattern, p))
            return compiled

        cls._COMPILED_RESTART = _compile_list(cls.RESTART_PHRASES)
        cls._COMPILED_OPEN = _compile_list(cls.OPEN_PHRASES)
        cls._COMPILED_CLOSE = _compile_list(cls.CLOSE_PHRASES)
        cls._COMPILED_SHUTDOWN = _compile_list(cls.SHUTDOWN_PHRASES)
        cls._SYS_TERMS_RE = re.compile(r'\b(?:' + '|'.join(re.escape(t) for t in cls.SYSTEM_TERMS) + r')\b', re.IGNORECASE)

        try:
            from core.apps.aliases import APPLICATION_ALIASES
            apps = [re.escape(app) for app in sorted(APPLICATION_ALIASES.keys(), key=len, reverse=True) if app not in ("pc", "system", "computer")]
            cls._APP_TARGETS_RE = re.compile(r'\b(?:' + '|'.join(apps) + r')\b', re.IGNORECASE)
        except Exception:
            pass

    @classmethod
    def normalize_text(cls, text: str) -> str:
        """Standardizes spacing, punctuation, and common abbreviations using precompiled regexes."""
        if not text:
            return ""
        cleaned = text.strip()
        cleaned = cls._NORM_CLEAN_RE.sub(" ", cleaned)
        cleaned = cls._WHITESPACE_RE.sub(" ", cleaned).strip()

        words = cleaned.split()
        normalized_words = []
        for w in words:
            lowered = w.lower()
            if lowered in cls.ABBREVIATIONS:
                normalized_words.append(cls.ABBREVIATIONS[lowered])
            else:
                normalized_words.append(w)
        return " ".join(normalized_words)

    @classmethod
    def is_system_restart_utterance(cls, text: str) -> bool:
        """
        Determines if the utterance indicates restarting the system/PC.
        Handles:
          - "restart", "reboot"
          - "restart the PC", "reboot my computer"
          - "system ko restart karo", "PC dobara start karo"
          - "computer dobara start karo", "phir se start karo"
        """
        if not text:
            return False
        lowered = text.lower().strip()
        lowered = cls._NORM_PUNCT_RE.sub(" ", lowered)
        lowered = cls._WHITESPACE_RE.sub(" ", lowered).strip()

        cls._init_patterns()

        # Guard: Explicit Jarvis application reload/restart is NOT system restart
        if "jarvis" in lowered and not any(w in lowered for w in ["system", "pc", "computer", "laptop", "machine"]):
            return False

        # 1. Direct bare commands: "restart", "reboot"
        if lowered in ("restart", "reboot", "retstart", "re-start", "re-boot"):
            return True

        # 2. Check for explicit restart phrases
        matched_restart_phrase = False
        for pat, phrase in cls._COMPILED_RESTART:
            if pat.search(lowered):
                matched_restart_phrase = True
                break

        if not matched_restart_phrase:
            return False

        # 3. If matched phrase contains explicit target (e.g. "restart the pc", "reboot my computer")
        if any(w in lowered for w in ["pc", "computer", "system", "laptop", "machine"]):
            return True

        # 4. If phrase itself is a standalone restart command (e.g. "restart karo", "dobara start karo", "reboot karo")
        # Strip fillers/particles
        words = [w for w in lowered.split() if w not in cls.GRAMMATICAL_PARTICLES]
        meaningful = " ".join(words)
        if meaningful in ("restart", "reboot", "dobara start", "phir se start", "wapas start"):
            return True
        if lowered in ("restart karo", "reboot karo", "system restart", "pc restart", "dobara start karo", "phir se start karo"):
            return True

        # Default fallback: if restart phrase is present and no other application/target is mentioned
        if cls._APP_TARGETS_RE is not None:
            has_app_target = bool(cls._APP_TARGETS_RE.search(lowered))
        else:
            from core.apps.aliases import APPLICATION_ALIASES
            has_app_target = any(re.search(rf"\b{re.escape(app)}\b", lowered) for app in APPLICATION_ALIASES.keys() if app not in ("pc", "system", "computer"))
        if not has_app_target:
            return True

        return False

    @classmethod
    def is_open_action(cls, text: str) -> bool:
        """Checks if utterance contains an open/launch action verb."""
        cls._init_patterns()
        lowered = text.lower()
        for pat, _ in cls._COMPILED_OPEN:
            if pat.search(lowered):
                return True
        return False

    @classmethod
    def extract_open_target(cls, text: str) -> Optional[str]:
        """
        Extracts the target entity from an open utterance.
        e.g. "chrome khol do" -> "chrome"
             "chalao vlc" -> "vlc"
             "start calculator" -> "calculator"
             "launch excel" -> "excel"
        """
        cls._init_patterns()
        lowered = text.lower().strip()
        lowered = re.sub(r"[^\w\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()

        # Try to match open verb phrases and isolate remainder
        remainder = lowered
        for pat, phrase in cls._COMPILED_OPEN:
            if pat.search(remainder):
                remainder = pat.sub(" ", remainder)

        # Remove grammatical particles and fillers
        tokens = remainder.split()
        target_tokens = [w for w in tokens if w not in cls.GRAMMATICAL_PARTICLES]
        candidate = " ".join(target_tokens).strip()

        # Map abbreviations if present
        if candidate in cls.ABBREVIATIONS:
            candidate = cls.ABBREVIATIONS[candidate]

        return candidate if candidate else None

    @classmethod
    def expand_abbreviation(cls, term: str) -> str:
        """Expands an abbreviation if present in ABBREVIATIONS table."""
        return cls.ABBREVIATIONS.get(term.lower().strip(), term)

    @classmethod
    def get_canonical_term(cls, phrase: str) -> str:
        """Returns canonical action or term for a phrase."""
        cls._init_patterns()
        lowered = phrase.lower().strip()
        if cls.is_system_restart_utterance(lowered):
            return "restart"
        if cls.is_open_action(lowered):
            return "open"
        for pat, _ in cls._COMPILED_CLOSE:
            if pat.search(lowered):
                return "close"
        for pat, _ in cls._COMPILED_SHUTDOWN:
            if pat.search(lowered):
                return "shutdown"
        return lowered

    @classmethod
    def analyze(cls, text: str) -> LexicalAnalysis:
        """
        Provides comprehensive semantic analysis of the utterance.
        Does not execute commands or finalize intent without context.
        """
        cls._init_patterns()
        cleaned = cls.normalize_text(text)
        lowered = cleaned.lower()

        is_restart = cls.is_system_restart_utterance(lowered)
        is_open = cls.is_open_action(lowered)
        is_close = any(pat.search(lowered) for pat, _ in cls._COMPILED_CLOSE)
        is_shutdown = any(pat.search(lowered) for pat, _ in cls._COMPILED_SHUTDOWN)

        target_candidate = None
        if is_open:
            target_candidate = cls.extract_open_target(lowered)

        # Determine target domain
        target_domain = TargetDomain.UNKNOWN
        is_sys_target = bool(cls._SYS_TERMS_RE.search(lowered)) if cls._SYS_TERMS_RE else any(re.search(rf"\b{re.escape(t)}\b", lowered) for t in cls.SYSTEM_TERMS)
        if is_sys_target or is_restart or is_shutdown:
            target_domain = TargetDomain.SYSTEM
        elif target_candidate:
            from core.apps.aliases import APPLICATION_ALIASES
            from core.semantic.constants import KNOWN_APPS
            cand_low = target_candidate.lower()
            if cand_low in KNOWN_APPS or cand_low in APPLICATION_ALIASES:
                target_domain = TargetDomain.APPLICATION

        # Determine action concept
        action_concept = ActionConcept.UNKNOWN
        if is_restart:
            action_concept = ActionConcept.SYSTEM_RESTART
        elif is_shutdown:
            action_concept = ActionConcept.SYSTEM_SHUTDOWN
        elif is_open:
            if target_domain == TargetDomain.APPLICATION:
                action_concept = ActionConcept.OPEN_APPLICATION
            else:
                action_concept = ActionConcept.OPEN_APPLICATION  # Per specification: open/launch/start/chalao/khol do map to OPEN_APPLICATION / OPEN_TARGET
        elif is_close:
            action_concept = ActionConcept.CLOSE_TARGET

        return LexicalAnalysis(
            raw_text=text,
            normalized_text=cleaned,
            action_concept=action_concept,
            target_domain=target_domain,
            target_candidate=target_candidate,
            is_restart=is_restart,
            is_open=is_open,
            is_close=is_close,
            is_shutdown=is_shutdown,
            is_system_target=is_sys_target,
        )


@functools.lru_cache(maxsize=512)
def _cached_lexicon_analyze(text: str) -> LexicalAnalysis:
    """Internal LRU cached entry point for LexiconEngine.analyze."""
    return LexiconEngine._analyze_internal(text)


LexiconEngine._analyze_internal = LexiconEngine.analyze
LexiconEngine.analyze = classmethod(lambda cls, text: _cached_lexicon_analyze(text))


_lexicon_engine_instance: Optional[LexiconEngine] = None


def get_lexicon_engine() -> LexiconEngine:
    """Singleton getter for LexiconEngine."""
    global _lexicon_engine_instance
    if _lexicon_engine_instance is None:
        _lexicon_engine_instance = LexiconEngine()
    return _lexicon_engine_instance
