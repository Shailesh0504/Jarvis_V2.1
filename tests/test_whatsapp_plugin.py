# tests/test_whatsapp_plugin.py
"""
Comprehensive Regression Tests for Jarvis WhatsApp Plugin.
Validates:
- Local Contact Book resolution & alias matching
- Ambiguity detection & clarification when multiple contacts share similar names
- Draft vs. Send distinction & confirmation workflows
- Cancellation of active drafts
- Zero-API WhatsApp Web and Desktop URI protocol generation
- Voice/Video call initiating
- Natural Hindi, Hinglish, and English message extraction
- End-to-end integration through JarvisCore
"""

import os
from unittest.mock import patch
import pytest
from plugins.whatsapp.models import WhatsAppContact, WhatsAppMessageDraft, WhatsAppActionType
from plugins.whatsapp.contacts import ContactBook
from plugins.whatsapp.automation import WhatsAppAutomationEngine
from plugins.whatsapp.plugin import WhatsAppPlugin
from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager


@pytest.fixture
def contact_book(tmp_path):
    db_path = str(tmp_path / "test_contacts.db")
    return ContactBook(db_path=db_path)


@pytest.fixture
def wa_engine(contact_book):
    return WhatsAppAutomationEngine(contact_book=contact_book)


@pytest.fixture
def wa_plugin():
    return WhatsAppPlugin()


@pytest.fixture
def core_app(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_wa_app.db")
    mem = MemoryManager(db_path=db_path)
    llm = MockLLMProvider()
    resp_gen = ResponseGenerator(llm_provider=llm)
    plugins = PluginManager(plugin_dir="plugins")
    plugins.discover_and_load()

    core.initialize_subsystems(
        memory_manager=mem,
        learning_manager=None,
        brain=resp_gen,
        classifier=None,
        plugin_manager=plugins,
        response_generator=resp_gen
    )
    return core


def test_contact_book_resolution_and_aliases(contact_book):
    """Verifies contact resolution for exact names and aliases."""
    # 1. Alias "mom" -> Mummy
    mom, _ = contact_book.resolve_contact("mom")
    assert mom is not None
    assert mom.name == "Mummy"
    assert mom.phone_number == "+919876543210"

    # 2. Alias "dad" -> Papa
    dad, _ = contact_book.resolve_contact("dad")
    assert dad is not None
    assert dad.name == "Papa"

    # 3. Direct Phone number
    phone_c, _ = contact_book.resolve_contact("+919999999999")
    assert phone_c is not None
    assert phone_c.phone_number == "+919999999999"


def test_ambiguous_contact_resolution(contact_book, wa_engine):
    """Verifies that multiple contacts with similar names trigger clarification instead of guessing."""
    # Add a second Rahul
    contact_book.add_contact(WhatsAppContact(
        name="Rahul Verma",
        phone_number="+919876543299",
        aliases=["rahul v"]
    ))

    # Query for "Rahul"
    resolved, candidates = contact_book.resolve_contact("Rahul")
    assert resolved is None
    assert len(candidates) >= 2

    # Verify Automation Engine returns clarification request
    res = wa_engine.open_chat("Rahul")
    assert res.success is False
    assert res.needs_clarification is True
    assert len(res.clarification_options) >= 2
    assert "multiple contacts hain" in res.formatted_answer


def test_draft_message_workflow_and_cancellation(wa_engine):
    """Verifies message drafting and explicit cancellation."""
    # 1. Draft a message
    res = wa_engine.draft_message("Mummy", "Main 10 minute late aaunga")
    assert res.success is True
    assert res.draft is not None
    assert res.draft.status == "drafted"
    assert res.draft.requires_confirmation is True
    assert "Drafted" in res.formatted_answer

    # 2. Cancel draft
    cancel_res = wa_engine.cancel_current_draft()
    assert cancel_res.success is True
    assert "cancel" in cancel_res.formatted_answer


def test_send_message_url_generation(wa_engine):
    """Verifies WhatsApp Web pre-filled URL formatting."""
    res = wa_engine.send_message("Mummy", "Main nikal gaya", confirmed=True)
    assert res.success is True
    assert "web.whatsapp.com/send" in res.url
    assert "phone=919876543210" in res.url
    assert "text=Main+nikal+gaya" in res.url


def test_call_contact_initiator(wa_engine):
    """Verifies voice call initiation."""
    res = wa_engine.call_contact("Papa", video=False)
    assert res.success is True
    assert "Papa" in res.formatted_answer
    assert "Voice Call" in res.formatted_answer


def test_search_chat_and_draft_vs_send_distinction(wa_engine):
    """Verifies search chat and strictly separates drafting from sending."""
    # Search
    search_res = wa_engine.search_chat("project proposal")
    assert search_res.success is True
    assert "project proposal" in search_res.formatted_answer

    # Draft does NOT mark as sent
    draft_res = wa_engine.draft_message("Priya", "Can we review the document tomorrow?")
    assert draft_res.success is True
    assert draft_res.draft.status == "drafted"
    assert draft_res.draft.requires_confirmation is True

    # Send dispatches
    send_res = wa_engine.send_message("Priya", "Can we review the document tomorrow?", confirmed=True)
    assert send_res.success is True
    assert send_res.draft.status == "sent"


@patch("webbrowser.open")
@patch("os.startfile", create=True)
def test_end_to_end_core_whatsapp_routing(mock_startfile, mock_web_open, core_app):
    """Verifies natural Hindi/Hinglish requests routed through JarvisCore."""
    # 1. Hindi message with "ki"
    resp1 = core_app.process_input("Jarvis, Mummy ko message karo ki main 10 minute late aaunga")
    assert "Mummy" in resp1
    assert "10 minute late" in resp1
    assert "Main samajh gaya Boss! Bataiye" not in resp1

    # 2. Hindi message with "WhatsApp par hi bhejo"
    resp2 = core_app.process_input("Jarvis, Rahul ko WhatsApp par hi bhejo")
    assert "Rahul" in resp2

    # 3. Open WhatsApp
    resp3 = core_app.process_input("Jarvis, WhatsApp kholo")
    assert "WhatsApp" in resp3

    # 4. Open Chat
    resp4 = core_app.process_input("Jarvis, Priya ka chat kholo")
    assert "Priya" in resp4

    # 5. Call on WhatsApp
    resp5 = core_app.process_input("Jarvis, Rahul ko call karo")
    assert "Rahul" in resp5

    # 6. Search on WhatsApp
    resp6 = core_app.process_input("Jarvis, WhatsApp par search karo project files")
    assert "WhatsApp" in resp6 or "project files" in resp6

    # 7. Draft message
    resp7 = core_app.process_input("Jarvis, draft karo Priya ke liye ki kal milte hain")
    assert "Priya" in resp7 or "Draft" in resp7
