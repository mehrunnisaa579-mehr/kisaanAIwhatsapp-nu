import os
import re
import logging
from dotenv import load_dotenv

from utils.helpers import get_weather_instruction

logger = logging.getLogger(__name__)

# Caching variables to avoid repeated API list calls and model sweeps
_CACHED_AVAILABLE_MODELS = None
_CACHED_WORKING_MODEL = None

# Global cache for GET /gemini-status
LAST_STATUS = {
    "key_loaded": False,
    "key_length": 0,
    "selected_model": None,
    "available_generate_content_models": [],
    "tested_models": [],
    "working_model": None,
    "last_error_type": None
}


def _is_mostly_english(text: str) -> bool:
    """Return True if more than 40 % of the characters are basic ASCII letters."""
    if not text:
        return True
    ascii_letters = sum(1 for ch in text if "a" <= ch <= "z" or "A" <= ch <= "Z")
    return (ascii_letters / len(text)) > 0.40


def _validate_response(text: str, language_hint: str = "ur", crop: str = "Unknown") -> str | None:
    """
    Validate Gemini output before using it as farmer_response.

    Returns cleaned text or None if the response is unusable.
    """
    if not text:
        return None

    # Clean markdown bold asterisks if present
    text = text.replace("**", "").strip()

    # 1. Reject empty response or whitespace only
    if not text:
        return None

    # 2. Reject response containing JSON/backend/agent/Gemini words
    banned_substrings = [
        "gemini", "ai model", "backend", "agent", "json",
        "confidence", "latency", "mock", "pipeline"
    ]
    text_lower = text.lower()
    for banned in banned_substrings:
        if banned in text_lower:
            logger.warning("Validation failed: contains banned word '%s'", banned)
            return None

    # 3. Reject response containing raw JSON
    trimmed = text.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        logger.warning("Validation failed: contains raw JSON block")
        return None
    if '"status":' in text or '"farmer_response":' in text or '{"status":' in trimmed:
        logger.warning("Validation failed: contains raw JSON fields")
        return None

    lang = (language_hint or "ur").strip().lower()
    if lang in ("urdu", "unknown"):
        lang = "ur"

    # Check if the query is an irrelevant query refusal or crop inquiry (when crop is Unknown)
    is_refusal_or_inquiry = (crop == "Unknown")
    refusal_keywords = [
        "یہ سسٹم صرف", "یہ نظام صرف", "سسٹم صرف",
        "yeh system sirf", "system sirf",
        "this system is only", "system is only", "only built for crops"
    ]
    if any(rk in text_lower or rk in text for rk in refusal_keywords):
        is_refusal_or_inquiry = True

    # 4. Language-specific validation checks
    if lang == "ur":
        # must contain Urdu/Arabic script
        urdu_char_count = sum(1 for ch in text if "\u0600" <= ch <= "\u06FF")
        min_urdu_chars = 15 if is_refusal_or_inquiry else 40
        if urdu_char_count < min_urdu_chars:
            logger.warning("Validation failed: too few Urdu characters (%d)", urdu_char_count)
            return None
        # should not be mostly English
        if _is_mostly_english(text):
            logger.warning("Validation failed: mostly English in Urdu response")
            return None
        # required Urdu headings must exist if not refusal/inquiry
        if not is_refusal_or_inquiry:
            required_headings = ["ممکنہ مسئلہ", "خطرے کی سطح", "تجویز کردہ عمل", "موسم کا خیال", "اگلا قدم"]
            for heading in required_headings:
                if heading not in text:
                    logger.warning("Validation failed: missing required Urdu heading '%s'", heading)
                    return None

    elif lang == "roman_urdu":
        # should be Latin script, should not contain mostly Urdu script
        urdu_char_count = sum(1 for ch in text if "\u0600" <= ch <= "\u06FF")
        if urdu_char_count > 20:
            logger.warning("Validation failed: contains too many Urdu script characters in Roman Urdu (%d)", urdu_char_count)
            return None
        # Roman Urdu headings should exist if not refusal/inquiry
        if not is_refusal_or_inquiry:
            roman_headings = ["mumkin masla", "khatray ki satah", "tajweez kardah amal", "mosam ka khayal", "agla qadam"]
            for heading in roman_headings:
                if heading not in text_lower:
                    logger.warning("Validation failed: missing Roman Urdu heading '%s'", heading)
                    return None

    elif lang == "english":
        # should be English/Latin script
        urdu_char_count = sum(1 for ch in text if "\u0600" <= ch <= "\u06FF")
        if urdu_char_count > 20:
            logger.warning("Validation failed: contains too many Urdu script characters in English (%d)", urdu_char_count)
            return None
        # English headings should exist if not refusal/inquiry
        if not is_refusal_or_inquiry:
            english_headings = ["possible issue", "risk level", "recommended action", "weather note", "next step"]
            for heading in english_headings:
                if heading not in text_lower:
                    logger.warning("Validation failed: missing English heading '%s'", heading)
                    return None

    return text


