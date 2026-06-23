"""
FarmAI Integration Router
Exposes the endpoints used by integration gateways (like WhatsApp, Baileys, etc.)
"""

import logging
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, File, Form, UploadFile, Request
from pydantic import BaseModel
from typing import Optional

from services.farmai_core import process_farmai_query

logger = logging.getLogger(__name__)

router = APIRouter()

def localize_text_with_gemini(text: str, instruction: str) -> str:
    """
    Local helper to translate/localize text using Gemini with key rotation.
    """
    from services.key_manager import run_with_key_rotation
    
    def _execute_translation(api_key: str) -> dict:
        import google.generativeai as genai
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

    rotation_res = run_with_key_rotation("CHAT", _execute_translation)
    if rotation_res.get("success") and rotation_res.get("result"):
        return rotation_res["result"]["text"]
    else:
        raise RuntimeError("Gemini localization failed on all keys: " + str(rotation_res.get("error_message")))

class IntegrationRequest(BaseModel):
    user_id: str
    source: Optional[str] = "integration"
    message_type: str
    text: Optional[str] = None
    crop: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    image_path: Optional[str] = None
    audio_path: Optional[str] = None

class ClearSessionRequest(BaseModel):
    user_id: str

@router.post("/integration/process")
async def integration_process(payload: IntegrationRequest, request: Request):
    """
    Integration endpoint to process crop disease queries.
    Accepts JSON input and returns structured diagnostic answers.
    """
    try:
        # Validate empty text for text message type
        if payload.message_type == "text" and (not payload.text or not payload.text.strip()):
            return {
                "status": "error",
                "message": "Text message is required for text processing."
            }

        # Validate empty image_path for image and text_image message types
        if payload.message_type in ("image", "text_image") and (not payload.image_path or not payload.image_path.strip()):
            return {
                "status": "error",
                "message": "image_path is required for image processing."
            }

        # Validate coordinate presence for location message type
        if payload.message_type == "location" and (payload.latitude is None or payload.longitude is None):
            return {
                "status": "error",
                "message": "Latitude and longitude are required for location message type."
            }

        base_url = str(request.base_url).rstrip('/')
        result = await process_farmai_query(
            user_id=payload.user_id,
            source=payload.source,
            message_type=payload.message_type,
            text=payload.text,
            crop=payload.crop,
            latitude=payload.latitude,
            longitude=payload.longitude,
            image_path=payload.image_path,
            audio_path=payload.audio_path,
            base_url=base_url,
        )
        return result

    except Exception as exc:
        logger.exception("Exception in /integration/process route: %s", exc)
        return {
            "status": "error",
            "message": "An internal error occurred while processing the request."
        }

