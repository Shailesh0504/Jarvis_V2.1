# tests/test_learning_approval.py
"""Unit tests for Learning Approval System (Human-in-the-Loop Memory & Knowledge Staging)."""

import os
import shutil
import pytest
from learning.approval import ApprovalManager, PendingLearning
from main import create_jarvis


def test_approval_manager_staging_lifecycle(tmp_path):
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = os.path.join(tmp_path, "approval_test.db").replace("\\", "/")
    cfg_content = f"""
system:
  name: "JARVIS_APPROVAL_TEST"
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
    approval = jarvis.learning_manager.approval

    # 1. Stage new candidate
    item = approval.stage_learning(
        layer=2,
        pattern_type="vocabulary",
        original_key="browser",
        proposed_val="edge",
        confidence=0.91
    )
    assert item.status == "PENDING"
    assert item.confidence == 0.91
    assert len(approval.get_pending_learnings()) == 1

    # Before approval, permanent vocabulary should still be default chrome
    assert jarvis.learning_manager.vocabulary.get_term("browser") == "chrome"

    # 2. Programmatic GUI Accept
    accepted = approval.accept_learning(item.id)
    assert accepted is True
    assert len(approval.get_pending_learnings()) == 0

    # After approval, permanent vocabulary is updated
    assert jarvis.learning_manager.vocabulary.get_term("browser") == "edge"


def test_conversational_voice_approval_flow(tmp_path):
    """
    Test Conversational Flow:
    1. User gives verbal correction: 'nahi, Chrome nahi Edge kholo'
    2. Jarvis stages candidate and asks: 'Kya main ise future ke liye yaad rakhu?'
    3. User confirms: 'Haan'
    4. Jarvis commits to permanent memory!
    """
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = os.path.join(tmp_path, "voice_approval_test.db").replace("\\", "/")
    cfg_content = f"""
system:
  name: "JARVIS_VOICE_APPROVAL_TEST"
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

    # Initial state: 'browser' -> 'chrome'
    assert jarvis.learning_manager.vocabulary.get_term("browser") == "chrome"

    # 1. Verbal Correction
    correction_resp = jarvis.process_input("nahi, Chrome nahi Edge kholo")
    assert "Kya main ise future ke liye yaad rakhu?" in correction_resp
    assert jarvis.dialog_manager.has_pending_learning() is True

    # 2. User confirms with 'Haan'
    confirm_resp = jarvis.process_input("Haan")
    assert "permanent memory me save kar liya" in confirm_resp
    assert jarvis.dialog_manager.has_pending_learning() is False

    # Permanent memory is now committed to Edge!
    assert jarvis.learning_manager.vocabulary.get_term("browser") == "Edge"


def test_conversational_voice_rejection_flow(tmp_path):
    """
    Test Conversational Flow Rejection:
    1. User gives verbal correction: 'nahi, Chrome nahi Brave kholo'
    2. Jarvis stages candidate and asks: 'Kya main ise future ke liye yaad rakhu?'
    3. User rejects: 'Nahi'
    4. Jarvis discards candidate, permanent memory remains untouched!
    """
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = os.path.join(tmp_path, "voice_rejection_test.db").replace("\\", "/")
    cfg_content = f"""
system:
  name: "JARVIS_VOICE_REJECTION_TEST"
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

    # 1. Verbal Correction
    correction_resp = jarvis.process_input("nahi, Chrome nahi Brave kholo")
    assert "Kya main ise future ke liye yaad rakhu?" in correction_resp
    assert jarvis.dialog_manager.has_pending_learning() is True

    # 2. User rejects with 'Nahi'
    reject_resp = jarvis.process_input("Nahi")
    assert "save nahi kiya" in reject_resp
    assert jarvis.dialog_manager.has_pending_learning() is False

    # Permanent memory still remains default Chrome, not Brave!
    assert jarvis.learning_manager.vocabulary.get_term("browser") == "chrome"
