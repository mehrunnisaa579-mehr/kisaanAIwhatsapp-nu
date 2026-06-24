"""
FarmAI Helpers
Shared utility functions for the multi-agent pipeline.
"""

import re
from utils.constants import (
    CROP_KEYWORDS,
    URDU_CHAR_RANGE,
    ROMAN_URDU_WORDS,
)


def detect_language(text: str) -> str:
    """
    Simple language hint detection.
    Returns: 'urdu', 'roman_urdu', 'english', 'punjabi', 'siraiki'
    """
    if not text:
        return "urdu"

    # Check for regional override first
    regional = detect_punjabi_siraiki_from_text(text)
    if regional:
        return regional

    # Check for Urdu script characters
    if re.search(r"[\u0600-\u06FF]", text):
        return "urdu"

    text_lower = text.lower()

    # Common Roman Urdu words list from prompt
    roman_urdu_words = [
        "meri", "mera", "mere", "fasal", "kapas", "kapaas", "gandum", "aam", 
        "patton", "pattay", "peelay", "nishan", "daag", "masla", "pani", 
        "khad", "keera", "keeray", "bimari", "spray", "zameen", "mitti"
    ]

    # English farming words list from prompt
    english_words = [
        "crop", "plant", "leaf", "leaves", "pest", "fertilizer", "soil", 
        "irrigation", "disease", "fungus", "water", "spray"
    ]

    words = re.findall(r"\b\w+\b", text_lower)
    
    roman_hits = sum(1 for w in words if w in roman_urdu_words)
    english_hits = sum(1 for w in words if w in english_words)

    if roman_hits > 0 or english_hits > 0:
        if roman_hits >= english_hits:
            return "roman_urdu"
        else:
            return "english"

    # Default to 'urdu' for unknown
    # But if there are English letters, check if they are common words
    if re.search(r"[a-zA-Z]", text):
        english_stop = {
            "my", "the", "is", "are", "have", "has", "of", "and", "in", "to", "it", 
            "you", "tell", "me", "joke", "story", "movie", "cotton", "rice", "wheat", 
            "mango", "pest", "insect", "weather", "hello", "hi", "hey", "please", "help"
        }
        roman_stop = {
            "yeh", "hai", "hain", "ke", "ki", "ka", "aur", "pe", "par", "ko", "mujhe", 
            "batao", "bataen", "karo", "kya", "kyun", "kab", "kese", "karna", "krna", 
            "he", "rha", "rhi"
        }
        
        eng_stop_hits = sum(1 for w in words if w in english_stop)
        rom_stop_hits = sum(1 for w in words if w in roman_stop)
        if rom_stop_hits > eng_stop_hits:
            return "roman_urdu"
        elif eng_stop_hits > rom_stop_hits:
            return "english"
        
        return "english"

    return "urdu"


def is_agriculture_related(text: str, has_image: bool) -> bool:
    """
    Check if the user query is agriculture-related.
    """
    # Treat uploaded image query as potentially agriculture-related if text is empty but image exists
    if not text and has_image:
        return True

    if not text:
        return False

    text_lower = text.lower()

    # List of keywords from prompt
    agri_keywords = [
        "crop", "crops", "plant", "plants", "leaf", "leaves", "soil", "water", 
        "irrigation", "fertilizer", "pest", "insect", "disease", "fungus", 
        "spray", "weather", "farm", "farming", "seed", "root", "fruit", 
        "wheat", "cotton", "mango", "rice", "sugarcane", "maize",
        "کپاس", "گندم", "آم", "فصل", "پودا", "پتے", "بیماری", "کیڑا", "کیڑے", 
        "کھاد", "پانی", "زمین", "مٹی", "سپرے", "موسم", "بارش", "جڑ", "پھل",
        "gandum", "kapas", "kapaas", "aam", "fasal", "podon", "poda", "patton", 
        "patte", "pattay", "bemari", "keera", "keeray", "khaad", "pani", 
        "zameen", "mitti", "spray", "mosam", "barish", "jar", "phul"
    ]

    for kw in agri_keywords:
        if kw in text_lower or kw in text:
            return True

    return False


