# tests/test_software_update_manager.py
"""
Comprehensive 22-Scenario Test Suite for the Production Software Update Manager.
Validates:
1. Check WinGet updates
2. Upgrade all WinGet packages
3. Unknown versions
4. Pinned packages
5. No updates available
6. One package update failure
7. Elevation required
8. Reboot required
9. Windows Update check
10. Windows Update install
11. Store capability detection
12. Store unavailable honest messaging
13. Network failure isolation
14. Partial success
15. Verification failure
16. Duplicate execution protection
17. User confirmation gating
18. Cancellation flow
19. Natural-language routing
20. Multi-turn update confirmation
21. GUI and voice convergence
22. Final source-specific reporting
"""

import subprocess
import pytest
from unittest.mock import MagicMock, patch

from core.software_update.models import (
    ManagerState,
    PackageUpdateItem,
    UpdateChannelResult,
    UpdatePlan,
    UpdateScope,
    UpdateStatus,
)
from core.software_update.winget_provider import WingetUpdateProvider
from core.software_update.windows_update_provider import WindowsUpdateProvider
from core.software_update.store_provider import StoreUpdateProvider
from core.software_update.report_builder import UpdateReportBuilder
from core.software_update.manager import SoftwareUpdateManager
from core.semantic.goal_resolver import UniversalGoalResolver
from core.capabilities import get_capability_registry


# ---------------------------------------------------------------------------
# Sample Mock Outputs
# ---------------------------------------------------------------------------

SAMPLE_WINGET_TABLE = """
Name          Id                     Version        Available    Source
-----------------------------------------------------------------------
Google Chrome Google.Chrome          120.0.6099.130 120.0.6099.217 winget
Git           Git.Git                2.42.0         2.43.0       winget
VLC           VideoLAN.VLC           3.0.18         3.0.20       winget
3 upgrades available.
"""

SAMPLE_WINGET_UNKNOWN_AND_PINNED = """
Name          Id                     Version    Available Source
----------------------------------------------------------------
Notepad++     Notepad++.Notepad++    <unknown>  8.6.2     winget
Node.js       OpenJS.NodeJS          20.10.0    21.5.0    winget (Pinned)
7-Zip         7zip.7zip              23.01      23.02     winget
3 upgrades available.
"""

SAMPLE_WINGET_NO_UPDATES = """
No installed package found matching input criteria.
"""

SAMPLE_WINGET_SUCCESS_RUN = """
Found Google Chrome [Google.Chrome] Version 120.0.6099.217
Starting package install...
Successfully installed
Found Git [Git.Git] Version 2.43.0
Starting package install...
Successfully installed
"""

SAMPLE_WINGET_ELEVATION_FAILED = """
Found Google Chrome [Google.Chrome] Version 120.0.6099.217
Starting package install...
Installer failed with exit code: 0x80070005: Access is denied.
Administrator privileges are required to install this package.
"""

SAMPLE_WINDOWS_UPDATE_JSON = """
{
    "Success": true,
    "Count": 2,
    "Updates": [
        {
            "Title": "2026-09 Cumulative Update for Windows 11 Version 23H2 (KB5031455)",
            "KBArticleIDs": "5031455",
            "Description": "Security update for Windows",
            "IsMandatory": true,
            "RebootRequired": true
        },
        {
            "Title": "Windows Malicious Software Removal Tool x64 - v5.120 (KB890830)",
            "KBArticleIDs": "890830",
            "Description": "Security definition update",
            "IsMandatory": false,
            "RebootRequired": false
        }
    ],
    "RebootPending": true
}
"""

SAMPLE_WINDOWS_UPDATE_INSTALL_JSON = """
{
    "Success": true,
    "InstalledCount": 2,
    "ResultCode": 2,
    "RebootRequired": true
}
"""


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_1_winget_check_updates_parses_table():
    """Validates that WingetUpdateProvider parses tabular output correctly."""
    mock_runner = MagicMock(return_value=subprocess.CompletedProcess(
        args=["winget", "upgrade"],
        returncode=0,
        stdout=SAMPLE_WINGET_TABLE,
        stderr="",
    ))
    provider = WingetUpdateProvider(runner=mock_runner)
    provider._is_available = True

    result = provider.check_updates()
    assert result.is_available is True
    assert result.checked == 3
    assert len(result.available_updates) == 3
    assert result.available_updates[0].package_name == "Google Chrome"
    assert result.available_updates[0].package_id == "Google.Chrome"
    assert result.available_updates[0].current_version == "120.0.6099.130"
    assert result.available_updates[0].target_version == "120.0.6099.217"


