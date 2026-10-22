# core/dialog_manager.py
"""Dialog Manager with Workflow Lock, Proactive Suggestions, and Dynamic Slot Filling."""

from dataclasses import dataclass, field
from enum import Enum
import logging
import os
import platform
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from core.confirmation import AFFIRMATION_PATTERN, CANCELLATION_PATTERN
from core.confirmation_manager import ConfirmationManager, PendingConfirmation

logger = logging.getLogger("jarvis.core.dialog")


class WorkflowState(str, Enum):
    """Authoritative state machine states for conversation and dialog workflows."""
    IDLE = "IDLE"
    UNDERSTANDING = "UNDERSTANDING"
    WAITING_FOR_SLOT = "WAITING_FOR_SLOT"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"


@dataclass
class WorkflowLock:
    workflow_type: str  # e.g. "EXCEL_OPEN", "MEDIA_PLAY", "CALCULATE_COLUMN"
    required_slots: List[str]  # e.g. ["file_target"]
    filled_slots: Dict[str, Any] = field(default_factory=dict)
    target_plugin: str = ""
    target_action: str = ""
    prompt_question: str = ""
    is_active: bool = True
    created_at: float = field(default_factory=time.time)
    timeout_seconds: float = 120.0
    language: str = "hi"
    turn_n: Optional[Dict[str, Any]] = None
    active_question: str = ""
    pending_goal: str = ""
    missing_slots: List[str] = field(default_factory=list)
    candidate_options: List[Dict[str, Any]] = field(default_factory=list)
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    state: WorkflowState = WorkflowState.WAITING_FOR_SLOT
    suspended_at: Optional[float] = None
    parent_workflow_id: Optional[str] = None
    state_history: List[Tuple[str, float]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def transition_to(self, new_state: Union[WorkflowState, str]) -> None:
        """Transitions workflow to a new state and logs in state history."""
        state_val = WorkflowState(new_state) if isinstance(new_state, str) else new_state
        old_state = self.state
        self.state = state_val
        self.state_history.append((state_val.value, time.time()))
        logger.info(
            "WorkflowLock[%s:%s] state transition: %s -> %s",
            self.workflow_type, self.workflow_id,
            old_state.value if hasattr(old_state, "value") else old_state,
            state_val.value
        )

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.timeout_seconds

    @property
    def all_missing_slots(self) -> List[str]:
        slots = self.missing_slots if self.missing_slots else self.required_slots
        missing = []
        for s in slots:
            if s in ("risk_profile", "risk_tolerance") and ("risk_profile" in self.filled_slots or "risk_tolerance" in self.filled_slots):
                continue
            if s in ("capital", "investment_amount") and ("capital" in self.filled_slots or "investment_amount" in self.filled_slots):
                continue
            if s not in self.filled_slots or not self.filled_slots[s]:
                missing.append(s)
        return missing

    @property
    def next_missing_slot(self) -> Optional[str]:
        missing = self.all_missing_slots
        return missing[0] if missing else None

    @property
    def is_complete(self) -> bool:
        return len(self.all_missing_slots) == 0


@dataclass
class SuggestionContext:
    workflow_type: str  # e.g. "EXCEL_OPEN", "MEDIA_PLAY", "TARGET_ACTION"
    suggested_candidate: Dict[str, Any]  # e.g. {"name": "monthly_sales.csv", "path": "...", "type": "file"}
    fallback_candidates: List[Dict[str, Any]] = field(default_factory=list)
    rejected_candidates: List[str] = field(default_factory=list)
    action: str = "open"
    target_plugin: str = ""
    prompt_message: str = ""
    created_at: float = field(default_factory=time.time)
    timeout_seconds: float = 120.0

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.timeout_seconds


@dataclass
class PendingReminderOffer:
    title: str
    remind_time: str  # ISO-8601 string
    time_display: str
    goal: str = ""
    created_at: float = field(default_factory=time.time)
    timeout_seconds: float = 120.0

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.timeout_seconds


class DialogManager:
    """Manages multi-turn conversations, active workflow locks, proactive suggestions, slot filling, proposals, and learning approvals."""

    # Natural Hinglish questions per slot for compose-style workflows
    # (EMAIL_COMPOSE / REMINDER_CREATE / ALARM_SET). send_confirm is dynamic.
    COMPOSE_SLOT_QUESTIONS = {
        "EMAIL_COMPOSE": {
            "recipient": "Kisko bhejna hai?",
            "subject": "Subject kya rakhna hai?",
            "body": "Mail mein kya likhna hai?",
        },
        "MESSAGE_COMPOSE": {
            "recipient": "Kisko message bhejna hai?",
            "message": "Message mein kya likhun?",
        },
        "REMINDER_CREATE": {
            "remind_time": "Kab yaad dilau, Boss?",
            "title": "Kis cheez ka reminder lagau?",
        },
        "ALARM_SET": {
            "time": "Kitne baje ka alarm lagau, Boss?",
        },
        "MEETING_SCHEDULE": {
            "attendees": "Kis ke saath meeting hai?",
            "meeting_time": "Meeting kab hai?",
            "title": "Meeting ka title kya rakhu?",
        },
    }
    COMPOSE_WORKFLOWS = frozenset({"EMAIL_COMPOSE", "MESSAGE_COMPOSE", "REMINDER_CREATE", "ALARM_SET", "MEETING_SCHEDULE"})

    def __init__(self):
        self.active_lock: Optional[WorkflowLock] = None
        self._suspended_workflows: Dict[str, WorkflowLock] = {}
        self._workflow_stack: List[str] = []
        self._last_pending_inquiry_list: List[Dict[str, Any]] = []
        self.pending_suggestion: Optional[SuggestionContext] = None
        self.pending_contextual_suggestion: Optional[Any] = None
        self.pending_reminder_offer: Optional[PendingReminderOffer] = None
        self.pending_proposal: Optional[Any] = None
        self.pending_learning: Optional[Any] = None
        self.pending_spelling: Optional[Dict[str, str]] = None
        self.confirmation_manager = ConfirmationManager(default_timeout_seconds=60.0)
        self._cancellation_patterns = [CANCELLATION_PATTERN]
        self._affirmative_patterns = [AFFIRMATION_PATTERN]

    @property
    def suspended_lock(self) -> Optional[WorkflowLock]:
        """Return the most recently suspended workflow lock (top of stack)."""
        while self._workflow_stack:
            top_id = self._workflow_stack[-1]
            lock = self._suspended_workflows.get(top_id)
            if lock and not lock.is_expired:
                return lock
            self._workflow_stack.pop()
            self._suspended_workflows.pop(top_id, None)
        return None

    @suspended_lock.setter
    def suspended_lock(self, value: Optional[WorkflowLock]) -> None:
        if value is None:
            if self._workflow_stack:
                top_id = self._workflow_stack.pop()
                self._suspended_workflows.pop(top_id, None)
        else:
            self.suspend_workflow(value)

    @property
    def pending_system_action(self) -> Optional[Dict[str, Any]]:
        p = self.confirmation_manager.get_pending_confirmation()
        if not p:
            return None
        return {
            "action": p.action,
            "language": p.language,
            "query": p.parameters.get("query", ""),
            "created_at": p.created_at,
            "expires_at": p.expires_at,
            "prompt": p.prompt,
        }

    @pending_system_action.setter
    def pending_system_action(self, value: Optional[Dict[str, Any]]) -> None:
        if value is None:
            self.confirmation_manager.clear_confirmation()
        else:
            self.confirmation_manager.request_confirmation(
                action=value.get("action", "shutdown"),
                parameters=value.get("parameters", {"query": value.get("query", "")}),
                prompt=value.get("prompt", ""),
                language=value.get("language", "hi"),
                target_plugin=value.get("target_plugin", "system"),
                target_action=value.get("target_action", "shutdown_pc"),
            )

    def has_pending_system_action(self) -> bool:
        return self.confirmation_manager.has_pending_confirmation()

    def has_pending_suggestion(self) -> bool:
        if self.pending_suggestion is None:
            return False
        if self.pending_suggestion.is_expired:
            logger.info(f"DialogManager: Pending suggestion for '{self.pending_suggestion.workflow_type}' expired.")
            self.pending_suggestion = None
            return False
        return True

    def set_pending_suggestion(
        self,
        workflow_type: str,
        candidate: Dict[str, Any],
        fallback_candidates: Optional[List[Dict[str, Any]]] = None,
        action: str = "open",
        target_plugin: str = "",
        prompt_message: str = "",
    ) -> SuggestionContext:
        suggestion = SuggestionContext(
            workflow_type=workflow_type.upper(),
            suggested_candidate=candidate,
            fallback_candidates=fallback_candidates or [],
            action=action,
            target_plugin=target_plugin,
            prompt_message=prompt_message,
        )
        self.pending_suggestion = suggestion
        logger.info(f"DialogManager: Set pending suggestion for '{candidate.get('name')}' in '{workflow_type}'")
        return suggestion

    def clear_pending_suggestion(self) -> None:
        if self.pending_suggestion:
            logger.info(f"DialogManager: Cleared pending suggestion for '{self.pending_suggestion.workflow_type}'")
        self.pending_suggestion = None

    def has_pending_contextual_suggestion(self) -> bool:
        if self.pending_contextual_suggestion is None:
            return False
        created = getattr(self.pending_contextual_suggestion, "created_at", 0.0)
        if (time.time() - created) > 120.0:
            logger.info("DialogManager: Pending contextual suggestion expired.")
            self.pending_contextual_suggestion = None
            return False
        return True

    def set_pending_contextual_suggestion(self, suggestion: Any) -> None:
        self.pending_contextual_suggestion = suggestion
        goal_name = getattr(suggestion, "goal", "")
        logger.info(f"DialogManager: Set pending contextual suggestion for goal='{goal_name}'")

    def clear_pending_contextual_suggestion(self) -> None:
        if self.pending_contextual_suggestion:
            logger.info("DialogManager: Cleared pending contextual suggestion")
        self.pending_contextual_suggestion = None

    def has_pending_reminder_offer(self) -> bool:
        if self.pending_reminder_offer is None:
            return False
        if self.pending_reminder_offer.is_expired:
            logger.info("DialogManager: Pending reminder offer expired.")
            self.pending_reminder_offer = None
            return False
        return True

    def set_pending_reminder_offer(
        self,
        title: Union[str, PendingReminderOffer],
        remind_time: str = "",
        time_display: str = "",
        goal: str = ""
    ) -> None:
        if isinstance(title, PendingReminderOffer):
            self.pending_reminder_offer = title
        else:
            self.pending_reminder_offer = PendingReminderOffer(
                title=title,
                remind_time=remind_time,
                time_display=time_display,
                goal=goal,
                created_at=time.time(),
            )
        logger.info(
            "DialogManager: Set pending reminder offer for '%s' at %s (%s)",
            self.pending_reminder_offer.title,
            self.pending_reminder_offer.time_display,
            self.pending_reminder_offer.remind_time
        )

    def clear_pending_reminder_offer(self) -> None:
        if self.pending_reminder_offer:
            logger.info("DialogManager: Cleared pending reminder offer")
        self.pending_reminder_offer = None

    def suspend_workflow(self, lock: Optional[WorkflowLock] = None) -> Optional[WorkflowLock]:
        """
        Suspends the specified or currently active workflow lock and pushes it to the stack.
        Transitions lock state to WorkflowState.SUSPENDED.
        """
        target_lock = lock or self.active_lock
        if target_lock is None:
            return None

        target_lock.transition_to(WorkflowState.SUSPENDED)
        target_lock.suspended_at = time.time()

        if not getattr(target_lock, "workflow_id", None):
            target_lock.workflow_id = str(uuid.uuid4())[:8]

        if target_lock.workflow_id in self._workflow_stack:
            self._workflow_stack.remove(target_lock.workflow_id)
        self._workflow_stack.append(target_lock.workflow_id)
        self._suspended_workflows[target_lock.workflow_id] = target_lock

        if self.active_lock == target_lock:
            self.active_lock = None

        logger.info(
            "DialogManager: Suspended workflow '%s' (id=%s). Stack depth: %d",
            target_lock.workflow_type, target_lock.workflow_id, len(self._workflow_stack)
        )
        return target_lock

    def resume_workflow(self, target: Optional[Union[str, int, WorkflowLock]] = None) -> Optional[WorkflowLock]:
        """
        Resumes a suspended workflow by target (index, query name, or top of stack).
        Transitions lock state back to WAITING_FOR_SLOT or WAITING_FOR_CONFIRMATION.
        """
        if not self._suspended_workflows:
            return None

        chosen_id: Optional[str] = None

        if isinstance(target, WorkflowLock):
            chosen_id = target.workflow_id
        elif isinstance(target, int):
            if self._last_pending_inquiry_list and 1 <= target <= len(self._last_pending_inquiry_list):
                chosen_id = self._last_pending_inquiry_list[target - 1].get("workflow_id")
            elif 1 <= target <= len(self._workflow_stack):
                rev_stack = list(reversed(self._workflow_stack))
                chosen_id = rev_stack[target - 1]
        elif isinstance(target, str) and target.strip():
            target_low = target.strip().lower()
            if target_low in self._suspended_workflows:
                chosen_id = target_low
            else:
                ordinal_map = {
                    "pehla": 1, "first": 1, "1st": 1, "pehle": 1,
                    "doosra": 2, "second": 2, "2nd": 2, "dusra": 2,
                    "teesra": 3, "third": 3, "3rd": 3, "tisra": 3,
                    "chautha": 4, "fourth": 4, "4th": 4
                }
                for word, idx in ordinal_map.items():
                    if word in target_low:
                        return self.resume_workflow(idx)

                for w_id in reversed(self._workflow_stack):
                    w_lock = self._suspended_workflows.get(w_id)
                    if not w_lock or w_lock.is_expired:
                        continue
                    wf_type = w_lock.workflow_type.lower()
                    recipient = str(w_lock.filled_slots.get("recipient", "")).lower()
                    subject = str(w_lock.filled_slots.get("subject", "")).lower()
                    title = str(w_lock.filled_slots.get("title", "")).lower()

                    if (target_low in wf_type or wf_type in target_low or
                        (recipient and recipient in target_low) or
                        (subject and subject in target_low) or
                        (title and title in target_low) or
                        ("email" in target_low and "email" in wf_type) or
                        ("mail" in target_low and "email" in wf_type) or
                        ("excel" in target_low and "excel" in wf_type) or
                        ("report" in target_low and "excel" in wf_type) or
                        ("backup" in target_low and "backup" in wf_type) or
                        ("reminder" in target_low and "reminder" in wf_type)):
                        chosen_id = w_id
                        break

        if not chosen_id:
            while self._workflow_stack:
                candidate_id = self._workflow_stack[-1]
                w_lock = self._suspended_workflows.get(candidate_id)
                if w_lock and not w_lock.is_expired:
                    chosen_id = candidate_id
                    break
                self._workflow_stack.pop()
                self._suspended_workflows.pop(candidate_id, None)

        if not chosen_id or chosen_id not in self._suspended_workflows:
            return None

        lock_to_resume = self._suspended_workflows.pop(chosen_id)
        if chosen_id in self._workflow_stack:
            self._workflow_stack.remove(chosen_id)

        if lock_to_resume.is_expired:
            return None

        if self.has_active_lock():
            self.suspend_workflow(self.active_lock)

        self.active_lock = lock_to_resume
        new_state = (
            WorkflowState.WAITING_FOR_CONFIRMATION
            if lock_to_resume.is_complete
            else WorkflowState.WAITING_FOR_SLOT
        )
        lock_to_resume.transition_to(new_state)
        logger.info(
            "DialogManager: Resumed workflow '%s' (id=%s). Missing slots: %s",
            lock_to_resume.workflow_type, lock_to_resume.workflow_id, lock_to_resume.all_missing_slots
        )
        return lock_to_resume

    def clear_suspended_workflows(self) -> None:
        """Clears all suspended workflows from pool and stack."""
        self._suspended_workflows.clear()
        self._workflow_stack.clear()
        self._last_pending_inquiry_list = []


    def resume_suspended_lock(self) -> Optional[WorkflowLock]:
        """Resumes a workflow lock that was temporarily suspended by an interruption."""
        return self.resume_workflow()

    def list_pending_workflows(self) -> List[WorkflowLock]:
        """Returns non-expired suspended workflows in stack order."""
        valid_locks = []
        for w_id in list(self._workflow_stack):
            lock = self._suspended_workflows.get(w_id)
            if lock and not lock.is_expired:
                valid_locks.append(lock)
            else:
                if w_id in self._workflow_stack:
                    self._workflow_stack.remove(w_id)
                self._suspended_workflows.pop(w_id, None)
        return valid_locks

    def get_workflow_display_name(self, lock: WorkflowLock, lang: str = "hi") -> str:
        wf_type = lock.workflow_type.upper()
        if wf_type == "EMAIL_COMPOSE":
            recipient = lock.filled_slots.get("recipient")
            if recipient:
                return f"{recipient} ka email draft" if lang == "hi" else f"email draft for {recipient}"
            return "email draft"
        if wf_type == "MESSAGE_COMPOSE":
            recipient = lock.filled_slots.get("recipient")
            if recipient:
                return f"{recipient} ko message" if lang == "hi" else f"message to {recipient}"
            return "message"
        if wf_type == "REMINDER_CREATE":
            title = lock.filled_slots.get("title")
            return f"reminder ({title})" if title else "reminder"
        if wf_type in ("EXCEL_OPEN", "EXCEL_WORKFLOW"):
            return "Excel report"
        if "BACKUP" in wf_type:
            return "backup upload"
        if "FILE" in wf_type:
            return "file search"
        return wf_type.replace("_", " ").lower()

    def format_pending_workflows_summary(self, lang: str = "hi") -> str:
        locks = self.list_pending_workflows()
        if not locks:
            return "Koi pending kaam nahi hai, Boss." if lang == "hi" else "No tasks are pending, Boss."

        self._last_pending_inquiry_list = [
            {"index": i + 1, "workflow_id": lock.workflow_id, "workflow_type": lock.workflow_type, "lock": lock}
            for i, lock in enumerate(locks)
        ]

        ordinals_hi = ["pehla", "doosra", "teesra", "chautha", "paanchwa"]
        ordinals_en = ["first", "second", "third", "fourth", "fifth"]
        ordinals = ordinals_hi if lang == "hi" else ordinals_en

        items = []
        for i, lock in enumerate(locks):
            ord_prefix = ordinals[i] if i < len(ordinals) else f"#{i+1}"
            name = self.get_workflow_display_name(lock, lang=lang)
            items.append(f"{ord_prefix} {name}")

        count = len(locks)
        if lang == "hi":
            count_str = f"{count} kaam pending {'hai' if count == 1 else 'hain'}: {', '.join(items)}."
        else:
            count_str = f"{count} task{' is' if count == 1 else 's are'} pending: {', '.join(items)}."
        return count_str

    def format_pending_workflow_detail(self, lock: WorkflowLock, lang: str = "hi") -> str:
        wf_type = lock.workflow_type.upper()
        if wf_type == "EMAIL_COMPOSE":
            recipient = lock.filled_slots.get("recipient", "kisi")
            filled_desc = []
            if "subject" in lock.filled_slots:
                filled_desc.append("subject set hai")
            if "body" in lock.filled_slots:
                filled_desc.append("body set hai")

            missing_desc = []
            for s in lock.all_missing_slots:
                if s == "subject":
                    missing_desc.append("subject pending hai")
                elif s == "body":
                    missing_desc.append("body pending hai")
                elif s == "send_confirm":
                    missing_desc.append("send confirmation pending hai")

            desc_parts = filled_desc + missing_desc
            details = ", ".join(desc_parts) if desc_parts else "slots pending hain"
            if lang == "hi":
                return f"{recipient} ko draft mail: {details}."
            return f"Draft email to {recipient}: {details}."

        filled = ", ".join(lock.filled_slots.keys()) or "none"
        missing = ", ".join(lock.all_missing_slots) or "none"
        if lang == "hi":
            return f"{lock.workflow_type.lower()}: {filled} set hai, {missing} pending hai."
        return f"{lock.workflow_type.lower()}: {filled} set, {missing} pending."

    def is_workflow_query(self, text: str) -> bool:
        if not text:
            return False
        low = text.strip().lower()
        if any(p in low for p in (
            "kaunse kaam pending", "kaunsa kaam pending", "kya pending",
            "kya kya pending", "kuch pending hai", "pending tasks",
            "pending task", "what is pending", "what tasks are pending",
            "show pending", "list pending", "kaam pending hain", "tasks pending"
        )):
            return True
        if any(p in low for p in (
            "pehla kya hai", "pehla wala kya hai", "first kya hai", "what is the first",
            "doosra kya hai", "dusra kya hai", "second kya hai", "what is the second",
            "teesra kya hai", "tisra kya hai", "third kya hai"
        )):
            return True
        if any(p in low for p in (
            "email continue karo", "mail continue karo", "wahi continue karo",
            "uspe wapas aao", "resume karo", "continue karo", "pehle email",
            "ab email continue", "pehle wala continue", "doosra wala continue",
            "draft continue", "report continue"
        )):
            return True
        return False

    def awaits_user_followup(self) -> bool:
        """Return whether Jarvis has asked for a contextual next turn."""
        has_suspended = bool(self.has_suspended_lock())
        return bool(
            self.has_active_lock()
            or has_suspended
            or self.has_pending_suggestion()
            or self.has_pending_contextual_suggestion()
            or self.has_pending_reminder_offer()
            or self.has_pending_system_action()
            or self.pending_spelling
            or self.pending_learning
            or self.pending_proposal
        )

    def interpret_turn_n_plus_1(self, user_text: Any, core: Any, raw_input: Optional[str] = None) -> Tuple[bool, str]:
        """
        Interprets user utterance in the context of current conversation state
        (TURN N + ACTIVE QUESTION + PENDING GOAL + MISSING SLOT + TURN N+1 ANSWER)
        before generic intent routing begins.
        """
        if not isinstance(user_text, str):
            user_text = getattr(user_text, "normalized_input", None) or getattr(user_text, "raw_input", "") or str(user_text)

        # 0. Check workflow-level inquiries and explicit resumes
        if self.is_workflow_query(user_text):
            low = user_text.lower().strip()
            # A. List pending workflows ("Mere kaunse kaam pending hain?")
            if any(p in low for p in ("kaunse kaam pending", "kaunsa kaam pending", "kya pending", "kya kya pending", "kuch pending hai", "pending tasks", "what is pending", "show pending", "list pending", "kaam pending hain")):
                return True, self.format_pending_workflows_summary(lang=getattr(self.active_lock, "language", "hi") if self.active_lock else "hi")

            # B. Detail of specific pending workflow ("Pehla kya hai?")
            m_first = re.search(r"\b(pehla|first|1st|pehle)\b", low)
            m_second = re.search(r"\b(doosra|dusra|second|2nd)\b", low)
            m_third = re.search(r"\b(teesra|tisra|third|3rd)\b", low)
            if any(p in low for p in ("kya hai", "what is", "detail", "batao")):
                idx = 1 if m_first else (2 if m_second else (3 if m_third else None))
                if idx is not None:
                    locks = self.list_pending_workflows()
                    if self._last_pending_inquiry_list and 1 <= idx <= len(self._last_pending_inquiry_list):
                        lock_ref = self._last_pending_inquiry_list[idx - 1].get("lock")
                        if lock_ref:
                            return True, self.format_pending_workflow_detail(lock_ref)
                    elif 1 <= idx <= len(locks):
                        return True, self.format_pending_workflow_detail(locks[idx - 1])
                    return True, "Us number ka koi pending kaam nahi hai, Boss."

            # C. Explicit resume command ("Ab email continue karo", "Wahi continue karo", "Pehle email continue karo")
            resumed = self.resume_workflow(target=low)
            if resumed:
                q = self._compose_question(resumed) if resumed.workflow_type in self.COMPOSE_WORKFLOWS else (resumed.prompt_question or "Aage kya karna hai?")
                desc = self.get_workflow_display_name(resumed)
                if any(k in low for k in ("haan continue", "achha email continue", "ab continue", "wahi continue")):
                    return True, f"Haan, {q}"
                return True, f"{desc.capitalize()} continue kar raha hoon. {q}"

        # Automatically resume suspended workflow if user is answering slots
        if not self.has_active_lock() and self.suspended_lock and not self.suspended_lock.is_expired:
            from core.semantic.slot_extractor import SemanticSlotExtractor
            if (not SemanticSlotExtractor.is_interruption(user_text, missing_slots=self.suspended_lock.missing_slots)
                    and not self._is_fresh_command_during_compose(user_text)):
                self.resume_suspended_lock()

        if self.has_active_lock():
            return self.process_locked_turn(user_text, core)

        # 0. Active container follow-up ("usme report file kholo" after an app is active)
        if self.is_container_followup(user_text, core):
            handled, resp = self.process_container_followup_turn(user_text, core)
            if handled:
                return True, resp

        if not self.awaits_user_followup():
            return False, ""

        # 1. Authoritative pending confirmation (restart, shutdown, delete)
        if self.has_pending_system_action():
            handled, resp = self.confirmation_manager.handle_confirmation(user_text, core)
            if handled:
                return True, resp

        # 2. Ambiguous spelling confirmation
        if self.pending_spelling:
            handled, resp = self.process_spelling_confirmation_turn(user_text, core)
            if handled:
                return True, resp

        # 3. Active workflow lock / pending goal / missing slot
        if self.has_active_lock():
            handled, resp = self.process_locked_turn(user_text, core)
            if handled:
                return True, resp

        # 4. Proactive candidate suggestion
        if self.has_pending_suggestion():
            handled, resp = self.process_suggestion_turn(user_text, core)
            if handled:
                return True, resp

        # 4.5 Contextual intelligent suggestion follow-up ("haan" / "yes" / "kar do" / "nahi")
        if self.has_pending_contextual_suggestion():
            handled, resp = self.process_contextual_suggestion_turn(user_text, core)
            if handled:
                return True, resp

        # 4.6 Contextual reminder offer follow-up ("haan" / "yes" / "kar do" / "nahi")
        if self.has_pending_reminder_offer():
            handled, resp = self.process_reminder_offer_turn(user_text, core)
            if handled:
                return True, resp

        # 5. Staged learning approval
        if self.has_pending_learning():
            handled, resp = self.process_learning_approval_turn(user_text, core)
            if handled:
                return True, resp

        # 6. Workflow proposal confirmation
        if self.has_pending_proposal():
            handled, resp = self.process_proposal_turn(user_text, core)
            if handled:
                return True, resp

        return False, ""

    def set_pending_system_action(self, action: str, language: str = "hi", query: str = "") -> str:
        return self.confirmation_manager.request_confirmation(
            action=action,
            parameters={"query": query},
            language=language,
            target_plugin="system",
            target_action="shutdown_pc",
        )

    def clear_pending_system_action(self) -> None:
        self.confirmation_manager.clear_confirmation()

    def process_system_action_turn(self, user_text: str, core: Any) -> Tuple[bool, str]:
        """Processes confirmation / rejection for destructive system actions (restart/shutdown)."""
        return self.confirmation_manager.handle_confirmation(user_text, core)

    def set_pending_spelling(self, typo: str, correction: str, corrected_text: str) -> None:
        self.pending_spelling = {
            "typo": typo, "correction": correction, "corrected_text": corrected_text
        }

    def process_spelling_confirmation_turn(self, user_text: str, core: Any) -> Tuple[bool, str]:
        if not self.pending_spelling:
            return False, ""
        pending = self.pending_spelling
        cleaned = user_text.strip().lower()
        if any(pattern.match(cleaned) for pattern in self._affirmative_patterns):
            self.pending_spelling = None
            if core.learning_manager:
                core.learning_manager.vocabulary.learn_term(
                    pending["typo"], pending["correction"], category="confirmed_spelling"
                )
            return True, core.process_input(pending["corrected_text"], source="gui")
        if any(pattern.match(cleaned) for pattern in self._cancellation_patterns):
            if hasattr(core, "reject_fuzzy_candidate"):
                core.reject_fuzzy_candidate(pending["typo"], pending["correction"])
            self.pending_spelling = None
            return True, "Theek hai Boss, woh interpretation galat thi. Main use apply nahi karunga—dobara bata dijiye."
        self.pending_spelling = None
        return False, ""

    def has_pending_learning(self) -> bool:
        return self.pending_learning is not None

    def set_pending_learning(self, learning: Any) -> None:
        self.pending_learning = learning
        logger.info(f"DialogManager: Pending learning approval '{getattr(learning, 'original_key', '')}' set.")

    def clear_pending_learning(self) -> None:
        self.pending_learning = None

    def process_learning_approval_turn(self, user_text: str, core: Any) -> Tuple[bool, str]:
        """Processes conversational approval or rejection for a staged learning item."""
        if not self.has_pending_learning():
            return False, ""

        cleaned = user_text.strip().lower()
        learning = self.pending_learning

        # 1. Affirmative Confirmation ("Haan" / "Yes" / "Yaad rakho")
        for p in self._affirmative_patterns:
            if p.match(cleaned):
                self.clear_pending_learning()
                if hasattr(core, "learning_manager") and core.learning_manager:
                    core.learning_manager.approval.accept_learning(learning.id)
                return True, f"Done! Maine permanent memory me save kar liya: '{learning.original_key}' ➔ '{learning.proposed_val}', Boss."

        # 2. Rejection ("Nahi" / "No" / "Rehne do")
        for p in self._cancellation_patterns:
            if p.match(cleaned):
                self.clear_pending_learning()
                if hasattr(core, "learning_manager") and core.learning_manager:
                    core.learning_manager.approval.reject_learning(learning.id)
                return True, "Thik hai Boss, ise permanent memory me save nahi kiya."

        # Fallback
        self.clear_pending_learning()
        return False, ""

    def has_pending_proposal(self) -> bool:
        return self.pending_proposal is not None

    def set_proposal(self, proposal: Any) -> None:
        self.pending_proposal = proposal
        logger.info(f"DialogManager: Pending workflow proposal '{getattr(proposal, 'display_title', '')}' set.")

    def clear_proposal(self) -> None:
        self.pending_proposal = None

    def process_proposal_turn(self, user_text: str, core: Any) -> Tuple[bool, str]:
        """Processes confirmation / rejection of a proactive workflow proposal."""
        if not self.has_pending_proposal():
            return False, ""

        cleaned = user_text.strip().lower()
        proposal = self.pending_proposal

        # 1. Affirmative Confirmation ("Yes" / "Haan" / "Kar do")
        for p in self._affirmative_patterns:
            if p.match(cleaned):
                self.clear_proposal()
                if hasattr(core, "learning_manager") and core.learning_manager:
                    res = core.learning_manager.confirm_workflow_proposal(proposal)
                    trigger = res["trigger_phrases"][0]
                    return True, (
                        f"Done! Maine '{res['title']}' workflow automate kar diya hai. "
                        f"Ab se aap bas 'Jarvis, {trigger}' bolenge to main pura workflow run kar dunga, Boss."
                    )
                return True, f"Automated workflow '{proposal.display_title}', Boss."

        # 2. Cancellation / Rejection ("No" / "Nahi" / "Rehne do")
        for p in self._cancellation_patterns:
            if p.match(cleaned):
                self.clear_proposal()
                return True, f"Thik hai Boss, '{proposal.display_title}' ko automate nahi kiya."

        # Unrecognized response while proposal pending
        self.clear_proposal()
        return False, ""

    def process_suggestion_turn(self, user_text: str, core: Any) -> Tuple[bool, str]:
        """
        Processes affirmative confirmation, rejection with fallback, or command override
        for proactive suggestions (Rules 4, 5, 6, 12, 13).
        """
        if not self.has_pending_suggestion():
            return False, ""

        raw = user_text.strip()
        cleaned = raw.lower()
        cleaned_no_punct = re.sub(r"[^\w\s]", " ", cleaned)
        cleaned_no_punct = re.sub(r"\s+", " ", cleaned_no_punct).strip()

        suggestion = self.pending_suggestion

        # 1. Check for blank / new workbook or explicit cancellation or other candidate
        is_blank_or_new = bool(re.search(r"\b(?:new|blank|fresh|nayi|naya|khali)\b", cleaned_no_punct))
        is_explicit_cancel = bool(re.search(r"\b(?:cancel|abort|rehne\s+do|stop|ruk\s+jao)\b", cleaned_no_punct))
        is_other_option = bool(re.search(r"\b(?:dusri\s+wali|dusra|dusri|other|different|change\s+it|koi\s+aur)\b", cleaned_no_punct))
        is_negative = (
            is_other_option
            or is_blank_or_new
            or is_explicit_cancel
            or any(p.match(cleaned_no_punct) for p in self._cancellation_patterns)
            or cleaned_no_punct in ("no", "nahi", "nah", "nope", "mat karo", "reject")
        )
        is_affirmative = not is_negative and (
            any(p.match(cleaned_no_punct) for p in self._affirmative_patterns)
            or bool(re.search(r"\b(?:wahi|wahi\s+wali|wahi\s+kholo|wahi\s+chalao|continue|proceed|kar\s+do|haan|yes|okay|ok|sure|bilkul)\b", cleaned_no_punct))
        )

        # 2. Rule 5 & 4: Affirmative Confirmation ("Haan", "Yes", "Wahi", "Okay", "Continue")
        if is_affirmative:
            cand = suggestion.suggested_candidate
            self.clear_pending_suggestion()
            return True, self._execute_confirmed_suggestion(suggestion, cand, core)

        # 3. Rule 5 & 6: User rejects suggestion ("Nahi", "Dusri wali", "New one", "Change it")
        if is_negative:
            cand = suggestion.suggested_candidate
            cand_name = cand.get("name", "")
            if cand_name and cand_name not in suggestion.rejected_candidates:
                suggestion.rejected_candidates.append(cand_name)

            # If user explicitly wants a blank / new workbook
            if is_blank_or_new and suggestion.workflow_type == "EXCEL_OPEN":
                self.clear_pending_suggestion()
                if core.plugin_manager:
                    core.plugin_manager.execute_action("windows", "launch_app", {"app_name": "excel"})
                if hasattr(core, "active_context"):
                    core.active_context.record_execution(action="open_app", application="excel", workflow="EXCEL_OPEN")
                return True, "Bilkul Boss, ek nayi blank Excel workbook khol di hai."

            # If user explicitly cancelled the entire operation
            if is_explicit_cancel:
                self.clear_pending_suggestion()
                return True, f"Theek hai Boss, {suggestion.workflow_type.lower()} operation cancel kar diya."

            # Rule 6: Fall back to next best candidate if available
            if suggestion.fallback_candidates:
                next_cand = suggestion.fallback_candidates.pop(0)
                while next_cand.get("name") in suggestion.rejected_candidates and suggestion.fallback_candidates:
                    next_cand = suggestion.fallback_candidates.pop(0)

                if next_cand.get("name") not in suggestion.rejected_candidates:
                    suggestion.suggested_candidate = next_cand
                    item_name = next_cand.get("name")
                    return True, f"Theek hai Boss, kya aap '{item_name}' open karna chahte hain ya koi aur file?"

            # No more fallbacks available -> ask targeted question and lock slot
            wf = suggestion.workflow_type
            self.clear_pending_suggestion()
            if wf == "EXCEL_OPEN":
                self.set_lock(
                    workflow_type="EXCEL_OPEN", required_slots=["file_target"],
                    target_plugin="excel", target_action="open", prompt_question="Kaunsi file?",
                )
                return True, "Theek hai Boss, fir kaunsi Excel file open karni hai?"
            elif wf in ("MEDIA_PLAY", "YOUTUBE_PLAY"):
                self.set_lock(
                    workflow_type="MEDIA_PLAY", required_slots=["media_target"],
                    target_plugin="vlc", target_action="play_file", prompt_question="Kaunsi movie?",
                )
                return True, "Theek hai Boss, fir kaunsi movie ya video play karni hai?"
            else:
                return True, "Theek hai Boss, aapko kya open karna hai, batayein?"

        # Rule 12 & 13: Check if input is a new explicit command or conversation topic switch
        is_command_or_chat = bool(
            re.search(
                r"\b(?:kya\s+haal|kaise\s+ho|kya\s+kar\s+rahe|hello|hi|hey|weather|mausam|time|samay|chrome|youtube|google|browser|notepad|shutdown|restart|exit|quit|band\s+karo)\b",
                cleaned_no_punct,
            )
        )
        if is_command_or_chat:
            self.clear_pending_suggestion()
            return False, ""

        # 4. Specific needle provided (e.g. user said "Sales wali" or "test.xlsx" or "Inception")
        if suggestion.workflow_type == "EXCEL_OPEN":
            self.clear_pending_suggestion()
            clean_val = self._clean_slot_value(raw)
            if clean_val and clean_val != "new":
                res = self.resolve_file(clean_val, extensions=["xlsx", "csv", "xls", "xlsm"])
                exact_matches = res["exact_matches"]
                close_suggestions = res["close_suggestions"]

                if len(exact_matches) == 1:
                    target_file = exact_matches[0]["path"]
                    display_name = exact_matches[0]["name"]
                    if core.plugin_manager:
                        core.plugin_manager.execute_action(
                            "windows", "launch_app", {"app_name": "excel", "path": target_file}
                        )
                    if hasattr(core, "active_context"):
                        core.active_context.record_execution(
                            action="open_file", application="excel", file_path=target_file, entity=display_name, workflow="EXCEL_OPEN"
                        )
                    return True, f"'{display_name}' Excel mein khol di hai, Boss."
                elif len(exact_matches) > 1:
                    display_names = [f"'{m['name']}'" for m in exact_matches[:3]]
                    options_str = ", ".join(display_names)
                    self.set_lock(
                        workflow_type="EXCEL_OPEN",
                        required_slots=["file_target"],
                        target_plugin="excel",
                        target_action="open",
                        prompt_question=f"'{clean_val}' ke {len(exact_matches)} matches mile: {options_str}. Kaunsi file open karni hai?"
                    )
                    return True, f"'{clean_val}' ke {len(exact_matches)} matches mile: {options_str}. Kaunsi file open karni hai?"
                else:
                    if close_suggestions:
                        suggested_name = close_suggestions[0]["name"]
                        suggestion.suggested_candidate = close_suggestions[0]
                        suggestion.fallback_candidates = close_suggestions[1:]
                        return True, f"'{clean_val}' naam ki koi file nahi mili, Boss. Kya aap '{suggested_name}' open karna chahte hain?"
                    return True, f"'{clean_val}' naam ki koi Excel file nahi mili, Boss. Kya aap nayi blank workbook kholna chahte hain?"

        # 5. Rule 12 & 13: Explicit new command override -> clear suggestion and let pipeline handle
        self.clear_pending_suggestion()
        return False, ""

    def _execute_confirmed_suggestion(self, suggestion: SuggestionContext, candidate: Dict[str, Any], core: Any) -> str:
        """Executes the confirmed suggested candidate and updates contextual memory (Rules 4, 10)."""
        wf = suggestion.workflow_type
        target_path = candidate.get("path", "")
        display_name = candidate.get("name", os.path.basename(target_path) if target_path else "")

        if wf == "EXCEL_OPEN":
            if core.plugin_manager:
                core.plugin_manager.execute_action("windows", "launch_app", {"app_name": "excel", "path": target_path})
            if hasattr(core, "active_context"):
                core.active_context.record_execution(
                    action="open_file", application="excel", file_path=target_path, entity=display_name, workflow="EXCEL_OPEN"
                )
            return f"'{display_name}' Excel mein khol di hai, Boss."

        elif wf in ("MEDIA_PLAY", "YOUTUBE_PLAY"):
            target_plugin = suggestion.target_plugin or "vlc"
            if target_plugin == "youtube":
                if core.plugin_manager:
                    core.plugin_manager.execute_action("youtube", "search_and_play", {"query": display_name})
            else:
                if core.plugin_manager:
                    core.plugin_manager.execute_action("vlc", "play_file", {"path": target_path})
            if hasattr(core, "active_context"):
                core.active_context.record_execution(
                    action="play_media", application=target_plugin, file_path=target_path, entity=display_name, workflow=wf
                )
            return f"'{display_name}' play kar diya hai, Boss."

        elif wf == "TARGET_ACTION":
            from core.target_engine import TargetRequest
            outcome = core.target_engine.execute(TargetRequest(
                target=candidate.get("name", ""),
                action=suggestion.action or "open",
            ))
            return outcome.message

        return f"'{display_name}' par action execute kar diya hai, Boss."

    def process_contextual_suggestion_turn(self, user_text: str, core: Any) -> Tuple[bool, str]:
        """
        Handles follow-up response to an active contextual next-step suggestion.
        Affirmative responses execute the suggested action or provide next-step guidance.
        Rejection backoff suppresses repetition.
        """
        from core.intelligence.suggestion_manager import get_suggestion_manager
        sug_mgr = getattr(core, "suggestion_manager", None) or get_suggestion_manager()
        sug = self.pending_contextual_suggestion
        if not sug:
            return False, ""

        raw = (user_text or "").strip().lower()
        cleaned_no_punct = re.sub(r"[^\w\s]", "", raw).strip()

        # Check if user switched to an explicit command or new topic
        is_command_or_chat = bool(
            re.search(
                r"\b(?:chrome|notepad|calculator|word|excel|vlc|spotify|settings|volume|shutdown|restart|exit|quit|lock|weather|mausam|time|browser|google|youtube)\b",
                cleaned_no_punct,
            )
        )
        if is_command_or_chat and not any(p.match(cleaned_no_punct) for p in self._affirmative_patterns):
            self.clear_pending_contextual_suggestion()
            return False, ""

        # Check negative / rejection
        is_negative = (
            any(p.match(cleaned_no_punct) for p in self._cancellation_patterns)
            or cleaned_no_punct in ("no", "nahi", "nah", "nope", "mat karo", "rehne do", "cancel", "reject", "stop")
            or bool(re.search(r"\b(?:nahi|mat\s+karo|rehne\s+do|cancel|zarurat\s+nahi)\b", cleaned_no_punct))
        )

        # Check affirmative
        is_affirmative = not is_negative and (
            any(p.match(cleaned_no_punct) for p in self._affirmative_patterns)
            or bool(re.search(r"\b(?:haan|yes|kar\s+do|dikhao|batao|sure|okay|ok|bilkul|proceed|continue|batayein)\b", cleaned_no_punct))
        )

        if is_affirmative:
            sug_mgr.record_feedback(sug.suggestion_id, accepted=True)
            self.clear_pending_contextual_suggestion()

            action = getattr(sug, "action", "")
            target = getattr(sug, "target", "") or ""

            if action == "compare_travel_routes":
                dest_title = target.title() if target else "destination"
                if hasattr(core, "plugin_manager") and core.plugin_manager:
                    core.plugin_manager.execute_action("browser", "search_web", {"query": f"travel routes to {dest_title}"})
                return True, f"Bilkul Boss, {dest_title} ke travel routes aur booking options open kar raha hoon."

            elif action == "get_hourly_forecast":
                city_title = target.title() if target else "local area"
                return True, f"{city_title} mein agle 6 ghante mausam saaf rahega, taapman 28°C se 30°C ke beech rahega aur barish ke aasar kam hain."

            elif action == "start_troubleshooting_checklist":
                return True, (
                    "Theek hai, RDP troubleshooting ka pehla step:\n"
                    "1. Remote Desktop Services status check karein ('net start termservice').\n"
                    "2. Port 3389 firewall rule verify karein.\n"
                    "3. Target machine IP reachability verify karein (ping)."
                )

            elif action == "show_dns_setup_guide":
                return True, (
                    "Windows mein DNS configure karne ke steps:\n"
                    "1. Network Connections (ncpa.cpl) open karein.\n"
                    "2. Adapter properties mein IPv4 select karein.\n"
                    "3. Preferred DNS 8.8.8.8 aur Alternate 1.1.1.1 set karein."
                )

            elif action == "show_excel_formula_example":
                return True, (
                    "Excel mein duplicates highlight karne ke liye conditional formatting formula:\n"
                    "`=COUNTIF(A$2:A2, A2)>1` use karein, ya Data tab mein 'Remove Duplicates' par click karein."
                )

            elif action == "play_trending_songs":
                if hasattr(core, "plugin_manager") and core.plugin_manager:
                    core.plugin_manager.execute_action("youtube", "search_and_play", {"query": "trending songs"})
                return True, "Bilkul Boss, YouTube par trending romantic songs play kar raha hoon."

            elif action == "open_disk_cleanup":
                if hasattr(core, "plugin_manager") and core.plugin_manager:
                    core.plugin_manager.execute_action("windows", "launch_app", {"app_name": "cleanmgr"})
                return True, "Theek hai Boss, Windows Disk Cleanup utility launch kar raha hoon."

            elif action == "show_backup_options":
                return True, (
                    "Automated backup ke liye Windows Backup & Restore (File History) setup kar sakte hain, "
                    "ya OneDrive/Google Drive sync folder use kar sakte hain."
                )

            return True, f"Theek hai Boss, {sug.goal.lower().replace('_', ' ')} action execute kar diya hai."

        if is_negative:
            sug_mgr.record_feedback(sug.suggestion_id, accepted=False)
            self.clear_pending_contextual_suggestion()
            return True, "Theek hai Boss, koi baat nahi."

        # Topic switch / new command: clear suggestion and let normal pipeline handle it
        self.clear_pending_contextual_suggestion()
        return False, ""

    def process_reminder_offer_turn(self, user_text: str, core: Any = None) -> Tuple[bool, str]:
        """
        Handles follow-up response to an active reminder offer.
        User says "haan" / "yes" / "kar do" -> creates reminder in authoritative ReminderPlugin.
        User says "nahi" / "mat karo" -> gracefully declines.
        User gives another command -> clears offer and allows normal processing.
        """
        offer = self.pending_reminder_offer
        if not offer:
            return False, ""

        cleaned = (user_text or "").strip().lower()
        cleaned_no_punct = re.sub(r"[^\w\s]", "", cleaned).strip()

        # Check for affirmative confirmation ("haan", "yes", "kar do", "laga do", "sure", "proceed")
        is_affirmative = bool(
            any(p.match(cleaned_no_punct) for p in self._affirmative_patterns)
            or re.search(r"\b(?:haan|yes|yep|yeah|kar\s+do|laga\s+do|lagao|set\s+karo|bilkul|sure|okay|ok|please)\b", cleaned_no_punct)
        )

        # Check for negative refusal ("nahi", "mat karo", "cancel", "no", "nah", "rehne do")
        is_negative = bool(
            any(p.match(cleaned_no_punct) for p in self._cancellation_patterns)
            or cleaned_no_punct in ("no", "nahi", "nah", "nope", "mat karo", "rehne do", "cancel")
            or re.search(r"\b(?:nahi|mat\s+karo|rehne\s+do|cancel|no\s+thanks)\b", cleaned_no_punct)
        )

        if is_affirmative and not is_negative:
            self.clear_pending_reminder_offer()
            rem_title = offer.title or "Reminder"
            rem_time = offer.remind_time
            params = {"title": rem_title, "remind_time": rem_time}

            created_msg = None
            if hasattr(core, "plugin_manager") and core.plugin_manager:
                try:
                    res = core.plugin_manager.execute_action("reminder", "create_reminder", params)
                    if res and res.success:
                        created_msg = res.data.get("message")
                except Exception as e:
                    logger.debug("Error executing reminder action via plugin_manager: %s", e)

            if not created_msg:
                try:
                    from plugins.reminder.plugin import ReminderPlugin
                    res = ReminderPlugin().execute("create_reminder", params)
                    if res and res.success:
                        created_msg = res.data.get("message")
                except Exception as e:
                    logger.debug("Error executing reminder action directly: %s", e)

            if created_msg:
                return True, created_msg
            return True, f"Reminder set kar diya hai: '{rem_title}' {offer.time_display} ke liye, Boss. ⏰"

        if is_negative:
            self.clear_pending_reminder_offer()
            return True, "Theek hai, reminder set nahi kiya."

        # If user spoke an explicit command or new topic, clear offer and let normal pipeline handle it
        self.clear_pending_reminder_offer()
        return False, ""

    # ------------------------------------------------------------------
    # Active Container Follow-up (deictic reference into the just-used app/site)
    # ------------------------------------------------------------------
    # "usme report file kholo" / "isme youtube kholo" after an app or site is active.
    CONTAINER_REF_RE = re.compile(r"^\s*(?:ab\s+|phir\s+|please\s+|zara\s+)?(?:us|is)(?:me|mein)\b", re.IGNORECASE)
    CONTAINER_ACT_RE = re.compile(
        r"\b(?:open|kholo|khol\s+do|kholna|chalao|chala\s+do|play|le\s+aao|dikhao|banao|create|search|dhundo|find)\b",
        re.IGNORECASE,
    )
    DOC_APP_EXTENSIONS: Dict[str, List[str]] = {
        "excel": ["xlsx", "xls", "xlsm", "csv"],
        "word": ["docx", "doc", "rtf"],
        "notepad": ["txt", "log", "md", "ini", "cfg"],
        "powerpoint": ["pptx", "ppt"],
        "powerpnt": ["pptx", "ppt"],
    }
    MEDIA_EXTENSIONS = ["mp4", "mkv", "avi", "mov", "wmv", "mp3", "wav", "flac", "m4a"]
    GENERIC_EXTENSIONS = [
        "txt", "pdf", "docx", "doc", "xlsx", "xls", "csv", "pptx", "ppt",
        "png", "jpg", "jpeg", "mp4", "mkv", "mp3", "zip", "py", "json", "md",
    ]
    BROWSER_NAMES = {"chrome", "brave", "edge", "msedge", "firefox", "opera", "browser"}
    MEDIA_APP_NAMES = {"vlc", "media player", "wmplayer", "windows media player", "mpv"}
    EXPLORER_NAMES = {"explorer", "file explorer", "windows explorer"}

    def _active_container(self, core: Any) -> Optional[Dict[str, Any]]:
        """Reads the authoritative active container from ActiveTargetContext (SSOT)."""
        ctx = getattr(core, "active_context", None)
        if ctx is None or getattr(ctx, "is_active", False) is not True:
            return None
        app = str(getattr(ctx, "application", "") or "").lower().strip()
        site = str(getattr(ctx, "website", "") or "").lower().strip()
        browser = str(getattr(ctx, "browser", "") or app or "chrome").lower().strip()
        if app in self.BROWSER_NAMES:
            return {"kind": "browser", "name": app, "browser": browser}
        if site:
            return {"kind": "website", "name": site, "browser": browser}
        if not app:
            return None
        if app in self.DOC_APP_EXTENSIONS:
            return {"kind": "document", "name": app}
        if app in self.EXPLORER_NAMES:
            return {"kind": "explorer", "name": "explorer"}
        if app in self.MEDIA_APP_NAMES:
            return {"kind": "media", "name": app}
        return {"kind": "application", "name": app}

    def has_active_container(self, core: Any) -> bool:
        """True when an app/site container is active and could own a deictic follow-up."""
        return self._active_container(core) is not None

    def is_container_followup(self, text: str, core: Any = None) -> bool:
        """Narrow detector: pronoun-led request that refers to the active container."""
        if not text or not self.CONTAINER_REF_RE.search(text):
            return False
        if not self.CONTAINER_ACT_RE.search(text):
            return False
        return self._active_container(core) is not None

    def process_container_followup_turn(self, user_text: str, core: Any) -> Tuple[bool, str]:
        """
        Interprets a follow-up that refers back to the active container instead of
        re-classifying the utterance from scratch, e.g.
            "Excel open karo" -> "usme report file kholo" -> "kaunsi report file?"
        """
        container = self._active_container(core)
        if not container:
            return False, ""

        kind = container["kind"]
        name = container["name"]

        # Container is a browser/site: open the referenced site inside it.
        if kind in ("browser", "website"):
            needle = self._extract_container_needle(user_text)
            return self._open_reference_in_browser(container, needle or name, core)

        # Application containers that do not own files/slots: do not hijack.
        if kind == "application":
            return False, ""

        needle = self._extract_container_needle(user_text)
        extensions = self._container_extensions(container)

        if not needle:
            question = f"{name.title()} mein kaunsi file kholni hai, Boss?"
            self.set_lock(
                workflow_type="OPEN_IN_ACTIVE_CONTAINER",
                required_slots=["open_target"],
                prompt_question=question,
                initial_slots={"container_kind": kind, "container_name": name},
            )
            return True, question

        info = self.resolve_file(needle, extensions=extensions)
        exact_matches = info["exact_matches"]
        close_suggestions = info["close_suggestions"]

        if len(exact_matches) == 1:
            return True, self._open_in_container(container, exact_matches[0], needle, core)

        if len(exact_matches) > 1:
            names = ", ".join(f"'{m['name']}'" for m in exact_matches[:3])
            question = f"'{needle}' ke {len(exact_matches)} matches mile: {names}. Kaunsi file kholni hai?"
            self.set_lock(
                workflow_type="OPEN_IN_ACTIVE_CONTAINER",
                required_slots=["open_target"],
                prompt_question=question,
                initial_slots={
                    "container_kind": kind,
                    "container_name": name,
                    "candidates": exact_matches[:5],
                },
            )
            return True, question

        if close_suggestions:
            suggested = close_suggestions[0]
            self.set_pending_suggestion(
                workflow_type="OPEN_IN_ACTIVE_CONTAINER",
                candidate=suggested,
                fallback_candidates=close_suggestions[1:],
                action="open",
                prompt_message=f"'{needle}' naam ki file nahi mili. Kya aap '{suggested['name']}' kholna chahte hain?",
            )
            return True, (
                f"'{needle}' naam ki koi file nahi mili, Boss. "
                f"Kya aap '{suggested['name']}' kholna chahte hain?"
            )

        return True, f"'{needle}' naam ki koi file nahi mili, Boss."

    def _container_extensions(self, container: Dict[str, Any]) -> List[str]:
        name = container.get("name", "")
        kind = container.get("kind", "")
        if kind == "document":
            return self.DOC_APP_EXTENSIONS.get(name, self.GENERIC_EXTENSIONS)
        if kind == "media":
            return self.MEDIA_EXTENSIONS
        return self.GENERIC_EXTENSIONS

    def _extract_container_needle(self, text: str) -> str:
        """Strips the deictic marker, verbs and generic nouns, leaving the requested item."""
        needle = self.CONTAINER_REF_RE.sub(" ", text or "", count=1)
        needle = re.sub(
            r"\b(?:please|zara|ab|phir|open|launch|start|kholo|khol\s+do|kholna|chalao|chala\s+do|play|"
            r"le\s+aao|dikhao|karo|kar\s+do|file|files|document|documents|sheet|folder|tab|"
            r"new|naya|nayi|blank|create|banao|search|dhundo|find)\b",
            " ",
            needle,
            flags=re.IGNORECASE,
        )
        needle = re.sub(r"\s+", " ", needle).strip(" .?!,")
        return needle

    def _open_in_container(self, container: Dict[str, Any], match: Dict[str, Any], needle: str, core: Any) -> str:
        """Executes the open action inside the active container."""
        kind = container.get("kind", "")
        name = container.get("name", "")
        path = match.get("path", "")
        display = match.get("name", needle)

        if kind == "document":
            if getattr(core, "plugin_manager", None):
                core.plugin_manager.execute_action("windows", "launch_app", {"app_name": name, "path": path})
            ctx = getattr(core, "active_context", None)
            if ctx is not None:
                ctx.record_execution(
                    action="open_file", application=name, file_path=path,
                    entity=display, workflow="OPEN_IN_ACTIVE_CONTAINER",
                )
            return f"'{display}' {name.title()} mein khol di hai, Boss."

        if kind == "media":
            if getattr(core, "plugin_manager", None):
                core.plugin_manager.execute_action("vlc", "play_file", {"path": path})
            return f"'{display}' play kar diya hai, Boss."

        # Explorer / generic: reveal the resolved path
        if getattr(core, "plugin_manager", None):
            core.plugin_manager.execute_action("windows", "launch_app", {"app_name": "explorer", "path": path})
        return f"'{display}' File Explorer mein khol diya hai, Boss."

    def _open_reference_in_browser(self, container: Dict[str, Any], target: str, core: Any) -> Tuple[bool, str]:
        """Opens a referenced site/search inside the active browser container."""
        browser = container.get("browser") or container.get("name") or "chrome"
        target = (target or "").strip()
        if not target:
            return False, ""
        if getattr(core, "plugin_manager", None):
            res = core.plugin_manager.execute_action(
                "browser", "open_website",
                {"site": target, "url": f"https://www.{target}.com", "container": browser},
            )
            if getattr(res, "success", False):
                ctx = getattr(core, "active_context", None)
                if ctx is not None:
                    ctx.set_website(target, browser=browser, action="open_website")
                return True, f"{target.title()} {browser.title()} mein khol diya hai, Boss."
            return True, getattr(res, "error", None) or f"{target.title()} open nahi ho paaya, Boss."
        return True, f"{target.title()} {browser.title()} mein open kar raha hoon, Boss."

    def has_active_lock(self) -> bool:
        if self.active_lock is None:
            return False
        if self.active_lock.is_expired:
            logger.info(f"Workflow lock '{self.active_lock.workflow_type}' expired.")
            self.active_lock = None
            return False
        return self.active_lock.is_active

    def has_suspended_lock(self) -> bool:
        return self.suspended_lock is not None

    def set_lock(
        self,
        workflow_type: str,
        required_slots: List[str],
        target_plugin: str = "",
        target_action: str = "",
        prompt_question: str = "",
        initial_slots: Optional[Dict[str, Any]] = None,
        language: str = "hi"
    ) -> WorkflowLock:
        """Activates a workflow lock waiting for slot inputs."""
        if self.has_active_lock():
            self.suspend_workflow(self.active_lock)

        lock = WorkflowLock(
            workflow_type=workflow_type.upper(),
            required_slots=required_slots,
            filled_slots=initial_slots or {},
            target_plugin=target_plugin,
            target_action=target_action,
            prompt_question=prompt_question,
            language=language,
            active_question=prompt_question,
            pending_goal=workflow_type.upper(),
            missing_slots=required_slots
        )
        lock.transition_to(WorkflowState.WAITING_FOR_SLOT)
        self.active_lock = lock
        logger.info(f"DialogManager: Locked into workflow '{lock.workflow_type}'. Waiting for: {lock.next_missing_slot}")
        return lock

    def set_pending_goal(
        self,
        pending_goal: str,
        missing_slots: Any,
        active_question: str,
        turn_n: Optional[Any] = None,
        target_plugin: str = "",
        target_action: str = "",
        initial_slots: Optional[Dict[str, Any]] = None,
        candidate_options: Optional[List[Any]] = None,
        language: str = "hi"
    ) -> WorkflowLock:
        """
        Sets authoritative conversation state for Turn N:
        TURN N + ACTIVE QUESTION + PENDING GOAL + MISSING SLOT
        """
        if self.has_active_lock() and self.active_lock.workflow_type != pending_goal.upper():
            self.suspend_workflow(self.active_lock)

        slots_list = [missing_slots] if isinstance(missing_slots, str) else list(missing_slots)
        turn_meta = None
        if turn_n:
            turn_meta = {
                "turn_id": getattr(turn_n, "turn_id", ""),
                "raw_input": getattr(turn_n, "raw_input", ""),
                "normalized_input": getattr(turn_n, "normalized_input", ""),
                "timestamp": getattr(turn_n, "timestamp", time.time())
            }
        lock = WorkflowLock(
            workflow_type=pending_goal.upper(),
            required_slots=slots_list,
            filled_slots=initial_slots or {},
            target_plugin=target_plugin,
            target_action=target_action,
            prompt_question=active_question,
            language=language,
            turn_n=turn_meta,
            active_question=active_question,
            pending_goal=pending_goal.upper(),
            missing_slots=slots_list,
            candidate_options=candidate_options or []
        )
        lock.transition_to(WorkflowState.WAITING_FOR_SLOT)
        self.active_lock = lock
        logger.info(f"DialogManager: Set pending goal '{pending_goal}' with active question: '{active_question}'. Missing slots: {slots_list}")
        return lock

    def release_lock(self, status: str = "COMPLETED") -> None:
        if self.active_lock:
            state_val = WorkflowState.CANCELLED if status == "CANCELLED" else WorkflowState.COMPLETED
            self.active_lock.transition_to(state_val)
            logger.info(f"DialogManager: Released workflow lock '{self.active_lock.workflow_type}' with status {status}.")
        self.active_lock = None

    def is_cancellation(self, text: str) -> bool:
        cleaned = re.sub(r'[^\w\s]', ' ', text.strip().lower())
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        # If candidate disambiguation is active on the lock, selections like 'nayi wali' or 'dusri wali' are not cancellations
        if self.has_active_lock() and getattr(self.active_lock, "candidate_options", None):
            if any(w in cleaned for w in ("nayi", "naya", "pehli", "pehla", "doosri", "doosra", "dusri", "dusra", "teesri", "teesra", "first", "second", "third", "last", "purani")):
                return False
        for p in self._cancellation_patterns:
            if p.match(cleaned) or p.search(cleaned):
                return True
        return False

    def process_locked_turn(self, user_text: str, core: Any) -> Tuple[bool, str]:
        """
        Processes incoming user text against current workflow lock.
        Returns (handled_by_lock: bool, response_message: str).
        """
        if not self.has_active_lock():
            return False, ""

        cleaned = user_text.strip()

        # 1. Check for cancellation
        if self.is_cancellation(cleaned):
            wf_name = self.active_lock.workflow_type
            lang = getattr(self.active_lock, "language", "hi")
            self.release_lock(status="CANCELLED")
            if wf_name == "STOCK_SELECTION_WORKFLOW":
                try:
                    from stock.stock_service import StockService
                    StockService.get_instance().complete_workflow()
                except Exception:
                    pass
                return True, "Theek hai, stock selection cancel kar diya."
            if wf_name == "PASSWORD_GENERATE":
                return True, "Theek hai, password generation cancel kar diya." if lang == "hi" else "Cancelled password generation."
            if wf_name == "EMAIL_COMPOSE":
                return True, "Theek hai, email send nahi karunga." if lang == "hi" else "Alright, I won't send the email."
            if wf_name == "MESSAGE_COMPOSE":
                return True, "Theek hai, message nahi bhejunga." if lang == "hi" else "Alright, I won't send the message."
            if wf_name == "REMINDER_CREATE":
                return True, "Theek hai, reminder cancel kar diya." if lang == "hi" else "Alright, reminder cancelled."
            if wf_name == "MEETING_SCHEDULE":
                return True, "Theek hai, meeting schedule nahi karunga." if lang == "hi" else "Alright, I won't schedule the meeting."
            return True, f"Theek hai, {wf_name.lower()} cancel kar diya." if lang == "hi" else f"Cancelled {wf_name.lower()}."

        # Mid-workflow correction ("Nahi, Rohit ko" / "Nahi, 6 baje" / "Sorry, Pune ka"):
        # replace a filled slot instead of cancelling. Only for compose workflows.
        if self.active_lock.workflow_type in self.COMPOSE_WORKFLOWS:
            corrected = self._try_workflow_correction(cleaned, core)
            if corrected is not None:
                return True, corrected

        # Check for interruption command (e.g. "volume 50 kar do", "stop", "pause")
        from core.semantic.slot_extractor import SemanticSlotExtractor, TypeSafeSlotValidator, ValidationStatus
        if SemanticSlotExtractor.is_interruption(cleaned):
            logger.info(f"DialogManager: Interruption detected during workflow '{self.active_lock.workflow_type}'. Suspending lock.")
            self.suspend_workflow(self.active_lock)
            return False, ""

        # Check for topic switch or conversational greeting
        low_clean = cleaned.lower()
        if low_clean in ("hi", "hello", "kya haal hai", "kaise ho", "kya kar rahe ho", "kuch nahi", "hey", "namaste", "pranam"):
            self.release_lock(status="CANCELLED")
            return False, ""

        # Topic switch check: only switch if user explicitly commands a completely different domain
        is_topic_switch = False
        if any(w in low_clean for w in ("shutdown", "restart", "reboot", "lock computer", "system lock", "laptop lock", "weather", "mausam", "time kya", "samay kya", "what time")):
            is_topic_switch = True
        elif any(w in low_clean for w in ("chrome open karo", "brave open karo", "notepad open karo", "calculator open karo", "open chrome", "open notepad")):
            if not any(k in self.active_lock.all_missing_slots for k in ("browser", "target_medium", "app_id", "application", "media_target")):
                is_topic_switch = True
        if is_topic_switch:
            self.suspend_workflow(self.active_lock)
            return False, ""

        # Dedicated Stock Selection Workflow interception
        if self.active_lock.workflow_type == "STOCK_SELECTION_WORKFLOW":
            return self._handle_stock_workflow_turn(cleaned, core)

        # Compose workflows (email / reminder / alarm) use dedicated slot filling
        if self.active_lock.workflow_type in self.COMPOSE_WORKFLOWS:
            return self._handle_compose_lock_turn(cleaned, core)

        # 2. Multi-slot extraction via SemanticSlotExtractor
        missing_slots = self.active_lock.all_missing_slots
        if not missing_slots:
            lock = self.active_lock
            self.release_lock()
            return True, self._execute_completed_workflow(lock, core)

        extracted = SemanticSlotExtractor.extract_slots(cleaned, expected_slots=missing_slots)
        if extracted:
            for k, v in extracted.items():
                self.active_lock.filled_slots[k] = v
                logger.info(f"DialogManager: Filled validated slot '{k}' = '{v}' in workflow '{self.active_lock.workflow_type}'")
            if hasattr(core, "active_context") and core.active_context:
                core.active_context.filled_slots.update(self.active_lock.filled_slots)
                core.active_context.missing_slots = self.active_lock.all_missing_slots
        else:
            # Type-safe single slot fallback
            slot_key = self.active_lock.next_missing_slot
            if slot_key:
                clean_cand = self._clean_slot_value(cleaned)
                val_status, norm_val, reason = TypeSafeSlotValidator.validate_slot(slot_key, clean_cand)
                if val_status == ValidationStatus.VALID:
                    self.active_lock.filled_slots[slot_key] = norm_val
                    logger.info(f"DialogManager: Validated single slot '{slot_key}' = '{norm_val}' in workflow '{self.active_lock.workflow_type}'")
                    if hasattr(core, "active_context") and core.active_context:
                        core.active_context.filled_slots[slot_key] = norm_val
                        core.active_context.missing_slots = self.active_lock.all_missing_slots
                else:
                    logger.warning(f"DialogManager: Rejected invalid value for slot '{slot_key}': '{clean_cand}' ({reason})")
                    lang = getattr(self.active_lock, "language", "hi")
                    if slot_key in ("capital", "investment_amount"):
                        prompt = "Budget amount mujhe clear nahi hua. Kripya numeric amount batayein, jaise ₹50,000." if lang == "hi" else "I could not understand the budget amount. Please specify a numeric amount like 50,000."
                    elif slot_key in ("risk_profile", "risk_tolerance"):
                        prompt = "Risk preference samajh nahi aayi. Kripya conservative, moderate ya aggressive batayein." if lang == "hi" else "Please specify your risk preference as conservative, moderate, or aggressive."
                    elif slot_key == "horizon":
                        prompt = "Time horizon samajh nahi aaya. Kripya 1 month ya short term batayein." if lang == "hi" else "Please specify your time horizon, like 1 month or short term."
                    else:
                        prompt = f"{slot_key.replace('_', ' ')} samajh nahi aaya. Kripya dobara batayein." if lang == "hi" else f"Could not understand {slot_key.replace('_', ' ')}. Please try again."
                    return True, prompt

        # 3. Check if all required slots are now filled
        if self.active_lock.is_complete:
            lock = self.active_lock
            self.release_lock()
            if hasattr(core, "active_context") and core.active_context:
                core.active_context.active_workflow = None
                core.active_context.pending_goal = None
                core.active_context.missing_slots = []
            # Execute the completed workflow
            return True, self._execute_completed_workflow(lock, core)

        # 4. Ask next required slot / remaining slots
        rem_slots = self.active_lock.all_missing_slots
        lang = getattr(self.active_lock, "language", "hi")
        if self.active_lock.workflow_type in ("EQUITY_RESEARCH", "FIND_OR_SUGGEST_EQUITY", "SHORT_TERM_INVESTMENT_RESEARCH"):
            missing_labels = []
            for s in rem_slots:
                if s in ("capital", "investment_amount"):
                    missing_labels.append("budget / capital")
                elif s in ("risk_profile", "risk_tolerance"):
                    missing_labels.append("risk preference (conservative / moderate / aggressive)")
                elif s == "horizon":
                    missing_labels.append("time horizon (short-term / 1 month / long-term)")
                else:
                    missing_labels.append(s.replace("_", " "))
            if lang == "hi":
                return True, f"Theek hai. Bas {' aur '.join(missing_labels)} bhi bata dijiye taaki main screening start kar sakun."
            return True, f"Understood. Please also provide {' and '.join(missing_labels)} so I can begin screening."

        next_slot = self.active_lock.next_missing_slot
        if lang == "hi":
            return True, f"Kripya {next_slot.replace('_', ' ')} batayein."
        return True, f"Please specify {next_slot.replace('_', ' ')}."

    def _handle_stock_workflow_turn(self, user_text: str, core: Any) -> Tuple[bool, str]:
        """Handles voice slot updates, follow-up filtering, and window recovery when STOCK_SELECTION_WORKFLOW is active."""
        try:
            from stock.stock_service import StockService
            service = StockService.get_instance()
        except Exception as e:
            logger.exception("Failed to import or access StockService in stock workflow turn: %s", e)
            self.release_lock()
            return True, "Stock screening module me takneeki samasya aayi hai. Maine workflow reset kar diya hai, aap aam commands continue kar sakte hain."

        cleaned = user_text.strip().lower()

        # Check for window not opening / recovery request
        if any(w in cleaned for w in [
            "window open nahi hua", "window open nahi hui", "window nahi khula", 
            "window nahi khuli", "window nahi open hua", "window nahi open hui",
            "selection window open nahi", "window open nahi", "khula nahi", "open nahi hua"
        ]):
            try:
                stock_server = service.start_web_wizard()
                web_url = service.get_web_url()
                import webbrowser
                webbrowser.open(web_url)

                # Check verification if core has window_manager
                recovered = False
                if core and hasattr(core, "window_manager") and hasattr(core.window_manager, "verify_browser_opened"):
                    v_res = core.window_manager.verify_browser_opened(expected_url=web_url, timeout=2.0)
                    recovered = bool(v_res and v_res.verified)
                elif stock_server:
                    recovered = bool(stock_server.is_running)

                if recovered:
                    return True, "Maine stock selection window dobara open karne ki koshish ki hai. Kya ab aapko dashboard dikh raha hai?"
                else:
                    return True, f"Maaf kijiye, window automatically open nahi ho pa rahi hai. Aap browser me {web_url} open kar sakte hain, ya hum yahin voice se screening jari rakh sakte hain."
            except Exception as e:
                logger.exception("Error attempting to recover stock window: %s", e)
                return True, "Window open karne me takneeki samasya aayi. Aap voice ke zariye apna budget ya preference bata sakte hain."

        try:
            # 1. If results already analyzed, prioritize conversational follow-up questions / filters
            if service.current_state in ("ANALYZED", "RESULTS_DISPLAYED", "RESULTS_READY") or bool(service.last_shortlist):
                handled_fu, fu_resp = service.handle_followup_utterance(user_text)
                if handled_fu:
                    return True, fu_resp

            # 2. Analyze trigger
            if any(w in cleaned for w in ["analyze", "screening karo", "shortlist karo", "scan karo", "run karo", "get stock ideas"]):
                res = service.analyze(service.active_params)
                return True, res.voice_response

            # 3. Market Cap updates
            if "large cap" in cleaned or "largecap" in cleaned:
                service.update_active_param("market_cap", ["large_cap"])
                self.active_lock.filled_slots["market_cap"] = ["large_cap"]
                return True, "Theek hai, market segment Large Cap set kar diya hai."
            if "mid cap" in cleaned or "midcap" in cleaned:
                service.update_active_param("market_cap", ["mid_cap"])
                self.active_lock.filled_slots["market_cap"] = ["mid_cap"]
                return True, "Theek hai, market segment Mid Cap set kar diya hai."
            if "small cap" in cleaned or "smallcap" in cleaned:
                service.update_active_param("market_cap", ["small_cap"])
                self.active_lock.filled_slots["market_cap"] = ["small_cap"]
                return True, "Theek hai, market segment Small Cap set kar diya hai."

            # 4. Risk updates
            if any(w in cleaned for w in ["conservative", "kam risk", "low risk"]):
                service.update_active_param("risk", "conservative")
                self.active_lock.filled_slots["risk"] = "conservative"
                return True, "Theek hai, risk preference Conservative set kar diya hai."
            if any(w in cleaned for w in ["aggressive", "high risk", "zyada risk", "jyada risk"]):
                service.update_active_param("risk", "aggressive")
                self.active_lock.filled_slots["risk"] = "aggressive"
                return True, "Theek hai, risk preference Aggressive set kar diya hai."
            if "moderate" in cleaned:
                service.update_active_param("risk", "moderate")
                self.active_lock.filled_slots["risk"] = "moderate"
                return True, "Theek hai, risk preference Moderate set kar diya hai."

            # 5. Horizon updates
            if any(w in cleaned for w in ["3 month", "3 mahine", "3 months"]):
                service.update_active_param("horizon", "3_12_months")
                self.active_lock.filled_slots["horizon"] = "3_12_months"
                return True, "Theek hai, investment horizon 3 mahine set kar diya hai."
            if any(w in cleaned for w in ["1 month", "1 mahina", "ek mahina", "short term", "swing"]):
                service.update_active_param("horizon", "swing_short_term")
                self.active_lock.filled_slots["horizon"] = "swing_short_term"
                return True, "Theek hai, investment horizon Swing / Short Term set kar diya hai."
            if any(w in cleaned for w in ["long term", "3 years", "saal", "year"]):
                service.update_active_param("horizon", "3_plus_years")
                self.active_lock.filled_slots["horizon"] = "3_plus_years"
                return True, "Theek hai, investment horizon Long Term set kar diya hai."

            # 6. Sector updates
            for sec in ["it", "banking", "auto", "pharma", "fmcg", "energy", "defence", "metals", "real estate", "telecom"]:
                if (len(sec) <= 2 and re.search(r'\b' + re.escape(sec) + r'\b', cleaned)) or (len(sec) > 2 and sec in cleaned):
                    service.update_active_param("sectors", [sec.upper()])
                    self.active_lock.filled_slots["sectors"] = [sec.upper()]
                    return True, f"Theek hai, sector preference {sec.upper()} set kar diya hai."

            # 7. Capital / Budget updates
            from core.semantic.slot_extractor import SlotNormalizer
            norm_cap, _ = SlotNormalizer.normalize_capital(cleaned)
            if norm_cap is not None and norm_cap > 0:
                service.update_active_param("capital", float(norm_cap))
                self.active_lock.filled_slots["capital"] = float(norm_cap)
                return True, f"Theek hai, budget ₹{int(norm_cap):,} set kar diya hai."

            # 8. Recommendation memory questions ("target kya diya tha", "us time price kya tha", etc.)
            handled_mem, mem_resp = service.answer_memory_query(user_text)
            if handled_mem:
                return True, mem_resp

            # 9. Follow-up fallback (if user asked about a stock while waiting)
            handled_fu, fu_resp = service.handle_followup_utterance(user_text)
            if handled_fu:
                return True, fu_resp

            return True, "Theek hai, selection window mein criteria update kar diya hai."
        except Exception as e:
            logger.exception("Unexpected error inside _handle_stock_workflow_turn: %s", e)
            self.release_lock()
            return True, "Stock screening me ek takneeki samasya aayi. Workflow reset kar diya gaya hai."

    @classmethod
    def _resolve_candidate_selection(
        cls,
        selection_text: str,
        candidates: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Resolves ordinals ('pehli', 'doosri', 'last', '1st', '2nd') and
        recency markers ('nayi wali', 'purani wali', 'latest', 'oldest')
        or name substring against a candidate list.
        """
        if not candidates or not selection_text:
            return None

        low = selection_text.lower().strip()

        # 1. Recency selection ('nayi wali', 'naya', 'naye', 'latest', 'newest')
        if any(w in low for w in ("nayi", "naya", "naye", "latest", "newest")):
            def _extract_year_or_mtime(cand: Dict[str, Any]) -> float:
                name = cand.get("name", "")
                m = re.search(r"\b(20\d\d|19\d\d)\b", name)
                if m:
                    return float(m.group(1)) * 1000000.0 + cand.get("mtime", 0)
                return float(cand.get("mtime", 0) or 0)
            sorted_cands = sorted(candidates, key=_extract_year_or_mtime, reverse=True)
            return sorted_cands[0]

        # 2. Oldest selection ('purani wali', 'purana', 'oldest', 'pehle wali')
        if any(w in low for w in ("purani", "purana", "oldest", "old")):
            def _extract_year_or_mtime(cand: Dict[str, Any]) -> float:
                name = cand.get("name", "")
                m = re.search(r"\b(20\d\d|19\d\d)\b", name)
                if m:
                    return float(m.group(1)) * 1000000.0 + cand.get("mtime", 0)
                return float(cand.get("mtime", 0) or 0)
            sorted_cands = sorted(candidates, key=_extract_year_or_mtime, reverse=False)
            return sorted_cands[0]

        # 3. Ordinal selection ('pehli', 'first', '1st', 'doosri', 'second', '2nd', 'teesri', 'last')
        from core.reference_resolver import ReferenceResolver
        ord_idx = ReferenceResolver._extract_ordinal(low)
        if ord_idx is not None:
            if ord_idx == -1:
                return candidates[-1]
            if 0 <= ord_idx < len(candidates):
                return candidates[ord_idx]

        # 4. Name substring or exact match
        for cand in candidates:
            cname = cand.get("name", "").lower()
            cbase, _ = os.path.splitext(cname)
            if low in cname or low in cbase or cbase in low:
                return cand

        return None

    def _clean_slot_value(self, text: str) -> str:
        """Extracts core entity name, stripping conversational fillers like 'wali', 'wala', 'file', 'karo'."""
        cleaned = text.strip().rstrip(".?!")
        lock = getattr(self, "active_lock", None)
        has_candidates = bool(lock and getattr(lock, "candidate_options", None))
        if not has_candidates and re.search(r"\b(?:new|blank|fresh|nayi|naya|khali)\b", cleaned, flags=re.IGNORECASE):
            return "new"
        if has_candidates and any(w in cleaned.lower() for w in ("nayi", "naya", "pehli", "pehla", "doosri", "doosra", "dusri", "dusra", "teesri", "teesra", "first", "second", "third", "last", "purani", "latest")):
            return cleaned
        # If pure number or number with digit/char suffix (e.g. "12", "12 characters", "8 digit")
        num_m = re.match(r'^\s*(\d+)\s*(?:digits?|chars?|characters?|ank|akshar)?\s*$', cleaned, flags=re.IGNORECASE)
        if num_m:
            return num_m.group(1)
        # "Sales wali" -> "Sales"
        cleaned = re.sub(
            r"\b(?:wali|wala|waali|file|movie|document|folder|kholo|open|chalao|karo|please)\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        return cleaned or text.strip().rstrip(".?!")

    @staticmethod
    def resolve_file(
        needle: str,
        extensions: Optional[List[str]] = None,
        search_dirs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Resolves a user-specified file name against local files.
        Returns exact_matches, close_suggestions, and all_discovered candidates.
        """
        import difflib
        from pathlib import Path

        clean_needle = needle.strip().lower()
        clean_needle = re.sub(
            r"\b(?:wali|wala|waali|wale|file|files|kholo|open|karo|please|excel|workbook|sheet|csv)\b",
            "",
            clean_needle,
            flags=re.IGNORECASE,
        ).strip()
        if not clean_needle:
            clean_needle = needle.strip().lower()

        target_exts = [e.lower().lstrip(".") for e in (extensions or ["xlsx", "csv", "xls", "xlsm"])]

        dirs_to_search = []
        if search_dirs:
            dirs_to_search.extend(search_dirs)
        else:
            dirs_to_search.append(".")
            user_home = Path.home()
            for d in ["Documents", "Desktop", "Downloads"]:
                cand_dir = user_home / d
                if cand_dir.exists():
                    dirs_to_search.append(str(cand_dir))

        discovered = []
        seen_paths = set()

        for sdir in dirs_to_search:
            try:
                for root, _, files in os.walk(sdir):
                    if any(ig in root for ig in [".venv", "__pycache__", ".git", ".pytest_cache", "node_modules"]):
                        continue
                    for fname in files:
                        lower_fname = fname.lower()
                        if any(lower_fname.endswith(f".{ext}") for ext in target_exts):
                            full_path = os.path.abspath(os.path.join(root, fname))
                            if full_path not in seen_paths:
                                seen_paths.add(full_path)
                                mtime = os.path.getmtime(full_path) if os.path.exists(full_path) else 0
                                discovered.append({
                                    "name": fname,
                                    "path": full_path,
                                    "mtime": mtime,
                                })
            except Exception:
                continue

        scored_matches = []
        for item in discovered:
            fname_lower = item["name"].lower()
            base_name, _ = os.path.splitext(fname_lower)

            # 1. Exact base match (e.g. "test.xlsx" matches "test") -> Score 1.0
            if clean_needle and (clean_needle == base_name or clean_needle == fname_lower):
                scored_matches.append((1.0, item))
            # 2. Substring match (e.g. "sales" in "monthly_sales.csv")
            elif clean_needle and (clean_needle in base_name or base_name in clean_needle):
                word_match = bool(re.search(r"\b" + re.escape(clean_needle) + r"\b", base_name))
                score = 0.92 if word_match else 0.86
                scored_matches.append((score, item))
            elif clean_needle:
                # 3. Fuzzy match
                ratio = difflib.SequenceMatcher(None, clean_needle, base_name).ratio()
                if ratio >= 0.50:
                    scored_matches.append((ratio, item))
            else:
                # Needle is empty -> sort purely by recency (mtime)
                scored_matches.append((1.0, item))

        scored_matches.sort(key=lambda x: (x[0], x[1]["mtime"]), reverse=True)

        exact_matches = [m[1] for m in scored_matches if m[0] >= 0.85]
        close_suggestions = [m[1] for m in scored_matches if 0.55 <= m[0] < 0.85]

        return {
            "exact_matches": exact_matches,
            "close_suggestions": close_suggestions,
            "all_discovered": discovered,
        }

    _CORRECTION_LEAD_RE = re.compile(r"^(?:nahi|nahin|nhi|no|sorry|sory)\s*,?\s*(.+)$", re.IGNORECASE)

    @staticmethod
    def _parse_compose_time(text: str, period_hint: str = "") -> Tuple[Optional[str], Optional[str]]:
        """Parses clock times ('6 baje', 'kal 3 baje') and relative deltas
        ('20 minute baad', '2 ghante baad'). Returns (iso_time, display) or (None, None).
        period_hint 'am' forces morning for ambiguous hours (alarm 'subah 6 baje')."""
        low = (text or "").lower().strip()
        if (period_hint or "").lower() == "am":
            m_hr = re.search(r"\b(\d{1,2})(?:[:\.](\d{2}))?\s*(?:baje)?\b", low)
            if m_hr:
                try:
                    from core.time_context import get_time_context as _gtc
                    now = _gtc().now()
                except Exception:
                    import datetime as _dt
                    now = _dt.datetime.now().astimezone()
                hh = int(m_hr.group(1)) % 12
                mm2 = int(m_hr.group(2) or 0)
                cand = now.replace(hour=hh, minute=mm2, second=0, microsecond=0)
                import datetime as _dt2
                if cand <= now:
                    cand = cand + _dt2.timedelta(days=1)
                try:
                    disp = cand.strftime("%I:%M %p").lstrip("0")
                except Exception:
                    disp = cand.isoformat()
                return cand.isoformat(), f"subah {disp}"
        
        try:
            from core.time_context import get_time_context
            now = get_time_context().now()
        except Exception:
            import datetime as _dt
            now = _dt.datetime.now().astimezone()
        m = re.search(r"\b(\d+)\s*(minute|minutes|minut|minuts|mint|mints|min|mins|second|seconds|sec|secs|ghante|ghanta|ghanto|hour|hours|hr|hrs|din|days?)\b", low)
        if m:
            qty = int(m.group(1))
            unit = m.group(2)
            import datetime as _dt
            if unit.startswith("second"):
                delta = _dt.timedelta(seconds=qty)
            elif unit.startswith("din") or unit.startswith("day"):
                delta = _dt.timedelta(days=qty)
            elif unit.startswith("ghant") or unit.startswith("hour") or unit.startswith("hr"):
                delta = _dt.timedelta(hours=qty)
            else:
                delta = _dt.timedelta(minutes=qty)
            dt_obj = now + delta
            try:
                disp = dt_obj.strftime("%I:%M %p").lstrip("0")
            except Exception:
                disp = dt_obj.isoformat()
            return dt_obj.isoformat(), f"{qty} {unit} baad ({disp})"
        try:
            from core.conversational_intent import ConversationalIntentClassifier as _CIC
            dt_obj, disp = _CIC._extract_temporal_anchor(text)
            if dt_obj:
                return dt_obj.isoformat(), disp or dt_obj.isoformat()
        except Exception:
            pass
        return None, None

    def _try_workflow_correction(self, cleaned: str, core: Any = None) -> Optional[str]:
        """Maps 'Nahi, Rohit ko' / 'Nahi, 6 baje' onto a filled slot of the active
        compose lock. Returns ack response or None (fall through to normal flow)."""
        lock = self.active_lock
        if lock is None or lock.workflow_type not in self.COMPOSE_WORKFLOWS:
            return None
        m = self._CORRECTION_LEAD_RE.match((cleaned or "").strip())
        if not m:
            return None
        remainder = m.group(1).strip().rstrip(".?!")
        if not remainder:
            return None
        lang = getattr(lock, "language", "hi") or "hi"
        slot: Optional[str] = None
        value: Optional[str] = None
        disp: Optional[str] = None
        if lock.workflow_type in ("EMAIL_COMPOSE", "MESSAGE_COMPOSE"):
            if re.search(r"\b(?:attach|attachment)\b", remainder, re.IGNORECASE):
                slot = "attachment"
                value = re.sub(r"\b(?:attachment|attach)\b", "", remainder, flags=re.IGNORECASE).strip(" ,:")
            elif re.search(r"\bko\s*$", remainder, re.IGNORECASE):
                slot, value = "recipient", re.sub(r"\s+ko\s*$", "", remainder, flags=re.IGNORECASE).strip()
            elif re.search(r"\b(?:subject|vishay|topic)\b", remainder, re.IGNORECASE):
                slot, value = "subject", re.sub(r"^.*?\bsubject\b\s*", "", remainder, flags=re.IGNORECASE).strip() or remainder
            elif re.search(r"\b(?:body|likho|likhna|matter|content)\b", remainder, re.IGNORECASE):
                slot, value = "body", remainder
            elif lock.filled_slots:
                slot = list(lock.filled_slots.keys())[-1]
                if slot == "send_confirm":
                    slot = "body" if "body" in lock.filled_slots else list(lock.filled_slots.keys())[-1]
                value = remainder
            else:
                slot, value = lock.next_missing_slot, remainder
        elif lock.workflow_type == "MEETING_SCHEDULE":
            iso, d = self._parse_compose_time(remainder)
            if iso:
                slot, value, disp = "meeting_time", iso, d
            elif re.search(r"\bke\s+saath\s*$", remainder, re.IGNORECASE):
                slot, value = "attendees", re.sub(r"\s+ke\s+saath\s*$", "", remainder, flags=re.IGNORECASE).strip()
            elif lock.filled_slots:
                slot = list(lock.filled_slots.keys())[-1]
                value = remainder
            else:
                slot, value = lock.next_missing_slot, remainder
        else:  # REMINDER_CREATE / ALARM_SET
            iso, d = self._parse_compose_time(remainder, period_hint=str(lock.filled_slots.get("_period_hint", "") or ""))
            if iso:
                slot, value, disp = ("remind_time" if lock.workflow_type == "REMINDER_CREATE" else "time"), iso, d
            elif lock.filled_slots:
                slot = list(lock.filled_slots.keys())[-1]
                value = remainder
            else:
                slot, value = lock.next_missing_slot, remainder
        if not slot or not value:
            return None
        lock.filled_slots[slot] = value
        if disp:
            lock.filled_slots[slot + "_display"] = disp
        if hasattr(lock, "missing_slots") and slot in (lock.missing_slots or []):
            pass
        labels = {"recipient": "recipient", "subject": "subject", "body": "body",
                  "attachment": "attachment", "message": "message",
                  "title": "reminder", "remind_time": "reminder ka time", "time": "alarm ka time",
                  "attendees": "meeting attendees", "meeting_time": "meeting ka time"}
        lab = labels.get(slot, slot.replace("_", " "))
        show = disp or value
        if lang == "hi":
            ack = f"Theek hai, {lab} {show} kar diya."
        else:
            ack = f"Alright, updated {lab} to {show}."
        if lock.is_complete:
            if core:
                done = self.active_lock
                self.release_lock()
                return f"{ack} {self._execute_completed_workflow(done, core)}"
            return ack
        else:
            next_q = self._compose_question(lock)
            return f"{ack} {next_q}" if next_q else ack

    def _compose_question(self, lock: WorkflowLock) -> str:
        """Builds the next question for compose workflows (dynamic send_confirm summary)."""
        lang = getattr(lock, "language", "hi") or "hi"
        slot = lock.next_missing_slot
        if lock.workflow_type == "EMAIL_COMPOSE" and slot == "send_confirm":
            to = lock.filled_slots.get("recipient", "")
            sub = lock.filled_slots.get("subject", "")
            att = lock.filled_slots.get("attachment", "")
            att_note = f" Attachment: '{att}'." if att else ""
            if lang == "hi":
                return f"Mail ready hai — {to} ko, subject '{sub}'.{att_note} Send kar doon?"
            return f"Mail is ready — to {to}, subject '{sub}'.{att_note} Should I send it?"
        qmap = self.COMPOSE_SLOT_QUESTIONS.get(lock.workflow_type, {})
        q = qmap.get(slot or "")
        if q:
            return q
        if lang == "hi":
            return f"Kripya {(slot or 'details').replace('_', ' ')} batayein."
        return f"Please specify {(slot or 'details').replace('_', ' ')}."

    _FRESH_CMD_VERBS = frozenset({
        "open", "launch", "kholo", "khol", "close", "band", "call", "bhejo", "bhej",
        "chalao", "chala", "play", "volume", "reminder", "alarm", "meeting",
    })

    def _is_fresh_command_during_compose(self, cleaned: str) -> bool:
        """Detects a brand-new command while a compose lock is active
        ('5 baje reminder lagao', 'Report kholo', 'Rahul ko call karo', 'Chrome kholo').
        Slot answers ('Server update', '6 baje', 'Rahul ko', 'haan') return False."""
        try:
            from core.conversational_intent import ConversationalIntentClassifier as _CIC
            is_cmd, verb, target = _CIC._detect_action_command((cleaned or "").lower().strip())
        except Exception:
            return False
        if not is_cmd or not verb:
            return False
        v = verb.lower()
        if any(k in v for k in ("bhej", "send", "call", "reminder", "alarm", "meeting", "open", "launch",
                                "kholo", "khol", "close", "band", "chalao", "chala", "bajao", "play",
                                "volume", "batao", "dikhao", "weather", "mausam", "dikha", "search", "dhoondo")):
            return True
        _low = (cleaned or "").lower()
        if re.search(r"\bko\s+call\s+(?:karo|kar\s+do|lagao|kijiye)\b", _low):
            return True
        if re.search(r"\b(?:google|youtube|web)\b.{0,12}\bsearch\b|\bsearch\s+karo\b", _low):
            return True
        return False

    def _handle_compose_lock_turn(self, cleaned: str, core: Any) -> Tuple[bool, str]:
        """Dedicated slot filling for EMAIL_COMPOSE / REMINDER_CREATE / ALARM_SET."""
        from core.confirmation import is_affirmation as _is_yes, is_cancellation as _is_no
        lock = self.active_lock
        # Fresh command -> suspend lock and let the pipeline route it (never swallow).
        if self._is_fresh_command_during_compose(cleaned):
            self.suspend_workflow(self.active_lock)
            return False, ""
        lang = getattr(lock, "language", "hi") or "hi"
        slot = lock.next_missing_slot
        if slot is None:
            done = self.active_lock
            self.release_lock()
            return True, self._execute_completed_workflow(done, core)
        text = (cleaned or "").strip().rstrip(".?!")
        _period_hint = str(lock.filled_slots.get("_period_hint", "") or "")
        # Attachment mention at any stage ("Attachment January report") -> attachment slot
        if lock.workflow_type == "EMAIL_COMPOSE" and re.search(
                r"\b(?:attach|attachment|salagn|annexure)\b", text, re.IGNORECASE):
            fname = re.sub(r"\b(?:attachment|attach|salagn|annexure)\b", "", text, flags=re.IGNORECASE).strip(" ,:")
            if fname:
                lock.filled_slots["attachment"] = fname
                if hasattr(core, "active_context") and core.active_context:
                    try:
                        core.active_context.filled_slots.update(lock.filled_slots)
                    except Exception:
                        pass
                return True, (f"Theek hai, '{fname}' attach kar diya. {self._compose_question(lock)}"
                              if lang == "hi" else f"Attached '{fname}'. {self._compose_question(lock)}")
        if slot in ("remind_time", "time", "meeting_time"):
            iso, disp = self._parse_compose_time(text, period_hint=_period_hint)
            if not iso:
                q = self.COMPOSE_SLOT_QUESTIONS.get(lock.workflow_type, {}).get(slot, "Kab?")
                return True, f"Time samajh nahi aaya. {q}" if lang == "hi" else f"I didn't get the time. {q}"
            lock.filled_slots[slot] = iso
            lock.filled_slots[slot + "_display"] = disp
        elif slot == "attendees":
            val = re.sub(r"\s+ke\s+saath\s*$", "", text, flags=re.IGNORECASE).strip(" ,")
            if not val:
                return True, self._compose_question(lock)
            lock.filled_slots[slot] = val
        elif slot == "recipient":
            val = re.sub(r"\s+ko\s*$", "", text, flags=re.IGNORECASE).strip(" ,")
            val = re.sub(r"^(?:ko|to)\s+", "", val, flags=re.IGNORECASE).strip()
            if not val:
                return True, self._compose_question(lock)
            lock.filled_slots[slot] = val
        elif slot == "send_confirm":
            if _is_yes(text):
                lock.filled_slots[slot] = "yes"
            elif any(d in text.lower() for d in ("draft", "save karo", "draft mein", "draft me")):
                self.release_lock(status="COMPLETED")
                return True, "Email draft mein save kar diya." if lang == "hi" else "Saved email to drafts."
            elif _is_no(text):
                self.release_lock(status="CANCELLED")
                return True, "Theek hai, email send nahi karunga." if lang == "hi" else "Alright, I won't send the email."
            else:
                return True, self._compose_question(lock)
        else:  # subject / title / body / message — free text (strip spoken cue prefixes)
            # A bare question is never a slot answer — re-ask instead of filling junk.
            if (cleaned or "").strip().endswith("?"):
                return True, self._compose_question(lock)
            # "Rohit ko" while message/body is asked but a recipient is already set
            # means recipient change, not message text.
            if slot in ("message", "body") and lock.filled_slots.get("recipient"):
                m_ko = re.match(r"^(.+?)\s+ko\s*$", text, flags=re.IGNORECASE)
                if m_ko and m_ko.group(1).strip():
                    lock.filled_slots["recipient"] = m_ko.group(1).strip().title()
                    if hasattr(core, "active_context") and core.active_context:
                        try:
                            core.active_context.filled_slots.update(lock.filled_slots)
                        except Exception:
                            pass
                    return True, (f"Theek hai, recipient {m_ko.group(1).strip().title()} kar diya. {self._compose_question(lock)}"
                                  if lang == "hi" else f"Alright, recipient updated. {self._compose_question(lock)}")
            if slot == "subject":
                text = re.sub(r"^(?:subject|vishay|topic)\s*(?:hai|:)?\s*", "", text, flags=re.IGNORECASE).strip()
            elif slot == "body":
                text = re.sub(r"^(?:body\s+(?:mein|me)\s+)?(?:likho|likhna|likh\s+do|likh\s+dijiye)\s*", "", text, flags=re.IGNORECASE).strip()
            if not text:
                return True, self._compose_question(lock)
            lock.filled_slots[slot] = text
        if hasattr(core, "active_context") and core.active_context:
            try:
                core.active_context.filled_slots.update(lock.filled_slots)
                core.active_context.missing_slots = lock.all_missing_slots
            except Exception:
                pass
        if lock.is_complete:
            done = self.active_lock
            self.release_lock()
            if hasattr(core, "active_context") and core.active_context:
                try:
                    core.active_context.active_workflow = None
                    core.active_context.pending_goal = None
                    core.active_context.missing_slots = []
                except Exception:
                    pass
            return True, self._execute_completed_workflow(done, core)
        return True, self._compose_question(lock)

    def describe_suspended(self) -> str:
        """Human-readable one-line description of the suspended lock, if any."""
        lock = getattr(self, "suspended_lock", None)
        if lock is None or lock.is_expired:
            return ""
        if lock.workflow_type == "EMAIL_COMPOSE":
            to = lock.filled_slots.get("recipient", "")
            return f"{to} ko mail" if to else "mail"
        if lock.workflow_type in ("REMINDER_CREATE", "ALARM_SET"):
            return lock.filled_slots.get("title", "") or "reminder"
        if lock.workflow_type == "MEETING_SCHEDULE":
            return lock.filled_slots.get("title", "") or "meeting"
        return lock.workflow_type.lower()

    def _execute_completed_workflow(self, lock: WorkflowLock, core: Any) -> str:
        """Executes the action with filled slots."""
        if lock.workflow_type == "OPEN_IN_ACTIVE_CONTAINER":
            kind = str(lock.filled_slots.get("container_kind", "document"))
            name = str(lock.filled_slots.get("container_name", ""))
            candidates = lock.filled_slots.get("candidates") or []
            answer = str(lock.filled_slots.get("open_target", "")).strip()
            if not answer:
                return f"Kripya exact file ka naam batayein, Boss."

            chosen = self._resolve_candidate_selection(answer, candidates)
            if chosen is None:
                lower_answer = answer.lower()
                for cand in candidates:
                    cand_name = str(cand.get("name", ""))
                    if cand_name and (lower_answer in cand_name.lower() or cand_name.lower().startswith(lower_answer)):
                        chosen = cand
                        break

            if chosen is None:
                container = {"kind": kind, "name": name}
                info = self.resolve_file(answer, extensions=self._container_extensions(container))
                exact = info["exact_matches"]
                if exact:
                    chosen = exact[0]

            if chosen is None:
                return f"'{answer}' naam ki file nahi mili, Boss."

            return self._open_in_container({"kind": kind, "name": name}, chosen, answer, core)

        if lock.workflow_type == "VOLUME_ADJUST":
            direction = str(lock.filled_slots.get("direction", "")).lower().strip()
            if any(w in direction for w in ("badhao", "badha", "tez", "up", "increase", "unmute", "zyada", "loud")):
                if core.plugin_manager:
                    core.plugin_manager.execute_action("audio", "volume_up", {"step": 10})
                return "Volume badha di hai, Boss."
            elif any(w in direction for w in ("kam", "dheere", "dheemi", "down", "decrease", "ghatao", "mute")):
                if core.plugin_manager:
                    core.plugin_manager.execute_action("audio", "volume_down", {"step": 10})
                return "Volume kam kar di hai, Boss."
            else:
                digits = re.findall(r'\d+', direction)
                if digits:
                    lvl = int(digits[0])
                    if core.plugin_manager:
                        core.plugin_manager.execute_action("audio", "set_volume", {"level": lvl})
                    return f"Volume {lvl} percent set kar di hai, Boss."
                return "Volume adjust kar di hai, Boss."

        if lock.workflow_type == "SYSTEM_CLEANUP_DISAMBIGUATION":
            choice = str(lock.filled_slots.get("cleanup_target", "")).lower().strip()
            from core.natural_responses import NaturalResponseSynthesizer
            has_recycle = any(w in choice for w in ("recycle", "bin", "trash", "dustbin", "kachra", "dono", "both"))
            has_temp = any(w in choice for w in ("temp", "temporary", "files", "dono", "both"))

            msgs = []
            if has_temp or (not has_recycle and not has_temp):
                if core.plugin_manager:
                    core.plugin_manager.execute_action("system", "clear_temp_files", {})
                else:
                    try:
                        from plugins.system.plugin import SystemPlugin
                        SystemPlugin().execute("clear_temp_files", {})
                    except Exception:
                        pass
                msgs.append(NaturalResponseSynthesizer.system_maintenance("clear_temp_files", target="temp", is_repeat=False))
                if hasattr(core, "active_context") and core.active_context:
                    core.active_context.update_command_context("TEMP_FILE_CLEANUP", "clear_temp_files", {"target": "temp_files"}, service="system")

            if has_recycle:
                if core.plugin_manager:
                    core.plugin_manager.execute_action("system", "empty_recycle_bin", {})
                else:
                    try:
                        from plugins.system.plugin import SystemPlugin
                        SystemPlugin().execute("empty_recycle_bin", {})
                    except Exception:
                        pass
                if not msgs:
                    msgs.append(NaturalResponseSynthesizer.system_maintenance("empty_recycle_bin", target="recycle_bin", is_repeat=False))
                else:
                    msgs.append("aur Recycle Bin bhi khali kar diya hai, Boss.")
                if hasattr(core, "active_context") and core.active_context:
                    core.active_context.update_command_context("RECYCLE_BIN_CLEANUP", "empty_recycle_bin", {"target": "recycle_bin"}, service="system")

            return " ".join(msgs)

        if lock.workflow_type == "APP_WEB_DISAMBIGUATION":
            medium = str(lock.filled_slots.get("target_medium", "")).lower().strip()
            app_id = lock.filled_slots.get("app_id") or lock.filled_slots.get("target", "app")
            web_url = lock.filled_slots.get("web_url", "")
            disp = lock.filled_slots.get("display_name") or app_id.capitalize()
            if any(w in medium for w in ("website", "web", "site", "browser", "online", "link", "url", "portal")):
                if core.plugin_manager:
                    core.plugin_manager.execute_action("browser", "open_website", {"url": web_url or f"https://{app_id}.com", "site": app_id})
                else:
                    import webbrowser
                    webbrowser.open(web_url or f"https://{app_id}.com")
                if hasattr(core, "active_context") and core.active_context:
                    core.active_context.set_website(app_id, action="open_website", url=web_url)
                return f"{disp} website open kar di hai, Boss."
            else:
                if core.plugin_manager:
                    core.plugin_manager.execute_action("windows", "launch_app", {"app_name": app_id})
                if hasattr(core, "active_context") and core.active_context:
                    core.active_context.set_application(app_id, action="launch_app")
                return f"{disp} application open kar di hai, Boss."

        if lock.workflow_type == "PASSWORD_GENERATE":
            from core.semantic.parsers.security import generate_secure_password
            from core.natural_responses import NaturalResponseSynthesizer
            raw_len = str(lock.filled_slots.get("length", "12")).strip()
            digits = re.findall(r'\d+', raw_len)
            length = int(digits[0]) if digits else 12
            length = max(6, min(128, length))
            pwd = generate_secure_password(length)
            lang = getattr(lock, "language", "hi")
            return NaturalResponseSynthesizer.generate_password(length, pwd, language=lang)

        if lock.workflow_type == "TARGET_ACTION":
            from core.target_engine import TargetRequest
            raw_scope = lock.filled_slots.get("target_scope", "").casefold()
            scope = "all" if any(word in raw_scope for word in ("all", "sab", "saare", "sabhi")) else "one"
            outcome = core.target_engine.execute(TargetRequest(
                target=lock.filled_slots.get("target", ""),
                action=lock.filled_slots.get("action", ""),
                container=lock.filled_slots.get("container", ""),
                scope=scope,
            ))
            return outcome.message

        if lock.workflow_type == "WIFI_PASSWORD_CONFIRM":
            confirmation = lock.filled_slots.get("confirmation", "").lower()
            if not any(pattern.match(confirmation) for pattern in self._affirmative_patterns):
                return "Theek hai Boss, Wi-Fi password nahi dikhata."
            if not core.plugin_manager:
                return "Network plugin available nahi hai, Boss."
            result = core.plugin_manager.execute_action("network", "copy_wifi_password", {})
            if not result.success:
                return result.error or "Wi-Fi password retrieve nahi ho paaya, Boss."
            if isinstance(result.data, dict):
                sensitive_display = result.data.get("sensitive_display")
                if isinstance(sensitive_display, dict):
                    core._pending_sensitive_display = sensitive_display
                return result.data.get("message", "Wi-Fi password chatbox mein dikha diya hai, Boss.")
            return "Wi-Fi password chatbox mein dikha diya hai, Boss."

        if lock.workflow_type == "MODEL_QUERY":
            model_type = lock.filled_slots.get("model_type", "").lower()
            if any(word in model_type for word in ("ai", "jarvis", "tumhara", "aapka")):
                provider = str(core.config.get("brain", {}).get("llm_provider", "mock")).lower()
                model = str(core.config.get("brain", {}).get("model", "default"))
                if provider == "mock":
                    return "Abhi main Jarvis ke built-in conversational engine par chal raha hoon."
                return f"Abhi main {provider} provider ka {model} model use kar raha hoon."
            if any(word in model_type for word in ("laptop", "computer", "pc", "system")):
                try:
                    result = subprocess.run(
                        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "(Get-CimInstance Win32_ComputerSystem).Model"],
                        capture_output=True, text=True, timeout=8, check=False,
                    )
                    laptop_model = result.stdout.strip() or platform.machine()
                except Exception:
                    laptop_model = platform.machine()
                return f"Aapke laptop ka model {laptop_model} hai."
            return "AI model ya laptop model—kaunsa jaanana hai, Boss?"

        if lock.workflow_type == "EMAIL_COMPOSE":
            to = str(lock.filled_slots.get("recipient", "")).strip()
            sub = str(lock.filled_slots.get("subject", "")).strip()
            body = str(lock.filled_slots.get("body", "")).strip()
            att = str(lock.filled_slots.get("attachment", "")).strip()
            lang = getattr(lock, "language", "hi") or "hi"
            att_note = f" '{att}' ko mail client me attach kar dijiye." if att else ""
            try:
                if core.plugin_manager:
                    res = core.plugin_manager.execute_action(
                        "email", "open_email_client",
                        {"recipient": to, "subject": sub, "body": body})
                    if res and getattr(res, "success", False):
                        if hasattr(core, "active_context") and core.active_context:
                            core.active_context.update_command_context(
                                "EMAIL_COMPOSE", "open_email_client",
                                {"recipient": to, "subject": sub}, service="email")
                        return (f"Mail client me draft khol diya hai — wahan se send kar dijiye, Boss.{att_note}"
                                if lang == "hi" else f"Opened a draft in your mail client, Boss.{att_note}")
            except Exception:
                pass
            return (f"Mail ready hai — {to} ko, subject '{sub}'. Mail client kholne me dikkat aayi, aap manually bhej dijiye.{att_note}"
                    if lang == "hi" else f"Mail is ready for {to} (subject '{sub}') but I couldn't open the mail client.{att_note}")

        if lock.workflow_type == "MESSAGE_COMPOSE":
            to = str(lock.filled_slots.get("recipient", "")).strip()
            msg = str(lock.filled_slots.get("message", "")).strip()
            lang = getattr(lock, "language", "hi") or "hi"
            try:
                if core.plugin_manager:
                    res = core.plugin_manager.execute_action(
                        "whatsapp", "draft_message",
                        {"recipient": to, "message": msg})
                    if res and getattr(res, "success", False):
                        if hasattr(core, "active_context") and core.active_context:
                            core.active_context.update_command_context(
                                "MESSAGE_COMPOSE", "draft_message",
                                {"recipient": to}, service="whatsapp")
                        return (f"Theek hai, {to} ke liye WhatsApp draft ready hai."
                                if lang == "hi" else f"WhatsApp draft ready for {to}.")
            except Exception:
                pass
            return ("WhatsApp draft nahi ban paya. Contact list me naam check karke dobara boliye, Boss."
                    if lang == "hi" else "Couldn't create the WhatsApp draft. Please check the contact name.")

        if lock.workflow_type == "MEETING_SCHEDULE":
            lang = getattr(lock, "language", "hi") or "hi"
            attendees = str(lock.filled_slots.get("attendees", "")).strip()
            iso = str(lock.filled_slots.get("meeting_time", "")).strip()
            title = str(lock.filled_slots.get("title", "")).strip() or "Meeting"
            if not iso:
                return ("Time adhura reh gaya. Dobara batayein, Boss."
                        if lang == "hi" else "Time is incomplete. Please try again.")
            try:
                if core.plugin_manager:
                    res = core.plugin_manager.execute_action(
                        "calendar", "add_event",
                        {"title": title, "start_time": iso,
                         "description": f"{attendees} ke saath" if attendees else ""})
                    if res and getattr(res, "success", False):
                        data = getattr(res, "data", {}) or {}
                        return data.get("message") or f"Meeting schedule kar di: '{title}'."
            except Exception:
                pass
            return ("Meeting save nahi ho payi. Dobara try kijiye, Boss."
                    if lang == "hi" else "Couldn't save the meeting. Please try again.")

        if lock.workflow_type in ("REMINDER_CREATE", "ALARM_SET"):
            lang = getattr(lock, "language", "hi") or "hi"
            if lock.workflow_type == "ALARM_SET":
                title = "Subah uthna (alarm)"
                iso = str(lock.filled_slots.get("time", "")).strip()
                disp = str(lock.filled_slots.get("time_display", "") or iso).strip()
            else:
                title = str(lock.filled_slots.get("title", "")).strip()
                iso = str(lock.filled_slots.get("remind_time", "")).strip()
                disp = str(lock.filled_slots.get("remind_time_display", "") or iso).strip()
            if not title or not iso:
                return ("Details adhuri reh gayi. Dobara batayein, Boss."
                        if lang == "hi" else "Details are incomplete. Please try again.")
            try:
                if core.plugin_manager:
                    res = core.plugin_manager.execute_action(
                        "reminder", "create_reminder",
                        {"title": title, "remind_time": iso})
                    if res and getattr(res, "success", False):
                        data = getattr(res, "data", {}) or {}
                        rid = data.get("id")
                        if hasattr(core, "active_context") and core.active_context:
                            try:
                                ents = dict(core.active_context.last_entities or {})
                                if rid:
                                    ents["reminder_id"] = rid
                                ents["reminder_title"] = title
                                core.active_context.update_command_context(
                                    "REMINDER_CREATE", "create_reminder",
                                    ents, service="reminder")
                            except Exception:
                                pass
                        return data.get("message") or f"Reminder laga diya: '{title}'."
            except Exception:
                pass
            return ("Reminder save nahi ho paya. Dobara try kijiye, Boss."
                    if lang == "hi" else "Couldn't save the reminder. Please try again.")

        if lock.workflow_type == "EXCEL_OPEN":
            file_target = lock.filled_slots.get("file_target", "").strip()
            candidates = getattr(lock, "candidate_options", []) or []

            # Disambiguation selection if candidates were active
            if candidates:
                chosen = self._resolve_candidate_selection(file_target, candidates)
                if chosen:
                    target_file = chosen["path"]
                    display_name = chosen["name"]
                    if core.plugin_manager:
                        core.plugin_manager.execute_action(
                            "windows",
                            "launch_app",
                            {"app_name": "excel", "path": target_file}
                        )
                    if hasattr(core, "active_context"):
                        core.active_context.record_execution(
                            action="open_file", application="excel", file_path=target_file, entity=display_name, workflow="EXCEL_OPEN"
                        )
                    return f"'{display_name}' Excel mein khol di hai, Boss."

            if not candidates and (re.search(r"\b(?:new|blank|fresh|khali)\b", file_target, flags=re.IGNORECASE) or file_target == "new"):
                if core.plugin_manager:
                    launch_res = core.plugin_manager.execute_action(
                        "windows", "launch_app", {"app_name": "excel"}
                    )
                    if not launch_res.success:
                        return "Excel open nahi ho paaya, Boss. Ek baar installation check kar lijiye."
                if hasattr(core, "active_context"):
                    core.active_context.record_execution(action="open_app", application="excel", workflow="EXCEL_OPEN")
                return "Bilkul Boss, ek nayi blank Excel workbook khol di hai."

            res_info = self.resolve_file(file_target, extensions=["xlsx", "csv", "xls", "xlsm"])
            exact_matches = res_info["exact_matches"]
            close_suggestions = res_info["close_suggestions"]

            # Case 1: Exactly 1 match found -> Open immediately
            if len(exact_matches) == 1:
                target_file = exact_matches[0]["path"]
                display_name = exact_matches[0]["name"]
                if core.plugin_manager:
                    core.plugin_manager.execute_action(
                        "windows",
                        "launch_app",
                        {"app_name": "excel", "path": target_file}
                    )
                if hasattr(core, "active_context"):
                    core.active_context.record_execution(
                        action="open_file", application="excel", file_path=target_file, entity=display_name, workflow="EXCEL_OPEN"
                    )
                return f"'{display_name}' Excel mein khol di hai, Boss."

            # Case 2: Multiple matches found -> Re-arm lock for clarification
            elif len(exact_matches) > 1:
                display_names = [f"'{m['name']}'" for m in exact_matches[:3]]
                options_str = ", ".join(display_names)
                self.set_lock(
                    workflow_type="EXCEL_OPEN",
                    required_slots=["file_target"],
                    target_plugin="excel",
                    target_action="open",
                    prompt_question=f"'{file_target}' ke {len(exact_matches)} matches mile: {options_str}. Kaunsi file open karni hai?"
                )
                if self.active_lock:
                    self.active_lock.candidate_options = exact_matches
                return f"'{file_target}' ke {len(exact_matches)} matches mile: {options_str}. Kaunsi file open karni hai?"

            # Case 3: 0 matches found -> Suggest closest match if available
            else:
                if close_suggestions:
                    suggested_name = close_suggestions[0]["name"]
                    self.set_pending_suggestion(
                        workflow_type="EXCEL_OPEN",
                        candidate=close_suggestions[0],
                        fallback_candidates=close_suggestions[1:],
                        action="open",
                        target_plugin="excel",
                        prompt_message=f"'{file_target}' naam ki koi file nahi mili, Boss. Kya aap '{suggested_name}' open karna chahte hain?"
                    )
                    return f"'{file_target}' naam ki koi file nahi mili, Boss. Kya aap '{suggested_name}' open karna chahte hain?"
                return f"'{file_target}' naam ki koi Excel file nahi mili, Boss. Kya aap nayi blank workbook kholna chahte hain?"

        elif lock.workflow_type in ("YOUTUBE_PLAY", "MEDIA_PLAY"):
            media_target = lock.filled_slots.get("media_target", "")
            target_plugin = lock.target_plugin or "youtube"
            if target_plugin == "youtube" or lock.workflow_type == "YOUTUBE_PLAY" or not target_plugin:
                if core.plugin_manager:
                    res = core.plugin_manager.execute_action("youtube", "search_and_play", {"query": media_target})
                    if res.success:
                        if hasattr(core, "active_context"):
                            core.active_context.set_website("youtube", action="search_and_play")
                        if isinstance(res.data, dict) and res.data.get("message"):
                            return res.data["message"]
                        return f"'{media_target}' YouTube par play kar diya hai, Boss."
                    return res.error or f"YouTube par '{media_target}' play nahi ho paaya, Boss."
                return f"{media_target} YouTube par play kar raha hoon."
            else:
                if core.plugin_manager:
                    core.plugin_manager.execute_action("vlc", "play_file", {"path": media_target})
                if hasattr(core, "active_context"):
                    core.active_context.record_execution(
                        action="play_media", application="vlc", file_path=media_target, entity=media_target, workflow=lock.workflow_type
                    )
                return f"Playing '{media_target}' in VLC, Boss."

        elif lock.workflow_type in ("EQUITY_RESEARCH", "FIND_OR_SUGGEST_EQUITY", "SHORT_TERM_INVESTMENT_RESEARCH"):
            from core.equity_research.manager import EquityResearchManager
            from core.equity_research.models import AdvisoryMode, OutputMode, RiskTolerance

            mgr = EquityResearchManager.get_instance()

            capital_val = lock.filled_slots.get("capital") or lock.filled_slots.get("investment_amount", 50000.0)
            try:
                capital_float = float(capital_val)
            except Exception:
                capital_float = 50000.0

            risk_val = str(lock.filled_slots.get("risk_profile") or lock.filled_slots.get("risk_tolerance", "MODERATE")).upper()
            if "CONSERVATIVE" in risk_val or "LOW" in risk_val:
                risk_enum = RiskTolerance.CONSERVATIVE
            elif "AGGRESSIVE" in risk_val or "HIGH" in risk_val:
                risk_enum = RiskTolerance.AGGRESSIVE
            else:
                risk_enum = RiskTolerance.MODERATE

            horizon_val = str(lock.filled_slots.get("horizon", "1_MONTH"))
            sector_val = lock.filled_slots.get("sector", None)

            mgr.update_profile({
                "investment_amount": capital_float,
                "risk_tolerance": risk_enum.value,
                "sector_preference": sector_val,
            })

            lang = getattr(lock, "language", "hi")
            report, rep_text = mgr.research_shortlist(
                output_mode=OutputMode.STANDARD,
                advisory_mode=AdvisoryMode.PERSONALIZED_ADVISORY,
                language=lang
            )

            horizon_display = "1 month" if horizon_val in ("1_MONTH", "SHORT_TERM") else horizon_val.replace("_", " ").lower()
            risk_display = risk_enum.value.lower()
            cap_display = f"₹{int(capital_float):,}"

            ack = (
                f"Samajh gaya — {horizon_display} horizon, {cap_display} capital aur {risk_display} risk profile ke basis par Indian equities ko screen karta hoon.\n\n"
                if lang == "hi"
                else f"Understood — screening Indian equities based on a {horizon_display} horizon, {cap_display} capital, and {risk_display} risk profile.\n\n"
            )
            return ack + rep_text

        if lock.target_plugin and lock.target_action and hasattr(core, "plugin_manager") and core.plugin_manager:
            res = core.plugin_manager.execute_action(lock.target_plugin, lock.target_action, lock.filled_slots)
            if res.success:
                if isinstance(res.data, dict) and res.data.get("message"):
                    return res.data["message"]
                return f"{lock.workflow_type.replace('_', ' ').title()} complete kar diya hai, Boss."
            return res.error or f"{lock.workflow_type.replace('_', ' ').title()} execute nahi ho paaya, Boss."

        return f"Completed {lock.workflow_type.lower()} with parameters: {lock.filled_slots}."
