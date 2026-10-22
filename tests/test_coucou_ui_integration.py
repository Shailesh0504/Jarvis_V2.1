# tests/test_coucou_ui_integration.py
"""Unit tests verifying JARVIS Dynamic Island UI, Original Character, FSM, and Controller."""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication(["-platform", "offscreen"])

import pytest
from main import create_jarvis
from gui.app import JarvisMainWindow
from gui.sound_effects import Sound, JarvisSoundEngine, CoucouSoundEngine
from gui.island.character import JarvisCharacter
from gui.island.state_machine import IslandState, IslandStateMachine
from gui.island.controller import IslandController


@pytest.fixture(scope="session")
def qapp():
    return _app


@pytest.fixture
def jarvis_gui_core(tmp_path):
    db_file = os.path.join(tmp_path, "gui_coucou_test.db").replace("\\", "/")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(f"""
system:
  name: "JARVIS_ISLAND_TEST"
memory:
  db_path: "{db_file}"
brain:
  llm_provider: "mock"
reminder:
  db_path: "{str(tmp_path / 'gui_reminders.db').replace(chr(92), '/')}"
plugins:
  plugin_dir: "plugins"
  auto_load: true
""")
    return create_jarvis(str(cfg_file))


def test_jarvis_sound_engine():
    """Verifies that the native Jarvis sound engine plays cues safely."""
    engine = JarvisSoundEngine.instance()
    assert engine is not None
    assert engine.enabled is True

    engine.play("greet")
    engine.play("blip")
    engine.play("finish")
    engine.play("non_existent_safe")


def test_jarvis_character_widget(qapp):
    """Verifies that the original JARVIS Character renders, handles states, and tracks gaze."""
    character = JarvisCharacter(size=36)
    assert character.width() >= 36
    assert character.height() >= 30

    # Test state changes
    character.set_system_state("listening")
    assert character._current_state == "listening"
    assert character._eye_aperture == "wide"

    character.set_system_state("thinking")
    assert character._current_state == "thinking"

    character.set_system_state("executing")
    assert character._current_state == "executing"

    character.set_system_state("success")
    assert character._current_state == "success"
    assert character._eye_aperture == "arc_happy"

    character.set_system_state("error")
    assert character._current_state == "error"
    assert character._eye_aperture == "alert_line"

    character.set_system_state("ready")
    assert character._current_state == "idle"

    character.repaint()
    character.close()


def test_island_state_machine():
    """Verifies the 16-state IslandStateMachine transitions and listeners."""
    fsm = IslandStateMachine(initial_state=IslandState.IDLE_HIDDEN)
    assert fsm.current_state == IslandState.IDLE_HIDDEN
    assert fsm.is_idle() is True

    # Transition to peek
    fsm.transition_to(IslandState.IDLE_PEEK, reason="approach")
    assert fsm.current_state == IslandState.IDLE_PEEK

    # Transition to compact
    fsm.transition_to(IslandState.COMPACT, reason="hover")
    assert fsm.current_state == IslandState.COMPACT
    assert fsm.is_idle() is False

    # Transition to chat
    fsm.transition_to(IslandState.CHAT, reason="click")
    assert fsm.current_state == IslandState.CHAT
    assert fsm.is_interactive() is True


def test_main_window_coucou_dynamic_island(qapp, jarvis_gui_core):
    """Verifies JARVIS Dynamic Island mode, character, and studio toggle."""
    window = JarvisMainWindow(jarvis_gui_core)

    # 1. Verify character exists in header
    assert hasattr(window, "character")
    assert isinstance(window.character, JarvisCharacter)
    assert hasattr(window, "mochi")

    # 2. Verify telemetry pills in header
    assert hasattr(window, "model_pill")
    assert hasattr(window, "mic_pill")
    assert hasattr(window, "island_btn")

    # 3. Test Dynamic Island mode toggle (Island Mode is primary & default)
    assert window._is_island_mode is True
    assert window.sidebar.isHidden() is True
    assert "Studio" in window.island_btn.text()

    # Toggle to Studio mode
    window.toggle_island_mode()
    assert window._is_island_mode is False
    assert window.sidebar.isHidden() is False
    assert window.status_bar.isHidden() is False
    assert "Island" in window.island_btn.text()

    # Toggle back to Island mode
    window.toggle_island_mode()
    assert window._is_island_mode is True
    assert window.sidebar.isHidden() is True
    assert window.status_bar.isHidden() is True
    assert "Studio" in window.island_btn.text()

    # 4. State updates properly propagate to Character
    window.set_system_state("listening")
    assert window.character._current_state == "listening"

    window.set_system_state("thinking")
    assert window.character._current_state == "thinking"

    window.set_system_state("ready")
    assert window.character._current_state == "idle"

    from PySide6.QtGui import QCloseEvent
    window.closeEvent(QCloseEvent())
    window.close()


