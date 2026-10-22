# tests/test_antigravity_app_website_resolution.py
"""
Automated unit and integration test suite for:
1. Application vs Website distinction (Antigravity application vs website).
2. Clean entity extraction decoupled from user utterance and verbs.
3. Centralized alias mappings (APPLICATION_ALIASES, WEBSITE_ALIASES, PLUGIN_ALIASES).
4. Deterministic resolution order (local app -> known website -> browser fallback).
5. End-to-end execution without regression.
"""

import os
import shutil
import pytest
from unittest.mock import MagicMock, patch

from core.apps import (
    APPLICATION_ALIASES,
    WEBSITE_ALIASES,
    PLUGIN_ALIASES,
    ApplicationRegistry,
    InstalledAppDetector,
    get_application_registry,
    get_installed_app_detector,
)
from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from core.semantic import SemanticPipelineOrchestrator
from brain.semantic_parser import HinglishNLUParser
from main import create_jarvis


# =====================================================================
# 1. Centralized Aliases Tests
# =====================================================================

def test_centralized_alias_registries_exist():
    """Verify central alias registries are defined, populated, and non-empty."""
    assert isinstance(APPLICATION_ALIASES, dict)
    assert len(APPLICATION_ALIASES) > 0
    assert "antigravity" in APPLICATION_ALIASES
    assert "chrome" in APPLICATION_ALIASES
    assert "brave" in APPLICATION_ALIASES
    assert "word" in APPLICATION_ALIASES
    assert "excel" in APPLICATION_ALIASES

    assert isinstance(WEBSITE_ALIASES, dict)
    assert len(WEBSITE_ALIASES) > 0
    assert "chatgpt" in WEBSITE_ALIASES
    assert WEBSITE_ALIASES["chatgpt"] == "https://chatgpt.com"

    assert isinstance(PLUGIN_ALIASES, dict)
    assert len(PLUGIN_ALIASES) > 0
    assert "browser" in PLUGIN_ALIASES
    assert "apps" in PLUGIN_ALIASES


def test_registry_indexes_central_application_aliases():
    """Verify ApplicationRegistry loads and indexes all centralized aliases."""
    reg = ApplicationRegistry()
    app = reg.find_by_alias("antigravity")
    assert app is not None
    assert app.app_id == "antigravity"
    assert app.display_name == "Antigravity"

    app_ide = reg.find_by_alias("antigravity ide")
    assert app_ide is not None
    assert app_ide.app_id == "antigravity_ide"
    assert app_ide.display_name == "Antigravity IDE"


# =====================================================================
# 2. Entity Extraction & Query Parsing Tests
# =====================================================================

def test_entity_extraction_decoupled_from_user_text():
    """
    Verify command parser extracts clean entities without verbs or qualifiers.
    - 'antigravity application open karo' -> entity: 'antigravity'
    - 'open antigravity' -> entity: 'antigravity'
    - 'antigravity chala do' -> entity: 'antigravity'
    - 'antigravity ki website kholo' -> entity: 'antigravity' (no 'ki')
    """
    reg = ApplicationRegistry()

    cases = [
        ("open antigravity", "antigravity", "auto", False),
        ("antigravity application open karo", "antigravity", "application", False),
        ("launch antigravity", "antigravity", "auto", False),
        ("antigravity chalao", "antigravity", "auto", False),
        ("start antigravity", "antigravity", "auto", False),
        ("antigravity chala do", "antigravity", "auto", False),
        ("antigravity website kholo", "antigravity", "website", True),
        ("open antigravity website", "antigravity", "website", True),
        ("antigravity ki website kholo", "antigravity", "website", True),
    ]

    for query, expected_entity, expected_target_type, expected_is_web in cases:
        matched_app, meta = reg.parse_query(query)
        assert meta["cleaned_target"] == expected_entity, (
            f"Query '{query}' expected cleaned target '{expected_entity}', got '{meta['cleaned_target']}'"
        )
        assert meta["extracted_entity"] == expected_entity, (
            f"Query '{query}' expected extracted entity '{expected_entity}', got '{meta['extracted_entity']}'"
        )
        assert meta["target_type"] == expected_target_type, (
            f"Query '{query}' expected target_type '{expected_target_type}', got '{meta['target_type']}'"
        )
        assert meta["is_website"] == expected_is_web, (
            f"Query '{query}' expected is_website={expected_is_web}, got {meta['is_website']}"
        )


# =====================================================================
# 3. Application vs Website Semantic Parsing Tests
# =====================================================================

def test_application_requests_parsed_as_open_app():
    """
    Verify all application variations for Antigravity resolve strictly to OPEN_APP.
    """
    app_queries = [
        "open antigravity",
        "antigravity application open karo",
        "launch antigravity",
        "antigravity chalao",
        "start antigravity",
        "antigravity chala do",
    ]

    for q in app_queries:
        action = SemanticPipelineOrchestrator.parse(q)
        assert action is not None, f"Query '{q}' returned None SemanticAction"
        assert action.intent == "OPEN_APP", f"Query '{q}' expected OPEN_APP, got {action.intent}"
        assert action.action == "launch_app", f"Query '{q}' expected launch_app, got {action.action}"
        assert action.parameters.get("app_name") == "antigravity", (
            f"Query '{q}' expected app_name='antigravity', got {action.parameters.get('app_name')}"
        )
        assert action.parameters.get("target_type") == "application", (
            f"Query '{q}' expected target_type='application', got {action.parameters.get('target_type')}"
        )


