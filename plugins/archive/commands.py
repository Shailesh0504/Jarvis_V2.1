# plugins/archive/commands.py
"""Command actions supported by Archive Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="create_zip",
        description="Creates a compressed .zip archive of a folder or file",
        keywords=["create zip", "zip file banao", "compress folder", "make zip"],
        parameters=[
            PluginParameter(name="source_path", type="string", description="Path of folder or file to compress", required=True),
            PluginParameter(name="output_zip", type="string", description="Destination .zip file path", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="extract_zip",
        description="Extracts a .zip archive into a target folder",
        keywords=["extract zip", "unzip karo", "uncompress file", "zip kholo"],
        parameters=[
            PluginParameter(name="zip_path", type="string", description="Path of .zip file to extract", required=True),
            PluginParameter(name="extract_to", type="string", description="Destination folder", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="list_archive_contents",
        description="Lists the files contained inside a zip or tar archive",
        keywords=["list zip", "zip contents dikhao", "archive files", "inside archive"],
        parameters=[
            PluginParameter(name="archive_path", type="string", description="Path to .zip or .tar.gz file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),

    # 10 New Actions
    PluginAction(
        name="create_tar_archive",
        description="Creates a compressed .tar.gz or .tar.bz2 archive of files or directories",
        keywords=["create tar", "tar gz banao", "make tar archive", "tar ball banao"],
        parameters=[
            PluginParameter(name="source_path", type="string", description="File or directory to compress", required=True),
            PluginParameter(name="output_path", type="string", description="Destination .tar.gz path", required=False, default=""),
            PluginParameter(name="compression", type="string", description="'gz' or 'bz2'", required=False, default="gz")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="extract_tar_archive",
        description="Safely extracts a .tar, .tar.gz, or .tar.bz2 archive with path sanitization",
        keywords=["extract tar", "untar karo", "tar gz extract karo"],
        parameters=[
            PluginParameter(name="archive_path", type="string", description="Path to .tar.gz file", required=True),
            PluginParameter(name="extract_to", type="string", description="Destination folder", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="extract_single_file_from_archive",
        description="Extracts a specific individual file from inside an archive without extracting everything",
        keywords=["extract single file", "zip se ek file nikalo", "extract one file"],
        parameters=[
            PluginParameter(name="archive_path", type="string", description="Path to archive", required=True),
            PluginParameter(name="member_name", type="string", description="File path inside archive", required=True),
            PluginParameter(name="destination_dir", type="string", description="Target destination folder", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="verify_archive_integrity",
        description="Verifies the internal CRC32 checksums and readability of an archive file",
        keywords=["verify archive", "test zip", "archive integrity", "corrupt zip check"],
        parameters=[
            PluginParameter(name="archive_path", type="string", description="Path to archive to test", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_archive_compression_ratio",
        description="Calculates uncompressed size, compressed size, and space savings percentage",
        keywords=["compression ratio", "archive size savings", "zip efficiency"],
        parameters=[
            PluginParameter(name="archive_path", type="string", description="Path to archive", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="add_file_to_archive",
        description="Appends a new file into an existing .zip archive without extracting",
        keywords=["add to zip", "zip mein file dalo", "append to archive"],
        parameters=[
            PluginParameter(name="archive_path", type="string", description="Existing .zip file", required=True),
            PluginParameter(name="file_to_add", type="string", description="New file path to add", required=True),
            PluginParameter(name="arcname", type="string", description="Optional internal path inside zip", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="delete_file_from_archive",
        description="Removes a specific file entry from inside a .zip archive",
        keywords=["delete from zip", "remove file from zip", "zip se file hatao"],
        parameters=[
            PluginParameter(name="archive_path", type="string", description="Target .zip file", required=True),
            PluginParameter(name="member_name", type="string", description="Internal file name to delete", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="search_files_in_archive",
        description="Searches for files matching a wildcard or pattern inside an archive",
        keywords=["search zip", "find file in zip", "archive file search"],
        parameters=[
            PluginParameter(name="archive_path", type="string", description="Path to archive", required=True),
            PluginParameter(name="pattern", type="string", description="Wildcard or keyword to match", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="convert_archive_format",
        description="Converts an archive between formats (.zip to .tar.gz or vice versa)",
        keywords=["convert zip to tar", "convert archive", "archive format badlo"],
        parameters=[
            PluginParameter(name="source_archive", type="string", description="Source archive path", required=True),
            PluginParameter(name="target_format", type="string", description="'zip' or 'tar.gz'", required=True),
            PluginParameter(name="output_path", type="string", description="Optional output archive path", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_archive_metadata",
        description="Retrieves total file count, directories, creation times, and encryption status",
        keywords=["archive metadata", "zip info", "archive details"],
        parameters=[
            PluginParameter(name="archive_path", type="string", description="Path to archive", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    )
]
