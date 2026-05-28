# F5 AWD Irrigation Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-field AWD irrigation stage recommendations for rice farmers — injected into RAG context, fired as proactive alerts, and shown as an aquifer stress layer on the admin choropleth.

**Architecture:** Static thresholds JSON drives a `compute_awd_stage()` service that takes last-flood-date + SSURGO drainage class + optional USGS well depth and returns days-to-threshold + recommendation. The result is injected into the LLM system prompt for rice queries, checked nightly for alert firing, and surfaced on a new admin map toggle.

**Tech Stack:** FastAPI, Pydantic, httpx (async), Upstash Redis cache, React 19 + Tailwind, Vitest. No new packages required.

---

## File Map

| Action | File | What changes |
|--------|------|-------------|
| Create | `backend/data/awd_thresholds.json` | Dry rate per drainage class |
| Create | `backend/supabase/migrations/007_rice_fields.sql` | `rice_fields` jsonb column |
| Create | `backend/services/awd_scheduler.py` | AWD stage calculator |
| Create | `backend/tests/test_awd_scheduler.py` | Unit tests (7 tests) |
| Create | `backend/routers/admin_aquifer.py` | GET /admin/aquifer-stress |
| Modify | `backend/services/context.py` | Add `fetch_usgs_well(fips)` |
| Modify | `backend/models/user.py` | Add `RiceField`, `rice_fields` on 3 models |
| Modify | `backend/services/user.py` | `create_profile` + `update_profile` accept `rice_fields` |
| Modify | `backend/routers/auth.py` | Pass `rice_fields` to `create_profile` |
| Modify | `backend/utils/prompt.py` | Add `awd_context` param |
| Modify | `backend/services/rag.py` | Compute + inject AWD context for rice queries |
| Modify | `backend/routers/query.py` | Pass `rice_fields` from profile |
| Modify | `backend/main.py` | Register `admin_aquifer_router` |
| Modify | `scripts/nightly_alerts.py` | AWD alert loop |
| Modify | `frontend/src/components/auth/RegisterForm.jsx` | Conditional step 4 |
| Modify | `frontend/src/constants/i18n.js` | Step 4 strings |
| Modify | `frontend/src/components/admin/ARCountyMap.jsx` | Aquifer stress toggle |
| Modify | `frontend/src/pages/AdminDashboardPage.jsx` | Fetch + pass aquifer data |

---

## Task 1: Static data files

**Files:**
- Create: `backend/data/awd_thresholds.json`
- Create: `backend/supabase/migrations/007_rice_fields.sql`

- [ ] **Step 1: Create `awd_thresholds.json`**

```json
{
  "poorly drained":           {"dry_rate_cm_per_day": 0.5, "threshold_cm": 15},
  "somewhat poorly drained":  {"dry_rate_cm_per_day": 0.8, "threshold_cm": 15},
  "moderately well drained":  {"dry_rate_cm_per_day": 1.2, "threshold_cm": 15},
  "well drained":             {"dry_rate_cm_per_day": 1.5, "threshold_cm": 15},
  "default":                  {"dry_rate_cm_per_day": 0.8, "threshold_cm": 15}
}
```

Save to `backend/data/awd_thresholds.json`.

- [ ] **Step 2: Create migration 007**

```sql
-- backend/supabase/migrations/007_rice_fields.sql
ALTER TABLE farmer_profiles
  ADD COLUMN IF NOT EXISTS rice_fields jsonb NOT NULL DEFAULT '[]'::jsonb;
```

Save to `backend/supabase/migrations/007_rice_fields.sql`.

- [ ] **Step 3: Commit**

```bash
git add backend/data/awd_thresholds.json backend/supabase/migrations/007_rice_fields.sql
git commit -m "feat: add AWD thresholds data and migration 007"
```

---

## Task 2: AWD scheduler service + unit tests

