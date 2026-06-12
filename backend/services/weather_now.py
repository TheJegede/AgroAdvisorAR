"""Open-Meteo forecast client for before-you-spray (Gate C) conditions.

Separate from weather_history.py (which hits the archive API for past drift
dates). This hits the forecast API for current/near-term conditions at the
field point. Inversion is a heuristic ESTIMATE, never a measurement — callers
must surface it as a human-attested confirmation, never an auto-pass (PRD §3).
"""
import logging
from datetime import datetime, timedelta

import httpx

from services.weather_history import _degrees_to_compass

logger = logging.getLogger(__name__)

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_INVERSION_WINDOW = timedelta(hours=2)


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _naive(dt: datetime | None) -> datetime | None:
    """Drop tzinfo so request `at` compares against Open-Meteo local-time strings."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None)


def _estimate_inversion(wind_mph, at, sunrise, sunset) -> dict:
    """Heuristic ESTIMATE of temperature-inversion risk — never a measurement.

    'elevated' when wind_mph < 3.0 AND `at` is within 2h after sunrise OR within
    2h before sunset (or later). 'low' otherwise. 'unknown' if any input missing.
    Always is_estimate=True so callers treat it as a confirmation, never a fact.
    """
    at, sunrise, sunset = _naive(at), _naive(sunrise), _naive(sunset)
    if wind_mph is None or at is None or sunrise is None or sunset is None:
        return {
            "risk": "unknown",
            "is_estimate": True,
            "reason": "Insufficient data to estimate inversion risk — confirm conditions on the ground.",
            "reason_es": "Datos insuficientes para estimar el riesgo de inversión — confirme las condiciones en el campo.",
        }
    near_dawn = sunrise <= at <= sunrise + _INVERSION_WINDOW
    near_dusk = at >= sunset - _INVERSION_WINDOW
    if wind_mph < 3.0 and (near_dawn or near_dusk):
        return {
            "risk": "elevated",
            "is_estimate": True,
            "reason": (
                f"Wind {wind_mph} mph and the time is near dawn/dusk — temperature "
                "inversions form in calm air near sunrise and sunset. Confirm no inversion."
            ),
            "reason_es": (
                f"Viento de {wind_mph} mph y la hora está cerca del amanecer/atardecer — las "
                "inversiones térmicas se forman con aire en calma cerca del amanecer y el atardecer. "
                "Confirme que no hay inversión."
            ),
        }
    return {
        "risk": "low",
        "is_estimate": True,
        "reason": (
            f"Wind {wind_mph} mph and the time is away from dawn/dusk — inversion "
            "less likely, but still confirm visually (no smoke/dust hanging low)."
        ),
        "reason_es": (
            f"Viento de {wind_mph} mph y la hora está lejos del amanecer/atardecer — inversión "
            "menos probable, pero confirme visualmente (sin humo/polvo suspendido bajo)."
        ),
    }


async def fetch_forecast_conditions(lat: float, lon: float, at: datetime) -> dict:
    """Near-term spray conditions at (lat, lon) for time `at`.

    Returns {"available": True, ...} or {"available": False} on error.
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                OPEN_METEO_FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "wind_speed_10m,wind_direction_10m,temperature_2m",
                    "hourly": "wind_speed_10m,precipitation,soil_moisture_0_to_1cm,temperature_2m",
                    "daily": "sunrise,sunset",
                    "wind_speed_unit": "mph",
                    "temperature_unit": "fahrenheit",
                    "timezone": "America/Chicago",
                    "forecast_hours": 48,
                },
            )
            resp.raise_for_status()
            raw = resp.json()

        current = raw.get("current", {})
        hourly = raw.get("hourly", {})
        daily = raw.get("daily", {})

        wind_mph = current.get("wind_speed_10m")
        wind_deg = current.get("wind_direction_10m")
        temp_f = current.get("temperature_2m")

        times = hourly.get("time", [])
        precip = hourly.get("precipitation", [])
        soil = hourly.get("soil_moisture_0_to_1cm", [])

        at_naive = _naive(at)
        horizon = at_naive + timedelta(hours=48) if at_naive else None

        # Sum precipitation over the 48h window starting at `at` (exclude past hours).
        # Track coverage: zero matched hours -> precip is UNKNOWN (None), never 0.0,
        # so the rain-free check degrades to needs_confirmation instead of a false
        # pass on no data (F2).
        precip_sum = 0.0
        precip_hours = 0
        soil_now = None
        for i, ts in enumerate(times):
            t = _parse_iso(ts)
            if t is None:
                continue
            if at_naive is not None and at_naive <= t < horizon:
                precip_hours += 1
                if i < len(precip) and precip[i] is not None:
                    precip_sum += precip[i]
                if soil_now is None and i < len(soil) and soil[i] is not None:
                    soil_now = soil[i]
        if soil_now is None:
            soil_now = next((s for s in soil if s is not None), None)
        precip_total = round(precip_sum, 2) if precip_hours > 0 else None

        sunrise = (daily.get("sunrise") or [None])[0]
        sunset = (daily.get("sunset") or [None])[0]

        inversion = _estimate_inversion(
            wind_mph, at, _parse_iso(sunrise), _parse_iso(sunset)
        )

        return {
            "available": True,
            "source": "open-meteo-forecast",
            "at": at.isoformat(),
            "wind_speed_mph": round(wind_mph, 1) if wind_mph is not None else None,
            "wind_direction_deg": round(wind_deg, 1) if wind_deg is not None else None,
            "wind_direction_label": _degrees_to_compass(wind_deg) if wind_deg is not None else None,
            "temp_f": round(temp_f, 1) if temp_f is not None else None,
            "precip_next_48h_in": precip_total,
            "soil_moisture_0_1cm": round(soil_now, 3) if soil_now is not None else None,
            "sunrise": sunrise,
            "sunset": sunset,
            "inversion": inversion,
        }
    except Exception:
        logger.exception(
            "Open-Meteo forecast fetch failed lat=%s lon=%s at=%s", lat, lon, at
        )
        return {"available": False}
