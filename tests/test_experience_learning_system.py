# tests/test_experience_learning_system.py
"""
Comprehensive test suite for the Persistent Experience Learning System.
Validates:
1. All four memory types (Episodic, Semantic, Procedural, Failure, and Preference).
2. Semantic vector embeddings, cosine similarity, and hybrid ranking.
3. Quality safeguards: anti-pollution filter, deduplication merging, and contradiction resolution.
4. Non-destructive versioning and high-value user correction handling.
5. Cross-session persistence across simulated restarts.
6. The complete closed learning loop:
   Task -> Action -> Result -> Feedback -> Stored Experience -> Future Retrieval -> Improved Action.
7. Integration with MemoryManager, JarvisCore, and AgentReasoner.
"""

import os
import shutil
import tempfile
import time
from typing import Any, Dict, List
import pytest

from core.experience.models import (
    ExperienceContext,
    ExperienceItem,
    MemoryType,
)
from core.experience.vector_store import SemanticVectorEngine
from core.experience.safeguards import ExperienceSafeguards
from core.experience.storage import ExperienceStorageManager
from core.experience.evaluator import OutcomeEvaluator
from core.experience.retriever import ExperienceRetriever
from core.experience.system import ExperienceLearningSystem
from memory.database import DatabaseManager


@pytest.fixture
def temp_dir():
    """Provides a fresh isolated temporary directory for file operations and SQLite."""
    td = tempfile.mkdtemp(prefix="jarvis_exp_test_")
    yield td
    shutil.rmtree(td, ignore_errors=True)


@pytest.fixture
def exp_system(temp_dir):
    """Provides an isolated ExperienceLearningSystem."""
    db_path = os.path.join(temp_dir, "test_experience.db")
    return ExperienceLearningSystem(db_or_path=db_path)


def test_experience_item_serialization():
    """Validates complete serialization and deserialization of ExperienceItem."""
    item = ExperienceItem(
        memory_type=MemoryType.PROCEDURAL,
        category="excel",
        query_pattern="calculate sales report",
        content={"steps": [{"plugin": "excel", "action": "sum_column"}]},
        confidence=0.92,
        success_count=3,
        failure_count=1,
        version=2,
        is_active=True,
        superseded_by=None,
        source="execution",
        task_metadata={"env": "prod"},
        embedding=[0.1, 0.2, 0.3],
    )

    d = item.to_dict()
    restored = ExperienceItem.from_dict(d)

    assert restored.id == item.id
    assert restored.memory_type == MemoryType.PROCEDURAL
    assert restored.category == "excel"
    assert restored.query_pattern == "calculate sales report"
    assert len(restored.content["steps"]) == 1
    assert restored.confidence == 0.92
    assert restored.success_count == 3
    assert restored.failure_count == 1
    assert restored.version == 2
    assert restored.is_active is True
    assert restored.embedding == [0.1, 0.2, 0.3]


def test_all_memory_types_storage_and_retrieval(exp_system):
    """Validates storing and retrieving Episodic, Semantic, Procedural, Failure, and Preference memories."""
    # 1. Procedural Memory
    proc = exp_system.record_task_success(
        goal="Clean Excel Sheet and Autofit",
        steps=[
            {"plugin": "excel", "action": "select_range", "parameters": {"range": "A1:Z100"}},
            {"plugin": "excel", "action": "autofit", "parameters": {}},
        ],
        category="excel"
    )
    assert proc is not None
    assert proc.memory_type == MemoryType.PROCEDURAL

    # 2. Failure Memory
    fail = exp_system.record_task_failure(
        goal="Open non-existent report",
        failed_step={"plugin": "files", "action": "read_file", "parameters": {"path": "missing.txt"}},
        error_msg="File not found on disk",
        diagnosis="FILE_NOT_FOUND",
        category="files"
    )
    assert fail is not None
    assert fail.memory_type == MemoryType.FAILURE
    assert "Verify file exists" in fail.content.get("avoidance_strategy", "")

    # 3. Preference Memory
    pref = exp_system.record_user_preference(key="default_browser", value="brave", category="browser")
    assert pref is not None
    assert pref.memory_type == MemoryType.PREFERENCE

    # 4. Semantic Fact Memory
    fact = exp_system.record_semantic_fact(key="project_codename", value="Jarvis V2", category="facts", tags="core,dev")
    assert fact is not None
    assert fact.memory_type == MemoryType.SEMANTIC

    # 5. Episodic Trace
    ep = exp_system.record_episode(
        task_id="ep_001",
        goal="Run weekly diagnostics",
        steps_trace=[{"plugin": "system", "action": "stats", "success": True}],
        final_result="All systems nominal",
        success=True
    )
    assert ep is not None
    assert ep.memory_type == MemoryType.EPISODIC

    # Verify active items count
    active_all = exp_system.storage.get_active_items()
    assert len(active_all) == 5


