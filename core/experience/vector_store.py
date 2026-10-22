# core/experience/vector_store.py
"""
Semantic Vector Engine and Similarity Retrieval for Experience Memories.
Provides local, zero-dependency, high-speed semantic embeddings and hybrid search
combining cosine vector similarity, token overlap, and confidence weighting.
"""

import hashlib
import math
import re
from typing import Dict, List, Optional, Tuple


class SemanticVectorEngine:
    """
    Offline semantic vector generator and similarity matcher.
    Generates normalized dense feature vectors using subword n-grams and token hashing.
    Uses lightweight local feature hashing; no external model dependency is required.
    """

    DIMENSIONS: int = 128

    SYNONYM_MAP: Dict[str, str] = {
        "zip": "compress", "archive": "compress", "tar": "compress",
        "calculate": "calc", "calculation": "calc", "sum": "calc", "total": "calc",
        "revenue": "sales", "turnover": "sales", "earnings": "sales",
        "find": "search", "locate": "search", "khojo": "search",
        "kholo": "open", "launch": "open", "start": "open",
        "sheet": "excel", "spreadsheet": "excel", "workbook": "excel",
    }

    def embed_text(self, text: str) -> List[float]:
        """
        Generates a normalized dense vector of length DIMENSIONS for the given text.
        Captures word roots, character n-grams, and semantic keywords.
        """
        if not text:
            return [0.0] * self.DIMENSIONS

        vector = [0.0] * self.DIMENSIONS
        raw_tokens = re.findall(r"\w+", text.lower())

        # Map to canonical synonyms & stems
        tokens = []
        for t in raw_tokens:
            canon = self.SYNONYM_MAP.get(t, t)
            tokens.append(canon)
            if len(canon) > 4:
                tokens.append(canon[:4])

        # 1. Unigram and Bigram Feature Hashing
        features = list(tokens)
        for i in range(len(tokens) - 1):
            features.append(f"{tokens[i]}_{tokens[i+1]}")

        # 2. Character 3-grams for morphological/Hindi/Hinglish root matching
        for token in raw_tokens:
            if len(token) >= 3:
                for j in range(len(token) - 2):
                    features.append(token[j:j+3])

        # 3. Hash features into fixed dimension vector
        for feat in features:
            h = int(hashlib.md5(feat.encode("utf-8")).hexdigest(), 16)
            idx = h % self.DIMENSIONS
            sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
            vector[idx] += sign

        # 4. L2 Normalization
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 1e-9:
            vector = [round(x / norm, 5) for x in vector]
        else:
            vector = [0.0] * self.DIMENSIONS

        return vector

    @staticmethod
    def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Calculates cosine similarity between two normalized vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a < 1e-9 or norm_b < 1e-9:
            return 0.0

        sim = dot / (norm_a * norm_b)
        return max(0.0, min(1.0, float(sim)))

    @classmethod
    def token_overlap_ratio(cls, text_a: str, text_b: str) -> float:
        """Calculates canonical Jaccard token overlap between two strings."""
        raw_a = re.findall(r"\w+", text_a.lower())
        raw_b = re.findall(r"\w+", text_b.lower())
        tokens_a = {cls.SYNONYM_MAP.get(w, w) for w in raw_a}
        tokens_b = {cls.SYNONYM_MAP.get(w, w) for w in raw_b}
        if not tokens_a or not tokens_b:
            return 0.0

        intersection = tokens_a.intersection(tokens_b)
        union = tokens_a.union(tokens_b)
        return len(intersection) / len(union)

    def hybrid_similarity(
        self,
        query: str,
        target_text: str,
        query_vector: Optional[List[float]] = None,
        target_vector: Optional[List[float]] = None
    ) -> float:
        """
        Combines vector cosine similarity with token overlap for optimal precision and recall.
        Weighting: 60% semantic vector similarity + 40% lexical token overlap.
        """
        if not query or not target_text:
            return 0.0

        # Exact substring or identity boost
        q_norm = query.strip().lower()
        t_norm = target_text.strip().lower()
        if q_norm == t_norm or q_norm in t_norm or t_norm in q_norm:
            return 0.95

        q_vec = query_vector if query_vector is not None else self.embed_text(query)
        t_vec = target_vector if target_vector is not None else self.embed_text(target_text)

        vec_sim = self.cosine_similarity(q_vec, t_vec)
        lex_sim = self.token_overlap_ratio(query, target_text)

        score = (vec_sim * 0.6) + (lex_sim * 0.4)
        return round(score, 4)
