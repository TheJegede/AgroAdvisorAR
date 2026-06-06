"""Growing degree day accumulation from Open-Meteo historical archive."""
import logging
from datetime import date

import httpx

from utils.counties import AR_COUNTIES

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"


async def compute_gdd_since_jan1(
    county_fips: str, base_temp_c: float = 10.0, upper_cap_c: float = 30.0
) -> float:
    """Return cumulative GDD (base 10°C, tmax capped at 30°C) from Jan 1 to today
    for a given AR county.

    Standard rice/soybean GDD models cap the daily high so hot days don't inflate
    accumulation. Without the cap, cumulative GDD overshoots on hot Arkansas days
    and pest alerts (rice_water_weevil, palmer_amaranth) fire days early.

    Returns 0.0 on any error so the alert engine fails open.
    """
    if county_fips not in AR_COUNTIES:
        logger.warning("Unknown county FIPS %s — returning 0 GDD", county_fips)
        return 0.0

    _, lat, lon, _ = AR_COUNTIES[county_fips]
    today = date.today()
    start_date = f"{today.year}-01-01"
    end_date = today.isoformat()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                OPEN_METEO_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": start_date,
                    "end_date": end_date,
                    "daily": "temperature_2m_max,temperature_2m_min",
                    "temperature_unit": "celsius",
                    "timezone": "America/Chicago",
                },
            )
            resp.raise_for_status()
            raw = resp.json()

        daily = raw.get("daily", {})
        t_max = daily.get("temperature_2m_max", [])
        t_min = daily.get("temperature_2m_min", [])

        gdd = 0.0
        for tmax, tmin in zip(t_max, t_min):
            if tmax is None or tmin is None:
                continue
            capped_tmax = min(tmax, upper_cap_c)
            gdd += max(0.0, (capped_tmax + tmin) / 2.0 - base_temp_c)

        return round(gdd, 2)

    except Exception:
        logger.exception("GDD fetch failed for fips=%s", county_fips)
        return 0.0
