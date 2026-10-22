# tests/test_system_volume_control.py
"""
Comprehensive test suite verifying Windows Core Audio system volume control:
1. Validation and clamping (0 to 100, negatives, floats, strings, percentages, natural words).
2. Default playback device acquisition and scalar setting (0.0 - 1.0).
3. Immediate read-back verification within small tolerance.
4. Structured success/failure returns ({success: True, requested: 50, actual: 50} / {success: False, error: ...}).
5. Prevention of false-positive "set kar diya" confirmation upon failure.
6. Debug logging for output device, old volume, requested volume, API result, and final volume.
7. Pipeline routing of commands: 'set volume 50 percent', 'volume 80', 'volume 0', and 'volume 100'.
"""

import logging
from unittest.mock import MagicMock, patch
import pytest

from plugins.audio.volume_controller import (
    set_system_volume,
    get_system_volume,
    get_default_playback_device_and_volume,
)
from plugins.audio.plugin import AudioPlugin
from core.app import JarvisCore
from main import create_jarvis


# 1. Validation and Clamping Tests
def test_set_system_volume_validation_and_clamping():
    """Validates that volume inputs are clamped strictly between 0 and 100."""
    with patch("plugins.audio.volume_controller.get_default_playback_device_and_volume") as mock_get_dev:
        mock_dev = MagicMock()
        mock_endpoint = MagicMock()
        mock_dev.FriendlyName = "Mock Speakers"
        mock_endpoint.GetMasterVolumeLevelScalar.side_effect = [0.20, 0.0]  # old, read-back
        mock_get_dev.return_value = (mock_dev, mock_endpoint)

        # Negative clamped to 0
        res_neg = set_system_volume(-25)
        assert res_neg["requested"] == 0
        assert mock_endpoint.SetMasterVolumeLevelScalar.called
        args, _ = mock_endpoint.SetMasterVolumeLevelScalar.call_args
        assert args[0] == 0.0

        # Over 100 clamped to 100
        mock_endpoint.GetMasterVolumeLevelScalar.side_effect = [0.20, 1.0]
        res_over = set_system_volume(150)
        assert res_over["requested"] == 100
        args, _ = mock_endpoint.SetMasterVolumeLevelScalar.call_args
        assert args[0] == 1.0

        # Percentage string "50%"
        mock_endpoint.GetMasterVolumeLevelScalar.side_effect = [0.20, 0.50]
        res_pct = set_system_volume("50%")
        assert res_pct["requested"] == 50
        args, _ = mock_endpoint.SetMasterVolumeLevelScalar.call_args
        assert args[0] == 0.50

        # Natural words: "max" -> 100, "mute" -> 0, "half" -> 50
        mock_endpoint.GetMasterVolumeLevelScalar.side_effect = [0.20, 1.0]
        res_max = set_system_volume("max")
        assert res_max["requested"] == 100

        mock_endpoint.GetMasterVolumeLevelScalar.side_effect = [0.20, 0.0]
        res_mute = set_system_volume("mute")
        assert res_mute["requested"] == 0

        mock_endpoint.GetMasterVolumeLevelScalar.side_effect = [0.20, 0.50]
        res_half = set_system_volume("half")
        assert res_half["requested"] == 50


# 2. Success and Read-Back Verification
def test_set_system_volume_success_and_read_back():
    """Ensures volume scalar 0.0-1.0 is passed and read-back is verified within tolerance."""
    with patch("plugins.audio.volume_controller.get_default_playback_device_and_volume") as mock_get_dev:
        mock_dev = MagicMock()
        mock_endpoint = MagicMock()
        mock_dev.FriendlyName = "Realtek High Definition Audio"
        # Old volume: 30%, Read-back final volume: 50%
        mock_endpoint.GetMasterVolumeLevelScalar.side_effect = [0.30, 0.50]
        mock_get_dev.return_value = (mock_dev, mock_endpoint)

        res = set_system_volume(50, tolerance=2)

        assert res["success"] is True
        assert res["requested"] == 50
        assert res["actual"] == 50
        assert res["old_volume"] == 30
        assert res["device"] == "Realtek High Definition Audio"
        assert res["error"] is None
        assert "Volume 50% set kar diya hai" in res["message"]


# 3. Debug Logging Verification
def test_set_system_volume_debug_logging(caplog):
    """Verifies all required debug log metrics: output device, old volume, requested volume, API call, final volume."""
    caplog.set_level(logging.DEBUG, logger="jarvis.plugins.audio.volume")
    with patch("plugins.audio.volume_controller.get_default_playback_device_and_volume") as mock_get_dev:
        mock_dev = MagicMock()
        mock_endpoint = MagicMock()
        mock_dev.FriendlyName = "Headphones (CMF Buds 2)"
        mock_endpoint.GetMasterVolumeLevelScalar.side_effect = [0.28, 0.80]
        mock_get_dev.return_value = (mock_dev, mock_endpoint)

        set_system_volume(80)

        log_text = caplog.text
        assert "Detected output device: Headphones (CMF Buds 2)" in log_text
        assert "Old volume: 28%" in log_text
        assert "Requested volume: 80%" in log_text
        assert "API call result: SUCCESS" in log_text
        assert "Verified final volume: 80%" in log_text


