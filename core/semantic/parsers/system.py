# core/semantic/parsers/system.py
"""System-level operations parser for power, maintenance, audio, screen, bluetooth, security, and network."""

from difflib import SequenceMatcher
import re
from typing import Any, Optional

from core.semantic.models import IntentName, SemanticAction

# --- System Control Precompiled Patterns ---
LOCK_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\b(?:system|pc|computer|laptop|screen|desktop|my\s+computer|my\s+pc)\s+lock\b',
        r'\block\s+(?:system|pc|computer|laptop|screen|desktop|my\s+computer|my\s+pc)\b',
        r'\b(?:system|pc|computer|laptop|screen)\s+ko\s+lock\b',
        r'\b(?:pc|screen|computer|system|laptop)\s+lock\s+(?:karo|kar\s+do|kar\s+de|kijiye)\b',
        r'^system\s+lock$', r'^pc\s+lock$', r'^screen\s+lock$', r'^lock\s+pc$', r'^lock\s+screen$'
    ]
]
RESTART_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\b(?:system|pc|computer|laptop)\s+(?:restart|reboot|retstart|restat|restard|rebote)\b',
        r'\b(?:restart|reboot|retstart|restat|restard|rebote)\s+(?:the\s+)?(?:system|pc|computer|laptop)\b',
        r'\b(?:pc|computer|system|laptop)\s+(?:restart|reboot|retstart|restat|restard)\s+(?:karo|kar\s+do)\b',
        r'\b(?:reboot|rebote)\b'
    ]
]
JARVIS_RELOAD_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\b(?:jarvis|program)\s+(?:restart|reload)\b',
        r'\b(?:restart|reload)\s+(?:jarvis|program)\b',
        r'\b(?:jarvis|program)\s+ko\s+(?:restart|reload)\s*(?:karo|kar\s+do)?\b',
        r'\b(?:live\s+)?auto\s*update\s*(?:karo|kar\s+do)?\b',
        r'^restart\s+jarvis$', r'^reload\s+jarvis$', r'^jarvis\s+restart$', r'^jarvis\s+reload$'
    ]
]
SHUTDOWN_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\b(?:system|pc|computer|laptop)\s+(?:shutdown|shatdown|sutdown|shutdon)\b',
        r'\b(?:shutdown|shatdown|sutdown|shutdon)\s+(?:the\s+)?(?:system|pc|computer|laptop)\b',
        r'\b(?:pc|computer|system|laptop)\s+band\s+(?:karo|kar\s+do)\b',
        r'\bturn\s+off\s+(?:the\s+)?(?:pc|computer|system|laptop)\b',
        r'\bpower\s+off\b'
    ]
]
IS_LOCK_RE = re.compile(
    r'\b(?:lock\s+pc|lock\s+screen|lock\s+system|lock\s+(?:my\s+)?computer|system\s+lock|pc\s+lock|screen\s+lock|laptop\s+lock)\b',
    re.IGNORECASE
)
IS_RESTART_RE = re.compile(r'\b(?:restart|reboot|retstart|restat|restard|rebote)\b', re.IGNORECASE)
IS_SHUTDOWN_RE = re.compile(r'\b(?:shut\s*down|turn\s+off|power\s+off|shatdown|sutdown|shutdon)\b', re.IGNORECASE)
IS_BAND_RE = re.compile(r'\b(?:pc|computer|system)\s+band\s+(?:karo|kar\s+do|kardo)\b', re.IGNORECASE)

# --- Maintenance Precompiled Patterns ---
RECYCLE_BIN_TARGET_RE = re.compile(
    r"\b(?:recycle\s*bin|recyclebin|trash(?:\s*can)?|dustbin|kachra\s*(?:dabba|dibba)?)\b",
    re.IGNORECASE
)
TEMP_FILES_TARGET_RE = re.compile(
    r"\b(?:temp|temporary)\b(?:\s+(?:files?|data|folders?|dirs?|directory))?|\b(?:files?|data|folder)\s+temp\b",
    re.IGNORECASE
)
CLEANUP_ACTION_RE = re.compile(
    r"\b(?:clear|clean|cleanup|delete|remove|erase|saaf|khali|empty|hatao|hata)\b",
    re.IGNORECASE
)
MODIFIER_BHI_RE = re.compile(r"\b(?:bhi|also|as\s+well|too)\b", re.IGNORECASE)

# --- Audio Precompiled Patterns ---
SET_VOL_RE = re.compile(r'\b(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})\b', re.IGNORECASE)
SET_VOL_FLEXIBLE_RE = re.compile(
    r'\b(?:set\s+)?(?:volume|awaaz|awaz|sound)\s+(?:to\s+|ko\s+)?(\d{1,3})\s*(?:percent|%|pe)?\b|\b(\d{1,3})\s*(?:percent|%)\s*(?:volume|awaaz|awaz|sound)?\b|\b(?:volume|awaaz|awaz|sound)\s+(\d{1,3})\s*(?:percent|%|pe)?\s*(?:karo|kar\s+do|kardo|kijiye|set\s+karo)?\b',
    re.IGNORECASE
)
VOL_DOWN_IDIOMS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\b(?:(?:awaaz|awaz|sound)\s+)?(?:bahut\s+)?(?:tez|zyada|loud)\s+hai\b',
        r'\b(?:awaaz|awaz)\s+kaan\s+(?:phad|faad|phat|dard)\s*(?:rahi\s+hai|raha\s+hai|kar\s+rahe\s+hain|rahe\s+hain)\b',
        r'\bkaan\s+(?:phad|faad|phat|dard)\s*(?:rahe\s+hain|kar\s+rahe\s+hain|raha\s+hai)\b',
        r'\b(?:bahut\s+)?shor\s+(?:hai|ho\s+raha\s+hai|kam\s+karo)\b',
        r'\b(?:awaaz|awaz|sound)\s+(?:dheere|dheemi|kam)\s+(?:karo|kar\s+do|kijiye)\b',
        r'\b(?:dheere|dheemi)\s+karo\b',
        r'\b(?:volume|sound|awaz|awaaz)\s+down\b',
        r'\b(?:volume|sound|awaz|awaaz)\s+kam\s+(?:karo|kar\s+do|kardo)\b',
        r'\bdecrease\s+(?:the\s+)?volume\b',
    ]
]
VOL_UP_IDIOMS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\b(?:awaaz|awaz|sound)\s+nahi\s+aa\s+rahi(?:\s+hai)?\b',
        r'\b(?:kuch\s+)?sunai\s+nahi\s+(?:de\s+raha|pad\s+raha|aa\s+raha)(?:\s+hai)?\b',
        r'\b(?:awaaz|awaz|sound)\s+(?:bahut\s+)?(?:kam|dheemi|low)\s+hai\b',
        r'\b(?:thoda\s+)?tez\s+(?:bolo|karo|kar\s+do)\b',
        r'\b(?:awaaz|awaz|sound)\s+(?:badhao|tez\s+karo|up\s+karo|increase\s+karo)\b',
        r'\b(?:volume|sound|awaz|awaaz)\s+up\b',
        r'\bincrease\s+(?:the\s+)?volume\b',
    ]
]
VOL_AMBIGUOUS_RE = re.compile(
    r'^(?:(?:jarvis|please|bhai|yaar)\s+)?(?:volume|awaaz|awaz|sound)\s+(?:adjust|theek|thik|sahi|set)\s*(?:karo|kar\s+do|kardo|kijiye)?$|^(?:adjust|fix)\s+(?:the\s+)?(?:volume|sound|audio)$',
    re.IGNORECASE
)

