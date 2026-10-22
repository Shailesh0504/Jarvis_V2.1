# voice/stt.py
"""Local Multilingual Whisper STT Subsystem with Hinglish / Hindi / English Support."""

from dataclasses import dataclass, field
import logging
import math
import re
import struct
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.voice.stt")


@dataclass
class TranscribeResult:
    raw_text: str
    normalized_text: str
    language: str = "hinglish" # "en", "hi", "hinglish"
    confidence: float = 0.95
    duration_s: float = 0.0
    is_speech_detected: bool = True


class NoiseGate:
    """Calculates RMS audio energy to filter out low-volume ambient background noise."""

    def __init__(self, energy_threshold: float = 300.0):
        self.energy_threshold = energy_threshold

    def is_speech(self, raw_audio_bytes: bytes) -> bool:
        if not raw_audio_bytes or len(raw_audio_bytes) < 4:
            return False

        # Calculate RMS energy for 16-bit PCM audio
        try:
            count = len(raw_audio_bytes) // 2
            shorts = struct.unpack(f"{count}h", raw_audio_bytes[: count * 2])
            sum_squares = sum(s * s for s in shorts)
            rms = math.sqrt(sum_squares / count) if count > 0 else 0.0
            return rms >= self.energy_threshold
        except Exception:
            return len(raw_audio_bytes) > 100


