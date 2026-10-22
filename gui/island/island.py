# gui/island/island.py
"""Coucou Dynamic Island Widget — High-fidelity replication of island.ts & layout.ts.

Replicates Coucou's top-edge Dynamic Island:
- Horizontally centered pitch-black capsule (#0b0c0e) attached to desktop top edge (y=0)
- Fixed 720x320 panel canvas; island capsule morphs via sub-stepped Spring physics
- Hidden (w=184, h=0, wake-strip 240x6)
- Compact pill (w=288, h=32, corner_radius=14) with embedded companion bot & 2x2 mini-grid
- Expanded card (w=640, h=160..240, corner_radius=22) with Coucou tabbed header & card views
- Full drag-and-drop file ingestion
- Auto-collapse timer with hover awareness
"""

import os
import time
import logging
from typing import Optional
from PySide6.QtCore import Qt, QPoint, QRect, QRectF, QTimer, Signal
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush,
    QMouseEvent, QDragEnterEvent, QDropEvent,
    QKeySequence, QShortcut
)
from PySide6.QtWidgets import (
    QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton
)

from .animator import IslandPhysicsAnimator
from .character import JarvisCharacter
from .icons import create_coucou_icon
from .state_machine import IslandState, IslandStateMachine, GuiVisibilityState
from .visibility_manager import CoucouVisibilityManager
from .views import (
    CoucouHeaderWidget, CoucouOverviewCard, CoucouApprovalCard,
    CoucouQuestionCard, CoucouFinishedCard, CoucouErrorCard,
    CoucouChatCard, CoucouDropCard, CoucouListeningCard,
    CoucouThinkingCard, CoucouSpeakingCard, CoucouSettingsCard
)
from .greeting import GreetingCanvasWidget
from ..sound_effects import Sound

logger = logging.getLogger("jarvis.gui.island")


