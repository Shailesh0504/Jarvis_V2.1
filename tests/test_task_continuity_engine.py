# tests/test_task_continuity_engine.py
"""
Comprehensive tests for the Long-Horizon Task Continuity Engine.
Validates:
1. Invariant compliance (PLAN -> EXECUTE -> VERIFY -> CHECKPOINT -> NEXT -> FINAL VALIDATION -> COMPLETE).
2. Step failure diagnosis and adaptive strategy retry without restarting prior steps.
3. SQLite checkpointing and crash recovery from the latest verified checkpoint.
4. Active Workflow Lock: conversational status queries, urgent interruption suspension/auto-resume, and intentional cancellation.
5. Watchdog timeout and retry circuit breakers preventing infinite loops.
6. Procedural experience learning, retrieval, and environmental applicability validation.
7. Realistic 10+ step workflow recovering from a mid-pipeline failure.
8. End-to-end integration with JarvisCore and working memory synchronization.
"""

import os
import shutil
import tempfile
import time
from typing import Any, Dict, List, Optional
import pytest

from core.task_engine.models import (
    TaskState,
    TaskStep,
    StepExecutionReport,
    TaskStatus,
)
from core.task_engine.persistence import TaskPersistenceManager
from core.task_engine.verifier import TaskVerifier
from core.task_engine.watchdog import TaskWatchdog
from core.task_engine.diagnostics import FailureDiagnoser, FailureDiagnosis
from core.task_engine.experience import ExperienceLearner
from core.task_engine.engine import TaskContinuityEngine
from memory.database import DatabaseManager


class MockPluginManager:
    """Mock plugin manager simulating realistic action dispatch and failure injection."""

    def __init__(self):
        self.call_history: List[Dict[str, Any]] = []
        self.fail_once_actions: set = set()
        self.always_fail_actions: set = set()
        self.registered_plugins = {"fs", "system", "workspace", "builder", "report"}

    def get_plugin(self, name: str):
        return {"name": name} if name in self.registered_plugins else None

    def execute_action(self, plugin_name: str, action_name: str, parameters: Dict[str, Any]):
        call_entry = {"plugin": plugin_name, "action": action_name, "parameters": dict(parameters)}
        self.call_history.append(call_entry)

        action_key = f"{plugin_name}.{action_name}"

        # Simulating permanent failure
        if action_key in self.always_fail_actions:
            return {"success": False, "error": f"Simulated permanent error in {action_key}"}

        # Simulating transient failure that heals on retry
        if action_key in self.fail_once_actions:
            self.fail_once_actions.remove(action_key)
            return {"success": False, "error": f"Simulated transient error in {action_key}"}

        # Built-in mock behaviors
        if plugin_name == "fs":
            if action_name == "create_file":
                path = parameters.get("path")
                content = parameters.get("content", "")
                if path:
                    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                return {"success": True, "data": {"path": path, "bytes_written": len(content)}}

            elif action_name == "create_dir":
                path = parameters.get("path")
                if path:
                    os.makedirs(path, exist_ok=True)
                return {"success": True, "data": {"dir": path}}

        if plugin_name == "builder":
            if action_name == "build_module":
                output_file = parameters.get("output_file")
                if parameters.get("force_refocus") or parameters.get("fallback_csv_format") or parameters.get("clean_cache"):
                    # Success on adapted strategy
                    if output_file:
                        with open(output_file, "w", encoding="utf-8") as f:
                            f.write("BUILD_SUCCESS_VERSION_1")
                    return {"success": True, "data": {"status": "built", "output_file": output_file}}
                # If primary strategy, create file with content
                if output_file:
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write("BUILD_SUCCESS")
                return {"success": True, "data": {"status": "built", "output_file": output_file}}

        return {"success": True, "data": {"echo": parameters, "action": action_name}}


@pytest.fixture
def temp_dir():
    """Provides a fresh isolated temporary directory for file operations and SQLite."""
    td = tempfile.mkdtemp(prefix="jarvis_task_test_")
    yield td
    shutil.rmtree(td, ignore_errors=True)


@pytest.fixture
def persistence_mgr(temp_dir):
    """Provides a TaskPersistenceManager with an isolated SQLite database."""
    db_path = os.path.join(temp_dir, "test_tasks.db")
    db = DatabaseManager(db_path=db_path)
    return TaskPersistenceManager(db_or_path=db)


