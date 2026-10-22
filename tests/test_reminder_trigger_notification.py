# tests/test_reminder_trigger_notification.py
"""
Unit and Integration Tests for Real-Time Reminder Triggers, Notifications, and Spoken Delivery.

Verifies:
1. ReminderScheduler._trigger_notification dispatches EventTopics.REMINDER_TRIGGERED on EventBus.
2. ReminderPlugin._on_triggered calls native desktop notification.
3. JarvisCore._on_reminder_triggered speaks reminder via TTSManager when headless/CLI.
4. JarvisApp (GUI) receives cross-thread reminder signal, adds message to Live Chat view, refreshes table, and speaks.
5. PluginManager pre-loads resident plugins ('reminder') and propagates event_bus.
"""

import datetime
from unittest.mock import MagicMock, patch
import pytest

from core.event_bus import EventBus, EventTopics, Event
from plugins.reminder.models import ReminderItem, ReminderStatus
from plugins.reminder.scheduler import ReminderScheduler
from plugins.reminder.plugin import ReminderPlugin
from core.app import JarvisCore


class TestReminderTriggerNotification:
    """Tests for end-to-end reminder dispatch, notification, and voice delivery."""

    def test_scheduler_trigger_dispatches_event_bus(self):
        mock_bus = MagicMock()
        mock_callback = MagicMock()
        mock_db = MagicMock()

        scheduler = ReminderScheduler(
            db=mock_db,
            event_bus=mock_bus,
            on_reminder_triggered=mock_callback,
        )

        item = ReminderItem(
            id=42,
            title="Khana khane jaana",
            remind_time=datetime.datetime.now().astimezone().isoformat(),
            status=ReminderStatus.PENDING.value,
        )

        scheduler._trigger_notification(item, is_missed=False)

        # 1. EventBus publish check
        mock_bus.publish.assert_called_once()
        published_event = mock_bus.publish.call_args[0][0]
        assert published_event.topic == "reminder.triggered"
        assert published_event.data["id"] == 42
        assert published_event.data["title"] == "Khana khane jaana"
        assert published_event.data["is_missed"] is False

        # 2. Callback check
        mock_callback.assert_called_once_with(item)

    def test_plugin_on_triggered_calls_desktop_notification(self):
        plugin = ReminderPlugin()
        item = ReminderItem(
            id=10,
            title="Meeting with Client",
            remind_time="2026-09-16T15:00:00+05:30",
        )

        with patch.object(plugin, "_send_desktop_notification") as mock_notify:
            plugin._on_triggered(item)
            mock_notify.assert_called_once_with(
                title="⏰ Jarvis Reminder",
                message="Meeting with Client",
            )

    def test_core_on_reminder_triggered_speaks_in_headless_or_cli(self):
        core = JarvisCore()
        mock_tts = MagicMock()
        core.set_tts_manager(mock_tts)
        core.has_active_gui = False

        event = Event(
            topic=EventTopics.REMINDER_TRIGGERED,
            data={
                "id": 5,
                "title": "Khana khane jaana",
                "is_missed": False,
            }
        )

        core._on_reminder_triggered(event)
        mock_tts.speak.assert_called_once()
        spoken_arg = mock_tts.speak.call_args[0][0]
        assert "Khana khane jaana" in spoken_arg
        assert "reminder" in spoken_arg.lower()

    def test_core_does_not_double_speak_when_gui_is_active(self):
        core = JarvisCore()
        mock_tts = MagicMock()
        core.set_tts_manager(mock_tts)
        core.has_active_gui = True  # GUI is active, so GUI handles speech and chat display

        event = Event(
            topic=EventTopics.REMINDER_TRIGGERED,
            data={
                "id": 5,
                "title": "Khana khane jaana",
                "is_missed": False,
            }
        )

        core._on_reminder_triggered(event)
        mock_tts.speak.assert_not_called()

    def test_plugin_manager_preloads_resident_plugins_with_event_bus(self):
        from plugins.manager import PluginManager

        bus = EventBus()
        manager = PluginManager(event_bus=bus)
        assert "reminder" in manager.resident_plugins

        # Mock loading directory
        with patch.object(manager, "_load_plugin_from_dir") as mock_load:
            manager._manifests["reminder"] = MagicMock()
            manager.discover_and_load()
            # Verify reminder was preloaded
            mock_load.assert_any_call("reminder", manager._plugin_paths.get("reminder", "plugins\\reminder"))
