"""
FarmAI Core Wrapper Service
Exposes process_farmai_query to coordinate agent pipeline operations.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from agents.input_parser import parse_input
from agents.diagnosis_agent import generate_mock_diagnosis
from agents.context_agent import get_context
from agents.action_planner import plan_actions
from agents.execution_agent import execute_actions
from agents.recovery_agent import apply_recovery
from agents.outcome_agent import format_outcome
from services.gemini_service import generate_safe_tts_summary
from services.session_memory import (
    get_session,
    update_session,
    save_location,
    get_last_location,
)

logger = logging.getLogger(__name__)

_FALLBACK_FARMER_RESPONSE = (
    "آپ کا پیغام موصول ہو گیا ہے۔ "
    "بہتر مشورے کے لیے فصل کی صاف تصویر یا مزید تفصیل بھیجیں۔"
)

AFFIRMATIVE_KEYWORDS = {
    "yes", "y", "haan", "han", "hanji", "jee", "ji", "audio", "sunao", 
    "suna do", "awaz", "آواز", "ہاں", "جی", "سنائیں", "سنا دیں"
}

NEGATIVE_KEYWORDS = {
    "no", "nahi", "nahin", "no thanks", "nahi chahiye", "نہیں", "نہيں", "نہیں۔"
}

def is_affirmative_response(text: Optional[str]) -> bool:
    """Helper to detect if user response confirms audio playback."""
    if not text:
        return False
    clean_txt = text.strip().lower().replace(".", "").replace("?", "").replace("!", "")
    return clean_txt in AFFIRMATIVE_KEYWORDS

def is_negative_response(text: Optional[str]) -> bool:
    """Helper to detect if user response refuses audio playback."""
    if not text:
        return False
    clean_txt = text.strip().lower().replace(".", "").replace("?", "").replace("!", "")
    return clean_txt in NEGATIVE_KEYWORDS

def is_weather_question(text: Optional[str]) -> bool:
    """Helper to detect if the query is asking about weather/spray/watering advice."""
    if not text:
        return False
    text_lower = text.lower()
    weather_keywords = [
        "spray", "paani", "pani", "mosam", "weather", "barish", "rain", 
        "سپرے", "پانی", "موسم", "بارش", "water", "irrigation", "forecast"
    ]
    return any(kw in text_lower or kw in text for kw in weather_keywords)

def get_audio_offer_text(lang: str) -> str:
    """Get language-appropriate audio offer prompt."""
    if lang == "ur" or lang == "urdu":
        return "کیا آپ اس مشورے کی آڈیو سمری سننا چاہتے ہیں؟ اگر ہاں، تو 'ہاں' لکھیں۔"
    elif lang == "english":
        return "Would you like to hear an audio summary of this advice? Reply 'yes' if you want audio."
    else:
        return "Kya aap is mashwaray ki audio summary sunna chahtay hain? Agar haan, to 'haan' likhein."

async def _process_farmai_query_impl(
    user_id: str,
    source: str = "integration",
    message_type: str = "text",
    text: Optional[str] = None,
    crop: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    image_path: Optional[str] = None,
    audio_path: Optional[str] = None,
    base_url: Optional[str] = None,
    language_hint: Optional[str] = None,
) -> dict:
    """
    Main entry point function to process crop queries for integrations.
    Supports 'text', 'image', 'text_image', and 'location' message processing.
    """
    session = get_session(user_id)
    pending_offer = session.get("pending_audio_offer", False)
    last_lang = session.get("last_language", "ur")
    last_crop = session.get("last_crop")

    # ── 1. Check for pending audio offer confirmations ────────────────────
    if pending_offer and message_type == "text" and text:
        # User replied to audio offer
        if is_affirmative_response(text):
            print("[Debug Log] Received audio confirmation: affirmative")
            print(f"[Debug Log] pending_audio_offer: {pending_offer}")
            
            saved_summary = session.get("last_tts_summary")
            summary_found = bool(saved_summary)
            print(f"[Debug Log] Saved TTS summary found: {summary_found}")
            
            if not saved_summary or not saved_summary.strip():
                print("[Debug Log] Summary missing, returning error")
                err_lang = last_lang or "ur"
                if err_lang in ("ur", "urdu"):
                    err_msg = "پہلے سے کوئی مشورہ موجود نہیں ہے۔ براہ کرم نیا سوال پوچھیں۔"
                elif err_lang == "english":
                    err_msg = "No previous advice found. Please ask a new question."
                else:
                    err_msg = "Pehle se koi mashwara maujood nahi hai. Barah-e-karam naya sawal poochein."
                
                return {
                    "status": "error",
                    "message": err_msg
                }

            print(f"[Debug Log] tts_summary length: {len(saved_summary)}")
            print(f"[Debug Log] language_hint used: {last_lang}")
            print("[Debug Log] generate_tts_audio called")

            # Trim the text to about 350-500 characters maximum, preferring sentence boundary
            trimmed_summary = saved_summary
            if len(trimmed_summary) > 500:
                delimiters = [".", "?", "!", "\n", "\u06d4"]
                best_idx = -1
                for idx in range(500, 350, -1):
                    if idx < len(trimmed_summary) and trimmed_summary[idx] in delimiters:
                        best_idx = idx + 1
                        break
                if best_idx != -1:
                    trimmed_summary = trimmed_summary[:best_idx].strip()
                else:
                    trimmed_summary = trimmed_summary[:500].strip() + "..."

            # Generate audio response using the existing TTS service
            logger.info("[LANG_TRACE] tts_language=%s tts_summary_preview=%s", last_lang, (trimmed_summary[:120] if trimmed_summary else ""))
            from services.tts_service import generate_tts_audio
            tts_res = generate_tts_audio(trimmed_summary, last_lang)
            tts_success = tts_res.get("success", False)
            print(f"[Debug Log] generate_tts_audio returned success: {tts_success}")

            if tts_success:
                filename = tts_res.get("filename")
                print(f"[Debug Log] Runtime filename returned: {filename}")
                
                if not filename:
                    print("[Debug Log] Failure: success returned True but filename is missing")
                    update_session(user_id, {
                        "audio_generation_status": "failed",
                        "pending_audio_offer": True
                    })
                    return {
                        "status": "error",
                        "message": "Audio bananay mein masla aa raha hai. Text jawab phir bhi available hai."
                    }

                # Locate WAV file path
                backend_dir = Path(__file__).resolve().parent.parent
                wav_path = backend_dir / "static" / "audio" / filename
                print(f"[Debug Log] WAV path: {wav_path}")

                wav_exists = wav_path.is_file()
                wav_size = wav_path.stat().st_size if wav_exists else 0
                print(f"[Debug Log] WAV exists: {wav_exists}")
                print(f"[Debug Log] WAV size: {wav_size} bytes")

                # Verify file existence and non-emptiness
                if not wav_exists or wav_size == 0:
                    print("[Debug Log] Verification failed: WAV file does not exist or is empty")
                    update_session(user_id, {
                        "audio_generation_status": "failed",
                        "pending_audio_offer": True
                    })
                    return {
                        "status": "error",
                        "message": "Audio file generation failed: generated file is empty or missing."
                    }

                # Set up dynamically built URLs
                resolved_base = base_url
                if not resolved_base:
                    resolved_base = os.getenv("BASE_URL", "http://127.0.0.1:8000")
                resolved_base = resolved_base.strip().rstrip('/')

                audio_url = f"{resolved_base}/static/audio/{filename}"
                audio_format = "wav_fallback"
                audio_mime_type = "audio/wav"
                whatsapp_ready = False
                ogg_created = False
                wav_created = True

                print("[Debug Log] OGG conversion attempted: True")
                
                # Attempt OGG OPUS conversion
                from services.audio_converter import convert_wav_to_ogg_opus
                conv_res = convert_wav_to_ogg_opus(str(wav_path))

                if conv_res.get("success"):
                    ogg_filename = conv_res["filename"]
                    ogg_path = backend_dir / "static" / "audio" / ogg_filename
                    
                    ogg_exists = ogg_path.is_file()
                    ogg_size = ogg_path.stat().st_size if ogg_exists else 0
                    print(f"[Debug Log] OGG exists: {ogg_exists}")
                    print(f"[Debug Log] OGG size: {ogg_size} bytes")

                    if ogg_exists and ogg_size > 0:
                        audio_url = f"{resolved_base}/static/audio/{ogg_filename}"
                        audio_format = "ogg_opus"
                        audio_mime_type = "audio/ogg"
                        whatsapp_ready = True
                        ogg_created = True
                        print(f"[Debug Log] OGG file verified successfully. URL: {audio_url}")
                    else:
                        print("[Debug Log] OGG file exists but is empty. Falling back to WAV.")
                else:
                    print(f"[Debug Log] OGG conversion failed: {conv_res.get('error_message')}. Falling back to WAV.")

                # Format localized notification string
                if last_lang in ("ur", "urdu"):
                    confirm_msg = "آڈیو سمری تیار ہے۔"
                elif last_lang == "english":
                    confirm_msg = "Audio summary is ready."
                else:
                    confirm_msg = "Audio summary tayyar hai."

                print(f"[Debug Log] final dynamic audio_url: {audio_url}")
                print(f"[Debug Log] whatsapp_ready value: {whatsapp_ready}")

                # Update session states on success
                update_session(user_id, {
                    "pending_audio_offer": False,
                    "last_audio_url": audio_url,
                    "last_audio_format": audio_format,
                    "last_audio_mime_type": audio_mime_type,
                    "whatsapp_ready": whatsapp_ready,
                    "audio_generation_status": "ready",
                })

                return {
                    "status": "success",
                    "message_type": "audio_response",
                    "farmer_response": confirm_msg,
                    "tts_summary": saved_summary,
                    "audio_url": audio_url,
                    "audio_format": audio_format,
                    "audio_mime_type": audio_mime_type,
                    "whatsapp_ready": whatsapp_ready,
                    "audio_available": True,
                    "expects_audio_confirmation": False,
                    "metadata": {
                        "used_saved_tts_summary": True,
                        "pending_audio_offer": False,
                        "wav_created": wav_created,
                        "ogg_created": ogg_created
                    }
                }
            else:
                # TTS generation failed
                print("[Debug Log] generate_tts_audio failed to execute successfully")
                update_session(user_id, {
                    "audio_generation_status": "failed",
                    "pending_audio_offer": True
                })
                return {
                    "status": "error",
                    "message": "Audio bananay mein masla aa raha hai. Text jawab phir bhi available hai."
                }

        elif is_negative_response(text):
            print("[Debug Log] Received audio confirmation: negative")
            # Clear pending offer
            update_session(user_id, {
                "pending_audio_offer": False
            })

            if last_lang in ("ur", "urdu"):
                refuse_confirm = "ٹھیک ہے، جب ضرورت ہو تو بتا دیں۔"
            elif last_lang == "english":
                refuse_confirm = "Alright, let know if you need it later."
            else:
                refuse_confirm = "Theek hai, jab zaroorat ho to bata dein."

            return {
                "status": "success",
                "message_type": "text_response",
                "farmer_response": refuse_confirm,
                "tts_summary": refuse_confirm,
                "audio_url": None,
                "audio_available": False,
                "expects_audio_confirmation": False,
                "metadata": {
                    "pending_audio_offer": False
                }
            }

        # If user input is neither yes nor no, fall through to process as a new query

    # ── 2. Resolve coordinates ───────────────────────────────────────────
    location_saved = False
    used_saved_location = False
    
    current_lat = latitude
    current_lon = longitude
    
    if current_lat is not None and current_lon is not None:
        save_location(user_id, current_lat, current_lon)
        location_saved = True
    else:
        saved_loc = get_last_location(user_id)
        if saved_loc:
            current_lat = saved_loc.get("latitude")
            current_lon = saved_loc.get("longitude")
            used_saved_location = True

    # ── 2.3 Special branch for weather-based spray and irrigation/water queries ──
    if message_type == "text" and not image_path and text:
        from utils.helpers import is_weather_action_query
        try:
            if is_weather_action_query(text):
                from utils.helpers import detect_language
                from services.weather_service import get_mock_weather
                
                lang = language_hint or detect_language(text)
                location_available = current_lat is not None and current_lon is not None
                
                logger.info("[WEATHER_ACTION] detected=True language_hint=%s location_available=%s", lang, str(location_available).lower())
                
                text_lower = text.lower()
                spray_kws = ["spray", "سپرے", "اسپرے", "dawa", "dawai", "دوائی", "زہر"]
                has_spray = any(kw in text_lower for kw in spray_kws)
                intent = "spray" if has_spray else "water"
                logger.info("[WEATHER_ACTION] intent=%s response_mode=one_paragraph", intent)
                
                if not location_available:
                    # Missing location response
                    if lang in ("ur", "urdu", "unknown"):
                        refusal_msg = "اسپرے یا پانی کا صحیح مشورہ دینے کے لیے مجھے آپ کی لوکیشن کی ضرورت ہے، کیونکہ بارش، ہوا اور درجہ حرارت کا اس پر گہرا اثر ہوتا ہے۔ براہ کرم واٹس ایپ پر اپنی لوکیشن پن بھیجیں، پھر میں بتا دوں گا کہ آج اسپرے یا پانی دینا ٹھیک ہے یا نہیں۔"
                    elif lang == "roman_urdu":
                        refusal_msg = "Spray ya pani ka sahi mashwara dene ke liye mujhe aap ki location chahiye, kyun ke barish, hawa aur temperature ka asar hota hai. Barah-e-karam WhatsApp location pin bhej dein, phir main bata dunga ke aaj spray ya pani dena theek hai ya nahi."
                    elif lang == "english":
                        refusal_msg = "To give you accurate advice on spraying or irrigation, I need your location because weather conditions like rain and wind play a critical role. Please share your WhatsApp location pin so I can guide you."
                    elif lang in ("punjabi", "pa", "panjabi"):
                        refusal_msg = "اسپرے یا پانی دین دا صحیح مشورہ دین لئی مینوں تہاڈی لوکیشن دی لوڑ اے، کیونکہ بارش، ہوا تے درجہ حرارت دا اثر پیندا اے۔ مہربانی کر کے واٹس ایپ لوکیشن پن بھیجو، فیر میں دس دیاں گا کہ اج اسپرے یا پانی دینا ٹھیک اے یا نہیں۔"
                    elif lang in ("siraiki", "seraiki", "saraiki", "skr", "saraki"):
                        refusal_msg = "اسپرے یا پانی ڈیون دا صحیح مشورہ ڈیون کیتے میکوں تہاڈی لوکیشن دی لوڑ اے، کیونکہ بارش، ہوا تے درجہ حرارت دا اثر تھیندے۔ مہربانی کر کے واٹس ایپ لوکیشن پن بھیجو، ولا میں ڈس ڈیساں کہ اج اسپرے یا پانی ڈیون ٹھیک اے یا نہیں۔"
                    else:
                        refusal_msg = "اسپرے یا پانی کا صحیح مشورہ دینے کے لیے مجھے آپ کی لوکیشن کی ضرورت ہے، کیونکہ بارش، ہوا اور درجہ حرارت کا اس پر گہرا اثر ہوتا ہے۔ براہ کرم واٹس ایپ پر اپنی لوکیشن پن بھیجیں، پھر میں بتا دوں گا کہ آج اسپرے یا پانی دینا ٹھیک ہے یا نہیں۔"
                    
                    update_session(user_id, {
                        "pending_audio_offer": True,
                        "last_tts_summary": refusal_msg,
                        "last_farmer_response": refusal_msg[:300],
                        "last_audio_language": lang,
                        "last_audio_url": None,
                        "last_audio_format": None,
                        "last_message_type": message_type,
                        "last_crop": last_crop,
                        "last_language": lang,
                        "last_question": text[:100],
                        "last_context": "Farmer asked weather-action query but location was missing."
                    })
                    
                    offer_text = get_audio_offer_text(lang)
                    
                    return {
                        "status": "success",
                        "user_id": user_id,
                        "source": source,
                        "message_type": message_type,
                        "farmer_response": refusal_msg,
                        "tts_summary": refusal_msg,
                        "audio_offer_text": offer_text,
                        "audio_available": True,
                        "expects_audio_confirmation": True,
                        "audio_url": None,
                        "language": lang,
                        "metadata": {
                            "pending_audio_offer": True,
                            "session_used": True,
                            "location_saved": False,
                            "used_saved_location": False,
                            "last_crop": last_crop,
                            "weather_action_intent": intent,
                            "location_available": False,
                        }
                    }
                else:
                    weather = get_mock_weather(current_lat, current_lon)
                    rain_expected = weather.get("rain_expected", False)
                    temp = weather.get("temperature", 32)
                    spray_safe = weather.get("spray_safe", True)
                    
                    if intent == "spray":
                        if rain_expected or not spray_safe:
                            if lang in ("ur", "urdu", "unknown"):
                                advice_msg = "آپ کی لوکیشن کے موسم کے مطابق آج بارش یا ناموافق موسم کا امکان ہے، اس لیے ابھی اسپرے کرنے سے پرہیز کریں کیونکہ بارش کی وجہ سے دوائی اثر کھو سکتی ہے۔ اسپرے کے لیے پرسکون اور خشک موسم کا انتظار کریں اور کیمیکل کے استعمال میں مقامی زرعی ماہر یا بوتل پر لکھی ہدایات پر عمل کریں۔"
                            elif lang == "roman_urdu":
                                advice_msg = "Aap ki location ke mosam ke mutabiq aaj barish ya unfavorable weather ka imkan hai, is liye abhi spray karne se parhez karein kyun ke barish ki wajah se dawai zaya ho sakti hai. Spray ke liye calm aur khushk mosam ka intezar karein aur chemical ke istemal mein local expert ki advice zaroor lein."
                            elif lang == "english":
                                advice_msg = "According to your location's weather forecast, rain or unfavorable conditions are expected today. Please avoid spraying as the chemical can wash away. Wait for calm, dry weather, and always follow label instructions or consult a local agricultural expert."
                            elif lang in ("punjabi", "pa", "panjabi"):
                                advice_msg = "تہاڈی لوکیشن دے موسم دے مطابق اج بارش یا خراب موسم دا امکان اے، ایس لئی ہن اسپرے کرن توں پرہیز کرو کیونکہ بارش نال دوائی ضائع ہو سکدی اے۔ اسپرے لئی پرسکون تے خشک موسم دا انتظار کرو تے کیمیکل ورتن ویلے مقامی ماہر یا بوتل تے لکھیاں ہدایات تے عمل کرو۔"
                            elif lang in ("siraiki", "seraiki", "saraiki", "skr", "saraki"):
                                advice_msg = "تہاڈی لوکیشن دے موسم دے مطابق اج بارش یا خراب موسم دا امکان اے، ایں کیتے ہن اسپرے کرن توں پرہیز کرو کیونکہ بارش نال دوائی ضائع تھی سگدی اے۔ اسپرے کیتے پرسکون تے خشک موسم دا انتظار کرو تے کیمیکل ورتن ویلے مقامی ماہر یا بوتل تے لکھیاں ہدایات تے عمل کرو۔"
                            else:
                                advice_msg = "آپ کی لوکیشن کے موسم کے مطابق آج بارش یا ناموافق موسم کا امکان ہے، اس لیے ابھی اسپرے کرنے سے پرہیز کریں کیونکہ بارش کی وجہ سے دوائی اثر کھو سکتی ہے۔ اسپرے کے لیے پرسکون اور خشک موسم کا انتظار کریں اور کیمیکل کے استعمال میں مقامی زرعی ماہر یا بوتل پر لکھی ہدایات پر عمل کریں۔"
                        else:
                            if lang in ("ur", "urdu", "unknown"):
                                advice_msg = "آپ کی لوکیشن کے موسم کے مطابق آج اسپرے کرنا محفوظ ہے کیونکہ بارش کا امکان نہیں ہے اور موسم پرسکون ہے۔ تیز ہوا میں اسپرے کرنے سے بچیں تاکہ دوائی ضائع نہ ہو، اور کیمیکل کے استعمال میں بوتل پر لکھی ہدایات اور حفاظتی تدابیر پر عمل کریں۔"
                            elif lang == "roman_urdu":
                                advice_msg = "Aap ki location ke mosam ke mutabiq aaj spray karna bilkul safe hai kyun ke barish ka koi imkan nahi hai aur mosam calm hai. Tez hawa mein spray karne se bachein taake dawai zaya na ho, aur chemical istemal karte waqt label ki instructions par amal karein."
                            elif lang == "english":
                                advice_msg = "Based on your location's weather, it is safe to spray today as no rain is forecast and conditions are calm. Avoid spraying in strong winds to prevent chemical drift, and always follow the label's safety instructions."
                            elif lang in ("punjabi", "pa", "panjabi"):
                                advice_msg = "تہاڈی لوکیشن دے موسم دے مطابق اج اسپرے کرنا بالکل محفوظ اے کیونکہ بارش دا کوئی امکان نہیں اے تے موسم پرسکون اے۔ تیز ہوا وچ اسپرے نہ کرو تاں جے دوائی ضائع نہ ہووے، تے کیمیکل ورتن ویلے بوتل تے لکھیاں ہدایات تے عمل کرو۔"
                            elif lang in ("siraiki", "seraiki", "saraiki", "skr", "saraki"):
                                advice_msg = "تہاڈی لوکیشن دے موسم دے مطابق اج اسپرے کرنا بالکل محفوظ اے کیونکہ بارش دا کوئی امکان کائنی تے موسم پرسکون اے۔ تیز ہوا وچ اسپرے نہ کرو تاں جے دوائی ضائع نہ تھیوے، تے کیمیکل ورتن ویلے بوتل تے لکھیاں ہدایات تے عمل کرو۔"
                            else:
                                advice_msg = "آپ کی لوکیشن کے موسم کے مطابق آج اسپرے کرنا محفوظ ہے کیونکہ بارش کا امکان نہیں ہے اور موسم پرسکون ہے۔ تیز ہوا میں اسپرے کرنے سے بچیں تاکہ دوائی ضائع نہ ہو، اور کیمیکل کے استعمال میں بوتل پر لکھی ہدایات اور حفاظتی تدابیر پر عمل کریں۔"
                    else: # water
                        if rain_expected:
                            if lang in ("ur", "urdu", "unknown"):
                                advice_msg = "آپ کی لوکیشن کے موسم کے مطابق آج بارش متوقع ہے، اس لیے ابھی فصل کو پانی دینے سے گریز کریں یا پانی کی مقدار کم کر دیں تاکہ زیادہ نمی سے جڑیں خراب نہ ہوں اور وسائل کی بچت ہو۔ ہمیشہ پانی دینے سے پہلے مٹی کی نمی ضرور چیک کریں۔"
                            elif lang == "roman_urdu":
                                advice_msg = "Aap ki location ke mosam ke mutabiq aaj barish expected hai, is liye abhi fasal ko pani dene se greez karein ya pani ki quantity kam kar dein taake zayada nami se jarein kharab na hon. Pani dene se pehle mitti ki nami zaroor check karein."
                            elif lang == "english":
                                advice_msg = "Rain is expected in your location today, so we recommend holding off or reducing irrigation to save water and prevent waterlogging. Always check the soil moisture levels before deciding to irrigate."
                            elif lang in ("punjabi", "pa", "panjabi"):
                                advice_msg = "تہاڈی لوکیشن دے موسم دے مطابق اج بارش دا امکان اے، ایس لئی ہن فصل نوں پانی دین توں پرہیز کرو یا پانی دی مقدار گھٹ کر دیو تاں جے زیادہ نمی نال جڑاں خراب نہ ہون۔ پانی دین توں پہلے مٹی دی نمی لازمی چیک کرو۔"
                            elif lang in ("siraiki", "seraiki", "saraiki", "skr", "saraki"):
                                advice_msg = "تہاڈی لوکیشن دے موسم دے مطابق اج بارش دا امکان اے، ایں کیتے ہن فصل کوں پانی ڈیون توں پرہیز کرو یا پانی دی مقدار گھٹ کر ڈیو تاں جے زیادہ نمی نال جڑاں خراب نہ تھین۔ پانی ڈیون توں پہلے مٹی دی نمی لازمی چیک کرو۔"
                            else:
                                advice_msg = "آپ کی لوکیشن کے موسم کے مطابق آج بارش متوقع ہے، اس لیے ابھی فصل کو پانی دینے سے گریز کریں یا پانی کی مقدار کم کر دیں تاکہ زیادہ نمی سے جڑیں خراب نہ ہوں اور وسائل کی بچت ہو۔ ہمیشہ پانی دینے سے پہلے مٹی کی نمی ضرور چیک کریں۔"
                        else:
                            if temp > 35:
                                if lang in ("ur", "urdu", "unknown"):
                                    advice_msg = "آپ کی لوکیشن پر آج موسم کافی گرم اور خشک ہے اور بارش کا امکان نہیں ہے، اس لیے فصل کو ہلکا پانی دینے کی ضرورت ہو سکتی ہے۔ زیادہ پانی دینے سے بچیں اور مٹی کی نمی کی حالت دیکھ کر ہی پانی کا فیصلہ کریں۔"
                                elif lang == "roman_urdu":
                                    advice_msg = "Aap ki location par aaj mosam kaafi garm aur khushk hai aur barish ka koi imkan nahi hai, is liye fasal ko light irrigation ki zaroorat ho sakti hai. Zayada pani dene se parhez karein aur mitti ki nami dekh kar hi pani dein."
                                elif lang == "english":
                                    advice_msg = "The weather in your location today is quite hot and dry with no rain expected, so your crop may need light watering. Avoid overwatering and check the soil moisture beforehand."
                                elif lang in ("punjabi", "pa", "panjabi"):
                                    advice_msg = "تہاڈی لوکیشن تے اج موسم کافی گرم تے خشک اے تے بارش دا کوئی امکان نہیں اے، ایس لئی فصل نوں ہلکا پانی دین دی لوڑ ہو سکدی اے۔ زیادہ پانی دین توں بچو تے مٹی دی نمی دیکھ کے ہی پانی دا فیصلہ کرو۔"
                                elif lang in ("siraiki", "seraiki", "saraiki", "skr", "saraki"):
                                    advice_msg = "تہاڈی لوکیشن تے اج موسم کافی گرم تے خشک اے تے بارش دا کوئی امکان کائنی، ایں کیتے فصل کوں ہلکا پانی ڈیون دی لوڑ تھی سگدی اے۔ زیادہ پانی ڈیون توں بچو تے مٹی دی نمی ڈیکھ کے ہی پانی دا فیصلہ کرو۔"
                                else:
                                    advice_msg = "آپ کی لوکیشن پر آج موسم کافی گرم اور خشک ہے اور بارش کا امکان نہیں ہے، اس لیے فصل کو ہلکا پانی دینے کی ضرورت ہو سکتی ہے۔ زیادہ پانی دینے سے بچیں اور مٹی کی نمی کی حالت دیکھ کر ہی پانی کا فیصلہ کریں۔"
                            else:
                                if lang in ("ur", "urdu", "unknown"):
                                    advice_msg = "آپ کی لوکیشن کے موسم کے مطابق آج بارش کا امکان نہیں ہے اور درجہ حرارت معتدل ہے۔ اگر مٹی خشک محسوس ہو تو معمول کے مطابق پانی دیں اور جڑوں کو گلنے سے بچانے کے لیے ضرورت سے زیادہ پانی دینے سے گریز کریں۔"
                                elif lang == "roman_urdu":
                                    advice_msg = "Aap ki location ke mosam ke mutabiq aaj barish ka koi imkan nahi hai aur temperature moderate hai. Agar mitti khushk lagay to normal pani dein aur jaron ko galne se bachane ke liye zayada pani dene se greez karein."
                                elif lang == "english":
                                    advice_msg = "No rain is expected today and the temperature is moderate. Apply normal irrigation if the soil feels dry, but avoid overwatering to protect the roots from rotting."
                                elif lang in ("punjabi", "pa", "panjabi"):
                                    advice_msg = "تہاڈی لوکیشن دے موسم دے مطابق اج بارش دا کوئی امکان نہیں اے تے درجہ حرارت معتدل اے۔ جے مٹی خشک محسوس ہووے تاں معمول دے مطابق پانی دیو تے جڑاں نوں گلن توں بچان لئی زیادہ پانی دین توں پرہیز کرو۔"
                                elif lang in ("siraiki", "seraiki", "saraiki", "skr", "saraki"):
                                    advice_msg = "تہاڈی لوکیشن دے موسم دے مطابق اج بارش دا کوئی امکان کائنی تے درجہ حرارت معتدل اے۔ جے مٹی خشک محسوس تھیوے تاں معمول دے مطابق پانی ڈیو تے جڑاں کوں گلن توں بچاوݨ کیتے زیادہ پانی ڈیون توں پرہیز کرو۔"
                                else:
                                    advice_msg = "آپ کی لوکیشن کے موسم کے مطابق آج بارش کا امکان نہیں ہے اور درجہ حرارت معتدل ہے۔ اگر مٹی خشک محسوس ہو تو معمول کے مطابق پانی دیں اور جڑوں کو گلنے سے بچانے کے لیے ضرورت سے زیادہ پانی دینے سے گریز کریں۔"
                                    
                    update_session(user_id, {
                        "pending_audio_offer": True,
                        "last_tts_summary": advice_msg,
                        "last_farmer_response": advice_msg[:300],
                        "last_audio_language": lang,
                        "last_audio_url": None,
                        "last_audio_format": None,
                        "last_message_type": message_type,
                        "last_crop": last_crop,
                        "last_language": lang,
                        "last_question": text[:100],
                        "last_context": f"Farmer asked weather-action query: '{text[:50]}...'"
                    })
                    
                    offer_text = get_audio_offer_text(lang)
                    
                    return {
                        "status": "success",
                        "user_id": user_id,
                        "source": source,
                        "message_type": message_type,
                        "farmer_response": advice_msg,
                        "tts_summary": advice_msg,
                        "audio_offer_text": offer_text,
                        "audio_available": True,
                        "expects_audio_confirmation": True,
                        "audio_url": None,
                        "language": lang,
                        "metadata": {
                            "pending_audio_offer": True,
                            "session_used": True,
                            "location_saved": location_saved,
                            "used_saved_location": used_saved_location,
                            "last_crop": last_crop,
                            "weather_action_intent": intent,
                            "location_available": True,
                        }
                    }
        except Exception as e:
            logger.warning("[WEATHER_ACTION] Weather action flow failed, falling back to normal pipeline: %s", type(e).__name__)

    # ── 2.5 Early check for Market Rates / Mandi Intent ───────────────────
    is_market = False
    if message_type in ("text", "text_image") and text:
        from services.market_rates_service import detect_market_intent
        if detect_market_intent(text):
            norm_text = text.lower()
            advisory_words = ["spray", "fertilizer", "dose", "growth", "water", "flow", "application", "پانی", "سپرے"]
            has_advisory = any(w in norm_text for w in advisory_words)
            
            strong_market_words = [
                "mandi", "market", "price", "sell", "selling", "bikri", "bechna", "bechun", 
                "qeemat", "narkh", "منڈی", "ریٹ", "قیمت", "نرخ", "بیچنا", "فروخت", "بھاؤ"
            ]
            has_strong_market = any(w in norm_text for w in strong_market_words)
            
            if has_advisory and not has_strong_market:
                is_market = False
            else:
                is_market = True

    if is_market:
        try:
            from services.market_rates_service import get_market_rate_advice
            advice = get_market_rate_advice(
                text=text,
                latitude=current_lat,
                longitude=current_lon,
                crop=crop,
                language=last_lang or "urdu"
            )
            
            guidance = advice.get("market_guidance", "")
            
            if advice.get("reason") == "commodity_not_detected":
                metadata = {
                    "market_intent": True,
                    "commodity": None,
                    "reason": "commodity_not_detected",
                    "price_prediction": False,
                    "safe_financial_advice": True,
                    "market_service_integrated": True
                }
            else:
                metadata = {
                    "market_intent": True,
                    "commodity": advice.get("commodity"),
                    "nearest_mandis": advice.get("nearest_mandis"),
                    "rates": advice.get("rates"),
                    "market_source": advice.get("source"),
                    "market_last_updated": advice.get("last_updated"),
                    "price_prediction": False,
                    "safe_financial_advice": True,
                    "market_service_integrated": True
                }
            
            update_session(user_id, {
                "pending_audio_offer": True,
                "last_tts_summary": guidance,
                "last_farmer_response": guidance[:300],
                "last_audio_language": last_lang or "urdu",
                "last_audio_url": None,
                "last_audio_format": None,
                "last_message_type": message_type,
                "last_question": text[:100] if text else None,
                "last_context": f"Farmer asked market rate: '{text[:50]}...'"
            })
            
            offer_text = get_audio_offer_text(last_lang or "urdu")
            
            return {
                "status": "success",
                "user_id": user_id,
                "source": source,
                "message_type": "market_rate",
                "farmer_response": guidance,
                "tts_summary": guidance,
                "audio_offer_text": offer_text,
                "audio_available": True,
                "expects_audio_confirmation": True,
                "audio_url": None,
                "language": last_lang or "urdu",
                "metadata": metadata
            }
            
        except Exception as exc:
            logger.exception("Error in process_farmai_query (market check): %s", exc)
            fallback_msg = (
                "Mandi rate ki maloomat is waqt dastiyab nahi hain. "
                "Barah-e-karam apni qareebi mandi ya arhti se final rate confirm kar lein."
            )
            return {
                "status": "success",
                "user_id": user_id,
                "source": source,
                "message_type": "market_rate",
                "farmer_response": fallback_msg,
                "tts_summary": fallback_msg,
                "audio_available": False,
                "expects_audio_confirmation": False,
                "audio_url": None,
                "language": last_lang or "urdu",
                "metadata": {
                    "market_intent": True,
                    "market_error": True,
                    "price_prediction": False,
                    "safe_financial_advice": True
                }
            }

    # ── 3. Check for weather queries without location ─────────────────────
    if message_type in ("text", "image", "text_image") and is_weather_question(text):
        if current_lat is None or current_lon is None:
            from utils.helpers import detect_language
            lang = detect_language(text)
            
            if lang == "urdu" or lang == "ur":
                refusal_msg = "بہتر مشورے کے لیے پہلے اپنی لوکیشن بھیج دیں تاکہ میں موسم دیکھ کر سپرے اور پانی کا درست مشورہ دے سکوں۔"
            elif lang == "english":
                refusal_msg = "Please share your location first so I can check the weather and give accurate spray or irrigation advice."
            else:
                refusal_msg = "Behtar mashwaray ke liye pehle apni location bhej dein taake main mosam dekh kar spray aur pani ka sahi mashwara de sakun."
                
            return {
                "status": "success",
                "user_id": user_id,
                "source": source,
                "message_type": message_type,
                "farmer_response": refusal_msg,
                "tts_summary": refusal_msg,
                "language": lang,
                "audio_url": None,
                "metadata": {
                    "session_used": True,
                    "location_saved": False,
                    "used_saved_location": False,
                    "last_crop": last_crop
                }
            }

    # ── 4. Handle Location-Only messages ──────────────────────────────────
    if message_type == "location":
        if current_lat is None or current_lon is None:
            return {
                "status": "error",
                "message": "Latitude and longitude are required for location message type."
            }
        
        try:
            from services.weather_service import get_mock_weather
            weather = get_mock_weather(current_lat, current_lon)
            
            rain_expected = weather.get("rain_expected", False)
            
            if last_lang in ("ur", "urdu"):
                if rain_expected:
                    advice = (
                        "آپ کی لوکیشن محفوظ ہو گئی ہے۔ اس لوکیشن کے موسم کے مطابق بارش کا امکان ہے، "
                        "اس لیے ابھی سپرے یا پانی دینے میں احتیاط کریں۔"
                    )
                else:
                    advice = (
                        "آپ کی لوکیشن محفوظ ہو گئی ہے۔ اس لوکیشن کے موسم کے مطابق فی الحال بارش کا امکان نہیں ہے، "
                        "اس لیے سپرے کیا جا سکتا ہے لیکن سپرے سے پہلے ہوا اور نمی کا خیال رکھیں۔"
                    )
            elif last_lang == "english":
                if rain_expected:
                    advice = (
                        "Your location has been saved. According to the weather forecast for this location, rain is expected. "
                        "Please avoid spraying or watering at this time."
                    )
                else:
                    advice = (
                        "Your location has been saved. According to the weather forecast for this location, no rain is expected. "
                        "Spraying can be done, but please monitor wind speed and humidity levels beforehand."
                    )
            else:
                if rain_expected:
                    advice = (
                        "Aap ki location save ho gayi hai. Is location ke mosam ke mutabiq barish ka imkan hai, "
                        "is liye abhi spray ya pani dene mein ehtiyat karein."
                    )
                else:
                    advice = (
                        "Aap ki location save ho gayi hai. Is location ke mosam ke mutabiq agar barish ka imkan kam hai to spray kiya ja sakta hai, "
                        "lekin spray se pehle hawa aur nami ka khayal rakhein."
                    )
            
            # Save audio context and offer text
            update_session(user_id, {
                "pending_audio_offer": True,
                "last_tts_summary": advice,
                "last_farmer_response": advice[:300],
                "last_audio_language": last_lang,
                "last_audio_url": None,
                "last_audio_format": None,
                "last_message_type": "location",
                "last_question": "Location payload",
                "last_context": f"Farmer sent location: lat={current_lat}, lon={current_lon}"
            })
            
            offer_text = get_audio_offer_text(last_lang)
            
            return {
                "status": "success",
                "user_id": user_id,
                "source": source,
                "message_type": "location",
                "farmer_response": advice,
                "tts_summary": advice,
                "audio_offer_text": offer_text,
                "audio_available": True,
                "expects_audio_confirmation": True,
                "audio_url": None,
                "language": last_lang,
                "metadata": {
                    "pending_audio_offer": True,
                    "session_used": True,
                    "location_saved": True,
                    "used_saved_location": False,
                    "last_crop": last_crop
                }
            }
        except Exception as exc:
            logger.exception("Error in process_farmai_query (location): %s", exc)
            return {
                "status": "error",
                "message": "An internal error occurred while processing the request."
            }

    # ── 5. Handle Text messages ───────────────────────────────────────────
    elif message_type == "text":
        if not text or not text.strip():
            return {
                "status": "error",
                "message": "Text message is required for text processing."
            }

        try:
            # 1. Parse Input
            parsed = parse_input(
                text=text,
                crop=crop,
                latitude=current_lat,
                longitude=current_lon,
                image=None,
                language_hint=language_hint,
            )

            # Ensure image fields are initialized to None
            parsed["image_bytes"] = None
            parsed["image_mime"] = None

            # 2. Run sequential multi-agent pipeline
            diagnosis = generate_mock_diagnosis(parsed)
            context = get_context(parsed, diagnosis)
            action_chain = plan_actions(parsed, diagnosis, context)
            execution_result = execute_actions(action_chain)
            recovery_result = apply_recovery(diagnosis, context, execution_result)
            outcome = format_outcome(
                parsed,
                diagnosis,
                context,
                action_chain,
                execution_result,
                recovery_result,
            )

            # 3. Format integration response output
            farmer_response = outcome.get("farmer_response") or _FALLBACK_FARMER_RESPONSE
            language_hint = parsed.get("language_hint", "ur")
            tts_summary = outcome.get("tts_summary") or generate_safe_tts_summary(farmer_response, language_hint)

            # 4. Save crop, language, and context updates to user session
            detected_crop = parsed.get("crop")
            detected_lang = parsed.get("language_hint", "ur")
            
            update_session(user_id, {
                "pending_audio_offer": True,
                "last_tts_summary": tts_summary,
                "last_farmer_response": farmer_response[:300],
                "last_audio_language": language_hint,
                "last_audio_url": None,
                "last_audio_format": None,
                "last_message_type": "text",
                "last_crop": detected_crop if (detected_crop and detected_crop != "Unknown") else last_crop,
                "last_language": detected_lang if detected_lang else last_lang,
                "last_question": text[:100],
                "last_context": f"Farmer asked text query: '{text[:50]}...'"
            })

            offer_text = get_audio_offer_text(language_hint)

            return {
                "status": "success",
                "user_id": user_id,
                "source": source,
                "message_type": "text",
                "farmer_response": farmer_response,
                "tts_summary": tts_summary,
                "audio_offer_text": offer_text,
                "audio_available": True,
                "expects_audio_confirmation": True,
                "audio_url": None,
                "language": language_hint,
                "metadata": {
                    "pending_audio_offer": True,
                    "session_used": True,
                    "location_saved": location_saved,
                    "used_saved_location": used_saved_location,
                    "last_crop": detected_crop if (detected_crop and detected_crop != "Unknown") else last_crop,
                    "crop": parsed.get("crop"),
                    "location_received": parsed.get("has_location", False),
                    "diagnosis": outcome.get("diagnosis"),
                    "weather": outcome.get("weather"),
                    "irrigation_advice": outcome.get("irrigation_advice"),
                    "cost_summary": outcome.get("cost_summary"),
                    "rag_status": outcome.get("rag_status"),
                    "gemini_status": outcome.get("gemini_status"),
                }
            }

        except Exception as exc:
            logger.exception("Error in process_farmai_query (text): %s", exc)
            return {
                "status": "error",
                "message": "An internal error occurred while processing the request."
            }

    # ── 6. Handle Image / Text-Image messages ─────────────────────────────
    elif message_type in ("image", "text_image"):
        if not image_path or not image_path.strip():
            return {
                "status": "error",
                "message": "image_path is required for image processing."
            }

        resolved_path = Path(image_path)
        if not resolved_path.is_absolute():
            backend_dir = Path(__file__).resolve().parent.parent
            opt1 = backend_dir / image_path
            if opt1.is_file():
                resolved_path = opt1
            else:
                opt2 = backend_dir.parent / image_path
                if opt2.is_file():
                    resolved_path = opt2
                else:
                    opt3 = Path(os.getcwd()) / image_path
                    if opt3.is_file():
                        resolved_path = opt3

        if not resolved_path.is_file():
            return {
                "status": "error",
                "message": "Image file not found."
            }

        ext = resolved_path.suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            return {
                "status": "error",
                "message": "Unsupported image format."
            }

        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp"
        }
        image_mime = mime_map.get(ext, "image/jpeg")

        try:
            with open(resolved_path, "rb") as f:
                image_bytes = f.read()

            class MockUploadFile:
                def __init__(self, filename: str):
                    self.filename = filename

            mock_image = MockUploadFile(resolved_path.name)

            parsed = parse_input(
                text=text,
                crop=crop,
                latitude=current_lat,
                longitude=current_lon,
                image=mock_image,
                language_hint=language_hint,
            )

            parsed["image_bytes"] = image_bytes
            parsed["image_mime"] = image_mime

            diagnosis = generate_mock_diagnosis(parsed)
            context = get_context(parsed, diagnosis)
            action_chain = plan_actions(parsed, diagnosis, context)
            execution_result = execute_actions(action_chain)
            recovery_result = apply_recovery(diagnosis, context, execution_result)
            outcome = format_outcome(
                parsed,
                diagnosis,
                context,
                action_chain,
                execution_result,
                recovery_result,
            )

            farmer_response = outcome.get("farmer_response") or _FALLBACK_FARMER_RESPONSE
            language_hint = parsed.get("language_hint", "ur")
            tts_summary = outcome.get("tts_summary") or generate_safe_tts_summary(farmer_response, language_hint)

            # Save crop, language, and context updates to user session
            detected_crop = parsed.get("crop")
            detected_lang = parsed.get("language_hint", "ur")
            
            update_session(user_id, {
                "pending_audio_offer": True,
                "last_tts_summary": tts_summary,
                "last_farmer_response": farmer_response[:300],
                "last_audio_language": language_hint,
                "last_audio_url": None,
                "last_audio_format": None,
                "last_message_type": message_type,
                "last_crop": detected_crop if (detected_crop and detected_crop != "Unknown") else last_crop,
                "last_language": detected_lang if detected_lang else last_lang,
                "last_question": text[:100] if text else None,
                "last_context": f"Farmer sent image for crop diagnosis: '{text[:50]}...'" if text else "Farmer sent image for diagnosis."
            })

            offer_text = get_audio_offer_text(language_hint)

            return {
                "status": "success",
                "user_id": user_id,
                "source": source,
                "message_type": message_type,
                "farmer_response": farmer_response,
                "tts_summary": tts_summary,
                "audio_offer_text": offer_text,
                "audio_available": True,
                "expects_audio_confirmation": True,
                "audio_url": None,
                "language": language_hint,
                "metadata": {
                    "image_received": True,
                    "image_path": image_path,
                    "session_used": True,
                    "location_saved": location_saved,
                    "used_saved_location": used_saved_location,
                    "last_crop": detected_crop if (detected_crop and detected_crop != "Unknown") else last_crop,
                    "crop": parsed.get("crop"),
                    "location_received": parsed.get("has_location", False),
                    "diagnosis": outcome.get("diagnosis"),
                    "weather": outcome.get("weather"),
                    "irrigation_advice": outcome.get("irrigation_advice"),
                    "cost_summary": outcome.get("cost_summary"),
                    "rag_status": outcome.get("rag_status"),
                    "gemini_status": outcome.get("gemini_status"),
                }
            }

        except Exception as exc:
            logger.exception("Error in process_farmai_query (image/%s): %s", message_type, exc)
            return {
                "status": "error",
                "message": "An internal error occurred while processing the request."
            }

    else:
        return {
            "status": "error",
            "message": f"Message type '{message_type}' is not supported in this version."
        }


async def process_farmai_query(
    user_id: str,
    source: str = "integration",
    message_type: str = "text",
    text: Optional[str] = None,
    crop: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    image_path: Optional[str] = None,
    audio_path: Optional[str] = None,
    base_url: Optional[str] = None,
    language_hint: Optional[str] = None,
) -> dict:
    res = await _process_farmai_query_impl(
        user_id=user_id,
        source=source,
        message_type=message_type,
        text=text,
        crop=crop,
        latitude=latitude,
        longitude=longitude,
        image_path=image_path,
        audio_path=audio_path,
        base_url=base_url,
        language_hint=language_hint,
    )
    
    if res and isinstance(res, dict) and res.get("status") == "success":
        farmer_resp = res.get("farmer_response")
        msg_type = res.get("message_type")
        lang = res.get("language") or language_hint or "ur"
        
        if farmer_resp and msg_type != "audio_response":
            from utils.helpers import append_audio_offer_line
            res["farmer_response"] = append_audio_offer_line(farmer_resp, lang)
            
    return res
