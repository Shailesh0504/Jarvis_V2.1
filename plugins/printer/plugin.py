# plugins/printer/plugin.py
"""Printer capability plugin implementation for managing printers, print queues, and document spooling."""

import logging
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.printer")

try:
    import win32print
except ImportError:
    win32print = None


class PrinterPlugin(BasePlugin):
    """Controls Windows printer discovery, spooling, default assignment, and queue control."""

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="printer",
            version="2.0.0",
            description="Windows printer manager, queue controller, and document spooling supervisor.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def _resolve_printer_name(self, name: str) -> str:
        if name and name.strip():
            return name.strip()
        if win32print:
            try:
                return win32print.GetDefaultPrinter()
            except Exception:
                pass
        return "Microsoft Print to PDF"

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name == "set_default_printer":
            expected = parameters.get("printer_name", "").strip()
            current = self._resolve_printer_name("")
            matched = expected.lower() in current.lower() if expected else True
            return VerificationResult(
                verified=matched,
                state=ExecutionState.SUCCESS if matched else ExecutionState.FAILED,
                check_type="default_printer_match",
                expected=expected,
                actual=current,
                message=f"Default printer verified: {current}" if matched else f"Default printer mismatch: expected {expected}, got {current}"
            )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. list_printers
        if action_name == "list_printers":
            printers = []
            if win32print:
                try:
                    enum_flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                    for p in win32print.EnumPrinters(enum_flags):
                        p_name = p[2]
                        if p_name not in printers:
                            printers.append(p_name)
                except Exception as e:
                    logger.debug("win32print enumeration failed: %s", e)

            if not printers:
                # PowerShell fallback
                try:
                    out = subprocess.check_output(
                        ["powershell", "-NoProfile", "-Command", "Get-Printer | Select-Object -ExpandProperty Name"],
                        text=True,
                        timeout=5
                    )
                    printers = [line.strip() for line in out.splitlines() if line.strip()]
                except Exception:
                    printers = ["Microsoft Print to PDF", "Microsoft XPS Document Writer"]

            return PluginResult(
                success=True,
                data={"printers": printers, "count": len(printers), "message": f"Available printers ({len(printers)}): {', '.join(printers[:4])}"}
            )

        # 2. get_default_printer
        elif action_name == "get_default_printer":
            default_p = self._resolve_printer_name("")
            return PluginResult(
                success=True,
                data={"default_printer": default_p, "message": f"Default printer: '{default_p}'"}
            )

        # 3. print_file
        elif action_name == "print_file":
            path = parameters.get("file_path", "").strip()
            printer_name = parameters.get("printer_name", "").strip()
            if not path or not os.path.exists(path):
                return PluginResult(success=False, error=f"File to print '{path}' not found.")

            try:
                if printer_name and os.name == "nt":
                    # Use PowerShell Out-Printer
                    ps_cmd = f'Start-Process -FilePath "{os.path.abspath(path)}" -Verb PrintTo -ArgumentList "{printer_name}"'
                    subprocess.Popen(["powershell", "-NoProfile", "-Command", ps_cmd])
                else:
                    os.startfile(path, "print")

                return PluginResult(
                    success=True,
                    data={"file": os.path.abspath(path), "printer": printer_name or self._resolve_printer_name(""), "message": f"'{path}' sent to printer spooler."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Print error: {e}")

        # 4. set_default_printer
        elif action_name == "set_default_printer":
            name = parameters.get("printer_name", "").strip()
            if not name:
                return PluginResult(success=False, error="printer_name parameter is required.")

            success = False
            if win32print:
                try:
                    win32print.SetDefaultPrinter(name)
                    success = True
                except Exception as e:
                    logger.debug("win32print.SetDefaultPrinter failed: %s", e)

            if not success:
                try:
                    ps_cmd = f'(Get-CimInstance Win32_Printer -Filter "Name = \'{name}\'").SetDefaultPrinter()'
                    subprocess.check_call(["powershell", "-NoProfile", "-Command", ps_cmd], timeout=5)
                    success = True
                except Exception as e:
                    return PluginResult(success=False, error=f"Failed to set default printer '{name}': {e}")

            return PluginResult(
                success=True,
                data={"default_printer": name, "message": f"'{name}' set as system default printer."}
            )

        # 5. get_printer_queue_status
        elif action_name == "get_printer_queue_status":
            name = self._resolve_printer_name(parameters.get("printer_name", ""))
            jobs = []
            if win32print:
                try:
                    h = win32print.OpenPrinter(name)
                    try:
                        raw_jobs = win32print.EnumJobs(h, 0, -1, 1)
                        for j in raw_jobs:
                            jobs.append({
                                "job_id": j.get("JobId"),
                                "document": j.get("pDocument"),
                                "user": j.get("pUserName"),
                                "status": j.get("Status"),
                                "total_pages": j.get("TotalPages", 0)
                            })
                    finally:
                        win32print.ClosePrinter(h)
                except Exception as e:
                    logger.debug("EnumJobs failed for %s: %s", name, e)

            return PluginResult(
                success=True,
                data={
                    "printer": name,
                    "job_count": len(jobs),
                    "jobs": jobs,
                    "message": f"Printer '{name}' queue has {len(jobs)} pending job(s)."
                }
            )

        # 6. cancel_print_job
        elif action_name == "cancel_print_job":
            name = self._resolve_printer_name(parameters.get("printer_name", ""))
            job_id = int(parameters.get("job_id", 0))
            if job_id <= 0:
                return PluginResult(success=False, error="Valid job_id is required.")

            if win32print:
                try:
                    h = win32print.OpenPrinter(name, {"DesiredAccess": win32print.PRINTER_ALL_ACCESS})
                    try:
                        win32print.SetJob(h, job_id, 0, None, win32print.JOB_CONTROL_DELETE)
                        return PluginResult(
                            success=True,
                            data={"printer": name, "job_id": job_id, "message": f"Print job #{job_id} cancelled."}
                        )
                    finally:
                        win32print.ClosePrinter(h)
                except Exception as e:
                    logger.debug("win32print cancel job failed: %s", e)

            # PowerShell fallback
            try:
                subprocess.check_call(
                    ["powershell", "-NoProfile", "-Command", f"Remove-PrintJob -PrinterName '{name}' -ID {job_id}"],
                    timeout=5
                )
                return PluginResult(
                    success=True,
                    data={"printer": name, "job_id": job_id, "message": f"Print job #{job_id} cancelled via PowerShell."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Could not cancel job #{job_id}: {e}")

        # 7. clear_print_queue
        elif action_name == "clear_print_queue":
            name = self._resolve_printer_name(parameters.get("printer_name", ""))
            cleared = False
            if win32print:
                try:
                    h = win32print.OpenPrinter(name, {"DesiredAccess": win32print.PRINTER_ALL_ACCESS})
                    try:
                        win32print.SetPrinter(h, 0, None, win32print.PRINTER_CONTROL_PURGE)
                        cleared = True
                    finally:
                        win32print.ClosePrinter(h)
                except Exception as e:
                    logger.debug("win32print purge queue failed: %s", e)

            if not cleared:
                try:
                    subprocess.check_call(
                        ["powershell", "-NoProfile", "-Command", f"Get-PrintJob -PrinterName '{name}' | Remove-PrintJob"],
                        timeout=5
                    )
                    cleared = True
                except Exception as e:
                    return PluginResult(success=False, error=f"Failed to clear print queue for '{name}': {e}")

            return PluginResult(
                success=True,
                data={"printer": name, "cleared": True, "message": f"Print queue for '{name}' purged successfully."}
            )

        # 8. pause_printer
        elif action_name == "pause_printer":
            name = self._resolve_printer_name(parameters.get("printer_name", ""))
            if win32print:
                try:
                    h = win32print.OpenPrinter(name, {"DesiredAccess": win32print.PRINTER_ALL_ACCESS})
                    try:
                        win32print.SetPrinter(h, 0, None, win32print.PRINTER_CONTROL_PAUSE)
                        return PluginResult(success=True, data={"printer": name, "paused": True, "message": f"Printer '{name}' paused."})
                    finally:
                        win32print.ClosePrinter(h)
                except Exception as e:
                    return PluginResult(success=False, error=f"Failed to pause printer '{name}': {e}")

            return PluginResult(success=False, error="win32print not available.")

        # 9. resume_printer
        elif action_name == "resume_printer":
            name = self._resolve_printer_name(parameters.get("printer_name", ""))
            if win32print:
                try:
                    h = win32print.OpenPrinter(name, {"DesiredAccess": win32print.PRINTER_ALL_ACCESS})
                    try:
                        win32print.SetPrinter(h, 0, None, win32print.PRINTER_CONTROL_RESUME)
                        return PluginResult(success=True, data={"printer": name, "resumed": True, "message": f"Printer '{name}' resumed."})
                    finally:
                        win32print.ClosePrinter(h)
                except Exception as e:
                    return PluginResult(success=False, error=f"Failed to resume printer '{name}': {e}")

            return PluginResult(success=False, error="win32print not available.")

        # 10. get_printer_properties
        elif action_name == "get_printer_properties":
            name = self._resolve_printer_name(parameters.get("printer_name", ""))
            props = {}
            if win32print:
                try:
                    h = win32print.OpenPrinter(name)
                    try:
                        info = win32print.GetPrinter(h, 2)
                        props = {
                            "printer_name": info.get("pPrinterName"),
                            "driver_name": info.get("pDriverName"),
                            "port_name": info.get("pPortName"),
                            "share_name": info.get("pShareName"),
                            "location": info.get("pLocation"),
                            "comment": info.get("pComment"),
                            "status": info.get("Status", 0),
                            "pending_jobs_count": info.get("cJobs", 0)
                        }
                    finally:
                        win32print.ClosePrinter(h)
                except Exception as e:
                    return PluginResult(success=False, error=f"Failed to read properties for '{name}': {e}")

            return PluginResult(
                success=True,
                data={
                    "printer": name,
                    "properties": props,
                    "message": f"Properties for '{name}': Driver={props.get('driver_name')}, Port={props.get('port_name')}."
                }
            )

        # 11. print_text_direct
        elif action_name == "print_text_direct":
            text = parameters.get("text", "").strip()
            printer_name = parameters.get("printer_name", "").strip()
            if not text:
                return PluginResult(success=False, error="text parameter is required.")

            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
                f.write(text)
                temp_path = f.name

            try:
                res = self.execute("print_file", {"file_path": temp_path, "printer_name": printer_name})
                return PluginResult(
                    success=res.success,
                    data={"temp_file": temp_path, "printer": printer_name or self._resolve_printer_name(""), "message": "Text document dispatched to printer."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Direct print failed: {e}")

        # 12. print_pdf_file
        elif action_name == "print_pdf_file":
            pdf_path = parameters.get("pdf_path", "").strip()
            printer_name = parameters.get("printer_name", "").strip()
            copies = max(1, int(parameters.get("copies", 1)))

            if not pdf_path or not os.path.isfile(pdf_path):
                return PluginResult(success=False, error=f"PDF file '{pdf_path}' not found.")

            target_printer = self._resolve_printer_name(printer_name)
            try:
                for _ in range(copies):
                    self.execute("print_file", {"file_path": pdf_path, "printer_name": target_printer})

                return PluginResult(
                    success=True,
                    data={
                        "pdf_path": os.path.abspath(pdf_path),
                        "printer": target_printer,
                        "copies": copies,
                        "message": f"Dispatched {copies} copy/copies of '{os.path.basename(pdf_path)}' to '{target_printer}'."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"PDF print failed: {e}")

        # 13. check_printer_online_status
        elif action_name == "check_printer_online_status":
            name = self._resolve_printer_name(parameters.get("printer_name", ""))
            online = True
            status_desc = "Ready"

            if win32print:
                try:
                    h = win32print.OpenPrinter(name)
                    try:
                        info = win32print.GetPrinter(h, 2)
                        st = info.get("Status", 0)
                        if st & 0x00000002:  # PRINTER_STATUS_ERROR
                            online = False
                            status_desc = "Error"
                        elif st & 0x00000004:  # PRINTER_STATUS_PENDING_DELETION
                            status_desc = "Pending Deletion"
                        elif st & 0x00000008:  # PRINTER_STATUS_PAPER_JAM
                            online = False
                            status_desc = "Paper Jam"
                        elif st & 0x00000010:  # PRINTER_STATUS_PAPER_OUT
                            status_desc = "Paper Out"
                        elif st & 0x00000020:  # PRINTER_STATUS_MANUAL_FEED
                            status_desc = "Manual Feed"
                        elif st & 0x00000040:  # PRINTER_STATUS_PAPER_PROBLEM
                            status_desc = "Paper Problem"
                        elif st & 0x00000080:  # PRINTER_STATUS_OFFLINE
                            online = False
                            status_desc = "Offline"
                        else:
                            status_desc = "Ready / Online"
                    finally:
                        win32print.ClosePrinter(h)
                except Exception as e:
                    online = False
                    status_desc = f"Unreachable ({e})"

            return PluginResult(
                success=True,
                data={
                    "printer": name,
                    "online": online,
                    "status_description": status_desc,
                    "message": f"Printer '{name}' status: {status_desc}."
                }
            )

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Printer plugin.")
