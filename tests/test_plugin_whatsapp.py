# tests/test_plugin_whatsapp.py
"""Tests for WhatsAppPlugin covering original and newly added actions."""

import os
import pytest
from plugins.whatsapp.plugin import WhatsAppPlugin


@pytest.fixture
def plugin(tmp_path):
    p = WhatsAppPlugin()
    p.engine.contact_book.db_path = str(tmp_path / "whatsapp_contacts.db")
    p.engine.contact_book._init_db()
    return p


def test_whatsapp_manifest(plugin):
    manifest = plugin.get_manifest()
    assert manifest.name == "whatsapp"
    action_names = {a.name for a in manifest.actions}
    expected = {
        "open_whatsapp",
        "open_chat",
        "draft_message",
        "send_message",
        "search_chat",
        "call_contact",
        "cancel_action",
        "add_contact",
        "list_contacts",
        "delete_contact",
        "generate_chat_link",
        "queue_scheduled_message",
        "list_scheduled_messages",
        "cancel_scheduled_message",
        "validate_phone_number",
        "export_contacts_vcard",
        "import_contacts_vcard"
    }
    assert expected.issubset(action_names)


def test_whatsapp_contact_management(plugin):
    # Add Contact
    res_add = plugin.execute("add_contact", {
        "name": "Karan Singhania",
        "phone_number": "+919811223344",
        "relationship": "client",
        "aliases": ["karan", "singhania"],
        "is_trusted": True
    })
    assert res_add.success is True
    assert res_add.data["name"] == "Karan Singhania"

    # List Contacts
    res_list = plugin.execute("list_contacts", {})
    assert res_list.success is True
    assert res_list.data["count"] >= 1
    names = [c["name"] for c in res_list.data["contacts"]]
    assert "Karan Singhania" in names

    # Delete Contact
    res_del = plugin.execute("delete_contact", {"name": "Karan Singhania"})
    assert res_del.success is True

    # Confirm deletion
    res_list_after = plugin.execute("list_contacts", {})
    names_after = [c["name"] for c in res_list_after.data["contacts"]]
    assert "Karan Singhania" not in names_after


def test_whatsapp_chat_link_and_validation(plugin):
    # Generate chat link
    res_link = plugin.execute("generate_chat_link", {
        "phone_number": "+91 98765-43210",
        "message": "Hello from Jarvis!"
    })
    assert res_link.success is True
    assert "wa.me/919876543210" in res_link.data["link"]
    assert "Hello%20from%20Jarvis%21" in res_link.data["link"]

    # Validate phone valid 10-digit
    res_val = plugin.execute("validate_phone_number", {"phone_number": "9876543210", "default_country_code": "+91"})
    assert res_val.success is True
    assert res_val.data["is_valid"] is True
    assert res_val.data["formatted"] == "+919876543210"

    # Validate phone invalid
    res_inv = plugin.execute("validate_phone_number", {"phone_number": "123"})
    assert res_inv.success is True
    assert res_inv.data["is_valid"] is False


def test_whatsapp_scheduling_workflow(plugin):
    # Queue scheduled message
    res_queue = plugin.execute("queue_scheduled_message", {
        "recipient": "Mummy",
        "message": "Good morning!",
        "scheduled_time": "2026-09-06T08:00:00Z"
    })
    assert res_queue.success is True
    assert "scheduled_item" in res_queue.data
    msg_id = res_queue.data["scheduled_item"]["id"]

    # List scheduled messages
    res_outbox = plugin.execute("list_scheduled_messages", {})
    assert res_outbox.success is True
    assert res_outbox.data["count"] >= 1

    # Cancel scheduled message
    res_cancel = plugin.execute("cancel_scheduled_message", {"message_id": msg_id})
    assert res_cancel.success is True


def test_whatsapp_vcard_export_import(plugin, tmp_path):
    vcf_path = str(tmp_path / "contacts.vcf")

    # Export to vCard
    res_exp = plugin.execute("export_contacts_vcard", {"output_path": vcf_path})
    assert res_exp.success is True
    assert os.path.exists(vcf_path)

    # Import from vCard
    res_imp = plugin.execute("import_contacts_vcard", {"file_path": vcf_path})
    assert res_imp.success is True
    assert res_imp.data["imported_count"] >= 1


def test_whatsapp_draft_and_cancel(plugin):
    res_draft = plugin.execute("draft_message", {"recipient": "Mummy", "message": "Arriving home at 7 PM"})
    assert res_draft.success is True
    assert res_draft.data["draft"]["status"] == "drafted"

    res_cancel = plugin.execute("cancel_action", {})
    assert res_cancel.success is True
