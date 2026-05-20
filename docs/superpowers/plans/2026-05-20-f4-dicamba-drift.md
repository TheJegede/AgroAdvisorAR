# F4 Dicamba Drift Documentation Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a structured 3-step drift incident wizard, Open-Meteo weather auto-fill, ASPB complaint PDF generator, admin drift-reports tab with choropleth second layer, and Playwright E2E coverage.

**Architecture:** Service-split backend (`weather_history.py` + `drift_service.py` + `pdf_generator.py` + thin `drift_reports` router). 3-step React wizard follows `RegisterForm.jsx` glassmorphism pattern. Admin choropleth extended with `dataLayer` prop for query-volume vs drift-reports toggle.

**Tech Stack:** FastAPI, Supabase Python SDK, reportlab (new dep), Open-Meteo archive API (free, no key), React 19 + Vite + TailwindCSS, react-simple-maps

---

## File Map

```
New backend:
  backend/data/                                  ← create (fixes D6 discrepancy flag)
  backend/supabase/migrations/006_drift_reports.sql
  backend/services/weather_history.py
  backend/services/drift_service.py
  backend/services/pdf_generator.py
  backend/routers/drift_reports.py
  backend/tests/test_weather_history.py
  backend/tests/test_pdf_generator.py
  backend/tests/test_drift_service.py

New frontend:
  frontend/src/hooks/useDriftReports.js
  frontend/src/hooks/useDriftReports.test.js
  frontend/src/components/drift/DriftReportWizard.jsx
  frontend/src/pages/DriftReportPage.jsx
  frontend/e2e/drift.spec.js

Modified:
  backend/requirements.txt                       ← add reportlab
  backend/main.py                                ← register drift_reports router
  backend/routers/admin.py                       ← add GET /admin/drift-reports
  frontend/src/App.jsx                           ← add /drift-report route
  frontend/src/components/layout/Sidebar.jsx    ← add Drift Report nav item
  frontend/src/constants/i18n.js                ← new EN/ES strings
  frontend/src/hooks/useAdmin.js                ← add useDriftReportAdmin
  frontend/src/components/admin/ARCountyMap.jsx ← dataLayer + driftData props
  frontend/src/pages/AdminDashboardPage.jsx     ← Drift Reports tab
```

---

## Task 1: Migration + Data Directory + Bare Router Skeleton

**Files:**
- Create: `backend/data/` (empty directory with `.gitkeep`)
- Create: `backend/supabase/migrations/006_drift_reports.sql`
- Create: `backend/routers/drift_reports.py` (skeleton only)
- Modify: `backend/main.py`

- [ ] **Step 1: Create `backend/data/` directory**

```bash
cd backend
mkdir data
echo "" > data/.gitkeep
```

- [ ] **Step 2: Write migration `006_drift_reports.sql`**

Create `backend/supabase/migrations/006_drift_reports.sql`:

```sql
CREATE TABLE IF NOT EXISTS drift_reports (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  farmer_id              uuid REFERENCES farmer_profiles(id) ON DELETE CASCADE,
  incident_date          date NOT NULL,
  county_fips            text NOT NULL,
  affected_crop          text,
  affected_acres         float,
  suspected_herbicide    text DEFAULT 'dicamba',
  wind_direction         text,
  wind_speed_mph         float,
  temp_at_time_f         float,
  symptoms_description   text,
  neighboring_applicator text,
  photos_attached        bool DEFAULT false,
  weather_json           jsonb,
  aspb_submitted         bool DEFAULT false,
  created_at             timestamptz DEFAULT now()
);

ALTER TABLE drift_reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "farmer sees own drift reports"
  ON drift_reports FOR ALL
  USING (farmer_id = auth.uid());

CREATE POLICY IF NOT EXISTS "admin sees all drift reports"
  ON drift_reports FOR SELECT
  USING (
    auth.uid()::text = ANY(
      string_to_array(current_setting('app.admin_user_ids', true), ',')
    )
  );
```

- [ ] **Step 3: Apply migration to local Supabase**

In the Supabase Dashboard SQL editor (or via CLI), run the contents of `006_drift_reports.sql`.

Verify:
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'drift_reports'
ORDER BY ordinal_position;
```
Expected: 15 columns including `id`, `farmer_id`, `incident_date`, `weather_json`, etc.

- [ ] **Step 4: Write bare router skeleton**

Create `backend/routers/drift_reports.py`:

```python
"""Drift report submission + PDF generation endpoints."""
from fastapi import APIRouter, Depends
from services.auth import get_current_user

router = APIRouter(prefix="/drift-reports", tags=["drift-reports"])


@router.get("")
def list_drift_reports(user: dict = Depends(get_current_user)):
    return []
```

- [ ] **Step 5: Register router in `backend/main.py`**

Add after the existing router imports and `include_router` calls:

```python
# Add to imports at top:
from routers.drift_reports import router as drift_reports_router

# Add after the last include_router line:
app.include_router(drift_reports_router, prefix="/api/v1")
```

- [ ] **Step 6: Verify Checkpoint 1**

Start backend: `cd backend && uvicorn main:app --reload --port 8000`

```bash
# Get a valid token first (login curl from CLAUDE.md)
TOKEN="<your_token>"

curl -s http://localhost:8000/api/v1/drift-reports \
  -H "Authorization: Bearer $TOKEN"
```

Expected: `[]` with HTTP 200.

- [ ] **Step 7: Commit**

```bash
git add backend/data/.gitkeep \
        backend/supabase/migrations/006_drift_reports.sql \
        backend/routers/drift_reports.py \
        backend/main.py
git commit -m "feat: add drift_reports migration, data dir, bare router (F4 task 1)"
```

---

## Task 2: `weather_history.py` — TDD

**Files:**
- Create: `backend/services/weather_history.py`
- Create: `backend/tests/test_weather_history.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_weather_history.py`:

```python
import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _make_open_meteo_mock():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    # 24-hour data: wind=8.0 mph, direction=180deg (South), temp index 12 = 91.4
    temps = [70.0 + i * 0.5 for i in range(24)]  # index 12 = 76.0
    temps[12] = 91.4
    mock_resp.json.return_value = {
        "hourly": {
            "time": [f"2024-07-14T{h:02d}:00" for h in range(24)],
            "windspeed_10m": [8.0] * 24,
            "winddirection_10m": [180.0] * 24,  # 180 deg -> "S"
            "temperature_2m": temps,
        }
    }
    return mock_resp


def test_fetch_historical_weather_success():
    mock_resp = _make_open_meteo_mock()
    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(
            get=AsyncMock(return_value=mock_resp)
        ))
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        weather_mod = importlib.import_module("services.weather_history")
        result = asyncio.run(
            weather_mod.fetch_historical_weather(34.74, -91.83, "2024-07-14")
        )

    assert result["available"] is True
    assert result["source"] == "open-meteo"
    assert result["date"] == "2024-07-14"
    s = result["hourly_summary"]
    assert s["wind_speed_mph_avg"] == 8.0
    assert s["wind_direction_label"] == "S"
    assert s["temp_f_at_noon"] == 91.4


def test_fetch_historical_weather_graceful_fail():
    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(
            get=AsyncMock(side_effect=Exception("network timeout"))
        ))
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        weather_mod = importlib.import_module("services.weather_history")
        result = asyncio.run(
            weather_mod.fetch_historical_weather(34.74, -91.83, "2024-07-14")
        )

    assert result["available"] is False
    assert "hourly_summary" not in result
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend
pytest tests/test_weather_history.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` for `services.weather_history`.

- [ ] **Step 3: Implement `backend/services/weather_history.py`**

```python
"""Open-Meteo archive API client for historical weather at drift incident date."""
import httpx
import logging

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
        wind_speeds = [v for v in hourly.get("windspeed_10m", []) if v is not None]
        wind_dirs = [v for v in hourly.get("winddirection_10m", []) if v is not None]
        temps = hourly.get("temperature_2m", [])

        temp_at_noon = None
        if len(temps) > 12 and temps[12] is not None:
            temp_at_noon = temps[12]
        elif temps:
            temp_at_noon = next((t for t in temps if t is not None), None)

        wind_speed_avg = sum(wind_speeds) / len(wind_speeds) if wind_speeds else None
        wind_dir_avg = sum(wind_dirs) / len(wind_dirs) if wind_dirs else None
        wind_dir_label = _degrees_to_compass(wind_dir_avg) if wind_dir_avg is not None else None

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
            "raw": raw,
        }
    except Exception:
        logger.exception(
            "Open-Meteo historical fetch failed lat=%s lon=%s date=%s", lat, lon, date
        )
        return {"available": False}
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd backend
pytest tests/test_weather_history.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Smoke test against live Open-Meteo**

