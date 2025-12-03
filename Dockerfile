FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including FFmpeg for Whisper)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        ffmpeg \
        && \
    rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml /app/
COPY voice_pipeline /app/voice_pipeline/

# Install dependencies
RUN pip install --no-cache-dir uv && \
    uv pip install --system --compile-bytecode . && \
    pip install --no-cache-dir uvicorn[standard]

# Expose port
EXPOSE 8001

# Run the application
CMD ["uvicorn", "voice_pipeline.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
