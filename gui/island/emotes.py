# gui/island/emotes.py
"""JARVIS Emote System — temporary emotional overlays (never replace character).

Emotes: EMOTE_LOVE, EMOTE_PROUD, EMOTE_HAPPY, EMOTE_SURPRISED, EMOTE_CONFUSED, EMOTE_SAD.
Lifecycle: pop -> hold -> fade -> previous state. Driven by CharacterController;
this module owns metadata (duration, particle kind, sound cue, eye shape).
"""

from enum import Enum


class Emote(str, Enum):
    LOVE = "love"
    PROUD = "proud"
    HAPPY = "happy"
    SURPRISED = "surprised"
    CONFUSED = "confused"
    SAD = "sad"


EMOTE_CONFIG = {
    Emote.LOVE: {"duration": 1.8, "sound": "love", "eye": "love_hearts", "particles": "hearts"},
    Emote.PROUD: {"duration": 1.8, "sound": "proud", "eye": "happy", "particles": "stars"},
    Emote.HAPPY: {"duration": 1.6, "sound": "greet", "eye": "happy", "particles": "sparkles"},
    Emote.SURPRISED: {"duration": 1.4, "sound": "pop", "eye": "wide", "particles": "rings"},
    Emote.CONFUSED: {"duration": 1.6, "sound": "think", "eye": "pill", "particles": "question"},
    Emote.SAD: {"duration": 1.6, "sound": "sleep", "eye": "closed", "particles": "drops"},
}


def emote_from_string(name: str) -> Emote:
    key = str(name or "").strip().lower().replace("emote_", "")
    for e in Emote:
        if e.value == key:
            return e
    return Emote.HAPPY
