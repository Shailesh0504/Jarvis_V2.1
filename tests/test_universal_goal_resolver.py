# tests/test_universal_goal_resolver.py
"""
Comprehensive Automated Test Suite for Universal Meaning -> Goal -> Capability Resolver.
Tests:
- Section 14: Universal Paraphrase Matrix (all 20 phrasings canonicalize to TEMP_FILE_CLEANUP)
- Section 8: Priority Hierarchy (explicit target > context; 'temp bhi clear karo' overrides recycle bin)
- Section 7 & 9: Anaphora, Repeat & Conversational Modifiers ('phir se karo', 'isme YouTube kholo', 'isko band karo')
- Section 10: Indirect Request Understanding & Precise Clarification ('bhai computer halka kar de')
- Section 11: Capability-Aware Failure Gate ('mere Windows ka pura registry optimize kar do')
- Section 20: Internal 11-field Debug Representation formatting
- Section 21: Multi-turn Conversational Regression Flow
- Section 16: Cross-Feature Generalization (Apps, Browser, Volume, Power)
"""

import pytest

from brain.response import ResponseGenerator
from brain.semantic_parser import HinglishNLUParser
from brain.llm import MockLLMProvider
from core.app import JarvisCore
from core.capabilities import CapabilityRegistry
from core.context import ActiveTargetContext
from core.permissions import PermissionLevel
from core.semantic.goal_resolver import UniversalGoalResolver
from core.semantic.models import IntentName
from core.semantic.resolution import ResolutionDecision
from memory.memory_manager import MemoryManager
from plugins.manager import PluginManager


@pytest.fixture
def test_core(tmp_path, monkeypatch):
    """Fixture providing initialized JarvisCore with admin permissions for verified execution."""
    db_path = str(tmp_path / "goal_res_test.db").replace("\\", "/")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f'''system:\n  name: JARVIS_GOAL_TEST\npermissions:\n  default_level: ADMIN\n  admin_mode: true\nmemory:\n  db_path: "{db_path}"\nbrain:\n  llm_provider: mock\nplugins:\n  plugin_dir: plugins\n  auto_load: true\n''',
        encoding="utf-8",
    )
    from main import create_jarvis
    from plugins.base import PluginResult

    core = create_jarvis(str(config_path))
    core.permission_guard.admin_mode = True
    core.permission_guard.enforce = False

    def safe_execute(plugin, action, parameters):
        if plugin == "system" and action == "clear_temp_files":
            return PluginResult(success=True, data={"removed": 5, "skipped": 0, "message": "Temp cleanup complete, Boss. 5 items remove hue aur 0 in-use items skip hue."})
        if plugin == "system" and action == "empty_recycle_bin":
            return PluginResult(success=True, data={"message": "Recycle Bin clear kar diya hai, Boss."})
        return PluginResult(success=True, data={})

    monkeypatch.setattr(core.plugin_manager, "execute_action", safe_execute)
    return core


# =========================================================================
# 1. Section 14: Universal Paraphrase Test Matrix (20 Phrases)
# =========================================================================

PARAPHRASE_TEST_PHRASES = [
    "temp file clear karo",
    "clear temp file",
    "temp files delete kar do",
    "temporary files hata do",
    "temp clean karo",
    "temp bhi clean karo",
    "temp file bhi clear karo",
    "temporary files ko saaf kar do",
    "temp data remove kar do",
    "temp folder clean kar do",
    "computer ke temporary files hata do",
    "system ka temp clean kar do",
    "temporary junk hata do",
    "temp wala saaf kar do",
    "bhai temp bhi delete kar de",
    "please clean temporary files",
    "remove temporary files",
    "delete temp data",
    "temp files ko remove karo",
    "phir se temp clean karo",
]