**Files:**
- Create: `backend/services/awd_scheduler.py`
- Create: `backend/tests/test_awd_scheduler.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_awd_scheduler.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import tempfile
import os
from datetime import date, timedelta


def _write_thresholds():
    data = {
        "poorly drained":          {"dry_rate_cm_per_day": 0.5, "threshold_cm": 15},
        "somewhat poorly drained": {"dry_rate_cm_per_day": 0.8, "threshold_cm": 15},
        "moderately well drained": {"dry_rate_cm_per_day": 1.2, "threshold_cm": 15},
        "well drained":            {"dry_rate_cm_per_day": 1.5, "threshold_cm": 15},
        "default":                 {"dry_rate_cm_per_day": 0.8, "threshold_cm": 15},
    }
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, tmp)
    tmp.close()
    return tmp.name


def _make_scheduler(path):
    import importlib
    import services.awd_scheduler as mod
    mod._thresholds = None  # reset cache
    mod._THRESHOLDS_PATH = Path(path)
    return mod


def test_re_flood_now_when_past_threshold():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        last_flood = date.today() - timedelta(days=30)
        # 30 * 0.8 = 24cm > 15cm threshold
        r = mod.compute_awd_stage("f1", last_flood, "somewhat poorly drained", None)
        assert r.days_to_threshold == 0
        assert r.recommendation == "re-flood now"
    finally:
        os.unlink(path)


def test_prepare_to_reflood_within_2_days():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        # At 0.8 cm/day, threshold at 15cm = 18.75 days
        # 17 days elapsed: 13.6 cm depth, 1.4 cm left = ceil(1.4/0.8) = 2 days
        last_flood = date.today() - timedelta(days=17)
        r = mod.compute_awd_stage("f1", last_flood, "somewhat poorly drained", None)
        assert r.days_to_threshold <= 2
        assert r.recommendation == "prepare to re-flood"
    finally:
        os.unlink(path)


def test_maintain_flood_early_in_cycle():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        last_flood = date.today() - timedelta(days=3)
        r = mod.compute_awd_stage("f1", last_flood, "somewhat poorly drained", None)
        assert r.days_to_threshold > 2
        assert r.recommendation == "maintain flood"
    finally:
        os.unlink(path)


def test_well_drained_faster_dry_rate():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        # 9 days * 1.5 cm/day = 13.5 cm depth; ceil((15-13.5)/1.5) = 1 day → prepare
        last_flood = date.today() - timedelta(days=9)
        r = mod.compute_awd_stage("f1", last_flood, "well drained", None)
        assert r.recommendation in ("prepare to re-flood", "re-flood now")
    finally:
        os.unlink(path)


def test_unknown_drainage_class_uses_default():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        last_flood = date.today() - timedelta(days=1)
        r = mod.compute_awd_stage("f1", last_flood, "bogus drainage class", None)
        assert r.recommendation == "maintain flood"
    finally:
        os.unlink(path)


def test_aquifer_stress_passes_through():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        last_flood = date.today()
        r = mod.compute_awd_stage("North 40", last_flood, "default", 5.2, "critical")
        assert r.aquifer_stress_level == "critical"
        assert r.well_depth_m == 5.2
        assert r.field_name == "North 40"
    finally:
        os.unlink(path)


def test_format_awd_context_contains_field_and_recommendation():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        last_flood = date.today() - timedelta(days=30)
        r = mod.compute_awd_stage("North 40", last_flood, "somewhat poorly drained", None)
        ctx = mod.format_awd_context([r])
        assert "North 40" in ctx
        assert "re-flood now" in ctx
        assert "[AWD IRRIGATION STATUS]" in ctx
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_awd_scheduler.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `awd_scheduler` doesn't exist yet.

- [ ] **Step 3: Implement `awd_scheduler.py`**

Create `backend/services/awd_scheduler.py`:

```python
"""AWD irrigation stage calculator — per field, per drainage class."""
import json
import math
from datetime import date
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
    well_depth_m: Optional[float] = None


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
        rec: Literal["maintain flood", "prepare to re-flood", "re-flood now"] = "re-flood now"
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
        well_str = f" USGS well depth: {r.well_depth_m:.2f}m." if r.well_depth_m is not None else ""
        lines.append(
            f"Field '{r.field_name}': {r.recommendation}. "
            f"Days to re-flood threshold: {r.days_to_threshold}. "
            f"Aquifer stress: {r.aquifer_stress_level}.{well_str}"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_awd_scheduler.py -v
```

Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/awd_scheduler.py backend/tests/test_awd_scheduler.py
git commit -m "feat: add AWD scheduler service with unit tests"
```

---

## Task 3: USGS well fetch in context.py

**Files:**
- Modify: `backend/services/context.py`

- [ ] **Step 1: Add `fetch_usgs_well` to `context.py`**

Open `backend/services/context.py`. Add these imports at the top (after existing imports):

```python
from datetime import date as _date
```

Add these two constants after the existing `SSURGO_QUERY` block:

```python
USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
USGS_STAT_URL = "https://waterservices.usgs.gov/nwis/stat/"
```

Add this function after `get_context()`:

```python
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
            # dateTime format from USGS stats API: "1900-MM-DD"
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
```

- [ ] **Step 2: Verify no import errors**

```bash
cd backend && python -c "from services.context import fetch_usgs_well; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/services/context.py
git commit -m "feat: add fetch_usgs_well to context service"
```

---

## Task 4: User models — RiceField + rice_fields

**Files:**
- Modify: `backend/models/user.py`

- [ ] **Step 1: Write failing test**

Add this test to `backend/tests/test_awd_scheduler.py` (append at bottom):

```python
def test_rice_field_model_validates():
    import importlib
    mod = importlib.import_module("models.user")
    from datetime import date as d
    rf = mod.RiceField(field_name="South 20", last_flood_date=d(2026, 5, 1))
    assert rf.irrigation_method == "continuous flood"
    assert rf.acres is None


def test_register_request_accepts_rice_fields():
    import importlib
    mod = importlib.import_module("models.user")
    from datetime import date as d
    req = mod.RegisterRequest(
        email="t@test.com",
        password="testpass1",
        full_name="Test",
        county_fips="05001",
        rice_fields=[{"field_name": "f1", "last_flood_date": "2026-05-01", "acres": None, "irrigation_method": "awd"}],
    )
    assert len(req.rice_fields) == 1
    assert req.rice_fields[0].field_name == "f1"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_awd_scheduler.py::test_rice_field_model_validates tests/test_awd_scheduler.py::test_register_request_accepts_rice_fields -v
```

Expected: FAIL — `RiceField` not defined.

- [ ] **Step 3: Add `RiceField` and `rice_fields` to `models/user.py`**

Open `backend/models/user.py`. Make these three changes:

**A. Update imports** (top of file — add `date` and `Optional` if not already there):

```python
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Literal, Optional
from datetime import date
from utils.counties import AR_COUNTIES
```

**B. Add `RiceField` model** (insert before `RegisterRequest`):

```python
class RiceField(BaseModel):
    field_name: str
    acres: Optional[float] = None
    last_flood_date: date
    irrigation_method: Literal["continuous flood", "intermittent", "awd"] = "continuous flood"
```

**C. Add `rice_fields` to `RegisterRequest`** (after the existing `language` field):

```python
rice_fields: list[RiceField] = Field(default_factory=list)
```

**D. Add `rice_fields` to `FarmerProfile`** (after `last_active`):

```python
rice_fields: list[dict] = Field(default_factory=list)
```

**E. Add `rice_fields` to `UpdateProfileRequest`** (after `language`):

```python
rice_fields: Optional[list[RiceField]] = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_awd_scheduler.py::test_rice_field_model_validates tests/test_awd_scheduler.py::test_register_request_accepts_rice_fields -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/models/user.py backend/tests/test_awd_scheduler.py
git commit -m "feat: add RiceField model and rice_fields to user models"
```

---

## Task 5: User service + auth router accept rice_fields

**Files:**
- Modify: `backend/services/user.py`
- Modify: `backend/routers/auth.py`

- [ ] **Step 1: Update `create_profile` in `user.py`**

Open `backend/services/user.py`. Modify `create_profile` to accept and persist `rice_fields`:

```python
def create_profile(
    user_id: str,
    full_name: str,
    county_fips: str,
    primary_crops: list[str],
    language: str,
    rice_fields: list[dict] | None = None,
) -> dict:
    county_name = AR_COUNTIES[county_fips][0]
    client = _get_service_client()
    result = client.table("farmer_profiles").insert({
        "id": user_id,
        "full_name": full_name,
        "county_fips": county_fips,
        "county_name": county_name,
        "primary_crops": primary_crops,
        "language": language,
        "rice_fields": rice_fields or [],
    }).execute()
    if not result.data:
        raise RuntimeError(f"Profile insert returned no data for user {user_id}")
    return result.data[0]
```

- [ ] **Step 2: Update `update_profile` in `user.py`**

In `update_profile`, before the client call, add handling for `rice_fields` serialization. Find the existing `if "county_fips" in updates` block and add after it:

```python
if "rice_fields" in updates and updates["rice_fields"] is not None:
    updates["rice_fields"] = [
        f.model_dump() if hasattr(f, "model_dump") else f
        for f in updates["rice_fields"]
    ]
```

- [ ] **Step 3: Update `auth.py` to pass rice_fields**

Open `backend/routers/auth.py`. Change the `create_profile` call to:

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

- [ ] **Step 4: Verify no import errors**

```bash
cd backend && python -c "from services.user import create_profile; from routers.auth import register; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/services/user.py backend/routers/auth.py
git commit -m "feat: persist rice_fields through register and update_profile"
```

---

## Task 6: RAG context injection

**Files:**
- Modify: `backend/utils/prompt.py`
- Modify: `backend/services/rag.py`
- Modify: `backend/routers/query.py`

- [ ] **Step 1: Add `awd_context` param to `build_system_prompt`**

Open `backend/utils/prompt.py`. Change the function signature to:

```python
def build_system_prompt(
    *,
    soil_context: dict,
    weather_context: dict,
    retrieved_docs: list[Document],
    session_history: list[dict],
    language: str,
    is_safety_critical: bool,
    county_name: str,
    awd_context: str | None = None,
) -> str:
```

In the function body, after the local conditions block (after the `parts.append("")` that closes the local conditions section), insert:

```python
    # AWD irrigation context (rice queries only)
    if awd_context:
        parts.append(awd_context)
        parts.append("")
```

The exact insertion point is after this existing block:
```python
    if soil_context.get("available") or weather_context.get("available"):
        parts.append(f"[LOCAL CONDITIONS — {county_name.upper()}, ARKANSAS]")
        if soil_context.get("available"):
            parts.append("SOIL: " + json.dumps(soil_context, indent=None))
        if weather_context.get("available"):
            parts.append("WEATHER: " + json.dumps(weather_context, indent=None))
        parts.append("")
```

Add the AWD block immediately after that closing `parts.append("")`.

- [ ] **Step 2: Update `run_rag_query` in `rag.py`**

Open `backend/services/rag.py`. 

**A. Add import at top** (after existing imports):

```python
from datetime import date as _date
```

**B. Update `run_rag_query` signature** to add `rice_fields` param:

```python
async def run_rag_query(
    *,
    message: str,
    county_fips: str,
    language: str,
    category: str,
    session_history: list[dict],
    rice_fields: list[dict] | None = None,
) -> tuple[AdvisoryResponse, list[dict]]:
```

**C. Inject AWD context** — after the line `ctx = await context_task` and before `county_info = get_county_info(county_fips)`, add:

```python
    # AWD context injection for rice queries with registered fields
    awd_context: str | None = None
    if rice_fields and category == "IN_SCOPE_RICE":
        from services import awd_scheduler
        from services.context import fetch_usgs_well
        usgs = await fetch_usgs_well(county_fips)
        stress = (usgs or {}).get("stress_level", "normal")
        well_m = (usgs or {}).get("current_depth_m")
        drainage = soil.get("drainage_class") or "default"

        awd_results = [
            awd_scheduler.compute_awd_stage(
                field_name=f["field_name"],
                last_flood_date=_date.fromisoformat(f["last_flood_date"]),
                drainage_class=drainage,
                current_well_m=well_m,
                aquifer_stress_level=stress,
            )
            for f in rice_fields[:3]
            if f.get("field_name") and f.get("last_flood_date")
        ]
        if awd_results:
            awd_context = awd_scheduler.format_awd_context(awd_results)
```

**D. Pass `awd_context` to `build_system_prompt`** — update the existing call:

```python
    system_prompt = build_system_prompt(
        soil_context=soil,
        weather_context=weather,
        retrieved_docs=docs,
        session_history=session_history,
        language=language,
        is_safety_critical=(category == "SAFETY_CRITICAL"),
        county_name=county_name,
        awd_context=awd_context,
    )
```

- [ ] **Step 3: Pass `rice_fields` from `query.py`**

Open `backend/routers/query.py`. After the existing line:

```python
county_fips = (profile or {}).get("county_fips") or "05055"
```

Add:

```python
rice_fields = (profile or {}).get("rice_fields") or []
```

In `event_stream()`, update the `run_rag_query` call to pass `rice_fields`:

```python
result, retrieved_chunks = await run_rag_query(
    message=req.message,
    county_fips=county_fips,
    language=language,
    category=category,
    session_history=req.session_history,
    rice_fields=rice_fields,
)
```

- [ ] **Step 4: Verify no import errors**

```bash
cd backend && python -c "from utils.prompt import build_system_prompt; from services.rag import run_rag_query; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Run existing RAG tests to confirm no regressions**

```bash
cd backend && pytest tests/ -v --ignore=tests/test_citation_guard_v2.py -x
```

Expected: All tests PASS (test_citation_guard_v2.py excluded — requires NLI model on disk).

- [ ] **Step 6: Commit**

```bash
git add backend/utils/prompt.py backend/services/rag.py backend/routers/query.py
git commit -m "feat: inject AWD context into RAG system prompt for rice queries"
```

---

## Task 7: Nightly AWD alerts

**Files:**
- Modify: `scripts/nightly_alerts.py`

- [ ] **Step 1: Update `nightly_alerts.py`**

Replace the full content of `scripts/nightly_alerts.py` with:

```python
# scripts/nightly_alerts.py
"""Nightly alert orchestrator — run via GitHub Actions."""
import asyncio
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from services.alert_engine import AlertEngine
from services.awd_scheduler import compute_awd_stage
from services.context import fetch_ssurgo, fetch_usgs_well
from services.user import _get_service_client
from services.cache import _get_client as _get_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

AWD_DEDUP_TTL = 5 * 24 * 60 * 60  # 5 days


async def run_awd_alerts(farmers: list[dict], supabase) -> int:
    redis = _get_redis()
    fired = 0

    for farmer in farmers:
        if "rice" not in (farmer.get("primary_crops") or []):
            continue
        rice_fields = farmer.get("rice_fields") or []
        if not rice_fields:
            continue

        fips = farmer.get("county_fips") or ""
        if not fips:
            continue

        soil = await fetch_ssurgo(fips)
        drainage = (soil or {}).get("drainage_class") or "default"
        usgs = await fetch_usgs_well(fips)
        stress = (usgs or {}).get("stress_level", "normal")
        well_m = (usgs or {}).get("current_depth_m")

        for field in rice_fields:
            last_flood_str = field.get("last_flood_date")
            field_name = field.get("field_name") or ""
            if not last_flood_str or not field_name:
                continue

            try:
                last_flood = date.fromisoformat(last_flood_str)
            except ValueError:
                continue

            result = compute_awd_stage(
                field_name=field_name,
                last_flood_date=last_flood,
                drainage_class=drainage,
                current_well_m=well_m,
                aquifer_stress_level=stress,
            )
            if result.days_to_threshold > 2:
                continue

            slug = field_name.lower().replace(" ", "_")[:20]
            redis_key = f"alert:{farmer['id']}:awd_refood:{slug}"
            if redis is not None:
                try:
                    if redis.exists(redis_key):
                        continue
                except Exception:
                    logger.warning("Redis exists check failed key=%s", redis_key)

            days = result.days_to_threshold
            row = {
                "farmer_id": farmer["id"],
                "pest": "awd_refood",
                "county_fips": fips,
                "message_en": (
                    f"Rice field '{field_name}': AWD re-flood threshold in {days} day(s). "
                    "Re-flood soon. See UA Extension MP192."
                ),
                "message_es": (
                    f"Arrozal '{field_name}': umbral AWD en {days} dia(s). "
                    "Inunde pronto. Ver MP192."
                ),
            }
            try:
                supabase.table("alerts").insert(row).execute()
            except Exception:
                logger.exception(
                    "AWD alert insert failed farmer=%s field=%s", farmer["id"], field_name
                )
                continue

            if redis is not None:
                try:
                    redis.set(redis_key, "1", ex=AWD_DEDUP_TTL)
                except Exception:
                    logger.warning("Redis set failed key=%s", redis_key)

            fired += 1
            logger.info(
                "AWD alert fired farmer=%s field=%s days=%d", farmer["id"], field_name, days
            )

    return fired


async def main() -> None:
    supabase = _get_service_client()
    cutoff = (date.today() - timedelta(days=30)).isoformat()

    result = (
        supabase.table("farmer_profiles")
        .select("id, county_fips, primary_crops, language, rice_fields")
        .gte("last_active", cutoff)
        .execute()
    )
    farmers = result.data or []
    logger.info("Processing %d active farmers (last_active > %s)", len(farmers), cutoff)

    engine = AlertEngine()
    total_fired = 0

    for farmer in farmers:
        county = farmer.get("county_fips") or ""
        crops = farmer.get("primary_crops") or []
        if not county or not crops:
            continue
        try:
            fired = await engine.run_for_farmer(
                farmer_id=farmer["id"],
                county_fips=county,
                primary_crops=crops,
                language=farmer.get("language", "en"),
            )
            total_fired += len(fired)
        except Exception:
            logger.exception("GDD alert run failed for farmer=%s", farmer["id"])

    awd_fired = await run_awd_alerts(farmers, supabase)
    total_fired += awd_fired

    logger.info(
        "Nightly alerts complete. GDD alerts: %d, AWD alerts: %d",
        total_fired - awd_fired,
        awd_fired,
    )


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify syntax**

```bash
python -c "import ast; ast.parse(open('scripts/nightly_alerts.py').read()); print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add scripts/nightly_alerts.py
git commit -m "feat: add AWD alert loop to nightly_alerts.py"
```

---

## Task 8: Admin aquifer stress endpoint

**Files:**
- Create: `backend/routers/admin_aquifer.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Create `admin_aquifer.py`**

Create `backend/routers/admin_aquifer.py`:

```python
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
```

- [ ] **Step 2: Register router in `main.py`**

Open `backend/main.py`. Add import after existing router imports:

```python
from routers.admin_aquifer import router as admin_aquifer_router
```

Add include after existing `include_router` calls:

```python
app.include_router(admin_aquifer_router, prefix="/api/v1")
```

- [ ] **Step 3: Verify app starts**

```bash
cd backend && python -c "from main import app; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/routers/admin_aquifer.py backend/main.py
git commit -m "feat: add admin aquifer stress endpoint"
```

---

## Task 9: RegisterForm step 4 (frontend)

**Files:**
- Modify: `frontend/src/constants/i18n.js`
- Modify: `frontend/src/components/auth/RegisterForm.jsx`

- [ ] **Step 1: Add step 4 strings to `i18n.js`**

Open `frontend/src/constants/i18n.js`.

In the `en` object, add these keys before the closing `},` of the `en` block (after `registerSubtitle`):

```js
    wizardStep4Title: 'Rice Fields',
    wizardStep4Heading: 'Rice field details (optional)',
    riceFieldsHelp: 'Add your rice fields to get AWD irrigation timing in your answers.',
    addField: 'Add field',
    removeField: 'Remove',
    fieldName: 'Field name',
    fieldAcres: 'Acres (optional)',
    lastFloodDate: 'Last flood date',
    irrigationMethod: 'Irrigation method',
    skipStep: 'Skip',
    errFieldNameRequired: 'Field name is required.',
    errLastFloodDateRequired: 'Last flood date is required.',
