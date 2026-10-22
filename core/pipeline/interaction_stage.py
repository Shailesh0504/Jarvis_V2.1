# core/pipeline/interaction_stage.py
"""
Interaction Stage for Jarvis V2.1 Pipeline.
Handles:
- Active workflow cancel checks
- Authoritative interaction gating (voice, cli, gui)
- Barge-in audio cutoff
- Chime playback
- Standalone wake word response
- Interruption and stop session handling
"""

import logging
from typing import Any, Optional, Tuple

from core.event_bus import WakeWordDetected
from core.interaction_gate import GateDecision, InteractionGate
from core.state import SystemState

logger = logging.getLogger("jarvis.pipeline.interaction")


class InteractionStage:
    """Evaluates user interaction gate, wake words, and barge-in interruptions."""

    def __init__(self, core: Any):
        self.core = core

    def process(self, raw_input: str, source: str = "cli") -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Processes initial interaction gating.
        
        Returns:
            (handled, early_response, effective_input)
            - If handled is True: early_response is returned to the user immediately.
            - If handled is False and effective_input is None: input was dropped/ignored by gate.
            - If handled is False and effective_input is str: proceed to next pipeline stage.
        """
        core = self.core
        # 1. Desktop workflow cancellation check
        if getattr(core, "desktop_workflows", None) and core.desktop_workflows.planner.CANCEL_PATTERN.fullmatch(raw_input.strip()):
            if core.desktop_workflows.pending_plan or core.desktop_workflows.executor.active_plan_id:
                handled, response, _ = core.desktop_workflows.try_handle(raw_input)
                if handled:
                    return True, response, None

        # 2. Gate Decision Evaluation
        is_explicit = (source in ("gui", "cli", "test"))
        gate_decision = None

        if source == "voice_gated":
            is_speaking = False
            if hasattr(core, "tts_manager") and core.tts_manager:
                is_speaking = core.tts_manager.is_speaking()
            elif hasattr(core, "interaction_gate") and core.interaction_gate:
                is_speaking = core.interaction_gate._is_tts_speaking
            ww_res = core.interaction_gate.wake_detector.detect(raw_input) if hasattr(core, "interaction_gate") else None
            is_standalone = bool(ww_res and ww_res.detected and ww_res.is_standalone)
            gate_decision = GateDecision(
                accepted=True,
                command=raw_input,
                reason="voice_gated",
                is_barge_in=is_speaking,
                is_standalone_wake=is_standalone,
                matched_variant=ww_res.matched_variant if ww_res and ww_res.detected else "",
                position=ww_res.position if ww_res and ww_res.detected else "none"
            )
        elif hasattr(core, "interaction_gate") and core.interaction_gate:
            gate_decision = core.interaction_gate.evaluate(raw_input, is_explicit_listen=is_explicit)
        else:
            gate_decision = GateDecision(accepted=True, command=raw_input, reason="default_accept")

        if not gate_decision.accepted:
            # Silently drop non-accepted background chatter
            return True, "", None

        # 3. Handle real-time Barge-In interruption (audio cutoff < 20ms)
        if gate_decision.is_barge_in and hasattr(core, "interrupt_active_speech"):
            core.interrupt_active_speech(reason=gate_decision.reason or "barge_in", interrupting_text=raw_input)

        # 4. Wake word detected: play chime & emit event
        if gate_decision.matched_variant or gate_decision.is_standalone_wake:
            try:
                from voice.chime import play_wake_chime_async
                play_wake_chime_async()
            except Exception:
                pass
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.WAKE_DETECTED)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit_domain_event(
                    WakeWordDetected(
                        wake_word=gate_decision.matched_variant or "jarvis",
                        position=gate_decision.position or "prefix",
                        cleaned_command=gate_decision.command
                    )
                )

        # 5. Stop command / Interruption phrase
        if gate_decision.reason in ("stop_command", "interruption_phrase"):
            if hasattr(core, "dialog_manager") and core.dialog_manager and (
                core.dialog_manager.has_pending_system_action()
                or core.dialog_manager.has_active_lock()
                or core.dialog_manager.has_pending_proposal()
                or core.dialog_manager.has_pending_learning()
            ):
                effective_input = raw_input
            else:
                if hasattr(core, "session_manager") and core.session_manager:
                    core.session_manager.end_session()
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                resp = "Theek hai Boss, ruk gaya."
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                return True, resp, None
        else:
            effective_input = gate_decision.command if gate_decision.command else raw_input

        # 6. Standalone wake word response
        if gate_decision.is_standalone_wake:
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            resp = "Yes, I'm listening."
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            return True, resp, None

        return False, None, effective_input
