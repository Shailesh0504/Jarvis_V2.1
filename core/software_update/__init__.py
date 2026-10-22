# core/software_update/__init__.py
"""Production Software Update Manager for Jarvis V2.1."""

from .models import (
    ManagerState,
    PackageUpdateItem,
    UpdateChannelResult,
    UpdatePlan,
    UpdateScope,
    UpdateStatus,
)
from .manager import SoftwareUpdateManager, get_software_update_manager
from .report_builder import UpdateReportBuilder
from .store_provider import StoreUpdateProvider
from .windows_update_provider import WindowsUpdateProvider
from .winget_provider import WingetUpdateProvider

__all__ = [
    "SoftwareUpdateManager",
    "get_software_update_manager",
    "WingetUpdateProvider",
    "WindowsUpdateProvider",
    "StoreUpdateProvider",
    "UpdateReportBuilder",
    "PackageUpdateItem",
    "UpdatePlan",
    "UpdateScope",
    "UpdateStatus",
    "ManagerState",
    "UpdateChannelResult",
]
