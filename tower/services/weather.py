from __future__ import annotations

import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from ..models import Location, RiskLevel, WeatherCondition, WeatherSnapshot, WeatherSource


logger = logging.getLogger(__name__)

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _risk_from_condition(condition: str) -> str:
    if condition == WeatherCondition.STORM:
        return RiskLevel.HIGH
    if condition == WeatherCondition.RAIN:
        return RiskLevel.MEDIUM
    if condition == WeatherCondition.CLEAR:
        return RiskLevel.LOW
    return RiskLevel.LOW


def _condition_from_openweather(main: str) -> str:
    main_norm = (main or "").strip().lower()
    if main_norm in {"thunderstorm", "tornado", "squall"}:
        return WeatherCondition.STORM
    if main_norm in {"rain", "drizzle"}:
        return WeatherCondition.RAIN
    if main_norm in {"fog", "mist", "haze"}:
        return WeatherCondition.FOG
    if main_norm in {"clear", "clouds", "smoke", "dust", "sand", "ash"}:
        return WeatherCondition.CLEAR
    return WeatherCondition.UNKNOWN


def _condition_from_open_meteo_code(code: int | None) -> str:
    if code is None:
        return WeatherCondition.UNKNOWN
    # Open-Meteo weather codes: https://open-meteo.com/en/docs
    if code in {95, 96, 99}:
        return WeatherCondition.STORM
    if 61 <= code <= 67 or 80 <= code <= 82 or 51 <= code <= 57:
        return WeatherCondition.RAIN
    if code in {45, 48}:
        return WeatherCondition.FOG
    if code in {0, 1, 2, 3}:
        return WeatherCondition.CLEAR
    return WeatherCondition.UNKNOWN


def get_or_fetch_weather(location: Location, *, force: bool = False) -> WeatherSnapshot | None:
    now = timezone.now()
    ttl = timedelta(seconds=getattr(settings, "WEATHER_CACHE_TTL_SECONDS", 300))

    snapshot = WeatherSnapshot.objects.filter(location=location).first()
    if snapshot and not force and snapshot.expires_at and snapshot.expires_at > now:
        return snapshot

    try:
        if getattr(settings, "OPENWEATHER_API_KEY", ""):
            payload = _fetch_openweather(location)
            condition = _condition_from_openweather(payload.get("weather", [{}])[0].get("main", ""))
            temp_c = (payload.get("main") or {}).get("temp")
            source = WeatherSource.OPENWEATHER
            raw = payload
        else:
            payload = _fetch_open_meteo(location)
            current = payload.get("current") or {}
            condition = _condition_from_open_meteo_code(current.get("weather_code"))
            temp_c = current.get("temperature_2m")
            source = WeatherSource.OPEN_METEO
            raw = payload

        risk = _risk_from_condition(condition)

        if snapshot is None:
            snapshot = WeatherSnapshot(location=location)

        snapshot.source = source
        snapshot.condition = condition
        snapshot.risk_level = risk
        snapshot.temperature_c = float(temp_c) if temp_c is not None else None
        snapshot.raw_json = raw
        snapshot.fetched_at = now
        snapshot.expires_at = now + ttl
        if snapshot.pk:
            snapshot.save(
                update_fields=[
                    "source",
                    "condition",
                    "risk_level",
                    "temperature_c",
                    "raw_json",
                    "fetched_at",
                    "expires_at",
                    "updated_at",
                ]
            )
        else:
            snapshot.save()
        return snapshot
    except Exception as exc:
        # Keep refresh jobs resilient in restricted/offline environments.
        logger.warning("Weather fetch failed for %s: %s", location, exc)
        if snapshot is None:
            snapshot = WeatherSnapshot(location=location)
        snapshot.source = WeatherSource.OPEN_METEO
        snapshot.condition = WeatherCondition.UNKNOWN
        snapshot.risk_level = RiskLevel.LOW
        snapshot.temperature_c = None
        snapshot.raw_json = {"fallback": True, "reason": "weather_fetch_failed"}
        snapshot.fetched_at = now
        snapshot.expires_at = now + ttl
        if snapshot.pk:
            snapshot.save(
                update_fields=[
                    "source",
                    "condition",
                    "risk_level",
                    "temperature_c",
                    "raw_json",
                    "fetched_at",
                    "expires_at",
                    "updated_at",
                ]
            )
        else:
            snapshot.save()
        return snapshot


def _fetch_openweather(location: Location) -> dict:
    params = {
        "lat": location.latitude,
        "lon": location.longitude,
        "appid": settings.OPENWEATHER_API_KEY,
        "units": "metric",
    }
    resp = requests.get(OPENWEATHER_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _fetch_open_meteo(location: Location) -> dict:
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "current": "weather_code,temperature_2m",
    }
    resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()