def test_task_state_serialization():
    """Validates complete serialization and deserialization of TaskState."""
    steps = [
        TaskStep(step_id="s1", name="Step 1", plugin_name="fs", action_name="create_dir", parameters={"path": "dir1"}),
        TaskStep(step_id="s2", name="Step 2", plugin_name="fs", action_name="create_file", parameters={"path": "file1"}),
    ]
    state = TaskState(
        goal="Setup project",
        plan=steps,
        current_step=1,
        completed_steps=[
            StepExecutionReport(step_id="s1", step_name="Step 1", success=True, verified=True, data={"path": "dir1"})
        ],
        remaining_steps=[steps[1]],
        failed_steps=[],
        retry_count=1,
        execution_context={"project_root": "dir1"},
        final_status=TaskStatus.RUNNING,
    )

    d = state.to_dict()
    restored = TaskState.from_dict(d)

    assert restored.task_id == state.task_id
    assert restored.goal == "Setup project"
    assert len(restored.plan) == 2
    assert restored.current_step == 1
    assert len(restored.completed_steps) == 1
    assert restored.completed_steps[0].verified is True
    assert restored.execution_context.get("project_root") == "dir1"
    assert restored.final_status == TaskStatus.RUNNING


def test_persistence_checkpoints(persistence_mgr):
    """Validates saving task state, recording checkpoints, and retrieving incomplete tasks."""
    steps = [
        TaskStep(step_id="step_a", name="Step A"),
        TaskStep(step_id="step_b", name="Step B"),
    ]
    task = TaskState(goal="Test persistence", plan=steps, final_status=TaskStatus.RUNNING)
    persistence_mgr.save_task_state(task)

    # Record checkpoint
    report = StepExecutionReport(step_id="step_a", step_name="Step A", success=True, verified=True, data={"res": 1})
    task.advance_step(report)
    persistence_mgr.checkpoint_step(task, report)

    # Check incomplete task retrieval
    incompletes = persistence_mgr.get_incomplete_tasks()
    assert len(incompletes) == 1
    loaded = incompletes[0]
    assert loaded.task_id == task.task_id
    assert loaded.current_step == 1
    assert len(loaded.completed_steps) == 1
    assert loaded.completed_steps[0].step_id == "step_a"

    # Verify checkpoint history
    cps = persistence_mgr.get_checkpoints_for_task(task.task_id)
    assert len(cps) == 1
    assert cps[0]["step_id"] == "step_a"
    assert cps[0]["verified"] == 1


def test_step_by_step_invariant_execution(temp_dir, persistence_mgr):
    """
    Validates the core invariant:
    PLAN -> EXECUTE STEP -> VERIFY -> CHECKPOINT -> NEXT STEP -> VERIFY -> FINAL VALIDATION -> COMPLETE.
    """
    mock_plugins = MockPluginManager()
    engine = TaskContinuityEngine(persistence_manager=persistence_mgr, plugin_manager=mock_plugins)

    file_1 = os.path.join(temp_dir, "step1.txt")
    file_2 = os.path.join(temp_dir, "step2.txt")

    steps = [
        TaskStep(
            step_id="create_f1",
            name="Create Step 1 File",
            plugin_name="fs",
            action_name="create_file",
            parameters={"path": file_1, "content": "STEP_1_OK"},
            verification_type="file_exists",
            verification_params={"path": file_1, "non_empty": True}
        ),
        TaskStep(
            step_id="create_f2",
            name="Create Step 2 File",
            plugin_name="fs",
            action_name="create_file",
            parameters={"path": file_2, "content": "STEP_2_OK"},
            verification_type="file_content",
            verification_params={"path": file_2, "contains": "STEP_2_OK"}
        ),
        TaskStep(
            step_id="echo_status",
            name="Report Status",
            plugin_name="system",
            action_name="status",
            parameters={"status": "completed_all"},
            verification_type="data_key",
            verification_params={"key": "action"}
        ),
    ]

    success, msg, state = engine.start_workflow(
        goal="Step Invariant Verification Test",
        steps=steps,
        execution_context={"expected_output_file": file_2}
    )

    assert success is True
    assert state.final_status == TaskStatus.COMPLETED
    assert len(state.completed_steps) == 3
    assert state.current_step == 3
    assert os.path.exists(file_1)
    assert os.path.exists(file_2)

    # Checkpoints were persisted for all steps in SQLite
    checkpoints = persistence_mgr.get_checkpoints_for_task(state.task_id)
    assert len(checkpoints) == 3
    for cp in checkpoints:
        assert cp["verified"] == 1


