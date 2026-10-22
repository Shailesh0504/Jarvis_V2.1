# tests/test_home_greeting.py
"""Home greeting context: session/start/context-based, never per-second.

Covers the pure resolver/store plus the overview card locks and the
app wiring (execution success -> All done, new turn -> time reset,
long-idle expand -> Welcome back, startup variants).
"""

from datetime import datetime

import pytest
from PySide6.QtWidgets import QApplication

from gui.island.home_context import (
    HomeKind, HomeStore, LONG_IDLE_SEC, describe_idle,
    resolve_context_greeting, resolve_time_greeting,
)

app = QApplication.instance() or QApplication(["-platform", "offscreen"])


def _at(hour, minute=0):
    return datetime(2026, 9, 14, hour, minute)


def test_time_greeting_mapping():
    assert resolve_time_greeting(_at(8))[0] == "Good Morning, Boss"
    assert resolve_time_greeting(_at(8))[2] == "morning"
    assert resolve_time_greeting(_at(13))[0] == "Good Afternoon, Boss"
    assert resolve_time_greeting(_at(13))[2] == "afternoon"
    assert resolve_time_greeting(_at(19))[0] == "Good Evening, Boss"
    assert resolve_time_greeting(_at(19))[2] == "evening"
    assert resolve_time_greeting(_at(23, 30))[0] == "Working Late, Boss?"
    assert resolve_time_greeting(_at(23, 30))[2] == "night"
    assert resolve_time_greeting(_at(3))[2] == "night"
    # Boundaries mirror DayPart config: 5 / 12 / 17 / 21.
    assert resolve_time_greeting(_at(5))[2] == "morning"
    assert resolve_time_greeting(_at(12))[2] == "afternoon"
    assert resolve_time_greeting(_at(17))[2] == "evening"
    assert resolve_time_greeting(_at(21))[2] == "night"


def test_context_greeting_texts():
    title, sub = resolve_context_greeting(HomeKind.FIRST_STARTUP)
    assert title == "Good to see you, Boss."
    title, sub = resolve_context_greeting(HomeKind.WELCOME_BACK, "20m")
    assert title == "Welcome back, Boss."
    assert "20m" in sub
    title, sub = resolve_context_greeting(HomeKind.TASK_DONE, "chrome")
    assert title == "All done, Boss."
    assert "chrome" in sub
    title, _ = resolve_context_greeting(HomeKind.TASK_DONE, "")
    assert title == "All done, Boss."


def test_describe_idle():
    assert describe_idle(30) == "a moment"
    assert describe_idle(20 * 60) == "20m"
    assert describe_idle(2 * 3600 + 14 * 60) == "2h 14m"
    assert describe_idle(3 * 86400) == "3d"


def test_home_store_first_startup_and_idle(tmp_path):
    store = HomeStore(storage_path=str(tmp_path / "home.json"))
    assert store.is_first_startup() is True
    assert store.idle_seconds() is None
    store.mark_active(timestamp=1000.0)
    assert store.is_first_startup() is False
    assert store.idle_seconds(now=1000.0 + LONG_IDLE_SEC + 5) > LONG_IDLE_SEC
    # Round-trip across instances.
    reloaded = HomeStore(storage_path=str(tmp_path / "home.json"))
    assert reloaded.is_first_startup() is False


@pytest.fixture()
def card():
    from gui.island.views import CoucouOverviewCard
    c = CoucouOverviewCard()
    yield c
    c.close()


def test_task_done_locks_across_show_and_refresh(card):
    card.show_home(HomeKind.TASK_DONE, "chrome")
    assert card.greeting_label.text() == "All done, Boss."
    # showEvent / set_view refresh path must NOT wipe a locked context.
    card.restore_home()
    card.refresh_greeting()
    assert card.greeting_label.text() == "All done, Boss."
    assert "chrome" in card.ticker_text.text()


def test_live_activity_restores_locked_home(card):
    card.show_home(HomeKind.TASK_DONE, "chrome")
    card.set_activity("Thinking", "Analyzing intent...")
    assert card.ticker_text.text() == "Analyzing intent..."
    card.restore_home()
    assert card.greeting_label.text() == "All done, Boss."
    assert "chrome" in card.ticker_text.text()


def test_time_greeting_stable_within_daypart(card):
    card.show_home(HomeKind.TIME)
    first_title = card.greeting_label.text()
    assert first_title in ("Good Morning, Boss", "Good Afternoon, Boss",
                           "Good Evening, Boss", "Working Late, Boss?")
    # Repeated refreshes (expand/show churn) keep the title rock-stable.
    for _ in range(5):
        card.refresh_greeting()
        card.restore_home()
    assert card.greeting_label.text() == first_title


def test_set_activity_contract_unchanged(card):
    card.set_activity("JARVIS", "Processing request", "#00f0ff")
    assert card.who_name.text() == "JARVIS"
    assert card.ticker_text.text() == "Processing request"