def test_coucou_spring_physics_animator():
    """Verifies Coucou Spring, Tracked, and IslandPhysicsAnimator numerical stability."""
    from gui.island.animator import Spring, Tracked, IslandPhysicsAnimator, close_curve

    # 1. Test close_curve
    assert close_curve(0.0) == 0.0
    assert abs(close_curve(1.0) - 1.0) < 0.01

    # 2. Test Spring
    spring = Spring(100.0, response=0.5, damping=0.72)
    spring.target = 200.0
    for _ in range(60):
        spring.step(0.016)
    assert abs(spring.value - 200.0) < 15.0

    # 3. Test Tracked spring and curve
    tracked = Tracked(288.0)
    tracked.spring_to(640.0)
    assert tracked.animating is True
    for _ in range(120):
        tracked.step(0.016)
    assert abs(tracked.value - 640.0) < 5.0

    # 4. Test IslandPhysicsAnimator transitions
    animator = IslandPhysicsAnimator(initial_w=288.0, initial_h=32.0)
    animator.transition_to(target_w=640.0, target_h=160.0, bot_cx=58.0, bot_cy=84.0, bot_d=56.0, is_closing=False)
    assert animator.is_animating is True
    for _ in range(60):
        animator.step()
    assert animator.w.value > 300.0
    assert animator.h.value > 40.0


def test_coucou_all_card_views(qapp):
    """Verifies all specialized Coucou card views instantiate, format, and handle signals."""
    from gui.island.views import (
        CoucouHeaderWidget, CoucouOverviewCard, CoucouApprovalCard,
        CoucouQuestionCard, CoucouFinishedCard, CoucouErrorCard,
        CoucouChatCard, CoucouDropCard
    )

    # 1. Header widget
    header = CoucouHeaderWidget()
    assert header.height() == 34
    header.set_active_tab("chat")
    assert header._active_tab == "chat"
    header._toggle_sound()
    assert header._sound_enabled is False

    # 2. Overview card
    overview = CoucouOverviewCard()
    overview.set_activity("JARVIS", "Processing request", "#00f0ff")
    assert overview.who_name.text() == "JARVIS"

    # 3. Approval card
    approval = CoucouApprovalCard()
    approval.set_approval_data("rm -rf temp", reason="High Risk Command")
    assert "High Risk" in approval.who_label.text()
    assert "rm -rf" in approval.code_label.text()
    decision_result = []
    approval.decision_made.connect(lambda allowed: decision_result.append(allowed))
    approval.allow_btn.click()
    assert decision_result == [True]

    # 4. Question card
    question = CoucouQuestionCard()
    question.set_question("Kaunsa folder kholun?", ["Folder A", "Folder B"])
    assert "folder" in question.question_text.text()

    # 5. Finished card
    finished = CoucouFinishedCard()
    finished.set_finished_data("Task Done", "File downloaded")
    assert finished.summary_title.text() == "Task Done"

    # 6. Error card
    error = CoucouErrorCard()
    error.set_error_data("Failed", "Connection refused")
    assert error.error_title.text() == "Failed"

    # 7. Chat card
    chat = CoucouChatCard()
    chat.add_message("user", "Hello Jarvis")
    chat.add_message("assistant", "Hello Boss, how can I assist you?")
    assert chat.bubble_layout.count() >= 2

    # 8. Drop card
    drop = CoucouDropCard()
    assert drop is not None


def test_coucou_island_widget_states_and_morphing(qapp):
    """Verifies CoucouIslandWidget geometry modes, animation step, and views switching."""
    from gui.island.island import CoucouIslandWidget

    island = CoucouIslandWidget()
    assert island.width() == 720
    assert island.height() == 320

    # 1. Test Hidden mode
    island.set_mode("hidden")
    assert island._current_mode == "hidden"
    assert island.animator.w.target == 184.0
    assert island.animator.h.target == 0.0

    # 2. Test Compact mode
    island.set_mode("compact")
    assert island._current_mode == "compact"
    assert island.animator.w.target == 288.0
    assert island.animator.h.target == 32.0

    # 3. Test Expanded mode
    island.expand_to_view("chat")
    assert island._current_mode == "expanded"
    assert island._current_view == "chat"
    assert island.animator.w.target == 640.0
    assert island.animator.h.target == 240.0

    # Step physics simulation
    for _ in range(60):
        island.animator.step()
    island._on_anim_tick()

    island.collapse_to_compact()
    assert island._current_mode == "compact"

    island.close()


def test_coucou_launch_greeting_ceremony(qapp):
    """Verifies that the Coucou launch greeting expands in 640x150 space and collapses to compact."""
    from gui.island.island import CoucouIslandWidget

    island = CoucouIslandWidget()
    island.show()

    # Trigger launch greeting
    island.play_startup_greeting()
    assert island._is_greeting_active is True
    assert island._locked_view == "greeting"
    assert island._current_view == "greeting"
    assert island._current_mode == "expanded"
    assert island.animator.w.target == 640.0
    assert island.animator.h.target == 150.0
    assert island.header.isHidden() is True
    assert island.character.isHidden() is True

    # Ceremony finishes -> smooth start: full overview holds Mochi visibly...
    island.view_greeting.skip()
    island._on_greeting_completed()
    assert island._is_greeting_active is False
    assert island._locked_view is None
    assert island._current_view == "overview"
    assert island._current_mode == "expanded"
    assert island.header.isHidden() is False
    assert island.character.isHidden() is False

    # ...then eases home on its own.
    island._settle_after_greeting()
    assert island._current_mode == "compact"

    # ...but never yanks the user away if they already took over.
    island.expand_to_view("chat")
    island._settle_after_greeting()
    assert island._current_view == "chat"
    assert island._current_mode == "expanded"

    island.close()


