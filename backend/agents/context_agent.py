"""
FarmAI — ContextAgent
Enriches the pipeline with weather data and detects contradictions
between user text and diagnosis.
"""

import time
from services.weather_service import get_mock_weather
from services.logging_service import create_log, measure_latency_ms
from utils.constants import HEALTHY_KEYWORDS
from utils.helpers import contains_healthy_keywords


def get_context(parsed_input: dict, diagnosis: dict) -> dict:
    """
    Fetch contextual information (weather, contradictions).

    Parameters
    ----------
    parsed_input : dict
        Output of InputParserAgent.
    diagnosis : dict
        Output of DiagnosisAgent.

    Returns
    -------
    dict with keys: weather, contradictions, context_notes, log
    """
    t0 = time.perf_counter()

    # --- Weather ---
    weather = get_mock_weather(
        latitude=parsed_input.get("latitude"),
        longitude=parsed_input.get("longitude"),
    )

    # --- Contradiction detection ---
    contradictions = []
    text = parsed_input.get("text", "") or ""
    risk_level = diagnosis.get("risk_level", "Low")

    if contains_healthy_keywords(text, HEALTHY_KEYWORDS):
        if risk_level in ("Medium", "High"):
            contradictions.append({
                "type": "text_vs_diagnosis",
                "message_urdu": (
                    "کسان کے پیغام کے مطابق فصل ٹھیک ہے، مگر علامات "
                    "بیماری کی طرف اشارہ کر رہی ہیں۔"
                ),
                "severity": "medium",
            })

    # --- Context notes ---
    context_notes = []
    if weather["spray_safe"]:
        context_notes.append("موسم سپرے کے لیے موزوں ہے۔")
    else:
        context_notes.append("موسم سپرے کے لیے موزوں نہیں۔")

    if weather["rain_expected"]:
        context_notes.append("بارش متوقع ہے۔")

    latency = measure_latency_ms(t0)

    log = create_log(
        agent_name="ContextAgent",
        input_summary=f"weather_source={weather['source']}, "
                      f"contradictions={len(contradictions)}",
        decision="Context enriched with weather and contradiction check",
        status="success",
        latency_ms=latency,
    )

    return {
        "weather": weather,
        "contradictions": contradictions,
        "context_notes": context_notes,
        "log": log,
    }
