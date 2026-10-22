# tests/test_app_resolver_system_apps.py
"""
Automated Test Suite for Priority-Based App Resolver Architecture,
Windows System Applications (Camera, Calculator, Settings, Notepad, Paint,
Task Manager, File Explorer, Control Panel, Command Prompt, PowerShell, Snipping Tool),
Natural Query Normalization, Exhaustion Handling, and Regression Invariants.
"""

import os
import shutil
import pytest
from unittest.mock import patch, MagicMock

from core.apps import (
    AppResolver,
    ResolvedApp,
    SYSTEM_APP_DEFINITIONS,
    get_app_resolver,
    ApplicationRegistry,
    InstalledAppDetector,
    get_application_registry,
    get_installed_app_detector,
)
from core.semantic import SemanticPipelineOrchestrator
from core.execution.strategies import ExecutionStrategyEngine
from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from main import create_jarvis


# =====================================================================
# 1. App Resolver Architecture & 5-Tier Priority Tests
# =====================================================================

def test_app_resolver_singleton():
    """Verify get_app_resolver() returns a valid AppResolver singleton."""
    resolver = get_app_resolver()
    assert isinstance(resolver, AppResolver)
    assert get_app_resolver() is resolver


def test_app_resolver_tier1_system_apps():
    """Verify Tier 1 correctly resolves common Windows system applications and launch strategies."""
    resolver = get_app_resolver()

    expected_apps = {
        "camera": ("protocol", "microsoft.windows.camera:"),
        "calculator": ("protocol", "calculator:"),
        "settings": ("protocol", "ms-settings:"),
        "notepad": ("executable", "notepad.exe"),
        "paint": ("executable", "mspaint.exe"),
        "task manager": ("executable", "taskmgr.exe"),
        "file explorer": ("executable", "explorer.exe"),
        "control panel": ("executable", "control.exe"),
        "command prompt": ("executable", "cmd.exe"),
        "powershell": ("executable", "powershell.exe"),
        "snipping tool": ("protocol", "ms-screenclip:"),
    }

    for query, (expected_strat, expected_target_contains) in expected_apps.items():
        res = resolver.resolve(query)
        assert res is not None, f"Expected '{query}' to resolve via AppResolver"
        assert res.is_system_app is True, f"'{query}' must be marked as system app"
        assert res.resolution_strategy == "system_app", f"'{query}' must resolve at Tier 1 (system_app)"
        assert res.launch_strategy == expected_strat, f"'{query}' expected strategy '{expected_strat}', got '{res.launch_strategy}'"
        assert expected_target_contains.lower() in res.launch_target.lower(), (
            f"'{query}' expected target containing '{expected_target_contains}', got '{res.launch_target}'"
        )


def test_app_resolver_camera_specifications():
    """Verify Camera specifically has all required UWP protocols, process names, and aliases."""
    resolver = get_app_resolver()
    res = resolver.resolve("camera")

    assert res is not None
    assert res.app_id == "camera"
    assert res.display_name == "Camera"
    assert res.launch_strategy == "protocol"
    assert res.launch_target == "microsoft.windows.camera:"
    assert res.protocol == "microsoft.windows.camera:"
    assert any("windowscamera" in p.lower() for p in res.process_names)
    assert any("camera" in t.lower() for t in res.window_titles)


def test_app_resolver_tier2_known_aliases():
    """Verify Tier 2 resolves standard registered desktop apps (Office, Browsers, etc.)."""
    resolver = get_app_resolver()

    # For installed Office apps or browsers, resolution should succeed via known_alias
    for app in ["word", "excel", "chrome", "edge"]:
        res = resolver.resolve(app)
        if res:  # Only if installed on host machine
            assert res.app_id == app
            assert res.resolution_strategy in ("known_alias", "start_menu_or_registration", "executable_path", "installed_search")


def test_app_resolver_tier5_exhaustion_for_fake_apps():
    """Verify AppResolver exhausts all 5 tiers and returns None for non-existent apps."""
    resolver = get_app_resolver()
    fake_app = "totally_nonexistent_fake_app_xyz_999"
    res = resolver.resolve(fake_app)
    assert res is None, f"Nonexistent app '{fake_app}' must resolve to None"


# =====================================================================
# 2. Natural Language Query Parsing & Speech Variants
# =====================================================================

