# core/universal_window_resolver.py
"""
Universal Application & Window Resolution Engine for Jarvis V2.1.
[AUTHORITATIVE OWNER / SINGLE SOURCE OF TRUTH (SSOT)]

Provides a multi-signal, token-based, fuzzy window and application resolution pipeline.
Eliminates brittle exact string matching and application-specific hardcoding.
Handles:
- Natural Language & Hinglish phrasings
- Demonstratives & Deictic Pronouns ('yah window', 'yeh', 'ye', 'this', 'current', 'isko')
- ASR / Speech Recognition noise suffixes ('id', 'ide', 'app', 'application', 'browser', 'software')
- Spaces, hyphens, and punctuation differences ('anti gravity', 'anti-gravity' -> 'antigravity')
- Dynamic window titles (e.g. 'Jarvis_19-09-2026 - Antigravity IDE - main.py')
- Multi-signal confidence scoring across process, exe, title, tokens, and fuzzy similarity
- Distinguishing PROCESS_RUNNING, WINDOW_EXISTS, VISIBLE_WINDOW, MINIMIZED_WINDOW, FOREGROUND_WINDOW
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("jarvis.core.universal_window_resolver")


@dataclass
class NormalizedTarget:
    """Normalized multi-representation view of a target application query."""
    raw: str
    clean: str
    collapsed: str
    noise_stripped: str
    collapsed_stripped: str
    tokens: List[str]
    has_noise_suffix: bool = False


class UniversalAppNormalizer:
    """
    Normalizes application and window target queries into canonical forms.
    Context-aware: strips noise words without stripping meaningful single-token queries.
    """

    PUNCTUATION_RE = re.compile(r"[-_./\\]+")
    NON_ALPHANUM_RE = re.compile(r"[^a-z0-9]")
    WHITESPACE_RE = re.compile(r"\s+")

    # Words that often appear as noise, suffixes, or conversational artifacts
    NOISE_WORDS: Set[str] = {
        "id", "ide", "app", "application", "software", "program",
        "browser", "brouser", "browzer", "broser", "window",
        "wala", "wali", "wale", "ko", "ka", "ki", "ke", "par", "pe",
        "mein", "me", "the"
    }

    # Relative demonstrative terms meaning current / active / foreground window
    RELATIVE_TERMS: Set[str] = {
        "current", "this", "active", "focused", "foreground",
        "is window", "iss window", "ye window", "yeh window", "yah window",
        "this window", "current window", "active window", "focused window",
        "isko", "ise", "isse", "isey", "ye wala", "yeh wala", "yah wala",
        "yah", "yeh", "ye", "is", "iss", "window"
    }

    COMPOUND_PREFIXES: Set[str] = {
        "anti", "micro", "auto", "multi", "meta", "sub", "super", "hyper", "post", "pre", "non"
    }

    @classmethod
    def is_relative_target(cls, target: str) -> bool:
        """Determines if target refers to the active/current foreground window or recent conversational target."""
        if not target:
            return True
        norm = cls.WHITESPACE_RE.sub(" ", target.lower().strip())
        return norm in cls.RELATIVE_TERMS

    @classmethod
    def normalize(cls, query: str) -> NormalizedTarget:
        """
        Produces multiple search representations of the input query.
        Example:
            'Anti Gravity ID' ->
                clean: 'anti gravity id'
                collapsed: 'antigravityid'
                noise_stripped: 'antigravity'
                collapsed_stripped: 'antigravity'
                tokens: ['antigravity']
        """
        raw = query or ""
        lowered = raw.lower().strip()

        # Replace hyphens, underscores, dots, slashes with spaces for tokenization
        clean = cls.PUNCTUATION_RE.sub(" ", lowered)
        clean = cls.WHITESPACE_RE.sub(" ", clean).strip()

        collapsed = cls.NON_ALPHANUM_RE.sub("", lowered)

        # Split into tokens
        tokens = [t for t in clean.split() if t]

        # Strip trailing noise words if we have more than 1 token
        stripped_tokens = list(tokens)
        has_noise = False
        while len(stripped_tokens) > 1 and stripped_tokens[-1] in cls.NOISE_WORDS:
            stripped_tokens.pop()
            has_noise = True

        # Also strip leading noise words if multi-token (e.g. 'the chrome app')
        while len(stripped_tokens) > 1 and stripped_tokens[0] in cls.NOISE_WORDS:
            stripped_tokens.pop(0)
            has_noise = True

        # Merge compound prefixes (e.g. anti-gravity -> antigravity)
        if len(stripped_tokens) >= 2 and stripped_tokens[0] in cls.COMPOUND_PREFIXES:
            merged_first = f"{stripped_tokens[0]}{stripped_tokens[1]}"
            stripped_tokens = [merged_first] + stripped_tokens[2:]

        noise_stripped = " ".join(stripped_tokens)
        collapsed_stripped = cls.NON_ALPHANUM_RE.sub("", noise_stripped)

        return NormalizedTarget(
            raw=raw,
            clean=clean,
            collapsed=collapsed,
            noise_stripped=noise_stripped,
            collapsed_stripped=collapsed_stripped,
            tokens=stripped_tokens,
            has_noise_suffix=has_noise
        )


@dataclass
class ScoredWindowMatch:
    """Represents an evaluated window candidate with score and diagnostic reasons."""
    window: Any  # WindowInfo
    score: float
    matched_signals: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def __post_init__(self):
        self.confidence = min(1.0, max(0.0, round(self.score / 100.0, 3)))


class UniversalWindowResolver:
    """
    Authoritative engine for resolving target strings to Windows top-level windows.
    Evaluates process names, executable paths, window titles, tokens, fuzzy metrics,
    and runtime system state.
    """

    _instance: Optional["UniversalWindowResolver"] = None

    # Common canonical alias mapping for desktop apps
    COMMON_ALIASES: Dict[str, Tuple[str, ...]] = {
        "antigravity": ("antigravity ide", "antigravity", "antigravity.exe", "antigravity ide.exe"),
        "chrome": ("google chrome", "chrome.exe", "chrome"),
        "google chrome": ("chrome", "chrome.exe", "google chrome"),
        "vscode": ("visual studio code", "code.exe", "code", "vs code"),
        "vs code": ("visual studio code", "code.exe", "code", "vscode"),
        "visual studio code": ("code", "code.exe", "vscode", "vs code"),
        "notepad": ("notepad.exe", "notepad"),
        "calc": ("calculator", "calculatorapp.exe", "calc.exe"),
        "calculator": ("calc", "calculatorapp.exe", "calc.exe"),
        "edge": ("microsoft edge", "msedge.exe", "edge"),
        "brave": ("brave browser", "brave.exe", "brave"),
        "vlc": ("vlc media player", "vlc.exe", "vlc"),
        "explorer": ("file explorer", "windows explorer", "explorer.exe"),
        "word": ("microsoft word", "winword.exe", "word"),
        "excel": ("microsoft excel", "excel.exe", "excel"),
        "powerpoint": ("microsoft powerpoint", "powerpnt.exe", "powerpoint"),
    }

    def __init__(self):
        self.normalizer = UniversalAppNormalizer()
        self._last_context: Dict[str, Any] = {}
        self._context_timeout_sec: float = 60.0

    @classmethod
    def get_instance(cls) -> "UniversalWindowResolver":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def update_context(
        self,
        app_name: str,
        window_title: str = "",
        hwnd: int = 0,
        process_name: str = "",
        action: str = ""
    ) -> None:
        """Updates the recent target conversation context with timestamp."""
        self._last_context = {
            "app_name": app_name,
            "window_title": window_title,
            "hwnd": hwnd,
            "process_name": process_name,
            "action": action,
            "timestamp": time.time()
        }
        logger.debug("CONVERSATION_CONTEXT_UPDATED target=%r hwnd=%s", app_name, hwnd)

    def get_active_context(self) -> Optional[Dict[str, Any]]:
        """Returns the recent target context if not expired."""
        if not self._last_context:
            return None
        elapsed = time.time() - self._last_context.get("timestamp", 0.0)
        if elapsed <= self._context_timeout_sec:
            return dict(self._last_context)
        return None

    def match_windows(
        self,
        target: str,
        windows: List[Any],
        context: Optional[Dict[str, Any]] = None,
        fg_hwnd: Optional[int] = None
    ) -> List[ScoredWindowMatch]:
        """
        Evaluates a list of WindowInfo candidates against the target query.
        Returns candidates ranked by confidence score in descending order.
        """
        if not windows:
            return []

        norm = self.normalizer.normalize(target)
        target_clean = norm.clean
        target_collapsed = norm.collapsed
        target_stripped = norm.noise_stripped
        target_collapsed_stripped = norm.collapsed_stripped
        target_tokens = norm.tokens

        # Check conversation context if target is deictic/pronoun
        is_deictic = self.normalizer.is_relative_target(target)
        active_ctx = context or self.get_active_context()

        # Build alias variants
        alias_terms = set()
        for term_key in (target_clean, target_collapsed, target_stripped, target_collapsed_stripped):
            if term_key in self.COMMON_ALIASES:
                alias_terms.update(self.COMMON_ALIASES[term_key])

        # Also incorporate WindowsAppResolver specs if available
        try:
            from core.windows_app_resolver import get_windows_app_resolver
            spec = get_windows_app_resolver().get_app_spec(target_clean) or get_windows_app_resolver().get_app_spec(target_stripped)
            if spec:
                if spec.display_name:
                    alias_terms.add(spec.display_name.lower())
                if spec.canonical_id:
                    alias_terms.add(spec.canonical_id.lower())
                for t in spec.window_titles:
                    alias_terms.add(t.lower())
                for p in spec.process_names:
                    alias_terms.add(p.lower())
                for a in spec.aliases:
                    alias_terms.add(a.lower())
        except Exception:
            pass

        scored_matches: List[ScoredWindowMatch] = []

        for w in windows:
            score = 0.0
            signals: List[str] = []

            title = (getattr(w, "title", "") or "").strip()
            title_lower = title.lower()
            title_collapsed = self.normalizer.NON_ALPHANUM_RE.sub("", title_lower)
            title_tokens = [t for t in self.normalizer.PUNCTUATION_RE.sub(" ", title_lower).split() if t]

            pname = (getattr(w, "process_name", "") or "").strip()
            pname_lower = pname.lower()
            pname_base = pname_lower[:-4] if pname_lower.endswith(".exe") else pname_lower
            pname_collapsed = self.normalizer.NON_ALPHANUM_RE.sub("", pname_lower)
            pname_base_collapsed = self.normalizer.NON_ALPHANUM_RE.sub("", pname_base)

            hwnd = getattr(w, "hwnd", 0)
            is_fg = (fg_hwnd and hwnd == fg_hwnd) or getattr(w, "is_foreground", False)

            # -------------------------------------------------------------
            # CASE A: Deictic / Relative Reference ('yah window', 'isko', 'this')
            # -------------------------------------------------------------
            if is_deictic:
                if is_fg:
                    score += 100.0
                    signals.append("deictic_foreground")
                elif active_ctx and active_ctx.get("hwnd") == hwnd:
                    score += 95.0
                    signals.append("deictic_context_hwnd")
                elif active_ctx and active_ctx.get("app_name"):
                    ctx_app = active_ctx["app_name"].lower()
                    if ctx_app in pname_lower or ctx_app in title_lower:
                        score += 90.0
                        signals.append("deictic_context_app")
                else:
                    score += 50.0
                    signals.append("deictic_generic")

                scored_matches.append(ScoredWindowMatch(window=w, score=score, matched_signals=signals))
                continue

            # -------------------------------------------------------------
            # SIGNAL 1: Process / Executable Name Matching
            # -------------------------------------------------------------
            # 1a. Exact or Collapsed Process Match
            if target_clean in (pname_lower, pname_base) or target_stripped in (pname_lower, pname_base):
                score += 95.0
                signals.append("process_exact")
            elif target_collapsed_stripped in (pname_collapsed, pname_base_collapsed) or target_collapsed in (pname_collapsed, pname_base_collapsed):
                score += 92.0
                signals.append("process_collapsed_exact")
            elif target_collapsed_stripped and target_collapsed_stripped in pname_base_collapsed:
                score += 88.0
                signals.append("process_collapsed_substring")
            elif target_stripped and target_stripped in pname_base:
                score += 85.0
                signals.append("process_substring")

            # 1b. Alias / Spec Process Match
            if any(a in pname_lower or pname_lower in a for a in alias_terms):
                score += 85.0
                signals.append("process_alias_match")

            # -------------------------------------------------------------
            # SIGNAL 2: Window Title Matching
            # -------------------------------------------------------------
            # 2a. Collapsed Title Containment
            if target_collapsed_stripped and target_collapsed_stripped in title_collapsed:
                score += 86.0
                signals.append("title_collapsed_substring")
            elif target_stripped and target_stripped in title_lower:
                score += 84.0
                signals.append("title_substring")

            # 2b. Token Subset Match (all target tokens appear in title or process)
            if len(target_tokens) >= 2:
                combined_text = f"{title_lower} {pname_lower}"
                if all(tok in combined_text for tok in target_tokens):
                    score += 85.0
                    signals.append("all_tokens_contained")
                else:
                    overlap = sum(1 for tok in target_tokens if tok in combined_text)
                    if overlap > 0:
                        ratio = float(overlap) / float(len(target_tokens))
                        score += 50.0 * ratio
                        signals.append(f"token_overlap_{overlap}_{len(target_tokens)}")

            # 2c. Alias in Title
            if any(a in title_lower for a in alias_terms if not a.endswith(".exe")):
                score += 80.0
                signals.append("title_alias_match")

            # -------------------------------------------------------------
            # SIGNAL 3: Fuzzy Sequence / Levenshtein Matching
            # -------------------------------------------------------------
            # Test fuzzy ratio on process base and distinct title segments
            best_fuzzy = 0.0
            test_terms = [t for t in (target_stripped, target_clean, target_collapsed_stripped) if t]
            for term in test_terms:
                best_fuzzy = max(best_fuzzy, SequenceMatcher(None, term, pname_base).ratio())
                best_fuzzy = max(best_fuzzy, SequenceMatcher(None, term, pname_base_collapsed).ratio())
                for segment in re.split(r"[-–—:|]", title_lower):
                    seg_clean = segment.strip()
                    if seg_clean:
                        best_fuzzy = max(best_fuzzy, SequenceMatcher(None, term, seg_clean).ratio())

            if best_fuzzy >= 0.85:
                score += best_fuzzy * 80.0
                signals.append(f"fuzzy_high_{best_fuzzy:.2f}")
            elif best_fuzzy >= 0.65:
                score += best_fuzzy * 60.0
                signals.append(f"fuzzy_mid_{best_fuzzy:.2f}")

            # -------------------------------------------------------------
            # SIGNAL 4: Active & Foreground Modifiers
            # -------------------------------------------------------------
            if is_fg:
                score += 15.0
                signals.append("is_foreground")

            if getattr(w, "is_maximized", False):
                score += 5.0
            elif not getattr(w, "is_minimized", False):
                score += 10.0

            # Penalize system dialogs / helpers unless specifically targeting dialogs
            if getattr(w, "is_dialog", False):
                score -= 40.0
                signals.append("is_dialog_penalty")

            # Context boost
            if active_ctx and active_ctx.get("hwnd") == hwnd:
                score += 15.0
                signals.append("recent_context_match")

            if score >= 40.0:
                scored_matches.append(ScoredWindowMatch(
                    window=w,
                    score=score,
                    matched_signals=signals
                ))

        # Sort descending by score
        scored_matches.sort(key=lambda m: m.score, reverse=True)
        return scored_matches

    def resolve_window(
        self,
        target: str,
        windows: Optional[List[Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        fg_hwnd: Optional[int] = None
    ) -> Optional[Any]:
        """
        Finds and returns the best matching WindowInfo for a target query.
        Returns None if no candidate achieves reasonable confidence.
        """
        matches = self.match_windows(target, windows or [], context=context, fg_hwnd=fg_hwnd)
        if not matches:
            return None

        top = matches[0]
        logger.debug(
            "RESOLVED_WINDOW target=%r best_hwnd=%s title=%r score=%.2f signals=%s",
            target, top.window.hwnd, top.window.title, top.score, top.matched_signals
        )
        return top.window


# Global singleton instance
_resolver = UniversalWindowResolver()


def get_universal_window_resolver() -> UniversalWindowResolver:
    """Returns the singleton UniversalWindowResolver."""
    return _resolver


def normalize_application_name(name: str) -> str:
    """
    Public utility to normalize an application name into canonical collapsed/cleaned form.
    Example:
        normalize_application_name("Anti Gravity") -> "antigravity"
        normalize_application_name("Anti-Gravity") -> "antigravity"
        normalize_application_name("Anti Gravity ID") -> "antigravity"
        normalize_application_name("Google Chrome Browser") -> "google chrome"
    """
    norm = UniversalAppNormalizer.normalize(name)
    return norm.noise_stripped or norm.clean or norm.collapsed
