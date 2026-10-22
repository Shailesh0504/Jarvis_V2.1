# tests/test_coucou_sound_mochi_visuals.py
"""Comprehensive acceptance test suite for Coucou-Style Sound + Mochi Visual System.

Verifies:
1. Master Sound -> Visual Mapping for all 28 named sounds.
2. Character state machine, eye shapes, and badges.
3. FSM UI transitions: HIDDEN -> COMPACT (peek), COMPACT -> EXPANDED (open), EXPANDED -> COMPACT (close).
4. Same-state transitions stay completely silent.
5. Startup greeting ceremony coordination.
6. Task and chat lifecycles.
7. Permission/approval pinning and unpinning.
8. File drop and upload decile gating: tick ONLY at 10%, 20%, ..., 90%; never 0%, 100% approve.
9. Hover and sustained hover love reactions with cooldowns.
10. Slap click squash and 3-click dizzy spiral rotation.
11. SoundEngine controls: volume, enable/disable, missing asset safety, dedup, cooldowns.
"""

import os
import time
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt, QPoint, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])

from gui.sound_effects import Sound, JarvisSoundEngine, SOUND_NAMES
from gui.island.character import JarvisCharacter
from gui.island.state_machine import GuiVisibilityState
from gui.island.visibility_manager import CoucouVisibilityManager
from gui.island.semantic_events import (
    jarvis_visual_event,
    register_visual_targets,
    SemanticEventManager,
    EVENT_COOLDOWNS,
    EVENT_DISPATCH_TABLE
)


@pytest.fixture(autouse=True)
def setup_sound_engine_test_mode():
    """Configures the sound engine to record all plays for test inspection."""
    engine = JarvisSoundEngine.instance()
    engine.set_enabled(True)
    engine.set_volume(0.15)
    engine.record_all_plays_for_test = True
    engine.played_history.clear()
    engine.last_played_sound = None
    with engine._lock:
        engine._seen_events.clear()
        engine._last_play.clear()

    # Reset semantic event manager state
    mgr = SemanticEventManager.instance()
    with mgr._lock:
        mgr._seen_event_ids.clear()
        mgr._last_event_time.clear()
        mgr._last_ticked_deciles.clear()
    yield
    engine.played_history.clear()


# ── 1. Master Sound Mapping Tests ─────────────────────────────────────────────

def test_all_28_sounds_present_and_dispatched():
    """Verifies that all 28 named sounds can be played or dispatched safely."""
    engine = JarvisSoundEngine.instance()
    
    expected_sounds = [
        "peek", "open", "close", "greet", "work", "think", "search",
        "approval", "approve", "finish", "error", "question", "rate",
        "sleep", "dizzy", "slap", "annoyed", "hover", "love", "wink",
        "proud", "yawn", "send", "tick", "blip", "gulp", "pop", "attach"
    ]
    
    for snd in expected_sounds:
        res = engine.play(snd, cooldown_ms=0)
        assert res is True, f"Failed to play sound: {snd}"
        assert engine.last_played_sound == snd


def test_character_states_and_palettes():
    """Verifies all Coucou character states are recognized and map to appropriate eyes & badges."""
    character = JarvisCharacter(size=36)
    
    states_to_test = {
        "idle": ("pill", None),
        "working": ("pill", "dots"),
        "thinking": ("pill", "dots"),
        "searching": ("searching", "search"),
        "approval": ("wide", "alert"),
        "question": ("wide", "question"),
        "error": ("flat", "dot"),
        "finished": ("happy", "dot"),
        "ratelimit": ("tired", "alert"),
        "sleeping": ("closed", None),
        "dizzy": ("spiral", None),
        "love": ("love_hearts", None),
        "proud": ("happy", None),
        "wink": ("wink", None),
        "annoyed": ("line", None),
        "happy": ("happy", None),
    }
    
    for state, (expected_eye, expected_badge_kind) in states_to_test.items():
        character.set_system_state(state)
        assert character._current_state == ("emote_love" if state == "love" else state)
        assert character._eye_shape == expected_eye, f"State {state} expected eye {expected_eye}, got {character._eye_shape}"
        if expected_badge_kind is not None:
            assert character.badge_kind == expected_badge_kind, f"State {state} expected badge {expected_badge_kind}, got {character.badge_kind}"


# ── 2. Exact UI State Transitions (FSM) ──────────────────────────────────────

