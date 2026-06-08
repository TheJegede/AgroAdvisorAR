# F4 Dicamba — Phase 1: `/check` Endpoint (Gates A + C)

**Status:** Ready after Phase 0. Second phase of `AgroAdvisor_F4_PRD_v3.md`.
**Ships:** `POST /api/v1/dicamba/check` returning structured per-gate results for **Gate A** (legal
window, rules lookup) and **Gate C** (weather now). Gates B + D stub-append later — no schema churn.
**Why these gates first:** A is pure rules (Phase 0). C reuses the weather idiom. Both are the most
verifiable; map + attestation-heavy gates come later (PRD §7).

## Context

PRD §3 four-gate model + §6 reliability tiers. The hard rule (PRD §3 callout, §4): the tool **never
invents certainty** — verifiable facts stated as fact; unverifiable items (inversion) returned as
`needs_confirmation`, never auto-`pass`. Existing `weather_history.py` hits the Open-Meteo **archive**
API (historical, county centroid); "spray NOW" needs the **forecast** API at the field point — a new
service, not an extension. Field lat/lon comes from the request (map pin, Phase 2).

## Files

### New: `backend/services/weather_now.py`

Separate from `weather_history.py`. Reuse its `httpx.AsyncClient(timeout=...)` + graceful
`{"available": False}` fallback + compass-label helper convention.

```python
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

async def fetch_forecast_conditions(lat: float, lon: float, at: datetime) -> dict:
    """Near-term spray conditions at (lat, lon) for time `at`.
    Returns {"available": True, ...} or {"available": False}."""
```

Open-Meteo params: `current=wind_speed_10m,wind_direction_10m,temperature_2m`;
`hourly=wind_speed_10m,precipitation,soil_moisture_0_to_1cm,temperature_2m`; `daily=sunrise,sunset`;
`wind_speed_unit=mph`, `temperature_unit=fahrenheit`, `timezone=America/Chicago`, `forecast_hours=48`.

Returned summary: `wind_speed_mph`, `wind_direction_deg`, `wind_direction_label`, `temp_f`,
`precip_next_48h_in` (sum of hourly precip over next 48h), `soil_moisture_0_1cm`, `sunrise`, `sunset`,
and `inversion {risk, is_estimate: True, reason}`.

```python
def _estimate_inversion(wind_mph, at, sunrise, sunset) -> dict:
    """Heuristic ESTIMATE — never a measurement.
    'elevated' when wind_mph < 3.0 AND `at` within ~2h after sunrise OR ~2h before/after sunset;
    'low' otherwise; 'unknown' if any input missing. Always is_estimate=True so callers
    surface it as human-attested confirmation, never an auto-pass."""
```

> Soil-saturation source (Open-Meteo soil moisture vs recent-rainfall proxy) and any mesonet delta-T
> upgrade are PRD §8 open questions — deferred to Phase 5. Phase 1 returns soil moisture as raw value,
> no Gate-C pass/fail on it yet.

### New: `backend/models/spray.py`

```python
GateId      = Literal["A", "B", "C", "D"]
GateStatus  = Literal["pass", "fail", "needs_confirmation"]
CheckTier   = Literal["verifiable_fact", "human_attested"]
CheckStatus = Literal["pass", "fail", "needs_confirmation"]

class ApplicatorAttestation(BaseModel):
    no_inversion_observed: bool | None = None    # Gate C confirmation
    boom_height_ok: bool | None = None           # Gate D (reserved)
    droplet_setup_ok: bool | None = None         # Gate D (reserved)
    sensitive_crops_checked: bool | None = None  # Gate B (reserved)
    tank_clean_ok: bool | None = None            # Gate D (reserved)

class SprayCheckRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    product: str
    at: datetime
    attestation: ApplicatorAttestation = ApplicatorAttestation()

class CheckResult(BaseModel):
    id: str; label: str; tier: CheckTier; status: CheckStatus
    reason: str; observed: str | None = None; expected: str | None = None

class GateResult(BaseModel):
    gate: GateId; title: str; status: GateStatus; checks: list[CheckResult]

class SprayCheckResponse(BaseModel):
    overall_status: GateStatus; rule_version: str; evaluated_at: datetime
    weather_available: bool; gates: list[GateResult]
```

