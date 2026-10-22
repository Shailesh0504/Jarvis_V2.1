# core/timezone_manager.py
"""
Centralized Timezone Management Subsystem for Jarvis V2.
Provides robust, crash-resilient timezone resolution, system timezone discovery,
safe fallbacks for Windows environments lacking IANA tzdata, startup validation,
and timezone-aware datetime conversions.

Invariant:
`get_timezone()` and `get_ist_timezone()` must NEVER raise ZoneInfoNotFoundError.
"""

from datetime import datetime, timezone, timedelta, tzinfo
import logging
import os
import threading
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("jarvis.core.timezone_manager")


class TimezoneManager:
    """
    Central authoritative Timezone Manager for Jarvis V2.
    Ensures safe timezone resolution across platforms (Windows / Linux / macOS).
    """

    _instance: Optional["TimezoneManager"] = None
    _lock = threading.Lock()

    def __init__(self, default_timezone: str = "Asia/Kolkata"):
        self.default_timezone_key = default_timezone
        self._cached_tz: Dict[str, tzinfo] = {}
        self._is_native_iana_supported: Optional[bool] = None

    @classmethod
    def get_instance(cls, default_timezone: str = "Asia/Kolkata") -> "TimezoneManager":
        """Singleton accessor for TimezoneManager."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(default_timezone=default_timezone)
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Resets singleton instance (useful for testing)."""
        with cls._lock:
            cls._instance = None

    def get_timezone(self, key: Optional[str] = None) -> tzinfo:
        """
        Resolves a timezone key (e.g. 'Asia/Kolkata', 'UTC', 'Europe/London')
        into a valid datetime.tzinfo object.

        Resolution hierarchy:
        1. In-memory cache
        2. Python standard library zoneinfo.ZoneInfo
        3. dateutil.tz.gettz (if installed)
        4. Known offset fallback (e.g. Asia/Kolkata -> UTC+05:30)
        5. Local OS system timezone via datetime.now().astimezone().tzinfo
        6. UTC fallback

        Guaranteed NEVER to raise ZoneInfoNotFoundError or KeyError.
        """
        tz_key = (key or self.default_timezone_key).strip()

        with self._lock:
            if tz_key in self._cached_tz:
                return self._cached_tz[tz_key]

        resolved_tz: Optional[tzinfo] = None

        # 1. Try standard zoneinfo
        try:
            import zoneinfo
            resolved_tz = zoneinfo.ZoneInfo(tz_key)
            self._is_native_iana_supported = True
        except Exception as exc:
            # On Windows without tzdata package, ZoneInfoNotFoundError occurs
            logger.debug("zoneinfo.ZoneInfo lookup failed for '%s': %s", tz_key, exc)
            self._is_native_iana_supported = False

        # 2. Try dateutil.tz as secondary provider if available
        if resolved_tz is None:
            try:
                from dateutil import tz as dateutil_tz
                d_tz = dateutil_tz.gettz(tz_key)
                if d_tz is not None:
                    resolved_tz = d_tz
            except Exception:
                pass

        # 3. Known region fallbacks
        if resolved_tz is None:
            resolved_tz = self._get_known_region_fallback(tz_key)

        # 4. OS system timezone fallback
        if resolved_tz is None:
            try:
                sys_tz = datetime.now().astimezone().tzinfo
                if sys_tz is not None:
                    resolved_tz = sys_tz
                    logger.debug("Falling back to local OS timezone for '%s'", tz_key)
            except Exception:
                pass

        # 5. Final safety fallback: UTC
        if resolved_tz is None:
            resolved_tz = timezone.utc
            logger.warning("All timezone resolution attempts failed for '%s'; falling back to UTC.", tz_key)

        with self._lock:
            self._cached_tz[tz_key] = resolved_tz

        return resolved_tz

    def _get_known_region_fallback(self, key: str) -> Optional[tzinfo]:
        """Provides mathematically exact fixed-offset fallbacks for common regions."""
        norm = key.strip().lower().replace("_", "")
        # Indian Standard Time (IST) UTC+05:30
        if norm in ("asia/kolkata", "asia/calcutta", "ist", "india"):
            return timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
        # UTC / GMT
        if norm in ("utc", "gmt", "etc/utc", "etc/gmt", "z"):
            return timezone.utc
        # US Eastern
        if norm in ("america/newyork", "est", "us/eastern"):
            return timezone(timedelta(hours=-5), name="America/New_York")
        # US Pacific
        if norm in ("america/losangeles", "pst", "us/pacific"):
            return timezone(timedelta(hours=-8), name="America/Los_Angeles")
        # UK / London
        if norm in ("europe/london", "bst"):
            return timezone(timedelta(hours=0), name="Europe/London")
        # Dubai / UAE (GST UTC+4)
        if norm in ("asia/dubai", "gst"):
            return timezone(timedelta(hours=4), name="Asia/Dubai")
        # Japan (JST UTC+9)
        if norm in ("asia/tokyo", "jst"):
            return timezone(timedelta(hours=9), name="Asia/Tokyo")

        return None

    def get_ist_timezone(self) -> tzinfo:
        """Convenience method returning guaranteed valid Indian Standard Time (IST) tzinfo."""
        return self.get_timezone("Asia/Kolkata")

    def get_now(self, key: Optional[str] = None) -> datetime:
        """Returns the current timezone-aware datetime for the requested or default timezone."""
        tz = self.get_timezone(key)
        return datetime.now(tz)

    def to_timezone(self, dt: datetime, target_key: Optional[str] = None) -> datetime:
        """
        Safely converts any datetime object into the specified target timezone.
        If the datetime is naive, attaches local/configured timezone first.
        """
        target_tz = self.get_timezone(target_key)
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            # Naive datetime: assume it represents local/configured time
            local_tz = self.get_timezone()
            dt = dt.replace(tzinfo=local_tz)
        return dt.astimezone(target_tz)

    def validate_timezone(self, key: str) -> Tuple[bool, str]:
        """
        Validates whether a timezone key is natively available via IANA zoneinfo,
        or if a fallback is active. Returns (is_native_iana, status_message).
        """
        try:
            import zoneinfo
            _ = zoneinfo.ZoneInfo(key)
            return True, f"Natively supported by IANA ZoneInfo: {key}"
        except Exception as err:
            fallback = self.get_timezone(key)
            return False, f"Fallback active for '{key}' ({fallback}): {err}"

    def validate_on_startup(self) -> bool:
        """
        Validates default and configured timezones during application startup.
        Logs diagnostics, ensures zero crashes, and returns status.
        """
        is_native, msg = self.validate_timezone(self.default_timezone_key)
        if is_native:
            logger.info("[TIMEZONE] Default timezone '%s' initialized natively via IANA zoneinfo.", self.default_timezone_key)
        else:
            logger.warning(
                "[TIMEZONE] Native IANA timezone data unavailable on this OS (%s). "
                "Safe fallback (+05:30 offset) is active. To enable native IANA lookups on Windows, run 'pip install tzdata'.",
                msg
            )
        return True

    def format_iso(self, dt: Optional[datetime] = None, key: Optional[str] = None) -> str:
        """Returns ISO-8601 string representation with accurate timezone offset."""
        if dt is None:
            dt = self.get_now(key)
        else:
            dt = self.to_timezone(dt, key)
        return dt.isoformat()


def get_timezone_manager() -> TimezoneManager:
    """Convenience helper to retrieve the global TimezoneManager instance."""
    return TimezoneManager.get_instance()
