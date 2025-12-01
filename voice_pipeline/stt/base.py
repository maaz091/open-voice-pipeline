from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from voice_pipeline.config import VoicePipelineSettings


class Transcript:
    """A transcript chunk from STT."""

    __slots__ = ("text", "final")

    def __init__(self, text: str, final: bool = False):
        self.text = text
        self.final = final


class SpeechToTextProvider(ABC):
    """Abstract base class for speech-to-text providers."""

    def __init__(self, settings: VoicePipelineSettings):
        self.settings = settings

    @abstractmethod
    async def stream(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[Transcript]:
        """
        Convert audio chunks to transcripts.
        
        Args:
            audio_chunks: Async iterator of audio byte chunks
            
        Yields:
            Transcript objects with text and final flag
        """
        raise NotImplementedError

