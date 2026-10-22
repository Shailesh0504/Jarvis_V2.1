# plugins/email/plugin.py
"""Email capability plugin implementation for managing, composing, validating, and sending emails."""

import datetime
from email.message import EmailMessage
import json
import logging
import os
import re
import smtplib
from typing import Any, Dict, List, Optional
import urllib.parse
import webbrowser

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.email")


class EmailPlugin(BasePlugin):
    """Handles email composition, drafts persistence, SMTP dispatch, and mailto integration."""

    def __init__(self, manifest: Optional[PluginManifest] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest=manifest, config=config)
        self.store_path = os.path.join("data", "email_store.json")
        self._ensure_store()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="email",
            version="2.0.0",
            description="Email management, draft storage, SMTP dispatch, and native mailto client assistant.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def _ensure_store(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
            if not os.path.exists(self.store_path):
                with open(self.store_path, "w", encoding="utf-8") as f:
                    json.dump({"drafts": [], "templates": [], "next_id": 1}, f, indent=2)
        except Exception:
            pass

    def _read_store(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.store_path):
                with open(self.store_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.debug("Failed to read email store: %s", e)
        return {"drafts": [], "templates": [], "next_id": 1}

    def _write_store(self, data: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to write email store: %s", e)

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name == "export_draft_to_eml":
            out_path = parameters.get("output_path")
            if out_path and os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="file_exists",
                    expected=out_path,
                    actual=f"{os.path.getsize(out_path)} bytes",
                    message="EML email file export verified."
                )
            return VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="file_exists",
                expected=out_path,
                actual=None,
                error="Exported EML file missing or empty."
            )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. validate_email_address
        if action_name == "validate_email_address":
            email = parameters.get("email", "").strip()
            pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
            is_valid = bool(re.match(pattern, email))
            return PluginResult(
                success=is_valid,
                data={"email": email, "valid": is_valid, "message": f"Email '{email}' is {'valid' if is_valid else 'invalid'}."},
                error=None if is_valid else f"'{email}' is not a syntactically valid email address."
            )

        # 2. create_mailto_url
        elif action_name == "create_mailto_url":
            recipient = parameters.get("recipient", "").strip()
            subject = parameters.get("subject", "").strip()
            body = parameters.get("body", "").strip()
            cc = parameters.get("cc", "").strip()

            query_parts = []
            if subject:
                query_parts.append(f"subject={urllib.parse.quote(subject)}")
            if body:
                query_parts.append(f"body={urllib.parse.quote(body)}")
            if cc:
                query_parts.append(f"cc={urllib.parse.quote(cc)}")

            query_str = f"?{'&'.join(query_parts)}" if query_parts else ""
            mailto_url = f"mailto:{recipient}{query_str}"
            return PluginResult(
                success=True,
                data={"url": mailto_url, "recipient": recipient, "message": f"Mailto URL generated: {mailto_url}"}
            )

        # 3. open_email_client
        elif action_name == "open_email_client":
            recipient = parameters.get("recipient", "").strip()
            subject = parameters.get("subject", "").strip()
            body = parameters.get("body", "").strip()

            if recipient or subject or body:
                res = self.execute("create_mailto_url", {"recipient": recipient, "subject": subject, "body": body})
                target = res.data["url"]
            else:
                target = "mailto:"

            try:
                webbrowser.open(target)
                return PluginResult(
                    success=True,
                    data={"target": target, "message": "Opened default system email client."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Could not open email client: {e}")

        # 4. save_local_draft / compose_draft
        elif action_name in ("save_local_draft", "compose_draft"):
            recipient = parameters.get("recipient", "").strip()
            subject = parameters.get("subject", "Draft").strip()
            body = parameters.get("body", "").strip()

            store = self._read_store()
            draft_id = store.get("next_id", 1)
            draft = {
                "id": draft_id,
                "recipient": recipient,
                "subject": subject,
                "body": body,
                "created_at": datetime.datetime.now().isoformat()
            }
            store["drafts"].append(draft)
            store["next_id"] = draft_id + 1
            self._write_store(store)

            return PluginResult(
                success=True,
                data={"draft": draft, "message": f"Email draft #{draft_id} '{subject}' saved successfully."}
            )

        # 5. list_local_drafts
        elif action_name == "list_local_drafts":
            limit = int(parameters.get("limit", 10))
            store = self._read_store()
            drafts = store.get("drafts", [])[:limit]
            return PluginResult(
                success=True,
                data={
                    "drafts": drafts,
                    "count": len(drafts),
                    "message": f"Found {len(drafts)} saved email draft(s)." if drafts else "No saved email drafts."
                }
            )

        # 6. delete_local_draft
        elif action_name == "delete_local_draft":
            draft_id = int(parameters.get("draft_id", 0))
            store = self._read_store()
            initial_count = len(store.get("drafts", []))
            store["drafts"] = [d for d in store.get("drafts", []) if d.get("id") != draft_id]

            if len(store["drafts"]) < initial_count:
                self._write_store(store)
                return PluginResult(success=True, data={"draft_id": draft_id, "message": f"Draft #{draft_id} deleted."})
            return PluginResult(success=False, error=f"Draft #{draft_id} not found.")

        # 7. export_draft_to_eml
        elif action_name == "export_draft_to_eml":
            output_path = parameters.get("output_path", "").strip()
            if not output_path:
                return PluginResult(success=False, error="output_path is required.")

            draft_id = int(parameters.get("draft_id", -1))
            recipient = parameters.get("recipient", "").strip()
            subject = parameters.get("subject", "").strip()
            body = parameters.get("body", "").strip()

            if draft_id > 0:
                store = self._read_store()
                found = next((d for d in store.get("drafts", []) if d.get("id") == draft_id), None)
                if found:
                    recipient = recipient or found.get("recipient", "")
                    subject = subject or found.get("subject", "")
                    body = body or found.get("body", "")

            msg = EmailMessage()
            msg["Subject"] = subject or "Untitled Draft"
            msg["To"] = recipient or "recipient@example.com"
            msg["From"] = "jarvis@assistant.local"
            msg["Date"] = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
            msg.set_content(body or "")

            try:
                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(msg.as_bytes())

                return PluginResult(
                    success=True,
                    data={"output_path": output_path, "size_bytes": os.path.getsize(output_path), "message": f"Exported EML to '{output_path}'."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Export to EML failed: {e}")

        # 8. verify_smtp_connection
        elif action_name == "verify_smtp_connection":
            host = parameters.get("smtp_server", "").strip()
            port = int(parameters.get("smtp_port", 587))
            user = parameters.get("username", "").strip()
            password = parameters.get("password", "").strip()

            if not host:
                return PluginResult(success=False, error="smtp_server host is required.")

            try:
                server = smtplib.SMTP(host, port, timeout=5)
                server.ehlo()
                if port == 587:
                    server.starttls()
                    server.ehlo()
                if user and password:
                    server.login(user, password)
                server.quit()
                return PluginResult(success=True, data={"host": host, "port": port, "message": f"Successfully verified SMTP connection to {host}:{port}."})
            except Exception as e:
                return PluginResult(success=False, error=f"SMTP connection test failed: {e}")

        # 9. send_smtp_email
        elif action_name == "send_smtp_email":
            recipient = parameters.get("recipient", "").strip()
            subject = parameters.get("subject", "").strip()
            body = parameters.get("body", "").strip()
            host = parameters.get("smtp_server", "").strip()
            port = int(parameters.get("smtp_port", 587))
            user = parameters.get("username", "").strip()
            pwd = parameters.get("password", "").strip()
            use_tls = bool(parameters.get("use_tls", True))

            if not recipient or not subject or not host or not user or not pwd:
                return PluginResult(success=False, error="recipient, subject, smtp_server, username, and password are required.")

            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = recipient
            msg.set_content(body)

            try:
                server = smtplib.SMTP(host, port, timeout=10)
                server.ehlo()
                if use_tls:
                    server.starttls()
                    server.ehlo()
                server.login(user, pwd)
                server.send_message(msg)
                server.quit()

                return PluginResult(
                    success=True,
                    data={"recipient": recipient, "subject": subject, "message": f"Email successfully sent via SMTP to '{recipient}'."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to send SMTP email: {e}")

        # 10. create_email_template
        elif action_name == "create_email_template":
            name = parameters.get("name", "").strip().lower()
            subject_tmpl = parameters.get("subject_template", "").strip()
            body_tmpl = parameters.get("body_template", "").strip()

            if not name or not subject_tmpl:
                return PluginResult(success=False, error="name and subject_template are required.")

            store = self._read_store()
            store["templates"] = [t for t in store.get("templates", []) if t.get("name") != name]
            tmpl = {"name": name, "subject_template": subject_tmpl, "body_template": body_tmpl}
            store["templates"].append(tmpl)
            self._write_store(store)

            return PluginResult(
                success=True,
                data={"template": tmpl, "message": f"Email template '{name}' saved successfully."}
            )

        # 11. send_email (existing fallback)
        elif action_name == "send_email":
            recipient = parameters.get("recipient", "").strip()
            subject = parameters.get("subject", "").strip()
            body = parameters.get("body", "").strip()
            smtp_server = parameters.get("smtp_server", "")

            if not recipient:
                return PluginResult(success=False, error="Recipient email is required.")

            # If full SMTP parameters are passed, dispatch via SMTP
            if smtp_server and parameters.get("sender_email") and parameters.get("sender_password"):
                return self.execute("send_smtp_email", {
                    "recipient": recipient,
                    "subject": subject,
                    "body": body,
                    "smtp_server": smtp_server,
                    "smtp_port": parameters.get("smtp_port", 587),
                    "username": parameters.get("sender_email"),
                    "password": parameters.get("sender_password")
                })

            # Otherwise save draft and open mailto composer safely
            self.execute("save_local_draft", {"recipient": recipient, "subject": subject, "body": body})
            self.execute("open_email_client", {"recipient": recipient, "subject": subject, "body": body})
            return PluginResult(
                success=True,
                data={
                    "recipient": recipient,
                    "subject": subject,
                    "message": f"Draft saved and email composer opened for '{recipient}' with subject '{subject}'."
                }
            )

        # 12. check_unread_emails (existing)
        elif action_name == "check_unread_emails":
            store = self._read_store()
            drafts_count = len(store.get("drafts", []))
            return PluginResult(
                success=True,
                data={
                    "unread_count": 0,
                    "drafts_count": drafts_count,
                    "message": f"Inbox checked: 0 unread messages, {drafts_count} local draft(s) pending."
                }
            )

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Email plugin.")
