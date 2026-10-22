# tests/test_hindi_vocab_engine.py
"""
Comprehensive tests for the Hindi/Hinglish Semantic Vocabulary Engine.

Coverage:
  - Single word classification (all 9 categories)
  - Multi-word phrase greedy matching (ye wala, baad mein, etc.)
  - enrich_speech_entities() across categories
  - Empathetic response generation (body state & emotion)
  - kal disambiguation by hour
  - Quantity modifier mapping
  - Direction-to-scroll mapping
  - Object reference resolution
  - 'thoda' and 'ek' NOT in normalizer FILLERS (preserved in commands)
  - Normalizer new synonyms (rok do, bhejo, etc.)
  - Regression: existing features unaffected
"""

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
from core.semantic.normalizer import HinglishNormalizer


# ---------------------------------------------------------------------------
# 1. Single-word classification — MOVEMENT
# ---------------------------------------------------------------------------

class TestMovement:
    @pytest.mark.parametrize("word,expected_concept", [
        ("aana",   MovementConcept.ARRIVE),
        ("jaana",  MovementConcept.DEPART),
        ("chalna", MovementConcept.WALK),
        ("rukna",  MovementConcept.STOP),
        ("baithna",MovementConcept.SIT),
        ("uthna",  MovementConcept.RISE),
        ("daudna", MovementConcept.RUN),
        ("lautna", MovementConcept.RETURN),
    ])
    def test_movement_word(self, word, expected_concept):
        result = HindiVocabEngine.classify(word)
        assert result is not None, f"'{word}' should be classified"
        cat, concept = result
        assert cat == HindiVocabCategory.MOVEMENT
        assert concept == expected_concept

    def test_movement_case_insensitive(self):
        """All lookups are lowercase-normalized."""
        result = HindiVocabEngine.classify("AANA")
        assert result is not None
        assert result[1] == MovementConcept.ARRIVE


# ---------------------------------------------------------------------------
# 2. DIRECTION
# ---------------------------------------------------------------------------

class TestDirection:
    @pytest.mark.parametrize("word,expected_concept", [
        ("upar",   DirectionConcept.UP),
        ("niche",  DirectionConcept.DOWN),
        ("aage",   DirectionConcept.FORWARD),
        ("peeche", DirectionConcept.BACK),
        ("idhar",  DirectionConcept.HERE_DIR),
        ("udhar",  DirectionConcept.THERE_DIR),
        ("yahan",  DirectionConcept.HERE),
        ("wahan",  DirectionConcept.THERE),
        ("andar",  DirectionConcept.INSIDE),
        ("bahar",  DirectionConcept.OUTSIDE),
        ("left",   DirectionConcept.LEFT),
        ("right",  DirectionConcept.RIGHT),
        ("pass",   DirectionConcept.NEAR),
        ("door",   DirectionConcept.FAR),
    ])
    def test_direction_word(self, word, expected_concept):
        result = HindiVocabEngine.classify(word)
        assert result is not None, f"'{word}' should be classified"
        cat, concept = result
        assert cat == HindiVocabCategory.DIRECTION
        assert concept == expected_concept


# ---------------------------------------------------------------------------
# 3. OBJECT REFERENCE
# ---------------------------------------------------------------------------

class TestObjectReference:
    @pytest.mark.parametrize("word,expected_concept", [
        ("ye",   ObjectRefConcept.THIS),
        ("yeh",  ObjectRefConcept.THIS),
        ("iska", ObjectRefConcept.THIS),
        ("iski", ObjectRefConcept.THIS),
        ("isse", ObjectRefConcept.THIS),
        ("isko", ObjectRefConcept.THIS),
        ("inhe", ObjectRefConcept.THIS),
        ("isme", ObjectRefConcept.THIS),
        ("wo",   ObjectRefConcept.THAT),
        ("woh",  ObjectRefConcept.THAT),
        ("uska", ObjectRefConcept.THAT),
        ("uski", ObjectRefConcept.THAT),
        ("usse", ObjectRefConcept.THAT),
        ("usko", ObjectRefConcept.THAT),
        ("unhe", ObjectRefConcept.THAT),
        ("usme", ObjectRefConcept.THAT),
    ])
    def test_object_reference_word(self, word, expected_concept):
        result = HindiVocabEngine.classify(word)
        assert result is not None, f"'{word}' should be classified"
        cat, concept = result
        assert cat == HindiVocabCategory.OBJECT_REFERENCE
        assert concept == expected_concept