# 4. Verification Mismatch Failure Handling (Do Not Allow False Positives)
def test_set_system_volume_verification_mismatch_fails():
    """If the Windows volume does not actually change, verify that success is False and error is reported."""
    with patch("plugins.audio.volume_controller.get_default_playback_device_and_volume") as mock_get_dev:
        mock_dev = MagicMock()
        mock_endpoint = MagicMock()
        mock_dev.FriendlyName = "Mock Audio Device"
        # Simulated bug: requested 80%, but audio hardware read-back stays stuck at 20%
        mock_endpoint.GetMasterVolumeLevelScalar.side_effect = [0.20, 0.20]
        mock_get_dev.return_value = (mock_dev, mock_endpoint)

        res = set_system_volume(80, tolerance=2)

        assert res["success"] is False
        assert res["requested"] == 80
        assert res["actual"] == 20
        assert res["error"] is not None
        assert "Verification mismatch" in res["error"]
        assert "Boss, volume change nahi ho paaya" in res["message"]


# 5. Core Audio Exception Handling
def test_set_system_volume_exception_handling():
    """Ensures COM / Core Audio exceptions are caught, logged, and return clean failure dict."""
    with patch("plugins.audio.volume_controller.get_default_playback_device_and_volume") as mock_get_dev:
        mock_get_dev.side_effect = RuntimeError("Audio service unavailable or device disconnected.")

        res = set_system_volume(50)

        assert res["success"] is False
        assert res["requested"] == 50
        assert "Audio service unavailable" in res["error"]
        assert "Boss, volume change nahi ho paaya" in res["message"]


# 6. AudioPlugin Execution Rejects False Success on Verification Failure
def test_audio_plugin_execute_fails_when_volume_not_verified():
    """AudioPlugin.execute must return PluginResult(success=False) if Windows volume verification fails."""
    plugin = AudioPlugin()
    with patch("plugins.audio.volume_controller.set_system_volume") as mock_set:
        mock_set.return_value = {
            "success": False,
            "requested": 50,
            "actual": 20,
            "error": "Hardware volume failed to change.",
            "message": "Boss, volume change nahi ho paaya: Hardware volume failed to change."
        }

        plugin_res = plugin.execute("set_volume", {"level": 50})

        assert plugin_res.success is False
        assert plugin_res.error == "Hardware volume failed to change."
        assert "set kar diya" not in plugin_res.data.get("message", "")


# 7. Command Pipeline Routing for 'set volume 50 percent', 'volume 80', 'volume 0', 'volume 100'
def test_command_pipeline_volume_commands():
    """End-to-end command pipeline test for user specified phrases."""
    test_cases = [
        ("set volume 50 percent", 50),
        ("volume 80", 80),
        ("volume 0", 0),
        ("volume 100", 100),
    ]

    core = create_jarvis()

    for cmd, expected_level in test_cases:
        # Case A: Success execution
        with patch("plugins.audio.volume_controller.set_system_volume") as mock_set_vol:
            mock_set_vol.return_value = {
                "success": True,
                "requested": expected_level,
                "actual": expected_level,
                "level": expected_level,
                "device": "Mock Speakers",
                "old_volume": 20,
                "error": None,
                "message": f"Volume {expected_level}% set kar diya hai, Boss."
            }

            resp = core.process_input(cmd, source="cli")
            assert mock_set_vol.called
            assert f"{expected_level}% set kar diya hai" in resp

        # Case B: Failure execution (Jarvis must NOT say "set kar diya")
        with patch("plugins.audio.volume_controller.set_system_volume") as mock_set_vol:
            mock_set_vol.return_value = {
                "success": False,
                "requested": expected_level,
                "actual": 10,
                "level": 10,
                "device": "Mock Speakers",
                "old_volume": 20,
                "error": "Hardware audio verification failed.",
                "message": "Boss, volume change nahi ho paaya: Hardware audio verification failed."
            }

            resp_fail = core.process_input(cmd, source="cli")
            assert "set kar diya" not in resp_fail
            assert "volume change nahi ho paaya" in resp_fail or "Hardware audio verification failed" in resp_fail


def test_pytest_sessionstart_sets_volume_to_12():
    """Verify that the pytest sessionstart hook sets system volume to 12%."""
    from conftest import pytest_sessionstart
    with patch("plugins.audio.volume_controller.set_system_volume") as mock_set:
        pytest_sessionstart(None)
        mock_set.assert_called_once_with(12)