@router.post("/integration/process-upload")
async def integration_process_upload(
    request: Request,
    user_id: str = Form(...),
    source: str = Form("upload_test"),
    message_type: str = Form("image"),
    text: Optional[str] = Form(None),
    crop: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    image: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    language_hint: Optional[str] = Form(None),
):
    """
    Convenience endpoint for manual testing that accepts direct image upload via multipart/form-data.
    Saves the file to a temporary uploads folder and calls process_farmai_query.
    """
    try:
        has_audio = audio is not None and getattr(audio, "filename", "") != ""

        if has_audio:
            logger.info("[VOICE DEBUG] Endpoint /integration/process-upload called")
            logger.info(f"[VOICE DEBUG] Audio file received: filename={audio.filename}")
            
            # Read bytes
            audio_bytes = await audio.read()
            audio_size = len(audio_bytes)
            logger.info(f"[VOICE DEBUG] Audio size: {audio_size} bytes")
            
            # Validate format
            filename = audio.filename
            ext = os.path.splitext(filename)[1].lower()
            
            ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".webm", ".m4a", ".mp4"}
            ALLOWED_AUDIO_MIMES = {
                "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3", "audio/ogg",
                "audio/webm", "audio/m4a", "audio/x-m4a", "audio/aac", "video/mp4", "audio/mp4"
            }
            
            if ext not in ALLOWED_AUDIO_EXTENSIONS:
                return {
                    "status": "error",
                    "message": "Unsupported audio format."
                }
                
            mime_type = audio.content_type
            if not mime_type:
                ext_to_mime = {
                    ".wav": "audio/wav",
                    ".mp3": "audio/mpeg",
                    ".ogg": "audio/ogg",
                    ".webm": "audio/webm",
                    ".m4a": "audio/m4a",
                    ".mp4": "audio/mp4"
                }
                mime_type = ext_to_mime.get(ext, "audio/m4a")
            
            if mime_type not in ALLOWED_AUDIO_MIMES:
                mime_type = "audio/m4a"
                
            logger.info(f"[VOICE DEBUG] Audio MIME type: {mime_type}")
            
            # Size limit check
            MAX_AUDIO_SIZE = 8 * 1024 * 1024  # 8 MB
            if audio_size == 0 or audio_size > MAX_AUDIO_SIZE:
                logger.info("[VOICE DEBUG] STT failure: audio file too large or empty")
                return {
                    "status": "error",
                    "message": "Voice samajhne mein masla aa raha hai. Dobara clear audio bhejein.",
                    "stage": "stt_failed",
                    "metadata": {
                        "audio_saved": False,
                        "stt_success": False
                    }
                }
                
            # Ensure static/uploads/audio/ folder exists
            backend_dir = Path(__file__).resolve().parent.parent
            audio_upload_dir = backend_dir / "static" / "uploads" / "audio"
            audio_upload_dir.mkdir(parents=True, exist_ok=True)
            
            safe_audio_filename = f"voice_{uuid.uuid4().hex}{ext}"
            audio_target_path = audio_upload_dir / safe_audio_filename
            
            try:
                with open(audio_target_path, "wb") as f:
                    f.write(audio_bytes)
                logger.info(f"[VOICE DEBUG] Audio saved path: {audio_target_path}")
            except Exception as e:
                logger.exception("Could not save uploaded audio: %s", e)
                return {
                    "status": "error",
                    "message": "Could not save uploaded audio."
                }
                
            # Call existing STT
            logger.info("[VOICE DEBUG] STT started")
            from services.stt_service import transcribe_audio
            stt_result = transcribe_audio(audio_bytes, mime_type, language_hint)
            
            if not stt_result.get("success"):
                logger.info(f"[VOICE DEBUG] STT failure: {stt_result.get('error_type')}")
                return {
                    "status": "error",
                    "message": "Voice samajhne mein masla aa raha hai. Dobara clear audio bhejein.",
                    "stage": "stt_failed",
                    "metadata": {
                        "audio_saved": True,
                        "stt_success": False
                    }
                }
                
            transcript = stt_result.get("transcript", "")
            detected_lang = stt_result.get("language_hint", "ur")
            logger.info("[VOICE DEBUG] STT success: True")
            logger.info(f"[VOICE DEBUG] Transcript length: {len(transcript)}")
            
            if not transcript or not transcript.strip():
                logger.info("[VOICE DEBUG] STT failure: empty transcript")
                return {
                    "status": "error",
                    "message": "Voice samajhne mein masla aa raha hai. Dobara clear audio bhejein.",
                    "stage": "stt_failed",
                    "metadata": {
                        "audio_saved": True,
                        "stt_success": False
                    }
                }

            # Step 3 - Detect Punjabi/Siraiki inside voice-upload branch
            def detect_voice_upload_language(transcript: str, language_hint: str = None) -> str | None:
                hint = str(language_hint or "").lower().strip()

                if hint in ("punjabi", "pa", "panjabi"):
                    return "punjabi"

                if hint in ("siraiki", "seraiki", "saraiki", "skr", "saraki"):
                    return "siraiki"

                text = str(transcript or "").lower()

                siraiki_strong_markers = [
                    "میکوں",
                    "مینکوں",
                    "تیکوں",
                    "تینکوں",
                    "تساں",
                    "اساں",
                    "ساڈا",
                    "ساڈی",
                    "ساڈے",
                    "تہاڈا",
                    "تہاڈی",
                    "تہاڈے",
                    "کیتھاں",
                    "کتھاں",
                    "کڈاں",
                    "کینویں",
                    "کیویں",
                    "تھی رہا",
                    "تھی رہی",
                    "تھی رہے",
                    "تھیوے",
                    "تھیوݨ",
                    "تھیوڻ",
                    "ہن",
                    "پیا ہن",
                    "رہے ہن",
                    "لگدے ہن",
                    "پترے",
                    "پتراں",
                    "لبھدے",
                    "لبھئے",
                    "ڈسوں",
                    "دسو میکوں",
                    "میکوں دسو",
                    "کرنا چاہیدا",
                    "کی کرنا چاہیدا",
                    "پانی ڈیو",
                    "گھٹت",
                    "ڈکھ",
                    "سگدا اے",
                    "سگدی اے",
                ]

                siraiki_phrase_markers = [
                    "میکوں دسو",
                    "تساں دسو",
                    "پتے پیلے تھی",
                    "پتے پیلے تھی رہے",
                    "پتے پیلے تھی رہے ہن",
                    "فصل پیلی تھی رہی",
                    "کپاس دے پتے پیلے تھی",
                    "کنک دے پتے پیلے تھی",
                ]

                punjabi_strong_markers = [
                    "تسی",
                    "تسیں",
                    "مینوں",
                    "مینو",
                    "سانوں",
                    "ساڈا",
                    "ساڈی",
                    "ساڈے",
                    "توانوں",
                    "تہاڈا",
                    "تہاڈی",
                    "تہاڈے",
                    "کداں",
                    "کیداں",
                    "کیتھے",
                    "کتھے",
                    "کی حال",
                    "میں کی کراں",
                    "میں کی کرا",
                    "کی کراں",
                    "کی کرنا اے",
                    "پیلے نے",
                    "لگدے نے",
                    "رہے نے",
                    "نیں",
                    "اے",
                    "ہو سکدا اے",
                    "ہو سکدی اے",
                ]

                punjabi_phrase_markers = [
                    "میری کنک دے پتے",
                    "میری کپاس دے پتے",
                    "کنک دے پتے پیلے نے",
                    "کپاس دے پتے پیلے نے",
                    "فصل دے پتے",
                    "دے پتے پیلے",
                    "تسی دسو",
                    "مینوں دسو",
                    "میں کی کراں",
                ]

                siraiki_score = 0
                punjabi_score = 0

                for marker in siraiki_strong_markers:
                    if marker in text:
                        siraiki_score += 2

                for marker in siraiki_phrase_markers:
                    if marker in text:
                        siraiki_score += 3

                for marker in punjabi_strong_markers:
                    if marker in text:
                        punjabi_score += 2

                for marker in punjabi_phrase_markers:
                    if marker in text:
                        punjabi_score += 3

                if siraiki_score >= 2 and siraiki_score >= punjabi_score:
                    return "siraiki"

                if punjabi_score >= 2:
                    return "punjabi"

                return None

            form_hint_clean = str(language_hint or "").lower().strip()

            # Treat these values as empty/missing
            if form_hint_clean in ("", "none", "null", "undefined"):
                form_hint_clean = ""

            language_detection_source = "stt_fallback"
            language_detection_marker_type = "none"

            if form_hint_clean:
                # 1. Explicit language_hint always wins
                language_detection_source = "explicit_hint"
                if form_hint_clean in ("punjabi", "pa", "panjabi"):
                    input_voice_language = "punjabi"
                elif form_hint_clean in ("siraiki", "seraiki", "saraiki", "skr", "saraki"):
                    input_voice_language = "siraiki"
                elif form_hint_clean in ("urdu", "ur"):
                    input_voice_language = "urdu"
                elif form_hint_clean in ("roman_urdu", "roman-urdu", "roman urdu"):
                    input_voice_language = "roman_urdu"
                elif form_hint_clean in ("english", "en"):
                    input_voice_language = "english"
                else:
                    input_voice_language = form_hint_clean
            else:
                # 2. No language_hint: auto-detect Punjabi/Siraiki from transcript markers
                detected_voice_lang = detect_voice_upload_language(transcript, None)

                if detected_voice_lang in ("punjabi", "siraiki"):
                    input_voice_language = detected_voice_lang
                    language_detection_source = "shahmukhi_marker"
                    language_detection_marker_type = detected_voice_lang
                else:
                    language_detection_source = "stt_fallback"
                    if detected_lang in ("ur", "urdu"):
                        input_voice_language = "urdu"
                    elif detected_lang in ("en", "english"):
                        input_voice_language = "english"
                    elif detected_lang:
                        input_voice_language = detected_lang
                    else:
                        input_voice_language = "urdu"

            # Step 4 - Ask FarmAI to answer in Punjabi/Siraiki without polluting transcript
            pipeline_text = transcript
            if input_voice_language == "punjabi":
                pipeline_text = (
                    transcript
                    + "\n\n[Instruction: Respond in natural Pakistani Punjabi using Shahmukhi/Urdu script where possible. "
                      "Keep the existing required response structure/headings if the pipeline needs them.]"
                )
            elif input_voice_language == "siraiki":
                pipeline_text = (
                    transcript
                    + "\n\n[Instruction: Respond in natural Pakistani Siraiki using Shahmukhi/Urdu script where possible. "
                      "Keep the existing required response structure/headings if the pipeline needs them.]"
                )
                
            # Check for combined image upload
            has_image_for_combined = image is not None and getattr(image, "filename", "") != ""
            
            combined_image_voice = False
            combined_fallback_used = False
            combined_fallback_reason = None
            saved_combined_image_path = None
            message_type_for_core = "text"
            image_path_for_core = None
            image_saved_for_combined = False
            image_used_for_combined = False

            if has_image_for_combined:
                logger.info("[COMBINED DEBUG] image + audio request detected")
                try:
                    logger.info("[COMBINED DEBUG] combined image save started")
                    # Validate extension
                    img_filename = image.filename
                    img_ext = os.path.splitext(img_filename)[1].lower()
                    if img_ext not in (".jpg", ".jpeg", ".png", ".webp"):
                        logger.warning("[COMBINED DEBUG] Unsupported image format for combined mode")
                        raise ValueError("Unsupported image format")

                    # Resolve static/uploads/images/ directory
                    backend_dir = Path(__file__).resolve().parent.parent
                    img_upload_dir = backend_dir / "static" / "uploads" / "images"
                    img_upload_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Generate unique filename
                    img_safe_filename = f"upload_{uuid.uuid4().hex}{img_ext}"
                    img_target_file_path = img_upload_dir / img_safe_filename
                    
                    # Read bytes and save
                    img_bytes = await image.read()
                    with open(img_target_file_path, "wb") as f:
                        f.write(img_bytes)
                    
                    saved_combined_image_path = f"static/uploads/images/{img_safe_filename}"
                    logger.info("[COMBINED DEBUG] combined image save success")
                    
                    combined_image_voice = True
                    image_saved_for_combined = True
                    image_used_for_combined = True
                    message_type_for_core = "text_image"
                    image_path_for_core = saved_combined_image_path
                except Exception as img_exc:
                    logger.exception("Failed to process image in combined mode, falling back: %s", img_exc)
                    combined_image_voice = False
                    combined_fallback_used = True
                    combined_fallback_reason = "image_save_or_validation_failed"
                    image_saved_for_combined = False
                    image_used_for_combined = False
                    message_type_for_core = "text"
                    image_path_for_core = None
                    logger.info("[COMBINED DEBUG] combined fallback used")

            # Send transcript to existing FarmAI core
            logger.info("[VOICE DEBUG] FarmAI process started")
            base_url = str(request.base_url).rstrip('/')
            
            farmai_success = False
            farmai_result = {}
            
            if combined_image_voice:
                try:
                    logger.info("[COMBINED DEBUG] calling FarmAI core with text_image")
                    farmai_result = await process_farmai_query(
                        user_id=user_id,
                        source=source,
                        message_type=message_type_for_core,
                        text=pipeline_text,
                        crop=crop,
                        latitude=latitude,
                        longitude=longitude,
                        image_path=image_path_for_core,
                        audio_path=f"static/uploads/audio/{safe_audio_filename}",
                        base_url=base_url,
                    )
                    farmai_success = farmai_result.get("status") == "success"
                    if farmai_success:
                        logger.info("[COMBINED DEBUG] text_image core success")
                    else:
                        raise RuntimeError("Combined text_image core returned failure status")
                except Exception as core_exc:
                    logger.exception("[COMBINED DEBUG] process_farmai_query failed for text_image, falling back: %s", core_exc)
                    combined_image_voice = False
                    combined_fallback_used = True
                    combined_fallback_reason = "text_image_core_failed"
                    image_saved_for_combined = False
                    image_used_for_combined = False
                    message_type_for_core = "text"
                    image_path_for_core = None
                    logger.info("[COMBINED DEBUG] combined fallback used")

            if not farmai_success:
                try:
                    farmai_result = await process_farmai_query(
                        user_id=user_id,
                        source=source,
                        message_type="text",
                        text=pipeline_text, # Use pipeline_text
                        crop=crop,
                        latitude=latitude,
                        longitude=longitude,
                        image_path=None,
                        audio_path=f"static/uploads/audio/{safe_audio_filename}",
                        base_url=base_url,
                    )
                    farmai_success = farmai_result.get("status") == "success"
                    logger.info(f"[VOICE DEBUG] FarmAI process success: {farmai_success}")
                except Exception as exc:
                    logger.exception("Error in process_farmai_query for voice input: %s", exc)
                    farmai_result = {}
                    farmai_success = False
                    logger.info("[VOICE DEBUG] FarmAI process success: False")
                
            if not farmai_success:
                error_message = farmai_result.get("message", "جواب بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔")
                return {
                    "status": "error",
                    "message": error_message,
                    "stage": "analysis_failed",
                    "metadata": {
                        "audio_saved": True,
                        "stt_success": True,
                        "analysis_success": False
                    }
                }
                
            # Clear pending audio offer so we don't mess up future text requests
            from services.session_memory import update_session
            update_session(user_id, {"pending_audio_offer": False})
            
            # Post-processing localization for Punjabi/Siraiki voice mode
            localization_success = None
            localized_response_language = None
            localization_partial = False
            localization_error_type = None

            if input_voice_language in ("punjabi", "siraiki"):
                logger.info("[LOCALIZATION DEBUG] response localization started")
                logger.info(f"[LOCALIZATION DEBUG] target language: {input_voice_language}")
                
                orig_farmer_response = farmai_result.get("farmer_response", "")
                orig_tts_summary = farmai_result.get("tts_summary", "")
                
                logger.info(f"[LOCALIZATION DEBUG] original farmer_response length: {len(orig_farmer_response)}")
                logger.info(f"[LOCALIZATION DEBUG] original tts_summary length: {len(orig_tts_summary)}")
                
                if input_voice_language == "punjabi":
                    localized_response_language = "punjabi"
                    farmer_prompt = "Translate/localize the following farming advisory into natural Pakistani Punjabi using Shahmukhi/Urdu script. Do not add new facts. Do not remove important safety advice. Keep it clear and farmer-friendly. Return only the localized text."
                    tts_prompt = "Translate/localize the following farming advisory into natural Pakistani Punjabi using Shahmukhi/Urdu script. Do not add new facts. Do not remove important safety advice. Keep it clear and farmer-friendly. Return only the localized text."
                else: # siraiki
                    localized_response_language = "siraiki"
                    farmer_prompt = "Translate/localize the following farming advisory into natural Pakistani Siraiki using Shahmukhi/Urdu script. Do not add new facts. Do not remove important safety advice. Keep it clear and farmer-friendly. Return only the localized text."
                    tts_prompt = "Translate/localize the following farming advisory into natural Pakistani Siraiki using Shahmukhi/Urdu script. Do not add new facts. Do not remove important safety advice. Keep it clear and farmer-friendly. Return only the localized text."
                
                localized_farmer = None
                farmer_failed = False
                farmer_err_msg = ""
                if orig_farmer_response and orig_farmer_response.strip():
                    try:
                        logger.info(f"[VOICE DEBUG] Localizing farmer_response for {input_voice_language}")
                        localized_farmer = localize_text_with_gemini(orig_farmer_response, farmer_prompt)
                    except Exception as e:
                        logger.exception("farmer_response localization failed: %s", e)
                        farmer_failed = True
                        farmer_err_msg = type(e).__name__

                localized_tts = None
                tts_failed = False
                tts_err_msg = ""
                if orig_tts_summary and orig_tts_summary.strip():
                    try:
                        logger.info(f"[VOICE DEBUG] Localizing tts_summary for {input_voice_language}")
                        localized_tts = localize_text_with_gemini(orig_tts_summary, tts_prompt)
                    except Exception as e:
                        logger.exception("tts_summary localization failed: %s", e)
                        tts_failed = True
                        tts_err_msg = type(e).__name__
                elif localized_farmer:
                    fallback_tts = orig_farmer_response
                    if fallback_tts and len(fallback_tts) > 300:
                        fallback_tts = fallback_tts[:300].strip() + "..."
                    try:
                        logger.info(f"[VOICE DEBUG] Localizing fallback tts_summary for {input_voice_language}")
                        localized_tts = localize_text_with_gemini(fallback_tts, tts_prompt)
                    except Exception as e:
                        logger.exception("fallback tts_summary localization failed: %s", e)
                        tts_failed = True
                        tts_err_msg = type(e).__name__

                if localized_farmer:
                    farmai_result["farmer_response"] = localized_farmer
                    logger.info(f"[LOCALIZATION DEBUG] localized farmer_response length: {len(localized_farmer)}")
                else:
                    logger.info("[LOCALIZATION DEBUG] localized farmer_response length: 0")

                if localized_tts:
                    farmai_result["tts_summary"] = localized_tts
                    logger.info(f"[LOCALIZATION DEBUG] localized tts_summary length: {len(localized_tts)}")
                else:
                    logger.info("[LOCALIZATION DEBUG] localized tts_summary length: 0")

                # Resolve overall success state
                if (localized_farmer or not orig_farmer_response.strip()) and (localized_tts or not orig_tts_summary.strip()):
                    localization_success = True
                    logger.info("[LOCALIZATION DEBUG] response localization success/failure: success")
                elif farmer_failed and (localized_tts or not orig_tts_summary.strip()):
                    localization_success = True
                    localization_partial = True
                    logger.info("[LOCALIZATION DEBUG] response localization success/failure: partial success")
                else:
                    localization_success = False
                    localization_error_type = farmer_err_msg or tts_err_msg or "unknown_localization_error"
                    logger.info(f"[LOCALIZATION DEBUG] response localization success/failure: failure ({localization_error_type})")

            # Immediate TTS generation
            tts_text = farmai_result.get("tts_summary")
            if not tts_text or not tts_text.strip():
                tts_text = farmai_result.get("farmer_response")
                
            if tts_text and len(tts_text) > 300 and not farmai_result.get("tts_summary"):
                tts_text = tts_text[:300].strip() + "..."
                
            # Step 5 - Generate TTS with Orus only for Punjabi/Siraiki voice uploads
            if input_voice_language == "punjabi":
                tts_language_hint = "punjabi"
                voice_override = "Orus"
                punjabi_siraiki_voice_mode = True
            elif input_voice_language == "siraiki":
                tts_language_hint = "siraiki"
                voice_override = "Orus"
                punjabi_siraiki_voice_mode = True
            else:
                tts_language_hint = language_hint or detected_lang
                voice_override = None
                punjabi_siraiki_voice_mode = False

            tts_voice_used = voice_override if voice_override else "default"

            logger.info("[VOICE DEBUG] TTS started")
            from services.tts_service import generate_tts_audio
            
            if punjabi_siraiki_voice_mode:
                tts_result = generate_tts_audio(tts_text, tts_language_hint, voice_override=voice_override)
            else:
                tts_result = generate_tts_audio(tts_text, tts_language_hint)
                
            tts_success = tts_result.get("success", False)
            logger.info(f"[VOICE DEBUG] TTS success: {tts_success}")
            
            audio_url = None
            audio_format = None
            audio_mime_type = None
            whatsapp_ready = False
            ogg_success = False
            
            wav_filename = tts_result.get("filename")
            if tts_success and wav_filename:
                wav_path = Path(backend_dir) / "static" / "audio" / wav_filename
                wav_exists = wav_path.is_file()
                wav_size = wav_path.stat().st_size if wav_exists else 0
                logger.info(f"[VOICE DEBUG] WAV file exists: {wav_exists}, size: {wav_size} bytes")
                
                if wav_exists and wav_size > 0:
                    # Attempt OGG OPUS conversion
                    from services.audio_converter import convert_wav_to_ogg_opus
                    try:
                        conv_res = convert_wav_to_ogg_opus(str(wav_path))
                        if conv_res.get("success"):
                            ogg_filename = conv_res["filename"]
                            ogg_path = Path(backend_dir) / "static" / "audio" / ogg_filename
                            ogg_exists = ogg_path.is_file()
                            ogg_size = ogg_path.stat().st_size if ogg_exists else 0
                            
                            if ogg_exists and ogg_size > 0:
                                audio_url = f"{base_url}/static/audio/{ogg_filename}"
                                audio_format = "ogg_opus"
                                audio_mime_type = "audio/ogg"
                                whatsapp_ready = True
                                ogg_success = True
                            else:
                                logger.warning("[VOICE DEBUG] OGG file is empty or missing after conversion.")
                        else:
                            logger.warning(f"[VOICE DEBUG] OGG conversion failed: {conv_res.get('error_message')}")
                    except Exception as e:
                        logger.exception(f"[VOICE DEBUG] Exception in OGG conversion: {e}")
                    
                    logger.info(f"[VOICE DEBUG] OGG conversion success: {ogg_success}")
                    
                    # Fallback to WAV if OGG conversion did not succeed
                    if not ogg_success:
                        audio_url = f"{base_url}/static/audio/{wav_filename}"
                        audio_format = "wav_fallback"
                        audio_mime_type = "audio/wav"
                        whatsapp_ready = False
                else:
                    tts_success = False
            else:
                tts_success = False
                
            audio_url_present = audio_url is not None
            logger.info(f"[VOICE DEBUG] Final audio_url present: {audio_url_present}")
            
            # Resolve raw/effective voice language
            raw_stt_detected_language = detected_lang
            effective_voice_language = input_voice_language or tts_language_hint or raw_stt_detected_language
            if effective_voice_language == "urdu":
                effective_voice_language = "ur"

            # Step 7 - Build metadata for verification
            res_metadata = {
                "audio_saved": True,
                "stt_success": True,
                "analysis_success": True,
                "tts_success": tts_success,
                "voice_reply_generated": tts_success
            }
            if punjabi_siraiki_voice_mode:
                res_metadata.update({
                    "raw_stt_detected_language": raw_stt_detected_language,
                    "input_voice_language": input_voice_language,
                    "tts_language_hint": tts_language_hint,
                    "tts_voice_used": tts_voice_used,
                    "punjabi_siraiki_voice_mode": punjabi_siraiki_voice_mode,
                    "localization_success": localization_success if localization_success is not None else False,
                    "language_detection_source": language_detection_source,
                    "language_detection_marker_type": language_detection_marker_type
                })
                if localization_success:
                    res_metadata["localized_response_language"] = localized_response_language
                if localization_partial:
                    res_metadata["localization_partial"] = True
                if localization_error_type:
                    res_metadata["localization_error_type"] = localization_error_type
            elif input_voice_language in ("urdu", "roman_urdu", "english"):
                res_metadata.update({
                    "input_voice_language": input_voice_language,
                    "tts_language_hint": tts_language_hint,
                    "tts_voice_used": tts_voice_used,
                    "punjabi_siraiki_voice_mode": punjabi_siraiki_voice_mode,
                    "language_detection_source": language_detection_source
                })

            # Add combined image + voice properties to metadata
            if has_image_for_combined:
                res_metadata.update({
                    "combined_image_voice": combined_image_voice,
                    "image_saved": image_saved_for_combined,
                    "image_used": image_used_for_combined,
                    "message_type_used_for_core": message_type_for_core,
                    "combined_fallback_used": combined_fallback_used
                })
                if combined_fallback_reason:
                    res_metadata["combined_fallback_reason"] = combined_fallback_reason
            else:
                res_metadata.update({
                    "combined_image_voice": False,
                    "image_used": False
                })
            
            if tts_success:
                return {
                    "status": "success",
                    "message_type": "voice_response",
                    "input_type": "audio",
                    "transcription": transcript, # Original transcription (Step 4)
                    "detected_language": effective_voice_language,
                    "farmer_response": farmai_result.get("farmer_response"),
                    "tts_summary": farmai_result.get("tts_summary"),
                    "audio_url": audio_url,
                    "audio_format": audio_format,
                    "audio_mime_type": audio_mime_type,
                    "whatsapp_ready": whatsapp_ready,
                    "metadata": res_metadata
                }
            else:
                return {
                    "status": "partial_success",
                    "message_type": "voice_response",
                    "input_type": "audio",
                    "transcription": transcript, # Original transcription (Step 4)
                    "farmer_response": farmai_result.get("farmer_response"),
                    "tts_summary": farmai_result.get("tts_summary") or tts_text,
                    "audio_url": None,
                    "audio_format": None,
                    "audio_mime_type": None,
                    "whatsapp_ready": False,
                    "metadata": res_metadata
                }

        image_processed = False
        image_path_to_pass = None

        has_image = image is not None and getattr(image, "filename", "") != ""

        if has_image:
            # Validate extension
            filename = image.filename
            ext = os.path.splitext(filename)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                return {
                    "status": "error",
                    "message": "Unsupported image format."
                }

            # Resolve static/uploads/images/ directory
            backend_dir = Path(__file__).resolve().parent.parent
            upload_dir = backend_dir / "static" / "uploads" / "images"
            
            try:
                upload_dir.mkdir(parents=True, exist_ok=True)
                
                # Generate unique filename
                safe_filename = f"upload_{uuid.uuid4().hex}{ext}"
                target_file_path = upload_dir / safe_filename
                
                # Read bytes and save
                image_bytes = await image.read()
                with open(target_file_path, "wb") as f:
                    f.write(image_bytes)
                
                image_processed = True
                image_path_to_pass = f"static/uploads/images/{safe_filename}"
            except Exception as e:
                logger.exception("Could not save uploaded image: %s", e)
                return {
                    "status": "error",
                    "message": "Could not save uploaded image."
                }

        # Determine processing parameters based on text/image presence
        if image_processed:
            msg_type = "text_image" if (text and text.strip()) else "image"
        else:
            if text and text.strip():
                msg_type = "text"
            else:
                return {
                    "status": "error",
                    "message": "Please provide text or an image file."
                }

        base_url = str(request.base_url).rstrip('/')
        result = await process_farmai_query(
            user_id=user_id,
            source=source,
            message_type=msg_type,
            text=text,
            crop=crop,
            latitude=latitude,
            longitude=longitude,
            image_path=image_path_to_pass,
            audio_path=None,
            base_url=base_url,
        )

        if image_processed and result.get("status") == "success":
            if "metadata" not in result:
                result["metadata"] = {}
            result["metadata"]["uploaded_image_path"] = image_path_to_pass

        return result

    except Exception as exc:
        logger.exception("Exception in /integration/process-upload route: %s", exc)
        return {
            "status": "error",
            "message": "An internal error occurred while processing the request."
        }


