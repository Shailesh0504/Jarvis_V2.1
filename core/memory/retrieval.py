# core/memory/retrieval.py
"""
Hybrid Memory Retrieval and Ranking Engine for Jarvis V2.
Combines Working Memory, Episodic Memory, and Semantic Memory.
Ranks candidate memories using:
    Score = (Relevance * 0.40) + (Recency * 0.40) + (Confidence * 0.20)
Where:
- Relevance evaluates topic match, entity overlap, and keyword matching
- Recency applies time decay (recent turns have high score, days/months old have lower)
- Confidence weights confirmed facts vs tentative hypotheses
"""

from dataclasses import dataclass
import logging
import math
import time
from typing import Any, Dict, List, Optional

from memory.database import DatabaseManager
from core.memory.working_memory import WorkingConversationMemory
from core.memory.episodic_memory import EpisodicConversationMemory
from core.memory.semantic_memory import SemanticConversationMemory

logger = logging.getLogger("jarvis.core.memory.retrieval")


@dataclass
class RetrievedMemory:
    source: str  # "working", "episodic", "semantic"
    topic: str
    content: str
    score: float
    recency_score: float
    relevance_score: float
    confidence: float
    metadata: Dict[str, Any]


class ConversationMemoryRetriever:
    """Authoritative memory retrieval engine providing relevant context before responding."""

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        working_memory: Optional[WorkingConversationMemory] = None,
        episodic_memory: Optional[EpisodicConversationMemory] = None,
        semantic_memory: Optional[SemanticConversationMemory] = None,
        memory_manager: Optional[Any] = None,
    ):
        if memory_manager is not None:
            self._manager = memory_manager
            self.db = memory_manager.db
            self.working = working_memory or WorkingConversationMemory()
            self.episodic = episodic_memory or EpisodicConversationMemory(memory_manager=memory_manager)
            self.semantic = semantic_memory or SemanticConversationMemory(memory_manager=memory_manager)
        else:
            self.db = db or DatabaseManager()
            self.working = working_memory or WorkingConversationMemory()
            self.episodic = episodic_memory or EpisodicConversationMemory(self.db)
            self.semantic = semantic_memory or SemanticConversationMemory(self.db)
            self._manager = getattr(self.episodic, "_manager", None)

    def retrieve(
        self,
        query: str,
        active_topic: Optional[str] = None,
        entities: Optional[Dict[str, Any]] = None,
        limit: int = 5
    ) -> List[RetrievedMemory]:
        """
        Retrieves and ranks top memories relevant to the current utterance and topic.
        """
        now = time.time()
        candidates: List[RetrievedMemory] = []
        tokens = set(query.lower().split())

        # 1. Inspect Working Memory turns
        for turn in reversed(self.working.get_recent_turns(limit=6)):
            turn_tokens = set(turn.normalized_text.split())
            overlap = len(tokens.intersection(turn_tokens)) / max(len(tokens), 1)
            topic_bonus = 0.5 if (active_topic and turn.topic == active_topic) else 0.0
            relevance = min(1.0, overlap + topic_bonus)

            # Age in seconds
            age = max(0.0, now - turn.timestamp)
            # Fast exponential decay for working memory (half-life ~ 10 mins = 600s)
            recency = math.exp(-age / 600.0)

            score = (relevance * 0.40) + (recency * 0.40) + (1.0 * 0.20)
            if score > 0.30:
                candidates.append(RetrievedMemory(
                    source="working",
                    topic=turn.topic,
                    content=f"{turn.speaker}: {turn.text}",
                    score=score,
                    recency_score=recency,
                    relevance_score=relevance,
                    confidence=1.0,
                    metadata={"timestamp": turn.timestamp}
                ))

        # 2. Inspect Episodic Memory events
        recent_events = self.episodic.get_recent_events(limit=15)
        for ev in recent_events:
            ev_topic = ev.get("topic", "")
            fact = ev.get("fact", "")
            fact_tokens = set(fact.lower().split())
            overlap = len(tokens.intersection(fact_tokens)) / max(len(tokens), 1)
            topic_bonus = 0.6 if (active_topic and ev_topic == active_topic) else 0.0
            relevance = min(1.0, overlap + topic_bonus)

            age = max(0.0, now - float(ev.get("created_at", now)))
            # Slower decay for episodic memory (half-life ~ 2 hours = 7200s)
            recency = math.exp(-age / 7200.0)
            conf = float(ev.get("confidence", 1.0))

            score = (relevance * 0.40) + (recency * 0.40) + (conf * 0.20)
            if score > 0.35:
                candidates.append(RetrievedMemory(
                    source="episodic",
                    topic=ev_topic,
                    content=fact,
                    score=score,
                    recency_score=recency,
                    relevance_score=relevance,
                    confidence=conf,
                    metadata={"event_id": ev.get("id"), "created_at": ev.get("created_at")}
                ))

        # 3. Inspect Semantic Memory facts
        for word in tokens:
            if len(word) >= 3:
                semantic_facts = self.semantic.search_facts(word, limit=3)
                for f in semantic_facts:
                    key = f.get("key", "")
                    val = f.get("value", "")
                    relevance = 0.70 if word in key else 0.50
                    recency = 0.30  # Semantic facts are long-term, recency is baseline
                    conf = float(f.get("confidence", 1.0))
                    score = (relevance * 0.40) + (recency * 0.40) + (conf * 0.20)
                    candidates.append(RetrievedMemory(
                        source="semantic",
                        topic=f.get("category", "facts"),
                        content=f"{key} = {val}",
                        score=score,
                        recency_score=recency,
                        relevance_score=relevance,
                        confidence=conf,
                        metadata={"fact_id": f.get("id")}
                    ))

        # Deduplicate candidates by content
        unique_cands: Dict[str, RetrievedMemory] = {}
        for c in sorted(candidates, key=lambda x: x.score, reverse=True):
            if c.content not in unique_cands:
                unique_cands[c.content] = c

        results = list(unique_cands.values())[:limit]
        logger.debug("[MEMORY_RETRIEVAL] Retrieved %d memories for query %r", len(results), query)
        return results
