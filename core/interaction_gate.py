# core/interaction_gate.py
"""
Authoritative Interaction Gate for Jarvis V2.
Guarantees that raw/background speech is strictly gated before reaching
IntentDetector, CommandRouter, ConversationEngine, Memory, or LLM.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import threading
import time
from typing import Callable, Optional

from voice.wake_word import WakeWordDetector, WakeWordMatchResult

logger = logging.getLogger("jarvis.core.gate")


class InteractionState(str, Enum):
    IDLE = "idle"                   # Default Standby: Only wake words are accepted. Normal speech is ignored.
    WAKE_DETECTED = "wake_detected" # Wake word matched; command being queued/processed.
    LISTENING = "listening"         # Explicit listening (Listen button clicked or active session window).
    PROCESSING = "processing"       # Brain / Plugin executing.
    RESPONDING = "responding"       # TTS audio playback. STT input is strictly suppressed.
    STOPPED = "stopped"             # Voice system off.


@dataclass
class GateDecision:
    accepted: bool
    command: str = ""
    reason: str = ""                # "wake_word_detected", "explicit_listening", "ignored_idle", "suppressed_tts", "stop_command", "interruption_phrase", "barge_in_active_session"
    state: InteractionState = InteractionState.IDLE
    is_standalone_wake: bool = False
    matched_variant: str = ""
    position: str = "none"
    is_barge_in: bool = False
    attention_score: float = 1.0


class InteractionGate:
    """
    Central Authoritative Gatekeeper for all Voice and Speech-to-Text interactions.
    
    Rule 1 (IDLE): Only valid wake-word triggers are accepted. Normal speech is discarded.
    Rule 2 (LISTENING): Explicit button activation or active dialogue session accepts commands directly.
    Rule 3 (RESPONDING): Microphone input is suppressed during TTS playback to prevent self-voice echo,
           UNLESS barge_in_enabled is True and an interruption phrase, wake word, or active command is detected.
    Rule 4 (POST-EXECUTION): Reverts to IDLE after a single command completes unless continuous mode is active.
    """

    def __init__(
        self,
        wake_detector: Optional[WakeWordDetector] = None,
        session_timeout: float = 10.0,
        continuous_mode: bool = False,
        max_session_commands: int = 3,
        barge_in_enabled: bool = False,
        tts_text_getter: Optional[Callable[[], str]] = None,
    ):
        self.wake_detector = wake_detector or WakeWordDetector()
        self.session_timeout = session_timeout
        self.continuous_mode = continuous_mode
        self.max_session_commands = max(1, int(max_session_commands))
        self._remaining_commands = 0
        self.barge_in_enabled = barge_in_enabled
        self._get_active_spoken_text = tts_text_getter

        self.state = InteractionState.IDLE
        self._is_tts_speaking = False
        self._last_tts_finish_time = 0.0
        self._last_spoken_text = ""
        self._last_activity_time = 0.0

        self._lock = threading.Lock()
        self._state_listener: Optional[Callable[[InteractionState], None]] = None

    def set_tts_text_getter(self, getter: Callable[[], str]) -> None:
        """Sets callback to query currently spoken chunk for acoustic echo cancellation."""
        self._get_active_spoken_text = getter

    def set_state_listener(self, listener: Callable[[InteractionState], None]) -> None:
        self._state_listener = listener

    def _transition_to(self, new_state: InteractionState) -> None:
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            logger.debug(f"INTERACTION_STATE: {old_state.value.upper()} -> {new_state.value.upper()}")
            if self._state_listener:
                try:
                    self._state_listener(new_state)
                except Exception as e:
                    logger.debug(f"State listener callback error: {e}")

    def set_tts_speaking(self, is_speaking: bool, text: str = "") -> None:
        """Sets the TTS playback state to prevent acoustic feedback / self-triggering."""
        with self._lock:
            self._is_tts_speaking = is_speaking
            if text:
                self._last_spoken_text = text
            elif self._get_active_spoken_text:
                try:
                    active = self._get_active_spoken_text()
                    if active:
                        self._last_spoken_text = active
                except Exception:
                    pass

            if is_speaking:
                self._transition_to(InteractionState.RESPONDING)
            else:
                self._last_tts_finish_time = time.time()
                # Revert to IDLE or LISTENING after speaking completes
                if self.continuous_mode or (
                    self._remaining_commands > 0
                    and time.time() - self._last_activity_time < self.session_timeout
                ):
                    if self._remaining_commands > 0:
                        self._last_activity_time = time.time()
                    self._transition_to(InteractionState.LISTENING)
                else:
                    self._transition_to(InteractionState.IDLE)

    def is_tts_suppressed(self) -> bool:
        """Checks if input should be suppressed due to TTS playback or cooldown."""
        with self._lock:
            if self._is_tts_speaking:
                return True
            if time.time() - self._last_tts_finish_time < 0.4:
                return True
            return False

    def activate_explicit_listening(self) -> None:
        """Turns microphone monitoring on without bypassing the wake-word gate."""
        with self._lock:
            self._remaining_commands = 0
            self._transition_to(InteractionState.IDLE)
            logger.info("Microphone monitoring active; waiting for wake word.")

    def authorize_followup(self) -> None:
        """Authorize one wake-free reply after Jarvis asks a clarification."""
        with self._lock:
            self._remaining_commands = 1
            self._last_activity_time = time.time()
            if not self._is_tts_speaking:
                self._transition_to(InteractionState.LISTENING)
            logger.info("INTERACTION_STATE: One contextual follow-up authorized.")

    def deactivate_listening(self) -> None:
        """Returns the gate to IDLE standby mode."""
        with self._lock:
            self._transition_to(InteractionState.IDLE)
            self._remaining_commands = 0
            logger.info("INTERACTION_STATE: Reverted to IDLE standby mode.")

    def is_stop_command(self, text: str) -> bool:
        """Detects explicit session termination phrases."""
        lowered = text.lower().strip()
        stop_phrases = [
            "stop listening", "stop voice", "bas jarvis", "bas karo jarvis",
            "shant ho jao", "chup ho jao", "cancel voice", "exit voice"
        ]
        if any(p in lowered for p in stop_phrases):
            return True
        if lowered in ("stop", "cancel", "bas", "bas karo"):
            return True
        return False

    def is_interruption_phrase(self, text: str) -> bool:
        """Detects barge-in interruption phrases (Hindi/English/Hinglish)."""
        import re
        lowered = text.lower().strip()
        phrases = [
            "stop listening", "stop voice", "bas jarvis", "bas karo jarvis",
            "shant ho jao", "chup ho jao", "cancel voice", "exit voice",
            "ruk jao", "ruko", "ruk", "chup", "chup raho", "shant", "bolna band karo",
            "shut up", "nahi ye karo", "nahi ruko", "arre suno", "ek minute", "wait"
        ]
        words = set(re.findall(r"\b\w+\b", lowered))
        single_word_stops = {"stop", "cancel", "bas", "ruko", "ruk", "chup", "shant", "wait"}
        if words.intersection(single_word_stops):
            return True
        return any(p in lowered for p in phrases)

    def extract_barge_in_command(self, text: str) -> Optional[str]:
        """
        Extracts an alternate command if the interruption contains one,
        e.g., 'nahi ye karo Brave kholo' -> 'Brave kholo',
              'ruko Brave kholo' -> 'Brave kholo'.
        Returns None if utterance is purely a stop phrase.
        """
        import re
        raw = text.strip()
        lowered = raw.lower()
        pure_stops = {
            "stop", "ruk jao", "ruko", "ruk", "chup", "chup raho", "shant",
            "cancel", "bas karo", "bas", "bolna band karo", "shut up",
            "stop listening", "stop voice", "bas jarvis", "bas karo jarvis",
            "shant ho jao", "chup ho jao", "cancel voice", "exit voice", "wait"
        }
        if lowered in pure_stops:
            return None

        patterns = [
            r"^(?:nahi\s+ye\s+karo|nahi\s+ruko|nahi\s+bhai|ruk\s+jao|ruko|ruk|arre\s+suno|ek\s+minute|wait)[,\s]+(.+)$",
            r"^(?:stop|chup|shant|cancel)[,\s]+(.+)$"
        ]
        for pat in patterns:
            m = re.match(pat, raw, flags=re.IGNORECASE)
            if m:
                trailing = m.group(1).strip()
                if trailing and len(trailing) > 1 and trailing.lower() not in ("jao", "karo", "ho jao", "raho"):
                    return trailing
        return None

    def _is_self_voice_echo(self, text: str) -> bool:
        """
        Detects if microphone input is merely acoustic echo of Jarvis's own TTS output.
        Compares words in incoming text against active spoken chunk or recently spoken text within a 2.5s window.
        """
        candidate_text = ""
        if self._is_tts_speaking:
            if self._get_active_spoken_text:
                try:
                    candidate_text = self._get_active_spoken_text()
                except Exception:
                    pass
            if not candidate_text:
                candidate_text = self._last_spoken_text
        elif (time.time() - self._last_tts_finish_time) < 2.5:
            candidate_text = self._last_spoken_text
        else:
            return False

        if not candidate_text or not candidate_text.strip():
            return False

        import re
        def tokenize(s: str) -> set:
            return set(re.findall(r"\b\w+\b", s.lower()))

        text_words = tokenize(text)
        if not text_words:
            return False

        # Exclude intentional command keywords from echo classification
        interruption_keywords = {"stop", "ruk", "ruko", "chup", "shant", "cancel", "bas", "jarvis", "wait"}
        if text_words.intersection(interruption_keywords):
            return False

        spoken_words = tokenize(candidate_text)
        if not spoken_words:
            return False

        overlap = text_words.intersection(spoken_words)
        overlap_ratio = len(overlap) / len(text_words)
        if overlap_ratio >= 0.5:
            logger.debug(f"InteractionGate: Acoustic echo detected ({overlap_ratio*100:.0f}% overlap with '{candidate_text}'): '{text}'")
            return True
        return False

    def on_command_completed(self) -> None:
        """Called after a command finishes execution to manage state transition."""
        with self._lock:
            if self.continuous_mode:
                self._last_activity_time = time.time()
                self._transition_to(InteractionState.LISTENING)
            else:
                self._transition_to(
                    InteractionState.LISTENING if self._remaining_commands > 0 else InteractionState.IDLE
                )

    def _consume_session_command(self) -> None:
        self._remaining_commands = max(0, self._remaining_commands - 1)
        self._last_activity_time = time.time()
        self._transition_to(
            InteractionState.LISTENING if self._remaining_commands > 0 else InteractionState.IDLE
        )

    def evaluate(
        self,
        text: str,
        is_explicit_listen: bool = False,
        attention_context: Optional[dict] = None
    ) -> GateDecision:
        """
        Main authoritative decision point for any incoming speech-to-text transcript.
        
        Outputs structured GateDecision:
        - STT_RECEIVED: text
        - INTERACTION_STATE: current state
        - WAKEWORD_DETECTED: True/False
        - GATE_DECISION: ACCEPT / IGNORE
        - ROUTED_TO: pipeline / none
        - IS_BARGE_IN: True if interrupted active speech / responding state
        - ATTENTION_SCORE: visual/context attention confidence weight
        """
        att_score = 1.0
        if attention_context and isinstance(attention_context, dict):
            att_score = float(attention_context.get("attention_score", 1.0))
            if attention_context.get("face_detected") is False:
                att_score = min(att_score, 0.5)

        dec = self._evaluate_inner(text=text, is_explicit_listen=is_explicit_listen)
        dec.attention_score = att_score
        return dec

    def _evaluate_inner(self, text: str, is_explicit_listen: bool = False) -> GateDecision:
        if not text or not text.strip():
            return GateDecision(accepted=False, reason="empty_text", state=self.state)

        raw = text.strip()

        with self._lock:
            was_speaking = self._is_tts_speaking

            # Typed GUI/CLI input is already an intentional direct interaction.
            # It can never create acoustic feedback loops through microphone hardware.
            # Microphone transcripts never set this flag; they remain wake-gated and subject to echo suppression.
            if is_explicit_listen:
                ww_res = self.wake_detector.detect(raw)
                if ww_res.detected:
                    from voice.chime import play_wake_chime_async
                    play_wake_chime_async()
                if ww_res.detected and ww_res.is_standalone:
                    self._remaining_commands = self.max_session_commands
                    self._last_activity_time = time.time()
                    self._transition_to(InteractionState.LISTENING)
                    return GateDecision(
                        accepted=True, command="", reason="wake_word_standalone",
                        state=InteractionState.LISTENING, is_standalone_wake=True,
                        matched_variant=ww_res.matched_variant, position="standalone",
                        is_barge_in=was_speaking
                    )
                effective_cmd = ww_res.cleaned_command if ww_res.detected and ww_res.cleaned_command else raw
                return GateDecision(
                    accepted=True, command=effective_cmd, reason="explicit_text_input",
                    state=self.state, matched_variant=ww_res.matched_variant if ww_res.detected else "",
                    position=ww_res.position if ww_res.detected else "none",
                    is_barge_in=was_speaking
                )

            # 1. Check TTS playback / Self-Voice suppression (Microphone input only)
            # 1a. Fast-path check acoustic echo (during TTS or in the 2.5s post-playback window)
            if self._is_self_voice_echo(raw):
                logger.info(f"STT_RECEIVED: '{raw}' | state={self.state.value.upper()} | GATE_DECISION=IGNORE (echo) | ROUTED_TO=none")
                return GateDecision(accepted=False, reason="suppressed_echo", state=self.state)

            is_awaiting_followup = (self._remaining_commands > 0)
            suppress_cooldown = (time.time() - self._last_tts_finish_time < 0.4) and not is_awaiting_followup
            if self._is_tts_speaking or suppress_cooldown:
                if self.barge_in_enabled:

                    # 1b. Check interruption phrase (e.g. 'stop', 'ruk jao', 'chup', 'nahi ye karo Brave kholo')
                    extracted_alt = self.extract_barge_in_command(raw)
                    if extracted_alt:
                        logger.info(f"STT_RECEIVED: '{raw}' | state=RESPONDING | barge_in=True | GATE_DECISION=ACCEPT (interruption+command) | ROUTED_TO=pipeline")
                        self._consume_session_command()
                        return GateDecision(
                            accepted=True,
                            command=extracted_alt,
                            reason="barge_in_interruption_command",
                            state=InteractionState.PROCESSING,
                            is_barge_in=True
                        )

                    if self.is_interruption_phrase(raw) or self.is_stop_command(raw):
                        logger.info(f"STT_RECEIVED: '{raw}' | state=RESPONDING | barge_in=True | GATE_DECISION=ACCEPT (interruption) | ROUTED_TO=pipeline")
                        self._transition_to(InteractionState.IDLE)
                        self._remaining_commands = 0
                        return GateDecision(
                            accepted=True,
                            command="stop listening",
                            reason="interruption_phrase",
                            state=InteractionState.IDLE,
                            is_barge_in=True
                        )

                    # 1c. Check wake word
                    ww_res = self.wake_detector.detect(raw)
                    if ww_res.detected:
                        self._last_activity_time = time.time()
                        self._remaining_commands = self.max_session_commands
                        try:
                            from voice.chime import play_wake_chime_async
                            play_wake_chime_async()
                        except Exception:
                            pass
                        if ww_res.is_standalone:
                            self._transition_to(InteractionState.LISTENING)
                            return GateDecision(
                                accepted=True,
                                command="",
                                reason="wake_word_standalone",
                                state=InteractionState.LISTENING,
                                is_standalone_wake=True,
                                matched_variant=ww_res.matched_variant,
                                position="standalone",
                                is_barge_in=True
                            )
                        else:
                            self._consume_session_command()
                            return GateDecision(
                                accepted=True,
                                command=ww_res.cleaned_command,
                                reason="wake_word_detected",
                                state=InteractionState.PROCESSING,
                                matched_variant=ww_res.matched_variant,
                                position=ww_res.position,
                                is_barge_in=True
                            )

                    # 1d. Active conversation barge-in (user says new command directly during dialogue)
                    if self.state == InteractionState.LISTENING or self.continuous_mode or is_awaiting_followup:
                        self._last_activity_time = time.time()
                        self._consume_session_command()
                        try:
                            from voice.chime import play_wake_chime_async
                            play_wake_chime_async()
                        except Exception:
                            pass
                        logger.info(f"STT_RECEIVED: '{raw}' | state=LISTENING | barge_in=True | GATE_DECISION=ACCEPT | ROUTED_TO=pipeline")
                        return GateDecision(
                            accepted=True,
                            command=raw,
                            reason="barge_in_active_session",
                            state=InteractionState.PROCESSING,
                            is_barge_in=True
                        )

                    logger.debug(f"STT_RECEIVED: '{raw}' | state=RESPONDING | wakeword=False | GATE_DECISION=IGNORE (suppressed during TTS) | ROUTED_TO=none")
                    return GateDecision(accepted=False, reason="suppressed_tts", state=InteractionState.RESPONDING)
                else:
                    logger.debug(f"STT_RECEIVED: '{raw}' | state=RESPONDING | wakeword=N/A | GATE_DECISION=IGNORE (suppressed during TTS) | ROUTED_TO=none")
                    return GateDecision(accepted=False, reason="suppressed_tts", state=InteractionState.RESPONDING)

            # 2. Check for explicit stop command when in active session or explicitly addressed
            if (self.state == InteractionState.LISTENING or is_explicit_listen) and self.is_stop_command(raw):
                self._transition_to(InteractionState.IDLE)
                self._remaining_commands = 0
                logger.info(f"STT_RECEIVED: '{raw}' | state={self.state.value.upper()} | wakeword=N/A | GATE_DECISION=ACCEPT (stop command) | ROUTED_TO=session_stop")
                return GateDecision(
                    accepted=True,
                    command="stop listening",
                    reason="stop_command",
                    state=InteractionState.IDLE
                )

            # 3. Handle Active Listening Mode (Explicit Listen button or Active Dialogue Session)
            if self.state == InteractionState.LISTENING and self._remaining_commands > 0:
                # Check session inactivity timeout if not manually forced
                if not is_explicit_listen and (time.time() - self._last_activity_time > self.session_timeout):
                    logger.info(f"Interaction session timed out ({self.session_timeout}s) -> Reverting to IDLE.")
                    self._transition_to(InteractionState.IDLE)
                    # Now fall through to IDLE check below
                else:
                    self._last_activity_time = time.time()

                    # Strip wake word if present in the command
                    ww_res = self.wake_detector.detect(raw)
                    try:
                        from voice.chime import play_wake_chime_async
                        play_wake_chime_async()
                    except Exception:
                        pass

                    if ww_res.detected and ww_res.is_standalone:
                        self._transition_to(InteractionState.LISTENING)
                        logger.info(f"STT_RECEIVED: '{raw}' | state=LISTENING | wakeword=True (standalone) | GATE_DECISION=ACCEPT | ROUTED_TO=wake_prompt")
                        return GateDecision(
                            accepted=True,
                            command="",
                            reason="wake_word_standalone",
                            state=InteractionState.LISTENING,
                            is_standalone_wake=True,
                            matched_variant=ww_res.matched_variant,
                            position="standalone"
                        )

                    effective_cmd = ww_res.cleaned_command if ww_res.detected and ww_res.cleaned_command else raw
                    self._consume_session_command()

                    logger.info(f"STT_RECEIVED: '{raw}' | state=LISTENING | wakeword={'True' if ww_res.detected else 'N/A'} | GATE_DECISION=ACCEPT | ROUTED_TO=pipeline")
                    return GateDecision(
                        accepted=True,
                        command=effective_cmd,
                        reason="wake_session",
                        state=InteractionState.PROCESSING,
                        matched_variant=ww_res.matched_variant if ww_res.detected else "",
                        position=ww_res.position if ww_res.detected else "none"
                    )

            # 4. IDLE / Standby Mode: STRICT Wake-Word Gating
            ww_res = self.wake_detector.detect(raw)

            if not ww_res.detected:
                # NO WAKE WORD IN IDLE: Completely discard the transcript!
                logger.debug(f"STT_RECEIVED: '{raw}' | state=IDLE | wakeword=False | GATE_DECISION=IGNORE | ROUTED_TO=none")
                return GateDecision(
                    accepted=False,
                    reason="ignored_idle",
                    state=InteractionState.IDLE
                )

            # WAKE WORD DETECTED IN IDLE!
            self._last_activity_time = time.time()
            self._remaining_commands = self.max_session_commands
            try:
                from voice.chime import play_wake_chime_async
                play_wake_chime_async()
            except Exception:
                pass

            if ww_res.is_standalone:
                # Standalone "Jarvis" -> transition to LISTENING for next utterance
                self._transition_to(InteractionState.LISTENING)
                logger.info(f"STT_RECEIVED: '{raw}' | state=WAKE_DETECTED | wakeword=True (variant='{ww_res.matched_variant}') | GATE_DECISION=ACCEPT (standalone wake) | ROUTED_TO=wake_prompt")
                return GateDecision(
                    accepted=True,
                    command="",
                    reason="wake_word_standalone",
                    state=InteractionState.LISTENING,
                    is_standalone_wake=True,
                    matched_variant=ww_res.matched_variant,
                    position="standalone"
                )
            else:
                # Attached command (e.g. "Jarvis, Chrome kholo" / "meri awaaz sun rahe ho Jarvis")
                self._consume_session_command()
                logger.info(f"STT_RECEIVED: '{raw}' | state=WAKE_DETECTED | wakeword=True (variant='{ww_res.matched_variant}') | GATE_DECISION=ACCEPT | ROUTED_TO=pipeline")
                return GateDecision(
                    accepted=True,
                    command=ww_res.cleaned_command,
                    reason="wake_word_detected",
                    state=InteractionState.PROCESSING,
                    matched_variant=ww_res.matched_variant,
                    position=ww_res.position
                )
