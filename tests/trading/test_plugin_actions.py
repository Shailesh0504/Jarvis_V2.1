# tests/trading/test_plugin_actions.py
"""
Unit tests for TradingSignalsPlugin:
- Plugin initialization and manifest validation
- Actions:
  - get_signal_status (checks broker invariant)
  - set_strategy_mode (switches modes)
  - reset_signal_state (resets to FLAT)
  - start_signal_monitor / stop_signal_monitor
"""

import pytest
from plugins.trading_signals import TradingSignalsPlugin
from plugins.trading_signals.models.signal_types import (
    PositionState,
    StrategyTriggerMode
)


def test_plugin_manifest_and_permissions():
    """Verify plugin manifest registers proper actions and permissions."""
    plugin = TradingSignalsPlugin()
    assert plugin.manifest.name == "trading_signals"
    assert plugin.manifest.enabled is True
    assert "screen.read" in plugin.manifest.normalized_permissions

    action_names = [a.name for a in plugin.manifest.actions]
    assert "start_signal_monitor" in action_names
    assert "stop_signal_monitor" in action_names
    assert "get_signal_status" in action_names
    assert "set_strategy_mode" in action_names
    assert "reset_signal_state" in action_names


def test_plugin_get_status_invariant():
    """Verify get_signal_status reports broker invariant and FLAT initial state."""
    plugin = TradingSignalsPlugin()
    res = plugin.execute("get_signal_status")

    assert res.success is True
    assert res.data["signal_state"] == PositionState.FLAT.value
    assert res.data["broker_invariant"] == "JARVIS_SIGNAL_ACTIVE != ACTUAL_BROKER_POSITION"
    assert res.data["strategy_mode"] == StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD.value


def test_plugin_set_strategy_mode():
    """Verify strategy mode can be updated via plugin action."""
    plugin = TradingSignalsPlugin()

    # Switch to DUAL_FRESH_TRIGGER
    res = plugin.execute("set_strategy_mode", {"mode": "DUAL_FRESH_TRIGGER"})
    assert res.success is True
    assert plugin.strategy_mode == StrategyTriggerMode.DUAL_FRESH_TRIGGER

    # Switch back to REGIME_CONFIRMED_OPTION_LEAD
    res = plugin.execute("set_strategy_mode", {"mode": "REGIME_CONFIRMED_OPTION_LEAD"})
    assert res.success is True
    assert plugin.strategy_mode == StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD

    # Invalid mode returns failure
    res_inv = plugin.execute("set_strategy_mode", {"mode": "NON_EXISTENT_MODE"})
    assert res_inv.success is False
    assert "Invalid strategy mode" in res_inv.error


def test_plugin_reset_signal_state():
    """Verify reset_signal_state clears state back to FLAT."""
    plugin = TradingSignalsPlugin()
    # Force state to active
    plugin.position_tracker.state = PositionState.JARVIS_SIGNAL_ACTIVE

    res = plugin.execute("reset_signal_state")
    assert res.success is True
    assert plugin.position_tracker.state == PositionState.FLAT
    assert res.data["signal_state"] == PositionState.FLAT.value


def test_plugin_unknown_action():
    """Verify executing unknown action returns error."""
    plugin = TradingSignalsPlugin()
    res = plugin.execute("unknown_arbitrary_action")
    assert res.success is False
    assert "Unknown action" in res.error
