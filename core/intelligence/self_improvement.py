# core/intelligence/self_improvement.py
"""
Authoritative Self-Improvement Engine for Jarvis V2.1 (`intelligence.self_improvement`).

Single Source of Truth (SSOT) orchestrating all 9 self-learning and adaptation capabilities:
1. Interaction Evaluation (evaluate_interaction)
2. Feedback Detection (detect_feedback)
3. Mistake Detection (detect_mistake)
4. Correction Learning (learn_correction)
5. Pattern Learning (learn_pattern)
6. Confidence Scoring (score_confidence)
7. Learning Promotion (promote_learning)
8. Learning Rollback (rollback_learning)
9. Regression Generation (generate_regression_case)

Strictly adheres to the No-Duplicate-Implementation Rule (AGENTS.md §1.1).
Consolidates and orchestrates existing subsystems:
- LearningManager (5-Layer Learning)
- ExperienceLearningSystem (Procedural, Failure, Preference, Versioned Memory)
- ApprovalManager (Candidate Staging & Promotion)
- PatternLearningEngine (Habits & Transitions)
- ExecutionDiagnosticEngine (Root Cause Derivation)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

logger = logging.getLogger("jarvis.intelligence.self_improvement")


class FeedbackType(str, Enum):
    """Categorization of detected user feedback."""
    POSITIVE_AFFIRMATION = "POSITIVE_AFFIRMATION"  # "sahi hai", "shabash", "perfect", "good job"
    SATISFACTION = "SATISFACTION"                  # "theek hai", "chalega", "works"
    NEGATIVE_COMPLAINT = "NEGATIVE_COMPLAINT"      # "galat kar diya", "tum sun nahi rahe ho", "stupid"
    DISSATISFACTION = "DISSATISFACTION"            # "nahi ye galat hai", "bekar hai", "not what I asked"
    CORRECTION = "CORRECTION"                      # "nahi, chrome nahi edge", "maine 50 bola tha"
    NEUTRAL = "NEUTRAL"                            # Ordinary turn without explicit feedback


class LearningPromotionStatus(str, Enum):
    """Lifecycle status of a learned rule or habit."""
    CANDIDATE = "CANDIDATE"      # Staged, requires evidence or confirmation
    PROMOTED = "PROMOTED"        # Promoted to active policy
    REJECTED = "REJECTED"        # Discarded during review or validation
    ROLLED_BACK = "ROLLED_BACK"  # Previously promoted, then rolled back safely


@dataclass
class RegressionCase:
    """
    Structured, replayable regression test case generated from a mistake or correction.
    Guarantees that a fixed mistake or learned preference never regresses.
    """
    case_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    query: str = ""
    expected_action: str = ""
    expected_target: str = ""
    avoid_action: Optional[str] = None
    context_requirements: Dict[str, Any] = field(default_factory=dict)
    created_from: str = "mistake_detection"  # "mistake_detection", "user_correction", "feedback"
    created_at: float = field(default_factory=time.time)
    verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "name": self.name,
            "query": self.query,
            "expected_action": self.expected_action,
            "expected_target": self.expected_target,
            "avoid_action": self.avoid_action,
            "context_requirements": dict(self.context_requirements),
            "created_from": self.created_from,
            "created_at": self.created_at,
            "verified": self.verified,
            "metadata": dict(self.metadata)
        }


class SelfImprovementEngine:
    """
    Central Authoritative Self-Improvement Engine (`intelligence.self_improvement`).
    Coordinates all 9 learning, adaptation, promotion, and regression capabilities.
    """

    # Feedback detection patterns
    FEEDBACK_PATTERNS = [
        (re.compile(r"\b(?:galat\s+kar\s+diya|tumne\s+galat\s+kiya|you\s+made\s+a\s+mistake|wrong\s+answer|hamesha\s+galat)\b", re.I), FeedbackType.NEGATIVE_COMPLAINT),
        (re.compile(r"\b(?:tum\s+sun\s+nahi\s+rahe|not\s+listening|you\s+are\s+useless|bakwas|bekar|bahut\s+slow)\b", re.I), FeedbackType.NEGATIVE_COMPLAINT),
        (re.compile(r"\b(?:nahi\s+ye\s+galat\s+hai|nahi\s+ye\s+nahi|ye\s+kya\s+hai|not\s+this|not\s+what\s+i\s+asked|ye\s+galat\s+hai|galat\s+hai|wrong)\b", re.I), FeedbackType.DISSATISFACTION),
        (re.compile(r"\b(?:sahi\s+hai|bilkul\s+sahi|perfect|excellent|shabash|great\s+job|nice\s+job|well\s+done|good\s+job|badhiya)\b", re.I), FeedbackType.POSITIVE_AFFIRMATION),
        (re.compile(r"\b(?:theek\s+hai|chalega|works|okay|ok\s+cool)\b", re.I), FeedbackType.SATISFACTION),
    ]

    def __init__(
        self,
        learning_manager: Optional[Any] = None,
        db: Optional[Any] = None,
        min_promotion_frequency: int = 3,
        min_promotion_confidence: float = 0.80
    ):
        self._lock = threading.RLock()
        self.learning_manager = learning_manager
        self.db = db
        self.min_promotion_frequency = min_promotion_frequency
        self.min_promotion_confidence = min_promotion_confidence

        # In-memory regression case catalog (backed by experience memory / db)
        self._regression_cases: Dict[str, RegressionCase] = {}
        # Rollback history tracking
        self._rollback_history: List[Dict[str, Any]] = []
        # Traceable learning event counter (per-session)
        self._event_counter: int = 0

        self._initialize_subsystems()

    def _initialize_subsystems(self) -> None:
        """Initializes or binds underlying learning subsystems."""
        if not self.learning_manager and self.db:
            try:
                from learning.learner import LearningManager
                self.learning_manager = LearningManager(db=self.db, enabled=True)
            except Exception as e:
                logger.debug("SelfImprovementEngine: LearningManager bind note: %s", e)

        # Load persisted regression cases from experience memory
        self._load_regression_cases()

    def _load_regression_cases(self) -> None:
        """Loads regression cases from the Experience Learning System if available."""
        if self.learning_manager and hasattr(self.learning_manager, "experience_system"):
            try:
                exp_sys = self.learning_manager.experience_system
                if hasattr(exp_sys, "storage"):
                    items = exp_sys.storage.get_active_items()
                    for item in items:
                        if item.category == "regression_case" and item.content:
                            c = item.content
                            case = RegressionCase(
                                case_id=item.id,
                                name=c.get("name", ""),
                                query=c.get("query", item.query_pattern),
                                expected_action=c.get("expected_action", ""),
                                expected_target=c.get("expected_target", ""),
                                avoid_action=c.get("avoid_action"),
                                context_requirements=c.get("context_requirements", {}),
                                created_from=c.get("created_from", "experience"),
                                created_at=item.created_at,
                                verified=c.get("verified", True),
                                metadata=dict(item.task_metadata)
                            )
                            self._regression_cases[case.case_id] = case
            except Exception as e:
                logger.debug("SelfImprovementEngine: Load regression cases note: %s", e)

    # -------------------------------------------------------------------------
    # 0. LEARNING EVENT ID GENERATION
    # -------------------------------------------------------------------------
    def generate_event_id(self) -> str:
        """
        Generates a traceable learning event ID in the format:
        LEARN-YYYYMMDD-NNNNNN
        e.g., LEARN-20260920-000001
        """
        with self._lock:
            self._event_counter += 1
            date_str = datetime.now().strftime("%Y%m%d")
            return f"LEARN-{date_str}-{self._event_counter:06d}"

    # -------------------------------------------------------------------------
    # 1. INTERACTION EVALUATION
    # -------------------------------------------------------------------------
    def evaluate_interaction(
        self,
        goal: str,
        steps: List[Dict[str, Any]],
        execution_results: Optional[List[Any]] = None,
        verification_results: Optional[List[Any]] = None,
        execution_context: Optional[Dict[str, Any]] = None,
        category: str = "general"
    ) -> Optional[Any]:
        """
        1. Interaction Evaluation branch.
        Evaluates task execution against verified OS state:
        - On verified success: distills procedural recipe into Experience Memory.
        - On failure: triggers mistake detection and failure avoidance memory.
        """
        if self.learning_manager and hasattr(self.learning_manager, "evaluate_outcome"):
            exp_item = self.learning_manager.evaluate_outcome(
                goal=goal,
                steps=steps,
                execution_results=execution_results,
                verification_results=verification_results,
                execution_context=execution_context,
                category=category
            )
            # If outcome was a failure, auto-generate a regression case
            is_failure = False
            if verification_results:
                is_failure = any(
                    (getattr(vr, "verified", None) is False or (isinstance(vr, dict) and vr.get("verified") is False))
                    for vr in verification_results
                )
            elif execution_results:
                is_failure = any(
                    (getattr(er, "success", None) is False or (isinstance(er, dict) and er.get("success") is False))
                    for er in execution_results
                )

            if is_failure:
                failed_step = steps[-1] if steps else {}
                self.generate_regression_case(
                    name=f"Mistake Avoidance: {goal}",
                    query=goal,
                    expected_action="verified_execution",
                    expected_target=failed_step.get("target") or goal,
                    avoid_action=failed_step.get("action", "execute"),
                    created_from="mistake_detection",
                    context_requirements=execution_context or {}
                )

            return exp_item
        return None

    # -------------------------------------------------------------------------
    # 2. FEEDBACK DETECTION
    # -------------------------------------------------------------------------
    def detect_feedback(self, raw_text: str, turn: Optional[Any] = None) -> Tuple[FeedbackType, float, Optional[str]]:
        """
        2. Feedback Detection branch.
        Scans input for positive praise, satisfaction, complaints, or dissatisfaction.
        Returns: (FeedbackType, sentiment_score [-1.0 to 1.0], matched_cue)
        """
        if not raw_text:
            return FeedbackType.NEUTRAL, 0.0, None

        cleaned = raw_text.strip()
        for pat, fb_type in self.FEEDBACK_PATTERNS:
            match = pat.search(cleaned)
            if match:
                cue = match.group(0)
                if fb_type == FeedbackType.POSITIVE_AFFIRMATION:
                    sentiment = 0.95
                elif fb_type == FeedbackType.SATISFACTION:
                    sentiment = 0.60
                elif fb_type == FeedbackType.DISSATISFACTION:
                    sentiment = -0.60
                elif fb_type == FeedbackType.NEGATIVE_COMPLAINT:
                    sentiment = -0.90
                else:
                    sentiment = 0.0

                logger.info(
                    "[SELF_IMPROVEMENT_FEEDBACK] Detected %s (cue='%s', sentiment=%.2f)",
                    fb_type.value, cue, sentiment
                )
                return fb_type, sentiment, cue

        # Check for verbal correction
        if re.search(r"\b(?:nahi|no)[,\s]+.+?\s+(?:nahi|mein|kholo|open)\b", cleaned, re.I):
            return FeedbackType.CORRECTION, -0.40, "verbal_correction_pattern"

        return FeedbackType.NEUTRAL, 0.0, None

    # -------------------------------------------------------------------------
    # 3. MISTAKE DETECTION
    # -------------------------------------------------------------------------
    def detect_mistake(
        self,
        target: str,
        action: str = "execute",
        error_msg: str = "",
        verification_result: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        3. Mistake Detection branch.
        Investigates OS execution failures and derives root cause and avoidance strategy.
        """
        if self.learning_manager and hasattr(self.learning_manager, "detect_mistake"):
            return self.learning_manager.detect_mistake(
                target=target,
                action=action,
                error_msg=error_msg,
                verification_result=verification_result
            )

        root_cause = error_msg or "Execution or verification failure"
        return {
            "root_cause": root_cause,
            "diagnostics": [error_msg] if error_msg else [],
            "suggested_recovery_strategy": "Verify target application availability and OS state before re-attempting.",
            "target": target,
            "action": action
        }

    # -------------------------------------------------------------------------
    # 4. CORRECTION LEARNING
    # -------------------------------------------------------------------------
    def learn_correction(
        self,
        text: str,
        active_context: Optional[Any] = None
    ) -> Any:
        """
        4. Correction Learning branch.
        Treats verbal corrections as high-value ground truth, updates container preferences,
        vocabulary, versioned experience memories, and auto-generates a regression case.
        """
        if not self.learning_manager:
            return None

        res = self.learning_manager.detect_correction(text, active_context=active_context)
        if getattr(res, "is_correction", False):
            # Auto-generate regression case to lock in the user's correction
            target = getattr(res, "target", "") or getattr(res, "concept", "")
            corrected_val = getattr(res, "new_value", "") or getattr(res, "preferred_container", "")
            old_val = getattr(res, "old_value", "")

            # Stamp traceable event ID
            event_id = self.generate_event_id()
            logger.info(
                "[LEARNING] event=%s type=EXPLICIT_CORRECTION scope=%s old=%s new=%s confidence=0.95 status=CONFIRMED",
                event_id,
                getattr(res, "correction_type", "USER").upper(),
                old_val or "(none)",
                corrected_val or target,
            )

            if target and corrected_val:
                self.generate_regression_case(
                    name=f"Correction: {target} -> {corrected_val}",
                    query=f"open {target}",
                    expected_action="open_container_target",
                    expected_target=f"{corrected_val}:{target}",
                    avoid_action=f"open in {old_val}" if old_val else None,
                    created_from="user_correction",
                    context_requirements={"target": target, "preferred_container": corrected_val,
                                          "learning_event_id": event_id}
                )

        return res

    # -------------------------------------------------------------------------
    # 5. PATTERN LEARNING
    # -------------------------------------------------------------------------
    def learn_pattern(
        self,
        raw_input: str,
        normalized_input: str,
        intent: Any,
        results: Optional[List[Any]] = None
    ) -> None:
        """
        5. Pattern Learning branch.
        Observes interaction to learn habits, app transitions, and repeated workflows.
        """
        if self.learning_manager and hasattr(self.learning_manager, "observe_interaction"):
            self.learning_manager.observe_interaction(raw_input, normalized_input, intent, results)

    # -------------------------------------------------------------------------
    # 6. CONFIDENCE SCORING
    # -------------------------------------------------------------------------
    def score_confidence(
        self,
        pattern_or_intent: str,
        success: bool = True,
        frequency: Optional[int] = None
    ) -> float:
        """
        6. Confidence Scoring branch.
        Computes dynamic evidence-based confidence score scaling with frequency:
        1 -> 0.35, 2 -> 0.55, 3 -> 0.70, 4 -> 0.82, 5 -> 0.88, 6+ -> >= 0.90
        Penalized by recent failures/corrections.
        """
        if self.learning_manager and hasattr(self.learning_manager, "score_confidence"):
            return self.learning_manager.score_confidence(pattern_or_intent, success=success, frequency=frequency)

        freq = frequency if frequency is not None else 1
        base = 0.35 if freq == 1 else (0.55 if freq == 2 else (0.70 if freq == 3 else min(0.95, 0.50 + freq * 0.08)))
        if not success:
            return max(0.10, round(base * 0.75, 2))
        return min(0.98, round(base, 2))

    # -------------------------------------------------------------------------
    # 7. LEARNING PROMOTION
    # -------------------------------------------------------------------------
    def promote_learning(
        self,
        item_id_or_key: str,
        frequency: int = 3,
        confidence: float = 0.85,
        force_promote: bool = False
    ) -> Tuple[bool, LearningPromotionStatus, str]:
        """
        7. Learning Promotion branch.
        Promotes a candidate learning (preference, habit, vocabulary, or workflow)
        to verified active policy only when evidence thresholds are satisfied:
        frequency >= min_promotion_frequency AND confidence >= min_promotion_confidence.
        """
        with self._lock:
            if not force_promote:
                if frequency < self.min_promotion_frequency:
                    reason = f"Insufficient frequency ({frequency} < {self.min_promotion_frequency}); remains candidate."
                    logger.info("SelfImprovementEngine: Promotion rejected for '%s': %s", item_id_or_key, reason)
                    return False, LearningPromotionStatus.CANDIDATE, reason

                if confidence < self.min_promotion_confidence:
                    reason = f"Insufficient confidence ({confidence:.2f} < {self.min_promotion_confidence:.2f}); remains candidate."
                    logger.info("SelfImprovementEngine: Promotion rejected for '%s': %s", item_id_or_key, reason)
                    return False, LearningPromotionStatus.CANDIDATE, reason

            # Delegate to ApprovalManager if an approval item exists
            if self.learning_manager and hasattr(self.learning_manager, "approval"):
                appr_mgr = self.learning_manager.approval
                if item_id_or_key in appr_mgr._pending:
                    appr_mgr.accept_learning(item_id_or_key)
                    logger.info("SelfImprovementEngine: Promoted approval item '%s' to active memory.", item_id_or_key)
                    return True, LearningPromotionStatus.PROMOTED, "Promoted successfully via ApprovalManager."

            # Update Experience item if present
            if self.learning_manager and hasattr(self.learning_manager, "experience_system"):
                exp_sys = self.learning_manager.experience_system
                items = exp_sys.storage.get_active_items()
                for item in items:
                    if item.id == item_id_or_key or item.query_pattern == item_id_or_key:
                        item.confidence = max(item.confidence, confidence)
                        item.task_metadata["promotion_status"] = LearningPromotionStatus.PROMOTED.value
                        item.task_metadata["promoted_at"] = time.time()
                        exp_sys.storage.update(item)
                        logger.info("SelfImprovementEngine: Promoted experience item '%s' (Conf: %.2f)", item.id, item.confidence)
                        return True, LearningPromotionStatus.PROMOTED, "Promoted successfully in Experience Storage."

            return True, LearningPromotionStatus.PROMOTED, "Promoted candidate to verified active status."

    # -------------------------------------------------------------------------
    # 8. LEARNING ROLLBACK
    # -------------------------------------------------------------------------
    def rollback_learning(
        self,
        item_id_or_key: str,
        reason: str = "user_reversal"
    ) -> Tuple[bool, str]:
        """
        8. Learning Rollback branch.
        Safely reverts a promoted rule, preference, or habit without raw data destruction.
        Marks the item as ROLLED_BACK with version superseding and records rollback audit.
        """
        with self._lock:
            rolled_back = False
            details = ""

            # Check Execution Preferences
            if self.learning_manager and hasattr(self.learning_manager, "exec_pref"):
                cur_pref = self.learning_manager.get_execution_preference(item_id_or_key)
                if cur_pref:
                    # Clear container preference safely
                    if hasattr(self.learning_manager, "clear_execution_preference"):
                        self.learning_manager.clear_execution_preference(item_id_or_key)
                    elif hasattr(self.learning_manager.exec_pref, "clear_target_preference"):
                        self.learning_manager.exec_pref.clear_target_preference(item_id_or_key, scope="all")
                    elif hasattr(self.learning_manager.exec_pref, "clear_preference"):
                        self.learning_manager.exec_pref.clear_preference(item_id_or_key)
                    rolled_back = True
                    details = f"Reverted execution preference for '{item_id_or_key}' (was '{cur_pref}')."

            # Check Experience System items
            if self.learning_manager and hasattr(self.learning_manager, "experience_system"):
                exp_sys = self.learning_manager.experience_system
                items = exp_sys.storage.get_active_items()
                for item in items:
                    if item.id == item_id_or_key or item.query_pattern == item_id_or_key or item.content.get("key") == item_id_or_key:
                        # Deactivate without physical row delete (versioned rollback)
                        item.is_active = False
                        item.task_metadata["rollback_reason"] = reason
                        item.task_metadata["rolled_back_at"] = time.time()
                        item.task_metadata["status"] = LearningPromotionStatus.ROLLED_BACK.value
                        exp_sys.storage.update(item)
                        rolled_back = True
                        details = f"Rolled back experience item '{item.id}' [v{item.version}]."
                        break

            # Check Approval Staging
            if self.learning_manager and hasattr(self.learning_manager, "approval"):
                appr_mgr = self.learning_manager.approval
                if item_id_or_key in appr_mgr._pending:
                    appr_mgr.reject_learning(item_id_or_key)
                    rolled_back = True
                    details = f"Discarded staged learning candidate '{item_id_or_key}'."

            if rolled_back:
                self._rollback_history.append({
                    "item_id_or_key": item_id_or_key,
                    "reason": reason,
                    "timestamp": time.time(),
                    "details": details
                })
                logger.warning("SelfImprovementEngine: Rollback executed for '%s'. Reason: %s", item_id_or_key, reason)
                return True, details

            return False, f"Item '{item_id_or_key}' not found for rollback."

    # -------------------------------------------------------------------------
    # 9. REGRESSION GENERATION
    # -------------------------------------------------------------------------
    def generate_regression_case(
        self,
        name: str,
        query: str,
        expected_action: str,
        expected_target: str,
        avoid_action: Optional[str] = None,
        created_from: str = "mistake_detection",
        context_requirements: Optional[Dict[str, Any]] = None
    ) -> RegressionCase:
        """
        9. Regression Generation branch.
        Creates and persists a structured, replayable regression case to guarantee
        that once a mistake is corrected or a preference learned, it stays fixed.
        """
        with self._lock:
            case = RegressionCase(
                name=name,
                query=query,
                expected_action=expected_action,
                expected_target=expected_target,
                avoid_action=avoid_action,
                created_from=created_from,
                context_requirements=dict(context_requirements or {})
            )
            self._regression_cases[case.case_id] = case

            # Persist into Experience Learning System as a regression item
            if self.learning_manager and hasattr(self.learning_manager, "experience_system"):
                try:
                    self.learning_manager.experience_system.storage.store_item(
                        query_pattern=query,
                        memory_type="procedural",
                        category="regression_case",
                        content=case.to_dict(),
                        task_metadata={"case_id": case.case_id, "created_from": created_from},
                        confidence=1.0
                    )
                except Exception as e:
                    logger.debug("SelfImprovementEngine: Persist regression case note: %s", e)

            logger.info(
                "[SELF_IMPROVEMENT_REGRESSION_GEN] Created regression case '%s' (query='%s', expect='%s')",
                case.name, case.query, case.expected_target
            )
            return case

    def get_regression_cases(self) -> List[RegressionCase]:
        """Retrieves all active regression cases."""
        with self._lock:
            return list(self._regression_cases.values())

    def get_rollback_history(self) -> List[Dict[str, Any]]:
        """Retrieves history of executed rollbacks."""
        with self._lock:
            return list(self._rollback_history)


