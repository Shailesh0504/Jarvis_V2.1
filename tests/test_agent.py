# tests/test_agent.py
"""Tests for Autonomous Agent ReAct Loop, Multi-Step Reasoning, and Goal Resolution."""

import os
import shutil
import pytest
from main import create_jarvis


@pytest.fixture
def agent_jarvis(tmp_path, monkeypatch):
    orig_plugins = os.path.abspath("plugins")
    monkeypatch.chdir(tmp_path)
    # Copy plugins folder into temp directory
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    # Create a test sales spreadsheet in workspace
    sales_file = tmp_path / "sales_august.csv"
    sales_file.write_text(
        "Product,Units,Sales,Region\n"
        "Laptop,10,50000,North\n"
        "Phone,25,75000,South\n"
        "Headphones,40,20000,East\n"
    )

    cfg_content = f"""
system:
  name: "JARVIS_AGENT_TEST"
memory:
  db_path: "{os.path.join(tmp_path, 'agent.db').replace('\\', '/')}"
learning:
  enabled: true
brain:
  llm_provider: "mock"
plugins:
  plugin_dir: "{str(temp_plugins).replace('\\', '/')}"
  auto_load: true
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(cfg_content)

    return create_jarvis(str(cfg_file)), tmp_path


def test_agent_is_complex_goal_detection(agent_jarvis):
    jarvis, _ = agent_jarvis
    reasoner = jarvis.agent.reasoner

    assert reasoner.is_complex_goal("kal jo Excel file banayi thi usko open karo aur sales column ka total nikalo") is True
    assert reasoner.is_complex_goal("find recent excel file and calculate average sales") is True
    assert reasoner.is_complex_goal("what time is it") is False
    assert reasoner.is_complex_goal("status") is False


def test_agent_plan_formulation(agent_jarvis):
    jarvis, _ = agent_jarvis
    reasoner = jarvis.agent.reasoner

    steps = reasoner.formulate_plan("kal jo Excel file banayi thi usko open karo aur sales column ka total nikalo")
    assert len(steps) == 2
    assert steps[0].plugin_name == "files"
    assert steps[0].action_name == "find_recent_files"
    assert steps[1].plugin_name == "excel"
    assert steps[1].action_name == "calculate_column"
    assert steps[1].parameters["column_name"] == "sales"
    assert steps[1].parameters["operation"] == "sum"


def test_agent_autonomous_execution_end_to_end(agent_jarvis):
    jarvis, tmp_path = agent_jarvis

    # User speaks in natural Hinglish with complex goal
    user_goal = "Jarvis, kal jo Excel file banayi thi usko open karo aur sales column ka total nikalo."
    response = jarvis.process_input(user_goal)

    # 50,000 + 75,000 + 20,000 = 145,000
    assert "145,000" in response or "145000" in response
    assert "sales" in response.lower()


def test_agent_average_calculation(agent_jarvis):
    jarvis, tmp_path = agent_jarvis

    user_goal = "find recent spreadsheet and calculate average of sales"
    response = jarvis.process_input(user_goal)

    # Average of 50000, 75000, 20000 = 48,333.33
    assert "48,333" in response or "48333" in response
