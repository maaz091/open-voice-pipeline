"""Base class for text-to-speech providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from voice_pipeline.config import VoicePipelineSettings


class AudioChunk:
    """An audio chunk from TTS."""

    __slots__ = ("audio", "final")

    def __init__(self, audio: bytes, final: bool = False):
        self.audio = audio
        self.final = final


class TextToSpeechProvider(ABC):
    """Abstract base class for text-to-speech providers."""

    def __init__(self, settings: VoicePipelineSettings):
        self.settings = settings

    @abstractmethod
    async def stream_speech(self, text: str) -> AsyncIterator[AudioChunk]:
        """
        Convert text to speech audio.
        
        Args:
            text: The text to synthesize
            
        Yields:
            AudioChunk objects with audio bytes
        """
        raise NotImplementedError

