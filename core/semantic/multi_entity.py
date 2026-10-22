# core/semantic/multi_entity.py
"""
Multi-Entity / Multi-Action Command Parser for Jarvis V2.1.
Decomposes complex, natural language multi-target utterances into structured execution plans:
- Identifies global actions and per-clause actions
- Discovers multiple entities (adjacent or conjunction-separated)
- Associates container browsers (e.g. 'youtube brave mein')
- Independently resolves user execution preferences per entity
- Inherits actions across all targets
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from core.entities.knowledge import EntityDefinition, EntityKnowledgeBase, get_entity_knowledge_base

logger = logging.getLogger("jarvis.semantic.multi_entity")


@dataclass
class ActionItem:
    """Represents an independent actionable step in a multi-action plan."""
    action: str                     # "open", "close", "minimize", "maximize", "focus", "restore"
    target: str                     # Canonical ID (e.g. "excel", "chrome", "youtube")
    display_name: str               # Human-friendly display label (e.g. "Microsoft Excel")
    entity_type: str                # "application", "browser", "website", "system_tool", "folder"
    container: str = ""             # Preferred/explicit browser container (e.g. "brave", "chrome")
    parameters: Dict[str, Any] = field(default_factory=dict)
    is_new: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "display_name": self.display_name,
            "entity_type": self.entity_type,
            "container": self.container,
            "parameters": dict(self.parameters),
            "is_new": self.is_new,
        }


@dataclass
class MultiActionPlan:
    """Complete decomposed plan containing multiple independent actions."""
    global_action: str
    actions: List[ActionItem] = field(default_factory=list)
    raw_query: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "global_action": self.global_action,
            "actions": [a.to_dict() for a in self.actions],
            "raw_query": self.raw_query,
        }


# Regexes for action detection
ACTION_PATTERNS: Dict[str, List[re.Pattern]] = {
    "open": [
        re.compile(r'\b(?:open|launch|start|run|kholo|khol\s+do|khol\s+de|kholiye|chalao|chala\s+do|chala\s+de|chalu\s+karo|start\s+karo|open\s+karo)\b', re.IGNORECASE),
    ],
    "close": [
        re.compile(r'\b(?:close|band\s+karo|band\s+kar\s+do|band\s+kar|band|kill|terminate|exit)\b', re.IGNORECASE),
    ],
    "minimize": [
        re.compile(r'\b(?:minimize|chhota\s+karo|chhoti\s+karo|minimize\s+karo)\b', re.IGNORECASE),
    ],
    "maximize": [
        re.compile(r'\b(?:maximize|fullscreen|full\s+screen|bada\s+karo|badi\s+karo|maximize\s+karo)\b', re.IGNORECASE),
    ],
    "restore": [
        re.compile(r'\b(?:restore|unmaximize)\b', re.IGNORECASE),
    ],
    "focus": [
        re.compile(r'\b(?:focus|bring\s+to\s+front|foreground|samne\s+lao|switch\s+to)\b', re.IGNORECASE),
    ],
    "clean": [
        re.compile(r'\b(?:clean|clear|cleanup|empty|khali|saaf|delete|hatao|hata|remove)\b', re.IGNORECASE),
    ],
}

# Container connectors binding a browser to a website/tab (e.g. "chrome wala youtube", "brave me youtube", "chrome ka youtube")
CONTAINER_CONNECTORS = (
    "wala", "wali", "wale", "ka", "ki", "ke", "me", "mein", "par", "pe", "se",
    "in", "on", "inside", "under", "through", "ke andar", "ke under",
    "wala tab", "wali tab", "ka tab", "ki tab"
)

# Known browser names for container detection
KNOWN_BROWSERS = {"chrome", "brave", "edge", "firefox", "opera", "vivaldi", "browser"}

# Temporal splitters (e.g. "pehle X phir Y")
TEMPORAL_SPLIT_RE = re.compile(
    r'\b(?:pehle|first|then|phir|after\s+that|uske\s+baad|aur\s+phir|and\s+then)\b',
    re.IGNORECASE
)

# Conjunction splitters (e.g. "X aur Y", "X, Y and Z")
CONJUNCTION_SPLIT_RE = re.compile(
    r'\b(?:aur|and|tatha|evam|ya|or)\b|,',
    re.IGNORECASE
)


class MultiEntityCommandParser:
    """
    NLP Command Parser that detects multiple targets and constructs a MultiActionPlan.
    """

    def __init__(self, knowledge_base: Optional[EntityKnowledgeBase] = None) -> None:
        self.kb = knowledge_base or get_entity_knowledge_base()

    def parse(
        self,
        query: str,
        preference_manager: Optional[Any] = None
    ) -> Optional[MultiActionPlan]:
        """
        Decomposes query into a MultiActionPlan if multiple entities are identified.
        Returns None if query is purely single-entity or not a multi-action command.
        """
        raw_text = query.strip()
        lowered = raw_text.lower()

        if not raw_text:
            return None

        # 1. Detect global action verb
        global_action = self._detect_global_action(lowered) or "open"

        # 2. Extract all entities from the text
        extracted_spans = self.kb.extract_entities_from_text(raw_text)
        if not extracted_spans:
            return None

        # 3. Associate explicit containers (e.g. 'youtube brave mein', 'open youtube in brave')
        # A browser entity immediately paired with a website entity via container markers
        # represents a container rather than a standalone app.
        action_items = self._resolve_entities_and_containers(
            raw_text, extracted_spans, global_action, preference_manager
        )

        # 4. Filter and validate: Only return a plan if 2 or more independent actions exist
        if len(action_items) < 2:
            return None

        logger.info(
            "MULTI_ENTITY_PLAN_CREATED count=%d global_action=%s targets=%s",
            len(action_items),
            global_action,
            [a.target for a in action_items],
        )

        return MultiActionPlan(
            global_action=global_action,
            actions=action_items,
            raw_query=raw_text
        )

    def _detect_global_action(self, text: str) -> Optional[str]:
        """Identifies action verb from text based on presence and location."""
        for action_name, patterns in ACTION_PATTERNS.items():
            for pat in patterns:
                if pat.search(text):
                    return action_name
        return None

    def _resolve_entities_and_containers(
        self,
        text: str,
        spans: List[Tuple[EntityDefinition, int, int]],
        default_action: str,
        preference_manager: Optional[Any] = None,
    ) -> List[ActionItem]:
        """
        Processes extracted entity spans.
        Differentiates between independent entities and container specifications.
        """
        lowered = text.lower()
        items: List[ActionItem] = []
        skip_indices: set = set()

        for idx, (entity, start, end) in enumerate(spans):
            if idx in skip_indices:
                continue

            # 1. Distributive container resolution (e.g. "Chrome aur Brave kholo aur dono me YouTube open karo")
            # If the user specifies "dono me", "in both", "sab me", "in all" targeting this entity:
            if entity.entity_type == "website":
                lead_text = lowered[spans[idx - 1][2]:start] if idx > 0 else lowered[:start]
                trail_text = lowered[end:min(len(lowered), end + 25)]
                dist_pat = re.compile(
                    r'\b(?:(?:dono|teeno|chaaron|sab)\s+(?:me|mein|par|pe|browser\s+me|browser\s+mein)|in\s+(?:both|all|all\s+three)(?:\s+of\s+them)?|both\s+(?:me|mein)|on\s+(?:both|all))\b',
                    re.IGNORECASE
                )
                if dist_pat.search(lead_text) or dist_pat.search(trail_text):
                    preceding_browsers = [it.target for it in items if it.entity_type == "browser" or it.target in KNOWN_BROWSERS]
                    if preceding_browsers:
                        local_action = self._detect_local_action(text, start, end) or default_action
                        for b_target in preceding_browsers:
                            items.append(ActionItem(
                                action=local_action,
                                target=entity.entity_id,
                                display_name=entity.display_name,
                                entity_type=entity.entity_type,
                                container=b_target,
                                parameters={
                                    "canonical_name": entity.canonical_name,
                                    "url": entity.url,
                                    "executables": entity.executables,
                                }
                            ))
                        continue

            # Check if this entity is preceded or followed by an explicit container clause
            container_browser = ""

            # Only website entities can be launched inside a browser container
            if entity.entity_type == "website":
                # Check if previous entity was a browser with prefix pattern (e.g. "chrome wala youtube", "brave mein youtube", "chrome ka youtube")
                if idx - 1 >= 0 and (idx - 1) not in skip_indices:
                    prev_ent, p_start, p_end = spans[idx - 1]
                    if prev_ent.entity_id in KNOWN_BROWSERS or prev_ent.entity_type == "browser":
                        inter = lowered[p_end:start].strip()
                        has_prefix_marker = (
                            not inter  # adjacent e.g. "chrome youtube"
                            or any(inter.startswith(w) for w in CONTAINER_CONNECTORS)
                            or any(inter.endswith(w) for w in CONTAINER_CONNECTORS)
                            or any(w in inter.split() for w in CONTAINER_CONNECTORS)
                        )
                        if has_prefix_marker:
                            container_browser = prev_ent.entity_id
                            if items and items[-1].target == prev_ent.entity_id:
                                items.pop()

                # Check if next entity is a browser with container markers (e.g. "youtube brave mein", "youtube in brave", "youtube chrome wala tab")
                if not container_browser and idx + 1 < len(spans):
                    next_ent, n_start, n_end = spans[idx + 1]
                    if next_ent.entity_id in KNOWN_BROWSERS or next_ent.entity_type == "browser":
                        inter = lowered[end:n_start].strip()
                        has_conjunction = bool(CONJUNCTION_SPLIT_RE.search(inter) or TEMPORAL_SPLIT_RE.search(inter))
                        if not has_conjunction:
                            after_next = lowered[n_end:min(len(lowered), n_end + 15)].strip()
                            postfix_connectors = ("me", "mein", "par", "pe", "se", "ke andar", "ke under", "inside", "wala tab", "wali tab")
                            has_marker = (
                                inter in ("in", "on", "inside", "of", "from", "at")
                                or any(after_next.startswith(w) for w in postfix_connectors)
                                or any(inter.endswith(w) for w in ("in", "on", "inside", "from"))
                            )
                            if has_marker:
                                container_browser = next_ent.entity_id
                                skip_indices.add(idx + 1)

            # If no explicit container was provided, consult user preference memory
            if not container_browser and entity.entity_type == "website" and preference_manager:
                try:
                    pref = preference_manager.get_execution_preference(entity.entity_id)
                    if pref:
                        container_browser = pref
                except Exception:
                    pass

            # Detect clause-specific action if explicitly specified near this entity
            local_action = self._detect_local_action(text, start, end) or default_action

            items.append(ActionItem(
                action=local_action,
                target=entity.entity_id,
                display_name=entity.display_name,
                entity_type=entity.entity_type,
                container=container_browser,
                parameters={
                    "canonical_name": entity.canonical_name,
                    "url": entity.url,
                    "executables": entity.executables,
                }
            ))

        return items

    def _detect_local_action(self, text: str, start: int, end: int) -> Optional[str]:
        """Detects if an action verb is situated directly in the clause of the given span."""
        # Look around 15 characters before or 20 characters after the entity
        lowered = text.lower()
        clause_window = lowered[max(0, start - 15):min(len(lowered), end + 25)]
        for action_name, patterns in ACTION_PATTERNS.items():
            for pat in patterns:
                if pat.search(clause_window):
                    return action_name
        return None


def get_multi_entity_parser() -> MultiEntityCommandParser:
    """Helper to access global parser instance."""
    return MultiEntityCommandParser()
