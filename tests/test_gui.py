# tests/test_gui.py
"""Unit tests for PySide6 GUI Components (Headless Offscreen Mode)."""

import datetime
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

# Ensure QApplication singleton exists before any widgets are constructed
_app = QApplication.instance() or QApplication(["-platform", "offscreen"])

import pytest
from main import create_jarvis
from gui.app import JarvisMainWindow
from gui.views.dashboard_view import DashboardView
from gui.views.chat_view import ChatView
from gui.views.plugins_view import PluginsView
from gui.views.memory_view import MemoryView
from gui.views.learning_view import LearningView
from gui.views.workflows_view import WorkflowsView
from gui.views.settings_view import SettingsView
from gui.views.reminders_view import RemindersView
from gui.views.activity_log_view import ActivityLogView


@pytest.fixture(scope="session")
def qapp():
    return _app


@pytest.fixture
def jarvis_gui_core(tmp_path):
    db_file = os.path.join(tmp_path, "gui_test.db").replace("\\", "/")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(f"""
system:
  name: "JARVIS_GUI_TEST"
memory:
  db_path: "{db_file}"
brain:
  llm_provider: "mock"
reminder:
  db_path: "{str(tmp_path / 'gui_reminders.db').replace(chr(92), '/')}"
plugins:
  plugin_dir: "plugins"
  auto_load: true
""")
    return create_jarvis(str(cfg_file))


def test_main_window_instantiation(qapp, jarvis_gui_core):
    """Verifies that the main PySide6 window instantiates and initializes all tabs."""
    window = JarvisMainWindow(jarvis_gui_core)
    assert "JARVIS" in window.windowTitle()
    assert window.stack.count() == len(window.nav_buttons)
    assert window.status_badge.text() in ("● READY", "● ONLINE")
    assert hasattr(window, "view_websites")
    window.close()


def test_dashboard_view_metrics(qapp, jarvis_gui_core):
    """Verifies that DashboardView loads telemetry cards."""
    view = DashboardView(jarvis_gui_core)
    view.refresh_metrics()
    assert "%" in view.card_cpu.value_lbl.text()
    assert "GB" in view.card_ram.value_lbl.text()
    assert view.card_battery.value_lbl.text() != "--"
    total_plugins = len(jarvis_gui_core.plugin_manager.get_catalog())
    assert view.card_plugin.value_lbl.text() == f"{total_plugins} / {total_plugins} Enabled"


def test_dashboard_view_with_active_proactive_coordinator(qapp, jarvis_gui_core):
    """Verifies that DashboardView handles active proactive coordinator without AttributeError."""
    if hasattr(jarvis_gui_core, "proactive_coordinator") and jarvis_gui_core.proactive_coordinator:
        from core.intelligence.models import PatternType
        jarvis_gui_core.proactive_coordinator.is_running = True
        jarvis_gui_core.proactive_coordinator.pattern_engine._record_pattern_evidence(
            pattern_key="time_app:morning:excel",
            pattern_type=PatternType.TIME_APP_HABIT,
        )
        view = DashboardView(jarvis_gui_core)
        view.refresh_metrics()
        assert "habits tracked" in view.card_proactive.sub_lbl.text()
        assert "ACTIVE" in view.card_proactive.value_lbl.text()


def test_left_sidebar_navigation_matches_all_views(qapp, jarvis_gui_core):
    """Every sidebar item must select its matching content page."""
    window = JarvisMainWindow(jarvis_gui_core)
    assert len(window.nav_buttons) == window.stack.count()
    assert len(window.nav_buttons) >= 10
    for index, button in enumerate(window.nav_buttons):
        button.click()
        assert window.stack.currentIndex() == index
        assert button.isChecked()
    window.close()


def test_gui_reminder_created_from_lazy_plugin_is_immediately_visible(qapp, jarvis_gui_core):
    """Regression: GUI loads the reminder plugin and populates the table."""
    view = RemindersView(jarvis_gui_core)
    target = (datetime.datetime.now().astimezone() + datetime.timedelta(hours=1)).isoformat()
    plugin = view._get_reminder_plugin()
    if plugin:
        plugin.execute("create_reminder", {
            "title": "GUI visibility test",
            "remind_time": target,
        })
    view.load_reminders()
    assert view.table.rowCount() >= 1


