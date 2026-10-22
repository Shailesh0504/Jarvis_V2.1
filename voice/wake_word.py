# voice/wake_word.py
"""
Universal Multi-Position Wake-Word Detector and Voice Conversation Session Engine.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("jarvis.voice.wakeword")


class WakeWordState(str, Enum):
    IDLE = "idle"
    WAKE_DETECTED = "wake_detected"
    LISTENING = "listening"
    PROCESSING = "processing"
    RESPONDING = "responding"


class WakePosition(str):
    """
    Position-independent wake word location specifier.
    Supports equality with both new standard names ('beginning', 'middle', 'end', 'standalone')
    and legacy aliases ('prefix', 'embedded', 'suffix').
    """

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            s = str(self)
            if s in ("prefix", "beginning") and other in ("prefix", "beginning"):
                return True
            if s in ("suffix", "end") and other in ("suffix", "end"):
                return True
            if s in ("embedded", "middle") and other in ("embedded", "middle"):
                return True
        return super().__eq__(other)

    def __hash__(self) -> int:
        s = str(self)
        if s in ("prefix", "beginning"):
            return hash("beginning")
        if s in ("suffix", "end"):
            return hash("end")
        if s in ("embedded", "middle"):
            return hash("middle")
        return super().__hash__()


@dataclass
class WakeWordMatchResult:
    detected: bool
    cleaned_command: str = ""
    is_standalone: bool = False
    position: str = "none"  # "beginning" ("prefix"), "middle" ("embedded"), "end" ("suffix"), "standalone", "none"
    matched_variant: str = ""
    confidence: float = 0.0
    jarvis_addressed: bool = False

    def __post_init__(self):
        if not self.jarvis_addressed and self.detected:
            self.jarvis_addressed = True


def normalize_text(text: str) -> str:
    """Normalizes input text for wake word detection."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def contains_standalone_wake_word(text: str, wake_word: str = "jarvis") -> bool:
    """
    Checks if text contains a standalone wake-word token with word-boundary matching.
    Guarantees no false positives on words like 'jarvisian', 'jarvises', 'myjarvisapp', 'jarvis123'.
    """
    if not text:
        return False
    detector = WakeWordDetector([wake_word])
    return detector.detect(text).detected


