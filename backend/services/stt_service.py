import os
import logging
import re
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

backend_dir = Path(__file__).resolve().parent.parent
dotenv_path = backend_dir / ".env"
load_dotenv(dotenv_path=dotenv_path)

from services.gemini_service import get_available_gemini_models, classify_gemini_error

logger = logging.getLogger(__name__)

def transcribe_audio(audio_bytes: bytes, mime_type: str, language_hint: str = None) -> dict:
    """
    Transcribe audio bytes using Gemini API audio understanding capabilities.
    
    Parameters
    ----------
    audio_bytes : bytes
        The raw bytes of the audio file.
    mime_type : str
        The MIME type of the audio file (e.g. audio/m4a, audio/wav, etc.)
    language_hint : str | None
        Optional language style hint.
        
    Returns
    -------
    dict with keys: success, transcript, language_hint, error_type, model_used
    """
    from services.key_manager import run_with_key_rotation

    def _execute_transcribe(api_key: str) -> dict:
        if not api_key:
            return {
                "success": False,
                "transcript": "",
                "language_hint": "unknown",
                "error_type": "missing_api_key",
                "model_used": ""
            }
            
        # Discover available models
        available_models = get_available_gemini_models(api_key)
        
        # Priority list of multimodal models supporting audio
        priority_models = [
            "models/gemini-2.5-flash",
            "models/gemini-2.0-flash",
            "models/gemini-1.5-flash",
            "models/gemini-3.5-flash",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-3.5-flash"
        ]
        
        selected_model = None
        env_model = os.getenv("GEMINI_MODEL", "").strip()
        
        def clean_name(n: str) -> str:
            return n[7:] if n.startswith("models/") else n
            
        normalized_available = {clean_name(m): m for m in available_models}
        
        # Try configured model first if it exists in available models
        if env_model and clean_name(env_model) in normalized_available:
            selected_model = normalized_available[clean_name(env_model)]
            
        if not selected_model:
            for p in priority_models:
                p_clean = clean_name(p)
                if p_clean in normalized_available:
                    selected_model = normalized_available[p_clean]
                    break
                    
        if not selected_model and available_models:
            selected_model = available_models[0]
            
        if not selected_model:
            logger.error("No valid Gemini model available for audio transcription.")
            return {
                "success": False,
                "transcript": "",
                "language_hint": "unknown",
                "error_type": "model_not_available",
                "model_used": ""
            }
            
        logger.info("Transcribing audio: mime=%s, bytes=%d, using model: %s", mime_type, len(audio_bytes), selected_model)
        
        prompt = (
            "You are FarmAI's speech-to-text processor.\n"
            "Your task is only to transcribe the farmer's voice note.\n"
            "Do not answer the farming question.\n"
            "Do not give advice.\n"
            "Return only the clean transcript text.\n\n"
            "Preserve the speaker's original language and dialect style.\n"
            "Do NOT translate Punjabi or Siraiki speech into standard Urdu.\n"
            "Do NOT normalize regional words into Urdu.\n"
            "If the speaker uses Urdu, return Urdu script.\n"
            "If the speaker uses Punjabi, return natural Punjabi using Shahmukhi/Urdu script or the same spoken style, preserving words like 'کی کراں', 'تسی', 'دسو', 'چاہیدا اے', 'ہو رہے نے'.\n"
            "If the speaker uses Siraiki, return natural Siraiki using Shahmukhi/Urdu script or the same spoken style, preserving words like 'تھیندے', 'میکوں', 'کیرے', 'رک واں', 'تساں', 'چاہسو'.\n"
            "If the speaker uses English, return English.\n"
            "If the speaker uses Roman Urdu or Roman Punjabi/Siraiki, preserve the Roman style.\n"
            "If speech is mixed, preserve the dominant style naturally.\n\n"
            "Do not include markdown.\n"
            "Do not include JSON in the transcript.\n"
            "Do not mention Gemini, backend, API, or model.\n"
            "If the audio is completely silent or unclear, reply with 'TRANSCRIPTION_FAILED'."
        )
        
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(selected_model)
            
            audio_part = {
                "mime_type": mime_type,
                "data": audio_bytes
            }
            
            response = model.generate_content([prompt, audio_part], request_options={"timeout": 30.0})
            transcript = response.text.strip() if response and hasattr(response, "text") else ""
            
            # Clean any markdown or wrapping the model might add
            transcript = transcript.replace('**', '').replace('"', '').replace("'", "").strip()
            
            if not transcript or "TRANSCRIPTION_FAILED" in transcript or len(transcript) < 2:
                return {
                    "success": False,
                    "transcript": "",
                    "language_hint": "unknown",
                    "error_type": "unclear_audio",
                    "model_used": selected_model
                }
                
            from utils.helpers import detect_language
            lang_detected = detect_language(transcript)
            
            # Keep consistent with urdu scripts mapping
            if lang_detected in ("urdu", "ur"):
                lang_detected = "ur"
                
            return {
                "success": True,
                "transcript": transcript,
                "language_hint": lang_detected,
                "error_type": None,
                "model_used": selected_model
            }
            
        except Exception as exc:
            err_type, err_msg = classify_gemini_error(exc)
            logger.exception("Audio transcription failed in stt_service: %s", err_msg)
            if err_type in ("quota_or_rate_limit", "invalid_api_key"):
                raise exc
            return {
                "success": False,
                "transcript": "",
                "language_hint": "unknown",
                "error_type": err_type,
                "model_used": selected_model
            }

    # Execute with key rotation using the STT pool
    rotation_res = run_with_key_rotation("STT", _execute_transcribe)
    
    if rotation_res.get("success"):
        return rotation_res["result"]
    else:
        return {
            "success": False,
            "transcript": "",
            "language_hint": "unknown",
            "error_type": rotation_res.get("error_type", "transcription_failed"),
            "model_used": ""
        }
