# tests/test_natural_language_vocab_kb.py
"""
Comprehensive tests for the Large Natural Language Semantic Knowledge Base in Jarvis.

Validates:
1. User-specified 9-category ontology:
   - MOVEMENT, DIRECTION, OBJECT_REFERENCE, BODY_STATE, EMOTION,
     TIME, ACTION, QUANTITY, REFERENCE
2. Exact classification of all user example words.
3. Expanded morphological forms, inflections, and Hinglish/English terms.
4. Greedy multi-word phrase matching and entity enrichment on natural utterances.
5. Empathetic conversational responses for bodily conditions and emotional states.
6. Quantity modifier multipliers (small, large, half, full, zero, multiple).
7. Scroll direction resolution.
8. Sub-millisecond lookup latency benchmark (< 0.05 ms).
"""

import time
import pytest
from core.semantic.hindi_vocab import (
    HindiVocabEngine,
    HindiVocabCategory,
    MovementConcept,
    DirectionConcept,
    ObjectRefConcept,
    BodyStateConcept,
    EmotionConcept,
    TimeRefConcept,
    ActionVerbConcept,
    QuantityConcept,
    ReferenceConcept,
)


# ---------------------------------------------------------------------------
# 1. User Example Verification (All 9 Categories)
# ---------------------------------------------------------------------------

