# plugins/vlc/commands.py
"""Command actions supported by VLC plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="play_file",
        description="Plays an audio or video file via VLC media player",
        keywords=["play in vlc", "play video", "play song", "vlc chalao", "gaana bajao", "play movie"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to media file", required=False, default="")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="stop_playback",
        description="Stops active VLC media playback and closes player",
        keywords=["stop vlc", "stop video", "stop song", "vlc band karo", "vlc stop", "stop playback"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),

    # 10 New Actions
    PluginAction(
        name="is_vlc_running",
        description="Checks if VLC media player is currently running and returns process information",
        keywords=["is vlc running", "vlc status", "check vlc", "vlc chal raha hai"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="find_vlc_executable",
        description="Locates the installed VLC executable on the Windows file system",
        keywords=["find vlc", "vlc path", "where is vlc", "locate vlc"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="pause_resume_vlc",
        description="Toggles pause or resume on the active VLC media player",
        keywords=["pause vlc", "resume vlc", "vlc pause karo", "vlc roko", "vlc play"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="vlc_fullscreen_toggle",
        description="Toggles fullscreen mode on VLC media player",
        keywords=["vlc fullscreen", "fullscreen vlc", "vlc badi screen karo", "vlc maximize screen"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="vlc_volume_up",
        description="Increases playback volume in VLC media player",
        keywords=["vlc volume badhao", "vlc volume up", "vlc sound up", "vlc awaz badhao"],
        parameters=[
            PluginParameter(name="steps", type="integer", description="Number of volume steps to increase", required=False, default=1)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="vlc_volume_down",
        description="Decreases playback volume in VLC media player",
        keywords=["vlc volume kam karo", "vlc volume down", "vlc sound down", "vlc awaz kam karo"],
        parameters=[
            PluginParameter(name="steps", type="integer", description="Number of volume steps to decrease", required=False, default=1)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="vlc_mute_toggle",
        description="Mutes or unmutes playback audio in VLC media player",
        keywords=["vlc mute", "vlc unmute", "vlc chup karo", "vlc awaz band karo"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="vlc_seek_forward",
        description="Seeks forward 10 seconds in VLC media playback",
        keywords=["vlc aage karo", "vlc seek forward", "vlc forward", "vlc skip forward"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="vlc_seek_backward",
        description="Seeks backward 10 seconds in VLC media playback",
        keywords=["vlc peeche karo", "vlc seek backward", "vlc rewind", "vlc skip backward"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="vlc_next_track",
        description="Skips to the next track in VLC playlist",
        keywords=["vlc agla gaana", "vlc next", "vlc next track", "next video vlc"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    )
]