# ---------------------------------------------------------------------------
# 4. BODY STATE
# ---------------------------------------------------------------------------

class TestBodyState:
    @pytest.mark.parametrize("word,expected_concept", [
        ("bhookh",   BodyStateConcept.HUNGER),
        ("pyaas",    BodyStateConcept.THIRST),
        ("neend",    BodyStateConcept.SLEEP_STATE),
        ("thakan",   BodyStateConcept.FATIGUE),
        ("dard",     BodyStateConcept.PAIN),
        ("garmi",    BodyStateConcept.HOT),
        ("sardi",    BodyStateConcept.COLD),
        ("aaram",    BodyStateConcept.REST),
    ])
    def test_body_state_word(self, word, expected_concept):
        result = HindiVocabEngine.classify(word)
        assert result is not None
        cat, concept = result
        assert cat == HindiVocabCategory.BODY_STATE
        assert concept == expected_concept


# ---------------------------------------------------------------------------
# 5. EMOTION
# ---------------------------------------------------------------------------

class TestEmotion:
    @pytest.mark.parametrize("word,expected_concept", [
        ("khushi",    EmotionConcept.JOY),
        ("dukh",      EmotionConcept.SADNESS),
        ("gussa",     EmotionConcept.ANGER),
        ("pyaar",     EmotionConcept.LOVE),
        ("nafrat",    EmotionConcept.HATRED),
        ("dar",       EmotionConcept.FEAR),
        ("tension",   EmotionConcept.ANXIETY),
        ("pareshani", EmotionConcept.WORRY),
        ("excited",   EmotionConcept.EXCITEMENT),
        ("bored",     EmotionConcept.BOREDOM),
    ])
    def test_emotion_word(self, word, expected_concept):
        result = HindiVocabEngine.classify(word)
        assert result is not None
        cat, concept = result
        assert cat == HindiVocabCategory.EMOTION
        assert concept == expected_concept


# ---------------------------------------------------------------------------
# 6. TIME
# ---------------------------------------------------------------------------

class TestTime:
    @pytest.mark.parametrize("word,expected_concept", [
        ("abhi",    TimeRefConcept.NOW),
        ("baad",    TimeRefConcept.LATER),
        ("pehle",   TimeRefConcept.BEFORE),
        ("pahle",   TimeRefConcept.BEFORE),
        ("kal",     TimeRefConcept.YESTERDAY_OR_TOMORROW),
        ("aaj",     TimeRefConcept.TODAY),
        ("parso",   TimeRefConcept.DAY_AFTER),
        ("subah",   TimeRefConcept.MORNING),
        ("dopahar", TimeRefConcept.AFTERNOON),
        ("shaam",   TimeRefConcept.EVENING),
        ("raat",    TimeRefConcept.NIGHT),
    ])
    def test_time_word(self, word, expected_concept):
        result = HindiVocabEngine.classify(word)
        assert result is not None, f"'{word}' should classify as TIME"
        cat, concept = result
        assert cat == HindiVocabCategory.TIME
        assert concept == expected_concept

    def test_baad_mein_multiword(self):
        """'baad mein' (2-word phrase) should match as LATER."""
        result = HindiVocabEngine.classify("baad mein")
        assert result is not None
        assert result[1] == TimeRefConcept.LATER


