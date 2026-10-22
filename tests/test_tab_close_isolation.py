# tests/test_tab_close_isolation.py
"""
Unit and Integration Tests for Browser Tab Close Isolation.

Guarantees:
1. A tab close command ('dhan tab close karo', 'close YouTube tab') NEVER calls
   window_manager.execute_operation("close", ...), which could terminate the entire
   browser window or kill browser processes.
2. BrowserTabManager NEVER presses Ctrl+W if the foreground window title does not
   match the target tab title (e.g. if the foreground tab is ChatGPT).
3. If the target tab is already active in the foreground, activate_tab does not
   send Ctrl+1 (which jumps to Tab 1 / ChatGPT) or cycle tabs unnecessarily.
4. Multiple matching tabs across same-app windows do not trigger application-wide
   window closing unless scope="all" is explicitly requested.
5. End-to-end processing of 'dhan tab close karo' safely isolates the Dhan tab.
"""

from unittest.mock import MagicMock, call, patch
import pytest

from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager
from core.target_engine import (
    ActionPlanner, BrowserTabManager, TargetCandidate, TargetKind,
    TargetRequest, UniversalTargetDiscoveryEngine,
)
from plugins.windows.window_manager import WindowManager, WindowState


@pytest.fixture
def core_app(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_tab_isolation.db")
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


def test_tab_close_never_calls_window_manager_execute_operation():
    """
    Closing a tab must NEVER call window_manager.execute_operation("close", ...),
    which sends WM_CLOSE to the entire browser window.
    """
    mock_wm = MagicMock(spec=WindowManager)
    engine = UniversalTargetDiscoveryEngine(window_manager=mock_wm)

    dhan_tab = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="https://dhan.co",
        title="Dhan - Online Stock Trading and Investing Platform for India - Google Chrome",
        url="https://dhan.co",
        browser="chrome",
        hwnd=131624,
        tab_index=1,
        confidence=0.95,
    )

    with patch.object(engine.resolver, "resolve", return_value=[dhan_tab]), \
         patch.object(engine.executor.tab_manager, "perform_tab_action", return_value=True):

        outcome = engine.execute(TargetRequest("dhan", "close"))
        assert outcome.success is True
        assert outcome.verified is True

        # CRITICAL ASSERTION: execute_operation("close", ...) must NOT have been called!
        for c in mock_wm.execute_operation.call_args_list:
            assert c[0][0] != "close", f"execute_operation('close') was unexpectedly called with {c}"


def test_app_close_still_calls_window_manager_execute_operation():
    """
    Closing an APPLICATION (e.g. 'close Chrome') MUST still call
    window_manager.execute_operation("close", "chrome") to clean up processes.
    """
    mock_wm = MagicMock(spec=WindowManager)
    mock_wm.execute_operation.return_value = {"success": True}
    engine = UniversalTargetDiscoveryEngine(window_manager=mock_wm)

    chrome_app = TargetCandidate(
        kind=TargetKind.APPLICATION,
        identity="chrome",
        title="Google Chrome",
        process_name="chrome.exe",
        hwnd=131624,
        confidence=0.98,
    )

    with patch.object(engine.resolver, "resolve", return_value=[chrome_app]), \
         patch.object(engine.executor, "execute", return_value=True):

        outcome = engine.execute(TargetRequest("chrome", "close"))
        assert outcome.success is True

        # Verify that execute_operation("close", ...) was indeed called for the app
        mock_wm.execute_operation.assert_called_with("close", "chrome")


