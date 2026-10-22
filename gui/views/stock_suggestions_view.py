# gui/views/stock_suggestions_view.py
"""
Stock Suggestions View: Premium Visual Trading & Screener Cockpit for JARVIS V2 (PySide6).
Provides real-time intraday momentum and multi-day swing trade suggestions
with technical confluence, mathematical position sizing, and interactive trade planning.
"""

from datetime import datetime
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QClipboard, QDesktopServices, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget
)

from core.equity_research.stock_screener import (
    StockScreenerEngine,
    StockSuggestion,
    PositionSizeResult
)

logger = logging.getLogger("jarvis.gui.stock_suggestions_view")


class StockScanWorker(QThread):
    """Background scanner thread preventing UI freeze during network/calc operations."""

    scan_finished = Signal(dict)
    scan_failed = Signal(str)

    def __init__(self, force_refresh: bool = False, parent=None):
        super().__init__(parent)
        self.force_refresh = force_refresh

    def run(self) -> None:
        try:
            engine = StockScreenerEngine.get_instance()
            results = engine.get_all_suggestions(force_refresh=self.force_refresh)
            self.scan_finished.emit(results)
        except Exception as exc:
            logger.error(f"StockScanWorker error: {exc}", exc_info=True)
            self.scan_failed.emit(str(exc))