@pytest.mark.parametrize("phrase", PARAPHRASE_TEST_PHRASES)
def test_universal_paraphrases_canonicalize_to_temp_file_cleanup(phrase):
    """Verifies all 20 phrasings from Section 14 resolve to canonical TEMP_FILE_CLEANUP."""
    # Test via UniversalGoalResolver
    res = UniversalGoalResolver.resolve(phrase)
    assert res.goal == "TEMP_FILE_CLEANUP", f"Failed goal for '{phrase}': {res.goal}"
    assert res.intent == IntentName("TEMP_FILE_CLEANUP"), f"Wrong intent for '{phrase}': {res.intent}"
    assert res.capability_required == "system.maintenance.temp_cleanup"
    assert res.capability_available is True
    assert res.decision == ResolutionDecision.EXECUTE

    # Test via HinglishNLUParser.resolve_goal
    res_parser = HinglishNLUParser.resolve_goal(phrase)
    assert res_parser.goal == "TEMP_FILE_CLEANUP"

    # Test via HinglishNLUParser.parse (backward compatibility)
    act = HinglishNLUParser.parse(phrase)
    assert act is not None, f"Failed to parse '{phrase}'"
    assert act.intent == IntentName("TEMP_FILE_CLEANUP")
    assert act.service == "system"
    assert act.action == "clear_temp_files"


# =========================================================================
# 2. Section 8: Priority Hierarchy (Explicit Target > Context)
# =========================================================================

def test_explicit_target_priority_overrides_context():
    """
    Section 8 Invariant:
    User: 'Recycle Bin clear karo'
    User: 'temp bhi clear karo'
    Second request must resolve to TEMP_FILE_CLEANUP, NOT Recycle Bin.
    """
    ctx = ActiveTargetContext()
    ctx.update_command_context(
        intent="RECYCLE_BIN_CLEANUP",
        action="empty_recycle_bin",
        entities={"target": "recycle_bin"},
        service="system",
    )
    assert ctx.last_intent == "RECYCLE_BIN_CLEANUP"

    # Now user says "temp bhi clear karo"
    res = UniversalGoalResolver.resolve("temp bhi clear karo", context=ctx)
    assert res.goal == "TEMP_FILE_CLEANUP", f"Explicit target failed to override context: {res.goal}"
    assert res.intent == IntentName("TEMP_FILE_CLEANUP")
    assert res.entities.get("entity") == "temp_files"
    assert res.parameters.get("modifier") == "ALSO"
    assert res.capability_required == "system.maintenance.temp_cleanup"
    assert res.decision == ResolutionDecision.EXECUTE


# =========================================================================
# 3. Section 7 & 9: Anaphora, Modifiers & Contextual Follow-ups
# =========================================================================

def test_generic_repeat_anaphora_resolution():
    """Tests 'phir se karo' and 'same kaam karo' inherit previous goal."""
    ctx = ActiveTargetContext()
    ctx.update_command_context(
        intent="TEMP_FILE_CLEANUP",
        action="clear_temp_files",
        entities={"target": "temp_files"},
        service="system",
    )

    for phrase in ["phir se karo", "same kaam karo", "dobara kar do", "haan wohi karo"]:
        res = UniversalGoalResolver.resolve(phrase, context=ctx)
        assert res.goal == "TEMP_FILE_CLEANUP", f"Failed repeat for '{phrase}': {res.goal}"
        assert res.capability_required == "system.maintenance.temp_cleanup"
        assert res.decision == ResolutionDecision.EXECUTE
        assert "last_intent" in res.context_dependencies or "last_action" in res.context_dependencies


def test_container_context_inheritance():
    """
    Section 7 Invariant:
    Turn 1: Chrome kholo
    Turn 2: isme YouTube kholo -> container=chrome, entity=youtube
    Turn 3: Brave mein YouTube kholo
    Turn 4: isme Gmail bhi kholo -> container=brave, entity=gmail, modifier=ALSO
    """
    ctx = ActiveTargetContext()
    ctx.set_application("chrome", action="launch_app")

    res1 = UniversalGoalResolver.resolve("isme YouTube kholo", context=ctx)
    assert res1.entities.get("container") == "chrome"
    assert res1.entities.get("entity") == "youtube"
    assert res1.goal == "OPEN_WEBSITE"
    assert res1.decision == ResolutionDecision.EXECUTE

    ctx2 = ActiveTargetContext()
    ctx2.set_application("brave", action="launch_app")

    res2 = UniversalGoalResolver.resolve("isme Gmail bhi kholo", context=ctx2)
    assert res2.entities.get("container") == "brave"
    assert res2.entities.get("entity") == "gmail"
    assert res2.parameters.get("modifier") == "ALSO"
    assert res2.goal == "OPEN_WEBSITE"
    assert res2.decision == ResolutionDecision.EXECUTE


