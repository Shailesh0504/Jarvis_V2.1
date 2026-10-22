# core/app.py
"""Main JarvisCore application orchestrator.
Thin application composition layer coordinating bootstrap, pipeline execution,
actions, feedback, and external integration interfaces.
"""

import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from core.context import SessionContext, TurnContext
from core.conversation import ConversationManager
from core.event_bus import EventBus
from core.executor import PlanExecutor, StepExecutionResult
from core.intent import Intent, IntentType, IntentResult
from core.permissions import PermissionGuard, PermissionLevel
from core.planner import TaskPlanner, ExecutionPlan
from core.interaction_gate import InteractionGate, InteractionState, GateDecision
from core.router import CommandRouter
from core.state import StateMachine, SystemState
from core.agent import AutonomousAgent
from brain.agent import AgentReasoner
from core.laya import get_laya_core, LayaRoute

from core.bootstrap.service_initializer import ServiceInitializer
from core.pipeline.input_pipeline import InputPipeline
from core.execution.action_service import ActionService
from core.feedback.turn_feedback import TurnFeedbackService
from core.response.finalizer import ResponseFinalizer

logger = logging.getLogger("jarvis.core")


class JarvisCore:
    """Central orchestrator for Jarvis V2."""

    _EXIT_SHUTDOWN_RE = re.compile(
        r"^(?:jarvis\s+)?(?:exit|quit|shutdown|bye\s+bye|bye-bye|bye|goodbye|alvida|terminate)(?:\s+jarvis)?$|"
        r"^(?:jarvis\s+(?:ko\s+)?band\s+karo|band\s+karo\s+jarvis|jarvis\s+close\s+karo|close\s+jarvis)$",
        re.IGNORECASE
    )

    def __init__(self, config_path: str = "config.yaml"):
        ServiceInitializer.init_core_infrastructure(self, config_path=config_path)
        self._pipeline = InputPipeline(self)

    @property
    def pipeline(self) -> InputPipeline:
        if not hasattr(self, "_pipeline") or self._pipeline is None:
            self._pipeline = InputPipeline(self)
        return self._pipeline

    @pipeline.setter
    def pipeline(self, val: Any) -> None:
        self._pipeline = val

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        return ServiceInitializer.load_config(config_path)

    def take_sensitive_display(self) -> Optional[Dict[str, Any]]:
        disp = self._pending_sensitive_display
        self._pending_sensitive_display = None
        return disp

    def take_news_briefing(self) -> Optional[Dict[str, Any]]:
        briefing = self._pending_news_briefing
        self._pending_news_briefing = None
        return briefing

    def reject_fuzzy_candidate(self, typo: str, rejected_candidate: str) -> None:
        self._rejected_fuzzy_candidates.add((typo.lower().strip(), rejected_candidate.lower().strip()))

    @staticmethod
    def _ensure_response(response: Any) -> str:
        """Guarantees that every accepted command produces visible/spoken feedback."""
        return ResponseFinalizer.ensure_response(response)

    def _consume_spell_ack(self, resp: str) -> str:
        """If a silent spelling correction was applied this turn, prepend spoken ack."""
        return ResponseFinalizer.consume_spell_ack(resp, self)

    def _handle_pending_website_learning(self, user_text: str) -> Optional[str]:
        """Consume a URL supplied in response to a safe website clarification."""
        pending = self.conversation_manager.session.get_variable("pending_website_learning")
        if not pending:
            return None
        if time.time() - pending.get("created_at", 0) > 120:
            self.conversation_manager.session.active_variables.pop("pending_website_learning", None)
            return None
        cleaned = user_text.strip()
        if re.fullmatch(r"(?:nahi|nahin|cancel|rehne do|chhodo|chhod do)", cleaned, flags=re.IGNORECASE):
            self.conversation_manager.session.active_variables.pop("pending_website_learning", None)
            return "Theek hai, main is website mapping ko save nahi karunga."
        # Only a URL-like answer (or cancel) consumes the pending mapping.
        # Anything else ("Arijit Singh", "February wali", "Thoda aur", fresh commands)
        # defers so the normal pipeline routes it; the mapping stays pending (120s TTL).
        url_match = re.search(r"(?:https?://[^\s]+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+[^\s]*)", cleaned, flags=re.IGNORECASE)
        if not url_match:
            return None
        try:
            entry = self.website_knowledge.learn(pending["alias"], url_match.group(0))
        except ValueError:
            return "Yeh valid HTTP/HTTPS website URL nahi lag raha. URL dobara bhej dijiye."
        self.conversation_manager.session.active_variables.pop("pending_website_learning", None)
        return f"Samajh gaya. Ab se '{pending['alias']}' ke naam se {entry['canonical_name']} open karunga."

    def initialize_subsystems(
        self,
        memory_manager: Optional[Any] = None,
        learning_manager: Optional[Any] = None,
        brain: Optional[Any] = None,
        classifier: Optional[Any] = None,
        plugin_manager: Optional[Any] = None,
        response_generator: Optional[Any] = None
    ) -> None:
        """Inject or wire subsystems into the core engine."""
        ServiceInitializer.wire_subsystems(
            self,
            memory_manager=memory_manager,
            learning_manager=learning_manager,
            brain=brain,
            classifier=classifier,
            plugin_manager=plugin_manager,
            response_generator=response_generator
        )
        self.pipeline = InputPipeline(self)

    def set_tts_manager(self, tts_manager: Any) -> None:
        """Binds active TTSManager to core and wires acoustic echo cancellation callback."""
        self.tts_manager = tts_manager
        if hasattr(self, "interaction_gate") and self.interaction_gate:
            if hasattr(tts_manager, "get_current_spoken_chunk"):
                self.interaction_gate.set_tts_text_getter(tts_manager.get_current_spoken_chunk)
        try:
            from voice.device_manager import AudioDeviceManager
            AudioDeviceManager().set_tts_engine(tts_manager)
        except Exception:
            pass

    def interrupt_active_speech(self, reason: str = "barge_in", interrupting_text: str = "") -> None:
        """Immediately stops active TTS playback, cancels queued speech chunks, and marks turn as INTERRUPTED."""
        logger.info(f"JarvisCore: ⚡ Interrupting active speech (reason='{reason}', text='{interrupting_text}')")
        if hasattr(self, "tts_manager") and self.tts_manager:
            try:
                self.tts_manager.stop(new_generation=True)
            except Exception as e:
                logger.debug(f"Error stopping tts_manager: {e}")

        if hasattr(self, "interaction_gate") and self.interaction_gate:
            self.interaction_gate.set_tts_speaking(False)

        interrupted_turn = None
        if hasattr(self, "conversation_manager") and self.conversation_manager:
            interrupted_turn = self.conversation_manager.interrupt_active_turn(reason=reason)

        try:
            from core.event_bus import ConversationInterrupted
            turn_id = interrupted_turn.turn_id if interrupted_turn else "none"
            gen_id = getattr(self.conversation_manager, "current_generation_id", 0) if hasattr(self, "conversation_manager") else 0
            self.event_bus.emit_domain_event(
                ConversationInterrupted(
                    turn_id=turn_id,
                    previous_turn_id=turn_id,
                    generation_id=gen_id,
                    previous_generation_id=gen_id,
                    interrupting_input=interrupting_text,
                    reason=reason,
                    timestamp=time.time(),
                    interrupted_at=time.time()
                )
            )
        except Exception as e:
            logger.debug(f"Error emitting ConversationInterrupted event: {e}")

    def _on_reminder_triggered(self, event: Any) -> None:
        """Handles background reminder trigger when fired via EventBus."""
        data = getattr(event, "data", {}) or {}
        title = data.get("title", "Reminder")
        is_missed = data.get("is_missed", False)
        try:
            from plugins.reminder.plugin import format_reminder_alert
            spoken_text = format_reminder_alert(title, is_missed=is_missed, for_spoken=True)
        except Exception:
            spoken_text = (
                f"Boss, aapka ek reminder miss ho gaya tha: {title}."
                if is_missed
                else f"Boss, aapke {title} ka time ho gaya hai."
            )
        logger.info("[REMINDER_TRIGGERED] Triggered reminder: '%s' (missed=%s)", title, is_missed)
        if hasattr(self, "tts_manager") and self.tts_manager and not getattr(self, "has_active_gui", False):
            try:
                self.tts_manager.speak(spoken_text, priority=True)
            except Exception as e:
                logger.debug(f"Error speaking reminder alert: {e}")

    def shutdown(self) -> None:
        """Gracefully shuts down all background services, workers, and update monitors."""
        logger.info("JarvisCore: Shutting down core subsystems...")
        if hasattr(self, "update_manager") and self.update_manager:
            try:
                self.update_manager.stop()
            except Exception as e:
                logger.debug("Error stopping update_manager: %s", e)
        if hasattr(self, "proactive_coordinator") and self.proactive_coordinator:
            try:
                self.proactive_coordinator.stop()
            except Exception as e:
                logger.debug("Error stopping proactive_coordinator: %s", e)
        if hasattr(self, "plugin_manager") and self.plugin_manager:
            for p in list(self.plugin_manager.get_all_plugins().values()):
                try:
                    p.shutdown()
                except Exception as e:
                    logger.debug("Error shutting down plugin: %s", e)
        if hasattr(self, "archify_server") and self.archify_server:
            try:
                self.archify_server.stop()
            except Exception as e:
                logger.debug("Error stopping archify_server: %s", e)

    def _acknowledge_learning(self, correction_result: Any) -> str:
        """Produces a natural verbal acknowledgement when JARVIS learns something from the user."""
        new_val = (
            getattr(correction_result, "new_value", None)
            or getattr(correction_result, "preferred_container", None)
            or ""
        ).strip()
        concept = (
            getattr(correction_result, "concept", None)
            or getattr(correction_result, "target", None)
            or ""
        ).strip()
        ctype = str(getattr(correction_result, "correction_type", "correction")).lower()

        if "browser" in ctype or (new_val.lower() in {"chrome", "brave", "firefox", "edge"} and concept.lower() in {"browser", "web", "brouser"}):
            return f"Samajh gaya Sir. Aapka preferred browser '{new_val}' hai. Main ise yaad rakhunga."
        if "preference" in ctype and new_val and concept:
            return f"Theek hai Sir. Aapki preference noted — '{concept}' ke liye '{new_val}' use karunga."
        if new_val and concept:
            return f"Samajh gaya Sir. Aage se '{concept}' ke liye '{new_val}' use karunga."
        if new_val:
            return f"Okay Sir. '{new_val}' note kar liya hai."
        return "Samajh gaya Sir. Aapka correction save kar liya. Aage dhyan rakhunga."

    def _finalize_fast_turn(
        self,
        turn: Any,
        resp: str,
        start_time: float,
        tracker: Any,
        intent_name: str,
        source: str
    ) -> str:
        return ResponseFinalizer.finalize_fast_turn(
            self, turn=turn, resp=resp, start_time=start_time, tracker=tracker, intent_name=intent_name, source=source
        )

    def _check_target_status(self, target_value: str, query: str) -> str:
        """Inspects target status without altering state."""
        q_low = (query or "").lower()
        tv_low = (target_value or "").lower()

        clean_target = re.sub(
            r"\b(?:konse|kaun\s+se|kaunse|kis|which|kahan|kidhar|browser|brouser|browzer|broser|mein|me|par|pe|open|hai|khula)\b",
            "",
            tv_low,
            flags=re.IGNORECASE
        ).strip()
        lookup_target = clean_target if clean_target else target_value
        target_display = "YouTube" if lookup_target.lower() == "youtube" else lookup_target.capitalize()

        BROWSER_LOCATION_WORDS = (
            "konse browser", "kaun se browser", "kaunse browser", "kis browser",
            "which browser", "what browser", "kahan open hai", "kahan hai",
            "kidhar open hai", "kidhar hai", "kahan khula", "kahan chal raha",
            "brouser", "browzer", "broser", "kisi bhi browser",
        )
        is_browser_loc = (
            any(w in q_low for w in BROWSER_LOCATION_WORDS)
            or any(w in tv_low for w in ("konse", "kahan", "kidhar", "browser", "brouser", "browzer", "broser"))
            or bool(re.search(r"\b(?:kaun\s+se|kaunse|konse|kis|which|what)\s+(?:browser|brouser|browzer|broser)\b", q_low))
            or bool(re.search(r"\b(?:browser|brouser|browzer|broser)\s+(?:me(?:in)?|mein|par|pe)\b", q_low))
        )

        status_resp = self.target_engine.check_target_status(lookup_target, query)

        conf_mgr = getattr(self, "confirmation_manager", None) or getattr(getattr(self, "dialog_manager", None), "confirmation_manager", None)
        is_followup_offer = ("kya aap" in status_resp.lower() and "open" in status_resp.lower()) or ("would you like" in status_resp.lower() and "open" in status_resp.lower())
        if conf_mgr and is_browser_loc and is_followup_offer:
            is_en = "would you like" in status_resp.lower()

            def _do_open_target(**kw):
                logger.info("Executing confirmed target launch for '%s'", lookup_target)
                from core.target_engine import TargetRequest
                outcome = self.target_engine.execute(TargetRequest(target=lookup_target, action="open"))
                if hasattr(self, "active_context") and self.active_context:
                    self.active_context.set_website(lookup_target, action="open_website")
                return outcome

            conf_mgr.request_confirmation(
                action="open_target",
                parameters={"target": lookup_target, "site": lookup_target},
                prompt=f"Would you like me to open {target_display}?" if is_en else f"Kya aap {target_display} open karna chahte hain?",
                language="en" if is_en else "hi",
                timeout_seconds=60.0,
                target_plugin="browser",
                target_action="open_website",
                description=f"{target_display} open",
                callback=_do_open_target,
                affirmative_response=f"Sure Sir, opening {target_display} now." if is_en else f"Theek hai Sir, {target_display} open kar raha hoon.",
                cancellation_response=f"Alright Sir, not opening {target_display}." if is_en else f"Theek hai Sir, {target_display} open nahi kar raha hoon.",
            )

        return status_resp

    def _handle_state_dispute(self, target: Optional[str], container: Optional[str], query: str) -> str:
        """Handles conversational state disputes and corrections."""
        if not target:
            target = (
                getattr(self.active_context, "website", None)
                or getattr(self.active_context, "application", None)
                or getattr(self.active_context, "last_entity", None)
            )
        if not target and hasattr(self, "conversation_manager") and self.conversation_manager:
            try:
                recent_turns = self.conversation_manager.session.get_recent_history(limit=3)
                for t in reversed(recent_turns):
                    t_input = (getattr(t, "raw_input", "") or "").lower()
                    for cand in ("youtube", "chrome", "brave", "firefox", "edge", "spotify", "notepad", "calculator"):
                        if cand in t_input:
                            target = cand
                            break
                    if target:
                        break
            except Exception:
                pass

        clean_tgt = (target or "application").strip().lower()
        clean_tgt = re.sub(r"\b(?:to|open|hai|mein|me|bhai|yaar)\b", "", clean_tgt).strip() or "application"
        tgt_display = "YouTube" if clean_tgt == "youtube" else clean_tgt.capitalize()
        container_display = container.capitalize() if container else ""

        status_resp = self.target_engine.check_target_status(clean_tgt, query)
        is_actually_open = ("open hai" in status_resp.lower() or "chal raha hai" in status_resp.lower()) and ("nahi" not in status_resp.lower())
        is_en = bool(re.search(r"\b(?:but|however|is\s+not|isn't)\b", query, re.IGNORECASE))

        if is_actually_open:
            if is_en:
                return f"I double-checked: {tgt_display} is currently running on the system."
            return f"Maine dobara verify kiya: {tgt_display} abhi system par chal raha hai."

        if container_display:
            if is_en:
                resp = f"Apologies, I checked — {tgt_display} is not open in {container_display}. Would you like me to open {tgt_display}?"
            else:
                resp = f"Maafi chahta hoon, maine check kiya — {container_display} mein {tgt_display} open nahi hai. Kya aap chahte hain ki main {tgt_display} open kar doon?"
        else:
            if is_en:
                resp = f"Apologies, I checked — {tgt_display} is not open. Would you like me to open {tgt_display}?"
            else:
                resp = f"Maafi chahta hoon, maine check kiya — {tgt_display} open nahi hai. Kya aap chahte hain ki main {tgt_display} open kar doon?"

        conf_mgr = getattr(self, "confirmation_manager", None) or getattr(getattr(self, "dialog_manager", None), "confirmation_manager", None)
        if conf_mgr:
            def _do_open_target(**kw):
                logger.info("Executing confirmed target launch after state dispute for '%s'", clean_tgt)
                from core.target_engine import TargetRequest
                outcome = self.target_engine.execute(TargetRequest(target=clean_tgt, action="open", container=container or None))
                if hasattr(self, "active_context") and self.active_context:
                    self.active_context.set_website(clean_tgt, action="open_website")
                return outcome

            conf_mgr.request_confirmation(
                action="open_target",
                parameters={"target": clean_tgt, "container": container, "site": clean_tgt},
                prompt=f"Would you like me to open {tgt_display}?" if is_en else f"Kya aap chahte hain ki main {tgt_display} open kar doon?",
                language="en" if is_en else "hi",
                timeout_seconds=60.0,
                target_plugin="browser",
                target_action="open_website",
                description=f"{tgt_display} open",
                callback=_do_open_target,
                affirmative_response=f"Sure Sir, opening {tgt_display} now." if is_en else f"Theek hai Sir, {tgt_display} open kar raha hoon.",
                cancellation_response=f"Alright Sir, not opening {tgt_display}." if is_en else f"Theek hai Sir, {tgt_display} open nahi kar raha hoon.",
            )

        return resp

    def _try_fast_command_path(
        self,
        raw_text: str,
        normalized_input: str,
        turn: Any,
        start_time: float,
        tracker: Any,
        source: str
    ) -> Optional[str]:
        if not hasattr(self, "fast_path") or not self.fast_path:
            from core.execution.fast_path import FastPathEngine
            self.fast_path = FastPathEngine(core=self)
        return self.fast_path.try_handle(
            raw_text=raw_text,
            normalized_input=normalized_input,
            turn=turn,
            start_time=start_time,
            tracker=tracker,
            source=source,
        )

    def _dispatch_fast_route(
        self,
        turn: Any,
        laya_decision: Any,
        start_time: float,
        source: str
    ) -> Optional[str]:
        """Laya Tri-Bridge Route 1: Fast Router."""
        fast_resp = self._try_fast_command_path(
            raw_text=turn.raw_input,
            normalized_input=turn.normalized_input,
            turn=turn,
            start_time=start_time,
            tracker=getattr(self, "latency_tracker", None),
            source=source
        )
        if fast_resp is not None:
            if laya_decision and hasattr(self, "laya_core") and self.laya_core:
                try:
                    verify_out = self.laya_core.verify_execution(
                        decision=laya_decision,
                        execution_result={"success": True, "message": fast_resp},
                        core=self
                    )
                    turn.metadata["laya_verification"] = verify_out
                except Exception as _ver_exc:
                    logger.debug("Laya verification note: %s", _ver_exc)

            self.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            self.conversation_manager.complete_turn(turn, fast_resp)
            self.state_machine.transition_to(SystemState.IDLE)
            self.action_logger.log_success(fast_resp, turn.execution_time_ms)
            if self.memory_manager:
                self.memory_manager.record_interaction(
                    turn.raw_input, fast_resp, intent=getattr(turn, "intent", "fast_path") or "fast_path", source=source
                )
            self.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": fast_resp})
            return fast_resp
        return None

    def _dispatch_chat_route(
        self,
        turn: Any,
        laya_decision: Any,
        start_time: float,
        source: str
    ) -> str:
        """Laya Tri-Bridge Route 2: Chat & Reasoning."""
        return self.pipeline.conversation_handler.dispatch_chat_route(
            turn=turn, laya_decision=laya_decision, start_time=start_time, source=source
        )

    def _dispatch_agent_route(
        self,
        turn: Any,
        laya_decision: Any,
        start_time: float,
        source: str
    ) -> str:
        """Laya Tri-Bridge Route 3: Autonomous Agent Planner."""
        return self.pipeline.agent_handler.dispatch_agent_route(
            turn=turn, laya_decision=laya_decision, start_time=start_time, source=source
        )

    def process_input(self, raw_input: str, source: str = "cli") -> str:
        """Process input and remove legacy, repetitive forms of address."""
        response = ""
        with self._process_lock:
            try:
                response = self._process_input(raw_input, source=source)
            except Exception as exc:
                logger.exception("Unhandled input pipeline failure")
                try:
                    from core.logger import log_mistake, MistakeCategory
                    log_mistake(
                        category=MistakeCategory.SYNTAX_EXCEPTION if isinstance(exc, (SyntaxError, TypeError, AttributeError)) else MistakeCategory.GENERAL_FAILURE,
                        user_query=raw_input,
                        error_message=str(exc),
                        error_type=type(exc).__name__,
                        failing_module="core.app",
                        context={"source": source},
                        diagnosis=f"Unhandled exception in input pipeline: {type(exc).__name__}: {str(exc)}",
                        anti_pattern="Unhandled exception bypassing specialized intent/action handlers.",
                        recommended_fix="Add safe input validation or handler exception guard."
                    )
                except Exception:
                    pass
                if self.state_machine.current_state != SystemState.SHUTDOWN:
                    self.state_machine.transition_to(SystemState.ERROR)
                    self.state_machine.transition_to(SystemState.IDLE)
                self.event_bus.emit(
                    "core.input_failed",
                    {"source": source, "error": str(exc)},
                )
                if hasattr(self, "dialog_manager") and self.dialog_manager and self.dialog_manager.has_active_lock():
                    try:
                        self.dialog_manager.release_lock()
                    except Exception:
                        pass
                response = "Maaf kijiye, is request ko process karte waqt ek takneeki samasya aayi. Main taiyaar hoon, aap koi doosri command de sakte hain."
        if not isinstance(response, str):
            return response
        if response == "" and source in ("voice_standby", "voice_idle", "standby"):
            return ""
        if not response.strip():
            response = self._ensure_response(response)

        if hasattr(self, "response_engine") and self.response_engine:
            current_turn = self.conversation_manager.session.get_current_turn()
            is_fp = bool(current_turn and current_turn.metadata.get("is_fast_path"))
            conversation_response = bool(
                current_turn and current_turn.raw_input == raw_input
                and (current_turn.metadata.get("conversation_response") or is_fp)
            )
            intent_val = getattr(current_turn, "intent", "") if current_turn else ""
            response = self.response_engine.render_response(
                context={"user_text": raw_input, "source": source, "intent": intent_val,
                         "parameters": {"conversation_response": conversation_response}},
                default_text=response
            )
        response = re.sub(r"\s*,?\s*\bBoss\b\s*,?", " ", response, flags=re.IGNORECASE)
        response = re.sub(r"\s+([,.!?])", r"\1", response)
        response = response.strip()

        # Adapt response if user has set a brevity preference (Point 7: Consistent Personality & Preference Memory)
        prefer_short = False
        if hasattr(self, "memory_manager") and self.memory_manager and hasattr(self.memory_manager, "preferences"):
            try:
                prefer_short = str(self.memory_manager.preferences.get("brevity_preference", "")).lower() in ("short", "true", "concise")
            except Exception:
                pass
        if prefer_short:
            from core.response_style import ResponseStyleManager
            response = ResponseStyleManager.apply_brevity_preference(response, prefer_short=True)

        response = self._attach_contextual_suggestion_if_appropriate(raw_input, response, source=source)
        return response

    def _attach_contextual_suggestion_if_appropriate(
        self, raw_input: str, response: str, source: str = "cli"
    ) -> str:
        """Evaluates turn context and appends high-scoring next-step suggestion if permitted."""
        return ResponseFinalizer.attach_contextual_suggestion(self, raw_input, response, source=source)

    def _process_input(self, raw_input: str, source: str = "cli") -> str:
        """Main execution pipeline delegated cleanly to InputPipeline."""
        return self.pipeline.process(self, raw_input, source=source)

    def _handle_system_command(self, intent: Intent) -> str:
        return self.pipeline.command_handler.handle_system_command(intent)

    def _render_conversation_reply(self, text: str, fallback: str) -> str:
        """Keep early non-executable chat on the same engine as fallback chat."""
        engine = getattr(self, "conversation_engine", None)
        if engine:
            try:
                handled, response, _ = engine.process_conversation_turn(
                    text, recent_turns=self.conversation_manager.get_history(limit=6)
                )
                if handled and response and "thoda context chahiye" not in response.lower():
                    current_turn = self.conversation_manager.session.get_current_turn()
                    if current_turn:
                        current_turn.metadata["conversation_response"] = True
                    return response
            except Exception:
                logger.warning("Conversation response unavailable; using local fallback", exc_info=True)
        return fallback

    def _handle_memory_command(self, intent: Intent) -> str:
        return self.pipeline.command_handler.handle_memory_command(intent)

    def _handle_identity_query(self, text: str, raw_input: Optional[str] = None) -> Optional[str]:
        """Handles Jarvis self-identity questions via the semantic self-intent layer."""
        # Bare model disambiguation keeps its existing owner/flow (unchanged).
        cleaned = (text or "").lower().strip().rstrip("?.!")
        if cleaned in {"model", "model?", "kaunsa model", "which model"}:
            self.dialog_manager.set_lock(
                workflow_type="MODEL_QUERY", required_slots=["model_type"],
                prompt_question="AI model ya laptop model?",
            )
            return "Aap mera AI model pooch rahe hain ya laptop ka model, Boss?"

        if any(phrase in cleaned for phrase in (
            "tumhara model", "aapka model", "ai model", "which ai model",
            "kaunsa ai model", "model use kar rahe",
        )):
            provider = str(self.config.get("brain", {}).get("llm_provider", "mock")).lower()
            model = str(self.config.get("brain", {}).get("model", "default"))
            if provider == "mock":
                return "Abhi main Jarvis ke built-in conversational engine par chal raha hoon."
            if provider == "ollama":
                return f"Abhi main Ollama par {model} model use kar raha hoon."
            return f"Abhi main {provider} provider ka {model} model use kar raha hoon."

        # Semantic self-intent layer (single owner: core/semantic/self_intents.py).
        # Covers identity, creator/origin, capabilities, status, help, memory,
        # language, offline and technology intents across Hindi/Hinglish/English
        # with typo/STT tolerance. Returns None on low confidence so the normal
        # pipeline (rules / ML / LLM / fallback) continues untouched.
        try:
            from core.semantic.self_intents import detect_self_intent
            result = detect_self_intent(
                text or "",
                raw_text=raw_input if raw_input is not None else text,
                last_intent=getattr(self, "_last_self_intent", None),
            )
            if result.intent.value != "UNKNOWN" and result.response_text:
                self._last_self_intent = result.intent.value
                return result.response_text
            if result.intent.value != "UNKNOWN":
                # Detected but intentionally deferred (e.g. greeting stays with
                # the existing greeting flow). Remember context, don't answer.
                self._last_self_intent = result.intent.value
        except Exception:
            logger.debug("Self-intent layer note", exc_info=True)
        return None

    def _handle_profile_interpretation(self, interpretation: Any, turn: TurnContext) -> str:
        """Persists or retrieves a typed personal fact at structured-intent priority."""
        from brain.personal_profile import PersonalProfileExtractor
        english = bool(re.match(r"(?:my|i |i'm|what|where|do you|remember|no[, ])", turn.normalized_input, re.I))
        if interpretation.field == "summary":
            try:
                facts = []
                if self.memory_manager:
                    for fact_key, hi_label, en_label in PersonalProfileExtractor.FIELDS.values():
                        fact = self.memory_manager.get_fact(fact_key)
                        if fact and fact.get("value"):
                            facts.append(f"{en_label if english else hi_label}: {fact['value']}")
                if not facts:
                    return "I don't have any personal details saved yet." if english else "Abhi aapki koi personal baat saved nahi hai."
                return ("You told me — " if english else "Aapne bataya tha — ") + "; ".join(facts) + "."
            except Exception:
                logger.warning("Personal memory summary unavailable", exc_info=True)
                return "Abhi saved memory padh nahi pa raha. Thodi der baad dobara try karte hain."
        key, label, english_label = PersonalProfileExtractor.FIELDS[interpretation.field]
        if interpretation.intent == "USER_PROFILE_QUERY":
            turn.intent = Intent(
                name="user_profile_query", type=IntentType.MEMORY_QUERY,
                entities={"field": interpretation.field, "namespace": interpretation.namespace.value},
                raw_query=turn.normalized_input,
            )
            try:
                fact = self.memory_manager.get_fact(key) if self.memory_manager else None
            except Exception:
                logger.warning("Personal memory read unavailable", exc_info=True)
                return "Abhi saved memory padh nahi pa raha. Thodi der baad dobara try karte hain."
            if fact and fact.get("value"):
                if english:
                    return f"You told me your {english_label} is {fact['value']}."
                if interpretation.field == "interest":
                    return f"Aapne bataya tha ki aapko {fact['value']} pasand hai."
                return f"Aapka {label} {fact['value']} hai."
            if interpretation.field == "name":
                return "Aapne abhi tak apna naam mujhe nahi bataya. Aap apna naam bata sakte hain."
            return f"I don't have your {english_label} saved yet." if english else f"Aapki {label} ke baare mein abhi koi baat saved nahi hai."

        value = interpretation.value or ""
        turn.intent = Intent(
            name="user_profile_update", type=IntentType.MEMORY_STORE,
            entities={
                "field": interpretation.field, "value": value,
                "namespace": interpretation.namespace.value,
                "confidence": interpretation.confidence,
            },
            raw_query=turn.normalized_input,
        )
        if hasattr(self, "dialog_manager") and self.dialog_manager and getattr(self.dialog_manager, "pending_spelling", None):
            pending = self.dialog_manager.pending_spelling
            self.reject_fuzzy_candidate(pending["typo"], pending["correction"])
            self.dialog_manager.pending_spelling = None
        if not self.memory_manager:
            return "Abhi memory connected nahi hai, isliye ise future ke liye save nahi kar paaya."
        try:
            self.memory_manager.store_fact(key, value, category="user_profile")
            saved = self.memory_manager.get_fact(key)
            if not saved or saved.get("value") != value:
                raise ValueError("Personal fact was not persisted")
        except Exception:
            logger.warning("Personal memory write unavailable", exc_info=True)
            return "Ye baat abhi save nahi ho paayi. Main ise yaad rakhne ka vaada nahi karunga."
        self._last_profile_field = interpretation.field
        if interpretation.field == "preferred_browser":
            b_val = value.strip().lower()
            b_val = re.sub(r"\b(?:hai|bhai|browser|brouser)\b", "", b_val).strip() or "chrome"
            if hasattr(self, "learning_manager") and self.learning_manager:
                if hasattr(self.learning_manager, "preferences") and self.learning_manager.preferences:
                    self.learning_manager.preferences.set("preferred_browser", b_val)
                if hasattr(self.learning_manager, "vocabulary") and self.learning_manager.vocabulary:
                    self.learning_manager.vocabulary.learn_term("browser", b_val, category="preferred_browser")
            if hasattr(self, "active_context") and self.active_context:
                self.active_context.browser = b_val

            if english:
                if interpretation.is_correction:
                    return f"Understood Sir. Your preferred browser is {b_val.capitalize()}. I'll remember this."
                return "Okay Sir."
            if interpretation.is_correction:
                return f"Samajh gaya Sir. Aapka preferred browser {b_val.capitalize()} hai. Main ise yaad rakhunga."
            return "Okay Sir."

        if english and interpretation.field != "name":
            return f"Got it — I'll remember your {english_label}: {value}."
        if interpretation.field != "name":
            if interpretation.field == "interest":
                return f"Achha, aapko {value} pasand hai. Ye yaad rakhunga."
            return f"Theek hai, aapka {label} {value} hai. Ye yaad rakhunga."
        if interpretation.is_correction:
            return f"Theek hai, aapka naam {value} hai. Main ise yaad rakhunga."
        return f"Samajh gaya, {value}. Main aapka naam yaad rakhunga."

    def _handle_learning_command(self, intent: Intent) -> str:
        return self.pipeline.learning_handler.handle_learning_command(intent)

    def enable_auth(self) -> None:
        """Enable biometric face authentication in config and runtime."""
        self.config.setdefault("security", {}).setdefault("face_auth", {})["enabled"] = True
        if hasattr(self, "auth") and self.auth:
            self.auth.enabled = True

    def disable_auth(self) -> None:
        """Disable biometric face authentication in config and runtime."""
        self.config.setdefault("security", {}).setdefault("face_auth", {})["enabled"] = False
        if hasattr(self, "auth") and self.auth:
            self.auth.enabled = False

    def execute_action_plan(self, action_plan: Any) -> Any:
        """Authoritative unified execution of an ActionPlan."""
        return ActionService.execute_action_plan(self, action_plan)

    def execute_task_workflow(
        self,
        goal: str,
        steps: Optional[List[Any]] = None,
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str, Optional[Any]]:
        """Execute a multi-step task workflow via TaskContinuityEngine with step-by-step verification."""
        return ActionService.execute_task_workflow(
            self, goal=goal, steps=steps, execution_context=execution_context
        )

    def retrieve_experience(self, query: str, category: Optional[str] = None):
        """Retrieves relevant past experiences from Experience Learning System."""
        return TurnFeedbackService.retrieve_experience(self, query=query, category=category)

    def record_learning_experience(
        self,
        goal: str,
        steps: List[Dict[str, Any]],
        success: bool = True,
        error_msg: Optional[str] = None,
        category: str = "general"
    ):
        """Records task execution experience into the persistent learning system."""
        return TurnFeedbackService.record_learning_experience(
            self, goal=goal, steps=steps, success=success, error_msg=error_msg, category=category
        )

    def _record_turn_feedback(
        self,
        turn: TurnContext,
        goal: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        execution_results: Optional[List[Any]] = None,
        verification_results: Optional[List[Any]] = None,
        success: bool = True,
        error_msg: Optional[str] = None,
        category: str = "general",
        intent_name: Optional[str] = None
    ) -> None:
        """Authoritative Feedback Loop hook."""
        TurnFeedbackService.record_turn_feedback(
            core=self,
            turn=turn,
            goal=goal,
            steps=steps,
            execution_results=execution_results,
            verification_results=verification_results,
            success=success,
            error_msg=error_msg,
            category=category,
            intent_name=intent_name
        )
