# core/cross_script_matcher.py
"""
Cross-Script & Devanagari-English Phonetic Matcher.

Enables bidirectional matching between Hindi (Devanagari script) and English (Latin script):
1. English utterance -> Devanagari screen text:
   User: "Paramhans aashram kahan likha hai" -> Screen: "परमहंस आश्रम" (High match score)
2. Devanagari utterance -> English screen text:
   User: "परमहंस आश्रम पर क्लिक करो" -> Screen: "PARAMHANS AASHRAM" (High match score)
3. Devanagari utterance -> Devanagari screen text:
   User: "परमहंस आश्रम कहाँ लिखा है" -> Screen: "परमहंस आश्रम" (Exact match)
4. Phonetic & Transliteration Normalization:
   Handles spelling variations (aashram/ashram, paramhans/paramhansa, v/w, sh/s, ee/i, oo/u).
"""

from dataclasses import dataclass
import re
import unicodedata
from typing import List, Optional, Set, Tuple

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


# Devanagari Unicode Block: U+0900 to U+097F
DEVANAGARI_RANGE = re.compile(r'[\u0900-\u097F]')


# Consonants mapping Devanagari to Latin phonetics
DEVA_TO_LATIN_CONSONANTS = {
    'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng',
    'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'ny',
    'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
    'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
    'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm',
    'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v',
    'श': 'sh', 'ष': 'sh', 'स': 's', 'ह': 'h',
    'क्ष': 'ksh', 'त्र': 'tr', 'ज्ञ': 'gy',
    'क़': 'q', 'ख़': 'kh', 'ग़': 'gh', 'ज़': 'z', 'फ़': 'f', 'ड़': 'd', 'ढ़': 'dh'
}

# Vowels mapping Devanagari to Latin phonetics
DEVA_TO_LATIN_VOWELS = {
    'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo',
    'ऋ': 'ri', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au'
}

# Matras (dependent vowel signs) mapping to Latin phonetics
DEVA_TO_LATIN_MATRAS = {
    'ा': 'aa', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo',
    'ृ': 'ri', 'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au',
    'ॉ': 'o', 'ॅ': 'e'
}

# Special marks
VIRAMA = '्'  # Halant
ANUSVARA = 'ं' # Nasal dot
CHANDRABINDU = 'ँ'
VISARGA = 'ः'
NUKTA = '़'


def is_devanagari(text: str) -> bool:
    """Returns True if the text contains any Devanagari characters."""
    return bool(DEVANAGARI_RANGE.search(text))


def devanagari_to_latin(text: str) -> str:
    """
    Transliterates Devanagari text to Latin phonetic representation.
    Handles inherent 'a' vowels, matras, halant, anusvara, and nukta.
    e.g. 'परमहंस आश्रम' -> 'paramhans aashram'
    """
    if not text:
        return ""

    # Normalize unicode (NFC)
    normalized = unicodedata.normalize('NFC', text)
    result = []
    i = 0
    n = len(normalized)

    while i < n:
        char = normalized[i]

        # Check special marks
        if char == ANUSVARA or char == CHANDRABINDU:
            # Nasal sound 'n' or 'm' (before p/b/m usually 'm', otherwise 'n')
            result.append('n')
            i += 1
            continue
        elif char == VISARGA:
            result.append('h')
            i += 1
            continue
        elif char == VIRAMA:
            # Halant suppresses previous inherent vowel
            i += 1
            continue

        # Independent vowels
        if char in DEVA_TO_LATIN_VOWELS:
            result.append(DEVA_TO_LATIN_VOWELS[char])
            i += 1
            continue

        # Consonants
        if char in DEVA_TO_LATIN_CONSONANTS:
            # Check for nukta on next char
            has_nukta = (i + 1 < n and normalized[i + 1] == NUKTA)
            base_char = normalized[i:i + 2] if has_nukta else char
            c_trans = DEVA_TO_LATIN_CONSONANTS.get(base_char, DEVA_TO_LATIN_CONSONANTS.get(char, ''))
            result.append(c_trans)
            i += (2 if has_nukta else 1)

            # Check what follows: virama, matra, anusvara, or another consonant/whitespace/end
            if i < n:
                next_char = normalized[i]
                if next_char == VIRAMA:
                    # Halant: no inherent vowel
                    i += 1
                elif next_char == ANUSVARA or next_char == CHANDRABINDU:
                    # Inherent 'a' is nasalized by anusvara -> 'an'
                    result.append('an')
                    i += 1
                elif next_char in DEVA_TO_LATIN_MATRAS:
                    result.append(DEVA_TO_LATIN_MATRAS[next_char])
                    i += 1
                elif next_char in (' ', '\t', '\n', '.', ',', '!', '?', '-', '_', ':', ';', "'", '"'):
                    # Word-final consonant in modern Hindi typically drops inherent schwa
                    pass
                elif next_char in DEVA_TO_LATIN_CONSONANTS or next_char in DEVA_TO_LATIN_VOWELS:
                    # Internal consonant without matra or virama has inherent 'a'
                    result.append('a')
            continue

        # Whitespace, punctuation, Latin letters, numbers, etc.
        result.append(char)
        i += 1

    return "".join(result)


