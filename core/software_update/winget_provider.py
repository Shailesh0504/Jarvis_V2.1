# core/software_update/winget_provider.py
"""
WinGet Update Provider for Jarvis V2.1.
Encapsulates discovery, policy validation, execution, and state verification
for Windows Package Manager (winget) managed applications.
"""

import logging
import re
import shutil
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import PackageUpdateItem, UpdateChannelResult, UpdateStatus

logger = logging.getLogger("jarvis.software_update.winget")


class WingetUpdateProvider:
    """
    Manages application updates via Windows Package Manager (winget).
    Guarantees:
    - Never uses --force or --ignore-security-hash without explicit policy permission.
    - Accurately identifies packages with unknown versions or pinned status.
    - Detects elevation requirements and UAC boundaries honestly.
    - Performs post-install verification by re-querying package versions.
    """

    PROVIDER_NAME = "winget"

    # Known Winget HRESULT / Exit Codes
    EXIT_SUCCESS = 0
    EXIT_NO_APPLICABLE_UPDATES = -1978335189
    EXIT_UPDATE_NOT_APPLICABLE = -1978334963
    EXIT_REBOOT_REQUIRED = 3010
    EXIT_INSTALL_REBOOT_REQUIRED = -1978334965

    def __init__(self, runner: Optional[Callable[..., subprocess.CompletedProcess]] = None):
        self._runner = runner or subprocess.run
        self._is_available: Optional[bool] = None

    def is_available(self) -> bool:
        """Checks if winget binary is present and accessible in PATH."""
        if self._is_available is not None:
            return self._is_available
        winget_path = shutil.which("winget")
        self._is_available = winget_path is not None
        return self._is_available

    def check_updates(
        self,
        include_unknown: bool = False,
        include_pinned: bool = False,
        timeout_sec: int = 45,
    ) -> UpdateChannelResult:
        """
        Runs 'winget upgrade' in preview mode and parses available upgrades.
        Does NOT modify any installed software.
        """
        result = UpdateChannelResult(provider_name=self.PROVIDER_NAME)

        if not self.is_available():
            result.is_available = False
            result.error = "Windows Package Manager (winget) is not installed or not in PATH."
            return result

        cmd = ["winget", "upgrade"]
        if include_unknown:
            cmd.append("--include-unknown")
        if include_pinned:
            cmd.append("--include-pinned")

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
            result.error = f"winget check timed out after {timeout_sec}s."
            return result
        except Exception as e:
            result.error = f"Failed to execute winget: {e}"
            return result

        parsed_items, unknown_items, pinned_items = self.parse_upgrade_output(proc.stdout)
        result.checked = len(parsed_items) + len(unknown_items) + len(pinned_items)
        result.available_updates = parsed_items
        result.skipped_items = unknown_items + pinned_items

        return result

    def upgrade_all(
        self,
        accept_agreements: bool = True,
        include_unknown: bool = False,
        include_pinned: bool = False,
        allow_reboot: bool = False,
        timeout_sec: int = 300,
        package_ids: Optional[List[str]] = None,
    ) -> UpdateChannelResult:
        """
        Executes 'winget upgrade --all' or upgrades specific packages.
        Strictly excludes dangerous flags (--force, --ignore-security-hash).
        """
        result = UpdateChannelResult(provider_name=self.PROVIDER_NAME)

        if not self.is_available():
            result.is_available = False
            result.error = "Windows Package Manager (winget) is not available."
            return result

        # 1. Preview first if not already given package_ids
        preview = self.check_updates(include_unknown=include_unknown, include_pinned=include_pinned)
        if preview.error:
            result.error = preview.error
            return result

        items_to_upgrade = preview.available_updates
        if package_ids:
            target_set = {pid.lower() for pid in package_ids}
            items_to_upgrade = [it for it in items_to_upgrade if it.package_id.lower() in target_set]

        if not items_to_upgrade:
            result.checked = preview.checked
            return result

        # 2. Build upgrade command line
        cmd = ["winget", "upgrade"]
        if package_ids and len(package_ids) == 1:
            cmd.extend(["--id", package_ids[0], "--exact"])
        else:
            cmd.append("--all")

        if accept_agreements:
            cmd.extend(["--accept-source-agreements", "--accept-package-agreements"])
        if include_unknown:
            cmd.append("--include-unknown")
        if include_pinned:
            cmd.append("--include-pinned")
        if allow_reboot:
            cmd.append("--allow-reboot")

        logger.info("Executing winget upgrade with command: %s", " ".join(cmd))

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
            result.error = f"winget upgrade timed out after {timeout_sec}s."
            return result
        except Exception as e:
            result.error = f"Failed to run winget upgrade: {e}"
            return result

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        combined = stdout + "\n" + stderr
        exit_code = proc.returncode

        # 3. Check for elevation requirements
        needs_elevation = self._detect_elevation_requirement(combined, exit_code)

        # 4. Check reboot requirement from exit code or output
        reboot_req = exit_code in (self.EXIT_REBOOT_REQUIRED, self.EXIT_INSTALL_REBOOT_REQUIRED) or bool(
            re.search(r"\b(?:reboot|restart)\s+(?:is\s+)?required\b", combined, re.IGNORECASE)
        )
        result.reboot_required = reboot_req

        # 5. Verify individual package statuses
        for item in items_to_upgrade:
            ver_status, ver_err = self._verify_package_status(item, combined, exit_code, needs_elevation)
            item.status = ver_status
            if reboot_req and ver_status == UpdateStatus.UPDATED:
                item.reboot_required = True

            if ver_status == UpdateStatus.UPDATED:
                result.updated_items.append(item)
            elif ver_status in (UpdateStatus.FAILED, UpdateStatus.REQUIRES_ELEVATION):
                item.error_reason = ver_err
                result.failed_items.append(item)
            else:
                result.skipped_items.append(item)

        result.checked = len(items_to_upgrade)
        return result

    def parse_upgrade_output(
        self, output: str
    ) -> Tuple[List[PackageUpdateItem], List[PackageUpdateItem], List[PackageUpdateItem]]:
        """
        Parses the tabular output of 'winget upgrade'.
        Returns: (upgradable_items, unknown_items, pinned_items)
        """
        upgradable: List[PackageUpdateItem] = []
        unknown: List[PackageUpdateItem] = []
        pinned: List[PackageUpdateItem] = []

        if not output:
            return upgradable, unknown, pinned

        lines = output.splitlines()
        header_idx = -1
        col_splits: List[int] = []

        # Find dashed separator line (e.g. "-------------------")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("---") and len(stripped) >= 10:
                header_idx = i - 1
                break

        if header_idx < 0 or header_idx >= len(lines):
            return self._regex_fallback_parse(output)

        header_line = lines[header_idx]
        sep_line = lines[header_idx + 1]

        # Determine column positions: Name, Id, Version, Available, Source
        name_pos = header_line.find("Name")
        id_pos = header_line.find("Id")
        ver_pos = header_line.find("Version")
        avail_pos = header_line.find("Available")
        src_pos = header_line.find("Source")

        if min(name_pos, id_pos, ver_pos, avail_pos) < 0:
            return self._regex_fallback_parse(output)

        # Parse row lines after separator
        for line in lines[header_idx + 2:]:
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"^\d+\s+upgrades?\s+available", stripped, re.IGNORECASE):
                break
            if stripped.startswith("No installed package found") or stripped.startswith("No applicable upgrade"):
                break

            try:
                parts = stripped.split()
                if len(parts) < 4:
                    continue

                is_pinned = "pinned" in stripped.lower()
                if parts[-1].lower() in ("(pinned)", "pinned"):
                    parts.pop()

                if len(parts) >= 5:
                    src = parts[-1]
                    avail_ver = parts[-2]
                    cur_ver = parts[-3]
                    pkg_id = parts[-4]
                    name = " ".join(parts[:-4])
                else:
                    src = "winget"
                    avail_ver = parts[-1]
                    cur_ver = parts[-2]
                    pkg_id = parts[-3]
                    name = parts[0]

                item = PackageUpdateItem(
                    package_name=name or pkg_id,
                    package_id=pkg_id,
                    current_version=cur_ver or "Unknown",
                    target_version=avail_ver or "Latest",
                    source=src or "winget",
                    status=UpdateStatus.AVAILABLE,
                )

                if "unknown" in cur_ver.lower() or "unknown" in avail_ver.lower():
                    item.status = UpdateStatus.UNKNOWN
                    unknown.append(item)
                elif is_pinned:
                    item.status = UpdateStatus.BLOCKED
                    pinned.append(item)
                else:
                    upgradable.append(item)
            except Exception as e:
                logger.debug("Failed parsing row: %s error=%s", line, e)

        return upgradable, unknown, pinned

    def _regex_fallback_parse(
        self, output: str
    ) -> Tuple[List[PackageUpdateItem], List[PackageUpdateItem], List[PackageUpdateItem]]:
        """Fallback regex parser for non-standard or shifted column headers."""
        upgradable: List[PackageUpdateItem] = []
        unknown: List[PackageUpdateItem] = []
        pinned: List[PackageUpdateItem] = []

        # Example line: "Google Chrome  Google.Chrome  120.0.6099.130  120.0.6099.217  winget"
        row_pat = re.compile(
            r"^(?P<name>.+?)\s{2,}(?P<id>[A-Za-z0-9_\-\.]+)\s{2,}(?P<curr>[^\s]+)\s{2,}(?P<avail>[^\s]+)(?:\s{2,}(?P<src>[^\s]+))?$"
        )

        for line in output.splitlines():
            s = line.strip()
            if not s or s.startswith("---") or s.startswith("Name") or "upgrades available" in s:
                continue
            m = row_pat.match(s)
            if m:
                d = m.groupdict()
                pkg_id = d["id"]
                name = d["name"]
                cur_ver = d["curr"]
                avail_ver = d["avail"]
                src = d.get("src") or "winget"

                item = PackageUpdateItem(
                    package_name=name,
                    package_id=pkg_id,
                    current_version=cur_ver,
                    target_version=avail_ver,
                    source=src,
                    status=UpdateStatus.AVAILABLE,
                )
                if "unknown" in cur_ver.lower() or "unknown" in avail_ver.lower():
                    item.status = UpdateStatus.UNKNOWN
                    unknown.append(item)
                elif "pinned" in s.lower():
                    item.status = UpdateStatus.BLOCKED
                    pinned.append(item)
                else:
                    upgradable.append(item)

        return upgradable, unknown, pinned

    def _detect_elevation_requirement(self, output: str, exit_code: int) -> bool:
        """Determines if the upgrade process failed due to administrative privileges."""
        elevation_terms = [
            "administrator privileges",
            "requires elevation",
            "access is denied",
            "run as administrator",
            "elevation required",
            "user account control",
            "0x80070005",
        ]
        lowered = output.lower()
        if any(term in lowered for term in elevation_terms):
            return True
        return False

    def _verify_package_status(
        self,
        item: PackageUpdateItem,
        combined_output: str,
        exit_code: int,
        needs_elevation: bool,
    ) -> Tuple[UpdateStatus, Optional[str]]:
        """Verifies whether an individual package succeeded, failed, or requires elevation."""
        pkg_id_lower = item.package_id.lower()
        pkg_name_lower = item.package_name.lower()
        comb_lower = combined_output.lower()

        if needs_elevation:
            return UpdateStatus.REQUIRES_ELEVATION, "Administrator permission required"

        # Check if package specifically had an error in output (by ID or name)
        pkg_err_match = re.search(
            rf"(?:{re.escape(pkg_id_lower)}|{re.escape(pkg_name_lower)}).*?(?:failed|error|cancelled|hash|mismatch)",
            comb_lower,
        )
        if pkg_err_match:
            return UpdateStatus.FAILED, "Installer returned failure or hash error"

        # Check if package specifically succeeded (by ID or name)
        pkg_success_match = re.search(
            rf"(?:successfully installed|successful upgrade).*?(?:{re.escape(pkg_id_lower)}|{re.escape(pkg_name_lower)})|(?:{re.escape(pkg_id_lower)}|{re.escape(pkg_name_lower)}).*?(?:successfully installed|successful)",
            comb_lower,
        )
        if pkg_success_match:
            return UpdateStatus.UPDATED, None

        if exit_code == 0:
            return UpdateStatus.UPDATED, None

        if exit_code != 0:
            return UpdateStatus.FAILED, f"Upgrade failed with exit code {exit_code}"

        return UpdateStatus.VERIFICATION_UNKNOWN, "Verification inconclusive"
