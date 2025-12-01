import base64
import logging
from collections.abc import AsyncIterator

import httpx

from voice_pipeline.stt.base import SpeechToTextProvider, Transcript

logger = logging.getLogger(__name__)


class GeminiSTTProvider(SpeechToTextProvider):
    """Uploads audio to Gemini and yields a transcript."""

    _api_url = "https://generativelanguage.googleapis.com/v1beta"

    async def stream(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[Transcript]:
        """
        Convert audio chunks to transcript using Gemini API.
        
        Collects all audio chunks and processes them as a complete utterance.
        Yields a single final transcript.
        """
        if not self.settings.gemini_api_key:
            raise RuntimeError("Gemini API key not configured.")

        # Collect all audio chunks
        audio_bytes = bytearray()
        async for chunk in audio_chunks:
            if chunk:
                audio_bytes.extend(chunk)

        if not audio_bytes:
            return

        # Process complete audio and yield final transcript
        try:
            text = await self._transcribe_audio(bytes(audio_bytes))
            if text:
                logger.info(f"🎤 GEMINI STT RESULT: '{text}'")
                yield Transcript(text=text, final=True)
            else:
                logger.warning("Gemini STT returned empty text")
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            raise

    async def _transcribe_audio(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes using Gemini API."""
        if not audio_bytes:
            return ""
            
        # Build payload
        payload = self._build_payload(audio_bytes)
        model_name = self.settings.gemini_model
        url = f"{self._api_url}/models/{model_name}:generateContent"

        logger.debug(f"Transcribing {len(audio_bytes)} bytes with {model_name}")

        # Make request
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                params={"key": self.settings.gemini_api_key},
                json=payload,
            )
            if not response.is_success:
                error_body = response.text
                raise RuntimeError(
                    f"Gemini API error {response.status_code}: {error_body}"
                )
            data = response.json()
            text = self._extract_transcript(data)
            logger.debug(f"Extracted transcript: {text[:100] if text else 'EMPTY'}")
            return text

    def _build_payload(self, audio: bytes) -> dict:
        """Construct Gemini inline audio payload."""
        audio_b64 = base64.b64encode(audio).decode("ascii")
        return {
            "contents": [
                {
                    "parts": [
                        {
                            "text": "Transcribe the following audio. Only output the exact words spoken, do not respond or add any commentary. Just the transcription:"
                        },
                        {
                            "inline_data": {
                                "mime_type": self.settings.gemini_audio_mime_type,
                                "data": audio_b64,
                            }
                        }
                    ],
                }
            ],
            # System instruction to ensure transcription only
            "system_instruction": {
                "parts": [{"text": "You are a speech-to-text transcription service. Your only job is to transcribe audio exactly as spoken. Do not respond, comment, or add anything. Just output the exact words you hear."}]
            }
        }

    def _extract_transcript(self, data: dict) -> str:
        """Extract transcript text from Gemini response."""
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                logger.warning("No candidates in Gemini response")
                return ""
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                logger.warning("No parts in Gemini response content")
                return ""
            
            text = parts[0].get("text", "").strip()
            
            # If Gemini returned JSON (with timestamps), parse it and extract just text
            if text.startswith("[") or text.startswith("{"):
                import json
                try:
                    transcript_data = json.loads(text)
                    # If it's a list of segments with text fields
                    if isinstance(transcript_data, list):
                        text_parts = [item.get("text", "") for item in transcript_data if isinstance(item, dict) and item.get("text")]
                        if text_parts:
                            return " ".join(text_parts)
                    # If it's a dict with text field
                    elif isinstance(transcript_data, dict):
                        dict_text = transcript_data.get("text", "")
                        if dict_text:
                            return dict_text
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parsing failed: {e}, returning raw text")
                    # If JSON parsing fails, return the text as-is
                    pass
            
            # Strip timestamps (format: "00:01 text here" or "00:01:00 text here")
            import re
            # Remove timestamp patterns like "00:01 " or "00:01:00 " at start of lines
            text = re.sub(r'^\d{2}:\d{2}(:\d{2})?\s+', '', text, flags=re.MULTILINE)
            
            return text if text else ""
        except (KeyError, IndexError, AttributeError) as e:
            logger.error(f"Error extracting transcript: {e}", exc_info=True)
            return ""

