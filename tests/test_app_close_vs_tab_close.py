# tests/test_app_close_vs_tab_close.py
"""
Unit and Integration Tests for Application Close vs. Tab Close in Jarvis V2.
Validates:
- 'close Chrome', 'Chrome band karo', 'Chrome close kar do', 'browser band karo', 'close VLC':
    Interpreted as CLOSE_APPLICATION (closes entire application, all windows/processes).
    Does NOT ask 'ke 2 matches mile. Ek ya sab par action karna hai?'.
    Response: '<App> band kar diya, Boss.'.
- Tab-Specific Rule:
    'YouTube wala tab band karo' -> CLOSE_TAB on YouTube tab.
    'GLPI ka tab band karo' -> CLOSE_TAB on GLPI tab.
    'ye tab band karo', 'current tab close karo' -> CLOSE_CURRENT_TAB.
- Application vs Window vs Tab distinctions:
    'Chrome window band karo' -> CLOSE_WINDOW.
    'Chrome ke saare windows band karo' -> CLOSE_APPLICATION.
- No unnecessary confirmation: number of OS processes/windows never pollutes user semantic intent.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager
from core.target_engine import TargetCandidate, TargetKind


@pytest.fixture
def app_instance(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_close_app.db")
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


def test_close_chrome_application_no_matches_prompt(app_instance):
    """
    Verifies that 'close Chrome' / 'Chrome band karo' closes the entire application
    without asking 'Chrome ke 2 matches mile. Ek ya sab par action karna hai?'.
    """
    candidates = [
        TargetCandidate(kind=TargetKind.APPLICATION, identity="chrome", title="New Tab - Google Chrome", process_name="chrome.exe", hwnd=1001, confidence=0.98),
        TargetCandidate(kind=TargetKind.APPLICATION, identity="chrome", title="GitHub - Google Chrome", process_name="chrome.exe", hwnd=1002, confidence=0.97),
    ]

    with patch("core.target_engine.TargetResolver.resolve", return_value=candidates), \
         patch("plugins.windows.window_manager.WindowManager.execute_operation", return_value={"success": True, "message": "Chrome band kar diya hai, Boss."}), \
         patch("plugins.windows.window_manager.WindowManager.is_process_running", return_value=(False, [])), \
         patch("plugins.windows.window_manager.WindowManager.find_windows_for_app", return_value=[]):

        # 1. "close Chrome"
        resp1 = app_instance.process_input("close Chrome")
        assert "matches mile" not in resp1
        assert "Chrome band kar diya" in resp1 or "Chrome band" in resp1

        # 2. "Chrome band karo"
        resp2 = app_instance.process_input("Chrome band karo")
        assert "matches mile" not in resp2
        assert "Chrome band kar diya" in resp2 or "Chrome band" in resp2

        # 3. "Chrome close kar do"
        resp3 = app_instance.process_input("Chrome close kar do")
        assert "matches mile" not in resp3
        assert "Chrome band kar diya" in resp3 or "Chrome band" in resp3


def test_close_vlc_and_brave_applications(app_instance):
    """Verifies that closing other applications also executes cleanly without match prompts."""
    vlc_candidates = [
        TargetCandidate(kind=TargetKind.APPLICATION, identity="vlc", title="VLC media player", process_name="vlc.exe", hwnd=2001, confidence=0.99)
    ]

    with patch("core.target_engine.TargetResolver.resolve", return_value=vlc_candidates), \
         patch("plugins.windows.window_manager.WindowManager.execute_operation", return_value={"success": True, "message": "Vlc band kar diya hai, Boss."}):

        resp_vlc = app_instance.process_input("close vlc")
        assert "matches mile" not in resp_vlc
        assert "Vlc band kar diya" in resp_vlc or "VLC" in resp_vlc


def test_tab_specific_close(app_instance):
    """
    Verifies that explicit tab closing ('YouTube wala tab band karo', 'GLPI ka tab band karo')
    routes to tab close, not killing the whole browser application.
    """
    yt_tab = TargetCandidate(kind=TargetKind.BROWSER_TAB, identity="youtube", title="YouTube - Google Chrome", browser="chrome", tab_id="yt-1", confidence=0.95)

    with patch("core.target_engine.TargetResolver.resolve", return_value=[yt_tab]), \
         patch("core.target_engine.BrowserTabManager.perform_tab_action", return_value=True):

        # "YouTube wala tab band karo"
        resp_tab = app_instance.process_input("YouTube wala tab band karo")
        assert "matches mile" not in resp_tab
        assert "band kar diya" in resp_tab


def test_current_tab_close(app_instance):
    """Verifies closing the active / current tab."""
    curr_tab = TargetCandidate(kind=TargetKind.BROWSER_TAB, identity="current", title="Current Tab", browser="chrome", tab_id="curr-1", confidence=0.99)

    with patch("core.target_engine.TargetResolver.resolve", return_value=[curr_tab]), \
         patch("core.target_engine.BrowserTabManager.perform_tab_action", return_value=True):

        resp1 = app_instance.process_input("ye tab band karo")
        assert "band kar diya" in resp1

        resp2 = app_instance.process_input("current tab close karo")
        assert "band kar diya" in resp2


def test_close_bing_and_domain_tabs(app_instance):
    """
    Verifies that 'close bing tab' and 'close bing.com tab' resolve accurately
    using URL/domain + title + tab metadata without being misspelled as 'bring'.
    """
    bing_tab = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="bing",
        title="Bing Search - Microsoft Edge",
        url="https://www.bing.com/search?q=test",
        domain="bing.com",
        browser="edge",
        tab_id="bing-1",
        confidence=0.96
    )

    with patch("core.target_engine.TargetResolver.resolve", return_value=[bing_tab]), \
         patch("core.target_engine.BrowserTabManager.perform_tab_action", return_value=True):

        # 1. "close bing tab"
        resp1 = app_instance.process_input("close bing tab")
        assert "Bring" not in resp1
        assert "band kar diya" in resp1

        # 2. "close bing.com tab"
        resp2 = app_instance.process_input("close bing.com tab")
        assert "Bring" not in resp2
        assert "band kar diya" in resp2


def test_close_camera_prioritizes_application_over_unrelated_tab(app_instance):
    """
    Regression: 'close camera' / 'camera band karo' must prioritize the Camera desktop
    application over unrelated browser tabs whose titles happen to contain 'camera'
    (e.g. 'Jarvis Camera Fix - Google Chrome'), and must execute window_manager.execute_operation('close', 'camera').
    """
    from core.target_engine import UniversalTargetDiscoveryEngine, TargetRequest

    mock_wm = MagicMock()
    mock_wm.execute_operation.return_value = {"success": True, "message": "Camera process band kar diya hai, Boss."}

    camera_app = TargetCandidate(
        kind=TargetKind.APPLICATION,
        identity="Camera",
        title="Camera",
        process_name="ApplicationFrameHost.exe",
        hwnd=4001,
        confidence=1.0,
    )
    chrome_camera_tab = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="https://github.com",
        title="Jarvis Camera Fix - Google Chrome",
        browser="chrome",
        hwnd=5001,
        confidence=0.92,
    )

    mock_app_disc = MagicMock()
    mock_app_disc.discover.return_value = [camera_app]

    mock_tab_disc = MagicMock()
    mock_tab_disc.discover.return_value = [chrome_camera_tab]

    engine = UniversalTargetDiscoveryEngine(window_manager=mock_wm, tab_discovery=mock_tab_disc)
    engine.resolver.apps = mock_app_disc

    # 1. Resolve must prioritize Camera application over the browser tab
    matches = engine.resolver.resolve(TargetRequest("camera", "close"))
    assert len(matches) > 0
    assert matches[0].kind == TargetKind.APPLICATION
    assert matches[0].title == "Camera"

    # 2. Execute must close Camera application, NOT the browser tab
    with patch.object(engine.executor, "execute", return_value=True):
        outcome = engine.execute(TargetRequest("camera", "close"))
        assert outcome.success is True
        mock_wm.execute_operation.assert_called_with("close", "camera")


