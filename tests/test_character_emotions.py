# tests/test_character_emotions.py
"""Reference-faithful character emotions: shapes, badges, tints, crossfade,
transparency (no black box), layering smoke, and performance bounds."""

import math

import pytest
from PySide6.QtWidgets import QApplication

from gui.island.character import JarvisCharacter

app = QApplication.instance() or QApplication(["-platform", "offscreen"])


@pytest.fixture()
def char():
    c = JarvisCharacter(parent=None, size=48)
    yield c
    try:
        c.stop()
        c.close()
    except Exception:
        pass


def test_legacy_eye_shapes_preserved(char):
    """Existing contracts must not move (coucou_ui asserts these apertures)."""
    char.set_system_state("listening")
    assert char._eye_aperture == "wide"
    char.set_system_state("success")
    assert char._eye_aperture == "arc_happy"
    char.set_system_state("error")
    assert char._eye_aperture == "alert_line"
    char.set_system_state("ready")
    assert char._current_state == "idle"
    char.trigger_love_emote(duration_s=0.2)
    assert char._eye_shape == "love_hearts"


def test_new_feeling_shapes():
    """Reference feelings: worried (sad), spiral (confused)."""
    assert JarvisCharacter.CANONICAL_STATES  # sanity
    c = JarvisCharacter(parent=None, size=36)
    try:
        c.set_system_state("sad")
        assert c._eye_shape == "worried"
        assert c._eye_aperture == "worried"
        c.set_system_state("confused")
        assert c._eye_shape == "spiral"
        assert c._eye_aperture == "spiral"
    finally:
        c.stop()
        c.close()


def test_badge_kinds_per_state(char):
    char.set_system_state("listening")
    assert char.badge_kind == "dots"
    char.set_system_state("speaking")
    assert char.badge_kind is None  # Speaking wears no dots; reserved strictly for thinking/working
    char.set_system_state("error")
    assert char.badge_kind == "dot"
    char.set_system_state("approval")
    assert char.badge_kind == "alert"
    char.set_system_state("working")
    assert char.badge_kind == "dots"  # working wears the blue "..." (reference)
    char.set_system_state("success")
    assert char.badge_kind == "dot"
    char.set_system_state("confused")
    assert char.badge_kind == "question"
    char.set_system_state("idle")
    assert char.badge_kind is None  # clean face at rest: no stuck-progress look
    char.set_system_state("thinking")
    assert char.badge_kind == "dots"  # violet thinking dots
    char.set_system_state("searching")
    assert char.badge_kind == "search"


def test_badge_pop_restarts_on_change(char):
    char.set_system_state("idle")
    char._badge_pop = 1.0
    char.set_system_state("listening")
    assert char._badge_pop == 0.0


def test_emotion_crossfade_glides(char):
    """Tint must travel toward the new feeling instead of snapping."""
    speaking_tint = JarvisCharacter._STATE_TINTS["speaking"]

    def dist():
        return math.dist(char._tint_cur, speaking_tint)

    char.set_system_state("idle")
    for _ in range(30):
        char._on_tick()
    d0 = dist()
    char.set_system_state("speaking")
    for _ in range(6):
        char._on_tick()
    d1 = dist()
    assert d1 < d0, "tint did not glide toward speaking"


