# gui/island/character.py
"""Original JARVIS Core Companion Character Widget (Coucou Interaction Model).

Implements a high-fidelity living AI desktop companion:
- Coucou-style Apple super-ellipse (squircle) organic body with 60 FPS breathing
- Expressive cybernetic aperture eyes (pill, wide, happy, closed, flat, wink, spiral)
- Smooth cursor look tracking (yaw, pitch, roll) with natural spring damping
- Real-time Audio Reactive Visualizer:
  * Responds to REAL microphone RMS audio levels from JARVIS speech pipeline
  * Concentric acoustic ripple waves radiating outward in LISTENING state
  * 5-bar animated audio-level equalizer in LISTENING state
  * Responsive speech waveform oscillating to TTS synthesis in SPEAKING state
- State-aware animations:
  * IDLE: Gentle breathing pulse, eye look tracking, natural micro-blinks
  * LISTENING: Bright cyan aura, expanding audio ripples, active microphone equalizer
  * THINKING: Violet-indigo core, 3 orbiting luminous particles with fading trails
  * SPEAKING: Dynamic speech waveform, acoustic mouth pulse
  * WORKING: Energetic orbital rotation, vibrant blue core
  * SUCCESS: Joyful curved arc eyes, emerald sparkle flare, happy bounce
  * ERROR: Crimson warning pulse, flat alert eyes, subtle tremor
  * SLEEPING: Low-energy quiescent core, closed curved eyelids, floating 'z' particles
"""

import math
import os
import random
import re
import time
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QFont, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap, QRadialGradient
)
from PySide6.QtWidgets import QWidget

from .state_machine import IslandState

# ── Affection / Appreciation Regex Pattern ────────────────────────────────────
AFFECTION_REGEX = re.compile(
    r"\b(?:"
    r"(?:i\s+)?love\s+(?:you|u|ya)|"
    r"love\s+you\s+jarvis|"
    r"thank\s+you|thanks|thanku|thx|dhanyawad|shukriya|"
    r"(?:you\s+are|you're|u\s+r|tum\s+bahut)\s+(?:awesome|amazing|the\s+best|great|sweet|cute|so\s+good|wonderful|cool|acche)|"
    r"good\s+job|great\s+job|well\s+done|shabash|badhiya\s+kaam|"
    r"proud\s+of\s+you|you\s+rock|so\s+smart|meri\s+jaan|i\s+like\s+you"
    r")\b",
    flags=re.IGNORECASE
)


def is_affection_or_praise(text: str) -> bool:
    """Returns True if the text expresses affection, gratitude, or praise."""
    if not text:
        return False
    return bool(AFFECTION_REGEX.search(str(text).strip()))