def infer_crop(text: str, explicit_crop: str = None) -> str:
    """
    Infer the crop from explicit parameter or text keywords.
    Returns crop name or 'Unknown'.
    """
    # Prefer explicitly passed crop
    if explicit_crop and explicit_crop.strip():
        # Normalize against known crops
        for crop_name, keywords in CROP_KEYWORDS.items():
            if explicit_crop.strip().lower() in [k.lower() for k in keywords]:
                return crop_name
            if explicit_crop.strip().lower() == crop_name.lower():
                return crop_name
        return explicit_crop.strip()

    if not text:
        return "Unknown"

    text_lower = text.lower()

    # Also check original text (for Urdu keywords)
    for crop_name, keywords in CROP_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower or keyword in text:
                return crop_name

    return "Unknown"


def contains_healthy_keywords(text: str, keywords: list) -> bool:
    """Check if text contains any of the healthy/fine keywords."""
    if not text:
        return False
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower or kw in text:
            return True
    return False


def get_weather_instruction(weather: dict | None) -> str:
    """Get the weather-aware instruction string in Urdu."""
    if not weather:
        return "موسم کی معلومات دستیاب نہیں، اس لیے سپرے سے پہلے مقامی موسم ضرور چیک کریں۔"
    rain_expected = weather.get("rain_expected")
    if rain_expected is True:
        return "بارش متوقع ہے، اس لیے ابھی سپرے یا پانی دینے میں احتیاط کریں۔"
    elif rain_expected is False:
        return "فی الحال بارش متوقع نہیں، مگر سپرے سے پہلے مقامی موسم ضرور دیکھ لیں۔"
    else:
        return "موسم کی معلومات دستیاب نہیں، اس لیے سپرے سے پہلے مقامی موسم ضرور چیک کریں۔"


def is_image_blank_or_solid(image_bytes: bytes) -> bool:
    """
    Check if the image is blank, solid color, black, or extremely small (<= 10x10).
    """
    if not image_bytes:
        return False
    import io
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.size[0] <= 10 or img.size[1] <= 10:
            return True
        img_rgb = img.convert("RGB")
        colors = img_rgb.getcolors(img.size[0] * img.size[1])
        if colors and len(colors) == 1:
            return True
        return False
    except Exception:
        return False


def detect_punjabi_siraiki_from_text(text: str, current_hint: str | None = None) -> str | None:
    if not text:
        return None

    # Normalise text
    text_lower = text.lower()

    # If hint is already punjabi or siraiki, preserve it!
    if current_hint in ("punjabi", "siraiki"):
        return current_hint

    siraiki_strong = [
        "thinday", "thindi", "murjhainday", "meku", "keewein", "waan", "dewan", 
        "میکوں", "مینکوں", "تیکوں", "تینکوں", "تساں", "اساں", "کیتھاں", "کتھاں", 
        "کڈاں", "کینویں", "کیویں", "تھیوے", "تھیوݨ", "تھیوڻ", "ڈسوں", "پترے", 
        "پتراں", "لبھدے", "لبھئے", "پانی ڈیو"
    ]
    
    siraiki_medium = [
        "meda", "meday", "saday", "lagday", "honday", "paye ne", 
        "kapaas de pattay peelay thinday", "ruk waan", "thi", "hun", "karaan",
        "تھی رہا", "تھی رہی", "تھی رہے", "ہن", "پیا ہن", "رہے ہن", "لگدے ہن",
        "دسو میکوں", "میکوں دسو", "کرنا چاہیدا", "کی کرنا چاہیدا", "گھٹت", "ڈکھ",
        "سگدا اے", "سگدی اے"
    ]
    
    punjabi_strong = [
        "mainu", "minon", "مینوں", "مینو", "تسی", "تسیں", "سانوں", "توانوں", 
        "کداں", "کیداں", "کیتھے", "کتھے", "میں کی کراں", "میں کی کرا", "کی کراں", 
        "ki karaan", "kehri", "paawan", "ho rahe ne", "karni chahidi ae", 
        "paani dena chahida", "chal reha ae", "lag gaya ae", "ki aa", 
        "پیلے نے", "لگدے نے", "رہے نے", "نیں", "ہو سکدا اے", "ہو سکدی اے"
    ]
    
    punjabi_medium = [
        "ne", "ae", "dasso", "kithay", "mannay", "dass", "کی حال", "کی کرنا اے"
    ]

    siraiki_score = 0
    punjabi_score = 0

    # Calculate Siraiki score
    for word in siraiki_strong:
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower) or (re.search(r'[\u0600-\u06FF]', word) and word in text):
            siraiki_score += 2
            
    for word in siraiki_medium:
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower) or (re.search(r'[\u0600-\u06FF]', word) and word in text):
            siraiki_score += 1

    # Calculate Punjabi score
    for word in punjabi_strong:
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower) or (re.search(r'[\u0600-\u06FF]', word) and word in text):
            punjabi_score += 2
            
    for word in punjabi_medium:
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower) or (re.search(r'[\u0600-\u06FF]', word) and word in text):
            punjabi_score += 1

    # Log the trace values for score analysis
    import logging
    logger = logging.getLogger(__name__)
    logger.info("[LANG_TRACE] punjabi_score=%d siraiki_score=%d", punjabi_score, siraiki_score)

    if siraiki_score >= 2 and siraiki_score > punjabi_score:
        logger.info("[LANG_TRACE] regional_language_override=siraiki")
        return "siraiki"
    if punjabi_score >= 2 and punjabi_score > siraiki_score:
        logger.info("[LANG_TRACE] regional_language_override=punjabi")
        return "punjabi"

    logger.info("[LANG_TRACE] regional_language_override=none")
    return None


