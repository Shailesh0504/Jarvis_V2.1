# plugins/archive/plugin.py
"""Archive capability plugin implementation for managing zip, tar, compression, and extraction."""

import fnmatch
import logging
import os
import shutil
import tarfile
import tempfile
import zipfile
from typing import Any, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.archive")


class ArchivePlugin(BasePlugin):
    """Controls compression, decompression, validation, and manipulation of archives."""

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="archive",
            version="2.0.0",
            description="Comprehensive ZIP and TAR archive manager, inspector, and converter.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name in ("create_zip", "create_tar_archive", "convert_archive_format", "add_file_to_archive"):
            path = (result_data or {}).get("output_zip") or (result_data or {}).get("output_path") or (result_data or {}).get("archive_path")
            if path and os.path.isfile(path) and os.path.getsize(path) > 0:
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="file_exists",
                    expected=path,
                    actual=f"{os.path.getsize(path)} bytes",
                    message="Archive artifact verified on disk."
                )
            return VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="file_exists",
                expected=path or "valid archive",
                actual="Missing or empty",
                error="Expected archive was not produced."
            )
        elif action_name in ("extract_zip", "extract_tar_archive", "extract_single_file_from_archive"):
            dest = (result_data or {}).get("extracted_to") or (result_data or {}).get("destination_path")
            if dest and os.path.exists(dest):
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="directory_exists",
                    expected=dest,
                    actual="Exists",
                    message="Extracted output verified on disk."
                )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. create_zip
        if action_name == "create_zip":
            src = parameters.get("source_path", "").strip()
            out = parameters.get("output_zip", "").strip()
            if not src or not os.path.exists(src):
                return PluginResult(success=False, error=f"Source '{src}' nahi mila, Boss.")

            if not out:
                out = f"{src.rstrip(r'\/')}.zip"

            try:
                os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
                if os.path.isdir(src):
                    shutil.make_archive(out.replace(".zip", ""), 'zip', src)
                else:
                    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
                        zf.write(src, os.path.basename(src))

                return PluginResult(
                    success=True,
                    data={"output_zip": os.path.abspath(out), "message": f"ZIP archive '{out}' successfully created."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Zip creation error: {e}")

        # 2. extract_zip
        elif action_name == "extract_zip":
            zpath = parameters.get("zip_path", "").strip() or parameters.get("archive_path", "").strip()
            dest = parameters.get("extract_to", "").strip()
            if not zpath or not os.path.exists(zpath):
                return PluginResult(success=False, error=f"Archive file '{zpath}' nahi mili, Boss.")

            if not dest:
                dest = zpath.replace(".zip", "")

            try:
                os.makedirs(dest, exist_ok=True)
                with zipfile.ZipFile(zpath, 'r') as zf:
                    # Safe extraction avoiding path traversal
                    for member in zf.infolist():
                        target_path = os.path.abspath(os.path.join(dest, member.filename))
                        if not target_path.startswith(os.path.abspath(dest)):
                            raise ValueError(f"Path traversal detected in archive: {member.filename}")
                    zf.extractall(dest)

                return PluginResult(
                    success=True,
                    data={"extracted_to": os.path.abspath(dest), "message": f"Archive '{zpath}' extracted to: {dest}"}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Extraction error: {e}")

        # 3. list_archive_contents
        elif action_name == "list_archive_contents":
            zpath = parameters.get("archive_path", "").strip() or parameters.get("zip_path", "").strip()
            if not zpath or not os.path.exists(zpath):
                return PluginResult(success=False, error=f"Archive file '{zpath}' nahi mili, Boss.")

            try:
                if tarfile.is_tarfile(zpath):
                    with tarfile.open(zpath, "r:*") as tf:
                        names = tf.getnames()
                else:
                    with zipfile.ZipFile(zpath, 'r') as zf:
                        names = zf.namelist()

                return PluginResult(
                    success=True,
                    data={"files": names, "count": len(names), "message": f"Archive contains {len(names)} items."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Read archive error: {e}")

        # 4. create_tar_archive
        elif action_name == "create_tar_archive":
            src = parameters.get("source_path", "").strip()
            out = parameters.get("output_path", "").strip()
            comp = parameters.get("compression", "gz").strip().lower()

            if not src or not os.path.exists(src):
                return PluginResult(success=False, error=f"Source '{src}' not found.")

            ext = f".tar.{comp}" if comp in ("gz", "bz2") else ".tar"
            if not out:
                out = f"{src.rstrip(r'\/')}{ext}"

            os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
            mode = f"w:{comp}" if comp in ("gz", "bz2") else "w"

            try:
                with tarfile.open(out, mode) as tf:
                    tf.add(src, arcname=os.path.basename(src))

                return PluginResult(
                    success=True,
                    data={"output_path": os.path.abspath(out), "message": f"TAR archive created: {out}"}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Tar creation error: {e}")

        # 5. extract_tar_archive
        elif action_name == "extract_tar_archive":
            path = parameters.get("archive_path", "").strip()
            dest = parameters.get("extract_to", "").strip()
            if not path or not os.path.isfile(path):
                return PluginResult(success=False, error=f"Archive file '{path}' not found.")

            if not dest:
                dest = os.path.splitext(os.path.splitext(path)[0])[0]

            try:
                os.makedirs(dest, exist_ok=True)
                with tarfile.open(path, "r:*") as tf:
                    # Sanitize paths
                    for m in tf.getmembers():
                        tpath = os.path.abspath(os.path.join(dest, m.name))
                        if not tpath.startswith(os.path.abspath(dest)):
                            raise ValueError(f"Path traversal detected in tar: {m.name}")
                    tf.extractall(dest)

                return PluginResult(
                    success=True,
                    data={"extracted_to": os.path.abspath(dest), "message": f"Extracted TAR archive to {dest}."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Tar extract error: {e}")

        # 6. extract_single_file_from_archive
        elif action_name == "extract_single_file_from_archive":
            path = parameters.get("archive_path", "").strip()
            member = parameters.get("member_name", "").strip()
            dest = parameters.get("destination_dir", "").strip()

            if not path or not os.path.isfile(path):
                return PluginResult(success=False, error=f"Archive '{path}' not found.")
            if not member:
                return PluginResult(success=False, error="member_name is required.")
            if not dest:
                return PluginResult(success=False, error="destination_dir is required.")

            os.makedirs(dest, exist_ok=True)
            try:
                if tarfile.is_tarfile(path):
                    with tarfile.open(path, "r:*") as tf:
                        tarinfo = tf.getmember(member)
                        tf.extract(tarinfo, path=dest)
                else:
                    with zipfile.ZipFile(path, "r") as zf:
                        zf.extract(member, path=dest)

                target = os.path.join(dest, member)
                return PluginResult(
                    success=True,
                    data={"destination_path": os.path.abspath(target), "message": f"Extracted '{member}' to '{dest}'."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed extracting '{member}': {e}")

        # 7. verify_archive_integrity
        elif action_name == "verify_archive_integrity":
            path = parameters.get("archive_path", "").strip()
            if not path or not os.path.isfile(path):
                return PluginResult(success=False, error=f"Archive '{path}' not found.")

            try:
                if tarfile.is_tarfile(path):
                    with tarfile.open(path, "r:*") as tf:
                        count = len(tf.getmembers())
                    return PluginResult(
                        success=True,
                        data={"valid": True, "type": "tar", "items": count, "message": f"TAR archive is valid ({count} items)."}
                    )
                else:
                    with zipfile.ZipFile(path, "r") as zf:
                        corrupted = zf.testzip()
                    if corrupted is None:
                        return PluginResult(
                            success=True,
                            data={"valid": True, "type": "zip", "message": "ZIP archive CRC32 checksums verified. No corruption."}
                        )
                    else:
                        return PluginResult(
                            success=False,
                            data={"valid": False, "first_corrupted_file": corrupted},
                            error=f"ZIP archive corrupted at '{corrupted}'."
                        )
            except Exception as e:
                return PluginResult(success=False, error=f"Integrity check failed: {e}")

        # 8. get_archive_compression_ratio
        elif action_name == "get_archive_compression_ratio":
            path = parameters.get("archive_path", "").strip()
            if not path or not os.path.isfile(path):
                return PluginResult(success=False, error=f"Archive '{path}' not found.")

            try:
                compressed_size = os.path.getsize(path)
                uncompressed_size = 0

                if tarfile.is_tarfile(path):
                    with tarfile.open(path, "r:*") as tf:
                        uncompressed_size = sum(m.size for m in tf.getmembers())
                else:
                    with zipfile.ZipFile(path, "r") as zf:
                        uncompressed_size = sum(i.file_size for i in zf.infolist())

                savings_pct = 0.0
                if uncompressed_size > 0:
                    savings_pct = round((1.0 - (compressed_size / float(uncompressed_size))) * 100.0, 1)

                return PluginResult(
                    success=True,
                    data={
                        "archive_path": os.path.abspath(path),
                        "compressed_bytes": compressed_size,
                        "uncompressed_bytes": uncompressed_size,
                        "savings_percent": savings_pct,
                        "message": f"Compressed: {round(compressed_size/1024, 1)} KB vs Uncompressed: {round(uncompressed_size/1024, 1)} KB ({savings_pct}% space saved)."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed calculating compression ratio: {e}")

        # 9. add_file_to_archive
        elif action_name == "add_file_to_archive":
            path = parameters.get("archive_path", "").strip()
            add_file = parameters.get("file_to_add", "").strip()
            arcname = parameters.get("arcname", "").strip()

            if not path or not os.path.isfile(path):
                return PluginResult(success=False, error=f"Archive '{path}' not found.")
            if not add_file or not os.path.isfile(add_file):
                return PluginResult(success=False, error=f"File to add '{add_file}' not found.")

            if not arcname:
                arcname = os.path.basename(add_file)

            try:
                with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(add_file, arcname)

                return PluginResult(
                    success=True,
                    data={"archive_path": os.path.abspath(path), "added_file": arcname, "message": f"Added '{arcname}' to '{path}'."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed appending file to archive: {e}")

        # 10. delete_file_from_archive
        elif action_name == "delete_file_from_archive":
            path = parameters.get("archive_path", "").strip()
            member = parameters.get("member_name", "").strip()

            if not path or not os.path.isfile(path):
                return PluginResult(success=False, error=f"Archive '{path}' not found.")
            if not member:
                return PluginResult(success=False, error="member_name is required.")

            try:
                temp_zip = f"{path}.tmp"
                with zipfile.ZipFile(path, "r") as zin:
                    if member not in zin.namelist():
                        return PluginResult(success=False, error=f"'{member}' not found inside archive.")

                    with zipfile.ZipFile(temp_zip, "w") as zout:
                        for item in zin.infolist():
                            if item.filename != member:
                                buffer = zin.read(item.filename)
                                zout.writestr(item, buffer)

                os.remove(path)
                os.rename(temp_zip, path)

                return PluginResult(
                    success=True,
                    data={"archive_path": os.path.abspath(path), "deleted_member": member, "message": f"Deleted '{member}' from '{path}'."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed deleting member: {e}")

        # 11. search_files_in_archive
        elif action_name == "search_files_in_archive":
            path = parameters.get("archive_path", "").strip()
            pattern = parameters.get("pattern", "").strip()

            if not path or not os.path.isfile(path):
                return PluginResult(success=False, error=f"Archive '{path}' not found.")
            if not pattern:
                return PluginResult(success=False, error="pattern is required.")

            try:
                if tarfile.is_tarfile(path):
                    with tarfile.open(path, "r:*") as tf:
                        names = tf.getnames()
                else:
                    with zipfile.ZipFile(path, "r") as zf:
                        names = zf.namelist()

                matches = [n for n in names if fnmatch.fnmatch(n.lower(), f"*{pattern.lower()}*")]

                return PluginResult(
                    success=True,
                    data={"pattern": pattern, "count": len(matches), "matches": matches, "message": f"Found {len(matches)} match(es) for '{pattern}'."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Search failed: {e}")

        # 12. convert_archive_format
        elif action_name == "convert_archive_format":
            src = parameters.get("source_archive", "").strip()
            target_fmt = parameters.get("target_format", "").strip().lower()
            out_path = parameters.get("output_path", "").strip()

            if not src or not os.path.isfile(src):
                return PluginResult(success=False, error=f"Source archive '{src}' not found.")

            temp_dir = tempfile.mkdtemp(prefix="conv_arch_")
            try:
                # Extract
                if tarfile.is_tarfile(src):
                    with tarfile.open(src, "r:*") as tf:
                        tf.extractall(temp_dir)
                else:
                    with zipfile.ZipFile(src, "r") as zf:
                        zf.extractall(temp_dir)

                # Recompress
                if not out_path:
                    base, _ = os.path.splitext(src)
                    if base.endswith(".tar"):
                        base = os.path.splitext(base)[0]
                    out_path = f"{base}.{target_fmt.lstrip('.')}"

                if "tar" in target_fmt:
                    comp = "gz" if "gz" in target_fmt else ("bz2" if "bz2" in target_fmt else "")
                    mode = f"w:{comp}" if comp else "w"
                    with tarfile.open(out_path, mode) as tf:
                        for f in os.listdir(temp_dir):
                            tf.add(os.path.join(temp_dir, f), arcname=f)
                else:
                    shutil.make_archive(out_path.replace(".zip", ""), "zip", temp_dir)

                return PluginResult(
                    success=True,
                    data={"output_path": os.path.abspath(out_path), "format": target_fmt, "message": f"Converted '{src}' to '{out_path}'."}
                )
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        # 13. get_archive_metadata
        elif action_name == "get_archive_metadata":
            path = parameters.get("archive_path", "").strip()
            if not path or not os.path.isfile(path):
                return PluginResult(success=False, error=f"Archive '{path}' not found.")

            try:
                st = os.stat(path)
                meta = {
                    "path": os.path.abspath(path),
                    "size_kb": round(st.st_size / 1024.0, 2),
                    "is_tar": tarfile.is_tarfile(path),
                    "is_zip": zipfile.is_zipfile(path)
                }

                if meta["is_zip"]:
                    with zipfile.ZipFile(path, "r") as zf:
                        meta["items_count"] = len(zf.infolist())
                        meta["has_comments"] = bool(zf.comment)
                elif meta["is_tar"]:
                    with tarfile.open(path, "r:*") as tf:
                        meta["items_count"] = len(tf.getmembers())

                return PluginResult(
                    success=True,
                    data={"metadata": meta, "message": f"Archive metadata: {meta.get('items_count', 0)} item(s), {meta['size_kb']} KB."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Metadata error: {e}")

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Archive plugin.")
