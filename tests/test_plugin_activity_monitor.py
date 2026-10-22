# tests/test_plugin_activity_monitor.py
import os
import time
import pytest
from unittest.mock import patch
from plugins.activity_monitor.plugin import ActivityMonitorPlugin
from plugins.activity_monitor.memory import ActivityEvent


@pytest.fixture
def activity_plugin(tmp_path):
    plugin = ActivityMonitorPlugin()
    return plugin


def test_activity_idle_time_and_alert(activity_plugin):
    with patch.object(activity_plugin, "_get_idle_time_seconds", return_value=120.0):
        # Idle time
        res = activity_plugin.execute("get_idle_time", {})
        assert res.success is True
        assert res.data["idle_seconds"] == 120.0
        assert res.data["idle_minutes"] == 2.0
        assert res.data["is_idle"] is True

        # Idle alert
        alert_res = activity_plugin.execute("set_idle_alert", {"threshold_minutes": 1})
        assert alert_res.success is True
        assert alert_res.data["alert_triggered"] is True

        alert_res2 = activity_plugin.execute("set_idle_alert", {"threshold_minutes": 5})
        assert alert_res2.success is True
        assert alert_res2.data["alert_triggered"] is False


def test_activity_top_applications_and_productivity(activity_plugin):
    now = time.time()
    e1 = ActivityEvent(
        application="code",
        content_title="main.py - VS Code",
        start_time=now - 300,
        last_seen_time=now,
        state="closed"
    )
    e2 = ActivityEvent(
        application="spotify",
        content_title="Chill Beats",
        start_time=now - 120,
        last_seen_time=now,
        state="closed"
    )
    activity_plugin.memory._events.extend([e1, e2])

    # Top applications
    top_res = activity_plugin.execute("get_top_applications", {"limit": 2})
    assert top_res.success is True
    assert len(top_res.data["top_applications"]) == 2
    assert top_res.data["top_applications"][0]["application"] == "code"

    # Productivity score
    prod_res = activity_plugin.execute("get_productivity_score", {})
    assert prod_res.success is True
    assert prod_res.data["productivity_score"] > 0
    assert prod_res.data["productive_seconds"] >= 300.0


def test_activity_export_and_clear(activity_plugin, tmp_path):
    now = time.time()
    activity_plugin.memory._events.append(
        ActivityEvent(application="chrome", website="youtube", content_title="Music", start_time=now - 50, last_seen_time=now)
    )

    # Export to JSON
    json_path = str(tmp_path / "activity.json")
    exp_res = activity_plugin.execute("export_activity_log", {"output_path": json_path, "format": "json"})
    assert exp_res.success is True
    assert os.path.isfile(json_path)

    # Export to CSV
    csv_path = str(tmp_path / "activity.csv")
    exp_csv = activity_plugin.execute("export_activity_log", {"output_path": csv_path, "format": "csv"})
    assert exp_csv.success is True
    assert os.path.isfile(csv_path)

    # Clear history
    clear_res = activity_plugin.execute("clear_activity_history", {})
    assert clear_res.success is True
    assert len(activity_plugin.memory._events) == 0


def test_activity_summary_domains_switches_break(activity_plugin):
    now = time.time()
    evs = [
        ActivityEvent(application="code", website="", content_title="main.py", start_time=now - 600, last_seen_time=now - 300),
        ActivityEvent(application="chrome", website="youtube", content_title="Video", start_time=now - 300, last_seen_time=now - 100),
        ActivityEvent(application="code", website="", content_title="app.py", start_time=now - 100, last_seen_time=now)
    ]
    activity_plugin.memory._events.extend(evs)

    # Summary
    summary_res = activity_plugin.execute("get_session_summary", {})
    assert summary_res.success is True
    assert summary_res.data["total_events"] == 3
    assert summary_res.data["unique_applications_count"] == 2

    # Domains
    domain_res = activity_plugin.execute("track_website_domain", {})
    assert domain_res.success is True
    assert any(d["domain"] == "youtube" for d in domain_res.data["domains"])

    # Focus switches
    switch_res = activity_plugin.execute("get_focus_switches", {})
    assert switch_res.success is True
    assert switch_res.data["total_switches"] == 2

    # Break recommendation
    break_res = activity_plugin.execute("get_break_recommendation", {"max_continuous_minutes": 5})
    assert break_res.success is True
    assert break_res.data["recommend_break"] is True
