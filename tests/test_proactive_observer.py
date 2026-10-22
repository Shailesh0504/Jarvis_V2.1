# tests/test_proactive_observer.py
"""
Comprehensive tests for Phase 1 Proactive Activity Observer foundation.
Verifies models, WindowObserver, ScreenObserver, deduplication, attention transitions,
lifecycle management, and exception resilience.
"""

import time
from unittest.mock import MagicMock, patch
import pytest

from core.observer.models import (
    ActivityEvent,
    ActivityImportance,
    ActivityType,
    DesktopSnapshot,
)
from core.observer.window_observer import WindowObserver
from core.observer.screen_observer import ScreenObserver
from core.observer.activity_observer import ProactiveActivityObserver


# ---------------------------------------------------------------------------
# 1. Models & Serialization Tests
# ---------------------------------------------------------------------------

def test_activity_event_models_and_serialization():
    """Verifies that ActivityEvent dataclass serializes correctly."""
    event = ActivityEvent(
        event_type=ActivityType.APPLICATION_OPENED,
        importance=ActivityImportance.HIGH,
        application="chrome",
        window_title="YouTube - Google Chrome",
        content_title="Arijit Singh - Kesariya",
        website="youtube",
        confidence=0.95,
        metadata={"tab_count": 5}
    )

    d = event.to_dict()
    assert d["event_type"] == "APPLICATION_OPENED"
    assert d["importance"] == "HIGH"
    assert d["application"] == "chrome"
    assert d["window_title"] == "YouTube - Google Chrome"
    assert d["content_title"] == "Arijit Singh - Kesariya"
    assert d["website"] == "youtube"
    assert d["confidence"] == 0.95
    assert d["metadata"]["tab_count"] == 5
    assert len(d["event_id"]) > 0


def test_desktop_snapshot_validation():
    """Verifies DesktopSnapshot validity checking."""
    valid_snap = DesktopSnapshot(hwnd=12345, title="Main Window", process_name="chrome")
    assert valid_snap.is_valid is True

    invalid_hwnd = DesktopSnapshot(hwnd=0, title="Main Window", process_name="chrome")
    assert invalid_hwnd.is_valid is False

    empty_title = DesktopSnapshot(hwnd=12345, title="   ", process_name="chrome")
    assert empty_title.is_valid is False


# ---------------------------------------------------------------------------
# 2. WindowObserver Tests
# ---------------------------------------------------------------------------

def test_window_observer_process_normalization():
    """Verifies that process names are normalized to standard identifiers."""
    obs = WindowObserver()
    assert obs.normalize_process_name("chrome.exe") == "chrome"
    assert obs.normalize_process_name("BRAVE.EXE") == "brave"
    assert obs.normalize_process_name("Code.exe") == "vscode"
    assert obs.normalize_process_name("EXCEL.EXE") == "excel"
    assert obs.normalize_process_name("vlc.exe") == "vlc"
    assert obs.normalize_process_name("CustomApp.exe") == "customapp"
    assert obs.normalize_process_name("") == ""


def test_window_observer_with_window_manager():
    """Verifies that WindowObserver reuses an injected WindowManager."""
    mock_wm = MagicMock()
    mock_win = MagicMock()
    mock_win.hwnd = 998877
    mock_win.title = "Quarterly Report - Excel"
    mock_win.process_name = "EXCEL.EXE"
    mock_win.rect = (10, 10, 800, 600)
    mock_wm.get_foreground_window.return_value = mock_win

    obs = WindowObserver(window_manager=mock_wm)
    snap = obs.get_foreground_snapshot()

    assert snap is not None
    assert snap.hwnd == 998877
    assert snap.title == "Quarterly Report - Excel"
    assert snap.process_name == "excel"
    assert snap.rect == (10, 10, 800, 600)


def test_window_observer_resilience_when_no_foreground_window():
    """Verifies that WindowObserver returns None cleanly if no foreground window exists."""
    obs = WindowObserver()
    with patch.object(obs, "_user32") as mock_user32:
        mock_user32.GetForegroundWindow.return_value = 0
        snap = obs.get_foreground_snapshot()
        assert snap is None


# ---------------------------------------------------------------------------
# 3. ScreenObserver (Idle & Attention) Tests
# ---------------------------------------------------------------------------

def test_screen_observer_idle_calculation():
    """Verifies that ScreenObserver computes idle seconds and attention transitions."""
    obs = ScreenObserver(idle_threshold_sec=5.0)

    # Simulate 2 seconds since last input -> Active
    with patch.object(obs, "get_idle_seconds", return_value=2.0):
        idle_secs, is_idle, transition = obs.check_attention_state()
        assert idle_secs == 2.0
        assert is_idle is False
        assert transition is None

    # Simulate 6 seconds since last input -> Transitions to Became Idle
    with patch.object(obs, "get_idle_seconds", return_value=6.0):
        idle_secs, is_idle, transition = obs.check_attention_state()
        assert idle_secs == 6.0
        assert is_idle is True
        assert transition == "became_idle"

    # Simulate 8 seconds (still idle) -> Stays idle, no new transition
    with patch.object(obs, "get_idle_seconds", return_value=8.0):
        idle_secs, is_idle, transition = obs.check_attention_state()
        assert is_idle is True
        assert transition is None

    # Simulate user resuming input (1.0 second since input) -> Transitions to Became Active
    with patch.object(obs, "get_idle_seconds", return_value=1.0):
        idle_secs, is_idle, transition = obs.check_attention_state()
        assert is_idle is False
        assert transition == "became_active"