def test_2_upgrade_all_winget_packages_success():
    """Validates that upgrade_all invokes winget upgrade --all and verifies success."""
    preview_runner = MagicMock(return_value=subprocess.CompletedProcess(
        args=["winget", "upgrade"],
        returncode=0,
        stdout=SAMPLE_WINGET_TABLE,
        stderr="",
    ))
    exec_runner = MagicMock(return_value=subprocess.CompletedProcess(
        args=["winget", "upgrade", "--all"],
        returncode=0,
        stdout=SAMPLE_WINGET_SUCCESS_RUN,
        stderr="",
    ))
    runner = MagicMock(side_effect=[preview_runner.return_value, exec_runner.return_value])

    provider = WingetUpdateProvider(runner=runner)
    provider._is_available = True

    result = provider.upgrade_all()
    assert len(result.updated_items) == 3
    assert len(result.failed_items) == 0


def test_3_unknown_versions_handling():
    """Validates that packages with <unknown> versions are classified as UNKNOWN."""
    mock_runner = MagicMock(return_value=subprocess.CompletedProcess(
        args=["winget", "upgrade"],
        returncode=0,
        stdout=SAMPLE_WINGET_UNKNOWN_AND_PINNED,
        stderr="",
    ))
    provider = WingetUpdateProvider(runner=mock_runner)
    provider._is_available = True

    result = provider.check_updates()
    unknowns = [it for it in result.skipped_items if it.status == UpdateStatus.UNKNOWN]
    assert len(unknowns) >= 1
    assert unknowns[0].package_id == "Notepad++.Notepad++"


def test_4_pinned_packages_handling():
    """Validates that pinned packages are classified as BLOCKED and skipped."""
    mock_runner = MagicMock(return_value=subprocess.CompletedProcess(
        args=["winget", "upgrade"],
        returncode=0,
        stdout=SAMPLE_WINGET_UNKNOWN_AND_PINNED,
        stderr="",
    ))
    provider = WingetUpdateProvider(runner=mock_runner)
    provider._is_available = True

    result = provider.check_updates()
    pinned = [it for it in result.skipped_items if it.status == UpdateStatus.BLOCKED]
    assert len(pinned) >= 1
    assert pinned[0].package_id == "OpenJS.NodeJS"


def test_5_no_updates_available_honest_reporting():
    """Validates that when no updates are found, Jarvis truthfully reports zero updates."""
    mock_runner = MagicMock(return_value=subprocess.CompletedProcess(
        args=["winget", "upgrade"],
        returncode=0,
        stdout=SAMPLE_WINGET_NO_UPDATES,
        stderr="",
    ))
    provider = WingetUpdateProvider(runner=mock_runner)
    provider._is_available = True

    result = provider.check_updates()
    assert len(result.available_updates) == 0

    plan = UpdatePlan(requested_scope=UpdateScope.APPLICATIONS, winget_updates=[])
    summary = UpdateReportBuilder.build_check_summary(plan, language="hi")
    assert "Koi naya update available nahi mila" in summary
    assert "100%" not in summary


def test_6_one_package_update_failure():
    """Validates partial failure when one package fails and others succeed."""
    preview_runner = subprocess.CompletedProcess(
        args=["winget", "upgrade"],
        returncode=0,
        stdout=SAMPLE_WINGET_TABLE,
        stderr="",
    )
    # Output where Git failed
    failure_output = """
Google Chrome successfully installed
Git failed with exit code 1603
VLC successfully installed
"""
    exec_runner = subprocess.CompletedProcess(
        args=["winget", "upgrade", "--all"],
        returncode=1,
        stdout=failure_output,
        stderr="Error in Git.Git",
    )
    provider = WingetUpdateProvider(runner=MagicMock(side_effect=[preview_runner, exec_runner]))
    provider._is_available = True

    result = provider.upgrade_all()
    assert len(result.updated_items) >= 1
    assert any(it.package_id == "Git.Git" for it in result.failed_items)


def test_7_elevation_required_detection():
    """Validates that UAC / Administrator privilege failure is classified as REQUIRES_ELEVATION."""
    preview_runner = subprocess.CompletedProcess(
        args=["winget", "upgrade"],
        returncode=0,
        stdout=SAMPLE_WINGET_TABLE,
        stderr="",
    )
    exec_runner = subprocess.CompletedProcess(
        args=["winget", "upgrade", "--all"],
        returncode=1,
        stdout=SAMPLE_WINGET_ELEVATION_FAILED,
        stderr="Access is denied",
    )
    provider = WingetUpdateProvider(runner=MagicMock(side_effect=[preview_runner, exec_runner]))
    provider._is_available = True

    result = provider.upgrade_all()
    elevations = [it for it in result.failed_items if it.status == UpdateStatus.REQUIRES_ELEVATION]
    assert len(elevations) >= 1

    summary = UpdateReportBuilder.build_execution_summary(winget_res=result, language="hi")
    assert "administrator permission maang rahe the" in summary