HEADINGS_MAP = {
    "ur": [
        ("ممکنہ مسئلہ", "ممکنہ مسئلہ:"),
        ("خطرے کی سطح", "خطرے کی سطح:"),
        ("تجویز کردہ عمل", "تجویز کردہ عمل:"),
        ("موسم کا خیال", "موسم کا خیال:"),
        ("اگلا قدم", "اگلا قدم:")
    ],
    "roman_urdu": [
        ("mumkin masla", "Mumkin Masla:"),
        ("khatray ki satah", "Khatray ki Satah:"),
        ("tajweez kardah amal", "Tajweez Kardah Amal:"),
        ("mosam ka khayal", "Mosam ka Khayal:"),
        ("agla qadam", "Agla Qadam:")
    ],
    "english": [
        ("possible issue", "Possible Issue:"),
        ("risk level", "Risk Level:"),
        ("recommended action", "Recommended Action:"),
        ("weather note", "Weather Note:"),
        ("next step", "Next Step:")
    ]
}


def extract_sections(text: str, lang: str) -> dict:
    headings_list = HEADINGS_MAP.get(lang, HEADINGS_MAP["ur"])
    found = []
    text_lower = text.lower()
    for key, display_name in headings_list:
        idx = text_lower.find(key.lower())
        if idx != -1:
            found.append((idx, key, display_name))
    
    # Sort by index
    found.sort(key=lambda x: x[0])
    
    sections = {}
    for i in range(len(found)):
        idx, key, display_name = found[i]
        start_idx = idx + len(key)
        # Check if there is a colon following it, skip it
        while start_idx < len(text) and text[start_idx] in (':', ' ', '\t', '\n'):
            start_idx += 1
        
        end_idx = found[i+1][0] if i + 1 < len(found) else len(text)
        section_content = text[start_idx:end_idx].strip()
        sections[key] = section_content
    return sections


def clean_and_shorten_section(text: str, max_sentences: int) -> str:
    if not text:
        return ""
    # Remove bullet symbols like *, -, +, or numbers like 1., 2. at start of lines
    cleaned = re.sub(r'^\s*[-*+•]\s*', '', text, flags=re.MULTILINE)
    cleaned = re.sub(r'^\s*\d+[\s\.)\-:]*', '', cleaned, flags=re.MULTILINE)
    
    # Remove markdown asterisks, brackets, parentheses, percent signs, special characters
    cleaned = cleaned.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
    cleaned = re.sub(r'[\(\)\[\]\{\}%]', ' ', cleaned)
    cleaned = cleaned.replace("⚠", "").replace("-", "—")
    
    # Split into sentences using common sentence endings: Urdu full stop (۔), English full stop (.), newlines, etc.
    sentences = re.split(r'[۔\.\n!\?]', cleaned)
    # Clean each sentence and filter out empty ones
    clean_sentences = []
    for s in sentences:
        s_clean = s.strip()
        if s_clean and len(s_clean) > 2:
            clean_sentences.append(s_clean)
            
    selected = clean_sentences[:max_sentences]
    
    # Join sentences back with correct full stop depending on characters
    is_urdu = any("\u0600" <= ch <= "\u06FF" for ch in text)
    separator = "۔ " if is_urdu else ". "
    end_char = "۔" if is_urdu else "."
    
    joined = separator.join(selected)
    if joined and not joined.endswith(end_char):
        joined += end_char
    return joined


def enforce_short_complete_tts_summary(summary: str, lang: str) -> str:
    if not summary:
        return _get_fallback_summary(lang)
        
    # Split into sentences using full-stop boundaries (۔ for Urdu, . for English/Roman Urdu, plus ! and ?)
    sentences = re.split(r'([۔\n!\?]|\.(?!\d))', summary)
    
    reconstructed_sentences = []
    i = 0
    while i < len(sentences):
        s = sentences[i].strip()
        sep = ""
        if i + 1 < len(sentences):
            sep = sentences[i+1].strip()
        
        if s or sep:
            full_sent = f"{s}{sep}".strip()
            if len(full_sent) > 1:
                reconstructed_sentences.append(full_sent)
        i += 2
        
    clean_sents = [s for s in reconstructed_sentences if len(s.strip()) > 3]
    
    if not clean_sents:
        return _get_fallback_summary(lang)
        
    # Keep max 3 sentences initially
    selected_sents = clean_sents[:3]
    
    def fits(sents):
        joined = " ".join(sents).strip()
        words = len(joined.split())
        chars = len(joined)
        return words <= 55 and chars <= 350
        
    if fits(selected_sents):
        return " ".join(selected_sents).strip()
        
    selected_sents = clean_sents[:2]
    if fits(selected_sents):
        return " ".join(selected_sents).strip()
        
    selected_sents = clean_sents[:1]
    if fits(selected_sents):
        return " ".join(selected_sents).strip()
        
    return _get_fallback_summary(lang)


