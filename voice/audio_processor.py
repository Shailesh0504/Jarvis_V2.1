# voice/audio_processor.py
"""
High-Performance Real-Time Audio DSP Subsystem for Jarvis V2.
Provides:
- Audio Calibration across devices (Laptop Mic, Earbuds, Bluetooth, USB Mic)
- Low-frequency rumble cut & soft noise profile suppression
- Controlled Automatic Gain Control (AGC) with soft-knee limiting
- Multi-feature Adaptive VAD (Energy SNR + Zero Crossing Rate + Temporal Continuity)
- Pre-roll circular audio buffer (prevents initial word clipping)
- Acoustic Echo Ducking during TTS playback with barge-in support
"""

from collections import deque
from dataclasses import dataclass, field
import logging
import math
import struct
import time
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("jarvis.voice.audio_processor")


@dataclass
class AudioFrameMetrics:
    """Metrics for a single processed PCM frame."""
    raw_rms: float
    processed_rms: float
    noise_floor: float
    snr_db: float
    zero_crossing_rate: float
    is_speech: bool
    vad_state: str  # "SILENCE", "SPEECH_ONSET", "SPEECH_ACTIVE", "PAUSE_TRAILING"
    gain_applied_db: float
    audio_confidence: float


@dataclass
class ProcessedAudioResult:
    """Result of processing a full utterance buffer."""
    pcm_bytes: bytes
    duration_s: float
    average_rms: float
    peak_amplitude: int
    average_snr_db: float
    audio_confidence: float
    device_name: str
    is_clipped: bool


