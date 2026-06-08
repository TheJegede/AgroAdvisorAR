# F4 Dicamba — Phase 4: Record Generator + Gate D (DESIGN)

**Status:** Approved 2026-06-08 (dialogue). Detailed design for the fifth phase of
`AgroAdvisor_F4_PRD_v3.md`. Supersedes the outline `docs/superpowers/plans/2026-06-08-f4-dicamba-phase4-record.md`.
**Ships:** `POST /api/v1/dicamba/record` (persist the decision + generate a PDF record), Gate D
(equipment & target, incl. full verifiable downwind geometry), and a `/spray-records` history page.
This is where "the record is a byproduct" (PRD §4) becomes real.

## Locked decisions (user, 2026-06-08)

1. **Gate D = full verifiable downwind geometry + human-attested equipment checks.** Not deferred,
   not advisory-only — a real fail verdict when a research station is downwind and inside its buffer.
2. **Frontend = wizard save + PDF download AND a `/spray-records` history page** (mirrors the
   drift-reports list).
3. **Record = fully immutable: no edit, no delete, ever** (append-only audit log). Strongest
   legal-defensibility stance. DB enforces it (no UPDATE/DELETE RLS policy); the service exposes no
   mutate/delete functions.

## Judgment calls (not separately asked)

- **`POST /record` re-runs the check server-side authoritatively.** The client sends the same
  `SprayCheckRequest` (lat/lon/product/at/attestation); the server re-fetches weather + stations,
  recomputes ALL gates via `run_spray_check`, and persists THAT snapshot. Client-submitted gate
  verdicts are never trusted (anti-tamper / the record reflects what the tool actually computed).
- **PDF on-demand** via `GET /record/{id}/pdf` `StreamingResponse` (mirror `routers/drift_reports.py`).
  No Supabase storage bucket — regenerate from the frozen record each download.
- **Migration `009_spray_records.sql`** is the next number (008 is the latest).

## Context / reuse

- IDOR-write pattern: `backend/services/session.py add_message` — service-role client
  (`_get_service_client`) + manual `farmer_id` filter + ownership gate before any read/write.
- Persistence + PDF + list/get/stream endpoint shape: `services/drift_service.py` +
  `routers/drift_reports.py` + `services/pdf_generator.py generate_complaint_pdf`.
- RLS template: `supabase/migrations/006_drift_reports.sql` (owner FOR ALL + admin FOR SELECT).
- `weather_now.fetch_forecast_conditions` already returns `wind_direction_deg` +
  `wind_direction_label` → downwind geometry is feasible with no weather-service change.
- Gate B station list + buffers + `nearest_station`/`haversine_ft` shipped Phase 3
  (`services/spray_stations.py`, `services/spray_check.py`). `run_spray_check` already takes `stations`.
- `ApplicatorAttestation` reserves `boom_height_ok`, `droplet_setup_ok`, `tank_clean_ok` (Phase 1).

## Section 1 — Data model: `backend/supabase/migrations/009_spray_records.sql`

Immutable table `public.spray_records`:

| column | type | note |
|---|---|---|
| `id` | uuid PK default `gen_random_uuid()` | |
| `farmer_id` | uuid FK `farmer_profiles(id)` ON DELETE CASCADE | stamped from JWT, never client |
| `created_at` | timestamptz default `now()` | |
| `lat` | double precision NOT NULL | field point |
| `lon` | double precision NOT NULL | field point |
| `product` | text NOT NULL | |
| `applied_at` | timestamptz NOT NULL | = `req.at` |
| `overall_status` | text NOT NULL | rollup |
| `rule_version` | text NOT NULL | frozen ruleset id |
| `gates` | jsonb NOT NULL | per-gate results snapshot |
| `attestation` | jsonb NOT NULL | what the human confirmed |
| `weather_json` | jsonb | frozen weather snapshot (defensibility) |

No `updated_at`. Index `spray_records_farmer_recent (farmer_id, created_at DESC)`.

RLS (`ENABLE ROW LEVEL SECURITY`):
- `"farmer reads own spray records"` — `FOR SELECT USING (farmer_id = auth.uid())`.
- `"farmer inserts own spray records"` — `FOR INSERT WITH CHECK (farmer_id = auth.uid())`.
- `"admin reads all spray records"` — `FOR SELECT USING (admin_user_ids match)` (mirror 006).
- **No UPDATE or DELETE policy** → both are denied for everyone (immutability enforced at the DB).

