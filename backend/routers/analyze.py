"""
FarmAI — /analyze router
Orchestrates the 7-agent mock pipeline and returns
a structured response to the frontend.
farmer_response is ALWAYS returned and never empty.
"""

import time
import logging
from fastapi import APIRouter, File, Form, UploadFile
from typing import Optional

from agents.input_parser import parse_input
from agents.diagnosis_agent import generate_mock_diagnosis
from agents.context_agent import get_context
from agents.action_planner import plan_actions
from agents.execution_agent import execute_actions
from agents.recovery_agent import apply_recovery
from agents.outcome_agent import format_outcome
from services.gemini_service import generate_safe_tts_summary

logger = logging.getLogger(__name__)

router = APIRouter()

_FALLBACK_FARMER_RESPONSE = (
    "آپ کا پیغام موصول ہو گیا ہے۔ "
    "بہتر مشورے کے لیے فصل کی صاف تصویر یا مزید تفصیل بھیجیں۔"
)


@router.post("/analyze")
async def analyze_crop(
    text: Optional[str] = Form(None),
    crop: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    """
    Main analysis endpoint.

    Accepts multipart/form-data with optional text, crop, coordinates,
    and image. Runs the input through a 7-agent mock pipeline and
    returns a structured JSON response compatible with the frontend.

    farmer_response is guaranteed to always be a non-empty Urdu string.
    """

    try:
        t_total_start = time.perf_counter()
        
        t_parse_start = time.perf_counter()
        # 1. InputParser
        parsed = parse_input(
            text=text,
            crop=crop,
            latitude=latitude,
            longitude=longitude,
            image=image,
        )

        image_bytes = None
        image_mime = None
        if image is not None and getattr(image, "filename", "") != "":
            image_bytes = await image.read()
            image_mime = image.content_type
            logger.info(
                "[Image Debug] filename=%s, content_type=%s, bytes_len=%d",
                image.filename, image.content_type, len(image_bytes) if image_bytes else 0
            )
        else:
            logger.info("[Image Debug] No image received or filename empty (image=%s)", image)

        parsed["image_bytes"] = image_bytes
        parsed["image_mime"] = image_mime
        dt_parse = (time.perf_counter() - t_parse_start) * 1000
        logger.info(f"[Timing] input_parser: {dt_parse:.1f}ms")

        # 2. DiagnosisAgent
        diagnosis = generate_mock_diagnosis(parsed)

        t_weather_start = time.perf_counter()
        # 3. ContextAgent
        context = get_context(parsed, diagnosis)
        dt_weather = (time.perf_counter() - t_weather_start) * 1000
        logger.info(f"[Timing] weather: {dt_weather:.1f}ms")

        # 4. ActionPlannerAgent
        action_chain = plan_actions(parsed, diagnosis, context)

        # 5. ExecutionAgent
        execution_result = execute_actions(action_chain)

        # 6. RecoveryAgent
        recovery_result = apply_recovery(diagnosis, context, execution_result)

        t_gemini_start = time.perf_counter()
        # 7. OutcomeAgent
        outcome = format_outcome(
            parsed, diagnosis, context,
            action_chain, execution_result, recovery_result,
        )
        dt_gemini = (time.perf_counter() - t_gemini_start) * 1000
        logger.info(f"[Timing] gemini: {dt_gemini:.1f}ms")
        
        dt_total = (time.perf_counter() - t_total_start) * 1000
        logger.info(f"[Timing] total_analyze: {dt_total:.1f}ms")

        # Safety: ensure farmer_response is never empty
        farmer_response = outcome.get("farmer_response") or _FALLBACK_FARMER_RESPONSE
        language_hint = parsed.get("language_hint", "ur")
        tts_summary = outcome.get("tts_summary") or generate_safe_tts_summary(farmer_response, language_hint)

        # Build final response — preserves frontend-compatible top-level keys
        return {
            "status": "success",
            "tts_summary": tts_summary,
            "input_summary": {
                "text": parsed.get("text"),
                "crop": parsed.get("crop"),
                "image_received": parsed.get("has_image", False),
                "location_received": parsed.get("has_location", False),
                "language_hint": parsed.get("language_hint", "unknown"),
            },
            "diagnosis": outcome.get("diagnosis"),
            "farmer_response": farmer_response,
            "action_chain": outcome.get("action_chain"),
            "agent_logs": outcome.get("agent_logs"),
            "before_after": outcome.get("before_after"),
            "weather": outcome.get("weather"),
            "irrigation_advice": outcome.get("irrigation_advice"),
            "cost_summary": outcome.get("cost_summary"),
            "contradictions": outcome.get("contradictions", []),
            "recovery": outcome.get("recovery"),
            "gemini_status": outcome.get("gemini_status"),
            "rag_status": outcome.get("rag_status"),
        }

    except Exception as exc:
        logger.exception("Pipeline error in /analyze: %s", exc)
        return {
            "status": "success",
            "input_summary": {
                "text": text,
                "crop": crop,
                "image_received": image is not None,
                "location_received": latitude is not None and longitude is not None,
                "language_hint": "unknown",
            },
            "diagnosis": {},
            "farmer_response": _FALLBACK_FARMER_RESPONSE,
            "tts_summary": generate_safe_tts_summary(_FALLBACK_FARMER_RESPONSE, "ur"),
            "action_chain": [],
            "agent_logs": [],
            "before_after": {},
            "weather": {},
            "irrigation_advice": {"heading": "پانی کا مشورہ", "message": "", "based_on": "weather"},
            "cost_summary": {},
            "contradictions": [],
            "recovery": {"status": "stable", "actions": []},
            "gemini_status": {
                "used": False,
                "success": False,
                "error_type": "unknown_error",
                "model_used": None,
                "available_models": [],
                "tested_models": [],
                "working_model": None
            },
        }

