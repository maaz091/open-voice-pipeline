"""Coqui XTTS TTS provider implementation."""

import logging
import re
from collections.abc import AsyncIterator

import httpx

from voice_pipeline.tts.base import AudioChunk, TextToSpeechProvider

logger = logging.getLogger(__name__)

# XTTS has a 400 token limit. Use ~250 characters per chunk to be safe
# (tokens are typically 1-4 characters, so 250 chars ≈ 200-250 tokens)
MAX_CHUNK_LENGTH = 250


def split_text_into_chunks(text: str, max_length: int = MAX_CHUNK_LENGTH) -> list[str]:
    """
    Split text into chunks that respect XTTS token limits.
    
    Tries to split at sentence boundaries first, then at word boundaries.
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    remaining = text
    
    while len(remaining) > max_length:
        # Try to split at sentence boundary (., !, ?)
        sentence_match = re.search(rf'.{{0,{max_length}}}[.!?]\s+', remaining)
        if sentence_match:
            chunk = sentence_match.group(0).strip()
            remaining = remaining[len(chunk):].strip()
            if chunk:
                chunks.append(chunk)
            continue
        
        # Try to split at word boundary
        word_match = re.search(rf'.{{0,{max_length}}}\s+', remaining)
        if word_match:
            chunk = word_match.group(0).strip()
            remaining = remaining[len(chunk):].strip()
            if chunk:
                chunks.append(chunk)
            continue
        
        # Force split at max_length (shouldn't happen often)
        chunk = remaining[:max_length]
        remaining = remaining[max_length:].strip()
        if chunk:
            chunks.append(chunk)
    
    if remaining:
        chunks.append(remaining)
    
    return chunks


class CoquiTTSProvider(TextToSpeechProvider):
    """Calls a Coqui XTTS HTTP endpoint to synthesize audio."""

    async def stream_speech(self, text: str) -> AsyncIterator[AudioChunk]:
        """Synthesize speech using Coqui XTTS service."""
        if not self.settings.tts_service_url:
            raise RuntimeError("TTS service URL missing.")

        # Split text into chunks if it's too long
        text_chunks = split_text_into_chunks(text, MAX_CHUNK_LENGTH)
        
        if len(text_chunks) > 1:
            logger.info(f"Splitting text into {len(text_chunks)} chunks for TTS (total length: {len(text)})")
        else:
            logger.info(f"TTS request to: {self.settings.tts_service_url}")

        # Synthesize each chunk sequentially
        for i, chunk_text in enumerate(text_chunks):
            logger.info(f"🔊 TTS chunk {i+1}/{len(text_chunks)}: '{chunk_text[:50]}...'")
            
            # XTTS server API: text, language, speed, and optionally speaker_id
            payload = {
                "text": chunk_text,
                "language": self.settings.tts_language,
                "speed": self.settings.tts_speed,
            }
            # Add speaker_id if configured
            if self.settings.tts_speaker_id:
                payload["speaker_id"] = self.settings.tts_speaker_id

            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    async with client.stream(
                        "POST", self.settings.tts_service_url, json=payload
                    ) as response:
                        response.raise_for_status()
                        
                        # Accumulate complete WAV file
                        audio_bytes = bytearray()
                        chunk_count = 0
                        
                        # Collect all chunks from HTTP response
                        async for http_chunk in response.aiter_bytes():
                            if http_chunk:
                                audio_bytes.extend(http_chunk)
                                chunk_count += 1
                        
                        total_bytes = len(audio_bytes)
                        logger.info(f"✅ TTS chunk {i+1}/{len(text_chunks)}: received {chunk_count} HTTP chunks, {total_bytes} total bytes")
                        
                        if total_bytes == 0:
                            logger.warning(f"⚠️ No audio received for chunk {i+1}")
                            continue
                        
                        # Send complete WAV file as a single chunk
                        # Mark final=True for each complete WAV file so browser can play it immediately
                        is_last_text_chunk = (i == len(text_chunks) - 1)
                        logger.info(f"📤 Yielding audio chunk {i+1}: {total_bytes} bytes, final={is_last_text_chunk}")
                        yield AudioChunk(audio=bytes(audio_bytes), final=True)  # Always final=True for complete WAV files
            except httpx.ConnectError as e:
                raise RuntimeError(
                    f"Failed to connect to TTS service at {self.settings.tts_service_url}. "
                    f"Is the XTTS container running? Error: {e}"
                ) from e
            except httpx.HTTPStatusError as e:
                # Don't try to read response.text on streaming responses
                error_msg = f"TTS synthesis failed for chunk {i+1}/{len(text_chunks)}: {e.response.status_code}"
                try:
                    # Try to read error message if available
                    if hasattr(e.response, 'text') and not isinstance(e.response, httpx.StreamingResponse):
                        error_msg += f" - {e.response.text}"
                except Exception:
                    pass
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e