# ── app wiring (full window, tmp config) ─────────────────────────────────────
@pytest.fixture()
def gui_core(tmp_path):
    from main import create_jarvis
    db_file = str(tmp_path / "home_test.db").replace("\\", "/")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(f"""
system:
  name: "JARVIS_HOME_TEST"
memory:
  db_path: "{db_file}"
brain:
  llm_provider: "mock"
reminder:
  db_path: "{str(tmp_path / 'home_reminders.db').replace(chr(92), '/')}"
plugins:
  plugin_dir: "plugins"
  auto_load: true
""")
    return create_jarvis(str(cfg_file))


@pytest.fixture()
def window(gui_core, tmp_path, monkeypatch):
    from gui.app import JarvisMainWindow
    from gui.sound_effects import Sound
    monkeypatch.setattr(Sound, "_mixer_ready", lambda: False)
    monkeypatch.setattr(Sound, "_is_headless", False)
    monkeypatch.setattr(Sound, "record_all_plays_for_test", False)
    monkeypatch.setattr("winsound.PlaySound", lambda *a, **k: None, raising=False)
    win = JarvisMainWindow(gui_core)
    win.show()
    # Isolate home persistence per test.
    win._home_store = HomeStore(storage_path=str(tmp_path / "home.json"))
    win._last_welcome_back_at = 0.0
    yield win
    try:
        win.close()
    except Exception:
        pass


def test_execution_success_locks_all_done(window):
    win = window
    win._on_execution_completed_event({
        "success": True, "timestamp": 4242.0,
        "executed_action": "launch_app", "target": "chrome"})
    assert win.island.view_overview.greeting_label.text() == "All done, Boss."
    # Ready restore keeps the locked context (not time).
    win.set_system_state("ready")
    assert win.island.view_overview.greeting_label.text() == "All done, Boss."


def test_new_turn_resets_home_to_time(window, monkeypatch):
    from PySide6.QtCore import QObject, Signal
    win = window
    win.island.view_overview.show_home(HomeKind.TASK_DONE, "chrome")
    assert win.island.view_overview.greeting_label.text() == "All done, Boss."

    class FakeWorker(QObject):
        finished = Signal(str, str, object, int)

        def __init__(self, *a, **k):
            super().__init__()

        def cancel(self):
            pass

        def start(self):
            pass

        def isRunning(self):
            return False

    monkeypatch.setattr("gui.app.TaskWorker", FakeWorker)
    win._start_message_worker("time kya hai", source="gui")
    assert win.island.view_overview.greeting_label.text() != "All done, Boss."


def test_long_idle_expand_welcomes_back(window):
    win = window
    win._home_store.mark_active(timestamp=1000.0)
    # Simulate 20 idle minutes: monkeypatch time for the idle read only.
    import gui.app as app_module
    import time as _time
    real_time = _time.time
    try:
        _time.time = lambda: 1000.0 + 20 * 60
        win._maybe_welcome_back()
    finally:
        _time.time = real_time
    assert win.island.view_overview.greeting_label.text() == "Welcome back, Boss."
    # Second expand in the same span does not re-trigger.
    win.island.view_overview.show_home(HomeKind.TIME)
    try:
        _time.time = lambda: 1000.0 + 21 * 60
        win._maybe_welcome_back()
    finally:
        _time.time = real_time
    assert win.island.view_overview.greeting_label.text() != "Welcome back, Boss."


def test_startup_variants(window, tmp_path):
    from gui.island.home_context import HomeStore
    win = window
    # First startup ever.
    win._home_store = HomeStore(storage_path=str(tmp_path / "fresh.json"))
    win._init_home_greeting()
    assert win.island.view_overview.greeting_label.text() == "Good to see you, Boss."
    # Restart after long idle → welcome back.
    win._home_store = HomeStore(storage_path=str(tmp_path / "idle.json"))
    win._home_store.mark_active(timestamp=1000.0)
    import time as _time
    real_time = _time.time
    try:
        _time.time = lambda: 1000.0 + 60 * 60
        win._init_home_greeting()
    finally:
        _time.time = real_time
    assert win.island.view_overview.greeting_label.text() == "Welcome back, Boss."


def test_dynamic_backend_state_status_line(card):
    """Verifies that the Home card status line dynamically maps real backend states."""
    # 1. Idle home layout starts with full online readiness
    assert card.ticker_text.text() == "● JARVIS is online and ready"

    # 2. Listening
    card.set_backend_state("listening")
    assert card.ticker_text.text() == "● Listening for you"
    assert "22d3ee" in card.who_dot.styleSheet()

    # 3. Thinking
    card.set_backend_state("thinking")
    assert card.ticker_text.text() == "● Thinking..."
    assert "a855f7" in card.who_dot.styleSheet()

    # 4. Working / Executing
    card.set_backend_state("working")
    assert card.ticker_text.text() == "● Working on your request"
    assert "f59e0b" in card.who_dot.styleSheet()

    card.set_backend_state("executing")
    assert card.ticker_text.text() == "● Working on your request"

    # 5. Speaking
    card.set_backend_state("speaking")
    assert card.ticker_text.text() == "● Speaking"
    assert "00f0ff" in card.who_dot.styleSheet()

    # 6. Task completed
    card.set_backend_state("success")
    assert card.ticker_text.text() == "● Task completed"
    assert "10b981" in card.who_dot.styleSheet()

    card.set_backend_state("task_done")
    assert card.ticker_text.text() == "● Task completed"

    # 7. Waiting for you
    card.set_backend_state("waiting_user")
    assert card.ticker_text.text() == "● Waiting for you"
    assert "38bdf8" in card.who_dot.styleSheet()

    card.set_backend_state("question")
    assert card.ticker_text.text() == "● Waiting for you"

    # 8. Returning to ready
    card.set_backend_state("ready")
    assert card.ticker_text.text() == "● Ready"

    # Direct online reset
    card.set_backend_state("ready", details="online")
    assert card.ticker_text.text() == "● JARVIS is online and ready"


