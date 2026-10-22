# gui/app.py
"""Main PySide6 Application for JARVIS — Authentic Coucou Dynamic Island Companion.

High-fidelity reproduction of the Windows Coucou Dynamic Island interaction model:
- Primary interface: True top-centered Dynamic Island canvas (720x320, frameless, transparent)
- Anchored to the top edge of Windows desktop (y = 0) with multi-monitor & DPI awareness
- Hidden idle state with invisible top wake-strip (240x6)
- Compact pill state (288x32) with embedded animated JARVIS Character and status indicators
- Expanded card state (640x160..240) with Coucou tabbed header and specialized card views
- Coucou Spring-based expansion and cubic-bezier 340ms collapse animation
- Integrated audio sound effects (peek, open, close, blip, finish, error, approve, attach)
- Drag-and-drop file ingestion directly on the island
- Full preservation of all 12 deep studio views via Studio Mode secondary window
- 100% preservation of all existing JARVIS backend, voice, STT, commands, and verification layers
"""

import sys
import os
import logging
import threading
import psutil
from collections import deque
from typing import Optional

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout,
    QLabel, QMainWindow, QMenu, QPushButton, QScrollArea,
    QSizePolicy, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget
)

from core.state import SystemState

from .styles import MODERN_DARK_STYLE
from .sound_effects import Sound
from .island import (
    CoucouIslandWidget, JarvisCharacter, IslandState, IslandStateMachine,
    IslandController, StatusPill, ToolPill, ActiveAppPill, is_affection_or_praise,
    AnchorPositionManager, FloatStore, MochiFloater, FLOAT_SIZE
)
from .island.home_context import HomeStore, HomeKind, LONG_IDLE_SEC, describe_idle

# Deep Studio Views (all 12 preserved)
from .views.dashboard_view import DashboardView
from .views.chat_view import ChatView
from .views.websites_view import WebsitesView
from .views.plugins_view import PluginsView
from .views.memory_view import MemoryView
from .views.learning_view import LearningView
from .views.workflows_view import WorkflowsView
from .views.reminders_view import RemindersView
from .views.activity_log_view import ActivityLogView
from .views.settings_view import SettingsView
from .views.news_view import NewsView
from .views.stock_suggestions_view import StockSuggestionsView


logger = logging.getLogger(__name__)


class UpdateStatusBridge(QObject):
    """Bridge for cross-thread EventBus live update notifications to the Qt UI thread."""
    update_signal = Signal(dict)


class ReminderNotificationBridge(QObject):
    """Bridge for cross-thread EventBus reminder notifications to the Qt UI thread."""
    reminder_signal = Signal(dict)


class NavigationBridge(QObject):
    """Bridge for cross-thread EventBus view navigation to the Qt UI thread."""
    navigate_signal = Signal(dict)


class SemanticBridge(QObject):
    """Generic bridge for cross-thread verified backend events to the Qt UI thread."""
    payload = Signal(dict)


class SuggestionBridge(QObject):
    """Bridge for cross-thread proactive-suggestion alerts to the Qt UI thread."""
    suggestion_signal = Signal(dict)


class TaskWorker(QThread):
    """Background worker thread for non-blocking asynchronous execution."""
    finished = Signal(str, str, object, int)

    def __init__(self, core, user_text: str, tts_engine=None, source: str = "gui", generation_id: int = 0, parent=None):
        super().__init__(parent)
        self.core = core
        self.user_text = user_text
        self.tts_engine = tts_engine
        self.source = source
        self.generation_id = generation_id
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        sensitive_payload = None
        if self.is_cancelled:
            return
        try:
            resp = self.core.process_input(self.user_text, source=self.source)
            if self.is_cancelled:
                return
            if hasattr(self.core, "take_sensitive_display"):
                sensitive_payload = self.core.take_sensitive_display()
        except Exception as e:
            logger.exception("TaskWorker background execution failed: %s", e)
            resp = "Maaf kijiye, is command ko process karte waqt ek takneeki samasya aayi. Kripya dobara koshish karein."
        if not self.is_cancelled:
            self.finished.emit("Jarvis", resp, sensitive_payload, self.generation_id)


class JarvisStudioWindow(QMainWindow):
    """Secondary Desktop Studio Window housing all 12 deep dashboard views."""

    def __init__(self, core, tts_engine=None, parent=None):
        super().__init__(parent)
        self.core = core
        self.tts_engine = tts_engine
        self.setWindowTitle("JARVIS Studio — Command Center")
        self.resize(1100, 680)
        self.setStyleSheet(MODERN_DARK_STYLE)

        # Set Window & Taskbar Icon
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "jarvis_logo.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "jarvis_logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Studio Body with Sidebar & Stack
        self.studio_body = QWidget(central)
        body_layout = QHBoxLayout(self.studio_body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = QFrame(self.studio_body)
        self.sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(6, 12, 6, 12)
        sidebar_layout.setSpacing(4)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        nav_items = [
            ("📊  Dashboard", 0),
            ("💬  Chat", 1),
            ("🌐  Websites", 2),
            ("🧩  Plugins", 3),
            ("🧠  Memory", 4),
            ("🎓  Learning", 5),
            ("⚡  Workflows", 6),
            ("⏰  Reminders", 7),
            ("📝  Activity Log", 8),
            ("⚙️  Settings", 9),
            ("📰  News", 10),
            ("📈  Stock Suggestions", 11),
        ]

        self.nav_buttons = []
        for label, idx in nav_items:
            btn = QPushButton(label)
            btn.setProperty("class", "nav-btn")
            btn.setCheckable(True)
            if idx == 1:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked=False, i=idx: self.switch_tab(i))
            self.nav_group.addButton(btn, idx)
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()
        body_layout.addWidget(self.sidebar)

        # 12 Preserved Views Stack
        self.stack = QStackedWidget(self.studio_body)
        self.view_dashboard = DashboardView(self.core)
        self.view_chat = ChatView(self.core)
        self.view_websites = WebsitesView(self.core)
        self.view_plugins = PluginsView(self.core)
        self.view_memory = MemoryView(self.core)
        self.view_learning = LearningView(self.core)
        self.view_workflows = WorkflowsView(self.core)
        self.view_reminders = RemindersView(self.core)
        self.view_activity_log = ActivityLogView(self.core)
        self.view_settings = SettingsView(self.core, tts_engine=self.tts_engine)
        self.view_news = NewsView(self.core)
        self.view_stock_suggestions = StockSuggestionsView(self.core)

        self.stack.addWidget(self.view_dashboard)        # 0
        self.stack.addWidget(self.view_chat)             # 1
        self.stack.addWidget(self.view_websites)         # 2
        self.stack.addWidget(self.view_plugins)          # 3
        self.stack.addWidget(self.view_memory)           # 4
        self.stack.addWidget(self.view_learning)         # 5
        self.stack.addWidget(self.view_workflows)        # 6
        self.stack.addWidget(self.view_reminders)        # 7
        self.stack.addWidget(self.view_activity_log)     # 8
        self.stack.addWidget(self.view_settings)         # 9
        self.stack.addWidget(self.view_news)             # 10
        self.stack.addWidget(self.view_stock_suggestions)# 11

        body_layout.addWidget(self.stack, stretch=1)
        root_layout.addWidget(self.studio_body, stretch=1)

        # Bottom Status Bar
        self.status_bar = QFrame(central)
        self.status_bar.setObjectName("status_bar")
        sb_layout = QHBoxLayout(self.status_bar)
        sb_layout.setContentsMargins(16, 4, 16, 4)
        self.mic_status = QLabel("● Mic Ready | Waiting for command")
        self.mic_status.setStyleSheet("color: #10b981; font-weight: 600;")
        sb_layout.addWidget(self.mic_status)
        sb_layout.addStretch()
        self.telemetry_lbl = QLabel("CPU 0% | RAM 0.0/0.0GB | Battery -- | STT: Ready | LLM: Local | TTS: Ready")
        self.telemetry_lbl.setStyleSheet("color: #64748b; font-weight: 500;")
        sb_layout.addWidget(self.telemetry_lbl)
        root_layout.addWidget(self.status_bar)

        # Initially hidden in Island Mode
        self.sidebar.hide()
        self.status_bar.hide()

    def switch_tab(self, index: int):
        Sound.play("blip")
        self.stack.setCurrentIndex(index)
        if index < len(self.nav_buttons):
            self.nav_buttons[index].setChecked(True)

        if index == 0:
            self.view_dashboard.refresh_metrics()
        elif index == 2:
            self.view_websites.refresh_websites()
        elif index == 3:
            self.view_plugins.refresh_plugins()
        elif index == 4:
            self.view_memory.refresh_memories()
        elif index == 5:
            self.view_learning.refresh_learning_data()
        elif index == 6:
            self.view_workflows.refresh_workflows()
        elif index == 7:
            if hasattr(self.view_reminders, "load_reminders"):
                self.view_reminders.load_reminders()
        elif index == 8:
            if hasattr(self.view_activity_log, "refresh_logs"):
                self.view_activity_log.refresh_logs()
        elif index == 9:
            if hasattr(self.view_settings, "refresh_settings"):
                self.view_settings.refresh_settings()
        elif index == 10:
            if hasattr(self, "view_news"):
                self.view_news.pages.setCurrentIndex(0)
        elif index == 11:
            if hasattr(self, "view_stock_suggestions"):
                self.view_stock_suggestions.refresh_data()

    def closeEvent(self, event):
        """Closing Settings / Studio ONLY hides this window. It NEVER terminates JARVIS or its services."""
        logger.info("[LIFECYCLE] Settings / Studio window closeEvent received. Hiding studio window; JARVIS application remains alive.")
        event.ignore()
        self.hide()


