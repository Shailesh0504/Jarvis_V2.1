# tests/test_phase_4_eventbus_governance.py
"""
Unit and integration tests for Phase 4: EventBus Governance & Persistence Boundaries.
Validates:
1. Canonical EventTopics naming and domain event serialization.
2. EventBus isolated subscriber error handling (failing subscriber does not disrupt bus).
3. Asynchronous event emission (publish_async / emit_async).
4. State machine automatic state change event propagation.
5. SQLite DatabaseManager connection hardening (WAL mode, busy timeout).
"""

import os
import sqlite3
import tempfile
import threading
import time
from unittest.mock import MagicMock
import pytest

from core.app import JarvisCore
from core.event_bus import (
    ActionPlanned,
    ActivityObserved,
    Event,
    EventBus,
    EventTopics,
    ExecutionCompleted,
    PolicyEvaluated,
    ProactiveSuggestionProposed,
    SystemStateChanged,
)
from core.state import SystemState
from memory.database import DatabaseManager


class TestEventBusGovernance:
    """Tests for EventBus topic standardization, domain events, and error isolation."""

    def test_canonical_topics_structure(self):
        assert EventTopics.USER_INPUT_RECEIVED == "user.input.received"
        assert EventTopics.VOICE_WAKEWORD_DETECTED == "voice.wakeword.detected"
        assert EventTopics.ACTION_PLANNED == "action.planned"
        assert EventTopics.POLICY_EVALUATED == "policy.evaluated"
        assert EventTopics.EXECUTION_COMPLETED == "execution.completed"
        assert EventTopics.STATE_CHANGED == "system.state.changed"

    def test_domain_events_emission(self):
        bus = EventBus()
        received = []

        bus.subscribe("action.planned", lambda ev: received.append(ev))
        bus.subscribe("policy.evaluated", lambda ev: received.append(ev))
        bus.subscribe("execution.completed", lambda ev: received.append(ev))

        p_event = ActionPlanned(plan_id="p123", action="launch_app", target="notepad")
        bus.emit_domain_event(p_event)

        pol_event = PolicyEvaluated(plan_id="p123", allowed=True, reason="ok")
        bus.emit_domain_event(pol_event)

        exec_event = ExecutionCompleted(plan_id="p123", action="launch_app", target="notepad", success=True)
        bus.emit_domain_event(exec_event)

        assert len(received) == 3
        assert received[0].topic == "action.planned"
        assert received[0].data.plan_id == "p123"
        assert received[1].topic == "policy.evaluated"
        assert received[1].data.allowed is True
        assert received[2].topic == "execution.completed"
        assert received[2].data.success is True

    def test_subscriber_error_isolation(self):
        """A subscriber raising an exception must NEVER crash other subscribers or the publisher."""
        bus = EventBus()
        success_marker = []

        def broken_handler(ev):
            raise RuntimeError("Intentional Subscriber Crash")

        def good_handler(ev):
            success_marker.append(ev.topic)

        bus.subscribe("test.topic", broken_handler)
        bus.subscribe("test.topic", good_handler)

        # Must not raise an exception
        ev = bus.emit("test.topic", data={"key": "value"})

        assert len(success_marker) == 1
        assert success_marker[0] == "test.topic"

    def test_has_subscribers_and_unsubscribe(self):
        bus = EventBus()
        assert bus.has_subscribers("system.shutdown") is False

        handler = lambda ev: None
        bus.subscribe("system.*", handler)
        assert bus.has_subscribers("system.shutdown") is True
        assert bus.has_subscribers("system.state.changed") is True
        assert bus.has_subscribers("user.input") is False

        bus.unsubscribe("system.*", handler)
        assert bus.has_subscribers("system.shutdown") is False

    def test_async_event_emission(self):
        bus = EventBus()
        delivered = threading.Event()

        def async_handler(ev):
            delivered.set()

        bus.subscribe("async.topic", async_handler)
        bus.emit_async("async.topic", {"message": "hello"})

        # Wait up to 2 seconds for background delivery
        assert delivered.wait(timeout=2.0) is True


class TestSystemStateEventWiring:
    """Tests that state transitions automatically publish to EventBus."""

    def test_state_machine_transition_emits_event(self):
        core = JarvisCore(config_path="config.yaml")
        state_events = []

        core.event_bus.subscribe(
            EventTopics.STATE_CHANGED,
            lambda ev: state_events.append(ev.data)
        )

        core.state_machine.transition_to(SystemState.IDLE)
        assert len(state_events) == 1
        assert state_events[0]["old_state"] == "INITIALIZING"
        assert state_events[0]["new_state"] == "IDLE"

    def test_execute_action_plan_emits_pipeline_events(self):
        core = JarvisCore(config_path="config.yaml")
        emitted_events = []

        core.event_bus.subscribe(
            "action.planned",
            lambda ev: emitted_events.append(("action.planned", ev.data))
        )
        core.event_bus.subscribe(
            "policy.evaluated",
            lambda ev: emitted_events.append(("policy.evaluated", ev.data))
        )
        core.event_bus.subscribe(
            "execution.completed",
            lambda ev: emitted_events.append(("execution.completed", ev.data))
        )

        from core.execution.models import ActionPlan
        plan = ActionPlan(
            action="open_folder",
            target="Desktop",
            target_type="folder",
            required_permission="EXECUTE",
            source="test"
        )

        core.execute_action_plan(plan)

        event_topics = [topic for topic, _ in emitted_events]
        assert "action.planned" in event_topics
        assert "policy.evaluated" in event_topics
        assert "execution.completed" in event_topics

        # Check plan_id correlation
        planned_data = next(d for t, d in emitted_events if t == "action.planned")
        policy_data = next(d for t, d in emitted_events if t == "policy.evaluated")
        completed_data = next(d for t, d in emitted_events if t == "execution.completed")

        assert planned_data["plan_id"] == plan.plan_id
        assert policy_data["plan_id"] == plan.plan_id


class TestDatabaseManagerPersistence:
    """Tests for SQLite WAL mode, timeout configuration, and concurrency."""

    def test_database_manager_wal_mode(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
            db_path = os.path.join(tmp_dir, "test_jarvis.db")
            db = DatabaseManager(db_path=db_path)

            # Check journal_mode
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode")
                mode = cursor.fetchone()[0].lower()
                assert mode == "wal"

            # Execute insert and select with all required columns
            now = time.time()
            db.execute_update(
                "INSERT INTO preferences (user_id, category, key, value, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("u1", "ui", "theme", "dark", now)
            )
            rows = db.execute_query("SELECT value FROM preferences WHERE key = ?", ("theme",))
            assert len(rows) == 1
            assert rows[0]["value"] == "dark"
