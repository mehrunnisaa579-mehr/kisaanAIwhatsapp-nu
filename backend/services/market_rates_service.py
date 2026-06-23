"""
FarmAI — Market Rates & Nearest Mandi Service
Completely isolated foundation service for intent detection, nearest mandi
proximity calculations, unit conversions, and mock rate formatting.
"""

import os
import json
import math
from typing import Optional, List, Dict

# Base directory lookup for safe relative path resolving
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MARKET_INTENT_KEYWORDS = [
    "rate", "rates", "price", "prices", "market", "mandi", "sell", "selling", "sold", "bikri",
    "bechna", "bechun", "bechna hai", "narkh", "qeemat", "rate kya", "mandi rate", "current rate",
    "نرخ", "ریٹ", "قیمت", "منڈی", "بیچنا", "بیچوں", "فروخت", "بھاؤ", "قیمتیں"
]


def normalize_text(text: Optional[str]) -> str:
    """Normalize text: strip, lowercase, handle None safely."""
    if not text:
        return ""
    return text.strip().lower()


def load_market_commodities() -> dict:
    """Load commodities catalog JSON file."""
    path = os.path.join(BASE_DIR, "data", "market_commodities.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"commodities": []}


def detect_market_intent(text: Optional[str]) -> bool:
    """
    Detect if user query has market rate/selling intent.
    Ignores advisory-only queries to prevent false positives.
    """
    if not text:
        return False
    
    norm = normalize_text(text)
    
    # Check if any market-specific keyword exists in text
    for kw in MARKET_INTENT_KEYWORDS:
        if kw in norm:
            return True
            
    return False


def detect_market_commodity(text: Optional[str], crop: Optional[str] = None) -> Optional[str]:
    """
    Detect commodity canonical key from query text or explicit crop.
    Catalog-driven matching.
    """
    catalog = load_market_commodities()
    commodities = catalog.get("commodities", [])
    
    norm_text = normalize_text(text)
    
    # 1. Prefer crop parameter if provided and valid in catalog (either canonical or alias match)
    if crop:
        norm_crop = normalize_text(crop)
        # Check canonical match
        for item in commodities:
            if item["canonical"] == norm_crop:
                return item["canonical"]
        # Check alias match in crop parameter
        for item in commodities:
            for alias in item.get("aliases", []):
                if normalize_text(alias) == norm_crop:
                    return item["canonical"]

    # 2. Check query text against aliases
    # Sort aliases by length descending to match longer multi-word aliases first (e.g. "seed cotton" before "cotton")
    alias_matches = []
    for item in commodities:
        for alias in item.get("aliases", []):
            norm_alias = normalize_text(alias)
            if norm_alias and norm_alias in norm_text:
                alias_matches.append((item["canonical"], len(norm_alias)))
                
    if alias_matches:
        alias_matches.sort(key=lambda x: x[1], reverse=True)
        return alias_matches[0][0]
        
    return None


def load_mandi_locations() -> List[Dict]:
    """Load mandi locations JSON file."""
    path = os.path.join(BASE_DIR, "data", "mandi_locations.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def load_mock_market_rates() -> dict:
    """Load mock market rates JSON file."""
    path = os.path.join(BASE_DIR, "data", "market_rates_mock.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"source": "local_mock", "last_updated": "mock-data", "rates": []}


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two coordinates using Haversine formula."""
    R = 6371.0  # Radius of Earth in km
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def find_nearest_mandis(latitude: Optional[float], longitude: Optional[float], limit: int = 3) -> List[Dict]:
    """
    Find nearest mandis from user coordinates.
    Falls back to default cities if coordinates are missing/invalid.
    """
    mandis = load_mandi_locations()
    
    valid_coords = False
    if latitude is not None and longitude is not None:
        try:
            lat = float(latitude)
            lon = float(longitude)
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                valid_coords = True
        except (ValueError, TypeError):
            pass
            
    if not valid_coords or not mandis:
        # Fallback default mandis
        defaults = ["Multan", "Khanewal", "Bahawalpur"]
        result = []
        for name in defaults:
            mandi_info = next((m for m in mandis if m["name"] == name), None)
            if mandi_info:
                res = dict(mandi_info)
                res["distance_km"] = None
                result.append(res)
            else:
                result.append({
                    "name": name,
                    "district": name,
                    "province": "Punjab",
                    "lat": None,
                    "lon": None,
                    "distance_km": None
                })
        return result[:limit]

    # Calculate distances
    scored = []
    for m in mandis:
        try:
            dist = haversine_distance_km(lat, lon, m["lat"], m["lon"])
            res = dict(m)
            res["distance_km"] = round(dist, 1)
            scored.append(res)
        except Exception:
            continue
            
    scored.sort(key=lambda x: x["distance_km"])
    return scored[:limit]


def convert_rate_units(rate_per_100kg: float) -> dict:
    """
    Convert Rs/100kg to Rs/40kg and Rs/maund.
    1 maund = 40kg. rate_per_maund = rate_per_100kg * 0.4.
    """
    rate_maund = round(rate_per_100kg * 0.4)
    rate_40kg = round(rate_per_100kg * 0.4)
    return {
        "rate_per_100kg": round(rate_per_100kg),
        "rate_per_40kg": rate_40kg,
        "rate_per_maund": rate_maund
    }


def fetch_market_rates(commodity: str, mandis: List[Dict]) -> List[Dict]:
    """Retrieve rates matching commodity and list of mandis from mock file."""
    mock_data = load_mock_market_rates()
    rates_list = mock_data.get("rates", [])
    
    result = []
    for mandi in mandis:
        mandi_name = mandi.get("name")
        dist = mandi.get("distance_km")
        
        matching_entry = None
        for r in rates_list:
            if r.get("commodity") == commodity and r.get("city", "").lower() == mandi_name.lower():
                matching_entry = r
                break
                
        if matching_entry:
            min_r = matching_entry["min_rate"]
            max_r = matching_entry["max_rate"]
            avg_r = matching_entry["avg_rate"]
            
            result.append({
                "commodity": commodity,
                "city": mandi_name,
                "min_rate": min_r,
                "max_rate": max_r,
                "avg_rate": avg_r,
                "min_rate_converted": convert_rate_units(min_r),
                "max_rate_converted": convert_rate_units(max_r),
                "avg_rate_converted": convert_rate_units(avg_r),
                "rate_available": True,
                "distance_km": dist,
                "source": "local_mock"
            })
        else:
            result.append({
                "commodity": commodity,
                "city": mandi_name,
                "rate_available": False,
                "distance_km": dist,
                "source": "local_mock"
            })
            
    return result


def format_market_response(commodity: str, rates: List[Dict], language: str = "urdu", source: str = "local_mock") -> str:
    """Format safe reference rates response in the requested language."""
    catalog = load_market_commodities()
    commodities = catalog.get("commodities", [])
    
    disp_name = commodity
    for item in commodities:
        if item["canonical"] == commodity:
            disp_name = item["display_name"]
            break
            
    lang = str(language or "urdu").lower().strip()
    if lang in ("ur", "urdu"):
        lang = "urdu"
    elif lang in ("roman_urdu", "roman"):
        lang = "roman_urdu"
    else:
        lang = "english"
        
    available = [r for r in rates if r.get("rate_available")]
    
    if not available:
        if lang == "urdu":
            return (
                f"معذرت، اس وقت {disp_name} کے لیے منڈی ریٹ کی معلومات دستیاب نہیں ہیں۔\n"
                "براہ کرم بعد میں دوبارہ کوشش کریں۔ حتمی ریٹ مقامی منڈی یا آڑھتی سے تصدیق کر لیں۔"
            )
        elif lang == "roman_urdu":
            return (
                f"Maazrat, is waqt {commodity} ke liye mandi rate ki maloomat dastiyab nahi hain.\n"
                "Barah-e-karam baad mein dobara koshish karein. Final rate local mandi ya arhti se confirm kar lein."
            )
        else:
            return (
                f"Sorry, market rate information for {commodity} is currently unavailable.\n"
                "Please try again later. Kindly confirm final rates from your local mandi or arhti."
            )
            
    lines = []
    if lang == "urdu":
        lines.append(f"آپ کے قریب دستیاب منڈی ریٹس ({disp_name}):")
        for idx, r in enumerate(available, 1):
            city = r["city"]
            dist_str = f" ({r['distance_km']} km)" if r.get("distance_km") is not None else ""
            avg_maund = r["avg_rate_converted"]["rate_per_maund"]
            min_maund = r["min_rate_converted"]["rate_per_maund"]
            max_maund = r["max_rate_converted"]["rate_per_maund"]
            lines.append(f"{idx}. {city}{dist_str}: اوسط ریٹ {avg_maund} روپے فی من (حدود: {min_maund} تا {max_maund} روپے)")
            
        lines.append("")
        lines.append("نوٹ: یہ ریٹس صرف ریفرنس کے لیے ہیں (لوکل موک ڈیٹا)۔ حتمی ریٹ کے لیے اپنے آڑھتی یا منڈی سے رابطہ کریں۔ مستقبل کی قیمتوں کی کوئی گارنٹی نہیں دی جا سکتی۔")
        
    elif lang == "roman_urdu":
        lines.append(f"Aap ke qareeb dastiyab mandi rates ({disp_name}):")
        for idx, r in enumerate(available, 1):
            city = r["city"]
            dist_str = f" ({r['distance_km']} km)" if r.get("distance_km") is not None else ""
            avg_maund = r["avg_rate_converted"]["rate_per_maund"]
            min_maund = r["min_rate_converted"]["rate_per_maund"]
            max_maund = r["max_rate_converted"]["rate_per_maund"]
            lines.append(f"{idx}. {city}{dist_str}: Average rate Rs {avg_maund} per maund (Range: {min_maund} to {max_maund} Rs)")
            
        lines.append("")
        lines.append("Note: symbol rates sirf reference ke liye hain (local mock data). Final rate local mandi ya arhti se confirm kar lein. Future price guarantee nahi ki ja sakti.")
        
    else:  # english
        lines.append(f"Available mandi rates near you ({commodity}):")
        for idx, r in enumerate(available, 1):
            city = r["city"]
            dist_str = f" ({r['distance_km']} km)" if r.get("distance_km") is not None else ""
            avg_maund = r["avg_rate_converted"]["rate_per_maund"]
            min_maund = r["min_rate_converted"]["rate_per_maund"]
            max_maund = r["max_rate_converted"]["rate_per_maund"]
            lines.append(f"{idx}. {city}{dist_str}: Avg rate Rs {avg_maund}/maund (Range: {min_maund} - {max_maund} Rs)")
            
        lines.append("")
        lines.append("Note: These rates are for reference only (local mock data). Please confirm final rates from your local mandi or arhti. Future prices cannot be guaranteed.")
        
    return "\n".join(lines)


def get_market_rate_advice(
    text: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    crop: Optional[str] = None,
    language: str = "urdu"
) -> dict:
    """
    Main entrypoint function for matching rates, locations, and output generation.
    Returns structured market details if intent is detected, or reason details.
    """
    # 1. Intent Detection
    if not detect_market_intent(text):
        return {
            "market_intent": False,
            "reason": "no_market_intent"
        }
        
    # 2. Commodity Detection
    commodity = detect_market_commodity(text, crop)
    if not commodity:
        lang = str(language or "urdu").lower().strip()
        if lang in ("roman_urdu", "roman"):
            guidance = "Barah-e-karam fasal/commodity ka naam batayein, jaise gandum, kapas, aloo, aam, pyaz, tamatar."
        elif lang == "english":
            guidance = "Please specify the crop/commodity name, such as wheat, cotton, potato, mango, onion, tomato."
        else:
            guidance = "براہ کرم فصل/commodity کا نام بتائیں، جیسے گندم، کپاس، آلو، آم، پیاز، ٹماٹر۔"
            
        return {
            "market_intent": True,
            "commodity": None,
            "reason": "commodity_not_detected",
            "market_guidance": guidance
        }
        
    # 3. Find Nearest Mandis
    nearest = find_nearest_mandis(latitude, longitude, limit=3)
    
    # 4. Fetch Rates
    rates = fetch_market_rates(commodity, nearest)
    
    # 5. Format response advice
    market_guidance = format_market_response(commodity, rates, language, source="local_mock")
    
    return {
        "market_intent": True,
        "commodity": commodity,
        "nearest_mandis": nearest,
        "rates": rates,
        "unit": "Rs/100kg",
        "converted_unit": "Rs/maund",
        "market_guidance": market_guidance,
        "source": "local_mock",
        "last_updated": "mock-data",
        "confidence": "mock",
        "safe_note": "Rates are for reference only; confirm from local mandi/arhti."
    }
