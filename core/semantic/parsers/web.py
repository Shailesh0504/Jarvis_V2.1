# core/semantic/parsers/web.py
"""Web search, product discovery, known website navigation, and network share parser."""

import re
from typing import Any, Dict, Optional, Tuple

from core.semantic.models import SemanticAction

# --- Precompiled Patterns ---
NEW_TAB_RE = re.compile(r'\b(?:naya\s+tab|naye\s+tab|new\s+tab|another\s+tab|dusra\s+tab|ek\s+aur\s+tab)\b', re.IGNORECASE)
CHATGPT_RE = re.compile(r'\b(?:chat\s*gpt|chatgpt|chart\s*gpt)\b', re.IGNORECASE)
DHAN_RE = re.compile(r'\b(?:dhan|dhan\s+app|dhan\s+trading)\b', re.IGNORECASE)
UNC_SHARE_MATCH_RE = re.compile(
    r"\s*(?:start|open|launch|kholo|explorer(?:\.exe)?)\s+['\"]?([\\/]{2,}[^'\"]+)['\"]?\s*",
    re.IGNORECASE
)
UNC_SHARE_VALID_RE = re.compile(r"\\\\[^\\/:*?\"<>|\s]+\\[^\\/:*?\"<>|]+(?:\\[^:*?\"<>|]*)*")

STATUS_QUESTION_RE = re.compile(r'\b(?:hai\s+kya|open\s+hai|chalu\s+hai|running\s+hai|chal\s+raha\s+hai|khula\s+hai)\b', re.IGNORECASE)

# Explicit browser container ("edge browser me", "brave me", "chrome par").
# An explicit container must ALWAYS win over defaults/preferences downstream.
BROWSER_CONTAINER_RE = re.compile(
    r"\b(chrome|brave|edge|firefox|opera)\b(?:\s+browser)?", re.IGNORECASE)
BROWSER_DISPLAY = {"chrome": "Chrome", "brave": "Brave", "edge": "Edge",
                   "firefox": "Firefox", "opera": "Opera"}


def extract_browser_container(lowered: str) -> str:
    """Returns canonical browser name when explicitly named, else ''."""
    m = BROWSER_CONTAINER_RE.search(lowered or "")
    return m.group(1).lower() if m else ""
GENERIC_WEB_PATTERNS = [
    re.compile(r"^(?:open|launch|visit|browse)\s+(.+?)(?:\s+(?:ka|mein|in)?\s*(?:naya|naye|new|another|dusra)\s+tab)?(?:\s+(?:website|site))?$", re.IGNORECASE),
    re.compile(r"^(?:open|launch|visit|browse)\s+(?:(?:a\s+)?new\s+tab\s+(?:of|for|with)\s+)(.+?)(?:\s+(?:website|site))?$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+(?:ka\s+)?(?:naya|naye|new|another|dusra)\s+tab(?:\s+mein)?\s+(?:kholo|open|open\s+karo)$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+(?:website|site)\s+(?:kholo|open\s+karo)$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+(?:kholo|open\s+karo)$", re.IGNORECASE),
]
TARGET_CLEANUP_RE = re.compile(
    r"\b(?:official|website|site|portal|webpage|page|please|zara|yaar|bhai|jarvis|ka|ki|ke|ko|par|pe|me|mein|in|naya|naye|new|tab|another|dusra|application|app|software|program)\b",
    re.IGNORECASE
)
BLOCKED_TARGETS = {"file", "folder", "document", "photo", "image", "settings", "app", "application", "program"}
CHAT_CHART_RE = re.compile(r"\b(?:chat|chart)\b", re.IGNORECASE)

RANGE_PRICE_RE = re.compile(
    r'\b(?:between|beech\s+mein)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)?|\d+k|\d+\s*(?:lakh|lac))\s*(?:and|aur|to|-)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)?|\d+k|\d+\s*(?:lakh|lac))\b',
    re.IGNORECASE
)
MAX_PRICE_RE1 = re.compile(r'\b(?:under|below|less\s+than)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)?|\d+k|\d+\s*(?:lakh|lac))\b', re.IGNORECASE)
MAX_PRICE_RE2 = re.compile(r'\b(\d+(?:,\d+)?|\d+k|\d+\s*(?:lakh|lac))\s*(?:ke\s+andar|ke\s+niche|se\s+kam|tak)\b', re.IGNORECASE)
MIN_PRICE_RE1 = re.compile(r'\b(?:above|over|more\s+than)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)?|\d+k|\d+\s*(?:lakh|lac))\b', re.IGNORECASE)
MIN_PRICE_RE2 = re.compile(r'\b(\d+(?:,\d+)?|\d+k|\d+\s*(?:lakh|lac))\s*(?:se\s+jyada|se\s+upar|se\s+zyada)\b', re.IGNORECASE)

PRODUCT_VERB_RE = re.compile(
    r'\b(?:dikhao|dekhao|dikhana|dikhaye|dikhado|dikha\s+do|dikha\s+de|dikha|dekho|dekhna|search\s+karo|search\s+kar\s+do|search\s+kar|search\s+kijiye|search|dhoondo|dhundo|dhoond\s+do|dhund\s+do|khojo|find\s+karo|find|show\s+me|show|display|look\s+for|search\s+for|kholo|open\s+karo|open|jao|chalo|navigate)\b',
    re.IGNORECASE
)
PRODUCT_FILLER_RE = re.compile(
    r'\b(?:mujhe|mujhko|humko|humein|mere\s+liye|zara|thoda|thodi|please|jarvis|ek|kuch|koi|bhai|yaar|na|toh|to|boss)\b',
    re.IGNORECASE
)
PRODUCT_INTENT_RE = re.compile(
    r'\b(?:lena\s+hai|chahiye|khareedna\s+hai|dekhna\s+hai|khareedo|buy)\b',
    re.IGNORECASE
)

COMPOUND_SPLIT_RE = re.compile(r'\b(?:to|toh|so)\s+', re.IGNORECASE)
PREFIX_NORM_RE = re.compile(r'^(?:mujhe|mujhko|humko|humein|mere\s+liye|please|zara|yaar|bhai|jarvis)\s+', re.IGNORECASE)

ON_SITE_RE = re.compile(r'^(?:on|in|at)\s+([a-zA-Z0-9.-]+(?:\s+(?:in|india))?)\s+(?:show|display|find|search(?:\s+for)?|dikhao|dekho)?\s*(.+)$', re.IGNORECASE)
ENG_SITE_RE = re.compile(r'^(?:show\s+me|show|display|search\s+for|search|find|look\s+for)\s+(.+?)\s+(?:on|in|at)\s+([a-zA-Z0-9.-]+(?:\s+(?:in|india))?)$', re.IGNORECASE)
HI_SITE_FIRST_RE = re.compile(r'^([a-zA-Z0-9.-]+(?:\s+(?:in|india))?)\s+(?:pe|par|me|mein|ke\s+upar)\s+(.+)$', re.IGNORECASE)
HI_SITE_LAST_RE = re.compile(r'^(.+?)\s+([a-zA-Z0-9.-]+(?:\s+(?:in|india))?)\s+(?:pe|par|me|mein)(?:\s+(?:dikhao|dekhao|search\s+karo|dhoondo|dhundo|find\s+karo|kholo|open))?$', re.IGNORECASE)

SEARCH_TRIGGER_PATTERNS = [
    re.compile(r'\b(?:dikhao|dekhao|dikhana|dikhaye|dikhado|dikha\s+do|dikha\s+de|dekho|dekhna)\b', re.IGNORECASE),
    re.compile(r'\b(?:search|dhoondo|dhundo|dhoond|dhund|khojo|find|show|display|browse|buy|khareedo)\b', re.IGNORECASE),
    re.compile(r'\b(?:chahiye|lena\s+hai|khareedna\s+hai|price|ke\s+andar|under|below|se\s+upar|above)\b', re.IGNORECASE)
]

WEB_SEARCH_RE = re.compile(
    r"(?:search\s+(.+)"
    r"|(.+?)\s+search\s+(?:karo|kar\s+do|kijiye)(?:\s+(.+))?"
    r"|(?:google|bing)\s+search\s+(?:karo\s+)?(.+)"
    r"|(?:google|bing)\s+(?:par|pe|mein\s+)?(.+?)\s+search\s+karo)",
    re.IGNORECASE
)

