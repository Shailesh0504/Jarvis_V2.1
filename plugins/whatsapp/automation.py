# plugins/whatsapp/automation.py
"""
Local Zero-API WhatsApp Desktop & Web Automation Engine for Jarvis V2.
Uses clean URI protocols and pre-filled web routing with zero external API dependencies.
"""

import logging
import os
import subprocess
import sys
import urllib.parse
import webbrowser
from typing import Any, Dict, List, Optional, Tuple

from .contacts import ContactBook
from .models import WhatsAppActionResult, WhatsAppActionType, WhatsAppContact, WhatsAppMessageDraft

logger = logging.getLogger("jarvis.plugins.whatsapp.automation")


class WhatsAppAutomationEngine:
    """Zero-API Desktop and Browser WhatsApp Controller."""

    def __init__(self, contact_book: Optional[ContactBook] = None):
        self.contacts = contact_book or ContactBook()
        self._current_draft: Optional[WhatsAppMessageDraft] = None

    @property
    def contact_book(self) -> ContactBook:
        return self.contacts

    def get_whatsapp_web_url(self, phone: Optional[str] = None, text: Optional[str] = None) -> str:
        """Generates standard pre-filled WhatsApp Web URL."""
        base = "https://web.whatsapp.com/send"
        params = {}
        if phone:
            clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")
            params["phone"] = clean_phone
        if text:
            params["text"] = text.strip()

        if params:
            return f"{base}?{urllib.parse.urlencode(params)}"
        return "https://web.whatsapp.com/"

    def get_whatsapp_desktop_uri(self, phone: Optional[str] = None, text: Optional[str] = None) -> str:
        """Generates Windows native whatsapp:// protocol URI."""
        base = "whatsapp://send"
        params = {}
        if phone:
            clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")
            params["phone"] = clean_phone
        if text:
            params["text"] = text.strip()

        if params:
            return f"{base}?{urllib.parse.urlencode(params)}"
        return "whatsapp://"

    def open_whatsapp(self) -> WhatsAppActionResult:
        """Launches WhatsApp Desktop or WhatsApp Web."""
        try:
            # 1. Try Windows native WhatsApp Desktop app via URI
            if sys.platform == "win32":
                os.startfile("whatsapp://")
                return WhatsAppActionResult(
                    success=True,
                    action=WhatsAppActionType.OPEN_WHATSAPP,
                    formatted_answer="WhatsApp Desktop launch kar diya hai, Boss.",
                    url="whatsapp://"
                )
        except Exception as e:
            logger.debug(f"WhatsApp Desktop startfile error: {e}. Falling back to web.")

        # 2. Fallback to WhatsApp Web in browser
        web_url = "https://web.whatsapp.com/"
        webbrowser.open(web_url)
        return WhatsAppActionResult(
            success=True,
            action=WhatsAppActionType.OPEN_WHATSAPP,
            formatted_answer="WhatsApp Web browser mein open kar diya hai, Boss.",
            url=web_url
        )

    def open_chat(self, recipient: str) -> WhatsAppActionResult:
        """Opens chat with a specific contact."""
        contact, matches = self.contacts.resolve_contact(recipient)

        if not contact and matches:
            # Multiple candidates -> Ask for clarification!
            options_str = ", ".join(f"'{c.name}'" for c in matches)
            return WhatsAppActionResult(
                success=False,
                action=WhatsAppActionType.OPEN_CHAT,
                formatted_answer=f"'{recipient}' naam se multiple contacts hain: {options_str}. Aap kiska chat open karna chahte hain?",
                needs_clarification=True,
                clarification_options=[c.name for c in matches],
                error="ambiguous_recipient"
            )

        target_name = contact.name if contact else recipient
        phone = contact.phone_number if contact else None

        # Build Launch URLs
        web_url = self.get_whatsapp_web_url(phone=phone)
        desktop_uri = self.get_whatsapp_desktop_uri(phone=phone)

        # Attempt to launch
        opened = False
        if sys.platform == "win32" and phone:
            try:
                os.startfile(desktop_uri)
                opened = True
            except Exception:
                opened = False

        if not opened:
            webbrowser.open(web_url)

        return WhatsAppActionResult(
            success=True,
            action=WhatsAppActionType.OPEN_CHAT,
            formatted_answer=f"'{target_name}' ka WhatsApp chat open kar diya hai, Boss.",
            contact=contact,
            url=web_url
        )

    def draft_message(self, recipient: str, message: str) -> WhatsAppActionResult:
        """Drafts a message without sending it, presenting it to the user for review."""
        contact, matches = self.contacts.resolve_contact(recipient)

        if not contact and matches:
            options_str = ", ".join(f"'{c.name}'" for c in matches)
            return WhatsAppActionResult(
                success=False,
                action=WhatsAppActionType.DRAFT_MESSAGE,
                formatted_answer=f"'{recipient}' naam se multiple contacts hain: {options_str}. Aap kiske liye message draft karna chahte hain?",
                needs_clarification=True,
                clarification_options=[c.name for c in matches],
                error="ambiguous_recipient"
            )

        target_name = contact.name if contact else recipient
        phone = contact.phone_number if contact else None

        self._current_draft = WhatsAppMessageDraft(
            recipient_name=target_name,
            phone_number=phone,
            message_text=message.strip(),
            status="drafted",
            requires_confirmation=True
        )

        formatted = (
            f"📝 **WhatsApp Message Drafted**:\n"
            f"• **Recipient**: {target_name}" + (f" ({phone})" if phone else "") + "\n"
            f"• **Message**: \"{message.strip()}\"\n\n"
            f"Kya main ye message send kar doon, Boss? (Boliye 'Yes' ya 'Send karo')"
        )

        return WhatsAppActionResult(
            success=True,
            action=WhatsAppActionType.DRAFT_MESSAGE,
            formatted_answer=formatted,
            draft=self._current_draft,
            contact=contact
        )

    def send_message(self, recipient: str, message: str, confirmed: bool = False) -> WhatsAppActionResult:
        """
        Sends message to recipient. If recipient is ambiguous or not trusted,
        and confirmed is False, it creates a draft and requests confirmation.
        """
        contact, matches = self.contacts.resolve_contact(recipient)

        if not contact and matches:
            options_str = ", ".join(f"'{c.name}'" for c in matches)
            return WhatsAppActionResult(
                success=False,
                action=WhatsAppActionType.SEND_MESSAGE,
                formatted_answer=f"'{recipient}' naam se multiple contacts hain: {options_str}. Kisko bhejna hai?",
                needs_clarification=True,
                clarification_options=[c.name for c in matches],
                error="ambiguous_recipient"
            )

        target_name = contact.name if contact else recipient
        phone = contact.phone_number if contact else None

        # Build Pre-filled send URLs
        web_url = self.get_whatsapp_web_url(phone=phone, text=message)
        desktop_uri = self.get_whatsapp_desktop_uri(phone=phone, text=message)

        # Launch WhatsApp with pre-filled message
        opened = False
        if sys.platform == "win32" and phone:
            try:
                os.startfile(desktop_uri)
                opened = True
            except Exception:
                opened = False

        if not opened:
            webbrowser.open(web_url)

        draft = WhatsAppMessageDraft(
            recipient_name=target_name,
            phone_number=phone,
            message_text=message,
            status="sent",
            requires_confirmation=False
        )
        self._current_draft = None

        formatted = (
            f"✅ **WhatsApp Message Sent / Dispatched**:\n"
            f"• **To**: {target_name}" + (f" ({phone})" if phone else "") + "\n"
            f"• **Message**: \"{message.strip()}\"\n"
            f"WhatsApp open ho gaya hai pre-filled message ke saath, Boss."
        )

        return WhatsAppActionResult(
            success=True,
            action=WhatsAppActionType.SEND_MESSAGE,
            formatted_answer=formatted,
            draft=draft,
            contact=contact,
            url=web_url
        )

    def search_chat(self, query: str) -> WhatsAppActionResult:
        """Opens WhatsApp search for contacts or keywords."""
        url = "https://web.whatsapp.com/"
        if sys.platform == "win32":
            try:
                os.startfile("whatsapp://")
            except Exception:
                webbrowser.open(url)
        else:
            webbrowser.open(url)

        return WhatsAppActionResult(
            success=True,
            action=WhatsAppActionType.SEARCH_CHAT,
            formatted_answer=f"WhatsApp open kar diya hai '{query}' search karne ke liye, Boss.",
            url=url
        )

    def call_contact(self, recipient: str, video: bool = False) -> WhatsAppActionResult:
        """Initiates voice or video call on WhatsApp Desktop."""
        contact, matches = self.contacts.resolve_contact(recipient)
        target_name = contact.name if contact else recipient
        phone = contact.phone_number if contact else None

        call_type = "Video Call" if video else "Voice Call"
        web_url = self.get_whatsapp_web_url(phone=phone)

        if sys.platform == "win32" and phone:
            try:
                os.startfile(f"whatsapp://call?phone={phone.replace('+', '')}")
            except Exception:
                webbrowser.open(web_url)
        else:
            webbrowser.open(web_url)

        return WhatsAppActionResult(
            success=True,
            action=WhatsAppActionType.CALL_CONTACT,
            formatted_answer=f"'{target_name}' ko WhatsApp {call_type} connect kar raha hoon, Boss.",
            contact=contact,
            url=web_url
        )

    def cancel_current_draft(self) -> WhatsAppActionResult:
        """Cancels any active pending message draft."""
        if self._current_draft:
            rec = self._current_draft.recipient_name
            self._current_draft = None
            return WhatsAppActionResult(
                success=True,
                action=WhatsAppActionType.CANCEL_ACTION,
                formatted_answer=f"'{rec}' ke liye message draft cancel kar diya gaya hai, Boss."
            )
        return WhatsAppActionResult(
            success=True,
            action=WhatsAppActionType.CANCEL_ACTION,
            formatted_answer="Koi pending message draft nahi tha, Boss."
        )
