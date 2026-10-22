# gui/island/visibility_manager.py
"""Coucou-Style 3-Stage Visibility System for JARVIS GUI.

Implements the 3 primary visibility stages:
EXPANDED <-> COMPACT <-> HIDDEN

1. EXPANDED / ACTIVE STATE:
   - When mouse leaves the GUI, starts auto-close timer (default 15s).
   - If mouse returns within 15s, cancels timer immediately.
   - If user interacts / clicks / types, resets timer.
2. EXPANDED -> COMPACT:
   - After 15s mouse-out, smoothly collapses expanded GUI into compact island.
   - Visual identity / avatar and microphone indicator remain clearly visible.
3. COMPACT STATE:
   - When mouse is outside compact island, starts 60s hide timer.
   - If mouse enters compact island, cancels 60s timer.
   - Clicking compact island immediately expands to EXPANDED state.
   - Background listening / wake-word detection continues normally.
4. COMPACT -> HIDDEN:
   - After 60s mouse-out on compact island, transitions to HIDDEN state.
   - Backend service, wake-word detection, microphone logic remain alive.
5. HIDDEN WAKE STRIP:
   - Top-center ~240x6 px wake strip.
   - High-frequency GUI polling is parked to save CPU.
   - Mouse entering wake strip triggers HIDDEN -> COMPACT with subtle sound.
6. PINNED / IMPORTANT UI EXCEPTION:
   - Confirmation, permission, active task, critical notification,
     user input required, active conversation, typing -> blocks auto-close.
7. ACTIVITY RESET:
   - Resets auto-close lifecycle on mouse move, click, mic, typing, speech, task.
"""

import logging
from typing import Optional
from PySide6.QtCore import QObject, QTimer, Signal

from .state_machine import GuiVisibilityState
from ..sound_effects import Sound

logger = logging.getLogger("jarvis.gui.visibility")


def _log_gui(msg: str):
    """Outputs standardized log message for JARVIS GUI state tracking."""
    logger.info(msg)
    print(msg, flush=True)


