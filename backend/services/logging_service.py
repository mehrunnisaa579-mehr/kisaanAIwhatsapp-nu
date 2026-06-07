"""
FarmAI Logging Service
Creates structured log entries for each agent in the pipeline.
Logs are returned in the API response (no file I/O).
"""

import time
from datetime import datetime, timezone


def create_log(
    agent_name: str,
    input_summary: str,
    decision: str,
    status: str = "success",
    confidence: float = None,
    latency_ms: int = None,
) -> dict:
    """
    Create a single structured log entry for an agent.

    Parameters
    ----------
    agent_name : str
        Name of the agent (e.g. 'InputParserAgent').
    input_summary : str
        Brief description of what the agent received.
    decision : str
        What the agent decided / produced.
    status : str
        'success', 'delayed', 'needs_recovery', 'error', etc.
    confidence : float | None
        Confidence score if applicable.
    latency_ms : int | None
        Actual or mock latency in milliseconds.

    Returns
    -------
    dict
        Structured log entry.
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent_name,
        "input_summary": input_summary,
        "decision": decision,
        "status": status,
        "confidence": confidence,
        "latency_ms": latency_ms if latency_ms is not None else 0,
    }


def collect_logs(*logs) -> list:
    """
    Merge multiple log entries (dicts or lists of dicts) into a flat list.
    """
    merged = []
    for entry in logs:
        if entry is None:
            continue
        if isinstance(entry, list):
            merged.extend(entry)
        elif isinstance(entry, dict):
            merged.append(entry)
    return merged


def measure_latency_ms(start_time: float) -> int:
    """
    Calculate elapsed milliseconds from a time.perf_counter() start.
    """
    return int((time.perf_counter() - start_time) * 1000)
