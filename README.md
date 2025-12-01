# XTTS Model Setup Guide

This guide explains how to set up the Coqui XTTS v2 model for the voice pipeline service.

## Quick Reference

**Common Commands:**
```bash
# Navigate to voice-pipeline directory first
cd voice-pipeline

# Start the service
docker compose up -d xtts

# View logs
docker compose logs -f xtts

# Check health
curl http://localhost:8002/health

# Test TTS
curl -X POST http://localhost:8002/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello world","language":"en"}' \
  --output output.wav

# Restart service (picks up code changes)
docker compose restart xtts
```

## Overview

The XTTS (eXtended Text-to-Speech) model is a high-quality, multilingual TTS model that provides natural-sounding speech synthesis. The model files are pre-downloaded and included in this repository to avoid:
- Long download times during Docker builds
- License acceptance prompts in non-interactive environments
- Network issues during container startup

## Model Files

The XTTS model must be placed in `docker/xtts/model/` (relative to `voice-pipeline/`), but **this entire folder is git‑ignored and not stored in the repository**.

You need to download the model locally (see “Initial Setup”) and copy these files into `docker/xtts/model/`:

- `config.json` - Model configuration
- `model.pth` - Main model weights (~1.8 GB)
- `speakers_xtts.pth` - Speaker embeddings
- `vocab.json` - Vocabulary file
- `hash.md5` - Model integrity hash
- `tos_agreed.txt` - License acceptance confirmation

**Total size (local only):** ~1.9 GB

## Initial Setup (One-Time)