# --- Bluetooth Precompiled Patterns ---
BT_CLEAN_RE = re.compile(r'\b(bluetooth|bt|connect|karo|ko|se|pair|device)\b', re.IGNORECASE)

# --- Face Auth Precompiled Patterns ---
FACE_ENROLL_RE1 = re.compile(r"\b(?:enroll|register|scan|capture|add|save)\b", re.IGNORECASE)
FACE_ENROLL_RE2 = re.compile(r"\b(?:face|chehra|biometrics?)\b", re.IGNORECASE)
FACE_ENROLL_RE3 = re.compile(r"\b(?:face|chehra)\s+(?:register|enroll|scan|save)(?:\s+(?:karo|kar\s+do|kijiye))?\b", re.IGNORECASE)
FACE_STATUS_RE1 = re.compile(r"\b(?:face\s+auth|face\s+authentication|face\s+lock|biometric\s+lock)\b", re.IGNORECASE)
FACE_STATUS_RE2 = re.compile(r"\b(?:status|enabled\s+hai\s+kya|check|on\s+hai\s+kya|kaisa\s+hai)\b", re.IGNORECASE)
FACE_STATUS_RE3 = re.compile(r"\b(?:check|is|status\s+of)\s+(?:face\s+auth|face\s+authentication|face\s+lock)\b", re.IGNORECASE)
FACE_DISABLE_RE1 = re.compile(r"\b(?:face\s+auth|face\s+authentication|face\s+lock|biometric\s+lock)\b.*\b(?:band|disable|off|turn\s+off|deactivate)\b", re.IGNORECASE)
FACE_DISABLE_RE2 = re.compile(r"\b(?:disable|turn\s+off|band\s+karo)\b.*\b(?:face\s+auth|face\s+authentication|face\s+lock)\b", re.IGNORECASE)
FACE_ENABLE_RE1 = re.compile(r"\b(?:face\s+auth|face\s+authentication|face\s+lock|biometric\s+lock)\b.*\b(?:chalu|enable|on|turn\s+on|activate)\b", re.IGNORECASE)
FACE_ENABLE_RE2 = re.compile(r"\b(?:enable|turn\s+on|chalu\s+karo)\b.*\b(?:face\s+auth|face\s+authentication|face\s+lock)\b", re.IGNORECASE)

# --- Network Precompiled Patterns ---
WIFI_RE = re.compile(r"\b(?:wifi|wi-fi|wireless|network)\b", re.IGNORECASE)
PASSWORD_RE = re.compile(r"\b(?:password|passcode|key|pwd)\b", re.IGNORECASE)
WORD_FIND_RE = re.compile(r"[a-z]+")
SSID_RE = re.compile(
    r"(?:wifi|wi-fi|wireless)\s+['\"]?([^'\"]+?)['\"]?\s+(?:ka|ki)?\s*(?:password|passcode|key)",
    re.IGNORECASE
)
WIFI_CONFIRM_RE = re.compile(r"\b(?:pass|pas|pwd|credential|secret|pin)\b", re.IGNORECASE)
SPEED_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(?:internet|wifi|wi-fi|network)\s+(?:ki\s+)?speed\b",
        r"\bspeed\s*test\b",
        r"\b(?:download|upload)\s+speed\b",
        r"\bnet\s+(?:ki\s+)?speed\b"
    ]
]

# --- Screen Inspection Precompiled Patterns ---
CAP_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\b(?:kya\s+)?(?:tum\s+)?(?:meri\s+)?(?:laptop\s+)?screen\s+(?:ko\s+)?(?:dekh|view)\s+(?:sakte\s*y?\s*ho|pa\s+rahe\s+ho|rahe\s+ho)\b',
        r'\b(?:kya\s+)?(?:meri\s+)?screen\s+dikh\s+rahi\s+hai\b',
        r'\b(?:tumhe\s+)?screen\s+(?:dikh|nazar\s+aa)\s+rahi\s+hai\b',
        r'\b(?:dekh\s+sakte\s*y?\s*ho\s+kya\s+(?:meri\s+)?screen)\b',
        r'\b(?:are\s+you\s+able\s+to\s+see|can\s+you\s+see|can\s+you\s+view|can\s+you\s+look\s+at)\s+(?:what\s+is\s+on\s+)?(?:my\s+|the\s+)?(?:laptop\s+)?screen\b',
        r'\b(?:is\s+my\s+screen\s+visible\s+to\s+you)\b'
    ]
]
WIN_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\b(?:laptop\s+ki\s+screen|screen|desktop)\s+(?:pe|par|mein)?\s*(?:konsi|kaunsi|kaun\s+kaun\s+si)\s+(?:windows?|apps?)\b',
        r'\b(?:konsi|kaunsi|kaun\s+kaun\s+si)\s+(?:windows?|apps?)\s+(?:hai|open|khuli|chalu|running)\b',
        r'\b(?:what|which)\s+(?:windows|apps|applications)\s+(?:are\s+)?(?:currently\s+)?(?:open|running|active|visible)\b',
        r'\b(?:screen|laptop|desktop)\b.*\b(?:konsi|kaunsi)\s+windows?\b',
        r'\b(?:konsi|kaunsi)\s+windows?\b.*\b(?:screen|laptop|desktop)\b',
        r'\b(?:list|show|display)\s+(?:all\s+)?(?:open|active)\s+(?:windows|apps)\b'
    ]
]
SCREEN_GENERAL_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'(?:^|\b)(?:kya\s+)?(?:abhi\s+)?(?:screen|desktop|laptop\s+screen)\s+(?:par|pe|mein)?\s*(?:kya|kaun\s+kaun\s+se\s+apps?|kaunse\s+apps?)\s+(?:open|chalu|running|active|chal\s+rahe?|khula\s+hua|khule|hai)\b',
        r'(?:^|\b)(?:abhi\s+)?(?:screen|desktop)\s+(?:par|pe)?\s*(?:kya\s+hai|kya\s+open\s+hai|kya\s+chal\s+raha\s+hai)\b',
        r'(?:^|\b)(?:dekho|check\s+karo|batao)\s+(?:ki\s+)?(?:screen|desktop)\s+(?:par|pe)?\s*(?:kya\s+hai|kya\s+open\s+hai|kya\s+chal\s+raha\s+hai)\b',
        r'\bwhat(?:\'s|\s+is)\s+(?:currently\s+)?(?:open|running)\s+(?:on\s+)?(?:my\s+)?(?:screen|desktop)\b'
    ]
]