```bash
cd backend
python -c "
from services.weather_history import fetch_historical_weather
import asyncio
result = asyncio.run(fetch_historical_weather(34.74, -91.83, '2024-07-14'))
print(result['available'], result.get('hourly_summary'))
"
```

Expected: `True {'wind_speed_mph_avg': ..., 'wind_direction_label': '...', 'temp_f_at_noon': ...}`

- [ ] **Step 6: Commit**

```bash
git add backend/services/weather_history.py backend/tests/test_weather_history.py
git commit -m "feat: add Open-Meteo historical weather service with tests (F4 task 2)"
```

---

## Task 3: `drift_service.py` — TDD

**Files:**
- Create: `backend/services/drift_service.py`
- Create: `backend/tests/test_drift_service.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_drift_service.py`:

```python
import importlib
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _fake_client_insert(expected_row_id, inserted_rows_sink):
    class FakeResult:
        data = [{"id": expected_row_id, "farmer_id": "farmer-1"}]

    class FakeTable:
        def insert(self, row):
            inserted_rows_sink.append(row)
            return self
        def execute(self):
            return FakeResult()

    class FakeClient:
        def table(self, _name):
            return FakeTable()

    return FakeClient()


def _fake_client_select(return_data):
    class FakeResult:
        data = return_data

    class FakeChain:
        def select(self, *a): return self
        def eq(self, *a): return self
        def order(self, *a, **kw): return self
        def maybe_single(self): return self
        def gte(self, *a): return self
        def lte(self, *a): return self
        def execute(self): return FakeResult()

    class FakeClient:
        def table(self, _name):
            return FakeChain()

    return FakeClient()


def test_create_report_populates_weather_fields(monkeypatch):
    drift_service = importlib.import_module("services.drift_service")
    inserted = []
    monkeypatch.setattr(
        drift_service, "_get_service_client",
        lambda: _fake_client_insert("uuid-1", inserted),
    )

    data = {
        "incident_date": "2024-07-14",
        "county_fips": "05055",
        "affected_crop": "soybean",
        "affected_acres": 50.0,
        "suspected_herbicide": "dicamba",
        "symptoms_description": "Cupping",
        "neighboring_applicator": None,
        "photos_attached": False,
        "aspb_submitted": False,
    }
    weather = {
        "available": True,
        "hourly_summary": {
            "wind_speed_mph_avg": 8.2,
            "wind_direction_label": "S",
            "temp_f_at_noon": 91.4,
        },
    }

    result = drift_service.create_report("farmer-1", data, weather)

    assert result["id"] == "uuid-1"
    assert len(inserted) == 1
    row = inserted[0]
    assert row["wind_speed_mph"] == 8.2
    assert row["wind_direction"] == "S"
    assert row["temp_at_time_f"] == 91.4
    assert row["farmer_id"] == "farmer-1"


def test_create_report_handles_unavailable_weather(monkeypatch):
    drift_service = importlib.import_module("services.drift_service")
    inserted = []
    monkeypatch.setattr(
        drift_service, "_get_service_client",
        lambda: _fake_client_insert("uuid-2", inserted),
    )

    data = {
        "incident_date": "2024-07-14",
        "county_fips": "05055",
        "affected_crop": None,
        "affected_acres": None,
        "suspected_herbicide": "dicamba",
        "symptoms_description": None,
        "neighboring_applicator": None,
        "photos_attached": False,
        "aspb_submitted": False,
    }

    result = drift_service.create_report("farmer-1", data, {"available": False})

    assert result["id"] == "uuid-2"
    row = inserted[0]
    assert row.get("wind_speed_mph") is None
    assert row.get("weather_json") is None


def test_get_report_returns_none_when_not_found(monkeypatch):
    drift_service = importlib.import_module("services.drift_service")
    monkeypatch.setattr(
        drift_service, "_get_service_client",
        lambda: _fake_client_select(None),
    )

    result = drift_service.get_report("non-existent", "farmer-1")
    assert result is None


def test_list_reports_returns_empty_list(monkeypatch):
    drift_service = importlib.import_module("services.drift_service")
    monkeypatch.setattr(
        drift_service, "_get_service_client",
        lambda: _fake_client_select([]),
    )

    result = drift_service.list_reports("farmer-1")
    assert result == []
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend
pytest tests/test_drift_service.py -v
```

Expected: `ModuleNotFoundError` for `services.drift_service`.

- [ ] **Step 3: Implement `backend/services/drift_service.py`**

```python
"""CRUD for drift_reports table. Uses service-role client (bypasses RLS)."""
from services.user import _get_service_client


def create_report(farmer_id: str, data: dict, weather: dict) -> dict:
    row = {
        "farmer_id": farmer_id,
        "incident_date": str(data["incident_date"]),
        "county_fips": data["county_fips"],
        "affected_crop": data.get("affected_crop"),
        "affected_acres": data.get("affected_acres"),
        "suspected_herbicide": data.get("suspected_herbicide", "dicamba"),
        "symptoms_description": data.get("symptoms_description"),
        "neighboring_applicator": data.get("neighboring_applicator"),
        "photos_attached": data.get("photos_attached", False),
        "aspb_submitted": data.get("aspb_submitted", False),
        "weather_json": weather if weather.get("available") else None,
        "wind_speed_mph": None,
        "wind_direction": None,
        "temp_at_time_f": None,
    }
    if weather.get("available"):
        s = weather.get("hourly_summary", {})
        row["wind_speed_mph"] = s.get("wind_speed_mph_avg")
        row["wind_direction"] = s.get("wind_direction_label")
        row["temp_at_time_f"] = s.get("temp_f_at_noon")

    result = _get_service_client().table("drift_reports").insert(row).execute()
    return result.data[0]


def get_report(report_id: str, farmer_id: str) -> dict | None:
    result = (
        _get_service_client()
        .table("drift_reports")
        .select("*")
        .eq("id", report_id)
        .eq("farmer_id", farmer_id)
        .maybe_single()
        .execute()
    )
    return result.data


def list_reports(farmer_id: str) -> list[dict]:
    result = (
        _get_service_client()
        .table("drift_reports")
        .select("*")
        .eq("farmer_id", farmer_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def list_all_reports(
    county_fips: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    q = _get_service_client().table("drift_reports").select("*")
    if county_fips:
        q = q.eq("county_fips", county_fips)
    if date_from:
        q = q.gte("incident_date", date_from)
    if date_to:
        q = q.lte("incident_date", date_to)
    return q.order("created_at", desc=True).execute().data or []
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd backend
pytest tests/test_drift_service.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/services/drift_service.py backend/tests/test_drift_service.py
git commit -m "feat: add drift_service CRUD with tests (F4 task 3)"
```

---

## Task 4: `pdf_generator.py` — TDD

**Files:**
- Create: `backend/services/pdf_generator.py`
- Create: `backend/tests/test_pdf_generator.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add `reportlab` to `requirements.txt`**

Add this line to `backend/requirements.txt`:

```
reportlab>=4.0.0
```

Install it:

```bash
cd backend
pip install reportlab
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_pdf_generator.py`:

```python
import importlib
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


REPORT_FIXTURE = {
    "id": "aaaabbbb-1234-5678-abcd-111122223333",
    "incident_date": "2024-07-14",
    "county_fips": "05055",
    "affected_crop": "soybean",
    "affected_acres": 50.0,
    "suspected_herbicide": "dicamba",
    "symptoms_description": "Cupping and strapping observed on leaves",
    "neighboring_applicator": "John Doe Farm",
    "weather_json": {
        "available": True,
        "hourly_summary": {
            "wind_speed_mph_avg": 8.2,
            "wind_direction_label": "S",
            "temp_f_at_noon": 91.4,
        },
    },
}

PROFILE_FIXTURE = {
    "full_name": "Test Farmer",
    "email": "testfarmer@example.com",
    "county_fips": "05055",
}


def test_generate_complaint_pdf_returns_valid_pdf_bytes():
    pdf_mod = importlib.import_module("services.pdf_generator")
    pdf_bytes = pdf_mod.generate_complaint_pdf(REPORT_FIXTURE, PROFILE_FIXTURE)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes[:4] == b"%PDF"