If you need to download the model yourself (e.g., if it's missing or corrupted):

### Prerequisites

1. **Python 3.9, 3.10, or 3.11** (XTTS 0.22.0 requires Python < 3.12)
2. **Microsoft Visual Studio Build Tools** (for compiling C++ extensions on Windows)
3. **Virtual environment** (recommended)

### Windows Setup

1. **Install Visual Studio Build Tools:**
   - Download from: https://visualstudio.microsoft.com/downloads/
   - Select "Build Tools for Visual Studio"
   - Install with "Desktop development with C++" workload

2. **Create a virtual environment with Python 3.11:**
   ```cmd
   py -3.11 -m venv xtts-env
   xtts-env\Scripts\activate
   ```

3. **Open x64 Native Tools Command Prompt:**
   - Search for "x64 Native Tools Command Prompt for VS" in Start menu
   - This ensures the 64-bit compiler is available

4. **Navigate to your project directory and activate the virtual environment:**
   ```cmd
   cd path\to\your\project
   xtts-env\Scripts\activate
   ```

5. **Install TTS with correct dependencies:**
   ```cmd
   pip install "transformers==4.35.2"
   pip install "TTS==0.22.0"
   ```
   
   **Important:** Install `transformers==4.35.2` BEFORE installing TTS, as TTS 0.22.0 requires this specific version. Newer versions of transformers are incompatible.
   
   **Note:** This will take 10-20 minutes as it compiles C++ extensions.

6. **Download the model:**
   ```cmd
   python -c "from TTS.api import TTS; tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2', gpu=False)"
   ```
   
   When prompted:
   - Read the CPML license terms
   - Type `y` to accept the license
   - Wait for download to complete (~1.8 GB, 15-30 minutes depending on connection)
   - Press `Ctrl+C` after the model loads (you may see an error about transformers - this is expected and will be fixed in Docker)

7. **Copy model to repository:**
   ```cmd
   cd voice-pipeline
   mkdir docker\xtts\model
   xcopy /E /I "%LOCALAPPDATA%\tts\tts_models--multilingual--multi-dataset--xtts_v2" "docker\xtts\model"
   ```

### Linux/macOS Setup

1. **Create virtual environment:**
   ```bash
   python3.11 -m venv xtts-env
   source xtts-env/bin/activate
   ```

2. **Install TTS with correct dependencies:**
   ```bash
   pip install "transformers==4.35.2"
   pip install "TTS==0.22.0"
   ```
   
   **Important:** Install `transformers==4.35.2` BEFORE installing TTS, as TTS 0.22.0 requires this specific version.

3. **Download the model:**
   ```bash
   python -c "from TTS.api import TTS; tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2', gpu=False)"
   ```
   
   Accept the license when prompted.

4. **Copy model to repository:**
   ```bash
   cd voice-pipeline
   mkdir -p docker/xtts/model
   cp -r ~/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2/* docker/xtts/model/
   ```

## License

The XTTS model is licensed under the **CPML (Coqui Public Model License)**. By using this model, you agree to:

- **Non-commercial use:** Free for non-commercial projects
- **Commercial use:** Requires a commercial license from Coqui (contact: licensing@coqui.ai)

See: https://coqui.ai/cpml.txt for full terms.

The `tos_agreed.txt` file in the model directory confirms license acceptance.

## Docker Usage

Once the model is in `docker/xtts/model/` (relative to voice-pipeline/), the Docker container will:

1. Copy the model into the container at build time
2. Set `TTS_MODEL_PATH` environment variable to point to it
3. Load the model on container startup
4. Serve TTS requests via HTTP on port 5002

**No download or license prompts occur in Docker** because the model is pre-downloaded.

### Port Configuration

- **Container port:** 5002 (internal)
- **Host port:** 8002 (external)
- **Access URL:** `http://localhost:8002`

The port mapping is configured in `docker-compose.yml` (in the voice-pipeline/ directory).

### How the Server Works

The XTTS server (`server.py`) uses a direct model loading approach:

1. **Model Loading:** Uses `Xtts.init_from_config()` and `load_checkpoint()` directly instead of the TTS API wrapper, which gives better control over checkpoint paths
2. **PyTorch Compatibility:** Patches `torch.load` to use `weights_only=False` for PyTorch 2.6+ compatibility
3. **Checkpoint Parameters:** Passes `checkpoint_dir`, `checkpoint_path`, `vocab_path`, and `speaker_file_path` explicitly
4. **Inference:** Uses the XTTS model's `inference()` method directly for synthesis

This approach avoids issues with:
- Path resolution in the TTS API wrapper
- PyTorch 2.6+ security restrictions
- Checkpoint directory detection

### File Structure

```
voice-pipeline/              # Project root
├── docker-compose.yml       # Docker Compose configuration
├── docker/
│   └── xtts/
│       ├── Dockerfile       # Container build configuration
│       ├── server.py        # FastAPI TTS server
│       ├── README.md        # This file
│       └── model/           # Pre-downloaded model files
│           ├── config.json
│           ├── model.pth
│           ├── speakers_xtts.pth
│           ├── vocab.json
│           ├── hash.md5
│           └── tos_agreed.txt
└── ...
```

## Verifying Model Integrity

Check that all required files are present:

```bash
# Windows (from voice-pipeline directory)
cd voice-pipeline
dir docker\xtts\model

# Linux/macOS (from voice-pipeline directory)
cd voice-pipeline
ls -lh docker/xtts/model
```

You should see:
- `config.json` (~4 KB)
- `model.pth` (~1.8 GB)
- `speakers_xtts.pth` (~7.7 MB)
- `vocab.json` (~361 KB)
- `hash.md5` (32 bytes)
- `tos_agreed.txt` (63 bytes)

## Troubleshooting

### Model Not Found Error

If the Docker container can't find the model:

1. Verify the model directory exists: `docker/xtts/model/` (from voice-pipeline/)
2. Check that `model.pth` is present and ~1.8 GB
3. Ensure the Dockerfile `COPY` command is correct
4. Rebuild the container (from voice-pipeline/): `docker compose build xtts`

### License Prompt in Docker

If you see license prompts in Docker:

1. Ensure `tos_agreed.txt` exists in the model directory
2. Set `ENV COQUI_TOS_AGREED=1` in the Dockerfile
3. Verify the model was copied correctly during build

### Build Errors on Windows

If `pip install TTS` fails:

1. Ensure you're using **x64 Native Tools Command Prompt** (not regular Developer Command Prompt)
2. Verify Python 3.9-3.11 (not 3.12+)
3. Check that Visual Studio Build Tools are installed with C++ workload
4. Try: `pip install wheel` first, then install transformers before TTS:
   ```cmd
   pip install "transformers==4.35.2"
   pip install "TTS==0.22.0"
   ```

### ImportError: cannot import name 'BeamSearchScorer' from 'transformers'

This error occurs when using an incompatible version of transformers:

**Solution:** Install `transformers==4.35.2` before installing TTS:
```cmd
pip install "transformers==4.35.2"
pip install "TTS==0.22.0"
```

### PyTorch weights_only Error in Docker

If you see `_pickle.UnpicklingError: Weights only load failed` in Docker logs:

**Solution:** This is already handled in `server.py` by patching `torch.load` to use `weights_only=False`. The patch is applied automatically when the server starts.

If you're still seeing this error:
1. Ensure you're using the latest `server.py` from the repository
2. Check that the volume mount is working: `docker compose -f docker-compose.voice.yml restart xtts`
3. Verify the server.py file has the torch.load patch at the top

### Model Download Fails

If the model download fails:

1. Check internet connection
2. Verify you have ~2 GB free disk space
3. Try downloading again (partial downloads may be cached)
4. Check firewall/proxy settings

### Container Won't Start or Model Won't Load

If the container starts but the model doesn't load:

1. **Check container logs (from voice-pipeline/):**
   ```bash
   cd voice-pipeline
   docker compose logs xtts --tail 50
   ```

2. **Verify model files are in the container:**
   ```bash
   docker compose exec xtts ls -la /opt/xtts/
   ```
   
   You should see all 6 files (config.json, model.pth, speakers_xtts.pth, vocab.json, hash.md5, tos_agreed.txt)

3. **Check if server.py is being updated (volume mount):**
   ```bash
   docker compose exec xtts cat /app/server.py | head -20
   ```
   
   The file should have the `torch.load` patch at the top.

4. **Restart the container to pick up changes:**
   ```bash
   docker compose restart xtts
   ```

5. **If model still won't load, rebuild the container (from voice-pipeline/):**
   ```bash
   cd voice-pipeline
   docker compose build --no-cache xtts
   docker compose up -d xtts
   ```

## Updating the Model

To update to a newer version of XTTS:

1. Follow the download steps above with the new version
2. Replace files in `docker/xtts/model/` (from voice-pipeline/)
3. Update the Dockerfile if model paths changed
4. Rebuild the container (from voice-pipeline/): `docker compose build xtts`

## Model Location Reference

- **Local download (Windows):** `%LOCALAPPDATA%\tts\tts_models--multilingual--multi-dataset--xtts_v2`
- **Local download (Linux):** `~/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2`
- **Local download (macOS):** `~/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2`
- **Repository location:** `docker/xtts/model/` (relative to voice-pipeline/)
- **Docker container:** `/opt/xtts/` (set via `TTS_MODEL_PATH`)

## API Endpoints

The XTTS service exposes the following HTTP endpoints:

### GET `/health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "device": "cpu",
  "model_loaded": true
}
```

### POST `/tts`
Synthesize speech from text.

**Request Body:**
```json
{
  "text": "Hello, this is a test.",
  "language": "en",
  "voice": "en_US-lessac-medium",
  "speed": 1.0
}
```

**Parameters:**
- `text` (required): Text to synthesize
- `language` (optional): Language code (default: "en")
- `voice` (optional): Voice name (default: "en_US-lessac-medium")
- `speed` (optional): Playback speed multiplier (default: 1.0)

**Response:**
- Content-Type: `audio/wav`
- Body: WAV audio file (22.05 kHz sample rate)

### GET `/`
Service information endpoint.

**Response:**
```json
{
  "service": "XTTS TTS Service",
  "version": "1.0.0",
  "model_loaded": true,
  "device": "cpu",
  "endpoints": {
    "health": "/health",
    "tts": "/tts (POST)"
  }
}
```

## Testing the Service

After setting up the model and starting the container:

1. **Check if the service is running (from voice-pipeline/):**
   ```bash
   cd voice-pipeline
   docker compose ps xtts
   ```

2. **Check the logs to verify model loaded (from voice-pipeline/):**
   ```bash
   cd voice-pipeline
   docker compose logs xtts --tail 20
   ```
   
   Look for: `INFO:__main__:XTTS model loaded successfully from local path`

3. **Test the health endpoint:**
   ```bash
   curl http://localhost:8002/health
   ```
   
   Should return: `{"status":"healthy","device":"cpu","model_loaded":true}`

4. **Test TTS synthesis:**
   
   **Windows (PowerShell):**
   ```powershell
   $body = @{
       text = "Hello, this is a test of the text to speech system."
       language = "en"
   } | ConvertTo-Json
   
   Invoke-RestMethod -Uri "http://localhost:8002/tts" `
     -Method Post `
     -ContentType "application/json" `
     -Body $body `
     -OutFile "test_tts.wav"
   ```
   
   **Linux/macOS:**
   ```bash
   curl -X POST http://localhost:8002/tts \
     -H "Content-Type: application/json" \
     -d '{"text":"Hello, this is a test of the text to speech system.","language":"en"}' \
     --output test_tts.wav
   ```
   
   **Windows (curl.exe):**
   ```cmd
   curl.exe -X POST http://localhost:8002/tts ^
     -H "Content-Type: application/json" ^
     -d "{\"text\":\"Hello, this is a test of the text to speech system.\",\"language\":\"en\"}" ^
     --output test_tts.wav
   ```

5. **Play the audio file** to verify it works:
   - Windows: `start test_tts.wav`
   - Linux: `aplay test_tts.wav` or `mpv test_tts.wav`
   - macOS: `afplay test_tts.wav`

## Next Steps

After setting up the model (from voice-pipeline/ directory):

1. Build the Docker container: `docker compose build xtts`
2. Start the service: `docker compose up -d xtts`
3. Wait for model to load (check logs): `docker compose logs -f xtts`
4. Test the TTS endpoint using the commands above

**Important:** All docker compose commands should be run from the `voice-pipeline/` directory, as that is now the project root.

For more information, see the main voice pipeline README.

---

# Integration Guide: Voice Pipeline Service

This section explains how to integrate the voice pipeline service into your application.

## Quick Start

**To integrate into any app:**
1. Start the service: `docker compose up -d`
2. Call `POST /api/voice` with an audio file
3. Get back transcript, LLM response, and audio
4. Use the audio in your app

**No code changes needed in the voice-pipeline** — it's a standalone service that works with any HTTP client.

## Prerequisites

**Required:**
- Docker & Docker Compose installed
- 4GB+ RAM (8GB recommended)
- API keys:
  - Google Gemini API key (for STT)
  - Runpod endpoint URL (for LLM)
  - Optional: Runpod API key

## Step 1: Setup the Service

**1. Clone/Copy the voice-pipeline directory:**
```bash
# The voice-pipeline folder is standalone - just copy it
cp -r voice-pipeline /path/to/your/project/
cd voice-pipeline
```

**2. Configure environment:**
```bash
# Copy example env file (if available) or create .env.voice
# Edit .env.voice with your API keys:
# - VOICE_GEMINI_API_KEY=your_key
# - VOICE_RUNPOD_BASE_URL=your_runpod_url
# - VOICE_RUNPOD_MODEL=your_model
```

**3. Start the service:**
```bash
docker compose up -d
```

**4. Verify it's running:**
```bash
curl http://localhost:8001/health
# Should return: {"status":"healthy","service":"voice-pipeline"}
```

## Step 2: Integration Options

### Option A: Simple HTTP Endpoint (Recommended)

**Endpoint:** `POST http://localhost:8001/api/voice`

