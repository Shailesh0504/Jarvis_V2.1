# tests/test_screen_inspection.py
"""
Unit and Integration Tests for Human-Like Real-Time Screen Inspection in Jarvis V2.
Validates:
- "screen par kya open hai", "screen par kya chal raha hai", "laptop screen par kya hai", "what is on screen"
- Accurate discovery of foreground active application and background running windows.
- Natural human-like spoken response synthesis.
- Non-regression: specific app status checks ("kya YouTube open hai", "is Notepad running") remain unaffected.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager
from plugins.windows.window_manager import WindowInfo


@pytest.fixture
def app_instance(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_screen_app.db")
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
        response_generator=resp_gen
    )
    return core


def test_screen_inspection_with_foreground_window(app_instance):
    """Verifies screen inspection when a foreground window and other apps are open."""
    fake_fg = WindowInfo(hwnd=101, title="Google Search - Brave", process_name="brave.exe", pid=1234)
    fake_all = [
        fake_fg,
        WindowInfo(hwnd=102, title="Jarvis_V2 - Visual Studio Code", process_name="Code.exe", pid=2345),
        WindowInfo(hwnd=103, title="Untitled - Notepad", process_name="notepad.exe", pid=3456),
    ]

    with patch("plugins.windows.window_manager.WindowManager.get_foreground_window", return_value=fake_fg), \
         patch("plugins.windows.window_manager.WindowManager.list_all_windows", return_value=fake_all):

        resp = app_instance.process_input("screen par kya open hai")
        assert "foreground mein Brave open hai" in resp or "Brave" in resp
        assert "Google Search - Brave" in resp or "Google Search" in resp


def test_screen_inspection_speech_variations(app_instance):
    """Verifies multiple natural Hinglish and English phrasing for screen inspection."""
    fake_fg = WindowInfo(hwnd=101, title="WhatsApp", process_name="WhatsApp.exe", pid=1234)
    fake_all = [fake_fg]

    with patch("plugins.windows.window_manager.WindowManager.get_foreground_window", return_value=fake_fg), \
         patch("plugins.windows.window_manager.WindowManager.list_all_windows", return_value=fake_all):

        # 1. "screen par kya chal raha hai"
        resp1 = app_instance.process_input("screen par kya chal raha hai")
        assert "Whatsapp" in resp1 or "WhatsApp" in resp1

        # 2. "laptop screen par kya hai"
        resp2 = app_instance.process_input("laptop screen par kya hai")
        assert "Whatsapp" in resp2 or "WhatsApp" in resp2

        # 3. "what is open on my screen"
        resp3 = app_instance.process_input("what is open on my screen")
        assert "Whatsapp" in resp3 or "WhatsApp" in resp3


def test_screen_inspection_clean_desktop(app_instance):
    """Verifies response when no user application windows are open."""
    with patch("plugins.windows.window_manager.WindowManager.get_foreground_window", return_value=None), \
         patch("plugins.windows.window_manager.WindowManager.list_all_windows", return_value=[]), \
         patch("plugins.windows.window_manager.WindowManager.is_process_running", return_value=(False, [])):

        resp = app_instance.process_input("screen par kya open hai")
        assert "koi active application" in resp or "desktop clean hai" in resp


def test_individual_app_status_non_regression(app_instance):
    """Verifies that specific app queries like 'kya YouTube open hai' still route to app status check."""
    with patch("plugins.windows.window_manager.WindowManager.is_process_running", return_value=(False, [])), \
         patch("plugins.windows.window_manager.WindowManager.find_windows_for_app", return_value=[]), \
         patch("core.target_engine.TargetResolver.resolve", return_value=[]):

        resp = app_instance.process_input("kya YouTube open hai")
        assert "Youtube" in resp or "YouTube" in resp
        assert "abhi open nahi hai" in resp
