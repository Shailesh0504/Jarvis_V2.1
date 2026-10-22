# gui/views/activity_log_view.py
"""Activity Log & Live Console View for Jarvis V2 GUI."""

import datetime
import json
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor

from core.logger import GLOBAL_LOG_BUFFER, LogEntry


class ActivityLogView(QWidget):
    """Real-time console displaying color-coded activity logs and observed desktop events."""

    def __init__(self, jarvis_core=None):
        super().__init__()
        self.core = jarvis_core
        self.log_buffer = GLOBAL_LOG_BUFFER
        self.active_mode = "console"
        self._init_ui()

        # Update timer for live polling
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_logs)
        self.timer.start(500) # Every 500ms

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # Header Title
        hdr = QHBoxLayout()
        title_label = QLabel("ACTIVITY LOG & TELEMETRY")
        title_label.setStyleSheet("font-size: 16px; font-weight: 800; color: #f8fafc; letter-spacing: 1px;")
        hdr.addWidget(title_label)
        hdr.addStretch()

        # Mode toggle pills: Console vs Desktop Timeline
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)

        btn_console = QPushButton("● Console & Debug")
        btn_console.setCheckable(True)
        btn_console.setChecked(True)
        btn_console.setStyleSheet("""
            QPushButton {
                background-color: #1e293b; color: #94a3b8; border: 1px solid #334155;
                border-radius: 12px; padding: 5px 12px; font-size: 12px; font-weight: bold;
            }
            QPushButton:checked { background-color: #0284c7; color: white; border-color: #38bdf8; }
        """)
        btn_console.clicked.connect(lambda: self._set_mode("console"))
        self.mode_group.addButton(btn_console, 0)
        hdr.addWidget(btn_console)

        btn_timeline = QPushButton("🖥 Activity Timeline")
        btn_timeline.setCheckable(True)
        btn_timeline.setStyleSheet("""
            QPushButton {
                background-color: #1e293b; color: #94a3b8; border: 1px solid #334155;
                border-radius: 12px; padding: 5px 12px; font-size: 12px; font-weight: bold;
            }
            QPushButton:checked { background-color: #0284c7; color: white; border-color: #38bdf8; }
        """)
        btn_timeline.clicked.connect(lambda: self._set_mode("timeline"))
        self.mode_group.addButton(btn_timeline, 1)
        hdr.addWidget(btn_timeline)

        main_layout.addLayout(hdr)

        # Controls Toolbar (Filter, Search, Auto-Scroll, Clear)
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(10)

        # Log Level Filter
        self.filter_label = QLabel("Filter:")
        self.filter_label.setStyleSheet("color: #94a3b8; font-weight: 600;")
        self.toolbar.addWidget(self.filter_label)

        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["ALL", "INPUT", "INTENT", "PLUGIN", "ACTION", "SUCCESS", "MEMORY", "DEBUG", "INFO", "WARNING", "ERROR"])
        self.combo_filter.currentTextChanged.connect(self._refresh_logs)
        self.combo_filter.setStyleSheet("""
            QComboBox {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 700;
            }
        """)
        self.toolbar.addWidget(self.combo_filter)

        # Search Bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search messages...")
        self.search_input.textChanged.connect(self._refresh_logs)
        self.toolbar.addWidget(self.search_input)

        # Auto-Scroll Checkbox
        self.check_autoscroll = QCheckBox("Auto-Scroll")
        self.check_autoscroll.setChecked(True)
        self.check_autoscroll.setStyleSheet("color: #94a3b8;")
        self.toolbar.addWidget(self.check_autoscroll)

        # Clear Button
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setProperty("class", "chip-btn")
        self.btn_clear.clicked.connect(self._clear_logs)
        self.toolbar.addWidget(self.btn_clear)

        main_layout.addLayout(self.toolbar)

        # Content Stack: 0 = Console Text Edit, 1 = Observer Activity Timeline Table
        self.view_stack = QStackedWidget()

        # Console Text Display
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.Monospace)
        self.console.setFont(font)
        self.console.setStyleSheet("""
            QTextEdit {
                background-color: #0b0f19;
                color: #e2e8f0;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 12px;
                line-height: 1.5;
            }
        """)
        self.view_stack.addWidget(self.console)

        # Desktop Activity Timeline Table
        self.timeline_table = QTableWidget()
        self.timeline_table.setColumnCount(5)
        self.timeline_table.setHorizontalHeaderLabels(["TIME", "EVENT TYPE", "APP / SITE", "WINDOW / CONTENT TITLE", "IMPORTANCE"])
        self.timeline_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.timeline_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.timeline_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.timeline_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.timeline_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.timeline_table.verticalHeader().setVisible(False)
        self.timeline_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.timeline_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.view_stack.addWidget(self.timeline_table)

        main_layout.addWidget(self.view_stack, stretch=1)

        self._refresh_logs()

    def _set_mode(self, mode: str):
        self.active_mode = mode
        if mode == "timeline":
            self.view_stack.setCurrentIndex(1)
            self.filter_label.setVisible(False)
            self.combo_filter.setVisible(False)
            self.check_autoscroll.setVisible(False)
            self._render_timeline()
        else:
            self.view_stack.setCurrentIndex(0)
            self.filter_label.setVisible(True)
            self.combo_filter.setVisible(True)
            self.check_autoscroll.setVisible(True)
            self._refresh_logs()

    def refresh_logs(self):
        """Public refresh method."""
        if self.active_mode == "timeline":
            self._render_timeline()
        else:
            self._refresh_logs()

    def _color_for_level(self, level: str) -> str:
        colors = {
            "INPUT": "#38bdf8", # Sky Blue
            "INTENT": "#a855f7", # Purple
            "PLUGIN": "#60a5fa", # Blue
            "ACTION": "#f59e0b", # Amber
            "SUCCESS": "#22c55e", # Green
            "MEMORY": "#ec4899", # Pink
            "DEBUG": "#64748b", # Gray
            "INFO": "#38bdf8", # Cyan
            "WARNING": "#eab308", # Yellow
            "ERROR": "#ef4444" # Red
        }
        return colors.get(level.upper(), "#94a3b8")

    def _refresh_logs(self):
        if self.active_mode == "timeline":
            return

        level_filter = self.combo_filter.currentText()
        search_query = self.search_input.text().strip()

        entries = self.log_buffer.get_entries(level_filter=level_filter, search=search_query)

        html_lines = []
        for e in entries:
            color = self._color_for_level(e.level)
            html_lines.append(
                f"<span style='color: #64748b;'>{e.timestamp}</span> "
                f"<b style='color: {color};'>[{e.category.upper()}]</b> "
                f"<span style='color: #f1f5f9;'>{e.message}</span>"
            )

        self.console.setHtml("<br>".join(html_lines))

        if self.check_autoscroll.isChecked():
            cursor = self.console.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.console.setTextCursor(cursor)

    def _render_timeline(self):
        query = self.search_input.text().strip().lower()
        rows = []
        if self.core and hasattr(self.core, "memory_manager") and self.core.memory_manager:
            db = getattr(self.core.memory_manager, "db", None)
            if db and hasattr(db, "execute_query"):
                try:
                    sql = "SELECT timestamp, event_type, application, website, window_title, content_title, importance FROM proactive_activity_events ORDER BY timestamp DESC LIMIT 60"
                    rows = db.execute_query(sql)
                except Exception:
                    rows = []

        filtered = []
        for r in rows:
            app = str(r.get("application") or r.get("website") or "").lower()
            title = str(r.get("window_title") or r.get("content_title") or "").lower()
            ev_type = str(r.get("event_type", "")).lower()
            if not query or query in app or query in title or query in ev_type:
                filtered.append(r)

        self.timeline_table.setRowCount(len(filtered))
        for row_idx, r in enumerate(filtered):
            ts = r.get("timestamp", 0)
            t_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "--"
            time_item = QTableWidgetItem(t_str)
            time_item.setForeground(Qt.gray)
            self.timeline_table.setItem(row_idx, 0, time_item)

            ev_str = str(r.get("event_type", "")).upper()
            ev_item = QTableWidgetItem(ev_str)
            ev_item.setForeground(Qt.cyan)
            self.timeline_table.setItem(row_idx, 1, ev_item)

            target = str(r.get("application") or r.get("website") or "Desktop").title()
            tgt_item = QTableWidgetItem(target)
            tgt_item.setForeground(Qt.white)
            self.timeline_table.setItem(row_idx, 2, tgt_item)

            detail = str(r.get("content_title") or r.get("window_title") or "")
            self.timeline_table.setItem(row_idx, 3, QTableWidgetItem(detail))

            imp_str = str(r.get("importance", "MEDIUM")).upper()
            imp_item = QTableWidgetItem(imp_str)
            imp_color = Qt.green if imp_str == "LOW" else (Qt.yellow if imp_str == "MEDIUM" else Qt.red)
            imp_item.setForeground(imp_color)
            self.timeline_table.setItem(row_idx, 4, imp_item)

    def _clear_logs(self):
        if self.active_mode == "timeline":
            if self.core and hasattr(self.core, "memory_manager") and self.core.memory_manager:
                db = getattr(self.core.memory_manager, "db", None)
                if db and hasattr(db, "execute_update"):
                    db.execute_update("DELETE FROM proactive_activity_events")
            self._render_timeline()
        else:
            self.log_buffer.clear()
            self.console.clear()
