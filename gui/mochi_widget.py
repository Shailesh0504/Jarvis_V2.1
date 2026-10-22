# gui/mochi_widget.py
"""Mochi Mascot Interactive Widget for Jarvis V2 Desktop Application.

Faithfully implements Coucou's Mochi companion:
- Squircle face with state-aware color tinting & soft metallic gradients
- Breathing idle animation and randomized natural eye blinks
- Real-time cursor tracking (pupils/look yaw & pitch follow cursor movement)
- Multiple expressive eye shapes (pill, wide, happy arc, hearts, spiral, annoyed line, closed)
- Interactive pokes: click to annoy (annoyed.wav), 3 clicks to dizzy (dizzy.wav), hover for love (love.wav)
- Full integration with Coucou sound effects and Jarvis system states
"""

import math
import random
import time
from typing import Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QFont, QLinearGradient, QPainter,
    QPainterPath, QPen, QRadialGradient
)
from PySide6.QtWidgets import QWidget

from .sound_effects import Sound


class MochiWidget(QWidget):
    """Coucou-authentic animated mascot widget for top island notch and header."""

    state_changed = Signal(str)

    def __init__(self, parent=None, size: int = 42):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size + 16, size + 8)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

        # State and Appearance
        self._current_state = "idle"  # idle, listening, thinking, executing, speaking, finished, error, dizzy
        self._eye_shape = "pill"      # pill, wide, happy, heart, spiral, line, closed
        self._custom_emote = None
        self._emote_expiry = 0.0

        # Animation parameters
        self._start_time = time.time()
        self._blink_start = 0.0
        self._is_blinking = False
        self._next_blink_time = time.time() + random.uniform(2.5, 5.0)

        # Mouse tracking & look direction
        self._look_x = 0.0  # -1.0 to 1.0
        self._look_y = 0.0  # -1.0 to 1.0
        self._target_look_x = 0.0
        self._target_look_y = 0.0
        self._is_hovered = False

        # Interaction click counters
        self._click_times = []
        self._is_dizzy = False
        self._dizzy_until = 0.0

        # Coucou State Colors (RGB floats 0..1)
        self._state_colors = {
            "idle": (0.91, 0.92, 0.94),
            "listening": (0.13, 0.83, 0.93),  # Cyan
            "thinking": (0.55, 0.36, 0.96),   # Violet
            "executing": (0.23, 0.62, 1.00),  # Blue
            "speaking": (0.75, 0.52, 0.99),   # Purple
            "finished": (0.20, 0.83, 0.60),   # Emerald green
            "approval": (0.96, 0.65, 0.14),   # Amber
            "error": (0.96, 0.31, 0.37),      # Crimson
            "dizzy": (0.96, 0.45, 0.71),      # Pink
        }

        # 60 FPS animation timer
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_animation_frame)
        self._anim_timer.start(16)

    def set_system_state(self, state: str, play_sound: bool = True) -> None:
        """Transitions Mochi's appearance, eye shape, and Coucou sounds to match system state."""
        state_clean = state.lower().strip()
        if self._is_dizzy and state_clean not in ("error",):
            return

        old_state = self._current_state
        self._current_state = state_clean

        if state_clean == "listening":
            self._eye_shape = "wide"
            if play_sound and old_state != state_clean:
                Sound.play("peek")
        elif state_clean == "thinking":
            self._eye_shape = "pill"
            self._target_look_x = 0.5
            self._target_look_y = -0.6
            if play_sound and old_state != state_clean:
                Sound.play("think")
        elif state_clean == "executing":
            self._eye_shape = "pill"
            if play_sound and old_state != state_clean:
                Sound.play("work")
        elif state_clean == "speaking":
            self._eye_shape = "happy"
            if play_sound and old_state != state_clean:
                Sound.play("blip")
        elif state_clean == "finished":
            self._eye_shape = "happy"
            if play_sound and old_state != state_clean:
                Sound.play("finish")
        elif state_clean == "error":
            self._eye_shape = "line"
            if play_sound and old_state != state_clean:
                Sound.play("error")
        else:
            self._current_state = "idle"
            self._eye_shape = "pill"

        self.update()

    def show_emote(self, emote: str, duration: float = 2.0) -> None:
        """Temporarily shows an emote (heart, wink, happy, annoyed, spiral)."""
        self._custom_emote = emote
        self._emote_expiry = time.time() + duration
        self.update()

    def enterEvent(self, event):
        self._is_hovered = True
        if not self._is_dizzy and self._current_state in ("idle", "ready"):
            self.show_emote("heart", duration=1.8)
            Sound.play("hover")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self._target_look_x = 0.0
        self._target_look_y = 0.0
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        # Calculate look yaw & pitch from mouse offset to center
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        dx = (event.position().x() - cx) / (self.width() / 2.0)
        dy = (event.position().y() - cy) / (self.height() / 2.0)
        self._target_look_x = max(-1.0, min(1.0, dx))
        self._target_look_y = max(-1.0, min(1.0, dy))
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        now = time.time()
        self._click_times = [t for t in self._click_times if now - t < 1.5]
        self._click_times.append(now)

        if len(self._click_times) >= 3:
            # Dizzy trigger on 3 fast clicks!
            self._is_dizzy = True
            self._dizzy_until = now + 3.5
            self._current_state = "dizzy"
            self._eye_shape = "spiral"
            Sound.play("dizzy")
            self._click_times.clear()
        else:
            # Annoyed trigger on click
            self.show_emote("line", duration=1.2)
            Sound.play("annoyed")

        self.update()
        super().mousePressEvent(event)

    def _on_animation_frame(self) -> None:
        now = time.time()

        # Handle dizzy expiration
        if self._is_dizzy and now > self._dizzy_until:
            self._is_dizzy = False
            self.set_system_state("idle", play_sound=False)

        # Handle emote expiration
        if self._custom_emote and now > self._emote_expiry:
            self._custom_emote = None

        # Handle natural random blinks
        if not self._is_blinking and now > self._next_blink_time:
            self._is_blinking = True
            self._blink_start = now
        elif self._is_blinking and now - self._blink_start > 0.14:
            self._is_blinking = False
            self._next_blink_time = now + random.uniform(2.5, 6.0)

        # Smooth pupil tracking interpolation
        self._look_x += (self._target_look_x - self._look_x) * 0.15
        self._look_y += (self._target_look_y - self._look_y) * 0.15

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        now = time.time()
        elapsed = now - self._start_time

        # Idle breathing bounce
        breath_y = 0.0
        scale_x = 1.0
        scale_y = 1.0

        if self._current_state == "executing":
            # Energetic pulse
            pulse = math.sin(elapsed * 6.0)
            breath_y = pulse * 2.0
            scale_x = 1.0 + pulse * 0.04
            scale_y = 1.0 - pulse * 0.04
        elif self._current_state == "listening":
            breath_y = math.sin(elapsed * 4.0) * 1.5
        elif self._is_dizzy:
            breath_y = math.sin(elapsed * 12.0) * 2.0
        else:
            breath_y = math.sin(elapsed * 2.2) * 1.0

        # Active eye shape determination
        active_eye = self._custom_emote or self._eye_shape
        if self._is_dizzy:
            active_eye = "spiral"

        # Center dimensions
        w = float(self._size)
        h = float(self._size) * 0.88
        cx = self.width() / 2.0
        cy = (self.height() / 2.0) + breath_y

        body_rect = QRectF(cx - (w * scale_x) / 2.0, cy - (h * scale_y) / 2.0, w * scale_x, h * scale_y)

        # 1. Subtle Outer Glow for active states
        if self._current_state in ("listening", "thinking", "executing", "speaking"):
            glow_col = self._state_colors.get(self._current_state, (0.2, 0.6, 1.0))
            radial = QRadialGradient(body_rect.center(), w * 0.9)
            radial.setColorAt(0.0, QColor.fromRgbF(glow_col[0], glow_col[1], glow_col[2], 0.35))
            radial.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(radial))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(body_rect.center(), w * 0.85, h * 0.85)

        # 2. Mochi Squircle Body with metallic sheen
        base_top = (0.93, 0.93, 0.94)
        base_bot = (0.77, 0.77, 0.79)
        tint_col = self._state_colors.get(self._current_state, base_top)

        # Mix state tint into body gradient
        t_mix = 0.55 if self._current_state not in ("idle", "ready") else 0.08
        top_r = base_top[0] * (1 - t_mix) + tint_col[0] * t_mix
        top_g = base_top[1] * (1 - t_mix) + tint_col[1] * t_mix
        top_b = base_top[2] * (1 - t_mix) + tint_col[2] * t_mix

        bot_r = base_bot[0] * (1 - t_mix) + (tint_col[0] * 0.8) * t_mix
        bot_g = base_bot[1] * (1 - t_mix) + (tint_col[1] * 0.8) * t_mix
        bot_b = base_bot[2] * (1 - t_mix) + (tint_col[2] * 0.8) * t_mix

        body_grad = QLinearGradient(body_rect.topLeft(), body_rect.bottomLeft())
        body_grad.setColorAt(0.0, QColor.fromRgbF(top_r, top_g, top_b, 1.0))
        body_grad.setColorAt(1.0, QColor.fromRgbF(bot_r, bot_g, bot_b, 1.0))

        squircle_radius = 13.0
        squircle_path = QPainterPath()
        squircle_path.addRoundedRect(body_rect, squircle_radius, squircle_radius)

        # Subtle dark border
        painter.setBrush(QBrush(body_grad))
        painter.setPen(QPen(QColor(30, 32, 38, 180), 1.2))
        painter.drawPath(squircle_path)

        # Top soft specular highlight
        highlight_rect = QRectF(body_rect.x() + 3, body_rect.y() + 2, body_rect.width() - 6, body_rect.height() * 0.4)
        hl_grad = QLinearGradient(highlight_rect.topLeft(), highlight_rect.bottomLeft())
        hl_grad.setColorAt(0.0, QColor(255, 255, 255, 120))
        hl_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(hl_grad))
        painter.setPen(Qt.NoPen)
        hl_path = QPainterPath()
        hl_path.addRoundedRect(highlight_rect, 8.0, 8.0)
        painter.drawPath(hl_path)

        # 3. Eyes rendering
        eye_y_offset = (self._look_y * 2.5)
        eye_x_offset = (self._look_x * 3.5)

        eye_spacing = w * 0.22
        left_eye_cx = body_rect.center().x() - eye_spacing + eye_x_offset
        right_eye_cx = body_rect.center().x() + eye_spacing + eye_x_offset
        eye_cy = body_rect.center().y() - 1.0 + eye_y_offset

        # Check for blinking
        blink_scale = 0.12 if self._is_blinking else 1.0

        eye_w = 4.8
        eye_h = 7.5 * blink_scale

        ink_color = QColor(26, 20, 18)

        for ecx in (left_eye_cx, right_eye_cx):
            if active_eye == "heart":
                # Heart eyes!
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(244, 80, 94)))
                self._draw_heart(painter, ecx, eye_cy, size=6.0)
            elif active_eye == "spiral":
                # Spiral dizzy eyes
                painter.setPen(QPen(QColor(244, 114, 182), 1.6))
                painter.setBrush(Qt.NoBrush)
                rot = elapsed * 8.0
                painter.save()
                painter.translate(ecx, eye_cy)
                painter.rotate(rot * 57.3)
                painter.drawArc(QRectF(-4, -4, 8, 8), 0, 270 * 16)
                painter.drawArc(QRectF(-2.5, -2.5, 5, 5), 180 * 16, 270 * 16)
                painter.restore()
            elif active_eye == "happy":
                # Upward happy arc ^
                painter.setPen(QPen(ink_color, 2.0, Qt.SolidLine, Qt.RoundCap))
                painter.setBrush(Qt.NoBrush)
                arc_path = QPainterPath()
                arc_path.moveTo(ecx - 3.5, eye_cy + 1.5)
                arc_path.quadTo(ecx, eye_cy - 4.0, ecx + 3.5, eye_cy + 1.5)
                painter.drawPath(arc_path)
            elif active_eye == "line":
                # Annoyed flat slit -
                painter.setPen(QPen(ink_color, 2.2, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(QPointF(ecx - 3.5, eye_cy), QPointF(ecx + 3.5, eye_cy))
            elif active_eye == "closed":
                # Sleeping gentle curve
                painter.setPen(QPen(ink_color, 1.8, Qt.SolidLine, Qt.RoundCap))
                painter.setBrush(Qt.NoBrush)
                arc_path = QPainterPath()
                arc_path.moveTo(ecx - 3.0, eye_cy - 1.0)
                arc_path.quadTo(ecx, eye_cy + 2.5, ecx + 3.0, eye_cy - 1.0)
                painter.drawPath(arc_path)
            elif active_eye == "wide":
                # Wide attentive eye
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(ink_color))
                painter.drawEllipse(QRectF(ecx - 3.0, eye_cy - 4.5, 6.0, 9.0 * blink_scale))
                # White gleam reflection
                if not self._is_blinking:
                    painter.setBrush(QBrush(QColor(255, 255, 255, 240)))
                    painter.drawEllipse(QRectF(ecx - 1.5, eye_cy - 3.5, 2.2, 2.2))
            else:
                # Default "pill" eye with pupil gloss
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(ink_color))
                eye_rect = QRectF(ecx - eye_w / 2.0, eye_cy - eye_h / 2.0, eye_w, eye_h)
                painter.drawRoundedRect(eye_rect, eye_w / 2.0, eye_w / 2.0)
                # Glossy reflection dot
                if not self._is_blinking:
                    painter.setBrush(QBrush(QColor(255, 255, 255, 230)))
                    painter.drawEllipse(QRectF(ecx - 1.2, eye_cy - eye_h * 0.35, 1.8, 1.8))

        # 4. State indicator badge (dots / bang / wave)
        if self._current_state in ("thinking", "executing"):
            # 3 animated dots below/beside
            dot_color = QColor.fromRgbF(*self._state_colors.get(self._current_state, (0.5, 0.5, 1.0)))
            for i in range(3):
                dot_phase = (elapsed * 5.0 + i * 0.8) % (math.pi * 2)
                dot_y = math.sin(dot_phase) * 1.5
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(dot_color))
                painter.drawEllipse(QPointF(body_rect.right() - 2 + (i * 3.5), body_rect.top() + 4 + dot_y), 1.2, 1.2)

    def _draw_heart(self, painter: QPainter, cx: float, cy: float, size: float):
        path = QPainterPath()
        path.moveTo(cx, cy + size * 0.6)
        path.cubicTo(cx - size, cy - size * 0.2, cx - size * 0.5, cy - size * 0.8, cx, cy - size * 0.3)
        path.cubicTo(cx + size * 0.5, cy - size * 0.8, cx + size, cy - size * 0.2, cx, cy + size * 0.6)
        painter.drawPath(path)
