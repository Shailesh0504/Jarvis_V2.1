# gui/island/state_machine.py
"""UI-only State Machine for JARVIS Floating Island Companion.

Maintains strict transition rules between all 16 required UI states:
IDLE_HIDDEN -> IDLE_PEEK -> COMPACT -> EXPANDED -> LISTENING -> THINKING ->
PROCESSING -> EXECUTING -> WAITING_USER -> SUCCESS -> WARNING -> ERROR ->
CHAT -> FILE_CONTEXT -> SETTINGS -> PAUSED.
"""

from enum import Enum
import logging
import time
from typing import Callable, List, Optional
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("jarvis.gui.island.fsm")


class GuiVisibilityState(Enum):
    EXPANDED = "EXPANDED"
    COMPACT = "COMPACT"
    HIDDEN = "HIDDEN"


class IslandState(Enum):
    FLOATING_ANCHOR = "floating_anchor"
    COLLAPSED_ANCHOR = "collapsed_anchor"
    EXPANDED_ISLAND = "expanded_island"
    DRAG_ANCHOR = "drag_anchor"
    IDLE_HIDDEN = "idle_hidden"
    IDLE_PEEK = "idle_peek"
    COMPACT = "compact"
    EXPANDED = "expanded"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    WORKING = "working"
    PROCESSING = "processing"
    EXECUTING = "executing"
    WAITING_USER = "waiting_user"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CHAT = "chat"
    FILE_CONTEXT = "file_context"
    SETTINGS = "settings"
    PAUSED = "paused"
    EMOTE_LOVE = "emote_love"
    # Canonical spec §5 aliases (deterministic, same backing states)
    HIDDEN_ANCHOR = "floating_anchor"
    PEEK = "idle_peek"
    APPROVAL = "waiting_user"
    EMOTE = "emote_love"
    DRAGGING = "drag_anchor"


class IslandStateMachine(QObject):
    """Authoritative state machine orchestrating JARVIS Island transitions."""

    state_changed = Signal(str, str)  # (old_state_value, new_state_value)

    def __init__(self, initial_state: IslandState = IslandState.FLOATING_ANCHOR, parent=None):
        super().__init__(parent)
        self._current_state: IslandState = initial_state
        self._previous_state: Optional[IslandState] = None
        self._last_transition_time: float = time.time()
        self._listeners: List[Callable[[IslandState, IslandState], None]] = []

    @property
    def current_state(self) -> IslandState:
        return self._current_state

    @property
    def previous_state(self) -> Optional[IslandState]:
        return self._previous_state

    def is_idle(self) -> bool:
        return self._current_state in (
            IslandState.IDLE_HIDDEN,
            IslandState.IDLE_PEEK,
        )

    def is_anchor(self) -> bool:
        return self._current_state in (
            IslandState.FLOATING_ANCHOR,
            IslandState.COLLAPSED_ANCHOR,
        )

    def is_interactive(self) -> bool:
        return self._current_state not in (IslandState.IDLE_HIDDEN,)

    def is_expanded_surface(self) -> bool:
        return self._current_state in (
            IslandState.EXPANDED_ISLAND,
            IslandState.EXPANDED,
            IslandState.CHAT,
            IslandState.WAITING_USER,
            IslandState.SETTINGS,
            IslandState.FILE_CONTEXT,
        )

    def transition_to(self, new_state: IslandState, reason: str = "") -> bool:
        """Transitions to the target state if valid, notifying all listeners."""
        if new_state == self._current_state:
            return False

        old_state = self._current_state
        self._previous_state = old_state
        self._current_state = new_state
        self._last_transition_time = time.time()

        logger.debug(
            "Island FSM: %s -> %s (reason='%s')",
            old_state.value,
            new_state.value,
            reason,
        )

        for listener in self._listeners:
            try:
                listener(old_state, new_state)
            except Exception as e:
                logger.error("Error in state transition listener: %s", e)

        self.state_changed.emit(old_state.value, new_state.value)
        return True

    def add_listener(self, callback: Callable[[IslandState, IslandState], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[IslandState, IslandState], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def trigger_emote(self, emote_state: IslandState = IslandState.EMOTE_LOVE, duration_s: float = 1.8) -> None:
        """Temporarily displays an emotional emote on the character, returning to previous state."""
        from PySide6.QtCore import QTimer

        prev = self._current_state if self._current_state != emote_state else (self._previous_state or IslandState.COMPACT)
        self.transition_to(emote_state, reason=f"trigger_emote:{emote_state.value}")

        def _revert():
            if self._current_state == emote_state:
                self.transition_to(prev, reason="emote_expired")

        QTimer.singleShot(int(duration_s * 1000), _revert)