def test_chat_active_view_lock_survives_worker_and_fsm(qapp):
    """Verifies that activeView == 'chat' locks the view and prevents background FSM transitions from returning to Home."""
    from gui.island.island import CoucouIslandWidget

    island = CoucouIslandWidget()
    island.show()

    # User enters chat
    island.expand_to_view("chat")
    assert island._current_view == "chat"
    assert island._locked_view == "chat"
    assert island._auto_collapse_timer.isActive() is False

    # Simulate user typing and pressing Enter
    island.view_chat.input_field.setText("hello jarvis")
    submitted = []
    island.view_chat.message_submitted.connect(lambda t: submitted.append(t))
    island.view_chat._on_submit()
    assert submitted == ["hello jarvis"]
    assert island.view_chat.input_field.text() == ""

    # FSM state transitions caused by background task worker:
    # 1. State changes to THINKING
    island.fsm.transition_to(IslandState.THINKING)
    assert island._current_view == "chat"
    assert island._locked_view == "chat"
    assert island.character._current_state == "thinking"

    # 2. State changes to SPEAKING
    island.fsm.transition_to(IslandState.SPEAKING)
    assert island._current_view == "chat"
    assert island._locked_view == "chat"
    assert island.character._current_state == "speaking"

    # 3. Worker finishes and state returns to READY / COMPACT
    island.fsm.transition_to(IslandState.COMPACT)
    assert island._current_view == "chat"
    assert island._locked_view == "chat"
    assert island._current_mode == "expanded"

    # Auto-collapse timeout should NOT collapse chat
    island._on_auto_collapse_timeout()
    assert island._current_view == "chat"
    assert island._current_mode == "expanded"

    # Only explicit navigation away unlocks chat
    island.set_view("overview")
    assert island._locked_view is None
    assert island._current_view == "overview"

    island.close()


def test_minimal_companion_home_view(qapp):
    """Verifies that the Home view is a minimal companion card and compact status is minimal."""
    from gui.island.island import CoucouIslandWidget

    island = CoucouIslandWidget()
    island.show()

    # Compact pill status
    assert island.compact_status.text() == "JARVIS"

    # Overview companion card has quick chat action and no dashboard clutter
    overview = island.view_overview
    assert overview.who_name.text() == "JARVIS"
    assert overview.tool_tag.text() == "Companion"
    assert overview.ask_btn is not None

    # Clicking Ask JARVIS switches to Chat
    island.expand_to_view("overview")
    overview.ask_btn.click()
    assert island._current_view == "chat"
    assert island._locked_view == "chat"

    island.close()


def test_jarvis_emote_love_state_machine_and_trigger(qapp):
    """Verifies EMOTE_LOVE in IslandState, affection pattern matching, and pop/float/reversion lifecycle."""
    from gui.island.character import JarvisCharacter, is_affection_or_praise
    from gui.island.state_machine import IslandState, IslandStateMachine
    from gui.island.island import CoucouIslandWidget

    # 1. State Machine Enum Check
    assert IslandState.EMOTE_LOVE.value == "emote_love"

    # 2. Contextual Affection Pattern Matching
    assert is_affection_or_praise("I love you") is True
    assert is_affection_or_praise("thank you Jarvis") is True
    assert is_affection_or_praise("you are awesome") is True
    assert is_affection_or_praise("good job") is True
    assert is_affection_or_praise("thanks buddy") is True
    assert is_affection_or_praise("tum bahut acche ho") is True
    assert is_affection_or_praise("well done") is True
    assert is_affection_or_praise("open chrome") is False
    assert is_affection_or_praise("system status") is False

    # 3. Character Widget Love Emote Trigger & Reversion
    char = JarvisCharacter(size=36)
    char.set_system_state("listening")
    assert char._current_state == "listening"

    # Trigger Love Emote
    char.trigger_love_emote(duration_s=1.8)
    assert char._is_emote_active is True
    assert char._current_state == "emote_love"
    assert char._eye_shape == "love_hearts"
    assert char._emote_previous_state == "listening"
    assert len(char._floating_hearts) > 0

    # Fast forward tick to expire duration
    char._emote_start_time -= 2.0
    char._on_tick()

    # Must automatically revert to previous state (LISTENING)
    assert char._is_emote_active is False
    assert char._current_state == "listening"
    char.close()

    # 4. Island Widget Love Emote Integration
    island = CoucouIslandWidget()
    island.show()
    island.trigger_love_emote(duration_s=1.8)
    assert island.character._current_state == "emote_love"
    assert island.compact_status.text() == "♥ JARVIS"

    # Fast forward expiration
    island.character._emote_start_time -= 2.0
    island.character._on_tick()
    assert island.character._is_emote_active is False
    island.close()


