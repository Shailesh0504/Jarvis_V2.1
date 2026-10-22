# gui/island/views.py
"""Coucou Dynamic Island Views — High-fidelity Python/Qt implementation of views.ts.

Faithfully implements Coucou's visual composition, card washes, and typography:
- CoucouHeaderWidget: 3 tab capsules (home, bubble, plus) + 2 header actions (gear, sound)
- CoucouOverviewCard: Left card with Who dot, active task ticker, and jump arrow; Right card with 2x2 tool pills
- CoucouApprovalCard: Amber wash, code block, Deny (N) and Allow (Y) capsule buttons
- CoucouQuestionCard: Cyan wash, question prompt, option buttons
- CoucouFinishedCard: Green wash, completion summary, OK button
- CoucouErrorCard: Red wash, error diagnosis, Retry button
- CoucouChatCard: Indigo wash, scrollable bubbles, capsule input bar with circular send button
- CoucouDropCard: Dashed border file drop target card
"""

import html
import os
import re
from typing import List, Optional
from PySide6.QtCore import Qt, Signal, QRectF, QTimer, QUrl
from PySide6.QtGui import (
    QColor, QFont, QPainter, QLinearGradient, QRadialGradient, QBrush, QPen,
    QTextCursor, QKeySequence, QPixmap, QTextDocument
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QLineEdit, QScrollArea, QSizePolicy, QSlider, QComboBox,
    QTextBrowser
)

from .icons import create_coucou_icon
from .pills import StatusPill, ToolPill, ActiveAppPill


class WashCard(QFrame):
    """Rounded dark card (#141518) with optional soft radial wash gradient."""

    def __init__(self, wash_color: Optional[QColor] = None, parent=None):
        super().__init__(parent)
        self.wash_color = wash_color
        self.setObjectName("wash_card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            QFrame#wash_card {
                background: #141518;
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 18px;
            }
        """)

    def set_wash(self, color: Optional[QColor]):
        self.wash_color = color
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.wash_color:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            w = self.width()
            h = self.height()
            grad = QRadialGradient(w / 2.0, h * 1.3, max(w, h) * 0.9)
            grad.setColorAt(0.0, self.wash_color)
            grad.setColorAt(0.7, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(0, 0, w, h), 18, 18)
            painter.end()


class CoucouHeaderWidget(QWidget):
    """Coucou Top Bar: 3 tabs on the left, 4 compact control actions on the right:
       1. Microphone toggle (real audio capture & VAD pipeline)
       2. Speaker toggle (independent TTS speech output mute)
       3. Settings (opens settings view without terminating JARVIS)
       4. Close × (smoothly hides island to top-edge wake strip without terminating JARVIS)
    """

    tab_changed = Signal(str)          # "overview", "chat", "drop"
    mic_toggled = Signal(bool)         # True = mic enabled, False = mic disabled
    speaker_toggled = Signal(bool)     # True = TTS enabled, False = TTS muted
    sound_toggled = Signal(bool)       # Backward-compatibility alias
    settings_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        self._mic_enabled = True
        self._speaker_enabled = True
        self._sound_enabled = True
        self._active_tab = "overview"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 2, 10, 2)
        layout.setSpacing(6)

        # Tab capsule container
        self.tab_container = QWidget()
        tabs_layout = QHBoxLayout(self.tab_container)
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(4)

        self.tab_home = QPushButton()
        self.tab_home.setIcon(create_coucou_icon("house", QColor("#f5f6f8"), 14))
        self.tab_home.setToolTip("Overview")
        self.tab_home.setCursor(Qt.PointingHandCursor)
        self.tab_home.clicked.connect(lambda: self.set_active_tab("overview"))

        self.tab_chat = QPushButton()
        self.tab_chat.setIcon(create_coucou_icon("bubble", QColor("#8e939c"), 14))
        self.tab_chat.setToolTip("Ask JARVIS")
        self.tab_chat.setCursor(Qt.PointingHandCursor)
        self.tab_chat.clicked.connect(lambda: self.set_active_tab("chat"))

        self.tab_drop = QPushButton()
        self.tab_drop.setIcon(create_coucou_icon("plus", QColor("#8e939c"), 14))
        self.tab_drop.setToolTip("Drop Files")
        self.tab_drop.setCursor(Qt.PointingHandCursor)
        self.tab_drop.clicked.connect(lambda: self.set_active_tab("drop"))

        for btn in (self.tab_home, self.tab_chat, self.tab_drop):
            btn.setFixedSize(30, 22)
            tabs_layout.addWidget(btn)

        layout.addWidget(self.tab_container)
        layout.addStretch()

        # ── 4 Compact Controls in Top-Right ──────────────────────────────────
        btn_style = """
            QPushButton {
                background: transparent;
                border-radius: 11px;
                border: none;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.08);
            }
            QToolTip {
                background-color: #141518;
                color: #f5f6f8;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 6px;
                padding: 4px 8px;
                font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", -apple-system, sans-serif;
                font-size: 11px;
                font-weight: 500;
            }
        """

        # 1. Microphone Toggle (real hardware/audio capture toggle)
        self.mic_btn = QPushButton()
        self.mic_btn.setFixedSize(26, 22)
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.setStyleSheet(btn_style)
        self.mic_btn.clicked.connect(self._toggle_mic)
        layout.addWidget(self.mic_btn)

        # 2. Speaker Toggle (independent TTS speech output mute)
        self.speaker_btn = QPushButton()
        self.speaker_btn.setFixedSize(26, 22)
        self.speaker_btn.setCursor(Qt.PointingHandCursor)
        self.speaker_btn.setStyleSheet(btn_style)
        self.speaker_btn.clicked.connect(self._toggle_speaker)
        layout.addWidget(self.speaker_btn)
        # Backward-compatibility alias
        self.sound_btn = self.speaker_btn

        # 3. Settings (opens settings view without terminating process)
        self.gear_btn = QPushButton()
        self.gear_btn.setIcon(create_coucou_icon("gear", QColor("#8e939c"), 14))
        self.gear_btn.setToolTip("Settings")
        self.gear_btn.setCursor(Qt.PointingHandCursor)
        self.gear_btn.setFixedSize(26, 22)
        self.gear_btn.setStyleSheet(btn_style)
        self.gear_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self.gear_btn)

        # 4. Close (×) (smoothly hides Dynamic Island to top-edge; NOT app exit)
        self.close_btn = QPushButton()
        self.close_btn.setIcon(create_coucou_icon("xmark", QColor("#8e939c"), 13))
        self.close_btn.setToolTip("Hide Island (Ctrl+Space to reopen)")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setFixedSize(26, 22)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border-radius: 11px;
                border: none;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.20);
            }
            QToolTip {
                background-color: #141518;
                color: #f5f6f8;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 6px;
                padding: 4px 8px;
                font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", -apple-system, sans-serif;
                font-size: 11px;
                font-weight: 500;
            }
        """)
        self.close_btn.clicked.connect(self.close_clicked.emit)
        layout.addWidget(self.close_btn)

        self._refresh_mic_icon()
        self._refresh_speaker_icon()
        self._update_styles()

    def set_active_tab(self, tab: str, notify: bool = True):
        if self._active_tab != tab:
            self._active_tab = tab
            self._update_styles()
            if notify:
                self.tab_changed.emit(tab)

    def set_mic_enabled(self, enabled: bool):
        if self._mic_enabled != enabled:
            self._mic_enabled = enabled
            self._refresh_mic_icon()

    def set_speaker_enabled(self, enabled: bool):
        if self._speaker_enabled != enabled:
            self._speaker_enabled = enabled
            self._sound_enabled = enabled
            self._refresh_speaker_icon()

    def _toggle_mic(self):
        self._mic_enabled = not self._mic_enabled
        self._refresh_mic_icon()
        self.mic_toggled.emit(self._mic_enabled)

    def _toggle_speaker(self):
        self._speaker_enabled = not self._speaker_enabled
        self._sound_enabled = self._speaker_enabled
        self._refresh_speaker_icon()
        self.speaker_toggled.emit(self._speaker_enabled)
        self.sound_toggled.emit(self._speaker_enabled)

    def _toggle_sound(self):
        self._toggle_speaker()

    def _refresh_mic_icon(self):
        if self._mic_enabled:
            self.mic_btn.setIcon(create_coucou_icon("mic", QColor("#22d3ee"), 14))
            self.mic_btn.setToolTip("Microphone: ON (Click to turn OFF / Ctrl+Shift+M)")
        else:
            self.mic_btn.setIcon(create_coucou_icon("micOff", QColor("#ef4444"), 14))
            self.mic_btn.setToolTip("Microphone: OFF (Click to turn ON / Ctrl+Shift+M)")

    def _refresh_speaker_icon(self):
        if self._speaker_enabled:
            self.speaker_btn.setIcon(create_coucou_icon("speakerOn", QColor("#f5f6f8"), 14))
            self.speaker_btn.setToolTip("Speaker TTS: ON (Click to mute)")
        else:
            self.speaker_btn.setIcon(create_coucou_icon("speakerOff", QColor("#64748b"), 14))
            self.speaker_btn.setToolTip("Speaker TTS: MUTED (Click to unmute)")

    def _update_styles(self):
        tooltip_css = "QToolTip { background-color: #141518; color: #f5f6f8; border: 1px solid rgba(255,255,255,0.16); border-radius: 6px; padding: 4px 8px; font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Inter', -apple-system, sans-serif; font-size: 11px; font-weight: 500; }"
        active_style = f"background: #1d1f23; border-radius: 11px; border: 1px solid rgba(255,255,255,0.06); {tooltip_css}"
        inactive_style = f"background: transparent; border-radius: 11px; border: none; {tooltip_css}"

        self.tab_home.setStyleSheet(active_style if self._active_tab == "overview" else inactive_style)
        self.tab_chat.setStyleSheet(active_style if self._active_tab == "chat" else inactive_style)
        self.tab_drop.setStyleSheet(active_style if self._active_tab == "drop" else inactive_style)

        self.tab_home.setIcon(create_coucou_icon("house", QColor("#f5f6f8" if self._active_tab == "overview" else "#8e939c"), 14))
        self.tab_chat.setIcon(create_coucou_icon("bubble", QColor("#f5f6f8" if self._active_tab == "chat" else "#8e939c"), 14))
        self.tab_drop.setIcon(create_coucou_icon("plus", QColor("#f5f6f8" if self._active_tab == "drop" else "#8e939c"), 14))


