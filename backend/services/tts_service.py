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
    Cleans markdown formatting, list indicators, raw JSON blocks, 
    headings, and trailing audio offer messages before sending text 
    to the TTS engine.
    """
    if not text:
        return ""
    
    # 1. Clean JSON if accidentally present
    trimmed = text.strip()
    if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
        try:
            data = json.loads(trimmed)
            if isinstance(data, dict):
                for key in ["farmer_response", "text", "message", "response"]:
                    if key in data and data[key]:
                        return clean_text_for_tts(str(data[key]))
        except Exception:
            pass

    # Remove inline JSON-like strings
    text = re.sub(r'\{[^{}]*\}', '', text)
    
    # Remove banned audio-offer lines by checking line-by-line
    banned_keywords = [
        "audio summary", "voice summary", "آڈیو سمری", "sunna chahtay", "سننا چاہتے",
        "sunao", "hear an audio summary", "audio offer", "summary sunna", "chaunde ho", "chahso", "sunnan chahso",
        "kya aap", "ki tusi", "tusan is"
    ]
    
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        line_lower = line_stripped.lower()
        if any(kw in line_lower for kw in banned_keywords):
            continue
            
        # Remove headings
        headings_pattern = r'(?i)^\s*(ممکنہ مسئلہ|خطرے کی سطح|تجویز کردہ عمل|موسم کا خیال|اگلا قدم|mumkin masla|khatray ki satah|tajweez kardah amal|mosam ka khayal|agla qadam|possible issue|risk level|recommended action|weather note|next step)\s*:?\s*'
        line_stripped = re.sub(headings_pattern, '', line_stripped)
        
        # Clean markdown bold/italic/code markers
        line_stripped = line_stripped.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
        line_stripped = line_stripped.replace("```", "")
        line_stripped = re.sub(r'^#+\s*', '', line_stripped)
        line_stripped = re.sub(r'^\s*[-*+]\s+', '', line_stripped)
        line_stripped = re.sub(r'^\s*\d+[\.\)]\s+', '', line_stripped)
        line_stripped = re.sub(r'^>\s+', '', line_stripped)
        
        final_line = line_stripped.strip()
        if final_line:
            cleaned_lines.append(final_line)
            
    text = " ".join(cleaned_lines)
    
    # Sentence-bound if too long (max 350 characters)
    if len(text) > 350:
        sentences = re.split(r'([۔\.\?!\n])', text)
        reconstructed = []
        current_len = 0
        i = 0
        while i < len(sentences):
            s = sentences[i].strip()
            delim = sentences[i+1].strip() if i + 1 < len(sentences) else ""
            full_sentence = f"{s}{delim}".strip()
            if full_sentence:
                if current_len + len(full_sentence) + 1 <= 350:
                    reconstructed.append(full_sentence)
                    current_len += len(full_sentence) + 1
                else:
                    if not reconstructed:
                        reconstructed.append(full_sentence[:347] + "...")
                    break
            i += 2
        text = " ".join(reconstructed).strip()
        
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


def convert_to_roman_fallback(text: str, lang: str) -> str:
    """
    Converts a short Punjabi or Siraiki summary into easy Roman Punjabi/Siraiki for TTS
    using Gemini model with CHAT key rotation.
    """
    from services.key_manager import run_with_key_rotation
    
    instruction = (
        f"Convert this short {lang.title()} summary into easy Roman {lang.title()} for text-to-speech. "
        "Keep the same meaning. Do not add advice. Do not remove important warning. "
        "Return only the Roman speakable text."
    )
    
    def _execute_roman_fallback(api_key: str) -> dict:
        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        model = genai.GenerativeModel(model_name)
        prompt = f"{instruction}\n\nText:\n{text}"
        response = model.generate_content(prompt, request_options={"timeout": 20.0})
        raw_text = response.text if response and hasattr(response, "text") else ""
        if not raw_text or not raw_text.strip():
            raise ValueError("Empty response from Gemini")
        return {
            "success": True,
            "text": raw_text.strip()
        }
        
    try:
        logger.info("[TTS_FLOW] Requesting Roman fallback translation for language=%s", lang)
        rotation_res = run_with_key_rotation("CHAT", _execute_roman_fallback)
        if rotation_res.get("success") and rotation_res.get("result"):
            return rotation_res["result"]["text"]
    except Exception as exc:
        logger.warning("[TTS_FLOW] Roman fallback translation failed: %s", exc)
    return ""


def generate_tts_audio(text: str, language_hint: str = None, voice_override: str = None, source: str = None) -> dict:
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

    # Determine language outside to keep it in scope for final status
    active_lang = language_hint
    if not active_lang:
        # Infer language from text
        from utils.helpers import detect_language
        active_lang = detect_language(cleaned_text)

    # Logging TTS Flow info (Part 9)
    source_str = source or "unknown"
    lang_str = str(active_lang).lower().strip()
    text_preview = cleaned_text[:120].replace('\n', ' ') if cleaned_text else ""
    logger.info("[TTS_FLOW] source=%s", source_str)
    logger.info("[TTS_FLOW] language_hint=%s", lang_str)
    logger.info("[TTS_FLOW] original_tts_text_preview=%s", text_preview)

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
        
        def build_tts_prompt(text_to_speak: str, lang: str) -> str:
            lang_key = str(lang).lower().strip()
            if lang_key in ("punjabi", "pa", "panjabi"):
                return f"Read this Punjabi text aloud naturally in a Pakistani Punjabi style. Do not translate it to Urdu. Only speak the given text.\n\nText: {text_to_speak}"
            elif lang_key in ("siraiki", "seraiki", "saraiki", "skr", "saraki"):
                return f"Read this Siraiki text aloud naturally in a Pakistani Siraiki style. Do not translate it to Urdu. Only speak the given text.\n\nText: {text_to_speak}"
            elif lang_key == "roman_urdu":
                return f"Read the following Roman Urdu text naturally aloud. Do not translate it, only speak the text.\n\nText: {text_to_speak}"
            else:
                if lang_key in ("ur", "urdu"):
                    lang_instruction = "Read it with natural Urdu pronunciation."
                elif lang_key in ("en", "english"):
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
                return f"{system_prompt}\n\nText: {text_to_speak}"

        # 3. Model Discovery and Selection
        available_models = get_available_gemini_models(api_key)
        
        priority_models = [
            "models/gemini-2.5-flash-preview-tts",
            "models/gemini-3.1-flash-tts-preview",
            "gemini-2.5-flash-preview-tts",
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
                    
        # Remove duplicates while preserving order & filter out PRO models (Part 6)
        unique_tts_candidates = []
        for m in tts_candidate_models:
            if m not in unique_tts_candidates:
                if "pro" in m.lower():
                    continue
                if "tts" in m.lower():
                    unique_tts_candidates.append(m)
        tts_candidate_models = unique_tts_candidates

        # Log candidate models list clearly
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

        # Loop 1: Attempt standard cleaned_text
        for attempt_model in models_to_attempt:
            selected_model = attempt_model
            models_tried.append(selected_model)

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
                
                full_prompt = build_tts_prompt(cleaned_text, active_lang)
                response = model.generate_content(
                    full_prompt,
                    generation_config=config,
                    request_options={"timeout": 30.0}
                )
                
                pcm_bytes = extract_inline_audio_bytes(response)

                if pcm_bytes:
                    logger.info("TTS succeeded with model: %s", selected_model)
                    break
                else:
                    logger.warning("TTS model returned no inline audio bytes: %s", selected_model)
                    
            except Exception as exc:
                err_type, err_msg = classify_gemini_error(exc)
                logger.warning("TTS attempt failed with model %s: %s", selected_model, err_msg)
                # If quota/invalid key, raise to trigger key rotation
                if err_type in ("quota_or_rate_limit", "invalid_api_key"):
                    raise exc

        # Loop 2: If standard text failed and language is Punjabi/Siraiki, try Roman fallback (Part 5)
        is_regional_lang = lang_lower in ("punjabi", "pa", "panjabi", "siraiki", "seraiki", "saraiki", "skr", "saraki")
        if not pcm_bytes and is_regional_lang:
            logger.info("[TTS_FLOW] retry_with_roman_fallback=true")
            roman_text = convert_to_roman_fallback(cleaned_text, active_lang)
            if roman_text and roman_text.strip():
                logger.info("[TTS_FLOW] Retrying TTS with Roman speakable text: %s", roman_text[:120])
                for attempt_model in models_to_attempt:
                    selected_model = attempt_model
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
                        
                        # Use build_tts_prompt with Roman Urdu style rules to synthesis Roman Siraiki/Punjabi characters smoothly
                        full_prompt = build_tts_prompt(roman_text, "roman_urdu")
                        response = model.generate_content(
                            full_prompt,
                            generation_config=config,
                            request_options={"timeout": 30.0}
                        )
                        
                        pcm_bytes = extract_inline_audio_bytes(response)
                        if pcm_bytes:
                            logger.info("TTS succeeded with Roman fallback on model: %s", selected_model)
                            break
                        else:
                            logger.warning("TTS model returned no inline audio bytes for Roman fallback: %s", selected_model)
                            
                    except Exception as exc:
                        err_type, err_msg = classify_gemini_error(exc)
                        logger.warning("TTS Roman fallback attempt failed with model %s: %s", selected_model, err_msg)
                        if err_type in ("quota_or_rate_limit", "invalid_api_key"):
                            raise exc
            else:
                logger.warning("[TTS_FLOW] Roman fallback translation returned empty text")
        else:
            if is_regional_lang or lang_lower in ("ur", "urdu", "roman_urdu", "en", "english"):
                logger.info("[TTS_FLOW] retry_with_roman_fallback=false")

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
    from services.key_manager import run_with_key_rotation
    rotation_res = run_with_key_rotation("TTS", _execute_tts)
    
    if rotation_res.get("success"):
        res = rotation_res["result"]
        # Add rotation tracking to tts_status
        res["tts_status"]["pool"] = rotation_res.get("pool")
        res["tts_status"]["attempts"] = rotation_res.get("attempts")
        res["tts_status"]["key_index_used"] = rotation_res.get("key_index_used")
        logger.info("[TTS_FLOW] result=success reason=none")
        return res
    else:
        # Rotation failed completely (all keys exhausted or pool empty) or returned non-rotatable error
        res = rotation_res.get("result")
        err_type = rotation_res.get("error_type", "tts_failed")
        if res and isinstance(res, dict):
            if "tts_status" not in res:
                res["tts_status"] = {}
            res["tts_status"]["pool"] = rotation_res.get("pool")
            res["tts_status"]["attempts"] = rotation_res.get("attempts")
            res["tts_status"]["key_index_used"] = rotation_res.get("key_index_used")
            logger.info("[TTS_FLOW] result=failure reason=%s", res.get("error_type", err_type))
            return res

        logger.info("[TTS_FLOW] result=failure reason=%s", err_type)
        return {
            "success": False,
            "error_type": err_type,
            "message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔",
            "tts_status": {
                "success": False,
                "pool": rotation_res.get("pool"),
                "error_type": err_type,
                "attempts": rotation_res.get("attempts", []),
                "key_index_used": rotation_res.get("key_index_used", 0)
            }
        }
