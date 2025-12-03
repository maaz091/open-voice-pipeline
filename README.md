# Voice Pipeline Service

A complete, production-ready voice pipeline service that provides **Speech-to-Text (STT) → Large Language Model (LLM) → Text-to-Speech (TTS)** functionality via HTTP REST API and WebSocket streaming.

## Features

- 🎤 **Local Whisper STT** - Open-source speech recognition (no API keys needed)
- 🤖 **LLM Integration** - Supports Runpod and custom chat service adapters
- 🔊 **GPU-Accelerated TTS** - Coqui XTTS running on Runpod (RTX 4000 Ada)
- 🔄 **Real-Time Streaming** - WebSocket support for live voice interactions
- 🚀 **Production Ready** - Docker containerized, easy to deploy
- 🔌 **Pluggable Architecture** - Easy to integrate into any application

## Architecture

```
User Audio → Whisper STT → Runpod LLM → Runpod XTTS → Audio Response
```

### Components

1. **STT (Speech-to-Text)**: Local Whisper model (runs in the pipeline container)
2. **LLM (Large Language Model)**: Runpod endpoint (OpenAI-compatible API)
3. **TTS (Text-to-Speech)**: Coqui XTTS on Runpod GPU pod (RTX 4000 Ada)

## Quick Start

### Prerequisites

- Docker & Docker Compose
- 4GB+ RAM (8GB recommended)
- Runpod endpoints configured:
  - LLM endpoint URL
  - XTTS endpoint URL (GPU pod)

### 1. Clone and Configure

```bash
cd voice-pipeline
cp .env.voice.example .env.voice
```

Edit `.env.voice` with your configuration:

```env
# STT Configuration (Whisper - local, no API key needed)
VOICE_STT_PROVIDER=whisper
VOICE_WHISPER_MODEL=small
VOICE_WHISPER_LANGUAGE=en

# LLM Configuration (Runpod)
VOICE_RUNPOD_BASE_URL=https://your-llm-endpoint.runpod.net
VOICE_RUNPOD_MODEL=your-model-name
VOICE_RUNPOD_API_KEY=optional_key

# TTS Configuration (Runpod XTTS)
VOICE_TTS_SERVICE_URL=https://your-xtts-endpoint.runpod.net/tts
VOICE_TTS_SPEAKER_ID=Ana Florence
VOICE_TTS_LANGUAGE=en
VOICE_TTS_SPEED=1.0
```

### 2. Start the Service

```bash
docker compose up --build
```

The service will:
- Download Whisper model on first run (~500MB for "small" model)
- Start the voice pipeline service on port 8001
- Connect to your Runpod LLM and XTTS endpoints

### 3. Test the Service

```bash
# Health check
curl http://localhost:8001/health

# Test complete pipeline
curl -X POST http://localhost:8001/api/voice \
  -F "file=@test_audio.wav" \
  -o response.json
```

## Integration Guide

### Option 1: HTTP REST API (Simple)

**Endpoint:** `POST http://localhost:8001/api/voice`

**Request:**
- Method: `POST`
- Content-Type: `multipart/form-data`
- Body: audio file (WAV, MP3, OGG, FLAC, M4A, WEBM)

**Response:**
```json
{
  "transcript": "User's spoken text",
  "llm_response": "LLM's response text",
  "audio": "base64-encoded-wav-file",
  "audio_format": "wav",
  "sample_rate": 22050,
  "audio_size_bytes": 197720
}
```

#### JavaScript Example

```javascript
async function processVoice(audioFile) {
  const formData = new FormData();
  formData.append('file', audioFile);

  const response = await fetch('http://localhost:8001/api/voice', {
    method: 'POST',
    body: formData
  });

  const result = await response.json();

  // Decode and play audio
  const audioBytes = atob(result.audio);
  const audioArray = new Uint8Array(audioBytes.length);
  for (let i = 0; i < audioBytes.length; i++) {
    audioArray[i] = audioBytes.charCodeAt(i);
  }
  const audioBlob = new Blob([audioArray], { type: 'audio/wav' });
  const audioUrl = URL.createObjectURL(audioBlob);

  const audio = new Audio(audioUrl);
  audio.play();

  return {
    transcript: result.transcript,
    llmResponse: result.llm_response,
    audioUrl: audioUrl
  };
}
```

#### Python Example

