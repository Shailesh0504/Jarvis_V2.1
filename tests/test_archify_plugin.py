# tests/test_archify_plugin.py
"""Test suite for the Archify Architecture Visualization Plugin and Semantic Intent Integration."""

import os
from unittest.mock import patch
import pytest

from core.semantic.orchestrator import SemanticPipelineOrchestrator
from plugins.archify.plugin import ArchifyPlugin
from plugins.manifest import PluginManifest, PluginResult


@pytest.fixture
def archify_plugin():
    return ArchifyPlugin()


def test_archify_manifest_and_metadata(archify_plugin):
    manifest = archify_plugin.get_manifest()
    assert manifest.name == "archify"
    assert manifest.version == "1.0.0"
    assert "filesystem" in manifest.permissions
    
    actions = {a.name: a for a in manifest.actions}
    assert "show_architecture" in actions
    action = actions["show_architecture"]
    assert "archify dikhao" in action.keywords
    assert "show archify" in action.keywords


def test_archify_html_artifact_exists(archify_plugin):
    assert os.path.isfile(archify_plugin.arch_html_path)
    assert archify_plugin.arch_html_path.endswith("jarvis-architecture.html")
    
    # Check that file has required components
    with open(archify_plugin.arch_html_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    assert "Jarvis V2.1 System Architecture" in content or "Jarvis V2.1 Live Runtime Architecture" in content
    assert "voice-execution-path" in content or "runtime-execution-path" in content
    assert "proactive-learning-loop" in content or "proactive-learning-observability" in content
    assert "plugin-runtime-boundary" in content or "execution-pipeline-boundary" in content or "boundary" in content
    assert "node-nlu_orchestrator" in content or "node-speech_act_nlu" in content
    assert "node-cmd_router" in content
    assert "node-sqlite_stores" in content


def test_archify_semantic_parser_hindi_english():
    orchestrator = SemanticPipelineOrchestrator()
    
    queries = [
        "archify dikhao",
        "show archify",
        "open archify",
        "complete archify dikhao",
        "jarvis architecture dikhao",
        "architecture open karo",
        "jarvis ka architecture dikhao",
    ]
    
    for query in queries:
        act = orchestrator.parse(query)
        assert act is not None, f"Failed to parse query: {query}"
        assert act.service == "archify", f"Expected service archify for '{query}', got {act.service}"
        assert act.action == "show_architecture", f"Expected action show_architecture for '{query}', got {act.action}"
        assert act.confidence >= 0.95


def test_archify_execution(archify_plugin):
    # Mock os.startfile / webbrowser.open to prevent browser window popping during pytest
    with patch("os.startfile", create=True) as mock_startfile, \
         patch("webbrowser.open") as mock_webbrowser:
        
        result = archify_plugin.execute("show_architecture", {})
        assert result.success is True
        assert result.data is not None
        assert "file_path" in result.data
        assert "url" in result.data
        assert mock_startfile.called or mock_webbrowser.called


def test_archify_builder_recompile():
    from plugins.archify.builder import compile_archify_html
    ok, msg = compile_archify_html()
    assert ok is True
    assert "updated successfully" in msg


def test_architecture_change_triggers_live_update():
    from core.reload_policy import classify_file_change, ReloadCategory
    from core.update_manager import LiveUpdateManager
    from unittest.mock import MagicMock

    # 1. Verify architecture.txt change classification
    plan1 = classify_file_change("architecture.txt")
    assert plan1.category == ReloadCategory.HOT_RELOAD_SAFE
    assert plan1.target_name == "archify"

    # 2. Verify plugins/archify JSON change classification
    plan2 = classify_file_change("plugins/archify/jarvis-architecture.json")
    assert plan2.category == ReloadCategory.HOT_RELOAD_SAFE
    assert plan2.target_name == "archify"

    # 3. Verify LiveUpdateManager applies plan and recompiles
    mock_core = MagicMock()
    mock_core.event_bus = MagicMock()
    mock_core.plugin_manager = None
    update_mgr = LiveUpdateManager(core=mock_core)

    with patch("plugins.archify.builder.compile_archify_html") as mock_compile:
        mock_compile.return_value = (True, "Viewer updated")
        res = update_mgr.apply_plan(plan1)
        assert res is True
        mock_compile.assert_called_once()
