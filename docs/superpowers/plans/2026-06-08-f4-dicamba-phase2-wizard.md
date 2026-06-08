# F4 Dicamba — Phase 2: Spray-Check Wizard (3-step gate flow)

**Status:** Ready after Phase 1. Third phase of `AgroAdvisor_F4_PRD_v3.md`.
**Ships:** A NEW 3-step wizard, coexisting with the old drift-report wizard, wired to
`POST /api/v1/dicamba/check`. End-to-end usable with the easy gates (A + C).
**Why now:** Makes Phase 1 real for a user — walk the flow, drop a field pin, get a per-gate answer.

## Context

PRD §5 maps the existing 3-step wizard onto the gate flow. Locked decisions: **coexist** with the old
drift tool (keep the ASPB complaint generator), **field location = click a map pin** → real lat/lon,
**add react-leaflet** (keep react-simple-maps for the admin choropleth). Reuse the step/validation
pattern from `frontend/src/components/drift/DriftReportWizard.jsx` and the hook pattern from
`frontend/src/hooks/useDriftReports.js` (axios via `frontend/src/lib/api.js`, Bearer from localStorage,
`useLang` for en/es).

## Files

### New: `frontend/src/components/dicamba/SprayCheckWizard.jsx`

Copy `DriftReportWizard.jsx`'s `StepIndicator`, `FieldError`, step-validation structure.

- **Step 1 — Eligibility (Gate A inputs):** product `<select>` (from rules-derived list — fetch or
  hardcode the 3 approved ids for now), applicator license/training attestation checkboxes. Validation:
  product required, license attested.
- **Step 2 — Live conditions (Gate C):** react-leaflet single-marker click-to-place map → sets
  `{lat, lon}`; on placement, call `/check` and show weather summary (wind, temp, 48h rain, soil,
  sunrise/sunset). Validation: pin required.
- **Step 3 — Attest + result:** per-gate `GateResult` cards; inversion confirmation toggle
  (`no_inversion_observed`) that re-runs `/check`; outcome banner driven by `overall_status`
  (`pass` → "Meets the requirements you confirmed"; `fail`/`needs_confirmation` → "Not clear — here's
  why" with reasons). Advisory framing per PRD §4 — never "Approved, spray now."

### New: `frontend/src/hooks/useSprayCheck.js`

Mirror `useDriftReports.js`. `runCheck({lat, lon, product, at, attestation})` → `POST
/api/v1/dicamba/check` via `lib/api.js`. Export a step-validation helper
(`getSprayStepErrors(form, step)`) like `getDriftStepErrors` for unit testing.

### Map dependency

Add `react-leaflet` + `leaflet` to `frontend/package.json`. `.npmrc` already has
`legacy-peer-deps=true` (React 19). Import Leaflet CSS. Minimal single-marker map only — full Gate B
buffer-ring view is Phase 3.

### Result UI / a11y

`GateResult` cards show tier badges (verifiable fact vs confirm-needed) and pass/fail/needs-confirmation
states. Honor the design-audit Low-badge contrast fix (≥4.5:1) and touch-target sizes. All copy in EN +
ES via `useLang`.

### Route / entry

Add a nav entry + route distinct from the existing drift tool (coexist — do not replace its link).

## TDD

- `frontend/src/hooks/useSprayCheck.test.js` (vitest, mirror `useDriftReports.test.js`): per-step
  validation (missing product, missing pin), request body shape, response handling.
- Playwright spec (repo-root `tests/`) mocking `/api/v1/dicamba/check` via `page.route()`: walk all 3
  steps, place a pin, assert gate cards + outcome banner; assert inversion toggle re-runs check.

## Verification

`cd frontend && npm run test` (vitest) + `npm run lint` clean; `npx playwright test` spray spec green
(mocked). Manual: `npm run dev`, walk the wizard, drop a pin over an AR field, confirm Gate A + C
cards render and the inversion toggle flips the outcome. Old drift wizard still reachable + working.

## Out of scope

Gate B buffer rings / station pins (Phase 3); record save + PDF (Phase 4); full Spanish parity audit
(Phase 5 — copy is bilingual from the start but not yet professionally reviewed).