def test_natural_camera_queries():
    """Verify natural Hinglish and English camera commands resolve to OPEN_APP launch_app."""
    test_queries = [
        "open camera",
        "camera kholo",
        "camera chalao",
        "launch camera",
        "start camera",
        "camera open karo",
        "zara camera khol do",
        "please open camera",
        "camera start karo",
        "camera chala do",
    ]

    for q in test_queries:
        action = SemanticPipelineOrchestrator.parse(q)
        assert action is not None, f"Query '{q}' produced None SemanticAction"
        assert action.intent == "OPEN_APP", f"Query '{q}' expected OPEN_APP, got {action.intent}"
        assert action.action == "launch_app", f"Query '{q}' expected launch_app, got {action.action}"
        assert (action.parameters or {}).get("app_name") == "camera", (
            f"Query '{q}' expected app_name='camera', got {action.parameters.get('app_name')}"
        )


def test_natural_system_app_queries():
    """Verify natural commands for other common Windows system apps."""
    cases = [
        ("open calculator", "calc"),
        ("calculator kholo", "calc"),
        ("hisab kitab kholo", "calc"),
        ("open settings", "settings"),
        ("settings kholo", "settings"),
        ("windows settings open karo", "settings"),
        ("open notepad", "notepad"),
        ("notepad kholo", "notepad"),
        ("open paint", "paint"),
        ("mspaint kholo", "paint"),
        ("open task manager", "taskmgr"),
        ("task manager kholo", "taskmgr"),
        ("open file explorer", "explorer"),
        ("explorer kholo", "explorer"),
        ("open control panel", "control_panel"),
        ("control panel kholo", "control_panel"),
        ("open command prompt", "cmd"),
        ("cmd kholo", "cmd"),
        ("open powershell", "powershell"),
        ("powershell kholo", "powershell"),
        ("open snipping tool", "snipping_tool"),
        ("snipping tool kholo", "snipping_tool"),
    ]

    for q, expected_app_id in cases:
        action = SemanticPipelineOrchestrator.parse(q)
        assert action is not None, f"Query '{q}' produced None SemanticAction"
        assert action.intent == "OPEN_APP", f"Query '{q}' expected OPEN_APP, got {action.intent}"
        assert action.action == "launch_app", f"Query '{q}' expected launch_app, got {action.action}"
        app_name = (action.parameters or {}).get("app_name")
        assert app_name == expected_app_id, f"Query '{q}' expected app_name='{expected_app_id}', got '{app_name}'"


# =====================================================================
# 3. InstalledAppDetector Integration Tests
# =====================================================================

def test_detector_detects_camera():
    """Verify InstalledAppDetector identifies camera with protocol launch strategy."""
    detector = get_installed_app_detector()
    info = detector.detect("camera")

    assert info is not None
    assert info.is_installed is True
    assert info.app_id == "camera"
    assert info.launch_strategy == "protocol"
    assert info.protocol == "microsoft.windows.camera:"

    launch_cmd = detector.get_launch_command("camera")
    assert launch_cmd is not None
    target, args, strat = launch_cmd
    assert target == "microsoft.windows.camera:"
    assert strat == "protocol"


def test_detector_exhaustion_on_uninstalled_app():
    """Verify detector safely returns is_installed=False for uninstalled apps."""
    detector = get_installed_app_detector()
    info = detector.detect("fake_uninstalled_app_xyz")
    assert info is None or info.is_installed is False


# =====================================================================
# 4. Execution Strategy Engine Tests
# =====================================================================

def test_launch_application_verified_camera_protocol_priority(monkeypatch):
    """Verify launch_application_verified prioritizes protocol strategy for Camera."""
    engine = ExecutionStrategyEngine()
    dispatched_strategies = []

    def mock_dispatch(strategy, app_def, canonical_id, installed_info, is_new=False, file_path=None):
        dispatched_strategies.append(strategy)
        return True, None

    monkeypatch.setattr(engine, "_dispatch_app_strategy", mock_dispatch)
    monkeypatch.setattr(
        engine.verifier,
        "verify_application_running",
        lambda app, should_run=True: VerificationResult(
            verified=True,
            state=ExecutionState.SUCCESS,
            check_type="app_running",
            expected=True,
            actual=True
        )
    )

    res = engine.launch_application_verified("camera")
    assert res.success is True
    assert res.status == ExecutionState.SUCCESS
    # Protocol must be the FIRST strategy attempted
    assert len(dispatched_strategies) > 0
    assert dispatched_strategies[0] == "protocol"


