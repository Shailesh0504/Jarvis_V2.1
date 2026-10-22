# tests/test_universal_nlu_and_anti_guessing.py
"""
Universal NLU and Anti-Guessing Boundary Test Suite.
Verifies:
1. Audio & Volume Intelligence (colloquial idioms, flexible volume levels, directional ambiguity gating)
2. Media Controls (relative unquantified seek +10s/-10s, contextual playback vs resume vs clarification)
3. Windows App & Action Ellipsis (action inheritance for follow-ups: close/open, relative repeat)
4. Anti-Guessing Boundary (dual-target app vs website clarification and multi-turn resolution)
"""

import pytest
from unittest.mock import MagicMock

from core.context import ActiveTargetContext
from core.contextual_resolver import ContextualActionResolver
from core.dialog_manager import DialogManager
from core.semantic import SemanticPipelineOrchestrator
from core.semantic.parsers.system import parse_audio_control
from core.semantic.parsers.media import parse_youtube_control, parse_media_playback
from core.semantic.parsers.windows import parse_service_open
from core.semantic.parsers.web import parse_known_website


# ============================================================================
# 1. AUDIO & VOLUME INTELLIGENCE
# ============================================================================

def test_volume_setting_flexible_phrasings():
    """Verify numbers extracted correctly from various Hinglish/English phrasing."""
    cases = [
        ("volume 50 karo", 50),
        ("awaz 80% karo", 80),
        ("volume to 70", 70),
        ("sound 30 percent", 30),
        ("volume ko 60 karo", 60),
    ]
    for text, expected_level in cases:
        act = parse_audio_control(text, text.lower())
        assert act is not None, f"Failed for {text}"
        assert act.intent == "SET_VOLUME"
        assert act.parameters["level"] == expected_level


def test_volume_colloquial_idioms_down():
    """Verify colloquial expressions indicating high volume resolve to VOLUME_DOWN."""
    idioms = [
        "awaaz kaan phad rahi hai",
        "kaan phat rahe hain",
        "bahut tez hai",
        "bahut shor hai",
        "shor kam karo",
        "dheere karo",
        "sound down",
        "volume kam karo",
    ]
    for text in idioms:
        act = parse_audio_control(text, text.lower())
        assert act is not None, f"Failed for: {text}"
        assert act.intent == "VOLUME_DOWN", f"Expected VOLUME_DOWN for {text}, got {act.intent}"


def test_volume_colloquial_idioms_up():
    """Verify colloquial expressions indicating inaudibility resolve to VOLUME_UP."""
    idioms = [
        "awaaz nahi aa rahi",
        "kuch sunai nahi de raha",
        "awaaz bahut kam hai",
        "thoda tez bolo",
        "awaaz badhao",
        "volume up",
    ]
    for text in idioms:
        act = parse_audio_control(text, text.lower())
        assert act is not None, f"Failed for: {text}"
        assert act.intent == "VOLUME_UP", f"Expected VOLUME_UP for {text}, got {act.intent}"


def test_volume_directional_ambiguity_gate():
    """Verify vague volume queries trigger clarification without guessing direction."""
    ambiguous_queries = [
        "volume adjust karo",
        "awaaz theek karo",
        "volume sahi karo",
        "awaaz set karo",
        "adjust the volume",
    ]
    for text in ambiguous_queries:
        act = parse_audio_control(text, text.lower())
        assert act is not None, f"Failed for: {text}"
        assert act.needs_clarification is True
        assert "Volume badhana hai ya kam karna hai?" in act.clarification_prompt
        assert act.parameters.get("workflow_type") == "VOLUME_ADJUST"


# ============================================================================
# 2. MEDIA CONTROLS & CONTEXTUAL PLAYBACK
# ============================================================================

def test_media_relative_unquantified_seek():
    """Verify unquantified relative seeking defaults to +10s forward or -10s backward."""
    forward_phrases = [
        "thoda aage badhao",
        "aage karo",
        "skip karo",
        "fast forward",
        "seek forward",
    ]
    for text in forward_phrases:
        act = parse_youtube_control(text, text.lower())
        assert act is not None, f"Failed for forward seek: {text}"
        assert act.action == "seek"
        assert act.parameters["seconds"] == 10

    backward_phrases = [
        "thoda peeche karo",
        "thoda piche karo",
        "peeche karo",
        "rewind karo",
        "seek backward",
    ]
    for text in backward_phrases:
        act = parse_youtube_control(text, text.lower())
        assert act is not None, f"Failed for backward seek: {text}"
        assert act.action == "seek"
        assert act.parameters["seconds"] == -10