def test_ui_visibility_fsm_sounds():
    """Verifies HIDDEN->COMPACT=peek, COMPACT->EXPANDED=open, EXPANDED->COMPACT=close, and same-state=NO SOUND."""
    engine = JarvisSoundEngine.instance()
    character = JarvisCharacter(size=36)

    # 1. HIDDEN -> COMPACT = peek.wav
    res = jarvis_visual_event("hidden_to_compact", character=character)
    assert res["sound"] == "peek"
    assert engine.last_played_sound == "peek"

    # 2. Same-state transition produces NO sound
    engine.last_played_sound = None
    res_repeat = jarvis_visual_event("hidden_to_compact", character=character)
    # Cooldown suppresses duplicate
    assert res_repeat["sound_played"] is False

    # 3. COMPACT -> EXPANDED = open.wav
    res_open = jarvis_visual_event("compact_to_expanded", character=character)
    assert res_open["sound"] == "open"
    assert engine.last_played_sound == "open"

    # 4. EXPANDED -> COMPACT = close.wav
    res_close = jarvis_visual_event("expanded_to_compact", character=character)
    assert res_close["sound"] == "close"
    assert engine.last_played_sound == "close"


# ── 3. Startup Greeting Coordination ──────────────────────────────────────────

def test_startup_greeting_event():
    """Verifies greet.wav coordinates with happy character visual state."""
    engine = JarvisSoundEngine.instance()
    character = JarvisCharacter(size=36)
    
    res = jarvis_visual_event("startup_greeting", character=character)
    assert res["sound"] == "greet"
    assert res["state"] == "happy"
    assert character._current_state == "happy"
    assert character._eye_shape == "happy"


# ── 4. Task and Chat Lifecycles ───────────────────────────────────────────────

def test_task_lifecycle_coordination():
    """Verifies task lifecycle: work.wav -> think.wav -> search.wav -> finish.wav / error.wav."""
    engine = JarvisSoundEngine.instance()
    character = JarvisCharacter(size=36)

    # Start task
    res_start = jarvis_visual_event("task_started", character=character)
    assert res_start["sound"] == "work"
    assert character._current_state == "working"

    # Thinking
    res_think = jarvis_visual_event("thinking_started", character=character)
    assert res_think["sound"] == "think"
    assert character._current_state == "thinking"

    # Searching
    res_search = jarvis_visual_event("search_started", character=character)
    assert res_search["sound"] == "search"
    assert character._current_state == "searching"
    assert character._eye_shape == "searching"

    # Verified Success
    res_finish = jarvis_visual_event("task_success", character=character)
    assert res_finish["sound"] == "finish"
    assert character._current_state == "finished"
    assert character._eye_shape == "happy"

    # Failure
    res_fail = jarvis_visual_event("task_failed", character=character)
    assert res_fail["sound"] == "error"
    assert character._current_state == "error"
    assert character._eye_shape == "flat"


def test_chat_lifecycle_coordination():
    """Verifies message send -> send.wav."""
    engine = JarvisSoundEngine.instance()
    character = JarvisCharacter(size=36)

    res = jarvis_visual_event("message_sent", character=character)
    assert res["sound"] == "send"
    assert engine.last_played_sound == "send"


# ── 5. Permission / Approval ──────────────────────────────────────────────────

def test_permission_approval_pinning():
    """Verifies approval.wav sets orange character and pins UI; approve/deny unpins."""
    engine = JarvisSoundEngine.instance()
    character = JarvisCharacter(size=36)
    
    class MockVisibilityMgr:
        def __init__(self):
            self.pinned = False
        def set_pinned(self, p):
            self.pinned = p

    vm = MockVisibilityMgr()
    
    # Request approval
    res_req = jarvis_visual_event("approval_required", character=character, visibility_mgr=vm)
    assert res_req["sound"] == "approval"
    assert character._current_state == "approval"
    assert character._eye_shape == "wide"
    assert character.badge_kind == "alert"
    assert vm.pinned is True

    # User approves
    res_app = jarvis_visual_event("user_approved", character=character, visibility_mgr=vm)
    assert res_app["sound"] == "approve"
    assert character._current_state == "happy"
    assert vm.pinned is False

    # Reset and test user denies
    vm.set_pinned(True)
    res_den = jarvis_visual_event("user_denied", character=character, visibility_mgr=vm)
    assert res_den["sound"] == "blip"
    assert vm.pinned is False


# ── 6. File Drop and Upload Decile Gating ──────────────────────────────────────

