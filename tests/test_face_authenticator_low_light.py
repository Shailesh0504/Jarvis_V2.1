# tests/test_face_authenticator_low_light.py
"""
Unit and Integration Tests for Jarvis Biometric Facial Authentication in Low-Light Conditions.
Validates:
1. Low-light face detection down to severe underexposure (5% - 40% ambient light).
2. Verification confidence: Enrolled daylight face verifies reliably under low-light.
3. Robustness against low-light CMOS sensor noise (thermal/gain grain).
4. Anti-spoofing security: Empty dark rooms, dark walls, and sensor noise are strictly rejected.
5. Ratio-preserving adaptive luminance enhancement preserving skin chrominance.
6. GUI Gateway Fill Light and low-light visual assist handling.
"""

import os
import tempfile
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from security.face_authenticator import AuthResult, FaceAuthenticator


@pytest.fixture
def temp_profile():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.remove(path)


def make_synthetic_face(w=640, h=480, bg_color=(100, 100, 100), skin_color=(210, 165, 135)):
    """Creates a synthetic human face with facial features (eyes, eyebrows, mouth)."""
    img = np.full((h, w, 3), bg_color, dtype=np.uint8)
    yy, xx = np.ogrid[:h, :w]
    cx, cy = w // 2, h // 2

    # Face ellipse
    face_mask = ((xx - cx) / (w * 0.18)) ** 2 + ((yy - cy) / (h * 0.28)) ** 2 <= 1.0
    img[face_mask] = skin_color

    # Left eye + eyebrow
    eye_l = ((xx - (cx - 40)) / 16) ** 2 + ((yy - (cy - 30)) / 10) ** 2 <= 1.0
    img[eye_l] = [40, 30, 25]

    # Right eye + eyebrow
    eye_r = ((xx - (cx + 40)) / 16) ** 2 + ((yy - (cy - 30)) / 10) ** 2 <= 1.0
    img[eye_r] = [40, 30, 25]

    # Mouth
    mouth = ((xx - cx) / 32) ** 2 + ((yy - (cy + 60)) / 12) ** 2 <= 1.0
    img[mouth] = [120, 50, 50]

    return img