def test_gui_reminder_edit_functionality(qapp, jarvis_gui_core):
    """Verifies that reminders can be edited via update_reminder and EditReminderDialog."""
    from gui.views.reminders_view import EditReminderDialog
    from PySide6.QtWidgets import QPushButton

    view = RemindersView(jarvis_gui_core)
    target = (datetime.datetime.now().astimezone() + datetime.timedelta(hours=2)).isoformat()
    res = view.create_reminder({
        "title": "Original Meeting",
        "remind_time": target,
        "recurrence": "none"
    })
    assert res is not None and res.success
    reminder_id = res.data["id"]

    # Verify Edit button is present in the actions column (column 5)
    row_count = view.table.rowCount()
    assert row_count >= 1
    target_row = None
    for r in range(row_count):
        id_item = view.table.item(r, 0)
        if id_item and id_item.text() == f"#{reminder_id}":
            target_row = r
            break
    assert target_row is not None

    act_widget = view.table.cellWidget(target_row, 5)
    assert act_widget is not None
    edit_buttons = [b for b in act_widget.findChildren(QPushButton) if b.text() == "Edit"]
    assert len(edit_buttons) == 1

    # Verify EditReminderDialog initialization and get_data
    sample_data = {
        "id": reminder_id,
        "title": "Original Meeting",
        "remind_time": target,
        "recurrence": "none"
    }
    dlg = EditReminderDialog(sample_data, parent=view)
    assert dlg.title_input.text() == "Original Meeting"
    assert dlg.recur_combo.currentText() == "None (One-time)"

    dlg.title_input.setText("Updated Team Sync")
    dlg.recur_combo.setCurrentText("Daily")
    edit_data = dlg.get_data()
    assert edit_data["reminder_id"] == reminder_id
    assert edit_data["new_title"] == "Updated Team Sync"
    assert edit_data["new_recurrence"] == "daily"
    dlg.close()

    # Execute update_reminder
    new_target = (datetime.datetime.now().astimezone() + datetime.timedelta(hours=4)).isoformat()
    update_res = view.update_reminder({
        "reminder_id": reminder_id,
        "new_title": "Updated Team Sync",
        "new_time": new_target,
        "new_recurrence": "daily"
    })
    assert update_res is not None and update_res.success

    # Verify table reflects the update
    updated_row = None
    for r in range(view.table.rowCount()):
        id_item = view.table.item(r, 0)
        if id_item and id_item.text() == f"#{reminder_id}":
            updated_row = r
            break
    assert updated_row is not None
    assert view.table.item(updated_row, 1).text() == "Updated Team Sync"
    assert view.table.item(updated_row, 3).text() == "Daily"
    view.close()


def test_chat_view_send_message(qapp, jarvis_gui_core):
    """Verifies chat message rendering and add_message functionality."""
    view = ChatView(jarvis_gui_core)
    view.add_message("Jarvis", "Hello Boss")
    view.add_message("You", "Open Excel")
    assert view.chat_display is not None


def test_plugins_view_catalog(qapp, jarvis_gui_core):
    """Verifies PluginsView populates cards for all registered plugins."""
    view = PluginsView(jarvis_gui_core)
    assert view.table.rowCount() >= 1


def test_memory_view_refresh(qapp, jarvis_gui_core):
    """Verifies MemoryView loads memories and conversations from SQLite."""
    jarvis_gui_core.memory_manager.db.execute_update(
        "INSERT INTO memories (user_id, key, value, created_at, updated_at) VALUES ('default_user', 'owner_name', 'Boss', 100, 100)"
    )
    view = MemoryView(jarvis_gui_core)
    view.refresh_memories()
    assert view.table.rowCount() >= 1


def test_learning_view_approval_and_habits(qapp, jarvis_gui_core):
    """Verifies LearningView renders habits and staged approval items."""
    staged = jarvis_gui_core.learning_manager.approval.stage_learning(
        layer=2,
        pattern_type="vocabulary",
        original_key="calc",
        proposed_val="calculator",
        confidence=0.9
    )
    view = LearningView(jarvis_gui_core)
    view.refresh_learning_data()
    assert view.approvals_frame is not None
    assert view.cards_container.count() >= 1


def test_workflows_view_creation(qapp, jarvis_gui_core):
    """Verifies WorkflowsView loads workflow triggers and sequences."""
    view = WorkflowsView(jarvis_gui_core)
    view.refresh_workflows()
    assert view.cards_layout is not None


def test_settings_view_save_and_reset(qapp, jarvis_gui_core):
    """Verifies SettingsView loads configuration, allows edits, and saves to state."""
    view = SettingsView(jarvis_gui_core)
    assert view.input_user.text() == "Boss"
    view.input_user.setText("Sir")
    view._save_settings()
    assert jarvis_gui_core.learning_manager.preferences.get("user_title") == "Sir"


