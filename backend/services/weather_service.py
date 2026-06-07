"""
FarmAI Weather Service
Fetches live weather data from Open-Meteo or returns mock fallback data.
"""

import requests
import os
import logging

logger = logging.getLogger(__name__)


def get_live_weather(latitude: float, longitude: float) -> dict:
    """
    Fetch current live weather from Open-Meteo API using coordinate inputs.
    """
    try:
        base_url = os.getenv("OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1/forecast").strip()
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,rain,precipitation",
            "hourly": "precipitation_probability",
            "forecast_days": 1
        }
        res = requests.get(base_url, params=params, timeout=5)
        if res.status_code == 200:
            data = res.json()
            current = data.get("current", {})
            hourly = data.get("hourly", {})
            
            temp = current.get("temperature_2m", 32)
            humidity = current.get("relative_humidity_2m", 55)
            rain = current.get("rain", 0.0)
            precipitation = current.get("precipitation", 0.0)
            
            # Check rain expected: if it's currently raining, or if any of the next 6 hours has > 30% rain probability
            rain_probs = hourly.get("precipitation_probability", [])
            next_6_hours_probs = rain_probs[:6] if rain_probs else []
            max_prob = max(next_6_hours_probs) if next_6_hours_probs else 0
            
            rain_expected = (rain > 0 or precipitation > 0 or max_prob > 30)
            
            # Spray safe if no rain is expected and humidity is not extremely high (e.g. < 85%)
            spray_safe = not rain_expected and humidity < 85
            
            return {
                "temperature": int(round(temp)) if temp is not None else 32,
                "humidity": int(round(humidity)) if humidity is not None else 55,
                "rain_expected": bool(rain_expected),
                "rain_probability": int(max_prob),
                "spray_safe": bool(spray_safe),
                "location": "منتقل مقام",
                "source": "open_meteo"
            }
        else:
            logger.error(f"Open-Meteo API returned status code {res.status_code}")
    except Exception as e:
        logger.error(f"Error fetching live weather: {e}")
        
    return {
        "temperature": 32,
        "humidity": 55,
        "rain_expected": False,
        "rain_probability": 20,
        "spray_safe": True,
        "location": "مقام دستیاب نہیں (Fallback)",
        "source": "fallback"
    }


def get_mock_weather(latitude: float = None, longitude: float = None) -> dict:
    """
    Return weather data. If coordinates exist, fetch live data.
    """
    if latitude is not None and longitude is not None:
        return get_live_weather(latitude, longitude)
        
    return {
        "temperature": 32,
        "humidity": 55,
        "rain_expected": False,
        "rain_probability": 20,
        "spray_safe": True,
        "location": "مقام دستیاب نہیں",
        "source": "mock_weather_no_location",
    }
