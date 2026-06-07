import os
import re
import uuid
import wave
import io
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

backend_dir = Path(__file__).resolve().parent.parent
dotenv_path = backend_dir / ".env"
load_dotenv(dotenv_path=dotenv_path)

from services.gemini_service import get_available_gemini_models, classify_gemini_error

logger = logging.getLogger(__name__)

# Constants
STATIC_AUDIO_DIR = backend_dir / "static" / "audio"
DEFAULT_VOICE = "Aoede" # Puck, Charon, Fenrir, Kore, Aoede

def clean_text_for_tts(text: str) -> str:
    """
    Cleans markdown formatting, list indicators, and raw JSON blocks 
    before sending text to the TTS engine.
    """
    if not text:
        return ""
    
    # 1. Clean JSON if accidentally present
    trimmed = text.strip()
    if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
        try:
            data = json.loads(trimmed)
            if isinstance(data, dict):
                # Try common keys for message response
                for key in ["farmer_response", "text", "message", "response"]:
                    if key in data and data[key]:
                        return clean_text_for_tts(str(data[key]))
        except Exception:
            pass

    # Remove inline JSON-like strings
    text = re.sub(r'\{[^{}]*\}', '', text)
    
    # 2. Clean markdown bold/italic/code markers
    text = text.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
    text = text.replace("```", "")
    
    # Remove header markers (e.g., "# Heading" -> "Heading")
    text = re.sub(r'#+\s*', '', text)
    
    # Remove bullet/list markers at the beginning of lines
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
    
    # Remove excessive newlines
    text = re.sub(r'\n+', '\n', text)
    return text.strip()


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    """Converts raw 16-bit linear PCM bytes into standard WAV bytes."""
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        wav_file.setnchannels(1)       # Mono
        wav_file.setsampwidth(2)      # 16-bit (2 bytes per sample)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return wav_io.getvalue()


