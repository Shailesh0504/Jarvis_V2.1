# tests/test_face_authenticator_security.py
"""
Security and anti-bypass tests for Jarvis Biometric Facial Authentication.
Verifies that:
1. Empty rooms, walls, furniture, dark scenes, and non-face backgrounds never authenticate.
2. Single-frame noise/lighting flicker cannot bypass verification (multi-frame requirement).
3. GUI startup strictly blocks launch unless genuine authentication succeeds.
4. Genuine face profiles authenticate reliably under normal variations.
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


def test_empty_warm_room_and_walls_rejected(temp_profile):
    """Verify empty room or beige/wood wall never causes false-positive verification."""
    auth = FaceAuthenticator(profile_path=temp_profile)
    face = make_synthetic_face()
    auth.enroll(frame=face, user_name="Boss")
    assert auth.has_enrolled_profile() is True

    # 1. Warm beige empty room (classic user issue when restarting without being in front of screen)
    warm_room = np.full((480, 640, 3), [180, 150, 120], dtype=np.uint8)
    success, conf, msg = auth.verify_frame(warm_room)
    assert success is False
    assert conf < auth.confidence_threshold

    # 2. Wooden door / dark beige wall filling camera
    wood_wall = np.full((480, 640, 3), [160, 120, 90], dtype=np.uint8)
    success, conf, msg = auth.verify_frame(wood_wall)
    assert success is False
    assert conf < auth.confidence_threshold


def test_blue_screen_dark_room_random_noise_rejected(temp_profile):
    """Verify non-face visual inputs never falsely authenticate."""
    auth = FaceAuthenticator(profile_path=temp_profile)
    face = make_synthetic_face()
    auth.enroll(frame=face, user_name="Boss")

    # 1. Blue screen / monitor glow
    blue_screen = np.full((480, 640, 3), [20, 40, 200], dtype=np.uint8)
    success, conf, msg = auth.verify_frame(blue_screen)
    assert success is False

    # 2. Dark room at night
    dark_room = np.full((480, 640, 3), [25, 25, 20], dtype=np.uint8)
    success, conf, msg = auth.verify_frame(dark_room)
    assert success is False

    # 3. Random camera sensor noise
    noise = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    success, conf, msg = auth.verify_frame(noise)
    assert success is False
    assert conf < auth.confidence_threshold


def test_genuine_face_verified_with_illumination_shift(temp_profile):
    """Verify genuine enrolled face authenticates with high confidence under lighting shift."""
    auth = FaceAuthenticator(profile_path=temp_profile)
    face = make_synthetic_face()
    auth.enroll(frame=face, user_name="Boss")

    # 1. Same face
    success, conf, msg = auth.verify_frame(face)
    assert success is True
    assert conf >= 0.90
    assert "Identity Confirmed" in msg

    # 2. Same face under brighter ambient light (+15 brightness)
    brighter_face = np.clip(face.astype(float) + 15, 0, 255).astype(np.uint8)
    success_b, conf_b, msg_b = auth.verify_frame(brighter_face)
    assert success_b is True
    assert conf_b >= 0.85


def test_gui_dialog_multi_frame_consecutive_requirement(temp_profile):
    """Verify that a single isolated frame cannot unlock the GUI dialog."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from gui.dialogs.face_auth_dialog import FaceAuthDialog
    auth = FaceAuthenticator(profile_path=temp_profile)
    face = make_synthetic_face()
    auth.enroll(frame=face, user_name="Boss")

    dialog = FaceAuthDialog(authenticator=auth)
    assert dialog._consecutive_matches == 0
    assert dialog.is_authenticated is False

    # Frame 1: valid frame received (1 match) -> must NOT unlock yet
    dialog._on_frame_received(face)
    assert dialog._consecutive_matches == 1
    assert dialog.is_authenticated is False

    # Interspersed invalid frame (e.g. noise or turned head) -> counter resets
    empty_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    dialog._on_frame_received(empty_frame)
    assert dialog._consecutive_matches == 0
    assert dialog.is_authenticated is False

    # 3 consecutive valid frames -> unlocks
    dialog._on_frame_received(face)
    assert dialog._consecutive_matches == 1
    assert dialog.is_authenticated is False

    dialog._on_frame_received(face)
    assert dialog._consecutive_matches == 2
    assert dialog.is_authenticated is False

    dialog._on_frame_received(face)
    assert dialog._consecutive_matches == 3
    assert dialog.is_authenticated is True
    assert dialog.auth_method == "facial_biometrics"
    dialog.close()


def test_gui_launch_gate_exits_when_not_authenticated():
    """Verify launch_gui returns 0 immediately if user cancels or authentication fails."""
    from gui import launch_gui

    mock_core = MagicMock()
    mock_core.config = {"security": {"face_auth": {"enabled": True}}}

    with patch("gui.dialogs.face_auth_dialog.FaceAuthDialog.exec") as mock_exec, \
         patch("gui.JarvisMainWindow") as mock_window:
        # Dialog closed without authentication
        res = launch_gui(mock_core, bypass_auth=False)
        assert res == 0
        # Main window must NEVER have been instantiated or shown
        mock_window.assert_not_called()