SYSTEM_NON_SITES = {
    "desktop", "folder", "file", "screen", "pc", "laptop", "computer",
    "system", "windows", "tab", "tabs", "browser", "taskbar",
    "short", "detail", "brief", "vistaar", "hindi", "english", "baare",
    "iska", "isko", "usko", "ye", "yeh", "woh", "wo", "kuch", "apne"
}

EXCLUDED_PRODUCT_QUERIES = {
    "batao", "samjhao", "bolo", "kaho", "kya", "kyun", "kaise", "bataiye", "explain", "tell", "say"
}


def parse_price_number(text: str) -> Optional[int]:
    """Extracts integer value from currency representations like '50k', '1.5 lakh', '15,000'."""
    s = text.lower().strip().replace(",", "").replace("₹", "").replace("rs.", "").replace("rs", "").strip()
    try:
        if s.endswith("k"):
            return int(float(s[:-1]) * 1000)
        if "lakh" in s or "lac" in s:
            num = re.sub(r"[^\d.]", "", s)
            return int(float(num) * 100000)
        return int(float(s))
    except Exception:
        return None


def extract_price_filters(text: str) -> Tuple[str, Dict[str, Any]]:
    """Extracts min_price and max_price filters and returns cleaned text."""
    filters = {}
    cleaned = text

    m_range = RANGE_PRICE_RE.search(cleaned)
    if m_range:
        v1 = parse_price_number(m_range.group(1))
        v2 = parse_price_number(m_range.group(2))
        if v1 is not None and v2 is not None:
            filters["min_price"] = min(v1, v2)
            filters["max_price"] = max(v1, v2)
            cleaned = cleaned[:m_range.start()] + " " + cleaned[m_range.end():]

    m_max1 = MAX_PRICE_RE1.search(cleaned)
    if m_max1:
        val = parse_price_number(m_max1.group(1))
        if val is not None:
            filters["max_price"] = val
            cleaned = cleaned[:m_max1.start()] + " " + cleaned[m_max1.end():]

    m_max2 = MAX_PRICE_RE2.search(cleaned)
    if m_max2:
        val = parse_price_number(m_max2.group(1))
        if val is not None:
            filters["max_price"] = val
            cleaned = cleaned[:m_max2.start()] + " " + cleaned[m_max2.end():]

    m_min1 = MIN_PRICE_RE1.search(cleaned)
    if m_min1:
        val = parse_price_number(m_min1.group(1))
        if val is not None:
            filters["min_price"] = val
            cleaned = cleaned[:m_min1.start()] + " " + cleaned[m_min1.end():]

    m_min2 = MIN_PRICE_RE2.search(cleaned)
    if m_min2:
        val = parse_price_number(m_min2.group(1))
        if val is not None:
            filters["min_price"] = val
            cleaned = cleaned[:m_min2.start()] + " " + cleaned[m_min2.end():]

    return cleaned, filters


def clean_product_query(text: str) -> str:
    """Removes search verbs, fillers, and intent connectors from product query."""
    q = text.strip()
    q = PRODUCT_VERB_RE.sub(' ', q)
    q = PRODUCT_FILLER_RE.sub(' ', q)
    q = PRODUCT_INTENT_RE.sub(' ', q)
    return re.sub(r'\s+', ' ', q).strip(' ,.?!:;')


def parse_network_share(raw_text: str) -> Optional[SemanticAction]:
    """Parse commands such as ``start \\\\server\\share`` safely."""
    match = UNC_SHARE_MATCH_RE.fullmatch(raw_text)
    if not match:
        return None

    candidate = match.group(1).strip().replace("/", "\\")
    unc_path = "\\\\" + candidate.lstrip("\\")
    if not UNC_SHARE_VALID_RE.fullmatch(unc_path):
        return None

    return SemanticAction(
        intent="OPEN_NETWORK_SHARE",
        service="windows",
        action="open_path",
        parameters={"path": unc_path},
    )


