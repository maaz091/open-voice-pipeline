"""Orchestration of STT → LLM → TTS pipeline."""

import asyncio
import logging
import re
from collections.abc import AsyncIterator

from voice_pipeline.llm.base import LLMProvider
from voice_pipeline.stt.base import SpeechToTextProvider
from voice_pipeline.transport.dto import AgentAudioChunk, AgentTextChunk, TranscriptChunk
from voice_pipeline.tts.base import TextToSpeechProvider

logger = logging.getLogger(__name__)

# Pattern to detect sentence boundaries for streaming TTS
SENTENCE_PATTERN = re.compile(r'([.!?]+\s+|\.{3}\s+)')


class VoicePipeline:
    """Orchestrates STT, LLM, and TTS providers for a voice session."""

    def __init__(
        self,
        stt_provider: SpeechToTextProvider,
        llm_provider: LLMProvider,
        tts_provider: TextToSpeechProvider,
    ):
        self.stt_provider = stt_provider
        self.llm_provider = llm_provider
        self.tts_provider = tts_provider
        self._interrupted = False
        self._current_tts_task: asyncio.Task | None = None

    def interrupt(self):
        """Interrupt current processing (e.g., stop TTS playback)."""
        logger.info("Pipeline interrupted by user")
        self._interrupted = True
        if self._current_tts_task:
            self._current_tts_task.cancel()

    async def process_audio_chunk(self, audio_chunk: bytes) -> AsyncIterator:
        """
        Process complete audio through the pipeline: STT → LLM → TTS.
        
        Simple flow:
        1. Audio → STT → Text
        2. Text → LLM → Text response
        3. Text response → TTS → Audio
        
        Yields events in sequence:
        - TranscriptChunk: STT transcription result (final)
        - AgentTextChunk: LLM response text (streaming)
        - AgentAudioChunk: TTS synthesized audio (streaming)
        """
        self._interrupted = False
        
        async def audio_iterator():
            yield audio_chunk

        # Step 1: STT - Convert audio to text
        transcript_text = ""
        async for transcript in self.stt_provider.stream(audio_iterator()):
            if self._interrupted:
                logger.info("STT interrupted")
                return
                
            if transcript.final and transcript.text:
                transcript_text = transcript.text
                logger.info(f"✅ STT TRANSCRIPT: '{transcript_text}'")
                yield TranscriptChunk(text=transcript_text, final=True)
                break

        if not transcript_text.strip() or self._interrupted:
            logger.warning("No transcript generated from audio or interrupted")
            return

        # Step 2 & 3: LLM → TTS (REAL-TIME STREAMING like ElevenLabs)
        # Start TTS as soon as we have complete sentences, don't wait for full LLM response
        logger.info(f"📝 Sending to LLM: '{transcript_text[:100]}...'")
        
        text_buffer = ""  # Accumulate text until we have complete sentences
        llm_chunk_count = 0
        tts_sentence_count = 0
        is_llm_final = False
        
        async for llm_response in self.llm_provider.stream_response(transcript_text):
            if self._interrupted:
                logger.info("LLM interrupted")
                return
            
            llm_chunk_count += 1
            
            # Yield text chunk to client immediately
            yield AgentTextChunk(text=llm_response.text, final=llm_response.final)
            
            # Accumulate text for TTS
            if llm_response.text:
                text_buffer += llm_response.text
                logger.debug(f"📝 Text buffer: '{text_buffer[:100]}...' ({len(text_buffer)} chars)")
            
            # Check if we have complete sentences to synthesize (REAL-TIME)
            while text_buffer:
                # Look for sentence endings
                match = SENTENCE_PATTERN.search(text_buffer)
                if match:
                    # Found a complete sentence - synthesize it IMMEDIATELY
                    sentence_end = match.end()
                    sentence = text_buffer[:sentence_end].strip()
                    text_buffer = text_buffer[sentence_end:]
                    
                    if sentence:
                        tts_sentence_count += 1
                        logger.info(f"🔊 REAL-TIME TTS: Synthesizing sentence {tts_sentence_count}: '{sentence[:80]}...'")
                        
                        # Synthesize this sentence immediately (don't wait for more text!)
                        try:
                            async for audio_chunk in self.tts_provider.stream_speech(sentence):
                                if self._interrupted:
                                    logger.info("TTS interrupted during sentence synthesis")
                                    return
                                
                                # Pass through audio chunks with their final flag from TTS provider
                                # TTS provider already marks complete WAV files with final=True
                                yield AgentAudioChunk(audio=audio_chunk.audio, final=audio_chunk.final)
                            
                            logger.debug(f"✅ Sent audio chunks for sentence {tts_sentence_count}")
                        except Exception as e:
                            logger.error(f"TTS error for sentence {tts_sentence_count}: {e}", exc_info=True)
                else:
                    # No complete sentence yet, wait for more text
                    break
            
            # Check if LLM is done
            if llm_response.final:
                is_llm_final = True
                logger.info(f"✅ LLM response complete: {llm_chunk_count} chunks")
                break
        
        # Synthesize any remaining text after LLM finishes
        if text_buffer.strip() and not self._interrupted:
            remaining = text_buffer.strip()
            logger.info(f"🔊 Synthesizing remaining text: '{remaining[:80]}...'")
            try:
                async for audio_chunk in self.tts_provider.stream_speech(remaining):
                    if self._interrupted:
                        return
                    # Last chunk from TTS provider already has final=True, so pass it through
                    yield AgentAudioChunk(audio=audio_chunk.audio, final=audio_chunk.final)
            except Exception as e:
                logger.error(f"TTS error for remaining text: {e}", exc_info=True)
        
        # Don't send empty final chunk - each sentence's last chunk already has final=True
        logger.info(f"✅ REAL-TIME TTS complete: {tts_sentence_count} sentences synthesized as they arrived")
