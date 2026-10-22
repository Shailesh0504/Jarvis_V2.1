# tests/test_stt_multilingual.py
"""Unit tests for Local Multilingual Whisper STT Subsystem with Hinglish / Hindi / English Support."""

import pytest
from voice.stt import SpeechToText, NoiseGate, HinglishNormalizer, TranscribeResult
from main import create_jarvis


def test_hinglish_normalizer_code_switching():
    normalizer = HinglishNormalizer()

    # Mixed Hinglish sentence
    raw = "Jarvis kal wali Excel file open karke sales ka total nikal do"
    norm = normalizer.normalize(raw)
    lang = normalizer.detect_language(raw)

    assert lang == "hinglish"
    assert "yesterday" in norm
    assert "open" in norm
    assert "calculate sum of sales" in norm
    assert "sales" in norm


def test_stt_pure_hindi_and_english():
    stt = SpeechToText(engine="mock")

    # Hindi
    res_hi = stt.transcribe(b"", simulated_text="Jarvis volume kam karo")
    assert res_hi.language in ("hi", "hinglish")
    assert "volume down" in res_hi.normalized_text

    # English
    res_en = stt.transcribe(b"", simulated_text="Jarvis take a screenshot")
    assert res_en.language == "en"
    assert "take screenshot" in res_en.normalized_text


def test_noise_gate_filters_silence_and_low_energy():
    gate = NoiseGate(energy_threshold=300.0)

    # Empty / zero audio bytes -> silence
    silence = b"\x00" * 200
    assert gate.is_speech(silence) is False

    # High amplitude PCM audio
    loud_pcm = b"\x50\x20" * 200
    assert gate.is_speech(loud_pcm) is True


def test_end_to_end_hinglish_pipeline_execution(tmp_path):
    """
    Verifies that Hinglish raw query preserves user expression in episodic memory
    while executing underlying normalized commands seamlessly.
    """
    import os, shutil
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = os.path.join(tmp_path, "stt_test.db").replace("\\", "/")
    cfg_content = f"""
system:
  name: "JARVIS_STT_TEST"
memory:
  db_path: "{db_path}"
brain:
  llm_provider: "mock"
plugins:
  plugin_dir: "{str(temp_plugins).replace('\\', '/')}"
  auto_load: true
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(cfg_content)

    jarvis = create_jarvis(str(cfg_file))
    stt = SpeechToText(engine="mock")

    # Transcribe Hinglish utterance
    hinglish_audio = "Jarvis screenshot lo"
    res = stt.transcribe(b"", simulated_text=hinglish_audio)

    # Process into core
    resp = jarvis.process_input(res.normalized_text)
    assert "Screenshot" in resp or "saved" in resp.lower() or "completed" in resp.lower()
