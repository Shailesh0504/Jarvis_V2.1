# gui/island/floater.py
"""Mochi on the desktop — free-floating 120pt companion window.

Single-identity rule: the floater hosts a `JarvisCharacter` (the ONE authoritative
character implementation — never MochiWidget, never a copy). The island hides its
own character while Mochi is loose, so exactly one Mochi is ever visible.

Geometry-math SSOT stays in `AnchorPositionManager` (clamp + active screen);
this module only adds float-specific persistence (mode + follow flag) in
data/mochi_float.json — anchor_position.json is never touched.
"""

import json
import logging
import os
import time
from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QMenu, QWidget

from .character import JarvisCharacter
from .position_manager import AnchorPositionManager
from ..sound_effects import Sound

logger = logging.getLogger("jarvis.gui.island.floater")

FLOAT_SIZE = 120          # 120pt free companion window
FLOAT_CHAR_SIZE = 104     # character widget size inside it
FOLLOW_INTERVAL_MS = 60
FOLLOW_MIN_DIST = 200     # start trailing beyond this cursor distance (px)
FOLLOW_STEP_CAP = 16      # max px per follow tick
FLY_MS = 550              # one leg of fly-home-and-back
AUTOSAVE_SEC = 5.0


def _default_storage_path() -> str:
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(data_dir, "mochi_float.json")


class FloatStore:
    """Persists float position + mode + follow flag (DPI-aware normalized coords)."""

    def __init__(self, storage_path: Optional[str] = None,
                 pos_manager: Optional[AnchorPositionManager] = None):
        self.storage_path = storage_path or _default_storage_path()
        self.pos = pos_manager or AnchorPositionManager()

    def load(self) -> dict:
        """Returns {pos: QPoint|None, mode: 'docked'|'loose', follow: bool}."""
        state = {"pos": None, "mode": "docked", "follow": True}
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                if data.get("mode") == "loose":
                    state["mode"] = "loose"
                state["follow"] = bool(data.get("follow", True))
                if "rel_x" in data and "rel_y" in data:
                    from PySide6.QtWidgets import QApplication
                    screen = QApplication.primaryScreen()
                    geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
                    x = geo.x() + int(float(data["rel_x"]) * max(1, geo.width() - FLOAT_SIZE))
                    y = geo.y() + int(float(data["rel_y"]) * max(1, geo.height() - FLOAT_SIZE))
                    state["pos"] = self.pos.clamp_position(QPoint(x, y), geo, FLOAT_SIZE)
                elif "abs_x" in data and "abs_y" in data:
                    state["pos"] = QPoint(int(data["abs_x"]), int(data["abs_y"]))
        except Exception as e:
            logger.debug(f"[FLOAT] load failed: {e}")
        return state

    def save(self, pos: QPoint, screen_geo: QRect, mode: str, follow: bool) -> None:
        """Read-modify-write so mode/follow survive alongside geometry."""
        try:
            avail_w = max(1, screen_geo.width() - FLOAT_SIZE)
            avail_h = max(1, screen_geo.height() - FLOAT_SIZE)
            data = {
                "rel_x": max(0.0, min(1.0, (pos.x() - screen_geo.x()) / avail_w)),
                "rel_y": max(0.0, min(1.0, (pos.y() - screen_geo.y()) / avail_h)),
                "abs_x": pos.x(),
                "abs_y": pos.y(),
                "mode": "loose" if mode == "loose" else "docked",
                "follow": bool(follow),
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"[FLOAT] save failed: {e}")


