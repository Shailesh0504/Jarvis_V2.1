# conftest.py
"""Global Pytest Configuration and Environment Setup for Jarvis V2."""

import os

# Mark every pytest run as an automated test run so production plugins
# (SystemPlugin.shutdown_pc/restart, AppsPlugin.close_app, etc.) take the
# simulated-success path instead of touching the real OS.
os.environ["JARVIS_TEST_MODE"] = "1"

# Ensure Qt / PySide6 runs in headless offscreen mode across all test sessions
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"

try:
    import PySide6.QtCore
    import PySide6.QtWidgets
    _app = PySide6.QtWidgets.QApplication.instance() or PySide6.QtWidgets.QApplication(["-platform", "offscreen"])
except Exception:
    pass


def pytest_sessionstart(session):
    """Ensure system/laptop volume is set to 12% whenever pytest runs."""
    try:
        from plugins.audio.volume_controller import set_system_volume
        set_system_volume(12)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test-time safety net (SSOT for pytest runs):
# Program test karte samay opencode application band nahi hona chahiye,
# aur system shutdown / restart bhi nahi hona chahiye.
# Isliye yahan dangerous OS calls ko globally block kiya gaya hai.
# Production code ka existing `JARVIS_TEST_MODE` / `"pytest" in sys.modules`
# guard primary hai; ye fixture defense-in-depth hai taaki koi test
# galti se bhi real shutdown / taskkill / process-kill na kar sake.
# ---------------------------------------------------------------------------

# Substrings of processes that must NEVER be killed during tests.
# Includes the coding agent host (opencode), editors, and the test runner itself.
PROTECTED_PROCESS_SUBSTRINGS = frozenset({
    "opencode",
    "code",
    "vscode",
    "cursor",
    "windsurf",
    "python",
    "pytest",
    "conda",
})


def _cmd_text(cmd) -> str:
    try:
        if isinstance(cmd, (list, tuple)):
            return " ".join(str(c) for c in cmd).lower()
        return str(cmd).lower()
    except Exception:
        return ""


def _is_shutdown_cmd(cmd_text: str) -> bool:
    t = cmd_text.strip()
    if not t:
        return False
    # Windows shutdown/hibernate + Linux power commands
    dangerous = (
        "shutdown", "restart-computer", "stop-computer", "reboot",
        "poweroff", "halt", "init 6", "init 0",
    )
    return any(d in t for d in dangerous)


def _targets_protected_process(cmd_text: str) -> bool:
    return any(p in cmd_text for p in PROTECTED_PROCESS_SUBSTRINGS)


