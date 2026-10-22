# core/knowledge/pipeline/entity_extractor.py
"""
Entity and Relation Extractor with Anaphora Resolution.
Extracts canonical entities and relations using longest-alias matching,
and resolves conversational follow-ups and pronouns ("wahan", "unka", "iska")
to previously discussed entities.
"""

from typing import Any, Dict, List, Optional, Tuple
import re
import time
import logging

from ..models import KnowledgeEntity
from ..synonyms import resolve_property_key
from ..entity_store import EntityStore

logger = logging.getLogger("jarvis.core.knowledge.pipeline.entity_extractor")

# Pronoun mapping for anaphoric resolution
LOCATION_PRONOUNS = ["wahan", "wahan ki", "wahan ka", "wahan ke", "there", "that place"]
PERSON_PRONOUNS = ["unka", "unki", "unke", "unhonne", "his", "her", "their", "him"]
GENERAL_PRONOUNS = ["iska", "iski", "iske", "isne", "uska", "uski", "uske", "usne", "its", "it"]


class ConversationContextTracker:
    """Tracks active conversational context for follow-up questions and anaphora resolution."""

    def __init__(self, ttl_seconds: float = 300.0):
        self.last_entity_id: Optional[str] = None
        self.last_entity_name: Optional[str] = None
        self.last_entity_type: Optional[str] = None
        self.last_domain: Optional[str] = None
        self.last_timestamp: float = 0.0
        self.ttl_seconds = ttl_seconds

    def update_context(self, entity: KnowledgeEntity, domain: Optional[str] = None) -> None:
        """Updates the active context with the last referenced entity."""
        self.last_entity_id = entity.entity_id
        self.last_entity_name = entity.canonical_name
        self.last_entity_type = entity.entity_type
        self.last_domain = domain or entity.entity_type
        self.last_timestamp = time.time()

    def get_last_entity(self, entity_store: EntityStore) -> Optional[KnowledgeEntity]:
        """Returns the last active entity if context has not expired."""
        if not self.last_entity_id:
            return None
        if (time.time() - self.last_timestamp) > self.ttl_seconds:
            return None
        return entity_store.entities.get(self.last_entity_id)

    def clear(self) -> None:
        self.last_entity_id = None
        self.last_entity_name = None
        self.last_entity_type = None
        self.last_domain = None
        self.last_timestamp = 0.0


# Global singleton context tracker for session continuity
_GLOBAL_CONTEXT_TRACKER = ConversationContextTracker()


def get_context_tracker() -> ConversationContextTracker:
    return _GLOBAL_CONTEXT_TRACKER


# Stopwords and short particles that must NOT match entities unless explicit technical context exists
STOPWORD_ALIASES = {
    "ka", "ki", "ke", "ko", "se", "me", "mein", "par", "pe", "or", "as", "up",
    "to", "in", "on", "at", "by", "is", "it", "an", "am", "he", "c", "h", "n",
    "o", "u", "g", "a", "i", "we", "us", "do", "so", "if", "my", "no", "na"
}
EXPLICIT_CONTEXT_CUES = {
    "symbol", "chemical", "tatva", "element", "code", "vehicle", "capital",
    "rajdhani", "state", "rajya", "country", "desh", "constant", "formula"
}


class GKEntityExtractor:
    """Extracts entities, target relations, and resolves anaphoric follow-up pronouns."""

    def __init__(self, entity_store: EntityStore, context_tracker: Optional[ConversationContextTracker] = None):
        self.entity_store = entity_store
        self.context_tracker = context_tracker or get_context_tracker()

    def extract_entities(self, text: str) -> List[Tuple[KnowledgeEntity, float]]:
        """
        Finds all candidate entities mentioned in the text using longest-match principle.
        Returns list of (KnowledgeEntity, confidence_score) sorted by specificity and confidence.
        """
        lowered = f" {text.lower()} "
        candidates: List[Tuple[KnowledgeEntity, float, int]] = []

        # Sort all known aliases by length descending (longest first)
        sorted_aliases = sorted(self.entity_store.alias_map.items(), key=lambda x: len(x[0]), reverse=True)

        matched_entity_ids = set()
        for alias, entity_id in sorted_aliases:
            if entity_id in matched_entity_ids:
                continue

            # Guard against common grammatical particles and short stopwords matching as entities
            if alias in STOPWORD_ALIASES or len(alias) <= 2:
                if not any(cue in lowered for cue in EXPLICIT_CONTEXT_CUES):
                    continue

            # Word boundary regex search
            pattern = r"\b" + re.escape(alias) + r"\b"
            m = re.search(pattern, lowered)
            if m:
                # Guard against interrogative question pronoun "who" colliding with acronym WHO
                if alias == "who" and re.search(r"\bwho\s+(?:is|was|were|are|did|wrote|made|invented|discovered|has|had)\b", lowered):
                    continue

                ent = self.entity_store.entities.get(entity_id)
                if ent:
                    candidates.append((ent, 1.0, len(alias)))
                    matched_entity_ids.add(entity_id)

        # Sort by alias length (longer alias match = higher specificity)
        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
        return [(c[0], c[1]) for c in candidates]

    def resolve_anaphora(self, text: str) -> Optional[Tuple[KnowledgeEntity, str]]:
        """
        Checks if text contains anaphoric pronouns referring to recent context.
        Returns (KnowledgeEntity, pronoun_type) or None.
        """
        lowered = text.lower()
        last_entity = self.context_tracker.get_last_entity(self.entity_store)
        if not last_entity:
            return None

        # 1. Location pronouns ("wahan", "there")
        for p in LOCATION_PRONOUNS:
            if re.search(r"\b" + re.escape(p) + r"\b", lowered):
                # If last entity is a country, state, city, planet or has capital/location
                return last_entity, "location"

        # 2. Person pronouns ("unka", "unke", "his", "her")
        for p in PERSON_PRONOUNS:
            if re.search(r"\b" + re.escape(p) + r"\b", lowered):
                return last_entity, "person"

        # 3. General pronouns ("iska", "iski", "its")
        for p in GENERAL_PRONOUNS:
            if re.search(r"\b" + re.escape(p) + r"\b", lowered):
                return last_entity, "general"

        return None

    def extract_relation(self, text: str, entity: Optional[KnowledgeEntity] = None) -> Optional[str]:
        """
        Extracts the target relation or property key from query text.
        """
        lowered = text.lower()

        # Specific compound relations
        if any(w in lowered for w in ["first prime minister", "first pm", "pehle pradhan mantri", "pehle pm"]):
            return "first_prime_minister"
        if any(w in lowered for w in ["first president", "pehle rashtrapati"]):
            return "first_president"
        if any(w in lowered for w in ["population", "aabadi", "jansankhya", "kitne log"]):
            return "population"
        if any(w in lowered for w in ["theory", "famous theory", "siddhant", "relativity"]):
            return "famous_theory"
        if any(w in lowered for w in ["revolution", "orbit period", "chakkar kitne din", "chakkar lagati"]):
            return "revolution_period"
        if any(w in lowered for w in ["diameter", "size", "aakaar", "kitna bada"]):
            return "diameter"
        if any(w in lowered for w in ["mass", "vajan", "weight"]):
            return "mass"

        # Standard canonical property matcher
        prop_key = resolve_property_key(lowered)
        if prop_key:
            return prop_key

        # If entity provided, check directly against entity properties
        if entity:
            for k in entity.properties.keys():
                phrase = k.replace("_", " ")
                if phrase in lowered:
                    return k

        return None
