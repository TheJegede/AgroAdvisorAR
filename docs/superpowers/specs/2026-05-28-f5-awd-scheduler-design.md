# F5 — AWD Irrigation Scheduler + Aquifer-Aware Advisory

**Date:** 2026-05-28
**Status:** Approved
**PRD ref:** §F5

---

## Overview

Rice farmers receive per-field Alternate Wetting and Drying (AWD) irrigation stage
recommendations ("re-flood now / in 2 days / maintain flood") injected into every RAG
response, backed by USGS aquifer well data and SSURGO soil drainage class. Low-threshold
fields trigger proactive alerts via the existing F3 alert infrastructure. The admin
choropleth gains a second "Aquifer Stress" toggle layer.

NIW angle: water-conservation advisory for AR Delta rice (Climate-Smart Commodities);
AR aquifer depletion is a nationally-significant resource concern.

---

## Architecture & Data Flow

```
RegisterForm step 4 (rice only)
  → rice_fields jsonb saved on farmer_profiles (migration 007)
  ↓
query.py
  → profile includes rice_fields
  → run_rag_query(..., rice_fields=[...])
        ├── fetch_usgs_well(fips)           ← new in context.py
        ├── awd_scheduler.compute_awd_stage()  per field
        └── format_awd_context() → string
              ↓ injected into build_system_prompt(awd_context=...)
  ↓
nightly_alerts.py (06:00 CT daily)
  → per rice farmer per field:
        awd_scheduler.compute_awd_stage()
        days_to_threshold <= 2 → alerts insert + Redis dedup
  ↓
GET /api/v1/admin/aquifer-stress
  → fetch_usgs_well() for all 75 counties (parallel, 24h Redis cache)
  → ARCountyMap.jsx second toggle layer
```

---

## Components

### `backend/data/awd_thresholds.json` (new)

Dry rate is cm of water table drop per day after flood ends, derived from UA Extension
AWD guidelines (MP192). Threshold is 15 cm below surface for all classes.

```json
{
  "poorly drained":           {"dry_rate_cm_per_day": 0.5, "threshold_cm": 15},
  "somewhat poorly drained":  {"dry_rate_cm_per_day": 0.8, "threshold_cm": 15},
  "moderately well drained":  {"dry_rate_cm_per_day": 1.2, "threshold_cm": 15},
  "well drained":             {"dry_rate_cm_per_day": 1.5, "threshold_cm": 15},
  "default":                  {"dry_rate_cm_per_day": 0.8, "threshold_cm": 15}
}
```

---

### `backend/services/awd_scheduler.py` (new)

```python
from datetime import date
import json
import math
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel

_THRESHOLDS_PATH = Path(__file__).parent.parent / "data" / "awd_thresholds.json"
_thresholds: dict | None = None


class AWDStageResult(BaseModel):
    field_name: str
    days_to_threshold: int
    recommendation: Literal["maintain flood", "prepare to re-flood", "re-flood now"]
    aquifer_stress_level: Literal["normal", "stressed", "critical"]
    well_depth_m: Optional[float]


def _get_thresholds() -> dict:
    global _thresholds
    if _thresholds is None:
        _thresholds = json.loads(_THRESHOLDS_PATH.read_text())
    return _thresholds


def compute_awd_stage(
    field_name: str,
    last_flood_date: date,
    drainage_class: str,
    current_well_m: float | None,
    aquifer_stress_level: Literal["normal", "stressed", "critical"] = "normal",
) -> AWDStageResult:
    thresholds = _get_thresholds()
    key = (drainage_class or "").lower()
    cfg = thresholds.get(key) or thresholds["default"]
    dry_rate: float = cfg["dry_rate_cm_per_day"]
    threshold_cm: float = cfg["threshold_cm"]

    days_elapsed = max(0, (date.today() - last_flood_date).days)
    estimated_depth_cm = days_elapsed * dry_rate

    if estimated_depth_cm >= threshold_cm:
        days_left = 0
    else:
        days_left = math.ceil((threshold_cm - estimated_depth_cm) / dry_rate)

    if days_left <= 0:
        rec = "re-flood now"
    elif days_left <= 2:
        rec = "prepare to re-flood"
    else:
        rec = "maintain flood"

    return AWDStageResult(
        field_name=field_name,
        days_to_threshold=days_left,
        recommendation=rec,
        aquifer_stress_level=aquifer_stress_level,
        well_depth_m=current_well_m,
    )


def format_awd_context(results: list[AWDStageResult]) -> str:
    lines = ["[AWD IRRIGATION STATUS]"]
    for r in results:
        lines.append(
            f"Field '{r.field_name}': {r.recommendation}. "
            f"Days to re-flood threshold: {r.days_to_threshold}. "
            f"Aquifer stress: {r.aquifer_stress_level}."
            + (f" USGS well depth: {r.well_depth_m:.2f}m." if r.well_depth_m else "")
        )
    return "\n".join(lines)
```

