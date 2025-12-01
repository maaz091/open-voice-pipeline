class VoiceEvent:
    """Base class for voice events."""

    __slots__ = ("type",)

    def __init__(self, type: str):
        self.type = type


class TranscriptChunk(VoiceEvent):
    """Transcript chunk from STT."""

    __slots__ = ("type", "text", "final")

    def __init__(self, text: str, final: bool = False):
        super().__init__("transcript")
        self.text = text
        self.final = final


class AgentTextChunk(VoiceEvent):
    """Text chunk from LLM agent."""

    __slots__ = ("type", "text", "final")

    def __init__(self, text: str, final: bool = False):
        super().__init__("agent_text")
        self.text = text
        self.final = final


class AgentAudioChunk(VoiceEvent):
    """Audio chunk from TTS."""

    __slots__ = ("type", "audio", "final")

    def __init__(self, audio: bytes, final: bool = False):
        super().__init__("agent_audio")
        self.audio = audio
        self.final = final


class ModeChangeEvent(VoiceEvent):
    """Mode change event (listening/speaking/idle)."""

    __slots__ = ("type", "mode")

    def __init__(self, mode: str):
        super().__init__("mode_change")
        self.mode = mode  # "listening", "speaking", or "idle"

