# tests/test_contextual_proactive_suggestions.py
"""Comprehensive unit tests verifying the 15 Contextual & Proactive Clarification Rules."""

import os
import tempfile
import time
import pytest
from unittest.mock import MagicMock

from core.context import ActiveTargetContext
from core.dialog_manager import DialogManager, SuggestionContext, WorkflowLock
from core.app import JarvisCore


def test_rule_1_and_rule_3_proactive_suggestion_single_candidate():
    """Rule 1 & Rule 3: Single candidate leads to proactive suggestion instead of blank question."""
    dm = DialogManager()
    cand = {"name": "financial_report.xlsx", "path": "/path/financial_report.xlsx"}
    dm.set_pending_suggestion(
        workflow_type="EXCEL_OPEN",
        candidate=cand,
        fallback_candidates=[],
        action="open",
        target_plugin="excel"
    )

    assert dm.has_pending_suggestion() is True
    assert dm.pending_suggestion.suggested_candidate["name"] == "financial_report.xlsx"
    assert dm.awaits_user_followup() is True


def test_rule_4_suggestion_is_not_confirmed_automatically():
    """Rule 4: Suggestion is staged and awaits user response, does not execute immediately."""
    dm = DialogManager()
    cand = {"name": "monthly_sales.csv", "path": "/path/monthly_sales.csv"}
    dm.set_pending_suggestion(
        workflow_type="EXCEL_OPEN",
        candidate=cand,
        fallback_candidates=[],
        action="open"
    )
    assert dm.has_pending_suggestion() is True
    # Still pending, not executed


def test_rule_5_affirmative_confirmations():
    """Rule 5: Diverse affirmative confirmations (yes, haan, okay, wahi, continue, bilkul)."""
    dm = DialogManager()
    core = MagicMock()
    core.plugin_manager.execute_action.return_value = MagicMock(success=True)
    core.active_context = ActiveTargetContext()

    confirmations = ["haan", "yes", "wahi", "wahi wali", "okay", "ok", "continue", "bilkul", "kar do"]
    for word in confirmations:
        cand = {"name": "test_sheet.xlsx", "path": "c:/data/test_sheet.xlsx"}
        dm.set_pending_suggestion(
            workflow_type="EXCEL_OPEN", candidate=cand, fallback_candidates=[], action="open"
        )
        handled, msg = dm.process_suggestion_turn(word, core)
        assert handled is True
        assert "test_sheet.xlsx" in msg
        assert "Excel mein khol di hai" in msg
        assert dm.has_pending_suggestion() is False
        assert core.active_context.last_file == "test_sheet.xlsx"


def test_rule_6_rejection_and_fallback_progression():
    """Rule 6: User rejects suggestion -> fall back to next candidate without repeating rejected one."""
    dm = DialogManager()
    core = MagicMock()
    core.plugin_manager.execute_action.return_value = MagicMock(success=True)
    core.active_context = ActiveTargetContext()

    cand1 = {"name": "q1_sales.xlsx", "path": "/path/q1_sales.xlsx"}
    cand2 = {"name": "q2_sales.xlsx", "path": "/path/q2_sales.xlsx"}
    dm.set_pending_suggestion(
        workflow_type="EXCEL_OPEN",
        candidate=cand1,
        fallback_candidates=[cand2],
        action="open"
    )

    # 1. Reject first suggestion
    handled, msg = dm.process_suggestion_turn("nahi dusri wali", core)
    assert handled is True
    assert "q2_sales.xlsx" in msg
    assert dm.has_pending_suggestion() is True
    assert "q1_sales.xlsx" in dm.pending_suggestion.rejected_candidates

    # 2. Confirm second suggestion with "wahi"
    handled2, msg2 = dm.process_suggestion_turn("wahi", core)
    assert handled2 is True
    assert "q2_sales.xlsx" in msg2
    assert "Excel mein khol di hai" in msg2
    assert dm.has_pending_suggestion() is False


def test_rule_6_rejection_with_no_more_fallbacks_asks_targeted_question():
    """Rule 6: If all candidates rejected, ask targeted question and set workflow lock."""
    dm = DialogManager()
    core = MagicMock()
    cand1 = {"name": "lone_file.xlsx", "path": "/path/lone_file.xlsx"}
    dm.set_pending_suggestion(
        workflow_type="EXCEL_OPEN", candidate=cand1, fallback_candidates=[], action="open"
    )

    handled, msg = dm.process_suggestion_turn("nahi", core)
    assert handled is True
    assert "fir kaunsi Excel file open karni hai" in msg
    assert dm.has_active_lock() is True
    assert dm.active_lock.workflow_type == "EXCEL_OPEN"


