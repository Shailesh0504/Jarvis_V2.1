# core/intelligence/learning_inspector.py
"""
Learning Inspector — Spec §20, §21, §22, §23
Handles all learning inspection, forget/rollback, metrics, and
explainability commands routed from `core/app.py`.

SSOT assignment:
  Inspection / Forget / Metrics queries → this module
  Actual rollback execution              → SelfImprovementEngine.rollback_learning()
  Actual preference clearing             → ExecutionPreferenceManager / VocabularyLayer

This module never duplicates learning logic — it only reads and delegates.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.intelligence.learning_inspector")

# ---------------------------------------------------------------------------
# Inspection command patterns (multilingual: Hindi + Hinglish + English)
# ---------------------------------------------------------------------------
_SHOW_LEARNING_RE = re.compile(
    r"\b(?:show\s+(?:my\s+)?learning|show\s+corrections?|show\s+learned?"
    r"|learning\s+(?:history|log|list)|meri?\s+learning\s+(?:dikhao|batao)"
    r"|kya\s+seekha|maine\s+kya\s+bataya|aapne\s+kya\s+seekha)\b",
    re.IGNORECASE,
)
_SHOW_PREFS_RE = re.compile(
    r"\b(?:show\s+(?:my\s+)?(?:preferences?|settings?|choices?)"
    r"|show\s+learned\s+preferences?"
    r"|show\s+(?:browser|app)\s+(?:preference|setting)"
    r"|current\s+preferences?|meri?\s+(?:pasand|preferences?)\s+(?:dikhao|batao)"
    r"|preferred\s+(?:browser|app)\s+kya\s+hai)\b",
    re.IGNORECASE,
)
_SHOW_FAILED_RE = re.compile(
    r"\b(?:show\s+failed?\s+commands?|show\s+(?:my\s+)?(?:mistakes?|errors?)"
    r"|recent\s+(?:failures?|mistakes?)"
    r"|galtiyan\s+(?:dikhao|batao)|meri?\s+galtiyan)\b",
    re.IGNORECASE,
)
_SHOW_CONFIDENCE_RE = re.compile(
    r"\b(?:show\s+(?:learning\s+)?confidence|learning\s+confidence"
    r"|confidence\s+(?:score|level))\b",
    re.IGNORECASE,
)
_EXPLAIN_RE = re.compile(
    r"\b(?:why\s+did\s+you\s+(?:do\s+that|open\s+(?:that|it)|use\s+(?:that|it))"
    r"|tumne\s+(?:ye|yeh|yeh\s+kyon|kyon)\s+(?:kiya|khola|use\s+kiya)"
    r"|yeh\s+kyun\s+kiya|tumhari?\s+reasoning\s+kya\s+(?:thi|hai)"
    r"|reason\s+(?:batao|kya\s+hai)|kaise\s+seekha|tum\s+(?:firefox|chrome|brave)\s+kyun)\b",
    re.IGNORECASE,
)
_LEARNING_STATS_RE = re.compile(
    r"\b(?:learning\s+stats?|learning\s+metrics?|learning\s+statistics"
    r"|show\s+learning\s+stats?|learning\s+report)\b",
    re.IGNORECASE,
)
_FORGET_RE = re.compile(
    r"\b(?:forget\s+(?:this\s+)?learning|bhool\s+jao|bhool\s+jao\s+ye"
    r"|learning\s+(?:hatao|delete\s+karo|remove\s+karo)"
    r"|(?P<tgt>[\w\s]+?)\s+(?:wali?\s+)?(?:preference|learning|mapping)\s+(?:bhool\s+jao|hatao|delete\s+karo)"
    r"|disable\s+learning|enable\s+learning)\b",
    re.IGNORECASE,
)
_FORGET_SPECIFIC_RE = re.compile(
    r"(?P<tgt>[\w]+)\s+(?:wali?\s+)?(?:preference|pasand|learning|mapping)\s+"
    r"(?:bhool\s+jao|hatao|delete\s+karo|remove\s+karo|mat\s+yaad\s+rakhna)",
    re.IGNORECASE,
)


class LearningMetricsCollector:
    """
    Computes learning metrics (spec §23) by querying existing tables.
    No new schema required.
    """

    def __init__(self, db: Any, learning_manager: Any = None) -> None:
        self.db = db
        self.learning_manager = learning_manager

    def get_metrics(self) -> Dict[str, Any]:
        """Returns a live snapshot of all learning metrics."""
        metrics: Dict[str, Any] = {
            "total_learning_events": 0,
            "confirmed_learning": 0,
            "active_learning": 0,
            "superseded_learning": 0,
            "rejected_learning": 0,
            "learned_vocabulary_terms": 0,
            "learned_preferences": 0,
            "learned_execution_preferences": 0,
            "total_corrections": 0,
            "repeat_error_rate": 0.0,
            "regression_cases": 0,
        }
        try:
            # Experience memories (the authoritative learning store)
            rows = self.db.execute_query(
                "SELECT COUNT(*) as cnt, "
                "SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) as active_cnt, "
                "SUM(CASE WHEN is_active=0 THEN 1 ELSE 0 END) as superseded_cnt, "
                "SUM(failure_count) as total_failures, "
                "SUM(success_count) as total_success "
                "FROM experience_memories"
            )
            if rows:
                r = rows[0]
                metrics["total_learning_events"] = int(r.get("cnt") or 0)
                metrics["active_learning"] = int(r.get("active_cnt") or 0)
                metrics["superseded_learning"] = int(r.get("superseded_cnt") or 0)
                total_fail = int(r.get("total_failures") or 0)
                total_succ = int(r.get("total_success") or 0)
                denom = total_fail + total_succ
                metrics["repeat_error_rate"] = round(total_fail / denom, 3) if denom > 0 else 0.0

            # Confirmed learning = active preference + procedural + semantic items
            rows2 = self.db.execute_query(
                "SELECT COUNT(*) as cnt FROM experience_memories "
                "WHERE is_active=1 AND memory_type IN ('preference','procedural')"
            )
            if rows2:
                metrics["confirmed_learning"] = int(rows2[0].get("cnt") or 0)

            # Vocabulary terms
            rows3 = self.db.execute_query(
                "SELECT COUNT(*) as cnt FROM entities WHERE entity_type='vocabulary'"
            )
            if rows3:
                metrics["learned_vocabulary_terms"] = int(rows3[0].get("cnt") or 0)

            # Preferences
            rows4 = self.db.execute_query(
                "SELECT COUNT(*) as cnt FROM preferences WHERE user_id='default_user' AND category='general'"
            )
            if rows4:
                metrics["learned_preferences"] = int(rows4[0].get("cnt") or 0)

            # Execution preferences
            rows5 = self.db.execute_query(
                "SELECT COUNT(*) as cnt FROM preferences WHERE user_id='default_user' AND category='execution'"
            )
            if rows5:
                metrics["learned_execution_preferences"] = int(rows5[0].get("cnt") or 0)

            # Corrections
            try:
                rows6 = self.db.execute_query(
                    "SELECT COUNT(*) as cnt FROM corrections WHERE user_id='default_user'"
                )
                if rows6:
                    metrics["total_corrections"] = int(rows6[0].get("cnt") or 0)
            except Exception:
                pass  # corrections table may not exist in all DB versions

            # Regression cases
            rows7 = self.db.execute_query(
                "SELECT COUNT(*) as cnt FROM experience_memories WHERE category='regression_case' AND is_active=1"
            )
            if rows7:
                metrics["regression_cases"] = int(rows7[0].get("cnt") or 0)

        except Exception as e:
            logger.debug("LearningMetricsCollector.get_metrics error: %s", e)

        return metrics

    def format_for_user(self, metrics: Dict[str, Any]) -> str:
        """Returns a human-readable metrics summary."""
        rate = metrics.get("repeat_error_rate", 0.0)
        rate_str = f"{rate * 100:.1f}%"
        return (
            f"📊 Learning Metrics:\n"
            f"• Total Learning Events: {metrics['total_learning_events']}\n"
            f"• Active/Confirmed: {metrics['active_learning']} | Superseded: {metrics['superseded_learning']}\n"
            f"• Vocabulary Terms Learned: {metrics['learned_vocabulary_terms']}\n"
            f"• Execution Preferences: {metrics['learned_execution_preferences']}\n"
            f"• Corrections Recorded: {metrics['total_corrections']}\n"
            f"• Regression Test Cases: {metrics['regression_cases']}\n"
            f"• Repeat Error Rate: {rate_str}"
        )


class LearningInspector:
    """
    Handles all learning inspection, explainability, forget, and metrics
    commands from the user (spec §20, §21, §22, §23).

    Integration point: called from `core/app.py._process_input()` as
    an early-check step before generic intent routing.
    """

    def __init__(
        self,
        db: Any = None,
        learning_manager: Any = None,
        self_improvement_engine: Any = None,
    ) -> None:
        self.db = db
        self.learning_manager = learning_manager
        self.sie = self_improvement_engine
        self._metrics_collector: Optional[LearningMetricsCollector] = None
        if db:
            self._metrics_collector = LearningMetricsCollector(db, learning_manager)

    def _ensure_metrics(self) -> LearningMetricsCollector:
        if not self._metrics_collector and self.db:
            self._metrics_collector = LearningMetricsCollector(self.db, self.learning_manager)
        return self._metrics_collector  # type: ignore

    # -----------------------------------------------------------------------
    # Main dispatch
    # -----------------------------------------------------------------------

    def try_handle(self, text: str, core: Any) -> Optional[str]:
        """
        Checks if `text` is a learning inspection/forget/metrics command.
        Returns a response string if handled, or None to pass through to normal routing.
        """
        cleaned = text.strip()

        # Explainability: "tumne ye kyun kiya?"
        if _EXPLAIN_RE.search(cleaned):
            return self._explain_last_action(core)

        # Learning stats/metrics
        if _LEARNING_STATS_RE.search(cleaned):
            return self._show_learning_stats()

        # Show all learning
        if _SHOW_LEARNING_RE.search(cleaned):
            return self._show_learning(core)

        # Show preferences
        if _SHOW_PREFS_RE.search(cleaned):
            return self._show_preferences(core)

        # Show failed commands
        if _SHOW_FAILED_RE.search(cleaned):
            return self._show_failed_commands()

        # Show confidence
        if _SHOW_CONFIDENCE_RE.search(cleaned):
            return self._show_confidence()

        # Forget specific learning: "Firefox wali preference bhool jao"
        forget_match = _FORGET_SPECIFIC_RE.search(cleaned)
        if forget_match:
            tgt = forget_match.group("tgt").strip().lower()
            return self._forget_learning(tgt, core)

        # Generic forget / disable / enable
        if _FORGET_RE.search(cleaned):
            if re.search(r"\bdisable\s+learning\b", cleaned, re.IGNORECASE):
                return self._toggle_learning(False, core)
            if re.search(r"\benable\s+learning\b", cleaned, re.IGNORECASE):
                return self._toggle_learning(True, core)
            return self._forget_learning(None, core)

        return None

    # -----------------------------------------------------------------------
    # Handlers
    # -----------------------------------------------------------------------

    def _show_learning(self, core: Any) -> str:
        """Lists all active learned vocabulary + execution preferences."""
        lines: List[str] = ["📚 Seekhi hui cheezein:"]

        # Vocabulary
        if self.learning_manager and hasattr(self.learning_manager, "vocabulary"):
            vocab = self.learning_manager.vocabulary.get_all_vocabulary()
            custom = {k: v for k, v in vocab.items()
                      if k not in {"browser", "movie", "video player", "media player",
                                   "recording", "code editor", "sheet", "spreadsheet"}}
            if custom:
                lines.append("\n🔤 Vocabulary Mappings (user-taught):")
                for k, v in list(custom.items())[:10]:
                    lines.append(f"  • '{k}' → '{v}'")

        # Execution preferences
        if self.learning_manager and hasattr(self.learning_manager, "exec_pref"):
            ep = self.learning_manager.exec_pref.get_all_target_preferences()
            if ep:
                lines.append("\n🌐 Execution Preferences (target → browser/container):")
                for k, v in list(ep.items())[:10]:
                    lines.append(f"  • '{k}' → '{v}'")

        # Recent corrections from experience
        corrections = self._get_recent_corrections(limit=5)
        if corrections:
            lines.append("\n✏️ Recent Corrections:")
            for c in corrections:
                lines.append(f"  • {c}")

        if len(lines) == 1:
            return "Abhi tak koi bhi specific learning save nahi ki gayi hai, Sir."

        return "\n".join(lines)

    def _show_preferences(self, core: Any) -> str:
        """Lists all persisted user preferences."""
        lines: List[str] = ["⚙️ Aapki Saved Preferences:"]

        if self.learning_manager:
            if hasattr(self.learning_manager, "preferences"):
                prefs = self.learning_manager.preferences.get_all()
                for k, v in prefs.items():
                    lines.append(f"  • {k}: {v}")

            if hasattr(self.learning_manager, "exec_pref"):
                ep = self.learning_manager.exec_pref.get_all_target_preferences()
                if ep:
                    lines.append("\n🌐 Execution Preferences:")
                    for k, v in ep.items():
                        lines.append(f"  • '{k}' always opens in '{v}'")

        if len(lines) == 1:
            return "Koi bhi preference save nahi hai abhi, Sir."
        return "\n".join(lines)

    def _show_failed_commands(self) -> str:
        """Lists recent failure patterns from experience memory."""
        if not self.db:
            return "Failure history available nahi hai abhi."
        try:
            rows = self.db.execute_query(
                "SELECT query_pattern, failure_count, content_json FROM experience_memories "
                "WHERE memory_type='failure' AND is_active=1 "
                "ORDER BY failure_count DESC, updated_at DESC LIMIT 8"
            )
            if not rows:
                return "Koi known failure pattern nahi milа, Sir. Badhiya hai!"
            lines = ["❌ Recent Failure Patterns:"]
            for r in rows:
                pat = r.get("query_pattern", "")
                fc = r.get("failure_count", 0)
                lines.append(f"  • '{pat}' — {fc} time(s) failed")
            return "\n".join(lines)
        except Exception as e:
            logger.debug("_show_failed_commands error: %s", e)
            return "Failure history retrieve karne mein samasya aayi."

    def _show_confidence(self) -> str:
        """Shows confidence scores for active learning items."""
        if not self.db:
            return "Confidence data available nahi hai."
        try:
            rows = self.db.execute_query(
                "SELECT query_pattern, confidence, memory_type FROM experience_memories "
                "WHERE is_active=1 ORDER BY confidence DESC LIMIT 8"
            )
            if not rows:
                return "Koi active learning item nahi mila."
            lines = ["📈 Learning Confidence Scores:"]
            for r in rows:
                pat = r.get("query_pattern", "")[:40]
                conf = float(r.get("confidence", 0.0))
                mtype = r.get("memory_type", "")
                bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))
                lines.append(f"  [{bar}] {conf:.2f} — {pat} ({mtype})")
            return "\n".join(lines)
        except Exception as e:
            logger.debug("_show_confidence error: %s", e)
            return "Confidence data retrieve karne mein samasya aayi."

    def _explain_last_action(self, core: Any) -> str:
        """Explains why the last action was taken using learning/context sources."""
        explanations: List[str] = []

        # Check execution preferences
        if self.learning_manager and hasattr(self.learning_manager, "exec_pref"):
            ep = self.learning_manager.exec_pref.get_all_target_preferences()
            if ep:
                pref_lines = [f"'{k}' → '{v}'" for k, v in list(ep.items())[:3]]
                explanations.append(
                    f"Aapne pehle bataया tha ki: {', '.join(pref_lines)}. "
                    f"Isliye maine usi preference ko follow kiya."
                )

        # Check vocabulary
        if self.learning_manager and hasattr(self.learning_manager, "vocabulary"):
            vocab = self.learning_manager.vocabulary.get_all_vocabulary()
            custom = {k: v for k, v in vocab.items()
                      if k not in {"browser", "movie", "video player", "media player",
                                   "recording", "code editor", "sheet", "spreadsheet"}}
            if custom:
                voc_lines = [f"'{k}' = '{v}'" for k, v in list(custom.items())[:3]]
                explanations.append(
                    f"Maine aapki vocabulary se seekha tha ki: {', '.join(voc_lines)}."
                )

        # Check regression cases
        if self.sie and hasattr(self.sie, "_regression_cases"):
            rc = list(self.sie._regression_cases.values())
            if rc:
                last_rc = rc[-1]
                explanations.append(
                    f"Ek previous correction se ek rule bana tha: '{last_rc.name}' "
                    f"(expect: {last_rc.expected_target})."
                )

        if not explanations:
            return (
                "Mujhe is baar koi specific learned preference ya correction apply nahi karni padi. "
                "Ye default behavior tha."
            )

        return "💡 Maine ye isliye kiya:\n" + "\n".join(f"  • {e}" for e in explanations)

    def _show_learning_stats(self) -> str:
        """Returns formatted learning metrics."""
        mc = self._ensure_metrics()
        if not mc:
            return "Learning metrics available nahi hain abhi."
        metrics = mc.get_metrics()
        return mc.format_for_user(metrics)

    def _forget_learning(self, target: Optional[str], core: Any) -> str:
        """
        Forgets a specific learned preference or vocabulary mapping.
        Calls SelfImprovementEngine.rollback_learning() + clears execution pref.
        Preserves audit history per spec §22.
        """
        if not self.learning_manager:
            return "Learning system available nahi hai abhi."

        if target:
            target_clean = target.strip().lower()
            reverted = False
            messages: List[str] = []

            # 1. Clear execution preference (e.g. "firefox" as preferred browser for a target)
            if hasattr(self.learning_manager, "exec_pref"):
                current_pref = self.learning_manager.exec_pref.get_target_preference(target_clean)
                if current_pref:
                    self.learning_manager.exec_pref.clear_target_preference(target_clean, scope="all")
                    messages.append(f"Execution preference '{target_clean}' → '{current_pref}' clear kar diya.")
                    reverted = True

            # 2. Clear vocabulary mapping
            if hasattr(self.learning_manager, "vocabulary"):
                existing = self.learning_manager.vocabulary.get_term(target_clean)
                if existing:
                    # Reset to default or remove
                    try:
                        self.learning_manager.vocabulary.learn_term(target_clean, "", category="forgotten")
                        messages.append(f"Vocabulary mapping '{target_clean}' → '{existing}' bhool gaya.")
                        reverted = True
                    except Exception as e:
                        logger.debug("forget vocabulary error: %s", e)

            # 3. Delegate to SelfImprovementEngine rollback
            if self.sie:
                ok, detail = self.sie.rollback_learning(target_clean, reason="user_forget_command")
                if ok:
                    messages.append(detail)
                    reverted = True

            # 4. Clear general preference key
            if hasattr(self.learning_manager, "preferences"):
                pref_val = self.learning_manager.preferences.get(target_clean)
                if pref_val is not None:
                    self.learning_manager.preferences.set(target_clean, "")
                    messages.append(f"Preference '{target_clean}' = '{pref_val}' reset kar diya.")
                    reverted = True

            if reverted:
                logger.info(
                    "[LEARNING] type=FORGET target='%s' details=%s",
                    target_clean,
                    "; ".join(messages)
                )
                return (
                    f"Theek hai Sir. '{target_clean}' se related learning bhool gaya hoon. "
                    f"Audit history preserved hai.\n"
                    + "\n".join(f"  • {m}" for m in messages)
                )
            else:
                return f"Sir, '{target_clean}' ke liye koi saved learning nahi mili jo main bhool sakun."
        else:
            # Generic forget latest
            if self.sie:
                cases = self.sie.get_regression_cases()
                if cases:
                    last_case = cases[-1]
                    self.sie.rollback_learning(last_case.case_id, reason="user_forget_command")
                    return f"Theek hai Sir, sabse recent learning '{last_case.name}' bhool gaya hoon."
            return "Koi specific cheez nahi mili jo main bhool sakun. Please specify karein, jaise: 'Firefox wali preference bhool jao'."

    def _toggle_learning(self, enable: bool, core: Any) -> str:
        """Enables or disables the learning system."""
        if self.learning_manager:
            self.learning_manager.enabled = enable
            state = "enable" if enable else "disable"
            logger.info("LearningInspector: Learning %sd by user command.", state)
            if enable:
                return "Theek hai Sir. Learning system ab active hai."
            return "Theek hai Sir. Learning system temporarily disabled kar diya. Next restart par phir se active ho jayega."
        return "Learning manager available nahi hai."

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _get_recent_corrections(self, limit: int = 5) -> List[str]:
        """Returns human-readable summaries of recent corrections."""
        result: List[str] = []
        if not self.db:
            return result
        try:
            rows = self.db.execute_query(
                "SELECT concept, original_value, corrected_value, occurrences "
                "FROM corrections WHERE user_id='default_user' "
                "ORDER BY last_updated DESC LIMIT ?",
                (limit,)
            )
            for r in rows:
                result.append(
                    f"'{r.get('original_value')}' → '{r.get('corrected_value')}' "
                    f"(concept: {r.get('concept')}, {r.get('occurrences')} time(s))"
                )
        except Exception as e:
            logger.debug("_get_recent_corrections error: %s", e)
        return result


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------
_INSPECTOR_INSTANCE: Optional[LearningInspector] = None
_INSPECTOR_LOCK = __import__("threading").Lock()


def get_learning_inspector(
    db: Any = None,
    learning_manager: Any = None,
    self_improvement_engine: Any = None,
) -> LearningInspector:
    """Returns the singleton LearningInspector, initializing on first call."""
    global _INSPECTOR_INSTANCE
    if _INSPECTOR_INSTANCE is None:
        with _INSPECTOR_LOCK:
            if _INSPECTOR_INSTANCE is None:
                _INSPECTOR_INSTANCE = LearningInspector(
                    db=db,
                    learning_manager=learning_manager,
                    self_improvement_engine=self_improvement_engine,
                )
    else:
        # Wire in components if not yet set
        if db is not None and _INSPECTOR_INSTANCE.db is None:
            _INSPECTOR_INSTANCE.db = db
            _INSPECTOR_INSTANCE._metrics_collector = LearningMetricsCollector(db, learning_manager)
        if learning_manager is not None and _INSPECTOR_INSTANCE.learning_manager is None:
            _INSPECTOR_INSTANCE.learning_manager = learning_manager
        if self_improvement_engine is not None and _INSPECTOR_INSTANCE.sie is None:
            _INSPECTOR_INSTANCE.sie = self_improvement_engine
    return _INSPECTOR_INSTANCE