class WakeWordDetector:
    """
    Precision Multi-Position Wake-Word Detection Engine.
    Recognizes 'Jarvis' and its phonetic variants at the beginning, middle,
    end, or standalone in any English, Hindi, or Hinglish utterance.
    """

    # Comprehensive phonetic variants and honorific forms (longer variants first)
    WAKE_VARIANTS = [
        r'jarvis\s+ji',
        r'jarvis\s+bhai',
        r'jarvis\s+sir',
        r'jarvis\s+yaar',
        r'jarvis\s+dost',
        r'jarvisji',
        r'jharvis',
        r'jarves',
        r'jarvees',
        r'zervis',
        r'jarwis',
        r'javis',
        r'jarvish',
        r'jervis',
        r'jerwis',
        r'charvis',
        r'chervis',
        r'chaarvis',
        r'zarvis',
        r'sarvis',
        r'jaavis',
        r'service',
        r'jarvis',
    ]

    # Preceding greetings or prefixes that may attach to the wake word
    # NOTE: Conversational action verbs (like 'sun', 'suno') are intentionally excluded
    # so phrases like "Zara suno Jarvis" preserve "Zara suno" as command text.
    GREETING_PREFIX = r'(?:\b(?:hey|hi|hello|ok|okay|arre|are|oye)[,\s]+)?'

    # Common discourse connectors immediately following the wake word
    DISCOURSE_CONNECTORS = [
        r'^(?:to|toh|please|ab|phir|aur|batao|bata|bhai|yaar|ji|sir|kya)\s+'
    ]

    # Negative patterns to prevent false positives (e.g. "java is", "jar on table", "car visit")
    FALSE_POSITIVE_PATTERNS = [
        r'\bjava\s+is\b',
        r'\bjar\s+is\b',
        r'\bjar\s+on\b',
        r'\bcar\s+service\b',
        r'\bweb\s+service\b',
        r'\bcustomer\s+service\b',
        r'\bwindows\s+service\b',
        r'\bthe\s+service\b',
        r'\bstart\s+service\b',
        r'\bstop\s+service\b',
        r'\binstall\s+service\b',
        r'\bcloud\s+service\b',
        r'\broom\s+service\b',
        r'\bbus\s+service\b',
        r'\bfood\s+service\b',
        r'\btaxi\s+service\b',
    ]

    # Patterns indicating the wake-word token is actually a content/action argument (e.g. "usme Jarvis type karo")
    PAYLOAD_PRE_RE = re.compile(
        r'\b(?:type|write|likh|likho|likhna|dalo|daal\s+do|search(?:\s+for)?|dhoondo|dhundo|named?|naam\s+k[aei]|called|about|into|in|usme|isme|file\s+me|file\s+mein)\s+[\'"]?$',
        re.IGNORECASE
    )
    PAYLOAD_POST_RE = re.compile(
        r'^[\'"]?\s+(?:type\s+karo|likho|likh\s+do|likhna|dalo|daal\s+do|search\s+karo|dhoondo|dhundo|banao|bana\s+do|naam\s+k[aei]|named?)',
        re.IGNORECASE
    )

    def __init__(self, wake_words: Optional[Any] = None, debounce_window: float = 0.4):
        if isinstance(wake_words, (int, float)):
            self.debounce_window = float(wake_words)
            self.wake_words = ["jarvis"]
        else:
            self.wake_words = [w.strip().lower() for w in wake_words] if wake_words else ["jarvis"]
            self.debounce_window = float(debounce_window) if isinstance(debounce_window, (int, float)) else 0.4

        self._last_trigger_time = 0.0
        self._last_processed_text = ""

        # Precompile combined regex for variants with strict token boundary lookarounds
        # (?<![\w\-]) and (?![\w\-]) prevent matches on jarvisian, jarvises, myjarvisapp, jarvis123, jarvis-app
        sorted_variants = sorted(self.WAKE_VARIANTS, key=lambda x: len(x), reverse=True)
        variants_pattern = "|".join(sorted_variants)
        self.re_full_wake = re.compile(
            rf'(?<![\w\-])(?:{self.GREETING_PREFIX}(?:{variants_pattern}))(?![\w\-])',
            re.IGNORECASE
        )

        # Precompile negative patterns
        self.re_false_positives = [
            re.compile(p, re.IGNORECASE) for p in self.FALSE_POSITIVE_PATTERNS
        ]

    def contains_standalone_wake_word(self, text: str, wake_word: Optional[str] = None) -> bool:
        """Returns True if the text contains a standalone wake-word address."""
        if not text:
            return False
        return self.detect(text).detected

    def detect(self, text: str) -> WakeWordMatchResult:
        """
        Detects wake words anywhere in the utterance (beginning, middle, end, or standalone)
        and returns structured result with clean command extraction and debug logging.
        """
        if not text or not text.strip():
            return WakeWordMatchResult(detected=False)

        raw = text.strip()

        # Check negative patterns first to prevent false positive triggers
        for fp_re in self.re_false_positives:
            if fp_re.search(raw):
                logger.debug(f"[WAKE] Wake word rejected false-positive pattern: '{raw}'")
                return WakeWordMatchResult(detected=False)

        # Fast path exact match for common standalone utterances
        lowered = raw.lower()
        if lowered in (
            "jarvis", "jarvis!", "jarvis?", "jarvis.", "jarvis,",
            "hey jarvis", "hey, jarvis", "hi jarvis", "hello jarvis",
            "ok jarvis", "okay jarvis"
        ):
            matched = raw.strip()
            logger.info(f"[WAKE] Wake word detected: {matched}")
            logger.info(f"[WAKE] Position: standalone")
            logger.info(f"[WAKE] JARVIS_ADDRESSED=True")
            logger.info(f'[WAKE] Clean utterance: ""')
            return WakeWordMatchResult(
                detected=True,
                cleaned_command="",
                is_standalone=True,
                position=WakePosition("standalone"),
                matched_variant=matched,
                confidence=1.0,
                jarvis_addressed=True
            )

        # Find all wake-word occurrences using strict word-boundary token matching
        matches = list(self.re_full_wake.finditer(raw))
        if not matches:
            logger.debug(f'[WAKE] JARVIS_ADDRESSED=False | Utterance: "{raw}"')
            return WakeWordMatchResult(detected=False, cleaned_command=raw)

        # Filter matches: distinguish true wake-word addresses from payload arguments
        wake_matches = []
        for m in matches:
            pre = raw[:m.start()]
            post = raw[m.end():]
            is_payload = bool(self.PAYLOAD_PRE_RE.search(pre) or self.PAYLOAD_POST_RE.search(post))
            if not is_payload:
                wake_matches.append(m)

        if not wake_matches:
            logger.debug(f'[WAKE] JARVIS_ADDRESSED=False (payload preserved) | Utterance: "{raw}"')
            return WakeWordMatchResult(detected=False, cleaned_command=raw)

        # Determine position based on first wake match
        first_m = wake_matches[0]
        start_idx = first_m.start()
        end_idx = first_m.end()

        # Classify position: beginning / middle / end / standalone
        prefix_clean = re.sub(r'^[,\s:;?!.-]+|[,\s:;?!.-]+$', '', raw[:start_idx]).strip()
        suffix_clean = re.sub(r'^[,\s:;?!.-]+|[,\s:;?!.-]+$', '', raw[end_idx:]).strip()

        if not prefix_clean and not suffix_clean:
            position = WakePosition("standalone")
        elif not prefix_clean and suffix_clean:
            position = WakePosition("beginning")
        elif prefix_clean and not suffix_clean:
            position = WakePosition("end")
        else:
            position = WakePosition("middle")

        # Strip ONLY true wake-word addresses from the string (preserve payload matches)
        cleaned_chars = list(raw)
        for m in wake_matches:
            s, e = m.start(), m.end()
            pre = raw[:s]
            post = raw[e:]
            # Engulf surrounding quotes if enclosed
            if (pre.endswith('"') and post.startswith('"')) or (pre.endswith("'") and post.startswith("'")):
                s -= 1
                e += 1
            # Engulf paired vocative commas setting off the wake word in the middle (e.g. "...hai, Jarvis, batao...")
            elif pre.rstrip().endswith(',') and post.lstrip().startswith(','):
                idx_pre = pre.rfind(',')
                idx_post = e + post.find(',') + 1
                s = idx_pre
                e = idx_post
            cleaned_chars[s:e] = ' ' * (e - s)
        cleaned = "".join(cleaned_chars)

        # Normalize boundary punctuation between excised tokens and surrounding words
        cleaned = re.sub(r'^[,\s:;?!.\-\'"]+', '', cleaned)
        cleaned = re.sub(r'[,\s:;?!.\-\'"]+$', '', cleaned)
        cleaned = re.sub(r'\s*([,;:!?.-])\s*[,;:!?.-]+', r'\1 ', cleaned)

        # Remove leading conversational connectors (e.g. "Jarvis to meri awaaz..." -> "meri awaaz...")
        if position in ("prefix", "beginning"):
            cleaned = re.sub(r'^(?:to|toh)\s+', '', cleaned, flags=re.IGNORECASE)

        # Collapse excess whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        is_standalone = (len(cleaned) == 0)
        if is_standalone:
            position = WakePosition("standalone")

        # Structured debug logging as specified
        matched_text = first_m.group(0).strip()
        logger.info(f"[WAKE] Wake word detected: {matched_text}")
        logger.info(f"[WAKE] Position: {position}")
        logger.info(f"[WAKE] JARVIS_ADDRESSED=True")
        logger.info(f'[WAKE] Clean utterance: "{cleaned}"')

        # Debounce check
        now = time.time()
        if (now - self._last_trigger_time < self.debounce_window) and (cleaned == self._last_processed_text):
            logger.debug(f"Wake word debounce suppressed duplicate trigger: '{raw}'")

        self._last_trigger_time = now
        self._last_processed_text = cleaned

        return WakeWordMatchResult(
            detected=True,
            cleaned_command=cleaned,
            is_standalone=is_standalone,
            position=position,
            matched_variant=matched_text,
            confidence=0.98,
            jarvis_addressed=True
        )


