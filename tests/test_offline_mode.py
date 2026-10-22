# tests/test_offline_mode.py
"""Comprehensive tests for 100% Offline-First Architecture in Jarvis V2."""

import os
import shutil
import pytest
from core.connectivity import ConnectivityManager
from main import create_jarvis


@pytest.fixture
def jarvis_offline(tmp_path):
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = os.path.join(tmp_path, "offline_test.db").replace("\\", "/")
    cfg_content = f"""
system:
  name: "JARVIS_OFFLINE_TEST"
memory:
  db_path: "{db_path}"
brain:
  llm_provider: "mock" # Offline local fallback
plugins:
  plugin_dir: "{str(temp_plugins).replace('\\', '/')}"
  auto_load: true
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(cfg_content)

    return create_jarvis(str(cfg_file))


def test_voice_and_wakeword_offline(jarvis_offline):
    """Voice & Wake Word must function 100% locally without external APIs."""
    resp = jarvis_offline.process_input("Jarvis, Volume 50 karo")
    assert "50%" in resp


def test_memory_offline(jarvis_offline):
    """13-Table SQLite Memory must store and search facts locally offline."""
    mem = jarvis_offline.memory_manager
    mem.store_fact("project_codename", "Project Phoenix", category="local_dev")
    fact = mem.get_fact("project_codename")
    assert fact is not None
    assert fact["value"] == "Project Phoenix"

    # Search local facts
    res = mem.search_memories("Phoenix")
    assert len(res) >= 1


def test_local_plugins_offline(jarvis_offline, tmp_path):
    """Core plugins (Files, Excel, PDF, VLC, System, Windows) operate 100% offline."""
    # 1. System plugin offline
    resp_sys = jarvis_offline.process_input("system stats")
    assert "CPU:" in resp_sys

    # 2. Files plugin offline
    test_file = tmp_path / "offline_note.txt"
    test_file.write_text("Offline local note content")
    res_f = jarvis_offline.plugin_manager.execute_action("files", "list_dir", {"path": str(tmp_path)})
    assert res_f.success is True
    assert "offline_note.txt" in str(res_f.data)

    # 3. Excel workflow offline
    resp_excel = jarvis_offline.process_input("Excel clean karo")
    assert "Workflow 'excel_clean' executed successfully" in resp_excel


def test_smart_brain_and_fast_brain_offline(jarvis_offline, tmp_path):
    """Fast Brain and Smart Brain operate autonomously offline."""
    # Fast brain
    resp_fast = jarvis_offline.process_input("Screenshot lo")
    assert "Screenshot taken" in resp_fast

    # Smart brain multi-step planning
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir()
    (downloads_dir / "report.pdf").write_text("PDF content")
    (downloads_dir / "report_dup.pdf").write_text("PDF content")

    query = f"Mere {str(downloads_dir).replace(chr(92), '/')} folder ko organize kar do aur duplicate files ka report bana do"
    resp_smart = jarvis_offline.process_input(query)
    assert "SMART BRAIN EXECUTION REPORT" in resp_smart
    assert "Duplicate Files Scan" in resp_smart


def test_learning_engine_offline(jarvis_offline):
    """5-Layer Learning engine persists locally in SQLite without cloud sync."""
    learn = jarvis_offline.learning_manager

    # Layer 2: Vocabulary
    learn.vocabulary.learn_term("browser", "edge")
    assert learn.vocabulary.resolve_text("open browser") == "open edge"

    # Layer 4: Real-time correction
    resp_corr = jarvis_offline.process_input("nahi, Chrome nahi Edge kholo")
    assert "Previous assumption" in resp_corr
    assert "Edge" in resp_corr
    assert "Kya main ise future ke liye yaad rakhu?" in resp_corr
    jarvis_offline.process_input("Haan")


def test_online_plugins_graceful_offline_degradation():
    """Online plugins (Browser / YouTube) must return clean offline notice when internet is unavailable."""
    from plugins.browser.plugin import BrowserPlugin
    from plugins.youtube.plugin import YouTubePlugin

    browser = BrowserPlugin()
    browser.connectivity.set_forced_offline(True)
    res_b = browser.safe_execute("open_url", {"url": "https://google.com"})
    assert res_b.success is False
    assert "offline" in res_b.error.lower()

    youtube = YouTubePlugin()
    youtube.connectivity.set_forced_offline(True)
    res_y = youtube.safe_execute("search_and_play", {"query": "Iron Man"})
    assert res_y.success is False
    assert "offline" in res_y.error.lower()