def append_audio_offer_line(response_text: str, language_hint: str | None = None) -> str:
    if not response_text:
        return response_text

    # Normalize response_text to inspect and check for control messages
    resp_clean = response_text.strip().lower().rstrip("۔?.!")
    confirm_phrases = {
        "آڈیو سمری تیار ہے",
        "audio summary is ready",
        "audio summary tayyar hai",
        "ٹھیک ہے، جب ضرورت ہو تو بتا دیں",
        "alright, let know if you need it later",
        "theek hai, jab zaroorat ho to bata dein",
        "پہلے سے کوئی مشورہ موجود نہیں ہے۔ براہ کرم نیا سوال پوچھیں",
        "no previous advice found. please ask a new question",
        "pehle se koi mashwara maujood nahi hai. barah-e-karam naya sawal poochein",
        "audio bananay mein masla aa raha hai. text jawab phir bhi available hai"
    }
    if resp_clean in confirm_phrases:
        return response_text

    lang = (language_hint or "ur").strip().lower()
    if lang in ("ur", "urdu", "unknown"):
        offer = "کیا آپ اس کی آڈیو سمری سننا چاہتے ہیں؟"
    elif lang == "roman_urdu":
        offer = "Kya aap is ki audio summary sunna chahtay hain?"
    elif lang == "english":
        offer = "Do you want to hear an audio summary of this?"
    elif lang in ("punjabi", "pa", "panjabi"):
        offer = "Ki tusi is di audio summary sunna chaunde ho?"
    elif lang in ("siraiki", "seraiki", "saraiki", "skr", "saraki"):
        offer = "Tusan is di audio summary sunnan chahso?"
    else:
        offer = "کیا آپ اس کی آڈیو سمری سننا چاہتے ہیں؟" # default to Urdu

    # Split into lines to inspect and remove existing offer lines
    lines = response_text.splitlines()
    
    # We want to remove any trailing lines that contain keywords representing audio offer
    banned_keywords = [
        "audio summary",
        "voice summary",
        "آڈیو سمری",
        "sunna chahtay",
        "سننا چاہتے",
        "sunao",
        "hear an audio summary",
        "audio offer",
        "summary sunna"
    ]
    
    # Clean trailing empty lines or lines with banned keywords from the end
    while lines:
        last_line = lines[-1].strip()
        if not last_line:
            lines.pop()
            continue
        
        last_line_lower = last_line.lower()
        has_keyword = any(kw in last_line_lower for kw in banned_keywords)
        
        if has_keyword:
            lines.pop()
        else:
            break
            
    # Reconstruct the response text
    cleaned_text = "\n".join(lines).strip()
    
    # Log that the audio offer line is appended
    import logging
    logger = logging.getLogger(__name__)
    logger.info("[AUDIO_OFFER] language_hint=%s appended=true", lang)
    
    return f"{cleaned_text}\n\n{offer}"


