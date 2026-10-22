# core/wallpaper/query_enhancer.py
"""
Semantic query normalizer, visual query extractor, and stylistic enhancer.
"""

import logging
import re
from typing import List, Optional, Set, Tuple

from core.wallpaper.models import WallpaperRequest

logger = logging.getLogger("jarvis.wallpaper.enhancer")

# Curated modifier vocabulary
KNOWN_MODIFIERS = [
    "4k", "hd", "ultra hd", "8k", "dark", "minimal", "minimalist", "colorful",
    "futuristic", "gaming", "nature", "space", "galaxy", "mountain", "abstract",
    "city", "car", "architecture", "cyberpunk", "anime", "neon", "sunset",
    "forest", "ocean", "landscape", "scenery", "aesthetic"
]

STYLE_MODIFIERS = {
    "4k", "hd", "ultra hd", "8k", "dark", "minimal", "minimalist", "colorful",
    "futuristic", "neon", "sunset", "aesthetic", "light", "bright", "black", "white"
}

RANDOM_REQUEST_PATTERNS = [
    r"\b(?:koi\s+(?:bhi\s+)?achha|koi\s+sundar|achha\s+sa|random|kuch\s+achha|choose\s+karo)\b",
    r"\b(?:(?:ek\s+)?achha\s+wallpaper|any\s+good|choose\s+one|surprise\s+me|random\s+wallpaper|mere\s+liye.*choose)\b",
]


AMBIGUOUS_PATTERNS = [
    r"^(?:wallpaper\s+change\s+karo|wallpaper\s+badal\s+do|change\s+wallpaper|change\s+my\s+wallpaper|wallpaper\s+badlo)$",
    r"^(?:desktop\s+wallpaper\s+change\s+karo|desktop\s+wallpaper\s+badlo)$",
]

CURATED_RANDOM_THEMES = [
    "galaxy space nebula",
    "mountain landscape sunset",
    "nature forest minimalist",
    "cyberpunk futuristic city neon",
    "abstract dark gradient minimal",
    "ocean beach aerial",
    "deep space stars",
    "architectural modern minimalist",
]

KNOWN_ENTITY_SYNONYMS = {
    "ironman": "iron man",
    "spiderman": "spider man",
    "antman": "ant man",
    "batman": "batman",
    "superman": "superman",
    "aquaman": "aquaman",
    "captainamerica": "captain america",
    "wonderwoman": "wonder woman",
    "blackpanther": "black panther",
    "avengers": "avengers",
}



class WallpaperQueryEnhancer:
    """Extracts semantic visual subject and enhances desktop wallpaper search queries."""

    @classmethod
    def enhance_request(
        cls,
        raw_text: str,
        context_topic: Optional[str] = None,
        context_modifiers: Optional[List[str]] = None,
    ) -> WallpaperRequest:
        cleaned = raw_text.strip()
        lowered = cleaned.lower()

        # 1. Check for Ambiguous requests ("wallpaper change karo")
        for pat in AMBIGUOUS_PATTERNS:
            if re.search(pat, lowered):
                return WallpaperRequest(
                    raw_query=cleaned,
                    visual_query="",
                    modifiers=[],
                    is_random=False,
                    is_ambiguous=True,
                )

        # 2. Check for Random/Curated requests ("koi achha wallpaper laga do")
        is_random = any(re.search(pat, lowered) for pat in RANDOM_REQUEST_PATTERNS)
        if is_random and not any(w in lowered for w in ("galaxy", "space", "mountain", "car", "nature", "gaming", "anime")):
            return WallpaperRequest(
                raw_query=cleaned,
                visual_query="aesthetic desktop",
                modifiers=["4k", "landscape"],
                is_random=True,
                is_ambiguous=False,
            )

        # 3. Check for Conversational Refinements ("thoda dark wala", "aur dark", "dusra wala")
        is_refinement = False
        active_subject = ""
        if context_topic and (
            any(w in lowered for w in ("thoda", "wala", "wali", "dusra", "aur", "next", "another", "more"))
            or (len(lowered.split()) <= 2 and any(w in lowered for w in STYLE_MODIFIERS))
        ):
            is_refinement = True
            active_subject = context_topic

        # 4. Extract Modifiers
        found_modifiers: List[str] = []
        for mod in KNOWN_MODIFIERS:
            pattern = rf"\b{re.escape(mod)}\b"
            if re.search(pattern, lowered):
                found_modifiers.append(mod)

        # Inherit context modifiers if refining
        if is_refinement and context_modifiers:
            for cm in context_modifiers:
                if cm not in found_modifiers:
                    found_modifiers.append(cm)

        # 5. Extract Core Visual Subject
        # Strip filler words
        filler_patterns = [
            r"\b(?:jarvis|mujhe|ek|ka|ke|liye|desktop|laptop|screen|par|pe|karo|kar|do|laga|lagao|lagana|set|chahiye|dhoondho|aur|please|bhai|wallpaper|wallpapers|background|photo|image|picture)\b",
            r"\b(?:thoda|aur|wala|wali|wale|thoda\s+sa|achha|beautiful|sundar|badal|change)\b",
        ]
        visual_candidate = lowered
        for pat in filler_patterns:
            visual_candidate = re.sub(pat, " ", visual_candidate, flags=re.IGNORECASE)

        visual_candidate = re.sub(r"\s+", " ", visual_candidate).strip()
        for syn_k, syn_v in KNOWN_ENTITY_SYNONYMS.items():
            visual_candidate = re.sub(rf"\b{re.escape(syn_k)}\b", syn_v, visual_candidate, flags=re.IGNORECASE)
        visual_candidate = re.sub(r"\s+", " ", visual_candidate).strip()

        # Strip quality/resolution tags from visual subject (retained in found_modifiers)
        for qmod in ("4k", "8k", "ultra hd", "hd"):
            visual_candidate = re.sub(rf"\b{re.escape(qmod)}\b", " ", visual_candidate, flags=re.IGNORECASE)
        visual_candidate = re.sub(r"\s+", " ", visual_candidate).strip()

        # If refining and active_subject exists, merge context subject only for modifier refinements
        if is_refinement and active_subject:
            if not visual_candidate:
                visual_candidate = active_subject
            elif all(w in STYLE_MODIFIERS for w in visual_candidate.split()):
                visual_candidate = f"{visual_candidate} {active_subject}".strip()
            else:
                # User specified a distinct new subject; do not contaminate with previous topic
                is_refinement = False

        if not visual_candidate and is_random:
            visual_candidate = "landscape"

        # Fallback if entirely stripped
        if not visual_candidate:
            visual_candidate = "nature" if "nature" in lowered else "minimal"


        # 6. Enhance search query for desktop wallpapers
        enhancements = []
        if visual_candidate:
            enhancements.append(visual_candidate)

        for mod in found_modifiers:
            if mod not in visual_candidate:
                enhancements.append(mod)

        # Ensure desktop wallpaper orientation cues
        if "wallpaper" not in enhancements and "desktop" not in enhancements:
            enhancements.append("desktop wallpaper")

        enhanced_visual = " ".join(enhancements).strip()

        return WallpaperRequest(
            raw_query=cleaned,
            visual_query=visual_candidate,
            modifiers=found_modifiers,
            is_random=is_random,
            is_ambiguous=False,
            context_refinement=is_refinement,
        )
