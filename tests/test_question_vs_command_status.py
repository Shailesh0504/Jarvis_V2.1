# tests/test_question_vs_command_status.py
import pytest
from unittest.mock import patch, MagicMock
from core.app import JarvisCore
from brain.semantic_parser import HinglishNLUParser
from plugins.windows.window_manager import WindowInfo
from core.target_engine import TargetCandidate, TargetKind


@pytest.fixture
def jarvis_core():
    core = JarvisCore()
    return core


def test_nlu_parser_distinguishes_question_from_command():
    """
    Verifies that questions ('open hai kya', 'chalu hai kya', 'is ... open')
    are parsed as CHECK_APP_STATUS actions instead of OPEN_APP / OPEN_WEBSITE.
    """
    # 1. Questions / Status inquiries
    q1 = HinglishNLUParser.parse("YouTube open hai kya")
    assert q1 is not None
    assert q1.action == "check_status"
    assert q1.parameters.get("target") == "youtube"

    q2 = HinglishNLUParser.parse("kya YouTube open hai")
    assert q2 is not None
    assert q2.action == "check_status"

    q3 = HinglishNLUParser.parse("is YouTube open?")
    assert q3 is not None
    assert q3.action == "check_status"

    q4 = HinglishNLUParser.parse("Excel chalu hai kya")
    assert q4 is not None
    assert q4.action == "check_status"
    assert q4.parameters.get("target") == "excel"

    q5 = HinglishNLUParser.parse("is notepad running")
    assert q5 is not None
    assert q5.action == "check_status"
    assert q5.parameters.get("target") == "notepad"

    # 2. Imperative Commands
    cmd1 = HinglishNLUParser.parse("YouTube open karo")
    assert cmd1 is not None
    assert cmd1.action == "open_youtube" or cmd1.intent in {"OPEN_APP", "OPEN_WEBSITE"}

    cmd2 = HinglishNLUParser.parse("open excel")
    assert cmd2 is not None
    assert cmd2.action in {"launch_app", "open_app"}


def test_youtube_open_hai_kya_when_open_in_browser(jarvis_core):
    """
    When user asks 'YouTube open hai kya' and YouTube tab is open in Brave,
    Jarvis replies that YouTube is open in Brave and DOES NOT launch or open anything.
    """
    candidate = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="101",
        title="YouTube - Watch Videos Online",
        url="https://youtube.com",
        browser="brave",
        confidence=1.0,
    )

    with patch.object(jarvis_core.target_engine.resolver, "resolve", return_value=[candidate]), \
         patch("webbrowser.open") as mock_web_open, \
         patch("subprocess.Popen") as mock_popen:

        resp = jarvis_core.process_input("YouTube open hai kya")
        assert "Haan" in resp
        assert "Youtube" in resp or "YouTube" in resp
        assert "Brave mein open hai" in resp
        mock_web_open.assert_not_called()
        mock_popen.assert_not_called()


def test_youtube_open_hai_kya_when_not_open(jarvis_core):
    """
    When user asks 'YouTube open hai kya' and YouTube is NOT open,
    Jarvis replies that YouTube is not open and DOES NOT open it.
    """
    with patch.object(jarvis_core.target_engine.resolver, "resolve", return_value=[]), \
         patch.object(jarvis_core.target_engine.window_manager, "find_windows_for_app", return_value=[]), \
         patch.object(jarvis_core.target_engine.window_manager, "is_process_running", return_value=(False, [])), \
         patch("webbrowser.open") as mock_web_open, \
         patch("subprocess.Popen") as mock_popen:

        resp = jarvis_core.process_input("YouTube open hai kya")
        assert "Nahi" in resp
        assert "abhi open nahi hai" in resp
        mock_web_open.assert_not_called()
        mock_popen.assert_not_called()


def test_excel_chalu_hai_kya_when_open(jarvis_core):
    """
    When user asks 'Excel chalu hai kya' and Excel window is open,
    Jarvis replies that Excel is open.
    """
    win = WindowInfo(hwnd=201, title="Sales_2026.xlsx - Excel", process_name="excel.exe", pid=3001)

    with patch.object(jarvis_core.target_engine.resolver, "resolve", return_value=[]), \
         patch.object(jarvis_core.target_engine.window_manager, "find_windows_for_app", return_value=[win]), \
         patch("subprocess.Popen") as mock_popen:

        resp = jarvis_core.process_input("Excel chalu hai kya")
        assert "Haan" in resp
        assert "Excel" in resp
        mock_popen.assert_not_called()