class CoucouVisibilityManager(QObject):
    """Authoritative state machine orchestrating the Coucou 3-stage visibility lifecycle."""

    state_changed = Signal(str, str)  # (old_state_str, new_state_str)
    auto_close_started = Signal(int)
    auto_close_cancelled = Signal(str)
    compact_hide_started = Signal(int)
    compact_hide_cancelled = Signal()
    wake_strip_triggered = Signal()
    activity_reset = Signal()

    def __init__(
        self,
        island_widget,
        expanded_timeout_s: float = 15.0,
        compact_timeout_s: float = 60.0,
        parent=None
    ):
        super().__init__(parent)
        self.widget = island_widget
        self._state: GuiVisibilityState = GuiVisibilityState.COMPACT
        self.expanded_timeout_s: float = float(expanded_timeout_s)
        self.compact_timeout_s: float = float(compact_timeout_s)
        self._is_mouse_inside: bool = False
        self._manual_pinned: bool = False

        # Independent cancellable timers
        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self._on_auto_close_timeout)

        self._compact_hide_timer = QTimer(self)
        self._compact_hide_timer.setSingleShot(True)
        self._compact_hide_timer.timeout.connect(self._on_compact_hide_timeout)

    @property
    def state(self) -> GuiVisibilityState:
        return self._state

    @property
    def is_mouse_inside(self) -> bool:
        return self._is_mouse_inside

    def configure(self, expanded_timeout_s: Optional[float] = None, compact_timeout_s: Optional[float] = None):
        """Updates timeout configurations."""
        if expanded_timeout_s is not None:
            self.expanded_timeout_s = max(1.0, float(expanded_timeout_s))
            if self._state == GuiVisibilityState.EXPANDED and self._auto_close_timer.isActive():
                self._auto_close_timer.start(int(self.expanded_timeout_s * 1000))
        if compact_timeout_s is not None:
            self.compact_timeout_s = max(1.0, float(compact_timeout_s))
            if self._state == GuiVisibilityState.COMPACT and self._compact_hide_timer.isActive():
                self._compact_hide_timer.start(int(self.compact_timeout_s * 1000))

    def set_pinned(self, pinned: bool):
        """Sets manual pin lock."""
        self._manual_pinned = bool(pinned)
        if self._manual_pinned:
            if self._auto_close_timer.isActive():
                self._auto_close_timer.stop()
                _log_gui("[JARVIS_GUI] PINNED_AUTO_HIDE_BLOCKED")
            if self._compact_hide_timer.isActive():
                self._compact_hide_timer.stop()
                _log_gui("[JARVIS_GUI] PINNED_AUTO_HIDE_BLOCKED")

    def is_pinned_or_important(self) -> bool:
        """Determines if the GUI is showing an interactive/important state that blocks auto-collapse."""
        if self._manual_pinned:
            return True

        if not self.widget:
            return False

        # 1. Greeting ceremony active
        if getattr(self.widget, "_is_greeting_active", False):
            return True

        # 2. Explicit locked view (e.g. Chat)
        if getattr(self.widget, "_locked_view", None) == "chat":
            return True

        # 3. Active card view checks (approval, question, chat, prompt, settings)
        current_view = getattr(self.widget, "_current_view", "")
        if current_view in ("approval", "question", "chat", "prompt", "settings", "greeting"):
            return True

        # 4. Input field interaction (focus or typed non-empty text)
        if hasattr(self.widget, "view_chat") and hasattr(self.widget.view_chat, "input_field"):
            inp = self.widget.view_chat.input_field
            if inp.hasFocus() or bool(inp.text().strip()):
                return True

        # 5. FSM states indicating active background work or user interaction
        if hasattr(self.widget, "fsm") and self.widget.fsm:
            st = self.widget.fsm.current_state.value.lower()
            if any(k in st for k in (
                "waiting", "approval", "question", "listening",
                "thinking", "speaking", "working", "executing", "processing"
            )):
                return True

        # 6. Character state indicating active processing or listening
        if hasattr(self.widget, "character") and self.widget.character:
            cst = getattr(self.widget.character, "_current_state", "")
            if cst in ("listening", "thinking", "speaking", "working", "executing"):
                return True

        # 7. Parent window active worker or TTS speaking
        parent = self.widget.parent()
        if parent:
            if getattr(parent, "_active_worker", None) and parent._active_worker.isRunning():
                return True
            if getattr(parent, "tts_manager", None) and hasattr(parent.tts_manager, "is_speaking"):
                if parent.tts_manager.is_speaking():
                    return True

        return False

    def transition_to(self, new_state: GuiVisibilityState, reason: str = "") -> bool:
        """Explicit state transition with timer safety and logging."""
        if new_state == self._state:
            return False

        # Block collapsing/hiding if pinned/important
        if new_state in (GuiVisibilityState.COMPACT, GuiVisibilityState.HIDDEN):
            if self._state == GuiVisibilityState.EXPANDED and self.is_pinned_or_important():
                _log_gui("[JARVIS_GUI] PINNED_AUTO_HIDE_BLOCKED")
                return False

        old_state = self._state
        self._state = new_state

        # Log new state transition
        _log_gui(f"[JARVIS_GUI] STATE={new_state.value}")

        # Update widget mode & manage timers for new state
        if new_state == GuiVisibilityState.EXPANDED:
            self._compact_hide_timer.stop()
            if self.widget and hasattr(self.widget, "set_mode"):
                self.widget.set_mode("expanded", is_closing=False)
            if not self._is_mouse_inside and not self.is_pinned_or_important():
                self._start_auto_close_timer()
            else:
                self._auto_close_timer.stop()

        elif new_state == GuiVisibilityState.COMPACT:
            self._auto_close_timer.stop()
            if self.widget and hasattr(self.widget, "set_mode"):
                self.widget.set_mode("compact", is_closing=(old_state == GuiVisibilityState.EXPANDED))
            if not self._is_mouse_inside:
                self._start_compact_hide_timer()

        elif new_state == GuiVisibilityState.HIDDEN:
            self._auto_close_timer.stop()
            self._compact_hide_timer.stop()
            if self.widget and hasattr(self.widget, "set_mode"):
                self.widget.set_mode("hidden", is_closing=True)
            _log_gui("[JARVIS_GUI] WAKE_STRIP_ACTIVE")

        self.state_changed.emit(old_state.value, new_state.value)
        return True

    def on_mouse_enter(self):
        """Handler for mouse entering the GUI / island."""
        self._is_mouse_inside = True

        if self._state == GuiVisibilityState.HIDDEN:
            _log_gui("[JARVIS_GUI] WAKE_STRIP_TRIGGERED")
            Sound.play("peek")
            self.transition_to(GuiVisibilityState.COMPACT, reason="wake_strip")
            return

        if self._state == GuiVisibilityState.COMPACT:
            if self._compact_hide_timer.isActive():
                self._compact_hide_timer.stop()
                _log_gui("[JARVIS_GUI] COMPACT_HIDE_TIMER_CANCELLED")
                self.compact_hide_cancelled.emit()

        elif self._state == GuiVisibilityState.EXPANDED:
            if self._auto_close_timer.isActive():
                self._auto_close_timer.stop()
                _log_gui("[JARVIS_GUI] AUTO_CLOSE_CANCELLED reason=mouse_enter")
                self.auto_close_cancelled.emit("mouse_enter")

        _log_gui("[JARVIS_GUI] ACTIVITY_TIMER_RESET")
        self.activity_reset.emit()

    def on_mouse_leave(self):
        """Handler for mouse leaving the GUI / island."""
        self._is_mouse_inside = False

        if self._state == GuiVisibilityState.EXPANDED:
            if self.is_pinned_or_important():
                _log_gui("[JARVIS_GUI] PINNED_AUTO_HIDE_BLOCKED")
            else:
                self._start_auto_close_timer()

        elif self._state == GuiVisibilityState.COMPACT:
            self._start_compact_hide_timer()

    def on_mouse_click(self):
        """Handler for click / interaction on the island."""
        _log_gui("[JARVIS_GUI] ACTIVITY_TIMER_RESET")
        self.activity_reset.emit()

        if self._state == GuiVisibilityState.HIDDEN:
            _log_gui("[JARVIS_GUI] WAKE_STRIP_TRIGGERED")
            Sound.play("peek")
            self.transition_to(GuiVisibilityState.COMPACT, reason="wake_strip_click")
        elif self._state == GuiVisibilityState.COMPACT:
            if self._compact_hide_timer.isActive():
                self._compact_hide_timer.stop()
                _log_gui("[JARVIS_GUI] COMPACT_HIDE_TIMER_CANCELLED")
                self.compact_hide_cancelled.emit()
            self.transition_to(GuiVisibilityState.EXPANDED, reason="compact_click")
        elif self._state == GuiVisibilityState.EXPANDED:
            if self._auto_close_timer.isActive():
                self._auto_close_timer.stop()
                _log_gui("[JARVIS_GUI] AUTO_CLOSE_CANCELLED reason=click")
                self.auto_close_cancelled.emit("click")

    def notify_activity(self, reason: str = "activity"):
        """Notifies the manager of user activity (typing, voice, task, state change)."""
        _log_gui("[JARVIS_GUI] ACTIVITY_TIMER_RESET")
        self.activity_reset.emit()

        if self._state == GuiVisibilityState.EXPANDED:
            if self._is_mouse_inside or self.is_pinned_or_important():
                if self._auto_close_timer.isActive():
                    self._auto_close_timer.stop()
                    _log_gui(f"[JARVIS_GUI] AUTO_CLOSE_CANCELLED reason={reason}")
                    self.auto_close_cancelled.emit(reason)
            else:
                # User interacted while mouse is outside: restart 15s timer
                self._start_auto_close_timer()

        elif self._state == GuiVisibilityState.COMPACT:
            if not self._is_mouse_inside:
                self._start_compact_hide_timer()

    def _start_auto_close_timer(self):
        """Starts or resets the 15-second expanded auto-close timer."""
        self._auto_close_timer.stop()
        sec = int(self.expanded_timeout_s)
        self._auto_close_timer.start(int(self.expanded_timeout_s * 1000))
        _log_gui(f"[JARVIS_GUI] AUTO_CLOSE_STARTED seconds={sec}")
        self.auto_close_started.emit(sec)

    def _start_compact_hide_timer(self):
        """Starts or resets the 60-second compact hide timer."""
        self._compact_hide_timer.stop()
        sec = int(self.compact_timeout_s)
        self._compact_hide_timer.start(int(self.compact_timeout_s * 1000))
        _log_gui(f"[JARVIS_GUI] COMPACT_HIDE_TIMER_STARTED seconds={sec}")
        self.compact_hide_started.emit(sec)

    def _on_auto_close_timeout(self):
        """Auto-close timer fired: EXPANDED -> COMPACT."""
        if self._state != GuiVisibilityState.EXPANDED:
            return

        if self.is_pinned_or_important():
            _log_gui("[JARVIS_GUI] PINNED_AUTO_HIDE_BLOCKED")
            return

        if self.widget and hasattr(self.widget, "collapse_to_compact"):
            self.widget.collapse_to_compact()
        else:
            self.transition_to(GuiVisibilityState.COMPACT, reason="auto_close_timeout")

    def _on_compact_hide_timeout(self):
        """Compact hide timer fired: COMPACT -> HIDDEN."""
        if self._state != GuiVisibilityState.COMPACT:
            return

        if self.is_pinned_or_important():
            _log_gui("[JARVIS_GUI] PINNED_AUTO_HIDE_BLOCKED")
            return

        self.transition_to(GuiVisibilityState.HIDDEN, reason="compact_hide_timeout")

    def stop(self):
        """Stops all timers cleanly."""
        self._auto_close_timer.stop()
        self._compact_hide_timer.stop()
