# core/semantic/parsers/aliases.py
"""User-learned alias management and execution parser."""

import re
from typing import Optional

from core.semantic.models import SemanticAction

DEL_ALIAS_RE1 = re.compile(
    r'\b([a-zA-Z0-9_\-\.]+)\s+alias\s+(?:delete|remove|hata)\s*(?:kar\s+do|karo|do)?\b',
    re.IGNORECASE
)
DEL_ALIAS_RE2 = re.compile(
    r'\b(?:delete|remove)\s+(?:the\s+)?([a-zA-Z0-9_\-\.]+)\s+alias\b',
    re.IGNORECASE
)
UPD_ALIAS_RE1 = re.compile(
    r'([a-zA-Z0-9_\-\.]+)\s+(?:ka|ki)?\s*(?:website|url|target)\s*(?:change|update)\s*(?:kar\s+do|karo)?\s*(?:to|ko|se)?\s*(https?://[^\s]+|[a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,}[^\s]*)',
    re.IGNORECASE
)
UPD_ALIAS_RE2 = re.compile(
    r'([a-zA-Z0-9_\-\.]+)\s+ko\s+(?:naye|new)\s*(?:url|website)?\s*(https?://[^\s]+|[a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,}[^\s]*)\s*se\s*map\s*karo',
    re.IGNORECASE
)
REM_ALIAS_RE = re.compile(
    r'(?:remember|yaad\s+rakhna)\s+(?:that\s+)?([a-zA-Z0-9_\-\.]+)\s+means\s+(?:this\s+website\s*:?\s*)?(https?://[^\s]+|[a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,}[^\s]*|[a-zA-Z0-9_\-\.\s]+)',
    re.IGNORECASE
)
MAP_ALIAS_RE = re.compile(
    r'([a-zA-Z0-9_\-\.]+)\s+ko\s+(?:open\s+)?(https?://[^\s]+|[a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,}[^\s]*|[a-zA-Z0-9_\-\.\s]+?)\s*se\s*map\s*karo',
    re.IGNORECASE
)
FUT_ALIAS_RE = re.compile(
    r'(?:future\s+mein\s+)?(?:jab\s+(?:bhi\s+)?main\s+bolun|whenever\s+i\s+say)\s+(?:`|")?(?:open\s+)?([a-zA-Z0-9_\-\.]+)(?:`|")?[\,\s]+(?:to|then)?\s*(.+?)\s*(?:open\s+karna|kholna|open\s+karo|open|khol\s+dena)',
    re.IGNORECASE
)
MULTIWORD_FUT_ALIAS_RE = re.compile(
    r'(?:future\s+mein\s+)?(?:jab\s+(?:bhi\s+)?main|whenever\s+i)\s+(?:open\s+)?(.+?)\s+(?:bolun|say)\s+(?:to|then)\s+(https?://[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s]*)\s*(?:open\s+karna|kholna|open\s+karo|open|khol\s+dena)?\s*$',
    re.IGNORECASE,
)
ENGLISH_FUT_ALIAS_RE = re.compile(
    r'whenever\s+i\s+say\s+(?:open\s+)?(.+?)(?:,|\s)+(?:open\s+)?(?:the\s+)?(?:.+?\s+)?(?:website|site)?\s*(https?://[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s]*)\s*$',
    re.IGNORECASE,
)
PENDING_WEBSITE_ALIAS_RE = re.compile(
    r'(?:remember\s+(?:this\s+)?website\s+as|(.+?)\s+ko\s+(?:is|this)\s+website\s+se\s+map\s+karo|(.+?)\s+ka\s+matlab\s+.+?\s+website\s+hai)',
    re.IGNORECASE,
)
MEANING_ALIAS_RE = re.compile(
    r'([a-zA-Z0-9_\-\.\s]+?)\s+(?:se\s+mera\s+matlab|ka\s+matlab)\s+(.+?)\s*(?:hai|hota\s+hai)?$',
    re.IGNORECASE,
)
FUT_APP_ALIAS_RE = re.compile(
    r'(?:future\s+mein\s+)?(?:jab\s+(?:bhi\s+)?main|whenever\s+i)\s+(?:open\s+)?(?:[\'"`]?)(.+?)(?:[\'"`]?)\s+(?:bolun|say)\s+(?:to|then)\s+(?:open\s+)?(?:[\'"`]?)(.+?)(?:[\'"`]?)\s*(?:open\s+karna|kholna|open\s+karo|open|khol\s+dena)?\s*$',
    re.IGNORECASE,
)
URL_EXTRACT_RE = re.compile(r'(https?://[^\s]+|[a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,}[^\s]*)')
STRIP_ALIAS_DESC_RE = re.compile(r'\b(?:website|site|app|the)\b', re.IGNORECASE)
STRIP_PREFIX_RE = re.compile(r'^(?:jarvis|please)\s*[\,\:\s]*', re.IGNORECASE)


