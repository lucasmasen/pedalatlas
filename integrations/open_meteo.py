"""Open-Meteo forecast lookups.

The request is coordinates and field names only. Forecasts from this module
are short-lived observations, not material for a permanent wiki page.
Documented endpoint: https://api.open-meteo.com/v1/forecast
"""

from __future__ import annotations

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WMO_CODES = {
    0: "clear",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "rime fog",
    51: "light drizzle",
    53: "drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
}


def forecast_params(lat: float, lon: float) -> dict[str, str | int]:
    return {
        "latitude": f"{lat:.5f}",
        "longitude": f"{lon:.5f}",
        "current": "temperature_2m,precipitation,wind_speed_10m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,snowfall_sum,wind_speed_10m_max",
        "forecast_days": 7,
        "timezone": "auto",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }


def _at(daily: dict, key: str, index: int):
    values = daily.get(key) or []
    if index >= len(values):
        return None
    return values[index]


def condition_label(code: int | None) -> str:
    if code is None:
        return "unknown"
    return WMO_CODES.get(int(code), f"code {int(code)}")


def parse_forecast(payload: dict) -> dict:
    current = payload.get("current") or {}
    daily = payload.get("daily") or {}
    days = []
    for index, day in enumerate((daily.get("time") or [])[:7]):
        days.append(
            {
                "date": day,
                "temp_max_c": _at(daily, "temperature_2m_max", index),
                "temp_min_c": _at(daily, "temperature_2m_min", index),
                "precipitation_mm": _at(daily, "precipitation_sum", index),
                "snowfall_cm": _at(daily, "snowfall_sum", index),
                "wind_max_kmh": _at(daily, "wind_speed_10m_max", index),
            }
        )
    code = current.get("weather_code")
    return {
        "current": {
            "temperature_c": current.get("temperature_2m"),
            "precipitation_mm": current.get("precipitation"),
            "wind_kmh": current.get("wind_speed_10m"),
            "weather_code": code,
            "condition": condition_label(code) if code is not None else "unknown",
        },
        "daily": days,
    }


def fetch_forecast(lat: float, lon: float, client: httpx.Client) -> dict:
    response = client.get(FORECAST_URL, params=forecast_params(lat, lon), timeout=20.0)
    response.raise_for_status()
    return parse_forecast(response.json())
