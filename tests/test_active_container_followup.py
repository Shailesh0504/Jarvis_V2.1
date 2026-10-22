"""Tests for Active Container Follow-up (workflow-lock continuity across turns).
================================================================================
Verifies that after an app / site container is active, a deictic follow-up
("usme <thing> kholo", "isme <site> kholo") is interpreted *within that container*
instead of being re-classified — and that ambiguity triggers slot filling.

Scenario under test (the reported defect):
    User : Excel open karo
    Jarvis: Microsoft Excel open ho gaya.
    User : usme report file kholo
    Jarvis: kaunsi file?          <- must ASK, not treat "usme report" as a path
"""

import os
import shutil

import pytest

from main import create_jarvis


@pytest.fixture
def jarvis_container(tmp_path, monkeypatch):
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    db_path = os.path.join(tmp_path, "container.db").replace("\\", "/")
    cfg_content = f"""
system:
  name: "JARVIS_CONTAINER_TEST"
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
    return create_jarvis(str(cfg_file)), workspace


# ---------------------------------------------------------------------------
# Document container (the reported scenario)
# ---------------------------------------------------------------------------

class TestDocumentContainerFollowup:
    def test_excel_then_ambiguous_report_asks_which_file(self, jarvis_container):
        jarvis, ws = jarvis_container
        (ws / "report_q1.xlsx").write_text("a,b\n1,2\n")
        (ws / "report_q2.xlsx").write_text("a,b\n3,4\n")

        resp1 = jarvis.process_input("Excel open karo")
        assert "excel" in resp1.lower()

        resp2 = jarvis.process_input("usme report file kholo")
        # Must ask for the file, and must never treat "usme report" as a path.
        assert "Kaunsi file kholni hai" in resp2
        assert "usme" not in resp2.lower()
        assert "does not exist" not in resp2.lower()
        assert "nahi karta" not in resp2.lower()
        # An active workflow lock now owns the conversation.
        assert jarvis.dialog_manager.has_active_lock() is True

        resp3 = jarvis.process_input("report_q1")
        assert "report_q1.xlsx" in resp3
        assert jarvis.dialog_manager.has_active_lock() is False

    def test_excel_then_unique_file_opens_directly(self, jarvis_container):
        jarvis, ws = jarvis_container
        (ws / "budget.xlsx").write_text("a,b\n5,6\n")

        jarvis.process_input("Excel open karo")
        resp = jarvis.process_input("usme budget file kholo")

        assert "budget.xlsx" in resp
        assert jarvis.dialog_manager.has_active_lock() is False

    def test_missing_file_reports_honestly(self, jarvis_container):
        jarvis, ws = jarvis_container
        jarvis.process_input("Excel open karo")
        resp = jarvis.process_input("usme nonexistent_zzz file kholo")

        assert "nahi mili" in resp.lower() or "nahi" in resp.lower()
        assert "does not exist" not in resp.lower()


# ---------------------------------------------------------------------------
# Browser / media / explorer containers
# ---------------------------------------------------------------------------

class TestOtherContainerFollowups:
    def test_browser_container_opens_referenced_site(self, jarvis_container):
        jarvis, _ = jarvis_container
        jarvis.process_input("Chrome open karo")
        resp = jarvis.process_input("usme youtube kholo")

        assert "youtube" in resp.lower()
        assert "chrome" in resp.lower()
        assert "does not exist" not in resp.lower()

    def test_media_container_plays_referenced_file(self, jarvis_container):
        jarvis, ws = jarvis_container
        (ws / "inception.mp4").write_text("fake")
        jarvis.process_input("vlc open karo")
        resp = jarvis.process_input("usme inception chalao")

        assert "inception.mp4" in resp
        assert "path" not in resp.lower()

    def test_explorer_container_resolves_item(self, jarvis_container):
        jarvis, ws = jarvis_container
        (ws / "notes_alpha.txt").write_text("x")
        jarvis.process_input("Explorer open karo")
        resp = jarvis.process_input("usme notes_alpha kholo")

        assert "notes_alpha" in resp
        assert "does not exist" not in resp.lower()


# ---------------------------------------------------------------------------
# Guards: must NOT hijack unrelated utterances
# ---------------------------------------------------------------------------

class TestContainerFollowupGuards:
    def test_plain_command_after_launch_is_untouched(self, jarvis_container):
        jarvis, _ = jarvis_container
        jarvis.process_input("Excel open karo")
        resp = jarvis.process_input("volume 30 karo")

        assert "volume" in resp.lower()
        assert jarvis.dialog_manager.has_active_lock() is False

    def test_second_app_launch_still_works(self, jarvis_container):
        jarvis, _ = jarvis_container
        jarvis.process_input("Excel open karo")
        resp = jarvis.process_input("Chrome kholo")

        assert "chrome" in resp.lower()
        assert jarvis.dialog_manager.has_active_lock() is False

    def test_no_container_means_no_interception(self, jarvis_container):
        jarvis, _ = jarvis_container
        # No app/site opened yet -> the follow-up is not a container request.
        assert jarvis.dialog_manager.is_container_followup("usme report file kholo", jarvis) is False
        assert jarvis.dialog_manager.has_active_container(jarvis) is False

    def test_pronoun_without_action_verb_is_not_container_followup(self, jarvis_container):
        jarvis, _ = jarvis_container
        jarvis.process_input("Excel open karo")
        # No open/action verb -> not our business.
        assert jarvis.dialog_manager.is_container_followup("usme kuch nahi hai", jarvis) is False

    def test_existing_multi_turn_desktop_task_not_hijacked(self, jarvis_container):
        """Chained desktop-task continuations must keep reaching the desktop coordinator."""
        jarvis, ws = jarvis_container
        jarvis.process_input("test folder ke under ek text file banao")
        resp = jarvis.process_input("usme ek aur file banao")
        # Handled (by whatever owns it) without a bogus container-open ambiguity prompt.
        assert "Kaunsi file kholni hai" not in resp