class MochiFloater(QWidget):
    """Free 120pt desktop companion. Drag to move, double-click to dock home."""

    dock_requested = Signal()    # user wants Mochi back in the island
    chat_requested = Signal()    # clean click → open island chat

    def __init__(self, parent=None, size: int = FLOAT_SIZE,
                 store: Optional[FloatStore] = None):
        super().__init__(parent)
        self._size = size
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(size, size)

        self.store = store or FloatStore()
        self.follow_enabled = True
        self._loose = False
        self._flying = False
        self._dragging = False
        self._drag_threshold = 8  # same click-vs-drag contract as the anchor
        self._press_pos = QPoint()
        self._press_window_pos = QPoint()
        self._last_autosave = 0.0
        self._fly_anim = None
        self.dock_zone_provider: Optional[Callable[[], QRect]] = None

        # The character itself — shared AccessoryManager instance is injected by
        # the app so the outfit is one object, live in both homes, never copied.
        self.character = JarvisCharacter(self, size=FLOAT_CHAR_SIZE)
        self.character.setGeometry(8, 8, FLOAT_CHAR_SIZE + 16, FLOAT_CHAR_SIZE + 16)

        self._follow_timer = QTimer(self)
        self._follow_timer.timeout.connect(self._on_follow_tick)
        self._follow_timer.start(FOLLOW_INTERVAL_MS)

    # ── state ────────────────────────────────────────────────────────────────
    @property
    def is_loose(self) -> bool:
        return self._loose

    @property
    def is_flying(self) -> bool:
        return self._flying

    def set_loose(self, loose: bool, at: Optional[QPoint] = None,
                  follow: Optional[bool] = None) -> None:
        """Show (loose) or hide (docked) the free companion."""
        if follow is not None:
            self.follow_enabled = bool(follow)
        if loose:
            self._loose = True
            if at is not None:
                self.move(at)
            self.show()
            self.raise_()
        else:
            self._loose = False
            self._flying = False
            self.hide()

    def stop(self) -> None:
        """Freezes timers for a clean shutdown (mirrors JarvisCharacter.stop)."""
        try:
            self._follow_timer.stop()
        except Exception:
            pass
        try:
            if self._fly_anim is not None:
                self._fly_anim.stop()
        except Exception:
            pass
        try:
            self.character.stop()
        except Exception:
            pass

    # ── input: drag to move, click for chat, double-click to dock ─────────────
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._press_window_pos = self.pos()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton and not self._flying:
            delta = event.globalPosition().toPoint() - self._press_pos
            if not self._dragging and delta.manhattanLength() > self._drag_threshold:
                self._dragging = True
            if self._dragging:
                target = self._press_window_pos + delta
                screen = self.store.pos.get_active_screen(target)
                geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
                self.move(self.store.pos.clamp_position(target, geo, self._size))
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            if self._dragging:
                self._dragging = False
                if self._dropped_on_dock_zone():
                    self.dock_requested.emit()
                else:
                    self._persist_here("loose")
            else:
                self.chat_requested.emit()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.dock_requested.emit()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        follow_action = menu.addAction("Follow cursor")
        follow_action.setCheckable(True)
        follow_action.setChecked(self.follow_enabled)
        dock_action = menu.addAction("Dock Mochi home")
        reset_action = menu.addAction("Reset float position")
        chosen = menu.exec(event.globalPos())
        if chosen == follow_action:
            self.follow_enabled = bool(follow_action.isChecked())
            self._persist_here("loose")
        elif chosen == dock_action:
            self.dock_requested.emit()
        elif chosen == reset_action:
            self.reset_float_position()

    def _dropped_on_dock_zone(self) -> bool:
        try:
            if self.dock_zone_provider is None:
                return False
            zone = self.dock_zone_provider()
            if zone is None:
                return False
            center = self.geometry().center()
            return zone.adjusted(-24, -24, 24, 24).contains(center)
        except Exception:
            return False

    # ── follow the cursor (gentle trailing, never grabbing focus) ─────────────
    def _on_follow_tick(self) -> None:
        try:
            self._follow_step(QCursor.pos())
        except Exception:
            pass

    def _follow_step(self, cursor: QPoint) -> bool:
        """One follow tick. Returns True if the window moved. Testable headlessly."""
        if (not self.follow_enabled or not self._loose or not self.isVisible()
                or self._dragging or self._flying):
            return False
        center = self.geometry().center()
        dx = cursor.x() - center.x()
        dy = cursor.y() - center.y()
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < FOLLOW_MIN_DIST:
            return False
        step = min(FOLLOW_STEP_CAP, dist * 0.15)
        nx = int(center.x() + dx / dist * step - self._size / 2)
        ny = int(center.y() + dy / dist * step - self._size / 2)
        screen = self.store.pos.get_active_screen(cursor)
        geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        self.move(self.store.pos.clamp_position(QPoint(nx, ny), geo, self._size))
        now = time.time()
        if now - self._last_autosave > AUTOSAVE_SEC:
            self._last_autosave = now
            self._persist_here("loose")
        return True

    # ── fly home on alerts, then fly back ─────────────────────────────────────
    def fly_home_and_back(self, home_center: QPoint, hold_ms: int = 1200,
                          animate: bool = True) -> bool:
        """Flies to home, reacts, flies back. Returns False if not applicable."""
        if not self._loose or self._flying or not self.isVisible():
            try:
                self.character.trigger_emote("surprised", duration_s=1.2)
            except Exception:
                pass
            return False
        self._flying = True
        away_pos = self.pos()
        home_top_left = QPoint(home_center.x() - self._size // 2,
                               home_center.y() - self._size // 2)
        try:
            self.character.trigger_emote("surprised", duration_s=1.2)
        except Exception:
            pass
        Sound.play("pop")

        if not animate:
            # Synchronous path for headless tests (no event-loop flight needed).
            self.move(home_top_left)
            self.move(away_pos)
            self._flying = False
            try:
                self.character.trigger_emote("happy", duration_s=1.4)
            except Exception:
                pass
            return True

        self._fly_anim = QPropertyAnimation(self, b"pos", self)
        self._fly_anim.setDuration(FLY_MS)
        self._fly_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._fly_anim.setStartValue(away_pos)
        self._fly_anim.setEndValue(home_top_left)
        self._fly_anim.finished.connect(
            lambda: self._on_arrived_home(away_pos, hold_ms))
        self._fly_anim.start()
        return True

    def _on_arrived_home(self, away_pos: QPoint, hold_ms: int) -> None:
        Sound.play("blip")
        QTimer.singleShot(max(0, int(hold_ms)),
                          lambda: self._fly_back(away_pos))

    def _fly_back(self, away_pos: QPoint) -> None:
        if not self._loose:
            self._flying = False
            return
        back = QPropertyAnimation(self, b"pos", self)
        back.setDuration(FLY_MS)
        back.setEasingCurve(QEasingCurve.InOutQuad)
        back.setStartValue(self.pos())
        back.setEndValue(away_pos)
        self._fly_anim = back
        back.finished.connect(self._on_arrived_back)
        back.start()

    def _on_arrived_back(self) -> None:
        self._flying = False
        try:
            self.character.trigger_emote("happy", duration_s=1.4)
        except Exception:
            pass
        Sound.play("finish")
        self._persist_here("loose")

    # ── persistence ──────────────────────────────────────────────────────────
    def _persist_here(self, mode: str) -> None:
        try:
            screen = self.store.pos.get_active_screen(self.pos())
            geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
            self.store.save(self.pos(), geo, mode, self.follow_enabled)
        except Exception as e:
            logger.debug(f"[FLOAT] persist failed: {e}")

    def persist(self, mode: str) -> None:
        """Explicit persist hook for shutdown/dock (window may be hidden)."""
        self._persist_here(mode)

    def reset_float_position(self) -> None:
        """Clears the saved float spot; Mochi re-appears near the island next time."""
        try:
            if os.path.exists(self.store.storage_path):
                os.remove(self.store.storage_path)
        except Exception as e:
            logger.debug(f"[FLOAT] reset failed: {e}")

    # ── click-through everywhere except the companion itself ──────────────────
    def nativeEvent(self, event_type, message):
        """Win32 precision hit-testing (mirrors JarvisMainWindow's 3-step pattern)."""
        if event_type == b"windows_generic_MSG":
            try:
                import ctypes
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 132:  # WM_NCHITTEST
                    if self._dragging or self._flying:
                        return True, 1  # HTCLIENT
                    hit = QRect(8, 8, self._size - 16, self._size - 16)

                    # 1. Authoritative Qt logical cursor coordinates (DPI-independent)
                    if hit.contains(self.mapFromGlobal(QCursor.pos())):
                        return True, 1  # HTCLIENT

                    # 2. lParam physical coords, direct mapping…
                    raw_x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    raw_y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    if hit.contains(self.mapFromGlobal(QPoint(raw_x, raw_y))):
                        return True, 1  # HTCLIENT

                    # …and DPI-scaled mapping (e.g. 1.25x, 1.5x).
                    dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
                    if dpr > 1.0 and hit.contains(
                            self.mapFromGlobal(QPoint(int(raw_x / dpr), int(raw_y / dpr)))):
                        return True, 1  # HTCLIENT

                    # OUTSIDE the companion → clicks pass through to the desktop.
                    return True, -1  # HTTRANSPARENT
            except Exception:
                pass
        return super().nativeEvent(event_type, message)