def test_step_failure_diagnosis_and_adaptive_retry(temp_dir, persistence_mgr):
    """
    Validates failure diagnosis, strategy adaptation, and resume from the failed step.
    Step 1 succeeds. Step 2 fails once due to a transient error, gets diagnosed,
    retried, verified, and Step 3 completes without re-executing Step 1.
    """
    mock_plugins = MockPluginManager()
    mock_plugins.fail_once_actions.add("builder.build_module")

    engine = TaskContinuityEngine(persistence_manager=persistence_mgr, plugin_manager=mock_plugins)

    build_out = os.path.join(temp_dir, "build.bin")
    steps = [
        TaskStep(
            step_id="step_prep",
            name="Prepare Workspace",
            plugin_name="fs",
            action_name="create_dir",
            parameters={"path": os.path.join(temp_dir, "work")}
        ),
        TaskStep(
            step_id="step_build",
            name="Build Module",
            plugin_name="builder",
            action_name="build_module",
            parameters={"output_file": build_out},
            verification_type="file_exists",
            verification_params={"path": build_out}
        ),
        TaskStep(
            step_id="step_final",
            name="Verify Completion",
            plugin_name="system",
            action_name="status",
            parameters={"status": "all_done"}
        )
    ]

    success, msg, state = engine.start_workflow(goal="Adaptive Recovery Test", steps=steps)

    assert success is True
    assert state.final_status == TaskStatus.COMPLETED
    assert len(state.completed_steps) == 3
    assert state.step_retry_counts["step_build"] == 1
    assert len(state.failed_steps) == 1
    assert state.failed_steps[0]["step_id"] == "step_build"
    assert os.path.exists(build_out)


def test_watchdog_circuit_breaker_prevents_infinite_loop(temp_dir, persistence_mgr):
    """
    Validates that the watchdog circuit breaker prevents infinite retry loops
    when a step fails persistently beyond max_retries.
    """
    mock_plugins = MockPluginManager()
    mock_plugins.always_fail_actions.add("builder.build_module")

    watchdog = TaskWatchdog(default_timeout=5.0, max_retries_per_step=2)
    engine = TaskContinuityEngine(
        persistence_manager=persistence_mgr,
        plugin_manager=mock_plugins,
        watchdog=watchdog
    )

    steps = [
        TaskStep(step_id="step_ok", name="Ok Step", plugin_name="fs", action_name="create_dir", parameters={"path": temp_dir}),
        TaskStep(step_id="step_broken", name="Broken Step", plugin_name="builder", action_name="build_module", parameters={"out": "foo"}),
    ]

    success, msg, state = engine.start_workflow(goal="Circuit Breaker Test", steps=steps)

    assert success is False
    assert state.final_status == TaskStatus.FAILED
    # Step 1 succeeded, step 2 failed
    assert len(state.completed_steps) == 1
    assert state.current_step == 1
    assert state.step_retry_counts["step_broken"] >= 2
    assert "LIMIT_EXCEEDED" in state.failed_steps[-1].get("diagnosis", "") or "exceeded" in state.failed_steps[-1].get("error", "")


