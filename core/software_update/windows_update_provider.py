# core/software_update/windows_update_provider.py
"""
Windows Update Provider for Jarvis V2.1.
Dedicated OS-level update management using native Windows Update COM APIs and PowerShell.
Separates Windows operating system updates from third-party application updates.
"""

import json
import logging
import platform
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import PackageUpdateItem, UpdateChannelResult, UpdateStatus

logger = logging.getLogger("jarvis.software_update.windows_update")


class WindowsUpdateProvider:
    """
    Manages Windows OS updates, patch detection, and reboot requirements.
    Uses native Windows Update COM components (Microsoft.Update.Session) without
    requiring third-party modules.
    """

    PROVIDER_NAME = "windows_update"

    # PowerShell script to inspect pending/available Windows updates safely
    PS_CHECK_SCRIPT = """
$ErrorActionPreference = 'Stop'
try {
    $Session = New-Object -ComObject Microsoft.Update.Session
    $Searcher = $Session.CreateUpdateSearcher()
    $Searcher.Online = $true
    $Criteria = "IsInstalled=0 and Type='Software' and IsHidden=0"
    $Result = $Searcher.Search($Criteria)
    
    $Updates = @()
    foreach ($item in $Result.Updates) {
        $Updates += @{
            Title = $item.Title
            KBArticleIDs = ($item.KBArticleIDs -join ', ')
            Description = $item.Description
            IsMandatory = $item.IsMandatory
            RebootRequired = $item.RebootRequired
            MaxDownloadSize = $item.MaxDownloadSize
        }
    }
    
    $RebootPending = $false
    if (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired') {
        $RebootPending = $true
    }
    if (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing\\RebootPending') {
        $RebootPending = $true
    }

    @{
        Success = $true
        Count = $Updates.Count
        Updates = $Updates
        RebootPending = $RebootPending
    } | ConvertTo-Json -Depth 3 -Compress
} catch {
    @{
        Success = $false
        Error = $_.Exception.Message
        RebootPending = $false
    } | ConvertTo-Json -Compress
}
"""

    # PowerShell script to install pending updates
    PS_INSTALL_SCRIPT = """
$ErrorActionPreference = 'Stop'
try {
    $Session = New-Object -ComObject Microsoft.Update.Session
    $Searcher = $Session.CreateUpdateSearcher()
    $Result = $Searcher.Search("IsInstalled=0 and Type='Software' and IsHidden=0")
    
    if ($Result.Updates.Count -eq 0) {
        @{
            Success = $true
            InstalledCount = 0
            RebootRequired = $false
            Message = "No updates to install."
        } | ConvertTo-Json -Compress
        exit 0
    }

    $ToDownload = New-Object -ComObject Microsoft.Update.UpdateColl
    foreach ($up in $Result.Updates) {
        $ToDownload.Add($up) | Out-Null
    }
    
    $Downloader = $Session.CreateUpdateDownloader()
    $Downloader.Updates = $ToDownload
    $Downloader.Download() | Out-Null
    
    $ToInstall = New-Object -ComObject Microsoft.Update.UpdateColl
    foreach ($up in $Result.Updates) {
        if ($up.IsDownloaded) {
            $ToInstall.Add($up) | Out-Null
        }
    }
    
    $Installer = $Session.CreateUpdateInstaller()
    $Installer.Updates = $ToInstall
    $InstallResult = $Installer.Install()
    
    @{
        Success = $true
        InstalledCount = $ToInstall.Count
        ResultCode = $InstallResult.ResultCode
        RebootRequired = $InstallResult.RebootRequired
    } | ConvertTo-Json -Compress
} catch {
    @{
        Success = $false
        Error = $_.Exception.Message
    } | ConvertTo-Json -Compress
}
"""

    def __init__(self, runner: Optional[Callable[..., subprocess.CompletedProcess]] = None):
        self._runner = runner or subprocess.run
        self._is_windows = platform.system() == "Windows"

    def is_available(self) -> bool:
        """Windows Update provider is available on Windows operating systems."""
        return self._is_windows

    def check_updates(self, timeout_sec: int = 60) -> UpdateChannelResult:
        """Queries native Windows Update service for pending OS patches."""
        result = UpdateChannelResult(provider_name=self.PROVIDER_NAME)

        if not self.is_available():
            result.is_available = False
            result.error = "Windows Update provider is only supported on Windows operating systems."
            return result

        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", self.PS_CHECK_SCRIPT]
        extra_kwargs = {}
        if self._is_windows and hasattr(subprocess, "CREATE_NO_WINDOW"):
            extra_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            proc = self._runner(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                encoding="utf-8",
                errors="replace",
                **extra_kwargs,
            )
        except subprocess.TimeoutExpired:
            result.error = f"Windows Update check timed out after {timeout_sec}s."
            return result
        except Exception as e:
            result.error = f"Failed to execute Windows Update query: {e}"
            return result

        parsed_data = self._parse_json_result(proc.stdout)
        if not parsed_data:
            # Check if stdout or stderr has raw error
            result.error = proc.stderr.strip() if proc.stderr else "Windows Update check returned invalid data."
            return result

        if not parsed_data.get("Success", False):
            result.error = parsed_data.get("Error", "Unknown Windows Update error.")
            return result

        result.reboot_required = bool(parsed_data.get("RebootPending", False))
        updates_list = parsed_data.get("Updates", [])
        if isinstance(updates_list, dict):
            updates_list = [updates_list]

        result.checked = len(updates_list)
        for up in updates_list:
            title = up.get("Title", "Windows Update")
            kb = up.get("KBArticleIDs", "")
            pkg_id = f"KB{kb}" if kb else title
            item = PackageUpdateItem(
                package_name=title,
                package_id=pkg_id,
                current_version="Installed OS",
                target_version="Latest",
                source="windows_update",
                status=UpdateStatus.AVAILABLE,
                reboot_required=bool(up.get("RebootRequired", False)),
                details=up,
            )
            result.available_updates.append(item)

        return result

    def install_updates(self, timeout_sec: int = 600) -> UpdateChannelResult:
        """Downloads and installs pending Windows OS updates."""
        result = UpdateChannelResult(provider_name=self.PROVIDER_NAME)

        if not self.is_available():
            result.is_available = False
            result.error = "Windows Update provider is only supported on Windows."
            return result

        # Check preview first
        preview = self.check_updates()
        if preview.error:
            result.error = preview.error
            return result

        if not preview.available_updates:
            result.checked = 0
            result.reboot_required = preview.reboot_required
            return result

        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", self.PS_INSTALL_SCRIPT]
        extra_kwargs = {}
        if self._is_windows and hasattr(subprocess, "CREATE_NO_WINDOW"):
            extra_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            proc = self._runner(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                encoding="utf-8",
                errors="replace",
                **extra_kwargs,
            )
        except subprocess.TimeoutExpired:
            result.error = f"Windows Update installation timed out after {timeout_sec}s."
            return result
        except Exception as e:
            result.error = f"Failed to execute Windows Update installation: {e}"
            return result

        parsed_data = self._parse_json_result(proc.stdout)
        if not parsed_data or not parsed_data.get("Success", False):
            err_msg = parsed_data.get("Error") if parsed_data else proc.stderr.strip()
            result.error = err_msg or "Windows Update installation failed."
            return result

        installed_count = parsed_data.get("InstalledCount", 0)
        reboot_req = bool(parsed_data.get("RebootRequired", False)) or preview.reboot_required
        result.reboot_required = reboot_req

        for i, item in enumerate(preview.available_updates):
            if i < installed_count:
                item.status = UpdateStatus.UPDATED
                item.reboot_required = reboot_req
                result.updated_items.append(item)
            else:
                item.status = UpdateStatus.SKIPPED
                result.skipped_items.append(item)

        result.checked = len(preview.available_updates)
        return result

    def is_reboot_pending(self) -> bool:
        """Inspects system registry to determine if a restart is pending."""
        if not self.is_available():
            return False

        ps_script = """
$rb = $false
if (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired') { $rb = $true }
if (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing\\RebootPending') { $rb = $true }
Write-Output $rb
"""
        extra_kwargs = {}
        if self._is_windows and hasattr(subprocess, "CREATE_NO_WINDOW"):
            extra_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            proc = self._runner(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10,
                **extra_kwargs,
            )
            return "true" in proc.stdout.strip().lower()
        except Exception as e:
            logger.debug("Failed checking reboot pending: %s", e)
            return False

    def _parse_json_result(self, raw_output: str) -> Optional[Dict[str, Any]]:
        """Extracts and parses JSON from PowerShell output."""
        if not raw_output:
            return None
        text = raw_output.strip()
        try:
            return json.loads(text)
        except Exception:
            # Attempt to locate JSON boundaries
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    pass
        return None
