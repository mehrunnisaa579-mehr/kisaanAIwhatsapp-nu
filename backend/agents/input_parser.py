"""
FarmAI — InputParser Agent
Parses and normalises raw user input (text, image flag, location, crop).
"""

import time
from utils.helpers import detect_language, infer_crop
from services.logging_service import create_log, measure_latency_ms


def parse_input(
    text: str = None,
    crop: str = None,
    latitude: float = None,
    longitude: float = None,
    image=None,
) -> dict:
    """
    Parse raw input and return a structured representation.

    Parameters
    ----------
    text : str | None
        User's message (can be Urdu, Roman Urdu, or English).
    crop : str | None
        Explicitly selected crop from the frontend.
    latitude, longitude : float | None
        GPS coordinates if available.
    image : UploadFile | None
        Image attachment if any.

    Returns
    -------
    dict with keys: crop, text, has_image, has_location, language_hint,
         normalized_query, confidence, log
    """
    t0 = time.perf_counter()

    has_image = image is not None and getattr(image, "filename", "") != ""
    has_location = latitude is not None and longitude is not None

    language_hint = detect_language(text)
    detected_crop = infer_crop(text, crop)

    # Build a normalised query string
    normalized_query = (text or "").strip()
    if not normalized_query:
        normalized_query = f"Image-only query for {detected_crop}"

    # Confidence heuristic — more signals → higher confidence
    confidence = 0.5
    if text:
        confidence += 0.15
    if has_image:
        confidence += 0.10
    if has_location:
        confidence += 0.05
    if detected_crop != "Unknown":
        confidence += 0.10
    confidence = round(min(confidence, 0.90), 2)

    latency = measure_latency_ms(t0)

    log = create_log(
        agent_name="InputParserAgent",
        input_summary=f"text={'yes' if text else 'no'}, "
                      f"image={'yes' if has_image else 'no'}, "
                      f"location={'yes' if has_location else 'no'}",
        decision=f"Detected crop: {detected_crop}, lang: {language_hint}",
        status="success",
        confidence=confidence,
        latency_ms=latency,
    )

    return {
        "crop": detected_crop,
        "text": text,
        "has_image": has_image,
        "has_location": has_location,
        "latitude": latitude,
        "longitude": longitude,
        "language_hint": language_hint,
        "normalized_query": normalized_query,
        "confidence": confidence,
        "log": log,
    }