def _get_fallback_summary(lang: str) -> str:
    if lang == "ur":
        return "آپ کی فصل میں بیماری، کیڑے یا غذائی کمی کا مسئلہ ہو سکتا ہے۔ پتے غور سے دیکھیں، پانی اور کھاد کا توازن رکھیں، اور واضح تصویر بھیج کر تشخیص confirm کریں۔"
    elif lang == "roman_urdu":
        return "Aap ki fasal mein bemari, keera ya ghizai kami ka masla ho sakta hai. Pattay check karein, pani aur khaad ka tawazun rakhein, aur clear tasveer bhej kar diagnosis confirm karein."
    else:
        return "Your crop may have a disease, pest, or nutrient issue. Check the leaves carefully, manage water and fertilizer balance, and send a clear photo for confirmation."


def generate_safe_tts_summary(farmer_response: str, language_hint: str) -> str:
    if not farmer_response:
        return ""
    
    lang = (language_hint or "ur").strip().lower()
    if lang in ("urdu", "unknown"):
        lang = "ur"
    elif lang not in ("roman_urdu", "english"):
        lang = "ur"
        
    headings_list = HEADINGS_MAP.get(lang, HEADINGS_MAP["ur"])
    has_headings = any(key.lower() in farmer_response.lower() for key, _ in headings_list)
    
    if not has_headings:
        # Refusal or fallback paragraph: Clean and get first 2 sentences, keep it brief
        summary = clean_and_shorten_section(farmer_response, 2)
        return enforce_short_complete_tts_summary(summary, lang)
        
    sections = extract_sections(farmer_response, lang)
    
    # Identify heading keys in order
    issue_key = "ممکنہ مسئلہ" if lang == "ur" else ("mumkin masla" if lang == "roman_urdu" else "possible issue")
    action_key = "تجویز کردہ عمل" if lang == "ur" else ("tajweez kardah amal" if lang == "roman_urdu" else "recommended action")
    next_key = "اگلا قدم" if lang == "ur" else ("agla qadam" if lang == "roman_urdu" else "next step")
    
    issue_content = ""
    action_content = ""
    next_content = ""
    
    for k, v in sections.items():
        if k.lower() == issue_key.lower():
            issue_content = v
        elif k.lower() == action_key.lower():
            action_content = v
        elif k.lower() == next_key.lower():
            next_content = v
            
    # Try soft substring matches if direct match failed
    if not issue_content:
        for k, v in sections.items():
            if issue_key.lower() in k.lower() or k.lower() in issue_key.lower():
                issue_content = v
    if not action_content:
        for k, v in sections.items():
            if action_key.lower() in k.lower() or k.lower() in action_key.lower():
                action_content = v
    if not next_content:
        for k, v in sections.items():
            if next_key.lower() in k.lower() or k.lower() in next_key.lower():
                next_content = v

    # Clean and get first 1 sentence of each
    parts = []
    if issue_content:
        cleaned_issue = clean_and_shorten_section(issue_content, 1)
        if cleaned_issue:
            parts.append(cleaned_issue)
            
    if action_content:
        cleaned_action = clean_and_shorten_section(action_content, 1)
        if cleaned_action:
            parts.append(cleaned_action)
            
    if next_content:
        cleaned_next = clean_and_shorten_section(next_content, 1)
        if cleaned_next:
            parts.append(cleaned_next)
            
    # Join into a single heading-free paragraph
    summary = " ".join(parts).strip()
    
    # If we got nothing from parts, fall back to clean and shorten the whole farmer_response
    if not summary:
        summary = clean_and_shorten_section(farmer_response, 2)
        
    return enforce_short_complete_tts_summary(summary, lang)


def is_too_short_or_invalid(tts_summary: str, lang: str, has_headings: bool) -> bool:
    if not tts_summary:
        return True
    
    # Clean it up first to check real characters and words
    cleaned = clean_tts_summary_format(tts_summary)
    
    word_count = len(cleaned.split())
    char_count = len(cleaned)
    
    # Reject if empty or too short (less than 12 words)
    if word_count < 12:
        return True
        
    # Reject if too long (over 55 words or 350 characters)
    if word_count > 55 or char_count > 350:
        return True
        
    # Reject if it contains JSON/backend/agent/Gemini words
    banned_substrings = [
        "gemini", "ai model", "backend", "agent", "json",
        "confidence", "latency", "mock", "pipeline"
    ]
    cleaned_lower = cleaned.lower()
    for banned in banned_substrings:
        if banned in cleaned_lower:
            return True
            
    # Reject if it contains obvious raw markdown or bullet symbols
    if any(m in tts_summary for m in ["**", "```", "•", " - ", " * "]):
        return True
        
    return False


