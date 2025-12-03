"""
FastAPI server for Coqui XTTS v2 text-to-speech service.

This server loads the XTTS model on startup and provides an HTTP endpoint
for text-to-speech synthesis.
"""

# Standard library imports
import io
import logging
import os
from pathlib import Path
from typing import Optional

# Third-party imports
import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Patch torch.load to use weights_only=False for XTTS checkpoint loading
# PyTorch 2.6+ defaults to weights_only=True for security, but XTTS checkpoints
# contain custom classes that need to be loaded
_original_torch_load = torch.load


def _patched_torch_load(*args, **kwargs):
    """Patch torch.load to allow loading XTTS checkpoints."""
    if 'weights_only' not in kwargs:
        kwargs['weights_only'] = False
    return _original_torch_load(*args, **kwargs)


torch.load = _patched_torch_load

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="XTTS TTS Service", version="1.0.0")

# Global model variables
xtts_model = None  # Direct XTTS model instance
xtts_config = None
tts_device = None


class TTSRequest(BaseModel):
    """Request model for TTS synthesis."""
    text: str
    voice: str = "en_US-lessac-medium"  # Legacy field (not used)
    speed: float = 1.0  # Playback speed multiplier (not yet implemented)
    language: Optional[str] = None  # Language code (e.g., "en", "es", "fr")
    speaker_id: Optional[str] = None  # Built-in speaker name (e.g., "Daisy Studious", "Gracie Wise")
    # Note: 58 built-in speakers available. See speakers_xtts.pth for full list.


def load_xtts_model():
    """Load the XTTS model on startup."""
    global xtts_model, xtts_config, tts_device
    
    model_path = os.getenv("TTS_MODEL_PATH", "/opt/xtts")
    model_dir = Path(model_path)
    
    if not model_dir.exists():
        raise RuntimeError(f"Model directory not found: {model_path}")
    
    # Check for required files
    required_files = ["config.json", "model.pth"]
    for file in required_files:
        if not (model_dir / file).exists():
            raise RuntimeError(f"Required model file not found: {model_dir / file}")
    
    logger.info(f"Loading XTTS model from: {model_path}")
    logger.info(f"CUDA available: {torch.cuda.is_available()}, devices: {torch.cuda.device_count()}")
    # Determine device
    tts_device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Using device: {tts_device}")
    
    try:
        # Load XTTS model directly using the model class (no Synthesizer wrapper)
        from TTS.tts.models.xtts import Xtts
        from TTS.tts.configs.xtts_config import XttsConfig
        
        # Load config
        config = XttsConfig()
        config.load_json(str(model_dir / "config.json"))
        
        # Initialize model from config
        model_instance = Xtts.init_from_config(config)
        
        # Load checkpoint - pass both directory and file path
        checkpoint_dir = str(model_dir)
        checkpoint_path = str(model_dir / "model.pth")
        vocab_path = str(model_dir / "vocab.json")
        speaker_file_path = str(model_dir / "speakers_xtts.pth")
        
        logger.info(f"Loading checkpoint from: {checkpoint_path}")
        model_instance.load_checkpoint(
            config,
            checkpoint_dir=checkpoint_dir,
            checkpoint_path=checkpoint_path,
            vocab_path=vocab_path,
            speaker_file_path=speaker_file_path,
            use_deepspeed=False
        )
        
        if tts_device == "cuda":
            model_instance.cuda()
        else:
            # CPU optimizations for faster inference
            # Set number of threads for better CPU utilization
            num_threads = int(os.getenv("TORCH_NUM_THREADS", "4"))  # Use 4 threads by default
            torch.set_num_threads(num_threads)
            logger.info(f"CPU mode: Using {num_threads} threads for inference")
            
            # Enable inference mode optimizations
            model_instance.eval()  # Set to evaluation mode
        
        # Store model and config for direct use
        xtts_model = model_instance
        xtts_config = config
        
        logger.info("XTTS model loaded successfully from local path")
        
    except Exception as e:
        logger.error(f"Failed to load XTTS model: {e}", exc_info=True)
        raise


@app.on_event("startup")
async def startup_event():
    """Load the model when the server starts."""
    try:
        load_xtts_model()
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        raise  # Raise to prevent server from starting with broken model


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    if xtts_model is None:
        return {"status": "unhealthy", "error": "Model not loaded"}
    return {
        "status": "healthy",
        "device": tts_device,
        "model_loaded": xtts_model is not None
    }


