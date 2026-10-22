# gui/island/question_card.py
"""Compact User Choice / Question Card for JARVIS Island.

Features:
- Clear question prompt
- Horizontal or wrapped pill buttons for fast keyboard/mouse selection
- Instantly returns selection
"""

from typing import List
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
)


class QuestionCard(QFrame):
    """Compact multiple-choice question card for prompt resolution."""

    option_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("island_question_card")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Question prompt
        self.prompt_lbl = QLabel("JARVIS needs an answer:")
        self.prompt_lbl.setWordWrap(True)
        self.prompt_lbl.setStyleSheet("color: #f5f6f8; font-size: 13px; font-weight: 700;")
        layout.addWidget(self.prompt_lbl)

        # Options Container
        self.options_layout = QHBoxLayout()
        self.options_layout.setSpacing(8)
        layout.addLayout(self.options_layout)

        self.setStyleSheet("""
            QFrame#island_question_card {
                background-color: #141518;
                border: 1px solid rgba(34, 211, 238, 0.25);
                border-radius: 14px;
            }
        """)

    def set_question(self, question: str, options: List[str]) -> None:
        """Sets question text and creates option buttons."""
        self.prompt_lbl.setText(question)

        # Clear existing buttons
        while self.options_layout.count():
            item = self.options_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for opt in options:
            btn = QPushButton(opt)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1d1f23;
                    color: #22d3ee;
                    border: 1px solid rgba(34, 211, 238, 0.35);
                    border-radius: 8px;
                    padding: 6px 14px;
                    font-size: 11.5px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: rgba(34, 211, 238, 0.2);
                    color: #ffffff;
                }
            """)
            btn.clicked.connect(lambda checked=False, choice=opt: self.option_selected.emit(choice))
            self.options_layout.addWidget(btn)

        self.options_layout.addStretch()