```

In the `es` object, add the same keys (after `registerSubtitle`):

```js
    wizardStep4Title: 'Arrozales',
    wizardStep4Heading: 'Detalles de arrozales (opcional)',
    riceFieldsHelp: 'Agrega tus arrozales para obtener recomendaciones AWD en tus respuestas.',
    addField: 'Agregar campo',
    removeField: 'Eliminar',
    fieldName: 'Nombre del campo',
    fieldAcres: 'Acres (opcional)',
    lastFloodDate: 'Ultima fecha de inundacion',
    irrigationMethod: 'Metodo de riego',
    skipStep: 'Omitir',
    errFieldNameRequired: 'El nombre del campo es requerido.',
    errLastFloodDateRequired: 'La fecha de inundacion es requerida.',
```

- [ ] **Step 2: Update `RegisterForm.jsx`**

Open `frontend/src/components/auth/RegisterForm.jsx`.

**A. Remove `const TOTAL_STEPS = 3`** (line 12). Replace with a comment noting it's now dynamic:

```js
// TOTAL_STEPS computed dynamically below — 4 for rice farmers, 3 otherwise
```

**B. Update `getRegistrationStepErrors`** — add step 4 validation after the step 2 block:

```js
  if (step === 4) {
    form.rice_fields.forEach((field, i) => {
      if (!field.field_name.trim()) errs[`rice_field_${i}_name`] = t.errFieldNameRequired
      if (!field.last_flood_date) errs[`rice_field_${i}_date`] = t.errLastFloodDateRequired
    })
  }
