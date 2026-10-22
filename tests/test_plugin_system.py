# tests/test_plugin_system.py
"""Automated unit and verification tests for upgraded System plugin."""

import os
import pytest
from plugins.system.plugin import SystemPlugin


@pytest.fixture
def sys_plugin():
    return SystemPlugin()


def test_system_manifest_and_health(sys_plugin):
    manifest = sys_plugin.get_manifest()
    assert manifest.name == "system"
    assert len(manifest.actions) == 19

    health = sys_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 19


def test_get_time_and_info(sys_plugin):
    res_time = sys_plugin.execute("get_time")
    assert res_time.success is True
    assert "time" in res_time.data
    assert "date" in res_time.data

    res_info = sys_plugin.execute("get_system_info")
    assert res_info.success is True
    assert "cpu_percent" in res_info.data

    # Verify state hook
    v = sys_plugin.verify_state("get_system_info", {}, res_info.data)
    assert v is not None
    assert v.verified is True


def test_disk_and_uptime(sys_plugin):
    res_disk = sys_plugin.execute("get_disk_space")
    assert res_disk.success is True
    assert res_disk.data["count"] >= 1
    assert "total_gb" in res_disk.data["partitions"][0]

    res_up = sys_plugin.execute("get_system_uptime")
    assert res_up.success is True
    assert res_up.data["uptime_seconds"] > 0
    assert "boot_time" in res_up.data


def test_cpu_and_network(sys_plugin):
    res_cpu = sys_plugin.execute("get_cpu_per_core_usage")
    assert res_cpu.success is True
    assert res_cpu.data["core_count"] >= 1
    assert len(res_cpu.data["per_core_percent"]) >= 1

    res_net = sys_plugin.execute("get_active_network_interfaces")
    assert res_net.success is True
    assert res_net.data["count"] >= 1


def test_env_and_health_report(sys_plugin):
    res_env = sys_plugin.execute("get_os_environment_variable", {"variable_name": "PATH"})
    assert res_env.success is True
    assert len(res_env.data["value"]) > 0

    res_rep = sys_plugin.execute("get_system_health_report")
    assert res_rep.success is True
    assert "report" in res_rep.data
    assert "cpu_percent" in res_rep.data["report"]
    assert "ram_percent" in res_rep.data["report"]

    # Verify state hook
    v = sys_plugin.verify_state("get_system_health_report", {}, res_rep.data)
    assert v is not None
    assert v.verified is True
