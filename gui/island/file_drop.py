# gui/island/file_drop.py
"""File Drop Overlay and Receptive Target for JARVIS Island.

Features:
- Detects drag/drop events over the island
- Visually receptive dashed glowing border with 'Drop file here'
- Once dropped: presents contextual actions: [ Ask JARVIS ] [ Open ] [ Cancel ]
- Reuses existing backend file logic
"""

import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
)


class FileDropTarget(QFrame):
    """File drag-and-drop target overlay for JARVIS Island."""

    file_dropped = Signal(str)            # file_path
    ask_file_requested = Signal(str)      # file_path
    open_file_requested = Signal(str)     # file_path
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("island_file_drop")
        self._current_file_path = ""
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Drop Zone prompt
        self.prompt_box = QFrame()
        self.prompt_box.setStyleSheet("""
            border: 2px dashed rgba(34, 211, 238, 0.45);
            border-radius: 12px;
            background-color: rgba(34, 211, 238, 0.05);
            padding: 16px;
        """)
        prompt_layout = QVBoxLayout(self.prompt_box)
        prompt_layout.setAlignment(Qt.AlignCenter)
        prompt_layout.setSpacing(4)

        self.icon_lbl = QLabel("📎")
        self.icon_lbl.setStyleSheet("font-size: 24px;")
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        prompt_layout.addWidget(self.icon_lbl)

        self.msg_lbl = QLabel("Drop file here to analyze with JARVIS")
        self.msg_lbl.setStyleSheet("color: #f5f6f8; font-size: 13px; font-weight: 600;")
        self.msg_lbl.setAlignment(Qt.AlignCenter)
        prompt_layout.addWidget(self.msg_lbl)

        layout.addWidget(self.prompt_box)

        # Contextual Action Row (hidden initially)
        self.action_box = QFrame()
        act_layout = QHBoxLayout(self.action_box)
        act_layout.setContentsMargins(0, 0, 0, 0)
        act_layout.setSpacing(8)

        self.file_chip = QLabel("")
        self.file_chip.setStyleSheet("""
            background: #141518;
            color: #22d3ee;
            border: 1px solid rgba(34, 211, 238, 0.3);
            border-radius: 999px;
            padding: 4px 12px;
            font-size: 11px;
            font-weight: 600;
        """)
        act_layout.addWidget(self.file_chip)

        act_layout.addStretch()

        self.ask_btn = QPushButton("Ask JARVIS")
        self.ask_btn.setCursor(Qt.PointingHandCursor)
        self.ask_btn.setStyleSheet("""
            QPushButton {
                background: #22c55e;
                color: #0b0c0e;
                border-radius: 8px;
                padding: 5px 14px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover { background: #16a34a; }
        """)
        self.ask_btn.clicked.connect(lambda: self.ask_file_requested.emit(self._current_file_path))
        act_layout.addWidget(self.ask_btn)

        self.open_btn = QPushButton("Open")
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.setStyleSheet("""
            QPushButton {
                background: #1d1f23;
                color: #f5f6f8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover { background: #27292e; }
        """)
        self.open_btn.clicked.connect(lambda: self.open_file_requested.emit(self._current_file_path))
        act_layout.addWidget(self.open_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #9398a1;
                border: none;
                padding: 5px 8px;
                font-size: 11px;
            }
            QPushButton:hover { color: #f4505e; }
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        act_layout.addWidget(self.cancel_btn)

        self.action_box.setVisible(False)
        layout.addWidget(self.action_box)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.prompt_box.setStyleSheet("""
                border: 2px dashed #22d3ee;
                border-radius: 12px;
                background-color: rgba(34, 211, 238, 0.12);
                padding: 16px;
            """)

    def dragLeaveEvent(self, event):
        self.prompt_box.setStyleSheet("""
            border: 2px dashed rgba(34, 211, 238, 0.45);
            border-radius: 12px;
            background-color: rgba(34, 211, 238, 0.05);
            padding: 16px;
        """)

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.set_dropped_file(path)
                self.file_dropped.emit(path)
                event.acceptProposedAction()

    def set_dropped_file(self, file_path: str):
        self._current_file_path = file_path
        file_name = os.path.basename(file_path)
        self.msg_lbl.setText("File attached and ready")
        self.file_chip.setText(f"📄 {file_name}")
        self.action_box.setVisible(True)

    def _on_cancel(self):
        self._current_file_path = ""
        self.action_box.setVisible(False)
        self.msg_lbl.setText("Drop file here to analyze with JARVIS")
        self.cancelled.emit()
