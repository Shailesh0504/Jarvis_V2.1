# tests/test_proactive_activity_memory.py
"""
Comprehensive tests for Phase 3: Activity & Context Memory.
Verifies short-term sliding window, live context access, SQLite persistence,
importance filtering, temporal queries (abhi, last, offset minutes), website filters,
and automatic observer integration.
"""

import time
from unittest.mock import MagicMock, patch
import pytest

from core.observer.activity_memory import ActivityMemory
from core.observer.models import ActivityEvent, ActivityImportance, ActivityType, DesktopSnapshot
from core.observer.activity_observer import ProactiveActivityObserver
from memory.database import DatabaseManager


@pytest.fixture
def temp_db(tmp_path):
    """Creates a fresh SQLite database with proactive schema in a temp directory."""
    db_file = str(tmp_path / "test_jarvis.db")
    db = DatabaseManager(db_path=db_file)
    return db


# ---------------------------------------------------------------------------
# 1. Short-Term Context Window Tests
# ---------------------------------------------------------------------------

def test_short_term_context_sliding_window_and_current_context():
    """Verifies that sliding window holds events, rolls over, and exposes current context."""
    mem = ActivityMemory(db=None, max_history=3)

    e1 = ActivityEvent(
        event_type=ActivityType.WEBSITE_OPENED,
        importance=ActivityImportance.MEDIUM,
        application="chrome",
        window_title="Google Search",
        website="google",
        content_title="machine learning",
        timestamp=1000.0
    )
    e2 = ActivityEvent(
        event_type=ActivityType.DOCUMENT_EDITED,
        importance=ActivityImportance.MEDIUM,
        application="excel",
        window_title="Sales.xlsx - Excel",
        content_title="Sales.xlsx",
        timestamp=1050.0
    )
    e3 = ActivityEvent(
        event_type=ActivityType.VIDEO_PLAYED,
        importance=ActivityImportance.HIGH,
        application="chrome",
        window_title="Kesariya - YouTube",
        website="youtube",
        content_title="Kesariya",
        timestamp=1100.0
    )

    mem.record_event(e1)
    mem.record_event(e2)
    mem.record_event(e3)

    # Context should match e3
    ctx = mem.get_current_context()
    assert ctx["application"] == "chrome"
    assert ctx["website"] == "youtube"
    assert ctx["content_title"] == "Kesariya"
    assert ctx["is_video"] is True
    assert ctx["is_document"] is False

    # Exceed capacity
    e4 = ActivityEvent(
        event_type=ActivityType.APPLICATION_OPENED,
        importance=ActivityImportance.LOW,
        application="calculator",
        window_title="Calculator",
        timestamp=1150.0
    )
    mem.record_event(e4)

    # e1 must have rolled over
    recent = mem.get_recent_events(limit=10)
    assert len(recent) == 3
    assert recent[0].application == "excel"
    assert recent[-1].application == "calculator"


# ---------------------------------------------------------------------------
# 2. SQLite Persistence & Importance Filtering Tests
# ---------------------------------------------------------------------------

def test_sqlite_persistence_importance_filtering(temp_db):
    """Verifies that LOW events remain in RAM while MEDIUM and HIGH events write to SQLite."""
    mem = ActivityMemory(db=temp_db, max_history=50)

    low_ev = ActivityEvent(
        event_type=ActivityType.USER_IDLE,
        importance=ActivityImportance.LOW,
        application="chrome",
        window_title="Idle screen",
        timestamp=time.time()
    )
    med_ev = ActivityEvent(
        event_type=ActivityType.WEBSITE_OPENED,
        importance=ActivityImportance.MEDIUM,
        application="chrome",
        window_title="GitHub - Brave",
        website="github",
        content_title="microsoft/vscode",
        timestamp=time.time()
    )
    high_ev = ActivityEvent(
        event_type=ActivityType.VIDEO_PLAYED,
        importance=ActivityImportance.HIGH,
        application="chrome",
        window_title="Interstellar - YouTube",
        website="youtube",
        content_title="Interstellar Trailer",
        timestamp=time.time()
    )

    mem.record_event(low_ev)
    mem.record_event(med_ev)
    mem.record_event(high_ev)

    # Query SQLite directly
    rows = temp_db.execute_query("SELECT * FROM proactive_activity_events ORDER BY timestamp ASC")
    assert len(rows) == 2  # Only med_ev and high_ev persisted
    event_types = [r["event_type"] for r in rows]
    assert "WEBSITE_OPENED" in event_types
    assert "VIDEO_PLAYED" in event_types
    assert "USER_IDLE" not in event_types


# ---------------------------------------------------------------------------
# 3. Temporal Queries (abhi, last, thodi_der_pehle, offset_minutes)
# ---------------------------------------------------------------------------

