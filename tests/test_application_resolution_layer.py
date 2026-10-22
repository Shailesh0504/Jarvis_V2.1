# tests/test_application_resolution_layer.py
"""
Comprehensive automated test suite for Application Resolution, Detection,
Intent Prioritization, and Execution Verification Layer.
"""

import os
import shutil
import pytest
from unittest.mock import patch, MagicMock

from core.apps import ApplicationRegistry, InstalledAppDetector, get_application_registry, get_installed_app_detector
from core.apps.detector import InstalledAppInfo
from core.semantic import SemanticPipelineOrchestrator
from core.execution.strategies import ExecutionStrategyEngine
from core.execution.models import ExecutionState, VerificationResult, ExecutionResult
from main import create_jarvis


# =====================================================================
# 1. Registry & Query Parsing Tests
# =====================================================================

def test_registry_app_definitions():
    """Verify all required Microsoft Office & system apps are registered."""
    registry = ApplicationRegistry()
    for app_id in ["word", "excel", "powerpoint", "access", "publisher", "chrome", "notepad", "calc"]:
        app_def = registry.get_app(app_id)
        assert app_def is not None, f"App '{app_id}' must be registered in ApplicationRegistry"
        assert len(app_def.aliases) > 0
        assert len(app_def.executables) > 0


def test_registry_parse_queries():
    """Verify query parsing correctly identifies app, intent, and flags."""
    registry = ApplicationRegistry()
    test_cases = [
        ("open word", "word", False, False, False),
        ("open microsoft word", "word", False, False, False),
        ("open excel", "excel", False, False, False),
        ("open ms excel", "excel", False, False, False),
        ("open new excel", "excel", True, False, False),
        ("ek nayi blank excel sheet kholo", "excel", True, False, False),
        ("open ppt", "powerpoint", False, False, False),
        ("open power point", "powerpoint", False, False, False),
        ("open microsoft power point", "powerpoint", False, False, False),
        ("open powerpoint", "powerpoint", False, False, False),
        ("open access", "access", False, False, False),
        ("open microsoft access", "access", False, False, False),
        ("open publisher", "publisher", False, False, False),
        ("open microsoft publisher", "publisher", False, False, False),
        ("open excel website", "excel", False, True, False),
        ("open powerpoint website", "powerpoint", False, True, False),
        ("open startup folder", None, False, False, True),
        ("open desktop folder", None, False, False, True),
    ]

    for query, expected_app, expected_new, expected_web, expected_folder in test_cases:
        matched_app, meta = registry.parse_query(query)
        if expected_app is not None:
            assert matched_app is not None, f"Query '{query}' expected app '{expected_app}', got None"
            assert matched_app.app_id == expected_app, f"Query '{query}' expected app '{expected_app}', got '{matched_app.app_id}'"
        assert meta["is_new"] == expected_new, f"Query '{query}' expected is_new={expected_new}"
        assert meta["is_website"] == expected_web, f"Query '{query}' expected is_website={expected_web}"
        assert meta["is_folder"] == expected_folder, f"Query '{query}' expected is_folder={expected_folder}"


# =====================================================================
# 2. Installed Application Detection Tests
# =====================================================================

def test_detector_finds_office_apps():
    """Verify InstalledAppDetector correctly inspects system for Office applications."""
    detector = InstalledAppDetector()
    
    # On this Windows machine, Office apps are installed in Office16 Root
    for app_id in ["word", "excel", "powerpoint", "access", "publisher"]:
        info = detector.detect(app_id)
        assert info is not None and info.is_installed is True, f"Expected {app_id} to be detected on system"
        assert info.executable_path is not None and os.path.exists(info.executable_path), f"Resolved path for {app_id} must exist"


def test_detector_handles_uninstalled_apps():
    """Verify detector safely returns uninstalled status for non-existent apps."""
    detector = InstalledAppDetector()
    assert detector.is_installed("completely_fake_nonexistent_app_999") is False
    assert detector.detect("completely_fake_nonexistent_app_999") is None


# =====================================================================
# 3. Semantic Pipeline Intent Prioritization Tests
# =====================================================================