# --- Status Query Precompiled Patterns ---
STATUS_PATTERNS = [
    re.compile(r"^(?:kya\s+)?(?:check\s+karo\s+(?:ki\s+)?|dekho\s+(?:ki\s+)?|batao\s+(?:ki\s+)?|is\s+)?(.+?)\s+(?:open|chalu|running|active|chal\s+raha|chal\s+rahi|khula\s+hua|khula|khuli|on)\s+hai(?:\s+kya)?$", re.IGNORECASE),
    re.compile(r"^(?:kya\s+)?(.+?)\s+(?:open|chalu|running|active)\s+nahi\s+hai(?:\s+na)?$", re.IGNORECASE),
    re.compile(r"^is\s+(.+?)\s+not\s+(?:open|running|active)$", re.IGNORECASE),
    re.compile(r"^(?:kaunsa|kaunsi|konsa|which)\s+(.+?)\s+(?:window|tab)?\s*(?:open|active|chal\s+raha)\s+hai(?:\s+kya)?$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+(?:ka\s+)?(?:kaunsa|kaunsi|konsa|which)\s+(?:window|tab)?\s*(?:open|active|chal\s+raha)\s+hai(?:\s+kya)?$", re.IGNORECASE),
    re.compile(r"^is\s+(.+?)\s+(?:open|running|active|launched|on)$", re.IGNORECASE),
    re.compile(r"^check\s+(?:if\s+)?(.+?)\s+is\s+(?:open|running|active|on)$", re.IGNORECASE),
    re.compile(r"^kya\s+(.+?)\s+(?:chal\s+raha\s+hai|chal\s+rahi\s+hai|open\s+hai|chalu\s+hai|running\s+hai)$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+(?:open|chalu|running)\s+hai$", re.IGNORECASE)
]
TARGET_CLEAN_RE = re.compile(r"\b(?:app|application|browser|website|site|program|window|tab|please|yaar|jarvis|bhai)\b", re.IGNORECASE)


