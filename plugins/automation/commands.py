# plugins/automation/commands.py
"""Command actions supported by Automation Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="click",
        description="Clicks a screen coordinate using generic mouse automation",
        keywords=["click", "mouse click", "click karo", "screen click"],
        parameters=[
            PluginParameter(name="x", type="integer", description="Screen X coordinate", required=True),
            PluginParameter(name="y", type="integer", description="Screen Y coordinate", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="paste_text",
        description="Pastes supplied text into the verified active application",
        keywords=["paste text", "text paste karo", "paste karo"],
        parameters=[
            PluginParameter(name="text", type="string", description="Text to paste", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="type_text",
        description="Simulates typing text via keyboard simulation",
        keywords=["type text", "text type karo", "likho screen pe"],
        parameters=[
            PluginParameter(name="text", type="string", description="Text to type", required=True),
            PluginParameter(name="interval", type="number", description="Delay between keystrokes in seconds", required=False, default=0.02)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="press_hotkey",
        description="Simulates pressing a hotkey shortcut (e.g. ctrl+c, alt+tab, win+d)",
        keywords=["press key", "hotkey press karo", "shortcut dabao"],
        parameters=[
            PluginParameter(name="hotkey", type="string", description="Shortcut combination (e.g. ctrl+s, win+d)", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="run_macro",
        description="Executes a predefined or registered multi-step automation workflow or macro",
        keywords=["run macro", "workflow execute karo", "automation chalao", "macro run karo"],
        parameters=[
            PluginParameter(name="macro_name", type="string", description="Name of the macro workflow", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),

    # 10 New Actions
    PluginAction(
        name="double_click",
        description="Performs a mouse double-click at specified coordinates",
        keywords=["double click", "double click karo", "do baar click"],
        parameters=[
            PluginParameter(name="x", type="integer", description="Screen X coordinate", required=False, default=-1),
            PluginParameter(name="y", type="integer", description="Screen Y coordinate", required=False, default=-1)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="right_click",
        description="Performs a contextual right-click at specified coordinates",
        keywords=["right click", "right click karo", "context menu kholo"],
        parameters=[
            PluginParameter(name="x", type="integer", description="Screen X coordinate", required=False, default=-1),
            PluginParameter(name="y", type="integer", description="Screen Y coordinate", required=False, default=-1)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="mouse_scroll",
        description="Scrolls the vertical mouse wheel up or down",
        keywords=["scroll screen", "scroll up", "scroll down", "mouse scroll karo"],
        parameters=[
            PluginParameter(name="clicks", type="integer", description="Number of scroll units (positive for up, negative for down)", required=True),
            PluginParameter(name="x", type="integer", description="Optional target X coordinate", required=False, default=-1),
            PluginParameter(name="y", type="integer", description="Optional target Y coordinate", required=False, default=-1)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="mouse_drag_and_drop",
        description="Drags the mouse from start coordinates to end coordinates",
        keywords=["drag and drop", "drag mouse", "drop karo", "mouse drag karo"],
        parameters=[
            PluginParameter(name="start_x", type="integer", description="Starting X coordinate", required=True),
            PluginParameter(name="start_y", type="integer", description="Starting Y coordinate", required=True),
            PluginParameter(name="end_x", type="integer", description="Ending X coordinate", required=True),
            PluginParameter(name="end_y", type="integer", description="Ending Y coordinate", required=True),
            PluginParameter(name="duration", type="number", description="Drag duration in seconds", required=False, default=0.5)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_cursor_position",
        description="Returns current screen cursor position (X, Y) and screen dimensions",
        keywords=["cursor position", "mouse position", "mouse kahan hai", "screen size"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="move_cursor",
        description="Smoothly moves the mouse cursor to target screen coordinates",
        keywords=["move mouse", "move cursor", "mouse hilao", "cursor le jao"],
        parameters=[
            PluginParameter(name="x", type="integer", description="Target X coordinate", required=True),
            PluginParameter(name="y", type="integer", description="Target Y coordinate", required=True),
            PluginParameter(name="duration", type="number", description="Movement duration in seconds", required=False, default=0.2)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="register_custom_macro",
        description="Registers a named sequence of automation steps into persistent macro registry",
        keywords=["save macro", "register macro", "macro banao", "custom workflow save"],
        parameters=[
            PluginParameter(name="macro_name", type="string", description="Unique macro name", required=True),
            PluginParameter(name="steps", type="array", description="List of step dictionaries", required=True),
            PluginParameter(name="description", type="string", description="Optional description", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="list_macros",
        description="Lists all saved automation macros and their step definitions",
        keywords=["list macros", "macros dikhao", "available macros", "macro list"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="delete_macro",
        description="Removes a macro definition from the macro registry",
        keywords=["delete macro", "remove macro", "macro hatao"],
        parameters=[
            PluginParameter(name="macro_name", type="string", description="Name of macro to delete", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="find_template_on_screen",
        description="Locates an image template on screen and returns its coordinates if visible",
        keywords=["find on screen", "locate image", "screen pe dhundo", "template match"],
        parameters=[
            PluginParameter(name="template_path", type="string", description="Path to reference image template", required=True),
            PluginParameter(name="confidence", type="number", description="Matching confidence threshold (0.5 - 1.0)", required=False, default=0.8)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="draw_bappa",
        description="Draws Lord Ganesha (Bappa) using animated Python turtle graphics",
        keywords=[
            "drawing bappa", "draw bappa", "bappa drawing", "bappa ki drawing",
            "bappa draw karo", "bappa drawing banao", "drawing bappa banao",
            "ganpati bappa drawing", "draw ganpati bappa", "draw ganesha", "ganesha drawing"
        ],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    )
]

