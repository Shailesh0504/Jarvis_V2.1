# memory/short_term.py
"""Short-Term Memory Tier: Active conversation window and session turn buffer."""

import json
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from .database import DatabaseManager

logger = logging.getLogger("jarvis.memory.short_term")


class ShortTermMemory:
    """Manages active conversation turns, sliding window buffer, and conversation transcripts."""

    def __init__(self, db: DatabaseManager, window_size: int = 10):
        self.db = db
        self.window_size = window_size
        self._active_turns: List[Dict[str, Any]] = []

    def record_turn(
        self,
        session_id: str,
        user_input: str,
        assistant_response: str,
        intent: Optional[str] = None,
        source: str = "cli",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Stores user input and assistant response into conversations table and active buffer."""
        turn_id = str(uuid.uuid4())
        now = time.time()
        meta_str = json.dumps(metadata or {})

        # Insert user message
        sql_user = """
        INSERT INTO conversations (session_id, user_id, turn_id, role, content, intent, source, metadata, timestamp)
        VALUES (?, 'default_user', ?, 'user', ?, ?, ?, ?, ?)
        """
        self.db.execute_update(sql_user, (session_id, turn_id, user_input, intent or "", source, meta_str, now))

        # Insert assistant message
        sql_assistant = """
        INSERT INTO conversations (session_id, user_id, turn_id, role, content, intent, source, metadata, timestamp)
        VALUES (?, 'default_user', ?, 'assistant', ?, ?, ?, ?, ?)
        """
        self.db.execute_update(sql_assistant, (session_id, turn_id, assistant_response, intent or "", source, meta_str, now + 0.001))

        # Update in-memory sliding buffer
        self._active_turns.append({"role": "user", "content": user_input, "intent": intent})
        self._active_turns.append({"role": "assistant", "content": assistant_response, "intent": intent})

        if len(self._active_turns) > (self.window_size * 2):
            self._active_turns = self._active_turns[-(self.window_size * 2):]

    def get_conversation_history(self, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """Returns recent turns for LLM prompt context injection."""
        lim = limit or self.window_size
        if len(self._active_turns) >= (lim * 2):
            return [{"role": t["role"], "content": t["content"]} for t in self._active_turns[-(lim * 2):]]

        # Fallback to DB
        sql = """
        SELECT role, content FROM conversations
        ORDER BY timestamp DESC
        LIMIT ?
        """
        rows = self.db.execute_query(sql, (lim * 2,))
        rows.reverse()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def clear_active_session(self) -> None:
        self._active_turns.clear()
