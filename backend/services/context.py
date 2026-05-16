"""SSURGO soil data + NOAA weather context injection service."""
import asyncio
import json
import logging
import httpx
from utils.counties import get_county_info, fips_to_areasymbol
from services.cache import cache_get, cache_set
import config

logger = logging.getLogger(__name__)

SSURGO_QUERY = """
SELECT TOP 1
  c.compname AS dominant_series,
  ct.texcl AS texture_class,
  ch.ph1to1h2o_r AS ph,
  ch.om_r AS organic_matter_pct,
  c.drainagecl AS drainage_class,
  c.floodtype AS flood_frequency,
  c.comppct_r AS component_pct
FROM legend l
INNER JOIN mapunit mu ON mu.lkey = l.lkey
INNER JOIN component c ON c.mukey = mu.mukey
LEFT OUTER JOIN chorizon ch ON ch.cokey = c.cokey
LEFT OUTER JOIN chtexturegrp ctg ON ctg.chkey = ch.chkey AND ctg.rvindicator = 'Yes'
LEFT OUTER JOIN chtexture ct ON ct.chtgkey = ctg.chtgkey
WHERE l.areasymbol = '{area_symbol}'
  AND c.majcompflag = 'Yes'
  AND c.compkind != 'Miscellaneous area'
ORDER BY c.comppct_r DESC
"""


def _unavailable() -> dict:
    return {"available": False}


async def fetch_ssurgo(fips: str) -> dict:
    cache_key = f"ssurgo:{fips}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    area_symbol = fips_to_areasymbol(fips)
    query = SSURGO_QUERY.format(area_symbol=area_symbol).strip()

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(
                config.SSURGO_ENDPOINT,
                data={"query": query, "format": "json+columnname+metadata"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            raw = resp.json()

        table = raw.get("Table", [])
        # table[0]=headers, table[1]=col metadata, table[2]=first data row
        if len(table) < 3:
            return _unavailable()

        headers = table[0]
        row = dict(zip(headers, table[2]))
        result = {
            "available": True,
            "dominant_series": row.get("dominant_series"),
            "texture_class": row.get("texture_class"),
            "ph": row.get("ph"),
            "organic_matter_pct": row.get("organic_matter_pct"),
            "drainage_class": row.get("drainage_class"),
            "flood_frequency": row.get("flood_frequency"),
        }
    except Exception:
        logger.exception("SSURGO context fetch failed for fips %s", fips)
        return _unavailable()

    cache_set(cache_key, result)
    return result


async def fetch_noaa(fips: str) -> dict:
    cache_key = f"noaa:{fips}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    county = get_county_info(fips)
    if not county:
        return _unavailable()

    lat, lon = county["lat"], county["lon"]

    try:
        async with httpx.AsyncClient(
            timeout=3.0,
            headers={"User-Agent": config.NOAA_USER_AGENT},
        ) as client:
            # Step 1: resolve gridpoint
            points_resp = await client.get(config.NOAA_POINTS_URL.format(lat=lat, lon=lon))
            points_resp.raise_for_status()
            props = points_resp.json()["properties"]
            grid_id = props["gridId"]
            grid_x = props["gridX"]
            grid_y = props["gridY"]

            # Step 2: fetch 7-day forecast
            forecast_resp = await client.get(
                f"https://api.weather.gov/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast"
            )
            forecast_resp.raise_for_status()
            periods = forecast_resp.json()["properties"]["periods"]

        # Aggregate first 7 daytime periods
        daily = []
        for p in periods:
            if p.get("isDaytime") and len(daily) < 7:
                daily.append({
                    "name": p["name"],
                    "temp_high_f": p["temperature"],
                    "precip_pct": p.get("probabilityOfPrecipitation", {}).get("value"),
                    "wind": p.get("windSpeed"),
                    "short_forecast": p["shortForecast"],
                })

        result = {
            "available": True,
            "county": county["county_name"],
            "forecast_7day": daily,
        }
    except Exception:
        logger.exception("NOAA context fetch failed for fips %s", fips)
        return _unavailable()

    cache_set(cache_key, result)
    return result


async def get_context(fips: str) -> dict:
    """Fetch both SSURGO and NOAA context concurrently."""
    soil, weather = await asyncio.gather(
        fetch_ssurgo(fips),
        fetch_noaa(fips),
    )
    return {"soil": soil, "weather": weather}