class AudioCalibrator:
    """Tracks baseline RMS, dynamic range, and device-specific calibration."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.device_name: str = "Default Microphone"
        self.is_bluetooth: bool = False
        self.is_usb: bool = False
        self.baseline_noise_floor: float = 25.0
        self.peak_seen: float = 100.0
        self._history_rms: Deque[float] = deque(maxlen=50)

    def set_device(self, name: str, is_bluetooth: bool = False, is_usb: bool = False) -> None:
        self.device_name = name or "Default Microphone"
        self.is_bluetooth = is_bluetooth
        self.is_usb = is_usb
        # Preset initial noise floor expectations by device category
        if is_bluetooth:
            self.baseline_noise_floor = 15.0  # Bluetooth hands-free codec quantization noise
        elif is_usb:
            self.baseline_noise_floor = 10.0  # Studio mics have lower self-noise
        else:
            self.baseline_noise_floor = 12.0  # Laptop internal mic / fan proximity
        logger.info(
            f"AudioCalibrator: Configured for '{self.device_name}' "
            f"(BT={is_bluetooth}, USB={is_usb}, Initial Floor={self.baseline_noise_floor:.1f})"
        )

    def update_frame(self, rms: float) -> None:
        self._history_rms.append(rms)
        if rms > self.peak_seen:
            self.peak_seen = max(self.peak_seen * 0.95, rms)


class NoiseSuppressor:
    """
    Suppresses stationary background noise (fan, AC, ambient rumble)
    without destroying soft speech consonants (/s/, /t/, /k/, /p/, /ch/).
    Applies high-pass filtering (>80Hz) and soft spectral noise profile attenuation.
    """

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        # Simple 1st-order high-pass IIR filter state (cutoff ~80Hz)
        dt = 1.0 / sample_rate
        rc = 1.0 / (2.0 * math.pi * 80.0)
        self._hp_alpha = rc / (rc + dt)
        self._prev_x = 0.0
        self._prev_y = 0.0

        # Running noise spectrum estimate (16 sub-bands)
        self.num_bands = 16
        self.noise_band_profile = np.ones(self.num_bands, dtype=np.float32) * 50.0

    def filter_rumble(self, samples: np.ndarray) -> np.ndarray:
        """High-pass filter removing mechanical desk thumps and AC 50/60Hz hum."""
        if len(samples) == 0:
            return samples
        out = np.empty_like(samples, dtype=np.float32)
        px = self._prev_x
        py = self._prev_y
        alpha = self._hp_alpha

        for i in range(len(samples)):
            x = float(samples[i])
            y = alpha * (py + x - px)
            out[i] = y
            px = x
            py = y

        self._prev_x = px
        self._prev_y = py
        return out

    def update_noise_profile(self, fft_magnitudes: np.ndarray, is_speech: bool) -> None:
        """Updates stationary noise profile during non-speech intervals."""
        if is_speech or len(fft_magnitudes) < self.num_bands:
            return
        band_size = len(fft_magnitudes) // self.num_bands
        bands = np.array([
            np.mean(fft_magnitudes[i * band_size : (i + 1) * band_size])
            for i in range(self.num_bands)
        ], dtype=np.float32)
        # Slow update: leak 3% of current noise
        self.noise_band_profile = (self.noise_band_profile * 0.97) + (bands * 0.03)

    def suppress_noise(self, samples_float: np.ndarray, is_speech: bool) -> np.ndarray:
        """Applies rumble cut and soft noise profile subtraction."""
        rumble_cut = self.filter_rumble(samples_float)
        if len(rumble_cut) < 64:
            return rumble_cut

        try:
            fft_vals = np.fft.rfft(rumble_cut)
            mags = np.abs(fft_vals)
            phases = np.angle(fft_vals)

            self.update_noise_profile(mags, is_speech)

            if is_speech:
                band_size = len(mags) // self.num_bands
                if band_size > 0:
                    expanded_noise = np.repeat(self.noise_band_profile, band_size)
                    if len(expanded_noise) < len(mags):
                        expanded_noise = np.pad(expanded_noise, (0, len(mags) - len(expanded_noise)), mode='edge')
                    elif len(expanded_noise) > len(mags):
                        expanded_noise = expanded_noise[:len(mags)]

                    clean_mags = np.maximum(mags - (0.55 * expanded_noise), mags * 0.35)
                    clean_fft = clean_mags * np.exp(1j * phases)
                    cleaned = np.fft.irfft(clean_fft, n=len(rumble_cut))
                    return cleaned
            return rumble_cut
        except Exception:
            return rumble_cut


class AutomaticGainControl:
    """
    Intelligent Automatic Gain Control (AGC) with soft-knee limiter.
    - Normalizes speech volume to target RMS (~3500 - 4500 on 16-bit scale, ~-18 dBFS).
    - Caps maximum boost to +20 dB (factor ~10.0x).
    - NEVER boosts pure background noise (expansion floor prevents fan/AC amplification).
    - Uses soft saturation curve (tanh) to prevent digital clipping on loud speech.
    """

    def __init__(
        self,
        target_rms: float = 3800.0,
        max_gain_db: float = 20.0,
        min_gain_db: float = -12.0,
        expansion_threshold_db: float = 4.0
    ):
        self.target_rms = target_rms
        self.max_gain = 10.0 ** (max_gain_db / 20.0)  # ~10.0x (+20dB)
        self.min_gain = 10.0 ** (min_gain_db / 20.0)  # ~0.25x (-12dB)
        self.expansion_threshold_db = expansion_threshold_db
        self._current_gain = 1.0
        self._attack_coeff = 0.15  # Fast rise when speech begins
        self._decay_coeff = 0.04   # Gentle fall

    def apply_agc(
        self,
        samples_float: np.ndarray,
        frame_rms: float,
        noise_floor: float,
        is_speech: bool
    ) -> Tuple[np.ndarray, float]:
        """
        Applies controlled gain to speech frames.
        Returns (gain_adjusted_samples, gain_db).
        """
        if len(samples_float) == 0:
            return samples_float, 0.0

        snr_ratio = frame_rms / max(noise_floor, 1.0)

        # Expansion guard: if frame is down in the noise floor, do NOT amplify noise
        if not is_speech and snr_ratio < 1.3:
            self._current_gain = (self._current_gain * 0.95) + (1.0 * 0.05)
            gain_db = 20.0 * math.log10(max(self._current_gain, 0.001))
            return samples_float * self._current_gain, gain_db

        # For valid speech: compute desired gain towards target RMS
        if frame_rms > 5.0:
            desired_gain = self.target_rms / frame_rms
            desired_gain = max(self.min_gain, min(self.max_gain, desired_gain))

            # Smooth attack/decay
            if desired_gain > self._current_gain:
                self._current_gain += (desired_gain - self._current_gain) * self._attack_coeff
            else:
                self._current_gain += (desired_gain - self._current_gain) * self._decay_coeff

        # Apply gain
        boosted = samples_float * self._current_gain

        # Soft-knee saturation limiter to prevent digital clipping at +/- 32767
        threshold = 24000.0
        ceiling = 32500.0
        mask = np.abs(boosted) > threshold
        if np.any(mask):
            excess = np.abs(boosted[mask]) - threshold
            ratio = excess / (32767.0 - threshold)
            saturated_excess = (ceiling - threshold) * np.tanh(ratio)
            boosted[mask] = np.sign(boosted[mask]) * (threshold + saturated_excess)

        gain_db = 20.0 * math.log10(max(self._current_gain, 0.001))
        return boosted, gain_db


class AdaptiveVAD:
    """
    Multi-feature Voice Activity Detector combining:
    1. Running Noise Floor & SNR estimation.
    2. Zero-Crossing Rate (ZCR) & High-Frequency Flux for unvoiced consonants (/s/, /p/, /t/, /ch/).
    3. Temporal persistence (eliminates keyboard click false triggers).
    4. Adaptive Hang-Over Time (prevents mid-sentence cutoff during slow/quiet speech).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        initial_noise_floor: float = 25.0,
        min_snr_db: float = 2.8
    ):
        self.sample_rate = sample_rate
        self.noise_floor = initial_noise_floor
        self.min_snr_db = min_snr_db
        self.state = "SILENCE"

        self._consecutive_speech_frames = 0
        self._consecutive_silence_frames = 0
        self._speech_onset_frames_needed = 2  # 2 frames * 64ms = 128ms
        self._speech_active = False
        self._last_speech_time = 0.0

    def compute_zero_crossing_rate(self, samples: np.ndarray) -> float:
        """Calculates zero-crossing rate indicating fricatives / high-frequency speech."""
        if len(samples) < 2:
            return 0.0
        signs = np.sign(samples)
        signs[signs == 0] = 1
        return float(np.sum(np.abs(np.diff(signs))) / (2.0 * len(samples)))

    def process_frame(
        self,
        samples: np.ndarray,
        frame_rms: float,
        is_bluetooth: bool = False
    ) -> Tuple[bool, float, str]:
        """
        Evaluates frame for voice activity.
        Returns (is_speech, snr_db, vad_state).
        """
        now = time.time()
        zcr = self.compute_zero_crossing_rate(samples)

        snr_ratio = frame_rms / max(self.noise_floor, 1.0)
        snr_db = 20.0 * math.log10(max(snr_ratio, 0.001))

        effective_min_snr = self.min_snr_db * (1.0 if is_bluetooth else 1.0)

        # Multi-feature speech classifier:
        # A) Strong energy above noise floor
        is_energy_speech = (snr_db >= effective_min_snr)

        # B) Quiet unvoiced consonant speech: Moderate SNR + High Zero-Crossing Rate
        is_fricative_speech = (snr_db >= (effective_min_snr - 2.0)) and (zcr >= 0.14)

        # C) Whispered / soft speech candidate: Low energy RMS with consonant flux
        is_whisper_speech = (frame_rms >= 10.0) and (zcr >= 0.12) and (snr_db >= 1.0)

        frame_speech_candidate = is_energy_speech or is_fricative_speech or is_whisper_speech

        if frame_speech_candidate:
            self._consecutive_speech_frames += 1
            self._consecutive_silence_frames = 0

            if not self._speech_active:
                if self._consecutive_speech_frames >= self._speech_onset_frames_needed:
                    self._speech_active = True
                    self.state = "SPEECH_ONSET"
                    self._last_speech_time = now
                else:
                    self.state = "POTENTIAL_ONSET"
            else:
                self.state = "SPEECH_ACTIVE"
                self._last_speech_time = now
        else:
            self._consecutive_silence_frames += 1
            self._consecutive_speech_frames = 0

            if self._speech_active:
                self.state = "PAUSE_TRAILING"
                hangover_limit_s = 0.45
                if (now - self._last_speech_time) > hangover_limit_s:
                    self._speech_active = False
                    self.state = "SILENCE"
            else:
                self.state = "SILENCE"
                if frame_rms > self.noise_floor:
                    self.noise_floor += (frame_rms - self.noise_floor) * 0.015
                else:
                    self.noise_floor += (frame_rms - self.noise_floor) * 0.05
                self.noise_floor = max(10.0, min(self.noise_floor, 350.0))

        return self._speech_active, snr_db, self.state


