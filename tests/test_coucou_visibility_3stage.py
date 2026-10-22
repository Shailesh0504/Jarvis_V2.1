# tests/test_coucou_visibility_3stage.py
"""Unit tests for Coucou-Style 3-Stage Visibility System for JARVIS GUI.

Validates the exact 10 scenarios requested:
TEST 1: Expanded -> mouse leaves -> wait 15 sec -> Compact.
TEST 2: Expanded -> mouse leaves -> 10 sec -> mouse returns -> remains Expanded.
TEST 3: Expanded -> Compact -> remain outside 60 sec -> Hidden.
TEST 4: Hidden -> move mouse to top-center wake area -> Compact.
TEST 5: Compact -> click -> Expanded.
TEST 6: Expanded -> trigger confirmation/permission -> wait >15 sec -> must remain visible.
TEST 7: Compact -> mouse enters -> 60 sec timer must cancel.
TEST 8: Rapid mouse enter/leave 20 times -> no duplicate timers, no crash, no stuck state.
TEST 9: Hidden state -> verify JARVIS backend/wake-word/microphone functionality remains alive.
TEST 10: Verify desktop applications behind JARVIS can still receive clicks when JARVIS is compact/hidden.
"""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication(["-platform", "offscreen"])

import pytest
from unittest.mock import patch
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QEnterEvent, QMouseEvent

from main import create_jarvis
from gui.app import JarvisMainWindow
from gui.island.island import CoucouIslandWidget
from gui.island.visibility_manager import CoucouVisibilityManager
from gui.island.state_machine import GuiVisibilityState, IslandState


@pytest.fixture(scope="session")
def qapp():
    return _app


@pytest.fixture
def jarvis_gui_core(tmp_path):
    db_file = os.path.join(tmp_path, "gui_vis_test.db").replace("\\", "/")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(f"""
system:
  name: "JARVIS_VIS_TEST"
memory:
  db_path: "{db_file}"
brain:
  llm_provider: "mock"
reminder:
  db_path: "{str(tmp_path / 'gui_reminders.db').replace(chr(92), '/')}"
plugins:
  plugin_dir: "plugins"
  auto_load: true
""")
    return create_jarvis(str(cfg_file))


def test_scenario_1_expanded_mouse_leaves_wait_15s_compact(qapp, caplog):
    """TEST 1: Expanded -> mouse leaves -> wait 15 sec -> Compact."""
    with caplog.at_level("INFO"):
        island = CoucouIslandWidget()
        mgr = island.visibility_mgr

        # Start in Expanded
        island.expand_to_view("overview")
        assert mgr.state == GuiVisibilityState.EXPANDED
        assert island._current_mode == "expanded"
        assert "[JARVIS_GUI] STATE=EXPANDED" in caplog.text

        # Mouse leaves GUI
        mgr.on_mouse_leave()
        assert mgr._auto_close_timer.isActive() is True
        assert "[JARVIS_GUI] AUTO_CLOSE_STARTED seconds=15" in caplog.text

        # 15s timer fires
        mgr._auto_close_timer.timeout.emit()
        assert mgr.state == GuiVisibilityState.COMPACT
        assert island._current_mode == "compact"
        assert "[JARVIS_GUI] STATE=COMPACT" in caplog.text

        island.close()


def test_scenario_2_expanded_mouse_leaves_10s_returns_remains_expanded(qapp, caplog):
    """TEST 2: Expanded -> mouse leaves -> 10 sec -> mouse returns -> remains Expanded."""
    with caplog.at_level("INFO"):
        island = CoucouIslandWidget()
        mgr = island.visibility_mgr

        island.expand_to_view("overview")
        assert mgr.state == GuiVisibilityState.EXPANDED

        # Mouse leaves
        mgr.on_mouse_leave()
        assert mgr._auto_close_timer.isActive() is True

        # Mouse returns before timeout (e.g. at 10s)
        mgr.on_mouse_enter()
        assert mgr._auto_close_timer.isActive() is False
        assert mgr.state == GuiVisibilityState.EXPANDED
        assert island._current_mode == "expanded"
        assert "[JARVIS_GUI] AUTO_CLOSE_CANCELLED reason=mouse_enter" in caplog.text

        island.close()


