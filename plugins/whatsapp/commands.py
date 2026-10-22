# plugins/whatsapp/commands.py
"""
Command actions and definitions for the WhatsApp Plugin.
"""

from typing import Any, Dict, List, Optional
from core.permissions import PermissionLevel
from plugins.manifest import PluginAction, PluginParameter
from .automation import WhatsAppAutomationEngine
from .models import WhatsAppActionResult

ACTIONS = [
    PluginAction(
        name="open_whatsapp",
        description="Launches WhatsApp Desktop or WhatsApp Web",
        keywords=["open whatsapp", "whatsapp kholo", "launch whatsapp", "start whatsapp"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="open_chat",
        description="Opens a conversation with a specific contact",
        keywords=["open chat", "chat kholo", "chat open karo"],
        parameters=[
            PluginParameter(name="recipient", type="string", description="Contact name or phone number", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="draft_message",
        description="Drafts a WhatsApp message for review prior to sending",
        keywords=["draft message", "message draft karo", "draft karo"],
        parameters=[
            PluginParameter(name="recipient", type="string", description="Recipient contact name", required=True),
            PluginParameter(name="message", type="string", description="Message text content", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="send_message",
        description="Sends or dispatches a WhatsApp message to a recipient",
        keywords=["send message", "message bhejo", "message karo", "whatsapp karo", "whatsapp bhejo"],
        parameters=[
            PluginParameter(name="recipient", type="string", description="Recipient contact name", required=True),
            PluginParameter(name="message", type="string", description="Message text content", required=True),
            PluginParameter(name="confirmed", type="boolean", description="Whether user explicitly confirmed sending", required=False, default=False)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=None
    ),
    PluginAction(
        name="search_chat",
        description="Searches messages or contacts inside WhatsApp",
        keywords=["search whatsapp", "whatsapp par search karo", "search chat"],
        parameters=[
            PluginParameter(name="query", type="string", description="Search keyword or contact name", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="call_contact",
        description="Initiates a voice or video call on WhatsApp",
        keywords=["call on whatsapp", "whatsapp call karo", "call karo"],
        parameters=[
            PluginParameter(name="recipient", type="string", description="Contact name or phone number", required=True),
            PluginParameter(name="video", type="boolean", description="Whether to start video call", required=False, default=False)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=None
    ),
    PluginAction(
        name="cancel_action",
        description="Cancels an active WhatsApp draft or action",
        keywords=["cancel draft", "cancel message", "mat bhejo", "cancel karo"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="add_contact",
        description="Adds a new contact to the local WhatsApp address book",
        keywords=["add whatsapp contact", "save contact", "naya contact save karo"],
        parameters=[
            PluginParameter(name="name", type="string", description="Contact name", required=True),
            PluginParameter(name="phone_number", type="string", description="Phone number with country code", required=True),
            PluginParameter(name="relationship", type="string", description="Relationship (friend, colleague, family)", required=False, default="contact"),
            PluginParameter(name="aliases", type="list", description="Alternative names / nicknames", required=False, default=[]),
            PluginParameter(name="is_trusted", type="boolean", description="Whether contact is trusted for quick send", required=False, default=False)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=None
    ),
    PluginAction(
        name="list_contacts",
        description="Lists all saved contacts in the local WhatsApp address book",
        keywords=["list contacts", "all contacts", "whatsapp contacts", "contacts dikhao"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="delete_contact",
        description="Deletes a contact from the local WhatsApp address book",
        keywords=["delete contact", "remove contact", "contact hatao"],
        parameters=[
            PluginParameter(name="name", type="string", description="Contact name to delete", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=None
    ),
    PluginAction(
        name="generate_chat_link",
        description="Generates a direct Click-to-Chat wa.me link for any phone number",
        keywords=["chat link", "wa.me link", "whatsapp direct link"],
        parameters=[
            PluginParameter(name="phone_number", type="string", description="Target phone number", required=True),
            PluginParameter(name="message", type="string", description="Pre-filled message text", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="queue_scheduled_message",
        description="Schedules a WhatsApp message to be sent at a future time",
        keywords=["schedule whatsapp", "schedule message", "baad mein bhejo"],
        parameters=[
            PluginParameter(name="recipient", type="string", description="Recipient name or number", required=True),
            PluginParameter(name="message", type="string", description="Message content", required=True),
            PluginParameter(name="scheduled_time", type="string", description="Scheduled delivery timestamp (ISO format)", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=None
    ),
    PluginAction(
        name="list_scheduled_messages",
        description="Lists all queued and scheduled WhatsApp messages in the outbox",
        keywords=["scheduled messages", "whatsapp outbox", "pending messages"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="cancel_scheduled_message",
        description="Cancels a queued scheduled WhatsApp message by its ID",
        keywords=["cancel scheduled message", "delete scheduled message"],
        parameters=[
            PluginParameter(name="message_id", type="integer", description="ID of the scheduled message", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=None
    ),
    PluginAction(
        name="validate_phone_number",
        description="Validates and cleans a phone number to standard international E.164 format",
        keywords=["validate phone", "check phone number", "clean phone number"],
        parameters=[
            PluginParameter(name="phone_number", type="string", description="Phone number to validate", required=True),
            PluginParameter(name="default_country_code", type="string", description="Default country code (e.g. +91)", required=False, default="+91")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="export_contacts_vcard",
        description="Exports the local WhatsApp contact book to a standard .vcf (vCard) file",
        keywords=["export vcard", "export contacts vcf", "backup contacts"],
        parameters=[
            PluginParameter(name="output_path", type="string", description="Target .vcf file path", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="import_contacts_vcard",
        description="Imports contacts from a .vcf (vCard) file into the local address book",
        keywords=["import vcard", "import contacts vcf", "load contacts"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Source .vcf file path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=None
    )
]


class WhatsAppCommands:
    """Executable command handlers for the WhatsApp subsystem."""

    def __init__(self, engine: Optional[WhatsAppAutomationEngine] = None):
        self.engine = engine or WhatsAppAutomationEngine()

    def open_whatsapp(self) -> Dict[str, Any]:
        res: WhatsAppActionResult = self.engine.open_whatsapp()
        return res.to_dict()

    def open_chat(self, recipient: str) -> Dict[str, Any]:
        res: WhatsAppActionResult = self.engine.open_chat(recipient)
        return res.to_dict()

    def draft_message(self, recipient: str, message: str) -> Dict[str, Any]:
        res: WhatsAppActionResult = self.engine.draft_message(recipient, message)
        return res.to_dict()

    def send_message(self, recipient: str, message: str, confirmed: bool = False) -> Dict[str, Any]:
        res: WhatsAppActionResult = self.engine.send_message(recipient, message, confirmed=confirmed)
        return res.to_dict()

    def search_chat(self, query: str) -> Dict[str, Any]:
        res: WhatsAppActionResult = self.engine.search_chat(query)
        return res.to_dict()

    def call_contact(self, recipient: str, video: bool = False) -> Dict[str, Any]:
        res: WhatsAppActionResult = self.engine.call_contact(recipient, video=video)
        return res.to_dict()

    def cancel_action(self) -> Dict[str, Any]:
        res: WhatsAppActionResult = self.engine.cancel_current_draft()
        return res.to_dict()