class StockCard(QFrame):
    """Visual card displaying a single Intraday or Swing trade recommendation."""

    def __init__(
        self,
        suggestion: StockSuggestion,
        capital: float = 50000.0,
        risk_pct: float = 1.0,
        on_speak: Optional[Callable[[str], None]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.suggestion = suggestion
        self.capital = capital
        self.risk_pct = risk_pct
        self.on_speak = on_speak
        self._init_ui()

    def _init_ui(self):
        self.setObjectName("stock_card")
        self.setStyleSheet("""
            #stock_card {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 14px;
            }
            #stock_card:hover {
                border: 1px solid #38bdf8;
                background-color: #131d35;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Top Row: Symbol, Name, Badges, CMP
        top_row = QHBoxLayout()

        # Symbol + Company Name
        sym_box = QVBoxLayout()
        sym_box.setSpacing(2)
        sym_lbl = QLabel(self.suggestion.symbol)
        sym_lbl.setStyleSheet("font-size: 17px; font-weight: 800; color: #38bdf8;")
        name_lbl = QLabel(f"{self.suggestion.name} • {self.suggestion.sector}")
        name_lbl.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: 500;")
        sym_box.addWidget(sym_lbl)
        sym_box.addWidget(name_lbl)
        top_row.addLayout(sym_box)

        top_row.addStretch()

        # Trade Type Pill
        is_intra = (self.suggestion.trade_type == "INTRADAY")
        type_bg = "rgba(56, 189, 248, 0.15)" if is_intra else "rgba(168, 85, 247, 0.15)"
        type_color = "#38bdf8" if is_intra else "#c084fc"
        type_border = "#38bdf8" if is_intra else "#a855f7"
        type_txt = "⚡ INTRADAY" if is_intra else "📈 SWING"
        type_badge = QLabel(type_txt)
        type_badge.setStyleSheet(f"background: {type_bg}; color: {type_color}; border: 1px solid {type_border}; border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 700;")
        top_row.addWidget(type_badge)

        # Direction Badge (BUY/SELL)
        is_buy = (self.suggestion.direction == "BUY")
        dir_bg = "rgba(16, 185, 129, 0.15)" if is_buy else "rgba(239, 68, 68, 0.15)"
        dir_color = "#10b981" if is_buy else "#ef4444"
        dir_border = "#10b981" if is_buy else "#ef4444"
        dir_badge = QLabel(f"● {self.suggestion.direction}")
        dir_badge.setStyleSheet(f"background: {dir_bg}; color: {dir_color}; border: 1px solid {dir_border}; border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 800;")
        top_row.addWidget(dir_badge)

        # Confluence Score
        score_badge = QLabel(f"★ {self.suggestion.confluence_score}% MATCH")
        score_badge.setStyleSheet("background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid #f59e0b; border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 700;")
        top_row.addWidget(score_badge)

        layout.addLayout(top_row)

        # 2. Strategy Subtitle
        strat_lbl = QLabel(f"Strategy: {self.suggestion.strategy_name}")
        strat_lbl.setStyleSheet("font-size: 12px; color: #cbd5e1; font-weight: 600;")
        layout.addWidget(strat_lbl)

        # 3. Key Levels Grid
        lvl = self.suggestion.levels
        levels_frame = QFrame()
        levels_frame.setStyleSheet("background-color: #0b1120; border-radius: 8px; border: 1px solid #1e293b; padding: 6px;")
        levels_grid = QGridLayout(levels_frame)
        levels_grid.setContentsMargins(8, 8, 8, 8)
        levels_grid.setHorizontalSpacing(16)
        levels_grid.setVerticalSpacing(4)

        # Headers
        h1 = QLabel("CMP / Entry Zone")
        h1.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 600;")
        h2 = QLabel("Target 1")
        h2.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 600;")
        h3 = QLabel("Target 2")
        h3.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 600;")
        h4 = QLabel("Stop-Loss")
        h4.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 600;")
        h5 = QLabel("Risk : Reward")
        h5.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 600;")

        levels_grid.addWidget(h1, 0, 0)
        levels_grid.addWidget(h2, 0, 1)
        levels_grid.addWidget(h3, 0, 2)
        levels_grid.addWidget(h4, 0, 3)
        levels_grid.addWidget(h5, 0, 4)

        # Values
        v1 = QLabel(f"₹{lvl.cmp:.2f} ({lvl.entry_min:.1f} - {lvl.entry_max:.1f})")
        v1.setStyleSheet("color: #f8fafc; font-size: 13px; font-weight: 700;")
        v2 = QLabel(f"₹{lvl.target_1:.2f} (+{lvl.target_1_pct}%)")
        v2.setStyleSheet("color: #10b981; font-size: 13px; font-weight: 700;")
        v3 = QLabel(f"₹{lvl.target_2:.2f}")
        v3.setStyleSheet("color: #34d399; font-size: 13px; font-weight: 700;")
        v4 = QLabel(f"₹{lvl.stop_loss:.2f} (-{lvl.stop_loss_pct}%)")
        v4.setStyleSheet("color: #ef4444; font-size: 13px; font-weight: 700;")
        v5 = QLabel(lvl.risk_reward)
        v5.setStyleSheet("color: #38bdf8; font-size: 13px; font-weight: 800;")

        levels_grid.addWidget(v1, 1, 0)
        levels_grid.addWidget(v2, 1, 1)
        levels_grid.addWidget(v3, 1, 2)
        levels_grid.addWidget(v4, 1, 3)
        levels_grid.addWidget(v5, 1, 4)

        layout.addWidget(levels_frame)

        # 4. Dynamic Position Sizing Calculator Banner
        pos_calc = StockScreenerEngine.calculate_position_size(
            capital=self.capital,
            risk_pct=self.risk_pct,
            entry_price=lvl.cmp,
            stop_loss_price=lvl.stop_loss,
            target_1_price=lvl.target_1,
            target_2_price=lvl.target_2
        )
        pos_banner = QLabel(
            f"💰 Position Sizing (₹{int(self.capital):,} cap @ {self.risk_pct}% risk): "
            f"<b>Buy {pos_calc.recommended_shares} shares</b> (₹{pos_calc.total_investment:,.0f}) • "
            f"Max Loss: <font color='#ef4444'>-₹{pos_calc.max_loss:,.0f}</font> • "
            f"Gain Target 1: <font color='#10b981'>+₹{pos_calc.potential_profit_t1:,.0f}</font>"
        )
        pos_banner.setStyleSheet("font-size: 11px; color: #94a3b8; padding: 4px 6px; background: rgba(30, 41, 59, 0.4); border-radius: 4px;")
        layout.addWidget(pos_banner)

        # 5. Thesis Points (Collapsible / Concise)
        thesis_text = " • ".join(self.suggestion.thesis_points[:3])
        thesis_lbl = QLabel(f"<b>Thesis:</b> {thesis_text}")
        thesis_lbl.setWordWrap(True)
        thesis_lbl.setStyleSheet("font-size: 11px; color: #94a3b8; line-height: 1.3;")
        layout.addWidget(thesis_lbl)

        # 6. Action Buttons Bar
        act_bar = QHBoxLayout()
        act_bar.setSpacing(8)

        copy_btn = QPushButton("📋 Copy Plan")
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #38bdf8;
            }
        """)
        copy_btn.clicked.connect(self._copy_trade_plan)
        act_bar.addWidget(copy_btn)

        speak_btn = QPushButton("🔊 Speak Setup")
        speak_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #a855f7;
            }
        """)
        speak_btn.clicked.connect(self._speak_trade_plan)
        act_bar.addWidget(speak_btn)

        chart_btn = QPushButton("📊 View Chart")
        chart_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #10b981;
            }
        """)
        chart_btn.clicked.connect(self._open_tradingview_chart)
        act_bar.addWidget(chart_btn)

        act_bar.addStretch()

        time_lbl = QLabel(f"Scanned: {self.suggestion.generated_at}")
        time_lbl.setStyleSheet("font-size: 10px; color: #64748b;")
        act_bar.addWidget(time_lbl)

        layout.addLayout(act_bar)

    def _copy_trade_plan(self):
        """Copies structured trade setup to user clipboard."""
        lvl = self.suggestion.levels
        text = (
            f"⚡ JARVIS Stock Setup: {self.suggestion.symbol} ({self.suggestion.trade_type})\n"
            f"Direction: {self.suggestion.direction}\n"
            f"CMP: ₹{lvl.cmp:.2f}\n"
            f"Entry Zone: ₹{lvl.entry_min:.2f} - ₹{lvl.entry_max:.2f}\n"
            f"Target 1: ₹{lvl.target_1:.2f} (+{lvl.target_1_pct}%)\n"
            f"Target 2: ₹{lvl.target_2:.2f}\n"
            f"Stop-Loss: ₹{lvl.stop_loss:.2f} (-{lvl.stop_loss_pct}%)\n"
            f"Risk:Reward: {lvl.risk_reward}\n"
            f"Strategy: {self.suggestion.strategy_name}\n"
            f"Thesis: {' '.join(self.suggestion.thesis_points[:2])}"
        )
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(text)

    def _speak_trade_plan(self):
        """Speaks trade plan aloud via Jarvis TTS."""
        lvl = self.suggestion.levels
        speech = (
            f"Boss, {self.suggestion.name} par {self.suggestion.trade_type.lower()} setup active hai. "
            f"CMP hai {lvl.cmp:.1f} rupaye. Target 1 hai {lvl.target_1:.1f} rupaye, aur Stop Loss hai {lvl.stop_loss:.1f} rupaye. "
            f"Risk-to-Reward ratio hai {lvl.risk_reward}."
        )
        if self.on_speak:
            self.on_speak(speech)

    def _open_tradingview_chart(self):
        """Opens live interactive TradingView chart for the symbol."""
        sym = self.suggestion.symbol
        url = f"https://in.tradingview.com/chart/?symbol=NSE%3A{sym}"
        QDesktopServices.openUrl(QUrl(url))


