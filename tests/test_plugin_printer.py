# tests/test_plugin_printer.py
"""Automated unit and verification tests for upgraded Printer plugin."""

import os
import pytest
from plugins.printer.plugin import PrinterPlugin


@pytest.fixture
def printer_plugin():
    return PrinterPlugin()


def test_printer_manifest_and_health(printer_plugin):
    manifest = printer_plugin.get_manifest()
    assert manifest.name == "printer"
    assert len(manifest.actions) == 13

    health = printer_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 13


def test_list_and_default_printer(printer_plugin):
    res_list = printer_plugin.execute("list_printers")
    assert res_list.success is True
    assert res_list.data["count"] > 0
    assert len(res_list.data["printers"]) > 0

    res_def = printer_plugin.execute("get_default_printer")
    assert res_def.success is True
    assert "default_printer" in res_def.data
    assert len(res_def.data["default_printer"]) > 0


def test_printer_properties_and_status(printer_plugin):
    res_def = printer_plugin.execute("get_default_printer")
    def_name = res_def.data["default_printer"]

    res_props = printer_plugin.execute("get_printer_properties", {"printer_name": def_name})
    assert res_props.success is True
    assert "properties" in res_props.data

    res_status = printer_plugin.execute("check_printer_online_status", {"printer_name": def_name})
    assert res_status.success is True
    assert "online" in res_status.data
    assert "status_description" in res_status.data


def test_queue_status(printer_plugin):
    res_queue = printer_plugin.execute("get_printer_queue_status")
    assert res_queue.success is True
    assert "job_count" in res_queue.data
    assert isinstance(res_queue.data["jobs"], list)


def test_set_default_and_verify_state(printer_plugin):
    res_def = printer_plugin.execute("get_default_printer")
    def_name = res_def.data["default_printer"]

    # Re-setting the same default printer
    res_set = printer_plugin.execute("set_default_printer", {"printer_name": def_name})
    assert res_set.success is True

    # Test verify_state hook
    v = printer_plugin.verify_state("set_default_printer", {"printer_name": def_name}, res_set.data)
    assert v is not None
    assert v.verified is True