@router.get("/integration/voice/health")
async def integration_voice_health():
    """
    Optional health endpoint for integration voice capabilities.
    """
    import subprocess
    
    # Check STT keys
    stt_available = bool(
        os.getenv("GEMINI_STT_KEY_1") or
        os.getenv("GEMINI_STT_KEY_2") or
        os.getenv("GEMINI_STT_KEY_3") or
        os.getenv("GEMINI_API_KEY")
    )
    
    # Check TTS keys
    tts_available = bool(
        os.getenv("GEMINI_TTS_KEY_1") or
        os.getenv("GEMINI_TTS_KEY_2") or
        os.getenv("GEMINI_TTS_KEY_3") or
        os.getenv("GEMINI_API_KEY")
    )
    
    # Check static uploads audio directory
    backend_dir = Path(__file__).resolve().parent.parent
    audio_upload_dir = backend_dir / "static" / "uploads" / "audio"
    audio_upload_dir_exists = audio_upload_dir.is_dir()
    
    # Check ffmpeg availability
    ffmpeg_available = False
    try:
        res = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
        if res.returncode == 0:
            ffmpeg_available = True
    except Exception:
        pass
        
    return {
        "status": "ok",
        "stt_available": stt_available,
        "tts_available": tts_available,
        "audio_upload_dir_exists": audio_upload_dir_exists,
        "ffmpeg_available": ffmpeg_available,
        "supported_languages": ["urdu", "roman_urdu", "english", "punjabi", "siraiki"],
        "supported_audio_formats": ["wav", "mp3", "ogg", "webm", "m4a", "mp4"],
        "voice_upload_punjabi_siraiki_supported": True,
        "punjabi_voice": "Orus",
        "siraiki_voice": "Orus"
    }

