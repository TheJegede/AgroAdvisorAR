"""GET /api/v1/admin/aquifer-stress — USGS well stress levels for all 75 AR counties."""
import asyncio
import logging

from fastapi import APIRouter, Depends

from services.admin import require_admin
from services.context import fetch_usgs_well
from services.cache import cache_get, cache_set
from utils.counties import AR_COUNTIES

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

_CACHE_KEY = "admin:aquifer_stress_all"
_CACHE_TTL = 86400  # 24 h


@router.get("/aquifer-stress")
async def aquifer_stress(_: dict = Depends(require_admin)):
    """Return {county_fips: stress_level} for all 75 AR counties. Cached 24 h."""
    cached = cache_get(_CACHE_KEY)
    if cached:
        return {"data": cached}

    fips_list = list(AR_COUNTIES.keys())
    wells = await asyncio.gather(
        *[fetch_usgs_well(f) for f in fips_list],
        return_exceptions=True,
    )

    result: dict[str, str] = {}
    for fips, well in zip(fips_list, wells):
        if isinstance(well, Exception) or well is None:
            result[fips] = "normal"
        else:
            result[fips] = well.get("stress_level", "normal")

    cache_set(_CACHE_KEY, result, ttl=_CACHE_TTL)
    return {"data": result}
