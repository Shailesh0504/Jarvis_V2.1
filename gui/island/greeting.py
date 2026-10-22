# gui/island/greeting.py
"""JARVIS Launch Greeting Controller & Canvas — High-Fidelity Port of Coucou greeting.ts.

Coordinates the choreographed startup greeting sequence in 640×150 space:
- Growth from top edge with spring/back easing (t: 0 -> 0.45s)
- Eye states (pill, happy squint, eye roll, content, blink)
- Dip & Pop bounce with squash & stretch (t: 1.25 -> 1.52s) + Sound.play("greet")
- Mechanical/cybernetic waving hand animation (t: 1.52 -> 2.58s)
- Luminous arc-reactor activity badge pop-in (t: 2.72s) + Sound.play("blip")
- Particle burst (5 rings of 170 seeded dots + 16 colored particle streaks)
- Cyan/azure soft radiating halo
- Auto-collapse into compact top-edge island (t: 4.6 -> 4.94s)
- Interactive hover-to-hold and click-to-skip awareness
"""

import math
import time
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, Signal
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush, QLinearGradient,
    QRadialGradient, QFont
)
from PySide6.QtWidgets import QWidget

from ..sound_effects import Sound

# ── Timing (mirrors Coucou greeting.ts `T`) ───────────────────────────────────
T_GROW = 0.45
T_SQUINT0 = 0.60
T_SQUINT1 = 0.82
T_DIP0 = 1.25
T_DIP1 = 1.40
T_POP0 = 1.36
T_POP1 = 1.52
T_CONTENT0 = 2.45
T_CONTENT1 = 2.58
T_TUCK0 = 2.58
T_TUCK1 = 2.80
T_BADGE = 2.72
T_DOWN0 = 2.85
T_DOWN1 = 3.20
T_BLINK2 = 3.80
T_TINT0 = 3.85
T_TINT1 = 4.15
T_END = 4.60
T_AUTO_LEAVE = 4.90
T_COLLAPSE = 0.34

C0_X, C0_Y = 168.0, 84.0
HB = 58.0
ASP = 1.34
SMALL_W = 288.0
SMALL_H = 32.0


def _ease_out(t: float) -> float:
    return 1.0 - math.pow(1.0 - t, 3)


def _ease_in(t: float) -> float:
    return t * t * t


def _ease_in_out(t: float) -> float:
    return 4.0 * t * t * t if t < 0.5 else 1.0 - math.pow(-2.0 * t + 2.0, 3) / 2.0


def _ease_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * math.pow(t - 1.0, 3) + c1 * math.pow(t - 1.0, 2)


def _clamp(v: float, a: float, b: float) -> float:
    return max(a, min(b, v))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _seg(t: float, a: float, b: float) -> float:
    return _clamp((t - a) / (b - a), 0.0, 1.0) if b > a else 0.0


