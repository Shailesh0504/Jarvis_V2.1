# core/desktop_workflow.py
"""Generic natural-language desktop action planning and verified orchestration."""

from dataclasses import dataclass, field
from enum import Enum
import logging
import os
import re
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from plugins.manifest import PluginResult

logger = logging.getLogger("jarvis.desktop_workflow")


class DesktopAction(str, Enum):
    OPEN = "OPEN"
    WAIT_FOR_WINDOW = "WAIT_FOR_WINDOW"
    FOCUS = "FOCUS"
    TYPE = "TYPE"
    CLICK = "CLICK"
    HOTKEY = "HOTKEY"
    WAIT = "WAIT"
    READ_SCREEN = "READ_SCREEN"
    SELECT_TEXT = "SELECT_TEXT"
    PASTE = "PASTE"
    SAVE = "SAVE"
    SEARCH = "SEARCH"
    OPEN_FILE = "OPEN_FILE"


class WorkflowState(str, Enum):
    READY = "READY"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class DesktopActionStep:
    action: DesktopAction
    target: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    timeout_seconds: float = 6.0
    retries: int = 1
    critical: bool = True
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    rollback: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id, "action": self.action.value, "target": self.target,
            "parameters": dict(self.parameters), "depends_on": list(self.depends_on),
            "timeout_seconds": self.timeout_seconds, "retries": self.retries,
        }


@dataclass
class DesktopActionPlan:
    user_query: str
    steps: List[DesktopActionStep]
    target_application: str = ""
    missing_slots: List[str] = field(default_factory=list)
    state: WorkflowState = WorkflowState.READY
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def needs_input(self) -> bool:
        return bool(self.missing_slots)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id, "user_query": self.user_query,
            "target_application": self.target_application,
            "missing_slots": list(self.missing_slots), "state": self.state.value,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass
class DesktopStepResult:
    step_id: str
    action: DesktopAction
    success: bool
    attempts: int = 1
    data: Any = None
    error: Optional[str] = None
    elapsed_ms: float = 0.0


@dataclass
class DesktopWorkflowResult:
    plan_id: str
    state: WorkflowState
    steps: List[DesktopStepResult]
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.state == WorkflowState.COMPLETED


