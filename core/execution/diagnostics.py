# core/execution/diagnostics.py
"""
Diagnostic inspection engine for failed Jarvis commands and operations.
Investigates root causes such as path resolution, shell namespaces, environment variables,
process execution, quoting/escaping, permissions, window activation, and Explorer state.
"""

from dataclasses import dataclass, field
import logging
import os
import sys
from typing import Any, Dict, List, Optional
import psutil

logger = logging.getLogger("jarvis.execution.diagnostics")


@dataclass
class DiagnosticReport:
    """Detailed findings from a root-cause investigation of a failed operation."""
    target: str
    action: str
    failure_identified: bool
    root_cause: str
    diagnostics: List[str] = field(default_factory=list)
    suggested_recovery_strategy: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def summary_message(self) -> str:
        """User-facing Hinglish diagnostic summary."""
        lines = [f"🔍 *Diagnostic Inspection Report for '{self.target}':*"]
        for diag in self.diagnostics:
            lines.append(f"• {diag}")
        if self.suggested_recovery_strategy:
            lines.append(f"💡 Recommended Strategy: {self.suggested_recovery_strategy}")
        return "\n".join(lines)


class ExecutionDiagnosticEngine:
    """
    Investigates why an operation or strategy failed on the operating system.
    """

    def __init__(self, window_manager: Optional[Any] = None):
        self.window_manager = window_manager

    def diagnose_folder_operation(
        self,
        target: str,
        attempted_strategy: str = "shell_uri",
        raw_error: Optional[str] = None
    ) -> DiagnosticReport:
        """
        Conducts deep investigation into why a folder (such as Startup, Downloads, Documents)
        failed to open or verify.
        """
        clean_target = str(target or "").strip().lower()
        findings: List[str] = []
        details: Dict[str, Any] = {}
        root_cause = "Unknown failure"
        recommended_strategy = "physical_path"

        # 1. Environment-Variable Resolution Check
        home = os.path.expanduser("~")
        appdata = os.environ.get("APPDATA")
        programdata = os.environ.get("PROGRAMDATA")
        localappdata = os.environ.get("LOCALAPPDATA")

        env_status = []
        if not appdata or not os.path.exists(appdata):
            env_status.append("APPDATA environment variable missing or invalid")
        if not home or not os.path.exists(home):
            env_status.append("User home directory missing or inaccessible")

        if env_status:
            findings.append(f"Environment Issue: {', '.join(env_status)}")
            details["env_issues"] = env_status
        else:
            findings.append("Environment variables (%APPDATA%, %USERPROFILE%) resolved correctly.")

        # 2. Path Resolution & Shell Namespace vs Filesystem Check
        is_startup = any(s in clean_target for s in ("startup", "start up", "shell:startup"))
        physical_startup_user = os.path.join(
            appdata or os.path.join(home, "AppData", "Roaming"),
            r"Microsoft\Windows\Start Menu\Programs\Startup"
        )
        physical_startup_common = os.path.join(
            programdata or r"C:\ProgramData",
            r"Microsoft\Windows\Start Menu\Programs\Startup"
        )

        resolved_physical_path = ""
        if is_startup:
            details["physical_user_startup"] = physical_startup_user
            details["physical_common_startup"] = physical_startup_common
            user_exists = os.path.exists(physical_startup_user)
            common_exists = os.path.exists(physical_startup_common)
            details["user_startup_exists"] = user_exists
            details["common_startup_exists"] = common_exists

            if user_exists:
                resolved_physical_path = physical_startup_user
                findings.append(f"Physical User Startup folder verified at '{physical_startup_user}'.")
            elif common_exists:
                resolved_physical_path = physical_startup_common
                findings.append(f"User Startup missing, but Common Startup exists at '{physical_startup_common}'.")
            else:
                findings.append("Physical Startup directory does not exist on disk yet (virtual shell namespace only).")
                root_cause = "Physical Startup folder directory does not exist on disk."
                recommended_strategy = "create_physical_and_open"
        else:
            from plugins.files.operations import FilesystemOperations
            ops = FilesystemOperations()
            special = ops.get_special_path(clean_target)
            if special and not special.startswith("shell:"):
                resolved_physical_path = special
            elif os.path.isabs(target) or os.path.exists(target):
                resolved_physical_path = target

            if resolved_physical_path:
                if os.path.exists(resolved_physical_path):
                    findings.append(f"Target directory verified on disk: '{resolved_physical_path}'.")
                else:
                    findings.append(f"Physical path '{resolved_physical_path}' does not exist on disk.")
                    root_cause = f"Target directory '{resolved_physical_path}' does not exist."

        # 3. Permissions & Access Check
        if resolved_physical_path and os.path.exists(resolved_physical_path):
            readable = os.access(resolved_physical_path, os.R_OK)
            writable = os.access(resolved_physical_path, os.W_OK)
            if not readable:
                findings.append(f"Permission Issue: Read access denied on '{resolved_physical_path}'.")
                root_cause = f"Permission denied on '{resolved_physical_path}'."
            else:
                findings.append(f"Filesystem permissions: Read={readable}, Write={writable} (Accessible).")

        # 4. Windows Explorer Process Check
        explorer_pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if (proc.info['name'] or '').lower() == 'explorer.exe':
                    explorer_pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        details["explorer_pids"] = explorer_pids
        if not explorer_pids:
            findings.append("Critical OS Issue: explorer.exe process is NOT running.")
            root_cause = "explorer.exe process is not active."
            recommended_strategy = "restart_explorer_and_open"
        else:
            findings.append(f"Windows Explorer shell process active (PIDs: {explorer_pids}).")

        # 5. Multiple Explorer Windows Check
        open_folder_wins = []
        if self.window_manager:
            try:
                open_folder_wins = self.window_manager.find_folder_windows("")
            except Exception as e:
                logger.debug("Failed to list folder windows: %s", e)

        details["open_folder_windows_count"] = len(open_folder_wins)
        if len(open_folder_wins) > 1:
            findings.append(f"System State: {len(open_folder_wins)} Explorer windows already open on desktop.")
            details["open_folder_titles"] = [w.get("title") for w in open_folder_wins]
            # Multiple explorer windows might cause new window to group or fail to gain focus
            recommended_strategy = "direct_explorer_separate_process"

        # 6. Shell URI vs Explorer Argument Quoting Check
        if attempted_strategy == "shell_uri" and is_startup:
            findings.append(
                "Command Strategy Issue: 'shell:startup' via ShellExecute can be discarded by Windows Explorer if folder is empty or uninitialized."
            )
            root_cause = "Shell URI 'shell:startup' failed to instantiate visible CabinetWClass window."
            recommended_strategy = "physical_path_explorer"

        if raw_error:
            findings.append(f"Subprocess/System Error Recorded: {raw_error}")
            root_cause = raw_error

        if not root_cause or root_cause == "Unknown failure":
            if resolved_physical_path:
                root_cause = f"Window activation failure: Explorer opened in background or failed to render window for '{resolved_physical_path}'."
                recommended_strategy = "com_shell_explore"
            else:
                root_cause = f"Unable to locate or launch folder for '{clean_target}'."
                recommended_strategy = "physical_path"

        return DiagnosticReport(
            target=target,
            action="open_folder",
            failure_identified=True,
            root_cause=root_cause,
            diagnostics=findings,
            suggested_recovery_strategy=recommended_strategy,
            details=details
        )
