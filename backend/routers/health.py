from fastapi import APIRouter
import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "project": "FarmAI",
        "message": "Backend is running",
    }


@router.get("/gemini-status")
async def gemini_status():
    from services.gemini_service import LAST_STATUS, get_available_gemini_models

    from pathlib import Path
    backend_dir = Path(__file__).resolve().parent.parent
    dotenv_path = backend_dir / ".env"
    load_dotenv(dotenv_path=dotenv_path)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    key_loaded = bool(api_key)
    key_length = len(api_key) if key_loaded else 0

    # Live discovery if not run yet
    if not LAST_STATUS["available_generate_content_models"] and key_loaded:
        try:
            models = get_available_gemini_models(api_key)
            LAST_STATUS["key_loaded"] = key_loaded
            LAST_STATUS["key_length"] = key_length
            LAST_STATUS["available_generate_content_models"] = models
            if models:
                env_model = os.getenv("GEMINI_MODEL", "").strip()
                LAST_STATUS["selected_model"] = env_model if env_model else models[0]
        except Exception as e:
            logger.error("Failed to list models in gemini-status route: %s", e)
            LAST_STATUS["last_error_type"] = "invalid_api_key"

    return {
        "key_loaded": key_loaded or LAST_STATUS.get("key_loaded", False),
        "key_length": key_length or LAST_STATUS.get("key_length", 0),
        "selected_model": LAST_STATUS.get("selected_model"),
        "available_generate_content_models": LAST_STATUS.get("available_generate_content_models", []),
        "tested_models": LAST_STATUS.get("tested_models", []),
        "working_model": LAST_STATUS.get("working_model"),
        "last_error_type": LAST_STATUS.get("last_error_type")
    }