def _determine_action_type(target: str) -> str:
    from core.windows_app_resolver import WindowsAppResolver
    t = target.strip().lower()
    if t.startswith(("http://", "https://")):
        return "OPEN_WEBSITE"
    if re.search(r'\.[a-z]{2,}(/|$)', t):
        return "OPEN_WEBSITE"
    if WindowsAppResolver.is_application(target):
        return "OPEN_APPLICATION"
    if "." in t and " " not in t and any(t.endswith(ext) for ext in [".com", ".org", ".net", ".in", ".io", ".co"]):
        return "OPEN_WEBSITE"
    return "OPEN_APPLICATION"


def parse_alias_management(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Detects user commands to learn, update, delete, or list custom website/app aliases."""
    # 1. Delete Alias (e.g. "GLPI alias delete kar do", "GLPI alias hata do", "delete GLPI alias")
    m_del = DEL_ALIAS_RE1.search(raw_text)
    m_del2 = DEL_ALIAS_RE2.search(raw_text)
    if m_del or m_del2:
        alias_name = (m_del.group(1) if m_del else m_del2.group(1)).strip()
        return SemanticAction(
            intent="DELETE_ALIAS",
            service="alias",
            action="delete_alias",
            query=raw_text,
            parameters={"alias": alias_name}
        )

    # 2. Update Alias (e.g. "GLPI ka website change kar do to https://...", "GLPI ko naye url https://... se map karo")
    m_upd = UPD_ALIAS_RE1.search(raw_text)
    m_upd2 = UPD_ALIAS_RE2.search(raw_text)
    if m_upd or m_upd2:
        match = m_upd if m_upd else m_upd2
        alias_name = match.group(1).strip()
        new_target = match.group(2).strip()
        return SemanticAction(
            intent="UPDATE_ALIAS",
            service="alias",
            action="update_alias",
            query=raw_text,
            parameters={"alias": alias_name, "target": new_target}
        )

    # 3. Learn Alias
    # Meaning alias e.g. "store se mera matlab Microsoft Store hai" or "store ka matlab Microsoft Store hai"
    m_meaning = MEANING_ALIAS_RE.search(raw_text)
    if m_meaning:
        alias_name = m_meaning.group(1).strip(" '\"`")
        target = m_meaning.group(2).strip(" '\"`")
        if alias_name and target:
            action_type = _determine_action_type(target)
            return SemanticAction(
                intent="LEARN_ALIAS",
                service="alias",
                action="learn_alias",
                query=raw_text,
                parameters={"alias": alias_name, "target": target, "action_type": action_type}
            )

    # Future alias with app or web target e.g. "jab main 'store' bolun to Microsoft Store open karna"
    m_fut_app = FUT_APP_ALIAS_RE.search(raw_text)
    if m_fut_app:
        alias_name = m_fut_app.group(1).strip(" '\"`")
        target_phrase = m_fut_app.group(2).strip(" '\"`")
        if alias_name and target_phrase:
            action_type = _determine_action_type(target_phrase)
            return SemanticAction(
                intent="LEARN_ALIAS",
                service="alias",
                action="learn_alias",
                query=raw_text,
                parameters={"alias": alias_name, "target": target_phrase, "action_type": action_type}
            )

    m_english_future = ENGLISH_FUT_ALIAS_RE.search(raw_text)
    if m_english_future:
        return SemanticAction(
            intent="LEARN_ALIAS",
            service="alias",
            action="learn_alias",
            query=raw_text,
            parameters={"alias": m_english_future.group(1).strip(), "target": m_english_future.group(2).strip(), "action_type": "OPEN_WEBSITE"},
        )

    m_multiword = MULTIWORD_FUT_ALIAS_RE.search(raw_text)
    if m_multiword:
        return SemanticAction(
            intent="LEARN_ALIAS",
            service="alias",
            action="learn_alias",
            query=raw_text,
            parameters={"alias": m_multiword.group(1).strip(), "target": m_multiword.group(2).strip(), "action_type": "OPEN_WEBSITE"},
        )

    m_pending = PENDING_WEBSITE_ALIAS_RE.search(raw_text)
    if m_pending:
        alias_name = (m_pending.group(1) or m_pending.group(2) or raw_text.split(" as ")[-1]).strip(" .,'\"")
        if alias_name:
            return SemanticAction(
                intent="LEARN_ALIAS",
                service="alias",
                action="learn_alias",
                query=raw_text,
                parameters={"alias": alias_name, "target": "", "action_type": "OPEN_WEBSITE"},
            )

    m_rem = REM_ALIAS_RE.search(raw_text)
    if m_rem:
        alias_name = m_rem.group(1).strip(" '\"`")
        target = m_rem.group(2).strip(" '\"`")
        action_type = _determine_action_type(target)
        return SemanticAction(
            intent="LEARN_ALIAS",
            service="alias",
            action="learn_alias",
            query=raw_text,
            parameters={"alias": alias_name, "target": target, "action_type": action_type}
        )

    m_map = MAP_ALIAS_RE.search(raw_text)
    if m_map:
        alias_name = m_map.group(1).strip(" '\"`")
        target = m_map.group(2).strip(" '\"`")
        action_type = _determine_action_type(target)
        return SemanticAction(
            intent="LEARN_ALIAS",
            service="alias",
            action="learn_alias",
            query=raw_text,
            parameters={"alias": alias_name, "target": target, "action_type": action_type}
        )

    m_fut = FUT_ALIAS_RE.search(raw_text)
    if m_fut:
        alias_name = m_fut.group(1).strip(" '\"`")
        target_phrase = m_fut.group(2).strip(" '\"`")
        url_m = URL_EXTRACT_RE.search(target_phrase)
        if url_m:
            target = url_m.group(1).strip()
            action_type = "OPEN_WEBSITE"
        else:
            target = STRIP_ALIAS_DESC_RE.sub('', target_phrase).strip()
            if not target:
                target = alias_name
            action_type = _determine_action_type(target)
        return SemanticAction(
            intent="LEARN_ALIAS",
            service="alias",
            action="learn_alias",
            query=raw_text,
            parameters={"alias": alias_name, "target": target, "action_type": action_type}
        )

    return None


def parse_custom_alias_execution(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """
    Checks if the utterance is an execution of a user-taught custom alias.
    Matches exact alias or commands like 'open GLPI', 'GLPI kholo', 'GLPI open karo', 'GLPI website kholo', 'Jarvis, GLPI'.
    """
    try:
        # Structured website knowledge is checked before universal target
        # parsing so a learned multiword site is never mistaken for an app.
        from plugins.browser.website_resolver import WebsiteResolver
        clean_q = STRIP_PREFIX_RE.sub('', lowered).strip()
        website = WebsiteResolver.resolve(clean_q)
        if website.source in {"user_learned", "custom_alias"}:
            return SemanticAction(
                intent="OPEN_WEBSITE",
                service="browser",
                action="open_website",
                query=raw_text,
                parameters={"site": clean_q},
                confidence=website.confidence,
            )
    except Exception:
        pass
    try:
        from core.alias_manager import get_alias_manager
        alias_mgr = get_alias_manager()
        clean_q = STRIP_PREFIX_RE.sub('', lowered).strip()
        alias_entry = alias_mgr.resolve_alias(clean_q)
        if alias_entry:
            act_type = alias_entry.get("action_type", "OPEN_WEBSITE")
            from core.windows_app_resolver import WindowsAppResolver
            if act_type in ("OPEN_APPLICATION", "OPEN_APP", "launch_app") or (
                WindowsAppResolver.is_application(alias_entry["target"])
                and not alias_entry["target"].startswith(("http://", "https://"))
            ):
                return SemanticAction(
                    intent="OPEN_APP",
                    service="system",
                    action="launch_app",
                    query=raw_text,
                    parameters={
                        "app_name": alias_entry["target"],
                        "action_type": "OPEN_APPLICATION",
                    },
                    confidence=0.98,
                )
            return SemanticAction(
                intent="OPEN_WEBSITE",
                service="browser",
                action="open_website",
                query=raw_text,
                parameters={
                    "site": alias_entry["alias"],
                    "url": alias_entry["target"],
                    "action_type": alias_entry.get("action_type", "OPEN_WEBSITE")
                },
                confidence=0.95,
            )
    except Exception:
        pass
    return None
