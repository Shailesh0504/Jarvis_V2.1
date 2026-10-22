# plugins/whatsapp/__init__.py
"""
Dedicated WhatsApp Plugin for Jarvis V2.
"""

from .models import WhatsAppContact, WhatsAppMessageDraft, WhatsAppActionResult, WhatsAppActionType
from .contacts import ContactBook
from .automation import WhatsAppAutomationEngine
from .commands import WhatsAppCommands, ACTIONS
from .plugin import WhatsAppPlugin

__all__ = [
    "WhatsAppPlugin",
    "WhatsAppAutomationEngine",
    "ContactBook",
    "WhatsAppCommands",
    "WhatsAppContact",
    "WhatsAppMessageDraft",
    "WhatsAppActionResult",
    "WhatsAppActionType",
    "ACTIONS",
]