def test_antigravity_ide_requests_parsed_as_open_ide_app():
    """
    Verify all IDE variations for Antigravity resolve directly to OPEN_APP with app_name='antigravity_ide'
    and do NOT trigger clarification or open website.
    """
    ide_queries = [
        "open antigravity ide",
        "antigravity ide open karo",
        "antigravity ide kholo",
        "launch antigravity ide",
        "anti gravity ide open karo",
    ]
    for q in ide_queries:
        action = SemanticPipelineOrchestrator.parse(q)
        assert action is not None, f"Query '{q}' returned None SemanticAction"
        assert action.intent == "OPEN_APP", f"Query '{q}' expected OPEN_APP, got {action.intent}"
        assert action.action == "launch_app", f"Query '{q}' expected launch_app, got {action.action}"
        assert action.needs_clarification is False, f"Query '{q}' unexpectedly requested clarification"
        assert action.parameters.get("app_name") == "antigravity_ide", (
            f"Query '{q}' expected app_name='antigravity_ide', got {action.parameters.get('app_name')}"
        )



def test_website_requests_parsed_as_open_website():
    """
    Verify explicit website variations resolve to OPEN_WEBSITE and never OPEN_APP.
    """
    website_queries = [
        ("antigravity website kholo", "antigravity"),
        ("open antigravity website", "antigravity"),
        ("antigravity ki website kholo", "antigravity"),
    ]

    for q, expected_site in website_queries:
        action = SemanticPipelineOrchestrator.parse(q)
        assert action is not None, f"Query '{q}' returned None SemanticAction"
        assert action.intent == "OPEN_WEBSITE", f"Query '{q}' expected OPEN_WEBSITE, got {action.intent}"
        assert action.parameters.get("site") == expected_site, (
            f"Query '{q}' expected site='{expected_site}', got {action.parameters.get('site')}"
        )
        assert action.query == expected_site
        assert action.service == "browser"


def test_known_web_service_requests():
    """Verify known web service 'open chatgpt' resolves directly to its URL."""
    action = SemanticPipelineOrchestrator.parse("open chatgpt")
    assert action is not None
    assert action.intent == "OPEN_WEBSITE"
    assert action.parameters.get("url") == "https://chatgpt.com"
    assert action.query == "chatgpt"


def test_existing_apps_remain_open_app():
    """Verify existing applications continue to resolve to OPEN_APP without regression."""
    existing_apps = [
        ("open chrome", "chrome"),
        ("open brave", "brave"),
        ("open excel", "excel"),
        ("open word", "word"),
    ]
    for q, expected_app in existing_apps:
        action = SemanticPipelineOrchestrator.parse(q)
        assert action is not None, f"Query '{q}' returned None"
        assert action.intent == "OPEN_APP", f"Query '{q}' expected OPEN_APP, got {action.intent}"
        assert action.parameters.get("app_name") == expected_app


# =====================================================================
# 4. Dynamic Installed App Detection Tests
# =====================================================================

def test_antigravity_installed_detection():
    """Verify InstalledAppDetector locates Antigravity on this system."""
    detector = get_installed_app_detector()
    info = detector.detect("antigravity")
    assert info is not None
    assert info.is_installed is True
    assert info.app_id == "antigravity"
    # Should resolve either to shortcut or executable
    assert (info.shortcut_path is not None and os.path.exists(info.shortcut_path)) or (
        info.executable_path is not None and os.path.exists(info.executable_path)
    )


# =====================================================================
# 5. End-to-End Jarvis Execution Tests
# =====================================================================

@pytest.fixture
def jarvis_instance(tmp_path):
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = (tmp_path / "antigravity_test.db").as_posix()
    plugins_posix = temp_plugins.as_posix()
    cfg_content = f"""
system:
  name: "JARVIS_ANTIGRAVITY_TEST"
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


def test_e2e_antigravity_app_launch_verified(jarvis_instance, monkeypatch):
    """
    Verify end-to-end execution of 'open antigravity' triggers local app launch
    and does NOT open browser or website.
    """
    launched_apps = []

    def mock_launch(app_name, is_new=False, file_path=None):
        launched_apps.append(app_name)
        return ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action=f"launch_{app_name}",
            executed_action="start_menu_shortcut",
            target=app_name,
            verification_result=VerificationResult(
                verified=True,
                state=ExecutionState.SUCCESS,
                check_type="app_running",
                expected=app_name,
                actual=app_name
            ),
            data={"message": f"Launched '{app_name}' successfully."}
        )

    monkeypatch.setattr(jarvis_instance.execution_strategies, "launch_application_verified", mock_launch)

    resp = jarvis_instance.process_input("open antigravity")
    assert "website" not in resp.lower()
    assert "antigravity" in resp.lower()
    assert len(launched_apps) == 1
    assert launched_apps[0] == "antigravity"


def test_e2e_antigravity_website_open(jarvis_instance, monkeypatch):
    """
    Verify end-to-end execution of 'antigravity website kholo' delegates to browser.
    """
    browser_calls = []

    mock_outcome = MagicMock()
    mock_outcome.success = True
    mock_outcome.message = "antigravity website open kar diya."
    mock_outcome.needs_clarification = False

    monkeypatch.setattr(jarvis_instance.target_engine, "execute", lambda req: browser_calls.append(req) or mock_outcome)

    resp = jarvis_instance.process_input("antigravity website kholo")
    assert len(browser_calls) == 1
    assert browser_calls[0].target == "antigravity"
    assert browser_calls[0].action == "open"
    assert "open kar diya" in resp