def test_crash_recovery_from_latest_checkpoint(temp_dir, persistence_mgr):
    """
    Simulates an unexpected process crash / restart.
    Steps 1 and 2 are verified and checkpointed. A crash occurs.
    A new engine instance recovers from the database and resumes from Step 3
    without re-executing Steps 1 and 2.
    """
    mock_plugins_1 = MockPluginManager()
    engine_1 = TaskContinuityEngine(persistence_manager=persistence_mgr, plugin_manager=mock_plugins_1)

    f1 = os.path.join(temp_dir, "crash_1.txt")
    f2 = os.path.join(temp_dir, "crash_2.txt")
    f3 = os.path.join(temp_dir, "crash_3.txt")

    steps = [
        TaskStep(step_id="s1", name="File 1", plugin_name="fs", action_name="create_file", parameters={"path": f1, "content": "1"}),
        TaskStep(step_id="s2", name="File 2", plugin_name="fs", action_name="create_file", parameters={"path": f2, "content": "2"}),
        TaskStep(step_id="s3", name="File 3", plugin_name="fs", action_name="create_file", parameters={"path": f3, "content": "3"}),
    ]

    task = TaskState(goal="Crash Simulation Task", plan=steps, final_status=TaskStatus.RUNNING)
    persistence_mgr.save_task_state(task)

    # Step 1 executed & verified
    mock_plugins_1.execute_action("fs", "create_file", {"path": f1, "content": "1"})
    rep1 = StepExecutionReport(step_id="s1", step_name="File 1", success=True, verified=True, data={"path": f1})
    task.advance_step(rep1)
    persistence_mgr.checkpoint_step(task, rep1)

    # Step 2 executed & verified
    mock_plugins_1.execute_action("fs", "create_file", {"path": f2, "content": "2"})
    rep2 = StepExecutionReport(step_id="s2", step_name="File 2", success=True, verified=True, data={"path": f2})
    task.advance_step(rep2)
    persistence_mgr.checkpoint_step(task, rep2)

    # Checkpoint state: step 2 completed, current_step is 2 (0-indexed -> pointing to s3)
    assert task.current_step == 2

    # --- SIMULATE CRASH & RESTART WITH FRESH ENGINE ---
    mock_plugins_2 = MockPluginManager()
    engine_2 = TaskContinuityEngine(persistence_manager=persistence_mgr, plugin_manager=mock_plugins_2)

    recovery_results = engine_2.recover_incomplete_tasks()
    assert len(recovery_results) == 1
    recovered_task, succ, msg = recovery_results[0]

    assert succ is True
    assert recovered_task.final_status == TaskStatus.COMPLETED
    assert len(recovered_task.completed_steps) == 3
    # Ensure fresh engine only executed step 3, never re-dispatched step 1 or 2
    assert len(mock_plugins_2.call_history) == 1
    assert mock_plugins_2.call_history[0]["parameters"]["path"] == f3
    assert os.path.exists(f3)


def test_active_workflow_lock_conversational_queries(temp_dir, persistence_mgr):
    """
    Validates that task-related queries ("what is the status of the task?")
    are answered without disrupting, resetting, or cancelling the active task.
    """
    mock_plugins = MockPluginManager()
    engine = TaskContinuityEngine(persistence_manager=persistence_mgr, plugin_manager=mock_plugins)

    task = TaskState(
        goal="Deploy Production Cluster",
        plan=[
            TaskStep(step_id="s1", name="Verify nodes"),
            TaskStep(step_id="s2", name="Provision storage"),
            TaskStep(step_id="s3", name="Launch containers"),
        ],
        current_step=1,
        completed_steps=[StepExecutionReport(step_id="s1", step_name="Verify nodes", success=True, verified=True)],
        final_status=TaskStatus.RUNNING,
    )
    engine.active_task = task
    persistence_mgr.save_task_state(task)

    # Ask task status in Hindi/Hinglish
    handled, resp = engine.handle_conversational_input("task ka status kya hai?")
    assert handled is True
    assert "Deploy Production Cluster" in resp
    assert "Step 2/3" in resp
    assert task.final_status == TaskStatus.RUNNING

    # Ask which step is running in English
    handled, resp = engine.handle_conversational_input("what step are you currently on?")
    assert handled is True
    assert "Provision storage" in resp
    assert task.final_status == TaskStatus.RUNNING


def test_active_workflow_lock_urgent_interruption_and_autoresume(temp_dir, persistence_mgr):
    """
    Validates that an unrelated urgent command:
    1. Suspends the active task state.
    2. Executes the interruption via interruption_executor.
    3. Automatically resumes the suspended task from the checkpoint to completion.
    """
    mock_plugins = MockPluginManager()
    engine = TaskContinuityEngine(persistence_manager=persistence_mgr, plugin_manager=mock_plugins)

    f_resume = os.path.join(temp_dir, "autoresume.txt")
    steps = [
        TaskStep(step_id="step_a", name="Step A"),
        TaskStep(step_id="step_b", name="Step B", plugin_name="fs", action_name="create_file", parameters={"path": f_resume, "content": "RESUMED_OK"}),
    ]
    task = TaskState(
        goal="Multi-stage Background Pipeline",
        plan=steps,
        current_step=1,
        completed_steps=[StepExecutionReport(step_id="step_a", step_name="Step A", success=True, verified=True)],
        final_status=TaskStatus.RUNNING,
    )
    engine.active_task = task
    persistence_mgr.save_task_state(task)

    interruption_called = []

    def mock_interruption_executor(cmd: str) -> str:
        interruption_called.append(cmd)
        return "It is currently 10:30 PM, Boss."

    # Send unrelated command while task is running
    handled, resp = engine.handle_conversational_input(
        "kya time hua hai?",
        interruption_executor=mock_interruption_executor
    )

    assert handled is True
    assert "It is currently 10:30 PM, Boss." in resp
    assert "Multi-stage Background Pipeline" in resp
    assert len(interruption_called) == 1
    assert interruption_called[0] == "kya time hua hai?"

    # The suspended task must have auto-resumed and completed Step B
    assert os.path.exists(f_resume)
    assert task.final_status == TaskStatus.COMPLETED


