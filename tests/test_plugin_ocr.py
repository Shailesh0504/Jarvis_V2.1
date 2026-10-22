# tests/test_plugin_ocr.py
"""Automated unit and verification tests for upgraded OCR plugin."""

import os
from PIL import Image, ImageDraw
import pytest
from plugins.ocr.plugin import OcrPlugin


@pytest.fixture
def sample_image(tmp_path):
    img_path = str(tmp_path / "test_ocr.png")
    img = Image.new("RGB", (200, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 30), "HELLO JARVIS 123", fill=(0, 0, 0))
    img.save(img_path)
    return img_path


def test_ocr_manifest_and_health():
    plugin = OcrPlugin()
    manifest = plugin.get_manifest()
    assert manifest.name == "ocr"
    assert len(manifest.actions) == 12

    health = plugin.get_health_status()
    assert "status" in health
    assert health["actions_count"] == 12


def test_ocr_engine_check():
    plugin = OcrPlugin()
    res = plugin.execute("check_ocr_engine_available", {})
    assert res.success is True
    assert "pytesseract_installed" in res.data
    assert res.data["pytesseract_installed"] is True


def test_get_image_dimensions(sample_image):
    plugin = OcrPlugin()
    res = plugin.execute("get_image_dimensions", {"image_path": sample_image})
    assert res.success is True
    assert res.data["width"] == 200
    assert res.data["height"] == 80
    assert res.data["format"] == "PNG"

    # Missing file test
    res_bad = plugin.execute("get_image_dimensions", {"image_path": "nonexistent.png"})
    assert res_bad.success is False


def test_preprocess_image(sample_image, tmp_path):
    plugin = OcrPlugin()
    out_enhanced = str(tmp_path / "enhanced.png")
    res = plugin.execute("preprocess_image_for_ocr", {
        "image_path": sample_image,
        "output_path": out_enhanced
    })
    assert res.success is True
    assert os.path.isfile(out_enhanced)
    assert os.path.getsize(out_enhanced) > 0


def test_batch_ocr_empty_or_missing_dir(tmp_path):
    plugin = OcrPlugin()
    empty_dir = str(tmp_path / "empty_folder")
    os.makedirs(empty_dir, exist_ok=True)
    res = plugin.execute("batch_ocr_images", {"directory_path": empty_dir})
    assert res.success is True
    assert res.data["files_processed"] == 0

    res_missing = plugin.execute("batch_ocr_images", {"directory_path": "invalid_dir_path_xyz"})
    assert res_missing.success is False
