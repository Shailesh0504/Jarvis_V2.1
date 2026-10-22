# tests/test_window_management_plugin.py
"""
Comprehensive tests for dedicated Window/Desktop Management Plugin,
deterministic window selection, system dialog avoidance ("Restore pages?"),
minimized window restoration, position verification, task planner step decomposition,
and multilingual natural language variations.
"""

from unittest.mock import MagicMock, patch
import pytest

from plugins.windows.plugin import WindowsPlugin
from plugins.windows.window_manager import WindowInfo, WindowManager, is_system_dialog_window
from core.desktop_task.planner import DesktopTaskPlanner
from core.desktop_task.executor import DesktopTaskExecutor
from core.desktop_task.context import DesktopExecutionContext
from brain.semantic_parser import HinglishNLUParser


# ---------------------------------------------------------------------------
# 1. Deterministic Selection & Dialog Filtering ("Restore pages?")
# ---------------------------------------------------------------------------

def test_deterministic_selection_prefers_normal_over_restore_pages():
    """Verify that when 'Restore pages?' dialog exists alongside a normal window, normal window is picked."""
    wm = WindowManager()
    restore_dlg = WindowInfo(
        hwnd=101,
        title="Restore pages?",
        process_name="brave.exe",
        pid=5001,
        is_dialog=True,
        is_foreground=False,
        rect=(100, 100, 350, 250),
        z_index=1
    )
    normal_tab = WindowInfo(
        hwnd=102,
        title="GitHub - Brave",
        process_name="brave.exe",
        pid=5001,
        is_dialog=False,
        is_foreground=False,
        rect=(0, 0, 1920, 1040),
        z_index=2
    )

    best = wm.select_best_window([restore_dlg, normal_tab], target_app="brave")
    assert best is not None
    assert best.hwnd == 102
    assert best.title == "GitHub - Brave"


def test_deterministic_selection_multiple_windows_prefers_foreground():
    """Verify that among multiple normal windows of the same app, the foreground window is preferred."""
    wm = WindowManager()
    win_bg = WindowInfo(
        hwnd=201,
        title="Google - Brave",
        process_name="brave.exe",
        pid=5001,
        is_foreground=False,
        rect=(0, 0, 1920, 1040),
        z_index=2
    )
    win_fg = WindowInfo(
        hwnd=202,
        title="YouTube - Brave",
        process_name="brave.exe",
        pid=5001,
        is_foreground=True,
        rect=(0, 0, 1920, 1040),
        z_index=1
    )

    best = wm.select_best_window([win_bg, win_fg], target_app="brave")
    assert best is not None
    assert best.hwnd == 202
    assert best.title == "YouTube - Brave"


def test_deterministic_selection_prefers_non_minimized_usable_window():
    """Verify visible non-minimized usable window is preferred over a minimized window."""
    wm = WindowManager()
    minimized_win = WindowInfo(
        hwnd=301,
        title="Doc 1 - Brave",
        process_name="brave.exe",
        pid=5001,
        is_minimized=True,
        is_foreground=False,
        z_index=1
    )
    visible_win = WindowInfo(
        hwnd=302,
        title="Doc 2 - Brave",
        process_name="brave.exe",
        pid=5001,
        is_minimized=False,
        is_foreground=False,
        rect=(0, 0, 1200, 800),
        z_index=2
    )

    best = wm.select_best_window([minimized_win, visible_win], target_app="brave")
    assert best is not None
    assert best.hwnd == 302


def test_system_dialog_detection_patterns():
    """Test standard dialog detection helper."""
    assert is_system_dialog_window("Restore pages?") is True
    assert is_system_dialog_window("Restore pages") is True
    assert is_system_dialog_window("Open File") is True
    assert is_system_dialog_window("Save As") is True
    assert is_system_dialog_window("Untitled - Notepad", class_name="#32770") is True
    assert is_system_dialog_window("Google - Google Chrome") is False
    assert is_system_dialog_window("YouTube - Brave") is False


# ---------------------------------------------------------------------------
# 2. Window Positioning, Snapping & Verification
# ---------------------------------------------------------------------------

def test_snap_window_left_and_position_verification():
    """Test snap_window to left half with position verification returning structured result."""
    wm = WindowManager()
    win = WindowInfo(hwnd=401, title="New Tab - Brave", process_name="brave.exe", pid=6001, is_minimized=True)

    with patch.object(wm, "find_windows_for_app", return_value=[win]):
        res = wm.snap_window(hwnd_or_app=401, position="left", app_name="brave")

    assert res["success"] is True
    assert res["selected_hwnd"] == 401
    assert res["requested_position"] == "left"
    assert res["verification_status"] is True
    assert "actual_position" in res
    assert res["actual_position"]["x"] == 0
    expected_w = wm.get_work_area(401)[2] // 2
    assert res["actual_position"]["width"] == expected_w