def test_pronoun_action_resolution():
    """Tests 'isko band karo', 'isko minimize karo' against active target in context."""
    ctx = ActiveTargetContext()
    ctx.set_application("brave", action="launch_app")

    res_close = UniversalGoalResolver.resolve("isko band karo", context=ctx)
    assert res_close.goal == "CLOSE_APPLICATION"
    assert res_close.entities.get("app_name") == "brave"
    assert res_close.decision == ResolutionDecision.EXECUTE

    res_min = UniversalGoalResolver.resolve("isko minimize karo", context=ctx)
    assert res_min.goal == "MINIMIZE_WINDOW"
    assert res_min.entities.get("app_name") == "brave"
    assert res_min.decision == ResolutionDecision.EXECUTE


# =========================================================================
# 4. Section 10: Indirect Phrasing & Precise Clarification
# =========================================================================

def test_indirect_cleanup_triggers_precise_clarification():
    """
    Section 4 & 10 Invariant:
    'bhai computer halka kar de' without context must NOT blindly guess;
    it must ask precise clarification:
    'Computer cleanup mein temp files saaf karun ya Recycle Bin bhi?'
    """
    res = UniversalGoalResolver.resolve("bhai computer halka kar de")
    assert res.decision == ResolutionDecision.ASK_PRECISE_CLARIFICATION
    assert res.goal == "SYSTEM_CLEANUP"
    assert res.clarification_prompt == "Computer cleanup mein temp files saaf karun ya Recycle Bin bhi?"

    # Also test via orchestrator parser
    act = HinglishNLUParser.parse("bhai computer halka kar de")
    assert act is not None
    assert act.needs_clarification is True
    assert act.clarification_prompt == "Computer cleanup mein temp files saaf karun ya Recycle Bin bhi?"


def test_capability_question_does_not_execute():
    """
    Section 3 Invariant:
    'computer mein jo temporary garbage hai usko hata sakte ho?'
    is a CAPABILITY_QUESTION -> answers ability directly; NEVER executes.
    """
    res = UniversalGoalResolver.resolve("computer mein jo temporary garbage hai usko hata sakte ho?")
    assert res.speech_act == "CAPABILITY_QUESTION"
    assert res.decision == ResolutionDecision.ANSWER
    assert "Haan" in res.response_text
    assert "saaf kar sakta hoon" in res.response_text


# =========================================================================
# 5. Section 11: Capability-Aware Failure Gate
# =========================================================================

def test_unsupported_capability_honest_refusal():
    """
    Section 11 Invariant:
    'mere Windows ka pura registry optimize kar do'
    must NOT hallucinate capability; returns transparent refusal:
    'Ye exact operation abhi meri available capabilities mein nahi hai.'
    """
    res = UniversalGoalResolver.resolve("mere Windows ka pura registry optimize kar do")
    assert res.decision == ResolutionDecision.CAPABILITY_UNAVAILABLE
    assert res.capability_available is False
    assert res.response_text == CapabilityRegistry.UNSUPPORTED_RESPONSE


# =========================================================================
# 6. Section 20: Internal 11-Field Debug Representation
# =========================================================================

def test_internal_debug_representation_format():
    """
    Section 20 Invariant:
    Internal debug string includes all 11 decision fields:
    INPUT, MEANING, SPEECH ACT, GOAL, INTENT, ENTITY, CONTEXT, CAPABILITY, CONFIDENCE, DECISION.
    """
    res = UniversalGoalResolver.resolve("computer ka temp bhi saaf kar do")
    debug_str = res.to_debug_string()

    required_headers = [
        "INPUT:",
        "MEANING:",
        "SPEECH ACT:",
        "GOAL:",
        "INTENT:",
        "ENTITY:",
        "CONTEXT:",
        "CAPABILITY:",
        "CONFIDENCE:",
        "DECISION:",
    ]
    for header in required_headers:
        assert header in debug_str, f"Missing header '{header}' in debug string:\n{debug_str}"

    assert "TEMP_FILE_CLEANUP" in debug_str
    assert "EXECUTE" in debug_str
    assert "system.maintenance.temp_cleanup" in debug_str