---

### `context.py` — add `fetch_usgs_well(fips)` (modified)

USGS Instantaneous Values API (no API key required):
- Endpoint: `https://waterservices.usgs.gov/nwis/iv/?format=json&stateCd=AR&parameterCd=72019&siteType=GW&siteStatus=active&bBox={lon_min},{lat_min},{lon_max},{lat_max}`
- `parameterCd=72019` = depth to water level, feet below land surface
- Bounding box: county lat/lon ± 0.5 degrees
- Pick nearest site to county centroid (Euclidean distance on lat/lon)
- Convert feet to meters: × 0.3048

USGS Stats API (percentile baseline):
- Endpoint: `https://waterservices.usgs.gov/nwis/stat/?format=json&sites={site_no}&parameterCd=72019&statReportType=daily&statType=p75_va,p90_va`
- `p75_va`: 75th percentile depth. If `current > p75_va` → stressed
- `p90_va`: 90th percentile depth. If `current > p90_va` → critical
- (Higher depth = more depletion = worse for aquifer)

Both responses cached in Redis at keys `usgs_well:{fips}` (TTL 86400s).
On any exception: return `None` and log warning (fails open).

```python
async def fetch_usgs_well(fips: str) -> dict | None:
    """Returns {site_no, current_depth_m, stress_level} or None on failure."""
    cache_key = f"usgs_well:{fips}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    # ... USGS IV call, stats call, stress_level computation ...
    cache_set(cache_key, result, ttl=86400)
    return result
```

`get_context(fips)` unchanged — callers that need well data call `fetch_usgs_well` directly.

---

### Migration 007 — `backend/supabase/migrations/007_rice_fields.sql` (new)

```sql
ALTER TABLE farmer_profiles
  ADD COLUMN IF NOT EXISTS rice_fields jsonb NOT NULL DEFAULT '[]'::jsonb;
```

`rice_fields` schema (enforced in application layer, not DB):
```json
[
  {
    "field_name": "North 40",
    "acres": 40.0,
    "last_flood_date": "2026-05-01",
    "irrigation_method": "continuous flood"
  }
]
```

`irrigation_method` enum: `"continuous flood"` | `"intermittent"` | `"awd"`.
`acres` optional. `field_name` and `last_flood_date` required.

---

### `backend/models/user.py` (modified)

Add `RiceField` model and optional `rice_fields` field:

```python
from datetime import date as DateType

class RiceField(BaseModel):
    field_name: str
    acres: float | None = None
    last_flood_date: DateType
    irrigation_method: Literal["continuous flood", "intermittent", "awd"] = "continuous flood"
```

Add to `RegisterRequest`:
```python
rice_fields: list[RiceField] = Field(default_factory=list)
```

Add to `FarmerProfile`:
```python
rice_fields: list[dict] = Field(default_factory=list)
```

Add to `UpdateProfileRequest`:
```python
rice_fields: list[RiceField] | None = None
```

---

### `backend/services/user.py` (modified)

`create_profile` — add `rice_fields: list[dict] = []` parameter, include in insert dict:
```python
"rice_fields": rice_fields,
```

`update_profile` — serialize `rice_fields` if present in updates:
```python
if "rice_fields" in updates and updates["rice_fields"] is not None:
    updates["rice_fields"] = [
        f.model_dump() if hasattr(f, "model_dump") else f
        for f in updates["rice_fields"]
    ]
```

---

### `backend/routers/auth.py` (modified)

Pass `rice_fields` through `create_profile`:
```python
create_profile(
    user_id=user_id,
    full_name=body.full_name,
    county_fips=body.county_fips,
    primary_crops=body.primary_crops,
    language=body.language,
    rice_fields=[f.model_dump() for f in body.rice_fields],
)
```