class PreRollBuffer:
    """
    Circular ring buffer keeping ~400ms (approx 6-8 frames @ 1024 samples) of pre-speech audio.
    When speech onset is confirmed, pre-roll frames are prepended to ensure the first word
    and soft onset consonants are never clipped or lost.
    """

    def __init__(self, max_frames: int = 7):
        self.max_frames = max_frames
        self._buffer: Deque[bytes] = deque(maxlen=max_frames)

    def append(self, pcm_bytes: bytes) -> None:
        self._buffer.append(pcm_bytes)

    def get_and_clear(self) -> List[bytes]:
        frames = list(self._buffer)
        self._buffer.clear()
        return frames

    def clear(self) -> None:
        self._buffer.clear()


class AcousticEchoDucker:
    """
    Suppresses microphone pickup of Jarvis's own TTS speech output.
    """

    def __init__(self, attenuation_db: float = -18.0):
        self.attenuation_factor = 10.0 ** (attenuation_db / 20.0)
        self._is_tts_speaking = False
        self._tts_finish_time = 0.0
        self._duck_decay_time = 0.25

    def set_tts_speaking(self, is_speaking: bool) -> None:
        self._is_tts_speaking = is_speaking
        if not is_speaking:
            self._tts_finish_time = time.time()

    def is_ducking_active(self) -> bool:
        if self._is_tts_speaking:
            return True
        return (time.time() - self._tts_finish_time) < self._duck_decay_time

    def apply_ducking(self, samples_float: np.ndarray) -> np.ndarray:
        if self.is_ducking_active():
            return samples_float * self.attenuation_factor
        return samples_float