### New: `backend/services/spray_check.py`

```python
def evaluate_gate_a(rules: dict, req: SprayCheckRequest) -> GateResult:
    """Gate A — Legal window. Pure. Checks (verifiable_fact):
    in_season, product_approved, within_cutoff. Failing check => status 'fail'."""

def evaluate_gate_c(rules: dict, weather: dict, req: SprayCheckRequest) -> GateResult:
    """Gate C — Weather now.
    verifiable_fact: wind_in_range, temp_in_range, rain_free_48h.
    human_attested: no_inversion -> 'pass' only if inversion.risk=='low' AND
      attestation.no_inversion_observed is True; else 'needs_confirmation' (NEVER auto-pass).
    If weather.available is False: all verifiable checks -> 'needs_confirmation' (cannot measure)."""

def run_spray_check(req, rules, weather) -> SprayCheckResponse:
    """Assemble Gate A + C; roll up (fail > needs_confirmation > pass); stamp rules['rule_version'].
    Gate B/D evaluators append here later — no signature change."""
```

Roll-up at check→gate→overall: `fail` if any failed; else `needs_confirmation` if any needs it; else
`pass`. Guarantees an unverifiable item can never yield a clean `pass`.

### New: `backend/routers/dicamba.py`

```python
router = APIRouter(prefix="/dicamba", tags=["dicamba"])

@router.post("/check", response_model=SprayCheckResponse)
async def check_spray(body: SprayCheckRequest, user: dict = Depends(get_current_user)):
    try:
        rules = resolve_rules(body.at.date())
    except RulesNotFoundError:
        raise HTTPException(422, "No dicamba rules effective for that date")
    weather = await fetch_forecast_conditions(body.lat, body.lon, body.at)
    return run_spray_check(body, rules, weather)
```

Unapproved product is **not** a 422 — Gate A reports `product_approved=fail` so the checklist shows
it. Stateless (no write → no IDOR surface yet; persistence is Phase 4). Register in `backend/main.py`:
`app.include_router(dicamba_router, prefix="/api/v1")` → `POST /api/v1/dicamba/check`.

## TDD (write tests first)

- `backend/tests/test_weather_now.py` (mirror `test_weather_history.py` httpx mock): parse fields;
  graceful fail → `available False`; 48h precip sum; inversion elevated (calm + near dawn) / low
  (midday breezy) / unknown (missing inputs) / always `is_estimate True`.
- `backend/tests/test_spray_check.py` (pure, no I/O): Gate A pass; fail out-of-season; fail unapproved
  product; fail after cutoff; Gate C all-pass with low inversion + attestation; fail wind>max; fail
  wind<min; fail temp out-of-range; fail rain within 48h; inversion-estimate-alone →
  `needs_confirmation`; inversion `needs_confirmation` when estimate `elevated` even if attested;
  all-`needs_confirmation` when weather unavailable; roll-up precedence; rule_version stamped.
- `backend/tests/test_dicamba_router.py` (mirror `test_drift_reports_router.py`, monkeypatch
  `resolve_rules` + AsyncMock `fetch_forecast_conditions`, `FAKE_USER`): returns Gates A+C; 422 no
  rules; uses authenticated `user["sub"]` (no client-supplied owner trusted); weather-unavailable path.

## Verification

`cd backend && pytest tests/test_weather_now.py tests/test_spray_check.py tests/test_dicamba_router.py`
green; full suite stays green. Manual: `uvicorn main:app --reload`, then authenticated `POST
/api/v1/dicamba/check` with sample field/product/`at` → confirm Gate A + C JSON and inversion
`needs_confirmation`.

## Out of scope

Gate B (map/buffers) + Gate D (equipment) evaluators; persistence/PDF (Phase 4); soil-saturation
pass/fail; UI (Phase 2).
