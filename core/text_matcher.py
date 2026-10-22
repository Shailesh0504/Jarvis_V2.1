# core/text_matcher.py
"""
Unicode-Aware, Case-Insensitive, Whitespace-Normalized, Multi-Word Phrase & Fuzzy Text Matcher.

Enforces:
1. Case-Insensitive Matching with Unicode NFKC & casefold().
2. Whitespace Normalization (collapsing arbitrary spaces, tabs, newlines).
3. Punctuation Tolerance (ignoring peripheral punctuation e.g. 'Paramhans Aashram.', 'Rahul?').
4. Cross-Script Hindi/English Matching integration.
5. Multi-Word Spatial Phrase Matching: Merging adjacent OCR tokens into single phrase bounding boxes.
6. OCR Fault Tolerance & Fuzzy Matching.
"""

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

from core.cross_script_matcher import get_cross_script_matcher


@dataclass
class BoundingBox:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def center_x(self) -> int:
        return self.left + self.width // 2

    @property
    def center_y(self) -> int:
        return self.top + self.height // 2

    def to_dict(self) -> Dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
            "center_x": self.center_x,
            "center_y": self.center_y
        }


@dataclass
class OCRToken:
    text: str
    bbox: BoundingBox
    confidence: float = 1.0
    line_num: int = 0
    word_num: int = 0


@dataclass
class VisualTextMatch:
    text: str                  # Query target
    matched_text: str          # Text found on screen / in element
    confidence: float          # OCR / source detection confidence
    match_score: float         # String similarity / match score (0.0 to 1.0)
    match_type: str            # 'exact', 'casefold', 'cross_script_exact', 'cross_script_fuzzy', 'spatial_phrase', 'fuzzy'
    bbox: BoundingBox          # Screen bounding box
    window_title: str = ""     # Target window title
    process_name: str = ""     # Target process
    strategy: str = "ocr"      # 'uia', 'dom', 'ocr', 'winocr'
    hitbox: Optional[BoundingBox] = None  # Accessible button/link hitbox if available


