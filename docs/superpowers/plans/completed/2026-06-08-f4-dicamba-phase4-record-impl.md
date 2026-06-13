# F4 Dicamba Phase 4 — Record Generator + Gate D Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Gate D (verifiable downwind geometry + human-attested equipment checks) and an immutable, PDF-backed spray-record (`POST /dicamba/record` + history page) to the F4 dicamba spray-check.

**Architecture:** Gate D appends to the existing `run_spray_check` engine (so `/check` returns 4 gates). `POST /dicamba/record` re-runs the check server-side authoritatively and persists the snapshot to a new immutable `spray_records` table (RLS owner SELECT+INSERT only) via the `session.py` service-role + manual-`farmer_id` pattern. PDFs regenerate on demand from the frozen record. The wizard's Step 4 gains Gate D checkboxes + Save/Download; a new `/spray-records` page lists saved records.

**Tech Stack:** FastAPI, Pydantic, Supabase (service-role client), ReportLab, React 19 + react-leaflet, Vitest, Playwright, pytest.

**Design spec:** `docs/superpowers/specs/completed/2026-06-08-f4-dicamba-phase4-record-design.md`

---

## File Structure

**Backend**
- Modify `backend/data/dicamba_rules.json` — add `weather_thresholds.downwind_half_angle_deg: 45`.
- Modify `backend/services/spray_rules.py` — `downwind_half_angle_deg(rules)` accessor.
- Modify `backend/services/spray_stations.py` — `bearing_deg`, `angular_diff` pure helpers.
- Modify `backend/services/spray_check.py` — `evaluate_gate_d`, wire into `run_spray_check`.
- Modify `backend/models/spray.py` — `ApplicatorAttestation` (+2 fields), new `SprayRecord` model.
- Create `backend/services/spray_record.py` — `create_record`/`get_record`/`list_records`.
- Modify `backend/services/pdf_generator.py` — `generate_spray_record_pdf`.
- Modify `backend/routers/dicamba.py` — `/record` (POST), `/records`, `/record/{id}`, `/record/{id}/pdf`.
- Create `backend/supabase/migrations/009_spray_records.sql`.
- Tests: extend `test_spray_rules.py`, `test_spray_stations.py`, `test_spray_check.py`, `test_dicamba_router.py`, `test_pdf_generator.py`; create `test_spray_record.py`.

**Frontend**
- Modify `frontend/src/hooks/useSprayCheck.js` — `saveRecord`.
- Modify `frontend/src/components/dicamba/SprayCheckWizard.jsx` — Gate D checkboxes + Save/Download on Step 4.
- Create `frontend/src/hooks/useSprayRecords.js` — `fetchRecords`.
- Create `frontend/src/pages/SprayRecordsPage.jsx` + route + sidebar nav + i18n keys.
- Tests: extend `useSprayCheck.test.js`, create `useSprayRecords.test.js`, extend `e2e/spray-check.spec.js`.

---

## Task 1: Rules-as-data downwind cone

**Files:**
- Modify: `backend/data/dicamba_rules.json`
- Modify: `backend/services/spray_rules.py`
- Test: `backend/tests/test_spray_rules.py`

- [ ] **Step 1: Add the threshold to the rules JSON**

In `backend/data/dicamba_rules.json`, inside the single record's `"weather_thresholds"` object, add a key (after `"air_temp_f"`):

```json
      "air_temp_f": {"min": 50.0, "max": 91.0},
      "downwind_half_angle_deg": 45
```

(Add a comma after the `air_temp_f` line.)

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/test_spray_rules.py`:

```python
def test_downwind_half_angle_deg_reads_value():
    from services import spray_rules
    rules = spray_rules.resolve_rules(date(2026, 5, 1))
    assert spray_rules.downwind_half_angle_deg(rules) == 45.0
```

(Ensure `from datetime import date` is imported at the top — it already is in this file; if not, add it.)

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_spray_rules.py::test_downwind_half_angle_deg_reads_value -v`
Expected: FAIL — `AttributeError: module 'services.spray_rules' has no attribute 'downwind_half_angle_deg'`.

- [ ] **Step 4: Add the accessor**

In `backend/services/spray_rules.py`, after `buffers_ft`:

```python
def downwind_half_angle_deg(rules: dict) -> float:
    """Half-angle (deg) of the downwind cone used by Gate D geometry."""
    return float(rules["weather_thresholds"]["downwind_half_angle_deg"])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_spray_rules.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add backend/data/dicamba_rules.json backend/services/spray_rules.py backend/tests/test_spray_rules.py
git commit -m "feat(f4): rules-as-data downwind cone half-angle (Gate D prep)"
```

---

## Task 2: Bearing + angular-diff geometry helpers

**Files:**
- Modify: `backend/services/spray_stations.py`
- Test: `backend/tests/test_spray_stations.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_spray_stations.py`:

```python
def test_bearing_due_north_is_zero():
    # Same lon, higher lat -> initial bearing ~0 deg.
    b = spray_stations.bearing_deg(34.70, -91.80, 34.85, -91.80)
    assert abs(b - 0.0) < 0.5 or abs(b - 360.0) < 0.5


def test_bearing_due_east_is_ninety():
    b = spray_stations.bearing_deg(34.70, -91.80, 34.70, -91.60)
    assert abs(b - 90.0) < 0.5


def test_angular_diff_wraps_across_zero():
    assert spray_stations.angular_diff(350.0, 10.0) == 20.0
    assert spray_stations.angular_diff(10.0, 350.0) == 20.0
    assert spray_stations.angular_diff(0.0, 180.0) == 180.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_spray_stations.py -k "bearing or angular" -v`
Expected: FAIL — `AttributeError: ... has no attribute 'bearing_deg'`.

- [ ] **Step 3: Add the helpers**

In `backend/services/spray_stations.py`, after `nearest_station`:

```python
def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, 0-360 deg (0 = north)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def angular_diff(a: float, b: float) -> float:
    """Smallest absolute angle (deg) between two bearings, 0-180."""
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_spray_stations.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/services/spray_stations.py backend/tests/test_spray_stations.py
git commit -m "feat(f4): bearing_deg + angular_diff station geometry helpers"
```

---

## Task 3: Attestation fields + SprayRecord model

**Files:**
- Modify: `backend/models/spray.py`
- Test: `backend/tests/test_spray_check.py` (model import is exercised by Gate D tests in Task 4; add a direct model test here)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_spray_check.py`:

```python
def test_attestation_has_gate_d_fields():
    from models.spray import ApplicatorAttestation
    a = ApplicatorAttestation(additives_ok=True, ground_application_only=True)
    assert a.additives_ok is True
    assert a.ground_application_only is True


