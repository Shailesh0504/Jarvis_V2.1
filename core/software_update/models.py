# core/software_update/models.py
"""
Data models and enumerations for the Jarvis Software Update Manager.
Enforces strict domain separation, truthful reporting, and granular package tracking.
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional


class UpdateStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UPDATED = "UPDATED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REQUIRES_ELEVATION = "REQUIRES_ELEVATION"
    REQUIRES_REBOOT = "REQUIRES_REBOOT"
    VERIFICATION_UNKNOWN = "VERIFICATION_UNKNOWN"


class UpdateScope(str, Enum):
    APPLICATIONS = "APPLICATIONS"
    OS = "OS"
    ALL_SUPPORTED = "ALL_SUPPORTED"
    STORE = "STORE"
    SPECIFIC_PACKAGE = "SPECIFIC_PACKAGE"


class ManagerState(str, Enum):
    IDLE = "IDLE"
    CHECKING = "CHECKING"
    UPDATING = "UPDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class PackageUpdateItem:
    """Represents an individual update item from any provider."""
    package_name: str
    package_id: str
    current_version: str
    target_version: str
    source: str  # "winget", "windows_update", "msstore", "unknown"
    status: UpdateStatus = UpdateStatus.AVAILABLE
    error_code: Optional[int] = None
    error_reason: Optional[str] = None
    reboot_required: bool = False
    requires_elevation: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_name": self.package_name,
            "package_id": self.package_id,
            "current_version": self.current_version,
            "target_version": self.target_version,
            "source": self.source,
            "status": self.status.value if isinstance(self.status, UpdateStatus) else str(self.status),
            "error_code": self.error_code,
            "error_reason": self.error_reason,
            "reboot_required": self.reboot_required,
            "requires_elevation": self.requires_elevation,
            "details": self.details,
        }


@dataclass
class UpdateChannelResult:
    """Summary of operations performed by an individual provider."""
    provider_name: str
    is_available: bool = True
    checked: int = 0
    available_updates: List[PackageUpdateItem] = field(default_factory=list)
    updated_items: List[PackageUpdateItem] = field(default_factory=list)
    failed_items: List[PackageUpdateItem] = field(default_factory=list)
    skipped_items: List[PackageUpdateItem] = field(default_factory=list)
    reboot_required: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "is_available": self.is_available,
            "checked": self.checked,
            "available_count": len(self.available_updates),
            "updated_count": len(self.updated_items),
            "failed_count": len(self.failed_items),
            "skipped_count": len(self.skipped_items),
            "reboot_required": self.reboot_required,
            "error": self.error,
        }


@dataclass
class UpdatePlan:
    """Structured plan summarizing discovered updates across all providers."""
    requested_scope: UpdateScope
    winget_updates: List[PackageUpdateItem] = field(default_factory=list)
    windows_updates: List[PackageUpdateItem] = field(default_factory=list)
    store_updates: List[PackageUpdateItem] = field(default_factory=list)
    unknown_items: List[PackageUpdateItem] = field(default_factory=list)
    skipped_items: List[PackageUpdateItem] = field(default_factory=list)
    blocked_items: List[PackageUpdateItem] = field(default_factory=list)
    reboot_required: bool = False
    confirmation_required: bool = True
    created_at: float = field(default_factory=time.time)

    @property
    def total_available(self) -> int:
        return len(self.winget_updates) + len(self.windows_updates) + len(self.store_updates)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requested_scope": self.requested_scope.value if isinstance(self.requested_scope, UpdateScope) else str(self.requested_scope),
            "total_available": self.total_available,
            "winget_count": len(self.winget_updates),
            "windows_count": len(self.windows_updates),
            "store_count": len(self.store_updates),
            "unknown_count": len(self.unknown_items),
            "skipped_count": len(self.skipped_items),
            "blocked_count": len(self.blocked_items),
            "reboot_required": self.reboot_required,
            "confirmation_required": self.confirmation_required,
            "created_at": self.created_at,
        }


@dataclass
class UpdateSessionLog:
    """Structured execution log for audit and telemetry."""
    session_id: str
    start_time: float
    end_time: Optional[float] = None
    scope: str = "ALL_SUPPORTED"
    channel_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    reboot_required: bool = False
    status: str = "COMPLETED"
    cancelled: bool = False
    summary_message: str = ""