class CoucouPillWidget(QFrame):
    """Capsule pill matching Coucou overview.png right-hand cards."""

    clicked = Signal()

    def __init__(self, title: str, color_hex: str = "#22c55e", parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)
        self._color = color_hex

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 10, 2)
        layout.setSpacing(6)

        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {color_hex}; font-size: 11px; font-family: Segoe UI, Arial; background: transparent; border: none;")
        layout.addWidget(self.dot)

        self.lbl = QLabel(title)
        self.lbl.setStyleSheet("color: #f5f6f8; font-size: 11px; font-weight: 500; font-family: Segoe UI, Arial; background: transparent; border: none;")
        layout.addWidget(self.lbl)
        layout.addStretch()

        self._update_style(hover=False)

    def _update_style(self, hover: bool = False):
        if hover:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {self._color}20;
                    border: 1px solid {self._color}80;
                    border-radius: 14px;
                }}
                QLabel {{
                    border: none;
                    background: transparent;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background: #111215;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 14px;
                }}
                QLabel {{
                    border: none;
                    background: transparent;
                }}
            """)

    def setText(self, text: str):
        self.lbl.setText(text)

    def text(self) -> str:
        return self.lbl.text()

    def enterEvent(self, event):
        self._update_style(hover=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._update_style(hover=False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MicStatusIndicator(QFrame):
    """Small, non-intrusive mic status capsule indicator for the Home overview card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 8, 0)
        layout.setSpacing(4)

        self.lbl = QLabel("🎙 Ready")
        self.lbl.setStyleSheet("color: #8e939c; font-size: 10.5px; font-weight: 500; font-family: Segoe UI, Arial; background: transparent; border: none;")
        layout.addWidget(self.lbl)

        self._current_state = "ready"
        self._is_bluetooth = False
        self._apply_style("ready")

    def text(self) -> str:
        return self.lbl.text()

    def setText(self, text: str) -> None:
        """Backward-compatible setter; infers state from text if needed."""
        text_lower = text.lower()
        if "listening" in text_lower or "heard" in text_lower or "transcribing" in text_lower:
            self.set_mic_state("listening")
        elif "processing" in text_lower or "thinking" in text_lower or "running" in text_lower:
            self.set_mic_state("processing")
        elif "speaking" in text_lower:
            self.set_mic_state("speaking")
        elif "unavailable" in text_lower or "error" in text_lower or "mute" in text_lower:
            self.set_mic_state("unavailable")
        elif "bluetooth" in text_lower or "earbud" in text_lower:
            self.set_mic_state("bluetooth", is_bluetooth=True)
        elif "ready" in text_lower:
            self.set_mic_state("ready")
        else:
            self.lbl.setText(text)

    def set_mic_state(self, state: str, is_bluetooth: Optional[bool] = None, details: str = "") -> None:
        state_lower = (state or "ready").lower().strip()
        if is_bluetooth is not None:
            self._is_bluetooth = bool(is_bluetooth)

        if state_lower in ("unavailable", "disabled", "muted", "off") or details == "unavailable":
            self._current_state = "unavailable"
            self.lbl.setText("⚠ Microphone unavailable")
            self._apply_style("unavailable")
        elif state_lower in ("listening", "wake_word", "wake"):
            self._current_state = "listening"
            self.lbl.setText("🎙 Listening...")
            self._apply_style("listening")
        elif state_lower in ("processing", "thinking", "working", "executing"):
            self._current_state = "processing"
            self.lbl.setText("◌ Processing...")
            self._apply_style("processing")
        elif state_lower == "speaking":
            self._current_state = "speaking"
            self.lbl.setText("🔊 Speaking...")
            self._apply_style("speaking")
        elif state_lower == "bluetooth" or (self._is_bluetooth and state_lower in ("ready", "idle", "normal")):
            self._current_state = "bluetooth"
            self.lbl.setText("🎙 Bluetooth microphone")
            self._apply_style("bluetooth")
        else:
            self._current_state = "ready"
            self.lbl.setText("🎙 Ready")
            self._apply_style("ready")

    def _apply_style(self, state: str) -> None:
        styles = {
            "ready": ("#8e939c", "rgba(255, 255, 255, 0.05)", "rgba(255, 255, 255, 0.08)"),
            "listening": ("#22d3ee", "rgba(34, 211, 238, 0.12)", "rgba(34, 211, 238, 0.35)"),
            "processing": ("#c084fc", "rgba(192, 132, 252, 0.12)", "rgba(192, 132, 252, 0.35)"),
            "speaking": ("#00f0ff", "rgba(0, 240, 255, 0.12)", "rgba(0, 240, 255, 0.35)"),
            "bluetooth": ("#38bdf8", "rgba(56, 189, 248, 0.10)", "rgba(56, 189, 248, 0.25)"),
            "unavailable": ("#fbbf24", "rgba(245, 158, 11, 0.12)", "rgba(245, 158, 11, 0.30)"),
        }
        color, bg, border = styles.get(state, styles["ready"])
        self.lbl.setStyleSheet(f"color: {color}; font-size: 10.5px; font-weight: 500; font-family: Segoe UI, Arial; background: transparent; border: none;")
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 10px;
            }}
        """)


class CoucouOverviewCard(QWidget):
    """Coucou Overview view: Clean minimal companion card with quick prompt action (dashboard clutter eliminated)."""

    jump_clicked = Signal()
    chat_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 6)
        layout.setSpacing(10)

        # Single sleek Companion Card matching Coucou philosophy
        self.card = WashCard(wash_color=QColor(0, 240, 255, 30))
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(14)

        # Bot placeholder spacer (the actual JarvisCharacter sits in island canvas overlay)
        self.bot_spacer = QWidget()
        self.bot_spacer.setFixedWidth(64)
        card_layout.addWidget(self.bot_spacer)

        # Companion info column
        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(4)

        who_row = QHBoxLayout()
        who_row.setContentsMargins(0, 0, 0, 0)
        who_row.setSpacing(8)

        self.who_dot = QLabel("●")
        self.who_dot.setStyleSheet("color: #00f0ff; font-size: 11px; font-family: Segoe UI, Arial;")
        who_row.addWidget(self.who_dot)

        self.who_name = QLabel("JARVIS")
        self.who_name.setStyleSheet("color: #f5f6f8; font-size: 14px; font-weight: 700; font-family: Segoe UI, Arial;")
        who_row.addWidget(self.who_name)

        self.tool_tag = QLabel("Companion")
        self.tool_tag.setStyleSheet("color: #8e939c; font-size: 11px; font-weight: 500; font-family: Segoe UI, Arial;")
        who_row.addWidget(self.tool_tag)

        # Small mic status indicator badge (clean, non-intrusive)
        self.mic_indicator = MicStatusIndicator(parent=self.card)
        who_row.addWidget(self.mic_indicator)
        who_row.addStretch()
        info_col.addLayout(who_row)

        self.greeting_label = QLabel("Good morning, Boss")
        self.greeting_label.setStyleSheet("color: #00f0ff; font-size: 12.5px; font-weight: 600; font-family: Segoe UI, Arial;")
        info_col.addWidget(self.greeting_label)

        self.ticker_text = QLabel("\u25cf JARVIS is online and ready")
        self.ticker_text.setWordWrap(True)
        self.ticker_text.setStyleSheet("color: #9398a1; font-size: 11.5px; font-weight: 500; font-family: Segoe UI, Arial;")
        info_col.addWidget(self.ticker_text)

        # Quick Chat Prompt Pill Button
        self.ask_btn = QPushButton("💬 Ask JARVIS anything…")
        self.ask_btn.setCursor(Qt.PointingHandCursor)
        self.ask_btn.setStyleSheet("""
            QPushButton {
                background: #111215;
                color: #8e939c;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 11.5px;
                font-family: Segoe UI, Arial;
                text-align: left;
            }
            QPushButton:hover {
                background: #1a1c21;
                color: #f5f6f8;
                border-color: rgba(0, 240, 255, 0.35);
            }
        """)
        self.ask_btn.clicked.connect(self.chat_requested.emit)
        info_col.addWidget(self.ask_btn)

        card_layout.addLayout(info_col, stretch=1)

        self.jump_btn = QPushButton()
        self.jump_btn.setIcon(create_coucou_icon("arrowUpRight", QColor("#8e939c"), 12))
        self.jump_btn.setFixedSize(22, 22)
        self.jump_btn.setStyleSheet("background: transparent; border: none;")
        self.jump_btn.setCursor(Qt.PointingHandCursor)
        self.jump_btn.setToolTip("Open Studio")
        self.jump_btn.clicked.connect(self.jump_clicked.emit)
        card_layout.addWidget(self.jump_btn, alignment=Qt.AlignTop)

        layout.addWidget(self.card)

        # Retain backward-compatible references for app.py and legacy tests (hidden from layout)
        self.left_card = self.card
        self.right_card = QWidget()
        self.pill_app = CoucouPillWidget("VS Code", color_hex="#22c55e", parent=self.right_card)
        self.pill_status = StatusPill(parent=self.right_card)
        self.pill_engine = CoucouPillWidget("Local LLM", color_hex="#6366f1", parent=self.right_card)
        self.pill_mic = self.mic_indicator

        # Locked home greeting: session/start/context-based, never per-second.
        # _home_kind in ("time", "first_startup", "welcome_back", "task_done").
        self._home_kind = "time"
        self._home_daypart = None
        self._home_detail = ""
        self._home_title = ""
        self._home_sub = ""
        self._live_active = False
        self.refresh_greeting()

    def show_home(self, kind: str = "time", detail: str = "") -> None:
        """Locks in a home greeting. Context kinds persist until replaced."""
        from .home_context import HomeKind, resolve_context_greeting, resolve_time_greeting
        kind = str(kind or HomeKind.TIME)
        if kind not in HomeKind.ALL:
            kind = HomeKind.TIME
        self._live_active = False
        if kind == HomeKind.TIME:
            title, sub, daypart = resolve_time_greeting()
            self._home_kind = HomeKind.TIME
            self._home_daypart = daypart
            self._home_detail = ""
        else:
            title, sub = resolve_context_greeting(kind, detail)
            self._home_kind = kind
            self._home_detail = str(detail or "")
        self._home_title = title
        self._home_sub = sub
        self.who_name.setText("JARVIS")
        self.greeting_label.setText(title)
        self.ticker_text.setText(sub)
        self.who_dot.setStyleSheet("color: #00f0ff; font-size: 11px; font-family: Segoe UI, Arial;")

    def restore_home(self) -> None:
        """Re-applies the locked home greeting after live activity ends."""
        self._live_active = False
        if self._home_kind == "time":
            self.refresh_greeting()
            return
        if self._home_title:
            self.who_name.setText("JARVIS")
            self.greeting_label.setText(self._home_title)
            self.ticker_text.setText(self._home_sub)
            self.who_dot.setStyleSheet("color: #00f0ff; font-size: 11px; font-family: Segoe UI, Arial;")

    def refresh_greeting(self):
        """Stable refresh: time-based title recomputes ONLY on day-part rollover.

        Contextual locks (first startup / welcome back / task done) are never
        overwritten here; live activity text is never clobbered either. The
        clock subtitle still ticks so the card never looks frozen.
        """
        if self._live_active:
            return
        if getattr(self, "_home_kind", "time") != "time":
            return
        try:
            from .home_context import resolve_time_greeting
            title, sub, daypart = resolve_time_greeting()
            if self._home_daypart is not None and daypart == self._home_daypart:
                self.ticker_text.setText(sub)
                self._home_sub = sub
                return
            self._home_daypart = daypart
            self._home_title = title
            self._home_sub = sub
            self.who_name.setText("JARVIS")
            self.greeting_label.setText(title)
            self.ticker_text.setText(sub)
            self.who_dot.setStyleSheet("color: #00f0ff; font-size: 11px; font-family: Segoe UI, Arial;")
        except Exception:
            if not self._home_title:
                self.who_name.setText("JARVIS")
                self.greeting_label.setText("Good Day, Boss")
                self.ticker_text.setText("\u25cf JARVIS is online and ready")

    def showEvent(self, event):
        if not getattr(self, "_live_active", False):
            self.restore_home()
        super().showEvent(event)

    def set_activity(self, title: str, subtitle: str, color_hex: str = "#00f0ff"):
        self._live_active = True
        self.who_name.setText(title)
        self.ticker_text.setText(subtitle)
        self.who_dot.setStyleSheet(f"color: {color_hex}; font-size: 11px; font-family: Segoe UI, Arial;")

    def set_backend_state(self, state: str, details: str = "") -> None:
        """Dynamically updates the intelligent status line based on real backend activity."""
        state_lower = (state or "ready").lower().strip()
        state_map = {
            "ready": ("\u25cf Ready", "#00f0ff"),
            "idle": ("\u25cf Ready", "#00f0ff"),
            "online": ("\u25cf JARVIS is online and ready", "#00f0ff"),
            "listening": ("\u25cf Listening for you", "#22d3ee"),
            "thinking": ("\u25cf Thinking...", "#a855f7"),
            "working": ("\u25cf Working on your request", "#f59e0b"),
            "executing": ("\u25cf Working on your request", "#f59e0b"),
            "speaking": ("\u25cf Speaking", "#00f0ff"),
            "success": ("\u25cf Task completed", "#10b981"),
            "task_done": ("\u25cf Task completed", "#10b981"),
            "waiting": ("\u25cf Waiting for you", "#38bdf8"),
            "waiting_user": ("\u25cf Waiting for you", "#38bdf8"),
            "question": ("\u25cf Waiting for you", "#38bdf8"),
            "approval": ("\u25cf Waiting for you", "#38bdf8"),
            "error": ("\u25cf Error encountered", "#ef4444"),
            "paused": ("\u25cf Paused", "#6b7079"),
        }
        status_text, dot_color = state_map.get(state_lower, ("\u25cf JARVIS is online and ready", "#00f0ff"))

        if state_lower in ("ready", "idle"):
            if getattr(self, "_home_kind", "time") != "time" and getattr(self, "_home_sub", ""):
                self.restore_home()
                return
            if not self._live_active or details == "online":
                status_text = "\u25cf JARVIS is online and ready"
            else:
                status_text = "\u25cf Ready"
                QTimer.singleShot(3500, self._settle_to_online)
            self._live_active = False
        else:
            self._live_active = True

        self.who_name.setText("JARVIS")
        self.who_dot.setStyleSheet(f"color: {dot_color}; font-size: 11px; font-family: Segoe UI, Arial;")
        self.ticker_text.setText(status_text)
        if hasattr(self, "mic_indicator") and self.mic_indicator:
            self.mic_indicator.set_mic_state(state_lower, details=details)

    def set_mic_state(self, state: str, is_bluetooth: Optional[bool] = None, details: str = "") -> None:
        """Explicitly sets the mic status indicator (e.g. bluetooth, unavailable, listening, ready)."""
        if hasattr(self, "mic_indicator") and self.mic_indicator:
            self.mic_indicator.set_mic_state(state, is_bluetooth=is_bluetooth, details=details)

    def _settle_to_online(self) -> None:
        """Settles '\u25cf Ready' back to '\u25cf JARVIS is online and ready' if still idle."""
        if not getattr(self, "_live_active", False) and self.ticker_text.text() == "\u25cf Ready":
            self.ticker_text.setText("\u25cf JARVIS is online and ready")
            self.who_dot.setStyleSheet("color: #00f0ff; font-size: 11px; font-family: Segoe UI, Arial;")


class CoucouApprovalCard(QWidget):
    """Coucou Approval View: Amber wash, code block, Deny (N) and Allow (Y) buttons."""

    decision_made = Signal(bool)  # True = allow, False = deny

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 6)

        self.card = WashCard(wash_color=QColor(245, 165, 36, 65))
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(12)

        self.bot_spacer = QWidget()
        self.bot_spacer.setFixedWidth(64)
        card_layout.addWidget(self.bot_spacer)

        content_col = QVBoxLayout()
        content_col.setContentsMargins(0, 0, 0, 0)
        content_col.setSpacing(6)

        who_row = QHBoxLayout()
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: #f5a524; font-size: 11px; font-family: Segoe UI, Arial;")
        who_row.addWidget(self.dot)
        self.who_label = QLabel("JARVIS needs permission")
        self.who_label.setStyleSheet("color: #8e939c; font-size: 12px; font-weight: 500; font-family: Segoe UI, Arial;")
        who_row.addWidget(self.who_label)
        who_row.addStretch()
        content_col.addLayout(who_row)

        self.code_label = QLabel("powershell -Command Remove-Item -Force cache.db")
        self.code_label.setStyleSheet("background: #0e0f11; color: #f5f6f8; font-family: 'Cascadia Mono', Consolas, monospace; font-size: 11px; padding: 5px 10px; border-radius: 8px; border: 1px solid rgba(245, 165, 36, 0.25);")
        content_col.addWidget(self.code_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.deny_btn = QPushButton("Deny  [N]")
        self.deny_btn.setCursor(Qt.PointingHandCursor)
        self.deny_btn.setStyleSheet("background: rgba(255,255,255,0.08); color: #f1f2f4; font-size: 11.5px; font-weight: 600; padding: 5px 14px; border-radius: 999px; border: none; font-family: Segoe UI, Arial;")
        self.deny_btn.clicked.connect(lambda: self.decision_made.emit(False))

        self.allow_btn = QPushButton("Allow  [Y]")
        self.allow_btn.setCursor(Qt.PointingHandCursor)
        self.allow_btn.setStyleSheet("background: #f5f6f8; color: #0b0c0e; font-size: 11.5px; font-weight: 700; padding: 5px 16px; border-radius: 999px; border: none; font-family: Segoe UI, Arial;")
        self.allow_btn.clicked.connect(lambda: self.decision_made.emit(True))

        always_btn = QPushButton("Always")
        always_btn.setCursor(Qt.PointingHandCursor)
        always_btn.setStyleSheet("background: rgba(255,255,255,0.08); color: #f1f2f4; font-size: 11.5px; font-weight: 600; padding: 5px 14px; border-radius: 999px; border: none; font-family: Segoe UI, Arial;")
        always_btn.clicked.connect(lambda: self.decision_made.emit(True))

        btn_row.addWidget(self.deny_btn)
        btn_row.addWidget(self.allow_btn)
        btn_row.addWidget(always_btn)
        btn_row.addStretch()
        content_col.addLayout(btn_row)

        card_layout.addLayout(content_col, stretch=1)
        layout.addWidget(self.card)

    def set_approval_data(self, command: str, reason: str = "JARVIS needs permission"):
        self.who_label.setText(reason)
        self.code_label.setText(command)


class CoucouQuestionCard(QWidget):
    """Coucou Question View: Cyan wash, prompt text, options."""

    option_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 6)

        self.card = WashCard(wash_color=QColor(34, 211, 238, 55))
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(12)

        self.bot_spacer = QWidget()
        self.bot_spacer.setFixedWidth(64)
        card_layout.addWidget(self.bot_spacer)

        content_col = QVBoxLayout()
        content_col.setContentsMargins(0, 0, 0, 0)
        content_col.setSpacing(6)

        who_row = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet("color: #22d3ee; font-size: 11px; font-family: Segoe UI, Arial;")
        who_row.addWidget(dot)
        self.prompt_title = QLabel("JARVIS needs an answer")
        self.prompt_title.setStyleSheet("color: #8e939c; font-size: 12px; font-weight: 500; font-family: Segoe UI, Arial;")
        who_row.addWidget(self.prompt_title)
        who_row.addStretch()
        content_col.addLayout(who_row)

        self.question_text = QLabel("Antigravity application aur website dono available hain — kaunsa kholun?")
        self.question_text.setWordWrap(True)
        self.question_text.setStyleSheet("color: #f5f6f8; font-size: 12px; font-weight: 500; font-family: Segoe UI, Arial;")
        content_col.addWidget(self.question_text)

        self.btn_row = QHBoxLayout()
        self.btn_row.setSpacing(6)
        content_col.addLayout(self.btn_row)

        card_layout.addLayout(content_col, stretch=1)
        layout.addWidget(self.card)

    def set_question(self, question: str, options: Optional[List[str]] = None):
        self.question_text.setText(question)
        while self.btn_row.count():
            item = self.btn_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        opts = options or ["Application", "Website"]
        for opt in opts:
            btn = QPushButton(opt)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("background: rgba(34, 211, 238, 0.15); color: #22d3ee; border: 1px solid rgba(34, 211, 238, 0.3); font-size: 11px; font-weight: 600; padding: 4px 14px; border-radius: 999px; font-family: Segoe UI, Arial;")
            btn.clicked.connect(lambda checked=False, o=opt: self.option_selected.emit(o))
            self.btn_row.addWidget(btn)
        self.btn_row.addStretch()


class CoucouFinishedCard(QWidget):
    """Coucou Finished View: Green wash, confirmation summary, OK button."""

    dismiss_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 6)

        self.card = WashCard(wash_color=QColor(52, 211, 153, 60))
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(12)

        self.bot_spacer = QWidget()
        self.bot_spacer.setFixedWidth(64)
        card_layout.addWidget(self.bot_spacer)

        content_col = QVBoxLayout()
        content_col.setContentsMargins(0, 0, 0, 0)
        content_col.setSpacing(6)

        who_row = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet("color: #34d399; font-size: 11px; font-family: Segoe UI, Arial;")
        who_row.addWidget(dot)
        self.summary_title = QLabel("Task Finished")
        self.summary_title.setStyleSheet("color: #8e939c; font-size: 12px; font-weight: 500; font-family: Segoe UI, Arial;")
        who_row.addWidget(self.summary_title)
        who_row.addStretch()
        content_col.addLayout(who_row)

        self.detail_text = QLabel("Chrome window launched and activated successfully.")
        self.detail_text.setStyleSheet("color: #f5f6f8; font-size: 12px; font-weight: 500; font-family: Segoe UI, Arial;")
        content_col.addWidget(self.detail_text)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setStyleSheet("background: rgba(255,255,255,0.1); color: #f5f6f8; font-size: 11.5px; font-weight: 600; padding: 4px 18px; border-radius: 999px; border: none; font-family: Segoe UI, Arial;")
        ok_btn.clicked.connect(self.dismiss_requested.emit)
        btn_row.addWidget(ok_btn)
        btn_row.addStretch()
        content_col.addLayout(btn_row)

        card_layout.addLayout(content_col, stretch=1)
        layout.addWidget(self.card)

    def set_finished_data(self, title: str, detail: str):
        self.summary_title.setText(title)
        self.detail_text.setText(detail)


class CoucouErrorCard(QWidget):
    """Coucou Error View: Red wash, error diagnosis, retry button."""

    retry_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 6)

        self.card = WashCard(wash_color=QColor(244, 80, 94, 65))
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(12)

        self.bot_spacer = QWidget()
        self.bot_spacer.setFixedWidth(64)
        card_layout.addWidget(self.bot_spacer)

        content_col = QVBoxLayout()
        content_col.setContentsMargins(0, 0, 0, 0)
        content_col.setSpacing(6)

        who_row = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet("color: #f4505e; font-size: 11px; font-family: Segoe UI, Arial;")
        who_row.addWidget(dot)
        self.error_title = QLabel("Execution Stopped")
        self.error_title.setStyleSheet("color: #8e939c; font-size: 12px; font-weight: 500; font-family: Segoe UI, Arial;")
        who_row.addWidget(self.error_title)
        who_row.addStretch()
        content_col.addLayout(who_row)

        self.detail_text = QLabel("Target application process was not found.")
        self.detail_text.setStyleSheet("color: #f5f6f8; font-size: 12px; font-weight: 500; font-family: Segoe UI, Arial;")
        content_col.addWidget(self.detail_text)

        btn_row = QHBoxLayout()
        retry_btn = QPushButton("Retry")
        retry_btn.setCursor(Qt.PointingHandCursor)
        retry_btn.setStyleSheet("background: #f4505e; color: #ffffff; font-size: 11.5px; font-weight: 600; padding: 4px 16px; border-radius: 999px; border: none; font-family: Segoe UI, Arial;")
        retry_btn.clicked.connect(self.retry_requested.emit)
        btn_row.addWidget(retry_btn)
        btn_row.addStretch()
        content_col.addLayout(btn_row)

        card_layout.addLayout(content_col, stretch=1)
        layout.addWidget(self.card)

    def set_error_data(self, title: str, detail: str):
        self.error_title.setText(title)
        self.detail_text.setText(detail)


def parse_markdown_code_blocks(text: str) -> List[dict]:
    """
    Parses conversational text into sequential markdown text and fenced code blocks.
    Returns list of dicts: {"type": "text"|"code", "lang": str, "content": str}
    """
    pattern = re.compile(r"```([a-zA-Z0-9_\-\+]*)\r?\n?(.*?)```", re.DOTALL)
    segments = []
    last_idx = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > last_idx:
            pre_text = text[last_idx:start]
            if pre_text:
                segments.append({"type": "text", "lang": "", "content": pre_text})
        lang = match.group(1).strip() or "code"
        code_content = match.group(2)
        segments.append({"type": "code", "lang": lang, "content": code_content})
        last_idx = end

    if last_idx < len(text):
        post_text = text[last_idx:]
        if post_text:
            segments.append({"type": "text", "lang": "", "content": post_text})

    if not segments:
        segments.append({"type": "text", "lang": "", "content": text})

    return segments


class CoucouMessageBubble(QFrame):
    """
    Clean Coucou message bubble with natural text selection and zero copy buttons.
    - User message: sleek right-aligned obsidian bubble (#1e2025).
    - Assistant message: left-aligned bubble (#0e0f11) with cyan gradient avatar.
    - Selectable by mouse and keyboard without any copy icons or buttons.
    """
    def __init__(self, role: str, content: str, parent=None):
        super().__init__(parent)
        self.role = role.lower()
        self.content = content
        self.setStyleSheet("background: transparent; border: none;")
        self._init_ui()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        if self.role in ("user", "you"):
            main_layout.addStretch()
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background: #1e2025;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 14px;
                }
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 6)
            card_layout.setSpacing(4)

            lbl = QLabel(self.content)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            lbl.setCursor(Qt.IBeamCursor)
            lbl.setStyleSheet("""
                QLabel {
                    background: transparent;
                    color: #f5f6f8;
                    font-size: 11.5px;
                    font-family: Segoe UI, Arial;
                    border: none;
                }
            """)
            card_layout.addWidget(lbl)
            main_layout.addWidget(card)

        else:
            # Assistant (JARVIS)
            avatar = QLabel()
            avatar.setFixedSize(20, 20)
            avatar.setAlignment(Qt.AlignCenter)
            mochi_path = os.path.join(os.path.dirname(__file__), "..", "assets", "128x128@2x.png")
            if os.path.exists(mochi_path):
                avatar.setPixmap(QPixmap(mochi_path).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            avatar.setStyleSheet("border-radius: 10px; background: transparent; border: none;")
            main_layout.addWidget(avatar, alignment=Qt.AlignTop)

            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background: #0e0f11;
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 14px;
                }
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 8)
            card_layout.setSpacing(6)

            segments = parse_markdown_code_blocks(self.content)
            for seg in segments:
                if seg["type"] == "text":
                    t = seg["content"].strip()
                    if t:
                        t_lbl = QLabel(t)
                        t_lbl.setWordWrap(True)
                        t_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
                        t_lbl.setCursor(Qt.IBeamCursor)
                        t_lbl.setStyleSheet("""
                            QLabel {
                                background: transparent;
                                color: #f5f6f8;
                                font-size: 11.5px;
                                font-family: Segoe UI, Arial;
                                line-height: 1.45;
                                border: none;
                            }
                        """)
                        card_layout.addWidget(t_lbl)
                elif seg["type"] == "code":
                    code_card = QFrame()
                    code_card.setObjectName("code_card")
                    code_card.setStyleSheet("""
                        QFrame#code_card {
                            background: #0d1117;
                            border: 1px solid rgba(255, 255, 255, 0.08);
                            border-radius: 8px;
                        }
                    """)
                    code_layout = QVBoxLayout(code_card)
                    code_layout.setContentsMargins(0, 0, 0, 0)
                    code_layout.setSpacing(0)

                    header_bar = QFrame()
                    header_bar.setStyleSheet("""
                        QFrame {
                            background: #161b22;
                            border-top-left-radius: 7px;
                            border-top-right-radius: 7px;
                            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
                        }
                    """)
                    h_bar_layout = QHBoxLayout(header_bar)
                    h_bar_layout.setContentsMargins(8, 3, 8, 3)

                    lang_lbl = QLabel(seg["lang"].upper())
                    lang_lbl.setStyleSheet("color: #8b949e; font-size: 10px; font-weight: 700; border: none; background: transparent;")
                    h_bar_layout.addWidget(lang_lbl)
                    h_bar_layout.addStretch()
                    code_layout.addWidget(header_bar)

                    c_lbl = QLabel(seg["content"].strip())
                    c_lbl.setWordWrap(False)
                    c_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
                    c_lbl.setCursor(Qt.IBeamCursor)
                    c_lbl.setStyleSheet("""
                        QLabel {
                            background: transparent;
                            color: #e6edf3;
                            font-family: Consolas, monospace;
                            font-size: 11px;
                            padding: 8px 10px;
                            border: none;
                        }
                    """)
                    code_layout.addWidget(c_lbl)
                    card_layout.addWidget(code_card)

            main_layout.addWidget(card)
            main_layout.addStretch()


class CoucouChatBrowser(QTextBrowser):
    """
    Selectable rich document browser for Coucou Dynamic Island Chat Card:
    - Native continuous mouse text selection (partial words, sentences, and multi-message spans)
    - Native Ctrl+C copying exact selected text to OS clipboard
    - Native Ctrl+A selecting full conversation text
    - Zero copy buttons, copy icons, or 'Copied' feedback
    - Protected user selection (auto-scroll safely suppressed while user is selecting text)
    - Native context menu (Copy, Select All)
    - Authentic Coucou bubble cards: #1e2025 for user (right-aligned), #0e0f11 for assistant (left-aligned)
    - Avatar stays in its own layout cell (width 28px) on the left, NEVER overlapping message text
    - Zero selectable metadata or labels (JARVIS label/avatar cannot accidentally be copied)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auto_scroll_to_bottom = True
        self.setReadOnly(True)
        self.setOpenExternalLinks(False)
        self.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        self.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.setCursor(Qt.IBeamCursor)
        self.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
                color: #f5f6f8;
                font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", -apple-system, sans-serif;
                font-size: 12px;
                selection-background-color: #22d3ee;
                selection-color: #0b0c0e;
                padding: 0px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 5px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 2px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(34, 211, 238, 0.5);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Register authentic Mochi mascot pixmap as in-memory document resource (never letter 'J')
        mochi_path = os.path.join(os.path.dirname(__file__), "..", "assets", "128x128@2x.png")
        if os.path.exists(mochi_path):
            avatar_pix = QPixmap(mochi_path).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            avatar_pix = QPixmap(20, 20)
            avatar_pix.fill(Qt.transparent)
        self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl("jarvis://avatar.png"), avatar_pix)

        vsb = self.verticalScrollBar()
        vsb.rangeChanged.connect(self._on_scroll_range_changed)
        vsb.valueChanged.connect(self._on_scroll_value_changed)

    def copy(self):
        super().copy()
        cb = QApplication.clipboard()
        if cb:
            t = cb.text()
            cleaned = t.replace("\ufffc", "").strip()
            if cleaned != t:
                cb.setText(cleaned)

    def _on_scroll_range_changed(self, min_val: int, max_val: int):
        if self._auto_scroll_to_bottom and not self.textCursor().hasSelection():
            self.verticalScrollBar().setValue(max_val)

    def _on_scroll_value_changed(self, value: int):
        if self.textCursor().hasSelection():
            self._auto_scroll_to_bottom = False
            return
        vsb = self.verticalScrollBar()
        if vsb.maximum() - value <= 50:
            self._auto_scroll_to_bottom = True
        else:
            self._auto_scroll_to_bottom = False

    def scroll_to_bottom(self, force: bool = True):
        # Auto-scroll safety: preserve active user text selection without interruption
        if self.textCursor().hasSelection():
            return
        if force:
            self._auto_scroll_to_bottom = True

        vsb = self.verticalScrollBar()
        vsb.setValue(vsb.maximum())
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

        QTimer.singleShot(10, self._deferred_scroll_to_bottom)
        QTimer.singleShot(60, self._deferred_scroll_to_bottom)
        QTimer.singleShot(180, self._deferred_scroll_to_bottom)
        QTimer.singleShot(320, self._deferred_scroll_to_bottom)

    def _deferred_scroll_to_bottom(self):
        if self._auto_scroll_to_bottom and not self.textCursor().hasSelection():
            vsb = self.verticalScrollBar()
            vsb.setValue(vsb.maximum())
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)
            self.ensureCursorVisible()

    def append_message(self, role: str, content: str):
        is_user = role.lower() in ("user", "you")
        if is_user:
            escaped_body = html.escape(content).replace("\n", "<br/>")
            html_chunk = f"""
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 8px;">
              <tr>
                <td align="right">
                  <table cellpadding="7" cellspacing="0" border="0" style="background-color: #1e2025; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 14px;">
                    <tr>
                      <td style="color: #f5f6f8; font-size: 11.5px; font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.45;">
                        {escaped_body}
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
            """
        else:
            segments = parse_markdown_code_blocks(content)
            body_parts = []
            for seg in segments:
                if seg["type"] == "text":
                    t = seg["content"]
                    if t.strip():
                        t_esc = html.escape(t).replace("\n", "<br/>")
                        body_parts.append(f'<div style="color: #f5f6f8; font-size: 11.5px; line-height: 1.45; font-family: \'Segoe UI\', Arial, sans-serif; margin-bottom: 3px;">{t_esc}</div>')
                elif seg["type"] == "code":
                    code_raw = seg["content"]
                    code_esc = html.escape(code_raw)
                    lang = seg["lang"].upper() if seg["lang"] else "CODE"
                    code_html = f"""
                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 4px 0; background-color: #0d1117; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px;">
                      <tr>
                        <td style="background-color: #161b22; padding: 3px 8px; font-size: 10px; font-weight: bold; color: #8b949e; border-bottom: 1px solid rgba(255, 255, 255, 0.06);">
                          {lang}
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 8px;">
                          <pre style="margin: 0; font-family: Consolas, monospace; font-size: 11px; color: #e6edf3; white-space: pre-wrap; word-wrap: break-word;">{code_esc}</pre>
                        </td>
                      </tr>
                    </table>
                    """
                    body_parts.append(code_html)

            body_html = "".join(body_parts)
            if not body_html.strip():
                t_esc = html.escape(content).replace("\n", "<br/>")
                body_html = f'<div style="color: #f5f6f8; font-size: 11.5px; line-height: 1.45; font-family: \'Segoe UI\', Arial, sans-serif;">{t_esc}</div>'

            html_chunk = f"""
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 8px;">
              <tr>
                <td align="left" valign="top">
                  <table cellpadding="8" cellspacing="0" border="0" style="background-color: #0e0f11; border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 14px;">
                    <tr>
                      <td style="color: #f5f6f8; font-size: 11.5px; font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.45;">
                        {body_html}
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
            """

        # Append using independent cursor to preserve user's active text selection
        has_sel = self.textCursor().hasSelection()
        saved_cursor = QTextCursor(self.textCursor()) if has_sel else None

        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html_chunk)

        if has_sel and saved_cursor:
            self.setTextCursor(saved_cursor)