def test_dynamic_island_top_right_controls_and_mic_pipeline(qapp, jarvis_gui_core):
    """Verifies Criteria 1, 2, 3:
    1. MIC ON -> actual microphone capture starts.
    2. MIC OFF -> actual microphone capture stops.
    3. MIC OFF -> Chat typing still works.
    """
    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    header = window.island.header
    assert header.mic_btn is not None
    assert header.speaker_btn is not None
    assert header.gear_btn is not None
    assert header.close_btn is not None

    # Initial state
    assert window.controller.micEnabled is True
    assert "ON" in header.mic_btn.toolTip()

    # 1. MIC OFF via button click
    header.mic_btn.click()
    assert window.controller.micEnabled is False
    assert window.controller.audioState == "muted"
    assert "OFF" in header.mic_btn.toolTip()
    # Actual audio pipeline stopped
    assert window.view_chat._voice_thread is None

    # 2. MIC OFF -> Chat typing still works!
    test_msg = "hello from chat"
    window.island.expand_to_view("chat")
    window.island.view_chat.input_field.setText(test_msg)
    assert window.island.view_chat.input_field.text() == test_msg
    # Submitting message still executes background worker
    window.island.view_chat._handle_send()
    assert window._active_worker is not None

    # 3. MIC ON via toggle_mic
    window.toggle_mic()
    assert window.controller.micEnabled is True
    assert window.controller.audioState == "capturing"
    assert "ON" in header.mic_btn.toolTip()

    window.close()


def test_dynamic_island_speaker_tts_mute(qapp, jarvis_gui_core):
    """Verifies Criterion 4:
    Speaker OFF -> JARVIS does not speak (TTS muted) but STT / mic still works.
    """
    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    header = window.island.header
    assert window.controller.speakerEnabled is True
    assert "ON" in header.speaker_btn.toolTip()

    # Toggle speaker OFF
    header.speaker_btn.click()
    assert window.controller.speakerEnabled is False
    assert window.view_chat.is_muted is True
    assert window.controller.ttsState == "muted"
    assert "MUTED" in header.speaker_btn.toolTip()

    # Microphone is still independent and enabled
    assert window.controller.micEnabled is True

    # Re-enable speaker
    header.speaker_btn.click()
    assert window.controller.speakerEnabled is True
    assert window.view_chat.is_muted is False
    assert window.controller.ttsState == "idle"

    window.close()


def test_dynamic_island_settings_lifecycle_and_return(qapp, jarvis_gui_core):
    """Verifies Criteria 5 & 6:
    5. Settings open -> application remains alive.
    6. Settings close -> previous view returns. Never terminates JARVIS.
    """
    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    island = window.island
    # Navigate to chat first
    island.expand_to_view("chat")
    assert island._current_view == "chat"

    # Open Settings via gear button
    island.header.gear_btn.click()
    assert island._current_view == "settings"
    assert island._previous_view == "chat"
    assert window.isVisible() is True  # Application remains alive

    # Close Settings via Done button
    island.view_settings.done_btn.click()
    # Must return to previous active view (chat)
    assert island._current_view == "chat"
    assert window.isVisible() is True  # Application remains alive

    # Open Settings from overview
    island.set_view("overview")
    island.header.gear_btn.click()
    assert island._current_view == "settings"
    assert island._previous_view == "overview"

    # Close Settings via gear button toggle
    island.header.gear_btn.click()
    assert island._current_view == "overview"
    assert island._current_mode == "compact"
    assert window.isVisible() is True

    window.close()


def test_dynamic_island_close_button_collapses_to_compact_then_hides(qapp, jarvis_gui_core):
    """Verifies the reference Coucou loop (Criteria 7 & 8):
    7. Close (×) -> compact pill (mini bot + JARVIS + grid), never exits.
    8. Idle with nothing running -> thin top-edge line; notch hover peeks back.
    Backend remains alive throughout.
    """
    from unittest.mock import patch
    from PySide6.QtCore import QPoint

    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    island = window.island
    island.set_mode("expanded")
    assert island._current_mode == "expanded"

    # Click Close (×) -> compact pill with plain "JARVIS" status
    island.header.close_btn.click()
    assert island._current_mode == "compact"
    assert island.compact_status.text() == "JARVIS"
    assert window._is_anchor_mode is False
    assert window.isVisible() is True
    assert window.width() == 720
    assert window.height() == 320
    assert window.core is not None
    assert window.fsm.current_state == IslandState.COMPACT

    # Idle timeout with nothing running -> thin top-edge line (cursor far away)
    with patch("PySide6.QtGui.QCursor.pos", return_value=QPoint(1000, 900)):
        island._on_auto_collapse_timeout()
    assert island._current_mode == "hidden"

    # Controller idle path agrees: COMPACT + quiet -> IDLE_HIDDEN
    island.set_mode("compact")
    window.controller._last_active_time -= 10
    window.controller._check_idle_timeout()
    assert window.fsm.current_state == IslandState.IDLE_HIDDEN
    assert island._current_mode == "hidden"

    # Notch hover peeks back out; descending reaches the pill; click reopens home
    island.peek_out()
    assert island._current_mode == "peek"
    island.set_mode("compact")
    assert island._current_mode == "compact"
    window.expand_island("overview")
    assert island._current_mode == "expanded"
    assert window._is_anchor_mode is False
    assert window.width() == 720
    assert window.height() == 320

    window.close()