# ---------------------------------------------------------------------------
# 7. ACTION
# ---------------------------------------------------------------------------

class TestAction:
    @pytest.mark.parametrize("phrase,expected_concept", [
        ("kholo",       ActionVerbConcept.OPEN),
        ("band karo",   ActionVerbConcept.CLOSE),
        ("chalao",      ActionVerbConcept.PLAY),
        ("rok do",      ActionVerbConcept.STOP),
        ("bhejo",       ActionVerbConcept.SEND),
        ("lao",         ActionVerbConcept.BRING),
        ("le jao",      ActionVerbConcept.TAKE),
        ("rakho",       ActionVerbConcept.PLACE),
        ("hatao",       ActionVerbConcept.REMOVE),
        ("dikhao",      ActionVerbConcept.SHOW),
        ("chhupao",     ActionVerbConcept.HIDE),
        ("likho",       ActionVerbConcept.WRITE),
        ("padho",       ActionVerbConcept.READ),
        ("bolo",        ActionVerbConcept.SPEAK),
        ("sunao",       ActionVerbConcept.LISTEN),
    ])
    def test_action_word(self, phrase, expected_concept):
        result = HindiVocabEngine.classify(phrase)
        assert result is not None, f"'{phrase}' should classify as ACTION"
        cat, concept = result
        assert cat == HindiVocabCategory.ACTION
        assert concept == expected_concept


# ---------------------------------------------------------------------------
# 8. QUANTITY
# ---------------------------------------------------------------------------

class TestQuantity:
    @pytest.mark.parametrize("word,expected_concept", [
        ("thoda",  QuantityConcept.SMALL),
        ("zyada",  QuantityConcept.LARGE),
        ("jyada",  QuantityConcept.LARGE),
        ("kam",    QuantityConcept.LESS),
        ("sab",    QuantityConcept.ALL),
        ("kuch",   QuantityConcept.SOME),
        ("koi",    QuantityConcept.ANY),
        ("ek",     QuantityConcept.ONE),
        ("do",     QuantityConcept.TWO),
        ("saare",  QuantityConcept.ALL_OF),
        ("saara",  QuantityConcept.ALL_OF),
        ("aadha",  QuantityConcept.HALF),
    ])
    def test_quantity_word(self, word, expected_concept):
        result = HindiVocabEngine.classify(word)
        assert result is not None, f"'{word}' should classify as QUANTITY"
        cat, concept = result
        assert cat == HindiVocabCategory.QUANTITY
        assert concept == expected_concept


# ---------------------------------------------------------------------------
# 9. REFERENCE
# ---------------------------------------------------------------------------

class TestReference:
    @pytest.mark.parametrize("phrase,expected_concept", [
        ("ye wala",     ReferenceConcept.FIRST),
        ("pehla",       ReferenceConcept.FIRST),
        ("doosra",      ReferenceConcept.SECOND),
        ("dusra wala",  ReferenceConcept.SECOND),
        ("last wala",   ReferenceConcept.LAST),
        ("upar wala",   ReferenceConcept.TOP),
        ("niche wala",  ReferenceConcept.BOTTOM),
        ("pichla",      ReferenceConcept.PREVIOUS),
        ("agla",        ReferenceConcept.NEXT),
        ("wo wala",     ReferenceConcept.SECOND),
    ])
    def test_reference_word(self, phrase, expected_concept):
        result = HindiVocabEngine.classify(phrase)
        assert result is not None, f"'{phrase}' should classify as REFERENCE"
        cat, concept = result
        assert cat == HindiVocabCategory.REFERENCE
        assert concept == expected_concept


# ---------------------------------------------------------------------------
# 10. enrich_speech_entities()
# ---------------------------------------------------------------------------

