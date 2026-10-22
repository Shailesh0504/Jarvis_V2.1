# plugins/files/plugin.py
"""Files Plugin implementation."""

import os
import time
from typing import Any, Dict, Optional
from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .operations import FilesystemOperations
from .permissions import PERMISSIONS_REQUIRED


class FilesPlugin(BasePlugin):
    """File and directory exploration and verified desktop filesystem operations."""

    def __init__(self, manifest: Optional[PluginManifest] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest=manifest, config=config)
        self.ops = FilesystemOperations()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="files",
            version="1.0.0",
            description="Allows listing directories, viewing file metadata, and executing verified desktop filesystem tasks.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}
        act_upper = action_name.upper().strip()

        # 1. Structured Desktop Task Orchestration Actions
        if act_upper == "RESOLVE_PATH":
            res = self.ops.resolve_path(parameters.get("target") or parameters.get("path", ""), parameters.get("base_dir"))
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper == "LIST_DIRECTORY":
            res = self.ops.list_directory(parameters.get("path", "."), parameters.get("filter_type", "all"))
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper == "COUNT_ITEMS":
            res = self.ops.count_items(parameters.get("path", "."), parameters.get("filter_type", "all"))
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper == "CREATE_FOLDER":
            parent = parameters.get("parent") or parameters.get("path", "")
            res = self.ops.create_folder(parent, parameters.get("name", ""))
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper == "CREATE_FILE":
            parent = parameters.get("parent") or parameters.get("path", "")
            res = self.ops.create_file(
                parent=parent,
                name=parameters.get("name"),
                file_type=parameters.get("file_type", "txt"),
                initial_content=parameters.get("initial_content", "")
            )
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper == "WRITE_FILE":
            target = parameters.get("target") or parameters.get("path", "")
            res = self.ops.write_file(
                target=target,
                content=parameters.get("content", ""),
                mode=parameters.get("mode", "w")
            )
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper == "READ_FILE":
            target = parameters.get("target") or parameters.get("path", "")
            max_chars = int(parameters.get("max_chars", 10000))
            res = self.ops.read_file(target=target, max_chars=max_chars)
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper == "MOVE":
            source = parameters.get("source") or parameters.get("src") or parameters.get("path", "")
            destination = parameters.get("destination") or parameters.get("dst", "")
            res = self.ops.move(source, destination)
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper == "COPY":
            source = parameters.get("source") or parameters.get("src") or parameters.get("path", "")
            destination = parameters.get("destination") or parameters.get("dst", "")
            res = self.ops.copy(source, destination)
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper == "RENAME":
            source = parameters.get("source") or parameters.get("path", "")
            res = self.ops.rename(source, parameters.get("new_name") or parameters.get("new_name_or_path", ""))
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper == "DELETE":
            target = parameters.get("target") or parameters.get("path", "")
            res = self.ops.delete(target, confirmed=parameters.get("confirmed", False))
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper == "OPEN":
            target = parameters.get("target") or parameters.get("path", "")
            res = self.ops.open(target)
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper == "VERIFY":
            target = parameters.get("target") or parameters.get("path", "")
            res = self.ops.verify(
                verify_type=parameters.get("verify_type", ""),
                target=target,
                expected=parameters.get("expected")
            )
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper in ("OPEN_FOLDER", "OPEN_DIRECTORY"):
            target = parameters.get("target") or parameters.get("path") or parameters.get("folder", "")
            res = self.ops.open_folder(target)
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        if act_upper in ("CLOSE_FOLDER", "CLOSE_DIRECTORY", "CLOSE_ALL_FOLDERS"):
            target = parameters.get("target") or parameters.get("path") or parameters.get("folder", "")
            close_all = bool(parameters.get("close_all", False) or act_upper == "CLOSE_ALL_FOLDERS" or target.lower() in ("all", "all folders", "saare", "saare folder", "saare folders"))
            res = self.ops.close_folder(target=target, close_all=close_all)
            return PluginResult(success=res.success, data=res.to_dict(), error=res.error)

        # 2. Legacy File Actions (Backward Compatibility)
        if action_name == "list_dir":
            target_path = parameters.get("path", ".") or "."
            try:
                if not os.path.exists(target_path):
                    return PluginResult(success=False, error=f"Path '{target_path}' does not exist.")
                items = os.listdir(target_path)
                return PluginResult(
                    success=True,
                    data={
                        "path": os.path.abspath(target_path),
                        "count": len(items),
                        "files": items[:25],
                        "message": f"Found {len(items)} items in {os.path.basename(os.path.abspath(target_path)) or 'current directory'}."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=str(e))

        elif action_name == "get_file_info":
            target_path = parameters.get("path")
            if not target_path or not os.path.exists(target_path):
                return PluginResult(success=False, error=f"File '{target_path}' not found.")
            try:
                stat = os.stat(target_path)
                return PluginResult(
                    success=True,
                    data={
                        "path": os.path.abspath(target_path),
                        "size_bytes": stat.st_size,
                        "size_kb": round(stat.st_size / 1024, 2),
                        "modified": time.ctime(stat.st_mtime),
                        "message": f"File '{os.path.basename(target_path)}' is {round(stat.st_size/1024, 2)} KB."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=str(e))

        elif action_name == "read_file":
            target_path = parameters.get("path", "")
            max_chars = int(parameters.get("max_chars", 4000))
            if not target_path or not os.path.exists(target_path):
                return PluginResult(success=False, error=f"File '{target_path}' not found.")
            try:
                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(max_chars)
                return PluginResult(
                    success=True,
                    data={
                        "path": os.path.abspath(target_path),
                        "content": content,
                        "length": len(content),
                        "message": f"Read {len(content)} characters from '{os.path.basename(target_path)}'."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Error reading file '{target_path}': {e}")

        elif action_name == "write_file":
            target_path = parameters.get("path", "")
            content = str(parameters.get("content", ""))
            if not target_path:
                return PluginResult(success=False, error="File path is required.")
            try:
                dir_name = os.path.dirname(os.path.abspath(target_path))
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return PluginResult(
                    success=True,
                    data={
                        "path": os.path.abspath(target_path),
                        "bytes_written": len(content.encode("utf-8")),
                        "message": f"Successfully wrote {len(content)} characters to '{os.path.basename(target_path)}'."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Error writing to file '{target_path}': {e}")

        elif action_name == "find_recent_files":
            raw_ext = parameters.get("extension", "").lower()
            if raw_ext in ("excel", "spreadsheet", "sheets"):
                target_exts = ["xlsx", "csv", "xls", "xlsm"]
            elif raw_ext:
                target_exts = [e.strip().lstrip(".") for e in raw_ext.split(",") if e.strip()]
            else:
                target_exts = []

            search_dir = parameters.get("directory", ".") or "."
            limit = int(parameters.get("limit", 5))

            try:
                matched_files = []
                for root, _, filenames in os.walk(search_dir):
                    # Skip .venv, __pycache__, .git
                    if any(ignored in root for ignored in [".venv", "__pycache__", ".git", ".pytest_cache"]):
                        continue
                    for fname in filenames:
                        lower_fname = fname.lower()
                        matches = False
                        if not target_exts:
                            matches = True
                        else:
                            for te in target_exts:
                                if lower_fname.endswith(f".{te}"):
                                    matches = True
                                    break

                        if matches:
                            full_path = os.path.join(root, fname)
                            try:
                                mtime = os.path.getmtime(full_path)
                                matched_files.append({
                                    "name": fname,
                                    "path": os.path.abspath(full_path),
                                    "rel_path": full_path,
                                    "modified_timestamp": mtime,
                                    "modified_str": time.ctime(mtime)
                                })
                            except Exception:
                                pass

                # Sort by mtime descending (most recent first)
                matched_files.sort(key=lambda x: x["modified_timestamp"], reverse=True)
                top_files = matched_files[:limit]

                if top_files:
                    best_file = top_files[0]["path"]
                    return PluginResult(
                        success=True,
                        data={
                            "files": top_files,
                            "count": len(top_files),
                            "latest_file": best_file,
                            "latest_file_name": top_files[0]["name"],
                            "message": f"Found {len(top_files)} recent files. Latest: '{top_files[0]['name']}'."
                        }
                    )
                return PluginResult(
                    success=True,
                    data={"files": [], "count": 0, "latest_file": None, "message": "No matching recent files found."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Error finding files: {e}")

        elif action_name == "organize_directory":
            target_dir = parameters.get("directory", ".") or "."
            dry_run = parameters.get("dry_run", False)

            if not os.path.exists(target_dir):
                return PluginResult(success=False, error=f"Directory '{target_dir}' does not exist.")

            CATEGORY_EXTS = {
                "Documents": ["pdf", "docx", "doc", "txt", "xlsx", "xls", "pptx", "csv"],
                "Images": ["jpg", "jpeg", "png", "gif", "svg", "webp", "bmp"],
                "Audio": ["mp3", "wav", "flac", "aac", "ogg"],
                "Video": ["mp4", "mkv", "avi", "mov", "wmv"],
                "Archives": ["zip", "rar", "7z", "tar", "gz"],
                "Code": ["py", "js", "html", "css", "json", "ts", "cpp", "c", "java"],
                "Installers": ["exe", "msi", "dmg", "iso"]
            }

            moved_counts = {cat: 0 for cat in CATEGORY_EXTS}
            moved_counts["Others"] = 0
            total_moved = 0

            try:
                for fname in os.listdir(target_dir):
                    fpath = os.path.join(target_dir, fname)
                    if os.path.isfile(fpath):
                        ext = fname.split(".")[-1].lower() if "." in fname else ""
                        assigned_cat = "Others"
                        for cat, exts in CATEGORY_EXTS.items():
                            if ext in exts:
                                assigned_cat = cat
                                break

                        cat_dir = os.path.join(target_dir, assigned_cat)
                        if not dry_run:
                            os.makedirs(cat_dir, exist_ok=True)
                            dest_path = os.path.join(cat_dir, fname)
                            # If dest exists, rename with timestamp
                            if os.path.exists(dest_path) and dest_path != fpath:
                                dest_path = os.path.join(cat_dir, f"{int(time.time())}_{fname}")
                            os.rename(fpath, dest_path)

                        moved_counts[assigned_cat] += 1
                        total_moved += 1

                summary_parts = [f"{k}: {v}" for k, v in moved_counts.items() if v > 0]
                summary_str = ", ".join(summary_parts) if summary_parts else "No loose files found to organize"
                return PluginResult(
                    success=True,
                    data={
                        "directory": os.path.abspath(target_dir),
                        "total_files_organized": total_moved,
                        "breakdown": moved_counts,
                        "message": f"Organized {total_moved} files in '{os.path.basename(os.path.abspath(target_dir)) or 'directory'}' ({summary_str})."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Error organizing directory: {e}")

        elif action_name == "find_duplicates":
            target_dir = parameters.get("directory", ".") or "."
            if not os.path.exists(target_dir):
                return PluginResult(success=False, error=f"Directory '{target_dir}' does not exist.")

            import hashlib

            def get_file_hash(filepath: str) -> str:
                hasher = hashlib.md5()
                try:
                    with open(filepath, "rb") as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            hasher.update(chunk)
                    return hasher.hexdigest()
                except Exception:
                    return ""

            try:
                hash_map = {}
                duplicates = []

                for root, _, files in os.walk(target_dir):
                    if any(ignored in root for ignored in [".venv", "__pycache__", ".git", ".pytest_cache"]):
                        continue
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        try:
                            fhash = get_file_hash(fpath)
                            if fhash:
                                if fhash in hash_map:
                                    duplicates.append({
                                        "original": hash_map[fhash],
                                        "duplicate": fpath,
                                        "name": fname,
                                        "size_kb": round(os.path.getsize(fpath) / 1024, 2)
                                    })
                                else:
                                    hash_map[fhash] = fpath
                        except Exception:
                            pass

                dup_count = len(duplicates)
                return PluginResult(
                    success=True,
                    data={
                        "directory": os.path.abspath(target_dir),
                        "duplicate_count": dup_count,
                        "duplicates": duplicates,
                        "message": f"Duplicate scan completed: Found {dup_count} duplicate files in '{os.path.basename(os.path.abspath(target_dir)) or 'directory'}'."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Error scanning for duplicates: {e}")

        elif action_name == "calculate_hash":
            target_path = parameters.get("path", "")
            algo = str(parameters.get("algorithm", "sha256")).lower().strip()
            if not target_path or not os.path.exists(target_path):
                return PluginResult(success=False, error=f"File '{target_path}' does not exist.")
            import hashlib
            try:
                h = hashlib.new(algo)
                with open(target_path, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
                digest = h.hexdigest()
                return PluginResult(
                    success=True,
                    data={
                        "path": os.path.abspath(target_path),
                        "algorithm": algo,
                        "hash": digest,
                        "size_bytes": os.path.getsize(target_path),
                        "message": f"{algo.upper()} checksum: {digest}"
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Error calculating hash: {e}")

        elif action_name == "get_directory_size":
            target_dir = parameters.get("path", ".") or "."
            if not os.path.exists(target_dir):
                return PluginResult(success=False, error=f"Directory '{target_dir}' does not exist.")
            total_bytes = 0
            file_count = 0
            dir_count = 0
            exts: Dict[str, int] = {}
            for root, dirs, files in os.walk(target_dir):
                dir_count += len(dirs)
                for f in files:
                    file_count += 1
                    fp = os.path.join(root, f)
                    ext = os.path.splitext(f)[1].lower() or "no_ext"
                    exts[ext] = exts.get(ext, 0) + 1
                    try:
                        total_bytes += os.path.getsize(fp)
                    except OSError:
                        pass
            return PluginResult(
                success=True,
                data={
                    "path": os.path.abspath(target_dir),
                    "size_bytes": total_bytes,
                    "size_kb": round(total_bytes / 1024, 2),
                    "size_mb": round(total_bytes / (1024 * 1024), 2),
                    "size_gb": round(total_bytes / (1024 * 1024 * 1024), 3),
                    "file_count": file_count,
                    "folder_count": dir_count,
                    "extensions": exts,
                    "message": f"Directory size: {round(total_bytes / (1024*1024), 2)} MB across {file_count} files."
                }
            )

        elif action_name == "search_files_by_content":
            query = str(parameters.get("query", "")).strip()
            if not query:
                return PluginResult(success=False, error="'query' parameter is required.")
            target_dir = parameters.get("directory", ".") or "."
            ext_filter = str(parameters.get("extension", "")).lower().strip().lstrip(".")
            case_sens = bool(parameters.get("case_sensitive", False))
            target_q = query if case_sens else query.lower()

            matches = []
            for root, _, files in os.walk(target_dir):
                if any(ig in root for ig in [".venv", "__pycache__", ".git"]):
                    continue
                for f in files:
                    if ext_filter and not f.lower().endswith(f".{ext_filter}"):
                        continue
                    fp = os.path.join(root, f)
                    try:
                        with open(fp, "r", encoding="utf-8", errors="ignore") as fl:
                            for idx, line in enumerate(fl, 1):
                                check_line = line if case_sens else line.lower()
                                if target_q in check_line:
                                    matches.append({
                                        "file": os.path.abspath(fp),
                                        "name": f,
                                        "line_number": idx,
                                        "content": line.strip()[:200]
                                    })
                                    if len(matches) >= 50:
                                        break
                    except Exception:
                        pass
                    if len(matches) >= 50:
                        break
                if len(matches) >= 50:
                    break

            return PluginResult(
                success=True,
                data={
                    "query": query,
                    "match_count": len(matches),
                    "matches": matches,
                    "message": f"Found {len(matches)} match(es) for '{query}'."
                }
            )

        elif action_name == "batch_rename":
            target_dir = parameters.get("directory", "")
            if not target_dir or not os.path.exists(target_dir):
                return PluginResult(success=False, error=f"Directory '{target_dir}' does not exist.")
            prefix = str(parameters.get("prefix", ""))
            suffix = str(parameters.get("suffix", ""))
            rep_from = str(parameters.get("replace_from", ""))
            rep_to = str(parameters.get("replace_to", ""))

            renamed = []
            for f in os.listdir(target_dir):
                fp = os.path.join(target_dir, f)
                if os.path.isfile(fp):
                    stem, ext = os.path.splitext(f)
                    new_stem = stem
                    if rep_from:
                        new_stem = new_stem.replace(rep_from, rep_to)
                    if prefix:
                        new_stem = prefix + new_stem
                    if suffix:
                        new_stem = new_stem + suffix
                    new_name = new_stem + ext
                    if new_name != f:
                        new_fp = os.path.join(target_dir, new_name)
                        os.rename(fp, new_fp)
                        renamed.append({"old": f, "new": new_name})

            return PluginResult(
                success=True,
                data={
                    "renamed_count": len(renamed),
                    "renamed_files": renamed,
                    "message": f"Batch renamed {len(renamed)} files."
                }
            )

        elif action_name == "find_large_files":
            target_dir = parameters.get("directory", ".") or "."
            min_mb = float(parameters.get("min_size_mb", 10.0))
            limit = int(parameters.get("limit", 10))
            min_bytes = min_mb * 1024 * 1024

            large_files = []
            for root, _, files in os.walk(target_dir):
                if any(ig in root for ig in [".venv", "__pycache__", ".git"]):
                    continue
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        sz = os.path.getsize(fp)
                        if sz >= min_bytes:
                            large_files.append({
                                "name": f,
                                "path": os.path.abspath(fp),
                                "size_bytes": sz,
                                "size_mb": round(sz / (1024 * 1024), 2)
                            })
                    except OSError:
                        pass

            large_files.sort(key=lambda x: x["size_bytes"], reverse=True)
            top_large = large_files[:limit]
            return PluginResult(
                success=True,
                data={
                    "min_size_mb": min_mb,
                    "count": len(top_large),
                    "files": top_large,
                    "message": f"Found {len(top_large)} files exceeding {min_mb} MB."
                }
            )

        elif action_name == "compare_files":
            p1 = str(parameters.get("path1", "")).strip()
            p2 = str(parameters.get("path2", "")).strip()
            if not p1 or not os.path.exists(p1):
                return PluginResult(success=False, error=f"File 1 '{p1}' does not exist.")
            if not p2 or not os.path.exists(p2):
                return PluginResult(success=False, error=f"File 2 '{p2}' does not exist.")
            import difflib
            try:
                with open(p1, "r", encoding="utf-8", errors="replace") as f1:
                    lines1 = f1.readlines()
                with open(p2, "r", encoding="utf-8", errors="replace") as f2:
                    lines2 = f2.readlines()
                diff = list(difflib.unified_diff(lines1, lines2, fromfile=os.path.basename(p1), tofile=os.path.basename(p2)))
                matcher = difflib.SequenceMatcher(None, "".join(lines1), "".join(lines2))
                ratio = round(matcher.ratio(), 4)
                return PluginResult(
                    success=True,
                    data={
                        "path1": os.path.abspath(p1),
                        "path2": os.path.abspath(p2),
                        "are_identical": len(diff) == 0,
                        "similarity_ratio": ratio,
                        "diff_lines": diff[:50],
                        "message": "Files are identical." if len(diff) == 0 else f"Files differ (similarity: {round(ratio*100, 1)}%)."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Error comparing files: {e}")

        elif action_name == "touch_file":
            target = str(parameters.get("path", "")).strip()
            if not target:
                return PluginResult(success=False, error="'path' parameter is required.")
            try:
                parent = os.path.dirname(os.path.abspath(target))
                if parent:
                    os.makedirs(parent, exist_ok=True)
                if not os.path.exists(target):
                    with open(target, "a"):
                        pass
                else:
                    os.utime(target, None)
                mtime = os.path.getmtime(target)
                return PluginResult(
                    success=True,
                    data={
                        "path": os.path.abspath(target),
                        "modified": time.ctime(mtime),
                        "message": f"Updated timestamp for '{os.path.basename(target)}'."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Error updating file timestamp: {e}")

        elif action_name == "find_empty_folders":
            target_dir = parameters.get("directory", ".") or "."
            do_delete = bool(parameters.get("delete", False))
            if not os.path.exists(target_dir):
                return PluginResult(success=False, error=f"Directory '{target_dir}' does not exist.")
            empty_dirs = []
            for root, dirs, files in os.walk(target_dir, topdown=False):
                if any(ig in root for ig in [".venv", "__pycache__", ".git"]):
                    continue
                if not dirs and not files:
                    empty_dirs.append(root)
                    if do_delete:
                        try:
                            os.rmdir(root)
                        except OSError:
                            pass
            return PluginResult(
                success=True,
                data={
                    "empty_folders": empty_dirs,
                    "count": len(empty_dirs),
                    "deleted": do_delete,
                    "message": f"Found {len(empty_dirs)} empty folders{' (deleted)' if do_delete else ''}."
                }
            )

        elif action_name == "secure_delete":
            target = str(parameters.get("path", "")).strip()
            passes = max(1, int(parameters.get("passes", 1)))
            if not target or not os.path.exists(target):
                return PluginResult(success=False, error=f"File '{target}' does not exist.")
            if os.path.isdir(target):
                return PluginResult(success=False, error="secure_delete operates on files only.")
            try:
                size = os.path.getsize(target)
                with open(target, "ba+", buffering=0) as f:
                    for _ in range(passes):
                        f.seek(0)
                        f.write(os.urandom(size))
                os.remove(target)
                return PluginResult(
                    success=True,
                    data={
                        "path": os.path.abspath(target),
                        "bytes_shredded": size,
                        "passes": passes,
                        "message": f"Securely shredded '{os.path.basename(target)}' ({size} bytes, {passes} passes)."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Error shredding file: {e}")

        elif action_name == "get_disk_free_space":
            target_path = parameters.get("path", ".") or "."
            import shutil
            try:
                usage = shutil.disk_usage(target_path)
                return PluginResult(
                    success=True,
                    data={
                        "path": os.path.abspath(target_path),
                        "total_bytes": usage.total,
                        "used_bytes": usage.used,
                        "free_bytes": usage.free,
                        "total_gb": round(usage.total / (1024 ** 3), 2),
                        "used_gb": round(usage.used / (1024 ** 3), 2),
                        "free_gb": round(usage.free / (1024 ** 3), 2),
                        "percent_free": round((usage.free / usage.total) * 100, 1),
                        "message": f"Disk space: {round(usage.free / (1024**3), 2)} GB free of {round(usage.total / (1024**3), 2)} GB."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Error retrieving disk space: {e}")

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Files plugin.")
