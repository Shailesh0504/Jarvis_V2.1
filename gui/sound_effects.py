# gui/sound_effects.py
"""JARVIS Audio Event Feedback Engine (Coucou-style, event-driven).

Single centralized sound system for all GUI feedback. Behavioural rules:
- Sounds fire ONLY on semantic events/state transitions (never from frame
  loops, audio callbacks, RMS/VAD/STT-partial paths, or progress ticks).
- Windows-first: preloaded pygame mixer playback (overlap-safe channels,
  volume honored); winsound async as fallback. The mixer is owned by the
  TTS pipeline — this engine never (re)initializes it.
- Missing/corrupt assets fail silent with a debug log. No system beeps, ever.
- Centralized dedup: per-name cooldowns + exact-event suppression.
"""

import os
import sys
import logging
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("jarvis.gui.sound")

ASSETS_SOUNDS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "sounds"
)
JARVIS_SOUNDS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins", "sounds"
)

SOUND_NAMES = [
    "peek", "open", "close", "hover", "blip", "slap", "annoyed", "dizzy",
    "greet", "greeting", "work", "finish", "error", "approval", "question",
    "approve", "gulp", "tick", "send", "love", "pop", "proud", "wink",
    "yawn", "attach", "think", "search", "rate", "sleep"
]

# Subtle by default: UI feedback sits under voice, never over it.
DEFAULT_VOLUME = 0.12
DEFAULT_COOLDOWN_MS = 800
EVENT_MEMORY_SEC = 5.0


