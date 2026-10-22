# tests/test_event_bus_architecture.py
"""Unit tests for Decoupled Event Bus Architecture & 10 Domain Event Classes."""

import os
import pytest
from core.event_bus import (
    EventBus,
    Event,
    UserInputReceived,
    WakeWordDetected,
    CommandDetected,
    TaskStarted,
    TaskCompleted,
    MemoryCreated,
    LearningDetected,
    SuggestionCreated,
    PluginLoaded,
    PluginError,
    ConversationInterrupted
)
from main import create_jarvis


def test_event_bus_emit_and_receive_10_domain_events():
    """Verifies all 10 domain events can be emitted and dispatched over the Event Bus."""
    bus = EventBus()
    received_events = []

    def generic_listener(evt: Event):
        received_events.append(evt)

    # Subscribe to all topics using wildcard
    bus.subscribe("*", generic_listener)

    # 1. UserInputReceived
    bus.emit_domain_event(UserInputReceived(text="Jarvis, open Excel", source="voice"))
    # 2. WakeWordDetected
    bus.emit_domain_event(WakeWordDetected(wake_word="jarvis", position="prefix", cleaned_command="open Excel"))
    # 3. CommandDetected
    bus.emit_domain_event(CommandDetected(intent="open_app", plugin_name="windows", action_name="launch_app"))
    # 4. TaskStarted
    bus.emit_domain_event(TaskStarted(task_id="t-101", workflow_name="excel_clean", plan_steps=6))
    # 5. TaskCompleted
    bus.emit_domain_event(TaskCompleted(task_id="t-101", success=True, output="Excel cleaned", execution_time_ms=12.5))
    # 6. MemoryCreated
    bus.emit_domain_event(MemoryCreated(memory_type="long_term", key="user_editor", value="VSCode"))
    # 7. LearningDetected
    bus.emit_domain_event(LearningDetected(layer=2, pattern_type="vocabulary", details={"term": "movie", "target": "vlc"}))
    # 8. SuggestionCreated
    bus.emit_domain_event(SuggestionCreated(suggestion_id="sug-1", text="Open recent sales workbook?", confidence=0.95))
    # 9. PluginLoaded
    bus.emit_domain_event(PluginLoaded(plugin_name="excel", version="1.0.0", permissions=["filesystem", "office"]))
    # 10. PluginError
    bus.emit_domain_event(PluginError(plugin_name="broken_plugin", error_message="Crash on init"))

    assert len(received_events) == 10
    topics = [e.topic for e in received_events]
    assert "user.input.received" in topics
    assert "voice.wakeword.detected" in topics
    assert "command.detected" in topics
    assert "task.started" in topics
    assert "task.completed" in topics
    assert "memory.created" in topics
    assert "learning.detected" in topics
    assert "suggestion.created" in topics
    assert "plugin.loaded" in topics
    assert "plugin.error" in topics


def test_wildcard_topic_filtering():
    bus = EventBus()
    plugin_events = []
    task_events = []

    bus.subscribe("plugin.*", lambda e: plugin_events.append(e))
    bus.subscribe("task.*", lambda e: task_events.append(e))

    bus.emit_domain_event(PluginLoaded(plugin_name="pdf"))
    bus.emit_domain_event(PluginError(plugin_name="pdf", error_message="fail"))
    bus.emit_domain_event(TaskStarted(task_id="t-1"))
    bus.emit_domain_event(TaskCompleted(task_id="t-1"))

    assert len(plugin_events) == 2
    assert len(task_events) == 2


def test_full_pipeline_event_bus_emission(tmp_path):
    """Verifies that running process_input emits events on the shared EventBus."""
    import shutil
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = os.path.join(tmp_path, "bus_test.db").replace("\\", "/")
    cfg_content = f"""
system:
  name: "JARVIS_BUS_TEST"
memory:
  db_path: "{db_path}"
brain:
  llm_provider: "mock"
plugins:
  plugin_dir: "{str(temp_plugins).replace('\\', '/')}"
  auto_load: true
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(cfg_content)

    jarvis = create_jarvis(str(cfg_file))
    captured = []

    jarvis.event_bus.subscribe("*", lambda e: captured.append(e))

    resp = jarvis.process_input("Jarvis, Volume 50 karo")
    assert "50%" in resp

    topics = [e.topic for e in captured]
    assert "voice.wakeword.detected" in topics
    assert "user.input.received" in topics


def test_conversation_interrupted_event_instantiation_and_aliases():
    """Verifies ConversationInterrupted handles both canonical and alias parameter signatures seamlessly."""
    # 1. Canonical arguments
    evt1 = ConversationInterrupted(
        previous_turn_id="turn-101",
        previous_generation_id=5,
        interrupting_input="ruk jao",
        reason="user_barge_in"
    )
    assert evt1.previous_turn_id == "turn-101"
    assert evt1.turn_id == "turn-101"
    assert evt1.previous_generation_id == 5
    assert evt1.generation_id == 5
    assert evt1.interrupting_input == "ruk jao"
    assert evt1.reason == "user_barge_in"
    assert evt1.get("reason") == "user_barge_in"
    assert evt1.get("previous_generation_id") == 5
    assert evt1.get("generation_id") == 5
    assert evt1["reason"] == "user_barge_in"

    # 2. app.py argument signature (turn_id, generation_id, interrupted_at)
    evt2 = ConversationInterrupted(
        turn_id="turn-202",
        generation_id=8,
        reason="barge_in",
        interrupted_at=1234567.89
    )
    assert evt2.turn_id == "turn-202"
    assert evt2.previous_turn_id == "turn-202"
    assert evt2.generation_id == 8
    assert evt2.previous_generation_id == 8
    assert evt2.timestamp == 1234567.89
    assert evt2.interrupted_at == 1234567.89
    assert evt2.get("generation_id") == 8
    assert evt2.get("non_existent", "fallback") == "fallback"

    # 3. Emission and bus topic dispatch
    bus = EventBus()
    received = []
    bus.subscribe("conversation.interrupted", lambda e: received.append(e))
    bus.emit_domain_event(evt2)

    assert len(received) == 1
    assert received[0].topic == "conversation.interrupted"
    assert received[0].data.get("generation_id") == 8
    assert received[0].data.get("reason") == "barge_in"

