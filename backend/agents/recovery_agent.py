"""
FarmAI — RecoveryAgent
Handles edge cases: low confidence, over-budget treatments, rain delays.
"""

import time
from utils.constants import MANGO_ALTERNATIVE_COST_PKR
from services.logging_service import create_log, measure_latency_ms


def apply_recovery(
    diagnosis: dict,
    context: dict,
    execution_result: dict,
) -> dict:
    """
    Apply recovery logic for problematic actions.

    Parameters
    ----------
    diagnosis : dict
        Output of DiagnosisAgent.
    context : dict
        Output of ContextAgent.
    execution_result : dict
        Output of ExecutionAgent.

    Returns
    -------
    dict with keys: recovery_status, recovery_actions, log
    """
    t0 = time.perf_counter()

    recovery_actions = []
    weather = context.get("weather", {})

    # Case 1 — Low confidence → ask for second photo
    if diagnosis.get("needs_second_photo", False):
        recovery_actions.append({
            "type": "request_second_photo",
            "message_urdu": (
                "تشخیص کا اعتماد کم ہے، براہ کرم ایک اور واضح تصویر بھیجیں "
                "تاکہ FarmAI بہتر تجزیہ کر سکے۔"
            ),
            "status": "recovery_required",
        })

    # Case 2 — Over-budget treatment (needs_recovery flag)
    executed = execution_result.get("executed_actions", [])
    for action in executed:
        if action.get("status") == "needs_recovery":
            cost = action.get("estimated_cost_pkr", 0)
            if cost > 2000:
                recovery_actions.append({
                    "type": "budget_alternative",
                    "original_cost_pkr": cost,
                    "alternative_cost_pkr": MANGO_ALTERNATIVE_COST_PKR,
                    "message_urdu": (
                        "مہنگا علاج بجٹ سے زیادہ ہے، اس لیے کم قیمت "
                        "متبادل تجویز کیا گیا ہے۔"
                    ),
                    "status": "recovery_applied",
                })

    # Case 3 — Rain expected → delay spray
    if weather.get("rain_expected", False):
        recovery_actions.append({
            "type": "rain_delay",
            "message_urdu": (
                "بارش متوقع ہے، اس لیے سپرے کو مؤخر کرنا بہتر ہے۔"
            ),
            "status": "recovery_applied",
        })

    # Determine overall status
    if not recovery_actions:
        recovery_status = "stable"
    else:
        has_required = any(
            a.get("status") == "recovery_required" for a in recovery_actions
        )
        recovery_status = "recovery_required" if has_required else "recovery_applied"

    latency = measure_latency_ms(t0)

    log = create_log(
        agent_name="RecoveryAgent",
        input_summary=f"needs_second_photo={diagnosis.get('needs_second_photo', False)}, "
                      f"rain={weather.get('rain_expected', False)}",
        decision=f"recovery_status={recovery_status}, "
                 f"actions={len(recovery_actions)}",
        status=recovery_status,
        latency_ms=latency,
    )

    return {
        "recovery_status": recovery_status,
        "recovery_actions": recovery_actions,
        "log": log,
    }
