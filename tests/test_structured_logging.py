# tests/test_structured_logging.py
"""Unit tests for Professional Structured Action Logging and Activity Log Buffer."""

import pytest
from core.logger import LogBuffer, LogEntry, StructuredActionLogger
from main import create_jarvis


def test_structured_action_logger_formatting():
    buffer = LogBuffer(max_size=50)
    logger = StructuredActionLogger(buffer=buffer)

    # 1. INPUT
    e1 = logger.log_input("Jarvis Excel kholo")
    assert e1.level == "INPUT"
    assert e1.category == "INPUT"
    assert e1.message == "Jarvis Excel kholo"

    # 2. INTENT
    e2 = logger.log_intent("open_app", confidence=0.95)
    assert e2.level == "INTENT"
    assert "open_app" in e2.message

    # 3. PLUGIN
    e3 = logger.log_plugin("windows")
    assert e3.level == "PLUGIN"
    assert e3.message == "windows"

    # 4. ACTION
    e4 = logger.log_action("launch_app", {"app_name": "excel"})
    assert e4.level == "ACTION"
    assert "launch_app" in e4.message

    # 5. SUCCESS
    e5 = logger.log_success("Excel opened", execution_time_ms=2.5)
    assert e5.level == "SUCCESS"
    assert "2.50ms" in e5.message

    # 6. MEMORY
    e6 = logger.log_memory("workflow_success")
    assert e6.level == "MEMORY"
    assert "workflow_success" in e6.message

    # Verify buffer contents
    entries = buffer.get_entries()
    assert len(entries) == 6


def test_log_buffer_level_and_search_filtering():
    buffer = LogBuffer(max_size=50)
    logger = StructuredActionLogger(buffer=buffer)

    logger.log_input("Play movie")
    logger.log_intent("play_media")
    logger.log_plugin("vlc")
    logger.log_action("play_file", {"path": "Inception.mp4"})
    logger.log_success("Playing Inception in VLC", execution_time_ms=5.1)
    logger.log_error("Failed to connect Bluetooth")

    # Filter by level
    errors = buffer.get_entries(level_filter="ERROR")
    assert len(errors) == 1
    assert "Bluetooth" in errors[0].message

    actions = buffer.get_entries(level_filter="ACTION")
    assert len(actions) == 1
    assert "play_file" in actions[0].message

    # Filter by search
    vlc_entries = buffer.get_entries(search="vlc")
    assert len(vlc_entries) >= 2


def test_live_pipeline_action_logging(tmp_path):
    """Verifies that running process_input logs structured steps in the action logger."""
    import os
    import shutil
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = os.path.join(tmp_path, "log_test.db").replace("\\", "/")
    cfg_content = f"""
system:
  name: "JARVIS_LOG_TEST"
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

    jarvis = create_jarvis(str(cfg_file))
    jarvis.action_logger.buffer.clear()

    resp = jarvis.process_input("Jarvis, Volume 50 karo")
    assert "50%" in resp

    entries = jarvis.action_logger.buffer.get_entries()
    levels = [e.level for e in entries]
    assert "INPUT" in levels
    assert "SUCCESS" in levels