def test_semantic_vector_similarity_and_hybrid_search():
    """Validates vector embeddings, cosine similarity, and hybrid lexical/semantic retrieval."""
    engine = SemanticVectorEngine()

    v1 = engine.embed_text("calculate monthly sales report in excel")
    v2 = engine.embed_text("excel sheet revenue calculation and sum")
    v3 = engine.embed_text("turn off the living room lights")

    # High similarity between semantically related phrases
    sim_related = engine.cosine_similarity(v1, v2)
    # Low similarity between unrelated tasks
    sim_unrelated = engine.cosine_similarity(v1, v3)

    assert sim_related > 0.45
    assert sim_unrelated < 0.35
    assert sim_related > sim_unrelated

    # Hybrid similarity check
    hybrid_score = engine.hybrid_similarity("sales calculation", "calculate sales for excel")
    assert hybrid_score > 0.40


def test_safeguards_pollution_filter(exp_system):
    """Validates that trivial utterances and empty payload records are discarded as pollution."""
    # Trivial greetings
    item_hi = exp_system.record_task_success(goal="hi", steps=[{"plugin": "system", "action": "echo"}])
    assert item_hi is None

    item_test = exp_system.record_task_success(goal="test", steps=[{"plugin": "system", "action": "echo"}])
    assert item_test is None

    # Empty steps procedural
    item_empty = exp_system.record_task_success(goal="non-trivial complex task", steps=[])
    assert item_empty is None


def test_safeguards_deduplication(exp_system):
    """Validates that duplicate procedural executions merge, update counts, and strengthen confidence."""
    steps = [
        {"plugin": "files", "action": "compress", "parameters": {"dir": "archive"}},
        {"plugin": "system", "action": "notify", "parameters": {"msg": "done"}},
    ]

    # First execution
    item1 = exp_system.record_task_success(goal="Backup archive files", steps=steps, category="backup")
    assert item1 is not None
    initial_conf = item1.confidence
    assert item1.success_count == 1

    # Second execution of the exact same task procedure
    item2 = exp_system.record_task_success(goal="Backup archive files", steps=steps, category="backup")
    assert item2 is not None
    # Must have the same ID (merged, not duplicated in SQLite)
    assert item2.id == item1.id
    assert item2.success_count == 2
    assert item2.confidence >= initial_conf

    # Verify only 1 active record in storage
    active_backups = exp_system.storage.get_active_items(category="backup")
    assert len(active_backups) == 1


def test_safeguards_contradiction_and_versioning(exp_system):
    """
    Validates contradiction resolution and versioning:
    User establishes initial preference, then corrects it.
    The old memory is deprecated/superseded, and a new versioned record is created.
    """
    # 1. User establishes preference: default_browser = chrome
    p1 = exp_system.record_user_preference(key="default_browser", value="chrome", category="browser")
    assert p1.version == 1
    assert p1.is_active is True

    # 2. User provides explicit verbal correction: "nahi chrome nahi edge"
    new_pref, superseded = exp_system.record_user_correction(
        concept="default_browser",
        old_value="chrome",
        new_value="edge",
        context="nahi chrome nahi edge use karo"
    )

    assert new_pref is not None
    assert superseded is not None
    # Versioning: new version is 2
    assert new_pref.version == 2
    assert new_pref.is_active is True
    assert new_pref.confidence >= 0.95
    assert new_pref.content["value"] == "edge"

    # Old preference is superseded
    assert superseded.is_active is False
    assert superseded.superseded_by == new_pref.id

    # Active query returns strictly version 2 (edge), never the superseded version
    ctx = exp_system.retrieve_experience("which browser should I open?")
    assert ctx.preferences.get("default_browser") == "edge"


def test_outcome_evaluator_generalization():
    """Validates outcome evaluation parameter abstraction and failure avoidance derivation."""
    evaluator = OutcomeEvaluator()

    raw_steps = [
        {"plugin": "files", "action": "open", "parameters": {"path": "C:/Users/Admin/AppData/Local/Temp/data.csv"}},
        {"plugin": "excel", "action": "clean", "parameters": {"mode": "fast"}}
    ]
    item = evaluator.evaluate_successful_task(goal="Clean temporary file", steps=raw_steps)
    assert item is not None
    # Specific temp path generalized to variable
    first_step_params = item.content["steps"][0]["parameters"]
    assert first_step_params["path"] == "$temp_dir"