def test_settings_view_biometric_face_registration(qapp, jarvis_gui_core):
    """Verifies that SettingsView includes the Biometric Face Authentication section."""
    view = SettingsView(jarvis_gui_core)
    assert hasattr(view, "lbl_profile_status")
    assert hasattr(view, "btn_register_face")
    assert "Register" in view.btn_register_face.text()


def test_all_views_refresh_without_exceptions(qapp, jarvis_gui_core):
    """Ensures state transitions execute without raising unhandled exceptions."""
    window = JarvisMainWindow(jarvis_gui_core)
    window.set_system_state("ready")
    window.set_system_state("listening")
    window.set_system_state("thinking")
    window.set_system_state("ready")
    window.close()


def test_chat_view_command_history_up_down_arrows(qapp, jarvis_gui_core):
    """Verifies that pressing Up Arrow in input field recalls previous commands, and Down Arrow navigates forward."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    view = ChatView(jarvis_gui_core)
    # 1. Type and submit first command
    view.input_field.setText("chrome kholo")
    view._send_message()
    assert view.input_field.text() == ""
    assert "chrome kholo" in view.input_field.history

    # 2. Type and submit second command
    view.input_field.setText("volume 50 karo")
    view._send_message()
    assert "volume 50 karo" in view.input_field.history

    # 3. User is currently typing a new draft
    view.input_field.setText("new draft")

    # 4. Press Up Arrow: should recall the most recent command ('volume 50 karo')
    up_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Up, Qt.NoModifier)
    view.input_field.keyPressEvent(up_event)
    assert view.input_field.text() == "volume 50 karo"
    assert view.input_field.cursorPosition() == len("volume 50 karo")

    # 5. Press Up Arrow again: should recall older command ('chrome kholo')
    view.input_field.keyPressEvent(up_event)
    assert view.input_field.text() == "chrome kholo"
    assert view.input_field.cursorPosition() == len("chrome kholo")

    # 6. Press Up Arrow again: clamped at oldest
    view.input_field.keyPressEvent(up_event)
    assert view.input_field.text() == "chrome kholo"

    # 7. Press Down Arrow: should navigate forward to 'volume 50 karo'
    down_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Down, Qt.NoModifier)
    view.input_field.keyPressEvent(down_event)
    assert view.input_field.text() == "volume 50 karo"

    # 8. Press Down Arrow again: should restore unsent 'new draft'
    view.input_field.keyPressEvent(down_event)
    assert view.input_field.text() == "new draft"


def test_chat_view_voice_command_added_to_history(qapp, jarvis_gui_core):
    """Verifies that voice-spoken commands are automatically recorded in command history and recallable with Up Arrow."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    view = ChatView(jarvis_gui_core)
    # Simulate voice message arrival
    view.add_message("You", "antigravity chalao")
    assert "antigravity chalao" in view.input_field.history

    # Press Up Arrow in empty input field: should recall voice command
    up_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Up, Qt.NoModifier)
    view.input_field.keyPressEvent(up_event)
    assert view.input_field.text() == "antigravity chalao"


