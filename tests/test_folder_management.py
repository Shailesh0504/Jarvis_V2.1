# tests/test_folder_management.py
# tests/test_folder_management.py
"""
Unit and integration tests for daily-use folder management (open and close) across:
- Path resolution for all daily-use folders (startup, downloads, documents, pictures, videos, recycle_bin, temp, etc.)
- Win32 & COM folder window discovery and safe non-destructive closing in WindowManager
- FilesystemOperations open_folder and close_folder execution
- FilesPlugin OPEN_FOLDER and CLOSE_FOLDER action execution
- HinglishNLUParser folder open/close semantic intent parsing
- DesktopTaskPlanner and DesktopTaskExecutor workflow orchestration
- End-to-end routing in JarvisApp
"""

import os
from unittest.mock import MagicMock, patch
import pytest

from brain.semantic_parser import HinglishNLUParser, SemanticAction
from core.app import JarvisCore
from core.desktop_task.executor import DesktopTaskExecutor
from core.desktop_task.planner import DesktopTaskPlanner
from plugins.files.operations import ActionResult, FilesystemOperations
from plugins.files.plugin import FilesPlugin
from plugins.windows.window_manager import WindowInfo, WindowManager


@pytest.fixture
def app_instance(tmp_path):
    from brain.llm import MockLLMProvider
    from brain.response import ResponseGenerator
    from memory.memory_manager import MemoryManager
    from plugins.manager import PluginManager

    core = JarvisCore()
    db_path = str(tmp_path / "test_folder_app.db")
    mem = MemoryManager(db_path=db_path)
    llm = MockLLMProvider()
    resp_gen = ResponseGenerator(llm_provider=llm)
    plugins = PluginManager(plugin_dir="plugins")
    plugins.discover_and_load()

    core.initialize_subsystems(
        memory_manager=mem,
        learning_manager=None,
        brain=resp_gen,
        classifier=None,
        plugin_manager=plugins,
        response_generator=resp_gen,
    )
    return core


class TestFolderResolution:
    """Validates path resolution for all Windows daily-use folders."""

    def test_daily_folders_resolution(self):
        ops = FilesystemOperations()

        # Startup
        startup_path = ops.get_special_path("startup")
        assert startup_path and ("startup" in startup_path.lower() or "start menu" in startup_path.lower())
        assert ops.get_special_path("startup folder") == startup_path

        # Downloads
        downloads_path = ops.get_special_path("downloads")
        assert downloads_path and "Downloads" in downloads_path
        assert ops.get_special_path("downloads folder") == downloads_path

        # Documents
        docs_path = ops.get_special_path("documents")
        assert docs_path and "Documents" in docs_path
        assert ops.get_special_path("docs") == docs_path

        # Desktop
        desktop_path = ops.get_special_path("desktop")
        assert desktop_path and "Desktop" in desktop_path

        # Pictures / Photos
        pics_path = ops.get_special_path("pictures")
        assert pics_path and "Pictures" in pics_path
        assert ops.get_special_path("photos") == pics_path

        # Videos / Movies
        vids_path = ops.get_special_path("videos")
        assert vids_path and "Videos" in vids_path
        assert ops.get_special_path("movies") == vids_path

        # Music / Songs
        music_path = ops.get_special_path("music")
        assert music_path and "Music" in music_path
        assert ops.get_special_path("songs") == music_path

        # Recycle Bin
        recycle_path = ops.get_special_path("recycle bin")
        assert recycle_path == "shell:RecycleBinFolder"
        assert ops.get_special_path("trash") == "shell:RecycleBinFolder"

        # Temp
        temp_path = ops.get_special_path("temp")
        assert temp_path and os.path.exists(temp_path)

        # AppData
        appdata_path = ops.get_special_path("appdata")
        assert appdata_path and "AppData" in appdata_path

        # Drives
        assert ops.get_special_path("c drive") == "C:\\"
        assert ops.get_special_path("d drive") == "D:\\"

        # Home
        home_path = ops.get_special_path("home")
        assert home_path and os.path.exists(home_path)

    def test_startup_uses_windows_known_folder_when_physical_directory_is_absent(self):
        """Startup must not degrade to a relative path on a fresh profile."""
        ops = FilesystemOperations()

        with patch("plugins.files.operations.os.path.exists", return_value=False):
            resolved = ops.resolve_path("startup folder")

        assert resolved.success is True
        assert resolved.verified is True
        assert resolved.target == "shell:startup"
        assert resolved.data["is_dir"] is True


