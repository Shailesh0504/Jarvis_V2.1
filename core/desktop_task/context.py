# core/desktop_task/context.py
"""
Capability-agnostic execution context and multi-turn reference resolution.
Maintains execution state, entity references, and pronouns across conversational turns
for filesystem, browser, media, and third-party plugin capabilities.
"""

from dataclasses import dataclass, field
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from .action_registry import TaskActionResult

logger = logging.getLogger("jarvis.desktop_task.context")


@dataclass
class CreatedEntity:
    """Record of a created task entity (file, folder, tab, document, etc.)."""
    identifier: str
    entity_type: str = "file"  # "folder", "file", "document", "tab", "stream"
    name: str = ""
    parent: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


# Backward-compatible alias
CreatedObject = CreatedEntity


class TaskExecutionContext:
    """
    Capability-agnostic execution context.
    Tracks active targets, entity aliases, step results, and pronouns across turns.
    """

    FOLDER_PRONOUNS = {
        "usme", "isme", "iske andar", "uske andar", "usme hi", "isme hi",
        "inside", "inside it", "in it", "there", "in there", "us folder mein",
        "us folder me", "us folder ke andar", "same folder", "current folder"
    }

    FILE_PRONOUNS = {
        "us file", "us file ko", "us file me", "us file mein", "that file",
        "the file", "this file", "ye file", "same file", "wo file", "woh file"
    }

    def __init__(self, default_base: Optional[str] = None, runtime_context: Optional[Any] = None):
        self.default_base = default_base or ""
        self.runtime_context = runtime_context
        self.active_folder: Optional[str] = self.default_base or None
        self.active_file: Optional[str] = None
        self.active_target: Optional[str] = None
        self.entities: Dict[str, Any] = {}
        self.resolved_paths: Dict[str, str] = {}
        self.created_objects: List[CreatedEntity] = []
        self.previous_step_results: List[TaskActionResult] = []
        self.pending_confirmation: Optional[Dict[str, Any]] = None

        if self.default_base:
            self.resolved_paths["desktop"] = self.default_base
            self.resolved_paths["base"] = self.default_base

    def set_entity(self, key: str, value: Any) -> None:
        """Stores a capability-agnostic contextual entity."""
        clean_k = key.strip().lower()
        self.entities[clean_k] = value

    def get_entity(self, key: str, default: Any = None) -> Any:
        """Retrieves a stored contextual entity."""
        return self.entities.get(key.strip().lower(), default)

    def update_active_folder(self, path: str) -> None:
        """Update active folder and register alias."""
        abs_p = os.path.abspath(path) if path else ""
        self.active_folder = abs_p
        self.active_target = abs_p
        if abs_p:
            base_name = os.path.basename(abs_p).lower()
            if base_name:
                self.resolved_paths[base_name] = abs_p
                self.resolved_paths[f"{base_name} folder"] = abs_p
            logger.info("CONTEXT: active_folder updated to '%s'", abs_p)

    def update_active_file(self, path: str) -> None:
        """Update active file, its parent folder, and register alias."""
        abs_p = os.path.abspath(path) if path else ""
        self.active_file = abs_p
        self.active_target = abs_p
        if abs_p:
            parent = os.path.dirname(abs_p)
            if parent:
                self.update_active_folder(parent)
            base_name = os.path.basename(abs_p).lower()
            if base_name:
                self.resolved_paths[base_name] = abs_p
                self.resolved_paths[f"{base_name} file"] = abs_p
            if self.runtime_context and hasattr(self.runtime_context, "desktop"):
                self.runtime_context.desktop.last_file = os.path.basename(abs_p)
                self.runtime_context.desktop.last_file_path = abs_p
                self.runtime_context.desktop.target_type = "file"
            logger.info("CONTEXT: active_file updated to '%s'", abs_p)

    def record_created(self, path: str, is_dir: bool = False, entity_type: Optional[str] = None) -> None:
        """Record newly created task object."""
        abs_p = os.path.abspath(path) if path else ""
        name = os.path.basename(abs_p) if abs_p else ""
        parent = os.path.dirname(abs_p) if abs_p else ""
        etype = entity_type or ("folder" if is_dir else "file")
        entity = CreatedEntity(
            identifier=abs_p,
            entity_type=etype,
            name=name,
            parent=parent
        )
        self.created_objects.append(entity)
        if is_dir or etype == "folder":
            self.update_active_folder(abs_p)
        else:
            self.update_active_file(abs_p)

    def resolve_reference(self, reference: str, target_type: str = "any") -> Optional[str]:
        """Resolve a natural language reference or pronoun to a contextual path/entity."""
        ref = reference.strip().lower()
        if not ref:
            return self.active_folder or self.default_base or None

        # Clean common Hindi / Hinglish postpositions
        cleaned_ref = re.sub(
            r"\b(?:pe|par|per|me|mein|ke\s+andar|ke\s+under|ke\s+bheetar|ko|se)\b",
            "",
            ref,
            flags=re.IGNORECASE
        ).strip()

        # 1. Known special system keywords
        if cleaned_ref in ("desktop", "on desktop", "desktop pe", "desktop par"):
            if "desktop" in self.resolved_paths:
                return self.resolved_paths["desktop"]

        # 2. File pronoun matches
        if any(p in ref for p in self.FILE_PRONOUNS):
            if self.active_file:
                return self.active_file
            if self.runtime_context and hasattr(self.runtime_context, "desktop") and getattr(self.runtime_context.desktop, "last_file_path", None):
                return self.runtime_context.desktop.last_file_path

        # 3. Folder pronoun matches
        if any(p in ref for p in self.FOLDER_PRONOUNS):
            if target_type == "file" and self.active_file:
                return self.active_file
            if self.active_folder:
                return self.active_folder
            if self.active_file:
                return os.path.dirname(self.active_file)
            if self.runtime_context and hasattr(self.runtime_context, "desktop") and getattr(self.runtime_context.desktop, "last_file_path", None):
                return os.path.dirname(self.runtime_context.desktop.last_file_path)
            return self.default_base or None

        # 4. Resolved aliases dictionary lookup
        if cleaned_ref in self.resolved_paths:
            return self.resolved_paths[cleaned_ref]

        # Strip "folder" or "file" suffix for lookup (e.g. "test folder" -> "test")
        norm_key = re.sub(r"\b(?:folder|directory|dir|file|document)\b", "", cleaned_ref).strip()
        if norm_key in self.resolved_paths:
            return self.resolved_paths[norm_key]

        # 5. Check if matches active folder or file name directly
        if self.active_folder and os.path.basename(self.active_folder).lower() == norm_key:
            return self.active_folder
        if self.active_file and os.path.basename(self.active_file).lower() == norm_key:
            return self.active_file

        # 6. Fallback: if user specified a name, construct path inside active_folder or default_base
        base = self.active_folder or self.default_base
        if base and norm_key:
            return os.path.join(base, norm_key)

        return None

    def clear(self) -> None:
        """Reset context state."""
        self.active_folder = self.default_base or None
        self.active_file = None
        self.active_target = None
        self.entities.clear()
        self.resolved_paths.clear()
        if self.default_base:
            self.resolved_paths["desktop"] = self.default_base
            self.resolved_paths["base"] = self.default_base
        self.created_objects.clear()
        self.previous_step_results.clear()
        self.pending_confirmation = None


# Backward-compatible class alias
DesktopExecutionContext = TaskExecutionContext