class TestUserExampleExactWords:
    """Verifies that every single word in the user's example prompt resolves correctly."""

    @pytest.mark.parametrize("word,expected_cat,expected_concept", [
        # MOVEMENT
        ("aana", HindiVocabCategory.MOVEMENT, MovementConcept.ARRIVE),
        ("jaana", HindiVocabCategory.MOVEMENT, MovementConcept.DEPART),
        ("chalna", HindiVocabCategory.MOVEMENT, MovementConcept.WALK),
        ("rukna", HindiVocabCategory.MOVEMENT, MovementConcept.STOP),
        ("baithna", HindiVocabCategory.MOVEMENT, MovementConcept.SIT),
        ("uthna", HindiVocabCategory.MOVEMENT, MovementConcept.RISE),
        ("daudna", HindiVocabCategory.MOVEMENT, MovementConcept.RUN),
        ("lautna", HindiVocabCategory.MOVEMENT, MovementConcept.RETURN),

        # DIRECTION
        ("upar", HindiVocabCategory.DIRECTION, DirectionConcept.UP),
        ("niche", HindiVocabCategory.DIRECTION, DirectionConcept.DOWN),
        ("aage", HindiVocabCategory.DIRECTION, DirectionConcept.FORWARD),
        ("peeche", HindiVocabCategory.DIRECTION, DirectionConcept.BACK),
        ("idhar", HindiVocabCategory.DIRECTION, DirectionConcept.HERE_DIR),
        ("udhar", HindiVocabCategory.DIRECTION, DirectionConcept.THERE_DIR),
        ("yahan", HindiVocabCategory.DIRECTION, DirectionConcept.HERE),
        ("wahan", HindiVocabCategory.DIRECTION, DirectionConcept.THERE),
        ("andar", HindiVocabCategory.DIRECTION, DirectionConcept.INSIDE),
        ("bahar", HindiVocabCategory.DIRECTION, DirectionConcept.OUTSIDE),
        ("left", HindiVocabCategory.DIRECTION, DirectionConcept.LEFT),
        ("right", HindiVocabCategory.DIRECTION, DirectionConcept.RIGHT),
        ("pass", HindiVocabCategory.DIRECTION, DirectionConcept.NEAR),
        ("door", HindiVocabCategory.DIRECTION, DirectionConcept.FAR),

        # OBJECT REFERENCE
        ("ye", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THIS),
        ("wo", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THAT),
        ("iska", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THIS),
        ("uska", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THAT),
        ("iski", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THIS),
        ("uski", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THAT),
        ("isse", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THIS),
        ("usse", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THAT),
        ("isko", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THIS),
        ("usko", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THAT),
        ("inhe", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THIS),
        ("unhe", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THAT),
        ("isme", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THIS),
        ("usme", HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THAT),

        # BODY / STATE
        ("bhookh", HindiVocabCategory.BODY_STATE, BodyStateConcept.HUNGER),
        ("pyaas", HindiVocabCategory.BODY_STATE, BodyStateConcept.THIRST),
        ("neend", HindiVocabCategory.BODY_STATE, BodyStateConcept.SLEEP_STATE),
        ("thakan", HindiVocabCategory.BODY_STATE, BodyStateConcept.FATIGUE),
        ("dard", HindiVocabCategory.BODY_STATE, BodyStateConcept.PAIN),
        ("garmi", HindiVocabCategory.BODY_STATE, BodyStateConcept.HOT),
        ("sardi", HindiVocabCategory.BODY_STATE, BodyStateConcept.COLD),
        ("aaram", HindiVocabCategory.BODY_STATE, BodyStateConcept.REST),

        # EMOTION
        ("khushi", HindiVocabCategory.EMOTION, EmotionConcept.JOY),
        ("dukh", HindiVocabCategory.EMOTION, EmotionConcept.SADNESS),
        ("gussa", HindiVocabCategory.EMOTION, EmotionConcept.ANGER),
        ("pyaar", HindiVocabCategory.EMOTION, EmotionConcept.LOVE),
        ("nafrat", HindiVocabCategory.EMOTION, EmotionConcept.HATRED),
        ("dar", HindiVocabCategory.EMOTION, EmotionConcept.FEAR),
        ("tension", HindiVocabCategory.EMOTION, EmotionConcept.ANXIETY),
        ("pareshani", HindiVocabCategory.EMOTION, EmotionConcept.WORRY),
        ("excited", HindiVocabCategory.EMOTION, EmotionConcept.EXCITEMENT),
        ("bored", HindiVocabCategory.EMOTION, EmotionConcept.BOREDOM),

        # TIME
        ("abhi", HindiVocabCategory.TIME, TimeRefConcept.NOW),
        ("baad mein", HindiVocabCategory.TIME, TimeRefConcept.LATER),
        ("pehle", HindiVocabCategory.TIME, TimeRefConcept.BEFORE),
        ("kal", HindiVocabCategory.TIME, TimeRefConcept.YESTERDAY_OR_TOMORROW),
        ("aaj", HindiVocabCategory.TIME, TimeRefConcept.TODAY),
        ("parso", HindiVocabCategory.TIME, TimeRefConcept.DAY_AFTER),
        ("subah", HindiVocabCategory.TIME, TimeRefConcept.MORNING),
        ("dopahar", HindiVocabCategory.TIME, TimeRefConcept.AFTERNOON),
        ("shaam", HindiVocabCategory.TIME, TimeRefConcept.EVENING),
        ("raat", HindiVocabCategory.TIME, TimeRefConcept.NIGHT),

        # ACTION
        ("kholo", HindiVocabCategory.ACTION, ActionVerbConcept.OPEN),
        ("band karo", HindiVocabCategory.ACTION, ActionVerbConcept.CLOSE),
        ("chalao", HindiVocabCategory.ACTION, ActionVerbConcept.PLAY),
        ("rok do", HindiVocabCategory.ACTION, ActionVerbConcept.STOP),
        ("bhejo", HindiVocabCategory.ACTION, ActionVerbConcept.SEND),
        ("lao", HindiVocabCategory.ACTION, ActionVerbConcept.BRING),
        ("le jao", HindiVocabCategory.ACTION, ActionVerbConcept.TAKE),
        ("rakho", HindiVocabCategory.ACTION, ActionVerbConcept.PLACE),
        ("hatao", HindiVocabCategory.ACTION, ActionVerbConcept.REMOVE),
        ("dikhao", HindiVocabCategory.ACTION, ActionVerbConcept.SHOW),
        ("chhupao", HindiVocabCategory.ACTION, ActionVerbConcept.HIDE),
        ("likho", HindiVocabCategory.ACTION, ActionVerbConcept.WRITE),
        ("padho", HindiVocabCategory.ACTION, ActionVerbConcept.READ),
        ("bolo", HindiVocabCategory.ACTION, ActionVerbConcept.SPEAK),
        ("sunao", HindiVocabCategory.ACTION, ActionVerbConcept.LISTEN),

        # QUANTITY
        ("thoda", HindiVocabCategory.QUANTITY, QuantityConcept.SMALL),
        ("zyada", HindiVocabCategory.QUANTITY, QuantityConcept.LARGE),
        ("kam", HindiVocabCategory.QUANTITY, QuantityConcept.LESS),
        ("sab", HindiVocabCategory.QUANTITY, QuantityConcept.ALL),
        ("kuch", HindiVocabCategory.QUANTITY, QuantityConcept.SOME),
        ("koi", HindiVocabCategory.QUANTITY, QuantityConcept.ANY),
        ("ek", HindiVocabCategory.QUANTITY, QuantityConcept.ONE),
        ("do", HindiVocabCategory.QUANTITY, QuantityConcept.TWO),
        ("saare", HindiVocabCategory.QUANTITY, QuantityConcept.ALL_OF),
        ("aadha", HindiVocabCategory.QUANTITY, QuantityConcept.HALF),

        # REFERENCE
        ("ye wala", HindiVocabCategory.REFERENCE, ReferenceConcept.FIRST),
        ("wo wala", HindiVocabCategory.REFERENCE, ReferenceConcept.SECOND),
        ("pehla", HindiVocabCategory.REFERENCE, ReferenceConcept.FIRST),
        ("doosra", HindiVocabCategory.REFERENCE, ReferenceConcept.SECOND),
        ("last wala", HindiVocabCategory.REFERENCE, ReferenceConcept.LAST),
        ("upar wala", HindiVocabCategory.REFERENCE, ReferenceConcept.TOP),
        ("niche wala", HindiVocabCategory.REFERENCE, ReferenceConcept.BOTTOM),
        ("pichla", HindiVocabCategory.REFERENCE, ReferenceConcept.PREVIOUS),
        ("agla", HindiVocabCategory.REFERENCE, ReferenceConcept.NEXT),
    ])
    def test_exact_example_word(self, word, expected_cat, expected_concept):
        result = HindiVocabEngine.classify(word)
        assert result is not None, f"Word '{word}' must be classified"
        cat, concept = result
        assert cat == expected_cat, f"Category mismatch for '{word}'"
        assert concept == expected_concept, f"Concept mismatch for '{word}'"