def test_no_black_box_transparency(char):
    """Widget corners must stay transparent — no black rectangle behind Mochi."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    assert char.autoFillBackground() is False
    char.set_system_state("happy")
    char._on_tick()
    img = QImage(char.size(), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    char.render(img)
    w, h = img.width(), img.height()
    for x, y in ((1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)):
        assert img.pixelColor(x, y).alpha() < 30, f"opaque corner at {(x, y)}"
    # …but the body itself really painted (center opaque).
    assert img.pixelColor(w // 2, h // 2).alpha() > 200


def test_render_smoke_all_states_and_outfits(char):
    """Every feeling × outfit paints without exceptions (layering order safe)."""
    states = list(JarvisCharacter.CANONICAL_STATES) + [
        "sleeping", "working", "speaking", "approval", "warning",
        "emote_love", "emote_proud", "proud", "sad",
    ]
    for state in states:
        char.set_system_state(state)
        char._on_tick()
        char.repaint()
    for outfit in ("none", "crown", "sunglasses", "santa_hat"):
        char.set_accessory(outfit)
        char.set_system_state("happy")
        char._on_tick()
        char.repaint()
    for emote in ("love", "proud", "happy", "surprised", "confused", "sad"):
        char.trigger_emote(emote, duration_s=0.2)
        char._on_tick()
        char.repaint()
    char.set_accessory("none")


def test_celebration_stars_bounded(char):
    char.set_system_state("idle")
    char._stars.clear()
    char.set_system_state("proud")
    assert 1 <= len(char._stars) <= 14
    for _ in range(200):
        char._on_tick()
    assert len(char._stars) <= 14  # drains, never leaks


def test_mouth_closes_after_voice_ends(char):
    """Stuck-speaking self-heals: no TTS + no voice → idle (mouth shut)."""
    char.set_system_state("speaking")
    char.set_tts_active(True)
    assert char._current_state == "speaking"
    char.set_tts_active(False)
    char._last_voice_time -= 5.0
    char._speaking_since -= 5.0
    char._target_audio_level = 0.0
    char._audio_level = 0.0
    char._on_tick()
    assert char._current_state == "idle"


def test_mouth_stays_open_while_tts_live(char):
    """Real TTS sound keeps the mouth talking even with a silent mic."""
    char.set_system_state("speaking")
    char.set_tts_active(True)
    char._last_voice_time -= 5.0
    char._speaking_since -= 5.0
    char._target_audio_level = 0.0
    char._audio_level = 0.0
    char._on_tick()
    assert char._current_state == "speaking"


def test_fresh_voice_keeps_mouth_alive(char):
    """Loud mic voice keeps speaking alive without any TTS flag."""
    char.set_system_state("speaking")
    char.set_tts_active(False)
    char._speaking_since -= 5.0
    char.set_audio_level(0.6, True)
    char._on_tick()
    assert char._current_state == "speaking"


def test_stale_speaking_paints_closed_smile(char):
    """Even before the watchdog fires, a voiceless frame never gapes."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    char.set_system_state("speaking")
    char.set_tts_active(False)
    char._last_voice_time -= 5.0
    char._audio_level = 0.0
    char._target_audio_level = 0.0
    img = QImage(char.size(), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    char.render(img)  # smile fallback path — must not raise
    assert img.pixelColor(2, 2).alpha() < 30


def _render_pixels(char):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    img = QImage(char.size(), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    char.render(img)
    return [img.pixelColor(x, y).getRgb()
            for x in range(0, img.width(), 3)
            for y in range(0, img.height(), 3)]


def test_speaking_visuals_ignore_audio(char, monkeypatch):
    """No lip-sync: frozen clock + different audio levels → identical frame."""
    import time as _time
    monkeypatch.setattr(_time, "time", lambda: 1234.5)
    char.set_system_state("speaking")
    char.set_tts_active(True)
    char._audio_level = 0.0
    char._target_audio_level = 0.0
    quiet = _render_pixels(char)
    char._audio_level = 0.9
    char._target_audio_level = 0.9
    loud = _render_pixels(char)
    assert quiet == loud


def test_badge_dots_animate_over_time(char, monkeypatch):
    """The '...' badge is the aliveness: dots move between two ticks of the clock."""
    import time as _time
    clock = [1000.0]
    monkeypatch.setattr(_time, "time", lambda: clock[0])
    char.set_system_state("thinking")
    frame_a = _render_pixels(char)
    clock[0] += 0.6
    frame_b = _render_pixels(char)
    assert frame_a != frame_b
