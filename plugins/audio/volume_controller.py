# plugins/audio/volume_controller.py
"""
Windows Core Audio Master Volume Controller using pycaw.
Provides validated, clamped, and read-back verified hardware-level volume adjustment.
"""

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("jarvis.plugins.audio.volume")


def get_default_playback_device_and_volume() -> Tuple[Any, Any]:
    """
    Acquires the default Windows audio endpoint and its IAudioEndpointVolume interface safely.
    Handles COM initialization and both modern pycaw properties and legacy COM activation.
    Returns (device, endpoint_volume).
    """
    # NOTE: Caller is responsible for COM apartment init/uninit.
    # Do NOT call CoInitialize here — it is already managed by the caller.

    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from ctypes import cast, POINTER

    device = AudioUtilities.GetSpeakers()
    if not device:
        raise RuntimeError("No default Windows audio playback device found.")

    # Modern pycaw provides dev.EndpointVolume directly as POINTER(IAudioEndpointVolume)
    endpoint_vol = getattr(device, "EndpointVolume", None)
    if endpoint_vol is None:
        # Fallback for older pycaw versions or direct COM activation
        dev_obj = getattr(device, "_dev", device)
        if hasattr(dev_obj, "Activate"):
            interface = dev_obj.Activate(IAudioEndpointVolume._iid_, 7, None)
            endpoint_vol = cast(interface, POINTER(IAudioEndpointVolume))
        else:
            raise RuntimeError("Could not acquire IAudioEndpointVolume interface from audio device.")

    return device, endpoint_vol


def get_system_volume() -> Dict[str, Any]:
    """
    Reads the current master volume and mute state from the default playback device.
    Returns structured dict with device name, volume percent, scalar, and mute state.
    """
    import comtypes
    try:
        comtypes.CoInitialize()
    except Exception:
        pass

    try:
        device, endpoint_vol = get_default_playback_device_and_volume()
        device_name = getattr(device, "FriendlyName", str(device)) or "Default Playback Device"
        scalar = endpoint_vol.GetMasterVolumeLevelScalar()
        pct = int(round(scalar * 100))
        muted = bool(endpoint_vol.GetMute())
        return {
            "success": True,
            "device": device_name,
            "volume": pct,
            "scalar": scalar,
            "muted": muted,
            "error": None
        }
    except Exception as exc:
        return {
            "success": False,
            "device": "Unknown",
            "volume": 50,
            "scalar": 0.5,
            "muted": False,
            "error": str(exc)
        }
    finally:
        # Explicitly release COM objects before uninitializing apartment
        try:
            del endpoint_vol
        except Exception:
            pass
        try:
            del device
        except Exception:
            pass
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass


def set_system_volume(percent: Any, tolerance: int = 2) -> Dict[str, Any]:
    """
    Robust Windows master volume setter with validation, clamping, and read-back verification.

    Parameters:
        percent: Requested volume level (int, float, or string like '50', '80%', 'max', 'mute').
        tolerance: Allowed difference between requested and read-back volume percent (default 2%).

    Returns:
        Structured dict:
        {
            "success": bool,
            "requested": int,
            "actual": int,
            "level": int,
            "device": str,
            "old_volume": int,
            "error": Optional[str],
            "message": str
        }
    """
    # 1. Validate and clamp requested volume
    parsed: Optional[float] = None
    if isinstance(percent, (int, float)):
        parsed = float(percent)
    elif isinstance(percent, str):
        from plugins.audio.plugin import _parse_volume_level
        parsed = float(_parse_volume_level(percent))

    if parsed is None:
        err_msg = f"Invalid volume level provided: {percent}"
        logger.error(err_msg)
        return {
            "success": False,
            "requested": percent,
            "actual": None,
            "level": None,
            "device": None,
            "old_volume": None,
            "error": err_msg,
            "message": f"Boss, volume change nahi ho paaya: {err_msg}"
        }

    clamped = max(0, min(100, int(round(parsed))))
    target_scalar = clamped / 100.0

    import comtypes
    try:
        comtypes.CoInitialize()
    except Exception:
        pass

    device_name = "Unknown"
    old_volume = None

    try:
        device, endpoint_vol = get_default_playback_device_and_volume()
        device_name = getattr(device, "FriendlyName", str(device)) or "Default Playback Device"
        logger.debug(f"Detected output device: {device_name}")

        old_scalar = endpoint_vol.GetMasterVolumeLevelScalar()
        old_volume = int(round(old_scalar * 100))
        logger.debug(f"Old volume: {old_volume}% (scalar {old_scalar:.4f})")
        logger.debug(f"Requested volume: {clamped}% (target scalar {target_scalar:.4f})")

        # Set master volume via Windows Core Audio API
        api_result_status = "SUCCESS"
        try:
            endpoint_vol.SetMasterVolumeLevelScalar(target_scalar, None)
            if clamped > 0:
                # If unmuting is necessary when raising volume above zero
                try:
                    if endpoint_vol.GetMute() == 1:
                        endpoint_vol.SetMute(0, None)
                except Exception:
                    pass
            elif clamped == 0:
                try:
                    endpoint_vol.SetMute(1, None)
                except Exception:
                    pass
        except Exception as e:
            api_result_status = f"FAILED: {e}"
            logger.debug(f"API call result: {api_result_status}")
            raise

        logger.debug(f"API call result: {api_result_status}")

        # Immediately read back verified final volume
        final_scalar = endpoint_vol.GetMasterVolumeLevelScalar()
        final_volume = int(round(final_scalar * 100))
        logger.debug(f"Verified final volume: {final_volume}% (scalar {final_scalar:.4f})")

        # Verify within tolerance
        if abs(final_volume - clamped) <= tolerance:
            return {
                "success": True,
                "requested": clamped,
                "actual": final_volume,
                "level": final_volume,
                "device": device_name,
                "old_volume": old_volume,
                "error": None,
                "message": f"Volume {final_volume}% set kar diya hai, Boss."
            }
        else:
            err = f"Verification mismatch: requested {clamped}%, but verified volume is {final_volume}%."
            logger.error(err)
            return {
                "success": False,
                "requested": clamped,
                "actual": final_volume,
                "level": final_volume,
                "device": device_name,
                "old_volume": old_volume,
                "error": err,
                "message": f"Boss, volume change nahi ho paaya: {err}"
            }

    except Exception as exc:
        err_detail = str(exc)
        logger.exception(f"Windows volume control exception: {err_detail}")
        return {
            "success": False,
            "requested": clamped,
            "actual": None,
            "level": None,
            "device": device_name,
            "old_volume": old_volume,
            "error": err_detail,
            "message": f"Boss, volume change nahi ho paaya: {err_detail}"
        }
    finally:
        # Explicitly release COM objects before uninitializing apartment
        try:
            del endpoint_vol
        except Exception:
            pass
        try:
            del device
        except Exception:
            pass
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass
