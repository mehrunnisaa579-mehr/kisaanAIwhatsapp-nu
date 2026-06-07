from fastapi import APIRouter, Query
from services.weather_service import get_mock_weather

router = APIRouter()


@router.get("/weather-mock")
async def weather_mock():
    return {
        "rain_expected": False,
        "temperature": 32,
        "humidity": 55,
        "spray_safe": True,
    }


@router.get("/weather")
async def get_weather(
    latitude: float = Query(None),
    longitude: float = Query(None)
):
    return get_mock_weather(latitude, longitude)
