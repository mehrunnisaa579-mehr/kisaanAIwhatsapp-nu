"""
FarmAI — ExecutionAgent
Simulates execution of the action chain.
No real side-effects — marks actions as executed with timestamps.
"""

import time
from datetime import datetime, timezone
from services.logging_service import create_log, measure_latency_ms


def execute_actions(action_chain: list) -> dict:
    """
    Simulate execution of every action in the chain.

    Parameters
    ----------
    action_chain : list[dict]
        Output of ActionPlannerAgent.plan_actions().

    Returns
    -------
    dict with keys: executed_actions, execution_summary, log
    """
    t0 = time.perf_counter()

    executed = []
    counts = {"successful": 0, "delayed": 0, "needs_recovery": 0}

    for action in action_chain:
        entry = dict(action)  # shallow copy
        status = entry.get("status", "success")

        # Keep delayed / needs_recovery unchanged; mark others as simulated
        if status == "delayed":
            counts["delayed"] += 1
        elif status == "needs_recovery":
            counts["needs_recovery"] += 1
        else:
            counts["successful"] += 1

        entry["executed"] = True
        entry["execution_timestamp"] = datetime.now(timezone.utc).isoformat()
        entry["execution_status"] = f"simulated_{status}"
        executed.append(entry)

    latency = measure_latency_ms(t0)

    log = create_log(
        agent_name="ExecutionAgent",
        input_summary=f"actions_count={len(action_chain)}",
        decision=(
            f"Executed {counts['successful']} ok, "
            f"{counts['delayed']} delayed, "
            f"{counts['needs_recovery']} needs_recovery"
        ),
        status="success",
        latency_ms=latency,
    )

    return {
        "executed_actions": executed,
        "execution_summary": {
            "total_actions": len(action_chain),
            "successful": counts["successful"],
            "delayed": counts["delayed"],
            "needs_recovery": counts["needs_recovery"],
        },
        "log": log,
    }