```python
import httpx
import base64

def process_voice(audio_file_path):
    """Process audio through the complete voice pipeline."""
    with open(audio_file_path, 'rb') as f:
        files = {'file': f}
        response = httpx.post('http://localhost:8001/api/voice', files=files)
        response.raise_for_status()

    result = response.json()

    # Save audio
    audio_bytes = base64.b64decode(result['audio'])
    with open('output.wav', 'wb') as f:
        f.write(audio_bytes)

    return {
        'transcript': result['transcript'],
        'llm_response': result['llm_response'],
        'audio_file': 'output.wav'
    }
```

### Option 2: WebSocket Streaming (Real-Time)

**Endpoint:** `ws://localhost:8001/ws/session/{session_id}`

#### Connection Flow

1. **Connect** → Server accepts and sends `mode_change: "idle"`
2. **Start Recording** → Send `voice_audio_stream_start`
3. **Send Audio** → Send `voice_audio_chunk` (base64) repeatedly
4. **End Recording** → Send `voice_audio_stream_end`
5. **Receive Events**:
   - `transcript` - STT result
   - `agent_text` - LLM response (streaming)
   - `agent_audio` - TTS audio chunks (complete WAV files)
   - `mode_change` - State changes (idle/listening/speaking)

#### JavaScript Example

```javascript
const ws = new WebSocket('ws://localhost:8001/ws/session/my-session');

ws.onopen = () => {
  console.log('Connected');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch (data.type) {
    case 'mode_change':
      console.log('Mode:', data.mode);
      break;
    case 'transcript':
      console.log('Transcript:', data.text);
      break;
    case 'agent_text':
      console.log('LLM:', data.text);
      break;
    case 'agent_audio':
      if (data.audio && data.final) {
        // Complete WAV file - play immediately
        const audio = new Audio('data:audio/wav;base64,' + data.audio);
        audio.play();
      }
      break;
    case 'error':
      console.error('Error:', data.message);
      break;
  }
};

// Start recording
ws.send(JSON.stringify({ type: 'voice_audio_stream_start' }));

// Send audio chunks (from MediaRecorder)
ws.send(JSON.stringify({
  type: 'voice_audio_chunk',
  audio: base64AudioData
}));

// Stop recording
ws.send(JSON.stringify({ type: 'voice_audio_stream_end' }));

// Interrupt current processing
ws.send(JSON.stringify({ type: 'interrupt' }));
```

See `test-voice.html` for a complete interactive example.

## Configuration

### Environment Variables (.env.voice)

```env
# STT Configuration (Whisper)
VOICE_STT_PROVIDER=whisper
VOICE_WHISPER_MODEL=small          # tiny, base, small, medium, large
VOICE_WHISPER_LANGUAGE=en          # en, es, fr, etc. (None = auto-detect)

# LLM Configuration (Runpod)
VOICE_RUNPOD_BASE_URL=https://your-llm-endpoint.runpod.net
VOICE_RUNPOD_MODEL=your-model-name
VOICE_RUNPOD_API_KEY=optional_key

# TTS Configuration (Runpod XTTS)
VOICE_TTS_SERVICE_URL=https://your-xtts-endpoint.runpod.net/tts
VOICE_TTS_SPEAKER_ID=Ana Florence  # Optional: Daisy Studious, Gracie Wise, etc.
VOICE_TTS_LANGUAGE=en
VOICE_TTS_SPEED=1.0
```

### Whisper Model Sizes

- `tiny` - Fastest, least accurate (~39MB)
- `base` - Good balance (~150MB)
- `small` - Better accuracy (~500MB) **Recommended**
- `medium` - High accuracy (~1.5GB)
- `large` - Best accuracy (~3GB)

### XTTS Speaker IDs

Available speakers include: `Ana Florence`, `Daisy Studious`, `Gracie Wise`, `Claribel Dervla`, and 54 more. See your XTTS service for the full list.

## API Reference

### POST `/api/voice`

Complete voice pipeline endpoint.

**Request:**
- Content-Type: `multipart/form-data`
- Body: `file` (audio file)

**Response:**
```json
{
  "transcript": "string",
  "llm_response": "string",
  "audio": "base64-encoded-string",
  "audio_format": "wav",
  "sample_rate": 22050,
  "audio_size_bytes": 197720
}
```

### POST `/api/stt`

Speech-to-text only.

**Request:**
- Content-Type: `multipart/form-data`
- Body: `file` (audio file)

**Response:**
```json
{
  "text": "transcribed text"
}
```

### POST `/api/tts`

Text-to-speech only.

**Request:**
- Content-Type: `application/json`
- Body:
```json
{
  "text": "text to synthesize",
  "language": "en"
}
```

