"""WebSocket server for real-time voice sessions."""

import asyncio
import base64
import json
import logging

from fastapi import WebSocket

from voice_pipeline.config import VoicePipelineSettings
from voice_pipeline.pipeline import VoicePipeline
from voice_pipeline.providers import (
    create_llm_provider,
    create_stt_provider,
    create_tts_provider,
)
from voice_pipeline.transport.dto import (
    AgentAudioChunk,
    AgentTextChunk,
    ModeChangeEvent,
    TranscriptChunk,
)

logger = logging.getLogger(__name__)


class VoiceWebSocketServer:
    """WebSocket server for voice pipeline sessions (ElevenLabs-like behavior)."""

    def __init__(self, settings: VoicePipelineSettings):
        self.settings = settings

    async def handle_session(self, websocket: WebSocket, session_id: str):
        """Handle a WebSocket voice session with continuous streaming."""
        await websocket.accept()
        logger.info(f"Voice session started: {session_id}")

        try:
            # Create providers
            stt_provider = create_stt_provider(self.settings)
            llm_provider = create_llm_provider(self.settings)
            tts_provider = create_tts_provider(self.settings)

            # Create pipeline
            pipeline = VoicePipeline(stt_provider, llm_provider, tts_provider)

            # State management
            mode = "idle"
            audio_buffer = bytearray()
            is_recording = False
            processing_task: asyncio.Task | None = None

            # Emit initial idle mode
            await self._send_mode_change(websocket, "idle")

            # Handle incoming messages
            async for message in websocket.iter_text():
                try:
                    data = json.loads(message)
                    event_type = data.get("type")

                    if event_type == "voice_audio_stream_start":
                        # Start of a new recording
                        if mode == "speaking" and processing_task:
                            pipeline.interrupt()
                            processing_task.cancel()
                        
                        audio_buffer.clear()
                        is_recording = True
                        mode = "listening"
                        await self._send_mode_change(websocket, "listening")
                        logger.info(f"Audio stream started for session {session_id}")
                    
                    elif event_type == "voice_audio_chunk":
                        # Accumulate audio chunks while recording
                        if is_recording:
                            audio_data = data.get("audio")
                            if audio_data:
                                audio_bytes = base64.b64decode(audio_data)
                                audio_buffer.extend(audio_bytes)
                    
                    elif event_type == "voice_audio_stream_end":
                        # End of recording - process complete audio
                        is_recording = False
                        logger.info(f"Audio stream ended for session {session_id}, processing {len(audio_buffer)} bytes")
                        
                        if audio_buffer:
                            # Cancel any existing processing to prevent loops
                            if processing_task and not processing_task.done():
                                logger.warning("⚠️ Cancelling previous processing task to prevent loop")
                                pipeline.interrupt()
                                try:
                                    processing_task.cancel()
                                    await asyncio.sleep(0.1)  # Give it time to cancel
                                except Exception as e:
                                    logger.warning(f"Error cancelling task: {e}")
                            
                            # Switch to idle while processing
                            mode = "idle"
                            await self._send_mode_change(websocket, "idle")
                            
                            # Create a copy of audio buffer and clear it immediately
                            audio_to_process = bytes(audio_buffer)
                            audio_buffer.clear()
                            
                            # Process audio in background task (only if not already processing)
                            if processing_task is None or processing_task.done():
                                logger.info(f"🚀 Starting new processing task for {len(audio_to_process)} bytes")
                                processing_task = asyncio.create_task(
                                    self._process_audio(
                                        websocket, pipeline, audio_to_process, session_id
                                    )
                                )
                            else:
                                logger.warning("⚠️ Processing task still running, skipping new request to prevent loop")
                        else:
                            mode = "idle"
                            await self._send_mode_change(websocket, "idle")

                    elif event_type == "interrupt":
                        # User wants to interrupt agent speech
                        logger.info("Interrupt requested by user")
                        pipeline.interrupt()
                        if processing_task and not processing_task.done():
                            processing_task.cancel()
                        mode = "listening"
                        await self._send_mode_change(websocket, "listening")

                    elif event_type == "disconnect":
                        break

                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in message: {message}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    if self._is_connected(websocket):
                        try:
                            await websocket.send_json({"type": "error", "message": str(e)})
                        except Exception:
                            pass

        except Exception as e:
            logger.error(f"Session error: {e}", exc_info=True)
        finally:
            logger.info(f"Voice session ended: {session_id}")

    def _is_connected(self, websocket: WebSocket) -> bool:
        """Check if WebSocket is still connected."""
        try:
            return websocket.client_state.name == "CONNECTED"
        except Exception:
            return False

    async def _process_audio(
        self,
        websocket: WebSocket,
        pipeline: VoicePipeline,
        audio_data: bytes,
        session_id: str,
    ):
        """Process audio through pipeline and send events in real-time."""
        try:
            speaking_mode_sent = False
            
            # Process: STT → LLM → TTS
            async for event in pipeline.process_audio_chunk(audio_data):
                # Check if WebSocket is still connected before each send
                if not self._is_connected(websocket):
                    logger.warning(f"WebSocket closed during processing for session {session_id}")
                    break
                
                # Update mode based on event type
                if isinstance(event, AgentAudioChunk) and not speaking_mode_sent:
                    await self._send_mode_change(websocket, "speaking")
                    speaking_mode_sent = True
                
                # Send event immediately (real-time streaming)
                await self._send_event(websocket, event)
            
            # Processing complete, return to listening mode
            if self._is_connected(websocket):
                await self._send_mode_change(websocket, "listening")
            
        except asyncio.CancelledError:
            logger.info(f"Processing cancelled for session {session_id}")
            if self._is_connected(websocket):
                await self._send_mode_change(websocket, "listening")
        except Exception as e:
            logger.error(f"Error processing audio: {e}", exc_info=True)
            if self._is_connected(websocket):
                try:
                    await websocket.send_json({"type": "error", "message": str(e)})
                    await self._send_mode_change(websocket, "listening")
                except Exception:
                    pass

    async def _send_event(self, websocket: WebSocket, event):
        """Send an event to the client (real-time streaming)."""
        if not self._is_connected(websocket):
            logger.debug("Cannot send event: WebSocket not connected")
            return
        
        try:
            if isinstance(event, TranscriptChunk):
                logger.info(f"📤 Sending TRANSCRIPT: '{event.text[:100]}...'")
                await websocket.send_json(
                    {"type": "transcript", "text": event.text, "final": event.final}
                )
            elif isinstance(event, AgentTextChunk):
                await websocket.send_json(
                    {"type": "agent_text", "text": event.text, "final": event.final}
                )
            elif isinstance(event, AgentAudioChunk):
                if event.audio:
                    # Encode to base64
                    audio_b64 = base64.b64encode(event.audio).decode("ascii")
                    logger.info(f"🔊 Encoding audio: {len(event.audio)} bytes → {len(audio_b64)} base64 chars")
                    
                    # Only split if base64 is >1MB (very rare for single sentences)
                    # Most sentences are <32KB, so we send complete WAV files directly
                    MAX_BASE64_SIZE = 1024 * 1024  # 1MB base64 (~750KB binary)
                    
                    if len(audio_b64) > MAX_BASE64_SIZE:
                        # Very large audio - split into chunks
                        CHUNK_SIZE = 32 * 1024  # 32KB base64 chunks
                        total_chunks = (len(audio_b64) + CHUNK_SIZE - 1) // CHUNK_SIZE
                        
                        for i in range(0, len(audio_b64), CHUNK_SIZE):
                            if not self._is_connected(websocket):
                                logger.warning("❌ WebSocket closed while sending audio chunks")
                                return
                            
                            chunk = audio_b64[i:i + CHUNK_SIZE]
                            is_last = (i + CHUNK_SIZE >= len(audio_b64))
                            is_final = is_last and event.final
                            
                            await websocket.send_json({
                                "type": "agent_audio",
                                "audio": chunk,
                                "final": is_final,
                                "chunk_index": i // CHUNK_SIZE,
                                "total_chunks": total_chunks,
                            })
                        logger.info(f"✅ Sent large audio split into {total_chunks} chunks")
                    else:
                        # Normal case: Send complete WAV file in one message
                        await websocket.send_json({
                            "type": "agent_audio",
                            "audio": audio_b64,
                            "final": event.final,
                        })
                        logger.info(f"✅ Sent complete audio chunk: {len(event.audio)} bytes")
                elif event.final:
                    # Empty final chunk
                    await websocket.send_json(
                        {"type": "agent_audio", "audio": "", "final": True}
                    )
            elif isinstance(event, ModeChangeEvent):
                await websocket.send_json(
                    {"type": "mode_change", "mode": event.mode}
                )
        except Exception as e:
            logger.error(f"Failed to send event: {e}")
            # Don't raise - just log the error

    async def _send_mode_change(self, websocket: WebSocket, mode: str):
        """Send mode change event."""
        if not self._is_connected(websocket):
            logger.debug(f"Cannot send mode change '{mode}': WebSocket not connected")
            return
        
        try:
            await websocket.send_json({"type": "mode_change", "mode": mode})
        except Exception as e:
            logger.warning(f"Failed to send mode change '{mode}': {e}")
