# core/semantic/goal_resolver.py
"""
Universal Meaning -> Goal -> Capability Resolver for Jarvis V2.1.
Translates varied, imperfect Hindi, Hinglish, and English user input into canonical goals,
matches them against available capabilities, applies priority hierarchy:
    explicit target > strong semantic evidence > active context > previous context
and enforces the anti-guessing boundary with precise clarification and honest failure.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from core.capabilities import CapabilityDescriptor, get_capability_registry
from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from core.semantic.hindi_vocab import HindiVocabEngine
from core.semantic.models import IntentName
from core.semantic.normalizer import HinglishNormalizer
from core.semantic.resolution import (
    MultiDimensionalConfidence,
    ResolutionDecision,
    SemanticResolution,
)
from core.semantic.goals import (
    CanonicalGoal,
    CanonicalSpeechAct,
    CleanupGoalMixin,
    SoftwareUpdateGoalMixin,
    EquityResearchGoalMixin,
    ContextualGoalMixin,
    CrossFeatureGoalMixin,
)

logger = logging.getLogger("jarvis.semantic.goal_resolver")


class UniversalGoalResolver(
    CleanupGoalMixin,
    SoftwareUpdateGoalMixin,
    EquityResearchGoalMixin,
    ContextualGoalMixin,
    CrossFeatureGoalMixin,
):
    """
    Authoritative Universal Meaning -> Goal -> Capability Resolver.
    Sits before command execution to derive unified decision models.
    """

    """
    Authoritative Universal Meaning -> Goal -> Capability Resolver.
    Sits before command execution to derive unified decision models.
    """
    @classmethod
    def resolve(
        cls,
        user_input: str,
        context: Optional[Any] = None,
    ) -> SemanticResolution:
        """
        Main entry point for Universal Meaning -> Goal -> Capability Resolution.
        Derives all 11 fields of the decision model.
        """
        raw_text = user_input.strip()
        lowered = raw_text.lower()
        cap_reg = get_capability_registry()

        # Step 1: Pre-normalization (Hinglish + vocabulary)
        norm_text = HinglishNormalizer.normalize_text(lowered)
        effective_text = norm_text if norm_text else lowered
        # Strip trailing punctuation for clean regex parsing
        effective_text = re.sub(r"[.?!,;:]+$", "", effective_text).strip()

        # Spelling resolution for ASR typos (e.g. 'chrme' -> 'chrome', 'braev' -> 'brave', 'tem' -> 'temp')
        try:
            from brain.spelling_resolver import SpellingResolver
            spelling_res = SpellingResolver.resolve(effective_text)
            if spelling_res and spelling_res.corrected_text:
                effective_text = spelling_res.corrected_text
        except Exception as e:
            logger.debug(f"Spelling resolution bypassed: {e}")

        # Step 2: Capability-Aware Failure Gate (detect unsupported operations)
        is_unsupported, refusal_msg = cap_reg.is_unsupported_operation(effective_text)
        if is_unsupported:
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Request unsupported system/OS manipulation",
                speech_act="ACTION_COMMAND",
                goal="UNSUPPORTED_OPERATION",
                intent="UNSUPPORTED",
                entities={},
                parameters={},
                context_dependencies=[],
                capability_required="system.unsupported",
                capability_available=False,
                confidence=1.0,
                confidence_breakdown=MultiDimensionalConfidence(
                    intent_confidence=1.0,
                    entity_confidence=1.0,
                    context_confidence=1.0,
                    capability_confidence=0.0,
                    action_confidence=0.0,
                ),
                decision=ResolutionDecision.CAPABILITY_UNAVAILABLE,
                response_text=refusal_msg or cap_reg.UNSUPPORTED_RESPONSE,
            )

        # Meta-Contextual Assistance ("tum context se samajhne ki koshish karo", "samjho main karna kya chahta hoon")
        if cls.RE_META_CONTEXT.search(effective_text):
            return cls._resolve_meta_contextual(raw_text, effective_text, context)

        # Inverse Action ("jo pichhli baar kiya tha, uska ulta kar")
        if cls.RE_INVERSE_ACTION.search(effective_text):
            return cls._resolve_inverse_action(raw_text, effective_text, context)

        # Step 3: Speech-Act & Conversational Gating
        has_pending = bool(
            context
            and hasattr(context, "has_pending_confirmation")
            and context.has_pending_confirmation()
        )
        conv_res = ConversationalIntentClassifier.classify(
            effective_text,
            has_pending_confirmation=has_pending,
            active_context=context,
        )

        speech_act = conv_res.intent_type.value if hasattr(conv_res.intent_type, "value") else str(conv_res.intent_type)

        # 3a. Capability Questions ("kya tum system lock kar sakte ho?", "can you clear temp files?")
        if conv_res.intent_type == ConversationalIntentType.CAPABILITY_QUESTION:
            if not cls._is_equity_research_candidate(effective_text, context):
                return cls._resolve_capability_question(raw_text, effective_text, conv_res)

        # 3b. Status Questions ("system lock hai kya?")
        if conv_res.intent_type in (ConversationalIntentType.STATUS_QUESTION, ConversationalIntentType.STATUS_AFTER_ACTION):
            return cls._resolve_status_question(raw_text, effective_text, conv_res)

        # 3c. Troubleshooting ("system lock kyun nahi ho raha?")
        if conv_res.intent_type == ConversationalIntentType.TROUBLESHOOTING:
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Troubleshoot {conv_res.target or 'operation'}",
                speech_act="TROUBLESHOOTING",
                goal="TROUBLESHOOT",
                intent="TROUBLESHOOTING",
                entities={"target": conv_res.target},
                parameters={},
                context_dependencies=[],
                capability_required="core.troubleshoot",
                capability_available=True,
                confidence=conv_res.confidence,
                decision=ResolutionDecision.ANSWER,
                response_text=conv_res.natural_response or "Is operation mein koi error detected nahi hai.",
            )

        # 3c-2. Information Questions ("software updates kaise karte hain?")
        if conv_res.intent_type == ConversationalIntentType.INFORMATION_QUESTION:
            if "update" in effective_text:
                ans = "Software update karne ke liye aap 'software update kar do' ya 'Windows update kar do' bol sakte hain. Main WinGet aur Windows Update dono check karta hoon."
            else:
                ans = conv_res.natural_response or "Is topic ki information main bata sakta hoon."
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Information inquiry regarding {conv_res.target or 'topic'}",
                speech_act="INFORMATION_REQUEST",
                goal="INFORMATION_REQUEST",
                intent="INFORMATION_REQUEST",
                entities={"target": conv_res.target or "general"},
                parameters={},
                context_dependencies=[],
                capability_required="core.information",
                capability_available=True,
                confidence=conv_res.confidence,
                decision=ResolutionDecision.ANSWER,
                response_text=ans,
            )

        # 3-neg. Negation Invariant Enforcement ("Chrome mat kholo", "Usko band mat karo")
        if conv_res.parameters.get("is_negated"):
            neg_target = conv_res.target or "operation"
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Negated command for {neg_target}",
                speech_act="REJECTION",
                goal="NEGATED_COMMAND",
                intent=IntentName("REJECTION"),
                entities={"target": neg_target},
                parameters={"is_negated": True},
                context_dependencies=[],
                capability_required="core.dialog",
                capability_available=True,
                confidence=0.98,
                decision=ResolutionDecision.ANSWER,
                response_text=conv_res.natural_response or f"Theek hai, main {neg_target} perform nahi kar raha.",
            )

        # 3-prag. Pragmatic Situational Clarification ("Yaar bahut garmi hai")
        if conv_res.parameters.get("pragmatic_goal"):
            p_goal = conv_res.parameters.get("pragmatic_goal")
            p_prompt = conv_res.parameters.get("clarification_prompt", "AC chala doon?")
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Pragmatic statement indicating potential {p_goal}",
                speech_act="PRAGMATIC_STATEMENT",
                goal=p_goal,
                intent=IntentName("PRAGMATIC"),
                entities={"goal": p_goal},
                parameters=conv_res.parameters,
                context_dependencies=[],
                capability_required="core.pragmatic",
                capability_available=True,
                confidence=0.58,  # Calibrated uncertainty
                decision=ResolutionDecision.CLARIFY,
                clarification_prompt=p_prompt,
                response_text=p_prompt,
            )

        # 3d. Confirmation / Cancellation
        if conv_res.intent_type == ConversationalIntentType.CANCELLATION:
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Cancel pending operation",
                speech_act="CANCELLATION",
                goal="CANCEL",
                intent=IntentName("CANCELLATION"),
                decision=ResolutionDecision.ANSWER,
                response_text=conv_res.natural_response or "Theek hai, cancel kar diya hai.",
            )

        # 3e. Expressed Desires ("mera video dekhne ka man kar raha hai", "gaana sunne ka mood hai")
        if conv_res.intent_type == ConversationalIntentType.EXPRESSED_DESIRE:
            desire_goal = conv_res.parameters.get("goal", "WATCH_VIDEO")
            desire_act = conv_res.parameters.get("possible_next_action", "OFFER_VIDEO/YOUTUBE")
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Expressed user desire for {desire_goal}",
                speech_act="CONVERSATION",
                goal=desire_goal,
                intent=IntentName("EXPRESSED_DESIRE"),
                entities={"goal": desire_goal, "possible_action": desire_act},
                parameters={"goal": desire_goal, "possible_next_action": desire_act},
                context_dependencies=[],
                capability_required="",
                capability_available=True,
                confidence=conv_res.confidence,
                decision=ResolutionDecision.ANSWER,
                response_text=conv_res.natural_response or "Bataiye main kya madad karun?",
            )

        # Low-confidence unanchored pronoun command guard (Anti-Guessing Boundary)
        if cls.RE_ISOLATED_PRONOUN_CMD.match(effective_text):
            has_prev_action = bool(context and (getattr(context, "last_action", None) or getattr(context, "last_intent", None) or getattr(context, "application", None)))
            if not has_prev_action:
                clarify_msg = "Aap kya perform karna chahte hain?"
                return SemanticResolution(
                    raw_input=raw_text,
                    meaning="Ambiguous command without context antecedent",
                    speech_act="ACTION_COMMAND",
                    goal="AMBIGUOUS_COMMAND",
                    intent="UNKNOWN",
                    entities={},
                    parameters={},
                    context_dependencies=[],
                    capability_required="",
                    capability_available=False,
                    confidence=0.30,
                    confidence_breakdown=MultiDimensionalConfidence(
                        intent_confidence=0.30,
                        entity_confidence=0.0,
                        context_confidence=0.0,
                        capability_confidence=0.0,
                        action_confidence=0.30,
                    ),
                    decision=ResolutionDecision.ASK_PRECISE_CLARIFICATION,
                    clarification_prompt=clarify_msg,
                    response_text=clarify_msg,
                )

        # Step 4: Conversational Modifiers & Anaphora Extraction
        has_bhi = bool(cls.RE_MODIFIER_BHI.search(effective_text))
        is_repeat = bool(cls.RE_MODIFIER_REPEAT.search(effective_text))
        has_container_ref = bool(cls.RE_MODIFIER_CONTAINER.search(effective_text))
        has_pronoun_ref = bool(cls.RE_MODIFIER_PRONOUN.search(effective_text))

        # Step 4.5: Conversational Repair / Correction ("nahi, Brave kholo", "nahi, Chrome mein")
        m_corr = cls.RE_CORRECTION.match(effective_text)
        if m_corr:
            corr_clause = m_corr.group(1).strip()
            # Container correction: e.g. "Chrome mein", "in Brave"
            m_container = re.search(r"^(?:in\s+)?([a-z0-9_-]+)\s*(?:me|mein|par|pe)?$", corr_clause, re.IGNORECASE)
            known_browsers = {"chrome", "brave", "edge", "firefox", "opera"}
            if m_container and m_container.group(1).lower() in known_browsers:
                new_container = m_container.group(1).lower()
                target_entity = (
                    getattr(context, "website", None)
                    or getattr(context, "last_entity", None)
                    or getattr(context, "current_target", None)
                ) if context else None
                if target_entity:
                    return SemanticResolution(
                        raw_input=raw_text,
                        meaning=f"Open {target_entity} inside {new_container} (conversational correction)",
                        speech_act="ACTION_COMMAND",
                        goal="OPEN_WEBSITE",
                        intent=IntentName("OPEN_WEBSITE"),
                        entities={"entity": target_entity, "container": new_container},
                        parameters={"container": new_container, "is_correction": True},
                        context_dependencies=["active_context"],
                        capability_required="browser.website.open",
                        capability_available=True,
                        confidence=0.95,
                        action_plan={
                            "service": "browser",
                            "action": "open_website",
                            "parameters": {"site": target_entity, "url": f"https://www.{target_entity}.com", "container": new_container},
                        },
                        decision=ResolutionDecision.EXECUTE,
                    )
            # General correction: resolve the clause directly
            return cls.resolve(corr_clause, context=context)

        # Step 4.6: Negative Constraints & Scope Restrictors Extraction
        # e.g. "lekin meri personal files ko touch mat karna", "without touching personal files"
        exclude_personal_files = False
        m_neg = cls.RE_NEGATIVE_CONSTRAINT.search(effective_text)
        if m_neg:
            exclude_personal_files = True
            core_action_text = cls.RE_NEGATIVE_CONSTRAINT.sub("", effective_text).strip()
            if core_action_text:
                effective_text = core_action_text

        # Step 5: Entity Detection & Target Extraction with Negation Scoping
        temp_negated = bool(cls.RE_NEGATED_TEMP.search(effective_text))
        recycle_negated = bool(cls.RE_NEGATED_RECYCLE.search(effective_text))

        has_temp_target = bool(cls.RE_TEMP_ENTITY.search(effective_text)) and not temp_negated
        has_recycle_target = bool(cls.RE_RECYCLE_ENTITY.search(effective_text)) and not recycle_negated
        has_clean_action = bool(cls.RE_CLEAN_ACTION.search(effective_text))
        is_indirect_cleanup = bool(cls.RE_INDIRECT_CLEANUP.search(effective_text))

        # =========================================================================
        # Goal 1: SYSTEM MAINTENANCE & CLEANUP
        # =========================================================================
        # Priority Rule: explicit target > strong semantic evidence > active context > previous context
        is_cleanup_candidate = (
            has_temp_target
            or has_recycle_target
            or is_indirect_cleanup
            or recycle_negated
            or temp_negated
            or (is_repeat and context and "CLEANUP" in str(getattr(context, "last_intent", "") or ""))
            or (has_bhi and has_clean_action and context and "CLEANUP" in str(getattr(context, "last_intent", "") or ""))
        )
        if is_cleanup_candidate:
            return cls._resolve_cleanup_goal(
                raw_text=raw_text,
                effective_text=effective_text,
                has_temp_target=has_temp_target,
                has_recycle_target=has_recycle_target,
                has_clean_action=has_clean_action,
                is_indirect_cleanup=is_indirect_cleanup,
                has_bhi=has_bhi,
                is_repeat=is_repeat,
                context=context,
                exclude_personal_files=exclude_personal_files,
                recycle_negated=recycle_negated,
                temp_negated=temp_negated,
            )

        # =========================================================================
        # Goal 1b: SOFTWARE & OS UPDATES (WinGet, Windows Update, Store, All Apps)
        # =========================================================================
        is_update_candidate = bool(
            cls.RE_UPDATE_CHECK.search(effective_text)
            or cls.RE_UPDATE_WINDOWS.search(effective_text)
            or cls.RE_UPDATE_ALL.search(effective_text)
            or cls.RE_UPDATE_CANCEL.search(effective_text)
            or (cls.RE_UPDATE_CONFIRM_EXECUTE.search(effective_text) and cls._has_pending_update_plan())
        )
        if is_update_candidate:
            return cls._resolve_software_update_goal(raw_text, effective_text, context, has_bhi)

        # =========================================================================
        # Goal 1c: INDIAN STOCK 1-MONTH EQUITY RESEARCH & DECISION SUPPORT
        # =========================================================================
        is_equity_candidate = cls._is_equity_research_candidate(effective_text, context)
        if is_equity_candidate:
            return cls._resolve_equity_research_goal(raw_text, effective_text, context)

        # =========================================================================
        # Goal 2: REPEAT PREVIOUS GOAL ("phir se karo", "same kaam karo")
        # =========================================================================
        if is_repeat and context and getattr(context, "last_intent", None):
            return cls._resolve_generic_repeat(raw_text, effective_text, context)

        # =========================================================================
        # Goal 3: CONTAINER FOLLOW-UP ("isme YouTube kholo")
        # =========================================================================
        if has_container_ref and context and (getattr(context, "application", None) or getattr(context, "website", None)):
            container_app = getattr(context, "application", None) or getattr(context, "website", None)
            res_container = cls._resolve_container_followup(raw_text, effective_text, container_app, has_bhi)
            if res_container:
                return res_container

        # =========================================================================
        # Goal 4: PRONOUN / OBJECT REFERENCE ("isko band karo", "isko hata do")
        # =========================================================================
        if has_pronoun_ref and context:
            res_pronoun = cls._resolve_pronoun_action(raw_text, effective_text, context)
            if res_pronoun:
                return res_pronoun

        # =========================================================================
        # Goal 5: CROSS-FEATURE CANONICAL GOALS (Apps, Browser, Volume, Power)
        # =========================================================================
        res_cross = cls._resolve_cross_feature_goal(raw_text, effective_text, context, has_bhi)
        if res_cross:
            return res_cross

        # Fallback: Unknown goal or unsupported command
        return SemanticResolution(
            raw_input=raw_text,
            meaning=f"Unrecognized capability for request: {raw_text}",
            speech_act="ACTION_COMMAND",
            goal="UNKNOWN_GOAL",
            intent="UNKNOWN",
            entities={},
            parameters={},
            context_dependencies=[],
            capability_required="",
            capability_available=False,
            confidence=0.30,
            confidence_breakdown=MultiDimensionalConfidence(
                intent_confidence=0.30,
                entity_confidence=0.0,
                context_confidence=0.5,
                capability_confidence=0.0,
                action_confidence=0.30,
            ),
            decision=ResolutionDecision.CAPABILITY_UNAVAILABLE,
            response_text=cap_reg.UNSUPPORTED_RESPONSE,
        )
    def resolve_utterance(self, raw_text: str, context: Optional[Any] = None) -> SemanticResolution:
        """Instance method alias for resolve."""
        return self.resolve(raw_text, context)


# Backward-compatibility alias
GoalResolver = UniversalGoalResolver

__all__ = [
    "CanonicalGoal",
    "CanonicalSpeechAct",
    "UniversalGoalResolver",
    "GoalResolver",
]


