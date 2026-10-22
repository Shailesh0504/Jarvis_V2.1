# tests/test_face_authenticator_fallback.py
"""
Unit and Integration Tests for Biometric Face Authenticator Fallback Path (Gap 2).
Covers:
- Voice PIN spoken word normalization (English / Hindi / Hinglish digits)
- Voice PIN authentication & lockout rate limiting
- Emergency passphrase override verification
- Camera-unavailable graceful fallback
"""

import time
from unittest.mock import MagicMock, patch
import pytest

from security.face_authenticator import AuthResult, FaceAuthenticator


@pytest.fixture
def auth_instance(tmp_path):
    prof_path = str(tmp_path / "face_profile.json")
    cfg = {
        "security": {
            "face_auth": {
                "enabled": True,
                "user_name": "Boss",
                "master_pin": "5678",
                "emergency_passphrase": "delta shield override 99",
                "pin_max_attempts": 3,
                "pin_lockout_seconds": 2,
            }
        }
    }
    return FaceAuthenticator(config=cfg, profile_path=prof_path)


class TestFaceAuthenticatorFallback:
    """Validates the multi-tier fallback authentication paths."""

    def test_normalize_pin_digits(self, auth_instance):
        assert auth_instance.normalize_pin("5678") == "5678"
        assert auth_instance.normalize_pin("5-6-7-8") == "5678"
        assert auth_instance.normalize_pin(" 5 6 7 8 ") == "5678"

    def test_normalize_pin_english_words(self, auth_instance):
        assert auth_instance.normalize_pin("five six seven eight") == "5678"
        assert auth_instance.normalize_pin("one two three four") == "1234"
        assert auth_instance.normalize_pin("zero zero zero zero") == "0000"

    def test_normalize_pin_hindi_hinglish_words(self, auth_instance):
        assert auth_instance.normalize_pin("ek do teen char") == "1234"
        assert auth_instance.normalize_pin("paanch chhah saat aath") == "5678"
        assert auth_instance.normalize_pin("panch chhe saat aath") == "5678"
        assert auth_instance.normalize_pin("shunya shunya shunya shunya") == "0000"

    def test_authenticate_voice_pin_success(self, auth_instance):
        res = auth_instance.authenticate_voice_pin("five six seven eight")
        assert res.success is True
        assert res.method == "master_passcode"
        assert "5678" in res.message or "verified" in res.message.lower()

    def test_authenticate_voice_pin_hindi_success(self, auth_instance):
        res = auth_instance.authenticate_voice_pin("paanch chhe saat aath")
        assert res.success is True
        assert res.method == "master_passcode"

    def test_authenticate_voice_pin_incorrect_and_lockout(self, auth_instance):
        # 1st wrong attempt
        r1 = auth_instance.authenticate_voice_pin("1111")
        assert r1.success is False
        assert "2 attempts remaining" in r1.error

        # 2nd wrong attempt
        r2 = auth_instance.authenticate_voice_pin("2222")
        assert r2.success is False
        assert "1 attempts remaining" in r2.error

        # 3rd wrong attempt -> triggers lockout
        r3 = auth_instance.authenticate_voice_pin("3333")
        assert r3.success is False
        assert "Locked" in r3.error

        # Immediate 4th attempt during lockout
        r4 = auth_instance.authenticate_voice_pin("5678")
        assert r4.success is False
        assert "locked" in r4.error.lower()

        # Wait for lockout to expire (2 seconds)
        time.sleep(2.1)
        r5 = auth_instance.authenticate_voice_pin("5678")
        assert r5.success is True

    def test_emergency_passphrase_override(self, auth_instance):
        res = auth_instance.authenticate_voice_pin("delta shield override 99")
        assert res.success is True
        assert res.method == "emergency_passphrase"
        assert "Emergency override accepted" in res.message

    def test_authenticate_cli_camera_unavailable_fallback(self, auth_instance):
        # Simulate open_camera returning None (no camera / device busy)
        with patch.object(auth_instance, "open_camera", return_value=None):
            with patch("builtins.input", return_value="five six seven eight"):
                res = auth_instance.authenticate_cli()
                assert res.success is True
                assert res.method == "master_passcode"
                assert res.user_name == "Boss"