def canonicalize_phonetic(text: str) -> str:
    """
    Produces a normalized canonical phonetic representation for both Latin and Devanagari text.
    Allows exact phonetic comparison across scripts and spelling variations:
    - Normalizes long vs short vowels (aa -> a, ee -> i, oo -> u)
    - Normalizes sibilants (sh/s/shh -> s)
    - Normalizes labials (w -> v)
    - Normalizes aspirates (ph -> f, kh -> k in fuzzy contexts)
    - Collapses repeated adjacent identical characters
    e.g.:
      'Paramhans Aashram' -> 'paramhans asram'
      'परमहंस आश्रम' -> 'paramhans asram'
    """
    if not text:
        return ""

    # If Devanagari, first transliterate to Latin
    s = devanagari_to_latin(text) if is_devanagari(text) else text

    # NFKC Unicode normalization & lowercase
    s = unicodedata.normalize('NFKC', s).casefold()

    # Replace punctuation with spaces
    s = re.sub(r'[^a-z0-9\s]', ' ', s)

    # Phonetic normalization rules
    s = re.sub(r'aa+', 'a', s)
    s = re.sub(r'ee+', 'i', s)
    s = re.sub(r'oo+', 'u', s)
    s = re.sub(r'ou', 'au', s)
    s = re.sub(r'sh+', 's', s)
    s = re.sub(r'w+', 'v', s)
    s = re.sub(r'ph+', 'f', s)
    s = re.sub(r'z+', 'j', s)
    s = re.sub(r'q+', 'k', s)

    # Specific common Hindi word stem normalizations
    # e.g. ashrama -> asram, paramhansa -> paramhans
    s = re.sub(r'\basrama?\b', 'asram', s)
    s = re.sub(r'\baasrama?\b', 'asram', s)
    s = re.sub(r'\bparamhansa?\b', 'paramhans', s)
    s = re.sub(r'\bparamahans\b', 'paramhans', s)

    # English -le / -el endings (e.g. google -> gugal, apple -> apal, table -> tabal)
    s = re.sub(r'([bcdfghjklmnpqrstvwxyz])le\b', r'\1al', s)
    s = re.sub(r'([bcdfghjklmnpqrstvwxyz])el\b', r'\1al', s)

    # Schwa syncope on 3-consonant clusters (e.g. paramahans -> paramhans)
    s = re.sub(r'([bcdfghjklmnprstvwxyz])a([bcdfghjklmnprstvwxyz])a([bcdfghjklmnprstvwxyz])', r'\1a\2\3', s)

    # Collapse repeated whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s


