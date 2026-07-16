from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.schemas.explore import ExploreWeather
from app.services.amap_client import AmapClient
from app.services.simple_cache import TtlCache


class AmapWeatherService:
    def __init__(self, client: AmapClient) -> None:
        self._client = client
        self._weather_cache: TtlCache[ExploreWeather] = TtlCache(max_items=128)

    async def get_city_weather(self, *, adcode: str) -> ExploreWeather:
        normalized_adcode = _normalize_amap_city_adcode(adcode)
        cached = self._weather_cache.get(normalized_adcode)
        if cached is not None:
            return cached

        payload = await self._client.get(
            "/v3/weather/weatherInfo",
            {
                "city": normalized_adcode,
                "extensions": "all",
                "output": "JSON",
            },
        )
        weather = _parse_weather(payload, requested_adcode=adcode, normalized_adcode=normalized_adcode)
        self._weather_cache.set(normalized_adcode, weather, ttl_seconds=1800)
        return weather


def _parse_weather(payload: dict[str, Any], *, requested_adcode: str, normalized_adcode: str) -> ExploreWeather:
    forecasts = payload.get("forecasts")
    if not isinstance(forecasts, list) or not forecasts:
        raise HTTPException(status_code=502, detail="高德天气服务未返回可用预报。")

    forecast = forecasts[0]
    if not isinstance(forecast, dict):
        raise HTTPException(status_code=502, detail="高德天气服务响应格式异常。")

    casts = forecast.get("casts")
    if not isinstance(casts, list) or not casts:
        raise HTTPException(status_code=502, detail="高德天气服务未返回当天预报。")

    today = casts[0]
    if not isinstance(today, dict):
        raise HTTPException(status_code=502, detail="高德天气服务当天预报格式异常。")

    city = _clean_string(forecast.get("city")) or "当前城市"
    adcode = _clean_string(forecast.get("adcode")) or normalized_adcode or requested_adcode
    day_weather = _clean_string(today.get("dayweather"))
    night_weather = _clean_string(today.get("nightweather"))
    day_temp = _clean_string(today.get("daytemp"))
    night_temp = _clean_string(today.get("nighttemp"))
    report_time = _clean_string(forecast.get("reporttime"))

    weather = day_weather or night_weather or "天气"
    weather_label = (
        f"{day_weather}转{night_weather}"
        if day_weather and night_weather and day_weather != night_weather
        else weather
    )
    temp_label = _format_temperature_range(night_temp=night_temp, day_temp=day_temp)
    text = f"{weather_label} {temp_label}".strip() if temp_label else weather_label

    return ExploreWeather(
        city=city,
        adCode=adcode,
        weather=weather_label,
        dayTemp=day_temp,
        nightTemp=night_temp,
        text=text,
        reportTime=report_time,
    )


def _format_temperature_range(*, night_temp: str | None, day_temp: str | None) -> str | None:
    if night_temp and day_temp:
        return f"{night_temp}°-{day_temp}°"
    if day_temp:
        return f"{day_temp}°"
    if night_temp:
        return f"{night_temp}°"
    return None


def _normalize_amap_city_adcode(adcode: str) -> str:
    return {
        "110100": "110000",
        "120100": "120000",
        "310100": "310000",
        "500100": "500000",
    }.get(adcode.strip(), adcode.strip())


def _clean_string(value: Any) -> str | None:
    if value is None or value == []:
        return None
    text = str(value).strip()
    return text or None