class JarvisCharacter(QWidget):
    """Living, interactive JARVIS AI Companion Character (CharacterController).

    States: IDLE, LISTENING, THINKING, SPEAKING, WORKING, SUCCESS, ERROR,
    LOVE, PROUD, HAPPY, CONFUSED, SURPRISED (+ legacy aliases).
    """

    state_changed = Signal(str)

    # Canonical character states (spec §7 & Coucou master spec)
    CANONICAL_STATES = (
        "idle", "listening", "thinking", "speaking", "working", "searching",
        "approval", "question", "success", "finished", "error", "ratelimit",
        "sleeping", "dizzy", "love", "proud", "wink", "annoyed", "happy",
        "confused", "surprised", "sad",
    )

    # Soft body-tint wash per state (bottom of the porcelain gradient).
    # Reference look: white top melting into a feeling-colored base.
    _STATE_TINTS = {
        "idle": (226, 212, 198), "listening": (183, 224, 254),
        "thinking": (221, 214, 254), "processing": (199, 210, 254),
        "speaking": (214, 196, 255), "executing": (205, 225, 255),
        "working": (200, 222, 255), "searching": (205, 218, 255),
        "success": (193, 240, 214), "finished": (193, 240, 214),
        "approval": (255, 228, 180), "warning": (255, 228, 180),
        "question": (195, 235, 245), "error": (255, 203, 203),
        "ratelimit": (255, 222, 180), "sleeping": (199, 213, 230),
        "paused": (199, 213, 230), "dizzy": (245, 205, 230),
        "emote_love": (245, 218, 226), "love": (245, 218, 226),
        "proud": (255, 232, 196), "emote_proud": (255, 232, 196),
        "wink": (230, 222, 212), "annoyed": (238, 215, 215),
        "happy": (255, 224, 214), "emote_happy": (255, 224, 214),
        "confused": (193, 238, 244), "emote_confused": (193, 238, 244),
        "surprised": (198, 230, 255), "emote_surprised": (198, 230, 255),
        "sad": (203, 219, 236), "emote_sad": (203, 219, 236),
    }

    # Floating status badge per state: (kind, r, g, b).
    # kind: dots pill | alert (!) | question (?) | search (magnifying glass) | dot (plain).
    # Rule: badge means "Mochi is engaged". Idle shows a clean face — when the
    # work is done the badge goes away instead of looking like stuck progress.
    _STATE_BADGES = {
        "listening": ("dots", 56, 184, 248),
        "working": ("dots", 59, 130, 246),       # Blue working state with '...'
        "executing": ("dots", 59, 130, 246),
        "thinking": ("dots", 168, 85, 247),     # Purple thinking state with '...'
        "searching": ("search", 59, 130, 246),   # Search indicator
        "success": ("dot", 34, 197, 94),
        "finished": ("dot", 34, 197, 94),
        "approval": ("alert", 245, 158, 11),     # Orange approval state with '!'
        "warning": ("alert", 245, 158, 11),
        "question": ("question", 34, 211, 238),  # Cyan question state with '?'
        "error": ("dot", 239, 68, 68),
        "ratelimit": ("alert", 245, 158, 11),
        "confused": ("question", 34, 211, 238),
        "emote_confused": ("question", 34, 211, 238),
    }

    def __init__(self, parent=None, size: int = 36):
        super().__init__(parent)
        self._size = size
        self.resize(size + 16, size + 16)
        # The character paints every pixel itself — never let Qt fill a
        # background box behind it (no black/gray rectangle, ever).
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

        # Active state
        self._current_state = "idle"
        self._eye_shape = "pill"  # pill, wide, happy, closed, flat, wink, spiral

        # Animation timing
        self._start_time = time.time()
        self._blink_start = 0.0
        self._is_blinking = False
        self._next_blink_time = time.time() + random.uniform(2.5, 5.0)

        # Smooth cursor tracking (yaw & pitch)
        self._look_x = 0.0
        self._look_y = 0.0
        self._target_look_x = 0.0
        self._target_look_y = 0.0
        self._is_hovered = False
        self._hover_enter_time = 0.0
        self._last_love_at = 0.0

        # Live Real-time Audio Level (0.0 to 1.0)
        self._audio_level = 0.0
        self._target_audio_level = 0.0
        self._is_user_speaking = False

        # Particles & orbits
        self._orbit_angle = 0.0
        self._click_pulse_radius = 0.0
        self._click_pulse_alpha = 0.0
        self._z_particles: List[Tuple[float, float, float, float]] = []  # x, y, alpha, size
        # Dynamic state physics (bounce & shake)
        self._shake_intensity = 0.0
        self._bounce_intensity = 0.0

        # Emote lifecycle & Affection tracking
        self._is_emote_active = False
        self._emote_type: Optional[str] = None
        self._emote_start_time = 0.0
        self._emote_duration = 1.8
        self._emote_previous_state = "idle"
        self._emote_alpha = 0.0
        self._floating_hearts: List[List[float]] = []  # [x, y, alpha, size, speed_y, wobble_phase]
        self._emote_particles_kind = "hearts"
        self._last_z_spawn = 0.0
        self._animation_intensity = 1.0  # 0.0..1.5 (Settings → Appearance)
        self._tick_count = 0

        # Smooth emotion crossfade targets (lerped every tick, never jumps)
        self._tint_cur = [226.0, 212.0, 198.0]
        self._core_cur = [0.0, 240.0, 255.0]
        self._badge_pop = 1.0
        self._stars: List[List[float]] = []  # [x, y, alpha, size, phase, rise]

        # Hoisted paint objects (no per-frame allocs on the hot path)
        self._bead_color = QColor(20, 18, 18)
        self._bead_brush = QBrush(self._bead_color)
        self._badge_font = QFont("Segoe UI", 10, QFont.Bold)

        # Voice truth: is TTS *actually* producing sound right now, and when was
        # the last real voice activity (mic or TTS start)? The mouth and the
        # speaking state follow truth — never a stuck flag.
        self._tts_active = False
        self._last_voice_time = 0.0
        self._speaking_since = 0.0

        # Independent Appearance / Accessory system (spec §12)
        try:
            from .accessories import AccessoryManager
            self.accessories = AccessoryManager()
        except Exception:
            self.accessories = None

        # Official Coucou Love Emote pixmap reference (with alpha transparency)
        love_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "char_emote_love_alpha.png")
        if not os.path.exists(love_path):
            love_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "char_emote_love.png")
        self._love_pixmap: Optional[QPixmap] = QPixmap(love_path) if os.path.exists(love_path) else None

        # Coucou Slap, Squash, Rotation, and Search dynamics
        self._squash_scale_x = 1.0
        self._squash_scale_y = 1.0
        self._rotation_deg = 0.0
        self._head_tilt_deg = 0.0
        self._search_phase = 0.0
        self._dizzy_until = 0.0
        self._chew_phase = 0.0
        self._chew_until = 0.0
        self._click_history: List[float] = []

        # State accent palettes (Primary RGBA, Glow RGBA)
        self._state_palettes = {
            "idle": (QColor(0, 240, 255), QColor(0, 240, 255, 65)),          # Electric Cyan
            "listening": (QColor(34, 211, 238), QColor(34, 211, 238, 140)),  # Bright Cyan
            "thinking": (QColor(168, 85, 247), QColor(168, 85, 247, 120)),   # Violet Purple
            "processing": (QColor(99, 102, 241), QColor(99, 102, 241, 110)), # Indigo
            "speaking": (QColor(56, 189, 248), QColor(56, 189, 248, 130)),   # Sky Blue
            "executing": (QColor(59, 130, 246), QColor(59, 130, 246, 120)),  # Electric Blue
            "working": (QColor(59, 130, 246), QColor(59, 130, 246, 120)),    # Electric Blue
            "searching": (QColor(99, 102, 241), QColor(99, 102, 241, 120)),  # Indigo/Purple
            "success": (QColor(34, 197, 94), QColor(34, 197, 94, 130)),      # Emerald
            "finished": (QColor(34, 197, 94), QColor(34, 197, 94, 130)),     # Emerald
            "approval": (QColor(245, 165, 36), QColor(245, 165, 36, 120)),   # Amber
            "warning": (QColor(245, 165, 36), QColor(245, 165, 36, 120)),    # Amber
            "question": (QColor(34, 211, 238), QColor(34, 211, 238, 130)),   # Cyan
            "error": (QColor(244, 80, 94), QColor(244, 80, 94, 130)),        # Crimson
            "ratelimit": (QColor(245, 165, 36), QColor(245, 165, 36, 110)),  # Orange
            "sleeping": (QColor(107, 112, 121), QColor(107, 112, 121, 50)),  # Dim Slate
            "paused": (QColor(107, 112, 121), QColor(107, 112, 121, 50)),
            "dizzy": (QColor(244, 114, 182), QColor(244, 114, 182, 130)),    # Pink
            "emote_love": (QColor(255, 77, 109), QColor(255, 105, 180, 160)), # Affection Rose/Pink
            "love": (QColor(255, 77, 109), QColor(255, 105, 180, 160)),
            "proud": (QColor(250, 204, 21), QColor(250, 204, 21, 130)),       # Gold
            "emote_proud": (QColor(250, 204, 21), QColor(250, 204, 21, 130)),
            "wink": (QColor(0, 240, 255), QColor(0, 240, 255, 65)),
            "annoyed": (QColor(248, 113, 113), QColor(248, 113, 113, 110)),  # Light Red
            "happy": (QColor(34, 197, 94), QColor(34, 197, 94, 120)),
            "emote_happy": (QColor(34, 197, 94), QColor(34, 197, 94, 120)),
            "confused": (QColor(251, 146, 60), QColor(251, 146, 60, 120)),    # Orange
            "emote_confused": (QColor(251, 146, 60), QColor(251, 146, 60, 120)),
            "surprised": (QColor(56, 189, 248), QColor(56, 189, 248, 140)),
            "emote_surprised": (QColor(56, 189, 248), QColor(56, 189, 248, 140)),
            "sad": (QColor(100, 116, 139), QColor(100, 116, 139, 110)),
            "emote_sad": (QColor(100, 116, 139), QColor(100, 116, 139, 110)),
        }

        # 60 FPS Render Timer (adaptive: throttled when idle — spec §17)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(16)

    def set_tts_active(self, active: bool) -> None:
        """TTS engine truth: speaking sound is (not) coming out right now."""
        self._tts_active = bool(active)
        now = time.time()
        if self._tts_active:
            self._speaking_since = now
            self._last_voice_time = now
        self.update()

    def set_animation_intensity(self, value: float) -> None:
        try:
            self._animation_intensity = max(0.0, min(1.5, float(value)))
        except Exception:
            pass

    def set_accessory(self, name: str) -> None:
        if self.accessories is not None:
            try:
                from .accessories import Accessory
                self.accessories.set_accessory(Accessory(str(name).lower()))
                self.update()
            except Exception:
                pass

    def stop(self) -> None:
        """Stops the 60fps render timer safely."""
        if hasattr(self, "_timer") and self._timer:
            self._timer.stop()

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)

    def set_audio_level(self, level: float, is_speech: bool = False) -> None:
        """Feeds REAL microphone RMS audio level from speech recognition pipeline."""
        self._target_audio_level = max(0.0, min(1.0, float(level)))
        self._is_user_speaking = is_speech
        if level > 0.04 or is_speech:
            self._last_voice_time = time.time()
        if is_speech and self._current_state in ("idle", "ready", "compact"):
            self.set_system_state("listening")

    def trigger_love_emote(self, duration_s: float = 1.8) -> None:
        """Temporarily displays the LOVE/AFFECTION EMOTE with pop/float/fade and love sound."""
        self.trigger_emote("love", duration_s=duration_s)

    def trigger_slap(self) -> None:
        """User clicked character: quick squash, slap sound, then annoyed reaction."""
        self._squash_scale_y = 0.62
        self._squash_scale_x = 1.38
        self._click_pulse_radius = self._size * 0.4
        self._click_pulse_alpha = 0.9
        try:
            from ..sound_effects import Sound
            Sound.play("slap", reason="character_click")
        except Exception:
            pass
        QTimer.singleShot(200, self._on_slap_reaction)

    def _on_slap_reaction(self) -> None:
        if self._current_state != "dizzy":
            self.set_system_state("annoyed")
            try:
                from ..sound_effects import Sound
                Sound.play("annoyed", reason="after_slap")
            except Exception:
                pass
            QTimer.singleShot(1400, self._revert_from_annoyed)

    def _revert_from_annoyed(self) -> None:
        if self._current_state == "annoyed":
            self.set_system_state("idle")

    def trigger_dizzy(self, duration_s: float = 3.5) -> None:
        """3 rapid slaps: dizzy.wav + spiral eyes + rotation."""
        self._dizzy_until = time.time() + duration_s
        self.set_system_state("dizzy")
        try:
            from ..sound_effects import Sound
            Sound.play("dizzy", reason="triple_slap_dizzy")
        except Exception:
            pass

    def trigger_gulp(self, duration_s: float = 1.6) -> None:
        """File accepted: gulp.wav + mouth slot/chew animation."""
        self._chew_until = time.time() + duration_s
        try:
            from ..sound_effects import Sound
            Sound.play("gulp", reason="file_gulp")
        except Exception:
            pass
        self.update()

    def trigger_emote(self, name: str = "love", duration_s: Optional[float] = None) -> None:
        """Generic temporary emote: pop → hold → fade → previous state (spec §13)."""
        try:
            from .emotes import EMOTE_CONFIG, emote_from_string
            em = emote_from_string(name)
            cfg = EMOTE_CONFIG.get(em, {})
            dur = float(duration_s) if duration_s else float(cfg.get("duration", 1.8))
            sound = str(cfg.get("sound", "blip"))
            eye = str(cfg.get("eye", "happy"))
            kind = str(cfg.get("particles", "hearts"))
        except Exception:
            em, dur, sound, eye, kind = None, float(duration_s or 1.8), "blip", "happy", "hearts"
        state_key = f"emote_{em.value}" if em is not None else "emote_happy"
        # Canonical short states (proud/happy/...) also supported directly
        if str(name).lower() in ("proud", "happy", "confused", "surprised", "sad", "love", "wink"):
            state_key = str(name).lower() if str(name).lower() != "love" else "emote_love"
            if em is not None and em.value == "love":
                state_key = "emote_love"
        if not self._is_emote_active:
            self._emote_previous_state = self._current_state if self._current_state else "idle"
        self._is_emote_active = True
        self._emote_type = state_key
        self._emote_start_time = time.time()
        self._emote_duration = float(dur)
        self._emote_particles_kind = kind
        self._bounce_intensity = 1.25
        self.set_system_state(state_key, _from_emote=True)

        # Seed floating particles
        self._floating_hearts.clear()
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        for i in range(5):
            hx = cx + (random.random() - 0.5) * (self._size * 0.8)
            hy = cy - self._size * 0.15 - (i * 3.5)
            self._floating_hearts.append([
                hx, hy, 1.0, random.uniform(3.5, 6.5),
                random.uniform(0.6, 1.1), random.uniform(0.0, 6.28)
            ])
        try:
            from ..sound_effects import JarvisSoundEngine
            JarvisSoundEngine.instance().play(sound)
        except Exception:
            pass

    def _heart_path(self, cx: float, cy: float, size: float) -> QPainterPath:
        """Draws a smooth organic vector heart path."""
        path = QPainterPath()
        path.moveTo(cx, cy + size * 0.45)
        path.cubicTo(cx - size * 0.75, cy - size * 0.15, cx - size * 0.65, cy - size * 0.85, cx, cy - size * 0.35)
        path.cubicTo(cx + size * 0.65, cy - size * 0.85, cx + size * 0.75, cy - size * 0.15, cx, cy + size * 0.45)
        path.closeSubpath()
        return path

    @property
    def current_state(self) -> str:
        return getattr(self, "_current_state", "idle")

    def set_state(self, state: str) -> None:
        """Alias for set_system_state."""
        self.set_system_state(state)

    def set_system_state(self, state: str, _from_emote: bool = False) -> None:
        """Updates character visual state and emotional expression."""
        normalized = str(state).lower().strip()
        if normalized in ("ready", "idle_hidden", "idle_peek", "compact", "expanded"):
            normalized = "idle"
        elif normalized in ("chat", "file_context", "drop"):
            normalized = "idle"
        # Canonical emotion aliases (spec §7)
        alias = {
            "emote_love": "emote_love", "love": "emote_love",
            "emote_proud": "emote_proud", "proud": "proud",
            "emote_happy": "happy", "happy": "happy",
            "emote_surprised": "emote_surprised", "surprised": "surprised",
            "emote_confused": "emote_confused", "confused": "confused",
            "emote_sad": "emote_sad", "sad": "emote_sad",
        }
        if normalized in alias:
            normalized = alias[normalized]

        if normalized not in self._state_palettes:
            normalized = "idle"

        self._current_state = normalized

        # Mouth opens the moment speech begins (even before first audio frame).
        if normalized == "speaking":
            now_s = time.time()
            self._speaking_since = now_s
            self._last_voice_time = now_s

        # Trigger physics dynamics based on state
        if normalized in ("error", "warning"):
            self._shake_intensity = 1.0
        elif normalized == "annoyed":
            self._shake_intensity = 0.8
        elif normalized == "dizzy":
            self._shake_intensity = 0.4
        elif normalized in ("success", "finished"):
            self._bounce_intensity = 1.0
        elif normalized == "approval":
            self._bounce_intensity = 1.1
        elif normalized == "working":
            self._bounce_intensity = 0.35
        elif normalized == "emote_love":
            self._bounce_intensity = 1.25

        # Head tilt
        if normalized == "question":
            self._head_tilt_deg = 8.5
        elif normalized == "wink":
            self._head_tilt_deg = -7.0
        else:
            self._head_tilt_deg = 0.0

        # Select eye expression based on state
        if normalized in ("emote_love", "love"):
            self._eye_shape = "love_hearts"
        elif normalized in ("proud", "emote_proud", "happy"):
            self._eye_shape = "happy"
        elif normalized in ("surprised", "emote_surprised"):
            self._eye_shape = "wide"
        elif normalized in ("confused", "emote_confused", "dizzy"):
            self._eye_shape = "spiral"
        elif normalized in ("sad", "emote_sad"):
            self._eye_shape = "worried"
        elif normalized in ("sleeping", "yawn"):
            self._eye_shape = "closed"
        elif normalized in ("listening", "approval", "question"):
            self._eye_shape = "wide"
        elif normalized in ("success", "finished"):
            self._eye_shape = "happy"
        elif normalized in ("error", "warning"):
            self._eye_shape = "flat"
        elif normalized == "searching":
            self._eye_shape = "searching"
        elif normalized == "ratelimit":
            self._eye_shape = "tired"
        elif normalized == "annoyed":
            self._eye_shape = "line"
        elif normalized == "wink":
            self._eye_shape = "wink"
        elif normalized in ("thinking", "processing"):
            self._eye_shape = "pill"
        elif normalized == "speaking":
            self._eye_shape = "wide"
        else:
            self._eye_shape = "pill"

        self.state_changed.emit(normalized)
        # Fresh feeling, not a snap: restart badge pop + celebration stars on change.
        if normalized != getattr(self, "_prev_painted_state", None):
            self._badge_pop = 0.0
            if normalized in ("proud", "emote_proud", "success", "finished"):
                self._seed_stars()
            self._prev_painted_state = normalized
        self.update()

    def _seed_stars(self) -> None:
        """One-shot celebration burst above the head (proud / success entry)."""
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        for _ in range(7):
            if len(self._stars) >= 14:
                break
            self._stars.append([
                cx + random.uniform(-1.0, 1.0) * self._size * 0.55,
                cy - self._size * 0.45 + random.uniform(-8.0, 4.0),
                1.0, random.uniform(3.0, 5.5),
                random.uniform(0.0, 6.28), random.uniform(0.4, 0.9),
            ])

    @property
    def _eye_aperture(self) -> str:
        """Compatibility property for test harnesses expecting legacy aperture names."""
        mapping = {
            "wide": "wide",
            "happy": "arc_happy",
            "flat": "alert_line",
            "closed": "closed",
            "pill": "pill",
            "love_hearts": "love_hearts",
            "spiral": "spiral",
            "worried": "worried",
        }
        return mapping.get(self._eye_shape, self._eye_shape)

    @property
    def badge_kind(self) -> Optional[str]:
        """Current floating status badge kind (None when the feeling needs none)."""
        badge = self._STATE_BADGES.get(self._current_state)
        return badge[0] if badge else None

    def set_island_state(self, island_state: IslandState) -> None:
        val = island_state.value if isinstance(island_state, IslandState) else str(island_state)
        self.set_system_state(val)

    def _on_tick(self) -> None:
        """Frame update hook (adaptive rate: 60fps active, ~15fps idle — spec §17)."""
        self._tick_count += 1
        idle_like = (
            self._current_state in ("idle", "sleeping", "paused")
            and not self._is_emote_active
            and not self._is_hovered
            and self._audio_level < 0.02
            and self._click_pulse_alpha <= 0.0
            and self._bounce_intensity <= 0.02
            and self._shake_intensity <= 0.02
        )
        # Throttle idle repaints: process every 4th tick (~15fps), keep audio responsive
        if idle_like and (self._tick_count % 4) != 0:
            # Still decay audio target cheaply without repaint
            self._target_audio_level = max(0.0, self._target_audio_level * 0.92)
            self._adapt_timer(idle_like)
            return
        now = time.time()
        t = now - self._start_time
        ai = getattr(self, "_animation_intensity", 1.0)

        # Self-healing speaking state: no TTS sound + no voice activity for a
        # while means the turn is over — settle to idle, never hang open-mouthed.
        if (self._current_state == "speaking" and not self._is_emote_active
                and not self._tts_active
                and (now - self._last_voice_time) > 1.2
                and (now - self._speaking_since) > 1.2):
            self.set_system_state("idle")

        # Smooth audio level low-pass filter
        self._audio_level += (self._target_audio_level - self._audio_level) * 0.22
        # Decay target audio level gently
        self._target_audio_level = max(0.0, self._target_audio_level * 0.92)

        # Emotion crossfade: tint + aura core glide toward the feeling (never snap)
        tgt_tint = self._STATE_TINTS.get(self._current_state, self._STATE_TINTS["idle"])
        pal = self._state_palettes.get(self._current_state, self._state_palettes["idle"])
        tgt_core = (pal[0].red(), pal[0].green(), pal[0].blue())
        for i in range(3):
            self._tint_cur[i] += (tgt_tint[i] - self._tint_cur[i]) * 0.16
            self._core_cur[i] += (tgt_core[i] - self._core_cur[i]) * 0.16
        if self._badge_pop < 1.0:
            self._badge_pop = min(1.0, self._badge_pop + 0.09)

        # Celebration stars drift up, twinkle, fade (bounded, no leaks)
        if self._stars:
            alive_stars = []
            for sx_, sy_, sa, ss, ph, spd in self._stars:
                ph += 0.12
                sy_ -= spd
                sa -= 0.02
                if sa > 0.0 and sy_ > -10.0:
                    alive_stars.append([sx_, sy_, sa, ss, ph, spd])
            self._stars = alive_stars

        # Sustained hover affection: one love reaction per long visit (Coucou-style).
        if (self._is_hovered and self._hover_enter_time > 0.0
                and not self._is_emote_active
                and (now - self._hover_enter_time) > 2.5
                and (now - self._last_love_at) > 30.0):
            self._last_love_at = now
            self.trigger_love_emote(duration_s=1.6)

        # Smooth cursor look tracking with spring ease
        if self._is_hovered or (self.parentWidget() and self.parentWidget().underMouse()):
            cursor_pos = self.mapFromGlobal(QCursor.pos())
            center_x = self.width() / 2.0
            center_y = self.height() / 2.0
            dx = (cursor_pos.x() - center_x) / 120.0
            dy = (cursor_pos.y() - center_y) / 80.0
            self._target_look_x = max(-1.0, min(1.0, dx))
            self._target_look_y = max(-1.0, min(1.0, dy))
        else:
            if self._current_state == "thinking":
                # Looking thoughtfully up and to the right
                self._target_look_x = 0.55
                self._target_look_y = -0.45
            elif self._current_state == "idle":
                # Gentle idle wander — alive even when the room is quiet
                self._target_look_x = math.sin(t * 0.5) * 0.30
                self._target_look_y = math.cos(t * 0.37) * 0.22
            else:
                self._target_look_x = 0.0
                self._target_look_y = 0.0

        self._look_x += (self._target_look_x - self._look_x) * 0.14
        self._look_y += (self._target_look_y - self._look_y) * 0.14

        # Orbit spin for thinking/executing
        if self._current_state in ("thinking", "processing", "executing", "working"):
            speed = 4.0 if self._current_state in ("executing", "working") else 2.2
            self._orbit_angle = (self._orbit_angle + speed) % 360.0

        # Click ripple decay
        if self._click_pulse_alpha > 0.0:
            self._click_pulse_radius += 1.2
            self._click_pulse_alpha = max(0.0, self._click_pulse_alpha - 0.06)

        # Micro-blink schedule
        if self._eye_shape not in ("closed", "happy", "flat"):
            if not self._is_blinking and now >= self._next_blink_time:
                self._is_blinking = True
                self._blink_start = now
            elif self._is_blinking:
                if now - self._blink_start > 0.15:
                    self._is_blinking = False
                    self._next_blink_time = now + random.uniform(2.6, 5.5)

        # Floating 'z' particles for sleeping state
        if self._current_state == "sleeping":
            if now - self._last_z_spawn > 1.2:
                self._last_z_spawn = now
                self._z_particles.append((self.width() * 0.5, self.height() * 0.35, 1.0, 9.0))
            updated_z = []
            for zx, zy, za, zs in self._z_particles:
                zx += 0.35
                zy -= 0.65
                za -= 0.015
                if za > 0.0:
                    updated_z.append((zx, zy, za, zs))
            self._z_particles = updated_z

        # Handle active Love Emote lifecycle (Pop -> Float -> Fade -> Auto Revert)
        if self._is_emote_active:
            elapsed = now - self._emote_start_time
            prog = elapsed / self._emote_duration
            if prog >= 1.0:
                self._is_emote_active = False
                self._emote_alpha = 0.0
                self._floating_hearts.clear()
                # Revert to previous character state automatically
                target_state = self._emote_previous_state if self._emote_previous_state != "emote_love" else "idle"
                self.set_system_state(target_state)
            else:
                # Pop phase (0.0 -> 0.22)
                if prog < 0.22:
                    self._emote_alpha = min(1.0, prog / 0.22)
                # Float & hold phase (0.22 -> 0.78)
                elif prog <= 0.78:
                    self._emote_alpha = 1.0
                # Fade phase (0.78 -> 1.0)
                else:
                    self._emote_alpha = max(0.0, 1.0 - (prog - 0.78) / 0.22)

                # Dynamically spawn subtle floating hearts during emote
                if 0.10 <= prog <= 0.70 and len(self._floating_hearts) < 8 and random.random() < 0.16:
                    cx = self.width() / 2.0
                    cy = self.height() / 2.0
                    hx = cx + (random.random() - 0.5) * (self._size * 0.75)
                    hy = cy - self._size * 0.2
                    self._floating_hearts.append([
                        hx, hy, 1.0, random.uniform(3.5, 6.5),
                        random.uniform(0.6, 1.1), random.uniform(0.0, 6.28)
                    ])

        # Animate floating love hearts
        if self._floating_hearts:
            alive_hearts = []
            for hx, hy, ha, hs, spd, w_ph in self._floating_hearts:
                w_ph += 0.08
                hx += math.sin(w_ph) * 0.35
                hy -= spd
                ha -= 0.018
                if ha > 0.0 and hy > 0:
                    alive_hearts.append([hx, hy, ha, hs, spd, w_ph])
            self._floating_hearts = alive_hearts

        # Decay physics dynamics
        if self._shake_intensity > 0.0:
            self._shake_intensity = max(0.0, self._shake_intensity * 0.88)
        if self._bounce_intensity > 0.0:
            self._bounce_intensity = max(0.0, self._bounce_intensity * 0.86)

        # Squash & stretch decay back to 1.0
        self._squash_scale_x += (1.0 - self._squash_scale_x) * 0.22
        self._squash_scale_y += (1.0 - self._squash_scale_y) * 0.22

        # Dizzy continuous rotation
        if self._current_state == "dizzy":
            self._rotation_deg = (self._rotation_deg + 8.5) % 360.0
            if now > self._dizzy_until:
                self._rotation_deg = 0.0
                self.set_system_state("idle")
        elif self._rotation_deg != 0.0:
            self._rotation_deg = 0.0

        # Searching left-right gaze scan
        if self._current_state == "searching":
            self._search_phase += 0.14
            self._target_look_x = math.sin(self._search_phase) * 0.85
            self._target_look_y = 0.0

        # Chewing swallow oscillation
        if now < self._chew_until:
            self._chew_phase = math.sin((self._chew_until - now) * 16.0)
        else:
            self._chew_phase = 0.0

        self._adapt_timer(idle_like)
        self.update()

    def _adapt_timer(self, idle_like: bool) -> None:
        """Switches render interval: 16ms active vs 66ms idle to keep idle CPU low."""
        try:
            target = 66 if idle_like else 16
            if self._timer.interval() != target:
                self._timer.setInterval(target)
        except Exception:
            pass

    def enterEvent(self, event) -> None:
        # Genuine hover entry only: exactly one hover cue per entry, never a loop.
        if not self._is_hovered:
            try:
                from ..sound_effects import Sound
                Sound.play("hover", reason="avatar_enter", cooldown_ms=1500)
            except Exception:
                pass
            self._hover_enter_time = time.time()
        self._is_hovered = True
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._is_hovered = False
        self._hover_enter_time = 0.0
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            now = time.time()
            self._click_history = [t for t in self._click_history if now - t < 1.5]
            self._click_history.append(now)

            if len(self._click_history) >= 3:
                self._click_history.clear()
                self.trigger_dizzy(duration_s=3.5)
            else:
                self.trigger_slap()
            self.update()
        super().mousePressEvent(event)

    def _squircle_path(self, cx: float, cy: float, rx: float, ry: float) -> QPainterPath:
        """Generates Apple-style super-ellipse (squircle) path with exponent 2/2.7."""
        path = QPainterPath()
        steps = 48
        exp_n = 2.0 / 2.7
        for i in range(steps + 1):
            angle = (i / steps) * 2.0 * math.pi
            ca = math.cos(angle)
            sa = math.sin(angle)
            sign_ca = 1.0 if ca >= 0 else -1.0
            sign_sa = 1.0 if sa >= 0 else -1.0
            px = cx + rx * sign_ca * (abs(ca) ** exp_n)
            py = cy + ry * sign_sa * (abs(sa) ** exp_n)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.closeSubpath()
        return path

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0
        base_r = max(8.0, (min(w, h) - 10.0) / 2.0)

        total_rot = self._rotation_deg + self._head_tilt_deg
        has_rot = abs(total_rot) > 0.01
        if has_rot:
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(total_rot)
            painter.translate(-cx, -cy)

        palette = self._state_palettes.get(self._current_state, self._state_palettes["idle"])
        # Crossfaded live colors (lerped in _on_tick) — feelings glide, never snap.
        core_color = QColor(int(self._core_cur[0]), int(self._core_cur[1]), int(self._core_cur[2]))
        glow_color = QColor(core_color.red(), core_color.green(), core_color.blue(),
                            palette[1].alpha())

        now = time.time()
        t = now - self._start_time

        # ── 1. Breathing & Audio Dynamics ─────────────────────────────────────
        if self._current_state == "sleeping":
            breath_amp = 0.04
            sy = 1.0 + math.sin(t * 1.2) * breath_amp
            sx = 1.0 - math.sin(t * 1.2) * (breath_amp * 0.5)
        elif self._current_state == "listening":
            # Audio-reactive scale expansion (real mic feedback, not lip-sync)
            audio_boost = self._audio_level * 0.14
            sy = 1.0 + audio_boost + math.sin(t * 8.0) * 0.02
            sx = 1.0 - audio_boost * 0.4
        else:
            # Calm breathing everywhere else — speaking included (no lip-sync).
            breath_amp = 0.035
            sy = 1.0 + math.sin(t * 1.8) * breath_amp
            sx = 1.0 - math.sin(t * 1.8) * (breath_amp * 0.5)

        # Micro bounce on success or love emote pop
        if self._bounce_intensity > 0.01:
            bounce_y = -abs(math.sin(t * 12.0)) * (base_r * 0.24 * self._bounce_intensity)
            cy += bounce_y

        # Gentle floating lift during EMOTE_LOVE
        if self._current_state == "emote_love" or self._emote_alpha > 0.01:
            float_lift = -3.2 * math.sin(math.pi * min(1.0, max(0.0, (now - self._emote_start_time) / self._emote_duration))) * self._emote_alpha
            cy += float_lift

        # Micro shake on error
        if self._shake_intensity > 0.01:
            shake_x = math.sin(t * 36.0) * (base_r * 0.20 * self._shake_intensity)
            cx += shake_x

        # Exact aspect ratio ~1.27 matching 128x128@2x.png (207x163 bbox) with squash dynamics
        rx = (base_r * 1.13) * sx * self._squash_scale_x
        ry = (base_r * 0.89) * sy * self._squash_scale_y

        # ── 2. Live Microphone Audio Reactive Ripples (LISTENING State) ────────
        if self._current_state == "listening":
            wave_alpha = int(45 + self._audio_level * 165)
            wave_color = QColor(core_color.red(), core_color.green(), core_color.blue(), wave_alpha)

            for i in range(1, 3):
                wave_r = max(rx, ry) * (1.18 + i * 0.22 + (self._audio_level * 0.35))
                painter.setPen(QPen(wave_color, 1.4, Qt.DashLine if i == 2 else Qt.SolidLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), wave_r, wave_r * 0.88)

        # ── 3. Ambient Aura Glow ──────────────────────────────────────────────
        # Audio-reactive only while listening (mic truth); calm elsewhere.
        aura_boost = self._audio_level * 0.2 if self._current_state == "listening" else 0.0
        aura_r = max(rx, ry) * (1.40 + aura_boost)
        aura_grad = QRadialGradient(cx, cy, aura_r)
        if self._current_state == "emote_love" or self._emote_alpha > 0.01:
            love_glow = QColor(255, 115, 140, int(155 * self._emote_alpha))
            aura_grad.setColorAt(0.0, love_glow)
            aura_grad.setColorAt(0.7, QColor(love_glow.red(), love_glow.green(), love_glow.blue(), int(love_glow.alpha() * 0.25)))
        else:
            aura_grad.setColorAt(0.0, glow_color)
            aura_grad.setColorAt(0.7, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), int(glow_color.alpha() * 0.25)))
        aura_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(aura_grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), aura_r, aura_r)

        # ── 4. Click Pulse Ripple ─────────────────────────────────────────────
        if self._click_pulse_alpha > 0.0:
            rip_color = QColor(core_color.red(), core_color.green(), core_color.blue(), int(self._click_pulse_alpha * 240))
            painter.setPen(QPen(rip_color, 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), self._click_pulse_radius, self._click_pulse_radius)

        # ── 5. Orbiting Energy Particles (Thinking / Executing) ───────────────
        if self._current_state in ("thinking", "processing", "executing", "working"):
            num_particles = 3
            p_dist = max(rx, ry) * 1.25
            for i in range(num_particles):
                angle_rad = math.radians(self._orbit_angle + (i * (360.0 / num_particles)))
                px = cx + math.cos(angle_rad) * p_dist
                py = cy + math.sin(angle_rad) * p_dist
                p_grad = QRadialGradient(px, py, 3.8)
                p_grad.setColorAt(0.0, QColor(255, 255, 255, 250))
                p_grad.setColorAt(0.5, core_color)
                p_grad.setColorAt(1.0, QColor(core_color.red(), core_color.green(), core_color.blue(), 0))
                painter.setBrush(QBrush(p_grad))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(px, py), 3.0, 3.0)

        # ── 6. Squircle Companion Body (Sampled from 128x128@2x.png) ──────────
        body_path = self._squircle_path(cx, cy, rx, ry)

        # Porcelain Ivory Body Gradient: white top melting into the feeling tint.
        # (No grounding shadow: the reference look floats clean with zero black.)
        body_grad = QLinearGradient(cx, cy - ry, cx, cy + ry)
        body_grad.setColorAt(0.0, QColor(248, 241, 233))
        body_grad.setColorAt(0.48, QColor(238, 227, 218))
        body_grad.setColorAt(1.0, QColor(int(self._tint_cur[0]),
                                         int(self._tint_cur[1]),
                                         int(self._tint_cur[2])))
        painter.setBrush(QBrush(body_grad))

        # Solid crisp continuous black outline border matching reference
        stroke_w = max(1.8, rx * 0.058)
        border_pen = QPen(QColor(16, 17, 20), stroke_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(border_pen)
        painter.drawPath(body_path)

        # ── 6.1. Composable Accessories (independent of state — spec §12) ─────
        try:
            if getattr(self, "accessories", None) is not None:
                self.accessories.paint(painter, cx, cy, rx, ry)
        except Exception:
            pass

        # ── 6.5. Soft Blush Cheeks (always on like the reference; deeper on warmth)
        warm = self._current_state in ("emote_love", "love", "happy", "emote_happy",
                                       "proud", "emote_proud", "success", "finished")
        blush_a = 200 if (warm or self._emote_alpha > 0.01) else 95
        blush_col = QColor(242, 156, 163, blush_a)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(blush_col))
        blush_rx = rx * 0.22
        blush_ry = ry * 0.12
        blush_y = cy + ry * 0.20
        painter.drawEllipse(QPointF(cx - rx * 0.52, blush_y), blush_rx, blush_ry)
        painter.drawEllipse(QPointF(cx + rx * 0.52, blush_y), blush_rx, blush_ry)

        # ── 6.6. Cute Blue Dialogue Badge (EMOTE_LOVE State) ──────────────────
        if (self._current_state == "emote_love" or self._emote_alpha > 0.01) and rx >= 10.0:
            bubble_alpha = int(255 * self._emote_alpha)
            bx = cx - rx * 0.96
            by = cy - ry * 0.95
            bw = rx * 0.68
            bh = ry * 0.44
            br = bh * 0.50

            # Blue pill bubble with dark outline
            bubble_rect = QRectF(bx, by, bw, bh)
            painter.setPen(QPen(QColor(16, 17, 20, bubble_alpha), max(1.4, rx * 0.05)))
            painter.setBrush(QBrush(QColor(59, 130, 246, bubble_alpha)))
            painter.drawRoundedRect(bubble_rect, br, br)

            # Three white dialogue dots
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, bubble_alpha)))
            dot_r = max(1.1, bh * 0.15)
            dot_spacing = bw * 0.23
            for d in range(3):
                dx = bx + bw * 0.27 + d * dot_spacing
                dy = by + bh * 0.50
                painter.drawEllipse(QPointF(dx, dy), dot_r, dot_r)

        # ── 6.7. Floating Status Badge (reference look: top-left pill/dot, pops in)
        badge = self._STATE_BADGES.get(self._current_state)
        if badge is not None and rx >= 10.0:
            kind, br_, bg_, bb_ = badge
            p = min(1.0, self._badge_pop)
            pop = 1.0 + 2.70158 * (p - 1.0) ** 3 + 1.70158 * (p - 1.0) ** 2  # ease-out-back
            pop = max(0.01, pop)
            badge_col = QColor(br_, bg_, bb_)
            outline = QPen(QColor(16, 17, 20), max(1.4, rx * 0.05))
            if kind == "dots":
                bw2 = rx * 0.68 * pop
                bh2 = ry * 0.44 * pop
                bx2 = cx - rx * 0.96
                by2 = cy - ry * 0.98
                painter.setPen(outline)
                painter.setBrush(QBrush(badge_col))
                painter.drawRoundedRect(QRectF(bx2, by2, bw2, bh2), bh2 * 0.5, bh2 * 0.5)
                # Animated thinking / processing bounce indicator
                painter.setPen(Qt.NoPen)
                dd = max(1.1, bh2 * 0.15)
                for d in range(3):
                    bounce = math.sin(t * 6.0 + d * 2.094) * 0.5 + 0.5
                    rr = dd * (0.7 + 0.55 * bounce)
                    painter.setBrush(QBrush(QColor(255, 255, 255, int(150 + 105 * bounce))))
                    painter.drawEllipse(
                        QPointF(bx2 + bw2 * 0.27 + d * bw2 * 0.23,
                                by2 + bh2 * 0.50 - bounce * 1.6), rr, rr)
            else:
                cr = ry * 0.30 * pop
                ccx = cx - rx * 0.72
                ccy = cy - ry * 0.78
                painter.setPen(outline)
                painter.setBrush(QBrush(badge_col))
                painter.drawEllipse(QPointF(ccx, ccy), cr, cr)
                if kind in ("alert", "question"):
                    self._badge_font.setPixelSize(max(6, int(cr * 1.15)))
                    painter.setFont(self._badge_font)
                    painter.setPen(QPen(QColor(255, 255, 255)))
                    painter.drawText(QRectF(ccx - cr, ccy - cr, cr * 2.0, cr * 2.0),
                                     Qt.AlignCenter, "!" if kind == "alert" else "?")
                elif kind == "search":
                    painter.setPen(QPen(QColor(255, 255, 255), max(1.2, cr * 0.22)))
                    painter.setBrush(Qt.NoBrush)
                    mg_r = cr * 0.38
                    painter.drawEllipse(QPointF(ccx - cr * 0.12, ccy - cr * 0.12), mg_r, mg_r)
                    painter.drawLine(
                        QPointF(ccx + cr * 0.12, ccy + cr * 0.12),
                        QPointF(ccx + cr * 0.45, ccy + cr * 0.45)
                    )

        # ── 7. Expressive Eyes ────────────────────────────────────────────────
        eye_offset_x = self._look_x * (rx * 0.16)
        eye_offset_y = self._look_y * (ry * 0.14)

        eye_spacing = rx * 0.41
        eye_base_y = cy + ry * 0.04
        eye_r = max(2.2, rx * 0.105)

        left_eye_center = QPointF(cx - eye_spacing + eye_offset_x, eye_base_y + eye_offset_y)
        right_eye_center = QPointF(cx + eye_spacing + eye_offset_x, eye_base_y + eye_offset_y)

        bead_color = self._bead_color

        # Handle blinks
        blink_scale = 1.0
        if self._is_blinking and self._eye_shape not in ("closed", "happy", "flat", "love_hearts"):
            blink_scale = 0.12

        if self._eye_shape == "love_hearts" or (self._current_state == "emote_love" and self._emote_alpha > 0.01):
            # Glowing Sweet Coral-Rose Heart Eyes (♥ ♥)
            heart_size = eye_r * 1.55
            heart_col = QColor(255, 77, 109, int(255 * self._emote_alpha))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(heart_col))
            for e_center in (left_eye_center, right_eye_center):
                h_path = self._heart_path(e_center.x(), e_center.y() + eye_r * 0.05, heart_size)
                painter.drawPath(h_path)

        elif self._eye_shape == "happy":
            # Upward joyful curved arcs (^ ^)
            arc_pen = QPen(bead_color, max(2.0, eye_r * 0.55), Qt.SolidLine, Qt.RoundCap)
            painter.setPen(arc_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(QRectF(left_eye_center.x() - eye_r, left_eye_center.y() - eye_r * 0.7, eye_r * 2.0, eye_r * 1.5), 30 * 16, 120 * 16)
            painter.drawArc(QRectF(right_eye_center.x() - eye_r, right_eye_center.y() - eye_r * 0.7, eye_r * 2.0, eye_r * 1.5), 30 * 16, 120 * 16)

        elif self._eye_shape == "wink":
            # Left eye closed joy arc (^), right eye open bead (•)
            arc_pen = QPen(bead_color, max(2.0, eye_r * 0.55), Qt.SolidLine, Qt.RoundCap)
            painter.setPen(arc_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(QRectF(left_eye_center.x() - eye_r, left_eye_center.y() - eye_r * 0.7, eye_r * 2.0, eye_r * 1.5), 30 * 16, 120 * 16)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._bead_brush)
            painter.drawEllipse(right_eye_center, eye_r * 1.1, max(0.8, eye_r * 1.1 * blink_scale))

        elif self._eye_shape == "line":
            # Annoyed straight horizontal slit line eyes (- -)
            line_pen = QPen(bead_color, max(2.2, eye_r * 0.55), Qt.SolidLine, Qt.RoundCap)
            painter.setPen(line_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(QPointF(left_eye_center.x() - eye_r * 0.9, left_eye_center.y() + eye_r * 0.15),
                             QPointF(left_eye_center.x() + eye_r * 0.9, left_eye_center.y() - eye_r * 0.15))
            painter.drawLine(QPointF(right_eye_center.x() - eye_r * 0.9, right_eye_center.y() - eye_r * 0.15),
                             QPointF(right_eye_center.x() + eye_r * 0.9, right_eye_center.y() + eye_r * 0.15))

        elif self._eye_shape == "tired":
            # Tired half-closed eyes + blue sweat drop on temple
            line_pen = QPen(bead_color, max(2.0, eye_r * 0.5), Qt.SolidLine, Qt.RoundCap)
            painter.setPen(line_pen)
            painter.setBrush(Qt.NoBrush)
            for ec in (left_eye_center, right_eye_center):
                painter.drawLine(QPointF(ec.x() - eye_r, ec.y() - eye_r * 0.2),
                                 QPointF(ec.x() + eye_r, ec.y() - eye_r * 0.2))
                painter.drawArc(QRectF(ec.x() - eye_r, ec.y() - eye_r * 0.5, eye_r * 2.0, eye_r * 1.4), 200 * 16, 140 * 16)
            # Sweat drop on temple
            sw_x = cx + rx * 0.65
            sw_y = cy - ry * 0.55
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(56, 189, 248, 220)))
            painter.drawEllipse(QPointF(sw_x, sw_y), eye_r * 0.55, eye_r * 0.8)

        elif self._eye_shape == "searching":
            # Searching scanning eyes: bead eyes with cyan scanner line
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._bead_brush)
            for ec in (left_eye_center, right_eye_center):
                painter.drawEllipse(ec, eye_r * 1.05, eye_r * 1.05)
            scan_col = QColor(56, 189, 248, int(80 + math.sin(t * 10.0) * 40))
            painter.setPen(QPen(scan_col, 1.4, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(QPointF(left_eye_center.x() - eye_r * 1.5, eye_base_y),
                             QPointF(right_eye_center.x() + eye_r * 1.5, eye_base_y))

        elif self._eye_shape == "closed":
            # Peaceful sleeping closed curves (u u)
            sleep_pen = QPen(QColor(110, 105, 100), max(1.8, eye_r * 0.45), Qt.SolidLine, Qt.RoundCap)
            painter.setPen(sleep_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(QRectF(left_eye_center.x() - eye_r, left_eye_center.y() - eye_r * 0.4, eye_r * 2.0, eye_r * 1.2), 210 * 16, 120 * 16)
            painter.drawArc(QRectF(right_eye_center.x() - eye_r, right_eye_center.y() - eye_r * 0.4, eye_r * 2.0, eye_r * 1.2), 210 * 16, 120 * 16)

        elif self._eye_shape == "flat":
            # Alert / error horizontal straight bars (- -)
            line_pen = QPen(bead_color, max(2.2, eye_r * 0.6), Qt.SolidLine, Qt.RoundCap)
            painter.setPen(line_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(QPointF(left_eye_center.x() - eye_r, left_eye_center.y()), QPointF(left_eye_center.x() + eye_r, left_eye_center.y()))
            painter.drawLine(QPointF(right_eye_center.x() - eye_r, right_eye_center.y()), QPointF(right_eye_center.x() + eye_r, right_eye_center.y()))

        elif self._eye_shape == "spiral":
            # Dizzy / confused spiral eyes (@ @), slowly turning
            spin = t * 1.6
            spiral_pen = QPen(bead_color, max(1.6, eye_r * 0.34), Qt.SolidLine, Qt.RoundCap)
            painter.setPen(spiral_pen)
            painter.setBrush(Qt.NoBrush)
            for e_center in (left_eye_center, right_eye_center):
                poly_pts = []
                turns, segs = 2.4, 30
                for s in range(segs + 1):
                    frac = s / segs
                    ang = spin + frac * turns * 2.0 * math.pi
                    rr = eye_r * (0.10 + 0.90 * frac)
                    poly_pts.append(QPointF(e_center.x() + math.cos(ang) * rr,
                                            e_center.y() + math.sin(ang) * rr))
                path = QPainterPath()
                path.moveTo(poly_pts[0])
                for pt in poly_pts[1:]:
                    path.lineTo(pt)
                painter.drawPath(path)

        elif self._eye_shape == "worried":
            # Sad / worried: steady bead left, small lifted curve right
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._bead_brush)
            painter.drawEllipse(left_eye_center, eye_r, max(0.8, eye_r * blink_scale))
            worry_pen = QPen(bead_color, max(2.0, eye_r * 0.5), Qt.SolidLine, Qt.RoundCap)
            painter.setPen(worry_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(QRectF(right_eye_center.x() - eye_r * 0.9,
                                   right_eye_center.y() - eye_r * 0.9,
                                   eye_r * 1.8, eye_r * 1.4), 35 * 16, 110 * 16)

        else:
            # Round Solid Bead Eyes (Matching 128x128@2x.png)
            cur_r = eye_r * (1.18 if self._eye_shape == "wide" else 1.0)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._bead_brush)

            for eye_pt in (left_eye_center, right_eye_center):
                painter.drawEllipse(eye_pt, cur_r, max(0.8, cur_r * blink_scale))

        # ── 8. Human Mouth (feeling-driven, never lip-synced)
        # Speaking wears the same calm smile as joy with speech reactive dynamics.
        st = self._current_state
        mouth_y = cy + ry * 0.42
        mouth_pen = QPen(QColor(20, 18, 18, 220), max(1.6, eye_r * 0.5), Qt.SolidLine, Qt.RoundCap)
        if self._chew_phase != 0.0:
            # Gulp/chewing mouth: expands & contracts in animated swallow cycle
            ch_r = max(2.0, eye_r * (0.8 + 0.45 * self._chew_phase))
            painter.setPen(QPen(QColor(20, 18, 18), max(1.6, eye_r * 0.45)))
            painter.setBrush(QBrush(QColor(240, 140, 150)))
            painter.drawEllipse(QPointF(cx, mouth_y), ch_r * 1.3, ch_r * 0.9)
        elif st in ("love", "emote_love", "happy", "emote_happy", "proud",
                  "emote_proud", "success", "finished", "speaking"):
            painter.setPen(mouth_pen)
            painter.setBrush(Qt.NoBrush)
            mw = rx * 0.22
            painter.drawArc(QRectF(cx - mw, mouth_y - mw * 0.55, mw * 2.0, mw * 1.3),
                            200 * 16, 140 * 16)
        elif st in ("sad", "emote_sad"):
            painter.setPen(mouth_pen)
            painter.setBrush(Qt.NoBrush)
            mw = rx * 0.18
            painter.drawArc(QRectF(cx - mw, mouth_y - mw * 0.35, mw * 2.0, mw * 1.1),
                            20 * 16, 140 * 16)
        elif st == "surprised" or st == "emote_surprised":
            painter.setPen(mouth_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(cx, mouth_y + 1.0), rx * 0.07, ry * 0.09)
        elif st in ("confused", "emote_confused", "error", "warning"):
            painter.setPen(mouth_pen)
            painter.setBrush(Qt.NoBrush)
            mw = rx * 0.13
            painter.drawLine(QPointF(cx - mw, mouth_y), QPointF(cx + mw, mouth_y))

        # ── 9. Live 5-Bar Audio Equalizer (LISTENING State) ───────────────────
        if self._current_state == "listening" and self._size >= 28:
            bar_y = cy + ry * 0.45
            bar_w = 2.2
            spacing = 4.0
            num_bars = 5
            total_w = num_bars * bar_w + (num_bars - 1) * (spacing - bar_w)
            start_x = cx - total_w / 2.0

            painter.setPen(Qt.NoPen)
            for b in range(num_bars):
                phase_offset = b * 0.8
                osc = math.sin(t * 14.0 + phase_offset) * 0.5 + 0.5
                bar_h = max(2.0, (self._audio_level * 10.0 + osc * 3.0))
                bx = start_x + b * spacing
                painter.setBrush(QBrush(core_color))
                painter.drawRoundedRect(QRectF(bx, bar_y - bar_h / 2.0, bar_w, bar_h), 1.0, 1.0)

        # ── 10. Floating Sleep 'Z's (SLEEPING State) ──────────────────────────
        if self._current_state == "sleeping" and self._z_particles:
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            for zx, zy, za, zs in self._z_particles:
                z_col = QColor(180, 185, 195, int(za * 220))
                painter.setPen(QPen(z_col))
                painter.drawText(int(zx), int(zy), "Z")

        # ── 11. Floating Love Hearts (EMOTE_LOVE State) ───────────────────────
        if self._floating_hearts:
            for hx, hy, ha, hs, _, _ in self._floating_hearts:
                h_col = QColor(255, 80, 110, int(ha * 230))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(h_col))
                path = self._heart_path(hx, hy, hs)
                painter.drawPath(path)

        # ── 12. Celebration Stars (proud / success entry — topmost, never under)
        if self._stars:
            for sx_, sy_, sa, ss, ph, _ in self._stars:
                tw = 0.6 + 0.4 * math.sin(ph)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(250, 200, 60, int(sa * 230 * tw))))
                painter.drawPath(self._star_path(sx_, sy_, ss))

        if has_rot:
            painter.restore()

    def _star_path(self, cx: float, cy: float, r: float) -> QPainterPath:
        """Five-point celebration star path."""
        path = QPainterPath()
        for i in range(11):
            ang = -math.pi / 2.0 + i * math.pi / 5.0
            rr = r if i % 2 == 0 else r * 0.45
            px = cx + math.cos(ang) * rr
            py = cy + math.sin(ang) * rr
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.closeSubpath()
        return path
