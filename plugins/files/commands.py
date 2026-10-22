# plugins/files/commands.py
"""Command actions supported by Files plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="list_dir",
        description="Lists files and subdirectories at a given path",
        keywords=["list files", "show directory", "files in folder", "folder check karo"],
        parameters=[
            PluginParameter(name="path", type="string", description="Directory path to inspect", required=False, default=".")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="read_file",
        description="Reads text content from a local file",
        keywords=["read file", "view file", "show content", "file padho"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="write_file",
        description="Writes content to a file",
        keywords=["write file", "save file", "create file", "file banao"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to file", required=True),
            PluginParameter(name="content", type="string", description="Text content to write", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="find_recent_files",
        description="Find recently created or modified files by extension and days",
        keywords=["recent files", "find files", "latest file", "search recent", "find recent file", "kal ki file"],
        parameters=[
            PluginParameter(name="extension", type="string", description="File extension like .xlsx, .csv, .pdf", required=False, default=""),
            PluginParameter(name="directory", type="string", description="Root search directory", required=False, default="."),
            PluginParameter(name="limit", type="int", description="Max number of files to return", required=False, default=5)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="organize_directory",
        description="Organizes files into categorized subfolders (Documents, Images, Audio, Video, Archives, Code)",
        keywords=["organize folder", "organize downloads", "clean folder", "sort files", "organize kar do"],
        parameters=[
            PluginParameter(name="directory", type="string", description="Target directory to organize", required=False, default="."),
            PluginParameter(name="dry_run", type="bool", description="If True, only simulates without moving files", required=False, default=False)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="find_duplicates",
        description="Scans a directory and detects duplicate files by content hash and size",
        keywords=["duplicate files", "find duplicates", "duplicate report", "duplicate files ka report"],
        parameters=[
            PluginParameter(name="directory", type="string", description="Directory to scan for duplicates", required=False, default=".")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_file_info",
        description="Inspects file metadata, size in KB, and last modified date",
        keywords=["file info", "file details", "file size", "file ki jankari"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    # Structured Desktop Task Orchestration Actions
    PluginAction(
        name="RESOLVE_PATH",
        description="Resolves a special directory name or relative path to an absolute path with verification",
        keywords=["resolve path", "find desktop path"],
        parameters=[
            PluginParameter(name="target", type="string", description="Path or special name to resolve", required=True),
            PluginParameter(name="base_dir", type="string", description="Optional base directory", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="LIST_DIRECTORY",
        description="Lists directory entries with filtering and verification",
        keywords=["list directory", "directory listing"],
        parameters=[
            PluginParameter(name="path", type="string", description="Directory path", required=True),
            PluginParameter(name="filter_type", type="string", description="Filter (all, files, directories)", required=False, default="all")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="COUNT_ITEMS",
        description="Counts folders and files in a directory with verified results",
        keywords=["count items", "kitne folder hain", "how many files"],
        parameters=[
            PluginParameter(name="path", type="string", description="Directory path", required=True),
            PluginParameter(name="filter_type", type="string", description="Filter (all, files, directories)", required=False, default="all")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="CREATE_FOLDER",
        description="Creates a new folder with on-disk verification",
        keywords=["create folder", "folder banao", "make directory"],
        parameters=[
            PluginParameter(name="parent", type="string", description="Parent directory", required=True),
            PluginParameter(name="name", type="string", description="Folder name", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="CREATE_FILE",
        description="Creates a new file with verified existence on disk",
        keywords=["create file", "file banao", "make file"],
        parameters=[
            PluginParameter(name="parent", type="string", description="Parent directory", required=True),
            PluginParameter(name="name", type="string", description="File name", required=False, default=""),
            PluginParameter(name="file_type", type="string", description="Extension/type", required=False, default="txt"),
            PluginParameter(name="initial_content", type="string", description="Initial content", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="WRITE_FILE",
        description="Writes content to a file with byte-level verification",
        keywords=["write file", "type in file", "file mein likho"],
        parameters=[
            PluginParameter(name="target", type="string", description="Target file path", required=True),
            PluginParameter(name="content", type="string", description="Content to write", required=True),
            PluginParameter(name="mode", type="string", description="Mode ('w' or 'a')", required=False, default="w")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="READ_FILE",
        description="Reads file content with size and content verification",
        keywords=["read file", "file padho"],
        parameters=[
            PluginParameter(name="target", type="string", description="Target file path", required=True),
            PluginParameter(name="max_chars", type="int", description="Maximum characters", required=False, default=10000)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="MOVE",
        description="Moves a file or directory with destination verification",
        keywords=["move file", "move folder"],
        parameters=[
            PluginParameter(name="source", type="string", description="Source path", required=True),
            PluginParameter(name="destination", type="string", description="Destination path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="COPY",
        description="Copies a file or directory with verified target",
        keywords=["copy file", "copy folder"],
        parameters=[
            PluginParameter(name="source", type="string", description="Source path", required=True),
            PluginParameter(name="destination", type="string", description="Destination path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="RENAME",
        description="Renames a file or folder with verification",
        keywords=["rename file", "rename folder"],
        parameters=[
            PluginParameter(name="source", type="string", description="Source path", required=True),
            PluginParameter(name="new_name", type="string", description="New name or path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="DELETE",
        description="Deletes a file or directory with confirmation and verified removal",
        keywords=["delete file", "delete folder", "hatao"],
        parameters=[
            PluginParameter(name="target", type="string", description="Target path to delete", required=True),
            PluginParameter(name="confirmed", type="bool", description="User confirmation flag", required=False, default=False)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="OPEN",
        description="Opens a file or directory in default OS application with verification",
        keywords=["open file", "open folder", "kholo"],
        parameters=[
            PluginParameter(name="target", type="string", description="Target path to open", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="VERIFY",
        description="Verifies an expectation (existence, contents, item count) against filesystem state",
        keywords=["verify filesystem", "check exists"],
        parameters=[
            PluginParameter(name="verify_type", type="string", description="Verification check type", required=True),
            PluginParameter(name="target", type="string", description="Target path", required=True),
            PluginParameter(name="expected", type="string", description="Expected value", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="OPEN_FOLDER",
        description="Opens a daily-use or named folder in Windows Explorer",
        keywords=["open folder", "folder kholo", "open startup folder", "open downloads"],
        parameters=[
            PluginParameter(name="target", type="string", description="Folder name or path to open", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="CLOSE_FOLDER",
        description="Safely closes Windows Explorer folder window(s) without killing explorer.exe",
        keywords=["close folder", "folder band karo", "close startup folder", "close all folders"],
        parameters=[
            PluginParameter(name="target", type="string", description="Folder name to close (or 'all')", required=False, default=""),
            PluginParameter(name="close_all", type="bool", description="If True, closes all open folder windows", required=False, default=False)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="calculate_hash",
        description="Calculates cryptographic checksum (MD5, SHA1, SHA256, SHA512) of a file",
        keywords=["file hash", "checksum", "sha256", "md5", "verify file hash"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to file", required=True),
            PluginParameter(name="algorithm", type="string", description="Hash algorithm (md5, sha1, sha256, sha512)", required=False, default="sha256")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_directory_size",
        description="Recursively calculates directory size, total item count, and file extension breakdown",
        keywords=["directory size", "folder size", "kitna space le raha hai", "disk usage folder"],
        parameters=[
            PluginParameter(name="path", type="string", description="Directory path", required=False, default=".")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="search_files_by_content",
        description="Searches for text or regex patterns inside files within a directory",
        keywords=["search inside files", "grep files", "content search", "file text search"],
        parameters=[
            PluginParameter(name="query", type="string", description="Text to search for", required=True),
            PluginParameter(name="directory", type="string", description="Search directory", required=False, default="."),
            PluginParameter(name="extension", type="string", description="Optional file extension filter", required=False, default=""),
            PluginParameter(name="case_sensitive", type="boolean", description="Case-sensitive matching", required=False, default=False)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="batch_rename",
        description="Renames multiple files in a directory using pattern replacement, prefixes, or suffixes",
        keywords=["batch rename", "bulk rename", "rename files", "saari files rename"],
        parameters=[
            PluginParameter(name="directory", type="string", description="Target directory", required=True),
            PluginParameter(name="prefix", type="string", description="Optional prefix to prepend", required=False, default=""),
            PluginParameter(name="suffix", type="string", description="Optional suffix to append", required=False, default=""),
            PluginParameter(name="replace_from", type="string", description="Substring to replace", required=False, default=""),
            PluginParameter(name="replace_to", type="string", description="Replacement string", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="find_large_files",
        description="Finds files in a directory exceeding a given size threshold (in MB)",
        keywords=["large files", "biggest files", "badi files dhoondo", "heavy files"],
        parameters=[
            PluginParameter(name="directory", type="string", description="Directory to scan", required=False, default="."),
            PluginParameter(name="min_size_mb", type="float", description="Minimum file size in MB", required=False, default=10.0),
            PluginParameter(name="limit", type="integer", description="Maximum results", required=False, default=10)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="compare_files",
        description="Compares two files line-by-line and reports difference count and similarity",
        keywords=["compare files", "diff files", "file difference", "do files compare karo"],
        parameters=[
            PluginParameter(name="path1", type="string", description="First file path", required=True),
            PluginParameter(name="path2", type="string", description="Second file path", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="touch_file",
        description="Creates an empty file if missing or updates its access and modified timestamps",
        keywords=["touch file", "update timestamp", "create empty file"],
        parameters=[
            PluginParameter(name="path", type="string", description="Target file path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="find_empty_folders",
        description="Finds all empty subdirectories in a folder and optionally deletes them",
        keywords=["empty folders", "khali folder", "find empty directories", "clean empty folders"],
        parameters=[
            PluginParameter(name="directory", type="string", description="Directory to scan", required=False, default="."),
            PluginParameter(name="delete", type="boolean", description="Delete empty folders if True", required=False, default=False)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="secure_delete",
        description="Securely shreds a file by overwriting it with random bytes before deleting",
        keywords=["secure delete", "shred file", "safe delete", "permanent delete"],
        parameters=[
            PluginParameter(name="path", type="string", description="File path to shred", required=True),
            PluginParameter(name="passes", type="integer", description="Number of overwrite passes", required=False, default=1)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_disk_free_space",
        description="Reports total, used, and free disk space on the specified drive or path",
        keywords=["disk space", "free space", "drive space", "hard disk capacity"],
        parameters=[
            PluginParameter(name="path", type="string", description="Drive or path to inspect", required=False, default=".")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    )
]
