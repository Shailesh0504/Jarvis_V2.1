# core/execution/plugin_verifier.py
"""
Phase 3.0-B3-B: Plugin Verification Bridge.

Thin adapter that maps plugin (service, action, params, result) tuples to
authoritative physical verification calls on the existing
ExecutionVerificationLayer (verifier.py).

Design invariants:
- NEVER creates a second verifier. Calls get_execution_verifier() singleton.
- NEVER invents verification criteria. Only maps to existing verifier methods.
- Unmappable services/actions -> classify_unverifiable() -> UNVERIFIED (not FAILED, not SUCCESS).
- Verification failure must NOT crash plugin execution (all exceptions caught, UNVERIFIED returned).
- No duplicate execution. No retries for destructive actions.
- Preserves existing plugin response behavior — verification is additive.

Plugin service -> verifier mapping:
    browser    open/navigate/search/search_website    -> verify_browser_opened(site)
    youtube    search_and_play/open                   -> verify_browser_opened("youtube")
    apps       open/launch/start                      -> verify_application_running(app_name)
    vlc        play/open/start                        -> verify_media_player("vlc")
    excel      open/launch                            -> verify_application_running("excel")
    windows    focus/maximize/minimize/restore/close  -> verify_window_operation(app, action)
    system     (all)                                  -> UNVERIFIED (no observable state for cleanup ops)
    audio, network, math, reminder, calendar,
    whatsapp, news, clipboard, etc.                   -> UNVERIFIED
"""

import logging
from typing import Any, Dict, Optional

from core.execution.models import ExecutionState, VerificationResult

logger = logging.getLogger("jarvis.execution.plugin_verifier")


# ---------------------------------------------------------------------------
# Public constants: services with verifiable physical state
# ---------------------------------------------------------------------------

#: Plugin services that support physical verification.
VERIFIABLE_SERVICES = frozenset({
    "browser",
    "youtube",
    "apps",
    "vlc",
    "excel",
    "windows",
})

#: Actions within VERIFIABLE_SERVICES that support physical verification.
VERIFIABLE_ACTIONS: Dict[str, frozenset] = {
    "browser": frozenset({
        "open", "open_website", "open_url", "navigate", "goto",
        "search", "search_website", "launch", "open_site",
    }),
    "youtube": frozenset({
        "search_and_play", "open", "play", "search",
    }),
    "apps": frozenset({
        "open", "launch", "start", "run", "open_application",
    }),
    "vlc": frozenset({
        "play", "open", "start", "launch",
    }),
    "excel": frozenset({
        "open", "launch", "start",
    }),
    "windows": frozenset({
        "focus", "maximize", "minimize", "restore", "close", "close_app",
        "close_window", "activate", "foreground", "band",
    }),
}

#: Destructive plugin actions — never automatically retried.
DESTRUCTIVE_ACTIONS: frozenset = frozenset({
    "delete", "remove", "shred", "format", "clear_temp_files",
    "empty_recycle_bin", "wipe", "uninstall",
})