# ---------------------------------------------------------------------------
# 2. Expanded Vocabulary & Inflections
# ---------------------------------------------------------------------------

class TestExpandedVocabularyCategories:
    """Verifies expanded inflections, conjugations, and new concepts across categories."""

    def test_movement_expanded(self):
        # Additional movement concepts: TURN, JUMP, FALL, CLIMB, DESCEND
        assert HindiVocabEngine.classify("mudna") == (HindiVocabCategory.MOVEMENT, MovementConcept.TURN)
        assert HindiVocabEngine.classify("ghoomna") == (HindiVocabCategory.MOVEMENT, MovementConcept.TURN)
        assert HindiVocabEngine.classify("kudna") == (HindiVocabCategory.MOVEMENT, MovementConcept.JUMP)
        assert HindiVocabEngine.classify("chhalang") == (HindiVocabCategory.MOVEMENT, MovementConcept.JUMP)
        assert HindiVocabEngine.classify("girna") == (HindiVocabCategory.MOVEMENT, MovementConcept.FALL)
        assert HindiVocabEngine.classify("chadhna") == (HindiVocabCategory.MOVEMENT, MovementConcept.CLIMB)
        assert HindiVocabEngine.classify("utarna") == (HindiVocabCategory.MOVEMENT, MovementConcept.DESCEND)
        # Conjugations
        assert HindiVocabEngine.classify("aa raha") == (HindiVocabCategory.MOVEMENT, MovementConcept.ARRIVE)
        assert HindiVocabEngine.classify("chale gaye") == (HindiVocabCategory.MOVEMENT, MovementConcept.DEPART)
        assert HindiVocabEngine.classify("wapas aana") == (HindiVocabCategory.MOVEMENT, MovementConcept.RETURN)

    def test_direction_expanded(self):
        # STRAIGHT, CENTER, DIAGONAL, AROUND
        assert HindiVocabEngine.classify("seedha") == (HindiVocabCategory.DIRECTION, DirectionConcept.STRAIGHT)
        assert HindiVocabEngine.classify("beech mein") == (HindiVocabCategory.DIRECTION, DirectionConcept.CENTER)
        assert HindiVocabEngine.classify("tirchha") == (HindiVocabCategory.DIRECTION, DirectionConcept.DIAGONAL)
        assert HindiVocabEngine.classify("charon taraf") == (HindiVocabCategory.DIRECTION, DirectionConcept.AROUND)
        assert HindiVocabEngine.classify("kareeb") == (HindiVocabCategory.DIRECTION, DirectionConcept.NEAR)
        assert HindiVocabEngine.classify("faasle par") == (HindiVocabCategory.DIRECTION, DirectionConcept.FAR)

    def test_object_ref_expanded(self):
        # Gender and case inflections + RELATIVE
        assert HindiVocabEngine.classify("iske") == (HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THIS)
        res = HindiVocabEngine.classify("jiska")
        assert res == (HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.RELATIVE)
        assert HindiVocabEngine.classify("jiski") == (HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.RELATIVE)
        assert HindiVocabEngine.classify("inme") == (HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THIS)
        assert HindiVocabEngine.classify("unme") == (HindiVocabCategory.OBJECT_REFERENCE, ObjectRefConcept.THAT)

    def test_body_state_expanded(self):
        # SICK, DIZZY, HEALTH
        assert HindiVocabEngine.classify("tabiyat kharab") == (HindiVocabCategory.BODY_STATE, BodyStateConcept.SICK)
        assert HindiVocabEngine.classify("bimar") == (HindiVocabCategory.BODY_STATE, BodyStateConcept.SICK)
        assert HindiVocabEngine.classify("chakkar") == (HindiVocabCategory.BODY_STATE, BodyStateConcept.DIZZY)
        assert HindiVocabEngine.classify("swasth") == (HindiVocabCategory.BODY_STATE, BodyStateConcept.HEALTH)
        assert HindiVocabEngine.classify("tandoorust") == (HindiVocabCategory.BODY_STATE, BodyStateConcept.HEALTH)
        assert HindiVocabEngine.classify("thak gaya") == (HindiVocabCategory.BODY_STATE, BodyStateConcept.FATIGUE)
        assert HindiVocabEngine.classify("sir dard") == (HindiVocabCategory.BODY_STATE, BodyStateConcept.PAIN)

    def test_emotion_expanded(self):
        # CALM, CONFUSED, CONFIDENT
        assert HindiVocabEngine.classify("shant") == (HindiVocabCategory.EMOTION, EmotionConcept.CALM)
        assert HindiVocabEngine.classify("confused") == (HindiVocabCategory.EMOTION, EmotionConcept.CONFUSED)
        assert HindiVocabEngine.classify("uljhan") == (HindiVocabCategory.EMOTION, EmotionConcept.CONFUSED)
        assert HindiVocabEngine.classify("confident") == (HindiVocabCategory.EMOTION, EmotionConcept.CONFIDENT)
        assert HindiVocabEngine.classify("masti") == (HindiVocabCategory.EMOTION, EmotionConcept.JOY)
        assert HindiVocabEngine.classify("dil toot gaya") == (HindiVocabCategory.EMOTION, EmotionConcept.SADNESS)

    def test_time_expanded(self):
        # DAILY, SOMETIMES, SOON, LATE, ALWAYS, NEVER
        assert HindiVocabEngine.classify("roz") == (HindiVocabCategory.TIME, TimeRefConcept.DAILY)
        assert HindiVocabEngine.classify("har roz") == (HindiVocabCategory.TIME, TimeRefConcept.DAILY)
        assert HindiVocabEngine.classify("kabhi kabhi") == (HindiVocabCategory.TIME, TimeRefConcept.SOMETIMES)
        assert HindiVocabEngine.classify("jaldi") == (HindiVocabCategory.TIME, TimeRefConcept.SOON)
        assert HindiVocabEngine.classify("der se") == (HindiVocabCategory.TIME, TimeRefConcept.LATE)
        assert HindiVocabEngine.classify("hamesha") == (HindiVocabCategory.TIME, TimeRefConcept.ALWAYS)
        assert HindiVocabEngine.classify("kabhi nahi") == (HindiVocabCategory.TIME, TimeRefConcept.NEVER)

    def test_action_expanded(self):
        # SEARCH, COPY, PASTE, REFRESH, DOWNLOAD, UPLOAD, INCREASE, DECREASE
        assert HindiVocabEngine.classify("dhoondo") == (HindiVocabCategory.ACTION, ActionVerbConcept.SEARCH)
        assert HindiVocabEngine.classify("copy karo") == (HindiVocabCategory.ACTION, ActionVerbConcept.COPY)
        assert HindiVocabEngine.classify("paste karo") == (HindiVocabCategory.ACTION, ActionVerbConcept.PASTE)
        assert HindiVocabEngine.classify("refresh karo") == (HindiVocabCategory.ACTION, ActionVerbConcept.REFRESH)
        assert HindiVocabEngine.classify("download karo") == (HindiVocabCategory.ACTION, ActionVerbConcept.DOWNLOAD)
        assert HindiVocabEngine.classify("upload karo") == (HindiVocabCategory.ACTION, ActionVerbConcept.UPLOAD)
        assert HindiVocabEngine.classify("badhao") == (HindiVocabCategory.ACTION, ActionVerbConcept.INCREASE)
        assert HindiVocabEngine.classify("ghatao") == (HindiVocabCategory.ACTION, ActionVerbConcept.DECREASE)

    def test_quantity_expanded(self):
        # FULL, ZERO, MULTIPLE
        assert HindiVocabEngine.classify("poora") == (HindiVocabCategory.QUANTITY, QuantityConcept.FULL)
        assert HindiVocabEngine.classify("bilkul nahi") == (HindiVocabCategory.QUANTITY, QuantityConcept.ZERO)
        assert HindiVocabEngine.classify("shunya") == (HindiVocabCategory.QUANTITY, QuantityConcept.ZERO)
        assert HindiVocabEngine.classify("dugna") == (HindiVocabCategory.QUANTITY, QuantityConcept.MULTIPLE)
        assert HindiVocabEngine.classify("teen") == (HindiVocabCategory.QUANTITY, QuantityConcept.MULTIPLE)

    def test_reference_expanded(self):
        # THIRD, FOURTH, MIDDLE, SAME, NEW_REF, OLD_REF
        assert HindiVocabEngine.classify("teesra") == (HindiVocabCategory.REFERENCE, ReferenceConcept.THIRD)
        assert HindiVocabEngine.classify("chautha") == (HindiVocabCategory.REFERENCE, ReferenceConcept.FOURTH)
        assert HindiVocabEngine.classify("beech wala") == (HindiVocabCategory.REFERENCE, ReferenceConcept.MIDDLE)
        assert HindiVocabEngine.classify("wahi wala") == (HindiVocabCategory.REFERENCE, ReferenceConcept.SAME)
        assert HindiVocabEngine.classify("naya wala") == (HindiVocabCategory.REFERENCE, ReferenceConcept.NEW_REF)
        assert HindiVocabEngine.classify("purana wala") == (HindiVocabCategory.REFERENCE, ReferenceConcept.OLD_REF)