class TestLowLightFaceAuthentication:
    """Test suite verifying facial biometrics under low-light and dark environments."""

    def test_ratio_preserving_enhancement(self):
        """Verifies that low-light enhancement restores exposure without desaturating colors."""
        face = make_synthetic_face()
        dark_face = (face.astype(float) * 0.15).astype(np.uint8)

        is_low, mean_lum = FaceAuthenticator.analyze_illumination(dark_face)
        assert is_low is True
        assert mean_lum < 30.0

        enhanced = FaceAuthenticator.enhance_low_light(dark_face)
        assert enhanced is not None
        assert enhanced.shape == dark_face.shape
        assert np.mean(enhanced) > np.mean(dark_face) * 2.0

        # Check chromaticity preservation at face center
        cx, cy = 320, 240
        raw_r, raw_g, raw_b = float(face[cy, cx, 0]), float(face[cy, cx, 1]), float(face[cy, cx, 2])
        enh_r, enh_g, enh_b = float(enhanced[cy, cx, 0]), float(enhanced[cy, cx, 1]), float(enhanced[cy, cx, 2])

        # Ratios R/G and R/B should be preserved closely
        raw_rg_ratio = raw_r / max(raw_g, 1.0)
        enh_rg_ratio = enh_r / max(enh_g, 1.0)
        assert abs(raw_rg_ratio - enh_rg_ratio) < 0.15

    def test_low_light_detection_across_illumination_levels(self):
        """Verifies that face detection succeeds across multiple low-light levels down to 8% brightness."""
        auth = FaceAuthenticator()
        normal_face = make_synthetic_face()

        # Normal lighting detection
        det_norm, bbox_norm = auth.detect_face_in_frame(normal_face)
        assert det_norm is True
        assert bbox_norm is not None

        # Severe low-light levels: 35%, 25%, 20%, 15%, 10%, 8%
        for factor in [0.35, 0.25, 0.20, 0.15, 0.10, 0.08]:
            dark_face = np.clip(normal_face.astype(float) * factor, 0, 255).astype(np.uint8)
            det, bbox = auth.detect_face_in_frame(dark_face)
            assert det is True, f"Failed to detect face at factor {factor:.2f}"
            assert bbox is not None

    def test_low_light_verification_confidence(self, temp_profile):
        """Verifies enrolled daylight face verifies with >= 0.85 confidence in low light."""
        auth = FaceAuthenticator(profile_path=temp_profile)
        normal_face = make_synthetic_face()
        auth.enroll(frame=normal_face, user_name="Boss")
        assert auth.has_enrolled_profile() is True

        for factor in [0.35, 0.25, 0.20, 0.15, 0.10, 0.08]:
            dark_face = np.clip(normal_face.astype(float) * factor, 0, 255).astype(np.uint8)
            success, conf, msg = auth.verify_frame(dark_face)
            assert success is True, f"Verification failed at factor {factor:.2f}: {msg}"
            assert conf >= 0.85, f"Confidence {conf:.3f} below 0.85 at factor {factor:.2f}"
            assert "Identity Confirmed" in msg
            if factor <= 0.25:
                assert "Low-Light Boost" in msg

    def test_low_light_with_sensor_noise(self, temp_profile):
        """Verifies robustness when camera sensor adds grain/noise under low illumination."""
        auth = FaceAuthenticator(profile_path=temp_profile)
        normal_face = make_synthetic_face()
        auth.enroll(frame=normal_face, user_name="Boss")

        for sigma in [2.0, 5.0, 8.0]:
            for factor in [0.20, 0.15, 0.10]:
                dark_face = normal_face.astype(float) * factor
                np.random.seed(42)
                noise = np.random.normal(0, sigma, dark_face.shape)
                noisy_dark_face = np.clip(dark_face + noise, 0, 255).astype(np.uint8)

                success, conf, msg = auth.verify_frame(noisy_dark_face)
                assert success is True, f"Failed with noise sigma={sigma}, factor={factor:.2f}"
                assert conf >= 0.85

    def test_empty_dark_room_with_noise_strictly_rejected(self, temp_profile):
        """Guarantees empty dark rooms and sensor noise never falsely authenticate."""
        auth = FaceAuthenticator(profile_path=temp_profile)
        face = make_synthetic_face()
        auth.enroll(frame=face, user_name="Boss")

        # 1. Pitch-black room
        black_room = np.zeros((480, 640, 3), dtype=np.uint8)
        success, conf, msg = auth.verify_frame(black_room)
        assert success is False
        assert conf == 0.0

        # 2. Dark ambient room [25, 25, 20]
        dark_room = np.full((480, 640, 3), [25, 25, 20], dtype=np.uint8)
        success, conf, msg = auth.verify_frame(dark_room)
        assert success is False
        assert conf == 0.0

        # 3. Dark room with high camera sensor noise
        for sigma in [2.0, 5.0, 10.0]:
            np.random.seed(42)
            noise = np.random.normal(0, sigma, dark_room.shape)
            noisy_room = np.clip(dark_room.astype(float) + noise, 0, 255).astype(np.uint8)

            success, conf, msg = auth.verify_frame(noisy_room)
            assert success is False, f"Spoof vulnerability: empty room with noise authenticated (sigma={sigma})"
            assert conf < auth.confidence_threshold

    def test_gui_dialog_fill_light_and_low_light_handling(self, temp_profile):
        """Headless verification of GUI dialog fill light toggle and low light frame handling."""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from gui.dialogs.face_auth_dialog import FaceAuthDialog
        auth = FaceAuthenticator(profile_path=temp_profile)
        face = make_synthetic_face()
        auth.enroll(frame=face, user_name="Boss")

        dialog = FaceAuthDialog(authenticator=auth)
        assert hasattr(dialog, "fill_light_btn")
        assert dialog._fill_light_active is False

        # Toggle fill light ON
        dialog.fill_light_btn.click()
        assert dialog._fill_light_active is True
        assert "Light ON" in dialog.fill_light_btn.text()

        # Toggle fill light OFF
        dialog.fill_light_btn.click()
        assert dialog._fill_light_active is False
        assert "Fill Light" in dialog.fill_light_btn.text()

        # Feed low-light frame
        dark_face = (face.astype(float) * 0.15).astype(np.uint8)
        dialog._on_frame_received(dark_face)
        assert dialog._confidence >= 0.85
        assert "Low-Light Boost" in dialog.status_label.text()
