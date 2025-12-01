"""FastAPI application factory for the voice pipeline service."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from voice_pipeline.config import get_settings
from voice_pipeline.routes import router
from voice_pipeline.transport.websocket import VoiceWebSocketServer

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    yield
    # Shutdown


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Voice Pipeline Service",
        version="0.1.0",
        description="Modular STT → LLM → TTS pipeline service",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes
    app.include_router(router)

    # WebSocket endpoint for real-time voice sessions
    websocket_server = VoiceWebSocketServer(settings)
    
    @app.websocket("/ws/session/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        await websocket_server.handle_session(websocket, session_id)

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "service": "voice-pipeline"}

    return app

