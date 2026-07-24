"""Open-Meteo weather connector (no API key required) — first concrete connector implementation."""
from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorResult, register_connector


@register_connector("weather_open_meteo")
class OpenMeteoConnector(BaseConnector):
    """
    Fetches current + short-range forecast weather for a configured list of
    lat/lon points (e.g. Nigerian state capitals). `config` expects:
        {"locations": [{"name": "Lagos", "lat": 6.5244, "lon": 3.3792}, ...]}
    """

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    async def fetch(self) -> ConnectorResult:
        locations: list[dict[str, Any]] = self.config.get("locations", [])
        records: list[dict[str, Any]] = []

        for loc in locations:
            params = {
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
                "hourly": "temperature_2m,precipitation_probability",
                "forecast_days": 2,
                "timezone": "auto",
            }
            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            payload = response.json()

            current = payload.get("current", {})
            records.append(
                {
                    "location_name": loc["name"],
                    "latitude": loc["lat"],
                    "longitude": loc["lon"],
                    "observed_at": current.get("time"),
                    "temperature_celsius": current.get("temperature_2m"),
                    "humidity_percent": current.get("relative_humidity_2m"),
                    "precipitation_mm": current.get("precipitation"),
                    "wind_speed_kmh": current.get("wind_speed_10m"),
                    "weather_code": current.get("weather_code"),
                    "hourly_forecast": payload.get("hourly", {}),
                }
            )

        return ConnectorResult(
            records=records, raw_count=len(records), metadata={"source": "open-meteo", "locations_count": len(locations)}
        )