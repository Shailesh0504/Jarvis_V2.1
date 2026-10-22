# tests/test_learning_5_layers.py
"""Comprehensive tests for the 5 Layers of Learning in Jarvis V2."""

import os
import shutil
import pytest
from main import create_jarvis


@pytest.fixture
def jarvis_learning(tmp_path):
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = os.path.join(tmp_path, "learning_5.db").replace("\\", "/")
    cfg_content = f"""
system:
  name: "JARVIS_LEARNING_TEST"
memory:
  db_path: "{db_path}"
learning:
  enabled: true
  min_habit_frequency: 3
brain:
  llm_provider: "mock"
plugins:
  plugin_dir: "{str(temp_plugins).replace('\\', '/')}"
  auto_load: true
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(cfg_content)

    return create_jarvis(str(cfg_file))


def test_layer_1_preferences(jarvis_learning):
    """Layer 1: User preferences (language style, conciseness, defaults)."""
    pref = jarvis_learning.learning_manager.preferences

    # Check defaults
    assert pref.get("language_style") == "hinglish"
    assert pref.get("preferred_browser") == "chrome"

    # Set custom preference
    pref.set("conciseness", "ultra_concise")
    pref.set("response_language", "hindi")

    assert pref.get("conciseness") == "ultra_concise"
    assert pref.get("response_language") == "hindi"


def test_layer_2_vocabulary(jarvis_learning):
    """Layer 2: Custom user vocabulary & synonym resolution."""
    vocab = jarvis_learning.learning_manager.vocabulary

    # Baseline defaults
    assert vocab.get_term("browser") == "chrome"
    assert vocab.get_term("movie") == "vlc"

    # Text resolution
    resolved = vocab.resolve_text("open browser and play movie")
    assert "chrome" in resolved
    assert "vlc" in resolved

    # Learn custom term
    vocab.learn_term("editor", "code")
    assert vocab.resolve_text("open editor") == "open code"


def test_layer_3_workflows_excel_clean(jarvis_learning):
    """Layer 3: Multi-step composite workflows."""
    response = jarvis_learning.process_input("Excel clean karo")
    assert "Workflow 'excel_clean' executed successfully" in response
    assert "Select used range" in response
    assert "Auto-fit" in response
    assert "Align text" in response
    assert "Apply standard grid borders" in response
    assert "Remove empty rows" in response
    assert "Save" in response


def test_layer_4_corrections_and_vocabulary_update(jarvis_learning):
    """Layer 4: Real-time correction detection, staging, and approval update of Layer 2 & Layer 1."""
    # Initially browser = chrome
    assert jarvis_learning.learning_manager.vocabulary.get_term("browser") == "chrome"

    # User gives correction: "nahi, Chrome nahi Edge kholo"
    response = jarvis_learning.process_input("nahi, Chrome nahi Edge kholo")

    assert "Previous assumption" in response
    assert "Chrome" in response
    assert "Correction" in response
    assert "Edge" in response
    assert "Kya main ise future ke liye yaad rakhu?" in response

    # User confirms with 'Haan'
    confirm_resp = jarvis_learning.process_input("Haan")
    assert "permanent memory me save kar liya" in confirm_resp

    # Verify Layer 2 vocabulary updated to Edge
    assert jarvis_learning.learning_manager.vocabulary.get_term("browser").lower() == "edge"

    # Verify Layer 1 preference updated to edge
    assert jarvis_learning.learning_manager.preferences.get("preferred_browser").lower() == "edge"


def test_layer_5_habit_and_proactive_suggestion(jarvis_learning):
    """Layer 5: Habit tracking & context-aware proactive suggestion."""
    habits = jarvis_learning.learning_manager.habits

    # Simulate repeated calls to build habit frequency
    for _ in range(3):
        habits.observe("excel_clean", {"action": "clean"})

    # Check proactive suggestion
    suggestion = habits.get_proactive_suggestion("Excel kholo")
    assert suggestion is not None
    assert "Sales folder" in suggestion
    assert "Excel file" in suggestion
