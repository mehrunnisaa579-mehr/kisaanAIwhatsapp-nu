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
    Returns: 'urdu', 'roman_urdu', 'english'
    """
    if not text:
        return "urdu"

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