# ---------------------------------------------------------------------------
# 3. Speech Entity Enrichment on Utterances
# ---------------------------------------------------------------------------

class TestEnrichmentOnComplexUtterances:
    """Verifies that multi-category utterances are cleanly tagged with metadata."""

    def test_multi_category_command(self):
        # "abhi upar scroll karke poora dikhao" -> abhi(TIME), upar(DIRECTION), poora(QUANTITY), dikhao(ACTION)
        entities = HindiVocabEngine.enrich_speech_entities("abhi upar scroll karke poora dikhao")
        assert entities.time_ref == TimeRefConcept.NOW
        assert entities.direction == DirectionConcept.UP
        assert entities.quantity == QuantityConcept.FULL
        assert entities.action == ActionVerbConcept.SHOW

    def test_emotion_and_body_utterance(self):
        # "aaj bahut thak gaya hoon aur gussa aa raha hai"
        entities = HindiVocabEngine.enrich_speech_entities("aaj bahut thak gaya hoon aur gussa aa raha hai")
        assert entities.time_ref == TimeRefConcept.TODAY
        assert entities.body_state == BodyStateConcept.FATIGUE
        assert entities.emotion == EmotionConcept.ANGER


# ---------------------------------------------------------------------------
# 4. Empathetic Responses for New States
# ---------------------------------------------------------------------------