**Request:**
- Method: POST
- Content-Type: multipart/form-data
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

#### JavaScript/TypeScript Example

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

// Usage
const input = document.querySelector('input[type="file"]');
input.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (file) {
    const result = await processVoice(file);
    console.log('Transcript:', result.transcript);
    console.log('LLM Response:', result.llmResponse);
  }
});
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

# Usage
result = process_voice('my_audio.wav')
print(f"Transcript: {result['transcript']}")
print(f"LLM Response: {result['llm_response']}")
```

#### cURL Example

```bash
curl -X POST http://localhost:8001/api/voice \
  -F "file=@audio.wav" \
  -o response.json

# Extract and decode audio
cat response.json | jq -r '.audio' | base64 -d > output.wav
```

#### React Example

```jsx
import React, { useState } from 'react';

function VoicePipeline() {
  const [transcript, setTranscript] = useState('');
  const [llmResponse, setLlmResponse] = useState('');
  const [audioUrl, setAudioUrl] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://localhost:8001/api/voice', {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();
      setTranscript(result.transcript);
      setLlmResponse(result.llm_response);

      // Decode and create audio URL
      const audioBytes = atob(result.audio);
      const audioArray = new Uint8Array(audioBytes.length);
      for (let i = 0; i < audioBytes.length; i++) {
        audioArray[i] = audioBytes.charCodeAt(i);
      }
      const audioBlob = new Blob([audioArray], { type: 'audio/wav' });
      const url = URL.createObjectURL(audioBlob);
      setAudioUrl(url);
    } catch (error) {
      console.error('Error processing voice:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input type="file" accept="audio/*" onChange={handleFileUpload} />
      {loading && <p>Processing...</p>}
      {transcript && <p>Transcript: {transcript}</p>}
      {llmResponse && <p>Response: {llmResponse}</p>}
      {audioUrl && (
        <audio controls src={audioUrl}>
          Your browser does not support the audio element.
        </audio>
      )}
    </div>
  );
}

