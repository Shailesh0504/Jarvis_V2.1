# gui/views/memory_view.py
"""Memory View: Visual Inspector for what Jarvis remembers across all cognitive tiers."""

import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)


class AddFactDialog(QDialog):
    """Modal dialog for teaching Jarvis a new persistent fact or preference."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Teach Jarvis New Memory Fact")
        self.resize(420, 260)
        self.setStyleSheet("""
            QDialog { background-color: #0f172a; color: #f8fafc; }
            QLabel { color: #94a3b8; font-size: 13px; font-weight: bold; }
            QLineEdit {
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
        layout.setSpacing(10)

        layout.addWidget(QLabel("Category (e.g. user_preference, work, identity):"))
        self.cat_input = QLineEdit("user_preference")
        layout.addWidget(self.cat_input)

        layout.addWidget(QLabel("Memory Key (e.g. favorite_browser, coffee_choice):"))
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("e.g. owner_nickname, default_ide")
        layout.addWidget(self.key_input)

        layout.addWidget(QLabel("Value / Information:"))
        self.val_input = QLineEdit()
        self.val_input.setPlaceholderText("e.g. Brave, VS Code, Black coffee")
        layout.addWidget(self.val_input)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("background-color: #475569;")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save Memory")
        self.btn_save.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_save)

        layout.addLayout(btn_box)

    def get_data(self):
        return {
            "category": self.cat_input.text().strip() or "facts",
            "key": self.key_input.text().strip(),
            "value": self.val_input.text().strip()
        }


class MemoryView(QWidget):
    """Visual Memory & Facts Inspector with multi-tier cognitive filtering."""

    def __init__(self, jarvis_core=None):
        super().__init__()
        self.core = jarvis_core
        self.active_tier = "facts"
        self._init_ui()
        self.refresh_memories()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("COGNITIVE MEMORY TIERS")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #f8fafc; letter-spacing: 1px;")
        hdr.addWidget(title)
        hdr.addStretch()

        self.btn_add_fact = QPushButton("+ Add Fact")
        self.btn_add_fact.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb);
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover { background: #1d4ed8; }
        """)
        self.btn_add_fact.clicked.connect(self._open_add_dialog)
        hdr.addWidget(self.btn_add_fact)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search memory...")
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(self._on_search)
        hdr.addWidget(self.search_input)

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setProperty("class", "chip-btn")
        refresh_btn.clicked.connect(lambda: self.refresh_memories())
        hdr.addWidget(refresh_btn)

        main_layout.addLayout(hdr)

        # Tier Filter Pills Bar
        pill_layout = QHBoxLayout()
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)

        tiers = [
            ("Facts & Knowledge", "facts"),
            ("Preferences", "preferences"),
            ("Episodic Conversations", "episodic"),
        ]

        for idx, (label, tier_key) in enumerate(tiers):
            btn = QPushButton(label)
            btn.setCheckable(True)
            if idx == 0:
                btn.setChecked(True)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #94a3b8;
                    border: 1px solid #334155;
                    border-radius: 12px;
                    padding: 5px 12px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #0284c7;
                    color: white;
                    border-color: #38bdf8;
                }
                QPushButton:hover:!checked {
                    background-color: #334155;
                    color: #f8fafc;
                }
            """)
            btn.clicked.connect(lambda checked=False, k=tier_key: self._set_tier(k))
            self.filter_group.addButton(btn, idx)
            pill_layout.addWidget(btn)

        pill_layout.addStretch()
        main_layout.addLayout(pill_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["CATEGORY", "KEY", "VALUE", "ACTION"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        main_layout.addWidget(self.table)

    def _set_tier(self, tier_key: str):
        self.active_tier = tier_key
        self.refresh_memories()

    def _open_add_dialog(self):
        dlg = AddFactDialog(self)
        if dlg.exec():
            data = dlg.get_data()
            if data["key"] and data["value"] and self.core and self.core.memory_manager:
                self.core.memory_manager.store_fact(
                    key=data["key"],
                    value=data["value"],
                    category=data["category"]
                )
                self.refresh_memories()

    def refresh_memories(self, query: str = ""):
        if not self.core or not self.core.memory_manager:
            return

        query_str = query.strip().lower()

        if self.active_tier == "preferences":
            self._render_preferences(query_str)
        elif self.active_tier == "episodic":
            self._render_episodic(query_str)
        else:
            self._render_facts(query_str)

    def _render_facts(self, query: str):
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["CATEGORY", "KEY", "VALUE", "ACTION"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)

        if query:
            facts = self.core.memory_manager.search_memories(query, limit=50)
        else:
            facts = self.core.memory_manager.long_term.get_all_facts()

        self.table.setRowCount(len(facts))

        for row, f in enumerate(facts):
            cat_item = QTableWidgetItem(f.get("category", "facts").upper())
            cat_item.setForeground(Qt.cyan)
            self.table.setItem(row, 0, cat_item)

            key_item = QTableWidgetItem(f.get("key", ""))
            key_item.setForeground(Qt.white)
            self.table.setItem(row, 1, key_item)

            val_item = QTableWidgetItem(str(f.get("value", "")))
            self.table.setItem(row, 2, val_item)

            del_btn = QPushButton("Delete")
            del_btn.setProperty("class", "chip-btn")
            del_btn.clicked.connect(lambda checked=False, k=f.get("key", ""): self._delete_fact(k))
            self.table.setCellWidget(row, 3, del_btn)

    def _render_preferences(self, query: str):
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["TIER", "PREFERENCE KEY", "VALUE", "ACTION"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)

        prefs = self.core.memory_manager.long_term.get_all_preferences()
        filtered = []
        for k, v in prefs.items():
            if not query or query in k.lower() or query in str(v).lower():
                filtered.append((k, v))

        self.table.setRowCount(len(filtered))
        for row, (k, v) in enumerate(filtered):
            tier_item = QTableWidgetItem("PREF")
            tier_item.setForeground(Qt.green)
            self.table.setItem(row, 0, tier_item)

            key_item = QTableWidgetItem(k)
            key_item.setForeground(Qt.white)
            self.table.setItem(row, 1, key_item)

            val_item = QTableWidgetItem(str(v))
            self.table.setItem(row, 2, val_item)

            del_btn = QPushButton("Reset")
            del_btn.setProperty("class", "chip-btn")
            del_btn.clicked.connect(lambda checked=False, pk=k: self._delete_preference(pk))
            self.table.setCellWidget(row, 3, del_btn)

    def _render_episodic(self, query: str):
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["TIME", "ROLE", "INTERACTION / CONTENT", "INTENT"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)

        recents = self.core.memory_manager.episodic.get_recent(limit=40)
        filtered = []
        for turn in recents:
            content = turn.get("content", "")
            intent = turn.get("intent", "")
            if not query or query in content.lower() or query in intent.lower():
                filtered.append(turn)

        self.table.setRowCount(len(filtered))
        for row, t in enumerate(filtered):
            ts = t.get("timestamp", 0)
            time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "--"
            time_item = QTableWidgetItem(time_str)
            time_item.setForeground(Qt.gray)
            self.table.setItem(row, 0, time_item)

            role = t.get("role", "user").upper()
            role_item = QTableWidgetItem(role)
            role_item.setForeground(Qt.cyan if role == "USER" else Qt.yellow)
            self.table.setItem(row, 1, role_item)

            content_item = QTableWidgetItem(str(t.get("content", "")))
            self.table.setItem(row, 2, content_item)

            intent_item = QTableWidgetItem(str(t.get("intent", "") or "--"))
            intent_item.setForeground(Qt.green)
            self.table.setItem(row, 3, intent_item)

    def _delete_fact(self, key: str):
        if self.core and self.core.memory_manager:
            self.core.memory_manager.long_term.delete_fact(key)
            self.refresh_memories()

    def _delete_preference(self, key: str):
        if self.core and self.core.memory_manager:
            self.core.memory_manager.db.execute_update(
                "DELETE FROM preferences WHERE key = ?", (key.strip().lower(),)
            )
            self.refresh_memories()

    def _on_search(self, text: str):
        self.refresh_memories(query=text.strip())
