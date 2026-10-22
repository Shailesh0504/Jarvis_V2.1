# core/confirmation_manager.py
"""
Centralized Reusable Confirmation State Machine for Jarvis V2.1.
Authoritative manager for all sensitive / destructive actions requiring explicit user confirmation:
- System restart & shutdown
- Process kill / application close
- File / directory deletion
- Logout / session termination
- Data clear / format
"""

from dataclasses import dataclass, field
import logging
import os
import re
import sys
import time
from typing import Any, Callable, Dict, Optional, Tuple

from core.confirmation import (
    ConfirmationType,
    classify_confirmation,
    is_affirmation,
    is_cancellation,
    is_ambiguous,
    normalize_confirmation_text
)

logger = logging.getLogger("jarvis.core.confirmation")


@dataclass
class PendingConfirmation:
    """Represents a pending confirmation awaiting user approval or rejection."""
    action: str                                     # e.g. "restart_computer", "shutdown_computer", "delete_file"
    parameters: Dict[str, Any] = field(default_factory=dict)
    target_plugin: str = ""                         # e.g. "system", "windows", "filesystem"
    target_action: str = ""                         # e.g. "shutdown_pc", "kill_process"
    prompt: str = ""                                # Clarification prompt question
    language: str = "hi"                            # "hi" or "en"
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 60.0)
    description: str = ""                           # Human-readable summary
    callback: Optional[Callable[..., Any]] = None   # Optional direct execution callback
    affirmative_response: str = ""                  # Custom natural affirmative response
    cancellation_response: str = ""                 # Custom natural cancellation response

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class ConfirmationManager:
    """
    Dedicated confirmation manager and state machine.
    
    Guarantees:
    1. Safety: Destructive actions never execute without explicit affirmative confirmation.
    2. Priority: Active confirmations are evaluated before normal intent routing.
    3. Multi-lingual: Supports English, Roman Hindi, Devanagari Hindi, and natural Hinglish.
    4. Ambiguity Resolution: Unclear responses prompt for clarification while keeping the action pending.
    5. Timeout Protection: Expired confirmations auto-cancel safely.
    """

    def __init__(self, default_timeout_seconds: float = 60.0):
        self.default_timeout_seconds = default_timeout_seconds
        self.pending: Optional[PendingConfirmation] = None

    def request_confirmation(
        self,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        prompt: str = "",
        language: str = "hi",
        timeout_seconds: Optional[float] = None,
        target_plugin: str = "system",
        target_action: str = "",
        description: str = "",
        callback: Optional[Callable[..., Any]] = None,
        affirmative_response: str = "",
        cancellation_response: str = "",
    ) -> str:
        """
        Registers a pending confirmation and returns the prompt question.
        """
        now = time.time()
        timeout = timeout_seconds or self.default_timeout_seconds
        target_act = target_action or action

        if not prompt:
            is_restart = "restart" in action.lower()
            if language == "en":
                prompt = (
                    "Are you sure you want to restart the computer? Please confirm (yes/no)."
                    if is_restart else
                    "Are you sure you want to shut down the computer? Please confirm (yes/no)."
                )
            else:
                prompt = (
                    "Boss, kya aap sach me system restart karna chahte hain? Confirm karne ke liye 'haan' ya 'nahi' boliye."
                    if is_restart else
                    "Boss, kya main computer shutdown (band) kar doon? Confirm karne ke liye 'haan' ya 'nahi' boliye."
                )

        self.pending = PendingConfirmation(
            action=action.lower(),
            parameters=parameters or {},
            target_plugin=target_plugin,
            target_action=target_act,
            prompt=prompt,
            language=language,
            created_at=now,
            expires_at=now + timeout,
            description=description or action,
            callback=callback,
            affirmative_response=affirmative_response,
            cancellation_response=cancellation_response,
        )
        logger.info(
            "ConfirmationManager: Requested confirmation for action='%s' (plugin='%s', timeout=%.1fs)",
            action, target_plugin, timeout
        )
        return prompt

    def has_pending_confirmation(self) -> bool:
        """Returns True if a confirmation object is set."""
        return self.pending is not None

    def is_expired(self) -> bool:
        """Returns True if the current confirmation has expired."""
        return bool(self.pending and self.pending.is_expired)

    def get_pending_confirmation(self) -> Optional[PendingConfirmation]:
        """Returns the current pending confirmation."""
        return self.pending

    def clear_confirmation(self) -> None:
        """Clears any pending confirmation."""
        if self.pending:
            logger.debug("ConfirmationManager: Cleared pending confirmation for '%s'", self.pending.action)
        self.pending = None

    def classify_confirmation(self, user_text: str) -> ConfirmationType:
        """Classifies user input using centralized patterns."""
        return classify_confirmation(user_text)

    def handle_confirmation(self, user_text: str, core: Any) -> Tuple[bool, str]:
        """
        Evaluates the user utterance against the active confirmation.
        Returns: (handled: bool, response_message: str)
        """
        if not self.pending:
            return False, ""

        pending = self.pending
        lang = pending.language

        # 1. Check for Expiration
        if pending.is_expired:
            self.clear_confirmation()
            logger.info("ConfirmationManager: Confirmation for '%s' expired.", pending.action)
            if lang == "en":
                return True, "Confirmation timed out, so I did not execute the action."
            return True, "Confirmation timeout ho gaya, isliye maine action execute nahi kiya."

        decision = self.classify_confirmation(user_text)

        # 2. Rejection / Cancellation (NO)
        if decision == ConfirmationType.NEGATIVE:
            self.clear_confirmation()
            logger.info("ConfirmationManager: User explicitly rejected '%s'.", pending.action)
            if pending.cancellation_response:
                return True, pending.cancellation_response
            is_restart = "restart" in pending.action.lower()
            if lang == "en":
                return True, "Cancelled Boss! System operation aborted."
            else:
                act_str = "restart" if is_restart else "action"
                return True, f"Theek hai Boss, system {act_str} cancel kar diya gaya hai. Main active hoon."

        # 3. Affirmative Confirmation (YES)
        if decision == ConfirmationType.AFFIRMATIVE:
            self.clear_confirmation()
            logger.info("ConfirmationManager: User explicitly confirmed '%s'. Executing...", pending.action)
            return self._execute_pending_action(pending, core)

        # 4. Ambiguous Response (Clarification Required)
        if decision == ConfirmationType.AMBIGUOUS:
            logger.info("ConfirmationManager: User response '%s' was ambiguous. Requesting clarification.", user_text)
            # Re-affirm and extend timeout slightly for the clarification turn
            pending.expires_at = time.time() + min(self.default_timeout_seconds, 45.0)
            is_restart = "restart" in pending.action.lower()
            if lang == "en":
                if is_restart:
                    return True, "Please confirm. Do you want to restart the computer? Yes or no?"
                return True, f"Please confirm. Do you want to proceed with {pending.description or pending.action}? Yes or no?"
            else:
                if is_restart:
                    return True, "Please confirm. Kya computer restart karna hai? Haan ya nahi?"
                return True, f"Please confirm. Kya {pending.description or pending.action} karna hai? Haan ya nahi?"

        # 5. Unrelated Utterance
        # The user said something unrelated (e.g. "open chrome", "what time is it").
        # Safety requirement: Do NOT execute destructive action.
        # Clear confirmation so user can continue their new task, and return (False, "")
        # to allow normal pipeline routing.
        self.clear_confirmation()
        logger.info("ConfirmationManager: Unrelated query '%s' received. Clearing confirmation.", user_text)
        return False, ""

    def _execute_pending_action(self, pending: PendingConfirmation, core: Any) -> Tuple[bool, str]:
        """Executes the confirmed destructive action with error handling and real feedback."""
        is_restart = "restart" in pending.action.lower()
        is_shutdown = "shutdown" in pending.action.lower() or "band" in pending.action.lower()
        lang = pending.language

        # Determine if running under pytest / test mode
        is_test = "pytest" in sys.modules or os.environ.get("JARVIS_TEST_MODE") == "1"
        execute_os = not is_test

        exec_params = dict(pending.parameters)
        exec_params["confirmed"] = True
        exec_params["execute_os"] = execute_os
        exec_params["language"] = lang
        if is_restart:
            exec_params["restart"] = True

        exec_error = None
        exec_success = True

        # Execution path A: Direct callback
        if pending.callback and callable(pending.callback):
            try:
                pending.callback(**exec_params)
            except Exception as e:
                exec_success = False
                exec_error = str(e)
                logger.error("ConfirmationManager callback error: %s", e)

        # Execution path B: Plugin Manager
        elif hasattr(core, "plugin_manager") and core.plugin_manager:
            plugin_name = pending.target_plugin or "system"
            action_name = pending.target_action or "shutdown_pc"
            try:
                res = core.plugin_manager.execute_action(plugin_name, action_name, exec_params)
                if res and hasattr(res, "success") and not res.success:
                    exec_success = False
                    exec_error = getattr(res, "error", "Execution failed")
            except Exception as e:
                exec_success = False
                exec_error = str(e)
                logger.error("ConfirmationManager plugin execution error: %s", e)

        if not exec_success and exec_error:
            if lang == "en":
                return True, f"Action execution failed: {exec_error}"
            act_label = "Restart" if is_restart else "Shutdown" if is_shutdown else "Action"
            return True, f"{act_label} command execute nahi ho paya: {exec_error}"

        if pending.affirmative_response:
            return True, pending.affirmative_response

        # Standard affirmative feedback
        if lang == "en":
            if is_restart:
                return True, "Restarting the computer now."
            if is_shutdown:
                return True, "Shutting down computer now. Goodbye!"
            return True, f"Executed {pending.description or pending.action} successfully."
        else:
            if is_restart:
                return True, "Theek hai Boss, system restart ho raha hai. Abhi milte hain!"
            if is_shutdown:
                return True, "Theek hai Boss, computer shutdown kar raha hoon. Alvida aur apna khayal rakhna!"
            return True, f"Theek hai Boss, {pending.description or pending.action} kar diya gaya hai."