# Singleton accessor
_SELF_IMPROVEMENT_ENGINE_INSTANCE: Optional[SelfImprovementEngine] = None
_SELF_IMPROVEMENT_ENGINE_LOCK = threading.Lock()


def get_self_improvement_engine(
    learning_manager: Optional[Any] = None,
    db: Optional[Any] = None
) -> SelfImprovementEngine:
    """Returns the singleton instance of SelfImprovementEngine."""
    global _SELF_IMPROVEMENT_ENGINE_INSTANCE
    if _SELF_IMPROVEMENT_ENGINE_INSTANCE is None:
        with _SELF_IMPROVEMENT_ENGINE_LOCK:
            if _SELF_IMPROVEMENT_ENGINE_INSTANCE is None:
                _SELF_IMPROVEMENT_ENGINE_INSTANCE = SelfImprovementEngine(
                    learning_manager=learning_manager,
                    db=db
                )
    elif learning_manager is not None and _SELF_IMPROVEMENT_ENGINE_INSTANCE.learning_manager is not learning_manager:
        _SELF_IMPROVEMENT_ENGINE_INSTANCE.learning_manager = learning_manager
        if db is not None:
            _SELF_IMPROVEMENT_ENGINE_INSTANCE.db = db
    return _SELF_IMPROVEMENT_ENGINE_INSTANCE