class JarvisMainWindow(QMainWindow):
    """Top-Edge Floating Dynamic Island Companion for JARVIS (Coucou Windows Interaction Model)."""

    active_mic_updated = Signal(object)

    def __init__(self, jarvis_core):
        super().__init__()
        self.core = jarvis_core
        self.setWindowTitle("JARVIS V2.1 — Dynamic Island Desktop Companion")

        # Ensure QApplication NEVER terminates when child or studio windows close
        app = QApplication.instance()
        if app:
            app.setQuitOnLastWindowClosed(False)
            from PySide6.QtGui import QPalette, QColor
            pal = app.palette()
            pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#141518"))
            pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#f5f6f8"))
            app.setPalette(pal)
            current_style = app.styleSheet() or ""
            if "QToolTip" not in current_style:
                app.setStyleSheet(current_style + "\n" + MODERN_DARK_STYLE)

        # Top-edge frameless translucent floating companion flags
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(720, 320)

        # Set Window & Taskbar Icon
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "jarvis_logo.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "jarvis_logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        app_font = QFont("Segoe UI Variable Text", 10)
        self.setFont(app_font)

        self._active_thread = None
        self._active_worker = None
        self._active_generation_id = 0
        self._message_queue = deque()
        self._tts_worker = None

        self._current_mic_name = "Default Mic"
        self._current_mic_is_bt = False
        self._current_state = "ready"
        self._current_state_details = ""
        self._is_island_mode = True
        self._drag_pos = QPoint()
        self.active_mic_updated.connect(self._on_active_mic_updated)

        # Permanent Floating Anchor manager and position tracking
        self.pos_manager = AnchorPositionManager()
        self.anchor_size = 44
        self._is_anchor_mode = False
        self._drag_start_pos = QPoint()
        self._drag_start_window_pos = QPoint()
        self._is_dragging_anchor = False
        self._drag_threshold = 8

        # Free-floating desktop companion ("Mochi on the desktop") — lazy window,
        # shared outfit, persisted mode. Island FSM remains the sole island authority.
        self.floater = None
        self._float_store = FloatStore()
        self._detach_threshold = 28  # drag on island bot beyond this tears Mochi loose
        self._detach_candidate = False
        self._suppress_anchor_release = False
        self.tray_float_action = None  # created in _init_system_tray when available
        screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        self.anchor_pos = self.pos_manager.load_position(screen_geo, self.anchor_size)

        # 1. State Machine & Controller
        self.fsm = IslandStateMachine(initial_state=IslandState.FLOATING_ANCHOR, parent=self)
        self.controller = IslandController(target_widget=self, fsm=self.fsm, parent=self)

        # 2. TTS Manager initialization
        try:
            from voice.tts import ProsodyConfig, TextToSpeech, TTSManager
            voice_cfg = self.core.config.get("voice", {}) if self.core else {}
            selected_voice = voice_cfg.get("voice_name", "hi-IN-SwaraNeural")
            prosody = ProsodyConfig(voice_name=selected_voice, voice_name_en=selected_voice)
            self.tts = TextToSpeech(engine="native", prosody=prosody)
            self.tts_manager = TTSManager(tts_engine=self.tts)
            self.tts_manager.add_speaking_state_listener(self._on_tts_speaking_state_changed)
            if self.core and hasattr(self.core, "set_tts_manager"):
                self.core.set_tts_manager(self.tts_manager)
            threading.Thread(target=self.tts_manager.warmup, daemon=True, name="TTSWarmupThread").start()
        except Exception as e:
            logger.error(f"TTSManager init failed: {e}")
            self.tts = None
            self.tts_manager = None

        # Build UI Architecture
        self._init_ui()
        self._position_top_center()
        self._init_telemetry_timer()
        self._init_system_tray()

        # Home greeting context: first startup / welcome back / time-based.
        # Decided ONCE per session here — never on a timer (stability rule).
        self._home_store = HomeStore()
        self._last_welcome_back_at = 0.0
        self._init_home_greeting()

        # Connect FSM to UI
        self.fsm.add_listener(self._on_island_fsm_transition)

        # 3. Audio Device Manager hotplug watcher
        try:
            from voice.device_manager import AudioDeviceManager
            self._adm = AudioDeviceManager()
            if self.tts_manager:
                self._adm.set_tts_engine(self.tts_manager)
            self._adm.start_hotplug_watcher(poll_interval=2.0)
            self._adm_listener = lambda dev: self.active_mic_updated.emit(dev)
            self._adm.register_device_change_listener(self._adm_listener, notify_immediate=True)
        except Exception as e:
            logger.debug(f"AudioDeviceManager watcher startup error: {e}")
            self._adm = None

        if self.core:
            self.core.has_active_gui = True

        # Wire live EventBus events to the GUI thread
        self._update_bridge = UpdateStatusBridge()
        self._update_bridge.update_signal.connect(self._on_update_status_event)
        if self.core and hasattr(self.core, "event_bus") and self.core.event_bus:
            self.core.event_bus.subscribe(
                "system.update.status",
                lambda evt: self._update_bridge.update_signal.emit(evt.data or {})
            )

        self._reminder_bridge = ReminderNotificationBridge()
        self._reminder_bridge.reminder_signal.connect(self._on_reminder_triggered_event)
        if self.core and hasattr(self.core, "event_bus") and self.core.event_bus:
            self.core.event_bus.subscribe(
                "reminder.triggered",
                lambda evt: self._reminder_bridge.reminder_signal.emit(evt.data or {})
            )

        self._nav_bridge = NavigationBridge()
        self._nav_bridge.navigate_signal.connect(self._on_navigation_event)
        if self.core and hasattr(self.core, "event_bus") and self.core.event_bus:
            self.core.event_bus.subscribe(
                "gui.navigate",
                lambda evt: self._nav_bridge.navigate_signal.emit(evt.data or {})
            )

        # Proactive suggestions previously never reached the GUI — bridge them so
        # a loose Mochi can fly home when something needs the user's attention.
        self._suggestion_bridge = SuggestionBridge()
        self._suggestion_bridge.suggestion_signal.connect(self._on_suggestion_proposed_event)
        if self.core and hasattr(self.core, "event_bus") and self.core.event_bus:
            try:
                self.core.event_bus.subscribe(
                    "proactive.suggestion.proposed",
                    lambda evt: self._suggestion_bridge.suggestion_signal.emit(
                        evt.data if isinstance(evt.data, dict) else {})
                )
            except Exception as e:
                logger.debug(f"Suggestion bridge subscription failed: {e}")

        # Verified execution outcomes → single finish/error chime per turn.
        # policy.evaluated(allowed) → work: only real execution plans reach the
        # action service, so chat-only turns never trigger work sounds.
        self._exec_bridge = SemanticBridge()
        self._exec_bridge.payload.connect(self._on_execution_completed_event)
        self._policy_bridge = SemanticBridge()
        self._policy_bridge.payload.connect(self._on_policy_evaluated_event)
        self._approval_bridge = SemanticBridge()
        self._approval_bridge.payload.connect(self._on_agent_approval_required_event)
        if self.core and hasattr(self.core, "event_bus") and self.core.event_bus:
            try:
                self.core.event_bus.subscribe(
                    "execution.completed",
                    lambda evt: self._exec_bridge.payload.emit(
                        evt.data if isinstance(evt.data, dict) else {})
                )
                self.core.event_bus.subscribe(
                    "policy.evaluated",
                    lambda evt: self._policy_bridge.payload.emit(
                        evt.data if isinstance(evt.data, dict) else {})
                )
                self.core.event_bus.subscribe(
                    "agent.approval.required",
                    lambda evt: self._approval_bridge.payload.emit(
                        evt.data if isinstance(evt.data, dict) else {})
                )
            except Exception as e:
                logger.debug(f"Execution sound bridges failed: {e}")

        self._apply_sound_settings()
        self._auto_start_voice_if_configured()
        Sound.initialize()
        self.set_system_state("ready")

        # Coucou choreographed startup greeting ceremony (live mode only)
        if not (os.environ.get("QT_QPA_PLATFORM") == "offscreen" or os.environ.get("PYTEST_CURRENT_TEST")):
            QTimer.singleShot(150, self.play_startup_greeting)

        # Mochi comes back where you left him: restore a loose floater, if any.
        if not (os.environ.get("QT_QPA_PLATFORM") == "offscreen" or os.environ.get("PYTEST_CURRENT_TEST")):
            try:
                QTimer.singleShot(600, self._restore_loose_mochi)
            except Exception as e:
                logger.debug(f"Float restore scheduling failed: {e}")

    def play_startup_greeting(self):
        """Plays choreographed startup greeting ceremony anchored to floating icon."""
        screen = self.pos_manager.get_active_screen(self.anchor_pos)
        screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        exp_geo = self.pos_manager.calculate_expanded_geometry(
            self.anchor_pos, screen_geo, anchor_size=self.anchor_size, island_size=QSize(720, 320)
        )
        self._is_anchor_mode = False
        self.setFixedSize(720, 320)
        self.setGeometry(exp_geo)
        self.island.setFixedSize(720, 320)
        self.island.play_startup_greeting()
        self.show()
        self.raise_()

    def _position_top_center(self):
        """Positions the window attached to the floating anchor on active screen."""
        screen = self.pos_manager.get_active_screen(self.anchor_pos)
        screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        if self._is_anchor_mode:
            self.setGeometry(self.anchor_pos.x(), self.anchor_pos.y(), self.anchor_size, self.anchor_size)
        else:
            exp_geo = self.pos_manager.calculate_expanded_geometry(
                self.anchor_pos, screen_geo, self.anchor_size, QSize(720, 320)
            )
            self.setGeometry(exp_geo)

    def _init_ui(self):
        central = QWidget(self)
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── 1. The Master Coucou Dynamic Island Widget ────────────────────────
        self.island = CoucouIslandWidget(fsm=self.fsm, parent=central)
        self.island.core = self.core
        self.island.tts_manager = self.tts_manager
        if hasattr(self.core, "config_path"):
            self.island.view_settings.config_path = self.core.config_path
        try:
            self.island.load_settings_from_config(self.core.config if hasattr(self.core, "config") else None)
        except Exception:
            pass
        self.island.settings_requested.connect(self.toggle_island_mode)
        self.island.mic_toggled.connect(self._on_island_mic_toggled)
        self.island.speaker_toggled.connect(self._on_island_speaker_toggled)
        self.island.close_requested.connect(self._on_island_close_requested)
        self.island.reset_position_requested.connect(self.reset_anchor_position)
        self.island.collapsed.connect(self._on_island_collapsed)
        self.island.expanded.connect(self._on_island_expanded)
        self.island.view_chat.message_submitted.connect(self._handle_user_message)
        self.island.view_approval.decision_made.connect(self._on_confirmation_action)
        self.island.view_question.option_selected.connect(self._on_question_option_selected)
        # Mirror appearance intensity onto the loose companion (island handles its own bot).
        self.island.view_settings.animation_changed.connect(self._on_island_animation_changed)
        # Dead-before: volume slider never reached the engine. Now: apply + persist.
        self.island.view_settings.volume_changed.connect(self._on_island_volume_changed)
        self.island.view_settings.settings_saved.connect(self._on_island_settings_saved)
        root_layout.addWidget(self.island)

        # Install event filter on window, island, and character for click-vs-drag detection
        self.installEventFilter(self)
        self.island.installEventFilter(self)
        if hasattr(self.island, "character") and self.island.character:
            self.island.character.installEventFilter(self)

        # ── 2. The Secondary Studio Window (Housing all 12 views) ─────────────
        self.studio_window = JarvisStudioWindow(self.core, tts_engine=self.tts_manager, parent=None)

        # Connect Studio chat view to user message handler
        self.studio_window.view_chat.message_submitted.connect(self._handle_user_message)
        self.studio_window.view_chat.voice_message_submitted.connect(self._handle_voice_message)
        self.studio_window.view_chat.remember_requested.connect(self._on_remember_requested)
        self.studio_window.view_chat.open_news_requested.connect(self._on_open_news_requested)
        self.studio_window.view_chat.play_briefing_requested.connect(self._on_play_briefing_requested)
        self.studio_window.view_chat.audio_level_updated.connect(self._on_live_audio_level)

        # Synchronize live voice thread changes back to Island header & controller
        self.studio_window.view_chat.voice_listening_changed.connect(self._on_voice_listening_changed)
        self.studio_window.view_chat.mute_toggled.connect(self._on_voice_mute_changed)

        # ── 3. Backward-Compatibility Aliases for Tests & Legacy Callers ──────
        self.sidebar = self.studio_window.sidebar
        self.stack = self.studio_window.stack
        self.nav_buttons = self.studio_window.nav_buttons
        self.studio_body = self.studio_window.studio_body
        self.status_bar = self.studio_window.status_bar
        self.mic_status = self.studio_window.mic_status
        self.telemetry_lbl = self.studio_window.telemetry_lbl

        self.view_dashboard = self.studio_window.view_dashboard
        self.view_chat = self.studio_window.view_chat
        self.view_websites = self.studio_window.view_websites
        self.view_plugins = self.studio_window.view_plugins
        self.view_memory = self.studio_window.view_memory
        self.view_learning = self.studio_window.view_learning
        self.view_workflows = self.studio_window.view_workflows
        self.view_reminders = self.studio_window.view_reminders
        self.view_activity_log = self.studio_window.view_activity_log
        self.view_settings = self.studio_window.view_settings
        self.view_news = self.studio_window.view_news
        self.view_stock_suggestions = self.studio_window.view_stock_suggestions

        self.character = self.island.character
        self.mochi = self.island.character
        self.status_pill = self.island.view_overview.pill_status
        self.status_badge = self.island.view_overview.pill_status.label
        self.active_app_pill = self.island.view_overview.pill_app
        self.model_pill = self.island.view_overview.pill_engine
        self.mic_pill = self.island.view_overview.pill_mic

        # Control button handles
        self.island_btn = QPushButton("🪟 Studio Mode")
        self.island_btn.clicked.connect(self.toggle_island_mode)
        self.collapse_btn = QPushButton("▲")
        self.collapse_btn.clicked.connect(self._collapse_to_idle)
        self.chat_toggle_btn = QPushButton("💬")
        self.chat_toggle_btn.clicked.connect(self._toggle_chat_surface)

        self.surface_container = self.island.expanded_container
        self.header = self.island.header
        self.context_stack = self.island.view_stack
        self.island_chat = self.island.view_chat
        self.activity_card = self.island.view_overview
        self.confirmation_card = self.island.view_approval
        self.question_card = self.island.view_question
        self.file_drop = self.island.view_drop

        self.update_status_label = QLabel("")
        self.update_status_label.setVisible(False)

    def visual_bounds(self) -> QRect:
        """Exact bounding rectangle where visible island/anchor graphics are drawn."""
        if self._is_anchor_mode:
            return QRect(2, 2, self.anchor_size - 4, self.anchor_size - 4)
        if hasattr(self, "island") and hasattr(self.island, "visual_bounds"):
            return self.island.visual_bounds()
        return QRect(40, 0, 640, 160)

    def interaction_bounds(self) -> QRect:
        """Active pointer hit-test region (visual bounds + forgiving margin)."""
        vb = self.visual_bounds()
        hit_margin = 8  # Forgiving hit margin ensuring right-edge buttons and close button are comfortably captured
        return QRect(
            max(0, vb.x() - hit_margin),
            max(0, vb.y() - hit_margin),
            min(self.width(), vb.width() + hit_margin * 2),
            min(self.height(), vb.height() + hit_margin * 2)
        )

    def window_bounds(self) -> QRect:
        """Current OS window bounds (geometry on desktop screen)."""
        return self.geometry()

    def expanded_island_bounds(self) -> QSize:
        """Target dimensions when Dynamic Island is fully expanded."""
        return QSize(720, 320)

    def is_pinned_or_important(self) -> bool:
        """Returns True if the island/window is in an important/interactive state that blocks auto-collapse/auto-hide."""
        if hasattr(self, "island") and hasattr(self.island, "is_pinned_or_important"):
            if self.island.is_pinned_or_important():
                return True
        if self._active_worker and self._active_worker.isRunning():
            return True
        if hasattr(self, "tts_manager") and self.tts_manager and self.tts_manager.is_speaking():
            return True
        return False

    # Coucou camelCase aliases
    visualBounds = visual_bounds
    interactionBounds = interaction_bounds
    windowBounds = window_bounds
    expandedIslandBounds = expanded_island_bounds

    def nativeEvent(self, event_type, message):
        """Win32 precision hit-testing: pass all clicks outside interactionBounds through to underlying desktop/browser."""
        if event_type == b"windows_generic_MSG":
            try:
                import ctypes
                from ctypes import wintypes
                from PySide6.QtGui import QCursor
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 132:  # WM_NCHITTEST
                    # While dragging anchor, keep mouse capture
                    if getattr(self, "_is_dragging_anchor", False):
                        return True, 1  # HTCLIENT

                    hit_rect = self.interaction_bounds()

                    # 1. Authoritative Qt logical cursor coordinates (DPI-independent)
                    cursor_pt = QCursor.pos()
                    local_pt = self.mapFromGlobal(cursor_pt)
                    if hit_rect.contains(local_pt):
                        return True, 1  # HTCLIENT

                    # 2. Extract coordinates from Windows lParam (physical pixels under display scaling)
                    raw_x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    raw_y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value

                    # Direct unscaled mapping (for logical coords in lParam)
                    direct_local_pt = self.mapFromGlobal(QPoint(raw_x, raw_y))
                    if hit_rect.contains(direct_local_pt):
                        return True, 1  # HTCLIENT

                    # Apply active display pixel ratio if OS uses DPI scaling (e.g. 1.25x, 1.5x)
                    active_dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
                    if active_dpr > 1.0:
                        scaled_local_pt = self.mapFromGlobal(QPoint(int(raw_x / active_dpr), int(raw_y / active_dpr)))
                        if hit_rect.contains(scaled_local_pt):
                            return True, 1  # HTCLIENT

                    # OUTSIDE visible island -> pass clicks directly through to underlying desktop/browser!
                    return True, -1  # HTTRANSPARENT
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def _init_system_tray(self):
        """Initializes minimal system tray icon and menu."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = self.windowIcon()
        self.tray_icon = QSystemTrayIcon(icon, self)
        self._tray_menu = QMenu(self)

        self.tray_status_action = QAction("● JARVIS: Ready", self)
        self.tray_status_action.setEnabled(False)
        self._tray_menu.addAction(self.tray_status_action)
        self._tray_menu.addSeparator()

        open_action = QAction("Open Island", self)
        open_action.triggered.connect(self._restore_and_open_island)
        self._tray_menu.addAction(open_action)

        chat_action = QAction("Chat with JARVIS", self)
        chat_action.triggered.connect(self._restore_and_open_chat)
        self._tray_menu.addAction(chat_action)

        studio_action = QAction("Studio Command Center", self)
        studio_action.triggered.connect(self.toggle_island_mode)
        self._tray_menu.addAction(studio_action)

        self.tray_float_action = QAction("Float Mochi on desktop", self)
        self.tray_float_action.triggered.connect(self._on_tray_float_toggled)
        self._tray_menu.addAction(self.tray_float_action)

        self._tray_menu.addSeparator()
        quit_action = QAction("Quit JARVIS", self)
        quit_action.triggered.connect(self._terminate_application)
        self._tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(self._tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._restore_and_open_island()

    def _on_tray_float_toggled(self):
        """Tray switch: set Mochi loose near the island, or dock him home."""
        try:
            if self.floater is not None and self.floater.is_loose:
                self._dock_mochi("tray_toggle")
            else:
                home = self._mochi_home_center()
                screen = self.pos_manager.get_active_screen(home)
                geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
                at = self.pos_manager.clamp_position(
                    QPoint(home.x() - FLOAT_SIZE // 2, home.y() + 60),
                    geo, FLOAT_SIZE)
                self._detach_mochi_to_desktop(
                    QPoint(at.x() + FLOAT_SIZE // 2, at.y() + FLOAT_SIZE // 2))
        except Exception as e:
            logger.debug(f"Tray float toggle failed: {e}")

    def _refresh_tray_float_action(self):
        try:
            if hasattr(self, "tray_float_action") and self.tray_float_action:
                loose = self.floater is not None and self.floater.is_loose
                self.tray_float_action.setText(
                    "Dock Mochi home" if loose else "Float Mochi on desktop")
        except Exception:
            pass

    def _restore_and_open_island(self):
        self.controller.set_island_visible(True)
        self.expand_island("overview")

    def _restore_and_open_chat(self):
        self.controller.set_island_visible(True)
        self.expand_island("chat")

    def _on_island_fsm_transition(self, old_state: IslandState, new_state: IslandState):
        """Coordinates UI layouts when the IslandStateMachine transitions."""
        self.character.set_island_state(new_state)

        if hasattr(self, "tray_status_action"):
            self.tray_status_action.setText(f"● JARVIS: {new_state.value.capitalize()}")

    def _init_home_greeting(self) -> None:
        """One-shot session greeting: first startup > welcome back > time-based."""
        try:
            view = getattr(getattr(self, "island", None), "view_overview", None)
            if view is None:
                return
            if self._home_store.is_first_startup():
                view.show_home(HomeKind.FIRST_STARTUP)
            else:
                idle = self._home_store.idle_seconds() or 0.0
                if idle > LONG_IDLE_SEC:
                    import time as _time
                    self._last_welcome_back_at = _time.time()
                    view.show_home(HomeKind.WELCOME_BACK, describe_idle(idle))
                else:
                    view.show_home(HomeKind.TIME)
            self._home_store.mark_active()
        except Exception as e:
            logger.debug(f"[HOME] init greeting failed: {e}")

    def _maybe_welcome_back(self) -> None:
        """Long-idle return to Home: welcome back (at most once per idle span)."""
        try:
            import time as _time
            idle = self._home_store.idle_seconds() or 0.0
            if idle > LONG_IDLE_SEC and (_time.time() - self._last_welcome_back_at) > LONG_IDLE_SEC:
                self._last_welcome_back_at = _time.time()
                self.island.view_overview.show_home(HomeKind.WELCOME_BACK, describe_idle(idle))
        except Exception as e:
            logger.debug(f"[HOME] welcome-back check failed: {e}")

    def expand_island(self, view_name: str = "overview"):
        """Expands Dynamic Island anchored to the floating JARVIS icon."""
        if not self._is_anchor_mode and self.width() == 720 and self.height() == 320 and self.island._current_view == view_name and self.island._current_mode == "expanded":
            return
        try:
            if hasattr(self, "controller") and self.controller:
                self.controller.set_active_view(view_name)
        except Exception:
            pass
        screen = self.pos_manager.get_active_screen(self.anchor_pos)
        screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        exp_geo = self.pos_manager.calculate_expanded_geometry(
            self.anchor_pos, screen_geo, anchor_size=self.anchor_size, island_size=QSize(720, 320)
        )
        self._is_anchor_mode = False
        self.setFixedSize(720, 320)
        self.setGeometry(exp_geo)
        self.island.setFixedSize(720, 320)
        self.island.expand_to_view(view_name)
        if view_name == "overview":
            self._maybe_welcome_back()
        self.fsm.transition_to(IslandState.EXPANDED_ISLAND, reason="expand_island")
        self.controller.set_island_expanded(True)
        self.show()
        self.raise_()

    def collapse_to_anchor(self):
        """Collapses expanded Dynamic Island back into the permanent floating JARVIS icon."""
        if self._is_anchor_mode and self.width() == self.anchor_size and self.height() == self.anchor_size and self.island._current_mode == "anchor":
            return
        screen = self.pos_manager.get_active_screen(self.anchor_pos)
        screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        self.anchor_pos = self.pos_manager.clamp_position(self.anchor_pos, screen_geo, self.anchor_size, min_visible=20)

        self._is_anchor_mode = True
        if self.island._current_mode != "anchor":
            self.island.collapse_to_anchor()
        self.setGeometry(self.anchor_pos.x(), self.anchor_pos.y(), self.anchor_size, self.anchor_size)
        self.setFixedSize(self.anchor_size, self.anchor_size)
        self.island.setFixedSize(self.anchor_size, self.anchor_size)
        self.fsm.transition_to(IslandState.COLLAPSED_ANCHOR, reason="collapse_to_anchor")
        self.controller.set_island_expanded(False)
        self.show()
        self.raise_()

    def reset_anchor_position(self):
        """Restores default TOP-CENTER anchor position and persists it."""
        screen = self.pos_manager.get_active_screen(self.anchor_pos)
        screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        self.anchor_pos = self.pos_manager.default_position(screen_geo, self.anchor_size)
        self.pos_manager.save_position(self.anchor_pos, screen_geo, self.anchor_size)
        if self._is_anchor_mode:
            self.move(self.anchor_pos)
        else:
            exp_geo = self.pos_manager.calculate_expanded_geometry(
                self.anchor_pos, screen_geo, anchor_size=self.anchor_size, island_size=QSize(720, 320)
            )
            self.setGeometry(exp_geo)

    # ── Mochi on the desktop: free-float lifecycle (island FSM untouched) ─────
    def _ensure_floater(self):
        """Lazily builds the 120pt free companion; shares ONE outfit manager."""
        if self.floater is not None:
            return self.floater
        from PySide6.QtWidgets import QApplication as _QA
        floater = MochiFloater(parent=None, size=FLOAT_SIZE, store=self._float_store)
        try:
            # One shared AccessoryManager object → outfit live in both homes, never copied.
            floater.character.accessories = self.island.character.accessories
            floater.character.set_animation_intensity(
                getattr(self.island.character, "_animation_intensity", 1.0))
            floater.character.set_system_state(getattr(self, "_current_state", "ready"))
        except Exception as e:
            logger.debug(f"Floater character sync failed: {e}")
        floater.dock_requested.connect(lambda: self._dock_mochi("floater_request"))
        floater.chat_requested.connect(lambda: self.expand_island("chat"))
        floater.dock_zone_provider = lambda: self.geometry()
        try:
            saved = self._float_store.load()
            floater.follow_enabled = bool(saved.get("follow", True))
        except Exception:
            pass
        self.floater = floater
        return floater

    def _mochi_home_center(self) -> QPoint:
        """Island anchor center — the spot Mochi flies home to."""
        try:
            return QPoint(self.anchor_pos.x() + self.anchor_size // 2,
                          self.anchor_pos.y() + self.anchor_size // 2)
        except Exception:
            return QPoint(960, 12)

    def _detach_mochi_to_desktop(self, global_pos: QPoint, follow: Optional[bool] = None):
        """Tears Mochi loose: 120pt floater at cursor, island collapses to empty nest."""
        try:
            floater = self._ensure_floater()
            screen = self.pos_manager.get_active_screen(global_pos)
            screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
            at = self.pos_manager.clamp_position(
                QPoint(global_pos.x() - FLOAT_SIZE // 2, global_pos.y() - FLOAT_SIZE // 2),
                screen_geo, FLOAT_SIZE)
            if follow is None:
                try:
                    follow = bool(self._float_store.load().get("follow", True))
                except Exception:
                    follow = True
            floater.set_loose(True, at=at, follow=follow)
            floater._persist_here("loose")
            self.island.set_mochi_loose(True)
            self.collapse_to_anchor()
            Sound.play("pop")
            logger.info("[FLOAT] Mochi detached to desktop at %s", at)
        except Exception as e:
            logger.error(f"[FLOAT] detach failed: {e}")
        finally:
            self._refresh_tray_float_action()

    def _dock_mochi(self, reason: str = "user_request"):
        """Calls Mochi home: floater hides + persists, island bot returns."""
        try:
            if self.floater is not None and self.floater.is_loose:
                try:
                    self.floater.persist("docked")
                except Exception:
                    pass
                self.floater.set_loose(False)
            self.island.set_mochi_loose(False)
            Sound.play("blip")
            logger.info("[FLOAT] Mochi docked home (reason=%s)", reason)
        except Exception as e:
            logger.error(f"[FLOAT] dock failed: {e}")
        finally:
            self._refresh_tray_float_action()

    def _restore_loose_mochi(self):
        """Next-launch restore: Mochi comes back exactly where you left him."""
        try:
            saved = self._float_store.load()
            if saved.get("mode") != "loose" or saved.get("pos") is None:
                return
            floater = self._ensure_floater()
            screen = self.pos_manager.get_active_screen(saved["pos"])
            screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
            at = self.pos_manager.clamp_position(saved["pos"], screen_geo, FLOAT_SIZE)
            floater.set_loose(True, at=at, follow=bool(saved.get("follow", True)))
            self.island.set_mochi_loose(True)
            if not self._is_anchor_mode:
                self.collapse_to_anchor()
            logger.info("[FLOAT] Restored loose Mochi at %s", at)
        except Exception as e:
            logger.debug(f"[FLOAT] restore failed: {e}")
        finally:
            self._refresh_tray_float_action()

    def _on_island_animation_changed(self, level: str):
        """Mirrors the appearance intensity onto the loose companion, if any."""
        try:
            if self.floater is not None and self.floater.is_loose:
                self.floater.character.set_animation_intensity(
                    getattr(self.island.character, "_animation_intensity", 1.0))
        except Exception:
            pass

    def _on_suggestion_proposed_event(self, data: dict):
        """A proactive suggestion needs attention → loose Mochi flies home & back."""
        try:
            if self.floater is not None and self.floater.is_loose:
                self.floater.fly_home_and_back(self._mochi_home_center())
        except Exception as e:
            logger.debug(f"[FLOAT] suggestion fly-home failed: {e}")

    def _on_island_collapsed(self):
        if self.island._current_mode == "anchor":
            if not self._is_anchor_mode or self.width() != self.anchor_size:
                self.collapse_to_anchor()

    def _on_island_expanded(self):
        if self._is_anchor_mode or self.width() != 720:
            self.expand_island(self.island._current_view)

    def eventFilter(self, watched, event):
        """Implements click-vs-drag detection for the permanent floating JARVIS anchor and dynamic island."""
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_start_window_pos = self.pos()
            self._is_dragging_anchor = False
            # Tear-off candidate: press began on the island bot itself. Anchor-mode
            # bot drags keep their existing move-anchor meaning; chat-locked and
            # greeting states never detach (chat invariant + ceremony guard).
            try:
                island = getattr(self, "island", None)
                self._detach_candidate = (
                    watched is getattr(island, "character", None)
                    and not self._is_anchor_mode
                    and getattr(island, "_current_mode", "") not in (
                        "anchor", "collapsed_anchor", "floating_anchor", "hidden")
                    and getattr(island, "_locked_view", None) != "chat"
                    and not getattr(island, "_is_greeting_active", False)
                    and not (self.floater is not None and self.floater.is_loose)
                )
            except Exception:
                self._detach_candidate = False
            return False

        elif event.type() == QEvent.MouseMove and (event.buttons() & Qt.LeftButton):
            delta = event.globalPosition().toPoint() - self._drag_start_pos
            # Tear-off wins over anchor-drag while the press began on the bot.
            if getattr(self, "_detach_candidate", False):
                if delta.manhattanLength() > self._detach_threshold:
                    self._detach_candidate = False
                    self._is_dragging_anchor = False
                    self._suppress_anchor_release = True
                    self._detach_mochi_to_desktop(event.globalPosition().toPoint())
                    return True
                return False
            if not self._is_dragging_anchor and delta.manhattanLength() > self._drag_threshold:
                self._is_dragging_anchor = True
                self.fsm.transition_to(IslandState.DRAG_ANCHOR, reason="user_drag_start")

            if self._is_dragging_anchor:
                target_pos = self._drag_start_window_pos + delta
                screen = self.pos_manager.get_active_screen(target_pos)
                screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
                clamped = self.pos_manager.clamp_position(target_pos, screen_geo, anchor_size=self.width(), min_visible=20)
                self.move(clamped)
                if self._is_anchor_mode:
                    self.anchor_pos = clamped
                return True

        elif event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            # Detach consumed this gesture: skip anchor side-effects entirely.
            if getattr(self, "_suppress_anchor_release", False):
                self._suppress_anchor_release = False
                self._detach_candidate = False
                return True
            self._detach_candidate = False
            if self._is_dragging_anchor:
                self._is_dragging_anchor = False
                screen = self.pos_manager.get_active_screen(self.pos())
                screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
                if self._is_anchor_mode:
                    self.anchor_pos = self.pos()
                    self.pos_manager.save_position(self.anchor_pos, screen_geo, self.anchor_size)
                    self.fsm.transition_to(IslandState.FLOATING_ANCHOR, reason="drag_finished")
                else:
                    self.anchor_pos = QPoint(self.pos().x() + (self.width() - self.anchor_size) // 2, self.pos().y())
                    self.pos_manager.save_position(self.anchor_pos, screen_geo, self.anchor_size)
                    self.fsm.transition_to(IslandState.EXPANDED_ISLAND, reason="drag_finished")
                return True
            else:
                # Clean pointer click without dragging (movement <= 8px)
                if self._is_anchor_mode:
                    # Empty nest: clicking the anchor calls a loose Mochi back home.
                    if self.floater is not None and self.floater.is_loose:
                        self._dock_mochi("anchor_recall")
                    else:
                        self.expand_island("overview")
                    return True

        return super().eventFilter(watched, event)

    def _collapse_to_idle(self):
        Sound.play("close")
        self.collapse_to_anchor()

    def _toggle_chat_surface(self):
        if self.island._current_mode == "expanded" and self.island._current_view == "chat":
            self.collapse_to_anchor()
        else:
            self.expand_island("chat")

    # ── Phase 1: Explicit Lifecycle Management (Settings vs Application) ──
    def openSettings(self):
        """Open Settings UI safely without altering JARVIS application lifecycle."""
        self.open_settings()

    def open_settings(self):
        """Open Settings UI safely without altering JARVIS application lifecycle."""
        logger.info("[LIFECYCLE] openSettings() requested — opening Settings tab without altering JARVIS application lifecycle.")
        if hasattr(self, "studio_window") and self.studio_window:
            self.studio_window.switch_tab(9)  # 9 is SettingsView
            self.studio_window.show()
            self.studio_window.raise_()
            self.studio_window.activateWindow()

    def closeSettings(self):
        """Close Settings UI safely without terminating JARVIS application."""
        self.close_settings()

    def close_settings(self):
        """Close Settings UI safely without terminating JARVIS application."""
        logger.info("[LIFECYCLE] closeSettings() requested — hiding Settings window; JARVIS core remains alive.")
        if hasattr(self, "studio_window") and self.studio_window:
            self.studio_window.hide()

    def exitApplication(self):
        """Authoritative explicit exit handler for the entire JARVIS application."""
        self.exit_application()

    def exit_application(self):
        """Authoritative explicit exit handler for the entire JARVIS application."""
        logger.info("[LIFECYCLE] exitApplication() explicitly invoked — initiating application termination.")
        self._terminate_application()

    def _open_settings(self):
        self.open_settings()

    def _on_live_audio_level(self, level: float, is_speech: bool):
        """Dispatches real-time audio levels to character and dynamic island."""
        if hasattr(self, "character") and self.character:
            self.character.set_audio_level(level, is_speech)
        if hasattr(self, "island") and self.island:
            self.island.set_audio_level(level, is_speech)
        try:
            if self.floater is not None and self.floater.is_loose:
                self.floater.character.set_audio_level(level, is_speech)
        except Exception:
            pass
        if is_speech and getattr(self, "_current_state", "ready") == "ready":
            self.set_system_state("listening")

    def toggle_island_mode(self):
        """Toggles between Dynamic Island mode and Expanded Studio mode."""
        Sound.play("blip")
        if self._is_island_mode:
            # Enter Studio Mode
            self._is_island_mode = False
            self.sidebar.show()
            self.status_bar.show()
            self.studio_window.show()
            self.studio_window.raise_()
            self.island_btn.setText("🏝️ Island Mode")
        else:
            # Return to Island Mode
            self._is_island_mode = True
            self.sidebar.hide()
            self.status_bar.hide()
            self.studio_window.hide()
            self.island_btn.setText("🪟 Studio Mode")
            self._position_top_center()
            self.island.set_mode("compact")

    def _on_confirmation_action(self, confirmed: bool):
        # Stay in context: report decision into chat history, never force-navigate
        # CHAT → HOME unless user explicitly chooses Home (spec §9).
        if confirmed:
            self._handle_user_message("yes, confirm")
        else:
            self._handle_user_message("cancel action")
        # Return to locked chat if chat was active; otherwise show overview briefly.
        try:
            if getattr(self.island, "_locked_view", None) == "chat" or self.controller.activeView == "chat":
                self.island.set_view("chat")
            # else: leave current finished view visible; auto-collapse timer handles it
        except Exception:
            pass

    def _on_question_option_selected(self, option: str):
        self._handle_user_message(option)
        try:
            if getattr(self.island, "_locked_view", None) == "chat" or self.controller.activeView == "chat":
                self.island.set_view("chat")
        except Exception:
            pass

    def set_system_state(self, state: str, details: str = "") -> None:
        """Centralized state machine controller for UI headers, character, and status bars."""
        state_lower = state.lower()
        prev_state = getattr(self, "_current_state", "ready")
        self._current_state = state_lower
        self._current_state_details = details
        if prev_state == "thinking" and state_lower != "thinking":
            if state_lower == "error":
                logger.info("[JARVIS_STATE] THINKING -> ERROR")
                logger.info("[MOCHI_THINKING] STOP reason=error")
            elif state_lower in ("ready", "idle"):
                logger.info("[MOCHI_THINKING] STOP reason=state_cleared")

        if hasattr(self, "island") and hasattr(self.island, "visibility_mgr"):
            self.island.visibility_mgr.notify_activity(f"state:{state_lower}")

        # 0. Semantic entry sounds: only on genuine transitions, never repeats.
        try:
            from .island.semantic_events import jarvis_visual_event
            entering = state_lower != prev_state
            if entering:
                if state_lower == "working":
                    jarvis_visual_event("task_started")
                elif state_lower == "thinking":
                    jarvis_visual_event("thinking_started")
                elif state_lower == "searching":
                    jarvis_visual_event("search_started")
                elif state_lower in ("confused", "dizzy"):
                    jarvis_visual_event("dizzy")
                elif state_lower == "listening":
                    jarvis_visual_event("ui_blip")
        except Exception:
            pass

        # 1. Update Character reaction
        if hasattr(self, "character") and self.character:
            self.character.set_system_state(state_lower)
        # Loose companion mirrors the same state (single identity, two homes).
        try:
            if self.floater is not None and self.floater.is_loose:
                self.floater.character.set_system_state(state_lower)
        except Exception:
            pass

        # 2. Update Status Pill & Badges
        mic_name = getattr(self, "_current_mic_name", "Default Mic")
        is_bt = getattr(self, "_current_mic_is_bt", False)
        mic_icon = "🎧" if is_bt else "🎙️"

        if hasattr(self, "mic_pill") and self.mic_pill:
            if hasattr(self.mic_pill, "set_mic_state"):
                mic_state = "unavailable" if not getattr(self, "mic_enabled", True) else state_lower
                self.mic_pill.set_mic_state(mic_state, is_bluetooth=is_bt, details=details)
                self.mic_pill.setToolTip(f"{mic_name} ({'Bluetooth' if is_bt else 'Built-in/USB'})")
            else:
                self.mic_pill.setText(f"{mic_icon} {mic_name}")

        state_texts = {
            "ready": "Waiting for command",
            "listening": "Listening…",
            "thinking": "Thinking…",
            "executing": f"Running: {details or 'action'}",
            "speaking": "Speaking…",
            "success": "✓ Done",
            "error": "Error",
            "paused": "Paused",
        }
        pill_text = state_texts.get(state_lower, "Waiting for command")
        if hasattr(self, "status_pill"):
            self.status_pill.set_status("READY" if state_lower == "ready" else pill_text, state=state_lower)

        if hasattr(self, "mic_status") and self.mic_status:
            self.mic_status.setText(f"● {mic_icon} {mic_name} | {pill_text}")

        # Update Island Overview Card: dynamic intelligent status line driven by actual backend state
        if hasattr(self, "island") and hasattr(self.island, "view_overview"):
            if hasattr(self.island.view_overview, "set_backend_state"):
                self.island.view_overview.set_backend_state(state_lower, details)
            elif state_lower == "ready":
                try:
                    self.island.view_overview.restore_home()
                except Exception:
                    self.island.view_overview.set_activity(
                        title="JARVIS",
                        subtitle=details if details else f"System {pill_text} • Audio {mic_name}"
                    )
            else:
                self.island.view_overview.set_activity(
                    title="JARVIS" if state_lower == "ready" else state_lower.capitalize(),
                    subtitle=details if details else f"System {pill_text} • Audio {mic_name}"
                )

        # 3. Synchronize IslandStateMachine and View Contents (preserve activeView — spec §5)
        chat_locked = (
            getattr(self.island, "_locked_view", None) == "chat"
            or getattr(self.controller, "activeView", "") == "chat"
            or (hasattr(self.island, "_current_view") and self.island._current_view in ("chat", "prompt"))
        )
        if state_lower == "listening":
            if hasattr(self, "island") and hasattr(self.island, "view_listening"):
                self.island.view_listening.set_transcript(details or "Listening...")
            if not chat_locked:
                self.fsm.transition_to(IslandState.LISTENING)
            else:
                self.character.set_system_state("listening")
        elif state_lower == "thinking":
            if hasattr(self, "island") and hasattr(self.island, "view_thinking"):
                self.island.view_thinking.set_thinking_text(details or "Analyzing intent & preparing response plan...")
            if not chat_locked:
                self.fsm.transition_to(IslandState.THINKING)
            else:
                self.character.set_system_state("thinking")
        elif state_lower == "speaking":
            if hasattr(self, "island") and hasattr(self.island, "view_speaking"):
                self.island.view_speaking.set_spoken_text(details or "")
            if not chat_locked:
                self.fsm.transition_to(IslandState.SPEAKING)
            else:
                self.character.set_system_state("speaking")
        elif state_lower in ("executing", "working"):
            if not chat_locked:
                self.fsm.transition_to(IslandState.WORKING)
            else:
                self.character.set_system_state("working")
        elif state_lower == "success":
            if not chat_locked:
                self.fsm.transition_to(IslandState.SUCCESS)
            else:
                self.character.set_system_state("success")
        elif state_lower == "ready":
            if chat_locked:
                # CHAT invariant: never navigate away; just settle character to idle.
                try:
                    self.character.set_system_state("idle")
                except Exception:
                    pass
                if hasattr(self, "controller") and self.controller:
                    self.controller.touch_activity()
            elif self.fsm.current_state in (
                IslandState.EXECUTING, IslandState.THINKING, IslandState.SUCCESS,
                IslandState.SPEAKING, IslandState.LISTENING, IslandState.WORKING
            ):
                self.fsm.transition_to(IslandState.COMPACT)
                if hasattr(self, "controller") and self.controller:
                    self.controller.touch_activity()
        elif state_lower == "error":
            if not chat_locked:
                self.fsm.transition_to(IslandState.ERROR)
            else:
                self.character.set_system_state("error")
        elif state_lower in ("approval", "waiting_user", "question", "chat", "settings"):
            # Route without destroying chat lock; island handles view mapping
            try:
                mapping = {"approval": IslandState.WAITING_USER, "waiting_user": IslandState.WAITING_USER,
                           "question": IslandState.CHAT, "chat": IslandState.CHAT,
                           "settings": IslandState.SETTINGS}
                target = mapping.get(state_lower, IslandState.CHAT)
                if not chat_locked or state_lower in ("chat", "settings"):
                    self.fsm.transition_to(target)
            except Exception:
                pass

    def _on_active_mic_updated(self, dev):
        if dev:
            self._current_mic_name = dev.name
            self._current_mic_is_bt = getattr(dev, "is_bluetooth", False)
        else:
            self._current_mic_name = "Default Mic"
            self._current_mic_is_bt = False
        self._refresh_mic_status_label()

    def _refresh_mic_status_label(self):
        self.set_system_state(getattr(self, "_current_state", "ready"), getattr(self, "_current_state_details", ""))

    def _toggle_voice_listening(self):
        if hasattr(self, "view_chat") and self.view_chat:
            self.view_chat._toggle_voice_listening()

    def _on_island_mic_toggled(self, enabled: bool):
        logger.info(f"[DYNAMIC ISLAND] Microphone toggled by user: {'ON' if enabled else 'OFF'}")
        self.controller.set_mic_enabled(enabled)
        if enabled:
            if hasattr(self, "view_chat") and self.view_chat:
                self.view_chat.start_voice_listening(play_chime=True)
            if hasattr(self, "mic_pill") and hasattr(self.mic_pill, "set_mic_state"):
                is_bt = getattr(self, "_current_mic_is_bt", False)
                self.mic_pill.set_mic_state("ready", is_bluetooth=is_bt)
        else:
            if hasattr(self, "view_chat") and self.view_chat:
                self.view_chat.stop_voice_listening()
            if hasattr(self, "mic_pill") and hasattr(self.mic_pill, "set_mic_state"):
                self.mic_pill.set_mic_state("unavailable")
        try:
            self.island.sync_mic_ui(bool(enabled), listening=bool(enabled))
        except Exception:
            pass

    def _on_voice_listening_changed(self, is_listening: bool):
        self.controller.set_mic_enabled(is_listening)
        if hasattr(self, "island") and hasattr(self.island, "header"):
            self.island.header.set_mic_enabled(is_listening)
        if hasattr(self, "mic_pill") and hasattr(self.mic_pill, "set_mic_state"):
            if is_listening:
                self.mic_pill.set_mic_state("listening")
            else:
                is_bt = getattr(self, "_current_mic_is_bt", False)
                self.mic_pill.set_mic_state("ready", is_bluetooth=is_bt)
        try:
            self.island.sync_mic_ui(bool(is_listening), listening=bool(is_listening))
        except Exception:
            pass

    def _on_island_speaker_toggled(self, enabled: bool):
        logger.info(f"[DYNAMIC ISLAND] Speaker TTS toggled by user: {'ON' if enabled else 'MUTED'}")
        self.controller.set_speaker_enabled(enabled)
        is_muted = not enabled
        if hasattr(self, "view_chat") and self.view_chat:
            self.view_chat.is_muted = is_muted
            self.view_chat.mute_toggled.emit(is_muted)
        if is_muted and self.tts_manager and self.tts_manager.is_speaking():
            self.tts_manager.stop()
        try:
            self.island.sync_speaker_ui(bool(enabled))
        except Exception:
            pass
        try:
            Sound.set_enabled(bool(enabled))
            self._persist_sound_settings()
        except Exception:
            pass

    def _on_voice_mute_changed(self, is_muted: bool):
        speaker_enabled = not is_muted
        self.controller.set_speaker_enabled(speaker_enabled)
        if hasattr(self, "island") and hasattr(self.island, "header"):
            self.island.header.set_speaker_enabled(speaker_enabled)
        try:
            self.island.sync_speaker_ui(bool(speaker_enabled))
        except Exception:
            pass

    def _on_island_volume_changed(self, value: int):
        """Settings volume 0–100 → engine + persisted config (existing mechanism)."""
        try:
            Sound.set_volume(float(value) / 100.0)
            self._persist_sound_settings()
        except Exception:
            pass

    def _on_island_settings_saved(self, data: dict):
        """Synchronizes saved island settings across app-level controller and TTS."""
        try:
            # Sync speech speed to TTS manager
            speed = int(data.get("speech_speed", 100))
            if hasattr(self, "tts_manager") and self.tts_manager:
                target = getattr(self.tts_manager, "tts", self.tts_manager)
                if hasattr(target, "set_prosody"):
                    diff = speed - 100
                    target.set_prosody(rate=speed)
                    if hasattr(target, "prosody"):
                        target.prosody.rate_edge = f"{diff:+d}%"
            # Sync controller mic & speaker state
            if hasattr(self, "controller") and self.controller:
                self.controller.set_mic_enabled(bool(data.get("mic_enabled", True)))
                self.controller.set_speaker_enabled(bool(data.get("sound_enabled", True)))
            # Sync companion animation
            anim = data.get("animation", "normal")
            self._on_island_animation_changed(anim)
        except Exception as e:
            logger.debug(f"[APP] _on_island_settings_saved failed: {e}")

    def _on_island_close_requested(self):
        logger.info("[DYNAMIC ISLAND] Close (×): compact pill; idle auto-hide takes it to the top-edge line. Backend & listeners remain alive.")
        # Island already collapsed to compact by hide_to_edge; sync window + FSM.
        self._is_anchor_mode = False
        try:
            self.fsm.transition_to(IslandState.COMPACT, reason="close_button")
        except Exception:
            pass
        try:
            self.controller.set_island_expanded(False)
        except Exception:
            pass

    def toggle_mic(self):
        """Toggle microphone capture, VAD, and wake-word detection."""
        if hasattr(self, "island") and hasattr(self.island, "toggle_mic"):
            self.island.toggle_mic()
        else:
            self._on_island_mic_toggled(not self.controller.micEnabled)

    def toggle_speaker(self):
        """Toggle JARVIS TTS speech output mute."""
        if hasattr(self, "island") and hasattr(self.island, "header"):
            self.island.header._toggle_speaker()
        else:
            self._on_island_speaker_toggled(not self.controller.speakerEnabled)

    def toggle_island_visibility(self):
        """Toggle Dynamic Island visibility between compact and hidden."""
        if hasattr(self, "island") and hasattr(self.island, "toggle_island_visibility"):
            self.island.toggle_island_visibility()
        else:
            self.controller.toggle_island_visible()

    def activate_jarvis(self):
        """Activate JARVIS into Chat view with focused input."""
        if hasattr(self, "island") and hasattr(self.island, "activate_jarvis"):
            self.island.activate_jarvis()
        else:
            self.island.expand_to_view("chat")

    def _handle_user_message(self, text: str):
        if hasattr(self, "island") and hasattr(self.island, "visibility_mgr"):
            self.island.visibility_mgr.notify_activity("user_message")
        try:
            from .island.semantic_events import jarvis_visual_event
            jarvis_visual_event("message_sent")
        except Exception:
            Sound.play("send")
        if is_affection_or_praise(text):
            if hasattr(self, "island") and hasattr(self.island, "trigger_love_emote"):
                self.island.trigger_love_emote()
            elif hasattr(self, "character") and hasattr(self.character, "trigger_love_emote"):
                self.character.trigger_love_emote()
        self._start_message_worker(text, source="gui")

    def _handle_voice_message(self, text: str):
        if hasattr(self, "island") and hasattr(self.island, "visibility_mgr"):
            self.island.visibility_mgr.notify_activity("voice_message")
        try:
            from .island.semantic_events import jarvis_visual_event
            jarvis_visual_event("message_sent")
        except Exception:
            Sound.play("send")
        if is_affection_or_praise(text):
            if hasattr(self, "island") and hasattr(self.island, "trigger_love_emote"):
                self.island.trigger_love_emote()
            elif hasattr(self, "character") and hasattr(self.character, "trigger_love_emote"):
                self.character.trigger_love_emote()
        self._start_message_worker(text, source="voice_gated")

    def _start_message_worker(self, text: str, source: str):
        # Fresh user turn: new context begins — activity clock + home back to time.
        # (STT partials never reach here — voice passes the interaction gate first.)
        try:
            self._home_store.mark_active()
            if hasattr(self, "island") and hasattr(self.island, "view_overview"):
                self.island.view_overview.show_home(HomeKind.TIME)
        except Exception:
            pass
        # Command accepted: exactly one blip per finalized utterance.
        try:
            Sound.play("blip", reason="command_accepted")
        except Exception:
            pass
        is_speaking = False
        if self.tts_manager and self.tts_manager.is_speaking():
            is_speaking = True
        elif self.core and hasattr(self.core, "interaction_gate") and self.core.interaction_gate._is_tts_speaking:
            is_speaking = True

        if is_speaking:
            if self.tts_manager:
                self.tts_manager.stop(new_generation=True)
            if self.core and hasattr(self.core, "interrupt_active_speech"):
                self.core.interrupt_active_speech(reason="user_barge_in", interrupting_text=text)

        self._active_generation_id += 1
        current_gen = self._active_generation_id

        if self._active_worker:
            self._active_worker.cancel()
            try:
                self._active_worker.finished.disconnect()
            except Exception:
                pass
            if getattr(self, "_current_state", "") == "thinking":
                logger.info("[JARVIS_STATE] THINKING -> IDLE")
                logger.info("[MOCHI_THINKING] STOP reason=cancel")

        logger.info("[JARVIS_STATE] IDLE -> THINKING")
        logger.info("[MOCHI_THINKING] START")
        self.set_system_state("thinking")

        try:
            prepare_tts = self.tts if not self.view_chat.is_muted else None
            self._active_worker = TaskWorker(
                self.core, text, tts_engine=prepare_tts, source=source, generation_id=current_gen, parent=self
            )
            self._active_thread = self._active_worker
            self._active_worker.finished.connect(self._on_worker_finished)
            self._active_worker.finished.connect(self._cleanup_active_thread)
            self._active_worker.start()
        except Exception as e:
            logger.error(f"Task worker launch error: {e}")
            logger.info("[JARVIS_STATE] THINKING -> ERROR")
            logger.info("[MOCHI_THINKING] STOP reason=error")
            try:
                from .island.semantic_events import jarvis_visual_event
                jarvis_visual_event("task_failed")
            except Exception:
                pass
            self.set_system_state("error", details=str(e))

    def cancel_current_task(self):
        """Explicitly cancels active message worker, halts thinking animation, and restores IDLE."""
        if self._active_worker:
            self._active_worker.cancel()
            try:
                self._active_worker.finished.disconnect()
            except Exception:
                pass
            self._cleanup_active_thread()
        if getattr(self, "_current_state", "") == "thinking":
            logger.info("[JARVIS_STATE] THINKING -> IDLE")
            logger.info("[MOCHI_THINKING] STOP reason=cancel")
            self.set_system_state("ready")

    def _on_worker_finished(self, sender: str, response: str, sensitive_payload=None, generation_id: int = 0):
        if generation_id != self._active_generation_id:
            return

        # 1. Final response arrived -> immediately stop thinking phase and clear thinking dots
        logger.info("[JARVIS_STATE] THINKING -> RESPONSE_RECEIVED")
        logger.info("[MOCHI_THINKING] STOP reason=response_received")

        # 2 & 3. Clear THINKING state and stop thinking animation before displaying text
        self.set_system_state("ready")

        # 4. Add/display assistant response to Island chat and standard view chat
        if hasattr(self, "island_chat") and hasattr(self.island_chat, "add_message"):
            self.island_chat.add_message(sender.lower(), response)
        if hasattr(self, "view_chat") and hasattr(self.view_chat, "add_message"):
            self.view_chat.add_message(sender, response)

        # Response completed chime: owned by the semantic manager (task_success).
        try:
            from .island.semantic_events import jarvis_visual_event
            jarvis_visual_event("task_success")
        except Exception:
            pass

        dialog = getattr(self.core, "dialog_manager", None)
        gate = getattr(self.core, "interaction_gate", None)
        if dialog and gate and dialog.awaits_user_followup():
            gate.authorize_followup()

        # Check for shutdown
        if "shutting down jarvis" in response.lower():
            if not self.view_chat.is_muted and self.tts_manager:
                try:
                    self.tts_manager.speak(response, priority=True)
                except Exception:
                    pass
            QTimer.singleShot(400, self._terminate_application)
            return

        # 5 & 6. Transition to SPEAKING state if TTS is speaking, otherwise stay IDLE
        if not self.view_chat.is_muted and self.tts_manager and response:
            logger.info("[JARVIS_STATE] RESPONSE_RECEIVED -> SPEAKING")
            self._speak_response(response)
        else:
            logger.info("[JARVIS_STATE] RESPONSE_RECEIVED -> IDLE")
            self.set_system_state("ready")

    def _cleanup_active_thread(self, *args):
        self._active_thread = None
        self._active_worker = None
        if self._message_queue:
            text, source = self._message_queue.popleft()
            QTimer.singleShot(0, lambda: self._start_message_worker(text, source))

    def _on_tts_speaking_state_changed(self, is_speaking: bool):
        # Voice truth first: both companions follow real TTS sound, not flags.
        try:
            if hasattr(self, "character") and self.character:
                self.character.set_tts_active(is_speaking)
            if getattr(self, "floater", None) is not None and self.floater.is_loose:
                self.floater.character.set_tts_active(is_speaking)
        except Exception:
            pass
        try:
            if self.core and hasattr(self.core, "interaction_gate"):
                active_chunk = ""
                if self.tts_manager and hasattr(self.tts_manager, "get_current_spoken_chunk"):
                    try:
                        active_chunk = self.tts_manager.get_current_spoken_chunk()
                    except Exception:
                        pass
                self.core.interaction_gate.set_tts_speaking(is_speaking, text=active_chunk)
        except Exception as e:
            logger.debug(f"Interaction-gate TTS flag failed (non-fatal): {e}")
        try:
            QTimer.singleShot(0, lambda: self.view_chat.set_speaking_state(is_speaking))
            if is_speaking:
                QTimer.singleShot(0, lambda: self.set_system_state("speaking"))
            else:
                logger.info("[JARVIS_STATE] SPEAKING -> IDLE")
                QTimer.singleShot(0, lambda: self.set_system_state("ready"))
        except Exception:
            pass

    def _switch_tab(self, index: int):
        self.studio_window.switch_tab(index)

    def _init_telemetry_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_telemetry)
        self.timer.start(1500)
        self._update_telemetry()

    def _update_telemetry(self):
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        used_gb = round(mem.used / (1024 ** 3), 1)
        total_gb = round(mem.total / (1024 ** 3), 1)

        llm_label = "Local"
        if self.core and hasattr(self.core, "brain") and self.core.brain:
            provider = getattr(self.core.brain, "llm", None)
            if provider:
                pname = type(provider).__name__
                if "Ollama" in pname:
                    llm_label = "Ollama"
                elif "OpenAI" in pname:
                    llm_label = "API"

        tts_label = "Speaking" if (self.tts_manager and self.tts_manager.is_speaking()) else "Ready"
        battery = psutil.sensors_battery()
        battery_label = "N/A" if battery is None else f"{round(battery.percent)}%"

        self.telemetry_lbl.setText(
            f"CPU {cpu}% | RAM {used_gb}/{total_gb}GB | Battery {battery_label} | "
            f"STT: Ready | LLM: {llm_label} | TTS: {tts_label}"
        )

        if hasattr(self, "model_pill") and self.model_pill:
            self.model_pill.setText(f"🤖 {llm_label}")

    def _auto_start_voice_if_configured(self) -> None:
        if not self.core:
            return
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen" or os.environ.get("PYTEST_CURRENT_TEST"):
            return
        voice_cfg = self.core.config.get("voice", {}) if self.core else {}
        if voice_cfg.get("enabled", True):
            QTimer.singleShot(750, lambda: self.view_chat.start_voice_listening(play_chime=False) if hasattr(self, "view_chat") else None)

    def _open_news_url(self, url: str) -> None:
        try:
            if url:
                from PySide6.QtGui import QDesktopServices
                from PySide6.QtCore import QUrl
                QDesktopServices.openUrl(QUrl(url))
        except Exception:
            pass

    def _on_open_news_requested(self) -> None:
        self._switch_tab(10)

    def _on_play_briefing_requested(self, text: str) -> None:
        if text:
            self._speak_response(text)

    def open_stock_suggestions(self, tab: str = "All") -> None:
        self._switch_tab(11)
        if hasattr(self, "view_stock_suggestions"):
            if tab.lower() == "intraday":
                self.view_stock_suggestions._set_tab("Intraday")
            elif tab.lower() == "swing":
                self.view_stock_suggestions._set_tab("Swing")
            else:
                self.view_stock_suggestions._set_tab("All")

    def _on_remember_requested(self, text: str):
        if self.core and hasattr(self.core, "memory_manager") and self.core.memory_manager:
            try:
                self.core.memory_manager.save_semantic_fact(
                    key="user_noted_memory",
                    value=text,
                    category="user_preference"
                )
            except Exception as e:
                logger.error(f"Error saving remembered memory: {e}")

    def _speak_response(self, text: str):
        if not self.view_chat.is_muted and self.tts_manager and text:
            self.set_system_state("speaking", details=text)
            self.tts_manager.speak(text)

    def _on_update_status_event(self, data: dict):
        msg = data.get("message", "")
        if msg:
            self.update_status_label.setText(msg)
            self.update_status_label.setVisible(True)
            QTimer.singleShot(4000, lambda: self.update_status_label.setVisible(False))

    def _on_reminder_triggered_event(self, data: dict):
        Sound.play("peek")
        title = data.get("title", "Reminder")
        is_missed = data.get("is_missed", False)
        prefix = "⏰ Missed Reminder" if is_missed else "⏰ Reminder"
        display_text = f"{prefix}: {title}"

        # A loose Mochi reacts to the alert: flies home, then flies back.
        try:
            if self.floater is not None and self.floater.is_loose:
                self.floater.fly_home_and_back(self._mochi_home_center())
        except Exception as e:
            logger.debug(f"[FLOAT] reminder fly-home failed: {e}")

        if hasattr(self, "island_chat") and hasattr(self.island_chat, "add_message"):
            self.island_chat.add_message("assistant", display_text)
        if hasattr(self, "view_chat") and hasattr(self.view_chat, "add_message"):
            self.view_chat.add_message("Jarvis", display_text)

        self._speak_response(f"Boss, aapka reminder: {title}")

    def _on_navigation_event(self, data: dict):
        tab = str(data.get("tab", "")).lower()
        if "stock" in tab:
            self.open_stock_suggestions(tab=str(data.get("filter", "All")))

    # ── Verified semantic sounds (EventBus → GUI thread) ────────────────────
    def _on_execution_completed_event(self, data: dict):
        """Verified task outcome: exactly one finish/error chime per execution."""
        try:
            success = bool(data.get("success", False))
            event_id = str(data.get("timestamp", "")) or (str(data.get("executed_action", "")) + str(data.get("target", "")))
            if success:
                Sound.play("finish", reason="task_success", event_id=event_id, cooldown_ms=1200)
                # Verified real task done → lock "All done" on Home until next turn.
                try:
                    if hasattr(self, "island") and hasattr(self.island, "view_overview"):
                        detail = str(data.get("target", "") or data.get("executed_action", "")).strip()
                        self.island.view_overview.show_home(HomeKind.TASK_DONE, detail)
                except Exception:
                    pass
                self.set_system_state("success")
            else:
                Sound.play("error", reason="task_failed", event_id=event_id, cooldown_ms=1200)
                self.set_system_state("error")
        except Exception as e:
            logger.debug(f"Execution sound hook failed: {e}")

    def _on_policy_evaluated_event(self, data: dict):
        """A real execution plan was approved: the task genuinely begins → work."""
        try:
            if not bool(data.get("allowed", False)):
                return
            plan_id = str(data.get("plan_id", "")) or "plan"
            Sound.play("work", reason="task_started", event_id=plan_id)
            self.set_system_state("working")
        except Exception as e:
            logger.debug(f"Policy sound hook failed: {e}")

    def _on_agent_approval_required_event(self, data: dict):
        """Permission genuinely required: populate card + expand + pin.

        The chime itself is owned by the semantic manager (approval_required
        fires from set_view("approval") below) — exactly one approval sound.
        """
        try:
            step = str(data.get("step", ""))
            question = str(data.get("question", "JARVIS needs permission"))
            if hasattr(self, "island") and hasattr(self.island, "view_approval"):
                self.island.view_approval.set_approval_data(step or question, reason=question)
                self.expand_island("approval")
            self.set_system_state("waiting_user")
            try:
                if hasattr(self, "controller") and self.controller:
                    self.controller.touch_activity()
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Approval sound hook failed: {e}")

    # ── Sound settings: apply + persist via the existing config mechanism ───
    def _apply_sound_settings(self) -> None:
        """Reads core.config['sound'] into the singleton (same pattern as voice)."""
        try:
            cfg = (self.core.config.get("sound", {}) if self.core and hasattr(self.core, "config") else {}) or {}
            Sound.set_enabled(bool(cfg.get("enabled", True)))
            Sound.set_volume(float(cfg.get("volume", 12)) / 100.0)
            try:
                if hasattr(self, "island") and hasattr(self.island, "view_settings"):
                    self.island.view_settings.set_speaker_state(Sound.enabled)
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Sound settings apply failed: {e}")

    def _persist_sound_settings(self) -> None:
        """Writes core.config['sound'] back to config.yaml (settings_view pattern)."""
        try:
            if not (self.core and hasattr(self.core, "config") and hasattr(self.core, "config_path")):
                return
            sound_cfg = self.core.config.setdefault("sound", {})
            sound_cfg["enabled"] = bool(Sound.enabled)
            sound_cfg["volume"] = int(round(Sound.volume * 100))
            import yaml
            with open(self.core.config_path, "w", encoding="utf-8") as config_file:
                yaml.safe_dump(self.core.config, config_file, sort_keys=False, allow_unicode=True)
        except Exception as e:
            logger.debug(f"Sound settings persist failed: {e}")

    def closeEvent(self, event):
        logger.info("[LIFECYCLE] JarvisMainWindow.closeEvent received. Initiating clean shutdown of GUI and background listeners.")
        try:
            try:
                self._home_store.mark_active()  # session end = last-active stamp
            except Exception:
                pass
            if hasattr(self, "tray_icon") and self.tray_icon:
                self.tray_icon.hide()
            if getattr(self, "floater", None) is not None:
                try:
                    self.floater.persist("loose" if self.floater.is_loose else "docked")
                except Exception:
                    pass
                self.floater.stop()
                self.floater.close()
            if hasattr(self, "character") and self.character:
                self.character.stop()
            if hasattr(self, "controller") and self.controller:
                self.controller.stop()
            if hasattr(self, "timer") and self.timer:
                self.timer.stop()
            if hasattr(self, "studio_window") and self.studio_window:
                self.studio_window.close()
            if hasattr(self, "view_chat") and self.view_chat:
                logger.info("[LIFECYCLE] Stopping microphone voice listening.")
                self.view_chat.stop_voice_listening()
            if self.tts_manager:
                try:
                    logger.info("[LIFECYCLE] Shutting down TTS manager.")
                    self.tts_manager.shutdown()
                except Exception:
                    pass
            if hasattr(self, "_adm") and self._adm:
                try:
                    logger.info("[LIFECYCLE] Stopping audio device manager watcher.")
                    if hasattr(self, "_adm_listener"):
                        self._adm.unregister_device_change_listener(self._adm_listener)
                    self._adm.stop_hotplug_watcher()
                except Exception:
                    pass
            if self._active_worker and self._active_worker.isRunning():
                self._active_worker.cancel()
                self._active_worker.wait(400)
        except Exception as e:
            logger.error("[LIFECYCLE] Error during JarvisMainWindow closeEvent: %s", e)
        event.accept()

    def _terminate_application(self):
        logger.info("[LIFECYCLE] _terminate_application invoked. Terminating JARVIS backend, audio threads, and GUI.")
        try:
            if getattr(self, "floater", None) is not None:
                try:
                    self.floater.persist("loose" if self.floater.is_loose else "docked")
                except Exception:
                    pass
                self.floater.stop()
                self.floater.close()
            if hasattr(self, "character") and self.character:
                self.character.stop()
            if hasattr(self, "controller") and self.controller:
                self.controller.stop()
            if hasattr(self, "timer") and self.timer:
                self.timer.stop()
            if hasattr(self, "studio_window") and self.studio_window:
                self.studio_window.close()
            if hasattr(self, "view_chat") and self.view_chat:
                logger.info("[LIFECYCLE] Stopping microphone voice listening on terminate.")
                self.view_chat.stop_voice_listening()
            if self.tts_manager:
                try:
                    logger.info("[LIFECYCLE] Shutting down TTS manager on terminate.")
                    self.tts_manager.shutdown()
                except Exception:
                    pass
            if hasattr(self, "_adm") and self._adm:
                try:
                    logger.info("[LIFECYCLE] Stopping audio device manager watcher on terminate.")
                    if hasattr(self, "_adm_listener"):
                        self._adm.unregister_device_change_listener(self._adm_listener)
                    self._adm.stop_hotplug_watcher()
                except Exception:
                    pass
            if self._active_worker and self._active_worker.isRunning():
                self._active_worker.cancel()
                self._active_worker.wait(300)
        except Exception as e:
            logger.error("[LIFECYCLE] Error during _terminate_application: %s", e)
        logger.info("[LIFECYCLE] Calling QApplication.quit()")
        QApplication.quit()
        import os
        logger.info("[LIFECYCLE] Exiting process via os._exit(0)")
        os._exit(0)
