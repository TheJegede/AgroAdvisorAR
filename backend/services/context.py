"""SSURGO soil data + NOAA weather context injection service."""
import asyncio
import json
import logging
import httpx
from datetime import date as _date
from utils.counties import get_county_info, fips_to_areasymbol
from services.cache import cache_get, cache_set
import config

logger = logging.getLogger(__name__)

USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
USGS_STAT_URL = "https://waterservices.usgs.gov/nwis/stat/"

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


async def fetch_usgs_well(fips: str) -> dict | None:
    """Return {site_no, current_depth_m, stress_level} for nearest USGS groundwater well.

    Uses USGS Instantaneous Values API (parameterCd=72019 = depth to water, ft below surface).
    Stress level derived from daily percentiles: >p90 = critical, >p75 = stressed.
    Returns None on any failure — callers must treat None as 'data unavailable'.
    Results cached 24 h in Redis.
    """
    cache_key = f"usgs_well:{fips}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    county = get_county_info(fips)
    if not county:
        return None

    lat, lon = county["lat"], county["lon"]

    # Step 1: fetch nearest active groundwater well within 0.5-degree bbox
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            iv_resp = await client.get(
                USGS_IV_URL,
                params={
                    "format": "json",
                    "stateCd": "AR",
                    "parameterCd": "72019",
                    "siteType": "GW",
                    "siteStatus": "active",
                    "bBox": f"{lon - 0.5},{lat - 0.5},{lon + 0.5},{lat + 0.5}",
                },
            )
            iv_resp.raise_for_status()
            iv_data = iv_resp.json()
    except Exception:
        logger.warning("USGS IV fetch failed fips=%s", fips)
        return None

    series = (iv_data.get("value") or {}).get("timeSeries") or []
    if not series:
        return None

    # Pick site nearest to county centroid (Euclidean distance on lat/lon)
    def _dist(ts):
        geo = ((ts.get("sourceInfo") or {}).get("geoLocation") or {}).get("geogLocation") or {}
        return (float(geo.get("latitude", 0)) - lat) ** 2 + (float(geo.get("longitude", 0)) - lon) ** 2

    ts = min(series, key=_dist)
    site_no = (((ts.get("sourceInfo") or {}).get("siteCode") or [{}])[0]).get("value", "")
    raw_values = (((ts.get("values") or [{}])[0]).get("value") or [])
    if not raw_values:
        return None

    try:
        current_depth_ft = float(raw_values[-1]["value"])
    except (ValueError, KeyError):
        return None

    current_depth_m = round(current_depth_ft * 0.3048, 3)

    # Step 2: get today's day-of-year percentile baseline from USGS stats API
    stress_level = "normal"
    try:
        today_mmdd = _date.today().strftime("%m-%d")  # e.g. "05-28"
        async with httpx.AsyncClient(timeout=5.0) as client:
            stat_resp = await client.get(
                USGS_STAT_URL,
                params={
                    "format": "json",
                    "sites": site_no,
                    "parameterCd": "72019",
                    "statReportType": "daily",
                    "statType": "p75_va,p90_va",
                },
            )
            stat_resp.raise_for_status()
            stat_data = stat_resp.json()

        p75: float | None = None
        p90: float | None = None
        for s in ((stat_data.get("value") or {}).get("timeSeries") or []):
            name = s.get("name", "")
            vals = (((s.get("values") or [{}])[0]).get("value") or [])
            # Find today's entry (dateTime format from USGS stats API: "1900-MM-DD")
            for entry in vals:
                dt = entry.get("dateTime", "")
                if dt.endswith(today_mmdd):
                    try:
                        v = float(entry["value"])
                    except (ValueError, KeyError):
                        continue
                    if "p75_va" in name:
                        p75 = v
                    elif "p90_va" in name:
                        p90 = v
                    break

        if p90 is not None and current_depth_ft > p90:
            stress_level = "critical"
        elif p75 is not None and current_depth_ft > p75:
            stress_level = "stressed"
    except Exception:
        logger.warning("USGS stats fetch failed site=%s", site_no)

    result: dict = {
        "site_no": site_no,
        "current_depth_m": current_depth_m,
        "stress_level": stress_level,
    }
    cache_set(cache_key, result, ttl=86400)
    return result