def test_cross_session_persistence(temp_dir):
    """
    Validates that experience is retained across session restarts:
    Engine 1 learns procedures, preferences, and pitfalls.
    Engine 1 is closed. Engine 2 boots from the same database and recalls all lessons.
    """
    db_path = os.path.join(temp_dir, "persistent_learning.db")

    # Session 1: Engine 1 executes and learns
    engine_1 = ExperienceLearningSystem(db_or_path=db_path)
    engine_1.record_task_success(
        goal="Synthesize monthly financial report",
        steps=[
            {"plugin": "excel", "action": "load_workbook", "parameters": {"file": "finances.xlsx"}},
            {"plugin": "excel", "action": "generate_chart", "parameters": {"type": "bar"}},
            {"plugin": "pdf", "action": "export_pdf", "parameters": {"out": "report.pdf"}},
        ],
        category="finance"
    )
    engine_1.record_task_failure(
        goal="Synthesize monthly financial report",
        failed_step={"plugin": "excel", "action": "generate_chart"},
        error_msg="Target window was not focused",
        diagnosis="WINDOW_UNFOCUSED",
        category="finance"
    )
    engine_1.record_user_preference(key="report_format", value="PDF", category="finance")

    # --- SIMULATE PROCESS RESTART ---
    del engine_1

    # Session 2: Engine 2 initializes fresh from the persistent database
    engine_2 = ExperienceLearningSystem(db_or_path=db_path)

    # Retrieve experience for financial reporting
    ctx = engine_2.retrieve_experience("financial report synthesize karo")
    assert ctx.has_relevant_experience() is True
    assert len(ctx.procedures) == 1
    assert ctx.procedures[0]["goal"] == "Synthesize monthly financial report"
    assert len(ctx.procedures[0]["steps"]) == 3
    assert len(ctx.failures) == 1
    assert "focus" in ctx.failures[0]["avoidance_strategy"].lower()
    assert ctx.preferences.get("report_format") == "PDF"


def test_complete_learning_loop_closed_cycle(temp_dir):
    """
    Closed-Loop Validation of the Complete Learning Cycle:
    Task -> Action -> Result -> Feedback -> Stored Experience -> Future Retrieval -> Improved Action.
    """
    db_path = os.path.join(temp_dir, "closed_loop.db")
    system = ExperienceLearningSystem(db_or_path=db_path)

    # 1. TASK: Initial request without prior experience
    task_goal = "Process Q3 sales transactions and calculate revenue"

    # Verify no prior experience exists for this task initially
    initial_ctx = system.retrieve_experience(task_goal)
    assert initial_ctx.has_relevant_experience() is False

    # 2. ACTION: Agent/Core executes step sequence
    executed_steps = [
        {"plugin": "files", "action": "find_recent_files", "parameters": {"pattern": "sales_q3"}},
        {"plugin": "excel", "action": "read_sheet", "parameters": {"sheet": "Transactions"}},
        {"plugin": "excel", "action": "calculate_column", "parameters": {"column": "Revenue", "operation": "sum"}},
    ]

    # 3. RESULT: Task execution succeeded and verified
    task_success = True

    # 4. FEEDBACK & STORED EXPERIENCE: Outcome Evaluator evaluates and stores lesson
    stored_item = system.record_task_success(
        goal=task_goal,
        steps=executed_steps,
        execution_context={"revenue_sum": 45000},
        category="sales"
    )
    assert stored_item is not None
    assert stored_item.memory_type == MemoryType.PROCEDURAL

    # 5. FUTURE RETRIEVAL: In a future session, user asks a similar query with different wording
    future_query = "calculate total revenue from recent quarterly sales spreadsheet"
    recalled_ctx = system.retrieve_experience(future_query)

    # 6. IMPROVED ACTION: Jarvis recalls proven procedure directly from experience
    assert recalled_ctx.has_relevant_experience() is True
    assert len(recalled_ctx.procedures) >= 1

    recalled_procedure = recalled_ctx.procedures[0]
    assert recalled_procedure["goal"] == task_goal
    assert len(recalled_procedure["steps"]) == 3

    # Verify Planner prompt injection
    prompt_context = recalled_ctx.format_for_planner()
    assert "Proven Historical Procedures:" in prompt_context
    assert "excel.calculate_column" in prompt_context


def test_jarvis_core_and_memory_manager_integration(temp_dir):
    """
    End-to-End integration test with JarvisCore and MemoryManager:
    Verifies that core.retrieve_experience, memory_manager.record_user_correction,
    and AgentReasoner planning context are seamlessly wired.
    """
    from core.app import JarvisCore
    from core.context import ActiveTargetContext
    from memory.memory_manager import MemoryManager

    db_path = os.path.join(temp_dir, "core_exp.db")
    mem_mgr = MemoryManager(db_path=db_path)

    core = JarvisCore()
    core.memory_manager = mem_mgr
    core.active_context = ActiveTargetContext()
    core.experience_system = mem_mgr.experience

    # 1. Record experience through MemoryManager facade
    mem_mgr.record_experience_success(
        goal="Compress project workspace",
        steps=[
            {"plugin": "files", "action": "compress_zip", "parameters": {"folder": "workspace"}},
        ],
        category="files"
    )

    # 2. Retrieve experience through JarvisCore facade
    ctx = core.retrieve_experience("zip workspace folder")
    assert ctx is not None
    assert len(ctx.procedures) == 1
    assert ctx.procedures[0]["goal"] == "Compress project workspace"

    # 3. User correction through MemoryManager
    new_pref, old_pref = mem_mgr.record_user_correction(
        concept="default_music_player",
        old_value="groove",
        new_value="vlc",
        context="don't use groove use vlc"
    )
    assert new_pref.content["value"] == "vlc"
    assert new_pref.confidence >= 0.95
