# tests/test_plugin_apps.py
"""Automated unit and verification tests for upgraded Apps plugin."""

import os
from typing import Optional, Tuple, get_type_hints
import pytest
from plugins.apps.plugin import AppsPlugin


@pytest.fixture
def apps_plugin():
    return AppsPlugin()


def test_apps_manifest_and_health(apps_plugin):
    manifest = apps_plugin.get_manifest()
    assert manifest.name == "apps"
    assert len(manifest.actions) == 13

    health = apps_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 13


def test_list_and_search_installed_apps(apps_plugin):
    res_list = apps_plugin.execute("list_installed_apps", {"limit": 20})
    assert res_list.success is True
    assert res_list.data["count"] > 0
    assert len(res_list.data["apps"]) > 0

    # Search
    first_app = res_list.data["apps"][0]
    query = first_app.split()[0]
    res_search = apps_plugin.execute("search_installed_apps", {"query": query})
    assert res_search.success is True
    assert res_search.data["count"] >= 1


def test_check_app_status_and_resources(apps_plugin):
    # Python should currently be running because pytest is executing
    res_status = apps_plugin.execute("check_app_status", {"app_name": "python"})
    assert res_status.success is True
    assert res_status.data["running"] is True
    assert len(res_status.data["pids"]) >= 1

    # Resource usage
    res_res = apps_plugin.execute("get_app_resource_usage", {"app_name": "python"})
    assert res_res.success is True
    assert res_res.data["memory_mb"] > 0
    assert res_res.data["process_count"] >= 1


def test_list_running_and_top_resources(apps_plugin):
    res_running = apps_plugin.execute("list_running_apps", {"limit": 50})
    assert res_running.success is True
    assert res_running.data["count"] >= 1
    assert "memory_mb" in res_running.data["running_apps"][0]

    # Top resources
    res_top = apps_plugin.execute("get_top_resource_apps", {"limit": 5})
    assert res_top.success is True
    assert len(res_top.data["top_apps"]) <= 5
    assert res_top.data["top_apps"][0]["memory_mb"] >= 0


def test_find_executable_and_startup(apps_plugin):
    # Find cmd or python
    res_find = apps_plugin.execute("find_app_executable_path", {"app_name": "cmd"})
    assert res_find.success is True
    assert os.path.exists(res_find.data["path"])

    # List startup apps
    res_startup = apps_plugin.execute("list_startup_apps")
    assert res_startup.success is True
    assert isinstance(res_startup.data["startup_apps"], list)


def test_close_and_verify_state(apps_plugin):
    # Testing close on a dummy process name
    res_close = apps_plugin.execute("close_app", {"app_name": "non_existent_dummy_app_xyz_123"})
    assert res_close.success is True
    assert res_close.data["closed_processes_count"] == 0

    # Test verify_state hook
    v = apps_plugin.verify_state("close_app", {"app_name": "non_existent_dummy_app_xyz_123"}, {})
    assert v is not None
    assert v.verified is True


def test_safe_query_value_type_annotations_and_behavior():
    hints = get_type_hints(AppsPlugin._safe_query_value)
    assert hints.get("return") == Tuple[Optional[str], int]
    val, reg_type = AppsPlugin._safe_query_value(None, "dummy_key")
    assert val is None
    assert reg_type == 0