def test_temporal_queries_abhi_last_and_thodi_der_pehle(temp_db):
    """Verifies natural temporal queries against activity memory."""
    mem = ActivityMemory(db=temp_db)
    now = time.time()

    # 1. Video played 10 minutes ago
    e_past = ActivityEvent(
        event_type=ActivityType.VIDEO_PLAYED,
        importance=ActivityImportance.HIGH,
        application="chrome",
        window_title="Earlier Video - YouTube",
        website="youtube",
        content_title="Earlier Video",
        timestamp=now - 600
    )
    mem.record_event(e_past)

    # 2. Document edited 2 minutes ago
    e_mid = ActivityEvent(
        event_type=ActivityType.DOCUMENT_EDITED,
        importance=ActivityImportance.MEDIUM,
        application="excel",
        window_title="Budget.xlsx",
        content_title="Budget.xlsx",
        timestamp=now - 120
    )
    mem.record_event(e_mid)

    # 3. Current active video
    e_curr = ActivityEvent(
        event_type=ActivityType.VIDEO_PLAYED,
        importance=ActivityImportance.HIGH,
        application="chrome",
        window_title="Current Song - YouTube",
        website="youtube",
        content_title="Current Song",
        timestamp=now
    )
    mem.record_event(e_curr)

    # "abhi" -> returns current active event
    q_abhi = mem.query_temporal("abhi")
    assert q_abhi is not None
    assert q_abhi.content_title == "Current Song"

    # "last" -> returns the previous event
    q_last = mem.query_temporal("last")
    assert q_last is not None
    assert q_last.content_title == "Budget.xlsx"

    # "last" with website="youtube" filter -> returns previous YouTube video
    q_last_yt = mem.query_temporal("last", website="youtube")
    assert q_last_yt is not None
    assert q_last_yt.content_title == "Earlier Video"

    # "thodi_der_pehle" -> returns event active earlier (10 min ago)
    q_earlier = mem.query_temporal("thodi_der_pehle")
    assert q_earlier is not None
    assert q_earlier.content_title == "Earlier Video"


def test_temporal_queries_offset_minutes_with_sqlite_fallback(temp_db):
    """Verifies that queries for 30 minutes ago fall back to SQLite when RAM buffer has rolled over."""
    mem = ActivityMemory(db=temp_db, max_history=2)
    now = time.time()

    # Activity from 35 minutes ago (persisted in SQLite)
    e_35m = ActivityEvent(
        event_id="ev_35m",
        event_type=ActivityType.VIDEO_PLAYED,
        importance=ActivityImportance.HIGH,
        application="chrome",
        window_title="SpaceX Launch - YouTube",
        website="youtube",
        content_title="SpaceX Launch",
        timestamp=now - (35 * 60)
    )
    mem.record_event(e_35m)

    # Two more recent events that push e_35m out of the RAM deque (max_history=2)
    e_recent1 = ActivityEvent(
        event_type=ActivityType.DOCUMENT_EDITED,
        importance=ActivityImportance.MEDIUM,
        application="vscode",
        window_title="main.py",
        timestamp=now - 300
    )
    e_recent2 = ActivityEvent(
        event_type=ActivityType.WEBSITE_OPENED,
        importance=ActivityImportance.MEDIUM,
        application="chrome",
        window_title="GitHub",
        website="github",
        timestamp=now
    )
    mem.record_event(e_recent1)
    mem.record_event(e_recent2)

    # e_35m is no longer in RAM deque
    assert "ev_35m" not in [e.event_id for e in mem._events]

    # Query with offset_minutes=35 -> should retrieve from SQLite
    q_res = mem.query_temporal(offset_minutes=35, website="youtube")
    assert q_res is not None
    assert q_res.event_id == "ev_35m"
    assert q_res.content_title == "SpaceX Launch"


# ---------------------------------------------------------------------------
# 4. Observer Integration & Pruning Tests
# ---------------------------------------------------------------------------

def test_activity_observer_wires_to_memory(temp_db):
    """Verifies that ProactiveActivityObserver automatically populates ActivityMemory on observation."""
    mem = ActivityMemory(db=temp_db)
    obs = ProactiveActivityObserver(poll_interval=1.0, memory=mem)

    snap = DesktopSnapshot(
        hwnd=777,
        title="Python 3.12 Docs - Google Chrome",
        process_name="chrome"
    )

    with patch.object(obs.window_observer, "get_foreground_snapshot", return_value=snap), \
         patch.object(obs.screen_observer, "check_attention_state", return_value=(0.5, False, None)), \
         patch.object(obs.volume_observer, "check_volume_change", return_value=(False, None, None, None)):
        obs.poll_once()

    assert mem.active_event is not None
    assert mem.active_event.application == "chrome"
    assert mem.get_current_context()["application"] == "chrome"


def test_prune_history(temp_db):
    """Verifies retention pruning of historical SQLite activity records."""
    mem = ActivityMemory(db=temp_db)
    now = time.time()

    # Event from 10 days ago
    e_old = ActivityEvent(
        event_id="old_10d",
        event_type=ActivityType.WEBSITE_OPENED,
        importance=ActivityImportance.MEDIUM,
        application="chrome",
        timestamp=now - (10 * 86400)
    )
    # Event from 2 days ago
    e_new = ActivityEvent(
        event_id="new_2d",
        event_type=ActivityType.WEBSITE_OPENED,
        importance=ActivityImportance.MEDIUM,
        application="chrome",
        timestamp=now - (2 * 86400)
    )

    mem.record_event(e_old)
    mem.record_event(e_new)

    # Prune older than 7 days
    deleted = mem.prune_history(retention_days=7)
    assert deleted == 1

    rows = temp_db.execute_query("SELECT event_id FROM proactive_activity_events")
    remaining_ids = [r["event_id"] for r in rows]
    assert "old_10d" not in remaining_ids
    assert "new_2d" in remaining_ids

    # Also test `days` keyword argument alias
    mem.record_event(e_old)
    deleted_alias = mem.prune_history(days=7)
    assert deleted_alias == 1

