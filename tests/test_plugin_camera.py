# tests/test_plugin_camera.py
"""Automated unit and verification tests for upgraded Camera plugin."""

import os
import pytest
from plugins.camera.plugin import CameraPlugin


@pytest.fixture
def camera_plugin():
    return CameraPlugin()


def test_camera_manifest_and_health(camera_plugin):
    manifest = camera_plugin.get_manifest()
    assert manifest.name == "camera"
    assert len(manifest.actions) == 12

    health = camera_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 12


def test_generate_test_pattern_and_verify(camera_plugin, tmp_path):
    pattern_path = str(tmp_path / "calibration.png")
    res = camera_plugin.execute("generate_test_pattern", {
        "save_path": pattern_path,
        "width": 320,
        "height": 240
    })
    assert res.success is True
    assert os.path.exists(pattern_path)
    assert os.path.getsize(pattern_path) > 0

    # Test verify_state
    v = camera_plugin.verify_state("generate_test_pattern", {}, res.data)
    assert v is not None
    assert v.verified is True


def test_apply_camera_filters(camera_plugin, tmp_path):
    base_img = str(tmp_path / "base.png")
    camera_plugin.execute("generate_test_pattern", {"save_path": base_img, "width": 200, "height": 150})

    for f_type in ["grayscale", "blur", "edges", "sepia", "invert"]:
        out_f = str(tmp_path / f"out_{f_type}.png")
        res = camera_plugin.execute("apply_camera_filter", {
            "image_path": base_img,
            "filter_type": f_type,
            "save_path": out_f
        })
        assert res.success is True
        assert os.path.exists(out_f)
        assert os.path.getsize(out_f) > 0


def test_detect_qr_code_on_image(camera_plugin, tmp_path):
    base_img = str(tmp_path / "test_qr.png")
    camera_plugin.execute("generate_test_pattern", {"save_path": base_img})

    res = camera_plugin.execute("detect_qr_code", {"image_path": base_img})
    assert res.success is True
    assert res.data["found"] is False


def test_list_camera_devices(camera_plugin):
    res = camera_plugin.execute("list_camera_devices", {"max_devices_to_probe": 2})
    assert res.success is True
    assert "available_devices" in res.data
    assert isinstance(res.data["available_devices"], list)
