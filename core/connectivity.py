# core/connectivity.py
"""Connectivity & Offline-First State Manager for Jarvis V2."""

import logging
import socket
import threading
import time
from typing import Callable, List, Optional

logger = logging.getLogger("jarvis.core.connectivity")


class ConnectivityManager:
    """Monitors internet connectivity and coordinates graceful offline degradation."""

    def __init__(self, check_hosts: Optional[List[str]] = None, timeout: float = 1.0):
        self.check_hosts = check_hosts or ["1.1.1.1", "8.8.8.8"]
        self.timeout = timeout
        self._forced_offline = False
        self._last_checked = 0.0
        self._cached_status = False
        self._listeners: List[Callable[[bool], None]] = []

    def set_forced_offline(self, offline: bool = True) -> None:
        """Testing & manual override hook to simulate 100% offline state."""
        self._forced_offline = offline
        self._cached_status = not offline
        logger.info(f"ConnectivityManager: Forced offline mode set to {offline}.")
        self._notify_listeners(self._cached_status)

    @property
    def is_online(self) -> bool:
        if self._forced_offline:
            return False

        now = time.time()
        # Cache connection status for 5 seconds to avoid network latency
        if (now - self._last_checked) < 5.0:
            return self._cached_status

        self._last_checked = now
        self._cached_status = self._check_socket_connection()
        return self._cached_status

    @property
    def is_offline(self) -> bool:
        return not self.is_online

    def _check_socket_connection(self) -> bool:
        """Fast non-blocking socket test to check if public IP is reachable."""
        for host in self.check_hosts:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                sock.connect((host, 53)) # DNS port
                sock.close()
                return True
            except (socket.timeout, OSError):
                continue
        return False

    def register_listener(self, callback: Callable[[bool], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def _notify_listeners(self, status: bool) -> None:
        for cb in self._listeners:
            try:
                cb(status)
            except Exception as e:
                logger.error(f"Error in connectivity listener: {e}")
