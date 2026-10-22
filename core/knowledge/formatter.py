# core/knowledge/formatter.py
"""
Natural Response Formatter for the Jarvis General Knowledge Engine.
Transforms structured facts and reasoning concepts into concise, conversational responses.
"""

from typing import Any, Optional
import re
from .models import KnowledgeQueryResult, ConfidenceLevel, KnowledgeSourceType


HINDI_MARKERS = [
    "kya", "hai", "hain", "kaun", "kaunsa", "kaunsi", "kisne", "kab", "kahan", "kaha",
    "kyun", "kyu", "batao", "bataiye", "bata", "desh", "rajdhani", "mudra", "hota", "hoti",
    "pehle", "pehli", "sabse", "karo", "do", "ki", "ka", "ke", "mein", "se", "ko"
]


def is_hindi_or_hinglish(text: str) -> bool:
    """Detects if query uses Hindi / Hinglish vocabulary."""
    lowered = text.lower()
    tokens = re.findall(r"\b\w+\b", lowered)
    return any(tok in HINDI_MARKERS for tok in tokens)


class KnowledgeResponseFormatter:
    """Formats knowledge query results into human-like conversational answers."""

    @classmethod
    def format(cls, result: KnowledgeQueryResult, original_query: str) -> str:
        """Formats the result into a concise, natural response."""
        is_hi = is_hindi_or_hinglish(original_query)

        # 1. Low Confidence or Unknown: Never hallucinate!
        if result.confidence == ConfidenceLevel.LOW or not result.found:
            if result.clarification_prompt:
                return result.clarification_prompt
            if is_hi:
                return "Is baare mein mere paas abhi reliable jaankari uplabdh nahi hai, Boss."
            return "I don't have reliable information on that right now, Boss."

        # 2. Time-Sensitive Query without live fetch
        if result.is_time_sensitive and result.needs_fresh_fetch:
            if is_hi:
                return f"{result.entity_name or 'Is'} ke live update ke liye mujhe live internet access ki zaroorat padegi, Boss."
            return f"I require a fresh live internet connection to retrieve the current {result.property_name or 'information'}."

        # 3. Conceptual / Reasoning Query
        if result.source_type == KnowledgeSourceType.REASONING and result.answer_text:
            return result.answer_text

        # 4. Property / Factual Query
        if result.entity_name and result.property_name and result.property_value is not None:
            return cls._format_property_response(
                entity_name=result.entity_name,
                property_name=result.property_name,
                property_value=str(result.property_value),
                is_hindi=is_hi
            )

        # 5. Entity Summary Fallback
        if result.answer_text:
            return result.answer_text

        if is_hi:
            return "Is baare mein mere paas abhi reliable jaankari uplabdh nahi hai, Boss."
        return "I don't have reliable information on that right now, Boss."

    @classmethod
    def _format_property_response(cls, entity_name: str, property_name: str, property_value: str, is_hindi: bool) -> str:
        """Formats property answer naturally."""
        val = property_value.strip()

        if is_hindi:
            if property_name == "capital":
                return f"{entity_name} ki capital {val} hai."
            if property_name == "currency":
                return f"{entity_name} ki currency {val} hai."
            if property_name == "continent":
                return f"{entity_name} {val} mahadweep mein sthit hai."
            if property_name in ("prime_minister", "current_prime_minister"):
                return f"{entity_name} ke Prime Minister {val} hain."
            if property_name in ("president", "current_president"):
                return f"{entity_name} ki President {val} hain."
            if property_name == "inventor" or property_name == "creator":
                return f"{entity_name} ko {val} ne banaya tha."
            if property_name == "discovered_by":
                return f"{entity_name} ki khoj {val} ne ki thi."
            if property_name == "chemical_formula":
                return f"{entity_name} ka chemical formula {val} hai."
            if property_name == "atomic_number":
                return f"{entity_name} ka atomic number {val} hai."
            if property_name == "full_form":
                return f"{entity_name} ka full form {val} hai."
            if property_name == "speed":
                return f"{entity_name} {val} hai."
            if property_name == "date":
                return f"{entity_name} {val} ko hua tha."
            if property_name == "independence_day":
                return f"{entity_name} {val} ko aazad hua tha."
            if property_name == "states_count":
                return f"{entity_name} mein {val} hain."
            if property_name == "population":
                return f"{entity_name} ki population {val} hai."
            if property_name in ("first_prime_minister", "first_pm"):
                return f"{entity_name} ke pehle Prime Minister {val} the."
            if property_name in ("first_president",):
                return f"{entity_name} ke pehle Rashtrapati {val} the."
            if property_name in ("official_language", "language", "official_languages"):
                return f"{entity_name} ki bhasha {val} hai."
            if property_name in ("largest_city",):
                return f"{entity_name} ka sabse bada shahar {val} hai."
            if property_name in ("famous_monuments", "famous_landmarks", "monuments", "landmarks"):
                return f"{entity_name} ke pramukh darshaniya sthal {val} hain."
            if property_name in ("height", "elevation", "altitude"):
                return f"{entity_name} ki unchai {val} hai."
            if property_name in ("length",):
                return f"{entity_name} ki lambai {val} hai."
            if property_name in ("depth",):
                return f"{entity_name} ki gehrai {val} hai."
            if property_name in ("temperature",):
                return f"{entity_name} ka tapman {val} hai."
            if property_name in ("moons_count",):
                return f"{entity_name} ke paas {val} chand hain."
            if property_name in ("order_from_sun",):
                return f"Surya se kram ke hisab se {entity_name} {val} hai."
            if property_name in ("known_as",):
                return f"{entity_name} ko '{val}' ke naam se bhi jaana jaata hai."
            if property_name in ("builder", "architect"):
                return f"{entity_name} ko {val} ne banwaya tha."
            if property_name in ("location",):
                return f"{entity_name} {val} mein sthit hai."
            if property_name in ("winter_capital",):
                return f"{entity_name} ki winter capital {val} hai."
            if property_name in ("summer_capital",):
                return f"{entity_name} ki summer capital {val} hai."
            if property_name in ("hardy_ramanujan_number",):
                return f"{entity_name} {val} hai."
            if property_name in ("born", "birth"):
                return f"{entity_name} ka janm {val} hua tha."
            if property_name in ("famous_theory", "theory"):
                return f"{entity_name} ki famous theory {val} hai."
            if property_name in ("revolution_period", "orbit_period"):
                return f"{entity_name} ko Surya ka ek poora chakkar lagane mein {val} lagte hain."
            if property_name in ("diameter",):
                return f"{entity_name} ka diameter {val} hai."
            if property_name in ("capital_of",):
                return f"{entity_name} {val} ki rajdhani hai."
            if property_name.startswith("national_"):
                neat_prop = property_name.replace("national_", "").replace("_", " ")
                return f"{entity_name} ka rashtriya {neat_prop} {val} hai."
            return f"{entity_name} ka {property_name.replace('_', ' ')} {val} hai."

        # English formatting
        if property_name == "capital":
            return f"The capital of {entity_name} is {val}."
        if property_name == "currency":
            return f"The currency of {entity_name} is {val}."
        if property_name == "continent":
            return f"{entity_name} is located in {val}."
        if property_name in ("prime_minister", "current_prime_minister"):
            return f"The Prime Minister of {entity_name} is {val}."
        if property_name in ("president", "current_president"):
            return f"The President of {entity_name} is {val}."
        if property_name in ("inventor", "creator"):
            return f"{entity_name} was created by {val}."
        if property_name in ("builder", "architect"):
            return f"{entity_name} was built by {val}."
        if property_name in ("location",):
            return f"{entity_name} is located in {val}."
        if property_name == "chemical_formula":
            return f"The chemical formula of {entity_name} is {val}."
        if property_name == "atomic_number":
            return f"The atomic number of {entity_name} is {val}."
        if property_name == "full_form":
            return f"{entity_name} stands for {val}."
        if property_name in ("speed", "speed_of_light"):
            return f"The {entity_name} is {val}."
        if property_name == "states_count":
            return f"{entity_name} has {val}."
        if property_name == "population":
            return f"The population of {entity_name} is {val}."
        if property_name in ("first_prime_minister", "first_pm"):
            return f"The first Prime Minister of {entity_name} was {val}."
        if property_name in ("first_president",):
            return f"The first President of {entity_name} was {val}."
        if property_name in ("official_language", "language", "official_languages"):
            return f"The official language of {entity_name} is {val}."
        if property_name in ("largest_city",):
            return f"The largest city in {entity_name} is {val}."
        if property_name in ("famous_monuments", "famous_landmarks", "monuments", "landmarks"):
            return f"Famous landmarks of {entity_name} include {val}."
        if property_name in ("height", "elevation", "altitude"):
            return f"The height of {entity_name} is {val}."
        if property_name in ("length",):
            return f"The length of {entity_name} is {val}."
        if property_name in ("depth",):
            return f"The depth of {entity_name} is {val}."
        if property_name in ("temperature",):
            return f"The temperature of {entity_name} is {val}."
        if property_name in ("moons_count",):
            return f"{entity_name} has {val}."
        if property_name in ("order_from_sun",):
            return f"In order from the Sun, {entity_name} is {val}."
        if property_name in ("known_as",):
            return f"{entity_name} is famously known as '{val}'."
        if property_name in ("winter_capital",):
            return f"The winter capital of {entity_name} is {val}."
        if property_name in ("summer_capital",):
            return f"The summer capital of {entity_name} is {val}."
        if property_name in ("hardy_ramanujan_number",):
            return f"The {entity_name} is {val}."
        if property_name in ("born", "birth"):
            return f"{entity_name} was born on {val}."
        if property_name in ("famous_theory", "theory"):
            return f"The famous theory of {entity_name} is {val}."
        if property_name in ("revolution_period", "orbit_period"):
            return f"The orbital period of {entity_name} is {val}."
        if property_name in ("diameter",):
            return f"The diameter of {entity_name} is {val}."
        if property_name in ("capital_of",):
            return f"{entity_name} is the capital of {val}."

        return f"The {property_name.replace('_', ' ')} of {entity_name} is {val}."
