"""Base class for LLM providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from voice_pipeline.config import VoicePipelineSettings


class LLMResponse:
    """A response chunk from the LLM."""

    __slots__ = ("text", "final")

    def __init__(self, text: str, final: bool = False):
        self.text = text
        self.final = final


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, settings: VoicePipelineSettings):
        self.settings = settings

    @abstractmethod
    async def stream_response(self, transcript: str) -> AsyncIterator[LLMResponse]:
        """
        Get LLM response for a transcript.
        
        Args:
            transcript: The user's transcribed text
            
        Yields:
            LLMResponse objects with text chunks
        """
        raise NotImplementedError
