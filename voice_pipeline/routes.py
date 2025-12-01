"""HTTP REST endpoints for modular STT and TTS access."""

import base64
import io

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from voice_pipeline.config import get_settings
from voice_pipeline.pipeline import VoicePipeline
from voice_pipeline.providers import (
    create_llm_provider,
    create_stt_provider,
    create_tts_provider,
)
from voice_pipeline.transport.dto import AgentAudioChunk, AgentTextChunk, TranscriptChunk

router = APIRouter(prefix="/api", tags=["voice"])

settings = get_settings()


@router.post("/stt")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Transcribe audio file to text.

    Accepts an audio file and returns JSON with transcript.
    """
    # Check content type or filename extension
    content_type = file.content_type or ""
    filename = file.filename or ""
    if not (content_type.startswith("audio/") or
            filename.lower().endswith((".wav", ".mp3", ".ogg", ".flac", ".m4a", ".webm"))):
        raise HTTPException(status_code=400, detail="File must be an audio file")

    try:
        # Read audio data
        audio_data = await file.read()
        if not audio_data:
            raise HTTPException(status_code=400, detail="Empty audio file")

        # Create STT provider
        stt_provider = create_stt_provider(settings)

        # Convert to async iterator
        async def audio_chunks():
            yield audio_data

        # Get transcript
        transcripts = []
        async for transcript in stt_provider.stream(audio_chunks()):
            if transcript.final:
                transcripts.append(transcript.text)

        if not transcripts:
            raise HTTPException(status_code=500, detail="No transcript generated")

        return {"text": " ".join(transcripts), "final": True}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT error: {str(e)}")


@router.post("/tts")
async def synthesize_speech(text: str):
    """
    Synthesize text to speech using Coqui XTTS.

    Returns audio as a streaming WAV file.
    """
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        # Create TTS provider
        tts_provider = create_tts_provider(settings)

        # Generate audio
        audio_chunks = []
        async for chunk in tts_provider.stream_speech(text):
            if chunk.audio:
                audio_chunks.append(chunk.audio)

        if not audio_chunks:
            raise HTTPException(status_code=500, detail="No audio generated")

        # Combine chunks
        import io
        audio_bytes = b"".join(audio_chunks)

        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/wav",
            headers={"Content-Disposition": 'attachment; filename="tts_output.wav"'},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)}")


@router.post("/voice")
async def process_voice_pipeline(file: UploadFile = File(...)):
    """
    Complete voice pipeline: Audio → STT → LLM → TTS → Audio
    
    This is the main endpoint that demonstrates the full pipeline.
    Takes an audio file, transcribes it, sends to LLM, and returns synthesized speech.
    
    **Complete Pipeline Flow:**
    1. Audio file → STT (Speech-to-Text) → Transcript
    2. Transcript → LLM → Response text
    3. Response text → TTS (Text-to-Speech) → Audio
    
    **Returns JSON with:**
    - `transcript`: The transcribed text from your audio
    - `llm_response`: The LLM's response text
    - `audio`: Base64-encoded WAV audio file
    - `audio_format`: "wav"
    - `sample_rate`: 22050
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8001/api/voice \\
      -F "file=@my_audio.wav" \\
      -o response.json
    ```
    """
    # Check content type
    content_type = file.content_type or ""
    filename = file.filename or ""
    if not (content_type.startswith("audio/") or
            filename.lower().endswith((".wav", ".mp3", ".ogg", ".flac", ".m4a", ".webm"))):
        raise HTTPException(status_code=400, detail="File must be an audio file")
    
    try:
        # Read audio data
        audio_data = await file.read()
        if not audio_data:
            raise HTTPException(status_code=400, detail="Empty audio file")
        
        # Create providers
        stt_provider = create_stt_provider(settings)
        llm_provider = create_llm_provider(settings)
        tts_provider = create_tts_provider(settings)
        
        # Create pipeline
        pipeline = VoicePipeline(stt_provider, llm_provider, tts_provider)
        
        # Process through pipeline
        transcript = ""
        llm_response = ""
        audio_chunks = []
        
        async for event in pipeline.process_audio_chunk(audio_data):
            if isinstance(event, TranscriptChunk):
                transcript = event.text
            elif isinstance(event, AgentTextChunk):
                llm_response += event.text
            elif isinstance(event, AgentAudioChunk):
                if event.audio:
                    audio_chunks.append(event.audio)
        
        if not audio_chunks:
            raise HTTPException(status_code=500, detail="No audio generated from pipeline")
        
        if not transcript:
            raise HTTPException(status_code=500, detail="No transcript generated from audio")
        
        if not llm_response:
            raise HTTPException(status_code=500, detail="No LLM response generated")
        
        # Combine audio chunks
        audio_bytes = b"".join(audio_chunks)
        
        # Return JSON with all pipeline results + audio
        return {
            "transcript": transcript,
            "llm_response": llm_response,
            "audio": base64.b64encode(audio_bytes).decode("ascii"),
            "audio_format": "wav",
            "sample_rate": 22050,
            "audio_size_bytes": len(audio_bytes),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")
