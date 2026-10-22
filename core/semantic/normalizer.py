# core/semantic/normalizer.py
"""Hinglish speech-to-text transcription normalizer, query cleaner, and generic typo-tolerant conversational normalizer."""

import re
from typing import List, Dict, Optional, Set, Tuple

# Precompiled patterns for hot-path performance
CONNECTOR_RE = re.compile(r'\b(wala|wali|wale|ka|ki|ke|pe|par|me|mein|in|on)\b', flags=re.IGNORECASE)
WHITESPACE_RE = re.compile(r'\s+')
_TRIPLE_LETTER_RE = re.compile(r'([a-zA-Z])\1{2,}')


def _is_damerau_levenshtein_1(w: str, cand: str) -> bool:
    """
    Returns True if w and cand have edit distance <= 1 under Damerau-Levenshtein
    (supporting single deletion, insertion, substitution, or adjacent transposition).
    """
    len_w, len_c = len(w), len(cand)
    if abs(len_w - len_c) > 1:
        return False
    if w == cand:
        return True

    # Same length: 1 substitution OR 1 adjacent transposition
    if len_w == len_c:
        diffs = [i for i in range(len_w) if w[i] != cand[i]]
        if len(diffs) == 1:
            return True
        if (
            len(diffs) == 2
            and diffs[1] == diffs[0] + 1
            and w[diffs[0]] == cand[diffs[1]]
            and w[diffs[1]] == cand[diffs[0]]
        ):
            return True
        return False

    # Length differs by 1: 1 insertion/deletion
    short, long_ = (w, cand) if len_w < len_c else (cand, w)
    for i in range(len(long_)):
        if long_[:i] + long_[i + 1:] == short:
            return True
    return False


