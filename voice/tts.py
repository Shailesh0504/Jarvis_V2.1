# voice/tts.py
"""
Human-Grade Neural & SAPI Streaming Text-to-Speech (TTS) Subsystem & Dedicated TTSManager.
Features hyper-realistic human voice persona (hi-IN-SwaraNeural / Zira),
thread-safe COM dispatch, natural Hindi/Hinglish prosody, instant sentence streaming,
audio caching, and zero-delay playback.
"""

from dataclasses import dataclass, field
import asyncio
import hashlib
import io
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("jarvis.voice.tts")


@dataclass
class ProsodyConfig:
    rate: int = 1  # SAPI rate: -10 to +10 (1 = natural ~175 WPM)
    rate_wpm: int = 180  # WPM for pyttsx3
    rate_edge: str = "+2%"  # Slightly lively, natural young-adult delivery
    pitch: float = 1.05  # Pitch multiplier for fallback
    pitch_edge: str = "+5Hz"  # Gentle youthful lift without sounding synthetic
    volume: float = 1.0  # 0.0 to 1.0
    voice_gender: str = "female"  # "female", "male"
    voice_name: str = "hi-IN-SwaraNeural"  # Default: Indian Female Natural Voice
    # Keep one persona across English and Hinglish sentence chunks.
    voice_name_en: str = "hi-IN-SwaraNeural"
    inter_chunk_pause_ms: int = 8  # Near-continuous human cadence between cached sentences
    allow_system_fallback: bool = False  # Never replace a selected neural persona with a robotic OS voice


class AudioLRUCache:
    """Ultra-fast in-memory LRU cache for pre-synthesized audio phrases.
    Does NOT permanently store audio files on disk unless explicitly configured.
    """

    def __init__(self, cache_dir: str = "data/audio_cache", max_mem_items: int = 100, persistent: bool = False):
        self.cache_dir = cache_dir
        self.max_mem_items = max_mem_items
        self.persistent = persistent
        self._mem_cache: Dict[str, bytes] = {}
        if self.persistent:
            try:
                os.makedirs(cache_dir, exist_ok=True)
            except Exception:
                pass

    def _extract_key_str(self, voice_or_prosody: Any) -> str:
        if isinstance(voice_or_prosody, str):
            return voice_or_prosody
        if hasattr(voice_or_prosody, "voice_name"):
            return getattr(voice_or_prosody, "voice_name", "hi-IN-SwaraNeural")
        return str(voice_or_prosody)

    def _hash_key(self, text: str, voice_or_prosody: Any) -> str:
        v_str = self._extract_key_str(voice_or_prosody)
        raw = f"{text.strip().lower()}:{v_str}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def get(self, text: str, voice_or_prosody: Any) -> Optional[bytes]:
        k = self._hash_key(text, voice_or_prosody)
        if k in self._mem_cache:
            # Refresh LRU position
            val = self._mem_cache.pop(k)
            self._mem_cache[k] = val
            return val

        if self.persistent:
            disk_path = os.path.join(self.cache_dir, f"{k}.mp3")
            if os.path.exists(disk_path):
                try:
                    with open(disk_path, "rb") as f:
                        data = f.read()
                        if data and len(data) > 500:
                            self._mem_cache[k] = data
                            return data
                except Exception:
                    pass
        return None

    def put(self, text: str, voice_or_prosody: Any, audio_data: bytes) -> None:
        if not audio_data or len(audio_data) < 500:
            return
        k = self._hash_key(text, voice_or_prosody)
        if k in self._mem_cache:
            self._mem_cache.pop(k)
        elif len(self._mem_cache) >= self.max_mem_items:
            try:
                self._mem_cache.pop(next(iter(self._mem_cache)))
            except Exception:
                pass
        self._mem_cache[k] = audio_data

        if self.persistent:
            try:
                disk_path = os.path.join(self.cache_dir, f"{k}.mp3")
                with open(disk_path, "wb") as f:
                    f.write(audio_data)
            except Exception:
                pass