def generate_tts_audio(text: str, language_hint: str = None) -> dict:
    """
    Generates TTS audio from input text using Gemini API.
    Saves file under static/audio/ and returns a status dict.
    """
    # Clean input text
    cleaned_text = clean_text_for_tts(text)
    if not cleaned_text:
        return {
            "success": False,
            "error_type": "empty_input",
            "message": "آواز بنانے کے لیے متن موجود نہیں۔"
        }

    # Trim to reasonable length if excessively long (e.g. limit to 2000 chars to avoid timeout/quota overload)
    if len(cleaned_text) > 2000:
        cleaned_text = cleaned_text[:2000] + "..."

    from services.key_manager import run_with_key_rotation

    def _execute_tts(api_key: str) -> dict:
        if not api_key:
            return {
                "success": False,
                "error_type": "missing_api_key",
                "message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔"
            }

        # 1. Model Selection
        env_model = os.getenv("GEMINI_TTS_MODEL", "").strip()
        selected_model = None

        if env_model:
            selected_model = env_model
            logger.info("Using configured GEMINI_TTS_MODEL: %s", selected_model)
        else:
            # Auto-discovery
            available_models = get_available_gemini_models(api_key)
            # Priority list of TTS models
            priority_models = [
                "models/gemini-2.5-flash-preview-tts",
                "models/gemini-3.1-flash-tts-preview",
                "models/gemini-2.5-pro-preview-tts",
                "models/gemini-2.5-flash",
                "models/gemini-2.0-flash",
                "gemini-2.5-flash-preview-tts",
                "gemini-3.1-flash-tts-preview",
                "gemini-2.5-flash",
                "gemini-2.0-flash"
            ]
            
            # Clean model names to find matches
            def clean_name(n: str) -> str:
                return n[7:] if n.startswith("models/") else n
                
            normalized_available = {clean_name(m): m for m in available_models}
            
            for p in priority_models:
                p_clean = clean_name(p)
                if p_clean in normalized_available:
                    selected_model = normalized_available[p_clean]
                    break
                    
            if not selected_model and available_models:
                # Fallback to any model in list
                selected_model = available_models[0]
                
        if not selected_model:
            logger.error("No valid Gemini model available for TTS generation.")
            return {
                "success": False,
                "error_type": "model_not_available",
                "message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔"
            }

        # 2. Build instructions prompt based on language_hint or detected language
        active_lang = language_hint
        if not active_lang:
            # Infer language from text
            from utils.helpers import detect_language
            active_lang = detect_language(cleaned_text)

        # Clean language hint
        lang_lower = str(active_lang).lower().strip()
        if lang_lower in ("ur", "urdu"):
            lang_instruction = "Read it with natural Urdu pronunciation."
        elif lang_lower == "roman_urdu":
            lang_instruction = "Read it in Pakistani Roman Urdu style, not English pronunciation."
        elif lang_lower in ("en", "english"):
            lang_instruction = "Read it in natural English pronunciation."
        else:
            lang_instruction = "Transition pronunciation smoothly based on the script used in text."

        system_prompt = (
            "You are a high-quality, natural Text-to-Speech engine.\n"
            "Your only task is to read the provided text clearly, naturally, and fluently.\n"
            "Do not answer the user.\n"
            "Do not summarize.\n"
            "Do not translate.\n"
            "Do not add extra advice.\n"
            "Only speak the provided text.\n\n"
            "Voice style:\n"
            "* Friendly, calm, supportive, and clear.\n"
            "* Suitable for Pakistani farmers.\n"
            "* Slightly slow and easy to understand.\n"
            "* Use natural pauses after headings and sentences.\n\n"
            "Language pronunciation:\n"
            f"* {lang_instruction}\n"
            "* If text mixes Urdu/Roman Urdu/English, transition smoothly without changing the voice awkwardly.\n\n"
            "Formatting cleanup:\n"
            "* Do not read markdown symbols.\n"
            "* Do not read asterisks, hashtags, bullets, or formatting markers.\n"
            "* Clean headings naturally before speaking.\n"
            "* Read abbreviations naturally, such as AI, API, TTS, gTTS.\n"
            "* Do not say 'star star', 'hash', or markdown symbols."
        )

        full_prompt = f"{system_prompt}\n\nText: {cleaned_text}"

        # 3. Call API
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(selected_model)
            
            # Generation config dictionary for audio modalities
            config = {
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {
                            "voice_name": DEFAULT_VOICE
                        }
                    }
                }
            }
            
            logger.info("Generating audio using model: %s, lang: %s", selected_model, active_lang)
            response = model.generate_content(
                full_prompt,
                generation_config=config,
                request_options={"timeout": 30.0}
            )
            
            # Extract audio bytes
            pcm_bytes = None
            if response and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.content and len(candidate.content.parts) > 0:
                    part = candidate.content.parts[0]
                    if hasattr(part, "inline_data") and part.inline_data:
                        pcm_bytes = part.inline_data.data
                        
            if not pcm_bytes:
                logger.error("Model did not return valid inline audio bytes.")
                return {
                    "success": False,
                    "error_type": "empty_response",
                    "message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔"
                }
                
            # Convert PCM to playable WAV
            wav_bytes = pcm_to_wav(pcm_bytes)
            
            # Ensure static/audio directory exists
            os.makedirs(STATIC_AUDIO_DIR, exist_ok=True)
            
            # Save audio file
            filename = f"tts_{uuid.uuid4().hex}.wav"
            file_path = os.path.join(STATIC_AUDIO_DIR, filename)
            with open(file_path, "wb") as f:
                f.write(wav_bytes)
                
            logger.info("Saved generated TTS audio: %s", file_path)
            return {
                "success": True,
                "filename": filename,
                "tts_status": {
                    "success": True,
                    "model_used": selected_model
                }
            }
            
        except Exception as exc:
            err_type, err_msg = classify_gemini_error(exc)
            logger.exception("Error in TTS service API execution: %s", err_msg)
            if err_type in ("quota_or_rate_limit", "invalid_api_key"):
                raise exc
            return {
                "success": False,
                "error_type": err_type,
                "message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔",
                "tts_status": {
                    "success": False,
                    "error_type": err_type
                }
            }

    # Execute with key rotation using the TTS pool
    rotation_res = run_with_key_rotation("TTS", _execute_tts)
    
    if rotation_res.get("success"):
        res = rotation_res["result"]
        # Add rotation tracking to tts_status
        res["tts_status"]["pool"] = rotation_res.get("pool")
        res["tts_status"]["attempts"] = rotation_res.get("attempts")
        res["tts_status"]["key_index_used"] = rotation_res.get("key_index_used")
        return res
    else:
        # Rotation failed completely (all keys exhausted or pool empty)
        return {
            "success": False,
            "error_type": rotation_res.get("error_type", "tts_failed"),
            "message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔",
            "tts_status": {
                "success": False,
                "pool": rotation_res.get("pool"),
                "error_type": rotation_res.get("error_type", "tts_failed"),
                "attempts": rotation_res.get("attempts", []),
                "key_index_used": rotation_res.get("key_index_used", 0)
            }
        }