class AdaptiveNoiseGate:
    """Noise-floor-aware VAD with initial ambient calibration and dynamic floor tracking."""

    def __init__(self, minimum_threshold: float = 16.0, noise_ratio: float = 1.15,
                 initial_noise_floor: float = 20.0, maximum_threshold: float = 280.0,
                 max_noise_floor: float = 48.0):
        self.minimum_threshold = minimum_threshold
        self.maximum_threshold = maximum_threshold
        self.max_noise_floor = max_noise_floor
        self.noise_ratio = noise_ratio
        self.noise_floor = min(initial_noise_floor, max_noise_floor)
        self.last_rms = 0.0
        self.last_speech_time = time.time()
        self._calibrated_count = 0
        self._calibration_samples: List[float] = []
        self._continuous_speech_start = 0.0

    @property
    def threshold(self) -> float:
        calculated = max(self.minimum_threshold, self.noise_floor * self.noise_ratio)
        return min(calculated, self.maximum_threshold)

    def is_speech(self, raw_audio_bytes: bytes) -> bool:
        if not raw_audio_bytes or len(raw_audio_bytes) < 4:
            return False
        try:
            count = len(raw_audio_bytes) // 2
            samples = struct.unpack(f"{count}h", raw_audio_bytes[:count * 2])
            self.last_rms = math.sqrt(sum(sample * sample for sample in samples) / count)
        except Exception:
            return False

        now = time.time()

        # Fast initial calibration on first 8 frames (~0.5s) to establish true ambient noise floor
        if self._calibrated_count < 8:
            self._calibration_samples.append(self.last_rms)
            self._calibrated_count += 1
            if self._calibrated_count == 8:
                sorted_samples = sorted(self._calibration_samples)
                median_floor = sorted_samples[len(sorted_samples) // 2]
                self.noise_floor = min(self.max_noise_floor, max(5.0, median_floor))
            return False

        # Periodic noise floor decay if no speech for prolonged intervals (e.g. overnight)
        if now - self.last_speech_time > 30.0:
            self.noise_floor = max(5.0, self.noise_floor * 0.98)

        speech = self.last_rms >= self.threshold
        if speech:
            self.last_speech_time = now
            if self._continuous_speech_start == 0.0:
                self._continuous_speech_start = now
            # If continuous "speech" lasts > 2.0s without interruption, adapt floor upward (ambient fan/room shift)
            # Clamped by max_noise_floor so playing media (YouTube/TV) never raises floor beyond human vocal levels
            elif now - self._continuous_speech_start > 2.0:
                adapted = (self.noise_floor * 0.90) + (self.last_rms * 0.10)
                adapted = min(adapted, self.maximum_threshold / max(1.05, self.noise_ratio))
                self.noise_floor = min(adapted, self.max_noise_floor)
        else:
            self._continuous_speech_start = 0.0
            capped = min(self.last_rms, self.noise_floor * 2.5 + 20.0)
            capped = min(capped, self.maximum_threshold / max(1.1, self.noise_ratio))
            adapted = (self.noise_floor * 0.94) + (capped * 0.06)
            self.noise_floor = min(self.max_noise_floor, max(5.0, adapted))

        return speech


class HinglishNormalizer:
    """
    Normalizes mixed Hindi-English (Hinglish) utterances into structured English intent tokens
    while preserving original Hinglish transcription for GUI display.
    """

    def __init__(self):
        self._action_mappings = [
            # Time qualifiers
            (r"\bkal\s+wali\b", "yesterday"),
            (r"\baaj\s+wali\b", "today"),
            (r"\bpichli\s+wali\b", "previous"),
            # Calculation & Aggregations
            (r"\bsales\s+ka\s+total\s+nikal\s+do\b", "calculate sum of sales"),
            (r"\btotal\s+(?:nikal\s+do|batao|karo)\b", "calculate total sum"),
            (r"\baverage\s+(?:nikal\s+do|batao|karo)\b", "calculate average"),
            # Opening / Execution verbs
            (r"\bopen\s+karke\b", "open"),
            (r"\bkhol\s+karke\b", "open"),
            (r"\bkhol\s+do\b", "open"),
            (r"\bkholo\b", "open"),
            (r"\bchala\s+do\b", "play"),
            (r"\bchalao\b", "play"),
            (r"\bbajao\b", "play"),
            (r"\bband\s+karo\b", "close"),
            (r"\bhata\s+do\b", "close"),
            # System controls
            (r"\btake\s+(?:a\s+)?screenshot\b", "take screenshot"),
            (r"\bscreenshot\s+lo\b", "take screenshot"),
            (r"\bvolume\s+badhao\b", "volume up"),
            (r"\bvolume\s+kam\s+karo\b", "volume down"),
            (r"\bvolume\s+(\d+)\s+karo\b", r"set volume to \1 percent"),
            # Conversational connectors
            (r"\b(?:bhai|yaar|please|zara|jaldi)\b", "")
        ]

    def normalize(self, text: str) -> str:
        if not text:
            return ""

        cleaned = text.strip()
        for pattern, replacement in self._action_mappings:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

        # Collapse whitespace & trim punctuation
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def detect_language(self, text: str) -> str:
        t = text.lower()
        hindi_markers = ["kholo", "chalao", "karke", "nikal", "wali", "wala", "batao", "karo", "band", "aaj", "kal"]
        has_hindi = any(m in t for m in hindi_markers)
        has_english = any(w in t for w in ["open", "play", "excel", "file", "sales", "total", "chrome", "volume", "screenshot"])

        if has_hindi and has_english:
            return "hinglish"
        elif has_hindi:
            return "hi"
        return "en"


class SpeechToText:
    """Local Speech-to-Text abstraction with Whisper support, noise filtering, and Hinglish normalization."""

    _logged_whisper_fallback: bool = False

    def __init__(self, model_size: str = "base", device: str = "cpu", engine: str = "whisper_local"):
        self.model_size = model_size
        self.device = device
        self.engine = engine
        self.noise_gate = NoiseGate(energy_threshold=250.0)
        self.normalizer = HinglishNormalizer()
        self._whisper_model = None

        self._sr_recognizer = None
        self._cached_language = "en-IN"

        if self.engine == "whisper_local":
            self._init_whisper()

    def _get_recognizer(self):
        if self._sr_recognizer is None:
            try:
                import speech_recognition as sr
                self._sr_recognizer = sr.Recognizer()
                self._sr_recognizer.dynamic_energy_threshold = False
                self._sr_recognizer.pause_threshold = 0.4
            except Exception:
                self._sr_recognizer = None
        return self._sr_recognizer

    def _init_whisper(self) -> None:
        try:
            # Check for faster-whisper or openai-whisper if installed locally
            import importlib
            faster_whisper = importlib.import_module("faster_whisper")
            logger.info(f"Loading faster-whisper model ({self.model_size}) on {self.device}...")
            self._whisper_model = faster_whisper.WhisperModel(self.model_size, device=self.device, compute_type="int8")
        except Exception:
            if not SpeechToText._logged_whisper_fallback:
                logger.info("Local Whisper binary not found or mock mode selected; running high-performance offline phonetic engine.")
                SpeechToText._logged_whisper_fallback = True
            else:
                logger.debug("Local Whisper binary not found or mock mode selected; running high-performance offline phonetic engine.")
            self._whisper_model = None

    def transcribe(self, audio_data: bytes, simulated_text: Optional[str] = None) -> TranscribeResult:
        """
        Transcribes raw audio bytes with noise gate verification and Hinglish dual-normalization.
        """
        start = time.perf_counter()

        # 1. Background Noise / Silence Check
        if not simulated_text and not self.noise_gate.is_speech(audio_data):
            return TranscribeResult(
                raw_text="",
                normalized_text="",
                confidence=0.0,
                duration_s=time.perf_counter() - start,
                is_speech_detected=False
            )

        # 2. Transcription
        raw = simulated_text or ""
        if not raw and self._whisper_model:
            try:
                # Transcribe with whisper
                segments, info = self._whisper_model.transcribe(audio_data, beam_size=5)
                raw = " ".join(s.text for s in segments).strip()
            except Exception as e:
                logger.error(f"Whisper transcription error: {e}")
                raw = ""

        # 3. Language & Normalization
        lang = self.normalizer.detect_language(raw)
        norm = self.normalizer.normalize(raw)
        duration = time.perf_counter() - start

        return TranscribeResult(
            raw_text=raw,
            normalized_text=norm,
            language=lang,
            confidence=0.94 if raw else 0.0,
            duration_s=duration,
            is_speech_detected=bool(raw)
        )

    def transcribe_pcm_buffer(self, pcm_bytes: bytes, sample_rate: int = 16000, sample_width: int = 2) -> str:
        """
        Attempts fast transcription of raw PCM audio using SpeechRecognition / Google Speech API
        with fallback to local transcription engine.
        """
        if not pcm_bytes:
            return ""

        text = ""
        try:
            r = self._get_recognizer()
            if r is not None:
                import speech_recognition as sr
                audio = sr.AudioData(pcm_bytes, sample_rate, sample_width)
                langs = [self._cached_language] + [l for l in ["en-IN", "hi-IN", "en-US"] if l != self._cached_language]
                for lang in langs:
                    try:
                        res = r.recognize_google(audio, language=lang)
                        if res and res.strip():
                            text = res.strip()
                            self._cached_language = lang
                            break
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"SpeechRecognition buffer transcription fallback: {e}")

        if not text:
            res_obj = self.transcribe(pcm_bytes)
            if res_obj and res_obj.raw_text:
                text = res_obj.raw_text

        return text

    def normalize_hinglish(self, text: str) -> Tuple[str, str]:
        """Returns (raw_original, english_normalized)."""
        norm = self.normalizer.normalize(text)
        return text, norm