def test_media_playback_unspecified_target_clarification():
    """Verify generic playback request without active media triggers clarification."""
    act = parse_media_playback("gaana chalao", "gaana chalao", context=None)
    assert act is not None
    assert act.needs_clarification is True
    assert "Kaunsa gaana play karun, Boss?" in act.clarification_prompt
    assert act.missing_slot == "media_target"


def test_media_playback_resumes_when_context_active():
    """Verify generic playback request resumes playback if media was active/paused in context."""
    ctx = ActiveTargetContext()
    ctx.set_website("youtube", action="pause")
    ctx.last_action = "pause"

    act = parse_media_playback("gaana chalao", "gaana chalao", context=ctx)
    assert act is not None
    assert act.intent == "RESUME_MEDIA"
    assert act.action == "resume"
    assert act.needs_clarification is False


# ============================================================================
# 3. ACTION ELLIPSIS & RELATIVE REPEAT
# ============================================================================

def test_action_ellipsis_close_inheritance():
    """Verify 'aur Excel bhi' inherits close_app when last action was closing an app."""
    ctx = ActiveTargetContext()
    ctx.set_application("chrome", action="close_app")
    ctx.update_command_context("CLOSE_APPLICATION", "close_app", {"app_name": "chrome"}, service="windows")

    mock_pm = MagicMock()
    result = ContextualActionResolver.resolve("aur Excel bhi", ctx, plugin_manager=mock_pm)
    assert result.handled is True
    assert result.intent == "CLOSE_APPLICATION"
    assert result.action == "close_app"
    assert result.target == "excel"
    assert "Excel bhi band kar diya hai, Boss." in result.response_message
    mock_pm.execute_action.assert_called_with("windows", "close_app", {"app_name": "excel"})


def test_action_ellipsis_launch_inheritance():
    """Verify 'Notepad bhi' inherits launch_app when last action was opening an app."""
    ctx = ActiveTargetContext()
    ctx.set_application("chrome", action="launch_app")
    ctx.update_command_context("OPEN_APPLICATION", "launch_app", {"app_name": "chrome"}, service="windows")

    mock_pm = MagicMock()
    result = ContextualActionResolver.resolve("Notepad bhi", ctx, plugin_manager=mock_pm)
    assert result.handled is True
    assert result.intent == "OPEN_APPLICATION"
    assert result.action == "launch_app"
    assert result.target == "notepad"
    assert "Notepad bhi open kar diya hai, Boss." in result.response_message
    mock_pm.execute_action.assert_called_with("windows", "launch_app", {"app_name": "notepad"})


def test_relative_repeat_volume_up():
    """Verify 'thoda aur' repeats volume_up if last action was volume_up."""
    ctx = ActiveTargetContext()
    ctx.update_command_context("VOLUME_UP", "volume_up", {"step": 10}, service="audio")

    mock_pm = MagicMock()
    result = ContextualActionResolver.resolve("thoda aur", ctx, plugin_manager=mock_pm)
    assert result.handled is True
    assert result.intent == "VOLUME_UP"
    assert result.action == "volume_up"
    assert "Volume thoda aur badha diya hai, Boss." in result.response_message
    mock_pm.execute_action.assert_called_with("audio", "volume_up", {"step": 10})


def test_relative_repeat_volume_down():
    """Verify 'thoda aur' repeats volume_down if last action was volume_down."""
    ctx = ActiveTargetContext()
    ctx.update_command_context("VOLUME_DOWN", "volume_down", {"step": 10}, service="audio")

    mock_pm = MagicMock()
    result = ContextualActionResolver.resolve("thoda aur", ctx, plugin_manager=mock_pm)
    assert result.handled is True
    assert result.intent == "VOLUME_DOWN"
    assert result.action == "volume_down"
    assert "Volume thoda aur kam kar diya hai, Boss." in result.response_message
    mock_pm.execute_action.assert_called_with("audio", "volume_down", {"step": 10})