class StockSuggestionsView(QWidget):
    """
    Main Sidebar View: Complete Stock Suggestions Screener Cockpit.
    """

    def __init__(self, core: Any = None, on_speak: Optional[Callable[[str], None]] = None, parent=None):
        super().__init__(parent)
        self.core = core
        self.on_speak = on_speak or (lambda text: self.core.speak(text) if self.core and hasattr(self.core, "speak") else None)
        self.engine = StockScreenerEngine.get_instance()

        self._current_tab = "All"
        self._current_sector = "All Sectors"
        self._search_filter = ""
        self._capital = 50000.0
        self._risk_pct = 1.0

        self._all_suggestions: Dict[str, List[StockSuggestion]] = {"all": [], "intraday": [], "swing": []}
        self._worker: Optional[StockScanWorker] = None

        self._init_ui()
        self._start_scan(force_refresh=False)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # 1. Header Row
        header_row = QHBoxLayout()

        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title_lbl = QLabel("📈  Stock Trade Suggestions (Intraday & Swing)")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #f8fafc;")
        sub_lbl = QLabel("Real-time technical screening, multi-factor confluence scoring, and mathematical position sizing for Indian equities.")
        sub_lbl.setStyleSheet("font-size: 12px; color: #94a3b8;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        header_row.addLayout(title_box)

        header_row.addStretch()

        # Market Status Badge
        _, _, is_open = self.engine.get_market_status()
        self.mkt_status_badge = QLabel("🟢 NSE LIVE (09:15 - 15:30 IST)" if is_open else "🔴 NSE CLOSED (Pre-Session Analysis)")
        mkt_style = "background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid #10b981;" if is_open else "background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid #ef4444;"
        self.mkt_status_badge.setStyleSheet(f"{mkt_style} border-radius: 8px; padding: 6px 12px; font-size: 11px; font-weight: 700;")
        header_row.addWidget(self.mkt_status_badge)

        # Refresh / Scan Button
        self.scan_btn = QPushButton("🔄 Scan Market Now")
        self.scan_btn.setStyleSheet("""
            QPushButton {
                background: linear-gradient(135deg, #0284c7, #0369a1);
                background-color: #0284c7;
                color: #ffffff;
                border: 1px solid #38bdf8;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.scan_btn.clicked.connect(lambda: self._start_scan(force_refresh=True))
        header_row.addWidget(self.scan_btn)

        main_layout.addLayout(header_row)

        # 2. Controls & Position Sizing Bar
        ctrl_frame = QFrame()
        ctrl_frame.setStyleSheet("background-color: #0d1527; border: 1px solid #1e293b; border-radius: 10px; padding: 10px;")
        ctrl_layout = QVBoxLayout(ctrl_frame)
        ctrl_layout.setContentsMargins(10, 10, 10, 10)
        ctrl_layout.setSpacing(10)

        # Row A: Trade Type Tabs & Sector Filter & Search
        row_a = QHBoxLayout()
        row_a.setSpacing(10)

        # Type Filter Buttons
        self.btn_all = QPushButton("All Setups")
        self.btn_intra = QPushButton("⚡ Intraday")
        self.btn_swing = QPushButton("📈 Swing Trade")

        for b, tab in [(self.btn_all, "All"), (self.btn_intra, "Intraday"), (self.btn_swing, "Swing")]:
            b.setCheckable(True)
            b.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #94a3b8;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    padding: 6px 14px;
                    font-weight: 600;
                    font-size: 12px;
                }
                QPushButton:checked {
                    background-color: #38bdf8;
                    color: #0f172a;
                    font-weight: 700;
                    border: 1px solid #38bdf8;
                }
            """)
            b.clicked.connect(lambda checked=False, t=tab: self._set_tab(t))

        self.btn_all.setChecked(True)
        row_a.addWidget(self.btn_all)
        row_a.addWidget(self.btn_intra)
        row_a.addWidget(self.btn_swing)

        row_a.addSpacing(12)

        # Sector Dropdown
        row_a.addWidget(QLabel("Sector:"))
        self.sector_combo = QComboBox()
        self.sector_combo.addItems([
            "All Sectors", "Banking", "IT", "Auto", "Energy", "Pharma",
            "FMCG", "Metals & Mining", "Retail", "Power", "Telecom"
        ])
        self.sector_combo.setStyleSheet("""
            QComboBox {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 12px;
            }
        """)
        self.sector_combo.currentTextChanged.connect(self._on_sector_changed)
        row_a.addWidget(self.sector_combo)

        row_a.addSpacing(12)

        # Search Box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Filter stock by ticker or name...")
        self.search_box.setStyleSheet("""
            QLineEdit {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #38bdf8;
            }
        """)
        self.search_box.textChanged.connect(self._on_search_changed)
        row_a.addWidget(self.search_box, stretch=1)

        ctrl_layout.addLayout(row_a)

        # Row B: Interactive Position Sizing Bar
        row_b = QHBoxLayout()
        row_b.setSpacing(12)

        calc_title = QLabel("💰 <b>Position Sizing Calculator:</b>")
        calc_title.setStyleSheet("color: #38bdf8; font-size: 12px;")
        row_b.addWidget(calc_title)

        row_b.addWidget(QLabel("Capital (₹):"))
        self.cap_input = QLineEdit("50000")
        self.cap_input.setFixedWidth(90)
        self.cap_input.setStyleSheet("background-color: #1e293b; color: #f8fafc; border: 1px solid #334155; border-radius: 4px; padding: 4px 8px; font-size: 12px;")
        self.cap_input.textChanged.connect(self._on_capital_changed)
        row_b.addWidget(self.cap_input)

        row_b.addWidget(QLabel("Max Risk (%):"))
        self.risk_input = QLineEdit("1.0")
        self.risk_input.setFixedWidth(55)
        self.risk_input.setStyleSheet("background-color: #1e293b; color: #f8fafc; border: 1px solid #334155; border-radius: 4px; padding: 4px 8px; font-size: 12px;")
        self.risk_input.textChanged.connect(self._on_risk_changed)
        row_b.addWidget(self.risk_input)

        self.calc_summary_lbl = QLabel("Max Risk: ₹500 (1%) • Trade size automatically calculated per card")
        self.calc_summary_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        row_b.addWidget(self.calc_summary_lbl)

        row_b.addStretch()

        ctrl_layout.addLayout(row_b)
        main_layout.addWidget(ctrl_frame)

        # 3. Status & Loading Banner
        self.loading_lbl = QLabel("Scanning market data...")
        self.loading_lbl.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 12px;")
        self.loading_lbl.setVisible(False)
        main_layout.addWidget(self.loading_lbl)

        # 4. Scroll Area with Stock Cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch()

        self.scroll_area.setWidget(self.cards_container)
        main_layout.addWidget(self.scroll_area, stretch=1)

        # 5. Regulatory & SEBI Disclaimer Footer
        footer = QLabel("⚖️ <b>Disclaimer:</b> JARVIS provides automated algorithmic technical screener setups for educational and decision-support purposes only. Not SEBI registered investment advice. Trading in equities, intraday, and derivatives carries market risk.")
        footer.setStyleSheet("color: #64748b; font-size: 11px; padding: 6px 0px;")
        main_layout.addWidget(footer)

    def refresh_data(self, force: bool = False):
        """Public refresh method invoked when tab is navigated to."""
        if not self._all_suggestions.get("all") or force:
            self._start_scan(force_refresh=force)
        else:
            self._render_cards()

    def _start_scan(self, force_refresh: bool = False):
        """Launches asynchronous market scanner."""
        self.loading_lbl.setText("🔄 Scanning NSE Indian market data & calculating technical indicators...")
        self.loading_lbl.setVisible(True)
        self.scan_btn.setEnabled(False)

        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait()

        self._worker = StockScanWorker(force_refresh=force_refresh, parent=self)
        self._worker.scan_finished.connect(self._on_scan_finished)
        self._worker.scan_failed.connect(self._on_scan_failed)
        self._worker.start()

    def _on_scan_finished(self, results: dict):
        self.loading_lbl.setVisible(False)
        self.scan_btn.setEnabled(True)
        self._all_suggestions = results
        self._render_cards()

    def _on_scan_failed(self, error_msg: str):
        self.loading_lbl.setText(f"⚠️ Scan failed: {error_msg}. Using cached fallback data.")
        self.scan_btn.setEnabled(True)

    def _set_tab(self, tab: str):
        self._current_tab = tab
        self.btn_all.setChecked(tab == "All")
        self.btn_intra.setChecked(tab == "Intraday")
        self.btn_swing.setChecked(tab == "Swing")
        self._render_cards()

    def _on_sector_changed(self, text: str):
        self._current_sector = text
        self._render_cards()

    def _on_search_changed(self, text: str):
        self._search_filter = text.strip().lower()
        self._render_cards()

    def _on_capital_changed(self, text: str):
        try:
            val = float(text.replace(",", "").strip())
            if val > 0:
                self._capital = val
                self._update_calc_summary()
                self._render_cards()
        except ValueError:
            pass

    def _on_risk_changed(self, text: str):
        try:
            val = float(text.strip())
            if 0.1 <= val <= 20.0:
                self._risk_pct = val
                self._update_calc_summary()
                self._render_cards()
        except ValueError:
            pass

    def _update_calc_summary(self):
        max_loss = int(self._capital * (self._risk_pct / 100.0))
        self.calc_summary_lbl.setText(f"Max Risk: ₹{max_loss:,} ({self._risk_pct}%) • Trade size automatically calculated per card")

    def _render_cards(self):
        """Renders filtered stock cards based on active trade tab, sector, and search text."""
        # Clear existing cards
        while self.cards_layout.count() > 1:
            child = self.cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Select items
        if self._current_tab == "Intraday":
            items = self._all_suggestions.get("intraday", [])
        elif self._current_tab == "Swing":
            items = self._all_suggestions.get("swing", [])
        else:
            items = self._all_suggestions.get("all", [])

        # Apply sector & search filter
        filtered: List[StockSuggestion] = []
        for s in items:
            if self._current_sector != "All Sectors" and self._current_sector.lower() not in s.sector.lower():
                continue
            if self._search_filter:
                combined_text = f"{s.symbol} {s.name} {s.sector}".lower()
                if self._search_filter not in combined_text:
                    continue
            filtered.append(s)

        if not filtered:
            empty_lbl = QLabel(f"No {self._current_tab} trade setups match current filters. Try changing sector or search query.")
            empty_lbl.setStyleSheet("color: #64748b; font-size: 13px; font-weight: 500; padding: 20px;")
            self.cards_layout.insertWidget(0, empty_lbl)
            return

        for idx, sug in enumerate(filtered):
            card = StockCard(
                suggestion=sug,
                capital=self._capital,
                risk_pct=self._risk_pct,
                on_speak=self.on_speak,
                parent=self.cards_container
            )
            self.cards_layout.insertWidget(idx, card)