def test_scenario_3_expanded_compact_outside_60s_hidden(qapp, caplog):
    """TEST 3: Expanded -> Compact -> remain outside 60 sec -> Hidden."""
    with caplog.at_level("INFO"):
        island = CoucouIslandWidget()
        mgr = island.visibility_mgr

        # Expanded -> Compact
        island.expand_to_view("overview")
        mgr.on_mouse_leave()
        mgr._auto_close_timer.timeout.emit()
        assert mgr.state == GuiVisibilityState.COMPACT
        assert island._current_mode == "compact"

        # Remain outside: 60s hide timer must be started
        assert mgr._compact_hide_timer.isActive() is True
        assert "[JARVIS_GUI] COMPACT_HIDE_TIMER_STARTED seconds=60" in caplog.text

        # 60s timer fires
        mgr._compact_hide_timer.timeout.emit()
        assert mgr.state == GuiVisibilityState.HIDDEN
        assert island._current_mode == "hidden"
        assert "[JARVIS_GUI] STATE=HIDDEN" in caplog.text
        assert "[JARVIS_GUI] WAKE_STRIP_ACTIVE" in caplog.text

        island.close()


def test_scenario_4_hidden_move_mouse_wake_area_compact(qapp, caplog):
    """TEST 4: Hidden -> move mouse to top-center wake area -> Compact."""
    with caplog.at_level("INFO"):
        island = CoucouIslandWidget()
        mgr = island.visibility_mgr

        # Set to Hidden
        mgr.transition_to(GuiVisibilityState.HIDDEN)
        assert mgr.state == GuiVisibilityState.HIDDEN
        assert island._current_mode == "hidden"

        # Mouse moves to top-center wake strip
        mgr.on_mouse_enter()
        assert "[JARVIS_GUI] WAKE_STRIP_TRIGGERED" in caplog.text
        assert mgr.state == GuiVisibilityState.COMPACT
        assert island._current_mode == "compact"
        assert "[JARVIS_GUI] STATE=COMPACT" in caplog.text

        island.close()


def test_scenario_5_compact_click_expanded(qapp, caplog):
    """TEST 5: Compact -> click -> Expanded."""
    with caplog.at_level("INFO"):
        island = CoucouIslandWidget()
        mgr = island.visibility_mgr

        mgr.transition_to(GuiVisibilityState.COMPACT)
        assert mgr.state == GuiVisibilityState.COMPACT

        # Click on compact island
        mgr.on_mouse_click()
        assert mgr.state == GuiVisibilityState.EXPANDED
        assert island._current_mode == "expanded"
        assert "[JARVIS_GUI] STATE=EXPANDED" in caplog.text

        island.close()


def test_scenario_6_expanded_confirmation_wait_15s_remains_visible(qapp, caplog):
    """TEST 6: Expanded -> trigger confirmation/permission -> wait >15 sec -> must remain visible."""
    with caplog.at_level("INFO"):
        island = CoucouIslandWidget()
        mgr = island.visibility_mgr

        island.expand_to_view("approval")
        assert island._current_view == "approval"
        assert mgr.is_pinned_or_important() is True

        # Mouse leaves while approval card is active
        mgr.on_mouse_leave()
        assert mgr._auto_close_timer.isActive() is False
        assert "[JARVIS_GUI] PINNED_AUTO_HIDE_BLOCKED" in caplog.text

        # Even if timeout handler is manually invoked, must NOT collapse
        mgr._on_auto_close_timeout()
        assert mgr.state == GuiVisibilityState.EXPANDED
        assert island._current_mode == "expanded"

        island.close()


def test_scenario_7_compact_mouse_enters_60s_timer_cancels(qapp, caplog):
    """TEST 7: Compact -> mouse enters -> 60 sec timer must cancel."""
    with caplog.at_level("INFO"):
        island = CoucouIslandWidget()
        mgr = island.visibility_mgr

        mgr.transition_to(GuiVisibilityState.COMPACT)
        mgr.on_mouse_leave()
        assert mgr._compact_hide_timer.isActive() is True

        # Mouse enters compact island
        mgr.on_mouse_enter()
        assert mgr._compact_hide_timer.isActive() is False
        assert "[JARVIS_GUI] COMPACT_HIDE_TIMER_CANCELLED" in caplog.text

        island.close()


def test_scenario_8_rapid_mouse_enter_leave_20_times(qapp):
    """TEST 8: Rapid mouse enter/leave 20 times -> no duplicate timers, no crash, no stuck state."""
    island = CoucouIslandWidget()
    mgr = island.visibility_mgr

    island.expand_to_view("overview")
    assert mgr.state == GuiVisibilityState.EXPANDED

    # Rapid toggle 20 times
    for _ in range(20):
        mgr.on_mouse_leave()
        assert mgr._auto_close_timer.isActive() is True
        assert mgr._compact_hide_timer.isActive() is False
        mgr.on_mouse_enter()
        assert mgr._auto_close_timer.isActive() is False
        assert mgr._compact_hide_timer.isActive() is False

    # State remains consistent
    assert mgr.state == GuiVisibilityState.EXPANDED
    assert island._current_mode == "expanded"
    island.close()


