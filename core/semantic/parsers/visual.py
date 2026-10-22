# core/semantic/parsers/visual.py
"""
Visual Text Interaction Semantic Parser.

Parses natural language requests to inspect, locate, point to, click, double-click,
or select on-screen text elements in the current focused window.
"""

from dataclasses import dataclass
import re
from typing import Optional, Tuple

from core.semantic.models import SemanticAction
from core.visual_reference import get_visual_reference_manager


# Patterns identifying explicit visual interaction queries
VISUAL_QUERY_PATTERNS = [
    # Location queries
    re.compile(r"\b(?:kahan\s+likha\s+hai|kahan\s+hai|kidhar\s+likha\s+hai|kidhar\s+hai|kaha\s+hai|kahan\s+par\s+hai|kahan\s+dikh\s+raha\s+hai)\b", re.IGNORECASE),
    re.compile(r"\b(?:dhundo|locate\s+karo|find\s+karo|search\s+karo|dhoondho|dhoondh\s+ke\s+batao)\b", re.IGNORECASE),
    re.compile(r"\b(?:where\s+is|find\s+text|locate\s+text|where\s+is\s+it\s+written)\b", re.IGNORECASE),
    # Deictic Hindi questions
    re.compile(r"[\u0900-\u097F]+.*(?:कहाँ|कहा|किधर|ढूंढो|खोजो|दिखाओ)", re.IGNORECASE),
]

# Patterns identifying click / double-click / select actions
CLICK_PATTERNS = [
    re.compile(r"\b(?:par\s+click\s+karo|pe\s+click\s+karo|par\s+click\s+kar\s+do|pe\s+click\s+kar\s+do|par\s+click|pe\s+click|click\s+karo|click\s+kar\s+do|click\s+kardo)\b", re.IGNORECASE),
    re.compile(r"\b(?:click\s+on|click\s+it|click\s+that)\b", re.IGNORECASE),
    re.compile(r"[\u0900-\u097F]+.*(?:पर\s+क्लिक|पे\s+क्लिक|क्लिक\s+करो|क्लिक\s+कर\s+दो)", re.IGNORECASE),
]

DOUBLE_CLICK_PATTERNS = [
    re.compile(r"\b(?:double\s+click\s+karo|double\s+click\s+kar\s+do|double\s+click|doubleclick)\b", re.IGNORECASE),
    re.compile(r"[\u0900-\u097F]+.*(?:डबल\s+क्लिक)", re.IGNORECASE),
]

SELECT_PATTERNS = [
    re.compile(r"\b(?:select\s+karo|select\s+kar\s+do|select\s+kardo|text\s+select\s+karo)\b", re.IGNORECASE),
    re.compile(r"[\u0900-\u097F]+.*(?:सेलेक्ट\s+करो|चुनो)", re.IGNORECASE),
]

POINT_PATTERNS = [
    re.compile(r"\b(?:mouse\s+le\s+jao|mouse\s+pointer\s+le\s+jao|point\s+karo|cursor\s+le\s+jao|pointer\s+rakho|mouse\s+rakho)\b", re.IGNORECASE),
]

# Prefixes to strip
PREFIX_STRIP_RE = re.compile(
    r"^(?:screen\s+par\s+dekho|screen\s+pe\s+dekho|screen\s+par|screen\s+pe|window\s+mein|window\s+me|"
    r"page\s+par|page\s+pe|is\s+page\s+par|is\s+window\s+mein|the\s+word|the\s+text|word|text|ye\s+word|yeh\s+word|"
    r"please|zara|mujhe\s+batao|batao|check\s+karo|dekho)\s+",
    re.IGNORECASE
)

