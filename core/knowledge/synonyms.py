# core/knowledge/synonyms.py
"""
Synonym mappings and linguistic normalizers for the Jarvis Knowledge Engine.
Maps multilingual (Hindi, Hinglish, English) expressions to canonical property and relation keys.
"""

from typing import Dict, List, Optional, Tuple
import re


# Canonical property synonyms
PROPERTY_SYNONYMS: Dict[str, List[str]] = {
    "capital": [
        "capital", "rajdhani", "capital city", "main city"
    ],
    "currency": [
        "currency", "mudra", "paise", "rupee", "paisa", "currency code"
    ],
    "continent": [
        "continent", "mahadweep", "maha dweep"
    ],
    "prime_minister": [
        "prime minister", "pm", "pradhan mantri", "pradhanmantri", "wazir e azam", "pradhan mantri ji"
    ],
    "president": [
        "president", "rashtrapati", "rashtrapati ji"
    ],
    "inventor": [
        "inventor", "invented by", "kisne banaya", "kisne banwaya", "founder", "banaya", "banwaya", "aavishkar", "aavishkarka",
        "creator", "developed by", "kisne develop kiya", "kisne invent kiya", "father of", "builder", "architect"
    ],
    "discovered_by": [
        "discovered by", "kisne khoja", "khoj", "discovery", "discover", "kisne discover kiya"
    ],
    "author": [
        "author", "writer", "kisne likha", "likha", "lekhak", "kavi", "written by"
    ],
    "chemical_formula": [
        "chemical formula", "formula", "sutra", "chemical symbol", "symbol"
    ],
    "atomic_number": [
        "atomic number", "parmanu sankhya", "parmanu kramank", "atomic no"
    ],
    "atomic_mass": [
        "atomic mass", "parmanu dravyaman", "atomic weight"
    ],
    "speed": [
        "speed", "gati", "raftar", "speed of"
    ],
    "full_form": [
        "full form", "full-form", "stands for", "meaning", "matlab", "full name", "ka arth", "expansion"
    ],
    "date": [
        "date", "year", "saal", "tarikh", "divas", "diwas", "day"
    ],
    "highest": [
        "highest", "sabse uncha", "sabse unchi", "tallest", "peak"
    ],
    "longest": [
        "longest", "sabse lamba", "sabse lambi"
    ],
    "largest": [
        "largest", "sabse bada", "sabse badi", "biggest"
    ],
    "smallest": [
        "smallest", "sabse chota", "sabse choti"
    ],
    "national_animal": [
        "national animal", "rashtriya pashu", "rashtriya janwar"
    ],
    "national_bird": [
        "national bird", "rashtriya pakshi"
    ],
    "national_flower": [
        "national flower", "rashtriya phool"
    ],
    "national_tree": [
        "national tree", "rashtriya ped", "rashtriya vriksha"
    ],
    "national_fruit": [
        "national fruit", "rashtriya phal"
    ],
    "national_anthem": [
        "national anthem", "rashtriya gaan", "rashtra gaan"
    ],
    "national_song": [
        "national song", "rashtriya geet", "rashtra geet"
    ],
    "father_of_nation": [
        "father of nation", "father of the nation", "rashtrapita", "rashtra pita"
    ],
    "states_count": [
        "how many states", "kitne rajya", "states count", "total states", "number of states"
    ],
    "language": [
        "language", "bhasha", "official language", "zuban"
    ],
    "boiling_point": [
        "boiling point", "kathanank", "ubal", "boiling temp"
    ],
    "freezing_point": [
        "freezing point", "himank", "freezing temp"
    ],
    "distance_to_sun": [
        "distance to sun", "suraj se doori", "sun distance"
    ],
    "moons_count": [
        "how many moons", "kitne chand", "kitne moon", "satellites count"
    ],
    "closest_planet": [
        "closest planet", "sabse paas ka grah", "paas ka grah", "nearest planet"
    ],
    "volcano": [
        "highest volcano", "volcano", "jwalamukhi", "largest volcano"
    ],
    "first_prime_minister": [
        "first prime minister", "first pm", "pehla prime minister", "pehle prime minister", "pehle pradhan mantri", "first pradhan mantri", "pratham pradhan mantri"
    ],
    "first_president": [
        "first president", "pehla president", "pehle president", "pehle rashtrapati", "pratham rashtrapati"
    ],
    "independence_day": [
        "independence", "independence day", "independent", "independent kab hua", "aazad", "azad", "swatantrata", "swatantra", "aazadi", "azadi"
    ],
    "official_language": [
        "official language", "rajbhasha", "raj bhasha", "language", "bhasha", "zuban", "boli", "matribhasha"
    ],
    "largest_city": [
        "largest city", "sabse bada shahar", "bada shahar", "biggest city"
    ],
    "famous_monuments": [
        "monuments", "famous monuments", "darshaniya sthal", "kya dekhne layak hai", "pramukh sthal", "ghumne ki jagah", "landmarks", "famous landmarks", "tourist places"
    ],
    "height": [
        "height", "unchai", "elevation", "altitude", "kitna uncha", "kitni unchi"
    ],
    "length": [
        "length", "lambai", "kitna lamba", "kitni lambi"
    ],
    "temperature": [
        "temperature", "tapman", "sabse garm grah", "hottest planet", "coldest planet", "garmi"
    ],
    "order_from_sun": [
        "order from sun", "suraj se kaunsa grah", "suraj ke sabse paas", "position from sun", "surya se sthiti"
    ],
    "hardy_ramanujan_number": [
        "hardy ramanujan number", "ramanujan number", "1729"
    ],
    "known_as": [
        "known as", "kya kehte hain", "kaunse naam se jaana jaata hai", "nickname", "sobriquet", "title"
    ],
    "winter_capital": [
        "winter capital", "sheetkalin rajdhani"
    ],
    "summer_capital": [
        "summer capital", "grishmkalin rajdhani"
    ],
    "born": [
        "born", "janm", "janam", "birth", "birthday", "janamdin", "janam kab hua", "janm kab hua", "paida", "kab paida hue", "janm kab"
    ],
    "latest_version": [
        "latest version", "current version", "naya version", "latest release", "newest version", "konsa version", "kaunsa version", "version", "latest update"
    ]
}


