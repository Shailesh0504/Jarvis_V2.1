# core/experience/log_learner.py
"""
Automated Mistake Ingestion & Reflection Engine for Jarvis V2.
Reads machine-readable structured mistake logs (logs/jarvis_mistakes.jsonl),
distills failure anti-patterns and avoidance advice into persistent Experience Memory,
and generates conversational reflections on lessons learned.
"""

from collections import Counter
import logging
from typing import Any, Dict, List, Optional

from core.logger import MistakeLogWriter, get_mistake_logger
from .evaluator import OutcomeEvaluator
from .models import ExperienceItem, MemoryType
from .safeguards import ExperienceSafeguards
from .storage import ExperienceStorageManager

logger = logging.getLogger("jarvis.experience.log_learner")


class LogLearningEngine:
    """
    Consumes structured mistake logs and embeds reusable failure lessons
    into long-term Experience Memory so Jarvis systematically learns from past mistakes.
    """

    def __init__(
        self,
        storage: Optional[ExperienceStorageManager] = None,
        evaluator: Optional[OutcomeEvaluator] = None,
        safeguards: Optional[ExperienceSafeguards] = None,
        log_writer: Optional[MistakeLogWriter] = None
    ):
        self.storage = storage or ExperienceStorageManager()
        self.evaluator = evaluator or OutcomeEvaluator()
        self.safeguards = safeguards or ExperienceSafeguards()
        self.log_writer = log_writer or get_mistake_logger()

    def digest_mistakes(self, limit: int = 50) -> List[ExperienceItem]:
        """
        Reads pending unlearned mistake entries from the JSONL log,
        evaluates each failure, stores them into SQLite experience memory,
        and marks them as DIGESTED.
        """
        unlearned = self.log_writer.get_unlearned_mistakes(limit=limit)
        if not unlearned:
            logger.debug("LogLearningEngine: No pending unlearned mistakes in log.")
            return []

        digested_items: List[ExperienceItem] = []
        digested_ids: List[str] = []

        for record in unlearned:
            log_id = record.get("log_id")
            goal = record.get("user_query") or record.get("normalized_query") or "unknown command"
            error_msg = record.get("error_message") or "Unknown error"
            category = record.get("category") or "general"
            diagnosis = record.get("diagnosis") or record.get("error_type") or "execution_failure"

            attempted_action = record.get("attempted_action") or "execute"
            failing_mod = record.get("failing_module") or "system"
            failed_step = {
                "plugin": failing_mod,
                "action": attempted_action,
                "parameters": record.get("action_parameters", {})
            }

            try:
                item = self.evaluator.evaluate_failed_task(
                    goal=goal,
                    failed_step=failed_step,
                    error_msg=error_msg,
                    attempted_strategy="primary",
                    category=category,
                    diagnosis=diagnosis
                )

                if item and not self.safeguards.is_pollution(item):
                    # Enrich with anti_pattern and recommended fix if available in log record
                    if record.get("anti_pattern") and isinstance(item.content, dict):
                        item.content["anti_pattern"] = record["anti_pattern"]
                    if record.get("recommended_fix") and isinstance(item.content, dict):
                        item.content["recommended_fix"] = record["recommended_fix"]
                    if record.get("turn_id"):
                        item.task_metadata["turn_id"] = record["turn_id"]

                    self.storage.save_item(item)
                    digested_items.append(item)

                if log_id:
                    digested_ids.append(log_id)
            except Exception as exc:
                logger.error("Error evaluating mistake log record %s: %s", log_id, exc)
                # Mark as digested anyway to avoid infinite stuck loops on corrupted records
                if log_id:
                    digested_ids.append(log_id)

        if digested_ids:
            self.log_writer.mark_as_digested(digested_ids)
            logger.info("LogLearningEngine: Successfully digested %d mistakes into long-term Experience Memory.", len(digested_items))

        return digested_items

    def get_learned_mistakes_summary(self, limit: int = 5) -> Dict[str, Any]:
        """
        Aggregates recent failure experiences and logs into a structured reflection report
        and conversational natural Hinglish explanation.
        """
        all_logs = self.log_writer.get_all_mistakes(limit=100)
        unlearned_count = len([l for l in all_logs if l.get("learned_status") == "PENDING"])
        digested_count = len([l for l in all_logs if l.get("learned_status") == "DIGESTED"])

        # Fetch failure experiences from SQLite database
        all_failures = self.storage.get_active_items(memory_type=MemoryType.FAILURE)
        failure_items = all_failures[:limit]

        # Categorize top failure modes
        cat_counter = Counter([l.get("category", "other") for l in all_logs])
        top_categories = dict(cat_counter.most_common(3))

        lessons: List[Dict[str, Any]] = []
        for itm in failure_items:
            content = itm.content if isinstance(itm.content, dict) else {}
            lessons.append({
                "goal": itm.query_pattern,
                "category": itm.category,
                "failed_action": content.get("failed_action", "action"),
                "error": content.get("error", ""),
                "root_cause": content.get("root_cause", ""),
                "avoidance_strategy": content.get("avoidance_strategy") or content.get("recommended_fix") or "Avoid repeated execution without verifying prerequisites."
            })

        # Formulate conversational Hinglish spoken summary
        if not lessons:
            spoken_summary = (
                "Boss, abhi tak maine system log me koi naya failure record nahi kiya hai. "
                "Main har turn ke outcome ko monitor kar raha hoon taaki aage aane wali galtiyon se seekh sakun."
            )
        else:
            lesson_bullets = []
            for i, l in enumerate(lessons[:3], start=1):
                advice = l['avoidance_strategy']
                if len(advice) > 80:
                    advice = advice[:77] + "..."
                lesson_bullets.append(f"{i}. '{l['goal']}' ke dauran: {advice}")
            spoken_summary = (
                f"Boss, maine recent logs se {len(lessons)} galtiyan analyze ki hain: "
                + " ".join(lesson_bullets)
                + " Ab main in scenarios me pehle check karta hoon taaki repeat mistake na ho."
            )

        return {
            "total_mistakes_logged": len(all_logs),
            "digested_mistakes_count": digested_count,
            "pending_unlearned_count": unlearned_count,
            "top_categories": top_categories,
            "lessons": lessons,
            "spoken_summary": spoken_summary
        }