class TestEnrichSpeechEntities:
    def test_time_entity_found(self):
        entities = HindiVocabEngine.enrich_speech_entities("abhi screenshot lo")
        assert entities.time_ref == TimeRefConcept.NOW

    def test_direction_entity_found(self):
        entities = HindiVocabEngine.enrich_speech_entities("upar scroll karo")
        assert entities.direction == DirectionConcept.UP

    def test_quantity_entity_found(self):
        entities = HindiVocabEngine.enrich_speech_entities("thoda volume badhao")
        assert entities.quantity == QuantityConcept.SMALL

    def test_emotion_entity_found(self):
        entities = HindiVocabEngine.enrich_speech_entities("aaj gussa aa raha hai")
        assert entities.emotion == EmotionConcept.ANGER

    def test_body_state_entity_found(self):
        entities = HindiVocabEngine.enrich_speech_entities("mujhe bhookh lag rahi hai")
        assert entities.body_state == BodyStateConcept.HUNGER

    def test_action_entity_found(self):
        entities = HindiVocabEngine.enrich_speech_entities("chrome kholo")
        assert entities.action == ActionVerbConcept.OPEN

    def test_multiword_reference_greedy(self):
        """'ye wala' should match as REFERENCE (FIRST), not 'ye' as OBJECT_REF."""
        entities = HindiVocabEngine.enrich_speech_entities("ye wala kholo")
        assert entities.reference == ReferenceConcept.FIRST
        # object_ref should be None because 'ye' was consumed by 'ye wala'
        assert entities.object_ref is None

    def test_multiple_categories_in_one_utterance(self):
        """'abhi upar scroll karo' should yield both TIME and DIRECTION."""
        entities = HindiVocabEngine.enrich_speech_entities("abhi upar scroll karo")
        assert entities.time_ref == TimeRefConcept.NOW
        assert entities.direction == DirectionConcept.UP

    def test_no_matches(self):
        """Pure English/app commands should yield empty EnrichedEntities."""
        entities = HindiVocabEngine.enrich_speech_entities("open chrome")
        assert len(entities.matches) == 0

    def test_has_category_helper(self):
        entities = HindiVocabEngine.enrich_speech_entities("zyada brightness badhao")
        assert entities.has_category(HindiVocabCategory.QUANTITY)
        assert not entities.has_category(HindiVocabCategory.EMOTION)


# ---------------------------------------------------------------------------
# 11. Empathetic response
# ---------------------------------------------------------------------------

class TestEmpatheticResponse:
    def test_body_state_returns_response(self):
        resp = HindiVocabEngine.get_empathetic_response("mujhe bhookh lag rahi hai")
        assert resp is not None
        assert isinstance(resp, str)
        assert len(resp) > 0

    def test_emotion_returns_response(self):
        resp = HindiVocabEngine.get_empathetic_response("bahut gussa aa raha hai")
        assert resp is not None
        assert "Boss" in resp  # All empathy responses address "Boss"

    def test_no_emotion_returns_none(self):
        resp = HindiVocabEngine.get_empathetic_response("chrome kholo")
        assert resp is None

    def test_all_body_states_have_responses(self):
        bodies = list(BodyStateConcept)
        for word, concept in {
            "bhookh": BodyStateConcept.HUNGER,
            "pyaas": BodyStateConcept.THIRST,
            "neend": BodyStateConcept.SLEEP_STATE,
            "thakan": BodyStateConcept.FATIGUE,
            "dard": BodyStateConcept.PAIN,
            "garmi": BodyStateConcept.HOT,
            "sardi": BodyStateConcept.COLD,
            "aaram": BodyStateConcept.REST,
        }.items():
            resp = HindiVocabEngine.get_empathetic_response(word)
            assert resp is not None, f"No response for body state '{word}'"

    def test_all_emotions_have_responses(self):
        for word in ["khushi", "dukh", "gussa", "pyaar", "nafrat",
                     "dar", "tension", "pareshani", "excited", "bored"]:
            resp = HindiVocabEngine.get_empathetic_response(word)
            assert resp is not None, f"No response for emotion '{word}'"


