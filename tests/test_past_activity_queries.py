import pytest
from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from brain.semantic_parser import HinglishNLUParser


def test_conversational_intent_activity_queries():
    phrases = [
        "main ne abhi konsi video dekhi",
        "maine abhi konsi video dekhi",
        "maine abhi kya dekha",
        "abhi konsi video chal rahi thi",
        "pichli video konsi thi",
        "what video was i watching",
        "what was i watching",
        "abhi main kya kar raha tha"
    ]
    for p in phrases:
        res = ConversationalIntentClassifier.classify(p)
        assert res.intent_type == ConversationalIntentType.ACTION_COMMAND, f"Failed for {p}: {res}"
        assert res.is_executable is True, f"Failed is_executable for {p}"
        assert res.target == "activity", f"Failed target for {p}"


def test_semantic_parser_activity_queries():
    act1 = HinglishNLUParser.parse("main ne abhi konsi video dekhi")
    assert act1 is not None
    assert act1.intent == "QUERY_PAST_MEDIA"
    assert act1.action == "get_last_media"

    act2 = HinglishNLUParser.parse("abhi konsi video chal rahi thi")
    assert act2 is not None
    assert act2.intent == "QUERY_PAST_MEDIA"
    assert act2.action == "get_last_media"

    act3 = HinglishNLUParser.parse("what video was i watching")
    assert act3 is not None
    assert act3.intent == "QUERY_PAST_MEDIA"
    assert act3.action == "get_last_media"

    act4 = HinglishNLUParser.parse("abhi main kya kar raha tha")
    assert act4 is not None
    assert act4.intent == "QUERY_PAST_ACTIVITY"
    assert act4.action == "get_last_activity"


def test_vocabulary_layer_plural_guard():
    from unittest.mock import MagicMock
    from learning.vocabulary_layer import VocabularyLayer
    db = MagicMock()
    db.execute_query.return_value = [{"name": "video", "normalized_value": "videos"}]
    vl = VocabularyLayer(db)
    # The guard should reject substituting 'video' -> 'videos'
    res = vl.resolve_text("main ne abhi konsi video dekhi")
    assert "konsi videos dekhi" not in res
    assert "video" in res
