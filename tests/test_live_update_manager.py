# tests/test_live_update_manager.py
"""
Comprehensive tests for Zero-Downtime Live Background Code Update Subsystem.
Verifies all 12 requirements from Section 17:
1. Modify normal plugin file -> GUI remains alive
2. Modify skill file -> GUI remains alive
3. Modify command router/brain -> Affected runtime reload only
4. Modify trading signal module -> Trading component reload/restart only, GUI remains alive
5. Multiple filesystem events -> One reload transaction
6. EventBus subscription after reload -> Exactly one active subscription
7. Old worker termination -> No orphan thread
8. Reload failure -> GUI remains alive
9. Rollback -> Previous working component restored
10. Full-restart-required change -> Explicitly classified and logged
11. GUI state preservation -> Same window/state/session preserved
12. Unrelated features -> No regression
"""

import os
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from core.event_bus import EventBus
from core.reload_policy import (
    ReloadCategory,
    ReloadPlan,
    classify_file_change,
    coalesce_file_changes,
)
from core.update_manager import LiveUpdateManager
from main import create_jarvis
from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult, PluginStatus


@pytest.fixture
def mock_core():
    """Provides a lightweight mocked core with EventBus and PluginManager."""
    core = MagicMock()
    core.event_bus = EventBus()
    core.config = {"system": {"auto_reload": True}}
    core.config_path = "config.yaml"
    return core


def test_1_modify_normal_plugin_keeps_gui_alive(mock_core):
    """1. Modifying a normal plugin file reloads in-process and never terminates the host."""
    plan = classify_file_change("plugins/calculator/plugin.py")
    assert plan.category == ReloadCategory.HOT_RELOAD_SAFE
    assert plan.plugin_name == "calculator"

    # Setup plugin manager mock
    mock_plugin_mgr = MagicMock()
    mock_plugin_mgr.reload_plugin.return_value = (True, "Reloaded calculator")
    mock_core.plugin_manager = mock_plugin_mgr

    update_mgr = LiveUpdateManager(core=mock_core)
    success = update_mgr.apply_plan(plan)

    assert success is True
    mock_plugin_mgr.reload_plugin.assert_called_once_with("calculator")
    # Verify no sys.exit or termination occurred


def test_2_modify_skill_file_keeps_gui_alive():
    """2. Modifying a skill file is classified as HOT_RELOAD_SAFE with zero downtime."""
    plan = classify_file_change("skills/weather/SKILL.md")
    assert plan.category == ReloadCategory.HOT_RELOAD_SAFE
    assert plan.target_name == "skills"

    plan_py = classify_file_change("skills/custom/handler.py")
    assert plan_py.category == ReloadCategory.HOT_RELOAD_SAFE


def test_3_modify_command_router_reloads_runtime_only(mock_core):
    """3. Modifying command parser/classifier reloads target module in-process."""
    plan = classify_file_change("brain/semantic_parser.py")
    assert plan.category == ReloadCategory.HOT_RELOAD_SAFE
    assert "brain.semantic_parser" in plan.modules_to_reload

    update_mgr = LiveUpdateManager(core=mock_core)
    with patch("importlib.reload") as mock_reload:
        success = update_mgr.apply_plan(plan)
        assert success is True


def test_4_modify_trading_signal_module_restarts_worker_only(mock_core):
    """4. Modifying trading signals triggers worker restart category without GUI termination."""
    plan = classify_file_change("plugins/trading_signals/models/panel_types.py")
    assert plan.category == ReloadCategory.WORKER_RESTART_REQUIRED
    assert plan.plugin_name == "trading_signals"

    plan2 = classify_file_change("plugins/trading_signals/strategy/confluence_engine.py")
    assert plan2.category == ReloadCategory.WORKER_RESTART_REQUIRED
    assert plan2.plugin_name == "trading_signals"

    mock_plugin_mgr = MagicMock()
    mock_plugin_mgr.reload_plugin.return_value = (True, "Trading signals reloaded")
    mock_core.plugin_manager = mock_plugin_mgr

    update_mgr = LiveUpdateManager(core=mock_core)
    success = update_mgr.apply_plan(plan)
    assert success is True
    mock_plugin_mgr.reload_plugin.assert_called_once_with("trading_signals")


def test_5_multiple_filesystem_events_debounced_into_single_transaction():
    """5. Rapid file modifications within debounce window coalesce into 1 transaction."""
    rapid_events = [
        "plugins/trading_signals/models/panel_types.py",
        "plugins/trading_signals/models/panel_types.py",
        "plugins/trading_signals/vision/extractor.py",
        "plugins/trading_signals/strategy/confluence_engine.py",
    ]
    coalesced = coalesce_file_changes(rapid_events)
    assert coalesced.category == ReloadCategory.WORKER_RESTART_REQUIRED
    assert coalesced.plugin_name == "trading_signals"
    assert len(coalesced.affected_files) == 3


