# tests/test_media_ducker.py
"""
Unit and regression tests for MediaDucker system volume attenuation:
1. Verifies MediaDucker singleton pattern and state initialization.
2. Verifies is_media_playing correctly checks peak audio meter of browser/media processes.
3. Verifies duck() sets active session volume to attenuation level (15%) and preserves original volume.
4. Verifies unduck() restores original session volumes accurately.
5. Verifies VoiceListener integrates with MediaDucker on mode transitions and stop phrases.
"""

from unittest.mock import MagicMock, patch
import pytest

from voice.media_ducker import MediaDucker
from voice.listener import VoiceListener, VoiceMode


@pytest.fixture(autouse=True)
def reset_ducker():
    """Reset MediaDucker singleton state before each test."""
    ducker = MediaDucker.get_instance()
    with ducker._lock:
        ducker._is_ducked = False
        ducker._original_volumes.clear()
    yield ducker
    with ducker._lock:
        ducker._is_ducked = False
        ducker._original_volumes.clear()


def test_media_ducker_singleton():
    """Verifies get_instance returns the authoritative singleton."""
    d1 = MediaDucker.get_instance()
    d2 = MediaDucker.get_instance()
    assert d1 is d2
    assert d1.is_ducked is False


def test_is_media_playing_detects_active_sound():
    """Verifies is_media_playing returns True when a browser process has active audio peak."""
    ducker = MediaDucker.get_instance()

    mock_proc = MagicMock()
    mock_proc.name.return_value = "brave.exe"

    mock_meter = MagicMock()
    mock_meter.GetPeakValue.return_value = 0.08  # Active audio peak

    mock_session = MagicMock()
    mock_session.Process = mock_proc
    mock_session.ProcessId = 1234
    mock_session._ctl.QueryInterface.return_value = mock_meter

    with patch("pycaw.pycaw.AudioUtilities.GetAllSessions", return_value=[mock_session]):
        with patch("os.name", "nt"):
            assert ducker.is_media_playing() is True


def test_is_media_playing_returns_false_on_silence():
    """Verifies is_media_playing returns False when sessions are silent or unrelated."""
    ducker = MediaDucker.get_instance()

    mock_proc = MagicMock()
    mock_proc.name.return_value = "notepad.exe"

    mock_session = MagicMock()
    mock_session.Process = mock_proc
    mock_session.ProcessId = 5678

    with patch("pycaw.pycaw.AudioUtilities.GetAllSessions", return_value=[mock_session]):
        with patch("os.name", "nt"):
            assert ducker.is_media_playing() is False


def test_duck_and_unduck_lifecycle():
    """Verifies duck sets volume to 15% and saves original, and unduck restores it."""
    ducker = MediaDucker.get_instance()

    mock_proc = MagicMock()
    mock_proc.name.return_value = "chrome.exe"

    mock_vol = MagicMock()
    mock_vol.GetMasterVolume.return_value = 0.80

    mock_meter = MagicMock()
    mock_meter.GetPeakValue.return_value = 0.10

    def query_interface_side_effect(interface):
        from pycaw.pycaw import ISimpleAudioVolume, IAudioMeterInformation
        if interface == ISimpleAudioVolume:
            return mock_vol
        elif interface == IAudioMeterInformation:
            return mock_meter
        return None

    mock_session = MagicMock()
    mock_session.Process = mock_proc
    mock_session.ProcessId = 9999
    mock_session._ctl.QueryInterface.side_effect = query_interface_side_effect

    with patch("pycaw.pycaw.AudioUtilities.GetAllSessions", return_value=[mock_session]):
        with patch("os.name", "nt"):
            # 1. Duck
            ducked = ducker.duck(attenuation=0.15)
            assert ducked is True
            assert ducker.is_ducked is True
            mock_vol.SetMasterVolume.assert_called_with(0.15, None)
            assert ducker._original_volumes[9999] == 0.80

            # 2. Duplicate duck should be a no-op
            assert ducker.duck(attenuation=0.15) is True

            # 3. Unduck
            restored = ducker.unduck()
            assert restored is True
            assert ducker.is_ducked is False
            mock_vol.SetMasterVolume.assert_called_with(0.80, None)
            assert len(ducker._original_volumes) == 0


def test_voice_listener_set_mode_triggers_duck_and_unduck():
    """Verifies VoiceListener ducks media in ACTIVE mode and unducks in STANDBY mode."""
    listener = VoiceListener(enable_audio_stream=False)

    with patch.object(MediaDucker.get_instance(), "duck") as mock_duck:
        listener.set_mode(VoiceMode.ACTIVE)
        mock_duck.assert_called_once_with(attenuation=0.15)

    with patch.object(MediaDucker.get_instance(), "unduck") as mock_unduck:
        listener.set_mode(VoiceMode.STANDBY)
        mock_unduck.assert_called_once()


def test_voice_listener_stop_phrase_triggers_unduck():
    """Verifies explicit stop phrase causes MediaDucker to unduck."""
    listener = VoiceListener(enable_audio_stream=False)
    listener.set_mode(VoiceMode.ACTIVE)

    with patch.object(MediaDucker.get_instance(), "unduck") as mock_unduck:
        res = listener.process_utterance("bas karo jarvis")
        assert res.detected is True
        assert listener.mode == VoiceMode.STANDBY
        assert mock_unduck.called is True


def test_unduck_delayed_cancels_and_schedules():
    """Verifies unduck_delayed schedules unduck on background timer safely."""
    ducker = MediaDucker.get_instance()
    with patch.object(ducker, "unduck") as mock_unduck:
        ducker.unduck_delayed(delay=0.05)
        assert ducker._delayed_timer is not None
        import time
        time.sleep(0.1)
        mock_unduck.assert_called_once()


def test_input_quality_accepts_devanagari_hindi_speech():
    """Verifies that Hindi Devanagari speech with matras is treated as CLEAN and not high symbol ratio."""
    from core.speech_understanding import InputQualityEvaluator, InputQuality
    quality, _, metrics = InputQualityEvaluator.evaluate_quality("यूट्यूब बंद करो", "यूट्यूब बंद करो")
    assert quality == InputQuality.CLEAN
    assert metrics.get("reason") == "lexically_coherent"


def test_devanagari_hindi_command_normalized_and_classified():
    """Verifies that Devanagari 'यूट्यूब बंद करो' is normalized and recognized as ACTION_COMMAND."""
    from core.semantic.normalizer import HinglishNormalizer
    from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType

    norm = HinglishNormalizer.normalize_text("यूट्यूब बंद करो")
    assert "youtube" in norm
    assert "band karo" in norm

    clf = ConversationalIntentClassifier()
    res = clf.classify(norm)
    assert res.intent_type == ConversationalIntentType.ACTION_COMMAND
    assert res.is_executable is True
    assert res.target == "youtube"

