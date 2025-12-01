FROM python:3.11-slim

# Set environment variables
ENV TTS_MODEL_PATH=/opt/xtts
ENV COQUI_TOS_AGREED=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (including FFmpeg for TorchCodec)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    build-essential \
    ffmpeg \
    && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Install PyTorch (large, but caches well)
RUN pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install transformers (must be before TTS)
RUN pip install --no-cache-dir "transformers==4.35.2"

# Install TTS (will use cached transformers)
RUN pip install --no-cache-dir "TTS==0.22.0"

# Install remaining small packages (including FastAPI for the server)
RUN pip install --no-cache-dir torchcodec soundfile requests fastapi uvicorn

# Create model directory and copy pre-downloaded model
RUN mkdir -p ${TTS_MODEL_PATH} /tmp

# Copy the pre-downloaded model (avoids download and license prompts)
COPY docker/xtts/model ${TTS_MODEL_PATH}/

# Copy server script
COPY docker/xtts/server.py /app/server.py

# Verify model files are present
RUN ls -lh ${TTS_MODEL_PATH} && \
    test -f ${TTS_MODEL_PATH}/model.pth && \
    test -f ${TTS_MODEL_PATH}/config.json && \
    echo "Model files verified"

# Expose TTS service port
EXPOSE 5002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5002/health', timeout=5)" || exit 1

# Run the TTS server
CMD ["python", "server.py"]
