# plugins/sounds/commands.py
"""Command actions for Sounds Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Action
    PluginAction(
        name="play_sound",
        description="Plays a system or assistant sound effect",
        keywords=["play sound", "sound effect", "play chime", "play alert", "sound bajao", "awaz chalao"],
        parameters=[
            PluginParameter(name="sound_name", type="string", description="Name of the sound to play", required=False, default="jarvis")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),

    # 10 New Actions
    PluginAction(
        name="play_system_beep",
        description="Plays a standard Windows system sound beep (ok, asterisk, exclamation, hand, question)",
        keywords=["system beep", "beep sound", "windows beep", "chime beep", "beep bajao"],
        parameters=[
            PluginParameter(name="beep_type", type="string", description="Type of beep: ok, asterisk, exclamation, hand, question", required=False, default="ok")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="play_alarm",
        description="Plays an alarm audio sound in the background",
        keywords=["play alarm", "alarm bajao", "sound alarm", "start alarm"],
        parameters=[
            PluginParameter(name="duration_seconds", type="integer", description="Duration to play alarm before stopping", required=False, default=5)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="stop_all_sounds",
        description="Immediately stops all actively playing audio or alarm sound effects",
        keywords=["stop sound", "stop alarm", "mute sound", "sound band karo", "alarm band karo"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="list_available_sounds",
        description="Lists all built-in sound effect assets available in Jarvis",
        keywords=["list sounds", "available sounds", "sound effects list", "saari awazein dikhao"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="set_sound_volume",
        description="Sets playback volume level for sound effects (0 to 100 percent)",
        keywords=["set sound volume", "effects volume", "sound volume set karo"],
        parameters=[
            PluginParameter(name="volume_percent", type="integer", description="Volume percentage (0-100)", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="play_custom_audio_file",
        description="Plays a custom audio file (.mp3, .wav) from disk with file verification",
        keywords=["play custom audio", "play audio file", "custom sound", "audio file bajao"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Path to audio file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="generate_frequency_tone",
        description="Generates an audio tone at a specific frequency (Hz) and duration (ms)",
        keywords=["frequency tone", "generate tone", "play tone", "hz tone", "tone bajao"],
        parameters=[
            PluginParameter(name="frequency", type="integer", description="Frequency in Hz (37 to 32767)", required=False, default=1000),
            PluginParameter(name="duration_ms", type="integer", description="Duration in milliseconds", required=False, default=400)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_audio_duration",
        description="Calculates or inspects the duration in seconds and size of an audio asset",
        keywords=["audio duration", "sound duration", "audio file length", "audio length"],
        parameters=[
            PluginParameter(name="sound_name_or_path", type="string", description="Sound name or absolute path", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="verify_sound_file",
        description="Verifies that an audio asset exists, is non-empty, and has a recognized format",
        keywords=["verify sound", "check sound file", "validate sound", "sound check karo"],
        parameters=[
            PluginParameter(name="sound_name_or_path", type="string", description="Sound name or path to verify", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="play_recycle_bin_sound",
        description="Plays the dedicated trash / recycle bin empty sound effect",
        keywords=["recycle bin sound", "trash sound", "delete sound", "koodadan ki awaz"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    )
]
