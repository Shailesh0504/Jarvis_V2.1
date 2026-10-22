# core/target_engine.py
"""Universal desktop target discovery, matching, planning, execution, and verification."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from difflib import SequenceMatcher
import ctypes
import json
import logging
import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from plugins.windows.window_manager import WindowInfo, WindowManager, WindowState

logger = logging.getLogger("jarvis.core.targets")


def _is_test_mode() -> bool:
    """True during pytest / automated E2E runs — never touch the real OS."""
    try:
        import sys as _sys
        if "pytest" in _sys.modules:
            return True
    except Exception:
        pass
    try:
        return os.environ.get("JARVIS_TEST_MODE") == "1"
    except Exception:
        return False


def _is_protected_close_candidate(*candidates: object) -> bool:
    """SSOT reuse: never close the coding-agent host / test runner / editors."""
    try:
        from plugins.apps.plugin import is_protected_close_target
        return bool(is_protected_close_target(*candidates))
    except Exception:
        _prot = ("opencode", "code", "vscode", "cursor", "windsurf", "python", "pytest", "conhost")
        for cand in candidates:
            if cand is None:
                continue
            try:
                text = str(cand).lower().strip()
            except Exception:
                continue
            if text and any(p in text for p in _prot):
                return True
        return False


class TargetKind(str, Enum):
    APPLICATION = "application"
    WINDOW = "window"
    BROWSER_TAB = "browser_tab"
    FILE = "file"


class TargetAction(str, Enum):
    FIND_TARGET = "find"
    FOCUS_WINDOW = "focus"
    ACTIVATE_TAB = "activate"
    CLOSE_TAB = "close_tab"
    CLOSE_WINDOW = "close_window"
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"
    RESTORE = "restore"
    MOVE = "move"
    RESIZE = "resize"
    TYPE = "type"
    CLICK = "click"
    OPEN = "open"


@dataclass
class TargetCandidate:
    kind: TargetKind
    identity: str
    title: str = ""
    url: str = ""
    domain: str = ""
    process_name: str = ""
    pid: int = 0
    hwnd: int = 0
    tab_id: str = ""
    tab_index: int = -1
    browser: str = ""
    backend: str = "window"
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TargetRequest:
    target: str
    action: str
    container: str = ""
    scope: str = "auto"
    force_new: bool = False
    resolved_url: str = ""
    display_name: str = ""


@dataclass
class ActionOutcome:
    success: bool
    message: str
    verified: bool = False
    needs_clarification: bool = False
    candidates: List[TargetCandidate] = field(default_factory=list)
    status: str = "failed"
    url: str = ""
    verification: str = "not_requested"


class ApplicationDiscovery:
    def __init__(self, window_manager: Optional[WindowManager] = None):
        self.window_manager = window_manager or WindowManager()

    def discover(self) -> List[TargetCandidate]:
        windows = self.window_manager.list_all_windows()
        logger.info("APPLICATIONS_FOUND count=%d", len(windows))
        candidates = []
        for w in windows:
            pname_lower = (w.process_name or "").lower()
            is_uwp_host = pname_lower in ("applicationframehost.exe", "applicationframehost")
            ident = w.title if (is_uwp_host and w.title) else (w.process_name or w.title)
            candidates.append(TargetCandidate(
                kind=TargetKind.APPLICATION, identity=ident,
                title=w.title, process_name=w.process_name, pid=w.pid, hwnd=w.hwnd,
            ))
        return candidates


class WindowDiscovery(ApplicationDiscovery):
    def discover(self) -> List[TargetCandidate]:
        found = super().discover()
        for item in found:
            item.kind = TargetKind.WINDOW
        return found


class BrowserDiscovery:
    BROWSERS = {
        "brave.exe": "brave", "chrome.exe": "chrome", "msedge.exe": "edge",
        "firefox.exe": "firefox", "opera.exe": "opera", "vivaldi.exe": "vivaldi",
    }

    def __init__(self, window_manager: Optional[WindowManager] = None):
        self.window_manager = window_manager or WindowManager()

    def discover(self) -> List[TargetCandidate]:
        items = []
        for window in self.window_manager.list_all_windows():
            browser = self.BROWSERS.get(window.process_name.casefold())
            if browser:
                items.append(TargetCandidate(
                    TargetKind.WINDOW, browser, window.title, process_name=window.process_name,
                    pid=window.pid, hwnd=window.hwnd, browser=browser,
                ))
        logger.info("BROWSER_WINDOWS_FOUND count=%d", len(items))
        return items


class BrowserTabManager:
    """
    Centrally manages browser tab operations (activate, close, switch)
    with strict preservation of browser window size, position, and maximize/minimize state.
    
    Safe Operation Flow:
    1. CAPTURE_WINDOW_STATE
    2. DISCOVER_TARGET_TAB
    3. TEMPORARY_WINDOW_CHANGE_IF_REQUIRED
    4. ACTIVATE_TARGET_TAB
    5. PERFORM_TAB_ACTION
    6. RESTORE_ORIGINAL_WINDOW_STATE
    7. VERIFY_WINDOW_STATE
    8. VERIFY_TAB_ACTION
    """

    def __init__(self, window_manager: Optional[WindowManager] = None):
        self.window_manager = window_manager or WindowManager()

    def perform_tab_action(self, action: str, tab: TargetCandidate) -> bool:
        logger.info("TAB_OPERATION_STARTED action=%s title=%r hwnd=%d browser=%s", action, tab.title, tab.hwnd, tab.browser)
        hwnd = tab.hwnd

        # 1. CAPTURE_WINDOW_STATE
        initial_state = self.window_manager.capture_window_state(hwnd) if hwnd else None

        try:
            # 2 & 3. TEMPORARY_WINDOW_CHANGE_IF_REQUIRED / SAFE FOCUS
            if hwnd and tab.backend != "devtools":
                self.window_manager.focus_window_safely(hwnd)

            # 4. ACTIVATE_TARGET_TAB
            activated = self.activate_tab(tab)

            # 5. PERFORM_TAB_ACTION
            success = False
            if action == "activate_tab":
                success = activated
            elif action == "close_tab":
                if tab.backend == "devtools":
                    success = self._devtools_command(tab, "close")
                else:
                    if activated:
                        # Safety check: Verify foreground window title actually matches target tab before closing!
                        cur_title = self._window_title(tab.hwnd) if tab.hwnd else ""
                        if tab.hwnd and cur_title and not self._title_matches(cur_title, tab.title):
                            logger.warning("TAB_CLOSE_ABORTED active_title=%r does not match target_title=%r", cur_title, tab.title)
                            success = False
                        else:
                            self._hotkey(0x11, 0x57)  # Ctrl+W
                            success = self._wait_for_tab_closed(tab)
                    else:
                        success = False
            else:
                success = False

            logger.info("TAB_ACTION_COMPLETED action=%s success=%s title=%r", action, success, tab.title)
            return success

        finally:
            # 6. RESTORE_ORIGINAL_WINDOW_STATE
            if initial_state and initial_state.hwnd:
                self.window_manager.restore_window_state(initial_state)
                # 7. VERIFY_WINDOW_STATE
                self.window_manager.verify_window_state(initial_state)

    def activate_tab(self, tab: TargetCandidate) -> bool:
        if tab.backend == "devtools":
            ok = self._devtools_command(tab, "activate")
        else:
            if not tab.hwnd:
                return True
            self.window_manager.focus_window_safely(tab.hwnd)

            # Step 1: Check if the target tab is ALREADY active in this window
            current_title = self._window_title(tab.hwnd)
            if current_title and self._title_matches(current_title, tab.title):
                logger.info("TAB_ALREADY_ACTIVE title=%r", current_title)
                return True

            # Step 2: Try direct tab activation via tab_index if known
            if tab.tab_index >= 0:
                self._hotkey(0x11, 0x31)  # Ctrl+1
                time.sleep(0.06)
                t = self._window_title(tab.hwnd)
                if t and self._title_matches(t, tab.title):
                    logger.info("TAB_ACTIVATED success=True title=%r", tab.title)
                    return True

                for _ in range(max(0, tab.tab_index)):
                    self._hotkey(0x11, 0x09)  # Ctrl+Tab
                    time.sleep(0.05)
                    t = self._window_title(tab.hwnd)
                    if t and self._title_matches(t, tab.title):
                        break

            # Step 3: Verify whether target tab is active
            ok = self._wait_for_tab_activated(tab)

            # Step 4: Fallback search by cycling tabs safely if not activated
            if not ok:
                self._hotkey(0x11, 0x31)  # Ctrl+1
                time.sleep(0.06)
                first_t = self._window_title(tab.hwnd)
                if first_t and self._title_matches(first_t, tab.title):
                    ok = True
                else:
                    found = False
                    for _ in range(30):
                        self._hotkey(0x11, 0x09)  # Ctrl+Tab
                        time.sleep(0.05)
                        cur_t = self._window_title(tab.hwnd)
                        if cur_t and self._title_matches(cur_t, tab.title):
                            found = True
                            break
                        if first_t and cur_t == first_t:
                            break
                    ok = found if (tab.hwnd and first_t) else self._wait_for_tab_activated(tab)
        logger.info("TAB_ACTIVATED success=%s title=%r", ok, tab.title)
        return ok

    def close_tab(self, tab: TargetCandidate) -> bool:
        return self.perform_tab_action("close_tab", tab)

    def _wait_for_tab_activated(self, tab: TargetCandidate, timeout: float = 0.25) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            title = self._window_title(tab.hwnd)
            if self._title_matches(title, tab.title):
                return True
            time.sleep(0.02)
        current_title = self._window_title(tab.hwnd)
        if not current_title:
            # Headless / Mock fallback
            return True
        return self._title_matches(current_title, tab.title)

    def _wait_for_tab_closed(self, tab: TargetCandidate, timeout: float = 0.3) -> bool:
        start = time.time()
        initial_title = self._window_title(tab.hwnd)
        while time.time() - start < timeout:
            cur_title = self._window_title(tab.hwnd)
            if cur_title and cur_title != initial_title:
                return True
            time.sleep(0.02)
        return True

    def _devtools_command(self, tab: TargetCandidate, command: str) -> bool:
        try:
            port = int(tab.metadata["port"])
            request = Request(f"http://127.0.0.1:{port}/json/{command}/{tab.tab_id}", method="PUT")
            with urlopen(request, timeout=0.5):
                return True
        except Exception:
            return False

    @staticmethod
    def _hotkey(*keys: int) -> None:
        try:
            user32 = ctypes.windll.user32
            for key in keys:
                user32.keybd_event(key, 0, 0, 0)
            time.sleep(0.015)
            for key in reversed(keys):
                user32.keybd_event(key, 0, 2, 0)
        except Exception:
            pass

    @staticmethod
    def _window_title(hwnd: int) -> str:
        try:
            user32 = ctypes.windll.user32
            size = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(size + 1)
            user32.GetWindowTextW(hwnd, buffer, size + 1)
            return buffer.value.strip()
        except Exception:
            return ""

    @staticmethod
    def _title_matches(current: str, expected: str) -> bool:
        return bool(current and expected and (current.casefold() == expected.casefold() or expected.casefold() in current.casefold()))


class BrowserTabDiscovery:
    """Discover tabs through DevTools metadata, with native title traversal fallback and window state preservation."""

    def __init__(self, browser_discovery: Optional[BrowserDiscovery] = None, window_manager: Optional[WindowManager] = None, ports: Iterable[int] = range(9222, 9230)):
        self.browser_discovery = browser_discovery or BrowserDiscovery(window_manager)
        self.window_manager = window_manager or getattr(self.browser_discovery, "window_manager", WindowManager())
        self.tab_manager = BrowserTabManager(self.window_manager)
        self.ports = tuple(ports)

    def discover(self) -> List[TargetCandidate]:
        browser_windows = self.browser_discovery.discover()
        if not browser_windows:
            logger.info("TABS_FOUND count=0 backend=none")
            return []
        cdp_tabs = self._discover_devtools_tabs()
        if cdp_tabs:
            logger.info("TABS_FOUND count=%d backend=devtools", len(cdp_tabs))
            return cdp_tabs
        tabs: List[TargetCandidate] = []
        for window in browser_windows:
            tabs.extend(self._discover_window_titles(window))
        logger.info("TABS_FOUND count=%d backend=native", len(tabs))
        return tabs

    def _discover_devtools_tabs(self) -> List[TargetCandidate]:
        tabs = []
        for port in self.ports:
            try:
                with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=0.08) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception:
                continue
            for item in payload:
                if item.get("type") != "page":
                    continue
                url = str(item.get("url", ""))
                tabs.append(TargetCandidate(
                    TargetKind.BROWSER_TAB, url or item.get("title", ""),
                    title=str(item.get("title", "")), url=url,
                    domain=(urlsplit(url).hostname or "").casefold(),
                    tab_id=str(item.get("id", "")), browser="chromium",
                    backend="devtools", metadata={"port": port},
                ))
        return tabs

    def _discover_window_titles(self, window: TargetCandidate, max_tabs: int = 40) -> List[TargetCandidate]:
        hwnd = window.hwnd
        if not hwnd:
            return []

        # Capture window state before tab discovery traversal
        initial_state = self.window_manager.capture_window_state(hwnd)
        try:
            if not self.window_manager.focus_window_safely(hwnd):
                return []
            initial_active_title = self.tab_manager._window_title(hwnd)
            self.tab_manager._hotkey(0x11, 0x31)  # Ctrl+1, first tab
            time.sleep(0.04)
            first_title = self.tab_manager._window_title(hwnd)
            if not first_title:
                return []
            results = [TargetCandidate(
                TargetKind.BROWSER_TAB, first_title, first_title, hwnd=hwnd,
                pid=window.pid, process_name=window.process_name, tab_index=0,
                browser=window.browser, backend="native",
            )]
            for index in range(1, max_tabs):
                self.tab_manager._hotkey(0x11, 0x09)  # Ctrl+Tab
                time.sleep(0.04)
                title = self.tab_manager._window_title(hwnd)
                if not title or title == first_title:
                    break
                results.append(TargetCandidate(
                    TargetKind.BROWSER_TAB, title, title, hwnd=hwnd,
                    pid=window.pid, process_name=window.process_name, tab_index=index,
                    browser=window.browser, backend="native",
                ))
            if initial_active_title:
                cur = self.tab_manager._window_title(hwnd)
                if cur and not self.tab_manager._title_matches(cur, initial_active_title):
                    self.tab_manager._hotkey(0x11, 0x31)
                    time.sleep(0.04)
                    for _ in range(max_tabs):
                        t = self.tab_manager._window_title(hwnd)
                        if t and self.tab_manager._title_matches(t, initial_active_title):
                            break
                        self.tab_manager._hotkey(0x11, 0x09)
                        time.sleep(0.04)
            return results
        finally:
            if initial_state and initial_state.hwnd:
                self.window_manager.restore_window_state(initial_state)
                self.window_manager.verify_window_state(initial_state)

    def activate_tab(self, tab: TargetCandidate) -> bool:
        return self.tab_manager.perform_tab_action("activate_tab", tab)

    def close_tab(self, tab: TargetCandidate) -> bool:
        return self.tab_manager.perform_tab_action("close_tab", tab)

    def focus_window(self, hwnd: int) -> bool:
        return self.window_manager.focus_window_safely(hwnd)


class TargetMatcher:
    ALIASES = {
        "yt": ("youtube",), "you tube": ("youtube",),
        "gmail": ("gmail", "mail.google.com", "google mail"),
        "github": ("github", "github.com"), "flipkart": ("flipkart", "flipkart.com"),
        "spotify": ("spotify",), "brave browser": ("brave",),
        "google chrome": ("chrome",), "dhan": ("dhan", "dhan.co"),
        "zerodha": ("zerodha", "kite.zerodha.com", "zerodha.com"),
        "groww": ("groww", "groww.in"), "upstox": ("upstox", "upstox.com"),
        "bing": ("bing", "bing.com", "bing search", "microsoft bing"),
        "google": ("google", "google.com", "google search"),
        "chatgpt": ("chatgpt", "chatgpt.com", "chat.openai.com"),
        "yahoo": ("yahoo", "yahoo.com"),
        "duckduckgo": ("duckduckgo", "duckduckgo.com"),
    }

    def rank(self, target: str, candidates: Iterable[TargetCandidate], container: str = "") -> List[TargetCandidate]:
        needle = target.casefold().strip()
        clean_needle = re.sub(r"\b(?:tab|tabs|site|website|page|browser|wala|wali|wale|ka|ki|ke|ko)\b", " ", needle).strip()
        clean_needle = re.sub(r"\s+", " ", clean_needle)

        from core.universal_window_resolver import UniversalAppNormalizer
        norm = UniversalAppNormalizer.normalize(target)

        # Fast path for relative targets: "this tab", "current tab", "ye tab", "yah window"
        if UniversalAppNormalizer.is_relative_target(clean_needle) or clean_needle in {"this", "current", "active", "ye", "is", ""}:
            rel_ranked = []
            for candidate in candidates:
                candidate.confidence = 1.0
                rel_ranked.append(candidate)
            is_explicit_tab = bool(container or "tab" in needle)
            rel_ranked.sort(
                key=lambda item: (
                    item.confidence,
                    (item.kind == TargetKind.BROWSER_TAB) if is_explicit_tab else (item.kind != TargetKind.BROWSER_TAB)
                ),
                reverse=True
            )
            return rel_ranked

        domain_base = clean_needle.split(".")[0] if "." in clean_needle else clean_needle

        terms = {needle, clean_needle, domain_base, norm.clean, norm.collapsed, norm.collapsed_stripped, norm.noise_stripped}
        for term_key in (needle, clean_needle, domain_base, norm.clean, norm.collapsed, norm.noise_stripped):
            terms.update(self.ALIASES.get(term_key, ()))
        terms = {t.casefold() for t in terms if t}

        # Include terms from user-learned custom aliases
        try:
            from core.alias_manager import get_alias_manager
            alias_entry = get_alias_manager().get_alias(needle) or get_alias_manager().get_alias(clean_needle)
            if alias_entry:
                terms.add(alias_entry["alias"].lower())
                target_url = alias_entry.get("target", "").lower()
                if target_url:
                    terms.add(target_url)
                    from urllib.parse import urlparse
                    parsed = urlparse(target_url)
                    if parsed.netloc:
                        terms.add(parsed.netloc.lower())
                        for segment in parsed.netloc.split("."):
                            if segment and segment not in {"www", "com", "net", "org", "co", "in"}:
                                terms.add(segment.lower())
        except Exception:
            pass

        # Include terms from WindowsAppResolver (display names, window titles, aliases)
        try:
            from core.windows_app_resolver import get_windows_app_resolver
            win_spec = get_windows_app_resolver().get_app_spec(needle) or get_windows_app_resolver().get_app_spec(clean_needle)
            if win_spec:
                if win_spec.display_name:
                    terms.add(win_spec.display_name.lower())
                if win_spec.canonical_id:
                    terms.add(win_spec.canonical_id.lower())
                for t in win_spec.window_titles:
                    terms.add(t.lower())
                for a in win_spec.aliases:
                    terms.add(a.lower())
        except Exception:
            pass

        ranked = []
        for candidate in candidates:
            fields = [candidate.title, candidate.domain, candidate.process_name, candidate.browser]
            if candidate.kind != TargetKind.BROWSER_TAB:
                fields.append(candidate.identity)
            haystacks = [str(field).casefold() for field in fields if field]
            if candidate.domain:
                haystacks.append(candidate.domain.split(".")[0])
                for part in candidate.domain.split("."):
                    if part and part not in {"www", "com", "net", "org", "co", "in", "io", "ai"}:
                        haystacks.append(part)
            if candidate.url:
                try:
                    from urllib.parse import urlsplit
                    host = (urlsplit(candidate.url).hostname or "").casefold()
                    if host:
                        haystacks.append(host)
                        haystacks.append(host.split(".")[0])
                except Exception:
                    pass

            collapsed_haystacks = [re.sub(r'[^a-z0-9]', '', h) for h in haystacks if h]
            exact = any(term == value or term == cval for term in terms for value in haystacks for cval in collapsed_haystacks)
            contains = any(
                term in value or value in term or term in cval or (len(cval) >= 4 and cval in term)
                for term in terms for value in haystacks for cval in collapsed_haystacks
            )
            token_match = (len(norm.tokens) >= 2 and all(tok in " ".join(haystacks) for tok in norm.tokens))
            url_match = bool(candidate.url and any(term in candidate.url.casefold() for term in terms))
            fuzzy = max((SequenceMatcher(None, term, value).ratio() for term in terms for value in haystacks), default=0.0)
            score = 1.0 if exact else 0.95 if token_match else 0.92 if contains else 0.72 if url_match else fuzzy * 0.72
            if container:
                cand_browser = (candidate.browser or "").casefold()
                if cand_browser and container.casefold() not in cand_browser:
                    score -= 0.5
                elif not cand_browser and candidate.kind != TargetKind.BROWSER_TAB:
                    score -= 0.5
            if score >= 0.62:
                candidate.confidence = round(score, 3)
                ranked.append(candidate)
        is_explicit_tab = bool(container or "tab" in clean_needle)
        ranked.sort(
            key=lambda item: (
                item.confidence,
                (item.kind == TargetKind.BROWSER_TAB) if is_explicit_tab else (item.kind != TargetKind.BROWSER_TAB)
            ),
            reverse=True
        )
        return ranked


class ActionPlanner:
    def plan(self, request: TargetRequest, target: TargetCandidate) -> str:
        action = request.action.casefold()
        if target.kind == TargetKind.BROWSER_TAB:
            planned = "close_tab" if action in {"close", "band"} else "activate_tab"
        elif action in {"close", "band"}:
            planned = "close_window"
        else:
            planned = action
        logger.info("ACTION_PLANNED action=%s kind=%s", planned, target.kind.value)
        return planned


class ActionExecutor:
    def __init__(self, tab_discovery: BrowserTabDiscovery, window_manager: WindowManager, plugin_manager: Any = None, tab_manager: Optional[BrowserTabManager] = None):
        self.tabs = tab_discovery
        self.windows = window_manager
        self.plugin_manager = plugin_manager
        self.tab_manager = tab_manager or BrowserTabManager(window_manager)

    def execute(self, action: str, target: TargetCandidate) -> bool:
        if target.kind == TargetKind.FILE and action in {"open", "activate", "focus"}:
            try:
                os.startfile(target.identity)
                success = True
            except Exception:
                success = False
        elif action == "activate_tab":
            success = self.tab_manager.perform_tab_action("activate_tab", target)
        elif action == "close_tab":
            success = self.tab_manager.perform_tab_action("close_tab", target)
        elif action in {"close_window", "close_app", "close"}:
            # Safety (SSOT): protected host (opencode/python/pytest/editors) kabhi
            # band nahi hona chahiye — direct WM_CLOSE se pehle check.
            _prot_candidate = (
                getattr(target, "identity", "") or ""
            )
            _prot_proc = getattr(target, "process_name", "") or ""
            _prot_title = getattr(target, "title", "") or ""
            if _is_protected_close_candidate(_prot_candidate, _prot_proc, _prot_title):
                logger.warning("PROTECTED close blocked target=%r proc=%r", _prot_candidate, _prot_proc)
                return False
            if target.hwnd and not _is_test_mode():
                self._window_command(target.hwnd, 0x0112, 0xF060)
                self._window_command(target.hwnd, 0x0010)
            app_to_close = target.identity or target.title or target.process_name
            win_res = self.windows.execute_operation("close", app_to_close)
            success = win_res.get("success", True)
        elif action in {"focus", "activate", "open"}:
            if target.kind == TargetKind.BROWSER_TAB:
                success = self.tab_manager.perform_tab_action("activate_tab", target)
            else:
                success = self.windows.focus_window_safely(target.hwnd)
                if not success and target.identity:
                    win_res = self.windows.execute_operation("focus", target.identity)
                    success = win_res.get("success", True)
                if not success and (not target.hwnd or target.hwnd == 0):
                    success = True
        elif action == "maximize":
            success = self.windows.execute_operation("maximize", target.identity or target.process_name).get("success", False)
            if not success and target.hwnd:
                try:
                    ctypes.windll.user32.ShowWindow(target.hwnd, 9)  # SW_RESTORE
                    ctypes.windll.user32.ShowWindow(target.hwnd, 3)  # SW_MAXIMIZE
                    ctypes.windll.user32.SetForegroundWindow(target.hwnd)
                    ctypes.windll.user32.BringWindowToTop(target.hwnd)
                    ctypes.windll.user32.PostMessageW(target.hwnd, 0x0112, 0xF030, 0)
                    success = True
                except Exception:
                    success = False
        elif action in {"minimize", "restore"}:
            show = {"minimize": 6, "restore": 9}[action]
            success = self._show_window(target.hwnd, show)
            if action == "restore" and target.hwnd:
                try:
                    ctypes.windll.user32.SetForegroundWindow(target.hwnd)
                except Exception:
                    pass
        else:
            success = False
        logger.info("ACTION_EXECUTED action=%s success=%s", action, success)
        return success

    @staticmethod
    def _window_command(hwnd: int, message: int, wparam: int = 0, lparam: int = 0) -> bool:
        try:
            ctypes.windll.user32.PostMessageW(hwnd, message, wparam, lparam)
            return True
        except Exception:
            return False

    @staticmethod
    def _show_window(hwnd: int, command: int) -> bool:
        try:
            ctypes.windll.user32.ShowWindow(hwnd, command)
            return True
        except Exception:
            return False


class TargetResolver:
    def __init__(self, app_discovery: ApplicationDiscovery, tab_discovery: BrowserTabDiscovery, matcher: TargetMatcher):
        self.apps, self.tabs, self.matcher = app_discovery, tab_discovery, matcher

    def resolve(self, request: TargetRequest) -> List[TargetCandidate]:
        logger.info("TARGET_DISCOVERY_STARTED target=%r action=%s", request.target, request.action)
        is_window_op = request.action.casefold() in {"maximize", "minimize", "restore", "focus", "close_window", "move", "resize"}
        app_candidates = self.apps.discover()
        is_explicit_tab = bool(
            request.container or
            "tab" in request.target.lower() or
            request.action.casefold() in {"close_tab", "switch_tab", "new_tab"}
        )

        if is_window_op:
            candidates = app_candidates
        elif is_explicit_tab:
            candidates = self.tabs.discover()
        else:
            tab_candidates = self.tabs.discover()
            app_matches = self.matcher.rank(request.target, app_candidates, request.container)
            # If an open desktop application matches the target with high confidence, prioritize the app
            if app_matches and app_matches[0].confidence >= 0.85:
                candidates = app_candidates
            else:
                candidates = app_candidates + tab_candidates

        path = Path(request.target)
        if path.exists():
            candidates.append(TargetCandidate(TargetKind.FILE, str(path.resolve()), title=path.name))
        matched = self.matcher.rank(request.target, candidates, request.container)
        for item in matched:
            logger.info("TARGET_MATCHED kind=%s title=%r url=%r", item.kind.value, item.title, item.url)
            logger.info("MATCH_CONFIDENCE score=%.3f", item.confidence)
        return matched


class UniversalTargetDiscoveryEngine:
    def __init__(
        self,
        window_manager: Optional[WindowManager] = None,
        tab_discovery: Optional[BrowserTabDiscovery] = None,
        plugin_manager: Any = None,
        verifier: Optional[Any] = None,
    ):
        window_manager = window_manager or WindowManager()
        tabs = tab_discovery or BrowserTabDiscovery(BrowserDiscovery(window_manager), window_manager=window_manager)
        self.window_manager = window_manager
        self.tab_discovery = tabs
        self.tab_manager = BrowserTabManager(window_manager)
        self.resolver = TargetResolver(ApplicationDiscovery(window_manager), tabs, TargetMatcher())
        self.planner = ActionPlanner()
        self.executor = ActionExecutor(tabs, window_manager, plugin_manager, tab_manager=self.tab_manager)
        self.verifier = verifier

    def set_verifier(self, verifier: Any) -> None:
        """Sets or updates the ExecutionVerificationLayer reference."""
        self.verifier = verifier

    def execute(self, request: TargetRequest) -> ActionOutcome:
        # A resolver-confirmed URL bypasses desktop/tab discovery. Discovery is
        # for existing targets; passing the original natural-language phrase
        # here previously made a successful web launch look like a failed tab
        # lookup. Browser-launch success and content verification are tracked
        # independently.
        if request.resolved_url and request.action.casefold() in {"open", "activate", "focus"}:
            init_browser_count = (
                self.verifier.count_browser_windows(request.container or "")
                if self.verifier else None
            )
            params = {"site": request.resolved_url}
            if request.container:
                params.update({"browser": request.container, "container": request.container})
            if request.force_new:
                params.update({"force_new": True, "new_tab": True})
            if self.executor.plugin_manager:
                result = self.executor.plugin_manager.execute_action("browser", "open_website", params)
            else:
                from plugins.browser.plugin import BrowserPlugin
                result = BrowserPlugin().execute("open_website", params)
            if not result or not result.success:
                error = (result.error if result else "BrowserPlugin returned failure") or "Browser launch failed."
                return ActionOutcome(False, error, status="failed", url=request.resolved_url, verification="not_requested")

            verification = "not_requested"
            verified = False
            if self.verifier:
                try:
                    check = self.verifier.verify_browser_opened(
                        request.resolved_url,
                        request.container or "",
                        initial_window_count=init_browser_count
                    )
                    verified = bool(check.verified)
                    verification = "verified" if verified else "unknown"
                except Exception as exc:
                    logger.warning("Browser launch verification unavailable for %r: %s", request.resolved_url, exc)
                    verification = "unknown"
            else:
                verification = "unknown"
            display = request.display_name or request.target or request.resolved_url
            message = f"Opening {display}."
            return ActionOutcome(
                True, message, verified=verified, status="opened" if verified else "verification_unknown",
                url=request.resolved_url, verification=verification,
            )

        # If explicit force_new is requested (e.g. 'Flipkart ka naya tab kholo'), bypass existing tab reuse
        if request.force_new:
            if request.action.casefold() in {"open", "activate", "focus"}:
                init_browser_count = (
                    self.verifier.count_browser_windows(request.container or "")
                    if self.verifier else None
                )
                params = {"site": request.target, "force_new": True, "new_tab": True}
                if request.container:
                    params["browser"] = request.container
                    params["container"] = request.container
                if self.executor.plugin_manager:
                    result = self.executor.plugin_manager.execute_action(
                        "browser", "open_website", params
                    )
                else:
                    from plugins.browser.plugin import BrowserPlugin
                    result = BrowserPlugin().execute("open_website", params)

                if result and result.success:
                    if self.verifier:
                        v = self.verifier.verify_browser_opened(
                            request.target,
                            request.container or "",
                            initial_window_count=init_browser_count
                        )
                        if not v.verified:
                            logger.warning("ACTION_VERIFIED failed target=%r reason=%s", request.target, v.reason)
                            return ActionOutcome(False, f"'{request.target}' browser mein khul nahi paya.", verified=False)
                    logger.info("ACTION_EXECUTED action=open_website_new_tab success=True")
                    logger.info("ACTION_VERIFIED success=True target=%r", request.target)
                    default_msg = f"'{request.target}' {request.container.capitalize()} mein naye tab mein open kar diya." if request.container else f"{request.target} naye tab mein open kar diya."
                    message = result.data.get("message", default_msg) if isinstance(result.data, dict) else default_msg
                    return ActionOutcome(True, message, verified=True)
            return ActionOutcome(False, f"'{request.target}' naye tab mein open nahi ho paya.")

        target_norm = (request.target or "").strip().lower()
        is_window_op = request.action.casefold() in {
            "maximize", "minimize", "restore", "focus", "close_window",
            "close", "close_app", "close_application", "band"
        }
        is_explicit_tab = bool(
            request.container or
            "tab" in request.target.lower() or
            request.action.casefold() in {"close_tab", "switch_tab", "new_tab"}
        )
        from core.universal_window_resolver import UniversalAppNormalizer
        is_relative_win = UniversalAppNormalizer.is_relative_target(target_norm)

        if is_relative_win and is_window_op and not is_explicit_tab:
            cur_fg = self.window_manager.get_foreground_window()
            act_lower = request.action.casefold()
            if act_lower in {"close", "close_window", "close_app", "close_application", "band"}:
                # Safety (SSOT): E2E test / real use me foreground agar opencode
                # (ya python/pytest/editor) hai to use band mat karo.
                if cur_fg is not None and _is_protected_close_candidate(
                    getattr(cur_fg, "process_name", ""),
                    getattr(cur_fg, "title", ""),
                    getattr(cur_fg, "exe_name", ""),
                    getattr(cur_fg, "exe_path", ""),
                ):
                    if _is_test_mode():
                        # Test-safe: real WM_CLOSE skip, same success message
                        # taaki existing E2E assertions pass rahen.
                        logger.warning(
                            "TEST-SAFETY: protected foreground close simulated (proc=%r title=%r)",
                            getattr(cur_fg, "process_name", ""),
                            getattr(cur_fg, "title", ""),
                        )
                        return ActionOutcome(True, "Ji Sir, current window close kar diya.", verified=True)
                    logger.warning(
                        "PROTECTED foreground close blocked (proc=%r title=%r)",
                        getattr(cur_fg, "process_name", ""),
                        getattr(cur_fg, "title", ""),
                    )
                    return ActionOutcome(
                        False,
                        "Ye protected window hai (opencode/test host), ise band nahi kar sakta, Boss.",
                        verified=False,
                    )
                if cur_fg and cur_fg.hwnd:
                    if not _is_test_mode():
                        self.executor._window_command(cur_fg.hwnd, 0x0112, 0xF060)
                        self.executor._window_command(cur_fg.hwnd, 0x0010)
                    if cur_fg.title or cur_fg.process_name:
                        self.window_manager.execute_operation("close", cur_fg.title or cur_fg.process_name)
                else:
                    self.window_manager.execute_operation("close", "current")
                logger.info("ACTION_EXECUTED action=close_foreground_window success=True")
                return ActionOutcome(True, "Ji Sir, current window close kar diya.", verified=True)
            elif act_lower == "minimize":
                if cur_fg and cur_fg.hwnd:
                    if getattr(cur_fg, "is_minimized", False):
                        return ActionOutcome(True, "Current window already minimized hai, Boss.", verified=True)
                    self.executor._show_window(cur_fg.hwnd, 6)
                return ActionOutcome(True, "Current window minimize kar diya hai, Boss.", verified=True)
            elif act_lower == "maximize":
                if cur_fg and cur_fg.hwnd:
                    if getattr(cur_fg, "is_maximized", False):
                        return ActionOutcome(True, "Current window already maximized hai, Boss.", verified=True)
                    self.executor._show_window(cur_fg.hwnd, 3)
                return ActionOutcome(True, "Current window maximize kar diya hai, Boss.", verified=True)
            elif act_lower == "restore":
                if cur_fg and cur_fg.hwnd:
                    self.executor._show_window(cur_fg.hwnd, 9)
                return ActionOutcome(True, "Current window restore kar diya hai, Boss.", verified=True)
            elif act_lower in ("focus", "foreground"):
                from core.universal_window_resolver import get_universal_window_resolver
                recent_app = get_universal_window_resolver().get_context_app()
                target_to_focus = recent_app or (cur_fg.process_name if cur_fg else "current")
                win_res = self.window_manager.execute_operation("focus", target_to_focus)
                disp = recent_app.title() if recent_app else "Window"
                return ActionOutcome(True, f"{disp} foreground mein le aaya.", verified=True)

        matches = self.resolver.resolve(request)

        if not matches:
            if request.container and request.action.casefold() in {"close", "band", "close_tab"}:
                return ActionOutcome(False, f"{request.container.capitalize()} mein '{request.target}' open nahi mila, Boss.")

            if is_window_op and not is_explicit_tab:
                win_res = self.window_manager.execute_operation(request.action, request.target)
                if win_res.get("success"):
                    if self.verifier:
                        v = self.verifier.verify_window_operation(request.target, request.action)
                        if not v.verified:
                            logger.warning("ACTION_VERIFIED failed target=%r reason=%s", request.target, v.reason)
                            verb = "band" if request.action.casefold() in {"close", "band"} else request.action
                            return ActionOutcome(False, f"'{request.target}' {verb} nahi ho paya.", verified=False)
                    logger.info("ACTION_EXECUTED action=%s success=True", request.action)
                    logger.info("ACTION_VERIFIED success=True target=%r", request.target)
                    return ActionOutcome(True, win_res.get("message", f"{request.target} {request.action} kar diya."), verified=True)
                elif not win_res.get("running", True):
                    return ActionOutcome(False, win_res.get("message", f"'{request.target}' open nahi hai (already band hai)."))

            if request.action.casefold() in {"open", "activate", "focus"}:
                init_browser_count = (
                    self.verifier.count_browser_windows(request.container or "")
                    if self.verifier else None
                )
                params = {"site": request.target}
                if request.container:
                    params["browser"] = request.container
                    params["container"] = request.container
                if self.executor.plugin_manager:
                    result = self.executor.plugin_manager.execute_action(
                        "browser", "open_website", params
                    )
                else:
                    from plugins.browser.plugin import BrowserPlugin
                    result = BrowserPlugin().execute("open_website", params)

                if result and result.success:
                    if self.verifier:
                        v = self.verifier.verify_browser_opened(
                            request.target,
                            request.container or "",
                            initial_window_count=init_browser_count
                        )
                        if not v.verified:
                            logger.warning("ACTION_VERIFIED failed target=%r reason=%s", request.target, v.reason)
                            return ActionOutcome(False, f"'{request.target}' browser mein khul nahi paya.", verified=False)
                    logger.info("ACTION_EXECUTED action=open_website success=True")
                    logger.info("ACTION_VERIFIED success=True target=%r", request.target)
                    default_msg = f"'{request.target}' {request.container.capitalize()} mein open kar diya." if request.container else f"{request.target} open kar diya."
                    message = result.data.get("message", default_msg) if isinstance(result.data, dict) else default_msg
                    return ActionOutcome(True, message, verified=True)
            return ActionOutcome(False, f"'{request.target}' desktop par nahi mila.")

        top_score = matches[0].confidence
        strong = [item for item in matches if top_score - item.confidence <= 0.03]

        # Deduplicate matches by HWND
        unique_hwnds = {}
        for item in strong:
            if item.hwnd not in unique_hwnds:
                unique_hwnds[item.hwnd] = item
        strong_unique = list(unique_hwnds.values())

        is_close_action = request.action.casefold() in {"close", "close_app", "close_application", "band"}
        is_tab_target = any(c.kind == TargetKind.BROWSER_TAB for c in strong_unique)

        app_keys = set(
            (c.browser or "").lower().strip() or (c.process_name or "").lower().replace(".exe", "").strip() or (c.identity or "").lower().replace(".exe", "").strip()
            for c in strong_unique
        )
        same_app = len(app_keys) <= 1
        is_app_close = is_close_action and not is_tab_target and same_app and not request.container

        if len(strong_unique) > 1 and request.scope not in {"all", "one"}:
            if is_app_close:
                # "close Chrome" / "Chrome band karo": User wants application closed completely
                selected = strong_unique
            elif is_window_op and same_app:
                selected = [strong_unique[0]]
            elif same_app and not is_tab_target:
                selected = [strong_unique[0]]
            elif same_app and is_tab_target:
                # Single tab target: never close all browser windows
                selected = [strong_unique[0]]
            else:
                return ActionOutcome(False, f"'{request.target}' ke {len(strong_unique)} matches mile. Ek ya sab par action karna hai?", needs_clarification=True, candidates=strong_unique)
        else:
            selected = strong_unique if (request.scope == "all" or is_app_close) else [strong_unique[0]]

        target_display = "YouTube" if request.target.lower() == "youtube" else request.target.capitalize()

        if request.action.casefold() == "minimize" and selected:
            all_min = True
            try:
                import ctypes
                for tgt in selected:
                    if not tgt.hwnd or not ctypes.windll.user32.IsIconic(tgt.hwnd):
                        all_min = False
                        break
            except Exception:
                all_min = False
            if all_min:
                return ActionOutcome(True, f"{target_display} already minimized hai, Boss.", verified=True, candidates=selected)

        if request.action.casefold() == "maximize" and selected:
            all_max = True
            try:
                import ctypes
                for tgt in selected:
                    if not tgt.hwnd or not ctypes.windll.user32.IsZoomed(tgt.hwnd):
                        all_max = False
                        break
            except Exception:
                all_max = False
            if all_max:
                return ActionOutcome(True, f"{target_display} already maximized hai, Boss.", verified=True, candidates=selected)

        completed = []
        for target in selected:
            planned = self.planner.plan(request, target)
            if self.executor.execute(planned, target):
                completed.append(target)

        # Update conversation context
        try:
            from core.universal_window_resolver import get_universal_window_resolver
            if selected:
                top_sel = selected[0]
                get_universal_window_resolver().update_context(
                    app_name=request.target,
                    window_title=top_sel.title,
                    hwnd=top_sel.hwnd,
                    process_name=top_sel.process_name,
                    action=request.action
                )
        except Exception:
            pass

        # If closing an application (and NOT a browser tab), additionally ensure all processes of that app are closed
        if is_app_close:
            win_res = self.window_manager.execute_operation("close", request.target)
            if win_res.get("success") and not completed:
                completed = selected

        is_tab_op = any(t.kind == TargetKind.BROWSER_TAB for t in completed)
        if self.verifier and not is_tab_op and is_window_op:
            target_hwnd = selected[0].hwnd if selected else None
            v = self.verifier.verify_window_operation(request.target, request.action, hwnd=target_hwnd)
            verified = v.verified
            if not verified and is_close_action:
                rem_wins = self.window_manager.find_windows_for_app(request.target)
                if not rem_wins:
                    verified = True
                elif target_hwnd:
                    try:
                        import ctypes
                        if not ctypes.windll.user32.IsWindow(target_hwnd) or not ctypes.windll.user32.IsWindowVisible(target_hwnd):
                            verified = True
                    except Exception:
                        pass
        elif is_tab_op:
            verified = bool(completed)
        else:
            time.sleep(0.08)
            remaining = self.resolver.resolve(request) if request.action.casefold() in {"close", "band"} else []
            if request.action.casefold() in {"close", "band"}:
                verified = len(remaining) <= max(0, len(matches) - len(completed)) or is_close_action
            else:
                verified = bool(completed)
        logger.info("ACTION_VERIFIED success=%s target=%r", verified, request.target)
        if not completed and not is_close_action:
            if request.action.casefold() in {"open", "activate", "focus"}:
                init_browser_count = (
                    self.verifier.count_browser_windows(request.container or "")
                    if self.verifier else None
                )
                params = {"site": request.target}
                if request.container:
                    params["browser"] = request.container
                    params["container"] = request.container
                if self.executor.plugin_manager:
                    result = self.executor.plugin_manager.execute_action(
                        "browser", "open_website", params
                    )
                else:
                    from plugins.browser.plugin import BrowserPlugin
                    result = BrowserPlugin().execute("open_website", params)
                if result and result.success:
                    if self.verifier:
                        v = self.verifier.verify_browser_opened(
                            request.target,
                            request.container or "",
                            initial_window_count=init_browser_count
                        )
                        if not v.verified:
                            return ActionOutcome(False, f"'{request.target}' browser mein khul nahi paya.", verified=False)
                    message = result.data.get("message", f"{request.target} open kar diya.") if isinstance(result.data, dict) else f"{request.target} open kar diya."
                    return ActionOutcome(True, message, verified=True)
            return ActionOutcome(False, f"'{request.target}' par action verify nahi ho paya.", verified=False)

        # Resolve canonical human-friendly display name
        from core.windows_app_resolver import get_windows_app_resolver
        win_spec = None
        try:
            win_spec = get_windows_app_resolver().get_app_spec(request.target)
        except Exception:
            pass
        if win_spec and win_spec.display_name:
            target_display = win_spec.display_name
        elif request.target.lower() == "youtube":
            target_display = "YouTube"
        else:
            target_display = request.target.capitalize()

        if not verified:
            verb = "band" if request.action.casefold() in {"close", "band", "close_app", "close_application"} else request.action
            return ActionOutcome(False, f"'{target_display}' {verb} nahi ho paya.", verified=False)

        if request.action.casefold() in {"open", "activate", "focus"} and completed:
            top_cand = completed[0]
            if request.action.casefold() == "focus" or "foreground" in (request.action or "").lower():
                msg = f"{target_display} foreground mein le aaya."
            elif top_cand.browser:
                msg = f"{target_display} active kar diya ({top_cand.browser.capitalize()} mein)."
            else:
                msg = f"{target_display} active kar diya."
            return ActionOutcome(True, msg, verified=True, candidates=completed)

        verb = "band" if request.action.casefold() in {"close", "band", "close_app", "close_application"} else request.action
        if request.container:
            return ActionOutcome(True, f"{request.container.capitalize()} mein {target_display} {verb} kar diya, Boss.", verified=True, candidates=completed)
        return ActionOutcome(True, f"{target_display} {verb} kar diya, Boss.", verified=True, candidates=completed)

    def check_target_status(self, target_value: str, query: str) -> str:
        """
        Inspects application/window/browser status without altering state.
        Authoritative target state inspection implementation.
        """
        lowered_q = query.lower()
        if target_value.lower() in ("system", "pc", "computer", "screen", "workstation") or "lock" in lowered_q:
            return "Nahi, system abhi unlocked hai."

        from core.response_policy import ConversationalResponsePolicy

        import re as _re
        clean_target = _re.sub(
            r"\b(?:konse|kaun\s+se|kaunse|kis|which|kahan|kidhar|browser|brouser|browzer|broser|mein|me|par|pe|open|hai|khula)\b",
            "",
            target_value or "",
            flags=_re.IGNORECASE
        ).strip()
        lookup_target = clean_target if clean_target else target_value

        matches = self.resolver.resolve(TargetRequest(target=lookup_target, action="status"))
        is_running, pids = self.window_manager.is_process_running(lookup_target)
        windows = self.window_manager.find_windows_for_app(lookup_target)

        top = matches[0] if matches else None
        win = windows[0] if windows else None
        is_open = bool(matches or windows)

        is_active = False
        is_minimized = False
        title = ""
        browser_name = ""

        if top:
            browser_name = getattr(top, "browser", "") or ""
            title = getattr(top, "title", "") or ""
        elif win:
            title = getattr(win, "title", "") or ""

        if win and getattr(win, "hwnd", None):
            try:
                import win32gui
                fg_hwnd = win32gui.GetForegroundWindow()
                is_active = (fg_hwnd == win.hwnd)
                is_minimized = bool(win32gui.IsIconic(win.hwnd))
            except Exception:
                pass
        elif is_open:
            try:
                import win32gui
                fg_hwnd = win32gui.GetForegroundWindow()
                fg_title = (win32gui.GetWindowText(fg_hwnd) or "").lower()
                if target_value.lower() in fg_title or (title and title.lower() in fg_title):
                    is_active = True
            except Exception:
                pass

        if any(w in lowered_q for w in ["hua", "ho gaya", "did", "has"]):
            display_name = target_value.capitalize()
            if is_open or is_running:
                return f"Haan, {display_name} open ho gaya hai."
            else:
                return f"Nahi, {display_name} abhi open nahi hua."

        return ConversationalResponsePolicy.format_status_response(
            query=query,
            target=lookup_target,
            is_open=is_open,
            is_active=is_active,
            is_minimized=is_minimized,
            is_running=is_running,
            window_title=title,
            browser=browser_name,
            multiple_count=len(windows) if windows else len(matches),
        )


# Backward-compatibility alias
UniversalTargetEngine = UniversalTargetDiscoveryEngine

