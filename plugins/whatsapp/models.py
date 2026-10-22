# plugins/whatsapp/models.py
"""
Data Models for Jarvis V2 WhatsApp Plugin.
"""

from dataclasses import dataclass, field
import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class WhatsAppActionType(str, Enum):
    OPEN_WHATSAPP = "open_whatsapp"
    OPEN_CHAT = "open_chat"
    DRAFT_MESSAGE = "draft_message"
    SEND_MESSAGE = "send_message"
    READ_MESSAGES = "read_messages"
    SEARCH_CHAT = "search_chat"
    CALL_CONTACT = "call_contact"
    CANCEL_ACTION = "cancel_action"
    MANAGE_CONTACT = "manage_contact"


@dataclass
class WhatsAppContact:
    """Represents a saved or resolved local contact."""
    name: str
    phone_number: Optional[str] = None
    relationship: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    is_trusted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "phone_number": self.phone_number,
            "relationship": self.relationship,
            "aliases": self.aliases,
            "is_trusted": self.is_trusted
        }


@dataclass
class WhatsAppMessageDraft:
    """Represents a composed message draft prior to sending."""
    recipient_name: str
    phone_number: Optional[str]
    message_text: str
    status: str = "drafted" # drafted, pending_confirmation, sent, cancelled
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    requires_confirmation: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recipient_name": self.recipient_name,
            "phone_number": self.phone_number,
            "message_text": self.message_text,
            "status": self.status,
            "created_at": self.created_at,
            "requires_confirmation": self.requires_confirmation
        }


@dataclass
class WhatsAppActionResult:
    """Standardized structured outcome of a WhatsApp plugin action."""
    success: bool
    action: WhatsAppActionType
    formatted_answer: str
    draft: Optional[WhatsAppMessageDraft] = None
    contact: Optional[WhatsAppContact] = None
    url: Optional[str] = None
    needs_clarification: bool = False
    clarification_options: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action.value,
            "formatted_answer": self.formatted_answer,
            "draft": self.draft.to_dict() if self.draft else None,
            "contact": self.contact.to_dict() if self.contact else None,
            "url": self.url,
            "needs_clarification": self.needs_clarification,
            "clarification_options": self.clarification_options,
            "error": self.error
        }