def test_chat_view_escape_key_restores_draft(qapp, jarvis_gui_core):
    """Verifies that Escape key cancels history navigation and restores the in-progress draft."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    view = ChatView(jarvis_gui_core)
    view.input_field.add_history("previous command")

    view.input_field.setText("my unfinished text")
    up_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Up, Qt.NoModifier)
    view.input_field.keyPressEvent(up_event)
    assert view.input_field.text() == "previous command"

    escape_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    view.input_field.keyPressEvent(escape_event)
    assert view.input_field.text() == "my unfinished text"


def test_dashboard_view_new_telemetry_cards(qapp, jarvis_gui_core):
    """Verifies that DashboardView exposes Active Target, Proactive AI, and Cognitive Memory cards."""
    view = DashboardView(jarvis_gui_core)
    view.refresh_metrics()
    assert hasattr(view, "card_active_app")
    assert hasattr(view, "card_proactive")
    assert hasattr(view, "card_memory_store")
    assert "Desktop" in view.card_active_app.value_lbl.text() or view.card_active_app.value_lbl.text() != "--"
    assert "Facts" in view.card_memory_store.value_lbl.text()


def test_plugins_view_search_and_selection(qapp, jarvis_gui_core):
    """Verifies search filtering and row selection inspector in PluginsView."""
    view = PluginsView(jarvis_gui_core)
    assert hasattr(view, "search_input")
    assert hasattr(view, "lbl_details_title")

    # Filter for 'browser'
    view.search_input.setText("browser")
    assert view.table.rowCount() >= 1

    # Select first row
    view.table.selectRow(0)
    assert "PLUGIN:" in view.lbl_details_title.text()


def test_memory_view_tier_filtering_and_dialog(qapp, jarvis_gui_core):
    """Verifies multi-tier cognitive memory switching and add button in MemoryView."""
    view = MemoryView(jarvis_gui_core)
    assert hasattr(view, "btn_add_fact")

    # Switch to preferences tier
    view._set_tier("preferences")
    assert view.active_tier == "preferences"
    assert "PREFERENCE KEY" in view.table.horizontalHeaderItem(1).text()

    # Switch to episodic tier
    view._set_tier("episodic")
    assert view.active_tier == "episodic"
    assert "INTERACTION / CONTENT" in view.table.horizontalHeaderItem(2).text()


def test_learning_view_teach_word_and_suggestions(qapp, jarvis_gui_core):
    """Verifies Teach Word button and dynamic suggestions panel in LearningView."""
    view = LearningView(jarvis_gui_core)
    assert hasattr(view, "btn_teach_word")
    assert hasattr(view, "sug_text")
    view.refresh_learning_data()
    assert len(view.sug_text.text()) > 0


def test_workflows_view_starters_and_creation(qapp, jarvis_gui_core):
    """Verifies starter routine installation and create button in WorkflowsView."""
    view = WorkflowsView(jarvis_gui_core)
    assert hasattr(view, "btn_add_wf")
    assert hasattr(view, "btn_starters")

    # Install starter routines
    view._install_starter_routines()
    assert view.cards_layout.count() >= 3


def test_activity_log_view_dual_mode_toggle(qapp, jarvis_gui_core):
    """Verifies toggle between Console and Desktop Activity Timeline in ActivityLogView."""
    view = ActivityLogView(jarvis_gui_core)
    assert hasattr(view, "timeline_table")

    # Switch to Desktop Activity Timeline
    view._set_mode("timeline")
    assert view.active_mode == "timeline"
    assert view.view_stack.currentIndex() == 1

    # Switch back to Console
    view._set_mode("console")
    assert view.active_mode == "console"
    assert view.view_stack.currentIndex() == 0


def test_settings_view_proactive_intelligence_card(qapp, jarvis_gui_core):
    """Verifies Proactive Intelligence settings controls in SettingsView."""
    view = SettingsView(jarvis_gui_core)
    assert hasattr(view, "combo_pro_enable")
    assert hasattr(view, "combo_conf")
    assert hasattr(view, "combo_guard")

    # Save proactive settings
    view.combo_pro_enable.setCurrentIndex(0)
    view._save_proactive_settings()
    assert "saved successfully" in view.pro_status.text()


def test_chat_view_auto_scroll_pins_to_bottom_on_new_message(qapp, jarvis_gui_core):
    """Verifies that ChatView automatically scrolls to the absolute bottom when new messages arrive."""
    view = ChatView(jarvis_gui_core)
    view.resize(600, 400)
    view.show()

    # Add enough messages to require scrolling
    for i in range(25):
        view.add_message("Jarvis", f"Message block {i} with content to occupy vertical space.")
    qapp.processEvents()

    vsb = view.chat_display.verticalScrollBar()
    assert vsb.maximum() > 0
    assert vsb.value() == vsb.maximum(), f"Scrollbar value {vsb.value()} does not match maximum {vsb.maximum()}"

    # Add a multi-line latest response
    view.add_message("Jarvis", "Latest response from Jarvis\nSecond line of response\nThird line of response")
    qapp.processEvents()

    assert vsb.value() == vsb.maximum(), f"Latest message not scrolled to bottom: value={vsb.value()}, max={vsb.maximum()}"
    view.close()


def test_chat_view_auto_scroll_preserves_user_history_inspection(qapp, jarvis_gui_core):
    """Verifies that when a user manually scrolls up to read history, auto-scroll is paused until re-engaged."""
    view = ChatView(jarvis_gui_core)
    view.resize(600, 400)
    view.show()

    for i in range(30):
        view.add_message("Jarvis", f"Message block {i}")
    qapp.processEvents()

    vsb = view.chat_display.verticalScrollBar()
    assert vsb.value() == vsb.maximum()

    # User manually scrolls up to inspect history
    vsb.setValue(100)
    qapp.processEvents()
    assert view.chat_display._auto_scroll_to_bottom is False

    # A new explicit message from user or reply forces scroll to bottom
    view.add_message("You", "User new command")
    qapp.processEvents()
    assert view.chat_display._auto_scroll_to_bottom is True
    assert vsb.value() == vsb.maximum()
    view.close()


def test_settings_view_update_actions_are_non_blocking(qapp, jarvis_gui_core):
    """Verifies that clicking Windows Update or Check Updates runs asynchronously and never freezes the UI."""
    from unittest.mock import patch
    from gui.views.settings_view import SettingsView, SoftwareUpdateWorker
    from core.software_update.models import UpdatePlan, UpdateScope

    view = SettingsView(jarvis_gui_core)
    view.show()
    qapp.processEvents()

    # Buttons should initially be enabled
    assert view.btn_check_upd.isEnabled() is True
    assert view.btn_win_upd.isEnabled() is True
    assert view.btn_run_upd.isEnabled() is True

    # Trigger Windows Update check
    with patch("os.startfile", create=True):
        with patch.object(SoftwareUpdateWorker, "start") as mock_start:
            view._gui_windows_update()
            assert mock_start.called
            # Buttons are disabled while worker is in flight
            assert view.btn_win_upd.isEnabled() is False
            assert "Checking Windows updates" in view.lbl_upd_summary.text()

            # Simulate worker completing
            dummy_plan = UpdatePlan(requested_scope=UpdateScope.OS, windows_updates=[])
            view._on_windows_check_done(dummy_plan, "All Windows systems up to date.")
            assert view.btn_win_upd.isEnabled() is True
            assert "Windows updates: 0 available" in view.lbl_upd_summary.text()

    view.close()


def test_gui_bluetooth_settings_and_status_bar_live_mic(qapp, jarvis_gui_core):
    """Verifies that Bluetooth earbuds connections update the GUI settings card and main status bar live."""
    from voice.device_manager import AudioDeviceInfo
    from gui.views.settings_view import SettingsView

    window = JarvisMainWindow(jarvis_gui_core)
    window.show()
    qapp.processEvents()

    # 1. Initial status bar mic display
    assert hasattr(window, "mic_status")
    initial_text = window.mic_status.text()
    assert "Waiting for command" in initial_text

    # 2. Simulate Bluetooth earbuds connection event
    bt_device = AudioDeviceInfo(
        index=3,
        name="CMF Buds 2 Hands-Free AG Audio",
        clean_name="CMF Buds 2",
        is_bluetooth=True,
        is_earbuds=True,
        is_usb=False,
        is_default=False,
        score=100,
        hostapi_name="MME"
    )
    window.active_mic_updated.emit(bt_device)
    qapp.processEvents()

    # 3. Check status bar dynamically updated with Bluetooth icon and name
    updated_text = window.mic_status.text()
    assert "🎧" in updated_text
    assert "CMF Buds 2" in updated_text

    # 4. Verify SettingsView Bluetooth card elements
    settings_view = SettingsView(jarvis_gui_core)
    settings_view.show()
    qapp.processEvents()

    assert hasattr(settings_view, "lbl_bt_badge")
    assert hasattr(settings_view, "chk_auto_switch")
    assert hasattr(settings_view, "chk_announce_bt")

    # 5. Emit live topology update to settings view
    topology_summary = {
        "active_input_name": "CMF Buds 2 Hands-Free AG Audio",
        "is_input_bluetooth": True,
        "active_output_name": "CMF Buds 2 Stereo",
        "is_output_bluetooth": True,
        "earbuds_paired": True,
        "auto_switch_enabled": True
    }
    settings_view.topology_updated.emit(topology_summary)
    qapp.processEvents()

    assert "Connected" in settings_view.lbl_bt_badge.text()
    assert "CMF Buds 2" in settings_view.lbl_bt_device.text()

    settings_view.close()
    window.close()


def test_taskbar_and_window_icon_assets(qapp, jarvis_gui_core):
    """Verifies that application window and taskbar icons are loaded, valid, and multi-resolution."""
    import sys
    assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "gui", "assets")
    ico_path = os.path.join(assets_dir, "jarvis_logo.ico")
    png_path = os.path.join(assets_dir, "jarvis_logo.png")
    header_path = os.path.join(assets_dir, "logo_header_36.png")

    assert os.path.exists(ico_path), "jarvis_logo.ico must exist"
    assert os.path.exists(png_path), "jarvis_logo.png must exist"
    assert os.path.exists(header_path), "logo_header_36.png must exist"

    window = JarvisMainWindow(jarvis_gui_core)
    icon = window.windowIcon()
    assert not icon.isNull(), "JarvisMainWindow must have a valid window icon"
    sizes = [(s.width(), s.height()) for s in icon.availableSizes()]
    assert any(w in [16, 24, 32, 48, 64, 128, 256] for w, _ in sizes)

    if sys.platform == "win32":
        import ctypes
        res = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("jarvis.ai.desktop.assistant.v2")
        assert res == 0

    window.close()
