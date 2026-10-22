# gui/island/animator.py
"""Spring physics and easing engine ported directly from Coucou Windows client (anim.ts).

Replicates the authentic Apple / macOS Dynamic Island spring feel:
- Spring: omega = 2*PI / response, zeta = dampingFraction. Integrated per frame (sub-stepped).
- close_curve: cubic-bezier(0.45, 0, 0.2, 1) over 340ms for clean non-oscillating collapse.
- Tracked: value driven by Spring when expanding/growing, or timed curve when shrinking.
- IslandPhysicsAnimator: controls island width, height, bot position (cx, cy), bot diameter (d), and opacity.
"""

import math
import time
from typing import Callable, Optional


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> Callable[[float], float]:
    """Cubic-bezier easing matching CSS cubic-bezier(x1, y1, x2, y2) with Newton-bisection solver."""
    def cx(t: float) -> float:
        return ((1.0 - t) ** 2 * 3.0 * t * x1) + (3.0 * (1.0 - t) * t * t * x2) + (t ** 3)

    def cy(t: float) -> float:
        return ((1.0 - t) ** 2 * 3.0 * t * y1) + (3.0 * (1.0 - t) * t * t * y2) + (t ** 3)

    def solve(x: float) -> float:
        lo = 0.0
        hi = 1.0
        t = x
        for _ in range(14):
            v = cx(t)
            if v < x:
                lo = t
            else:
                hi = t
            t = (lo + hi) / 2.0
        return cy(t)

    return solve


# Coucou 340ms close curve (.45, 0, .2, 1)
close_curve = cubic_bezier(0.45, 0.0, 0.2, 1.0)


class Spring:
    """SwiftUI / Coucou equivalent spring: omega = 2*PI / response, zeta = damping."""

    def __init__(self, value: float, response: float = 0.5, damping: float = 0.72):
        self.value = float(value)
        self.target = float(value)
        self.velocity = 0.0
        self.omega = (2.0 * math.pi) / response
        self.zeta = damping

    def configure(self, response: float, damping: float):
        self.omega = (2.0 * math.pi) / response
        self.zeta = damping

    def set(self, value: float):
        self.value = float(value)
        self.target = float(value)
        self.velocity = 0.0

    @property
    def settled(self) -> bool:
        return abs(self.target - self.value) < 0.1 and abs(self.velocity) < 0.2

    def step(self, dt: float):
        # Sub-stepping to maintain physical stability even if frame drops occur
        steps = max(1, math.ceil(dt / (1.0 / 240.0)))
        h = dt / steps
        for _ in range(steps):
            acc = (self.omega * self.omega * (self.target - self.value)) - (2.0 * self.zeta * self.omega * self.velocity)
            self.velocity += acc * h
            self.value += self.velocity * h


class Tracked:
    """Value driven by Spring (expanding) or timed curve (shrinking), matching Coucou IslandContainer."""

    def __init__(self, value: float):
        self.spring = Spring(value)
        self.curve_from = float(value)
        self.curve_to = float(value)
        self.curve_start = 0.0
        self.curve_dur = 0.340  # 340 ms
        self.mode = "idle"  # "spring", "curve", "idle"

    @property
    def value(self) -> float:
        return self.spring.value

    @property
    def target(self) -> float:
        return self.spring.target

    @property
    def animating(self) -> bool:
        return self.mode != "idle"

    def jump(self, v: float):
        self.spring.set(v)
        self.mode = "idle"

    def spring_to(self, v: float, response: float = 0.5, damping: float = 0.72):
        self.spring.configure(response, damping)
        self.spring.target = float(v)
        self.mode = "spring"

    def curve_towards(self, v: float, duration_s: float = 0.340, now: Optional[float] = None):
        if now is None:
            now = time.monotonic()
        self.curve_from = self.spring.value
        self.curve_to = float(v)
        self.curve_start = now
        self.curve_dur = max(0.01, duration_s)
        self.spring.target = float(v)
        self.spring.velocity = 0.0
        self.mode = "curve"

    def step(self, dt: float, now: Optional[float] = None):
        if now is None:
            now = time.monotonic()

        if self.mode == "spring":
            self.spring.step(dt)
            if self.spring.settled:
                self.spring.value = self.spring.target
                self.spring.velocity = 0.0
                self.mode = "idle"
        elif self.mode == "curve":
            p = clamp((now - self.curve_start) / self.curve_dur, 0.0, 1.0)
            eased = close_curve(p)
            self.spring.value = lerp(self.curve_from, self.curve_to, eased)
            if p >= 1.0:
                self.spring.value = self.curve_to
                self.spring.velocity = 0.0
                self.mode = "idle"


class IslandPhysicsAnimator:
    """High-fidelity animation controller coordinating Coucou geometry properties."""

    def __init__(self, initial_w: float = 288, initial_h: float = 32):
        self.w = Tracked(initial_w)
        self.h = Tracked(initial_h)
        self.bot_cx = Tracked(40.0)
        self.bot_cy = Tracked(16.0)
        self.bot_d = Tracked(20.0)
        self.opacity = Tracked(1.0)
        self._last_time = time.monotonic()

    @property
    def is_animating(self) -> bool:
        return (
            self.w.animating or
            self.h.animating or
            self.bot_cx.animating or
            self.bot_cy.animating or
            self.bot_d.animating or
            self.opacity.animating
        )

    def transition_to(
        self,
        target_w: float,
        target_h: float,
        bot_cx: float,
        bot_cy: float,
        bot_d: float,
        opacity: float = 1.0,
        is_closing: bool = False,
        response: float = 0.5,
        damping: float = 0.72
    ):
        """Animates towards target dimensions using Spring (open) or Curve (close)."""
        now = time.monotonic()
        if is_closing:
            self.w.curve_towards(target_w, duration_s=0.340, now=now)
            self.h.curve_towards(target_h, duration_s=0.340, now=now)
            self.bot_cx.curve_towards(bot_cx, duration_s=0.340, now=now)
            self.bot_cy.curve_towards(bot_cy, duration_s=0.340, now=now)
            self.bot_d.curve_towards(bot_d, duration_s=0.340, now=now)
            self.opacity.curve_towards(opacity, duration_s=0.250, now=now)
        else:
            self.w.spring_to(target_w, response=response, damping=damping)
            self.h.spring_to(target_h, response=response, damping=damping)
            self.bot_cx.spring_to(bot_cx, response=response, damping=damping)
            self.bot_cy.spring_to(bot_cy, response=response, damping=damping)
            self.bot_d.spring_to(bot_d, response=response, damping=damping)
            self.opacity.spring_to(opacity, response=response, damping=damping)

    def jump_to(self, target_w: float, target_h: float, bot_cx: float, bot_cy: float, bot_d: float, opacity: float = 1.0):
        self.w.jump(target_w)
        self.h.jump(target_h)
        self.bot_cx.jump(bot_cx)
        self.bot_cy.jump(bot_cy)
        self.bot_d.jump(bot_d)
        self.opacity.jump(opacity)

    def step(self) -> bool:
        """Steps physics forward by dt. Returns True if any property is still animating."""
        now = time.monotonic()
        dt = clamp(now - self._last_time, 0.001, 0.050)
        self._last_time = now

        self.w.step(dt, now)
        self.h.step(dt, now)
        self.bot_cx.step(dt, now)
        self.bot_cy.step(dt, now)
        self.bot_d.step(dt, now)
        self.opacity.step(dt, now)

        return self.is_animating