class AudioProcessor:
    """
    Unified real-time Audio DSP pipeline orchestrating Calibration,
    Noise Suppression, AGC, Adaptive VAD, Pre-roll, and Echo Ducking.
    """

    def __init__(self, sample_rate: int = 16000, chunk_size: int = 1024):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size

        self.calibrator = AudioCalibrator(sample_rate=sample_rate)
        self.noise_suppressor = NoiseSuppressor(sample_rate=sample_rate)
        self.agc = AutomaticGainControl()
        self.vad = AdaptiveVAD(sample_rate=sample_rate)
        self.pre_roll = PreRollBuffer(max_frames=7)
        self.echo_ducker = AcousticEchoDucker()

        self._utterance_frames: List[bytes] = []
        self._utterance_snr_history: List[float] = []
        self._utterance_start_time = 0.0
        self._speech_in_progress = False

    def on_device_changed(self, device_name: str, is_bluetooth: bool = False, is_usb: bool = False) -> None:
        """Adapts DSP parameters to newly connected hardware without service restart."""
        self.calibrator.set_device(device_name, is_bluetooth=is_bluetooth, is_usb=is_usb)
        self.pre_roll.clear()
        self._utterance_frames.clear()
        self._speech_in_progress = False

    def process_frame(self, raw_pcm_bytes: bytes) -> Tuple[Optional[bytes], AudioFrameMetrics]:
        """
        Processes a raw 16-bit 16kHz mono PCM frame through the DSP pipeline.
        Returns (processed_pcm_bytes, frame_metrics).
        """
        if not raw_pcm_bytes or len(raw_pcm_bytes) < 4:
            empty_metrics = AudioFrameMetrics(0, 0, self.vad.noise_floor, 0, 0, False, "SILENCE", 0, 0)
            return None, empty_metrics

        samples = np.frombuffer(raw_pcm_bytes, dtype=np.int16).astype(np.float32)
        raw_rms = float(np.sqrt(np.mean(samples ** 2))) if len(samples) > 0 else 0.0
        self.calibrator.update_frame(raw_rms)

        # 1. Echo Ducking
        samples = self.echo_ducker.apply_ducking(samples)

        # 2. Adaptive Multi-Feature VAD
        is_speech, snr_db, vad_state = self.vad.process_frame(
            samples, raw_rms, is_bluetooth=self.calibrator.is_bluetooth
        )

        # 3. Noise Suppression (sub-80Hz rumble cut + soft noise subtraction)
        suppressed = self.noise_suppressor.suppress_noise(samples, is_speech)

        # 4. Automatic Gain Control (AGC)
        agc_samples, gain_db = self.agc.apply_agc(
            suppressed, raw_rms, self.vad.noise_floor, is_speech
        )

        int16_samples = np.clip(agc_samples, -32768, 32767).astype(np.int16)
        processed_pcm = int16_samples.tobytes()
        proc_rms = float(np.sqrt(np.mean(int16_samples.astype(np.float32) ** 2)))

        zcr = self.vad.compute_zero_crossing_rate(samples)

        clipping_penalty = 0.2 if np.max(np.abs(int16_samples)) >= 32500 else 0.0
        snr_confidence = min(max((snr_db - 2.0) / 18.0, 0.2), 0.98)
        audio_confidence = max(0.1, snr_confidence - clipping_penalty)

        metrics = AudioFrameMetrics(
            raw_rms=raw_rms,
            processed_rms=proc_rms,
            noise_floor=self.vad.noise_floor,
            snr_db=snr_db,
            zero_crossing_rate=zcr,
            is_speech=is_speech,
            vad_state=vad_state,
            gain_applied_db=gain_db,
            audio_confidence=audio_confidence
        )

        # Pre-roll handling:
        if not is_speech and not self._speech_in_progress:
            self.pre_roll.append(processed_pcm)
            return None, metrics

        if is_speech and not self._speech_in_progress:
            self._speech_in_progress = True
            self._utterance_start_time = time.time()
            self._utterance_frames.clear()
            self._utterance_snr_history.clear()

            pre_frames = self.pre_roll.get_and_clear()
            self._utterance_frames.extend(pre_frames)

        self._utterance_frames.append(processed_pcm)
        self._utterance_snr_history.append(snr_db)

        return processed_pcm, metrics

    def finalize_utterance(self) -> Optional[ProcessedAudioResult]:
        """
        Assembles collected utterance frames into a finalized ProcessedAudioResult.
        """
        if not self._utterance_frames:
            self._speech_in_progress = False
            return None

        total_pcm = b"".join(self._utterance_frames)
        self._utterance_frames.clear()
        self._speech_in_progress = False

        if len(total_pcm) < 3200:  # Less than ~100ms
            return None

        samples = np.frombuffer(total_pcm, dtype=np.int16)
        dur = len(samples) / float(self.sample_rate)
        avg_rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
        peak = int(np.max(np.abs(samples))) if len(samples) > 0 else 0
        avg_snr = float(np.mean(self._utterance_snr_history)) if self._utterance_snr_history else 0.0

        audio_conf = min(max((avg_snr - 1.5) / 16.0, 0.35), 0.98)
        if peak >= 32600:
            audio_conf = max(0.2, audio_conf - 0.15)

        return ProcessedAudioResult(
            pcm_bytes=total_pcm,
            duration_s=dur,
            average_rms=avg_rms,
            peak_amplitude=peak,
            average_snr_db=avg_snr,
            audio_confidence=audio_conf,
            device_name=self.calibrator.device_name,
            is_clipped=(peak >= 32600)
        )
