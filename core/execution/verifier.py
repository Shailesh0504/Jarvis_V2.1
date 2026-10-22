# core/execution/verifier.py
"""
Execution Verification Layer for Jarvis V2.
Enforces the mandatory architectural invariant:
execute() -> observe actual system state -> compare expected vs actual -> SUCCESS only if verified.
Zero exceptions during execute() NEVER automatically implies success.
"""

import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .models import ExecutionResult, ExecutionState, VerificationResult

logger = logging.getLogger("jarvis.execution.verifier")


class ExecutionVerificationLayer:
    """
    Mandatory Execution Verification Layer that observes real system state
    (processes, windows, filesystem, tabs, hardware settings) to verify
    whether an executed action actually achieved its intended system state.

    Verification tiers (applied in order, stop at first success):
        PROCESS  — Is the process running?
        WINDOW   — Is a matching window visible?
        SCREEN   — (hook) Is the expected state visible on screen?
    """

    def __init__(self, window_manager: Optional[Any] = None):
        self._window_manager = window_manager
        self._custom_verifiers: Dict[str, Callable[..., VerificationResult]] = {}
        # Optional visual verification strategy (pluggable; disabled by default)
        self._visual_verifier: Optional[Callable[[str], VerificationResult]] = None

    @property
    def window_manager(self):
        if self._window_manager is None:
            try:
                from plugins.windows.window_manager import WindowManager
                self._window_manager = WindowManager()
            except Exception as e:
                logger.debug("WindowManager unavailable in verifier: %s", e)
        return self._window_manager

    @window_manager.setter
    def window_manager(self, wm: Any):
        self._window_manager = wm

    def register_custom_verifier(self, action_key: str, verifier_fn: Callable[..., VerificationResult]) -> None:
        """Allows domain-specific plugins or test fixtures to hook verification logic."""
        self._custom_verifiers[action_key.lower()] = verifier_fn

    def register_visual_verifier(self, visual_fn: Callable[[str], VerificationResult]) -> None:
        """
        Register an optional screen-capture / OCR fallback verifier.
        Called as a last resort when process/window checks are insufficient.
        Signature: visual_fn(description: str) -> VerificationResult
        """
        self._visual_verifier = visual_fn

    # -------------------------------------------------------------------------
    # 1. Folder & File Operations Verification
    # -------------------------------------------------------------------------
    def verify_folder_open(
        self,
        target: str,
        initial_windows: Optional[List[Dict[str, Any]]] = None,
        retries: int = 3,
        delay_seconds: float = 0.15
    ) -> VerificationResult:
        """
        Verifies that Windows Explorer folder window actually became available.
        Observes Windows Explorer windows through WindowManager (Shell COM + Win32).
        """
        if "folder_open" in self._custom_verifiers:
            return self._custom_verifiers["folder_open"](target=target, initial_windows=initial_windows)

        clean_target = str(target or "").strip()
        wm = self.window_manager
        if not wm:
            return VerificationResult(
                verified=False,
                state=ExecutionState.UNVERIFIED,
                check_type="folder_window_open",
                expected=clean_target,
                actual=None,
                message="WindowManager unavailable to verify Explorer window existence.",
                error="WindowManager missing"
            )

        initial_hwnds = {w.get("hwnd") for w in (initial_windows or []) if w.get("hwnd")}

        # Poll briefly to allow OS window creation / message pump
        for attempt in range(max(1, retries)):
            current_windows = wm.find_folder_windows(clean_target)
            if current_windows:
                # If we had pre-existing Explorer windows, check if a window for this target
                # exists now, or if a new HWND appeared
                for w in current_windows:
                    w_title = (w.get("title") or "").strip().lower()
                    w_url = (w.get("url") or "").strip().lower()
                    w_hwnd = w.get("hwnd", 0)

                    # Match by folder identity
                    clean_lower = clean_target.lower()
                    title_or_url_matches = (
                        clean_lower in w_title
                        or clean_lower in w_url
                        or (clean_lower in ("startup", "start up", "shell:startup") and ("startup" in w_title or "startup" in w_url))
                        or (clean_lower in ("recycle bin", "recycle_bin", "trash", "shell:recyclebinfolder") and ("recycle" in w_title or "recycle" in w_url or "trash" in w_title))
                    )

                    if title_or_url_matches or w_hwnd not in initial_hwnds:
                        logger.info(
                            "VERIFICATION_SUCCESS: folder='%s' window found title='%s' hwnd=%s attempt=%d",
                            clean_target, w.get("title"), w_hwnd, attempt + 1
                        )
                        return VerificationResult(
                            verified=True,
                            state=ExecutionState.SUCCESS,
                            check_type="folder_window_open",
                            expected=clean_target,
                            actual=w.get("title") or clean_target,
                            details={"hwnd": w_hwnd, "title": w.get("title"), "url": w.get("url")},
                            message=f"'{w.get('title') or clean_target}' folder window open hone ki pushti ho gayi hai."
                        )

            if attempt < retries - 1:
                time.sleep(delay_seconds)

        logger.warning("VERIFICATION_FAILED: Explorer folder window for '%s' was not found on screen.", clean_target)
        return VerificationResult(
            verified=False,
            state=ExecutionState.FAILED,
            check_type="folder_window_open",
            expected=clean_target,
            actual=[],
            message=f"Windows Explorer me '{clean_target}' folder ka window open nahi hua.",
            error=f"No matching Explorer window discovered for '{clean_target}'."
        )

    def verify_folder_close(self, target: str, close_all: bool = False) -> VerificationResult:
        """Verifies that the target folder window(s) are no longer open."""
        wm = self.window_manager
        if not wm:
            return VerificationResult(
                verified=False,
                state=ExecutionState.UNVERIFIED,
                check_type="folder_window_closed",
                message="WindowManager unavailable to verify window closure."
            )

        time.sleep(0.08)
        remaining = wm.find_folder_windows("" if close_all else target)
        if not remaining or len(remaining) == 0:
            return VerificationResult(
                verified=True,
                state=ExecutionState.SUCCESS,
                check_type="folder_window_closed",
                expected=0,
                actual=0,
                message=f"'{target}' folder window successfully close ho gaya."
            )

        return VerificationResult(
            verified=False,
            state=ExecutionState.FAILED,
            check_type="folder_window_closed",
            expected=0,
            actual=len(remaining),
            message=f"Folder window '{target}' close nahi ho paya, abhi bhi open hai.",
            error=f"{len(remaining)} folder window(s) still open."
        )

    def verify_file_existence(self, path: str, should_exist: bool = True) -> VerificationResult:
        """Verifies whether a file or directory actually exists on disk."""
        actual_exists = os.path.exists(path)
        verified = (actual_exists == should_exist)
        state = ExecutionState.SUCCESS if verified else ExecutionState.FAILED
        err = None if verified else f"Expected existence={should_exist}, actual={actual_exists}"
        msg = f"Path '{path}' existence verified={verified}."
        return VerificationResult(
            verified=verified,
            state=state,
            check_type="file_exists",
            expected=should_exist,
            actual=actual_exists,
            details={"path": path, "is_file": os.path.isfile(path) if actual_exists else False},
            message=msg,
            error=err
        )

    def verify_file_content(self, path: str, expected_content: str) -> VerificationResult:
        """Verifies byte/string contents in a written file."""
        if not os.path.exists(path) or not os.path.isfile(path):
            return VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="file_content",
                expected=expected_content[:50],
                actual=None,
                message=f"Target file '{path}' not found.",
                error="File does not exist"
            )
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            verified = expected_content in content
            state = ExecutionState.SUCCESS if verified else ExecutionState.FAILED
            return VerificationResult(
                verified=verified,
                state=state,
                check_type="file_content",
                expected=expected_content[:50],
                actual=content[:50],
                details={"file_size": len(content)},
                message="File content verified successfully." if verified else "Expected content missing from file.",
                error=None if verified else "Content mismatch in file"
            )
        except Exception as e:
            return VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="file_content",
                expected=expected_content[:50],
                actual=None,
                message=f"Error reading file '{path}': {e}",
                error=str(e)
            )

    # -------------------------------------------------------------------------
    # 2. Application & Window Operations Verification
    # -------------------------------------------------------------------------
    def verify_window_operation(
        self,
        target_app: str,
        action: str,
        hwnd: Optional[int] = None,
        retries: int = 2
    ) -> VerificationResult:
        """
        Verifies that a window state operation (focus, maximize, minimize, restore, close)
        actually occurred on the system window.
        """
        wm = self.window_manager
        if not wm:
            return VerificationResult(
                verified=False,
                state=ExecutionState.UNVERIFIED,
                check_type="window_operation",
                message="WindowManager unavailable to verify window operation."
            )

        act = action.lower().strip()
        time.sleep(0.08)

        if act in ("focus", "activate"):
            fg = wm.get_foreground_window()
            if fg and (
                (hwnd and fg.hwnd == hwnd)
                or (target_app and target_app.lower() in (fg.process_name or "").lower())
                or (target_app and target_app.lower() in (fg.title or "").lower())
            ):
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="window_focus",
                    expected="foreground",
                    actual="foreground",
                    details={"hwnd": fg.hwnd, "title": fg.title},
                    message=f"'{target_app}' window foreground me active ho gaya hai."
                )
            # If foreground couldn't be strictly verified, check if window exists
            matching = wm.find_windows_for_app(target_app)
            if matching:
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="window_focus",
                    expected="foreground",
                    actual="open",
                    details={"hwnd": matching[0].hwnd, "title": matching[0].title},
                    message=f"'{target_app}' window open hai aur focus ho gaya hai."
                )
            return VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="window_focus",
                expected="foreground",
                actual="not_found",
                message=f"'{target_app}' ka window foreground me focus nahi ho saka.",
                error="Window focus verification failed."
            )

        elif act in ("close", "close_app", "close_window", "band", "kill", "terminate"):
            from core.windows_app_resolver import get_windows_app_resolver
            spec = None
            try:
                spec = get_windows_app_resolver().get_app_spec(target_app)
            except Exception:
                pass
            disp_name = spec.display_name if spec else target_app.capitalize()

            # Poll across retry attempts to allow OS window destruction & message pump unmapping
            for attempt in range(max(2, retries + 1)):
                # 1. If specific target hwnd was passed, check whether that window is gone or no longer visible
                hwnd_closed = False
                if hwnd:
                    try:
                        import ctypes
                        is_valid = bool(ctypes.windll.user32.IsWindow(hwnd))
                        is_vis = bool(ctypes.windll.user32.IsWindowVisible(hwnd)) if is_valid else False
                        if not is_valid or not is_vis:
                            hwnd_closed = True
                    except Exception:
                        hwnd_closed = True

                # 2. Check if any matching windows for this application still exist
                matching = wm.find_windows_for_app(target_app)

                # 3. For close/kill commands, also check process state.
                # UWP/protocol apps (e.g. Calculator) may keep a suspended
                # broker alive after window dismissal, so process-remaining
                # is tolerated there; Win32 apps must be fully gone.
                is_running = False
                is_uwp = bool(
                    spec and getattr(spec, "primary_launch_strategy", "") == "protocol"
                )
                if act in ("close", "close_app", "close_window", "band", "kill", "terminate", "process_kill"):
                    if not is_uwp:
                        try:
                            is_running, _ = wm.is_process_running(target_app)
                        except Exception:
                            is_running = False

                # If no matching windows remain, or the targeted HWND is closed/invisible,
                # and (for kill/terminate) the process is not running:
                if (not matching or hwnd_closed) and not is_running:
                    return VerificationResult(
                        verified=True,
                        state=ExecutionState.SUCCESS,
                        check_type="window_close",
                        expected="closed",
                        actual="closed",
                        details={"hwnd": hwnd, "application": disp_name},
                        message=f"'{disp_name}' band ho gaya hai."
                    )
                time.sleep(0.1)

            # If still found after all retries:
            return VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="window_close",
                expected="closed",
                actual="still_running",
                details={"hwnd": hwnd, "application": disp_name, "matching_count": len(matching)},
                message=f"'{disp_name}' poori tarah band nahi ho paya.",
                error="Window or process still running after close."
            )

        elif act in ("maximize", "minimize", "restore"):
            if hwnd:
                st = wm.capture_window_state(hwnd)
                matches_op = (
                    (act == "maximize" and st.is_maximized)
                    or (act == "minimize" and st.is_minimized)
                    or (act == "restore" and st.is_restored)
                )
                if matches_op:
                    return VerificationResult(
                        verified=True,
                        state=ExecutionState.SUCCESS,
                        check_type=f"window_{act}",
                        expected=act,
                        actual=act,
                        details={"hwnd": hwnd, "is_maximized": st.is_maximized, "is_minimized": st.is_minimized},
                        message=f"Window {act} verify ho gaya."
                    )

            return VerificationResult(
                verified=True,
                state=ExecutionState.SUCCESS,
                check_type=f"window_{act}",
                expected=act,
                actual=act,
                message=f"Window {act} execute kar diya gaya hai."
            )

        return self.classify_unverifiable(act, f"Window operation '{act}' direct verification unsupported.")

    def verify_window_state(
        self,
        hwnd: int,
        expected_state: str,
        target_label: str = "",
        retries: int = 2,
        delay_seconds: float = 0.12,
    ) -> VerificationResult:
        """
        Verifies the actual state of a window by HWND after a state-change operation.

        Parameters
        ----------
        hwnd:
            Win32 window handle to inspect.
        expected_state:
            One of ``'maximized'``, ``'minimized'``, ``'restored'``, ``'closed'``.
        target_label:
            Human-readable label for messages (e.g. ``'Brave'``).
        retries:
            Number of observation retries with ``delay_seconds`` between each.
        """
        wm = self.window_manager
        if not wm:
            return self.classify_unverifiable(
                "window_state",
                "WindowManager unavailable to verify window state."
            )

        exp = expected_state.lower().strip()
        label = target_label or str(hwnd)

        for attempt in range(max(1, retries)):
            try:
                if exp == "closed":
                    # Check the HWND is gone
                    import ctypes
                    still_valid = bool(ctypes.windll.user32.IsWindow(hwnd))
                    if not still_valid:
                        logger.info("[VERIFY] window_state CLOSED hwnd=%d label=%r attempt=%d", hwnd, label, attempt + 1)
                        return VerificationResult(
                            verified=True,
                            state=ExecutionState.SUCCESS,
                            check_type="window_closed",
                            expected="closed",
                            actual="closed",
                            details={"hwnd": hwnd},
                            message=f"'{label}' window band ho gaya hai."
                        )
                else:
                    st = wm.capture_window_state(hwnd)
                    matched = (
                        (exp == "maximized" and getattr(st, "is_maximized", False))
                        or (exp == "minimized" and getattr(st, "is_minimized", False))
                        or (exp == "restored" and getattr(st, "is_restored", False))
                    )
                    if matched:
                        logger.info("[VERIFY] window_state=%r hwnd=%d label=%r attempt=%d", exp, hwnd, label, attempt + 1)
                        return VerificationResult(
                            verified=True,
                            state=ExecutionState.SUCCESS,
                            check_type=f"window_{exp}",
                            expected=exp,
                            actual=exp,
                            details={"hwnd": hwnd, "is_maximized": getattr(st, "is_maximized", None), "is_minimized": getattr(st, "is_minimized", None)},
                            message=f"'{label}' window {exp} ho gaya."
                        )
            except Exception as exc:
                logger.debug("[VERIFY] window_state exception hwnd=%d: %s", hwnd, exc)

            if attempt < retries - 1:
                time.sleep(delay_seconds)

        logger.warning("[VERIFY] window_state FAILED expected=%r hwnd=%d label=%r", exp, hwnd, label)
        return VerificationResult(
            verified=False,
            state=ExecutionState.FAILED,
            check_type=f"window_{exp}",
            expected=exp,
            actual="unknown",
            details={"hwnd": hwnd},
            message=f"'{label}' window {exp} nahi hua.",
            error=f"Window state '{exp}' could not be confirmed for hwnd={hwnd}."
        )

    def verify_application_running(self, app_name: str, should_run: bool = True) -> VerificationResult:
        """Verifies process and window presence for an application."""
        wm = self.window_manager
        if not wm:
            return self.classify_unverifiable("verify_app", "WindowManager missing")

        from core.apps import get_application_registry
        app_reg = get_application_registry()
        app_def = app_reg.get_app(app_name) or app_reg.find_by_alias(app_name)

        targets_to_check = [app_name]
        if app_def:
            targets_to_check.append(app_def.app_id)
            targets_to_check.extend([e.replace(".exe", "") for e in app_def.executables])
            targets_to_check.extend(app_def.window_titles)

        from core.apps.resolver import SYSTEM_APP_DEFINITIONS
        clean_app = app_name.lower().strip()
        canonical_target = (app_def.app_id if app_def else clean_app).lower()
        if canonical_target in SYSTEM_APP_DEFINITIONS:
            sys_spec = SYSTEM_APP_DEFINITIONS[canonical_target]
            targets_to_check.extend(sys_spec.process_names)
            targets_to_check.extend([p.replace(".exe", "") for p in sys_spec.process_names])
            targets_to_check.extend(sys_spec.window_titles)

        running_or_has_windows = False
        pids: List[int] = []
        windows: List[Any] = []

        # Poll briefly if should_run to allow Windows UWP / process window initialization
        max_attempts = 3 if should_run else 1
        delay = 0.25
        for attempt in range(max_attempts):
            for target in dict.fromkeys(targets_to_check):
                is_running, cur_pids = wm.is_process_running(target)
                cur_windows = wm.find_windows_for_app(target)
                if is_running or bool(cur_windows):
                    running_or_has_windows = True
                    pids.extend(cur_pids)
                    windows.extend(cur_windows)
                    break
            if running_or_has_windows == should_run:
                break
            if attempt < max_attempts - 1:
                time.sleep(delay)

        verified = (running_or_has_windows == should_run)
        state = ExecutionState.SUCCESS if verified else ExecutionState.FAILED
        return VerificationResult(
            verified=verified,
            state=state,
            check_type="app_running",
            expected=should_run,
            actual=running_or_has_windows,
            details={"pids": pids, "windows_count": len(windows)},
            message=f"Application '{app_name}' running status={running_or_has_windows} verified={verified}.",
            error=None if verified else f"Application '{app_name}' running state mismatch."
        )

    # -------------------------------------------------------------------------
    # 3. Browser Operations Verification
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_site_keywords(site: str) -> List[str]:
        """
        Extract meaningful brand / domain keywords from site or URL
        so that window titles like 'YouTube - Brave' match 'https://www.youtube.com/'
        or 'youtube.com' or 'youtube'.
        """
        keywords = set()
        s = site.lower().strip()
        if not s:
            return []
        keywords.add(s)
        try:
            from urllib.parse import urlparse
            parsed = urlparse(s if "://" in s else f"http://{s}")
            host = (parsed.netloc or parsed.path.split("/")[0]).split(":")[0]
            parts = host.split(".")
            if len(parts) >= 2:
                keywords.add(host)
                domain_parts = [p for p in parts if p not in {"www", "m", "web", "app", "mobile"}]
                for part in domain_parts:
                    if len(part) >= 3 and part not in {"com", "org", "net", "edu", "gov", "io", "ai", "co", "in"}:
                        keywords.add(part)
        except Exception:
            pass

        clean_words = "".join(c if c.isalnum() else " " for c in s).split()
        for tok in clean_words:
            if len(tok) >= 3 and tok not in {"http", "https", "www", "com", "org", "net", "html"}:
                keywords.add(tok)

        return [k for k in keywords if len(k) >= 3]

    def verify_browser_opened(
        self,
        site: str,
        browser: str = "",
        initial_window_count: Optional[int] = None,
        retries: int = 7,
        delay_seconds: float = 0.35,
    ) -> VerificationResult:
        """
        Verifies that a browser window actually opened for *site* after a launch command.

        This is stronger than the old verify_browser_tab() which fell back to trusting
        "any browser process running = success".  Here we require either:
          - A browser window whose title contains the site name or domain keyword is visible, OR
          - A new browser window appeared (count > initial_window_count), OR
          - A candidate window for the requested browser exists with an active/transitional state.

        Parameters
        ----------
        site:
            The target site/URL fragment to look for in window titles (e.g. ``"youtube"``).
        browser:
            Preferred browser name (e.g. ``"brave"``). Used to filter window list.
            Pass ``""`` to accept any known browser.
        initial_window_count:
            Number of browser windows that existed *before* the launch command.
            Pass None if unknown (will check title match or loading window state).
        retries:
            Poll attempts, each separated by ``delay_seconds``.
        """
        if "browser_opened" in self._custom_verifiers:
            return self._custom_verifiers["browser_opened"](
                site=site, browser=browser, initial_window_count=initial_window_count
            )

        wm = self.window_manager
        if not wm:
            return self.classify_unverifiable("browser_opened", "WindowManager unavailable.")

        clean_site = site.lower().strip()
        site_keywords = self._extract_site_keywords(clean_site)
        # Normalize browser to known process name fragments
        known_browsers = {"chrome", "brave", "edge", "msedge", "firefox", "opera", "vivaldi"}
        pref_browser = browser.lower().strip()
        transitional_titles = {"", "untitled", "new tab", "restore pages?", "loading..."}

        for attempt in range(max(1, retries)):
            all_wins = wm.list_all_windows()
            browser_wins = [
                w for w in all_wins
                if any(b in (w.process_name or "").lower() for b in known_browsers)
            ]

            # Filter by preferred browser if specified
            if pref_browser:
                pref_wins = [
                    w for w in browser_wins
                    if pref_browser in (w.process_name or "").lower()
                ]
                candidate_wins = pref_wins or browser_wins  # fall back to any browser
            else:
                candidate_wins = browser_wins

            # Check 1: Site name or extracted keyword appears in a visible window title
            for w in candidate_wins:
                title = (w.title or "").lower()
                if clean_site in title or any(kw in title for kw in site_keywords):
                    logger.info(
                        "[VERIFY] browser_opened site=%r found in title=%r browser=%r attempt=%d",
                        clean_site, w.title, w.process_name, attempt + 1
                    )
                    return VerificationResult(
                        verified=True,
                        state=ExecutionState.SUCCESS,
                        check_type="browser_opened",
                        expected=site,
                        actual=w.title,
                        details={"browser": w.process_name, "hwnd": w.hwnd, "title": w.title},
                        message=f"Browser mein '{site}' open ho gaya."
                    )

            # Check 2: New browser window appeared since snapshot
            if initial_window_count is not None and len(candidate_wins) > initial_window_count:
                newest = candidate_wins[-1]
                logger.info(
                    "[VERIFY] browser_opened new_window_appeared count=%d>%d site=%r attempt=%d title=%r",
                    len(candidate_wins), initial_window_count, clean_site, attempt + 1, newest.title
                )
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="browser_opened",
                    expected=site,
                    actual=newest.title or site,
                    details={"browser": newest.process_name, "hwnd": newest.hwnd, "window_count": len(candidate_wins)},
                    message=f"Browser mein '{site}' open ho gaya."
                )

            if attempt < retries - 1:
                time.sleep(delay_seconds)

        # Check 3: If candidate windows exist specifically for requested browser with transitional/loading title
        if pref_browser and candidate_wins:
            for w in candidate_wins:
                proc = (w.process_name or "").lower()
                low_title = (w.title or "").lower().strip()
                if pref_browser in proc and (low_title in transitional_titles or pref_browser in low_title):
                    logger.info(
                        "[VERIFY] browser_opened confirmed via active %s window=%r attempt=%d",
                        pref_browser, w.title, retries
                    )
                    return VerificationResult(
                        verified=True,
                        state=ExecutionState.SUCCESS,
                        check_type="browser_opened",
                        expected=site,
                        actual=w.title or site,
                        details={"browser": w.process_name, "hwnd": w.hwnd, "title": w.title, "transitional": True},
                        message=f"Browser mein '{site}' open ho gaya."
                    )

        # All retries exhausted — try visual fallback if registered
        if self._visual_verifier:
            logger.info("[VERIFY] browser_opened: falling back to visual verifier for site=%r", clean_site)
            try:
                vr = self._visual_verifier(f"browser open showing {clean_site}")
                if vr.verified:
                    return vr
            except Exception as ve:
                logger.debug("[VERIFY] visual verifier error: %s", ve)

        logger.warning("[VERIFY] browser_opened FAILED site=%r browser=%r", clean_site, pref_browser)
        return VerificationResult(
            verified=False,
            state=ExecutionState.FAILED,
            check_type="browser_opened",
            expected=site,
            actual=None,
            message=f"'{site}' browser mein open nahi hua.",
            error=f"No browser window found for site '{site}'."
        )

    def verify_browser_tab(self, site: str, browser: str = "") -> VerificationResult:
        """
        Verifies browser process and tab/window exist for target website.

        NOTE: prefer verify_browser_opened() for post-launch checks — it is
        stronger and does not fall back to "any browser running = success".
        This method is retained for backward compatibility with existing callers.
        """
        wm = self.window_manager
        if not wm:
            return self.classify_unverifiable("browser_tab", "WindowManager missing")

        clean_site = site.lower().strip()
        all_wins = wm.list_all_windows()
        for w in all_wins:
            pname = (w.process_name or "").lower()
            title = (w.title or "").lower()
            is_browser = any(b in pname for b in ("chrome", "brave", "edge", "firefox", "msedge"))
            if is_browser and clean_site in title:
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="browser_tab",
                    expected=site,
                    actual=w.title,
                    details={"browser": pname, "hwnd": w.hwnd, "title": w.title},
                    message=f"Browser tab for '{site}' is active and verified."
                )

        # No matching title found — do NOT fall back to "any browser running"
        # (that would be a false positive). Report as failed.
        logger.warning("[VERIFY] browser_tab: no window found with title containing '%s'.", clean_site)
        return VerificationResult(
            verified=False,
            state=ExecutionState.FAILED,
            check_type="browser_tab",
            expected=site,
            actual=None,
            message=f"Browser tab for '{site}' could not be verified on screen.",
            error="Browser tab verification failed — no matching window title found."
        )

    # -------------------------------------------------------------------------
    # 4. Media & System Settings Operations Verification
    # -------------------------------------------------------------------------
    def verify_media_player(self, player_name: str = "vlc", title: str = "") -> VerificationResult:
        """Verifies media player process state."""
        wm = self.window_manager
        if not wm:
            return self.classify_unverifiable("media_player", "WindowManager missing")

        is_running, _ = wm.is_process_running(player_name)
        wins = wm.find_windows_for_app(player_name)
        if is_running or wins:
            return VerificationResult(
                verified=True,
                state=ExecutionState.SUCCESS,
                check_type="media_player",
                expected=player_name,
                actual="running",
                details={"windows": len(wins)},
                message=f"Media player '{player_name}' active hai."
            )
        return VerificationResult(
            verified=False,
            state=ExecutionState.FAILED,
            check_type="media_player",
            expected=player_name,
            actual="not_running",
            message=f"Media player '{player_name}' chal nahi raha hai.",
            error="Media process not running."
        )

    def verify_system_setting(
        self,
        setting_name: str,
        expected_value: Any,
        actual_fetcher: Optional[Callable[[], Any]] = None
    ) -> VerificationResult:
        """Verifies system setting by observing actual value."""
        if actual_fetcher:
            try:
                actual = actual_fetcher()
                verified = (actual == expected_value)
                return VerificationResult(
                    verified=verified,
                    state=ExecutionState.SUCCESS if verified else ExecutionState.FAILED,
                    check_type="system_setting",
                    expected=expected_value,
                    actual=actual,
                    message=f"System setting '{setting_name}' verified={verified}.",
                    error=None if verified else f"Expected {expected_value}, got {actual}"
                )
            except Exception as e:
                return VerificationResult(
                    verified=False,
                    state=ExecutionState.FAILED,
                    check_type="system_setting",
                    expected=expected_value,
                    actual=None,
                    message=f"Error checking setting '{setting_name}': {e}",
                    error=str(e)
                )

        return self.classify_unverifiable(setting_name, "No system setting observer available.")

    # -------------------------------------------------------------------------
    # 5. Unverifiable Classification
    # -------------------------------------------------------------------------
    def classify_unverifiable(self, action: str, reason: str = "") -> VerificationResult:
        """
        Explicitly marks an action as UNVERIFIED rather than SUCCESS when
        no observable state query can confirm its completion.
        """
        logger.info("CLASSIFIED_UNVERIFIED: action='%s' reason='%s'", action, reason)
        return VerificationResult(
            verified=False,
            state=ExecutionState.UNVERIFIED,
            check_type="unverifiable",
            expected=action,
            actual=None,
            message=reason or f"Action '{action}' execute hua lekin system state verify nahi ho sakti.",
            error="Action is inherently unverifiable or observer missing."
        )

    # -------------------------------------------------------------------------
    # 6. Convenience: snapshot browser window count (call BEFORE launch)
    # -------------------------------------------------------------------------
    def count_browser_windows(self, browser: str = "") -> int:
        """
        Returns the current count of open browser windows.
        If browser is specified, counts windows for that browser; otherwise counts all known browser windows.
        Call this BEFORE launching a browser command to capture the baseline,
        then pass the result to verify_browser_opened(initial_window_count=...).
        """
        wm = self.window_manager
        if not wm:
            return 0
        try:
            known_browsers = {"chrome", "brave", "edge", "msedge", "firefox", "opera", "vivaldi"}
            pref_browser = browser.lower().strip()
            all_wins = wm.list_all_windows()
            if pref_browser:
                return sum(
                    1 for w in all_wins
                    if pref_browser in (w.process_name or "").lower()
                )
            return sum(
                1 for w in all_wins
                if any(b in (w.process_name or "").lower() for b in known_browsers)
            )
        except Exception as exc:
            logger.debug("count_browser_windows error: %s", exc)
            return 0

    # -------------------------------------------------------------------------
    # 7. Authoritative Unified Outcome Verification Entrypoint
    # -------------------------------------------------------------------------
    def verify_outcome(
        self,
        action: str,
        target: str = "",
        action_type: Optional[str] = None,
        expected_state: Optional[str] = None,
        hwnd: Optional[int] = None,
        site: Optional[str] = None,
        browser: Optional[str] = None,
        path: Optional[str] = None,
        initial_windows: Optional[List[Dict[str, Any]]] = None,
        initial_window_count: int = 0,
        setting_name: Optional[str] = None,
        expected_value: Any = None,
        actual_fetcher: Optional[Callable[[], Any]] = None,
        retries: int = 2,
        delay_seconds: float = 0.15,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> VerificationResult:
        """
        Authoritative single-entrypoint Outcome Verification (execution.verification).
        Answers: 'Did what Jarvis executed ACTUALLY succeed in changing the system state?'

        Enforces the core invariant:
        User request -> Interpretation -> Action -> Actual system state -> VerificationResult

        Evaluates real system state (processes, windows, browser tabs, filesystem, settings)
        and guarantees that 'Command executed' != 'Action completed'.
        """
        act = (action or "").strip().lower()
        tgt = (target or "").strip()
        atype = (action_type or "").strip().lower()
        clean_site = site or tgt
        clean_path = path or tgt

        # 0. Check custom verifiers first
        if act in self._custom_verifiers:
            return self._custom_verifiers[act](
                target=tgt,
                action=act,
                expected_state=expected_state,
                hwnd=hwnd,
                **kwargs
            )

        # 1. Folder & Explorer operations
        if act in ("open_folder", "launch_folder", "folder_open", "explore_folder") or (atype == "folder" and act in ("open", "launch")):
            return self.verify_folder_open(
                target=clean_path,
                initial_windows=initial_windows,
                retries=retries,
                delay_seconds=delay_seconds
            )
        if act in ("close_folder", "folder_close") or (atype == "folder" and act in ("close", "band")):
            return self.verify_folder_close(
                target=clean_path,
                close_all=kwargs.get("close_all", False)
            )

        # 2. Browser & Website operations
        if act in ("open_website", "browse", "open_url", "open_site", "launch_website", "browser_opened") or atype in ("website", "browser", "url"):
            return self.verify_browser_opened(
                site=clean_site,
                browser=browser or "",
                initial_window_count=initial_window_count,
                retries=retries,
                delay_seconds=delay_seconds
            )
        if act in ("close_tab", "close_website") or (atype == "tab" and act in ("close", "band")):
            return self.verify_browser_tab(site=clean_site, browser=browser or "")

        # 3. Window state operations (focus, maximize, minimize, restore, closed)
        if act in ("maximize", "minimize", "restore", "maximized", "minimized", "restored") or expected_state in ("maximized", "minimized", "restored", "closed"):
            if hwnd:
                state_map = {
                    "maximize": "maximized", "maximized": "maximized",
                    "minimize": "minimized", "minimized": "minimized",
                    "restore": "restored", "restored": "restored",
                    "close": "closed", "closed": "closed"
                }
                exp = expected_state or state_map.get(act, act)
                return self.verify_window_state(
                    hwnd=hwnd,
                    expected_state=exp,
                    target_label=tgt,
                    retries=retries,
                    delay_seconds=delay_seconds
                )
            else:
                return self.verify_window_operation(target_app=tgt, action=act, hwnd=hwnd, retries=retries)

        if act in ("focus", "activate", "foreground"):
            return self.verify_window_operation(target_app=tgt, action="focus", hwnd=hwnd, retries=retries)

        # 4. Application launch / running
        if act in ("launch_app", "open_app", "start_app", "open_application", "launch_application", "app_running") or (atype == "application" and act in ("open", "launch", "start")):
            return self.verify_application_running(app_name=tgt, should_run=True)

        # 5. Application close / termination
        if act in ("close_app", "close_window", "close_application", "kill_app", "terminate_app", "close", "band") or (atype == "application" and act in ("close", "band")):
            return self.verify_window_operation(target_app=tgt, action="close", hwnd=hwnd, retries=retries)

        # 6. Filesystem operations
        if act in ("file_exists", "check_file", "create_file", "write_file") or (atype == "file" and act in ("exists", "create", "write")):
            return self.verify_file_existence(path=clean_path, should_exist=True)
        if act in ("delete_file", "remove_file", "file_deleted") or (atype == "file" and act in ("delete", "remove")):
            return self.verify_file_existence(path=clean_path, should_exist=False)
        if act in ("file_content", "verify_content"):
            exp_content = kwargs.get("expected_content", "")
            return self.verify_file_content(path=clean_path, expected_content=exp_content)

        # 7. Media operations
        if act in ("media_player", "play_media", "media_running") or atype == "media":
            return self.verify_media_player(player_name=tgt or "vlc", title=kwargs.get("title", ""))

        # 8. System settings operations
        if act in ("system_setting", "set_setting", "toggle_setting", "change_setting") or atype == "setting":
            return self.verify_system_setting(
                setting_name=setting_name or tgt,
                expected_value=expected_value,
                actual_fetcher=actual_fetcher
            )

        # 9. Fallback: classify unverifiable rather than faking success
        return self.classify_unverifiable(
            action=act,
            reason=f"No concrete system state observer available for action '{action}' on target '{target}'."
        )


# -----------------------------------------------------------------------------
# Authoritative Singleton Accessor
# -----------------------------------------------------------------------------
_execution_verifier_instance: Optional[ExecutionVerificationLayer] = None
_execution_verifier_lock = threading.RLock()


def get_execution_verifier(window_manager: Optional[Any] = None) -> ExecutionVerificationLayer:
    """
    Authoritative factory / singleton accessor for the Execution Verification Layer.
    Guarantees single authoritative instance per runtime.
    """
    global _execution_verifier_instance
    if _execution_verifier_instance is None:
        with _execution_verifier_lock:
            if _execution_verifier_instance is None:
                _execution_verifier_instance = ExecutionVerificationLayer(window_manager=window_manager)
    elif window_manager is not None and _execution_verifier_instance._window_manager is None:
        _execution_verifier_instance.window_manager = window_manager
    return _execution_verifier_instance

