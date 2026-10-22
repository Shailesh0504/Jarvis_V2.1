# plugins/audio/commands.py
"""Command actions supported by Audio plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="set_volume",
        description="Sets system audio volume level (0-100)",
        keywords=["set volume", "volume", "volume karo", "volume 50", "sound level"],
        parameters=[
            PluginParameter(name="level", type="int", description="Volume percentage 0 to 100", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="volume_up",
        description="Increases system audio volume by a step",
        keywords=["volume up", "increase volume", "awaz badhao", "volume badhao", "volume tez karo"],
        parameters=[
            PluginParameter(name="step", type="int", description="Percentage to increase", required=False, default=10)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="volume_down",
        description="Decreases system audio volume by a step",
        keywords=["volume down", "decrease volume", "awaz kam karo", "volume kam karo", "volume dheere karo"],
        parameters=[
            PluginParameter(name="step", type="int", description="Percentage to decrease", required=False, default=10)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="mute",
        description="Mutes system audio output",
        keywords=["mute", "mute karo", "sound mute", "mute audio", "chup ho jao"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="unmute",
        description="Unmutes system audio output",
        keywords=["unmute", "unmute karo", "sound unmute", "unmute audio"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),

    # 10 New Actions
    PluginAction(
        name="get_volume",
        description="Returns current system master volume percentage and mute state",
        keywords=["get volume", "current volume", "volume kitna hai", "check volume"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="toggle_mute",
        description="Toggles the system audio mute state on or off",
        keywords=["toggle mute", "mute unmute toggle", "awaz band chalu"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="list_audio_devices",
        description="Lists all available audio playback and recording devices on the system",
        keywords=["audio devices", "playback devices", "speakers list", "sound devices"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="set_app_volume",
        description="Sets the volume percentage for a specific running application",
        keywords=["set app volume", "spotify volume", "chrome volume badhao", "app sound level"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Application name (e.g. spotify, chrome, vlc)", required=True),
            PluginParameter(name="level", type="integer", description="Volume percentage (0-100)", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_app_volume",
        description="Reads the volume level and mute state for an individual application",
        keywords=["get app volume", "check app sound", "app audio level"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Application name", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="list_app_audio_sessions",
        description="Lists all active application audio sessions currently registered with Windows CoreAudio",
        keywords=["audio sessions", "apps playing sound", "konse apps sound play kar rahe hain"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="fade_volume",
        description="Gradually ramps volume from current level to target level over specified duration",
        keywords=["fade volume", "gradual volume", "volume ramp karo", "smooth volume"],
        parameters=[
            PluginParameter(name="target_level", type="integer", description="Target volume percentage (0-100)", required=True),
            PluginParameter(name="duration_seconds", type="number", description="Duration in seconds", required=False, default=1.0)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="play_frequency_tone",
        description="Generates and plays an audible pure frequency tone (Hz) through the speakers",
        keywords=["play tone", "frequency beep", "sound frequency", "test tone"],
        parameters=[
            PluginParameter(name="frequency_hz", type="integer", description="Frequency in Hertz (37 - 32767)", required=False, default=440),
            PluginParameter(name="duration_ms", type="integer", description="Duration in milliseconds", required=False, default=500)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_default_audio_device",
        description="Retrieves the name and ID of the current default audio output endpoint",
        keywords=["default audio device", "current speakers", "default sound output"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="check_audio_engine_status",
        description="Verifies the operational status of the Windows Audio service (Audiosrv)",
        keywords=["audio service status", "is sound working", "audio engine health"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    )
]