# ---------------------------------------------------------------------------
# 4. ProactiveActivityObserver Deduplication & Event Emission
# ---------------------------------------------------------------------------

def test_activity_observer_deduplication():
    """Verifies that duplicate polls on unchanged window states produce no events."""
    obs = ProactiveActivityObserver(poll_interval=1.0)
    snap1 = DesktopSnapshot(hwnd=101, title="Calculator", process_name="calculator")

    with patch.object(obs.window_observer, "get_foreground_snapshot", return_value=snap1), \
         patch.object(obs.screen_observer, "check_attention_state", return_value=(0.5, False, None)), \
         patch.object(obs.volume_observer, "check_volume_change", return_value=(False, None, None, None)):

        # First poll: New window state -> Event emitted
        e1 = obs.poll_once()
        assert e1 is not None
        assert e1.event_type == ActivityType.APPLICATION_OPENED
        assert e1.application == "calculator"

        # Second poll: Same window state -> Suppressed (None)
        e2 = obs.poll_once()
        assert e2 is None

        # Third poll: Same window state -> Still suppressed (None)
        e3 = obs.poll_once()
        assert e3 is None


def test_activity_observer_app_and_window_switch_events():
    """Verifies event generation when switching windows and applications."""
    obs = ProactiveActivityObserver(poll_interval=1.0)
    snap_calc1 = DesktopSnapshot(hwnd=101, title="Calculator", process_name="calculator")
    snap_calc2 = DesktopSnapshot(hwnd=102, title="Graphing - Calculator", process_name="calculator")
    snap_taskmgr = DesktopSnapshot(hwnd=201, title="Task Manager", process_name="taskmgr")

    with patch.object(obs.screen_observer, "check_attention_state", return_value=(0.5, False, None)), \
         patch.object(obs.volume_observer, "check_volume_change", return_value=(False, None, None, None)):
        # 1. Open Calculator
        with patch.object(obs.window_observer, "get_foreground_snapshot", return_value=snap_calc1):
            e1 = obs.poll_once()
            assert e1 is not None
            assert e1.event_type == ActivityType.APPLICATION_OPENED
            assert e1.application == "calculator"

        # 2. Switch window within Calculator
        with patch.object(obs.window_observer, "get_foreground_snapshot", return_value=snap_calc2):
            e2 = obs.poll_once()
            assert e2 is not None
            assert e2.event_type == ActivityType.WINDOW_CHANGED
            assert e2.application == "calculator"
            assert e2.window_title == "Graphing - Calculator"

        # 3. Switch application to Task Manager
        with patch.object(obs.window_observer, "get_foreground_snapshot", return_value=snap_taskmgr):
            e3 = obs.poll_once()
            assert e3 is not None
            assert e3.event_type == ActivityType.APPLICATION_OPENED
            assert e3.application == "taskmgr"


def test_activity_observer_listeners_and_event_bus():
    """Verifies that registered callbacks and EventBus receive emitted events."""
    mock_bus = MagicMock()
    events_received = []

    def on_event(ev):
        events_received.append(ev)

    obs = ProactiveActivityObserver(
        poll_interval=1.0,
        event_bus=mock_bus,
        on_activity_callback=on_event
    )

    snap = DesktopSnapshot(hwnd=301, title="Inbox - Outlook", process_name="outlook")

    with patch.object(obs.window_observer, "get_foreground_snapshot", return_value=snap), \
         patch.object(obs.screen_observer, "check_attention_state", return_value=(0.5, False, None)), \
         patch.object(obs.volume_observer, "check_volume_change", return_value=(False, None, None, None)):
        obs.poll_once()

    assert len(events_received) == 1
    assert events_received[0].application == "outlook"
    assert mock_bus.emit.called
    assert mock_bus.emit.call_args[0][0] == "activity.observed"


def test_activity_observer_lifecycle_and_exception_resilience():
    """Verifies that background thread starts/stops cleanly and absorbs internal errors."""
    obs = ProactiveActivityObserver(poll_interval=0.1)

    # Inject an exception into window_observer while attention and volume are idle
    with patch.object(obs.window_observer, "get_foreground_snapshot", side_effect=RuntimeError("Win32 fault")), \
         patch.object(obs.screen_observer, "check_attention_state", return_value=(0.5, False, None)), \
         patch.object(obs.volume_observer, "check_volume_change", return_value=(False, None, None, None)):
        # poll_once must absorb the error and return None without raising
        result = obs.poll_once()
        assert result is None

    # Start and stop background thread
    obs.start()
    assert obs.is_active is True
    time.sleep(0.2)
    obs.stop()
    obs.join(timeout=2.0)
    assert obs.is_active is False