def test_generate_complaint_pdf_handles_missing_weather():
    pdf_mod = importlib.import_module("services.pdf_generator")
    report = {**REPORT_FIXTURE, "weather_json": None}
    pdf_bytes = pdf_mod.generate_complaint_pdf(report, {})

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes[:4] == b"%PDF"


def test_generate_complaint_pdf_handles_empty_profile():
    pdf_mod = importlib.import_module("services.pdf_generator")
    pdf_bytes = pdf_mod.generate_complaint_pdf(REPORT_FIXTURE, {})

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"
```

- [ ] **Step 3: Run test — verify it fails**

```bash
cd backend
pytest tests/test_pdf_generator.py -v
```

Expected: `ModuleNotFoundError` for `services.pdf_generator`.

- [ ] **Step 4: Implement `backend/services/pdf_generator.py`**

```python
"""ASPB drift complaint PDF generator using reportlab."""
from io import BytesIO
from datetime import date as date_type

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def generate_complaint_pdf(report: dict, farmer_profile: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )
    styles = getSampleStyleSheet()
    center = ParagraphStyle("center", parent=styles["Heading1"], fontSize=14, alignment=1)
    h2 = styles["Heading2"]
    normal = styles["Normal"]
    story = []

    # Header
    story.append(Paragraph("AR STATE PLANT BOARD", center))
    story.append(Paragraph("DICAMBA DRIFT INCIDENT COMPLAINT", center))
    story.append(
        Paragraph(f"Generated: {date_type.today().strftime('%B %d, %Y')}", normal)
    )
    story.append(HRFlowable(width="100%", thickness=1))
    story.append(Spacer(1, 0.2 * inch))

    # 1 Complainant
    story.append(Paragraph("1. COMPLAINANT INFORMATION", h2))
    story.append(
        _table([
            ["Name:", farmer_profile.get("full_name") or "N/A"],
            ["County:", _county_name(report.get("county_fips", ""))],
            ["Email:", farmer_profile.get("email") or "N/A"],
        ])
    )
    story.append(Spacer(1, 0.2 * inch))

    # 2 Incident
    story.append(Paragraph("2. INCIDENT DETAILS", h2))
    story.append(
        _table([
            ["Incident Date:", str(report.get("incident_date") or "N/A")],
            ["Affected Crop:", report.get("affected_crop") or "N/A"],
            ["Estimated Acres:", str(report.get("affected_acres") or "N/A")],
            ["Suspected Herbicide:", report.get("suspected_herbicide") or "dicamba"],
        ])
    )
    story.append(Spacer(1, 0.2 * inch))

    # 3 Weather
    story.append(Paragraph("3. WEATHER CONDITIONS AT TIME OF INCIDENT", h2))
    wx = report.get("weather_json") or {}
    summary = wx.get("hourly_summary", {}) if wx.get("available") else {}
    if summary:
        weather_rows = [
            ["Wind Speed:", f"{summary.get('wind_speed_mph_avg', 'N/A')} mph"],
            ["Wind Direction:", summary.get("wind_direction_label") or "N/A"],
            ["Temperature:", f"{summary.get('temp_f_at_noon', 'N/A')} °F"],
            ["Data Source:", "NOAA via Open-Meteo Archive API"],
        ]
    else:
        weather_rows = [["Note:", "Weather data unavailable for this incident date."]]
    story.append(_table(weather_rows))
    story.append(Spacer(1, 0.2 * inch))

    # 4 Symptoms
    story.append(Paragraph("4. SYMPTOM DESCRIPTION", h2))
    story.append(
        Paragraph(report.get("symptoms_description") or "No description provided.", normal)
    )
    story.append(Spacer(1, 0.2 * inch))

    # 5 Suspected source
    story.append(Paragraph("5. SUSPECTED SOURCE", h2))
    story.append(
        Paragraph(report.get("neighboring_applicator") or "Not specified.", normal)
    )
    story.append(Spacer(1, 0.2 * inch))

    # 6 Photo checklist
    story.append(Paragraph("6. PHOTO & DOCUMENTATION CHECKLIST", h2))
    for item in [
        "☐  Field damage photographs taken",
        "☐  GPS-tagged photos of affected area",
        "☐  Spray application records requested from applicator",
    ]:
        story.append(Paragraph(item, normal))
    story.append(Spacer(1, 0.2 * inch))

    # Footer
    story.append(HRFlowable(width="100%", thickness=1))
    story.append(Paragraph("SUBMIT THIS COMPLAINT TO:", h2))
    story.append(
        Paragraph("Email: arkansasstateplantboard@agriculture.arkansas.gov", normal)
    )
    story.append(
        Paragraph(
            "Mail: AR State Plant Board, 1 Natural Resources Dr, Little Rock, AR 72205",
            normal,
        )
    )
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph("Generated by AgroAdvisor AR", normal))

    doc.build(story)
    return buffer.getvalue()


def _table(data: list) -> Table:
    t = Table(data, colWidths=[2 * inch, 4 * inch])
    t.setStyle(
        TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    return t


def _county_name(fips: str) -> str:
    from utils.counties import get_county_info
    info = get_county_info(fips)
    return info["county_name"] if info else fips
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd backend
pytest tests/test_pdf_generator.py -v
```

Expected: 3 PASSED.

- [ ] **Step 6: Verify Checkpoint 4 manually**

```bash
cd backend
python -c "
from services.pdf_generator import generate_complaint_pdf
import json

report = {
    'incident_date': '2024-07-14',
    'county_fips': '05055',
    'affected_crop': 'soybean',
    'affected_acres': 50.0,
    'suspected_herbicide': 'dicamba',
    'symptoms_description': 'Cupping and strapping observed',
    'neighboring_applicator': 'Neighbor Farm',
    'weather_json': {
        'available': True,
        'hourly_summary': {
            'wind_speed_mph_avg': 8.2,
            'wind_direction_label': 'S',
            'temp_f_at_noon': 91.4
        }
    }
}
profile = {'full_name': 'Test Farmer', 'email': 'test@test.com'}
pdf = generate_complaint_pdf(report, profile)
with open('/tmp/test_drift.pdf', 'wb') as f:
    f.write(pdf)
print(f'PDF written: {len(pdf)} bytes')
"
```

Open `/tmp/test_drift.pdf` — verify all sections are present and readable.

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt \
        backend/services/pdf_generator.py \
        backend/tests/test_pdf_generator.py
git commit -m "feat: add reportlab PDF generator with tests (F4 task 4)"
```

---

## Task 5: Full `drift_reports` Router + Integration Tests

**Files:**
- Modify: `backend/routers/drift_reports.py` (replace skeleton with full implementation)
- Create: `backend/tests/test_drift_reports_router.py`

- [ ] **Step 1: Write router integration tests**

Create `backend/tests/test_drift_reports_router.py`:

```python
import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

FAKE_USER = {"sub": "farmer-uuid-1"}
FAKE_REPORT = {
    "id": "report-uuid-1",
    "farmer_id": "farmer-uuid-1",
    "incident_date": "2024-07-14",
    "county_fips": "05055",
    "weather_json": None,
}


def test_list_drift_reports_returns_list(monkeypatch):
    router_mod = importlib.import_module("routers.drift_reports")
    monkeypatch.setattr(router_mod, "list_reports", lambda farmer_id: [FAKE_REPORT])

    result = router_mod.list_drift_reports(user=FAKE_USER)
    assert result == [FAKE_REPORT]


def test_get_drift_report_404_when_not_found(monkeypatch):
    router_mod = importlib.import_module("routers.drift_reports")
    monkeypatch.setattr(router_mod, "get_report", lambda rid, fid: None)

    with pytest.raises(HTTPException) as exc_info:
        router_mod.get_drift_report("bad-id", user=FAKE_USER)

    assert exc_info.value.status_code == 404


def test_get_drift_report_returns_report(monkeypatch):
    router_mod = importlib.import_module("routers.drift_reports")
    monkeypatch.setattr(router_mod, "get_report", lambda rid, fid: FAKE_REPORT)

    result = router_mod.get_drift_report("report-uuid-1", user=FAKE_USER)
    assert result["id"] == "report-uuid-1"


def test_create_drift_report_calls_service(monkeypatch):
    router_mod = importlib.import_module("routers.drift_reports")
    monkeypatch.setattr(
        router_mod, "fetch_historical_weather",
        AsyncMock(return_value={"available": False}),
    )
    monkeypatch.setattr(
        router_mod, "create_report",
        lambda farmer_id, data, weather: {**FAKE_REPORT, "farmer_id": farmer_id},
    )

    from routers.drift_reports import DriftReportCreate
    from datetime import date
    body = DriftReportCreate(incident_date=date(2024, 7, 14), county_fips="05055")

    result = asyncio.run(router_mod.create_drift_report(body, user=FAKE_USER))
    assert result["farmer_id"] == "farmer-uuid-1"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd backend
pytest tests/test_drift_reports_router.py -v
```

Expected: failures because router still has skeleton implementation.

- [ ] **Step 3: Replace `backend/routers/drift_reports.py` with full implementation**

```python
"""Drift report submission + PDF generation endpoints."""
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.auth import get_current_user
from services.drift_service import create_report, get_report, list_reports
from services.weather_history import fetch_historical_weather
from services.pdf_generator import generate_complaint_pdf
from services.user import get_profile
from utils.counties import get_county_info

router = APIRouter(prefix="/drift-reports", tags=["drift-reports"])


class DriftReportCreate(BaseModel):
    incident_date: date
    county_fips: str
    affected_crop: Optional[str] = None
    affected_acres: Optional[float] = None
    suspected_herbicide: str = "dicamba"
    symptoms_description: Optional[str] = None
    neighboring_applicator: Optional[str] = None
    photos_attached: bool = False
    aspb_submitted: bool = False


@router.post("", status_code=201)
async def create_drift_report(
    body: DriftReportCreate,
    user: dict = Depends(get_current_user),
):
    county = get_county_info(body.county_fips)
    weather = {"available": False}
    if county:
        weather = await fetch_historical_weather(
            county["lat"], county["lon"], str(body.incident_date)
        )
    report = create_report(user["sub"], body.model_dump(), weather)
    return report


@router.get("")
def list_drift_reports(user: dict = Depends(get_current_user)):
    return list_reports(user["sub"])


@router.get("/{report_id}")
def get_drift_report(report_id: str, user: dict = Depends(get_current_user)):
    report = get_report(report_id, user["sub"])
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/{report_id}/pdf")
def download_drift_report_pdf(
    report_id: str,
    user: dict = Depends(get_current_user),
):
    report = get_report(report_id, user["sub"])
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    profile = get_profile(user["sub"]) or {}
    pdf_bytes = generate_complaint_pdf(report, profile)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=drift_report_{report_id[:8]}.pdf"
            )
        },
    )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd backend
pytest tests/test_drift_reports_router.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Verify Checkpoint 3 with curl**

```bash
TOKEN="<your_token>"

# Create a report
curl -s -X POST http://localhost:8000/api/v1/drift-reports \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_date": "2024-07-14",
    "county_fips": "05055",
    "affected_crop": "soybean",
    "affected_acres": 50,
    "symptoms_description": "Cupping and strapping on leaves"
  }'
