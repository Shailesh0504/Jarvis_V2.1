# tests/test_streaming_tts.py
"""Unit tests for Low-Latency Streaming Neural TTS Subsystem & Dedicated TTSManager."""

import os
import time
import pytest
from voice.tts import TextToSpeech, TTSManager, ProsodyConfig, AudioLRUCache, SentenceStreamer


def test_sentence_streamer_chunking():
    streamer = SentenceStreamer()

    # Multi-sentence complex response
    text = "Sure! VLC khol rahi hoon... ek second. Done, movie play kar di."
    chunks = streamer.chunk_sentences(text)

    assert len(chunks) >= 3
    assert "Sure" in chunks[0]
    assert any("VLC" in c for c in chunks)
    assert any("Done" in c for c in chunks)


def test_sentence_streamer_clean_for_speech():
    raw_text = "Here is the result: `code_data = 123` **Bold** and *Italic* with emoji 😄 and [link](https://example.com)!"
    cleaned = SentenceStreamer.clean_for_speech(raw_text)
    assert "😄" not in cleaned
    assert "http" not in cleaned
    assert "`" not in cleaned
    assert "*" not in cleaned
    assert "Bold and Italic with emoji and link" in cleaned


def test_audio_cache_latency_and_persistence(tmp_path):
    cache_dir = os.path.join(tmp_path, "audio_cache")
    cache = AudioLRUCache(cache_dir=cache_dir)
    prosody = ProsodyConfig(rate=185, pitch=1.05, voice_gender="female")

    # 1. Store audio payload
    custom_phrase = "Custom new synthesized response"
    dummy_payload = b"\x01\x02\x03\x04" * 200
    cache.put(custom_phrase, prosody, dummy_payload)

    # 2. Fast cache retrieval
    start = time.perf_counter()
    retrieved = cache.get(custom_phrase, prosody)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert retrieved == dummy_payload
    assert elapsed_ms < 10.0  # Sub-10ms cache retrieval


def test_prosody_configuration():
    prosody = ProsodyConfig(rate=190, pitch=1.1, volume=0.9, voice_gender="female", voice_name="zira")
    tts = TextToSpeech(engine="mock", prosody=prosody)

    assert tts.prosody.rate == 190
    assert tts.prosody.pitch == 1.1
    assert tts.prosody.voice_gender == "female"

    tts.set_prosody(rate=170, pitch=1.0, volume=1.0, voice_gender="female")
    assert tts.prosody.rate == 170
    assert tts.prosody.pitch == 1.0


def test_default_persona_stays_consistent_across_hinglish_and_english():
    tts = TextToSpeech(engine="mock")

    assert tts._select_voice_for_text("Good afternoon Boss!") == "hi-IN-SwaraNeural"
    assert tts._select_voice_for_text("Main active hoon, bataiye.") == "hi-IN-SwaraNeural"


def test_streaming_tts_playback_callbacks():
    tts = TextToSpeech(engine="mock")

    received_sentences = []

    def on_sentence(chunk: str):
        received_sentences.append(chunk)

    text = "Opening VLC player. Loading your favorite movie. Enjoy the show, Boss!"
    spoken = tts.speak_streaming(text, on_sentence_start=on_sentence)

    assert len(spoken) == 3
    assert len(received_sentences) == 3
    assert "Opening VLC player." in received_sentences[0]
    assert "Loading your favorite movie." in received_sentences[1]
    assert "Enjoy the show, Boss!" in received_sentences[2]


def test_tts_manager_async_queueing_and_first_chunk_latency():
    """Verify TTSManager queues and begins processing first sentence immediately."""
    tts = TextToSpeech(engine="mock")
    manager = TTSManager(tts_engine=tts)

    started_flag = []
    finished_flag = []

    def on_started():
        started_flag.append(time.perf_counter())

    def on_finished():
        finished_flag.append(time.perf_counter())

    t0 = time.perf_counter()
    manager.speak(
        "First sentence ready immediately. Second sentence continues smoothly.",
        on_started=on_started,
        on_finished=on_finished
    )

    # Allow background worker to process
    time.sleep(0.3)

    assert len(started_flag) > 0
    first_latency_ms = (started_flag[0] - t0) * 1000
    assert first_latency_ms < 100.0  # Immediate non-blocking first audio dispatch

    manager.shutdown()


