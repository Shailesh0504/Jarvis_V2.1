import functools
import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("jarvis.brain.spelling_resolver")


def _levenshtein(s1: str, s2: str) -> int:
    """Computes exact Damerau-Levenshtein edit distance (insertions, deletions, substitutions, and adjacent transpositions)."""
    d = {}
    len1, len2 = len(s1), len(s2)
    for i in range(-1, len1 + 1):
        d[(i, -1)] = i + 1
    for j in range(-1, len2 + 1):
        d[(-1, j)] = j + 1

    for i in range(len1):
        for j in range(len2):
            cost = 0 if s1[i] == s2[j] else 1
            d[(i, j)] = min(
                d[(i - 1, j)] + 1,        # deletion
                d[(i, j - 1)] + 1,        # insertion
                d[(i - 1, j - 1)] + cost, # substitution
            )
            if i > 0 and j > 0 and s1[i] == s2[j - 1] and s1[i - 1] == s2[j]:
                d[(i, j)] = min(d[(i, j)], d[(i - 2, j - 2)] + 1)  # adjacent transposition
    return d[(len1 - 1, len2 - 1)]


_TRIPLE_PLUS_RE = re.compile(r'(.)\1{2,}')
_DOUBLE_CONSONANTS_RE = re.compile(r'([bcdfghjklmnpqrstvwxyz])\1', re.IGNORECASE)
_DOUBLE_CONSONANTS_OK = {'ss', 'll', 'tt', 'nn', 'rr', 'ff', 'pp', 'cc', 'mm', 'gg', 'dd', 'bb'}


def _normalize_double_letters(word: str) -> str:
    """
    Collapses spurious duplicate consonants common in STT/typing errors with precompiled regexes.
    'excell' → 'excel', 'chrrome' → 'chrome', 'blutoothe' → 'bluetooth'
    """
    # Step 1: collapse triple+ letters to double
    result = _TRIPLE_PLUS_RE.sub(r'\1\1', word)
    # Step 2: collapse doubled consonants that are almost never valid in English app names
    result = _DOUBLE_CONSONANTS_RE.sub(
        lambda m: m.group(0) if m.group(0).lower() in _DOUBLE_CONSONANTS_OK else m.group(1),
        result
    )
    return result


# ---------------------------------------------------------------------------
# Phonetic neighbor table for cross-initial matching
# Maps a letter to the set of letters that are phonetically close enough
# that a user might type/say one when they mean the other.
# ---------------------------------------------------------------------------
_PHONETIC_NEIGHBORS: Dict[str, Set[str]] = {
    'b': {'p'},
    'c': {'k', 's'},
    'd': {'t'},
    'f': {'ph', 'v'},
    'g': {'j', 'k'},
    'j': {'g', 'y'},
    'k': {'c', 'g'},
    'p': {'b', 'f'},
    's': {'c', 'z'},
    't': {'d'},
    'v': {'b', 'f', 'w'},
    'w': {'v'},
    'z': {'s'},
}


def _phonetic_start_ok(word: str, candidate: str) -> bool:
    """
    Returns True if the word's first char could be a phonetic typo for the
    candidate's first char (or they match exactly).
    Also handles 'bl' vs 'bl', 'br' vs 'br' (same prefix clusters).
    """
    if not word or not candidate:
        return False
    w0, c0 = word[0], candidate[0]
    if w0 == c0:
        return True
    # Check phonetic neighbor table
    neighbors = _PHONETIC_NEIGHBORS.get(w0, set())
    if c0 in neighbors:
        return True
    # Also check reverse (candidate → word direction)
    rev_neighbors = _PHONETIC_NEIGHBORS.get(c0, set())
    if w0 in rev_neighbors:
        return True
    return False


@dataclass
class SpellingResolution:
    original_text: str
    corrected_text: str
    typo: str
    correction: str
    confidence: float
    needs_confirmation: bool
    alt_candidate: Optional[str] = None          # Second-best candidate if ambiguous
    alt_confidence: Optional[float] = None        # Confidence of alt_candidate
    correction_method: str = "fuzzy"              # "entity_aware" | "fuzzy" | "double_letter"