class CoucouChatCard(QWidget):
    """
    Coucou Chat View: Indigo wash, native multi-message selectable text document,
    capsule input bar with circular send button, zero copy buttons, and full Ctrl+A/Ctrl+C support.
    """

    message_submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auto_scroll_to_bottom = True
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 6)

        self.card = WashCard(wash_color=QColor(99, 102, 241, 60))
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(16, 10, 16, 10)
        card_layout.setSpacing(14)

        # Bot placeholder spacer (the actual living JarvisCharacter sits in island canvas overlay)
        self.bot_spacer = QWidget()
        self.bot_spacer.setFixedWidth(64)
        card_layout.addWidget(self.bot_spacer)

        # Chat column: scrollable messages + bottom input bar
        chat_col = QVBoxLayout()
        chat_col.setContentsMargins(0, 0, 0, 0)
        chat_col.setSpacing(6)

        # Selectable rich text chat document browser
        self.chat_display = CoucouChatBrowser(self.card)
        # Expose self.scroll pointing to chat_display for backwards-compatibility with scrollbar tests
        self.scroll = self.chat_display
        chat_col.addWidget(self.chat_display, stretch=1)

        # Bookkeeping layout for tests checking bubble_layout.count()
        self.bubble_layout = QVBoxLayout()
        self.bubble_layout.addStretch()

        # Bottom Input Bar matching Coucou chat.png
        self.input_bar = QFrame()
        self.input_bar.setStyleSheet("""
            QFrame {
                background: #0e0f11;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
            }
        """)
        bar_layout = QHBoxLayout(self.input_bar)
        bar_layout.setContentsMargins(12, 3, 4, 3)
        bar_layout.setSpacing(6)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask JARVIS anything…")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #f5f6f8;
                font-size: 12px;
                font-family: Segoe UI, Arial;
            }
        """)
        self.input_field.returnPressed.connect(self._on_submit)
        bar_layout.addWidget(self.input_field, stretch=1)

        self.send_btn = QPushButton()
        self.send_btn.setIcon(create_coucou_icon("arrowUp", QColor("#0b0c0e"), 12))
        self.send_btn.setFixedSize(24, 24)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: #f5f6f8;
                border-radius: 12px;
                border: none;
            }
            QPushButton:hover {
                background: #ffffff;
            }
        """)
        self.send_btn.clicked.connect(self._on_submit)
        bar_layout.addWidget(self.send_btn)

        chat_col.addWidget(self.input_bar)
        card_layout.addLayout(chat_col, stretch=1)
        layout.addWidget(self.card)

    @property
    def character(self):
        """Returns the active Mochi/JarvisCharacter instance associated with this chat surface."""
        p = self.parent()
        while p:
            if hasattr(p, "character") and p.character is not None:
                return p.character
            p = p.parent()
        if not hasattr(self, "_fallback_char"):
            from .character import JarvisCharacter
            self._fallback_char = JarvisCharacter(self.bot_spacer, size=56)
            self._fallback_char.show()
        return self._fallback_char

    def keyPressEvent(self, event):
        """Dispatches Ctrl+A to input field if input has focus; otherwise selects chat conversation."""
        if event.matches(QKeySequence.StandardKey.SelectAll):
            if self.input_field.hasFocus():
                self.input_field.selectAll()
            else:
                self.chat_display.selectAll()
            event.accept()
            return
        super().keyPressEvent(event)

    def scroll_to_bottom(self, force: bool = True):
        self.chat_display.scroll_to_bottom(force=force)

    def showEvent(self, event):
        super().showEvent(event)
        self.scroll_to_bottom(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._auto_scroll_to_bottom:
            self.scroll_to_bottom(force=False)

    def _on_submit(self):
        text = self.input_field.text().strip()
        if text:
            self.add_message("user", text)
            self.input_field.clear()
            self.input_field.setFocus()
            self.message_submitted.emit(text)
            self.scroll_to_bottom(force=True)

    def _handle_send(self):
        self._on_submit()

    def add_message(self, role: str, content: str):
        self._auto_scroll_to_bottom = True
        self.chat_display.append_message(role, content)
        bubble = CoucouMessageBubble(role=role, content=content)
        idx = max(0, self.bubble_layout.count() - 1)
        self.bubble_layout.insertWidget(idx, bubble)
        self.scroll_to_bottom(force=True)

    def clear(self):
        self.chat_display.clear()
        while self.bubble_layout.count() > 1:
            item = self.bubble_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        try:
            from gui.sound_effects import Sound
            Sound.play("close")
        except Exception:
            pass


class CoucouDropCard(QWidget):
    """Coucou File Drop target view."""

    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 6)

        self.card = WashCard(wash_color=QColor(99, 102, 241, 40))
        self.card.setStyleSheet("""
            QFrame#wash_card {
                background: #141518;
                border: 1.5px dashed rgba(255, 255, 255, 0.15);
                border-radius: 18px;
            }
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setAlignment(Qt.AlignCenter)
        card_layout.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(create_coucou_icon("doc", QColor("#8e939c"), 24).pixmap(24, 24))
        icon_lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(icon_lbl)

        title = QLabel("Drop files or logs here")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #f5f6f8; font-size: 13px; font-weight: 600; font-family: Segoe UI, Arial;")
        card_layout.addWidget(title)

        sub = QLabel("JARVIS will inspect, summarize, or execute them automatically")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color: #8e939c; font-size: 11px; font-family: Segoe UI, Arial;")
        card_layout.addWidget(sub)

        layout.addWidget(self.card)


class AudioWaveWidget(QWidget):
    """Dynamic multi-bar audio wave visualizer responding to real microphone RMS level."""

    def __init__(self, parent=None, num_bars: int = 7, color_hex: str = "#22d3ee"):
        super().__init__(parent)
        self.num_bars = num_bars
        self.color = QColor(color_hex)
        self.level = 0.0
        self.setFixedHeight(24)
        self.setFixedWidth(num_bars * 7 + 4)

    def set_level(self, level: float):
        self.level = max(0.0, min(1.0, float(level)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w = float(self.width())
        h = float(self.height())
        bar_w = 3.0
        spacing = 6.0
        start_x = 2.0
        cy = h / 2.0

        for i in range(self.num_bars):
            dist_from_center = abs(i - (self.num_bars - 1) / 2.0)
            falloff = 1.0 - (dist_from_center * 0.18)
            bh = max(3.0, (self.level * (h - 4.0) * falloff))
            bx = start_x + i * spacing
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(self.color))
            painter.drawRoundedRect(QRectF(bx, cy - bh / 2.0, bar_w, bh), 1.5, 1.5)


class CoucouListeningCard(QWidget):
    """Coucou Listening View: Bright cyan wash, companion bot spacer, live audio visualizer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 6)

        self.card = WashCard(wash_color=QColor(34, 211, 238, 70))
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(12)

        self.bot_spacer = QWidget()
        self.bot_spacer.setFixedWidth(64)
        card_layout.addWidget(self.bot_spacer)

        content_col = QVBoxLayout()
        content_col.setContentsMargins(0, 0, 0, 0)
        content_col.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: #22d3ee; font-size: 11px;")
        title_row.addWidget(self.dot)

        self.title_lbl = QLabel("Listening...")
        self.title_lbl.setStyleSheet("color: #f5f6f8; font-size: 13px; font-weight: 700; font-family: Segoe UI, Arial;")
        title_row.addWidget(self.title_lbl)
        title_row.addStretch()

        self.wave_widget = AudioWaveWidget(color_hex="#22d3ee")
        title_row.addWidget(self.wave_widget)
        content_col.addLayout(title_row)

        self.transcript_lbl = QLabel("Speak your command freely...")
        self.transcript_lbl.setWordWrap(True)
        self.transcript_lbl.setStyleSheet("color: #9398a1; font-size: 11.5px; font-weight: 500; font-family: Segoe UI, Arial;")
        content_col.addWidget(self.transcript_lbl)
        content_col.addStretch()

        card_layout.addLayout(content_col, stretch=1)
        layout.addWidget(self.card)

    def set_audio_level(self, level: float, is_speech: bool = False):
        self.wave_widget.set_level(level)
        if is_speech:
            self.title_lbl.setText("Heard speech...")
            self.dot.setStyleSheet("color: #38bdf8; font-size: 11px;")

    def set_transcript(self, text: str):
        self.transcript_lbl.setText(text or "Speak your command freely...")


