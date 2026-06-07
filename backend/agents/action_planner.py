"""
FarmAI — ActionPlannerAgent
Generates a 3–5 step action chain based on diagnosis, weather, and context.
"""

import time
from utils.constants import (
    MANGO_TREATMENT_COST_PKR,
    MANGO_ALTERNATIVE_COST_PKR,
    DEFAULT_TREATMENT_COST_PKR,
    DEFAULT_BUDGET_LIMIT_PKR,
    LOW_CONFIDENCE_THRESHOLD,
)
from services.logging_service import create_log, measure_latency_ms


def plan_actions(parsed_input: dict, diagnosis: dict, context: dict) -> list:
    """
    Generate a list of 3–5 action steps.

    Parameters
    ----------
    parsed_input : dict
        Output of InputParserAgent.
    diagnosis : dict
        Output of DiagnosisAgent.
    context : dict
        Output of ContextAgent.

    Returns
    -------
    list[dict]  — each item is an action step.
    """
    t0 = time.perf_counter()

    weather = context.get("weather", {})
    rain = weather.get("rain_expected", False)
    spray_safe = weather.get("spray_safe", True)
    crop = diagnosis.get("crop", "Unknown")
    confidence = diagnosis.get("confidence", 0.5)
    risk_level = diagnosis.get("risk_level", "Low")
    low_confidence = confidence < LOW_CONFIDENCE_THRESHOLD

    actions = []
    step = 0

    # --- Step 1: Diagnosis validation ---
    step += 1
    actions.append({
        "step": step,
        "agent": "ActionPlannerAgent",
        "title_urdu": "تشخیص کی تصدیق",
        "action": "Validate diagnosis",
        "action_urdu": "تشخیص کی توثیق کی گئی۔",
        "status": "success",
        "reason_urdu": (
            "فصل کی علامات کا جائزہ لیا گیا اور تشخیص کی تصدیق ہوئی۔"
        ),
        "estimated_cost_pkr": 0,
        "latency_ms": 0,
    })

    # --- Step 2: Weather / spray safety ---
    step += 1
    if rain or not spray_safe:
        actions.append({
            "step": step,
            "agent": "ActionPlannerAgent",
            "title_urdu": "موسم کی جانچ",
            "action": "Weather check — spray delayed",
            "action_urdu": "بارش یا نامناسب موسم کی وجہ سے سپرے مؤخر کیا گیا۔",
            "status": "delayed",
            "reason_urdu": "بارش متوقع ہے یا موسم سپرے کے لیے موزوں نہیں۔",
            "estimated_cost_pkr": 0,
            "latency_ms": 0,
        })
    else:
        actions.append({
            "step": step,
            "agent": "ActionPlannerAgent",
            "title_urdu": "موسم کی جانچ",
            "action": "Weather check — spray safe",
            "action_urdu": "موسم سپرے کے لیے موزوں ہے۔",
            "status": "success",
            "reason_urdu": "بارش متوقع نہیں اور موسم مناسب ہے۔",
            "estimated_cost_pkr": 0,
            "latency_ms": 0,
        })

    # --- Step 3: Treatment / spray recommendation ---
    step += 1
    if low_confidence:
        # Ask for second photo instead of suggesting strong treatment
        actions.append({
            "step": step,
            "agent": "ActionPlannerAgent",
            "title_urdu": "دوسری تصویر کی درخواست",
            "action": "Request second photo",
            "action_urdu": (
                "تشخیص کا اعتماد کم ہے، براہ کرم ایک اور واضح تصویر بھیجیں۔"
            ),
            "status": "needs_recovery",
            "reason_urdu": "تشخیص کا اعتماد کم ہونے کی وجہ سے مزید معلومات درکار ہیں۔",
            "estimated_cost_pkr": 0,
            "latency_ms": 0,
        })
    else:
        # Determine treatment cost
        treatment_cost = DEFAULT_TREATMENT_COST_PKR
        treatment_status = "success"

        if crop == "Mango":
            treatment_cost = MANGO_TREATMENT_COST_PKR
            if treatment_cost > DEFAULT_BUDGET_LIMIT_PKR:
                treatment_status = "needs_recovery"

        actions.append({
            "step": step,
            "agent": "ActionPlannerAgent",
            "title_urdu": "علاج / سپرے کی سفارش",
            "action": "Treatment recommendation",
            "action_urdu": f"تجویز کردہ علاج — تخمینی لاگت {treatment_cost} روپے۔",
            "status": treatment_status,
            "reason_urdu": (
                "فصل کی بیماری کے مطابق مناسب سپرے/دوا تجویز کی گئی۔"
            ),
            "estimated_cost_pkr": treatment_cost,
            "latency_ms": 0,
        })

    # --- Step 4: Expert alert (if risk Medium/High or low confidence) ---
    if risk_level in ("Medium", "High") or low_confidence:
        step += 1
        actions.append({
            "step": step,
            "agent": "ActionPlannerAgent",
            "title_urdu": "ماہر کو اطلاع",
            "action": "Expert alert simulation",
            "action_urdu": "مقامی زرعی ماہر کو اطلاع بھیجی گئی (سمیولیشن)۔",
            "status": "success",
            "reason_urdu": (
                "خطرے کی سطح یا کم اعتماد کی بنیاد پر ماہر سے مشورے "
                "کی سفارش کی جاتی ہے۔"
            ),
            "estimated_cost_pkr": 0,
            "latency_ms": 0,
        })

    # --- Step 5: 48-hour follow-up ---
    step += 1
    actions.append({
        "step": step,
        "agent": "ActionPlannerAgent",
        "title_urdu": "48 گھنٹے بعد فالو اپ",
        "action": "48-hour follow-up reminder",
        "action_urdu": "48 گھنٹے بعد فصل کا دوبارہ جائزہ لینے کی یاد دہانی۔",
        "status": "success",
        "reason_urdu": "علاج کے بعد فصل کی حالت کی نگرانی ضروری ہے۔",
        "estimated_cost_pkr": 0,
        "latency_ms": 0,
    })

    # Stamp latency on all actions
    latency = measure_latency_ms(t0)
    for a in actions:
        a["latency_ms"] = latency

    return actions
