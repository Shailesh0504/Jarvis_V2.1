# tests/test_plugin_tasks.py
"""Automated unit and verification tests for upgraded Tasks plugin."""

import os
import pytest
from plugins.tasks.plugin import TasksPlugin


@pytest.fixture
def tasks_plugin(tmp_path):
    plugin = TasksPlugin()
    plugin.db_path = str(tmp_path / "test_tasks.db")
    plugin._init_db()
    return plugin


def test_tasks_manifest_and_health(tasks_plugin):
    manifest = tasks_plugin.get_manifest()
    assert manifest.name == "tasks"
    assert len(manifest.actions) == 13

    health = tasks_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 13


def test_add_list_and_complete_task(tasks_plugin):
    res_add = tasks_plugin.execute("add_task", {
        "title": "Upgrade Plugin Ecosystem",
        "priority": "urgent"
    })
    assert res_add.success is True
    tid = res_add.data["task"]["id"]

    # List pending tasks
    res_list = tasks_plugin.execute("list_tasks", {"status": "pending"})
    assert res_list.success is True
    assert res_list.data["count"] >= 1

    # Complete task
    res_comp = tasks_plugin.execute("complete_task", {"task_id": tid})
    assert res_comp.success is True


def test_task_priority_and_filtering(tasks_plugin):
    res1 = tasks_plugin.execute("add_task", {"title": "Low Task", "priority": "low"})
    res2 = tasks_plugin.execute("add_task", {"title": "Urgent Task", "priority": "urgent"})
    tid1 = res1.data["task"]["id"]
    tid2 = res2.data["task"]["id"]

    # Filter
    res_filter = tasks_plugin.execute("filter_tasks_by_priority", {"priority": "urgent"})
    assert res_filter.success is True
    assert any(t["id"] == tid2 for t in res_filter.data["tasks"])

    # Update priority
    res_up = tasks_plugin.execute("set_task_priority", {"task_id": tid1, "priority": "high"})
    assert res_up.success is True


def test_due_date_and_metrics(tasks_plugin):
    # Add overdue task
    tasks_plugin.execute("add_task", {"title": "Old Task", "due_date": "2020-01-01"})
    tasks_plugin.execute("add_task", {"title": "Future Task", "due_date": "2099-01-01"})

    # Overdue query
    res_overdue = tasks_plugin.execute("get_overdue_tasks", {})
    assert res_overdue.success is True
    assert res_overdue.data["count"] >= 1

    # Metrics
    res_metrics = tasks_plugin.execute("get_task_metrics", {})
    assert res_metrics.success is True
    assert res_metrics.data["metrics"]["total_tasks"] >= 2


def test_markdown_export(tasks_plugin, tmp_path):
    tasks_plugin.execute("add_task", {"title": "Exportable Task 1"})
    tasks_plugin.execute("add_task", {"title": "Exportable Task 2"})

    md_path = str(tmp_path / "todo.md")
    res_exp = tasks_plugin.execute("export_tasks_to_markdown", {"output_path": md_path})
    assert res_exp.success is True
    assert os.path.isfile(md_path)
    assert os.path.getsize(md_path) > 0


def test_delete_and_clear_completed(tasks_plugin):
    res_add = tasks_plugin.execute("add_task", {"title": "To be cleared"})
    tid = res_add.data["task"]["id"]
    tasks_plugin.execute("complete_task", {"task_id": tid})

    # Clear completed
    res_clear = tasks_plugin.execute("clear_completed_tasks", {})
    assert res_clear.success is True
    assert res_clear.data["deleted_count"] >= 1