try:
    import pytest as _pytest

    @_pytest.fixture(autouse=True)
    def _jarvis_test_safety_net(monkeypatch):
        """Block real shutdown/restart and protected-process kills during tests."""
        import subprocess as _sp

        _real_popen = _sp.Popen
        _real_run = _sp.run

        class _BlockedPopen:
            def __init__(self, *args, **kwargs):
                self.args = args[0] if args else kwargs.get("args")
                self.returncode = 0

            def communicate(self, *a, **k):
                return (b"", b"")

            def wait(self, *a, **k):
                return 0

            def poll(self):
                return 0

            def kill(self):
                return None

            def terminate(self):
                return None

        def _safe_popen(cmd, *args, **kwargs):
            text = _cmd_text(cmd)
            if _is_shutdown_cmd(text) or _targets_protected_process(text):
                return _BlockedPopen(cmd, *args, **kwargs)
            return _real_popen(cmd, *args, **kwargs)

        def _safe_run(cmd, *args, **kwargs):
            text = _cmd_text(cmd)
            if _is_shutdown_cmd(text) or _targets_protected_process(text):
                import subprocess as _sub
                return _sub.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
            return _real_run(cmd, *args, **kwargs)

        monkeypatch.setattr("subprocess.Popen", _safe_popen)
        monkeypatch.setattr("subprocess.run", _safe_run)

        # Cover remaining subprocess entry points that bypass Popen/run patching
        # (bring_app_to_front uses check_output; other code may use call/check_call).
        try:
            _real_call = _sp.call

            def _safe_call(cmd, *args, **kwargs):
                text = _cmd_text(cmd)
                if _is_shutdown_cmd(text) or _targets_protected_process(text):
                    return 0
                return _real_call(cmd, *args, **kwargs)

            monkeypatch.setattr("subprocess.call", _safe_call)
        except Exception:
            pass
        try:
            _real_check_call = _sp.check_call

            def _safe_check_call(cmd, *args, **kwargs):
                text = _cmd_text(cmd)
                if _is_shutdown_cmd(text) or _targets_protected_process(text):
                    return 0
                return _real_check_call(cmd, *args, **kwargs)

            monkeypatch.setattr("subprocess.check_call", _safe_check_call)
        except Exception:
            pass
        try:
            _real_check_output = _sp.check_output

            def _safe_check_output(cmd, *args, **kwargs):
                text = _cmd_text(cmd)
                if _is_shutdown_cmd(text) or _targets_protected_process(text):
                    return b""
                return _real_check_output(cmd, *args, **kwargs)

            monkeypatch.setattr("subprocess.check_output", _safe_check_output)
        except Exception:
            pass

        # Block os.system("shutdown ...") style calls.
        import os as _os
        _real_system = _os.system

        def _safe_system(command):
            if _is_shutdown_cmd(_cmd_text(command)) or _targets_protected_process(_cmd_text(command)):
                return 0
            return _real_system(command)

        monkeypatch.setattr("os.system", _safe_system)

        # Block os.kill / os.popen variants during tests.
        try:
            _real_kill = _os.kill

            def _safe_kill(pid, sig):
                return None

            monkeypatch.setattr("os.kill", _safe_kill)
        except Exception:
            pass
        try:
            if hasattr(_os, "popen"):
                _real_popen_os = _os.popen

                def _safe_os_popen(cmd, *args, **kwargs):
                    text = _cmd_text(cmd)
                    if _is_shutdown_cmd(text) or _targets_protected_process(text):
                        import io as _io
                        return _io.StringIO("")
                    return _real_popen_os(cmd, *args, **kwargs)

                monkeypatch.setattr("os.popen", _safe_os_popen)
        except Exception:
            pass

        # Never let a test kill the runner via os._exit(); raise instead so
        # the failure is visible instead of the opencode/pytest app closing.
        _real__exit = _os._exit

        def _safe__exit(code=0):
            raise RuntimeError(f"Blocked os._exit({code}) during pytest (safety net).")

        monkeypatch.setattr("os._exit", _safe__exit)

        # Block real process kills during tests; dummy-name closes used in
        # tests (e.g. non_existent_dummy_app_xyz_123) simply no-op.
        try:
            import psutil as _psutil

            monkeypatch.setattr(_psutil.Process, "kill", lambda self, *a, **k: None)
            monkeypatch.setattr(_psutil.Process, "terminate", lambda self, *a, **k: None)
        except Exception:
            pass

        # Block DIRECT Win32 close (WM_CLOSE / SC_CLOSE) that bypasses
        # WindowManager.execute_operation — FastPath + TargetEngine send
        # PostMessageW straight to the foreground HWND, which during an E2E
        # run inside opencode IS the opencode window. No-op in tests so the
        # response text stays identical while the host never closes.
        try:
            from core.target_engine import ActionExecutor as _AE

            monkeypatch.setattr(_AE, "_window_command", staticmethod(lambda *a, **k: True))
            monkeypatch.setattr(_AE, "_show_window", staticmethod(lambda *a, **k: True))
        except Exception:
            pass

        yield
except Exception:
    pass


# ---------------------------------------------------------------------------
# Second layer (2026-09-25): block DIRECT Win32/OS effects that bypass
# subprocess — ctypes LockWorkStation (workstation lock), WindowManager
# close/kill (WM_CLOSE + taskkill of real apps like Excel/Chrome), and the
# system power/lock plugin actions. Fakes return realistic success payloads
# so response-text assertions keep passing; everything else delegates.
# Unconfirmed shutdown/restart still delegates to the real plugin so the
# confirmation prompt path ("sach me...?") keeps working — only confirmed
# power actions, locks, and window closes are faked. Per-test patch.object
# mocks still take precedence (applied inside tests, on top of this guard).
# ---------------------------------------------------------------------------

_TEST_SAFE_PLUGIN_ACTIONS = frozenset({
    ("system", "shutdown_pc"),
    ("system", "restart_pc"),
    ("system", "shutdown"),
    ("system", "restart"),
    ("system", "lock_pc"),
    ("system", "lock_system"),
    ("system", "lock"),
    ("system", "sleep_pc"),
    ("system", "hibernate"),
    ("system", "schedule_shutdown"),
    ("system", "abort_shutdown"),
    ("windows", "close_app"),
    ("windows", "kill_process"),
})

