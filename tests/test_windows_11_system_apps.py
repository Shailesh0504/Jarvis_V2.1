# tests/test_windows_11_system_apps.py
"""
Test Suite for Windows 11 Administrative Tools, Management Snap-ins (.msc),
and System Utilities (Open & Close).
"""

from unittest.mock import MagicMock, patch
import pytest

from brain.semantic_parser import HinglishNLUParser
from core.apps.resolver import get_app_resolver, SYSTEM_APP_DEFINITIONS
from core.windows_app_resolver import get_windows_app_resolver
from plugins.windows.window_manager import WindowInfo, WindowManager
from core.execution.verifier import ExecutionVerificationLayer
from core.execution.strategies import ExecutionStrategyEngine
from core.apps.detector import InstalledAppInfo


class TestWindows11SystemAppResolution:
    """Test resolution of Windows 11 system apps and administrative snap-ins."""

    @pytest.fixture(autouse=True)
    def setup_resolver(self):
        self.win_resolver = get_windows_app_resolver()
        self.app_resolver = get_app_resolver()

    @pytest.mark.parametrize("query,expected_id", [
        ("computer manager", "compmgmt"),
        ("computer management", "compmgmt"),
        ("compmgmt", "compmgmt"),
        ("disk management", "diskmgmt"),
        ("disk manager", "diskmgmt"),
        ("diskmgmt", "diskmgmt"),
        ("event viewer", "eventvwr"),
        ("eventvwr", "eventvwr"),
        ("performance monitor", "perfmon"),
        ("perfmon", "perfmon"),
        ("resource monitor", "resmon"),
        ("resmon", "resmon"),
        ("group policy", "gpedit"),
        ("group policy editor", "gpedit"),
        ("gpedit", "gpedit"),
        ("local security policy", "secpol"),
        ("secpol", "secpol"),
        ("system information", "msinfo32"),
        ("msinfo32", "msinfo32"),
        ("system config", "msconfig"),
        ("msconfig", "msconfig"),
        ("windows firewall", "wf"),
        ("defender firewall", "wf"),
        ("directx diagnostic tool", "dxdiag"),
        ("dxdiag", "dxdiag"),
        ("disk cleanup", "cleanmgr"),
        ("cleanmgr", "cleanmgr"),
        ("task scheduler", "taskschd"),
        ("taskschd", "taskschd"),
        ("local users and groups", "lusrmgr"),
        ("lusrmgr", "lusrmgr"),
        ("certificate manager", "certmgr"),
        ("certmgr", "certmgr"),
        ("network connections", "ncpa"),
        ("ncpa.cpl", "ncpa"),
        ("programs and features", "appwiz"),
        ("system properties", "sysdm"),
    ])
    def test_windows_app_resolver_matches(self, query, expected_id):
        match = self.win_resolver.resolve_application(query)
        assert match is not None, f"Expected to resolve '{query}', but got None"
        assert match.canonical_id == expected_id

    def test_system_app_definitions_synced(self):
        """Ensure all new system tools are present in SYSTEM_APP_DEFINITIONS."""
        for app_id in [
            "compmgmt", "diskmgmt", "eventvwr", "perfmon", "resmon",
            "gpedit", "secpol", "msinfo32", "msconfig", "wf", "dxdiag",
            "cleanmgr", "taskschd", "lusrmgr", "certmgr", "ncpa", "appwiz", "sysdm"
        ]:
            assert app_id in SYSTEM_APP_DEFINITIONS, f"App '{app_id}' missing in SYSTEM_APP_DEFINITIONS"


