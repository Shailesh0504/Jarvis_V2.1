"""
Tests for Jarvis Natural Language Understanding & Context Understanding Upgrade.
Validates:
1. Intent canonicalization across 20+ variations of temp file cleanup.
2. Synonym & paraphrase understanding (clear, clean, delete, remove, saaf, hatao).
3. Hindi/Hinglish modifiers ('bhi', 'ko', 'kar do', 'please', 'bhai') handling and 'ALSO' modifier extraction.
4. Short-term context memory (last_intent, last_action, last_entities).
5. Follow-up repetition and completion ('phir se karo', 'dobara karo', 'temp bhi').
6. Active context priority: Context assists incomplete commands but never overrides explicit targets.
7. End-to-end 4-turn (+repeat) conversational regression flow.
"""

import pytest
from unittest.mock import MagicMock

from brain.semantic_parser import HinglishNLUParser
from core.context import ActiveTargetContext
from core.contextual_resolver import ContextualActionResolver
from core.natural_responses import NaturalResponseSynthesizer
from core.semantic.models import IntentName
from main import create_jarvis
from plugins.base import PluginResult


TEMP_CLEANUP_VARIATIONS = [
    "temp file clear karo",
    "clear temp file",
    "temp files delete kar do",
    "temporary files hata do",
    "temp bhi clean kar do",
    "temp file bhi clear karo",
    "temporary files ko saaf kar do",
    "bhai temp bhi delete kar de please",
    "temp cleanup kar do",
    "temp delete karo",
    "clean temp files",
    "temporary data delete karo",
    "temp folder saaf kar do",
    "temp remove karo",
    "temp erase kar do",
    "temp files hatao",
    "temporary files clear karo",
    "bhai please temp clear kar do",
    "temp files ko clean karo",
    "temp clear kar dena",
]


@pytest.mark.parametrize("phrase", TEMP_CLEANUP_VARIATIONS)
def test_temp_cleanup_variations_canonicalize_to_temp_file_cleanup(phrase):
    """
    Every variation must canonicalize to TEMP_FILE_CLEANUP with high confidence,
    target='temp_files', and action='clean' (or 'clear_temp_files').
    """
    act = HinglishNLUParser.parse(phrase)
    assert act is not None, f"Failed to parse phrase: {phrase}"
    assert act.intent == IntentName.TEMP_FILE_CLEANUP
    assert act.intent == "SYSTEM_MAINTENANCE"  # Equivalence invariant
    assert act.confidence >= 0.85
    assert act.service == "system"
    assert act.action == "clear_temp_files"
    assert act.parameters.get("target") == "temp_files"


def test_modifier_bhi_extracted_as_also():
    """
    Phrases containing 'bhi', 'also', 'too' must extract modifier='ALSO'.
    Phrases without it must have modifier=None.
    """
    act_with_bhi = HinglishNLUParser.parse("temp file bhi clear karo")
    assert act_with_bhi is not None
    assert act_with_bhi.modifier == "ALSO"
    assert act_with_bhi.parameters.get("modifier") == "ALSO"

    act_without_bhi = HinglishNLUParser.parse("clear temp file")
    assert act_without_bhi is not None
    assert act_without_bhi.modifier is None


def test_short_term_memory_tracks_command_context():
    """
    ActiveTargetContext must record last_intent, last_action, last_entities, and last_success.
    """
    ctx = ActiveTargetContext()
    ctx.update_command_context(
        intent="TEMP_FILE_CLEANUP",
        action="clear_temp_files",
        entities={"target": "temp_files"},
        service="system",
        raw_command="temp file clear karo",
        success=True,
    )

    summary = ctx.get_command_context()
    assert summary["last_intent"] == "TEMP_FILE_CLEANUP"
    assert summary["last_action"] == "clear_temp_files"
    assert summary["last_entities"] == {"target": "temp_files"}
    assert summary["last_service"] == "system"
    assert summary["last_success"] is True
    assert ctx.is_active is True

    ctx.clear()
    assert ctx.last_intent is None
    assert not ctx.last_action


def test_follow_up_repeat_resolution():
    """
    Follow-up phrases like 'phir se karo' or 'dobara karo' must execute
    the last command in context with is_repeat=True.
    """
    ctx = ActiveTargetContext()
    ctx.update_command_context(
        intent="TEMP_FILE_CLEANUP",
        action="clear_temp_files",
        entities={"target": "temp_files"},
        service="system",
        raw_command="clear temp file",
        success=True,
    )

    plugin_mock = MagicMock()
    plugin_mock.execute_action.return_value = PluginResult(
        success=True, data={"removed": 5, "skipped": 0, "message": "Temp cleanup complete, Boss. 5 items remove hue aur 0 in-use items skip hue."}
    )

    for repeat_phrase in ["phir se karo", "dobara karo", "again", "once more", "ek baar aur"]:
        res = ContextualActionResolver.resolve(repeat_phrase, context=ctx, plugin_manager=plugin_mock)
        assert res.handled is True, f"Failed to handle repeat phrase: {repeat_phrase}"
        assert res.action == "clear_temp_files"
        resp = res.response_message
        assert "dobara" in resp or "phir se" in resp or "again" in resp.lower() or "repeated" in resp.lower()