---

### `backend/services/rag.py` (modified)

`run_rag_query` gains new parameter:
```python
async def run_rag_query(
    *,
    message: str,
    county_fips: str,
    language: str,
    category: str,
    session_history: list[dict],
    rice_fields: list[dict] | None = None,   # NEW
) -> tuple[AdvisoryResponse, list[dict]]:
```

After `ctx = await context_task`, if `category == "RICE"` and rice_fields:
```python
awd_context: str | None = None
if rice_fields and category == "IN_SCOPE_RICE":
    from services import awd_scheduler
    from services.context import fetch_usgs_well
    usgs = await fetch_usgs_well(county_fips)
    stress = (usgs or {}).get("stress_level", "normal")
    well_m = (usgs or {}).get("current_depth_m")
    drainage = (soil or {}).get("drainage_class") or "default"

    results = [
        awd_scheduler.compute_awd_stage(
            field_name=f["field_name"],
            last_flood_date=date.fromisoformat(f["last_flood_date"]),
            drainage_class=drainage,
            current_well_m=well_m,
            aquifer_stress_level=stress,
        )
        for f in rice_fields[:3]  # max 3 fields in context
    ]
    awd_context = awd_scheduler.format_awd_context(results)
```

Pass `awd_context` to `build_system_prompt(awd_context=awd_context)`.

---

### `backend/utils/prompt.py` (modified)

Add `awd_context: str | None = None` to `build_system_prompt` signature.
Insert after the local conditions block:
```python
if awd_context:
    parts.append(awd_context)
    parts.append("")
```

---

### `backend/routers/query.py` (modified)

Pass `rice_fields` from profile:
```python
profile = get_profile(user["sub"])
county_fips = (profile or {}).get("county_fips") or "05055"
rice_fields = (profile or {}).get("rice_fields") or []

# inside event_stream():
result, retrieved_chunks = await run_rag_query(
    ...
    rice_fields=rice_fields,
)
```

---

### `backend/routers/admin_aquifer.py` (new)

```python
"""GET /api/v1/admin/aquifer-stress — USGS well stress levels for all 75 AR counties."""
import asyncio
import logging
from fastapi import APIRouter, Depends
from services.admin import require_admin
from services.context import fetch_usgs_well
from utils.counties import AR_COUNTIES

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

CACHE_KEY = "admin:aquifer_stress_all"
CACHE_TTL = 86400  # 24h


@router.get("/aquifer-stress")
async def aquifer_stress(user: dict = Depends(require_admin)):
    from services.cache import cache_get, cache_set
    cached = cache_get(CACHE_KEY)
    if cached:
        return {"data": cached}

    fips_list = list(AR_COUNTIES.keys())
    wells = await asyncio.gather(*[fetch_usgs_well(f) for f in fips_list], return_exceptions=True)

    result = {}
    for fips, well in zip(fips_list, wells):
        if isinstance(well, Exception) or well is None:
            result[fips] = "normal"
        else:
            result[fips] = well.get("stress_level", "normal")

    cache_set(CACHE_KEY, result, ttl=CACHE_TTL)
    return {"data": result}
```

Register in `backend/main.py`:
```python
from routers.admin_aquifer import router as admin_aquifer_router
app.include_router(admin_aquifer_router, prefix="/api/v1")
```

---

### `scripts/nightly_alerts.py` (modified)

Select `rice_fields` in the farmer query. After existing GDD loop, add AWD check:

```python
from services.awd_scheduler import compute_awd_stage
from services.context import fetch_ssurgo, fetch_usgs_well
from datetime import date

AWD_DEDUP_TTL = 5 * 24 * 60 * 60  # 5 days

async def run_awd_alerts(farmers, supabase, redis) -> int:
    fired = 0
    for farmer in farmers:
        if "rice" not in (farmer.get("primary_crops") or []):
            continue
        rice_fields = farmer.get("rice_fields") or []
        if not rice_fields:
            continue

        fips = farmer["county_fips"]
        soil = await fetch_ssurgo(fips)
        drainage = (soil or {}).get("drainage_class") or "default"
        usgs = await fetch_usgs_well(fips)
        stress = (usgs or {}).get("stress_level", "normal")
        well_m = (usgs or {}).get("current_depth_m")

        for field in rice_fields:
            try:
                last_flood = date.fromisoformat(field["last_flood_date"])
            except (KeyError, ValueError):
                continue

            result = compute_awd_stage(
                field_name=field["field_name"],
                last_flood_date=last_flood,
                drainage_class=drainage,
                current_well_m=well_m,
                aquifer_stress_level=stress,
            )
            if result.days_to_threshold > 2:
                continue

            slug = field["field_name"].lower().replace(" ", "_")[:20]
            redis_key = f"alert:{farmer['id']}:awd_refood:{slug}"
            if redis is not None:
                try:
                    if redis.exists(redis_key):
                        continue
                except Exception:
                    pass

            days = result.days_to_threshold
            name = field["field_name"]
            row = {
                "farmer_id": farmer["id"],
                "pest": "awd_refood",
                "county_fips": fips,
                "message_en": (
                    f"Rice field '{name}': AWD re-flood threshold in {days} day(s). "
                    "Re-flood soon. See UA Extension MP192."
                ),
                "message_es": (
                    f"Arrozal '{name}': umbral AWD en {days} día(s). "
                    "Inunde pronto. Ver MP192."
                ),
            }
            try:
                supabase.table("alerts").insert(row).execute()
            except Exception:
                logger.exception("AWD alert insert failed farmer=%s field=%s", farmer["id"], name)
                continue

            if redis is not None:
                try:
                    redis.set(redis_key, "1", ex=AWD_DEDUP_TTL)
                except Exception:
                    pass
            fired += 1

    return fired
```

Update `main()` to select `rice_fields` and call `run_awd_alerts`.

---

### Frontend: `RegisterForm.jsx` (modified)

Dynamic `TOTAL_STEPS`: `form.primary_crops.includes('rice') ? 4 : 3`.

The existing `handleNext` / step logic uses `TOTAL_STEPS` as the ceiling — this continues working once it's computed dynamically. The existing submit guard only validates steps 1 and 2, so step 4 requires no changes there.

Step 4 UI renders a list of rice fields. Initial state: `rice_fields: []` in form. Farmer can add up to 5 fields or skip entirely.

Each field row:
```jsx
{
  field_name: '',           // required, text input
  acres: '',                // optional, number input
  last_flood_date: '',      // required, date input (type="date")
  irrigation_method: 'continuous flood',  // select
}
```

"Add field" button appends a blank entry. "Remove" button on each row removes it.
Validation: if any field row exists, `field_name` and `last_flood_date` must be non-empty.

`handleSubmit` sends `rice_fields` alongside existing form data.

Step 4 i18n strings needed in `i18n.js`:
```js
// EN
wizardStep4Title: 'Rice Fields',
wizardStep4Heading: 'Rice field details (optional)',
riceFieldsHelp: 'Add your rice fields to get AWD irrigation timing in your answers.',
addField: 'Add field',
removeField: 'Remove',
fieldName: 'Field name',
fieldAcres: 'Acres (optional)',
lastFloodDate: 'Last flood date',
irrigationMethod: 'Irrigation method',
irrigationMethodOptions: {
  'continuous flood': 'Continuous flood',
  'intermittent': 'Intermittent',
  'awd': 'AWD',
},
skipStep: 'Skip',

// ES
wizardStep4Title: 'Arrozales',
wizardStep4Heading: 'Detalles de arrozales (opcional)',
riceFieldsHelp: 'Agrega tus arrozales para obtener recomendaciones AWD en tus respuestas.',
addField: 'Agregar campo',
removeField: 'Eliminar',
fieldName: 'Nombre del campo',
fieldAcres: 'Acres (opcional)',
lastFloodDate: 'Última fecha de inundación',
irrigationMethod: 'Método de riego',
skipStep: 'Omitir',
```

---

### Frontend: `ARCountyMap.jsx` (modified)

Add third `dataLayer` value: `'aquifer'`. Add `aquiferData` prop (`{fips: stress_level}`).

Aquifer color function:
```js
function aquiferColor(stress) {
  if (stress === 'critical') return '#EF4444'   // red-500
  if (stress === 'stressed') return '#F59E0B'   // amber-500
  return '#10B981'                              // emerald-500 (normal)
}
```

Toggle button in admin dashboard alongside existing Drift toggle.
`AdminDashboard.jsx` fetches `/api/v1/admin/aquifer-stress` when aquifer toggle is active (lazy — not on page load).

