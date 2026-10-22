# plugins/whatsapp/plugin.py
"""
Dedicated Local WhatsApp Plugin for Jarvis V2.
"""

import json
import logging
import os
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from core.permissions import PermissionLevel
from .commands import ACTIONS, WhatsAppCommands
from .automation import WhatsAppAutomationEngine
from .models import WhatsAppContact

logger = logging.getLogger("jarvis.plugins.whatsapp")


class WhatsAppPlugin(BasePlugin):
    """
    Dedicated WhatsApp Plugin providing local Desktop and Web
    messaging, contact resolution, drafting, sending, searching, and calling.
    """

    def __init__(self, manifest=None, config=None, event_bus=None):
        super().__init__(manifest=manifest, config=config)
        self.event_bus = event_bus
        self.engine = WhatsAppAutomationEngine()
        self.commands = WhatsAppCommands(engine=self.engine)

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="whatsapp",
            version="2.0.0",
            description="Zero-API local WhatsApp Desktop and Web communication plugin.",
            author="Jarvis Team",
            permissions=[PermissionLevel.READ, PermissionLevel.WRITE],
            actions=ACTIONS
        )

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None, **kwargs) -> PluginResult:
        """Executes the requested WhatsApp action."""
        act_name = (action_name or kwargs.get("action", "")).lower().strip()
        params = parameters if parameters is not None else kwargs.get("parameters", kwargs)

        logger.info(f"WhatsAppPlugin: Executing action '{act_name}' with params {params}")

        # 1. Open WhatsApp
        if act_name in ("open_whatsapp", "launch_whatsapp", "open"):
            res = self.commands.open_whatsapp()
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 2. Open Chat
        elif act_name in ("open_chat", "chat"):
            rec = params.get("recipient", "")
            res = self.commands.open_chat(recipient=rec)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 3. Draft Message
        elif act_name in ("draft_message", "draft"):
            rec = params.get("recipient", "")
            msg = params.get("message", "")
            res = self.commands.draft_message(recipient=rec, message=msg)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 4. Send Message
        elif act_name in ("send_message", "send", "message"):
            rec = params.get("recipient", "")
            msg = params.get("message", "")
            conf = bool(params.get("confirmed", False))
            res = self.commands.send_message(recipient=rec, message=msg, confirmed=conf)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 5. Search Chat / Messages
        elif act_name in ("search_chat", "search", "find"):
            q = params.get("query", "")
            res = self.commands.search_chat(query=q)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 6. Call Contact
        elif act_name in ("call_contact", "call", "voice_call", "video_call"):
            rec = params.get("recipient", "")
            video = bool(params.get("video", False) or "video" in act_name)
            res = self.commands.call_contact(recipient=rec, video=video)
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 7. Cancel Action / Draft
        elif act_name in ("cancel_action", "cancel_draft", "cancel"):
            res = self.commands.cancel_action()
            return PluginResult(
                success=res.get("success", False),
                data=res,
                error=res.get("error")
            )

        # 8. Add Contact
        elif act_name in ("add_contact", "save_contact"):
            name = str(params.get("name", "")).strip()
            phone = str(params.get("phone_number", "")).strip()
            rel = str(params.get("relationship", "contact")).strip()
            aliases = params.get("aliases", [])
            trusted = bool(params.get("is_trusted", False))

            if not name or not phone:
                return PluginResult(success=False, error="Both name and phone_number are required.")

            alias_list = aliases if isinstance(aliases, list) else [str(aliases)]
            new_contact = WhatsAppContact(
                name=name,
                phone_number=phone,
                relationship=rel,
                aliases=alias_list,
                is_trusted=trusted
            )
            self.engine.contact_book.add_contact(new_contact)
            return PluginResult(
                success=True,
                data={
                    "name": name,
                    "phone_number": phone,
                    "relationship": rel,
                    "message": f"Saved contact '{name}' ({phone}) in local WhatsApp address book."
                }
            )

        # 9. List Contacts
        elif act_name in ("list_contacts", "get_contacts"):
            contacts = self.engine.contact_book.get_all_contacts()
            c_data = [
                {
                    "name": c.name,
                    "phone_number": c.phone_number,
                    "relationship": c.relationship,
                    "aliases": c.aliases,
                    "is_trusted": c.is_trusted
                }
                for c in contacts
            ]
            return PluginResult(
                success=True,
                data={
                    "contacts": c_data,
                    "count": len(c_data),
                    "message": f"Retrieved {len(c_data)} contact(s) from local address book."
                }
            )

        # 10. Delete Contact
        elif act_name in ("delete_contact", "remove_contact"):
            target_name = str(params.get("name", "")).strip()
            if not target_name:
                return PluginResult(success=False, error="Contact name parameter is required.")

            deleted = self.engine.contact_book.delete_contact(target_name)
            if deleted:
                return PluginResult(
                    success=True,
                    data={"name": target_name, "message": f"Contact '{target_name}' deleted successfully."}
                )
            return PluginResult(
                success=False,
                error=f"Contact '{target_name}' not found in address book."
            )

        # 11. Generate Chat Link (wa.me click-to-chat)
        elif act_name in ("generate_chat_link", "chat_link", "wa_me"):
            raw_phone = str(params.get("phone_number", "")).strip()
            msg = str(params.get("message", "")).strip()
            digits_only = re.sub(r"[^\d]", "", raw_phone)

            if not digits_only:
                return PluginResult(success=False, error="Valid phone number is required.")

            encoded_text = urllib.parse.quote(msg) if msg else ""
            link = f"https://wa.me/{digits_only}?text={encoded_text}" if encoded_text else f"https://wa.me/{digits_only}"

            return PluginResult(
                success=True,
                data={
                    "phone_number": digits_only,
                    "link": link,
                    "message_text": msg,
                    "message": f"Direct WhatsApp link generated: {link}"
                }
            )

        # 12. Queue Scheduled Message
        elif act_name in ("queue_scheduled_message", "schedule_message"):
            rec = str(params.get("recipient", "")).strip()
            msg = str(params.get("message", "")).strip()
            sched_time = str(params.get("scheduled_time", "")).strip()

            if not rec or not msg or not sched_time:
                return PluginResult(success=False, error="recipient, message, and scheduled_time are required.")

            outbox_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "whatsapp_outbox.json"))
            os.makedirs(os.path.dirname(outbox_file), exist_ok=True)
            outbox = []
            if os.path.exists(outbox_file):
                try:
                    with open(outbox_file, "r", encoding="utf-8") as f:
                        outbox = json.load(f)
                except Exception:
                    outbox = []

            item = {
                "id": len(outbox) + 1,
                "recipient": rec,
                "message": msg,
                "scheduled_time": sched_time,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending"
            }
            outbox.append(item)
            with open(outbox_file, "w", encoding="utf-8") as f:
                json.dump(outbox, f, indent=2)

            return PluginResult(
                success=True,
                data={
                    "scheduled_item": item,
                    "message": f"Message to '{rec}' queued for {sched_time} (ID: {item['id']})."
                }
            )

        # 13. List Scheduled Messages
        elif act_name in ("list_scheduled_messages", "outbox"):
            outbox_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "whatsapp_outbox.json"))
            outbox = []
            if os.path.exists(outbox_file):
                try:
                    with open(outbox_file, "r", encoding="utf-8") as f:
                        outbox = json.load(f)
                except Exception:
                    outbox = []

            return PluginResult(
                success=True,
                data={
                    "outbox": outbox,
                    "count": len(outbox),
                    "message": f"Outbox contains {len(outbox)} scheduled message(s)."
                }
            )

        # 14. Cancel Scheduled Message
        elif act_name in ("cancel_scheduled_message", "delete_scheduled_message"):
            msg_id = int(params.get("message_id", 0))
            outbox_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "whatsapp_outbox.json"))
            if not os.path.exists(outbox_file) or msg_id <= 0:
                return PluginResult(success=False, error="Valid message_id is required.")

            try:
                with open(outbox_file, "r", encoding="utf-8") as f:
                    outbox = json.load(f)
                found = False
                for item in outbox:
                    if item.get("id") == msg_id:
                        item["status"] = "cancelled"
                        found = True
                        break
                if found:
                    with open(outbox_file, "w", encoding="utf-8") as f:
                        json.dump(outbox, f, indent=2)
                    return PluginResult(success=True, data={"message_id": msg_id, "message": f"Scheduled message #{msg_id} cancelled."})
                return PluginResult(success=False, error=f"Message ID #{msg_id} not found in outbox.")
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to cancel scheduled message: {e}")

        # 15. Validate Phone Number
        elif act_name in ("validate_phone_number", "validate_phone"):
            raw_phone = str(params.get("phone_number", "")).strip()
            cc = str(params.get("default_country_code", "+91")).strip()
            digits = re.sub(r"[^\d]", "", raw_phone)

            if len(digits) == 10:
                formatted = f"{cc}{digits}"
                is_valid = True
            elif len(digits) >= 11 and len(digits) <= 15:
                formatted = f"+{digits}"
                is_valid = True
            else:
                formatted = raw_phone
                is_valid = False

            return PluginResult(
                success=True,
                data={
                    "input": raw_phone,
                    "is_valid": is_valid,
                    "formatted": formatted,
                    "digits": digits,
                    "message": f"Phone '{raw_phone}' is {'VALID' if is_valid else 'INVALID'} (Formatted: {formatted})."
                }
            )

        # 16. Export Contacts to vCard (.vcf)
        elif act_name in ("export_contacts_vcard", "export_vcf"):
            out_path = str(params.get("output_path", "")).strip()
            if not out_path:
                out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "whatsapp_contacts.vcf"))

            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            contacts = self.engine.contact_book.get_all_contacts()
            vcf_lines = []
            for c in contacts:
                vcf_lines.append("BEGIN:VCARD")
                vcf_lines.append("VERSION:3.0")
                vcf_lines.append(f"FN:{c.name}")
                if c.phone_number:
                    vcf_lines.append(f"TEL;TYPE=CELL:{c.phone_number}")
                if c.relationship:
                    vcf_lines.append(f"NOTE:Relationship={c.relationship}")
                vcf_lines.append("END:VCARD")

            vcf_content = "\n".join(vcf_lines)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(vcf_content)

            return PluginResult(
                success=True,
                data={
                    "file_path": out_path,
                    "contacts_exported": len(contacts),
                    "message": f"Exported {len(contacts)} contact(s) to '{os.path.basename(out_path)}'."
                }
            )

        # 17. Import Contacts from vCard (.vcf)
        elif act_name in ("import_contacts_vcard", "import_vcf"):
            in_path = str(params.get("file_path", "")).strip()
            if not in_path or not os.path.exists(in_path):
                return PluginResult(success=False, error="Valid vCard file path is required.")

            try:
                imported_count = 0
                with open(in_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                cards = content.split("BEGIN:VCARD")
                for card in cards:
                    if not card.strip():
                        continue
                    fn_match = re.search(r"^FN:(.*)$", card, re.MULTILINE)
                    tel_match = re.search(r"^TEL[^:]*:(.*)$", card, re.MULTILINE)
                    if fn_match and tel_match:
                        name = fn_match.group(1).strip()
                        phone = tel_match.group(1).strip()
                        if name and phone:
                            self.engine.contact_book.add_contact(WhatsAppContact(name=name, phone_number=phone))
                            imported_count += 1

                return PluginResult(
                    success=True,
                    data={
                        "imported_count": imported_count,
                        "file_path": in_path,
                        "message": f"Successfully imported {imported_count} contact(s) from vCard."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"vCard import failed: {e}")

        return PluginResult(
            success=False,
            error=f"Unsupported WhatsApp action '{act_name}'"
        )