export default VoicePipeline;
```

### Option B: WebSocket for Real-Time Streaming

**Endpoint:** `ws://localhost:8001/ws/session/{session_id}`

#### WebSocket Connection Process

**1. Client Connects:**
```javascript
const ws = new WebSocket('ws://localhost:8001/ws/session/my-session-123');
```

**2. Server Accepts & Initializes:**
- Server accepts the WebSocket connection
- Creates STT, LLM, and TTS providers
- Initializes session state (mode, audio buffer)
- Sends initial mode: `{"type": "mode_change", "mode": "idle"}`

**3. Client Receives Initial State:**
```javascript
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'mode_change') {
        console.log('Mode:', data.mode); // "idle"
    }
};
```

**4. Complete Flow:**
1. Connect to WebSocket → Server accepts → Receives `mode_change: "idle"`
2. Send `voice_audio_stream_start` → Server switches to `listening` mode
3. Send `voice_audio_chunk` (base64 audio) repeatedly → Server accumulates audio
4. Send `voice_audio_stream_end` → Server processes: STT → LLM → TTS
5. Receive events: `transcript`, `agent_text`, `agent_audio`, `mode_change`

**Session States:**
- `idle` - Initial state, no activity
- `listening` - Recording user audio
- `speaking` - Agent is speaking (TTS playback)