# Pre-compiled regular expressions for fast property matching
COMPILED_PROPERTY_MATCHERS: List[Tuple[str, re.Pattern]] = []
for prop_key, syns in PROPERTY_SYNONYMS.items():
    pattern_str = r"\b(?:" + "|".join(re.escape(s) for s in sorted(syns, key=len, reverse=True)) + r")\b"
    COMPILED_PROPERTY_MATCHERS.append((prop_key, re.compile(pattern_str, re.IGNORECASE)))


def resolve_property_key(text: str) -> Optional[str]:
    """Resolves an utterance segment to the most specific canonical property key."""
    lowered = text.lower()
    matches = []
    for prop_key, regex in COMPILED_PROPERTY_MATCHERS:
        m = regex.search(lowered)
        if m:
            matches.append((prop_key, len(m.group(0))))
    if matches:
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0][0]
    return None


def clean_query_text(query: str) -> str:
    """Removes conversational fluff, articles, and question punctuation."""
    lowered = query.lower().strip()
    lowered = re.sub(r"[?!.,]", " ", lowered)
    fillers = [
        "batao", "bataiye", "bata do", "bata", "tell me", "please", "zara", "kya hai", "kya hota hai",
        "kya hoti hai", "kya he", "what is", "what's", "who is", "who's", "which is", "which's",
        "mujhe batao", "explain", "jaan na chahta hoon", "kaise", "kyun", "kyu", "why", "how",
        "bhai", "jarvis", "dost"
    ]
    cleaned = lowered
    for f in sorted(fillers, key=len, reverse=True):
        cleaned = re.sub(r"\b" + re.escape(f) + r"\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
