# tests/test_plugin_reminder.py
import datetime
import os
import pytest
from plugins.reminder.plugin import ReminderPlugin


@pytest.fixture
def reminder_plugin(tmp_path):
    db_file = str(tmp_path / "test_reminders.db")
    plugin = ReminderPlugin(db_path=db_file)
    yield plugin
    plugin.scheduler.stop()


def test_reminder_complete_and_stats(reminder_plugin):
    now = datetime.datetime.now().astimezone()
    t1 = (now + datetime.timedelta(hours=1)).isoformat()
    t2 = (now + datetime.timedelta(hours=2)).isoformat()

    r1 = reminder_plugin.execute("create_reminder", {"title": "Task 1", "remind_time": t1})
    r2 = reminder_plugin.execute("create_reminder", {"title": "Task 2", "remind_time": t2})
    assert r1.success is True
    assert r2.success is True

    # Complete
    comp_res = reminder_plugin.execute("complete_reminder", {"reminder_id": r1.data["id"]})
    assert comp_res.success is True
    assert comp_res.data["status"] == "completed"

    # Stats
    stats_res = reminder_plugin.execute("get_reminder_stats", {})
    assert stats_res.success is True
    assert stats_res.data["completed"] == 1
    assert stats_res.data["pending"] == 1
    assert stats_res.data["completion_rate_percent"] == 50.0


def test_reminder_upcoming_countdown_search(reminder_plugin):
    now = datetime.datetime.now().astimezone()
    t = (now + datetime.timedelta(minutes=45)).isoformat()
    r = reminder_plugin.execute("create_reminder", {"title": "Meeting with Client", "remind_time": t})
    rid = r.data["id"]

    # Upcoming
    up_res = reminder_plugin.execute("get_next_upcoming", {})
    assert up_res.success is True
    assert up_res.data["reminder"]["id"] == rid
    assert up_res.data["minutes_remaining"] <= 45.1

    # Countdown
    count_res = reminder_plugin.execute("calculate_countdown", {"reminder_id": rid})
    assert count_res.success is True
    assert count_res.data["is_past"] is False
    assert count_res.data["minutes"] <= 45

    # Search
    search_res = reminder_plugin.execute("search_reminders", {"query": "Client"})
    assert search_res.success is True
    assert search_res.data["count"] == 1
    assert search_res.data["reminders"][0]["id"] == rid


def test_reminder_bulk_cancel_and_clear(reminder_plugin):
    future_time = (datetime.datetime.now().astimezone() + datetime.timedelta(hours=1)).isoformat()
    reminder_plugin.execute("create_reminder", {"title": "A", "remind_time": future_time})
    reminder_plugin.execute("create_reminder", {"title": "B", "remind_time": future_time})

    cancel_res = reminder_plugin.execute("bulk_cancel_reminders", {"status": "pending"})
    assert cancel_res.success is True
    assert cancel_res.data["cancelled_count"] >= 2

    # Clear completed/cancelled
    clear_res = reminder_plugin.execute("clear_completed_reminders", {})
    assert clear_res.success is True
    assert clear_res.data["purged_count"] >= 2


def test_reminder_export_import_and_reschedule(reminder_plugin, tmp_path):
    now = datetime.datetime.now().astimezone().isoformat()
    reminder_plugin.execute("create_reminder", {"title": "Export Me", "remind_time": now})

    # Export JSON
    json_path = str(tmp_path / "reminders.json")
    exp_res = reminder_plugin.execute("export_reminders", {"output_path": json_path, "format": "json"})
    assert exp_res.success is True
    assert os.path.isfile(json_path)

    # Export ICS
    ics_path = str(tmp_path / "reminders.ics")
    exp_ics = reminder_plugin.execute("export_reminders", {"output_path": ics_path, "format": "ics"})
    assert exp_ics.success is True
    assert os.path.isfile(ics_path)

    # Import
    imp_res = reminder_plugin.execute("import_reminders", {"file_path": json_path})
    assert imp_res.success is True
    assert imp_res.data["imported_count"] >= 1

    # Reschedule missed
    resched_res = reminder_plugin.execute("reschedule_missed_reminders", {"minutes_ahead": 30})
    assert resched_res.success is True
