# tests/test_face_authenticator.py
import json
import os
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from brain.semantic_parser import HinglishNLUParser
from core.app import JarvisCore
from security.face_authenticator import AuthResult, FaceAuthenticator


@pytest.fixture
def temp_profile():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def mock_face_frame():
    """Generates a non-blank mock image frame (200x200 RGB with skin tones)."""
    frame = np.ones((200, 200, 3), dtype=np.uint8)
    frame[..., 0] = 210  # R
    frame[..., 1] = 160  # G
    frame[..., 2] = 130  # B
    return frame


def test_feature_extraction_and_similarity(temp_profile, mock_face_frame):
    auth = FaceAuthenticator(profile_path=temp_profile)
    features = auth.compute_frame_features(mock_face_frame)
    assert features is not None
    assert len(features) == 32  # 16 blocks * 2 features

    # Identical features similarity is 1.0
    sim = auth.compare_features(features, features)
    assert pytest.approx(sim, 0.001) == 1.0


def test_face_enrollment_and_verification(temp_profile, mock_face_frame):
    auth = FaceAuthenticator(profile_path=temp_profile)
    assert auth.has_enrolled_profile() is False

    # 1. Enroll
    enroll_res = auth.enroll(frame=mock_face_frame, user_name="Boss")
    assert enroll_res["success"] is True
    assert auth.has_enrolled_profile() is True

    # 2. Verify matching frame
    success, conf, msg = auth.verify_frame(mock_face_frame)
    assert success is True
    assert conf >= 0.95
    assert "Identity Confirmed" in msg or "Boss" in msg

    # 3. Verify blank frame
    blank_frame = np.zeros((200, 200, 3), dtype=np.uint8)
    success, conf, msg = auth.verify_frame(blank_frame)
    assert success is False


def test_passcode_fallback(temp_profile):
    cfg = {"security": {"face_auth": {"master_pin": "5678"}}}
    auth = FaceAuthenticator(config=cfg, profile_path=temp_profile)

    assert auth.verify_passcode("5678") is True
    assert auth.verify_passcode("0000") is False


def test_cli_authentication_success_with_camera(temp_profile, mock_face_frame):
    auth = FaceAuthenticator(profile_path=temp_profile)
    auth.enroll(frame=mock_face_frame, user_name="Boss")

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, mock_face_frame)

    with patch.object(FaceAuthenticator, "open_camera", return_value=mock_cap):
        result = auth.authenticate_cli(timeout_seconds=2)
        assert result.success is True
        assert result.method == "facial_biometrics"
        assert result.confidence >= 0.90


def test_cli_authentication_fallback_when_camera_fails(temp_profile):
    auth = FaceAuthenticator(profile_path=temp_profile)

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False

    with patch.object(FaceAuthenticator, "open_camera", return_value=mock_cap), \
         patch("builtins.input", return_value="1234"):
        result = auth.authenticate_cli(timeout_seconds=1)
        assert result.success is True
        assert result.method == "master_passcode"


def test_semantic_parser_face_auth_commands():
    # 1. Enroll face
    act1 = HinglishNLUParser.parse("mera face register karo")
    assert act1 is not None
    assert act1.service == "security"
    assert act1.action == "enroll_face"

    # 2. Face lock status
    act2 = HinglishNLUParser.parse("face lock status check karo")
    assert act2 is not None
    assert act2.service == "security"
    assert act2.action == "get_status"

    # 3. Disable face lock
    act3 = HinglishNLUParser.parse("face lock band karo")
    assert act3 is not None
    assert act3.service == "security"
    assert act3.action == "disable_auth"

    # 4. Enable face lock
    act4 = HinglishNLUParser.parse("face lock chalu karo")
    assert act4 is not None
    assert act4.service == "security"
    assert act4.action == "enable_auth"


def test_app_routing_face_auth_status():
    core = JarvisCore()
    resp = core.process_input("face lock status")
    assert "Face Authentication" in resp
    assert "active" in resp or "enabled" in resp


def test_gui_face_auth_dialog():
    """Headless test for PySide6 FaceAuthDialog initialization."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from gui.dialogs.face_auth_dialog import FaceAuthDialog
    auth = FaceAuthenticator()
    dialog = FaceAuthDialog(authenticator=auth)

    assert dialog.windowTitle() == "JARVIS // Biometric Identity Gateway"
    assert dialog.user_name == auth.user_name

    # Test PIN unlock inside dialog
    dialog.pin_input.setText("1234")
    dialog._verify_pin()
    assert dialog.is_authenticated is True
    assert dialog.auth_method == "master_passcode"
    dialog.close()


def test_gui_face_register_dialog(temp_profile, mock_face_frame):
    """Test interactive PySide6 FaceRegisterDialog."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from gui.dialogs.face_register_dialog import FaceRegisterDialog
    auth = FaceAuthenticator(profile_path=temp_profile)
    dialog = FaceRegisterDialog(authenticator=auth)

    assert dialog.windowTitle() == "JARVIS // Biometric Profile Registration"
    assert dialog.name_input.text() == "Boss"

    # Simulate camera frame capture and registration
    dialog._current_frame = mock_face_frame
    dialog.name_input.setText("AdminBoss")
    dialog._start_capture()

    assert dialog.is_enrolled is True
    assert auth.has_enrolled_profile() is True
    assert auth.user_name == "AdminBoss"
    dialog.close()