## Section 2 — Gate D: `evaluate_gate_d(rules, req, weather, stations)`

Appended to `services/spray_check.py`; wired into `run_spray_check` → gate order **A, B, C, D**.
`run_spray_check` already receives `weather` + `stations`, so no new top-level plumbing.

**Verifiable downwind check (`downwind_clear`, `verifiable_fact`):**
- Wind blows TOWARD `wind_toward = (wind_direction_deg + 180) mod 360`.
- For each station: `bearing_deg(field → station)`; it is *downwind* if
  `angular_diff(wind_toward, bearing) <= _DOWNWIND_HALF_ANGLE_DEG` (default **45°**, a 90° cone) AND
  `haversine_ft(field, station) < buffers_ft.research_station`.
- Any station downwind AND inside its buffer → `fail` (observed = which station + bearing).
- Wind unavailable / `wind_direction_deg is None` → `needs_confirmation` (never a guessed pass).
- No station downwind-and-inside → `pass`.
- Geometry anchors = the geocoded research stations only; non-tolerant/organic neighbors stay
  human-attested (not geocoded) in Gate B.

**New pure helpers in `services/spray_stations.py`** (unit-test anchors):
- `bearing_deg(lat1, lon1, lat2, lon2) -> float` — initial great-circle bearing, 0–360.
- `angular_diff(a, b) -> float` — smallest absolute angle between two bearings, 0–180.

**Human-attested checks** (`human_attested`, `needs_confirmation` unless attested True):
- `boom_height` ← `attestation.boom_height_ok` (≤ 2 ft, from `weather_thresholds.boom_height_ft_max`).
- `droplet_size` ← `attestation.droplet_setup_ok` (Ultra Coarse or coarser).
- `tank_clean` ← `attestation.tank_clean_ok`.
- `additives` ← new `attestation.additives_ok` (required VRA+DRA present, prohibited AMS absent;
  reasons reference `rules.required_additives` / `rules.prohibited_additives`).
- `ground_application` ← new `attestation.ground_application_only` (no aerial OTT).

**`models/spray.py`:** add `additives_ok` + `ground_application_only` to `ApplicatorAttestation`.

**Consequence:** `/check` now returns 4 gates, so the wizard Step 4 gains a Gate D equipment-
attestation block (below) — otherwise Gate D can never clear.

`_DOWNWIND_HALF_ANGLE_DEG` is a module constant in `spray_check.py` with a comment (conservative
90° cone); promotable to rules-as-data later without touching callers.

## Section 3 — Service: `backend/services/spray_record.py`

Mirrors `session.py` (service-role client + manual `farmer_id`):
- `create_record(farmer_id: str, payload: dict) -> dict` — builds the row with `farmer_id` from the
  JWT (never client-supplied), inserts via `_get_service_client()`, `_assert_insert`, returns row.
- `get_record(record_id: str, farmer_id: str) -> dict | None` — `.eq("id", …).eq("farmer_id", …)`
  `.maybe_single()`; foreign/missing → `None` (IDOR gate).
- `list_records(farmer_id: str, limit: int = 50) -> list[dict]` — owner rows, `created_at DESC`.
- No update/delete functions (immutability in code + DB).

## Section 4 — Endpoints (extend `backend/routers/dicamba.py`)

- `POST /api/v1/dicamba/record` (`response_model` = a `SprayRecord` model; auth `user["sub"]`):
  resolve rules (422 on none), `fetch_forecast_conditions`, `load_stations`, `run_spray_check`
  authoritatively, assemble the snapshot payload, `create_record(user["sub"], payload)`, return record.
- `GET /api/v1/dicamba/records` → `list_records(user["sub"])`.
- `GET /api/v1/dicamba/record/{record_id}` → `get_record`; 404 if `None`.
- `GET /api/v1/dicamba/record/{record_id}/pdf` → `get_record` (404 if `None`) →
  `generate_spray_record_pdf(record, profile)` → `StreamingResponse(media_type="application/pdf")`.

New `SprayRecord` pydantic model in `models/spray.py` for the response (mirror table columns).

## Section 5 — PDF: `generate_spray_record_pdf(record, farmer_profile)` in `pdf_generator.py`

