# tests/test_plugin_email.py
"""Automated unit and verification tests for upgraded Email plugin."""

import os
import pytest
from plugins.email.plugin import EmailPlugin


@pytest.fixture
def email_plugin(tmp_path, monkeypatch):
    plugin = EmailPlugin()
    plugin.store_path = str(tmp_path / "email_store.json")
    plugin._ensure_store()
    return plugin


def test_email_manifest_and_health(email_plugin):
    manifest = email_plugin.get_manifest()
    assert manifest.name == "email"
    assert len(manifest.actions) == 13

    health = email_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 13


def test_email_validation(email_plugin):
    res_valid = email_plugin.execute("validate_email_address", {"email": "boss@jarvis.ai"})
    assert res_valid.success is True
    assert res_valid.data["valid"] is True

    res_invalid = email_plugin.execute("validate_email_address", {"email": "not-an-email"})
    assert res_invalid.success is False


def test_mailto_url_generation(email_plugin):
    res = email_plugin.execute("create_mailto_url", {
        "recipient": "dev@example.com",
        "subject": "Status Report",
        "body": "Everything is ready."
    })
    assert res.success is True
    url = res.data["url"]
    assert url.startswith("mailto:dev@example.com")
    assert "Status%20Report" in url


def test_draft_lifecycle(email_plugin):
    # Compose / save draft
    res_save = email_plugin.execute("save_local_draft", {
        "recipient": "team@example.com",
        "subject": "Sprint Review",
        "body": "Let's review the sprint."
    })
    assert res_save.success is True
    draft_id = res_save.data["draft"]["id"]

    # List drafts
    res_list = email_plugin.execute("list_local_drafts", {})
    assert res_list.success is True
    assert res_list.data["count"] >= 1

    # Delete draft
    res_del = email_plugin.execute("delete_local_draft", {"draft_id": draft_id})
    assert res_del.success is True


def test_export_eml(email_plugin, tmp_path):
    eml_file = str(tmp_path / "test_draft.eml")
    res = email_plugin.execute("export_draft_to_eml", {
        "recipient": "client@example.com",
        "subject": "Proposal",
        "body": "Here is the proposal.",
        "output_path": eml_file
    })
    assert res.success is True
    assert os.path.isfile(eml_file)
    assert os.path.getsize(eml_file) > 0


def test_template_management(email_plugin):
    res = email_plugin.execute("create_email_template", {
        "name": "meeting_invite",
        "subject_template": "Meeting: {topic}",
        "body_template": "Hi {name}, please attend the meeting at {time}."
    })
    assert res.success is True
    assert res.data["template"]["name"] == "meeting_invite"
