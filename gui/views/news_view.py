# gui/views/news_view.py
"""News Briefing View: Premium visual news briefing for JARVIS V2 (PySide6).

Renders ONLY real data from the structured news-briefing contract
(``NewsQueryResult.to_briefing_dict()``) produced by the authoritative
``LiveNewsEngine``. Never invents summaries, sources, timestamps, or images:
RSS supplies no summary/image, so those affordances are omitted when absent.

Design: deep navy / near-black / cyan accent, rounded cards, thin borders,
Segoe UI — "JARVIS is briefing me", not a generic news portal.
"""

import datetime
import logging
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

logger = logging.getLogger("jarvis.gui.news_view")

# Category tabs shown in the briefing header (All + engine categories).
CATEGORY_TABS: List[str] = [
    "All", "India", "World", "Business", "Technology",
    "Sports", "Science", "Entertainment",
]

# Maps tab label -> natural query routed through the existing news pipeline.
CATEGORY_QUERIES: Dict[str, str] = {
    "All": "aaj ki news batao",
    "India": "India ki news batao",
    "World": "world news batao",
    "Business": "business news batao",
    "Technology": "tech news batao",
    "Sports": "sports news batao",
    "Science": "science news batao",
    "Entertainment": "entertainment news batao",
}

# Section headers with emoji; only non-empty sections are rendered.
SECTION_TITLES: Dict[str, str] = {
    "INDIA": "🇮🇳 India",
    "WORLD": "🌎 World",
    "BUSINESS": "💼 Business",
    "TECHNOLOGY": "💻 Technology",
    "SPORTS": "🏆 Sports",
    "SCIENCE": "🔬 Science",
    "ENTERTAINMENT": "🎬 Entertainment",
    "TOP": "🔴 Top Stories",
}


class NewsFetchWorker(QThread):
    """Background fetcher hitting the existing LiveNewsEngine off the Qt main thread."""

    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, query: str, limit: int = 8, force_refresh: bool = False, parent=None):
        super().__init__(parent)
        self.query = query
        self.limit = limit
        self.force_refresh = force_refresh

    def run(self) -> None:
        try:
            from core.knowledge.news import get_live_news_engine
            engine = get_live_news_engine()
            res = engine.query(self.query, limit=self.limit, force_refresh=self.force_refresh)
            if res.found and res.headlines:
                self.finished.emit(res.to_briefing_dict())
            else:
                self.failed.emit(res.formatted_text or "News service unavailable right now.")
        except Exception as exc:  # never crash the GUI thread
            logger.warning("NewsFetchWorker failed: %s", exc)
            self.failed.emit("News service unavailable right now.")


def _source_time_line(article: Dict[str, Any]) -> str:
    """Builds the 'Source • time' attribution line from real fields only."""
    src = (article.get("source") or "News").strip() or "News"
    pub = (article.get("published_at") or "").strip()
    return f"{src} • {pub}" if pub else src


