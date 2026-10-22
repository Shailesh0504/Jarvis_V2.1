# tests/test_multi_workflow_runtime_state.py
"""Unit and integration tests for Multi-Workflow Runtime State & State Machine (Step 1)."""

from unittest.mock import MagicMock
import pytest

from core.dialog_manager import DialogManager, WorkflowLock, WorkflowState


class TestWorkflowStateAndLock:
    """Verifies WorkflowState enum and WorkflowLock state transitions."""

    def test_workflow_state_enum_completeness(self):
        expected_states = {
            "IDLE", "UNDERSTANDING", "WAITING_FOR_SLOT", "PLANNING",
            "EXECUTING", "WAITING_FOR_CONFIRMATION", "VERIFYING",
            "COMPLETED", "SUSPENDED", "CANCELLED", "FAILED", "RECOVERING"
        }
        actual_states = {s.value for s in WorkflowState}
        assert expected_states == actual_states

    def test_workflow_lock_initial_state_and_transition(self):
        lock = WorkflowLock(
            workflow_type="EMAIL_COMPOSE",
            required_slots=["recipient", "subject", "body"],
            filled_slots={"recipient": "Rahul"},
        )
        assert lock.state == WorkflowState.WAITING_FOR_SLOT
        assert len(lock.state_history) == 0

        lock.transition_to(WorkflowState.SUSPENDED)
        assert lock.state == WorkflowState.SUSPENDED
        assert len(lock.state_history) == 1
        assert lock.state_history[0][0] == "SUSPENDED"

        lock.transition_to(WorkflowState.WAITING_FOR_CONFIRMATION)
        assert lock.state == WorkflowState.WAITING_FOR_CONFIRMATION
        assert len(lock.state_history) == 2


class TestDialogManagerMultiWorkflowState:
    """Verifies DialogManager multi-workflow stack, suspension, list, detail, and resume."""

    def test_single_workflow_suspend_and_resume(self):
        dm = DialogManager()
        dm.set_lock(
            workflow_type="EMAIL_COMPOSE",
            required_slots=["recipient", "subject", "body"],
            initial_slots={"recipient": "Amit"},
            prompt_question="Subject kya rakhna hai?",
        )
        assert dm.has_active_lock() is True
        assert dm.has_suspended_lock() is False

        # Suspend workflow
        suspended = dm.suspend_workflow()
        assert suspended is not None
        assert dm.has_active_lock() is False
        assert dm.has_suspended_lock() is True
        assert suspended.state == WorkflowState.SUSPENDED
        assert dm.suspended_lock.workflow_id == suspended.workflow_id

        # Resume workflow
        resumed = dm.resume_suspended_lock()
        assert resumed is not None
        assert resumed.workflow_id == suspended.workflow_id
        assert dm.has_active_lock() is True
        assert dm.has_suspended_lock() is False
        assert resumed.state == WorkflowState.WAITING_FOR_SLOT

    def test_nested_multiple_workflows_lifo_stack(self):
        dm = DialogManager()

        # 1. Start Email
        lock1 = dm.set_lock(
            workflow_type="EMAIL_COMPOSE",
            required_slots=["recipient", "subject", "body"],
            initial_slots={"recipient": "Rahul"},
            prompt_question="Subject kya rakhna hai?",
        )
        assert dm.active_lock == lock1

        # 2. Start Backup (should auto-suspend Email)
        lock2 = dm.set_lock(
            workflow_type="BACKUP_UPLOAD",
            required_slots=["target_directory"],
            prompt_question="Kaunsa folder backup karna hai?",
        )
        assert dm.active_lock == lock2
        assert len(dm._workflow_stack) == 1
        assert dm._workflow_stack[0] == lock1.workflow_id

        # 3. Interruption suspends Backup
        dm.suspend_workflow()
        assert dm.has_active_lock() is False
        assert len(dm._workflow_stack) == 2
        # Top of stack is lock2 (Backup)
        assert dm.suspended_lock.workflow_id == lock2.workflow_id

        # 4. List pending workflows
        pending = dm.list_pending_workflows()
        assert len(pending) == 2
        summary = dm.format_pending_workflows_summary(lang="hi")
        assert "2 kaam pending hain" in summary
        assert "pehla" in summary
        assert "doosra" in summary

        # 5. Check detail of first pending workflow
        detail1 = dm.format_pending_workflow_detail(lock1, lang="hi")
        assert "Rahul ko draft mail" in detail1

        # 6. Resume specific workflow by name ("email")
        resumed_email = dm.resume_workflow(target="email")
        assert resumed_email is not None
        assert resumed_email.workflow_id == lock1.workflow_id
        assert dm.active_lock.workflow_id == lock1.workflow_id

        # Backup should still be in suspended stack
        assert dm.has_suspended_lock() is True
        assert dm.suspended_lock.workflow_id == lock2.workflow_id

    def test_workflow_query_detection(self):
        dm = DialogManager()
        assert dm.is_workflow_query("Mere kaunse kaam pending hain?") is True
        assert dm.is_workflow_query("kya pending hai") is True
        assert dm.is_workflow_query("Pehla kya hai?") is True
        assert dm.is_workflow_query("Ab email continue karo") is True
        assert dm.is_workflow_query("Wahi continue karo") is True
        assert dm.is_workflow_query("Backup chhod do, pehle email continue karo") is True
        assert dm.is_workflow_query("Chrome kholo") is False
        assert dm.is_workflow_query("Weather kaisa hai?") is False

    def test_interpret_turn_n_plus_1_pending_inquiry_and_resume(self):
        dm = DialogManager()
        mock_core = MagicMock()

        # When no pending workflows
        handled, resp = dm.interpret_turn_n_plus_1("Mere kaunse kaam pending hain?", mock_core)
        assert handled is True
        assert "Koi pending kaam nahi hai" in resp

        # Create two suspended workflows
        lock1 = dm.set_lock(
            workflow_type="EMAIL_COMPOSE",
            required_slots=["recipient", "subject", "body"],
            initial_slots={"recipient": "Rahul", "subject": "Project update"},
            prompt_question="Mail mein kya likhna hai?",
        )
        lock2 = dm.set_lock(
            workflow_type="BACKUP_UPLOAD",
            required_slots=["target_path"],
            prompt_question="Backup path batayein?",
        )
        dm.suspend_workflow(lock2)

        # Inquire pending
        handled, resp = dm.interpret_turn_n_plus_1("Mere kaunse kaam pending hain?", mock_core)
        assert handled is True
        assert "2 kaam pending hain" in resp
        assert "Rahul ka email draft" in resp
        assert "backup upload" in resp

        # Inquire detail of first
        handled, resp = dm.interpret_turn_n_plus_1("Pehla kya hai?", mock_core)
        assert handled is True
        assert "Rahul ko draft mail" in resp
        assert "subject set hai" in resp
        assert "body pending hai" in resp

        # Resume email
        handled, resp = dm.interpret_turn_n_plus_1("Ab email continue karo", mock_core)
        assert handled is True
        assert dm.has_active_lock() is True
        assert dm.active_lock.workflow_id == lock1.workflow_id
        assert "Mail mein kya likhna hai?" in resp or "continue" in resp
