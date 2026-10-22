# gui/island/pills.py
"""Compact Status and Tool Pills for JARVIS Island.

Features:
- StatusPill: Displays dynamic state (READY, LISTENING, THINKING, EXECUTING, SUCCESS, ERROR)
- ToolPill: Context-aware active tool badges (Browser, Calendar, Files, Workflows, Plugins)
- ActiveAppPill: Non-intrusive foreground context pill (e.g. Chrome, VS Code)
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


class StatusPill(QFrame):
    """Compact status pill with color, icon, and text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("island_status_pill")
        self._init_ui()

    def _init_ui(self):
        self.setFixedHeight(28)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 10, 3)
        layout.setSpacing(0)

        self.label = QLabel("● READY")
        self.label.setObjectName("status_badge")
        self.label.setStyleSheet("color: #22c55e; font-size: 11px; font-weight: 700; background: transparent; border: none;")
        layout.addWidget(self.label)

        self.setStyleSheet("""
            QFrame#island_status_pill {
                background-color: #111215;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)

    def set_status(self, text: str, state: str = "ready") -> None:
        state_colors = {
            "ready": "#22c55e",
            "listening": "#22d3ee",
            "thinking": "#a78bfa",
            "processing": "#818cf8",
            "executing": "#60a5fa",
            "speaking": "#38bdf8",
            "success": "#22c55e",
            "warning": "#f5a524",
            "error": "#f4505e",
            "offline": "#6b7079",
            "paused": "#9398a1",
        }
        color = state_colors.get(state.lower(), "#22c55e")
        if not text.startswith("●"):
            clean_text = text.upper()
            formatted = f"● {clean_text}"
        else:
            formatted = text
        self.label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 700;")
        self.label.setText(formatted)
        self.label.setProperty("state", state.lower())


class ToolPill(QPushButton):
    """Context-aware tool and capability capsule pill."""

    def __init__(self, label: str, icon: str = "⚡", color: str = "#22d3ee", parent=None):
        super().__init__(parent)
        self._color = color
        self.setText(f"{icon}  {label}")
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style("ready")

    def _apply_style(self, status: str = "ready") -> None:
        border_color = f"{self._color}40"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: #141518;
                color: #d1d5db;
                border: 1px solid {border_color};
                border-radius: 999px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {self._color}22;
                border-color: {self._color}88;
                color: #ffffff;
            }}
        """)


class ActiveAppPill(QFrame):
    """Subtle foreground context pill shown only when relevant."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 8, 2)
        layout.setSpacing(4)

        self.icon_lbl = QLabel("🪟")
        self.icon_lbl.setStyleSheet("font-size: 10px;")
        layout.addWidget(self.icon_lbl)

        self.name_lbl = QLabel("")
        self.name_lbl.setStyleSheet("color: #9398a1; font-size: 10.5px; font-weight: 500;")
        layout.addWidget(self.name_lbl)

        self.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 999px;
        """)
        self.setVisible(False)

    def set_app(self, app_name: Optional[str]) -> None:
        if app_name and app_name.strip():
            self.name_lbl.setText(app_name.strip())
            self.setVisible(True)
        else:
            self.setVisible(False)
