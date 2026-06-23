"""
FarmAI Session Memory Service
Implements a simple JSON-file based storage for user sessions.
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Resolve backend/data/session_memory.json
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
MEMORY_FILE = DATA_DIR / "session_memory.json"

def _ensure_file_exists():
    """Ensure data/ directory and session_memory.json exist."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not MEMORY_FILE.exists() or MEMORY_FILE.stat().st_size == 0:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to ensure session memory file exists: %s", e)

def _load_all_sessions() -> dict:
    """Read all sessions from the JSON file safely."""
    _ensure_file_exists()
    try:
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("Session memory file corrupt or unreadable, resetting: %s", e)
        # Reset file
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    return {}

def _save_all_sessions(sessions: dict):
    """Write all sessions back to the JSON file safely."""
    _ensure_file_exists()
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to write to session memory file: %s", e)

def get_session(user_id: str) -> dict:
    """Get session data for a specific user_id."""
    if not user_id:
        return {}
    sessions = _load_all_sessions()
    return sessions.get(user_id, {})

def update_session(user_id: str, updates: dict) -> dict:
    """Apply updates to a user's session record and save."""
    if not user_id:
        return {}
    sessions = _load_all_sessions()
    session = sessions.get(user_id, {})
    
    # Apply updates
    for k, v in updates.items():
        session[k] = v
        
    session["updated_at"] = datetime.utcnow().isoformat() + "Z"
    sessions[user_id] = session
    _save_all_sessions(sessions)
    return session

def save_location(user_id: str, latitude: float, longitude: float) -> dict:
    """Save user coordinates into the session memory."""
    updates = {
        "last_location": {
            "latitude": latitude,
            "longitude": longitude
        }
    }
    return update_session(user_id, updates)

def get_last_location(user_id: str) -> dict | None:
    """Retrieve saved location dict from the user session."""
    session = get_session(user_id)
    return session.get("last_location")

def save_last_crop(user_id: str, crop: str) -> dict:
    """Save user's crop context to session."""
    return update_session(user_id, {"last_crop": crop})

def save_last_language(user_id: str, language: str) -> dict:
    """Save user's language context to session."""
    return update_session(user_id, {"last_language": language})

def clear_session(user_id: str) -> dict:
    """Delete a user's session record entirely."""
    if not user_id:
        return {}
    sessions = _load_all_sessions()
    if user_id in sessions:
        del sessions[user_id]
        _save_all_sessions(sessions)
    return {}
