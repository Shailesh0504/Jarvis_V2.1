# core/execution/semantic_executor.py
"""
Semantic Action Executor for Jarvis V2.1.
Encapsulates execution of parsed SemanticAction instances (from HinglishNLUParser)
including universal window controls, application launches, folder operations,
browser/website navigation, activity queries, security controls, and plugin routing.
"""

import json
import logging
import re
import threading
import time
from typing import Any, Optional, Tuple

from core.intent import Intent, IntentType
from core.state import SystemState
from core.execution.outcome_hook import ExecutionOutcomeHook

logger = logging.getLogger("jarvis.execution.semantic_executor")


class SemanticActionExecutor:
    """
    Decoupled execution engine for parsed SemanticAction objects.
    Coordinates target engine, plugins, dialog manager, context, and feedback.
    """

    UNIVERSAL_WINDOW_ACTIONS = {
        "focus_window": "focus",
        "close_app": "close",
        "maximize_window": "maximize",
        "minimize_window": "minimize",
        "restore_window": "restore",
    }

    def __init__(self, core: Any = None):
        self.core = core

    def execute(
        self,
        semantic_act: Any,
        turn: Any,
        start_time: float,
        source: str = "user",
        ctx_key: Optional[str] = None,
        lce_tokens: Optional[list] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Executes a parsed SemanticAction.
        Returns:
            (handled: bool, response_message: Optional[str])
        """
        if not semantic_act or not self.core:
            return False, None

        # 1. Universal Window Actions
        if (
            semantic_act.service == "windows"
            and semantic_act.action in self.UNIVERSAL_WINDOW_ACTIONS
        ):
            return True, self._handle_window_action(semantic_act, turn)

        # 2. Jarvis Restart
        if semantic_act.intent == "JARVIS_RESTART" or semantic_act.action in {
            "restart_jarvis",
            "reload_jarvis",
        }:
            return True, self._handle_jarvis_restart(turn, start_time)

        # 3. Folder Open / Close
        if semantic_act.intent in ("FOLDER_OPEN", "FOLDER_CLOSE") or semantic_act.action in (
            "open_folder",
            "close_folder",
        ):
            return True, self._handle_folder_action(semantic_act, turn, start_time, source)

        # 4. Open / Launch Application
        if semantic_act.intent in ("OPEN_APP", "OPEN_APPLICATION") and semantic_act.action in ("launch_app", "open_app"):
            return True, self._handle_launch_app(semantic_act, turn, start_time, source)

        # 5. Generate Password
        if semantic_act.intent == "GENERATE_PASSWORD":
            return True, self._handle_generate_password(semantic_act, turn)

        # 6. Toggle Bluetooth
        if semantic_act.intent == "TOGGLE_BLUETOOTH":
            return True, self._handle_toggle_bluetooth(semantic_act, turn)

        # 7. Open File
        if semantic_act.intent == "OPEN_FILE" or semantic_act.action == "open_file":
            return True, self._handle_open_file(semantic_act, turn, start_time)

        # 8. Screen Inspection
        if semantic_act.intent == "SCREEN_INSPECTION" or semantic_act.action in (
            "inspect_screen",
            "describe_screen",
            "whats_on_screen",
        ):
            return True, self._handle_screen_inspection(semantic_act, turn)

        # 8b. Visual Text Interaction (Find, Point, Click, Double-Click, Select)
        if semantic_act.intent == "VISUAL_TEXT_INTERACTION" or semantic_act.service == "visual":
            return True, self._handle_visual_text_interaction(semantic_act, turn)

        # 9. Target Status Check
        if semantic_act.action in {"check_status", "check_app_status"}:
            return True, self._handle_target_status(semantic_act, turn)

        # 10. Alias Manager
        if semantic_act.service == "alias":
            return True, self._handle_alias_management(semantic_act, turn)

        # 11. Browser / YouTube Website Navigation
        if (
            semantic_act.service == "browser"
            and semantic_act.action in {"open_website", "open_url"}
        ) or (semantic_act.service == "youtube" and semantic_act.action == "open_youtube"):
            return True, self._handle_website_open(semantic_act, turn)

        # 12. Direct Target Engine Execution
        if semantic_act.service == "target" and semantic_act.action == "execute":
            return True, self._handle_target_execute(semantic_act, turn)

        # 13. Activity Memory Queries
        if semantic_act.service == "activity":
            return True, self._handle_activity_query(semantic_act, turn, source)

        # 14. Security / Face Authentication
        if semantic_act.service == "security":
            return True, self._handle_security(semantic_act, turn)

        # 14b. Software Update Manager
        if semantic_act.service == "software_update":
            return True, self._handle_software_update(semantic_act, turn, start_time)

        # 14c. Equity Research & Decision Support
        if semantic_act.service == "equity_research":
            return True, self._handle_equity_research(semantic_act, turn, start_time)

        # 14d. Developer Code Assistant
        if semantic_act.service == "code_assistant":
            return True, self._handle_code_assistant(semantic_act, turn, start_time)

        # 14e. Unified Memory Control (explicit remember/forget/recall only;
        # profiles stay with PersonalProfileExtractor, reminders keep dilana).
        if semantic_act.service == "memory":
            try:
                from memory.memory_api import get_unified_memory_for
                mem = get_unified_memory_for(self.core)
                try:
                    rel = mem.get_relevant(turn.normalized_input or turn.raw_input, limit=2)
                    turn.metadata["memory_context"] = [
                        {"key": r.get("key"), "memory_type": r.get("memory_type")} for r in rel
                    ]
                except Exception:
                    pass
            except Exception:
                pass
            return True, self._handle_memory_action(semantic_act, turn)

        # 15. Plugin / Standard Intent Route Dispatch
        return self._handle_plugin_or_intent(
            semantic_act, turn, start_time, source, ctx_key, lce_tokens
        )

    def _handle_memory_action(self, semantic_act: Any, turn: Any) -> str:
        """Executes explicit memory directives via UnifiedMemory. Never raises."""
        import re as _re

        def _slug(words: str, n: int = 6) -> str:
            toks = _re.sub(r"[^a-zA-Z0-9 ]", " ", words or "").lower().split()
            return "_".join(toks[:n]) or "note"

        def _derive_key_value(content: str):
            c = (content or "").strip()
            m = _re.fullmatch(r"my\s+(.+?)\s+is\s+(.+)", c, flags=_re.I)
            if m:
                return m.group(1).strip().lower(), m.group(2).strip()
            m = _re.fullmatch(r"(?:mera|meri)\s+(.+?)\s+(.+?)\s+hai", c, flags=_re.I)
            if m and len(m.group(1).split()) <= 4:
                return m.group(1).strip().lower(), m.group(2).strip()
            return f"note_{_slug(c)}", c

        try:
            from memory.memory_api import get_unified_memory_for
            mem = get_unified_memory_for(self.core)
        except Exception:
            return "Abhi memory connected nahi hai, Boss."
        try:
            action = (semantic_act.action or "").lower()
            params = dict(getattr(semantic_act, "parameters", {}) or {})

            if action == "remember":
                content = (params.get("content") or semantic_act.query or "").strip()
                if not content:
                    if params.get("needs_context"):
                        ctx_val = ""
                        try:
                            ctx = getattr(self.core, "active_context", None)
                            ctx_val = str(getattr(ctx, "last_entity", "") or getattr(ctx, "website", "") or "")
                        except Exception:
                            pass
                        if ctx_val.strip():
                            key, val = _derive_key_value(ctx_val.strip())
                            ok = mem.remember(key, val, memory_type="CONTEXT", confidence=1.0,
                                              importance=0.6, explicit=True)
                            return "Yaad rakh liya, Boss." if ok else "Ye baat save nahi ho paayi, Boss."
                    return "Kya yaad rakhna hai, Boss? Wapas batayein."
                key, val = _derive_key_value(content)
                mtype = "PREFERENCE" if _re.search(r"\b(hinglish|hindi|english|pasand|prefer)", content, _re.I) else "FACT"
                ok = mem.remember(key, val, memory_type=mtype, confidence=1.0,
                                  importance=0.7, explicit=True)
                if not ok:
                    return "Ye baat save nahi ho paayi, Boss."
                try:
                    mem.observe_turn_async(turn.raw_input, "remembered", intent="memory_remember")
                except Exception:
                    pass
                if key.startswith("note_"):
                    return f"Yaad rakh liya, Boss — {val}."
                return f"Yaad rakh liya, Boss — {key}: {val}."

            if action == "forget":
                target = (params.get("target") or semantic_act.query or "").strip().lower()
                if not target:
                    return "Kaunsi memory delete karun, Boss? Naam batayein."
                # try exact key, else first search hit (bounded, no dump)
                rec = mem.get(target)
                forget_key = target
                if rec is None:
                    hits = mem.search(target, limit=1)
                    if hits and hits[0].get("key"):
                        forget_key = str(hits[0]["key"])
                    else:
                        return "Ye to saved hi nahi tha, Boss."
                ok = mem.forget(forget_key)
                return "Bhool gaya, Boss." if ok else "Delete nahi ho paaya, Boss."

            if action == "recall_summary":
                items = mem.list_memories()
                vals = [f"{(r.get('key') or '').strip()}: {(r.get('value') or '').strip()}"
                        for r in items if r.get("key") and r.get("value")]
                if not vals:
                    return "Abhi aapki koi personal baat saved nahi hai."
                shown = "; ".join(vals[:8])
                suffix = "..." if len(vals) > 8 else ""
                return f"Aapne bataya tha — {shown}{suffix}."

            if action == "list_preferences":
                prefs = mem.get_preferences()
                if not prefs:
                    return "Koi preference saved nahi hai, Boss."
                shown = "; ".join(f"{k}: {v}" for k, v in list(prefs.items())[:8])
                return f"Aapki preferences — {shown}."

            if action == "query_fact":
                key = (params.get("key") or semantic_act.query or "").strip().lower()
                if not key:
                    return "Kya poochna hai, Boss? Wapas batayein."
                rec = mem.get(key)
                if rec is None:
                    hits = mem.search(key, limit=1)
                    rec = hits[0] if hits else None
                if rec is None or not rec.get("value"):
                    return "Ye saved nahi hai, Boss."
                val = str(rec["value"]).strip()
                english = bool(_re.match(r"(?i)^(what|who|where|when|which|tell)", turn.raw_input.strip()))
                if english:
                    return f"Your {rec.get('key', key)} is {val}."
                return f"Aapka {rec.get('key', key)} {val} hai."

            if action == "clear_session":
                mem.clear_session()
                return "Session memory saaf kar di, Boss."

            return "Memory command samajh nahi aaya, Boss."
        except Exception:
            return "Memory me kuch gadbad hui, Boss. Thodi der baad try karein."

    def _handle_window_action(self, semantic_act: Any, turn: Any) -> str:
        from core.target_engine import TargetRequest
        from core.execution.models import ExecutionResult, ExecutionState, VerificationResult

        action_name = self.UNIVERSAL_WINDOW_ACTIONS[semantic_act.action]
        target_value = semantic_act.parameters.get("app_name", semantic_act.query or "")
        outcome = self.core.target_engine.execute(
            TargetRequest(target=target_value, action=action_name)
        )
        self.core.last_execution_result = ExecutionResult(
            success=outcome.success,
            status=ExecutionState.SUCCESS if outcome.success else ExecutionState.FAILED,
            requested_action=semantic_act.action,
            executed_action=action_name,
            target=target_value,
            action_type="window",
            verification_result=VerificationResult(
                verified=outcome.verified,
                state=ExecutionState.SUCCESS if outcome.verified else ExecutionState.FAILED,
                check_type="window_operation",
                expected=target_value,
                actual=target_value if outcome.verified else None,
                message=outcome.message,
            ),
            error=None if outcome.success else outcome.message,
            reason="needs_clarification" if outcome.needs_clarification else (None if outcome.success else "verification_failed"),
            data={"needs_clarification": True} if outcome.needs_clarification else {},
        )
        try:
            ExecutionOutcomeHook.process_outcome(
                self.core,
                turn,
                self.core.last_execution_result,
                source=getattr(turn, "source", "user") or "user"
            )
        except Exception as _hook_err:
            logger.debug("OutcomeHook execution note: %s", _hook_err)

        if outcome.needs_clarification:
            self.core.dialog_manager.set_lock(
                workflow_type="TARGET_ACTION",
                required_slots=["target_scope"],
                target_plugin="target",
                target_action="execute",
                prompt_question=outcome.message,
                initial_slots={
                    "target": target_value,
                    "action": action_name,
                    "container": "",
                },
            )
        self.core.conversation_manager.complete_turn(turn, outcome.message)
        self.core.state_machine.transition_to(SystemState.IDLE)
        return outcome.message

    def _handle_jarvis_restart(self, turn: Any, start_time: float) -> str:
        from core.reloader import trigger_reload

        resp_msg = "Jarvis ko live restart kar raha hoon, Boss..."
        turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
        self.core.conversation_manager.complete_turn(turn, resp_msg)
        self.core.state_machine.transition_to(SystemState.IDLE)
        self.core.action_logger.log_success(resp_msg, turn.execution_time_ms)
        threading.Timer(0.4, trigger_reload).start()
        return resp_msg

    def _handle_folder_action(
        self, semantic_act: Any, turn: Any, start_time: float, source: str
    ) -> str:
        from core.execution.models import ExecutionResult, ExecutionState

        target_fld = (semantic_act.parameters or {}).get("target", "")
        if semantic_act.action == "open_folder":
            exec_res = self.core.execution_strategies.open_folder_verified(target=target_fld)
            self.core.last_execution_result = exec_res

            if exec_res.success:
                resp_msg = (
                    exec_res.data.get("message")
                    or f"'{target_fld}' folder open kar diya hai aur verify kar liya hai, Boss."
                )
            else:
                resp_msg = f"'{target_fld}' folder open nahi ho paya, Boss. Reason: {exec_res.reason or exec_res.error}"
        else:
            files_plugin = (
                self.core.plugin_manager.get_plugin("files")
                if hasattr(self.core, "plugin_manager") and self.core.plugin_manager
                else None
            )
            if files_plugin:
                res = files_plugin.execute(semantic_act.action, semantic_act.parameters or {})
                resp_msg = (
                    res.data.get("message")
                    if (res.data and "message" in res.data)
                    else (res.error or f"Folder action {semantic_act.action} execute ho gaya, Boss.")
                )
            else:
                from plugins.files.operations import FilesystemOperations

                ops = FilesystemOperations()
                res = ops.close_folder(
                    target=semantic_act.parameters.get("target", ""),
                    close_all=semantic_act.parameters.get("close_all", False),
                )
                resp_msg = (
                    res.data.get("message")
                    if (res.data and "message" in res.data)
                    else (res.error or "Folder action complete, Boss.")
                )
            self.core.last_execution_result = ExecutionResult(
                success=bool(getattr(res, "success", True)),
                status=ExecutionState.SUCCESS if getattr(res, "success", True) else ExecutionState.FAILED,
                requested_action="close_folder",
                executed_action="close_folder",
                target=target_fld,
                action_type="folder",
            )

        if self.core.last_execution_result:
            try:
                ExecutionOutcomeHook.process_outcome(
                    self.core,
                    turn,
                    self.core.last_execution_result,
                    source=source
                )
            except Exception as _hook_err:
                logger.debug("OutcomeHook execution note: %s", _hook_err)

        resp_msg = self.core._ensure_response(resp_msg)
        turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
        self.core.conversation_manager.complete_turn(turn, resp_msg)
        self.core.action_logger.log_success(resp_msg, turn.execution_time_ms)
        if self.core.memory_manager:
            try:
                self.core.memory_manager.record_interaction(
                    user_input=turn.raw_input,
                    response=resp_msg,
                    intent="nlu_open_app",
                    source=source,
                )
            except Exception as e:
                logger.error(f"Error recording memory: {e}")
        self.core.event_bus.emit(
            "response.completed", {"turn_id": turn.turn_id, "response": resp_msg}
        )
        return resp_msg

    def _handle_launch_app(
        self, semantic_act: Any, turn: Any, start_time: float, source: str
    ) -> str:
        app_target = (semantic_act.parameters or {}).get("app_name", semantic_act.query or "")
        is_new = bool((semantic_act.parameters or {}).get("is_new", False))
        file_path = (semantic_act.parameters or {}).get("file_path", None)
        not_installed = bool((semantic_act.parameters or {}).get("not_installed", False))
        clarification = (semantic_act.parameters or {}).get("clarification")

        if clarification:
            disp = (semantic_act.parameters or {}).get("display_name") or app_target.capitalize()
            self.core.dialog_manager.set_pending_spelling(app_target, disp, f"open {disp}")
            self.core.conversation_manager.complete_turn(turn, clarification)
            self.core.state_machine.transition_to(SystemState.IDLE)
            self.core.action_logger.log_success(clarification)
            return clarification

        logger.info(
            "COMMAND_ROUTED: Action=OPEN Entity=%s Target=APPLICATION Resolver=LOCAL_APPLICATION Handler=APPLICATION_LAUNCHER",
            app_target,
        )

        if not_installed:
            disp = (semantic_act.parameters or {}).get("display_name") or app_target.capitalize()
            resp_msg = f"'{disp}' aapke system par installed nahi mila, Boss."
        else:
            exec_res = self.core.execution_strategies.launch_application_verified(
                app_name=app_target, is_new=is_new, file_path=file_path
            )
            self.core.last_execution_result = exec_res

            if exec_res.success:
                from core.natural_responses import NaturalResponseSynthesizer

                user_lang = NaturalResponseSynthesizer.detect_language(turn.raw_input)
                disp = (exec_res.data or {}).get("display_name") or app_target.capitalize()
                resp_msg = NaturalResponseSynthesizer.open_app(disp, language=user_lang)
                if hasattr(self.core, "active_context") and self.core.active_context:
                    self.core.active_context.set_application(app_target, action="launch_app")
            elif exec_res.reason == "not_installed":
                disp = (exec_res.data or {}).get("display_name") or app_target.capitalize()
                resp_msg = f"'{disp}' aapke system par installed nahi mila, Boss."
            else:
                disp = (exec_res.data or {}).get("display_name") or app_target.capitalize()
                resp_msg = f"{disp} open nahi ho paya, Boss."

        if self.core.last_execution_result:
            try:
                ExecutionOutcomeHook.process_outcome(
                    self.core,
                    turn,
                    self.core.last_execution_result,
                    source=source
                )
            except Exception as _hook_err:
                logger.debug("OutcomeHook execution note: %s", _hook_err)

        resp_msg = self.core._ensure_response(resp_msg)
        turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
        self.core.conversation_manager.complete_turn(turn, resp_msg)
        self.core.state_machine.transition_to(SystemState.IDLE)
        self.core.action_logger.log_success(resp_msg, turn.execution_time_ms)
        if self.core.memory_manager:
            try:
                self.core.memory_manager.record_interaction(
                    user_input=turn.raw_input,
                    response=resp_msg,
                    intent="nlu_open_app",
                    source=source,
                )
            except Exception as e:
                logger.error(f"Error recording memory: {e}")
        self.core.event_bus.emit(
            "response.completed", {"turn_id": turn.turn_id, "response": resp_msg}
        )
        return resp_msg

    def _handle_generate_password(self, semantic_act: Any, turn: Any) -> str:
        from core.natural_responses import NaturalResponseSynthesizer

        user_lang = NaturalResponseSynthesizer.detect_language(turn.raw_input)
        if getattr(semantic_act, "needs_clarification", False) or (
            semantic_act.parameters or {}
        ).get("needs_clarification", False):
            prompt_q = (
                "Kitne characters ka?" if user_lang != "en" else "How many characters?"
            )
            self.core.dialog_manager.set_lock(
                workflow_type="PASSWORD_GENERATE",
                required_slots=["length"],
                prompt_question=prompt_q,
                language=user_lang,
            )
            self.core.conversation_manager.complete_turn(turn, prompt_q)
            self.core.state_machine.transition_to(SystemState.IDLE)
            self.core.action_logger.log_success(prompt_q)
            return prompt_q
        else:
            length = (semantic_act.parameters or {}).get("length", 12)
            from core.semantic.parsers.security import generate_secure_password

            pwd = generate_secure_password(length)
            resp_msg = NaturalResponseSynthesizer.generate_password(
                length, pwd, language=user_lang
            )
            self.core.conversation_manager.complete_turn(turn, resp_msg)
            self.core.state_machine.transition_to(SystemState.IDLE)
            self.core.action_logger.log_success(resp_msg)
            return resp_msg

    def _handle_toggle_bluetooth(self, semantic_act: Any, turn: Any) -> str:
        from core.natural_responses import NaturalResponseSynthesizer

        user_lang = NaturalResponseSynthesizer.detect_language(turn.raw_input)
        enabled = bool((semantic_act.parameters or {}).get("enabled", False))
        bt_plugin = (
            self.core.plugin_manager.get_plugin("bluetooth")
            if hasattr(self.core, "plugin_manager") and self.core.plugin_manager
            else None
        )
        if bt_plugin:
            bt_action = "enable_bluetooth" if enabled else "disable_bluetooth"
            res = bt_plugin.execute(bt_action, {})
            if res and res.success and res.data and res.data.get("message"):
                resp_msg = res.data["message"]
            else:
                resp_msg = NaturalResponseSynthesizer.toggle_device(
                    "Bluetooth", enabled, language=user_lang
                )
        else:
            resp_msg = NaturalResponseSynthesizer.toggle_device(
                "Bluetooth", enabled, language=user_lang
            )
        self.core.conversation_manager.complete_turn(turn, resp_msg)
        self.core.state_machine.transition_to(SystemState.IDLE)
        self.core.action_logger.log_success(resp_msg)
        return resp_msg

    def _handle_open_file(self, semantic_act: Any, turn: Any, start_time: float) -> str:
        file_target = (semantic_act.parameters or {}).get("path") or (
            semantic_act.parameters or {}
        ).get("file_name", "")
        files_plugin = (
            self.core.plugin_manager.get_plugin("files")
            if hasattr(self.core, "plugin_manager") and self.core.plugin_manager
            else None
        )
        if files_plugin:
            res = files_plugin.execute("OPEN", {"target": file_target})
            resp_msg = (
                res.data.get("message")
                if (res.data and "message" in res.data)
                else (res.error or f"'{file_target}' open kar diya hai, Boss.")
            )
        else:
            from plugins.files.operations import FilesystemOperations

            ops = FilesystemOperations()
            res = ops.open(file_target)
            resp_msg = (
                res.data.get("message")
                if (res.data and "message" in res.data)
                else (res.error or f"'{file_target}' open ho gaya, Boss.")
            )

        from core.execution.adapter import OutcomeAdapter
        adapted_file_res = OutcomeAdapter.from_plugin_result(
            res,
            requested_action="open_file",
            target=file_target,
            action_type="file"
        )
        try:
            ExecutionOutcomeHook.process_outcome(
                self.core,
                turn,
                adapted_file_res,
                source=getattr(turn, "source", "user") or "user"
            )
        except Exception as _hook_err:
            logger.debug("OutcomeHook execution note: %s", _hook_err)

        resp_msg = self.core._ensure_response(resp_msg)
        turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
        self.core.conversation_manager.complete_turn(turn, resp_msg)
        self.core.state_machine.transition_to(SystemState.IDLE)
        self.core.action_logger.log_success(resp_msg, turn.execution_time_ms)
        self.core.event_bus.emit(
            "response.completed", {"turn_id": turn.turn_id, "response": resp_msg}
        )
        return resp_msg

    def _handle_screen_inspection(self, semantic_act: Any, turn: Any) -> str:
        screen_plugin = (
            self.core.plugin_manager.get_plugin("screen")
            if hasattr(self.core, "plugin_manager") and self.core.plugin_manager
            else None
        )
        if screen_plugin:
            res = screen_plugin.execute("inspect_screen", semantic_act.parameters or {})
            resp_msg = (
                res.data.get("message")
                if (res.success and res.data)
                else "Screen status check karne mein error aaya, Boss."
            )
        else:
            wm = getattr(self.core.target_engine, "window_manager", None)
            if wm:
                is_cap = bool((semantic_act.parameters or {}).get("capability_query", False))
                is_list = bool((semantic_act.parameters or {}).get("list_windows", False))
                lang = (semantic_act.parameters or {}).get("language", "hi")
                fg = wm.get_foreground_window()
                all_wins = wm.list_all_windows()
                win_apps = list(
                    dict.fromkeys(
                        [
                            (w.process_name or "").replace(".exe", "").capitalize()
                            for w in all_wins
                            if w.title
                            and w.process_name
                            and w.process_name.lower()
                            not in ("explorer", "system", "idle", "taskhostw")
                        ]
                    )
                )
                win_str = ", ".join(win_apps[:5]) if win_apps else ""

                if lang == "en":
                    if is_cap:
                        if win_str:
                            resp_msg = f"Yes Boss! I can see and inspect your screen. Currently {win_str} are open on your screen."
                        else:
                            resp_msg = "Yes Boss! I can see and inspect your screen. Currently no active windows are open."
                    elif is_list:
                        if win_str:
                            resp_msg = f"Currently open windows on your screen are: {win_str}, Boss."
                        else:
                            resp_msg = "There are no active application windows open on your screen right now, Boss."
                    else:
                        if fg and fg.title and fg.title not in ("Active Window", "Program Manager"):
                            pname = (fg.process_name or "App").replace(".exe", "").capitalize()
                            resp_msg = f"Currently '{fg.title[:45]}' is open in the foreground in {pname}, Boss."
                        else:
                            resp_msg = "Currently no active application window is open on screen, Boss."
                else:
                    if is_cap:
                        if win_str:
                            resp_msg = f"Ji haan Boss! Main aapki screen dekh aur inspect kar sakta hoon. Abhi screen par {win_str} open hain."
                        else:
                            resp_msg = "Ji haan Boss! Main aapki screen dekh aur inspect kar sakta hoon. Abhi screen par koi active window open nahi hai."
                    elif is_list:
                        if win_str:
                            resp_msg = f"Abhi aapke laptop ki screen par {win_str} open hain, Boss."
                        else:
                            resp_msg = "Abhi screen par koi active application window open nahi hai, Boss."
                    else:
                        if fg and fg.title and fg.title not in ("Active Window", "Program Manager"):
                            pname = (fg.process_name or "App").replace(".exe", "").capitalize()
                            resp_msg = f"Abhi screen par foreground mein '{fg.title[:45]}' wala {pname} open hai, Boss."
                        else:
                            resp_msg = "Abhi screen par koi active application open nahi hai, Boss."
            else:
                resp_msg = "Screen details inspect kar raha hoon, Boss."

        self.core.conversation_manager.complete_turn(turn, resp_msg)
        self.core.state_machine.transition_to(SystemState.IDLE)
        return resp_msg

    def _handle_visual_text_interaction(self, semantic_act: Any, turn: Any) -> str:
        from core.visual_interaction import get_visual_interaction_engine
        from core.execution.models import ExecutionResult, ExecutionState, VerificationResult

        engine = get_visual_interaction_engine()
        params = semantic_act.parameters or {}
        target_text = params.get("target", semantic_act.query or "")
        sub_action = params.get("sub_action", semantic_act.action or "FIND_TEXT")
        ord_idx = params.get("ordinal_index")
        raw_utt = params.get("raw_utterance", turn.raw_input if turn else "")

        result = engine.execute(
            target_text=target_text,
            sub_action=sub_action,
            ordinal_index=ord_idx,
            raw_utterance=raw_utt
        )

        self.core.last_execution_result = ExecutionResult(
            success=result.success,
            status=ExecutionState.SUCCESS if result.success else ExecutionState.FAILED,
            requested_action=sub_action,
            executed_action=result.action,
            target=result.display_name,
            action_type="visual_text_interaction",
            verification_result=VerificationResult(
                verified=result.verified,
                state=ExecutionState.SUCCESS if result.verified else ExecutionState.FAILED,
                check_type="visual_interaction",
                expected=result.display_name,
                actual=result.display_name if result.verified else None,
                message=result.message,
            ),
            error=None if result.success else result.message,
            reason=None if result.success else "visual_target_not_found",
        )

        self.core.conversation_manager.complete_turn(turn, result.message)
        self.core.state_machine.transition_to(SystemState.IDLE)
        return result.message

    def _handle_target_status(self, semantic_act: Any, turn: Any) -> str:
        target_value = semantic_act.parameters.get("app_name") or semantic_act.parameters.get(
            "target", semantic_act.query or ""
        )
        resp_msg = self.core._check_target_status(target_value, turn.normalized_input)
        self.core.conversation_manager.complete_turn(turn, resp_msg)
        self.core.state_machine.transition_to(SystemState.IDLE)
        return resp_msg

    def _handle_alias_management(self, semantic_act: Any, turn: Any) -> str:
        from core.alias_manager import get_alias_manager

        alias_mgr = get_alias_manager()
        if semantic_act.action == "learn_alias":
            alias = semantic_act.parameters.get("alias", "")
            target = semantic_act.parameters.get("target", "")
            action_type = semantic_act.parameters.get("action_type", "OPEN_WEBSITE")
            description = semantic_act.parameters.get("description", "")
            if action_type.upper() == "OPEN_WEBSITE":
                if not target:
                    self.core.conversation_manager.session.set_variable(
                        "pending_website_learning",
                        {"alias": alias.strip(), "created_at": time.time()},
                    )
                    resp_msg = f"{alias.title()} ke liye kaunsa safe website URL save karun?"
                else:
                    try:
                        entry = self.core.website_knowledge.learn(alias, target)
                        alias_display = alias.upper() if len(alias.split()) == 1 else alias
                        resp_msg = f"Samajh gaya. Ab se '{alias_display}' ke naam se {entry['canonical_name']} open karunga."
                    except ValueError:
                        self.core.conversation_manager.session.set_variable(
                            "pending_website_learning",
                            {"alias": alias.strip(), "created_at": time.time()},
                        )
                        resp_msg = f"{alias.title()} ke liye valid HTTP/HTTPS URL bhej dijiye."
            elif action_type.upper() in ("OPEN_APPLICATION", "OPEN_APP"):
                alias_mgr.add_alias(
                    alias, target, action_type="OPEN_APPLICATION", description=description
                )
                resp_msg = f"Samajh gaya. Ab se '{alias}' bolne par {target} open karunga, Boss."
            else:
                alias_mgr.add_alias(alias, target, action_type=action_type, description=description)
                resp_msg = f"Samajh gaya. Ab jab aap {alias.upper()} bolenge, main woh command chala dunga."
            self.core.conversation_manager.complete_turn(turn, resp_msg)
            self.core.state_machine.transition_to(SystemState.IDLE)
            return resp_msg
        elif semantic_act.action == "update_alias":
            alias = semantic_act.parameters.get("alias", "")
            target = semantic_act.parameters.get("target", "")
            try:
                entry = self.core.website_knowledge.learn(alias, target)
                resp_msg = f"Samajh gaya. {alias.upper()} ka target URL update kar diya hai."
            except ValueError:
                resp_msg = "Naya website URL valid HTTP/HTTPS address hona chahiye."
            self.core.conversation_manager.complete_turn(turn, resp_msg)
            self.core.state_machine.transition_to(SystemState.IDLE)
            return resp_msg
        elif semantic_act.action == "delete_alias":
            alias = semantic_act.parameters.get("alias", "")
            success = self.core.website_knowledge.delete(alias) or alias_mgr.delete_alias(alias)
            if success:
                resp_msg = f"{alias.upper()} alias delete kar diya hai, Boss."
            else:
                resp_msg = f"'{alias}' naam ka koi custom alias nahi mila, Boss."
            self.core.conversation_manager.complete_turn(turn, resp_msg)
            self.core.state_machine.transition_to(SystemState.IDLE)
            return resp_msg
        return "Alias action processed."

    def _handle_website_open(self, semantic_act: Any, turn: Any) -> str:
        from core.target_engine import TargetRequest
        from core.execution.models import ExecutionResult, ExecutionState, VerificationResult

        target_value = (
            semantic_act.parameters.get("site")
            or semantic_act.parameters.get("url")
            or ("youtube" if semantic_act.service == "youtube" else "")
        )
        website_resolution = None
        if semantic_act.service in {"browser", "youtube"} and target_value:
            from plugins.browser.website_resolver import (
                AmbiguousWebsiteError,
                UnknownWebsiteError,
                WebsiteResolver,
            )

            try:
                website_resolution = WebsiteResolver.resolve(
                    target_value, semantic_act.parameters.get("search_candidates")
                )
            except AmbiguousWebsiteError:
                resp_msg = f"{target_value.title()} ke liye do websites saved hain. Aap kaunsi open karna chahte hain?"
                self.core.conversation_manager.complete_turn(turn, resp_msg)
                self.core.state_machine.transition_to(SystemState.IDLE)
                return resp_msg
            except UnknownWebsiteError:
                self.core.conversation_manager.session.set_variable(
                    "pending_website_learning",
                    {"alias": target_value.strip(), "created_at": time.time()},
                )
                resp_msg = f"{target_value.title()} se aap kis webpage ki baat kar rahe hain?"
                self.core.conversation_manager.complete_turn(turn, resp_msg)
                self.core.state_machine.transition_to(SystemState.IDLE)
                return resp_msg
            except ValueError:
                resp_msg = "Website URL valid nahi lag raha. HTTP ya HTTPS URL use kijiye."
                self.core.conversation_manager.complete_turn(turn, resp_msg)
                self.core.state_machine.transition_to(SystemState.IDLE)
                return resp_msg

        force_new = bool(semantic_act.parameters.get("force_new", False))
        container_value = (
            semantic_act.parameters.get("container")
            or semantic_act.parameters.get("browser")
            or ""
        )
        if (
            not container_value
            and target_value
            and hasattr(self.core, "learning_manager")
            and self.core.learning_manager
        ):
            saved_pref = self.core.learning_manager.get_execution_preference(target_value)
            if saved_pref:
                container_value = saved_pref
                logger.debug(
                    "EXEC_PREF_INJECTED target=%r container=%r",
                    target_value,
                    container_value,
                )

        outcome = self.core.target_engine.execute(
            TargetRequest(
                target=target_value,
                action="open",
                container=container_value,
                force_new=force_new,
                resolved_url=website_resolution.final_url if website_resolution else "",
                display_name=website_resolution.canonical_name
                if website_resolution
                else target_value,
            )
        )
        self.core.last_execution_result = ExecutionResult(
            success=outcome.success,
            status=ExecutionState.SUCCESS if outcome.success else ExecutionState.FAILED,
            requested_action="open_website",
            executed_action="open_website",
            target=target_value,
            action_type="browser",
            verification_result=VerificationResult(
                verified=outcome.verified,
                state=ExecutionState.SUCCESS if outcome.verified else ExecutionState.UNVERIFIED,
                check_type="browser_opened",
                expected=target_value,
                actual=outcome.url or target_value if outcome.success else None,
                message=outcome.message,
            ),
            error=None if outcome.success else outcome.message,
            reason=None if outcome.success else "verification_failed",
        )
        try:
            ExecutionOutcomeHook.process_outcome(
                self.core,
                turn,
                self.core.last_execution_result,
                source=getattr(turn, "source", "user") or "user"
            )
        except Exception as _hook_err:
            logger.debug("OutcomeHook execution note: %s", _hook_err)

        if outcome.success and hasattr(self.core, "active_context") and self.core.active_context:
            try:
                self.core.active_context.set_website(
                    target_value, action="open_website",
                    browser=container_value or "browser", container=container_value)
            except Exception:
                self.core.active_context.set_website(target_value, action="open_website")
        # Human-like success message: name the site + explicit browser instead of
        # echoing a raw URL ("Opening Https://Chatgpt.Com."). Only overrides when an
        # explicit container was given; all other flows keep outcome.message.
        resp_msg = outcome.message
        if outcome.success and container_value:
            from core.semantic.parsers.web import BROWSER_DISPLAY
            _site_disp = (website_resolution.canonical_name if website_resolution
                          else target_value)
            _site_disp = {"chatgpt": "ChatGPT"}.get(str(_site_disp).lower(), str(_site_disp).title())
            _b_disp = BROWSER_DISPLAY.get(container_value.lower(), container_value.capitalize())
            resp_msg = f"{_site_disp} {_b_disp} me khol diya."
        self.core.conversation_manager.complete_turn(turn, resp_msg)
        self.core.state_machine.transition_to(SystemState.IDLE)
        self.core._record_turn_feedback(
            turn=turn,
            goal=f"Open website {target_value}",
            steps=[{
                "plugin": "browser",
                "action": "open",
                "target": target_value,
                "container": container_value,
            }],
            execution_results=[self.core.last_execution_result],
            verification_results=[self.core.last_execution_result.verification_result]
            if self.core.last_execution_result
            and self.core.last_execution_result.verification_result
            else None,
            success=outcome.success,
            error_msg=None if outcome.success else outcome.message,
            category="browser",
            intent_name="open_website",
        )
        return resp_msg

    def _handle_target_execute(self, semantic_act: Any, turn: Any) -> str:
        from core.target_engine import TargetRequest

        outcome = self.core.target_engine.execute(TargetRequest(**semantic_act.parameters))
        _tx_container = str(semantic_act.parameters.get("container", "") or "")
        if outcome.success and semantic_act.parameters.get("action") in {
            "open",
            "activate",
            "focus",
        }:
            target_name = semantic_act.parameters.get("target", "")
            if target_name and hasattr(self.core, "active_context") and self.core.active_context:
                try:
                    self.core.active_context.set_website(
                        target_name, action="open_website",
                        browser=_tx_container or "browser", container=_tx_container)
                except Exception:
                    self.core.active_context.set_website(target_name, action="open_website")
        if outcome.needs_clarification:
            self.core.dialog_manager.set_lock(
                workflow_type="TARGET_ACTION",
                required_slots=["target_scope"],
                target_plugin="target",
                target_action="execute",
                prompt_question=outcome.message,
                initial_slots={
                    "target": semantic_act.parameters["target"],
                    "action": semantic_act.parameters["action"],
                    "container": semantic_act.parameters.get("container", ""),
                },
            )
        # Same human-like override as website-open: name site + explicit browser.
        _tx_msg = outcome.message
        if (outcome.success and _tx_container
                and semantic_act.parameters.get("action") == "open"
                and semantic_act.parameters.get("target")):
            from core.semantic.parsers.web import BROWSER_DISPLAY
            _t = str(semantic_act.parameters.get("target", ""))
            _t_disp = {"chatgpt": "ChatGPT", "youtube": "YouTube"}.get(_t.lower(), _t.title())
            _b_disp = BROWSER_DISPLAY.get(_tx_container.lower(), _tx_container.capitalize())
            _tx_msg = f"{_t_disp} {_b_disp} me khol diya."
        self.core.conversation_manager.complete_turn(turn, _tx_msg)
        self.core.state_machine.transition_to(SystemState.IDLE)
        return _tx_msg

    def _handle_activity_query(self, semantic_act: Any, turn: Any, source: str) -> str:
        if semantic_act.action == "get_last_media":
            act_plugin = (
                self.core.plugin_manager.get_plugin("activity_monitor")
                if hasattr(self.core, "plugin_manager") and self.core.plugin_manager
                else None
            )
            website = semantic_act.parameters.get("website", "")
            temporal = semantic_act.parameters.get("temporal", "current")
            offset_minutes = semantic_act.parameters.get("offset_minutes", 0)

            # 1. If act_plugin has memory events, let it handle directly
            if act_plugin and hasattr(act_plugin, "memory"):
                event = act_plugin.memory.query_temporal(
                    website=website or None,
                    temporal=temporal,
                    offset_minutes=offset_minutes,
                )
                if event:
                    res = act_plugin.execute(
                        "get_past_activity",
                        {
                            "website": website,
                            "temporal": temporal,
                            "offset_minutes": offset_minutes,
                        },
                    )
                    if res and res.success and res.data and res.data.get("message"):
                        resp_msg = res.data["message"]
                        self.core.conversation_manager.complete_turn(turn, resp_msg)
                        self.core.state_machine.transition_to(SystemState.IDLE)
                        if self.core.memory_manager:
                            self.core.memory_manager.record_interaction(
                                turn.raw_input,
                                resp_msg,
                                intent="query_past_media",
                                source=source,
                            )
                        return resp_msg

            # 2. Check coordinator memory fallback
            activity_mem = getattr(getattr(self.core, "proactive_coordinator", None), "memory", None)
            event = None
            if activity_mem:
                recent_evs = activity_mem.get_recent_events(limit=30) if hasattr(activity_mem, "get_recent_events") else getattr(activity_mem, "_events", [])
                for ev in reversed(recent_evs):
                    ev_type = getattr(ev, "event_type", None)
                    type_str = ev_type.value if hasattr(ev_type, "value") else str(ev_type)
                    if (
                        type_str in ("VIDEO_PLAYED", "media", "youtube_video_watched")
                        or (ev.metadata or {}).get("is_video")
                        or getattr(ev, "website", "") == "youtube"
                    ):
                        if getattr(ev, "content_title", None):
                            event = ev
                            break

                if not event:
                    from core.observer.activity_memory import ActivityType
                    q_ev = activity_mem.query_temporal(
                        website=website or None,
                        temporal=temporal,
                        offset_minutes=offset_minutes,
                        event_type=ActivityType.VIDEO_PLAYED.value if hasattr(ActivityType, "VIDEO_PLAYED") else "VIDEO_PLAYED"
                    )
                    if q_ev and getattr(q_ev, "content_title", None):
                        event = q_ev

            # 3. Check persistent proactive activity database table if no in-memory media event found
            if (not event or not getattr(event, "content_title", None)) and hasattr(self.core, "memory_manager") and self.core.memory_manager and self.core.memory_manager.db:
                try:
                    query_sql = (
                        "SELECT event_type, application, window_title, content_title, website, timestamp "
                        "FROM proactive_activity_events "
                        "WHERE (event_type IN ('VIDEO_PLAYED', 'media') OR website = 'youtube') "
                        "AND content_title IS NOT NULL AND content_title != '' "
                        "ORDER BY timestamp DESC LIMIT 1"
                    )
                    rows = self.core.memory_manager.db.execute_query(query_sql)
                    if rows:
                        r = rows[0]
                        from core.observer.activity_memory import ActivityEvent, ActivityType, ActivityImportance
                        event = ActivityEvent(
                            event_id="db_persisted",
                            event_type=ActivityType.VIDEO_PLAYED,
                            importance=ActivityImportance.HIGH,
                            application=r.get("application") or "browser",
                            window_title=r.get("window_title") or "",
                            content_title=r.get("content_title"),
                            website=r.get("website") or "youtube",
                            timestamp=float(r.get("timestamp") or 0.0)
                        )
                except Exception as _db_err:
                    logger.debug("Database lookup for past media note: %s", _db_err)

            if event and event.content_title:
                src = (event.website or event.application or "YouTube").capitalize()
                resp_msg = f"Boss, aap abhi {src} par '{event.content_title}' dekh rahe the."
                self.core.conversation_manager.complete_turn(turn, resp_msg)
                self.core.state_machine.transition_to(SystemState.IDLE)
                if self.core.memory_manager:
                    self.core.memory_manager.record_interaction(
                        turn.raw_input,
                        resp_msg,
                        intent="query_past_media",
                        source=source,
                    )
                return resp_msg

            media = (
                self.core.active_context.get_last_media()
                if hasattr(self.core, "active_context") and self.core.active_context
                else None
            )
            if media and media.get("title"):
                src = (media.get("source") or "YouTube").capitalize()
                resp_msg = f"Boss, aap abhi {src} par '{media['title']}' dekh/sun rahe the."
            else:
                rows = []
                if (
                    hasattr(self.core, "memory_manager")
                    and self.core.memory_manager
                    and self.core.memory_manager.db
                ):
                    try:
                        rows = self.core.memory_manager.db.execute_query(
                            "SELECT parameters_json, result_summary, plugin_name FROM plugin_usage WHERE plugin_name IN ('youtube', 'vlc') ORDER BY timestamp DESC LIMIT 1"
                        )
                    except Exception:
                        rows = []
                if rows:
                    params = json.loads(rows[0].get("parameters_json") or "{}")
                    title = (
                        params.get("query")
                        or params.get("file_path")
                        or rows[0].get("result_summary")
                        or "video"
                    )
                    src = (rows[0].get("plugin_name") or "YouTube").capitalize()
                    resp_msg = f"Boss, aap abhi {src} par '{title}' dekh/sun rahe the."
                else:
                    offset_min = semantic_act.parameters.get("offset_minutes", 0)
                    if offset_min and int(offset_min) > 0:
                        resp_msg = f"Boss, lagbhag {offset_min} minute pehle ka koi record nahi mila."
                    else:
                        resp_msg = "Boss, mere paas pichle session ki koi recent video ya gaana record nahi hai."

            self.core.conversation_manager.complete_turn(turn, resp_msg)
            self.core.state_machine.transition_to(SystemState.IDLE)
            if self.core.memory_manager:
                self.core.memory_manager.record_interaction(
                    turn.raw_input, resp_msg, intent="query_past_media", source=source
                )
            return resp_msg

        elif semantic_act.action == "get_last_activity":
            act_plugin = (
                self.core.plugin_manager.get_plugin("activity_monitor")
                if hasattr(self.core, "plugin_manager") and self.core.plugin_manager
                else None
            )
            website = semantic_act.parameters.get("website") or None
            temporal = semantic_act.parameters.get("temporal", "current")
            offset_minutes = semantic_act.parameters.get("offset_minutes", 0)

            # 1. If act_plugin has memory events, let it handle directly
            if act_plugin and hasattr(act_plugin, "memory"):
                event = act_plugin.memory.query_temporal(
                    website=website,
                    temporal=temporal,
                    offset_minutes=offset_minutes,
                )
                if event:
                    res = act_plugin.execute("get_past_activity", semantic_act.parameters)
                    if res and res.success and res.data and res.data.get("message"):
                        resp_msg = res.data["message"]
                        self.core.conversation_manager.complete_turn(turn, resp_msg)
                        self.core.state_machine.transition_to(SystemState.IDLE)
                        if self.core.memory_manager:
                            self.core.memory_manager.record_interaction(
                                turn.raw_input,
                                resp_msg,
                                intent="query_past_activity",
                                source=source,
                            )
                        return resp_msg

            # 2. Check coordinator memory fallback
            activity_mem = getattr(getattr(self.core, "proactive_coordinator", None), "memory", None)
            event = None
            if activity_mem:
                event = activity_mem.query_temporal(
                    website=website,
                    temporal=temporal,
                    offset_minutes=offset_minutes,
                )
            if not event and hasattr(self.core, "memory_manager") and self.core.memory_manager and self.core.memory_manager.db:
                try:
                    query_sql = (
                        "SELECT event_type, application, window_title, content_title, website, timestamp "
                        "FROM proactive_activity_events "
                        "WHERE event_type NOT IN ('USER_IDLE', 'USER_ACTIVE') "
                        "ORDER BY timestamp DESC LIMIT 1"
                    )
                    rows = self.core.memory_manager.db.execute_query(query_sql)
                    if rows:
                        r = rows[0]
                        from core.observer.activity_memory import ActivityEvent, ActivityType, ActivityImportance
                        event = ActivityEvent(
                            event_id="db_activity",
                            event_type=ActivityType.APPLICATION_OPENED,
                            importance=ActivityImportance.MEDIUM,
                            application=r.get("application") or "",
                            window_title=r.get("window_title") or "",
                            content_title=r.get("content_title"),
                            website=r.get("website"),
                            timestamp=float(r.get("timestamp") or 0.0)
                        )
                except Exception as _e:
                    logger.debug("Database activity query note: %s", _e)

            if event:
                app_disp = (event.application or event.website or "system").capitalize()
                if event.content_title and event.content_title.lower() != app_disp.lower():
                    resp_msg = f"Boss, aap abhi {app_disp} par '{event.content_title}' use kar rahe the."
                else:
                    resp_msg = f"Boss, aap abhi {app_disp} use kar rahe the."
                self.core.conversation_manager.complete_turn(turn, resp_msg)
                self.core.state_machine.transition_to(SystemState.IDLE)
                if self.core.memory_manager:
                    self.core.memory_manager.record_interaction(
                        turn.raw_input,
                        resp_msg,
                        intent="query_past_activity",
                        source=source,
                    )
                return resp_msg

            last_app = (
                self.core.active_context.application
                or self.core.active_context.website
                or self.core.active_context.last_file
                if hasattr(self.core, "active_context") and self.core.active_context
                else ""
            )
            if last_app:
                resp_msg = f"Boss, aap abhi '{last_app}' par kaam kar rahe the."
            else:
                resp_msg = "Boss, pichle session mein system idle tha."
            self.core.conversation_manager.complete_turn(turn, resp_msg)
            self.core.state_machine.transition_to(SystemState.IDLE)
            if self.core.memory_manager:
                self.core.memory_manager.record_interaction(
                    turn.raw_input, resp_msg, intent="query_past_activity", source=source
                )
            return resp_msg

        return "Activity query processed."

    def _handle_security(self, semantic_act: Any, turn: Any) -> str:
        from security.face_authenticator import FaceAuthenticator

        auth = FaceAuthenticator(config=getattr(self.core, "config", {}))
        if semantic_act.action == "enroll_face":
            user = semantic_act.parameters.get("user_name", "Boss")
            res = auth.enroll(user_name=user)
            resp_msg = res.get("message") or res.get("error", "Enrollment fail ho gaya.")
        elif semantic_act.action == "get_status":
            enrolled_txt = (
                "aur aapka face profile registered hai"
                if auth.has_enrolled_profile()
                else "lekin face profile abhi registered nahi hai"
            )
            state_txt = "active (enabled)" if auth.enabled else "disabled (band)"
            resp_msg = f"Face Authentication abhi {state_txt} hai, {enrolled_txt}, Boss."
        elif semantic_act.action == "enable_auth":
            auth.enabled = True
            self.core.config.setdefault("security", {}).setdefault("face_auth", {})["enabled"] = True
            resp_msg = "Face Authentication chalu (enable) kar diya hai, Boss. Next startup par biometric verification active hoga."
        elif semantic_act.action == "disable_auth":
            auth.enabled = False
            self.core.config.setdefault("security", {}).setdefault("face_auth", {})["enabled"] = False
            resp_msg = "Face Authentication band (disable) kar diya hai, Boss."
        else:
            resp_msg = "Face Authentication command process kar diya hai, Boss."

        self.core.conversation_manager.complete_turn(turn, resp_msg)
        self.core.state_machine.transition_to(SystemState.IDLE)
        return resp_msg

    def _handle_software_update(self, semantic_act: Any, turn: Any, start_time: float) -> str:
        from core.software_update.manager import SoftwareUpdateManager
        from core.software_update.models import UpdateScope

        mgr = SoftwareUpdateManager.get_instance()
        action = semantic_act.action
        params = semantic_act.parameters or {}
        lang = params.get("language", "hi")

        if action == "check_updates":
            scope_val = params.get("scope", "ALL_SUPPORTED")
            scope = getattr(UpdateScope, scope_val.upper(), UpdateScope.ALL_SUPPORTED)
            plan, resp_msg = mgr.check_updates(scope=scope, language=lang)
        elif action == "install_updates":
            success, resp_msg = mgr.execute_updates(language=lang)
        elif action == "windows_update":
            mode = params.get("action_mode", "install")
            if mode == "check":
                plan, resp_msg = mgr.check_updates(scope=UpdateScope.OS, language=lang)
            else:
                success, resp_msg = mgr.execute_updates(language=lang)
        elif action == "cancel_update":
            mgr.cancel()
            resp_msg = (
                "Software update process cancel kar diya gaya hai, Boss."
                if lang == "hi"
                else "Software update cancelled."
            )
        elif action == "get_status":
            st = mgr.get_status()
            resp_msg = f"Update status: {st.get('state', 'IDLE')}"
        else:
            resp_msg = "Update command process kar diya hai, Boss."

        resp_msg = self.core._ensure_response(resp_msg) if hasattr(self.core, "_ensure_response") else resp_msg
        turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
        self.core.conversation_manager.complete_turn(turn, resp_msg)
        self.core.state_machine.transition_to(SystemState.IDLE)
        if hasattr(self.core, "action_logger"):
            self.core.action_logger.log_success(resp_msg, turn.execution_time_ms)
        return resp_msg

    def _handle_equity_research(self, semantic_act: Any, turn: Any, start_time: float) -> str:
        from core.equity_research.manager import EquityResearchManager
        from core.equity_research.models import AdvisoryMode, OutputMode

        mgr = EquityResearchManager.get_instance()
        action = semantic_act.action
        params = semantic_act.parameters or {}
        lang = params.get("language", "hi")

        if (semantic_act.needs_clarification and semantic_act.clarification_prompt) or action == "open_stock_wizard" or params.get("open_wizard"):
            # Launch the Stock Query Wizard server and open webpage in browser with verification
            window_verified = False
            try:
                from stock.stock_router import StockWebServer
                from stock.stock_service import StockService
                import urllib.request
                import webbrowser

                # 1. Start HTTP server
                stock_server = StockWebServer.get_instance()
                wizard_url = stock_server.start()

                # Verify server responsiveness via HTTP probe
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{stock_server.port}/api/stocks/status")
                    with urllib.request.urlopen(req, timeout=2.0) as probe_resp:
                        if probe_resp.status != 200:
                            raise RuntimeError(f"Stock server probe returned HTTP {probe_resp.status}")
                except Exception as probe_err:
                    logger.debug("Stock server probe warning: %s", probe_err)

                # Pass any initial extracted parameters into the stock service
                stock_service = StockService.get_instance()
                stock_service.initialize_workflow(initial_params=params)

                # 2. Snapshot window state before launch
                initial_count = None
                wm = getattr(self.core, "target_engine", None)
                wm = getattr(wm, "window_manager", None) if wm else None
                if wm and hasattr(wm, "list_all_windows"):
                    try:
                        initial_count = len(wm.list_all_windows())
                    except Exception:
                        pass

                # 3. Open browser window
                webbrowser.open(wizard_url)

                # 4. Verify browser window appeared or is active
                verifier = getattr(self.core, "execution_verifier", None)
                if verifier and hasattr(verifier, "verify_browser_opened"):
                    v_res = verifier.verify_browser_opened(
                        site="JARVIS — Stock Query Wizard",
                        initial_window_count=initial_count,
                        retries=3,
                        delay_seconds=0.2
                    )
                    window_verified = bool(v_res and v_res.verified)
                else:
                    window_verified = bool(stock_server.is_running)
            except Exception as e:
                logger.error(f"Failed to launch or verify Stock Query Wizard: {e}", exc_info=True)
                window_verified = False

            if window_verified:
                resp_msg = "Bilkul. Main stock selection ke liye kuch details chahunga. Maine selection window open kar di hai."
            else:
                resp_msg = "Stock selection window open nahi ho saki. Main yahan voice ke zariye bhi screening kar sakta hoon — aap apna budget ya risk preference batayein."

            if hasattr(self.core, "dialog_manager") and self.core.dialog_manager:
                self.core.dialog_manager.set_lock(
                    workflow_type="STOCK_SELECTION_WORKFLOW",
                    required_slots=["horizon", "risk"],
                    target_plugin="equity_research",
                    target_action="research_shortlist",
                    prompt_question=resp_msg,
                    initial_slots=params,
                    language=lang,
                )
            if hasattr(self.core, "active_context") and self.core.active_context:
                self.core.active_context.pending_goal = "STOCK_SELECTION_WORKFLOW"
                self.core.active_context.active_workflow = "STOCK_SELECTION_WORKFLOW"
                self.core.active_context.missing_slots = ["horizon", "risk"]
        elif "response_text" in params and params["response_text"]:
            resp_msg = params["response_text"]
        elif action == "research_shortlist":
            report, resp_msg = mgr.research_shortlist(
                output_mode=OutputMode.STANDARD,
                advisory_mode=AdvisoryMode.PERSONALIZED_ADVISORY if (params.get("capital") or params.get("risk_tolerance")) else AdvisoryMode.RESEARCH,
                language=lang,
            )
        elif action == "analyze_stock":
            sym = params.get("symbol", "RELIANCE")
            cand, resp_msg = mgr.analyze_single_stock(sym, output_mode=OutputMode.STANDARD, language=lang)
        elif action == "market_regime":
            index_data = mgr.data_provider.get_index_metrics()
            regime, rationale = mgr.regime_engine.evaluate_regime(index_data)
            resp_msg = (
                f"📈 **Current Indian Market Regime**: **{regime.value}**\n"
                f"• {rationale}\n"
                f"• India VIX: {index_data.get('india_vix', 15.0)}"
            )
        elif action == "monitor_stock":
            sym = params.get("symbol", "TCS")
            ok, resp_msg = mgr.monitor_stock(sym)
        elif action == "suggest_stocks":
            from core.equity_research.stock_screener import StockScreenerEngine
            trade_type = str(params.get("trade_type", "all")).lower()
            screener = StockScreenerEngine.get_instance()
            if hasattr(self.core, "event_bus") and self.core.event_bus:
                self.core.event_bus.publish("gui.navigate", {"tab": "stock_suggestions", "filter": trade_type})
            if "intraday" in trade_type:
                items = screener.scan_intraday_stocks()
                tname = "Intraday"
            elif "swing" in trade_type:
                items = screener.scan_swing_stocks()
                tname = "Swing"
            else:
                items = screener.get_all_suggestions().get("all", [])
                tname = "Intraday aur Swing"
            if items:
                top = items[0]
                lvl = top.levels
                resp_msg = (
                    f"Boss, {tname} trading ke liye top pick hai {top.name} ({top.symbol}). "
                    f"CMP ₹{lvl.cmp:.1f}, Target ₹{lvl.target_1:.1f} (+{lvl.target_1_pct}%), "
                    f"aur Stop-Loss ₹{lvl.stop_loss:.1f} (-{lvl.stop_loss_pct}%). "
                    f"Maine sidebar mein Stock Suggestions cockpit open kar diya hai."
                )
            else:
                resp_msg = f"Boss, is samay koi high-confluence {tname} setups nahi mile."
        else:
            report, resp_msg = mgr.research_shortlist(output_mode=OutputMode.STANDARD, language=lang)

        resp_msg = self.core._ensure_response(resp_msg) if hasattr(self.core, "_ensure_response") else resp_msg
        turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
        self.core.conversation_manager.complete_turn(turn, resp_msg)
        self.core.state_machine.transition_to(SystemState.IDLE)
        if hasattr(self.core, "action_logger"):
            self.core.action_logger.log_success(resp_msg, turn.execution_time_ms)
        if hasattr(self.core, "memory_manager") and self.core.memory_manager:
            try:
                self.core.memory_manager.record_interaction(
                    turn.raw_input, resp_msg, intent="equity_research", source="user"
                )
            except Exception:
                pass
        if hasattr(self.core, "event_bus") and self.core.event_bus:
            self.core.event_bus.emit(
                "response.completed",
                {"turn_id": turn.turn_id, "response": resp_msg, "time_ms": turn.execution_time_ms}
            )
        return resp_msg

    def _handle_code_assistant(self, semantic_act: Any, turn: Any, start_time: float) -> str:
        plugin = (
            self.core.plugin_manager.get_plugin("code_assistant")
            if hasattr(self.core, "plugin_manager") and self.core.plugin_manager
            else None
        )
        params = semantic_act.parameters or {}
        if plugin:
            res = plugin.execute(semantic_act.action, params)
            if res.success and res.data:
                resp_msg = (
                    res.data.get("formatted_chatbox_report")
                    or res.data.get("summary_message")
                    or res.data.get("message")
                    or "Code assistant action completed, Boss."
                )
            else:
                resp_msg = res.error or "Code assistant action complete nahi ho saka, Boss."
        else:
            resp_msg = "Code assistant plugin abhi available nahi hai, Boss."

        resp_msg = self.core._ensure_response(resp_msg) if hasattr(self.core, "_ensure_response") else resp_msg
        turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
        self.core.conversation_manager.complete_turn(turn, resp_msg)
        self.core.state_machine.transition_to(SystemState.IDLE)
        if hasattr(self.core, "action_logger"):
            self.core.action_logger.log_success(resp_msg, turn.execution_time_ms)
        if hasattr(self.core, "event_bus") and self.core.event_bus:
            self.core.event_bus.emit(
                "response.completed",
                {"turn_id": turn.turn_id, "response": resp_msg, "time_ms": turn.execution_time_ms}
            )
        return resp_msg

    def _handle_plugin_or_intent(
        self,
        semantic_act: Any,
        turn: Any,
        start_time: float,
        source: str,
        ctx_key: Optional[str],
        lce_tokens: Optional[list],
    ) -> Tuple[bool, Optional[str]]:
        turn.intent = Intent(
            name=semantic_act.intent.lower(),
            type=IntentType.COMMAND,
            confidence=semantic_act.confidence,
            entities=semantic_act.parameters,
            target_plugin=semantic_act.service,
            target_action=semantic_act.action,
            raw_query=turn.normalized_input,
        )
        semantic_route, _ = self.core.router.route_intent(turn.intent)
        if semantic_act.needs_clarification:
            wf_override = (semantic_act.parameters or {}).get("workflow_type")
            if wf_override:
                workflow_type = wf_override
            elif semantic_act.service == "network" and semantic_act.action == "copy_wifi_password":
                workflow_type = "WIFI_PASSWORD_CONFIRM"
            elif semantic_act.service == "audio":
                workflow_type = "VOLUME_ADJUST"
            elif semantic_act.service == "app_disambiguation":
                workflow_type = "APP_WEB_DISAMBIGUATION"
            else:
                workflow_type = "MEDIA_PLAY"

            self.core.dialog_manager.set_lock(
                workflow_type=workflow_type,
                required_slots=[semantic_act.missing_slot or "media_target"],
                target_plugin=semantic_act.service,
                target_action=semantic_act.action,
                prompt_question=semantic_act.clarification_prompt
                or "Kaunsa gaana play karun, Boss?",
                initial_slots=semantic_act.parameters or {},
            )
            self.core.state_machine.transition_to(SystemState.RESPONDING)
            resp = semantic_act.clarification_prompt or "Kaunsa gaana play karun, Boss?"
            self.core.conversation_manager.complete_turn(turn, resp)
            self.core.state_machine.transition_to(SystemState.IDLE)
            return True, resp

        elif self.core.plugin_manager and semantic_route == "PLUGIN":
            from core.execution.adapter import OutcomeAdapter
            from core.execution.plugin_verifier import PluginVerificationBridge
            self.core.state_machine.transition_to(SystemState.EXECUTING)
            plugin_params = semantic_act.parameters or {}
            if semantic_act.service == "system" and semantic_act.action in (
                "clear_temp_files",
                "empty_recycle_bin",
            ):
                plugin_params = {}
            # B3-B: Snapshot window count BEFORE execution (non-blocking, safe)
            _pre_window_count = 0
            try:
                _pre_window_count = PluginVerificationBridge.snapshot_window_count(
                    service=semantic_act.service,
                    params=plugin_params,
                    core=self.core,
                )
            except Exception as _snap_err:
                logger.debug("Plugin pre-snapshot error: %s", _snap_err)
            res = self.core.plugin_manager.execute_action(
                semantic_act.service,
                semantic_act.action,
                plugin_params,
            )
            self.core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if res.success:
                if semantic_act.service == "youtube":
                    if hasattr(self.core, "active_context") and self.core.active_context:
                        self.core.active_context.set_website("youtube", action=semantic_act.action)
                        media_query = semantic_act.query or semantic_act.parameters.get("query", "")
                        if media_query:
                            self.core.active_context.record_media(
                                title=media_query, source="youtube"
                            )
                elif semantic_act.service == "browser":
                    site = semantic_act.parameters.get("site", "google")
                    if hasattr(self.core, "active_context") and self.core.active_context:
                        self.core.active_context.set_website(site, action=semantic_act.action)
                        if semantic_act.action == "search_website":
                            self.core.active_context.last_search_query = (
                                semantic_act.parameters.get("query", "")
                            )
                            self.core.active_context.last_action = "search_products"
                            if isinstance(res.data, dict) and "url" in res.data:
                                self.core.active_context.url = res.data["url"]
                elif semantic_act.service in {"vlc", "excel", "windows"}:
                    app = semantic_act.parameters.get("app_name", semantic_act.service)
                    if hasattr(self.core, "active_context") and self.core.active_context:
                        self.core.active_context.set_application(app, action=semantic_act.action)
                        if semantic_act.service == "vlc":
                            media_title = (
                                semantic_act.query
                                or semantic_act.parameters.get("target")
                                or semantic_act.parameters.get("file_path")
                                or ""
                            )
                            if media_title:
                                self.core.active_context.record_media(
                                    title=media_title, source="vlc"
                                )

                # Reinforce successful pattern in LCE
                if (
                    hasattr(self.core, "learning_manager")
                    and self.core.learning_manager
                    and hasattr(self.core.learning_manager, "lce")
                    and lce_tokens
                ):
                    try:
                        self.core.learning_manager.lce.record_success(
                            lce_tokens,
                            intent=semantic_act.intent,
                            entities=semantic_act.parameters,
                            context_key=ctx_key,
                        )
                    except Exception as e:
                        logger.warning(f"Error recording LCE pattern: {e}")

                if isinstance(res.data, dict):
                    sensitive_display = res.data.get("sensitive_display")
                    if isinstance(sensitive_display, dict):
                        self.core._pending_sensitive_display = sensitive_display
                    if res.data.get("requires_confirmation") and hasattr(
                        self.core, "dialog_manager"
                    ):
                        self.core.dialog_manager.set_pending_system_action(
                            action=res.data.get("action", "shutdown"),
                            language=res.data.get("language", "hi"),
                            query=turn.normalized_input,
                        )
                    resp_msg = (
                        res.data.get("formatted_answer")
                        or res.data.get("message")
                        or getattr(res, "message", "")
                        or f"Executed {semantic_act.action} successfully."
                    )
                else:
                    resp_msg = (
                        getattr(res, "message", "")
                        or f"Executed {semantic_act.action} successfully."
                    )
                if semantic_act.action in ("clear_temp_files", "empty_recycle_bin"):
                    if hasattr(self.core, "active_context") and self.core.active_context:
                        self.core.active_context.update_command_context(
                            intent=semantic_act.intent,
                            action=semantic_act.action,
                            entities=semantic_act.parameters or {},
                            service=semantic_act.service,
                            raw_command=getattr(turn, "raw_input", ""),
                            success=True,
                        )
                    from core.natural_responses import NaturalResponseSynthesizer
                    user_lang = NaturalResponseSynthesizer.detect_language(
                        getattr(turn, "raw_input", "") or getattr(turn, "normalized_input", "")
                    )
                    is_repeat = bool((semantic_act.parameters or {}).get("is_repeat", False))
                    exclude_personal = bool((semantic_act.parameters or {}).get("exclude_personal_files", False))
                    orig_msg = res.data.get("message", "") if isinstance(res.data, dict) else ""
                    if not orig_msg or "items remove hue aur" in orig_msg or exclude_personal:
                        resp_msg = NaturalResponseSynthesizer.system_maintenance(
                            semantic_act.action,
                            target="temp" if "temp" in semantic_act.action else "recycle_bin",
                            is_repeat=is_repeat,
                            language=user_lang,
                            safety_reassurance=exclude_personal,
                        )
                self.core.conversation_manager.complete_turn(turn, resp_msg)
                self.core.state_machine.transition_to(SystemState.IDLE)
                self.core.action_logger.log_success(resp_msg, turn.execution_time_ms)
                self.core._record_turn_feedback(
                    turn=turn,
                    goal=f"{semantic_act.service}.{semantic_act.action}",
                    steps=[{
                        "plugin": semantic_act.service,
                        "action": semantic_act.action,
                        "parameters": semantic_act.parameters,
                    }],
                    execution_results=[res],
                    success=True,
                    category=semantic_act.service,
                    intent_name=f"nlu_{semantic_act.intent.lower()}",
                )
                # B3-A/B3-B: Wire outcome infrastructure with physical verification (additive, non-fatal)
                try:
                    # B3-B: Perform physical verification if service is verifiable
                    _phys_vr = None
                    try:
                        if PluginVerificationBridge.is_verifiable(semantic_act.service, semantic_act.action):
                            _phys_vr = PluginVerificationBridge.verify(
                                service=semantic_act.service,
                                action=semantic_act.action,
                                params=plugin_params,
                                plugin_result=res,
                                core=self.core,
                                initial_window_count=_pre_window_count,
                            )
                    except Exception as _vr_err:
                        logger.debug("Plugin physical verification error: %s", _vr_err)
                    # Adapt with real VerificationResult if available
                    _adapted = OutcomeAdapter.from_plugin_result(
                        res,
                        requested_action=f"{semantic_act.service}.{semantic_act.action}",
                        target=str(plugin_params),
                        action_type="plugin",
                    )
                    # Inject physical VerificationResult when present (upgrades UNVERIFIED -> VERIFIED or FAILED)
                    if _phys_vr is not None:
                        from core.execution.models import ExecutionState
                        _adapted.verification_result = _phys_vr
                        if _phys_vr.verified:
                            _adapted.status = ExecutionState.SUCCESS
                        elif _phys_vr.state == ExecutionState.UNVERIFIED:
                            pass  # stays UNVERIFIED
                        else:
                            _adapted.status = ExecutionState.FAILED
                    ExecutionOutcomeHook.process_outcome(
                        self.core,
                        turn,
                        _adapted,
                        source=getattr(turn, "source", "user") or "user",
                    )
                except Exception as _hook_err:
                    logger.debug("Plugin OutcomeHook (success) note: %s", _hook_err)
                return True, resp_msg
            else:
                err_msg = (
                    (
                        res.data.get("message")
                        if isinstance(res.data, dict) and res.data.get("message")
                        else None
                    )
                    or res.error
                    or f"Failed to execute on {semantic_act.service}."
                )
                if (
                    semantic_act.service == "youtube"
                    and semantic_act.action == "search_and_play"
                    and re.search(r"\b(?:kaunsi|kaunsa|which)\b", err_msg, flags=re.IGNORECASE)
                ):
                    self.core.dialog_manager.set_lock(
                        workflow_type="YOUTUBE_PLAY",
                        required_slots=["media_target"],
                        target_plugin="youtube",
                        target_action="search_and_play",
                        prompt_question=err_msg,
                    )
                self.core.conversation_manager.complete_turn(turn, err_msg)
                self.core.state_machine.transition_to(SystemState.IDLE)
                self.core.action_logger.log_error(err_msg)
                self.core._record_turn_feedback(
                    turn=turn,
                    goal=f"{semantic_act.service}.{semantic_act.action}",
                    steps=[{
                        "plugin": semantic_act.service,
                        "action": semantic_act.action,
                        "parameters": semantic_act.parameters,
                    }],
                    execution_results=[res],
                    success=False,
                    error_msg=err_msg,
                    category=semantic_act.service,
                    intent_name=f"nlu_{semantic_act.intent.lower()}",
                )
                # B3-A: Wire outcome infrastructure (additive, non-fatal)
                try:
                    _adapted_fail = OutcomeAdapter.from_plugin_result(
                        res,
                        requested_action=f"{semantic_act.service}.{semantic_act.action}",
                        target=str(semantic_act.parameters or {}),
                        action_type="plugin",
                    )
                    ExecutionOutcomeHook.process_outcome(
                        self.core,
                        turn,
                        _adapted_fail,
                        source=getattr(turn, "source", "user") or "user",
                    )
                except Exception as _hook_err:
                    logger.debug("Plugin OutcomeHook (failure) note: %s", _hook_err)
                return True, err_msg

        return False, None
