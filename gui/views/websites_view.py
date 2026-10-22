# gui/views/websites_view.py
"""
Websites View: Visual Manager for Saved & User-Learned Website Shortcuts in Jarvis V2.
Provides View, Edit, Delete, Enable/Disable, Test/Open, and Search capabilities.
"""

import datetime
import logging
import webbrowser
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.website_knowledge import InvalidWebsiteURL, WebsiteKnowledgeStore, validate_website_url

logger = logging.getLogger("jarvis.gui.websites_view")


class AddEditWebsiteDialog(QDialog):
    """Modal dialog for creating or editing a learned website mapping."""

    def __init__(self, entry: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self.entry = entry
        is_edit = entry is not None
        self.setWindowTitle("Edit Website Shortcut" if is_edit else "Add New Website Shortcut")
        self.resize(520, 380)
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #f8fafc;
            }
            QLabel {
                color: #94a3b8;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }
            QLineEdit {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 10px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #00d2ff;
                background-color: #162238;
            }
            QPushButton {
                font-weight: 700;
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 13px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        # Title
        title_lbl = QLabel("EDIT SAVED WEBSITE" if is_edit else "ADD NEW WEBSITE SHORTCUT")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 800; color: #00d2ff; letter-spacing: 1px;")
        layout.addWidget(title_lbl)

        # Alias / Voice trigger
        layout.addWidget(QLabel("SPOKEN ALIAS / TRIGGER PHRASE (e.g. glpi, jira, my portal):"))
        self.alias_input = QLineEdit()
        self.alias_input.setPlaceholderText("e.g. glpi")
        layout.addWidget(self.alias_input)

        # Display Name
        layout.addWidget(QLabel("DISPLAY / CANONICAL NAME:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. GLPI Portal")
        layout.addWidget(self.name_input)

        # Target URL
        layout.addWidget(QLabel("TARGET WEBSITE URL (HTTP or HTTPS):"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://glpi-jioinstitute1.msappproxy.net/front/center.php")
        layout.addWidget(self.url_input)

        # Validation error message label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ef4444; font-size: 12px; font-weight: 600;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        # Fill existing data if editing
        if is_edit and entry:
            aliases = entry.get("aliases", [])
            primary_alias = aliases[0] if aliases else ""
            self.alias_input.setText(primary_alias)
            self.name_input.setText(entry.get("canonical_name", ""))
            self.url_input.setText(entry.get("url", ""))

        layout.addStretch()

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("background-color: #334155; color: #e2e8f0; border: none;")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save Shortcut")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00d2ff, stop:1 #3a7bd5);
                color: #0b0f19;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #33dcff, stop:1 #4f8de6);
            }
        """)
        self.btn_save.clicked.connect(self._validate_and_accept)
        btn_box.addWidget(self.btn_save)

        layout.addLayout(btn_box)

    def _validate_and_accept(self):
        alias = self.alias_input.text().strip()
        url = self.url_input.text().strip()
        if not alias:
            self.error_label.setText("Please enter a spoken alias or trigger phrase.")
            self.error_label.setVisible(True)
            return
        if not url:
            self.error_label.setText("Please enter a valid website URL.")
            self.error_label.setVisible(True)
            return

        try:
            safe_url = validate_website_url(url)
            self.validated_url = safe_url
            self.validated_alias = alias
            self.validated_name = self.name_input.text().strip() or alias.title()
            self.accept()
        except InvalidWebsiteURL as e:
            self.error_label.setText(str(e))
            self.error_label.setVisible(True)
        except Exception as e:
            self.error_label.setText(f"Invalid URL: {str(e)}")
            self.error_label.setVisible(True)

    def get_data(self) -> Dict[str, str]:
        return {
            "alias": getattr(self, "validated_alias", self.alias_input.text().strip()),
            "canonical_name": getattr(self, "validated_name", self.name_input.text().strip()),
            "url": getattr(self, "validated_url", self.url_input.text().strip()),
        }


class WebsitesView(QWidget):
    """
    Cyber-dark GUI management view for saved and learned websites in Jarvis.
    Enables user to View, Edit, Delete, Enable/Disable, Test/Open, and Search website shortcuts.
    """

    def __init__(self, jarvis_core=None):
        super().__init__()
        self.core = jarvis_core
        self._store: Optional[WebsiteKnowledgeStore] = None
        self._cached_entries: List[Dict[str, Any]] = []
        self._init_ui()
        self.refresh_websites()

    def _get_store(self) -> WebsiteKnowledgeStore:
        if self._store is not None:
            return self._store
        if self.core and hasattr(self.core, "website_knowledge") and self.core.website_knowledge:
            self._store = self.core.website_knowledge
            return self._store
        db_path = "data/jarvis.db"
        if self.core and hasattr(self.core, "memory_manager") and self.core.memory_manager:
            db_path = getattr(self.core.memory_manager.db, "db_path", db_path)
        self._store = WebsiteKnowledgeStore(db_path=db_path)
        return self._store

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # 1. Top Header Row
        header_row = QHBoxLayout()

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("🌐  SAVED & LEARNED WEBSITES")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #f8fafc; letter-spacing: 1.2px;")
        subtitle = QLabel("Manage website shortcuts, edit URLs, toggle active status, or test open in browser.")
        subtitle.setStyleSheet("font-size: 12px; color: #94a3b8;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_row.addLayout(title_box)

        header_row.addStretch()

        # Real-time search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search alias or URL...")
        self.search_input.setFixedWidth(240)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #131d31;
                border: 1px solid #1e293b;
                border-radius: 8px;
                color: #f8fafc;
                padding: 6px 12px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #00d2ff;
            }
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        header_row.addWidget(self.search_input)

        # "+ Add Website" button
        self.btn_add = QPushButton("+ Add Website")
        self.btn_add.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00d2ff, stop:1 #3a7bd5);
                color: #0b0f19;
                font-weight: 700;
                font-size: 12px;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #33dcff, stop:1 #4f8de6);
            }
        """)
        self.btn_add.clicked.connect(self._open_add_dialog)
        header_row.addWidget(self.btn_add)

        # Refresh button
        self.btn_refresh = QPushButton("↻ Refresh")
        self.btn_refresh.setProperty("class", "chip-btn")
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #00d2ff;
                border-color: #00d2ff;
            }
        """)
        self.btn_refresh.clicked.connect(self.refresh_websites)
        header_row.addWidget(self.btn_refresh)

        main_layout.addLayout(header_row)

        # 2. Main Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "STATUS", "ALIAS / TRIGGER", "NAME", "TARGET URL", "USAGE", "ACTIONS"
        ])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 115)  # Ample space for STATUS badge

        header.setSectionResizeMode(1, QHeaderView.Interactive)
        self.table.setColumnWidth(1, 160)  # Spoken triggers

        header.setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.setColumnWidth(2, 140)  # Canonical name

        header.setSectionResizeMode(3, QHeaderView.Stretch)  # URL stretches to fill available space

        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 85)   # Usage counter

        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 310)  # Full width for all 4 action buttons (Test, Edit, Toggle, Delete)

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #101726;
                border: 1px solid #1e293b;
                border-radius: 8px;
                color: #e2e8f0;
                gridline-color: transparent;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #1a2234;
            }
            QTableWidget::item:selected {
                background-color: #1e293b;
            }
            QHeaderView::section {
                background-color: #0b0f19;
                color: #94a3b8;
                padding: 10px 8px;
                border: none;
                border-bottom: 2px solid #1e293b;
                font-weight: 700;
                font-size: 11px;
                letter-spacing: 0.5px;
            }
        """)

        main_layout.addWidget(self.table)

        # 3. Status footer / count label
        self.footer_label = QLabel("0 websites saved")
        self.footer_label.setStyleSheet("color: #64748b; font-size: 12px;")
        main_layout.addWidget(self.footer_label)

    def _open_add_dialog(self):
        dlg = AddEditWebsiteDialog(parent=self)
        if dlg.exec():
            data = dlg.get_data()
            store = self._get_store()
            store.learn(
                alias=data["alias"],
                url=data["url"],
                canonical_name=data["canonical_name"],
            )
            self.refresh_websites()

    def _open_edit_dialog(self, entry: Dict[str, Any]):
        dlg = AddEditWebsiteDialog(entry=entry, parent=self)
        if dlg.exec():
            data = dlg.get_data()
            store = self._get_store()
            store.update_entry(
                entry_id=entry["id"],
                url=data["url"],
                canonical_name=data["canonical_name"],
                aliases=[data["alias"]] if data["alias"] else None,
            )
            self.refresh_websites()

    def _toggle_entry(self, entry: Dict[str, Any]):
        store = self._get_store()
        store.toggle_enabled(entry["id"])
        self.refresh_websites()

    def _delete_entry(self, entry: Dict[str, Any]):
        name = entry.get("canonical_name") or (entry.get("aliases", ["Website"])[0])
        reply = QMessageBox.question(
            self,
            "Delete Website Shortcut",
            f"Are you sure you want to delete '{name}'?\nJarvis will no longer open this website shortcut.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            store = self._get_store()
            store.delete_by_id(entry["id"])
            self.refresh_websites()

    def _test_open(self, url: str):
        try:
            logger.info("TEST_OPEN_WEBSITE url=%s", url)
            webbrowser.open(url)
        except Exception as e:
            logger.error("Failed to test open URL %s: %s", url, e)
            QMessageBox.warning(self, "Open Failed", f"Could not open browser for URL:\n{url}\n\nError: {e}")

    def _on_search_changed(self, query: str):
        self._populate_table(query.strip().lower())

    def refresh_websites(self):
        store = self._get_store()
        try:
            self._cached_entries = store.list_entries()
        except Exception as e:
            logger.error("Failed to load website entries: %s", e)
            self._cached_entries = []
        self._populate_table(self.search_input.text().strip().lower())

    def _populate_table(self, filter_text: str = ""):
        filtered = []
        for entry in self._cached_entries:
            if not filter_text:
                filtered.append(entry)
                continue
            name = (entry.get("canonical_name") or "").lower()
            url = (entry.get("url") or "").lower()
            aliases = " ".join(entry.get("aliases", [])).lower()
            if filter_text in name or filter_text in url or filter_text in aliases:
                filtered.append(entry)

        self.table.setRowCount(len(filtered))
        self.footer_label.setText(f"{len(filtered)} of {len(self._cached_entries)} websites shown")

        for row_idx, entry in enumerate(filtered):
            self.table.setRowHeight(row_idx, 52)
            is_enabled = entry.get("is_enabled", True)

            # 0. Status Badge
            status_widget = QWidget()
            status_layout = QHBoxLayout(status_widget)
            status_layout.setContentsMargins(6, 4, 6, 4)
            status_layout.setAlignment(Qt.AlignCenter)
            status_badge = QLabel("● ACTIVE" if is_enabled else "○ DISABLED")
            status_badge.setAlignment(Qt.AlignCenter)
            status_badge.setFixedHeight(28)
            status_badge.setFixedWidth(98)
            if is_enabled:
                status_badge.setStyleSheet("""
                    color: #10b981;
                    font-weight: 800;
                    font-size: 11px;
                    letter-spacing: 0.5px;
                    background-color: rgba(16, 185, 129, 0.15);
                    border: 1px solid rgba(16, 185, 129, 0.4);
                    border-radius: 14px;
                """)
            else:
                status_badge.setStyleSheet("""
                    color: #94a3b8;
                    font-weight: 700;
                    font-size: 11px;
                    letter-spacing: 0.5px;
                    background-color: rgba(148, 163, 184, 0.12);
                    border: 1px solid rgba(148, 163, 184, 0.3);
                    border-radius: 14px;
                """)
            status_layout.addWidget(status_badge)
            self.table.setCellWidget(row_idx, 0, status_widget)

            # 1. Alias / Trigger
            aliases = entry.get("aliases", [])
            display_aliases = ", ".join(aliases) if aliases else ""
            item_alias = QTableWidgetItem(display_aliases)
            item_alias.setForeground(QColor("#00d2ff"))
            font = item_alias.font()
            font.setBold(True)
            item_alias.setFont(font)
            item_alias.setToolTip(display_aliases)
            self.table.setItem(row_idx, 1, item_alias)

            # 2. Canonical Name
            item_name = QTableWidgetItem(entry.get("canonical_name", ""))
            item_name.setForeground(QColor("#f8fafc"))
            self.table.setItem(row_idx, 2, item_name)

            # 3. Target URL
            url_str = entry.get("url", "")
            item_url = QTableWidgetItem(url_str)
            item_url.setForeground(QColor("#94a3b8"))
            item_url.setToolTip(url_str)
            self.table.setItem(row_idx, 3, item_url)

            # 4. Usage Count
            usage_cnt = entry.get("usage_count", 0)
            item_usage = QTableWidgetItem(f"{usage_cnt} times")
            item_usage.setTextAlignment(Qt.AlignCenter)
            item_usage.setForeground(QColor("#64748b"))
            self.table.setItem(row_idx, 4, item_usage)

            # 5. Actions Button Group
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            actions_layout.setSpacing(6)
            actions_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            # Test/Open button
            btn_test = QPushButton("🔗 Test")
            btn_test.setToolTip("Open in default browser")
            btn_test.setFixedHeight(30)
            btn_test.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 210, 255, 0.12);
                    color: #00d2ff;
                    border: 1px solid rgba(0, 210, 255, 0.4);
                    border-radius: 6px;
                    padding: 0 10px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: rgba(0, 210, 255, 0.28);
                    border-color: #00d2ff;
                }
            """)
            btn_test.clicked.connect(lambda _, u=url_str: self._test_open(u))
            actions_layout.addWidget(btn_test)

            # Edit button
            btn_edit = QPushButton("✏️ Edit")
            btn_edit.setToolTip("Change URL or display name")
            btn_edit.setFixedHeight(30)
            btn_edit.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #f8fafc;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    padding: 0 10px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #334155;
                    color: #00d2ff;
                    border-color: #00d2ff;
                }
            """)
            btn_edit.clicked.connect(lambda _, e=entry: self._open_edit_dialog(e))
            actions_layout.addWidget(btn_edit)

            # Enable/Disable toggle button
            btn_toggle = QPushButton("Disable" if is_enabled else "Enable")
            btn_toggle.setToolTip("Toggle whether Jarvis recognizes this shortcut")
            btn_toggle.setFixedHeight(30)
            if is_enabled:
                btn_toggle.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(245, 158, 11, 0.12);
                        color: #fbbf24;
                        border: 1px solid rgba(245, 158, 11, 0.35);
                        border-radius: 6px;
                        padding: 0 10px;
                        font-size: 11px;
                        font-weight: 700;
                    }
                    QPushButton:hover {
                        background-color: rgba(245, 158, 11, 0.25);
                        border-color: #f59e0b;
                    }
                """)
            else:
                btn_toggle.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(16, 185, 129, 0.12);
                        color: #34d399;
                        border: 1px solid rgba(16, 185, 129, 0.35);
                        border-radius: 6px;
                        padding: 0 10px;
                        font-size: 11px;
                        font-weight: 700;
                    }
                    QPushButton:hover {
                        background-color: rgba(16, 185, 129, 0.25);
                        border-color: #10b981;
                    }
                """)
            btn_toggle.clicked.connect(lambda _, e=entry: self._toggle_entry(e))
            actions_layout.addWidget(btn_toggle)

            # Delete button
            btn_del = QPushButton("Delete")
            btn_del.setToolTip("Delete this website shortcut")
            btn_del.setFixedHeight(30)
            btn_del.setStyleSheet("""
                QPushButton {
                    background-color: rgba(239, 68, 68, 0.12);
                    color: #f87171;
                    border: 1px solid rgba(239, 68, 68, 0.35);
                    border-radius: 6px;
                    padding: 0 10px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: rgba(239, 68, 68, 0.28);
                    border-color: #ef4444;
                    color: #fca5a5;
                }
            """)
            btn_del.clicked.connect(lambda _, e=entry: self._delete_entry(e))
            actions_layout.addWidget(btn_del)

            self.table.setCellWidget(row_idx, 5, actions_widget)
