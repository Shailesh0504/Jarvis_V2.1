# gui/island/controller.py
"""Geometry, Animation, Multi-Monitor and Proximity Controller for JARVIS Island.

Features:
- Top-center screen anchoring across multiple monitors and display DPI scaling
- Proximity detection: wakes to IDLE_PEEK when mouse approaches top-center edge
- Smooth spring-like animated geometry transitions (HIDDEN -> PEEK -> COMPACT -> EXPANDED)
- Auto-collapse timer on completion/inactivity
- Non-intrusive: does not steal window focus during passive states
"""

import time
from typing import Optional, Tuple
from PySide6.QtCore import (
    QEasingCurve, QObject, QPoint, QPropertyAnimation, QRect, QTimer, Qt, Signal
)
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

from .state_machine import IslandState, IslandStateMachine


class IslandController(QObject):
    """Centralized Controller and State Orchestrator for JARVIS Island.

    Maintains independent states:
    1. micEnabled (bool): Microphone capture, VAD, and wake-word pipeline active
    2. speakerEnabled (bool): Independent TTS speech output state
    3. activeView (str): Currently displayed island card ("overview", "chat", "settings", etc.)
    4. islandVisible (bool): Whether island is displayed or hidden to top edge
    5. islandExpanded (bool): Whether island is expanded or compact
    6. audioState (str): "idle", "capturing", "muted"
    7. sttState (str): "idle", "listening", "transcribing", "muted"
    8. ttsState (str): "idle", "speaking", "muted"
    9. characterState (str): "idle", "listening", "thinking", "speaking", "working", "success", "error", "love"
    """

    geometry_updated = Signal(QRect)
    proximity_triggered = Signal(str)  # "peek", "compact", "leave"

    # State synchronization signals
    mic_changed = Signal(bool)
    speaker_changed = Signal(bool)
    active_view_changed = Signal(str)
    visibility_changed = Signal(bool)
    expanded_changed = Signal(bool)
    audio_state_changed = Signal(str)
    stt_state_changed = Signal(str)
    tts_state_changed = Signal(str)
    character_state_changed = Signal(str)

    # Canonical dimension presets (width, height)
    SIZE_PRESETS = {
        IslandState.IDLE_HIDDEN: (140, 4),
        IslandState.IDLE_PEEK: (180, 16),
        IslandState.COMPACT: (350, 46),
        IslandState.EXPANDED: (740, 470),
        IslandState.CHAT: (740, 470),
        IslandState.WAITING_USER: (740, 220),
        IslandState.FILE_CONTEXT: (740, 280),
        IslandState.SETTINGS: (760, 520),
        IslandState.LISTENING: (380, 50),
        IslandState.THINKING: (380, 50),
        IslandState.EXECUTING: (420, 50),
        IslandState.SUCCESS: (350, 46),
        IslandState.WARNING: (380, 50),
        IslandState.ERROR: (420, 50),
        IslandState.PAUSED: (340, 46),
    }

    def __init__(self, target_widget: QWidget, fsm: IslandStateMachine, parent=None):
        super().__init__(parent)
        self.widget = target_widget
        self.fsm = fsm
        self.auto_collapse_delay_sec = 4.0
        self._last_active_time = time.time()
        self._anim = None

        # ── 9 Independent States ─────────────────────────────────────────────
        self.micEnabled: bool = True
        self.speakerEnabled: bool = True
        self.activeView: str = "overview"
        self.previousView: Optional[str] = None
        self.islandVisible: bool = True
        self.islandExpanded: bool = False
        self.audioState: str = "idle"
        self.sttState: str = "idle"
        self.ttsState: str = "idle"
        self.characterState: str = "idle"

        # Listen to FSM state updates
        self.fsm.add_listener(self._on_state_transition)

        # Proximity polling timer (40ms tick = 25 Hz, very lightweight)
        self._proximity_timer = QTimer(self)
        self._proximity_timer.timeout.connect(self._check_cursor_proximity)
        self._proximity_timer.start(40)

        # Inactivity auto-collapse timer (checked every 500ms)
        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._check_idle_timeout)
        self._idle_timer.start(500)

    # ── Centralized Control Methods ──────────────────────────────────────────
    def set_mic_enabled(self, enabled: bool) -> None:
        """Sets microphone capture state and synchronizes audio/stt states."""
        if self.micEnabled != enabled:
            self.micEnabled = enabled
            self.audioState = "capturing" if enabled else "muted"
            self.sttState = "idle" if enabled else "muted"
            self.mic_changed.emit(enabled)
            self.audio_state_changed.emit(self.audioState)
            self.stt_state_changed.emit(self.sttState)

    def toggle_mic(self) -> bool:
        """Toggles microphone capture state; returns new state."""
        self.set_mic_enabled(not self.micEnabled)
        return self.micEnabled

    def set_speaker_enabled(self, enabled: bool) -> None:
        """Sets TTS speaker state and synchronizes ttsState."""
        if self.speakerEnabled != enabled:
            self.speakerEnabled = enabled
            self.ttsState = "idle" if enabled else "muted"
            self.speaker_changed.emit(enabled)
            self.tts_state_changed.emit(self.ttsState)

    def toggle_speaker(self) -> bool:
        """Toggles TTS speaker state; returns new state."""
        self.set_speaker_enabled(not self.speakerEnabled)
        return self.speakerEnabled

    def set_active_view(self, view_name: str) -> None:
        """Switches active view and keeps track of history."""
        if self.activeView != view_name:
            if view_name != "settings":
                self.previousView = self.activeView
            self.activeView = view_name
            self.active_view_changed.emit(view_name)

    def open_settings(self) -> None:
        """Opens Settings view without replacing or terminating the JARVIS process."""
        self.previousView = self.activeView
        self.activeView = "settings"
        self.islandExpanded = True
        self.active_view_changed.emit("settings")
        self.expanded_changed.emit(True)

    def close_settings(self) -> str:
        """Returns to previous active view. NEVER terminates the JARVIS process."""
        target_view = self.previousView or "overview"
        self.activeView = target_view
        self.active_view_changed.emit(target_view)
        return target_view

    def set_island_visible(self, visible: bool) -> None:
        """Sets island visibility state."""
        if self.islandVisible != visible:
            self.islandVisible = visible
            self.visibility_changed.emit(visible)

    def toggle_island_visible(self) -> bool:
        """Toggles island visibility; returns new state."""
        self.set_island_visible(not self.islandVisible)
        return self.islandVisible

    def set_island_expanded(self, expanded: bool) -> None:
        """Sets island expansion state."""
        if self.islandExpanded != expanded:
            self.islandExpanded = expanded
            self.expanded_changed.emit(expanded)

    def collapse_island(self) -> None:
        """Collapses expanded island to compact state."""
        self.islandExpanded = False
        self.expanded_changed.emit(False)

    def hide_island(self) -> None:
        """Smoothly hides Dynamic Island to top-edge; keeps backend/voice alive."""
        self.islandVisible = False
        self.islandExpanded = False
        self.visibility_changed.emit(False)
        self.expanded_changed.emit(False)

    def set_audio_state(self, state: str) -> None:
        if self.audioState != state:
            self.audioState = state
            self.audio_state_changed.emit(state)

    def set_stt_state(self, state: str) -> None:
        if self.sttState != state:
            self.sttState = state
            self.stt_state_changed.emit(state)

    def set_tts_state(self, state: str) -> None:
        if self.ttsState != state:
            self.ttsState = state
            self.tts_state_changed.emit(state)

    def set_character_state(self, state: str) -> None:
        if self.characterState != state:
            self.characterState = state
            self.character_state_changed.emit(state)

    def stop(self) -> None:
        """Stops all active polling and collapse timers cleanly."""
        if hasattr(self, "_proximity_timer") and self._proximity_timer:
            self._proximity_timer.stop()
        if hasattr(self, "_idle_timer") and self._idle_timer:
            self._idle_timer.stop()
        if hasattr(self, "_anim") and self._anim:
            try:
                self._anim.stop()
            except Exception:
                pass
        self.fsm.remove_listener(self._on_state_transition)

    def get_active_screen(self):
        """Returns the QScreen where the cursor is currently active."""
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos)
        if not screen:
            screen = QGuiApplication.primaryScreen()
        return screen

    def calculate_geometry(self, state: IslandState) -> QRect:
        """Calculates centered top-edge geometry for target state on the active monitor."""
        screen = self.get_active_screen()
        if not screen:
            return QRect(0, 0, 350, 46)

        geo = screen.availableGeometry()
        w, h = self.SIZE_PRESETS.get(state, (350, 46))

        # Horizontal centering at top edge
        x = geo.x() + (geo.width() - w) // 2
        # Y position: 0 for hidden/peek, slight offset for compact/expanded
        y = geo.y() if state in (IslandState.IDLE_HIDDEN, IslandState.IDLE_PEEK) else geo.y() + 6

        return QRect(x, y, w, h)

    def animate_to_state(self, state: IslandState, duration_ms: int = 240) -> None:
        """Performs smooth spring-like geometry animation to target state."""
        # For top-edge floating canvas (720x320 JarvisMainWindow), the window canvas
        # stays anchored at the top-center edge while the internal CoucouIslandWidget
        # spring physics engine morphs the pitch-black capsule.
        if self.widget.maximumSize().width() == 720 and self.widget.maximumSize().height() == 320:
            return

        target_geo = self.calculate_geometry(state)
        current_geo = self.widget.geometry()

        if target_geo == current_geo:
            return

        if self._anim and self._anim.state() == QPropertyAnimation.Running:
            self._anim.stop()

        self._anim = QPropertyAnimation(self.widget, b"geometry", self)
        self._anim.setDuration(duration_ms)
        # OutCubic / OutQuad provides natural spring-like easing without jitter
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.setStartValue(current_geo)
        self._anim.setEndValue(target_geo)
        self._anim.start()

    def touch_activity(self) -> None:
        """Resets the inactivity auto-collapse timer."""
        self._last_active_time = time.time()

    def _on_state_transition(self, old_state: IslandState, new_state: IslandState) -> None:
        self.touch_activity()
        self.animate_to_state(new_state)

    def _check_cursor_proximity(self) -> None:
        """Detects cursor approach towards screen top-center edge (notch hover)."""
        screen = self.get_active_screen()
        if not screen:
            return

        geo = screen.availableGeometry()
        cursor_pos = QCursor.pos()
        center_x = geo.x() + geo.width() // 2

        # Notch hover zone at the top edge of Windows screen:
        # Cursor within top 18px of monitor, and within +/- 140px of screen center
        is_at_notch_edge = (geo.y() <= cursor_pos.y() <= geo.y() + 18)
        is_within_notch_h = abs(cursor_pos.x() - center_x) <= 140

        current = self.fsm.current_state

        if current == IslandState.IDLE_HIDDEN:
            if is_at_notch_edge and is_within_notch_h:
                self.touch_activity()
                self.fsm.transition_to(IslandState.IDLE_PEEK, reason="notch_hover")
                self.proximity_triggered.emit("peek")
        elif current == IslandState.IDLE_PEEK:
            # When peeking:
            # If cursor moves down into the peeking notch (y between 18 and 50) and still centered:
            if abs(cursor_pos.x() - center_x) <= 160:
                if geo.y() + 18 < cursor_pos.y() <= geo.y() + 50:
                    self.touch_activity()
                    self.fsm.transition_to(IslandState.COMPACT, reason="notch_enter")
                    self.proximity_triggered.emit("compact")
                elif cursor_pos.y() <= geo.y() + 18:
                    # Cursor is still hovering the notch, maintain peek state
                    self.touch_activity()
                else:
                    # Cursor moved further down away from notch
                    self.fsm.transition_to(IslandState.IDLE_HIDDEN, reason="notch_leave")
                    self.proximity_triggered.emit("leave")
            else:
                # Cursor moved horizontally away from center notch
                self.fsm.transition_to(IslandState.IDLE_HIDDEN, reason="notch_leave")
                self.proximity_triggered.emit("leave")

    def _check_idle_timeout(self) -> None:
        """Auto-collapses completed or idle tasks back into top-edge hidden state when nothing is running."""
        now = time.time()
        elapsed = now - self._last_active_time
        current = self.fsm.current_state

        # ACTIVE CHAT INVARIANT: If activeView is chat or prompt, NEVER auto-collapse!
        if getattr(self, "activeView", "") in ("chat", "prompt"):
            self.touch_activity()
            return

        # Don't auto-collapse if user is actively hovering or interacting with expanded widget
        if self.widget.underMouse():
            self.touch_activity()
            return

        # Don't auto-collapse if something is running!
        # (active speech output, voice listening/transcribing, or active task execution)
        if self.ttsState == "speaking" or self.sttState in ("listening", "transcribing"):
            self.touch_activity()
            return
        if current in (
            IslandState.LISTENING, IslandState.THINKING, IslandState.SPEAKING,
            IslandState.WORKING, IslandState.EXECUTING, IslandState.PROCESSING
        ):
            self.touch_activity()
            return

        # When nothing is running:
        # 1. Auto-collapse SUCCESS or ERROR back to COMPACT after brief acknowledgment
        if current in (IslandState.SUCCESS, IslandState.ERROR):
            if elapsed >= 1.6:
                self.fsm.transition_to(IslandState.COMPACT, reason="success_complete")
        # 2. When in COMPACT with nothing running, automatically hide away into the top edge!
        elif current == IslandState.COMPACT:
            if elapsed >= self.auto_collapse_delay_sec:
                self.fsm.transition_to(IslandState.IDLE_HIDDEN, reason="nothing_running_hide_away")
        # 3. When in EXPANDED overview with nothing running, collapse to compact first
        elif current == IslandState.EXPANDED:
            if elapsed >= self.auto_collapse_delay_sec * 2.0:
                self.fsm.transition_to(IslandState.COMPACT, reason="expanded_idle_collapse")
        # 4. When in IDLE_PEEK and user moved away or timeout passed
        elif current == IslandState.IDLE_PEEK:
            if elapsed >= 2.5:
                self.fsm.transition_to(IslandState.IDLE_HIDDEN, reason="peek_idle_timeout")