def test_active_workflow_lock_intentional_cancellation(temp_dir, persistence_mgr):
    """
    Validates that intentional abort keywords cleanly cancel the workflow.
    """
    mock_plugins = MockPluginManager()
    engine = TaskContinuityEngine(persistence_manager=persistence_mgr, plugin_manager=mock_plugins)

    task = TaskState(
        goal="Batch Data Import",
        plan=[TaskStep(step_id="s1", name="Importing 10GB dataset")],
        final_status=TaskStatus.RUNNING
    )
    engine.active_task = task
    persistence_mgr.save_task_state(task)

    handled, resp = engine.handle_conversational_input("stop this task immediately")
    assert handled is True
    assert "cancel" in resp.lower()
    assert task.final_status == TaskStatus.CANCELLED
    assert engine.has_active_task() is False


def test_procedural_experience_learning(temp_dir, persistence_mgr):
    """
    Validates that successfully completed workflows store procedural experience
    which can be retrieved and validated for future plan formulation.
    """
    learner = ExperienceLearner(persistence_manager=persistence_mgr)

    steps = [
        TaskStep(step_id="s1", name="Create repo", plugin_name="workspace", action_name="init", parameters={"repo": "jarvis"}),
        TaskStep(step_id="s2", name="Setup env", plugin_name="workspace", action_name="configure", parameters={"env": "prod"}),
    ]
    task = TaskState(goal="Setup Jarvis Workspace", plan=steps, final_status=TaskStatus.COMPLETED)
    task.completed_steps = [
        StepExecutionReport(step_id="s1", step_name="Create repo", success=True, verified=True),
        StepExecutionReport(step_id="s2", step_name="Setup env", success=True, verified=True),
    ]

    learner.record_completed_workflow(task)

    # Query for similar goal
    exp = learner.retrieve_applicable_experience("Setup Jarvis Workspace")
    assert exp is not None
    assert exp["success_rate"] >= 1.0
    assert len(exp["procedure"]) == 2
    assert exp["procedure"][0]["step_id"] == "s1"

    # Environmental validation
    valid = learner.validate_environmental_applicability(exp, current_environment={"available_plugins": ["workspace"]})
    assert valid is True

    invalid = learner.validate_environmental_applicability(exp, current_environment={"available_plugins": ["unrelated"]})
    assert invalid is False