def test_file_drop_and_upload_progress_deciles():
    """Verifies gulp on file accept and tick.wav ONLY at deciles 10..90; 0%=no tick, 100%=approve."""
    engine = JarvisSoundEngine.instance()
    character = JarvisCharacter(size=36)

    # 1. File accepted -> gulp
    res_drop = jarvis_visual_event("file_accepted", character=character)
    assert res_drop["sound"] == "gulp"

    # 2. Upload progress 0% -> NO tick
    res_0 = jarvis_visual_event("upload_progress", percent=0, event_id="test_sess")
    assert res_0["sound_played"] is False

    # 3. Intermediate percent (5%) -> NO tick
    res_5 = jarvis_visual_event("upload_progress", percent=5, event_id="test_sess")
    assert res_5["sound_played"] is False

    # 4. 10% -> tick!
    res_10 = jarvis_visual_event("upload_progress", percent=10, event_id="test_sess")
    assert res_10["sound_played"] is True
    assert res_10["sound"] == "tick"

    # 5. Repeated callback at 12% (same decile) -> NO tick
    res_12 = jarvis_visual_event("upload_progress", percent=12, event_id="test_sess")
    assert res_12["sound_played"] is False

    # 6. Next deciles 20%, 30%, ..., 90% -> tick each
    for d in [20, 30, 40, 50, 60, 70, 80, 90]:
        res_d = jarvis_visual_event("upload_progress", percent=d, event_id="test_sess")
        assert res_d["sound_played"] is True
        assert res_d["sound"] == "tick"

    # 7. 100% -> approve.wav
    res_100 = jarvis_visual_event("upload_progress", percent=100, event_id="test_sess", character=character)
    assert res_100["sound_played"] is True
    assert res_100["sound"] == "approve"
    assert character._current_state == "happy"


# ── 7. Hover and Sustained Hover Interaction ──────────────────────────────────

def test_character_hover_and_sustained_love():
    """Verifies hover entry plays hover.wav once, and sustained hover triggers love.wav."""
    engine = JarvisSoundEngine.instance()
    character = JarvisCharacter(size=36)

    # Hover enter
    res_hover = jarvis_visual_event("hover", character=character)
    assert res_hover["sound"] == "hover"

    # Rapid hover re-trigger within cooldown -> suppressed
    res_hover_suppressed = jarvis_visual_event("hover", character=character)
    assert res_hover_suppressed["sound_played"] is False

    # Sustained hover -> love.wav with heart eyes
    res_love = jarvis_visual_event("sustained_hover", character=character)
    assert res_love["sound"] == "love"
    assert character._current_state == "emote_love"
    assert character._eye_shape == "love_hearts"


# ── 8. Character Click / Slap & Triple-Click Dizzy ─────────────────────────────

def test_character_slap_squash_and_triple_click_dizzy():
    """Verifies single click triggers slap squash and 3 rapid clicks trigger dizzy rotation."""
    character = JarvisCharacter(size=36)
    
    # 1. Single click -> slap
    character.trigger_slap()
    assert character._squash_scale_y < 1.0  # squashed
    assert character._squash_scale_x > 1.0  # stretched horizontally

    # 2. 3 rapid clicks directly on character -> dizzy
    ev = QMouseEvent(QEvent.MouseButtonPress, QPoint(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    character._click_history.clear()
    
    # Click 1
    character.mousePressEvent(ev)
    assert len(character._click_history) == 1
    
    # Click 2
    character.mousePressEvent(ev)
    assert len(character._click_history) == 2
    
    # Click 3 -> triggers dizzy
    character.mousePressEvent(ev)
    assert character._current_state == "dizzy"
    assert character._eye_shape == "spiral"


# ── 9. Deduplication and Event IDs ────────────────────────────────────────────

def test_event_id_deduplication():
    """Verifies that duplicate event IDs are suppressed."""
    engine = JarvisSoundEngine.instance()
    character = JarvisCharacter(size=36)

    # First event with id=task_999
    res1 = jarvis_visual_event("task_started", event_id="task_999", character=character)
    assert res1["sound_played"] is True

    # Immediate duplicate event with same ID
    res2 = jarvis_visual_event("task_started", event_id="task_999", character=character)
    assert res2["sound_played"] is False
    assert res2.get("suppressed") == "duplicate_id"

    # Third duplicate
    res3 = jarvis_visual_event("task_started", event_id="task_999", character=character)
    assert res3["sound_played"] is False


# ── 10. SoundEngine Volume and Safety Controls ────────────────────────────────

def test_sound_engine_controls():
    """Verifies volume slider, toggle, and missing asset safety."""
    engine = JarvisSoundEngine.instance()

    # Volume control
    engine.set_volume(0.42)
    assert abs(engine.get_volume() - 0.42) < 0.01

    # Zero volume suppresses playback
    engine.set_volume(0.0)
    res_zero = engine.play("blip", cooldown_ms=0)
    assert res_zero is False
    engine.set_volume(0.5)

    # Toggle enable / disable
    engine.set_enabled(False)
    assert engine.is_enabled() is False
    res_disabled = engine.play("blip", cooldown_ms=0)
    assert res_disabled is False

    engine.set_enabled(True)
    assert engine.is_enabled() is True
    res_enabled = engine.play("blip", cooldown_ms=0)
    assert res_enabled is True

    # Missing WAV asset is safe and does not raise
    res_missing = engine.play("non_existent_sound_12345", cooldown_ms=0)
    assert res_missing is False
