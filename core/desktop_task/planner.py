# core/desktop_task/planner.py
"""Desktop task planner and step decomposition pipeline."""

from dataclasses import dataclass, field
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple
from .context import DesktopExecutionContext

logger = logging.getLogger("jarvis.desktop_task.planner")


@dataclass
class AtomicTaskStep:
    """Atomic step in a multi-capability task plan."""
    step_id: str
    action: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    description: str = ""
    capability: str = "files"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "capability": self.capability,
            "parameters": dict(self.parameters),
            "depends_on": list(self.depends_on),
            "description": self.description,
        }


@dataclass
class DesktopTaskPlan:
    """Complete plan with decomposed steps and verification."""
    raw_query: str
    steps: List[AtomicTaskStep]
    intent_type: str
    requires_confirmation: bool = False
    confirmation_prompt: Optional[str] = None
    missing_slots: List[str] = field(default_factory=list)
    clarification_prompt: Optional[str] = None
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    @property
    def is_executable(self) -> bool:
        return bool(self.steps) and not bool(self.missing_slots)


class DesktopTaskPlanner:
    """Translates natural Hinglish/Hindi/English desktop instructions into atomic steps."""

    CONJUNCTION_SPLIT = re.compile(
        r"\s+(?:aur|and|then|phir|fir|uske\s+baad|\bor\b)\s+|,\s*",
        re.IGNORECASE
    )

    COUNT_QUERY_RE = re.compile(
        r"(?:kitne|kitane|kitni|kitna|how\s+many|count|number\s+of)\s+(?P<what>folder|folders|directory|directories|files?|cheezein|items?)",
        re.IGNORECASE
    )

    CREATE_FOLDER_RE = re.compile(
        r"(?:(?:naam\s+k[aei]\s+)?(?:folder|directory|dir)\s+(?:banao|bana\s+do|bana\s+de|create\s+karo|create|make))|"
        r"(?:(?:banao|bana\s+do|create\s+karo|create|make)\s+(?:ek\s+)?(?:naya\s+)?(?:folder|directory|dir))",
        re.IGNORECASE
    )

    CREATE_FILE_RE = re.compile(
        r"(?:(?:text\s+file|txt\s+file|file|document)\s+(?:banao|bana\s+do|bana\s+de|create\s+karo|create|make))|"
        r"(?:(?:banao|bana\s+do|create\s+karo|create|make)\s+(?:ek\s+)?(?:aur\s+)?(?:text\s+)?file)",
        re.IGNORECASE
    )

    WRITE_TEXT_RE = re.compile(
        r"(?:type\s+karo|likho|likh\s+do|write|type|dalo|daal\s+do)\s*:?[ ]*(.*)|(?:write|type)\s+(.+?)\s+(?:in|into|usme|isme)",
        re.IGNORECASE
    )

    OPEN_RE = re.compile(
        r"(?:open\s+karo|kholo|open|launch)\b",
        re.IGNORECASE
    )

    CLOSE_RE = re.compile(
        r"(?:close\s+karo|band\s+karo|band\s+kar\s+do|band\s+kardo|close|exit|shut)\b",
        re.IGNORECASE
    )

    DELETE_RE = re.compile(
        r"(?:delete\s+karo|delete|hatao|hata\s+do|remove\s+karo|remove|mitau)\b",
        re.IGNORECASE
    )

    FORBIDDEN_WRITE_CONTENT = {
        "usme", "isme", "iske", "uske", "iske andar", "uske andar", "usme hi", "isme hi",
        "it", "in it", "inside", "inside it", "there", "in there",
        "file", "folder", "text", "kuch", "kuch bhi", "something", "content", "data",
        "this", "that", "ye", "yeh", "wo", "woh", "karo", "do", "de", "kardo", "karde"
    }

    def _is_window_layout_query(self, raw: str) -> bool:
        """Determines if the raw query is requesting window snapping or multi-window layouts."""
        lower = raw.lower()
        if any(w in lower for w in ("play", "gaana", "song", "bajao", "chalao video", "movie chalao")):
            return False

        has_pos = any(p in lower for p in ("left", "right", "top", "bottom", "baayein", "daayein", "side by side"))
        apps = ("brave", "chrome", "notepad", "excel", "vlc", "calc", "calculator", "code", "vscode", "browser", "window", "windows")
        has_app = any(a in lower for a in apps)
        return has_pos and has_app

    def can_handle(self, text: str) -> bool:
        """Quickly check if the text matches desktop filesystem or window layout tasks."""
        raw = text.strip().lower()
        if not raw:
            return False

        # Ignore URLs, web addresses, and alias teaching
        if re.search(r"https?://|\bwww\.|alias|website", raw):
            return False

        # Ignore queries that are complex data analysis / calculations / smart brain operations
        analytical_keywords = ("total", "sum", "calculate", "average", "avg", "nikalo", "summarize", "organize", "duplicate", "scan", "report")
        if any(w in raw for w in analytical_keywords):
            return False

        # Check for window layout tasks
        if self._is_window_layout_query(raw):
            return True

        # Check for count queries on desktop/folder
        if self.COUNT_QUERY_RE.search(raw):
            return True

        # Check for folder/file operations
        keywords = (
            "folder", "file", "text file", "directory", "desktop", "downloads", "download", "documents", "document",
            "startup", "pictures", "picture", "photos", "photo", "images", "videos", "video", "movies", "movie", "music", "songs", "song",
            "recycle bin", "trash", "temp", "appdata", "c drive", "d drive", "usme", "iske andar", "subfolder"
        )
        actions = (
            "banao", "bana do", "create", "make", "likho", "type karo", "count", "kitne", "kitane",
            "open", "kholo", "delete", "hatao", "read", "padho", "close", "band karo", "band kar do", "band kardo", "band"
        )
        has_file_ext = bool(re.search(r"\.(?:txt|pdf|docx?|xlsx?|csv|py|json|md|log|png|jpe?g|mp[34]|zip|rar|exe|ini|cfg)\b", raw))
        has_close_all = bool(re.search(r"\b(?:all|saare|sab|sabhi|tamam)\s+(?:open\s+)?folders?\b", raw))
        has_kw = any(k in raw for k in keywords) or has_file_ext or has_close_all
        has_act = any(a in raw for a in actions)

        return has_kw and has_act

    def parse(self, text: str, context: Optional[DesktopExecutionContext] = None) -> Optional[DesktopTaskPlan]:
        """Decompose natural query into an executable DesktopTaskPlan."""
        raw = text.strip()
        if not raw:
            return None

        # 0. Check if this is a window layout / positioning task
        if self._is_window_layout_query(raw):
            layout_plan = self._plan_window_layout(raw, context)
            if layout_plan:
                return layout_plan

        # 1. Check if this is a directory counting query
        count_match = self.COUNT_QUERY_RE.search(raw)
        if count_match:
            return self._plan_count_query(raw, count_match, context)

        # 2. Check if this is a compound multi-step instruction
        clauses = [c.strip() for c in self.CONJUNCTION_SPLIT.split(raw) if c.strip()]
        if len(clauses) > 1:
            multi_plan = self._plan_multi_clause(raw, clauses, context)
            if multi_plan:
                return multi_plan

        # 3. Single-step parsing
        return self._plan_single_clause(raw, context)

    def _plan_window_layout(
        self,
        raw: str,
        context: Optional[DesktopExecutionContext]
    ) -> Optional[DesktopTaskPlan]:
        """Plans multi-window layout and snapping tasks decomposed into structured atomic actions."""
        items = []
        try:
            from brain.semantic_parser import HinglishNLUParser
            sem_act = HinglishNLUParser._parse_window_layout(raw, raw.lower())
            if sem_act:
                if sem_act.action == "position_window":
                    items = [sem_act.parameters]
                elif sem_act.action == "layout_windows" and "items" in sem_act.parameters:
                    items = sem_act.parameters["items"]
        except Exception:
            pass

        if not items:
            return None

        steps: List[AtomicTaskStep] = []
        step_idx = 1

        for it in items:
            app_name = it.get("app_name", "current")
            pos = str(it.get("position", "left")).lower()
            launch = bool(it.get("launch_if_needed", False))

            find_step = AtomicTaskStep(
                step_id=f"step_{step_idx}",
                action="FIND_WINDOW",
                capability="windows",
                parameters={"app_name": app_name, "prefer_active": True},
                description=f"Find and select best window for '{app_name}'"
            )
            steps.append(find_step)
            find_id = find_step.step_id
            step_idx += 1

            snap_action = "SNAP_LEFT" if pos in ("left", "baayein") else ("SNAP_RIGHT" if pos in ("right", "daayein") else "POSITION_WINDOW")
            snap_step = AtomicTaskStep(
                step_id=f"step_{step_idx}",
                action=snap_action,
                capability="windows",
                parameters={
                    "hwnd": f"${find_id}.selected_hwnd",
                    "app_name": app_name,
                    "position": pos,
                    "launch_if_needed": launch
                },
                depends_on=[find_id],
                description=f"Snap '{app_name}' to {pos}"
            )
            steps.append(snap_step)
            snap_id = snap_step.step_id
            step_idx += 1

            verify_step = AtomicTaskStep(
                step_id=f"step_{step_idx}",
                action="VERIFY_WINDOW_POSITION",
                capability="windows",
                parameters={
                    "hwnd": f"${find_id}.selected_hwnd",
                    "expected_position": pos
                },
                depends_on=[snap_id],
                description=f"Verify '{app_name}' window position on {pos}"
            )
            steps.append(verify_step)
            step_idx += 1

        return DesktopTaskPlan(
            raw_query=raw,
            steps=steps,
            intent_type="WINDOW_LAYOUT"
        )

    def _plan_count_query(
        self,
        raw: str,
        match: re.Match,
        context: Optional[DesktopExecutionContext]
    ) -> Optional[DesktopTaskPlan]:
        """Plan directory item counting task."""
        what = match.group("what").lower()
        if "folder" in what or "dir" in what:
            filter_type = "directories"
        elif "file" in what:
            filter_type = "files"
        else:
            filter_type = "all"

        # Determine location from text
        target_loc = self._extract_location(raw, context) or "desktop"

        steps = [
            AtomicTaskStep(
                step_id="step_1",
                action="RESOLVE_PATH",
                parameters={"target": target_loc},
                description=f"Resolve path for location '{target_loc}'"
            ),
            AtomicTaskStep(
                step_id="step_2",
                action="COUNT_ITEMS",
                parameters={"path": "$step_1.path", "filter_type": filter_type},
                depends_on=["step_1"],
                description=f"Count {filter_type} inside '{target_loc}'"
            ),
        ]

        return DesktopTaskPlan(
            raw_query=raw,
            steps=steps,
            intent_type="COUNT_ITEMS",
        )

    def _plan_single_clause(
        self,
        raw: str,
        context: Optional[DesktopExecutionContext]
    ) -> Optional[DesktopTaskPlan]:
        """Plan single-clause filesystem task."""
        lower = raw.lower()

        # 1. File creation (Check BEFORE folder creation so 'folder ke under file banao' is treated as file creation)
        is_file_creation = bool(self.CREATE_FILE_RE.search(raw)) or ("file" in lower and any(a in lower for a in ("banao", "bana do", "create", "make")))
        if is_file_creation:
            file_name = self._extract_name(raw, entity_type="file") or "file.txt"
            location = self._extract_location(raw, context) or (context.active_folder if context else "desktop")
            steps = [
                AtomicTaskStep(
                    step_id="step_1",
                    action="RESOLVE_PATH",
                    parameters={"target": location},
                    description=f"Resolve base path for '{location}'"
                ),
                AtomicTaskStep(
                    step_id="step_2",
                    action="CREATE_FILE",
                    parameters={"parent": "$step_1.path", "name": file_name, "file_type": "txt"},
                    depends_on=["step_1"],
                    description=f"Create file '{file_name}'"
                ),
                AtomicTaskStep(
                    step_id="step_3",
                    action="VERIFY",
                    parameters={"verify_type": "file_exists", "target": "$step_2.path"},
                    depends_on=["step_2"],
                    description=f"Verify file '{file_name}' exists"
                ),
            ]
            return DesktopTaskPlan(raw_query=raw, steps=steps, intent_type="CREATE_FILE")

        # 2. Folder creation: e.g. "desktop pe test naam ka folder banao", "iske andar subfolder bana do"
        is_folder_creation = bool(self.CREATE_FOLDER_RE.search(raw)) or any(k in lower for k in ("folder", "subfolder", "directory")) and any(a in lower for a in ("banao", "bana do", "create", "make"))
        if is_folder_creation:
            folder_name = self._extract_name(raw, entity_type="folder")
            if not folder_name:
                # Genuine missing parameter
                return DesktopTaskPlan(
                    raw_query=raw,
                    steps=[],
                    intent_type="CREATE_FOLDER",
                    missing_slots=["folder_name"],
                    clarification_prompt="Folder ka naam kya rakhna hai, Boss?"
                )

            location = self._extract_location(raw, context) or "desktop"
            steps = [
                AtomicTaskStep(
                    step_id="step_1",
                    action="RESOLVE_PATH",
                    parameters={"target": location},
                    description=f"Resolve base path for '{location}'"
                ),
                AtomicTaskStep(
                    step_id="step_2",
                    action="CREATE_FOLDER",
                    parameters={"parent": "$step_1.path", "name": folder_name},
                    depends_on=["step_1"],
                    description=f"Create folder '{folder_name}'"
                ),
                AtomicTaskStep(
                    step_id="step_3",
                    action="VERIFY",
                    parameters={"verify_type": "folder_exists", "target": "$step_2.path"},
                    depends_on=["step_2"],
                    description=f"Verify folder '{folder_name}' exists"
                ),
            ]
            return DesktopTaskPlan(raw_query=raw, steps=steps, intent_type="CREATE_FOLDER")

        # 3. Write text: e.g. "usme Jarvis likho", "us file me hello type karo"
        if any(w in lower for w in ("likho", "type karo", "write", "likh do")) and not any(f in lower for f in ("banao", "create")):
            content = self._extract_write_content(raw)
            if not content:
                return DesktopTaskPlan(
                    raw_query=raw,
                    steps=[],
                    intent_type="WRITE_FILE",
                    missing_slots=["content"],
                    clarification_prompt="File me kya text likhna hai, Boss?"
                )
            target = self._extract_target_file(raw, context)
            steps = [
                AtomicTaskStep(
                    step_id="step_1",
                    action="RESOLVE_PATH",
                    parameters={"target": target},
                    description=f"Resolve target file '{target}'"
                ),
                AtomicTaskStep(
                    step_id="step_2",
                    action="WRITE_FILE",
                    parameters={"target": "$step_1.path", "content": content},
                    depends_on=["step_1"],
                    description=f"Write text to file"
                ),
                AtomicTaskStep(
                    step_id="step_3",
                    action="VERIFY",
                    parameters={"verify_type": "file_content", "target": "$step_1.path", "expected": content},
                    depends_on=["step_2"],
                    description=f"Verify file content contains written text"
                ),
            ]
            return DesktopTaskPlan(raw_query=raw, steps=steps, intent_type="WRITE_FILE")

        # 4a. Close folder: e.g. "close startup folder", "close downloads", "downloads folder band karo", "close all folders", "saare folder band karo", "sabhi open folder close karo"
        is_close_folder = self.CLOSE_RE.search(raw) and (
            "folder" in lower
            or any(d in lower for d in ("all folders", "saare folder", "sab folder", "sabhi folder", "open folder", "open folders", "startup", "downloads", "documents", "pictures", "photos", "videos", "movies", "music", "songs", "recycle bin", "trash", "temp", "appdata", "c drive", "d drive"))
        )
        if is_close_folder:
            close_all = any(w in lower for w in ("all", "saare", "sab", "sabhi", "tamam", "all folders", "saare folders", "open folders", "open folder", "sab folder", "sabhi folder", "saare folder"))
            target = "all" if close_all else (self._extract_location(raw, context) or self._extract_name(raw, entity_type="folder") or "")
            steps = [
                AtomicTaskStep(
                    step_id="step_1",
                    action="CLOSE_FOLDER",
                    capability="files",
                    parameters={"target": target, "close_all": close_all},
                    description="Close all open folders" if close_all else f"Close folder '{target}'"
                )
            ]
            return DesktopTaskPlan(raw_query=raw, steps=steps, intent_type="CLOSE_FOLDER")

        # 4b. Open file/folder: e.g. "us file ko open karo", "test folder open karo", "open startup folder", "open downloads", "open picture"
        daily_folders = (
            "startup", "downloads", "download", "documents", "document", "docs", "desktop",
            "pictures", "picture", "photos", "photo", "images", "image", "videos", "video",
            "movies", "movie", "music", "songs", "song", "recycle bin", "trash", "temp",
            "appdata", "c drive", "d drive"
        )
        is_open_folder_or_file = self.OPEN_RE.search(raw) and not self.CLOSE_RE.search(raw) and (
            any(k in lower for k in ("file", "folder", "usme", "us file", "that"))
            or any(d in lower for d in daily_folders)
            or bool(re.search(r"\.\w{2,4}\b", raw))
        )
        if is_open_folder_or_file:
            target = self._extract_location(raw, context) or self._extract_target_file(raw, context)
            steps = [
                AtomicTaskStep(
                    step_id="step_1",
                    action="RESOLVE_PATH",
                    parameters={"target": target},
                    description=f"Resolve target '{target}' to open"
                ),
                AtomicTaskStep(
                    step_id="step_2",
                    action="OPEN",
                    parameters={"target": "$step_1.path"},
                    depends_on=["step_1"],
                    description=f"Open target"
                ),
            ]
            return DesktopTaskPlan(raw_query=raw, steps=steps, intent_type="OPEN")

        # 5. Delete file/folder: e.g. "test folder delete karo", "to_delete.txt delete karo", "that file delete karo"
        if self.DELETE_RE.search(raw):
            target = self._extract_target_file(raw, context) or self._extract_location(raw, context)
            if not target or target.lower() in ("delete", "karo", "hatao"):
                return DesktopTaskPlan(
                    raw_query=raw,
                    steps=[],
                    intent_type="DELETE",
                    missing_slots=["target"],
                    clarification_prompt="Kaunsa folder ya file delete karni hai, Boss?"
                )
            steps = [
                AtomicTaskStep(
                    step_id="step_1",
                    action="RESOLVE_PATH",
                    parameters={"target": target},
                    description=f"Resolve target path to delete '{target}'"
                ),
                AtomicTaskStep(
                    step_id="step_2",
                    action="DELETE",
                    parameters={"target": "$step_1.path", "confirmed": False},
                    depends_on=["step_1"],
                    description=f"Delete target with safety confirmation"
                ),
                AtomicTaskStep(
                    step_id="step_3",
                    action="VERIFY",
                    parameters={"verify_type": "path_not_exists", "target": "$step_1.path"},
                    depends_on=["step_2"],
                    description=f"Verify target path deleted"
                ),
            ]
            return DesktopTaskPlan(
                raw_query=raw,
                steps=steps,
                intent_type="DELETE",
                requires_confirmation=True,
                confirmation_prompt=f"Kya aap sach me '{target}' ko permanently delete karna chahte hain? (Haan / Nahi)"
            )

        return None

    def _plan_multi_clause(
        self,
        raw: str,
        clauses: List[str],
        context: Optional[DesktopExecutionContext]
    ) -> Optional[DesktopTaskPlan]:
        """Decompose chained multi-step clauses e.g. folder creation + file creation + write."""
        steps: List[AtomicTaskStep] = []
        step_idx = 1
        created_file_step_id: Optional[str] = None
        created_folder_step_id: Optional[str] = None
        plan_missing_content = False

        for clause in clauses:
            cl = clause.strip()
            lower = cl.lower()

            is_file_cl = bool(self.CREATE_FILE_RE.search(cl)) or ("file" in lower and any(a in lower for a in ("banao", "bana do", "create", "make")))
            is_folder_cl = (not is_file_cl) and (bool(self.CREATE_FOLDER_RE.search(cl)) or (any(k in lower for k in ("folder", "subfolder", "directory")) and any(a in lower for a in ("banao", "bana do", "create", "make"))))

            # 1. Folder creation clause
            if is_folder_cl:
                folder_name = self._extract_name(cl, entity_type="folder") or "new_folder"
                loc = self._extract_location(cl, context) or "desktop"

                resolve_step = AtomicTaskStep(
                    step_id=f"step_{step_idx}",
                    action="RESOLVE_PATH",
                    parameters={"target": loc},
                    description=f"Resolve base path for '{loc}'"
                )
                steps.append(resolve_step)
                step_idx += 1

                create_step = AtomicTaskStep(
                    step_id=f"step_{step_idx}",
                    action="CREATE_FOLDER",
                    parameters={"parent": f"${resolve_step.step_id}.path", "name": folder_name},
                    depends_on=[resolve_step.step_id],
                    description=f"Create folder '{folder_name}'"
                )
                steps.append(create_step)
                created_folder_step_id = create_step.step_id
                step_idx += 1

                verify_step = AtomicTaskStep(
                    step_id=f"step_{step_idx}",
                    action="VERIFY",
                    parameters={"verify_type": "folder_exists", "target": f"${create_step.step_id}.path"},
                    depends_on=[create_step.step_id],
                    description=f"Verify folder '{folder_name}' exists"
                )
                steps.append(verify_step)
                step_idx += 1

            # 2. File creation clause: e.g. "test folder ke under ek text file banao"
            elif is_file_cl:
                file_name = self._extract_name(cl, entity_type="file") or "file.txt"
                loc = self._extract_location(cl, context)

                parent_param: str
                depends: List[str] = []
                if loc and loc not in ("usme", "iske andar", "uske andar"):
                    resolve_step = AtomicTaskStep(
                        step_id=f"step_{step_idx}",
                        action="RESOLVE_PATH",
                        parameters={"target": loc},
                        description=f"Resolve folder '{loc}'"
                    )
                    steps.append(resolve_step)
                    parent_param = f"${resolve_step.step_id}.path"
                    depends.append(resolve_step.step_id)
                    step_idx += 1
                elif created_folder_step_id:
                    parent_param = f"${created_folder_step_id}.path"
                    depends.append(created_folder_step_id)
                else:
                    target_ref = "usme" if any(p in cl for p in ("usme", "iske andar")) else (context.active_folder if context else "desktop")
                    resolve_step = AtomicTaskStep(
                        step_id=f"step_{step_idx}",
                        action="RESOLVE_PATH",
                        parameters={"target": target_ref},
                        description=f"Resolve folder '{target_ref}'"
                    )
                    steps.append(resolve_step)
                    parent_param = f"${resolve_step.step_id}.path"
                    depends.append(resolve_step.step_id)
                    step_idx += 1

                create_file_step = AtomicTaskStep(
                    step_id=f"step_{step_idx}",
                    action="CREATE_FILE",
                    parameters={"parent": parent_param, "name": file_name, "file_type": "txt"},
                    depends_on=depends,
                    description=f"Create file '{file_name}'"
                )
                steps.append(create_file_step)
                created_file_step_id = create_file_step.step_id
                step_idx += 1

                verify_file_step = AtomicTaskStep(
                    step_id=f"step_{step_idx}",
                    action="VERIFY",
                    parameters={"verify_type": "file_exists", "target": f"${create_file_step.step_id}.path"},
                    depends_on=[create_file_step.step_id],
                    description=f"Verify file '{file_name}' exists"
                )
                steps.append(verify_file_step)
                step_idx += 1

            # 3. Write text clause: e.g. "usme Jarvis type karo"
            elif any(w in lower for w in ("likho", "type karo", "write", "likh do", "type")):
                content = self._extract_write_content(cl)
                if not content:
                    plan_missing_content = True
                    continue

                target_param: str
                depends = []
                if created_file_step_id:
                    target_param = f"${created_file_step_id}.path"
                    depends.append(created_file_step_id)
                else:
                    loc = self._extract_target_file(cl, context)
                    resolve_step = AtomicTaskStep(
                        step_id=f"step_{step_idx}",
                        action="RESOLVE_PATH",
                        parameters={"target": loc},
                        description=f"Resolve target file '{loc}'"
                    )
                    steps.append(resolve_step)
                    target_param = f"${resolve_step.step_id}.path"
                    depends.append(resolve_step.step_id)
                    step_idx += 1

                write_step = AtomicTaskStep(
                    step_id=f"step_{step_idx}",
                    action="WRITE_FILE",
                    parameters={"target": target_param, "content": content},
                    depends_on=depends,
                    description=f"Write '{content}' into target file"
                )
                steps.append(write_step)
                step_idx += 1

                verify_content_step = AtomicTaskStep(
                    step_id=f"step_{step_idx}",
                    action="VERIFY",
                    parameters={"verify_type": "file_content", "target": target_param, "expected": content},
                    depends_on=[write_step.step_id],
                    description=f"Verify content '{content}' in file"
                )
                steps.append(verify_content_step)
                step_idx += 1

        if not steps:
            if plan_missing_content:
                return DesktopTaskPlan(
                    raw_query=raw,
                    steps=[],
                    intent_type="WRITE_FILE",
                    missing_slots=["content"],
                    clarification_prompt="File me kya text likhna hai, Boss?"
                )
            return None

        missing_slots = []
        clarification_prompt = None
        if plan_missing_content:
            missing_slots.append("content")
            clarification_prompt = "File me kya text type karna hai, Boss?"

        return DesktopTaskPlan(
            raw_query=raw,
            steps=steps,
            intent_type="MULTI_STEP",
            missing_slots=missing_slots,
            clarification_prompt=clarification_prompt,
        )

    def _extract_location(self, text: str, context: Optional[DesktopExecutionContext]) -> Optional[str]:
        """Extract location/parent directory from text."""
        # 1. Check pronouns first: "usme", "iske andar", "uske andar"
        if re.search(r"\b(?:usme|isme|iske\s+andar|uske\s+andar|usme\s+hi|iske\s+under|uske\s+under)\b", text, re.IGNORECASE):
            return "usme"

        # 2. Check Special User Directories (Desktop, Downloads, Documents, Startup, Pictures, Videos, Music, Recycle Bin, Temp, AppData, Drives)
        if re.search(r"\bstartup\b", text, re.IGNORECASE):
            return "startup"
        if re.search(r"\bdesktop\b", text, re.IGNORECASE):
            return "desktop"
        if re.search(r"\bdownloads?\b", text, re.IGNORECASE):
            return "downloads"
        if re.search(r"\bdocuments?\b", text, re.IGNORECASE):
            return "documents"
        if re.search(r"\b(?:pictures?|photos?|images?)\b", text, re.IGNORECASE):
            return "pictures"
        if re.search(r"\b(?:videos?|movies?)\b", text, re.IGNORECASE):
            return "videos"
        if re.search(r"\b(?:music|songs?|audio)\b", text, re.IGNORECASE):
            return "music"
        if re.search(r"\b(?:recycle\s*bin|trash|dustbin)\b", text, re.IGNORECASE):
            return "recycle bin"
        if re.search(r"\b(?:temp|temporary)\b", text, re.IGNORECASE):
            return "temp"
        if re.search(r"\b(?:appdata|roaming)\b", text, re.IGNORECASE):
            return "appdata"
        if re.search(r"\blocal\s*appdata\b", text, re.IGNORECASE):
            return "localappdata"
        if re.search(r"\b(?:c\s*drive|local\s+disk\s*c|c:)\b", text, re.IGNORECASE):
            return "c_drive"
        if re.search(r"\b(?:d\s*drive|local\s+disk\s*d|d:)\b", text, re.IGNORECASE):
            return "d_drive"
        if re.search(r"\b(?:home|user\s+profile|user\s+folder)\b", text, re.IGNORECASE):
            return "home"

        # 3. Check "open/close <folder_name> folder" or "<folder_name> folder kholo/band karo"
        m_action = re.search(r"(?:open|kholo|launch|close|band\s+karo|band\s+kar\s+do|band\s+kardo)\s+(?:the\s+)?(?P<name>[\w\-]+)\s+folder\b", text, re.IGNORECASE)
        if m_action:
            val = m_action.group("name").strip()
            ignored = {"the", "a", "an", "this", "that", "it", "ek", "naya", "new", "all", "saare"}
            if val.lower() not in ignored:
                return val

        m_action_rev = re.search(r"(?P<name>[\w\-]+)\s+folder\s+(?:open|kholo|launch|close|band\s+karo|band\s+kar\s+do|band\s+kardo)\b", text, re.IGNORECASE)
        if m_action_rev:
            val = m_action_rev.group("name").strip()
            ignored = {"the", "a", "an", "this", "that", "it", "ek", "naya", "new", "all", "saare"}
            if val.lower() not in ignored:
                return val

        # 4. Check named folder references: e.g. "ghost_folder_xyz ke under", "test folder ke under", "test folder me"
        m = re.search(r"(?P<name>[\w\-]+)(?:\s+folder)?\s+(?:ke\s+(?:under|andar|bheetar)|me|mein|pe|par)\b", text, re.IGNORECASE)
        if m:
            val = m.group("name").strip()
            ignored = {"desktop", "downloads", "documents", "startup", "pictures", "videos", "music", "ek", "naya", "new", "aur", "or", "usme", "isme", "iske", "uske", "all", "saare"}
            if val.lower() not in ignored:
                return f"{val} folder" if "folder" not in val.lower() else val

        m_rev = re.search(r"(?:in|inside|under)\s+(?P<name>[\w\-]+)(?:\s+folder)?\b", text, re.IGNORECASE)
        if m_rev:
            val = m_rev.group("name").strip()
            ignored = {"desktop", "downloads", "documents", "startup", "pictures", "videos", "music", "the", "a", "an", "this", "that", "it", "all", "saare"}
            if val.lower() not in ignored:
                return f"{val} folder" if "folder" not in val.lower() else val

        return None

    def _extract_name(self, text: str, entity_type: str = "folder") -> Optional[str]:
        """Extract folder or file name from natural text."""
        # e.g. "test naam ka folder", "test name folder"
        m1 = re.search(r"(?P<name>[\w\-.]+)\s+naam\s+k[aei]\s+(?:folder|file|directory)", text, re.IGNORECASE)
        if m1:
            return m1.group("name")

        # e.g. "folder named test", "file named test.txt"
        m2 = re.search(r"(?:folder|file|directory)\s+named\s+(?P<name>[\w\-.]+)", text, re.IGNORECASE)
        if m2:
            return m2.group("name")

        # e.g. "make folder test", "create folder test"
        m3 = re.search(r"(?:folder|directory)\s+(?P<name>[\w\-]+)\s+(?:banao|create|make|karo)", text, re.IGNORECASE)
        if m3 and m3.group("name").lower() not in ("ka", "ke", "ki", "ek", "naya", "new", "aur", "or"):
            return m3.group("name")

        # e.g. "iske andar subfolder bana do" or "subfolder bana do" or "data folder bana do"
        m4 = re.search(r"\b(?P<name>[\w\-]+)\s+(?:folder\s+)?(?:banao|bana\s+do|bana\s+de|create\s+karo|create)\b", text, re.IGNORECASE)
        if m4:
            val = m4.group("name")
            ignored = {"ka", "ke", "ki", "ek", "naya", "new", "aur", "or", "andar", "under", "iske", "usme", "pe", "par", "ko", "folder", "directory", "file"}
            if val.lower() not in ignored:
                return val

        # e.g. "create file test.txt" or "test.txt file banao"
        m5 = re.search(r"(?P<name>[\w\-]+\.[a-zA-Z0-9]+)", text)
        if m5:
            return m5.group("name")

        # If entity is file and user said "ek text file", default can be inferred
        if entity_type == "file" and re.search(r"\b(?:text\s+file|ek\s+text\s+file|txt\s+file)\b", text, re.IGNORECASE):
            return "file.txt"

        return None

    def _clean_write_content(self, val: Optional[str]) -> Optional[str]:
        """Sanitizes extracted content and excludes pronouns and generic placeholders."""
        if not val:
            return None
        val = val.strip(" '\"\t\r\n")
        val = re.sub(r"^(?:aur|or|and|then|phir|fir|usme|isme|iske\s+andar|uske\s+andar|file\s+me|file\s+mein)\s*", "", val, flags=re.IGNORECASE).strip()
        val = re.sub(r"\s*(?:usme|isme|iske\s+andar|uske\s+andar|file\s+me|file\s+mein|in\s+it|into\s+it)$", "", val, flags=re.IGNORECASE).strip()
        val = val.strip(" '\"\t\r\n")
        if not val or val.lower() in self.FORBIDDEN_WRITE_CONTENT:
            return None
        return val

    def _extract_write_content(self, text: str) -> Optional[str]:
        """Extract text to be typed or written into file."""
        # 1. Explicit quotes: e.g. 'Jarvis', "Hello World"
        mq = re.search(r"[\"'](?P<content>[^\"']+)[\"']", text)
        if mq:
            c = self._clean_write_content(mq.group("content"))
            if c:
                return c

        # 2. Colon syntax: e.g. "type karo: Jarvis", "likho: Hello World"
        mc = re.search(r"(?:type\s+karo|likho|likh\s+do|write|type)\s*:\s*(?P<content>.+)", text, re.IGNORECASE)
        if mc:
            c = self._clean_write_content(mc.group("content"))
            if c:
                return c

        # 3. Target/Pronoun + Content + Verb: e.g. "usme Jarvis type karo", "file me Hello likho"
        m_mid = re.search(
            r"(?:usme|isme|file\s+me|file\s+mein|iske\s+andar|uske\s+andar)\s+(?P<content>.+?)\s+(?:type\s+karo|likho|likh\s+do|write|type|daal\s+do|dalo)",
            text,
            re.IGNORECASE
        )
        if m_mid:
            c = self._clean_write_content(m_mid.group("content"))
            if c:
                return c

        # 4. Content + Verb: e.g. "Jarvis type karo", "Hello likho"
        m_end = re.search(
            r"(?P<content>.+?)\s+(?:type\s+karo|likho|likh\s+do|likhna|type\s+kardo|write)$",
            text,
            re.IGNORECASE
        )
        if m_end:
            c = self._clean_write_content(m_end.group("content"))
            if c:
                return c

        # 5. Verb before Content: e.g. "likho Jarvis", "type karo Jarvis", "type Jarvis into file"
        m_verb = re.search(
            r"(?:type\s+karo|likh\s+do|likh\s+de|likho|write|type)\s+(?P<content>.+?)(?:\s+(?:in|into|usme|isme|file\s+me|folder\s+me)|\s*$)",
            text,
            re.IGNORECASE
        )
        if m_verb:
            c = self._clean_write_content(m_verb.group("content"))
            if c:
                return c

        return None

    def fill_slot(
        self,
        plan: DesktopTaskPlan,
        value: str,
        context: Optional[DesktopExecutionContext] = None
    ) -> DesktopTaskPlan:
        """Fills missing slots in an existing DesktopTaskPlan."""
        if not plan.missing_slots:
            return plan

        slot = plan.missing_slots.pop(0)
        cleaned = value.strip()

        if slot == "content":
            extracted = self._extract_write_content(cleaned) or self._clean_write_content(cleaned) or cleaned.strip(" '\"")
            created_file_step = next((s for s in plan.steps if s.action == "CREATE_FILE"), None)
            step_idx = len(plan.steps) + 1

            if created_file_step:
                target_param = f"${created_file_step.step_id}.path"
                depends = [created_file_step.step_id]
            else:
                target_file = self._extract_target_file(plan.raw_query, context)
                resolve_step = AtomicTaskStep(
                    step_id=f"step_{step_idx}",
                    action="RESOLVE_PATH",
                    parameters={"target": target_file},
                    description=f"Resolve target file '{target_file}'"
                )
                plan.steps.append(resolve_step)
                target_param = f"${resolve_step.step_id}.path"
                depends = [resolve_step.step_id]
                step_idx += 1

            write_step = AtomicTaskStep(
                step_id=f"step_{step_idx}",
                action="WRITE_FILE",
                parameters={"target": target_param, "content": extracted},
                depends_on=depends,
                description=f"Write '{extracted}' into target file"
            )
            plan.steps.append(write_step)
            step_idx += 1

            verify_step = AtomicTaskStep(
                step_id=f"step_{step_idx}",
                action="VERIFY",
                parameters={"verify_type": "file_content", "target": target_param, "expected": extracted},
                depends_on=[write_step.step_id],
                description=f"Verify content '{extracted}' in file"
            )
            plan.steps.append(verify_step)
            plan.clarification_prompt = None

        elif slot == "folder_name":
            name = self._extract_name(cleaned, "folder") or cleaned.strip(" '\"")
            step_idx = len(plan.steps) + 1
            loc = self._extract_location(plan.raw_query, context) or "desktop"
            resolve_step = AtomicTaskStep(
                step_id=f"step_{step_idx}",
                action="RESOLVE_PATH",
                parameters={"target": loc},
                description=f"Resolve folder '{loc}'"
            )
            plan.steps.append(resolve_step)
            step_idx += 1

            create_step = AtomicTaskStep(
                step_id=f"step_{step_idx}",
                action="CREATE_FOLDER",
                parameters={"parent": f"${resolve_step.step_id}.path", "name": name},
                depends_on=[resolve_step.step_id],
                description=f"Create folder '{name}'"
            )
            plan.steps.append(create_step)
            step_idx += 1

            verify_step = AtomicTaskStep(
                step_id=f"step_{step_idx}",
                action="VERIFY",
                parameters={"verify_type": "folder_exists", "target": f"${create_step.step_id}.path"},
                depends_on=[create_step.step_id],
                description=f"Verify folder '{name}' exists"
            )
            plan.steps.append(verify_step)
            plan.clarification_prompt = None

        return plan

    def _extract_target_file(self, text: str, context: Optional[DesktopExecutionContext]) -> str:
        """Extract target file for reading/writing/opening."""
        # Check explicit filename with extension first
        m = re.search(r"(?P<name>[\w\-]+\.[a-zA-Z0-9]+)", text)
        if m:
            return m.group("name")

        # Check pronouns
        if any(p in text.lower() for p in ("usme", "isme", "us file", "that file", "the file", "ye file")):
            if context and context.active_file:
                return context.active_file
            return "us file"

        return context.active_file if (context and context.active_file) else "file.txt"
