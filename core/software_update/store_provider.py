# core/software_update/store_provider.py
"""
Microsoft Store Update Provider for Jarvis V2.1.
Handles Microsoft Store / UWP application update detection and automated policy handling.
Provides honest capability reporting when automated Store updates cannot be safely completed.
"""

import logging
import shutil
import subprocess
from typing import Any, Callable, Dict, List, Optional

from .models import PackageUpdateItem, UpdateChannelResult, UpdateStatus

logger = logging.getLogger("jarvis.software_update.store")


class StoreUpdateProvider:
    """
    Manages Microsoft Store package updates.
    Enforces honest capability boundary:
    If Store automation is unavailable or untrusted, returns honest guidance
    rather than fabricating automated update completion.
    """

    PROVIDER_NAME = "microsoft_store"

    UNAVAILABLE_GUIDANCE = (
        "Microsoft Store updates ka automatic installation is environment mein available nahi hai; "
        "main unhe separately check/guide kar sakta hoon."
    )

    def __init__(self, runner: Optional[Callable[..., subprocess.CompletedProcess]] = None):
        self._runner = runner or subprocess.run
        self._has_winget = shutil.which("winget") is not None

    def is_available(self) -> bool:
        """Store updates via winget source msstore are available if winget exists."""
        return self._has_winget

    def check_updates(self, timeout_sec: int = 45) -> UpdateChannelResult:
        """Queries Microsoft Store for available updates using winget msstore source."""
        result = UpdateChannelResult(provider_name=self.PROVIDER_NAME)

        if not self.is_available():
            result.is_available = False
            result.error = self.UNAVAILABLE_GUIDANCE
            return result

        cmd = ["winget", "upgrade", "--source", "msstore"]
        try:
            proc = self._runner(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            result.error = f"Microsoft Store update check timed out after {timeout_sec}s."
            return result
        except Exception as e:
            result.error = f"Failed to check Microsoft Store updates: {e}"
            return result

        output = proc.stdout or ""
        # If winget does not support msstore source or msstore is disabled
        if "The source name was not found" in output or "No sources match the given value" in output:
            result.is_available = False
            result.error = self.UNAVAILABLE_GUIDANCE
            return result

        items = self._parse_store_output(output)
        result.checked = len(items)
        result.available_updates = items
        return result

    def upgrade_all(self, timeout_sec: int = 300) -> UpdateChannelResult:
        """Attempts to upgrade Store packages where supported."""
        result = UpdateChannelResult(provider_name=self.PROVIDER_NAME)

        if not self.is_available():
            result.is_available = False
            result.error = self.UNAVAILABLE_GUIDANCE
            return result

        preview = self.check_updates()
        if not preview.is_available:
            result.is_available = False
            result.error = self.UNAVAILABLE_GUIDANCE
            return result

        if not preview.available_updates:
            result.checked = 0
            return result

        cmd = [
            "winget", "upgrade", "--all", "--source", "msstore",
            "--accept-source-agreements", "--accept-package-agreements"
        ]
        try:
            proc = self._runner(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            result.error = f"Microsoft Store upgrade timed out after {timeout_sec}s."
            return result
        except Exception as e:
            result.error = f"Failed to execute Microsoft Store upgrade: {e}"
            return result

        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        exit_code = proc.returncode

        if exit_code == 0:
            for item in preview.available_updates:
                item.status = UpdateStatus.UPDATED
                result.updated_items.append(item)
        else:
            result.error = f"Store upgrade completed with warnings (code {exit_code})."
            for item in preview.available_updates:
                item.status = UpdateStatus.FAILED
                item.error_reason = "Store package installer failed"
                result.failed_items.append(item)

        result.checked = len(preview.available_updates)
        return result

    def _parse_store_output(self, output: str) -> List[PackageUpdateItem]:
        """Parses output from winget --source msstore."""
        items: List[PackageUpdateItem] = []
        if not output:
            return items

        lines = output.splitlines()
        dash_found = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("---"):
                dash_found = True
                continue
            if not dash_found or not stripped:
                continue
            if "upgrades available" in stripped.lower():
                break

            parts = [p.strip() for p in stripped.split("  ") if p.strip()]
            if len(parts) >= 2:
                name = parts[0]
                pkg_id = parts[1]
                cur_ver = parts[2] if len(parts) > 2 else "Unknown"
                avail_ver = parts[3] if len(parts) > 3 else "Latest"
                items.append(
                    PackageUpdateItem(
                        package_name=name,
                        package_id=pkg_id,
                        current_version=cur_ver,
                        target_version=avail_ver,
                        source="msstore",
                        status=UpdateStatus.AVAILABLE,
                    )
                )

        return items