class CoucouThinkingCard(QWidget):
    """Coucou Thinking View: Violet wash, companion bot spacer, intelligent processing text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 6)

        self.card = WashCard(wash_color=QColor(168, 85, 247, 65))
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(12)

        self.bot_spacer = QWidget()
        self.bot_spacer.setFixedWidth(64)
        card_layout.addWidget(self.bot_spacer)

        content_col = QVBoxLayout()
        content_col.setContentsMargins(0, 0, 0, 0)
        content_col.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: #c084fc; font-size: 11px;")
        title_row.addWidget(self.dot)

        self.title_lbl = QLabel("Thinking...")
        self.title_lbl.setStyleSheet("color: #f5f6f8; font-size: 13px; font-weight: 700; font-family: Segoe UI, Arial;")
        title_row.addWidget(self.title_lbl)
        title_row.addStretch()
        content_col.addLayout(title_row)

        self.detail_lbl = QLabel("Analyzing intent & preparing response plan...")
        self.detail_lbl.setWordWrap(True)
        self.detail_lbl.setStyleSheet("color: #9398a1; font-size: 11.5px; font-weight: 500; font-family: Segoe UI, Arial;")
        content_col.addWidget(self.detail_lbl)
        content_col.addStretch()

        card_layout.addLayout(content_col, stretch=1)
        layout.addWidget(self.card)

    def set_thinking_text(self, text: str):
        self.detail_lbl.setText(text)


class CoucouSpeakingCard(QWidget):
    """Coucou Speaking View: Sky blue wash, companion bot spacer, live speech subtitles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 6)

        self.card = WashCard(wash_color=QColor(56, 189, 248, 65))
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(12)

        self.bot_spacer = QWidget()
        self.bot_spacer.setFixedWidth(64)
        card_layout.addWidget(self.bot_spacer)

        content_col = QVBoxLayout()
        content_col.setContentsMargins(0, 0, 0, 0)
        content_col.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: #38bdf8; font-size: 11px;")
        title_row.addWidget(self.dot)

        self.title_lbl = QLabel("JARVIS")
        self.title_lbl.setStyleSheet("color: #f5f6f8; font-size: 13px; font-weight: 700; font-family: Segoe UI, Arial;")
        title_row.addWidget(self.title_lbl)
        title_row.addStretch()

        self.wave_widget = AudioWaveWidget(color_hex="#38bdf8")
        title_row.addWidget(self.wave_widget)
        content_col.addLayout(title_row)

        self.speech_text = QLabel("")
        self.speech_text.setWordWrap(True)
        self.speech_text.setStyleSheet("color: #f5f6f8; font-size: 12px; font-weight: 500; font-family: Segoe UI, Arial;")
        content_col.addWidget(self.speech_text)
        content_col.addStretch()

        card_layout.addLayout(content_col, stretch=1)
        layout.addWidget(self.card)

    def set_spoken_text(self, text: str):
        self.speech_text.setText(text)

    def set_audio_level(self, level: float):
        self.wave_widget.set_level(level)