Same ReportLab idiom as `generate_complaint_pdf` (`_table` helper reused). Sections:
1. Header: "AGROADVISOR AR — DICAMBA SPRAY RECORD" + generated date.
2. Applicator & field: name, county/email, lat/lon, `applied_at`, product, `rule_version`.
3. Per-gate outcomes: one labeled block per gate A/B/C/D, each check's label / status / observed.
4. Attestations: the list of what the human confirmed (from `attestation` JSONB).
5. Footer (bold): "This is a record of your decision and the conditions you confirmed. It is NOT
   legal advice or an authorization to spray. Always verify the product label and current state rules."
Handles missing weather / empty profile (mirror `test_pdf_generator.py`).

## Section 6 — Frontend

- `hooks/useSprayCheck.js`: add `saveRecord(payload) -> POST /dicamba/record`. (`payload` = the same
  `{lat, lon, product, at, attestation}` shape `runCheck` already builds.)
- `components/dicamba/SprayCheckWizard.jsx` Step 4 (Confirm & Result):
  - Gate D equipment checkboxes (`boom_height_ok`, `droplet_setup_ok`, `tank_clean_ok`,
    `additives_ok`, `ground_application_only`) that re-run `/check` (same pattern as the inversion +
    Gate B toggles).
  - **Save record** button → `saveRecord` → on success reveal a **Download PDF** link
    (`/api/v1/dicamba/record/{id}/pdf`). EN+ES, `min-h-touch`, advisory framing (never "approved").
- New `hooks/useSprayRecords.js` (`fetchRecords` → `GET /dicamba/records`) + `pages/SprayRecordsPage.jsx`
  + route `/spray-records` + sidebar nav `t.sprayRecords`: list rows (date, product, outcome badge,
  PDF link), mirrors the drift-reports list. i18n keys EN+ES.

## Section 7 — TDD

- **Service** (`tests/test_spray_record.py`, fake Supabase client): create stamps `farmer_id` from the
  arg, not the payload; `get_record`/`list_records` filter by `farmer_id` (foreign → None / []);
  no update/delete surface exists.
- **Gate D** (extend `tests/test_spray_check.py`): `bearing_deg`/`angular_diff` known pairs; station
  downwind + inside buffer → `fail`; downwind but outside buffer → not fail; crosswind → `pass`; wind
  unavailable → `needs_confirmation`; each human-attested item `needs_confirmation` unattested / `pass`
  attested; `run_spray_check` returns gates {A,B,C,D} and rolls up.
- **PDF** (`tests/test_pdf_generator.py`): valid `%PDF` magic bytes; missing weather / empty profile OK.
- **Router** (extend `tests/test_dicamba_router.py`): `/record` requires auth + uses authenticated
  owner + 422 no-rules; `/record/{id}` 404 foreign; `/records` lists owner only.
- **Frontend**: `useSprayCheck.test.js` save request shape (incl. all attestation fields);
  `useSprayRecords` list; e2e `spray-check.spec.js` — attest Gate D on Step 4, Save → PDF link appears;
  new/extended spec asserts `/spray-records` lists the saved record (mocked routes).

## Verification

Apply `009` to a Supabase branch. `cd backend && pytest` green (service + Gate D + PDF + router).
`cd frontend && npm run test` + `npm run lint` clean; `npx playwright test spray-check` green (mocked).
Manual: run a check → attest Gate D → Save → download the PDF → confirm a second user 404s on the
first user's record (RLS + app gate). Old drift wizard + Phase 2/3 flow still reachable.

## Out of scope (later phases)

Automated FieldWatch / EPA Bulletins Live! Two registry integration (Phase 5); geocoding non-tolerant /
organic neighbors for downwind geometry (stays human-attested here); professional Spanish copy review
(Phase 5); record export/retention tooling for legal discovery. `_DOWNWIND_HALF_ANGLE_DEG` and station
coordinates remain heuristic / UNVERIFIED — validate before any production/pilot reliance.

## Deploy note

HF backend is **not** auto-deployed; `/record` + `/records` + the 4th gate go live only after the
orphan-branch HF redeploy (deferred by owner until all F4 phases land — see CLAUDE.md Priorities #2 /
PROGRESS.md). Migration `009` must be applied to prod Supabase at cutover.