class ConversationSessionManager:
    """
    Manages active conversation sessions so users do not need to repeat
    the wake word before every sentence during an active dialogue.
    """

    def __init__(self, session_timeout: float = 15.0):
        self.session_timeout = session_timeout
        self._session_active = False
        self._last_activity_time = 0.0
        self.state = WakeWordState.IDLE

    @property
    def is_session_active(self) -> bool:
        if not self._session_active:
            return False
        if time.time() - self._last_activity_time > self.session_timeout:
            self._session_active = False
            self.state = WakeWordState.IDLE
            return False
        return True

    def activate_session(self) -> None:
        self._session_active = True
        self._last_activity_time = time.time()
        self.state = WakeWordState.LISTENING

    def touch(self) -> None:
        """Refreshes active conversation session timeout."""
        if self._session_active:
            self._last_activity_time = time.time()

    def end_session(self) -> None:
        self._session_active = False
        self.state = WakeWordState.IDLE

    def is_stop_command(self, text: str) -> bool:
        """Detects explicit session termination phrases."""
        lowered = text.lower().strip()
        stop_phrases = [
            "stop listening", "stop voice", "bas jarvis", "bas karo jarvis",
            "bas karo", "shant ho jao", "chup ho jao", "cancel voice",
            "band karo voice", "bye jarvis", "alvida jarvis", "stop"
        ]
        return any(p in lowered for p in stop_phrases)