def test_spray_record_model_roundtrips():
    from datetime import datetime as _dt
    from models.spray import SprayRecord
    rec = SprayRecord(
        id="r1", farmer_id="f1", created_at=_dt(2026, 6, 8, 12, 0),
        lat=34.7, lon=-91.8, product="engenia", applied_at=_dt(2026, 6, 8, 9, 0),
        overall_status="needs_confirmation", rule_version="2026-AR-OTT",
        gates=[], attestation={}, weather_json=None,
    )
    assert rec.product == "engenia"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_spray_check.py -k "gate_d_fields or spray_record_model" -v`
Expected: FAIL — `ValidationError`/`ImportError` (fields/model missing).

- [ ] **Step 3: Extend the models**

In `backend/models/spray.py`, add the two fields to `ApplicatorAttestation` (replace the `tank_clean_ok` line block):

```python
    tank_clean_ok: Optional[bool] = None             # Gate D — sprayer cleaned out
    additives_ok: Optional[bool] = None              # Gate D — VRA+DRA present, AMS absent
    ground_application_only: Optional[bool] = None   # Gate D — no aerial OTT application
```

Then append a `SprayRecord` model at the end of the file:

```python
class SprayRecord(BaseModel):
    id: str
    farmer_id: str
    created_at: datetime
    lat: float
    lon: float
    product: str
    applied_at: datetime
    overall_status: GateStatus
    rule_version: str
    gates: list[dict]
    attestation: dict
    weather_json: Optional[dict] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_spray_check.py -k "gate_d_fields or spray_record_model" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/models/spray.py backend/tests/test_spray_check.py
git commit -m "feat(f4): Gate D attestation fields + SprayRecord model"
```

---

## Task 4: Gate D evaluation + wire into run_spray_check

**Files:**
- Modify: `backend/services/spray_check.py`
- Test: `backend/tests/test_spray_check.py`

- [ ] **Step 1: Extend the `_weather` test helper with wind direction**

In `backend/tests/test_spray_check.py`, replace the `_weather` helper so it carries a wind bearing:

```python
def _weather(wind=6.0, temp=78.0, precip=0.0, risk="low", available=True, wind_dir=180.0):
    if not available:
        return {"available": False}
    return {
        "available": True,
        "wind_speed_mph": wind,
        "temp_f": temp,
        "precip_next_48h_in": precip,
        "wind_direction_deg": wind_dir,
        "inversion": {"risk": risk, "is_estimate": True, "reason": "x"},
    }
```

- [ ] **Step 2: Write the failing Gate D tests**

Append to `backend/tests/test_spray_check.py`:

```python
# ---- Gate D ----

# Field at (34.7, -91.8). A station ~0.97 mi due NORTH (inside the 1-mi research buffer).
NORTH_NEAR = {"id": "n", "name": "North REC", "lat": 34.714, "lon": -91.8}
# A station ~0.9 mi due EAST (inside buffer, crosswind when wind blows north).
EAST_NEAR = {"id": "e", "name": "East REC", "lat": 34.7, "lon": -91.7843}


def _att(**kw):
    return _req(**kw)


def test_gate_d_downwind_fail_when_station_in_cone_and_inside_buffer():
    # Wind FROM south (180) -> blowing TOWARD north (0). North station is downwind + inside buffer.
    gate = spray_check.evaluate_gate_d(RULES, _req(), _weather(wind_dir=180.0), [NORTH_NEAR])
    assert gate.gate == "D"
    assert _check(gate, "downwind_clear").status == "fail"


def test_gate_d_downwind_pass_when_station_is_crosswind():
    # Wind blowing toward north; the only near station is due EAST -> not in the cone.
    gate = spray_check.evaluate_gate_d(RULES, _req(), _weather(wind_dir=180.0), [EAST_NEAR])
    assert _check(gate, "downwind_clear").status == "pass"


def test_gate_d_downwind_pass_when_station_outside_buffer():
    # Station due north but ~10 mi away -> outside the 1-mi buffer, so not a fail.
    far_north = {"id": "fn", "name": "Far North", "lat": 34.85, "lon": -91.8}
    gate = spray_check.evaluate_gate_d(RULES, _req(), _weather(wind_dir=180.0), [far_north])
    assert _check(gate, "downwind_clear").status == "pass"


def test_gate_d_downwind_needs_confirmation_when_wind_unavailable():
    gate = spray_check.evaluate_gate_d(RULES, _req(), _weather(available=False), [NORTH_NEAR])
    assert _check(gate, "downwind_clear").status == "needs_confirmation"


def test_gate_d_equipment_checks_need_confirmation_unattested():
    gate = spray_check.evaluate_gate_d(RULES, _req(), _weather(), [EAST_NEAR])
    for cid in ("boom_height", "droplet_size", "tank_clean", "additives", "ground_application"):
        assert _check(gate, cid).status == "needs_confirmation"


def test_gate_d_equipment_checks_pass_when_attested():
    gate = spray_check.evaluate_gate_d(
        RULES, _req(boom_height_ok=True, droplet_setup_ok=True, tank_clean_ok=True,
                    additives_ok=True, ground_application_only=True),
        _weather(), [EAST_NEAR],
    )
    for cid in ("boom_height", "droplet_size", "tank_clean", "additives", "ground_application"):
        assert _check(gate, cid).status == "pass"


