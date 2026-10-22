# tests/test_capability_architecture.py
"""
Unit and Integration Tests for Capability-Based Plugin Architecture and Generalized Intent Routing.
"""

import pytest
from unittest.mock import patch
from brain.semantic_parser import HinglishNLUParser
from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager


@pytest.fixture
def jarvis_core(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_capabilities.db")
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


def test_lock_system_variations_intent_parsing():
    """Verify all Hinglish and English lock system variations map to LOCK_SYSTEM."""
    variations = [
        "system lock",
        "PC lock karo",
        "computer lock kar do",
        "Jarvis laptop lock",
        "lock my computer",
        "screen lock kar do",
        "lock pc",
        "lock screen",
        "screen lock"
    ]
    for phrase in variations:
        act = HinglishNLUParser.parse(phrase)
        assert act is not None, f"Failed to parse '{phrase}'"
        assert act.intent == "LOCK_SYSTEM", f"Wrong intent for '{phrase}': {act.intent}"
        assert act.service == "system"
        assert act.action == "lock_pc"


def test_audio_capabilities_intent_parsing():
    """Verify audio volume and mute intent parsing."""
    act_vol = HinglishNLUParser.parse("volume 50 karo")
    assert act_vol is not None
    assert act_vol.service == "audio"
    assert act_vol.action == "set_volume"
    assert act_vol.parameters.get("level") == 50

    act_up = HinglishNLUParser.parse("awaz badhao")
    assert act_up is not None
    assert act_up.service == "audio"
    assert act_up.action == "volume_up"

    act_down = HinglishNLUParser.parse("volume kam karo")
    assert act_down is not None
    assert act_down.service == "audio"
    assert act_down.action == "volume_down"

    act_mute = HinglishNLUParser.parse("mute karo")
    assert act_mute is not None
    assert act_mute.service == "audio"
    assert act_mute.action == "mute"

    act_unmute = HinglishNLUParser.parse("unmute karo")
    assert act_unmute is not None
    assert act_unmute.service == "audio"
    assert act_unmute.action == "unmute"


def test_screen_capabilities_intent_parsing():
    """Verify screenshot and recording capability parsing."""
    act_ss = HinglishNLUParser.parse("screenshot lo")
    assert act_ss is not None
    assert act_ss.service == "screen"
    assert act_ss.action == "take_screenshot"

    act_rec_start = HinglishNLUParser.parse("screen record karo")
    assert act_rec_start is not None
    assert act_rec_start.service == "screen"
    assert act_rec_start.action == "start_recording"

    act_rec_stop = HinglishNLUParser.parse("stop recording")
    assert act_rec_stop is not None
    assert act_rec_stop.service == "screen"
    assert act_rec_stop.action == "stop_recording"


def test_unc_network_share_routes_to_windows_explorer():
    action = HinglishNLUParser.parse(r"start \\\10.34.181.82\c$")
    assert action is not None
    assert action.intent == "OPEN_NETWORK_SHARE"
    assert action.service == "windows"
    assert action.action == "open_path"
    assert action.parameters["path"] == r"\\10.34.181.82\c$"

    from plugins.windows.plugin import WindowsPlugin
    plugin = WindowsPlugin()
    with patch("plugins.windows.plugin.subprocess.Popen") as popen:
        result = plugin.execute("open_path", action.parameters)
    assert result.success is True
    popen.assert_called_once_with(["explorer.exe", r"\\10.34.181.82\c$"])


@pytest.mark.parametrize("utterance", ["open chat GPT", "open chart GPT", "launch chatgpt"])
def test_chatgpt_stt_aliases_open_official_site(utterance):
    action = HinglishNLUParser.parse(utterance)
    assert action is not None
    assert action.service == "browser"
    assert action.action == "open_url"
    assert action.parameters == {"url": "https://chatgpt.com"}


def test_end_to_end_lock_and_capabilities_execution(jarvis_core):
    """Verify end-to-end execution of capability commands.

    SAFETY: "system lock" / "close excel" must NEVER touch the real OS here.
    conftest._block_direct_win32_effects (autouse) fakes workstation lock,
    window close/kill, and power actions with realistic success payloads —
    isliye ye test sirf routing + response text verify karta hai.
    """
    # 1. Lock PC
    resp_lock1 = jarvis_core.process_input("system lock")
    assert "lock" in resp_lock1.lower()

    resp_lock2 = jarvis_core.process_input("PC lock karo")
    assert "lock" in resp_lock2.lower()

    resp_lock3 = jarvis_core.process_input("lock my computer")
    assert "lock" in resp_lock3.lower()

    # 2. Audio control
    resp_vol = jarvis_core.process_input("volume 70 karo")
    assert "70" in resp_vol

    resp_mute = jarvis_core.process_input("mute karo")
    assert "mute" in resp_mute.lower()

    # 3. Screenshot
    resp_ss = jarvis_core.process_input("screenshot lo")
    assert "screenshot" in resp_ss.lower()

    # 4. App close
    resp_close = jarvis_core.process_input("close excel")
    assert "band kar diya" in resp_close.lower() or "excel" in resp_close.lower()
