# gui/island/accessories.py
"""JARVIS Appearance / Accessory System — independent, composable with character states.

Accessories: NONE, BEANIE, SANTA_HAT, PARTY_HAT, CROWN, WITCH_HAT,
SUNGLASSES, ROUND_GLASSES, SCARF, PUMPKIN, BOW.

Rendered procedurally with QPainter (vector, no copyrighted assets).
Composes with any character state, e.g. CROWN + PROUD, SANTA_HAT + HAPPY.
Persisted via data/jarvis_appearance.json through PersistenceController logic here.
"""

import json
import logging
import os
from enum import Enum
from typing import Optional

from PySide6.QtCore import QPointF
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

logger = logging.getLogger("jarvis.gui.island.accessories")


class Accessory(str, Enum):
    NONE = "none"
    BEANIE = "beanie"
    SANTA_HAT = "santa_hat"
    PARTY_HAT = "party_hat"
    CROWN = "crown"
    WITCH_HAT = "witch_hat"
    SUNGLASSES = "sunglasses"
    ROUND_GLASSES = "round_glasses"
    SCARF = "scarf"
    PUMPKIN = "pumpkin"
    BOW = "bow"


def _default_storage_path() -> str:
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(data_dir, "jarvis_appearance.json")


class AccessoryManager:
    """Owns selected accessory + persistence. Rendering is stateless given geometry."""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or _default_storage_path()
        self.current: Accessory = Accessory.NONE
        self.load()

    def set_accessory(self, acc: Accessory) -> None:
        try:
            if isinstance(acc, Accessory):
                self.current = acc
            else:
                self.current = Accessory(str(acc).strip().lower())
        except Exception:
            self.current = Accessory.NONE
        self.save()

    def load(self) -> None:
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                raw = str(data.get("accessory", "none")).lower()
                self.current = Accessory(raw) if raw in {a.value for a in Accessory} else Accessory.NONE
        except Exception as e:
            logger.debug(f"[ACCESSORY] load failed: {e}")

    def save(self) -> None:
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({"accessory": self.current.value}, f, indent=2)
        except Exception as e:
            logger.debug(f"[ACCESSORY] save failed: {e}")

    # ── Procedural vector rendering ──────────────────────────────────────────
    def paint(self, painter: QPainter, cx: float, cy: float, rx: float, ry: float) -> None:
        """Paints selected accessory relative to character center/radii. No-op for NONE."""
        acc = self.current
        if acc == Accessory.NONE:
            return
        try:
            if acc in (Accessory.BEANIE, Accessory.SANTA_HAT, Accessory.PARTY_HAT,
                       Accessory.CROWN, Accessory.WITCH_HAT):
                self._paint_hat(painter, cx, cy, rx, ry, acc)
            elif acc in (Accessory.SUNGLASSES, Accessory.ROUND_GLASSES):
                self._paint_glasses(painter, cx, cy, rx, ry, acc)
            elif acc == Accessory.SCARF:
                self._paint_scarf(painter, cx, cy, rx, ry)
            elif acc == Accessory.BOW:
                self._paint_bow(painter, cx, cy, rx, ry)
            elif acc == Accessory.PUMPKIN:
                self._paint_pumpkin_pin(painter, cx, cy, rx, ry)
        except Exception as e:
            logger.debug(f"[ACCESSORY] paint failed: {e}")

    def _paint_hat(self, p: QPainter, cx, cy, rx, ry, acc: Accessory) -> None:
        top_y = cy - ry * 0.92
        if acc == Accessory.CROWN:
            p.setPen(QPen(QColor(16, 17, 20), max(1.4, rx * 0.04)))
            p.setBrush(QBrush(QColor(250, 204, 21)))
            w, h = rx * 1.1, ry * 0.5
            path = QPainterPath()
            x0, y0 = cx - w / 2, top_y
            path.moveTo(x0, y0 + h * 0.55)
            path.lineTo(x0, y0 + h)
            path.lineTo(x0 + w, y0 + h)
            path.lineTo(x0 + w, y0 + h * 0.55)
            path.lineTo(x0 + w * 0.75, y0 + h * 0.72)
            path.lineTo(x0 + w * 0.5, y0)
            path.lineTo(x0 + w * 0.25, y0 + h * 0.72)
            path.closeSubpath()
            p.drawPath(path)
            p.setPen(QPen(QColor(239, 68, 68), max(1.2, rx * 0.05)))
            p.setBrush(QBrush(QColor(239, 68, 68)))
            p.drawEllipse(QPointF(cx, y0 + h * 0.12), rx * 0.07, rx * 0.07)
            return
        # Cone-style hats
        if acc == Accessory.SANTA_HAT:
            fill, trim = QColor(220, 38, 38), QColor(248, 250, 252)
        elif acc == Accessory.PARTY_HAT:
            fill, trim = QColor(99, 102, 241), QColor(250, 204, 21)
        elif acc == Accessory.WITCH_HAT:
            fill, trim = QColor(30, 27, 75), QColor(168, 85, 247)
        else:  # BEANIE
            p.setPen(QPen(QColor(16, 17, 20), max(1.4, rx * 0.045)))
            p.setBrush(QBrush(QColor(34, 211, 238)))
            p.drawEllipse(QPointF(cx, top_y - ry * 0.12), rx * 0.62, ry * 0.34)
            p.setBrush(QBrush(QColor(248, 250, 252)))
            p.drawEllipse(QPointF(cx, top_y - ry * 0.34), rx * 0.14, rx * 0.14)
            return
        p.setPen(QPen(QColor(16, 17, 20), max(1.4, rx * 0.045)))
        p.setBrush(QBrush(fill))
        path = QPainterPath()
        path.moveTo(cx - rx * 0.62, top_y + ry * 0.06)
        path.lineTo(cx + rx * 0.62, top_y + ry * 0.06)
        path.lineTo(cx + rx * 0.10, top_y - ry * 0.85)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(QBrush(trim))
        p.drawRoundedRect(cx - rx * 0.68, top_y - ry * 0.02, rx * 1.36, ry * 0.20, ry * 0.10, ry * 0.10)
        p.setBrush(QBrush(QColor(248, 250, 252)))
        p.drawEllipse(QPointF(cx + rx * 0.10, top_y - ry * 0.88), rx * 0.13, rx * 0.13)

    def _paint_glasses(self, p: QPainter, cx, cy, rx, ry, acc: Accessory) -> None:
        eye_y = cy + ry * 0.04
        dx = rx * 0.41
        r = rx * (0.20 if acc == Accessory.ROUND_GLASSES else 0.19)
        if acc == Accessory.SUNGLASSES:
            p.setPen(QPen(QColor(10, 10, 12), max(1.6, rx * 0.05)))
            p.setBrush(QBrush(QColor(15, 23, 42, 235)))
            for sx in (-1, 1):
                p.drawRoundedRect(cx + sx * dx - r, eye_y - r * 0.8, r * 2, r * 1.6, r * 0.5, r * 0.5)
            p.setPen(QPen(QColor(148, 163, 184, 160), max(1.2, rx * 0.035)))
            p.drawLine(QPointF(cx - dx + r, eye_y - r * 0.2), QPointF(cx + dx - r, eye_y - r * 0.2))
        else:
            p.setPen(QPen(QColor(30, 41, 59), max(1.6, rx * 0.05)))
            p.setBrush(QBrush(QColor(255, 255, 255, 28)))
            for sx in (-1, 1):
                p.drawEllipse(QPointF(cx + sx * dx, eye_y), r, r)
            p.drawLine(QPointF(cx - dx + r * 0.9, eye_y), QPointF(cx + dx - r * 0.9, eye_y))

    def _paint_scarf(self, p: QPainter, cx, cy, rx, ry) -> None:
        p.setPen(QPen(QColor(16, 17, 20), max(1.3, rx * 0.04)))
        p.setBrush(QBrush(QColor(239, 68, 68)))
        p.drawRoundedRect(cx - rx * 0.75, cy + ry * 0.62, rx * 1.5, ry * 0.30, ry * 0.15, ry * 0.15)
        p.setBrush(QBrush(QColor(248, 113, 113)))
        p.drawRoundedRect(cx + rx * 0.25, cy + ry * 0.80, rx * 0.32, ry * 0.42, rx * 0.10, rx * 0.10)

    def _paint_bow(self, p: QPainter, cx, cy, rx, ry) -> None:
        bx, by = cx + rx * 0.62, cy - ry * 0.78
        s = rx * 0.22
        p.setPen(QPen(QColor(16, 17, 20), max(1.2, rx * 0.04)))
        p.setBrush(QBrush(QColor(236, 72, 153)))
        for sx in (-1, 1):
            path = QPainterPath()
            path.moveTo(bx, by)
            path.lineTo(bx + sx * s, by - s * 0.7)
            path.lineTo(bx + sx * s, by + s * 0.7)
            path.closeSubpath()
            p.drawPath(path)
        p.setBrush(QBrush(QColor(190, 24, 93)))
        p.drawEllipse(QPointF(bx, by), s * 0.35, s * 0.35)

    def _paint_pumpkin_pin(self, p: QPainter, cx, cy, rx, ry) -> None:
        bx, by = cx - rx * 0.66, cy - ry * 0.72
        s = rx * 0.16
        p.setPen(QPen(QColor(16, 17, 20), max(1.1, rx * 0.035)))
        p.setBrush(QBrush(QColor(249, 115, 22)))
        p.drawEllipse(QPointF(bx, by), s, s * 0.85)
        p.setPen(QPen(QColor(22, 101, 52), max(1.1, rx * 0.035)))
        p.drawLine(QPointF(bx, by - s * 0.85), QPointF(bx, by - s * 1.25))
