from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
import logging

from services.tts_service import generate_tts_audio

logger = logging.getLogger(__name__)

router = APIRouter()

class TTSRequest(BaseModel):
    text: str
    language_hint: Optional[str] = None

@router.post("/tts")
async def text_to_speech(payload: TTSRequest, request: Request):
    """
    FastAPI endpoint for standalone text-to-speech conversion.
    
    Receives JSON body:
    {
      "text": "...",
      "language_hint": "urdu" | "roman_urdu" | "english" (optional)
    }
    
    Returns URL of generated audio file served from backend:
    {
      "status": "success",
      "audio_url": "http://<ip>:<port>/static/audio/tts_<uuid>.wav"
    }
    """
    text = payload.text
    lang_hint = payload.language_hint
    
    logger.info("Handling /tts request: text_len=%d, lang_hint=%s", len(text) if text else 0, lang_hint)
    
    # Generate audio using TTS service
    result = generate_tts_audio(text, lang_hint, source="standalone_tts")
    
    if not result.get("success"):
        return {
            "status": "error",
            "message": result.get("message", "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔"),
            "tts_status": result.get("tts_status", {
                "success": False,
                "error_type": result.get("error_type", "unknown_error")
            })
        }
    
    # Build absolute public URL dynamically based on request URL
    filename = result["filename"]
    base_url = str(request.base_url).rstrip('/')
    audio_url = f"{base_url}/static/audio/{filename}"
    
    return {
        "status": "success",
        "audio_url": audio_url,
        "tts_status": result.get("tts_status")
    }