```

Expected: JSON with `id` field. Check Supabase dashboard — row visible in `drift_reports`.

```bash
# List reports
curl -s http://localhost:8000/api/v1/drift-reports \
  -H "Authorization: Bearer $TOKEN"
```

Expected: array with 1 report.

- [ ] **Step 6: Run all backend tests together**

```bash
cd backend
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/routers/drift_reports.py \
        backend/tests/test_drift_reports_router.py
git commit -m "feat: full drift_reports router with integration tests (F4 task 5)"
```

---

## Task 6: Admin Endpoint

**Files:**
- Modify: `backend/routers/admin.py`

- [ ] **Step 1: Add admin drift-reports endpoint to `backend/routers/admin.py`**

Add this import at the top of the imports block:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
```

(The `Query` import may already exist — add it only if missing.)

Add this endpoint at the end of `backend/routers/admin.py`:

```python
@router.get("/drift-reports")
def admin_drift_reports(
    county_fips: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    _: dict = Depends(require_admin),
):
    from services.drift_service import list_all_reports
    return list_all_reports(
        county_fips=county_fips,
        date_from=date_from,
        date_to=date_to,
    )
```

- [ ] **Step 2: Verify with curl (admin token required)**

```bash
ADMIN_TOKEN="<your_admin_token>"

curl -s http://localhost:8000/api/v1/admin/drift-reports \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Expected: JSON array of reports.

```bash
# Non-admin should get 403
curl -s http://localhost:8000/api/v1/admin/drift-reports \
  -H "Authorization: Bearer $TOKEN"
```

Expected: `{"detail": "Admin access required."}` with HTTP 403.

- [ ] **Step 3: Commit**

```bash
git add backend/routers/admin.py
git commit -m "feat: add admin drift-reports endpoint (F4 task 6)"
```

---

## Task 7: `useDriftReports.js` Hook + Vitest Test

**Files:**
- Create: `frontend/src/hooks/useDriftReports.js`
- Create: `frontend/src/hooks/useDriftReports.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/useDriftReports.test.js`:

```js
import { describe, expect, it } from 'vitest'
import { getDriftStepErrors } from './useDriftReports'

describe('getDriftStepErrors', () => {
  it('flags missing incident_date on step 1', () => {
    const form = { incident_date: '', county_fips: '05055', affected_crop: 'soybean' }
    const errs = getDriftStepErrors(form, 1)
    expect(errs.incident_date).toBeTruthy()
  })

  it('passes step 1 with valid date and county', () => {
    const form = { incident_date: '2024-07-14', county_fips: '05055' }
    const errs = getDriftStepErrors(form, 1)
    expect(Object.keys(errs)).toHaveLength(0)
  })

  it('flags missing symptoms_description on step 2', () => {
    const form = { symptom_types: [], symptoms_description: '' }
    const errs = getDriftStepErrors(form, 2)
    expect(errs.symptoms).toBeTruthy()
  })

  it('passes step 2 when symptom_types has entries', () => {
    const form = { symptom_types: ['Cupping'], symptoms_description: '' }
    const errs = getDriftStepErrors(form, 2)
    expect(Object.keys(errs)).toHaveLength(0)
  })
})
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd frontend
npm run test -- useDriftReports
```

Expected: test file not found or import error.

- [ ] **Step 3: Implement `frontend/src/hooks/useDriftReports.js`**

```js
import { useState, useCallback } from 'react'
import api from '../lib/api'

export function getDriftStepErrors(form, step) {
  const errs = {}
  if (step === 1) {
    if (!form.incident_date) errs.incident_date = 'Incident date is required'
    if (!form.county_fips) errs.county_fips = 'County is required'
  }
  if (step === 2) {
    if (!form.symptom_types?.length && !form.symptoms_description?.trim()) {
      errs.symptoms = 'Select at least one symptom or provide a description'
    }
  }
  return errs
}

