# core/semantic/parsers/windows.py
"""Window layout, positioning, snapping, control, daily-use folder management, and app launching."""

import re
from typing import Any, Dict, Optional

from core.semantic.constants import (
    COMPILED_OPEN_VERBS,
    KNOWN_APPS,
    OPEN_VERBS,
    POSITION_KEYWORDS,
    SERVICE_PATTERNS,
    WINDOW_OPERATIONS,
)
from core.semantic.models import IntentName, SemanticAction
from core.semantic.normalizer import HinglishNormalizer

OPEN_APP_INTENT = IntentName("OPEN_APPLICATION")

# Precompiled patterns
CONTAINED_PREPOSITIONS = r"wala|wali|wale|ka|ki|ke|me|mein|par|pe|se|ke\s+andar|ke\s+under|in|on"

CONTAINED_VERBS_OPEN = r"open\s+kar\s+do|open\s+kardo|open\s+karo|open\s+kijiye|open|khol\s+do|khol\s+de|kholiye|kholo|chalao|chala\s+do|chala\s+de|launch\s+karo|launch|play\s+karo|play"

CONTAINED_VERBS_CLOSE = r"band\s+kar\s+do|band\s+kardo|band\s+kar\s+de|band\s+kijiye|band\s+karo|band|close\s+kar\s+do|close\s+kardo|close\s+kar\s+de|close\s+kijiye|close\s+karo|close|hatao|hata\s+do|exit|kill"

CONTAINED_VERBS_FOCUS = r"focus\s+karo|focus|activate\s+karo|activate|samne\s+lao|saamne\s+lao|switch\s+to"

ALL_CONTAINED_VERBS = rf"{CONTAINED_VERBS_CLOSE}|{CONTAINED_VERBS_OPEN}|{CONTAINED_VERBS_FOCUS}"

CONTAINED_BROWSER_NAMES = r"(?:google\s+)?chrome|brave(?:\s+browser)?|(?:microsoft\s+)?edge|(?:mozilla\s+)?firefox|opera|vivaldi"

CONTAINED_TAB_RE = re.compile(
    rf"(?:in\s+)?({CONTAINED_BROWSER_NAMES})(?:\s+browser)?\s+(?:{CONTAINED_PREPOSITIONS})\s+(.+?)(?:\s+wala)?\s+tab\s+({ALL_CONTAINED_VERBS})",
    re.IGNORECASE
)
BROWSER_CONTAINED_ENG_RE = re.compile(
    rf"^({ALL_CONTAINED_VERBS})\s+(.+?)(?:\s+(?:website|site|tab|app|application))?\s+(?:on|in|from|inside)\s+({CONTAINED_BROWSER_NAMES})$",
    re.IGNORECASE,
)
BROWSER_CONTAINED_HI_TARGET_FIRST_RE = re.compile(
    rf"^(.+?)(?:\s+ki\s+website|\s+ka\s+tab|\s+wala\s+tab|\s+wala|\s+tab)?\s*(?:ko\s+)?({CONTAINED_BROWSER_NAMES})\s+(?:{CONTAINED_PREPOSITIONS})\s*({ALL_CONTAINED_VERBS})$",
    re.IGNORECASE,
)
BROWSER_CONTAINED_HI_BROWSER_FIRST_RE = re.compile(
    rf"^({CONTAINED_BROWSER_NAMES})\s+(?:{CONTAINED_PREPOSITIONS})\s+(.+?)(?:\s+ki\s+website|\s+ka\s+tab|\s+wala\s+tab|\s+wala|\s+tab)?\s*(?:ko\s+)?({ALL_CONTAINED_VERBS})$",
    re.IGNORECASE,
)
BROWSER_CONTAINED_POSTFIX_RE = re.compile(
    rf"^(.+?)\s+({ALL_CONTAINED_VERBS})\s+({CONTAINED_BROWSER_NAMES})(?:\s+(?:{CONTAINED_PREPOSITIONS}))?$",
    re.IGNORECASE,
)
BROWSER_CONTAINED_PREFIX_RE = re.compile(
    rf"^(?:in|on|from)\s+({CONTAINED_BROWSER_NAMES})\s+({ALL_CONTAINED_VERBS})\s+(.+?)$",
    re.IGNORECASE,
)
GENERIC_TAB_RE = re.compile(
    rf"(.+?)(?:\s+wala\s+tab)?\s+({ALL_CONTAINED_VERBS})",
    re.IGNORECASE
)
REVERSE_TAB_RE = re.compile(
    rf"({ALL_CONTAINED_VERBS})\s+(.+)",
    re.IGNORECASE
)
ALL_SAB_RE = re.compile(r"\b(?:all|sab|saare|sabhi)\b", re.IGNORECASE)
ONE_EK_RE = re.compile(r"\b(?:one|ek)\b", re.IGNORECASE)
TAB_PAGE_RE = re.compile(r"\b(?:tab|tabs|page)\b", re.IGNORECASE)
CLEAN_TAB_TARGET_RE = re.compile(r"\b(?:all|sab|saare|sabhi|one|ek|ko|ka|ki|ke|tab|tabs|website|site|page|wala|wali|wale)\b", re.IGNORECASE)
BAND_CLOSE_RE = re.compile(r"\b(?:band|close)\b", re.IGNORECASE)


def normalize_browser_container(name: str) -> str:
    n = name.strip().lower()
    if "brave" in n:
        return "brave"
    if "chrome" in n:
        return "chrome"
    if "edge" in n:
        return "edge"
    if "firefox" in n:
        return "firefox"
    if "opera" in n:
        return "opera"
    if "vivaldi" in n:
        return "vivaldi"
    return n

STATUS_CHECK_EXCLUDE_RE = re.compile(r'\b(?:hai\s+kya|open\s+hai|chalu\s+hai|running\s+hai|chal\s+raha\s+hai|khula\s+hai)\b', re.IGNORECASE)
GLOBAL_LAUNCH_RE = re.compile(r'\b(open|kholo|launch|chalao)\b', re.IGNORECASE)
CLAUSE_SPLIT_RE = re.compile(r'\b(?:aur|and|or|phir|fir|then|tatha|saath\s+hi)\b|,', re.IGNORECASE)
COMPACT_LAYOUT_RE = re.compile(r'\b([a-zA-Z0-9_\-]+)\s+(?:ko\s+)?(left|right|top|bottom)\b', re.IGNORECASE)
LAYOUT_ISOLATE_STRIP_RE = re.compile(r'\b(open|kholo|launch|chalao|rakho|rakh\s+do|rakh|shift|position|set|karo|kar\s+do|kar|do|kijiye|lao|de|na|ko|ka|ki|ke|par|pe|me|mein|in|on|to|app|application|please|zara|screen|full|corner|side)\b', re.IGNORECASE)
CURRENT_WIN_STRIP_RE = re.compile(r'\b(this|current|active|focused|is|iss|yeh|ye|yah|isko|isse|ise|usko|usse|use|woh|usey|window)\b', re.IGNORECASE)
WINDOW_CONTROL_STRIP_RE = re.compile(r'\b(karo|kar\s+do|kar|do|kijiye|lao|de|na|ko|ka|ki|ke|par|pe|me|mein|in|on|to|app|application|please|zara|screen|full)\b', re.IGNORECASE)

APP_CLOSE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\bclose\b', r'\bband\s+karo\b', r'\bband\s+kar\s+do\b', r'\bband\s+kar\b',
        r'\bhatao\b', r'\bhata\s+do\b',
        r'\bkill\b', r'\bterminate\b', r'\bstop\b', r'\bexit\b'
    ]
]

CLOSE_ALL_FOLDERS_RE = re.compile(
    r'\b(?:close\s+(?:all|saare|sab|sabhi|tamam)\s+(?:open\s+)?folders?|(?:all|saare|sab|sabhi|tamam)\s+(?:open\s+)?folders?\s+(?:band|close)|open\s+folders?\s+(?:band|close)|close\s+all\s+open\s+folders)\b',
    re.IGNORECASE
)
CLOSE_NAMED_FOLDER_RE = re.compile(
    r'\b(?:close\s+(?:the\s+)?(?P<name>[\w\-]+)\s+folder|(?P<name2>[\w\-]+)\s+folder\s+(?:close|band\s+karo|band\s+kar\s+do|band\s+kardo|band))\b',
    re.IGNORECASE
)
OPEN_NAMED_FOLDER_RE = re.compile(
    r'\b(?:open\s+(?:the\s+)?(?P<name>[\w\-]+)\s+folder|(?P<name2>[\w\-]+)\s+folder\s+(?:kholo|open\s+karo|open\s+kar\s+do|open))\b',
    re.IGNORECASE
)

NATIVE_APPS = {
    "brave", "brave browser", "chrome", "google chrome", "edge", "microsoft edge", "firefox",
    "spotify", "vlc", "excel", "microsoft excel", "ms excel", "msexcel",
    "notepad", "calculator", "calc", "word", "microsoft word", "ms word", "winword", "msword",
    "powerpoint", "power point", "microsoft powerpoint", "microsoft power point",
    "ms powerpoint", "ms power point", "ppt",
    "access", "microsoft access", "ms access", "msaccess",
    "publisher", "microsoft publisher", "ms publisher", "mspub",
    "settings", "setting", "terminal", "cmd", "explorer", "store", "whatsapp",
}

WEB_IDENTITIES = {
    "youtube", "gmail", "flipkart", "github", "instagram", "facebook",
    "linkedin", "reddit", "amazon", "google", "chatgpt", "chat gpt",
    "bing", "yahoo", "duckduckgo", "dhan", "zerodha", "groww", "upstox", "glpi", "netflix",
}

DAILY_FOLDER_MAP = {
    "startup": ["startup", "start up"],
    "downloads": ["downloads", "download"],
    "documents": ["documents", "document", "docs", "my documents"],
    "desktop": ["desktop"],
    "pictures": ["pictures", "picture", "photos", "photo", "images"],
    "videos": ["videos", "video", "movies", "movie"],
    "music": ["music", "songs", "song", "audio"],
    "recycle_bin": ["recycle bin", "recyclebin", "trash", "dustbin", "bin"],
    "temp": ["temp", "temporary"],
    "appdata": ["appdata", "app data", "roaming"],
    "localappdata": ["localappdata", "local appdata", "local app data"],
    "c_drive": ["c drive", "c:", "c:\\", "local disk (c:)", "local disk c", "drive c"],
    "d_drive": ["d drive", "d:", "d:\\", "local disk (d:)", "local disk d", "drive d"],
    "e_drive": ["e drive", "e:", "e:\\", "local disk (e:)", "local disk e", "drive e"],
    "home": ["home", "user folder", "user profile", "home folder"],
}