class HinglishNormalizer:
    """
    Authoritative normalizer for conversational shorthand, STT phonetic errors,
    casual SMS abbreviations, fillers, and generic typo-tolerant word resolution.
    """

    FILLERS: List[str] = [
        r'\bbhai\b', r'\byaar\b', r'\bdost\b', r'\bplease\b', r'\bzara\b',
        # NOTE: 'thoda' and 'ek' intentionally removed — they are QUANTITY modifiers
        # (HindiVocabCategory.QUANTITY) and must be preserved for commands like
        # "thoda volume badhao" or "ek reminder set karo".
        r'\bjaldi\b', r'\bjarvis\b', r'\bna\b', r'\btoh\b',
        r'\bdear\b', r'\bsir\b', r'\bbro\b', r'\bbuddy\b', r'\bfriend\b', r'\bji\b'
    ]

    GENERIC_MEDIA_TERMS: List[str] = [
        "gaana", "gana", "song", "songs", "video", "videos", "music", "track"
    ]

    # -------------------------------------------------------------------------
    # 1. Canonical Conversational Shorthand & Slang Expansions
    # -------------------------------------------------------------------------
    COMMON_SHORTHAND: List[Tuple[str, str]] = [
        # Contextual "yu" / "u" / "ur" expansions
        (r'\bwhat\s+is\s+yu\b', 'what is your'),
        (r'\bwhat\s+is\s+u\b', 'what is your'),
        (r'\bwhat\s+is\s+ur\b', 'what is your'),
        (r'\bhow\s+r\s+u\b', 'how are you'),
        (r'\bhw\s+r\s+u\b', 'how are you'),
        (r'\bhw\s+are\s+you\b', 'how are you'),
        (r'\bhw\s+are\s+yu\b', 'how are you'),
        (r'\bwho\s+r\s+u\b', 'who are you'),
        (r'\bwho\s+are\s+u\b', 'who are you'),
        (r'\bwho\s+is\s+u\b', 'who are you'),
        (r'\bwho\s+r\s+you\b', 'who are you'),
        (r'\bu\b', 'you'),
        (r'\bur\b', 'your'),
        (r'\byu\b', 'you'),
        (r'\br\b', 'are'),
        (r'\bwht\b', 'what'),
        (r'\bwat\b', 'what'),
        (r'\bhw\b', 'how'),
        (r'\bplz\b', 'please'),
        (r'\bpls\b', 'please'),
        (r'\bthx\b', 'thanks'),
        (r'\bthanx\b', 'thanks'),
        (r'\bthnx\b', 'thanks'),
        (r'\bty\b', 'thank you'),
        (r'\bsry\b', 'sorry'),
        (r'\bwlcm\b', 'welcome'),

        # Hindi verbal and conversational shorthand
        (r'\bkr\s+(?:rhe|rahe|rha|raha|rhi|rahi|skte|sakte|skta|sakta|skti|sakti|do|de|dena)\b',
         lambda m: 'kar ' + m.group(0).split()[1]),
        (r'\b(?:kya|kaam|help)\s+kr\b', lambda m: m.group(0).split()[0] + ' kar'),
        (r'\bkr\b', 'kar'),
        (r'\bkrr\b', 'kar'),
        (r'\bkro\b', 'karo'),
        (r'\bkroo\b', 'karo'),
        (r'\bkrdo\b', 'kar do'),
        (r'\bkrna\b', 'karna'),
        (r'\bkrne\b', 'karne'),
        (r'\brha\b', 'raha'),
        (r'\brhe\b', 'rahe'),
        (r'\brhi\b', 'rahi'),
        (r'\bskta\b', 'sakta'),
        (r'\bskte\b', 'sakte'),
        (r'\bskti\b', 'sakti'),
        (r'\bbtao\b', 'batao'),
        (r'\bbtaiye\b', 'bataiye'),
        (r'\bbta\b', 'bata'),
        (r'\bkon\b', 'kaun'),
        (r'\bkoun\b', 'kaun'),
        (r'\bkese\b', 'kaise'),
        (r'\bthek\b', 'theek'),
        (r'\bthk\b', 'theek'),
        (r'\bbdia\b', 'badhiya'),
        (r'\bbdiya\b', 'badhiya'),
        (r'\bchahie\b', 'chahiye'),
        (r'\bkyu\b', 'kyun'),
        (r'\bknu\b', 'kyun'),

        # Action verb shorthands
        (r'\bopn\b', 'open'),
        (r'\bclse\b', 'close'),
        (r'\bclos\b', 'close'),
        (r'\bshudown\b', 'shutdown'),
        (r'\bshotdown\b', 'shutdown'),
        (r'\bshutdwn\b', 'shutdown'),
        (r'\brestat\b', 'restart'),
        (r'\brestrat\b', 'restart'),
    ]

    COMMON_CORRECTIONS: Dict[str, str] = {
        # --- STT phonetic typos ---
        r'\bsurur\b': 'surroor',
        r'\bsuror\b': 'surroor',
        r'\bsuroor\b': 'surroor',
        r'\bretstart\b': 'restart',
        r'\brestat\b': 'restart',
        r'\brestard\b': 'restart',
        r'\brebote\b': 'reboot',
        r'\brebot\b': 'reboot',
        r'\bshatdown\b': 'shutdown',
        r'\bsutdown\b': 'shutdown',
        r'\bshutdon\b': 'shutdown',
        r'\bchrom\b': 'chrome',
        r'\bcrome\b': 'chrome',
        r'\bchrme\b': 'chrome',
        r'\bchrrome\b': 'chrome',       # double-letter
        r'\bchorme\b': 'chrome',       # adjacent transposition
        r'\bbraev\b': 'brave',
        r'\btem\b': 'temp',
        r'\bphile\b': 'file',
        r'\bphiles\b': 'files',
        r'\byoutub\b': 'youtube',
        r'\byoutubee\b': 'youtube',
        r'\butube\b': 'youtube',
        r'\bfirfox\b': 'firefox',
        r'\bexcl\b': 'excel',
        r'\bexel\b': 'excel',
        r'\bexcell\b': 'excel',         # double-letter
        r'\bexcells\b': 'excel',
        r'\bnotepd\b': 'notepad',
        r'\bnotpad\b': 'notepad',
        r'\bblutooth\b': 'bluetooth',   # cross-vowel typo (very common STT)
        r'\bblootooth\b': 'bluetooth',
        r'\bbluetoothe\b': 'bluetooth',
        r'\bblutoothe\b': 'bluetooth',
        r'\bwhatsaap\b': 'whatsapp',    # double-letter
        r'\bwatsapp\b': 'whatsapp',
        r'\bwhtsapp\b': 'whatsapp',
        r'\bspotifiy\b': 'spotify',     # extra 'i'
        r'\bspotfy\b': 'spotify',
        r'\bspotyfy\b': 'spotify',
        r'\bcalcuator\b': 'calculator',
        r'\bcalcualtor\b': 'calculator',
        r'\bpowrpoint\b': 'powerpoint',
        r'\bpowerpont\b': 'powerpoint',
        r'\bbrwoser\b': 'browser',
        r'\bbrouser\b': 'browser',
        r'\bbrowzer\b': 'browser',
        r'\bbrower\b': 'browser',
        r'\bbajao\b': 'play',
        # --- Hindi action verb synonyms (HindiVocabCategory.ACTION) ---
        r'\brok\s+do\b': 'stop',
        r'\bbhej\s+do\b': 'send',
        r'\bdikha\s+do\b': 'show',
        r'\bchhupa\s+do\b': 'hide',
        r'\bbol\s+do\b': 'speak',
        r'\blikh\s+do\b': 'write',
        r'\bparh\s+do\b': 'read',
        r'\bhata\s+do\b': 'remove',
        # --- Time reference normalizations ---
        r'\babhi\s+ke\s+liye\b': 'now',
        r'\baaj\s+ka\b': 'today',
        r'\baaj\s+ki\b': 'today',
        # --- Greeting and salutation common typos ---
        r'\bmoring\b': 'morning',
        r'\bmornig\b': 'morning',
        r'\bmornin\b': 'morning',
        r'\bmrng\b': 'morning',
        r'\bgud\b': 'good',
        r'\bgd\b': 'good',
        r'\bgm\b': 'good morning',
        r'\bhelo\b': 'hello',
        r'\bhallo\b': 'hello',
        r'\bhelllo\b': 'hello',
        r'\bhii+\b': 'hi',
        r'\bhie\b': 'hi',
        r'\bevenig\b': 'evening',
        r'\bevenin\b': 'evening',
        r'\baftrnoon\b': 'afternoon',
        r'\bafternon\b': 'afternoon',
        r'\bnite\b': 'night',
        r'\bnyt\b': 'night',
        r'\bsuprabhat\b': 'shubh prabhat',
        r'\bsubh\s+prabhat\b': 'shubh prabhat',
        r'\bsubah\s+bakhair\b': 'subah bakhair',
        # --- Devanagari Hindi transliterated tech & app keywords ---
        r'\byootyoob\b': 'youtube',
        r'\byootoob\b': 'youtube',
        r'\byoutub\b': 'youtube',
        r'\bkrom\b': 'chrome',
        r'\bbrev\b': 'brave',
        r'\bvolyoom\b': 'volume',
        r'\bvaalyoom\b': 'volume',
        r'\bkailakuletar\b': 'calculator',
        r'\bkalkooletar\b': 'calculator',
    }

    _COMPILED_SHORTHAND = [
        (re.compile(pattern, re.IGNORECASE), repl)
        for pattern, repl in COMMON_SHORTHAND
    ]

    _COMPILED_CORRECTIONS: List[Tuple[re.Pattern, str]] = [
        (re.compile(pattern, re.IGNORECASE), repl)
        for pattern, repl in COMMON_CORRECTIONS.items()
    ]

    # Canonical Anchor Vocabulary for generic distance <= 1 typo tolerance
    ANCHOR_WORDS: Set[str] = {
        # Command Verbs
        'open', 'close', 'restart', 'shutdown', 'reboot', 'start', 'stop', 'clean',
        'clear', 'search', 'play', 'mute', 'unmute', 'type', 'click', 'lock',
        # Core Targets / Entities
        'chrome', 'browser', 'youtube', 'calculator', 'notepad', 'excel', 'system',
        'computer', 'laptop', 'window', 'windows', 'desktop', 'whatsapp', 'spotify',
        'camera', 'settings', 'bluetooth', 'wifi', 'volume', 'screen',
        # Conversational Core Words
        'morning', 'evening', 'afternoon', 'night', 'hello', 'thanks', 'welcome',
        'sorry', 'please', 'kaise', 'batao', 'bataiye', 'sakte', 'sakta', 'sakti',
        'karna', 'karo', 'kar', 'rahe', 'raha', 'rahi', 'achha', 'theek', 'badhiya',
        'shukriya', 'kaun', 'kyun', 'name', 'your', 'you', 'doing',
        'banao', 'bana', 'dikhao', 'sunao'
    }

    # Stop words and short grammatical particles that should NEVER be fuzzy-corrected.
    # NOTE: Hindi negation words (nahi/nahin/nhi/mat) are explicitly excluded:
    # "nahi" is Damerau-Levenshtein-1 from anchor "rahi" and was silently
    # rewritten to "rahi", destroying negation/troubleshooting/correction intents
    # ("kyun nahi ho raha" -> "kyun rahi ho raha").
    # NOTE (2026-09-25): command-critical Hinglish verbs corrupted the same way
    # by distance-1 anchors — verified via vocab probe, each exactly 1 match:
    #   "band"  -> "bana"  (broke ALL band-close: notepad/chrome/pc band karo)
    #   "kam"   -> "kar"   (broke volume/brightness-down: awaz kam karo)
    #   "hatao" -> "batao" (broke remove/delete verbs: file hatao)
    #   "gana"  -> "bana"  (broke song requests: gana chalao)
    #   "baja"  -> "bana"  (broke ring/play verbs)
    # These are legitimate command words, never typos — excluded, not remapped.
    EXCLUDED_WORDS: Set[str] = {
        'ka', 'ki', 'ke', 'ko', 'se', 'me', 'mein', 'pe', 'par', 'ne',
        'to', 'the', 'a', 'an', 'is', 'it', 'in', 'on', 'at', 'or', 'and',
        'main', 'mera', 'meri', 'mere', 'tum', 'aap', 'ye', 'woh', 'yeh',
        'bhi', 'na', 'toh', 'sir', 'dear', 'bro', 'ji', 'boss', 'you',
        'nahi', 'nahin', 'nhi', 'nhin', 'nah', 'mat', 'mt',
        'band', 'kam', 'hatao', 'gana', 'baja',
        'same', 'wahi', 'wohi',
        # NOTE (2026-09-27): time-critical words corrupted the same way —
        # "kal" -> "kar" (distance-1 anchor) broke every kal/parso follow-up
        # ("Kal ka?" -> "kar ka?"). Real words, never typos — excluded.
        'kal', 'parso', 'aaj', 'baar', 'din', 'raat', 'subah', 'shaam',
        'har', 'karne', 'peene', 'pina', 'pine', 'minut', 'ghante', 'baad',
    }

    @classmethod
    def _fuzzy_match_anchor(cls, token: str) -> Optional[str]:
        """
        Resolves a single token against the canonical ANCHOR_WORDS vocabulary
        using Damerau-Levenshtein distance <= 1 with strict ambiguity refusal.
        """
        low = token.lower()
        if len(low) < 3 or low in cls.ANCHOR_WORDS or low in cls.EXCLUDED_WORDS:
            return None
        # Do not alter numbers, decimals, or alphanumeric codes
        if any(c.isdigit() for c in low):
            return None

        matches = [cand for cand in cls.ANCHOR_WORDS if _is_damerau_levenshtein_1(low, cand)]
        if len(matches) == 1:
            return matches[0]
        return None

    @classmethod
    def normalize_text(cls, text: str) -> str:
        """
        Authoritative multi-stage normalization:
        1. Character elongation collapse (e.g. 'pleeease' -> 'please', 'hiii' -> 'hi')
        2. High-confidence conversational shorthand & STT phonetic corrections
        3. Token-level Damerau-Levenshtein anchor fuzzy matching (distance <= 1)
        """
        if not text:
            return ""

        res = text.strip()

        # Step 0: Devanagari Hindi transliteration to phonetic Latin/Hinglish
        try:
            from core.cross_script_matcher import is_devanagari, devanagari_to_latin
            if is_devanagari(res):
                res = devanagari_to_latin(res)
        except Exception:
            pass

        # Step 1: Character elongation collapse (triple+ repeated letters collapsed to single/double).
        # URLs are exempt: "www." is not elongated speech ("https://www.x.com" must survive).
        _url_spans = [(m.start(), m.end()) for m in re.finditer(r"https?://[^\s]+|(?:www\.)[^\s]+", res)]
        if _url_spans:
            _parts, _pos = [], 0
            for _s, _e in _url_spans:
                _parts.append(_TRIPLE_LETTER_RE.sub(r'\1', res[_pos:_s]))
                _parts.append(res[_s:_e])
                _pos = _e
            _parts.append(_TRIPLE_LETTER_RE.sub(r'\1', res[_pos:]))
            res = "".join(_parts)
        else:
            res = _TRIPLE_LETTER_RE.sub(r'\1', res)

        # Step 2: Contextual shorthand patterns
        for pat, repl in cls._COMPILED_SHORTHAND:
            res = pat.sub(repl, res)

        # Step 3: Explicit STT phonetic corrections
        for pat, repl in cls._COMPILED_CORRECTIONS:
            res = pat.sub(repl, res)

        # Step 4: Token-level anchor fuzzy matching
        tokens = res.split()
        modified = False
        norm_tokens = []
        for token in tokens:
            # Preserve punctuation on edges if present
            core = token.strip("?!.,;:")
            prefix = token[:token.find(core)] if core and token.find(core) > 0 else ""
            suffix = token[token.find(core) + len(core):] if core else ""
            if core:
                match = cls._fuzzy_match_anchor(core)
                if match:
                    norm_tokens.append(f"{prefix}{match}{suffix}")
                    modified = True
                    continue
            norm_tokens.append(token)

        if modified:
            res = " ".join(norm_tokens)

        res = WHITESPACE_RE.sub(' ', res).strip()
        return res

    @classmethod
    def clean_query(cls, text: str) -> str:
        """Cleans and capitalizes query extracted from Hinglish sentence."""
        res = text.strip()
        # Remove trailing connectors and punctuation
        res = CONNECTOR_RE.sub(' ', res)
        res = WHITESPACE_RE.sub(' ', res).strip()
        # Format title capitalization nicely
        if res:
            res = " ".join(word.capitalize() for word in res.split())
        return res

    @classmethod
    def has_also_modifier(cls, text: str) -> bool:
        """Detects whether utterance includes additive/sequential modifier ('bhi', 'also', 'as well')."""
        if not text:
            return False
        return bool(re.search(r'\b(?:bhi|also|as\s+well|too)\b', text, re.IGNORECASE))