def test_floating_anchor_drag_and_click_detection_and_reset(qapp, jarvis_gui_core, tmp_path):
    """Verifies:
    1. Movement > 8px enters DRAG_ANCHOR mode and moves anchor without opening Island.
    2. Pointer click (movement <= 8px) expands the Dynamic Island.
    3. Boundary clamping keeps >= 28px visible on-screen.
    4. Position persistence across restarts via AnchorPositionManager.
    5. 'Reset JARVIS Position' restores default top-center position.
    6. Permanent anchor remains visible across all system states.
    """
    from PySide6.QtCore import QEvent, QPoint, QRect, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from gui.island.position_manager import AnchorPositionManager

    storage = str(tmp_path / "test_anchor_pos.json")
    pos_mgr = AnchorPositionManager(storage_path=storage)

    window = JarvisMainWindow(jarvis_gui_core)
    window.pos_manager = pos_mgr
    window.show()

    # 1. Start in collapsed anchor mode
    window.collapse_to_anchor()
    assert window._is_anchor_mode is True
    assert window.width() == window.anchor_size
    assert window.height() == window.anchor_size
    assert window.isVisible() is True

    # 2. Click vs Drag Detection: Dragging (> 8px)
    initial_pos = window.pos()
    press_event = QMouseEvent(
        QEvent.MouseButtonPress,
        QPointF(20, 20),
        QPointF(initial_pos.x() + 20, initial_pos.y() + 20),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier
    )
    window.eventFilter(window, press_event)
    assert window._is_dragging_anchor is False

    # Move by 30 pixels (> 8px)
    move_event = QMouseEvent(
        QEvent.MouseMove,
        QPointF(50, 50),
        QPointF(initial_pos.x() + 50, initial_pos.y() + 50),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier
    )
    window.eventFilter(window, move_event)
    assert window._is_dragging_anchor is True
    assert window.fsm.current_state == IslandState.DRAG_ANCHOR

    # Release after dragging
    release_event = QMouseEvent(
        QEvent.MouseButtonRelease,
        QPointF(50, 50),
        QPointF(initial_pos.x() + 50, initial_pos.y() + 50),
        Qt.LeftButton,
        Qt.NoButton,
        Qt.NoModifier
    )
    window.eventFilter(window, release_event)
    assert window._is_dragging_anchor is False
    # Still in anchor mode! Did NOT expand on drag!
    assert window._is_anchor_mode is True

    # Verify position was saved to file
    assert os.path.exists(storage)

    # 3. Click detection (movement <= 8px): Expands Dynamic Island
    press_click = QMouseEvent(
        QEvent.MouseButtonPress,
        QPointF(20, 20),
        QPointF(window.pos().x() + 20, window.pos().y() + 20),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier
    )
    window.eventFilter(window, press_click)

    release_click = QMouseEvent(
        QEvent.MouseButtonRelease,
        QPointF(22, 22),  # only moved 2 pixels
        QPointF(window.pos().x() + 22, window.pos().y() + 22),
        Qt.LeftButton,
        Qt.NoButton,
        Qt.NoModifier
    )
    window.eventFilter(window, release_click)
    # Click expanded the island!
    assert window._is_anchor_mode is False
    assert window.width() == 720
    assert window.height() == 320

    # 4. Test Clamping Logic:
    screen_geo = QRect(0, 0, 1920, 1080)
    # Drag far off left edge -> clamped to -36 (64 - 28 = 36)
    far_left = pos_mgr.clamp_position(QPoint(-500, 100), screen_geo, anchor_size=64, min_visible=28)
    assert far_left.x() == -36
    # Drag far off right edge -> clamped so 28px visible
    far_right = pos_mgr.clamp_position(QPoint(3000, 100), screen_geo, anchor_size=64, min_visible=28)
    assert far_right.x() == 1920 - 28

    # 5. Intelligent Expansion Geometry:
    # Near top edge -> expands downward
    top_anchor = QPoint(900, 10)
    geo_down = pos_mgr.calculate_expanded_geometry(top_anchor, screen_geo, 64)
    assert geo_down.y() == 10  # expands downward

    # Near bottom edge -> expands upward
    bot_anchor = QPoint(900, 1000)
    geo_up = pos_mgr.calculate_expanded_geometry(bot_anchor, screen_geo, 64)
    assert geo_up.y() < 1000  # expands upward

    # 6. Reset Position in Settings restores default TOP-CENTER:
    screen = pos_mgr.get_active_screen(window.anchor_pos)
    active_geo = screen.availableGeometry() if screen else screen_geo
    window.reset_anchor_position()
    assert window.anchor_pos.y() == 8
    assert abs(window.anchor_pos.x() - (active_geo.width() - window.anchor_size) // 2) <= 2

    # 7. Permanent anchor remains visible across all states
    for state in ["ready", "listening", "thinking", "speaking", "working", "success", "error"]:
        window.set_system_state(state)
        assert window.isVisible() is True
        assert window.character.isVisible() is True

    window.close()


def test_chat_persistence_under_background_events(qapp, jarvis_gui_core):
    """Verifies Criteria 9 & 10:
    9. Chat remains Chat after sending a message and receiving a response.
    10. No backend/STT/TTS/audio event can unexpectedly navigate Chat to Home.
    """
    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    island = window.island
    island.expand_to_view("chat")
    assert island._current_view == "chat"
    assert island._locked_view == "chat"

    # Background audio / STT / system state events occur
    window.set_system_state("listening", details="Listening...")
    assert island._current_view == "chat"
    assert island.character._current_state == "listening"

    window.set_system_state("thinking", details="Analyzing...")
    assert island._current_view == "chat"
    assert island.character._current_state == "thinking"

    window.set_system_state("speaking", details="Hello!")
    assert island._current_view == "chat"
    assert island.character._current_state == "speaking"

    window.set_system_state("ready")
    assert island._current_view == "chat"
    assert island.character._current_state == "idle"

    # Auto collapse timeout check: Chat never auto-collapses
    window.controller._check_idle_timeout()
    assert island._current_view == "chat"
    assert island._current_mode == "expanded"

    window.close()


def test_escape_key_and_no_termination_invariant(qapp, jarvis_gui_core):
    """Verifies Criteria 11 & 12:
    11. Esc collapses the Island but never exits the application.
    12. No UI action terminates JARVIS process unless user explicitly selects Exit JARVIS from tray.
    """
    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    island = window.island
    island.expand_to_view("overview")
    assert island._current_mode == "expanded"

    # Esc collapses expanded Island to compact
    island.collapse_on_escape()
    assert island._current_mode == "compact"
    assert window.isVisible() is True

    # Esc again when already compact does not exit
    island.collapse_on_escape()
    assert window.isVisible() is True

    # 9 Independent Controller states verified
    ctrl = window.controller
    assert hasattr(ctrl, "micEnabled")
    assert hasattr(ctrl, "speakerEnabled")
    assert hasattr(ctrl, "activeView")
    assert hasattr(ctrl, "islandVisible")
    assert hasattr(ctrl, "islandExpanded")
    assert hasattr(ctrl, "audioState")
    assert hasattr(ctrl, "sttState")
    assert hasattr(ctrl, "ttsState")
    assert hasattr(ctrl, "characterState")

    window.close()


def test_dynamic_island_hides_when_nothing_running_and_peeks_on_notch_hover(qapp, jarvis_gui_core):
    """Verifies that:
    1. Dynamic Island hides away to top edge when nothing is running and idle.
    2. Dynamic Island peeks out when hovering the Windows top-center notch.
    3. Moving cursor away slides it back to hidden.
    4. Entering or clicking the peeking notch expands to compact/overview.
    5. Running tasks (speaking, listening, working) or Chat lock prevent auto-hiding.
    """
    from unittest.mock import patch
    from PySide6.QtCore import QPoint
    from gui.island.island import CoucouIslandWidget

    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    island = window.island
    ctrl = window.controller
    fsm = window.fsm

    # 1. Verify Peek mode geometry directly on CoucouIslandWidget
    island.set_mode("peek")
    assert island._current_mode == "peek"
    assert island.animator.w.target == 210.0
    assert island.animator.h.target == 16.0
    assert island.animator.bot_d.target == 16.0
    assert island.compact_container.isHidden() is True
    assert island.expanded_container.isHidden() is True

    # 2. Test FSM transition to IDLE_PEEK triggers peek_out on island
    island.set_mode("hidden")
    assert island._current_mode == "hidden"
    fsm.transition_to(IslandState.IDLE_PEEK, reason="notch_hover")
    assert island._current_mode == "peek"

    # 3. Test Inactivity Auto-Hide when nothing is running
    fsm.transition_to(IslandState.COMPACT, reason="user_return")
    assert fsm.current_state == IslandState.COMPACT
    ctrl.touch_activity()
    ctrl._last_active_time = ctrl._last_active_time - (ctrl.auto_collapse_delay_sec + 1.0)
    ctrl._check_idle_timeout()
    assert fsm.current_state == IslandState.IDLE_HIDDEN
    assert island._current_mode == "hidden"

    # 4. Inactivity Auto-Hide is BLOCKED when something IS running
    fsm.transition_to(IslandState.COMPACT, reason="ready")
    ctrl.set_tts_state("speaking")
    ctrl._last_active_time = ctrl._last_active_time - (ctrl.auto_collapse_delay_sec + 1.0)
    ctrl._check_idle_timeout()
    # TTS speaking prevents hide-away
    assert fsm.current_state == IslandState.COMPACT
    ctrl.set_tts_state("idle")

    # Also blocked when STT is listening
    ctrl.set_stt_state("listening")
    ctrl._last_active_time = ctrl._last_active_time - (ctrl.auto_collapse_delay_sec + 1.0)
    ctrl._check_idle_timeout()
    assert fsm.current_state == IslandState.COMPACT
    ctrl.set_stt_state("idle")

    # 5. Cursor Proximity / Notch Hover Detection on Windows screen
    fsm.transition_to(IslandState.IDLE_HIDDEN, reason="start_hidden")
    assert fsm.current_state == IslandState.IDLE_HIDDEN
    assert island._current_mode == "hidden"

    screen = ctrl.get_active_screen()
    geo = screen.availableGeometry()
    center_x = geo.x() + geo.width() // 2
    top_y = geo.y()

    # Move cursor to top-center notch (y=top_y + 4, x=center_x)
    notch_hover_pos = QPoint(center_x, top_y + 4)
    with patch("gui.island.controller.QCursor.pos", return_value=notch_hover_pos):
        ctrl._check_cursor_proximity()
        assert fsm.current_state == IslandState.IDLE_PEEK
        assert island._current_mode == "peek"

    # Cursor moves away from notch down the screen (y=top_y + 120, x=center_x)
    away_pos = QPoint(center_x, top_y + 120)
    with patch("gui.island.controller.QCursor.pos", return_value=away_pos):
        ctrl._check_cursor_proximity()
        assert fsm.current_state == IslandState.IDLE_HIDDEN
        assert island._current_mode == "hidden"

    # Cursor hovers notch again -> peeks out
    with patch("gui.island.controller.QCursor.pos", return_value=notch_hover_pos):
        ctrl._check_cursor_proximity()
        assert fsm.current_state == IslandState.IDLE_PEEK

    # Cursor enters deeper into peeking notch (y=top_y + 26) -> expands to compact
    deeper_pos = QPoint(center_x, top_y + 26)
    with patch("gui.island.controller.QCursor.pos", return_value=deeper_pos):
        ctrl._check_cursor_proximity()
        assert fsm.current_state == IslandState.COMPACT

    # 6. Widget Native Enter & Leave Events
    island.set_mode("hidden")
    island.enterEvent(None)
    assert island._current_mode == "peek"

    island.leaveEvent(None)
    assert island._current_mode == "hidden"

    window.close()


def test_hitbox_dimensions_separation_and_click_through(qapp, jarvis_gui_core):
    """Verifies:
    1. Separation of visualBounds, interactionBounds, windowBounds, expandedIslandBounds.
    2. Collapsed anchor is genuinely compact (44x44), not oversized (720x320).
    3. Click-through outside interactionBounds via WM_NCHITTEST (HTTRANSPARENT).
    4. Only visible island/anchor captures clicks (HTCLIENT).
    5. Underlying browser/desktop is not blocked by transparent overlays.
    """
    import ctypes
    from ctypes import wintypes
    from PySide6.QtCore import QPoint, QRect
    from gui.app import JarvisMainWindow

    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    # 1. In collapsed anchor mode:
    window.collapse_to_anchor()
    assert window._is_anchor_mode is True
    assert window.width() == 44
    assert window.height() == 44
    assert window.window_bounds().width() == 44
    assert window.window_bounds().height() == 44

    # Dimensions separation
    vb = window.visual_bounds()
    ib = window.interaction_bounds()
    wb = window.window_bounds()
    eib = window.expanded_island_bounds()

    assert vb.width() <= 44 and vb.height() <= 44
    assert ib.width() <= 44 and ib.height() <= 44
    assert eib.width() == 720 and eib.height() == 320

    # 2. Test Win32 hit-testing inside anchor (HTCLIENT = 1):
    center_pt = window.mapToGlobal(QPoint(22, 22))
    lParam_in = (center_pt.y() << 16) | (center_pt.x() & 0xFFFF)
    msg_in = wintypes.MSG(hwnd=int(window.winId()), message=132, wParam=0, lParam=lParam_in)
    handled_in, res_in = window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg_in))
    assert handled_in is True
    assert res_in == 1  # HTCLIENT: JARVIS captures click!

    # 3. Test expanded mode dimensions and click-through on wings:
    window.expand_island("overview")
    assert window._is_anchor_mode is False
    assert window.width() == 720
    assert window.height() == 320

    exp_vb = window.visual_bounds()
    exp_ib = window.interaction_bounds()
    assert exp_vb.width() == 640
    # Inside island (x=360, y=80) -> HTCLIENT
    on_island_pt = window.mapToGlobal(QPoint(360, 80))
    lParam_island = (on_island_pt.y() << 16) | (on_island_pt.x() & 0xFFFF)
    msg_island = wintypes.MSG(hwnd=int(window.winId()), message=132, wParam=0, lParam=lParam_island)
    handled_isl, res_isl = window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg_island))
    assert handled_isl is True
    assert res_isl == 1  # HTCLIENT

    # Left transparent wing (x=10, y=80) -> HTTRANSPARENT (-1)
    wing_pt = window.mapToGlobal(QPoint(10, 80))
    lParam_wing = (wing_pt.y() << 16) | (wing_pt.x() & 0xFFFF)
    msg_wing = wintypes.MSG(hwnd=int(window.winId()), message=132, wParam=0, lParam=lParam_wing)
    handled_wing, res_wing = window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg_wing))
    assert handled_wing is True
    assert res_wing == -1  # HTTRANSPARENT: Click passes straight to browser underneath!

    # Bottom transparent area (x=360, y=280) when overview height is ~160 -> HTTRANSPARENT (-1)
    bottom_pt = window.mapToGlobal(QPoint(360, 280))
    lParam_bottom = (bottom_pt.y() << 16) | (bottom_pt.x() & 0xFFFF)
    msg_bottom = wintypes.MSG(hwnd=int(window.winId()), message=132, wParam=0, lParam=lParam_bottom)
    handled_bot, res_bot = window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg_bottom))
    assert handled_bot is True
    assert res_bot == -1  # HTTRANSPARENT: Click passes straight to browser underneath!

    window.close()


def test_top_right_header_buttons_hit_testing_and_dpi_scaling(qapp, jarvis_gui_core):
    """Verifies that all 4 top-right buttons (Mic, Speaker, Settings, Close) are clickable,
    accept clicks under both standard (1.0x) and high-DPI (1.5x) display scaling,
    and trigger their respective actions cleanly.
    """
    import ctypes
    from ctypes import wintypes
    from PySide6.QtCore import QPoint
    from gui.app import JarvisMainWindow

    window = JarvisMainWindow(jarvis_gui_core)
    window.expand_island("overview")
    window.show()

    header = window.island.header

    # Step animations so buttons are in their final visual layout
    for _ in range(50):
        window.island._on_anim_tick()

    buttons = [
        ("mic", header.mic_btn),
        ("speaker", header.speaker_btn),
        ("gear", header.gear_btn),
        ("close", header.close_btn),
    ]

    for name, btn in buttons:
        btn_center = QPoint(btn.width() // 2, btn.height() // 2)
        local_pt = btn.mapTo(window, btn_center)
        global_pt = window.mapToGlobal(local_pt)

        # 1. Verify point is inside interaction_bounds
        assert window.interaction_bounds().contains(local_pt) is True, f"{name} button at {local_pt} not in interaction bounds {window.interaction_bounds()}"

        # 2. Verify nativeEvent returns HTCLIENT (1) for logical global coordinates
        lParam_logical = (global_pt.y() << 16) | (global_pt.x() & 0xFFFF)
        msg_logical = wintypes.MSG(hwnd=int(window.winId()), message=132, wParam=0, lParam=lParam_logical)
        handled_log, res_log = window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg_logical))
        assert handled_log is True
        assert res_log == 1, f"{name} button WM_NCHITTEST returned {res_log} instead of HTCLIENT (1)"

        # 3. Verify nativeEvent returns HTCLIENT (1) for 1.5x DPI scaled physical coordinates
        window.devicePixelRatioF = lambda: 1.5
        phys_x = int(global_pt.x() * 1.5)
        phys_y = int(global_pt.y() * 1.5)
        lParam_dpi = (phys_y << 16) | (phys_x & 0xFFFF)
        msg_dpi = wintypes.MSG(hwnd=int(window.winId()), message=132, wParam=0, lParam=lParam_dpi)
        handled_dpi, res_dpi = window.nativeEvent(b"windows_generic_MSG", ctypes.addressof(msg_dpi))
        assert handled_dpi is True
        assert res_dpi == 1, f"{name} button with 1.5x DPI returned {res_dpi} instead of HTCLIENT (1)"
        window.devicePixelRatioF = lambda: 1.0

    # 4. Verify clicking Mic toggles state
    initial_mic = window.controller.micEnabled
    header.mic_btn.click()
    assert window.controller.micEnabled != initial_mic

    # 5. Verify clicking Speaker toggles state
    initial_spk = window.controller.speakerEnabled
    header.speaker_btn.click()
    assert window.controller.speakerEnabled != initial_spk

    # 6. Verify clicking Settings toggles settings view
    header.gear_btn.click()
    assert window.island._current_view == "settings"

    # 7. Verify clicking Close collapses to the compact pill (never anchor, never exit)
    header.close_btn.click()
    assert window.island._current_mode == "compact"
    assert window._is_anchor_mode is False
    assert window.island.compact_status.text() == "JARVIS"

    window.close()