APP_MAP = {
    "brave": "brave",
    "brave browser": "brave",
    "chrome": "chrome",
    "google chrome": "chrome",
    "chrome browser": "chrome",
    "vlc": "vlc",
    "vlc media player": "vlc",
    "vlc player": "vlc",
    "excel": "excel",
    "excel sheet": "excel",
    "microsoft excel": "excel",
    "ms excel": "excel",
    "msexcel": "excel",
    "notepad": "notepad",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "code": "code",
    "spotify": "spotify",
    "edge": "edge",
    "microsoft edge": "edge",
    "firefox": "firefox",
    "firefox browser": "firefox",
    "calc": "calc",
    "calculator": "calc",
    "terminal": "terminal",
    "powershell": "powershell",
    "cmd": "cmd",
    "command prompt": "cmd",
    "word": "word",
    "ms word": "word",
    "microsoft word": "word",
    "winword": "word",
    "msword": "word",
    "powerpoint": "powerpoint",
    "power point": "powerpoint",
    "microsoft powerpoint": "powerpoint",
    "microsoft power point": "powerpoint",
    "ms powerpoint": "powerpoint",
    "ms power point": "powerpoint",
    "ppt": "powerpoint",
    "access": "access",
    "microsoft access": "access",
    "ms access": "access",
    "msaccess": "access",
    "publisher": "publisher",
    "microsoft publisher": "publisher",
    "ms publisher": "publisher",
    "mspub": "publisher",
    "browser": "browser"
}


