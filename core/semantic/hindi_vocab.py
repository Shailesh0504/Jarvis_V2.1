# core/semantic/hindi_vocab.py
"""
Hindi / Hinglish Semantic Vocabulary Engine for Jarvis V2.

Provides structured semantic lookup across 9 vocabulary categories:
  MOVEMENT, DIRECTION, OBJECT_REFERENCE, BODY_STATE, EMOTION,
  TIME, ACTION, QUANTITY, REFERENCE

Design Principles:
  - O(1) hash-based lookup (no regex on hot path)
  - No command execution — pure classification layer
  - Integrates with normalizer, speech_understanding, contextual_resolver
  - Action words enrich existing parsers; they do NOT bypass them

Usage:
    from core.semantic.hindi_vocab import HindiVocabEngine, HindiVocabCategory

    cat, concept = HindiVocabEngine.classify("jaana")
    # → (HindiVocabCategory.MOVEMENT, "DEPART")

    entities = HindiVocabEngine.enrich_speech_entities("abhi screenshot lo")
    # → {"time_ref": "NOW", "action": "CAPTURE"}
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Tuple

import re


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class HindiVocabCategory(str, Enum):
    """Semantic category for a Hindi/Hinglish vocabulary word."""
    MOVEMENT        = "MOVEMENT"
    DIRECTION       = "DIRECTION"
    OBJECT_REFERENCE = "OBJECT_REFERENCE"
    BODY_STATE      = "BODY_STATE"
    EMOTION         = "EMOTION"
    TIME            = "TIME"
    ACTION          = "ACTION"
    QUANTITY        = "QUANTITY"
    REFERENCE       = "REFERENCE"


class MovementConcept(str, Enum):
    ARRIVE  = "ARRIVE"
    DEPART  = "DEPART"
    WALK    = "WALK"
    STOP    = "STOP"
    SIT     = "SIT"
    RISE    = "RISE"
    RUN     = "RUN"
    RETURN  = "RETURN"
    TURN    = "TURN"
    JUMP    = "JUMP"
    FALL    = "FALL"
    CLIMB   = "CLIMB"
    DESCEND = "DESCEND"


class DirectionConcept(str, Enum):
    UP       = "UP"
    DOWN     = "DOWN"
    FORWARD  = "FORWARD"
    BACK     = "BACK"
    HERE_DIR = "HERE_DIR"   # idhar — directional "this way"
    THERE_DIR = "THERE_DIR" # udhar — directional "that way"
    HERE     = "HERE"       # yahan — locative "here"
    THERE    = "THERE"      # wahan — locative "there"
    INSIDE   = "INSIDE"
    OUTSIDE  = "OUTSIDE"
    LEFT     = "LEFT"
    RIGHT    = "RIGHT"
    NEAR     = "NEAR"
    FAR      = "FAR"
    STRAIGHT = "STRAIGHT"
    CENTER   = "CENTER"
    DIAGONAL = "DIAGONAL"
    AROUND   = "AROUND"


class ObjectRefConcept(str, Enum):
    THIS     = "THIS"   # ye / iska / iski / isse / isko / inhe / isme
    THAT     = "THAT"   # wo / uska / uski / usse / usko / unhe / usme
    RELATIVE = "RELATIVE" # jiska / jiski / jiske / jisse / jisko / jinhe / jisme


class BodyStateConcept(str, Enum):
    HUNGER      = "HUNGER"
    THIRST      = "THIRST"
    SLEEP_STATE = "SLEEP_STATE"
    FATIGUE     = "FATIGUE"
    PAIN        = "PAIN"
    HOT         = "HOT"
    COLD        = "COLD"
    REST        = "REST"
    SICK        = "SICK"
    DIZZY       = "DIZZY"
    HEALTH      = "HEALTH"


class EmotionConcept(str, Enum):
    JOY        = "JOY"
    SADNESS    = "SADNESS"
    ANGER      = "ANGER"
    LOVE       = "LOVE"
    HATRED     = "HATRED"
    FEAR       = "FEAR"
    ANXIETY    = "ANXIETY"
    WORRY      = "WORRY"
    EXCITEMENT = "EXCITEMENT"
    BOREDOM    = "BOREDOM"
    CALM       = "CALM"
    CONFUSED   = "CONFUSED"
    CONFIDENT  = "CONFIDENT"
    FATIGUE    = "FATIGUE"


class TimeRefConcept(str, Enum):
    NOW                   = "NOW"
    LATER                 = "LATER"
    BEFORE                = "BEFORE"
    YESTERDAY_OR_TOMORROW = "YESTERDAY_OR_TOMORROW"  # kal — disambiguated at runtime
    TODAY                 = "TODAY"
    DAY_AFTER             = "DAY_AFTER"
    MORNING               = "MORNING"
    AFTERNOON             = "AFTERNOON"
    EVENING               = "EVENING"
    NIGHT                 = "NIGHT"
    DAILY                 = "DAILY"
    SOMETIMES             = "SOMETIMES"
    SOON                  = "SOON"
    LATE                  = "LATE"
    ALWAYS                = "ALWAYS"
    NEVER                 = "NEVER"


class ActionVerbConcept(str, Enum):
    OPEN     = "OPEN"
    CLOSE    = "CLOSE"
    PLAY     = "PLAY"
    STOP     = "STOP"
    SEND     = "SEND"
    BRING    = "BRING"
    TAKE     = "TAKE"
    PLACE    = "PLACE"
    REMOVE   = "REMOVE"
    SHOW     = "SHOW"
    HIDE     = "HIDE"
    WRITE    = "WRITE"
    READ     = "READ"
    SPEAK    = "SPEAK"
    LISTEN   = "LISTEN"
    SEARCH   = "SEARCH"
    COPY     = "COPY"
    PASTE    = "PASTE"
    REFRESH  = "REFRESH"
    DOWNLOAD = "DOWNLOAD"
    UPLOAD   = "UPLOAD"
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"


class QuantityConcept(str, Enum):
    SMALL    = "SMALL"   # thoda
    LARGE    = "LARGE"   # zyada
    LESS     = "LESS"    # kam
    ALL      = "ALL"     # sab
    SOME     = "SOME"    # kuch
    ANY      = "ANY"     # koi
    ONE      = "ONE"     # ek
    TWO      = "TWO"     # do
    ALL_OF   = "ALL_OF"  # saare
    HALF     = "HALF"    # aadha
    FULL     = "FULL"    # poora
    ZERO     = "ZERO"    # bilkul nahi / shunya
    MULTIPLE = "MULTIPLE"# dugna / teen / multiple


class ReferenceConcept(str, Enum):
    FIRST    = "FIRST"    # ye / ye wala / pehla
    SECOND   = "SECOND"   # doosra / doosra wala / wo wala
    THIRD    = "THIRD"    # teesra / teesra wala
    FOURTH   = "FOURTH"   # chautha / chautha wala
    LAST     = "LAST"     # last wala / aakhri
    TOP      = "TOP"      # upar wala
    BOTTOM   = "BOTTOM"   # niche wala
    PREVIOUS = "PREVIOUS" # pichla
    NEXT     = "NEXT"     # agla
    MIDDLE   = "MIDDLE"   # beech wala
    SAME     = "SAME"     # wahi wala
    NEW_REF  = "NEW_REF"  # naya wala
    OLD_REF  = "OLD_REF"  # purana wala


# ---------------------------------------------------------------------------
# Vocabulary Maps  (word → concept string, all lowercase keys)
# ---------------------------------------------------------------------------

_MOVEMENT_MAP: Dict[str, str] = {
    # ARRIVE
    "aana":        MovementConcept.ARRIVE,
    "aao":         MovementConcept.ARRIVE,
    "aaiye":       MovementConcept.ARRIVE,
    "aa":          MovementConcept.ARRIVE,
    "aa raha":     MovementConcept.ARRIVE,
    "aa rahi":     MovementConcept.ARRIVE,
    "aa rahe":     MovementConcept.ARRIVE,
    "aa gaya":     MovementConcept.ARRIVE,
    "aa gayi":     MovementConcept.ARRIVE,
    "aa gaye":     MovementConcept.ARRIVE,
    "aa jana":     MovementConcept.ARRIVE,
    "padharna":    MovementConcept.ARRIVE,
    "padharo":     MovementConcept.ARRIVE,
    "padhariye":   MovementConcept.ARRIVE,
    "dakhil hona": MovementConcept.ARRIVE,
    "arrival":     MovementConcept.ARRIVE,
    "arrive":      MovementConcept.ARRIVE,
    "reach":       MovementConcept.ARRIVE,
    "enter karna": MovementConcept.ARRIVE,
    "enter karo":  MovementConcept.ARRIVE,

    # DEPART
    "jaana":       MovementConcept.DEPART,
    "jana":        MovementConcept.DEPART,
    "jao":         MovementConcept.DEPART,
    "jaiye":       MovementConcept.DEPART,
    "ja":          MovementConcept.DEPART,
    "ja raha":     MovementConcept.DEPART,
    "ja rahi":     MovementConcept.DEPART,
    "ja rahe":     MovementConcept.DEPART,
    "chala gaya":  MovementConcept.DEPART,
    "chali gayi":  MovementConcept.DEPART,
    "chale gaye":  MovementConcept.DEPART,
    "chale jao":   MovementConcept.DEPART,
    "nikalna":     MovementConcept.DEPART,
    "niklo":       MovementConcept.DEPART,
    "nikal jao":   MovementConcept.DEPART,
    "rawana hona": MovementConcept.DEPART,
    "vida hona":   MovementConcept.DEPART,
    "depart":      MovementConcept.DEPART,
    "departure":   MovementConcept.DEPART,
    "leave":       MovementConcept.DEPART,
    "exit":        MovementConcept.DEPART,

    # WALK
    "chalna":       MovementConcept.WALK,
    "chalo":        MovementConcept.WALK,
    "chaliye":      MovementConcept.WALK,
    "chal":         MovementConcept.WALK,
    "chal raha":    MovementConcept.WALK,
    "chal rahi":    MovementConcept.WALK,
    "chal rahe":    MovementConcept.WALK,
    "paidal":       MovementConcept.WALK,
    "paidal chalna":MovementConcept.WALK,
    "tahalna":      MovementConcept.WALK,
    "tahlo":        MovementConcept.WALK,
    "aage chalna":  MovementConcept.WALK,
    "walk":         MovementConcept.WALK,
    "stroll":       MovementConcept.WALK,

    # STOP
    "rukna":     MovementConcept.STOP,
    "ruko":      MovementConcept.STOP,
    "rukiye":    MovementConcept.STOP,
    "ruk":       MovementConcept.STOP,
    "ruk jao":   MovementConcept.STOP,
    "ruk gaya":  MovementConcept.STOP,
    "thamna":    MovementConcept.STOP,
    "thamo":     MovementConcept.STOP,
    "theharna":  MovementConcept.STOP,
    "thehro":    MovementConcept.STOP,
    "stop":      MovementConcept.STOP,
    "halt":      MovementConcept.STOP,
    "freeze":    MovementConcept.STOP,
    "pause":     MovementConcept.STOP,

    # SIT
    "baithna":   MovementConcept.SIT,
    "baitho":    MovementConcept.SIT,
    "baithiye":  MovementConcept.SIT,
    "baith":     MovementConcept.SIT,
    "baith jao": MovementConcept.SIT,
    "baith gaya":MovementConcept.SIT,
    "virajna":   MovementConcept.SIT,
    "virajiye":  MovementConcept.SIT,
    "sit":       MovementConcept.SIT,
    "sit down":  MovementConcept.SIT,

    # RISE
    "uthna":      MovementConcept.RISE,
    "utho":       MovementConcept.RISE,
    "uthiye":     MovementConcept.RISE,
    "uth":        MovementConcept.RISE,
    "uth jao":    MovementConcept.RISE,
    "uth gaya":   MovementConcept.RISE,
    "khade hona": MovementConcept.RISE,
    "khada ho":   MovementConcept.RISE,
    "jagna":      MovementConcept.RISE,
    "jaago":      MovementConcept.RISE,
    "wake up":    MovementConcept.RISE,
    "get up":     MovementConcept.RISE,
    "rise":       MovementConcept.RISE,
    "stand up":   MovementConcept.RISE,

    # RUN
    "daudna":    MovementConcept.RUN,
    "daudo":     MovementConcept.RUN,
    "daudiye":   MovementConcept.RUN,
    "daud":      MovementConcept.RUN,
    "daud raha": MovementConcept.RUN,
    "bhagna":    MovementConcept.RUN,
    "bhago":     MovementConcept.RUN,
    "bhag":      MovementConcept.RUN,
    "bhag jao":  MovementConcept.RUN,
    "lapakna":   MovementConcept.RUN,
    "lapko":     MovementConcept.RUN,
    "run":       MovementConcept.RUN,
    "sprint":    MovementConcept.RUN,
    "rush":      MovementConcept.RUN,

    # RETURN
    "lautna":      MovementConcept.RETURN,
    "lauto":       MovementConcept.RETURN,
    "lautiye":     MovementConcept.RETURN,
    "laut":        MovementConcept.RETURN,
    "laut aao":    MovementConcept.RETURN,
    "wapas aana":  MovementConcept.RETURN,
    "wapas jaana": MovementConcept.RETURN,
    "wapas":       MovementConcept.RETURN,
    "vapas":       MovementConcept.RETURN,
    "vapas aana":  MovementConcept.RETURN,
    "return":      MovementConcept.RETURN,
    "come back":   MovementConcept.RETURN,
    "go back":     MovementConcept.RETURN,

    # TURN
    "mudna":    MovementConcept.TURN,
    "mudo":     MovementConcept.TURN,
    "mudiye":   MovementConcept.TURN,
    "mud":      MovementConcept.TURN,
    "mud jao":  MovementConcept.TURN,
    "ghoomna":  MovementConcept.TURN,
    "ghoomo":   MovementConcept.TURN,
    "turn":     MovementConcept.TURN,
    "rotate":   MovementConcept.TURN,

    # JUMP
    "kudna":    MovementConcept.JUMP,
    "kudo":     MovementConcept.JUMP,
    "kud":      MovementConcept.JUMP,
    "chhalang": MovementConcept.JUMP,
    "jump":     MovementConcept.JUMP,
    "leap":     MovementConcept.JUMP,

    # FALL
    "girna":    MovementConcept.FALL,
    "giro":     MovementConcept.FALL,
    "gir":      MovementConcept.FALL,
    "gir gaya": MovementConcept.FALL,
    "fall":     MovementConcept.FALL,
    "drop":     MovementConcept.FALL,

    # CLIMB
    "chadhna":  MovementConcept.CLIMB,
    "chadho":   MovementConcept.CLIMB,
    "chadh":    MovementConcept.CLIMB,
    "climb":    MovementConcept.CLIMB,
    "ascend":   MovementConcept.CLIMB,

    # DESCEND
    "utarna":   MovementConcept.DESCEND,
    "utro":     MovementConcept.DESCEND,
    "utar":     MovementConcept.DESCEND,
    "descend":  MovementConcept.DESCEND,
}

_DIRECTION_MAP: Dict[str, str] = {
    # UP
    "upar":          DirectionConcept.UP,
    "uppar":         DirectionConcept.UP,
    "uper":          DirectionConcept.UP,
    "up":            DirectionConcept.UP,
    "above":         DirectionConcept.UP,
    "top":           DirectionConcept.UP,
    "upward":        DirectionConcept.UP,
    "upwards":       DirectionConcept.UP,
    "overhead":      DirectionConcept.UP,
    "ooncha":        DirectionConcept.UP,
    "uncha":         DirectionConcept.UP,
    "sir par":       DirectionConcept.UP,
    "upar ki taraf": DirectionConcept.UP,

    # DOWN
    "niche":          DirectionConcept.DOWN,
    "neeche":         DirectionConcept.DOWN,
    "nichhe":         DirectionConcept.DOWN,
    "down":           DirectionConcept.DOWN,
    "below":          DirectionConcept.DOWN,
    "bottom":         DirectionConcept.DOWN,
    "downward":       DirectionConcept.DOWN,
    "downwards":      DirectionConcept.DOWN,
    "underneath":     DirectionConcept.DOWN,
    "niche ki taraf": DirectionConcept.DOWN,

    # FORWARD
    "aage":          DirectionConcept.FORWARD,
    "agge":          DirectionConcept.FORWARD,
    "samne":         DirectionConcept.FORWARD,
    "front":         DirectionConcept.FORWARD,
    "forward":       DirectionConcept.FORWARD,
    "forwards":      DirectionConcept.FORWARD,
    "ahead":         DirectionConcept.FORWARD,
    "aage ki taraf": DirectionConcept.FORWARD,

    # BACK
    "peeche":          DirectionConcept.BACK,
    "piche":           DirectionConcept.BACK,
    "back":            DirectionConcept.BACK,
    "backward":        DirectionConcept.BACK,
    "backwards":       DirectionConcept.BACK,
    "behind":          DirectionConcept.BACK,
    "rear":            DirectionConcept.BACK,
    "peeche ki taraf": DirectionConcept.BACK,

    # HERE_DIR
    "idhar":      DirectionConcept.HERE_DIR,
    "is taraf":   DirectionConcept.HERE_DIR,
    "iss taraf":  DirectionConcept.HERE_DIR,
    "this side":  DirectionConcept.HERE_DIR,
    "this way":   DirectionConcept.HERE_DIR,

    # THERE_DIR
    "udhar":      DirectionConcept.THERE_DIR,
    "us taraf":   DirectionConcept.THERE_DIR,
    "uss taraf":  DirectionConcept.THERE_DIR,
    "that side":  DirectionConcept.THERE_DIR,
    "that way":   DirectionConcept.THERE_DIR,

    # HERE (locative)
    "yahan":      DirectionConcept.HERE,
    "yaha":       DirectionConcept.HERE,
    "yahan par":  DirectionConcept.HERE,
    "idhar hi":   DirectionConcept.HERE,
    "yahi":       DirectionConcept.HERE,
    "right here": DirectionConcept.HERE,

    # THERE (locative)
    "wahan":       DirectionConcept.THERE,
    "waha":        DirectionConcept.THERE,
    "wahan par":   DirectionConcept.THERE,
    "udhar hi":    DirectionConcept.THERE,
    "wahi":        DirectionConcept.THERE,
    "right there": DirectionConcept.THERE,

    # INSIDE
    "andar":    DirectionConcept.INSIDE,
    "bheetar":  DirectionConcept.INSIDE,
    "bhitar":   DirectionConcept.INSIDE,
    "inside":   DirectionConcept.INSIDE,
    "within":   DirectionConcept.INSIDE,
    "ke andar": DirectionConcept.INSIDE,

    # OUTSIDE
    "bahar":    DirectionConcept.OUTSIDE,
    "baahar":   DirectionConcept.OUTSIDE,
    "bahir":    DirectionConcept.OUTSIDE,
    "out":      DirectionConcept.OUTSIDE,
    "outside":  DirectionConcept.OUTSIDE,
    "outdoors": DirectionConcept.OUTSIDE,
    "ke bahar": DirectionConcept.OUTSIDE,

    # LEFT
    "left":        DirectionConcept.LEFT,
    "baye":        DirectionConcept.LEFT,
    "bayen":       DirectionConcept.LEFT,
    "baaye":       DirectionConcept.LEFT,
    "baayen":      DirectionConcept.LEFT,
    "ulta haath":  DirectionConcept.LEFT,
    "left side":   DirectionConcept.LEFT,

    # RIGHT
    "right":        DirectionConcept.RIGHT,
    "daye":         DirectionConcept.RIGHT,
    "dayen":        DirectionConcept.RIGHT,
    "daaye":        DirectionConcept.RIGHT,
    "daayen":       DirectionConcept.RIGHT,
    "seedha haath": DirectionConcept.RIGHT,
    "right side":   DirectionConcept.RIGHT,

    # NEAR
    "pass":       DirectionConcept.NEAR,
    "paas":       DirectionConcept.NEAR,
    "kareeb":     DirectionConcept.NEAR,
    "qarib":      DirectionConcept.NEAR,
    "nazdeek":    DirectionConcept.NEAR,
    "nazdik":     DirectionConcept.NEAR,
    "samip":      DirectionConcept.NEAR,
    "near":       DirectionConcept.NEAR,
    "nearby":     DirectionConcept.NEAR,
    "close":      DirectionConcept.NEAR,
    "bagal mein": DirectionConcept.NEAR,

    # FAR
    "door":       DirectionConcept.FAR,
    "dur":        DirectionConcept.FAR,
    "doori":      DirectionConcept.FAR,
    "faasle par": DirectionConcept.FAR,
    "far":        DirectionConcept.FAR,
    "distant":    DirectionConcept.FAR,
    "away":       DirectionConcept.FAR,

    # STRAIGHT
    "seedha":   DirectionConcept.STRAIGHT,
    "sidha":    DirectionConcept.STRAIGHT,
    "straight": DirectionConcept.STRAIGHT,
    "direct":   DirectionConcept.STRAIGHT,

    # CENTER
    "beech":      DirectionConcept.CENTER,
    "beech mein": DirectionConcept.CENTER,
    "center":     DirectionConcept.CENTER,
    "centre":     DirectionConcept.CENTER,
    "middle":     DirectionConcept.CENTER,

    # DIAGONAL
    "tirchha":  DirectionConcept.DIAGONAL,
    "diagonal": DirectionConcept.DIAGONAL,
    "cross":    DirectionConcept.DIAGONAL,

    # AROUND
    "charon taraf":  DirectionConcept.AROUND,
    "chaaron taraf": DirectionConcept.AROUND,
    "all around":    DirectionConcept.AROUND,
    "charon or":     DirectionConcept.AROUND,
}

_OBJECT_REF_MAP: Dict[str, str] = {
    # THIS-proximal
    "ye":       ObjectRefConcept.THIS,
    "yeh":      ObjectRefConcept.THIS,
    "iska":     ObjectRefConcept.THIS,
    "iski":     ObjectRefConcept.THIS,
    "iske":     ObjectRefConcept.THIS,
    "isse":     ObjectRefConcept.THIS,
    "is se":    ObjectRefConcept.THIS,
    "iss se":   ObjectRefConcept.THIS,
    "isko":     ObjectRefConcept.THIS,
    "isey":     ObjectRefConcept.THIS,
    "ise":      ObjectRefConcept.THIS,
    "inhe":     ObjectRefConcept.THIS,
    "inhein":   ObjectRefConcept.THIS,
    "isme":     ObjectRefConcept.THIS,
    "is mein":  ObjectRefConcept.THIS,
    "iss mein": ObjectRefConcept.THIS,
    "inka":     ObjectRefConcept.THIS,
    "inki":     ObjectRefConcept.THIS,
    "inke":     ObjectRefConcept.THIS,
    "inse":     ObjectRefConcept.THIS,
    "inme":     ObjectRefConcept.THIS,
    "inko":     ObjectRefConcept.THIS,
    "this":     ObjectRefConcept.THIS,

    # THAT-distal
    "wo":       ObjectRefConcept.THAT,
    "woh":      ObjectRefConcept.THAT,
    "uska":     ObjectRefConcept.THAT,
    "uski":     ObjectRefConcept.THAT,
    "uske":     ObjectRefConcept.THAT,
    "usse":     ObjectRefConcept.THAT,
    "us se":    ObjectRefConcept.THAT,
    "uss se":   ObjectRefConcept.THAT,
    "usko":     ObjectRefConcept.THAT,
    "usey":     ObjectRefConcept.THAT,
    "use":      ObjectRefConcept.THAT,
    "unhe":     ObjectRefConcept.THAT,
    "unhein":   ObjectRefConcept.THAT,
    "usme":     ObjectRefConcept.THAT,
    "us mein":  ObjectRefConcept.THAT,
    "uss mein": ObjectRefConcept.THAT,
    "unka":     ObjectRefConcept.THAT,
    "unki":     ObjectRefConcept.THAT,
    "unke":     ObjectRefConcept.THAT,
    "unse":     ObjectRefConcept.THAT,
    "unme":     ObjectRefConcept.THAT,
    "unko":     ObjectRefConcept.THAT,
    "that":     ObjectRefConcept.THAT,

    # RELATIVE
    "jiska": ObjectRefConcept.RELATIVE,
    "jiski": ObjectRefConcept.RELATIVE,
    "jiske": ObjectRefConcept.RELATIVE,
    "jisse": ObjectRefConcept.RELATIVE,
    "jisko": ObjectRefConcept.RELATIVE,
    "jinhe": ObjectRefConcept.RELATIVE,
    "jisme": ObjectRefConcept.RELATIVE,
}

_BODY_STATE_MAP: Dict[str, str] = {
    # HUNGER
    "bhookh":          BodyStateConcept.HUNGER,
    "bhukh":           BodyStateConcept.HUNGER,
    "bhookha":         BodyStateConcept.HUNGER,
    "bhookhi":         BodyStateConcept.HUNGER,
    "bhookhe":         BodyStateConcept.HUNGER,
    "hungry":          BodyStateConcept.HUNGER,
    "starving":        BodyStateConcept.HUNGER,
    "bhookh lagi":     BodyStateConcept.HUNGER,
    "bhookh lagi hai": BodyStateConcept.HUNGER,

    # THIRST
    "pyaas":          BodyStateConcept.THIRST,
    "pyas":           BodyStateConcept.THIRST,
    "pyasa":          BodyStateConcept.THIRST,
    "pyasi":          BodyStateConcept.THIRST,
    "thirsty":        BodyStateConcept.THIRST,
    "pyaas lagi":     BodyStateConcept.THIRST,
    "pyaas lagi hai": BodyStateConcept.THIRST,

    # SLEEP
    "neend":             BodyStateConcept.SLEEP_STATE,
    "nind":              BodyStateConcept.SLEEP_STATE,
    "sona":              BodyStateConcept.SLEEP_STATE,
    "so jao":            BodyStateConcept.SLEEP_STATE,
    "so gaya":           BodyStateConcept.SLEEP_STATE,
    "sleepy":            BodyStateConcept.SLEEP_STATE,
    "drowsy":            BodyStateConcept.SLEEP_STATE,
    "aalsi":             BodyStateConcept.SLEEP_STATE,
    "neend aa rahi":     BodyStateConcept.SLEEP_STATE,
    "neend aa rahi hai": BodyStateConcept.SLEEP_STATE,

    # FATIGUE
    "thakan":     BodyStateConcept.FATIGUE,
    "thakaan":    BodyStateConcept.FATIGUE,
    "thakawat":   BodyStateConcept.FATIGUE,
    "thaka":      BodyStateConcept.FATIGUE,
    "thaki":      BodyStateConcept.FATIGUE,
    "thake":      BodyStateConcept.FATIGUE,
    "tired":      BodyStateConcept.FATIGUE,
    "fatigue":    BodyStateConcept.FATIGUE,
    "exhausted":  BodyStateConcept.FATIGUE,
    "thak gaya":  BodyStateConcept.FATIGUE,
    "thak gayi":  BodyStateConcept.FATIGUE,
    "thak gaye":  BodyStateConcept.FATIGUE,

    # PAIN
    "dard":       BodyStateConcept.PAIN,
    "dukhna":     BodyStateConcept.PAIN,
    "peeda":      BodyStateConcept.PAIN,
    "pain":       BodyStateConcept.PAIN,
    "ache":       BodyStateConcept.PAIN,
    "headache":   BodyStateConcept.PAIN,
    "sir dard":   BodyStateConcept.PAIN,
    "badan dard": BodyStateConcept.PAIN,
    "kamar dard": BodyStateConcept.PAIN,

    # HOT
    "garmi":              BodyStateConcept.HOT,
    "garam":              BodyStateConcept.HOT,
    "paseena":            BodyStateConcept.HOT,
    "heat":               BodyStateConcept.HOT,
    "hot":                BodyStateConcept.HOT,
    "garmi lag rahi":     BodyStateConcept.HOT,
    "garmi lag rahi hai": BodyStateConcept.HOT,

    # COLD
    "sardi":              BodyStateConcept.COLD,
    "thand":              BodyStateConcept.COLD,
    "thanda":             BodyStateConcept.COLD,
    "thandi":             BodyStateConcept.COLD,
    "cold":               BodyStateConcept.COLD,
    "freezing":           BodyStateConcept.COLD,
    "sardi lag rahi":     BodyStateConcept.COLD,
    "thand lag rahi":     BodyStateConcept.COLD,
    "thand lag rahi hai": BodyStateConcept.COLD,

    # REST
    "aaram":       BodyStateConcept.REST,
    "araam":       BodyStateConcept.REST,
    "sukoon":      BodyStateConcept.REST,
    "vishram":     BodyStateConcept.REST,
    "rest":        BodyStateConcept.REST,
    "relax":       BodyStateConcept.REST,
    "aaram karna": BodyStateConcept.REST,

    # SICK
    "tabiyat kharab": BodyStateConcept.SICK,
    "bimar":          BodyStateConcept.SICK,
    "beemar":         BodyStateConcept.SICK,
    "unwell":         BodyStateConcept.SICK,
    "sick":           BodyStateConcept.SICK,
    "bukhar":         BodyStateConcept.SICK,
    "fever":          BodyStateConcept.SICK,
    "kamzori":        BodyStateConcept.SICK,

    # DIZZY
    "chakkar":    BodyStateConcept.DIZZY,
    "dizzy":      BodyStateConcept.DIZZY,
    "giddiness":  BodyStateConcept.DIZZY,

    # HEALTH
    "swasth":     BodyStateConcept.HEALTH,
    "tandoorust": BodyStateConcept.HEALTH,
    "healthy":    BodyStateConcept.HEALTH,
    "fit":        BodyStateConcept.HEALTH,
    "energetic":  BodyStateConcept.HEALTH,
}

_EMOTION_MAP: Dict[str, str] = {
    # JOY
    "khushi":    EmotionConcept.JOY,
    "khush":     EmotionConcept.JOY,
    "aanand":    EmotionConcept.JOY,
    "prasannta": EmotionConcept.JOY,
    "happy":     EmotionConcept.JOY,
    "joyful":    EmotionConcept.JOY,
    "cheerful":  EmotionConcept.JOY,
    "glad":      EmotionConcept.JOY,
    "pleased":   EmotionConcept.JOY,
    "mauj":      EmotionConcept.JOY,
    "maza":      EmotionConcept.JOY,
    "masti":     EmotionConcept.JOY,

    # SADNESS
    "dukh":          EmotionConcept.SADNESS,
    "udas":          EmotionConcept.SADNESS,
    "udasi":         EmotionConcept.SADNESS,
    "gham":          EmotionConcept.SADNESS,
    "sad":           EmotionConcept.SADNESS,
    "sorrow":        EmotionConcept.SADNESS,
    "unhappy":       EmotionConcept.SADNESS,
    "upset":         EmotionConcept.SADNESS,
    "rona":          EmotionConcept.SADNESS,
    "dil toot gaya": EmotionConcept.SADNESS,

    # ANGER
    "gussa":         EmotionConcept.ANGER,
    "krodh":         EmotionConcept.ANGER,
    "naraz":         EmotionConcept.ANGER,
    "narazgi":       EmotionConcept.ANGER,
    "angry":         EmotionConcept.ANGER,
    "mad":           EmotionConcept.ANGER,
    "furious":       EmotionConcept.ANGER,
    "irritated":     EmotionConcept.ANGER,
    "annoyed":       EmotionConcept.ANGER,
    "gussa aa raha": EmotionConcept.ANGER,

    # LOVE
    "pyaar":    EmotionConcept.LOVE,
    "pyar":     EmotionConcept.LOVE,
    "prem":     EmotionConcept.LOVE,
    "mohabbat": EmotionConcept.LOVE,
    "chaahat":  EmotionConcept.LOVE,
    "ishq":     EmotionConcept.LOVE,
    "love":     EmotionConcept.LOVE,
    "affection":EmotionConcept.LOVE,
    "adore":    EmotionConcept.LOVE,

    # HATRED
    "nafrat":  EmotionConcept.HATRED,
    "ghin":    EmotionConcept.HATRED,
    "hate":    EmotionConcept.HATRED,
    "hatred":  EmotionConcept.HATRED,
    "disgust": EmotionConcept.HATRED,
    "dislike": EmotionConcept.HATRED,

    # FEAR
    "dar":           EmotionConcept.FEAR,
    "darr":          EmotionConcept.FEAR,
    "khauf":         EmotionConcept.FEAR,
    "bhay":          EmotionConcept.FEAR,
    "scared":        EmotionConcept.FEAR,
    "afraid":        EmotionConcept.FEAR,
    "fear":          EmotionConcept.FEAR,
    "panic":         EmotionConcept.FEAR,
    "darr lag raha": EmotionConcept.FEAR,

    # ANXIETY
    "tension":         EmotionConcept.ANXIETY,
    "chinta":          EmotionConcept.ANXIETY,
    "stress":          EmotionConcept.ANXIETY,
    "fikar":           EmotionConcept.ANXIETY,
    "fikr":            EmotionConcept.ANXIETY,
    "anxious":         EmotionConcept.ANXIETY,
    "anxiety":         EmotionConcept.ANXIETY,
    "nervous":         EmotionConcept.ANXIETY,
    "tension ho rahi": EmotionConcept.ANXIETY,

    # WORRY
    "pareshani":     EmotionConcept.WORRY,
    "pareshan":      EmotionConcept.WORRY,
    "duvidha":       EmotionConcept.WORRY,
    "musibat":       EmotionConcept.WORRY,
    "trouble":       EmotionConcept.WORRY,
    "worried":       EmotionConcept.WORRY,
    "worry":         EmotionConcept.WORRY,
    "pareshan hoon": EmotionConcept.WORRY,

    # EXCITEMENT
    "excited":    EmotionConcept.EXCITEMENT,
    "utsuk":      EmotionConcept.EXCITEMENT,
    "utsaah":     EmotionConcept.EXCITEMENT,
    "josh":       EmotionConcept.EXCITEMENT,
    "thrilled":   EmotionConcept.EXCITEMENT,
    "pumped":     EmotionConcept.EXCITEMENT,
    "eager":      EmotionConcept.EXCITEMENT,
    "excitement": EmotionConcept.EXCITEMENT,

    # BOREDOM
    "bored":        EmotionConcept.BOREDOM,
    "pak gaya":     EmotionConcept.BOREDOM,
    "bore hona":    EmotionConcept.BOREDOM,
    "boring":       EmotionConcept.BOREDOM,
    "dull":         EmotionConcept.BOREDOM,
    "bore ho raha": EmotionConcept.BOREDOM,

    # CALM
    "shant":    EmotionConcept.CALM,
    "shanti":   EmotionConcept.CALM,
    "calm":     EmotionConcept.CALM,
    "peaceful": EmotionConcept.CALM,

    # CONFUSED
    "confused":  EmotionConcept.CONFUSED,
    "confusion": EmotionConcept.CONFUSED,
    "uljhan":    EmotionConcept.CONFUSED,

    # CONFIDENT
    "confident":  EmotionConcept.CONFIDENT,
    "confidence": EmotionConcept.CONFIDENT,
    "bharosa":    EmotionConcept.CONFIDENT,
}

_TIME_MAP: Dict[str, str] = {
    # NOW
    "abhi":         TimeRefConcept.NOW,
    "turant":       TimeRefConcept.NOW,
    "isi waqt":     TimeRefConcept.NOW,
    "foran":        TimeRefConcept.NOW,
    "fauran":       TimeRefConcept.NOW,
    "right now":    TimeRefConcept.NOW,
    "immediately":  TimeRefConcept.NOW,
    "now":          TimeRefConcept.NOW,
    "instantly":    TimeRefConcept.NOW,
    "abhi ke abhi": TimeRefConcept.NOW,

    # LATER
    "baad mein":   TimeRefConcept.LATER,
    "baad":        TimeRefConcept.LATER,
    "baadme":      TimeRefConcept.LATER,
    "later":       TimeRefConcept.LATER,
    "afterwards":  TimeRefConcept.LATER,
    "baad me":     TimeRefConcept.LATER,

    # BEFORE
    "pehle":       TimeRefConcept.BEFORE,
    "pahle":       TimeRefConcept.BEFORE,
    "isse pehle":  TimeRefConcept.BEFORE,
    "earlier":     TimeRefConcept.BEFORE,
    "before":      TimeRefConcept.BEFORE,
    "previously":  TimeRefConcept.BEFORE,

    # YESTERDAY_OR_TOMORROW
    "kal":           TimeRefConcept.YESTERDAY_OR_TOMORROW,
    "bita kal":      TimeRefConcept.YESTERDAY_OR_TOMORROW,
    "aane wala kal": TimeRefConcept.YESTERDAY_OR_TOMORROW,
    "yesterday":     TimeRefConcept.YESTERDAY_OR_TOMORROW,
    "tomorrow":      TimeRefConcept.YESTERDAY_OR_TOMORROW,

    # TODAY
    "aaj":         TimeRefConcept.TODAY,
    "today":       TimeRefConcept.TODAY,
    "aaj ke din":  TimeRefConcept.TODAY,

    # DAY_AFTER
    "parso":                 TimeRefConcept.DAY_AFTER,
    "parson":                TimeRefConcept.DAY_AFTER,
    "day after tomorrow":    TimeRefConcept.DAY_AFTER,
    "day before yesterday":  TimeRefConcept.DAY_AFTER,

    # MORNING
    "subah":   TimeRefConcept.MORNING,
    "savere":  TimeRefConcept.MORNING,
    "bhor":    TimeRefConcept.MORNING,
    "morning": TimeRefConcept.MORNING,
    "dawn":    TimeRefConcept.MORNING,
    "subha":   TimeRefConcept.MORNING,

    # AFTERNOON
    "dopahar":      TimeRefConcept.AFTERNOON,
    "doopahar":     TimeRefConcept.AFTERNOON,
    "teesre pehar": TimeRefConcept.AFTERNOON,
    "afternoon":    TimeRefConcept.AFTERNOON,
    "noon":         TimeRefConcept.AFTERNOON,
    "midday":       TimeRefConcept.AFTERNOON,

    # EVENING
    "shaam":   TimeRefConcept.EVENING,
    "sham":    TimeRefConcept.EVENING,
    "sanjh":   TimeRefConcept.EVENING,
    "sandhya": TimeRefConcept.EVENING,
    "evening": TimeRefConcept.EVENING,
    "dusk":    TimeRefConcept.EVENING,

    # NIGHT
    "raat":       TimeRefConcept.NIGHT,
    "raatri":     TimeRefConcept.NIGHT,
    "night":      TimeRefConcept.NIGHT,
    "midnight":   TimeRefConcept.NIGHT,
    "late night": TimeRefConcept.NIGHT,

    # DAILY
    "roz":     TimeRefConcept.DAILY,
    "har roz": TimeRefConcept.DAILY,
    "daily":   TimeRefConcept.DAILY,
    "har din": TimeRefConcept.DAILY,

    # SOMETIMES
    "kabhi kabhi": TimeRefConcept.SOMETIMES,
    "sometimes":   TimeRefConcept.SOMETIMES,

    # SOON
    "jaldi":    TimeRefConcept.SOON,
    "soon":     TimeRefConcept.SOON,
    "shortly":  TimeRefConcept.SOON,
    "jaldi se": TimeRefConcept.SOON,

    # LATE
    "der se": TimeRefConcept.LATE,
    "late":   TimeRefConcept.LATE,

    # ALWAYS
    "hamesha": TimeRefConcept.ALWAYS,
    "sada":    TimeRefConcept.ALWAYS,
    "always":  TimeRefConcept.ALWAYS,

    # NEVER
    "kabhi nahi": TimeRefConcept.NEVER,
    "never":      TimeRefConcept.NEVER,
}

_ACTION_MAP: Dict[str, str] = {
    # OPEN
    "kholo":         ActionVerbConcept.OPEN,
    "khol do":       ActionVerbConcept.OPEN,
    "khol de":       ActionVerbConcept.OPEN,
    "kholna":        ActionVerbConcept.OPEN,
    "kholiye":       ActionVerbConcept.OPEN,
    "open karo":     ActionVerbConcept.OPEN,
    "open kar do":   ActionVerbConcept.OPEN,
    "start karo":    ActionVerbConcept.OPEN,
    "start kar do":  ActionVerbConcept.OPEN,
    "chalu karo":    ActionVerbConcept.OPEN,
    "launch karo":   ActionVerbConcept.OPEN,

    # CLOSE
    "band karo":     ActionVerbConcept.CLOSE,
    "band kar do":   ActionVerbConcept.CLOSE,
    "band kar":      ActionVerbConcept.CLOSE,
    "band kijiye":   ActionVerbConcept.CLOSE,
    "close karo":    ActionVerbConcept.CLOSE,
    "close kar do":  ActionVerbConcept.CLOSE,
    "exit karo":     ActionVerbConcept.CLOSE,
    "quit karo":     ActionVerbConcept.CLOSE,

    # PLAY
    "chalao":        ActionVerbConcept.PLAY,
    "chala do":      ActionVerbConcept.PLAY,
    "chala de":      ActionVerbConcept.PLAY,
    "bajao":         ActionVerbConcept.PLAY,
    "baja do":       ActionVerbConcept.PLAY,
    "play karo":     ActionVerbConcept.PLAY,
    "play kar do":   ActionVerbConcept.PLAY,
    "run karo":      ActionVerbConcept.PLAY,

    # STOP
    "rok do":        ActionVerbConcept.STOP,
    "rokna":         ActionVerbConcept.STOP,
    "roko":          ActionVerbConcept.STOP,
    "rokiye":        ActionVerbConcept.STOP,
    "pause karo":    ActionVerbConcept.STOP,
    "stop karo":     ActionVerbConcept.STOP,

    # SEND
    "bhejo":         ActionVerbConcept.SEND,
    "bhej do":       ActionVerbConcept.SEND,
    "bhej de":       ActionVerbConcept.SEND,
    "bhej kijiye":   ActionVerbConcept.SEND,
    "send karo":     ActionVerbConcept.SEND,
    "forward karo":  ActionVerbConcept.SEND,

    # BRING
    "lao":           ActionVerbConcept.BRING,
    "le aao":        ActionVerbConcept.BRING,
    "lana":          ActionVerbConcept.BRING,
    "laiye":         ActionVerbConcept.BRING,
    "fetch karo":    ActionVerbConcept.BRING,

    # TAKE
    "le jao":        ActionVerbConcept.TAKE,
    "le jana":       ActionVerbConcept.TAKE,
    "le jaiye":      ActionVerbConcept.TAKE,
    "take away":     ActionVerbConcept.TAKE,

    # PLACE
    "rakho":         ActionVerbConcept.PLACE,
    "rakh do":       ActionVerbConcept.PLACE,
    "rakhna":        ActionVerbConcept.PLACE,
    "rakhiye":       ActionVerbConcept.PLACE,
    "save karo":     ActionVerbConcept.PLACE,
    "store karo":    ActionVerbConcept.PLACE,

    # REMOVE
    "hatao":         ActionVerbConcept.REMOVE,
    "hata do":       ActionVerbConcept.REMOVE,
    "hatana":        ActionVerbConcept.REMOVE,
    "hataiye":       ActionVerbConcept.REMOVE,
    "remove karo":   ActionVerbConcept.REMOVE,
    "delete karo":   ActionVerbConcept.REMOVE,
    "clear karo":    ActionVerbConcept.REMOVE,

    # SHOW
    "dikhao":        ActionVerbConcept.SHOW,
    "dikha do":      ActionVerbConcept.SHOW,
    "dikhana":       ActionVerbConcept.SHOW,
    "dikhaiye":      ActionVerbConcept.SHOW,
    "show karo":     ActionVerbConcept.SHOW,
    "display karo":  ActionVerbConcept.SHOW,
    "view karo":     ActionVerbConcept.SHOW,

    # HIDE
    "chhupao":       ActionVerbConcept.HIDE,
    "chhupa do":     ActionVerbConcept.HIDE,
    "chhupana":      ActionVerbConcept.HIDE,
    "chhupaiye":     ActionVerbConcept.HIDE,
    "hide karo":     ActionVerbConcept.HIDE,
    "minimize karo": ActionVerbConcept.HIDE,

    # WRITE
    "likho":         ActionVerbConcept.WRITE,
    "likh do":       ActionVerbConcept.WRITE,
    "likhna":        ActionVerbConcept.WRITE,
    "likhiye":       ActionVerbConcept.WRITE,
    "type karo":     ActionVerbConcept.WRITE,
    "write karo":    ActionVerbConcept.WRITE,
    "note karo":     ActionVerbConcept.WRITE,

    # READ
    "padho":         ActionVerbConcept.READ,
    "parho":         ActionVerbConcept.READ,
    "padh do":       ActionVerbConcept.READ,
    "padhna":        ActionVerbConcept.READ,
    "padhiye":       ActionVerbConcept.READ,
    "read karo":     ActionVerbConcept.READ,

    # SPEAK
    "bolo":          ActionVerbConcept.SPEAK,
    "bol do":        ActionVerbConcept.SPEAK,
    "bolna":         ActionVerbConcept.SPEAK,
    "boliye":        ActionVerbConcept.SPEAK,
    "speak karo":    ActionVerbConcept.SPEAK,
    "batao":         ActionVerbConcept.SPEAK,
    "batayein":      ActionVerbConcept.SPEAK,

    # LISTEN
    "sunao":         ActionVerbConcept.LISTEN,
    "suna do":       ActionVerbConcept.LISTEN,
    "sunana":        ActionVerbConcept.LISTEN,
    "suno":          ActionVerbConcept.LISTEN,
    "suniye":        ActionVerbConcept.LISTEN,
    "sunna":         ActionVerbConcept.LISTEN,
    "listen karo":   ActionVerbConcept.LISTEN,

    # SEARCH
    "dhoondo":       ActionVerbConcept.SEARCH,
    "dhundo":        ActionVerbConcept.SEARCH,
    "khojo":         ActionVerbConcept.SEARCH,
    "search karo":   ActionVerbConcept.SEARCH,
    "find karo":     ActionVerbConcept.SEARCH,

    # COPY
    "copy karo":     ActionVerbConcept.COPY,
    "copy kar do":   ActionVerbConcept.COPY,

    # PASTE
    "paste karo":    ActionVerbConcept.PASTE,
    "paste kar do":  ActionVerbConcept.PASTE,

    # REFRESH
    "refresh karo":  ActionVerbConcept.REFRESH,
    "reload karo":   ActionVerbConcept.REFRESH,

    # DOWNLOAD
    "download karo": ActionVerbConcept.DOWNLOAD,

    # UPLOAD
    "upload karo":   ActionVerbConcept.UPLOAD,

    # INCREASE
    "badhao":        ActionVerbConcept.INCREASE,
    "badha do":      ActionVerbConcept.INCREASE,
    "increase karo": ActionVerbConcept.INCREASE,

    # DECREASE
    "ghatao":        ActionVerbConcept.DECREASE,
    "ghata do":      ActionVerbConcept.DECREASE,
    "decrease karo": ActionVerbConcept.DECREASE,
}

_QUANTITY_MAP: Dict[str, str] = {
    # SMALL
    "thoda":       QuantityConcept.SMALL,
    "thodi":       QuantityConcept.SMALL,
    "thode":       QuantityConcept.SMALL,
    "zara sa":     QuantityConcept.SMALL,
    "thoda sa":    QuantityConcept.SMALL,
    "a little":    QuantityConcept.SMALL,
    "slightly":    QuantityConcept.SMALL,
    "minimal":     QuantityConcept.SMALL,
    "bit":         QuantityConcept.SMALL,

    # LARGE
    "zyada":       QuantityConcept.LARGE,
    "jyada":       QuantityConcept.LARGE,
    "bahut":       QuantityConcept.LARGE,
    "bahot":       QuantityConcept.LARGE,
    "adhik":       QuantityConcept.LARGE,
    "kaafi":       QuantityConcept.LARGE,
    "more":        QuantityConcept.LARGE,
    "much":        QuantityConcept.LARGE,
    "lot":         QuantityConcept.LARGE,
    "extra":       QuantityConcept.LARGE,

    # LESS
    "kam":         QuantityConcept.LESS,
    "thoda kam":   QuantityConcept.LESS,
    "less":        QuantityConcept.LESS,
    "fewer":       QuantityConcept.LESS,
    "reduced":     QuantityConcept.LESS,

    # ALL
    "sab":         QuantityConcept.ALL,
    "sabhi":       QuantityConcept.ALL,
    "all":         QuantityConcept.ALL,
    "everything":  QuantityConcept.ALL,
    "everyone":    QuantityConcept.ALL,
    "whole":       QuantityConcept.ALL,

    # SOME
    "kuch":        QuantityConcept.SOME,
    "thode bohot": QuantityConcept.SOME,
    "some":        QuantityConcept.SOME,
    "a few":       QuantityConcept.SOME,
    "several":     QuantityConcept.SOME,

    # ANY
    "koi":         QuantityConcept.ANY,
    "kisi":        QuantityConcept.ANY,
    "anyone":      QuantityConcept.ANY,
    "anybody":     QuantityConcept.ANY,
    "anything":    QuantityConcept.ANY,
    "any":         QuantityConcept.ANY,

    # ONE
    "ek":          QuantityConcept.ONE,
    "single":      QuantityConcept.ONE,
    "one":         QuantityConcept.ONE,
    "solo":        QuantityConcept.ONE,

    # TWO
    "do":          QuantityConcept.TWO,
    "double":      QuantityConcept.TWO,
    "two":         QuantityConcept.TWO,
    "both":        QuantityConcept.TWO,
    "dono":        QuantityConcept.TWO,

    # ALL_OF
    "saare":       QuantityConcept.ALL_OF,
    "saara":       QuantityConcept.ALL_OF,
    "saari":       QuantityConcept.ALL_OF,
    "all of them": QuantityConcept.ALL_OF,
    "entire":      QuantityConcept.ALL_OF,

    # HALF
    "aadha":       QuantityConcept.HALF,
    "aadhi":       QuantityConcept.HALF,
    "aadhe":       QuantityConcept.HALF,
    "half":        QuantityConcept.HALF,

    # FULL
    "poora":       QuantityConcept.FULL,
    "poori":       QuantityConcept.FULL,
    "poore":       QuantityConcept.FULL,
    "full":        QuantityConcept.FULL,
    "complete":    QuantityConcept.FULL,

    # ZERO
    "bilkul nahi": QuantityConcept.ZERO,
    "shunya":      QuantityConcept.ZERO,
    "zero":        QuantityConcept.ZERO,
    "none":        QuantityConcept.ZERO,

    # MULTIPLE
    "dugna":       QuantityConcept.MULTIPLE,
    "tiguna":      QuantityConcept.MULTIPLE,
    "teen":        QuantityConcept.MULTIPLE,
    "chaar":       QuantityConcept.MULTIPLE,
    "paanch":      QuantityConcept.MULTIPLE,
}

_REFERENCE_MAP: Dict[str, str] = {
    # FIRST
    "ye wala":    ReferenceConcept.FIRST,
    "yeh wala":   ReferenceConcept.FIRST,
    "pehla":      ReferenceConcept.FIRST,
    "pahla":      ReferenceConcept.FIRST,
    "pehli":      ReferenceConcept.FIRST,
    "pehla wala": ReferenceConcept.FIRST,
    "first":      ReferenceConcept.FIRST,
    "first wala": ReferenceConcept.FIRST,

    # SECOND
    "doosra":      ReferenceConcept.SECOND,
    "dusra":       ReferenceConcept.SECOND,
    "doosri":      ReferenceConcept.SECOND,
    "doosra wala": ReferenceConcept.SECOND,
    "dusra wala":  ReferenceConcept.SECOND,
    "second":      ReferenceConcept.SECOND,
    "second wala": ReferenceConcept.SECOND,
    "wo wala":     ReferenceConcept.SECOND,
    "woh wala":    ReferenceConcept.SECOND,

    # THIRD
    "teesra":     ReferenceConcept.THIRD,
    "tisra":      ReferenceConcept.THIRD,
    "teesri":     ReferenceConcept.THIRD,
    "third":      ReferenceConcept.THIRD,
    "third wala": ReferenceConcept.THIRD,

    # FOURTH
    "chautha":     ReferenceConcept.FOURTH,
    "chauthi":     ReferenceConcept.FOURTH,
    "fourth":      ReferenceConcept.FOURTH,
    "fourth wala": ReferenceConcept.FOURTH,

    # LAST
    "last wala":    ReferenceConcept.LAST,
    "aakhri":       ReferenceConcept.LAST,
    "aakhri wala":  ReferenceConcept.LAST,
    "aakhiri":      ReferenceConcept.LAST,
    "aakhiri wala": ReferenceConcept.LAST,
    "antim":        ReferenceConcept.LAST,
    "last":         ReferenceConcept.LAST,
    "final":        ReferenceConcept.LAST,

    # TOP
    "upar wala": ReferenceConcept.TOP,
    "top wala":  ReferenceConcept.TOP,
    "uppermost": ReferenceConcept.TOP,
    "topmost":   ReferenceConcept.TOP,

    # BOTTOM
    "niche wala":  ReferenceConcept.BOTTOM,
    "neeche wala": ReferenceConcept.BOTTOM,
    "bottom wala": ReferenceConcept.BOTTOM,
    "lowest":      ReferenceConcept.BOTTOM,

    # PREVIOUS
    "pichla":      ReferenceConcept.PREVIOUS,
    "pichli":      ReferenceConcept.PREVIOUS,
    "pichla wala": ReferenceConcept.PREVIOUS,
    "previous":    ReferenceConcept.PREVIOUS,

    # NEXT
    "agla":      ReferenceConcept.NEXT,
    "agli":      ReferenceConcept.NEXT,
    "agla wala": ReferenceConcept.NEXT,
    "next":      ReferenceConcept.NEXT,

    # MIDDLE
    "beech wala":  ReferenceConcept.MIDDLE,
    "center wala": ReferenceConcept.MIDDLE,

    # SAME
    "wahi":      ReferenceConcept.SAME,
    "wahi wala": ReferenceConcept.SAME,
    "same wala": ReferenceConcept.SAME,

    # NEW_REF
    "naya wala": ReferenceConcept.NEW_REF,
    "new wala":  ReferenceConcept.NEW_REF,

    # OLD_REF
    "purana wala": ReferenceConcept.OLD_REF,
    "old wala":    ReferenceConcept.OLD_REF,
}

# ---------------------------------------------------------------------------
# Master flat lookup (word → (category, concept))
# Built once at import time — O(1) per query thereafter
# ---------------------------------------------------------------------------

_MASTER_VOCAB: Dict[str, Tuple[HindiVocabCategory, str]] = {}

def _register(category: HindiVocabCategory, vocab: Dict[str, str]) -> None:
    for word, concept in vocab.items():
        _MASTER_VOCAB[word.lower()] = (category, concept)


_register(HindiVocabCategory.MOVEMENT,         _MOVEMENT_MAP)
_register(HindiVocabCategory.DIRECTION,         _DIRECTION_MAP)
_register(HindiVocabCategory.OBJECT_REFERENCE,  _OBJECT_REF_MAP)
_register(HindiVocabCategory.BODY_STATE,        _BODY_STATE_MAP)
_register(HindiVocabCategory.EMOTION,           _EMOTION_MAP)
_register(HindiVocabCategory.TIME,              _TIME_MAP)
_register(HindiVocabCategory.ACTION,            _ACTION_MAP)
_register(HindiVocabCategory.QUANTITY,          _QUANTITY_MAP)
_register(HindiVocabCategory.REFERENCE,         _REFERENCE_MAP)

# Multi-word keys sorted longest-first so greedy matching works correctly
_MULTI_WORD_KEYS: List[str] = sorted(
    [k for k in _MASTER_VOCAB if " " in k], key=len, reverse=True
)
_SINGLE_WORD_KEYS: Set[str] = {k for k in _MASTER_VOCAB if " " not in k}

# ---------------------------------------------------------------------------
# Empathetic response templates for body/emotion states
# ---------------------------------------------------------------------------

_BODY_EMPATHY: Dict[str, str] = {
    BodyStateConcept.HUNGER:      "Lagta hai aap bhookhe hain, Boss. Kya main kuch order karne mein help karun?",
    BodyStateConcept.THIRST:      "Paani pine ka time aa gaya, Boss. Kya main reminder set karun?",
    BodyStateConcept.SLEEP_STATE: "Neend aa rahi hai, Boss. Kya main Do Not Disturb mode on karun?",
    BodyStateConcept.FATIGUE:     "Thak gaye hain aap, Boss. Kya main ek break reminder set karun?",
    BodyStateConcept.PAIN:        "Dard ho raha hai, Boss. Kya koi help chahiye?",
    BodyStateConcept.HOT:         "Garmi lag rahi hai, Boss. Kya main fan ya AC ke liye remind karun?",
    BodyStateConcept.COLD:        "Sardi lag rahi hai, Boss. Dhyan rakhein.",
    BodyStateConcept.REST:        "Bilkul aaram karein, Boss. Kya mujhe system mute karna chahiye?",
    BodyStateConcept.SICK:        "Tabiyat theek nahi lag rahi, Boss. Thoda rest lijiye aur dhyan rakhein.",
    BodyStateConcept.DIZZY:       "Chakkar aa rahe hain, Boss? Kripya baith jayein aur paani pijiye.",
    BodyStateConcept.HEALTH:      "Bahut badiya, Boss! Full energy ke saath kaam karte hain.",
}

_EMOTION_EMPATHY: Dict[str, str] = {
    EmotionConcept.JOY:        "Khushi mein hun aapke saath, Boss! Kya koi khaas kaam hai?",
    EmotionConcept.SADNESS:    "Sab theek ho jayega, Boss. Koi help chahiye ho toh batayein.",
    EmotionConcept.ANGER:      "Lagta hai aap upset hain, Boss. Kya main kuch kar sakta hoon?",
    EmotionConcept.LOVE:       "Pyaar toh sabse khubsoorat cheez hai, Boss!",
    EmotionConcept.HATRED:     "Samajh sakta hoon Boss, koi baat nahi. Kya main help kar sakta hoon?",
    EmotionConcept.FEAR:       "Dar lagne par baat karein Boss, main hoon yahan.",
    EmotionConcept.ANXIETY:    "Tension mat lein, Boss. Ek kaam ek baar mein. Kya help chahiye?",
    EmotionConcept.WORRY:      "Pareshan hain Boss? Koi baat nahi, batayein main kya kar sakta hoon.",
    EmotionConcept.EXCITEMENT: "Bahut accha! Boss excited hain — batayein kya plan hai!",
    EmotionConcept.BOREDOM:    "Bore ho gaye, Boss? Koi game chalayein, ya koi kaam?",
    EmotionConcept.CALM:       "Bahut badhiya, Boss. Sukoon aur shanti se kaam karein.",
    EmotionConcept.CONFUSED:   "Confusion ho rahi hai, Boss? Batayein main kya clarify karun.",
    EmotionConcept.CONFIDENT:  "Full confidence! Let's get this done, Boss!",
}


# ---------------------------------------------------------------------------
# Dataclasses for structured results
# ---------------------------------------------------------------------------

@dataclass
class VocabMatch:
    word: str
    category: HindiVocabCategory
    concept: str


@dataclass
class EnrichedEntities:
    """All vocab matches found in a single utterance."""
    matches: List[VocabMatch]

    # Convenience accessors
    @property
    def time_ref(self) -> Optional[str]:
        for m in self.matches:
            if m.category == HindiVocabCategory.TIME:
                return m.concept
        return None

    @property
    def direction(self) -> Optional[str]:
        for m in self.matches:
            if m.category == HindiVocabCategory.DIRECTION:
                return m.concept
        return None

    @property
    def quantity(self) -> Optional[str]:
        for m in self.matches:
            if m.category == HindiVocabCategory.QUANTITY:
                return m.concept
        return None

    @property
    def object_ref(self) -> Optional[str]:
        for m in self.matches:
            if m.category == HindiVocabCategory.OBJECT_REFERENCE:
                return m.concept
        return None

    @property
    def reference(self) -> Optional[str]:
        for m in self.matches:
            if m.category == HindiVocabCategory.REFERENCE:
                return m.concept
        return None

    @property
    def action(self) -> Optional[str]:
        for m in self.matches:
            if m.category == HindiVocabCategory.ACTION:
                return m.concept
        return None

    @property
    def emotion(self) -> Optional[str]:
        for m in self.matches:
            if m.category == HindiVocabCategory.EMOTION:
                return m.concept
        return None

    @property
    def body_state(self) -> Optional[str]:
        for m in self.matches:
            if m.category == HindiVocabCategory.BODY_STATE:
                return m.concept
        return None

    def has_category(self, category: HindiVocabCategory) -> bool:
        return any(m.category == category for m in self.matches)


# ---------------------------------------------------------------------------
# Main Engine
# ---------------------------------------------------------------------------

class HindiVocabEngine:
    """
    O(1) lookup engine for Hindi/Hinglish semantic vocabulary.

    Thread-safe — all state is module-level constants.
    Never executes commands. Pure classification layer.
    """

    # Expose vocab sets for use by other modules (e.g. speech_understanding)
    KNOWN_BODY_STATE_WORDS: Set[str] = set(_BODY_STATE_MAP.keys())
    KNOWN_EMOTION_WORDS: Set[str] = set(_EMOTION_MAP.keys())
    KNOWN_TIME_WORDS: Set[str] = set(_TIME_MAP.keys())
    KNOWN_ACTION_WORDS: Set[str] = {k for k in _ACTION_MAP if " " not in k}
    KNOWN_QUANTITY_WORDS: Set[str] = set(_QUANTITY_MAP.keys())
    KNOWN_DIRECTION_WORDS: Set[str] = set(_DIRECTION_MAP.keys())

    # Words that should NOT be stripped as fillers even when normalizer sees them
    # because they carry semantic content (quantity modifiers, time refs)
    PRESERVE_WORDS: Set[str] = (
        KNOWN_QUANTITY_WORDS
        | KNOWN_TIME_WORDS
        | KNOWN_DIRECTION_WORDS
        | KNOWN_BODY_STATE_WORDS
        | KNOWN_EMOTION_WORDS
    )

    @classmethod
    def classify(cls, word: str) -> Optional[Tuple[HindiVocabCategory, str]]:
        """
        Single-word or multi-word phrase lookup.
        Returns (category, concept) or None if not in vocabulary.

        Examples:
            classify("gussa")  → (HindiVocabCategory.EMOTION, "ANGER")
            classify("ye wala") → (HindiVocabCategory.REFERENCE, "FIRST")
            classify("hello")  → None
        """
        key = word.strip().lower()
        return _MASTER_VOCAB.get(key)

    @classmethod
    def enrich_speech_entities(cls, text: str) -> EnrichedEntities:
        """
        Scans entire utterance for vocab matches (greedy multi-word first).
        Returns EnrichedEntities with all matches found.

        Does NOT modify the text — purely additive metadata.
        """
        lowered = text.lower()
        matches: List[VocabMatch] = []
        consumed_spans: List[Tuple[int, int]] = []

        # Pass 1: multi-word phrases (longest first)
        for phrase in _MULTI_WORD_KEYS:
            start = 0
            while True:
                idx = lowered.find(phrase, start)
                if idx == -1:
                    break
                end = idx + len(phrase)
                # Ensure word boundaries
                pre_ok = (idx == 0 or not lowered[idx - 1].isalpha())
                post_ok = (end == len(lowered) or not lowered[end].isalpha())
                if pre_ok and post_ok:
                    # Not already consumed by a longer match
                    if not any(s <= idx < e or s < end <= e for s, e in consumed_spans):
                        cat, concept = _MASTER_VOCAB[phrase]
                        matches.append(VocabMatch(word=phrase, category=cat, concept=concept))
                        consumed_spans.append((idx, end))
                start = end

        # Pass 2: single words
        word_re = re.compile(r'\b\w+\b')
        for m in word_re.finditer(lowered):
            word = m.group()
            if word in _SINGLE_WORD_KEYS:
                span = (m.start(), m.end())
                if not any(s <= span[0] < e or s < span[1] <= e for s, e in consumed_spans):
                    cat, concept = _MASTER_VOCAB[word]
                    matches.append(VocabMatch(word=word, category=cat, concept=concept))
                    consumed_spans.append(span)

        return EnrichedEntities(matches=matches)

    @classmethod
    def resolve_object_reference(
        cls,
        text: str,
        last_app: Optional[str] = None,
        last_website: Optional[str] = None,
        last_file: Optional[str] = None,
    ) -> Optional[str]:
        """
        Resolves proximal/distal object references (ye/wo) to concrete targets
        using the provided active context.

        Returns the resolved target name or None if no reference found.

        Examples:
            resolve_object_reference("ye wala kholo", last_app="notepad")
            → "notepad"
        """
        entities = cls.enrich_speech_entities(text)
        ref = entities.object_ref or entities.reference

        if not ref:
            return None

        if ref == ObjectRefConcept.THIS:
            return last_app or last_website or last_file
        if ref == ObjectRefConcept.THAT:
            return last_website or last_app or last_file
        if ref == ReferenceConcept.FIRST:
            return last_app or last_website
        if ref == ReferenceConcept.PREVIOUS:
            return last_app or last_website
        if ref == ReferenceConcept.NEXT:
            return None  # Next item resolution requires list context — defer to caller

        return None

    @classmethod
    def disambiguate_kal(cls, current_hour: int) -> str:
        """
        Disambiguate 'kal' (yesterday vs. tomorrow) based on time of day.

        Convention:
          - If current_hour >= 17 (5 PM+) or >= 20 (night): kal = TOMORROW
          - Otherwise (morning/afternoon): kal = YESTERDAY
        """
        if current_hour >= 17:
            return "TOMORROW"
        return "YESTERDAY"

    @classmethod
    def get_empathetic_response(
        cls,
        text: str,
    ) -> Optional[str]:
        """
        If the utterance expresses a body state or emotion, returns a
        short empathetic conversational response.
        Returns None if no body/emotion word found.

        This response is CONVERSATIONAL ONLY — no commands are executed.
        """
        entities = cls.enrich_speech_entities(text)

        if entities.body_state:
            return _BODY_EMPATHY.get(entities.body_state)
        if entities.emotion:
            return _EMOTION_EMPATHY.get(entities.emotion)

        return None

    @classmethod
    def get_quantity_modifier(cls, text: str) -> Optional[Tuple[str, float]]:
        """
        Returns (concept, multiplier) for quantity words found in text.

        Multiplier is a hint for numeric commands:
          thoda → SMALL, 0.25   (e.g. "thoda volume badhao" → increase by 5%)
          zyada → LARGE, 0.75   (e.g. "zyada brightness" → increase by 25%)
          kam   → LESS,  0.25
          aadha → HALF,  0.50

        Returns None if no quantity word found.
        """
        _MULTIPLIERS: Dict[str, float] = {
            QuantityConcept.SMALL:    0.25,
            QuantityConcept.LARGE:    0.75,
            QuantityConcept.LESS:     0.25,
            QuantityConcept.ALL:      1.00,
            QuantityConcept.ALL_OF:   1.00,
            QuantityConcept.HALF:     0.50,
            QuantityConcept.FULL:     1.00,
            QuantityConcept.ZERO:     0.00,
            QuantityConcept.ONE:      0.10,
            QuantityConcept.TWO:      0.20,
            QuantityConcept.MULTIPLE: 2.00,
        }
        entities = cls.enrich_speech_entities(text)
        q = entities.quantity
        if q:
            return (q, _MULTIPLIERS.get(q, 0.50))
        return None

    @classmethod
    def get_direction_for_scroll(cls, text: str) -> Optional[str]:
        """
        Maps direction words to scroll/move directions understood by window manager.
        Returns "UP", "DOWN", "LEFT", "RIGHT" or None.
        """
        _SCROLL_MAP: Dict[str, str] = {
            DirectionConcept.UP:       "UP",
            DirectionConcept.DOWN:     "DOWN",
            DirectionConcept.LEFT:     "LEFT",
            DirectionConcept.RIGHT:    "RIGHT",
            DirectionConcept.FORWARD:  "DOWN",  # "aage" = forward in reading = scroll down
            DirectionConcept.BACK:     "UP",    # "peeche" = scroll back up
            DirectionConcept.STRAIGHT: "DOWN",
            DirectionConcept.CENTER:   "CENTER",
        }
        entities = cls.enrich_speech_entities(text)
        d = entities.direction
        if d:
            return _SCROLL_MAP.get(d)
        return None
