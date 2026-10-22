# tests/test_browser_tab_window_state.py
"""
Regression and unit tests for browser tab operations with exact window state preservation.
Verifies that closing, activating, or switching tabs never unintentionally changes
browser window size, position, monitor, or maximized/minimized state across all browsers and websites.
"""

from unittest.mock import MagicMock, call, patch
import pytest

from core.target_engine import (
    ActionOutcome, BrowserTabDiscovery, BrowserTabManager, TargetCandidate,
    TargetKind, TargetRequest, UniversalTargetDiscoveryEngine,
)
from plugins.windows.window_manager import WindowInfo, WindowManager, WindowState


def create_mock_tab(title: str, url: str, browser: str = "brave", hwnd: int = 100, index: int = 0, backend: str = "native") -> TargetCandidate:
    from urllib.parse import urlsplit
    return TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity=url,
        title=title,
        url=url,
        domain=urlsplit(url).hostname or "",
        browser=browser,
        hwnd=hwnd,
        tab_index=index,
        tab_id=f"{browser}-{hwnd}-{index}",
        backend=backend,
        confidence=1.0,
    )


def test_closing_background_youtube_tab_while_brave_is_maximized(caplog):
    """
    Test 1: Closing a background YouTube tab while Brave is maximized.
    Verifies that Brave starts maximized, the tab is closed, and Brave remains maximized afterward.
    """
    caplog.set_level("INFO")
    mock_wm = MagicMock(spec=WindowManager)
    
    maximized_state = WindowState(
        hwnd=101,
        process_name="brave.exe",
        browser="brave",
        title="Active Tab - Brave",
        is_maximized=True,
        is_minimized=False,
        is_restored=False,
        position=(-8, -8),
        size=(1936, 1056),
        rect=(-8, -8, 1928, 1048),
        restore_bounds=(100, 100, 1200, 800),
        monitor=1,
    )
    
    mock_wm.capture_window_state.return_value = maximized_state
    mock_wm.verify_window_state.return_value = True

    tab_mgr = BrowserTabManager(window_manager=mock_wm)
    tab_mgr._activate_tab_internal = MagicMock(return_value=True)
    tab_mgr._hotkey = MagicMock()
    tab_mgr._wait_for_tab_closed = MagicMock(return_value=True)

    yt_tab = create_mock_tab("Dheere Dheere Pyar - YouTube - Brave", "https://youtube.com/watch?v=123", browser="brave", hwnd=101, index=3)

    success = tab_mgr.close_tab(yt_tab)
    assert success is True

    # Verify flow
    mock_wm.capture_window_state.assert_called_once_with(101)
    mock_wm.focus_window_safely.assert_called_with(101)
    mock_wm.restore_window_state.assert_called_once_with(maximized_state)
    mock_wm.verify_window_state.assert_called_once_with(maximized_state)

    # Verify structured logs
    logs = caplog.text
    assert "TAB_OPERATION_STARTED action=close_tab" in logs
    assert "TAB_ACTION_COMPLETED action=close_tab success=True" in logs


def test_closing_tab_while_brave_is_restored_preserves_exact_size_and_position(caplog):
    """
    Test 2: Closing a tab while Brave is restored with specific custom bounds.
    Verifies that exact position, width, height, and restored bounds are preserved.
    """
    caplog.set_level("INFO")
    mock_wm = MagicMock(spec=WindowManager)

    restored_state = WindowState(
        hwnd=102,
        process_name="brave.exe",
        browser="brave",
        title="GitHub - Brave",
        is_maximized=False,
        is_minimized=False,
        is_restored=True,
        position=(150, 75),
        size=(1024, 768),
        rect=(150, 75, 1174, 843),
        restore_bounds=(150, 75, 1024, 768),
        monitor=1,
    )

    mock_wm.capture_window_state.return_value = restored_state
    mock_wm.verify_window_state.return_value = True

    tab_mgr = BrowserTabManager(window_manager=mock_wm)
    tab_mgr._activate_tab_internal = MagicMock(return_value=True)
    tab_mgr._hotkey = MagicMock()
    tab_mgr._wait_for_tab_closed = MagicMock(return_value=True)

    gh_tab = create_mock_tab("openai/gpt-4 - GitHub - Brave", "https://github.com/openai/gpt-4", browser="brave", hwnd=102, index=1)

    success = tab_mgr.close_tab(gh_tab)
    assert success is True

    mock_wm.capture_window_state.assert_called_once_with(102)
    mock_wm.restore_window_state.assert_called_once_with(restored_state)
    mock_wm.verify_window_state.assert_called_once_with(restored_state)


def test_closing_tab_in_minimized_browser_restores_minimized_state(caplog):
    """
    Test 3: Closing a tab in a minimized browser.
    Verifies that the window state is captured as minimized, temporarily brought up for action,
    and restored to minimized afterward.
    """
    caplog.set_level("INFO")
    mock_wm = MagicMock(spec=WindowManager)

    minimized_state = WindowState(
        hwnd=103,
        process_name="msedge.exe",
        browser="edge",
        title="Flipkart - Edge",
        is_maximized=False,
        is_minimized=True,
        is_restored=False,
        position=(-32000, -32000),
        size=(160, 31),
        rect=(-32000, -32000, -31840, -31969),
        restore_bounds=(200, 200, 1100, 700),
        monitor=1,
    )

    mock_wm.capture_window_state.return_value = minimized_state
    mock_wm.verify_window_state.return_value = True

    tab_mgr = BrowserTabManager(window_manager=mock_wm)
    tab_mgr._activate_tab_internal = MagicMock(return_value=True)
    tab_mgr._hotkey = MagicMock()
    tab_mgr._wait_for_tab_closed = MagicMock(return_value=True)

    flipkart_tab = create_mock_tab("Online Shopping - Flipkart - Edge", "https://flipkart.com", browser="edge", hwnd=103, index=2)

    success = tab_mgr.close_tab(flipkart_tab)
    assert success is True

    # Must restore to the captured minimized state
    mock_wm.restore_window_state.assert_called_once_with(minimized_state)
    mock_wm.verify_window_state.assert_called_once_with(minimized_state)


def test_closing_tab_across_multiple_browser_windows():
    """
    Test 4: Multiple browser windows open. Closing a tab in Window A does not affect Window B.
    """
    mock_wm = MagicMock(spec=WindowManager)

    state_win_a = WindowState(hwnd=201, process_name="chrome.exe", browser="chrome", is_maximized=True)
    state_win_b = WindowState(hwnd=202, process_name="chrome.exe", browser="chrome", is_maximized=False, position=(50, 50), size=(800, 600))

    def capture_side_effect(hwnd):
        return state_win_a if hwnd == 201 else state_win_b

    mock_wm.capture_window_state.side_effect = capture_side_effect
    mock_wm.verify_window_state.return_value = True

    tab_mgr = BrowserTabManager(window_manager=mock_wm)
    tab_mgr._activate_tab_internal = MagicMock(return_value=True)
    tab_mgr._hotkey = MagicMock()
    tab_mgr._wait_for_tab_closed = MagicMock(return_value=True)

    tab_in_a = create_mock_tab("Docs - Google Chrome", "https://docs.google.com", browser="chrome", hwnd=201, index=0)

    success = tab_mgr.close_tab(tab_in_a)
    assert success is True

    mock_wm.capture_window_state.assert_called_once_with(201)
    mock_wm.restore_window_state.assert_called_once_with(state_win_a)


def test_closing_tab_with_multiple_different_browsers_open():
    """
    Test 5: Multiple different browsers open (Brave maximized, Chrome restored).
    Closing a tab in Chrome preserves Chrome's restored state without touching Brave.
    """
    mock_wm = MagicMock(spec=WindowManager)

    brave_state = WindowState(hwnd=301, process_name="brave.exe", browser="brave", is_maximized=True)
    chrome_state = WindowState(hwnd=302, process_name="chrome.exe", browser="chrome", is_maximized=False, position=(300, 200), size=(900, 700))

    def capture_side_effect(hwnd):
        if hwnd == 301:
            return brave_state
        return chrome_state

    mock_wm.capture_window_state.side_effect = capture_side_effect
    mock_wm.verify_window_state.return_value = True

    tab_mgr = BrowserTabManager(window_manager=mock_wm)
    tab_mgr._activate_tab_internal = MagicMock(return_value=True)
    tab_mgr._hotkey = MagicMock()
    tab_mgr._wait_for_tab_closed = MagicMock(return_value=True)

    gmail_tab = create_mock_tab("Inbox - Gmail - Google Chrome", "https://mail.google.com", browser="chrome", hwnd=302, index=1)

    success = tab_mgr.close_tab(gmail_tab)
    assert success is True

    mock_wm.capture_window_state.assert_called_once_with(302)
    mock_wm.restore_window_state.assert_called_once_with(chrome_state)
    mock_wm.verify_window_state.assert_called_once_with(chrome_state)


def test_generic_websites_and_arbitrary_urls_tab_operations():
    """
    Test 6: Generic support for any arbitrary website or domain.
    """
    mock_wm = MagicMock(spec=WindowManager)
    state = WindowState(hwnd=401, process_name="firefox.exe", browser="firefox", is_maximized=True)
    mock_wm.capture_window_state.return_value = state
    mock_wm.verify_window_state.return_value = True

    tab_mgr = BrowserTabManager(window_manager=mock_wm)
    tab_mgr._activate_tab_internal = MagicMock(return_value=True)
    tab_mgr._hotkey = MagicMock()
    tab_mgr._wait_for_tab_closed = MagicMock(return_value=True)

    custom_tab = create_mock_tab("Internal Dashboard - Company Portal", "https://internal.corp/dashboard", browser="firefox", hwnd=401, index=4)

    assert tab_mgr.close_tab(custom_tab) is True
    mock_wm.restore_window_state.assert_called_once_with(state)


def test_window_manager_live_capture_and_restore_methods():
    """
    Test 7: Direct unit test of WindowManager window state capture and verification logic in headless/mock mode.
    """
    wm = WindowManager()
    state = wm.capture_window_state(0)
    assert state.hwnd == 0
    assert state.is_maximized is False
    assert state.is_minimized is False

    # Verify restore and verify return gracefully when hwnd is invalid or headless
    assert wm.restore_window_state(state) is True
    assert wm.verify_window_state(state) is True
