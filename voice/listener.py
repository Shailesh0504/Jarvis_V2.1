# voice/listener.py
"""
Voice Subsystem Continuous Listener and Voice State Controller.
Manages persistent audio stream monitoring, wake-word gating, active listening modes,
echo/self-voice suppression, energy-based VAD, and state transitions.
"""

from collections import deque
from enum import Enum
import logging
import math
import struct
import threading
import time
from typing import Any, Callable, Deque, Dict, List, Optional, Set

from .audio_processor import AudioFrameMetrics, AudioProcessor, ProcessedAudioResult
from .device_manager import AudioDeviceManager, AudioDeviceInfo
from .stt import AdaptiveNoiseGate, SpeechToText, TranscribeResult
from .wake_word import WakeWordDetector, WakeWordMatchResult, WakeWordState

logger = logging.getLogger("jarvis.voice.listener")


class VoiceMode(str, Enum):
    STANDBY = "standby"   # IDLE mode: Only wake word triggers processing; background speech is discarded
    ACTIVE = "active"     # LISTENING mode: Explicit Listen button or active continuous session


class PersistentAudioStream:
    """
    Continuous, low-latency audio capture stream backend.
    Maintains a single open hardware handle (WASAPI / PyAudio / SoundDevice) to eliminate
    Windows taskbar microphone indicator flickering and device reinitialization lag.
    Prioritizes Bluetooth Earbuds / Headset input devices dynamically.
    """

    _active_streams: Set['PersistentAudioStream'] = set()
    _active_streams_lock = threading.Lock()

    @classmethod
    def has_active_streams(cls) -> bool:
        """Returns True if any PersistentAudioStream is actively open and running."""
        with cls._active_streams_lock:
            return len(cls._active_streams) > 0

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        on_frame: Optional[Callable[[bytes], None]] = None,
        device: Optional[int] = None
    ):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.on_frame = on_frame
        self.device = device
        self.is_active = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._backend = "none"
        self._lock = threading.Lock()

    def start(self, device: Optional[int] = None) -> bool:
        with self._lock:
            if self.is_active:
                return True

            if device is not None:
                self.device = device
            elif self.device is None:
                adm = AudioDeviceManager()
                active_dev = adm.get_active_input_device()
                self.device = active_dev.index if active_dev else adm.get_best_sounddevice_index()

            self._stop_event.clear()
            self.is_active = True

            # 1. Try SoundDevice RawInputStream with non-blocking callback
            try:
                import sounddevice as sd
                def _sd_callback(indata, frames, time_info, status):
                    if not self._stop_event.is_set() and self.on_frame:
                        self.on_frame(bytes(indata))

                try:
                    self._sd_stream = sd.RawInputStream(
                        samplerate=self.sample_rate,
                        blocksize=self.chunk_size,
                        channels=1,
                        dtype='int16',
                        device=self.device,
                        callback=_sd_callback
                    )
                    self._sd_stream.start()
                except Exception as e_spec:
                    logger.debug(f"PersistentAudioStream: Device {self.device} failed ({e_spec}). Falling back to default mic.")
                    self.device = None
                    self._sd_stream = sd.RawInputStream(
                        samplerate=self.sample_rate,
                        blocksize=self.chunk_size,
                        channels=1,
                        dtype='int16',
                        device=None,
                        callback=_sd_callback
                    )
                    self._sd_stream.start()

                self._backend = "sounddevice_stream"
                adm = AudioDeviceManager()
                dev_info = adm.get_active_input_device() or adm.get_best_input_device()
                dev_name = dev_info.clean_name if dev_info else f"Index {self.device}"
                logger.info(f"PersistentAudioStream: Started via sounddevice using device: {dev_name} (Index: {self.device})")
                self.is_active = True
                with PersistentAudioStream._active_streams_lock:
                    PersistentAudioStream._active_streams.add(self)
                return True
            except Exception as e_sd:
                logger.debug(f"PersistentAudioStream: sounddevice stream failed ({e_sd}), trying PyAudio...")

            # 2. Try PyAudio callback stream
            try:
                import pyaudio
                pa = pyaudio.PyAudio()
                def _pa_callback(in_data, frame_count, time_info, status):
                    if not self._stop_event.is_set() and self.on_frame:
                        self.on_frame(in_data)
                    return (None, pyaudio.paContinue)

                self._pa_instance = pa
                pa_device = AudioDeviceManager().get_best_sr_device_index()
                self._pa_stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=pa_device,
                    frames_per_buffer=self.chunk_size,
                    stream_callback=_pa_callback
                )
                self._pa_stream.start_stream()
                self._backend = "pyaudio_stream"
                logger.info(f"PersistentAudioStream: Started via PyAudio callback stream (Device Index: {pa_device}).")
                self.is_active = True
                with PersistentAudioStream._active_streams_lock:
                    PersistentAudioStream._active_streams.add(self)
                return True
            except Exception as e_pa:
                logger.debug(f"PersistentAudioStream: PyAudio stream not initialized ({e_pa}). Running in manual/simulated feed mode.")
                self._backend = "simulated"
                self.is_active = True
                with PersistentAudioStream._active_streams_lock:
                    PersistentAudioStream._active_streams.add(self)
                return True

    def switch_device(self, new_device: Optional[int] = None) -> bool:
        """Dynamically switches audio capture to a new device (e.g. connected earbuds or internal mic)."""
        logger.info(f"PersistentAudioStream: Hot-switching audio device to: {new_device}...")
        self.stop()
        self.device = new_device
        return self.start(device=new_device)

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            self.is_active = False
            with PersistentAudioStream._active_streams_lock:
                PersistentAudioStream._active_streams.discard(self)

            if hasattr(self, "_sd_stream") and self._sd_stream:
                try:
                    self._sd_stream.stop()
                    self._sd_stream.close()
                except Exception:
                    pass
                self._sd_stream = None

            if hasattr(self, "_pa_stream") and self._pa_stream:
                try:
                    self._pa_stream.stop_stream()
                    self._pa_stream.close()
                except Exception:
                    pass
                self._pa_stream = None

            if hasattr(self, "_pa_instance") and self._pa_instance:
                try:
                    self._pa_instance.terminate()
                except Exception:
                    pass
                self._pa_instance = None

            logger.info("PersistentAudioStream: Audio stream closed cleanly.")


