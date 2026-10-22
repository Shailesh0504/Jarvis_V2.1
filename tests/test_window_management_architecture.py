# tests/test_window_management_architecture.py
"""
Unit and Regression Tests for Generic WindowManager, ApplicationController,
and Core Brain NLU Window Operations across all Windows applications.
"""

import pytest
from unittest.mock import patch, MagicMock
from brain.semantic_parser import HinglishNLUParser, SemanticAction
from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager
from plugins.windows.plugin import WindowsPlugin
from plugins.windows.window_manager import WindowManager, WindowInfo


@pytest.fixture
def jarvis_app(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_window.db")
    mem = MemoryManager(db_path=db_path)
    llm = MockLLMProvider()
    resp_gen = ResponseGenerator(llm_provider=llm)
    plugins = PluginManager(plugin_dir="plugins")
    plugins.discover_and_load()

    core.initialize_subsystems(
        memory_manager=mem,
        learning_manager=None,
        brain=resp_gen,
        classifier=None,
        plugin_manager=plugins,
        response_generator=resp_gen
    )
    return core


def test_nlu_parser_window_operations_all_apps():
    """Verify HinglishNLUParser parses natural language window operations for all applications."""
    # 1. Brave maximize
    act_brave = HinglishNLUParser.parse("maximize Brave browser")
    assert act_brave is not None
    assert act_brave.intent == "WINDOW_MAXIMIZE"
    assert act_brave.service == "windows"
    assert act_brave.action == "maximize_window"
    assert act_brave.parameters["app_name"] == "brave"
    assert act_brave.parameters["operation"] == "maximize"

    act_brave_hi = HinglishNLUParser.parse("Brave ko maximize karo")
    assert act_brave_hi is not None
    assert act_brave_hi.intent == "WINDOW_MAXIMIZE"
    assert act_brave_hi.parameters["app_name"] == "brave"

    # 2. Chrome fullscreen/maximize
    act_chrome = HinglishNLUParser.parse("Chrome full screen karo")
    assert act_chrome is not None
    assert act_chrome.intent == "WINDOW_MAXIMIZE"
    assert act_chrome.parameters["app_name"] == "chrome"

    # 3. VLC minimize
    act_vlc = HinglishNLUParser.parse("VLC ko minimize karo")
    assert act_vlc is not None
    assert act_vlc.intent == "WINDOW_MINIMIZE"
    assert act_vlc.service == "windows"
    assert act_vlc.action == "minimize_window"
    assert act_vlc.parameters["app_name"] == "vlc"

    # 4. Excel restore
    act_excel = HinglishNLUParser.parse("Excel window restore karo")
    assert act_excel is not None
    assert act_excel.intent == "WINDOW_RESTORE"
    assert act_excel.service == "windows"
    assert act_excel.action == "restore_window"
    assert act_excel.parameters["app_name"] == "excel"

    # 5. Notepad close
    act_notepad = HinglishNLUParser.parse("Notepad ko close karo")
    assert act_notepad is not None
    assert act_notepad.intent == "WINDOW_CLOSE"
    assert act_notepad.service == "windows"
    assert act_notepad.action == "close_app"
    assert act_notepad.parameters["app_name"] == "notepad"

    # 6. VS Code focus
    act_code = HinglishNLUParser.parse("VS Code ko focus karo")
    assert act_code is not None
    assert act_code.intent == "WINDOW_FOCUS"
    assert act_code.service == "windows"
    assert act_code.action == "focus_window"
    assert act_code.parameters["app_name"] == "code"

    # 7. Browser foreground
    act_browser = HinglishNLUParser.parse("browser ko foreground mein lao")
    assert act_browser is not None
    assert act_browser.intent == "WINDOW_FOCUS"
    assert act_browser.service == "windows"
    assert act_browser.parameters["app_name"] == "browser"

    # 8. Active/current window maximize
    act_current = HinglishNLUParser.parse("is window ko maximize karo")
    assert act_current is not None
    assert act_current.intent == "WINDOW_MAXIMIZE"
    assert act_current.parameters["app_name"] == "current"

    # 9. Arbitrary applications (Photoshop, Telegram, Discord)
    act_ps = HinglishNLUParser.parse("Photoshop ko maximize karo")
    assert act_ps is not None
    assert act_ps.intent == "WINDOW_MAXIMIZE"
    assert act_ps.parameters["app_name"] == "photoshop"

    act_tg = HinglishNLUParser.parse("Telegram ko minimize karo")
    assert act_tg is not None
    assert act_tg.intent == "WINDOW_MINIMIZE"
    assert act_tg.parameters["app_name"] == "telegram"


def test_nlu_parser_window_layout_and_positions():
    """Verify HinglishNLUParser parses single and multi-window positioning and tiling commands."""
    # 1. Multi-window layout: "Chrome ko left mein aur Brave ko right side mein open karo"
    act_multi = HinglishNLUParser.parse("Chrome ko left mein aur Brave ko right side mein open karo")
    assert act_multi is not None
    assert act_multi.intent == "WINDOW_LAYOUT"
    assert act_multi.service == "windows"
    assert act_multi.action == "layout_windows"
    items = act_multi.parameters["items"]
    assert len(items) == 2
    assert items[0]["app_name"] == "chrome"
    assert items[0]["position"] == "left"
    assert items[0]["launch_if_needed"] is True
    assert items[1]["app_name"] == "brave"
    assert items[1]["position"] == "right"
    assert items[1]["launch_if_needed"] is True

    # 2. Single window position: "VLC left side mein karo" / "VLC ko left mein rakho"
    act_vlc = HinglishNLUParser.parse("VLC left side mein karo")
    assert act_vlc is not None
    assert act_vlc.intent == "WINDOW_POSITION"
    assert act_vlc.parameters["app_name"] == "vlc"
    assert act_vlc.parameters["position"] == "left"

    act_vlc2 = HinglishNLUParser.parse("VLC ko left mein rakho")
    assert act_vlc2 is not None
    assert act_vlc2.intent == "WINDOW_POSITION"
    assert act_vlc2.parameters["app_name"] == "vlc"
    assert act_vlc2.parameters["position"] == "left"

    # 3. Single window position: "Excel ko right mein rakho" / "Excel ko right side karo"
    act_excel = HinglishNLUParser.parse("Excel ko right mein rakho")
    assert act_excel is not None
    assert act_excel.intent == "WINDOW_POSITION"
    assert act_excel.parameters["app_name"] == "excel"
    assert act_excel.parameters["position"] == "right"

    act_excel2 = HinglishNLUParser.parse("Excel ko right side karo")
    assert act_excel2 is not None
    assert act_excel2.intent == "WINDOW_POSITION"
    assert act_excel2.parameters["app_name"] == "excel"
    assert act_excel2.parameters["position"] == "right"

    # 4. Corner position: "Notepad ko left top corner mein rakho" / "Notepad ko top left mein rakho"
    act_np = HinglishNLUParser.parse("Notepad ko left top corner mein rakho")
    assert act_np is not None
    assert act_np.intent == "WINDOW_POSITION"
    assert act_np.parameters["app_name"] == "notepad"
    assert act_np.parameters["position"] == "top_left"

    act_np2 = HinglishNLUParser.parse("Notepad ko top left mein rakho")
    assert act_np2 is not None
    assert act_np2.intent == "WINDOW_POSITION"
    assert act_np2.parameters["app_name"] == "notepad"
    assert act_np2.parameters["position"] == "top_left"

    # 5. Side by side: "do windows ko side by side karo" / "side by side karo"
    act_sbs = HinglishNLUParser.parse("do windows ko side by side karo")
    assert act_sbs is not None
    assert act_sbs.intent == "WINDOW_LAYOUT"
    assert act_sbs.parameters.get("layout_type") == "side_by_side"

    # 6. Active window shift: "is window ko right side shift karo"
    act_shift = HinglishNLUParser.parse("is window ko right side shift karo")
    assert act_shift is not None
    assert act_shift.intent == "WINDOW_POSITION"
    assert act_shift.parameters["app_name"] == "current"
    assert act_shift.parameters["position"] == "right"

    # 7. Tri-window layout: "Chrome left, VLC right aur Excel bottom"
    act_tri = HinglishNLUParser.parse("Chrome left, VLC right aur Excel bottom")
    assert act_tri is not None
    assert act_tri.intent == "WINDOW_LAYOUT"
    assert len(act_tri.parameters["items"]) == 3
    assert act_tri.parameters["items"][0]["app_name"] == "chrome"
    assert act_tri.parameters["items"][0]["position"] == "left"
    assert act_tri.parameters["items"][1]["app_name"] == "vlc"
    assert act_tri.parameters["items"][1]["position"] == "right"
    assert act_tri.parameters["items"][2]["app_name"] == "excel"
    assert act_tri.parameters["items"][2]["position"] == "bottom"

    # 8. Arbitrary unknown apps: "Photoshop ko left mein rakho"
    act_ps = HinglishNLUParser.parse("Photoshop ko left mein rakho")
    assert act_ps is not None
    assert act_ps.intent == "WINDOW_POSITION"
    assert act_ps.parameters["app_name"] == "photoshop"
    assert act_ps.parameters["position"] == "left"


def test_window_manager_operations():
    """Verify WindowManager executes window operations on target windows."""
    wm = WindowManager()
    fake_window = WindowInfo(hwnd=12345, title="Brave Browser", process_name="brave.exe", pid=999)

    # 1. Maximize
    with patch.object(wm, "find_windows_for_app", return_value=[fake_window]), \
         patch.object(wm, "_user32") as mock_u32:
        res = wm.execute_operation("maximize", "brave")
        assert res["success"] is True
        assert res["operation"] == "maximize"
        assert "Brave window maximize kar di hai" in res["message"]
        from unittest.mock import call
        assert call(12345, 3) in mock_u32.ShowWindow.call_args_list

    # 2. Minimize
    with patch.object(wm, "find_windows_for_app", return_value=[fake_window]), \
         patch.object(wm, "_user32") as mock_u32:
        res = wm.execute_operation("minimize", "brave")
        assert res["success"] is True
        assert res["operation"] == "minimize"
        assert "Brave window minimize kar di hai" in res["message"]
        mock_u32.ShowWindow.assert_called_once_with(12345, 6)

    # 3. Restore
    with patch.object(wm, "find_windows_for_app", return_value=[fake_window]), \
         patch.object(wm, "_user32") as mock_u32:
        res = wm.execute_operation("restore", "brave")
        assert res["success"] is True
        assert res["operation"] == "restore"
        assert "Brave window restore kar di hai" in res["message"]
        mock_u32.ShowWindow.assert_called_once_with(12345, 9)

    # 4. Focus / Foreground
    with patch.object(wm, "find_windows_for_app", return_value=[fake_window]), \
         patch.object(wm, "_user32") as mock_u32:
        res = wm.execute_operation("focus", "brave")
        assert res["success"] is True
        assert res["operation"] == "focus"
        assert "Brave ko foreground mein le aaya hoon" in res["message"]
        mock_u32.ShowWindow.assert_called_once_with(12345, 5)

    # 5. Close
    with patch.object(wm, "find_windows_for_app", return_value=[fake_window]), \
         patch.object(wm, "_user32") as mock_u32:
        res = wm.execute_operation("close", "brave")
        assert res["success"] is True
        assert res["operation"] == "close"
        assert "Brave band kar diya hai" in res["message"]
        from unittest.mock import call
        assert call(12345, 0x0010, 0, 0) in mock_u32.PostMessageW.call_args_list


def test_window_manager_position_and_layout():
    """Verify WindowManager positions windows with correct work-area calculations."""
    wm = WindowManager()
    fake_chrome = WindowInfo(hwnd=1001, title="Google Chrome", process_name="chrome.exe", pid=201)
    fake_brave = WindowInfo(hwnd=1002, title="Brave", process_name="brave.exe", pid=202)
    fake_np = WindowInfo(hwnd=1003, title="Notepad", process_name="notepad.exe", pid=203)

    # Position Chrome Left: (0, 0, 960, 1080)
    with patch.object(wm, "find_windows_for_app", return_value=[fake_chrome]), \
         patch.object(wm, "get_work_area", return_value=(0, 0, 1920, 1080)), \
         patch.object(wm, "_user32") as mock_u32:
        res = wm.position_window("chrome", "left")
        assert res["success"] is True
        assert res["rect"] == {"x": 0, "y": 0, "width": 960, "height": 1080}
        mock_u32.ShowWindow.assert_called_once_with(1001, 9)  # SW_RESTORE
        mock_u32.MoveWindow.assert_called_once_with(1001, 0, 0, 960, 1080, True)

    # Position Brave Right: (960, 0, 960, 1080)
    with patch.object(wm, "find_windows_for_app", return_value=[fake_brave]), \
         patch.object(wm, "get_work_area", return_value=(0, 0, 1920, 1080)), \
         patch.object(wm, "_user32") as mock_u32:
        res = wm.position_window("brave", "right")
        assert res["success"] is True
        assert res["rect"] == {"x": 960, "y": 0, "width": 960, "height": 1080}
        mock_u32.MoveWindow.assert_called_once_with(1002, 960, 0, 960, 1080, True)

    # Position Notepad Top Left: (0, 0, 960, 540)
    with patch.object(wm, "find_windows_for_app", return_value=[fake_np]), \
         patch.object(wm, "get_work_area", return_value=(0, 0, 1920, 1080)), \
         patch.object(wm, "_user32") as mock_u32:
        res = wm.position_window("notepad", "top_left")
        assert res["success"] is True
        assert res["rect"] == {"x": 0, "y": 0, "width": 960, "height": 540}
        mock_u32.MoveWindow.assert_called_once_with(1003, 0, 0, 960, 540, True)


def test_window_manager_disambiguation_multiple_windows():
    """Verify WindowManager requests clarification when multiple distinct windows are open."""
    wm = WindowManager()
    win1 = WindowInfo(hwnd=101, title="Q1_Report.xlsx - Excel", process_name="excel.exe", pid=1001)
    win2 = WindowInfo(hwnd=102, title="Budget_2026.xlsx - Excel", process_name="excel.exe", pid=1001)

    with patch.object(wm, "find_windows_for_app", return_value=[win1, win2]):
        res = wm.execute_operation("maximize", "excel")
        assert res["success"] is False
        assert res.get("multiple") is True
        assert "multiple windows open hain" in res["message"]
        assert "Kaunsi window use karni hai" in res["message"]


def test_window_manager_not_running_handling():
    """Verify WindowManager handles not running application gracefully."""
    wm = WindowManager()

    with patch.object(wm, "find_windows_for_app", return_value=[]), \
         patch.object(wm, "is_process_running", return_value=(False, [])):
        res = wm.execute_operation("maximize", "nonexistent_app")
        assert res["success"] is False
        assert "open nahi hai" in res["message"]


def test_end_to_end_window_commands_no_fallback_prompt(jarvis_app):
    """End-to-end test proving window & layout commands do NOT fall into the generic conversation fallback."""
    fake_chrome = WindowInfo(hwnd=501, title="Google Chrome", process_name="chrome.exe", pid=101)
    fake_brave = WindowInfo(hwnd=502, title="Brave", process_name="brave.exe", pid=102)
    fake_vlc = WindowInfo(hwnd=503, title="VLC", process_name="vlc.exe", pid=103)
    fake_excel = WindowInfo(hwnd=504, title="Excel", process_name="excel.exe", pid=104)
    fake_np = WindowInfo(hwnd=505, title="Notepad", process_name="notepad.exe", pid=105)

    def mock_find_win(app_name):
        mapping = {
            "chrome": [fake_chrome],
            "brave": [fake_brave],
            "vlc": [fake_vlc],
            "excel": [fake_excel],
            "notepad": [fake_np],
            "current": [fake_chrome]
        }
        return mapping.get(app_name.lower(), [fake_chrome])

    with patch("plugins.windows.window_manager.WindowManager.find_windows_for_app", side_effect=mock_find_win), \
         patch("plugins.windows.window_manager.WindowManager._user32"):

        # 1. Multi-window layout: "Chrome ko left mein aur Brave ko right side mein open karo"
        resp1 = jarvis_app.process_input("Chrome ko left mein aur Brave ko right side mein open karo")
        assert "Main samajh gaya Boss! Bataiye 'chrome ko left mein" not in resp1
        assert "Chrome (left)" in resp1
        assert "Brave (right)" in resp1

        # 2. Position VLC: "VLC left side mein karo"
        resp2 = jarvis_app.process_input("VLC left side mein karo")
        assert "Main samajh gaya Boss" not in resp2
        assert "Vlc ko left side mein set kar diya hai" in resp2

        # 3. Position Excel: "Excel ko right side karo"
        resp3 = jarvis_app.process_input("Excel ko right side karo")
        assert "Main samajh gaya Boss" not in resp3
        assert "Excel ko right side mein set kar diya hai" in resp3

        # 4. Position Notepad Top Left: "Notepad ko top left mein rakho"
        resp4 = jarvis_app.process_input("Notepad ko top left mein rakho")
        assert "Main samajh gaya Boss" not in resp4
        assert "Notepad ko top_left side mein set kar diya hai" in resp4


def test_open_setting_and_system_apps(jarvis_app):
    """Verifies that 'open setting', 'settings kholo', and app launching work cleanly."""
    with patch("subprocess.Popen") as mock_popen:
        # 1. Open Setting
        resp1 = jarvis_app.process_input("open setting")
        assert "Main samajh gaya Boss! Bataiye" not in resp1
        assert "Launched 'settings'" in resp1 or "settings" in resp1.lower()

        # 2. Settings kholo
        resp2 = jarvis_app.process_input("settings kholo")
        assert "Main samajh gaya Boss! Bataiye" not in resp2

        # 3. Open Calculator
        resp3 = jarvis_app.process_input("open calculator")
        assert "Main samajh gaya Boss! Bataiye" not in resp3
        assert "calc" in resp3.lower() or "calculator" in resp3.lower()

        # 4. Open Notepad
        resp4 = jarvis_app.process_input("notepad kholo")
        assert "Main samajh gaya Boss! Bataiye" not in resp4
        assert "notepad" in resp4.lower()


def test_brave_browser_maximize_without_tab_disambiguation_prompt(jarvis_app):
    """
    Verifies that 'brave browser ko maximize karo' maximizes Brave directly
    without asking '3 matches mile. Ek ya sab par action karna hai?' even when multiple Brave tabs exist.
    """
    brave_win = WindowInfo(hwnd=501, title="YouTube - Brave", process_name="brave.exe", pid=2001)
    with patch.object(jarvis_app.target_engine.window_manager, "list_all_windows", return_value=[brave_win]), \
         patch.object(jarvis_app.target_engine.window_manager, "find_windows_for_app", return_value=[brave_win]), \
         patch("ctypes.windll.user32.ShowWindow") as mock_show, \
         patch("ctypes.windll.user32.SetForegroundWindow") as mock_fg:
        
        resp = jarvis_app.process_input("brave browser ko maximize karo")
        assert "matches mile" not in resp
        assert "Ek ya sab" not in resp
        assert "brave" in resp.lower() and ("maximize" in resp.lower() or "bada" in resp.lower())

