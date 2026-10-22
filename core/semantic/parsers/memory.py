# core/semantic/parsers/memory.py
"""Explicit memory-control command parser (Phase 8).

Owns ONLY explicit user memory directives. Runs BEFORE the reminder parser so
"yaad rakho ..." creates memory while "yaad dilana / reminder laga do" still
routes to reminders. Profile phrasings ("mera naam ... hai") stay with
PersonalProfileExtractor (runs earlier in JarvisCore); this parser never
claims them.
"""

import re
from typing import Optional

from core.semantic.models import SemanticAction

# Reminder-owned signals — never steal these. Time expressions alone do NOT
# imply a reminder: an explicit "yaad rakho / remember" lead always wins.
_REMINDER_GUARD_RE = re.compile(
    r"\b(yaad\s+dilana|yaad\s+dila\s+do|yaad\s+dilao|reminder|remind\s+me|alarm)\b",
    re.IGNORECASE,
)

# Command verbs (explicit memory only)
_REMEMBER_LEAD_RE = re.compile(
    r"^(?:yaad\s+rakho(?:\s+ki)?|remember(?:\s+that)?)\s+(?P<content>.+)$",
    re.IGNORECASE,
)
_REMEMBER_TRAIL_RE = re.compile(
    r"^(?P<content>.+?)[, ]+(?:isko\s+)?yaad\s+rakhna$",
    re.IGNORECASE,
)
_REMEMBER_ISKO_RE = re.compile(
    r"^(?:isko|ise|isse)\s+yaad\s+rakhna\.?$",
    re.IGNORECASE,
)
_FORGET_RE = re.compile(
    r"^(?:ye(?:h)?\s+(?:memory|baat)\s+(?:delete|hatao|bhool)\s+karo"
    r"|(?:ye(?:h)?\s+)?yaad\s+mat\s+rakhna"
    r"|(?P<target>.+?)\s+(?:ko\s+)?bhool\s+jao"
    r"|forget\s+(?P<target_en>.+))\.?$",
    re.IGNORECASE,
)
_RECALL_RE = re.compile(
    r"^(?:tumhe(?:n)?\s+)?mere\s+baare\s+mein\s+kya\s+yaad\s+hai\??$"
    r"|^what\s+do\s+you\s+remember\s+about\s+me\??$"
    r"|^maine\s+kya\s+(?:bataya|sikhaya)\s+tha\??$"
    r"|^yaad\s+dilao\s+maine\s+kya\s+bataya\s+tha\??$",
    re.IGNORECASE,
)
_PREF_QUERY_RE = re.compile(
    r"^meri\s+preferences?\s+kya\s+hain?\??$"
    r"|^what\s+are\s+my\s+preferences\??$",
    re.IGNORECASE,
)
# Generic personal-fact query ("what is my X?" / "mera X kya hai?").
# Known profile fields stay with PersonalProfileExtractor (runs first).
_FACT_QUERY_RE = re.compile(
    r"^(?:what\s+is\s+my\s+(?P<k_en>.+?)|mera\s+(?P<k_hi>.+?)\s+kya\s+hai)\??$",
    re.IGNORECASE,
)
_PROFILE_FIELD_GUARD_RE = re.compile(
    r"^(?:naam|name|shehar|shahar|city|pasandida\s+khana|favourite\s+food|favorite\s+food|"
    r"pasandida\s+browser|favourite\s+browser|preferred\s+browser|browser|pasand|interest|"
    r"hobby|current\s+project|project)$",
    re.IGNORECASE,
)
_CLEAR_SESSION_RE = re.compile(
    r"^session\s+memory\s+(?:clear|saaf)\s+karo\.?$",
    re.IGNORECASE,
)

# Profile-owned: never claim (PersonalProfileExtractor runs first in core).
_PROFILE_GUARD_RE = re.compile(
    r"(mera\s+naam|my\s+name\s+is|main\s+.+\s+hoon|i\s+am\s+.+|"
    r"rehta\s+hoon|live\s+in|pasand\s+hai|i\s+like|hobby|project)",
    re.IGNORECASE,
)

# Command verbs — a memory turn must not hijack real commands.
_COMMAND_GUARD_RE = re.compile(
    r"\b(kholo|open|band\s+karo|close|chalao|delete\s+karo|bhejo|play|lock|shutdown)\b",
    re.IGNORECASE,
)

# Website-alias teaching owns URL-bearing content ("remember X means <url>").
_URL_GUARD_RE = re.compile(
    r"https?://|www\.|\.(?:com|net|org|io|in|gov|edu|app)\b",
    re.IGNORECASE,
)