def clean_tts_summary_format(tts_summary: str) -> str:
    if not tts_summary:
        return ""
    # 1. Remove markdown bold, bullets, underscores
    cleaned = re.sub(r'^\s*[-*+•]\s*', '', tts_summary, flags=re.MULTILINE)
    cleaned = cleaned.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
    
    # 2. Strip headings (case-insensitive, optionally followed by colons/spaces)
    headings_to_remove = [
        "ممکنہ مسئلہ", "خطرے کی سطح", "تجویز کردہ عمل", "موسم کا خیال", "اگلا قدم",
        "mumkin masla", "khatray ki satah", "tajweez kardah amal", "mosam ka khayal", "agla qadam",
        "possible issue", "risk level", "recommended action", "weather note", "next step"
    ]
    for heading in headings_to_remove:
        pattern = re.compile(re.escape(heading) + r'\s*:?', re.IGNORECASE)
        cleaned = pattern.sub('', cleaned)

    # 3. Remove unwanted brackets, percentages, special chars
    cleaned = re.sub(r'[\(\)\[\]\{\}%]', ' ', cleaned)
    cleaned = cleaned.replace("⚠", "").replace("-", "—")
    
    # 4. Normalize spaces
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()



def get_available_gemini_models(api_key: str) -> list[str]:
    """Retrieve list of available models supporting generateContent."""
    global _CACHED_AVAILABLE_MODELS
    if _CACHED_AVAILABLE_MODELS is not None:
        return _CACHED_AVAILABLE_MODELS
    available = []
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        models_iterable = genai.list_models()
        while True:
            try:
                m = next(models_iterable)
            except StopIteration:
                break
            except Exception as loop_err:
                logger.warning("Error during iterating models list: %s", loop_err)
                raise loop_err
            
            try:
                methods = getattr(m, 'supported_generation_methods', [])
                if any('generateContent' in method for method in methods):
                    available.append(m.name)
            except Exception as e:
                logger.warning("Skipping model entry check: %s", e)
                continue
        _CACHED_AVAILABLE_MODELS = available
    except Exception as e:
        logger.error("Failed to list models: %s", e)
        raise e
    return available


def classify_gemini_error(exc: Exception) -> tuple[str, str]:
    """Classify the exception into one of the designated error types."""
    exc_name = type(exc).__name__
    exc_msg = str(exc)
    msg_lower = exc_msg.lower()

    # 1. Deadline / Timeout (check FIRST — these are common and should not be misclassified)
    deadline_keywords = ["deadline", "504", "deadlineexceeded"]
    if any(kw in msg_lower for kw in deadline_keywords):
        return "network_error", f"{exc_name}: {exc_msg}"

    # 2. Quota or rate limit
    quota_keywords = ["429", "resourceexhausted", "quota", "rate limit", "limit 0", "free tier request limit", "retry_delay"]
    if any(kw in msg_lower for kw in quota_keywords):
        return "quota_or_rate_limit", f"{exc_name}: {exc_msg}"

    # 3. Invalid API key
    invalid_keywords = [
        "invalid api key", "api key not valid", "permission denied",
        "unauthorized", "403", "api_key_invalid", "authentication",
        "unauthenticated", "401"
    ]
    if any(kw in msg_lower for kw in invalid_keywords):
        return "invalid_api_key", f"{exc_name}: {exc_msg}"

    # 4. Model not available / unsupported
    model_keywords = ["not found", "404", "unsupported method"]
    if any(kw in msg_lower for kw in model_keywords):
        return "model_not_available", f"{exc_name}: {exc_msg}"

    # 5. Network error
    network_keywords = ["connect", "network", "timeout", "dns", "connectionreseterror", "httpconnectionpool"]
    if any(kw in msg_lower for kw in network_keywords):
        return "network_error", f"{exc_name}: {exc_msg}"

    # 6. Invalid image — only if the error specifically says the image data is bad
    #    "Unable to process input image" means the model can't handle the image format,
    #    NOT that the user's image is corrupt. Be very specific here.
    image_corrupt_keywords = ["decode image", "corrupt", "invalid image data", "could not read image"]
    if any(kw in msg_lower for kw in image_corrupt_keywords):
        return "invalid_image", f"{exc_name}: {exc_msg}"

    # 7. Model can't process image (different from corrupt image — this is a model capability issue)
    if "unable to process input image" in msg_lower:
        return "model_image_unsupported", f"{exc_name}: {exc_msg}"

    # 8. Generic bad request / invalid argument
    if "invalid_argument" in msg_lower or "bad_request" in msg_lower or "400" in msg_lower:
        return "bad_request", f"{exc_name}: {exc_msg}"

    # 9. Unknown error
    return "unknown_error", f"{exc_name}: {exc_msg}"


