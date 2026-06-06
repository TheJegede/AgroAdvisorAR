"""Open-Meteo archive API client for historical weather at drift incident date."""
import httpx
import logging
import math

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"

_COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _degrees_to_compass(deg: float) -> str:
    return _COMPASS[round(deg / 22.5) % 16]


async def fetch_historical_weather(lat: float, lon: float, date: str) -> dict:
    """Fetch historical weather from Open-Meteo.

    Args:
        lat: County centroid latitude.
        lon: County centroid longitude.
        date: YYYY-MM-DD string.

    Returns:
        Summary dict with hourly_summary key, or {"available": False} on error.
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                OPEN_METEO_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": date,
                    "end_date": date,
                    "hourly": "windspeed_10m,winddirection_10m,temperature_2m",
                    "wind_speed_unit": "mph",
                    "temperature_unit": "fahrenheit",
                    "timezone": "America/Chicago",
                },
            )
            resp.raise_for_status()
            raw = resp.json()

        hourly = raw.get("hourly", {})
        times = hourly.get("time", [])
        raw_speeds = hourly.get("windspeed_10m", [])
        raw_dirs = hourly.get("winddirection_10m", [])
        temps = hourly.get("temperature_2m", [])

        def _hour_of(ts: str) -> int | None:
            # Open-Meteo hourly timestamps are local "YYYY-MM-DDTHH:MM".
            try:
                return int(ts[11:13])
            except (TypeError, ValueError, IndexError):
                return None

        # Pick the value AT local noon by matching the hour label, not a fixed
        # index — temps[12] is off by an hour on DST-transition days (F14).
        temp_at_noon = None
        noon_idx = next(
            (i for i, ts in enumerate(times) if _hour_of(ts) == 12), None
        )
        if noon_idx is not None and noon_idx < len(temps) and temps[noon_idx] is not None:
            temp_at_noon = temps[noon_idx]
        elif temps:
            temp_at_noon = next((t for t in temps if t is not None), None)

        # Wind over the typical daytime application window (08:00–18:00) rather
        # than a full 24h average, which would dilute a high-wind spray window
        # with calm overnight hours in the drift PDF (F14). Fall back to all
        # hours when timestamps are unavailable.
        if times and len(times) == len(raw_speeds):
            day_idx = [i for i, ts in enumerate(times)
                       if (_hour_of(ts) is not None and 8 <= _hour_of(ts) <= 18)]
        else:
            day_idx = list(range(len(raw_speeds)))
        wind_speeds = [raw_speeds[i] for i in day_idx
                       if i < len(raw_speeds) and raw_speeds[i] is not None]
        wind_dirs = [raw_dirs[i] for i in day_idx
                     if i < len(raw_dirs) and raw_dirs[i] is not None]

        wind_speed_avg = sum(wind_speeds) / len(wind_speeds) if wind_speeds else None
        if wind_dirs:
            sin_avg = sum(math.sin(math.radians(d)) for d in wind_dirs) / len(wind_dirs)
            cos_avg = sum(math.cos(math.radians(d)) for d in wind_dirs) / len(wind_dirs)
            wind_dir_avg = math.degrees(math.atan2(sin_avg, cos_avg)) % 360
            wind_dir_label = _degrees_to_compass(wind_dir_avg)
        else:
            wind_dir_avg = None
            wind_dir_label = None

        return {
            "available": True,
            "source": "open-meteo",
            "date": date,
            "lat": lat,
            "lon": lon,
            "hourly_summary": {
                "wind_speed_mph_avg": round(wind_speed_avg, 1) if wind_speed_avg is not None else None,
                "wind_direction_deg_avg": round(wind_dir_avg, 1) if wind_dir_avg is not None else None,
                "wind_direction_label": wind_dir_label,
                "temp_f_at_noon": round(temp_at_noon, 1) if temp_at_noon is not None else None,
            },
        }
    except Exception:
        logger.exception(
            "Open-Meteo historical fetch failed lat=%s lon=%s date=%s", lat, lon, date
        )
        return {"available": False}