class PluginVerificationBridge:
    """
    Maps plugin execution results to physical verification checks using the
    existing ExecutionVerificationLayer singleton.

    Usage:
        vr = PluginVerificationBridge.verify(
            service="youtube",
            action="search_and_play",
            params={"query": "arijit singh"},
            plugin_result=res,
            core=self.core,
            initial_window_count=snapshot,
        )
    """

    @classmethod
    def verify(
        cls,
        service: str,
        action: str,
        params: Optional[Dict[str, Any]],
        plugin_result: Any,
        core: Optional[Any] = None,
        initial_window_count: int = 0,
        initial_windows: Optional[list] = None,
    ) -> VerificationResult:
        """
        Performs physical verification for a completed plugin action.

        Parameters
        ----------
        service:
            Plugin service name (e.g. ``"youtube"``, ``"browser"``).
        action:
            Plugin action name (e.g. ``"search_and_play"``, ``"open"``).
        params:
            Plugin execution parameters dict.
        plugin_result:
            Raw plugin result object (PluginResult or dict). Used to extract
            supplementary context (URLs, app names, etc.).
        core:
            JarvisCore reference. Used to reach the window_manager for verifier init.
        initial_window_count:
            Browser/app window count captured BEFORE plugin execution.
        initial_windows:
            Window list snapshot captured BEFORE plugin execution (for folder checks).

        Returns
        -------
        VerificationResult
            Physical verification result. Always returns a result; never raises.
        """
        try:
            return cls._dispatch(
                service=service,
                action=action,
                params=params or {},
                plugin_result=plugin_result,
                core=core,
                initial_window_count=initial_window_count,
                initial_windows=initial_windows or [],
            )
        except Exception as exc:
            logger.debug(
                "[PluginVerifier] Verification dispatch error service=%r action=%r: %s",
                service, action, exc
            )
            return _unverified(action, f"Verification dispatch error: {exc}")

    @classmethod
    def _get_verifier(cls, core: Optional[Any]) -> Any:
        """Returns the ExecutionVerificationLayer singleton, seeded with WindowManager if available."""
        from core.execution.verifier import get_execution_verifier
        wm = None
        if core is not None:
            wm = (
                getattr(core, "window_manager", None)
                or getattr(getattr(core, "target_engine", None), "window_manager", None)
            )
        return get_execution_verifier(window_manager=wm)

    @classmethod
    def _dispatch(
        cls,
        service: str,
        action: str,
        params: Dict[str, Any],
        plugin_result: Any,
        core: Optional[Any],
        initial_window_count: int,
        initial_windows: list,
    ) -> VerificationResult:
        svc = service.lower().strip()
        act = action.lower().strip()

        # Fast path: services with no physical verifier available
        if svc not in VERIFIABLE_SERVICES:
            return _unverified(
                f"{svc}.{act}",
                f"Plugin service '{svc}' has no physical verifier registered."
            )

        # Check action eligibility
        eligible_actions = VERIFIABLE_ACTIONS.get(svc, frozenset())
        if act not in eligible_actions:
            return _unverified(
                f"{svc}.{act}",
                f"Plugin action '{act}' on service '{svc}' has no physical verifier."
            )

        verifier = cls._get_verifier(core)

        # --- browser: open/navigate/search ---
        if svc == "browser":
            site = (
                params.get("site")
                or params.get("url")
                or params.get("query")
                or _extract_result_url(plugin_result)
                or "browser"
            )
            return verifier.verify_browser_opened(
                site=site,
                browser=params.get("browser", ""),
                initial_window_count=initial_window_count,
                retries=5,
                delay_seconds=0.3,
            )

        # --- youtube: search_and_play/open ---
        if svc == "youtube":
            query = (
                params.get("query")
                or params.get("title")
                or params.get("media_target")
                or "youtube"
            )
            return verifier.verify_browser_opened(
                site=query,
                browser="",
                initial_window_count=initial_window_count,
                retries=5,
                delay_seconds=0.35,
            )

        # --- apps: open/launch ---
        if svc == "apps":
            app_name = (
                params.get("app_name")
                or params.get("app")
                or params.get("target")
                or params.get("name")
                or ""
            )
            if not app_name:
                return _unverified(f"{svc}.{act}", "No app_name available to verify.")
            return verifier.verify_application_running(app_name=app_name, should_run=True)

        # --- vlc: play/open ---
        if svc == "vlc":
            return verifier.verify_media_player(player_name="vlc")

        # --- excel: open ---
        if svc == "excel":
            return verifier.verify_application_running(app_name="excel", should_run=True)

        # --- windows: window state operations ---
        if svc == "windows":
            app_target = (
                params.get("app_name")
                or params.get("app")
                or params.get("target")
                or params.get("window_title")
                or ""
            )
            hwnd = params.get("hwnd") or _extract_result_hwnd(plugin_result)
            return verifier.verify_window_operation(
                target_app=app_target,
                action=act,
                hwnd=hwnd,
                retries=2,
            )

        # Fallthrough — should not reach here given guard above
        return _unverified(f"{svc}.{act}", "Unhandled service in dispatch.")

    @classmethod
    def snapshot_window_count(
        cls,
        service: str,
        params: Optional[Dict[str, Any]],
        core: Optional[Any],
    ) -> int:
        """
        Captures browser window count BEFORE plugin execution.
        Should be called immediately before plugin_manager.execute_action().
        Only meaningful for browser/youtube services.
        Returns 0 for all other services.
        """
        svc = (service or "").lower().strip()
        if svc not in ("browser", "youtube"):
            return 0
        try:
            verifier = cls._get_verifier(core)
            params = params or {}
            pref_browser = params.get("browser", "")
            return verifier.count_browser_windows(browser=pref_browser)
        except Exception as exc:
            logger.debug("[PluginVerifier] snapshot_window_count error: %s", exc)
            return 0

    @classmethod
    def is_verifiable(cls, service: str, action: str) -> bool:
        """Returns True if this (service, action) pair has a physical verifier."""
        svc = (service or "").lower().strip()
        act = (action or "").lower().strip()
        return (
            svc in VERIFIABLE_SERVICES
            and act in VERIFIABLE_ACTIONS.get(svc, frozenset())
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _unverified(action: str, reason: str) -> VerificationResult:
    """Returns an explicit UNVERIFIED sentinel (not FAILED, not SUCCESS)."""
    return VerificationResult(
        verified=False,
        state=ExecutionState.UNVERIFIED,
        check_type="plugin_unverifiable",
        expected=action,
        actual=None,
        message=reason or f"Action '{action}' has no physical verifier.",
        error=None,  # Not an error — just unverifiable
    )


def _extract_result_url(plugin_result: Any) -> str:
    """Safely extracts URL from a plugin result for browser verification context."""
    try:
        if isinstance(plugin_result, dict):
            return plugin_result.get("data", {}).get("url", "") or plugin_result.get("url", "")
        data = getattr(plugin_result, "data", None)
        if isinstance(data, dict):
            return data.get("url", "") or ""
        return getattr(plugin_result, "url", "") or ""
    except Exception:
        return ""


def _extract_result_hwnd(plugin_result: Any) -> Optional[int]:
    """Safely extracts HWND from a plugin result for window verification."""
    try:
        if isinstance(plugin_result, dict):
            return plugin_result.get("data", {}).get("hwnd")
        data = getattr(plugin_result, "data", None)
        if isinstance(data, dict):
            return data.get("hwnd")
        return getattr(plugin_result, "hwnd", None)
    except Exception:
        return None