export function useDriftReports() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const createReport = useCallback(async (data) => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.post('/drift-reports', data)
      return res.data
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to submit report'
      setError(msg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const listReports = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get('/drift-reports')
      return res.data
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load reports')
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const downloadPdf = useCallback(async (reportId) => {
    const res = await api.get(`/drift-reports/${reportId}/pdf`, {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `drift_report_${reportId.slice(0, 8)}.pdf`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [])

  return { createReport, listReports, downloadPdf, loading, error }
}
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd frontend
npm run test -- useDriftReports
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useDriftReports.js \
        frontend/src/hooks/useDriftReports.test.js
git commit -m "feat: add useDriftReports hook with validation tests (F4 task 7)"
```

---

## Task 8: `DriftReportWizard.jsx` + `DriftReportPage.jsx`

**Files:**
- Create: `frontend/src/components/drift/DriftReportWizard.jsx`
- Create: `frontend/src/pages/DriftReportPage.jsx`

- [ ] **Step 1: Create `frontend/src/pages/DriftReportPage.jsx`**

```jsx
import DriftReportWizard from '../components/drift/DriftReportWizard'

export default function DriftReportPage() {
  return (
    <div className="flex-1 overflow-y-auto bg-parchment dark:bg-hc-bg">
      <div className="max-w-2xl mx-auto py-8 px-4">
        <DriftReportWizard />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create `frontend/src/components/drift/DriftReportWizard.jsx`**

```jsx
import { useState } from 'react'
import { useLang } from '../../contexts/LangContext'
import { useProfile } from '../../hooks/useProfile'
import { useDriftReports, getDriftStepErrors } from '../../hooks/useDriftReports'
import Alert from '../ui/Alert'
import { COUNTY_OPTIONS } from '../../constants/counties'

const TOTAL_STEPS = 3

const INPUT_CLS =
  'w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-base text-charcoal outline-none transition placeholder:text-gray-400 focus:border-field focus:ring-2 focus:ring-field/20 dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg'
const INPUT_ERR_CLS = 'border-red-400/60 focus:border-red-400/80 focus:ring-red-300/25'
const BTN_PRIMARY_CLS =
  'flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-field px-5 py-3 font-bold text-white shadow transition hover:bg-field/90 focus:outline-none focus:ring-2 focus:ring-field/50 disabled:opacity-60 dark:border-2 dark:border-hc-border dark:bg-hc-accent dark:text-hc-accent-fg'
const BTN_GHOST_CLS =
  'flex-1 rounded-xl border border-gray-200 bg-white px-4 py-3 font-semibold text-gray-600 transition hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-200 dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg'

const SYMPTOM_OPTIONS = ['Cupping', 'Strapping', 'Stunting', 'Discoloration', 'Other']

const STEP_TITLES_EN = ['Incident Basics', 'Symptoms', 'Source & Submit']
const STEP_TITLES_ES = ['Detalles del Incidente', 'Síntomas', 'Fuente y Enviar']

function StepIndicator({ step, titles }) {
  return (
    <ol className="flex items-center justify-between mb-6">
      {titles.map((title, i) => {
        const n = i + 1
        const isCurrent = n === step
        const isDone = n < step
        return (
          <li key={n} className="flex-1 flex items-center">
            <div className="flex flex-col items-center flex-1">
              <span
                aria-current={isCurrent ? 'step' : undefined}
                className={[
                  'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-colors',
                  isCurrent
                    ? 'bg-field text-white border-field'
                    : isDone
                      ? 'bg-field/70 text-white border-field/70'
                      : 'bg-gray-100 text-gray-400 border-gray-200 dark:bg-hc-bg dark:text-hc-fg dark:border-hc-border',
                ].join(' ')}
              >
                {isDone ? '✓' : n}
              </span>
              <span className="text-[10px] text-gray-500 mt-1 text-center leading-tight dark:text-hc-fg">
                {title}
              </span>
            </div>
            {i < titles.length - 1 && (
              <div className={`flex-1 h-px mx-1 ${isDone ? 'bg-field/50' : 'bg-gray-200'}`} />
            )}
          </li>
        )
      })}
    </ol>
  )
}

function FieldError({ msg }) {
  if (!msg) return null
  return <p className="text-xs text-red-500 mt-1">{msg}</p>
}

export default function DriftReportWizard() {
  const { lang } = useLang()
  const { profile } = useProfile()
  const { createReport, downloadPdf, loading, error } = useDriftReports()

  const [step, setStep] = useState(1)
  const [errs, setErrs] = useState({})
  const [submitted, setSubmitted] = useState(null)

  const [form, setForm] = useState({
    incident_date: '',
    county_fips: profile?.county_fips || '',
    affected_crop: '',
    affected_acres: '',
    symptom_types: [],
    symptoms_description: '',
    neighboring_applicator: '',
    photos_field: false,
    photos_gps: false,
    photos_records: false,
    aspb_submitted: false,
  })

  const stepTitles = lang === 'es' ? STEP_TITLES_ES : STEP_TITLES_EN

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  function toggleSymptom(s) {
    setForm((f) => ({
      ...f,
      symptom_types: f.symptom_types.includes(s)
        ? f.symptom_types.filter((x) => x !== s)
        : [...f.symptom_types, s],
    }))
  }

  function handleNext() {
    const stepErrs = getDriftStepErrors(form, step)
    if (Object.keys(stepErrs).length > 0) {
      setErrs(stepErrs)
      return
    }
    setErrs({})
    setStep((s) => s + 1)
  }

  async function handleSubmit() {
    const stepErrs = getDriftStepErrors(form, 3)
    if (Object.keys(stepErrs).length > 0) {
      setErrs(stepErrs)
      return
    }
    setErrs({})

    const symptomsText = [
      form.symptom_types.join(', '),
      form.symptoms_description.trim(),
    ]
      .filter(Boolean)
      .join(': ')

    try {
      const report = await createReport({
        incident_date: form.incident_date,
        county_fips: form.county_fips || profile?.county_fips,
        affected_crop: form.affected_crop || null,
        affected_acres: form.affected_acres ? parseFloat(form.affected_acres) : null,
        symptoms_description: symptomsText || null,
        neighboring_applicator: form.neighboring_applicator.trim() || null,
        photos_attached: form.photos_field || form.photos_gps || form.photos_records,
        aspb_submitted: form.aspb_submitted,
      })
      setSubmitted(report)
    } catch {
      // error shown via hook's error state
    }
  }

  if (submitted) {
    return (
      <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm dark:bg-hc-surface dark:border-hc-border">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-field/10 flex items-center justify-center text-field text-xl">✓</div>
          <div>
            <p className="font-semibold text-charcoal dark:text-hc-fg">
              {lang === 'es' ? 'Reporte enviado' : 'Report submitted'}
            </p>
            <p className="text-xs text-gray-500 dark:text-hc-fg">
              {lang === 'es' ? 'ID de reporte:' : 'Report ID:'} {submitted.id?.slice(0, 8)}
            </p>
          </div>
        </div>

        {submitted.wind_speed_mph != null && (
          <div className="bg-gray-50 rounded-xl p-4 mb-4 text-sm dark:bg-hc-bg">
            <p className="font-semibold text-charcoal dark:text-hc-fg mb-2">
              {lang === 'es' ? 'Condiciones meteorológicas auto-llenadas:' : 'Auto-filled weather conditions:'}
            </p>
            <p className="text-gray-600 dark:text-hc-fg">
              Wind: {submitted.wind_speed_mph} mph {submitted.wind_direction} · Temp: {submitted.temp_at_time_f}°F
            </p>
          </div>
        )}

        <button
          onClick={() => downloadPdf(submitted.id)}
          className={BTN_PRIMARY_CLS + ' w-full mt-2'}
        >
          {lang === 'es' ? 'Descargar PDF de queja ASPB' : 'Download ASPB Complaint PDF'}
        </button>
        <button
          onClick={() => { setSubmitted(null); setStep(1); setForm(f => ({ ...f, incident_date: '', affected_crop: '', affected_acres: '', symptom_types: [], symptoms_description: '', neighboring_applicator: '' })) }}
          className={BTN_GHOST_CLS + ' w-full mt-2'}
        >
          {lang === 'es' ? 'Nuevo reporte' : 'File another report'}
        </button>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm dark:bg-hc-surface dark:border-hc-border">
      <h1 className="text-lg font-bold text-charcoal dark:text-hc-fg mb-1">
        {lang === 'es' ? 'Reporte de Deriva de Dicamba' : 'Dicamba Drift Report'}
      </h1>
      <p className="text-sm text-gray-500 dark:text-hc-fg mb-6">
        {lang === 'es'
          ? 'Documente un incidente de deriva y genere una queja para el ASPB.'
          : 'Document a drift incident and generate an ASPB complaint package.'}
      </p>

      <StepIndicator step={step} titles={stepTitles} />

      {error && <Alert variant="error" className="mb-4">{error}</Alert>}

      {/* Step 1 */}
      {step === 1 && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-1">
              {lang === 'es' ? 'Fecha del incidente *' : 'Incident date *'}
            </label>
            <input
              type="date"
              max={new Date().toISOString().split('T')[0]}
              value={form.incident_date}
              onChange={(e) => set('incident_date', e.target.value)}
              className={`${INPUT_CLS} ${errs.incident_date ? INPUT_ERR_CLS : ''}`}
            />
            <FieldError msg={errs.incident_date} />
          </div>

          <div>
            <label className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-1">
              {lang === 'es' ? 'Cultivo afectado' : 'Affected crop'}
            </label>
            <select
              value={form.affected_crop}
              onChange={(e) => set('affected_crop', e.target.value)}
              className={INPUT_CLS}
            >
              <option value="">{lang === 'es' ? 'Seleccionar...' : 'Select...'}</option>
              <option value="rice">{lang === 'es' ? 'Arroz' : 'Rice'}</option>
              <option value="soybean">{lang === 'es' ? 'Soja' : 'Soybean'}</option>
              <option value="other">{lang === 'es' ? 'Otro' : 'Other'}</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-1">
              {lang === 'es' ? 'Acres estimados' : 'Estimated acres'}
            </label>
            <input
              type="number"
              min="0"
              step="0.1"
              value={form.affected_acres}
              onChange={(e) => set('affected_acres', e.target.value)}
              placeholder="0.0"
              className={INPUT_CLS}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-1">
              {lang === 'es' ? 'Condado *' : 'County *'}
            </label>
            <select
              value={form.county_fips}
              onChange={(e) => set('county_fips', e.target.value)}
              className={`${INPUT_CLS} ${errs.county_fips ? INPUT_ERR_CLS : ''}`}
            >
              <option value="">{lang === 'es' ? 'Seleccionar condado...' : 'Select county...'}</option>
              {COUNTY_OPTIONS.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
            <FieldError msg={errs.county_fips} />
          </div>
        </div>
      )}

      {/* Step 2 */}
      {step === 2 && (
        <div className="space-y-4">
          <div>
            <p className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-2">
              {lang === 'es' ? 'Tipo de síntomas observados' : 'Observed symptom types'}
            </p>
            <div className="grid grid-cols-2 gap-2">
              {SYMPTOM_OPTIONS.map((s) => (
                <label key={s} className="flex items-center gap-2 text-sm text-charcoal dark:text-hc-fg cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.symptom_types.includes(s)}
                    onChange={() => toggleSymptom(s)}
                    className="rounded accent-field"
                  />
                  {lang === 'es' ? {
                    Cupping: 'Enroscamiento',
                    Strapping: 'Estrechamiento',
                    Stunting: 'Atrofia',
                    Discoloration: 'Decoloración',
                    Other: 'Otro',
                  }[s] : s}
                </label>
              ))}
            </div>
            <FieldError msg={errs.symptoms} />
          </div>

          <div>
            <label className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-1">
              {lang === 'es' ? 'Descripción de síntomas' : 'Symptom description'}
            </label>
            <textarea
              rows={4}
              value={form.symptoms_description}
              onChange={(e) => set('symptoms_description', e.target.value)}
              placeholder={lang === 'es'
                ? 'Describa los síntomas observados en detalle...'
                : 'Describe the symptoms you observed in detail...'}
              className={`${INPUT_CLS} resize-none`}
            />
          </div>

          <div className="bg-amber-50 rounded-xl p-4 text-sm text-amber-800 dark:bg-hc-bg dark:text-hc-fg">
            {lang === 'es'
              ? 'Las condiciones meteorológicas (viento, temperatura) se agregarán automáticamente al enviar mediante datos históricos de NOAA.'
              : 'Weather conditions (wind, temperature) will be auto-filled on submit using NOAA historical data.'}
          </div>
        </div>
      )}

      {/* Step 3 */}
      {step === 3 && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-1">
              {lang === 'es' ? 'Aplicador sospechoso (opcional)' : 'Suspected applicator (optional)'}
            </label>
            <input
              type="text"
              value={form.neighboring_applicator}
              onChange={(e) => set('neighboring_applicator', e.target.value)}
              placeholder={lang === 'es' ? 'Nombre del agricultor/empresa...' : 'Farmer or company name...'}
              className={INPUT_CLS}
            />
          </div>

          <div>
            <p className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-2">
              {lang === 'es' ? 'Lista de documentación fotográfica (recordatorio)' : 'Photo documentation checklist (reminder)'}
            </p>
            {[
              ['photos_field', lang === 'es' ? 'Fotografías del daño en el campo tomadas' : 'Field damage photographs taken'],
              ['photos_gps', lang === 'es' ? 'Fotos con GPS del área afectada' : 'GPS-tagged photos of affected area'],
              ['photos_records', lang === 'es' ? 'Registros de aplicación solicitados' : 'Spray application records requested'],
            ].map(([field, label]) => (
              <label key={field} className="flex items-center gap-2 text-sm text-charcoal dark:text-hc-fg cursor-pointer mb-1">
                <input
                  type="checkbox"
                  checked={form[field]}
                  onChange={(e) => set(field, e.target.checked)}
                  className="rounded accent-field"
                />
                {label}
              </label>
            ))}
          </div>

          <label className="flex items-center gap-2 text-sm text-charcoal dark:text-hc-fg cursor-pointer">
            <input
              type="checkbox"
              checked={form.aspb_submitted}
              onChange={(e) => set('aspb_submitted', e.target.checked)}
              className="rounded accent-field"
            />
            {lang === 'es'
              ? 'Ya envié esta queja al ASPB'
              : 'I have already submitted this complaint to ASPB'}
          </label>
        </div>
      )}

      {/* Navigation */}
      <div className="flex gap-3 mt-8">
        {step > 1 && (
          <button
            type="button"
            onClick={() => { setErrs({}); setStep((s) => s - 1) }}
            className={BTN_GHOST_CLS}
          >
            {lang === 'es' ? 'Atrás' : 'Back'}
          </button>
        )}
        {step < TOTAL_STEPS ? (
          <button type="button" onClick={handleNext} className={BTN_PRIMARY_CLS}>
            {lang === 'es' ? 'Siguiente' : 'Next'}
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={loading}
            className={BTN_PRIMARY_CLS}
          >
            {loading
              ? (lang === 'es' ? 'Enviando...' : 'Submitting...')
              : (lang === 'es' ? 'Enviar reporte' : 'Submit report')}
          </button>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/DriftReportPage.jsx \
        frontend/src/components/drift/DriftReportWizard.jsx
git commit -m "feat: add DriftReportWizard 3-step form + DriftReportPage (F4 task 8)"
```

---

## Task 9: App Route + Sidebar Nav + i18n

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/layout/Sidebar.jsx`
- Modify: `frontend/src/constants/i18n.js`

- [ ] **Step 1: Add i18n strings to `frontend/src/constants/i18n.js`**

In the `en:` object, add after any existing nav-related key (e.g., after `profile: 'My Profile'`):

```js
driftReportNav: 'Drift Report',
driftReportTitle: 'Dicamba Drift Report',
```

In the `es:` object, add the same keys:

```js
driftReportNav: 'Reporte de Deriva',
driftReportTitle: 'Reporte de Deriva de Dicamba',
```

- [ ] **Step 2: Add `/drift-report` route to `frontend/src/App.jsx`**

Add the import near the top with other page imports:

```jsx
import DriftReportPage from './pages/DriftReportPage'
```

Add the route inside the protected `<Route element={<ProtectedRoute>...}>` block, after the profile route:

```jsx
<Route path="/drift-report" element={<DriftReportPage />} />
```

- [ ] **Step 3: Add Drift Report nav item to `frontend/src/components/layout/Sidebar.jsx`**

In the "Bottom navigation items" `<div>`, add this item **before** the Profile/Settings `SidebarNavItem`:

```jsx
<SidebarNavItem to="/drift-report" onClick={onClose}>
  <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
  </svg>
  {t.driftReportNav}
</SidebarNavItem>
```

- [ ] **Step 4: Verify Checkpoint 6 manually**

Start dev server: `cd frontend && npm run dev`

1. Navigate to `/login`, log in.
2. Confirm "Drift Report" nav item appears in sidebar.
3. Click it → `/drift-report` renders the wizard.
4. Toggle EN/ES → nav item label switches to "Reporte de Deriva".

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx \
        frontend/src/components/layout/Sidebar.jsx \
        frontend/src/constants/i18n.js
git commit -m "feat: add /drift-report route, sidebar nav item, i18n strings (F4 task 9)"
```

---

## Task 10: Admin Dashboard — Drift Tab + Choropleth Second Layer

**Files:**
- Modify: `frontend/src/hooks/useAdmin.js`
- Modify: `frontend/src/components/admin/ARCountyMap.jsx`
- Modify: `frontend/src/pages/AdminDashboardPage.jsx`

- [ ] **Step 1: Add `useDriftReportAdmin` to `frontend/src/hooks/useAdmin.js`**

Append this export at the end of the file:

```js
export function useDriftReportAdmin({ dateFrom = '', dateTo = '' } = {}) {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await api.get('/admin/drift-reports', {
        params: {
          ...(dateFrom && { date_from: dateFrom }),
          ...(dateTo && { date_to: dateTo }),
        },
      })
      setReports(data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load drift reports')
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo])

  useEffect(() => { load() }, [load])

  return { reports, loading, error, refresh: load }
}
```

- [ ] **Step 2: Update `frontend/src/components/admin/ARCountyMap.jsx`**

Replace the entire file content with:

```jsx
import { useState } from 'react'
import { ComposableMap, Geographies, Geography } from 'react-simple-maps'

const GEO_URL = 'https://cdn.jsdelivr.net/npm/us-atlas@3/counties-10m.json'

function countyColor(count, maxCount) {
  if (count === 0) return '#EEF2EF'
  const t = Math.sqrt(count / maxCount)
  const r = Math.round(240 + (45 - 240) * t)
  const g = Math.round(242 + (106 - 242) * t)
  const b = Math.round(240 + (79 - 240) * t)
  return `rgb(${r},${g},${b})`
}

function driftCountyColor(count, maxCount) {
  if (count === 0) return '#EEF2EF'
  const t = Math.sqrt(count / maxCount)
  const r = Math.round(240 + (233 - 240) * t)
  const g = Math.round(242 + (162 - 242) * t)
  const b = Math.round(240 + (40 - 240) * t)
  return `rgb(${r},${g},${b})`
}

export default function ARCountyMap({
  countyData = [],
  dataLayer = 'queries',
  driftData = {},
}) {
  const [tooltip, setTooltip] = useState(null)

  const queryCountByFips = {}
  let queryMaxCount = 1
  countyData.forEach(({ county_fips, count }) => {
    queryCountByFips[county_fips] = count
    if (count > queryMaxCount) queryMaxCount = count
  })

  const driftValues = Object.values(driftData)
  const driftMaxCount = driftValues.length > 0 ? Math.max(1, ...driftValues) : 1

  function getFips(geoId) {
    return String(geoId).padStart(5, '0')
  }

  function getColor(fips) {
    if (dataLayer === 'drift') {
      return driftCountyColor(driftData[fips] || 0, driftMaxCount)
    }
    return countyColor(queryCountByFips[fips] || 0, queryMaxCount)
  }

  function getCount(fips) {
    return dataLayer === 'drift'
      ? (driftData[fips] || 0)
      : (queryCountByFips[fips] || 0)
  }

  const unit = dataLayer === 'drift' ? 'reports' : 'queries'
  const gradientEnd = dataLayer === 'drift' ? '#E9A228' : '#2D6A4F'
  const displayMax = dataLayer === 'drift' ? driftMaxCount : queryMaxCount

  return (
    <div className="relative w-full" style={{ minHeight: 220 }}>
      <ComposableMap
        projection="geoAlbersUsa"
        projectionConfig={{ scale: 4800, center: [-92.4, 34.75] }}
        style={{ width: '100%', height: 'auto' }}
      >
        <Geographies geography={GEO_URL}>
          {({ geographies }) =>
            geographies
              .filter((geo) => getFips(geo.id).startsWith('05'))
              .map((geo) => {
                const fips = getFips(geo.id)
                const count = getCount(fips)
                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={getColor(fips)}
                    stroke="#ffffff"
                    strokeWidth={0.8}
                    onMouseEnter={() => {
                      const name = geo.properties?.name || fips
                      setTooltip({ name, count })
                    }}
                    onMouseLeave={() => setTooltip(null)}
                    style={{
                      default: { outline: 'none' },
                      hover: { outline: 'none', opacity: 0.75, cursor: 'pointer' },
                      pressed: { outline: 'none' },
                    }}
                  />
                )
              })
          }
        </Geographies>
      </ComposableMap>

      {tooltip && (
        <div className="absolute top-2 right-2 bg-white border border-gray-200 rounded-md px-3 py-1.5 text-xs shadow-sm pointer-events-none dark:bg-hc-surface dark:border-hc-border dark:text-hc-fg">
          <span className="font-semibold">{tooltip.name} County</span>
          <span className="text-gray-500 dark:text-hc-fg ml-2">
            {tooltip.count} {unit}
          </span>
        </div>
      )}

      <div className="flex items-center gap-2 mt-2 text-xs text-gray-500 dark:text-hc-fg px-1">
        <span>0</span>
        <div
          className="flex-1 h-2 rounded"
          style={{
            background: `linear-gradient(to right, #EEF2EF, ${gradientEnd})`,
          }}
        />
        <span>{displayMax}</span>
        <span className="ml-1">{unit}</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Update `frontend/src/pages/AdminDashboardPage.jsx`**

`AdminDashboardPage.jsx` currently has no React import. Add it at the top of the file (line 1):

```jsx
import { useState } from 'react'
```

Add `useDriftReportAdmin` to the existing import line for `useAdmin`:

```jsx
import { useAdminMetrics, useDriftReportAdmin } from '../hooks/useAdmin'
```

Add state for the active tab and drift filters at the top of `AdminDashboardPage`:

```jsx
const [adminTab, setAdminTab] = useState('overview')
const [mapLayer, setMapLayer] = useState('queries')
const [driftDateFrom, setDriftDateFrom] = useState('')
const [driftDateTo, setDriftDateTo] = useState('')
const [driftPage, setDriftPage] = useState(0)
const DRIFT_PAGE_SIZE = 20

const { reports: driftReports, loading: driftLoading } = useDriftReportAdmin({
  dateFrom: driftDateFrom,
  dateTo: driftDateTo,
})
```

Add a tab bar right before the existing first `SectionCard` (after the KPI grid):

```jsx
{/* Tab bar */}
<div className="flex gap-2 border-b border-gray-100 dark:border-hc-border pb-0">
  {['overview', 'drift'].map((tab) => (
    <button
      key={tab}
      onClick={() => setAdminTab(tab)}
      className={[
        'px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px',
        adminTab === tab
          ? 'border-field text-field dark:border-hc-accent dark:text-hc-accent'
          : 'border-transparent text-gray-500 hover:text-charcoal dark:text-hc-fg',
      ].join(' ')}
    >
      {tab === 'overview' ? 'Overview' : 'Drift Reports'}
    </button>
  ))}
</div>
```

Wrap all existing content after the tab bar in `{adminTab === 'overview' && (...)}`.

After that block, add:

```jsx
{adminTab === 'drift' && (
  <div className="space-y-4">
    {/* Choropleth toggle + map */}
    <SectionCard title="County Drift Reports">
      <div className="flex gap-2 mb-3">
        {['queries', 'drift'].map((layer) => (
          <button
            key={layer}
            onClick={() => setMapLayer(layer)}
            className={[
              'px-3 py-1 rounded-full text-xs font-medium border transition',
              mapLayer === layer
                ? 'bg-field text-white border-field dark:bg-hc-accent dark:border-hc-border'
                : 'bg-white text-gray-500 border-gray-200 hover:border-gray-300 dark:bg-hc-bg dark:text-hc-fg dark:border-hc-border',
            ].join(' ')}
          >
            {layer === 'queries' ? 'Query Volume' : 'Drift Reports'}
          </button>
        ))}
      </div>
      <ARCountyMap
        countyData={metrics?.county_query_volume || []}
        dataLayer={mapLayer}
        driftData={driftReports.reduce((acc, r) => {
          acc[r.county_fips] = (acc[r.county_fips] || 0) + 1
          return acc
        }, {})}
      />
    </SectionCard>

    {/* Date filter */}
    <SectionCard title="Filter Reports">
      <div className="flex gap-3 flex-wrap">
        <div>
          <label className="text-xs text-gray-500 dark:text-hc-fg block mb-1">From</label>
          <input
            type="date"
            value={driftDateFrom}
            onChange={(e) => { setDriftDateFrom(e.target.value); setDriftPage(0) }}
            className="rounded-lg border border-gray-200 px-3 py-2 text-sm dark:bg-hc-bg dark:border-hc-border dark:text-hc-fg"
          />
        </div>
        <div>
          <label className="text-xs text-gray-500 dark:text-hc-fg block mb-1">To</label>
          <input
            type="date"
            value={driftDateTo}
            onChange={(e) => { setDriftDateTo(e.target.value); setDriftPage(0) }}
            className="rounded-lg border border-gray-200 px-3 py-2 text-sm dark:bg-hc-bg dark:border-hc-border dark:text-hc-fg"
          />
        </div>
        {(driftDateFrom || driftDateTo) && (
          <button
            onClick={() => { setDriftDateFrom(''); setDriftDateTo(''); setDriftPage(0) }}
            className="self-end text-xs text-gray-400 hover:text-gray-600 pb-2"
          >
            Clear
          </button>
        )}
      </div>
    </SectionCard>

    {/* Report list */}
    <SectionCard title={`Drift Reports (${driftReports.length})`}>
      {driftLoading ? (
        <p className="text-sm text-gray-500">Loading...</p>
      ) : driftReports.length === 0 ? (
        <p className="text-sm text-gray-500">No drift reports yet.</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-100 dark:border-hc-border">
                  <th className="pb-2 font-medium">County</th>
                  <th className="pb-2 font-medium">Date</th>
                  <th className="pb-2 font-medium">Crop</th>
                  <th className="pb-2 font-medium">Symptoms</th>
                  <th className="pb-2 font-medium">ASPB Filed</th>
                </tr>
              </thead>
              <tbody>
                {driftReports
                  .slice(driftPage * DRIFT_PAGE_SIZE, (driftPage + 1) * DRIFT_PAGE_SIZE)
                  .map((r) => (
                    <tr key={r.id} className="border-b border-gray-50 dark:border-hc-border">
                      <td className="py-2 text-charcoal dark:text-hc-fg">{r.county_fips}</td>
                      <td className="py-2 text-charcoal dark:text-hc-fg">{r.incident_date}</td>
                      <td className="py-2 text-charcoal dark:text-hc-fg">{r.affected_crop || '—'}</td>
                      <td className="py-2 text-gray-500 dark:text-hc-fg max-w-[200px] truncate">
                        {r.symptoms_description?.slice(0, 60) || '—'}
                      </td>
                      <td className="py-2 text-charcoal dark:text-hc-fg">
                        {r.aspb_submitted ? '✓' : '—'}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          {driftReports.length > DRIFT_PAGE_SIZE && (
            <div className="flex gap-2 mt-3 justify-end">
              <button
                disabled={driftPage === 0}
                onClick={() => setDriftPage((p) => p - 1)}
                className="text-xs px-3 py-1 rounded border border-gray-200 disabled:opacity-40"
              >
                Prev
              </button>
              <span className="text-xs text-gray-500 self-center">
                {driftPage + 1} / {Math.ceil(driftReports.length / DRIFT_PAGE_SIZE)}
              </span>
              <button
                disabled={(driftPage + 1) * DRIFT_PAGE_SIZE >= driftReports.length}
                onClick={() => setDriftPage((p) => p + 1)}
                className="text-xs px-3 py-1 rounded border border-gray-200 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </SectionCard>
  </div>
)}
```

Also add `useState` to the existing React import if not already there (it should already be used, check the import line).

- [ ] **Step 4: Verify Checkpoint 7 manually**

With dev server + backend running, as an admin user:

1. Navigate to `/admin`
2. Verify "Overview" and "Drift Reports" tabs appear
3. Click "Drift Reports" tab
4. Verify map renders with "Query Volume" / "Drift Reports" toggle
5. Click "Drift Reports" toggle — map recolors to amber gradient
6. Verify date filter inputs render and can be filled
7. If drift reports exist, verify table shows them

- [ ] **Step 5: Run lint**

```bash
cd frontend
npm run lint
```

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useAdmin.js \
        frontend/src/components/admin/ARCountyMap.jsx \
        frontend/src/pages/AdminDashboardPage.jsx
git commit -m "feat: admin drift reports tab, choropleth second layer, useDriftReportAdmin (F4 task 10)"
```

---

## Task 11: Playwright E2E Test

**Files:**
- Create: `frontend/e2e/drift.spec.js`

- [ ] **Step 1: Create `frontend/e2e/drift.spec.js`**

```js
import { test, expect } from '@playwright/test'
import { loginAs, mockProfileBackend, EMAIL, PASSWORD } from './helpers.js'

const MOCK_REPORT_ID = 'aaaabbbb-1234-5678-abcd-111122223333'
const MOCK_REPORT = {
  id: MOCK_REPORT_ID,
  farmer_id: 'e2e-user',
  incident_date: '2024-07-14',
  county_fips: '05055',
  affected_crop: 'soybean',
  affected_acres: 50,
  symptoms_description: 'Cupping, Strapping',
  neighboring_applicator: null,
  wind_speed_mph: 8.2,
  wind_direction: 'S',
  temp_at_time_f: 91.4,
  weather_json: {
    available: true,
    hourly_summary: {
      wind_speed_mph_avg: 8.2,
      wind_direction_label: 'S',
      temp_f_at_noon: 91.4,
    },
  },
  aspb_submitted: false,
  photos_attached: false,
  created_at: '2024-07-14T12:00:00Z',
}

async function mockDriftBackend(page) {
  await page.route('**/api/v1/drift-reports', async (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_REPORT),
      })
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([MOCK_REPORT]),
    })
  })

  await page.route(`**/api/v1/drift-reports/${MOCK_REPORT_ID}/pdf`, async (route) => {
    // Return a minimal valid PDF (just the header bytes)
    const pdfBytes = Buffer.from('%PDF-1.4 mock pdf content')
    return route.fulfill({
      status: 200,
      contentType: 'application/pdf',
      body: pdfBytes,
      headers: {
        'Content-Disposition': `attachment; filename=drift_report_${MOCK_REPORT_ID.slice(0, 8)}.pdf`,
      },
    })
  })
}

