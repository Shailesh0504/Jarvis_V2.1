# Auto-extracted domain goal mixin
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

logger = logging.getLogger("jarvis.semantic.goal_resolver")


class CleanupGoalMixin:
    RE_TEMP_ENTITY = re.compile(
        r"\b(?:temp|temporary)\b(?:\s+(?:files?|data|folders?|dirs?|directory|junk|garbage|kachra|cheezein|clutter|kooda|trash|stuff))?|\b(?:files?|data|folder|junk|garbage|kachra|clutter|trash|stuff)\s+(?:temp|temporary)\b",
        re.IGNORECASE,
    )
    RE_RECYCLE_ENTITY = re.compile(
        r"\b(?:recycle(?:\s*bin)?|recyclebin|trash(?:\s*can)?|dustbin|kachra\s*(?:dabba|dibba)?)\b",
        re.IGNORECASE,
    )
    RE_CLEAN_ACTION = re.compile(
        r"\b(?:clear|clean|cleanup|delete|remove|erase|saaf|khali|empty|hatao|hata|halke?|nikaal|nikaalo|nipta\s*do|nipta|tidy(?:\s*up)?)\b",
        re.IGNORECASE,
    )
    RE_INDIRECT_CLEANUP = re.compile(
        r"\b(?:thoda\s+)?(?:computer|pc|system|machine|laptop|disk)\s+(?:ko\s+)?(?:thoda\s+)?(?:halka|clean|cleanup|cleaning|saaf|safai|fresh|refresh|speed\s*up|tidy\s*up)\s*(?:kar\s+do|karo|kardo|kar\s+de|kijiye|chahiye|karna\s+hai|need|want)?\b|"
        r"\b(?:mujhe\s+)?(?:thoda\s+)?(?:system|computer|pc|machine|laptop)\s+(?:ka\s+)?(?:basic\s+|thoda\s+)?(?:cleanup|cleaning|safai)\s*(?:chahiye|karo|kar\s+do|kardo|kar\s+de|kijiye|karna\s+hai|need|want)?\b|"
        r"\b(?:clean|cleanup|saaf)\s+(?:up\s+)?(?:the\s+)?(?:system|computer|pc|laptop|machine)\b|"
        r"\b(?:halka|clean|cleanup|saaf|fresh|refresh|tidy\s*up)\s+(?:kar\s+do|karo|kardo|kar\s+de)\s+(?:computer|pc|system|disk)\b|"
        r"\b(?:system|computer|machine)\s+(?:mein|se)\s+(?:jo\s+)?(?:unnecessary|faltu|extra|temporary)\s+(?:cheezein|files?|data|garbage|junk|kachra|clutter|kooda)\s+(?:hata|saaf|clean|remove|nikaal|nikaalo)\b|"
        r"\b(?:disk|computer|system)\s+par\s+(?:jo\s+|jitna\s+)?(?:unnecessary|faltu|temporary)\s+(?:junk|garbage|kachra|trash|stuff|cheezein)\s+(?:hai\s+)?(?:use\s+|sab\s+)?(?:hata|saaf|clean|remove|nikaal)\b|"
        r"\bsystem\s+ko\s+halka\s+karna\s+hai(?:\s*,\s*|\s+)(?:woh\s+)?basic\s+wala\s+kaam\s+kar\b|"
        r"\b(?:computer|pc|system|machine)\s+ko\s+(?:thoda\s+)?tidy\s*up\s*(?:kar\s+do|karo|kar\s+de|kardo)?\b",
        re.IGNORECASE,
    )
    RE_NEGATED_TEMP = re.compile(
        r"\b(?:temp|temporary)\s+(?:nahi|not|mat|chhod(?:kar|\s+do)?)\b|(?<!\brecycle\s)(?<!\bbin\s)(?<!\btrash\s)\b(?:nahi|not|mat)\s+(?:temp|temporary)\b|\b(?:temp|temporary)\s+ko\s+chhodkar\b",
        re.IGNORECASE,
    )
    RE_NEGATED_RECYCLE = re.compile(
        r"\b(?:recycle(?:\s*bin)?|trash|dustbin)\s+(?:nahi|not|mat|ko\s+(?:abhi\s+)?chhod\s*do|ko\s+chhodkar|chhodkar|chhod\s*do)\b|(?<!\btemp\s)(?<!\btemporary\s)\b(?:nahi|not|mat)\s+(?:recycle(?:\s*bin)?|trash)\b|\bpar\s+recycle(?:\s*bin)?\s+(?:ko\s+)?(?:abhi\s+)?chhod\s*do\b",
        re.IGNORECASE,
    )
    RE_NEGATIVE_CONSTRAINT = re.compile(
        r",?\s*\b(?:lekin|magar|parantu|kintu|par|but|except|without|bina|chhodkar|ko\s+chhodkar|ke\s+alawa)\s+"
        r"(?:"
        r"(?:don\'t|do\s*not|mat|without|bina)\s+(?:touch|touching|delete|deleting|remove|removing|chhedna|chhedo|hataana)\s+(?:meri\s+|my\s+|any\s+|apni\s+)?(?:personal\s*(?:files?|data|documents?|photos?)|files?|data|documents?)|"
        r"(?:touch|touching|delete|deleting|remove|removing)\s+(?:meri\s+|my\s+|any\s+|apni\s+)?(?:personal\s*(?:files?|data|documents?|photos?)|files?|data|documents?)|"
        r"(?:meri\s+|my\s+|apni\s+)?(?:personal\s*(?:files?|data|documents?|photos?|videos?|folders?)|files?|data|documents?)\s+(?:ko\s+)?(?:touch\s*mat\s*karna|mat\s*touch\s*karna|mat\s*chhuna|chhedna\s*mat|mat\s*chhedna|mat\s*chhedo|delete\s*mat\s*karna|mat\s*delete\s*karna|hataana\s*mat|mat\s*hataana|hatao\s*mat|saaf\s*mat\s*karna|mat\s*saaf\s*karna|don\'t\s*touch|do\s*not\s*touch|don\'t\s*delete|do\s*not\s*delete)\b|"
        r"(?:meri\s+|my\s+)?(?:personal\s*(?:files?|data|documents?)|files?|data)\s+(?:ko\s+)?(?:touch|delete|chhedne|hataaye)\s*(?:kiye)?|"
        r"woh\s+wali\s+jagah\s+mat\s+chhedna\s+jahan\s+meri\s+files\s+hain|"
        r"(?:jo\s+)?(?:user|meri|my|apni|personal)\s*(?:files?|data|documents?)\s*(?:hain\s+)?(?:woh\s+)?(?:rehne\s+de|rehne\s+dena|safe\s+rakhna)"
        r")\b",
        re.IGNORECASE,
    )
    @classmethod
    def _resolve_cleanup_goal(
        cls,
        raw_text: str,
        effective_text: str,
        has_temp_target: bool,
        has_recycle_target: bool,
        has_clean_action: bool,
        is_indirect_cleanup: bool,
        has_bhi: bool,
        is_repeat: bool,
        context: Optional[Any],
        exclude_personal_files: bool = False,
        recycle_negated: bool = False,
        temp_negated: bool = False,
    ) -> SemanticResolution:
        """
        Resolves system cleanup requests adhering strictly to Section 4, 8, 10, 14.
        Explicit target overrides context.
        Indirect ambiguous requests trigger precise clarification.
        """
        modifier_str = "ALSO" if has_bhi else ("REPEAT" if is_repeat else None)

        # 1. Explicit Current Target: TEMP FILES
        # "temp bhi clear karo" -> explicit target "temp" overrides previous Recycle Bin context!
        if has_temp_target and not temp_negated:
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Clean temporary system data",
                speech_act="ACTION_COMMAND",
                goal="TEMP_FILE_CLEANUP",
                intent=IntentName("TEMP_FILE_CLEANUP"),
                entities={"entity": "temp_files", "target": "temp_files"},
                parameters={"action": "clean", "action_type": "CLEAN", "modifier": modifier_str, "exclude_personal_files": exclude_personal_files},
                context_dependencies=[],
                capability_required="system.maintenance.temp_cleanup",
                capability_available=True,
                confidence=1.0 if has_clean_action else 0.92,
                confidence_breakdown=MultiDimensionalConfidence(
                    intent_confidence=1.0,
                    entity_confidence=1.0,
                    context_confidence=1.0,
                    capability_confidence=1.0,
                    action_confidence=1.0 if has_clean_action else 0.85,
                ),
                action_plan={
                    "service": "system",
                    "action": "clear_temp_files",
                    "parameters": {"target": "temp_files", "exclude_personal_files": exclude_personal_files},
                },
                decision=ResolutionDecision.EXECUTE,
            )

        # 2. Explicit Current Target: RECYCLE BIN
        if has_recycle_target and not recycle_negated:
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Empty system Recycle Bin",
                speech_act="ACTION_COMMAND",
                goal="RECYCLE_BIN_CLEANUP",
                intent=IntentName("RECYCLE_BIN_CLEANUP"),
                entities={"entity": "recycle_bin", "target": "recycle_bin"},
                parameters={"action": "empty", "action_type": "CLEAN", "modifier": modifier_str, "exclude_personal_files": exclude_personal_files},
                context_dependencies=[],
                capability_required="system.maintenance.recycle_bin",
                capability_available=True,
                confidence=1.0,
                confidence_breakdown=MultiDimensionalConfidence(
                    intent_confidence=1.0,
                    entity_confidence=1.0,
                    context_confidence=1.0,
                    capability_confidence=1.0,
                    action_confidence=1.0,
                ),
                action_plan={
                    "service": "system",
                    "action": "empty_recycle_bin",
                    "parameters": {"target": "recycle_bin", "exclude_personal_files": exclude_personal_files},
                },
                decision=ResolutionDecision.EXECUTE,
            )

        # 2.1. Negation-Induced Disambiguation: Recycle Bin excluded ("par Recycle Bin ko abhi chhod do")
        if recycle_negated and (is_indirect_cleanup or has_clean_action or not has_temp_target):
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Clean computer temporary cache excluding Recycle Bin",
                speech_act="ACTION_COMMAND",
                goal="TEMP_FILE_CLEANUP",
                intent=IntentName("TEMP_FILE_CLEANUP"),
                entities={"entity": "temp_files", "target": "temp_files"},
                parameters={"action": "clean", "action_type": "CLEAN", "exclude_recycle_bin": True, "exclude_personal_files": exclude_personal_files},
                context_dependencies=[],
                capability_required="system.maintenance.temp_cleanup",
                capability_available=True,
                confidence=0.95,
                action_plan={
                    "service": "system",
                    "action": "clear_temp_files",
                    "parameters": {"target": "temp_files", "exclude_personal_files": exclude_personal_files},
                },
                decision=ResolutionDecision.EXECUTE,
            )

        # 2.2. Complementary Context Target ("Usko bhi saaf kar de")
        if has_bhi and has_clean_action and context:
            prev_intent = str(getattr(context, "last_intent", "") or "")
            prev_act = str(getattr(context, "last_action", "") or "")
            if "TEMP" in prev_intent or prev_act == "clear_temp_files":
                return SemanticResolution(
                    raw_input=raw_text,
                    meaning="Empty Recycle Bin as complementary cleanup target",
                    speech_act="ACTION_COMMAND",
                    goal="RECYCLE_BIN_CLEANUP",
                    intent=IntentName("RECYCLE_BIN_CLEANUP"),
                    entities={"entity": "recycle_bin", "target": "recycle_bin"},
                    parameters={"action": "empty", "action_type": "CLEAN", "modifier": "ALSO", "exclude_personal_files": exclude_personal_files},
                    context_dependencies=["last_intent", "last_action"],
                    capability_required="system.maintenance.recycle_bin",
                    capability_available=True,
                    confidence=0.95,
                    action_plan={
                        "service": "system",
                        "action": "empty_recycle_bin",
                        "parameters": {"target": "recycle_bin", "exclude_personal_files": exclude_personal_files},
                    },
                    decision=ResolutionDecision.EXECUTE,
                )
            elif "RECYCLE" in prev_intent or prev_act == "empty_recycle_bin":
                return SemanticResolution(
                    raw_input=raw_text,
                    meaning="Clean temporary files as complementary cleanup target",
                    speech_act="ACTION_COMMAND",
                    goal="TEMP_FILE_CLEANUP",
                    intent=IntentName("TEMP_FILE_CLEANUP"),
                    entities={"entity": "temp_files", "target": "temp_files"},
                    parameters={"action": "clean", "action_type": "CLEAN", "modifier": "ALSO", "exclude_personal_files": exclude_personal_files},
                    context_dependencies=["last_intent", "last_action"],
                    capability_required="system.maintenance.temp_cleanup",
                    capability_available=True,
                    confidence=0.95,
                    action_plan={
                        "service": "system",
                        "action": "clear_temp_files",
                        "parameters": {"target": "temp_files", "exclude_personal_files": exclude_personal_files},
                    },
                    decision=ResolutionDecision.EXECUTE,
                )

        # 3. Contextual Repeat: "phir se karo"
        if is_repeat and context:
            prev_intent = str(getattr(context, "last_intent", "") or "")
            prev_act = str(getattr(context, "last_action", "") or "")
            if "TEMP" in prev_intent or prev_act == "clear_temp_files":
                return SemanticResolution(
                    raw_input=raw_text,
                    meaning="Repeat temporary files cleanup",
                    speech_act="ACTION_COMMAND",
                    goal="TEMP_FILE_CLEANUP",
                    intent=IntentName("TEMP_FILE_CLEANUP"),
                    entities={"entity": "temp_files", "target": "temp_files"},
                    parameters={"action": "clean", "action_type": "CLEAN", "modifier": "REPEAT", "exclude_personal_files": exclude_personal_files},
                    context_dependencies=["last_intent", "last_action"],
                    capability_required="system.maintenance.temp_cleanup",
                    capability_available=True,
                    confidence=0.95,
                    action_plan={
                        "service": "system",
                        "action": "clear_temp_files",
                        "parameters": {"target": "temp_files", "exclude_personal_files": exclude_personal_files},
                    },
                    decision=ResolutionDecision.EXECUTE,
                )
            if "RECYCLE" in prev_intent or prev_act == "empty_recycle_bin":
                return SemanticResolution(
                    raw_input=raw_text,
                    meaning="Repeat Recycle Bin cleanup",
                    speech_act="ACTION_COMMAND",
                    goal="RECYCLE_BIN_CLEANUP",
                    intent=IntentName("RECYCLE_BIN_CLEANUP"),
                    entities={"entity": "recycle_bin", "target": "recycle_bin"},
                    parameters={"action": "empty", "action_type": "CLEAN", "modifier": "REPEAT", "exclude_personal_files": exclude_personal_files},
                    context_dependencies=["last_intent", "last_action"],
                    capability_required="system.maintenance.recycle_bin",
                    capability_available=True,
                    confidence=0.95,
                    action_plan={
                        "service": "system",
                        "action": "empty_recycle_bin",
                        "parameters": {"target": "recycle_bin", "exclude_personal_files": exclude_personal_files},
                    },
                    decision=ResolutionDecision.EXECUTE,
                )

        # 4. Indirect Phrasing: "bhai computer halka kar de" / "system clean karo"
        # Candidates: TEMP_FILE_CLEANUP vs RECYCLE_BIN_CLEANUP
        # If user explicitly requested not to touch personal files ("lekin meri personal files ko touch mat karna"),
        # the safe, non-destructive system maintenance action is temporary cache cleanup (TEMP_FILE_CLEANUP),
        # which strictly isolates to %TEMP% and never touches user documents/personal files.
        if exclude_personal_files:
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Clean temporary files safely without touching personal files",
                speech_act="ACTION_COMMAND",
                goal="TEMP_FILE_CLEANUP",
                intent=IntentName("TEMP_FILE_CLEANUP"),
                entities={"entity": "temp_files", "target": "temp_files"},
                parameters={"action": "clean", "action_type": "CLEAN", "exclude_personal_files": True},
                context_dependencies=[],
                capability_required="system.maintenance.temp_cleanup",
                capability_available=True,
                confidence=0.95,
                confidence_breakdown=MultiDimensionalConfidence(
                    intent_confidence=0.95,
                    entity_confidence=0.95,
                    context_confidence=1.0,
                    capability_confidence=1.0,
                    action_confidence=0.95,
                ),
                action_plan={
                    "service": "system",
                    "action": "clear_temp_files",
                    "parameters": {"target": "temp_files", "exclude_personal_files": True},
                },
                decision=ResolutionDecision.EXECUTE,
            )

        # Anti-Guessing Boundary: If context specifies one, choose that. Otherwise ask precise clarification.
        if context:
            prev_intent = str(getattr(context, "last_intent", "") or "")
            if "TEMP" in prev_intent:
                return SemanticResolution(
                    raw_input=raw_text,
                    meaning="Clean temporary files to lighten computer (context-inferred)",
                    speech_act="ACTION_COMMAND",
                    goal="TEMP_FILE_CLEANUP",
                    intent=IntentName("TEMP_FILE_CLEANUP"),
                    entities={"entity": "temp_files", "target": "temp_files"},
                    parameters={"action": "clean", "action_type": "CLEAN"},
                    context_dependencies=["last_intent"],
                    capability_required="system.maintenance.temp_cleanup",
                    capability_available=True,
                    confidence=0.88,
                    action_plan={
                        "service": "system",
                        "action": "clear_temp_files",
                        "parameters": {"target": "temp_files"},
                    },
                    decision=ResolutionDecision.EXECUTE,
                )

        # No distinguishing evidence: candidates are equally close.
        # Section 4 & Section 10: Ask precise clarification!
        clarify_text = "Computer cleanup mein temp files saaf karun ya Recycle Bin bhi?"
        return SemanticResolution(
            raw_input=raw_text,
            meaning="General system cleanup / storage optimization",
            speech_act="ACTION_COMMAND",
            goal="SYSTEM_CLEANUP",
            intent=IntentName("SYSTEM_MAINTENANCE"),
            entities={"candidates": ["temp_files", "recycle_bin"]},
            parameters={"workflow_type": "SYSTEM_CLEANUP_DISAMBIGUATION"},
            context_dependencies=[],
            capability_required="system.maintenance",
            capability_available=True,
            confidence=0.70,
            confidence_breakdown=MultiDimensionalConfidence(
                intent_confidence=0.85,
                entity_confidence=0.60,
                context_confidence=0.60,
                capability_confidence=1.0,
                action_confidence=0.85,
            ),
            action_plan={
                "service": "system",
                "action": "disambiguate_cleanup",
                "missing_slot": "cleanup_target",
            },
            decision=ResolutionDecision.ASK_PRECISE_CLARIFICATION,
            clarification_prompt=clarify_text,
            response_text=clarify_text,
        )
