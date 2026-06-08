# F4 Dicamba — Phase 3: Gate B Field & Buffer Map (OUTLINE)

**Status:** Outline. Detail this plan when Phase 2 ships. Fourth phase of `AgroAdvisor_F4_PRD_v3.md`.
**Ships:** Gate B — a field-level proximity map (react-leaflet) with buffer rings + the static
research-station list, plus applicator-confirmation prompts for what the tool can't see.

## Context

PRD §3 Gate B: 1 mi from university/USDA research stations, ½ mi from certified organic/specialty,
¼ mi from non-dicamba-tolerant crops. PRD §6: stations = **verifiable**; registries = **partial**
(voluntary, incomplete); unregistered neighbors = **human-attested**. Buffer distances already live in
`backend/data/dicamba_rules.json` (`buffers_ft`, Phase 0). Field lat/lon already captured (Phase 2 pin).

## Scope

- **Frontend:** extend the Phase 2 react-leaflet map to a field view — zoom to pin; draw buffer rings
  (5280 / 2640 / 1320 ft from `buffers_ft`); plot research-station markers; show distance-to-nearest.
  Add `human_attested` prompt: "No non-tolerant crop within ¼ mile?" (feeds `sensitive_crops_checked`).
- **Backend data:** new static file `backend/data/ar_research_stations.json` (name, lat/lon) — UA/USDA
  Arkansas research stations.
- **Backend logic:** `evaluate_gate_b(rules, req)` appended to `services/spray_check.py` — haversine
  distance (ft) from field point to each station vs `research_station` buffer = `verifiable_fact`;
  non-tolerant-neighbor = `human_attested` → `needs_confirmation` unless attested. Append to
  `run_spray_check` gate list (no schema change — `GateResult` already generic).
- **Partial tier:** organic/specialty depends on FieldWatch registries (Phase 5) — until then, surface
  as a `human_attested` confirmation, noting data is incomplete (PRD §6 "partial").

## TDD (sketch)

- Backend: haversine distance correctness; in-buffer → fail, out-of-buffer → pass; nearest-station
  selection; non-tolerant confirmation → `needs_confirmation` vs attested → pass.
- Frontend: ring radii match `buffers_ft`; station markers render; distance label; confirmation prompt
  gating.

## Verification

Backend pytest for `evaluate_gate_b`; vitest/Playwright for the map (mock `/check`); manual: pin a
field near a known station, confirm rings + station pin + Gate B fail when inside the 1-mile ring.

## Open questions (resolve when detailing)

- Authoritative source + coordinates for AR research stations.
- Whether to show all 75-county context or just the zoomed field neighborhood.
- Downwind geometry for Gate D (wind direction × Gate B sites) — coordinate with Phase 4.