class JarvisSoundEngine:
    """Manages dynamic desktop companion audio cues and sound effects."""

    _instance: Optional["JarvisSoundEngine"] = None

    def __init__(self, sounds_dir: Optional[str] = None):
        self.sounds_dir = sounds_dir or ASSETS_SOUNDS_DIR
        self.plugin_sounds_dir = JARVIS_SOUNDS_DIR
        self.enabled = True
        self.volume = DEFAULT_VOLUME
        self._is_headless = (
            os.environ.get("QT_QPA_PLATFORM") == "offscreen"
            or bool(os.environ.get("PYTEST_CURRENT_TEST"))
        )
        self._cache: Dict[str, object] = {}
        self._lock = threading.Lock()
        self._last_play: Dict[str, float] = {}
        self._seen_events: Dict[Tuple[str, str], float] = {}
        self.played_history: List[Tuple[str, str, float]] = []
        self.last_played_sound: Optional[str] = None
        self.record_all_plays_for_test: bool = False

    @classmethod
    def instance(cls) -> "JarvisSoundEngine":
        if cls._instance is None:
            cls._instance = JarvisSoundEngine()
        return cls._instance

    def initialize(self) -> None:
        """Best-effort preload of short cues (only if the TTS mixer is ready)."""
        for name in SOUND_NAMES:
            try:
                self._ensure_cached(name)
            except Exception:
                pass

    def set_volume(self, vol: float) -> None:
        self.volume = max(0.0, min(1.0, float(vol)))

    def get_volume(self) -> float:
        return self.volume

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def is_enabled(self) -> bool:
        return self.enabled

    # ── internals ──────────────────────────────────────────────────────────
    def _mixer_ready(self) -> bool:
        try:
            import pygame
            return bool(pygame.mixer.get_init())
        except Exception:
            return False

    def _wav_path(self, clean_name: str) -> Optional[str]:
        direct = os.path.join(self.sounds_dir, f"{clean_name}.wav")
        if os.path.exists(direct):
            return direct
        gui_sounds = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds", f"{clean_name}.wav")
        if os.path.exists(gui_sounds):
            return gui_sounds
        legacy = os.path.join(self.plugin_sounds_dir, f"{clean_name}.mp3")
        if os.path.exists(legacy):
            return legacy
        return None

    def _ensure_cached(self, clean_name: str):
        """Returns a cached pygame Sound, loading once. Never inits the mixer."""
        cached = self._cache.get(clean_name)
        if cached is not None:
            return cached
        if not self._mixer_ready():
            return None
        path = self._wav_path(clean_name)
        if path is None:
            return None
        try:
            import pygame
            sound = pygame.mixer.Sound(path)
            with self._lock:
                self._cache[clean_name] = sound
            return sound
        except Exception as e:
            logger.debug(f"[JARVIS_SOUND] preload failed name={clean_name}: {e}")
            return None

    def _prune_events(self, now: float) -> None:
        try:
            stale = [k for k, ts in self._seen_events.items()
                     if now - ts > EVENT_MEMORY_SEC]
            for k in stale:
                del self._seen_events[k]
        except Exception:
            pass

    # ── public API ─────────────────────────────────────────────────────────
    def play(self, sound_name: str, volume: Optional[float] = None,
             reason: str = "", event_id: str = "",
             cooldown_ms: Optional[int] = None) -> bool:
        """Plays a named cue non-blockingly. Returns True iff sound was emitted.

        Filters (in order): headless/disabled → exact-duplicate event →
        per-name cooldown → zero volume → missing asset. Every decision is
        logged at debug level in the [JARVIS_SOUND] format.
        """
        clean_name = str(sound_name).lower().strip().replace(".mp3", "").replace(".wav", "")
        reason = str(reason or "")
        now = time.monotonic()

        if not self.enabled:
            logger.debug(f"[JARVIS_SOUND] SUPPRESSED name={clean_name} reason=disabled")
            return False

        if self._is_headless and not self.record_all_plays_for_test:
            logger.debug(f"[JARVIS_SOUND] SUPPRESSED name={clean_name} reason=headless")
            return False

        with self._lock:
            self._prune_events(now)
            if event_id:
                key = (clean_name, str(event_id))
                if key in self._seen_events:
                    logger.debug(f"[JARVIS_SOUND] SUPPRESSED name={clean_name} reason=duplicate_event")
                    return False
            window = float(cooldown_ms) / 1000.0 if cooldown_ms is not None else DEFAULT_COOLDOWN_MS / 1000.0
            last = self._last_play.get(clean_name, 0.0)
            if now - last < window:
                logger.debug(f"[JARVIS_SOUND] SUPPRESSED name={clean_name} reason=cooldown")
                return False

        vol = self.volume if volume is None else max(0.0, min(1.0, float(volume)))
        if vol <= 0.0:
            logger.debug(f"[JARVIS_SOUND] SUPPRESSED name={clean_name} reason=volume_zero")
            return False

        wav_path = self._wav_path(clean_name)
        if clean_name not in SOUND_NAMES and wav_path is None:
            logger.debug(f"[JARVIS_SOUND] SUPPRESSED name={clean_name} reason=missing_asset")
            return False

        if self.record_all_plays_for_test:
            self._mark_played(clean_name, event_id, now, reason)
            return True

        # 1. Primary: preloaded/cached pygame mixer (overlap-safe channels).
        sound = self._ensure_cached(clean_name)
        if sound is not None:
            try:
                sound.set_volume(vol)
                sound.play()
                self._mark_played(clean_name, event_id, now, reason)
                return True
            except Exception as e:
                logger.debug(f"[JARVIS_SOUND] mixer play failed name={clean_name}: {e}")

        # 2. Fallback: native Windows async playback (no volume control, single
        #    channel). Never touches capture paths, never blocks the GUI thread.
        wav_path = self._wav_path(clean_name)
        if wav_path is not None and sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                self._mark_played(clean_name, event_id, now, reason)
                return True
            except Exception as e:
                logger.debug(f"[JARVIS_SOUND] winsound failed name={clean_name}: {e}")

        # 3. Missing/corrupt asset: stay silent, never crash, never beep.
        if wav_path is None:
            logger.debug(f"[JARVIS_SOUND] SUPPRESSED name={clean_name} reason=missing_asset")
        else:
            logger.debug(f"[JARVIS_SOUND] SUPPRESSED name={clean_name} reason=playback_error")
        return False

    def _mark_played(self, clean_name: str, event_id: str, now: float, reason: str) -> None:
        with self._lock:
            self._last_play[clean_name] = now
            if event_id:
                self._seen_events[(clean_name, str(event_id))] = now
            self.last_played_sound = clean_name
            self.played_history.append((clean_name, reason, now))
        logger.debug(f"[JARVIS_SOUND] PLAY name={clean_name} reason={reason}")


# Global singleton facade
Sound = JarvisSoundEngine.instance()
CoucouSoundEngine = JarvisSoundEngine  # Backward-compatible alias