@app.post("/tts")
async def synthesize_speech(request: TTSRequest):
    """
    Synthesize speech from text.
    
    Returns audio as a streaming WAV file.
    """
    if xtts_model is None or xtts_config is None:
        raise HTTPException(
            status_code=503,
            detail="TTS model not loaded. Check server logs."
        )
    
    if not request.text or not request.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Text cannot be empty"
        )
    
    try:
        logger.info(f"Synthesizing: '{request.text[:50]}...' (language: {request.language or 'en'})")
        
        # XTTS can use either:
        # 1. speaker_wav - reference audio file for voice cloning
        # 2. speaker_id - use a built-in speaker from speakers_xtts.pth (better quality)
        #
        # Use speaker_id from request, or default to a cleaner quality English speaker
        # Available speakers: 'Claribel Dervla', 'Daisy Studious', 'Gracie Wise', 'Ana Florence', etc. (58 total)
        # "Ana Florence" tends to be cleaner/less noisy than "Daisy Studious"
        speaker_id = request.speaker_id or "Ana Florence"  # Default: cleaner quality English speaker
        
        logger.info(f"Using speaker: {speaker_id}")
        
        # Use XTTS model's synthesize method with speaker_id (no reference audio needed)
        # This uses the built-in speaker embeddings for much better quality
        # Enable torch optimizations for faster CPU inference
        with torch.inference_mode():  # Faster than torch.no_grad() for inference
            result = xtts_model.synthesize(
                text=request.text,
                config=xtts_config,
                speaker_wav=None,  # No reference audio needed when using speaker_id
                language=request.language or "en",
                speaker_id=speaker_id
            )
        
        # Handle return value - synthesize() may return tuple (wav, sample_rate) or just wav
        try:
            # synthesize() returns a dict with 'wav' key, or possibly a tuple
            if isinstance(result, dict):
                wav = result.get('wav', result)  # Extract 'wav' from dict
                sample_rate = result.get('sample_rate', 22050)
            elif isinstance(result, tuple):
                wav = result[0]  # Extract audio from tuple
                sample_rate = result[1] if len(result) > 1 else 22050
            else:
                wav = result
                sample_rate = 22050
            
            # Convert PyTorch tensor to numpy array if needed
            logger.info(f"Result type: {type(result)}, wav type: {type(wav)}")
            if isinstance(wav, torch.Tensor):
                logger.info(f"Tensor shape: {wav.shape}, dtype: {wav.dtype}")
                # Move to CPU and convert to numpy
                wav_np = wav.detach().cpu().numpy()
                logger.info(f"After conversion: shape={wav_np.shape}, ndim={wav_np.ndim}")
                wav = wav_np
            elif isinstance(wav, list):
                wav = np.array(wav)
                logger.info(f"List converted: shape={wav.shape}, ndim={wav.ndim}")
            elif not isinstance(wav, np.ndarray):
                wav = np.array(wav)
                logger.info(f"Array converted: shape={wav.shape}, ndim={wav.ndim}")
        except Exception as e:
            logger.error(f"Error processing result: {e}, result type: {type(result)}")
            raise
        
        # Ensure wav is 1D array (soundfile expects 1D for mono, 2D for stereo)
        logger.info(f"Final check - wav.ndim={wav.ndim}, wav.shape={wav.shape}")
        if wav.ndim == 0:
            # Scalar - shouldn't happen but handle it
            logger.error(f"Unexpected scalar wav value: {wav}")
            raise ValueError("Invalid audio output: scalar value")
        elif wav.ndim > 1:
            # Multi-dimensional - flatten or take first channel
            logger.warning(f"Wav has shape {wav.shape}, flattening to 1D")
            wav = wav.flatten()
        elif wav.ndim == 1 and len(wav) == 0:
            # Empty array
            logger.error("Empty audio output from synthesize()")
            raise ValueError("Empty audio output - reference audio may be invalid")
        
        # Ensure float32 dtype for soundfile
        if wav.dtype != np.float32:
            wav = wav.astype(np.float32)
        
        # Normalize audio to reduce noise and prevent clipping
        # Normalize to -1.0 to 1.0 range, but keep it slightly below to avoid clipping
        max_val = np.abs(wav).max()
        if max_val > 0:
            # Normalize to 95% of max to prevent clipping, but don't amplify quiet audio too much
            target_max = 0.95
            if max_val < 0.1:
                # If audio is very quiet, normalize more gently
                wav = wav * (target_max / max_val) * 0.5
            else:
                wav = wav * (target_max / max_val)
        
        # Clip to safe range to prevent any artifacts
        wav = np.clip(wav, -1.0, 1.0)
        
        logger.info(f"Audio shape: {wav.shape}, sample_rate: {sample_rate}, dtype: {wav.dtype}, max: {np.abs(wav).max():.4f}")
        
        # Convert to WAV bytes
        buffer = io.BytesIO()
        sf.write(buffer, wav, sample_rate, format='WAV')
        buffer.seek(0)
        
        logger.info(f"Generated {len(buffer.getvalue())} bytes of audio")
        
        return StreamingResponse(
            io.BytesIO(buffer.getvalue()),
            media_type="audio/wav",
            headers={
                "Content-Disposition": f'attachment; filename="tts_output.wav"'
            }
        )
        
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"TTS synthesis failed: {str(e)}"
        )


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "XTTS TTS Service",
        "version": "1.0.0",
        "model_loaded": xtts_model is not None,
        "device": tts_device,
        "endpoints": {
            "health": "/health",
            "tts": "/tts (POST)"
        }
    }


# Application entry point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5002)
