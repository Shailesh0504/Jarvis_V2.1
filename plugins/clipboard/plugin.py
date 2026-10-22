# plugins/clipboard/plugin.py
"""Clipboard capability plugin implementation for reading, setting, transforming, and tracking system clipboard."""

import base64
import ctypes
import datetime
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.clipboard")


class ClipboardPlugin(BasePlugin):
    """Controls Windows clipboard reading, writing, transformations, and history tracking."""

    def __init__(self, manifest=None, config=None):
        super().__init__(manifest=manifest, config=config)
        self._clipboard_buffer = ""
        self._history: List[Dict[str, Any]] = []

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="clipboard",
            version="2.0.0",
            description="Windows system clipboard reader, copier, transformer, and history manager.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name in ("set_clipboard_text", "append_to_clipboard", "transform_clipboard_text", "restore_clipboard_from_history"):
            expected = (result_data or {}).get("text") or (result_data or {}).get("transformed_text")
            current = self._read_windows_clipboard() or self._clipboard_buffer
            matched = (expected == current) if expected is not None else True
            return VerificationResult(
                verified=matched,
                state=ExecutionState.SUCCESS if matched else ExecutionState.FAILED,
                check_type="clipboard_content_match",
                expected=expected[:50] if expected else "",
                actual=current[:50] if current else "",
                message="Clipboard content verified." if matched else "Clipboard content did not match expected value."
            )
        elif action_name == "save_clipboard_to_file":
            path = (result_data or {}).get("file_path")
            if path and os.path.isfile(path) and os.path.getsize(path) > 0:
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="file_exists",
                    expected=path,
                    actual=f"{os.path.getsize(path)} bytes",
                    message="Saved clipboard dump verified on disk."
                )
        return None

    def _read_windows_clipboard(self) -> str:
        text = ""
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if user32.OpenClipboard(None):
                try:
                    h_clip = user32.GetClipboardData(13)  # CF_UNICODETEXT
                    if h_clip:
                        p_data = kernel32.GlobalLock(h_clip)
                        if p_data:
                            text = ctypes.c_wchar_p(p_data).value or ""
                            kernel32.GlobalUnlock(h_clip)
                finally:
                    user32.CloseClipboard()
        except Exception:
            pass
        return text or self._clipboard_buffer

    def _write_windows_clipboard(self, text: str) -> bool:
        self._clipboard_buffer = text
        # Record in history if non-empty and different from last
        if text and (not self._history or self._history[0].get("text") != text):
            self._history.insert(0, {
                "text": text,
                "preview": text[:80] + ("..." if len(text) > 80 else ""),
                "length": len(text),
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            if len(self._history) > 100:
                self._history.pop()

        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    count = len(text) + 1
                    h_mem = kernel32.GlobalAlloc(0x0042, count * ctypes.sizeof(ctypes.c_wchar))
                    if h_mem:
                        p_mem = kernel32.GlobalLock(h_mem)
                        if p_mem:
                            ctypes.cdll.msvcrt.wcscpy(ctypes.c_wchar_p(p_mem), text)
                            kernel32.GlobalUnlock(h_mem)
                            user32.SetClipboardData(13, h_mem)
                finally:
                    user32.CloseClipboard()
                return True
        except Exception:
            pass
        return False

    def _detect_content_type(self, text: str) -> str:
        s = text.strip()
        if not s:
            return "empty"
        if re.match(r'^https?://[^\s]+$', s, re.IGNORECASE):
            return "url"
        if re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', s):
            return "email"
        if os.path.exists(s):
            return "file_path"
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                json.loads(s)
                return "json"
            except Exception:
                pass
        if any(kw in s for kw in ("def ", "class ", "import ", "function ", "const ", "var ", "return ", "if (", "console.log")):
            return "code_snippet"
        return "plain_text"

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. get_clipboard_text
        if action_name == "get_clipboard_text":
            text = self._read_windows_clipboard()
            preview = text[:200] + ("..." if len(text) > 200 else "")
            return PluginResult(
                success=True,
                data={"text": text, "preview": preview, "length": len(text), "message": f"Clipboard text: '{preview or '[Empty]'}'"}
            )

        # 2. set_clipboard_text
        elif action_name == "set_clipboard_text":
            text = parameters.get("text", "")
            self._write_windows_clipboard(text)
            return PluginResult(
                success=True,
                data={"text": text, "length": len(text), "message": "Text clipboard mein copy kar diya hai, Boss."}
            )

        # 3. clear_clipboard
        elif action_name == "clear_clipboard":
            self._clipboard_buffer = ""
            try:
                user32 = ctypes.windll.user32
                if user32.OpenClipboard(None):
                    user32.EmptyClipboard()
                    user32.CloseClipboard()
            except Exception:
                pass

            return PluginResult(
                success=True,
                data={"cleared": True, "message": "Clipboard clear kar diya hai, Boss."}
            )

        # 4. append_to_clipboard
        elif action_name == "append_to_clipboard":
            text = parameters.get("text", "")
            delimiter = parameters.get("delimiter", "\n")
            current = self._read_windows_clipboard()
            combined = f"{current}{delimiter}{text}" if current else text
            self._write_windows_clipboard(combined)

            return PluginResult(
                success=True,
                data={"text": combined, "appended_length": len(text), "message": f"Appended {len(text)} characters to clipboard."}
            )

        # 5. get_clipboard_metrics
        elif action_name == "get_clipboard_metrics":
            text = self._read_windows_clipboard()
            ctype = self._detect_content_type(text)
            words = len(re.findall(r'\b\w+\b', text))
            lines = len(text.splitlines()) if text else 0

            return PluginResult(
                success=True,
                data={
                    "char_count": len(text),
                    "word_count": words,
                    "line_count": lines,
                    "detected_type": ctype,
                    "preview": text[:100],
                    "message": f"Clipboard: {len(text)} chars, {words} words, {lines} lines (Type: {ctype})."
                }
            )

        # 6. get_clipboard_history
        elif action_name == "get_clipboard_history":
            limit = max(1, int(parameters.get("limit", 20)))
            items = self._history[:limit]
            return PluginResult(
                success=True,
                data={"history": items, "count": len(items), "message": f"Retrieved {len(items)} history entries."}
            )

        # 7. save_clipboard_to_file
        elif action_name == "save_clipboard_to_file":
            dest = parameters.get("file_path", "").strip()
            if not dest:
                return PluginResult(success=False, error="file_path is required.")

            text = self._read_windows_clipboard()
            try:
                os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(text)

                return PluginResult(
                    success=True,
                    data={"file_path": os.path.abspath(dest), "bytes": len(text.encode('utf-8')), "message": f"Saved clipboard contents to '{dest}'."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed saving clipboard to file: {e}")

        # 8. load_file_to_clipboard
        elif action_name == "load_file_to_clipboard":
            path = parameters.get("file_path", "").strip()
            if not path or not os.path.isfile(path):
                return PluginResult(success=False, error=f"File '{path}' not found.")

            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                self._write_windows_clipboard(content)
                return PluginResult(
                    success=True,
                    data={"file_path": os.path.abspath(path), "chars_copied": len(content), "message": f"Loaded {len(content)} chars from '{path}' into clipboard."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed loading file to clipboard: {e}")

        # 9. transform_clipboard_text
        elif action_name == "transform_clipboard_text":
            transform = parameters.get("transformation", "").strip().lower()
            text = self._read_windows_clipboard()

            if not text:
                return PluginResult(success=False, error="Clipboard is currently empty.")

            transformed = text
            try:
                if transform == "uppercase":
                    transformed = text.upper()
                elif transform == "lowercase":
                    transformed = text.lower()
                elif transform == "titlecase":
                    transformed = text.title()
                elif transform == "strip":
                    transformed = text.strip()
                elif transform == "json_prettify":
                    parsed = json.loads(text)
                    transformed = json.dumps(parsed, indent=2)
                elif transform == "base64_encode":
                    transformed = base64.b64encode(text.encode("utf-8")).decode("utf-8")
                elif transform == "base64_decode":
                    transformed = base64.b64decode(text.encode("utf-8")).decode("utf-8", errors="ignore")
                else:
                    return PluginResult(success=False, error=f"Unsupported transformation '{transform}'.")

                self._write_windows_clipboard(transformed)
                return PluginResult(
                    success=True,
                    data={"transformation": transform, "transformed_text": transformed, "message": f"Applied '{transform}' to clipboard text."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Transformation '{transform}' failed: {e}")

        # 10. search_clipboard_history
        elif action_name == "search_clipboard_history":
            query = parameters.get("query", "").lower().strip()
            if not query:
                return PluginResult(success=False, error="query is required.")

            matches = [item for item in self._history if query in item.get("text", "").lower()]
            return PluginResult(
                success=True,
                data={"query": query, "count": len(matches), "matches": matches, "message": f"Found {len(matches)} match(es) in clipboard history."}
            )

        # 11. clear_clipboard_history
        elif action_name == "clear_clipboard_history":
            self._history.clear()
            return PluginResult(
                success=True,
                data={"cleared": True, "message": "Clipboard history cleared."}
            )

        # 12. restore_clipboard_from_history
        elif action_name == "restore_clipboard_from_history":
            idx = int(parameters.get("history_index", 0))
            if idx < 0 or idx >= len(self._history):
                return PluginResult(success=False, error=f"Invalid history index {idx}. Available entries: {len(self._history)}.")

            entry = self._history[idx]
            restored_text = entry["text"]
            self._write_windows_clipboard(restored_text)

            return PluginResult(
                success=True,
                data={"history_index": idx, "text": restored_text, "message": f"Restored history item #{idx} to clipboard."}
            )

        # 13. inspect_clipboard_formats
        elif action_name == "inspect_clipboard_formats":
            formats = []
            format_names = {
                1: "CF_TEXT",
                2: "CF_BITMAP",
                7: "CF_OEMTEXT",
                8: "CF_DIB",
                13: "CF_UNICODETEXT",
                14: "CF_ENHMETAFILE",
                15: "CF_HDROP (Files)"
            }
            try:
                user32 = ctypes.windll.user32
                if user32.OpenClipboard(None):
                    try:
                        fmt = user32.EnumClipboardFormats(0)
                        while fmt != 0:
                            formats.append({"id": fmt, "name": format_names.get(fmt, f"Format_{fmt}")})
                            fmt = user32.EnumClipboardFormats(fmt)
                    finally:
                        user32.CloseClipboard()
            except Exception:
                formats = [{"id": 13, "name": "CF_UNICODETEXT"}]

            if not formats and self._clipboard_buffer:
                formats = [{"id": 13, "name": "CF_UNICODETEXT"}]

            return PluginResult(
                success=True,
                data={"formats": formats, "count": len(formats), "message": f"Clipboard contains {len(formats)} format(s)."}
            )

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Clipboard plugin.")
