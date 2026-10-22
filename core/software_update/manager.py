# core/software_update/manager.py
"""
Authoritative Software Update Manager for Jarvis V2.1.
Orchestrates multi-channel updates (WinGet, Windows Update, Microsoft Store, Unknown items),
enforces update concurrency locks, multi-turn plan inheritance, cancellation,
and truthful reporting.
"""

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import (
    ManagerState,
    PackageUpdateItem,
    UpdateChannelResult,
    UpdatePlan,
    UpdateScope,
    UpdateSessionLog,
    UpdateStatus,
)
from .report_builder import UpdateReportBuilder
from .store_provider import StoreUpdateProvider
from .windows_update_provider import WindowsUpdateProvider
from .winget_provider import WingetUpdateProvider

logger = logging.getLogger("jarvis.software_update.manager")


class SoftwareUpdateManager:
    """
    Central authoritative service for software and OS updates.
    Guarantees:
    - Thread-safe state machine preventing duplicate parallel executions.
    - Caches discovery plans for fluid multi-turn confirmation dialogues.
    - Preserves provider isolation across WinGet, Windows Update, and Store.
    - Supports safe cancellation tokens.
    """

    _instance: Optional["SoftwareUpdateManager"] = None
    _singleton_lock = threading.Lock()

    def __init__(
        self,
        winget_provider: Optional[WingetUpdateProvider] = None,
        windows_provider: Optional[WindowsUpdateProvider] = None,
        store_provider: Optional[StoreUpdateProvider] = None,
        history_file: str = "data/software_updates_history.json",
    ):
        self.winget = winget_provider or WingetUpdateProvider()
        self.windows = windows_provider or WindowsUpdateProvider()
        self.store = store_provider or StoreUpdateProvider()
        self.history_file = history_file

        self._state = ManagerState.IDLE
        self._lock = threading.RLock()
        self._cancel_requested = False
        self._pending_plan: Optional[UpdatePlan] = None
        self._active_session: Optional[UpdateSessionLog] = None
        self._history: List[Dict[str, Any]] = []

        self._load_history()

    @classmethod
    def get_instance(cls) -> "SoftwareUpdateManager":
        """Singleton accessor ensuring single authoritative owner for updates."""
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @property
    def state(self) -> ManagerState:
        return self._state

    @property
    def is_busy(self) -> bool:
        return self._state in (ManagerState.CHECKING, ManagerState.UPDATING)

    @property
    def pending_plan(self) -> Optional[UpdatePlan]:
        return self._pending_plan

    def check_updates(
        self,
        scope: UpdateScope = UpdateScope.ALL_SUPPORTED,
        include_unknown: bool = False,
        include_pinned: bool = False,
        language: str = "hi",
    ) -> Tuple[UpdatePlan, str]:
        """
        Discovers available updates across requested channels without installing.
        Stores the resulting plan for multi-turn execution.
        """
        with self._lock:
            if self.is_busy:
                msg = (
                    "Update process abhi pehle se chal raha hai, Boss. Kripya thoda wait kijiye."
                    if language == "hi"
                    else "An update process is already currently running. Please wait."
                )
                return self._pending_plan or UpdatePlan(requested_scope=scope), msg

            self._state = ManagerState.CHECKING
            self._cancel_requested = False

        logger.info("Starting update discovery for scope=%s", scope.value)
        winget_res: Optional[UpdateChannelResult] = None
        windows_res: Optional[UpdateChannelResult] = None
        store_res: Optional[UpdateChannelResult] = None

        try:
            # 1. WinGet updates (Applications)
            if scope in (UpdateScope.ALL_SUPPORTED, UpdateScope.APPLICATIONS):
                if not self._cancel_requested:
                    winget_res = self.winget.check_updates(
                        include_unknown=include_unknown,
                        include_pinned=include_pinned,
                    )

            # 2. Windows Updates (OS)
            if scope in (UpdateScope.ALL_SUPPORTED, UpdateScope.OS):
                if not self._cancel_requested:
                    windows_res = self.windows.check_updates()

            # 3. Store Updates (UWP / Store)
            if scope in (UpdateScope.ALL_SUPPORTED, UpdateScope.STORE):
                if not self._cancel_requested:
                    store_res = self.store.check_updates()

            # Check reboot pending
            reboot_pending = (
                (windows_res.reboot_required if windows_res else False)
                or self.windows.is_reboot_pending()
            )

            plan = UpdatePlan(
                requested_scope=scope,
                winget_updates=winget_res.available_updates if winget_res else [],
                windows_updates=windows_res.available_updates if windows_res else [],
                store_updates=store_res.available_updates if store_res else [],
                unknown_items=[
                    it for it in (winget_res.skipped_items if winget_res else [])
                    if it.status == UpdateStatus.UNKNOWN
                ],
                skipped_items=[
                    it for it in (winget_res.skipped_items if winget_res else [])
                    if it.status != UpdateStatus.UNKNOWN
                ],
                reboot_required=reboot_pending,
                confirmation_required=True,
            )

            with self._lock:
                self._pending_plan = plan
                self._state = ManagerState.IDLE

            summary_msg = UpdateReportBuilder.build_check_summary(
                plan=plan,
                store_result=store_res,
                language=language,
            )
            return plan, summary_msg

        except Exception as e:
            logger.error("Error during update check: %s", e, exc_info=True)
            with self._lock:
                self._state = ManagerState.FAILED
            err_msg = (
                f"Updates check karne mein error aaya: {e}"
                if language == "hi"
                else f"Error checking for updates: {e}"
            )
            return UpdatePlan(requested_scope=scope), err_msg

    def execute_updates(
        self,
        plan: Optional[UpdatePlan] = None,
        allow_reboot: bool = False,
        language: str = "hi",
    ) -> Tuple[bool, str]:
        """
        Executes updates according to the provided or pending UpdatePlan.
        Enforces update concurrency locks and transparently reports results.
        """
        target_plan = plan or self._pending_plan

        with self._lock:
            if self._state == ManagerState.UPDATING:
                msg = (
                    "Updates installation already running hai, Boss. Duplicate update launch nahi hoga."
                    if language == "hi"
                    else "Update installation is already in progress. Duplicate request blocked."
                )
                return False, msg

            self._state = ManagerState.UPDATING
            self._cancel_requested = False

        session_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        session_log = UpdateSessionLog(
            session_id=session_id,
            start_time=start_time,
            scope=target_plan.requested_scope.value if target_plan else "ALL_SUPPORTED",
        )
        self._active_session = session_log

        winget_res: Optional[UpdateChannelResult] = None
        windows_res: Optional[UpdateChannelResult] = None
        store_res: Optional[UpdateChannelResult] = None

        try:
            # 1. Execute WinGet application updates
            should_run_winget = (
                target_plan is None
                or target_plan.requested_scope in (UpdateScope.ALL_SUPPORTED, UpdateScope.APPLICATIONS)
                or bool(target_plan.winget_updates)
            )
            if should_run_winget and not self._cancel_requested:
                pkg_ids = [it.package_id for it in target_plan.winget_updates] if target_plan and target_plan.winget_updates else None
                winget_res = self.winget.upgrade_all(
                    accept_agreements=True,
                    allow_reboot=allow_reboot,
                    package_ids=pkg_ids,
                )
                session_log.channel_results["winget"] = winget_res.to_dict()

            # 2. Execute Windows Update
            should_run_windows = (
                target_plan is None
                or target_plan.requested_scope in (UpdateScope.ALL_SUPPORTED, UpdateScope.OS)
                or bool(target_plan.windows_updates)
            )
            if should_run_windows and not self._cancel_requested:
                windows_res = self.windows.install_updates()
                session_log.channel_results["windows"] = windows_res.to_dict()

            # 3. Execute Store Updates
            should_run_store = (
                target_plan is None
                or target_plan.requested_scope in (UpdateScope.ALL_SUPPORTED, UpdateScope.STORE)
                or bool(target_plan.store_updates)
            )
            if should_run_store and not self._cancel_requested:
                store_res = self.store.upgrade_all()
                session_log.channel_results["store"] = store_res.to_dict()

            # Evaluate final reboot requirement
            reboot_required = (
                (winget_res.reboot_required if winget_res else False)
                or (windows_res.reboot_required if windows_res else False)
                or self.windows.is_reboot_pending()
            )
            session_log.reboot_required = reboot_required
            session_log.end_time = time.time()
            session_log.cancelled = self._cancel_requested
            session_log.status = "CANCELLED" if self._cancel_requested else "COMPLETED"

            report_msg = UpdateReportBuilder.build_execution_summary(
                winget_res=winget_res,
                windows_res=windows_res,
                store_res=store_res,
                reboot_required=reboot_required,
                language=language,
            )
            session_log.summary_message = report_msg

            # Save session history
            self._save_session(session_log)

            with self._lock:
                self._pending_plan = None
                self._state = ManagerState.COMPLETED

            return True, report_msg

        except Exception as e:
            logger.error("Error during update execution: %s", e, exc_info=True)
            with self._lock:
                self._state = ManagerState.FAILED
            session_log.end_time = time.time()
            session_log.status = "FAILED"
            session_log.summary_message = str(e)
            self._save_session(session_log)
            err_msg = (
                f"Updates install karne mein error aaya: {e}"
                if language == "hi"
                else f"Error installing updates: {e}"
            )
            return False, err_msg

    def cancel(self) -> bool:
        """Requests cooperative cancellation of ongoing update tasks."""
        with self._lock:
            if not self.is_busy:
                return False
            self._cancel_requested = True
            logger.info("Cancellation requested for SoftwareUpdateManager.")
            return True

    def get_status(self) -> Dict[str, Any]:
        """Returns current state and pending plan diagnostics."""
        with self._lock:
            return {
                "state": self._state.value,
                "is_busy": self.is_busy,
                "cancel_requested": self._cancel_requested,
                "has_pending_plan": self._pending_plan is not None,
                "pending_plan": self._pending_plan.to_dict() if self._pending_plan else None,
                "active_session": self._active_session.__dict__ if self._active_session else None,
                "reboot_pending": self.windows.is_reboot_pending(),
                "history_count": len(self._history),
            }

    def get_history(self) -> List[Dict[str, Any]]:
        """Returns recorded update session history."""
        return list(self._history)

    def _load_history(self) -> None:
        """Loads past update session history from disk if present."""
        if not os.path.isfile(self.history_file):
            return
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                self._history = json.load(f)
        except Exception as e:
            logger.debug("Could not load update history: %s", e)

    def _save_session(self, session: UpdateSessionLog) -> None:
        """Appends session log to history and persists to file."""
        record = {
            "session_id": session.session_id,
            "start_time": session.start_time,
            "end_time": session.end_time,
            "scope": session.scope,
            "status": session.status,
            "reboot_required": session.reboot_required,
            "summary": session.summary_message,
            "channels": session.channel_results,
        }
        self._history.insert(0, record)
        if len(self._history) > 50:
            self._history = self._history[:50]

        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.history_file)), exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self._history, f, indent=2)
        except Exception as e:
            logger.debug("Could not save update history file: %s", e)


def get_software_update_manager() -> SoftwareUpdateManager:
    """Helper function to access the authoritative SoftwareUpdateManager singleton."""
    return SoftwareUpdateManager.get_instance()
