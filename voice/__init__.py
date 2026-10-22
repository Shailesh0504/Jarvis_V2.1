# voice/__init__.py
"""Voice Subsystem with Universal Wake-Word Detection, Streaming TTS, and Audio Monitoring."""

from .wake_word import (
    WakeWordDetector,
    WakeWordMatchResult,
    WakeWordState,
    ConversationSessionManager,
)
from .device_manager import AudioDeviceManager, AudioDeviceInfo
from .listener import VoiceListener
from .chime import play_wake_chime_async
from .tts import TextToSpeech, TTSManager, ProsodyConfig, SentenceStreamer

__all__ = [
    "WakeWordDetector",
    "WakeWordMatchResult",
    "WakeWordState",
    "ConversationSessionManager",
    "AudioDeviceManager",
    "AudioDeviceInfo",
    "VoiceListener",
    "play_wake_chime_async",
    "TextToSpeech",
    "TTSManager",
    "ProsodyConfig",
    "SentenceStreamer",
]
