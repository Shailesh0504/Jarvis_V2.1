# tests/test_audited_logic_fixes.py
"""
Comprehensive test suite verifying all audited logical fixes:
1. UniversalTargetEngine alias and LocationPlugin import compatibility.
2. ExcelPlugin create_sheet & write_sheet functionality.
3. BluetoothPlugin status, list_devices, & toggle_bluetooth actions.
4. FilesPlugin get_file_info, read_file, & write_file actions.
5. PDFPlugin summarize_pdf & read_pdf actions.
6. SystemPlugin get_battery action declaration.
7. VLCPlugin stop_playback action declaration.
8. AudioPlugin resilient volume string parsing ("max", "mute", "half", etc.).
9. DialogManager workflow lock re-arming on multiple matches and suggestion staging.
10. JarvisCore face auth enable/disable configuration persistence.
"""

import os
from unittest.mock import MagicMock, patch
import pytest

from core.target_engine import UniversalTargetEngine, UniversalTargetDiscoveryEngine
from plugins.location.plugin import LocationPlugin
from plugins.excel.plugin import ExcelPlugin
from plugins.bluetooth.plugin import BluetoothPlugin
from plugins.files.plugin import FilesPlugin
from plugins.pdf.plugin import PDFPlugin
from plugins.system.plugin import SystemPlugin
from plugins.vlc.plugin import VLCPlugin
from plugins.audio.plugin import AudioPlugin, _parse_volume_level, _parse_step
from core.dialog_manager import DialogManager, WorkflowLock, SuggestionContext
from core.app import JarvisCore


# 1. UniversalTargetEngine alias & LocationPlugin
def test_universal_target_engine_alias():
    assert UniversalTargetEngine is UniversalTargetDiscoveryEngine
    engine = UniversalTargetEngine()
    assert engine is not None


def test_location_plugin_initialization_and_manifest():
    plugin = LocationPlugin()
    assert plugin is not None
    manifest = plugin.get_manifest()
    assert manifest.name == "location"