class TestFolderOperations:
    """Validates open_folder and close_folder operations."""

    @patch("plugins.files.operations.os.startfile")
    def test_open_folder(self, mock_startfile):
        ops = FilesystemOperations()

        # Open downloads
        res = ops.open_folder("downloads")
        assert res.success is True
        assert res.action == "OPEN"
        assert "open kar diya hai" in res.data.get("message", "")

        # Open recycle bin
        res_rb = ops.open_folder("recycle bin")
        assert res_rb.success is True
        assert "Recycle Bin" in res_rb.data.get("message", "")

    @patch("plugins.files.operations.subprocess.Popen")
    def test_open_startup_folder_uses_windows_known_folder(self, mock_popen):
        ops = FilesystemOperations()

        res = ops.open_folder("startup")

        assert res.success is True
        assert res.verified is True
        assert res.target == "shell:startup"
        assert "Startup" in res.data["message"]
        mock_popen.assert_called_once_with(["explorer.exe", "shell:startup"])

    @patch.object(WindowManager, "close_folder_window")
    @patch.object(WindowManager, "close_all_folder_windows")
    def test_close_folder(self, mock_close_all, mock_close_specific):
        mock_close_specific.return_value = True
        mock_close_all.return_value = 3

        ops = FilesystemOperations()

        # Close specific folder
        res = ops.close_folder("startup")
        assert res.success is True
        assert res.action == "CLOSE_FOLDER"
        assert "band kar di hai" in res.data.get("message", "")
        mock_close_specific.assert_called_once_with("startup")

        # Close all folders
        res_all = ops.close_folder(close_all=True)
        assert res_all.success is True
        assert res_all.data.get("closed_all") is True
        assert "3 open folder windows band kar diye hain" in res_all.data.get("message", "")
        mock_close_all.assert_called_once()

    def test_files_plugin_execute(self):
        plugin = FilesPlugin()

        with patch.object(plugin.ops, "open_folder") as mock_open:
            mock_open.return_value = ActionResult(
                success=True, action="OPEN", target="C:\\Downloads",
                data={"message": "'Downloads' folder open kar diya hai, Boss."}
            )
            res = plugin.execute("OPEN_FOLDER", {"target": "downloads"})
            assert res.success is True
            assert "Downloads" in res.data.get("message", "")

        with patch.object(plugin.ops, "close_folder") as mock_close:
            mock_close.return_value = ActionResult(
                success=True, action="CLOSE_FOLDER", target="downloads",
                data={"message": "'Downloads' folder window band kar di hai, Boss."}
            )
            res = plugin.execute("CLOSE_FOLDER", {"target": "downloads"})
            assert res.success is True
            assert "band kar di hai" in res.data.get("message", "")


class TestWindowManagerFolderClosing:
    """Validates WindowManager safe folder window discovery and closing without killing explorer.exe."""

    def test_close_folder_window_com_and_win32(self):
        wm = WindowManager()

        # Mock Shell COM windows
        mock_com_win = MagicMock()
        mock_com_win.LocationName = "Startup"
        mock_com_win.LocationURL = "file:///C:/Users/Admin/AppData/Roaming/Startup"
        mock_com_win.HWND = 12345

        mock_shell_wins = MagicMock()
        mock_shell_wins.Count = 1
        mock_shell_wins.Item.return_value = mock_com_win

        mock_shell = MagicMock()
        mock_shell.Windows.return_value = mock_shell_wins

        with patch("win32com.client.Dispatch", return_value=mock_shell):
            found = wm.find_folder_windows("startup")
            assert len(found) >= 1
            assert found[0]["title"] == "Startup"

            closed = wm.close_folder_window("startup")
            assert closed is True
            mock_com_win.Quit.assert_called_once()

    def test_execute_operation_folder_close_safeguard(self):
        wm = WindowManager()
        with patch.object(wm, "close_folder_window", return_value=True) as mock_close:
            res = wm.execute_operation("close", "downloads folder")
            assert res["success"] is True
            assert "band kar di hai" in res["message"]
            mock_close.assert_called_once_with("downloads folder")