class TestWindows11NLUIntentParsing:
    """Test natural language parsing for open and close commands."""

    @pytest.mark.parametrize("phrase,expected_app", [
        ("open computer manager", "compmgmt"),
        ("computer manager kholo", "compmgmt"),
        ("computer manager open karo", "compmgmt"),
        ("open disk management", "diskmgmt"),
        ("disk management kholo", "diskmgmt"),
        ("open event viewer", "eventvwr"),
        ("event viewer khol do", "eventvwr"),
        ("open performance monitor", "perfmon"),
        ("open resource monitor", "resmon"),
        ("resource monitor chalao", "resmon"),
        ("open group policy editor", "gpedit"),
        ("open local security policy", "secpol"),
        ("open system information", "msinfo32"),
        ("system information open kar do", "msinfo32"),
        ("open system configuration", "msconfig"),
        ("open windows defender firewall", "wf"),
        ("open directx diagnostic tool", "dxdiag"),
        ("open disk cleanup", "cleanmgr"),
        ("open task scheduler", "taskschd"),
        ("open network connections", "ncpa"),
        ("open programs and features", "appwiz"),
        ("open system properties", "sysdm"),
    ])
    def test_nlu_parses_open_commands(self, phrase, expected_app):
        act = HinglishNLUParser.parse(phrase)
        assert act is not None, f"Failed to parse '{phrase}'"
        assert act.intent == "OPEN_APP", f"Expected OPEN_APP for '{phrase}', got {act.intent}"
        assert act.action == "launch_app"
        assert act.service == "windows"
        assert act.parameters.get("app_name") == expected_app
        # Strict negative check: Must NOT be OPEN_WEBSITE
        assert act.intent != "OPEN_WEBSITE"

    @pytest.mark.parametrize("phrase,expected_name", [
        ("close computer manager", "computer manager"),
        ("computer manager band kar do", "computer manager"),
        ("computer manager close karo", "computer manager"),
        ("close disk management", "disk management"),
        ("disk management band karo", "disk management"),
        ("close event viewer", "event viewer"),
        ("event viewer band kar do", "event viewer"),
        ("close resource monitor", "resource monitor"),
        ("resource monitor band karo", "resource monitor"),
        ("close system information", "system information"),
        ("close task scheduler", "task scheduler"),
    ])
    def test_nlu_parses_close_commands(self, phrase, expected_name):
        act = HinglishNLUParser.parse(phrase)
        assert act is not None, f"Failed to parse close for '{phrase}'"
        assert act.intent == "WINDOW_CLOSE"
        assert act.action == "close_app"
        assert act.service == "windows"
        app_param = act.parameters.get("app_name", "").lower()
        canonical_match = (
            expected_name.lower() in app_param
            or app_param in expected_name.lower()
            or (expected_name == "computer manager" and "computer management" in app_param)
        )
        assert canonical_match, f"Expected '{expected_name}', got '{app_param}'"


class TestWindowManagerSnapInManagement:
    """Test WindowManager window finding, process tracking, and safe closing for snap-ins."""

    @pytest.fixture
    def wm(self):
        wm = WindowManager()
        wm._user32 = MagicMock()
        return wm

    def test_find_windows_for_snapin_by_alias(self, wm):
        # Mock open windows where MMC has Computer Management open
        wm.list_all_windows = lambda: [
            WindowInfo(hwnd=1001, title="Computer Management", process_name="mmc.exe", pid=5001),
            WindowInfo(hwnd=1002, title="Settings", process_name="SystemSettings.exe", pid=5002),
        ]
        # Query using alias "computer manager"
        wins = wm.find_windows_for_app("computer manager")
        assert len(wins) == 1
        assert wins[0].title == "Computer Management"
        assert wins[0].hwnd == 1001

        # Query using canonical "compmgmt"
        wins2 = wm.find_windows_for_app("compmgmt")
        assert len(wins2) == 1
        assert wins2[0].title == "Computer Management"

    def test_mmc_snapin_running_state_isolation(self, wm):
        """Verify that when only Device Manager is open, Computer Management is reported as NOT running."""
        wm.list_all_windows = lambda: [
            WindowInfo(hwnd=2001, title="Device Manager", process_name="mmc.exe", pid=6001)
        ]
        # Computer Management should NOT be running
        running_cm, pids_cm = wm.is_process_running("computer manager")
        assert running_cm is False
        assert pids_cm == []

        # Device Manager should be running
        running_dm, pids_dm = wm.is_process_running("device manager")
        assert running_dm is True
        assert 6001 in pids_dm

    def test_execute_close_snapin_safe(self, wm):
        """Verify closing a snap-in posts WM_CLOSE to window without terminating other MMC processes."""
        wm.list_all_windows = lambda: [
            WindowInfo(hwnd=1001, title="Computer Management", process_name="mmc.exe", pid=5001)
        ]
        res = wm.execute_operation("close", "computer manager")
        assert res["success"] is True
        assert res["operation"] == "close"
        assert wm._user32.PostMessageW.called

    def test_verification_layer_snapin_close(self, wm):
        """Verify ExecutionVerificationLayer correctly reports closed when snap-in window disappears."""
        # Window list is now empty (closed)
        wm.list_all_windows = lambda: []
        verif = ExecutionVerificationLayer(window_manager=wm)
        res = verif.verify_window_operation("computer manager", "close")
        assert res.verified is True
        assert "band" in res.message


class TestExecutionStrategyMSCSupport:
    """Test execution strategy handling of .msc files."""

    def test_direct_executable_msc_startfile(self):
        engine = ExecutionStrategyEngine()
        installed = InstalledAppInfo(
            app_id="compmgmt",
            display_name="Computer Management",
            executable_path=r"C:\Windows\System32\compmgmt.msc",
            is_installed=True
        )
        with patch("os.path.exists", return_value=True), \
             patch("os.startfile", create=True) as mock_startfile:
            success, err = engine._dispatch_app_strategy(
                strategy="direct_executable",
                app_def=None,
                canonical_id="compmgmt",
                installed_info=installed
            )
            assert success is True
            assert err is None
            mock_startfile.assert_called_once_with(r"C:\Windows\System32\compmgmt.msc")