def test_relative_repeat_media_seek():
    """Verify 'thoda aur' repeats seek delta if last action was seek."""
    ctx = ActiveTargetContext()
    ctx.update_command_context("YOUTUBE_CONTROL", "seek", {"seconds": 10}, service="youtube")

    mock_pm = MagicMock()
    result = ContextualActionResolver.resolve("thoda aur", ctx, plugin_manager=mock_pm)
    assert result.handled is True
    assert result.intent == "YOUTUBE_CONTROL"
    assert result.action == "seek"
    assert "Thoda aur aage seek kar diya hai, Boss." in result.response_message
    mock_pm.execute_action.assert_called_with("youtube", "seek", {"seconds": 10})


# ============================================================================
# 4. ANTI-GUESSING BOUNDARY & DUAL-TARGET DISAMBIGUATION
# ============================================================================

def test_antigravity_ambiguous_clarification():
    """Verify 'antigravity kholo' triggers clarification without guessing app or website."""
    act = SemanticPipelineOrchestrator.parse("antigravity kholo")
    assert act is not None
    assert act.needs_clarification is True
    assert "application open karun ya website?" in act.clarification_prompt
    assert act.parameters.get("workflow_type") == "APP_WEB_DISAMBIGUATION"


def test_antigravity_explicit_app_no_clarification():
    """Verify explicit 'antigravity application kholo' launches the app directly."""
    act = SemanticPipelineOrchestrator.parse("antigravity application kholo")
    assert act is not None
    assert act.needs_clarification is False
    assert act.action == "launch_app"
    assert act.parameters["app_name"] == "antigravity"


def test_antigravity_explicit_website_no_clarification():
    """Verify explicit 'antigravity website kholo' opens the website directly."""
    act = SemanticPipelineOrchestrator.parse("antigravity website kholo")
    assert act is not None
    assert act.needs_clarification is False
    assert act.action == "open_website"
    assert act.parameters["site"] == "antigravity"


def test_dialog_manager_volume_adjust_resolution():
    """Verify DialogManager resolves VOLUME_ADJUST slot responses accurately."""
    dm = DialogManager()
    dm.set_lock(
        workflow_type="VOLUME_ADJUST",
        required_slots=["direction"],
        prompt_question="Volume badhana hai ya kam karna hai?"
    )

    mock_core = MagicMock()
    mock_core.plugin_manager = MagicMock()

    # User says "badhao"
    handled, msg = dm.process_locked_turn("badhao", mock_core)
    assert handled is True
    assert "Volume badha di hai, Boss." in msg
    mock_core.plugin_manager.execute_action.assert_called_with("audio", "volume_up", {"step": 10})

    # Reset and test "kam karo"
    dm.set_lock(
        workflow_type="VOLUME_ADJUST",
        required_slots=["direction"],
        prompt_question="Volume badhana hai ya kam karna hai?"
    )
    handled, msg = dm.process_locked_turn("kam karo", mock_core)
    assert handled is True
    assert "Volume kam kar di hai, Boss." in msg
    mock_core.plugin_manager.execute_action.assert_called_with("audio", "volume_down", {"step": 10})


def test_dialog_manager_app_web_disambiguation_resolution():
    """Verify DialogManager resolves APP_WEB_DISAMBIGUATION slot responses accurately."""
    dm = DialogManager()
    dm.set_lock(
        workflow_type="APP_WEB_DISAMBIGUATION",
        required_slots=["target_medium"],
        prompt_question="Antigravity application open karun ya website?",
        initial_slots={"app_id": "antigravity", "web_url": "https://antigravity.google.com", "display_name": "Antigravity"}
    )

    mock_core = MagicMock()
    mock_core.plugin_manager = MagicMock()
    mock_core.active_context = ActiveTargetContext()

    # User says "website"
    handled, msg = dm.process_locked_turn("website", mock_core)
    assert handled is True
    assert "Antigravity website open kar di hai, Boss." in msg
    mock_core.plugin_manager.execute_action.assert_called_with("browser", "open_website", {
        "url": "https://antigravity.google.com",
        "site": "antigravity"
    })

    # Reset and test "application"
    dm.set_lock(
        workflow_type="APP_WEB_DISAMBIGUATION",
        required_slots=["target_medium"],
        prompt_question="Antigravity application open karun ya website?",
        initial_slots={"app_id": "antigravity", "web_url": "https://antigravity.google.com", "display_name": "Antigravity"}
    )
    handled, msg = dm.process_locked_turn("application", mock_core)
    assert handled is True
    assert "Antigravity application open kar di hai, Boss." in msg
    mock_core.plugin_manager.execute_action.assert_called_with("windows", "launch_app", {
        "app_name": "antigravity"
    })
