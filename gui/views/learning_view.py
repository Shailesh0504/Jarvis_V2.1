# gui/views/learning_view.py
"""Learning View: 5-Layer Learning Dashboard with Human-in-the-Loop Approvals."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)


class LearningView(QWidget):
    """Visual Dashboard for Learned Vocabulary, Habits, and Human-in-the-Loop Approvals."""

    def __init__(self, jarvis_core=None):
        super().__init__()
        self.core = jarvis_core
        self._init_ui()
        self.refresh_learning_data()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("5-LAYER LEARNING & PERSONALIZATION")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #f8fafc; letter-spacing: 1px;")
        hdr.addWidget(title)
        self.btn_teach_word = QPushButton("+ Teach Word")
        self.btn_teach_word.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #4f46e5);
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover { background: #4338ca; }
        """)
        self.btn_teach_word.clicked.connect(self._open_teach_dialog)
        hdr.addWidget(self.btn_teach_word)

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setProperty("class", "chip-btn")
        refresh_btn.clicked.connect(self.refresh_learning_data)
        hdr.addWidget(refresh_btn)
        main_layout.addLayout(hdr)

        # Pending Approvals Card (Human-in-the-Loop)
        self.approvals_frame = QFrame()
        self.approvals_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e1b4b, stop:1 #0f172a);
                border: 1px solid #6366f1;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        self.approvals_layout = QVBoxLayout(self.approvals_frame)
        self.approvals_layout.setSpacing(8)

        app_title = QLabel("💡 PENDING LEARNING APPROVALS (HUMAN-IN-THE-LOOP)")
        app_title.setStyleSheet("font-weight: 800; color: #a5b4fc; font-size: 12px; letter-spacing: 0.5px;")
        self.approvals_layout.addWidget(app_title)

        self.cards_container = QVBoxLayout()
        self.cards_container.setSpacing(8)
        self.approvals_layout.addLayout(self.cards_container)
        main_layout.addWidget(self.approvals_frame)

        # 2 Columns: Left = Vocabulary (Layer 2), Right = Habits & Suggestions (Layer 5)
        cols_layout = QHBoxLayout()
        cols_layout.setSpacing(16)

        # Left Column: Learned Vocabulary
        vocab_box = QVBoxLayout()
        vocab_lbl = QLabel("PERMANENT LEARNED VOCABULARY (LAYER 2)")
        vocab_lbl.setStyleSheet("font-weight: 700; color: #38bdf8; font-size: 12px;")
        vocab_box.addWidget(vocab_lbl)

        self.vocab_table = QTableWidget()
        self.vocab_table.setColumnCount(2)
        self.vocab_table.setHorizontalHeaderLabels(["USER TERM", "MAPPING / APP"])
        self.vocab_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.vocab_table.verticalHeader().setVisible(False)
        self.vocab_table.setEditTriggers(QTableWidget.NoEditTriggers)
        vocab_box.addWidget(self.vocab_table)
        cols_layout.addLayout(vocab_box, stretch=1)

        # Right Column: Habits & Suggestions
        right_box = QVBoxLayout()
        right_box.setSpacing(12)

        habit_lbl = QLabel("RECURRING HABITS & FREQUENCIES (LAYER 5)")
        habit_lbl.setStyleSheet("font-weight: 700; color: #10b981; font-size: 12px;")
        right_box.addWidget(habit_lbl)

        self.habit_table = QTableWidget()
        self.habit_table.setColumnCount(2)
        self.habit_table.setHorizontalHeaderLabels(["HABIT KEY", "OCCURRENCES"])
        self.habit_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.habit_table.verticalHeader().setVisible(False)
        self.habit_table.setEditTriggers(QTableWidget.NoEditTriggers)
        right_box.addWidget(self.habit_table)

        # Proactive Suggestions Panel
        sug_card = QFrame()
        sug_card.setProperty("class", "card")
        sug_card_layout = QVBoxLayout(sug_card)
        sug_title = QLabel("PROACTIVE CONTEXTUAL SUGGESTIONS")
        sug_title.setProperty("class", "card-title")
        self.sug_text = QLabel("• Suggested: Aap usually Sales folder ki latest Excel file open karte hain.\n• Suggested: Automate 'Prepare Sales Report' macro?")
        self.sug_text.setStyleSheet("color: #00d2ff; font-weight: 600; line-height: 1.5; margin-top: 6px;")
        sug_card_layout.addWidget(sug_title)
        sug_card_layout.addWidget(self.sug_text)
        right_box.addWidget(sug_card)

        cols_layout.addLayout(right_box, stretch=1)
        main_layout.addLayout(cols_layout)

    def refresh_learning_data(self):
        if not self.core or not self.core.learning_manager:
            return

        # 1. Load Pending Approvals
        # Clear existing cards
        while self.cards_container.count():
            item = self.cards_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        pending_items = self.core.learning_manager.approval.get_pending_learnings()
        if not pending_items:
            empty_lbl = QLabel("No pending learnings. Jarvis is in sync with verified knowledge.")
            empty_lbl.setStyleSheet("color: #94a3b8; font-style: italic; font-size: 12px; padding: 4px;")
            self.cards_container.addWidget(empty_lbl)
        else:
            for item in pending_items:
                card = QFrame()
                card.setStyleSheet("background: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 8px;")
                c_layout = QHBoxLayout(card)
                c_layout.setContentsMargins(8, 6, 8, 6)

                info_box = QVBoxLayout()
                mapping_lbl = QLabel(f'"{item.original_key}" ➔ {item.proposed_val}')
                mapping_lbl.setStyleSheet("color: #f8fafc; font-weight: 700; font-size: 13px;")
                conf_lbl = QLabel(f"Type: {item.pattern_type.capitalize()}  |  Confidence: {int(item.confidence * 100)}%")
                conf_lbl.setStyleSheet("color: #38bdf8; font-size: 11px;")
                info_box.addWidget(mapping_lbl)
                info_box.addWidget(conf_lbl)
                c_layout.addLayout(info_box, stretch=1)

                # Buttons: Accept, Reject, Edit
                btn_accept = QPushButton("Accept")
                btn_accept.setStyleSheet("background: #10b981; color: white; font-weight: 700; border-radius: 4px; padding: 4px 12px;")
                btn_accept.clicked.connect(lambda _, i_id=item.id: self._on_accept(i_id))

                btn_reject = QPushButton("Reject")
                btn_reject.setStyleSheet("background: #ef4444; color: white; font-weight: 700; border-radius: 4px; padding: 4px 12px;")
                btn_reject.clicked.connect(lambda _, i_id=item.id: self._on_reject(i_id))

                btn_edit = QPushButton("Edit")
                btn_edit.setStyleSheet("background: #3b82f6; color: white; font-weight: 700; border-radius: 4px; padding: 4px 12px;")
                btn_edit.clicked.connect(lambda _, i_id=item.id, cur_val=item.proposed_val: self._on_edit(i_id, cur_val))

                c_layout.addWidget(btn_accept)
                c_layout.addWidget(btn_reject)
                c_layout.addWidget(btn_edit)
                self.cards_container.addWidget(card)

        # 2. Load Permanent Vocabulary
        vocab = self.core.learning_manager.vocabulary.get_all_vocabulary()
        self.vocab_table.setRowCount(len(vocab))
        for row, (term, mapping) in enumerate(vocab.items()):
            t_item = QTableWidgetItem(term)
            t_item.setForeground(Qt.white)
            m_item = QTableWidgetItem(f"→  {mapping}")
            m_item.setForeground(Qt.cyan)
            self.vocab_table.setItem(row, 0, t_item)
            self.vocab_table.setItem(row, 1, m_item)

        # 3. Load Habits
        habits = self.core.learning_manager.habits.get_top_habits(limit=10)
        self.habit_table.setRowCount(len(habits))
        for row, h in enumerate(habits):
            h_key = QTableWidgetItem(h.get("habit_key", ""))
            h_key.setForeground(Qt.white)
            h_freq = QTableWidgetItem(f"{h.get('frequency', 1)} times")
            h_freq.setForeground(Qt.green)
            self.habit_table.setItem(row, 0, h_key)
            self.habit_table.setItem(row, 1, h_freq)

        # 4. Load Dynamic Proactive Suggestions
        suggestions = []
        if hasattr(self.core, "proactive_coordinator") and self.core.proactive_coordinator:
            engine = getattr(self.core.proactive_coordinator, "pattern_engine", None)
            if engine and hasattr(engine, "get_all_patterns"):
                for p in engine.get_all_patterns()[:3]:
                    key = getattr(p, "pattern_key", str(p))
                    conf = int(getattr(p, "confidence", 1.0) * 100)
                    suggestions.append(f"• Proactive Pattern: '{key}' ({conf}% confidence)")

        if not suggestions and habits:
            for h in habits[:3]:
                k = h.get("habit_key", "")
                freq = h.get("frequency", 1)
                suggestions.append(f"• Habit detected: '{k}' invoked {freq} times")

        if suggestions:
            self.sug_text.setText("\n".join(suggestions))
        else:
            self.sug_text.setText("• No proactive habit suggestions yet.\n• Jarvis observes app usage and proposes automations automatically.")

    def _on_accept(self, item_id: str):
        if self.core and self.core.learning_manager:
            self.core.learning_manager.approval.accept_learning(item_id)
            self.refresh_learning_data()

    def _on_reject(self, item_id: str):
        if self.core and self.core.learning_manager:
            self.core.learning_manager.approval.reject_learning(item_id)
            self.refresh_learning_data()

    def _on_edit(self, item_id: str, current_val: str):
        text, ok = QInputDialog.getText(self, "Edit Learning", "Corrected Mapping / Target:", text=current_val)
        if ok and text.strip() and self.core and self.core.learning_manager:
            self.core.learning_manager.approval.edit_learning(item_id, text.strip())
            self.refresh_learning_data()

    def _open_teach_dialog(self):
        term, ok1 = QInputDialog.getText(self, "Teach Custom Vocabulary", "User Word / Slang / Synonym:")
        if not ok1 or not term.strip():
            return
        mapping, ok2 = QInputDialog.getText(self, "Target Mapping", f"What should '{term.strip()}' map to? (e.g. chrome, vlc, calculator):")
        if ok2 and mapping.strip() and self.core and self.core.learning_manager:
            self.core.learning_manager.vocabulary.learn_word(term.strip().lower(), mapping.strip().lower())
            self.refresh_learning_data()