class CoucouSettingsCard(QWidget):
    """In-Island Settings View matching Coucou buildSettings in views.ts.

    Layout rule: labeled sections scroll inside the card while the action row
    (Done / Reset Position / Advanced) stays pinned below — so every control
    is reachable at any window/DPI scale and Done is never scrolled away.
    """

    open_advanced_requested = Signal()
    done_clicked = Signal()
    settings_saved = Signal(dict)
    sound_toggled = Signal(bool)
    volume_changed = Signal(int)
    autoclose_changed = Signal(int)
    compact_hide_changed = Signal(int)
    reset_position_requested = Signal()
    mic_setting_changed = Signal(bool)
    wake_word_changed = Signal(str)
    voice_changed = Signal(str)
    speech_speed_changed = Signal(int)
    greeting_changed = Signal(bool)
    animation_changed = Signal(str)
    accessory_changed = Signal(str)
    theme_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 6)

        self.card = WashCard()
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(12)

        self.bot_spacer = QWidget()
        self.bot_spacer.setFixedWidth(64)
        card_layout.addWidget(self.bot_spacer)

        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(4)

        # Scrollable sections (never clipped at 125%/150% DPI or small heights)
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.settings_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        settings_inner = QWidget()
        settings_inner.setStyleSheet("background: transparent;")
        content_col = QVBoxLayout(settings_inner)
        content_col.setContentsMargins(0, 0, 4, 0)
        content_col.setSpacing(3)
        self.settings_scroll.setWidget(settings_inner)
        right_col.addWidget(self.settings_scroll, stretch=1)

        def _caption(text: str) -> QLabel:
            lbl = QLabel(text.upper())
            lbl.setStyleSheet(
                "color: #5b6472; font-size: 9px; font-weight: 700; "
                "font-family: Segoe UI, Arial; letter-spacing: 1px;"
            )
            return lbl

        content_col.addWidget(_caption("Speaker"))
        # Row 1: Speaker toggle + volume slider (mirrors header speaker — same state)
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.sound_btn = QPushButton("🔊 Speaker: ON")
        self.sound_btn.setCheckable(True)
        self.sound_btn.setChecked(True)
        self.sound_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #f5f6f8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 999px;
                padding: 3px 12px;
                font-size: 11px;
                font-family: Segoe UI, Arial;
            }
            QPushButton:checked {
                background: rgba(34, 197, 94, 0.2);
                border-color: rgba(34, 197, 94, 0.4);
                color: #22c55e;
            }
        """)
        self.sound_btn.toggled.connect(self._on_sound_toggled)
        self.sound_btn.setToolTip("Speaker TTS is ON — tap to mute JARVIS voice")
        row1.addWidget(self.sound_btn)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(80)
        self.vol_slider.setFixedHeight(16)
        self.vol_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #22d3ee;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #f5f6f8;
                width: 10px;
                margin-top: -3px;
                margin-bottom: -3px;
                border-radius: 5px;
            }
        """)
        self.vol_slider.valueChanged.connect(self.volume_changed.emit)
        row1.addWidget(self.vol_slider)
        content_col.addLayout(row1)

        content_col.addWidget(_caption("Island"))
        # Row 2: Auto-close timer pills: 10s, 15s, 30s
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        timer_lbl = QLabel("Auto-close:")
        timer_lbl.setStyleSheet("color: #8e939c; font-size: 11px; font-family: Segoe UI, Arial;")
        row2.addWidget(timer_lbl)

        self._autoclose_btns = []
        for sec in (10, 15, 30):
            btn = QPushButton(f"{sec}s")
            btn.setCheckable(True)
            if sec == 15:
                btn.setChecked(True)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.06);
                    color: #8e939c;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 10px;
                    padding: 2px 8px;
                    font-size: 10.5px;
                }
                QPushButton:checked {
                    background: rgba(255, 255, 255, 0.16);
                    color: #f5f6f8;
                    font-weight: 600;
                }
            """)
            btn.clicked.connect(lambda ch=False, s=sec: self._on_autoclose_clicked(s))
            self._autoclose_btns.append(btn)
            row2.addWidget(btn)
        row2.addStretch()
        content_col.addLayout(row2)

        # Row 2c: Compact -> Hidden delay pills: 30s, 60s, 120s
        row2c = QHBoxLayout()
        row2c.setSpacing(6)
        hide_lbl = QLabel("Hide delay:")
        hide_lbl.setStyleSheet("color: #8e939c; font-size: 11px; font-family: Segoe UI, Arial;")
        row2c.addWidget(hide_lbl)

        self._hide_delay_btns = []
        for sec in (30, 60, 120):
            h_btn = QPushButton(f"{sec}s")
            h_btn.setCheckable(True)
            if sec == 60:
                h_btn.setChecked(True)
            h_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.06);
                    color: #8e939c;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 10px;
                    padding: 2px 8px;
                    font-size: 10.5px;
                }
                QPushButton:checked {
                    background: rgba(255, 255, 255, 0.16);
                    color: #f5f6f8;
                    font-weight: 600;
                }
            """)
            h_btn.clicked.connect(lambda ch=False, s=sec: self._on_hide_delay_clicked(s))
            self._hide_delay_btns.append(h_btn)
            row2c.addWidget(h_btn)
        row2c.addStretch()
        content_col.addLayout(row2c)

        # Voice input: mic master mirror + wake word
        content_col.addWidget(_caption("Voice input"))
        row2b = QHBoxLayout()
        row2b.setSpacing(6)
        lbl_style = "color: #8e939c; font-size: 10.5px; font-family: Segoe UI, Arial;"
        self.mic_check = QPushButton("🎙️ Mic: ON")
        self.mic_check.setCheckable(True)
        self.mic_check.setChecked(True)
        self.mic_check.setFixedHeight(20)
        self.mic_check.setStyleSheet("QPushButton{font-size:10.5px;color:#22d3ee;background:rgba(34,211,238,.12);border:1px solid rgba(34,211,238,.3);border-radius:8px;padding:1px 8px;}QPushButton:checked{color:#22d3ee;}QPushButton:!checked{color:#64748b;}")
        self.mic_check.toggled.connect(lambda c: (self.mic_check.setText("🎙️ Mic: ON" if c else "🎙️ Mic: OFF"), self.mic_setting_changed.emit(bool(c))))
        self.mic_check.setToolTip("Microphone master switch (mirrors header mic)")
        row2b.addWidget(self.mic_check)
        wake_lbl = QLabel("Wake:")
        wake_lbl.setStyleSheet(lbl_style)
        row2b.addWidget(wake_lbl)
        self.wake_edit = QLineEdit()
        self.wake_edit.setPlaceholderText("jarvis")
        self.wake_edit.setFixedWidth(70)
        self.wake_edit.setFixedHeight(20)
        self.wake_edit.setStyleSheet("QLineEdit{background:#0e0f11;color:#f5f6f8;border:1px solid rgba(255,255,255,.1);border-radius:8px;font-size:10.5px;padding:0 6px;}")
        self.wake_edit.editingFinished.connect(lambda: self.wake_word_changed.emit(self.wake_edit.text().strip()))
        row2b.addWidget(self.wake_edit)
        row2b.addStretch()
        content_col.addLayout(row2b)

        # Speech rate with live value readout (was crammed into the row above)
        row2b2 = QHBoxLayout()
        row2b2.setSpacing(6)
        spd_lbl = QLabel("Speed:")
        spd_lbl.setStyleSheet(lbl_style)
        row2b2.addWidget(spd_lbl)
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(50, 200)
        self.speed_slider.setValue(100)
        self.speed_slider.setFixedWidth(110)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        row2b2.addWidget(self.speed_slider)
        self.speed_value = QLabel("100%")
        self.speed_value.setFixedWidth(38)
        self.speed_value.setStyleSheet(lbl_style)
        row2b2.addWidget(self.speed_value)
        row2b2.addStretch()
        content_col.addLayout(row2b2)

        # Appearance — accessory / animation / theme / greeting (spec §11-12)
        content_col.addWidget(_caption("Appearance"))
        row2c = QHBoxLayout()
        row2c.setSpacing(6)
        acc_lbl = QLabel("Style:")
        acc_lbl.setStyleSheet(lbl_style)
        row2c.addWidget(acc_lbl)

        def _fill_combo(combo, values, signal):
            """Pretty display text, raw snake_case value, readable popup list."""
            for value in values:
                combo.addItem(value.replace("_", " ").title(), value)
            combo.setFixedHeight(20)
            combo.setStyleSheet(
                "QComboBox{background:#0e0f11;color:#f5f6f8;font-size:10.5px;"
                "border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:1px 4px;}"
                "QComboBox QAbstractItemView{background:#1a1c21;color:#f5f6f8;"
                "selection-background-color:rgba(34,211,238,.25);"
                "selection-color:#ffffff;outline:0;border:1px solid rgba(255,255,255,.12);}"
            )
            try:
                combo.view().setMinimumWidth(150)
            except Exception:
                pass
            combo.currentIndexChanged.connect(
                lambda idx, cb=combo, sig=signal: sig.emit(cb.itemData(idx)))

        self.accessory_combo = QComboBox()
        _fill_combo(self.accessory_combo,
                    ["none", "beanie", "santa_hat", "party_hat", "crown", "witch_hat",
                     "sunglasses", "round_glasses", "scarf", "pumpkin", "bow"],
                    self.accessory_changed)
        row2c.addWidget(self.accessory_combo)
        self.anim_combo = QComboBox()
        _fill_combo(self.anim_combo, ["calm", "normal", "lively"], self.animation_changed)
        self.anim_combo.setCurrentIndex(1)  # normal
        row2c.addWidget(self.anim_combo)
        self.theme_combo = QComboBox()
        _fill_combo(self.theme_combo, ["dark", "darker"], self.theme_changed)
        row2c.addWidget(self.theme_combo)
        self.greet_check = QPushButton("👋 Greet: ON")
        self.greet_check.setCheckable(True)
        self.greet_check.setChecked(True)
        self.greet_check.setFixedHeight(20)
        self.greet_check.setStyleSheet("QPushButton{font-size:10.5px;color:#22c55e;background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.3);border-radius:8px;padding:1px 8px;}QPushButton:!checked{color:#64748b;}")
        self.greet_check.toggled.connect(lambda c: (self.greet_check.setText("👋 Greet: ON" if c else "👋 Greet: OFF"), self.greeting_changed.emit(bool(c))))
        row2c.addWidget(self.greet_check)
        row2c.addStretch()
        content_col.addLayout(row2c)
        content_col.addStretch()

        # Pinned action row — always visible below the scroll, never scrolled away
        row3 = QHBoxLayout()
        row3.setSpacing(10)

        self.done_btn = QPushButton("Done")
        self.done_btn.setCursor(Qt.PointingHandCursor)
        self.done_btn.setStyleSheet("""
            QPushButton {
                background: rgba(34, 211, 238, 0.15);
                color: #22d3ee;
                border: 1px solid rgba(34, 211, 238, 0.35);
                border-radius: 10px;
                padding: 3px 14px;
                font-size: 11px;
                font-weight: 600;
                font-family: Segoe UI, Arial;
            }
            QPushButton:hover {
                background: rgba(34, 211, 238, 0.25);
                color: #38bdf8;
            }
        """)
        self.done_btn.clicked.connect(self._on_done_clicked)
        row3.addWidget(self.done_btn)

        # Reset JARVIS Anchor Position Button
        self.reset_pos_btn = QPushButton("Reset Position")
        self.reset_pos_btn.setCursor(Qt.PointingHandCursor)
        self.reset_pos_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #f5f6f8;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
                padding: 3px 12px;
                font-size: 11px;
                font-family: Segoe UI, Arial;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.16);
                color: #22d3ee;
                border-color: rgba(34, 211, 238, 0.4);
            }
        """)
        self.reset_pos_btn.clicked.connect(self.reset_position_requested.emit)
        row3.addWidget(self.reset_pos_btn)

        # Advanced Settings Link
        adv_btn = QPushButton("Advanced Studio...")
        adv_btn.setCursor(Qt.PointingHandCursor)
        adv_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #22d3ee;
                font-size: 11px;
                font-weight: 600;
                text-decoration: underline;
                font-family: Segoe UI, Arial;
            }
            QPushButton:hover {
                color: #38bdf8;
            }
        """)
        adv_btn.clicked.connect(self.open_advanced_requested.emit)
        row3.addWidget(adv_btn)
        row3.addStretch()
        right_col.addLayout(row3)

        card_layout.addLayout(right_col, stretch=1)
        layout.addWidget(self.card)

    def _on_hide_delay_clicked(self, sec: int):
        for btn in getattr(self, "_hide_delay_btns", []):
            btn.setChecked(btn.text() == f"{sec}s")
        self.compact_hide_changed.emit(sec)

    def _on_speed_changed(self, value: int):
        self.speed_value.setText(f"{int(value)}%")
        self.speech_speed_changed.emit(int(value))

    def _on_sound_toggled(self, checked: bool):
        self.sound_btn.setText("🔊 Speaker: ON" if checked else "🔇 Speaker: OFF")
        self.sound_btn.setToolTip(
            "Speaker TTS is ON — tap to mute JARVIS voice" if checked
            else "Speaker TTS is MUTED — tap to unmute JARVIS voice"
        )
        self.sound_toggled.emit(checked)

    def set_mic_state(self, enabled: bool) -> None:
        """Mirrors the header master mic switch without re-emitting (no loops)."""
        try:
            self.mic_check.blockSignals(True)
            self.mic_check.setChecked(bool(enabled))
            self.mic_check.setText("🎙️ Mic: ON" if enabled else "🎙️ Mic: OFF")
            self.mic_check.setToolTip(
                "Microphone is ON (master switch mirrored from header)" if enabled
                else "Microphone is OFF (master switch mirrored from header)"
            )
        finally:
            self.mic_check.blockSignals(False)

    def set_speaker_state(self, enabled: bool) -> None:
        """Mirrors the header speaker switch without re-emitting (no loops)."""
        try:
            self.sound_btn.blockSignals(True)
            self.sound_btn.setChecked(bool(enabled))
            self.sound_btn.setText("🔊 Speaker: ON" if enabled else "🔇 Speaker: OFF")
            self.sound_btn.setToolTip(
                "Speaker TTS is ON — tap to mute JARVIS voice" if enabled
                else "Speaker TTS is MUTED — tap to unmute JARVIS voice"
            )
        finally:
            self.sound_btn.blockSignals(False)

    def _on_autoclose_clicked(self, sec: int):
        for btn in getattr(self, "_autoclose_btns", []):
            btn.setChecked(btn.text() == f"{sec}s")
        self.autoclose_changed.emit(sec)

    def get_autoclose(self) -> int:
        for btn in getattr(self, "_autoclose_btns", []):
            if btn.isChecked():
                try:
                    return int(btn.text().replace("s", ""))
                except Exception:
                    pass
        return 15

    def set_autoclose(self, sec: int):
        for btn in getattr(self, "_autoclose_btns", []):
            btn.setChecked(btn.text() == f"{sec}s")

    def get_hide_delay(self) -> int:
        for btn in getattr(self, "_hide_delay_btns", []):
            if btn.isChecked():
                try:
                    return int(btn.text().replace("s", ""))
                except Exception:
                    pass
        return 60

    def set_hide_delay(self, sec: int):
        for btn in getattr(self, "_hide_delay_btns", []):
            btn.setChecked(btn.text() == f"{sec}s")

    def get_settings(self) -> dict:
        """Returns snapshot dictionary of all current settings controls."""
        return {
            "sound_enabled": bool(self.sound_btn.isChecked()),
            "sound_volume": int(self.vol_slider.value()),
            "auto_close_sec": self.get_autoclose(),
            "hide_delay_sec": self.get_hide_delay(),
            "mic_enabled": bool(self.mic_check.isChecked()),
            "wake_word": self.wake_edit.text().strip() or "jarvis",
            "speech_speed": int(self.speed_slider.value()),
            "accessory": str(self.accessory_combo.currentData() or "none").lower(),
            "animation": str(self.anim_combo.currentData() or "normal").lower(),
            "theme": str(self.theme_combo.currentData() or "dark").lower(),
            "greeting_enabled": bool(self.greet_check.isChecked()),
        }

    def set_settings(self, data: dict) -> None:
        """Populates all UI controls from a dictionary without spurious event loops."""
        if not isinstance(data, dict):
            return

        if "sound_enabled" in data:
            self.set_speaker_state(bool(data["sound_enabled"]))

        if "sound_volume" in data:
            try:
                val = max(0, min(100, int(data["sound_volume"])))
                self.vol_slider.blockSignals(True)
                self.vol_slider.setValue(val)
                self.vol_slider.blockSignals(False)
            except Exception:
                pass

        if "auto_close_sec" in data:
            try:
                self.set_autoclose(int(data["auto_close_sec"]))
            except Exception:
                pass

        if "hide_delay_sec" in data:
            try:
                self.set_hide_delay(int(data["hide_delay_sec"]))
            except Exception:
                pass

        if "mic_enabled" in data:
            self.set_mic_state(bool(data["mic_enabled"]))

        if "wake_word" in data:
            try:
                self.wake_edit.blockSignals(True)
                self.wake_edit.setText(str(data["wake_word"]))
                self.wake_edit.blockSignals(False)
            except Exception:
                pass

        if "speech_speed" in data:
            try:
                val = max(50, min(200, int(data["speech_speed"])))
                self.speed_slider.blockSignals(True)
                self.speed_slider.setValue(val)
                self.speed_value.setText(f"{val}%")
                self.speed_slider.blockSignals(False)
            except Exception:
                pass

        if "accessory" in data:
            try:
                acc = str(data["accessory"]).lower()
                idx = self.accessory_combo.findData(acc)
                if idx >= 0:
                    self.accessory_combo.blockSignals(True)
                    self.accessory_combo.setCurrentIndex(idx)
                    self.accessory_combo.blockSignals(False)
            except Exception:
                pass

        if "animation" in data:
            try:
                anim = str(data["animation"]).lower()
                idx = self.anim_combo.findData(anim)
                if idx >= 0:
                    self.anim_combo.blockSignals(True)
                    self.anim_combo.setCurrentIndex(idx)
                    self.anim_combo.blockSignals(False)
            except Exception:
                pass

        if "theme" in data:
            try:
                thm = str(data["theme"]).lower()
                idx = self.theme_combo.findData(thm)
                if idx >= 0:
                    self.theme_combo.blockSignals(True)
                    self.theme_combo.setCurrentIndex(idx)
                    self.theme_combo.blockSignals(False)
            except Exception:
                pass

        if "greeting_enabled" in data:
            try:
                en = bool(data["greeting_enabled"])
                self.greet_check.blockSignals(True)
                self.greet_check.setChecked(en)
                self.greet_check.setText("👋 Greet: ON" if en else "👋 Greet: OFF")
                self.greet_check.blockSignals(False)
            except Exception:
                pass

    def _resolve_config_path(self, config_path: Optional[str] = None) -> str:
        if config_path and os.path.exists(config_path):
            return config_path
        if getattr(self, "config_path", None) and os.path.exists(self.config_path):
            return self.config_path
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        cand = os.path.join(root, "config.yaml")
        if os.path.exists(cand):
            return cand
        return "config.yaml"

    def save_settings(self, config_path: Optional[str] = None) -> dict:
        """Persists all island settings into config.yaml and external appearance store."""
        import json
        import yaml
        import logging
        _logger = logging.getLogger("jarvis.gui.island.settings")

        data = self.get_settings()
        target_path = self._resolve_config_path(config_path)

        # 1. Update config.yaml
        cfg = {}
        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            except Exception as e:
                _logger.debug(f"[SETTINGS] Failed to read config from {target_path}: {e}")
                cfg = {}

        sound_sec = cfg.setdefault("sound", {})
        sound_sec["enabled"] = bool(data["sound_enabled"])
        sound_sec["volume"] = int(data["sound_volume"])

        voice_sec = cfg.setdefault("voice", {})
        voice_sec["enabled"] = bool(data["mic_enabled"])
        voice_sec["speed"] = int(data["speech_speed"])

        sys_sec = cfg.setdefault("system", {})
        wake = str(data["wake_word"]).strip() or "jarvis"
        existing_wakes = sys_sec.get("wake_words", [])
        if not isinstance(existing_wakes, list):
            existing_wakes = []
        new_wakes = [wake]
        for w in (f"hey {wake}", f"ok {wake}"):
            if w not in new_wakes:
                new_wakes.append(w)
        for w in existing_wakes:
            if w not in new_wakes:
                new_wakes.append(w)
        sys_sec["wake_words"] = new_wakes

        isl_sec = cfg.setdefault("island", {})
        isl_sec["auto_close_sec"] = int(data["auto_close_sec"])
        isl_sec["hide_delay_sec"] = int(data["hide_delay_sec"])
        isl_sec["accessory"] = str(data["accessory"])
        isl_sec["animation"] = str(data["animation"])
        isl_sec["theme"] = str(data["theme"])
        isl_sec["greeting_enabled"] = bool(data["greeting_enabled"])

        try:
            with open(target_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
            _logger.info(f"[SETTINGS] Successfully saved settings to {target_path}")
        except Exception as exc:
            _logger.error(f"[SETTINGS] Failed to write settings to {target_path}: {exc}")

        # 2. Sync appearance JSON
        try:
            from .accessories import _default_storage_path
            acc_store = _default_storage_path()
            with open(acc_store, "w", encoding="utf-8") as af:
                json.dump({"accessory": data["accessory"]}, af, indent=2)
        except Exception as exc:
            _logger.debug(f"[SETTINGS] Failed to write appearance json: {exc}")

        self.settings_saved.emit(data)
        return data

    def _on_done_clicked(self):
        """Saves all settings to config.yaml and disk, provides visual confirmation, and emits done."""
        import logging
        _logger = logging.getLogger("jarvis.gui.island.settings")
        try:
            self.save_settings()
        except Exception as e:
            _logger.debug(f"[SETTINGS] Save on Done failed: {e}")

        # Visual feedback: Done button morphs into vibrant green "✓ Saved!"
        orig_text = self.done_btn.text()
        orig_style = self.done_btn.styleSheet()
        try:
            self.done_btn.setText("✓ Saved!")
        except Exception:
            pass

        self.done_clicked.emit()

        def _reset_btn():
            try:
                self.done_btn.setText(orig_text)
                self.done_btn.setStyleSheet(orig_style)
            except Exception:
                pass

        QTimer.singleShot(400, _reset_btn)


