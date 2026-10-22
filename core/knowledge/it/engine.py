# core/knowledge/it/engine.py
"""
Dedicated IT & Infrastructure Knowledge Engine for Jarvis V2.1.
Coordinates concept resolution, safe command explanations, structured 6-phase troubleshooting,
question classification, Hinglish translation, and multi-turn context tracking.
Implements the Senior IT Systems Administrator response persona.
"""

from typing import Any, Dict, List, Optional
import logging
import threading

from .models import (
    CommandRiskLevel,
    ITCommand,
    ITConcept,
    ITDomain,
    ITQueryResult,
    ITQuestionType,
    ITTroubleshootingGuide
)
from .concept_store import ITConceptStore
from .troubleshooting_store import TroubleshootingKnowledgeStore
from .command_store import CommandKnowledgeStore
from .classifier import ITQuestionClassifier
from .context_tracker import ITContextTracker

logger = logging.getLogger("jarvis.core.knowledge.it.engine")


class ITKnowledgeEngine:
    """Dedicated IT / Infrastructure Knowledge Subsystem."""

    _instance: Optional["ITKnowledgeEngine"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.concept_store = ITConceptStore()
        self.troubleshooting_store = TroubleshootingKnowledgeStore()
        self.command_store = CommandKnowledgeStore()
        self.classifier = ITQuestionClassifier()
        self.context_tracker = ITContextTracker()
        logger.info("[IT_KNOWLEDGE_ENGINE] Initialized with 5 domains, troubleshooting recipes, and command catalog.")

    @classmethod
    def get_instance(cls) -> "ITKnowledgeEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_it_candidate(self, query: str) -> bool:
        """Determines if an utterance is an IT/infrastructure technical inquiry."""
        lowered = query.strip().lower()

        # Capability questions MUST be rejected here (handled upstream by ConversationalIntent)
        if any(tok in lowered for tok in ["sakte ho", "sakti ho", "sakte hain", "kar paoge", "can you", "could you", "able to"]):
            return False

        # Reject pure non-technical questions
        if any(w in lowered for w in ["capital of", "rajdhani", "currency", "mudra", "pm of", "who is", "formula"]):
            if not any(it in lowered for it in ["dns", "ip", "port", "azure", "server", "vm", "active directory"]):
                return False

        # Check for command match
        if self.command_store.get_command(lowered) is not None:
            return True

        # Check for troubleshooting match
        if self.troubleshooting_store.match_guide(lowered) is not None:
            return True

        # Check for concept match
        if self.concept_store.resolve_concept(lowered) is not None:
            return True

        # Check for contextual continuation
        if self.context_tracker.is_continuation_query(lowered) and self.context_tracker.is_context_active():
            return True

        # Check for classifier confidence
        qtype, domain, conf = self.classifier.classify_utterance(lowered)
        if qtype != ITQuestionType.ACTION_REQUEST and domain != ITDomain.GENERAL_IT and conf >= 0.70:
            return True

        return False

    def query(self, query_text: str) -> ITQueryResult:
        """Evaluates an IT inquiry and returns a structured ITQueryResult."""
        raw_query = query_text.strip()
        lowered = raw_query.lower()
        is_hi = self._is_hindi_or_hinglish(lowered)

        logger.debug(f"[IT_KNOWLEDGE_ENGINE] Processing IT query: {raw_query!r}")

        # 1. Handle Continuation Queries ("ab next kya karu?")
        if self.context_tracker.is_continuation_query(lowered) and self.context_tracker.is_context_active():
            next_step = self.context_tracker.get_next_step()
            active_concept = self.context_tracker.active_concept
            active_domain = self.context_tracker.active_domain or ITDomain.GENERAL_IT
            if next_step:
                resp = (
                    f"Agla step ye hai: {next_step}"
                    if is_hi else
                    f"The next step is: {next_step}"
                )
                return ITQueryResult(
                    found=True,
                    confidence=0.95,
                    question_type=ITQuestionType.HOW_TO,
                    domain=active_domain,
                    concept_id=active_concept.concept_id if active_concept else None,
                    answer_text=resp,
                    detailed_steps=[next_step]
                )

        # 2. Classify Utterance
        qtype, domain, class_conf = self.classifier.classify_utterance(lowered)

        # 3. Action Request Interceptor (Ensure Safety)
        if qtype == ITQuestionType.ACTION_REQUEST:
            return ITQueryResult(
                found=False,
                confidence=0.0,
                question_type=ITQuestionType.ACTION_REQUEST,
                domain=domain,
                answer_text="",
                clarification_needed=False
            )

        # 4. Check for Command Explanation
        # If user asks "What does ipconfig do?" or mentions a specific command
        cmd_info = self.command_store.get_command(lowered)
        if cmd_info and (qtype == ITQuestionType.COMMAND_EXPLANATION or "kya" in lowered or "what" in lowered or "explain" in lowered or "command" in lowered):
            answer = self._format_command_explanation(cmd_info, is_hi)
            self.context_tracker.update_context(domain=domain, steps=cmd_info.safe_examples)
            return ITQueryResult(
                found=True,
                confidence=0.95,
                question_type=ITQuestionType.COMMAND_EXPLANATION,
                domain=domain,
                command_name=cmd_info.command,
                answer_text=answer,
                diagnostic_commands=cmd_info.safe_examples,
                source=f"Microsoft Command Reference ({cmd_info.tool})"
            )

        # 5. Check for Troubleshooting Queries ("RDP connect nahi ho raha", "DNS resolve nahi kar raha")
        guide = self.troubleshooting_store.match_guide(lowered)
        if guide and (qtype == ITQuestionType.TROUBLESHOOTING or any(t in lowered for t in ["troubleshoot", "nahi", "error", "fail", "issue", "problem"])):
            answer = self._format_troubleshooting_response(guide, is_hi)
            self.context_tracker.update_context(domain=guide.domain, troubleshooting=guide)
            return ITQueryResult(
                found=True,
                confidence=0.92,
                question_type=ITQuestionType.TROUBLESHOOTING,
                domain=guide.domain,
                troubleshooting_id=guide.issue_id,
                answer_text=answer,
                detailed_steps=guide.possible_fixes,
                diagnostic_commands=guide.commands_tools,
                source=guide.docs_source
            )

        # 6. Check for Concept Resolution (AD DS, Azure VM, DNS, VLAN, RAID, etc.)
        concept = self.concept_store.resolve_concept(lowered)
        if concept:
            self.context_tracker.update_context(domain=concept.domain, concept=concept)

            # Check for version-sensitive / current questions
            if qtype == ITQuestionType.CURRENT_INFO or "latest" in lowered:
                ans = self._format_current_info_response(concept, is_hi)
                return ITQueryResult(
                    found=True,
                    confidence=0.85,
                    question_type=ITQuestionType.CURRENT_INFO,
                    domain=concept.domain,
                    concept_id=concept.concept_id,
                    answer_text=ans,
                    is_time_sensitive=True,
                    source="Microsoft Official Roadmap / Learn"
                )

            # Check for Comparison
            if qtype == ITQuestionType.COMPARISON:
                ans = self._format_comparison_response(concept, lowered, is_hi)
                return ITQueryResult(
                    found=True,
                    confidence=0.90,
                    question_type=ITQuestionType.COMPARISON,
                    domain=concept.domain,
                    concept_id=concept.concept_id,
                    answer_text=ans,
                    source=concept.docs_source
                )

            # Check for How-To / Configuration
            if qtype in (ITQuestionType.HOW_TO, ITQuestionType.CONFIGURATION) and concept.how_to_steps:
                ans = self._format_howto_response(concept, is_hi)
                return ITQueryResult(
                    found=True,
                    confidence=0.90,
                    question_type=qtype,
                    domain=concept.domain,
                    concept_id=concept.concept_id,
                    answer_text=ans,
                    detailed_steps=concept.how_to_steps,
                    diagnostic_commands=concept.related_commands,
                    source=concept.docs_source
                )

            # Check for Best Practices
            if qtype == ITQuestionType.BEST_PRACTICE and concept.best_practices:
                ans = self._format_best_practice_response(concept, is_hi)
                return ITQueryResult(
                    found=True,
                    confidence=0.90,
                    question_type=ITQuestionType.BEST_PRACTICE,
                    domain=concept.domain,
                    concept_id=concept.concept_id,
                    answer_text=ans,
                    detailed_steps=concept.best_practices,
                    source=concept.docs_source
                )

            # Default: Definition / Overview (Concise, experienced IT admin tone)
            ans = self._format_definition_response(concept, is_hi)
            return ITQueryResult(
                found=True,
                confidence=0.92,
                question_type=ITQuestionType.DEFINITION,
                domain=concept.domain,
                concept_id=concept.concept_id,
                answer_text=ans,
                diagnostic_commands=concept.related_commands,
                source=concept.docs_source
            )

        # 7. Unknown IT Query / Low Confidence Handling (Strict Anti-Hallucination)
        unknown_ans = (
            "Is IT issue ya configuration ke baare mein mere paas abhi reliable information uplabdh nahi hai, Boss. Kripya query thoda specific karein."
            if is_hi else
            "I do not have reliable documentation on that specific IT topic right now, Boss. Please provide more specific details."
        )
        return ITQueryResult(
            found=False,
            confidence=0.30,
            question_type=qtype,
            domain=domain,
            answer_text=unknown_ans,
            clarification_needed=True
        )

    # =========================================================================
    # EXPERIENCED IT ADMINISTRATOR PERSONA FORMATTERS
    # =========================================================================

    def _format_definition_response(self, concept: ITConcept, is_hi: bool) -> str:
        """Concise 1-2 sentence definition like a senior systems engineer."""
        if is_hi:
            def_text = concept.definition_hi or concept.definition_en
            cmd_mention = f" Relevant commands: {', '.join(concept.related_commands[:2])}." if concept.related_commands else ""
            return f"{def_text}{cmd_mention}"
        else:
            def_text = concept.definition_en
            cmd_mention = f" Related tools/commands: {', '.join(concept.related_commands[:2])}." if concept.related_commands else ""
            return f"{def_text}{cmd_mention}"

    def _format_howto_response(self, concept: ITConcept, is_hi: bool) -> str:
        """Step-by-step guidance formatted cleanly."""
        lead = (
            f"{concept.canonical_name} configure karne ke core steps ye hain:"
            if is_hi else
            f"Here are the primary steps to configure {concept.canonical_name}:"
        )
        steps_formatted = " ".join([f"{i+1}. {step}" for i, step in enumerate(concept.how_to_steps)])
        return f"{lead} {steps_formatted}"

    def _format_troubleshooting_response(self, guide: ITTroubleshootingGuide, is_hi: bool) -> str:
        """
        Follows the mandatory 6-phase IT Administrator troubleshooting structure:
        Problem -> Likely Causes -> Safe Checks -> Commands/Tools -> Possible Fixes -> Verification
        """
        if is_hi:
            header = f"{guide.title_hi}."
            causes = f"Likely causes: {', '.join(guide.likely_causes[:2])}."
            checks = f"Sabse pehle safe checks: {guide.safe_checks[0]}."
            cmd = f"Useful diagnostic commands: {', '.join(guide.commands_tools[:2])}."
            fix = f"Key fix: {guide.possible_fixes[0]}."
            verify = f"Verification: {guide.verification_steps[0]}."
            return f"{header} {causes} {checks} {cmd} {fix} {verify}"
        else:
            header = f"{guide.title_en}."
            causes = f"Likely causes: {', '.join(guide.likely_causes[:2])}."
            checks = f"Initial safe checks: {guide.safe_checks[0]}."
            cmd = f"Diagnostic tools: {', '.join(guide.commands_tools[:2])}."
            fix = f"Primary fix: {guide.possible_fixes[0]}."
            verify = f"Verification: {guide.verification_steps[0]}."
            return f"{header} {causes} {checks} {cmd} {fix} {verify}"

    def _format_command_explanation(self, cmd: ITCommand, is_hi: bool) -> str:
        """Explains command safely without executing."""
        if is_hi:
            purpose = cmd.purpose_hi
            syntax = f"Syntax: '{cmd.syntax}'."
            example = f"Common usage: '{cmd.safe_examples[0]}'." if cmd.safe_examples else ""
            return f"{cmd.command} ({cmd.tool}) {purpose} {syntax} {example}"
        else:
            purpose = cmd.purpose_en
            syntax = f"Syntax: '{cmd.syntax}'."
            example = f"Common example: '{cmd.safe_examples[0]}'." if cmd.safe_examples else ""
            return f"{cmd.command} ({cmd.tool}) {purpose} {syntax} {example}"

    def _format_comparison_response(self, concept: ITConcept, lowered: str, is_hi: bool) -> str:
        if is_hi:
            return f"{concept.canonical_name}: {concept.definition_hi}"
        return f"{concept.canonical_name}: {concept.definition_en}"

    def _format_best_practice_response(self, concept: ITConcept, is_hi: bool) -> str:
        lead = (
            f"{concept.canonical_name} ke liye recommended best practices:"
            if is_hi else
            f"Recommended best practices for {concept.canonical_name}:"
        )
        bp_text = " ".join([f"- {bp}" for bp in concept.best_practices])
        return f"{lead} {bp_text}"

    def _format_current_info_response(self, concept: ITConcept, is_hi: bool) -> str:
        if is_hi:
            return f"{concept.canonical_name} ke latest updates aur version-sensitive features ke liye official Microsoft Learn documentation ya Azure Updates portal verify karna recommended hai."
        return f"For the latest features and version-sensitive updates regarding {concept.canonical_name}, please verify via official Microsoft Learn documentation or the Azure Updates portal."

    def _is_hindi_or_hinglish(self, text: str) -> bool:
        hinglish_tokens = [
            "kya", "hai", "kaise", "karein", "karna", "nahi", "karo", "kyun", "kyu", "hota", "hoti",
            "chahiye", "batao", "kaunsa", "ab", "next", "aur", "tarika", "pehle", "kholun"
        ]
        return any(f" {t} " in f" {text} " or text.startswith(t) or text.endswith(t) for t in hinglish_tokens)


def get_it_knowledge_engine() -> ITKnowledgeEngine:
    """Global getter for the IT Knowledge Engine."""
    return ITKnowledgeEngine.get_instance()