# ---------------------------------------------------------------------------
# 12. kal disambiguation
# ---------------------------------------------------------------------------

class TestKalDisambiguation:
    def test_kal_evening_is_tomorrow(self):
        # 17:00 → tomorrow
        assert HindiVocabEngine.disambiguate_kal(17) == "TOMORROW"

    def test_kal_night_is_tomorrow(self):
        assert HindiVocabEngine.disambiguate_kal(22) == "TOMORROW"

    def test_kal_morning_is_yesterday(self):
        # 10:00 → yesterday
        assert HindiVocabEngine.disambiguate_kal(10) == "YESTERDAY"

    def test_kal_afternoon_is_yesterday(self):
        assert HindiVocabEngine.disambiguate_kal(14) == "YESTERDAY"

    def test_kal_boundary(self):
        # 16:59 → yesterday; 17:00 → tomorrow
        assert HindiVocabEngine.disambiguate_kal(16) == "YESTERDAY"
        assert HindiVocabEngine.disambiguate_kal(17) == "TOMORROW"


# ---------------------------------------------------------------------------
# 13. Quantity modifier
# ---------------------------------------------------------------------------

class TestQuantityModifier:
    def test_thoda_small_multiplier(self):
        result = HindiVocabEngine.get_quantity_modifier("thoda volume badhao")
        assert result is not None
        concept, mult = result
        assert concept == QuantityConcept.SMALL
        assert mult == pytest.approx(0.25)

    def test_zyada_large_multiplier(self):
        result = HindiVocabEngine.get_quantity_modifier("zyada brightness chahiye")
        assert result is not None
        concept, mult = result
        assert concept == QuantityConcept.LARGE
        assert mult == pytest.approx(0.75)

    def test_aadha_half_multiplier(self):
        result = HindiVocabEngine.get_quantity_modifier("aadha screen karo")
        assert result is not None
        assert result[0] == QuantityConcept.HALF
        assert result[1] == pytest.approx(0.50)

    def test_no_quantity_returns_none(self):
        result = HindiVocabEngine.get_quantity_modifier("chrome kholo")
        assert result is None


# ---------------------------------------------------------------------------
# 14. Direction scroll mapping
# ---------------------------------------------------------------------------

class TestDirectionScroll:
    @pytest.mark.parametrize("text,expected_dir", [
        ("upar scroll karo",   "UP"),
        ("niche jao",          "DOWN"),
        ("aage chalao",        "DOWN"),   # forward = scroll down
        ("peeche jao",         "UP"),     # back = scroll up
        ("left scroll karo",   "LEFT"),
        ("right move karo",    "RIGHT"),
    ])
    def test_direction_scroll(self, text, expected_dir):
        result = HindiVocabEngine.get_direction_for_scroll(text)
        assert result == expected_dir

    def test_no_direction_returns_none(self):
        assert HindiVocabEngine.get_direction_for_scroll("chrome kholo") is None


# ---------------------------------------------------------------------------
# 15. Object reference resolution
# ---------------------------------------------------------------------------

class TestObjectRefResolution:
    def test_ye_resolves_to_last_app(self):
        resolved = HindiVocabEngine.resolve_object_reference(
            "ye kholo", last_app="notepad"
        )
        assert resolved == "notepad"

    def test_wo_resolves_to_last_website(self):
        resolved = HindiVocabEngine.resolve_object_reference(
            "wo kholo", last_website="youtube", last_app="chrome"
        )
        assert resolved == "youtube"

    def test_ye_wala_resolves_to_last_app(self):
        resolved = HindiVocabEngine.resolve_object_reference(
            "ye wala kholo", last_app="excel"
        )
        assert resolved == "excel"

    def test_no_reference_returns_none(self):
        resolved = HindiVocabEngine.resolve_object_reference(
            "chrome kholo", last_app="notepad"
        )
        assert resolved is None

    def test_no_context_returns_none(self):
        resolved = HindiVocabEngine.resolve_object_reference("ye kholo")
        assert resolved is None


