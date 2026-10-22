# plugins/screen/commands.py
"""Command actions supported by Screen plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="take_screenshot",
        description="Captures a desktop screenshot and saves snapshot image",
        keywords=["screenshot lo", "take screenshot", "capture screen", "screenshot", "screen photo"],
        parameters=[
            PluginParameter(name="filename", type="string", description="Optional filename", required=False, default="")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="start_recording",
        description="Starts desktop screen recording session",
        keywords=["screen record karo", "start recording", "record screen", "recording chalu karo"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="stop_recording",
        description="Stops active desktop screen recording session",
        keywords=["stop recording", "recording band karo", "stop screen record"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="inspect_screen",
        description="Inspects what applications and windows are open and visible on the user's screen",
        keywords=["screen par kya open hai", "screen par kya hai", "what is on screen", "screen status", "screen par kya chal raha hai"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),

    # 10 New Actions
    PluginAction(
        name="capture_active_window",
        description="Captures a screenshot cropped specifically to the currently focused window bounds",
        keywords=["window screenshot", "active window capture", "window ki photo lo"],
        parameters=[
            PluginParameter(name="save_path", type="string", description="Optional output file path", required=False, default="")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="capture_region_screenshot",
        description="Captures a specific rectangular coordinate region of the screen",
        keywords=["crop screenshot", "region capture", "specific area screenshot"],
        parameters=[
            PluginParameter(name="x", type="integer", description="Top-left X coordinate", required=True),
            PluginParameter(name="y", type="integer", description="Top-left Y coordinate", required=True),
            PluginParameter(name="width", type="integer", description="Rectangle width", required=True),
            PluginParameter(name="height", type="integer", description="Rectangle height", required=True),
            PluginParameter(name="save_path", type="string", description="Optional output path", required=False, default="")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_screen_resolution",
        description="Returns primary display width, height, and refresh rate",
        keywords=["screen resolution", "display size", "monitor resolution", "desktop dimensions"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="list_monitors",
        description="Enumerates all connected physical or virtual displays and their bounding rectangles",
        keywords=["list monitors", "multiple displays", "screens connected", "all monitors"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_screen_brightness",
        description="Queries current monitor brightness percentage",
        keywords=["get brightness", "screen brightness", "display brightness kitni hai"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="set_screen_brightness",
        description="Adjusts screen brightness to specified percentage (0-100)",
        keywords=["set brightness", "brightness badhao", "brightness kam karo", "screen bright karo"],
        parameters=[
            PluginParameter(name="level", type="integer", description="Brightness level (0-100)", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="brightness_up",
        description="Raises monitor brightness relative to current level",
        keywords=["brightness badhao", "screen bright karo", "ujala badhao"],
        parameters=[
            PluginParameter(name="step", type="integer", description="Step to raise (default 15)", required=False, default=15)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="brightness_down",
        description="Lowers monitor brightness relative to current level",
        keywords=["brightness kam karo", "screen dim karo", "ujala kam karo"],
        parameters=[
            PluginParameter(name="step", type="integer", description="Step to lower (default 15)", required=False, default=15)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="record_screen_timelapse",
        description="Captures a sequence of screenshots over time to create a timelapse record",
        keywords=["screen timelapse", "interval screenshot", "periodic screenshot"],
        parameters=[
            PluginParameter(name="count", type="integer", description="Number of frames", required=False, default=4),
            PluginParameter(name="interval_seconds", type="number", description="Delay between frames", required=False, default=0.5)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="list_saved_screenshots",
        description="Lists all saved screenshot snapshots stored on disk with file sizes",
        keywords=["list screenshots", "purane screenshots", "show screenshots"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="delete_screenshot",
        description="Removes a specific screenshot file from disk",
        keywords=["delete screenshot", "screenshot hatao", "remove screenshot"],
        parameters=[
            PluginParameter(name="filename", type="string", description="Filename or path to delete", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_pixel_color",
        description="Reads the RGB color value of the pixel at coordinate (X, Y)",
        keywords=["pixel color", "color at cursor", "check pixel rgb"],
        parameters=[
            PluginParameter(name="x", type="integer", description="Screen X coordinate", required=True),
            PluginParameter(name="y", type="integer", description="Screen Y coordinate", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    )
]