def parse_system_control(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Detects system restart, shutdown, lock, and sleep requests."""
    # Guard: Never treat capability questions, status inquiries, past status checks, or troubleshooting as commands
    is_non_command = bool(
        any(w in lowered for w in [
            "sakte ho", "sakti ho", "sakte hain", "kar paoge", "can you", "could you", "able to",
            "hai kya", "hua kya", "ho gaya kya", "kyun nahi", "kyu nahi", "why isn't", "why did", "kaise karein", "kaise hota hai"
        ])
        or (lowered.startswith("kya ") and not any(k in lowered for k in ["karo", "kar do", "kardo", "please"]))
        or lowered.endswith("?")
    )
    if is_non_command:
        return None

    # 1. Lock Workstation
    is_lock = bool(
        not any(v in lowered for v in ("click", "double click", "doubleclick", "kahan", "kidhar", "locate"))
        and (
            IS_LOCK_RE.search(lowered)
            or any(re.search(rf"\b{re.escape(w)}\b", lowered) for w in ["lock karo", "lock kar do", "lock kardo", "lock computer"])
            or any(pat.search(lowered) for pat in LOCK_PATTERNS)
        )
    )
    if is_lock:
        return SemanticAction(
            intent="LOCK_SYSTEM",
            service="system",
            action="lock_pc",
            query=raw_text,
            parameters={}
        )

    # 1b. Restart / Reload Jarvis Application (not PC)
    is_jarvis_reload = any(pat.search(lowered) for pat in JARVIS_RELOAD_PATTERNS) or (
        ("jarvis" in lowered or "program" in lowered) and ("restart" in lowered or "reload" in lowered)
    )
    if is_jarvis_reload and not any(w in lowered for w in ["computer", "pc", "laptop", "machine"]):
        return SemanticAction(
            intent="JARVIS_RESTART",
            service="system",
            action="restart_jarvis",
            query=raw_text,
            parameters={"query": raw_text}
        )

    # 2. Restart PC
    from core.semantic.lexicon import LexiconEngine
    is_restart = bool(
        LexiconEngine.is_system_restart_utterance(lowered)
        or (IS_RESTART_RE.search(lowered) and any(w in lowered for w in ["system", "pc", "computer", "machine", "karo", "kardo", "kar do", "the pc"]))
        or any(pat.search(lowered) for pat in RESTART_PATTERNS)
    )
    if is_restart:
        return SemanticAction(
            intent="SYSTEM_RESTART",
            service="system",
            action="shutdown_pc",
            query=raw_text,
            parameters={"restart": True, "query": raw_text}
        )

    # 3. Shutdown PC
    is_shutdown = bool(
        (IS_SHUTDOWN_RE.search(lowered) and any(w in lowered for w in ["system", "pc", "computer", "machine", "karo", "kardo", "kar do", "the pc", "the computer"]))
        or IS_BAND_RE.search(lowered)
        or any(pat.search(lowered) for pat in SHUTDOWN_PATTERNS)
    )
    if is_shutdown:
        return SemanticAction(
            intent="SYSTEM_SHUTDOWN",
            service="system",
            action="shutdown_pc",
            query=raw_text,
            parameters={"restart": False, "query": raw_text}
        )

    # 4. Sleep PC
    if any(w in lowered for w in ["system sleep", "sleep pc", "pc sleep karo", "computer sleep karo"]):
        return SemanticAction(
            intent="SLEEP_SYSTEM",
            service="system",
            action="sleep_pc",
            query=None,
            parameters={}
        )

    return None


def parse_system_maintenance(lowered: str, context: Optional[Any] = None) -> Optional[SemanticAction]:
    """
    Routes system maintenance and cleanup commands (temp files, recycle bin, indirect cleanup)
    using the authoritative UniversalGoalResolver.
    """
    from core.semantic.goal_resolver import UniversalGoalResolver
    from core.semantic.resolution import ResolutionDecision

    res = UniversalGoalResolver.resolve(lowered, context=context)
    if res.goal in ("TEMP_FILE_CLEANUP", "RECYCLE_BIN_CLEANUP", "SYSTEM_CLEANUP"):
        if res.decision in (ResolutionDecision.EXECUTE, ResolutionDecision.ASK_PRECISE_CLARIFICATION):
            return res.to_semantic_action()

    return None


def parse_software_update(raw_text: str, lowered: str, context: Optional[Any] = None) -> Optional[SemanticAction]:
    """
    Routes software and Windows update commands (WinGet, Windows Update, Store, check, install, cancel)
    using the authoritative UniversalGoalResolver.
    """
    from core.semantic.goal_resolver import UniversalGoalResolver
    from core.semantic.resolution import ResolutionDecision

    # Guard: Never treat capability questions or informational requests as commands
    is_non_command = bool(
        any(w in lowered for w in [
            "sakte ho", "sakti ho", "sakte hain", "kar paoge", "can you", "could you", "able to",
            "kaise karte hain", "kaise hota hai", "how to update", "what is", "kaise karein"
        ])
        or (lowered.startswith("kya ") and not any(k in lowered for k in ["karo", "kar do", "kardo", "please", "install", "check"]))
        or (lowered.endswith("?") and not any(k in lowered for k in ["check", "update"]))
    )
    if is_non_command:
        return None

    res = UniversalGoalResolver.resolve(raw_text, context=context)
    if res.goal in ("UPDATE_INSTALLED_SOFTWARE", "UPDATE_WINDOWS", "CHECK_FOR_UPDATES", "EXECUTE_UPDATE_PLAN", "CANCEL_UPDATE"):
        if res.decision in (ResolutionDecision.EXECUTE, ResolutionDecision.ASK_PRECISE_CLARIFICATION):
            return res.to_semantic_action()

    return None


def parse_equity_research(raw_text: str, lowered: str, context: Optional[Any] = None) -> Optional[SemanticAction]:
    """
    Routes Indian equity research, stock suggestions, single-stock analysis, and market regime queries
    using the authoritative UniversalGoalResolver.
    """
    from core.semantic.goal_resolver import UniversalGoalResolver
    from core.semantic.resolution import ResolutionDecision

    # Guard 1: Definitional and educational queries (e.g., "stock kya hota hai?", "what is a stock?")
    # must be handled as general knowledge / education, NEVER equity research.
    if any(p in lowered for p in [
        "kya hota hai", "kya hoti hai", "kya hote hain", "ka matlab kya", "ki definition",
        "what is a stock", "what is stock", "what are stocks", "what is share", "what are shares",
        "stock definition", "meaning of stock", "meaning of share", "kyun kehte hain"
    ]):
        return None

    # Guard 2: Generic market news queries (e.g., "stock market mein aaj kya hua?")
    if any(p in lowered for p in [
        "aaj kya hua", "kya hua aaj", "today news", "market news", "aaj kyu gira", "aaj kyu badha"
    ]):
        return None

    # Guard 3: Portfolio review requests ("mere portfolio ka review karo")
    if "portfolio" in lowered and any(w in lowered for w in ["review", "check", "dekho"]):
        return None

    res = UniversalGoalResolver.resolve(raw_text, context=context)
    if res.goal in (
        "SHORT_TERM_INVESTMENT_RESEARCH",
        "FIND_OR_SUGGEST_EQUITY",
        "ANALYZE_STOCK_SETUP",
        "MARKET_REGIME_QUERY",
        "MONITOR_EQUITY_THESIS",
    ):
        if res.decision in (
            ResolutionDecision.EXECUTE,
            ResolutionDecision.ASK_PRECISE_CLARIFICATION,
            ResolutionDecision.CLARIFY,
            ResolutionDecision.ANSWER,
        ):
            return res.to_semantic_action()

    return None


def parse_audio_control(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Handles audio volume, mute, unmute, colloquial volume idioms, and directional ambiguity."""
    # 1. Directional Ambiguity Gate: e.g. "volume adjust karo", "awaaz theek karo"
    if VOL_AMBIGUOUS_RE.search(lowered):
        return SemanticAction(
            intent="SET_VOLUME",
            service="audio",
            action="adjust_volume",
            parameters={"workflow_type": "VOLUME_ADJUST"},
            needs_clarification=True,
            clarification_prompt="Volume badhana hai ya kam karna hai?",
            missing_slot="direction",
            confidence=0.90,
        )

    # 2. Explicit Volume Setting with Numbers: "volume 50 karo", "awaz 80%", etc.
    vol_match = SET_VOL_FLEXIBLE_RE.search(lowered) or SET_VOL_RE.search(lowered)
    if vol_match:
        val_str = vol_match.group(1) or (vol_match.group(2) if vol_match.lastindex >= 2 else None) or (vol_match.group(3) if vol_match.lastindex >= 3 else None)
        if val_str and val_str.isdigit():
            level = max(0, min(100, int(val_str)))
            return SemanticAction(
                intent="SET_VOLUME",
                service="audio",
                action="set_volume",
                query=str(level),
                parameters={"level": level},
                confidence=1.0,
            )

    # 3. Colloquial Idioms for Volume Down: "awaaz kaan phad rahi hai", "bahut tez hai", etc.
    if any(pat.search(lowered) for pat in VOL_DOWN_IDIOMS):
        return SemanticAction(
            intent="VOLUME_DOWN",
            service="audio",
            action="volume_down",
            query=None,
            parameters={"step": 10, "idiom": True},
            confidence=0.95,
        )

    # 4. Colloquial Idioms for Volume Up: "awaaz nahi aa rahi", "kuch sunai nahi de raha", etc.
    if any(pat.search(lowered) for pat in VOL_UP_IDIOMS):
        return SemanticAction(
            intent="VOLUME_UP",
            service="audio",
            action="volume_up",
            query=None,
            parameters={"step": 10, "idiom": True},
            confidence=0.95,
        )

    # 5. Standard Volume Up phrases
    if any(w in lowered for w in ["volume badhao", "awaz badhao", "sound badhao", "volume up", "increase volume", "volume tez karo"]):
        return SemanticAction(
            intent="VOLUME_UP",
            service="audio",
            action="volume_up",
            query=None,
            parameters={"step": 10}
        )

    # 6. Standard Volume Down phrases
    if any(w in lowered for w in ["volume kam karo", "awaz kam karo", "sound kam karo", "volume down", "decrease volume", "volume dheere karo"]):
        return SemanticAction(
            intent="VOLUME_DOWN",
            service="audio",
            action="volume_down",
            query=None,
            parameters={"step": 10}
        )

    # 7. Unmute
    if any(w in lowered for w in ["unmute karo", "sound unmute", "unmute audio", "unmute sound"]) or lowered == "unmute":
        return SemanticAction(
            intent="UNMUTE_AUDIO",
            service="audio",
            action="unmute",
            query=None,
            parameters={}
        )

    # 8. Mute
    if any(w in lowered for w in ["mute karo", "sound mute", "mute audio", "chup ho jao", "mute sound"]) or lowered == "mute":
        return SemanticAction(
            intent="MUTE_AUDIO",
            service="audio",
            action="mute",
            query=None,
            parameters={}
        )

    return None



def parse_screen_control(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Handles screenshot, screen recording, and monitor brightness."""
    if any(w in lowered for w in ["screenshot lo", "take screenshot", "capture screen", "screenshot karo", "screenshot", "screen capture", "screen snapshot"]):
        return SemanticAction(
            intent="SCREENSHOT",
            service="screen",
            action="take_screenshot",
            query=None,
            parameters={}
        )

    # Hinglish photo synonyms — screen co-occurrence required so bare "photo lo"
    # (camera/file ambiguity) never hijacks this branch.
    if "screen" in lowered and any(w in lowered for w in ["photo lo", "photo le lo", "photo khicho", "photo kheecho", "tasveer lo", "picture lo"]):
        return SemanticAction(
            intent="SCREENSHOT",
            service="screen",
            action="take_screenshot",
            query=None,
            parameters={"via": "photo_synonym"}
        )

    if any(w in lowered for w in ["screen record karo", "start recording", "record screen", "recording chalu karo", "recording start karo"]):
        return SemanticAction(
            intent="RECORD_SCREEN",
            service="screen",
            action="start_recording",
            query=None,
            parameters={}
        )

    if any(w in lowered for w in ["stop recording", "recording band karo", "stop screen record", "recording rok do"]):
        return SemanticAction(
            intent="RECORD_SCREEN",
            service="screen",
            action="stop_recording",
            query=None,
            parameters={}
        )

    # Monitor brightness — mirrors the audio volume shape (explicit level,
    # relative up/down with step). Executor: screen plugin (set_screen_brightness
    # for levels, brightness_up/down relatives). Screen-scoped words only so
    # volume/audio phrasings never collide (audio parser runs earlier anyway).
    bright_match = re.search(
        r"\bbrightness\s+(?:ko\s+)?(\d{1,3})\s*(?:percent|%|pe)?\b|\b(\d{1,3})\s*(?:percent|%)\s*brightness\b"
        r"|\bbrightness\s+(\d{1,3})\s*(?:karo|kar\s+do|kardo|set\s+karo)?\b",
        lowered,
    )
    if bright_match:
        val_str = bright_match.group(1) or bright_match.group(2) or bright_match.group(3)
        if val_str and val_str.isdigit():
            level = max(0, min(100, int(val_str)))
            return SemanticAction(
                intent="SET_BRIGHTNESS",
                service="screen",
                action="set_screen_brightness",
                query=str(level),
                parameters={"level": level},
                confidence=1.0,
            )

    if any(w in lowered for w in [
        "brightness badhao", "brightness tez karo", "screen bright karo", "screen bright kar do",
        "brightness up karo", "brightness zyada karo", "ujala badhao", "roshni badhao",
        "increase brightness", "brightness increase karo", "display bright karo",
    ]):
        return SemanticAction(
            intent="BRIGHTNESS_UP",
            service="screen",
            action="brightness_up",
            query=None,
            parameters={"step": 15},
            confidence=0.95,
        )

    if any(w in lowered for w in [
        "brightness kam karo", "brightness dheere karo", "screen dim karo", "screen dim kar do",
        "brightness down karo", "brightness ghatao", "ujala kam karo", "roshni kam karo",
        "decrease brightness", "brightness decrease karo", "display dim karo",
    ]):
        return SemanticAction(
            intent="BRIGHTNESS_DOWN",
            service="screen",
            action="brightness_down",
            query=None,
            parameters={"step": 15},
            confidence=0.95,
        )

    if any(w in lowered for w in [
        "brightness kitni hai", "screen brightness kitni hai", "display brightness kitni hai",
        "brightness check karo", "current brightness",
    ]):
        return SemanticAction(
            intent="QUERY_BRIGHTNESS",
            service="screen",
            action="get_screen_brightness",
            query=None,
            parameters={},
            confidence=0.95,
        )

    return None


def parse_bluetooth_control(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Handles Bluetooth enable, disable, scan, connect, and status."""
    if "bluetooth" not in lowered and "bt" not in lowered:
        return None

    # Off / Disable
    if any(w in lowered for w in [
        "off karo", "off kar do", "band karo", "band kar do", "band", "turn off",
        "disable", "switch off", "off", "rok do"
    ]):
        return SemanticAction(
            intent="TOGGLE_BLUETOOTH",
            service="bluetooth",
            action="disable_bluetooth",
            query=raw_text,
            parameters={"enabled": False},
            confidence=1.0,
        )

    # On / Enable
    if any(w in lowered for w in [
        "on karo", "on kar do", "chalu karo", "chalu kar do", "chalu", "turn on",
        "enable", "switch on", "on"
    ]):
        return SemanticAction(
            intent="TOGGLE_BLUETOOTH",
            service="bluetooth",
            action="enable_bluetooth",
            query=raw_text,
            parameters={"enabled": True},
            confidence=1.0,
        )

    if any(w in lowered for w in ["scan", "dhoondo", "search"]):
        return SemanticAction(
            intent="SCAN_BLUETOOTH",
            service="bluetooth",
            action="scan",
            query=None,
            parameters={}
        )

    if any(w in lowered for w in ["connect", "jodo", "pair"]):
        dev = BT_CLEAN_RE.sub(' ', lowered).strip()
        return SemanticAction(
            intent="CONNECT_BLUETOOTH",
            service="bluetooth",
            action="connect",
            query=dev or "headphones",
            parameters={"device_name": dev or "headphones"}
        )

    return None


def parse_face_auth(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Routes face authentication and biometric enrollment commands to Security."""
    if (FACE_ENROLL_RE1.search(lowered) and FACE_ENROLL_RE2.search(lowered)) or FACE_ENROLL_RE3.search(lowered):
        if "status" not in lowered and "lock" not in lowered:
            return SemanticAction(
                intent="SECURITY_FACE_AUTH",
                service="security",
                action="enroll_face",
                parameters={"user_name": "Boss"},
                confidence=1.0,
            )

    if (FACE_STATUS_RE1.search(lowered) and FACE_STATUS_RE2.search(lowered)) or FACE_STATUS_RE3.search(lowered):
        return SemanticAction(
            intent="SECURITY_FACE_AUTH",
            service="security",
            action="get_status",
            parameters={},
            confidence=1.0,
        )

    if FACE_DISABLE_RE1.search(lowered) or FACE_DISABLE_RE2.search(lowered):
        return SemanticAction(
            intent="SECURITY_FACE_AUTH",
            service="security",
            action="disable_auth",
            parameters={},
            confidence=1.0,
        )

    if FACE_ENABLE_RE1.search(lowered) or FACE_ENABLE_RE2.search(lowered):
        return SemanticAction(
            intent="SECURITY_FACE_AUTH",
            service="security",
            action="enable_auth",
            parameters={},
            confidence=1.0,
        )

    return None


def parse_network(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Handles internet/Wi-Fi speed test and Wi-Fi password requests."""
    has_wifi = bool(WIFI_RE.search(lowered))
    password_words = WORD_FIND_RE.findall(lowered)
    password_similarity = max(
        (SequenceMatcher(None, word, "password").ratio() for word in password_words),
        default=0.0,
    )
    has_password_intent = bool(PASSWORD_RE.search(lowered)) or password_similarity >= 0.72

    if has_wifi and has_password_intent:
        if any(marker in lowered for marker in (
            "sabhi", "saare", "sare", "all", "saved", "past", "previous",
            "purane", "jitne", "profiles", "passwords",
        )):
            return SemanticAction(
                intent="LIST_SAVED_WIFI_PASSWORDS", service="network",
                action="list_saved_wifi_passwords", parameters={}, confidence=1.0,
            )
        ssid_match = SSID_RE.search(raw_text)
        ssid = ""
        if ssid_match:
            candidate = ssid_match.group(1).strip()
            if candidate.lower() not in {"ka", "ki", "kaa", "current", "connected"}:
                ssid = candidate
        return SemanticAction(
            intent="COPY_WIFI_PASSWORD",
            service="network",
            action="copy_wifi_password",
            parameters={"ssid": ssid},
            confidence=1.0,
        )

    if has_wifi and WIFI_CONFIRM_RE.search(lowered):
        return SemanticAction(
            intent="CONFIRM_WIFI_PASSWORD",
            service="network",
            action="copy_wifi_password",
            parameters={},
            needs_clarification=True,
            clarification_prompt="Kya aap Wi-Fi ka password jaanana chahte hain, Boss?",
            missing_slot="confirmation",
            confidence=0.6,
        )

    if any(pattern.search(lowered) for pattern in SPEED_PATTERNS):
        return SemanticAction(
            intent="MEASURE_INTERNET_SPEED",
            service="network",
            action="measure_speed",
            parameters={},
            confidence=1.0,
        )

    return None


def parse_screen_inspection(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Detects screen capability inquiries, window listing, and desktop activity inspection."""
    cleaned = lowered.strip(" .?!")

    is_english = any(w in cleaned for w in (
        "are you able to see", "can you see", "can you view", "can you look at",
        "what windows", "which windows", "what apps are open", "what is open on",
        "what is on screen", "show open windows", "list open windows"
    )) and not any(w in cleaned for w in (
        "kya", "tum", "aap", "meri", "mera", "mere", "dekh", "khula", "kaunsi",
        "konsi", "batao", "puchh", "raha", "rahe", "hai", "hain", "pe", "par"
    ))
    lang = "en" if is_english else "hi"

    cap_phrases = [
        "meri screen dekh sakte", "meri screen dekh pa rahe", "screen dekh saktey ho",
        "screen dekh sakte ho", "screen dekh pa rahe ho", "screen dekh rahe ho",
        "screen dikh rahi hai", "screen dikh rahi", "screen visible hai",
        "are you able to see my screen", "can you see my screen", "can you see the screen",
        "are you seeing my screen", "can you view my screen", "can you look at my screen",
        "can you see what is on my screen", "can you see what's on my screen",
        "are you able to see what is on my screen"
    ]
    if any(p in cleaned for p in cap_phrases) or any(pat.search(cleaned) for pat in CAP_PATTERNS):
        return SemanticAction(
            intent="SCREEN_INSPECTION",
            service="screen",
            action="inspect_screen",
            query=raw_text,
            parameters={"capability_query": True, "language": lang}
        )

    win_phrases = [
        "konsi windows hai", "konsi window hai", "kaunsi windows hai", "kaunsi window hai",
        "konsi windows open", "kaunsi windows open", "konsi window khuli", "kaunsi window khuli",
        "kaun kaun si windows", "kaun kaun se apps", "konsi apps open", "kaunsi apps open",
        "what windows are open", "which windows are open", "what apps are open",
        "list open windows", "show open windows", "list active windows"
    ]
    if any(p in cleaned for p in win_phrases) or any(pat.search(cleaned) for pat in WIN_PATTERNS):
        return SemanticAction(
            intent="SCREEN_INSPECTION",
            service="screen",
            action="inspect_screen",
            query=raw_text,
            parameters={"list_windows": True, "language": lang}
        )

    screen_phrases = [
        "screen par kya open hai", "screen par kya chal raha hai", "screen par kya hai",
        "screen par kya khula hai", "screen par kya dikh raha hai",
        "screen pe kya open hai", "screen pe kya chal raha hai", "screen pe kya hai",
        "screen pe kya khula hai", "screen pe kya dikh raha hai",
        "laptop screen par kya", "laptop screen pe kya", "desktop par kya open hai",
        "what is on screen", "what is on my screen", "what is open on my screen",
        "what is open on screen", "what is currently open", "what is currently running"
    ]
    if any(w in cleaned for w in screen_phrases) or any(pat.search(cleaned) for pat in SCREEN_GENERAL_PATTERNS):
        return SemanticAction(
            intent="SCREEN_INSPECTION",
            service="screen",
            action="inspect_screen",
            query=raw_text,
            parameters={"language": lang}
        )

    return None


def parse_status_query(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Detects status questions asking if an application, website, or window is open / running."""
    cleaned = lowered.strip(" .?!")
    has_question_context = (
        "?" in raw_text or "kya" in lowered or "check" in lowered
        or "dekho" in lowered or "batao" in lowered or lowered.startswith("is ")
    )

    for idx, pat in enumerate(STATUS_PATTERNS):
        if idx == len(STATUS_PATTERNS) - 1 and not has_question_context:
            continue
        m = pat.fullmatch(cleaned)
        if m:
            target = m.group(1).strip()
            if target.lower() in ("screen", "screen par", "screen par kya", "screen pe", "screen pe kya", "laptop screen", "desktop", "desktop par"):
                continue
            target = TARGET_CLEAN_RE.sub(" ", target)
            target = re.sub(r"\s+", " ", target).strip()
            if not target:
                continue
            app_map = {
                "yt": "youtube",
                "utube": "youtube",
                "calc": "calculator",
                "my computer": "explorer",
                "this pc": "explorer",
                "chrome browser": "chrome",
                "brave browser": "brave",
            }
            mapped_target = app_map.get(target, target)
            return SemanticAction(
                intent="CHECK_APP_STATUS",
                service="windows",
                action="check_status",
                query=mapped_target,
                parameters={"app_name": mapped_target, "target": mapped_target},
                confidence=1.0,
            )
    return None


def parse_code_assistant(raw_text: str, lowered: str, context: Optional[Any] = None) -> Optional[SemanticAction]:
    """
    Parses developer code assistant queries:
    - Error finding ("Jarvis code mein ye error find karo")
    - File analysis ("main.py analyze karo")
    - Unused functions ("unused functions find karo")
    - Project architecture ("project architecture check karo")
    - Pytest runner ("pytest run karo")
    - Error fix suggestion ("error fix suggest karo")
    - Git change impact ("last change ka impact batao")
    - Dead code finding ("dead code find karo")
    - Mode check/switch ("code assistant mode check karo")
    """
    cleaned = lowered.strip(" .?!")

    # 1. Error Finding ("Jarvis code mein ye error find karo", "code mein error find karo")
    if (
        ("code" in cleaned and "error" in cleaned and any(w in cleaned for w in ["find", "dhundo", "search", "karo", "batao"]))
        or ("error find" in cleaned)
        or ("find error" in cleaned)
    ):
        query = None
        target_file = None
        # Extract potential file or error snippet if provided
        m_file = re.search(r"([a-zA-Z0-9_\-\.\/\\]+\.py)", raw_text)
        if m_file:
            target_file = m_file.group(1)
        return SemanticAction(
            intent="FIND_CODE_ERRORS",
            service="code_assistant",
            action="find_errors",
            query=raw_text,
            parameters={"query": query, "target_file": target_file},
            confidence=0.98,
        )

    # 2. File Analysis ("main.py analyze karo", "analyze main.py")
    m_analyze = re.search(r"([a-zA-Z0-9_\-\.\/\\]+\.py)\s+(?:ko\s+)?analyze", cleaned)
    if m_analyze:
        target_file = m_analyze.group(1)
        return SemanticAction(
            intent="ANALYZE_CODE_FILE",
            service="code_assistant",
            action="analyze_file",
            query=target_file,
            parameters={"file_path": target_file},
            confidence=0.98,
        )
    if ("analyze" in cleaned or "analysis" in cleaned) and any(f in cleaned for f in [".py", "file", "main"]):
        m_any_file = re.search(r"([a-zA-Z0-9_\-\.\/\\]+\.py)", raw_text)
        file_path = m_any_file.group(1) if m_any_file else "main.py"
        return SemanticAction(
            intent="ANALYZE_CODE_FILE",
            service="code_assistant",
            action="analyze_file",
            query=file_path,
            parameters={"file_path": file_path},
            confidence=0.95,
        )

    # 3. Unused Functions ("unused functions find karo", "brain mein unused functions find karo")
    if ("unused function" in cleaned) or ("uncalled function" in cleaned) or ("unused functions" in cleaned):
        target_dir = "."
        for mod in ["core", "brain", "plugins", "memory", "learning", "security", "tests"]:
            if f"{mod} mein" in cleaned or f"in {mod}" in cleaned or f"{mod}/" in cleaned or f"{mod} " in cleaned:
                target_dir = mod
                break
        return SemanticAction(
            intent="FIND_UNUSED_FUNCTIONS",
            service="code_assistant",
            action="find_unused_functions",
            query=raw_text,
            parameters={"target_dir": target_dir},
            confidence=0.98,
        )

    # 4a. Interactive Archify Architecture Visualization ("archify dikhao", "show archify", "complete archify dikhao", "jarvis architecture dikhao", "archify me dikhai de")
    if (
        "archify" in cleaned
        or ("architecture" in cleaned and any(w in cleaned for w in ["dikhao", "show", "open", "kholo", "display", "dikhai de", "dikhe", "view", "viewer", "visualize"]))
    ):
        return SemanticAction(
            intent="SHOW_ARCHIFY",
            service="archify",
            action="show_architecture",
            query=raw_text,
            parameters={},
            confidence=0.99,
        )

    # 4b. Project Architecture Check ("project architecture check karo", "architecture audit karo")
    if (
        "archify" not in cleaned
        and (
            ("architecture" in cleaned and any(w in cleaned for w in ["check", "verify", "audit", "dekho"]))
            or ("project architecture" in cleaned and any(w in cleaned for w in ["check", "verify", "audit", "dekho", "batao", "karo"]))
        )
    ):
        return SemanticAction(
            intent="CHECK_ARCHITECTURE",
            service="code_assistant",
            action="check_architecture",
            query=raw_text,
            parameters={},
            confidence=0.98,
        )

    # 5. Pytest Runner ("pytest run karo", "run pytest")
    if ("pytest" in cleaned and any(w in cleaned for w in ["run", "chalao", "karo", "execute"])) or ("run tests" in cleaned) or ("tests run karo" in cleaned):
        m_target = re.search(r"(?:tests\/[a-zA-Z0-9_\-]+\.py)", raw_text)
        test_tgt = m_target.group(0) if m_target else None
        return SemanticAction(
            intent="RUN_PYTEST",
            service="code_assistant",
            action="run_pytest",
            query=raw_text,
            parameters={"test_target": test_tgt},
            confidence=0.98,
        )

    # 6. Error Fix Suggestion ("error fix suggest karo", "suggest error fix")
    if ("error" in cleaned and "fix" in cleaned and any(w in cleaned for w in ["suggest", "batao", "karo", "kaise"])) or ("fix suggest" in cleaned):
        return SemanticAction(
            intent="SUGGEST_ERROR_FIX",
            service="code_assistant",
            action="suggest_error_fix",
            query=raw_text,
            parameters={},
            confidence=0.98,
        )

    # 7. Git Change Impact Assessment ("last change ka impact batao")
    if ("last change" in cleaned or "change" in cleaned) and ("impact" in cleaned):
        return SemanticAction(
            intent="ANALYZE_CHANGE_IMPACT",
            service="code_assistant",
            action="analyze_change_impact",
            query=raw_text,
            parameters={},
            confidence=0.98,
        )

    # 8. Dead Code Finder ("dead code find karo")
    if ("dead code" in cleaned) or ("unreachable code" in cleaned):
        return SemanticAction(
            intent="FIND_DEAD_CODE",
            service="code_assistant",
            action="find_dead_code",
            query=raw_text,
            parameters={"target_dir": "."},
            confidence=0.98,
        )

    # 9. Mode Management ("code assistant mode check karo", "code assistant mode set karo")
    if "code assistant mode" in cleaned or "assistant mode" in cleaned:
        if any(w in cleaned for w in ["set", "badlo", "karo"]) and any(m in cleaned.upper() for m in ["READ_ONLY", "SUGGEST", "PATCH", "AUTO_FIX"]):
            target_mode = "READ_ONLY"
            for m in ["AUTO_FIX", "SUGGEST", "PATCH", "READ_ONLY"]:
                if m.lower() in cleaned or m in cleaned.upper():
                    target_mode = m
                    break
            return SemanticAction(
                intent="SET_ASSISTANT_MODE",
                service="code_assistant",
                action="set_mode",
                query=raw_text,
                parameters={"mode": target_mode},
                confidence=0.99,
            )
        else:
            return SemanticAction(
                intent="GET_ASSISTANT_MODE",
                service="code_assistant",
                action="get_mode",
                query=raw_text,
                parameters={},
                confidence=0.99,
            )

    # 10. Holistic Project Health Audit ("Jarvis, mere pure project ka health audit karo")
    if ("health audit" in cleaned) or ("health check" in cleaned and "project" in cleaned) or ("project" in cleaned and "audit" in cleaned) or ("health score" in cleaned):
        return SemanticAction(
            intent="RUN_HEALTH_AUDIT",
            service="code_assistant",
            action="run_health_audit",
            query=raw_text,
            parameters={"target_dir": "."},
            confidence=0.99,
        )

    # 11. Dependency Analyzer ("dependency analyze karo", "dependencies check karo")
    if "circular" not in cleaned and ("dependency" in cleaned or "dependencies" in cleaned) and any(w in cleaned for w in ["check", "analyze", "batao", "karo", "audit"]):
        return SemanticAction(
            intent="ANALYZE_DEPENDENCIES",
            service="code_assistant",
            action="analyze_dependencies",
            query=raw_text,
            parameters={},
            confidence=0.98,
        )

    # 12. Import Analyzer ("imports analyze karo", "wildcard imports check karo")
    if ("import" in cleaned or "imports" in cleaned) and any(w in cleaned for w in ["check", "analyze", "find", "dhundo", "wildcard", "karo"]):
        return SemanticAction(
            intent="ANALYZE_IMPORTS",
            service="code_assistant",
            action="analyze_imports",
            query=raw_text,
            parameters={"target_dir": "."},
            confidence=0.98,
        )

    # 13. Duplication Detector ("duplicate code find karo", "code duplication check karo")
    if ("duplicate" in cleaned or "duplication" in cleaned) and any(w in cleaned for w in ["code", "find", "check", "dhundo", "karo"]):
        return SemanticAction(
            intent="DETECT_DUPLICATION",
            service="code_assistant",
            action="detect_duplication",
            query=raw_text,
            parameters={"target_dir": "."},
            confidence=0.98,
        )

    # 14. Complexity Analyzer ("code complexity check karo", "complex functions find karo")
    if ("complexity" in cleaned) and any(w in cleaned for w in ["check", "analyze", "batao", "find", "karo"]):
        return SemanticAction(
            intent="ANALYZE_COMPLEXITY",
            service="code_assistant",
            action="analyze_complexity",
            query=raw_text,
            parameters={"target_dir": "."},
            confidence=0.98,
        )

    # 15. Circular Dependency Detector ("circular dependencies check karo", "circular imports find karo")
    if ("circular" in cleaned) and any(w in cleaned for w in ["dependency", "dependencies", "import", "imports", "cycle", "cycles", "karo"]):
        return SemanticAction(
            intent="DETECT_CIRCULAR_DEPENDENCIES",
            service="code_assistant",
            action="detect_circular_dependencies",
            query=raw_text,
            parameters={"target_dir": "."},
            confidence=0.98,
        )

    # 16. Security Scanner ("security scan karo", "security check karo", "vulnerabilities find karo")
    if ("security" in cleaned or "vulnerabilit" in cleaned or "secrets" in cleaned) and any(w in cleaned for w in ["scan", "check", "find", "audit", "dhundo", "karo"]):
        return SemanticAction(
            intent="SCAN_SECURITY",
            service="code_assistant",
            action="scan_security",
            query=raw_text,
            parameters={"target_dir": "."},
            confidence=0.98,
        )

    # 17. Performance Analyzer ("performance analyze karo", "performance issues find karo")
    if ("performance" in cleaned or "bottleneck" in cleaned) and any(w in cleaned for w in ["analyze", "check", "find", "batao", "issues", "karo"]):
        return SemanticAction(
            intent="ANALYZE_PERFORMANCE",
            service="code_assistant",
            action="analyze_performance",
            query=raw_text,
            parameters={"target_dir": "."},
            confidence=0.98,
        )

    # 18. Coverage Analyzer ("test coverage check karo", "coverage report batao")
    if ("coverage" in cleaned or "untested" in cleaned) and any(w in cleaned for w in ["check", "analyze", "batao", "report", "karo"]):
        return SemanticAction(
            intent="ANALYZE_COVERAGE",
            service="code_assistant",
            action="analyze_coverage",
            query=raw_text,
            parameters={"target_dir": "."},
            confidence=0.98,
        )

    return None


