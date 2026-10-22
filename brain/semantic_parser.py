# brain/semantic_parser.py
"""
Core Brain Natural-Language Understanding (NLU) and Semantic Entity Extraction Engine.
Thin facade preserving public API contracts while delegating to modular core/semantic/ package.
"""

from typing import Any, Dict, Optional

from core.semantic import (
    KNOWN_APPS,
    OPEN_VERBS,
    PLAY_VERBS,
    POSITION_KEYWORDS,
    SEARCH_VERBS,
    SERVICE_PATTERNS,
    WINDOW_OPERATIONS,
    HinglishNormalizer,
    SemanticAction,
    SemanticPipelineOrchestrator,
)
from core.semantic.parsers.windows import (
    extract_single_layout_item,
    parse_window_layout,
)


class HinglishNLUParser:
    """
    Generalized Natural-Language Understanding Engine Facade.
    Maintains 100% backward compatibility for all core subsystems, plugins, and test suites.
    """

    PLAY_VERBS = PLAY_VERBS
    OPEN_VERBS = OPEN_VERBS
    SEARCH_VERBS = SEARCH_VERBS
    SERVICE_PATTERNS = SERVICE_PATTERNS
    WINDOW_OPERATIONS = WINDOW_OPERATIONS
    POSITION_KEYWORDS = POSITION_KEYWORDS
    KNOWN_APPS = KNOWN_APPS

    @classmethod
    def parse(cls, user_input: str, context: Optional[Any] = None) -> Optional[SemanticAction]:
        """
        Parses user query into a structured SemanticAction.
        Returns None if query is purely conversational or doesn't match a command.
        """
        return SemanticPipelineOrchestrator.parse(user_input, context=context)

    @classmethod
    def resolve_goal(cls, user_input: str, context: Optional[Any] = None) -> Any:
        """
        Authoritative Meaning -> Goal -> Capability Resolution.
        Derives all 11 decision fields including capability availability and debug string.
        """
        from core.semantic.goal_resolver import UniversalGoalResolver
        return UniversalGoalResolver.resolve(user_input, context=context)

    @classmethod
    def parse_multi(cls, user_input: str, preference_manager: Optional[Any] = None) -> Optional[Any]:
        """
        Parses user query into a MultiActionPlan if multiple entities/actions are requested.
        Returns None if query is a single-entity or conversational command.
        """
        from core.semantic.multi_entity import get_multi_entity_parser
        return get_multi_entity_parser().parse(user_input, preference_manager=preference_manager)

    @classmethod
    def _parse_window_layout(cls, raw_text: str, lowered: str) -> Optional[SemanticAction]:
        """Backward-compatible hook for core/desktop_task/planner.py."""
        return parse_window_layout(raw_text, lowered)

    @classmethod
    def _extract_single_layout_item(cls, clause: str, global_launch: bool = False) -> Optional[Dict[str, Any]]:
        """Backward-compatible hook for single layout clause extraction."""
        return extract_single_layout_item(clause, global_launch=global_launch)


__all__ = [
    "HinglishNLUParser",
    "SemanticAction",
    "HinglishNormalizer",
]