**What Happens When You Connect:**
1. **Client connects** → `new WebSocket('ws://localhost:8001/ws/session/{id}')`
2. **Server accepts** → FastAPI accepts connection, creates session
3. **Server initializes** → Creates STT, LLM, TTS providers, initializes state
4. **Server sends** → `{"type": "mode_change", "mode": "idle"}` (initial state)
5. **Server listens** → Waits for client events in a loop
6. **Connection stays open** → Until client disconnects or sends `disconnect` event

**Session ID:**
- Can be any string (e.g., `"user-123"`, `"session-abc"`)
- Used for logging and identification
- Multiple clients can have different session IDs
- No session persistence (each connection is independent)

#### JavaScript WebSocket Example

```javascript
class VoicePipelineWebSocket {
  constructor(sessionId) {
    this.ws = new WebSocket(`ws://localhost:8001/ws/session/${sessionId}`);
    this.audioChunks = [];
    this.setupEventHandlers();
  }

  setupEventHandlers() {
    this.ws.onopen = () => {
      console.log('WebSocket connected');
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      switch (data.type) {
        case 'mode_change':
          console.log('Mode:', data.mode); // idle, listening, speaking
          break;
        case 'transcript':
          console.log('Transcript:', data.text);
          break;
        case 'agent_text':
          console.log('LLM text:', data.text);
          break;
        case 'agent_audio':
          if (data.audio) {
            this.audioChunks.push(data.audio);
          }
          if (data.final) {
            this.playAudio();
          }
          break;
        case 'error':
          console.error('Error:', data.message);
          break;
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  startRecording() {
    this.ws.send(JSON.stringify({ type: 'voice_audio_stream_start' }));
  }

  sendAudioChunk(base64Audio) {
    this.ws.send(JSON.stringify({
      type: 'voice_audio_chunk',
      audio: base64Audio
    }));
  }

  stopRecording() {
    this.ws.send(JSON.stringify({ type: 'voice_audio_stream_end' }));
  }

  interrupt() {
    this.ws.send(JSON.stringify({ type: 'interrupt' }));
  }

  playAudio() {
    // Combine all chunks
    const combinedBase64 = this.audioChunks.join('');
    const audioBytes = atob(combinedBase64);
    const audioArray = new Uint8Array(audioBytes.length);
    for (let i = 0; i < audioBytes.length; i++) {
      audioArray[i] = audioBytes.charCodeAt(i);
    }
    const audioBlob = new Blob([audioArray], { type: 'audio/wav' });
    const audioUrl = URL.createObjectURL(audioBlob);
    
    const audio = new Audio(audioUrl);
    audio.play();
    
    // Clear chunks for next response
    this.audioChunks = [];
  }

  close() {
    this.ws.close();
  }
}

// Usage
const pipeline = new VoicePipelineWebSocket('my-session-id');

// Start recording
pipeline.startRecording();

// Send audio chunks (from MediaRecorder or similar)
// pipeline.sendAudioChunk(base64AudioData);

// Stop recording
pipeline.stopRecording();
```

### Option C: Individual Endpoints

If you need separate STT/TTS functionality:

- `POST /api/stt` - Just transcription
- `POST /api/tts` - Just text-to-speech
- `POST /api/voice` - Complete pipeline

## Step 3: Configuration

**Environment variables (.env.voice):**
```bash
# STT (Gemini)
VOICE_GEMINI_API_KEY=your_key
VOICE_GEMINI_MODEL=gemini-2.5-flash
VOICE_GEMINI_LANGUAGE_CODE=en-US
VOICE_GEMINI_AUDIO_MIME_TYPE=audio/wav

# LLM (Runpod)
VOICE_RUNPOD_BASE_URL=https://your-endpoint.runpod.net
VOICE_RUNPOD_MODEL=your-model-name
VOICE_RUNPOD_API_KEY=optional_key

# TTS (XTTS)
VOICE_TTS_SERVICE_URL=http://xtts:5002/tts
VOICE_TTS_SPEAKER_ID=Ana Florence
VOICE_TTS_LANGUAGE=en
VOICE_TTS_SPEED=1.0
```

## Step 4: Deployment

**For production:**
1. Update CORS settings in `voice_pipeline/app.py` (change `allow_origins=["*"]` to your domain)
2. Use environment variables for secrets (never commit `.env.voice`)
3. Set up reverse proxy (nginx) if needed
4. Configure SSL/TLS

**Docker Compose:**
```bash
# Production
docker compose up -d
```

## Step 5: Testing

**Test the complete pipeline:**
```bash
# Using the test script
python test_pipeline_endpoint.py test_tts.wav

# Or with cURL
curl -X POST http://localhost:8001/api/voice \
  -F "file=@test_tts.wav" \
  -o response.json
```

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
  "text": "transcribed text",
  "language": "en-US"
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
- `disconnect` - Close connection

**Server → Client Events:**
- `mode_change` - Mode changed (idle/listening/speaking)
- `transcript` - STT transcription
- `agent_text` - LLM response text (streaming)
- `agent_audio` - TTS audio chunk (base64)
- `error` - Error message

## Troubleshooting

### Service Not Starting
```bash
# Check logs
docker compose logs voice-pipeline
docker compose logs xtts

# Check health
curl http://localhost:8001/health
curl http://localhost:8002/health
```

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

### Audio Not Playing
- Ensure base64 decoding is correct
- Check audio format (should be WAV, 22050 Hz)
- Verify audio blob is created correctly
- Check browser console for errors

### LLM Not Responding
- Verify `VOICE_RUNPOD_BASE_URL` is correct
- Check Runpod endpoint is accessible
- Verify model name matches your Runpod deployment
- Check logs: `docker compose logs voice-pipeline`

## Summary

**To integrate into any app:**
1. ✅ Start the service: `docker compose up -d`
2. ✅ Call `POST /api/voice` with an audio file
3. ✅ Get back transcript, LLM response, and audio
4. ✅ Use the audio in your app

**The voice-pipeline is a standalone, pluggable service** that requires no modifications to integrate with your application. Just send HTTP requests and handle the responses!