class TestFolderSemanticNLU:
    """Validates multilingual NLU parsing for opening and closing daily-use folders."""

    def test_parse_open_folder_english(self):
        for q in ["open startup folder", "open startup", "open downloads folder", "open documents", "open recycle bin"]:
            act = HinglishNLUParser.parse(q)
            assert act is not None
            assert act.intent == "FOLDER_OPEN"
            assert act.action == "open_folder"

    def test_parse_open_folder_hinglish_hindi(self):
        for q in ["startup folder kholo", "downloads kholo", "recycle bin open karo", "c drive kholo", "photos folder open kar do"]:
            act = HinglishNLUParser.parse(q)
            assert act is not None
            assert act.intent == "FOLDER_OPEN"
            assert act.action == "open_folder"

    def test_parse_close_folder_english(self):
        for q in ["close startup folder", "close downloads", "close recycle bin", "close all folders"]:
            act = HinglishNLUParser.parse(q)
            assert act is not None
            assert act.intent == "FOLDER_CLOSE"
            assert act.action == "close_folder"

    def test_parse_close_folder_hinglish_hindi(self):
        for q in ["startup folder band karo", "downloads band karo", "saare folder band karo", "sab folder band kar do"]:
            act = HinglishNLUParser.parse(q)
            assert act is not None
            assert act.intent == "FOLDER_CLOSE"
            assert act.action == "close_folder"


class TestDesktopTaskWorkflowForFolders:
    """Validates DesktopTaskPlanner and DesktopTaskExecutor for folder workflows."""

    def test_planner_open_and_close_folder(self):
        planner = DesktopTaskPlanner()

        # Open startup folder
        plan_open = planner.parse("open startup folder")
        assert plan_open is not None
        assert plan_open.intent_type == "OPEN"
        assert len(plan_open.steps) == 2
        assert plan_open.steps[0].action == "RESOLVE_PATH"
        assert plan_open.steps[0].parameters["target"] == "startup"
        assert plan_open.steps[1].action == "OPEN"

        # Close startup folder
        plan_close = planner.parse("close startup folder")
        assert plan_close is not None
        assert plan_close.intent_type == "CLOSE_FOLDER"
        assert len(plan_close.steps) == 1
        assert plan_close.steps[0].action == "CLOSE_FOLDER"
        assert plan_close.steps[0].parameters["target"] == "startup"

        # Close all folders
        plan_close_all = planner.parse("saare folder band karo")
        assert plan_close_all is not None
        assert plan_close_all.intent_type == "CLOSE_FOLDER"
        assert plan_close_all.steps[0].parameters["close_all"] is True

    def test_executor_close_folder_synthesis(self):
        planner = DesktopTaskPlanner()
        executor = DesktopTaskExecutor()

        plan = planner.parse("close startup folder")
        with patch.object(executor, "_dispatch_action") as mock_dispatch:
            mock_dispatch.return_value = ActionResult(
                success=True, action="CLOSE_FOLDER", target="startup", verified=True,
                data={"message": "'Startup' folder window band kar di hai, Boss."}
            )
            report = executor.execute(plan)
            assert report.success is True
            assert "band kar di hai" in report.response_message


class TestJarvisAppFolderRouting:
    """Validates end-to-end folder open and close queries through JarvisApp / JarvisCore."""

    def test_app_open_and_close_folder_turn(self, app_instance):
        with patch("plugins.files.operations.os.startfile"), \
             patch("plugins.files.operations.subprocess.Popen"), \
             patch.object(WindowManager, "find_folder_windows", return_value=[{"title": "Startup", "hwnd": 1234}]):
            resp_open = app_instance.process_input("open startup folder")
            assert "open kar diya hai" in resp_open

        with patch.object(WindowManager, "close_folder_window", return_value=True):
            resp_close = app_instance.process_input("startup folder band karo")
            assert "band kar di hai" in resp_close
