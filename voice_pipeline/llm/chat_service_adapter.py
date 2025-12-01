"""Adapter for the existing Django ChatService."""

import logging
from collections.abc import AsyncIterator

import httpx

from voice_pipeline.llm.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class ChatServiceAdapter(LLMProvider):
    """Adapts the existing Django ChatService for use in the voice pipeline."""

    async def stream_response(self, transcript: str) -> AsyncIterator[LLMResponse]:
        """Send transcript to ChatService and stream back responses."""
        if not transcript or not transcript.strip():
            return

        payload = {
            "message": transcript,
            "stream": True,
        }

        headers = {"Content-Type": "application/json"}
        if self.settings.chat_service_api_key:
            headers["Authorization"] = f"Bearer {self.settings.chat_service_api_key}"

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
                    "POST",
                    self.settings.chat_service_url,
                    json=payload,
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line:
                            # Parse SSE or JSON response
                            # This is a simplified version - adjust based on actual ChatService format
                            yield LLMResponse(text=line, final=False)
                    yield LLMResponse(text="", final=True)
        except httpx.RequestError as e:
            logger.error(f"ChatService request failed: {e}")
            raise RuntimeError(f"Failed to connect to ChatService: {e}") from e


