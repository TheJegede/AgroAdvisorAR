"""Arkansas research-station loader + distance helpers (F4 Phase 3: Gate B).

Static seed list (ar_research_stations.json) is marked UNVERIFIED at source —
provenance is stated, not hidden (PRD v3 §6). Mirrors the load+cache idiom in
services/spray_rules.py. Single source: both evaluate_gate_b and
GET /dicamba/stations read load_stations().
"""
import json
import math
from pathlib import Path

_DEFAULT_PATH = str(Path(__file__).parent.parent / "data" / "ar_research_stations.json")
_cache: dict[str, list[dict]] = {}

# Great-circle earth radius in feet (mean radius 6_371_008.8 m / 0.3048).
_EARTH_RADIUS_FT = 20_902_231.0


def load_stations(path: str | None = None) -> list[dict]:
    """Load + cache the `stations` array. path overrides for tests."""
    p = path or _DEFAULT_PATH
    if p not in _cache:
        with open(p) as f:
            _cache[p] = json.load(f)["stations"]
    return _cache[p]


def haversine_ft(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in feet between two lat/lon points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_RADIUS_FT * math.asin(math.sqrt(a))


def nearest_station(
    lat: float, lon: float, stations: list[dict]
) -> tuple[dict, float] | tuple[None, None]:
    """Nearest station + its distance in ft. (None, None) when list is empty."""
    if not stations:
        return None, None
    best, best_d = None, math.inf
    for s in stations:
        d = haversine_ft(lat, lon, s["lat"], s["lon"])
        if d < best_d:
            best, best_d = s, d
    return best, best_d