def test_tab_close_aborts_if_foreground_title_does_not_match():
    """
    If the active window title is 'ChatGPT' while trying to close 'Dhan',
    BrowserTabManager MUST abort and NEVER send Ctrl+W!
    """
    mock_wm = MagicMock(spec=WindowManager)
    mock_wm.focus_window_safely.return_value = True
    tab_mgr = BrowserTabManager(window_manager=mock_wm)

    # Foreground window title is ChatGPT
    tab_mgr._window_title = MagicMock(return_value="ChatGPT: Chat, Work, Create & Code with AI - Google Chrome")
    tab_mgr.activate_tab = MagicMock(return_value=True)  # Pretend activate returned True
    tab_mgr._hotkey = MagicMock()
    tab_mgr._wait_for_tab_closed = MagicMock()

    dhan_tab = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="https://dhan.co",
        title="Dhan - Online Stock Trading and Investing Platform for India - Google Chrome",
        browser="chrome",
        hwnd=131624,
        tab_index=2,
    )

    success = tab_mgr.close_tab(dhan_tab)

    # Tab close MUST fail because the active tab is ChatGPT, not Dhan!
    assert success is False

    # Ctrl+W (0x11, 0x57) MUST NOT have been called!
    assert call(0x11, 0x57) not in tab_mgr._hotkey.call_args_list
    assert not tab_mgr._wait_for_tab_closed.called


def test_tab_close_already_active_does_not_cycle_to_first_tab():
    """
    If Dhan is already the active tab in the browser window, activate_tab must
    return True immediately without pressing Ctrl+1 (which would jump to Tab 1 / ChatGPT).
    """
    mock_wm = MagicMock(spec=WindowManager)
    mock_wm.focus_window_safely.return_value = True
    tab_mgr = BrowserTabManager(window_manager=mock_wm)

    # Window title is already Dhan
    tab_mgr._window_title = MagicMock(return_value="Dhan - Online Stock Trading and Investing Platform for India - Google Chrome")
    tab_mgr._hotkey = MagicMock()

    dhan_tab = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="https://dhan.co",
        title="Dhan - Online Stock Trading and Investing Platform for India - Google Chrome",
        browser="chrome",
        hwnd=131624,
        tab_index=2,
    )

    active = tab_mgr.activate_tab(dhan_tab)
    assert active is True

    # MUST NOT send Ctrl+1 (0x11, 0x31) because Dhan is already active!
    assert call(0x11, 0x31) not in tab_mgr._hotkey.call_args_list
    assert call(0x11, 0x09) not in tab_mgr._hotkey.call_args_list


def test_tab_close_multiple_windows_same_app_closes_only_one_tab():
    """
    If multiple Chrome windows have matching tabs, only ONE tab is closed
    by default (scope='auto'), not all windows.
    """
    mock_wm = MagicMock(spec=WindowManager)
    engine = UniversalTargetDiscoveryEngine(window_manager=mock_wm)

    tab_win1 = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="https://dhan.co/trading",
        title="Dhan - Online Stock Trading - Google Chrome",
        browser="chrome",
        hwnd=1001,
        confidence=0.92,
    )
    tab_win2 = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="https://dhan.co/home",
        title="Dhan - Home - Google Chrome",
        browser="chrome",
        hwnd=1002,
        confidence=0.92,
    )

    with patch.object(engine.resolver, "resolve", return_value=[tab_win1, tab_win2]), \
         patch.object(engine.executor, "execute", return_value=True) as mock_exec:

        outcome = engine.execute(TargetRequest("dhan", "close"))
        assert outcome.success is True

        # Exactly 1 tab must have been closed, not both windows!
        assert mock_exec.call_count == 1
        closed_target = mock_exec.call_args[0][1]
        assert closed_target.hwnd == 1001


def test_dhan_tab_close_karo_end_to_end(core_app):
    """
    Full end-to-end integration test: 'dhan tab close karo' correctly routes,
    closes only the Dhan tab, and does not kill Chrome or ChatGPT.
    """
    dhan_tab = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="https://dhan.co",
        title="Dhan - Online Stock Trading and Investing Platform for India - Google Chrome",
        browser="chrome",
        hwnd=131624,
        confidence=0.95,
    )

    with patch("core.target_engine.TargetResolver.resolve", return_value=[dhan_tab]), \
         patch("core.target_engine.BrowserTabManager.perform_tab_action", return_value=True), \
         patch("plugins.windows.window_manager.WindowManager.execute_operation") as mock_exec_op:

        response = core_app.process_input("dhan tab close karo")

        assert "band kar diya" in response or "Dhan" in response
        assert "matches mile" not in response

        # Ensure no window_manager close operation was triggered
        for c in mock_exec_op.call_args_list:
            assert c[0][0] != "close", f"execute_operation('close') was called: {c}"
