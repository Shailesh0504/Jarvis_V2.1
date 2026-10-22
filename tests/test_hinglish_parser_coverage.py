# tests/test_hinglish_parser_coverage.py
"""Hinglish parser coverage locks (2026-09-25).

Locks the verified battery: normalizer must preserve command-critical Hindi
verbs (band/kam/hatao/gana/baja), and the semantic orchestrator must resolve
close/volume/screenshot/delete/brightness Hinglish phrasings end-to-end.
"""

from core.semantic.normalizer import HinglishNormalizer
from core.semantic.orchestrator import SemanticPipelineOrchestrator as SPO
from core.weather import get_weather_engine


def test_normalizer_preserves_command_verbs():
    for w in ["band", "kam", "hatao", "gana", "baja"]:
        assert HinglishNormalizer.normalize_text(w) == w, f"corrupted: {w}"
    # Sentence-level (the actual reported failures)
    assert HinglishNormalizer.normalize_text("notepad band karo") == "notepad band karo"
    assert HinglishNormalizer.normalize_text("awaz kam karo") == "awaz kam karo"


def _intent(text):
    a = SPO.parse(text)
    assert a is not None, f"no parse for {text!r}"
    return a


def test_band_close_phrasings():
    assert _intent("notepad band karo").intent == "WINDOW_CLOSE"
    assert _intent("chrome band kar do").intent == "WINDOW_CLOSE"
    assert _intent("chrome hatao").intent == "WINDOW_CLOSE"
    assert _intent("pc band karo").intent == "SYSTEM_SHUTDOWN"


def test_volume_down_hinglish():
    a = _intent("awaz kam karo")
    assert (a.intent, a.service, a.action) == ("VOLUME_DOWN", "audio", "volume_down")


def test_screenshot_photo_synonyms():
    assert _intent("screen ki photo lo").action == "take_screenshot"
    assert _intent("screen ka photo lo").action == "take_screenshot"


def test_file_delete_phrasings():
    for t in ["test.txt delete karo", "file delete karo test.txt", "test file hatao"]:
        a = _intent(t)
        assert a.intent == "DELETE_FILE", t
        assert a.service == "files" and a.action == "delete", t


def test_brightness_phrasings():
    assert _intent("brightness badhao").action == "brightness_up"
    assert _intent("brightness kam karo").action == "brightness_down"
    a = _intent("brightness 70 karo")
    assert a.action == "set_screen_brightness" and a.parameters.get("level") == 70
    assert _intent("brightness kitni hai").action == "get_screen_brightness"


def test_container_guards_intact():
    # Website/tab inside browser must NOT close the browser
    from core.semantic.parsers.windows import parse_app_close
    assert parse_app_close("chrome me youtube band karo", "chrome me youtube band karo") is None
    a = _intent("chrome wala youtube band kar do")
    assert a.intent == "UNIVERSAL_TARGET_ACTION"


def test_weather_mousam_gate():
    w = get_weather_engine()
    assert w.is_weather_query("weather batao") is True
    assert w.is_weather_query("aaj ka mousam") is True