def test_position_window_multiple_brave_windows_does_not_ask_clarification():
    """Test that position_window does NOT stop with clarification when multiple Brave windows exist."""
    wm = WindowManager()
    dlg = WindowInfo(hwnd=501, title="Restore pages?", process_name="brave.exe", pid=7001, is_dialog=True)
    normal = WindowInfo(hwnd=502, title="Dashboard - Brave", process_name="brave.exe", pid=7001, is_dialog=False)

    with patch.object(wm, "find_windows_for_app", return_value=[dlg, normal]):
        res = wm.position_window(app_name="brave", position="left")

    assert res["success"] is True
    assert res.get("multiple") is not True
    assert res["selected_hwnd"] == 502
    assert res["title"] == "Dashboard - Brave"
    assert res["verification_status"] is True


def test_missing_application_handling():
    """Test querying/snapping an application that is not running and cannot be found."""
    wm = WindowManager()

    with patch.object(wm, "find_windows_for_app", return_value=[]), \
         patch.object(wm, "is_process_running", return_value=(False, [])):
        res = wm.position_window(app_name="nonexistent_browser", position="left", launch_if_needed=False)

    assert res["success"] is False
    assert res.get("running") is False
    assert "open nahi hai" in res["message"]


# ---------------------------------------------------------------------------
# 3. Dedicated WindowsPlugin Reusable Actions
# ---------------------------------------------------------------------------

def test_windows_plugin_reusable_actions_get_windows():
    """Test GET_WINDOWS action in WindowsPlugin."""
    plugin = WindowsPlugin()
    fake_win = WindowInfo(hwnd=801, title="Chrome Main", process_name="chrome.exe", pid=123)

    with patch.object(plugin.window_manager, "list_all_windows", return_value=[fake_win]):
        res = plugin.execute("GET_WINDOWS", {})
        assert res.success is True
        assert res.data["count"] == 1
        assert res.data["windows"][0]["hwnd"] == 801


def test_windows_plugin_reusable_actions_find_window():
    """Test FIND_WINDOW action in WindowsPlugin."""
    plugin = WindowsPlugin()
    dlg = WindowInfo(hwnd=802, title="Restore pages?", process_name="brave.exe", pid=124, is_dialog=True)
    normal = WindowInfo(hwnd=803, title="Google Search - Brave", process_name="brave.exe", pid=124)

    with patch.object(plugin.window_manager, "find_windows_for_app", return_value=[dlg, normal]):
        res = plugin.execute("FIND_WINDOW", {"app_name": "brave"})
        assert res.success is True
        assert res.data["selected_hwnd"] == 803
        assert res.data["title"] == "Google Search - Brave"


def test_windows_plugin_reusable_actions_snap_left_and_right():
    """Test SNAP_LEFT and SNAP_RIGHT actions in WindowsPlugin."""
    plugin = WindowsPlugin()
    win_brave = WindowInfo(hwnd=901, title="Brave", process_name="brave.exe", pid=333)
    win_chrome = WindowInfo(hwnd=902, title="Chrome", process_name="chrome.exe", pid=444)

    with patch.object(plugin.window_manager, "list_all_windows", return_value=[win_brave, win_chrome]):
        res_left = plugin.execute("SNAP_LEFT", {"hwnd": 901, "app_name": "brave"})
        assert res_left.success is True
        assert res_left.data["selected_hwnd"] == 901
        assert res_left.data["verification_status"] is True

        res_right = plugin.execute("SNAP_RIGHT", {"hwnd": 902, "app_name": "chrome"})
        assert res_right.success is True
        assert res_right.data["selected_hwnd"] == 902
        assert res_right.data["verification_status"] is True


def test_windows_plugin_verify_window_position_action():
    """Test VERIFY_WINDOW_POSITION action in WindowsPlugin."""
    plugin = WindowsPlugin()
    work_area = plugin.window_manager.get_work_area(999)
    wx, wy, ww, wh = work_area
    expected_w = ww // 2
    plugin.window_manager._mock_rects[999] = (wx, wy, wx + expected_w, wy + wh)

    res = plugin.execute("VERIFY_WINDOW_POSITION", {
        "hwnd": 999,
        "expected_position": "left",
        "tolerance": 25
    })
    assert res.success is True
    assert res.data["verification_status"] is True