test('drift report wizard: complete 3 steps and submit', async ({ page }) => {
  await mockProfileBackend(page)
  await mockDriftBackend(page)
  await loginAs(page, EMAIL, PASSWORD)

  // Navigate to drift report page via sidebar
  await page.waitForURL('/')
  await page.getByRole('link', { name: /drift report/i }).click()
  await page.waitForURL('/drift-report')

  // Step 1: Incident basics
  await expect(page.getByText(/incident/i).first()).toBeVisible()
  await page.locator('input[type="date"]').fill('2024-07-14')
  await page.locator('select').first().selectOption('soybean')
  await page.locator('input[type="number"]').fill('50')
  await page.getByRole('button', { name: /next/i }).click()

  // Step 2: Symptoms
  await page.getByLabel(/cupping/i).check()
  await page.getByRole('button', { name: /next/i }).click()

  // Step 3: Source & submit
  await expect(page.getByText(/source|applicator/i).first()).toBeVisible()
  await page.getByRole('button', { name: /submit report/i }).click()

  // Success card
  await expect(page.getByText(/report submitted|reporte enviado/i)).toBeVisible({
    timeout: 10000,
  })
  await expect(page.getByText(/8.2 mph/i)).toBeVisible()
})

test('drift report PDF download button appears on success', async ({ page }) => {
  await mockProfileBackend(page)
  await mockDriftBackend(page)
  await loginAs(page, EMAIL, PASSWORD)

  await page.goto('/drift-report')

  await page.locator('input[type="date"]').fill('2024-07-14')
  await page.getByRole('button', { name: /next/i }).click()
  await page.getByLabel(/cupping/i).check()
  await page.getByRole('button', { name: /next/i }).click()
  await page.getByRole('button', { name: /submit report/i }).click()

  await expect(page.getByRole('button', { name: /download.*pdf|descargar.*pdf/i })).toBeVisible({
    timeout: 10000,
  })
})