```

**C. Add `rice_fields: []` to initial form state**:

```js
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    county_fips: '',
    primary_crops: [],
    language: 'en',
    rice_fields: [],
  })
```

**D. Add `totalSteps` computed value** after the `[form, setForm]` line:

```js
  const totalSteps = form.primary_crops.includes('rice') ? 4 : 3
```

**E. Replace all occurrences of `TOTAL_STEPS`** with `totalSteps` throughout the component. There are 3 occurrences:
- `setStep((s) => Math.min(s + 1, TOTAL_STEPS))` → `setStep((s) => Math.min(s + 1, totalSteps))`
- `{t.wizardStep} {step} {t.wizardOf} {TOTAL_STEPS}` → `{t.wizardStep} {step} {t.wizardOf} {totalSteps}`
- `{step < TOTAL_STEPS && (` → `{step < totalSteps && (`

**F. Update `titles` and `headings` arrays** to be dynamic:

```js
  const titles = [
    t.wizardStep1Title,
    t.wizardStep2Title,
    t.wizardStep3Title,
    ...(totalSteps === 4 ? [t.wizardStep4Title] : []),
  ]
  const headings = [
    t.wizardStep1Heading,
    t.wizardStep2Heading,
    t.wizardStep3Heading,
    ...(totalSteps === 4 ? [t.wizardStep4Heading] : []),
  ]
```

**G. Add step 4 content** — after the closing `}` of `{step === 3 && (...)})`, add:

```jsx
      {step === 4 && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-white/70 dark:text-hc-fg">{t.riceFieldsHelp}</p>

          {form.rice_fields.map((field, i) => (
            <div key={i} className="flex flex-col gap-2 p-3 rounded-xl border border-white/20 bg-white/[0.05]">
              <GlassInput
                id={`field_name_${i}`}
                label={t.fieldName}
                value={field.field_name}
                onChange={(e) => {
                  const updated = [...form.rice_fields]
                  updated[i] = { ...updated[i], field_name: e.target.value }
                  setForm((f) => ({ ...f, rice_fields: updated }))
                }}
                error={fieldErrors[`rice_field_${i}_name`]}
              />
              <GlassInput
                id={`last_flood_date_${i}`}
                label={t.lastFloodDate}
                type="date"
                value={field.last_flood_date}
                onChange={(e) => {
                  const updated = [...form.rice_fields]
                  updated[i] = { ...updated[i], last_flood_date: e.target.value }
                  setForm((f) => ({ ...f, rice_fields: updated }))
                }}
                error={fieldErrors[`rice_field_${i}_date`]}
              />
              <GlassInput
                id={`acres_${i}`}
                label={t.fieldAcres}
                type="number"
                value={field.acres}
                onChange={(e) => {
                  const updated = [...form.rice_fields]
                  updated[i] = { ...updated[i], acres: e.target.value }
                  setForm((f) => ({ ...f, rice_fields: updated }))
                }}
              />
              <div className="flex flex-col gap-1">
                <label htmlFor={`irrigation_method_${i}`} className="text-sm font-medium text-white/80 dark:text-hc-fg">
                  {t.irrigationMethod}
                </label>
                <select
                  id={`irrigation_method_${i}`}
                  value={field.irrigation_method}
                  onChange={(e) => {
                    const updated = [...form.rice_fields]
                    updated[i] = { ...updated[i], irrigation_method: e.target.value }
                    setForm((f) => ({ ...f, rice_fields: updated }))
                  }}
                  className={`${INPUT_CLS} [&>option]:bg-slate-900 [&>option]:text-white`}
                >
                  <option value="continuous flood">Continuous flood</option>
                  <option value="intermittent">Intermittent</option>
                  <option value="awd">AWD</option>
                </select>
              </div>
              <button
                type="button"
                onClick={() => setForm((f) => ({
                  ...f,
                  rice_fields: f.rice_fields.filter((_, j) => j !== i),
                }))}
                className="text-sm text-red-300 hover:text-red-200 self-start"
              >
                {t.removeField}
              </button>
            </div>
          ))}

          {form.rice_fields.length < 5 && (
            <button
              type="button"
              onClick={() => setForm((f) => ({
                ...f,
                rice_fields: [
                  ...f.rice_fields,
                  { field_name: '', acres: '', last_flood_date: '', irrigation_method: 'continuous flood' },
                ],
              }))}
              className={BTN_GHOST_CLS}
            >
              + {t.addField}
            </button>
          )}
        </div>
      )}
```

**H. Add "Skip" option on step 4** — the existing `{step < totalSteps && ...}` condition already handles the Next button. When on step 4, the submit button shows. That's correct. No extra change needed.

- [ ] **Step 3: Run frontend lint**

```bash
cd frontend && npm run lint
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/constants/i18n.js frontend/src/components/auth/RegisterForm.jsx
git commit -m "feat: add conditional rice fields step to registration wizard"
```

---

## Task 10: ARCountyMap aquifer toggle

**Files:**
- Modify: `frontend/src/components/admin/ARCountyMap.jsx`
- Modify: `frontend/src/pages/AdminDashboardPage.jsx`

- [ ] **Step 1: Update `ARCountyMap.jsx`**

Open `frontend/src/components/admin/ARCountyMap.jsx`.

**A. Add `aquiferColor` function** after `driftColor`:

```js
function aquiferColor(stress) {
  if (stress === 'critical') return '#EF4444'  // red-500
  if (stress === 'stressed') return '#F59E0B'  // amber-500
  return '#10B981'                             // emerald-500
}
```

**B. Update component signature** to accept `aquiferData` prop:

```js
export default function ARCountyMap({ countyData = [], dataLayer = 'queries', driftData = {}, aquiferData = {} }) {
```

**C. Replace the `isDrift` constant** and color logic. Currently:

```js
  const isDrift = dataLayer === 'drift'
```

Replace with:

```js
  const isDrift = dataLayer === 'drift'
  const isAquifer = dataLayer === 'aquifer'
```

**D. Update the `countByFips` / `maxCount` block** — add aquifer branch:

```js
  const countByFips = {}
  let maxCount = 1
  if (isDrift) {
    Object.entries(driftData).forEach(([fips, count]) => {
      countByFips[fips] = count
      if (count > maxCount) maxCount = count
    })
  } else if (!isAquifer) {
    countyData.forEach(({ county_fips, count }) => {
      countByFips[county_fips] = count
      if (count > maxCount) maxCount = count
    })
  }
```

**E. Update the `fill` prop on `<Geography>`** — replace the current ternary:

```js
fill={isDrift ? driftColor(count, maxCount) : countyColor(count, maxCount)}
```

with:

```js
fill={
  isAquifer
    ? aquiferColor(aquiferData[fips] || 'normal')
    : isDrift
      ? driftColor(count, maxCount)
      : countyColor(count, maxCount)
}
```

**F. Update tooltip** — replace the `{tooltip.count} {isDrift ? 'reports' : 'queries'}` span:

```jsx
<span className="text-gray-500 dark:text-hc-fg ml-2">
  {isAquifer
    ? (aquiferData[tooltip?.fips] || 'normal')
    : `${tooltip.count} ${isDrift ? 'reports' : 'queries'}`}
</span>
```

But `tooltip` currently doesn't carry `fips`. Update the `onMouseEnter` handler to also capture fips:

```js
onMouseEnter={() => {
  const name = geo.properties?.name || fips
  setTooltip({ name, count, fips })
}}
```

**G. Update legend** — replace the legend `div`:

```jsx
      <div className="flex items-center gap-2 mt-2 text-xs text-gray-500 dark:text-hc-fg px-1">
        {isAquifer ? (
          <>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full inline-block" style={{background:'#10B981'}} /> Normal</span>
            <span className="flex items-center gap-1 ml-2"><span className="w-3 h-3 rounded-full inline-block" style={{background:'#F59E0B'}} /> Stressed</span>
            <span className="flex items-center gap-1 ml-2"><span className="w-3 h-3 rounded-full inline-block" style={{background:'#EF4444'}} /> Critical</span>
          </>
        ) : (
          <>
            <span>0</span>
            <div
              className="flex-1 h-2 rounded"
              style={{ background: isDrift
                ? 'linear-gradient(to right, #FEF9EE, #E9A228)'
                : 'linear-gradient(to right, #EEF2EF, #2D6A4F)' }}
            />
            <span>{maxCount}</span>
            <span className="ml-1">{isDrift ? 'reports' : 'queries'}</span>
          </>
        )}
      </div>
```

- [ ] **Step 2: Update `AdminDashboardPage.jsx`**

Open `frontend/src/pages/AdminDashboardPage.jsx`.

**A. Add `useEffect` and `useState` for aquifer data** — add `useEffect` to existing `useState` import if not already there:

```js
import { useState, useEffect } from 'react'
```

**B. Add `api` import** — add after existing imports:

```js
import api from '../lib/api'
```

**C. Add aquifer state** — after existing `const [mapLayer, setMapLayer] = useState('queries')`:

```js
  const [aquiferData, setAquiferData] = useState({})
  const [aquiferLoading, setAquiferLoading] = useState(false)
```

**D. Add `useEffect` to fetch aquifer data** — after the `aquiferData` state line:

```js
  useEffect(() => {
    if (mapLayer !== 'aquifer' || Object.keys(aquiferData).length > 0) return
    setAquiferLoading(true)
    api.get('/admin/aquifer-stress')
      .then(res => setAquiferData(res.data.data || {}))
      .catch(() => {})
      .finally(() => setAquiferLoading(false))
  }, [mapLayer])
```

**E. Add "Aquifer Stress" toggle** — find the existing toggle array:

```js
{[['queries', 'Query Volume'], ['drift', 'Drift Reports']].map(([layer, label]) => (
```

Replace with:

```js
{[['queries', 'Query Volume'], ['drift', 'Drift Reports'], ['aquifer', 'Aquifer Stress']].map(([layer, label]) => (
```

And update the active button color logic for the aquifer layer:

```js
mapLayer === layer
  ? layer === 'drift'
    ? 'bg-harvest text-white border-harvest'
    : layer === 'aquifer'
      ? 'bg-blue-600 text-white border-blue-600'
      : 'bg-field text-white border-field'
  : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50 dark:bg-hc-bg dark:text-hc-fg dark:border-hc-border',
```

**F. Pass `aquiferData` prop to `ARCountyMap`**:

```jsx
<ARCountyMap
  countyData={metrics?.county_query_volume ?? []}
  dataLayer={mapLayer}
  driftData={driftCountMap}
  aquiferData={aquiferData}
/>
```

- [ ] **Step 3: Run frontend lint**

```bash
cd frontend && npm run lint
```

Expected: No errors.

- [ ] **Step 4: Run frontend tests**

```bash
cd frontend && npm run test -- --run
```

Expected: All existing tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/admin/ARCountyMap.jsx frontend/src/pages/AdminDashboardPage.jsx
git commit -m "feat: add aquifer stress toggle to admin county map"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `awd_thresholds.json` | Task 1 |
| Migration 007 `rice_fields` | Task 1 |
| `awd_scheduler.py` with `compute_awd_stage` + `format_awd_context` | Task 2 |
| `AWDStageResult` model | Task 2 |
| `fetch_usgs_well` in `context.py` | Task 3 |
| `RiceField` model, `rice_fields` on 3 user models | Task 4 |
| `create_profile` + `update_profile` accept `rice_fields` | Task 5 |
| `auth.py` passes `rice_fields` | Task 5 |
| `build_system_prompt` `awd_context` param | Task 6 |
| `run_rag_query` injects AWD context for `IN_SCOPE_RICE` | Task 6 |
| `query.py` passes `rice_fields` | Task 6 |
| Nightly AWD alert check | Task 7 |
| Redis dedup for AWD alerts | Task 7 |
| `GET /api/v1/admin/aquifer-stress` | Task 8 |
| Register `admin_aquifer_router` in `main.py` | Task 8 |
| RegisterForm conditional step 4 | Task 9 |
| i18n step 4 strings (EN + ES) | Task 9 |
| `ARCountyMap` aquifer toggle | Task 10 |
| Lazy fetch aquifer data in `AdminDashboardPage` | Task 10 |

All spec requirements covered. ✓

**Placeholder scan:** No TBD/TODO found. All code blocks complete. ✓

**Type consistency:**
- `AWDStageResult` fields: `field_name`, `days_to_threshold`, `recommendation`, `aquifer_stress_level`, `well_depth_m` — consistent across Tasks 2, 6, 7. ✓
- `fetch_usgs_well` returns `{site_no, current_depth_m, stress_level}` — consumed correctly in Tasks 6 and 7. ✓
- `rice_fields: list[dict]` in DB/profile; `list[RiceField]` in API models — serialized with `.model_dump()` at boundary in Tasks 4 and 5. ✓
- `IN_SCOPE_RICE` category string (not `RICE`) — correct in Task 6. ✓
