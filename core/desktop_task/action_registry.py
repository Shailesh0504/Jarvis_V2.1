# core/desktop_task/action_registry.py
"""
Task action results and backward-compatible delegate to the FileSystem plugin.
Concrete filesystem execution is decoupled and hosted in plugins.files.operations.
"""

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, Optional

from plugins.files.operations import ActionResult, FilesystemOperations

logger = logging.getLogger("jarvis.desktop_task.action_registry")

# Canonical task action result
TaskActionResult = ActionResult


class FilesystemActionRegistry:
    """Backward-compatible facade delegating directly to FileSystem plugin operations."""

    @staticmethod
    def get_special_path(name: str) -> str:
        return FilesystemOperations.get_special_path(name)

    def __init__(self, ops: Optional[FilesystemOperations] = None):
        self._ops = ops or FilesystemOperations()

    def resolve_path(self, target: str, base_dir: Optional[str] = None) -> TaskActionResult:
        return self._ops.resolve_path(target, base_dir=base_dir)

    def list_directory(self, path: str, filter_type: str = "all") -> TaskActionResult:
        return self._ops.list_directory(path, filter_type=filter_type)

    def count_items(self, path: str, filter_type: str = "all") -> TaskActionResult:
        return self._ops.count_items(path, filter_type=filter_type)

    def create_folder(self, parent: str, name: str) -> TaskActionResult:
        return self._ops.create_folder(parent, name)

    def create_file(
        self,
        parent: str,
        name: Optional[str] = None,
        file_type: str = "txt",
        initial_content: str = ""
    ) -> TaskActionResult:
        return self._ops.create_file(parent, name=name, file_type=file_type, initial_content=initial_content)

    def write_file(self, target: str, content: str, mode: str = "w") -> TaskActionResult:
        return self._ops.write_file(target, content, mode=mode)

    def read_file(self, target: str, max_chars: int = 10000) -> TaskActionResult:
        return self._ops.read_file(target, max_chars=max_chars)

    def move(self, source: str, destination: str) -> TaskActionResult:
        return self._ops.move(source, destination)

    def copy(self, source: str, destination: str) -> TaskActionResult:
        return self._ops.copy(source, destination)

    def rename(self, source: str, new_name_or_path: str) -> TaskActionResult:
        return self._ops.rename(source, new_name_or_path)

    def delete(self, target: str, confirmed: bool = False) -> TaskActionResult:
        return self._ops.delete(target, confirmed=confirmed)

    def open(self, target: str) -> TaskActionResult:
        return self._ops.open(target)

    def verify(self, verify_type: str, target: str, expected: Any = None) -> TaskActionResult:
        return self._ops.verify(verify_type, target, expected=expected)
