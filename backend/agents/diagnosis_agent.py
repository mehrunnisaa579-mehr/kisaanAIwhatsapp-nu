"""
FarmAI — DiagnosisAgent
Generates a mock rule-based diagnosis from parsed input.
Will be replaced by Gemini + RAG diagnosis later.
"""

import time
from utils.constants import (
    DISEASE_MAP,
    UNKNOWN_DISEASE,
    IMAGE_CONFIDENCE_BOOST,
    MAX_CONFIDENCE,
    LOW_CONFIDENCE_THRESHOLD,
)
from services.logging_service import create_log, measure_latency_ms


def generate_mock_diagnosis(parsed_input: dict) -> dict:
    """
    Return a mock diagnosis based on the detected crop.

    Parameters
    ----------
    parsed_input : dict
        Output of InputParserAgent.parse_input().

    Returns
    -------
    dict with keys: crop, disease, disease_urdu, confidence, risk_level,
         evidence, needs_second_photo, log
    """
    t0 = time.perf_counter()

    crop = parsed_input.get("crop", "Unknown")
    has_image = parsed_input.get("has_image", False)

    # Look up disease from constant map
    disease_info = DISEASE_MAP.get(crop, UNKNOWN_DISEASE)

    confidence = disease_info["confidence"]
    evidence = []

    # If image is present, boost confidence slightly
    if has_image:
        confidence = min(confidence + IMAGE_CONFIDENCE_BOOST, MAX_CONFIDENCE)
        evidence.append("Image was considered in analysis")

    if parsed_input.get("text"):
        evidence.append("Text symptoms were analysed")

    confidence = round(confidence, 2)
    needs_second_photo = confidence < LOW_CONFIDENCE_THRESHOLD

    latency = measure_latency_ms(t0)

    log = create_log(
        agent_name="DiagnosisAgent",
        input_summary=f"crop={crop}, has_image={has_image}",
        decision=f"{disease_info['disease']} (conf={confidence})",
        status="success",
        confidence=confidence,
        latency_ms=latency,
    )

    return {
        "crop": crop,
        "disease": disease_info["disease"],
        "disease_urdu": disease_info["disease_urdu"],
        "confidence": confidence,
        "risk_level": disease_info["risk_level"],
        "evidence": evidence,
        "needs_second_photo": needs_second_photo,
        "log": log,
    }
