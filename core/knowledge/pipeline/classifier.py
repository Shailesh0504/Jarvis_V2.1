# core/knowledge/pipeline/classifier.py
"""
Deep Question Type Classifier for the General Knowledge Engine.
Classifies normalized utterances into over 20 specific question types,
distinguishing simple factual inquiries from complex reasoning,
comparisons, spatial relationships, rates, multi-step queries, and wordplay.
"""

from typing import Tuple
import re

from ..models import GKQuestionType


class GKQuestionClassifier:
    """Classifies user queries into specific semantic question categories."""

    @classmethod
    def classify(cls, text: str) -> Tuple[GKQuestionType, float]:
        """
        Classifies input text into a GKQuestionType with confidence score.
        """
        lowered = text.strip().lower()

        # 1. Check for Multi-Step Query ("...aur...", "...and...")
        # e.g., "India kab independent hua aur uske first Prime Minister kaun the?"
        if any(f" {conj} " in lowered for conj in ["aur", "and", "tatha", "evam"]):
            # Confirm if both halves have distinct question attributes or targets
            parts = re.split(r"\b(?:aur|and|tatha)\b", lowered)
            if len(parts) >= 2 and len(parts[0].strip()) > 3 and len(parts[1].strip()) > 3:
                q_cues = ["kaun", "kya", "kab", "kahan", "who", "what", "when", "where", "first", "pehle"]
                if any(c in parts[0] for c in q_cues) and any(c in parts[1] for c in q_cues):
                    return GKQuestionType.MULTI_STEP, 0.95

        # 2. Check for Mathematical / Rate Reasoning
        # e.g., "If a train travels 60 km in 1 hour, how far in 3 hours?"
        if any(w in lowered for w in ["km", "speed", "hour", "ghante", "distance", "doori", "travels", "chalegi"]):
            if any(w in lowered for w in ["if", "agar", "yadi"]) and any(w in lowered for w in ["how far", "kitni door", "kitna travel", "kitna dur"]):
                return GKQuestionType.MATHEMATICAL_RATE, 0.95

        # 3. Check for Spatial / Directional Reasoning
        # e.g., "If India is north of Sri Lanka, which country is south of India?"
        if any(w in lowered for w in ["north", "south", "east", "west", "uttar", "dakshin", "poorv", "pashchim"]):
            if any(w in lowered for w in ["which country", "kaun sa desh", "kaunsa desh", "direction", "opposite"]):
                return GKQuestionType.SPATIAL_RELATION, 0.92

        # 4. Check for Comparison Reasoning
        # e.g., "Which planet is larger, Earth or Mars?", "Is Earth bigger than Mars?"
        if (
            any(w in lowered for w in ["larger", "smaller", "bigger", "bada", "chota", "badi", "choti", "highest", "longest", "compare", "vs", "versus"])
            and any(w in lowered for w in ["which", "kaun", "kaunsa", "ya", "or", "than", "se bada", "se chota"])
        ):
            return GKQuestionType.COMPARISON, 0.92

        # 5. Check for Ambiguous Entities (Polysemous terms)
        # e.g., "Java kya hai?", "Mercury kya hai?", "Apple kya hai?"
        ambiguous_singlets = ["java", "mercury", "apple", "python", "jaguar", "saturn"]
        tokens = re.findall(r"\b\w+\b", lowered)
        for term in ambiguous_singlets:
            if term in tokens and len(tokens) <= 5:
                # If neutral without clarifying context like "programming" or "planet" or "fruit"
                if not any(ctx in lowered for ctx in ["language", "code", "coding", "island", "planet", "fruit", "company", "car", "snake"]):
                    if any(q in lowered for q in ["kya hai", "what is", "meaning of", "define"]):
                        return GKQuestionType.AMBIGUOUS, 0.90

        # 6. Festival date queries ("Ganpati kab hai?", "Diwali 2026 mein kab?")
        # Must come BEFORE CURRENT_FRESH so "aaj" in festival context goes to calendar engine
        _festival_aliases_sample = [
            "ganpati", "ganesh chaturthi", "diwali", "deepawali", "holi", "navratri",
            "janmashtami", "dussehra", "raksha bandhan", "rakhi", "mahashivratri",
            "shivratri", "guru purnima", "chhath puja", "baisakhi", "pongal",
            "onam", "teej", "karwa chauth", "basant panchami", "durga puja",
            "ram navami", "buddha purnima", "mahavir jayanti", "guru nanak jayanti",
            "christmas", "eid", "republic day", "independence day", "gandhi jayanti",
            "teachers day", "childrens day", "constitution day",
        ]
        _festival_date_words = [
            "kab hai", "kab padega", "kab padegi", "kab aayega", "kab tha",
            "kab hoga", "kab se", "kab tak", "when is", "which date", "kis date",
        ]
        if any(fa in lowered for fa in _festival_aliases_sample):
            if any(dw in lowered for dw in _festival_date_words) or re.search(r'\b20[2-9]\d\b', lowered):
                return GKQuestionType.FESTIVAL_DATE, 0.95
            if any(w in lowered for w in ["kya hai", "what is", "baare mein", "about"]):
                return GKQuestionType.FESTIVAL_INFO, 0.92

        _upcoming_words = [
            "agla festival", "agla tyohaar", "next festival", "upcoming festival",
            "next tyohaar", "agle festival",
        ]
        if any(w in lowered for w in _upcoming_words):
            return GKQuestionType.UPCOMING_EVENT, 0.93

        # 7. Check for Current / Time-Sensitive Inquiries
        if any(w in lowered for w in ["current", "today", "latest", "now", "recent", "aaj", "abhi", "vartaman", "2026"]):
            return GKQuestionType.CURRENT_FRESH, 0.90

        # 7. Check for Why / Cause-Effect
        if any(w in lowered for w in ["why", "kyun", "kyu", "reason", "wajah", "kaaran", "karan"]):
            return GKQuestionType.WHY, 0.90

        # 8. Check for How / Process
        if any(w in lowered for w in ["how", "kaise", "process", "mechanism", "kaise banta", "kaise hoti"]):
            return GKQuestionType.HOW, 0.90

        # 9. Check for Explanation
        if any(w in lowered for w in ["explain", "samjhao", "vistar", "kya hota hai", "kya hoti hai"]):
            return GKQuestionType.EXPLANATION, 0.88

        # 10. Check for When (Time / Historical)
        if any(w in lowered for w in ["when", "kab", "kis saal", "kis year", "tarikh", "date"]):
            return GKQuestionType.WHEN, 0.88

        # 11. Check for Where (Geographical Location)
        if any(w in lowered for w in ["where", "kahan", "kaha", "kis jagah"]):
            return GKQuestionType.WHERE, 0.88

        # 12. Check for Who (Person / Role)
        if any(w in lowered for w in ["who", "kaun", "kisne"]):
            return GKQuestionType.WHO, 0.88

        # 13. Check for Definition
        if any(w in lowered for w in ["define", "definition", "what is", "kya hai"]):
            return GKQuestionType.DEFINITION, 0.85

        # Default fallback is factual property lookup
        return GKQuestionType.FACTUAL, 0.80
