# gui/views/plugins_view.py
"""Plugins View: Visual Plugin Manager with interactive live toggles and diagnostics."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)


class PluginsView(QWidget):
    """Visual Plugin Manager Dashboard with search and capability inspector."""

    def __init__(self, jarvis_core=None):
        super().__init__()
        self.core = jarvis_core
        self._current_catalog = {}
        self._init_ui()
        self.refresh_plugins()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("PLUGIN MANAGER & CAPABILITIES")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #f8fafc; letter-spacing: 1px;")
        hdr.addWidget(title)
        hdr.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter plugins...")
        self.search_input.setFixedWidth(220)
        self.search_input.textChanged.connect(self._filter_table)
        hdr.addWidget(self.search_input)

        refresh_btn = QPushButton("↻ Refresh Plugins")
        refresh_btn.setProperty("class", "chip-btn")
        refresh_btn.clicked.connect(self.refresh_plugins)
        hdr.addWidget(refresh_btn)
        main_layout.addLayout(hdr)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["PLUGIN", "STATUS", "VERSION", "PERMISSIONS", "ACTION"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_row_selected)

        main_layout.addWidget(self.table, stretch=2)

        # Details Panel
        self.details_card = QFrame()
        self.details_card.setProperty("class", "card")
        self.details_layout = QVBoxLayout(self.details_card)
        self.details_layout.setContentsMargins(16, 12, 16, 12)
        self.details_layout.setSpacing(6)

        self.lbl_details_title = QLabel("Select a plugin to inspect actions, intents, and capabilities")
        self.lbl_details_title.setStyleSheet("font-weight: 700; color: #38bdf8; font-size: 13px;")
        self.details_layout.addWidget(self.lbl_details_title)

        self.lbl_details_desc = QLabel("Plugin metadata, actions, and keyword triggers will appear here.")
        self.lbl_details_desc.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.lbl_details_desc.setWordWrap(True)
        self.details_layout.addWidget(self.lbl_details_desc)

        self.lbl_details_actions = QLabel("")
        self.lbl_details_actions.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        self.lbl_details_actions.setWordWrap(True)
        self.details_layout.addWidget(self.lbl_details_actions)

        main_layout.addWidget(self.details_card, stretch=1)

    def refresh_plugins(self):
        if not self.core or not self.core.plugin_manager:
            return

        self._current_catalog = self.core.plugin_manager.get_catalog()
        self._populate_table(self._current_catalog)

    def _populate_table(self, catalog):
        self.table.setRowCount(len(catalog))

        for row, (p_name, manifest) in enumerate(catalog.items()):
            is_enabled = manifest.enabled

            # Col 0: Name
            item_name = QTableWidgetItem(manifest.name.title())
            item_name.setForeground(Qt.white)
            item_name.setData(Qt.UserRole, p_name)
            self.table.setItem(row, 0, item_name)

            # Col 1: Status
            status_text = "● Enabled" if is_enabled else "○ Disabled"
            item_status = QTableWidgetItem(status_text)
            item_status.setForeground(Qt.green if is_enabled else Qt.gray)
            self.table.setItem(row, 1, item_status)

            # Col 2: Version
            item_ver = QTableWidgetItem(manifest.version)
            self.table.setItem(row, 2, item_ver)

            # Col 3: Permissions
            perms_str = ", ".join(f"✓ {p.name if hasattr(p, 'name') else str(p)}" for p in manifest.permissions) if manifest.permissions else "None"
            item_perms = QTableWidgetItem(perms_str)
            item_perms.setForeground(Qt.cyan)
            self.table.setItem(row, 3, item_perms)

            # Col 4: Action Button
            btn_action = QPushButton("Disable" if is_enabled else "Enable")
            btn_action.setProperty("class", "chip-btn")
            btn_action.clicked.connect(lambda checked=False, name=p_name, en=is_enabled: self._toggle_plugin(name, en))
            self.table.setCellWidget(row, 4, btn_action)

    def _filter_table(self, query: str):
        query = query.strip().lower()
        if not query:
            self._populate_table(self._current_catalog)
            return

        filtered = {}
        for p_name, m in self._current_catalog.items():
            name_match = query in p_name.lower() or query in m.name.lower()
            desc_match = query in getattr(m, "description", "").lower()
            action_match = any(query in a.name.lower() or any(query in kw.lower() for kw in a.keywords) for a in getattr(m, "actions", []))
            if name_match or desc_match or action_match:
                filtered[p_name] = m
        self._populate_table(filtered)

    def _on_row_selected(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        item = self.table.item(row, 0)
        if not item:
            return
        p_name = item.data(Qt.UserRole) or item.text().lower()
        manifest = self._current_catalog.get(p_name)
        if not manifest:
            return

        self.lbl_details_title.setText(f"PLUGIN: {manifest.name.upper()} (v{manifest.version}) — Author: {getattr(manifest, 'author', 'Jarvis')}")
        self.lbl_details_desc.setText(f"Description: {getattr(manifest, 'description', 'No description declared.')}")

        actions_list = []
        for a in getattr(manifest, "actions", []):
            kw_str = ", ".join(a.keywords[:4]) if hasattr(a, "keywords") and a.keywords else ""
            actions_list.append(f"• {a.name}: {getattr(a, 'description', '')} (Triggers: {kw_str})")

        intents = getattr(manifest, "supported_intents", [])
        intents_str = f"Supported Intents: {', '.join(intents)}" if intents else "No declared intents"

        actions_text = "\n".join(actions_list[:6]) if actions_list else "No direct action endpoints declared"
        self.lbl_details_actions.setText(f"{intents_str}\n\nActions:\n{actions_text}")

    def _toggle_plugin(self, plugin_name: str, currently_enabled: bool):
        if not self.core or not self.core.plugin_manager:
            return

        if currently_enabled:
            self.core.plugin_manager.disable_plugin(plugin_name)
        else:
            self.core.plugin_manager.enable_plugin(plugin_name)

        self.refresh_plugins()
