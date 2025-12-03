"""Whisper STT provider implementation using openai-whisper."""

import io
import logging
from collections.abc import AsyncIterator

import numpy as np
import soundfile as sf
import torch
import whisper

from voice_pipeline.stt.base import SpeechToTextProvider, Transcript

logger = logging.getLogger(__name__)


class WhisperSTTProvider(SpeechToTextProvider):
    """Local Whisper model for speech-to-text transcription."""

    def __init__(self, settings):
        super().__init__(settings)
        self._model = None
        self._model_name = getattr(settings, "whisper_model", "base")

    def _load_model(self):
        """Lazy load Whisper model on first use."""
        if self._model is None:
            logger.info(f"Loading Whisper model: {self._model_name}")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = whisper.load_model(self._model_name, device=device)
            logger.info(f"Whisper model loaded on {device}")
        return self._model

    async def stream(
        self, audio_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[Transcript]:
        """
        Convert audio chunks to transcript using Whisper.

        Collects all audio chunks and processes them as a complete utterance.
        Yields a single final transcript.
        """
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
                logger.info(f" WHISPER STT RESULT: '{text}'")
                yield Transcript(text=text, final=True)
            else:
                logger.warning("Whisper STT returned empty text")
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}", exc_info=True)
            raise

    async def _transcribe_audio(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes using Whisper model."""
        if not audio_bytes:
            return ""

        # Load model (lazy load on first use)
        model = self._load_model()

        # Convert audio bytes to numpy array
        # Try to read as WAV first, fallback to raw audio
        try:
            audio_file = io.BytesIO(audio_bytes)
            audio_data, sample_rate = sf.read(audio_file)
            
            # Convert to mono if stereo
            if audio_data.ndim > 1:
                audio_data = np.mean(audio_data, axis=1)
            
            # Ensure float32 format
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)
            
            # Normalize to [-1, 1] range if needed
            if np.abs(audio_data).max() > 1.0:
                audio_data = audio_data / np.abs(audio_data).max()
            
        except Exception as e:
            logger.warning(f"Failed to read audio with soundfile: {e}, trying raw conversion")
            # Fallback: assume raw PCM audio (16-bit, mono, 16kHz)
            # This is a common format from browser MediaRecorder
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
            audio_array = audio_array / 32768.0  # Normalize to [-1, 1]
            audio_data = audio_array
            sample_rate = 16000  # Default assumption

        logger.debug(f"Transcribing {len(audio_data)} samples at {sample_rate}Hz")

        # Run transcription
        # Use fp16=False for CPU compatibility, fp16=True for GPU (faster)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        result = model.transcribe(
            audio_data,
            fp16=(device == "cuda"),
            language=getattr(self.settings, "whisper_language", None),
            task="transcribe",
        )

        text = result.get("text", "").strip()
        logger.debug(f"Extracted transcript: {text[:100] if text else 'EMPTY'}")
        return text
