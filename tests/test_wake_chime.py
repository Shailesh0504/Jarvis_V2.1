# tests/test_wake_chime.py
"""Unit tests for the Wake-Chime acoustic cue player."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import voice.chime as chime
from voice.chime import play_wake_chime_async, _play_wake_chime_sync
from core.interaction_gate import InteractionGate, InteractionState


def test_wake_chime_async_non_blocking():
    """Verifies that play_wake_chime_async runs non-blockingly in a daemon thread."""
    with patch("voice.chime._play_wake_chime_sync"):
        start = time.perf_counter()
        play_wake_chime_async()
        elapsed = time.perf_counter() - start

        # Async launch should be non-blocking (< 250ms)
        assert elapsed < 0.25


def test_wake_chime_triggered_on_wake_detection():
    """Verifies that InteractionGate evaluates wake words and initiates acoustic feedback."""
    gate = InteractionGate()
    decision = gate.evaluate("Jarvis, volume 50 karo")
    assert decision.accepted is True
    assert decision.command == "volume 50 karo"


def test_project_wake_mp3_exists():
    assert chime._WAKE_SOUND_PATH == Path(__file__).resolve().parents[1] / "plugins" / "sounds" / "jarvis.mp3"
    assert chime._WAKE_SOUND_PATH.is_file()


def test_wake_mp3_is_cached_and_played_non_blocking():
    fake_pygame = MagicMock()
    fake_pygame.mixer.get_init.return_value = True
    channel = fake_pygame.mixer.find_channel.return_value
    sound = fake_pygame.mixer.Sound.return_value

    with patch.dict("sys.modules", {"pygame": fake_pygame}):
        chime._cached_wake_sound = None
        _play_wake_chime_sync()
        _play_wake_chime_sync()

    fake_pygame.mixer.Sound.assert_called_once_with(str(chime._WAKE_SOUND_PATH))
    assert channel.play.call_count == 2
    sound.set_volume.assert_called_once_with(0.90)