class TestExpandedEmpatheticResponses:
    """Verifies conversational empathy responses for bodily conditions and emotions."""

    def test_sick_state_empathy(self):
        resp = HindiVocabEngine.get_empathetic_response("aaj meri tabiyat kharab lag rahi hai")
        assert resp is not None
        assert "rest" in resp.lower() or "tabiyat" in resp.lower()

    def test_dizzy_state_empathy(self):
        resp = HindiVocabEngine.get_empathetic_response("mujhe chakkar aa rahe hain")
        assert resp is not None
        assert "paani" in resp.lower() or "chakkar" in resp.lower()

    def test_calm_emotion_empathy(self):
        resp = HindiVocabEngine.get_empathetic_response("aaj mann bahut shant hai")
        assert resp is not None
        assert "sukoon" in resp.lower() or "shanti" in resp.lower()

    def test_confusion_emotion_empathy(self):
        resp = HindiVocabEngine.get_empathetic_response("main bahut confused hoon")
        assert resp is not None
        assert "clarify" in resp.lower() or "confusion" in resp.lower()


# ---------------------------------------------------------------------------
# 5. Quantity Modifiers & Scroll Directions
# ---------------------------------------------------------------------------

class TestModifiersAndScroll:
    def test_quantity_multipliers(self):
        assert HindiVocabEngine.get_quantity_modifier("poora volume kar do")[1] == 1.00
        assert HindiVocabEngine.get_quantity_modifier("bilkul nahi sunna")[1] == 0.00
        assert HindiVocabEngine.get_quantity_modifier("dugna speed badhao")[1] == 2.00

    def test_scroll_directions(self):
        assert HindiVocabEngine.get_direction_for_scroll("seedha chalo") == "DOWN"
        assert HindiVocabEngine.get_direction_for_scroll("beech mein jao") == "CENTER"


# ---------------------------------------------------------------------------
# 6. Performance & Scale Benchmark
# ---------------------------------------------------------------------------

class TestPerformanceBenchmark:
    def test_sub_millisecond_classification_latency(self):
        """Verifies that in-memory classification takes < 0.05 ms per lookup."""
        words_to_test = [
            "aana", "jaana", "upar", "niche", "ye", "wo", "bhookh", "neend",
            "khushi", "gussa", "abhi", "baad mein", "kholo", "band karo",
            "thoda", "zyada", "ye wala", "last wala", "tabiyat kharab", "dugna"
        ]

        # Warm up
        for w in words_to_test:
            HindiVocabEngine.classify(w)

        # Timed benchmark: 1000 iterations
        start = time.perf_counter()
        for _ in range(1000):
            for w in words_to_test:
                HindiVocabEngine.classify(w)
        total_time = time.perf_counter() - start

        # 20 words * 1000 iterations = 20,000 lookups
        avg_latency_ms = (total_time / 20000) * 1000
        assert avg_latency_ms < 0.05, f"Lookup latency too high: {avg_latency_ms:.5f} ms"