---

### `backend/tests/test_awd_scheduler.py` (new)

```python
from datetime import date, timedelta
from services.awd_scheduler import compute_awd_stage, format_awd_context

def today(): return date.today()

def test_re_flood_now_when_past_threshold():
    # 30 days elapsed at 0.8 cm/day = 24cm > 15cm threshold
    last_flood = today() - timedelta(days=30)
    r = compute_awd_stage("f1", last_flood, "somewhat poorly drained", None)
    assert r.days_to_threshold == 0
    assert r.recommendation == "re-flood now"

def test_prepare_to_reflood_at_2_days():
    # days needed to hit 15cm at 0.8 cm/day = 18.75 days
    # after 17 days: 13.6cm, 1.4cm left = ceil(1.4/0.8) = 2 days
    last_flood = today() - timedelta(days=17)
    r = compute_awd_stage("f1", last_flood, "somewhat poorly drained", None)
    assert r.days_to_threshold <= 2
    assert r.recommendation == "prepare to re-flood"

def test_maintain_flood_early_in_cycle():
    last_flood = today() - timedelta(days=3)
    r = compute_awd_stage("f1", last_flood, "somewhat poorly drained", None)
    assert r.days_to_threshold > 2
    assert r.recommendation == "maintain flood"

def test_well_drained_faster_dry_rate():
    # 0-day elapsed → same day
    last_flood = today() - timedelta(days=9)
    r = compute_awd_stage("f1", last_flood, "well drained", None)
    # 9 × 1.5 = 13.5cm < 15cm → ceil((15-13.5)/1.5) = ceil(1.0) = 1 → prepare
    assert r.recommendation in ("prepare to re-flood", "re-flood now")

def test_unknown_drainage_class_uses_default():
    last_flood = today() - timedelta(days=1)
    r = compute_awd_stage("f1", last_flood, "bogus class", None)
    assert r.recommendation == "maintain flood"

def test_aquifer_stress_passes_through():
    last_flood = today()
    r = compute_awd_stage("f1", last_flood, "default", 5.2, "critical")
    assert r.aquifer_stress_level == "critical"
    assert r.well_depth_m == 5.2

def test_format_awd_context_includes_recommendation():
    last_flood = today() - timedelta(days=30)
    r = compute_awd_stage("North 40", last_flood, "somewhat poorly drained", None)
    ctx = format_awd_context([r])
    assert "North 40" in ctx
    assert "re-flood now" in ctx
```

---

## Success Metrics

| Metric | Target |
|---|---|
| AWD alerts fired + farmer responses | ≥ 10 |
| Rice fields registered by pilot farmers | ≥ 5 fields |
| USGS well fetch success rate | ≥ 80% of AR Delta counties |

---

## New Files Summary

| File | Purpose |
|---|---|
| `backend/data/awd_thresholds.json` | Dry rate per drainage class |
| `backend/services/awd_scheduler.py` | AWD stage calculator |
| `backend/supabase/migrations/007_rice_fields.sql` | `rice_fields` jsonb column |
| `backend/routers/admin_aquifer.py` | Admin aquifer stress endpoint |
| `backend/tests/test_awd_scheduler.py` | Unit tests (7 tests) |

## Modified Files Summary

| File | Change |
|---|---|
| `backend/services/context.py` | Add `fetch_usgs_well(fips)` |
| `backend/models/user.py` | Add `RiceField`, `rice_fields` on 3 models |
| `backend/services/user.py` | `create_profile` + `update_profile` accept `rice_fields` |
| `backend/routers/auth.py` | Pass `rice_fields` to `create_profile` |
| `backend/services/rag.py` | AWD context injection for rice queries |
| `backend/utils/prompt.py` | `awd_context` param on `build_system_prompt` |
| `backend/routers/query.py` | Pass `rice_fields` from profile to `run_rag_query` |
| `backend/routers/main.py` | Register `admin_aquifer_router` |
| `scripts/nightly_alerts.py` | Add AWD alert loop |
| `frontend/src/components/auth/RegisterForm.jsx` | Conditional step 4 |
| `frontend/src/constants/i18n.js` | Step 4 strings |
| `frontend/src/components/admin/ARCountyMap.jsx` | Aquifer stress toggle |
