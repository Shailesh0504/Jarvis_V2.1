# tests/test_cognitive_memory.py
"""Comprehensive tests for the 5-Tier Cognitive Memory Architecture & 13 Normalized Tables."""

import os
import pytest
from memory.database import DatabaseManager
from memory.memory_manager import MemoryManager


@pytest.fixture
def mem_engine(tmp_path):
    db_file = os.path.join(tmp_path, "cognitive_test.db").replace("\\", "/")
    return MemoryManager(db_path=db_file)


def test_13_tables_created(mem_engine):
    """Verifies that all 13 relational tables exist in SQLite."""
    sql = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    rows = mem_engine.db.execute_query(sql)
    table_names = [r["name"] for r in rows]

    expected_tables = [
        "conversations",
        "corrections",
        "entities",
        "feedback",
        "learned_patterns",
        "memories",
        "plugin_usage",
        "plugins",
        "preferences",
        "suggestions",
        "tasks",
        "users",
        "workflows"
    ]
    for exp in expected_tables:
        assert exp in table_names, f"Expected table '{exp}' to exist in SQLite schema."


def test_short_term_memory_tier(mem_engine):
    """Short-Term Memory: Active conversation sliding window."""
    stm = mem_engine.short_term

    stm.record_turn(
        session_id="sess_101",
        user_input="Hi Jarvis",
        assistant_response="Hello Boss",
        intent="greeting"
    )
    history = stm.get_conversation_history(limit=5)
    assert len(history) == 2
    assert history[0]["content"] == "Hi Jarvis"
    assert history[1]["content"] == "Hello Boss"


def test_working_memory_tier(mem_engine):
    """Working Memory: Current in-flight task and variable scoping."""
    wm = mem_engine.working

    task_id = wm.start_task(
        task_title="Excel Sales Audit",
        user_goal="Calculate total sales in monthly report",
        total_steps=2
    )
    assert task_id is not None
    assert wm.active_task_id == task_id

    # Intermediate variable caching
    wm.set_variable("target_file", "data/sales.xlsx")
    assert wm.get_variable("target_file") == "data/sales.xlsx"

    wm.update_task_progress(task_id, current_step=1, step_data={"sales_sum": 150000})
    assert wm.get_variable("sales_sum") == 150000

    wm.complete_task(task_id)
    assert wm.active_task_id is None

    recent = wm.get_recent_tasks(limit=1)
    assert len(recent) == 1
    assert recent[0]["status"] == "COMPLETED"


def test_long_term_memory_tier(mem_engine):
    """Long-Term Memory: Facts and preferences."""
    ltm = mem_engine.long_term

    # Store fact
    ltm.store_fact(key="car_model", value="Tesla Model Y", category="personal", tags="vehicle,electric")
    fact = ltm.get_fact("car_model")
    assert fact is not None
    assert fact["value"] == "Tesla Model Y"

    # Search facts
    results = ltm.search_facts("Tesla")
    assert len(results) == 1

    # Preferences
    ltm.set_preference("theme", "dark")
    assert ltm.get_preference("theme") == "dark"


def test_episodic_memory_tier(mem_engine):
    """Episodic Memory: Timeline of past events and plugin usage."""
    ep = mem_engine.episodic

    ep.record(
        user_input="Open YouTube",
        response="Opening YouTube in browser.",
        intent="youtube_search",
        execution_results=[{"plugin": "youtube", "action": "search", "success": True}]
    )

    timeline = ep.get_recent(limit=5)
    assert len(timeline) >= 1

    # Plugin usage check
    sql = "SELECT * FROM plugin_usage WHERE plugin_name = 'youtube'"
    usage = mem_engine.db.execute_query(sql)
    assert len(usage) == 1
    assert usage[0]["action_name"] == "search"
    assert usage[0]["success"] == 1


def test_procedural_memory_tier(mem_engine):
    """Procedural Memory: Composite workflows and custom entities."""
    proc = mem_engine.procedural

    # Register workflow
    steps = [
        {"plugin": "system", "action": "lock", "description": "Lock workstation"}
    ]
    proc.register_workflow(
        workflow_name="lockdown",
        trigger_phrases=["system lock", "lock pc"],
        steps=steps,
        description="Immediate workstation lockdown"
    )

    wf = proc.get_workflow("lockdown")
    assert wf is not None
    assert "lock pc" in wf["triggers"]
    assert len(wf["steps"]) == 1

    # Learn custom domain entity
    proc.learn_entity("project_dir", "c:/workspace/jarvis", entity_type="path")
    assert proc.resolve_entity("project_dir") == "c:/workspace/jarvis"
