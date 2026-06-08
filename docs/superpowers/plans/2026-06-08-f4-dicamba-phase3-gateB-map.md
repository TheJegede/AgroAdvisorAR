# F4 Dicamba — Phase 3: Gate B Field & Buffer Map

**Status:** Detailed 2026-06-08 (Phase 2 shipped — `main` `5aec0c1`). Fourth phase of
`AgroAdvisor_F4_PRD_v3.md`.
**Ships:** Gate B — the `/check` endpoint adds `evaluate_gate_b` (verifiable station distance +
human-attested neighbor confirmations), a new static research-station list + loader + `GET
/dicamba/stations`, and a **new dedicated wizard step** ("Field & Buffers") that draws buffer rings +
station markers on the react-leaflet field map and collects the two Gate B confirmations.
**Why now:** Phase 2 captured the field pin and the `/check` call returns all gates in one shot —
Gate B is the next gate that slots in with no schema change.

## Locked decisions (user, 2026-06-08)

1. **Station data = curated seed list, marked UNVERIFIED.** Hand-build `ar_research_stations.json`
   from public UA Division of Agriculture / USDA-ARS station names + approximate lat/lon, tagged
   `source: UNVERIFIED` exactly like `dicamba_rules.json`'s `source_citation`. Owner re-confirms later.
   Honesty-tier discipline (PRD §6) — the data's provenance is stated, not hidden.
2. **New dedicated Gate B step → wizard becomes 4 steps:** Eligibility (A) → **Field & Buffers (B)** →
   Live Conditions (C) → Confirm & Result. The field **pin moves to the new Step 2**; the live-
   conditions step reuses it.
3. **Two human-attested fields.** Add `organic_specialty_checked` alongside the reserved
   `sensitive_crops_checked` (= non-tolerant ¼ mi). Distinct distances, distinct reasons.

## Baked-in defaults (not asked — PRD-driven)

- Map = **zoomed field neighborhood**, not the 75-county view.
- **Gate D downwind geometry (wind × Gate B sites) is deferred to Phase 4** — out of scope here.
- Organic/specialty is a **Partial** tier (PRD §6): FieldWatch registries are Phase 5, so until then it
  is surfaced as a **human-attested** confirmation whose copy notes the registry data is incomplete.

## Context / reuse

- Buffers already in `backend/data/dicamba_rules.json` (`buffers_ft`: `research_station 5280`,
  `organic_specialty 2640`, `non_tolerant_crop 1320` ft — Phase 0).