class CrossScriptMatcher:
    """
    Authoritative Cross-Script and Hindi-English Phonetic Matcher.
    Calculates match confidence between user queries and screen texts regardless of script.
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

    def is_cross_script(self, text_a: str, text_b: str) -> bool:
        """Returns True if one text is in Devanagari and the other is in Latin."""
        a_deva = is_devanagari(text_a)
        b_deva = is_devanagari(text_b)
        return a_deva != b_deva

    def score(self, query: str, candidate: str) -> Tuple[float, str]:
        """
        Calculates similarity score (0.0 to 1.0) and identifies match type:
        - 'exact': exact unicode-normalized match
        - 'casefold': casefold match
        - 'cross_script_exact': canonical transliteration matches exactly (score: 0.98 - 1.0)
        - 'cross_script_fuzzy': canonical transliteration matches with minor edit distance (score: 0.85 - 0.95)
        - 'fuzzy': rapidfuzz/token similarity (score: 0.70 - 0.85)
        - 'none': no match (< 0.70)
        """
        if not query or not candidate:
            return 0.0, "none"

        q_clean = query.strip()
        c_clean = candidate.strip()

        # 1. Exact string match
        if q_clean == c_clean:
            return 1.0, "exact"

        # 2. Unicode NFKC + Casefold match
        q_norm = unicodedata.normalize('NFKC', q_clean).casefold()
        c_norm = unicodedata.normalize('NFKC', c_clean).casefold()
        if q_norm == c_norm:
            return 0.99, "casefold"

        # 3. Canonical phonetic transliteration match
        q_canon = canonicalize_phonetic(q_clean)
        c_canon = canonicalize_phonetic(c_clean)

        if q_canon and c_canon:
            if q_canon == c_canon:
                m_type = "cross_script_exact" if self.is_cross_script(q_clean, c_clean) else "phonetic_exact"
                return 0.98, m_type

            # Substring containment in canonical form
            if len(q_canon) >= 4 and len(c_canon) >= 4:
                if q_canon in c_canon or c_canon in q_canon:
                    m_type = "cross_script_containment" if self.is_cross_script(q_clean, c_clean) else "containment"
                    return 0.95, m_type

        # 4. Fuzzy word-by-word and phrase similarity
        q_tokens = [t for t in q_canon.split() if t]
        c_tokens = [t for t in c_canon.split() if t]

        if q_tokens and c_tokens:
            # Check all query tokens are present in candidate
            all_tokens_found = True
            token_scores = []
            for qt in q_tokens:
                best_t_score = 0.0
                for ct in c_tokens:
                    if qt == ct:
                        best_t_score = 1.0
                        break
                    elif HAS_RAPIDFUZZ:
                        sim = fuzz.ratio(qt, ct) / 100.0
                        if sim > best_t_score:
                            best_t_score = sim
                    else:
                        # Simple prefix / substring
                        if qt in ct or ct in qt:
                            best_t_score = max(best_t_score, 0.88)
                token_scores.append(best_t_score)
                if best_t_score < 0.78:
                    all_tokens_found = False

            if all_tokens_found and token_scores:
                avg_token_score = sum(token_scores) / len(token_scores)
                if avg_token_score >= 0.85:
                    m_type = "cross_script_fuzzy" if self.is_cross_script(q_clean, c_clean) else "phonetic_fuzzy"
                    return round(avg_token_score * 0.94, 3), m_type

        # 5. Whole phrase RapidFuzz on canonical form
        if HAS_RAPIDFUZZ and q_canon and c_canon:
            ratio = fuzz.ratio(q_canon, c_canon) / 100.0
            if ratio >= 0.82:
                m_type = "cross_script_fuzzy" if self.is_cross_script(q_clean, c_clean) else "fuzzy"
                return round(ratio * 0.92, 3), m_type

        return 0.0, "none"


_cross_script_matcher_instance: Optional[CrossScriptMatcher] = None


def get_cross_script_matcher() -> CrossScriptMatcher:
    """Returns singleton instance of CrossScriptMatcher."""
    global _cross_script_matcher_instance
    if _cross_script_matcher_instance is None:
        _cross_script_matcher_instance = CrossScriptMatcher()
    return _cross_script_matcher_instance
