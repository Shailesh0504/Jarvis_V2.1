# core/models/gateway.py
"""
Model Gateway Abstraction for Jarvis V2.1.
Decouples core business logic and orchestration from specific model vendors and hardware dependencies.
Provides abstract interfaces for LLM, Embedding, STT, TTS, and Vision providers.
"""

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.core.models.gateway")


class LLMProvider(ABC):
    """Abstract interface for text and conversational inference models."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        pass

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        pass


class EmbeddingProvider(ABC):
    """Abstract interface for semantic vector embeddings."""

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        pass


class STTProvider(ABC):
    """Abstract interface for speech-to-text recognition."""

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, **kwargs) -> str:
        pass

    @abstractmethod
    def is_speech(self, audio_bytes: bytes) -> bool:
        pass


class TTSProvider(ABC):
    """Abstract interface for text-to-speech audio generation."""

    @abstractmethod
    def synthesize(self, text: str, **kwargs) -> bytes:
        pass

    @abstractmethod
    def speak(self, text: str, **kwargs) -> bool:
        pass


class VisionProvider(ABC):
    """Abstract interface for biometric authentication and visual inspection."""

    @abstractmethod
    def authenticate_face(self, frame_data: Optional[Any] = None) -> bool:
        pass

    @abstractmethod
    def inspect_screen(self) -> Dict[str, Any]:
        pass


class DefaultLocalLLMAdapter(LLMProvider):
    """Adapter bridging existing brain.llm.BaseLLMProvider to LLMProvider interface."""

    def __init__(self, legacy_llm: Optional[Any] = None):
        self._legacy = legacy_llm

    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        if self._legacy and hasattr(self._legacy, "generate"):
            return self._legacy.generate(prompt, system_prompt=system_prompt, **kwargs)
        return "I am operating in local offline mode."

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        if self._legacy and hasattr(self._legacy, "chat"):
            return self._legacy.chat(messages, **kwargs)
        last_msg = messages[-1]["content"] if messages else ""
        return self.generate(last_msg, **kwargs)


class DefaultLocalSTTAdapter(STTProvider):
    """Adapter bridging voice.stt / voice.listener to STTProvider interface."""

    def __init__(self, legacy_stt: Optional[Any] = None):
        self._legacy = legacy_stt

    def transcribe(self, audio_bytes: bytes, **kwargs) -> str:
        if self._legacy and hasattr(self._legacy, "transcribe"):
            res = self._legacy.transcribe(audio_bytes)
            return getattr(res, "normalized_text", str(res))
        return ""

    def is_speech(self, audio_bytes: bytes) -> bool:
        if self._legacy and hasattr(self._legacy, "is_speech"):
            return self._legacy.is_speech(audio_bytes)
        return len(audio_bytes) > 100


class DefaultLocalTTSAdapter(TTSProvider):
    """Adapter bridging voice.tts.TTSManager to TTSProvider interface."""

    def __init__(self, legacy_tts: Optional[Any] = None):
        self._legacy = legacy_tts

    def synthesize(self, text: str, **kwargs) -> bytes:
        if self._legacy and hasattr(self._legacy, "synthesize_to_bytes"):
            return self._legacy.synthesize_to_bytes(text)
        return b""

    def speak(self, text: str, **kwargs) -> bool:
        if self._legacy and hasattr(self._legacy, "speak"):
            self._legacy.speak(text)
            return True
        return True


class ModelGateway:
    """
    Central registry and provider gateway.
    Core orchestration depends ONLY on ModelGateway and its abstract interfaces,
    never on vendor-specific drivers directly.
    """

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
        embedding: Optional[EmbeddingProvider] = None,
        stt: Optional[STTProvider] = None,
        tts: Optional[TTSProvider] = None,
        vision: Optional[VisionProvider] = None,
    ):
        self.llm: LLMProvider = llm or DefaultLocalLLMAdapter()
        self.embedding: Optional[EmbeddingProvider] = embedding
        self.stt: STTProvider = stt or DefaultLocalSTTAdapter()
        self.tts: TTSProvider = tts or DefaultLocalTTSAdapter()
        self.vision: Optional[VisionProvider] = vision

    def register_llm(self, provider: LLMProvider) -> None:
        self.llm = provider
        logger.info(f"[ModelGateway] Registered LLMProvider: {type(provider).__name__}")

    def register_stt(self, provider: STTProvider) -> None:
        self.stt = provider
        logger.info(f"[ModelGateway] Registered STTProvider: {type(provider).__name__}")

    def register_tts(self, provider: TTSProvider) -> None:
        self.tts = provider
        logger.info(f"[ModelGateway] Registered TTSProvider: {type(provider).__name__}")

    def register_vision(self, provider: VisionProvider) -> None:
        self.vision = provider
        logger.info(f"[ModelGateway] Registered VisionProvider: {type(provider).__name__}")