def test_coucou_header_tooltips_styling_and_palette(jarvis_gui_core):
    """
    Verify that top-right header controls (Mic, Speaker, Settings, Close) have clear
    tooltips and that QToolTip palette & styles enforce dark glass styling with crisp
    light text (avoiding black-on-black illegible rectangles).
    """
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication

    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    header = window.island.header

    # 1. Verify buttons have meaningful tooltips
    assert "Settings" in header.gear_btn.toolTip()
    assert "Microphone" in header.mic_btn.toolTip()
    assert "Speaker" in header.speaker_btn.toolTip()
    assert "Hide" in header.close_btn.toolTip()

    # 2. Verify global application tooltip palette has high contrast
    palette = QApplication.palette()
    assert palette.color(QPalette.ToolTipBase).name().lower() == "#141518"
    assert palette.color(QPalette.ToolTipText).name().lower() == "#f5f6f8"

    # 3. Verify header button styles contain QToolTip styling
    gear_style = header.gear_btn.styleSheet()
    assert "QToolTip" in gear_style
    assert "#141518" in gear_style
    assert "#f5f6f8" in gear_style

    close_style = header.close_btn.styleSheet()
    assert "QToolTip" in close_style
    assert "#141518" in close_style
    assert "#f5f6f8" in close_style

    window.close()