# Suffixes to strip
SUFFIX_STRIP_RE = re.compile(
    r"\s+(?:kahan\s+likha\s+hai|kahan\s+hai|kidhar\s+likha\s+hai|kidhar\s+hai|kaha\s+hai|kahan\s+par\s+hai|"
    r"kahan\s+dikh\s+raha\s+hai|kahan|kidhar|kaha|dhundo|dhoondho|locate\s+karo|find\s+karo|search\s+karo|"
    r"par\s+click\s+karo|pe\s+click\s+karo|par\s+click\s+kar\s+do|pe\s+click\s+kar\s+do|par\s+click|pe\s+click|"
    r"click\s+karo|click\s+kar\s+do|click\s+kardo|click\s+on|click\s+it|click|"
    r"double\s+click\s+karo|double\s+click\s+kar\s+do|double\s+click|"
    r"select\s+karo|select\s+kar\s+do|select\s+kardo|select|"
    r"mouse\s+le\s+jao|mouse\s+pointer\s+le\s+jao|point\s+karo|cursor\s+le\s+jao|pointer\s+rakho|mouse\s+rakho|"
    r"likha\s+hua\s+hai|likha\s+hai|likhi\s+hai|likha|likhi|word|text|"
    r"कहाँ\s+लिखा\s+है|कहाँ\s+है|कहाँ|किधर|ढूंढो|खोजो|पर\s+क्लिक\s+करो|पे\s+क्लिक\s+करो|क्लिक\s+करो|क्लिक|डबल\s+क्लिक|सेलेक्ट\s+करो)$",
    re.IGNORECASE
)


def extract_target_text(raw_text: str) -> str:
    """Strips command preambles, visual action suffixes, and quotes to isolate target text."""
    s = raw_text.strip()

    # Remove quotes if present
    s = re.sub(r"^[\"']|[\"']$", "", s).strip()

    # Repeatedly strip known suffixes
    for _ in range(2):
        s = SUFFIX_STRIP_RE.sub("", s).strip()

    # Strip prefixes
    for _ in range(2):
        s = PREFIX_STRIP_RE.sub("", s).strip()

    # Clean punctuation and extra spaces
    s = re.sub(r"^[\"']|[\"']$", "", s).strip()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_visual_text_interaction(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """
    Parses user utterance into a structured VISUAL_TEXT_INTERACTION SemanticAction.
    Returns None if utterance is not a visual text interaction command.
    """
    cleaned = lowered.strip()

    # Exclude system window management commands like "is window ko close karo"
    if any(w in cleaned for w in ("window close", "window band", "window minimize", "window maximize", "window restore")):
        return None
    if any(w in cleaned for w in ("close karo", "band karo", "close kar do", "band kar do")) and any(w in cleaned for w in ("window", "app", "application")):
        return None

    # Exclude explicit web-search phrasing ("Google search karo server error")
    # so it defers to the web-search parser instead of on-screen text find.
    if re.search(r"\b(?:google|bing|duckduckgo)\b", cleaned) and re.search(r"\bsearch\b", cleaned):
        return None

    # Determine sub-action
    sub_action = None
    if any(pat.search(cleaned) for pat in DOUBLE_CLICK_PATTERNS):
        sub_action = "DOUBLE_CLICK_TEXT"
    elif any(pat.search(cleaned) for pat in SELECT_PATTERNS):
        sub_action = "SELECT_TEXT"
    elif any(pat.search(cleaned) for pat in CLICK_PATTERNS):
        sub_action = "CLICK_TEXT"
    elif any(pat.search(cleaned) for pat in POINT_PATTERNS):
        sub_action = "POINT_TO_TEXT"
    elif any(pat.search(cleaned) for pat in VISUAL_QUERY_PATTERNS):
        sub_action = "FIND_TEXT"

    # Also check Devanagari direct text
    if not sub_action:
        if "कहाँ" in raw_text or "किधर" in raw_text or "ढूंढो" in raw_text:
            sub_action = "FIND_TEXT"
        elif "क्लिक" in raw_text:
            sub_action = "CLICK_TEXT"
        elif "सेलेक्ट" in raw_text:
            sub_action = "SELECT_TEXT"

    if not sub_action:
        return None

    ref_mgr = get_visual_reference_manager()
    is_ref = ref_mgr.is_deictic_reference(cleaned)
    ord_idx = ref_mgr.extract_ordinal_index(cleaned)

    # Extract target text
    target = extract_target_text(raw_text)

    # If pure deictic reference or empty target with valid memory
    if is_ref and not target:
        target = "current_reference"
    elif not target and ord_idx is not None:
        target = "current_reference"

    if not target:
        return None

    return SemanticAction(
        intent="VISUAL_TEXT_INTERACTION",
        service="visual",
        action=sub_action.lower(),
        query=target,
        parameters={
            "target": target,
            "sub_action": sub_action,
            "ordinal_index": ord_idx,
            "is_reference": is_ref,
            "raw_utterance": raw_text
        },
        confidence=1.0
    )
