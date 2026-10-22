# core/knowledge/pipeline/fast_path.py
"""
Fast Knowledge Path for Instant Deterministic Fact Retrieval.
Provides sub-15ms cached resolution for recurring, unambiguous factual queries.
"""

from typing import Dict, Optional
import time
from collections import OrderedDict

from ..models import KnowledgeQueryResult


class FastKnowledgePath:
    """In-memory LRU cache for deterministic knowledge answers."""

    def __init__(self, max_size: int = 500, ttl_seconds: float = 3600.0):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        # key -> (result, timestamp)
        self._cache: OrderedDict[str, tuple[KnowledgeQueryResult, float]] = OrderedDict()

    def get(self, normalized_query: str) -> Optional[KnowledgeQueryResult]:
        """Looks up cached answer by normalized query string."""
        key = normalized_query.strip().lower()
        if key in self._cache:
            res, ts = self._cache[key]
            if (time.time() - ts) < self.ttl_seconds:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                return res
            else:
                del self._cache[key]
        return None

    def put(self, normalized_query: str, result: KnowledgeQueryResult) -> None:
        """Stores a deterministic answer in fast-path cache."""
        # Only cache reliable, non-time-sensitive results
        if not result.found or result.is_time_sensitive or result.needs_fresh_fetch:
            return

        key = normalized_query.strip().lower()
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (result, time.time())

        # Evict oldest if exceeding capacity
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        """Clears fast path cache."""
        self._cache.clear()