test('drift report nav item appears in sidebar for authenticated user', async ({ page }) => {
  await mockProfileBackend(page)
  await loginAs(page, EMAIL, PASSWORD)
  await expect(page.getByRole('link', { name: /drift report/i })).toBeVisible()
})
```

- [ ] **Step 2: Verify Checkpoint 8 — run E2E tests**

```bash
cd frontend
# Ensure both servers are running: backend on :8000, frontend on :5173
npx playwright test e2e/drift.spec.js --headed
```

Expected: 3 tests pass. (Use `--headed` to watch browser on first run; remove for CI.)

- [ ] **Step 3: Run full test suite**

```bash
# Backend
cd backend && pytest tests/ -v

# Frontend
cd frontend && npm run test && npx playwright test e2e/drift.spec.js
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/drift.spec.js
git commit -m "test: add Playwright E2E tests for drift report wizard (F4 task 11)"
```

---

## Final Checkpoint: Full Suite + Status Bar Update

- [ ] **Run all backend tests**

```bash
cd backend && pytest tests/ -v
```

- [ ] **Run frontend lint + unit tests**

```bash
cd frontend && npm run lint && npm run test
```

- [ ] **Run all Playwright tests**

```bash
cd frontend && npx playwright test
```

- [ ] **Update `docs/status-bar.md`**

Once F4 is deployed to prod (Vercel + Railway), check off:

> T1 | F4 · Dicamba drift tool deployed (wizard + PDF, prod URL live) | Real users / data | +3% | ☑

Recalculate production-readiness % (71% + 3% = 74%), update bars, update "Last updated" date.

- [ ] **Final commit**

```bash
git add docs/status-bar.md
git commit -m "chore: update status-bar for F4 completion"
```