def test_run_spray_check_includes_gate_d():
    resp = spray_check.run_spray_check(_req(), RULES, _weather(), [EAST_NEAR])
    assert {g.gate for g in resp.gates} == {"A", "B", "C", "D"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_spray_check.py -k "gate_d or include_gate_d" -v`
Expected: FAIL — `AttributeError: module 'services.spray_check' has no attribute 'evaluate_gate_d'`.

- [ ] **Step 4: Implement `evaluate_gate_d`**

In `backend/services/spray_check.py`, add a module constant near the top (after imports) and the function before `evaluate_gate_c` (or after — order is free):

```python
_FULL_CIRCLE = 360.0


def _attested_check(check_id, label, ok, attested_reason, unattested_reason):
    """Human-attested Gate D item: pass only on an explicit True attestation."""
    attested = ok is True
    return CheckResult(
        id=check_id, label=label, tier="human_attested",
        status="pass" if attested else "needs_confirmation",
        reason=attested_reason if attested else unattested_reason,
        observed=None, expected="applicator-confirmed",
    )


def evaluate_gate_d(
    rules: dict, req: SprayCheckRequest, weather: dict, stations: list[dict]
) -> GateResult:
    """Gate D — Equipment & target. Verifiable downwind geometry + human-attested setup."""
    half_angle = spray_rules.downwind_half_angle_deg(rules)
    research_buf = float(spray_rules.buffers_ft(rules)["research_station"])
    available = weather.get("available", False)
    wind_dir = weather.get("wind_direction_deg")
    cone_label = f"no research station within a {2 * half_angle:.0f}° downwind cone inside its buffer"

    if not available or wind_dir is None:
        downwind = CheckResult(
            id="downwind_clear", label="No sensitive site downwind of the field",
            tier="verifiable_fact", status="needs_confirmation",
            reason="Wind direction unavailable — confirm downwind exposure on the ground.",
            observed=None, expected=cone_label,
        )
    else:
        wind_toward = (wind_dir + 180.0) % _FULL_CIRCLE
        hit = None
        for s in stations:
            dist = spray_stations.haversine_ft(req.lat, req.lon, s["lat"], s["lon"])
            if dist >= research_buf:
                continue
            bearing = spray_stations.bearing_deg(req.lat, req.lon, s["lat"], s["lon"])
            if spray_stations.angular_diff(wind_toward, bearing) <= half_angle:
                hit = (s, dist, bearing)
                break
        if hit:
            s, dist, bearing = hit
            downwind = CheckResult(
                id="downwind_clear", label="No sensitive site downwind of the field",
                tier="verifiable_fact", status="fail",
                reason=f"{s['name']} is downwind of the field and inside the research-station buffer.",
                observed=f"wind toward {wind_toward:.0f}°; {s['name']} at bearing {bearing:.0f}°, {dist / 5280:.1f} mi",
                expected=cone_label,
            )
        else:
            downwind = CheckResult(
                id="downwind_clear", label="No sensitive site downwind of the field",
                tier="verifiable_fact", status="pass",
                reason="No research station is downwind of the field within its buffer.",
                observed=f"wind toward {wind_toward:.0f}°", expected=cone_label,
            )

    att = req.attestation
    boom = _attested_check(
        "boom_height", "Boom height at or below the label maximum", att.boom_height_ok,
        "Applicator confirmed boom height is within the label maximum.",
        "Confirm the boom is at or below the label maximum height (≤ 2 ft).",
    )
    droplet = _attested_check(
        "droplet_size", "Droplet size Ultra Coarse or coarser", att.droplet_setup_ok,
        "Applicator confirmed nozzles produce Ultra Coarse or coarser droplets.",
        "Confirm nozzle setup produces Ultra Coarse or coarser droplets (per label).",
    )
    tank = _attested_check(
        "tank_clean", "Sprayer cleaned out before loading", att.tank_clean_ok,
        "Applicator confirmed the sprayer was cleaned out.",
        "Confirm the sprayer was cleaned out before loading.",
    )
    additives = _attested_check(
        "additives", "Required additives present, prohibited absent", att.additives_ok,
        "Applicator confirmed approved VRA + DRA are in the tank and AMS is not.",
        "Confirm an approved VRA and DRA are in the tank and that AMS is not added.",
    )
    ground = _attested_check(
        "ground_application", "Ground application only (no aerial)", att.ground_application_only,
        "Applicator confirmed this is a ground application.",
        "Confirm this is a ground application — aerial over-the-top dicamba is prohibited.",
    )

    return _gate("D", "Equipment & target", [downwind, boom, droplet, tank, additives, ground])
```

- [ ] **Step 5: Wire Gate D into `run_spray_check`**

In `backend/services/spray_check.py`, update the `gates` list in `run_spray_check`:

```python
    gates = [
        evaluate_gate_a(rules, req),
        evaluate_gate_b(rules, req, stations or []),
        evaluate_gate_c(rules, weather, req),
        evaluate_gate_d(rules, req, weather, stations or []),
    ]
```

- [ ] **Step 6: Run the full spray-check suite**

Run: `cd backend && python -m pytest tests/test_spray_check.py -v`
Expected: PASS (all, incl. the existing `{A,B,C}`→ now update any assertion expecting exactly `{A,B,C}`).

NOTE: `test_response_stamps_rule_version_from_resolved_record` asserts `{"A","B","C"}`. Update it to `{"A","B","C","D"}`:

```python
    assert {g.gate for g in resp.gates} == {"A", "B", "C", "D"}
```

- [ ] **Step 7: Commit**

```bash
git add backend/services/spray_check.py backend/tests/test_spray_check.py
git commit -m "feat(f4): Gate D downwind geometry + equipment attestations"
```

---

## Task 5: Migration `009_spray_records.sql`

**Files:**
- Create: `backend/supabase/migrations/009_spray_records.sql`

- [ ] **Step 1: Write the migration**

Create `backend/supabase/migrations/009_spray_records.sql`:

```sql
-- 009_spray_records.sql
-- Immutable dicamba spray-decision records (F4 Phase 4).
-- Append-only: no UPDATE/DELETE policy -> both denied for everyone.

CREATE TABLE IF NOT EXISTS public.spray_records (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  farmer_id       uuid REFERENCES farmer_profiles(id) ON DELETE CASCADE,
  created_at      timestamptz DEFAULT now(),
  lat             double precision NOT NULL,
  lon             double precision NOT NULL,
  product         text NOT NULL,
  applied_at      timestamptz NOT NULL,
  overall_status  text NOT NULL,
  rule_version    text NOT NULL,
  gates           jsonb NOT NULL,
  attestation     jsonb NOT NULL,
  weather_json    jsonb
);

ALTER TABLE public.spray_records ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "farmer reads own spray records" ON spray_records;
CREATE POLICY "farmer reads own spray records"
  ON spray_records FOR SELECT
  USING (farmer_id = auth.uid());

DROP POLICY IF EXISTS "farmer inserts own spray records" ON spray_records;
CREATE POLICY "farmer inserts own spray records"
  ON spray_records FOR INSERT
  WITH CHECK (farmer_id = auth.uid());

DROP POLICY IF EXISTS "admin reads all spray records" ON spray_records;
CREATE POLICY "admin reads all spray records"
  ON spray_records FOR SELECT
  USING (
    auth.uid()::text = ANY(
      string_to_array(current_setting('app.admin_user_ids', true), ',')
    )
  );

CREATE INDEX IF NOT EXISTS spray_records_farmer_recent
  ON public.spray_records USING btree (farmer_id, created_at DESC);
```

- [ ] **Step 2: Sanity-check the SQL parses (optional, no DB)**

Run: `cd backend && python -c "open('supabase/migrations/009_spray_records.sql').read(); print('ok')"`
Expected: `ok` (file exists/readable; full apply happens on a Supabase branch at verification).

- [ ] **Step 3: Commit**

```bash
git add backend/supabase/migrations/009_spray_records.sql
git commit -m "feat(f4): migration 009 immutable spray_records table + RLS"
```

---

## Task 6: `spray_record.py` service

**Files:**
- Create: `backend/services/spray_record.py`
- Test: `backend/tests/test_spray_record.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_spray_record.py`:

```python
import importlib
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _fake_insert_client(sink):
    class FakeResult:
        data = [{"id": "rec-1", "farmer_id": "farmer-1"}]

    class FakeTable:
        def insert(self, row):
            sink.append(row)
            return self
        def execute(self):
            return FakeResult()

    class FakeClient:
        def table(self, _name):
            return FakeTable()

    return FakeClient()


def _fake_select_client(return_data, captured_eqs):
    class FakeResult:
        data = return_data

    class FakeChain:
        def select(self, *a): return self
        def eq(self, col, val):
            captured_eqs.append((col, val))
            return self
        def order(self, *a, **kw): return self
        def maybe_single(self): return self
        def execute(self): return FakeResult()

    class FakeClient:
        def table(self, _name):
            return FakeChain()

    return FakeClient()


def test_create_record_stamps_farmer_id_from_arg(monkeypatch):
    svc = importlib.import_module("services.spray_record")
    sink = []
    monkeypatch.setattr(svc, "_get_service_client", lambda: _fake_insert_client(sink))
    payload = {
        "lat": 34.7, "lon": -91.8, "product": "engenia",
        "applied_at": "2026-06-08T09:00:00", "overall_status": "needs_confirmation",
        "rule_version": "2026-AR-OTT", "gates": [], "attestation": {},
        "weather_json": None, "farmer_id": "attacker-supplied",
    }
    svc.create_record("farmer-1", payload)
    # farmer_id is stamped from the arg, never the payload.
    assert sink[0]["farmer_id"] == "farmer-1"


def test_get_record_filters_by_id_and_farmer(monkeypatch):
    svc = importlib.import_module("services.spray_record")
    eqs = []
    monkeypatch.setattr(
        svc, "_get_service_client", lambda: _fake_select_client({"id": "rec-1"}, eqs)
    )
    svc.get_record("rec-1", "farmer-1")
    assert ("id", "rec-1") in eqs
    assert ("farmer_id", "farmer-1") in eqs


def test_get_record_returns_none_for_foreign(monkeypatch):
    svc = importlib.import_module("services.spray_record")
    monkeypatch.setattr(
        svc, "_get_service_client", lambda: _fake_select_client(None, [])
    )
    assert svc.get_record("rec-1", "other-farmer") is None


def test_no_mutate_or_delete_surface():
    svc = importlib.import_module("services.spray_record")
    assert not hasattr(svc, "update_record")
    assert not hasattr(svc, "delete_record")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_spray_record.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.spray_record'`.

- [ ] **Step 3: Implement the service**

Create `backend/services/spray_record.py`:

```python
"""CRUD for the immutable spray_records table (F4 Phase 4).

Append-only: only create/read/list. Uses the service-role client (bypasses RLS),
so farmer_id is stamped from the authenticated arg — never client-supplied — and
reads filter by farmer_id manually (mirrors services/session.py, anti-IDOR)."""
from services.user import _get_service_client
from utils.db import _assert_insert

_PERSISTED = (
    "lat", "lon", "product", "applied_at", "overall_status",
    "rule_version", "gates", "attestation", "weather_json",
)


def create_record(farmer_id: str, payload: dict) -> dict:
    row = {k: payload.get(k) for k in _PERSISTED}
    row["farmer_id"] = farmer_id  # from JWT, never the payload
    result = _get_service_client().table("spray_records").insert(row).execute()
    _assert_insert(result, f"spray_record (farmer {farmer_id})")
    return result.data[0]


def get_record(record_id: str, farmer_id: str) -> dict | None:
    result = (
        _get_service_client()
        .table("spray_records")
        .select("*")
        .eq("id", record_id)
        .eq("farmer_id", farmer_id)
        .maybe_single()
        .execute()
    )
    return result.data


def list_records(farmer_id: str, limit: int = 50) -> list[dict]:
    result = (
        _get_service_client()
        .table("spray_records")
        .select("*")
        .eq("farmer_id", farmer_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []
```

NOTE: the `_fake_select_client` in the test does not implement `.limit()`. Add `def limit(self, *a): return self` to that fake chain, OR keep the service without `.limit` on `get_record` (it has none) — only `list_records` uses `.limit`. Update the test fake to include `limit`:

In `backend/tests/test_spray_record.py` `_fake_select_client`'s `FakeChain`, add:

```python
        def limit(self, *a): return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_spray_record.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/services/spray_record.py backend/tests/test_spray_record.py
git commit -m "feat(f4): spray_record service (create/get/list, anti-IDOR, no mutate)"
```

---

## Task 7: PDF generator

**Files:**
- Modify: `backend/services/pdf_generator.py`
- Test: `backend/tests/test_pdf_generator.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_pdf_generator.py` (match the import style already used there; if the module is imported as `from services.pdf_generator import ...`, mirror it):

```python
def test_generate_spray_record_pdf_returns_pdf_bytes():
    from services.pdf_generator import generate_spray_record_pdf
    record = {
        "id": "rec-1", "lat": 34.7, "lon": -91.8, "product": "engenia",
        "applied_at": "2026-06-08T09:00:00", "overall_status": "needs_confirmation",
        "rule_version": "2026-AR-OTT",
        "gates": [
            {"gate": "A", "title": "Legal window", "status": "pass", "checks": [
                {"id": "in_season", "label": "Inside the dicamba season window",
                 "tier": "verifiable_fact", "status": "pass", "reason": "ok", "observed": "2026-06-08"}
            ]},
        ],
        "attestation": {"no_inversion_observed": True, "boom_height_ok": True},
        "weather_json": {"available": True, "wind_speed_mph": 6.0, "temp_f": 78.0},
    }
    out = generate_spray_record_pdf(record, {"full_name": "Jane Farmer", "email": "j@x.com"})
    assert out[:4] == b"%PDF"


def test_generate_spray_record_pdf_handles_missing_weather_and_empty_profile():
    from services.pdf_generator import generate_spray_record_pdf
    record = {
        "id": "rec-2", "lat": 34.7, "lon": -91.8, "product": "engenia",
        "applied_at": "2026-06-08T09:00:00", "overall_status": "fail",
        "rule_version": "2026-AR-OTT", "gates": [], "attestation": {}, "weather_json": None,
    }
    out = generate_spray_record_pdf(record, {})
    assert out[:4] == b"%PDF"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_pdf_generator.py -k spray_record -v`
Expected: FAIL — `ImportError: cannot import name 'generate_spray_record_pdf'`.

- [ ] **Step 3: Implement the generator**

Append to `backend/services/pdf_generator.py` (reuses the existing `_table` helper and imports):

```python
def generate_spray_record_pdf(record: dict, farmer_profile: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch,
    )
    styles = getSampleStyleSheet()
    center = ParagraphStyle("center", parent=styles["Heading1"], fontSize=14, alignment=1)
    h2 = styles["Heading2"]
    normal = styles["Normal"]
    bold = ParagraphStyle("bold", parent=normal, fontName="Helvetica-Bold")
    story = []

    story.append(Paragraph("AGROADVISOR AR", center))
    story.append(Paragraph("DICAMBA SPRAY RECORD", center))
    story.append(Paragraph(f"Generated: {date_type.today().strftime('%B %d, %Y')}", normal))
    story.append(HRFlowable(width="100%", thickness=1))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("1. APPLICATOR & FIELD", h2))
    story.append(_table([
        ["Applicator:", farmer_profile.get("full_name") or "N/A"],
        ["Email:", farmer_profile.get("email") or "N/A"],
        ["Field (lat, lon):", f"{record.get('lat')}, {record.get('lon')}"],
        ["Product:", record.get("product") or "N/A"],
        ["Applied at:", str(record.get("applied_at") or "N/A")],
        ["Rule version:", record.get("rule_version") or "N/A"],
        ["Overall status:", str(record.get("overall_status") or "N/A")],
    ]))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("2. GATE OUTCOMES", h2))
    for gate in record.get("gates") or []:
        story.append(Paragraph(f"Gate {gate.get('gate')} — {gate.get('title')} [{gate.get('status')}]", bold))
        rows = [
            [c.get("label", ""), c.get("status", ""), c.get("observed") or ""]
            for c in gate.get("checks") or []
        ]
        if rows:
            story.append(_table_wide(rows))
        story.append(Spacer(1, 0.1 * inch))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("3. CONFIRMED BY APPLICATOR", h2))
    att = record.get("attestation") or {}
    confirmed = [k for k, v in att.items() if v is True]
    if confirmed:
        for k in confirmed:
            story.append(Paragraph(f"☑  {k.replace('_', ' ')}", normal))
    else:
        story.append(Paragraph("No items were attested.", normal))
    story.append(Spacer(1, 0.2 * inch))

    story.append(HRFlowable(width="100%", thickness=1))
    story.append(Paragraph(
        "This is a record of your decision and the conditions you confirmed. It is NOT legal "
        "advice or an authorization to spray. Always verify the product label and current state rules.",
        bold,
    ))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph("Generated by AgroAdvisor AR", normal))

    doc.build(story)
    return buffer.getvalue()


def _table_wide(data: list) -> Table:
    t = Table(data, colWidths=[3.2 * inch, 1.3 * inch, 1.5 * inch])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_pdf_generator.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/services/pdf_generator.py backend/tests/test_pdf_generator.py
git commit -m "feat(f4): spray-record PDF generator"
```

---

## Task 8: Record endpoints

**Files:**
- Modify: `backend/routers/dicamba.py`
- Test: `backend/tests/test_dicamba_router.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_dicamba_router.py`:

```python
def test_create_record_persists_and_uses_authenticated_owner(monkeypatch):
    router_mod = importlib.import_module("routers.dicamba")
    monkeypatch.setattr(router_mod, "resolve_rules", lambda on_date: RULES)
    monkeypatch.setattr(
        router_mod, "fetch_forecast_conditions", AsyncMock(return_value=WEATHER_OK)
    )
    monkeypatch.setattr(router_mod, "load_stations", lambda: [])
    captured = {}

    def _fake_create(farmer_id, payload):
        captured["farmer_id"] = farmer_id
        captured["payload"] = payload
        return {"id": "rec-1", "farmer_id": farmer_id, **payload}

    monkeypatch.setattr(router_mod, "create_record", _fake_create)

    rec = asyncio.run(router_mod.create_spray_record(_body(), user=FAKE_USER))
    assert captured["farmer_id"] == FAKE_USER["sub"]
    assert captured["payload"]["rule_version"] == "2026-AR-OTT"
    assert {g["gate"] for g in captured["payload"]["gates"]} == {"A", "B", "C", "D"}
    assert rec["id"] == "rec-1"


def test_get_record_404_when_foreign(monkeypatch):
    router_mod = importlib.import_module("routers.dicamba")
    monkeypatch.setattr(router_mod, "get_record", lambda rid, fid: None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(router_mod.get_spray_record("rec-x", user=FAKE_USER))
    assert exc.value.status_code == 404


def test_list_records_uses_owner(monkeypatch):
    router_mod = importlib.import_module("routers.dicamba")
    seen = {}
    monkeypatch.setattr(
        router_mod, "list_records",
        lambda fid, **kw: seen.setdefault("fid", fid) or [{"id": "rec-1"}],
    )
    out = asyncio.run(router_mod.list_spray_records(user=FAKE_USER))
    assert seen["fid"] == FAKE_USER["sub"]
    assert out[0]["id"] == "rec-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_dicamba_router.py -k "record" -v`
Expected: FAIL — `AttributeError: ... has no attribute 'create_spray_record'`.

- [ ] **Step 3: Implement the endpoints**

In `backend/routers/dicamba.py`, extend imports and add the routes. Update the imports block:

```python
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from models.spray import (
    ResearchStation, SprayCheckRequest, SprayCheckResponse, SprayRecord,
)
from services.auth import get_current_user
from services.pdf_generator import generate_spray_record_pdf
from services.spray_check import run_spray_check
from services.spray_record import create_record, get_record, list_records
from services.spray_rules import RulesNotFoundError, resolve_rules
from services.spray_stations import load_stations
from services.user import get_profile
from services.weather_now import fetch_forecast_conditions
```

Then append the routes after `list_stations`:

```python
def _build_record_payload(body: SprayCheckRequest, resp: SprayCheckResponse, weather: dict) -> dict:
    return {
        "lat": body.lat,
        "lon": body.lon,
        "product": body.product,
        "applied_at": body.at.isoformat(),
        "overall_status": resp.overall_status,
        "rule_version": resp.rule_version,
        "gates": [g.model_dump() for g in resp.gates],
        "attestation": body.attestation.model_dump(),
        "weather_json": weather if weather.get("available") else None,
    }


@router.post("/record", response_model=SprayRecord, status_code=201)
async def create_spray_record(
    body: SprayCheckRequest,
    user: dict = Depends(get_current_user),
):
    try:
        rules = resolve_rules(body.at.date())
    except RulesNotFoundError:
        raise HTTPException(status_code=422, detail="No dicamba rules effective for that date")
    weather = await fetch_forecast_conditions(body.lat, body.lon, body.at)
    stations = load_stations()
    resp = run_spray_check(body, rules, weather, stations)
    payload = _build_record_payload(body, resp, weather)
    return create_record(user["sub"], payload)


@router.get("/records", response_model=list[SprayRecord])
async def list_spray_records(user: dict = Depends(get_current_user)):
    return list_records(user["sub"])


@router.get("/record/{record_id}", response_model=SprayRecord)
async def get_spray_record(record_id: str, user: dict = Depends(get_current_user)):
    record = get_record(record_id, user["sub"])
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.get("/record/{record_id}/pdf")
async def download_spray_record_pdf(record_id: str, user: dict = Depends(get_current_user)):
    record = get_record(record_id, user["sub"])
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    profile = get_profile(user["sub"]) or {}
    pdf_bytes = generate_spray_record_pdf(record, profile)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=spray_record_{record_id[:8]}.pdf"},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_dicamba_router.py -v`
Expected: PASS (all).

- [ ] **Step 5: Run the FULL backend suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS (all). Fix any assertion still expecting 3 gates.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/dicamba.py backend/tests/test_dicamba_router.py
git commit -m "feat(f4): /dicamba/record endpoints (create/list/get/pdf)"
```

---

## Task 9: Wizard — Gate D checkboxes + Save/Download (Step 4)

**Files:**
- Modify: `frontend/src/hooks/useSprayCheck.js`
- Modify: `frontend/src/components/dicamba/SprayCheckWizard.jsx`
- Test: `frontend/src/hooks/useSprayCheck.test.js`

- [ ] **Step 1: Add `saveRecord` to the hook**

In `frontend/src/hooks/useSprayCheck.js`, after `fetchStations`:

```js
  // Persist the decision as an immutable record; returns the saved row (with id).
  const saveRecord = useCallback(async ({ lat, lon, product, at, attestation }) => {
    const res = await api.post('/dicamba/record', {
      lat,
      lon,
      product,
      at: at || new Date().toISOString(),
      attestation: attestation || {},
    })
    return res.data
  }, [])
```

Add `saveRecord` to the returned object:

```js
  return { runCheck, fetchStations, saveRecord, loading, error }
```

- [ ] **Step 2: Write the failing hook test**

Append to `frontend/src/hooks/useSprayCheck.test.js` — but the existing file only tests `getSprayStepErrors` (pure). Add a request-shape note instead via the wizard e2e (Task 11). For the unit layer, assert the attestation keys the wizard sends are complete by testing `getSprayStepErrors` step-4 has no required fields (already covered) AND add a guard test that the Gate D field names exist as constants. Skip a network unit test here (axios mocking isn't set up in this file). Proceed to the wizard.

(No code change in this step — it documents that hook network tests are covered by e2e.)

- [ ] **Step 3: Add Gate D state + handlers to the wizard**

In `frontend/src/components/dicamba/SprayCheckWizard.jsx`:

(a) destructure `saveRecord`:

```js
  const { runCheck, fetchStations, saveRecord, loading, error } = useSprayCheck()
```

(b) add to the initial `form` state (after `organic_specialty_checked: false,`):

```js
    boom_height_ok: false,
    droplet_setup_ok: false,
    tank_clean_ok: false,
    additives_ok: false,
    ground_application_only: false,
```

(c) add record state near the other `useState`s:

```js
  const [savedRecord, setSavedRecord] = useState(null)
  const [saving, setSaving] = useState(false)
```

(d) extend the `check()` attestation object to send all attestation fields:

```js
        attestation: {
          no_inversion_observed: merged.no_inversion_observed,
          sensitive_crops_checked: merged.sensitive_crops_checked,
          organic_specialty_checked: merged.organic_specialty_checked,
          boom_height_ok: merged.boom_height_ok,
          droplet_setup_ok: merged.droplet_setup_ok,
          tank_clean_ok: merged.tank_clean_ok,
          additives_ok: merged.additives_ok,
          ground_application_only: merged.ground_application_only,
        },
```

(e) add a generic Gate D toggle (re-runs `/check`, like the inversion toggle) and a save handler, after `handleGateBToggle`:

```js
  async function handleGateDToggle(field, checked) {
    set(field, checked)
    await check({ [field]: checked })
  }

  async function handleSaveRecord() {
    setSaving(true)
    try {
      const rec = await saveRecord({
        lat: form.lat,
        lon: form.lon,
        product: form.product,
        attestation: {
          no_inversion_observed: form.no_inversion_observed,
          sensitive_crops_checked: form.sensitive_crops_checked,
          organic_specialty_checked: form.organic_specialty_checked,
          boom_height_ok: form.boom_height_ok,
          droplet_setup_ok: form.droplet_setup_ok,
          tank_clean_ok: form.tank_clean_ok,
          additives_ok: form.additives_ok,
          ground_application_only: form.ground_application_only,
        },
      })
      setSavedRecord(rec)
    } catch {
      // surfaced via hook error state
    } finally {
      setSaving(false)
    }
  }
```

- [ ] **Step 4: Render Gate D checkboxes + Save/Download on Step 4**

In the Step 4 block (`{step === 4 && (`), inside the `{result ? ( <> ... )` fragment, AFTER the gate cards `<div className="space-y-3">...</div>` and BEFORE the rule-version `<p>`, insert a Gate D attestation block and the save/download controls:

```jsx
              <div className="space-y-2" data-testid="gate-d-attestations">
                <p className="text-sm font-semibold text-charcoal dark:text-hc-fg">
                  {es ? 'Equipo y objetivo (Compuerta D)' : 'Equipment & target (Gate D)'}
                </p>
                {[
                  ['boom_height_ok', es ? 'Altura de botavara dentro del máximo de la etiqueta.' : 'Boom height within the label maximum.'],
                  ['droplet_setup_ok', es ? 'Boquillas producen gotas Ultra Gruesas o más.' : 'Nozzles produce Ultra Coarse or coarser droplets.'],
                  ['tank_clean_ok', es ? 'Tanque limpiado antes de cargar.' : 'Sprayer cleaned out before loading.'],
                  ['additives_ok', es ? 'VRA + DRA aprobados presentes; sin AMS.' : 'Approved VRA + DRA present; no AMS.'],
                  ['ground_application_only', es ? 'Aplicación terrestre solamente (sin aérea).' : 'Ground application only (no aerial).'],
                ].map(([field, label]) => (
                  <label key={field} className="flex items-start gap-2 text-sm text-charcoal dark:text-hc-fg cursor-pointer bg-gray-50 rounded-xl p-3 dark:bg-hc-bg">
                    <input
                      type="checkbox"
                      checked={form[field]}
                      onChange={(e) => handleGateDToggle(field, e.target.checked)}
                      className="rounded accent-field mt-0.5"
                      data-testid={`gate-d-${field}`}
                    />
                    {label}
                  </label>
                ))}
              </div>

              {savedRecord ? (
                <a
                  href={`/api/v1/dicamba/record/${savedRecord.id}/pdf`}
                  className={BTN_PRIMARY_CLS}
                  data-testid="download-pdf-link"
                >
                  {es ? 'Descargar PDF del registro' : 'Download record PDF'}
                </a>
              ) : (
                <button
                  type="button"
                  onClick={handleSaveRecord}
                  disabled={saving}
                  className={BTN_PRIMARY_CLS}
                  data-testid="save-record-btn"
                >
                  {saving
                    ? (es ? 'Guardando...' : 'Saving...')
                    : (es ? 'Guardar registro' : 'Save record')}
                </button>
              )}
```

- [ ] **Step 5: Run vitest + lint**

Run: `cd frontend && npm run test && npm run lint`
Expected: PASS + clean (existing `getSprayStepErrors` tests still green; no new failures).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useSprayCheck.js frontend/src/components/dicamba/SprayCheckWizard.jsx frontend/src/hooks/useSprayCheck.test.js
git commit -m "feat(f4): wizard Step 4 Gate D attestations + save record + PDF download"
```

---

## Task 10: Records history page

**Files:**
- Create: `frontend/src/hooks/useSprayRecords.js`
- Create: `frontend/src/pages/SprayRecordsPage.jsx`
- Modify: `frontend/src/App.jsx` (route)
- Modify: the sidebar nav component + `frontend/src/i18n.js` (or wherever `t.sprayCheck` lives)
- Test: `frontend/src/hooks/useSprayRecords.test.js`

- [ ] **Step 1: Locate the nav + i18n + routing anchors**

Run: `cd frontend && grep -rn "sprayCheck\|/spray-check" src/`
Expected: shows the route registration in `App.jsx`, the sidebar `<NavLink>`/`<a href="/spray-check">`, and the `sprayCheck` key in `i18n.js` (EN + ES). Use these exact locations as the pattern for the records page.

- [ ] **Step 2: Create the hook**

Create `frontend/src/hooks/useSprayRecords.js`:

```js
import { useState, useEffect, useCallback } from 'react'
import api from '../lib/api'

export function useSprayRecords() {
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchRecords = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get('/dicamba/records')
      setRecords(res.data)
      return res.data
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load records')
      return []
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchRecords() }, [fetchRecords])

  return { records, loading, error, fetchRecords }
}
```

- [ ] **Step 3: Write the failing hook test**

Create `frontend/src/hooks/useSprayRecords.test.js`:

```js
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useSprayRecords } from './useSprayRecords'
import api from '../lib/api'

vi.mock('../lib/api', () => ({ default: { get: vi.fn() } }))

describe('useSprayRecords', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads records on mount', async () => {
    api.get.mockResolvedValue({ data: [{ id: 'rec-1', product: 'engenia' }] })
    const { result } = renderHook(() => useSprayRecords())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(api.get).toHaveBeenCalledWith('/dicamba/records')
    expect(result.current.records[0].id).toBe('rec-1')
  })
})
```

NOTE: confirm `@testing-library/react` is a dependency. Run `cd frontend && grep testing-library package.json`. If absent, instead write a plain test that mocks `api` and calls `fetchRecords` via the exported function logic — but the project already uses Vitest + React 19, and `renderHook` is the idiomatic choice; add `@testing-library/react` as a devDependency only if missing (`npm i -D @testing-library/react`).

- [ ] **Step 4: Run test to verify it fails then passes**

Run: `cd frontend && npx vitest run src/hooks/useSprayRecords.test.js`
Expected: FAIL first (hook not wired / lib mock), then PASS after Step 2 is in place. (Step 2 precedes this; if it already passes, good.)

- [ ] **Step 5: Create the page**

Create `frontend/src/pages/SprayRecordsPage.jsx`:

```jsx
import { useLang } from '../contexts/LangContext'
import { useSprayRecords } from '../hooks/useSprayRecords'
import Alert from '../components/ui/Alert'

const STATUS_BADGE = {
  pass: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100',
  fail: 'bg-red-100 text-red-900 dark:bg-red-900 dark:text-red-100',
  needs_confirmation: 'bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100',
}

export default function SprayRecordsPage() {
  const { lang } = useLang()
  const es = lang === 'es'
  const { records, loading, error } = useSprayRecords()

  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm dark:bg-hc-surface dark:border-hc-border">
      <h1 className="text-lg font-bold text-charcoal dark:text-hc-fg mb-4">
        {es ? 'Registros de aplicación' : 'Spray records'}
      </h1>
      {error && <Alert variant="error" className="mb-4">{error}</Alert>}
      {loading ? (
        <p className="text-sm text-gray-500 dark:text-hc-fg">{es ? 'Cargando...' : 'Loading...'}</p>
      ) : records.length === 0 ? (
        <Alert variant="info">{es ? 'Aún no hay registros guardados.' : 'No saved records yet.'}</Alert>
      ) : (
        <ul className="space-y-2" data-testid="records-list">
          {records.map((r) => (
            <li key={r.id} className="flex items-center justify-between bg-gray-50 rounded-xl p-3 dark:bg-hc-bg">
              <div className="text-sm text-charcoal dark:text-hc-fg">
                <span className="font-semibold">{r.product}</span>
                {' · '}{new Date(r.applied_at).toLocaleDateString()}
                <span className={`ml-2 text-[10px] font-bold px-2 py-0.5 rounded-full ${STATUS_BADGE[r.overall_status] || ''}`}>
                  {r.overall_status}
                </span>
              </div>
              <a
                href={`/api/v1/dicamba/record/${r.id}/pdf`}
                className="text-sm font-semibold text-field-dark underline min-h-touch flex items-center"
              >
                {es ? 'PDF' : 'PDF'}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 6: Register the route + nav + i18n**

In `frontend/src/App.jsx`, add (mirror the `/spray-check` route registration found in Step 1):

```jsx
import SprayRecordsPage from './pages/SprayRecordsPage'
// ...inside the authenticated <Routes>, beside the spray-check route:
<Route path="/spray-records" element={<SprayRecordsPage />} />
```

In the sidebar nav (the file Step 1 surfaced), add a link beside the spray-check one:

```jsx
<NavLink to="/spray-records" /* same className pattern as the spray-check link */>
  {t.sprayRecords}
</NavLink>
```

In `frontend/src/i18n.js`, add to BOTH the `en` and `es` dictionaries (beside `sprayCheck`):

```js
  sprayRecords: 'Spray records', // en
```
```js
  sprayRecords: 'Registros', // es
```

- [ ] **Step 7: Run vitest + lint**

Run: `cd frontend && npm run test && npm run lint`
Expected: PASS + clean.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/hooks/useSprayRecords.js frontend/src/hooks/useSprayRecords.test.js frontend/src/pages/SprayRecordsPage.jsx frontend/src/App.jsx frontend/src/i18n.js frontend/src/components
git commit -m "feat(f4): spray-records history page + route + nav"
```

---

## Task 11: E2E — Gate D attest, save, PDF link, records list

**Files:**
- Modify: `frontend/e2e/spray-check.spec.js`

- [ ] **Step 1: Extend the check mock for Gate D + add record routes**

In `frontend/e2e/spray-check.spec.js` `checkResponse(att)`, add a Gate D gate to the `gates` array (after Gate C), driven by attestation, and fold it into the overall rollup:

```js
      {
        gate: 'D',
        title: 'Equipment & target',
        status: (att.boom_height_ok && att.droplet_setup_ok && att.tank_clean_ok && att.additives_ok && att.ground_application_only) ? 'pass' : 'needs_confirmation',
        checks: [
          { id: 'downwind_clear', label: 'No sensitive site downwind of the field', tier: 'verifiable_fact', status: 'pass', reason: 'No research station is downwind within its buffer.', observed: 'wind toward 0°', expected: 'no research station within a 90° downwind cone inside its buffer' },
          { id: 'boom_height', label: 'Boom height at or below the label maximum', tier: 'human_attested', status: att.boom_height_ok ? 'pass' : 'needs_confirmation', reason: 'x', observed: null, expected: 'applicator-confirmed' },
          { id: 'droplet_size', label: 'Droplet size Ultra Coarse or coarser', tier: 'human_attested', status: att.droplet_setup_ok ? 'pass' : 'needs_confirmation', reason: 'x', observed: null, expected: 'applicator-confirmed' },
          { id: 'tank_clean', label: 'Sprayer cleaned out before loading', tier: 'human_attested', status: att.tank_clean_ok ? 'pass' : 'needs_confirmation', reason: 'x', observed: null, expected: 'applicator-confirmed' },
          { id: 'additives', label: 'Required additives present, prohibited absent', tier: 'human_attested', status: att.additives_ok ? 'pass' : 'needs_confirmation', reason: 'x', observed: null, expected: 'applicator-confirmed' },
          { id: 'ground_application', label: 'Ground application only (no aerial)', tier: 'human_attested', status: att.ground_application_only ? 'pass' : 'needs_confirmation', reason: 'x', observed: null, expected: 'applicator-confirmed' },
        ],
      },
```

Then in `mockRoutes(page)`, add the record routes:

```js
  await page.route('**/api/v1/dicamba/record', (route) =>
    route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ id: 'rec-1', product: 'engenia', applied_at: '2026-06-08T09:00:00', overall_status: 'needs_confirmation' }) })
  );
  await page.route('**/api/v1/dicamba/records', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([{ id: 'rec-1', product: 'engenia', applied_at: '2026-06-08T09:00:00', overall_status: 'needs_confirmation' }]) })
  );
  await page.route('**/api/v1/dicamba/record/*/pdf', (route) =>
    route.fulfill({ status: 200, contentType: 'application/pdf', body: '%PDF-1.4 fake' })
  );
```

NOTE: register `**/dicamba/record` BEFORE `**/dicamba/records` is not required (different paths), but register `**/dicamba/check` so it does not greedily match `/record`. Playwright matches by glob; `**/dicamba/check` won't match `/record`, so order is safe.

- [ ] **Step 2: Add a save + PDF assertion to the 4-step walk**

At the end of the existing `wizard walks 4 steps ...` test (after the outcome-banner assertion), append:

```js
  // Step 4 — attest Gate D, save the record, PDF link appears
  await page.getByTestId('gate-d-boom_height_ok').check();
  await page.getByTestId('gate-d-droplet_setup_ok').check();
  await page.getByTestId('gate-d-tank_clean_ok').check();
  await page.getByTestId('gate-d-additives_ok').check();
  await page.getByTestId('gate-d-ground_application_only').check();
  const [recReq] = await Promise.all([
    page.waitForRequest('**/api/v1/dicamba/record'),
    page.getByTestId('save-record-btn').click(),
  ]);
  expect(recReq.postDataJSON().attestation.boom_height_ok).toBe(true);
  await expect(page.getByTestId('download-pdf-link')).toBeVisible({ timeout: 10000 });
```

- [ ] **Step 3: Add a records-page test**

Append a new test to `frontend/e2e/spray-check.spec.js`:

```js
test('spray-records page lists saved records', async ({ page }) => {
  await page.goto('/spray-records');
  await expect(page.getByTestId('records-list')).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId('records-list')).toContainText('engenia');
});
```

- [ ] **Step 4: Run the spray e2e**

Run: `cd frontend && npx playwright test spray-check`
Expected: PASS (all spray specs).

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/spray-check.spec.js
git commit -m "test(f4): e2e Gate D attest + save record + PDF link + records page"
```

---

## Task 12: Docs + memory update

**Files:**
- Modify: `PROGRESS.md`, `CLAUDE.md`
- Modify: `C:\Users\jeged\.claude\projects\C--Users-jeged-Downloads-AgroAdvisor\memory\project_f4_dicamba.md` + `MEMORY.md`

- [ ] **Step 1: Update PROGRESS.md**

Add a "Phase 4 SHIPPED" paragraph mirroring the Phase 3 entry: `spray_records` immutable table + RLS (009), Gate D (downwind geometry + 5 equipment attestations), `/dicamba/record` + `/records` + `/record/{id}` + `/pdf`, PDF generator, wizard Step 4 Gate D + Save/Download, `/spray-records` page. Record final test counts (backend/frontend/playwright). Note HF backend still not redeployed + migration 009 must be applied at cutover.

- [ ] **Step 2: Update CLAUDE.md F4 section**

Add a `**Phase 4 (record + Gate D):**` bullet under the F4 Dicamba Spray-Check section; move "record save + PDF" and "Gate D" out of Pending.

- [ ] **Step 3: Update memory**

Append a Phase 4 SHIPPED block to `memory/project_f4_dicamba.md`; update its `description:` and the `MEMORY.md` index line to "Phases 0-4 SHIPPED ... Phase 5 next = FieldWatch + pro Spanish".

- [ ] **Step 4: Commit**

```bash
git add PROGRESS.md CLAUDE.md
git commit -m "docs(f4): record Phase 4 (record generator + Gate D) shipped"
```

(Memory files live outside the repo — they are written, not committed.)

---

## Final verification

- [ ] `cd backend && python -m pytest -q` → all green.
- [ ] `cd frontend && npm run test && npm run lint` → green + clean.
- [ ] `cd frontend && npx playwright test spray-check` → green.
- [ ] Apply `009_spray_records.sql` to a Supabase branch; manual smoke: run a check → attest Gate D → Save → download PDF → second user 404s on the first's record.
- [ ] (Deferred, owner) HF backend orphan-branch redeploy so `/record` + 4th gate go live; apply 009 to prod Supabase.
```