def test_scenario_9_hidden_state_jarvis_backend_alive(qapp, jarvis_gui_core):
    """TEST 9: Hidden state -> verify JARVIS backend/wake-word/microphone functionality remains alive."""
    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    island = window.island
    mgr = island.visibility_mgr

    # Transition to Hidden
    mgr.transition_to(GuiVisibilityState.HIDDEN)
    assert mgr.state == GuiVisibilityState.HIDDEN
    assert island._current_mode == "hidden"

    # Core systems and voice remain alive and responsive
    assert window.core is not None
    assert window.core.has_active_gui is True
    assert window.controller.micEnabled is True
    assert window.controller.speakerEnabled is True
    assert window.isVisible() is True  # Process and host window alive, not terminated!

    window.close()


def test_scenario_10_desktop_click_through_compact_and_hidden(qapp, jarvis_gui_core):
    """TEST 10: Verify desktop applications behind JARVIS can still receive clicks when JARVIS is compact/hidden."""
    import ctypes
    from ctypes import wintypes
    from PySide6.QtCore import QPoint

    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    island = window.island
    mgr = island.visibility_mgr

    # 1. In COMPACT mode:
    mgr.transition_to(GuiVisibilityState.COMPACT)
    assert mgr.state == GuiVisibilityState.COMPACT
    vb_compact = window.visual_bounds()
    ib_compact = window.interaction_bounds()

    # Inside compact capsule (center top: x=360, y=16) -> HTCLIENT (1)
    on_compact_pt = window.mapToGlobal(QPoint(360, 16))
    lParam_c = (on_compact_pt.y() << 16) | (on_compact_pt.x() & 0xFFFF)
    msg_c = wintypes.MSG(hwnd=int(window.winId()), message=132, wParam=0, lParam=lParam_c)
    handled_c, res_c = window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg_c))
    assert handled_c is True
    assert res_c == 1  # Captures interaction

    # Outside compact capsule (bottom wing: x=360, y=180) -> HTTRANSPARENT (-1)
    under_compact_pt = window.mapToGlobal(QPoint(360, 180))
    lParam_u = (under_compact_pt.y() << 16) | (under_compact_pt.x() & 0xFFFF)
    msg_u = wintypes.MSG(hwnd=int(window.winId()), message=132, wParam=0, lParam=lParam_u)
    handled_u, res_u = window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg_u))
    assert handled_u is True
    assert res_u == -1  # Passes straight through to desktop!

    # 2. In HIDDEN mode:
    mgr.transition_to(GuiVisibilityState.HIDDEN)
    assert mgr.state == GuiVisibilityState.HIDDEN

    # Inside 240x6 wake strip (x=360, y=3) -> HTCLIENT (1)
    wake_pt = window.mapToGlobal(QPoint(360, 3))
    lParam_w = (wake_pt.y() << 16) | (wake_pt.x() & 0xFFFF)
    msg_w = wintypes.MSG(hwnd=int(window.winId()), message=132, wParam=0, lParam=lParam_w)
    handled_w, res_w = window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg_w))
    assert handled_w is True
    assert res_w == 1  # Captures wake hover

    # Outside wake strip (left side: x=50, y=3) -> HTTRANSPARENT (-1)
    outside_wake_pt = window.mapToGlobal(QPoint(50, 3))
    lParam_ow = (outside_wake_pt.y() << 16) | (outside_wake_pt.x() & 0xFFFF)
    msg_ow = wintypes.MSG(hwnd=int(window.winId()), message=132, wParam=0, lParam=lParam_ow)
    handled_ow, res_ow = window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg_ow))
    assert handled_ow is True
    assert res_ow == -1  # Desktop apps receive click!

    # Below wake strip (y=50) -> HTTRANSPARENT (-1)
    below_wake_pt = window.mapToGlobal(QPoint(360, 50))
    lParam_bw = (below_wake_pt.y() << 16) | (below_wake_pt.x() & 0xFFFF)
    msg_bw = wintypes.MSG(hwnd=int(window.winId()), message=132, wParam=0, lParam=lParam_bw)
    handled_bw, res_bw = window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg_bw))
    assert handled_bw is True
    assert res_bw == -1  # Desktop apps receive click!

    window.close()