class CoucouMiniGrid(QWidget):
    """The 2x2 mini-bot indicator grid from Coucou compact.png (28x28)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 4 mini-bots matching Coucou compact.png:
        # Top-left: Green #22c55e
        # Top-right: Amber #f5a524
        # Bottom-left: Indigo #6366f1
        # Bottom-right: Coral #f4505e
        dots = [
            (3.0, 3.0, QColor("#22c55e")),
            (15.0, 3.0, QColor("#f5a524")),
            (3.0, 15.0, QColor("#6366f1")),
            (15.0, 15.0, QColor("#f4505e")),
        ]
        for x, y, col in dots:
            painter.setPen(Qt.NoPen)
            painter.setBrush(col)
            painter.drawRoundedRect(QRectF(x, y, 10.0, 10.0), 3.5, 3.5)
            # Two tiny dark eyes
            painter.setBrush(QColor("#000000"))
            painter.drawRect(QRectF(x + 2.5, y + 4.0, 1.5, 2.5))
            painter.drawRect(QRectF(x + 6.0, y + 4.0, 1.5, 2.5))

        painter.end()


class CoucouIslandWidget(QWidget):
    """The authentic Coucou Dynamic Island canvas widget (720x320)."""

    view_switched = Signal(str)
    collapsed = Signal()
    expanded = Signal()
    settings_requested = Signal()
    mic_toggled = Signal(bool)
    speaker_toggled = Signal(bool)
    close_requested = Signal()
    reset_position_requested = Signal()

    def __init__(self, fsm: Optional[IslandStateMachine] = None, parent=None):
        super().__init__(parent)
        self.setFixedSize(720, 320)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self.fsm = fsm or IslandStateMachine(initial_state=IslandState.COMPACT, parent=self)
        self.animator = IslandPhysicsAnimator(initial_w=288, initial_h=32)
        self._current_mode = "compact"  # "hidden", "compact", "expanded"
        self._current_view = "overview"

        # 60 FPS animation timer
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start(16)

        # Active View Lock & Launch Greeting state
        self._locked_view: Optional[str] = None
        self._is_greeting_active: bool = False

        # 3-Stage Coucou Visibility Manager (EXPANDED <-> COMPACT <-> HIDDEN)
        self.visibility_mgr = CoucouVisibilityManager(
            island_widget=self,
            expanded_timeout_s=15.0,
            compact_timeout_s=60.0,
            parent=self
        )
        self.visibility_mgr.state_changed.connect(self._on_visibility_state_changed)
        # Compatibility reference for legacy callers/tests checking _auto_collapse_timer
        self._auto_collapse_timer = self.visibility_mgr._auto_close_timer
        self._auto_collapse_delay_s = 15.0

        # Character companion bot
        self.character = JarvisCharacter(self, size=24)
        self.character.show()
        # Single-identity flag: while Mochi floats free on the desktop, the
        # island shows an empty nest (anchor capsule stays, bot hidden).
        self._mochi_loose = False

        # Register visual targets with semantic event manager
        try:
            from .semantic_events import register_visual_targets
            register_visual_targets(character=self.character, island=self, visibility_mgr=self.visibility_mgr)
        except Exception:
            pass

        # 2x2 Mini grid for compact pill
        self.mini_grid = CoucouMiniGrid(self)
        self.mini_grid.show()

        # ── Compact UI Container (Minimal companion mode) ────────────────────
        self.compact_container = QWidget(self)
        self.compact_container.setFixedHeight(32)
        self.compact_container.setAttribute(Qt.WA_TranslucentBackground, True)
        compact_layout = QHBoxLayout(self.compact_container)
        compact_layout.setContentsMargins(48, 0, 44, 0)
        compact_layout.setSpacing(6)

        self.compact_status = QLabel("JARVIS")
        self.compact_status.setStyleSheet("color: #e8eaed; font-size: 11.5px; font-weight: 600; font-family: Segoe UI, Arial;")
        compact_layout.addWidget(self.compact_status, stretch=1)

        # ── Expanded UI Container ─────────────────────────────────────────────
        self.expanded_container = QWidget(self)
        self.expanded_container.setAttribute(Qt.WA_TranslucentBackground, True)
        expanded_layout = QVBoxLayout(self.expanded_container)
        expanded_layout.setContentsMargins(0, 0, 0, 0)
        expanded_layout.setSpacing(0)

        # Coucou Header
        self.header = CoucouHeaderWidget(self.expanded_container)
        self.header.tab_changed.connect(self.set_view)
        self.header.mic_toggled.connect(self.mic_toggled.emit)
        self.header.speaker_toggled.connect(self.speaker_toggled.emit)
        self.header.settings_clicked.connect(self._toggle_settings_view)
        self.header.close_clicked.connect(self.hide_to_edge)
        expanded_layout.addWidget(self.header)

        # Card views stack
        self.view_stack = QStackedWidget(self.expanded_container)

        self.view_overview = CoucouOverviewCard()
        self.view_overview.jump_clicked.connect(self.settings_requested.emit)
        self.view_overview.chat_requested.connect(lambda: self.set_view("chat"))
        self.view_stack.addWidget(self.view_overview)       # 0: overview

        self.view_approval = CoucouApprovalCard()
        self.view_approval.decision_made.connect(self._on_approval_decision)
        self.view_stack.addWidget(self.view_approval)       # 1: approval

        self.view_question = CoucouQuestionCard()
        self.view_question.option_selected.connect(self._on_question_option)
        self.view_stack.addWidget(self.view_question)       # 2: question

        self.view_finished = CoucouFinishedCard()
        self.view_finished.dismiss_requested.connect(self.collapse_to_compact)
        self.view_stack.addWidget(self.view_finished)       # 3: finished

        self.view_error = CoucouErrorCard()
        self.view_error.retry_requested.connect(lambda: self.set_view("overview"))
        self.view_stack.addWidget(self.view_error)          # 4: error

        self.view_chat = CoucouChatCard()
        self.view_chat.message_submitted.connect(self._on_island_chat_submitted)
        self.view_stack.addWidget(self.view_chat)           # 5: chat

        self.view_drop = CoucouDropCard()
        self.view_drop.file_dropped.connect(self._handle_dropped_file)
        self.view_stack.addWidget(self.view_drop)           # 6: drop

        self.view_listening = CoucouListeningCard()
        self.view_stack.addWidget(self.view_listening)      # 7: listening

        self.view_thinking = CoucouThinkingCard()
        self.view_stack.addWidget(self.view_thinking)       # 8: thinking

        self.view_speaking = CoucouSpeakingCard()
        self.view_stack.addWidget(self.view_speaking)       # 9: speaking

        self.view_settings = CoucouSettingsCard()
        self.view_settings.open_advanced_requested.connect(self.settings_requested.emit)
        self.view_settings.done_clicked.connect(self._close_settings_view)
        self.view_settings.settings_saved.connect(self._on_settings_saved)
        self.view_settings.sound_toggled.connect(self._on_settings_speaker)
        self.view_settings.autoclose_changed.connect(lambda s: self.visibility_mgr.configure(expanded_timeout_s=float(s)))
        self.view_settings.compact_hide_changed.connect(lambda s: self.visibility_mgr.configure(compact_timeout_s=float(s)))
        self.view_settings.reset_position_requested.connect(self.reset_position_requested.emit)
        self.view_settings.mic_setting_changed.connect(self._on_settings_mic)
        self.view_settings.accessory_changed.connect(self.set_accessory)
        self.view_settings.animation_changed.connect(self.set_animation_intensity)
        self.view_stack.addWidget(self.view_settings)       # 10: settings
        try:
            self.load_settings_from_config()
        except Exception:
            pass

        self.view_greeting = GreetingCanvasWidget(self.expanded_container)
        self.view_greeting.completed.connect(self._on_greeting_completed)
        self.view_stack.addWidget(self.view_greeting)       # 11: greeting

        expanded_layout.addWidget(self.view_stack)
        self.expanded_container.hide()

        self._previous_view: Optional[str] = None

        # Global Keyboard Shortcuts
        self.sc_toggle_island = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.sc_toggle_island.activated.connect(self.toggle_island_visibility)

        self.sc_toggle_mic = QShortcut(QKeySequence("Ctrl+Shift+M"), self)
        self.sc_toggle_mic.activated.connect(self.toggle_mic)

        self.sc_activate_jarvis = QShortcut(QKeySequence("Ctrl+Shift+J"), self)
        self.sc_activate_jarvis.activated.connect(self.activate_jarvis)

        self.sc_escape = QShortcut(QKeySequence("Escape"), self)
        self.sc_escape.activated.connect(self.collapse_on_escape)

        # Connect FSM listener
        self.fsm.add_listener(self._on_fsm_state_changed)
        self._apply_geometry_for_mode(self._current_mode, is_closing=False)

    def visual_bounds(self) -> QRect:
        """Exact bounding rectangle where visible island/anchor graphics are drawn."""
        if self._current_mode in ("anchor", "collapsed_anchor", "floating_anchor"):
            w = 44
            h = 44
            return QRect(int((self.width() - w) / 2), int((self.height() - h) / 2), w, h)
        elif self._current_mode == "expanded":
            w = int(getattr(self.animator.w, "target", 640))
            h = int(getattr(self.animator.h, "target", 160))
            island_x = int((self.width() - w) / 2)
            return QRect(island_x, 0, w, h)
        elif self._current_mode == "compact":
            w = int(getattr(self.animator.w, "target", 288))
            h = int(getattr(self.animator.h, "target", 32))
            island_x = int((self.width() - w) / 2)
            return QRect(island_x, 0, w, h)
        elif self._current_mode == "peek":
            w = int(getattr(self.animator.w, "target", 210))
            h = int(getattr(self.animator.h, "target", 16))
            island_x = int((self.width() - w) / 2)
            return QRect(island_x, 0, w, h)
        elif self._current_mode == "hidden":
            wake_w = 240
            wake_h = 6
            island_x = int((self.width() - wake_w) / 2)
            return QRect(island_x, 0, wake_w, wake_h)
        w = int(self.animator.w.value)
        h = int(self.animator.h.value)
        island_x = int((self.width() - w) / 2)
        return QRect(island_x, 0, w, h)

    def interaction_bounds(self) -> QRect:
        """Active pointer hit-test region (visual bounds + forgiving margin)."""
        vb = self.visual_bounds()
        hit_margin = 8  # Forgiving hit margin ensuring right-edge buttons and close button are comfortably captured
        return QRect(
            max(0, vb.x() - hit_margin),
            max(0, vb.y() - hit_margin),
            min(self.width(), vb.width() + hit_margin * 2),
            min(self.height(), vb.height() + hit_margin * 2)
        )

    # Coucou camelCase aliases
    visualBounds = visual_bounds
    interactionBounds = interaction_bounds

    def _on_anim_tick(self):
        is_running = self.animator.step()

        # Dynamic positioning
        w = self.animator.w.value
        h = self.animator.h.value
        island_x = (720.0 - w) / 2.0

        # Position Character Bot (Always raised above container)
        # Empty nest while Mochi floats free: exactly one Mochi is ever visible.
        if getattr(self, "_mochi_loose", False):
            self.character.hide()
        elif self._current_mode in ("anchor", "collapsed_anchor", "floating_anchor"):
            self.character.setGeometry(4, 4, 36, 36)
            self.character.show()
            self.character.raise_()
        else:
            bot_d = max(14.0, self.animator.bot_d.value)
            bot_cx = island_x + self.animator.bot_cx.value
            bot_cy = self.animator.bot_cy.value
            bx = int(bot_cx - bot_d / 2.0)
            by = int(bot_cy - bot_d / 2.0)
            self.character.setGeometry(bx, by, int(bot_d), int(bot_d))

            if h <= 0.5 or self._is_greeting_active or self._current_view == "greeting":
                self.character.hide()
            else:
                self.character.show()
                self.character.raise_()

        # Position Mini Grid in Compact Mode
        if self._current_mode == "compact":
            self.mini_grid.setGeometry(int(island_x + w - 42.0), 2, 28, 28)
            self.mini_grid.show()
            self.mini_grid.raise_()
        else:
            self.mini_grid.hide()

        # Position compact and expanded containers
        self.compact_container.setGeometry(int(island_x), 0, int(w), 32)
        if self.compact_container.layout():
            self.compact_container.layout().activate()
        self.expanded_container.setGeometry(int(island_x), 0, int(w), int(h))

        self.update()
        if not is_running and self._current_mode == "hidden":
            self._anim_timer.setInterval(250)

    def set_mode(self, mode: str, is_closing: bool = False):
        if mode == self._current_mode:
            return
        old_mode = self._current_mode
        self._current_mode = mode
        if hasattr(self, "visibility_mgr"):
            if mode == "expanded" and self.visibility_mgr.state != GuiVisibilityState.EXPANDED:
                self.visibility_mgr.transition_to(GuiVisibilityState.EXPANDED, reason="set_mode:expanded")
            elif mode == "compact" and self.visibility_mgr.state != GuiVisibilityState.COMPACT:
                self.visibility_mgr.transition_to(GuiVisibilityState.COMPACT, reason="set_mode:compact")
            elif mode == "hidden" and self.visibility_mgr.state != GuiVisibilityState.HIDDEN:
                self.visibility_mgr.transition_to(GuiVisibilityState.HIDDEN, reason="set_mode:hidden")
        self._apply_geometry_for_mode(mode, is_closing=is_closing)
        self._play_transition_sound(old_mode, mode)

    def _on_visibility_state_changed(self, old_state: str, new_state: str):
        if new_state == GuiVisibilityState.EXPANDED.value:
            if self._current_mode != "expanded":
                self.set_mode("expanded", is_closing=False)
        elif new_state == GuiVisibilityState.COMPACT.value:
            if self._current_mode != "compact":
                self.set_mode("compact", is_closing=(old_state == GuiVisibilityState.EXPANDED.value))
        elif new_state == GuiVisibilityState.HIDDEN.value:
            if self._current_mode != "hidden":
                self.set_mode("hidden", is_closing=True)

    def _play_transition_sound(self, old_mode: str, new_mode: str) -> None:
        """Single owner of open/close/peek sounds: real transitions only.

        HIDDEN → COMPACT = peek | * → EXPANDED = open | EXPANDED → COMPACT = close.
        Same-state calls never reach here (early return above); hidden/anchor
        arrivals and the greeting ceremony stay silent.
        """
        try:
            if getattr(self, "_is_greeting_active", False):
                return
            from .semantic_events import jarvis_visual_event
            if new_mode == "compact" and old_mode in ("hidden", "peek"):
                jarvis_visual_event("hidden_to_compact", character=self.character, island=self)
            elif new_mode == "expanded" and old_mode != "expanded":
                jarvis_visual_event("compact_to_expanded", character=self.character, island=self)
            elif new_mode == "compact" and old_mode == "expanded":
                jarvis_visual_event("expanded_to_compact", character=self.character, island=self)
        except Exception:
            pass

    def _apply_geometry_for_mode(self, mode: str, is_closing: bool = False):
        if mode in ("anchor", "collapsed_anchor", "floating_anchor"):
            target_w, target_h = 44.0, 44.0
            bot_cx, bot_cy, bot_d = 22.0, 22.0, 36.0
            opacity = 1.0
            self.compact_container.hide()
            self.expanded_container.hide()
            self.mini_grid.hide()
        elif mode == "hidden":
            target_w, target_h = 184.0, 0.0
            bot_cx, bot_cy, bot_d = 46.0, 16.0, 6.0
            opacity = 0.0
            self.compact_container.hide()
            self.expanded_container.hide()
            self.mini_grid.hide()
        elif mode == "peek":
            target_w, target_h = 210.0, 16.0
            bot_cx, bot_cy, bot_d = 36.0, 9.0, 16.0
            opacity = 1.0
            self.compact_container.hide()
            self.expanded_container.hide()
            self.mini_grid.hide()
            self._start_auto_collapse_timer(3.0)
        elif mode == "compact":
            target_w, target_h = 288.0, 32.0
            bot_cx, bot_cy, bot_d = 40.0, 16.0, 22.0
            opacity = 1.0
            self.compact_container.show()
            self.expanded_container.hide()
            self.mini_grid.show()
            if hasattr(self, "visibility_mgr") and not getattr(self.visibility_mgr, "is_mouse_inside", False):
                self.visibility_mgr._start_compact_hide_timer()
        else:  # "expanded"
            target_w = 640.0
            target_h = 150.0 if self._current_view == "greeting" else (240.0 if self._current_view in ("chat", "prompt", "settings") else (180.0 if self._current_view in ("approval", "question") else 160.0))
            bot_cx = 58.0
            bot_cy = 84.0
            bot_d = 56.0
            opacity = 1.0
            self.compact_container.hide()
            self.expanded_container.show()
            self.mini_grid.hide()
            if hasattr(self, "visibility_mgr"):
                if not getattr(self.visibility_mgr, "is_mouse_inside", False) and not self.visibility_mgr.is_pinned_or_important():
                    self.visibility_mgr._start_auto_close_timer()

        if hasattr(self, "_anim_timer"):
            self._anim_timer.setInterval(16)

        self.animator.transition_to(
            target_w=target_w,
            target_h=target_h,
            bot_cx=bot_cx,
            bot_cy=bot_cy,
            bot_d=bot_d,
            opacity=opacity,
            is_closing=is_closing
        )

    def set_view(self, view_name: str):
        self._current_view = view_name
        if view_name in ("chat", "prompt"):
            self._locked_view = "chat"
            self._auto_collapse_timer.stop()
            if hasattr(self, "visibility_mgr"):
                self.visibility_mgr._auto_close_timer.stop()
        elif view_name != "greeting":
            self._locked_view = None

        if view_name != "greeting" and not getattr(self, "_mochi_loose", False) and not getattr(self, "_is_greeting_active", False):
            self.character.show()
            self.character.raise_()

        if view_name == "approval":
            try:
                from .semantic_events import jarvis_visual_event
                jarvis_visual_event("approval_required", character=self.character, island=self, visibility_mgr=self.visibility_mgr)
            except Exception:
                pass
        elif view_name == "question":
            try:
                from .semantic_events import jarvis_visual_event
                jarvis_visual_event("question_asked", character=self.character, island=self, visibility_mgr=self.visibility_mgr)
            except Exception:
                pass

        view_map = {
            "overview": 0,
            "approval": 1,
            "question": 2,
            "finished": 3,
            "error": 4,
            "chat": 5,
            "prompt": 5,
            "drop": 6,
            "upload": 6,
            "listening": 7,
            "thinking": 8,
            "speaking": 9,
            "settings": 10,
            "greeting": 11,
        }
        idx = view_map.get(view_name, 0)
        self.view_stack.setCurrentIndex(idx)
        if view_name == "overview" and hasattr(self, "view_overview"):
            self.view_overview.refresh_greeting()
        elif view_name in ("chat", "prompt") and hasattr(self, "view_chat") and self.view_chat:
            if hasattr(self.view_chat, "scroll_to_bottom"):
                self.view_chat.scroll_to_bottom(force=True)
        target_tab = "chat" if view_name in ("chat", "prompt") else ("drop" if view_name in ("drop", "upload") else ("settings" if view_name == "settings" else "overview"))
        self.header.set_active_tab(target_tab, notify=False)

        if self._current_mode == "expanded":
            if view_name == "greeting":
                target_h = 150.0
            elif view_name in ("chat", "prompt", "settings"):
                target_h = 240.0
            elif view_name in ("approval", "question"):
                target_h = 180.0
            else:
                target_h = 160.0

            self.animator.transition_to(
                target_w=640.0,
                target_h=target_h,
                bot_cx=58.0,
                bot_cy=84.0,
                bot_d=56.0,
                is_closing=False
            )
        self.view_switched.emit(view_name)

    def _toggle_settings_view(self):
        """Toggles between Settings card and previous active view."""
        if self._current_mode == "expanded" and self._current_view == "settings":
            self._close_settings_view()
        else:
            self._previous_view = self._current_view if self._current_view != "settings" else "overview"
            try:
                self.load_settings_from_config()
            except Exception:
                pass
            self.expand_to_view("settings")

    def _close_settings_view(self):
        """Returns cleanly to previous active view. NEVER terminates the JARVIS process."""
        target = getattr(self, "_previous_view", None) or "overview"
        if target == "overview":
            self.set_view("overview")
            self.collapse_to_compact()
        else:
            self.set_view(target)

    def set_mochi_loose(self, loose: bool) -> None:
        """Shows the empty nest (loose=True) or restores the island bot (docked).

        Single-identity invariant: island bot and desktop floater never show together.
        """
        self._mochi_loose = bool(loose)
        try:
            if self._mochi_loose:
                self.character.hide()
                if self._current_mode == "compact":
                    self.set_compact_status("Mochi is out — click nest to call back")
            else:
                if self._current_mode == "compact":
                    self.set_compact_status("JARVIS")
                # _on_anim_tick re-shows the bot on its next frame.
        except Exception:
            pass

    def toggle_island_visibility(self):
        """Ctrl+Space shortcut: toggles hidden vs compact/visible."""
        if self._current_mode == "hidden":
            self.set_mode("compact", is_closing=False)
        else:
            self.hide_to_edge()

    def toggle_mic(self):
        """Ctrl+Shift+M shortcut: toggles real microphone audio pipeline."""
        new_state = not self.header._mic_enabled
        self.header.set_mic_enabled(new_state)
        self.mic_toggled.emit(new_state)

    def activate_jarvis(self):
        """Ctrl+Shift+J shortcut: expands to Chat and focuses text input."""
        Sound.play("open")
        self.expand_to_view("chat")
        if hasattr(self.view_chat, "input_field"):
            self.view_chat.input_field.setFocus()

    def collapse_on_escape(self):
        """Esc shortcut: collapses expanded island to compact. NEVER terminates application."""
        if self._is_greeting_active:
            self.view_greeting.skip()
            return
        if self._current_view == "settings":
            self._close_settings_view()
            return
        if self._current_mode == "expanded":
            self._locked_view = None
            self.collapse_to_compact()

    def set_compact_status(self, text: str):
        """Update the compact capsule status text."""
        self.compact_status.setText(text)

    def set_system_state(self, state: str, details: str = "") -> None:
        """Propagates backend state to character, overview card, and status displays."""
        try:
            if hasattr(self, "character") and self.character:
                self.character.set_system_state(state)
        except Exception:
            pass
        try:
            if hasattr(self, "view_overview") and self.view_overview:
                self.view_overview.set_backend_state(state, details)
        except Exception:
            pass

    def trigger_love_emote(self, duration_s: float = 1.8):
        """Triggers the JARVIS Love/Affection emote inside the Dynamic Island."""
        self.trigger_emote("love", duration_s=duration_s)

    def trigger_emote(self, name: str = "love", duration_s: float = 1.8):
        """Generic temporary emote dispatcher (spec §13). Never replaces character."""
        try:
            self.character.trigger_emote(name, duration_s=duration_s)
        except Exception:
            try:
                self.character.trigger_love_emote(duration_s=duration_s)
            except Exception:
                pass
        if self._current_mode == "compact":
            labels = {"love": "♥ JARVIS", "proud": "★ JARVIS", "happy": "😊 JARVIS",
                      "surprised": "✦ JARVIS", "confused": "? JARVIS", "sad": "… JARVIS"}
            self.set_compact_status(labels.get(str(name).lower(), "♥ JARVIS"))
            QTimer.singleShot(int(duration_s * 1000), lambda: self.set_compact_status("JARVIS"))

    def set_accessory(self, name: str) -> None:
        """Independent accessory selector (spec §12), composable with any state."""
        try:
            self.character.set_accessory(name)
        except Exception:
            pass

    def set_animation_intensity(self, level: str) -> None:
        mapping = {"calm": 0.4, "normal": 1.0, "lively": 1.4}
        try:
            self.character.set_animation_intensity(mapping.get(str(level).lower(), 1.0))
        except Exception:
            pass

    def _on_island_chat_submitted(self, text: str) -> None:
        # Re-emit for app-level handler (set at construction via view_chat.message_submitted
        # direct connection in app.py as well); kept for mic/accessory symmetry.
        pass

    def _on_settings_mic(self, enabled: bool) -> None:
        self.header.set_mic_enabled(bool(enabled))
        self.mic_toggled.emit(bool(enabled))

    def _on_settings_speaker(self, enabled: bool) -> None:
        """Settings speaker row drives the REAL speaker state (same as header)."""
        Sound.set_enabled(bool(enabled))
        self.header.set_speaker_enabled(bool(enabled))
        self.speaker_toggled.emit(bool(enabled))

    def _on_settings_saved(self, data: dict) -> None:
        """Applies saved settings across runtime components and in-memory core config."""
        try:
            self._on_settings_speaker(data.get("sound_enabled", True))
            Sound.set_volume(float(data.get("sound_volume", 80)) / 100.0)
            self._on_settings_mic(data.get("mic_enabled", True))
            self.visibility_mgr.configure(
                expanded_timeout_s=float(data.get("auto_close_sec", 15)),
                compact_timeout_s=float(data.get("hide_delay_sec", 60))
            )
            self.set_accessory(data.get("accessory", "none"))
            self.set_animation_intensity(data.get("animation", "normal"))
            self._greeting_enabled = bool(data.get("greeting_enabled", True))

            if hasattr(self, "core") and self.core and hasattr(self.core, "config"):
                cfg = self.core.config
                cfg.setdefault("sound", {})["enabled"] = bool(data.get("sound_enabled", True))
                cfg.setdefault("sound", {})["volume"] = int(data.get("sound_volume", 80))
                cfg.setdefault("voice", {})["enabled"] = bool(data.get("mic_enabled", True))
                cfg.setdefault("voice", {})["speed"] = int(data.get("speech_speed", 100))
                wake = str(data.get("wake_word", "jarvis")).strip() or "jarvis"
                cfg.setdefault("system", {})["wake_words"] = [wake, f"hey {wake}", f"ok {wake}"]
                isl = cfg.setdefault("island", {})
                isl["auto_close_sec"] = int(data.get("auto_close_sec", 15))
                isl["hide_delay_sec"] = int(data.get("hide_delay_sec", 60))
                isl["accessory"] = data.get("accessory", "none")
                isl["animation"] = data.get("animation", "normal")
                isl["theme"] = data.get("theme", "dark")
                isl["greeting_enabled"] = bool(data.get("greeting_enabled", True))
        except Exception as e:
            logger.debug(f"[ISLAND] _on_settings_saved failed: {e}")

    def load_settings_from_config(self, cfg: Optional[dict] = None) -> None:
        """Loads configuration and populates CoucouSettingsCard + runtime state."""
        try:
            if cfg is None:
                if hasattr(self, "core") and self.core and hasattr(self.core, "config"):
                    cfg = self.core.config
                else:
                    cfg_path = getattr(self.view_settings, "config_path", None)
                    if not cfg_path or not os.path.exists(cfg_path):
                        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                        cfg_path = os.path.join(root, "config.yaml")
                    if os.path.exists(cfg_path):
                        import yaml
                        with open(cfg_path, "r", encoding="utf-8") as f:
                            cfg = yaml.safe_load(f) or {}
                    else:
                        cfg = {}

            island_cfg = cfg.get("island", {}) if isinstance(cfg, dict) else {}
            sound_cfg = cfg.get("sound", {}) if isinstance(cfg, dict) else {}
            voice_cfg = cfg.get("voice", {}) if isinstance(cfg, dict) else {}
            sys_cfg = cfg.get("system", {}) if isinstance(cfg, dict) else {}

            wake_words = sys_cfg.get("wake_words", ["jarvis"])
            primary_wake = wake_words[0] if wake_words else "jarvis"

            acc_val = island_cfg.get("accessory")
            if not acc_val:
                try:
                    acc_val = getattr(self.character.accessories.current, "value", "none")
                except Exception:
                    acc_val = "none"

            settings_data = {
                "sound_enabled": sound_cfg.get("enabled", getattr(Sound, "enabled", True)),
                "sound_volume": sound_cfg.get("volume", int(round(getattr(Sound, "volume", 0.8) * 100))),
                "auto_close_sec": island_cfg.get("auto_close_sec", int(getattr(self.visibility_mgr, "expanded_timeout_s", 15))),
                "hide_delay_sec": island_cfg.get("hide_delay_sec", int(getattr(self.visibility_mgr, "compact_timeout_s", 60))),
                "mic_enabled": voice_cfg.get("enabled", getattr(self.header, "_mic_enabled", True)),
                "wake_word": primary_wake,
                "speech_speed": voice_cfg.get("speed", 100),
                "accessory": acc_val,
                "animation": island_cfg.get("animation", "normal"),
                "theme": island_cfg.get("theme", "dark"),
                "greeting_enabled": island_cfg.get("greeting_enabled", getattr(self, "_greeting_enabled", True)),
            }
            self.view_settings.set_settings(settings_data)
        except Exception as e:
            logger.debug(f"[ISLAND] load_settings_from_config error: {e}")

    def sync_mic_ui(self, mic_enabled: bool, listening: bool = False) -> None:
        """Pushes master mic state to every mirror (header + settings).

        All mirror setters are signal-blocked, so this never loops back.
        Voice capture lives only in the header master switch — the chat card
        intentionally has no mic control.
        """
        try:
            self.header.set_mic_enabled(bool(mic_enabled))
        except Exception:
            pass
        try:
            self.view_settings.set_mic_state(bool(mic_enabled))
        except Exception:
            pass

    def sync_speaker_ui(self, enabled: bool) -> None:
        """Pushes master speaker state to header + settings mirrors (no loops)."""
        try:
            self.header.set_speaker_enabled(bool(enabled))
        except Exception:
            pass
        try:
            self.view_settings.set_speaker_state(bool(enabled))
        except Exception:
            pass

    def set_audio_level(self, level: float, is_speech: bool = False):
        """Forward real audio levels to companion bot and active waveform visualizers."""
        self.character.set_audio_level(level, is_speech)
        self.view_listening.set_audio_level(level, is_speech)
        self.view_speaking.set_audio_level(level)

    def expand_to_view(self, view_name: str):
        self.set_view(view_name)
        self.set_mode("expanded", is_closing=False)
        self.expanded.emit()

    def collapse_to_compact(self):
        self._locked_view = None
        # Reference pill always reads plain "JARVIS" (never a stale status).
        if not getattr(self, "_mochi_loose", False):
            self.set_compact_status("JARVIS")
        self.set_mode("compact", is_closing=True)
        self.collapsed.emit()

    def collapse_to_anchor(self):
        """Collapses expanded Dynamic Island back into the permanent floating JARVIS icon."""
        if self._current_mode == "anchor":
            return
        self._locked_view = None
        self.set_mode("anchor", is_closing=True)
        self.collapsed.emit()

    def peek_out(self):
        """Peeks out slightly from the top edge when the notch is hovered."""
        if self._locked_view == "chat" or self._is_greeting_active:
            return
        if self._current_mode != "peek":
            self.set_mode("peek", is_closing=False)

    def hide_to_edge(self):
        """Close (×): back to the compact pill; idle auto-hide takes it to the
        top-edge line, notch hover peeks it back. Backend/voice stay alive."""
        self.collapse_to_compact()
        self.close_requested.emit()

    def play_startup_greeting(self):
        """Plays the Coucou-choreographed startup greeting ceremony on launch."""
        self._is_greeting_active = True
        self._locked_view = "greeting"
        self.header.hide()
        self.character.hide()
        self.mini_grid.hide()
        self.set_view("greeting")
        self.set_mode("expanded", is_closing=False)
        self.view_greeting.start()

    def _on_greeting_completed(self):
        """Called when greeting ceremony completes or is skipped."""
        self._is_greeting_active = False
        self._locked_view = None
        self.header.show()
        if not getattr(self, "_mochi_loose", False):
            self.character.show()
            self.character.raise_()
        self.set_view("overview")
        # Smooth start: linger full-size so Mochi visibly arrives in the
        # overview, then ease home — never vanish-then-pop.
        QTimer.singleShot(2200, self._settle_after_greeting)

    def _settle_after_greeting(self):
        """Gentle post-greeting collapse; skipped if the user took over."""
        try:
            if self._is_greeting_active:
                return
            if (self._current_mode == "expanded" and self._current_view == "overview"
                    and self._locked_view is None):
                self.collapse_to_compact()
        except Exception:
            pass

    def _on_fsm_state_changed(self, old_state: IslandState, new_state: IslandState):
        state_str = new_state.value.lower()

        # ACTIVE VIEW LOCK: When locked in chat, update bot expression but NEVER navigate away or collapse!
        if self._locked_view == "chat" or (self._current_mode == "expanded" and self._current_view in ("chat", "prompt")):
            if "emote_love" in state_str:
                self.character.trigger_love_emote()
            elif "thinking" in state_str:
                self.character.set_state("thinking")
            elif "speaking" in state_str:
                self.character.set_state("speaking")
            elif "listening" in state_str:
                self.character.set_state("listening")
            elif "working" in state_str or "executing" in state_str:
                self.character.set_state("working")
            elif "finished" in state_str or "success" in state_str:
                self.character.set_state("success")
            elif "error" in state_str:
                self.character.set_state("error")
            elif "compact" in state_str or "ready" in state_str or "idle" in state_str or "anchor" in state_str:
                self.character.set_state("idle")
            return

        # GREETING LOCK: Do not interrupt greeting unless user specifically requested
        if self._is_greeting_active and "greeting" in getattr(self, "_locked_view", ""):
            return

        if "floating_anchor" in state_str or "collapsed_anchor" in state_str or state_str == "anchor":
            self.character.set_state("idle")
            self.collapse_to_anchor()
        elif "hidden" in state_str:
            self.set_mode("hidden", is_closing=True)
        elif "peek" in state_str:
            self.peek_out()
        elif "emote_love" in state_str:
            self.trigger_love_emote()
        elif "compact" in state_str:
            self.character.set_state("idle")
            if not getattr(self, "_mochi_loose", False):
                self.set_compact_status("JARVIS")
            self.set_mode("compact", is_closing=(old_state == IslandState.EXPANDED))
        elif "approval" in state_str or "confirmation" in state_str:
            self.expand_to_view("approval")
        elif "question" in state_str:
            self.expand_to_view("question")
        elif "chat" in state_str:
            self.expand_to_view("chat")
        elif "drop" in state_str:
            self.expand_to_view("drop")
        elif "error" in state_str:
            self.character.set_state("error")
            self.expand_to_view("error")
        elif "finished" in state_str or "success" in state_str:
            self.character.set_state("success")
            self.expand_to_view("finished")
        elif "listening" in state_str:
            self.character.set_state("listening")
            self.set_compact_status("Listening…")
            self.expand_to_view("listening")
        elif "thinking" in state_str:
            self.character.set_state("thinking")
            self.set_compact_status("Thinking…")
            self.expand_to_view("thinking")
        elif "speaking" in state_str:
            self.character.set_state("speaking")
            self.set_compact_status("Speaking…")
            self.expand_to_view("speaking")
        elif "working" in state_str or "executing" in state_str:
            self.character.set_state("working")
            self.set_compact_status("Working…")
            self.expand_to_view("overview")
        elif "settings" in state_str:
            self.expand_to_view("settings")
        elif "expanded" in state_str:
            self.expand_to_view("overview")

    def _start_auto_collapse_timer(self, seconds: float):
        if hasattr(self, "visibility_mgr"):
            self.visibility_mgr.expanded_timeout_s = max(0.1, float(seconds))
            self.visibility_mgr._start_auto_close_timer()
        else:
            self._auto_collapse_timer.stop()
            if seconds > 0 and self._locked_view != "chat":
                self._auto_collapse_timer.start(int(seconds * 1000))

    def _on_auto_collapse_timeout(self):
        if hasattr(self, "visibility_mgr"):
            if self._current_mode == "expanded":
                self.visibility_mgr._on_auto_close_timeout()
            elif self._current_mode in ("compact", "peek"):
                self.visibility_mgr._on_compact_hide_timeout()
        else:
            if self._current_mode == "expanded":
                self.collapse_to_compact()
            elif self._current_mode in ("compact", "peek"):
                self.set_mode("hidden", is_closing=True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.collapse_on_escape()
            return
        super().keyPressEvent(event)

    def _on_approval_decision(self, allowed: bool):
        from .semantic_events import jarvis_visual_event
        if allowed:
            jarvis_visual_event("user_approved", character=self.character, island=self, visibility_mgr=self.visibility_mgr)
            if hasattr(self, "view_finished"):
                self.view_finished.set_finished_data("Action Authorized", "Executing confirmed operation...")
                self.set_view("finished")
        else:
            jarvis_visual_event("user_denied", character=self.character, island=self, visibility_mgr=self.visibility_mgr)
            self.collapse_to_compact()

    def _on_question_option(self, opt: str):
        from .semantic_events import jarvis_visual_event
        jarvis_visual_event("ui_blip")
        self.collapse_to_compact()

    def _handle_dropped_file(self, file_path: str):
        from .semantic_events import jarvis_visual_event
        jarvis_visual_event("file_accepted", file_path=file_path, character=self.character, island=self)
        self.expand_to_view("chat")
        self.view_chat.add_message("user", f"Analyzed file: {file_path}")

    # ── Paint Event ───────────────────────────────────────────────────────────
    def paintEvent(self, event):
        w = self.animator.w.value
        h = self.animator.h.value

        if self._current_mode in ("anchor", "collapsed_anchor", "floating_anchor") or (w <= 50.0 and h <= 50.0):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            island_x = (self.width() - w) / 2.0
            island_y = (self.height() - h) / 2.0
            path = QPainterPath()
            path.addRoundedRect(island_x, island_y, w, h, 14.0, 14.0)

            # 1. Soft Depth Shadow
            painter.setPen(QPen(QColor(0, 0, 0, 100), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

            # 2. Rich Obsidian Black surface
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(11, 12, 14, 240))
            painter.drawPath(path)

            # 3. Hairline border
            painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            painter.end()
            return

        if h <= 0.5:
            # Wake strip: one thin black line glued to the top edge.
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            wake_x = (720.0 - 240.0) / 2.0
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(11, 12, 14, 220))
            painter.drawRoundedRect(QRectF(wake_x, 0, 240.0, 6.0), 3.0, 3.0)
            painter.end()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        island_x = (720.0 - w) / 2.0
        corner_radius = 22.0 if self._current_mode == "expanded" else (14.0 if self._current_mode == "compact" else 8.0)
        corner_radius = min(corner_radius, max(1.0, h / 2.0))

        # Coucou Island Capsule Path (glued to top edge: 0 0 corner corner)
        path = QPainterPath()
        path.moveTo(island_x, 0)
        path.lineTo(island_x + w, 0)
        path.lineTo(island_x + w, max(0.0, h - corner_radius))
        path.arcTo(island_x + w - (corner_radius * 2), h - (corner_radius * 2), corner_radius * 2, corner_radius * 2, 0, -90)
        path.lineTo(island_x + corner_radius, h)
        path.arcTo(island_x, h - (corner_radius * 2), corner_radius * 2, corner_radius * 2, -90, -90)
        path.closeSubpath()

        # 1. Soft Depth Shadow
        shadow_pen = QPen(QColor(0, 0, 0, 90), 3)
        painter.setPen(shadow_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # 2. Rich Obsidian Black surface (#0b0c0e - safe non-zero for Windows DWM)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(11, 12, 14))
        painter.drawPath(path)

        # 3. Hairline border (rgba(255, 255, 255, 0.08))
        border_pen = QPen(QColor(255, 255, 255, 20), 1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        painter.end()

    # ── Mouse Interaction ─────────────────────────────────────────────────────
    def is_pinned_or_important(self) -> bool:
        """Returns True if the island is in an important/interactive state that blocks auto-collapse/auto-hide."""
        if hasattr(self, "visibility_mgr"):
            return self.visibility_mgr.is_pinned_or_important()
        return False

    def enterEvent(self, event):
        super().enterEvent(event)
        if event is None and self._current_mode == "hidden":
            self.peek_out()
            if hasattr(self, "visibility_mgr"):
                self.visibility_mgr._is_mouse_inside = True
            return

        if hasattr(self, "visibility_mgr"):
            self.visibility_mgr.on_mouse_enter()
        if self._current_mode == "hidden":
            self.peek_out()
        elif self._current_mode == "peek":
            self.set_mode("compact", is_closing=False)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if hasattr(self, "visibility_mgr"):
            self.visibility_mgr.on_mouse_leave()
        if self._current_mode == "peek":
            self.set_mode("hidden", is_closing=True)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position()
        w = self.animator.w.value
        island_x = (720.0 - w) / 2.0

        if hasattr(self, "visibility_mgr"):
            pt = pos.toPoint() if hasattr(pos, "toPoint") else QPoint(int(pos.x()), int(pos.y()))
            if self.interaction_bounds().contains(pt):
                self.visibility_mgr.notify_activity("mouse_move")

        if self._current_mode == "hidden":
            if 240.0 <= pos.x() <= 480.0 and pos.y() <= 16.0:
                self.peek_out()
        elif self._current_mode == "peek":
            if island_x <= pos.x() <= island_x + w and pos.y() > 10.0:
                self.set_mode("compact", is_closing=False)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._mouse_press_pos = event.globalPosition().toPoint()
            self._mouse_is_drag = False
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and not getattr(self, "_mouse_is_drag", False):
            if hasattr(self, "visibility_mgr"):
                self.visibility_mgr.on_mouse_click()
            if self._current_mode in ("anchor", "collapsed_anchor", "floating_anchor"):
                self.expand_to_view("overview")
            elif self._current_mode in ("peek", "compact"):
                self.expand_to_view("overview")
            elif self._current_mode == "hidden":
                self.peek_out()
        self._mouse_is_drag = False
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            if self._current_mode != "expanded":
                self.expand_to_view("drop")

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                path = urls[0].toLocalFile()
                self._handle_dropped_file(path)
                event.acceptProposedAction()