_TEST_SAFE_WINDOW_OPS = frozenset({"close", "terminate", "kill", "band"})

try:
    import pytest as _pytest2

    @_pytest2.fixture(autouse=True)
    def _block_direct_win32_effects(monkeypatch):
        """Fake workstation lock, real window close/kill, and power actions."""
        import logging as _logging
        _log = _logging.getLogger("jarvis.tests.safety")

        # 1. Workstation lock: ctypes direct call (no subprocess involved).
        try:
            import ctypes as _ctypes
            _user32 = _ctypes.windll.user32
            if hasattr(_user32, "LockWorkStation"):
                monkeypatch.setattr(_user32, "LockWorkStation", lambda *a, **k: 1)
        except Exception as _e:
            _log.debug("LockWorkStation guard unavailable: %s", _e)

        # 2. Real window close/kill via WindowManager.
        try:
            from plugins.windows.window_manager import WindowManager as _WM
            _real_op = _WM.execute_operation

            def _safe_op(self, operation, app_name, **kwargs):
                if str(operation or "").lower().strip() in _TEST_SAFE_WINDOW_OPS:
                    # Folder closes never kill explorer (close_folder_window path)
                    # — safe by design, delegate so folder tests keep working.
                    try:
                        _low = str(app_name or "").lower().strip()
                        _aliases = getattr(_WM, "FOLDER_ALIASES", {}) or {}
                        _is_folderish = "folder" in _low or any(
                            _low in [a.lower() for a in aliases]
                            for aliases in _aliases.values()
                        )
                    except Exception:
                        _is_folderish = "folder" in str(app_name or "").lower()
                    if _is_folderish:
                        return _real_op(self, operation, app_name, **kwargs)
                    _log.warning("TEST-SAFETY: faked window %s(%r)", operation, app_name)
                    display = (app_name or "Window").capitalize()
                    return {
                        "success": True,
                        "app": app_name,
                        "operation": operation,
                        "test_safe": True,
                        "message": f"{display} band kar diya hai, Boss. (test-safe)",
                    }
                return _real_op(self, operation, app_name, **kwargs)

            monkeypatch.setattr(_WM, "execute_operation", _safe_op)
        except Exception as _e:
            _log.debug("WindowManager guard unavailable: %s", _e)

        # 3. System power/lock plugin actions. Unconfirmed shutdown/restart
        # delegates to the real plugin (confirmation prompt, OS-safe without
        # confirmed=True); confirmed power actions and locks are faked.
        try:
            from plugins.manager import PluginManager as _PM
            from plugins.manifest import PluginResult as _PR
            _real_exec = _PM.execute_action

            def _safe_exec(self, plugin_name, action_name, parameters):
                key = (str(plugin_name or "").lower(), str(action_name or "").lower())
                if key in _TEST_SAFE_PLUGIN_ACTIONS:
                    params = parameters or {}
                    if key[1] in ("shutdown_pc", "restart_pc", "shutdown", "restart") \
                            and not (isinstance(params, dict) and params.get("confirmed", False)):
                        return _real_exec(self, plugin_name, action_name, parameters)
                    _log.warning("TEST-SAFETY: faked %s.%s", key[0], key[1])
                    if "restart" in key[1]:
                        text = "System restart ho gaya hai, Boss. (test-safe, koi real restart nahi hua)"
                    elif "shutdown" in key[1]:
                        text = "System shutdown ho gaya hai, Boss. (test-safe, koi real shutdown nahi hua)"
                    elif "lock" in key[1]:
                        text = "System lock kar diya hai, Boss. (test-safe, workstation lock nahi hua)"
                    else:
                        label = str(params.get("target") or params.get("app_name") or key[1])
                        text = f"{label} band kar diya hai, Boss. (test-safe)"
                    return _PR(success=True, data={
                        "test_safe": True,
                        "message": text,
                        "formatted_answer": text,
                    })
                return _real_exec(self, plugin_name, action_name, parameters)

            monkeypatch.setattr(_PM, "execute_action", _safe_exec)
        except Exception as _e:
            _log.debug("PluginManager guard unavailable: %s", _e)

        yield
except Exception:
    pass