class SentenceStreamer:
    """Splits incoming text streams into low-latency sentence chunks for instant streaming."""

    @staticmethod
    def clean_for_speech(text: str) -> str:
        """Cleans emojis, markdown, URLs, and code blocks for crisp speech without changing chat display."""
        if not text:
            return ""
        # Remove URLs
        cleaned = re.sub(r'https?://\S+|www\.\S+', '', text)
        # Remove markdown code blocks and inline backticks
        cleaned = re.sub(r'```.*?```', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'`[^`]*`', '', cleaned)
        # Remove markdown symbols and html tags
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', cleaned)  # Emojis
        cleaned = re.sub(r'[*_#~\[\]\(\)<>]', '', cleaned)
        # Clean excessive punctuation repeats
        cleaned = re.sub(r'[!?.]{2,}', '.', cleaned)
        # Clean excessive whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    @classmethod
    def soften_delivery_punctuation(cls, text: str) -> str:
        """Reduces synthetic punctuation pauses without changing displayed chat text."""
        cleaned = cls.clean_for_speech(text)
        cleaned = re.sub(r"\s*[,;:]\s*", " ", cleaned)
        cleaned = re.sub(r"\s*[—–-]\s*", " ", cleaned)
        cleaned = re.sub(r"[.!]+", "", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @classmethod
    def chunk_sentences(cls, text: str) -> List[str]:
        """
        Chunks text at complete sentence and natural phrase boundaries.
        Avoids tiny fragments while dispatching complete sentences immediately.
        """
        if not text:
            return []

        # Split on sentence boundaries: periods, exclamation marks, question marks, ellipsis, or newlines
        raw_chunks = re.split(r"(?<=[.!?\n])\s+|(?<=\.\.\.)\s*", text.strip())
        chunks = []
        for c in raw_chunks:
            cleaned = cls.clean_for_speech(c)
            if cleaned and len(cleaned) > 1:
                chunks.append(cleaned)
        return chunks if chunks else ([cls.clean_for_speech(text)] if cls.clean_for_speech(text) else [])


class TextToSpeech:
    """
    Human-Grade Streaming Neural TTS Engine featuring native Indian voices,
    thread-safe SAPI5 fallback, prosody modulation, audio caching, and zero-delay playback.
    """

    def __init__(
        self,
        engine: str = "native",
        prosody: Optional[ProsodyConfig] = None,
        cache_enabled: bool = True
    ):
        self.engine = engine
        self.prosody = prosody or ProsodyConfig()
        self.cache = AudioLRUCache() if cache_enabled else None
        self.streamer = SentenceStreamer()
        self._is_stopped = False
        self.current_spoken_chunk: str = ""
        self._playback_lock = threading.Lock()
        self._mixer_initialized = False
        self._current_output_device_name: Optional[str] = None
        self._thread_local = threading.local()

        # Initialize Pygame Mixer for in-memory ultra-fast mp3 playback
        self._init_audio_mixer()

    def _init_audio_mixer(self, devicename: Optional[str] = None) -> None:
        """Initializes pygame mixer for seamless audio buffer playback on preferred/earbuds device."""
        if self.engine == "mock":
            self._current_output_device_name = devicename
            return
        try:
            import pygame
            if devicename is None:
                try:
                    from voice.device_manager import AudioDeviceManager
                    devicename = AudioDeviceManager().get_best_pygame_output_devicename()
                except Exception:
                    devicename = None

            if pygame.mixer.get_init():
                try:
                    pygame.mixer.music.stop()
                except Exception:
                    pass
                try:
                    pygame.mixer.quit()
                except Exception:
                    pass

            if devicename:
                try:
                    pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=512, devicename=devicename)
                    self._mixer_initialized = True
                    self._current_output_device_name = devicename
                    logger.info(f"Pygame audio mixer initialized for neural speech playback on: '{devicename}'.")
                    return
                except Exception as d_err:
                    logger.warning(f"Failed to initialize mixer on '{devicename}': {d_err}, falling back to default.")

            pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=512)
            self._mixer_initialized = True
            self._current_output_device_name = None
            logger.info("Pygame audio mixer initialized on default audio output.")
        except Exception as e:
            logger.warning(f"Audio mixer initialization failed: {e}")
            self._mixer_initialized = False

    def switch_output_device(self, device_name: Optional[str] = None) -> bool:
        """Dynamically re-targets pygame audio mixer to a specified device (e.g. connected earbuds or speakers)."""
        if self.engine == "mock":
            self._current_output_device_name = device_name
            return True

        with self._playback_lock:
            self._init_audio_mixer(devicename=device_name)
            return self._mixer_initialized

    def _ensure_audio_mixer(self) -> bool:
        """Retries mixer initialization after startup/device timing failures."""
        if self.engine == "mock":
            return False
        try:
            import pygame
            if pygame.mixer.get_init():
                self._mixer_initialized = True
                return True
        except Exception:
            pass

        self._init_audio_mixer(devicename=self._current_output_device_name)
        return self._mixer_initialized

    def _get_thread_sapi_engine(self):
        """Thread-safe lazy initialization of SAPI5 SpVoice with female voice."""
        if self.engine == "mock":
            return None

        # Retry after a previous transient COM failure instead of caching None
        # forever for the lifetime of the persistent TTS worker.
        if getattr(self._thread_local, "sapi_engine", None) is None:
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass

            try:
                import win32com.client
                spk = win32com.client.Dispatch("SAPI.SpVoice")
                spk.Rate = int(self.prosody.rate)
                spk.Volume = int(self.prosody.volume * 100)

                # Select Female voice if available (Zira, Hazel, etc.)
                if hasattr(spk, "GetVoices"):
                    voices = spk.GetVoices()
                    for idx in range(voices.Count):
                        v = voices.Item(idx)
                        v_desc = v.GetDescription().lower()
                        if self.prosody.voice_gender == "female":
                            if any(fn in v_desc for fn in ["zira", "female", "hazel", "eva"]):
                                spk.Voice = v
                                break
                self._thread_local.sapi_engine = spk
            except Exception as e:
                logger.warning(f"Thread SAPI initialization failed: {e}")
                self._thread_local.sapi_engine = None

        return getattr(self._thread_local, "sapi_engine", None)

    def _speak_with_windows_voice(self, text: str) -> bool:
        """Uses built-in Windows speech when optional Python audio modules are absent."""
        if os.name != "nt" or not text or self._is_stopped:
            return False

        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$speaker.Rate = " + str(max(-10, min(10, int(self.prosody.rate)))) + "; "
            "$speaker.Volume = " + str(max(0, min(100, int(self.prosody.volume * 100)))) + "; "
            "$text = [Console]::In.ReadToEnd(); "
            "$speaker.Speak($text); $speaker.Dispose()"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                input=text,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                logger.info(f"TTS_WINDOWS_FALLBACK: Spoke '{text}'")
                return True
            logger.warning(f"Windows speech fallback failed: {result.stderr.strip()}")
        except Exception as exc:
            logger.warning(f"Windows speech fallback error: {exc}")
        return False

    def _select_voice_for_text(self, text: str) -> str:
        """Selects appropriate natural neural voice (Hindi/Hinglish vs English)."""
        lower = text.lower()
        hinglish_words = [
            "kya", "hain", "hoon", "aap", "bataiye", "karo", "kholo", "badhiya",
            "boliye", "theek", "kaise", "sab", "main", "meri", "mera", "yeh",
            "woh", "wahan", "yahan", "zaroor", "namaste", "shukriya", "achha"
        ]
        if any(w in lower.split() for w in hinglish_words) or any(ord(c) > 127 for c in text):
            return self.prosody.voice_name  # hi-IN-SwaraNeural
        return self.prosody.voice_name_en  # en-IN-NeerjaNeural

    def set_prosody(
        self,
        rate: Optional[int] = None,
        pitch: Optional[float] = None,
        volume: Optional[float] = None,
        voice_gender: Optional[str] = None,
        voice_name: Optional[str] = None
    ) -> None:
        if rate is not None:
            self.prosody.rate = rate
            self.prosody.rate_wpm = rate
        if pitch is not None:
            self.prosody.pitch = pitch
        if volume is not None:
            self.prosody.volume = volume
        if voice_gender is not None:
            self.prosody.voice_gender = voice_gender
            if voice_gender == "male":
                self.prosody.voice_name = "hi-IN-MadhurNeural"
                self.prosody.voice_name_en = "en-IN-PrabhatNeural"
            else:
                self.prosody.voice_name = "hi-IN-SwaraNeural"
                self.prosody.voice_name_en = "en-IN-NeerjaNeural"
        if voice_name is not None:
            self.prosody.voice_name = voice_name
            self.prosody.voice_name_en = voice_name
            self.prosody.voice_gender = "male" if voice_name in {
                "hi-IN-MadhurNeural", "en-IN-PrabhatNeural"
            } else "female"

    def stop(self) -> None:
        """Immediately interrupts and halts all active speech playback without delay."""
        self._is_stopped = True
        self.current_spoken_chunk = ""
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

        try:
            sapi = getattr(self._thread_local, "sapi_engine", None)
            if sapi:
                sapi.Speak("", 2)  # SVSFPurgeBeforeSpeak
        except Exception:
            pass

    def _synthesize_neural_audio_sync(self, text: str, voice: str) -> Optional[bytes]:
        """Synthesizes human-like neural audio synchronously via edge_tts with fast fallback."""
        cache_voice = f"{voice}|{self.prosody.rate_edge}|{self.prosody.pitch_edge}"
        if self.cache:
            cached = self.cache.get(text, cache_voice)
            if cached:
                return cached

        try:
            import edge_tts

            async def _gen():
                comm = edge_tts.Communicate(
                    text,
                    voice=voice,
                    rate=self.prosody.rate_edge,
                    pitch=self.prosody.pitch_edge
                )
                audio_bytes = bytearray()
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        audio_bytes.extend(chunk["data"])
                return bytes(audio_bytes)

            try:
                # Run with generous timeout — 1.8s was too tight on slower networks
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(lambda: asyncio.run(_gen()))
                    audio = future.result(timeout=2.5)
            except Exception as exc:
                logger.warning(f"Edge TTS streaming synthesis failed for {voice}: {exc}")
                audio = self._synthesize_neural_audio_cli(text, voice)

            if audio and self.cache:
                self.cache.put(text, cache_voice, audio)
            return audio
        except Exception as exc:
            logger.warning(f"Edge TTS import/synthesis error for {voice}: {exc}")
            return self._synthesize_neural_audio_cli(text, voice)

    def _synthesize_neural_audio_cli(self, text: str, voice: str) -> Optional[bytes]:
        """Reliable subprocess retry when Edge's async stream fails in the GUI worker."""
        import tempfile

        output_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as output_file:
                output_path = output_file.name
            result = subprocess.run(
                [
                    sys.executable, "-m", "edge_tts",
                    "--voice", voice,
                    f"--rate={self.prosody.rate_edge}",
                    f"--pitch={self.prosody.pitch_edge}",
                    "--text", text,
                    "--write-media", output_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=2.5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0 and os.path.exists(output_path):
                with open(output_path, "rb") as audio_file:
                    audio = audio_file.read()
                if len(audio) > 500:
                    logger.info(f"Edge TTS CLI retry succeeded for {voice} ({len(audio)}b)")
                    return audio
            logger.warning(f"Edge TTS CLI retry failed for {voice}: {result.stderr.strip()}")
        except Exception as exc:
            logger.warning(f"Edge TTS CLI retry error for {voice}: {exc}")
        finally:
            if output_path:
                try:
                    os.unlink(output_path)
                except OSError:
                    pass
        return None

    def speak_chunk(self, chunk: str, response_id: Optional[str] = None) -> bool:
        """Plays a single sentence chunk with natural human voice (Neural or SAPI).
        Prioritizes in-memory playback and guarantees immediate cleanup of any temporary audio.
        """
        self._is_stopped = False

        if not chunk or not chunk.strip():
            return False

        clean_text = self.streamer.soften_delivery_punctuation(chunk)
        if not clean_text:
            return False

        resp_id = response_id or getattr(self, "_current_response_id", None) or f"resp_{int(time.time() * 1000)}"

        if self.engine == "mock":
            logger.info(
                f"[TTS_START] [TTS_AUDIO_CREATED] [AUDIO_READY] [TTS_PLAYBACK_START] [PLAYBACK_STARTED] "
                f"[TTS_PLAYBACK_FINISHED] [PLAYBACK_FINISHED] [TTS_CLEANUP] response_id={resp_id} "
                f"storage=memory temp_file=none cleanup_status=not_needed [Mock TTS Playback]: '{clean_text}'"
            )
            return True

        voice = self._select_voice_for_text(clean_text)
        self.current_spoken_chunk = clean_text
        t_start = time.perf_counter()
        logger.info(f"[TTS_START] response_id={resp_id} chunk='{clean_text}' voice={voice}")

        tmp_path = None
        try:
            # 1. Primary: Human-Grade Neural Voice Playback (Swara/Neerja)
            t_gen_start = time.perf_counter()
            audio_data = self._synthesize_neural_audio_sync(clean_text, voice)
            gen_time_ms = (time.perf_counter() - t_gen_start) * 1000.0

            if audio_data and not self._mixer_initialized:
                self._ensure_audio_mixer()

            if audio_data and self._mixer_initialized and not self._is_stopped:
                logger.info(
                    f"[TTS_AUDIO_CREATED] [TTS_GENERATION_SUCCESS] response_id={resp_id} "
                    f"bytes={len(audio_data)} gen_time_ms={gen_time_ms:.1f}ms voice={voice}"
                )

                # Attempt In-Memory Playback via BytesIO first (zero disk I/O)
                try:
                    import pygame
                    bio = io.BytesIO(audio_data)
                    with self._playback_lock:
                        pygame.mixer.music.load(bio)
                        logger.info(f"[AUDIO_READY] response_id={resp_id} storage=memory temp_file=none")
                        t_play_start = time.perf_counter()
                        latency_ms = (t_play_start - t_start) * 1000.0
                        logger.info(
                            f"[TTS_PLAYBACK_START] [PLAYBACK_STARTED] response_id={resp_id} "
                            f"storage=memory latency_ms={latency_ms:.1f}ms"
                        )
                        pygame.mixer.music.play()
                        time.sleep(0.04)
                        while pygame.mixer.music.get_busy() and not self._is_stopped:
                            time.sleep(0.02)
                    duration_ms = (time.perf_counter() - t_play_start) * 1000.0
                    logger.info(
                        f"[TTS_PLAYBACK_FINISHED] [PLAYBACK_FINISHED] response_id={resp_id} duration_ms={duration_ms:.1f}ms"
                    )
                    logger.info(f"[TTS_CLEANUP] response_id={resp_id} temp_file=none cleanup_status=not_needed")
                    return True
                except Exception as mem_err:
                    logger.warning(
                        f"In-memory pygame playback failed ({mem_err}), falling back to auto-cleaned temp file"
                    )
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                        tmp.write(audio_data)
                        tmp_path = tmp.name

                    try:
                        with self._playback_lock:
                            pygame.mixer.music.load(tmp_path)
                            logger.info(f"[AUDIO_READY] response_id={resp_id} storage=disk temp_file={tmp_path}")
                            t_play_start = time.perf_counter()
                            latency_ms = (t_play_start - t_start) * 1000.0
                            logger.info(
                                f"[TTS_PLAYBACK_START] [PLAYBACK_STARTED] response_id={resp_id} "
                                f"storage=disk temp_file={tmp_path} latency_ms={latency_ms:.1f}ms"
                            )
                            pygame.mixer.music.play()
                            time.sleep(0.04)
                            while pygame.mixer.music.get_busy() and not self._is_stopped:
                                time.sleep(0.02)
                        duration_ms = (time.perf_counter() - t_play_start) * 1000.0
                        logger.info(
                            f"[TTS_PLAYBACK_FINISHED] [PLAYBACK_FINISHED] response_id={resp_id} duration_ms={duration_ms:.1f}ms"
                        )
                        return True
                    except Exception as disk_err:
                        logger.error(f"[TTS_ERROR] response_id={resp_id} Disk temp playback error: {disk_err}")
                        # Audio endpoint recovery
                        try:
                            pygame.mixer.quit()
                            self._init_audio_mixer()
                        except Exception:
                            pass

            # 2. Guaranteed Fallback: Local Thread-Safe SAPI5
            if not self._is_stopped:
                sapi = self._get_thread_sapi_engine()
                if sapi:
                    with self._playback_lock:
                        try:
                            t_play_start = time.perf_counter()
                            latency_ms = (t_play_start - t_start) * 1000.0
                            logger.info(
                                f"[TTS_PLAYBACK_START] [PLAYBACK_STARTED] response_id={resp_id} "
                                f"mode=sapi_fallback latency_ms={latency_ms:.1f}ms Speaking '{clean_text}'"
                            )
                            sapi.Speak(clean_text, 0)
                            duration_ms = (time.perf_counter() - t_play_start) * 1000.0
                            logger.info(
                                f"[TTS_PLAYBACK_FINISHED] [PLAYBACK_FINISHED] response_id={resp_id} "
                                f"mode=sapi duration_ms={duration_ms:.1f}ms"
                            )
                            logger.info(f"[TTS_CLEANUP] response_id={resp_id} temp_file=none cleanup_status=not_needed")
                            return True
                        except Exception as fb_err:
                            logger.error(f"[TTS_ERROR] response_id={resp_id} SAPI speech error: {fb_err}")
                if self.prosody.allow_system_fallback and self._speak_with_windows_voice(clean_text):
                    logger.info(f"[TTS_CLEANUP] response_id={resp_id} temp_file=none cleanup_status=not_needed")
                    return True

            logger.warning(f"[TTS_ERROR] response_id={resp_id} TTS_SILENT: All engines failed for '{clean_text}'")
            return False
        finally:
            if tmp_path:
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    logger.info(f"[TTS_CLEANUP] response_id={resp_id} temp_file={tmp_path} cleanup_status=success")
                except Exception as clean_err:
                    logger.warning(f"[TTS_CLEANUP] response_id={resp_id} temp_file={tmp_path} cleanup_status=failed error={clean_err}")
            self.current_spoken_chunk = ""

    def speak(self, text: str) -> None:
        """Synchronous speech synthesis."""
        self.speak_streaming(text)

    def prepare_response_audio(self, text: str) -> bool:
        """Pre-synthesizes all sentences in parallel before the response is displayed."""
        chunks = self.streamer.chunk_sentences(text)
        if not chunks:
            return False
        if self.engine == "mock":
            return True

        started = time.perf_counter()
        prepared_count = 0

        def _prepare(chunk: str) -> bool:
            delivery_text = self.streamer.soften_delivery_punctuation(chunk)
            if not delivery_text:
                return False
            voice = self._select_voice_for_text(delivery_text)
            return bool(self._synthesize_neural_audio_sync(delivery_text, voice))

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(chunks))) as executor:
            prepared_count = sum(1 for ready in executor.map(_prepare, chunks) if ready)

        elapsed_ms = (time.perf_counter() - started) * 1000
        if prepared_count:
            logger.info(
                f"TTS_PREPARED: {prepared_count}/{len(chunks)} chunks ready before display "
                f"({elapsed_ms:.1f}ms)"
            )
            return prepared_count == len(chunks)
        logger.warning("TTS_PREPARE_FAILED: Could not prepare response audio")
        return False

    def prepare_first_chunk(self, text: str) -> bool:
        """Backward-compatible alias for complete response prefetch."""
        return self.prepare_response_audio(text)

    def warmup(self) -> None:
        """Pre-initializes audio mixer, COM voice, and pre-caches high-frequency phrases in RAM for zero-latency speech."""
        self._ensure_audio_mixer()
        try:
            self._get_thread_sapi_engine()
        except Exception:
            pass

        # Skip network pre-synthesis in automated pytest runs or interpreter shutdown
        if os.environ.get("PYTEST_CURRENT_TEST") or sys.is_finalizing() or self.engine == "mock":
            return

        # Pre-synthesize high-frequency affirmative phrases into RAM cache so voice start is instantaneous
        common_phrases = [
            "Yes, I'm listening.",
            "Theek hai Sir.",
            "Theek hai Boss, ruk gaya.",
        ]
        for phrase in common_phrases:
            if sys.is_finalizing():
                break
            try:
                delivery_text = self.streamer.soften_delivery_punctuation(phrase)
                if delivery_text and self.cache:
                    voice = self._select_voice_for_text(delivery_text)
                    cache_voice = f"{voice}|{self.prosody.rate_edge}|{self.prosody.pitch_edge}"
                    if not self.cache.get(delivery_text, cache_voice):
                        self._synthesize_neural_audio_sync(delivery_text, voice)
            except Exception as e:
                logger.debug(f"Warmup phrase synthesis skipped: {e}")

    def speak_streaming(
        self,
        text: str,
        on_sentence_start: Optional[Callable[[str], None]] = None
    ) -> List[str]:
        """
        Streams speech sentence-by-sentence with natural human voice.
        Returns the list of spoken chunks.
        """
        if not text:
            return []

        self._is_stopped = False
        chunks = self.streamer.chunk_sentences(text)
        spoken_chunks = []

        for idx, chunk in enumerate(chunks):
            if self._is_stopped:
                break

            start_chunk_time = time.perf_counter()
            if on_sentence_start:
                on_sentence_start(chunk)

            spoken = self.speak_chunk(chunk)
            latency_ms = (time.perf_counter() - start_chunk_time) * 1000

            if spoken:
                spoken_chunks.append(chunk)
                logger.info(f"TTS Stream Chunk {idx+1}/{len(chunks)}: '{chunk}' ({latency_ms:.1f}ms) [HUMAN VOICE]")

            # Natural slight pause between sentences
            if idx < len(chunks) - 1 and not self._is_stopped:
                pause_s = self.prosody.inter_chunk_pause_ms / 1000.0
                if pause_s > 0:
                    time.sleep(pause_s)

        return spoken_chunks


