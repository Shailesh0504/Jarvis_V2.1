# plugins/files/operations.py
"""
Concrete filesystem and desktop operations with mandatory verification.
Moved from Core into the dedicated FileSystem plugin to maintain strict separation
between Core cross-capability orchestration and plugin capability execution.
"""

from dataclasses import dataclass, field
import logging
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.plugins.files.operations")


@dataclass
class ActionResult:
    """Structured result of a concrete filesystem/desktop action with verification."""
    success: bool
    action: str
    target: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "success": self.success,
            "action": self.action,
            "target": self.target,
            "error": self.error,
            "verified": self.verified,
            "data": dict(self.data),
        }
        d.update(self.data)
        return d


class FilesystemOperations:
    """Provides atomic, verified filesystem and desktop operations."""

    @staticmethod
    def _resolve_default_special_path(name: str) -> str:
        """Resolve standard OS user directories and daily-use folders."""
        home = os.path.expanduser("~")
        name_clean = name.strip().lower().replace("_", " ")

        # Strip action prefixes/suffixes like 'open', 'kholo', 'folder', etc.
        name_clean = re.sub(r"^(?:open|kholo|launch|close|band\s+karo|band\s+kar\s+do|show|view)\s+", "", name_clean).strip()
        name_clean = re.sub(r"\s+(?:kholo|open\s+karo|band\s+karo|close)$", "", name_clean).strip()

        # Desktop variations
        if name_clean in ("desktop", "desktop pe", "desktop par", "desktop per", "on desktop", "desktop folder"):
            onedrive_desktop = os.path.join(home, "OneDrive", "Desktop")
            std_desktop = os.path.join(home, "Desktop")
            if os.path.exists(onedrive_desktop) and not os.path.exists(std_desktop):
                return os.path.abspath(onedrive_desktop)
            return os.path.abspath(std_desktop)

        # Downloads
        if name_clean in ("downloads", "download", "downloads folder", "download folder"):
            return os.path.abspath(os.path.join(home, "Downloads"))

        # Documents
        if name_clean in ("documents", "document", "docs", "documents folder", "my documents"):
            onedrive_docs = os.path.join(home, "OneDrive", "Documents")
            std_docs = os.path.join(home, "Documents")
            if os.path.exists(onedrive_docs) and not os.path.exists(std_docs):
                return os.path.abspath(onedrive_docs)
            return os.path.abspath(std_docs)

        # Startup
        if name_clean in ("startup", "startup folder", "start up", "start up folder", "windows startup", "windows startup folder"):
            # This Windows known-folder target remains valid even when the
            # physical Startup directory has not been created yet.  Returning
            # an AppData path only when it exists caused the command to fall
            # back to a non-existent relative path on fresh user profiles.
            return "shell:startup"

        # Pictures / Photos
        if name_clean in ("pictures", "picture", "photos", "photo", "images", "pictures folder", "photos folder"):
            return os.path.abspath(os.path.join(home, "Pictures"))

        # Videos / Movies
        if name_clean in ("videos", "video", "movies", "movie", "videos folder", "movies folder"):
            return os.path.abspath(os.path.join(home, "Videos"))

        # Music / Songs
        if name_clean in ("music", "songs", "song", "audio", "music folder", "songs folder"):
            return os.path.abspath(os.path.join(home, "Music"))

        # Recycle Bin / Trash
        if name_clean in ("recycle bin", "recyclebin", "recycle_bin", "trash", "recycle bin folder", "recycle_bin folder", "trash folder", "dustbin", "bin"):
            return "shell:RecycleBinFolder"

        # Temp / Temporary files
        if name_clean in ("temp", "temp folder", "temporary", "temporary files", "temporary folder"):
            temp_dir = os.environ.get("TEMP") or os.path.join(home, "AppData", "Local", "Temp")
            return os.path.abspath(temp_dir)

        # AppData / Roaming
        if name_clean in ("appdata", "app data", "appdata folder", "roaming", "roaming folder"):
            appdata_dir = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
            return os.path.abspath(appdata_dir)

        # Local AppData
        if name_clean in ("localappdata", "local appdata", "local app data", "localappdata folder"):
            local_appdata = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
            return os.path.abspath(local_appdata)

        # C Drive
        if name_clean in ("c drive", "c drive folder", "c:", "c:\\", "local disk c", "drive c", "c disk", "c"):
            return "C:\\"

        # D Drive
        if name_clean in ("d drive", "d drive folder", "d:", "d:\\", "local disk d", "drive d", "d disk", "d"):
            return "D:\\"

        # E Drive
        if name_clean in ("e drive", "e drive folder", "e:", "e:\\", "local disk e", "drive e", "e disk", "e"):
            return "E:\\"

        # Home / Current
        if name_clean in ("home", "user home", "home directory", "home folder", "user folder", "user profile"):
            return os.path.abspath(home)
        if name_clean in ("current", "current directory", "here"):
            return os.path.abspath(os.getcwd())

        return ""

    @staticmethod
    def get_special_path(name: str) -> str:
        """Resolve special OS user directories with hook support for test environments."""
        try:
            from core.desktop_task.action_registry import FilesystemActionRegistry
            if FilesystemActionRegistry.get_special_path != FilesystemOperations.get_special_path:
                custom = FilesystemActionRegistry.get_special_path(name)
                if custom:
                    return custom
        except Exception:
            pass
        return FilesystemOperations._resolve_default_special_path(name)

    def resolve_path(self, target: str, base_dir: Optional[str] = None, must_exist: bool = True) -> ActionResult:
        """Resolve a target path from a base directory or special name."""
        try:
            target_clean = target.strip()
            if target_clean.lower().startswith("shell:"):
                return ActionResult(
                    success=True,
                    action="RESOLVE_PATH",
                    target=target_clean,
                    verified=True,
                    data={
                        "path": target_clean,
                        "exists": True,
                        "is_dir": True,
                        "is_file": False,
                        "name": target_clean.split(":", 1)[1],
                    }
                )
            special = self.get_special_path(target_clean)
            if special:
                if special.lower().startswith("shell:"):
                    return ActionResult(
                        success=True,
                        action="RESOLVE_PATH",
                        target=special,
                        verified=True,
                        data={
                            "path": special,
                            "exists": True,
                            "is_dir": True,
                            "is_file": False,
                            "name": special.split(":", 1)[1],
                        }
                    )
                exists = os.path.exists(special)
                return ActionResult(
                    success=True if not must_exist else exists,
                    action="RESOLVE_PATH",
                    target=special,
                    verified=exists,
                    data={
                        "path": special,
                        "exists": exists,
                        "is_dir": os.path.isdir(special) if exists else False,
                        "is_file": os.path.isfile(special) if exists else False,
                        "name": os.path.basename(special),
                    }
                )

            # Check if absolute path
            if os.path.isabs(target_clean):
                full_path = os.path.abspath(target_clean)
            else:
                # Resolve relative to base_dir if provided
                base = base_dir or self.get_special_path("desktop")
                full_path = os.path.abspath(os.path.join(base, target_clean))

            exists = os.path.exists(full_path)
            success = exists if must_exist else True
            return ActionResult(
                success=success,
                action="RESOLVE_PATH",
                target=full_path,
                verified=exists,
                error=None if (exists or not must_exist) else f"Path '{full_path}' does not exist on disk.",
                data={
                    "path": full_path,
                    "exists": exists,
                    "is_dir": os.path.isdir(full_path) if exists else False,
                    "is_file": os.path.isfile(full_path) if exists else False,
                    "name": os.path.basename(full_path),
                }
            )
        except Exception as e:
            logger.exception("Failed to resolve path: %s", target)
            return ActionResult(
                success=False,
                action="RESOLVE_PATH",
                target=target,
                error=f"Error resolving path '{target}': {e}",
                verified=False,
            )

    def list_directory(self, path: str, filter_type: str = "all") -> ActionResult:
        """List contents of a directory with filtering."""
        try:
            abs_path = os.path.abspath(path)
            if not os.path.exists(abs_path):
                return ActionResult(
                    success=False,
                    action="LIST_DIRECTORY",
                    target=abs_path,
                    error=f"Directory '{abs_path}' does not exist.",
                    verified=False,
                )
            if not os.path.isdir(abs_path):
                return ActionResult(
                    success=False,
                    action="LIST_DIRECTORY",
                    target=abs_path,
                    error=f"Path '{abs_path}' is not a directory.",
                    verified=False,
                )

            entries = []
            files = []
            folders = []

            for entry in os.listdir(abs_path):
                entry_path = os.path.join(abs_path, entry)
                is_dir = os.path.isdir(entry_path)
                if is_dir:
                    folders.append(entry)
                else:
                    files.append(entry)

                if filter_type == "directories" and is_dir:
                    entries.append(entry)
                elif filter_type == "files" and not is_dir:
                    entries.append(entry)
                elif filter_type == "all":
                    entries.append(entry)

            return ActionResult(
                success=True,
                action="LIST_DIRECTORY",
                target=abs_path,
                verified=True,
                data={
                    "path": abs_path,
                    "entries": entries,
                    "files": files,
                    "folders": folders,
                    "total_count": len(entries),
                    "file_count": len(files),
                    "folder_count": len(folders),
                    "filter_type": filter_type,
                }
            )
        except Exception as e:
            logger.exception("Failed to list directory: %s", path)
            return ActionResult(
                success=False,
                action="LIST_DIRECTORY",
                target=path,
                error=f"Error listing directory '{path}': {e}",
                verified=False,
            )

    def count_items(self, path: str, filter_type: str = "all") -> ActionResult:
        """Count items in a directory with verification."""
        list_res = self.list_directory(path, filter_type=filter_type)
        if not list_res.success:
            return ActionResult(
                success=False,
                action="COUNT_ITEMS",
                target=path,
                error=list_res.error,
                verified=False,
            )

        count = len(list_res.data.get("entries", []))
        return ActionResult(
            success=True,
            action="COUNT_ITEMS",
            target=list_res.target,
            verified=True,
            data={
                "path": list_res.target,
                "count": count,
                "filter_type": filter_type,
                "folder_count": list_res.data.get("folder_count", 0),
                "file_count": list_res.data.get("file_count", 0),
            }
        )

    def create_folder(self, parent: str, name: str) -> ActionResult:
        """Create a folder inside a parent directory with strict verification."""
        try:
            res_parent = self.resolve_path(parent)
            if not res_parent.success:
                return res_parent

            parent_path = res_parent.target
            if not os.path.exists(parent_path):
                os.makedirs(parent_path, exist_ok=True)

            target_folder = os.path.abspath(os.path.join(parent_path, name.strip()))
            already_existed = os.path.exists(target_folder)

            # Create the folder
            os.makedirs(target_folder, exist_ok=True)

            # Verification step: ensure folder actually exists on disk
            verified = os.path.exists(target_folder) and os.path.isdir(target_folder)

            if not verified:
                return ActionResult(
                    success=False,
                    action="CREATE_FOLDER",
                    target=target_folder,
                    error=f"Verification failed: directory '{target_folder}' was not created.",
                    verified=False,
                )

            return ActionResult(
                success=True,
                action="CREATE_FOLDER",
                target=target_folder,
                verified=True,
                data={
                    "path": target_folder,
                    "name": os.path.basename(target_folder),
                    "parent": parent_path,
                    "is_dir": True,
                    "already_existed": already_existed,
                }
            )
        except Exception as e:
            logger.exception("Failed to create folder: %s in %s", name, parent)
            return ActionResult(
                success=False,
                action="CREATE_FOLDER",
                target=os.path.join(parent, name),
                error=f"Error creating folder '{name}': {e}",
                verified=False,
            )

    def create_file(
        self,
        parent: str,
        name: Optional[str] = None,
        file_type: str = "txt",
        initial_content: str = ""
    ) -> ActionResult:
        """Create an empty or initialized file with verification."""
        try:
            res_parent = self.resolve_path(parent)
            if not res_parent.success:
                return res_parent

            parent_path = res_parent.target
            if not os.path.exists(parent_path):
                os.makedirs(parent_path, exist_ok=True)

            # Resolve filename
            if not name:
                # Default timestamped or untitled name
                ext = file_type.lstrip(".")
                name = f"new_file.{ext}"

            # Ensure extension
            ext = file_type.lstrip(".")
            if not name.lower().endswith(f".{ext}") and "." not in name:
                name = f"{name}.{ext}"

            target_file = os.path.abspath(os.path.join(parent_path, name.strip()))

            # Avoid collision by default if not specified
            base_stem, base_ext = os.path.splitext(target_file)
            counter = 1
            final_path = target_file
            while os.path.exists(final_path) and counter < 100:
                final_path = f"{base_stem}_{counter}{base_ext}"
                counter += 1

            # Write content
            with open(final_path, "w", encoding="utf-8") as f:
                if initial_content:
                    f.write(initial_content)

            # Verification step: ensure file exists and is readable
            verified = os.path.exists(final_path) and os.path.isfile(final_path)
            if not verified:
                return ActionResult(
                    success=False,
                    action="CREATE_FILE",
                    target=final_path,
                    error=f"Verification failed: file '{final_path}' was not found on disk.",
                    verified=False,
                )

            return ActionResult(
                success=True,
                action="CREATE_FILE",
                target=final_path,
                verified=True,
                data={
                    "path": final_path,
                    "name": os.path.basename(final_path),
                    "parent": parent_path,
                    "size": os.path.getsize(final_path),
                    "is_file": True,
                }
            )
        except Exception as e:
            logger.exception("Failed to create file in %s", parent)
            return ActionResult(
                success=False,
                action="CREATE_FILE",
                target=parent,
                error=f"Error creating file: {e}",
                verified=False,
            )

    def write_file(self, target: str, content: str, mode: str = "w") -> ActionResult:
        """Write content to an existing or new file with byte-level verification."""
        try:
            res_target = self.resolve_path(target, must_exist=False)
            if not res_target.success:
                return res_target

            target_file = res_target.target

            # Ensure parent folder exists
            parent_dir = os.path.dirname(target_file)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            write_mode = "a" if mode in ("a", "append") else "w"
            with open(target_file, write_mode, encoding="utf-8") as f:
                f.write(content)

            # Verification: read back content or check size > 0
            verified = False
            actual_content = ""
            if os.path.exists(target_file) and os.path.isfile(target_file):
                with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                    actual_content = f.read()
                if content in actual_content:
                    verified = True

            if not verified:
                return ActionResult(
                    success=False,
                    action="WRITE_FILE",
                    target=target_file,
                    error=f"Verification failed: written content was not verified in '{target_file}'.",
                    verified=False,
                )

            return ActionResult(
                success=True,
                action="WRITE_FILE",
                target=target_file,
                verified=True,
                data={
                    "path": target_file,
                    "content": content,
                    "written_length": len(content),
                    "total_size": len(actual_content),
                    "content_preview": actual_content[:100],
                }
            )
        except Exception as e:
            logger.exception("Failed to write to file: %s", target)
            return ActionResult(
                success=False,
                action="WRITE_FILE",
                target=target,
                error=f"Error writing to file '{target}': {e}",
                verified=False,
            )

    def read_file(self, target: str, max_chars: int = 10000) -> ActionResult:
        """Read content from a file with verification."""
        try:
            res_target = self.resolve_path(target)
            if not res_target.success:
                return res_target

            target_file = res_target.target
            if not os.path.exists(target_file) or not os.path.isfile(target_file):
                return ActionResult(
                    success=False,
                    action="READ_FILE",
                    target=target_file,
                    error=f"File '{target_file}' not found.",
                    verified=False,
                )

            with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_chars)

            return ActionResult(
                success=True,
                action="READ_FILE",
                target=target_file,
                verified=True,
                data={
                    "path": target_file,
                    "content": content,
                    "length": len(content),
                }
            )
        except Exception as e:
            logger.exception("Failed to read file: %s", target)
            return ActionResult(
                success=False,
                action="READ_FILE",
                target=target,
                error=f"Error reading file '{target}': {e}",
                verified=False,
            )

    def move(self, source: str, destination: str) -> ActionResult:
        """Move a file or folder with source and destination verification."""
        try:
            res_src = self.resolve_path(source)
            if not res_src.success:
                return res_src
            src_path = res_src.target

            if not os.path.exists(src_path):
                return ActionResult(
                    success=False,
                    action="MOVE",
                    target=src_path,
                    error=f"Source '{src_path}' does not exist.",
                    verified=False,
                )

            res_dst = self.resolve_path(destination)
            dst_path = res_dst.target

            # Execute move
            final_dst = shutil.move(src_path, dst_path)

            # Verification: destination exists, source no longer exists
            verified = os.path.exists(final_dst) and not os.path.exists(src_path)
            if not verified:
                return ActionResult(
                    success=False,
                    action="MOVE",
                    target=final_dst,
                    error=f"Verification failed: move operation could not be confirmed.",
                    verified=False,
                )

            return ActionResult(
                success=True,
                action="MOVE",
                target=final_dst,
                verified=True,
                data={"source": src_path, "destination": final_dst}
            )
        except Exception as e:
            logger.exception("Failed to move %s to %s", source, destination)
            return ActionResult(
                success=False,
                action="MOVE",
                target=source,
                error=f"Error moving: {e}",
                verified=False,
            )

    def copy(self, source: str, destination: str) -> ActionResult:
        """Copy a file or directory with verification."""
        try:
            res_src = self.resolve_path(source)
            if not res_src.success:
                return res_src
            src_path = res_src.target

            if not os.path.exists(src_path):
                return ActionResult(
                    success=False,
                    action="COPY",
                    target=src_path,
                    error=f"Source '{src_path}' does not exist.",
                    verified=False,
                )

            res_dst = self.resolve_path(destination)
            dst_path = res_dst.target

            if os.path.isdir(src_path):
                final_dst = shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            else:
                if os.path.isdir(dst_path):
                    final_dst = shutil.copy2(src_path, dst_path)
                else:
                    final_dst = shutil.copy2(src_path, dst_path)

            verified = os.path.exists(final_dst)
            if not verified:
                return ActionResult(
                    success=False,
                    action="COPY",
                    target=final_dst,
                    error=f"Verification failed: copy destination '{final_dst}' was not found.",
                    verified=False,
                )

            return ActionResult(
                success=True,
                action="COPY",
                target=final_dst,
                verified=True,
                data={"source": src_path, "destination": final_dst}
            )
        except Exception as e:
            logger.exception("Failed to copy %s to %s", source, destination)
            return ActionResult(
                success=False,
                action="COPY",
                target=source,
                error=f"Error copying: {e}",
                verified=False,
            )

    def rename(self, source: str, new_name_or_path: str) -> ActionResult:
        """Rename a file or folder with verification."""
        try:
            res_src = self.resolve_path(source)
            if not res_src.success:
                return res_src
            src_path = res_src.target

            if not os.path.exists(src_path):
                return ActionResult(
                    success=False,
                    action="RENAME",
                    target=src_path,
                    error=f"Target '{src_path}' does not exist.",
                    verified=False,
                )

            # Determine destination path
            parent = os.path.dirname(src_path)
            clean_new = new_name_or_path.strip()
            if os.path.isabs(clean_new):
                dst_path = clean_new
            else:
                dst_path = os.path.join(parent, clean_new)

            os.rename(src_path, dst_path)

            verified = os.path.exists(dst_path) and not os.path.exists(src_path)
            if not verified:
                return ActionResult(
                    success=False,
                    action="RENAME",
                    target=dst_path,
                    error="Verification failed: rename could not be verified on disk.",
                    verified=False,
                )

            return ActionResult(
                success=True,
                action="RENAME",
                target=dst_path,
                verified=True,
                data={"old_path": src_path, "new_path": dst_path, "name": os.path.basename(dst_path)}
            )
        except Exception as e:
            logger.exception("Failed to rename %s to %s", source, new_name_or_path)
            return ActionResult(
                success=False,
                action="RENAME",
                target=source,
                error=f"Error renaming: {e}",
                verified=False,
            )

    def delete(self, target: str, confirmed: bool = False) -> ActionResult:
        """Safely delete a file or directory with verification."""
        try:
            res_target = self.resolve_path(target)
            if not res_target.success:
                return res_target

            target_path = res_target.target
            if not os.path.exists(target_path):
                return ActionResult(
                    success=False,
                    action="DELETE",
                    target=target_path,
                    error=f"Path '{target_path}' does not exist.",
                    verified=False,
                )

            if not confirmed:
                return ActionResult(
                    success=False,
                    action="DELETE",
                    target=target_path,
                    error="Safety check: explicit confirmation required before deleting.",
                    verified=False,
                    data={"requires_confirmation": True}
                )

            is_dir = os.path.isdir(target_path)
            if is_dir:
                shutil.rmtree(target_path)
            else:
                os.remove(target_path)

            # Verification: item must no longer exist
            verified = not os.path.exists(target_path)
            if not verified:
                return ActionResult(
                    success=False,
                    action="DELETE",
                    target=target_path,
                    error=f"Verification failed: '{target_path}' was not deleted.",
                    verified=False,
                )

            return ActionResult(
                success=True,
                action="DELETE",
                target=target_path,
                verified=True,
                data={"deleted_path": target_path, "is_dir": is_dir}
            )
        except Exception as e:
            logger.exception("Failed to delete %s", target)
            return ActionResult(
                success=False,
                action="DELETE",
                target=target,
                error=f"Error deleting '{target}': {e}",
                verified=False,
            )

    def open(self, target: str) -> ActionResult:
        """Open a file or directory in default OS handler."""
        try:
            res_target = self.resolve_path(target)
            target_path = res_target.target if (res_target and res_target.success) else target

            # Handle virtual shell folders like shell:RecycleBinFolder
            if target_path and target_path.lower().startswith("shell:"):
                if sys.platform == "win32":
                    subprocess.Popen(["explorer.exe", target_path])
                target_name = "Recycle Bin" if "recycle" in target_path.lower() else (
                    "Startup" if target_path.lower() == "shell:startup" else target
                )
                return ActionResult(
                    success=True,
                    action="OPEN",
                    target=target_path,
                    verified=True,
                    data={"path": target_path, "opened": True, "message": f"'{target_name}' open kar diya hai, Boss."}
                )

            if not os.path.exists(target_path):
                # Fallback special path resolution check
                special = self.get_special_path(target)
                if special and (os.path.exists(special) or special.lower().startswith("shell:")):
                    target_path = special
                    if target_path.lower().startswith("shell:"):
                        if sys.platform == "win32":
                            subprocess.Popen(["explorer.exe", target_path])
                        target_name = "Recycle Bin" if "recycle" in target_path.lower() else (
                            "Startup" if target_path.lower() == "shell:startup" else target
                        )
                        return ActionResult(
                            success=True,
                            action="OPEN",
                            target=target_path,
                            verified=True,
                            data={"path": target_path, "opened": True, "message": f"'{target_name}' open kar diya hai, Boss."}
                        )
                else:
                    return ActionResult(
                        success=False,
                        action="OPEN",
                        target=target_path,
                        error=f"Path '{target_path}' does not exist.",
                        verified=False,
                    )

            if sys.platform == "win32":
                os.startfile(target_path)  # type: ignore
            else:
                subprocess.Popen(["xdg-open", target_path])

            target_name = os.path.basename(target_path.rstrip("/\\")) or target_path
            return ActionResult(
                success=True,
                action="OPEN",
                target=target_path,
                verified=True,
                data={"path": target_path, "opened": True, "message": f"'{target_name}' open kar diya hai, Boss."}
            )
        except Exception as e:
            logger.exception("Failed to open %s", target)
            return ActionResult(
                success=False,
                action="OPEN",
                target=target,
                error=f"Error opening '{target}': {e}",
                verified=False,
            )

    def open_folder(self, target: str, verify_window: bool = False, window_manager: Optional[Any] = None) -> ActionResult:
        """Explicitly open a folder in Windows Explorer with optional window verification."""
        res = self.open(target)
        if res.success:
            name = os.path.basename(str(res.target or "").rstrip("/\\")) or res.target
            if str(res.target).lower().startswith("shell:"):
                name = "Startup" if str(res.target).lower() == "shell:startup" else "Recycle Bin"
            res.data["message"] = f"'{name}' folder open kar diya hai, Boss."

            if verify_window:
                wm = window_manager
                if not wm:
                    try:
                        from plugins.windows.window_manager import WindowManager
                        wm = WindowManager()
                    except Exception:
                        pass
                if wm:
                    wins = wm.find_folder_windows(name if name != target else target)
                    if not wins:
                        res.success = False
                        res.verified = False
                        res.error = f"Explorer window for '{name}' was not found on screen."
                        res.data["opened"] = False
                    else:
                        res.verified = True
        return res

    def close_folder(self, target: str = "", close_all: bool = False) -> ActionResult:
        """
        Safely closes Windows Explorer folder windows without terminating explorer.exe shell.
        """
        try:
            from plugins.windows.window_manager import WindowManager
            wm = WindowManager()

            is_all = close_all or (target.strip().lower() in ("all", "all folders", "saare", "saare folder", "saare folders", "sab", "everything"))
            if is_all:
                count = wm.close_all_folder_windows()
                msg = f"{count} open folder windows band kar diye hain, Boss." if count > 0 else "Koi open folder window nahi mili, Boss."
                return ActionResult(
                    success=True,
                    action="CLOSE_FOLDER",
                    target="all",
                    verified=True,
                    data={"count": count, "closed_all": True, "message": msg}
                )

            closed = wm.close_folder_window(target)
            clean_name = target.strip()
            msg = f"'{clean_name}' folder window band kar di hai, Boss." if closed else f"'{clean_name}' folder ka koi open window nahi mila, Boss."
            return ActionResult(
                success=closed,
                action="CLOSE_FOLDER",
                target=target,
                verified=closed,
                data={"closed": closed, "target": target, "message": msg}
            )
        except Exception as e:
            logger.exception("Failed to close folder %s", target)
            return ActionResult(
                success=False,
                action="CLOSE_FOLDER",
                target=target,
                error=f"Error closing folder '{target}': {e}",
                verified=False,
            )

    def verify(self, verify_type: str, target: str, expected: Any = None) -> ActionResult:
        """Verify an expectation against the filesystem."""
        try:
            res_target = self.resolve_path(target)
            target_path = res_target.target if res_target.success else target

            vtype = verify_type.lower().strip()

            if vtype in ("folder_exists", "dir_exists", "is_dir"):
                exists = os.path.exists(target_path) and os.path.isdir(target_path)
                return ActionResult(
                    success=exists,
                    action="VERIFY",
                    target=target_path,
                    verified=exists,
                    data={"check": vtype, "exists": exists}
                )

            if vtype in ("file_exists", "is_file"):
                exists = os.path.exists(target_path) and os.path.isfile(target_path)
                return ActionResult(
                    success=exists,
                    action="VERIFY",
                    target=target_path,
                    verified=exists,
                    data={"check": vtype, "exists": exists}
                )

            if vtype in ("file_contains", "contains_text", "file_content"):
                if not os.path.exists(target_path) or not os.path.isfile(target_path):
                    return ActionResult(
                        success=False,
                        action="VERIFY",
                        target=target_path,
                        verified=False,
                        error="Target file not found."
                    )
                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                matches = str(expected) in content if expected else False
                return ActionResult(
                    success=matches,
                    action="VERIFY",
                    target=target_path,
                    verified=matches,
                    data={"check": vtype, "matches": matches, "expected": expected}
                )

            if vtype in ("path_not_exists", "not_exists", "deleted", "does_not_exist"):
                not_exists = not os.path.exists(target_path)
                return ActionResult(
                    success=not_exists,
                    action="VERIFY",
                    target=target_path,
                    verified=not_exists,
                    data={"check": vtype, "not_exists": not_exists}
                )

            if vtype in ("count_equals", "item_count"):
                c_res = self.count_items(target_path)
                if not c_res.success:
                    return c_res
                actual_count = c_res.data.get("count", 0)
                matches = (actual_count == int(expected)) if expected is not None else False
                return ActionResult(
                    success=matches,
                    action="VERIFY",
                    target=target_path,
                    verified=matches,
                    data={"check": vtype, "actual": actual_count, "expected": expected}
                )

            return ActionResult(
                success=False,
                action="VERIFY",
                target=target_path,
                error=f"Unsupported verification check: '{verify_type}'",
                verified=False,
            )
        except Exception as e:
            logger.exception("Verification error on %s", target)
            return ActionResult(
                success=False,
                action="VERIFY",
                target=target,
                error=f"Verification check failed: {e}",
                verified=False,
            )
