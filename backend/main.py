from pathlib import Path
from dotenv import load_dotenv

backend_dir = Path(__file__).resolve().parent
dotenv_path = backend_dir / ".env"
load_dotenv(dotenv_path=dotenv_path)

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routers import health, analyze, weather, tts, voice, integration

app = FastAPI(
    title="FarmAI",
    description="AI-powered agricultural assistant for Pakistani farmers",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(analyze.router)
app.include_router(weather.router)
app.include_router(tts.router)
app.include_router(voice.router)
app.include_router(integration.router)

# Ensure static directory exists
STATIC_DIR = backend_dir / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "audio").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── RAG cache initialisation at startup ──────────────────────────────────
@app.on_event("startup")
async def startup_load_rag_cache():
    import logging
    _logger = logging.getLogger("rag_startup")
    try:
        from services.rag_service import initialize_rag_cache
        initialize_rag_cache()
        _logger.info("[RAG] Cache loaded successfully at startup.")
    except Exception as e:
        _logger.warning("[RAG] Failed to load RAG cache at startup: %s. Continuing without RAG.", e)


@app.get("/")
async def root():
    return {
        "project": "FarmAI",
        "status": "running",
        "message": "FarmAI backend is live",
    }
