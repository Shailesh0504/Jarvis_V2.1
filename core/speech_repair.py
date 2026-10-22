# core/speech_repair.py
"""
ASR Misrecognition Recovery & Speech Repair Engine for Jarvis V2.1.

Recovers from common ASR/STT phonetic misrecognitions before intent detection,
entity extraction, and visual text search.

Pipeline Position:
Speech -> STT -> Raw Transcript -> Speech Repair -> Normalized Transcript ->
Intent Detection -> Entity/Reference Extraction -> Context Resolution -> Action
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.core.speech_repair")


@dataclass
class SuspiciousToken:
    """Represents a token identified as potential ASR misrecognition."""
    token: str
    index: int
    reason: str
    suggested_replacements: List[str]
    confidence: float = 0.85


@dataclass
class CandidateScore:
    text: str
    confidence: float
    repaired: bool = False
    reason: str = ""


@dataclass
class RepairResult:
    """Result of ASR transcript evaluation and speech repair."""
    raw_text: str
    final_text: str
    repaired: bool
    reason: str = "none"
    confidence: float = 1.0
    candidates_evaluated: List[Tuple[str, float]] = field(default_factory=list)

    @property
    def original_text(self) -> str:
        return self.raw_text

    @property
    def candidates(self) -> List[CandidateScore]:
        return [
            CandidateScore(text=c[0], confidence=c[1], repaired=(c[0] != self.raw_text))
            for c in self.candidates_evaluated
        ]


class SuspiciousTokenDetector:
    """
    Detects tokens that are grammatically unnatural or likely ASR distortions.
    Strictly preserves grammatically valid instrumental postpositions (e.g. 'mouse se click karo').
    """

    # Objects commonly targeted in desktop window/app commands
    TARGET_OBJECTS = {
        "window", "app", "application", "browser", "tab", "screen",
        "page", "file", "folder", "document", "sheet", "program", "software"
    }

    # Action verbs in English and Hinglish
    ACTION_VERBS = {
        "close", "band", "minimize", "maximize", "restore", "kholo",
        "open", "chalao", "start", "focus", "hatao", "saaf", "delete"
    }

    # Common instruments where 'se' is a grammatically valid postposition
    INSTRUMENT_NOUNS = {
        "mouse", "keyboard", "touchpad", "cursor", "mic", "microphone",
        "link", "button", "shortcut", "command", "browser", "app", "file"
    }

    @classmethod
    def detect(cls, text: str) -> List[SuspiciousToken]:
        tokens = text.strip().split()
        if not tokens:
            return []

        suspicious: List[SuspiciousToken] = []
        lowered_tokens = [t.lower().rstrip(".,?!") for t in tokens]

        for i, tok in enumerate(lowered_tokens):
            # 1. Leading "se" or "sae" before target object: e.g. "se window ko close karo"
            if tok in ("se", "sae") and i == 0 and len(lowered_tokens) > 1:
                next_tok = lowered_tokens[i + 1]
                if next_tok in cls.TARGET_OBJECTS:
                    suspicious.append(SuspiciousToken(
                        token=tokens[i],
                        index=i,
                        reason="demonstrative_distorted_before_object",
                        suggested_replacements=["is", "iss", "ye", "this"],
                        confidence=0.92
                    ))
                elif next_tok in cls.ACTION_VERBS or (len(lowered_tokens) > 2 and lowered_tokens[i + 1] == "ko"):
                    suspicious.append(SuspiciousToken(
                        token=tokens[i],
                        index=i,
                        reason="demonstrative_distorted_before_action",
                        suggested_replacements=["isse", "ise", "isko", "ye"],
                        confidence=0.90
                    ))

            # 2. Non-leading "se" right before target object without preceding instrument:
            # e.g. "bhai se window close karo"
            elif tok in ("se", "sae") and i > 0 and (i + 1) < len(lowered_tokens):
                prev_tok = lowered_tokens[i - 1]
                next_tok = lowered_tokens[i + 1]

                # If preceded by an instrument (e.g. "mouse se click karo"), DO NOT flag. Valid postposition!
                if prev_tok in cls.INSTRUMENT_NOUNS:
                    continue

                # If preceded by conversational filler like "bhai", "yaar", "jarvis", "please"
                # and followed by an object, it's a distorted demonstrative
                if prev_tok in ("bhai", "yaar", "jarvis", "please", "ab", "sun") and next_tok in cls.TARGET_OBJECTS:
                    suspicious.append(SuspiciousToken(
                        token=tokens[i],
                        index=i,
                        reason="demonstrative_distorted_after_filler",
                        suggested_replacements=["is", "iss", "ye", "this"],
                        confidence=0.90
                    ))

            # 3. Common phonetic misrecognitions (e.g. "new batao" -> "news batao", "gane chalao" -> "gaana chalao")
            if tok == "new" and (i + 1) < len(lowered_tokens) and lowered_tokens[i + 1] in ("batao", "sunao", "dikhao", "padho", "kya", "update"):
                suspicious.append(SuspiciousToken(
                    token=tokens[i],
                    index=i,
                    reason="news_phonetic_truncation",
                    suggested_replacements=["news"],
                    confidence=0.95
                ))
            elif tok in ("gane", "gana", "song") and (i + 1) < len(lowered_tokens) and lowered_tokens[i + 1] in ("chalao", "bajao", "play", "laga", "lagao"):
                suspicious.append(SuspiciousToken(
                    token=tokens[i],
                    index=i,
                    reason="media_phonetic_variant",
                    suggested_replacements=["gaana"],
                    confidence=0.95
                ))

        return suspicious


class PhoneticCandidateGenerator:
    """Generates phonetically similar and common Hinglish ASR alternative sentences."""

    REPLACEMENT_MAP: Dict[str, List[str]] = {
        "se": ["is", "iss", "isse", "ise", "ye", "this"],
        "sae": ["is", "iss", "isse", "ise", "ye", "this"],
        "iss": ["is"],
        "isey": ["ise"],
        "issay": ["isse"],
        "yeh": ["ye"],
    }

    @classmethod
    def generate_candidates(cls, text: str, suspicious_tokens: List[SuspiciousToken]) -> List[str]:
        candidates = [text]
        if not suspicious_tokens:
            return candidates

        words = text.split()
        for st in suspicious_tokens:
            replacements = st.suggested_replacements or cls.REPLACEMENT_MAP.get(st.token.lower(), [])
            for rep in replacements:
                cand_words = list(words)
                cand_words[st.index] = rep
                cand_str = " ".join(cand_words)
                if cand_str not in candidates:
                    candidates.append(cand_str)

        return candidates


class CommandPatternValidator:
    """
    Validates candidate sentences against authoritative Hindi/Hinglish command schemas:
    - [demonstrative] [object] ko [action]
    - [demonstrative] [object] [action]
    - [demonstrative] [action]
    - [instrument] se [action]
    """

    # Valid demonstrative determiners
    DEMONSTRATIVES = {"is", "iss", "ye", "yeh", "this", "that", "current", "active"}
    DEMONSTRATIVE_PRONOUNS = {"isse", "ise", "isey", "isko", "ye", "yeh"}

    # Command schema patterns
    SCHEMA_DEMONSTRATIVE_OBJECT_KO_ACTION = re.compile(
        r"^(?:(?:jarvis|please|bhai|yaar)\s+)?(is|iss|ye|yeh|this)\s+([a-zA-Z]+)\s+ko\s+([a-zA-Z\s]+)$",
        re.IGNORECASE
    )
    SCHEMA_DEMONSTRATIVE_OBJECT_ACTION = re.compile(
        r"^(?:(?:jarvis|please|bhai|yaar)\s+)?(is|iss|ye|yeh|this)\s+([a-zA-Z]+)\s+([a-zA-Z\s]+)$",
        re.IGNORECASE
    )
    SCHEMA_DEMONSTRATIVE_PRONOUN_ACTION = re.compile(
        r"^(?:(?:jarvis|please|bhai|yaar)\s+)?(isse|ise|isey|isko)\s+([a-zA-Z\s]+)$",
        re.IGNORECASE
    )
    SCHEMA_INSTRUMENT_SE_ACTION = re.compile(
        r"^(?:(?:jarvis|please|bhai|yaar)\s+)?([a-zA-Z]+)\s+se\s+([a-zA-Z\s]+)$",
        re.IGNORECASE
    )

    @classmethod
    def match_schema(cls, sentence: str) -> Tuple[bool, str, float]:
        cleaned = sentence.strip().lower()

        # Check Schema 1: [demonstrative] [object] ko [action]
        m1 = cls.SCHEMA_DEMONSTRATIVE_OBJECT_KO_ACTION.match(cleaned)
        if m1:
            dem, obj, act = m1.groups()
            if obj in SuspiciousTokenDetector.TARGET_OBJECTS:
                return True, "demonstrative_object_ko_action", 1.0
            return True, "demonstrative_general_ko_action", 0.85

        # Check Schema 2: [demonstrative] [object] [action]
        m2 = cls.SCHEMA_DEMONSTRATIVE_OBJECT_ACTION.match(cleaned)
        if m2:
            dem, obj, act = m2.groups()
            if obj in SuspiciousTokenDetector.TARGET_OBJECTS:
                return True, "demonstrative_object_action", 0.95
            return True, "demonstrative_general_action", 0.80

        # Check Schema 3: [demonstrative_pronoun] [action] (e.g. "isse close karo")
        m3 = cls.SCHEMA_DEMONSTRATIVE_PRONOUN_ACTION.match(cleaned)
        if m3:
            return True, "demonstrative_pronoun_action", 0.95

        # Check Schema 4: [instrument] se [action] (e.g. "mouse se click karo")
        m4 = cls.SCHEMA_INSTRUMENT_SE_ACTION.match(cleaned)
        if m4:
            inst, act = m4.groups()
            if inst in SuspiciousTokenDetector.INSTRUMENT_NOUNS:
                return True, "instrument_se_action", 1.0
            return True, "general_se_action", 0.70

        return False, "no_schema_match", 0.30


class SpeechRepairEngine:
    """
    Authoritative Speech Repair & ASR Misrecognition Recovery Engine.
    Singleton service implementing context-aware repair, N-best hypothesis ranking,
    and structured audit logging.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.last_repair: Optional[RepairResult] = None

    @classmethod
    def get_instance(cls) -> "SpeechRepairEngine":
        if not cls._instance:
            cls._instance = SpeechRepairEngine()
        return cls._instance

    def generate_candidates(self, text: str) -> List[str]:
        """Generates candidate sentences for an input transcript."""
        suspicious = SuspiciousTokenDetector.detect(text)
        return PhoneticCandidateGenerator.generate_candidates(text, suspicious)

    def detect_suspicious_tokens(self, text: str) -> List[SuspiciousToken]:
        """Detects suspicious tokens in an input transcript."""
        return SuspiciousTokenDetector.detect(text)

    def score_candidate(self, candidate: str, context: Optional[Any] = None) -> float:
        """
        Scores a candidate sentence based on grammar validity, schema fit,
        intent compatibility, and desktop context.
        """
        fits_schema, schema_name, schema_weight = CommandPatternValidator.match_schema(candidate)

        # Base grammar score
        score = 0.5
        if fits_schema:
            score = 0.85 * schema_weight
        else:
            # Check if sentence has valid postposition like "mouse se click karo"
            tokens = candidate.lower().split()
            if "se" in tokens and tokens[0] == "se" and len(tokens) > 1 and tokens[1] in SuspiciousTokenDetector.TARGET_OBJECTS:
                # "se window" is ungrammatical as demonstrative
                score = 0.20
            else:
                score = 0.50

        cand_low = candidate.lower()
        if any(w in cand_low for w in ("news", "samachar", "khabar", "gaana", "gana", "song", "weather", "mausam")):
            score = max(score, 0.80)

        # Contextual boost: if candidate targets active window and context has a foreground window
        if context is not None:
            fg_app = getattr(context, "current_app", None) or getattr(context, "current_target", None)
            if any(w in cand_low for w in ("is window", "iss window", "this window", "ye window", "isse", "ise")) and fg_app:
                score = min(1.0, score + 0.10)

        return round(score, 3)

    @classmethod
    def _repair_conversational_self_correction(cls, text: str) -> Tuple[str, bool, str]:
        """
        Detects and repairs intra-utterance self-corrections, false starts,
        negation-contrast, and mid-speech aborts in human conversation.

        Examples:
        - "Rahul ko... nahi Rohit ko message bhejo" -> "Rohit ko message bhejo"
        - "Chrome mat kholo, Brave kholo" -> "Brave kholo"
        - "5 baje meeting rakho... sorry 6 baje" -> "6 baje meeting rakho"
        - "Pune ka weather batao... sorry Mumbai ka" -> "Mumbai ka weather batao"
        - "Volume 50 karo... actually 30" -> "Volume 30 karo"
        - "Folder delete karo... are nahi cancel" -> "cancel"
        """
        raw = text.strip()
        if not raw:
            return raw, False, "none"

        # 1. Pattern A: Negation contrast ("<Entity> mat <Action>, <NewEntity> <Action>")
        m_neg = re.match(
            r"^(?P<negated>.+?)\s+mat\s+(?P<verb>[a-zA-Z\u0900-\u097F]+(?:\s+karo|\s+kar\s+do|\s+kijiye|\s+kholo|\s+chalao|\s+bhejo|\s+lagao)?)[,.\s]+(?:balki\s+|par\s+|lekin\s+)?(?P<replacement>[^,.]+.*)$",
            raw,
            flags=re.IGNORECASE
        )
        if m_neg:
            negated = m_neg.group("negated").strip()
            verb = m_neg.group("verb").strip()
            replacement = m_neg.group("replacement").strip()
            if replacement and negated:
                # Whole-word match only: "karna" must NOT count as action word "kar",
                # else a bare prohibition ("Baaki kuch mat band karna", replacement="karna")
                # is mangled into "karna". Without a real replacement action, this is
                # NOT a contrast — leave the prohibition intact for negation handling.
                action_words = ("kholo", "open", "chalao", "play", "karo", "bhejo", "send", "lagao", "set", "band", "close")
                has_action = any(re.search(rf"\b{re.escape(w)}\b", replacement.lower()) for w in action_words)
                if not has_action:
                    # Bare prohibition tail, not a replacement entity
                    # ("Baaki kuch mat band karna" -> replacement "karna"):
                    # leave intact for negation handling downstream.
                    _tail = re.sub(r"[?!.,;]+$", "", replacement.lower()).strip()
                    if _tail in ("karna", "karna hai", "kar", "karo", "hona", "hona hai", "honA".lower(), "hai", "hoga", verb.lower()):
                        return raw, False, "none"
                    repaired = f"{replacement} {verb}".strip()
                else:
                    repaired = replacement
                return repaired, True, "negation_contrast"

        # 2. Pattern B: Pivot markers for mid-utterance self-correction & aborts
        # Note: Bare 'nahi'/'nahin' with only whitespace represents grammatical negation
        # ("lock kyun nahi ho raha", "chrome nahi khul raha"), so bare 'nahi' strictly requires
        # punctuation (ellipsis '...' or comma ',') or compound pivot ('nahi nahi', 'arrey nahi', 'sorry', 'actually', 'ruko', 'wait').
        if re.search(r"\b(?:kyun|kyu|kya)\s+nahi\b|\bnahi\s+(?:ho\s+raha|chal\s+raha|mil\s+raha|khul\s+raha|hua|tha|hai|hoga)\b", raw, re.IGNORECASE):
            pivot_pattern = re.compile(
                r"(?:\.{2,}|[,;])\s*(?P<pivot>arrey\s+nahi|arey\s+nahi|are\s+nahi|are\s+yaar\s+nahi|nahi\s+nahi|nahi|nahin|sorry|actually|ruko|wait)\s*[,;.]*\s*",
                flags=re.IGNORECASE
            )
        else:
            pivot_pattern = re.compile(
                r"(?:\.{2,}|[,;]|\s)\s*(?P<pivot>arrey\s+nahi|arey\s+nahi|are\s+nahi|are\s+yaar\s+nahi|nahi\s+nahi|sorry|actually|ruko|wait)\s*[,;.]*\s*|(?:\.{2,}|[,;])\s*(?P<pivot_bare>nahi|nahin)\s*[,;.]*\s*",
                flags=re.IGNORECASE
            )
        match = pivot_pattern.search(raw)
        if match:
            before = raw[:match.start()].strip()
            after = raw[match.end():].strip()
            if before and after:
                # Sub-case B1: Mid-utterance cancellation / abort ("... are nahi cancel", "... nahi mat karo")
                abort_words = ("cancel", "mat karo", "rehne do", "chhoro", "choro", "ruk jao", "stop", "abort")
                if any(w in after.lower() for w in abort_words) or after.lower() in ("no", "nahi", "nahin"):
                    return "cancel", True, "mid_utterance_cancellation"

                # Sub-case B2: If before does not contain an action verb and after does
                action_verbs = ("kholo", "open", "chalao", "play", "bhejo", "send", "karo", "kar", "do", "rakho", "set", "call", "delete", "close", "band", "batao", "dikhao", "sunao", "lagao")
                before_has_verb = any(re.search(rf"\b{re.escape(v)}\b", before, re.IGNORECASE) for v in action_verbs)
                after_has_verb = any(re.search(rf"\b{re.escape(v)}\b", after, re.IGNORECASE) for v in action_verbs)

                if not before_has_verb and after_has_verb:
                    return after, True, "mid_utterance_restart"

                # Sub-case B3: before has full predicate, after is replacement slot
                # Check 1: Postposition replacement ("ko", "ka", "ki", "ke", "mein", "se")
                m_post = re.search(r"\b([\w\u0900-\u097F]+)\s+(ko|ka|ki|ke|mein|me|se)\b", after, re.IGNORECASE)
                if m_post:
                    new_arg = m_post.group(0)
                    post = m_post.group(2)
                    m_orig = re.search(rf"\b([\w\u0900-\u097F]+)\s+{re.escape(post)}\b", before, re.IGNORECASE)
                    if m_orig:
                        orig_arg = m_orig.group(0)
                        repaired = before.replace(orig_arg, new_arg, 1)
                        return repaired, True, "slot_self_correction"

                # Check 2: Time replacement (e.g. "6 baje" replacing "5 baje")
                m_time = re.search(r"\b(\d+)\s*(baje|am|pm)\b", after, re.IGNORECASE)
                if m_time:
                    new_time = m_time.group(0)
                    m_orig_time = re.search(r"\b(\d+)\s*(baje|am|pm)\b", before, re.IGNORECASE)
                    if m_orig_time:
                        repaired = before.replace(m_orig_time.group(0), new_time, 1)
                        return repaired, True, "time_self_correction"

                # Check 3: Numeric replacement (e.g. "30" replacing "50" in "Volume 50 karo")
                m_num_after = re.search(r"\b(\d+)\b", after)
                m_num_before = re.search(r"\b(\d+)\b", before)
                if m_num_after and m_num_before:
                    repaired = before.replace(m_num_before.group(1), m_num_after.group(1), 1)
                    return repaired, True, "number_self_correction"

                # Check 4: Single token / entity substitution
                if after_has_verb:
                    return after, True, "clause_self_correction"
                else:
                    before_tokens = before.split()
                    if len(before_tokens) >= 2:
                        repaired = f"{after} " + " ".join(before_tokens[1:])
                        return repaired, True, "entity_self_correction"

        return raw, False, "none"

    def repair_transcript(
        self,
        text: str,
        context: Optional[Any] = None,
        n_best: Optional[List[Tuple[str, float]]] = None
    ) -> RepairResult:
        """
        Authoritative entry point for ASR speech repair.
        Evaluates raw input, suspicious tokens, candidate alternatives, and optional N-best STT.
        Returns RepairResult with final repaired text and structured metrics.
        """
        raw_text = (text or "").strip()
        if not raw_text:
            return RepairResult(raw_text="", final_text="", repaired=False)

        # 0. Intra-utterance self-repair (mid-speech corrections, false starts, negation-contrast)
        corrected_text, is_self_repaired, repair_reason = self._repair_conversational_self_correction(raw_text)
        if is_self_repaired:
            logger.info(
                f"[SPEECH_REPAIR_SELF_CORRECTION] RAW='{raw_text}' -> REPAIRED='{corrected_text}' "
                f"REASON='{repair_reason}'"
            )
            result = RepairResult(
                raw_text=raw_text,
                final_text=corrected_text,
                repaired=True,
                reason=repair_reason,
                confidence=0.98,
                candidates_evaluated=[(corrected_text, 0.98), (raw_text, 0.50)]
            )
            self.last_repair = result
            return result

        suspicious = SuspiciousTokenDetector.detect(raw_text)

        # Collect all candidates to evaluate
        candidates_to_score: Dict[str, float] = {}

        # 1. Include generated candidates from suspicious tokens
        cand_list = PhoneticCandidateGenerator.generate_candidates(raw_text, suspicious)
        for cand in cand_list:
            candidates_to_score[cand] = 0.0

        # 2. Include N-best hypotheses if provided
        if n_best:
            for hyp_text, hyp_conf in n_best:
                hyp_clean = hyp_text.strip()
                if hyp_clean:
                    # Also generate repairs on N-best hypotheses
                    hyp_susp = SuspiciousTokenDetector.detect(hyp_clean)
                    hyp_repairs = PhoneticCandidateGenerator.generate_candidates(hyp_clean, hyp_susp)
                    for hr in hyp_repairs:
                        candidates_to_score[hr] = max(candidates_to_score.get(hr, 0.0), hyp_conf * 0.3)

        # Score all candidates
        scored_candidates: List[Tuple[str, float]] = []
        for cand in candidates_to_score:
            base_score = self.score_candidate(cand, context=context)
            # Add bonus from N-best if applicable
            prior_bonus = candidates_to_score[cand]
            total_score = min(1.0, base_score + prior_bonus)
            scored_candidates.append((cand, total_score))

        # Sort candidates by score descending
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        best_cand, best_score = scored_candidates[0]
        raw_score = self.score_candidate(raw_text, context=context)

        # Decide whether to repair
        # Repair if best candidate is different from raw_text and has noticeably higher score
        repaired = False
        final_text = raw_text
        reason = "none"
        confidence = raw_score

        if best_cand != raw_text and (best_score - raw_score) >= 0.15:
            repaired = True
            final_text = best_cand
            confidence = best_score
            reason = "demonstrative/object command pattern"
            logger.info(
                f"[SPEECH_REPAIR] RAW_STT='{raw_text}' -> REPAIR_CANDIDATE='{best_cand}' "
                f"REASON='{reason}' CONFIDENCE={confidence:.2f} FINAL='{final_text}'"
            )
        else:
            final_text = raw_text
            confidence = raw_score
            logger.debug(f"[SPEECH_REPAIR] Preserving raw transcript: '{raw_text}' (conf={confidence:.2f})")

        result = RepairResult(
            raw_text=raw_text,
            final_text=final_text,
            repaired=repaired,
            reason=reason,
            confidence=confidence,
            candidates_evaluated=scored_candidates
        )
        self.last_repair = result
        return result

    def get_repair_reason(self) -> str:
        """Returns the reason for the last speech repair operation."""
        return self.last_repair.reason if self.last_repair else "none"


def get_speech_repair_engine() -> SpeechRepairEngine:
    """Returns singleton instance of SpeechRepairEngine."""
    return SpeechRepairEngine.get_instance()
