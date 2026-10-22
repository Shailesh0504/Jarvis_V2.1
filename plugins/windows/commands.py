# plugins/windows/commands.py
"""Command actions supported by Windows plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="open_path",
        description="Opens a local folder or UNC network share in File Explorer",
        keywords=["open path", "open network share", "start unc", "network folder kholo"],
        parameters=[
            PluginParameter(name="path", type="string", description="Local or UNC path to open", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="launch_app",
        description="Launches a Windows application executable or known program",
        keywords=["launch", "open app", "start program", "kholo", "chalao"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Name of app (notepad, calc, chrome, brave, etc.)", required=True),
            PluginParameter(name="path", type="string", description="Optional file path to open with app", required=False, default="")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="close_app",
        description="Closes or terminates a running application window or process",
        keywords=["close app", "band karo", "terminate process", "kill app", "close window"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Application or window name to close", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="maximize_window",
        description="Maximizes an application window or the active window",
        keywords=["maximize", "fullscreen", "full screen", "bada karo"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Application name (or 'current')", required=False, default="current")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="minimize_window",
        description="Minimizes an application window or the active window",
        keywords=["minimize", "chhota karo"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Application name (or 'current')", required=False, default="current")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="restore_window",
        description="Restores an application window to its normal unmaximized state",
        keywords=["restore window", "unmaximize"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Application name (or 'current')", required=False, default="current")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="focus_window",
        description="Brings an application window to the foreground and focuses it",
        keywords=["focus", "foreground", "bring to front", "samne lao"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Application name to bring to foreground", required=False, default=""),
            PluginParameter(name="hwnd", type="integer", description="Window handle (optional)", required=False, default=0)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="get_windows",
        description="Lists all visible top-level windows or windows matching an application",
        keywords=["get windows", "list windows", "all windows"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Application name filter", required=False, default=""),
            PluginParameter(name="include_hidden", type="boolean", description="Include hidden windows", required=False, default=False)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="find_window",
        description="Finds and deterministically selects the best window for an application",
        keywords=["find window", "select window"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Application name (brave, chrome, etc.)", required=True),
            PluginParameter(name="prefer_active", type="boolean", description="Prefer active/foreground window", required=False, default=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="move_window",
        description="Moves a window to specific desktop coordinates",
        keywords=["move window", "move"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Application name or 'current'", required=False, default=""),
            PluginParameter(name="hwnd", type="integer", description="Window handle", required=False, default=0),
            PluginParameter(name="x", type="integer", description="X coordinate", required=True),
            PluginParameter(name="y", type="integer", description="Y coordinate", required=True),
            PluginParameter(name="width", type="integer", description="Optional width", required=False, default=0),
            PluginParameter(name="height", type="integer", description="Optional height", required=False, default=0)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="resize_window",
        description="Resizes a window to specified width and height",
        keywords=["resize window", "resize"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Application name or 'current'", required=False, default=""),
            PluginParameter(name="hwnd", type="integer", description="Window handle", required=False, default=0),
            PluginParameter(name="width", type="integer", description="Width in pixels", required=True),
            PluginParameter(name="height", type="integer", description="Height in pixels", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="snap_left",
        description="Snaps a window to the left half of the screen and verifies position",
        keywords=["snap left", "left half", "left side"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Target application name or 'current'", required=False, default=""),
            PluginParameter(name="hwnd", type="integer", description="Window handle (optional)", required=False, default=0),
            PluginParameter(name="launch_if_needed", type="boolean", description="Whether to launch application if not running", required=False, default=False)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="snap_right",
        description="Snaps a window to the right half of the screen and verifies position",
        keywords=["snap right", "right half", "right side"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Target application name or 'current'", required=False, default=""),
            PluginParameter(name="hwnd", type="integer", description="Window handle (optional)", required=False, default=0),
            PluginParameter(name="launch_if_needed", type="boolean", description="Whether to launch application if not running", required=False, default=False)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="verify_window_position",
        description="Verifies the actual window rectangle/bounds against expected position",
        keywords=["verify window", "verify position"],
        parameters=[
            PluginParameter(name="hwnd", type="integer", description="Target window handle", required=True),
            PluginParameter(name="expected_position", type="string", description="Expected position (left, right, etc.)", required=False, default=""),
            PluginParameter(name="expected_rect", type="object", description="Expected rect dict", required=False, default=None),
            PluginParameter(name="tolerance", type="integer", description="Pixel tolerance", required=False, default=25)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="position_window",
        description="Positions and snaps a window to a layout area (left, right, top, bottom, top_left, top_right, bottom_left, bottom_right, center)",
        keywords=["position window", "left side", "right side", "top left", "rakho", "shift karo"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Target application name or 'current'", required=True),
            PluginParameter(name="position", type="string", description="Layout position (left, right, top, bottom, top_left, top_right, bottom_left, bottom_right, center)", required=True),
            PluginParameter(name="launch_if_needed", type="boolean", description="Whether to launch application if not running", required=False, default=False)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="layout_windows",
        description="Arranges multiple application windows according to a structured layout plan",
        keywords=["layout windows", "side by side", "tile windows", "multi window"],
        parameters=[
            PluginParameter(name="items", type="array", description="List of layout items with app_name, position, launch_if_needed", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="manage_window",
        description="Performs generic window operations on any target application",
        keywords=["window", "manage window", "window control"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Target application name or 'current'", required=True),
            PluginParameter(name="operation", type="string", description="Operation (maximize, minimize, restore, focus, close, move, resize, position)", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="kill_process",
        description="Terminates a running process by name or PID",
        keywords=["kill", "terminate process"],
        parameters=[
            PluginParameter(name="process_name", type="string", description="Process name (e.g. notepad.exe)", required=True)
        ],
        required_permission=PermissionLevel.ADMIN,
        required_capability=PluginCapability.PROCESS.value
    ),

    # 10 New Actions
    PluginAction(
        name="get_active_window_info",
        description="Retrieves metadata (title, HWND, process, PID, bounds) for the currently focused window",
        keywords=["active window", "focused window", "current window details", "active window info"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="set_window_transparency",
        description="Sets opacity percentage (0-100%) for an application window",
        keywords=["window transparency", "make window transparent", "opacity badlo window"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Target application name or 'current'", required=False, default="current"),
            PluginParameter(name="opacity_percent", type="integer", description="Opacity percentage (10-100)", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="set_window_always_on_top",
        description="Pins or unpins a window to be always on top of all other windows",
        keywords=["always on top", "pin window", "unpin window", "topmost window"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Target application name or 'current'", required=False, default="current"),
            PluginParameter(name="always_on_top", type="boolean", description="True to pin, False to unpin", required=False, default=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="hide_window",
        description="Hides an application window from the desktop and taskbar",
        keywords=["hide window", "window chupao", "invisible window"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Target application name", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="show_window",
        description="Un-hides and displays a previously hidden application window",
        keywords=["show window", "unhide window", "window wapas dikhao"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Target application name", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="cascade_windows",
        description="Cascades all visible top-level desktop windows in diagonal arrangement",
        keywords=["cascade windows", "cascade layout", "diagonal windows"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="tile_windows_horizontally",
        description="Arranges visible application windows tiled horizontally across the desktop",
        keywords=["tile horizontally", "tile windows horizontal", "stack windows"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="tile_windows_vertically",
        description="Arranges visible application windows side-by-side vertically across the desktop",
        keywords=["tile vertically", "side by side tile", "split vertical windows"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="minimize_all_windows",
        description="Minimizes all visible windows to show the desktop",
        keywords=["show desktop", "minimize all", "desktop dikhao", "sab windows minimize karo"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="restore_all_windows",
        description="Restores all previously minimized windows back to the desktop",
        keywords=["restore all windows", "unminimize all", "sab windows wapas lao"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    )
]
