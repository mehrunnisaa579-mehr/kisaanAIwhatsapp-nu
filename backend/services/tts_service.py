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


def extract_inline_audio_bytes(response):
    if not response or not getattr(response, "candidates", None):
        return None

    for candidate in response.candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) if content else None

        if not parts:
            continue

        for part in parts:
            inline_data = getattr(part, "inline_data", None)
            if inline_data and getattr(inline_data, "data", None):
                return inline_data.data

    return None


def generate_tts_audio(text: str, language_hint: str = None, voice_override: str = None) -> dict:
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

    # Determine language outside to keep it in scope for final status
    active_lang = language_hint
    if not active_lang:
        # Infer language from text
        from utils.helpers import detect_language
        active_lang = detect_language(cleaned_text)

    selected_voice = voice_override or DEFAULT_VOICE

    def _execute_tts(api_key: str) -> dict:
        if not api_key:
            return {
                "success": False,
                "error_type": "missing_api_key",
                "message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔"
            }

        # 1. Validate GEMINI_TTS_MODEL from environment
        env_model = os.getenv("GEMINI_TTS_MODEL", "").strip()
        if env_model:
            if "tts" not in env_model.lower():
                logger.error("Configured GEMINI_TTS_MODEL is not a TTS model: %s", env_model)
                return {
                    "success": False,
                    "error_type": "invalid_tts_model_config",
                    "message": "Configured GEMINI_TTS_MODEL is not a TTS model.",
                    "tts_status": {
                        "success": False,
                        "error_type": "invalid_tts_model_config",
                        "model_used": env_model
                    }
                }

        # 2. Build instructions prompt based on language_hint or detected language
        # Clean language hint
        lang_lower = str(active_lang).lower().strip()
        if lang_lower in ("ur", "urdu"):
            lang_instruction = "Read it with natural Urdu pronunciation."
        elif lang_lower == "roman_urdu":
            lang_instruction = "Read it in Pakistani Roman Urdu style, not English pronunciation."
        elif lang_lower in ("en", "english"):
            lang_instruction = "Read it in natural English pronunciation."
        elif lang_lower in ("punjabi", "pa", "panjabi"):
            lang_instruction = (
                "Read it in natural Pakistani Punjabi pronunciation. "
                "Use Pakistani Punjabi/Shahmukhi style if the text is in Urdu script. "
                "Do not pronounce it like English. "
                "Keep the tone friendly, clear, and suitable for farmers."
            )
        elif lang_lower in ("siraiki", "seraiki", "saraiki", "skr", "saraki"):
            lang_instruction = (
                "Read it in natural Pakistani Siraiki pronunciation. "
                "Use Pakistani Siraiki/Shahmukhi style if the text is in Urdu script. "
                "Do not pronounce it like English or generic Urdu. "
                "Keep the tone friendly, clear, and suitable for farmers."
            )
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

        # 3. Model Discovery and Selection
        available_models = get_available_gemini_models(api_key)
        
        priority_models = [
            "models/gemini-2.5-flash-preview-tts",
            "models/gemini-2.5-pro-preview-tts",
            "models/gemini-3.1-flash-tts-preview",
            "gemini-2.5-flash-preview-tts",
            "gemini-2.5-pro-preview-tts",
            "gemini-3.1-flash-tts-preview",
        ]
        
        # Build candidate list
        tts_candidate_models = []
        
        # If GEMINI_TTS_MODEL exists and contains "tts", add it first
        if env_model and "tts" in env_model.lower():
            tts_candidate_models.append(env_model)
            
        # Add priority TTS models
        for pm in priority_models:
            tts_candidate_models.append(pm)
            
        # Add available models containing "tts"
        if available_models:
            for m in available_models:
                if "tts" in m.lower():
                    tts_candidate_models.append(m)
                    
        # Remove duplicates while preserving order
        unique_tts_candidates = []
        for m in tts_candidate_models:
            if m not in unique_tts_candidates:
                if "tts" in m.lower():
                    unique_tts_candidates.append(m)
        tts_candidate_models = unique_tts_candidates

        # Step 7: Log candidate models list clearly
        logger.info("TTS candidate models: %s", tts_candidate_models)

        if not tts_candidate_models:
            logger.error("No valid Gemini model available for TTS generation.")
            return {
                "success": False,
                "error_type": "model_not_available",
                "message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔",
                "tts_status": {
                    "success": False,
                    "error_type": "model_not_available",
                    "voice_used": selected_voice,
                    "language_used": active_lang
                }
            }

        # Try up to 3 real TTS models inside the same key attempt
        models_to_attempt = tts_candidate_models[:3]
        models_tried = []
        pcm_bytes = None
        selected_model = None

        for attempt_model in models_to_attempt:
            selected_model = attempt_model
            models_tried.append(selected_model)

            # Step 7: Log trying model
            logger.info("Trying TTS model: %s", selected_model)
            logger.info("TTS active language: %s", active_lang)
            logger.info("TTS cleaned text length: %d", len(cleaned_text))
            logger.info("TTS env model present: %s", bool(env_model))

            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(selected_model)
                
                config = {
                    "response_modalities": ["AUDIO"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {
                                "voice_name": selected_voice
                            }
                        }
                    }
                }
                
                response = model.generate_content(
                    full_prompt,
                    generation_config=config,
                    request_options={"timeout": 30.0}
                )
                
                # Step 4: Extract audio bytes from all candidates and parts
                pcm_bytes = extract_inline_audio_bytes(response)

                if pcm_bytes:
                    # Step 7: Log success
                    logger.info("TTS succeeded with model: %s", selected_model)
                    break
                else:
                    # Step 7: Log warning
                    logger.warning("TTS model returned no inline audio bytes: %s", selected_model)
                    
            except Exception as exc:
                err_type, err_msg = classify_gemini_error(exc)
                logger.warning("TTS attempt failed with model %s: %s", selected_model, err_msg)
                # If quota/invalid key, raise to trigger key rotation
                if err_type in ("quota_or_rate_limit", "invalid_api_key"):
                    raise exc

        if pcm_bytes:
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
            # Step 6: Successful response
            return {
                "success": True,
                "filename": filename,
                "tts_status": {
                    "success": True,
                    "model_used": selected_model,
                    "models_tried": models_tried,
                    "voice_used": selected_voice,
                    "language_used": active_lang
                }
            }

        # Step 5: Correct final failure response when all TTS models fail
        return {
            "success": False,
            "error_type": "no_inline_audio_bytes",
            "message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔",
            "tts_status": {
                "success": False,
                "error_type": "no_inline_audio_bytes",
                "models_tried": models_tried,
                "last_model_used": models_tried[-1] if models_tried else None,
                "voice_used": selected_voice,
                "language_used": active_lang
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
        # Rotation failed completely (all keys exhausted or pool empty) or returned non-rotatable error
        res = rotation_res.get("result")
        if res and isinstance(res, dict):
            if "tts_status" not in res:
                res["tts_status"] = {}
            res["tts_status"]["pool"] = rotation_res.get("pool")
            res["tts_status"]["attempts"] = rotation_res.get("attempts")
            res["tts_status"]["key_index_used"] = rotation_res.get("key_index_used")
            return res

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