def test_window_backend_state_propagation(window):
    """Verifies that main window state transitions update the Home card status line directly."""
    win = window

    win.set_system_state("listening")
    assert win.island.view_overview.ticker_text.text() == "● Listening for you"

    win.set_system_state("thinking")
    assert win.island.view_overview.ticker_text.text() == "● Thinking..."

    win.set_system_state("working")
    assert win.island.view_overview.ticker_text.text() == "● Working on your request"

    win.set_system_state("speaking")
    assert win.island.view_overview.ticker_text.text() == "● Speaking"

    win.set_system_state("success")
    assert win.island.view_overview.ticker_text.text() == "● Task completed"

    win.set_system_state("waiting_user")
    assert win.island.view_overview.ticker_text.text() == "● Waiting for you"

    win.set_system_state("ready")
    assert win.island.view_overview.ticker_text.text() == "● Ready"


def test_home_mic_state_indicator():
    """Verifies that the Home overview card mic indicator correctly displays all 6 requested states."""
    from gui.island.views import CoucouOverviewCard

    card = CoucouOverviewCard()

    # 1. Normal / Ready: 🎙 Ready
    card.set_mic_state("ready")
    assert card.mic_indicator.text() == "🎙 Ready"

    # 2. Wake word detect / Listening: 🎙 Listening...
    card.set_mic_state("listening")
    assert card.mic_indicator.text() == "🎙 Listening..."

    # 3. Processing: ◌ Processing...
    card.set_mic_state("processing")
    assert card.mic_indicator.text() == "◌ Processing..."

    # Also thinking / working maps to processing for mic
    card.set_mic_state("thinking")
    assert card.mic_indicator.text() == "◌ Processing..."

    # 4. Speaking: 🔊 Speaking...
    card.set_mic_state("speaking")
    assert card.mic_indicator.text() == "🔊 Speaking..."

    # 5. Bluetooth mic: 🎙 Bluetooth microphone
    card.set_mic_state("ready", is_bluetooth=True)
    assert card.mic_indicator.text() == "🎙 Bluetooth microphone"

    card.set_mic_state("bluetooth")
    assert card.mic_indicator.text() == "🎙 Bluetooth microphone"

    # 6. Mic unavailable: ⚠ Microphone unavailable
    card.set_mic_state("unavailable")
    assert card.mic_indicator.text() == "⚠ Microphone unavailable"

    card.set_mic_state("muted")
    assert card.mic_indicator.text() == "⚠ Microphone unavailable"


def test_window_mic_state_propagation(window):
    """Verifies that main window state transitions update the Home mic indicator directly."""
    win = window

    win.set_system_state("listening")
    assert win.island.view_overview.mic_indicator.text() == "🎙 Listening..."

    win.set_system_state("thinking")
    assert win.island.view_overview.mic_indicator.text() == "◌ Processing..."

    win.set_system_state("speaking")
    assert win.island.view_overview.mic_indicator.text() == "🔊 Speaking..."

    # When connected to Bluetooth earbuds (e.g. CMF Buds 2 in real dev environment)
    if getattr(win, "_current_mic_is_bt", False):
        win.set_system_state("ready")
        assert win.island.view_overview.mic_indicator.text() == "🎙 Bluetooth microphone"
    else:
        win.set_system_state("ready")
        assert win.island.view_overview.mic_indicator.text() == "🎙 Ready"

    # Explicitly test non-Bluetooth ready transition
    win._current_mic_is_bt = False
    win.set_system_state("ready")
    assert win.island.view_overview.mic_indicator.text() == "🎙 Ready"

    # Explicitly test Bluetooth ready transition
    win._current_mic_is_bt = True
    win.set_system_state("ready")
    assert win.island.view_overview.mic_indicator.text() == "🎙 Bluetooth microphone"

    # Toggling mic off marks it unavailable regardless of device
    win._on_island_mic_toggled(False)
    assert win.island.view_overview.mic_indicator.text() == "⚠ Microphone unavailable"

    # Toggling back on returns to Bluetooth microphone if BT is active
    win._on_island_mic_toggled(True)
    assert win.island.view_overview.mic_indicator.text() == "🎙 Bluetooth microphone"

    # And returns to Ready if non-BT
    win._current_mic_is_bt = False
    win._on_island_mic_toggled(True)
    assert win.island.view_overview.mic_indicator.text() == "🎙 Ready"