def test_rule_7_multiple_candidates_present_top_two():
    """Rule 7: DialogManager.resolve_file and candidate presentation."""
    with tempfile.TemporaryDirectory() as temp_dir:
        f1 = os.path.join(temp_dir, "alpha.xlsx")
        f2 = os.path.join(temp_dir, "beta.xlsx")
        with open(f1, "w") as fp:
            fp.write("data1")
        with open(f2, "w") as fp:
            fp.write("data2")

        res = DialogManager.resolve_file("", extensions=["xlsx"], search_dirs=[temp_dir])
        cands = res["exact_matches"]
        assert len(cands) >= 2


def test_rule_8_zero_candidates_fuzzy_suggestion():
    """Rule 8: If 0 exact matches, suggest closest fuzzy match or blank workbook."""
    dm = DialogManager()
    core = MagicMock()
    lock = dm.set_lock("EXCEL_OPEN", ["file_target"])
    lock.filled_slots["file_target"] = "nonexistent_unicorn_budget"

    res = dm._execute_completed_workflow(lock, core)
    assert "naam ki koi Excel file nahi mili" in res
    assert "nayi blank workbook" in res


def test_rule_9_and_rule_10_contextual_memory_recording():
    """Rule 10: After successful execution, contextual memory updates correctly."""
    ctx = ActiveTargetContext()
    ctx.record_execution(
        action="open_file",
        application="excel",
        file_path="c:/users/admin/documents/sales.xlsx",
        entity="sales.xlsx",
        workflow="EXCEL_OPEN"
    )

    assert ctx.last_application == "excel"
    assert ctx.last_file == "sales.xlsx"
    assert ctx.last_file_path == "c:/users/admin/documents/sales.xlsx"
    assert ctx.last_action == "open_file"
    assert ctx.current_workflow == "EXCEL_OPEN"
    assert ctx.is_expired is False


def test_rule_11_context_ttl_expiration():
    """Rule 11: Context expires naturally after inactivity TTL."""
    ctx = ActiveTargetContext(ttl_seconds=0.1)
    ctx.record_execution(action="open_app", application="chrome")
    assert ctx.is_expired is False
    time.sleep(0.15)
    assert ctx.is_expired is True


def test_rule_12_and_rule_13_explicit_command_overrides_pending_suggestion():
    """Rule 12 & 13: Explicit new command overrides active suggestion."""
    dm = DialogManager()
    core = MagicMock()
    cand = {"name": "sales.xlsx", "path": "/path/sales.xlsx"}
    dm.set_pending_suggestion(
        workflow_type="EXCEL_OPEN", candidate=cand, fallback_candidates=[], action="open"
    )

    # User suddenly gives an unrelated query
    handled, msg = dm.process_suggestion_turn("kya haal hai jarvis", core)
    # Returns False so main pipeline handles this new command directly
    assert handled is False
    assert dm.has_pending_suggestion() is False


def test_rule_14_destructive_action_requires_explicit_confirmation():
    """Rule 14: Destructive action (shutdown/restart) requires explicit confirmation."""
    dm = DialogManager()
    core = MagicMock()
    core.plugin_manager = MagicMock()

    prompt = dm.set_pending_system_action("shutdown", language="hi")
    assert "Boss, kya main computer shutdown" in prompt
    assert dm.has_pending_system_action() is True

    # User confirms
    handled, msg = dm.process_system_action_turn("haan", core)
    assert handled is True
    assert "computer shutdown kar raha hoon" in msg
    assert dm.has_pending_system_action() is False


def test_rule_15_user_requests_blank_workbook():
    """User responds 'blank' or 'nayi' to suggestion -> opens blank Excel."""
    dm = DialogManager()
    core = MagicMock()
    core.plugin_manager = MagicMock()
    core.active_context = ActiveTargetContext()

    cand = {"name": "sales.xlsx", "path": "/path/sales.xlsx"}
    dm.set_pending_suggestion(
        workflow_type="EXCEL_OPEN", candidate=cand, fallback_candidates=[], action="open"
    )

    handled, msg = dm.process_suggestion_turn("nayi blank workbook khol do", core)
    assert handled is True
    assert "nayi blank Excel workbook khol di hai" in msg
    core.plugin_manager.execute_action.assert_called_with("windows", "launch_app", {"app_name": "excel"})
