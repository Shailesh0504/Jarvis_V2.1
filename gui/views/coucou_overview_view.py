# gui/views/coucou_overview_view.py
"""Coucou Overview Card View for Jarvis V2.

Faithfully implements Coucou's signature two-card overview layout:
- Left Card:
  - AgentWho row (colored dot, 'Jarvis V2.1', step count)
  - Live Action / Thought Ticker
  - Coucou Approval Box (Deny / Allow with shortcuts 'N' and 'Y')
  - Quick Ask / Prompt Bar with Voice Mic Pulse & Circular Send Arrow
- Right Card:
  - Integrations & Capabilities Mini-Pill Grid with colored dots
  - Clicking any mini-pill smoothly navigates to that capability view
"""

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget
)

from gui.sound_effects import Sound


class CoucouOverviewView(QWidget):
    """Coucou Signature 2-Column Overview Card."""

    open_capability = Signal(int)
    message_submitted = Signal(str)
    voice_toggle_requested = Signal()
    approval_decided = Signal(str)  # "allow" or "deny"

    def __init__(self, core=None, parent=None):
        super().__init__(parent)
        self.core = core
        self._current_step_text = "Online and ready. Say 'Jarvis' or type a command."
        self._step_count = "1/1"
        self._pending_approval_action = None

        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # ── Left Card: Live Session & Execution Ticker + Quick Ask ──────────
        self.left_card = QFrame()
        self.left_card.setObjectName("coucou_left_card")
        self.left_card.setStyleSheet("""
            QFrame#coucou_left_card {
                background-color: #141518;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 16px;
            }
        """)
        left_layout = QVBoxLayout(self.left_card)
        left_layout.setContentsMargins(14, 12, 14, 12)
        left_layout.setSpacing(10)

        # Header: Agent Who (Colored dot, name, badge)
        who_row = QHBoxLayout()
        who_row.setSpacing(8)

        self.agent_dot = QLabel("●")
        self.agent_dot.setStyleSheet("color: #22c55e; font-size: 11px;")
        who_row.addWidget(self.agent_dot)

        self.agent_name = QLabel("Jarvis V2.1")
        self.agent_name.setStyleSheet("font-weight: 700; font-size: 13px; color: #f5f6f8;")
        who_row.addWidget(self.agent_name)

        self.tool_label = QLabel("Cognitive Companion")
        self.tool_label.setStyleSheet("color: #6b7079; font-size: 11px; font-weight: 500;")
        who_row.addWidget(self.tool_label)

        who_row.addStretch()

        self.count_badge = QLabel(self._step_count)
        self.count_badge.setStyleSheet("""
            color: #9398a1;
            font-size: 11px;
            font-weight: 600;
            background: rgba(255, 255, 255, 0.05);
            padding: 2px 8px;
            border-radius: 999px;
        """)
        who_row.addWidget(self.count_badge)

        left_layout.addLayout(who_row)

        # Live Action & Thought Ticker Box
        self.ticker_box = QFrame()
        self.ticker_box.setStyleSheet("""
            background-color: #0e0f11;
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 10px;
            padding: 10px;
        """)
        ticker_layout = QVBoxLayout(self.ticker_box)
        ticker_layout.setContentsMargins(10, 8, 10, 8)
        ticker_layout.setSpacing(4)

        ticker_title = QLabel("CURRENT SESSION ACTIVITY")
        ticker_title.setStyleSheet("color: #6b7079; font-size: 9.5px; font-weight: 700; letter-spacing: 0.8px;")
        ticker_layout.addWidget(ticker_title)

        self.ticker_label = QLabel(self._current_step_text)
        self.ticker_label.setWordWrap(True)
        self.ticker_label.setStyleSheet("color: #f1f2f4; font-size: 12.5px; font-weight: 500; line-height: 1.4;")
        ticker_layout.addWidget(self.ticker_label)

        left_layout.addWidget(self.ticker_box, stretch=1)

        # Coucou Signature Approval Box (hidden by default)
        self.approval_box = QFrame()
        self.approval_box.setObjectName("approval_box")
        self.approval_box.setStyleSheet("""
            QFrame#approval_box {
                background-color: rgba(245, 165, 36, 0.12);
                border: 1px solid rgba(245, 165, 36, 0.4);
                border-radius: 12px;
                padding: 10px;
            }
        """)
        approval_layout = QVBoxLayout(self.approval_box)
        approval_layout.setContentsMargins(10, 8, 10, 8)
        approval_layout.setSpacing(8)

        self.approval_desc = QLabel("Permission Required")
        self.approval_desc.setStyleSheet("color: #f5a524; font-weight: 700; font-size: 12px;")
        approval_layout.addWidget(self.approval_desc)

        self.approval_cmd = QLabel("")
        self.approval_cmd.setStyleSheet("color: #f5f6f8; font-family: monospace; font-size: 11px; background: rgba(0,0,0,0.3); padding: 4px 8px; border-radius: 6px;")
        approval_layout.addWidget(self.approval_cmd)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.deny_btn = QPushButton("Deny  (N)")
        self.deny_btn.setCursor(Qt.PointingHandCursor)
        self.deny_btn.setStyleSheet("""
            QPushButton {
                background: #1d1f23;
                color: #f4505e;
                border: 1px solid rgba(244, 80, 94, 0.4);
                border-radius: 8px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(244, 80, 94, 0.2);
            }
        """)
        self.deny_btn.clicked.connect(lambda: self._on_approval_decision("deny"))
        btn_row.addWidget(self.deny_btn)

        self.allow_btn = QPushButton("Allow  (Y)")
        self.allow_btn.setCursor(Qt.PointingHandCursor)
        self.allow_btn.setStyleSheet("""
            QPushButton {
                background: #22c55e;
                color: #000000;
                border: none;
                border-radius: 8px;
                padding: 6px 16px;
                font-weight: 700;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #16a34a;
            }
        """)
        self.allow_btn.clicked.connect(lambda: self._on_approval_decision("allow"))
        btn_row.addWidget(self.allow_btn)

        approval_layout.addLayout(btn_row)
        self.approval_box.setVisible(False)
        left_layout.addWidget(self.approval_box)

        # Quick Ask / Prompt Bar
        prompt_bar = QHBoxLayout()
        prompt_bar.setSpacing(8)

        self.voice_btn = QPushButton("🎙️")
        self.voice_btn.setToolTip("Toggle Voice Listening")
        self.voice_btn.setCursor(Qt.PointingHandCursor)
        self.voice_btn.setFixedSize(34, 34)
        self.voice_btn.setStyleSheet("""
            QPushButton {
                background-color: #1d1f23;
                color: #22d3ee;
                border: 1px solid rgba(34, 211, 238, 0.3);
                border-radius: 17px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(34, 211, 238, 0.2);
            }
        """)
        self.voice_btn.clicked.connect(self._on_voice_clicked)
        prompt_bar.addWidget(self.voice_btn)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask Jarvis anything or speak…")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #0e0f11;
                color: #f5f6f8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 17px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #22d3ee;
            }
        """)
        self.input_field.returnPressed.connect(self._on_submit)
        prompt_bar.addWidget(self.input_field)

        self.send_btn = QPushButton("↑")
        self.send_btn.setToolTip("Send Prompt")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setFixedSize(34, 34)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #f5f6f8;
                color: #0b0c0e;
                border: none;
                border-radius: 17px;
                font-size: 16px;
                font-weight: 800;
            }
            QPushButton:hover {
                background-color: #22d3ee;
                color: #000000;
            }
        """)
        self.send_btn.clicked.connect(self._on_submit)
        prompt_bar.addWidget(self.send_btn)

        left_layout.addLayout(prompt_bar)

        layout.addWidget(self.left_card, stretch=6)

        # ── Right Card: Mini-Pill Integrations Grid ─────────────────────────
        self.right_card = QFrame()
        self.right_card.setObjectName("coucou_right_card")
        self.right_card.setStyleSheet("""
            QFrame#coucou_right_card {
                background-color: #141518;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 16px;
            }
        """)
        right_layout = QVBoxLayout(self.right_card)
        right_layout.setContentsMargins(14, 12, 14, 12)
        right_layout.setSpacing(10)

        right_title = QLabel("CAPABILITIES & TOOLS")
        right_title.setStyleSheet("color: #6b7079; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        right_layout.addWidget(right_title)

        # Grid of mini pills
        grid = QGridLayout()
        grid.setSpacing(8)

        pills = [
            ("🌐 Websites & Web", "#22d3ee", 2),
            ("🧩 Plugins Hub", "#a855f7", 3),
            ("🧠 Memory System", "#ec4899", 4),
            ("🎓 Learning Core", "#8b5cf6", 5),
            ("⚡ Workflows", "#f5a524", 6),
            ("⏰ Reminders", "#f43f5e", 7),
            ("📝 Activity Log", "#64748b", 8),
            ("⚙️ Settings", "#94a3b8", 9),
            ("📰 Live News", "#3b82f6", 10),
            ("📈 Stocks Intel", "#10b981", 11),
            ("📊 Dashboard", "#14b8a6", 0),
        ]

        row = 0
        col = 0
        for label, color, view_idx in pills:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #0e0f11;
                    color: #d1d5db;
                    border: 1px solid {color}33;
                    border-radius: 10px;
                    padding: 8px 10px;
                    font-size: 11px;
                    font-weight: 600;
                    text-align: left;
                }}
                QPushButton:hover {{
                    background-color: {color}1f;
                    border-color: {color}99;
                    color: #f5f6f8;
                }}
            """)
            btn.clicked.connect(lambda checked=False, i=view_idx: self._on_pill_clicked(i))
            grid.addWidget(btn, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

        right_layout.addLayout(grid)
        right_layout.addStretch()

        layout.addWidget(self.right_card, stretch=5)

    def _on_pill_clicked(self, view_idx: int):
        Sound.play("blip")
        self.open_capability.emit(view_idx)

    def _on_submit(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        Sound.play("send")
        self.message_submitted.emit(text)

    def _on_voice_clicked(self):
        Sound.play("peek")
        self.voice_toggle_requested.emit()

    def _on_approval_decision(self, decision: str):
        if decision == "allow":
            Sound.play("approve")
        else:
            Sound.play("close")
        self.approval_box.setVisible(False)
        self.approval_decided.emit(decision)

    def set_ticker_step(self, text: str, step_index: int = 1, total_steps: int = 1):
        """Updates the live action and thought ticker."""
        self._current_step_text = text
        self.ticker_label.setText(text)
        self._step_count = f"{step_index}/{max(total_steps, step_index)}"
        self.count_badge.setText(self._step_count)

    def show_approval(self, action_text: str, command: str = ""):
        """Shows the Coucou signature approval card."""
        Sound.play("approval")
        self.approval_desc.setText(f"Permission Request: {action_text}")
        self.approval_cmd.setText(command or action_text)
        self.approval_box.setVisible(True)

    def hide_approval(self):
        """Hides the approval card."""
        self.approval_box.setVisible(False)

    def set_system_state(self, state: str):
        """Reflects system state in the agent dot and left card."""
        colors = {
            "ready": "#22c55e",
            "listening": "#22d3ee",
            "thinking": "#8b5cf6",
            "executing": "#3b82f6",
            "speaking": "#c084fc",
            "error": "#f4505e",
            "paused": "#6b7079",
        }
        color = colors.get(state, "#22c55e")
        self.agent_dot.setStyleSheet(f"color: {color}; font-size: 11px;")
