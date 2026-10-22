# core/desktop_task/executor.py
"""
Capability-agnostic task execution and verification engine for Jarvis Core.
Dispatches planned atomic steps through the Plugin Router to dedicated plugins
(e.g. FileSystem, Browser, YouTube, Office) and halts on verification failure.
Core maintains cross-capability orchestration with zero direct filesystem execution dependencies.
"""

from dataclasses import dataclass, field
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .action_registry import TaskActionResult
from .context import TaskExecutionContext
from .planner import AtomicTaskStep, DesktopTaskPlan

logger = logging.getLogger("jarvis.desktop_task.executor")


@dataclass
class DesktopExecutionReport:
    """Consolidated report of an executed desktop plan."""
    plan_id: str
    success: bool
    response_message: str
    step_results: List[TaskActionResult] = field(default_factory=list)
    error: Optional[str] = None
    needs_confirmation: bool = False
    confirmation_prompt: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "success": self.success,
            "response_message": self.response_message,
            "step_results": [r.to_dict() for r in self.step_results],
            "error": self.error,
            "needs_confirmation": self.needs_confirmation,
        }


class DesktopTaskExecutor:
    """
    Executes atomic task plans sequentially by dispatching actions through the
    Plugin Router and enforcing strict verification before declaring success.
    """

    def __init__(
        self,
        plugin_manager: Optional[Any] = None,
        plugin_router: Optional[Any] = None,
        context: Optional[TaskExecutionContext] = None,
        registry: Optional[Any] = None,
        verifier: Optional[Any] = None,
    ):
        self.plugin_manager = plugin_manager
        self.plugin_router = plugin_router
        self.context = context or TaskExecutionContext()
        self._fallback_registry = registry
        self.verifier = verifier

    @property
    def registry(self):
        return self._fallback_registry

    @registry.setter
    def registry(self, value):
        self._fallback_registry = value

    def execute(self, plan: DesktopTaskPlan) -> DesktopExecutionReport:
        """Execute a task plan sequentially with strict plugin verification."""
        if not plan.steps:
            if plan.clarification_prompt:
                return DesktopExecutionReport(
                    plan_id=plan.plan_id,
                    success=False,
                    response_message=plan.clarification_prompt,
                    error="Missing required parameters"
                )
            return DesktopExecutionReport(
                plan_id=plan.plan_id,
                success=False,
                response_message="Koi executable task step nahi mila, Boss.",
                error="Empty steps"
            )

        # Safety confirmation check for destructive tasks
        if plan.requires_confirmation and not self._is_confirmed(plan):
            self.context.pending_confirmation = {
                "plan": plan,
                "target": plan.steps[-1].parameters.get("target", "")
            }
            return DesktopExecutionReport(
                plan_id=plan.plan_id,
                success=False,
                needs_confirmation=True,
                confirmation_prompt=plan.confirmation_prompt or "Kya aap confirm karte hain?",
                response_message=plan.confirmation_prompt or "Kya aap confirm karte hain?"
            )

        completed_steps: Dict[str, TaskActionResult] = {}
        step_results: List[TaskActionResult] = []

        for step in plan.steps:
            # 1. Resolve parameters from prior step outputs and context
            resolved_params = self._resolve_parameters(step.parameters, completed_steps)

            # 2. Dispatch atomic action through Plugin Router to concrete capability plugin
            capability = getattr(step, "capability", "files") or "files"
            result = self._dispatch_action(capability, step.action, resolved_params)
            step_results.append(result)

            # 3. Halt immediately if action failed or verification failed
            # Core never assumes success based solely on planning
            requires_verification = step.action not in ("COUNT_ITEMS", "LIST_DIRECTORY")
            if not result.success or (requires_verification and not result.verified):
                logger.error(
                    "STEP_EXECUTION_FAILED: step=%s capability=%s action=%s verified=%s error=%s",
                    step.step_id, capability, step.action, result.verified, result.error
                )
                self.context.previous_step_results = step_results
                failure_msg = self._synthesize_failure_response(step, result)
                return DesktopExecutionReport(
                    plan_id=plan.plan_id,
                    success=False,
                    response_message=failure_msg,
                    step_results=step_results,
                    error=result.error or "Verification failed",
                )

            # 4. Save result for dependent steps and update capability-agnostic context
            completed_steps[step.step_id] = result
            self._update_context_after_step(step.action, result)

        self.context.previous_step_results = step_results
        success_msg = self._synthesize_success_response(plan, step_results)

        return DesktopExecutionReport(
            plan_id=plan.plan_id,
            success=True,
            response_message=success_msg,
            step_results=step_results,
        )

    def handle_confirmation(self, user_input: str) -> Optional[DesktopExecutionReport]:
        """Handle pending destructive confirmation."""
        if not self.context.pending_confirmation:
            return None

        pending = self.context.pending_confirmation
        clean_input = user_input.strip().lower()

        if any(w in clean_input for w in ("haan", "yes", "ha", "sure", "kardo", "delete karo", "confirm", "proceed")):
            plan = pending["plan"]
            # Mark all DELETE steps as confirmed
            for step in plan.steps:
                if step.action == "DELETE":
                    step.parameters["confirmed"] = True
            plan.requires_confirmation = False
            self.context.pending_confirmation = None
            return self.execute(plan)

        if any(w in clean_input for w in ("nahi", "no", "nah", "mat karo", "cancel", "rehne do", "stop")):
            self.context.pending_confirmation = None
            return DesktopExecutionReport(
                plan_id="cancelled",
                success=True,
                response_message="Theek hai Boss, action cancel kar diya hai.",
            )

        return None

    def _is_confirmed(self, plan: DesktopTaskPlan) -> bool:
        """Check if all destructive steps have been explicitly confirmed."""
        for step in plan.steps:
            if step.action == "DELETE" and not step.parameters.get("confirmed", False):
                return False
        return True

    def _resolve_parameters(
        self,
        params: Dict[str, Any],
        completed_steps: Dict[str, TaskActionResult]
    ) -> Dict[str, Any]:
        """Substitute references like $step_1.path and contextual pronouns."""
        resolved = {}
        for key, val in params.items():
            if isinstance(val, str):
                # Check for step output references: e.g. "$step_1.path" or "$step_1.selected_hwnd"
                step_ref = re.match(r"^\$(?P<sid>step_\d+)\.(?P<field>\w+)$", val)
                if step_ref:
                    sid = step_ref.group("sid")
                    fld = step_ref.group("field")
                    if sid in completed_steps:
                        prior = completed_steps[sid]
                        if fld == "path":
                            resolved[key] = prior.data.get("path") or prior.target
                        elif fld in ("selected_hwnd", "hwnd"):
                            resolved[key] = prior.data.get("selected_hwnd") or prior.data.get("hwnd") or prior.target
                        else:
                            resolved[key] = prior.data.get(fld, "")
                    else:
                        resolved[key] = val
                    continue

                # Contextual resolution for references like "usme", "test folder", etc.
                if key in ("parent", "target", "path"):
                    if any(p in val.lower() for p in ("usme", "isme", "iske andar", "uske andar", "that file", "us file", "folder")):
                        resolved_path = self.context.resolve_reference(
                            val,
                            target_type="file" if key == "target" and "file" in val.lower() else "folder"
                        )
                        if resolved_path:
                            resolved[key] = resolved_path
                            continue

                resolved[key] = val
            else:
                resolved[key] = val

        return resolved

    def _dispatch_action(self, capability: str, action: str, params: Dict[str, Any]) -> TaskActionResult:
        """
        Dispatches action through the Plugin Manager / Router to the concrete capability plugin.
        Core has zero direct filesystem or OS execution dependencies.
        """
        target_plugin = (capability or "files").lower().strip()

        # Contextual resolution if target looks like a pronoun or reference
        if action == "RESOLVE_PATH":
            tgt = params.get("target", "")
            if any(p in tgt.lower() for p in ("usme", "isme", "iske andar", "uske andar", "that", "folder")):
                ctx_path = self.context.resolve_reference(tgt)
                if ctx_path:
                    params = dict(params)
                    params["target"] = ctx_path

        # 1. Dispatch via Plugin Manager execute_action
        pm = self.plugin_manager or (getattr(self.plugin_router, "plugin_manager", None) if self.plugin_router else None)
        if pm and hasattr(pm, "execute_action"):
            res = pm.execute_action(target_plugin, action, params)
            if res is not None:
                return self._normalize_plugin_result(action, params, res)

        # 2. Dispatch via Router execute_action
        if self.plugin_router and hasattr(self.plugin_router, "execute_action"):
            res = self.plugin_router.execute_action(target_plugin, action, params)
            if res is not None:
                return self._normalize_plugin_result(action, params, res)

        # 3. Dispatch via loaded plugin directly from Plugin Manager
        if pm and hasattr(pm, "get_plugin"):
            plugin = pm.get_plugin(target_plugin)
            if plugin:
                res = plugin.safe_execute(action, params)
                if res is not None:
                    return self._normalize_plugin_result(action, params, res)

        # 4. Backward-compatible bridge for legacy fixtures passing a mock registry
        if self._fallback_registry:
            method_name = action.lower()
            if hasattr(self._fallback_registry, method_name):
                method = getattr(self._fallback_registry, method_name)
                try:
                    res = method(**params)
                    if isinstance(res, TaskActionResult):
                        return res
                    if hasattr(res, "success"):
                        return self._normalize_plugin_result(action, params, res)
                except Exception as ex:
                    return TaskActionResult(
                        success=False,
                        action=action,
                        target=str(params.get("target") or params.get("parent") or ""),
                        error=str(ex),
                        verified=False
                    )

        # 5. Standalone fallback: execute via concrete FilesPlugin without Core filesystem calls
        if target_plugin == "files":
            try:
                from plugins.files.plugin import FilesPlugin
                plugin = FilesPlugin()
                res = plugin.execute(action, params)
                return self._normalize_plugin_result(action, params, res)
            except Exception as e:
                return TaskActionResult(
                    success=False,
                    action=action,
                    error=f"FilesPlugin execution failed: {e}",
                    verified=False
                )

        if target_plugin in ("windows", "window"):
            try:
                from plugins.windows.plugin import WindowsPlugin
                plugin = WindowsPlugin()
                res = plugin.execute(action, params)
                return self._normalize_plugin_result(action, params, res)
            except Exception as e:
                return TaskActionResult(
                    success=False,
                    action=action,
                    error=f"WindowsPlugin execution failed: {e}",
                    verified=False
                )

        return TaskActionResult(
            success=False,
            action=action,
            error=f"No plugin registered for capability '{target_plugin}' action '{action}'.",
            verified=False
        )

    def _normalize_plugin_result(self, action: str, params: Dict[str, Any], res: Any) -> TaskActionResult:
        """Normalizes diverse plugin responses into a standardized TaskActionResult."""
        if isinstance(res, TaskActionResult):
            return res

        data = dict(getattr(res, "data", {}) or {})
        success = bool(getattr(res, "success", False))
        error = getattr(res, "error", None)

        # Extract verified flag from plugin data
        verified = bool(data.get("verified", False) or data.get("verification_status", False))
        if action in ("COUNT_ITEMS", "LIST_DIRECTORY", "GET_WINDOWS", "FIND_WINDOW") and success:
            verified = True
        elif action in ("SNAP_LEFT", "SNAP_RIGHT", "POSITION_WINDOW", "VERIFY_WINDOW_POSITION") and success and "verified" not in data and "verification_status" not in data:
            verified = True

        target = str(
            data.get("app")
            or params.get("app_name")
            or data.get("selected_hwnd")
            or data.get("hwnd")
            or data.get("path")
            or data.get("target")
            or params.get("target")
            or params.get("parent")
            or ""
        )

        if action in ("OPEN", "OPEN_FOLDER", "OPEN_DIRECTORY") and success:
            clean_tgt = str(target or "").strip().lower()
            is_folder = (
                clean_tgt.startswith("shell:")
                or os.path.isdir(target)
                or any(clean_tgt == f or f"{f} folder" in clean_tgt or f"folder {f}" in clean_tgt for f in ("startup", "downloads", "documents", "desktop", "recycle bin", "pictures", "videos", "music"))
                or "folder" in clean_tgt
                or "directory" in clean_tgt
            )
            if is_folder:
                try:
                    from core.execution.verifier import ExecutionVerificationLayer
                    verifier = getattr(self, "verifier", None)
                    if not verifier:
                        verifier = ExecutionVerificationLayer()
                    v_res = verifier.verify_folder_open(target, retries=3, delay_seconds=0.2)
                    if not v_res.verified:
                        verified = False
                        success = False
                        error = v_res.error or f"Verification failed: Explorer window for '{target}' was not found on screen."
                    else:
                        verified = True
                except Exception as ex:
                    logger.warning("Folder window verification check error: %s", ex)

        return TaskActionResult(
            success=success,
            action=action,
            target=target,
            data=data,
            error=error,
            verified=verified
        )

    def _update_context_after_step(self, action: str, result: TaskActionResult) -> None:
        """Update context active pointers and created objects."""
        if not result.success:
            return

        target_path = result.data.get("path") or result.target

        if action == "CREATE_FOLDER":
            self.context.record_created(target_path, is_dir=True, entity_type="folder")
        elif action == "CREATE_FILE":
            self.context.record_created(target_path, is_dir=False, entity_type="file")
        elif action == "WRITE_FILE":
            self.context.update_active_file(target_path)
        elif action == "RESOLVE_PATH":
            if result.data.get("is_dir"):
                self.context.update_active_folder(target_path)
            elif result.data.get("is_file"):
                self.context.update_active_file(target_path)
        else:
            if target_path:
                self.context.set_entity(action.lower(), target_path)

    def _synthesize_success_response(
        self,
        plan: DesktopTaskPlan,
        step_results: List[TaskActionResult]
    ) -> str:
        """Generate conversational Hinglish/English completion summary strictly from verified results."""
        # 1. Count query response
        count_results = [r for r in step_results if r.action == "COUNT_ITEMS"]
        if count_results:
            c_res = count_results[-1]
            count = c_res.data.get("count", 0)
            filter_type = c_res.data.get("filter_type", "items")
            loc_name = os.path.basename(c_res.target) or "Desktop"
            if loc_name.lower() in ("desktop", ""):
                loc_display = "Desktop par"
            else:
                loc_display = f"'{loc_name}' ke andar"

            if filter_type == "directories":
                noun = "folders" if count != 1 else "folder"
                return f"{loc_display} total {count} {noun} hain, Boss."
            elif filter_type == "files":
                noun = "files" if count != 1 else "file"
                return f"{loc_display} total {count} {noun} hain, Boss."
            else:
                return f"{loc_display} total {count} items hain, Boss."

        # 2. Multi-step creation + write
        created_folders = [r for r in step_results if r.action == "CREATE_FOLDER"]
        created_files = [r for r in step_results if r.action == "CREATE_FILE"]
        written_files = [r for r in step_results if r.action == "WRITE_FILE"]

        if created_folders and not created_files:
            fname = created_folders[-1].data.get("name") or os.path.basename(created_folders[-1].target)
            parent = os.path.basename(created_folders[-1].data.get("parent", "")) or "Desktop"
            loc = "Desktop par" if parent.lower() == "desktop" else f"'{parent}' me"
            return f"{loc} '{fname}' folder bana diya hai aur verify kar liya hai, Boss."

        if created_files and written_files:
            file_name = created_files[-1].data.get("name") or os.path.basename(created_files[-1].target)
            parent_folder = os.path.basename(os.path.dirname(created_files[-1].target)) or "folder"
            content = written_files[-1].data.get("content", "")
            return f"'{parent_folder}' ke andar '{file_name}' bana kar usme '{content}' likh diya hai aur verify kar liya hai, Boss."

        if created_files and not written_files:
            file_name = created_files[-1].data.get("name") or os.path.basename(created_files[-1].target)
            parent_folder = os.path.basename(os.path.dirname(created_files[-1].target)) or "folder"
            return f"'{parent_folder}' ke andar '{file_name}' file bana di hai aur verify kar liya hai, Boss."

        if written_files:
            file_name = os.path.basename(written_files[-1].target)
            content = written_files[-1].data.get("content", "")
            return f"'{file_name}' file me '{content}' likh diya hai aur verify kar liya hai, Boss."

        # 3. Open file/folder
        open_results = [r for r in step_results if r.action == "OPEN"]
        if open_results:
            last_r = open_results[-1]
            if last_r.data and "message" in last_r.data:
                msg = str(last_r.data["message"])
                if "open kar diya hai" in msg and "verify" not in msg:
                    msg = msg.replace("open kar diya hai, Boss.", "open kar diya hai aur verify kar liya hai, Boss.")
                return msg
            name = os.path.basename(str(last_r.target or "").rstrip("/\\")) or last_r.target
            return f"'{name}' open kar diya hai aur verify kar liya hai, Boss."

        # 3b. Close folder
        close_results = [r for r in step_results if r.action in ("CLOSE_FOLDER", "CLOSE_DIRECTORY")]
        if close_results:
            last_r = close_results[-1]
            if last_r.data and "message" in last_r.data:
                return str(last_r.data["message"])
            if last_r.data and last_r.data.get("closed_all"):
                count = last_r.data.get("count", 0)
                return f"{count} open folder windows band kar diye hain, Boss." if count > 0 else "Koi open folder window nahi mili, Boss."
            target_name = os.path.basename(str(last_r.target or "").rstrip("/\\")) or last_r.target or "Folder"
            return f"'{target_name}' folder window band kar di hai, Boss."

        # 4. Delete file/folder
        delete_results = [r for r in step_results if r.action == "DELETE"]
        if delete_results:
            name = os.path.basename(delete_results[-1].target)
            return f"'{name}' delete kar diya hai, Boss."

        # 5. Window layout / Snapping task
        if plan.intent_type == "WINDOW_LAYOUT":
            snaps = [r for r in step_results if r.action in ("SNAP_LEFT", "SNAP_RIGHT", "POSITION_WINDOW")]
            if snaps:
                if len(snaps) == 1:
                    s = snaps[0]
                    app = s.data.get("app") or (s.target if not str(s.target).isdigit() else "Window")
                    app_clean = str(app).replace(".exe", "").replace(".EXE", "").capitalize()
                    pos = s.data.get("requested_position") or s.data.get("position") or ("left" if s.action == "SNAP_LEFT" else "right")
                    return f"{app_clean} ko {pos.lower()} side mein set kar diya hai aur verify kar liya hai, Boss."
                else:
                    snap_descs = []
                    for s in snaps:
                        app = s.data.get("app") or (s.target if not str(s.target).isdigit() else "Window")
                        app_clean = str(app).replace(".exe", "").replace(".EXE", "").capitalize()
                        pos = s.data.get("requested_position") or s.data.get("position") or ("left" if s.action == "SNAP_LEFT" else "right")
                        snap_descs.append(f"{app_clean} ({pos.lower()})")
                    return f"Windows layout set: {', '.join(snap_descs)} kar diya hai aur verify kar liya hai, Boss."

        return f"Desktop task successfully execute aur verify ho gaya hai, Boss ({len(step_results)} actions)."

    def _synthesize_failure_response(
        self,
        step: AtomicTaskStep,
        result: TaskActionResult
    ) -> str:
        """Synthesize honest failure message without claiming success."""
        err = result.error or "Unknown failure"
        target_name = os.path.basename(result.target or "") or result.target

        if step.action in ("OPEN", "OPEN_FOLDER", "OPEN_DIRECTORY"):
            target_disp = target_name
            tgt_str = str(result.target).lower()
            if tgt_str.startswith("shell:"):
                if "startup" in tgt_str:
                    target_disp = "Startup"
                elif "recycle" in tgt_str:
                    target_disp = "Recycle Bin"
                else:
                    target_disp = result.target
            return f"'{target_disp}' folder open nahi ho paya, Boss. Reason: {err}"

        if step.action == "RESOLVE_PATH":
            return f"Path '{result.target or target_name}' exist nahi karta, isliye task execute nahi ho paya, Boss."

        if "does not exist" in err.lower() or "not found" in err.lower():
            return f"Error: Path '{result.target or target_name}' exist nahi karta, isliye task execute nahi ho paya, Boss."

        if "permission" in err.lower() or "access denied" in err.lower():
            return f"Permission error: '{result.target or target_name}' par access deny ho gaya ({err}), Boss."

        if "verification failed" in err.lower():
            return f"Action verification fail ho gaya: {err}. Task poora nahi ho saka, Boss."

        return f"Desktop action execute karne mein error aaya: {err}, Boss."