@router.post("/integration/session/clear")
async def clear_integration_session(payload: ClearSessionRequest):
    """
    Clear session memory for the given user_id.
    """
    try:
        from services.session_memory import clear_session
        clear_session(payload.user_id)
        return {
            "status": "success",
            "message": "Session cleared."
        }
    except Exception as exc:
        logger.exception("Exception in /integration/session/clear route: %s", exc)
        return {
            "status": "error",
            "message": "An internal error occurred while clearing session."
        }

@router.get("/integration/audio/health")
async def integration_audio_health():
    """
    Performs real checks on TTS configuration, static folders, and ffmpeg capability.
    """
    import subprocess

    # 1. Check if required dynamic key pools or generic fallback keys are present in env
    tts_env_present = bool(
        os.getenv("GEMINI_TTS_KEY_1") or
        os.getenv("GEMINI_TTS_KEY_2") or
        os.getenv("GEMINI_TTS_KEY_3") or
        os.getenv("GEMINI_API_KEY")
    )

    # 2. Check static directory
    backend_dir = Path(__file__).resolve().parent.parent
    static_audio_dir = backend_dir / "static" / "audio"
    static_audio_dir_exists = static_audio_dir.is_dir()

    # 3. Check ffmpeg availability
    ffmpeg_available = False
    try:
        res = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
        if res.returncode == 0:
            ffmpeg_available = True
    except Exception:
        pass

    # 4. Check OGG OPUS libopus support
    ogg_opus_supported = False
    if ffmpeg_available:
        try:
            res = subprocess.run(["ffmpeg", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
            if "libopus" in res.stdout:
                ogg_opus_supported = True
        except Exception:
            pass

    env_model = os.getenv("GEMINI_TTS_MODEL", "").strip()
    is_audio_capable = False
    if env_model:
        is_audio_capable = "tts" in env_model.lower()
    else:
        is_audio_capable = True

    return {
        "status": "ok",
        "tts_env_present": tts_env_present,
        "tts_env_model": env_model if env_model else "",
        "tts_env_model_is_audio_capable": is_audio_capable,
        "ffmpeg_available": ffmpeg_available,
        "ogg_opus_supported": ogg_opus_supported,
        "static_audio_dir_exists": static_audio_dir_exists
    }
