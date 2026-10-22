# core/state.py
"""
State Machine managing System Lifecycle & Request/Workflow Lifecycle for Jarvis V2.1.
Preserves existing SystemState while adding strict RequestLifecycleState and RequestStateMachine.
"""

from enum import Enum
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("jarvis.core.state")


class SystemState(str, Enum):
    """The official system lifecycle states of Jarvis V2."""
    INITIALIZING = "INITIALIZING"
    IDLE = "IDLE"
    WAKE_DETECTED = "WAKE_DETECTED"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    THINKING = "THINKING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    RESPONDING = "RESPONDING"
    ERROR = "ERROR"
    SHUTDOWN = "SHUTDOWN"


class RequestLifecycleState(str, Enum):
    """
    The 13-state authoritative request & workflow lifecycle states for Jarvis V2.1.
    Guarantees deterministic, auditable transitions across each turn.
    """
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    UNDERSTANDING = "UNDERSTANDING"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    PLANNING = "PLANNING"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RESPONDING = "RESPONDING"


class StateMachine:
    """Deterministic System State Machine with valid transition enforcement and callback listeners."""

    def __init__(self, initial_state: SystemState = SystemState.IDLE):
        self.current_state = initial_state
        self._listeners: List[Callable[[SystemState, SystemState], None]] = []

        # Define valid transitions for state safety
        self._valid_transitions: Dict[SystemState, Set[SystemState]] = {
            SystemState.INITIALIZING: {
                SystemState.IDLE,
                SystemState.ERROR,
                SystemState.SHUTDOWN
            },
            SystemState.IDLE: {
                SystemState.WAKE_DETECTED,
                SystemState.LISTENING,
                SystemState.PROCESSING,
                SystemState.THINKING,
                SystemState.PLANNING,
                SystemState.RESPONDING,
                SystemState.SHUTDOWN
            },
            SystemState.WAKE_DETECTED: {
                SystemState.LISTENING,
                SystemState.PROCESSING,
                SystemState.THINKING,
                SystemState.RESPONDING,
                SystemState.IDLE,
                SystemState.ERROR
            },
            SystemState.LISTENING: {
                SystemState.PROCESSING,
                SystemState.THINKING,
                SystemState.IDLE,
                SystemState.ERROR
            },
            SystemState.PROCESSING: {
                SystemState.THINKING,
                SystemState.PLANNING,
                SystemState.EXECUTING,
                SystemState.RESPONDING,
                SystemState.ERROR,
                SystemState.IDLE,
                SystemState.SHUTDOWN
            },
            SystemState.THINKING: {
                SystemState.PLANNING,
                SystemState.EXECUTING,
                SystemState.RESPONDING,
                SystemState.ERROR,
                SystemState.IDLE,
                SystemState.SHUTDOWN
            },
            SystemState.PLANNING: {
                SystemState.EXECUTING,
                SystemState.RESPONDING,
                SystemState.ERROR,
                SystemState.IDLE,
                SystemState.SHUTDOWN
            },
            SystemState.EXECUTING: {
                SystemState.RESPONDING,
                SystemState.ERROR,
                SystemState.IDLE,
                SystemState.SHUTDOWN
            },
            SystemState.RESPONDING: {
                SystemState.IDLE,
                SystemState.LISTENING,
                SystemState.WAKE_DETECTED,
                SystemState.ERROR,
                SystemState.SHUTDOWN
            },
            SystemState.ERROR: {
                SystemState.IDLE,
                SystemState.SHUTDOWN
            },
            SystemState.SHUTDOWN: set()
        }

    def can_transition_to(self, target_state: SystemState) -> bool:
        if self.current_state == target_state:
            return True
        allowed = self._valid_transitions.get(self.current_state, set())
        return target_state in allowed

    def transition_to(self, new_state: SystemState) -> bool:
        """Transitions to new state if permitted, notifying registered listeners."""
        if self.current_state == new_state:
            return True

        if not self.can_transition_to(new_state):
            logger.warning(f"Illegal state transition attempted: {self.current_state} -> {new_state}")
            return False

        old_state = self.current_state
        self.current_state = new_state
        logger.info(f"State Machine: {old_state.value} -> {new_state.value}")

        # Notify transition callbacks
        for callback in self._listeners:
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.error(f"Error in state transition callback: {e}")

        return True

    def register_listener(self, callback: Callable[[SystemState, SystemState], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)


class RequestStateMachine:
    """
    Deterministic request & workflow lifecycle state machine for single-turn & multi-turn execution.
    Tracks complete audit trail of state transitions with millisecond timestamps.
    """

    def __init__(self, request_id: str = "default", initial_state: RequestLifecycleState = RequestLifecycleState.IDLE):
        self.request_id = request_id
        self.current_state = initial_state
        self._history: List[Dict[str, Any]] = [
            {"from": None, "to": initial_state.value, "timestamp": time.time(), "reason": "init"}
        ]
        self._listeners: List[Callable[[RequestLifecycleState, RequestLifecycleState, str], None]] = []

        # Directed legal transition graph
        self._valid_transitions: Dict[RequestLifecycleState, Set[RequestLifecycleState]] = {
            RequestLifecycleState.IDLE: {
                RequestLifecycleState.LISTENING,
                RequestLifecycleState.UNDERSTANDING,
                RequestLifecycleState.CANCELLED,
            },
            RequestLifecycleState.LISTENING: {
                RequestLifecycleState.UNDERSTANDING,
                RequestLifecycleState.CANCELLED,
                RequestLifecycleState.IDLE,
                RequestLifecycleState.FAILED,
            },
            RequestLifecycleState.UNDERSTANDING: {
                RequestLifecycleState.CLARIFICATION_REQUIRED,
                RequestLifecycleState.PLANNING,
                RequestLifecycleState.EXECUTING,       # Direct fast-path bypass
                RequestLifecycleState.RESPONDING,      # Direct chat/GK answer
                RequestLifecycleState.CANCELLED,
                RequestLifecycleState.FAILED,
            },
            RequestLifecycleState.CLARIFICATION_REQUIRED: {
                RequestLifecycleState.RESPONDING,
                RequestLifecycleState.UNDERSTANDING,
                RequestLifecycleState.CANCELLED,
                RequestLifecycleState.FAILED,
            },
            RequestLifecycleState.PLANNING: {
                RequestLifecycleState.WAITING_CONFIRMATION,
                RequestLifecycleState.EXECUTING,
                RequestLifecycleState.RESPONDING,
                RequestLifecycleState.CANCELLED,
                RequestLifecycleState.FAILED,
            },
            RequestLifecycleState.WAITING_CONFIRMATION: {
                RequestLifecycleState.RESPONDING,      # Ask confirmation prompt
                RequestLifecycleState.EXECUTING,       # Confirmed by user
                RequestLifecycleState.CANCELLED,       # Denied by user
                RequestLifecycleState.FAILED,
            },
            RequestLifecycleState.EXECUTING: {
                RequestLifecycleState.VERIFYING,
                RequestLifecycleState.RECOVERING,
                RequestLifecycleState.COMPLETED,
                RequestLifecycleState.FAILED,
                RequestLifecycleState.CANCELLED,
                RequestLifecycleState.RESPONDING,      # For immediate stream ack
            },
            RequestLifecycleState.VERIFYING: {
                RequestLifecycleState.COMPLETED,
                RequestLifecycleState.RECOVERING,
                RequestLifecycleState.FAILED,
                RequestLifecycleState.RESPONDING,
            },
            RequestLifecycleState.RECOVERING: {
                RequestLifecycleState.EXECUTING,       # Retry execution
                RequestLifecycleState.VERIFYING,       # Re-verify
                RequestLifecycleState.CLARIFICATION_REQUIRED, # Ask user
                RequestLifecycleState.COMPLETED,
                RequestLifecycleState.FAILED,
                RequestLifecycleState.CANCELLED,
            },
            RequestLifecycleState.COMPLETED: {
                RequestLifecycleState.RESPONDING,
                RequestLifecycleState.IDLE,
            },
            RequestLifecycleState.FAILED: {
                RequestLifecycleState.RESPONDING,
                RequestLifecycleState.IDLE,
            },
            RequestLifecycleState.CANCELLED: {
                RequestLifecycleState.RESPONDING,
                RequestLifecycleState.IDLE,
            },
            RequestLifecycleState.RESPONDING: {
                RequestLifecycleState.IDLE,
                RequestLifecycleState.LISTENING,
                RequestLifecycleState.COMPLETED,
            },
        }

    def can_transition_to(self, target_state: RequestLifecycleState) -> bool:
        if self.current_state == target_state:
            return True
        allowed = self._valid_transitions.get(self.current_state, set())
        return target_state in allowed

    def transition_to(self, new_state: RequestLifecycleState, reason: str = "") -> bool:
        if self.current_state == new_state:
            return True

        if not self.can_transition_to(new_state):
            logger.warning(
                f"[Request {self.request_id}] Illegal transition attempted: "
                f"{self.current_state.value} -> {new_state.value} (reason: {reason})"
            )
            return False

        old_state = self.current_state
        self.current_state = new_state
        entry = {
            "from": old_state.value,
            "to": new_state.value,
            "timestamp": time.time(),
            "reason": reason,
        }
        self._history.append(entry)
        logger.debug(f"[Request {self.request_id}] State: {old_state.value} -> {new_state.value} ({reason})")

        for callback in self._listeners:
            try:
                callback(old_state, new_state, reason)
            except Exception as e:
                logger.error(f"Error in RequestStateMachine callback: {e}")

        return True

    def register_listener(self, callback: Callable[[RequestLifecycleState, RequestLifecycleState, str], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def reset(self) -> None:
        """Resets the state machine back to IDLE and clears history."""
        self.current_state = RequestLifecycleState.IDLE
        self._history.clear()

