# gui/island/position_manager.py
"""Manages normalized and DPI-aware screen coordinates for the permanent JARVIS floating anchor."""

import json
import logging
import math
import os
from typing import Optional, Tuple
from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QGuiApplication, QCursor

logger = logging.getLogger("jarvis.gui.island.position")


class AnchorPositionManager:
    """Persists and restores floating anchor position using normalized DPI-aware coordinates."""

    DEFAULT_REL_X = 0.50   # Horizontal center
    DEFAULT_REL_Y = 0.008  # Attached near top-center edge

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
            os.makedirs(data_dir, exist_ok=True)
            storage_path = os.path.join(data_dir, "anchor_position.json")
        self.storage_path = storage_path

    def load_position(self, screen_geo: QRect, anchor_size: int = 44) -> QPoint:
        """Loads saved position, converting normalized coordinates to screen pixel coordinates."""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    rel_x = float(data.get("rel_x", self.DEFAULT_REL_X))
                    rel_y = float(data.get("rel_y", self.DEFAULT_REL_Y))
                    x = screen_geo.x() + int(rel_x * (screen_geo.width() - anchor_size))
                    y = screen_geo.y() + int(rel_y * (screen_geo.height() - anchor_size))
                    return self.clamp_position(QPoint(x, y), screen_geo, anchor_size)
        except Exception as e:
            logger.warning(f"[ANCHOR] Failed to load saved position: {e}")

        # Return default TOP-CENTER
        return self.default_position(screen_geo, anchor_size)

    def save_position(self, pos: QPoint, screen_geo: QRect, anchor_size: int = 44) -> None:
        """Saves current anchor position as normalized coordinates."""
        try:
            avail_w = max(1, screen_geo.width() - anchor_size)
            avail_h = max(1, screen_geo.height() - anchor_size)
            rel_x = max(0.0, min(1.0, (pos.x() - screen_geo.x()) / avail_w))
            rel_y = max(0.0, min(1.0, (pos.y() - screen_geo.y()) / avail_h))
            data = {
                "rel_x": rel_x,
                "rel_y": rel_y,
                "abs_x": pos.x(),
                "abs_y": pos.y()
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"[ANCHOR] Saved position: rel_x={rel_x:.3f}, rel_y={rel_y:.3f}")
        except Exception as e:
            logger.warning(f"[ANCHOR] Failed to save position: {e}")

    def default_position(self, screen_geo: QRect, anchor_size: int = 44) -> QPoint:
        """Calculates default TOP-CENTER position on active screen."""
        x = screen_geo.x() + (screen_geo.width() - anchor_size) // 2
        y = screen_geo.y() + 8
        return QPoint(x, y)

    def clamp_position(self, pos: QPoint, screen_geo: QRect, anchor_size: int = 44, min_visible: int = 20) -> QPoint:
        """Clamps anchor position so at least `min_visible` pixels remain on-screen."""
        min_x = screen_geo.x() - (anchor_size - min_visible)
        max_x = screen_geo.x() + screen_geo.width() - min_visible
        min_y = screen_geo.y()
        max_y = screen_geo.y() + screen_geo.height() - min_visible

        clamped_x = max(min_x, min(max_x, pos.x()))
        clamped_y = max(min_y, min(max_y, pos.y()))
        return QPoint(clamped_x, clamped_y)

    def calculate_expanded_geometry(
        self,
        anchor_pos: QPoint,
        screen_geo: QRect,
        anchor_size: int = 44,
        island_size: QSize = QSize(720, 320)
    ) -> QRect:
        """Calculates expanded Dynamic Island geometry anchored to the floating JARVIS icon."""
        island_w = island_size.width()
        island_h = island_size.height()

        # Check if anchor is in upper or lower half of screen
        is_near_top = anchor_pos.y() < (screen_geo.y() + screen_geo.height() // 2)

        # Horizontal alignment: center on anchor
        island_x = (anchor_pos.x() + anchor_size // 2) - (island_w // 2)
        # Left/Right edge clamping to keep fully visible on screen
        margin = 12
        island_x = max(screen_geo.x() + margin, min(screen_geo.x() + screen_geo.width() - island_w - margin, island_x))

        if is_near_top:
            # Expand downward
            island_y = anchor_pos.y()
            if island_y + island_h > screen_geo.y() + screen_geo.height() - margin:
                island_y = screen_geo.y() + screen_geo.height() - island_h - margin
        else:
            # Expand upward
            island_y = (anchor_pos.y() + anchor_size) - island_h
            if island_y < screen_geo.y() + margin:
                island_y = screen_geo.y() + margin

        return QRect(island_x, island_y, island_w, island_h)

    def get_active_screen(self, pos: Optional[QPoint] = None):
        """Returns the QScreen for the specified position or cursor."""
        if pos:
            screen = QGuiApplication.screenAt(pos)
            if screen:
                return screen
        try:
            cursor_pos = QCursor.pos()
            if cursor_pos:
                screen = QGuiApplication.screenAt(cursor_pos)
                if screen:
                    return screen
        except Exception:
            pass
        return QGuiApplication.primaryScreen()
