# tests/test_dual_brain.py
"""Comprehensive tests for Fast Brain (System 1) and Smart Brain (System 2)."""

import os
import shutil
import pytest
from main import create_jarvis


@pytest.fixture
def jarvis_dual(tmp_path):
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = os.path.join(tmp_path, "dual_brain.db").replace("\\", "/")
    cfg_content = f"""
system:
  name: "JARVIS_DUAL_TEST"
memory:
  db_path: "{db_path}"
brain:
  llm_provider: "mock"
plugins:
  plugin_dir: "{str(temp_plugins).replace('\\', '/')}"
  auto_load: true
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(cfg_content)

    return create_jarvis(str(cfg_file))


def test_fast_brain_app_launch(jarvis_dual):
    """Fast Brain: 'Chrome kholo' executes immediately."""
    resp = jarvis_dual.process_input("Chrome kholo")
    assert "Launched 'chrome' successfully" in resp or "chrome" in resp.lower()


def test_fast_brain_volume_control(jarvis_dual):
    """Fast Brain: 'Volume 50 karo' sets system volume."""
    resp = jarvis_dual.process_input("Volume 50 karo")
    assert "50%" in resp


def test_fast_brain_screenshot(jarvis_dual):
    """Fast Brain: 'Screenshot lo' captures screen snapshot."""
    resp = jarvis_dual.process_input("Screenshot lo")
    assert "Screenshot taken" in resp


def test_fast_brain_vlc_play(jarvis_dual):
    """Fast Brain: 'VLC play karo' starts playback."""
    resp = jarvis_dual.process_input("VLC play karo")
    assert "VLC" in resp or "playback" in resp.lower()


def test_fast_brain_shutdown(jarvis_dual):
    """Fast Brain: 'Computer shutdown karo' issues shutdown signal."""
    resp = jarvis_dual.process_input("Computer shutdown karo")
    assert "shutdown" in resp.lower() or "initiated" in resp.lower()


def test_smart_brain_downloads_organization_and_duplicate_report(jarvis_dual, tmp_path):
    """Smart Brain: 'Mere downloads folder ko organize kar do aur duplicate files ka report bana do.'"""
    # Create test downloads directory with sample files and a duplicate
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir()

    (downloads_dir / "invoice.pdf").write_text("Invoice data 123")
    (downloads_dir / "invoice_copy.pdf").write_text("Invoice data 123") # exact duplicate
    (downloads_dir / "photo.jpg").write_text("Image JPEG binary content")
    (downloads_dir / "track.mp3").write_text("Audio MP3 content")
    (downloads_dir / "script.py").write_text("print('hello')")

    query = f"Mere {str(downloads_dir).replace(chr(92), '/')} directory ko organize kar do aur duplicate files ka report bana do"

    # Process through Smart Brain
    resp = jarvis_dual.process_input(query)

    assert "SMART BRAIN EXECUTION REPORT" in resp
    assert "Total Files Categorized" in resp
    assert "Duplicate Files Scan" in resp
    assert "Duplicates Found: 1" in resp
    assert "invoice_copy.pdf" in resp or "invoice.pdf" in resp
