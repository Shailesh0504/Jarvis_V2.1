# tests/test_mochi_thinking_dots_lifecycle.py
"""Acceptance test suite for Mochi Thinking Dots Lifecycle and State Management.

Verifies:
1. Normal response: THINKING shows dots -> Response received clears THINKING & stops dots immediately.
2. Long response: Dots animate strictly during processing; stop immediately upon answer delivery.
3. TTS: Speaking state has active speaking face/waveform and ZERO thinking dots.
4. Error path: THINKING -> ERROR stops thinking dots immediately.
5. Cancel path: Active request cancelled -> IDLE stops thinking dots immediately.
6. Sequential requests: Fresh thinking state on each turn; zero stale animation.
7. Rapid requests: Clean cancellation of in-flight workers; single authoritative state.
"""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import time
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])

from main import create_jarvis
from gui.app import JarvisMainWindow, TaskWorker
from gui.island.character import JarvisCharacter


@pytest.fixture(scope="session")
def qapp():
    return _app


@pytest.fixture
def jarvis_gui_core(tmp_path):
    db_file = os.path.join(tmp_path, "gui_dots_test.db").replace("\\", "/")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(f"""
system:
  name: "JARVIS_DOTS_TEST"
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


def test_thinking_dots_only_during_thinking(qapp):
    """Character invariant: dots badge is active strictly during THINKING, never during SPEAKING or IDLE."""
    char = JarvisCharacter(size=36)
    
    # Idle / Ready: clean face, zero dots badge
    char.set_system_state("ready")
    assert char._current_state == "idle"
    assert char.badge_kind is None

    # Thinking: active purple dots badge
    char.set_system_state("thinking")
    assert char._current_state == "thinking"
    assert char.badge_kind == "dots"

    # Speaking: mouth active, NO dots badge
    char.set_system_state("speaking")
    assert char._current_state == "speaking"
    assert char.badge_kind is None

    # Error: error badge, NOT dots
    char.set_system_state("error")
    assert char.badge_kind == "dot"

    # Idle return
    char.set_system_state("idle")
    assert char.badge_kind is None


def test_acceptance_1_normal_response(qapp, jarvis_gui_core):
    """TEST 1 — NORMAL RESPONSE:
    Send query -> THINKING ON (dots active) -> Worker finishes -> THINKING OFF -> NO thinking dots.
    """
    window = JarvisMainWindow(jarvis_gui_core)
    window.show()
    
    # 1. Start message
    window._start_message_worker("hello", source="gui")
    assert window._current_state == "thinking"
    assert window.character._current_state == "thinking"
    assert window.character.badge_kind == "dots"

    # 2. Wait for worker to finish
    if window._active_worker:
        window._active_worker.wait(1000)
    qapp.processEvents()

    # 3. Thinking must be cleared immediately and dots must be gone
    assert window.character._current_state != "thinking"
    assert window.character.badge_kind != "dots"
    window.close()


def test_acceptance_2_long_response(qapp, jarvis_gui_core, monkeypatch):
    """TEST 2 — LONG RESPONSE:
    Simulates a multi-second execution. Dots animate during processing.
    When response arrives, dots stop immediately.
    """
    def _slow_process(*args, **kwargs):
        time.sleep(0.15)
        return "Quantum mechanics is..."
    monkeypatch.setattr(jarvis_gui_core, "process_input", _slow_process)

    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    window._start_message_worker("explain quantum mechanics", source="gui")
    assert window._current_state == "thinking"
    assert window.character.badge_kind == "dots"
    assert window._active_worker.isRunning()

    # Worker is still in thinking phase
    assert window.character.badge_kind == "dots"

    # Wait for worker thread to finish
    if window._active_worker:
        window._active_worker.wait(1000)
    qapp.processEvents()

    # Dots stopped immediately upon completion
    assert window.character._current_state != "thinking"
    assert window.character.badge_kind != "dots"
    window.close()


def test_acceptance_3_tts_speaking_no_dots(qapp, jarvis_gui_core):
    """TEST 3 — TTS:
    Response arrives and TTS starts -> Mochi is SPEAKING -> NOT THINKING -> ZERO dots.
    """
    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    window.set_system_state("thinking")
    assert window.character.badge_kind == "dots"

    # Transition to speaking
    window.set_system_state("speaking", details="Speaking final response")
    assert window._current_state == "speaking"
    assert window.character._current_state == "speaking"
    # CRITICAL: SPEAKING MUST NEVER SHOW THINKING DOTS
    assert window.character.badge_kind is None

    # TTS ends
    window._on_tts_speaking_state_changed(False)
    qapp.processEvents()
    assert window.character._current_state == "idle"
    assert window.character.badge_kind is None
    window.close()


def test_acceptance_4_error_stops_dots(qapp, jarvis_gui_core):
    """TEST 4 — ERROR:
    Request errors out -> THINKING -> ERROR -> Dots stop immediately.
    """
    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    window.set_system_state("thinking")
    assert window.character.badge_kind == "dots"

    # Force error
    window.set_system_state("error", details="Network connection failed")
    assert window._current_state == "error"
    assert window.character._current_state == "error"
    assert window.character.badge_kind != "dots"
    window.close()


def test_acceptance_5_cancel_stops_dots(qapp, jarvis_gui_core):
    """TEST 5 — CANCEL:
    Cancel active request -> THINKING -> IDLE -> Dots stop immediately.
    """
    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    window._start_message_worker("long running process", source="gui")
    assert window._current_state == "thinking"
    assert window.character.badge_kind == "dots"

    # User cancels
    window.cancel_current_task()
    qapp.processEvents()

    assert window._current_state == "ready"
    assert window.character._current_state == "idle"
    assert window.character.badge_kind is None
    window.close()


def test_acceptance_6_second_request(qapp, jarvis_gui_core):
    """TEST 6 — SECOND REQUEST:
    Request 1 completes (thinking -> response -> idle).
    Request 2 starts (idle -> thinking -> response -> idle).
    No stale animation or lingering state.
    """
    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    # Request 1
    window._start_message_worker("query 1", source="gui")
    assert window.character.badge_kind == "dots"
    window._on_worker_finished("Jarvis", "reply 1", generation_id=window._active_generation_id)
    qapp.processEvents()
    assert window.character.badge_kind is None

    # Request 2
    window._start_message_worker("query 2", source="gui")
    assert window.character.badge_kind == "dots"
    window._on_worker_finished("Jarvis", "reply 2", generation_id=window._active_generation_id)
    qapp.processEvents()
    assert window.character.badge_kind is None
    window.close()


def test_acceptance_7_rapid_requests(qapp, jarvis_gui_core):
    """TEST 7 — RAPID REQUESTS:
    Multiple requests fired in rapid succession cancel in-flight tasks cleanly.
    Single authoritative thinking state; no lingering animation loops.
    """
    window = JarvisMainWindow(jarvis_gui_core)
    window.show()

    # Rapid burst
    window._start_message_worker("first rapid message", source="gui")
    window._start_message_worker("second rapid message", source="gui")
    window._start_message_worker("third rapid message", source="gui")

    assert window._current_state == "thinking"
    assert window.character.badge_kind == "dots"

    # Only final generation finishes
    window._on_worker_finished("Jarvis", "final answer", generation_id=window._active_generation_id)
    qapp.processEvents()

    assert window.character._current_state != "thinking"
    assert window.character.badge_kind is None
    window.close()
