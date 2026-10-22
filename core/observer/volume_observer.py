# core/observer/volume_observer.py
"""
Lightweight System Audio Master Volume Observer.
Monitors Windows Core Audio hardware master volume levels and mute states
with thresholding and jitter filtering.
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger("jarvis.core.observer.volume")


class VolumeObserver:
    """
    Monitors master playback volume changes.
    Emits state changes only when volume alters significantly (>= 2%).
    """

    def __init__(self, change_threshold: int = 2):
        self.change_threshold = max(1, change_threshold)
        self._last_volume: Optional[int] = None
        self._last_muted: Optional[bool] = None

    def check_volume_change(self) -> Tuple[bool, Optional[int], Optional[int], Optional[bool]]:
        """
        Polls current master audio volume.

        Returns:
            Tuple of (changed: bool, old_volume: Optional[int], new_volume: Optional[int], muted: Optional[bool])
        """
        try:
            from plugins.audio.volume_controller import get_system_volume
            vol_data = get_system_volume()
            if not vol_data.get("success"):
                return False, None, None, None

            curr_vol = vol_data.get("volume", 50)
            curr_muted = vol_data.get("muted", False)

            # First poll initializes baseline without emitting a false trigger
            if self._last_volume is None:
                self._last_volume = curr_vol
                self._last_muted = curr_muted
                return False, curr_vol, curr_vol, curr_muted

            vol_diff = abs(curr_vol - self._last_volume)
            mute_changed = bool(curr_muted != self._last_muted)

            if vol_diff >= self.change_threshold or mute_changed:
                old_vol = self._last_volume
                self._last_volume = curr_vol
                self._last_muted = curr_muted
                return True, old_vol, curr_vol, curr_muted

            return False, self._last_volume, curr_vol, curr_muted

        except Exception as e:
            logger.debug("VolumeObserver poll failed: %s", e)
            return False, None, None, None

    def reset(self) -> None:
        """Resets baseline tracking."""
        self._last_volume = None
        self._last_muted = None