def test_nlu_intent_priorities():
    """
    Verify strict priority hierarchy:
    1. Local app launch (Word, Excel, PowerPoint, Access, Publisher)
    2. File / Folder operations
    3. Website only when explicitly requested
    """
    cases = [
        # Office apps MUST be OPEN_APP
        ("open word", "OPEN_APP", "launch_app", "word"),
        ("open microsoft word", "OPEN_APP", "launch_app", "word"),
        ("open excel", "OPEN_APP", "launch_app", "excel"),
        ("open ms excel", "OPEN_APP", "launch_app", "excel"),
        ("open new excel", "OPEN_APP", "launch_app", "excel"),
        ("open ppt", "OPEN_APP", "launch_app", "powerpoint"),
        ("open power point", "OPEN_APP", "launch_app", "powerpoint"),
        ("open microsoft power point", "OPEN_APP", "launch_app", "powerpoint"),
        ("open microsoft access", "OPEN_APP", "launch_app", "access"),
        ("open microsoft publisher", "OPEN_APP", "launch_app", "publisher"),

        # Folder operations MUST be FOLDER_OPEN
        ("open startup folder", "FOLDER_OPEN", "open_folder", None),
        ("open desktop folder", "FOLDER_OPEN", "open_folder", None),

        # Explicit website requests MUST be OPEN_WEBSITE
        ("open excel website", "OPEN_WEBSITE", "open_website", None),
        ("open powerpoint website", "OPEN_WEBSITE", "open_website", None),
        ("open microsoft.com", "OPEN_WEBSITE", "open_website", None),

        # File requests with extensions MUST be OPEN_FILE
        ("open myfile.xlsx", "OPEN_FILE", "open_file", None),
        ("open report.docx", "OPEN_FILE", "open_file", None),
    ]

    for query, expected_intent, expected_action, expected_app in cases:
        action = SemanticPipelineOrchestrator.parse(query)
        assert action is not None, f"Query '{query}' produced None SemanticAction"
        assert action.intent == expected_intent, f"Query '{query}' expected intent {expected_intent}, got {action.intent}"
        assert action.action == expected_action, f"Query '{query}' expected action {expected_action}, got {action.action}"
        if expected_app:
            app_name = action.parameters.get("app_name")
            assert app_name == expected_app, f"Query '{query}' expected app_name {expected_app}, got {app_name}"


# =====================================================================
# 4. Verified Execution & Fallback Guards Tests
# =====================================================================

def test_uninstalled_app_never_opens_website(monkeypatch):
    """
    Crucial Requirement: If requested app is not installed,
    Jarvis MUST NOT silently open a website or declare false success.
    """
    strategies = ExecutionStrategyEngine()

    # Mock detector to report app as not installed
    monkeypatch.setattr(
        strategies.app_detector,
        "detect",
        lambda app: InstalledAppInfo(app_id=str(app), display_name=str(app), is_installed=False)
    )

    # Attempt launch
    result = strategies.launch_application_verified("nonexistent_app")

    assert result.success is False
    assert result.status == ExecutionState.FAILED
    assert result.reason == "not_installed"
    assert result.executed_action == "detect_installation"


def test_verified_launch_success_when_process_found(monkeypatch):
    """Verify launch succeeds when process verification confirms application running."""
    strategies = ExecutionStrategyEngine()

    # Mock detector
    monkeypatch.setattr(
        strategies.app_detector,
        "detect",
        lambda app: InstalledAppInfo(app_id="word", display_name="Microsoft Word", is_installed=True, executable_path="C:/dummy/winword.exe")
    )
    # Mock dispatch strategy execution
    monkeypatch.setattr(strategies, "_dispatch_app_strategy", lambda **kwargs: (True, None))
    # Mock verifier to confirm app is running
    monkeypatch.setattr(
        strategies.verifier,
        "verify_application_running",
        lambda app, should_run=True: VerificationResult(
            verified=True,
            state=ExecutionState.SUCCESS,
            check_type="app_running",
            expected=True,
            actual=True
        )
    )

    result = strategies.launch_application_verified("word")
    assert result.success is True
    assert result.status == ExecutionState.SUCCESS
    assert result.verification_result.verified is True


def test_verified_launch_fails_when_process_not_found(monkeypatch):
    """
    Crucial Requirement: An execution returning without exception
    MUST NOT automatically mean success if system state verification fails.
    """
    strategies = ExecutionStrategyEngine()

    # Mock detector
    monkeypatch.setattr(
        strategies.app_detector,
        "detect",
        lambda app: InstalledAppInfo(app_id="word", display_name="Microsoft Word", is_installed=True, executable_path="C:/dummy/winword.exe")
    )
    # Mock dispatch strategy execution returning True
    monkeypatch.setattr(strategies, "_dispatch_app_strategy", lambda **kwargs: (True, None))

    # But verifier checks actual system state and finds NO process or window
    monkeypatch.setattr(
        strategies.verifier,
        "verify_application_running",
        lambda app, should_run=True: VerificationResult(
            verified=False,
            state=ExecutionState.FAILED,
            check_type="app_running",
            expected=True,
            actual=False,
            error="process_not_detected"
        )
    )

    result = strategies.launch_application_verified("word")
    assert result.success is False
    assert result.status == ExecutionState.FAILED
    assert result.verification_result.verified is False


# =====================================================================
# 5. Full End-to-End Jarvis App Interaction Tests
# =====================================================================

