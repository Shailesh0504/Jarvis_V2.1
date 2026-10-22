# memory/episodic.py
"""Episodic Memory Tier: Chronological timeline of past interactions, events, and tool outcomes."""

import json
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from .database import DatabaseManager

logger = logging.getLogger("jarvis.memory.episodic")


class EpisodicMemory:
    """Stores and recalls chronological event sequences of what occurred previously."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def record(
        self,
        user_input: str,
        response: str,
        intent: Optional[str] = None,
        source: str = "cli",
        session_id: Optional[str] = None,
        execution_results: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """Records an episodic interaction turn in the timeline."""
        turn_id = str(uuid.uuid4())
        sess = session_id or "default_session"
        now = time.time()
        meta_str = json.dumps(execution_results or [])

        # User event
        sql_user = """
        INSERT INTO conversations (session_id, user_id, turn_id, role, content, intent, source, metadata, timestamp)
        VALUES (?, 'default_user', ?, 'user', ?, ?, ?, ?, ?)
        """
        self.db.execute_update(sql_user, (sess, turn_id, user_input, intent or "", source, meta_str, now))

        # Assistant event
        sql_asst = """
        INSERT INTO conversations (session_id, user_id, turn_id, role, content, intent, source, metadata, timestamp)
        VALUES (?, 'default_user', ?, 'assistant', ?, ?, ?, ?, ?)
        """
        self.db.execute_update(sql_asst, (sess, turn_id, response, intent or "", source, meta_str, now + 0.001))

        # Record plugin usage details
        if execution_results:
            for item in execution_results:
                self.record_plugin_usage(
                    plugin_name=item.get("plugin", "system"),
                    action_name=item.get("action", "execute"),
                    success=item.get("success", True),
                    result_summary=str(item.get("data", "")),
                    error=item.get("error")
                )

    def record_plugin_usage(
        self,
        plugin_name: str,
        action_name: str,
        task_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        success: bool = True,
        result_summary: str = "",
        error: Optional[str] = None,
        execution_time_ms: float = 0.0
    ) -> None:
        sql = """
        INSERT INTO plugin_usage (plugin_name, action_name, task_id, parameters_json, success, result_summary, error, execution_time_ms, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params_str = json.dumps(parameters or {})
        self.db.execute_update(
            sql,
            (plugin_name, action_name, task_id or "", params_str, 1 if success else 0, result_summary[:500], error or "", execution_time_ms, time.time())
        )

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns recent conversation turns paired together."""
        sql = """
        SELECT turn_id, session_id, role, content, intent, timestamp
        FROM conversations
        ORDER BY timestamp DESC
        LIMIT ?
        """
        rows = self.db.execute_query(sql, (limit * 2,))
        turns_dict: Dict[str, Dict[str, Any]] = {}

        for r in rows:
            tid = r["turn_id"]
            if tid not in turns_dict:
                turns_dict[tid] = {
                    "id": tid,
                    "session_id": r["session_id"],
                    "user_input": "",
                    "assistant_response": "",
                    "intent": r["intent"],
                    "timestamp": r["timestamp"]
                }
            if r["role"] == "user":
                turns_dict[tid]["user_input"] = r["content"]
            elif r["role"] == "assistant":
                turns_dict[tid]["assistant_response"] = r["content"]

        # Sort turns by timestamp descending
        sorted_turns = sorted(turns_dict.values(), key=lambda x: x["timestamp"], reverse=True)
        return sorted_turns[:limit]

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches past conversation history for keywords."""
        sql = """
        SELECT id, session_id, role, content, intent, timestamp
        FROM conversations
        WHERE content LIKE ?
        ORDER BY timestamp DESC
        LIMIT ?
        """
        wildcard = f"%{query}%"
        return self.db.execute_query(sql, (wildcard, limit))