def test_context_does_not_override_explicit_target():
    """
    If the previous command was 'empty_recycle_bin', a new command with explicit
    target 'temp file bhi clear karo' must target temp files, NOT the recycle bin.
    """
    ctx = ActiveTargetContext()
    ctx.update_command_context(
        intent="RECYCLE_BIN_CLEANUP",
        action="empty_recycle_bin",
        entities={"target": "recycle_bin"},
        service="system",
        raw_command="recycle bin clear karo",
        success=True,
    )

    act = HinglishNLUParser.parse("temp file bhi clear karo", context=ctx)
    assert act is not None
    assert act.intent == IntentName.TEMP_FILE_CLEANUP
    assert act.action == "clear_temp_files"
    assert act.parameters.get("target") == "temp_files"


def test_natural_response_rotation():
    """
    NaturalResponseSynthesizer.system_maintenance rotates responses naturally.
    """
    # Reset counters for clean test
    NaturalResponseSynthesizer._counters.clear()

    resp1 = NaturalResponseSynthesizer.system_maintenance("clear_temp_files", target="temp", is_repeat=False)
    resp2 = NaturalResponseSynthesizer.system_maintenance("clear_temp_files", target="temp", is_repeat=False)
    resp3 = NaturalResponseSynthesizer.system_maintenance("clear_temp_files", target="temp", is_repeat=False)

    assert resp1 == "Done. Temp files clean kar diye."
    assert resp2 == "Done. Temp cleanup complete."
    assert resp3 == "Done. Temp files clean kar diye."  # Rotates back

    # Repeat variation
    resp_repeat = NaturalResponseSynthesizer.system_maintenance("clear_temp_files", target="temp", is_repeat=True)
    assert resp_repeat == "Done, temp cleanup dobara kar diya."


@pytest.fixture
def test_core(tmp_path, monkeypatch):
    db_path = str(tmp_path / "nlu_test.db").replace("\\", "/")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f'''system:\n  name: JARVIS_NLU_TEST\npermissions:\n  default_level: ADMIN\n  admin_mode: true\nmemory:\n  db_path: "{db_path}"\nbrain:\n  llm_provider: mock\nplugins:\n  plugin_dir: plugins\n  auto_load: true\n''',
        encoding="utf-8",
    )
    core = create_jarvis(str(config_path))
    core.permission_guard.admin_mode = True
    core.permission_guard.enforce = False
    return core


def test_four_turn_conversational_regression(test_core, monkeypatch):
    """
    Verifies the exact multi-turn conversation from Section 14:
    Turn 1: "please recycle bin khali karo" -> "Recycle Bin clear kar diya hai."
    Turn 2: "temp file bhi clear karo" -> "Done. Temp files clean kar diye."
    Turn 3: "clear temp file" -> "Done. Temp cleanup complete."
    Turn 4: "temp file bhi clear karo" -> "Done. Temp files clean kar diye."
    """
    import ctypes
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "shell32"):
        def fake_query(_root, byref_obj):
            byref_obj._obj.i64NumItems = 5
            byref_obj._obj.i64Size = 10240
            return 0
        def fake_empty(_hwnd, _root, _flags):
            return 0
        monkeypatch.setattr(ctypes.windll.shell32, "SHQueryRecycleBinW", fake_query)
        monkeypatch.setattr(ctypes.windll.shell32, "SHEmptyRecycleBinW", fake_empty)

    orig_execute = test_core.plugin_manager.execute_action
    def safe_execute(plugin, action, parameters):
        if plugin == "system" and action == "clear_temp_files":
            return PluginResult(success=True, data={"removed": 5, "skipped": 0, "message": "Temp cleanup complete, Boss. 5 items remove hue aur 0 in-use items skip hue."})
        if plugin == "system" and action == "empty_recycle_bin":
            return PluginResult(success=True, data={"message": "Recycle Bin clear kar diya hai, Boss."})
        return orig_execute(plugin, action, parameters)
    monkeypatch.setattr(test_core.plugin_manager, "execute_action", safe_execute)

    # Reset response variation counters
    NaturalResponseSynthesizer._counters.clear()

    # Turn 1: Recycle Bin
    resp1 = test_core.process_input("please recycle bin khali karo")
    assert resp1 == "Recycle Bin clear kar diya hai."
    assert "clear nahi hui" not in resp1

    # Turn 2: Temp files (with modifier 'bhi')
    resp2 = test_core.process_input("temp file bhi clear karo")
    assert resp2 == "Done. Temp files clean kar diye."
    assert "clear nahi hui" not in resp2

    # Turn 3: Direct imperative temp file
    resp3 = test_core.process_input("clear temp file")
    assert resp3 == "Done. Temp cleanup complete."
    assert "clear nahi hui" not in resp3

    # Turn 4: Repeated command with modifier 'bhi'
    resp4 = test_core.process_input("temp file bhi clear karo")
    assert resp4 in ("Done. Temp files clean kar diye.", "Done. Temp cleanup complete.")
    assert "clear nahi hui" not in resp4

    # Turn 5: Contextual Repeat
    resp5 = test_core.process_input("phir se karo")
    assert "dobara" in resp5 or "phir se" in resp5 or "Done" in resp5
    assert "clear nahi hui" not in resp5

