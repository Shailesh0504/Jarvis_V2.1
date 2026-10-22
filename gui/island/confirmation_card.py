# gui/island/confirmation_card.py
"""Compact Permission and Confirmation Card for JARVIS Island.

Features:
- Clear action description and risk indicator (amber for caution, crimson for dangerous)
- Distinct Cancel (Esc / N) and Allow/Confirm (Enter / Y) actions
- Keyboard accessible
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
)


class ConfirmationCard(QFrame):
    """Compact confirmation card for user permissions."""

    confirmed = Signal(bool)  # True = Allow/Confirm, False = Cancel

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("island_confirmation_card")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Header with warning badge
        hdr = QHBoxLayout()
        self.badge_lbl = QLabel("⚠️  Confirmation Required")
        self.badge_lbl.setStyleSheet("color: #f5a524; font-size: 11px; font-weight: 700;")
        hdr.addWidget(self.badge_lbl)
        hdr.addStretch()
        layout.addLayout(hdr)

        # Action description
        self.action_lbl = QLabel("JARVIS wants to perform an action:")
        self.action_lbl.setWordWrap(True)
        self.action_lbl.setStyleSheet("color: #f5f6f8; font-size: 12.5px; font-weight: 600;")
        layout.addWidget(self.action_lbl)

        # Command / Detail pill
        self.detail_lbl = QLabel("")
        self.detail_lbl.setWordWrap(True)
        self.detail_lbl.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.4);
            color: #9398a1;
            font-family: monospace;
            font-size: 11px;
            padding: 5px 8px;
            border-radius: 6px;
        """)
        layout.addWidget(self.detail_lbl)

        # Button Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self.cancel_btn = QPushButton("Cancel  (Esc)")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #1d1f23;
                color: #f4505e;
                border: 1px solid rgba(244, 80, 94, 0.35);
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 11.5px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: rgba(244, 80, 94, 0.2);
            }
        """)
        self.cancel_btn.clicked.connect(lambda: self.confirmed.emit(False))
        btn_row.addWidget(self.cancel_btn)

        self.allow_btn = QPushButton("Allow  (Enter)")
        self.allow_btn.setCursor(Qt.PointingHandCursor)
        self.allow_btn.setStyleSheet("""
            QPushButton {
                background-color: #22c55e;
                color: #0b0c0e;
                border: none;
                border-radius: 8px;
                padding: 6px 16px;
                font-size: 11.5px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #16a34a;
            }
        """)
        self.allow_btn.clicked.connect(lambda: self.confirmed.emit(True))
        btn_row.addWidget(self.allow_btn)

        layout.addLayout(btn_row)

        self.setStyleSheet("""
            QFrame#island_confirmation_card {
                background-color: #141518;
                border: 1px solid rgba(245, 165, 36, 0.3);
                border-radius: 14px;
            }
        """)

    def set_request(self, action_title: str, detail: str = "", is_dangerous: bool = False) -> None:
        """Configures the confirmation dialog."""
        self.action_lbl.setText(action_title)
        if detail:
            self.detail_lbl.setText(detail)
            self.detail_lbl.setVisible(True)
        else:
            self.detail_lbl.setVisible(False)

        if is_dangerous:
            self.badge_lbl.setText("🚨 Dangerous Action Confirmation")
            self.badge_lbl.setStyleSheet("color: #f4505e; font-size: 11px; font-weight: 700;")
            self.allow_btn.setText("Confirm  (Enter)")
            self.allow_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f4505e;
                    color: #ffffff;
                    border: none;
                    border-radius: 8px;
                    padding: 6px 16px;
                    font-size: 11.5px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #dc2626;
                }
            """)
        else:
            self.badge_lbl.setText("⚠️ Confirmation Required")
            self.badge_lbl.setStyleSheet("color: #f5a524; font-size: 11px; font-weight: 700;")
            self.allow_btn.setText("Allow  (Enter)")
            self.allow_btn.setStyleSheet("""
                QPushButton {
                    background-color: #22c55e;
                    color: #0b0c0e;
                    border: none;
                    border-radius: 8px;
                    padding: 6px 16px;
                    font-size: 11.5px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #16a34a;
                }
            """)
