# gui/views/workflows_view.py
"""Workflows View: Visual Procedural Macros & SOP Routine Launcher."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget
)


class CreateWorkflowDialog(QDialog):
    """Modal dialog for creating and registering a new procedural workflow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Procedural Workflow")
        self.resize(460, 360)
        self.setStyleSheet("""
            QDialog { background-color: #0f172a; color: #f8fafc; }
            QLabel { color: #94a3b8; font-size: 13px; font-weight: bold; }
            QLineEdit, QTextEdit {
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

        layout.addWidget(QLabel("Workflow Identifier (e.g. morning_setup, export_data):"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. focus_mode")
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("Trigger Phrases (comma-separated):"))
        self.triggers_input = QLineEdit()
        self.triggers_input.setPlaceholderText("e.g. focus mode, start coding, kaam shuru karo")
        layout.addWidget(self.triggers_input)

        layout.addWidget(QLabel("Workflow Steps (one step per line):"))
        self.steps_input = QTextEdit()
        self.steps_input.setPlaceholderText("e.g.\nopen vscode\nset volume to 20%\nopen github")
        layout.addWidget(self.steps_input)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("background-color: #475569;")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Register Workflow")
        self.btn_save.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_save)

        layout.addLayout(btn_box)

    def get_data(self):
        name = self.name_input.text().strip().lower().replace(" ", "_")
        triggers = [t.strip() for t in self.triggers_input.text().split(",") if t.strip()]
        raw_steps = [s.strip() for s in self.steps_input.toPlainText().splitlines() if s.strip()]
        steps = [{"description": s, "command": s} for s in raw_steps]
        return {
            "name": name,
            "triggers": triggers or [name.replace("_", " ")],
            "steps": steps,
            "description": f"Custom workflow: {name}"
        }


class WorkflowCard(QFrame):
    """Card displaying a composite procedural workflow and run button."""

    def __init__(self, name: str, triggers: list, steps: list, description: str = "", on_run=None):
        super().__init__()
        self.setProperty("class", "card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # Header
        hdr = QHBoxLayout()
        name_lbl = QLabel(name.replace("_", " ").title())
        name_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #f8fafc;")
        hdr.addWidget(name_lbl)
        hdr.addStretch()

        run_btn = QPushButton("▶ Run Workflow")
        run_btn.setProperty("class", "primary-btn")
        if on_run:
            run_btn.clicked.connect(lambda: on_run(name))
        hdr.addWidget(run_btn)
        layout.addLayout(hdr)

        if description:
            desc_lbl = QLabel(description)
            desc_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-style: italic;")
            layout.addWidget(desc_lbl)

        # Triggers
        triggers_lbl = QLabel(f"Triggers: {', '.join(triggers)}")
        triggers_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(triggers_lbl)

        # Steps list
        steps_box = QVBoxLayout()
        steps_box.setSpacing(4)
        for s in steps:
            desc = s.get("description", f"{s.get('plugin', '')}.{s.get('action', '')}")
            s_lbl = QLabel(f"  • {desc}")
            s_lbl.setStyleSheet("color: #cbd5e1; font-size: 12px;")
            steps_box.addWidget(s_lbl)
        layout.addLayout(steps_box)


class WorkflowsView(QWidget):
    """Workflows Launcher & SOP Routines."""

    def __init__(self, jarvis_core=None, on_execute_workflow=None):
        super().__init__()
        self.core = jarvis_core
        self.on_execute = on_execute_workflow
        self._init_ui()
        self.refresh_workflows()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        hdr = QHBoxLayout()
        title = QLabel("COMPOSITE WORKFLOWS & PROCEDURAL ROUTINES")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #f8fafc; letter-spacing: 1px;")
        hdr.addWidget(title)
        hdr.addStretch()

        self.btn_add_wf = QPushButton("+ Create Workflow")
        self.btn_add_wf.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb);
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover { background: #1d4ed8; }
        """)
        self.btn_add_wf.clicked.connect(self._open_create_dialog)
        hdr.addWidget(self.btn_add_wf)

        self.btn_starters = QPushButton("⚡ Starters")
        self.btn_starters.setProperty("class", "chip-btn")
        self.btn_starters.clicked.connect(self._install_starter_routines)
        hdr.addWidget(self.btn_starters)

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setProperty("class", "chip-btn")
        refresh_btn.clicked.connect(self.refresh_workflows)
        hdr.addWidget(refresh_btn)

        main_layout.addLayout(hdr)

        # Scroll area for workflow cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")
        self.container = QWidget()
        self.container.setStyleSheet("background-color: transparent;")
        self.cards_layout = QVBoxLayout(self.container)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch()
        scroll.setWidget(self.container)

        main_layout.addWidget(scroll)

    def _open_create_dialog(self):
        dlg = CreateWorkflowDialog(self)
        if dlg.exec():
            data = dlg.get_data()
            if data["name"] and data["steps"] and self.core and self.core.memory_manager:
                self.core.memory_manager.procedural.register_workflow(
                    workflow_name=data["name"],
                    trigger_phrases=data["triggers"],
                    steps=data["steps"],
                    description=data["description"]
                )
                self.refresh_workflows()

    def _install_starter_routines(self):
        if not self.core or not self.core.memory_manager:
            return

        routines = [
            (
                "morning_briefing",
                ["good morning", "morning briefing", "din shuru karo"],
                [
                    {"description": "Check system and audio health"},
                    {"description": "Check upcoming tasks and calendar reminders"},
                    {"description": "Present morning briefing summary"}
                ],
                "Daily morning status, reminders, and briefing routine"
            ),
            (
                "coding_setup",
                ["coding setup", "start coding", "dev workspace"],
                [
                    {"description": "Launch preferred Code Editor"},
                    {"description": "Open developer terminal session"},
                    {"description": "Navigate to project repository"}
                ],
                "Prepares the developer desktop workspace with one command"
            ),
            (
                "deep_focus",
                ["deep focus", "focus mode", "distraction free"],
                [
                    {"description": "Lower speaker volume to quiet mode"},
                    {"description": "Set distraction-free window layout"},
                    {"description": "Mute non-essential notifications"}
                ],
                "Zero-interruption focus state for deep intellectual work"
            ),
        ]

        for name, triggers, steps, desc in routines:
            self.core.memory_manager.procedural.register_workflow(
                workflow_name=name,
                trigger_phrases=triggers,
                steps=steps,
                description=desc
            )

        self.refresh_workflows()

    def refresh_workflows(self):
        if not self.core or not self.core.memory_manager:
            return

        workflows = self.core.memory_manager.procedural.get_all_workflows()
        # Clear existing cards except stretch
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not workflows:
            placeholder = QFrame()
            placeholder.setProperty("class", "card")
            p_layout = QVBoxLayout(placeholder)
            p_layout.setContentsMargins(16, 16, 16, 16)
            title_p = QLabel("⚡ No Procedural Workflows Registered Yet")
            title_p.setStyleSheet("color: #38bdf8; font-weight: 700; font-size: 14px;")
            desc_p = QLabel("Procedural workflows allow multi-step SOP routines (e.g. launching workspaces, setting volumes, running macros) to execute with a single voice command.\n\nClick '+ Create Workflow' above to build a custom routine or click '⚡ Starters' to install pre-configured templates.")
            desc_p.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.5;")
            desc_p.setWordWrap(True)
            p_layout.addWidget(title_p)
            p_layout.addWidget(desc_p)
            self.cards_layout.insertWidget(0, placeholder)
            return

        for wf in workflows:
            card = WorkflowCard(
                name=wf["name"],
                triggers=wf["triggers"],
                steps=wf["steps"],
                description=wf.get("description", ""),
                on_run=self._run_wf
            )
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    def _run_wf(self, name: str):
        if self.on_execute:
            self.on_execute(f"run workflow {name}")
        elif self.core:
            self.core.process_input(f"run workflow {name}")