def is_weather_action_query(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    
    # Spray keywords
    spray_kws = ["spray", "سپرے", "اسپرے", "dawa", "dawai", "دوائی", "زہر"]
    # Water/irrigation keywords
    water_kws = ["pani", "paani", "water", "irrigation", "aabpashi", "آبپاشی", "پانی"]
    
    has_spray = any(kw in text_lower for kw in spray_kws)
    has_water = any(kw in text_lower for kw in water_kws)
    
    if not (has_spray or has_water):
        return False
        
    # Decision keywords
    decision_kws = [
        "karun", "karni", "karna", "doon", "dena", "lagaun", "chahidi", "dewan", "ruk waan", "ruk jaun", "chahso",
        "chahiye", "krna", "krn", "dein", "lagana", "chahye", "chahiyay",
        "کروں", "کرنی", "کرنا", "دوں", "دینا", "لگاؤں", "لگانا", "دیواں", "نہ", "یا", "ضرورت", "چاہیے", "چاہئے"
    ]
    # Weather decision keywords
    weather_kws = [
        "mosam", "mausam", "weather", "barish", "rain", "hawa", "wind", "humidity", "temperature",
        "aaj", "kal", "mutabiq", "hisab", "hisaab", "chance", "ajj",
        "موسم", "بارش", "ہوا", "آج", "کل", "چانس"
    ]
    
    has_decision = any(kw in text_lower for kw in decision_kws)
    has_weather = any(kw in text_lower for kw in weather_kws)
    
    return has_decision or has_weather


def handle_weather_action_query(text: str, latitude: float | None, longitude: float | None, language_hint: str | None) -> tuple[str, str] | None:
    if not is_weather_action_query(text):
        return None
        
    lang = (language_hint or "ur").strip().lower()
    location_available = latitude is not None and longitude is not None
    
    text_lower = text.lower()
    spray_kws = ["spray", "سپرے", "اسپرے", "dawa", "dawai", "دوائی", "زہر"]
    has_spray = any(kw in text_lower for kw in spray_kws)
    intent = "spray" if has_spray else "water"
    
    if not location_available:
        if lang in ("ur", "urdu", "unknown"):
            advice_msg = "اسپرے یا پانی کا صحیح مشورہ دینے کے لیے مجھے آپ کی لوکیشن کی ضرورت ہے، کیونکہ بارش، ہوا اور درجہ حرارت کا اس پر گہرا اثر ہوتا ہے۔ براہ کرم واٹس ایپ پر اپنی لوکیشن پن بھیجیں، پھر میں بتا دوں گا کہ آج اسپرے یا پانی دینا ٹھیک ہے یا نہیں۔"
        elif lang == "roman_urdu":
            advice_msg = "Spray ya pani ka sahi mashwara dene ke liye mujhe aap ki location chahiye, kyun ke barish, hawa aur temperature ka asar hota hai. Barah-e-karam WhatsApp location pin bhej dein, phir main bata dunga ke aaj spray ya pani dena theek hai ya nahi."
        elif lang == "english":
            advice_msg = "To give you accurate advice on spraying or irrigation, I need your location because weather conditions like rain and wind play a critical role. Please share your WhatsApp location pin so I can guide you."
        elif lang in ("punjabi", "pa", "panjabi"):
            advice_msg = "اسپرے یا پانی دین دا صحیح مشورہ دین لئی مینوں تہاڈی لوکیشن دی لوڑ اے، کیونکہ بارش، ہوا تے درجہ حرارت دا اثر پیندا اے۔ مہربانی کر کے واٹس ایپ لوکیشن پن بھیجو، فیر میں دس دیاں گا کہ اج اسپرے یا پانی دینا ٹھیک اے یا نہیں۔"
        elif lang in ("siraiki", "seraiki", "saraiki", "skr", "saraki"):
            advice_msg = "اسپرے یا پانی ڈیون دا صحیح مشورہ ڈیون کیتے میکوں تہاڈی لوکیشن دی لوڑ اے، کیونکہ بارش، ہوا تے درجہ حرارت دا اثر تھیندے۔ مہربانی کر کے واٹس ایپ لوکیشن پن بھیجو، ولا میں ڈس ڈیساں کہ اج اسپرے یا پانی ڈیون ٹھیک اے یا نہیں۔"
        else:
            advice_msg = "اسپرے یا پانی کا صحیح مشورہ دینے کے لیے مجھے آپ کی لوکیشن کی ضرورت ہے، کیونکہ بارش، ہوا اور درجہ حرارت کا اس پر گہرا اثر ہوتا ہے۔ براہ کرم واٹس ایپ پر اپنی لوکیشن پن بھیجیں، پھر میں بتا دوں گا کہ آج اسپرے یا پانی دینا ٹھیک ہے یا نہیں۔"
        return advice_msg, advice_msg

    from services.weather_service import get_mock_weather
    weather = get_mock_weather(latitude, longitude)
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
                    
    return advice_msg, advice_msg




