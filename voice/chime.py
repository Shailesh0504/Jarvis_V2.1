# voice/chime.py
"""
Acoustic Cues & Futuristic Wake-Chime Audio Player for Jarvis V2.
Plays instant, non-blocking affirmative acoustic tones on wake-word detection.
"""

import logging
import io
import math
import struct
import threading
import time
import wave
from pathlib import Path

logger = logging.getLogger("jarvis.voice.chime")

_chime_lock = threading.Lock()
_last_chime_at = 0.0
_DEBOUNCE_SECONDS = 0.35
_WAKE_SOUND_PATH = Path(__file__).resolve().parents[1] / "plugins" / "sounds" / "jarvis.mp3"
_cached_wake_sound = None
_sound_load_lock = threading.Lock()


_DEFAULT_VOLUME = 0.90


def play_wake_chime_async() -> None:
    """Play one non-blocking soft cue, suppressing duplicate wake events."""
    global _last_chime_at
    now = time.monotonic()
    with _chime_lock:
        if now - _last_chime_at < _DEBOUNCE_SECONDS:
            return
        _last_chime_at = now
    t = threading.Thread(target=_play_wake_chime_sync, daemon=True, name="JarvisWakeChimeThread")
    t.start()


def _play_wake_chime_sync() -> None:
    """Start the configured MP3 without blocking wake-word processing."""
    global _cached_wake_sound
    try:
        if not _WAKE_SOUND_PATH.is_file():
            raise FileNotFoundError(str(_WAKE_SOUND_PATH))

        import pygame
        with _sound_load_lock:
            if not pygame.mixer.get_init():
                devicename = None
                try:
                    from voice.device_manager import AudioDeviceManager
                    devicename = AudioDeviceManager().get_best_pygame_output_devicename()
                except Exception:
                    devicename = None
                if devicename:
                    try:
                        pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=512, devicename=devicename)
                    except Exception:
                        pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=512)
                else:
                    pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=512)
                _cached_wake_sound = None

            if _cached_wake_sound is None:
                # Decode once. Every later wake reuses the in-memory sound and
                # therefore does no disk I/O or MP3 decoding on the hot path.
                _cached_wake_sound = pygame.mixer.Sound(str(_WAKE_SOUND_PATH))
                _cached_wake_sound.set_volume(_DEFAULT_VOLUME)
            sound = _cached_wake_sound

        channel = pygame.mixer.find_channel(force=True)
        if channel is None:
            raise RuntimeError("No pygame audio channel available")
        channel.play(sound)
        logger.info("Wake chime audio played successfully.")
        time.sleep(0.35)
        return
    except Exception as mp3_error:
        logger.debug(f"Wake MP3 unavailable; using synthesized fallback: {mp3_error}")

    _play_synthesized_fallback()


def _play_synthesized_fallback() -> None:
    """Generate Jarvis' built-in soft rising shimmer fallback cue."""
    try:
        import winsound
        sample_rate = 22050
        duration = 0.42
        frame_count = int(sample_rate * duration)
        frames = bytearray()

        # An original, assistant-style two-stage shimmer: a warm opening tone
        # followed by a brighter resolving tone. Layered harmonics and a slow
        # release keep it musical instead of sounding like a system beep.
        for index in range(frame_count):
            seconds = index / sample_rate
            position = seconds / duration
            attack = min(1.0, seconds / 0.025)
            release = min(1.0, max(0.0, duration - seconds) / 0.16)
            envelope = attack * release

            first_fade = max(0.0, 1.0 - seconds / 0.28)
            second_age = max(0.0, seconds - 0.105)
            second_fade = (1.0 - math.exp(-second_age / 0.025)) * max(
                0.0, 1.0 - second_age / 0.34
            )

            first = math.sin(2.0 * math.pi * 523.25 * seconds) * first_fade
            second = math.sin(2.0 * math.pi * 783.99 * seconds) * second_fade
            sparkle = math.sin(2.0 * math.pi * 1046.50 * seconds) * second_fade * 0.22
            body = (first * 0.62) + (second * 0.72) + sparkle

            # Gentle stereo movement gives the cue a spacious assistant feel.
            pan = 0.5 + (0.22 * math.sin(math.pi * position))
            amplitude = 32767 * 0.40 * envelope
            left = int(max(-32767, min(32767, amplitude * body * (1.0 - pan * 0.28))))
            right = int(max(-32767, min(32767, amplitude * body * (0.72 + pan * 0.28))))
            frames.extend(struct.pack("<hh", left, right))

        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav_file:
            wav_file.setnchannels(2)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(frames)
        winsound.PlaySound(audio.getvalue(), winsound.SND_MEMORY | winsound.SND_SYNC)
    except Exception as e:
        logger.debug(f"Native winsound chime unavailable: {e}")
        try:
            # MessageBeep is backed by the Windows sound scheme and remains
            # audible on systems where in-memory WAV playback is unavailable.
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
            return
        except Exception as fallback_error:
            logger.debug(f"Windows notification fallback unavailable: {fallback_error}")

        try:
            import sys
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass
