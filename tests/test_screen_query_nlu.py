# tests/test_screen_query_nlu.py
"""
Unit and Integration Tests for Screen Visibility Capability and Open Window Queries in Jarvis V2.
Validates:
1. "kya tum meri screen dekh saktey ho" (Screen visibility capability inquiry) -> SCREEN_INSPECTION, not LISTENING_CHECK.
2. "main laptop ki screen pe konsi windows hai puchh raha hun" (Window listing inquiry) -> SCREEN_INSPECTION, lists active windows.
3. "are you able to see my screen" & "can you see my screen" (English capability inquiry) -> SCREEN_INSPECTION, English visibility response.
4. Audio check non-regression: "meri awaaz sun rahe ho", "kya tum meri baat sun rahe ho" -> LISTENING_CHECK preserved.
"""

# tests/test_screen_query_nlu.py
from unittest.mock import patch
import pytest

from brain.conversation.classifier import ConversationClassifier
from brain.conversation.intents import ConversationalIntent
from brain.llm import MockLLMProvider
from brain.response import ResponseGenerator
from brain.semantic_parser import HinglishNLUParser
from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from plugins.manager import PluginManager
from plugins.windows.window_manager import WindowInfo


@pytest.fixture
def app_instance(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_screen_query_app.db")
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


def test_screen_capability_query_nlu():
    """Validates that 'kya tum meri screen dekh saktey ho' parses to SCREEN_INSPECTION and avoids LISTENING_CHECK."""
    text = "kya tum meri screen dekh saktey ho"
    action = HinglishNLUParser.parse(text)
    assert action is not None
    assert action.intent == "SCREEN_INSPECTION"
    assert action.action == "inspect_screen"
    assert action.parameters.get("capability_query") is True

    # Ensure classifier does not mistake this for audio hearing check
    classification = ConversationClassifier.classify_detailed(text)
    assert classification.intent != ConversationalIntent.LISTENING_CHECK
    assert classification.intent == ConversationalIntent.COMMAND


def test_screen_capability_query_english_nlu():
    """Validates that English capability questions parse correctly with language='en'."""
    for utterance in ["are you able to see my screen", "can you see my screen", "can you look at my screen"]:
        action = HinglishNLUParser.parse(utterance)
        assert action is not None, f"Failed to parse '{utterance}'"
        assert action.intent == "SCREEN_INSPECTION"
        assert action.parameters.get("capability_query") is True
        assert action.parameters.get("language") == "en"

        classification = ConversationClassifier.classify_detailed(utterance)
        assert classification.intent != ConversationalIntent.LISTENING_CHECK


def test_open_windows_inquiry_nlu():
    """Validates that window listing queries parse with list_windows=True."""
    queries = [
        "main laptop ki screen pe konsi windows hai puchh raha hun",
        "laptop ki screen pe konsi windows hai",
        "screen pe konsi windows open hai",
        "what windows are open on my screen",
        "which windows are open",
    ]
    for q in queries:
        action = HinglishNLUParser.parse(q)
        assert action is not None, f"Failed to parse '{q}'"
        assert action.intent == "SCREEN_INSPECTION"
        assert action.parameters.get("list_windows") is True


def test_screen_capability_execution(app_instance):
    """Verifies end-to-end execution of 'kya tum meri screen dekh saktey ho'."""
    fake_fg = WindowInfo(hwnd=101, title="WhatsApp Web - Brave", process_name="brave.exe", pid=1234)
    fake_all = [
        fake_fg,
        WindowInfo(hwnd=102, title="VS Code", process_name="Code.exe", pid=2345),
    ]

    with patch("plugins.windows.window_manager.WindowManager.get_foreground_window", return_value=fake_fg), \
         patch("plugins.windows.window_manager.WindowManager.list_all_windows", return_value=fake_all):

        resp = app_instance.process_input("kya tum meri screen dekh saktey ho")
        # Must confirm capability and mention screen / apps, NOT hearing / audio
        assert "awaaz" not in resp.lower()
        assert "Ji haan" in resp or "screen dekh" in resp
        assert "Brave" in resp


def test_open_windows_execution(app_instance):
    """Verifies end-to-end execution of 'main laptop ki screen pe konsi windows hai puchh raha hun'."""
    fake_fg = WindowInfo(hwnd=101, title="Excel - Sales Report", process_name="excel.exe", pid=1234)
    fake_all = [
        fake_fg,
        WindowInfo(hwnd=102, title="Brave Browser", process_name="brave.exe", pid=2345),
        WindowInfo(hwnd=103, title="VLC media player", process_name="vlc.exe", pid=3456),
    ]

    with patch("plugins.windows.window_manager.WindowManager.get_foreground_window", return_value=fake_fg), \
         patch("plugins.windows.window_manager.WindowManager.list_all_windows", return_value=fake_all):

        resp = app_instance.process_input("main laptop ki screen pe konsi windows hai puchh raha hun")
        # Must list windows rather than generic fallback
        assert "aage kya karna hai" not in resp
        assert "Excel" in resp or "Brave" in resp or "Vlc" in resp


def test_english_screen_capability_execution(app_instance):
    """Verifies end-to-end execution of 'are you able to see my screen'."""
    fake_fg = WindowInfo(hwnd=101, title="Excel", process_name="excel.exe", pid=1234)
    fake_all = [fake_fg]

    with patch("plugins.windows.window_manager.WindowManager.get_foreground_window", return_value=fake_fg), \
         patch("plugins.windows.window_manager.WindowManager.list_all_windows", return_value=fake_all):

        resp = app_instance.process_input("are you able to see my screen")
        assert "aage kya karna hai" not in resp
        assert "Yes" in resp or "screen" in resp.lower()


def test_hearing_check_non_regression():
    """Verifies that genuine listening checks are still classified as LISTENING_CHECK."""
    for audio_check in [
        "meri awaaz sun rahe ho",
        "kya tum meri baat sun rahe ho",
        "can you hear me",
        "are you listening",
        "kya meri awaaz aa rahi hai",
    ]:
        res = ConversationClassifier.classify_detailed(audio_check)
        assert res.intent == ConversationalIntent.LISTENING_CHECK, f"Regression for '{audio_check}': got {res.intent}"


def test_open_startup_folder_desktop_task(app_instance):
    """Verifies that 'open startup folder' plans and executes opening the Windows startup directory."""
    from core.desktop_workflow import DesktopWorkflowCoordinator
    dw = DesktopWorkflowCoordinator(plugin_manager=app_instance.plugin_manager)

    with patch("plugins.files.operations.subprocess.Popen") as mock_popen:
        handled, resp, plan = dw.try_handle("open startup folder")
        assert handled is True
        assert "startup" in resp.lower() or "open" in resp.lower()
        called_path = mock_popen.call_args[0][0][1]
        assert "startup" in called_path.lower()