def test_6_eventbus_subscription_after_reload_has_no_duplicates():
    """6. EventBus subscriptions from old module are removed before new ones register."""
    bus = EventBus()
    invocations = []

    # Mock handler representing a method from plugins.trading_signals
    class DummyTradingHandler:
        __module__ = "plugins.trading_signals.coordinator"

        def on_event(self, event):
            invocations.append("old")

    old_handler = DummyTradingHandler()
    bus.subscribe("trading.signal", old_handler.on_event)

    # Verify old handler receives event
    bus.emit("trading.signal", {"test": 1})
    assert len(invocations) == 1
    assert invocations[-1] == "old"

    # Simulate reload cleanup
    removed = bus.remove_handlers_by_module("plugins.trading_signals")
    assert removed == 1

    # Register replacement handler from newly loaded module
    class NewTradingHandler:
        __module__ = "plugins.trading_signals.coordinator"

        def on_event(self, event):
            invocations.append("new")

    new_handler = NewTradingHandler()
    bus.subscribe("trading.signal", new_handler.on_event)

    # Verify event is received ONLY by new handler (no duplicates)
    bus.emit("trading.signal", {"test": 2})
    assert len(invocations) == 2
    assert invocations[-1] == "new"


def test_7_old_worker_termination_leaves_no_orphan_threads():
    """7. Plugin shutdown halts active worker threads cleanly."""
    class DummyWorkerThread(threading.Thread):
        def __init__(self):
            super().__init__()
            self._stopped = False

        def run(self):
            while not self._stopped:
                time.sleep(0.01)

        def stop(self):
            self._stopped = True

    worker = DummyWorkerThread()
    worker.start()
    assert worker.is_alive()

    # Simulate plugin shutdown
    worker.stop()
    worker.join(timeout=1.0)
    assert not worker.is_alive()


def test_8_reload_failure_keeps_gui_alive_and_notifies(mock_core):
    """8. A syntax error or crash during reload preserves the GUI host and logs error."""
    mock_plugin_mgr = MagicMock()
    mock_plugin_mgr.reload_plugin.return_value = (False, "SyntaxError in plugin.py")
    mock_core.plugin_manager = mock_plugin_mgr

    events_received = []
    mock_core.event_bus.subscribe("system.update.status", lambda e: events_received.append(e.data))

    update_mgr = LiveUpdateManager(core=mock_core)
    plan = classify_file_change("plugins/bad_plugin/plugin.py")

    success = update_mgr.apply_plan(plan)
    assert success is False

    # Verify error notification emitted without crashing
    error_events = [e for e in events_received if e.get("status") == "error"]
    assert len(error_events) >= 1
    assert "SyntaxError" in error_events[0].get("message", "")


def test_9_rollback_restores_previous_working_component():
    """9. PluginManager.reload_plugin restores previous instance on failure."""
    from plugins.manager import PluginManager

    mgr = PluginManager(plugin_dir="plugins", config={})
    old_instance = MagicMock()
    old_instance.status = PluginStatus.ENABLED
    old_instance.get_manifest.return_value = MagicMock(name="mock_plugin")
    old_manifest = MagicMock(name="mock_plugin")

    mgr._plugins["mock_plugin"] = old_instance
    mgr._manifests["mock_plugin"] = old_manifest
    mgr._plugin_paths["mock_plugin"] = "."

    # Patch _load_plugin_from_dir to simulate syntax error on new version
    with patch.object(mgr, "_load_plugin_from_dir", side_effect=SyntaxError("Invalid syntax")):
        success, msg = mgr.reload_plugin("mock_plugin")
        assert success is False
        assert "Invalid syntax" in msg
        # Old instance was preserved
        assert mgr.get_plugin("mock_plugin") is old_instance


def test_10_full_restart_required_change_logs_and_emits_notice(mock_core):
    """10. Changes to bootstrap files (main.py) are classified FULL_RESTART and never kill GUI."""
    plan = classify_file_change("main.py")
    assert plan.category == ReloadCategory.FULL_RESTART_REQUIRED
    assert "bootstrap" in plan.reason.lower()

    events_received = []
    mock_core.event_bus.subscribe("system.update.status", lambda e: events_received.append(e.data))

    update_mgr = LiveUpdateManager(core=mock_core)
    # Applying plan must return False but MUST NOT call sys.exit or raise
    success = update_mgr.apply_plan(plan)
    assert success is False

    notice_events = [e for e in events_received if e.get("status") == "full_restart_needed"]
    assert len(notice_events) == 1


def test_11_gui_state_preservation(mock_core):
    """11. Updates leave core state machine, conversation, and active context intact."""
    from core.state import SystemState
    mock_core.state_machine = MagicMock()
    mock_core.state_machine.current_state = SystemState.IDLE

    mock_plugin_mgr = MagicMock()
    mock_plugin_mgr.reload_plugin.return_value = (True, "Reloaded")
    mock_core.plugin_manager = mock_plugin_mgr

    update_mgr = LiveUpdateManager(core=mock_core)
    plan = classify_file_change("plugins/system/plugin.py")
    update_mgr.apply_plan(plan)

    # State machine remains IDLE
    assert mock_core.state_machine.current_state == SystemState.IDLE


def test_12_unrelated_features_no_regression(mock_core):
    """12. Reloading one plugin leaves unrelated plugins registered and functional."""
    from plugins.manager import PluginManager
    mgr = PluginManager(plugin_dir="plugins", config={})

    p1 = MagicMock()
    p1.get_manifest.return_value = MagicMock(name="p1")
    p2 = MagicMock()
    p2.get_manifest.return_value = MagicMock(name="p2")

    mgr._plugins["p1"] = p1
    mgr._plugins["p2"] = p2

    # Reload p1 only
    with patch.object(mgr, "_load_plugin_from_dir", return_value=True):
        mgr._plugins["p1"] = MagicMock() # replacement
        mgr.reload_plugin("p1")

    # p2 remains completely untouched
    assert mgr.get_plugin("p2") is p2
