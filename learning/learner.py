# learning/learner.py
"""Unified 5-Layer Learning Manager for Jarvis V2."""

import logging
from typing import Any, Dict, List, Optional

from core.intent import Intent
from memory.database import DatabaseManager
from .preferences_layer import PreferencesLayer
from .vocabulary_layer import VocabularyLayer
from .workflow_layer import WorkflowLayer
from .corrections_layer import CorrectionsLayer, CorrectionResult
from .habit_layer import HabitLayer
from .sequence_miner import SequenceMiner, WorkflowProposal
from .approval import ApprovalManager, PendingLearning
from .execution_preference import ExecutionPreferenceManager

logger = logging.getLogger("jarvis.learning")


class LearningManager:
    """Central orchestrator for the 5 Layers of Learning."""

    def __init__(self, db: DatabaseManager, enabled: bool = True, min_habit_frequency: int = 3, event_bus: Optional[Any] = None):
        self.enabled = enabled
        self.db = db
        self.event_bus = event_bus

        # Layer 1: Preferences
        self.preferences = PreferencesLayer(self.db)

        # Layer 2: Vocabulary
        self.vocabulary = VocabularyLayer(self.db)

        # Layer 3: Workflows
        self.workflows = WorkflowLayer(self.db)

        # Layer 4: Corrections
        self.corrections = CorrectionsLayer(self.db, self.vocabulary, self.preferences)

        # Layer 5: Habits & Suggestions
        self.habits = HabitLayer(self.db, min_habit_frequency=min_habit_frequency)

        # Sequence Miner for Proactive Workflow Automation
        self.miner = SequenceMiner(min_chain_length=3, min_frequency=2)

        # Human-in-the-Loop Learning Approval Manager
        self.approval = ApprovalManager(self.db, self)

        # Learning Communication Engine (LCE)
        from .communication_engine import LearningCommunicationEngine
        self.lce = LearningCommunicationEngine(self.db, enabled=self.enabled)

        # Persistent Experience Learning System
        from core.experience import ExperienceLearningSystem
        self.experience_system = ExperienceLearningSystem(db_or_path=self.db)

        # Execution Preference Memory (per-target container/browser preferences)
        self.exec_pref = ExecutionPreferenceManager(self.db)

        # Proactive Pattern Learning Engine
        from core.intelligence.pattern_engine import PatternLearningEngine
        self.pattern_engine = PatternLearningEngine(db=self.db)

        # Execution Diagnostic Engine (Mistake Detection)
        from core.execution.diagnostics import ExecutionDiagnosticEngine
        self.diagnostic_engine = ExecutionDiagnosticEngine()

        # Authoritative Self-Improvement Engine (intelligence.self_improvement)
        from core.intelligence.self_improvement import SelfImprovementEngine
        self.self_improvement = SelfImprovementEngine(learning_manager=self, db=self.db)

        logger.info("5-Layer LearningManager and Experience System successfully initialized.")

    def observe_interaction(
        self,
        raw_input: str,
        normalized_input: str,
        intent: Intent,
        results: Optional[List[Any]] = None
    ) -> None:
        """Called on every turn to learn habits and usage patterns."""
        if not self.enabled:
            return

        # Track habitual command frequencies in Layer 5
        if intent.name and intent.name != "chat":
            context = {
                "entities": intent.entities,
                "target_plugin": intent.target_plugin,
                "target_action": intent.target_action
            }
            self.habits.observe(intent.name, context_details=context)

    def process_correction(self, text: str) -> CorrectionResult:
        """Processes potential verbal correction in Layer 4 and updates Experience System."""
        return self.detect_correction(text)

    # ------------------------------------------------------------------
    # Authoritative Self-Improvement & Feedback Layer APIs
    # ------------------------------------------------------------------

    def evaluate_outcome(
        self,
        goal: str,
        steps: List[Dict[str, Any]],
        execution_results: Optional[List[Any]] = None,
        verification_results: Optional[List[Any]] = None,
        execution_context: Optional[Dict[str, Any]] = None,
        category: str = "general",
    ) -> Optional[Any]:
        """
        Outcome Evaluation & Mistake Detection branch.
        Analyzes executed actions against verified OS state:
        - On verified success: distills parameterized procedural recipe into Experience Memory.
        - On failure or unverified execution: investigates root causes with Diagnostic Engine,
          distills failure anti-pattern, and saves avoidance advice to prevent repeating mistakes.
        """
        if not self.enabled:
            return None

        # Determine true success: verification results override raw execution results
        is_verified = True
        error_msg = ""
        failed_step = steps[-1] if steps else {"plugin": category or "system", "action": "execute"}

        if verification_results:
            for vr in verification_results:
                v_ok = getattr(vr, "verified", None)
                if v_ok is None and isinstance(vr, dict):
                    v_ok = vr.get("verified", True)
                if v_ok is False:
                    is_verified = False
                    error_msg = (
                        getattr(vr, "error", None)
                        or getattr(vr, "reason", None)
                        or getattr(vr, "message", None)
                        or getattr(vr, "failure_reason", None)
                        or getattr(vr, "error_details", None)
                        or (vr.get("error") or vr.get("failure_reason") if isinstance(vr, dict) else "Verification check failed")
                    )
                    break

        if is_verified and execution_results:
            for er in execution_results:
                s_ok = getattr(er, "success", None)
                if s_ok is None and isinstance(er, dict):
                    s_ok = er.get("success", True)
                if s_ok is False:
                    is_verified = False
                    error_msg = (
                        getattr(er, "error", None)
                        or getattr(er, "reason", None)
                        or (er.get("error") if isinstance(er, dict) else "Action execution failed")
                    )
                    break

        if not verification_results and not execution_results:
            if execution_context and "success" in execution_context:
                is_verified = bool(execution_context["success"])
                if not is_verified:
                    error_msg = str(execution_context.get("error", "Task execution failed"))

        if is_verified:
            # 1. Distill and store procedural experience
            exp_item = self.experience_system.record_task_success(
                goal=goal,
                steps=steps,
                execution_context=execution_context,
                category=category
            )
            # 2. Record sequence step for workflow discovery
            for s in steps:
                self.record_action_step(
                    plugin=s.get("plugin") or s.get("plugin_name", ""),
                    action=s.get("action") or s.get("action_name", ""),
                    parameters=s.get("parameters"),
                    description=s.get("description", "")
                )
            logger.info("Feedback Layer: Evaluated verified task success for goal '%s'", goal)
            return exp_item
        else:
            # Mistake Detection & Failure Anti-Pattern Recording
            diagnosis_report = self.detect_mistake(
                target=failed_step.get("target") or goal,
                action=failed_step.get("action", "execute"),
                error_msg=error_msg,
                verification_result=verification_results[0] if verification_results else None
            )
            root_cause = diagnosis_report.get("root_cause", "execution_failure")
            exp_item = self.experience_system.record_task_failure(
                goal=goal,
                failed_step=failed_step,
                error_msg=error_msg or "Execution or verification failed",
                category=category,
                diagnosis=root_cause
            )
            logger.warning(
                "Feedback Layer: Mistake detected for goal '%s'. Root cause: %s. Failure memory recorded.",
                goal, root_cause
            )
            return exp_item

    def detect_correction(
        self,
        text: str,
        active_context: Optional[Any] = None
    ) -> CorrectionResult:
        """
        Correction Detection branch.
        Detects explicit verbal corrections, browser/app preferences, and synonym mappings.
        Treats user corrections as high-value ground truth, updating Execution Preferences,
        Vocabulary, and recording versioned experience memories without destructive overwrites.
        """
        if not self.enabled:
            return CorrectionResult(is_correction=False)

        res = self.corrections.parse_and_apply_correction(text)
        if res.is_correction:
            # Contextual Target Resolution:
            # If user said "nahi, brave mein kholo" without naming the target entity,
            # resolve target from active context (e.g. active website "youtube").
            if res.preferred_container and not res.target and active_context:
                inferred_target = (
                    getattr(active_context, "website", None)
                    or getattr(active_context, "application", None)
                    or getattr(active_context, "last_entity", None)
                    or getattr(active_context, "last_media_source", None)
                    or ""
                )
                if inferred_target:
                    res.target = inferred_target
                    res.concept = inferred_target

            # Save container preference if browser preference identified
            if res.target and res.preferred_container:
                self.set_execution_preference(res.target, res.preferred_container)
                logger.info(
                    "Feedback Layer: Learned container preference '%s' -> '%s'",
                    res.target, res.preferred_container
                )

            # Record versioned correction in Experience System (safeguards handle contradiction/versioning)
            if hasattr(self, "experience_system") and self.experience_system:
                self.experience_system.record_user_correction(
                    concept=res.concept or res.target or "user_correction",
                    old_value=res.old_value,
                    new_value=res.new_value or res.preferred_container,
                    context=text
                )

            if self.event_bus:
                from core.event_bus import LearningDetected
                self.event_bus.emit_domain_event(
                    LearningDetected(
                        layer=4,
                        pattern_type="verbal_correction",
                        details={
                            "target": res.target,
                            "original": res.old_value,
                            "corrected": res.new_value or res.preferred_container,
                            "concept": res.concept
                        }
                    )
                )

        return res

    def detect_mistake(
        self,
        target: str,
        action: str = "execute",
        error_msg: str = "",
        verification_result: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Mistake Detection branch.
        Uses the ExecutionDiagnosticEngine to investigate why an operation failed on the OS.
        """
        clean_target = str(target or "").strip()
        findings: List[str] = []
        root_cause = "Unknown failure"
        suggested_recovery = ""

        if verification_result:
            v_reason = (
                getattr(verification_result, "error", None)
                or getattr(verification_result, "reason", None)
                or getattr(verification_result, "message", None)
                or getattr(verification_result, "failure_reason", None)
                or (
                    (verification_result.get("error") or verification_result.get("failure_reason") or verification_result.get("message"))
                    if isinstance(verification_result, dict) else ""
                )
            )
            v_err = getattr(verification_result, "error_details", None) or (
                verification_result.get("error_details") if isinstance(verification_result, dict) else ""
            )
            if v_reason:
                findings.append(f"Verification failure: {v_reason}")
                root_cause = f"{v_reason}"
            if v_err:
                findings.append(f"Verification error detail: {v_err}")

        if hasattr(self, "diagnostic_engine") and self.diagnostic_engine:
            try:
                # If target is a folder/path operation
                report = self.diagnostic_engine.diagnose_folder_operation(
                    target=clean_target,
                    raw_error=error_msg
                )
                if report.failure_identified:
                    root_cause = report.root_cause
                    findings.extend(report.diagnostics)
                    suggested_recovery = report.suggested_recovery_strategy
            except Exception as e:
                logger.debug("Diagnostic engine inspection note: %s", e)

        if not findings and error_msg:
            findings.append(error_msg[:300])
            root_cause = "action_execution_error"

        return {
            "root_cause": root_cause,
            "diagnostics": findings,
            "suggested_recovery_strategy": suggested_recovery,
            "target": clean_target,
            "action": action
        }

    def learn_pattern(
        self,
        raw_input: str,
        normalized_input: str,
        intent: Any,
        results: Optional[List[Any]] = None
    ) -> None:
        """
        Pattern Learning branch.
        Observes interaction to learn habits, app transitions, and repeated workflows.
        """
        self.observe_interaction(raw_input, normalized_input, intent, results)

    def score_confidence(
        self,
        pattern_or_intent: str,
        success: bool = True,
        frequency: Optional[int] = None
    ) -> float:
        """
        Confidence Scoring branch.
        Calculates evidence-based dynamic confidence:
        1 occurrence  -> 0.35
        2 occurrences -> 0.55
        3 occurrences -> 0.70
        4 occurrences -> 0.82
        5 occurrences -> 0.88
        6+ occurrences -> 0.90 to 0.95
        Penalized by recent failures/corrections.
        """
        freq = frequency if frequency is not None else 1
        if hasattr(self, "pattern_engine") and self.pattern_engine:
            base_conf = self.pattern_engine.calculate_confidence(freq)
        else:
            base_conf = 0.50 if freq <= 2 else min(0.95, 0.50 + (freq * 0.08))

        if not success:
            # Penalize confidence on failed or corrected operation
            calibrated = max(0.10, round(base_conf * 0.75, 2))
        else:
            calibrated = min(0.98, base_conf)

        return calibrated

    def promote_learning(self, item_id_or_key: str, frequency: int = 3, confidence: float = 0.85, force_promote: bool = False):
        """Delegates promotion evaluation to authoritative SelfImprovementEngine."""
        return self.self_improvement.promote_learning(item_id_or_key, frequency=frequency, confidence=confidence, force_promote=force_promote)

    def rollback_learning(self, item_id_or_key: str, reason: str = "user_reversal"):
        """Delegates rollback to authoritative SelfImprovementEngine."""
        return self.self_improvement.rollback_learning(item_id_or_key, reason=reason)

    def generate_regression_case(self, name: str, query: str, expected_action: str, expected_target: str, **kwargs):
        """Delegates regression generation to authoritative SelfImprovementEngine."""
        return self.self_improvement.generate_regression_case(name=name, query=query, expected_action=expected_action, expected_target=expected_target, **kwargs)

    def detect_feedback(self, raw_text: str):
        """Delegates feedback detection to authoritative SelfImprovementEngine."""
        return self.self_improvement.detect_feedback(raw_text)

    def resolve_vocabulary(self, text: str) -> str:
        """Applies learned user vocabulary mappings in Layer 2."""
        if not self.enabled:
            return text
        return self.vocabulary.resolve_text(text)

    def check_workflow_match(self, text: str) -> Optional[Dict[str, Any]]:
        """Checks for composite macro triggers in Layer 3."""
        if not self.enabled:
            return None
        return self.workflows.match_workflow(text)

    def get_proactive_suggestion(self, trigger_query: str) -> Optional[str]:
        """Queries Layer 5 for habit-based proactive recommendations."""
        if not self.enabled:
            return None
        sug = self.habits.get_proactive_suggestion(trigger_query)
        if sug and self.event_bus:
            from core.event_bus import SuggestionCreated
            self.event_bus.emit_domain_event(
                SuggestionCreated(text=sug, confidence=0.9)
            )
        return sug

    def record_action_step(self, plugin: str, action: str, parameters: Optional[Dict[str, Any]] = None, description: str = "") -> None:
        """Feeds individual executed steps into the sequence miner."""
        if not self.enabled:
            return
        self.miner.record_step(plugin=plugin, action=action, parameters=parameters, description=description)

    def check_for_workflow_proposal(self) -> Optional[WorkflowProposal]:
        """Checks if a repeated multi-step workflow chain has been discovered."""
        if not self.enabled:
            return None
        prop = self.miner.detect_proposal()
        if prop and self.event_bus:
            from core.event_bus import SuggestionCreated
            self.event_bus.emit_domain_event(
                SuggestionCreated(text=prop.prompt_text, confidence=0.95)
            )
        return prop

    def confirm_workflow_proposal(self, proposal: WorkflowProposal) -> Dict[str, Any]:
        """Synthesizes and registers the newly confirmed workflow into Layer 3 (Workflows) and SQLite."""
        self.workflows.register_workflow(
            name=proposal.name,
            description=f"Auto-synthesized workflow: {proposal.display_title}",
            trigger_phrases=proposal.trigger_phrases,
            steps=proposal.steps
        )
        self.miner.clear()
        logger.info(f"LearningManager: Synthesized new workflow '{proposal.name}' with {len(proposal.steps)} steps.")
        return {
            "name": proposal.name,
            "title": proposal.display_title,
            "trigger_phrases": proposal.trigger_phrases,
            "steps_count": len(proposal.steps)
        }

    # Backward compatibility helper methods
    def register_correction(self, original: str, correction: str) -> None:
        self.vocabulary.learn_term(original, correction)

    def get_correction_for(self, phrase: str) -> Optional[str]:
        res = self.vocabulary.get_term(phrase)
        return res

    def get_suggestions(self) -> List[str]:
        top = self.habits.get_top_habits()
        return [f"Frequent habit: {h['habit_key']} ({h['frequency']} times)" for h in top]

    # ------------------------------------------------------------------
    # Execution Preference passthrough helpers
    # ------------------------------------------------------------------

    def get_execution_preference(self, target: str) -> Optional[str]:
        """Return the saved container/browser preference for *target*, or None."""
        return self.exec_pref.get_target_preference(target)

    def set_execution_preference(
        self, target: str, container: str, scope: str = "permanent"
    ) -> None:
        """Persist a container preference for *target*.

        scope='permanent' (default) survives restarts.
        scope='session' is lost on next startup ("aaj ke liye").
        """
        self.exec_pref.set_target_preference(target, container, scope=scope)

    def clear_execution_preference(self, target: str, scope: str = "all") -> None:
        """Clear a container preference for *target*."""
        self.exec_pref.clear_target_preference(target, scope=scope)
