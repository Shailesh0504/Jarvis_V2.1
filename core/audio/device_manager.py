# core/audio/device_manager.py
"""
Central architectural alias for AudioDeviceManager.
Re-exports authoritative implementation from voice.device_manager (SSOT - Rule 1.1).
"""

from voice.device_manager import (
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
