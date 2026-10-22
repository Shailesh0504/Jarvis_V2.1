# core/speech_understanding.py
"""
Human-Like Speech Understanding Engine for Jarvis V2.
Features:
- Linguistic Filler & Hesitation Removal (preserves entities and intent)
- Context-Aware STT Error Correction (recovers 'tab' from 'type', app typos, browser contexts)
- Multi-Dimensional Confidence Model (Audio, STT, Language, Intent, Entity, Context)
- Semantic Relevance & Smart Clarification Decision Policy
- Comprehensive 11-Field Speech Diagnostics Logging
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import unicodedata

logger = logging.getLogger("jarvis.speech_understanding")


class SpeechDecision(str, Enum):
    EXECUTE_FAST_PATH = "execute_fast_path"
    EXECUTE_VERIFIED = "execute_verified"
    CLARIFY = "clarify"
    CONFIRM_DESTRUCTIVE = "confirm_destructive"
    CONVERSATION = "conversation"
    IGNORE_NOISE = "ignore_noise"


class InputQuality(str, Enum):
    """Authoritative pragmatic input quality classification."""
    CLEAN = "clean"
    INCOMPLETE_FRAGMENT = "incomplete_fragment"
    UNINTELLIGIBLE = "unintelligible"
    AMBIGUOUS = "ambiguous"
    EMPTY = "empty"


class NaturalUncertaintyResponder:
    """
    Provides varied, natural conversational responses in Hindi/Hinglish and English
    without repeating the exact same sentence every turn.
    """
    _last_unintelligible_idx: int = -1
    _last_incomplete_idx: int = -1
    _last_ambiguous_idx: int = -1

    UNINTELLIGIBLE_RESPONSES = [
        "Lagta hai input sahi capture nahi hua. Dobara boliye.",
        "Lagta hai message adhura aa gaya. Dobara boliye.",
        "Aawaz sahi se capture nahi hui, kripya dobara kahein.",
        "Ye samajh nahi aaya, Boss. Ek baar aur bolenge?",
        "It seems the input wasn't captured properly. Please say that again.",
    ]

    INCOMPLETE_RESPONSES = [
        "Lagta hai message adhura aa gaya. Dobara boliye.",
        "Lagta hai baat adhuri reh gayi. Aap kya kehna chahte hain?",
        "Sentence poora nahi aaya, Boss. Ek baar dobara bataiye.",
        "Could you please repeat? It seems the request was cut off.",
    ]

    AMBIGUOUS_RESPONSES = [
        "Kis application ki baat kar rahe hain?",
        "Kis application ya file ki baat kar rahe hain, Boss?",
        "Aap kaunsi application ya target ki baat kar rahe hain?",
        "Which application or item are you referring to?",
    ]

    @classmethod
    def get_unintelligible_response(cls) -> str:
        cls._last_unintelligible_idx = (cls._last_unintelligible_idx + 1) % len(cls.UNINTELLIGIBLE_RESPONSES)
        return cls.UNINTELLIGIBLE_RESPONSES[cls._last_unintelligible_idx]

    @classmethod
    def get_incomplete_response(cls) -> str:
        cls._last_incomplete_idx = (cls._last_incomplete_idx + 1) % len(cls.INCOMPLETE_RESPONSES)
        return cls.INCOMPLETE_RESPONSES[cls._last_incomplete_idx]

    @classmethod
    def get_ambiguous_response(cls) -> str:
        cls._last_ambiguous_idx = (cls._last_ambiguous_idx + 1) % len(cls.AMBIGUOUS_RESPONSES)
        return cls.AMBIGUOUS_RESPONSES[cls._last_ambiguous_idx]

    @classmethod
    def get_response(cls, quality: InputQuality) -> str:
        if quality == InputQuality.UNINTELLIGIBLE:
            return cls.get_unintelligible_response()
        elif quality == InputQuality.INCOMPLETE_FRAGMENT:
            return cls.get_incomplete_response()
        elif quality == InputQuality.AMBIGUOUS:
            return cls.get_ambiguous_response()
        return cls.get_unintelligible_response()


class InputQualityEvaluator:
    """
    Analyzes input lexical quality, detecting unintelligible keyboard mash,
    corrupted/broken tokens, incomplete fragments, and ambiguous pronoun requests.
    """
    NOISE_CHARACTERS = set(r"\[]{}|^~_@#$%*\\`=<>")
    KNOWN_SHORT_WORDS = {
        "hi", "hey", "ok", "bye", "yes", "no", "haan", "nahi", "kya", "hai",
        "sun", "ab", "yo", "tab", "vlc", "cmd", "run", "app", "pdf", "doc",
        "log", "cat", "cut", "del", "go", "up", "to", "on", "in", "at", "by",
        "ek", "do", "ye", "wo", "woh", "kar", "mat", "le", "ho"
    }
    PRONOUN_COMMAND_PATTERNS = [
        re.compile(r"^(?:open|kholo|close|band\s+karo|start|chalao|launch)\s+(?:it|this|that|ise|use|isko|usko)$", re.IGNORECASE),
        re.compile(r"^(?:ise|use|isko|usko)\s+(?:open(?:\s+karo|\s+kar\s+do)?|kholo|close(?:\s+karo|\s+kar\s+do)?|band(?:\s+karo|\s+kar\s+do)?|chalao|launch)$", re.IGNORECASE),
        re.compile(r"^(?:open|close|start|launch)\s+(?:it|this|that)$", re.IGNORECASE),
        re.compile(r"^(?:khol|band|chala|open|close)\s+(?:do|de|karo|kar\s+do)\s+(?:ise|use|isko|usko)$", re.IGNORECASE),
    ]

    @classmethod
    def evaluate_quality(
        cls,
        raw_text: str,
        cleaned_text: str,
        active_dialog_pending: bool = False
    ) -> Tuple[InputQuality, float, Dict[str, Any]]:
        text = (cleaned_text or raw_text or "").strip()
        if not text:
            return InputQuality.EMPTY, 0.0, {"reason": "empty_input"}

        non_space = [c for c in text if not c.isspace()]
        if not non_space:
            return InputQuality.EMPTY, 0.0, {"reason": "whitespace_only"}

        # Punctuation-only check
        if not any(c.isalnum() for c in text) and all(c in ".?!,-:; \t\n\r" for c in text):
            return InputQuality.EMPTY, 0.0, {"reason": "punctuation_only"}

        # URLs are valid inputs (e.g. teaching websites, pasting links, following up)
        if text.startswith("http://") or text.startswith("https://") or re.search(r"^(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/.*)?$", text):
            return InputQuality.CLEAN, 0.90, {"reason": "valid_url"}

        # Math expressions are always CLEAN (e.g. "2+2=?", "2+2", "25 mein 15 jod do").
        # Must precede noise/symbol gates: '=', '*', '%', '^' are valid math operators,
        # not keyboard mash. Single owner: plugins.math.calculator.SpokenMathNormalizer.
        try:
            from plugins.math.calculator import SpokenMathNormalizer as _MathNorm
            if _MathNorm.is_math_query(text):
                return InputQuality.CLEAN, 0.95, {"reason": "math_expression"}
        except Exception:
            pass

        # When active dialog is pending an answer, do not reject short non-dictionary tokens or isolated names as fragments
        if active_dialog_pending:
            return InputQuality.CLEAN, 0.90, {"reason": "active_dialog_followup"}

        # 1. Unintelligible Check (Noise chars, high symbol ratio, keyboard mash)
        noise_count = sum(1 for c in text if c in cls.NOISE_CHARACTERS)
        if noise_count >= 1 and (len(text) < 15 or noise_count / len(text) > 0.15):
            return InputQuality.UNINTELLIGIBLE, 0.05, {"reason": "noise_characters", "noise_count": noise_count}

        symbols = [
            c for c in non_space
            if not (c.isalnum() or unicodedata.category(c).startswith('M') or ('\u0900' <= c <= '\u097F'))
            and c not in ".?!,'\"-"
        ]
        symbol_ratio = len(symbols) / len(non_space)
        if symbol_ratio > 0.25:
            return InputQuality.UNINTELLIGIBLE, 0.05, {"reason": "high_symbol_ratio", "ratio": symbol_ratio}

        # Consecutive consonants (keyboard mash, e.g. asdfghjkl)
        if re.search(r"[bcdfghjklmnpqrstvwxz]{5,}", text.lower()):
            return InputQuality.UNINTELLIGIBLE, 0.05, {"reason": "consonant_cluster_mash"}

        # Repeated characters (e.g. aaaaa)
        if re.search(r"([a-zA-Z])\1{3,}", text):
            return InputQuality.UNINTELLIGIBLE, 0.05, {"reason": "character_repetition"}

        # Long words without vowels
        words = re.findall(r"[a-zA-Z]+", text)
        for w in words:
            if len(w) >= 5 and not any(v in w.lower() for v in "aeiouy"):
                return InputQuality.UNINTELLIGIBLE, 0.05, {"reason": "no_vowels", "word": w}

        # 2. Ambiguous Check (Pronoun command without explicit target)
        lower = text.lower()
        if any(pat.match(lower) for pat in cls.PRONOUN_COMMAND_PATTERNS):
            return InputQuality.AMBIGUOUS, 0.45, {"reason": "isolated_pronoun_command"}

        # 3. Incomplete Fragment Check (Single short non-dictionary token or trailing cut-offs)
        if len(words) == 1 and len(words[0]) <= 4 and words[0].lower() not in cls.KNOWN_SHORT_WORDS:
            return InputQuality.INCOMPLETE_FRAGMENT, 0.20, {"reason": "short_non_word_token", "token": words[0]}

        dangling_patterns = [
            re.compile(r"^(?:can\s+you\s+please|could\s+you|please|kripya|zara)\s*$", re.IGNORECASE),
            re.compile(r"^[a-zA-Z0-9]+\s+(?:ko|se|par|me|mein)\s*$", re.IGNORECASE),
        ]
        if any(pat.match(lower) for pat in dangling_patterns):
            return InputQuality.INCOMPLETE_FRAGMENT, 0.25, {"reason": "dangling_phrase"}

        return InputQuality.CLEAN, 0.90, {"reason": "lexically_coherent"}


class ContextualRecoveryEngine:
    """
    Reconstructs user meaning from active context, recent conversation history,
    active window, and known entities before declaring an input unintelligible or unrecoverable.
    """
    _pattern_observations: Dict[str, int] = {}
    _PROMOTION_THRESHOLD: int = 3

    @classmethod
    def attempt_recovery(
        cls,
        text: str,
        quality: InputQuality,
        active_context: Optional[Any] = None,
        recent_turns: Optional[List[Any]] = None,
        target_engine: Optional[Any] = None
    ) -> Tuple[bool, Optional[str], Optional[str], float]:
        text_clean = text.strip()
        lowered = text_clean.lower()

        # Extract active application or window context
        app = (getattr(active_context, "application", "") or "").lower() if active_context else ""
        if not app and target_engine and hasattr(target_engine, "window_manager"):
            try:
                fg = target_engine.window_manager.get_foreground_window()
                if fg and fg.process_name:
                    app = fg.process_name.lower().replace(".exe", "")
            except Exception:
                pass

        # Check recent turns for recently opened/mentioned app
        if not app and recent_turns:
            for turn in reversed(recent_turns):
                raw = (getattr(turn, "raw_input", "") or "")
                resp = (getattr(turn, "response", "") or "")
                m = re.search(r"\b(?:open|kholo|launch)\s+([a-zA-Z0-9]+)\b", raw, re.IGNORECASE)
                if m and m.group(1).lower() not in ("it", "this", "that", "ise", "use"):
                    app = m.group(1).lower()
                    break
                m2 = re.search(r"\b([a-zA-Z0-9]+)\s+(?:open|khol)\b", resp, re.IGNORECASE)
                if m2:
                    app = m2.group(1).lower()
                    break

        # 1. Fragment recovery: 'clo' -> 'close <app>'
        if quality == InputQuality.INCOMPLETE_FRAGMENT or lowered in ("clo", "cloz", "clos"):
            if app and (lowered.startswith("clo") or lowered in ("close", "band karo", "band")):
                reconstructed = f"close {app}"
                cls._record_observation("clo_to_close", app)
                return True, reconstructed, f"active_context(app={app})", 0.90

        # 2. Action verb without target: 'close' -> 'close <app>'
        if lowered in ("close", "band karo", "band", "exit"):
            if app:
                reconstructed = f"close {app}"
                cls._record_observation("close_standalone", app)
                return True, reconstructed, f"active_context(app={app})", 0.92

        # 3. Acoustic confusion / STT noise: 'grave' -> 'Brave'
        is_browser_context = False
        if active_context:
            cur_app = (getattr(active_context, "application", "") or "").lower()
            cur_site = (getattr(active_context, "website", "") or "").lower()
            if cur_site or any(b in cur_app for b in ("chrome", "brave", "edge", "firefox", "browser")):
                is_browser_context = True
        if not is_browser_context and recent_turns:
            for turn in reversed(recent_turns):
                combined = ((getattr(turn, "raw_input", "") or "") + " " + (getattr(turn, "response", "") or "")).lower()
                if any(b in combined for b in ("chrome", "brave", "edge", "firefox", "browser", "website")):
                    is_browser_context = True
                    break

        if is_browser_context:
            if re.search(r"\bgrave\b", lowered):
                reconstructed = re.sub(r"\bgrave\b", "Brave", text_clean, flags=re.IGNORECASE)
                cls._record_observation("grave_to_brave", "browser_context")
                return True, reconstructed, "browser_context_acoustic(grave->Brave)", 0.88

        # 4. Ambiguous pronoun resolution: 'open it' -> 'open <entity>'
        if quality == InputQuality.AMBIGUOUS or re.match(r"^(?:open|kholo|close|band\s+karo)\s+(?:it|this|that|ise|use)$", lowered):
            if recent_turns:
                for turn in reversed(recent_turns):
                    raw = (getattr(turn, "raw_input", "") or "")
                    resp = (getattr(turn, "response", "") or "")
                    m = re.search(r"\b([\w\-]+\.(?:pdf|txt|docx?|xlsx?|py|json|csv|png|jpg))\b", raw + " " + resp, re.IGNORECASE)
                    if m:
                        target = m.group(1)
                        act = "close" if any(w in lowered for w in ("close", "band")) else "open"
                        reconstructed = f"{act} {target}"
                        cls._record_observation("pronoun_to_file", target)
                        return True, reconstructed, f"recent_turn_entity({target})", 0.86

        return False, None, None, 0.0

    @classmethod
    def _record_observation(cls, pattern_key: str, context_target: str) -> bool:
        k = f"{pattern_key}:{context_target}"
        cls._pattern_observations[k] = cls._pattern_observations.get(k, 0) + 1
        return cls._pattern_observations[k] >= cls._PROMOTION_THRESHOLD

    @classmethod
    def get_pattern_observation_count(cls, pattern_key: str, context_target: str) -> int:
        k = f"{pattern_key}:{context_target}"
        return cls._pattern_observations.get(k, 0)

    @classmethod
    def is_pattern_promoted(cls, pattern_key: str, context_target: str) -> bool:
        return cls.get_pattern_observation_count(pattern_key, context_target) >= cls._PROMOTION_THRESHOLD


@dataclass
class ConfidenceScores:
    audio: float = 0.85
    stt: float = 0.90
    language: float = 0.88
    intent: float = 0.90
    entity: float = 0.85
    context: float = 0.80
    combined: float = 0.87


@dataclass
class SpeechUnderstandingResult:
    raw_stt: str
    cleaned_input: str
    correction_applied: Optional[str]
    intent: str
    entities: Dict[str, Any]
    decision: SpeechDecision
    clarification_prompt: Optional[str]
    confidence: ConfidenceScores
    diagnostics: Dict[str, Any]
    input_quality: InputQuality = InputQuality.CLEAN
    recovered_interpretation: Optional[str] = None
    context_used: Optional[str] = None


class LinguisticFillerFilter:
    """
    Strips conversational noise, polite fillers, and speech hesitations
    while strictly protecting critical target entities (apps, websites, files, tabs, actions).
    """

    # Non-destructive conversational prefixes and fillers
    FILLER_PATTERNS = [
        # Hesitation particles with optional punctuation dots / commas
        r"\b(?:umm+|uhh+|aah+|err+|actually|basically)(?:[\.\,\s]+|\b)",
        # Conversational prefixes / polite markers
        r"^(?:jarvis|bhai|yaar|dost|bro|boss|hey\s+jarvis|ok\s+jarvis|suno\s+jarvis)[\,\.\s]*",
        r"^(?:please|kripya|zara|ek\s+kaam\s+karo|ek\s+baar|sunna|arey?)[\,\.\s]*",
        # NOTE: 'thoda' intentionally removed from prefix-filler list —
        # it is a QUANTITY modifier (HindiVocabCategory.QUANTITY).
        # "thoda volume badhao" → 'thoda' must be preserved for the quantity multiplier.
        # Mid-sentence colloquial connectors
        r"\b(?:please\s+yaar|yaar\s+zara|zara\s+sa|bhai\s+zara|bhai\s+please)[\,\.\s]*",
        r"\b(?:ko\s+zara|ko\s+please|ko\s+ek\s+baar)\b",
        r"\b(?:woh\s+kya\s+hai\s+na|woh\s+jo)\b",
        r"\bwoh\s+(?=[a-z0-9])",  # "woh Chrome khol de" -> "Chrome khol de"
    ]

    _COMPILED_FILLERS = [re.compile(p, re.IGNORECASE) for p in FILLER_PATTERNS]

    # Clean punctuation and collapsed spaces
    _WHITESPACE_RE = re.compile(r"\s+")

    @classmethod
    def clean(cls, text: str) -> str:
        """Removes conversational fillers while maintaining entity integrity."""
        if not text:
            return ""

        res = text.strip()

        # Clean leading punctuation ellipses / dots
        res = re.sub(r"^[\.\,\-\s]+", "", res)

        # Apply filler stripping iteratively (2 passes to catch compound fillers like 'umm... please, actually')
        for _ in range(3):
            prev = res
            for pattern in cls._COMPILED_FILLERS:
                res = pattern.sub(" ", res)
            res = re.sub(r"^[\.\,\-\s]+", "", res)
            res = cls._WHITESPACE_RE.sub(" ", res).strip()
            if res == prev:
                break

        # Clean trailing polite suffixes: e.g. "open kar do please", "khol do yaar"
        res = re.sub(r"\s*,?\s*\b(?:please|yaar|bhai|boss|kripya)\s*$", "", res, flags=re.IGNORECASE)

        # Collapse whitespace
        res = cls._WHITESPACE_RE.sub(" ", res).strip()
        return res


class ContextAwareSpeechCorrector:
    """
    Applies context-driven acoustic correction to STT transcripts.
    Uses active window context, foreground process, and known entity vocabularies
    to recover phonetically similar slips (e.g. 'type' -> 'tab').
    """

    # Phonetic and acoustic confusions with context clues
    PHONETIC_CONFUSIONS = [
        # (Pattern, Correction, Context Condition, Description)
        (
            re.compile(r"\b([a-z0-9]+)\s+type\s+(?:ko\s+)?(?:band|close)\s+(?:karo|kar\s+do|karna)\b", re.IGNORECASE),
            r"\1 tab ko band karo",
            "browser_or_tab",
            "type -> tab in close context"
        ),
        (
            re.compile(r"\b(?:ye|current|this|active|wala)\s+type\s+(?:ko\s+)?(?:band|close)\b", re.IGNORECASE),
            r"current tab close karo",
            "browser_or_tab",
            "this type -> current tab"
        ),
        (
            re.compile(r"\btype\s+(?:ko\s+)?(?:band|close)\s+(?:karo|kar\s+do|kardo)\b", re.IGNORECASE),
            r"tab band karo",
            "browser_or_tab",
            "type band -> tab band"
        ),
        (
            re.compile(r"\bclose\s+(?:this|current)\s+type\b", re.IGNORECASE),
            r"close this tab",
            "browser_or_tab",
            "close this type -> close this tab"
        ),
        (
            re.compile(r"\bcruze\b|\bcloze\b", re.IGNORECASE),
            "close",
            "any",
            "cruze/cloze -> close"
        ),
        (
            re.compile(r"\bchrom\b|\bcrome\b", re.IGNORECASE),
            "chrome",
            "any",
            "chrom/crome -> chrome"
        ),
        (
            re.compile(r"\byoutub\b|\butube\b", re.IGNORECASE),
            "youtube",
            "any",
            "youtub -> youtube"
        ),
        (
            re.compile(r"\bexcl\b|\bexel\b", re.IGNORECASE),
            "excel",
            "any",
            "excl/exel -> excel"
        ),
        (
            re.compile(r"\bnotepd\b|\bnotpad\b", re.IGNORECASE),
            "notepad",
            "any",
            "notepd -> notepad"
        ),
        (
            re.compile(r"\bgrave\b", re.IGNORECASE),
            "Brave",
            "browser_or_tab",
            "grave -> Brave in browser context"
        ),
    ]

    @classmethod
    def correct(
        cls,
        text: str,
        active_context: Optional[Any] = None,
        target_engine: Optional[Any] = None
    ) -> Tuple[str, Optional[str]]:
        """
        Evaluates context and corrects speech-to-text slips.
        Returns (corrected_text, correction_applied_description).
        """
        if not text:
            return text, None

        corrected = text.strip()
        applied_notes = []

        # Check if active window is a browser or desktop context
        is_browser_context = False
        if active_context:
            cur_app = (getattr(active_context, "application", "") or "").lower()
            cur_site = (getattr(active_context, "website", "") or "").lower()
            is_browser_context = bool(
                cur_site or any(b in cur_app for b in ("chrome", "brave", "edge", "firefox", "browser"))
            )

        if not is_browser_context and target_engine and hasattr(target_engine, "window_manager"):
            try:
                fg = target_engine.window_manager.get_foreground_window()
                if fg and any(b in (fg.process_name or "").lower() for b in ("chrome", "brave", "edge", "firefox")):
                    is_browser_context = True
            except Exception:
                pass

        # If phrase specifically talks about closing/switching tabs, treat as tab-compatible
        phrase_lower = text.lower()
        if any(w in phrase_lower for w in ("band", "close", "khatam", "hata", "switch")):
            is_browser_context = True

        for pat, repl, cond, desc in cls.PHONETIC_CONFUSIONS:
            if cond == "browser_or_tab" and not is_browser_context:
                continue

            if pat.search(corrected):
                corrected = pat.sub(repl, corrected)
                applied_notes.append(desc)

        correction_str = ", ".join(applied_notes) if applied_notes else None
        return corrected, correction_str


class SpeechConfidenceModel:
    """
    Multi-dimensional confidence scoring engine evaluating:
    1. Audio confidence (SNR, dynamic range, clipping penalty)
    2. STT confidence (recognition certainty)
    3. Language confidence (grammatical / syntactical structure)
    4. Intent confidence (intent matching clarity)
    5. Entity confidence (known entities vs gibberish)
    6. Context confidence (compatibility with active window / workflow)
    """

    KNOWN_ENTITIES = {
        "chrome", "google chrome", "brave", "excel", "word", "notepad",
        "calculator", "calc", "settings", "camera", "terminal", "powershell",
        "cmd", "spotify", "vlc", "youtube", "task manager", "taskmgr",
        "tab", "current tab", "this tab", "volume", "time", "date", "joke", "weather",
        # Hindi/Hinglish semantic vocab words (body, emotion, time, direction)
        # Imported at class definition time to avoid circular imports at hot-path
        "bhookh", "pyaas", "neend", "thakan", "dard", "garmi", "sardi", "aaram",
        "khushi", "dukh", "gussa", "pyaar", "nafrat", "dar", "tension", "pareshani",
        "excited", "bored",
        "abhi", "aaj", "kal", "parso", "subah", "dopahar", "shaam", "raat",
        "upar", "niche", "aage", "peeche", "andar", "bahar", "idhar", "udhar",
    }

    DESTRUCTIVE_ACTIONS = {
        "shutdown", "restart", "reboot", "delete_file", "kill_process",
        "format_disk", "empty_trash", "wipe_memory"
    }

    @classmethod
    def evaluate(
        cls,
        text: str,
        cleaned_text: str,
        audio_conf: float = 0.85,
        active_context: Optional[Any] = None,
        semantic_act: Optional[Any] = None,
        is_fast_path_candidate: bool = False,
        input_quality: InputQuality = InputQuality.CLEAN
    ) -> Tuple[ConfidenceScores, SpeechDecision, Optional[str]]:
        """
        Computes composite confidence and renders a safe execution decision.
        """
        lowered = cleaned_text.lower()

        # Quality-driven immediate uncertainty handling
        if input_quality == InputQuality.UNINTELLIGIBLE:
            scores = ConfidenceScores(
                audio=round(audio_conf, 3),
                stt=0.10,
                language=0.05,
                intent=0.05,
                entity=0.05,
                context=0.05,
                combined=0.05
            )
            return scores, SpeechDecision.CLARIFY, NaturalUncertaintyResponder.get_unintelligible_response()

        if input_quality == InputQuality.INCOMPLETE_FRAGMENT:
            scores = ConfidenceScores(
                audio=round(audio_conf, 3),
                stt=0.30,
                language=0.20,
                intent=0.20,
                entity=0.20,
                context=0.20,
                combined=0.20
            )
            return scores, SpeechDecision.CLARIFY, NaturalUncertaintyResponder.get_incomplete_response()

        if input_quality == InputQuality.AMBIGUOUS:
            scores = ConfidenceScores(
                audio=round(audio_conf, 3),
                stt=0.85,
                language=0.80,
                intent=0.50,
                entity=0.20,
                context=0.30,
                combined=0.45
            )
            return scores, SpeechDecision.CLARIFY, NaturalUncertaintyResponder.get_ambiguous_response()

        if input_quality == InputQuality.EMPTY:
            scores = ConfidenceScores(
                audio=0.0, stt=0.0, language=0.0, intent=0.0, entity=0.0, context=0.0, combined=0.0
            )
            return scores, SpeechDecision.IGNORE_NOISE, None

        # 0. Deterministic math fast-lane: never ask to repeat "2+2=?".
        try:
            from plugins.math.calculator import SpokenMathNormalizer as _MathNorm2
            if _MathNorm2.is_math_query(cleaned_text) or _MathNorm2.is_math_query(text):
                scores = ConfidenceScores(
                    audio=round(audio_conf, 3),
                    stt=0.95,
                    language=0.95,
                    intent=0.95,
                    entity=0.90,
                    context=0.80,
                    combined=0.93,
                )
                return scores, SpeechDecision.EXECUTE_VERIFIED, None
        except Exception:
            pass

        # 1. STT Confidence
        stt_conf = 0.94 if len(cleaned_text.split()) >= 2 else (0.85 if cleaned_text else 0.20)

        # 2. Language Confidence (coherence of phrasing)
        lang_conf = 0.88
        if any(w in lowered for w in (
            "kholo", "open", "band", "close", "chalao", "play", "batao",
            "karo", "what", "how",
            # Hindi semantic vocab action/direction/time markers
            "dikhao", "bhejo", "rokna", "lao", "hatao", "rakho",
            "abhi", "aaj", "kal", "subah", "raat", "shaam",
            "upar", "niche", "aage", "peeche", "andar", "bahar",
        )):
            lang_conf = 0.95
        elif len(cleaned_text.split()) == 1 and cleaned_text not in cls.KNOWN_ENTITIES:
            lang_conf = 0.45

        # 3. Intent Confidence
        intent_conf = 0.50
        if is_fast_path_candidate:
            intent_conf = 0.98
        elif semantic_act:
            intent_conf = getattr(semantic_act, "confidence", 0.90)
        elif any(w in lowered for w in ("open", "kholo", "close", "band", "play", "chalao", "volume", "time", "joke")):
            intent_conf = 0.88

        # 4. Entity Confidence
        entity_conf = 0.40
        matched_entity = None
        for ent in cls.KNOWN_ENTITIES:
            if ent in lowered:
                entity_conf = 0.95
                matched_entity = ent
                break

        # 5. Context Confidence
        context_conf = 0.70
        if active_context:
            cur_app = (getattr(active_context, "application", "") or "").lower()
            if matched_entity and cur_app and matched_entity in cur_app:
                context_conf = 0.95
            elif "tab" in lowered and any(b in cur_app for b in ("chrome", "brave", "edge", "firefox")):
                context_conf = 0.98

        # Combined Weighted Confidence
        combined = (
            0.15 * audio_conf +
            0.20 * stt_conf +
            0.15 * lang_conf +
            0.25 * intent_conf +
            0.15 * entity_conf +
            0.10 * context_conf
        )

        scores = ConfidenceScores(
            audio=round(audio_conf, 3),
            stt=round(stt_conf, 3),
            language=round(lang_conf, 3),
            intent=round(intent_conf, 3),
            entity=round(entity_conf, 3),
            context=round(context_conf, 3),
            combined=round(combined, 3)
        )

        # Decision Logic:
        # Check destructive actions first
        if any(d in lowered for d in ("shutdown", "restart", "reboot", "format", "delete")):
            return scores, SpeechDecision.CONFIRM_DESTRUCTIVE, None

        if is_fast_path_candidate:
            return scores, SpeechDecision.EXECUTE_FAST_PATH, None

        # Human-like principle:
        # "Low volume != ignore user". If intent + entity are clear, execute safely!
        if intent_conf >= 0.80 and entity_conf >= 0.80:
            return scores, SpeechDecision.EXECUTE_VERIFIED, None

        # Pure conversational chitchat or greeting
        if any(w in lowered for w in ("hi", "hello", "kaise ho", "kya haal hai", "thanks", "joke", "shukriya")):
            return scores, SpeechDecision.CONVERSATION, None

        # If combined confidence is strong
        if combined >= 0.70:
            return scores, SpeechDecision.EXECUTE_VERIFIED, None

        # Genuine ambiguity -> Short, polite clarification (never repetitive)
        if intent_conf >= 0.60 and entity_conf < 0.50:
            clarification = NaturalUncertaintyResponder.get_ambiguous_response()
            return scores, SpeechDecision.CLARIFY, clarification

        if combined < 0.40:
            return scores, SpeechDecision.CLARIFY, NaturalUncertaintyResponder.get_unintelligible_response()

        clarification = NaturalUncertaintyResponder.get_ambiguous_response()
        return scores, SpeechDecision.CLARIFY, clarification


class SpeechDiagnosticsLogger:
    """
    Logs structured, standardized diagnostics for every speech understanding turn
    covering all 11 required fields.
    """

    @classmethod
    def log(
        cls,
        microphone_device: str,
        input_level: float,
        noise_floor: float,
        adaptive_threshold: float,
        vad_state: str,
        stt_result: str,
        correction_applied: Optional[str],
        intent: str,
        entities: Dict[str, Any],
        confidence_scores: ConfidenceScores,
        final_action: str
    ) -> None:
        diag = (
            f"[SPEECH_DIAGNOSTICS] Device='{microphone_device}' | "
            f"Level={input_level:.1f} | NoiseFloor={noise_floor:.1f} | "
            f"Thresh={adaptive_threshold:.1f} | VAD={vad_state} | "
            f"STT='{stt_result}' | Corrected='{correction_applied or 'none'}' | "
            f"Intent='{intent}' | Entities={entities} | "
            f"Conf[Audio={confidence_scores.audio}, STT={confidence_scores.stt}, "
            f"Intent={confidence_scores.intent}, Entity={confidence_scores.entity}, "
            f"Context={confidence_scores.context}, Combined={confidence_scores.combined}] | "
            f"Action='{final_action}'"
        )
        logger.info(diag)


class SpeechUnderstandingEngine:
    """
    Unified entry point orchestrating Speech Normalization, Context-Aware Correction,
    Multi-Dimensional Confidence Evaluation, and Diagnostics.
    """

    @classmethod
    def process_speech_input(
        cls,
        raw_text: str,
        audio_conf: float = 0.85,
        active_context: Optional[Any] = None,
        target_engine: Optional[Any] = None,
        device_name: str = "Default Microphone",
        input_level: float = 50.0,
        noise_floor: float = 25.0,
        recent_turns: Optional[List[Any]] = None,
        active_dialog_pending: bool = False,
    ) -> SpeechUnderstandingResult:
        start_t = time.perf_counter()

        # 1. Linguistic Filler & Hesitation Removal
        cleaned = LinguisticFillerFilter.clean(raw_text)

        # 2. Input Quality Evaluation (detect unintelligible mash, fragments, ambiguous pronouns)
        quality, quality_score, quality_meta = InputQualityEvaluator.evaluate_quality(
            raw_text, cleaned, active_dialog_pending=active_dialog_pending
        )

        # 3. Contextual Recovery Pipeline
        # (Before declaring input unintelligible, attempt contextual recovery across
        # active context, recent conversation history, and active windows)
        is_recovered = False
        reconstructed_text = None
        context_used = None
        rec_conf = 0.0

        is_recovered, reconstructed_text, context_used, rec_conf = ContextualRecoveryEngine.attempt_recovery(
            text=cleaned,
            quality=quality,
            active_context=active_context,
            recent_turns=recent_turns,
            target_engine=target_engine
        )

        # 4. Context-Aware Acoustic Correction
        corr_note = None
        if is_recovered and reconstructed_text:
            effective_input = reconstructed_text
            corr_note = f"Contextual recovery: {context_used}"
            quality = InputQuality.CLEAN
        else:
            corrected, corr_note = ContextAwareSpeechCorrector.correct(
                cleaned, active_context=active_context, target_engine=target_engine
            )
            effective_input = corrected if corrected else cleaned

        # 5. Fast-Path Candidate Check
        is_fast_candidate = False
        eff_lower = effective_input.lower()
        if quality == InputQuality.CLEAN:
            try:
                from plugins.math.calculator import SpokenMathNormalizer as _MathNorm3
                if _MathNorm3.is_math_query(effective_input):
                    is_fast_candidate = True
            except Exception:
                pass
            if any(eff_lower.startswith(p) for p in (
                "open ", "kholo ", "close ", "band ", "volume ", "time", "joke",
                "abhi ", "aaj ",  # time-qualified fast commands
            )):
                is_fast_candidate = True
            elif eff_lower in ("what time is it", "tell me a joke", "close this tab", "tab band karo"):
                is_fast_candidate = True

        # 6. Multi-Dimensional Confidence Evaluation
        scores, decision, clarif_prompt = SpeechConfidenceModel.evaluate(
            text=raw_text,
            cleaned_text=effective_input,
            audio_conf=audio_conf,
            active_context=active_context,
            is_fast_path_candidate=is_fast_candidate,
            input_quality=quality
        )

        # 7. Extract intent & entities summary
        intent_name = "unknown"
        entities = {}
        if is_fast_candidate:
            intent_name = "fast_path_candidate"
            entities = {"query": effective_input}
        elif quality == InputQuality.UNINTELLIGIBLE:
            intent_name = "unknown"
        elif quality == InputQuality.INCOMPLETE_FRAGMENT:
            intent_name = "incomplete_fragment"
        elif quality == InputQuality.AMBIGUOUS:
            intent_name = "ambiguous_command"
        elif decision == SpeechDecision.CONVERSATION:
            intent_name = "conversation_chitchat"
        elif decision == SpeechDecision.CONFIRM_DESTRUCTIVE:
            intent_name = "destructive_action"

        # Comprehensive 7-field UI / Debug Telemetry
        diagnostics_data = {
            "device": device_name,
            "input_level": input_level,
            "noise_floor": noise_floor,
            "vad_state": "SPEECH_FINALIZED",
            "scores": scores,
            "decision": decision.value,
            "raw_input": raw_text,
            "normalized_input": effective_input,
            "input_quality": quality.value,
            "detected_intent": intent_name,
            "confidence": scores.combined,
            "context_used": context_used,
            "recovered_interpretation": reconstructed_text if is_recovered else None,
        }

        # Log diagnostics
        SpeechDiagnosticsLogger.log(
            microphone_device=device_name,
            input_level=input_level,
            noise_floor=noise_floor,
            adaptive_threshold=noise_floor * 1.35,
            vad_state="SPEECH_FINALIZED",
            stt_result=raw_text,
            correction_applied=corr_note,
            intent=intent_name,
            entities=entities,
            confidence_scores=scores,
            final_action=decision.value
        )

        return SpeechUnderstandingResult(
            raw_stt=raw_text,
            cleaned_input=effective_input,
            correction_applied=corr_note,
            intent=intent_name,
            entities=entities,
            decision=decision,
            clarification_prompt=clarif_prompt,
            confidence=scores,
            diagnostics=diagnostics_data,
            input_quality=quality,
            recovered_interpretation=reconstructed_text if is_recovered else None,
            context_used=context_used
        )