# 2. ExcelPlugin create_sheet & write_sheet
def test_excel_plugin_manifest_and_write_sheet(tmp_path):
    plugin = ExcelPlugin()
    manifest = plugin.get_manifest()
    actions = [a.name for a in manifest.actions]
    assert "create_sheet" in actions
    assert "write_sheet" in actions

    test_file = str(tmp_path / "test.csv")
    create_res = plugin.execute("create_sheet", {"path": test_file, "sheet_name": "Data"})
    assert create_res.success is True
    assert os.path.exists(test_file)

    write_res = plugin.execute("write_sheet", {
        "path": test_file,
        "sheet_name": "Data",
        "data": [["Header1", "Header2"], ["Val1", "Val2"]]
    })
    assert write_res.success is True
    with open(test_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Header1,Header2" in content
    assert "Val1,Val2" in content


# 3. BluetoothPlugin status, list_devices, toggle_bluetooth
def test_bluetooth_plugin_manifest_and_execution():
    plugin = BluetoothPlugin()
    manifest = plugin.get_manifest()
    actions = [a.name for a in manifest.actions]
    assert "status" in actions
    assert "list_devices" in actions
    assert "toggle_bluetooth" in actions

    # status action (no parameters required)
    status_res = plugin.execute("status")
    assert status_res.success is True

    # list_devices action (mocked powershell subprocess)
    with patch("plugins.bluetooth.plugin.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='[{"FriendlyName": "Mock BT Device", "Status": "OK"}]', stderr="")
        list_res = plugin.execute("list_devices")
        assert list_res.success is True
        assert "Mock BT Device" in str(list_res.data)

    # toggle_bluetooth action
    toggle_res = plugin.execute("toggle_bluetooth", {"enable": True})
    assert toggle_res.success is True


# 4. FilesPlugin get_file_info, read_file, write_file
def test_files_plugin_manifest_and_read_write(tmp_path):
    plugin = FilesPlugin()
    manifest = plugin.get_manifest()
    actions = [a.name for a in manifest.actions]
    assert "get_file_info" in actions
    assert "read_file" in actions
    assert "write_file" in actions

    test_file = str(tmp_path / "note.txt")
    write_res = plugin.execute("write_file", {"path": test_file, "content": "Hello Jarvis Files"})
    assert write_res.success is True
    assert os.path.exists(test_file)

    read_res = plugin.execute("read_file", {"path": test_file})
    assert read_res.success is True
    assert read_res.data["content"] == "Hello Jarvis Files"

    info_res = plugin.execute("get_file_info", {"path": test_file})
    assert info_res.success is True
    assert "size_bytes" in info_res.data or "size_kb" in info_res.data


# 5. PDFPlugin summarize_pdf & read_pdf
def test_pdf_plugin_manifest_and_actions():
    plugin = PDFPlugin()
    manifest = plugin.get_manifest()
    actions = [a.name for a in manifest.actions]
    assert "summarize_pdf" in actions
    assert "read_pdf" in actions

    # Missing path returns graceful failure
    empty_read = plugin.execute("read_pdf", {"path": ""})
    assert empty_read.success is False

    empty_sum = plugin.execute("summarize_pdf", {"path": ""})
    assert empty_sum.success is False

    # Path provided returns success
    read_res = plugin.execute("read_pdf", {"path": "sample.pdf"})
    assert read_res.success is True

    sum_res = plugin.execute("summarize_pdf", {"path": "sample.pdf"})
    assert sum_res.success is True


# 6. SystemPlugin get_battery
def test_system_plugin_get_battery():
    plugin = SystemPlugin()
    manifest = plugin.get_manifest()
    actions = [a.name for a in manifest.actions]
    assert "get_battery" in actions

    res = plugin.execute("get_battery")
    assert res.success is True
    assert "battery_percent" in res.data or "message" in res.data


# 7. VLCPlugin stop_playback
def test_vlc_plugin_stop_playback():
    plugin = VLCPlugin()
    manifest = plugin.get_manifest()
    actions = [a.name for a in manifest.actions]
    assert "stop_playback" in actions

    res = plugin.execute("stop_playback")
    assert res.success is True


# 8. AudioPlugin resilient volume parsing
def test_audio_plugin_volume_parsing():
    plugin = AudioPlugin()

    # Direct helper tests
    assert _parse_volume_level(75) == 75
    assert _parse_volume_level("80%") == 80
    assert _parse_volume_level("max") == 100
    assert _parse_volume_level("full") == 100
    assert _parse_volume_level("mute") == 0
    assert _parse_volume_level("silent") == 0
    assert _parse_volume_level("half") == 50
    assert _parse_volume_level("medium") == 50
    assert _parse_volume_level("low") == 20
    assert _parse_volume_level("high") == 80
    assert _parse_volume_level("invalid_string") == 50

    # Step parsing
    assert _parse_step(10) == 10
    assert _parse_step("15%") == 15
    assert _parse_step("invalid") == 10

    # Execution with named words without throwing ValueError
    res = plugin.execute("set_volume", {"level": "max"})
    assert res.success is True
    assert res.data["level"] == 100

    res_mute = plugin.execute("set_volume", {"level": "mute"})
    assert res_mute.success is True
    assert res_mute.data["level"] == 0

    res_up = plugin.execute("volume_up", {"step": "10%"})
    assert res_up.success is True
    assert res_up.data["level"] == 10


# 9. DialogManager workflow lock re-arming on multiple matches and suggestion staging
def test_dialog_manager_multiple_matches_lock_retention():
    dm = DialogManager()
    core = MagicMock()

    lock = WorkflowLock(
        workflow_type="EXCEL_OPEN",
        required_slots=["file_target"],
        filled_slots={"file_target": "report"},
    )

    with patch.object(dm, "resolve_file") as mock_resolve:
        mock_resolve.return_value = {
            "exact_matches": [
                {"name": "sales_report.xlsx", "path": "/path/sales_report.xlsx"},
                {"name": "annual_report.xlsx", "path": "/path/annual_report.xlsx"}
            ],
            "close_suggestions": [],
            "all_discovered": []
        }

        reply = dm._execute_completed_workflow(lock, core)
        assert "matches mile" in reply
        # DialogManager should re-arm active_lock instead of dropping to normal flow
        assert dm.has_active_lock() is True
        assert dm.active_lock.workflow_type == "EXCEL_OPEN"


def test_dialog_manager_close_suggestion_staging():
    dm = DialogManager()
    core = MagicMock()

    lock = WorkflowLock(
        workflow_type="EXCEL_OPEN",
        required_slots=["file_target"],
        filled_slots={"file_target": "reprt"},
    )

    with patch.object(dm, "resolve_file") as mock_resolve:
        mock_resolve.return_value = {
            "exact_matches": [],
            "close_suggestions": [
                {"name": "report.xlsx", "path": "/path/report.xlsx"}
            ],
            "all_discovered": []
        }

        reply = dm._execute_completed_workflow(lock, core)
        assert "report.xlsx" in reply
        # Pending suggestion should be staged
        assert dm.has_pending_suggestion() is True
        assert dm.pending_suggestion.suggested_candidate["name"] == "report.xlsx"


# 10. JarvisCore face auth enable/disable configuration persistence
def test_jarvis_core_auth_toggle_persistence():
    core = JarvisCore()
    core.initialize_subsystems()

    core.enable_auth()
    assert core.config["security"]["face_auth"]["enabled"] is True

    core.disable_auth()
    assert core.config["security"]["face_auth"]["enabled"] is False
