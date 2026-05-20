# F4 · Dicamba Drift Documentation Tool — Design Spec

**Date:** 2026-05-20
**Feature:** F4 from `Tier1_Implementation_Plan (Addition).md`
**Status:** Approved for implementation

---

## Problem

Arkansas generated 1,000+ dicamba drift complaints in 2017. No digital tool exists to help AR farmers document a drift incident and generate a properly formatted AR State Plant Board (ASPB) complaint package. This feature closes that gap with a structured wizard + auto-populated weather data + PDF generator.

NIW mapping: Prong 1 (public safety, AR community welfare) + Prong 3 (time-sensitive safety benefit, Dhanasar favorable factor).

---

## Decisions Made

| Question | Decision |
|---|---|
| Historical weather source | Open-Meteo archive API — free, no key, JSON REST |
| PDF format | Structured complaint letter (reportlab) — not fillable form |
| Nav placement | Sidebar nav item `/drift-report` — standalone, no chat pre-fill |
| Admin tab scope | Full spec: choropleth second layer + date filter + list view |
| Architecture | Service-split (Approach B) |

---

## Architecture

### New Backend Files

```
backend/data/                                     ← create now (fixes D6 discrepancy flag)
backend/supabase/migrations/006_drift_reports.sql
backend/services/weather_history.py               ← Open-Meteo client only
backend/services/drift_service.py                 ← DB CRUD
backend/services/pdf_generator.py                 ← reportlab PDF only
backend/routers/drift_reports.py                  ← thin router
```

### New Frontend Files

```
frontend/src/pages/DriftReportPage.jsx
frontend/src/components/drift/DriftReportWizard.jsx
frontend/src/hooks/useDriftReports.js
```

### Modified Files

```
backend/main.py                                   ← register router
frontend/src/App.jsx                              ← /drift-report route
frontend/src/components/layout/Sidebar.jsx        ← nav item
frontend/src/constants/i18n.js                    ← new EN/ES strings
frontend/src/pages/AdminDashboardPage.jsx         ← drift tab + choropleth toggle
frontend/src/components/admin/ARCountyMap.jsx     ← dataLayer prop
frontend/src/hooks/useAdmin.js                    ← useDriftReportAdmin()
```

### API Endpoints

```
POST   /api/v1/drift-reports           → create report + auto-fetch weather
GET    /api/v1/drift-reports           → list current user's reports
GET    /api/v1/drift-reports/{id}      → single report
GET    /api/v1/drift-reports/{id}/pdf  → generate + stream PDF (synchronous)
GET    /api/v1/admin/drift-reports     → admin: all reports + county counts
```

All endpoints protected by existing JWT dependency. Admin endpoint uses existing `require_admin`.

---

## Data Model

### `006_drift_reports.sql`

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

CREATE POLICY "farmer sees own reports"
  ON drift_reports FOR ALL
  USING (farmer_id = auth.uid());

CREATE POLICY "admin sees all reports"
  ON drift_reports FOR SELECT
  USING (auth.uid()::text = ANY(
    string_to_array(current_setting('app.admin_user_ids', true), ',')
  ));
```

Note: column named `weather_json` (not `noaa_conditions_json`) — source is Open-Meteo.

### `weather_json` Shape

```json
{
  "source": "open-meteo",
  "date": "2024-07-14",
  "lat": 34.74,
  "lon": -91.83,
  "hourly_summary": {
    "wind_speed_mph_avg": 8.2,
    "wind_direction_deg_avg": 212,
    "wind_direction_label": "SSW",
    "temp_f_at_noon": 91.4
  },
  "raw": { "...": "full Open-Meteo response" }
}
```

`wind_speed_mph` populated from `hourly_summary.wind_speed_mph_avg`. `wind_direction` populated from `hourly_summary.wind_direction_label` (compass label, e.g. "SSW"). `temp_at_time_f` populated from `hourly_summary.temp_f_at_noon`. Farmer cannot override before submit (fields are shown as info on success card only).

---

## Backend Services

### `weather_history.py`

```python
async def fetch_historical_weather(lat: float, lon: float, date: str) -> dict:
    """
    GET https://archive-api.open-meteo.com/v1/archive
    params: latitude, longitude, start_date=date, end_date=date,
            hourly=windspeed_10m,winddirection_10m,temperature_2m,
            wind_speed_unit=mph, temperature_unit=fahrenheit,
            timezone=America/Chicago
    Returns summary dict on success, {"available": False} on any error.
    """
