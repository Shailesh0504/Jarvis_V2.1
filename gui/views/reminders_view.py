# gui/views/reminders_view.py
"""
Modern Cyber-Dark Reminders Management View for Jarvis GUI.
"""

import datetime
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal, QTimer, QDateTime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QDialog, QLineEdit, QComboBox, QDateTimeEdit, QMessageBox,
    QButtonGroup
)


class AddReminderDialog(QDialog):
    """Dialog for creating a new reminder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Schedule New Reminder")
        self.resize(400, 300)
        self.setStyleSheet("""
            QDialog { background-color: #0f172a; color: #f8fafc; }
            QLabel { color: #94a3b8; font-size: 13px; font-weight: bold; }
            QLineEdit, QComboBox, QDateTimeEdit {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #3b82f6;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #2563eb; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Reminder Title / Task:"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("e.g. Paani peena, Medicine, Meeting")
        layout.addWidget(self.title_input)

        layout.addWidget(QLabel("Date & Time:"))
        self.time_input = QDateTimeEdit()
        self.time_input.setDateTime(datetime.datetime.now() + datetime.timedelta(minutes=15))
        self.time_input.setCalendarPopup(True)
        layout.addWidget(self.time_input)

        layout.addWidget(QLabel("Recurrence:"))
        self.recur_combo = QComboBox()
        self.recur_combo.addItems(["None (One-time)", "Daily", "Weekly", "Weekdays", "Monthly"])
        layout.addWidget(self.recur_combo)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("background-color: #475569;")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Set Reminder")
        self.btn_save.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_save)

        layout.addLayout(btn_box)

    def get_data(self) -> Dict[str, Any]:
        dt = self.time_input.dateTime().toPython().astimezone()
        recur_map = {
            "None (One-time)": "none",
            "Daily": "daily",
            "Weekly": "weekly",
            "Weekdays": "weekdays",
            "Monthly": "monthly"
        }
        return {
            "title": self.title_input.text().strip(),
            "remind_time": dt.isoformat(),
            "recurrence": recur_map.get(self.recur_combo.currentText(), "none")
        }


class EditReminderDialog(QDialog):
    """Dialog for editing an existing scheduled reminder."""

    def __init__(self, reminder: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.reminder = reminder
        self.reminder_id = reminder.get("id")
        self.setWindowTitle(f"Edit Reminder #{self.reminder_id}")
        self.resize(420, 320)
        self.setStyleSheet("""
            QDialog { background-color: #0f172a; color: #f8fafc; }
            QLabel { color: #94a3b8; font-size: 13px; font-weight: bold; }
            QLineEdit, QComboBox, QDateTimeEdit {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #3b82f6;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #2563eb; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Reminder Title / Task:"))
        self.title_input = QLineEdit()
        self.title_input.setText(str(reminder.get("title", "")))
        self.title_input.setPlaceholderText("e.g. Paani peena, Medicine, Meeting")
        layout.addWidget(self.title_input)

        layout.addWidget(QLabel("Date & Time:"))
        self.time_input = QDateTimeEdit()
        self.time_input.setCalendarPopup(True)

        remind_time_str = reminder.get("remind_time", "")
        try:
            dt = datetime.datetime.fromisoformat(remind_time_str)
            self.time_input.setDateTime(QDateTime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second))
        except Exception:
            self.time_input.setDateTime(QDateTime.currentDateTime().addSecs(900))
        layout.addWidget(self.time_input)

        layout.addWidget(QLabel("Recurrence:"))
        self.recur_combo = QComboBox()
        self.recur_combo.addItems(["None (One-time)", "Daily", "Weekly", "Weekdays", "Monthly"])

        recur_rev_map = {
            "none": "None (One-time)",
            "daily": "Daily",
            "weekly": "Weekly",
            "weekdays": "Weekdays",
            "monthly": "Monthly"
        }
        current_recur = str(reminder.get("recurrence", "none")).lower()
        self.recur_combo.setCurrentText(recur_rev_map.get(current_recur, "None (One-time)"))
        layout.addWidget(self.recur_combo)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("background-color: #475569;")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save Changes")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb);
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover { background: #1d4ed8; }
        """)
        self.btn_save.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_save)

        layout.addLayout(btn_box)

    def get_data(self) -> Dict[str, Any]:
        dt = self.time_input.dateTime().toPython().astimezone()
        recur_map = {
            "None (One-time)": "none",
            "Daily": "daily",
            "Weekly": "weekly",
            "Weekdays": "weekdays",
            "Monthly": "monthly"
        }
        return {
            "reminder_id": self.reminder_id,
            "new_title": self.title_input.text().strip(),
            "new_time": dt.isoformat(),
            "new_recurrence": recur_map.get(self.recur_combo.currentText(), "none")
        }


class RemindersView(QWidget):
    """Dedicated Reminders panel showing active, recurring, snoozed, missed, and completed reminders."""

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self.current_filter = "all"
        self._init_ui()

        # Auto-refresh timer every 3 seconds
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.load_reminders)
        self.refresh_timer.start(3000)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header Bar
        header = QHBoxLayout()
        title = QLabel("⏰ Reminders & Alarms")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #f8fafc;")
        header.addWidget(title)
        header.addStretch()

        self.btn_add = QPushButton("+ Add Reminder")
        self.btn_add.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb);
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover { background: #1d4ed8; }
        """)
        self.btn_add.clicked.connect(self._open_add_dialog)
        header.addWidget(self.btn_add)

        layout.addLayout(header)

        # Filter Pills Bar
        pill_layout = QHBoxLayout()
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)

        filters = [
            ("All", "all"),
            ("Pending", "pending"),
            ("Today", "today"),
            ("Recurring", "recurring"),
            ("Snoozed", "snoozed"),
            ("Missed", "missed"),
            ("Completed", "completed")
        ]

        for idx, (label, f_key) in enumerate(filters):
            btn = QPushButton(label)
            btn.setCheckable(True)
            if idx == 0:
                btn.setChecked(True)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #94a3b8;
                    border: 1px solid #334155;
                    border-radius: 14px;
                    padding: 6px 14px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #3b82f6;
                    color: white;
                    border-color: #60a5fa;
                }
                QPushButton:hover:!checked {
                    background-color: #334155;
                    color: #f8fafc;
                }
            """)
            btn.clicked.connect(lambda checked=False, k=f_key: self._set_filter(k))
            self.filter_group.addButton(btn, idx)
            pill_layout.addWidget(btn)

        pill_layout.addStretch()
        layout.addLayout(pill_layout)

        # Reminders Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Title / Task", "Scheduled Time", "Recurrence", "Status", "Actions"])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 65)

        header.setSectionResizeMode(1, QHeaderView.Stretch)

        header.setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.setColumnWidth(2, 180)

        header.setSectionResizeMode(3, QHeaderView.Interactive)
        self.table.setColumnWidth(3, 110)

        header.setSectionResizeMode(4, QHeaderView.Interactive)
        self.table.setColumnWidth(4, 130)

        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 230)

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.itemDoubleClicked.connect(self._on_table_double_clicked)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 8px;
                gridline-color: transparent;
                color: #f8fafc;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #94a3b8;
                font-weight: bold;
                border: none;
                border-bottom: 2px solid #334155;
                padding: 10px 8px;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #1e293b;
                color: #e2e8f0;
            }
            QTableWidget::item:selected {
                background-color: #1e3a8a;
            }
        """)

        layout.addWidget(self.table)
        self.load_reminders()

    def _set_filter(self, filter_key: str):
        self.current_filter = filter_key
        self.load_reminders()

    def _get_reminder_plugin(self):
        if hasattr(self.core, "plugin_manager") and self.core.plugin_manager:
            return self.core.plugin_manager.get_plugin("reminder")
        return None

    def _execute_reminder_action(self, action: str, parameters: Dict[str, Any]):
        """Execute through PluginManager so an unloaded reminder plugin loads safely."""
        manager = getattr(self.core, "plugin_manager", None)
        if not manager:
            return None
        return manager.execute_action("reminder", action, parameters)

    def load_reminders(self):
        res = self._execute_reminder_action("list_reminders", {"filter": self.current_filter})
        if res is None:
            self.table.setRowCount(0)
            return
        if not res.success or not res.data:
            self.table.setRowCount(0)
            return

        reminders = res.data.get("reminders", [])
        self._loaded_reminders = reminders
        self.table.setRowCount(len(reminders))
        plugin = self._get_reminder_plugin()

        for row, r in enumerate(reminders):
            # ID
            id_item = QTableWidgetItem(f"#{r.get('id')}")
            id_item.setTextAlignment(Qt.AlignCenter)
            id_item.setFlags(id_item.flags() ^ Qt.ItemIsEditable)
            self.table.setItem(row, 0, id_item)

            # Title
            title_item = QTableWidgetItem(r.get("title", ""))
            title_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            title_item.setFlags(title_item.flags() ^ Qt.ItemIsEditable)
            self.table.setItem(row, 1, title_item)

            # Scheduled Time
            friendly_time = plugin.format_time_friendly(r.get("remind_time", "")) if plugin else r.get("remind_time", "")
            time_item = QTableWidgetItem(friendly_time)
            time_item.setTextAlignment(Qt.AlignCenter)
            time_item.setFlags(time_item.flags() ^ Qt.ItemIsEditable)
            self.table.setItem(row, 2, time_item)

            # Recurrence
            recur = r.get("recurrence", "none").capitalize()
            recur_item = QTableWidgetItem(recur)
            recur_item.setTextAlignment(Qt.AlignCenter)
            recur_item.setFlags(recur_item.flags() ^ Qt.ItemIsEditable)
            self.table.setItem(row, 3, recur_item)

            # Status Badge
            status = r.get("status", "pending").upper()
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setFlags(status_item.flags() ^ Qt.ItemIsEditable)
            self.table.setItem(row, 4, status_item)

            status_widget = QWidget()
            status_layout = QHBoxLayout(status_widget)
            status_layout.setContentsMargins(4, 4, 4, 4)
            status_layout.setAlignment(Qt.AlignCenter)
            status_badge = QLabel(f"● {status}")
            status_badge.setAlignment(Qt.AlignCenter)
            status_badge.setFixedHeight(26)
            status_badge.setFixedWidth(104)

            if status == "PENDING":
                status_badge.setStyleSheet("""
                    color: #06b6d4;
                    font-weight: 700;
                    font-size: 11px;
                    background-color: rgba(6, 182, 212, 0.15);
                    border: 1px solid rgba(6, 182, 212, 0.35);
                    border-radius: 13px;
                """)
            elif status == "SNOOZED":
                status_badge.setStyleSheet("""
                    color: #fbbf24;
                    font-weight: 700;
                    font-size: 11px;
                    background-color: rgba(245, 158, 11, 0.15);
                    border: 1px solid rgba(245, 158, 11, 0.35);
                    border-radius: 13px;
                """)
            elif status == "COMPLETED":
                status_badge.setStyleSheet("""
                    color: #10b981;
                    font-weight: 700;
                    font-size: 11px;
                    background-color: rgba(16, 185, 129, 0.15);
                    border: 1px solid rgba(16, 185, 129, 0.35);
                    border-radius: 13px;
                """)
            elif status == "MISSED":
                status_badge.setStyleSheet("""
                    color: #ef4444;
                    font-weight: 700;
                    font-size: 11px;
                    background-color: rgba(239, 68, 68, 0.15);
                    border: 1px solid rgba(239, 68, 68, 0.35);
                    border-radius: 13px;
                """)
            else:
                status_badge.setStyleSheet("""
                    color: #94a3b8;
                    font-weight: 700;
                    font-size: 11px;
                    background-color: rgba(148, 163, 184, 0.15);
                    border: 1px solid rgba(148, 163, 184, 0.35);
                    border-radius: 13px;
                """)

            status_layout.addWidget(status_badge)
            self.table.setCellWidget(row, 4, status_widget)

            # Action Buttons Widget
            act_widget = QWidget()
            act_layout = QHBoxLayout(act_widget)
            act_layout.setContentsMargins(4, 4, 4, 4)
            act_layout.setSpacing(6)
            act_layout.setAlignment(Qt.AlignCenter)

            rid = r.get("id")

            # Edit Button
            btn_edit = QPushButton("Edit")
            btn_edit.setToolTip("Edit title, time, or recurrence")
            btn_edit.setFixedHeight(28)
            btn_edit.setFixedWidth(64)
            btn_edit.setStyleSheet("""
                QPushButton {
                    background-color: rgba(59, 130, 246, 0.15);
                    color: #60a5fa;
                    border: 1px solid rgba(59, 130, 246, 0.35);
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: rgba(59, 130, 246, 0.3);
                    border-color: #3b82f6;
                    color: #bfdbfe;
                }
            """)
            btn_edit.clicked.connect(lambda ch=False, rem=r: self._open_edit_dialog(rem))
            act_layout.addWidget(btn_edit)

            # Snooze +10m
            btn_snooze = QPushButton("+10m")
            btn_snooze.setToolTip("Snooze by 10 minutes")
            btn_snooze.setFixedHeight(28)
            btn_snooze.setFixedWidth(64)
            btn_snooze.setStyleSheet("""
                QPushButton {
                    background-color: rgba(245, 158, 11, 0.15);
                    color: #fbbf24;
                    border: 1px solid rgba(245, 158, 11, 0.35);
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: rgba(245, 158, 11, 0.3);
                    border-color: #f59e0b;
                    color: #fef3c7;
                }
            """)
            btn_snooze.clicked.connect(lambda ch=False, i=rid: self._snooze_reminder(i, 10))
            act_layout.addWidget(btn_snooze)

            # Cancel / Delete
            btn_del = QPushButton("Delete")
            btn_del.setToolTip("Delete this reminder")
            btn_del.setFixedHeight(28)
            btn_del.setFixedWidth(64)
            btn_del.setStyleSheet("""
                QPushButton {
                    background-color: rgba(239, 68, 68, 0.15);
                    color: #f87171;
                    border: 1px solid rgba(239, 68, 68, 0.35);
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: rgba(239, 68, 68, 0.3);
                    border-color: #ef4444;
                    color: #fca5a5;
                }
            """)
            btn_del.clicked.connect(lambda ch=False, i=rid: self._delete_reminder(i))
            act_layout.addWidget(btn_del)

            self.table.setCellWidget(row, 5, act_widget)

    def _open_add_dialog(self):
        dlg = AddReminderDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            if not data.get("title"):
                QMessageBox.warning(self, "Invalid Input", "Please provide a reminder title.")
                return

            result = self.create_reminder(data)
            if result is not None and not result.success:
                QMessageBox.warning(self, "Reminder Not Saved", result.error or "Reminder save nahi ho saka.")

    def _open_edit_dialog(self, reminder_data: Dict[str, Any]):
        dlg = EditReminderDialog(reminder_data, self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            if not data.get("new_title"):
                QMessageBox.warning(self, "Invalid Input", "Please provide a reminder title.")
                return

            result = self.update_reminder(data)
            if result is not None and not result.success:
                QMessageBox.warning(self, "Reminder Not Updated", result.error or "Reminder update nahi ho saka.")

    def _on_table_double_clicked(self, item):
        row = item.row()
        if hasattr(self, "_loaded_reminders") and 0 <= row < len(self._loaded_reminders):
            self._open_edit_dialog(self._loaded_reminders[row])

    def create_reminder(self, data: Dict[str, Any]):
        """Create and immediately display a reminder; also usable by GUI tests."""
        result = self._execute_reminder_action("create_reminder", data)
        if result is not None and result.success:
            self.current_filter = "all"
            all_button = self.filter_group.button(0)
            if all_button:
                all_button.setChecked(True)
            self.load_reminders()
        return result

    def update_reminder(self, data: Dict[str, Any]):
        """Update an existing reminder; also usable by GUI tests."""
        result = self._execute_reminder_action("edit_reminder", data)
        if result is not None and result.success:
            self.load_reminders()
        return result

    def _snooze_reminder(self, reminder_id: int, minutes: int = 10):
        result = self._execute_reminder_action("snooze_reminder", {"reminder_id": reminder_id, "minutes": minutes})
        if result is not None and result.success:
            self.load_reminders()

    def _delete_reminder(self, reminder_id: int):
        result = self._execute_reminder_action("delete_reminder", {"reminder_id": reminder_id})
        if result is not None and result.success:
            self.load_reminders()

