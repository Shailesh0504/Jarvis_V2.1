# tests/test_proactive_workflow_synthesis.py
"""Unit tests for Proactive Autonomous Workflow Discovery & Synthesis ("Jarvis Khud Suggest Kare")."""

import os
import shutil
import pytest
from learning.sequence_miner import SequenceMiner
from main import create_jarvis


def test_sequence_miner_detects_repeated_chain():
    miner = SequenceMiner(min_chain_length=3, min_frequency=2)

    # 1. First execution of chain
    miner.record_step("windows", "launch_app", {"app_name": "excel"}, "Launch Excel")
    miner.record_step("excel", "read_sheet", {"path": "Sales.xlsx"}, "Open Sales.xlsx")
    miner.record_step("excel", "clean_sheet", {"operation": "autofit"}, "Clean data")
    miner.record_step("excel", "create_chart", {"chart_type": "bar"}, "Create chart")
    miner.record_step("excel", "clean_sheet", {"operation": "save"}, "Save workbook")

    # Only 1 occurrence, no proposal yet
    assert miner.detect_proposal() is None

    # 2. Second execution of identical chain
    miner.record_step("windows", "launch_app", {"app_name": "excel"}, "Launch Excel")
    miner.record_step("excel", "read_sheet", {"path": "Sales.xlsx"}, "Open Sales.xlsx")
    miner.record_step("excel", "clean_sheet", {"operation": "autofit"}, "Clean data")
    miner.record_step("excel", "create_chart", {"chart_type": "bar"}, "Create chart")
    miner.record_step("excel", "clean_sheet", {"operation": "save"}, "Save workbook")

    # Repeated chain (frequency 2) detected!
    proposal = miner.detect_proposal()
    assert proposal is not None
    assert proposal.display_title == "Prepare Sales Report"
    assert "sales report prepare karo" in proposal.trigger_phrases
    assert len(proposal.steps) >= 3


def test_end_to_end_proactive_workflow_synthesis_and_execution(tmp_path):
    """
    End-to-End Test:
    1. User executes repeated action chain twice.
    2. Jarvis proactively proposes automation: 'Kya main ise Prepare Sales Report naam se automate kar du?'
    3. User confirms with 'Yes'.
    4. Next time, User asks 'Jarvis, sales report prepare karo' -> Jarvis executes all steps!
    """
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = os.path.join(tmp_path, "proactive_test.db").replace("\\", "/")
    cfg_content = f"""
system:
  name: "JARVIS_PROACTIVE_TEST"
memory:
  db_path: "{db_path}"
brain:
  llm_provider: "mock"
plugins:
  plugin_dir: "{str(temp_plugins).replace('\\', '/')}"
  auto_load: true
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(cfg_content)

    jarvis = create_jarvis(str(cfg_file))

    # Feed repeated chain into sequence miner twice
    for _ in range(2):
        jarvis.learning_manager.record_action_step("windows", "launch_app", {"app_name": "excel"}, "Launch Excel")
        jarvis.learning_manager.record_action_step("excel", "read_sheet", {"path": "Sales.xlsx"}, "Open Sales.xlsx")
        jarvis.learning_manager.record_action_step("excel", "clean_sheet", {"operation": "autofit"}, "Clean data")
        jarvis.learning_manager.record_action_step("excel", "create_chart", {"chart_type": "bar"}, "Create chart")
        jarvis.learning_manager.record_action_step("excel", "clean_sheet", {"operation": "save"}, "Save workbook")

    # Run any query to trigger proposal check
    resp_with_proposal = jarvis.process_input("status")
    assert "Prepare Sales Report" in resp_with_proposal
    assert jarvis.dialog_manager.has_pending_proposal() is True

    # User confirms proposal with "Yes"
    confirm_resp = jarvis.process_input("Yes")
    assert "Prepare Sales Report" in confirm_resp
    assert "automate kar diya hai" in confirm_resp
    assert jarvis.dialog_manager.has_pending_proposal() is False

    # Next time: Execute newly learned composite workflow!
    exec_resp = jarvis.process_input("Jarvis, sales report prepare karo")
    assert "prepare_sales_report" in exec_resp or "executed successfully" in exec_resp