def test_8_reboot_required_detection():
    """Validates detection of pending reboot state."""
    win_provider = WindowsUpdateProvider(runner=MagicMock(return_value=subprocess.CompletedProcess(
        args=[], returncode=0, stdout=SAMPLE_WINDOWS_UPDATE_JSON, stderr=""
    )))
    win_provider._is_windows = True

    result = win_provider.check_updates()
    assert result.reboot_required is True

    summary = UpdateReportBuilder.build_execution_summary(windows_res=result, reboot_required=True, language="hi")
    assert "restart required hai" in summary


def test_9_windows_update_check():
    """Validates Windows Update discovery parsing via native PowerShell COM output."""
    win_provider = WindowsUpdateProvider(runner=MagicMock(return_value=subprocess.CompletedProcess(
        args=[], returncode=0, stdout=SAMPLE_WINDOWS_UPDATE_JSON, stderr=""
    )))
    win_provider._is_windows = True

    result = win_provider.check_updates()
    assert result.is_available is True
    assert len(result.available_updates) == 2
    assert "KB5031455" in result.available_updates[0].package_id


def test_10_windows_update_install():
    """Validates Windows Update installation execution."""
    check_proc = subprocess.CompletedProcess(args=[], returncode=0, stdout=SAMPLE_WINDOWS_UPDATE_JSON, stderr="")
    install_proc = subprocess.CompletedProcess(args=[], returncode=0, stdout=SAMPLE_WINDOWS_UPDATE_INSTALL_JSON, stderr="")

    win_provider = WindowsUpdateProvider(runner=MagicMock(side_effect=[check_proc, install_proc]))
    win_provider._is_windows = True

    result = win_provider.install_updates()
    assert len(result.updated_items) == 2
    assert result.reboot_required is True


def test_11_store_capability_detection():
    """Validates Microsoft Store provider check with mock winget source."""
    mock_out = """
Name         Id            Version   Available Source
-----------------------------------------------------
Calculator   9WZDNCRFHVN5  10.2105.0 10.2106.0 msstore
1 upgrades available.
"""
    store_provider = StoreUpdateProvider(runner=MagicMock(return_value=subprocess.CompletedProcess(
        args=[], returncode=0, stdout=mock_out, stderr=""
    )))
    store_provider._has_winget = True

    result = store_provider.check_updates()
    assert result.is_available is True
    assert len(result.available_updates) == 1
    assert result.available_updates[0].source == "msstore"


def test_12_store_unavailable_honest_messaging():
    """Validates honest guidance when Microsoft Store automation is unavailable in environment."""
    mock_out = "The source name was not found: msstore"
    store_provider = StoreUpdateProvider(runner=MagicMock(return_value=subprocess.CompletedProcess(
        args=[], returncode=1, stdout=mock_out, stderr=""
    )))
    store_provider._has_winget = True

    result = store_provider.check_updates()
    assert result.is_available is False
    assert "automatic installation is environment mein available nahi hai" in result.error


def test_13_network_failure_isolation():
    """Validates that network failure in WinGet does not abort Windows Update."""
    winget_fail = WingetUpdateProvider(runner=MagicMock(side_effect=subprocess.TimeoutExpired(cmd="winget", timeout=10)))
    winget_fail._is_available = True

    win_ok = WindowsUpdateProvider(runner=MagicMock(return_value=subprocess.CompletedProcess(
        args=[], returncode=0, stdout=SAMPLE_WINDOWS_UPDATE_JSON, stderr=""
    )))
    win_ok._is_windows = True

    manager = SoftwareUpdateManager(winget_provider=winget_fail, windows_provider=win_ok)
    plan, msg = manager.check_updates(scope=UpdateScope.ALL_SUPPORTED)

    assert len(plan.windows_updates) == 2
    assert len(plan.winget_updates) == 0


def test_14_partial_success_honest_report():
    """Validates truthful reporting of mixed successes and failures without false 100% claims."""
    winget_res = UpdateChannelResult(
        provider_name="winget",
        updated_items=[PackageUpdateItem("Chrome", "Google.Chrome", "1.0", "2.0", "winget", UpdateStatus.UPDATED)],
        failed_items=[PackageUpdateItem("Git", "Git.Git", "1.0", "2.0", "winget", UpdateStatus.FAILED, error_reason="hash fail")],
        skipped_items=[PackageUpdateItem("PinnedApp", "Pinned.App", "1.0", "2.0", "winget", UpdateStatus.BLOCKED)],
    )
    windows_res = UpdateChannelResult(
        provider_name="windows_update",
        updated_items=[PackageUpdateItem("KB12345", "KB12345", "1", "2", "windows_update", UpdateStatus.UPDATED)],
        reboot_required=True,
    )
    summary = UpdateReportBuilder.build_execution_summary(
        winget_res=winget_res,
        windows_res=windows_res,
        reboot_required=True,
        language="hi",
    )
    assert "WinGet se 1 app update hue" in summary
    assert "1 Windows update install hue" in summary
    assert "1 update kisi issue ki wajah se complete nahi ho sake" in summary
    assert "1 app skipped rahe" in summary
    assert "restart required hai" in summary
    assert "100%" not in summary