class DesktopActionPlanner:
    """Turns generic English/Hindi/Hinglish sequences into ordered desktop actions."""

    OPEN_PATTERN = re.compile(
        r"^(?:open|launch|start|run)\s+(?P<app>[\w .-]+?)$|^(?P<app_hi>[\w .-]+?)\s+(?:kholo|open\s+karo)$",
        re.IGNORECASE,
    )
    SEPARATOR = re.compile(r"\s+(?:and|then|aur|phir|fir|uske\s+baad)\s+", re.IGNORECASE)
    CANCEL_PATTERN = re.compile(r"^(?:stop|cancel|abort|ruk\s+jao|ruko|band\s+karo|rehne\s+do)$", re.IGNORECASE)

    def parse(self, text: str) -> Optional[DesktopActionPlan]:
        raw = text.strip()
        if not raw or self.CANCEL_PATTERN.fullmatch(raw):
            return None
        clauses = [part.strip(" ,") for part in self.SEPARATOR.split(raw) if part.strip(" ,")]
        if len(clauses) < 2:
            return None
        first = self.OPEN_PATTERN.fullmatch(clauses[0])
        if not first:
            return None
        app = (first.group("app") or first.group("app_hi") or "").strip()
        if not app:
            return None

        steps: List[DesktopActionStep] = []
        open_step = DesktopActionStep(DesktopAction.OPEN, app, {"app_name": app}, retries=1)
        wait_step = DesktopActionStep(DesktopAction.WAIT_FOR_WINDOW, app, depends_on=[open_step.step_id], retries=0)
        focus_step = DesktopActionStep(DesktopAction.FOCUS, app, depends_on=[wait_step.step_id], retries=2)
        steps.extend([open_step, wait_step, focus_step])
        previous = focus_step.step_id
        missing: List[str] = []

        for clause in clauses[1:]:
            action_steps, slot = self._parse_clause(clause, app, previous)
            if slot:
                missing.append(slot)
            if action_steps:
                steps.extend(action_steps)
                previous = action_steps[-1].step_id

        if len(steps) == 3 and not missing:
            return None
        state = WorkflowState.WAITING_FOR_INPUT if missing else WorkflowState.READY
        plan = DesktopActionPlan(raw, steps, app, missing, state)
        logger.info("PLAN_CREATED plan=%s actions=%s missing=%s", plan.plan_id,
                    [step.action.value for step in steps], missing)
        return plan

    def _parse_clause(self, clause: str, app: str, depends_on: str) -> Tuple[List[DesktopActionStep], Optional[str]]:
        cleaned = clause.strip()
        lower = cleaned.lower()
        dependency = [depends_on]

        type_match = re.match(r"^(?:type|write|likho|type\s+karo|ye\s+(?:text\s+)?type\s+karo)\b\s*:?[ ]*(.*)$", cleaned, re.IGNORECASE)
        suffix_write = re.match(r"^(.+?)\s+(?:likho|type\s+karo)$", cleaned, re.IGNORECASE)
        if type_match or suffix_write:
            text = (type_match.group(1) if type_match else suffix_write.group(1)).strip(" :")
            if not text or text.lower() in {"this", "this text", "ye", "ye text", "text", "typing"}:
                return [], "text"
            return [DesktopActionStep(DesktopAction.TYPE, app, {"text": text}, dependency)], None

        if re.fullmatch(r"(?:start\s+typing|type|write|likho|typing\s+start\s+karo|ye\s+text\s+type\s+karo)", lower):
            return [], "text"

        search = re.match(r"^(?:(.+?)\s+)?(?:search|search\s+karo|dhoondo)$", cleaned, re.IGNORECASE)
        search_prefix = re.match(r"^(?:search|search\s+for|dhoondo)\s+(.+)$", cleaned, re.IGNORECASE)
        if search or search_prefix:
            query = (search_prefix.group(1) if search_prefix else search.group(1) or "").strip()
            if not query:
                return [], "query"
            type_step = DesktopActionStep(DesktopAction.TYPE, app, {"text": query}, dependency)
            enter_step = DesktopActionStep(DesktopAction.HOTKEY, app, {"hotkey": "enter"}, [type_step.step_id])
            return [type_step, enter_step], None

        open_file = re.match(r"^(?:open|play|load|khol(?:o)?|chalao)\s+(.+)$", cleaned, re.IGNORECASE)
        if open_file:
            value = open_file.group(1).strip()
            generic = {"file", "a file", "movie", "a movie", "video", "a video", "document", "a document"}
            if value.lower() in generic:
                return [], "file_target"
            hotkey = DesktopActionStep(DesktopAction.HOTKEY, app, {"hotkey": "ctrl+o"}, dependency)
            type_step = DesktopActionStep(DesktopAction.TYPE, app, {"text": value}, [hotkey.step_id])
            enter = DesktopActionStep(DesktopAction.HOTKEY, app, {"hotkey": "enter"}, [type_step.step_id])
            return [hotkey, type_step, enter], None

        if re.fullmatch(r"(?:save|save\s+karo|file\s+save\s+karo)", lower):
            return [DesktopActionStep(DesktopAction.SAVE, app, {}, dependency)], None
        if re.fullmatch(r"(?:select\s+all|sab\s+select\s+karo|text\s+select\s+karo)", lower):
            return [DesktopActionStep(DesktopAction.SELECT_TEXT, app, {}, dependency)], None
        hotkey = re.match(r"^(?:press|hotkey)\s+(.+)$", cleaned, re.IGNORECASE)
        if hotkey:
            return [DesktopActionStep(DesktopAction.HOTKEY, app, {"hotkey": hotkey.group(1)}, dependency)], None
        wait = re.match(r"^(?:wait|ruko)\s*(\d+(?:\.\d+)?)?", lower)
        if wait:
            return [DesktopActionStep(DesktopAction.WAIT, app, {"seconds": float(wait.group(1) or 1)}, dependency)], None
        if re.fullmatch(r"(?:read\s+screen|screen\s+padho)", lower):
            return [DesktopActionStep(DesktopAction.READ_SCREEN, app, {}, dependency)], None
        return [], None

    def fill_slot(self, plan: DesktopActionPlan, value: str) -> DesktopActionPlan:
        if not plan.missing_slots:
            return plan
        slot = plan.missing_slots.pop(0)
        previous = plan.steps[-1].step_id
        cleaned = value.strip()
        if slot == "text":
            plan.steps.append(DesktopActionStep(DesktopAction.TYPE, plan.target_application, {"text": cleaned}, [previous]))
        elif slot == "query":
            typed = DesktopActionStep(DesktopAction.TYPE, plan.target_application, {"text": cleaned}, [previous])
            plan.steps.extend([typed, DesktopActionStep(DesktopAction.HOTKEY, plan.target_application,
                                                        {"hotkey": "enter"}, [typed.step_id])])
        elif slot == "file_target":
            hotkey = DesktopActionStep(DesktopAction.HOTKEY, plan.target_application, {"hotkey": "ctrl+o"}, [previous])
            typed = DesktopActionStep(DesktopAction.TYPE, plan.target_application, {"text": cleaned}, [hotkey.step_id])
            plan.steps.extend([hotkey, typed, DesktopActionStep(DesktopAction.HOTKEY, plan.target_application,
                                                               {"hotkey": "enter"}, [typed.step_id])])
        plan.state = WorkflowState.WAITING_FOR_INPUT if plan.missing_slots else WorkflowState.READY
        return plan


class DesktopWorkflowExecutor:
    """Sequential plugin-backed executor with dependency and window/focus verification."""

    def __init__(self, plugin_manager: Any, event_bus: Any = None,
                 sleep_fn: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.plugin_manager = plugin_manager
        self.event_bus = event_bus
        self.sleep = sleep_fn
        self.clock = clock
        self._cancel = threading.Event()
        self.active_plan_id: Optional[str] = None

    def cancel(self) -> None:
        self._cancel.set()

    def execute(self, plan: DesktopActionPlan) -> DesktopWorkflowResult:
        self._cancel.clear()
        self.active_plan_id = plan.plan_id
        plan.state = WorkflowState.RUNNING
        completed: Dict[str, DesktopStepResult] = {}
        results: List[DesktopStepResult] = []
        try:
            for step in plan.steps:
                if self._cancel.is_set():
                    plan.state = WorkflowState.CANCELLED
                    return DesktopWorkflowResult(plan.plan_id, plan.state, results, "Workflow cancelled by user")
                unmet = [dep for dep in step.depends_on if dep not in completed or not completed[dep].success]
                if unmet:
                    result = DesktopStepResult(step.step_id, step.action, False, error=f"Dependencies not met: {unmet}")
                else:
                    result = self._execute_with_retry(step)
                results.append(result)
                if self._cancel.is_set():
                    plan.state = WorkflowState.CANCELLED
                    return DesktopWorkflowResult(plan.plan_id, plan.state, results, "Workflow cancelled by user")
                if result.success:
                    completed[step.step_id] = result
                elif step.critical:
                    plan.state = WorkflowState.FAILED
                    logger.error("STEP_FAILED plan=%s step=%s action=%s error=%s", plan.plan_id,
                                 step.step_id, step.action.value, result.error)
                    self._rollback(plan, completed)
                    return DesktopWorkflowResult(plan.plan_id, plan.state, results, result.error)
            plan.state = WorkflowState.COMPLETED
            logger.info("WORKFLOW_COMPLETED plan=%s steps=%d", plan.plan_id, len(results))
            self._emit("WORKFLOW_COMPLETED", {"plan_id": plan.plan_id, "steps": len(results)})
            return DesktopWorkflowResult(plan.plan_id, plan.state, results)
        finally:
            self.active_plan_id = None

    def _execute_with_retry(self, step: DesktopActionStep) -> DesktopStepResult:
        started = self.clock()
        last_error = "Unknown failure"
        for attempt in range(1, step.retries + 2):
            if self._cancel.is_set():
                return DesktopStepResult(step.step_id, step.action, False, attempt, error="Cancelled")
            logger.info("STEP_STARTED step=%s action=%s attempt=%d", step.step_id, step.action.value, attempt)
            self._emit("STEP_STARTED", {"step_id": step.step_id, "action": step.action.value, "attempt": attempt})
            result = self._execute_step(step)
            if result.success:
                result.attempts = attempt
                result.elapsed_ms = (self.clock() - started) * 1000
                logger.info("STEP_SUCCESS step=%s action=%s", step.step_id, step.action.value)
                self._emit("STEP_SUCCESS", {"step_id": step.step_id, "action": step.action.value})
                return result
            last_error = result.error or last_error
            if attempt <= step.retries:
                self.sleep(min(0.2 * attempt, 0.5))
        logger.error("STEP_FAILED step=%s action=%s error=%s", step.step_id, step.action.value, last_error)
        self._emit("STEP_FAILED", {"step_id": step.step_id, "action": step.action.value, "error": last_error})
        return DesktopStepResult(step.step_id, step.action, False, step.retries + 1,
                                 error=last_error, elapsed_ms=(self.clock() - started) * 1000)

    def _execute_step(self, step: DesktopActionStep) -> DesktopStepResult:
        action, target = step.action, step.target
        if action == DesktopAction.OPEN:
            return self._plugin_step(step, "windows", "launch_app", {"app_name": target, **step.parameters})
        if action == DesktopAction.WAIT_FOR_WINDOW:
            logger.info("WAITING_FOR_WINDOW target=%s timeout=%.1f", target, step.timeout_seconds)
            self._emit("WAITING_FOR_WINDOW", {"target": target, "timeout": step.timeout_seconds})
            deadline = self.clock() + step.timeout_seconds
            while self.clock() < deadline and not self._cancel.is_set():
                if self._find_windows(target):
                    return DesktopStepResult(step.step_id, action, True, data={"target": target})
                self.sleep(0.1)
            return DesktopStepResult(step.step_id, action, False, error=f"Timed out waiting for '{target}' window")
        if action == DesktopAction.FOCUS:
            result = self._plugin_step(step, "windows", "focus_window", {"app_name": target})
            if result.success and not self._verify_focus(target):
                return DesktopStepResult(step.step_id, action, False, error=f"Wrong window focused; expected '{target}'")
            if result.success:
                logger.info("FOCUS_CHANGED target=%s", target)
                self._emit("FOCUS_CHANGED", {"target": target})
            return result
        if action == DesktopAction.TYPE:
            if not self._verify_focus(target):
                return DesktopStepResult(step.step_id, action, False, error=f"Refusing to type: '{target}' is not focused")
            result = self._plugin_step(step, "automation", "type_text", step.parameters)
            if result.success:
                logger.info("INPUT_TYPED target=%s chars=%d", target, len(step.parameters.get("text", "")))
                self._emit("INPUT_TYPED", {"target": target, "length": len(step.parameters.get("text", ""))})
            return result
        if action == DesktopAction.CLICK:
            return self._plugin_step(step, "automation", "click", step.parameters)
        if action == DesktopAction.HOTKEY:
            if not self._verify_focus(target):
                return DesktopStepResult(step.step_id, action, False, error=f"Refusing hotkey: '{target}' is not focused")
            return self._plugin_step(step, "automation", "press_hotkey", step.parameters)
        if action == DesktopAction.PASTE:
            return self._plugin_step(step, "automation", "paste_text", step.parameters)
        if action == DesktopAction.SELECT_TEXT:
            return self._plugin_step(step, "automation", "press_hotkey", {"hotkey": "ctrl+a"})
        if action == DesktopAction.SAVE:
            return self._plugin_step(step, "automation", "press_hotkey", {"hotkey": "ctrl+s"})
        if action == DesktopAction.READ_SCREEN:
            return self._plugin_step(step, "screen", "take_screenshot", {})
        if action == DesktopAction.WAIT:
            seconds = min(max(float(step.parameters.get("seconds", 1)), 0), step.timeout_seconds)
            self.sleep(seconds)
            return DesktopStepResult(step.step_id, action, True, data={"waited": seconds})
        return DesktopStepResult(step.step_id, action, False, error=f"Unsupported desktop action: {action.value}")

    def _plugin_step(self, step, plugin, action, parameters):
        result: PluginResult = self.plugin_manager.execute_action(plugin, action, parameters)
        return DesktopStepResult(step.step_id, step.action, result.success, data=result.data, error=result.error)

    def _window_manager(self):
        plugin = self.plugin_manager.get_plugin("windows")
        return getattr(plugin, "window_manager", None) if plugin else None

    def _find_windows(self, target: str):
        manager = self._window_manager()
        return manager.find_windows_for_app(target) if manager else []

    def _verify_focus(self, target: str) -> bool:
        manager = self._window_manager()
        if not manager:
            return False
        foreground = manager.get_foreground_window()
        if foreground is None:
            # Headless/mock environments must inject a verifier; real Windows never uses this branch.
            return manager._user32 is None
        matches = manager.find_windows_for_app(target)
        return any(win.hwnd == foreground.hwnd or (win.pid and win.pid == foreground.pid) for win in matches)

    def _rollback(self, plan, completed):
        for step in reversed(plan.steps):
            if step.step_id not in completed or not step.rollback:
                continue
            rollback = step.rollback
            try:
                self.plugin_manager.execute_action(rollback["plugin"], rollback["action"], rollback.get("parameters", {}))
            except Exception:
                logger.exception("Rollback failed for step %s", step.step_id)

    def _emit(self, name: str, data: Dict[str, Any]) -> None:
        if self.event_bus:
            self.event_bus.emit(f"desktop_workflow.{name.lower()}", data=data)


class DesktopWorkflowCoordinator:
    """Owns pending slot-filled plans, desktop filesystem tasks, and connects execution to learning."""

    def __init__(self, plugin_manager=None, event_bus=None, learning_manager=None, task_context=None):
        self.plugin_manager = plugin_manager
        self.planner = DesktopActionPlanner()
        self.executor = DesktopWorkflowExecutor(plugin_manager, event_bus)
        self.learning_manager = learning_manager
        self.pending_plan: Optional[DesktopActionPlan] = None
        self.pending_task_plan: Optional[Any] = None

        # Multi-step desktop filesystem task executor components
        from core.desktop_task.action_registry import FilesystemActionRegistry
        from core.desktop_task.context import DesktopExecutionContext
        from core.desktop_task.executor import DesktopTaskExecutor
        from core.desktop_task.planner import DesktopTaskPlanner

        self.task_context = task_context or DesktopExecutionContext()
        self.task_planner = DesktopTaskPlanner()
        self.task_registry = FilesystemActionRegistry()
        self.task_executor = DesktopTaskExecutor(
            plugin_manager=self.plugin_manager,
            registry=self.task_registry,
            context=self.task_context
        )

    def try_handle(self, text: str) -> Tuple[bool, str, Optional[Any]]:
        raw = text.strip()
        if not raw:
            return False, "", None

        # 1. Check for cancel pattern
        if self.planner.CANCEL_PATTERN.fullmatch(raw):
            if self.pending_plan or self.pending_task_plan or self.executor.active_plan_id or self.task_executor.context.pending_confirmation:
                self.pending_plan = None
                self.pending_task_plan = None
                self.task_executor.context.pending_confirmation = None
                self.executor.cancel()
                return True, "Theek hai yaar, workflow cancel kar diya.", None
            return False, "", None

        # 2. Check for pending destructive action confirmation in task executor
        if self.task_executor.context.pending_confirmation:
            report = self.task_executor.handle_confirmation(raw)
            if report:
                return True, report.response_message, report

        # 2b. Check for pending slot in desktop task plan
        if self.pending_task_plan:
            task_plan = self.task_planner.fill_slot(self.pending_task_plan, text, self.task_context)
            self.pending_task_plan = None
            if task_plan.missing_slots and task_plan.clarification_prompt:
                self.pending_task_plan = task_plan
                return True, task_plan.clarification_prompt, None

            report = self.task_executor.execute(task_plan)
            if self.learning_manager and report.success:
                self._record_task_steps(report)
            return True, report.response_message, report

        # 3. Check for pending slot in window action plan (e.g. "open notepad and start typing" -> next turn "Hello")
        if self.pending_plan:
            plan = self.planner.fill_slot(self.pending_plan, text)
            if plan.needs_input:
                return True, self._question(plan.missing_slots[0]), None
            self.pending_plan = None
            return self._run(plan)

        # 4. Check if this is a desktop filesystem task
        if self.task_planner.can_handle(raw):
            task_plan = self.task_planner.parse(raw, self.task_context)
            if task_plan:
                if task_plan.missing_slots and task_plan.clarification_prompt:
                    self.pending_task_plan = task_plan
                    return True, task_plan.clarification_prompt, None

                report = self.task_executor.execute(task_plan)
                if self.learning_manager and report.success:
                    self._record_task_steps(report)
                return True, report.response_message, report

        # 5. Check if this is a window-action workflow plan (e.g. "open Notepad and type Hello")
        plan = self.planner.parse(text)
        if not plan:
            return False, "", None
        if self.executor.event_bus:
            self.executor.event_bus.emit("desktop_workflow.plan_created", data=plan.to_dict())
        if plan.needs_input:
            self.pending_plan = plan
            return True, self._question(plan.missing_slots[0]), None
        return self._run(plan)

    def _run(self, plan):
        result = self.executor.execute(plan)
        if result.success:
            self._record_safe_steps(plan)
            return True, f"Workflow complete yaar: {plan.target_application} par {len(result.steps)} actions successfully execute hue.", result
        if result.state == WorkflowState.CANCELLED:
            return True, "Theek hai yaar, workflow cancel kar diya.", result
        return True, f"Workflow step fail ho gaya: {result.error}", result

    @staticmethod
    def _question(slot: str) -> str:
        return {"text": "Kya type karna hai?", "query": "Kya search karna hai?",
                "file_target": "Kaunsi file ya media open karni hai?"}.get(slot, f"{slot} batao?")

    def _record_safe_steps(self, plan):
        if not self.learning_manager:
            return
        destructive = {"DELETE", "CLOSE", "SHUTDOWN", "FORMAT", "SAVE"}
        if any(step.action.value in destructive for step in plan.steps):
            return
        for step in plan.steps:
            self.learning_manager.record_action_step(
                plugin="desktop", action=step.action.value.lower(), parameters=step.parameters,
                description=f"{step.action.value} {step.target}".strip(),
            )

    def _record_task_steps(self, report):
        if not self.learning_manager:
            return
        for step in report.step_results:
            if step.action != "DELETE":
                self.learning_manager.record_action_step(
                    plugin="desktop_task",
                    action=step.action.lower(),
                    parameters=step.data,
                    description=f"{step.action} {step.target}".strip(),
                )

