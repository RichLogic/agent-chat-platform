"""Weather tool — queries Open-Meteo API (free, no API key required)."""

from __future__ import annotations

from typing import Any

import os
import ssl

import httpx
import structlog

from agent_chat.tools.base import Tool

logger = structlog.get_logger()

# WMO Weather interpretation codes
_WEATHER_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherTool(Tool):
    name = "weather"
    description = "查询指定城市的天气信息。支持当前天气和未来多天预报（最多7天），包括温度、天气状况、风速等。"
    risk_level = "read"
    parameters = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称（英文），例如 Beijing, Tokyo, London",
            },
            "forecast_days": {
                "type": "integer",
                "description": "预报天数，1-7。1 表示只返回当前天气，2 表示今天和明天，以此类推。默认 1",
            },
        },
        "required": ["city"],
    }

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        city = arguments.get("city", "")
        if not city:
            return {"error": "Missing city parameter"}
        forecast_days = min(max(int(arguments.get("forecast_days", 1)), 1), 7)

        try:
            return await self._fetch_weather(city, forecast_days)
        except httpx.HTTPError as e:
            logger.error("weather_api_error", city=city, error=str(e))
            return {"error": f"无法连接天气服务（{type(e).__name__}），请检查网络或代理设置"}

    async def _fetch_weather(self, city: str, forecast_days: int) -> dict[str, Any]:
        proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.load_default_certs()
        async with httpx.AsyncClient(timeout=5.0, proxy=proxy, verify=ssl_ctx) as client:
            # Step 1: Geocode city name to coordinates
            geo_resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1, "language": "en"},
            )
            geo_data = geo_resp.json()

            if not geo_data.get("results"):
                return {"error": f"City not found: {city}"}

            location = geo_data["results"][0]
            lat = location["latitude"]
            lon = location["longitude"]
            resolved_name = location.get("name", city)
            country = location.get("country", "")

            # Step 2: Fetch weather (current + optional daily forecast)
            params: dict[str, Any] = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,apparent_temperature",
                "timezone": "auto",
            }
            if forecast_days > 1:
                params["daily"] = "temperature_2m_max,temperature_2m_min,weather_code,wind_speed_10m_max"
                params["forecast_days"] = forecast_days

            weather_resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params=params,
            )
            weather_data = weather_resp.json()

        current = weather_data.get("current", {})
        weather_code = current.get("weather_code", -1)
        weather_desc = _WEATHER_CODES.get(weather_code, "Unknown")

        result: dict[str, Any] = {
            "city": resolved_name,
            "country": country,
            "current": {
                "temperature": current.get("temperature_2m"),
                "apparent_temperature": current.get("apparent_temperature"),
                "humidity": current.get("relative_humidity_2m"),
                "wind_speed": current.get("wind_speed_10m"),
                "weather": weather_desc,
                "weather_code": weather_code,
            },
            "units": {
                "temperature": weather_data.get("current_units", {}).get("temperature_2m", "°C"),
                "wind_speed": weather_data.get("current_units", {}).get("wind_speed_10m", "km/h"),
                "humidity": "%",
            },
        }

        # Add daily forecast if requested
        daily = weather_data.get("daily")
        if daily and forecast_days > 1:
            dates = daily.get("time", [])
            forecast = []
            for i, date in enumerate(dates):
                code = daily["weather_code"][i] if i < len(daily.get("weather_code", [])) else -1
                forecast.append({
                    "date": date,
                    "temp_max": daily["temperature_2m_max"][i] if i < len(daily.get("temperature_2m_max", [])) else None,
                    "temp_min": daily["temperature_2m_min"][i] if i < len(daily.get("temperature_2m_min", [])) else None,
                    "weather": _WEATHER_CODES.get(code, "Unknown"),
                    "wind_speed_max": daily["wind_speed_10m_max"][i] if i < len(daily.get("wind_speed_10m_max", [])) else None,
                })
            result["forecast"] = forecast

        return result
