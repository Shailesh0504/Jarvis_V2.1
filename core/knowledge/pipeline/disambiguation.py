# core/knowledge/pipeline/disambiguation.py
"""
Entity Disambiguation Engine for Polysemous Terms.
Detects when a queried entity has multiple distinct semantic interpretations
(e.g., Java language vs Java island, Mercury planet vs element, Apple company vs fruit).
Resolves ambiguity via active conversational context or generates a focused clarification prompt.
"""

from typing import Dict, List, Optional, Tuple

from ..models import DisambiguationOption


class EntityDisambiguationEngine:
    """Manages polysemous entity detection and contextual disambiguation."""

    AMBIGUOUS_ENTITIES: Dict[str, List[DisambiguationOption]] = {
        "java": [
            DisambiguationOption(
                entity_id="java_programming",
                label_en="Java (Programming Language)",
                label_hi="Java (Programming Bhasha)",
                domain="computer_science",
                summary="High-level, class-based object-oriented programming language developed by Sun Microsystems."
            ),
            DisambiguationOption(
                entity_id="java_island",
                label_en="Java (Island in Indonesia)",
                label_hi="Java (Indonesia ka Dweep)",
                domain="geography",
                summary="An island of Indonesia bordered by the Indian Ocean to the south and Java Sea to the north."
            )
        ],
        "mercury": [
            DisambiguationOption(
                entity_id="mercury_planet",
                label_en="Mercury (Planet)",
                label_hi="Budh Grah (Mercury Planet)",
                domain="astronomy",
                summary="The smallest planet in the Solar System and the closest to the Sun."
            ),
            DisambiguationOption(
                entity_id="mercury_element",
                label_en="Mercury (Chemical Element Hg)",
                label_hi="Para (Mercury Element Hg)",
                domain="chemistry",
                summary="A heavy, silvery d-block element that is liquid at standard conditions for temperature and pressure."
            )
        ],
        "apple": [
            DisambiguationOption(
                entity_id="apple_company",
                label_en="Apple Inc. (Technology Company)",
                label_hi="Apple Inc. (Tech Company)",
                domain="technology",
                summary="American multinational technology company known for iPhone, Mac, and iOS."
            ),
            DisambiguationOption(
                entity_id="apple_fruit",
                label_en="Apple (Fruit)",
                label_hi="Seb (Apple Fruit)",
                domain="botany",
                summary="A round, edible fruit produced by an apple tree (Malus domestica)."
            )
        ],
        "python": [
            DisambiguationOption(
                entity_id="python_programming",
                label_en="Python (Programming Language)",
                label_hi="Python (Programming Language)",
                domain="computer_science",
                summary="High-level general-purpose programming language known for readability and Guido van Rossum."
            ),
            DisambiguationOption(
                entity_id="python_snake",
                label_en="Python (Reptile / Snake)",
                label_hi="Ajgar (Python Snake)",
                domain="zoology",
                summary="A family of non-venomous constricting snakes found in Africa, Asia, and Australia."
            )
        ]
    }

    @classmethod
    def check_ambiguity(
        cls,
        text: str,
        active_context_domain: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str], List[DisambiguationOption]]:
        """
        Checks if the text contains a polysemous term requiring disambiguation.
        Returns:
            (is_ambiguous, term, resolved_entity_id, options)
        """
        lowered = text.strip().lower()

        for term, options in cls.AMBIGUOUS_ENTITIES.items():
            # Match term as standalone word
            if term in lowered.split():
                # 1. Check if query text itself contains domain context cues
                if term == "java":
                    if any(w in lowered for w in ["language", "code", "coding", "program", "developer", "jvm"]):
                        return False, term, "java_programming", options
                    if any(w in lowered for w in ["island", "indonesia", "capital", "ocean", "geography"]):
                        return False, term, "java_island", options
                elif term == "mercury":
                    if any(w in lowered for w in ["planet", "solar system", "grah", "orbit", "sun"]):
                        return False, term, "mercury_planet", options
                    if any(w in lowered for w in ["element", "symbol", "metal", "liquid", "hg", "thermometer"]):
                        return False, term, "mercury_element", options
                elif term == "apple":
                    if any(w in lowered for w in ["company", "iphone", "steve jobs", "mac", "tech", "corp"]):
                        return False, term, "apple_company", options
                    if any(w in lowered for w in ["fruit", "phal", "eat", "tree", "vitamin", "red"]):
                        return False, term, "apple_fruit", options
                elif term == "python":
                    if any(w in lowered for w in ["code", "language", "script", "guido", "pip", "django", "banaya", "invent", "create", "develop", "founder", "author", "creator"]):
                        return False, term, "python_programming", options
                    if any(w in lowered for w in ["snake", "ajgar", "reptile", "animal", "jungle", "bite", "poison"]):
                        return False, term, "python_snake", options

                # 2. Check if active conversation context resolves it
                if active_context_domain:
                    for opt in options:
                        if opt.domain == active_context_domain:
                            return False, term, opt.entity_id, options

                # 3. Genuinely ambiguous and unresolvable without asking
                return True, term, None, options

        return False, None, None, []

    @classmethod
    def format_clarification_prompt(cls, term: str, options: List[DisambiguationOption], is_hindi: bool = True) -> str:
        """Generates a polite, targeted natural clarification question."""
        if term == "java":
            return (
                "Programming language Java ki baat kar rahe hain ya Indonesia ke Java island ki?"
                if is_hindi else
                "Are you referring to the Java programming language or the island of Java in Indonesia?"
            )
        if term == "mercury":
            return (
                "Aap saur mandal ke Mercury (Budh) grah ki baat kar rahe hain ya Mercury (Para) element ki?"
                if is_hindi else
                "Are you referring to the planet Mercury or the chemical element Mercury (Hg)?"
            )
        if term == "apple":
            return (
                "Aap Apple technology company ki baat kar rahe hain ya Apple (Seb) fruit ki?"
                if is_hindi else
                "Are you asking about Apple the technology company or apple the fruit?"
            )
        if term == "python":
            return (
                "Python programming language ki baat kar rahe hain ya Python (Ajgar) snake ki?"
                if is_hindi else
                "Are you referring to the Python programming language or the python snake?"
            )

        # Generic fallback
        opt_names = [opt.label_hi if is_hindi else opt.label_en for opt in options]
        opts_str = " ya ".join(opt_names) if is_hindi else " or ".join(opt_names)
        return (
            f"Aap {opts_str} mein se kiski baat kar rahe hain?"
            if is_hindi else
            f"Are you referring to {opts_str}?"
        )