def parse_universal_target_action(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Emit a generic target/action request without assuming its location."""
    container = ""
    target = ""
    verb = ""
    contained = CONTAINED_TAB_RE.fullmatch(lowered)
    if contained:
        container, target, verb = contained.groups()
    else:
        m_eng = BROWSER_CONTAINED_ENG_RE.fullmatch(lowered)
        if m_eng:
            verb, target, container = m_eng.groups()
            contained = m_eng
        else:
            m_hi_target = BROWSER_CONTAINED_HI_TARGET_FIRST_RE.fullmatch(lowered)
            if m_hi_target:
                target, container, verb = m_hi_target.groups()
                contained = m_hi_target
            else:
                m_hi_browser = BROWSER_CONTAINED_HI_BROWSER_FIRST_RE.fullmatch(lowered)
                if m_hi_browser:
                    container, target, verb = m_hi_browser.groups()
                    contained = m_hi_browser
                else:
                    m_prefix = BROWSER_CONTAINED_PREFIX_RE.fullmatch(lowered)
                    if m_prefix:
                        container, verb, target = m_prefix.groups()
                        contained = m_prefix
                    else:
                        m_postfix = BROWSER_CONTAINED_POSTFIX_RE.fullmatch(lowered)
                        if m_postfix and m_postfix.group(1).strip().lower() not in ("please", "zara", "kripya", "kindly", "bhai", "yaar", "dost"):
                            target, verb, container = m_postfix.groups()
                            contained = m_postfix
                        else:
                            generic = GENERIC_TAB_RE.fullmatch(lowered)
                            if not generic:
                                reverse = REVERSE_TAB_RE.fullmatch(lowered)
                                if not reverse:
                                    return None
                                verb, target = reverse.groups()
                            else:
                                target, verb = generic.groups()

    if container:
        container = normalize_browser_container(container)

    scope = "all" if ALL_SAB_RE.search(target) else "one" if ONE_EK_RE.search(target) else "auto"
    is_tab_command = bool(TAB_PAGE_RE.search(lowered) or container)
    clean_target = CLEAN_TAB_TARGET_RE.sub(" ", target)
    clean_target = re.sub(r"\s+", " ", clean_target).strip()

    if not contained and not is_tab_command and clean_target in NATIVE_APPS:
        return None

    has_web_domain = "." in clean_target and any(clean_target.endswith(tld) for tld in (".com", ".org", ".net", ".in", ".co", ".io", ".ai", ".app"))
    if not contained and not is_tab_command and not has_web_domain and clean_target not in WEB_IDENTITIES:
        return None

    target = clean_target
    action = (
        "close" if (BAND_CLOSE_RE.search(verb) or any(w in verb for w in ("band", "close", "hatao", "exit", "kill")))
        else "focus" if "focus" in verb
        else "activate" if "activate" in verb
        else "open"
    )
    if not target:
        return None
    if action == "open" and not contained and not is_tab_command:
        return None

    return SemanticAction(
        intent="UNIVERSAL_TARGET_ACTION", service="target", action="execute",
        parameters={"target": target, "action": action, "container": container, "scope": scope},
        confidence=1.0,
    )


def extract_single_layout_item(clause: str, global_launch: bool = False) -> Optional[Dict[str, Any]]:
    """Extracts (app_name, position, launch_if_needed) from a single clause."""
    found_pos = None
    for pos_key, patterns in POSITION_KEYWORDS.items():
        for pat in patterns:
            if re.search(pat, clause):
                found_pos = pos_key
                break
        if found_pos:
            break

    if not found_pos:
        return None

    clause_launch = global_launch or bool(GLOBAL_LAUNCH_RE.search(clause))

    isolated = clause
    for patterns in POSITION_KEYWORDS.values():
        for pat in patterns:
            isolated = re.sub(pat, ' ', isolated)

    for filler in HinglishNormalizer.FILLERS:
        isolated = re.sub(filler, ' ', isolated)

    isolated = LAYOUT_ISOLATE_STRIP_RE.sub(' ', isolated)
    isolated = re.sub(r'\s+', ' ', isolated).strip()

    if any(w in isolated for w in ["this window", "is window", "iss window", "current window", "active window", "focused window", "yeh window", "ye window", "isko", "isse", "ise", "this", "current", "active", "window"]):
        isolated_without_win = CURRENT_WIN_STRIP_RE.sub(' ', isolated).strip()
        if not isolated_without_win:
            isolated = "current"
        else:
            isolated = isolated_without_win

    if not isolated:
        target_app = "current"
    else:
        target_app = APP_MAP.get(isolated, isolated)
        if target_app == isolated:
            for k, v in APP_MAP.items():
                if k in isolated:
                    target_app = v
                    break

    return {
        "app_name": target_app,
        "position": found_pos,
        "launch_if_needed": clause_launch
    }


def parse_window_layout(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Parses window layout, positioning, snapping, and multi-window tiling."""
    if any(w in lowered for w in ["play", "chalao gaana", "gaana", "song", "bajao", "search karke"]):
        return None

    if "side by side" in lowered or "bagal bagal" in lowered or "side-by-side" in lowered:
        return SemanticAction(
            intent="WINDOW_LAYOUT",
            service="windows",
            action="layout_windows",
            query="side_by_side",
            parameters={"layout_type": "side_by_side"}
        )

    global_launch = bool(GLOBAL_LAUNCH_RE.search(lowered))

    clauses = CLAUSE_SPLIT_RE.split(lowered)
    items = []
    for c in clauses:
        c = c.strip()
        if not c:
            continue
        item = extract_single_layout_item(c, global_launch=global_launch)
        if item:
            items.append(item)

    if len(items) < 2:
        compact_matches = COMPACT_LAYOUT_RE.findall(lowered)
        if len(compact_matches) >= 2:
            compact_items = []
            for app, pos in compact_matches:
                app_clean = app.lower().strip()
                if app_clean in KNOWN_APPS or app_clean in ("current", "window", "this"):
                    compact_items.append({
                        "app_name": app_clean,
                        "position": pos.lower(),
                        "launch_if_needed": global_launch
                    })
            if len(compact_items) >= 2:
                items = compact_items

    if not items:
        return None

    if len(items) == 1:
        it = items[0]
        return SemanticAction(
            intent="WINDOW_POSITION",
            service="windows",
            action="position_window",
            query=it["app_name"],
            parameters={
                "app_name": it["app_name"],
                "position": it["position"],
                "launch_if_needed": it.get("launch_if_needed", False)
            }
        )
    else:
        return SemanticAction(
            intent="WINDOW_LAYOUT",
            service="windows",
            action="layout_windows",
            query="multi_window",
            parameters={"items": items}
        )


def parse_window_control(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Generic WindowManager / ApplicationController parser for ANY installed application."""
    if any(w in lowered for w in ["play", "chalao", "gaana", "song", "bajao", "search karke"]):
        return None

    matched_op = None
    matched_op_pattern = None

    for op, patterns in WINDOW_OPERATIONS.items():
        for pat in patterns:
            m = re.search(pat, lowered)
            if m:
                matched_op = op
                matched_op_pattern = m.group(0)
                break
        if matched_op:
            break

    if not matched_op:
        return None

    isolated = lowered
    isolated = re.sub(re.escape(matched_op_pattern), ' ', isolated)

    for filler in HinglishNormalizer.FILLERS:
        isolated = re.sub(filler, ' ', isolated)

    isolated = WINDOW_CONTROL_STRIP_RE.sub(' ', isolated)
    isolated = re.sub(r'\s+', ' ', isolated).strip()

    from core.universal_window_resolver import UniversalAppNormalizer

    is_current_win = False
    if any(w in isolated for w in [
        "this window", "is window", "iss window", "current window", "active window",
        "focused window", "yeh window", "ye window", "yah window", "isko", "isse",
        "ise", "usko", "usse", "use", "woh", "usey", "this", "current", "active", "window", "yah", "yeh", "ye", "is", "iss"
    ]):
        isolated_without_win = CURRENT_WIN_STRIP_RE.sub(' ', isolated).strip()
        if not isolated_without_win:
            is_current_win = True
        else:
            isolated = isolated_without_win

    if is_current_win or not isolated or UniversalAppNormalizer.is_relative_target(isolated):
        target_app = "current"
    else:
        norm = UniversalAppNormalizer.normalize(isolated)
        clean_isolated = norm.noise_stripped if norm.noise_stripped else isolated
        target_app = APP_MAP.get(clean_isolated, clean_isolated)
        if target_app == clean_isolated:
            for k, v in APP_MAP.items():
                # Word-boundary only: "code" must not match inside "opencode".
                if re.search(r'\b' + re.escape(k) + r'\b', clean_isolated):
                    target_app = v
                    break

    action_name_map = {
        "maximize": "maximize_window",
        "minimize": "minimize_window",
        "restore": "restore_window",
        "focus": "focus_window",
        "close": "close_app",
        "move": "move_window",
        "resize": "resize_window"
    }
    action_name = action_name_map.get(matched_op, "manage_window")
    intent_name = f"WINDOW_{matched_op.upper()}"

    return SemanticAction(
        intent=intent_name,
        service="windows",
        action=action_name,
        query=target_app,
        parameters={
            "app_name": target_app,
            "operation": matched_op
        }
    )


def parse_folder_management(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Extracts folder open and close intents for daily-use and named folders."""
    close_verbs = [r'\bclose\b', r'\bband\s+karo\b', r'\bband\s+kar\s+do\b', r'\bband\s+kardo\b', r'\bband\s+kar\b', r'\bexit\b', r'\bshut\b']
    has_close_verb = any(re.search(v, lowered) for v in close_verbs)

    if has_close_verb:
        if CLOSE_ALL_FOLDERS_RE.search(lowered) or (
            any(w in lowered for w in ("all folder", "saare folder", "sab folder", "all folders", "saare folders", "sab folders", "sabhi folder", "sabhi folders", "open folder", "open folders", "sabhi open folder", "saare open folder", "sab open folder"))
            and any(b in lowered for b in ("band", "close", "exit", "shut"))
        ):
            return SemanticAction(
                intent="FOLDER_CLOSE",
                service="files",
                action="close_folder",
                query="all",
                parameters={"target": "all", "close_all": True, "folder": "all"}
            )

        for canon, aliases in DAILY_FOLDER_MAP.items():
            for alias in aliases:
                pat = rf'\b(?:close\s+(?:the\s+)?{re.escape(alias)}(?:\s+folder)?|{re.escape(alias)}(?:\s+folder)?\s+(?:close|band\s+karo|band\s+kar\s+do|band\s+kardo|band))\b'
                if re.search(pat, lowered):
                    return SemanticAction(
                        intent="FOLDER_CLOSE",
                        service="files",
                        action="close_folder",
                        query=canon,
                        parameters={"target": canon, "close_all": False, "folder": canon}
                    )

        m_close_named = CLOSE_NAMED_FOLDER_RE.search(lowered)
        if m_close_named:
            target_name = (m_close_named.group("name") or m_close_named.group("name2") or "").strip()
            if target_name and target_name not in ("this", "that", "the", "ek", "naya", "new", "all", "saare"):
                return SemanticAction(
                    intent="FOLDER_CLOSE",
                    service="files",
                    action="close_folder",
                    query=target_name,
                    parameters={"target": target_name, "close_all": False, "folder": target_name}
                )

    open_verbs = [r'\bopen\b', r'\bkholo\b', r'\blaunch\b', r'\bopen\s+karo\b', r'\bopen\s+kar\s+do\b']
    has_open_verb = any(re.search(v, lowered) for v in open_verbs)

    # Negative feedback or failure reports must never be parsed as open commands
    if re.search(r'\b(?:nahi\s+hua|nhi\s+hua|open\s+nahi|open\s+nhi|nahi\s+khula|nhi\s+khula|fail|not\s+working|didn\'?t\s+work|galat\s+hua)\b', lowered):
        return None

    if has_open_verb:
        for canon, aliases in DAILY_FOLDER_MAP.items():
            for alias in aliases:
                if len(alias.split()) > 1 or alias in ("startup", "downloads", "download", "documents", "document", "docs", "desktop", "pictures", "picture", "photos", "photo", "images", "videos", "video", "movies", "music", "songs", "recycle bin", "trash", "temp"):
                    pat = rf'\b(?:open\s+(?:the\s+)?{re.escape(alias)}(?:\s+folder)?|{re.escape(alias)}(?:\s+folder)?\s+(?:kholo|open\s+karo|open\s+kar\s+do|open))\b'
                else:
                    pat = rf'\b(?:open\s+(?:the\s+)?{re.escape(alias)}\s+folder|{re.escape(alias)}\s+folder\s+(?:kholo|open\s+karo|open\s+kar\s+do|open))\b'

                if re.search(pat, lowered):
                    return SemanticAction(
                        intent="FOLDER_OPEN",
                        service="files",
                        action="open_folder",
                        query=canon,
                        parameters={"target": canon, "folder": canon}
                    )

        m_open_named = OPEN_NAMED_FOLDER_RE.search(lowered)
        if m_open_named:
            target_name = (m_open_named.group("name") or m_open_named.group("name2") or "").strip()
            if target_name and target_name not in ("this", "that", "the", "ek", "naya", "new", "all", "saare"):
                return SemanticAction(
                    intent="FOLDER_OPEN",
                    service="files",
                    action="open_folder",
                    query=target_name,
                    parameters={"target": target_name, "folder": target_name}
                )

    return None


def parse_app_close(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Handles app closing (e.g. 'close excel', 'excel band karo', 'close chrome', 'microsoft store band karo')."""
    has_close_verb = any(pat.search(lowered) for pat in APP_CLOSE_PATTERNS)
    if not has_close_verb:
        return None

    # Container activity guard: if the utterance targets a website/tab inside a browser, do not close the browser
    # e.g., "chrome wala youtube band kar do", "chrome me youtube band karo", "close youtube in chrome"
    for b_name in ("chrome", "brave", "edge", "firefox", "opera", "vivaldi"):
        if b_name in lowered:
            if any(web in lowered for web in WEB_IDENTITIES) or "tab" in lowered:
                if re.search(rf"\b{b_name}\b\s*(?:{CONTAINED_PREPOSITIONS})\b", lowered) or \
                   re.search(rf"\b(?:{CONTAINED_PREPOSITIONS})\s*{b_name}\b", lowered) or \
                   re.search(rf"\b(?:in|on|from)\s+{b_name}\b", lowered) or \
                   re.search(rf"\b{b_name}\b.*?\b(?:wala|wali|wale|ka|ki|ke|me|mein|in|on)\b", lowered):
                    return None

    # 1. Try WindowsAppResolver extraction
    try:
        from core.windows_app_resolver import get_windows_app_resolver
        win_resolver = get_windows_app_resolver()
        extracted = win_resolver.extract_app_entity_from_text(lowered)
        if extracted:
            win_match, _ = extracted
            if win_match.confidence >= 0.85:
                return SemanticAction(
                    intent="WINDOW_CLOSE",
                    service="windows",
                    action="close_app",
                    query=win_match.canonical_id,
                    parameters={
                        "app_name": win_match.canonical_id,
                        "display_name": win_match.display_name,
                        "operation": "close",
                        "process_names": win_match.process_names,
                    }
                )
    except Exception:
        pass

    from core.apps import get_application_registry
    app_reg = get_application_registry()
    matched_app, _ = app_reg.parse_query(lowered)
    if matched_app:
        return SemanticAction(
            intent="WINDOW_CLOSE",
            service="windows",
            action="close_app",
            query=matched_app.app_id,
            parameters={"app_name": matched_app.app_id, "operation": "close"}
        )

    for app in KNOWN_APPS:
        if app in lowered:
            canonical_name = APP_MAP.get(app, app)
            return SemanticAction(
                intent="WINDOW_CLOSE",
                service="windows",
                action="close_app",
                query=canonical_name,
                parameters={"app_name": canonical_name, "operation": "close"}
            )

    return None


def parse_service_open(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Handles application & service opening."""
    if STATUS_CHECK_EXCLUDE_RE.search(lowered):
        return None

    # Close-guard: an explicit close verb means this is NOT an open request.
    # Prevents "opencode band karo" / "<app> close karo" from being swallowed
    # as OPEN before parse_app_close runs (orchestrator runs open before close).
    if any(pat.search(lowered) for pat in APP_CLOSE_PATTERNS):
        return None

    from core.apps.registry import HINDI_OPEN_VERBS_RE
    has_open_verb = bool(HINDI_OPEN_VERBS_RE.search(lowered)) or any(pat.search(lowered) for pat in COMPILED_OPEN_VERBS)
    if not has_open_verb:
        # Word-boundary match only: substring check ("open" in "opencode")
        # previously misclassified "opencode band karo" as an open request.
        if not any(re.search(r'\b' + re.escape(w) + r'\b', lowered) for w in ["kholo", "open", "launch", "chalao", "chala do", "chala de", "start", "run", "play"]):
            return None

    if any(w in lowered for w in ["gaana", "song", "bajao", "search karke"]):
        return None
    # Priority Check via Normalized ApplicationRegistry
    from core.apps import get_application_registry, get_app_resolver
    app_reg = get_application_registry()
    matched_app, meta = app_reg.parse_query(lowered)
    if not matched_app:
        matched_app, meta = app_reg.parse_query(raw_text.lower())

    if "play" in lowered and not any(w in lowered for w in ["chess", "game"]):
        if not matched_app:
            resolver = get_app_resolver()
            resolved, _ = resolver.resolve_from_query(lowered)
            if not resolved:
                resolved, _ = resolver.resolve_from_query(raw_text.lower())
            if not resolved:
                return None
    if matched_app:
        # If user explicitly requested website, defer to website parser
        if meta.get("is_website"):
            return None
        # If user explicitly requested file, defer to file parser
        if meta.get("is_file"):
            return None
        # If user explicitly requested folder, defer to folder parser
        if meta.get("is_folder"):
            return None

        canonical_id = matched_app.app_id

        # Dual-candidate Ambiguity Gate: If target exists as both application and website, and user didn't specify medium
        from core.apps.aliases import WEBSITE_ALIASES
        cleaned_target = (meta.get("cleaned_target") or canonical_id).strip().lower()
        if (canonical_id in WEBSITE_ALIASES or cleaned_target in WEBSITE_ALIASES) and not meta.get("is_application") and canonical_id != "youtube":
            disp = matched_app.display_name or canonical_id.capitalize()
            return SemanticAction(
                intent=OPEN_APP_INTENT,
                service="app_disambiguation",
                action="clarify_app_or_web",
                query=canonical_id,
                parameters={
                    "app_id": canonical_id,
                    "target": canonical_id,
                    "web_url": WEBSITE_ALIASES.get(canonical_id) or WEBSITE_ALIASES.get(cleaned_target),
                    "display_name": disp,
                    "workflow_type": "APP_WEB_DISAMBIGUATION",
                },
                needs_clarification=True,
                clarification_prompt=f"{disp} application open karun ya website?",
                missing_slot="target_medium",
                confidence=0.95,
            )

        service = "windows"
        action = "launch_app"
        params: Dict[str, Any] = {
            "app_name": canonical_id,
            "entity": canonical_id,
            "display_name": matched_app.display_name,
            "is_new": meta.get("is_new", False),
            "target_type": "application",
            "extracted_entity": meta.get("extracted_entity", canonical_id),
        }

        if canonical_id == "youtube":
            is_new_tab = bool(re.search(r'\b(?:naya\s+tab|naye\s+tab|new\s+tab|another\s+tab|dusra\s+tab|ek\s+aur\s+tab)\b', lowered))
            return SemanticAction(
                intent=OPEN_APP_INTENT,
                service="youtube",
                action="open_youtube",
                query=None,
                parameters={"force_new": is_new_tab}
            )

        return SemanticAction(
            intent=OPEN_APP_INTENT,
            service=service,
            action=action,
            query=canonical_id,
            parameters=params,
            confidence=1.0,
        )


    # AppResolver & WindowsAppResolver priority resolution (e.g. Camera, Calculator, Settings, Microsoft Store, etc.)
    if not meta.get("is_website") and not meta.get("is_file") and not meta.get("is_folder"):
        # 1. Try WindowsAppResolver
        try:
            from core.windows_app_resolver import get_windows_app_resolver
            win_resolver = get_windows_app_resolver()
            extracted = win_resolver.extract_app_entity_from_text(lowered)
            if extracted:
                win_match, _ = extracted
                if win_match.confidence >= 0.85:
                    return SemanticAction(
                        intent=OPEN_APP_INTENT,
                        service="windows",
                        action="launch_app",
                        query=win_match.canonical_id,
                        parameters={
                            "app_name": win_match.canonical_id,
                            "entity": win_match.canonical_id,
                            "display_name": win_match.display_name,
                            "is_new": meta.get("is_new", False),
                            "target_type": "application",
                            "extracted_entity": win_match.canonical_id,
                        },
                        confidence=win_match.confidence,
                    )
        except Exception:
            pass

        from core.apps import get_app_resolver
        resolver = get_app_resolver()
        resolved, _ = resolver.resolve_from_query(lowered)
        if resolved:
            return SemanticAction(
                intent=OPEN_APP_INTENT,
                service="windows",
                action="launch_app",
                query=resolved.app_id,
                parameters={
                    "app_name": resolved.app_id,
                    "entity": resolved.app_id,
                    "display_name": resolved.display_name,
                    "is_new": meta.get("is_new", False),
                    "target_type": "application",
                    "extracted_entity": resolved.app_id,
                },
                confidence=1.0,
            )

    # Dynamic installed app detection or explicit application request fallback
    if not meta.get("is_website") and not meta.get("is_file") and not meta.get("is_folder"):
        cleaned_target = meta.get("cleaned_target", "")
        is_explicit_app = meta.get("is_application", False)
        from core.apps.aliases import WEBSITE_ALIASES
        is_known_web = (cleaned_target in WEB_IDENTITIES) or (cleaned_target in WEBSITE_ALIASES)

        if cleaned_target and (is_explicit_app or not is_known_web):
            from core.apps import get_installed_app_detector
            detector = get_installed_app_detector()
            installed_info = detector.detect(cleaned_target)
            if installed_info and installed_info.is_installed:
                app_id = installed_info.app_id
                disp = installed_info.display_name or app_id.capitalize()
                return SemanticAction(
                    intent=OPEN_APP_INTENT,
                    service="windows",
                    action="launch_app",
                    query=app_id,
                    parameters={
                        "app_name": app_id,
                        "display_name": disp,
                        "is_new": meta.get("is_new", False),
                        "target_type": "application",
                        "extracted_entity": meta.get("extracted_entity", app_id),
                    },
                    confidence=1.0,
                )
            elif is_explicit_app:
                # Explicit application requested by user, but not installed
                return SemanticAction(
                    intent=OPEN_APP_INTENT,
                    service="windows",
                    action="launch_app",
                    query=cleaned_target,
                    parameters={
                        "app_name": cleaned_target,
                        "display_name": cleaned_target.capitalize(),
                        "is_new": meta.get("is_new", False),
                        "not_installed": True,
                        "target_type": "application",
                        "extracted_entity": meta.get("extracted_entity", cleaned_target),
                    },
                    confidence=1.0,
                )

    # 0. Chess Game
    if any(w in lowered for w in ["chess", "chess game"]):
        return SemanticAction(
            intent=OPEN_APP_INTENT,
            service="windows",
            action="launch_app",
            query="chess",
            parameters={"app_name": "chess"},
            confidence=1.0,
        )

    # 1. Settings
    if any(re.search(r'\b' + s + r'\b', lowered) for s in ["settings", "setting", "windows settings", "system settings"]):
        return SemanticAction(
            intent=OPEN_APP_INTENT,
            service="windows",
            action="launch_app",
            query="settings",
            parameters={"app_name": "settings"}
        )

    # 2. Control Panel
    if "control panel" in lowered:
        return SemanticAction(
            intent=OPEN_APP_INTENT,
            service="windows",
            action="launch_app",
            query="control panel",
            parameters={"app_name": "control panel"}
        )

    # 3. Task Manager
    if any(w in lowered for w in ["task manager", "taskmgr"]):
        return SemanticAction(
            intent=OPEN_APP_INTENT,
            service="windows",
            action="launch_app",
            query="task manager",
            parameters={"app_name": "task manager"}
        )

    # 3b. Microsoft Store
    if any(re.search(r'\b' + s + r'\b', lowered) for s in ["microsoft store", "windows store", "ms store", "msstore", "store"]):
        return SemanticAction(
            intent=OPEN_APP_INTENT,
            service="windows",
            action="launch_app",
            query="microsoft store",
            parameters={"app_name": "microsoft store"}
        )

    # 4. YouTube Open
    if any(re.search(pat, lowered) for pat in SERVICE_PATTERNS["youtube"]):
        is_new_tab = bool(re.search(r'\b(?:naya\s+tab|naye\s+tab|new\s+tab|another\s+tab|dusra\s+tab|ek\s+aur\s+tab)\b', lowered))
        return SemanticAction(
            intent=OPEN_APP_INTENT,
            service="youtube",
            action="open_youtube",
            query=None,
            parameters={"force_new": is_new_tab}
        )

    # 5. VLC Open
    if any(re.search(pat, lowered) for pat in SERVICE_PATTERNS["vlc"]):
        return SemanticAction(
            intent=OPEN_APP_INTENT,
            service="windows",
            action="launch_app",
            query="vlc",
            parameters={"app_name": "vlc"}
        )

    # 6. Any other Known Application in KNOWN_APPS fallback
    for app in KNOWN_APPS:
        if re.search(r'\b' + re.escape(app) + r'\b', lowered):
            canonical_name = APP_MAP.get(app, app)
            return SemanticAction(
                intent=OPEN_APP_INTENT,
                service="windows",
                action="launch_app",
                query=canonical_name,
                parameters={"app_name": canonical_name}
            )

    return None


OPEN_FILE_EXPLICIT_RE = re.compile(
    r'^(?:open|kholo|launch|start|run)\s+(?:the\s+)?(.+?\.(?:xlsx|xls|csv|xlsm|docx|doc|pptx|ppt|pdf|txt|py|json|xml|html|zip|rar|log))$',
    re.IGNORECASE
)
REVERSE_OPEN_FILE_RE = re.compile(
    r'^(.+?\.(?:xlsx|xls|csv|xlsm|docx|doc|pptx|ppt|pdf|txt|py|json|xml|html|zip|rar|log))\s+(?:kholo|open|open\s+karo|open\s+kar\s+do|chalao)$',
    re.IGNORECASE
)
EXPLICIT_FILE_PHRASE_RE = re.compile(
    r'^(?:open|kholo)\s+(.+?)\s+file$|^(.+?)\s+file\s+(?:kholo|open|open\s+karo)$',
    re.IGNORECASE
)
# Word order "file kholo <target>" (file noun first, verb middle).
LEADING_FILE_OPEN_RE = re.compile(
    r'^file\s+(?:ko\s+)?(?:kholo|open|open\s+karo|open\s+kar\s+do|chalao)(?:\s+karo|\s+kar\s+do)?\s+(.+)$',
    re.IGNORECASE
)

# File-delete phrasings (Hinglish). Strictly file-scoped: requires either a
# filename with extension or the explicit word "file" — so app-close verbs
# like "chrome hatao" keep routing to WINDOW_CLOSE (parse_app_close runs first).
DELETE_FILE_EXPLICIT_RE = re.compile(
    r'^(?:delete|remove|hatao|hata\s+do|mitao)\s+(?:the\s+)?(.+?\.(?:xlsx|xls|csv|xlsm|docx|doc|pptx|ppt|pdf|txt|py|json|xml|html|zip|rar|log))$',
    re.IGNORECASE
)
REVERSE_DELETE_FILE_RE = re.compile(
    r'^(.+?\.(?:xlsx|xls|csv|xlsm|docx|doc|pptx|ppt|pdf|txt|py|json|xml|html|zip|rar|log))\s+(?:delete\s+karo|delete\s+kar\s+do|remove\s+karo|hatao|hata\s+do|mitao|saaf\s+karo|delete)$',
    re.IGNORECASE
)
EXPLICIT_DELETE_FILE_PHRASE_RE = re.compile(
    r'^(?:delete|remove|hatao)\s+(.+?)\s+file$|^(.+?)\s+file\s+(?:delete\s+karo|delete|remove\s+karo|hatao|hata\s+do)$',
    re.IGNORECASE
)
# Word order "file delete karo <target>" (file noun first, verb middle).
LEADING_FILE_DELETE_RE = re.compile(
    r'^file\s+(?:ko\s+)?(?:delete|remove|hatao)(?:\s+karo|\s+kar\s+do|\s+kardo)?\s+(.+)$',
    re.IGNORECASE
)


def parse_file_open(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Parse explicit requests to open specific files or documents."""
    text_clean = lowered.strip()
    match = OPEN_FILE_EXPLICIT_RE.fullmatch(text_clean)
    filename = ""
    if match:
        filename = match.group(1).strip()
    else:
        rev_match = REVERSE_OPEN_FILE_RE.fullmatch(text_clean)
        if rev_match:
            filename = rev_match.group(1).strip()
        else:
            phrase_match = EXPLICIT_FILE_PHRASE_RE.fullmatch(text_clean)
            if phrase_match:
                filename = (phrase_match.group(1) or phrase_match.group(2) or "").strip()
            else:
                lead_match = LEADING_FILE_OPEN_RE.fullmatch(text_clean)
                if lead_match:
                    filename = (lead_match.group(1) or "").strip()

    if not filename:
        return None

    return SemanticAction(
        intent="OPEN_FILE",
        service="files",
        action="open_file",
        query=filename,
        parameters={"path": filename, "file_name": filename, "target": filename},
        confidence=1.0,
    )


def parse_file_delete(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Parse explicit file-delete requests ("test.txt delete karo", "file delete karo test.txt").

    Destructive: returns the files-plugin DELETE action shape (target only).
    Confirmation/risk gating stays downstream (HIGH tier + ConfirmationManager).
    Runs AFTER parse_app_close so app closes ("chrome hatao") keep priority.
    """
    text_clean = lowered.strip()
    match = DELETE_FILE_EXPLICIT_RE.fullmatch(text_clean)
    filename = ""
    if match:
        filename = match.group(1).strip()
    else:
        rev_match = REVERSE_DELETE_FILE_RE.fullmatch(text_clean)
        if rev_match:
            filename = rev_match.group(1).strip()
        else:
            phrase_match = EXPLICIT_DELETE_FILE_PHRASE_RE.fullmatch(text_clean)
            if phrase_match:
                filename = (phrase_match.group(1) or phrase_match.group(2) or "").strip()
            else:
                lead_match = LEADING_FILE_DELETE_RE.fullmatch(text_clean)
                if lead_match:
                    filename = (lead_match.group(1) or "").strip()

    if not filename:
        return None

    return SemanticAction(
        intent="DELETE_FILE",
        service="files",
        action="delete",
        query=filename,
        parameters={"target": filename, "file_name": filename},
        confidence=0.95,
    )