@pytest.fixture
def jarvis_app_instance(tmp_path):
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = (tmp_path / "app_test.db").as_posix()
    plugins_posix = temp_plugins.as_posix()
    cfg_content = f"""
system:
  name: "JARVIS_APP_TEST"
memory:
  db_path: "{db_path}"
brain:
  llm_provider: "mock"
plugins:
  plugin_dir: "{plugins_posix}"
  auto_load: true
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(cfg_content)

    return create_jarvis(str(cfg_file))


def test_e2e_open_excel_launches_directly_without_csv_dialog(jarvis_app_instance, monkeypatch):
    """
    Fix for the user's specific bug:
    'open excel' must directly launch Excel, NOT ask:
    'Kya aap MW-FO-nse50_opt-18-Aug-2026.csv ya options_trades.csv open karna chahte hain?'
    """
    monkeypatch.setattr(
        jarvis_app_instance.execution_strategies,
        "launch_application_verified",
        lambda app_name, is_new=False, file_path=None: ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action=f"launch_{app_name}",
            executed_action="direct_executable",
            target=app_name,
            verification_result=VerificationResult(
                verified=True,
                state=ExecutionState.SUCCESS,
                check_type="application_running",
                expected=app_name,
                actual=app_name
            ),
            data={"message": f"Launched '{app_name}' successfully."}
        )
    )

    resp = jarvis_app_instance.process_input("open excel")
    assert "Launched 'excel' successfully" in resp or "excel" in resp.lower()
    # Must NOT prompt about CSV or other files
    assert "karna chahte hain" not in resp
    assert ".csv" not in resp.lower()


def test_e2e_open_office_apps_never_open_browser(jarvis_app_instance, monkeypatch):
    """
    Fix for the user's specific bug:
    'open ppt', 'open power point', 'open microsoft access', 'open microsoft publisher'
    must launch local apps and NEVER say "'ppt' ki website browser mein open kar raha hoon".
    """
    launched_apps = []

    def mock_launch(app_name, is_new=False, file_path=None):
        launched_apps.append((app_name, is_new))
        return ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action=f"launch_{app_name}",
            executed_action="direct_executable",
            target=app_name,
            verification_result=VerificationResult(
                verified=True,
                state=ExecutionState.SUCCESS,
                check_type="application_running",
                expected=app_name,
                actual=app_name
            ),
            data={"message": f"Launched '{app_name}' successfully."}
        )

    monkeypatch.setattr(jarvis_app_instance.execution_strategies, "launch_application_verified", mock_launch)

    queries = [
        ("open word", "word"),
        ("open ppt", "powerpoint"),
        ("open power point", "powerpoint"),
        ("open microsoft power point", "powerpoint"),
        ("open microsoft access", "access"),
        ("open microsoft publisher", "publisher"),
    ]

    for query, expected_app in queries:
        resp = jarvis_app_instance.process_input(query)
        assert "website browser mein open kar raha hoon" not in resp, f"Query '{query}' erroneously opened website"
        assert f"Launched '{expected_app}' successfully" in resp or expected_app in resp.lower()

    expected_app_names = [q[1] for q in queries]
    actual_app_names = [a[0] for a in launched_apps]
    assert actual_app_names == expected_app_names


def test_e2e_uninstalled_app_reports_clear_message(jarvis_app_instance, monkeypatch):
    """Verify that requesting an uninstalled app gives a clear message and doesn't launch browser."""
    def mock_launch_uninstalled(app_name, is_new=False, file_path=None):
        return ExecutionResult(
            success=False,
            status=ExecutionState.FAILED,
            reason="not_installed",
            requested_action=f"launch_{app_name}",
            executed_action="none",
            target=app_name,
            verification_result=VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="installation_check",
                expected=app_name,
                actual=None,
                error=f"Application '{app_name}' is not installed"
            ),
            data={"display_name": app_name.capitalize()}
        )

    monkeypatch.setattr(jarvis_app_instance.execution_strategies, "launch_application_verified", mock_launch_uninstalled)

    # Spotify is registered as an app in ApplicationRegistry
    resp = jarvis_app_instance.process_input("open spotify")
    assert "installed nahi mila" in resp or "not installed" in resp.lower()
    assert "website browser mein open kar raha hoon" not in resp


def test_e2e_negative_feedback_triggers_recovery(jarvis_app_instance, monkeypatch):
    """
    Verify that if the user says 'open nahi hua', Jarvis diagnoses and attempts alternative strategy.
    """
    # Set previous result as failed Word launch
    jarvis_app_instance.last_execution_result = ExecutionResult(
        success=False,
        status=ExecutionState.FAILED,
        requested_action="launch_word",
        executed_action="direct_executable",
        target="word",
        action_type="application",
        reason="timeout_waiting_for_window"
    )

    # User gives negative feedback
    resp = jarvis_app_instance.process_input("open nahi hua")
    assert "Word" in resp or "launch" in resp or "koshish" in resp or "try" in resp