class NewsCard(QFrame):
    """Compact article card: badge, headline, optional real summary, attribution, actions."""

    def __init__(
        self,
        article: Dict[str, Any],
        on_read: Callable[[Dict[str, Any]], None],
        on_listen: Callable[[str], None],
        on_open_source: Callable[[str], None],
        featured: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.article = article
        self._on_read = on_read
        self._on_listen = on_listen
        self._on_open_source = on_open_source
        self.setProperty("class", "card")
        self.setObjectName("news_featured" if featured else "news_card")
        if featured:
            self.setStyleSheet(
                "#news_featured { background-color: #0E1626; border: 1px solid rgba(0,210,255,0.45);"
                " border-radius: 12px; }"
            )
        self._build(featured)

    def _build(self, featured: bool) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        cat = (self.article.get("category") or "TOP").upper()
        badge = QLabel(cat)
        badge.setStyleSheet(
            "background-color: rgba(0,210,255,0.12); color: #00D2FF;"
            " border: 1px solid rgba(0,210,255,0.4); border-radius: 8px;"
            " padding: 2px 10px; font-size: 10px; font-weight: 800; letter-spacing: 1px;"
        )
        badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        layout.addWidget(badge)

        headline = QLabel(self.article.get("headline", "").strip() or "(headline unavailable)")
        headline.setWordWrap(True)
        headline.setStyleSheet(
            f"color: #EDF2F7; font-size: {'17px' if featured else '14px'}; font-weight: 800;"
            " background: transparent;"
        )
        layout.addWidget(headline)

        # Summary ONLY when the feed actually supplied one — never invented.
        summary = (self.article.get("summary") or "").strip()
        if summary:
            summ_lbl = QLabel(summary)
            summ_lbl.setWordWrap(True)
            summ_lbl.setStyleSheet("color: #8B98AD; font-size: 12px; background: transparent;")
            summ_lbl.setMaximumHeight(60)
            layout.addWidget(summ_lbl)

        meta = QLabel(_source_time_line(self.article))
        meta.setStyleSheet("color: #5B6B82; font-size: 11px; background: transparent;")
        layout.addWidget(meta)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        read_btn = QPushButton("Read")
        read_btn.setProperty("class", "chip-btn")
        read_btn.setCursor(Qt.PointingHandCursor)
        read_btn.clicked.connect(lambda: self._on_read(self.article))
        actions.addWidget(read_btn)

        listen_btn = QPushButton("🔊 Listen")
        listen_btn.setProperty("class", "chip-btn")
        listen_btn.setCursor(Qt.PointingHandCursor)
        listen_btn.clicked.connect(lambda: self._on_listen(self._listen_text()))
        actions.addWidget(listen_btn)

        if (self.article.get("url") or "").strip():
            open_btn = QPushButton("Open Source")
            open_btn.setProperty("class", "chip-btn")
            open_btn.setCursor(Qt.PointingHandCursor)
            open_btn.clicked.connect(lambda: self._on_open_source(self.article["url"]))
            actions.addWidget(open_btn)

        actions.addStretch()
        layout.addLayout(actions)

    def _listen_text(self) -> str:
        """Real article text for the existing TTS pipeline (headline + attribution)."""
        head = self.article.get("headline", "").strip()
        src = (self.article.get("source") or "").strip()
        text = head
        if src:
            text += f" — {src}."
        return text


class NewsView(QWidget):
    """Dedicated premium news briefing view with list + article-detail pages."""

    # Emitted when the view wants the shell to speak text via the existing TTS pipeline.
    listen_requested = Signal(str)
    # Emitted when the view wants the shell to open a source URL.
    open_source_requested = Signal(str)

    def __init__(
        self,
        jarvis_core=None,
        on_listen: Optional[Callable[[str], None]] = None,
        on_open_source: Optional[Callable[[str], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.core = jarvis_core
        self._on_listen_cb = on_listen
        self._on_open_source_cb = on_open_source
        self._briefing: Optional[Dict[str, Any]] = None
        self._active_tab = "All"
        self._tab_buttons: Dict[str, QPushButton] = {}
        self._worker: Optional[NewsFetchWorker] = None
        self._last_query = CATEGORY_QUERIES["All"]
        self.listen_requested.connect(self._dispatch_listen)
        self.open_source_requested.connect(self._dispatch_open_source)
        self._init_ui()

    # ------------------------------------------------------------------ UI --
    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(12)

        # Header: title + date + greeting + refresh + updated stamp.
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        self.title_lbl = QLabel("📰 Today's News")
        self.title_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #f8fafc; background: transparent;")
        title_col.addWidget(self.title_lbl)
        self.date_lbl = QLabel(datetime.date.today().strftime("%d %B %Y"))
        self.date_lbl.setStyleSheet("color: #8B98AD; font-size: 12px; font-weight: 600; background: transparent;")
        title_col.addWidget(self.date_lbl)
        self.greet_lbl = QLabel(self._greeting_text())
        self.greet_lbl.setStyleSheet("color: #5B6B82; font-size: 11px; background: transparent;")
        title_col.addWidget(self.greet_lbl)
        header.addLayout(title_col)
        header.addStretch()

        self.updated_lbl = QLabel("")
        self.updated_lbl.setStyleSheet("color: #5B6B82; font-size: 11px; background: transparent;")
        header.addWidget(self.updated_lbl)

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setProperty("class", "chip-btn")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.setToolTip("Fetch fresh news through the existing news pipeline")
        self.refresh_btn.clicked.connect(self.refresh_news)
        header.addWidget(self.refresh_btn)
        root.addLayout(header)

        # Category tabs.
        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(8)
        for tab in CATEGORY_TABS:
            btn = QPushButton(tab)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, t=tab: self.set_category_filter(t))
            self._tab_buttons[tab] = btn
            tabs_row.addWidget(btn)
        tabs_row.addStretch()
        root.addLayout(tabs_row)
        self._paint_tabs()

        # Stacked pages: 0 = briefing list, 1 = article detail.
        self.pages = QStackedWidget()
        root.addWidget(self.pages, stretch=1)

        # List page (scrollable).
        list_page = QWidget()
        list_layout = QVBoxLayout(list_page)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(2, 2, 2, 2)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch()
        self.scroll.setWidget(self.cards_host)
        list_layout.addWidget(self.scroll)
        self.pages.addWidget(list_page)

        # Detail page (scrollable).
        detail_page = QWidget()
        detail_layout = QVBoxLayout(detail_page)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.detail_host = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_host)
        self.detail_layout.setContentsMargins(2, 2, 2, 2)
        self.detail_layout.setSpacing(10)
        self.detail_layout.addStretch()
        self.detail_scroll.setWidget(self.detail_host)
        detail_layout.addWidget(self.detail_scroll)
        self.pages.addWidget(detail_page)

        self.show_empty("Say 'aaj ki news batao' or press Refresh to load today's briefing.")

    # -------------------------------------------------------------- helpers --
    def _greeting_text(self) -> str:
        try:
            hour = datetime.datetime.now().hour
            part = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
        except Exception:
            part = "Good morning"
        name = "Shailesh"
        try:
            if self.core is not None:
                if getattr(self.core, "learning_manager", None):
                    title = self.core.learning_manager.preferences.get("user_title", "")
                    if title:
                        name = str(title)
                if name == "Shailesh" and getattr(self.core, "memory_manager", None):
                    fact = self.core.memory_manager.get_fact("user_name")
                    if isinstance(fact, dict) and fact.get("value"):
                        name = str(fact["value"])
        except Exception:
            pass
        return f"{part}, {name}"

    def _paint_tabs(self) -> None:
        for tab, btn in self._tab_buttons.items():
            active = (tab == self._active_tab)
            btn.setChecked(active)
            if active:
                btn.setStyleSheet(
                    "QPushButton { background-color: rgba(0,210,255,0.14); color: #00D2FF;"
                    " border: 1px solid #00D2FF; border-radius: 12px; padding: 5px 14px;"
                    " font-size: 12px; font-weight: 700; }"
                )
            else:
                btn.setStyleSheet("")

    def _clear_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _clear_detail(self) -> None:
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    # --------------------------------------------------------------- states --
    def show_loading(self, query: str = "") -> None:
        """Skeleton loading state — never freezes the Qt main thread."""
        self.pages.setCurrentIndex(0)
        self._clear_cards()
        head = QLabel("📰\nFetching today's news...")
        head.setAlignment(Qt.AlignCenter)
        head.setStyleSheet("color: #00D2FF; font-size: 14px; font-weight: 700; background: transparent;")
        self.cards_layout.insertWidget(0, head)
        for _ in range(3):
            skel = QFrame()
            skel.setProperty("class", "card")
            skel.setMinimumHeight(110)
            self.cards_layout.insertWidget(1, skel)
        self.updated_lbl.setText("Fetching…")

    def show_error(self, message: str = "", query: str = "") -> None:
        """Error state — never displays fake/stale news as current."""
        self.pages.setCurrentIndex(0)
        self._clear_cards()
        msg = message or "News service unavailable right now."
        err = QLabel(f"⚠️ {msg}")
        err.setWordWrap(True)
        err.setAlignment(Qt.AlignCenter)
        err.setStyleSheet("color: #EF4444; font-size: 13px; font-weight: 700; background: transparent;")
        self.cards_layout.insertWidget(0, err)
        retry = QPushButton("Retry")
        retry.setProperty("class", "primary-btn")
        retry.setCursor(Qt.PointingHandCursor)
        retry.clicked.connect(lambda: self.fetch_query(query or self._last_query))
        wrap = QHBoxLayout()
        wrap.addStretch()
        wrap.addWidget(retry)
        wrap.addStretch()
        holder = QWidget()
        holder.setLayout(wrap)
        self.cards_layout.insertWidget(1, holder)

    def show_empty(self, message: str = "") -> None:
        self.pages.setCurrentIndex(0)
        self._clear_cards()
        lbl = QLabel(message or "No news available right now.")
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #8B98AD; font-size: 13px; background: transparent;")
        self.cards_layout.insertWidget(0, lbl)

    # ------------------------------------------------------------- briefing --
    def show_briefing(self, briefing: Dict[str, Any]) -> None:
        """Renders a structured briefing dict (real feed data only)."""
        if not isinstance(briefing, dict) or briefing.get("type") != "news":
            self.show_empty("No news available right now.")
            return
        articles = [a for a in briefing.get("articles", []) if isinstance(a, dict) and a.get("headline")]
        if not articles:
            self.show_empty("No news available right now.")
            return
        self._briefing = briefing
        self.pages.setCurrentIndex(0)
        self._clear_cards()

        date_str = briefing.get("date") or datetime.date.today().strftime("%d %B %Y")
        self.date_lbl.setText(str(date_str))
        if briefing.get("is_stale_fallback"):
            self.updated_lbl.setText("Showing saved headlines — live feed unreachable")
        else:
            self.updated_lbl.setText("Updated just now")

        if self._active_tab == "All":
            self._render_grouped(articles)
        else:
            self._render_flat(articles, self._active_tab)

    def _render_grouped(self, articles: List[Dict[str, Any]]) -> None:
        # Featured top story.
        top = articles[0]
        top_lbl = QLabel("🔴 Top Story")
        top_lbl.setStyleSheet("color: #EF4444; font-size: 12px; font-weight: 800; background: transparent;")
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, top_lbl)
        self.cards_layout.insertWidget(
            self.cards_layout.count() - 1,
            NewsCard(top, self.open_article, self._emit_listen, self._emit_open_source, featured=True),
        )
        # Remaining stories grouped by real category; empty categories omitted.
        by_cat: Dict[str, List[Dict[str, Any]]] = {}
        for art in articles[1:]:
            by_cat.setdefault((art.get("category") or "TOP").upper(), []).append(art)
        for cat in ["INDIA", "WORLD", "BUSINESS", "TECHNOLOGY", "SPORTS", "SCIENCE", "ENTERTAINMENT", "TOP"]:
            group = by_cat.get(cat, [])
            if not group:
                continue
            sec = QLabel(SECTION_TITLES.get(cat, cat.title()))
            sec.setStyleSheet("color: #8B98AD; font-size: 13px; font-weight: 800; background: transparent;")
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, sec)
            grid = self._card_grid(group)
            holder = QWidget()
            holder.setLayout(grid)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, holder)

    def _render_flat(self, articles: List[Dict[str, Any]], tab: str) -> None:
        sec = QLabel(f"📰 {tab} — {len(articles)} stor{'y' if len(articles) == 1 else 'ies'}")
        sec.setStyleSheet("color: #8B98AD; font-size: 13px; font-weight: 800; background: transparent;")
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, sec)
        self.cards_layout.insertWidget(
            self.cards_layout.count() - 1,
            NewsCard(articles[0], self.open_article, self._emit_listen, self._emit_open_source, featured=True),
        )
        if len(articles) > 1:
            grid = self._card_grid(articles[1:])
            holder = QWidget()
            holder.setLayout(grid)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, holder)

    def _card_grid(self, articles: List[Dict[str, Any]]) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(10)
        cols = 2 if self.width() >= 1100 else 1
        for i, art in enumerate(articles):
            card = NewsCard(art, self.open_article, self._emit_listen, self._emit_open_source)
            grid.addWidget(card, i // cols, i % cols)
        return grid

    # -------------------------------------------------------------- detail --
    def open_article(self, article: Dict[str, Any]) -> None:
        """Expanded article view built strictly from real returned article data."""
        self._clear_detail()
        back = QPushButton("← Back to News")
        back.setProperty("class", "chip-btn")
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        self.detail_layout.insertWidget(self.detail_layout.count() - 1, back)

        cat = QLabel((article.get("category") or "TOP").upper())
        cat.setStyleSheet(
            "background-color: rgba(0,210,255,0.12); color: #00D2FF;"
            " border: 1px solid rgba(0,210,255,0.4); border-radius: 8px;"
            " padding: 2px 10px; font-size: 10px; font-weight: 800; letter-spacing: 1px;"
        )
        self.detail_layout.insertWidget(self.detail_layout.count() - 1, cat)

        head = QLabel(article.get("headline", "").strip() or "(headline unavailable)")
        head.setWordWrap(True)
        head.setStyleSheet("color: #EDF2F7; font-size: 18px; font-weight: 800; background: transparent;")
        self.detail_layout.insertWidget(self.detail_layout.count() - 1, head)

        meta = QLabel(_source_time_line(article))
        meta.setStyleSheet("color: #5B6B82; font-size: 12px; background: transparent;")
        self.detail_layout.insertWidget(self.detail_layout.count() - 1, meta)

        summary = (article.get("summary") or "").strip()
        if summary:
            body = QLabel(summary)
            body.setWordWrap(True)
            body.setStyleSheet("color: #CBD5E1; font-size: 13px; background: transparent;")
            self.detail_layout.insertWidget(self.detail_layout.count() - 1, body)
            # Key points ONLY when a real summary exists — derived by sentence
            # split, never invented.
            import re as _re
            points = [p.strip() for p in _re.split(r"(?<=[.!?])\s+", summary) if p.strip()][:3]
            if points:
                kp = QLabel("Key points:")
                kp.setStyleSheet("color: #8B98AD; font-size: 12px; font-weight: 800; background: transparent;")
                self.detail_layout.insertWidget(self.detail_layout.count() - 1, kp)
                for p in points:
                    b = QLabel(f"• {p}")
                    b.setWordWrap(True)
                    b.setStyleSheet("color: #94A3B8; font-size: 12px; background: transparent;")
                    self.detail_layout.insertWidget(self.detail_layout.count() - 1, b)
        else:
            hint = QLabel("Full story available at the source link below.")
            hint.setStyleSheet("color: #5B6B82; font-size: 12px; font-style: italic; background: transparent;")
            self.detail_layout.insertWidget(self.detail_layout.count() - 1, hint)

        row = QHBoxLayout()
        row.setSpacing(8)
        listen_btn = QPushButton("🔊 Listen")
        listen_btn.setProperty("class", "primary-btn")
        listen_btn.setCursor(Qt.PointingHandCursor)
        listen_btn.clicked.connect(lambda: self._emit_listen(
            (article.get("headline", "").strip() or "") + (
                f" — {(article.get('source') or '').strip()}." if (article.get("source") or "").strip() else ""
            )
        ))
        row.addWidget(listen_btn)
        if (article.get("url") or "").strip():
            open_btn = QPushButton("Open Source")
            open_btn.setProperty("class", "chip-btn")
            open_btn.setCursor(Qt.PointingHandCursor)
            open_btn.clicked.connect(lambda: self._emit_open_source(article["url"]))
            row.addWidget(open_btn)
        # Save via the existing memory store (real capability, guarded).
        if self.core is not None and getattr(self.core, "memory_manager", None) is not None:
            save_btn = QPushButton("Save")
            save_btn.setProperty("class", "chip-btn")
            save_btn.setCursor(Qt.PointingHandCursor)
            save_btn.clicked.connect(lambda: self._save_article(article, save_btn))
            row.addWidget(save_btn)
        row.addStretch()
        holder = QWidget()
        holder.setLayout(row)
        self.detail_layout.insertWidget(self.detail_layout.count() - 1, holder)
        self.pages.setCurrentIndex(1)

    def _save_article(self, article: Dict[str, Any], btn: QPushButton) -> None:
        try:
            mm = getattr(self.core, "memory_manager", None)
            if mm is None:
                return
            key = f"saved_news_{abs(hash(article.get('headline', ''))) % 10_000_000}"
            value = f"{article.get('headline', '')} | {article.get('source', '')} | {article.get('url', '')}"
            if hasattr(mm, "store_fact"):
                mm.store_fact(key, value, category="saved_news")
                btn.setText("✓ Saved")
            elif hasattr(mm, "save_semantic_fact"):
                mm.save_semantic_fact(key=key, value=value, category="saved_news")
                btn.setText("✓ Saved")
        except Exception as exc:
            logger.debug("Save article failed: %s", exc)

    # --------------------------------------------------------------- fetch --
    def set_category_filter(self, tab: str) -> None:
        if tab not in CATEGORY_TABS:
            return
        self._active_tab = tab
        self._paint_tabs()
        query = CATEGORY_QUERIES.get(tab, CATEGORY_QUERIES["All"])
        # Re-render cached briefing instantly when possible; always refresh in background.
        if self._briefing and tab == "All":
            self.show_briefing(self._briefing)
        self.fetch_query(query)

    def refresh_news(self) -> None:
        """Refresh: fetch fresh news through the existing pipeline (force revalidation)."""
        self.fetch_query(CATEGORY_QUERIES.get(self._active_tab, CATEGORY_QUERIES["All"]), force_refresh=True)

    def fetch_query(self, query: str, force_refresh: bool = False, limit: int = 8) -> None:
        self._last_query = query
        self.show_loading(query)
        self._stop_worker()
        self._worker = NewsFetchWorker(query, limit=limit, force_refresh=force_refresh, parent=self)
        self._worker.finished.connect(self._on_fetch_finished)
        self._worker.failed.connect(self._on_fetch_failed)
        self._worker.start()

    def _on_fetch_finished(self, briefing: Dict[str, Any]) -> None:
        self.show_briefing(briefing)

    def _on_fetch_failed(self, message: str) -> None:
        # Stale-cache honesty is already handled by the engine formatter text;
        # the view surfaces the failure without fabricating fresh results.
        self.show_error(message, self._last_query)

    def _stop_worker(self) -> None:
        try:
            if self._worker is not None and self._worker.isRunning():
                self._worker.wait(1500)
        except Exception:
            pass
        self._worker = None

    # -------------------------------------------------------------- actions --
    def _emit_listen(self, text: str) -> None:
        if self._on_listen_cb is not None:
            try:
                self._on_listen_cb(text)
                return
            except Exception:
                pass
        self.listen_requested.emit(text)

    def _emit_open_source(self, url: str) -> None:
        if self._on_open_source_cb is not None:
            try:
                self._on_open_source_cb(url)
                return
            except Exception:
                pass
        self.open_source_requested.emit(url)

    def _dispatch_listen(self, text: str) -> None:
        # Fallback: speak via core TTS manager when the shell did not wire a callback.
        try:
            mgr = getattr(self.core, "tts_manager", None) if self.core else None
            if mgr is not None and text:
                mgr.speak(text)
        except Exception:
            pass

    def _dispatch_open_source(self, url: str) -> None:
        try:
            if url:
                QDesktopServices.openUrl(QUrl(url))
        except Exception as exc:
            logger.debug("Open source failed: %s", exc)

    # ------------------------------------------------------------ responsive --
    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        # Re-flow the card grid between 2-column (large) and 1-column (small).
        try:
            if self._briefing and self.pages.currentIndex() == 0:
                self.show_briefing(self._briefing)
        except Exception:
            pass
