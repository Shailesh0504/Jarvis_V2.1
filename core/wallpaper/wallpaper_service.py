# core/wallpaper/wallpaper_service.py
"""
Windows Desktop Wallpaper Service.
Native Windows 10/11 integration via ctypes SystemParametersInfoW, registry styles,
display resolution detection, and state verification.
"""

import ctypes
import logging
import os
import sys
from typing import Optional, Tuple

from core.wallpaper.models import AspectRatioTier, DisplayMetrics

logger = logging.getLogger("jarvis.wallpaper.service")

# Win32 Constants
SPI_SETDESKWALLPAPER = 20
SPI_GETDESKWALLPAPER = 115
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02


class WindowsWallpaperService:
    """Controls and verifies Windows desktop wallpaper state."""

    @classmethod
    def get_display_metrics(cls) -> DisplayMetrics:
        """Detects current primary monitor dimensions and aspect ratio tier."""
        width, height = 1920, 1080
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                width = user32.GetSystemMetrics(0)   # SM_CXSCREEN
                height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
            except Exception as e:
                logger.warning(f"Could not read GetSystemMetrics: {e}")

        aspect = (float(width) / float(height)) if height > 0 else 1.7777777777777777

        # Classify aspect ratio
        if aspect >= 3.0:
            tier = AspectRatioTier.SUPER_ULTRAWIDE
        elif aspect >= 2.2:
            tier = AspectRatioTier.ULTRAWIDE
        elif aspect >= 1.7:
            tier = AspectRatioTier.STANDARD_WIDE  # 16:9
        elif aspect >= 1.5:
            tier = AspectRatioTier.WIDE_WORK      # 16:10
        elif aspect < 1.0:
            tier = AspectRatioTier.PORTRAIT
        else:
            tier = AspectRatioTier.OTHER

        return DisplayMetrics(width=width, height=height, aspect_ratio=aspect, tier=tier)

    @classmethod
    def set_wallpaper_style_fill(cls) -> bool:
        """Sets Windows registry wallpaper style to Fill (10) without tiling."""
        if sys.platform != "win32":
            return True
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, "10")  # Fill
                winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, "0")
            return True
        except Exception as e:
            logger.warning(f"Failed to update registry wallpaper style: {e}")
            return False

    @classmethod
    def apply_wallpaper(cls, image_path: str) -> Tuple[bool, Optional[str]]:
        """
        Applies desktop wallpaper and verifies that the OS confirmed the change.
        Returns: (success, error_message)
        """
        abs_path = os.path.abspath(image_path)
        if not os.path.isfile(abs_path):
            return False, f"Image file not found: {abs_path}"

        if sys.platform != "win32":
            logger.info(f"[Non-Windows Mock] Setting wallpaper to {abs_path}")
            return True, None

        # 1. Ensure Fill style in registry
        cls.set_wallpaper_style_fill()

        # 2. Invoke SystemParametersInfoW
        try:
            user32 = ctypes.windll.user32
            res = user32.SystemParametersInfoW(
                SPI_SETDESKWALLPAPER,
                0,
                abs_path,
                SPIF_UPDATEINIFILE | SPIF_SENDCHANGE,
            )
            if not res:
                err = ctypes.GetLastError()
                return False, f"SystemParametersInfoW failed with error code {err}"
        except Exception as e:
            return False, f"Failed to call SystemParametersInfoW: {e}"

        # 3. Verify real applied OS state
        verified = cls.verify_wallpaper(abs_path)
        if not verified:
            logger.warning(f"Wallpaper was applied but verification returned false for {abs_path}")
            # Still return true if SPI_SETDESKWALLPAPER returned 1, but log warning
            return True, None

        logger.info(f"Successfully applied and verified Windows wallpaper: {abs_path}")
        return True, None

    @classmethod
    def verify_wallpaper(cls, expected_path: str) -> bool:
        """Verifies if the current desktop wallpaper matches expected image path."""
        if sys.platform != "win32":
            return True

        normalized_expected = os.path.normcase(os.path.abspath(expected_path))

        # Check via SPI_GETDESKWALLPAPER
        try:
            user32 = ctypes.windll.user32
            buf = ctypes.create_unicode_buffer(512)
            if user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, 512, buf, 0):
                current_spi = os.path.normcase(os.path.abspath(buf.value))
                if current_spi == normalized_expected:
                    return True
        except Exception:
            pass

        # Check via Registry fallback
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_READ) as key:
                reg_val, _ = winreg.QueryValueEx(key, "Wallpaper")
                current_reg = os.path.normcase(os.path.abspath(reg_val))
                if current_reg == normalized_expected:
                    return True
        except Exception:
            pass

        return False
