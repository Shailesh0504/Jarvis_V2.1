# plugins/clipboard/commands.py
"""Command actions supported by Clipboard Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="get_clipboard_text",
        description="Reads the current text content from the Windows system clipboard",
        keywords=["get clipboard", "clipboard padho", "read clipboard", "clipboard text"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="set_clipboard_text",
        description="Copies specified text to the Windows system clipboard",
        keywords=["copy to clipboard", "clipboard mein copy karo", "set clipboard", "copy text"],
        parameters=[
            PluginParameter(name="text", type="string", description="Text to copy to clipboard", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="clear_clipboard",
        description="Clears the system clipboard contents",
        keywords=["clear clipboard", "clipboard khali karo", "empty clipboard"],
        parameters=[],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),

    # 10 New Actions
    PluginAction(
        name="append_to_clipboard",
        description="Appends new text to the current clipboard content separated by a delimiter",
        keywords=["append clipboard", "clipboard mein jodo", "add to clipboard"],
        parameters=[
            PluginParameter(name="text", type="string", description="Text to append", required=True),
            PluginParameter(name="delimiter", type="string", description="Separator (e.g. newline, space, comma)", required=False, default="\n")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_clipboard_metrics",
        description="Analyzes clipboard content: word count, lines, chars, and detected type (URL, email, code, text)",
        keywords=["clipboard stats", "clipboard analysis", "clipboard length"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_clipboard_history",
        description="Returns list of recent items copied to clipboard during session",
        keywords=["clipboard history", "purana clipboard", "copy history dikhao"],
        parameters=[
            PluginParameter(name="limit", type="integer", description="Maximum history items to return", required=False, default=20)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="save_clipboard_to_file",
        description="Writes current clipboard content directly to a file on disk",
        keywords=["save clipboard", "clipboard save karo", "clipboard to file", "dump clipboard"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Target file path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="load_file_to_clipboard",
        description="Reads a text or source file from disk and loads its entire contents into the clipboard",
        keywords=["copy file to clipboard", "file clipboard mein dalo", "load to clipboard"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="File path to read", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="transform_clipboard_text",
        description="Transforms current clipboard text casing or encoding (uppercase, lowercase, titlecase, strip, json_prettify, base64_encode, base64_decode)",
        keywords=["transform clipboard", "uppercase clipboard", "lowercase clipboard", "format clipboard"],
        parameters=[
            PluginParameter(name="transformation", type="string", description="uppercase, lowercase, titlecase, strip, json_prettify, base64_encode, base64_decode", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="search_clipboard_history",
        description="Searches through previously copied items for keywords",
        keywords=["search clipboard", "find in clipboard history", "copied text search"],
        parameters=[
            PluginParameter(name="query", type="string", description="Keyword to search in history", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="clear_clipboard_history",
        description="Clears all recorded clipboard history entries",
        keywords=["clear clipboard history", "clipboard history saaf karo"],
        parameters=[],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="restore_clipboard_from_history",
        description="Restores a previously copied item from history onto the active clipboard",
        keywords=["restore clipboard", "history se copy karo", "clipboard wapas lao"],
        parameters=[
            PluginParameter(name="history_index", type="integer", description="0-indexed position in history", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="inspect_clipboard_formats",
        description="Lists all data format types currently present on Windows clipboard (text, unicode, bitmap, files)",
        keywords=["clipboard formats", "types in clipboard", "clipboard raw types"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    )
]