```

No caching — incident dates are fixed, fetched once on report creation. 3s timeout. Graceful fail pattern from `context.py`.

### `drift_service.py`

```python
async def create_report(farmer_id: str, data: dict, weather: dict) -> dict
async def get_report(report_id: str, farmer_id: str) -> dict | None
async def list_reports(farmer_id: str) -> list[dict]
async def list_all_reports(
    county_fips: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None
) -> list[dict]  # admin only
```

All use service-role Supabase client (same as `session.py`). `get_report` filters by `farmer_id` to prevent cross-user access.

### `pdf_generator.py`

```python
def generate_complaint_pdf(report: dict, farmer_profile: dict) -> bytes
```

Synchronous reportlab. PDF sections:

| Section | Content |
|---|---|
| Header | "AR State Plant Board — Dicamba Drift Incident Complaint" + generated date |
| Complainant | Name, county, contact info (from `farmer_profiles`) |
| Incident | Date, affected crop, estimated acres, county |
| Weather Conditions | Table: wind speed, wind direction, temperature — from Open-Meteo (or "Unavailable" if null) |
| Symptoms | Description + symptom type |
| Suspected Source | Applicator name if provided |
| Photo Checklist | ☐ Field damage photos taken ☐ GPS-tagged photos ☐ Spray records requested |
| Submission Instructions | Pre-addressed to `arkansasstateplantboard@agriculture.arkansas.gov` + ASPB mailing address: 1 Natural Resources Dr, Little Rock, AR 72205 |

### `routers/drift_reports.py`

Thin router. Key behaviors:
- `POST /drift-reports`: resolves county lat/lon from `counties.py`, calls `weather_history.fetch_historical_weather`, calls `drift_service.create_report`, returns created report
- `GET /{id}/pdf`: fetches report + farmer profile, calls `pdf_generator.generate_complaint_pdf`, returns `StreamingResponse(bytes, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=drift_report_{id}.pdf"})`
- `GET /admin/drift-reports`: requires `require_admin`, calls `drift_service.list_all_reports` with optional query params

---

## Frontend

### `DriftReportWizard.jsx` — 3-step wizard

Follows `RegisterForm.jsx` pattern: same `StepIndicator` component, same `INPUT_CLS`/`BTN_PRIMARY_CLS` Tailwind constants, same glassmorphism card style.

**Step 1 — Incident Basics**
- Incident date (date input, required, max = today)
- Affected crop (select: rice / soybean / other)
- Estimated acres (number input)
- County (pre-filled from profile, editable select)

**Step 2 — Conditions**
- Wind speed mph (number, placeholder "Auto-filled on submit")
- Wind direction (text, placeholder "Auto-filled on submit")
- Temperature °F (number, placeholder "Auto-filled on submit")
- Time of day (time input, optional)
- Symptoms (multi-select checkboxes: Cupping, Strapping, Stunting, Discoloration, Other)
- Symptoms description (textarea)

Weather auto-fill happens server-side on final submit — Step 2 fields start empty with placeholder text. On success, the response includes the auto-populated `wind_speed_mph`, `wind_direction`, `temp_at_time_f` values; the success card displays them so the farmer can confirm. Editing after submission is out of scope for this feature.

**Step 3 — Source & Submit**
- Suspected applicator name (text, optional)
- Nearest field boundary description (text, optional)
- Photo reminder checklist (3 checkboxes — display only, no file upload)
- "Submitted to ASPB already?" toggle
- Submit button → calls `useDriftReports.createReport()`
- On success: show success card with "Download PDF" button

### `useDriftReports.js`

```js
createReport(data)  // POST /api/v1/drift-reports → { id, ... }
listReports()       // GET  /api/v1/drift-reports  → [...]
downloadPdf(id)     // GET  /api/v1/drift-reports/:id/pdf → blob → browser download
```

`downloadPdf` uses `api.get(..., { responseType: 'blob' })` + `URL.createObjectURL` + programmatic `<a>` click — triggers download without opening a new tab.

### Sidebar Nav

New item in `Sidebar.jsx` between Sessions and Profile.
- EN: "Drift Report" | ES: "Reporte de Deriva"
- Icon: warning/alert icon from existing Heroicons set
- Visible to all authenticated users (not admin-only)

New i18n keys: `driftReport`, `driftReportNav`, `driftReportSubtitle`, step titles, field labels, symptom options, submit labels (all EN + ES).

### Admin Dashboard — Drift Reports Tab

`AdminDashboardPage.jsx` gets a tab bar above existing content:
- **"Overview"** tab — current dashboard content unchanged
- **"Drift Reports"** tab — new content:

1. **Choropleth toggle** — two buttons above `ARCountyMap`: "Query Volume" | "Drift Reports". `ARCountyMap` receives `dataLayer: "queries" | "drift"` prop + `driftData: {[fips]: count}`. Drift layer uses amber `#E9A228` gradient (distinguishable from existing green query layer).

2. **Date range filter** — two `<input type="date">` fields (From / To), filters list client-side.

3. **Report list** — table columns: County, Date, Crop, Symptoms (truncated 60 chars), Submitted to ASPB (✓/—). 20 rows per page, simple prev/next pagination.

Admin data from new `GET /api/v1/admin/drift-reports` endpoint, added to `useAdmin.js` as `useDriftReportAdmin({ dateFrom, dateTo })`.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Open-Meteo fails / timeout | Report created with null weather fields; PDF shows "Weather data unavailable" in conditions table |
| `GET /{id}/pdf` — not found or not owned | 404; frontend shows inline Alert |
| reportlab exception | 500 + logged traceback; frontend shows "PDF generation failed, try again" Alert |
| Supabase insert fails | 500; frontend catches + shows error Alert (same pattern as feedback widget) |
| Admin endpoint called by non-admin | 403 from `require_admin` (existing behavior) |

---

## Iterative Testing Checkpoints

Build and verify in this exact order — do not proceed to next checkpoint until current one passes.

### Checkpoint 1 — Migration + bare router
- Run `006_drift_reports.sql` against local Supabase
- Verify table exists: `SELECT * FROM drift_reports LIMIT 1;`
- Register empty router in `main.py`
- Verify `GET /api/v1/drift-reports` returns `[]` (authenticated)
- **Gate:** curl returns 200 with empty array

### Checkpoint 2 — Weather service
- Run `pytest backend/tests/test_weather_history.py` (mock httpx)
- Manual smoke: `python -c "from services.weather_history import fetch_historical_weather; import asyncio; print(asyncio.run(fetch_historical_weather(34.74, -91.83, '2024-07-14')))"`
- **Gate:** returns dict with `hourly_summary` keys populated

### Checkpoint 3 — Create + list reports
- `pytest backend/tests/test_drift_reports.py` (mock Supabase)
- curl `POST /api/v1/drift-reports` with test token + sample payload
- Verify row in Supabase table
- **Gate:** curl returns 201 with report id; row visible in Supabase dashboard

### Checkpoint 4 — PDF generation
- `pytest backend/tests/test_pdf_generator.py`
- curl `GET /api/v1/drift-reports/{id}/pdf` → save to `test.pdf` → open manually
- **Gate:** PDF opens, all sections present, weather table shows values (or "Unavailable" if Open-Meteo was mocked)

### Checkpoint 5 — Wizard frontend (dev server)
- `npm run dev` + backend on :8000
- Navigate to `/drift-report`
- Complete all 3 steps → submit
- Verify: report row in Supabase, success card appears, "Download PDF" triggers file download
- **Gate:** wizard completes without console errors; PDF downloads

### Checkpoint 6 — Sidebar nav
- Verify "Drift Report" link appears in sidebar for regular user
- Verify `/drift-report` route renders wizard
- Verify EN/ES toggle switches labels
- **Gate:** nav item visible, labels switch correctly

### Checkpoint 7 — Admin tab
- Log in as admin user
- Navigate to `/admin`
- Verify "Drift Reports" tab appears
- Verify choropleth toggle switches between query volume and drift layers
- Verify date filter narrows the list
- **Gate:** tab renders, choropleth toggles, filter works

### Checkpoint 8 — E2E Playwright
- `npx playwright test e2e/drift.spec.js`
- **Gate:** all tests pass (mocked endpoints, no live services)

---

## Testing Plan

### Backend (`pytest`)
- `backend/tests/test_weather_history.py` — mock httpx, assert summary extraction + graceful fail
- `backend/tests/test_pdf_generator.py` — fixture data, assert returns bytes + non-zero length
- `backend/tests/test_drift_reports.py` — mock Supabase, test all 5 endpoints (401, 404, 403, 200)

### Frontend (Vitest)
- `frontend/src/hooks/useDriftReports.test.js` — mock api, assert createReport + downloadPdf shape

### E2E (Playwright)
- `frontend/e2e/drift.spec.js` — mock POST + GET pdf via `page.route()`; complete wizard 3 steps → submit → download link appears

---

## Out of Scope (this feature)

- Actual photo file upload (flagged in spec as future work)
- Email submission directly from the app
- ASPB form field parsing / fillable PDF
- Chat pre-fill from drift-related queries