# =========================================================================
# 7. Section 16: Cross-Feature Generalization
# =========================================================================

def test_cross_feature_applications():
    """Tests application launches and closures across varied phrasings."""
    # Launch Chrome
    for phrase in ["Chrome kholo", "Chrome open karo", "Chrome chala do", "bhai Chrome start kar"]:
        res = UniversalGoalResolver.resolve(phrase)
        assert res.goal == "OPEN_APPLICATION", f"Failed for '{phrase}'"
        assert res.entities.get("entity") == "chrome"
        assert res.decision == ResolutionDecision.EXECUTE

    # Close Brave
    for phrase in ["Brave band karo", "Brave close kar do", "Brave ko hata do"]:
        res = UniversalGoalResolver.resolve(phrase)
        assert res.goal == "CLOSE_APPLICATION", f"Failed for '{phrase}'"
        assert res.entities.get("entity") == "brave"
        assert res.decision == ResolutionDecision.EXECUTE


def test_cross_feature_websites_and_media():
    """Tests website opening and media playback resolution."""
    # Open website
    for phrase in ["YouTube kholo", "YouTube browser mein chalao", "browser par YouTube le aao"]:
        res = UniversalGoalResolver.resolve(phrase)
        assert res.goal in ("OPEN_WEBSITE", "PLAY_MEDIA"), f"Failed for '{phrase}'"
        assert res.entities.get("entity") == "youtube"
        assert res.decision == ResolutionDecision.EXECUTE

    # Volume up
    res_vol = UniversalGoalResolver.resolve("awaz badhao")
    assert res_vol.goal == "VOLUME_UP"
    assert res_vol.decision == ResolutionDecision.EXECUTE

    # System lock
    res_lock = UniversalGoalResolver.resolve("system lock karo")
    assert res_lock.goal == "LOCK_SYSTEM"
    assert res_lock.decision == ResolutionDecision.EXECUTE


# =========================================================================
# 8. Section 21: Multi-Turn Conversational Regression Flow
# =========================================================================

def test_section_21_exact_conversation_flow(test_core):
    """
    Section 21 Invariant:
    User: please recycle bin khali karo
    Jarvis: Recycle Bin clear kar diya.
    User: temp file bhi clear karo
    Jarvis: Temp files clean kar diye.
    User: clear temp file
    Jarvis: Done.
    User: temp file bhi clear karo
    Jarvis: Done.
    """
    # Turn 1: Empty Recycle Bin
    resp1 = test_core.process_input("please recycle bin khali karo")
    assert "recycle bin" in resp1.lower()

    # Turn 2: Temp file bhi clear karo (must clean temp files, NOT recycle bin!)
    resp2 = test_core.process_input("temp file bhi clear karo")
    assert "temp" in resp2.lower()

    # Turn 3: Clear temp file
    resp3 = test_core.process_input("clear temp file")
    assert "temp" in resp3.lower()

    # Turn 4: Temp file bhi clear karo
    resp4 = test_core.process_input("temp file bhi clear karo")
    assert "temp" in resp4.lower()

    # Turn 5: Direct temp clean
    resp5 = test_core.process_input("temp clean karo")
    assert "temp" in resp5.lower()

    # Turn 6: Phir se karo (repeats temp clean)
    resp6 = test_core.process_input("phir se karo")
    assert "temp" in resp6.lower() or "dobara" in resp6.lower() or "done" in resp6.lower()


def test_section_21_indirect_cleanup_dialog_flow(test_core):
    """
    Tests indirect cleanup multi-turn disambiguation:
    User: 'bhai computer halka kar de'
    Jarvis: 'Computer cleanup mein temp files saaf karun ya Recycle Bin bhi?'
    User: 'temp files'
    Jarvis: 'Done. Temp files clean kar diye.'
    """
    resp_ask = test_core.process_input("bhai computer halka kar de")
    assert "Computer cleanup mein temp files saaf karun ya Recycle Bin bhi?" in resp_ask

    resp_answer = test_core.process_input("temp files")
    assert "temp" in resp_answer.lower()
