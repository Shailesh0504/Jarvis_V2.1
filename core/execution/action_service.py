"""ActionPlan execution and task workflow coordination service."""

import logging
from typing import Any, Dict, List, Optional, Tuple
from core.execution.models import ActionPlan, ExecutionResult, ExecutionState

logger = logging.getLogger("jarvis.execution.service")


class ActionService:
    """Authoritative unified execution service for ActionPlans and task workflows."""

    @classmethod
    def execute_action_plan(cls, core: Any, action_plan: Any) -> Any:
        """
        Authoritative unified execution of an ActionPlan.
        Enforces:
        1. PermissionGuard policy validation
        2. Authoritative verified execution (launch_application_verified, open_folder_verified, etc.)
        3. Observable state verification
        4. State update (last_execution_result, active_context)
        5. Telemetry & event notification (execution.completed)
        """
        # 0. Telemetry: Notify planned action
        if hasattr(core, "event_bus") and core.event_bus:
            core.event_bus.emit(
                "action.planned",
                {
                    "plan_id": getattr(action_plan, "plan_id", ""),
                    "action": getattr(action_plan, "action", ""),
                    "target": getattr(action_plan, "target", ""),
                    "target_type": getattr(action_plan, "target_type", "general"),
                    "risk_level": getattr(action_plan, "risk_level", "LOW"),
                    "source": getattr(action_plan, "source", "core"),
                }
            )

        # 1. Permission & Policy Gate
        allowed = True
        reason = ""
        if hasattr(core, "permission_guard") and core.permission_guard:
            val_res = core.permission_guard.validate_action_plan(action_plan)
            if isinstance(val_res, tuple) and len(val_res) == 2:
                allowed, reason = val_res
            else:
                allowed = bool(val_res)
                reason = "Action disallowed by permission policy" if not allowed else ""

            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit(
                    "policy.evaluated",
                    {
                        "plan_id": getattr(action_plan, "plan_id", ""),
                        "allowed": allowed,
                        "reason": reason,
                        "risk_level": getattr(action_plan, "risk_level", "LOW"),
                    }
                )

            if not allowed:
                logger.warning(
                    "ActionPlan %s execution blocked by PermissionGuard: %s",
                    getattr(action_plan, "plan_id", "unknown"), reason
                )
                res = ExecutionResult(
                    success=False,
                    status=ExecutionState.FAILED,
                    requested_action=getattr(action_plan, "action", ""),
                    executed_action=getattr(action_plan, "action", ""),
                    target=getattr(action_plan, "target", ""),
                    action_type=getattr(action_plan, "target_type", "general"),
                    error=f"Permission denied: {reason}",
                    reason="permission_denied"
                )
                core.last_execution_result = res
                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("execution.completed", res.to_dict())
                return res

        # 2. Dispatch based on action & target_type
        action = (getattr(action_plan, "action", "") or "").lower().strip()
        target = (getattr(action_plan, "target", "") or "").strip()
        target_type = (getattr(action_plan, "target_type", "") or "general").lower().strip()
        params = getattr(action_plan, "parameters", {}) or {}

        # 2.0 Pre-Execution Risk Gate via ExecutionStrategyEngine
        if hasattr(core, "execution_strategies") and core.execution_strategies:
            gate_res = core.execution_strategies.check_pre_execution_risk(
                action=action,
                target=target,
                parameters=params
            )
            if gate_res is not None:
                core.last_execution_result = gate_res
                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("execution.completed", gate_res.to_dict())
                return gate_res

        try:
            # A. Application Launch / Focus
            if target_type in ("application", "app") or action in ("launch_app", "open_app"):
                is_new = bool(params.get("is_new", False))
                file_path = params.get("file_path", None)
                res = core.execution_strategies.launch_application_verified(
                    app_name=target,
                    is_new=is_new,
                    file_path=file_path
                )
                if res.success and hasattr(core, "active_context") and core.active_context:
                    core.active_context.set_application(target, action="launch_app")

            # B. Folder Open / Close
            elif target_type == "folder" or action in ("open_folder", "close_folder"):
                if action == "open_folder":
                    res = core.execution_strategies.open_folder_verified(target=target)
                else:
                    files_plugin = (
                        core.plugin_manager.get_plugin("files")
                        if hasattr(core, "plugin_manager") and core.plugin_manager
                        else None
                    )
                    if files_plugin:
                        p_res = files_plugin.execute(action, params)
                        res = ExecutionResult(
                            success=bool(getattr(p_res, "success", True)),
                            status=ExecutionState.SUCCESS if getattr(p_res, "success", True) else ExecutionState.FAILED,
                            requested_action=action,
                            executed_action=action,
                            target=target,
                            action_type="folder",
                            data=getattr(p_res, "data", {}) or {},
                            error=getattr(p_res, "error", None)
                        )
                    else:
                        from plugins.files.operations import FilesystemOperations
                        ops = FilesystemOperations()
                        p_res = ops.close_folder(target=target, close_all=params.get("close_all", False))
                        res = ExecutionResult(
                            success=bool(getattr(p_res, "success", True)),
                            status=ExecutionState.SUCCESS if getattr(p_res, "success", True) else ExecutionState.FAILED,
                            requested_action=action,
                            executed_action=action,
                            target=target,
                            action_type="folder",
                            data=getattr(p_res, "data", {}) or {},
                            error=getattr(p_res, "error", None)
                        )

            # C. Volume Adjustment
            elif target_type == "system_setting" or action in ("set_volume", "adjust_volume"):
                try:
                    vol_val = int(round(float(target or params.get("volume", 50))))
                    from plugins.audio.volume_controller import set_system_volume
                    vol_res = set_system_volume(vol_val)
                    succ = bool(vol_res.get("success", True)) if isinstance(vol_res, dict) else True
                    res = ExecutionResult(
                        success=succ,
                        status=ExecutionState.SUCCESS if succ else ExecutionState.FAILED,
                        requested_action=action,
                        executed_action="set_system_volume",
                        target=str(vol_val),
                        action_type="system_setting",
                        data=vol_res if isinstance(vol_res, dict) else {"result": vol_res}
                    )
                except Exception as vol_err:
                    res = ExecutionResult(
                        success=False,
                        status=ExecutionState.FAILED,
                        requested_action=action,
                        executed_action="set_system_volume",
                        target=target,
                        action_type="system_setting",
                        error=str(vol_err)
                    )

            # D. Media / Music Playback
            elif target_type == "media" or action in ("play_music", "media_play"):
                media_cmd = f"play {target} song" if target else "play music"
                cmd_out = core.process_input(media_cmd, source=getattr(action_plan, "source", "proactive") or "proactive")
                res = ExecutionResult(
                    success=True,
                    status=ExecutionState.SUCCESS,
                    requested_action=action,
                    executed_action="process_input_media",
                    target=target,
                    action_type="media",
                    data={"output": cmd_out}
                )

            # E. Plugin Action Resolver
            elif getattr(action_plan, "resolver", "") == "plugin" and "plugin_name" in params and "action_name" in params:
                p_name = params["plugin_name"]
                a_name = params["action_name"]
                p_params = params.get("parameters", {})
                if hasattr(core, "plugin_manager") and core.plugin_manager:
                    p_res = core.plugin_manager.execute_action(p_name, a_name, p_params)
                    res = ExecutionResult(
                        success=bool(getattr(p_res, "success", True)),
                        status=ExecutionState.SUCCESS if getattr(p_res, "success", True) else ExecutionState.FAILED,
                        requested_action=action,
                        executed_action=f"{p_name}.{a_name}",
                        target=target,
                        action_type="plugin",
                        data=getattr(p_res, "data", {}) or {},
                        error=getattr(p_res, "error", None)
                    )
                else:
                    res = ExecutionResult(
                        success=False,
                        status=ExecutionState.FAILED,
                        requested_action=action,
                        executed_action=f"{p_name}.{a_name}",
                        error="Plugin manager not available"
                    )

            # F. Fallback Command Execution
            else:
                fallback_cmd = params.get("command") or target or action
                cmd_out = core.process_input(fallback_cmd, source=getattr(action_plan, "source", "action_plan") or "action_plan")
                res = ExecutionResult(
                    success=True,
                    status=ExecutionState.SUCCESS,
                    requested_action=action,
                    executed_action="process_input_fallback",
                    target=target,
                    action_type=target_type,
                    data={"output": cmd_out}
                )

        except Exception as exc:
            logger.error("Error executing ActionPlan %s: %s", getattr(action_plan, "plan_id", "unknown"), exc, exc_info=True)
            res = ExecutionResult(
                success=False,
                status=ExecutionState.FAILED,
                requested_action=getattr(action_plan, "action", ""),
                executed_action=getattr(action_plan, "action", ""),
                target=getattr(action_plan, "target", ""),
                action_type=getattr(action_plan, "target_type", "general"),
                error=str(exc)
            )

        core.last_execution_result = res
        if hasattr(core, "event_bus") and core.event_bus:
            core.event_bus.emit("execution.completed", res.to_dict())

        return res

    @classmethod
    def execute_task_workflow(
        cls,
        core: Any,
        goal: str,
        steps: Optional[List[Any]] = None,
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str, Optional[Any]]:
        """Execute a multi-step task workflow via TaskContinuityEngine with step-by-step verification."""
        if not hasattr(core, "task_engine") or not core.task_engine:
            return False, "Task Continuity Engine is not initialized.", None
        return core.task_engine.start_workflow(
            goal=goal,
            steps=steps,
            execution_context=execution_context,
        )