- Field lat/lon captured by the Phase 2 pin (`SprayCheckWizard.jsx`).
- `/check` returns **all** gates in one response; `GateResult`/`CheckResult` are generic (PRD-noted "no
  schema change"). `GateId` Literal already includes `"B"`.
- `services/spray_rules.py` load+cache idiom is the template for the new station loader.
- `ApplicatorAttestation` already reserves `sensitive_crops_checked` (Gate B).

## Backend

### New data: `backend/data/ar_research_stations.json`
Array of `{ "id", "name", "lat", "lon" }` for UA Division of Agriculture / USDA-ARS Arkansas research
stations (e.g. Rice Research & Extension Center–Stuttgart, Northeast REC–Keiser, Pine Tree RES,
Rohwer RES, Lon Mann Cotton REC–Marianna, SEREC–Monticello, Vegetable RES–Kibler, Fruit RES–Clarksville,
Cotton Branch–Marianna, Newport Extension Center, Main Station–Fayetteville). Top-level wrapper:
`{ "source": "UNVERIFIED — curated from public UA System Division of Agriculture / USDA-ARS station
listings; re-confirm coordinates before production (PRD v3 §6/§8)", "stations": [...] }`.

### New service: `backend/services/spray_stations.py`
Mirror `spray_rules.py` load+cache. Exports:
- `load_stations(path=None) -> list[dict]` — cached read of the `stations` array.
- `haversine_ft(lat1, lon1, lat2, lon2) -> float` — great-circle distance in feet (earth radius
  20_902_231 ft). Pure function, the unit-test anchor.
- `nearest_station(lat, lon, stations) -> tuple[dict, float] | tuple[None, None]` — nearest station +
  its distance in ft (None when the list is empty).

### `backend/services/spray_rules.py`
Add accessor `buffers_ft(rules) -> dict` returning `rules["buffers_ft"]` (parallels `wind_bounds` etc.).

### `backend/models/spray.py`
Add `organic_specialty_checked: Optional[bool] = None` to `ApplicatorAttestation` (Gate B). Add a small
`ResearchStation(BaseModel)` (`id, name, lat, lon`) for the stations endpoint response.

### `backend/services/spray_check.py`
Add `evaluate_gate_b(rules, req, stations) -> GateResult` with three checks:
- **`station_buffer`** (`verifiable_fact`): `nearest_station` → distance ft vs `buffers_ft.research_station`.
  `pass` when distance **≥** buffer (field is clear), `fail` when **<** buffer (inside the protected
  ring). `observed` = `"{miles} mi to {station name}"`, `expected` = `"≥ 1.0 mi (5280 ft) from research
  stations"`. Empty station list → `needs_confirmation` ("station data unavailable"), never a guessed
  pass.
- **`non_tolerant_neighbor`** (`human_attested`): `pass` only if `req.attestation.sensitive_crops_checked
  is True`; else `needs_confirmation`. Reason references the ¼-mile non-dicamba-tolerant crop buffer.
- **`organic_specialty`** (`human_attested`, Partial): `pass` only if
  `req.attestation.organic_specialty_checked is True`; else `needs_confirmation`. Reason notes the ½-mile
  buffer **and** that registry data is incomplete (voluntary registries; Phase 5 FieldWatch).

Wire into `run_spray_check(req, rules, weather, stations)` — gate order **A, B, C**; rollup unchanged
(`fail` > `needs_confirmation` > `pass`). Signature gains `stations`.

### `backend/routers/dicamba.py`
- `check_spray`: load stations via `spray_stations.load_stations()` and pass to `run_spray_check`.
- New `GET /dicamba/stations` → `list[ResearchStation]` (auth via `get_current_user`, same as `/check`)
  so the map can plot markers. Cheap static read; no persistence.

## Frontend

### `frontend/src/hooks/useSprayCheck.js`
- `runCheck` attestation now carries both `sensitive_crops_checked` + `organic_specialty_checked`
  (plus the existing `no_inversion_observed`).
- Add `fetchStations()` → `GET /dicamba/stations` (returns the array; cache in component state).
- `getSprayStepErrors`: pin requirement stays on **step 2** (now the Field & Buffers step). Steps 3
  (live conditions) and 4 (result) impose no required fields. Update the test accordingly.

### `frontend/src/components/dicamba/SprayCheckWizard.jsx`
Restructure to 4 steps (`TOTAL_STEPS = 4`, retitle `STEP_TITLES_EN/ES`):
- **Step 1 — Eligibility (A):** unchanged (product + license/training).
- **Step 2 — Field & Buffers (B):** the react-leaflet map.
  - Pin placement moves here; on placement fire `/check` (as today).
  - Draw three `Circle`s centered on the pin, radius = buffer ft × 0.3048 m (`research 1609 m`,
    `organic 805 m`, `non_tolerant 402 m`) — `BUFFERS_FT` hardcoded constant mirroring
    `dicamba_rules.json` (same pattern as Phase 2's `APPROVED_PRODUCTS`), with a code comment.
  - Plot stations from `fetchStations()` as `CircleMarker`s (distinct from the field `Marker` pin — no
    extra icon asset).
  - Show distance-to-nearest from the Gate B `station_buffer` check `observed`.
  - Two confirmation checkboxes (non-tolerant ¼ mi → `sensitive_crops_checked`; organic/specialty ½ mi
    with an "incomplete data" note → `organic_specialty_checked`); toggling re-runs `/check` (same
    pattern as the inversion toggle).
- **Step 3 — Live Conditions (C):** the conditions summary **and** the inversion toggle move here from
  the old result step.
- **Step 4 — Confirm & Result:** per-gate `GateResultCard`s (now A/B/C) + outcome banner + rule version
  + advisory disclaimer (unchanged logic, just the final step).

Keep advisory framing (never "approved, spray now"), EN+ES, HC badges ≥4.5:1, `min-h-touch`.

## TDD

- **Backend** (`backend/tests/test_spray_stations.py` + extend `test_spray_check.py`):
  - `haversine_ft` against a known pair (e.g. Stuttgart↔Fayetteville ≈ known miles, tolerance).
  - `nearest_station` picks the closest; empty list → `(None, None)`.
  - `evaluate_gate_b`: pin inside research ring → `station_buffer` fail; well outside → pass; empty
    stations → `needs_confirmation`.
  - non-tolerant + organic/specialty → `needs_confirmation` unattested, `pass` when attested.
  - `run_spray_check` includes Gate B and rolls up correctly.
  - `GET /dicamba/stations` returns the seed list (route test).
- **Frontend** (`useSprayCheck.test.js`): step gating still flags missing pin on step 2; request body
  now includes both Gate B attestation fields.
- **Playwright** (extend `e2e/spray-check.spec.js`): mock `GET /dicamba/stations` + `/dicamba/check`
  (Gate B status driven by the request attestation, like the inversion mock); walk all 4 steps; assert
  buffer rings render (`.leaflet-interactive` paths) + at least one station marker; assert the Gate B
  card appears in the result and the two confirm toggles re-run `/check` and flip Gate B
  `needs_confirmation → pass`.

## Verification

`cd backend && pytest` green (new Gate B + stations tests, full suite). `cd frontend && npm run test`
(vitest) + `npm run lint` clean; `npx playwright test spray-check` green (mocked). Manual: `npm run dev`,
pin a field near a seed station, confirm the three rings + station markers + distance label render, Gate
B card shows `station_buffer` fail when the pin sits inside the 1-mile ring, and the two confirmations
flip their checks. Old drift wizard + Phase 2 flow still reachable.

## Out of scope (later phases)

Automated FieldWatch / EPA Bulletins Live! Two registry integration (Phase 5); the `/record` save + PDF
with attestation fields (Phase 4); Gate D downwind geometry combining wind direction × Gate B sites
(Phase 4); professional Spanish copy review (Phase 5). Station coordinates ship **UNVERIFIED** — owner
must validate before any production/pilot reliance.

## Notes for the builder

- `/check` already returns every gate in one call — Gate B is additive; do **not** add a separate
  per-gate endpoint.
- HF backend is **not auto-deployed**; `/check` + `/stations` go live only after the orphan-branch HF
  redeploy (deferred by owner until all F4 phases land — see `PROGRESS.md` / CLAUDE.md Priorities #2).
- Keep station data server-side single-source: both `evaluate_gate_b` and `GET /dicamba/stations` read
  the same `spray_stations.load_stations()`.
