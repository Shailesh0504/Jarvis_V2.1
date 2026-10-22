# tests/test_plugin_notifications.py
"""Automated unit and verification tests for upgraded Notifications plugin."""

import json
import os
import pytest
from plugins.notifications.plugin import NotificationsPlugin


@pytest.fixture
def notif_plugin(tmp_path):
    plugin = NotificationsPlugin()
    plugin.db_path = str(tmp_path / "test_notifications.db")
    plugin._init_db()
    return plugin


def test_notifications_manifest_and_health(notif_plugin):
    manifest = notif_plugin.get_manifest()
    assert manifest.name == "notifications"
    assert len(manifest.actions) == 13

    health = notif_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 13


def test_show_and_list_notifications(notif_plugin):
    res = notif_plugin.execute("show_notification", {
        "title": "Build Finished",
        "message": "Project compilation succeeded without errors."
    })
    assert res.success is True
    assert "notification_id" in res.data
    nid = res.data["notification_id"]

    # Verify state hook
    v = notif_plugin.verify_state("show_notification", {}, res.data)
    assert v is not None
    assert v.verified is True

    # List notifications
    res_list = notif_plugin.execute("list_notifications", {"limit": 10})
    assert res_list.success is True
    assert res_list.data["count"] >= 1
    assert any(n["id"] == nid for n in res_list.data["notifications"])


def test_warning_error_and_actionable(notif_plugin):
    res_warn = notif_plugin.execute("show_warning_notification", {
        "title": "Low Disk Space",
        "message": "Drive C has less than 10% space remaining."
    })
    assert res_warn.success is True
    assert res_warn.data["type"] == "warning"

    res_err = notif_plugin.execute("show_error_notification", {
        "title": "Service Crash",
        "message": "Core daemon encountered unexpected exit."
    })
    assert res_err.success is True
    assert res_err.data["type"] == "error"

    res_act = notif_plugin.execute("show_actionable_notification", {
        "title": "Software Update",
        "message": "Version 2.2 is available.",
        "action_command": "jarvis://update"
    })
    assert res_act.success is True
    assert res_act.data["type"] == "actionable"


def test_unread_count_and_mark_read(notif_plugin):
    notif_plugin.execute("show_notification", {"title": "Msg 1", "message": "Content 1"})
    notif_plugin.execute("show_notification", {"title": "Msg 2", "message": "Content 2"})

    res_cnt = notif_plugin.execute("get_unread_notifications_count")
    assert res_cnt.success is True
    initial_unread = res_cnt.data["unread_count"]
    assert initial_unread >= 2

    # Mark all read
    res_mark = notif_plugin.execute("mark_notification_as_read", {"notification_id": 0})
    assert res_mark.success is True

    res_cnt_after = notif_plugin.execute("get_unread_notifications_count")
    assert res_cnt_after.data["unread_count"] == 0


def test_search_and_filter(notif_plugin):
    notif_plugin.execute("show_warning_notification", {
        "title": "Security Alert",
        "message": "Unrecognized login attempt detected."
    })
    notif_plugin.execute("show_notification", {
        "title": "Music Track",
        "message": "Playing track 1."
    })

    # Search
    res_search = notif_plugin.execute("search_notifications", {"query": "Security"})
    assert res_search.success is True
    assert res_search.data["count"] >= 1
    assert any("Security Alert" in n["title"] for n in res_search.data["notifications"])

    # Filter by type
    res_filter = notif_plugin.execute("filter_notifications_by_type", {"notification_type": "warning"})
    assert res_filter.success is True
    assert res_filter.data["count"] >= 1
    assert all(n["type"] == "warning" for n in res_filter.data["notifications"])


def test_delete_clear_export_and_stats(notif_plugin, tmp_path):
    res_n1 = notif_plugin.execute("show_notification", {"title": "Note 1", "message": "Alpha"})
    res_n2 = notif_plugin.execute("show_warning_notification", {"title": "Note 2", "message": "Beta"})
    nid1 = res_n1.data["notification_id"]
    nid2 = res_n2.data["notification_id"]

    # Stats
    res_stats = notif_plugin.execute("get_notification_summary_stats")
    assert res_stats.success is True
    assert res_stats.data["total_count"] >= 2
    assert "warning" in res_stats.data["breakdown_by_type"]

    # Export to JSON
    export_json = tmp_path / "notif_export.json"
    res_exp = notif_plugin.execute("export_notification_history", {
        "destination_path": str(export_json),
        "format": "json"
    })
    assert res_exp.success is True
    assert os.path.exists(export_json)
    with open(export_json, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert len(data) >= 2

    # Delete single notification
    res_del = notif_plugin.execute("delete_notification_by_id", {"notification_id": nid1})
    assert res_del.success is True

    # Clear all
    res_clear = notif_plugin.execute("clear_notifications")
    assert res_clear.success is True

    res_list_empty = notif_plugin.execute("list_notifications")
    assert res_list_empty.data["count"] == 0
