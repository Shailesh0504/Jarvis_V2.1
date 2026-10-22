# tests/test_mochi_floater.py
"""Mochi on the desktop — free-float companion (detach/dock/follow/fly-home/persist).

Headless (QT_QPA_PLATFORM=offscreen via conftest). Covers:
- No-duplicate invariant: floater reuses JarvisCharacter + AnchorPositionManager.
- 120pt window geometry, loose/dock flags, follow-step math.
- Alert fly-home-and-back (synchronous path) and FloatStore round-trip.
- Island empty-nest invariant (exactly one Mochi visible).
- App wiring: detach → nest + anchor; dock → restore; outfit shared; tray text.
"""

import os

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

from gui.island.character import JarvisCharacter
from gui.island.floater import FLOAT_SIZE, FloatStore, MochiFloater
from gui.island.island import CoucouIslandWidget
from gui.island.position_manager import AnchorPositionManager

app = QApplication.instance() or QApplication(["-platform", "offscreen"])


@pytest.fixture()
def store_path(tmp_path):
    return str(tmp_path / "mochi_float.json")


@pytest.fixture()
def floater(store_path):
    fl = MochiFloater(parent=None, store=FloatStore(storage_path=store_path))
    yield fl
    try:
        fl.stop()
        fl.close()
    except Exception:
        pass


def test_no_duplicate_character_or_position_systems(floater):
    """Floater must REUSE JarvisCharacter + AnchorPositionManager (AGENTS.md §1.1)."""
    assert isinstance(floater.character, JarvisCharacter)
    assert isinstance(floater.store.pos, AnchorPositionManager)


def test_float_window_is_120pt():
    fl = MochiFloater(parent=None, store=FloatStore(storage_path=":memory:__noloc__"))
    try:
        assert fl.width() == 120 and fl.height() == 120
        assert FLOAT_SIZE == 120
    finally:
        fl.stop()
        fl.close()


def test_store_round_trip_loose_and_docked(store_path):
    from PySide6.QtWidgets import QApplication as _QA
    screen = _QA.primaryScreen()
    geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
    store = FloatStore(storage_path=store_path)
    store.save(QPoint(geo.x() + 400, geo.y() + 300), geo, "loose", False)
    state = FloatStore(storage_path=store_path).load()
    assert state["mode"] == "loose"
    assert state["follow"] is False
    assert state["pos"] is not None
    assert abs(state["pos"].x() - (geo.x() + 400)) < 60  # normalized round-trip

    store.save(QPoint(10, 10), geo, "docked", True)
    state2 = FloatStore(storage_path=store_path).load()
    assert state2["mode"] == "docked"
    assert state2["follow"] is True


def test_store_defaults_when_no_file(tmp_path):
    state = FloatStore(storage_path=str(tmp_path / "missing.json")).load()
    assert state["mode"] == "docked"
    assert state["follow"] is True
    assert state["pos"] is None


def test_set_loose_and_dock_flags(floater):
    assert floater.is_loose is False
    floater.set_loose(True, at=QPoint(200, 200))
    assert floater.is_loose is True
    assert floater.isVisible() is True
    floater.set_loose(False)
    assert floater.is_loose is False
    assert floater.isVisible() is False


def test_follow_step_math(floater):
    # Hidden → never moves.
    assert floater._follow_step(QPoint(1500, 800)) is False

    floater.set_loose(True, at=QPoint(200, 200))
    before = floater.geometry().center()

    # Far cursor → moves closer.
    far = QPoint(before.x() + 600, before.y() + 100)
    assert floater._follow_step(far) is True
    after = floater.geometry().center()
    dist_before = ((far.x() - before.x()) ** 2 + (far.y() - before.y()) ** 2) ** 0.5
    dist_after = ((far.x() - after.x()) ** 2 + (far.y() - after.y()) ** 2) ** 0.5
    assert dist_after < dist_before

    # Near cursor → stays (no jitter).
    near = QPoint(after.x() + 20, after.y() + 10)
    assert floater._follow_step(near) is False

    # Dragging / flying / disabled → stays.
    floater._dragging = True
    assert floater._follow_step(far) is False
    floater._dragging = False
    floater._flying = True
    assert floater._follow_step(far) is False
    floater._flying = False
    floater.follow_enabled = False
    assert floater._follow_step(far) is False