# ---------------------------------------------------------------------------
# Clarification Formatter
# ---------------------------------------------------------------------------

class SpellingClarificationFormatter:
    """
    Generates natural, action-specific clarification and acknowledgement messages
    for spelling corrections.

    Replaces the generic "Kya aap 'X' kehna chahte hain, Boss?" with:
    - Silent ack: "Ji, Excel khol raha hoon."
    - Choice prompt: "Aap Excel keh rahe hain ya Edge, Boss?"
    - Specific confirm: "Aap Bluetooth enable karne ki baat kar rahe hain?"
    """

    # Action verb → natural Hindi ack phrase
    _OPEN_VERBS = {"kholo", "open", "launch", "start", "run", "kholiye", "khol", "chalo", "chala"}
    _CLOSE_VERBS = {"band", "close", "kill", "exit", "terminate", "bandh"}
    _PLAY_VERBS = {"chalao", "chala", "bajao", "play", "sunao", "stream", "laga"}
    _ENABLE_VERBS = {"on", "enable", "chalu", "activate", "chalao"}
    _DISABLE_VERBS = {"off", "disable", "band", "deactivate"}
    _SEARCH_VERBS = {"search", "dhoondo", "find", "dhundho"}

    # App display names for natural speech
    _APP_DISPLAY: Dict[str, str] = {
        "chrome": "Chrome",
        "google chrome": "Chrome",
        "excel": "Microsoft Excel",
        "word": "Microsoft Word",
        "powerpoint": "Microsoft PowerPoint",
        "notepad": "Notepad",
        "calculator": "Calculator",
        "spotify": "Spotify",
        "vlc": "VLC",
        "bluetooth": "Bluetooth",
        "wifi": "Wi-Fi",
        "youtube": "YouTube",
        "whatsapp": "WhatsApp",
        "brave": "Brave",
        "firefox": "Firefox",
        "edge": "Microsoft Edge",
        "camera": "Camera",
        "settings": "Settings",
        "calculator": "Calculator",
        "restart": "restart",
        "shutdown": "shutdown",
        "reboot": "restart",
        "microsoft": "Microsoft",
        "microsoft store": "Microsoft Store",
        "claude": "Claude",
        "gemini": "Gemini",
        "perplexity": "Perplexity",
    }

    @classmethod
    def _display(cls, term: str) -> str:
        return cls._APP_DISPLAY.get(term.lower(), term.capitalize())

    @classmethod
    def _detect_action_verb(cls, text: str) -> str:
        """Detects the primary action verb category from the utterance."""
        lowered = text.lower()
        words = set(re.findall(r'\b\w+\b', lowered))
        if words & cls._OPEN_VERBS:
            return "open"
        if words & cls._CLOSE_VERBS:
            return "close"
        if words & cls._PLAY_VERBS:
            return "play"
        if words & cls._ENABLE_VERBS:
            return "enable"
        if words & cls._DISABLE_VERBS:
            return "disable"
        if words & cls._SEARCH_VERBS:
            return "search"
        return "general"

    @classmethod
    def format_auto_ack(cls, typo: str, correction: str, original_text: str) -> str:
        """
        Returns a natural spoken acknowledgement for a **silent** auto-correction.
        Called when needs_confirmation=False and we want to inform the user.

        Examples:
          "open exel"  → "Ji, Microsoft Excel khol raha hoon."
          "crome open" → "Ji, Chrome khol raha hoon."
          "blutooth on" → "Ji, Bluetooth enable kar raha hoon."
        """
        display = cls._display(correction)
        action = cls._detect_action_verb(original_text)

        if action == "open":
            return f"Ji, {display} khol raha hoon."
        if action == "close":
            return f"Ji, {display} band kar raha hoon."
        if action == "play":
            return f"Ji, {display} chal raha hoon."
        if action == "enable":
            return f"Ji, {display} enable kar raha hoon."
        if action == "disable":
            return f"Ji, {display} disable kar raha hoon."
        if action == "search":
            return f"Ji, {display} search kar raha hoon."
        if correction in ("morning", "evening", "afternoon", "night", "hello", "hi", "namaste", "good"):
            return ""
        return f"Ji, {display} samajh gaya."

    @classmethod
    def format_clarification(
        cls,
        typo: str,
        correction: str,
        original_text: str,
        alt_candidate: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> str:
        """
        Returns a specific clarification message when confidence is moderate.

        With alt_candidate (ambiguous):
          "Shailesh, aap Excel keh rahe hain ya Word?" (if user_name is known)
          "Aap Excel keh rahe hain ya Edge, Boss?"     (if user_name is default)

        Without alt_candidate (uncertain single):
          "Shailesh, aap Bluetooth enable karne ki baat kar rahe hain?"
          "Aap Excel khol rahe hain, Boss?"
        """
        display = "Excel" if correction.lower() in ("excel", "microsoft excel") else cls._display(correction)
        action = cls._detect_action_verb(original_text)

        if alt_candidate:
            alt_display = "Word" if alt_candidate.lower() in ("word", "microsoft word") else ("Edge" if alt_candidate.lower() == "edge" else cls._display(alt_candidate))
            if user_name:
                return f"{user_name}, aap {display} keh rahe hain ya {alt_display}?"
            return f"Aap '{display}' keh rahe hain ya '{alt_display}', Boss?"

        # Single uncertain case — make it action-specific
        if correction in ("restart", "reboot"):
            if user_name:
                return f"{user_name}, aap system restart karne ki baat kar rahe hain?"
            return "Aap system restart karne ki baat kar rahe hain, Boss?"
        if correction == "shutdown":
            if user_name:
                return f"{user_name}, aap computer shutdown karne ki baat kar rahe hain?"
            return "Aap computer shutdown karne ki baat kar rahe hain, Boss?"
        if correction == "bluetooth":
            if action in ("enable", "disable"):
                state = "on" if action == "enable" else "off"
                if user_name:
                    return f"{user_name}, aap Bluetooth {state} karne ki baat kar rahe hain?"
                return f"Aap Bluetooth {state} karne ki baat kar rahe hain, Boss?"
            if user_name:
                return f"{user_name}, aap Bluetooth ki baat kar rahe hain?"
            return "Aap Bluetooth ki baat kar rahe hain, Boss?"
        if correction == "wifi":
            if user_name:
                return f"{user_name}, aap Wi-Fi ki baat kar rahe hain?"
            return "Aap Wi-Fi ki baat kar rahe hain, Boss?"

        # Generic action-specific
        if action == "open":
            if user_name:
                return f"{user_name}, aap {display} kholna chahte hain?"
            return f"Aap '{display}' kholna chahte hain, Boss?"
        if action == "close":
            if user_name:
                return f"{user_name}, aap {display} band karna chahte hain?"
            return f"Aap '{display}' band karna chahte hain, Boss?"
        if action == "play":
            if user_name:
                return f"{user_name}, aap {display} chalana chahte hain?"
            return f"Aap '{display}' chalana chahte hain, Boss?"

        if user_name:
            return f"{user_name}, kya aap {display} keh rahe hain?"
        return f"Aap '{display}' keh rahe hain, Boss?"

    @classmethod
    def format_ambiguous_choice(
        cls, option_a: str, option_b: str, original_text: str = "", user_name: Optional[str] = None
    ) -> str:
        """
        Formats a binary choice clarification when two candidates are equally plausible.
        Example: "Shailesh, aap Excel keh rahe hain ya Word?"
        """
        disp_a = "Excel" if option_a.lower() in ("excel", "microsoft excel") else cls._display(option_a)
        disp_b = "Word" if option_b.lower() in ("word", "microsoft word") else cls._display(option_b)
        if user_name:
            return f"{user_name}, aap {disp_a} keh rahe hain ya {disp_b}?"
        return f"Aap '{disp_a}' keh rahe hain ya '{disp_b}', Boss?"


# ---------------------------------------------------------------------------
# Main SpellingResolver — upgraded
# ---------------------------------------------------------------------------

class SpellingResolver:
    """
    Intelligent spelling correction for Jarvis commands.

    Upgrades over v1:
    1. Phonetic-neighbor first-char relaxation (blutooth→bluetooth, retstart→restart)
    2. Double-letter normalization pre-pass (excell→excel, chrrome→chrome)
    3. Top-2 candidate tracking for ambiguous corrections
    4. SpellingClarificationFormatter for natural, specific messages
    5. Larger length tolerance for long words (≥8 chars: diff up to 4)
    """

    CORE_TERMS = {
        "password", "internet", "network", "wifi", "chrome", "youtube", "excel",
        "notepad", "calculator", "screenshot", "recording", "volume", "brightness",
        "bluetooth", "whatsapp", "spotify", "browser", "camera", "calendar",
        "reminder", "shutdown", "restart", "reboot", "maximize", "minimize", "download",
        "upload", "speed", "weather", "location", "clipboard", "powerpoint", "microsoft",
        "bing", "google", "yahoo", "duckduckgo", "chatgpt", "claude", "gemini", "perplexity", "brave", "edge",
        "firefox", "vlc", "glpi", "dhan", "zerodha", "groww", "upstox",
        "system", "computer", "laptop", "machine", "screen", "window",
        "temp", "temporary", "recycle", "trash", "clean", "clear",
        "time", "timer", "samay", "date", "tarikh", "ghadi",
        "morning", "afternoon", "evening", "hello", "namaste", "night",
    }

    # Direct high-confidence typo dictionary for immediate precision
    KNOWN_TYPOS: Dict[str, str] = {
        "cloude": "claude",
        "cloude ai": "claude",
        "cloud ai": "claude",
        "retstart": "restart",
        "microsft": "microsoft",
        "excell": "excel",
        "exel": "excel",
        "chrme": "chrome",
        "crome": "chrome",
        "blutooth": "bluetooth",
        "blootooth": "bluetooth",
        "blutoothe": "bluetooth",
        "chrrome": "chrome",
        "braev": "brave",
        "tem": "temp",
        "phile": "file",
        "philes": "files",
        "youtub": "youtube",
        "moring": "morning",
        "mornig": "morning",
        "mornin": "morning",
        "mrng": "morning",
        "gud": "good",
        "helo": "hello",
        "hallo": "hello",
        "helllo": "hello",
        "hii": "hi",
        "hie": "hi",
        "suprabhat": "shubh prabhat",
        "evenig": "evening",
        "evenin": "evening",
        "aftrnoon": "afternoon",
        "afternon": "afternoon",
        "nite": "night",
        "nyt": "night",
    }
    IGNORE_WORDS = {
        "batao", "dikhao", "kholo", "karo", "karna", "chalao", "bajao", "please",
        "jarvis", "mujhe", "mera", "meri", "aap", "kya", "kaise", "kitna", "kitani",
        "kitni", "hai", "hain", "haan", "nahi", "wala", "wali", "file", "open",
        "close", "sabhi", "saare", "past", "connected", "mein", "main", "passwords",
        "tab", "tabs", "window", "windows", "site", "website", "page", "url", "domain",
        "sheet", "sheets", "the", "a", "an", "to", "for", "me", "do", "de",
        "chat", "bing", "bring", "search", "clear", "clean", "temp", "temporary",
        "empty", "recycle", "play", "playing", "store", "edge", "word", "paint",
        "photos", "maps", "clock", "notes", "mail", "apps", "storage",
        "time", "samay", "date", "tarikh",
        # Visual interaction action words — NEVER treat as typos
        "click", "clicks", "doubleclick", "double-click", "point", "select",
        # Hindi social / polite / filler words — NEVER treat as typos
        "dost", "bhai", "yaar", "re", "ji", "sahib", "na", "toh", "boss",
        "bc", "oye", "aye", "arre", "arrey", "chalo", "zara", "jaldi",
        "dear", "bro", "buddy", "friend", "sir", "good", "hi", "hey",
        "kar", "karke", "lao", "le", "sun", "suno", "dekho", "dekh",
        # Developer & Code Intelligence keywords — NEVER treat as typos
        "audit", "project", "code", "pytest", "coverage", "dependencies", "dependency",
        "circular", "complexity", "duplication", "syntax",
    }

    # Ambiguity threshold: if top-2 candidates are within this margin, treat as ambiguous
    _AMBIGUITY_MARGIN = 0.08

    _CACHED_TERMS: Optional[Set[str]] = None

    _COMMAND_CONTEXT_RE = re.compile(
        r"\b(?:kholo|open|close|chalao|play|dikhao|batao|check|download|upload|"
        r"password|speed|volume|brightness|screenshot|wifi|internet|app|file|"
        r"system|computer|pc|laptop|restart|shutdown|reboot|lock|sleep|band|"
        r"machine|window|screen|turn|enable|on|off|bluetooth|karo|kar|kardo|kar\s+do|"
        r"kijiye|shuru|chalu|start|launch|run)\b",
        re.IGNORECASE
    )
    _TEMP_CLEANUP_RE = re.compile(
        r"\btime\s+files?\s+(?:clean|clear|delete|remove|saaf|click)(?:\s+(?:karo|kar\s+do))?\b",
        re.IGNORECASE
    )
    _NAME_GUARD_RE = re.compile(r"\b(?:mera\s+naam|my\s+name|mujhe\s+.+\s+bulao|main\s+.+\s+hoon)\b", re.IGNORECASE)
    _MATH_GUARD_RE = re.compile(r"\d|\b(?:square|root|percent|plus|minus|multiply|divide|jod|guna|bhaag)\b", re.IGNORECASE)
    _WORDS_RE = re.compile(r"[A-Za-z]+")

    @classmethod
    def invalidate_cache(cls) -> None:
        cls._CACHED_TERMS = None
        _cached_spelling_resolve.cache_clear()

    @classmethod
    def _known_terms(cls, plugin_manager: Optional[Any]) -> Set[str]:
        if cls._CACHED_TERMS is not None:
            return cls._CACHED_TERMS

        terms = set(cls.CORE_TERMS)
        try:
            from core.windows_app_resolver import get_windows_app_resolver
            terms.update(get_windows_app_resolver().get_known_terms())
        except Exception:
            pass
        if plugin_manager:
            try:
                manifests = plugin_manager.get_all_manifests()
                if isinstance(manifests, dict):
                    for manifest in manifests.values():
                        terms.add(getattr(manifest, "name", "").lower())
                        for action in getattr(manifest, "actions", []):
                            for keyword in getattr(action, "keywords", []):
                                terms.update(
                                    w for w in re.findall(r"[a-z]+", keyword.lower())
                                    if len(w) >= 6 and w not in cls.IGNORE_WORDS
                                )
            except Exception:
                pass
        for typo in cls.KNOWN_TYPOS.keys():
            terms.discard(typo)
        cls._CACHED_TERMS = terms
        return terms

    @classmethod
    def _preprocess_word(cls, word: str) -> str:
        """
        Normalize the input word before fuzzy matching:
        1. Lowercase
        2. Collapse double-letters via _normalize_double_letters
        """
        return _normalize_double_letters(word.lower())

    @classmethod
    def resolve(
        cls,
        text: str,
        plugin_manager: Optional[Any] = None,
        rejected_candidates: Optional[Set[Tuple[str, str]]] = None,
    ) -> Optional[SpellingResolution]:
        """Resolves typos in user utterance with short-term LRU cache."""
        if plugin_manager is None and not rejected_candidates:
            return _cached_spelling_resolve(text)
        return cls._resolve_internal(text, plugin_manager=plugin_manager, rejected_candidates=rejected_candidates)

    @classmethod
    def _resolve_internal(
        cls,
        text: str,
        plugin_manager: Optional[Any] = None,
        rejected_candidates: Optional[Set[Tuple[str, str]]] = None,
    ) -> Optional[SpellingResolution]:
        lowered_text = text.lower()

        # -------------------------------------------------------------------
        # Path A: Entity-aware Windows App resolution (highest priority)
        # -------------------------------------------------------------------
        try:
            from core.windows_app_resolver import get_windows_app_resolver
            extracted = get_windows_app_resolver().extract_app_entity_from_text(text)
            if extracted:
                app_match, matched_phrase = extracted
                if app_match.confidence >= 0.85:
                    target_replacement = (
                        app_match.display_name if len(matched_phrase.split()) > 1
                        else ("calculator" if app_match.canonical_id == "calc" else app_match.canonical_id)
                    )
                    if matched_phrase.lower() != target_replacement.lower():
                        corrected = re.sub(
                            rf"\b{re.escape(matched_phrase)}\b",
                            target_replacement,
                            text,
                            count=1,
                            flags=re.IGNORECASE,
                        )
                        logger.info(
                            "SpellingResolver (Entity-Aware): '%s' -> '%s' (conf=%.2f)",
                            text, corrected, app_match.confidence,
                        )
                        return SpellingResolution(
                            original_text=text,
                            corrected_text=corrected,
                            typo=matched_phrase.lower(),
                            correction=target_replacement,
                            confidence=app_match.confidence,
                            needs_confirmation=False,
                            correction_method="entity_aware",
                        )
                    else:
                        return None
        except Exception as ex:
            logger.debug("Entity check in SpellingResolver error: %s", ex)

        # -------------------------------------------------------------------
        # Path B: Contextual STT typo (temp files pattern)
        # -------------------------------------------------------------------
        temp_cleanup = cls._TEMP_CLEANUP_RE.search(lowered_text)
        if temp_cleanup:
            corrected = re.sub(r"\btime\s+files?\b", "temp files", text, count=1, flags=re.IGNORECASE)
            corrected = re.sub(r"\bclick\b", "clean", corrected, count=1, flags=re.IGNORECASE)
            return SpellingResolution(
                original_text=text,
                corrected_text=corrected,
                typo=temp_cleanup.group(0),
                correction="temp files clean",
                confidence=0.82,
                needs_confirmation=True,
                correction_method="fuzzy",
            )

        # -------------------------------------------------------------------
        # Guard clauses — same as before
        # -------------------------------------------------------------------
        if cls._NAME_GUARD_RE.search(lowered_text):
            return None
        if cls._MATH_GUARD_RE.search(lowered_text):
            return None

        words = cls._WORDS_RE.findall(text)
        meaningful_words = [
            w for w in words
            if w.lower() not in {
                # Generic stop-words
                "please", "jarvis", "zara", "the", "a", "an", "ko", "ka", "ki",
                # Hindi social / polite / filler words (must never count as meaningful for typo detection)
                "bhai", "yaar", "dost", "re", "ji", "sahib", "na", "toh", "boss",
                "bc", "oye", "aye", "arre", "arrey", "jaldi", "suno", "dekho",
            }
        ]
        if len(meaningful_words) > 5:
            return None

        known = cls._known_terms(plugin_manager)

        command_context = bool(cls._COMMAND_CONTEXT_RE.search(lowered_text))
        # If command context word isn't explicitly present, check if short utterance contains
        # a high-confidence typo for a known core command or app name
        if not command_context and len(meaningful_words) <= 2:
            for mw in meaningful_words:
                mw_low = mw.lower()
                mw_pre = cls._preprocess_word(mw_low)
                if any(_phonetic_start_ok(mw_pre, cand) and abs(len(mw_pre) - len(cand)) <= 2 for cand in known):
                    command_context = True
                    break

        if not command_context:
            return None

        # -------------------------------------------------------------------
        # Path C: Fuzzy matching with phonetic relaxation + double-letter norm
        # -------------------------------------------------------------------
        rejected = rejected_candidates or set()

        # Track top-2 candidates for ambiguity detection
        candidates: List[Tuple[float, int, str, str, str]] = []
        # (score, dist, original_word, preprocessed_word, candidate)

        for word in words:
            lowered = word.lower()
            if lowered in cls.KNOWN_TYPOS and (lowered, cls.KNOWN_TYPOS[lowered]) not in rejected:
                target_term = cls.KNOWN_TYPOS[lowered]
                corrected = re.sub(
                    rf"\b{re.escape(word)}\b", target_term, text,
                    count=1, flags=re.IGNORECASE,
                )
                logger.info(
                    "SpellingResolver (Known-Typo): '%s' -> '%s' (conf=0.96)",
                    text, corrected,
                )
                return SpellingResolution(
                    original_text=text,
                    corrected_text=corrected,
                    typo=lowered,
                    correction=target_term,
                    confidence=0.96,
                    needs_confirmation=False,
                    correction_method="fuzzy",
                )

            if len(lowered) < 4 or lowered in known or lowered in cls.IGNORE_WORDS:
                continue

            # Pre-process: collapse double-letters before matching
            preprocessed = cls._preprocess_word(word)

            # If preprocessing itself already maps to a known term → high-conf correction
            if preprocessed != lowered and preprocessed in known:
                if (lowered, preprocessed) not in rejected:
                    corrected = re.sub(
                        rf"\b{re.escape(word)}\b", preprocessed, text,
                        count=1, flags=re.IGNORECASE,
                    )
                    logger.info(
                        "SpellingResolver (Double-Letter): '%s' -> '%s' (conf=0.96)",
                        text, corrected,
                    )
                    return SpellingResolution(
                        original_text=text,
                        corrected_text=corrected,
                        typo=lowered,
                        correction=preprocessed,
                        confidence=0.96,
                        needs_confirmation=False,
                        correction_method="double_letter",
                    )

            for candidate in known:
                # Length tolerance: longer words (≥8 chars) allow diff up to 4
                max_len_diff = 4 if max(len(preprocessed), len(candidate)) >= 8 else 3
                if abs(len(preprocessed) - len(candidate)) > max_len_diff:
                    continue

                # First-character check: exact OR phonetic neighbor
                if not _phonetic_start_ok(preprocessed, candidate):
                    continue

                if (lowered, candidate) in rejected:
                    continue

                # Score the preprocessed form against the candidate
                score = SequenceMatcher(None, preprocessed, candidate).ratio()
                dist = _levenshtein(preprocessed, candidate)

                logger.debug(
                    "Spelling candidate eval: word='%s' (pre='%s'), candidate='%s', score=%.2f, dist=%d",
                    lowered, preprocessed, candidate, score, dist,
                )

                if score >= 0.80:
                    candidates.append((score, dist, word, preprocessed, candidate))

        if not candidates:
            return None

        # Sort: highest score first, then lowest distance
        candidates.sort(key=lambda x: (-x[0], x[1]))
        best = candidates[0]
        best_score, best_dist, best_word, best_pre, best_candidate = best

        # Detect ambiguity: second candidate within margin of first
        alt_candidate: Optional[str] = None
        alt_conf: Optional[float] = None
        if len(candidates) > 1:
            second = candidates[1]
            # Only flag ambiguous if it's a different target word
            if second[4] != best_candidate and (best_score - second[0]) <= cls._AMBIGUITY_MARGIN:
                alt_candidate = second[4]
                alt_conf = second[0]
                logger.info(
                    "SpellingResolver (Ambiguous): top='%s' (%.2f) vs alt='%s' (%.2f)",
                    best_candidate, best_score, alt_candidate, second[0],
                )

        # Effective confidence: edit distance ≤ 1 on word ≥ 5 chars → high confidence
        effective_conf = (
            max(best_score, 0.91) if best_dist <= 1 and len(best_candidate) >= 5
            else best_score
        )

        # Needs confirmation if:
        # a) moderate confidence, OR
        # b) ambiguous (even if high confidence — user should choose)
        needs_confirm = effective_conf < 0.88 or alt_candidate is not None

        corrected = re.sub(
            rf"\b{re.escape(best_word)}\b", best_candidate, text,
            count=1, flags=re.IGNORECASE,
        )
        logger.info(
            "SpellingResolver resolved: '%s' -> '%s' (typo='%s', correction='%s', conf=%.2f, "
            "needs_confirm=%s, alt='%s')",
            text, corrected, best_word.lower(), best_candidate,
            effective_conf, needs_confirm, alt_candidate or "none",
        )
        return SpellingResolution(
            original_text=text,
            corrected_text=corrected,
            typo=best_word.lower(),
            correction=best_candidate,
            confidence=effective_conf,
            needs_confirmation=needs_confirm,
            alt_candidate=alt_candidate,
            alt_confidence=alt_conf,
            correction_method="fuzzy",
        )


@functools.lru_cache(maxsize=512)
def _cached_spelling_resolve(text: str) -> Optional[SpellingResolution]:
    """LRU cached resolver for standard spelling resolution without dynamic overrides."""
    return SpellingResolver._resolve_internal(text, plugin_manager=None, rejected_candidates=None)
