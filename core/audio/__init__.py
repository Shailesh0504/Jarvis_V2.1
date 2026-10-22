# core/audio/__init__.py
"""
core.audio package.
Re-exports AudioDeviceManager and core data structures.
"""

from .device_manager import (
    AudioDeviceManager,
    AudioDeviceInfo,
    PhysicalAudioHeadset,
    DeviceRole,
    AudioConnectionState,
    extract_base_headset_identity,
)

__all__ = [
    "AudioDeviceManager",
    "AudioDeviceInfo",
    "PhysicalAudioHeadset",
    "DeviceRole",
    "AudioConnectionState",
    "extract_base_headset_identity",
]