# ── Seeded Particle System (LCG Seed = 7, identical to Coucou) ────────────────
def _build_seeded_particles():
    seed = 7

    def rnd():
        nonlocal seed
        seed = ((seed * 1103515245) + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    rings = []
    for t0 in [0.1, 0.2, 0.3, 0.45, 0.6]:
        dots = []
        for _ in range(170):
            dots.append({
                "a": rnd() * math.pi * 2.0,
                "j": (rnd() - 0.5) * 0.22,
                "s": 0.7 + rnd() * 0.9,
                "al": 0.45 + rnd() * 0.55,
            })
        rings.append({"t0": t0, "dots": dots})

    cols = ["#00F0FF", "#3B9EFF", "#6366F1", "#22C55E", "#A78BFA"]
    streaks = []
    for i in range(16):
        streaks.append({
            "a": (i / 16.0) * math.pi * 2.0 + (rnd() - 0.5) * 0.3,
            "sp": 230.0 + rnd() * 260.0,
            "len": 6.0 + rnd() * 9.0,
            "t0": 0.08 + rnd() * 0.14,
            "col": cols[i % len(cols)],
        })
    return rings, streaks


PARTICLE_RINGS, PARTICLE_STREAKS = _build_seeded_particles()


class GreetingCanvasWidget(QWidget):
    """High-fidelity animated greeting canvas (640x150) rendering JARVIS's startup ceremony."""

    completed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(640, 150)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._start_time = 0.0
        self._tc = float("inf")
        self._is_running = False
        self._sound_greet_played = False
        self._sound_blip_played = False
        self._fired = False
        self._banner_title = "Good day, Boss"
        self._banner_sub = "JARVIS AI Assistant • Ready"
        self._banner_tag = "All systems operational"

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

    def start(self):
        """Starts the choreographed launch ceremony."""
        self._start_time = time.monotonic()
        self._tc = float("inf")
        self._is_running = True
        self._sound_greet_played = False
        self._sound_blip_played = False
        self._fired = False
        self._banner_title, self._banner_sub, self._banner_tag = self._get_banner_info()
        self._timer.start(16)
        self.show()

    @staticmethod
    def _get_banner_info() -> Tuple[str, str, str]:
        """Generates dynamic time-of-day greeting (Good Morning / Afternoon / Evening / Night)."""
        try:
            from core.time_context import get_time_context, DayPart
            tc = get_time_context()
            now = tc.now()
            dp = tc.get_day_part(now)
            if dp == DayPart.MORNING:
                title = "Good morning, Boss"
                tagline = "JARVIS is online & ready to assist"
            elif dp == DayPart.AFTERNOON:
                title = "Good afternoon, Boss"
                tagline = "All systems operational & listening"
            elif dp == DayPart.EVENING:
                title = "Good evening, Boss"
                tagline = "Ready for your evening commands"
            else:
                title = "Working late, Boss?"
                tagline = "Standing by at your desktop"
            time_sub = f"{now.strftime('%A, %b %d')} • {now.strftime('%I:%M %p')}"
            return title, time_sub, tagline
        except Exception:
            from datetime import datetime
            now = datetime.now()
            hr = now.hour
            title = "Good morning, Boss" if 5 <= hr < 12 else ("Good afternoon, Boss" if 12 <= hr < 17 else ("Good evening, Boss" if 17 <= hr < 21 else "Working late, Boss?"))
            return title, now.strftime("%A, %b %d • %I:%M %p"), "JARVIS is online and ready"

    def skip(self):
        """User clicked or interacted: gracefully collapse immediately."""
        if not self._is_running:
            return
        t = time.monotonic() - self._start_time
        if not math.isinf(self._tc) or self._tc > t:
            self._tc = t

    def _on_tick(self):
        if not self._is_running:
            return
        t = time.monotonic() - self._start_time

        # Trigger synchronized sounds
        if t >= T_POP0 and not self._sound_greet_played:
            self._sound_greet_played = True
            Sound.play("greet")

        if t >= T_BADGE and not self._sound_blip_played:
            self._sound_blip_played = True
            Sound.play("blip")

        # Completion check
        if t >= T_END and self._tc >= T_AUTO_LEAVE:
            self._finish()

        if math.isinf(self._tc) and t >= T_AUTO_LEAVE:
            self._tc = t

        if not math.isinf(self._tc) and t >= (self._tc + T_COLLAPSE):
            self._finish()

        self.update()

    def _finish(self):
        if self._fired:
            return
        self._fired = True
        self._is_running = False
        self._timer.stop()
        self.completed.emit()

    def mousePressEvent(self, event):
        self.skip()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        # Hover extends the ceremony comfortably without permanent freeze
        t = time.monotonic() - self._start_time
        if self._tc >= T_AUTO_LEAVE:
            self._tc = max(self._tc, t + 3.5)
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Leaving triggers collapse
        t = time.monotonic() - self._start_time
        if math.isinf(self._tc) or self._tc > t:
            self._tc = t
        super().leaveEvent(event)

    # ── Geometry & Squircle Path ──────────────────────────────────────────────
    @staticmethod
    def _squircle_path(cx: float, cy: float, hw: float, hh: float, exponent: float = 3.2) -> QPainterPath:
        path = QPainterPath()
        steps = 96
        for i in range(steps + 1):
            a = (i / float(steps)) * 2.0 * math.pi
            ca = math.cos(a)
            sa = math.sin(a)
            px = cx + hw * (-1.0 if ca < 0 else 1.0) * math.pow(abs(ca), 2.0 / exponent)
            py = cy + hh * (-1.0 if sa < 0 else 1.0) * math.pow(abs(sa), 2.0 / exponent)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.closeSubpath()
        return path

    # ── Painting ──────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        if not self._is_running:
            return

        t = time.monotonic() - self._start_time
        tc = self._tc

        # Calculate pose parameters
        gx = _seg(t, 0.0, 0.5)
        g = math.sin((math.pi * gx) / 2.0) + 0.04 * math.sin(math.pi * gx) * gx
        iw = _lerp(288.0, 640.0, g)
        ih = _lerp(32.0, 150.0, g)

        gg = _ease_back(_seg(t, 0.02, T_GROW))
        hb = _lerp(3.0, HB, gg)
        x = C0_X
        y = _lerp(16.0, C0_Y, _ease_out(_seg(t, 0.02, T_GROW)))
        sx, sy, tilt = 1.0, 1.0, 0.0

        # Dip and Pop bounce
        if T_DIP0 <= t < T_POP1:
            k = math.sin(math.pi * _seg(t, T_DIP0, T_POP1))
            y += hb * 0.22 * k
            sy = 1.0 - 0.06 * k
            sx = 1.0 + 0.04 * k

        if T_POP1 <= t < T_TUCK1:
            w = t - T_POP1
            fade = 1.0 - _seg(t, T_TUCK0, T_TUCK1)
            x += math.sin(w * 2.0 * math.pi * 0.9) * hb * ASP * 0.05 * fade
            tilt = math.sin(w * 2.0 * math.pi * 0.9 + 0.6) * 0.05 * fade
            y += math.sin(w * 2.0 * math.pi * 1.8) * 0.8 * fade

        if T_TUCK0 <= t < T_DOWN1:
            y += hb * 0.12 * math.sin(math.pi * _seg(t, T_TUCK0, T_DOWN1))

        # Eye expression
        eye_type = "pill"
        if T_SQUINT0 <= t < T_SQUINT1:
            eye_type = "happy"
        elif T_CONTENT0 <= t < T_CONTENT1 or T_DOWN0 <= t < T_DOWN1:
            eye_type = "happy"

        eye_roll = 0.0
        if T_DIP0 <= t < T_POP1:
            eye_roll = math.sin(math.pi * _seg(t, T_DIP0, T_POP1))

        def blink(tb):
            k = _seg(t, tb, tb + 0.12)
            return 1.0 - math.sin(math.pi * k) * 0.94 if 0.0 < k < 1.0 else 1.0

        open_factor = min(blink(1.95), blink(T_BLINK2))

        look_x, look_y = 0.0, 0.0
        if T_SQUINT1 <= t < T_DIP0:
            look_y = -0.2
        elif T_POP1 <= t < T_CONTENT0:
            look_x, look_y = 0.55, -0.45
        elif T_CONTENT0 <= t < T_DOWN1:
            look_x, look_y = -0.3, 0.6
        elif t >= T_DOWN1:
            k = _ease_in_out(_seg(t, T_DOWN1, T_DOWN1 + 0.35))
            look_x = _lerp(-0.3, 0.0, k)
            look_y = _lerp(0.6, 0.0, k)

        # Waving hand
        hand_r = _ease_back(_seg(t, T_POP0 + 0.04, T_POP0 + 0.18)) if t < T_TUCK0 else 1.0 - _ease_in(_seg(t, T_TUCK0 + 0.03, T_TUCK1))
        wave = (t - T_POP1) if T_POP1 <= t < T_TUCK0 else -1.0

        halo = _ease_out(_seg(t, 0.3, 0.7))
        badge = _ease_back(_seg(t, T_BADGE, T_BADGE + 0.28))
        card_alpha = _seg(t, 0.18, 0.45)

        # Collapse interpolation if triggered
        if t >= tc:
            e = _ease_in_out(_seg(t, tc, tc + T_COLLAPSE))
            x = _lerp(x, 320.0 - SMALL_W / 2.0 + 40.0, e)
            y = _lerp(y, 16.0, e)
            hb = _lerp(hb, 17.0, e)
            card_alpha *= (1.0 - _seg(t, tc, tc + 0.18))
            hand_r *= (1.0 - _seg(t, tc, tc + 0.15))
            halo *= (1.0 - e)
            tilt *= (1.0 - e)
            sx = _lerp(sx, 1.0, e)
            sy = _lerp(sy, 1.0, e)

        hh = hb / 2.0
        hw = hh * ASP

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 1. Background Card & Particle Streaks
        if card_alpha > 0.01:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(20, 21, 24, int(255 * card_alpha)))
            painter.drawRoundedRect(QRectF(10, 36, 620, 104), 20.0, 20.0)

            # Draw Seeded Expanding Particle Streaks
            for s in PARTICLE_STREAKS:
                k = _seg(t, s["t0"], s["t0"] + 0.6)
                if 0.0 < k < 1.0:
                    dist = s["sp"] * _ease_out(k) * 0.9 + 10.0
                    alpha = int(255 * (1.0 - k) * card_alpha)
                    col = QColor(s["col"])
                    col.setAlpha(alpha)
                    pen = QPen(col, 1.6, Qt.SolidLine, Qt.RoundCap)
                    painter.setPen(pen)
                    x1 = C0_X + math.cos(s["a"]) * (dist - s["len"])
                    y1 = C0_Y + math.sin(s["a"]) * (dist - s["len"]) * 0.42
                    x2 = C0_X + math.cos(s["a"]) * dist
                    y2 = C0_Y + math.sin(s["a"]) * dist * 0.42
                    painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

            # Draw Seeded Expanding Rings
            for ring in PARTICLE_RINGS:
                k = _seg(t, ring["t0"], ring["t0"] + 1.35)
                if 0.0 < k < 1.0:
                    rx = _lerp(14.0, 220.0, _ease_out(k))
                    ry = rx * 0.34
                    fade = (1.0 - k) * (k / 0.08 if k < 0.08 else 1.0) * card_alpha
                    for dot in ring["dots"]:
                        r = 1.0 + dot["j"]
                        col = QColor(255, 255, 255, int(255 * dot["al"] * fade))
                        painter.setPen(Qt.NoPen)
                        painter.setBrush(col)
                        px = C0_X + math.cos(dot["a"]) * rx * r
                        py = C0_Y + math.sin(dot["a"]) * ry * r
                        painter.drawRect(QRectF(px, py, dot["s"], dot["s"]))

        # 2. Cyan Glowing Halo behind JARVIS
        if halo > 0.01:
            r1 = hw * 2.6
            grad1 = QRadialGradient(x, y, r1)
            grad1.setColorAt(0.0, QColor(0, 240, 255, int(70 * halo)))
            grad1.setColorAt(1.0, QColor(0, 240, 255, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad1))
            painter.drawEllipse(QPointF(x, y), r1, r1)

        # 3. JARVIS Cybernetic Waving Arm
        if hand_r > 0.01:
            painter.save()
            hb_arm = hh * 2.0
            arm_len = hb_arm * 0.4 * hand_r
            arm_thick = hb_arm * 0.22 * hand_r
            rx_arm = _lerp(hw * 0.35, hw + hb_arm * 0.2, hand_r)
            ry_arm = _lerp(hh * 0.85, hh * 0.2, hand_r)
            ang = -0.61
            if wave >= 0:
                w_cycle = wave * 2.0 * math.pi * 2.5
                ang += math.sin(w_cycle) * 0.22
                ry_arm += math.sin(w_cycle + 0.8) * hb_arm * 0.04
                rx_arm += math.cos(w_cycle) * hb_arm * 0.015

            painter.translate(x + rx_arm, y + ry_arm)
            painter.rotate(math.degrees(ang))

            # 3. Waving Arm matching porcelain identity with dark outline
            arm_grad = QLinearGradient(arm_len / 2.0, -arm_thick / 2.0, -arm_len / 2.0, arm_thick / 2.0)
            arm_grad.setColorAt(0.0, QColor(248, 241, 233))
            arm_grad.setColorAt(1.0, QColor(226, 212, 198))
            painter.setPen(QPen(QColor(16, 17, 20), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(QBrush(arm_grad))
            painter.drawRoundedRect(QRectF(-arm_len / 2.0, -arm_thick / 2.0, arm_len, arm_thick), arm_thick / 2.0, arm_thick / 2.0)
            painter.restore()

        # 4. JARVIS Squircle Body (Porcelain Ivory matching 128x128@2x.png)
        painter.save()
        painter.translate(x, y)
        painter.rotate(math.degrees(tilt))
        painter.scale(sx, sy)

        body_path = self._squircle_path(0.0, 0.0, hw, hh, exponent=3.2)

        # Grounding shadow
        shadow_rect = QRectF(-hw * 0.85, hh * 0.82, hw * 1.7, hh * 0.32)
        shadow_grad = QRadialGradient(shadow_rect.center(), hw * 0.85)
        shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 75))
        shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(shadow_grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(shadow_rect)

        # Porcelain Ivory Body Gradient: Sampled directly from 128x128@2x.png
        body_grad = QLinearGradient(0, -hh, 0, hh)
        body_grad.setColorAt(0.0, QColor(248, 241, 233))
        body_grad.setColorAt(0.48, QColor(238, 227, 218))
        body_grad.setColorAt(1.0, QColor(226, 212, 198))

        # Solid crisp continuous black outline border
        painter.setPen(QPen(QColor(16, 17, 20), 3.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(QBrush(body_grad))
        painter.drawPath(body_path)

        # 5. JARVIS Expressive Solid Bead Eyes (matching 128x128@2x.png)
        painter.save()
        painter.setClipPath(body_path)
        er = hb * 0.095
        sp = hw * 0.41
        lx = look_x * hw * 0.16
        ly = look_y * hh * 0.14 + hh * 0.04 + eye_roll * hh * 1.25

        bead_color = QColor(20, 18, 18)

        for side in [-1, 1]:
            painter.save()
            painter.translate(side * sp + lx, ly)

            if eye_type == "happy":
                # Upward joyful curved arc (^ ^)
                pen = QPen(bead_color, er * 0.65, Qt.SolidLine, Qt.RoundCap)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                arc_r = er * 1.2
                painter.drawArc(QRectF(-arc_r, -arc_r * 0.6, arc_r * 2.0, arc_r * 1.4), int(30 * 16), int(120 * 16))
            else:
                # Solid round black bead eye with natural blink scaling
                painter.scale(1.0, max(0.12, open_factor))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(bead_color))
                painter.drawEllipse(QPointF(0, 0), er, er)

            painter.restore()

        painter.restore()  # Clip path

        # 6. Quantum Arc-Reactor Activity Badge (pops in at t = 2.72s)
        if badge > 0.01:
            br = hh * 0.32
            painter.save()
            painter.translate(-hw * 0.76, -hh * 0.70)
            painter.scale(badge, badge)

            # Outer ring
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(11, 12, 14))
            painter.drawEllipse(QPointF(0, 0), br + 2.0, br + 2.0)

            # Arc reactor cyan core
            core_grad = QRadialGradient(0, 0, br)
            core_grad.setColorAt(0.0, QColor(255, 255, 255))
            core_grad.setColorAt(0.5, QColor(0, 240, 255))
            core_grad.setColorAt(1.0, QColor(3, 105, 161))
            painter.setBrush(QBrush(core_grad))
            painter.drawEllipse(QPointF(0, 0), br, br)

            # 3 concentric quantum dots
            painter.setBrush(QColor(11, 12, 14))
            for i in [-1, 0, 1]:
                painter.drawEllipse(QPointF(i * br * 0.48, 0), br * 0.16, br * 0.16)

            painter.restore()

        painter.restore()  # Translation & tilt

        # 7. Dynamic Time-of-Day Greeting Banner Typography
        text_k = _seg(t, 1.20, 1.55)
        if t >= tc:
            text_k *= (1.0 - _seg(t, tc, tc + 0.16))

        if text_k > 0.01:
            slide_x = (1.0 - _ease_out(text_k)) * 14.0
            tx = 264.0 + slide_x

            # Soft radial accent wash behind typography
            wash_grad = QRadialGradient(tx + 100.0, 84.0, 190.0)
            wash_grad.setColorAt(0.0, QColor(0, 240, 255, int(22 * text_k)))
            wash_grad.setColorAt(1.0, QColor(0, 240, 255, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(wash_grad))
            painter.drawRoundedRect(QRectF(240, 36, 385, 96), 16.0, 16.0)

            # Title: Time-of-day Greeting
            painter.setPen(QColor(245, 246, 248, int(255 * text_k)))
            font_title = QFont("Segoe UI", 16)
            font_title.setBold(True)
            painter.setFont(font_title)
            painter.drawText(QRectF(tx, 42, 360, 28), Qt.AlignLeft | Qt.AlignVCenter, self._banner_title)

            # Subtitle: Day of week, Date & 12h Time
            painter.setPen(QColor(147, 152, 161, int(255 * text_k)))
            font_sub = QFont("Segoe UI", 11)
            font_sub.setWeight(QFont.Medium)
            painter.setFont(font_sub)
            painter.drawText(QRectF(tx, 69, 360, 22), Qt.AlignLeft | Qt.AlignVCenter, self._banner_sub)

            # Status pill with active green dot
            painter.setPen(QColor(34, 197, 94, int(255 * text_k)))
            font_dot = QFont("Segoe UI", 10)
            painter.setFont(font_dot)
            painter.drawText(QRectF(tx, 91, 14, 18), Qt.AlignLeft | Qt.AlignVCenter, "●")

            painter.setPen(QColor(142, 147, 156, int(255 * text_k)))
            font_tag = QFont("Segoe UI", 10)
            painter.setFont(font_tag)
            painter.drawText(QRectF(tx + 14, 91, 340, 18), Qt.AlignLeft | Qt.AlignVCenter, self._banner_tag)

            # Quick helper hint
            painter.setPen(QColor(100, 105, 115, int(180 * text_k)))
            font_hint = QFont("Segoe UI", 9)
            painter.setFont(font_hint)
            painter.drawText(QRectF(tx, 110, 360, 16), Qt.AlignLeft | Qt.AlignVCenter, "Click anywhere to continue • Esc to minimize")

        painter.end()
