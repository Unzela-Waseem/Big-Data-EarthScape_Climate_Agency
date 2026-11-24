"""Fetch model-based current weather for the Live Monitor.

Open-Meteo current conditions are derived from weather-model data. They are
useful for a frequently refreshed local reading, but are not direct sensor
observations or a replacement for the monthly global climate series.
"""

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


LOCATIONS = {
    "karachi": {"name": "Karachi", "latitude": 24.8607, "longitude": 67.0011},
    "lahore": {"name": "Lahore", "latitude": 31.5204, "longitude": 74.3587},
    "islamabad": {"name": "Islamabad", "latitude": 33.6844, "longitude": 73.0479},
    "peshawar": {"name": "Peshawar", "latitude": 34.0151, "longitude": 71.5249},
    "quetta": {"name": "Quetta", "latitude": 30.1798, "longitude": 66.9750},
}

PROVIDER = "Open-Meteo"
PROVIDER_URL = "https://open-meteo.com/"


def fetch_current_weather(city):
    """Fetch the latest available current-condition model data for a city."""
    location = LOCATIONS.get(city)
    if location is None:
        raise ValueError("Unknown weather location")

    params = urlencode({
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "timezone": "auto",
    })
    request = Request(
        f"https://api.open-meteo.com/v1/forecast?{params}",
        headers={"User-Agent": "EarthScape-Climate-Agency/1.0"},
    )
    with urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))

    current = payload.get("current") or {}
    temperature = current.get("temperature_2m")
    observed_at = current.get("time")
    if temperature is None or not observed_at:
        raise ValueError("Weather provider returned incomplete current conditions")

    return {
        "city": city,
        "city_name": location["name"],
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "observed_at": observed_at,
        "timezone": payload.get("timezone", "UTC"),
        "temperature_c": float(temperature),
        "apparent_temperature_c": _optional_float(current.get("apparent_temperature")),
        "relative_humidity_pct": _optional_float(current.get("relative_humidity_2m")),
        "wind_speed_kmh": _optional_float(current.get("wind_speed_10m")),
        "provider": PROVIDER,
        "provider_url": PROVIDER_URL,
        "data_kind": "model_based_current_conditions",
    }


def _optional_float(value):
    return float(value) if value is not None else None
