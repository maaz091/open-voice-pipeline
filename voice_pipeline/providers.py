from voice_pipeline.config import VoicePipelineSettings
from voice_pipeline.llm.base import LLMProvider
from voice_pipeline.llm.chat_service_adapter import ChatServiceAdapter
from voice_pipeline.llm.runpod import RunpodLLMProvider
from voice_pipeline.stt.base import SpeechToTextProvider
from voice_pipeline.stt.whisper import WhisperSTTProvider
from voice_pipeline.tts.base import TextToSpeechProvider
from voice_pipeline.tts.coqui import CoquiTTSProvider


def create_stt_provider(settings: VoicePipelineSettings) -> SpeechToTextProvider:
    """Create an STT provider based on configuration."""
    if settings.stt_provider == "whisper":
        return WhisperSTTProvider(settings)
    else:
        raise ValueError(f"Unknown STT provider: {settings.stt_provider}. Supported: 'whisper'")


def create_llm_provider(settings: VoicePipelineSettings) -> LLMProvider:
    """Create an LLM provider based on configuration."""
    if settings.llm_provider == "runpod":
        return RunpodLLMProvider(settings)
    elif settings.llm_provider == "chat_service":
        return ChatServiceAdapter(settings)
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def create_tts_provider(settings: VoicePipelineSettings) -> TextToSpeechProvider:
    """Create a TTS provider based on configuration."""
    if settings.tts_provider == "coqui":
        return CoquiTTSProvider(settings)
    else:
        raise ValueError(f"Unknown TTS provider: {settings.tts_provider}. Supported: 'coqui'")