def update_dotenv_model(working_model: str):
    """Update GEMINI_MODEL in .env safely if it has changed."""
    try:
        dotenv_path = ".env"
        if not os.path.exists(dotenv_path) and os.path.exists("backend/.env"):
            dotenv_path = "backend/.env"

        # Read env file
        if os.path.exists(dotenv_path):
            with open(dotenv_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        else:
            lines = []

        # Check if already set to avoid rewriting
        current_env_model = None
        for line in lines:
            if line.startswith("GEMINI_MODEL="):
                current_env_model = line.split("=", 1)[1].strip()
                break

        if current_env_model == working_model:
            return

        updated = False
        new_lines = []
        for line in lines:
            if line.startswith("GEMINI_MODEL="):
                new_lines.append(f"GEMINI_MODEL={working_model}\n")
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(f"GEMINI_MODEL={working_model}\n")

        with open(dotenv_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        logger.info("Successfully updated GEMINI_MODEL in %s to: %s", dotenv_path, working_model)
    except Exception as e:
        logger.error("Failed to update dotenv file: %s", e)


def generate_gemini_farmer_response(
    user_text: str,
    parsed_input: dict = None,
    diagnosis: dict = None,
    weather: dict = None,
    rag_context: str = "",
) -> dict:
    """
    Ask Gemini for a detailed Urdu farmer-facing answer.

    Parameters
    ----------
    user_text : str
        The farmer's original message.
    parsed_input : dict | None
        Parsed input from InputParserAgent (for crop info).
    diagnosis : dict | None
        Diagnosis result (crop, disease, risk).
    weather : dict | None
        Weather data (rain_expected, etc.).

    Returns
    -------
    dict with keys: success, text, error_type, error_message, model_used, available_models, tested_models, working_model
    """
    from services.key_manager import run_with_key_rotation

    def _execute_single_key(api_key: str) -> dict:
        LAST_STATUS["key_loaded"] = bool(api_key)
        LAST_STATUS["key_length"] = len(api_key) if api_key else 0

        if not api_key:
            logger.error("Gemini API key is missing from environment")
            LAST_STATUS["last_error_type"] = "missing_api_key"
            LAST_STATUS["tested_models"] = []
            LAST_STATUS["working_model"] = None
            return {
                "success": False,
                "text": "",
                "error_type": "missing_api_key",
                "error_message": "GEMINI_API_KEY environment variable is missing or empty.",
                "model_used": None,
                "available_models": [],
                "tested_models": [],
                "working_model": None
            }

        # ── 2. Discover available models ─────────────────────────────────────
        available_models = get_available_gemini_models(api_key)
        LAST_STATUS["available_generate_content_models"] = available_models

        # ── 3. Build context lines for the prompt ───────────────────────────
        context_lines: list[str] = []

        if user_text:
            context_lines.append(f"کسان کا پیغام: {user_text}")

        if parsed_input and parsed_input.get("has_image"):
            context_lines.append("کسان نے تصویر اپلوڈ کی ہے۔ (User has uploaded an image)")

        crop = "Unknown"
        if parsed_input:
            crop = parsed_input.get("crop", "Unknown")
            if crop and crop != "Unknown":
                context_lines.append(f"فصل: {crop}")

        if diagnosis:
            disease = diagnosis.get("disease_urdu") or diagnosis.get("disease", "")
            if disease:
                context_lines.append(f"ممکنہ بیماری: {disease}")
            risk = diagnosis.get("risk_level", "")
            if risk:
                context_lines.append(f"خطرے کی سطح: {risk}")

        # Determine weather instructions for Gemini
        weather_instruction = get_weather_instruction(weather)
        context_lines.append(f"موسم کی صورتحال کے لیے ہدایت: {weather_instruction}")

        context_block = "\n".join(context_lines) if context_lines else user_text

        # ── Inject RAG context if available ──────────────────────────────────
        if rag_context:
            context_block = context_block + "\n\n" + rag_context

        # ── 4. System prompt ────────────────────────────────────────────────
        language_hint = parsed_input.get("language_hint", "ur") if parsed_input else "ur"
        if language_hint in ("ur", "urdu"):
            language_hint = "ur"
        elif language_hint not in ("roman_urdu", "english"):
            language_hint = "ur"

        if language_hint == "roman_urdu":
            lang_instruction = (
                "The user has written in Roman Urdu. You MUST reply ONLY in Roman Urdu (Urdu language written in Latin/English characters). Do NOT use Urdu script (Arabic characters). Do NOT reply in English.\n"
                "Use these exact headings without any markdown bold formatting:\n"
                "Mumkin Masla:\n"
                "Khatray ki Satah:\n"
                "Tajweez Kardah Amal:\n"
                "Mosam ka Khayal:\n"
                "Agla Qadam:"
            )
        elif language_hint == "english":
            lang_instruction = (
                "The user has written in English. You MUST reply ONLY in English. Do NOT use Urdu script (Arabic characters). Do NOT reply in Roman Urdu.\n"
                "Use these exact headings without any markdown bold formatting:\n"
                "Possible Issue:\n"
                "Risk Level:\n"
                "Recommended Action:\n"
                "Weather Note:\n"
                "Next Step:"
            )
        else: # ur
            lang_instruction = (
                "The user has written in Urdu script. You MUST reply ONLY in Urdu script. Do NOT use Latin/English characters (except for numbers). Do NOT reply in Roman Urdu or English.\n"
                "Use these exact headings without any markdown bold formatting:\n"
                "ممکنہ مسئلہ:\n"
                "خطرے کی سطح:\n"
                "تجویز کردہ عمل:\n"
                "موسم کا خیال:\n"
                "اگلا قدم:"
            )

        system_prompt = (
            "You are FarmAI, a crop disease and farming assistant for Pakistani farmers.\n\n"
            "You MUST return a JSON object with exactly the following schema, and no other text or markdown wrapping (no ```json code blocks):\n"
            "{\n"
            '  "detailed_response": "string",\n'
            '  "tts_summary": "string"\n'
            "}\n\n"
            "CRITICAL RULES FOR RELEVANT ADVISORIES (when user query/image is agriculture-related):\n"
            "1. detailed_response:\n"
            "   - This is the full detailed answer shown in chat.\n"
            "   - It must use the structured headings in the language style of the user without markdown bold (no asterisks **).\n"
            f"   - {lang_instruction}\n"
            "2. tts_summary:\n"
            "   - This is a very short spoken audio summary for WhatsApp voice reply.\n"
            "   - It must be maximum 2–3 complete sentences and maximum 3 short lines.\n"
            "   - Ideal length is 30–45 words. Absolute maximum is 55 words or 350 characters.\n"
            "   - It must NOT include headings, bullets, numbering, markdown, tables, brackets, percentages, or technical formatting.\n"
            "   - It must NOT summarize every section separately.\n"
            "   - It should only mention: main problem, one likely cause, one or two immediate safe actions, and next step if needed.\n"
            "   - It must be complete and natural, not cut off mid-sentence.\n"
            "   - It must follow the same language style as the user.\n\n"
            "CRITICAL RULE FOR IRRELEVANT INPUTS (TEXT OR IMAGES):\n"
            "- If the user asks an unrelated question (politics, jokes, movies, etc.) OR if the uploaded image is completely blank, solid color, black, or not related to crops, plants, pests, farming, or agriculture (e.g., a person, a car, or a blank screen), you MUST politely refuse.\n"
            "- In this case, detailed_response must be the polite refusal paragraph, and tts_summary must be the same refusal or a slightly shorter spoken version. Do NOT add headings for irrelevant cases.\n"
            "- The refusal message must be exactly one of the following depending on the language style:\n"
            "  * Urdu script: \"یہ سسٹم صرف فصل، پودوں کی بیماری، کیڑے، کھاد، پانی، موسم، اور زرعی مسائل کے لیے بنایا گیا ہے۔ براہ کرم اپنی فصل کا مسئلہ، تصویر، یا وائس نوٹ بھیجیں۔\"\n"
            "  * Roman Urdu: \"Yeh system sirf faslon, podon ki bemari, keeron, khaad, pani, mosam, aur zaraati masail ke liye banaya gaya hai. Barah-e-karam apni fasal ka masla, tasveer, ya voice note bhejein.\"\n"
            "  * English: \"This system is only built for crops, plant diseases, pests, fertilizer, irrigation, weather impact, and farming problems. Please send your crop issue, image, or voice note.\"\n\n"
            "General Rules:\n"
            "* Do not mix languages.\n"
            "* Do not use English headings in Urdu/Roman Urdu answers.\n"
            "* Do not use Urdu script in English answers.\n"
            "* Do not use Urdu script in Roman Urdu answers.\n"
            "* Do not use markdown tables.\n"
            "* Do not use backend/agent/Gemini/model/TTS terms.\n"
            "* No exact pesticide dosage unless verified.\n"
            "* Recommend local agriculture expert for chemical treatment.\n"
            "* Keep answer useful and clear.\n"
            "* Do not use markdown bold formatting like asterisks (**) for headings or text.\n"
            "Crop-Specific Guidance:\n"
            "- If crop is Unknown but the query/image is relevant to farming:\n"
            "  * Response must ask for: crop name, clear close-up photo, affected part (leaf, fruit, stem, root), and weather/location if relevant.\n\n"
            "Multimodal / Image Analysis Rules:\n"
            "- If an image is provided: inspect the image carefully. Verify if it is related to crops, plants, pests, plant diseases, soil, or farming.\n"
            "- If the image is relevant to farming, analyze the crop or plant issue. If text context is provided, combine both text and image to give a better answer. If only the image is provided and text is empty, analyze the issue from the image and default to Urdu script (or the specified language style if hint is available).\n"
            "- If the crop or problem is not fully clear from the image, but the image is indeed related to farming (e.g. shows a farm, plant, field, leaf, or soil but not clearly diseased), politely ask the farmer for a clearer close-up image or more details, while still using the structured format.\n"
        )

        full_prompt = f"{system_prompt}\n---\n{context_block}"

        # ── 5. Auto Model Selection ──────────────────────────────────────────
        global _CACHED_WORKING_MODEL
        
        def clean_model_name(name: str) -> str:
            if name.startswith("models/"):
                return name[7:]
            return name

        normalized_available = {clean_model_name(m): m for m in available_models}

        def get_actual_model_name(name: str) -> str:
            c_name = clean_model_name(name)
            return normalized_available.get(c_name, name)

        # 1st Choice: Memory cache -> Environment variable -> Default
        env_model = os.getenv("GEMINI_MODEL", "").strip()
        first_choice = _CACHED_WORKING_MODEL or env_model or "gemini-2.5-flash"
        first_choice = get_actual_model_name(first_choice)

        models_to_try = [first_choice]

        # Try to find exactly one fallback candidate that is different from first_choice
        fallback_options = [
            env_model,
            "gemini-2.5-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-2.5-flash-lite"
        ]
        for opt in fallback_options:
            if opt:
                opt_actual = get_actual_model_name(opt)
                if clean_model_name(opt_actual) != clean_model_name(first_choice):
                    if available_models and (clean_model_name(opt_actual) not in normalized_available):
                        continue
                    models_to_try.append(opt_actual)
                    break

        # ── 6. Try Models in Sequence ────────────────────────────────────────
        tested_models = []
        working_model = None
        last_error_type = "unknown_error"
        last_error_msg = ""
        selected_model = None

        import google.generativeai as genai
        genai.configure(api_key=api_key)

        for model_name in models_to_try:
            logger.info("Attempting Gemini call with model: %s", model_name)
            selected_model = model_name
            tested_models.append(model_name)
            LAST_STATUS["tested_models"] = list(tested_models)
            LAST_STATUS["selected_model"] = model_name

            try:
                model = genai.GenerativeModel(model_name)
                
                image_bytes = parsed_input.get("image_bytes") if parsed_input else None
                image_mime = parsed_input.get("image_mime") if parsed_input else None
                
                gen_config = {"response_mime_type": "application/json"}
                
                if image_bytes and image_mime:
                    # Longer timeout for multimodal requests (images need more processing time)
                    req_opts = {"timeout": 45.0}
                    logger.info(
                        "[Gemini Image] Sending image to model %s: mime=%s, bytes=%d",
                        model_name, image_mime, len(image_bytes)
                    )
                    image_part = {
                        "mime_type": image_mime,
                        "data": image_bytes
                    }
                    response = model.generate_content([full_prompt, image_part], generation_config=gen_config, request_options=req_opts)
                else:
                    # Shorter timeout for text-only requests
                    req_opts = {"timeout": 20.0}
                    response = model.generate_content(full_prompt, generation_config=gen_config, request_options=req_opts)

                raw_text = response.text if response and hasattr(response, "text") else ""
                if not raw_text or not raw_text.strip():
                    logger.warning("Model %s returned empty response", model_name)
                    last_error_type = "empty_response"
                    last_error_msg = "Model returned empty response"
                    continue

                # Strip code fences if present
                raw_text = raw_text.strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                elif raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()

                import json
                try:
                    data = json.loads(raw_text)
                    detailed_response = data.get("detailed_response", "")
                    tts_summary = data.get("tts_summary", "")
                except Exception as json_err:
                    logger.warning("JSON parsing failed for model %s: %s. Raw text: %s", model_name, json_err, raw_text)
                    detailed_response = raw_text
                    tts_summary = ""

                validated_detailed = _validate_response(detailed_response, language_hint, crop)
                if validated_detailed:
                    headings_list = HEADINGS_MAP.get(language_hint, HEADINGS_MAP["ur"])
                    has_headings = any(key.lower() in validated_detailed.lower() for key, _ in headings_list)
                    
                    cleaned_tts = clean_tts_summary_format(tts_summary)
                    if is_too_short_or_invalid(cleaned_tts, language_hint, has_headings):
                        logger.info("tts_summary is missing or invalid. Generating safe summary.")
                        tts_summary = generate_safe_tts_summary(validated_detailed, language_hint)
                    else:
                        tts_summary = cleaned_tts

                    words_summary = len(tts_summary.split())
                    chars_summary = len(tts_summary)
                    preview_summary = tts_summary[:120]
                    logger.info("tts_summary_word_count: %d", words_summary)
                    logger.info("tts_summary_length_chars: %d", chars_summary)
                    logger.info("tts_summary_preview_first_120_chars: %s", preview_summary)

                    logger.info("Gemini response accepted using model %s (%d chars detailed, %d chars summary)", model_name, len(validated_detailed), len(tts_summary))
                    working_model = model_name
                    _CACHED_WORKING_MODEL = model_name
                    LAST_STATUS["working_model"] = model_name
                    LAST_STATUS["selected_model"] = model_name
                    LAST_STATUS["last_error_type"] = None
                    
                    # Update env file if working_model is different from env_model
                    update_dotenv_model(working_model)
                    
                    return {
                        "success": True,
                        "text": validated_detailed,
                        "tts_summary": tts_summary,
                        "error_type": None,
                        "error_message": None,
                        "model_used": model_name,
                        "available_models": available_models,
                        "tested_models": tested_models,
                        "working_model": working_model
                    }
                else:
                    logger.warning("Validation failed for response from model %s", model_name)
                    last_error_type = "validation_failed"
                    last_error_msg = "Response validation failed"
                    continue

            except Exception as exc:
                err_type, err_msg = classify_gemini_error(exc)
                logger.warning("Gemini call failed with model %s (%s)", model_name, err_msg)
                last_error_type = err_type
                last_error_msg = err_msg
                LAST_STATUS["last_error_type"] = err_type
                if err_type in ("quota_or_rate_limit", "invalid_api_key"):
                    logger.error("Aborting model trial loop because API key hit %s", err_type)
                    raise exc

        # All models failed or were rejected
        logger.error("All Gemini models failed or responses were invalid. Final error type: %s", last_error_type)
        LAST_STATUS["working_model"] = None
        LAST_STATUS["last_error_type"] = last_error_type
        
        # If the error is due to an invalid/corrupt image, return a clean farmer-facing response
        image_bytes = parsed_input.get("image_bytes") if parsed_input else None
        if image_bytes and last_error_type == "invalid_image":
            error_texts = {
                "ur": "تصویر پڑھنے میں مسئلہ آ رہا ہے۔ براہ کرم صاف تصویر دوبارہ بھیجیں۔",
                "roman_urdu": "Tasveer parhne mein masla aa raha hai. Barah-e-karam saaf tasveer dobara bhejein.",
                "english": "There is a problem processing the image. Please send a clear image again."
            }
            friendly_text = error_texts.get(language_hint, error_texts["ur"])
            return {
                "success": True,  # Treat as successful pipeline result so it renders nicely
                "text": friendly_text,
                "error_type": None,
                "error_message": None,
                "model_used": selected_model,
                "available_models": available_models,
                "tested_models": tested_models,
                "working_model": None
            }

        return {
            "success": False,
            "text": "",
            "error_type": last_error_type,
            "error_message": last_error_msg,
            "model_used": selected_model,
            "available_models": available_models,
            "tested_models": tested_models,
            "working_model": None
        }

    # Execute with key rotation using the CHAT pool
    rotation_res = run_with_key_rotation("CHAT", _execute_single_key)
    
    if rotation_res.get("success"):
        res = rotation_res["result"]
        res["pool"] = rotation_res.get("pool")
        res["key_index_used"] = rotation_res.get("key_index_used")
        res["attempts"] = rotation_res.get("attempts")
        return res
    else:
        return {
            "success": False,
            "text": "",
            "error_type": rotation_res.get("error_type", "unknown_error"),
            "error_message": rotation_res.get("error_message", "All keys failed"),
            "model_used": None,
            "available_models": [],
            "tested_models": [],
            "working_model": None,
            "pool": rotation_res.get("pool"),
            "key_index_used": rotation_res.get("key_index_used"),
            "attempts": rotation_res.get("attempts")
        }
