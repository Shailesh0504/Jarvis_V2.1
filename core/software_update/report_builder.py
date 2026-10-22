# core/software_update/report_builder.py
"""
Report Builder for Software Update Manager.
Generates honest, structured, source-separated natural-language reports in Hinglish and English.
Adheres strictly to the Conversational Feedback Policy and Anti-Hallucination Invariants.
"""

from typing import Any, Dict, List, Optional
from .models import UpdateChannelResult, UpdatePlan, UpdateStatus


class UpdateReportBuilder:
    """
    Builds precise, truthful status and execution reports.
    Guarantees:
    - Never merges disparate sources into a fake single number.
    - Never claims '100% of all software updated'.
    - Explicitly calls out skipped, unresolvable, or elevation-blocked packages.
    """

    @classmethod
    def build_check_summary(
        cls,
        plan: UpdatePlan,
        store_result: Optional[UpdateChannelResult] = None,
        language: str = "hi",
    ) -> str:
        """Generates summary message after update discovery phase."""
        winget_count = len(plan.winget_updates)
        windows_count = len(plan.windows_updates)
        store_count = len(plan.store_updates)
        total = winget_count + windows_count + store_count

        if total == 0:
            if plan.reboot_required:
                return (
                    "Aapka system aur installed applications up-to-date hain, lekin pichle updates ke liye ek restart pending hai, Boss."
                    if language == "hi"
                    else "Your system and installed applications are up to date, but a restart is currently pending."
                )
            return (
                "Aapka system aur installed software up-to-date hain, Boss. Koi naya update available nahi mila."
                if language == "hi"
                else "Your system and software are up to date, Boss. No pending updates found."
            )

        parts = []
        if winget_count > 0:
            parts.append(f"{winget_count} application update{'s' if winget_count > 1 else ''}")
        if windows_count > 0:
            parts.append(f"{windows_count} Windows update{'s' if windows_count > 1 else ''}")
        if store_count > 0:
            parts.append(f"{store_count} Microsoft Store update{'s' if store_count > 1 else ''}")

        summary_parts = " aur ".join(parts) if language == "hi" else " and ".join(parts)

        if language == "hi":
            msg = f"{summary_parts} available hain, Boss."
            if plan.skipped_items or plan.unknown_items:
                skip_count = len(plan.skipped_items) + len(plan.unknown_items)
                msg += f" ({skip_count} unmanaged/pinned packages skip kiye gaye)."
            msg += " Kya main inhe install kar doon?"
        else:
            msg = f"{summary_parts} available, Boss."
            if plan.skipped_items or plan.unknown_items:
                skip_count = len(plan.skipped_items) + len(plan.unknown_items)
                msg += f" ({skip_count} unmanaged/pinned items skipped)."
            msg += " Would you like me to install them?"

        return msg

    @classmethod
    def build_execution_summary(
        cls,
        winget_res: Optional[UpdateChannelResult] = None,
        windows_res: Optional[UpdateChannelResult] = None,
        store_res: Optional[UpdateChannelResult] = None,
        reboot_required: bool = False,
        language: str = "hi",
    ) -> str:
        """Generates comprehensive post-update summary from execution results."""
        w_updated = len(winget_res.updated_items) if winget_res else 0
        w_failed = len(winget_res.failed_items) if winget_res else 0
        w_skipped = len(winget_res.skipped_items) if winget_res else 0

        win_updated = len(windows_res.updated_items) if windows_res else 0
        win_failed = len(windows_res.failed_items) if windows_res else 0

        s_updated = len(store_res.updated_items) if store_res else 0
        s_failed = len(store_res.failed_items) if store_res else 0

        total_updated = w_updated + win_updated + s_updated
        total_failed = w_failed + win_failed + s_failed

        if total_updated == 0 and total_failed == 0:
            if reboot_required:
                return (
                    "Koi naya update install nahi hua, lekin pichle updates ke liye ek restart required hai, Boss."
                    if language == "hi"
                    else "No new updates were installed, but a system restart is required, Boss."
                )
            return (
                "Koi pending update install nahi hua, Boss."
                if language == "hi"
                else "No pending updates were installed, Boss."
            )

        # Check for elevation failures specifically
        elevation_failures = [
            it.package_name
            for it in (winget_res.failed_items if winget_res else [])
            if it.status == UpdateStatus.REQUIRES_ELEVATION
        ]

        if language == "hi":
            sentences = []
            sentences.append("Available application aur Windows updates check karke execute kiye.")

            details = []
            if w_updated > 0:
                details.append(f"WinGet se {w_updated} app{'s' if w_updated > 1 else ''} update hue")
            if s_updated > 0:
                details.append(f"Microsoft Store se {s_updated} app{'s' if s_updated > 1 else ''} update hue")
            if win_updated > 0:
                details.append(f"{win_updated} Windows update{'s' if win_updated > 1 else ''} install hue")

            if details:
                sentences.append(", ".join(details) + ".")

            if total_failed > 0:
                if elevation_failures:
                    sentences.append(
                        f"{len(elevation_failures)} update administrator permission maang rahe the, isliye woh complete nahi ho paaye."
                    )
                else:
                    sentences.append(f"{total_failed} update kisi issue ki wajah se complete nahi ho sake.")

            if w_skipped > 0:
                sentences.append(f"{w_skipped} app skipped rahe kyunki unka update source supported ya unpinned nahi tha.")

            if reboot_required:
                sentences.append("Kuch updates complete karne ke liye ek restart required hai, Boss.")

            return " ".join(sentences)
        else:
            sentences = []
            sentences.append("Executed available application and Windows updates.")

            details = []
            if w_updated > 0:
                details.append(f"{w_updated} app{'s' if w_updated > 1 else ''} updated via WinGet")
            if s_updated > 0:
                details.append(f"{s_updated} app{'s' if s_updated > 1 else ''} updated via Microsoft Store")
            if win_updated > 0:
                details.append(f"{win_updated} Windows update{'s' if win_updated > 1 else ''} installed")

            if details:
                sentences.append(", ".join(details) + ".")

            if total_failed > 0:
                if elevation_failures:
                    sentences.append(
                        f"{len(elevation_failures)} updates required administrator permissions and could not proceed."
                    )
                else:
                    sentences.append(f"{total_failed} update{'s' if total_failed > 1 else ''} failed.")

            if w_skipped > 0:
                sentences.append(f"{w_skipped} packages skipped (unmanaged or pinned).")

            if reboot_required:
                sentences.append("A system restart is required to finish installing updates, Boss.")

            return " ".join(sentences)
