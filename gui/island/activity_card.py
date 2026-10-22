# gui/island/activity_card.py
"""Compact Activity and Multi-Step Workflow Card for JARVIS Island.

Features:
- Single-step live action ticker (e.g. ◉ Opening Chrome -> ✓ Chrome opened)
- Multi-step workflow view: prominently highlights current step while keeping completed steps quieter
- Zero technical log dumps or stack traces
"""

from typing import List, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class ActivityCard(QFrame):
    """Compact activity execution and multi-step task card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("island_activity_card")
        self._init_ui()

    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 10)
        self.layout.setSpacing(6)

        # Header: Action Title / Goal
        self.title_lbl = QLabel("Action in progress")
        self.title_lbl.setStyleSheet("color: #f5f6f8; font-size: 12.5px; font-weight: 700;")
        self.layout.addWidget(self.title_lbl)

        # Active Step Box
        self.step_box = QFrame()
        self.step_box.setStyleSheet("""
            background-color: #0e0f11;
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 8px;
        """)
        step_layout = QVBoxLayout(self.step_box)
        step_layout.setContentsMargins(6, 4, 6, 4)
        step_layout.setSpacing(4)

        self.step_container = QVBoxLayout()
        self.step_container.setSpacing(3)
        step_layout.addLayout(self.step_container)
        self.layout.addWidget(self.step_box)

        self.setStyleSheet("""
            QFrame#island_activity_card {
                background-color: #141518;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 14px;
            }
        """)

    def set_single_action(self, action_text: str, is_completed: bool = False) -> None:
        """Sets a single-step action execution status."""
        self.title_lbl.setText("Current Activity")
        self._clear_steps()

        row = QHBoxLayout()
        row.setSpacing(6)

        icon = "✓" if is_completed else "●"
        icon_color = "#22c55e" if is_completed else "#38bdf8"
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"color: {icon_color}; font-weight: 800; font-size: 11px;")
        row.addWidget(icon_lbl)

        text_lbl = QLabel(action_text)
        text_lbl.setStyleSheet("color: #f5f6f8; font-size: 12px; font-weight: 500;")
        row.addWidget(text_lbl, stretch=1)

        step_widget = QWidget()
        step_widget.setLayout(row)
        self.step_container.addWidget(step_widget)

    def set_workflow_steps(self, title: str, steps: List[str], current_index: int = 0) -> None:
        """Renders multi-step workflow with prominent active step and quiet completed steps."""
        self.title_lbl.setText(title or "Workflow Execution")
        self._clear_steps()

        for idx, step_name in enumerate(steps):
            row = QHBoxLayout()
            row.setSpacing(6)

            if idx < current_index:
                # Completed step
                icon_lbl = QLabel("✓")
                icon_lbl.setStyleSheet("color: #22c55e; font-size: 10px; font-weight: 700;")
                lbl = QLabel(step_name)
                lbl.setStyleSheet("color: #6b7079; font-size: 11px; text-decoration: none;")
            elif idx == current_index:
                # Active prominent step
                icon_lbl = QLabel("●")
                icon_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 800;")
                lbl = QLabel(step_name)
                lbl.setStyleSheet("color: #f5f6f8; font-size: 12px; font-weight: 600;")
            else:
                # Upcoming step
                icon_lbl = QLabel("○")
                icon_lbl.setStyleSheet("color: #4b5563; font-size: 10px;")
                lbl = QLabel(step_name)
                lbl.setStyleSheet("color: #4b5563; font-size: 11px;")

            row.addWidget(icon_lbl)
            row.addWidget(lbl, stretch=1)
            sw = QWidget()
            sw.setLayout(row)
            self.step_container.addWidget(sw)

    def _clear_steps(self):
        while self.step_container.count():
            item = self.step_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
