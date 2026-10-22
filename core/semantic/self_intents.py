# core/semantic/self_intents.py
"""
Authoritative Semantic Self-Intent Layer for JARVIS identity/about-self understanding.

Single owner for ASSISTANT_* semantic intents (SSOT). Understands MEANING, not words:
normalization -> phrase/alias -> intent patterns -> guarded fuzzy -> token-overlap
similarity -> conversation context -> self-knowledge response. Generic fallback is
never produced here; on low confidence this module returns None so the normal
pipeline (rules / ML / LLM / fallback) continues untouched.

Reuses (never duplicates):
- core.semantic.normalizer.HinglishNormalizer for shorthand/STT normalization
  (u->you, ur->your, r->are, wht/wat->what, btao->batao, kon->kaun, kyu->kyun ...).
- core.conversational_intent.ConversationalIntentClassifier.CAPABILITY_GENERAL_RESP_*
  for capability wording (identical user-visible text as the existing path).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.core.semantic.self_intents")


class SelfIntent(str, Enum):
    ASSISTANT_IDENTITY = "ASSISTANT_IDENTITY"
    ASSISTANT_CREATOR_ORIGIN = "ASSISTANT_CREATOR_ORIGIN"
    ASSISTANT_CAPABILITIES = "ASSISTANT_CAPABILITIES"
    ASSISTANT_STATUS = "ASSISTANT_STATUS"
    ASSISTANT_GREETING = "ASSISTANT_GREETING"
    ASSISTANT_HELP = "ASSISTANT_HELP"
    ASSISTANT_MEMORY = "ASSISTANT_MEMORY"
    ASSISTANT_LANGUAGE = "ASSISTANT_LANGUAGE"
    ASSISTANT_OFFLINE = "ASSISTANT_OFFLINE"
    ASSISTANT_TECHNOLOGY = "ASSISTANT_TECHNOLOGY"
    UNKNOWN = "UNKNOWN"


@dataclass
class SelfIntentResult:
    intent: SelfIntent
    confidence: float
    original_text: str = ""
    normalized_text: str = ""
    entities: Dict[str, str] = field(default_factory=dict)
    context: Optional[str] = None
    response_source: str = "SELF_KNOWLEDGE"
    response_text: Optional[str] = None
    matched_by: str = "none"  # phrase | pattern | fuzzy | overlap | context


# ---------------------------------------------------------------------------
# 1. Normalization (extends the shared HinglishNormalizer, never replaces it)
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[?!.,;:\-\"'()]+")
_WS_RE = re.compile(r"\s+")

# Direct pre-maps applied BEFORE HinglishNormalizer (protects words that the
# shared fuzzy layer would otherwise corrupt, e.g. kaha->raha, bina->bana,
# sahi->rahi, karya->karna, karun->kaun, kab->kar).
_PRE_MAP: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bkaha\b"), "kahan"),
    (re.compile(r"\bsahi\b"), "theek"),
    (re.compile(r"\bkarya\b"), "kaam"),
    (re.compile(r"\bkarun\b"), "karo"),
    (re.compile(r"\bkab\b"), "when"),
    (re.compile(r"\bkas[eo]\b"), "kaise"),
]

# Placeholder protection for correct words that are distance-1 from a shared
# fuzzy anchor (digits make _fuzzy_match_anchor skip them); restored after.
_PLACEHOLDERS: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"\bbina\b"), "bina0", "bina"),
    (re.compile(r"\bbane\b"), "bane0", "bane"),
    (re.compile(r"\bsmart\b"), "smart0", "smart"),
    (re.compile(r"\bjaise\b"), "jaise0", "jaise"),
    (re.compile(r"\bshakti\b"), "shakti0", "shakti"),
]

# Self-domain token unification applied AFTER HinglishNormalizer.
_SELF_UNIFY: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\baapka\b", re.I), "aap ka"),
    (re.compile(r"\baapke\b", re.I), "aap ka"),
    (re.compile(r"\baapki\b", re.I), "aap ka"),
    (re.compile(r"\btumhara\b", re.I), "tumhara"),
    (re.compile(r"\btumhare\b", re.I), "tumhara"),
    (re.compile(r"\btumhari\b", re.I), "tumhara"),
    (re.compile(r"\btumara\b", re.I), "tumhara"),
    (re.compile(r"\btmhara\b", re.I), "tumhara"),
    (re.compile(r"\btumko\b", re.I), "tum ko"),
    (re.compile(r"\btumhein\b", re.I), "tumhe"),
    (re.compile(r"\btumhen\b", re.I), "tumhe"),
    (re.compile(r"\btujhe\b", re.I), "tumhe"),
    (re.compile(r"\btujhko\b", re.I), "tum ko"),
    (re.compile(r"\baapko\b", re.I), "aap ko"),
    (re.compile(r"\bapko\b", re.I), "aap ko"),
    (re.compile(r"\bapna\b", re.I), "tumhara"),
    (re.compile(r"\bapni\b", re.I), "tumhara"),
    (re.compile(r"\bapne\b", re.I), "tumhara"),
    (re.compile(r"\btera\b", re.I), "tumhara"),
    (re.compile(r"\bteri\b", re.I), "tumhara"),
    (re.compile(r"\btere\b", re.I), "tumhara"),
    (re.compile(r"\bkaunsi\b", re.I), "kaun si"),
    (re.compile(r"\bkonsi\b", re.I), "kaun si"),
    (re.compile(r"\bkonsa\b", re.I), "kaun sa"),
    (re.compile(r"\bname\b", re.I), "naam"),
    (re.compile(r"\bnaams\b", re.I), "naam"),
    (re.compile(r"\bnam\b", re.I), "naam"),
    (re.compile(r"\bbnaya\b", re.I), "banaya"),
    (re.compile(r"\bbnaye\b", re.I), "banaya"),
    (re.compile(r"\bbnaaya\b", re.I), "banaya"),
    (re.compile(r"\bcreat\b", re.I), "create"),
    (re.compile(r"\bcrate\b", re.I), "create"),
    (re.compile(r"\bcreatd\b", re.I), "created"),
    (re.compile(r"\bcreted\b", re.I), "created"),
    (re.compile(r"\bcreateed\b", re.I), "created"),
    (re.compile(r"\bbulit\b", re.I), "built"),
    (re.compile(r"\bbiult\b", re.I), "built"),
    (re.compile(r"\bdevlop\b", re.I), "develop"),
    (re.compile(r"\bdevelopd\b", re.I), "develop"),
    (re.compile(r"\bdevelopped\b", re.I), "developed"),
    (re.compile(r"\bcapablities\b", re.I), "capabilities"),
    (re.compile(r"\bcapabilites\b", re.I), "capabilities"),
    (re.compile(r"\bcapblities\b", re.I), "capabilities"),
    (re.compile(r"\bmemmory\b", re.I), "memory"),
    (re.compile(r"\bmemori\b", re.I), "memory"),
    (re.compile(r"\boflain\b", re.I), "offline"),
    (re.compile(r"\bofflinee\b", re.I), "offline"),
    (re.compile(r"\boffine\b", re.I), "offline"),
    (re.compile(r"\bwhts\b", re.I), "whats"),
    (re.compile(r"\bwats\b", re.I), "whats"),
    (re.compile(r"\bwhats\b", re.I), "what is"),
    (re.compile(r"\bkya h\b", re.I), "kya hai"),
]


def normalize_self_text(text: str) -> Tuple[str, str]:
    """Returns (original, normalized). Original is never destroyed."""
    original = (text or "").strip()
    lowered = original.lower()
    for pat, repl in _PRE_MAP:
        lowered = pat.sub(repl, lowered)
    for pat, holder, _ in _PLACEHOLDERS:
        lowered = pat.sub(holder, lowered)
    try:
        from core.semantic.normalizer import HinglishNormalizer
        norm = HinglishNormalizer.normalize_text(lowered)
    except Exception:
        norm = lowered
    for _, holder, real in _PLACEHOLDERS:
        norm = re.sub(r"\b" + re.escape(holder) + r"\b", real, norm)
    norm = _PUNCT_RE.sub(" ", norm)
    for pat, repl in _SELF_UNIFY:
        norm = pat.sub(repl, norm)
    norm = _WS_RE.sub(" ", norm).strip()
    return original, norm


_SELF_TOKENS = {
    "tum", "tumhe", "tumhara", "tumko", "tumse", "tumne", "tumhare",
    "tujhe", "aap", "aapka", "aapke", "aapko", "aapse", "tu", "tera",
    "teri", "you", "your", "yours", "yourself", "jarvis", "assistant",
}

# Nouns that belong to general-knowledge "kisne banaya" questions, NOT to self.
_GK_ENTITY_GUARD = {
    "computer", "laptop", "bluetooth", "python", "internet", "mobile",
    "phone", "television", "tv", "radio", "bulb", "plane", "train",
    "car", "taj", "mahal", "qutub", "india", "delhi", "mumbai",
}

# Device entities: offline/status questions about THESE defer to existing flows.
_DEVICE_ENTITY_GUARD = {
    "system", "computer", "laptop", "pc", "chrome", "brave", "edge",
    "firefox",
}

# App/action nouns: capability questions about THESE stay with the existing
# specific-capability flow (which answers with the exact target).
_CAPABILITY_TARGET_GUARD = {
    "chrome", "excel", "youtube", "vlc", "brave", "firefox", "edge",
    "notepad", "calculator", "calc", "spotify", "whatsapp", "volume",
    "brightness", "bluetooth", "wifi", "reminder", "alarm", "wallpaper",
    "screenshot", "screen", "browser", "file", "folder", "pdf", "word",
    "email", "camera", "printer", "shutdown", "restart", "lock", "mute",
    "song", "video", "music", "bappa", "system", "computer", "pc",
    "laptop",
}

# First-person/profile markers for the user-own-data guard.
_USER_WORDS = re.compile(r"\b(mera|meri|mere|my|maine|mine|mujhe|mujhko)\b", re.I)
_USER_DATA_WORDS = {"naam", "hobby", "pasand", "shauk"}
# Benefactive "mere liye" (for me) is never profile data.
_BENEFACTIVE_RE = re.compile(r"\bmere\s+liy", re.I)

# Strong command shapes always belong to existing execution flows, never self.
# ("open source" is knowledge talk, not an open command.)
_COMMAND_GUARD_RE = re.compile(
    r"\b(open(?!\s+source\b)|launch|start|close|band\s+kar\w*|kholo?|khol\s+do|chalao|bajao|"
    r"volume\s+\d|mute|unmute|shutdown|restart|reboot|lock\s+kar\w*|"
    r"on\s+kar\w*|off\s+kar\w*|dhoondo|search\s+kar\w*|reminder\s+(lagao|set)|yaad\s+dila)\b", re.I
)


def _tokens(norm: str) -> List[str]:
    return norm.split()


def _has_self_token(norm: str) -> bool:
    return bool(set(_tokens(norm)) & _SELF_TOKENS)


def _has_gk_entity(norm: str) -> bool:
    return bool(set(_tokens(norm)) & _GK_ENTITY_GUARD)


def _has_device_entity(norm: str) -> bool:
    return bool(set(_tokens(norm)) & _DEVICE_ENTITY_GUARD)


def _has_capability_target(norm: str) -> bool:
    return bool(set(_tokens(norm)) & _CAPABILITY_TARGET_GUARD)


# ---------------------------------------------------------------------------
# 2. Deterministic phrase / alias layer (high confidence)
# ---------------------------------------------------------------------------

_IDENTITY_PHRASES = {
    "tumhara naam kya hai", "aap ka naam kya hai", "aapka naam kya hai",
    "tumhara naam kya h", "tum kaun ho", "aap kaun ho", "tu kaun hai",
    "what is your naam", "who are you", "naam batao", "tumhara naam batao",
}

_CREATOR_PHRASES = {
    "tum ko kisne banaya", "tumhe kisne banaya", "aap ko kisne banaya",
    "aapko kisne banaya", "tumhe kisne banaya hai", "tumhara creator kaun hai",
    "tumhara creator kaun", "who created you", "who create you",
    "who made you", "who built you", "who developed you",
    "who is your creator", "how were you created",
}


# ---------------------------------------------------------------------------
# 3. Intent patterns + topic rules (semantic, typo-tolerant via normalization)
# ---------------------------------------------------------------------------

_IDENTITY_PATTERNS = [
    re.compile(r"\bnaam\s+kya\s+hai\b", re.I),
    re.compile(r"\bnaam\s+batao?\b", re.I),
    re.compile(r"\b(tumhara|aap\s+ka|tum|aap)\s+naam\b", re.I),
    re.compile(r"\bwhat\s+is\s+your\s+naam\b", re.I),
    re.compile(r"\byour\s+naam\b", re.I),
    re.compile(r"\bwho\s+are\s+you\b", re.I),
    re.compile(r"\b(tum|aap|tu)\s+kaun\s+ho\b", re.I),
    re.compile(r"\b(tum|aap|tu)\s+kaun\s+h\w+\b", re.I),
    re.compile(r"\btu\s+kaun\s+hai\b", re.I),
    re.compile(r"\bwhat\s+should\s+i\s+call\s+you\b", re.I),
    re.compile(r"\btumhe\s+kya\s+bulaun\b", re.I),
    re.compile(r"\bkya\s+bulaun\b", re.I),
    re.compile(r"\btell\s+me\s+your\s+naam\b", re.I),
    re.compile(r"\btell\s+me\s+about\s+yourself\b", re.I),
    re.compile(r"\bintroduce\s+yourself\b", re.I),
    re.compile(r"\bparichay\b", re.I),
]

_CREATOR_PATTERNS = [
    re.compile(r"\bkisne\s+banaya\b", re.I),
    re.compile(r"\bkis\s+ne\s+banaya\b", re.I),
    re.compile(r"\bkisne\s+develop\s+kiya\b", re.I),
    re.compile(r"\bkisne\s+create\s+kiya\b", re.I),
    re.compile(r"\bcreator\b", re.I),
    re.compile(r"\bwho\s+(created|create|made|built|developed|develop)\s+(you|u)\b", re.I),
    re.compile(r"\bwho\s+made\s+this\s+assistant\b", re.I),
    re.compile(r"\bhow\s+were\s+you\s+created\b", re.I),
    re.compile(r"\bwhere\s+did\s+you\s+come\s+from\b", re.I),
    re.compile(r"\bwhere\s+do\s+you\s+come\s+from\b", re.I),
    re.compile(r"\bkahan\s+se\s+aay?e\b", re.I),
    re.compile(r"\bjarvis\s+ko\s+kisne\b", re.I),
    re.compile(r"\bjarvis\s+kisne\s+banaya\b", re.I),
    re.compile(r"\bbanane\s+wala\b", re.I),
    re.compile(r"\b(nirmata|janmdata)\b", re.I),
    re.compile(r"\butpatti\b", re.I),
]

_MEMORY_TOPICS = {
    "yaad", "yaadon", "yaadein", "remember", "remembering", "memory",
    "bhool", "bhoolte", "bhoolne", "bhoolna", "bhoolakkad", "yaaddasht",
    "smriti", "smaran", "pehchan", "pehchante", "recognise", "recognize",
    "dimag", "dimaag", "memorize", "memorise", "forget", "forgetful",
    "capacity",
}
_MEMORY_PATTERNS = [
    re.compile(r"\bmemory\s+kaise\s+kaam\b", re.I),
    re.compile(r"\bkitni\s+baatein\s+yaad\b", re.I),
    re.compile(r"\b(kal|pichli|purani|last)\b.{0,12}\byaad\b", re.I),
    re.compile(r"\b(chehre|baat|naam)\b.{0,12}\byaad\s+hai\b", re.I),
    # "tum mujhe jaante ho" (recognition) is memory; bare "kya jaante ho"
    # stays a capability question. Caller checks the mujhe-context.
    re.compile(r"\bjaante\s+ho\b", re.I),
]

_LANGUAGE_WORDS = {
    "hindi", "english", "hinglish", "urdu", "punjabi", "marathi",
    "tamil", "telugu", "bengali", "gujarati", "kannada", "malayalam",
    "odia", "assamese", "sanskrit", "bhojpuri", "haryanvi", "pahadi",
    "bhasha", "bhashayein", "bhashaen", "language", "languages",
    "multilingual", "tongue", "matribhasha", "speak", "bolte",
    "bolo", "aati",
}
_LANGUAGE_PATTERNS = [
    re.compile(r"\bkaun\s*si\s+bhasha\b", re.I),
    re.compile(r"\bkaun\s+sa\s+language\b", re.I),
    re.compile(r"\bhow\s+many\s+languages\b", re.I),
    re.compile(r"\bmother\s+tongue\b", re.I),
]

_OFFLINE_NET = {
    "offline", "internet", "net", "wifi", "network", "data",
    "connection", "cloud", "online", "signal", "bandwidth", "sync",
    "local",
}
_OFFLINE_STRONG = {
    "offline", "without", "bina", "baghair", "chahiye", "zaroori",
    "zaroorat", "lagega", "lagta", "lagti", "lagegi", "band",
    "chaloge", "chalega", "chalte", "chalta", "chal", "kaam", "mode",
    "sync", "reconnect", "slow", "tayaar", "hote", "local", "cloud",
    "online", "use", "need", "jawab", "ruk", "tut", "tutne", "tuta",
    "tuti", "jaane", "aane", "hamesha", "kabhi", "flight", "jahaz",
    "first", "always",
}
_OFFLINE_PATTERNS = [
    re.compile(r"\b(2g|4g|5g)\b", re.I),
    re.compile(r"\bflight\s+mode\b", re.I),
]
# NOTE: "band" is intentionally absent — "internet band ho toh chaloge"
# is an offline question, not a close command.
_OFFLINE_DEVICE_VERBS = {
    "kholo", "khol", "open", "launch", "close", "lock",
    "unlock", "restart", "reboot", "shutdown", "chalao", "bajao",
    "mute", "unmute", "badhao", "ghatao",
}

_STATUS_TOPICS = {
    "haal", "theek", "khush", "mood", "fit", "healthy", "swasth",
    "fresh", "taaza", "energetic", "energy", "badhiya", "mast",
    "first", "class", "jhakaas", "tabeeyat", "thak", "thake",
    "thaka", "thaki", "aaram", "rest", "neend", "soye", "mehsoos",
    "feel", "achha", "achhe", "well", "scene", "life", "sahi",
}
# Vocatives / openers that address the assistant without a pronoun.
_STATUS_VOCATIVES = {
    "bhai", "sir", "boss", "yaar", "dost", "ji", "hello", "aur",
    "toh", "hey", "hi",
}
_STATUS_PATTERNS = [
    re.compile(r"\bhow\s+are\s+you\b", re.I),
    re.compile(r"\bhow\s+r\s+you\b", re.I),
    re.compile(r"\bhope\s+you\s+are\s+well\b", re.I),
    re.compile(r"\bare\s+you\s+doing\s+well\b", re.I),
    re.compile(r"\bare\s+you\s+well\b", re.I),
    re.compile(r"\bare\s+you\s+(ok|okay|fine|good)\b", re.I),
    re.compile(r"\bkaise\s+h(o|ain)\b", re.I),  # needs self/vocative (checked by caller)
    re.compile(r"\bkya\s+chal\s+raha\s+hai\b", re.I),  # needs self (checked by caller)
    re.compile(r"\bkaam\s+kais\w*\s+chal\b", re.I),
    re.compile(r"\bmehsoos\b", re.I),  # needs no-main guard (checked by caller)
]

_TECH_TOPICS = {
    "technology", "engine", "architecture", "operate", "function",
    "robot", "program", "software", "code", "python", "source",
    "version", "update", "updated", "learn", "seekhte", "seekho",
    "seekhna", "sikhata", "teacher", "teach", "teaches", "training",
    "trained", "smart", "intelligent", "iq", "emotion", "emotions",
    "feeling", "feelings", "sleep", "sote", "khate", "bhookh",
    "rehte", "live", "host", "hosted", "server", "laptop",
    "think", "sochte", "rule", "based", "bane", "principle",
    "thakte", "tired", "humans", "insaano", "system", "funda",
    "ai",
}
_TECH_PATTERNS = [
    re.compile(r"\bkaise\s+kaam\s+karte\s+h\w+\b", re.I),
    re.compile(r"\bhow\s+do\s+you\s+work\b", re.I),
    re.compile(r"\bhow\s+do\s+you\s+(think|learn|understand)\b", re.I),
    re.compile(r"\bkaise\s+bane\b", re.I),
    re.compile(r"\bbanaye\s+gaye\b", re.I),
    re.compile(r"\bkaise\s+chalte\s+h\w+\b", re.I),
    re.compile(r"\bkaise\s+sochte\s+h\w+\b", re.I),
    re.compile(r"\bkaise\s+samajhte\s+h\w+\b", re.I),
    re.compile(r"\bkaise\s+seekhte\s+h\w+\b", re.I),
    re.compile(r"\bopen\s+source\b", re.I),
    re.compile(r"\brule\s+based\b", re.I),
    re.compile(r"\bworking\s+principle\b", re.I),
    re.compile(r"\blike\s+humans\b", re.I),
    re.compile(r"\binsaano\s+jaise\b", re.I),
    re.compile(r"\bmade\s+in\s+python\b", re.I),
    re.compile(r"\bcode\s+se\s+bane\b", re.I),
    re.compile(r"\bpython\s+me\w*\s+bane\b", re.I),
    re.compile(r"\bare\s+you\s+an?\s+(ai|robot)\b", re.I),
]

_ABILITY_MARKERS = [
    re.compile(r"\bsakt[aei]\b", re.I),
    re.compile(r"\bcan\s+you\b", re.I),
    re.compile(r"\bcould\s+you\b", re.I),
    re.compile(r"\bable\s+to\b", re.I),
    re.compile(r"\bkar\s+paoge?\b", re.I),
    re.compile(r"\bkar\s+paogi\b", re.I),
]
_CAPABILITY_TOPICS = {
    "capabilities", "capability", "capable", "skills", "skill",
    "features", "feature", "seva", "service", "services", "function",
    "functions", "purpose", "uddeshya", "kshamta", "saksham",
    "limits", "limit", "seema", "fayda", "aata", "jaante", "kaam",
    "hunar", "sambhal",
}
_CAPABILITY_PATTERNS = [
    re.compile(r"\bwhat\s+can\s+you\s+do\b", re.I),
    re.compile(r"\bwhat\s+can\s+i\s+ask\s+you\b", re.I),
    re.compile(r"\bwhat\s+are\s+you\s+capable\s+of\b", re.I),
    re.compile(r"\bwhat\s+are\s+your\s+capabilit", re.I),
    re.compile(r"\btell\s+me\s+your\s+capabilit", re.I),
    re.compile(r"\blist\s+your\s+features\b", re.I),
    re.compile(r"\bshow\s+me\s+your\s+skills\b", re.I),
    re.compile(r"\bwhat\s+help\s+can\s+you\b", re.I),
    re.compile(r"\bwhat\s+tasks\s+can\s+you\b", re.I),
    re.compile(r"\bwhat\s+is\s+your\s+purpose\b", re.I),
    re.compile(r"\b(your|tumhara|aap\s+ka)\s+purpose\b", re.I),
    re.compile(r"\bcapabilit", re.I),
]

_HELP_PATTERNS = [
    re.compile(r"\bhelp\s+(chahiye|karo|kar\s+do|kar\s+dijiye|karoge|karenge|me)\b", re.I),
    re.compile(r"\bmadad\s+(karo|kar\s+do|kar\s+dijiye|karoge|karenge|chahiye)\b", re.I),
    re.compile(r"\bsahayata\b", re.I),
    re.compile(r"\bsahaayta\b", re.I),
    re.compile(r"\b(mujhe|meri)\s+(support|assist|guide)\b", re.I),
    re.compile(r"\b(support|assist|guide)\s+(karo|kar\s+do|chahiye)\b", re.I),
    re.compile(r"\bmargdarshan\b", re.I),
    re.compile(r"\bmadadgaar\b", re.I),
    re.compile(r"\bhelping\s+hand\b", re.I),
    re.compile(r"\bi\s+need\s+help\b", re.I),
    re.compile(r"\bneed\s+(some\s+)?help\b", re.I),
    re.compile(r"\bneed\s+assistance\b", re.I),
    re.compile(r"\bzaroorat\b.{0,10}\bhelp\b", re.I),
    re.compile(r"\bhelp\b.{0,10}\bzaroorat\b", re.I),
    re.compile(r"\bkaise\s+use\s+kar", re.I),
    re.compile(r"\bhow\s+to\s+use\s+you\b", re.I),
    re.compile(r"\bhelp\s+me\s+out\b", re.I),
    re.compile(r"^(help|madad|support|assist|guide)\b", re.I),
    re.compile(r"\b(help|madad)\s+kar\b", re.I),
]

_GREETING_PATTERNS = [
    re.compile(
        r"^(hi+|he+y+|hello+|hey+|namastey?|namaskar|pranam|ram\s+ram|"
        r"sat\s+sri\s+akal|adaab|yo|good\s+morning|good\s+afternoon|"
        r"good\s+evening|good\s+day|good\s+night|shubh\s+prabhat|"
        r"shubh\s+ratri|shubh\s+din|hellohello)\b", re.I
    ),
]

# Bare follow-ups resolved via conversation context only.
_BARE_CREATOR_FOLLOWUP = re.compile(
    r"^(kisne\s+banaya|kisne|creator\s+kaun|who\s+(made|created|built|create)\s+(you|u|it)|kisne\s+banaya\s+tha)\??$", re.I
)
_BARE_CAPABILITY_FOLLOWUP = re.compile(r"^(aur|aur\s+batao|aur\s+kya|tell\s+me\s+more|what\s+else|continue)\??$", re.I)


# ---------------------------------------------------------------------------
# 4. Overlap seeds for the token-similarity layer (normalized at load)
# ---------------------------------------------------------------------------

_OVERLAP_SEEDS_RAW: Dict[SelfIntent, List[str]] = {
    SelfIntent.ASSISTANT_IDENTITY: [
        "tumhara naam kya hai", "aap ka naam kya hai", "what is your name",
        "who are you", "tum kaun ho", "naam batao", "parichay do",
        "tumhe kya bulaun", "call you",
    ],
    SelfIntent.ASSISTANT_CREATOR_ORIGIN: [
        "tum ko kisne banaya", "who created you", "who made you",
        "tumhara creator kaun hai", "tumhe kisne develop kiya",
        "kahan se aaye", "banane wala kaun",
    ],
    SelfIntent.ASSISTANT_CAPABILITIES: [
        "capabilities kya hain", "skills kya hain", "tumhara kaam kya hai",
        "purpose kya hai", "seva de sakte", "kya aata hai",
        "kya jaante ho", "limits kya hain", "uddeshya kya hai",
        "kshamta kya hai", "features batao", "hunar hai",
    ],
    SelfIntent.ASSISTANT_STATUS: [
        "kya haal hai", "tumhara haal", "mood kaisa", "tabeeyat kaisi",
        "thak gaye", "neend hui", "mehsoos kar rahe", "first class",
        "jhakaas", "badhiya ho", "khush ho", "fresh ho",
    ],
    SelfIntent.ASSISTANT_HELP: [
        "help chahiye", "madad karo", "help karo", "sahayata karo",
        "guide karo", "support karo", "margdarshan karo",
    ],
    SelfIntent.ASSISTANT_MEMORY: [
        "yaad hai", "do you remember", "memory kaise", "bhool jaate",
        "yaaddasht kaisi", "pehchante ho", "dimag kaisa", "memorize",
        "forget things", "memory capacity",
    ],
    SelfIntent.ASSISTANT_LANGUAGE: [
        "bhasha samajhte", "language samajhte", "hindi samajhte",
        "which languages", "mother tongue", "matribhasha",
        "multilingual ho", "speak hindi", "hindi bolte",
    ],
    SelfIntent.ASSISTANT_OFFLINE: [
        # NOTE: no bare-"chal" seed — "aur batao kya chal raha hai" must
        # never link here (existing conversational flow owns it).
        "offline mode hai", "without internet", "internet chahiye",
        "wifi chahiye", "do you work offline", "cloud use karte",
        "network chahiye", "local chalte ho", "sync hote ho", "reconnect karte",
    ],
    SelfIntent.ASSISTANT_TECHNOLOGY: [
        "kaise kaam karte", "how do you work", "technology kya",
        "engine use", "open source", "version kya", "update hua",
        "seekhte ho", "teacher kaun", "training kahan", "smart ho",
        "emotions hain", "sote ho", "khate ho", "rehte ho",
        "robot ho", "program ho", "code kya", "bane ho", "iq kya",
    ],
}

_OVERLAP_SEEDS: Dict[SelfIntent, List[str]] = {}
for _intent, _seeds in _OVERLAP_SEEDS_RAW.items():
    _OVERLAP_SEEDS[_intent] = [normalize_self_text(s)[1] for s in _seeds]

_STOPWORDS = {
    "kya", "tum", "aap", "main", "hai", "hain", "ho", "hun", "hoon",
    "ka", "ki", "ke", "ko", "se", "ne", "pe", "par", "me", "mein",
    "ye", "yeh", "wo", "woh", "the", "a", "an", "is", "are", "you",
    "my", "i", "me", "we", "us", "our", "your", "yours", "to", "in",
    "on", "at", "or", "and", "na", "toh", "aur", "bhi",
    "what", "who", "whom", "whose", "which", "how", "do", "does",
    "did", "kaun", "kab", "kahan", "when", "kaise", "kyun", "kitna",
    "kitne", "kitni", "kabhi", "tha", "thi", "the", "thin", "hua",
    "hui", "hue", "hoga", "hogi", "gaya", "gaye", "gayi", "raha",
    "rahe", "rahi", "kar", "karo", "karna", "karte", "karne",
    "kiya", "kiye", "sakte", "sakta", "sakti", "sake",
    "mujhe", "mujhko", "mera", "meri", "mere", "tumhe", "tumhara",
    "tumhare", "tumhari", "tumko", "tumse", "tumne", "tu", "tera",
    "teri", "tere", "tujhe", "aapka", "aapke", "aapki", "aapko",
    "aapse", "liye", "liy", "batao", "bataiye", "tell",
    # Generic Hindi relativizers — never intent content on their own
    # ("ye doosra wala hai" must not link to "banane wala kaun").
    "wala", "wale", "wali",
}

# Guarded fuzzy vocabulary: token -> canonical. Distance<=1 accepted only
# when exactly one candidate matches AND the token is not a real common word
# (no blind fuzzy per spec section 12: kaam->naam, mode->made were caught).
_FUZZY_VOCAB = [
    "naam", "banaya", "creator", "created", "create", "made", "built",
    "develop", "developed", "capabilities", "capable", "memory",
    "offline", "language", "bhasha", "kaise", "kaun", "kisne",
]

_NO_FUZZY = {
    # Real Hinglish/English words that must never be "fixed" (each is
    # distance-1 from a fuzzy candidate but is a legitimate word).
    "kaam", "naam", "mode", "made", "kya", "kaise", "kaun", "kahan",
    "kabhi", "kitna", "kitne", "kal", "parso", "aaj", "tum", "aap",
    "hai", "ho", "hain", "hun", "hoon", "tha", "thi", "kar", "karo",
    "karna", "karte", "karne", "batao", "bata", "yaad", "theek",
    "achha", "badhiya", "chal", "chalte", "chaloge", "chalega",
    "chalta", "karoge", "hote", "rehte", "rehta", "hota", "hoti",
    "hua", "hui", "gaya", "gaye", "mera", "meri", "mere", "main",
    "mujhe", "tumhe", "tumhara", "aapka", "bina", "bane", "smart",
    "jaise", "shakti", "sahi", "kaha", "karya", "karun", "kab",
    "nam", "name", "se", "me", "ne", "ko", "pe", "ke", "ka",
    "aur", "or", "bhi", "na", "tumne", "tera", "teri", "tu",
    "do", "is", "are", "you", "your", "my", "we", "to", "in",
    "on", "the", "aapki", "aapke", "tumhare", "tumhari",
}


def _try_fuzzy_fix(tokens: List[str]) -> Tuple[List[str], bool]:
    try:
        from core.semantic.normalizer import _is_damerau_levenshtein_1 as _d1
    except Exception:
        return tokens, False
    fixed: List[str] = []
    changed = False
    for tok in tokens:
        low = tok.lower()
        if len(low) < 4 or low in _FUZZY_VOCAB or low in _NO_FUZZY:
            fixed.append(tok)
            continue
        if any(ch.isdigit() for ch in low):
            fixed.append(tok)
            continue
        matches = [c for c in _FUZZY_VOCAB if _d1(low, c)]
        if len(matches) == 1:
            fixed.append(matches[0])
            changed = True
        else:
            fixed.append(tok)
    return fixed, changed


def _overlap_score(norm: str, seed: str) -> float:
    a = set(norm.split()) - _STOPWORDS
    b = set(seed.split()) - _STOPWORDS
    if not a or not b:
        return 0.0
    inter = a & b
    if not inter:
        return 0.0
    return len(inter) / max(len(a), len(b))


# ---------------------------------------------------------------------------
# 5. Self-knowledge profile (no hallucinated creator/company/model claims)
# ---------------------------------------------------------------------------

IDENTITY_RESPONSE = "Mera naam JARVIS hai. Main aapka personal AI assistant hoon."
CREATOR_RESPONSE = (
    "Main aapke JARVIS project ka assistant hoon. "
    "Mere creator ki specific information mere current knowledge profile mein configured nahi hai."
)
STATUS_RESPONSE = "Main bilkul theek hoon, Boss, aur aapki help ke liye ready hoon. Aap bataiye, kya karna hai?"
HELP_RESPONSE = (
    "Ji, zaroor. Aap mujhse applications open ya close karne, reminders set karne, "
    "system aur audio control, web search aur normal conversations mein help le sakte hain, Boss."
)
MEMORY_RESPONSE = (
    "Meri memory aapki batayi hui zaroori baatein yaad rakhti hai, Boss. "
    "Aap 'mera naam Rahul hai' jaise bolkar kuch yaad kara sakte hain, "
    "aur 'mera naam kya hai' poochkar wapas sun sakte hain."
)
LANGUAGE_RESPONSE = (
    "Main Hindi, English aur Hinglish teeno samajhta hoon, Boss. "
    "Aap jaise bolenge — 'Chrome kholo' ya 'open Chrome' — main samajh jaunga."
)
OFFLINE_RESPONSE = (
    "Haan, Boss. Main offline-first hoon — apps, reminders, system control aur conversations "
    "bina internet ke kaam karte hain. Web search aur live jaankari ke liye internet chahiye."
)
TECHNOLOGY_RESPONSE = (
    "Main aapke JARVIS project ka local voice assistant hoon, Boss — "
    "speech recognition, semantic intent detection, aur domain plugins se kaam karta hoon."
)
CAPABILITY_FOLLOWUP_EXTRA = (
    " Jaise: 'YouTube kholo', 'volume 50 karo', 'yaad dilana kal subah 7 baje', ya 'screen par kya hai'."
)


def _capability_response(norm: str) -> str:
    try:
        from core.conversational_intent import ConversationalIntentClassifier as _CIC
        is_en = norm.startswith("can you") or norm.startswith("could you") or norm.startswith(
            "what can you") or norm.startswith("what are you")
        return _CIC.CAPABILITY_GENERAL_RESP_EN if is_en else _CIC.CAPABILITY_GENERAL_RESP_HI
    except Exception:
        return (
            "Ji, bilkul! Main applications open/close kar sakta hoon, reminders set kar sakta hoon, "
            "audio/system control, web search aur normal conversations handle kar sakta hoon, Boss."
        )


# ---------------------------------------------------------------------------
# 6. Layered detection entrypoint
# ---------------------------------------------------------------------------

def _topic_hit(toks: set, topics: set) -> bool:
    return bool(toks & topics)


def _match_patterns(norm: str, toks: set, entities: Dict[str, str],
                    original: str) -> Optional[SelfIntentResult]:
    """Runs the pattern/topic layer in specificity order. Returns None if none."""
    has_self = _has_self_token(norm)

    # --- CREATOR first (so "creator ka naam" never falls into identity) ---
    for pat in _CREATOR_PATTERNS:
        if pat.search(norm):
            if _has_gk_entity(norm) and not has_self and "jarvis" not in norm:
                continue
            return _hit(SelfIntent.ASSISTANT_CREATOR_ORIGIN, 0.96, original, norm, entities, "pattern")

    # --- IDENTITY ---
    for pat in _IDENTITY_PATTERNS:
        if pat.search(norm):
            return _hit(SelfIntent.ASSISTANT_IDENTITY, 0.96, original, norm, entities, "pattern")

    # --- MEMORY (before status/capabilities: "yaad rakh sakte ho") ---
    if _topic_hit(toks, _MEMORY_TOPICS):
        return _hit(SelfIntent.ASSISTANT_MEMORY, 0.95, original, norm, entities, "pattern")
    for pat in _MEMORY_PATTERNS:
        if pat.search(norm):
            if pat.pattern == r"\bjaante\s+ho\b" and not (toks & {"mujhe", "mujhko"}):
                continue
            return _hit(SelfIntent.ASSISTANT_MEMORY, 0.95, original, norm, entities, "pattern")

    # --- LANGUAGE (before capabilities: "hindi me baat kar sakte ho") ---
    if _topic_hit(toks, _LANGUAGE_WORDS):
        return _hit(SelfIntent.ASSISTANT_LANGUAGE, 0.93, original, norm, entities, "pattern")
    for pat in _LANGUAGE_PATTERNS:
        if pat.search(norm):
            return _hit(SelfIntent.ASSISTANT_LANGUAGE, 0.93, original, norm, entities, "pattern")

    # --- OFFLINE (before capabilities: "offline me kya kar sakte ho") ---
    if _match_offline(norm, toks, has_self):
        return _hit(SelfIntent.ASSISTANT_OFFLINE, 0.93, original, norm, entities, "pattern")

    # --- STATUS ---
    status_hit = _match_status(norm, toks, has_self)
    if status_hit:
        return _hit(SelfIntent.ASSISTANT_STATUS, status_hit, original, norm, entities, "pattern")

    # --- TECHNOLOGY (before capabilities: "kaise kaam karte ho") ---
    tech_hit = _match_technology(norm, toks, has_self)
    if tech_hit:
        return _hit(SelfIntent.ASSISTANT_TECHNOLOGY, tech_hit, original, norm, entities, "pattern")

    # --- CAPABILITIES ---
    if _has_capability_target(norm):
        pass  # specific targets stay with the existing capability flow
    else:
        for pat in _CAPABILITY_PATTERNS:
            if pat.search(norm):
                return _hit(SelfIntent.ASSISTANT_CAPABILITIES, 0.96, original, norm, entities, "pattern")
        for mk in _ABILITY_MARKERS:
            if mk.search(norm):
                return _hit(SelfIntent.ASSISTANT_CAPABILITIES, 0.94, original, norm, entities, "pattern")
        # "how to do X" how-to guides belong to knowledge flows unless self-asked.
        if has_self and re.search(r"\bhow\s+to\s+do\b", norm):
            return _hit(SelfIntent.ASSISTANT_CAPABILITIES, 0.90, original, norm, entities, "pattern")
        if has_self and "uddeshya" in toks:
            return _hit(SelfIntent.ASSISTANT_CAPABILITIES, 0.90, original, norm, entities, "pattern")
        if has_self and _topic_hit(toks, _CAPABILITY_TOPICS):
            return _hit(SelfIntent.ASSISTANT_CAPABILITIES, 0.90, original, norm, entities, "pattern")

    # --- HELP ---
    for pat in _HELP_PATTERNS:
        if pat.search(norm):
            return _hit(SelfIntent.ASSISTANT_HELP, 0.94, original, norm, entities, "pattern")

    # --- GREETING (detected but deferred: existing greeting flow owns reply) ---
    for pat in _GREETING_PATTERNS:
        if pat.search(norm):
            r = SelfIntentResult(SelfIntent.ASSISTANT_GREETING, 0.90, original, norm,
                                 dict(entities), None, "SELF_KNOWLEDGE", None, "pattern")
            _log(r)
            return r
    return None


def _match_offline(norm: str, toks: set, has_self: bool) -> bool:
    if "offline" in toks or ("local" in toks and "mode" in toks):
        return True
    for pat in _OFFLINE_PATTERNS:
        if pat.search(norm):
            return True
    if "flight" in toks or "jahaz" in toks:
        return True
    net = toks & _OFFLINE_NET
    if not net:
        return False
    if toks & _OFFLINE_DEVICE_VERBS:
        return False
    if _has_device_entity(norm) and not has_self and "offline" not in toks:
        return False
    if has_self:
        return True
    # Without an explicit self-reference, require a strong offline-context word
    # so device-status questions ("wifi on hai kya") never get hijacked.
    return bool(toks & _OFFLINE_STRONG)


def _match_status(norm: str, toks: set, has_self: bool) -> float:
    if any(t.startswith("rememb") for t in toks):
        return 0.0  # "are you good at remembering" is memory, not status
    for pat in _STATUS_PATTERNS[:6]:
        if pat.search(norm):
            return 0.94
    for pat in _STATUS_PATTERNS[6:]:
        if pat.pattern == r"\bkaise\s+h(o|ain)\b":
            if pat.search(norm) and (has_self or toks & _STATUS_VOCATIVES):
                return 0.94
        elif pat.pattern == r"\bkya\s+chal\s+raha\s+hai\b":
            if pat.search(norm) and has_self:
                return 0.93
        elif pat.pattern == r"\bmehsoos\b":
            if pat.search(norm) and "main" not in toks and "mujhe" not in toks:
                return 0.93
        elif pat.search(norm):
            return 0.93
    if has_self and _topic_hit(toks, _STATUS_TOPICS):
        return 0.90
    return 0.0


def _match_technology(norm: str, toks: set, has_self: bool) -> float:
    for pat in _TECH_PATTERNS:
        if pat.search(norm):
            return 0.94
    if _topic_hit(toks, {"samajhte"}) and "kaise" in toks:
        return 0.90
    if has_self and _topic_hit(toks, _TECH_TOPICS):
        # "system" alone is a device noun; require a question shape.
        if "system" in toks and "kya" not in toks and "kaise" not in toks:
            return 0.0
        return 0.90
    # Distinctive bare tech nouns (no self-reference needed).
    if _topic_hit(toks, {"source", "version", "principle", "robot"}):
        if "open" in toks or "version" in toks or "principle" in toks or "robot" in toks:
            return 0.88
    return 0.0


def detect_self_intent(
    text: str,
    raw_text: Optional[str] = None,
    last_intent: Optional[str] = None,
) -> SelfIntentResult:
    """Layered semantic detection. Never raises; returns UNKNOWN on failure."""
    try:
        original = (raw_text if raw_text is not None else text) or ""
        _, norm = normalize_self_text(text or "")
        if not norm:
            return SelfIntentResult(SelfIntent.UNKNOWN, 0.0, original, norm)

        toks = set(_tokens(norm))
        entities: Dict[str, str] = {}
        if "jarvis" in toks:
            entities["assistant"] = "JARVIS"
        elif _has_self_token(norm):
            entities["assistant"] = "JARVIS"

        # Layer 0: hard guards — existing flows own their queries.
        if _COMMAND_GUARD_RE.search(norm):
            return SelfIntentResult(SelfIntent.UNKNOWN, 0.0, original, norm, entities)
        # Model questions belong to the model-disambiguation flow in app.py.
        if "model" in toks:
            return SelfIntentResult(SelfIntent.UNKNOWN, 0.0, original, norm, entities)
        # User-own-data guard (profile memory / GK own their queries).
        # Only fires for actual stored-data questions; help pleas ("mujhe help
        # chahiye") and ability questions ("meri madad kar sakte ho") are about
        # the assistant and must proceed.
        if (_USER_WORDS.search(norm) and not _BENEFACTIVE_RE.search(norm)
                and "yaad" not in toks and "remember" not in toks and "memory" not in toks):
            if toks & _USER_DATA_WORDS:
                return SelfIntentResult(SelfIntent.UNKNOWN, 0.0, original, norm, entities)

        # Layer 1: exact phrase / alias match.
        if norm in _IDENTITY_PHRASES:
            return _hit(SelfIntent.ASSISTANT_IDENTITY, 0.97, original, norm, entities, "phrase")
        if norm in _CREATOR_PHRASES:
            return _hit(SelfIntent.ASSISTANT_CREATOR_ORIGIN, 0.96, original, norm, entities, "phrase")

        # Layer 2: semantic patterns / topic rules.
        hit = _match_patterns(norm, toks, entities, original)
        if hit is not None:
            return hit

        # Layer 3: guarded fuzzy fix then re-run pattern layer once.
        fixed_tokens, changed = _try_fuzzy_fix(norm.split())
        if changed:
            fixed = " ".join(fixed_tokens)
            hit = _match_patterns(fixed, set(fixed_tokens), entities, original)
            if hit is not None:
                hit.confidence = min(hit.confidence, 0.88)
                hit.matched_by = "fuzzy"
                hit.normalized_text = fixed
                _log(hit)
                return hit
            norm = fixed  # fall through to overlap with the fixed form
            toks = set(fixed_tokens)

        # Layer 4: token-overlap similarity against seed exemplars.
        best_intent = SelfIntent.UNKNOWN
        best_score = 0.0
        for intent, seeds in _OVERLAP_SEEDS.items():
            for seed in seeds:
                s = _overlap_score(norm, seed)
                if s > best_score:
                    best_score = s
                    best_intent = intent
        if best_intent != SelfIntent.UNKNOWN and best_score >= 0.5:
            if best_intent == SelfIntent.ASSISTANT_CREATOR_ORIGIN:
                if _has_gk_entity(norm) and not _has_self_token(norm) and "jarvis" not in norm:
                    pass
                else:
                    return _hit(best_intent, 0.82, original, norm, entities, "overlap")
            elif best_intent == SelfIntent.ASSISTANT_GREETING:
                pass  # greeting stays with the existing greeting flow
            elif best_intent == SelfIntent.ASSISTANT_CAPABILITIES and _has_capability_target(norm):
                pass  # specific targets stay with the existing capability flow
            else:
                return _hit(best_intent, 0.82, original, norm, entities, "overlap")

        # Layer 5: conversation context for short follow-ups.
        if last_intent:
            if _BARE_CREATOR_FOLLOWUP.match(norm) and last_intent in (
                "ASSISTANT_IDENTITY", "ASSISTANT_CREATOR_ORIGIN",
            ):
                r = _hit(SelfIntent.ASSISTANT_CREATOR_ORIGIN, 0.90, original, norm, entities, "context")
                r.context = "JARVIS_SELF_REFERENCE"
                _log(r)
                return r
            if _BARE_CAPABILITY_FOLLOWUP.match(norm) and last_intent in (
                "ASSISTANT_CAPABILITIES", "ASSISTANT_HELP",
            ):
                r = _hit(SelfIntent.ASSISTANT_CAPABILITIES, 0.80, original, norm, entities, "context")
                r.context = "CAPABILITY_CONTINUATION"
                _log(r)
                return r

        return SelfIntentResult(SelfIntent.UNKNOWN, 0.0, original, norm, entities)
    except Exception as exc:  # never break the pipeline
        logger.debug("detect_self_intent note: %s", exc)
        return SelfIntentResult(SelfIntent.UNKNOWN, 0.0, text or "", "")


def _hit(intent: SelfIntent, conf: float, original: str, norm: str,
         entities: Dict[str, str], by: str) -> SelfIntentResult:
    r = SelfIntentResult(intent, conf, original, norm, dict(entities),
                         "JARVIS_SELF_REFERENCE", "SELF_KNOWLEDGE", None, by)
    r.response_text = get_self_response(r)
    _log(r)
    return r


def _log(r: SelfIntentResult) -> None:
    logger.info(
        "[SELF_INTENT] ORIGINAL=%r NORMALIZED=%r INTENT=%s CONF=%.2f CONTEXT=%s SOURCE=%s BY=%s",
        r.original_text, r.normalized_text, r.intent.value, r.confidence,
        r.context or "-", r.response_source, r.matched_by,
    )


def get_self_response(result: SelfIntentResult) -> Optional[str]:
    """Maps a detected self intent to its knowledge response (None = defer)."""
    if result.intent == SelfIntent.ASSISTANT_IDENTITY:
        return IDENTITY_RESPONSE
    if result.intent == SelfIntent.ASSISTANT_CREATOR_ORIGIN:
        return CREATOR_RESPONSE
    if result.intent == SelfIntent.ASSISTANT_CAPABILITIES:
        base = _capability_response(result.normalized_text or "")
        if result.context == "CAPABILITY_CONTINUATION":
            return base + CAPABILITY_FOLLOWUP_EXTRA
        return base
    if result.intent == SelfIntent.ASSISTANT_STATUS:
        return STATUS_RESPONSE
    if result.intent == SelfIntent.ASSISTANT_HELP:
        return HELP_RESPONSE
    if result.intent == SelfIntent.ASSISTANT_MEMORY:
        return MEMORY_RESPONSE
    if result.intent == SelfIntent.ASSISTANT_LANGUAGE:
        return LANGUAGE_RESPONSE
    if result.intent == SelfIntent.ASSISTANT_OFFLINE:
        return OFFLINE_RESPONSE
    if result.intent == SelfIntent.ASSISTANT_TECHNOLOGY:
        return TECHNOLOGY_RESPONSE
    # GREETING intentionally deferred to the existing greeting flow; UNKNOWN defers.
    return None
