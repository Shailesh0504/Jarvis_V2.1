# tests/test_reminder_architecture.py
"""
Comprehensive unit and regression tests for the dedicated Reminder Plugin,
background scheduler, SQLite persistence, temporal NLU parsing, and GUI integration.
"""

import datetime
import os
import time
import pytest
from unittest.mock import patch, MagicMock

from brain.semantic_parser import HinglishNLUParser, SemanticAction
from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager
from plugins.reminder.models import ReminderItem, ReminderStatus, RecurrenceType
from plugins.reminder.database import ReminderDatabase
from plugins.reminder.scheduler import ReminderScheduler
from plugins.reminder.plugin import ReminderPlugin


@pytest.fixture
def jarvis_app(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_reminders_app.db")
    mem = MemoryManager(db_path=db_path)
    llm = MockLLMProvider()
    resp_gen = ResponseGenerator(llm_provider=llm)
    plugins = PluginManager(plugin_dir="plugins")
    plugins.discover_and_load()
    reminder_db = str(tmp_path / "test_reminders_plugin_iso.db")
    plugins._plugins["reminder"] = ReminderPlugin(db_path=reminder_db)

    core.initialize_subsystems(
        memory_manager=mem,
        learning_manager=None,
        brain=resp_gen,
        classifier=None,
        plugin_manager=plugins,
        response_generator=resp_gen
    )
    return core


def test_nlu_relative_time_parsing():
    """Verify relative time extraction in Hindi, Hinglish, and English."""
    # 1. 10 minute baad paani peene
    act1 = HinglishNLUParser.parse("mujhe 10 minute baad paani peene yaad dilana")
    assert act1 is not None
    assert act1.intent == "CREATE_REMINDER"
    assert act1.service == "reminder"
    assert act1.action == "create_reminder"
    assert "paani peene" in act1.parameters["title"]
    assert act1.parameters["recurrence"] == "none"
    remind_dt = datetime.datetime.fromisoformat(act1.parameters["remind_time"])
    now_dt = datetime.datetime.now().astimezone()
    # Check that scheduled time is roughly 10 mins in the future (+/- 1 min)
    delta_mins = (remind_dt - now_dt).total_seconds() / 60
    assert 9 <= delta_mins <= 11

    # 2. 30 minutes baad check karne
    act2 = HinglishNLUParser.parse("30 minutes baad mujhe check karne yaad dilana")
    assert act2 is not None
    assert act2.intent == "CREATE_REMINDER"
    assert "check karne" in act2.parameters["title"]
    remind_dt2 = datetime.datetime.fromisoformat(act2.parameters["remind_time"])
    delta_mins2 = (remind_dt2 - now_dt).total_seconds() / 60
    assert 29 <= delta_mins2 <= 31


def test_nlu_absolute_time_parsing():
    """Verify absolute date and time extraction."""
    # 1. Kal subah 8 baje papa ko call
    act1 = HinglishNLUParser.parse("kal subah 8 baje papa ko call karne ka reminder laga do")
    assert act1 is not None
    assert act1.intent == "CREATE_REMINDER"
    assert "papa" in act1.parameters["title"]
    remind_dt1 = datetime.datetime.fromisoformat(act1.parameters["remind_time"])
    now_dt = datetime.datetime.now().astimezone()
    assert remind_dt1.date() == (now_dt + datetime.timedelta(days=1)).date()
    assert remind_dt1.hour == 8
    assert remind_dt1.minute == 0

    # 2. Aaj 7 PM medicine
    act2 = HinglishNLUParser.parse("aaj 7 PM mujhe medicine yaad dilana")
    assert act2 is not None
    assert act2.intent == "CREATE_REMINDER"
    assert "medicine" in act2.parameters["title"]
    remind_dt2 = datetime.datetime.fromisoformat(act2.parameters["remind_time"])
    assert remind_dt2.hour == 19
    assert remind_dt2.minute == 0

    # 3. Remind me tomorrow at 5 PM
    act3 = HinglishNLUParser.parse("remind me tomorrow at 5 PM")
    assert act3 is not None
    assert act3.intent == "CREATE_REMINDER"
    remind_dt3 = datetime.datetime.fromisoformat(act3.parameters["remind_time"])
    assert remind_dt3.date() == (now_dt + datetime.timedelta(days=1)).date()
    assert remind_dt3.hour == 17


def test_nlu_recurring_reminders():
    """Verify recurring reminders for daily, weekly, and day-specific patterns."""
    # 1. Har din 9 baje exercise
    act1 = HinglishNLUParser.parse("har din 9 baje mujhe exercise yaad dilana")
    assert act1 is not None
    assert act1.intent == "CREATE_REMINDER"
    assert "exercise" in act1.parameters["title"]
    assert act1.parameters["recurrence"] == "daily"
    remind_dt1 = datetime.datetime.fromisoformat(act1.parameters["remind_time"])
    assert remind_dt1.hour == 9

    # 2. Har Monday meeting
    act2 = HinglishNLUParser.parse("har Monday meeting ka reminder")
    assert act2 is not None
    assert act2.intent == "CREATE_REMINDER"
    assert "meeting" in act2.parameters["title"]
    assert act2.parameters["recurrence"] == "weekly"
    assert act2.parameters["recurrence_rule"] == "monday"

    # 3. Remind me every day at 8 AM
    act3 = HinglishNLUParser.parse("remind me every day at 8 AM")
    assert act3 is not None
    assert act3.intent == "CREATE_REMINDER"
    assert act3.parameters["recurrence"] == "daily"
    remind_dt3 = datetime.datetime.fromisoformat(act3.parameters["remind_time"])
    assert remind_dt3.hour == 8


def test_nlu_ambiguous_time_clarification():
    """Verify that ambiguous time expressions (e.g. 'shaam ko') prompt for clarification."""
    act = HinglishNLUParser.parse("shaam ko paani peene yaad dilana")
    assert act is not None
    assert act.intent == "CREATE_REMINDER"
    assert act.clarification_prompt is not None
    assert "kitne baje" in act.clarification_prompt
    assert "Shaam" in act.clarification_prompt


def test_nlu_management_commands():
    """Verify NLU parsing of list, cancel, snooze, and toggle commands."""
    # 1. List reminders
    act_list = HinglishNLUParser.parse("mere reminders dikhao")
    assert act_list is not None
    assert act_list.intent == "LIST_REMINDERS"
    assert act_list.service == "reminder"
    assert act_list.action == "list_reminders"

    # 2. Aaj ke reminders
    act_today = HinglishNLUParser.parse("aaj ke reminders batao")
    assert act_today is not None
    assert act_today.parameters["filter"] == "today"

    # 3. Cancel reminder 5
    act_cancel = HinglishNLUParser.parse("reminder 5 cancel karo")
    assert act_cancel is not None
    assert act_cancel.intent == "CANCEL_REMINDER"
    assert act_cancel.parameters["reminder_id"] == 5

    # 4. Snooze reminder 10 minutes
    act_snooze = HinglishNLUParser.parse("is reminder ko 10 minute snooze karo")
    assert act_snooze is not None
    assert act_snooze.intent == "SNOOZE_REMINDER"
    assert act_snooze.parameters["minutes"] == 10

    # 5. Disable reminders
    act_toggle = HinglishNLUParser.parse("reminders band karo")
    assert act_toggle is not None
    assert act_toggle.intent == "TOGGLE_REMINDERS"
    assert act_toggle.parameters["enabled"] is False


def test_reminder_database_persistence(tmp_path):
    """Verify SQLite persistent storage across simulated restart."""
    db_file = str(tmp_path / "test_persist.db")
    db1 = ReminderDatabase(db_path=db_file)

    now_iso = datetime.datetime.now().astimezone().isoformat()
    r = ReminderItem(
        title="Drink Water",
        remind_time=now_iso,
        recurrence="none"
    )
    rid = db1.add_reminder(r)
    assert rid > 0

    # Simulate restart by initializing a new ReminderDatabase on the same file
    db2 = ReminderDatabase(db_path=db_file)
    fetched = db2.get_reminder(rid)
    assert fetched is not None
    assert fetched.id == rid
    assert fetched.title == "Drink Water"
    assert fetched.status == ReminderStatus.PENDING.value


def test_duplicate_voice_command_suppression(tmp_path):
    """Verify duplicate suppression prevents creating identical reminders twice."""
    db_file = str(tmp_path / "test_dup.db")
    plugin = ReminderPlugin(db_path=db_file)

    target_time = (datetime.datetime.now().astimezone() + datetime.timedelta(minutes=10)).isoformat()
    res1 = plugin.execute("create_reminder", {"title": "Take Medicine", "remind_time": target_time})
    assert res1.success is True
    assert res1.data.get("duplicate") is not True

    # Immediate second call with identical title and time
    res2 = plugin.execute("create_reminder", {"title": "Take Medicine", "remind_time": target_time})
    assert res2.success is True
    assert res2.data.get("duplicate") is True
    assert "pehle se set hai" in res2.data["message"]

    plugin.scheduler.stop()


def test_missed_reminders_recovery_on_startup(tmp_path):
    """Verify reminders that became due while Jarvis was closed are marked MISSED and not silently lost."""
    db_file = str(tmp_path / "test_missed.db")
    db = ReminderDatabase(db_path=db_file)

    # Insert a reminder in the past
    past_iso = (datetime.datetime.now().astimezone() - datetime.timedelta(hours=2)).isoformat()
    r = ReminderItem(title="Doctor Appointment", remind_time=past_iso, status=ReminderStatus.PENDING.value)
    rid = db.add_reminder(r)

    # Start scheduler and trigger startup missed recovery
    triggered_items = []
    def on_trig(item):
        triggered_items.append(item)

    scheduler = ReminderScheduler(db=db, on_reminder_triggered=on_trig, poll_interval=0.5)
    scheduler._handle_missed_reminders()

    updated = db.get_reminder(rid)
    assert updated.status == ReminderStatus.MISSED.value
    assert len(triggered_items) == 1
    assert triggered_items[0].title == "Doctor Appointment"


def test_snooze_and_cancel_lifecycle(tmp_path):
    """Verify snooze and cancel operations."""
    db_file = str(tmp_path / "test_lifecycle.db")
    plugin = ReminderPlugin(db_path=db_file)

    target_time = (datetime.datetime.now().astimezone() + datetime.timedelta(minutes=5)).isoformat()
    res = plugin.execute("create_reminder", {"title": "Team Standup", "remind_time": target_time})
    rid = res.data["id"]

    # Snooze +10 min
    res_snooze = plugin.execute("snooze_reminder", {"reminder_id": rid, "minutes": 10})
    assert res_snooze.success is True
    assert "snooze" in res_snooze.data["message"]
    item = plugin.db.get_reminder(rid)
    assert item.status == ReminderStatus.SNOOZED.value
    assert item.snooze_count == 1

    # Cancel
    res_cancel = plugin.execute("cancel_reminder", {"reminder_id": rid})
    assert res_cancel.success is True
    assert "cancel" in res_cancel.data["message"]
    item_cancelled = plugin.db.get_reminder(rid)
    assert item_cancelled.status == ReminderStatus.CANCELLED.value

    plugin.scheduler.stop()


def test_end_to_end_reminder_no_fallback_prompt(jarvis_app):
    """End-to-end test proving reminder commands execute directly and never fall into conversational fallback."""
    # 1. Create relative reminder
    resp1 = jarvis_app.process_input("mujhe 10 minute baad paani peene yaad dilana")
    assert "Main samajh gaya Boss! Bataiye" not in resp1
    assert "Reminder set kar diya hai" in resp1
    assert "paani peene" in resp1

    # 2. Create absolute reminder
    resp2 = jarvis_app.process_input("kal subah 8 baje papa ko call karne ka reminder laga do")
    assert "Main samajh gaya Boss" not in resp2
    assert "Reminder set kar diya hai" in resp2

    # 3. List reminders
    resp3 = jarvis_app.process_input("mere reminders dikhao")
    assert "Main samajh gaya Boss" not in resp3
    assert "reminders" in resp3.lower()

    # 4. Snooze reminder
    resp4 = jarvis_app.process_input("is reminder ko 10 minute snooze karo")
    assert "Main samajh gaya Boss" not in resp4
    assert "snooze" in resp4.lower()