def parse_known_website(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Resolve high-confidence website aliases, including common STT variants and new tab requests."""
    is_new_tab = bool(NEW_TAB_RE.search(lowered))

    if CHATGPT_RE.search(lowered) and any(w in lowered for w in ["open", "launch", "kholo", "visit", "tab"]):
        params = {"url": "https://chatgpt.com", "site": "chatgpt"}
        _container = extract_browser_container(lowered)
        if _container:
            params["container"] = _container
        if is_new_tab:
            params["force_new"] = True
        return SemanticAction(
            intent="OPEN_WEBSITE",
            service="browser",
            action="open_url",
            query="chatgpt",
            parameters=params,
            confidence=1.0,
        )

    if DHAN_RE.search(lowered) and any(w in lowered for w in ["open", "launch", "kholo", "visit", "tab"]):
        params = {"url": "https://dhan.co/", "site": "dhan"}
        _container = extract_browser_container(lowered)
        if _container:
            params["container"] = _container
        if is_new_tab:
            params["force_new"] = True
        return SemanticAction(
            intent="OPEN_WEBSITE",
            service="browser",
            action="open_url",
            parameters=params,
            confidence=1.0,
        )

    return None


def parse_generic_website_open(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Treat an unknown simple open-target as a website brand, not vague chat."""
    if STATUS_QUESTION_RE.search(lowered) or "?" in raw_text:
        return None

    is_new_tab = bool(NEW_TAB_RE.search(lowered))

    target = ""
    for pattern in GENERIC_WEB_PATTERNS:
        match = pattern.fullmatch(lowered)
        if match:
            target = match.group(1).strip(" .?!")
            break

    if not target:
        return None

    target = TARGET_CLEANUP_RE.sub(" ", target)
    target = re.sub(r"\s+", " ", target).strip()

    if (not target or target in BLOCKED_TARGETS or any(char in target for char in ("\\", "/"))
            or CHAT_CHART_RE.search(target)):
        return None

    # Intent Priority Invariant:
    # A known desktop application name must NOT be treated as a generic website
    # UNLESS the user explicitly requested a website/URL or used a domain extension.
    from core.apps import get_application_registry
    app_reg = get_application_registry()
    matched_app, meta = app_reg.parse_query(lowered)
    is_explicit_website = meta.get("is_website", False) or any(
        w in lowered for w in ["website", "site", "web", "url", ".com", ".org", ".net", ".in", ".co"]
    )
    if matched_app and not is_explicit_website:
        return None

    if meta.get("is_application") and not is_explicit_website:
        return None

    if app_reg.find_by_alias(target) and not is_explicit_website:
        return None

    from core.apps import get_installed_app_detector
    detector = get_installed_app_detector()
    if not is_explicit_website and (detector.is_installed(target) or detector.detect(target) is not None):
        return None

    # Defer file targets (e.g. myfile.xlsx, document.docx) to file handling
    from core.apps.registry import FILE_EXT_RE
    if FILE_EXT_RE.search(target) and not is_explicit_website:
        return None

    params = {"site": target}
    _container = extract_browser_container(lowered)
    if _container:
        params["container"] = _container
        # Drop the container mention from the site target ("xyz edge me kholo" -> "xyz").
        # If nothing remains ("edge kholo"), it is an APP open — defer to app parsers.
        target = re.sub(rf"\b{_container}\b(?:\s+browser)?", " ", target, flags=re.IGNORECASE)
        target = re.sub(r"\s+", " ", target).strip(" .?!")
        if not target:
            return None
        params["site"] = target
    if is_new_tab:
        params["force_new"] = True

    return SemanticAction(
        intent="OPEN_WEBSITE",
        service="browser",
        action="open_website",
        query=target,
        parameters=params,
        confidence=0.90
    )


def parse_product_discovery_and_web_search(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """
    Parses web search and product discovery commands targeting specific sites
    or generic web search with optional price constraints from Hindi, Hinglish, and English.
    """
    m_compound = COMPOUND_SPLIT_RE.split(raw_text)
    text_to_parse = m_compound[-1].strip() if len(m_compound) > 1 else raw_text.strip()
    text_to_parse = PREFIX_NORM_RE.sub('', text_to_parse).strip()

    site = ""
    raw_query_part = ""

    # 1. "on/in/at <site> [show/search/find] <query>"
    m_on_site = ON_SITE_RE.match(text_to_parse)
    if m_on_site:
        cand_site = m_on_site.group(1).strip()
        if cand_site.lower() not in SYSTEM_NON_SITES:
            site = cand_site
            raw_query_part = m_on_site.group(2).strip()

    # 2. "[show/display/search/find] <query> on/in/at <site>"
    if not site:
        m_eng = ENG_SITE_RE.match(text_to_parse)
        if m_eng:
            cand_site = m_eng.group(2).strip()
            if cand_site.lower() not in SYSTEM_NON_SITES:
                site = cand_site
                raw_query_part = m_eng.group(1).strip()

    # 3. "<site> pe/par/me/mein [query] [dikhao/search karo/dhoondo]"
    if not site:
        m_hi_site_first = HI_SITE_FIRST_RE.match(text_to_parse)
        if m_hi_site_first:
            cand_site = m_hi_site_first.group(1).strip()
            if cand_site.lower() not in SYSTEM_NON_SITES:
                site = cand_site
                raw_query_part = m_hi_site_first.group(2).strip()

    # 4. "<query> <site> pe/par/me/mein [dikhao/search karo]"
    if not site:
        m_hi_site_last = HI_SITE_LAST_RE.match(text_to_parse)
        if m_hi_site_last:
            cand_site = m_hi_site_last.group(2).strip()
            if cand_site.lower() not in SYSTEM_NON_SITES:
                site = cand_site
                raw_query_part = m_hi_site_last.group(1).strip()

    if not site:
        return None

    site_clean = site.lower().strip()
    if site_clean in ("amazon in", "amazon india"):
        site_clean = "amazon"

    query_without_filters, filters = extract_price_filters(raw_query_part)
    clean_query = clean_product_query(query_without_filters)

    if clean_query.lower() in EXCLUDED_PRODUCT_QUERIES:
        return None

    try:
        from plugins.browser.search_adapters import SearchSiteRegistry
        is_known_site = (SearchSiteRegistry.get_adapter(site_clean) is not None) or ("." in site_clean)
    except Exception:
        is_known_site = "." in site_clean

    has_search_trigger = any(pat.search(text_to_parse) for pat in SEARCH_TRIGGER_PATTERNS)
    if not is_known_site and not has_search_trigger:
        return None

    if not clean_query:
        if any(w in raw_query_part for w in ["open", "kholo", "jao", "chalo"]):
            return SemanticAction(
                intent="OPEN_WEBSITE",
                service="browser",
                action="open_website",
                parameters={"site": site_clean},
                confidence=0.9
            )
        return None

    params = {
        "site": site_clean,
        "query": clean_query,
        "filters": filters
    }
    if filters:
        params.update(filters)

    return SemanticAction(
        intent="WEB_SEARCH",
        service="browser",
        action="search_website",
        query=clean_query,
        parameters=params,
        confidence=1.0
    )


def parse_generic_web_search(lowered: str) -> Optional[SemanticAction]:
    """Fallback parser for direct search queries like 'search python tutorials'."""
    web_search = WEB_SEARCH_RE.fullmatch(lowered)
    if web_search:
        groups = [web_search.group(i) for i in (3, 4, 5, 1)]
        query = next((g.strip() for g in groups if g and g.strip()), "")
        if not query:
            fallback_q = (web_search.group(2) or "").strip()
            fallback_q = re.sub(r"^(?:google|bing)\s+(?:par|pe|mein\s+)?", "", fallback_q, flags=re.IGNORECASE).strip()
            query = fallback_q
        query = re.sub(r"^(?:karo|kar\s+do|kijiye)\s+", "", query, flags=re.IGNORECASE).strip()
        if query and "youtube" not in query and query.lower() not in ("kholo", "khol", "open", "karo"):
            return SemanticAction(
                intent="SEARCH_WEB", service="browser", action="search_google",
                query=query, parameters={"query": query}, confidence=1.0,
            )
    return None