class TextMatcher:
    """Authoritative text matching engine with multi-strategy scoring."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.cross_script = get_cross_script_matcher()

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalizes repeated spaces, tabs, and line breaks into single space."""
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def strip_peripheral_punctuation(text: str) -> str:
        """Removes peripheral non-essential punctuation while preserving alphanumeric tokens."""
        if not text:
            return ""
        # Strip leading and trailing punctuation (.,!?:;'"()[]{})
        s = text.strip()
        s = re.sub(r"^[\s.,!?:;'\"()\[\]{}]+|[\s.,!?:;'\"()\[\]{}]+$", "", s)
        return s

    @staticmethod
    def unicode_casefold(text: str) -> str:
        """Performs full Unicode NFKC normalization and casefold()."""
        if not text:
            return ""
        return unicodedata.normalize('NFKC', text).casefold()

    def compare_strings(self, query: str, candidate: str) -> Tuple[float, str]:
        """
        Compares query string against candidate text.
        Returns: (match_score, match_type).
        """
        if not query or not candidate:
            return 0.0, "none"

        q_clean = self.strip_peripheral_punctuation(self.normalize_whitespace(query))
        c_clean = self.strip_peripheral_punctuation(self.normalize_whitespace(candidate))

        if not q_clean or not c_clean:
            return 0.0, "none"

        # 1. Exact string match
        if q_clean == c_clean:
            return 1.0, "exact"

        # 2. Unicode NFKC + Casefold match
        q_fold = self.unicode_casefold(q_clean)
        c_fold = self.unicode_casefold(c_clean)

        if q_fold == c_fold:
            return 0.99, "casefold"

        # 3. Cross-script Hindi <-> English match
        cs_score, cs_type = self.cross_script.score(q_clean, c_clean)
        if cs_score >= 0.85:
            return cs_score, cs_type

        # 4. Phrase containment (Exact or Casefold)
        if len(q_fold) >= 3 and len(c_fold) >= 3:
            if q_fold in c_fold or c_fold in q_fold:
                # Substring containment ratio
                coverage = min(len(q_fold), len(c_fold)) / max(len(q_fold), len(c_fold))
                score = round(0.92 + coverage * 0.06, 3)
                return score, "containment"

        # 5. Token-based word order match (all query words present in candidate)
        q_words = [w for w in re.findall(r'\w+', q_fold) if w]
        c_words = [w for w in re.findall(r'\w+', c_fold) if w]

        if q_words and c_words and len(q_words) > 1:
            matched_count = 0
            for qw in q_words:
                if any(qw == cw or (HAS_RAPIDFUZZ and fuzz.ratio(qw, cw) >= 80) for cw in c_words):
                    matched_count += 1
            if matched_count == len(q_words):
                return 0.94, "token_match"

        # 6. Fuzzy similarity via RapidFuzz
        if HAS_RAPIDFUZZ:
            ratio = fuzz.ratio(q_fold, c_fold) / 100.0
            if ratio >= 0.80:
                return round(ratio * 0.90, 3), "fuzzy"

        return 0.0, "none"

    def match_spatial_tokens(
        self,
        query: str,
        tokens: List[OCRToken],
        max_line_dist: int = 25,
        max_word_dist: int = 150
    ) -> List[VisualTextMatch]:
        """
        Spatially groups adjacent OCR tokens into single multi-word phrase bounding boxes.
        Finds exact, casefold, cross-script, or fuzzy matches for the query.
        """
        if not query or not tokens:
            return []

        q_clean = self.strip_peripheral_punctuation(self.normalize_whitespace(query))
        q_fold = self.unicode_casefold(q_clean)
        q_words = [w for w in q_clean.split() if w]
        n_q = len(q_words)

        results: List[VisualTextMatch] = []

        # 1. Single Token Evaluation
        for tok in tokens:
            score, m_type = self.compare_strings(q_clean, tok.text)
            if score >= 0.78:
                results.append(VisualTextMatch(
                    text=q_clean,
                    matched_text=tok.text,
                    confidence=tok.confidence,
                    match_score=score,
                    match_type=m_type,
                    bbox=tok.bbox,
                    strategy="ocr"
                ))

        # 2. Multi-Word Spatial Window Search (for phrases of 2 to 6 words)
        # Groups tokens appearing in visual proximity horizontally on the same line
        if n_q > 1:
            n_tokens = len(tokens)
            # Window sizes around the query word count
            for w_size in range(max(2, n_q - 1), min(n_tokens + 1, n_q + 3)):
                for i in range(n_tokens - w_size + 1):
                    window = tokens[i:i + w_size]

                    # Verify tokens are on roughly the same horizontal line and ordered left-to-right
                    is_same_line = True
                    for j in range(len(window) - 1):
                        curr_box = window[j].bbox
                        next_box = window[j + 1].bbox

                        # Vertical alignment: vertical centers should be close
                        y_diff = abs(curr_box.center_y - next_box.center_y)
                        # Horizontal spacing: next box should start to the right of current box
                        x_gap = next_box.left - curr_box.right

                        if y_diff > max_line_dist or x_gap < -20 or x_gap > max_word_dist:
                            is_same_line = False
                            break

                    if not is_same_line:
                        continue

                    # Construct combined text and bounding box
                    combined_text = " ".join(t.text for t in window)
                    min_left = min(t.bbox.left for t in window)
                    min_top = min(t.bbox.top for t in window)
                    max_right = max(t.bbox.right for t in window)
                    max_bottom = max(t.bbox.bottom for t in window)
                    combined_bbox = BoundingBox(min_left, min_top, max_right, max_bottom)

                    avg_conf = sum(t.confidence for t in window) / len(window)

                    score, m_type = self.compare_strings(q_clean, combined_text)
                    if score >= 0.80:
                        results.append(VisualTextMatch(
                            text=q_clean,
                            matched_text=combined_text,
                            confidence=avg_conf,
                            match_score=score,
                            match_type=f"spatial_{m_type}",
                            bbox=combined_bbox,
                            strategy="ocr"
                        ))

        # Deduplicate matches with overlapping bounding boxes, keeping highest match score
        deduped: List[VisualTextMatch] = []
        for match in sorted(results, key=lambda m: (m.match_score, m.confidence), reverse=True):
            overlaps = False
            for kept in deduped:
                # Check bounding box IoU / center proximity
                dx = abs(match.bbox.center_x - kept.bbox.center_x)
                dy = abs(match.bbox.center_y - kept.bbox.center_y)
                if dx < 30 and dy < 20:
                    overlaps = True
                    break
            if not overlaps:
                deduped.append(match)

        return deduped


_text_matcher_instance: Optional[TextMatcher] = None


def get_text_matcher() -> TextMatcher:
    """Returns singleton instance of TextMatcher."""
    global _text_matcher_instance
    if _text_matcher_instance is None:
        _text_matcher_instance = TextMatcher()
    return _text_matcher_instance