# ---------------------------------------------------------------------------
# 4. Core Task Planner Step Decomposition
# ---------------------------------------------------------------------------

def test_task_planner_decomposes_multi_window_layout():
    """Verify Core Task Planner decomposes layout into atomic FIND -> SNAP -> VERIFY steps."""
    planner = DesktopTaskPlanner()
    raw_cmd = "Brave ko left me or Chrome ko right me open karo"

    assert planner.can_handle(raw_cmd) is True
    plan = planner.parse(raw_cmd)
    assert plan is not None
    assert plan.intent_type == "WINDOW_LAYOUT"
    assert len(plan.steps) == 6

    # Brave steps
    assert plan.steps[0].action == "FIND_WINDOW"
    assert plan.steps[0].parameters["app_name"] == "brave"
    assert plan.steps[0].capability == "windows"

    assert plan.steps[1].action == "SNAP_LEFT"
    assert plan.steps[1].parameters["hwnd"] == "$step_1.selected_hwnd"
    assert plan.steps[1].capability == "windows"

    assert plan.steps[2].action == "VERIFY_WINDOW_POSITION"
    assert plan.steps[2].parameters["hwnd"] == "$step_1.selected_hwnd"
    assert plan.steps[2].parameters["expected_position"] == "left"
    assert plan.steps[2].capability == "windows"

    # Chrome steps
    assert plan.steps[3].action == "FIND_WINDOW"
    assert plan.steps[3].parameters["app_name"] == "chrome"
    assert plan.steps[3].capability == "windows"

    assert plan.steps[4].action == "SNAP_RIGHT"
    assert plan.steps[4].parameters["hwnd"] == "$step_4.selected_hwnd"
    assert plan.steps[4].capability == "windows"

    assert plan.steps[5].action == "VERIFY_WINDOW_POSITION"
    assert plan.steps[5].parameters["hwnd"] == "$step_4.selected_hwnd"
    assert plan.steps[5].parameters["expected_position"] == "right"
    assert plan.steps[5].capability == "windows"


def test_task_executor_runs_window_layout_plan():
    """Verify DesktopTaskExecutor executes the decomposed atomic window steps and synthesizes response."""
    planner = DesktopTaskPlanner()
    context = DesktopExecutionContext()
    executor = DesktopTaskExecutor(context=context)

    plan = planner.parse("Brave ko left me or Chrome ko right me open karo")
    assert plan is not None

    win_brave = WindowInfo(hwnd=111, title="Brave Tab", process_name="brave.exe", pid=100)
    win_chrome = WindowInfo(hwnd=222, title="Chrome Tab", process_name="chrome.exe", pid=200)

    with patch.object(WindowManager, "list_all_windows", return_value=[win_brave, win_chrome]), \
         patch.object(WindowManager, "find_windows_for_app", side_effect=lambda app: [win_brave] if "brave" in app else [win_chrome]):
        report = executor.execute(plan)

    assert report.success is True
    assert len(report.step_results) == 6
    assert all(r.success for r in report.step_results)
    assert "Brave (left)" in report.response_message
    assert "Chrome (right)" in report.response_message


# ---------------------------------------------------------------------------
# 5. Multilingual Natural Language Parsing (Hinglish / Hindi / English)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phrase, expected_apps, expected_positions", [
    ("Brave ko left me or Chrome ko right me open karo", ["brave", "chrome"], ["left", "right"]),
    ("Brave left Chrome right", ["brave", "chrome"], ["left", "right"]),
    ("Brave ko left side karo aur Chrome ko right side", ["brave", "chrome"], ["left", "right"]),
    ("Chrome right me aur Brave left me", ["chrome", "brave"], ["right", "left"]),
    ("Chrome left aur Notepad right", ["chrome", "notepad"], ["left", "right"]),
])
def test_semantic_parser_window_layout_variations(phrase, expected_apps, expected_positions):
    """Test that all specified Hindi, Hinglish, and English phrasing variations parse correctly."""
    action = HinglishNLUParser.parse(phrase)
    assert action is not None
    assert action.service == "windows"
    assert action.action == "layout_windows"

    items = action.parameters.get("items", [])
    assert len(items) == len(expected_apps)
    for idx, expected_app in enumerate(expected_apps):
        assert items[idx]["app_name"] == expected_app
        assert items[idx]["position"] == expected_positions[idx]
