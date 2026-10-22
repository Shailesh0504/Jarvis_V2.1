# tests/test_plugin_bluetooth.py
"""Automated unit and verification tests for upgraded Bluetooth plugin."""

import pytest
from plugins.bluetooth.plugin import BluetoothPlugin


def test_bluetooth_manifest_and_health():
    plugin = BluetoothPlugin()
    manifest = plugin.get_manifest()
    assert manifest.name == "bluetooth"
    assert len(manifest.actions) == 13

    health = plugin.get_health_status()
    assert "status" in health
    assert health["actions_count"] == 13


def test_bluetooth_status_and_troubleshooter():
    plugin = BluetoothPlugin()
    res_status = plugin.execute("status", {})
    assert res_status.success is True
    assert "status" in res_status.data

    res_diag = plugin.execute("bluetooth_troubleshooter", {})
    assert res_diag.success is True
    assert "diagnostics" in res_diag.data
    assert "service_status" in res_diag.data["diagnostics"]


def test_bluetooth_device_listings():
    plugin = BluetoothPlugin()
    res_all = plugin.execute("list_devices", {})
    assert res_all.success is True
    assert isinstance(res_all.data["devices"], list)

    res_paired = plugin.execute("list_paired_devices", {})
    assert res_paired.success is True
    assert isinstance(res_paired.data["paired_devices"], list)

    res_audio = plugin.execute("list_connected_audio_devices", {})
    assert res_audio.success is True
    assert isinstance(res_audio.data["audio_devices"], list)


def test_bluetooth_device_not_found():
    plugin = BluetoothPlugin()
    res_bad = plugin.execute("get_device_details", {"device_name": "non_existent_device_xyz_999"})
    assert res_bad.success is False

    res_disc_bad = plugin.execute("disconnect_device", {"device_name": "non_existent_device_xyz_999"})
    assert res_disc_bad.success is False
