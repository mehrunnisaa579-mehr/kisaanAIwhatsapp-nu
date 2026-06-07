import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Initialize pools
CHAT_POOL = []
STT_POOL = []
TTS_POOL = []

backend_dir = Path(__file__).resolve().parent.parent
dotenv_path = backend_dir / ".env"

def classify_exception(exc: Exception) -> tuple[str, str]:
    exc_name = type(exc).__name__
    exc_msg = str(exc)
    msg_lower = exc_msg.lower()
    
    # 1. Invalid key / Authentication errors
    invalid_keywords = [
        "api key not valid",
        "invalid api key",
        "permission denied",
        "unauthorized",
        "authentication",
        "unauthenticated",
        "401",
        "403",
        "api_key_invalid"
    ]
    if any(kw in msg_lower for kw in invalid_keywords):
        return "invalid_api_key", f"{exc_name}: {exc_msg}"
        
    # 2. Quota / rate limit
    quota_keywords = [
        "429",
        "resourceexhausted",
        "quota exceeded",
        "quota",
        "rate limit",
        "limit 0",
        "free tier",
        "retry_delay"
    ]
    if any(kw in msg_lower for kw in quota_keywords):
        return "quota_or_rate_limit", f"{exc_name}: {exc_msg}"
        
    # 3. Model errors
    if "not found" in msg_lower or "404" in msg_lower:
        return "model_not_found", f"{exc_name}: {exc_msg}"
    if "unavailable" in msg_lower:
        return "model_unavailable", f"{exc_name}: {exc_msg}"
    if "unsupported" in msg_lower:
        return "unsupported_model", f"{exc_name}: {exc_msg}"
        
    # 4. Network errors
    network_keywords = [
        "connect", "network", "timeout", "dns", "connectionreseterror", "httpconnectionpool", "deadline", "504"
    ]
    if any(kw in msg_lower for kw in network_keywords):
        return "network_error", f"{exc_name}: {exc_msg}"
        
    # 5. Invalid response
    if "validation" in msg_lower or "empty response" in msg_lower:
        return "invalid_response", f"{exc_name}: {exc_msg}"
        
    return "unknown_error", f"{exc_name}: {exc_msg}"

def init_pools():
    global CHAT_POOL, STT_POOL, TTS_POOL
    load_dotenv(dotenv_path=dotenv_path)
    
    placeholders = {
        "your_key_here", "your_key", "test_key", "dummy_key", "placeholder_key"
    }
    
    def clean_and_validate(key_val):
        if not key_val:
            return None
        key_stripped = key_val.strip()
        if not key_stripped:
            return None
        if key_stripped.lower() in placeholders:
            return None
        return key_stripped

    # Chat pool
    chat_keys = []
    for k in ["GEMINI_CHAT_KEY_1", "GEMINI_CHAT_KEY_2", "GEMINI_CHAT_KEY_3"]:
        validated = clean_and_validate(os.getenv(k))
        if validated:
            chat_keys.append(validated)
    
    # STT pool
    stt_keys = []
    for k in ["GEMINI_STT_KEY_1", "GEMINI_STT_KEY_2", "GEMINI_STT_KEY_3"]:
        validated = clean_and_validate(os.getenv(k))
        if validated:
            stt_keys.append(validated)
            
    # TTS pool
    tts_keys = []
    for k in ["GEMINI_TTS_KEY_1", "GEMINI_TTS_KEY_2", "GEMINI_TTS_KEY_3"]:
        validated = clean_and_validate(os.getenv(k))
        if validated:
            tts_keys.append(validated)
            
    # Fallback to GEMINI_API_KEY
    gemini_api_key = clean_and_validate(os.getenv("GEMINI_API_KEY"))
    
    if not chat_keys and gemini_api_key:
        chat_keys.append(gemini_api_key)
    if not stt_keys and gemini_api_key:
        stt_keys.append(gemini_api_key)
    if not tts_keys and gemini_api_key:
        tts_keys.append(gemini_api_key)
        
    CHAT_POOL = chat_keys[:3]
    STT_POOL = stt_keys[:3]
    TTS_POOL = tts_keys[:3]
    
    fallback_available = "true" if gemini_api_key else "false"
    sdk_mode = "old google-generativeai"
    resolved_path = str(dotenv_path.resolve())
    
    # Precise logging requirements
    print("[Rotation Engines Active]")
    print(f"Chat/Image Pool: {len(CHAT_POOL)} key(s) loaded")
    print(f"STT Pool: {len(STT_POOL)} key(s) loaded")
    print(f"TTS Pool: {len(TTS_POOL)} key(s) loaded")
    print(f"GEMINI_API_KEY fallback available: {fallback_available}")
    print(f"Gemini SDK mode: {sdk_mode}")
    print(f"Loaded .env path: {resolved_path}")
    
    logger.info("[Rotation Engines Active]")
    logger.info("Chat/Image Pool: %d key(s) loaded", len(CHAT_POOL))
    logger.info("STT Pool: %d key(s) loaded", len(STT_POOL))
    logger.info("TTS Pool: %d key(s) loaded", len(TTS_POOL))
    logger.info("GEMINI_API_KEY fallback available: %s", fallback_available)
    logger.info("Gemini SDK mode: %s", sdk_mode)
    logger.info("Loaded .env path: %s", resolved_path)