**Response:**
- Content-Type: `audio/wav`
- Body: WAV audio file

### WebSocket `/ws/session/{session_id}`

Real-time streaming endpoint.

**Client → Server Events:**
- `voice_audio_stream_start` - Start recording
- `voice_audio_chunk` - Send audio chunk (base64)
- `voice_audio_stream_end` - End recording
- `interrupt` - Interrupt current processing

**Server → Client Events:**
- `mode_change` - Mode changed (idle/listening/speaking)
- `transcript` - STT transcription
- `agent_text` - LLM response text (streaming)
- `agent_audio` - TTS audio chunk (base64, complete WAV files)
- `error` - Error message

## Deployment

### Local Development

```bash
docker compose up --build
```

### Production

1. Update CORS settings in `voice_pipeline/app.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

2. Use environment variables for secrets (never commit `.env.voice`)

3. Set up reverse proxy (nginx) if needed

4. Configure SSL/TLS

## Runpod Setup

### XTTS Deployment

The XTTS service runs on a Runpod GPU pod (RTX 4000 Ada). See the XTTS Dockerfile in `docker/xtts/` for deployment details.

**Requirements:**
- Runpod GPU pod with RTX 4000 Ada (or compatible GPU)
- Docker image: `maaz091/xtts-gpu:latest` (or your own)
- Port: 5002
- Environment variables:
  - `COQUI_TOS_AGREED=1`
  - `TTS_MODEL_PATH=/opt/xtts`
  - `TORCH_NUM_THREADS=1`
  - `OMP_NUM_THREADS=1`
  - `MKL_NUM_THREADS=1`

### LLM Deployment

Configure your Runpod LLM endpoint to be OpenAI-compatible. The pipeline uses the OpenAI Python client format.

## Troubleshooting

### Service Not Starting

```bash
# Check logs
docker compose logs voice-pipeline

# Check health
curl http://localhost:8001/health
```

### Whisper Model Download Issues

The Whisper model downloads automatically on first use. If it fails:

1. Check internet connection
2. Verify disk space (500MB+ for "small" model)
3. Check Docker logs for errors

### XTTS Connection Issues

If TTS fails:

1. Verify `VOICE_TTS_SERVICE_URL` is correct
2. Test XTTS endpoint directly:
   ```bash
   curl https://your-xtts-endpoint.runpod.net/health
   ```
3. Check Runpod pod is running and healthy

### LLM Connection Issues

If LLM fails:

1. Verify `VOICE_RUNPOD_BASE_URL` is correct
2. Test LLM endpoint directly
3. Check API key if required
4. Verify model name matches your deployment

### CORS Errors

Update `allow_origins` in `voice_pipeline/app.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Project Structure

```
voice-pipeline/
├── voice_pipeline/          # Main application code
│   ├── stt/                 # Speech-to-text providers
│   │   ├── base.py         # STT provider interface
│   │   └── whisper.py      # Whisper STT implementation
│   ├── llm/                 # LLM providers
│   │   ├── base.py         # LLM provider interface
│   │   ├── runpod.py       # Runpod LLM implementation
│   │   └── chat_service_adapter.py
│   ├── tts/                 # Text-to-speech providers
│   │   ├── base.py         # TTS provider interface
│   │   └── coqui.py        # Coqui XTTS HTTP client
│   ├── transport/           # Communication layer
│   │   ├── websocket.py    # WebSocket handler
│   │   └── dto.py          # Data transfer objects
│   ├── pipeline.py         # Main pipeline orchestration
│   ├── providers.py        # Provider factory functions
│   ├── config.py           # Configuration settings
│   ├── routes.py           # HTTP REST endpoints
│   └── app.py              # FastAPI application
├── docker/                  # Docker configurations
│   └── xtts/               # XTTS service (for reference)
├── docker-compose.yml       # Docker Compose configuration
├── Dockerfile              # Main pipeline Dockerfile
├── pyproject.toml          # Python dependencies
├── .env.voice              # Environment configuration
├── .env.voice.example      # Example environment file
├── test-voice.html         # Interactive WebSocket test client
└── README.md               # This file
```

## License

This project uses:
- **Whisper** - MIT License (OpenAI)
- **Coqui XTTS** - CPML License (see Coqui licensing for commercial use)

## Support

For issues, questions, or contributions, please open an issue on the repository.

---

**Ready to integrate?** Start the service and call `POST /api/voice` with an audio file. That's it! 🚀

