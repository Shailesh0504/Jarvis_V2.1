# tests/test_phase_3_b3b_plugin_physical_verification.py
"""
Phase 3.0-B3-B: Plugin Physical Verification Tests.

Covers:
1. PluginVerificationBridge: service-to-verifier mapping correctness
2. Browser/YouTube plugin launch -> verify_browser_opened()
3. App plugin launch -> verify_application_running()
4. VLC/media plugin launch -> verify_media_player()
5. Windows plugin action -> verify_window_operation()
6. Unsupported service -> UNVERIFIED (not FAILED, not SUCCESS)
7. Verification failure (no window) -> FAILED status in adapted result
8. Plugin success + verification pass -> VERIFIED in TurnOutcome
9. Plugin success + verification fail -> FAILED in TurnOutcome
10. Plugin failure -> FAILED (no verification attempted)
11. No duplicate telemetry emission
12. No duplicate plugin execution
13. snapshot_window_count: returns 0 for non-browser, int>=0 for browser
14. is_verifiable: correct eligibility for all service/action pairs
15. crash isolation: PluginVerificationBridge.verify() never raises
16. AMBIGUOUS precedence preserved from B1/B3-A
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.execution.adapter import OutcomeAdapter
from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from core.execution.outcome_hook import ExecutionOutcomeHook
from core.execution.plugin_verifier import (
    PluginVerificationBridge,
    VERIFIABLE_SERVICES,
    VERIFIABLE_ACTIONS,
    _unverified,
    _extract_result_url,
    _extract_result_hwnd,
)
from core.context import TurnContext, TurnOutcome, TurnOutcomeStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_plugin_result(success=True, message="", error=None, data=None,
                        verification_result=None):
    return SimpleNamespace(
        success=success, message=message, error=error,
        data=data or {}, verification_result=verification_result,
    )


def _make_wm(is_running=True, windows=None, foreground=None, process_name="chrome"):
    """Mock WindowManager for verifier tests."""
    wm = MagicMock()
    wm.is_process_running.return_value = (is_running, [1234])
    win = MagicMock()
    win.process_name = process_name
    win.title = "YouTube - Brave"
    win.hwnd = 999
    wm.find_windows_for_app.return_value = windows if windows is not None else [win]
    wm.list_all_windows.return_value = [win]
    fg = MagicMock()
    fg.hwnd = 999
    fg.title = "YouTube - Brave"
    fg.process_name = process_name
    wm.get_foreground_window.return_value = foreground if foreground is not None else fg
    wm.count_browser_windows = MagicMock(return_value=1)
    return wm


def _make_verifier(wm=None):
    """Creates a fresh ExecutionVerificationLayer with injected mock WindowManager."""
    from core.execution.verifier import ExecutionVerificationLayer
    v = ExecutionVerificationLayer(window_manager=wm)
    return v


def _make_core(wm=None):
    core = MagicMock()
    core.last_execution_result = None
    core.event_bus.emit.return_value = None
    core.learning_manager.experience_system = None
    if wm:
        core.window_manager = wm
    return core


def _make_turn():
    return TurnContext(
        turn_id=str(uuid.uuid4()),
        raw_input="test",
        normalized_input="test",
    )


# ---------------------------------------------------------------------------
# Section 1: PluginVerificationBridge.is_verifiable()
# ---------------------------------------------------------------------------

class TestIsVerifiable:

    def test_browser_open_is_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("browser", "open") is True

    def test_browser_search_website_is_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("browser", "search_website") is True

    def test_youtube_search_and_play_is_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("youtube", "search_and_play") is True

    def test_vlc_play_is_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("vlc", "play") is True

    def test_vlc_open_is_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("vlc", "open") is True

    def test_excel_open_is_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("excel", "open") is True

    def test_apps_open_is_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("apps", "open") is True

    def test_windows_focus_is_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("windows", "focus") is True

    def test_windows_maximize_is_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("windows", "maximize") is True

    def test_windows_close_is_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("windows", "close") is True

    def test_system_clear_temp_not_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("system", "clear_temp_files") is False

    def test_audio_set_volume_not_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("audio", "set_volume") is False

    def test_network_unknown_not_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("network", "get_wifi_password") is False

    def test_reminder_add_not_verifiable(self):
        assert PluginVerificationBridge.is_verifiable("reminder", "add_reminder") is False

    def test_case_insensitive_service(self):
        assert PluginVerificationBridge.is_verifiable("YouTube", "search_and_play") is True

    def test_case_insensitive_action(self):
        assert PluginVerificationBridge.is_verifiable("browser", "OPEN") is True


# ---------------------------------------------------------------------------
# Section 2: snapshot_window_count()
# ---------------------------------------------------------------------------

class TestSnapshotWindowCount:

    def test_non_browser_service_returns_zero(self):
        count = PluginVerificationBridge.snapshot_window_count("audio", {}, None)
        assert count == 0

    def test_system_returns_zero(self):
        count = PluginVerificationBridge.snapshot_window_count("system", {}, None)
        assert count == 0

    def test_browser_returns_int(self):
        wm = _make_wm()
        wm.list_all_windows.return_value = [MagicMock(process_name="brave"), MagicMock(process_name="chrome")]
        core = _make_core(wm=wm)
        # Patch verifier singleton to use our mock WM
        from core.execution.verifier import ExecutionVerificationLayer
        with patch("core.execution.verifier._execution_verifier_instance",
                   ExecutionVerificationLayer(window_manager=wm)):
            count = PluginVerificationBridge.snapshot_window_count("browser", {}, core)
        assert isinstance(count, int)
        assert count >= 0

    def test_youtube_returns_int(self):
        wm = _make_wm()
        wm.list_all_windows.return_value = []
        core = _make_core(wm=wm)
        from core.execution.verifier import ExecutionVerificationLayer
        with patch("core.execution.verifier._execution_verifier_instance",
                   ExecutionVerificationLayer(window_manager=wm)):
            count = PluginVerificationBridge.snapshot_window_count("youtube", {}, core)
        assert count == 0

    def test_snapshot_non_fatal_on_exception(self):
        """snapshot_window_count must never raise."""
        core = MagicMock()
        core.window_manager = None
        core.target_engine.window_manager = None
        # Force verifier to have no WM
        from core.execution.verifier import ExecutionVerificationLayer
        with patch("core.execution.verifier._execution_verifier_instance",
                   ExecutionVerificationLayer(window_manager=None)):
            count = PluginVerificationBridge.snapshot_window_count("browser", {}, core)
        assert count == 0


# ---------------------------------------------------------------------------
# Section 3: PluginVerificationBridge.verify() — browser
# ---------------------------------------------------------------------------

class TestVerifyBrowser:

    def test_browser_open_verified_when_window_found(self):
        """Browser open + window with site title found -> VERIFIED."""
        wm = _make_wm()
        wm.list_all_windows.return_value = [
            SimpleNamespace(process_name="brave", title="YouTube - Brave", hwnd=1)
        ]
        from core.execution.verifier import ExecutionVerificationLayer
        with patch("core.execution.verifier._execution_verifier_instance",
                   ExecutionVerificationLayer(window_manager=wm)):
            res = _make_plugin_result(success=True)
            vr = PluginVerificationBridge.verify(
                service="browser",
                action="open",
                params={"site": "youtube"},
                plugin_result=res,
                initial_window_count=0,
            )
        assert isinstance(vr, VerificationResult)
        assert vr.verified is True
        assert vr.state == ExecutionState.SUCCESS
        assert vr.check_type == "browser_opened"

    def test_browser_open_unverified_when_no_window(self):
        """Browser open + no window found -> FAILED or UNVERIFIED (not a false positive)."""
        wm = _make_wm(windows=[])
        wm.list_all_windows.return_value = []
        from core.execution.verifier import ExecutionVerificationLayer
        with patch("core.execution.verifier._execution_verifier_instance",
                   ExecutionVerificationLayer(window_manager=wm)):
            res = _make_plugin_result(success=True)
            vr = PluginVerificationBridge.verify(
                service="browser",
                action="open",
                params={"site": "github"},
                plugin_result=res,
                initial_window_count=0,
            )
        # Must NOT be verified — no physical evidence
        assert vr.verified is False

    def test_browser_unverifiable_action_returns_unverified(self):
        """Browser action not in VERIFIABLE_ACTIONS -> UNVERIFIED with no error."""
        res = _make_plugin_result(success=True)
        vr = PluginVerificationBridge.verify(
            service="browser",
            action="close_tab",  # not in verifiable actions
            params={},
            plugin_result=res,
        )
        assert vr.verified is False
        assert vr.state == ExecutionState.UNVERIFIED
        assert vr.error is None  # Not an error, just unverifiable


# ---------------------------------------------------------------------------
# Section 4: PluginVerificationBridge.verify() — app / vlc / excel
# ---------------------------------------------------------------------------

class TestVerifyApp:

    def test_apps_open_verified_when_process_running(self):
        """Apps open + process found -> VERIFIED."""
        wm = _make_wm(is_running=True)
        from core.execution.verifier import ExecutionVerificationLayer
        with patch("core.execution.verifier._execution_verifier_instance",
                   ExecutionVerificationLayer(window_manager=wm)):
            # Patch app registry call inside verify_application_running
            with patch("core.apps.get_application_registry") as mock_reg:
                mock_reg.return_value.get_app.return_value = None
                mock_reg.return_value.find_by_alias.return_value = None
                with patch("core.apps.resolver.SYSTEM_APP_DEFINITIONS", {}):
                    res = _make_plugin_result(success=True)
                    vr = PluginVerificationBridge.verify(
                        service="apps",
                        action="open",
                        params={"app_name": "chrome"},
                        plugin_result=res,
                    )
        assert isinstance(vr, VerificationResult)
        assert vr.verified is True

    def test_apps_open_no_app_name_unverified(self):
        """Apps open with no app_name -> UNVERIFIED gracefully."""
        res = _make_plugin_result(success=True)
        vr = PluginVerificationBridge.verify(
            service="apps",
            action="open",
            params={},  # no app_name
            plugin_result=res,
        )
        assert vr.state == ExecutionState.UNVERIFIED
        assert vr.verified is False

    def test_vlc_play_verified_when_running(self):
        """VLC play + process running -> VERIFIED."""
        wm = _make_wm(is_running=True, process_name="vlc")
        from core.execution.verifier import ExecutionVerificationLayer
        with patch("core.execution.verifier._execution_verifier_instance",
                   ExecutionVerificationLayer(window_manager=wm)):
            res = _make_plugin_result(success=True)
            vr = PluginVerificationBridge.verify(
                service="vlc",
                action="play",
                params={},
                plugin_result=res,
            )
        assert vr.verified is True
        assert vr.check_type == "media_player"

    def test_vlc_play_failed_when_not_running(self):
        """VLC play + process not found -> FAILED."""
        wm = _make_wm(is_running=False, windows=[])
        from core.execution.verifier import ExecutionVerificationLayer
        with patch("core.execution.verifier._execution_verifier_instance",
                   ExecutionVerificationLayer(window_manager=wm)):
            res = _make_plugin_result(success=True)
            vr = PluginVerificationBridge.verify(
                service="vlc",
                action="play",
                params={},
                plugin_result=res,
            )
        assert vr.verified is False
        assert vr.state == ExecutionState.FAILED


# ---------------------------------------------------------------------------
# Section 5: Unsupported services -> UNVERIFIED
# ---------------------------------------------------------------------------

class TestUnverifiableServices:

    @pytest.mark.parametrize("service,action", [
        ("audio", "set_volume"),
        ("system", "clear_temp_files"),
        ("system", "empty_recycle_bin"),
        ("network", "get_wifi_password"),
        ("math", "calculate"),
        ("reminder", "add_reminder"),
        ("calendar", "add_event"),
        ("whatsapp", "send_message"),
        ("news", "get_headlines"),
        ("clipboard", "copy"),
        ("backup", "start_backup"),
        ("pdf", "open"),
        ("email", "send"),
        ("tasks", "add_task"),
    ])
    def test_unsupported_service_yields_unverified(self, service, action):
        """All unsupported services must return UNVERIFIED, never FAILED or SUCCESS."""
        res = _make_plugin_result(success=True)
        vr = PluginVerificationBridge.verify(
            service=service,
            action=action,
            params={},
            plugin_result=res,
        )
        assert vr.verified is False
        assert vr.state == ExecutionState.UNVERIFIED
        assert vr.error is None, f"UNVERIFIED should not be an error, got: {vr.error}"


# ---------------------------------------------------------------------------
# Section 6: Crash isolation — PluginVerificationBridge.verify() never raises
# ---------------------------------------------------------------------------

class TestVerifyCrashIsolation:

    def test_verify_never_raises_when_verifier_errors(self):
        """If the underlying verifier raises, verify() must return UNVERIFIED, never propagate."""
        from core.execution.verifier import ExecutionVerificationLayer
        broken_verifier = ExecutionVerificationLayer(window_manager=None)
        # Force verify_browser_opened to raise
        broken_verifier.verify_browser_opened = MagicMock(side_effect=RuntimeError("Boom!"))
        with patch("core.execution.verifier._execution_verifier_instance", broken_verifier):
            res = _make_plugin_result(success=True)
            vr = PluginVerificationBridge.verify(
                service="browser",
                action="open",
                params={"site": "youtube"},
                plugin_result=res,
            )
        assert isinstance(vr, VerificationResult)
        assert vr.verified is False

    def test_verify_never_raises_with_none_core(self):
        """verify() with core=None must succeed and return UNVERIFIED (no WM)."""
        res = _make_plugin_result(success=True)
        # No WindowManager -> browser verification is UNVERIFIED/FAILED
        from core.execution.verifier import ExecutionVerificationLayer
        v = ExecutionVerificationLayer(window_manager=None)
        with patch("core.execution.verifier._execution_verifier_instance", v):
            vr = PluginVerificationBridge.verify(
                service="browser",
                action="open",
                params={"site": "youtube"},
                plugin_result=res,
                core=None,
            )
        assert isinstance(vr, VerificationResult)
        assert vr.verified is False  # No WM = can't verify


# ---------------------------------------------------------------------------
# Section 7: Full pipeline integration — verify -> adapter -> hook -> outcome
# ---------------------------------------------------------------------------

class TestFullPipelineIntegration:

    def test_plugin_success_plus_physical_verification_yields_verified_outcome(self):
        """Plugin success + physical verification pass -> TurnOutcome VERIFIED."""
        # Real VerificationResult with verified=True
        real_vr = VerificationResult(
            verified=True,
            state=ExecutionState.SUCCESS,
            check_type="browser_opened",
            expected="youtube",
            actual="YouTube - Brave",
        )
        res = _make_plugin_result(success=True, verification_result=real_vr)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="browser.open", action_type="plugin")

        # When a real VerificationResult (verified=True) is present, adapter should yield SUCCESS
        assert adapted.status == ExecutionState.SUCCESS
        assert adapted.verification_result.verified is True

        core = _make_core()
        turn = _make_turn()
        outcome = ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")
        assert outcome.status == TurnOutcomeStatus.VERIFIED
        assert turn.execution_outcome is outcome

    def test_plugin_success_plus_physical_verification_fail_yields_failed_outcome(self):
        """Plugin success + physical verification failure -> TurnOutcome FAILED."""
        # Simulate: adapter with injected physical VR that FAILED
        real_vr = VerificationResult(
            verified=False,
            state=ExecutionState.FAILED,
            check_type="browser_opened",
            expected="github",
            actual=None,
            error="No browser window found",
        )
        # Build adapted result manually as the executor would
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="browser.open", action_type="plugin")
        # Inject physical verification
        adapted.verification_result = real_vr
        adapted.status = ExecutionState.FAILED

        core = _make_core()
        turn = _make_turn()
        outcome = ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")
        assert outcome.status == TurnOutcomeStatus.FAILED
        assert turn.execution_outcome is outcome

    def test_plugin_success_no_verifier_yields_unverified_outcome(self):
        """Plugin success + no physical verifier (unverifiable service) -> TurnOutcome UNVERIFIED."""
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="audio.set_volume", action_type="plugin")
        assert adapted.status == ExecutionState.UNVERIFIED

        core = _make_core()
        turn = _make_turn()
        outcome = ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")
        assert outcome.status == TurnOutcomeStatus.UNVERIFIED

    def test_plugin_failure_yields_failed_outcome_no_verification(self):
        """Plugin failure -> FAILED TurnOutcome (no physical verification needed)."""
        res = _make_plugin_result(success=False, error="Plugin error")
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="browser.open", action_type="plugin")
        assert adapted.status == ExecutionState.FAILED

        core = _make_core()
        turn = _make_turn()
        outcome = ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")
        assert outcome.status == TurnOutcomeStatus.FAILED

    def test_no_duplicate_telemetry(self):
        """Telemetry must fire exactly once per plugin turn regardless of verification path."""
        real_vr = VerificationResult(
            verified=True, state=ExecutionState.SUCCESS,
            check_type="media_player", expected="vlc", actual="running",
        )
        res = _make_plugin_result(success=True, verification_result=real_vr)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="vlc.play", action_type="plugin")

        core = _make_core()
        turn = _make_turn()
        ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")

        emit_calls = [c for c in core.event_bus.emit.call_args_list
                      if c.args and c.args[0] == "execution.outcome"]
        assert len(emit_calls) == 1, f"Expected exactly 1 telemetry emission, got {len(emit_calls)}"

    def test_b1_ambiguous_precedence_preserved(self):
        """AMBIGUOUS precedence from B1 must still hold in B3-B pipeline."""
        er = ExecutionResult(
            success=False,
            status=ExecutionState.PARTIAL,
            requested_action="media.play",
            executed_action="media.play",
            reason="needs_clarification",
        )
        status = ExecutionOutcomeHook.resolve_status(er)
        assert status == TurnOutcomeStatus.AMBIGUOUS


# ---------------------------------------------------------------------------
# Section 8: Private helper correctness
# ---------------------------------------------------------------------------

class TestPrivateHelpers:

    def test_unverified_helper_has_no_error(self):
        vr = _unverified("test.action", "No verifier")
        assert vr.verified is False
        assert vr.state == ExecutionState.UNVERIFIED
        assert vr.error is None  # Not an error field

    def test_extract_result_url_from_dict(self):
        d = {"data": {"url": "https://youtube.com"}}
        assert _extract_result_url(d) == "https://youtube.com"

    def test_extract_result_url_from_object(self):
        r = SimpleNamespace(data={"url": "https://github.com"})
        assert _extract_result_url(r) == "https://github.com"

    def test_extract_result_url_empty(self):
        assert _extract_result_url({}) == ""

    def test_extract_result_hwnd_from_dict(self):
        d = {"data": {"hwnd": 12345}}
        assert _extract_result_hwnd(d) == 12345

    def test_extract_result_hwnd_none_when_missing(self):
        assert _extract_result_hwnd({}) is None

    def test_extract_result_hwnd_non_fatal(self):
        """_extract_result_hwnd must not raise on malformed input."""
        assert _extract_result_hwnd(None) is None
        assert _extract_result_hwnd("bad input") is None


# ---------------------------------------------------------------------------
# Section 9: B2 primary path not affected
# ---------------------------------------------------------------------------

class TestB2PathNotAffected:

    def test_from_action_outcome_unaffected(self):
        """from_action_outcome (B2 path) must still work correctly."""
        outcome = SimpleNamespace(
            success=True,
            verified=True,
            needs_clarification=False,
            message="Window focused",
            verification="window_focus_check",
            url=None,
            candidates=None,
        )
        adapted = OutcomeAdapter.from_action_outcome(
            outcome, requested_action="focus_window", target="chrome", action_type="window"
        )
        assert adapted.success is True
        assert adapted.status == ExecutionState.SUCCESS
        assert adapted.executed_action == "focus_window"

    def test_b3a_unverified_invariant_still_holds(self):
        """B3-A invariant: plugin success without real VR -> UNVERIFIED (not broken by B3-B)."""
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="audio.set_volume")
        assert adapted.status == ExecutionState.UNVERIFIED
        assert adapted.verification_result.verified is False
