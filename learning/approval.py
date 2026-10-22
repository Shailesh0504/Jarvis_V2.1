# learning/approval.py
"""Human-in-the-Loop Learning Approval and Staging System for Jarvis V2."""

from dataclasses import dataclass, field
import json
import logging
import time
from typing import Any, Dict, List, Optional
import uuid
from memory.database import DatabaseManager

logger = logging.getLogger("jarvis.learning.approval")


@dataclass
class PendingLearning:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    layer: int = 2 # 1: Preferences, 2: Vocabulary, 3: Workflows, 4: Corrections, 5: Habits
    pattern_type: str = "vocabulary"
    original_key: str = ""
    proposed_val: str = ""
    confidence: float = 0.91
    status: str = "PENDING" # PENDING, ACCEPTED, REJECTED, EDITED
    prompt_text: str = "Kya main ise future ke liye yaad rakhu?"
    created_at: float = field(default_factory=time.time)


class ApprovalManager:
    """Manages staging of candidate learnings and user review lifecycle."""

    def __init__(self, db: DatabaseManager, learner: Optional[Any] = None):
        self.db = db
        self.learner = learner
        self._pending: Dict[str, PendingLearning] = {}
        self._load_pending_from_db()

    def _load_pending_from_db(self) -> None:
        try:
            sql = "SELECT id, pattern_key, pattern_type, confidence, context_data, last_seen FROM learned_patterns WHERE pattern_type LIKE 'pending_%'"
            rows = self.db.execute_query(sql)
            for r in rows:
                ctx = json.loads(r["context_data"] or "{}") if r["context_data"] else {}
                item = PendingLearning(
                    id=str(r["id"]),
                    layer=ctx.get("layer", 2),
                    pattern_type=ctx.get("pattern_type", "vocabulary"),
                    original_key=ctx.get("original_key", ""),
                    proposed_val=ctx.get("proposed_val", ""),
                    confidence=float(r["confidence"] or 0.91),
                    status=ctx.get("status", "PENDING")
                )
                self._pending[item.id] = item
        except Exception as e:
            logger.debug(f"ApprovalManager load: {e}")

    def stage_learning(
        self,
        layer: int,
        pattern_type: str,
        original_key: str,
        proposed_val: str,
        confidence: float = 0.91,
        prompt_text: str = "Kya main ise future ke liye yaad rakhu?"
    ) -> PendingLearning:
        """Stages candidate learning into the review queue."""
        item = PendingLearning(
            layer=layer,
            pattern_type=pattern_type,
            original_key=original_key.strip().lower(),
            proposed_val=proposed_val.strip(),
            confidence=confidence,
            prompt_text=prompt_text
        )
        self._pending[item.id] = item

        # Persist candidate into learned_patterns table
        ctx_json = json.dumps({
            "id": item.id,
            "layer": layer,
            "pattern_type": pattern_type,
            "original_key": item.original_key,
            "proposed_val": item.proposed_val,
            "status": "PENDING"
        })
        sql = """
        INSERT OR REPLACE INTO learned_patterns (pattern_key, pattern_type, frequency, confidence, context_data, last_seen)
        VALUES (?, ?, 0, ?, ?, ?)
        """
        pattern_key = f"pending_{item.id}"
        self.db.execute_update(sql, (pattern_key, f"pending_{pattern_type}", confidence, ctx_json, time.time()))
        logger.info(f"ApprovalManager: Staged candidate '{item.original_key}' -> '{item.proposed_val}' (Conf: {confidence*100:.0f}%) [ID: {item.id}]")
        return item

    def get_pending_learnings(self) -> List[PendingLearning]:
        return [item for item in self._pending.values() if item.status == "PENDING"]

    def get_latest_pending(self) -> Optional[PendingLearning]:
        pending = self.get_pending_learnings()
        return pending[-1] if pending else None

    def accept_learning(self, item_id: str) -> bool:
        """Approves and commits candidate to permanent memory and active layers."""
        item = self._pending.get(item_id)
        if not item:
            return False

        item.status = "ACCEPTED"

        # Apply to permanent memory & layers
        if self.learner:
            if item.layer in (2, 4) or item.pattern_type in ("vocabulary", "verbal_correction"):
                self.learner.vocabulary.learn_term(item.original_key, item.proposed_val)
                if item.original_key.lower() in ("browser", "web browser") or item.proposed_val.lower() in ("chrome", "edge", "brave", "firefox"):
                    self.learner.preferences.set("preferred_browser", item.proposed_val.lower())
                elif item.original_key.lower() in ("movie", "video", "player") or item.proposed_val.lower() in ("vlc", "wmplayer", "mpv"):
                    self.learner.preferences.set("preferred_media_player", item.proposed_val.lower())
            elif item.layer == 1 or item.pattern_type == "preference":
                self.learner.preferences.set(item.original_key, item.proposed_val)

        # Update SQLite learned_patterns table
        pattern_key = f"pending_{item_id}"
        sql = "DELETE FROM learned_patterns WHERE pattern_key = ?"
        self.db.execute_update(sql, (pattern_key,))
        logger.info(f"ApprovalManager: Accepted & committed '{item.original_key}' -> '{item.proposed_val}' into permanent memory.")
        return True

    def reject_learning(self, item_id: str) -> bool:
        """Rejects candidate and discards from staging."""
        item = self._pending.get(item_id)
        if not item:
            return False

        item.status = "REJECTED"
        pattern_key = f"pending_{item_id}"
        sql = "DELETE FROM learned_patterns WHERE pattern_key = ?"
        self.db.execute_update(sql, (pattern_key,))
        logger.info(f"ApprovalManager: Rejected candidate '{item.original_key}' [ID: {item_id}].")
        return True

    def edit_learning(self, item_id: str, new_val: str) -> bool:
        """Modifies candidate value and commits."""
        item = self._pending.get(item_id)
        if not item:
            return False

        item.proposed_val = new_val.strip()
        item.status = "EDITED"
        return self.accept_learning(item_id)
