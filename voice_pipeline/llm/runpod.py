"""Runpod LLM provider implementation using OpenAI-compatible API."""

import json
import logging
from collections.abc import AsyncIterator

import httpx

from voice_pipeline.llm.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class RunpodLLMProvider(LLMProvider):
    """LLM provider that calls Runpod API (OpenAI-compatible endpoint)."""

    async def stream_response(self, transcript: str) -> AsyncIterator[LLMResponse]:
        """Send transcript to Runpod API and stream back responses."""
        if not transcript or not transcript.strip():
            logger.warning("Empty transcript, skipping LLM call")
            return

        # Get Runpod configuration from settings
        runpod_base_url = getattr(self.settings, "runpod_base_url", None)
        runpod_api_key = getattr(self.settings, "runpod_api_key", None)
        runpod_model = getattr(self.settings, "runpod_model", None)

        if not runpod_base_url:
            raise RuntimeError("Runpod base URL not configured. Set VOICE_RUNPOD_BASE_URL.")

        # Build OpenAI-compatible request
        # Handle URLs that already have /v1 or don't have it
        base_url = runpod_base_url.rstrip('/')
        if base_url.endswith('/v1'):
            # URL already has /v1, just append chat/completions
            url = f"{base_url}/chat/completions"
        else:
            # URL doesn't have /v1, add it
            url = f"{base_url}/v1/chat/completions"
        
        payload = {
            "model": runpod_model or "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": transcript}
            ],
            "stream": True,
        }

        headers = {
            "Content-Type": "application/json",
        }
        if runpod_api_key:
            headers["Authorization"] = f"Bearer {runpod_api_key}"

        logger.info(f"📤 Sending to Runpod LLM: {url}")
        logger.info(f"📝 Transcript: '{transcript[:100]}...'")

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    
                    # Parse SSE (Server-Sent Events) stream
                    buffer = ""
                    chunk_count = 0
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        
                        # Process complete lines
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            
                            if not line or line == "data: [DONE]":
                                if line == "data: [DONE]":
                                    logger.info(f"✅ LLM stream complete: {chunk_count} chunks received")
                                continue
                                
                            if line.startswith("data: "):
                                data_str = line[6:]  # Remove "data: " prefix
                                try:
                                    data = json.loads(data_str)
                                    choices = data.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            chunk_count += 1
                                            logger.debug(f"LLM chunk {chunk_count}: '{content[:50]}...'")
                                            yield LLMResponse(text=content, final=False)
                                except json.JSONDecodeError:
                                    logger.warning(f"Failed to parse SSE data: {data_str}")
                    
                    logger.info(f"✅ LLM response complete: {chunk_count} text chunks")
                    yield LLMResponse(text="", final=True)
                    
        except httpx.RequestError as e:
            logger.error(f"Runpod API request failed: {e}")
            raise RuntimeError(f"Failed to connect to Runpod API: {e}") from e