def test_long_horizon_10_plus_step_workflow_with_mid_failure_recovery(temp_dir, persistence_mgr):
    """
    Realistic Long-Horizon Workflow (10+ Steps) with Mid-Pipeline Failure & Recovery.
    Pipeline:
      1. create_workspace_dir
      2. initialize_manifest
      3. generate_config
      4. validate_config
      5. create_src_module
      6. build_artifact (FAILS on attempt 1, diagnosed, retried, verified)
      7. run_linter
      8. generate_documentation
      9. package_bundle
      10. finalize_summary_report

    Verifies:
    - Steps 1-5 succeed and are checkpointed.
    - Step 6 fails on attempt 1, diagnoses root cause, adapts strategy, succeeds on attempt 2.
    - Steps 1-5 are PRESERVED and NOT repeated.
    - Steps 7-10 continue seamlessly to final verification.
    """
    mock_plugins = MockPluginManager()
    # Inject fail-once on step 6
    mock_plugins.fail_once_actions.add("builder.build_module")

    engine = TaskContinuityEngine(persistence_manager=persistence_mgr, plugin_manager=mock_plugins)

    ws_dir = os.path.join(temp_dir, "project_alpha")
    manifest = os.path.join(ws_dir, "manifest.json")
    config = os.path.join(ws_dir, "config.yaml")
    src_file = os.path.join(ws_dir, "main.py")
    build_out = os.path.join(ws_dir, "output.bin")
    doc_file = os.path.join(ws_dir, "README.md")
    report_file = os.path.join(ws_dir, "final_report.json")

    steps = [
        TaskStep(step_id="step_1", name="Create Workspace Dir", plugin_name="fs", action_name="create_dir", parameters={"path": ws_dir}, verification_type="file_exists", verification_params={"path": ws_dir}),
        TaskStep(step_id="step_2", name="Init Manifest", plugin_name="fs", action_name="create_file", parameters={"path": manifest, "content": '{"name": "alpha"}'}, verification_type="file_content", verification_params={"path": manifest, "contains": "alpha"}),
        TaskStep(step_id="step_3", name="Generate Config", plugin_name="fs", action_name="create_file", parameters={"path": config, "content": "mode: production\nthreads: 4"}, verification_type="file_content", verification_params={"path": config, "contains": "production"}),
        TaskStep(step_id="step_4", name="Validate Config", plugin_name="system", action_name="validate", parameters={"target": "config"}, verification_type="data_key", verification_params={"key": "action"}),
        TaskStep(step_id="step_5", name="Create Source Module", plugin_name="fs", action_name="create_file", parameters={"path": src_file, "content": "def main(): return 42"}, verification_type="file_exists", verification_params={"path": src_file}),
        # Step 6: Targeted mid-pipeline failure
        TaskStep(step_id="step_6", name="Build Artifact", plugin_name="builder", action_name="build_module", parameters={"output_file": build_out}, verification_type="file_exists", verification_params={"path": build_out}),
        TaskStep(step_id="step_7", name="Run Linter", plugin_name="system", action_name="lint", parameters={"src": src_file}, verification_type="data_key", verification_params={"key": "action"}),
        TaskStep(step_id="step_8", name="Generate Docs", plugin_name="fs", action_name="create_file", parameters={"path": doc_file, "content": "# Alpha Project Documentation"}, verification_type="file_content", verification_params={"path": doc_file, "contains": "Alpha"}),
        TaskStep(step_id="step_9", name="Package Bundle", plugin_name="system", action_name="package", parameters={"archive": "bundle.zip"}),
        TaskStep(step_id="step_10", name="Finalize Summary Report", plugin_name="fs", action_name="create_file", parameters={"path": report_file, "content": '{"status": "SUCCESS", "steps": 10}'}, verification_type="file_exists", verification_params={"path": report_file}),
    ]

    success, msg, state = engine.start_workflow(
        goal="Execute 10-Step Alpha Release Pipeline",
        steps=steps,
        execution_context={"expected_output_file": report_file}
    )

    assert success is True
    assert state.final_status == TaskStatus.COMPLETED
    assert len(state.completed_steps) == 10
    assert state.current_step == 10

    # Verify Step 6 failed once, was diagnosed, and recovered
    assert state.step_retry_counts["step_6"] == 1
    assert len(state.failed_steps) == 1
    assert state.failed_steps[0]["step_id"] == "step_6"

    # Verify all artifacts physically exist on disk
    assert os.path.exists(manifest)
    assert os.path.exists(config)
    assert os.path.exists(src_file)
    assert os.path.exists(build_out)
    assert os.path.exists(doc_file)
    assert os.path.exists(report_file)

    # Verify that all 10 checkpoints exist in SQLite
    checkpoints = persistence_mgr.get_checkpoints_for_task(state.task_id)
    assert len(checkpoints) == 10


def test_jarvis_core_task_continuity_integration(temp_dir):
    """
    End-to-end integration test with JarvisCore:
    Validates that execute_task_workflow wires with working memory,
    updates ActiveTargetContext, and handles conversational interaction.
    """
    from core.app import JarvisCore
    from core.context import ActiveTargetContext
    from memory.memory_manager import MemoryManager

    db_path = os.path.join(temp_dir, "core_jarvis.db")
    mem_mgr = MemoryManager(db_path=db_path)
    db = mem_mgr.db

    core = JarvisCore()
    core.memory_manager = mem_mgr
    core.active_context = ActiveTargetContext()
    core.task_engine = TaskContinuityEngine(
        persistence_manager=TaskPersistenceManager(db_or_path=db),
        plugin_manager=MockPluginManager()
    )
    # Bind working memory
    core.memory_manager.working.bind_task_state(core.task_engine.active_task)

    out_file = os.path.join(temp_dir, "jarvis_task.txt")
    steps = [
        TaskStep(step_id="step_core_1", name="Create Core Output", plugin_name="fs", action_name="create_file", parameters={"path": out_file, "content": "CORE_TASK_OK"}),
    ]

    success, msg, task = core.execute_task_workflow(goal="Core Task Integration Test", steps=steps)

    assert success is True
    assert task.final_status == TaskStatus.COMPLETED
    assert os.path.exists(out_file)
    assert core.task_engine.has_active_task() is False