# =====================================================================
# 5. Full End-to-End Jarvis Interaction Tests
# =====================================================================

@pytest.fixture
def jarvis_instance(tmp_path):
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = (tmp_path / "app_resolver_test.db").as_posix()
    plugins_posix = temp_plugins.as_posix()
    cfg_content = f"""
system:
  name: "JARVIS_APP_RESOLVER_TEST"
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


def test_e2e_open_camera_all_variants(jarvis_instance, monkeypatch):
    """Verify 'open camera', 'camera kholo', 'camera chalao', 'launch camera', 'start camera' all succeed."""
    launched_apps = []

    def mock_launch(app_name, is_new=False, file_path=None):
        launched_apps.append(app_name)
        return ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action=f"launch_{app_name}",
            executed_action="launch_app_protocol",
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

    monkeypatch.setattr(jarvis_instance.execution_strategies, "launch_application_verified", mock_launch)

    queries = [
        "open camera",
        "camera kholo",
        "camera chalao",
        "launch camera",
        "start camera",
    ]

    for q in queries:
        resp = jarvis_instance.process_input(q)
        assert "not installed" not in resp.lower()
        assert "installed nahi mila" not in resp.lower()
        assert "youtube" not in resp.lower()
        assert "Launched 'camera' successfully" in resp or "camera" in resp.lower()

    assert len(launched_apps) == len(queries)
    assert all(a == "camera" for a in launched_apps)


def test_e2e_uninstalled_app_exhausts_and_reports_clear_message(jarvis_instance):
    """Verify truly uninstalled app exhausts all tiers and informs user without crash."""
    resp = jarvis_instance.process_input("open fakeappthatdoesnotexist999 application")
    # Must report not installed
    assert ("installed nahi mila" in resp or "not installed" in resp.lower())
    # Must not open browser or declare false success
    assert "fakeappthatdoesnotexist999.com" not in resp.lower()


# =====================================================================
# 6. Regression Invariants: Websites, Folders, Media, Office Apps
# =====================================================================

def test_regression_office_apps_unbroken(jarvis_instance, monkeypatch):
    """Verify Word and Excel launch directly without regressions."""
    launched = []
    monkeypatch.setattr(
        jarvis_instance.execution_strategies,
        "launch_application_verified",
        lambda app_name, is_new=False, file_path=None: (
            launched.append(app_name) or ExecutionResult(
                success=True,
                status=ExecutionState.SUCCESS,
                requested_action=f"launch_{app_name}",
                executed_action="direct_executable",
                target=app_name,
                data={"message": f"Launched '{app_name}' successfully."}
            )
        )
    )

    resp = jarvis_instance.process_input("open excel")
    assert "Launched 'excel' successfully" in resp or "excel" in resp.lower()
    assert ".csv" not in resp.lower()

    resp2 = jarvis_instance.process_input("open word")
    assert "Launched 'word' successfully" in resp2 or "word" in resp2.lower()


def test_regression_explicit_website_never_hijacked():
    """Verify explicit website requests still route to OPEN_WEBSITE."""
    for q in ["open excel website", "open powerpoint website", "open microsoft.com"]:
        action = SemanticPipelineOrchestrator.parse(q)
        assert action is not None
        assert action.intent == "OPEN_WEBSITE"


def test_regression_folder_never_hijacked():
    """Verify folder commands still route to FOLDER_OPEN."""
    for q in ["open startup folder", "open desktop folder"]:
        action = SemanticPipelineOrchestrator.parse(q)
        assert action is not None
        assert action.intent == "FOLDER_OPEN"


def test_regression_song_playback_never_hijacked():
    """Verify real song playback requests still route to PLAY_MEDIA."""
    for q in ["play arijit singh songs", "arijit singh gaana chalao", "play song on youtube"]:
        action = SemanticPipelineOrchestrator.parse(q)
        assert action is not None
        assert action.intent in ("PLAY_MEDIA", "MEDIA_PLAYBACK")