class TTSManager:
    """
    Dedicated Asynchronous TTS Manager with persistent background worker thread,
    hyper-realistic human voice output, safe interruption, generation tracking, and microphone coordination.
    """

    def __init__(self, tts_engine: Optional[TextToSpeech] = None):
        self.tts = tts_engine or TextToSpeech(engine="native")
        self._queue: queue.Queue = queue.Queue()
        self._is_running = True
        self._is_speaking = False
        self._state_lock = threading.RLock()
        self._speaking_listener_callbacks: List[Callable[[bool], None]] = []
        self.current_generation_id: int = 0
        self._response_seq: int = 0

        # Start persistent worker thread
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="TTSManager-PersistentWorker",
            daemon=True
        )
        self._worker_thread.start()
        logger.info("TTSManager initialized with persistent human-voice worker and barge-in support.")

        # Register for dynamic audio output routing (Bluetooth Earbuds)
        try:
            from voice.device_manager import AudioDeviceManager
            self._adm = AudioDeviceManager()
            self._adm.register_output_device_change_listener(self._on_output_device_changed)
        except Exception as e:
            logger.debug(f"TTSManager: Could not register with AudioDeviceManager: {e}")
            self._adm = None

    def _on_output_device_changed(self, device_info: Any, pygame_name: Optional[str]) -> None:
        """Invoked when Bluetooth earbuds connect or disconnect."""
        try:
            if device_info and getattr(device_info, "is_bluetooth", False):
                logger.info(f"🎧 TTSManager: Routing speech audio to Bluetooth Earbuds ({pygame_name or getattr(device_info, 'clean_name', '')}).")
            else:
                logger.info(f"🔊 TTSManager: Restoring speech audio to {pygame_name or 'Default Speakers'}.")
            self.switch_output_device(pygame_name)
        except Exception as e:
            logger.debug(f"TTSManager _on_output_device_changed error: {e}")

    def switch_output_device(self, device_name: Optional[str] = None) -> bool:
        """Switches underlying TTS audio playback to specified device (or default)."""
        if hasattr(self.tts, "switch_output_device"):
            return self.tts.switch_output_device(device_name)
        return False

    def _next_response_id(self) -> str:
        with self._state_lock:
            self._response_seq += 1
            return f"resp_{int(time.time() * 1000)}_{self._response_seq}"

    def warmup(self) -> None:
        """Pre-warms underlying speech engine and mixer."""
        if hasattr(self.tts, "warmup"):
            self.tts.warmup()

    def add_speaking_state_listener(self, callback: Callable[[bool], None]) -> None:
        """Registers a callback for speaking state changes (e.g. mic echo suppression)."""
        self._speaking_listener_callbacks.append(callback)

    def _set_speaking_state(self, speaking: bool) -> None:
        callbacks = []
        with self._state_lock:
            if self._is_speaking != speaking:
                self._is_speaking = speaking
                callbacks = list(self._speaking_listener_callbacks)
        for cb in callbacks:
            try:
                cb(speaking)
            except Exception as e:
                logger.debug(f"Speaking state callback error: {e}")

        # Media Ducking: Automatically lower background music/YouTube while speaking and gently restore after
        try:
            from voice.media_ducker import MediaDucker
            if speaking:
                MediaDucker.get_instance().duck(attenuation=0.15)
            else:
                MediaDucker.get_instance().unduck_delayed(delay=0.4)
        except Exception:
            pass

    def is_speaking(self) -> bool:
        """Returns whether TTS is actively outputting audio."""
        with self._state_lock:
            return self._is_speaking

    def get_current_spoken_chunk(self) -> str:
        """Returns the text of the sentence chunk currently being spoken on the audio output."""
        return getattr(self.tts, "current_spoken_chunk", "")

    def speak(
        self,
        text: str,
        priority: bool = False,
        on_started: Optional[Callable[[], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
        generation_id: Optional[int] = None
    ) -> None:
        """Queues complete text, streaming its sentences immediately with natural human voice."""
        if not text or not text.strip():
            return

        if priority:
            self.stop(new_generation=True)

        with self._state_lock:
            gen = generation_id if generation_id is not None else self.current_generation_id
            self.tts._is_stopped = False

        resp_id = self._next_response_id()
        chunks = SentenceStreamer.chunk_sentences(text)
        logger.info(
            f"[RESPONSE_CREATED] response_id={resp_id} text='{text[:60]}...' "
            f"chunks={len(chunks)} (Priority={priority}, Gen={gen})"
        )

        for idx, chunk in enumerate(chunks):
            self._queue.put({
                "response_id": resp_id,
                "chunk": chunk,
                "generation_id": gen,
                "is_first": (idx == 0),
                "is_last": (idx == len(chunks) - 1),
                "on_started": on_started if idx == 0 else None,
                "on_finished": on_finished if idx == len(chunks) - 1 else None,
                "timestamp_queued": time.perf_counter()
            })
            logger.debug(f"[QUEUED_FOR_TTS] response_id={resp_id} chunk_idx={idx} total={len(chunks)}")

        # Pipelined Synthesis: For multi-sentence responses, pre-synthesize remaining chunks in memory
        if len(chunks) > 1 and self.tts.engine != "mock":
            def _prefetch_remaining():
                for c in chunks[1:]:
                    with self._state_lock:
                        if gen != self.current_generation_id:
                            break
                    cleaned = self.tts.streamer.soften_delivery_punctuation(c)
                    if cleaned:
                        v = self.tts._select_voice_for_text(cleaned)
                        self.tts._synthesize_neural_audio_sync(cleaned, v)
            threading.Thread(target=_prefetch_remaining, daemon=True, name="TTSPrefetchWorker").start()

    def stream_chunk(
        self,
        chunk: str,
        is_first: bool = False,
        is_last: bool = False,
        on_started: Optional[Callable[[], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
        generation_id: Optional[int] = None
    ) -> None:
        """Immediately queues a single sentence chunk as soon as it is generated."""
        clean = SentenceStreamer.clean_for_speech(chunk)
        if not clean:
            return

        with self._state_lock:
            gen = generation_id if generation_id is not None else self.current_generation_id
            self.tts._is_stopped = False

        resp_id = self._next_response_id()
        self._queue.put({
            "response_id": resp_id,
            "chunk": clean,
            "generation_id": gen,
            "is_first": is_first,
            "is_last": is_last,
            "on_started": on_started,
            "on_finished": on_finished,
            "timestamp_queued": time.perf_counter()
        })
        logger.info(f"[RESPONSE_CREATED] [QUEUED_FOR_TTS] response_id={resp_id} chunk='{clean}' (Gen={gen})")

    def stop(self, new_generation: bool = True) -> None:
        """Instantly stops playback, empties all pending speech tasks, and increments generation ID."""
        with self._state_lock:
            if new_generation:
                self.current_generation_id += 1
            # Drain queue
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except Exception:
                    break

            # Stop active engine output immediately
            self.tts.stop()
            self._set_speaking_state(False)
        logger.info(f"TTSManager: Speech output cancelled and queue flushed (Gen={self.current_generation_id}).")

    def _worker_loop(self) -> None:
        """Persistent background worker consuming sentence chunks with generation-based barge-in invalidation."""
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        while self._is_running:
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                if self.is_speaking():
                    self._set_speaking_state(False)
                continue

            chunk = item.get("chunk", "")
            item_gen = item.get("generation_id", self.current_generation_id)
            resp_id = item.get("response_id", f"resp_{int(time.time() * 1000)}")
            t_queued = item.get("timestamp_queued", time.perf_counter())
            on_started = item.get("on_started")
            on_finished = item.get("on_finished")

            # Invalidate stale chunks from previous interrupted turns
            with self._state_lock:
                if not chunk or item_gen != self.current_generation_id:
                    self._queue.task_done()
                    continue
                # CRITICAL FIX: Reset engine stop flag for valid current-generation item
                self.tts._is_stopped = False

            first_audio_latency_ms = (time.perf_counter() - t_queued) * 1000.0

            logger.info(f"[TTS_WORKER_RECEIVED] response_id={resp_id} chunk='{chunk}' (Gen={item_gen})")
            self._set_speaking_state(True)
            if on_started:
                try:
                    on_started()
                except Exception:
                    pass

            logger.info(
                f"[TTS_STARTED] [TTS_GENERATION_STARTED] response_id={resp_id} "
                f"Playing chunk '{chunk}' (Gen={item_gen}, Latency={first_audio_latency_ms:.1f}ms)"
            )
            playback_succeeded = False
            try:
                try:
                    playback_succeeded = self.tts.speak_chunk(chunk, response_id=resp_id)
                except TypeError:
                    playback_succeeded = self.tts.speak_chunk(chunk)

                pause_s = self.tts.prosody.inter_chunk_pause_ms / 1000.0
                if pause_s > 0 and not self._queue.empty() and not self.tts._is_stopped:
                    time.sleep(pause_s)

                # Only invoke finished callback if turn was NOT interrupted during playback
                with self._state_lock:
                    is_valid = (item_gen == self.current_generation_id and not self.tts._is_stopped)

                if is_valid and on_finished and item.get("is_last", False):
                    try:
                        on_finished()
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"[TTS_ERROR] response_id={resp_id} speak_chunk execution error: {e}")
                playback_succeeded = False
                with self._state_lock:
                    is_valid = False
            finally:
                self._queue.task_done()

            if playback_succeeded and is_valid:
                logger.info(f"[TTS_FINISHED] [PLAYBACK_FINISHED] response_id={resp_id} Chunk '{chunk}' completed.")
            else:
                if not playback_succeeded:
                    logger.info(f"[TTS_FAILED] [TTS_ERROR] response_id={resp_id} Chunk '{chunk}' playback failed.")
                else:
                    logger.debug(f"TTS_DROPPED: response_id={resp_id} Chunk '{chunk}' (valid={is_valid}, success={playback_succeeded}).")

    def shutdown(self) -> None:
        """Stops the worker thread cleanly on system shutdown."""
        self._is_running = False
        if getattr(self, "_adm", None):
            try:
                self._adm.unregister_output_device_change_listener(self._on_output_device_changed)
            except Exception:
                pass
        self.stop(new_generation=True)
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=0.5)