# ---------------------------------------------------------------------------
# 16. Normalizer regression: 'thoda' and 'ek' NOT in FILLERS
# ---------------------------------------------------------------------------

class TestNormalizerFillerRegression:
    def test_thoda_preserved_in_command(self):
        """'thoda' should NOT be stripped as a filler by LinguisticFillerFilter."""
        from core.speech_understanding import LinguisticFillerFilter
        result = LinguisticFillerFilter.clean("thoda volume badhao")
        assert "thoda" in result, "'thoda' should be preserved (not stripped as filler)"

    def test_ek_preserved_in_command(self):
        """'ek' should NOT be stripped as a filler by LinguisticFillerFilter."""
        from core.speech_understanding import LinguisticFillerFilter
        result = LinguisticFillerFilter.clean("ek reminder set karo")
        assert "ek" in result, "'ek' should be preserved (not stripped as filler)"

    def test_bhai_still_stripped(self):
        """'bhai' IS a filler and should be stripped by LinguisticFillerFilter."""
        from core.speech_understanding import LinguisticFillerFilter
        result = LinguisticFillerFilter.clean("bhai chrome kholo")
        assert "bhai" not in result

    def test_jaldi_not_a_filler_so_preserved(self):
        """'jaldi' is NOT registered as a LinguisticFillerFilter filler — it's preserved."""
        from core.speech_understanding import LinguisticFillerFilter
        result = LinguisticFillerFilter.clean("jaldi screenshot lo")
        # jaldi is intentionally NOT stripped (it conveys urgency, not noise)
        assert "jaldi" in result


# ---------------------------------------------------------------------------
# 17. Normalizer new action synonym corrections
# ---------------------------------------------------------------------------

class TestNormalizerActionSynonyms:
    def test_rok_do_normalized(self):
        result = HinglishNormalizer.normalize_text("gaana rok do")
        assert "stop" in result

    def test_bhej_do_normalized(self):
        result = HinglishNormalizer.normalize_text("message bhej do")
        assert "send" in result

    def test_dikha_do_normalized(self):
        result = HinglishNormalizer.normalize_text("screen dikha do")
        assert "show" in result

    def test_hata_do_normalized(self):
        result = HinglishNormalizer.normalize_text("icon hata do")
        assert "remove" in result


# ---------------------------------------------------------------------------
# 18. classify() — non-vocab words return None
# ---------------------------------------------------------------------------

class TestClassifyNegative:
    @pytest.mark.parametrize("word", [
        "chrome", "youtube", "open", "hello", "boss", "karo", "please",
        "volume", "screenshot", "whatsapp",
    ])
    def test_non_vocab_word_returns_none(self, word):
        result = HindiVocabEngine.classify(word)
        assert result is None, f"'{word}' should NOT be in Hindi vocab (not a semantic category word)"


# ---------------------------------------------------------------------------
# 19. PRESERVE_WORDS set completeness
# ---------------------------------------------------------------------------

class TestPreserveWords:
    def test_quantity_words_in_preserve_set(self):
        """All quantity words must be in PRESERVE_WORDS so they're never stripped."""
        for word in ["thoda", "zyada", "kam", "sab", "kuch", "koi", "ek", "do", "saare", "aadha"]:
            assert word in HindiVocabEngine.PRESERVE_WORDS, f"'{word}' missing from PRESERVE_WORDS"

    def test_time_words_in_preserve_set(self):
        for word in ["abhi", "aaj", "kal", "subah", "raat", "shaam", "dopahar"]:
            assert word in HindiVocabEngine.PRESERVE_WORDS

    def test_emotion_words_in_preserve_set(self):
        for word in ["gussa", "khushi", "tension", "pareshani"]:
            assert word in HindiVocabEngine.PRESERVE_WORDS
