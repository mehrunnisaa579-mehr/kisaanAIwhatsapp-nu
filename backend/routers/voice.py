import logging
import time
from fastapi import APIRouter, File, Form, UploadFile, Request
from typing import Optional

from services.stt_service import transcribe_audio
from services.gemini_service import generate_safe_tts_summary
from services.tts_service import generate_tts_audio

from agents.input_parser import parse_input
from agents.diagnosis_agent import generate_mock_diagnosis
from agents.context_agent import get_context
from agents.action_planner import plan_actions
from agents.execution_agent import execute_actions
from agents.recovery_agent import apply_recovery
from agents.outcome_agent import format_outcome

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/voice-analyze")
async def voice_analyze(
    request: Request,
    audio: UploadFile = File(...),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    language_hint: Optional[str] = Form(None),
):
    """
    Voice analysis endpoint.
    
    Accepts multipart/form-data:
    - audio: UploadFile, required
    - latitude: optional float
    - longitude: optional float
    - language_hint: optional string
    
    Transcribes audio to text, runs it through the existing 7-agent analysis flow,
    generates TTS audio from the tts_summary, and returns the response.
    """
    try:
        # 1. Audio Validation
        if not audio or getattr(audio, "filename", "") == "":
            return {
                "status": "success",
                "transcript": None,
                "farmer_response": "آواز موصول نہیں ہوئی۔ براہ کرم دوبارہ ریکارڈ کریں۔",
                "tts_summary": "آواز موصول نہیں ہوئی۔ براہ کرم دوبارہ ریکارڈ کریں۔",
                "audio_url": None,
                "voice_status": {
                    "audio_received": False,
                    "transcription_success": False,
                    "analysis_success": False,
                    "tts_success": False,
                    "error_type": "audio_missing"
                },
                "gemini_status": {
                    "used": False,
                    "success": False,
                    "error_type": "audio_missing",
                    "model_used": None,
                    "available_models": [],
                    "tested_models": [],
                    "working_model": None
                }
            }

        audio_bytes = await audio.read()
        audio_size = len(audio_bytes)
        
        if audio_size == 0:
            return {
                "status": "success",
                "transcript": None,
                "farmer_response": "آواز موصول نہیں ہوئی۔ براہ کرم دوبارہ ریکارڈ کریں۔",
                "tts_summary": "آواز موصول نہیں ہوئی۔ براہ کرم دوبارہ ریکارڈ کریں۔",
                "audio_url": None,
                "voice_status": {
                    "audio_received": True,
                    "transcription_success": False,
                    "analysis_success": False,
                    "tts_success": False,
                    "error_type": "audio_missing"
                },
                "gemini_status": {
                    "used": False,
                    "success": False,
                    "error_type": "audio_missing",
                    "model_used": None,
                    "available_models": [],
                    "tested_models": [],
                    "working_model": None
                }
            }

        MAX_AUDIO_SIZE = 8 * 1024 * 1024  # 8 MB
        if audio_size > MAX_AUDIO_SIZE:
            return {
                "status": "success",
                "transcript": None,
                "farmer_response": "آواز بہت لمبی ہے۔ براہ کرم مختصر وائس نوٹ بھیجیں۔",
                "tts_summary": "آواز بہت لمبی ہے۔ براہ کرم مختصر وائس نوٹ بھیجیں۔",
                "audio_url": None,
                "voice_status": {
                    "audio_received": True,
                    "transcription_success": False,
                    "analysis_success": False,
                    "tts_success": False,
                    "error_type": "audio_too_large"
                },
                "gemini_status": {
                    "used": False,
                    "success": False,
                    "error_type": "audio_too_large",
                    "model_used": None,
                    "available_models": [],
                    "tested_models": [],
                    "working_model": None
                }
            }

        # 2. Transcribe Audio
        mime_type = audio.content_type or "audio/m4a"
        trans_res = transcribe_audio(audio_bytes, mime_type, language_hint)
        
        if not trans_res.get("success"):
            error_type = trans_res.get("error_type", "transcription_failed")
            refusal_text = "آواز واضح نہیں۔ براہ کرم دوبارہ صاف آواز میں ریکارڈ کریں۔"
            return {
                "status": "success",
                "transcript": None,
                "farmer_response": refusal_text,
                "tts_summary": refusal_text,
                "audio_url": None,
                "voice_status": {
                    "audio_received": True,
                    "transcription_success": False,
                    "analysis_success": False,
                    "tts_success": False,
                    "error_type": error_type
                },
                "gemini_status": {
                    "used": True,
                    "success": False,
                    "error_type": error_type,
                    "model_used": trans_res.get("model_used"),
                    "available_models": [],
                    "tested_models": [trans_res.get("model_used")] if trans_res.get("model_used") else [],
                    "working_model": None
                }
            }

        transcript = trans_res["transcript"]
        detected_lang = trans_res["language_hint"]

        # 3. Use Existing Analysis Logic (Pipeline)
        try:
            # 1. InputParser
            parsed = parse_input(
                text=transcript,
                crop=None,
                latitude=latitude,
                longitude=longitude,
                image=None,
            )
            
            # Override language_hint with transcribed language hint if valid
            if detected_lang and detected_lang != "unknown":
                parsed["language_hint"] = detected_lang

            # 2. DiagnosisAgent
            diagnosis = generate_mock_diagnosis(parsed)

            # 3. ContextAgent
            context = get_context(parsed, diagnosis)

            # 4. ActionPlannerAgent
            action_chain = plan_actions(parsed, diagnosis, context)

            # 5. ExecutionAgent
            execution_result = execute_actions(action_chain)

            # 6. RecoveryAgent
            recovery_result = apply_recovery(diagnosis, context, execution_result)

            # 7. OutcomeAgent
            outcome = format_outcome(
                parsed, diagnosis, context,
                action_chain, execution_result, recovery_result,
            )
            
            farmer_response = outcome.get("farmer_response") or "آپ کا پیغام موصول ہو گیا ہے۔"
            lang_hint = parsed.get("language_hint", "ur")
            tts_summary = outcome.get("tts_summary") or generate_safe_tts_summary(farmer_response, lang_hint)
            analysis_success = True
            pipeline_error = None
        except Exception as pipe_exc:
            logger.exception("Pipeline error in /voice-analyze: %s", pipe_exc)
            farmer_response = "جواب بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔"
            tts_summary = farmer_response
            analysis_success = False
            pipeline_error = "analysis_failed"
            outcome = {}

        if not analysis_success:
            return {
                "status": "success",
                "transcript": transcript,
                "farmer_response": farmer_response,
                "tts_summary": tts_summary,
                "audio_url": None,
                "voice_status": {
                    "audio_received": True,
                    "transcription_success": True,
                    "analysis_success": False,
                    "tts_success": False,
                    "error_type": pipeline_error
                },
                "gemini_status": {
                    "used": True,
                    "success": False,
                    "error_type": pipeline_error,
                    "model_used": trans_res.get("model_used"),
                    "available_models": [],
                    "tested_models": [trans_res.get("model_used")] if trans_res.get("model_used") else [],
                    "working_model": None
                }
            }

        # 4. Generate TTS Audio for voice response
        tts_res = generate_tts_audio(tts_summary, parsed.get("language_hint"))
        audio_url = None
        tts_success = False
        tts_error_type = None

        if tts_res.get("success"):
            filename = tts_res["filename"]
            base_url = str(request.base_url).rstrip('/')
            audio_url = f"{base_url}/static/audio/{filename}"
            tts_success = True
        else:
            tts_error_type = tts_res.get("error_type", "tts_failed")

        return {
            "status": "success",
            "transcript": transcript,
            "farmer_response": farmer_response,
            "tts_summary": tts_summary,
            "audio_url": audio_url,
            "voice_status": {
                "audio_received": True,
                "transcription_success": True,
                "analysis_success": True,
                "tts_success": tts_success,
                "error_type": tts_error_type
            },
            "tts_error_message": "آواز بنانے میں مسئلہ آ رہا ہے، دوبارہ سننے کے لیے بٹن دبائیں۔" if not tts_success else None,
            "gemini_status": outcome.get("gemini_status"),
            "diagnosis": outcome.get("diagnosis"),
            "action_chain": outcome.get("action_chain"),
            "weather": outcome.get("weather"),
            "irrigation_advice": outcome.get("irrigation_advice"),
            "before_after": outcome.get("before_after"),
            "cost_summary": outcome.get("cost_summary"),
            "agent_logs": outcome.get("agent_logs"),
            "contradictions": outcome.get("contradictions", []),
            "recovery": outcome.get("recovery"),
        }

    except Exception as exc:
        logger.exception("Unexpected error in /voice-analyze: %s", exc)
        return {
            "status": "success",
            "transcript": None,
            "farmer_response": "جواب بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔",
            "tts_summary": "جواب بنانے میں مسئلہ آ رہا ہے، دوبارہ کوشش کریں۔",
            "audio_url": None,
            "voice_status": {
                "audio_received": True,
                "transcription_success": False,
                "analysis_success": False,
                "tts_success": False,
                "error_type": "unknown_error"
            },
            "gemini_status": {
                "used": False,
                "success": False,
                "error_type": "unknown_error",
                "model_used": None,
                "available_models": [],
                "tested_models": [],
                "working_model": None
            }
        }