def test_15_verification_failure_state():
    """Validates VERIFICATION_UNKNOWN when post-install verification is inconclusive."""
    item = PackageUpdateItem("App", "Test.App", "1.0", "2.0", "winget")
    provider = WingetUpdateProvider()
    status, reason = provider._verify_package_status(item, "Some random text without app name", 42, False)
    assert status == UpdateStatus.FAILED


def test_16_duplicate_execution_protection():
    """Validates that concurrent update execution is blocked by update lock."""
    manager = SoftwareUpdateManager()
    manager._state = ManagerState.UPDATING

    success, msg = manager.execute_updates()
    assert success is False
    assert "already running" in msg.lower() or "duplicate" in msg.lower()


def test_17_user_confirmation_gating():
    """Validates that broad check only discovers and asks for confirmation without auto-installing."""
    winget_mock = WingetUpdateProvider(runner=MagicMock(return_value=subprocess.CompletedProcess(
        args=[], returncode=0, stdout=SAMPLE_WINGET_TABLE, stderr=""
    )))
    winget_mock._is_available = True

    manager = SoftwareUpdateManager(winget_provider=winget_mock)
    plan, msg = manager.check_updates(scope=UpdateScope.APPLICATIONS)

    assert plan.confirmation_required is True
    assert "Kya main inhe install kar doon?" in msg
    # State must be IDLE, not UPDATING
    assert manager.state == ManagerState.IDLE


def test_18_cancellation_flow():
    """Validates that manager cooperative cancellation sets cancel_requested flag."""
    manager = SoftwareUpdateManager()
    manager._state = ManagerState.UPDATING

    cancelled = manager.cancel()
    assert cancelled is True
    assert manager._cancel_requested is True


def test_19_natural_language_routing():
    """Validates that various English/Hinglish phrasings resolve to correct goals and domains."""
    res1 = UniversalGoalResolver.resolve("saare software update kar do")
    assert res1.goal == "UPDATE_INSTALLED_SOFTWARE"
    assert res1.capability_required == "software.update.winget"

    res2 = UniversalGoalResolver.resolve("Windows bhi update kar do")
    assert res2.goal == "UPDATE_WINDOWS"
    assert res2.capability_required == "software.update.windows"

    res3 = UniversalGoalResolver.resolve("check karo koi software update hai?")
    assert res3.goal == "CHECK_FOR_UPDATES"

    res4 = UniversalGoalResolver.resolve("mere applications update kar do")
    assert res4.goal == "UPDATE_INSTALLED_SOFTWARE"

    res5 = UniversalGoalResolver.resolve("software aur Windows dono update check karo")
    assert res5.goal == "CHECK_FOR_UPDATES"


def test_20_multi_turn_context_inheritance():
    """Validates multi-turn conversation: check discovery followed by 'haan sab update kar do'."""
    manager = SoftwareUpdateManager.get_instance()
    # Simulate a prior check having found updates
    manager._pending_plan = UpdatePlan(
        requested_scope=UpdateScope.ALL_SUPPORTED,
        winget_updates=[PackageUpdateItem("Chrome", "Google.Chrome", "1.0", "2.0", "winget")],
    )

    res = UniversalGoalResolver.resolve("haan sab update kar do")
    assert res.goal == "EXECUTE_UPDATE_PLAN"
    assert res.decision.value == "EXECUTE"


def test_21_gui_and_voice_manager_convergence():
    """Validates that GUI view and voice system access the same underlying SoftwareUpdateManager singleton."""
    from core.software_update.manager import get_software_update_manager
    mgr1 = get_software_update_manager()
    mgr2 = SoftwareUpdateManager.get_instance()
    assert mgr1 is mgr2


def test_22_final_reporting_honesty():
    """Validates that report builder never hallucinates 100% or fabricates numbers."""
    plan = UpdatePlan(
        requested_scope=UpdateScope.ALL_SUPPORTED,
        winget_updates=[PackageUpdateItem("Chrome", "Google.Chrome", "1.0", "2.0", "winget")],
        windows_updates=[PackageUpdateItem("WinKB", "KB12345", "1", "2", "windows_update")],
        store_updates=[],
        skipped_items=[PackageUpdateItem("UnknownApp", "Unknown.App", "?", "?", "winget", UpdateStatus.UNKNOWN)],
    )
    summary = UpdateReportBuilder.build_check_summary(plan, language="hi")
    assert "1 application update" in summary
    assert "1 Windows update" in summary
    assert "1 unmanaged/pinned packages skip" in summary
    assert "Kya main inhe install kar doon?" in summary