class VoiceListener(threading.Thread):
    """
    Background thread & controller monitoring audio streams with strict voice-state gating.
    Guarantees that ordinary background speech is never routed as a command when in IDLE/standby mode.
    Maintains persistent-but-lightweight stream lifecycle to avoid Windows mic indicator toggling.
    """

    def __init__(
        self,
        wake_word_detector: Optional[WakeWordDetector] = None,
        stt: Optional[SpeechToText] = None,
        on_wake_detected: Optional[Callable[[WakeWordMatchResult], None]] = None,
        on_command_captured: Optional[Callable[[str], None]] = None,
        on_state_changed: Optional[Callable[[WakeWordState], None]] = None,
        session_timeout: float = 10.0,
        enable_audio_stream: bool = False,
        barge_in_enabled: bool = False,
        on_interrupted: Optional[Callable[[str], None]] = None,
        tts_text_getter: Optional[Callable[[], str]] = None,
    ):
        super().__init__(daemon=True, name="JarvisVoiceListener")
        self.detector = wake_word_detector or WakeWordDetector()
        self.stt = stt or SpeechToText()
        self.noise_gate = AdaptiveNoiseGate(minimum_threshold=55.0, noise_ratio=2.0)
        self.on_wake_detected = on_wake_detected
        self.on_command_captured = on_command_captured
        self.on_state_changed = on_state_changed
        self.barge_in_enabled = barge_in_enabled
        self.on_interrupted = on_interrupted
        self._get_active_spoken_text = tts_text_getter

        self.session_timeout = session_timeout
        self.mode = VoiceMode.STANDBY
        self.state = WakeWordState.IDLE

        self._is_tts_speaking = False
        self._last_tts_finish_time = 0.0
        self._last_active_speech_time = 0.0

        self.is_monitoring = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # VAD & Utterance segmentation state
        self._current_utterance_frames: List[bytes] = []
        self._speech_in_progress = False
        self._last_speech_time = 0.0
        self._silence_pause_threshold = 0.42  # seconds of silence before segmenting
        self._max_utterance_duration = 12.0 # seconds max utterance length
        self._utterance_start_time = 0.0

        # Persistent stream handle
        self._enable_audio_stream = enable_audio_stream
        self._audio_stream: Optional[PersistentAudioStream] = None

        # Intelligent Audio Processor (Calibration, Noise Suppression, AGC, VAD, Pre-roll)
        self.audio_processor = AudioProcessor()
        self._last_audio_metrics: Optional[Dict[str, Any]] = None

    def set_tts_text_getter(self, getter: Callable[[], str]) -> None:
        self._get_active_spoken_text = getter

    def _is_self_voice_echo(self, text: str) -> bool:
        """Detects if microphone input is merely acoustic echo of Jarvis's own TTS output."""
        if not self._is_tts_speaking or not self._get_active_spoken_text:
            return False
        active_chunk = self._get_active_spoken_text()
        if not active_chunk or not active_chunk.strip():
            return False

        import re
        def tokenize(s: str) -> set:
            return set(re.findall(r"\b\w+\b", s.lower()))

        text_words = tokenize(text)
        if not text_words:
            return False

        interruption_keywords = {"stop", "ruk", "ruko", "chup", "shant", "cancel", "bas", "jarvis", "wait"}
        if text_words.intersection(interruption_keywords):
            return False

        spoken_words = tokenize(active_chunk)
        if not spoken_words:
            return False

        overlap = text_words.intersection(spoken_words)
        return (len(overlap) / len(text_words)) >= 0.5

    def set_tts_speaking(self, is_speaking: bool) -> None:
        """Sets the TTS playback state to prevent acoustic feedback / self-triggering."""
        with self._lock:
            self._is_tts_speaking = is_speaking
            if hasattr(self, "audio_processor") and self.audio_processor:
                self.audio_processor.echo_ducker.set_tts_speaking(is_speaking)
            if not is_speaking:
                self._last_tts_finish_time = time.time()
                # Do not transition immediately to IDLE if in ACTIVE session
                if self.mode == VoiceMode.ACTIVE:
                    self._transition_state(WakeWordState.LISTENING)
                else:
                    self._transition_state(WakeWordState.IDLE)
            else:
                # Clear any half-buffered utterance on TTS start to prevent echo contamination
                self._current_utterance_frames.clear()
                self._speech_in_progress = False
                self._transition_state(WakeWordState.RESPONDING)

    def is_suppressed(self) -> bool:
        """Checks if speech recognition should be suppressed due to active TTS or echo cooldown."""
        with self._lock:
            if self._is_tts_speaking:
                return True
            # 0.4s cooldown window after TTS finishes
            if time.time() - self._last_tts_finish_time < 0.4:
                return True
            return False

    def set_mode(self, mode: VoiceMode) -> None:
        """Switches between STANDBY (IDLE/wake-word only) and ACTIVE (direct listening)."""
        with self._lock:
            self.mode = mode
            if mode == VoiceMode.ACTIVE:
                self._last_active_speech_time = time.time()
                self._transition_state(WakeWordState.LISTENING)
                try:
                    from .media_ducker import MediaDucker
                    MediaDucker.get_instance().duck(attenuation=0.15)
                except Exception:
                    pass
            else:
                self._transition_state(WakeWordState.IDLE)
                try:
                    from .media_ducker import MediaDucker
                    MediaDucker.get_instance().unduck()
                except Exception:
                    pass
        logger.info(f"VoiceListener mode set to: {self.mode.value.upper()}")

    def _transition_state(self, new_state: WakeWordState) -> None:
        if self.state != new_state:
            self.state = new_state
            if self.on_state_changed:
                try:
                    self.on_state_changed(new_state)
                except Exception as e:
                    logger.debug(f"Error in on_state_changed callback: {e}")

    def feed_audio_frame(self, raw_pcm_bytes: bytes) -> Optional[str]:
        """
        Processes an incoming PCM audio frame (e.g. 1024 samples @ 16kHz mono).
        Applies rumble cut, soft noise profile suppression, AGC, and adaptive VAD with pre-roll.
        Returns recognized text transcript if an utterance just completed, else None.
        """
        # 1. Zero-latency TTS feedback suppression (bypassed if barge_in_enabled)
        if not self.barge_in_enabled and self.is_suppressed():
            return None

        now = time.time()

        # 2. Process frame through AudioProcessor
        proc_pcm, metrics = self.audio_processor.process_frame(raw_pcm_bytes)
        frame_to_store = proc_pcm if proc_pcm is not None else raw_pcm_bytes

        if metrics.is_speech:
            if not self._speech_in_progress:
                self._speech_in_progress = True
                self._utterance_start_time = now
                self._current_utterance_frames.clear()
                if self.mode == VoiceMode.ACTIVE:
                    try:
                        from .media_ducker import MediaDucker
                        MediaDucker.get_instance().duck(attenuation=0.15)
                    except Exception:
                        pass

            self._current_utterance_frames.append(frame_to_store)
            self._last_speech_time = now

            # Max duration safety cap
            if now - self._utterance_start_time > self._max_utterance_duration:
                return self._finalize_current_utterance(metrics)

        elif self._speech_in_progress:
            # Trailing pause detection
            self._current_utterance_frames.append(frame_to_store)
            spoken_duration = now - self._utterance_start_time
            dynamic_silence_thresh = 0.38 if spoken_duration >= 0.5 else min(self._silence_pause_threshold, 0.58)
            if now - self._last_speech_time >= dynamic_silence_thresh:
                return self._finalize_current_utterance(metrics)

        return None

    def _finalize_current_utterance(self, last_metrics: Optional[Any] = None) -> Optional[str]:
        """Assembles buffered audio frames, transcribes them, and routes through process_utterance."""
        if not self._current_utterance_frames:
            self._speech_in_progress = False
            return None

        result = self.audio_processor.finalize_utterance()
        pcm_data = result.pcm_bytes if (result and result.pcm_bytes) else b"".join(self._current_utterance_frames)
        self._current_utterance_frames.clear()
        self._speech_in_progress = False

        if len(pcm_data) < 3200:  # Less than 0.1s audio
            return None

        # Fast transcribe buffer using AGC-normalized, pre-roll prepended audio
        text = self.stt.transcribe_pcm_buffer(pcm_data)
        if text and text.strip():
            audio_conf = result.audio_confidence if result else 0.85
            dev_name = result.device_name if result else "Default Microphone"
            in_level = result.average_rms if result else 50.0
            n_floor = getattr(last_metrics, "noise_floor", 25.0) if last_metrics else 25.0
            self._last_audio_metrics = {
                "audio_confidence": audio_conf,
                "device_name": dev_name,
                "input_level": in_level,
                "noise_floor": n_floor
            }
            self.process_utterance(text)
            return text
        return None

    def _on_audio_device_changed(self, new_device: Optional[AudioDeviceInfo]) -> None:
        """Callback invoked when Bluetooth earbuds connect or disconnect."""
        with self._lock:
            if new_device and new_device.is_bluetooth:
                logger.info(f"🎧 VoiceListener: Bluetooth Earbuds active ({new_device.clean_name}). Re-routing audio stream.")
                self.noise_gate = AdaptiveNoiseGate(minimum_threshold=15.0, noise_ratio=1.10, initial_noise_floor=10.0, maximum_threshold=240.0)
            elif new_device:
                logger.info(f"🎙️ VoiceListener: Audio input switched to {new_device.clean_name}.")
                self.noise_gate = AdaptiveNoiseGate(minimum_threshold=12.0, noise_ratio=1.08, initial_noise_floor=8.0, maximum_threshold=220.0)

            if hasattr(self, "audio_processor") and self.audio_processor and new_device:
                self.audio_processor.on_device_changed(
                    new_device.clean_name,
                    is_bluetooth=new_device.is_bluetooth,
                    is_usb=new_device.is_usb
                )

            if self._audio_stream and self._audio_stream.is_active:
                self._audio_stream.switch_device(new_device.index if new_device else None)

    def start_listening(self) -> None:
        self.is_monitoring = True
        self._stop_event.clear()

        device_manager = AudioDeviceManager()
        active_device = device_manager.get_active_input_device()
        if active_device and active_device.is_bluetooth:
            self.noise_gate = AdaptiveNoiseGate(minimum_threshold=15.0, noise_ratio=1.10, initial_noise_floor=10.0, maximum_threshold=240.0)
        else:
            self.noise_gate = AdaptiveNoiseGate(minimum_threshold=12.0, noise_ratio=1.08, initial_noise_floor=8.0, maximum_threshold=220.0)
        device_manager.register_device_change_listener(self._on_audio_device_changed)
        device_manager.start_hotplug_watcher()

        if self._enable_audio_stream and self._audio_stream is None:
            self._audio_stream = PersistentAudioStream(on_frame=self.feed_audio_frame)
            self._audio_stream.start()

        if not self.is_alive():
            self.start()
        logger.info("VoiceListener: Audio monitoring active.")

    def stop_listening(self) -> None:
        self.is_monitoring = False
        self._stop_event.set()

        AudioDeviceManager().unregister_device_change_listener(self._on_audio_device_changed)
        AudioDeviceManager().stop_hotplug_watcher()

        if self._audio_stream:
            self._audio_stream.stop()
            self._audio_stream = None

        self._transition_state(WakeWordState.IDLE)
        try:
            from .media_ducker import MediaDucker
            MediaDucker.get_instance().unduck()
        except Exception:
            pass
        logger.info("VoiceListener: Audio monitoring stopped.")

    def run(self) -> None:
        while not self._stop_event.is_set():
            if self.is_monitoring:
                # Check active session timeout
                if self.mode == VoiceMode.ACTIVE:
                    if time.time() - self._last_active_speech_time > self.session_timeout:
                        logger.info("VoiceListener: Active listening session timed out -> returning to STANDBY/IDLE.")
                        self.set_mode(VoiceMode.STANDBY)
                time.sleep(0.1)
            else:
                time.sleep(0.5)

    def is_stop_phrase(self, text: str) -> bool:
        lowered = text.lower().strip()
        stop_phrases = [
            "stop listening", "stop voice", "bas jarvis", "bas karo jarvis",
            "bas karo", "shant ho jao", "chup ho jao", "cancel voice",
            "band karo", "stop", "cancel", "ruk jao", "ruko", "ruk", "chup", "shant"
        ]
        return any(p in lowered for p in stop_phrases)

    def process_utterance(self, audio_text: str) -> WakeWordMatchResult:
        """
        Main gatekeeper for incoming speech transcripts.
        - Suppresses self-voice / TTS echo.
        - Supports real-time barge-in when barge_in_enabled is True.
        - In STANDBY (IDLE): Discards all speech lacking a valid wake word.
        - In ACTIVE (LISTENING): Processes all valid commands and handles explicit stop commands.
        """
        if not audio_text or not audio_text.strip():
            return WakeWordMatchResult(detected=False)

        raw = audio_text.strip()

        # 1. Echo / TTS Self-Voice Suppression & Barge-In
        if self.is_suppressed():
            if not self.barge_in_enabled:
                logger.debug(f"VoiceListener: Discarding audio during TTS playback/cooldown: '{raw}'")
                return WakeWordMatchResult(detected=False)

            # Barge-in is enabled: check acoustic echo
            if self._is_self_voice_echo(raw):
                logger.debug(f"VoiceListener: Discarding acoustic echo during TTS: '{raw}'")
                return WakeWordMatchResult(detected=False)

            is_stop = self.is_stop_phrase(raw)
            ww_res = self.detector.detect(raw)
            is_active = (self.mode == VoiceMode.ACTIVE)

            if is_stop or ww_res.detected or is_active:
                logger.info(f"VoiceListener: ⚡ Barge-in triggered during TTS playback by: '{raw}'")
                try:
                    from .media_ducker import MediaDucker
                    MediaDucker.get_instance().duck(attenuation=0.15)
                except Exception:
                    pass
                if self.on_interrupted:
                    try:
                        self.on_interrupted(raw)
                    except Exception as e:
                        logger.debug(f"Error in on_interrupted callback: {e}")
                self.set_tts_speaking(False)
            else:
                logger.debug(f"VoiceListener: Discarding non-wake speech during TTS: '{raw}'")
                return WakeWordMatchResult(detected=False)

        # 2. Check for explicit stop command
        if self.is_stop_phrase(raw):
            logger.info(f"VoiceListener: Explicit stop command received: '{raw}'")
            self.set_mode(VoiceMode.STANDBY)
            try:
                from .media_ducker import MediaDucker
                MediaDucker.get_instance().unduck()
            except Exception:
                pass
            if self.on_command_captured:
                self.on_command_captured("stop listening")
            return WakeWordMatchResult(detected=True, cleaned_command="stop listening")

        # 3. Mode Gating
        if self.mode == VoiceMode.STANDBY:
            # Standby mode: STRICT Wake-Word Detection
            res = self.detector.detect(raw)
            if not res.detected:
                logger.debug(f"VoiceListener: [STANDBY IDLE] Discarded background speech without wake word: '{raw}'")
                return WakeWordMatchResult(detected=False)

            # Wake word confirmed!
            logger.info(f"VoiceListener: Wake word detected in '{raw}' (Position: {res.position})")
            self._transition_state(WakeWordState.WAKE_DETECTED)
            try:
                from .media_ducker import MediaDucker
                MediaDucker.get_instance().duck(attenuation=0.15)
            except Exception:
                pass
            try:
                from .chime import play_wake_chime_async
                play_wake_chime_async()
            except Exception:
                pass

            if self.on_wake_detected:
                self.on_wake_detected(res)

            if res.is_standalone:
                # Standalone "Jarvis" -> enter brief active window for next command
                self.set_mode(VoiceMode.ACTIVE)
                if self.on_command_captured:
                    self.on_command_captured("Jarvis")
            elif res.cleaned_command:
                # Command attached -> process immediately
                self._transition_state(WakeWordState.PROCESSING)
                if self.on_command_captured:
                    self.on_command_captured(res.cleaned_command)
                self._transition_state(WakeWordState.IDLE)

            return res

        else:
            # ACTIVE mode: User explicitly clicked Listen or active session in progress
            self._last_active_speech_time = time.time()
            self._transition_state(WakeWordState.PROCESSING)
            try:
                from .media_ducker import MediaDucker
                MediaDucker.get_instance().duck(attenuation=0.15)
            except Exception:
                pass

            # Check if user also included wake word, and strip if present
            ww_check = self.detector.detect(raw)
            effective_cmd = ww_check.cleaned_command if ww_check.detected else raw

            try:
                from .chime import play_wake_chime_async
                play_wake_chime_async()
            except Exception:
                pass

            if self.on_command_captured:
                self.on_command_captured(effective_cmd)

            self._transition_state(WakeWordState.LISTENING)
            return WakeWordMatchResult(detected=True, cleaned_command=effective_cmd)