def run_with_key_rotation(pool_name: str, callable_fn):
    """
    Runs callable_fn with keys from the designated pool_name (CHAT, STT, TTS).
    callable_fn must accept api_key: callable_fn(api_key)
    
    Rotates to the next key in the pool if:
    - An exception classified as quota_or_rate_limit or invalid_api_key is raised.
    - The returned dict has success=False and error_type as quota_or_rate_limit or invalid_api_key.
    
    If all keys fail, returns a structured failure dictionary.
    """
    if pool_name == "CHAT":
        pool = CHAT_POOL
    elif pool_name == "STT":
        pool = STT_POOL
    elif pool_name == "TTS":
        pool = TTS_POOL
    else:
        raise ValueError(f"Unknown pool name: {pool_name}")
        
    if not pool:
        logger.error(f"Pool {pool_name} is empty and GEMINI_API_KEY fallback is missing.")
        return {
            "success": False,
            "error_type": "missing_api_key",
            "error_message": f"GEMINI_API_KEY environment variable is missing or empty for pool {pool_name}.",
            "pool": pool_name,
            "key_index_used": 0,
            "attempts": []
        }
        
    attempts = []
    max_to_try = min(3, len(pool))
    
    for idx in range(max_to_try):
        api_key = pool[idx]
        
        logger.info("[Rotation Engine] Pool %s using Key Index %d", pool_name, idx + 1)
        print(f"[Rotation Engine] Pool {pool_name} using Key Index {idx + 1}")
        
        try:
            res = callable_fn(api_key)
            
            # Check if returned dict indicates quota/invalid key error
            if isinstance(res, dict) and res.get("success") is False:
                err_type = res.get("error_type", "unknown_error")
                err_msg = res.get("error_message") or res.get("message") or ""
                
                attempts.append({
                    "key_index": idx + 1,
                    "success": False,
                    "error_type": err_type,
                    "error_message": err_msg
                })
                
                if err_type in ("quota_or_rate_limit", "invalid_api_key"):
                    logger.warning("[Rotation Engine] Pool %s Key Index %d failed: %s", pool_name, idx + 1, err_type)
                    print(f"[Rotation Engine] Pool {pool_name} Key Index {idx + 1} failed: {err_type}")
                    continue
                else:
                    # Non-rotatable error, stop and return the result
                    return {
                        "success": False,
                        "result": res,
                        "pool": pool_name,
                        "key_index_used": idx + 1,
                        "attempts": attempts,
                        "error_type": err_type,
                        "error_message": err_msg
                    }
            
            # If we reached here, either it's not a dict, or success is True/missing.
            logger.info("[Rotation Engine] Pool %s succeeded with Key Index %d", pool_name, idx + 1)
            print(f"[Rotation Engine] Pool {pool_name} succeeded with Key Index {idx + 1}")
            
            return {
                "success": True,
                "result": res,
                "pool": pool_name,
                "key_index_used": idx + 1,
                "attempts": attempts + [{
                    "key_index": idx + 1,
                    "success": True,
                    "error_type": None,
                    "error_message": None
                }],
                "error_type": None,
                "error_message": None
            }
            
        except Exception as exc:
            err_type, err_msg = classify_exception(exc)
            attempts.append({
                "key_index": idx + 1,
                "success": False,
                "error_type": err_type,
                "error_message": err_msg
            })
            
            if err_type in ("quota_or_rate_limit", "invalid_api_key"):
                logger.warning("[Rotation Engine] Pool %s Key Index %d failed: %s", pool_name, idx + 1, err_type)
                print(f"[Rotation Engine] Pool {pool_name} Key Index {idx + 1} failed: {err_type}")
                continue
            else:
                # Non-rotatable exception, return structured failure
                logger.error("[Rotation Engine] Pool %s failed with non-rotatable error %s. Aborting.", pool_name, err_type)
                return {
                    "success": False,
                    "result": None,
                    "pool": pool_name,
                    "key_index_used": idx + 1,
                    "attempts": attempts,
                    "error_type": err_type,
                    "error_message": err_msg
                }
                
    # If we tried all keys and all failed due to quota/invalid key
    logger.error("[Rotation Engine] All keys in pool %s failed due to quota/invalid key.", pool_name)
    final_err_type = attempts[-1]["error_type"] if attempts else "unknown_error"
    final_err_msg = attempts[-1]["error_message"] if attempts else "All keys exhausted"
    return {
        "success": False,
        "result": None,
        "pool": pool_name,
        "key_index_used": max_to_try,
        "attempts": attempts,
        "error_type": final_err_type,
        "error_message": final_err_msg
    }

# Run initialization once on import
init_pools()
