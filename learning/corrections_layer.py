# learning/corrections_layer.py
"""Layer 4: Real-time Corrections & Assumptions Feedback."""

from dataclasses import dataclass, field
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from memory.database import DatabaseManager
from .preferences_layer import PreferencesLayer
from .vocabulary_layer import VocabularyLayer

logger = logging.getLogger("jarvis.learning.corrections")


# Known browser names used throughout this module.
_BROWSERS: frozenset = frozenset(
    {"chrome", "edge", "brave", "firefox", "opera", "safari", "vivaldi"}
)


@dataclass
class CorrectionResult:
    is_correction: bool
    concept: str = ""
    old_value: str = ""
    new_value: str = ""
    explanation: str = ""
    # Extra structured data for browser-preference corrections
    correction_type: str = ""   # "browser_preference" | "vocabulary" | "general"
    target: str = ""            # the entity being opened (e.g. "youtube")
    preferred_container: str = ""  # the preferred browser / container


class CorrectionsLayer:
    """Layer 4: Detects user corrections and dynamically updates vocabulary & preferences."""

    def __init__(self, db: DatabaseManager, vocabulary: VocabularyLayer, preferences: PreferencesLayer):
        self.db = db
        self.vocabulary = vocabulary
        self.preferences = preferences

        # ---- Generic correction patterns (original set, unchanged) ----
        self._patterns = [
            # "nahi, Chrome nahi Edge kholo" / "nahi Chrome nahi Edge"
            re.compile(
                r"^(?:nahi|no|mat)[,\s]+\s*([a-zA-Z0-9_\-]+)\s+nahi\s+([a-zA-Z0-9_\-]+)"
                r"(?:\s+kholo|\s+use\s+karo|\s+open\s+karo|\s+chalao)?",
                re.IGNORECASE,
            ),
            # "no, open Edge instead of Chrome" / "open Edge instead of Chrome"
            re.compile(
                r"^(?:no|nahi)?[,\s]*(?:open|use|launch)?\s*([a-zA-Z0-9_\-]+)"
                r"\s+instead\s+of\s+([a-zA-Z0-9_\-]+)",
                re.IGNORECASE,
            ),
            # "by browser I mean Edge" / "browser matlab Edge"
            re.compile(
                r"^(?:by\s+)?([a-zA-Z0-9_\-]+)\s+(?:matlab|means|i mean)\s+([a-zA-Z0-9_\-]+)",
                re.IGNORECASE,
            ),
            # "don't use Chrome, use Edge"
            re.compile(
                r"^(?:don't|dont)\s+use\s+([a-zA-Z0-9_\-]+)[,\s]+use\s+([a-zA-Z0-9_\-]+)",
                re.IGNORECASE,
            ),
            # "nahi, maine bola tha Firefox mera favorite browser hai"
            re.compile(
                r"^(?:nahi|no)[,\s]+(?:maine\s+bola\s+tha\s+(?:ki\s+)?|maine\s+kaha\s+tha\s+(?:ki\s+)?)?"
                r"([a-zA-Z0-9_\-]+)\s+(?:mera|meri)\s+(?:favou?rite|preferred|pasandida)\s+(?:browser|brouser)\s+hai",
                re.IGNORECASE,
            ),
            # "nahi, mera favorite browser Firefox hai"
            re.compile(
                r"^(?:nahi|no)[,\s]+(?:maine\s+bola\s+tha\s+(?:ki\s+)?|maine\s+kaha\s+tha\s+(?:ki\s+)?)?"
                r"(?:mera|meri)\s+(?:favou?rite|preferred|pasandida)\s+(?:browser|brouser)\s+([a-zA-Z0-9_\-]+)(?:\s+hai)?",
                re.IGNORECASE,
            ),
        ]

        # ---- Browser-preference correction patterns (new) ----
        # Each pattern must produce:
        #   group(1) = target entity (e.g. "youtube")
        #   group(2) = preferred browser / container (e.g. "brave")
        #
        # Correction marker ("nahi", "no") is optional in some patterns because
        # the surrounding phrase structure already implies preference assignment.
        self._browser_pref_patterns: List[re.Pattern] = [
            # "nahi, youtube brave mein open karo"
            # "nahi youtube brave mein kholo"
            re.compile(
                r"^(?:nahi|no)[,\s]+(?:yaar[,\s]+)?([a-zA-Z0-9_.\-]+)\s+"
                r"([a-zA-Z0-9_\-]+)\s+mein\s+(?:open\s+karo|kholo|chalao|open\s+kar|open\s+karna|open\s+kare)",
                re.IGNORECASE,
            ),
            # "nahi, brave mein kholo" (target inferred from context — marked with sentinel)
            # Caller must resolve target from active context; target group = "" here.
            re.compile(
                r"^(?:nahi|no)[,\s]+(?:yaar[,\s]+)?([a-zA-Z0-9_\-]+)\s+mein\s+"
                r"(?:open\s+karo|kholo|chalao|open\s+kar|open\s+karna|open\s+kare|open\s+karo)",
                re.IGNORECASE,
            ),
            # "youtube brave mein open karo"  (no explicit correction marker but clear intent)
            re.compile(
                r"^([a-zA-Z0-9_.\-]+)\s+([a-zA-Z0-9_\-]+)\s+mein\s+"
                r"(?:open\s+karo|kholo|chalao|open\s+kar|open\s+karna|open\s+kare)",
                re.IGNORECASE,
            ),
            # "youtube ko brave mein kholo"
            re.compile(
                r"^([a-zA-Z0-9_.\-]+)\s+ko\s+([a-zA-Z0-9_\-]+)\s+mein\s+"
                r"(?:open\s+karo|kholo|chalao|open\s+kar|open\s+karna|open\s+kare)",
                re.IGNORECASE,
            ),
            # "ab se youtube brave mein kholna"
            re.compile(
                r"^ab\s+se\s+([a-zA-Z0-9_.\-]+)\s+([a-zA-Z0-9_\-]+)\s+mein\s+"
                r"(?:kholna|kholo|open\s+karo|chalao)",
                re.IGNORECASE,
            ),
            # "open youtube in brave" / "open youtube in chrome"  (English form)
            re.compile(
                r"^(?:nahi[,\s]+)?(?:open|launch|start)\s+([a-zA-Z0-9_.\-]+)\s+in\s+([a-zA-Z0-9_\-]+)",
                re.IGNORECASE,
            ),
            # "aaj ke liye youtube brave mein kholo"  (session scope marker)
            re.compile(
                r"^aaj\s+(?:ke\s+liye\s+)?([a-zA-Z0-9_.\-]+)\s+([a-zA-Z0-9_\-]+)\s+mein\s+"
                r"(?:open\s+karo|kholo|chalao|open\s+kar)",
                re.IGNORECASE,
            ),
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_and_apply_correction(self, text: str) -> CorrectionResult:
        cleaned = text.strip()

        # 1. Check browser-preference patterns first (higher priority, narrower scope)
        bp = self._parse_browser_preference(cleaned)
        if bp is not None:
            return bp

        # 2. Fall back to original generic correction patterns
        for idx, pattern in enumerate(self._patterns):
            m = pattern.match(cleaned)
            if m:
                if idx == 1:
                    new_val = m.group(1).strip()
                    old_val = m.group(2).strip()
                elif idx == 2:
                    concept = m.group(1).strip().lower()
                    new_val = m.group(2).strip()
                    old_val = self.vocabulary.get_term(concept) or "default"
                    self.vocabulary.learn_term(concept, new_val)
                    return CorrectionResult(
                        is_correction=True,
                        concept=concept,
                        old_value=old_val,
                        new_value=new_val,
                        explanation=f"Previous assumption: {concept} → {old_val}\nCorrection: {concept} → {new_val}",
                        correction_type="vocabulary",
                    )
                elif idx in (4, 5):
                    concept = "browser"
                    new_val = m.group(1).strip()
                    old_val = self.vocabulary.get_term("browser") or self.preferences.get("preferred_browser") or "chrome"
                    self.vocabulary.learn_term("browser", new_val.lower(), category="preferred_browser")
                    self.preferences.set("preferred_browser", new_val.lower())
                    return CorrectionResult(
                        is_correction=True,
                        concept=concept,
                        old_value=old_val,
                        new_value=new_val,
                        explanation=f"Aapka preferred browser {new_val.capitalize()} hai. Main ise yaad rakhunga.",
                        correction_type="vocabulary",
                    )
                else:
                    old_val = m.group(1).strip()
                    new_val = m.group(2).strip()

                concept = self._infer_concept(old_val, new_val)

                # Insert into corrections audit table
                sql = """
                INSERT INTO corrections (user_id, concept, original_value, corrected_value, occurrences, last_updated)
                VALUES ('default_user', ?, ?, ?, 1, ?)
                ON CONFLICT(user_id, original_value) DO UPDATE SET
                    corrected_value = excluded.corrected_value,
                    occurrences = occurrences + 1,
                    last_updated = excluded.last_updated
                """
                self.db.execute_update(sql, (concept or "general", old_val.lower(), new_val.lower(), time.time()))

                logger.info(f"Layer 4 Correction detected: concept '{concept}' | {old_val} -> {new_val}")
                return CorrectionResult(
                    is_correction=True,
                    concept=concept or "app",
                    old_value=old_val,
                    new_value=new_val,
                    explanation=f"Previous assumption:\n{concept or 'app'} → {old_val}\n\nCorrection:\n{concept or 'app'} → {new_val}",
                    correction_type="general",
                )

        return CorrectionResult(is_correction=False)

    # ------------------------------------------------------------------
    # Browser-preference pattern parser
    # ------------------------------------------------------------------

    def _parse_browser_preference(self, text: str) -> Optional[CorrectionResult]:
        """Try to extract a (target, browser) browser-preference correction.

        Returns a fully-populated CorrectionResult with
        ``correction_type="browser_preference"`` when a match is found,
        or ``None`` if no browser-preference pattern matches.
        """
        # Pattern index 0: "nahi, <target> <browser> mein open karo"  → groups (target, browser)
        # Pattern index 1: "nahi, <browser> mein kholo"               → groups (browser,)   target = ""
        # Pattern index 2: "<target> <browser> mein open karo"         → groups (target, browser)
        # Pattern index 3: "<target> ko <browser> mein kholo"          → groups (target, browser)
        # Pattern index 4: "ab se <target> <browser> mein kholna"      → groups (target, browser)
        # Pattern index 5: "open <target> in <browser>"                → groups (target, browser)
        # Pattern index 6: "aaj ke liye <target> <browser> mein..."   → groups (target, browser), session scope

        for idx, pat in enumerate(self._browser_pref_patterns):
            m = pat.match(text)
            if not m:
                continue

            groups = m.groups()
            scope = "session" if idx == 6 else "permanent"

            # Pattern 1: only one capture group → browser only (target from context)
            if len(groups) == 1 or (len(groups) >= 1 and idx == 1):
                browser_candidate = groups[0].strip().lower()
                if browser_candidate not in _BROWSERS:
                    continue
                # target = "" signals caller to use active context
                return CorrectionResult(
                    is_correction=True,
                    concept="browser",
                    old_value="",
                    new_value=browser_candidate,
                    explanation=f"Browser preference: (context target) → {browser_candidate}",
                    correction_type="browser_preference",
                    target="",                      # caller resolves from context
                    preferred_container=browser_candidate,
                )

            # All other patterns: two capture groups → (target, browser)
            g1, g2 = groups[0].strip().lower(), groups[1].strip().lower()

            # One of the two must be a known browser; the other is the target
            if g2 in _BROWSERS:
                target, browser = g1, g2
            elif g1 in _BROWSERS:
                # "brave youtube mein kholo" (unusual order) — skip, it's ambiguous
                continue
            else:
                # Neither is a known browser — not a browser-preference correction
                continue

            return CorrectionResult(
                is_correction=True,
                concept="browser",
                old_value=target,
                new_value=browser,
                explanation=f"Browser preference: {target} → {browser}",
                correction_type="browser_preference",
                target=target,
                preferred_container=browser,
                # Embed scope hint in explanation so caller can extract it
            )

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _infer_concept(self, old_val: str, new_val: str) -> str:
        players = {"vlc", "windows media player", "mpv", "kmplayer"}

        if old_val.lower() in _BROWSERS or new_val.lower() in _BROWSERS:
            return "browser"
        if old_val.lower() in players or new_val.lower() in players:
            return "movie"

        all_vocab = self.vocabulary.get_all_vocabulary()
        for k, v in all_vocab.items():
            if v.lower() == old_val.lower():
                return k

        return old_val.lower()
