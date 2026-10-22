# tests/test_coucou_sound_system.py
"""Coucou-style event-driven sound system: engine dedup, transition mapping,
semantic wiring, settings persistence, and mic/STT non-interference.

Headless (QT_QPA_PLATFORM=offscreen via conftest). Playback backends are
stubbed; what is verified is *when* and *whether* sounds fire — never real audio.
"""

import os
import wave

import pytest
from PySide6.QtWidgets import QApplication

from gui.sound_effects import JarvisSoundEngine, Sound, DEFAULT_VOLUME

app = QApplication.instance() or QApplication(["-platform", "offscreen"])


def _make_wav(path, freq=660.0, seconds=0.08, framerate=22050):
    import math
    import struct
    frames = int(framerate * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        for i in range(frames):
            sample = int(12000 * math.sin(2 * math.pi * freq * i / framerate))
            w.writeframes(struct.pack("<h", sample))


@pytest.fixture()
def engine(tmp_path):
    """Fresh engine with real wav files, guards lifted (backends stubbed per-test)."""
    d = tmp_path / "sounds"
    d.mkdir()
    for name in ("peek", "open", "close", "blip", "finish", "error", "work",
                 "think", "approval", "approve", "send", "hover", "love",
                 "dizzy", "tick"):
        _make_wav(d / f"{name}.wav")
    eng = JarvisSoundEngine(sounds_dir=str(d))
    eng._is_headless = False
    eng.enabled = True
    eng.volume = 0.12
    return eng


def _mixerless(monkeypatch, fail_on=()):
    """Force the winsound-fallback path (no pygame mixer in test env)."""
    import sys

    def fake_play(*a, **k):
        if a and any(s in str(a[0]) for s in fail_on):
            raise RuntimeError("unsupported wave format")
        calls.append(a)

    calls = []
    monkeypatch.setitem(sys.modules, "pygame", None)
    monkeypatch.setattr("winsound.PlaySound", fake_play, raising=False)
    return calls


# ── engine core ──────────────────────────────────────────────────────────────
def test_engine_preload_and_missing_assets(engine, monkeypatch):
    eng = engine
    calls = _mixerless(monkeypatch, fail_on=("corrupt",))
    assert eng.play("peek", reason="t") is True
    assert len(calls) == 1
    # Missing file: silent False, never crashes.
    assert eng.play("no_such_cue_xyz", reason="t") is False
    # Corrupt file: silent False, never crashes.
    corrupt = os.path.join(eng.sounds_dir, "corrupt.wav")
    with open(corrupt, "wb") as f:
        f.write(b"not a wav at all")
    assert eng.play("corrupt", reason="t") is False


def test_engine_duplicate_event_suppression(engine, monkeypatch):
    eng = engine
    calls = _mixerless(monkeypatch)
    assert eng.play("finish", reason="task_success", event_id="111") is True
    assert eng.play("finish", reason="task_success", event_id="111") is False
    assert len(calls) == 1
    # Same sound, different event → plays (with cooldown cleared).
    eng._last_play.clear()
    assert eng.play("finish", reason="task_success", event_id="222") is True
    assert len(calls) == 2


def test_engine_cooldown(engine, monkeypatch):
    eng = engine
    calls = _mixerless(monkeypatch)
    assert eng.play("blip", reason="a") is True
    assert eng.play("blip", reason="b") is False  # 800ms default cooldown
    eng._last_play.clear()
    assert eng.play("blip", reason="c", cooldown_ms=0) is True
    assert len(calls) == 2


def test_engine_disabled_and_zero_volume(engine, monkeypatch):
    eng = engine
    calls = _mixerless(monkeypatch)
    eng.enabled = False
    assert eng.play("peek", reason="t") is False
    eng.enabled = True
    eng.set_volume(0.0)
    assert eng.play("peek", reason="t") is False
    assert calls == []


def test_engine_overlap_two_names(engine, monkeypatch):
    eng = engine
    calls = _mixerless(monkeypatch)
    assert eng.play("blip", reason="a") is True
    assert eng.play("work", reason="b") is True
    assert len(calls) == 2


def test_engine_overlap_via_cached_mixer_sound(engine, monkeypatch):
    """pygame-channel path overlaps safely and honors volume."""
    eng = engine
    played = []

    class FakeSound:
        def __init__(self):
            self.volumes = []

        def set_volume(self, v):
            self.volumes.append(v)

        def play(self):
            played.append(True)
            return True

    fake = FakeSound()
    eng._cache["blip"] = fake
    assert eng.play("blip", reason="a") is True
    eng._last_play.clear()  # distinct turn: second name overlaps safely
    assert eng.play("work", reason="b") is True
    assert fake.volumes and abs(fake.volumes[0] - 0.12) < 1e-6
    assert played == [True]


def test_engine_logging_format(engine, monkeypatch, caplog):
    import logging
    eng = engine
    _mixerless(monkeypatch)
    with caplog.at_level(logging.DEBUG, logger="jarvis.gui.sound"):
        eng.play("open", reason="compact_to_expanded")
        eng.play("open", reason="compact_to_expanded")
    plays = [r for r in caplog.records if "PLAY name=open" in r.message]
    supps = [r for r in caplog.records if "SUPPRESSED name=open" in r.message]
    assert len(plays) == 1 and len(supps) == 1


def test_engine_default_volume_subtle():
    assert abs(DEFAULT_VOLUME - 0.12) < 1e-9
    assert abs(JarvisSoundEngine().volume - 0.12) < 1e-9


# ── FSM transition mapping ───────────────────────────────────────────────────
@pytest.fixture()
def island(monkeypatch):
    from gui.island.island import CoucouIslandWidget
    calls = []
    monkeypatch.setattr(Sound, "play", lambda *a, **k: calls.append((a, k)))
    isl = CoucouIslandWidget()
    yield isl, calls
    isl.close()


def test_transition_hidden_compact_peek(island):
    isl, calls = island
    isl._is_greeting_active = False
    isl.set_mode("hidden")
    calls.clear()
    isl.set_mode("compact")
    assert [(a[0] if a else None) for a, _ in calls] == ["peek"]
    assert calls[0][1].get("reason", "").endswith("hidden_to_compact")


def test_transition_compact_expanded_open(island):
    isl, calls = island
    isl._is_greeting_active = False
    isl.set_mode("compact")
    calls.clear()
    isl.set_mode("expanded")
    assert [a[0] for a, _ in calls] == ["open"]


def test_transition_expanded_compact_close(island):
    isl, calls = island
    isl._is_greeting_active = False
    isl.set_mode("expanded")
    calls.clear()
    isl.set_mode("compact")
    assert [a[0] for a, _ in calls] == ["close"]


def test_transition_same_state_silent(island):
    isl, calls = island
    isl._is_greeting_active = False
    isl.set_mode("expanded")
    calls.clear()
    isl.expand_to_view("overview")  # already expanded: no fresh open
    assert calls == []
    isl.set_mode("compact")
    calls.clear()
    isl.set_mode("compact")
    assert calls == []


def test_transition_to_hidden_silent(island):
    isl, calls = island
    isl._is_greeting_active = False
    isl.set_mode("compact")
    calls.clear()
    isl.set_mode("hidden")
    assert calls == []


def test_greeting_suppresses_transition_sounds(island):
    isl, calls = island
    isl._is_greeting_active = True
    isl.set_mode("compact")
    calls.clear()
    isl.set_mode("expanded")
    isl.set_mode("compact")
    assert calls == []


# ── app-level semantic wiring (full window, tmp config) ──────────────────────
@pytest.fixture()
def gui_core(tmp_path):
    from main import create_jarvis
    db_file = str(tmp_path / "snd_test.db").replace("\\", "/")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(f"""
system:
  name: "JARVIS_SOUND_TEST"
memory:
  db_path: "{db_file}"
brain:
  llm_provider: "mock"
reminder:
  db_path: "{str(tmp_path / 'snd_reminders.db').replace(chr(92), '/')}"
plugins:
  plugin_dir: "plugins"
  auto_load: true
""")
    return create_jarvis(str(cfg_file))


@pytest.fixture()
def window(gui_core, monkeypatch):
    from gui.app import JarvisMainWindow
    # Real engine path (dedup/cooldown/enabled honored), winsound stubbed.
    calls = []
    monkeypatch.setattr("winsound.PlaySound",
                        lambda *a, **k: calls.append(a), raising=False)
    monkeypatch.setattr(Sound, "_mixer_ready", lambda: False)
    monkeypatch.setattr(Sound, "_is_headless", False)
    # Another suite leaves the record flag on globally; real stubbed path here.
    monkeypatch.setattr(Sound, "record_all_plays_for_test", False)
    win = JarvisMainWindow(gui_core)
    win.show()
    # Keep singleton side-effects local to each test (engine + manager).
    saved_enabled, saved_volume = Sound.enabled, Sound.volume
    Sound._last_play.clear()
    Sound._seen_events.clear()
    try:
        from gui.island.semantic_events import SemanticEventManager
        _mgr = SemanticEventManager.instance()
        _mgr._last_event_time.clear()
        _mgr._seen_event_ids.clear()
    except Exception:
        pass
    yield win, calls
    Sound.enabled, Sound.volume = saved_enabled, saved_volume
    Sound._last_play.clear()
    Sound._seen_events.clear()
    try:
        win.close()
    except Exception:
        pass


def _names(calls):
    """winsound stub records paths — reduce to bare sound names."""
    import os as _os
    return [_os.path.splitext(_os.path.basename(a[0]))[0] if a else None
            for a in calls]


def test_thinking_entry_plays_think_once(window):
    win, calls = window
    win.set_system_state("thinking")
    win.set_system_state("thinking")  # re-entry (label refresh): silent
    win.set_system_state("thinking")
    assert _names(calls).count("think") == 1


def test_listening_entry_plays_blip_once(window):
    win, calls = window
    win.set_system_state("listening", details="hi")
    win.set_system_state("listening", details="hi")
    assert _names(calls).count("blip") == 1


def test_confused_entry_plays_dizzy(window):
    win, calls = window
    win.set_system_state("confused")
    assert _names(calls).count("dizzy") == 1


def test_worker_accept_and_response_sounds(window, monkeypatch):
    from PySide6.QtCore import QObject, Signal

    win, calls = window

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
    win._start_message_worker("open chrome", source="gui")
    assert _names(calls).count("blip") == 1  # accepted exactly once
    win._on_worker_finished("Jarvis", "Chrome khol diya", None, win._active_generation_id)
    assert _names(calls).count("finish") == 1  # response completed


def test_execution_verified_success_and_failure(window):
    win, calls = window
    win._on_execution_completed_event({
        "success": True, "timestamp": 4242.0,
        "executed_action": "launch_app", "target": "chrome"})
    win._on_execution_completed_event({  # duplicate delivery: silent
        "success": True, "timestamp": 4242.0,
        "executed_action": "launch_app", "target": "chrome"})
    win._on_execution_completed_event({
        "success": False, "timestamp": 4343.0,
        "executed_action": "launch_app", "target": "nope"})
    names = _names(calls)
    assert names.count("finish") == 1
    assert names.count("error") == 1


def test_policy_evaluated_starts_work_once(window):
    win, calls = window
    win._on_policy_evaluated_event({"allowed": True, "plan_id": "p-1"})
    win._on_policy_evaluated_event({"allowed": True, "plan_id": "p-1"})
    win._on_policy_evaluated_event({"allowed": False, "plan_id": "p-2"})
    assert _names(calls).count("work") == 1


def test_approval_shows_card_pins_and_chimes_once(window):
    win, calls = window
    payload = {"task_id": "t-9", "step_id": "s-3", "step": "Remove-Item cache.db",
               "question": "High risk action - allow?"}
    win._on_agent_approval_required_event(dict(payload))
    win._on_agent_approval_required_event(dict(payload))  # redelivery: silent
    assert _names(calls).count("approval") == 1
    assert win.island._current_view == "approval"
    assert "Remove-Item" in win.island.view_approval.code_label.text()
    # Pinned: auto-collapse must hold the confirmation, soundlessly.
    n_before = len(calls)
    win.island._on_auto_collapse_timeout()
    assert win.island._current_view == "approval"
    assert len(calls) == n_before


def test_deny_plays_blip_not_approval(window):
    """Deny path (user_denied) chimes blip exactly once — spec deny behavior."""
    win, calls = window
    win.expand_island("approval")
    calls.clear()
    Sound._last_play.clear()
    win.island._on_approval_decision(False)
    assert _names(calls).count("blip") == 1  # + close for the collapse; no approval
    assert "approval" not in _names(calls)
    win.island._on_approval_decision(True)
    assert _names(calls).count("approve") == 1


def test_volume_slider_reaches_engine_and_persists(window, tmp_path):
    win, calls = window
    win.core.config_path = str(tmp_path / "persist_cfg.yaml")
    win._on_island_volume_changed(30)
    assert abs(Sound.volume - 0.30) < 1e-9
    import yaml
    with open(win.core.config_path, encoding="utf-8") as f:
        saved = yaml.safe_load(f)
    assert saved["sound"]["volume"] == 30
    assert saved["sound"]["enabled"] is True


def test_sound_settings_apply_from_config(window):
    win, calls = window
    win.core.config["sound"] = {"enabled": False, "volume": 40}
    win._apply_sound_settings()
    assert Sound.enabled is False
    win.set_system_state("thinking")
    assert calls == []  # OFF means zero UI sounds
    win.core.config["sound"] = {"enabled": True, "volume": 40}
    win._apply_sound_settings()
    assert Sound.enabled is True


def test_standalone_wake_single_chime_no_gui_double(window, monkeypatch):
    """Confirmed wake -> exactly one voice chime, zero extra GUI sounds."""
    from types import SimpleNamespace
    from gui.views.chat_view import ChatView

    win, calls = window
    chimes = []
    monkeypatch.setattr("voice.chime.play_wake_chime_async",
                        lambda *a, **k: chimes.append(True))
    view = ChatView(win.core)
    view.core = SimpleNamespace(
        interaction_gate=SimpleNamespace(
            evaluate=lambda text, is_explicit_listen=False: SimpleNamespace(
                accepted=True, is_barge_in=False, reason="wake",
                is_standalone_wake=True, command=""),
            interrupt_active_speech=lambda **k: None),
        interrupt_active_speech=lambda **k: None)
    heard = []
    view.voice_message_submitted.connect(lambda t: heard.append(t))
    view._on_voice_transcribed("Jarvis")
    assert len(chimes) == 1
    assert calls == []  # GUI adds no second cue on top of the chime
    assert heard == ["Jarvis"]
    view.close()
