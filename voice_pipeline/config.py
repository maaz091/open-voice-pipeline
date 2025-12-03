from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VoicePipelineSettings(BaseSettings):
    """Settings for the voice pipeline service."""

    model_config = SettingsConfigDict(
        env_file=".env.voice",
        env_prefix="VOICE_"
    )

    # Transport
    websocket_path: str = Field(
        default="/ws/session/{session_id}",
        description="Path FastAPI binds for WebSocket sessions.",
    )

    # Providers
    stt_provider: Literal["whisper"] = Field(
        default="whisper", description="Speech-to-text provider (Whisper)."
    )
    tts_provider: Literal["coqui"] = Field(
        default="coqui", description="Text-to-speech provider (Coqui XTTS)."
    )
    llm_provider: Literal["runpod", "chat_service"] = Field(
        default="runpod", description="Default LLM provider key."
    )

    # Whisper STT
    whisper_model: str = Field(
        default="base", description="Whisper model size ('tiny', 'base', 'small', 'medium', 'large')."
    )
    whisper_language: str | None = Field(
        default=None, description="Language code for Whisper (e.g., 'en', 'es', 'fr'). None = auto-detect."
    )

    # LLM adapter
    chat_service_url: str = Field(
        default="http://localhost:8000/api/chat/voice",
        description="Endpoint accepting transcript payloads.",
    )
    chat_service_api_key: str | None = Field(
        default=None, description="Optional client API key for ChatService."
    )

    # Runpod LLM
    runpod_base_url: str | None = Field(
        default=None, description="Runpod API base URL (OpenAI-compatible)."
    )
    runpod_api_key: str | None = Field(
        default=None, description="Runpod API key."
    )
    runpod_model: str = Field(
        default="gpt-4o-mini", description="Runpod model name."
    )

    # TTS (Coqui XTTS)
    tts_service_url: str = Field(
        default="http://xtts:5002/tts",
        description="Coqui XTTS HTTP endpoint address.",
    )
    tts_speaker_id: str | None = Field(
        default=None,
        description="XTTS speaker ID (e.g., 'Ana Florence', 'Daisy Studious'). Uses default if not set."
    )
    tts_language: str = Field(
        default="en", description="Language code for TTS synthesis (e.g., 'en', 'es', 'fr')."
    )
    tts_speed: float = Field(
        default=1.0, description="Playback speed multiplier for TTS (1.0 = normal speed)."
    )

    # File system paths
    temp_dir: Path = Field(
        default=Path("./.tmp"),
        description="Base directory for transient audio buffers if needed.",
    )


def get_settings() -> VoicePipelineSettings:
    """Get the voice pipeline settings instance."""
    return VoicePipelineSettings()
