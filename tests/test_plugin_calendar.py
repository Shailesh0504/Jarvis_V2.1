# tests/test_plugin_calendar.py
"""Automated unit and verification tests for upgraded Calendar plugin."""

import datetime
import os
import pytest
from plugins.calendar.plugin import CalendarPlugin


@pytest.fixture
def calendar_plugin(tmp_path):
    plugin = CalendarPlugin()
    plugin.db_path = str(tmp_path / "test_calendar.db")
    plugin._init_db()
    return plugin


def test_calendar_manifest_and_health(calendar_plugin):
    manifest = calendar_plugin.get_manifest()
    assert manifest.name == "calendar"
    assert len(manifest.actions) == 13

    health = calendar_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 13


def test_add_list_and_agenda(calendar_plugin):
    today_str = datetime.date.today().strftime("%Y-%m-%d 14:00")
    res_add = calendar_plugin.execute("add_event", {
        "title": "Architecture Review",
        "start_time": today_str,
        "duration_minutes": 45
    })
    assert res_add.success is True
    eid = res_add.data["event"]["id"]

    # List events
    res_list = calendar_plugin.execute("list_events", {})
    assert res_list.success is True
    assert res_list.data["count"] >= 1

    # Today agenda
    res_agenda = calendar_plugin.execute("get_today_agenda", {})
    assert res_agenda.success is True
    assert res_agenda.data["count"] >= 1


def test_update_and_delete_event(calendar_plugin):
    res_add = calendar_plugin.execute("add_event", {
        "title": "Old Meeting",
        "start_time": "2026-10-01 10:00",
        "duration_minutes": 30
    })
    eid = res_add.data["event"]["id"]

    # Update event
    res_up = calendar_plugin.execute("update_event", {
        "event_id": eid,
        "title": "New Meeting Title",
        "start_time": "2026-10-01 11:00"
    })
    assert res_up.success is True
    assert res_up.data["title"] == "New Meeting Title"

    # Delete event
    res_del = calendar_plugin.execute("delete_event", {"event_id": eid})
    assert res_del.success is True


def test_search_and_conflict_check(calendar_plugin):
    target_time = "2026-11-15 15:30"
    calendar_plugin.execute("add_event", {
        "title": "Project Pitch",
        "start_time": target_time,
        "duration_minutes": 60
    })

    # Search
    res_search = calendar_plugin.execute("search_events", {"query": "Pitch"})
    assert res_search.success is True
    assert res_search.data["count"] >= 1

    # Conflict check
    res_conf = calendar_plugin.execute("check_conflict", {"start_time": target_time})
    assert res_conf.success is True
    assert res_conf.data["has_conflict"] is True

    res_free = calendar_plugin.execute("check_conflict", {"start_time": "2026-11-16 09:00"})
    assert res_free.success is True
    assert res_free.data["has_conflict"] is False


def test_ics_export_and_import(calendar_plugin, tmp_path):
    calendar_plugin.execute("add_event", {
        "title": "Team Sync",
        "start_time": "2026-12-01 10:00",
        "duration_minutes": 60
    })

    ics_path = str(tmp_path / "export.ics")
    res_exp = calendar_plugin.execute("export_events_ics", {"output_path": ics_path})
    assert res_exp.success is True
    assert os.path.isfile(ics_path)
    assert os.path.getsize(ics_path) > 0

    # Import ICS
    res_imp = calendar_plugin.execute("import_events_ics", {"file_path": ics_path})
    assert res_imp.success is True
    assert res_imp.data["imported_count"] >= 1