def test_fly_home_and_back_instant(floater):
    # Docked → not applicable (but still reacts with an emote, never crashes).
    assert floater.fly_home_and_back(QPoint(960, 12), animate=False) is False

    floater.set_loose(True, at=QPoint(300, 400))
    home = floater.pos()
    assert floater.fly_home_and_back(QPoint(960, 12), animate=False) is True
    assert floater.is_flying is False
    assert floater.pos() == home  # flew home and came back


def test_outfit_shared_manager_not_copied():
    """One AccessoryManager object serves both homes (outfit always in sync)."""
    from gui.island.accessories import AccessoryManager
    shared = AccessoryManager(storage_path=":memory:__nope__")
    a = JarvisCharacter(parent=None, size=24)
    b = JarvisCharacter(parent=None, size=24)
    try:
        a.accessories = shared
        b.accessories = shared
        a.set_accessory("crown")
        assert b.accessories.current.value == "crown"
        assert a.accessories is b.accessories
    finally:
        a.stop()
        b.stop()


def test_island_empty_nest_invariant():
    """Exactly one Mochi visible: island bot hides while loose, flag restores after."""
    island = CoucouIslandWidget()
    try:
        assert island._mochi_loose is False
        island.set_mochi_loose(True)
        assert island._mochi_loose is True
        assert island.character.isHidden() is True
        island.set_mochi_loose(False)
        assert island._mochi_loose is False
    finally:
        island.close()


@pytest.mark.skipif(os.name != "nt", reason="Win32 hit-testing only")
def test_floater_hit_test_center_vs_corner(floater):
    """Clicks on the companion register; transparent corners pass through."""
    import ctypes
    from ctypes import wintypes
    floater.set_loose(True, at=QPoint(200, 200))

    center = floater.mapToGlobal(QPoint(60, 60))
    msg_in = wintypes.MSG(hwnd=int(floater.winId()), message=132, wParam=0,
                          lParam=(center.y() << 16) | (center.x() & 0xFFFF))
    handled, res = floater.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg_in))
    assert handled is True and res == 1  # HTCLIENT

    corner = floater.mapToGlobal(QPoint(1, 1))
    msg_out = wintypes.MSG(hwnd=int(floater.winId()), message=132, wParam=0,
                           lParam=(corner.y() << 16) | (corner.x() & 0xFFFF))
    handled2, res2 = floater.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg_out))
    assert handled2 is True and res2 == -1  # HTTRANSPARENT
    floater.set_loose(False)


def test_app_detach_dock_wiring():
    """End-to-end through JarvisMainWindow (Tier 2): detach, nest, dock, tray, outfit."""
    from main import create_jarvis
    from gui.app import JarvisMainWindow

    core = create_jarvis()
    window = JarvisMainWindow(core)
    try:
        assert window.floater is None  # lazy until first detach

        window._detach_mochi_to_desktop(QPoint(500, 400))
        assert window.floater is not None
        assert window.floater.is_loose is True
        assert window.island._mochi_loose is True  # empty nest
        assert window._is_anchor_mode is True      # island collapsed home
        assert window.floater.character.accessories is window.island.character.accessories
        if getattr(window, "tray_float_action", None) is not None:
            assert "Dock" in window.tray_float_action.text()

        # State + audio mirror reaches the loose companion.
        window.set_system_state("thinking")
        assert window.floater.character._current_state == "thinking"
        window._on_live_audio_level(0.7, True)
        assert window.floater.character._target_audio_level > 0.0

        # Empty-nest recall: anchor click docks instead of expanding.
        window._dock_mochi("test")
        assert window.floater.is_loose is False
        assert window.island._mochi_loose is False
        if getattr(window, "tray_float_action", None) is not None:
            assert "Float" in window.tray_float_action.text()

        # Persistence records the docked mode for next launch.
        saved = window._float_store.load()
        assert saved["mode"] == "docked"
    finally:
        try:
            window.close()
        except Exception:
            pass