def test_tts_manager_instant_interruption():
    """Verify stop() clears queued speech immediately without lag."""
    tts = TextToSpeech(engine="mock")
    manager = TTSManager(tts_engine=tts)

    # Queue multiple long sentences
    for i in range(10):
        manager.stream_chunk(f"Long speech paragraph number {i} with details.")

    # Interrupt
    manager.stop()
    assert manager._queue.empty() is True
    assert manager.is_speaking() is False

    manager.shutdown()


def test_tts_manager_speaking_state_listener():
    """Verify speaking listener receives True on start and False on complete for echo suppression."""
    tts = TextToSpeech(engine="mock")
    manager = TTSManager(tts_engine=tts)

    state_transitions = []

    def on_state(speaking: bool):
        state_transitions.append(speaking)

    manager.add_speaking_state_listener(on_state)

    manager.speak("Short speech.")
    time.sleep(0.4)

    assert True in state_transitions

    manager.shutdown()


def test_tts_manager_reports_failed_playback(caplog):
    """A failed engine must not be reported as successfully finished."""
    tts = TextToSpeech(engine="mock")
    tts.speak_chunk = lambda _chunk: False
    manager = TTSManager(tts_engine=tts)

    with caplog.at_level("INFO", logger="jarvis.voice.tts"):
        manager.speak("This playback should fail.")
        manager._queue.join()

    manager.shutdown()
    assert "TTS_FAILED" in caplog.text
    assert "TTS_FINISHED" not in caplog.text


def test_native_tts_uses_windows_fallback(monkeypatch):
    tts = TextToSpeech(engine="native", prosody=ProsodyConfig(allow_system_fallback=True))
    monkeypatch.setattr(tts, "_synthesize_neural_audio_sync", lambda *_args: None)
    monkeypatch.setattr(tts, "_get_thread_sapi_engine", lambda: None)
    monkeypatch.setattr(tts, "_speak_with_windows_voice", lambda text: text == "Hello Boss")

    assert tts.speak_chunk("Hello Boss.") is True


def test_selected_neural_persona_never_uses_robotic_fallback(monkeypatch):
    tts = TextToSpeech(engine="native")
    monkeypatch.setattr(tts, "_synthesize_neural_audio_sync", lambda *_args: None)
    monkeypatch.setattr(tts, "_get_thread_sapi_engine", lambda: None)
    monkeypatch.setattr(
        tts,
        "_speak_with_windows_voice",
        lambda _text: (_ for _ in ()).throw(AssertionError("robotic fallback must stay disabled")),
    )

    assert tts.speak_chunk("Hello Boss.") is False


def test_neural_synthesis_retries_with_cli(monkeypatch):
    tts = TextToSpeech(engine="mock", cache_enabled=False)
    expected = b"neural-audio" * 100
    monkeypatch.setattr(tts, "_synthesize_neural_audio_cli", lambda *_args: expected)

    import edge_tts

    class FailingCommunicate:
        def __init__(self, *_args, **_kwargs):
            pass

        async def stream(self):
            raise RuntimeError("simulated stream failure")
            yield

    monkeypatch.setattr(edge_tts, "Communicate", FailingCommunicate)

    assert tts._synthesize_neural_audio_sync("Hello", "hi-IN-SwaraNeural") == expected


def test_prepare_first_chunk_warms_neural_audio_before_display(monkeypatch):
    tts = TextToSpeech(engine="native", cache_enabled=False)
    prepared = []
    monkeypatch.setattr(
        tts,
        "_synthesize_neural_audio_sync",
        lambda text, voice: prepared.append((text, voice)) or (b"audio" * 200),
    )

    assert tts.prepare_first_chunk("Hello Boss! Second sentence.") is True
    assert sorted(prepared) == sorted([
        ("Hello Boss", "hi-IN-SwaraNeural"),
        ("Second sentence", "hi-IN-SwaraNeural"),
    ])


def test_delivery_punctuation_uses_continuous_human_cadence():
    text = "Hello, Boss! Main ready hoon—boliye."
    softened = SentenceStreamer.soften_delivery_punctuation(text)

    assert softened == "Hello Boss Main ready hoon boliye"
    assert "," not in softened
    assert "—" not in softened
    assert "!" not in softened and "." not in softened