# Learning / correction layers own these forget targets ("X ki learning
# bhool jao", "preference bhool jao" via correction hook / inspector).
_LEARNING_FORGET_GUARD_RE = re.compile(
    r"\b(learning|sikhaya|sikhayi|preference|prefer|pattern|correction|vocabulary)\b",
    re.IGNORECASE,
)


def _clean(content: str) -> str:
    return re.sub(r"\s+", " ", (content or "").strip(" ,.!?")).strip()


def _strip_address(text: str) -> str:
    """Drops a leading wake-word address ("jarvis,"/"jarvis") so direct
    commands work with or without it. Never touches the inner content."""
    return re.sub(r"^(?:jarvis\s*,?\s+)", "", text.strip(), flags=re.IGNORECASE).strip()


def parse_memory_command(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    text = _strip_address(_clean(raw_text))
    low = _strip_address(_clean(lowered))
    if not low:
        return None
    # Guards: reminders, profiles, and real commands keep their owners.
    if _REMINDER_GUARD_RE.search(low):
        return None

    m = _CLEAR_SESSION_RE.match(low)
    if m:
        return SemanticAction(intent="MEMORY_CLEAR", service="memory",
                              action="clear_session", query=None,
                              parameters={}, confidence=1.0)

    if _RECALL_RE.match(low):
        return SemanticAction(intent="MEMORY_RECALL", service="memory",
                              action="recall_summary", query=None,
                              parameters={}, confidence=1.0)

    if _PREF_QUERY_RE.match(low):
        return SemanticAction(intent="MEMORY_PREFERENCES", service="memory",
                              action="list_preferences", query=None,
                              parameters={}, confidence=1.0)

    m = _FACT_QUERY_RE.match(low)
    if m:
        key = _clean(m.group("k_en") or m.group("k_hi") or "")
        if key and not _PROFILE_FIELD_GUARD_RE.match(key) \
                and not _COMMAND_GUARD_RE.search(key) and len(key.split()) <= 6:
            return SemanticAction(intent="MEMORY_QUERY_FACT", service="memory",
                                  action="query_fact", query=key,
                                  parameters={"key": key}, confidence=0.95)

    if _REMEMBER_ISKO_RE.match(low):
        return SemanticAction(intent="MEMORY_REMEMBER", service="memory",
                              action="remember", query=None,
                              parameters={"content": None, "needs_context": True},
                              confidence=0.85)

    m = _REMEMBER_LEAD_RE.match(text)
    if m:
        content = _clean(m.group("content"))
        if content and not _URL_GUARD_RE.search(content) \
                and not _PROFILE_GUARD_RE.search(content.lower()) \
                and not _COMMAND_GUARD_RE.search(content):
            return SemanticAction(intent="MEMORY_REMEMBER", service="memory",
                                  action="remember", query=content,
                                  parameters={"content": content, "explicit": True},
                                  confidence=1.0)
        return None

    m = _REMEMBER_TRAIL_RE.match(text)
    if m:
        content = _clean(m.group("content"))
        if content and not _PROFILE_GUARD_RE.search(content.lower()) \
                and not _COMMAND_GUARD_RE.search(content):
            return SemanticAction(intent="MEMORY_REMEMBER", service="memory",
                                  action="remember", query=content,
                                  parameters={"content": content, "explicit": True},
                                  confidence=1.0)
        return None

    m = _FORGET_RE.match(low)
    if m:
        target = _clean(m.group("target") or m.group("target_en") or "")
        if target and _LEARNING_FORGET_GUARD_RE.search(target):
            return None
        # Bare "ye memory delete karo" (no target) -> forget flow with slot ask.
        return SemanticAction(intent="MEMORY_FORGET", service="memory",
                              action="forget", query=target or None,
                              parameters={"target": target or None},
                              confidence=1.0)

    # "X bhool jao" with Hindi spelling variants not covered above.
    m = re.match(r"^(?P<t>.+?)\s+(?:ko\s+)?bhool\s+j(?:a)?o\.?$", low)
    if m:
        target = _clean(m.group("t"))
        if target and _LEARNING_FORGET_GUARD_RE.search(target):
            return None
        if target and target not in {"isko", "ise", "isse", "ye", "yeh"}:
            return SemanticAction(intent="MEMORY_FORGET", service="memory",
                                  action="forget", query=target,
                                  parameters={"target": target}, confidence=0.95)
        return SemanticAction(intent="MEMORY_FORGET", service="memory",
                              action="forget", query=None,
                              parameters={"target": None}, confidence=0.85)
    return None
